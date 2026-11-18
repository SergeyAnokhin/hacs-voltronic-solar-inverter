#pragma once
namespace esphome { namespace binary_sensor {
class BinarySensor { public: bool state = false; int n = 0; void publish_state(bool v) { state = v; n++; } };
}}
