# Voltronic Solar Inverter for Home Assistant (HACS)

A custom Home Assistant integration that reads live data, ratings, settings, warnings and option flags from Voltronic-compatible (PI30 protocol) hybrid solar inverters — developed and tested on the **Vevor GD5548JMH** (reports as `VMII-4000`, 24 V / 4000 W, firmware `00040.09`). The inverter's RS232 port is reached through an RS232-to-TCP gateway (e.g. Elfin EW10/EE10). By default the integration is **read-only**; optional control entities that change settings can be enabled in the options and are off by default.

> **Status: 0.2.0, early.** Reading is tested against responses recorded from the real inverter. The setting commands are implemented but **not yet verified on the device**.

## Requirements

- Home Assistant 2025.8 or newer, [HACS](https://hacs.xyz/)
- An RS232-to-TCP gateway connected to the inverter's RS232 port (2400 baud, 8N1), in transparent TCP server mode (Elfin default port `8899`)
- The gateway serves **one client at a time**: stop other tools (the prototype script, the vendor app) while the integration runs

No gateway? An ESP32 with a MAX3232 level shifter can replace it: [`esphome/vevor-bridge.yaml`](esphome/vevor-bridge.yaml) makes it a TCP bridge on port 8899 for this integration, and [`esphome/vevor-inverter.yaml`](esphome/vevor-inverter.yaml) is a standalone ESPHome firmware (PI30 only, optional setting controls). Wiring and limits: [docs/esphome.md](docs/esphome.md).

## Installation

**HACS (custom repository)**

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/SergeyAnokhin/hacs-voltronic-solar-inverter`, type *Integration*.
2. Search for **Voltronic Solar Inverter**, download it and restart Home Assistant.

> ⚠ Until the Home Assistant example integrations are moved out of `custom_components/` in this repository, HACS picks the wrong folder (it installs the first directory it finds). Use the manual installation for now.

**Manual**

Copy `custom_components/voltronic_solar_inverter/` into `<config>/custom_components/` and restart Home Assistant.

## Configuration

*Settings → Devices & services → Add integration → Voltronic Solar Inverter*.

| Field | Default | Meaning |
|---|---|---|
| Host | — | Gateway IP / host name, e.g. `192.168.1.47` |
| Port | `8899` | Gateway TCP port |
| Live values interval | 10 s (5–300) | `QPIGS` + `QMOD` |
| Settings and warnings interval | 60 s (30–3600) | `QPIRI` + `QFLAG` + `QPIWS` |

Setup reads the protocol, model and serial number (`QPI`, `QMN`, `QID`); the serial is the unique id. *Configure* (options) changes the intervals and the **Enable control entities** switch (default off).

## Entities

One device (model, serial number, firmware) with:

- **Sensors:** grid voltage / frequency, grid power (signed W), AC output voltage / frequency, output apparent power (VA) and power (W), load %, battery voltage, charge current, discharge current, battery power (signed, + = charging), heat-sink, inverter, transformer and PV temperatures, PV voltage / current / charging power, **PV energy today / this month / this year / total (kWh, from the inverter's own counters)**, mode (power on, standby = output off, line, battery, fault, power saving), charge stage (idle, bulk, absorption, float), **AC output on / off time (programs 48/49)** and **AC charger start / stop time (programs 46/47)**.
- **Diagnostic sensors:** current settings and ratings (output source priority, charger source priority, solar supply priority (program 43), battery type, AC input range, back-to-utility / back-to-battery / cut-off / bulk / float voltages, battery low-alarm voltage, max charging currents, equalization settings, rated output values), inverter clock and its offset from Home Assistant's time, fan speeds, serial number, firmware. Disabled by default: bus voltage, solar-charger battery voltage, battery level estimate, grid ratings, machine type, topology, output mode, second-output (dual output) thresholds, BMS SOC thresholds, grid-tie current, firmware date.
- **Binary sensors:** equalization enabled / active, AC output, load on, charging, solar charging, grid charging, SBU priority, fault, warning (with the active items as attributes); one diagnostic problem sensor per warning/fault bit (grid lost, battery low, overload, over-temperature, … — five on by default); the option flags (buzzer, overload bypass, power saving, backlight, …).
- **Control entities (only when enabled in the options):** switches for the 9 option flags, selects for output / charger source priority (only owner-verified values: *SBU*, *Only solar*) and solar supply priority (program 43: battery first / load first), numbers for max charging current and max utility charging current (values the inverter reports as allowed) and, on 24 V systems, back-to-utility / back-to-battery / cut-off / bulk voltages. A rejected command (`NAK`) raises an error; after `ACK` the settings are re-read. **Use at your own risk** — see [docs/integration.md](docs/integration.md#control-entities-only-with-enable-control-entities).

Full list with protocol sources: [docs/integration.md](docs/integration.md).

## Energy (kWh)

- **PV production:** use *PV energy total* (`total_increasing`, kWh) directly in *Settings → Dashboards → Energy → Solar production*. It is the inverter's own counter (same value as the vendor app), read with the CRC-less H protocol of units that support it.
- **Load (output) energy:** the inverter has no load counter. Create one: *Settings → Devices & services → Helpers → Create helper → Integral sensor* (Riemann sum), input `sensor.<device>_ac_output_power`, method *Left*, metric prefix *k*, time unit *hours*; optionally add a *Utility meter* for daily/monthly totals. Its accuracy depends on the live values interval.
- Inverters without the H protocol get no PV energy sensors; integrate `…_pv_charging_power` the same way.

## Known limitations (Vevor GD5548JMH, firmware 00040.09)

- The PV energy counters, inverter clock, schedules (programs 46–49), program 43, extra temperatures and grid power come from the vendor Wi-Fi dongle's CRC-less "H" protocol (`QPRTL`, `HGEN`, `HEEP1`/`HEEP2`, `HTEMP`, `HGRID`); the integration detects it at start-up and skips these entities on inverters without it. Load-energy counters and BMS data are not available at all. **The schedules are read-only:** no command to change programs 46–49 is known, and there is no command to switch the output on/off.
- The schedules run on the inverter's own clock, which can drift (about 10 minutes slow on the test unit); see the *Inverter clock offset* sensor.
- The battery level % is the inverter's voltage-based estimate, not a state of charge (meaningless for LiFePO4); it is disabled by default.
- On this firmware output/charger priority codes follow the LCD menu position, not the generic Voltronic numbering; unconfirmed codes are shown as such and cannot be selected.
- PV values are not yet verified with the array producing.

## Development

```bash
pip install -r requirements_test.txt
```

```bash
pytest
```

The protocol tests (`tests/test_framing.py`, `test_parsers.py`, `test_h_parsers.py`, `test_commands.py`, `test_client.py`) need only `pytest` and use responses recorded from the real inverter in `tests/fixtures/`. `tests/test_ha_integration.py` needs `pytest-homeassistant-custom-component` and is skipped without it; it runs as is on Linux/WSL (on Windows see [docs/integration.md](docs/integration.md#tests)). No test talks to a real inverter.

Other tools: [`python_scripts/get_inverter_info.py`](python_scripts/get_inverter_info.py) (original prototype, prints JSON) and [`tools/probe_inverter.py`](tools/probe_inverter.py) (read-only probe that refuses non-`Q` commands: `python tools/probe_inverter.py --mode both`).

## Documentation

| Doc | Content |
|---|---|
| [docs/README.md](docs/README.md) | Index of all docs |
| [docs/integration.md](docs/integration.md) | Architecture, entities, write commands, how to add an entity |
| [docs/project-overview.md](docs/project-overview.md) | Goals, decisions, roadmap |
| [docs/code-map.md](docs/code-map.md) | File map |
| [docs/inverter-protocol.md](docs/inverter-protocol.md) | Serial protocol and field mapping |
| [docs/research-summary.md](docs/research-summary.md) | Protocol research: what was tried, what works, open questions, next tests |
| [docs/settings-map.md](docs/settings-map.md) | LCD programs P01–P64: read source and write command for each |
| [docs/esphome.md](docs/esphome.md) | ESP32 + MAX3232 with ESPHome: wiring, native firmware, TCP bridge |
| [docs/inverter-vevor-gd5548jmh.md](docs/inverter-vevor-gd5548jmh.md) | Device reference (specs, settings, fault codes) |

`custom_components/` also contains the official Home Assistant example integrations, used only as reference patterns.

## License

See [LICENSE](LICENSE).
