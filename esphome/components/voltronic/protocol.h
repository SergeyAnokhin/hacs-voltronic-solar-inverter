#pragma once
// Pure protocol helpers for the Voltronic PI30 dialect (with CRC) and the Solar Plug
// "H" dialect (no CRC). No ESPHome includes on purpose: this file is compiled and
// tested on the PC (tests/esphome/test_protocol.cpp). Ports of
// custom_components/voltronic_solar_inverter/protocol/{framing,parsers,h_parsers}.py.

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
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
  if (cmd == "HSTS")  // second output state: HSTS[2] char 4 is 0 or 1
    return n >= 3 && t[2].size() >= 5 && (t[2][4] == '0' || t[2][4] == '1');
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


// ---------------------------------------------------------------------------------------------
// Setting (write) commands. Mirror of protocol/commands.py. Every builder validates its
// argument; is_allowed_write() is the final gate in front of the UART: nothing that is not
// produced by one of these shapes can be sent. All are unverified on the unit until the owner
// tests them (docs/settings-map.md); the agent never sends any of them.
// ---------------------------------------------------------------------------------------------

enum class ValueKind : uint8_t { VOLT, INT };
struct ValueRule {
  const char *prefix;
  ValueKind kind;
  uint8_t digits;  // INT: zero-padded width
  double min;
  double max;
  double step;
};

// 24 V system ranges (Vevor manual) and the service-tool setters; see commands.py.
static const ValueRule VALUE_RULES[] = {
    {"PBCV", ValueKind::VOLT, 0, 22.0, 25.5, 0.5},   // P12
    {"PBDV", ValueKind::VOLT, 0, 24.0, 29.0, 0.5},   // P13
    {"PSDV", ValueKind::VOLT, 0, 20.0, 26.0, 0.1},   // P29
    {"PCVV", ValueKind::VOLT, 0, 24.0, 30.0, 0.1},   // P26
    {"PSLV", ValueKind::VOLT, 0, 20.0, 27.0, 0.1},   // P24
    {"PDSDV", ValueKind::VOLT, 0, 20.0, 30.0, 0.1},  // second output cut-off
    {"PDSRV", ValueKind::VOLT, 0, 20.0, 30.0, 0.1},  // second output recover
    {"BMSSDC", ValueKind::INT, 3, 0, 100, 1},        // P38
    {"BMSB2UC", ValueKind::INT, 3, 0, 100, 1},       // P39
    {"BMSU2BC", ValueKind::INT, 3, 0, 100, 1},       // P40
    {"BMSSRC", ValueKind::INT, 3, 0, 100, 1},        // P41
    {"PDSDS", ValueKind::INT, 3, 0, 100, 1},
    {"PDSRS", ValueKind::INT, 3, 0, 50, 1},
    {"PDDLYT", ValueKind::INT, 3, 0, 60, 5},
    {"PDDCGT", ValueKind::INT, 4, 0, 990, 5},
    {"DISCC", ValueKind::INT, 3, 0, 250, 1},
    {"MNCHGC", ValueKind::INT, 3, 1, 999, 1},  // P02, the value must come from QMCHGCR
    {"MUCHGC", ValueKind::INT, 3, 1, 999, 1},  // P11, the value must come from QMUCHGCR
};

inline const ValueRule *find_value_rule(const std::string &prefix) {
  for (const auto &r : VALUE_RULES)
    if (prefix == r.prefix)
      return &r;
  return nullptr;
}

inline bool value_ok(const ValueRule &r, double v) {
  if (std::isnan(v) || v < r.min - 1e-4 || v > r.max + 1e-4)
    return false;
  double steps = (v - r.min) / r.step;
  if (std::fabs(steps - std::round(steps)) > 1e-3)
    return false;
  if (r.kind == ValueKind::INT && std::fabs(v - std::round(v)) > 1e-6)
    return false;
  return true;
}

// PBCV/PBDV/PSDV/PCVV/PSLV/PDSDV/PDSRV<nn.n>, BMS*/PDS*/PDD*/DISCC/MNCHGC/MUCHGC<digits>.
inline bool build_value(const std::string &prefix, double v, std::string &out) {
  const ValueRule *r = find_value_rule(prefix);
  if (r == nullptr || !value_ok(*r, v))
    return false;
  char buf[24];
  if (r->kind == ValueKind::VOLT)
    snprintf(buf, sizeof(buf), "%s%04.1f", r->prefix, v);
  else
    snprintf(buf, sizeof(buf), "%s%0*d", r->prefix, (int) r->digits, (int) std::lround(v));
  out = buf;
  return true;
}

struct CodeRule {
  const char *prefix;
  uint8_t count;
  uint8_t allowed[3];
};
// POP: 0 solar first, 1 SBU (2 utility first is not verified: not offered). PCP: 0..2. PVENGUSE (P43): 0, 1.
// PDAULC / PDAULON: 0 off, 1 on.
static const CodeRule CODE_RULES[] = {
    {"POP", 2, {0, 1, 0}},    {"PCP", 3, {0, 1, 2}},    {"PVENGUSE", 2, {0, 1, 0}},
    {"PDAULC", 2, {0, 1, 0}}, {"PDAULON", 2, {0, 1, 0}},
};

inline bool code_ok(const CodeRule &r, int code) {
  for (uint8_t i = 0; i < r.count; i++)
    if (r.allowed[i] == code)
      return true;
  return false;
}

inline bool build_code(const std::string &prefix, int code, std::string &out) {
  for (const auto &r : CODE_RULES) {
    if (prefix == r.prefix) {
      if (!code_ok(r, code))
        return false;
      char buf[24];
      snprintf(buf, sizeof(buf), "%s%02d", r.prefix, code);
      out = buf;
      return true;
    }
  }
  return false;
}

static const char FLAG_LETTERS[] = "abjkuvxyz";  // QFLAG options this component may change

inline bool build_flag(char letter, bool enabled, std::string &out) {
  if (letter == '\0' || std::strchr(FLAG_LETTERS, letter) == nullptr)
    return false;
  out = std::string(enabled ? "PE" : "PD") + letter;
  return true;
}

// PBATCD<abc>: 000 auto, 101 no discharge, 110 no charge, 100 neither. 011 / 010 shut the unit down: never.
inline bool battery_control_ok(const std::string &abc) {
  return abc == "000" || abc == "101" || abc == "110" || abc == "100";
}

// PBATMAXDISC<nnn>: 0 = no limit, else 30..150 A.
inline bool build_max_discharging(int amps, std::string &out) {
  if (!(amps == 0 || (amps >= 30 && amps <= 150)))
    return false;
  char buf[24];
  snprintf(buf, sizeof(buf), "PBATMAXDISC%03d", amps);
  out = buf;
  return true;
}

// ^S???ACLT (AC output, P48/P49) or ^S???ACCT (AC charger, P46/P47) <HH>-<HH>; the three "?" are literal.
inline bool build_schedule(bool ac_output, int start_hour, int end_hour, std::string &out) {
  if (start_hour < 0 || start_hour > 23 || end_hour < 0 || end_hour > 23)
    return false;
  char buf[32];
  snprintf(buf, sizeof(buf), "^S???AC%cT%02d-%02d", ac_output ? 'L' : 'C', start_hour, end_hour);
  out = buf;
  return true;
}

// ^S???DAT<yymmddhhmmss>: the inverter clock, local time.
inline bool build_clock(int year, int month, int day, int hour, int minute, int second, std::string &out) {
  if (year < 2016 || year > 2099 || month < 1 || month > 12 || day < 1 || day > 31 || hour < 0 || hour > 23 ||
      minute < 0 || minute > 59 || second < 0 || second > 60)
    return false;
  char buf[32];
  snprintf(buf, sizeof(buf), "^S???DAT%02d%02d%02d%02d%02d%02d", year % 100, month, day, hour, minute, second);
  out = buf;
  return true;
}

// True when s[from .. from+n) is all digits and s ends there.
inline bool all_digits_at(const std::string &s, size_t from, size_t n) {
  if (s.size() != from + n)
    return false;
  for (size_t i = from; i < s.size(); i++)
    if (s[i] < '0' || s[i] > '9')
      return false;
  return true;
}

inline bool starts_with(const std::string &s, const char *prefix) { return s.compare(0, std::strlen(prefix), prefix) == 0; }

// The only setting texts that may ever be written to the UART.
inline bool is_allowed_write(const std::string &t) {
  if (t.size() == 3 && t[0] == 'P' && (t[1] == 'E' || t[1] == 'D') && t[2] != '\0' &&
      std::strchr(FLAG_LETTERS, t[2]) != nullptr)
    return true;
  for (const auto &r : CODE_RULES) {
    size_t n = std::strlen(r.prefix);
    if (starts_with(t, r.prefix) && all_digits_at(t, n, 2))
      return code_ok(r, atoi(t.c_str() + n));
  }
  if (starts_with(t, "PBATCD"))
    return t.size() == 9 && battery_control_ok(t.substr(6));
  if (starts_with(t, "PBATMAXDISC")) {
    if (!all_digits_at(t, 11, 3))
      return false;
    int v = atoi(t.c_str() + 11);
    return v == 0 || (v >= 30 && v <= 150);
  }
  for (const auto &r : VALUE_RULES) {
    size_t n = std::strlen(r.prefix);
    if (!starts_with(t, r.prefix))
      continue;
    if (r.kind == ValueKind::VOLT) {
      if (t.size() != n + 4 || t[n + 2] != '.')
        continue;
      std::string num = t.substr(n);
      if (!(num[0] >= '0' && num[0] <= '9' && num[1] >= '0' && num[1] <= '9' && num[3] >= '0' && num[3] <= '9'))
        continue;
      return value_ok(r, strtod(num.c_str(), nullptr));
    }
    if (all_digits_at(t, n, r.digits))
      return value_ok(r, (double) atoi(t.c_str() + n));
  }
  if (starts_with(t, "^S???ACLT") || starts_with(t, "^S???ACCT")) {
    if (t.size() != 14 || t[11] != '-')
      return false;
    for (size_t i : {9, 10, 12, 13})
      if (t[i] < '0' || t[i] > '9')
        return false;
    return atoi(t.substr(9, 2).c_str()) <= 23 && atoi(t.substr(12, 2).c_str()) <= 23;
  }
  if (starts_with(t, "^S???DAT"))
    return all_digits_at(t, 8, 12);
  return false;
}

// Answer to a setting: frame = bytes before the CR. 1 = ACK, 0 = NAK, -1 = anything else.
// PI30 setters answer "(ACK" / "(NAK" + CRC; the "^S???" setters may answer in the PI18 style,
// "^1" (accepted) / "^0" (refused), with or without a CRC (framing.decode_write_answer).
inline int decode_write_answer(const std::string &frame) {
  if (frame.empty())
    return -1;
  if (frame[0] == '^') {
    if (frame.size() < 2 || (frame[1] != '0' && frame[1] != '1'))
      return -1;
    if (frame.size() == 2)
      return frame[1] == '1' ? 1 : 0;
    if (frame.size() == 4) {
      uint16_t crc = crc16_xmodem((const uint8_t *) frame.data(), 2);
      if ((uint8_t) frame[2] == escape_crc_byte((uint8_t) (crc >> 8)) &&
          (uint8_t) frame[3] == escape_crc_byte((uint8_t) (crc & 0xFF)))
        return frame[1] == '1' ? 1 : 0;
    }
    return -1;
  }
  std::string payload;
  if (!decode_pi30(frame, payload))
    return -1;
  if (payload == "ACK")
    return 1;
  if (payload == "NAK")
    return 0;
  return -1;
}

}  // namespace proto
}  // namespace voltronic
}  // namespace esphome
