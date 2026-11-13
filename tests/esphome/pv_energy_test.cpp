// Host test of the PV power / energy lambdas of esphome/packages/pv-string-energy.yaml and the
// 1 s mean block of pv-string-current.yaml. tests/test_esphome_pv_energy.py extracts the two
// `interval: 1s` lambdas from the YAML into energy_lambda.inc / hall_lambda.inc (next to this
// build) and compiles this file with minimal stand-ins for the ESPHome types; the logic under
// test is the real YAML code. Prints ALL OK and exits 0 on success.
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstddef>
#define id(x) x
static uint32_t g_now = 0;
static uint32_t millis() { return g_now; }
namespace sensor { struct Sensor { float state = NAN; int pubs = 0; void publish_state(float v) { state = v; pubs++; } }; }
struct Select { size_t idx = 0; struct O { bool ok; size_t v; size_t value_or(size_t d) const { return ok ? v : d; } };
  O active_index() const { return {true, idx}; } };
struct ESPTime { bool valid = false; int year = 0, month = 0, day_of_month = 0; bool is_valid() const { return valid; } };
struct Clock { ESPTime t; ESPTime now() const { return t; } };

// ---- globals / entities as ESPHome generates them: `id(x).` becomes `x->`, a bare `id(x)` becomes the
// pointer `x`, and a globals component is read as `x->value()` (see esphome/cpp_generator.py).
template <class T> struct G { T v{}; T &value() { return v; } };
#define GLOBAL(type, name) static G<type> name##_g; static G<type> *const name = &name##_g
#define OBJ(type, name) static type name##_o; static type *const name = &name##_o
GLOBAL(double[6], avg_sum); GLOBAL(int[6], avg_n); GLOBAL(uint32_t[2], avg_last);
GLOBAL(float[2], pv_i_now); GLOBAL(uint32_t, pv_i_now_ms);
GLOBAL(double, pe_total); GLOBAL(double, pe_day); GLOBAL(double, pe_month);
GLOBAL(double, pe_last_day); GLOBAL(double, pe_last_month);
GLOBAL(int, pe_day_key); GLOBAL(int, pe_month_key); GLOBAL(uint32_t, pe_ms); GLOBAL(uint32_t, pe_pub_ms);
GLOBAL(bool, pe_force);
GLOBAL(double[2], pw_sum); GLOBAL(int[2], pw_n); GLOBAL(uint32_t[2], pw_last);
OBJ(sensor::Sensor, pv_voltage);
OBJ(sensor::Sensor, pv_power_raw);
OBJ(sensor::Sensor, pv_power);
OBJ(sensor::Sensor, pv_energy_total);
OBJ(sensor::Sensor, pv_energy_today);
OBJ(sensor::Sensor, pv_energy_month);
OBJ(sensor::Sensor, pv_energy_yesterday);
OBJ(sensor::Sensor, pv_energy_last_month);
OBJ(sensor::Sensor, pv_raw_interval);
OBJ(sensor::Sensor, pv_avg_interval);
OBJ(sensor::Sensor, pv_energy_interval);
OBJ(sensor::Sensor, pv_string1_zero_trim);
OBJ(sensor::Sensor, pv_string2_zero_trim);
OBJ(sensor::Sensor, pv_string1_night_trim);
OBJ(sensor::Sensor, pv_string2_night_trim);
OBJ(sensor::Sensor, pv_string1_current_calibration_raw);
OBJ(sensor::Sensor, pv_string2_current_calibration_raw);
OBJ(sensor::Sensor, pv_string1_current_raw);
OBJ(sensor::Sensor, pv_string2_current_raw);
OBJ(sensor::Sensor, pv_string1_current);
OBJ(sensor::Sensor, pv_string2_current);
OBJ(Select, pv_strings_connection); OBJ(Select, pv_zero_source); OBJ(Clock, pv_calib_time);

static void energy_tick() {
#include "energy_lambda.inc"
}
static void hall_tick() {
#include "hall_lambda.inc"
}

static int fails = 0;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); fails++; } } while (0)
#define NEAR(a, b, eps) CHECK(fabs((double)(a) - (double)(b)) <= (eps))

static void second(float i1, float i2, float u) {
  g_now += 1000; pv_i_now->value()[0] = i1; pv_i_now->value()[1] = i2; pv_i_now_ms->value() = g_now; pv_voltage->state = u; energy_tick();
}
static void set_date(int y, int m, int d) { pv_calib_time->t.valid = true; pv_calib_time->t.year = y; pv_calib_time->t.month = m; pv_calib_time->t.day_of_month = d; }

int main() {
  pe_last_day->value() = -1; pe_last_month->value() = -1; pe_force->value() = true;
  pv_raw_interval->state = 1; pv_avg_interval->state = 60; pv_energy_interval->state = 300;
  g_now = 1000;
  // boot without a clock: nothing published for 2 min, counters run
  for (int s = 0; s < 100; s++) second(5, 3, 200);
  CHECK(isnan(pv_energy_total->state));
  NEAR(pe_total->value(), 1600.0 * 99 / 3.6e6, 1e-9);
  NEAR(pv_power_raw->state, 1600, 0.5);
  set_date(2026, 11, 13);
  second(5, 3, 200);               // clock valid: keys set (no last), forced publish
  CHECK(pe_day_key->value() == 20261113 && pe_month_key->value() == 202611);
  CHECK(!isnan(pv_energy_total->state) && isnan(pv_energy_yesterday->state) && isnan(pv_energy_last_month->state));
  // one hour parallel at 1600 W -> +1.6 kWh
  double t0 = pe_total->value();
  for (int s = 0; s < 3600; s++) second(5, 3, 200);
  NEAR(pe_total->value() - t0, 1.6, 1e-6);
  NEAR(pe_day->value(), pe_total->value(), 1e-9);
  // sent every 300 s: lags by at most 5 min of 1.6 kW, the counters themselves are exact
  NEAR(pv_energy_today->state, pe_day->value(), 1600.0 * 300 / 3.6e6 + 0.011);
  { int p0 = pv_energy_total->pubs; for (int s = 0; s < 299; s++) second(5, 3, 200);
    CHECK(pv_energy_total->pubs - p0 <= 1); }
  NEAR(pv_power->state, 1600, 0.5);
  // series: mean (5+3)/2 = 4 A x 200 V = 800 W
  pv_strings_connection->idx = 1;
  t0 = pe_total->value();
  for (int s = 0; s < 3600; s++) second(5, 3, 200);
  NEAR(pe_total->value() - t0, 0.8, 1e-6);
  pv_strings_connection->idx = 0;
  // negative sum -> 0 W, NaN voltage -> nothing counted, power unknown
  t0 = pe_total->value();
  for (int s = 0; s < 120; s++) second(-0.3f, 0.1f, 250);
  NEAR(pe_total->value() - t0, 0, 1e-12);
  for (int s = 0; s < 120; s++) second(5, 3, NAN);
  NEAR(pe_total->value() - t0, 0, 1e-12);
  CHECK(isnan(pv_power_raw->state));
  // stale Hall data (older than 3 s) -> not counted
  t0 = pe_total->value(); g_now += 4000; pv_voltage->state = 200; energy_tick(); g_now += 1000; energy_tick();
  NEAR(pe_total->value() - t0, 0, 1e-12);
  // a gap longer than 5 s adds nothing
  second(5, 3, 200); t0 = pe_total->value(); g_now += 9000; pv_i_now_ms->value() = g_now; energy_tick();
  NEAR(pe_total->value() - t0, 0, 1e-12);
  // day change
  double day_before = pe_day->value(), month_before = pe_month->value();
  set_date(2026, 11, 14);
  second(5, 3, 200);
  NEAR(pe_last_day->value(), day_before, 1e-12);
  NEAR(pv_energy_yesterday->state, day_before, 0.011);
  CHECK(pe_day->value() < 0.001 && pe_month->value() > month_before - 1e-9 && pe_last_month->value() < 0);
  CHECK(pv_energy_today->state < 0.01);
  // month change (also a day change)
  double m_before = pe_month->value();
  set_date(2026, 12, 1);
  second(5, 3, 200);
  NEAR(pe_last_month->value(), m_before, 0.001);
  NEAR(pv_energy_last_month->state, m_before, 0.011);
  CHECK(pe_month->value() < 0.001);
  CHECK(pe_month_key->value() == 202612 && pe_day_key->value() == 20261201);
  // year change
  set_date(2027, 1, 1); second(0, 0, 200);
  CHECK(pe_month_key->value() == 202701 && pe_day_key->value() == 20270101);
  printf("energy: total %.4f day %.4f month %.4f last_day %.4f last_month %.4f\n", pe_total->value(), pe_day->value(), pe_month->value(), pe_last_day->value(), pe_last_month->value());

  // ---- hall lambda: 1 s mean currents with the zero trim
  g_now += 1000; avg_sum->value()[4] = 10; avg_n->value()[4] = 4; avg_sum->value()[5] = 6; avg_n->value()[5] = 3;  // 2.5 A and 2.0 A
  pv_zero_source->idx = 2; pv_string1_zero_trim->state = -0.5f; pv_string2_zero_trim->state = 0.25f;
  hall_tick();
  NEAR(pv_i_now->value()[0], 2.0, 1e-6); NEAR(pv_i_now->value()[1], 2.25, 1e-6); CHECK(pv_i_now_ms->value() == g_now);
  CHECK(avg_n->value()[4] == 0 && avg_n->value()[5] == 0);
  printf(fails ? "FAILED %d\n" : "ALL OK\n", fails);
  return fails ? 1 : 0;
}
