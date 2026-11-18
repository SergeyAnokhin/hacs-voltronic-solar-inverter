#pragma once
#include <cstddef>
#include <cstdint>
#include <deque>
#include <functional>
extern std::deque<uint8_t> g_rx;
extern std::function<void(const uint8_t *, size_t)> g_on_tx;
namespace esphome { namespace uart {
class UARTDevice {
 public:
  int available() { return (int) g_rx.size(); }
  bool read_byte(uint8_t *b) { if (g_rx.empty()) return false; *b = g_rx.front(); g_rx.pop_front(); return true; }
  void write_array(const uint8_t *d, size_t n) { g_on_tx(d, n); }
  void flush() {}
};
}}  // namespace esphome::uart
