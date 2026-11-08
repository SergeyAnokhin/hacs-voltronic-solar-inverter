// Host test driver for esphome/components/voltronic/protocol.h.
// Reads one command per line from stdin, prints one result line per command.
// Driven by tests/test_esphome_protocol.py, which compares the output with the Python
// implementation on the recorded frames in tests/fixtures/.
#include <cstdio>
#include <iostream>
#include <sstream>
#include <string>

#include "protocol.h"

using namespace esphome::voltronic::proto;

static std::string to_hex(const std::string &s) {
  static const char *d = "0123456789abcdef";
  std::string out;
  for (unsigned char c : s) {
    out += d[c >> 4];
    out += d[c & 15];
  }
  return out;
}

static std::string from_hex(const std::string &h) {
  std::string out;
  for (size_t i = 0; i + 1 < h.size(); i += 2)
    out += (char) strtol(h.substr(i, 2).c_str(), nullptr, 16);
  return out;
}

int main() {
  std::string line;
  while (std::getline(std::cin, line)) {
    std::istringstream in(line);
    std::string op;
    in >> op;
    if (op == "ENC") {  // ENC <cmd> -> hex of the PI30 request
      std::string cmd;
      in >> cmd;
      std::cout << to_hex(encode_pi30(cmd)) << "\n";
    } else if (op == "FRAME") {  // FRAME <cmd> <plain 0|1> <hex of the received bytes incl. CR>
      std::string cmd, hex;
      int plain;
      in >> cmd >> plain >> hex;
      std::string raw = from_hex(hex);
      if (!raw.empty() && raw.back() == CR)
        raw.pop_back();
      std::string payload;
      bool ok = plain ? decode_plain(raw, payload) : decode_pi30(raw, payload);
      if (!ok) {
        std::cout << "BAD\n";
        continue;
      }
      bool valid = validate(cmd, split_tokens(payload), payload);
      std::cout << (valid ? "VALID " : "INVALID ") << payload << "\n";
    } else if (op == "CLASSES") {
      std::cout << QPIWS_CLASSES << "\n";
    } else if (op == "WS") {  // WS <bits> -> any fault, any warning
      std::string bits;
      in >> bits;
      std::cout << qpiws_any(bits, true) << " " << qpiws_any(bits, false) << "\n";
    } else if (op == "FLAG") {  // FLAG <payload> <letter> -> 1 / 0 / -1
      std::string payload, letter;
      in >> payload >> letter;
      std::cout << qflag_state(payload, letter[0]) << "\n";
    } else if (op == "NUM") {  // NUM <token> -> parsed float or NAN
      std::string tok;
      in >> tok;
      float f;
      if (parse_float(tok, f))
        std::cout << f << "\n";
      else
        std::cout << "NAN\n";
    }
  }
  return 0;
}
