#pragma once
// Pure protocol helpers for the Voltronic PI30 dialect (with CRC) and the Solar Plug
// "H" dialect (no CRC). No ESPHome includes on purpose: this file is compiled and
// tested on the PC (tests/esphome/test_protocol.cpp). Ports of
// custom_components/voltronic_solar_inverter/protocol/{framing,parsers,h_parsers}.py.

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <string>
#include <vector>

namespace esphome {
namespace voltronic {
namespace proto {

static const char CR = '\r';

// CRC-16/XMODEM (poly 0x1021, init 0).
inline uint16_t crc16_xmodem(const uint8_t *d, size_t n) {
  uint16_t crc = 0;
  for (size_t i = 0; i < n; i++) {
    crc ^= (uint16_t) d[i] << 8;
    for (int b = 0; b < 8; b++)
      crc = (crc & 0x8000) ? (uint16_t) ((crc << 1) ^ 0x1021) : (uint16_t) (crc << 1);
  }
  return crc;
}

// A CRC byte equal to '(' CR or LF is incremented by one.
inline uint8_t escape_crc_byte(uint8_t v) { return (v == 0x28 || v == 0x0D || v == 0x0A) ? (uint8_t) (v + 1) : v; }

// PI30 request: <ASCII> <CRC hi> <CRC lo> CR
inline std::string encode_pi30(const std::string &cmd) {
  uint16_t crc = crc16_xmodem((const uint8_t *) cmd.data(), cmd.size());
  std::string out = cmd;
  out += (char) escape_crc_byte((uint8_t) (crc >> 8));
  out += (char) escape_crc_byte((uint8_t) (crc & 0xFF));
  out += CR;
  return out;
}

// H dialect request: <ASCII> CR (no CRC).
inline std::string encode_plain(const std::string &cmd) { return cmd + CR; }

// `frame` = bytes received before the CR, starting with '('. Returns the payload
// without '(' and without the two CRC bytes; false on a malformed frame or CRC mismatch.
inline bool decode_pi30(const std::string &frame, std::string &payload) {
  if (frame.size() < 4 || frame[0] != '(')
    return false;
  size_t body_len = frame.size() - 2;
  uint16_t crc = crc16_xmodem((const uint8_t *) frame.data(), body_len);
  if ((uint8_t) frame[body_len] != escape_crc_byte((uint8_t) (crc >> 8)) ||
      (uint8_t) frame[body_len + 1] != escape_crc_byte((uint8_t) (crc & 0xFF)))
    return false;
  payload = frame.substr(1, body_len - 1);
  return true;
}

inline bool decode_plain(const std::string &frame, std::string &payload) {
  if (frame.size() < 2 || frame[0] != '(')
    return false;
  payload = frame.substr(1);
  return true;
}

inline std::vector<std::string> split_tokens(const std::string &s) {
  std::vector<std::string> out;
  size_t i = 0;
  while (i < s.size()) {
    while (i < s.size() && (s[i] == ' ' || s[i] == '\t'))
      i++;
    size_t j = i;
    while (j < s.size() && s[j] != ' ' && s[j] != '\t')
      j++;
    if (j > i)
      out.push_back(s.substr(i, j - i));
    i = j;
  }
  return out;
}

// Strict number parsing: the whole token must be consumed ("+00000" and "-0012" are fine).
inline bool parse_float(const std::string &s, float &out) {
  if (s.empty())
    return false;
  char *end = nullptr;
  double v = strtod(s.c_str(), &end);
  if (end == s.c_str() || *end != '\0' || std::isnan(v) || std::isinf(v))
    return false;
  out = (float) v;
  return true;
}

inline bool is_bits(const std::string &s, size_t exact_len = 0) {
  if (s.empty() || (exact_len && s.size() != exact_len))
    return false;
  for (char c : s)
    if (c != '0' && c != '1')
      return false;
  return true;
}

// H answers have no CRC, so a foreign answer can only be caught by these checks.
static const float MAX_GRID_POWER_W = 20000.0f;

// Check that `tokens` look like the answer to `cmd`. Mirrors the parsers' minimum field
// counts and the plausibility checks of the Python integration.
inline bool validate(const std::string &cmd, const std::vector<std::string> &t, const std::string &payload) {
  size_t n = t.size();
  float f;
  if (cmd == "QPIGS") {
    if (n < 17 || !is_bits(t[16], 8))
      return false;
    if (n > 20 && !is_bits(t[20], 3))
      return false;
    return true;
  }
  if (cmd == "QMOD")
    return payload.size() == 1;
  if (cmd == "QPIRI")
    return n >= 22;
  if (cmd == "QFLAG")
    return !payload.empty() && (payload[0] == 'E' || payload[0] == 'D');
  if (cmd == "QPIWS")
    return n == 1 && t[0].size() >= 31 && is_bits(t[0]);
  if (cmd == "Q1")
    return n >= 18;
  if (cmd == "QBEQI")
    return n >= 9;
  if (cmd == "QPI" || cmd == "QMN" || cmd == "QID" || cmd == "QVFW")
    return n >= 1;
  if (cmd == "HGRID") {
    if (n < 7 || !parse_float(t[0], f) || f < 0 || f > 300)
      return false;
    if (t[6][0] != '+' && t[6][0] != '-')
      return false;
    return parse_float(t[6], f) && std::fabs(f) <= MAX_GRID_POWER_W;
  }
  if (cmd == "HGEN")
    return n >= 6 && t[0].size() == 6 && t[1].size() == 5 && t[1][2] == ':';
  if (cmd == "HTEMP")
    return n >= 7;
  if (cmd == "HEEP1")
    return n >= 18 && t[3].size() >= 4;
  if (cmd == "HEEP2")
    return n >= 16;
  if (cmd == "HIMSG1")
    return n >= 2;
  return false;  // unknown command: never accept
}

// QPIWS bit classes, index = bit number: F fault, W warning, X fault if bit a1 is set else
// warning, - ignored (a0 PV loss is set whenever the array is disconnected; a13, a31 reserved).
static const char QPIWS_CLASSES[] = "-FFFFWFFFXXXW-WWXWFFFFWFFWWFWWF-";

// bit string -> true when any bit of the wanted class is set. `want_fault`: faults, else warnings.
inline bool qpiws_any(const std::string &bits, bool want_fault) {
  bool inverter_fault = bits.size() > 1 && bits[1] == '1';
  for (size_t i = 0; i < bits.size() && i < sizeof(QPIWS_CLASSES) - 1; i++) {
    if (bits[i] != '1')
      continue;
    char c = QPIWS_CLASSES[i];
    if (c == 'X')
      c = inverter_fault ? 'F' : 'W';
    if ((c == 'F' && want_fault) || (c == 'W' && !want_fault))
      return true;
  }
  return false;
}

// QFLAG "EabjvxyDkuz": letters after 'E' are enabled, after 'D' disabled.
// Returns 1 enabled, 0 disabled, -1 letter not present.
inline int qflag_state(const std::string &flags, char letter) {
  bool enabled = true;
  for (char c : flags) {
    if (c == 'E')
      enabled = true;
    else if (c == 'D')
      enabled = false;
    else if (c == letter)
      return enabled ? 1 : 0;
  }
  return -1;
}

}  // namespace proto
}  // namespace voltronic
}  // namespace esphome
