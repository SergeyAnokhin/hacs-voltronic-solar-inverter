// Host test of the setting (write) path of the driver esphome/components/voltronic/voltronic.cpp,
// built against stand-ins for the ESPHome base classes (tests/esphome/stubs) and a fake inverter.
// Driven by tests/test_esphome_driver_writes.py. Nothing here touches a real unit.
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <functional>
#include <map>
#include <string>
#include <vector>

#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/text_sensor/text_sensor.h"

uint32_t g_millis = 0;
std::deque<uint8_t> g_rx;
std::function<void(const uint8_t *, size_t)> g_on_tx;

#include "protocol.h"
#include "voltronic.h"

using namespace esphome;
using namespace esphome::voltronic;

static int fails = 0;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); fails++; } } while (0)

struct Sent {
  uint32_t at;
  std::string text;  // the ASCII part of the frame (without CRC and CR)
};
static std::vector<Sent> g_sent;
static std::map<std::string, std::string> g_script;  // setting / query text -> bytes to answer (raw)

static std::string pi30_answer(const std::string &payload) {
  std::string body = "(" + payload;
  uint16_t crc = proto::crc16_xmodem((const uint8_t *) body.data(), body.size());
  body += (char) proto::escape_crc_byte((uint8_t) (crc >> 8));
  body += (char) proto::escape_crc_byte((uint8_t) (crc & 0xFF));
  return body + "\r";
}

static std::string request_text(const uint8_t *d, size_t n) {
  std::string raw((const char *) d, n);
  while (!raw.empty() && raw.back() == '\r')
    raw.pop_back();
  // PI30 frames carry two CRC bytes; settings and queries are printable ASCII, so find the text by
  // trying every cut that matches a re-encoding of itself
  for (size_t len = raw.size(); len > 0; len--) {
    std::string cand = raw.substr(0, len);
    std::string enc = proto::encode_pi30(cand);
    if (enc.size() == n && enc.compare(0, n, (const char *) d, n) == 0)
      return cand;
  }
  return raw;
}

class FakeControl : public Control {
 public:
  std::string refresh;
  int results = 0;
  bool last_ok = false;
  std::string last_why;
  int answers = 0;
  void on_answer(const std::vector<std::string> &, const std::string &) override { answers++; }
  void on_write_result(bool ok, const char *why) override {
    results++;
    last_ok = ok;
    last_why = why;
  }
  const std::string &refresh_command() const override { return refresh; }
};

static Voltronic *g_hub;

static void run(uint32_t ms) {
  for (uint32_t t = 0; t < ms; t += 5) {
    g_millis += 5;
    g_hub->loop();
  }
}

static int count_sent(const std::string &text) {
  int n = 0;
  for (auto &s : g_sent)
    if (s.text == text)
      n++;
  return n;
}

int main() {
  g_on_tx = [&](const uint8_t *d, size_t n) {
    std::string text = request_text(d, n);
    g_sent.push_back({g_millis, text});
    auto it = g_script.find(text);
    if (it != g_script.end())
      for (char c : it->second)
        g_rx.push_back((uint8_t) c);
  };

  static Voltronic hub;
  g_hub = &hub;
  FakeControl ctl;
  hub.setup();
  g_millis = 1000;
  run(3000);

  // 1. writes are off by default: refused, nothing is sent
  CHECK(!hub.request_write("PEa", &ctl));
  run(3000);
  CHECK(g_sent.empty());

  hub.set_enable_writes(true);

  // 2. things that are not on the allow-list are refused even with writes enabled
  for (const char *bad : {"PF", "PBT00", "PBFT27.0", "PGR00", "POP02", "PBATCD011", "QPIGS", "F50", "PEd", ""})
    CHECK(!hub.request_write(bad, &ctl));
  run(3000);
  CHECK(g_sent.empty());

  // 3. ACK: the frame is the PI30 frame with CRC, the control hears ACK, the read-back is polled soon
  FakeControl flag;
  flag.refresh = "QFLAG";
  hub.add_control("QFLAG", &flag);  // makes QFLAG polled; the first poll is due at start-up
  g_script["PEa"] = pi30_answer("ACK");
  g_script["QFLAG"] = pi30_answer("EabjkuvxyzDl");  // a valid QFLAG answer
  run(2500);  // the first (start-up) poll of QFLAG happens now
  int qflag_before = count_sent("QFLAG");
  CHECK(qflag_before >= 1 && flag.answers >= 1);
  CHECK(hub.request_write("PEa", &flag));
  run(1500);
  CHECK(count_sent("PEa") == 1);
  CHECK(flag.results == 1 && flag.last_ok);
  CHECK(count_sent("QFLAG") > qflag_before);  // read back right after the ACK, not at the 60 s interval

  // 4. NAK: reported, no read-back requested because of it
  g_script["PDa"] = pi30_answer("NAK");
  CHECK(hub.request_write("PDa", &flag));
  run(2500);
  CHECK(count_sent("PDa") == 1);
  CHECK(flag.results == 2 && !flag.last_ok && flag.last_why == "NAK");

  // 5. no answer: times out after 2 s and is NOT sent a second time
  g_script.erase("POP01");
  CHECK(hub.request_write("POP01", &flag));
  run(9000);
  CHECK(count_sent("POP01") == 1);
  CHECK(flag.results == 3 && !flag.last_ok && flag.last_why == "timeout");

  // 6. PI18-style answer of the service-tool setters
  g_script["^S???ACLT07-22"] = std::string("^1\r");
  CHECK(hub.request_write("^S???ACLT07-22", &flag));
  run(2500);
  CHECK(count_sent("^S???ACLT07-22") == 1);
  CHECK(flag.results == 4 && flag.last_ok);

  // 7. garbage instead of an answer: not an ACK
  g_script["PCP01"] = pi30_answer("XYZ");
  CHECK(hub.request_write("PCP01", &flag));
  run(2500);
  CHECK(flag.results == 5 && !flag.last_ok && flag.last_why == "bad answer");

  // 8. a queued setting waits at least 2 s after the previous one; duplicates are dropped
  g_sent.clear();
  g_script["PCP00"] = pi30_answer("ACK");
  g_script["POP00"] = pi30_answer("ACK");
  CHECK(hub.request_write("PCP00", &flag));
  CHECK(hub.request_write("POP00", &flag));
  CHECK(hub.request_write("POP00", &flag));  // already queued: accepted, sent once
  run(6000);
  CHECK(count_sent("PCP00") == 1 && count_sent("POP00") == 1);
  uint32_t t1 = 0, t2 = 0;
  for (auto &s : g_sent) {
    if (s.text == "PCP00") t1 = s.at;
    if (s.text == "POP00") t2 = s.at;
  }
  CHECK(t2 >= t1 + 2000);

  // 9. the queue is bounded
  g_script.clear();
  int accepted = 0;
  for (int hour = 0; hour < 12; hour++) {
    char buf[32];
    snprintf(buf, sizeof(buf), "^S???ACLT%02d-%02d", hour, hour + 1);
    if (hub.request_write(buf, &flag))
      accepted++;
  }
  CHECK(accepted == 8);

  printf(fails ? "FAILED %d\n" : "ALL OK\n", fails);
  return fails ? 1 : 0;
}
