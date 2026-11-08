#include "voltronic.h"

#include <cmath>

#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include "protocol.h"

namespace esphome {
namespace voltronic {

static const char *const TAG = "voltronic";

static const uint32_t REPLY_TIMEOUT_MS = 2000;  // longest observed answer: 0.7 s
static const uint32_t GAP_MS = 100;             // pause between exchanges
static const uint32_t DRAIN_MS = 200;           // discard late bytes after a failure
static const uint32_t PROBE_RETRY_MS = 300000;  // QPRTL silent: ask again after 5 min
static const uint8_t MAX_MISSES = 5;            // then the command's sensors become unavailable
static const size_t MAX_FRAME = 512;

// The only commands this component can send. All are read-only queries. The allow-list
// is the same set the Python integration uses (PI30 'Q...' with CRC; owner-approved 'H...'
// and QPRTL without CRC). Order = tie-break order.
//                        name     plain  group fail_delay
static const CommandState COMMAND_TABLE[] = {
    {"QPRTL", true, 0, PROBE_RETRY_MS},  // H dialect probe
    {"QPI", false, 0, 60000},          {"QMN", false, 0, 60000},   {"QID", false, 0, 60000},
    {"QVFW", false, 0, 60000},         {"HIMSG1", true, 0, 60000},
    {"QPIGS", false, 1, 0},            {"QMOD", false, 1, 0},      {"HGRID", true, 1, 0},
    {"QPIRI", false, 2, 0},            {"QFLAG", false, 2, 0},     {"QPIWS", false, 2, 0},
    {"Q1", false, 2, 0},               {"QBEQI", false, 2, 0},     {"HGEN", true, 2, 0},
    {"HTEMP", true, 2, 0},             {"HEEP1", true, 2, 0},      {"HEEP2", true, 2, 0},
};
static const size_t PROBE_INDEX = 0;

Voltronic::Voltronic() {
  for (const auto &c : COMMAND_TABLE)
    this->cmds_.push_back(c);
}

CommandState *Voltronic::find_(const std::string &name) {
  for (auto &c : this->cmds_)
    if (name == c.name)
      return &c;
  ESP_LOGE(TAG, "Unknown command '%s' (not in the allow-list)", name.c_str());
  return nullptr;
}

void Voltronic::add_sensor(const std::string &cmd, int field, int pos, int len, sensor::Sensor *s) {
  CommandState *c = this->find_(cmd);
  if (c == nullptr)
    return;
  c->wanted = true;
  c->sensors.push_back({{field, pos, len, -1}, s});
}

void Voltronic::add_text_sensor(const std::string &cmd, int field, int pos, int len, int join_to,
                                const std::string &map, text_sensor::TextSensor *t) {
  CommandState *c = this->find_(cmd);
  if (c == nullptr)
    return;
  c->wanted = true;
  TextBinding b{{field, pos, len, join_to}, {}, t};
  // map format: "0=Solar first|1=SBU|2=Utility first"
  size_t i = 0;
  while (i < map.size()) {
    size_t bar = map.find('|', i);
    std::string item = map.substr(i, bar == std::string::npos ? std::string::npos : bar - i);
    size_t eq = item.find('=');
    if (eq != std::string::npos)
      b.map.emplace_back(item.substr(0, eq), item.substr(eq + 1));
    if (bar == std::string::npos)
      break;
    i = bar + 1;
  }
  c->texts.push_back(std::move(b));
}

void Voltronic::add_binary_sensor(const std::string &cmd, int field, int kind, int pos, const std::string &letters,
                                  binary_sensor::BinarySensor *b) {
  CommandState *c = this->find_(cmd);
  if (c == nullptr)
    return;
  c->wanted = true;
  c->binaries.push_back({{field, pos, 0, -1}, kind, letters, b});
}

void Voltronic::setup() {
  bool need_h = false;
  for (size_t i = 0; i < this->cmds_.size(); i++)
    if (this->cmds_[i].wanted && this->cmds_[i].plain && i != PROBE_INDEX)
      need_h = true;
  this->cmds_[PROBE_INDEX].wanted = need_h;
  // Poll order at start: spread the first requests over the first seconds.
  uint32_t now = millis();
  for (auto &c : this->cmds_)
    c.next_due = now + 2000;
  this->gap_until_ = now + 2000;
  this->drain_rx_();
}

void Voltronic::dump_config() {
  ESP_LOGCONFIG(TAG, "Voltronic inverter (read-only):");
  ESP_LOGCONFIG(TAG, "  Fast interval: %u ms, slow interval: %u ms", (unsigned) this->fast_interval_,
                (unsigned) this->slow_interval_);
  for (auto &c : this->cmds_)
    if (c.wanted)
      ESP_LOGCONFIG(TAG, "  Polls %s (%s, %u sensors, %u text, %u binary)", c.name, c.plain ? "no CRC" : "CRC",
                    (unsigned) c.sensors.size(), (unsigned) c.texts.size(), (unsigned) c.binaries.size());
}

void Voltronic::drain_rx_() {
  uint8_t b;
  while (this->available())
    this->read_byte(&b);
}

void Voltronic::loop() {
  uint32_t now = millis();
  switch (this->state_) {
    case State::IDLE:
      if ((int32_t) (now - this->gap_until_) >= 0)
        this->start_next_(now);
      break;
    case State::WAIT:
      this->read_(now);
      break;
    case State::DRAIN:
      this->drain_rx_();
      if ((int32_t) (now - this->drain_until_) >= 0) {
        this->state_ = State::IDLE;
        this->gap_until_ = now + GAP_MS;
      }
      break;
  }
}

void Voltronic::start_next_(uint32_t now) {
  if (this->retry_pending_ && this->cur_ >= 0) {
    this->retry_pending_ = false;
    this->send_(now);
    return;
  }
  int best = -1;
  int32_t best_overdue = -1;
  for (size_t i = 0; i < this->cmds_.size(); i++) {
    CommandState &c = this->cmds_[i];
    if (!c.wanted || !c.enabled)
      continue;
    // H queries wait for the QPRTL probe, and are skipped when the unit has no H dialect.
    if (c.plain && i != PROBE_INDEX && this->h_state_ != HState::YES)
      continue;
    int32_t overdue = (int32_t) (now - c.next_due);
    if (overdue < 0)
      continue;
    if (overdue > best_overdue) {
      best_overdue = overdue;
      best = (int) i;
    }
  }
  if (best < 0)
    return;
  this->cur_ = best;
  this->attempt_ = 0;
  this->send_(now);
}

void Voltronic::send_(uint32_t now) {
  CommandState &c = this->cmds_[this->cur_];
  this->drain_rx_();  // never read a stale answer as this command's answer
  std::string frame = c.plain ? proto::encode_plain(c.name) : proto::encode_pi30(c.name);
  this->write_array((const uint8_t *) frame.data(), frame.size());
  this->flush();
  ESP_LOGV(TAG, "TX %s%s", c.name, this->attempt_ ? " (retry)" : "");
  this->rx_.clear();
  this->sent_at_ = now;
  this->state_ = State::WAIT;
}

void Voltronic::read_(uint32_t now) {
  uint8_t b;
  while (this->available()) {
    this->read_byte(&b);
    char ch = (char) b;
    if (ch == proto::CR) {
      if (this->rx_.empty())
        continue;  // stray CR
      this->on_frame_(now);
      return;
    }
    if (this->rx_.empty() && ch != '(')
      continue;  // wait for the start of an answer
    this->rx_ += ch;
    if (this->rx_.size() > MAX_FRAME) {
      ESP_LOGW(TAG, "Frame too long, dropped");
      this->rx_.clear();
    }
  }
  if ((int32_t) (now - this->sent_at_) > (int32_t) REPLY_TIMEOUT_MS)
    this->on_failure_(now, "timeout");
}

void Voltronic::on_frame_(uint32_t now) {
  CommandState &c = this->cmds_[this->cur_];
  std::string payload;
  bool ok = c.plain ? proto::decode_plain(this->rx_, payload) : proto::decode_pi30(this->rx_, payload);
  if (!ok) {
    ESP_LOGW(TAG, "%s: bad frame or CRC (%u bytes)", c.name, (unsigned) this->rx_.size());
    this->on_failure_(now, "bad frame");
    return;
  }
  ESP_LOGD(TAG, "%s -> %s", c.name, payload.c_str());
  if (payload == "NAK" || payload == "ACK") {
    this->on_failure_(now, "NAK");
    return;
  }
  std::vector<std::string> tokens = proto::split_tokens(payload);
  if (this->cur_ == (int) PROBE_INDEX) {
    // Any "(H..." answer means the CRC-less dialect exists (HPVINV02 on this unit).
    if (payload.size() >= 1 && payload[0] == 'H') {
      this->h_state_ = HState::YES;
      ESP_LOGI(TAG, "H dialect present: %s", payload.c_str());
      this->on_success_(now, tokens, payload);
    } else {
      this->on_failure_(now, "unexpected QPRTL answer");
    }
    return;
  }
  if (!proto::validate(c.name, tokens, payload)) {
    ESP_LOGW(TAG, "%s: answer rejected: %s", c.name, payload.c_str());
    this->on_failure_(now, "rejected");
    return;
  }
  this->on_success_(now, tokens, payload);
}

void Voltronic::on_failure_(uint32_t now, const char *reason) {
  CommandState &c = this->cmds_[this->cur_];
  if (this->attempt_ == 0) {
    // One immediate retry: the first command after an idle period is sometimes lost.
    ESP_LOGD(TAG, "%s: %s, retrying once", c.name, reason);
    this->attempt_ = 1;
    this->retry_pending_ = true;
    this->state_ = State::DRAIN;
    this->drain_until_ = now + DRAIN_MS;
    return;
  }
  uint32_t period = c.group == 0 ? 0 : (c.group == 1 ? this->fast_interval_ : this->slow_interval_);
  c.next_due = now + (c.fail_delay ? c.fail_delay : period);
  if (c.misses < 255)
    c.misses++;
  ESP_LOGW(TAG, "%s failed (%s), %u in a row", c.name, reason, (unsigned) c.misses);
  if (this->cur_ == (int) PROBE_INDEX) {
    this->h_state_ = HState::NO;
    ESP_LOGW(TAG, "No answer to QPRTL: H dialect disabled, asking again in 5 min");
  }
  if (c.misses == MAX_MISSES + 1)
    this->publish_unavailable_(c);
  this->attempt_ = 0;
  this->retry_pending_ = false;
  this->state_ = State::DRAIN;  // a late answer must not reach the next command
  this->drain_until_ = now + DRAIN_MS;
}

void Voltronic::on_success_(uint32_t now, const std::vector<std::string> &tokens, const std::string &payload) {
  CommandState &c = this->cmds_[this->cur_];
  c.misses = 0;
  uint32_t period = c.group == 0 ? 0 : (c.group == 1 ? this->fast_interval_ : this->slow_interval_);
  if (period == 0) {
    c.enabled = false;  // boot-time command: done
  } else {
    c.next_due = now + period;
  }
  this->publish_(c, tokens, payload);
  this->attempt_ = 0;
  this->state_ = State::IDLE;
  this->gap_until_ = now + GAP_MS;
}

static bool extract_string(const std::vector<std::string> &t, const Extract &ex, std::string &out) {
  if (ex.field < 0 || (size_t) ex.field >= t.size())
    return false;
  std::string s = t[ex.field];
  if (ex.join_to > ex.field) {
    if ((size_t) ex.join_to >= t.size())
      return false;
    for (int i = ex.field + 1; i <= ex.join_to; i++)
      s += " " + t[i];
  }
  if (ex.len > 0) {
    if ((size_t) (ex.pos + ex.len) > s.size())
      return false;
    s = s.substr(ex.pos, ex.len);
  }
  out = s;
  return true;
}

void Voltronic::publish_(CommandState &c, const std::vector<std::string> &t, const std::string &payload) {
  for (auto &b : c.sensors) {
    if (b.ex.field == -1) {
      // derived: battery power in W, + = charging (QPIGS: V * (charge A - discharge A))
      float v, ic, id;
      if (proto::parse_float(t[8], v) && proto::parse_float(t[9], ic) && proto::parse_float(t[15], id))
        b.entity->publish_state(roundf(v * (ic - id) * 10.0f) / 10.0f);
      continue;
    }
    std::string s;
    float f;
    if (extract_string(t, b.ex, s) && proto::parse_float(s, f))
      b.entity->publish_state(f);
  }
  for (auto &b : c.texts) {
    std::string s;
    if (!extract_string(t, b.ex, s))
      continue;
    std::string out = s;
    bool found = false;
    for (auto &kv : b.map)
      if (kv.first == s) {
        out = kv.second;
        found = true;
        break;
      }
    if (!found && !b.map.empty() && !this->warned_mode_ && c.name == std::string("QMOD")) {
      ESP_LOGW(TAG, "Unknown QMOD letter '%s'", s.c_str());
      this->warned_mode_ = true;
    }
    if (!b.entity->has_state() || b.entity->state != out)
      b.entity->publish_state(out);
  }
  for (auto &b : c.binaries) {
    std::string s;
    if (b.kind == KIND_FAULTS || b.kind == KIND_WARNINGS) {
      if (!t.empty())
        b.entity->publish_state(proto::qpiws_any(t[0], b.kind == KIND_FAULTS));
      continue;
    }
    if (b.kind == KIND_FLAG) {
      int st = proto::qflag_state(payload, b.letters.empty() ? '?' : b.letters[0]);
      if (st >= 0)
        b.entity->publish_state(st == 1);
      continue;
    }
    if (b.kind == KIND_MODE) {
      if (!t.empty() && t[0].size() == 1)
        b.entity->publish_state(b.letters.find(t[0][0]) != std::string::npos);
      continue;
    }
    if (extract_string(t, b.ex, s) && (size_t) b.ex.pos < s.size())
      b.entity->publish_state(s[b.ex.pos] == '1');
  }
}

void Voltronic::publish_unavailable_(CommandState &c) {
  ESP_LOGW(TAG, "%s: no valid answer %u times, its sensors are now unknown", c.name, (unsigned) MAX_MISSES + 1);
  for (auto &b : c.sensors)
    b.entity->publish_state(NAN);
}

}  // namespace voltronic
}  // namespace esphome
