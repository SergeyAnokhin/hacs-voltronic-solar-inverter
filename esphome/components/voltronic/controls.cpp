#include "controls.h"

#include <cmath>
#include <cstdlib>

#include "esphome/core/log.h"
#include "protocol.h"

namespace esphome {
namespace voltronic {

static const char *const TAG = "voltronic.control";

bool ControlBase::token_(const std::vector<std::string> &t, std::string &out) const {
  if (this->ex_.field < 0 || (size_t) this->ex_.field >= t.size())
    return false;
  std::string s = t[this->ex_.field];
  if (this->ex_.len > 0) {
    if ((size_t) (this->ex_.pos + this->ex_.len) > s.size())
      return false;
    s = s.substr(this->ex_.pos, this->ex_.len);
  }
  out = s;
  return true;
}

// Two read-back tokens are the same when they are equal text or the same number ("050" == "50").
static bool same_token(const std::string &a, const std::string &b) {
  if (a == b)
    return true;
  float x, y;
  return proto::parse_float(a, x) && proto::parse_float(b, y) && x == y;
}

// ---- switch ---------------------------------------------------------------------------------

void VoltronicSwitch::write_state(bool state) {
  const std::string &cmd = state ? this->on_ : this->off_;
  if (this->hub_ == nullptr || !this->hub_->request_write(cmd, this)) {
    if (this->published_)
      this->publish_state(this->state);  // refused: keep showing the real state
    return;
  }
  this->pending_ = state;
}

void VoltronicSwitch::on_write_result(bool ok, const char *why) {
  if (ok) {
    this->publish_state(this->pending_);  // the read-back that follows shows what the inverter really holds
    this->published_ = true;
  } else if (this->published_) {
    this->publish_state(this->state);
  }
}

void VoltronicSwitch::on_answer(const std::vector<std::string> &t, const std::string &payload) {
  bool v;
  if (this->kind_ == KIND_FLAG) {
    int st = proto::qflag_state(payload, this->letters_.empty() ? '?' : this->letters_[0]);
    if (st < 0)
      return;
    v = st == 1;
  } else {
    std::string s;
    if (!this->token_(t, s) || (size_t) this->ex_.pos >= s.size())
      return;
    v = s[this->ex_.pos] == '1';
  }
  if (!this->published_ || this->state != v) {
    this->publish_state(v);
    this->published_ = true;
  }
}

void VoltronicSwitch::dump_config() {
  LOG_SWITCH("", "Voltronic Switch", this);
  ESP_LOGCONFIG(TAG, "  On: %s, off: %s, read back from %s", this->on_.c_str(), this->off_.c_str(), this->cmd_.c_str());
}

// ---- select ---------------------------------------------------------------------------------

void VoltronicSelect::set_read_map(const std::string &map) {
  // map format: "0=Solar first|1=SBU|2=Utility first"
  size_t i = 0;
  while (i < map.size()) {
    size_t bar = map.find('|', i);
    std::string item = map.substr(i, bar == std::string::npos ? std::string::npos : bar - i);
    size_t eq = item.find('=');
    if (eq != std::string::npos)
      this->map_.emplace_back(item.substr(0, eq), item.substr(eq + 1));
    if (bar == std::string::npos)
      break;
    i = bar + 1;
  }
}

void VoltronicSelect::setup() {
  if (!this->assumed_)
    return;
  this->pref_ = this->make_entity_preference<size_t>();
  size_t index = 0;
  if (this->pref_.load(&index) && this->has_index(index))
    this->publish_state(index);
}

void VoltronicSelect::control(size_t index) {
  if (index >= this->cmds_.size() || this->hub_ == nullptr || !this->hub_->request_write(this->cmds_[index], this)) {
    if (this->has_state())
      this->publish_state(this->active_index().value_or(0));
    return;
  }
  this->pending_ = index;
}

void VoltronicSelect::on_write_result(bool ok, const char *why) {
  if (ok) {
    this->publish_state(this->pending_);
    if (this->assumed_)
      this->pref_.save(&this->pending_);
  } else if (this->has_state()) {
    this->publish_state(this->active_index().value_or(0));
  }
}

void VoltronicSelect::on_answer(const std::vector<std::string> &t, const std::string &payload) {
  if (this->assumed_)
    return;
  std::string s;
  if (!this->token_(t, s))
    return;
  for (const auto &kv : this->map_) {
    if (same_token(kv.first, s)) {
      auto idx = this->index_of(kv.second);
      if (idx.has_value() && (!this->has_state() || this->active_index().value_or(SIZE_MAX) != *idx))
        this->publish_state(*idx);
      return;
    }
  }
  ESP_LOGD(TAG, "%s: the inverter reports '%s', which is not an option", this->get_name().c_str(), s.c_str());
}

void VoltronicSelect::dump_config() {
  LOG_SELECT("", "Voltronic Select", this);
  ESP_LOGCONFIG(TAG, "  Read back from %s%s", this->cmd_.c_str(), this->assumed_ ? " (assumed state)" : "");
}

// ---- number ---------------------------------------------------------------------------------

void VoltronicNumber::setup() {
  if (!this->assumed_)
    return;
  this->pref_ = this->make_entity_preference<float>();
  float v;
  if (this->pref_.load(&v) && !std::isnan(v))
    this->publish_state(v);
}

void VoltronicNumber::revert_() {
  if (this->has_state())
    this->publish_state(this->state);
}

void VoltronicNumber::control(float value) {
  std::string text;
  bool ok = false;
  if (this->kind_ == NUM_VALUE) {
    ok = proto::build_value(this->prefix_, (double) value, text);
  } else if (this->kind_ == NUM_MAX_DISCHARGE) {
    ok = std::fabs(value - std::round(value)) < 1e-6 && proto::build_max_discharging((int) std::lround(value), text);
  } else {
    // One hour of a window: the other hour is taken from the last answer of the parameter.
    std::string window;
    if (this->hub_ == nullptr || !this->hub_->last_token(this->cmd_, this->ex_.field, window) ||
        !proto::all_digits_at(window, 0, 4)) {
      ESP_LOGW(TAG, "%s: the current schedule has not been read yet", this->get_name().c_str());
      this->revert_();
      return;
    }
    int hour = (int) std::lround(value);
    int start = this->is_start_ ? hour : atoi(window.substr(0, 2).c_str());
    int end = this->is_start_ ? atoi(window.substr(2, 2).c_str()) : hour;
    ok = std::fabs(value - hour) < 1e-6 && proto::build_schedule(this->ac_output_, start, end, text);
  }
  if (!ok) {
    ESP_LOGW(TAG, "%s: %.2f is not a valid value here (range, step or format)", this->get_name().c_str(), value);
    this->revert_();
    return;
  }
  if (this->hub_ == nullptr || !this->hub_->request_write(text, this)) {
    this->revert_();
    return;
  }
  this->pending_ = value;
}

void VoltronicNumber::on_write_result(bool ok, const char *why) {
  if (ok) {
    this->publish_state(this->pending_);  // the read-back that follows shows what the inverter really holds
    if (this->assumed_)
      this->pref_.save(&this->pending_);
  } else {
    this->revert_();
  }
}

void VoltronicNumber::on_answer(const std::vector<std::string> &t, const std::string &payload) {
  if (this->assumed_)
    return;
  std::string s;
  float f;
  if (!this->token_(t, s) || !proto::parse_float(s, f))
    return;
  if (!this->has_state() || this->state != f)
    this->publish_state(f);
}

void VoltronicNumber::dump_config() {
  LOG_NUMBER("", "Voltronic Number", this);
  ESP_LOGCONFIG(TAG, "  Setting: %s, read back from %s%s", this->prefix_.c_str(), this->cmd_.c_str(),
                this->assumed_ ? " (assumed state)" : "");
}

// ---- button ---------------------------------------------------------------------------------

void VoltronicButton::press_action() {
  if (this->time_ == nullptr || this->hub_ == nullptr)
    return;
  ESPTime now = this->time_->now();
  std::string text;
  if (!now.is_valid() ||
      !proto::build_clock(now.year, now.month, now.day_of_month, now.hour, now.minute, now.second, text)) {
    ESP_LOGW(TAG, "Set clock: the ESP32's own clock is not valid yet");
    return;
  }
  this->hub_->request_write(text, this);
}

void VoltronicButton::on_write_result(bool ok, const char *why) {
  ESP_LOGI(TAG, "Set clock: %s", ok ? "accepted" : why);
}

void VoltronicButton::dump_config() { LOG_BUTTON("", "Voltronic Button", this); }

}  // namespace voltronic
}  // namespace esphome
