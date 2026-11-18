#pragma once
namespace esphome {
namespace setup_priority { const float DATA = 600.0f; }
class Component {
 public:
  virtual ~Component() {}
  virtual void setup() {}
  virtual void loop() {}
  virtual void dump_config() {}
  virtual float get_setup_priority() const { return 0.0f; }
};
}  // namespace esphome
