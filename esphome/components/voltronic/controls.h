#pragma once

// Control entities of the voltronic component: switch, select, number and the "set clock" button.
// Every one of them only asks the hub (Voltronic::request_write) to send a setting; the hub checks
// the built-in allow-list (protocol.h) and `enable_writes`. The new value is shown from the
// read-back of the parameter after the inverter ACKed it (values that cannot be read back are
// "assumed": they show the last ACKed value and are restored after a reboot).

#include <string>
#include <utility>
#include <vector>

#include "esphome/components/button/button.h"
#include "esphome/components/number/number.h"
#include "esphome/components/select/select.h"
#include "esphome/components/switch/switch.h"
#include "esphome/components/time/real_time_clock.h"
#include "esphome/core/component.h"
#include "esphome/core/preferences.h"
#include "voltronic.h"

namespace esphome {
namespace voltronic {

// Shared part: the hub, and where the value is read back from.
class ControlBase : public Control {
 public:
  void set_parent(Voltronic *hub) { this->hub_ = hub; }
  // Read back from token `field` (optionally the sub-string [pos, pos+len)) of the answer to `cmd`.
  void set_readback(const std::string &cmd, int field, int pos, int len) {
    this->cmd_ = cmd;
    this->ex_ = {field, pos, len, -1};
  }
  const std::string &refresh_command() const override { return this->cmd_; }

 protected:
  bool token_(const std::vector<std::string> &t, std::string &out) const;
  Voltronic *hub_{nullptr};
  std::string cmd_;
  Extract ex_{-1, 0, 0, -1};
};

class VoltronicSwitch : public switch_::Switch, public Component, public ControlBase {
 public:
  void set_commands(const std::string &on, const std::string &off) {
    this->on_ = on;
    this->off_ = off;
  }
  // kind: KIND_BIT (char `pos` of the token is '1') or KIND_FLAG (QFLAG letter).
  void set_readback_kind(int kind, const std::string &letters) {
    this->kind_ = kind;
    this->letters_ = letters;
  }
  void on_answer(const std::vector<std::string> &t, const std::string &payload) override;
  void on_write_result(bool ok, const char *why) override;
  void dump_config() override;

 protected:
  void write_state(bool state) override;
  std::string on_, off_, letters_;
  int kind_{KIND_BIT};
  bool pending_{false};
  bool published_{false};
};

class VoltronicSelect : public select::Select, public Component, public ControlBase {
 public:
  // Setting text for each option (same order as the options).
  void set_commands(const std::vector<std::string> &cmds) { this->cmds_ = cmds; }
  // "0=Solar first|1=SBU": token of the read-back -> option.
  void set_read_map(const std::string &map);
  // Cannot be read back: show the last ACKed option, restore it after a reboot.
  void set_assumed(bool assumed) { this->assumed_ = assumed; }
  void setup() override;
  void on_answer(const std::vector<std::string> &t, const std::string &payload) override;
  void on_write_result(bool ok, const char *why) override;
  void dump_config() override;

 protected:
  void control(size_t index) override;
  std::vector<std::string> cmds_;
  std::vector<std::pair<std::string, std::string>> map_;
  bool assumed_{false};
  size_t pending_{0};
  ESPPreferenceObject pref_;
};

enum NumberKind : int {
  NUM_VALUE = 0,       // prefix + value, see proto::VALUE_RULES
  NUM_MAX_DISCHARGE = 1,
  NUM_SCHEDULE = 2,    // one hour of an AC output / AC charger window
};

class VoltronicNumber : public number::Number, public Component, public ControlBase {
 public:
  void set_value_prefix(const std::string &prefix) {
    this->kind_ = NUM_VALUE;
    this->prefix_ = prefix;
  }
  void set_max_discharge() { this->kind_ = NUM_MAX_DISCHARGE; }
  // A schedule hour: the read-back token (field of `set_readback`) is the whole window "HHhh".
  void set_schedule(bool ac_output, bool is_start) {
    this->kind_ = NUM_SCHEDULE;
    this->ac_output_ = ac_output;
    this->is_start_ = is_start;
  }
  void set_assumed(bool assumed) { this->assumed_ = assumed; }
  void setup() override;
  void on_answer(const std::vector<std::string> &t, const std::string &payload) override;
  void on_write_result(bool ok, const char *why) override;
  void dump_config() override;

 protected:
  void control(float value) override;
  void revert_();
  int kind_{NUM_VALUE};
  std::string prefix_;
  bool ac_output_{false};
  bool is_start_{false};
  bool assumed_{false};
  float pending_{NAN};
  ESPPreferenceObject pref_;
};

// Sets the inverter clock to the ESP's local time (needs a `time:` component).
class VoltronicButton : public button::Button, public Component, public ControlBase {
 public:
  void set_time(time::RealTimeClock *t) { this->time_ = t; }
  void on_answer(const std::vector<std::string> &, const std::string &) override {}
  void on_write_result(bool ok, const char *why) override;
  void dump_config() override;

 protected:
  void press_action() override;
  time::RealTimeClock *time_{nullptr};
};

}  // namespace voltronic
}  // namespace esphome
