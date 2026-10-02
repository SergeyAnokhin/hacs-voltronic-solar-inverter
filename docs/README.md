# Documentation Index

Living documentation for the Voltronic/Vevor solar inverter Home Assistant integration. Read [code-map.md](code-map.md) first to locate files, then only the doc for your area. All docs are in English.

| Doc | Read it when |
|---|---|
| [project-overview.md](project-overview.md) | You need goals, owner wishes, decisions, environment, roadmap |
| [code-map.md](code-map.md) | You need to find which file does what |
| [integration.md](integration.md) | You touch the HA integration: layers, coordinators, entities, write commands, adding an entity |
| [inverter-protocol.md](inverter-protocol.md) | You touch commands, CRC, parsing, field mapping |
| [research-summary.md](research-summary.md) | You resume the protocol research: what was tried, what works, blind spots, next tests |
| [settings-map.md](settings-map.md) | You need, per LCD program P01–P64, where to read it and which (owner-tested) command writes it |
| [esphome.md](esphome.md) | You touch the ESPHome configs in `esphome/` (ESP32 + MAX3232 instead of the Elfin gateway): wiring, native vs bridge, controls |
| [inverter-vevor-gd5548jmh.md](inverter-vevor-gd5548jmh.md) | You need device specs, LCD settings meaning, fault/warning codes |
