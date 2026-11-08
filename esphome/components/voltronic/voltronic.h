#pragma once

#include <string>
#include <utility>
#include <vector>

#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "esphome/components/uart/uart.h"
#include "esphome/core/component.h"

namespace esphome {
namespace voltronic {

// Where a value sits in an answer: token `field`; optionally tokens field..join_to joined
// by a space; optionally the sub-string [pos, pos+len) of it. field -1 = derived value.
struct Extract {
  int field;
  int pos;
  int len;
  int join_to;
};

enum BinaryKind : int {
  KIND_BIT = 0,       // char `pos` of the token is '1'
  KIND_FLAG = 1,      // QFLAG letter enabled
  KIND_MODE = 2,      // QMOD letter is one of `letters`
  KIND_FAULTS = 3,    // any QPIWS fault bit
  KIND_WARNINGS = 4,  // any QPIWS warning bit
};

struct SensorBinding {
  Extract ex;
  sensor::Sensor *entity;
};
struct TextBinding {
  Extract ex;
  std::vector<std::pair<std::string, std::string>> map;
  text_sensor::TextSensor *entity;
};
struct BinaryBinding {
  Extract ex;
  int kind;
  std::string letters;
  binary_sensor::BinarySensor *entity;
};

// group: 0 = once at boot, 1 = fast, 2 = slow
struct CommandState {
  const char *name;
  bool plain;           // H dialect: no CRC
  uint8_t group;
  uint32_t fail_delay;  // ms until the next try after a failed exchange
  bool wanted{false};
  bool enabled{true};
  uint32_t next_due{0};
  uint8_t misses{0};
  std::vector<SensorBinding> sensors;
  std::vector<TextBinding> texts;
  std::vector<BinaryBinding> binaries;
};

enum class State : uint8_t { IDLE, WAIT, DRAIN };
enum class HState : uint8_t { UNKNOWN, YES, NO };

// Read-only driver: polls the inverter and publishes values. It sends nothing but the
// built-in queries below (no setting commands exist in this component yet).
class Voltronic : public Component, public uart::UARTDevice {
 public:
  Voltronic();

  void set_fast_interval(uint32_t ms) { this->fast_interval_ = ms; }
  void set_slow_interval(uint32_t ms) { this->slow_interval_ = ms; }

  void add_sensor(const std::string &cmd, int field, int pos, int len, sensor::Sensor *s);
  void add_text_sensor(const std::string &cmd, int field, int pos, int len, int join_to, const std::string &map,
                       text_sensor::TextSensor *t);
  void add_binary_sensor(const std::string &cmd, int field, int kind, int pos, const std::string &letters,
                         binary_sensor::BinarySensor *b);

  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

 protected:
  CommandState *find_(const std::string &name);
  void start_next_(uint32_t now);
  void send_(uint32_t now);
  void read_(uint32_t now);
  void on_frame_(uint32_t now);
  void on_failure_(uint32_t now, const char *reason);
  void on_success_(uint32_t now, const std::vector<std::string> &tokens, const std::string &payload);
  void publish_(CommandState &c, const std::vector<std::string> &tokens, const std::string &payload);
  void publish_unavailable_(CommandState &c);
  void drain_rx_();

  std::vector<CommandState> cmds_;
  int cur_{-1};
  uint8_t attempt_{0};
  bool retry_pending_{false};
  State state_{State::IDLE};
  HState h_state_{HState::UNKNOWN};
  uint32_t sent_at_{0};
  uint32_t gap_until_{0};
  uint32_t drain_until_{0};
  uint32_t fast_interval_{10000};
  uint32_t slow_interval_{60000};
  std::string rx_;
  bool warned_mode_{false};
};

}  // namespace voltronic
}  // namespace esphome
