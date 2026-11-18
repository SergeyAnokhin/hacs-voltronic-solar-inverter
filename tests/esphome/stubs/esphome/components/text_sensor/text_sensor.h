#pragma once
#include <string>
namespace esphome { namespace text_sensor {
class TextSensor { public: std::string state; bool has = false; int n = 0; bool has_state() const { return has; }
  void publish_state(const std::string &s) { state = s; has = true; n++; } };
}}
