#pragma once
#include <cmath>
namespace esphome { namespace sensor {
class Sensor { public: float state = NAN; int n = 0; void publish_state(float v) { state = v; n++; } };
}}
