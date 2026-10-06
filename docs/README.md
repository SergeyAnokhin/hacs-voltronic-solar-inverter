# Documentation Index

Living documentation for the Voltronic/Vevor solar inverter Home Assistant integration. Read [code-map.md](code-map.md) first to locate files, then only the doc for your area. All docs are in English.

| Doc | Read it when |
|---|---|
| [project-overview.md](project-overview.md) | You need goals, owner wishes, decisions, environment, roadmap |
| [code-map.md](code-map.md) | You need to find which file does what |
| [integration.md](integration.md) | You touch the HA integration: layers, coordinators, entities, write commands, adding an entity |
| [sensors.md](sensors.md) | You need what each sensor shows and how every derived one (battery power, power balance, daily energy / max, medians, clock offset) is computed |
| [inverter-protocol.md](inverter-protocol.md) | You touch commands, CRC, parsing, field mapping |
| [research-summary.md](research-summary.md) | You resume the protocol research: what was tried, what works, blind spots, next tests |
| [settings-map.md](settings-map.md) | You need, per LCD program P01–P64, where to read it and which (owner-tested) command writes it |
| [local-data.md](local-data.md) | You analyse the owner's real HA history: what to copy into `local_data/`, how to export entities with `tools/ha_history.py` |
| [esphome-hardware.md](esphome-hardware.md) | You build or debug the ESP32 + MAX3232 hardware: parts, wiring diagrams, RJ45 pin finding, troubleshooting |
| [esphome.md](esphome.md) | You touch the ESPHome configs in `esphome/` (ESP32 + MAX3232 instead of the Elfin gateway): wiring, native vs bridge, controls |
| [inverter-vevor-gd5548jmh.md](inverter-vevor-gd5548jmh.md) | You need device specs, LCD settings meaning, fault/warning codes |
