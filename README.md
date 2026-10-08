<img width="529" height="257" alt="logo" src="https://github.com/user-attachments/assets/a0a62a12-628b-46b5-ac83-cf6498b8cf57" />

# Voltronic/Vevor Solar Inverter for Home Assistant (HACS)

<img width="225" height="300" alt="image" src="https://github.com/user-attachments/assets/ea0d73d1-ee7d-422f-8414-9d203093059d" />

> [!CAUTION]
> **Changing inverter settings from Home Assistant is entirely at your own risk.** The switches, selects and numbers of this integration send setting commands straight to the inverter. A wrong value can change how the battery is charged or cut off, where the load is powered from, or what the inverter does on overload or over-temperature. There is no undo and no warranty; check every change on the inverter's display.
>
> **Tested on one unit only:** VEVOR GD5548JMH hybrid inverter, reporting model `VMII-4000`, protocol `PI30`, main firmware `00040.09` (firmware date 2026-01-19), 24 V / 4000 W, single MPPT, LiFePO4 battery bank set as *User-defined* without BMS, connected through an Elfin RS232-to-TCP gateway. On this unit **reading** every value was verified. The **setting commands** follow the Voltronic protocol and a sibling unit (`VMII-6200`), but they have not all been confirmed on this unit yet (status per command: [docs/integration.md](docs/integration.md#control-entities)). On other models or firmware even the readings may differ.

A custom Home Assistant integration that reads live data, ratings, settings, warnings and option flags from Voltronic-compatible (PI30 protocol) hybrid solar inverters — developed and tested on the **Vevor GD5548JMH** (reports as `VMII-4000`, 24 V / 4000 W, firmware `00040.09`). The inverter's RS232 port is reached through an RS232-to-TCP gateway (e.g. Elfin EW10/EE10). It also creates switches, selects and numbers that change inverter settings (see the warning above).

> **Status: 0.4.0, early.** Reading is tested against responses recorded from the real inverter. The setting commands are implemented but **not yet verified on the device**.


<img width="420" height="707" alt="image" src="https://github.com/user-attachments/assets/0e64709b-1383-4302-8780-63c4cb44ec2b" />
<img width="430" height="421" alt="image" src="https://github.com/user-attachments/assets/7ba76456-02a6-4957-8fcc-53ff0c48d17b" />


## Requirements

- Home Assistant 2025.8 or newer, [HACS](https://hacs.xyz/)
- An RS232-to-TCP gateway connected to the inverter's RS232 port (2400 baud, 8N1), in transparent TCP server mode (Elfin default port `8899`)
- The gateway serves **one client at a time**: stop other tools (the prototype script, the vendor app) while the integration runs

No gateway? An ESP32 with a MAX3232 level shifter can replace it: [`esphome/vevor-bridge.yaml`](esphome/vevor-bridge.yaml) makes it a TCP bridge on port 8899 for this integration, and [`esphome/vevor-inverter.yaml`](esphome/vevor-inverter.yaml) is a standalone ESPHome firmware (PI30 only, optional setting controls). Build guide with wiring diagrams: [docs/esphome-hardware.md](docs/esphome-hardware.md); firmware details: [docs/esphome.md](docs/esphome.md).

## Installation

**HACS (custom repository)**

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/SergeyAnokhin/hacs-voltronic-solar-inverter`, type *Integration*.
2. Search for **Voltronic Solar Inverter**, download it and restart Home Assistant.


**Manual**

Copy `custom_components/voltronic_solar_inverter/` into `<config>/custom_components/` and restart Home Assistant.

## Configuration

*Settings → Devices & services → Add integration → Voltronic Solar Inverter*.

| Field | Default | Meaning |
|---|---|---|
| Host | — | Gateway IP / host name, e.g. `192.168.1.47` |
| Port | `8899` | Gateway TCP port |
| Live values interval | 10 s (2–300) | `QPIGS` + `QMOD` (+ `HGRID`); one cycle takes ~1.5 s |
| Settings and warnings interval | 60 s (30–3600) | `QPIRI` + `QFLAG` + `QPIWS` |
| Battery power sensor (options only, optional) | — | An external battery meter (e.g. your BMS), W or kW, **positive while charging**. *PV power full* then uses it instead of the inverter's battery currents |

Setup reads the protocol, model and serial number (`QPI`, `QMN`, `QID`); the serial is the unique id. *Configure* (options) changes the two intervals and the battery power sensor.

**Derived values explain themselves:** open the attributes of *PV power full*, *Inverter losses*, *Battery power*, the daily energy sensors that are computed and *Inverter clock offset* to see the formula, the value of each variable in it and the formula with those values filled in.

**PV power full** = load + the inverter's own consumption + battery power (+ = charging) − grid, never below 0, as a 60-second mean (like *PV power*, so the two can be compared). The own consumption comes from the four *Own consumption* numbers below (plus a small load-dependent part); the integration itself adds the few watts the inverter draws from the grid without reporting them. With the inverter's own battery currents it only confirms the reported PV power: in daylight the inverter shows its own DC draw as "discharge current", so weak PV (up to ~90 W here) stays invisible. **Set an external battery power sensor to see that hidden PV power.**

## Entities

One device (model, serial number, firmware) with:

- **Sensors:** grid voltage / frequency, grid power (signed W), AC output voltage / frequency, output apparent power (VA) and power (W), load %, battery voltage, charge current, discharge current, battery power (signed, + = charging), heat-sink, inverter, transformer and PV temperatures, **PV voltage** (smoothed) and **PV voltage raw** (every sample), PV current, **PV power** (smoothed, records few rows) and **PV power raw** (every sample, for live dashboards), **PV power median / max (10 min)** and **PV power median / max today** (the daily ones start over at midnight; max today is restored after a restart), the same smoothed / raw pairs for grid power and **Load power** (AC output, W), **PV energy today / this month / this year / total (kWh, from the inverter's own counters)**, mode (power on, standby = output off, line, battery, fault, power saving), charge stage (idle, bulk, absorption, float), **AC output on / off time (programs 48/49)** and **AC charger start / stop time (programs 46/47)**, **Inverter losses** and **PV power full** (power-balance values: 10-minute and 60-second means, see below), **Load / Grid / Battery / Balance / PV full daily energy** (kWh since midnight, see [Energy](#energy-kwh)).
- **Diagnostic sensors:** current settings and ratings (battery type, AC input range, float voltage, battery low-alarm voltage; the settings that have a control entity below, e.g. priorities, charge currents and the 24 V voltage thresholds, are shown by that control instead of a duplicate sensor), inverter clock and its offset from Home Assistant's time, fan speeds. **Hidden by default** (static values that never change): rated output values, battery rating voltage, serial number, firmware. Disabled by default: equalization settings, bus voltage, solar-charger battery voltage, battery level estimate, grid ratings, machine type, topology, output mode, second-output (dual output) thresholds, BMS SOC thresholds, grid-tie current, firmware date.
- **Binary sensors:** AC output, load on, charging, solar charging, grid charging, SBU priority, fault, warning (with the active items as attributes); one diagnostic problem sensor per warning/fault bit (grid lost, battery low, overload, over-temperature, … — five on by default); disabled by default: equalization enabled / active.
- **Own consumption numbers (W):** how much the inverter uses itself with no load, in four states: *battery mode*, *line mode*, *output off, standby* and *output off, solar charging*. Stored in Home Assistant only, never sent to the inverter. They feed *PV power full*, *PV full daily energy* and *Balance daily energy*. Defaults 48 / 47 / 12 / 34 W were measured on the test unit with an external meter and the battery's BMS; adjust them if your unit differs. See [docs/sensors.md](docs/sensors.md#power-balance-sensors).
- **Control entities (change settings, at your own risk):** switches for the 9 option flags, selects for output / charger source priority (only owner-verified values: *SBU*, *Only solar*) and solar supply priority (program 43: battery first / load first), numbers for max charging current and max utility charging current (values the inverter reports as allowed) and, on 24 V systems, back-to-utility / back-to-battery / cut-off / bulk voltages. A rejected command (`NAK`) raises an error; after `ACK` the settings are re-read. **Use at your own risk** — see [docs/integration.md](docs/integration.md#control-entities).

Full list with protocol sources: [docs/integration.md](docs/integration.md).

## Energy (kWh)

- **PV production:** use *PV energy total* (`total_increasing`, kWh) directly in *Settings → Dashboards → Energy → Solar production*. It is the inverter's own counter (same value as the vendor app), read with the CRC-less H protocol of units that support it.
- **Daily energy: load, grid, battery, balance** (kWh since local midnight, start over at midnight, restored after a restart on the same day). The inverter has no counters for these, so the integration integrates the power itself, with the same trapezoidal rule as Home Assistant's *Integral* (Riemann sum) helper, over **every** poll (not over the smoothed sensors, whose recorded values lag by up to 10 % / 10 min and would bias the sum). Only the writes are thinned out: a new state when the value grew by ≥ 0.05 kWh, or every 10 min with any change. A gap longer than three live-value intervals (lost connection, restart) adds nothing.
  - *Load daily energy* (`…_load_daily_energy`): AC output power (*Load power*).
  - *Grid daily energy* (`…_grid_daily_energy`): grid power drawn (export, if any, counts as 0). Only with the H protocol.
  - *Battery daily energy* (`…_battery_daily_energy`): net energy into the battery, **+** = charged more than discharged today, **−** = the battery ended the day emptier. From the inverter's battery currents (whole amperes; 1.03 × the BMS at night, up to ~1.1 × while charging), so treat it as rough.
  - *PV full daily energy* (`…_pv_full_daily_energy`): the integral of *PV power full* (every poll, unsmoothed), i.e. the real PV energy including what the inverter's own PV counter misses. Use it to compare with other panels. Needs the external battery power sensor to be meaningful in daylight; while that sensor is unavailable nothing is added. On the test unit's dull day 2026-10-07: 0.77 kWh by this method against 0.27 kWh in *PV energy today*.
  - *Balance daily energy* (`…_balance_daily_energy`): load + battery − real grid import, i.e. what the PV really gave after the inverter's own consumption. A battery that charges or empties does not change it. **> 0:** the system produced more than it consumed itself today; **< 0:** it cost more than it gave (night, own consumption, charging from the grid). The grid import includes the few watts the inverter draws without reporting them (worked out from the *Own consumption* numbers). Only with the H protocol.
  - Signed ones (battery, balance) are `total` with `last_reset` = midnight; load and grid are `total_increasing`.
  - For month/year totals, add a *Utility meter* helper on top of these, or use their long-term statistics.
- Inverters without the H protocol get no PV energy sensors; integrate `…_pv_power` the same way.

## Fast dashboard, small database

Every changed value is a new row in the recorder database (Home Assistant writes a state only when it changes, keeps raw history for 10 days, and 5-minute/hourly long-term statistics for every sensor with a state class). With a short *Live values interval* (down to 2 s) fast-changing sensors would fill it, so the integration offers a **raw / normal pair** (PV power, PV voltage, grid power, AC output power):

| Entity | Updates | Use it for |
|---|---|---|
| `sensor.<device>_pv_power_raw` (*PV power raw*) | every poll | live dashboard cards; **exclude it from the recorder** |
| `sensor.<device>_pv_power` (*PV power*) | mean of the last 60 s, written only when it moves by ≥ 10 % (and ≥ 20 W), drops to 0, or after 10 min with any change | history graphs, statistics, automations; the dashboard does not jump |
| `sensor.<device>_pv_power_median_10min` (*PV power median (10 min)*) | median of the last 10 min, same write rules | how the sun has really been doing lately, without cloud spikes |
| `sensor.<device>_pv_power_max_10min` (*PV power max (10 min)*) | maximum of the last 10 min, same write rules | recent peak |
| `sensor.<device>_pv_power_max_today` (*PV power max today*) | written only when a new maximum is reached; starts over at midnight | today's peak; survives a restart |

The same *max today* rule exists for the measured currents: `pv_current_max_today` (*PV current max today*), `battery_charge_current_max_today` and `battery_discharge_current_max_today` (whole amperes). Every *max today* sensor has the attribute `max_time` (*Time of maximum*): the local time when today's maximum was first reached (also restored after a restart). The inverter reports no grid input or AC output current, so there is no maximum for those.

`grid_power` / `grid_power_raw` and `ac_output_active_power` (*Load power*, the output in W) / `ac_output_active_power_raw` follow the same pair rule. `pv_input_voltage` / `pv_input_voltage_raw` too, with the voltage thresholds: ≥ 5 % and ≥ 1 V instead of ≥ 10 % / ≥ 20 W. Values are rounded before they reach the state (and so the database): battery-side and PV voltages to 0.1 V, grid / AC output voltages and all currents to whole numbers.

Exclude the raw sensors in `configuration.yaml`:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.inverter_vmii_4000_*_raw
```

Entity ids assume the default device name *Inverter VMII-4000*. Do **not** exclude the *PV energy* or the *… daily energy* sensors: the Energy dashboard needs their recorded statistics.

For other sensors you can build the same pattern with Home Assistant helpers: a *Statistics* helper (UI) or the YAML *Filter* integration (`time_simple_moving_average` + `time_throttle`) for a smoothed copy, then exclude the original from the recorder.

## Known limitations (Vevor GD5548JMH, firmware 00040.09)

- The PV energy counters, inverter clock, schedules (programs 46–49), program 43, extra temperatures and grid power come from the vendor Wi-Fi dongle's CRC-less "H" protocol (`QPRTL`, `HGEN`, `HEEP1`/`HEEP2`, `HTEMP`, `HGRID`); the integration detects it at start-up and skips these entities on inverters without it. Load-energy counters and BMS data are not available at all. **The schedules are read-only:** no command to change programs 46–49 is known, and there is no command to switch the output on/off.
- The schedules run on the inverter's own clock, which can drift (about 10 minutes slow on the test unit); see the *Inverter clock offset* sensor.
- The battery level % is the inverter's voltage-based estimate, not a state of charge (meaningless for LiFePO4); it is disabled by default.
- On this firmware output/charger priority codes follow the LCD menu position, not the generic Voltronic numbering; unconfirmed codes are shown as such and cannot be selected.
- PV values are not yet verified with the array producing.
- The inverter under-reports its own consumption: about 13 W (control board) is never shown, and grid power reads ~16 W + ~2 % low against an external meter. Battery currents are whole amperes (~25 W steps on 24 V). At night they match the battery's BMS within ~3 %, but in daylight the "discharge current" is the inverter stage's own DC draw: weak PV (up to ~90 W) is shown neither as PV power nor as a smaller discharge, so *PV power full* cannot reveal it from the inverter's data alone (an external battery meter can).
- Only one client should poll the RS232 gateway: with two clients (e.g. this integration and a script) the answers get mixed up.

## Troubleshooting

A single lost answer from the gateway no longer makes entities flicker: they keep their last value for two failed polls in a row and only then become unavailable. To see why polls fail, turn on debug logging (integration page → ⋮ → *Enable debug logging*, or in `configuration.yaml`):

```yaml
logger:
  default: warning
  logs:
    custom_components.voltronic_solar_inverter: debug
```

## Development

```bash
pip install -r requirements_test.txt
```

```bash
pytest
```

The protocol tests (`tests/test_framing.py`, `test_parsers.py`, `test_h_parsers.py`, `test_commands.py`, `test_client.py`, `test_smoothing.py`, `test_power_balance.py`) need only `pytest` and use responses recorded from the real inverter in `tests/fixtures/`. `tests/test_ha_integration.py` needs `pytest-homeassistant-custom-component` and is skipped without it; it runs as is on Linux/WSL (on Windows see [docs/integration.md](docs/integration.md#tests)). No test talks to a real inverter.

Other tools: [`python_scripts/get_inverter_info.py`](python_scripts/get_inverter_info.py) (original prototype, prints JSON) and [`tools/probe_inverter.py`](tools/probe_inverter.py) (read-only probe that refuses non-`Q` commands: `python tools/probe_inverter.py --mode both`). For a one-second "is the inverter answering?" check: `python tools/quick_check.py` (sends only `QMOD` and `QPIGS`). For power-balance tests: `python tools/balance_logger.py log.csv` (read-only, every 5 s; disable the integration while it runs). To export sensor history from a copy of your HA database: `python tools/ha_history.py list "%vevor%"` (read-only; see [docs/local-data.md](docs/local-data.md)).

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
| [docs/esphome-hardware.md](docs/esphome-hardware.md) | Step-by-step build guide: parts, wiring diagrams, finding the RJ45 pins, first test |
| [docs/inverter-vevor-gd5548jmh.md](docs/inverter-vevor-gd5548jmh.md) | Device reference (specs, settings, fault codes) |


## License

See [LICENSE](LICENSE).
