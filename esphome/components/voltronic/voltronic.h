#pragma once

#include <deque>
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

// A control entity (switch / select / number / button, see controls.h). The hub shows it every
// answer of the command it reads back from, and tells it how a write ended.
class Control {
 public:
  virtual ~Control() {}
  virtual void on_answer(const std::vector<std::string> &tokens, const std::string &payload) = 0;
  // ok = ACK; otherwise `why` is "NAK", "timeout" or "bad answer".
  virtual void on_write_result(bool ok, const char *why) = 0;
  // The command to poll again right after an ACK ("" = none, e.g. values that cannot be read back).
  virtual const std::string &refresh_command() const = 0;
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
  std::vector<Control *> controls;
  std::vector<std::string> last_tokens;  // the last valid answer (schedule numbers need the other hour)
};

struct WriteRequest {
  std::string text;
  Control *who;
};

enum class State : uint8_t { IDLE, WAIT, DRAIN, WRITE };
enum class HState : uint8_t { UNKNOWN, YES, NO };

// Driver: polls the inverter and publishes values. Setting commands go through request_write()
// only, which refuses anything that is not on the built-in allow-list (protocol.h) and does
// nothing at all unless `enable_writes: true` is set in the YAML.
class Voltronic : public Component, public uart::UARTDevice {
 public:
  Voltronic();

  void set_fast_interval(uint32_t ms) { this->fast_interval_ = ms; }
  void set_slow_interval(uint32_t ms) { this->slow_interval_ = ms; }
  void set_enable_writes(bool on) { this->writes_enabled_ = on; }
  bool writes_enabled() const { return this->writes_enabled_; }

  void add_sensor(const std::string &cmd, int field, int pos, int len, sensor::Sensor *s);
  void add_text_sensor(const std::string &cmd, int field, int pos, int len, int join_to, const std::string &map,
                       text_sensor::TextSensor *t);
  void add_binary_sensor(const std::string &cmd, int field, int kind, int pos, const std::string &letters,
                         binary_sensor::BinarySensor *b);
  // Make `cmd` polled and show every answer of it to `c`.
  void add_control(const std::string &cmd, Control *c);

  // Queue one setting (never retried). False = refused (writes disabled, not on the allow-list, queue full).
  bool request_write(const std::string &text, Control *who);
  // Token `field` of the last valid answer of `cmd`; false when there is none yet.
  bool last_token(const std::string &cmd, int field, std::string &out);

  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

 protected:
  CommandState *find_(const std::string &name);
  void mark_due_(const std::string &cmd, uint32_t now);
  void start_next_(uint32_t now);
  void send_(uint32_t now);
  void read_(uint32_t now);
  void on_frame_(uint32_t now);
  void on_failure_(uint32_t now, const char *reason);
  void on_success_(uint32_t now, const std::vector<std::string> &tokens, const std::string &payload);
  void publish_(CommandState &c, const std::vector<std::string> &tokens, const std::string &payload);
  void publish_unavailable_(CommandState &c);
  void drain_rx_();
  void start_write_(uint32_t now);
  void read_write_(uint32_t now);
  void finish_write_(uint32_t now, bool ok, const char *why);

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
  uint16_t stray_{0};      // bytes ignored before an answer's '(' during the current exchange
  uint8_t stray_first_{0};
  bool warned_mode_{false};
  bool writes_enabled_{false};
  std::deque<WriteRequest> writes_;
  WriteRequest cur_write_{"", nullptr};
  uint32_t last_write_ms_{0};
};

}  // namespace voltronic
}  // namespace esphome
