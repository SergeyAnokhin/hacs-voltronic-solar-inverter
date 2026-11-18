# ESPHome component `voltronic` (read + controls)

An ESPHome external component that owns the ESP32's UART, polls the inverter in **both** protocol dialects (PI30 with CRC and the Solar Plug "H" dialect without CRC) and publishes sensors, binary sensors and text sensors. It covers stages 1 and 6 of the plan in [esphome-full-control.md](esphome-full-control.md): everything readable, plus the **control entities** (switch / select / number / button) that change the inverter's settings, off until `enable_writes: true` is set (see [Controls](#controls-changing-settings)). Derived values (stage 5) are not in the component. Folder: [`esphome/components/voltronic/`](../esphome/components/voltronic/); ready entity list: [`esphome/packages/voltronic-inverter.yaml`](../esphome/packages/voltronic-inverter.yaml). Checked so far: `esphome config` (ESPHome 2026.10.2) is valid with every entity enabled, the C++ protocol layer passes host tests against the frames recorded from the real inverter, and the firmware compile result is in [Status](#status). **The controls have never been sent to the real inverter: the owner tests every write himself.**

## Use it in your device YAML

Remove the old trial from `pvcontroller.yaml` (the `globals: rx_buf` and both `interval:` blocks): two readers on one UART steal each other's bytes. Then add:

```yaml
external_components:
  - source:
      type: git
      url: https://github.com/SergeyAnokhin/hacs-voltronic-solar-inverter
      ref: main
      path: esphome/components
    components: [voltronic]
    refresh: 60s

uart:                      # unchanged
  id: rs232
  tx_pin: GPIO25
  rx_pin: GPIO26
  baud_rate: 2400

voltronic:
  id: inverter
  uart_id: rs232
  # fast_interval: 10s     # QPIGS, QMOD, HGRID (min 2s)
  # slow_interval: 60s     # everything else (min 5s)

packages:
  pv_current:              # unchanged (Hall sensors)
    url: https://github.com/SergeyAnokhin/hacs-voltronic-solar-inverter
    ref: main
    files: [esphome/packages/pv-string-current.yaml]
    refresh: 60s
  inverter:                # all inverter entities
    url: https://github.com/SergeyAnokhin/hacs-voltronic-solar-inverter
    ref: main
    files: [esphome/packages/voltronic-inverter.yaml]
    refresh: 60s
```

The `git` source works only after the component is pushed to the `main` branch of the repository. To try it before that, copy the folder `esphome/components/voltronic` to `components/voltronic` next to your YAML (ESPHome Dashboard add-on: `/config/esphome/components/voltronic`), replace the `source:` by `type: local` / `path: components`, and copy `voltronic-inverter.yaml` next to the YAML as `packages: inverter: !include voltronic-inverter.yaml`.

Instead of the package you can list only the entities you want (`sensor: - platform: voltronic`, keys in [`entities.py`](../esphome/components/voltronic/entities.py)). **A command is polled only when at least one of its entities exists**, so a shorter list leaves more time on the 2400 baud line.

## What it does

| Part | Behaviour |
|---|---|
| Commands | Built-in allow-list of queries: PI30 `QPI QMN QID QVFW QPIGS QMOD QPIRI QFLAG QPIWS Q1 QBEQI` (CRC) and `QPRTL HIMSG1 HGRID HGEN HTEMP HEEP1 HEEP2 HSTS` (no CRC). Settings have their own allow-list ([Controls](#controls-changing-settings)); nothing else can be sent |
| Groups | boot (identity, once; retried every 60 s until answered), **fast** (`QPIGS QMOD HGRID`, default 10 s), **slow** (`QPIRI QFLAG QPIWS Q1 QBEQI HGEN HTEMP HEEP1 HEEP2 HSTS`, default 60 s). The most overdue command goes first, so slow ones are not starved |
| H dialect | `QPRTL` is sent once at boot. An `H…` answer enables the H queries; silence disables them and `QPRTL` is asked again every 5 min |
| Reliability | one command in flight; 2 s timeout; one immediate retry (the first command after idle is sometimes lost); CRC checked; answers validated by field count and plausibility (a foreign `HGRID` answer is dropped); 0.2 s of late bytes discarded after a failure; stale RX bytes dropped before every send; 100 ms gap |
| Availability | 6 failed exchanges in a row → the numeric sensors of that command become unknown; text and binary sensors keep the last value |
| Logging | `logger: level: DEBUG` shows every answer (`QPIGS -> …`), failures and retries; `VERBOSE` also every request |

Ported from the Python integration: [`protocol.h`](../esphome/components/voltronic/protocol.h) (CRC, framing, validators, QPIWS classes, QFLAG) mirrors `protocol/framing.py` and `parsers.py`; the polling plan mirrors `coordinator.py`.

## Entities

Keys, field positions and units are in [`entities.py`](../esphome/components/voltronic/entities.py); names in the package. They follow [integration.md](integration.md#entities):

| Platform | Content |
|---|---|
| `sensor` | `QPIGS` live values (grid, AC output, load, bus, battery V / charge / discharge current, **battery power** derived `V × (I_chg − I_dis)`, heat sink, PV V / A / W, SCC V), `grid_power` (`HGRID`, + = import), `QPIRI` settings (P02, P11, P12, P13, P26, P27, P29 and ratings), `QBEQI` equalization values, `HGEN` PV energy today / month / year / total, `HTEMP` temperatures and fans, `HEEP1/2` low-alarm voltage P24, schedules P46–P49 as hours, BMS thresholds, grid-tie current |
| `binary_sensor` | load on, charging, solar charging, AC charging, AC output switched on / active, charging to float, `warnings_present`, `faults_present`, one `alarm_<name>` per `QPIWS` bit (grid lost, battery low, overload, over temperature, …), the nine `QFLAG` options, equalization enabled / active |
| `text_sensor` | operating mode (`QMOD`; `Charging` = letter `C`), output / charger priority (P01 / P16, LCD menu-position codes), battery type, input range, charge stage, solar supply priority (P43), inverter clock, model, serial, firmware version / date, protocol |

Raw values only: there is no smoothing, no daily energy and no power balance yet (use ESPHome filters or Home Assistant helpers; plan in [esphome-full-control.md](esphome-full-control.md#7-derived-values-ha-integration--esphome)). The control entities are in [Controls](#controls-changing-settings). `battery_capacity_percent` is the inverter's voltage-based estimate, **not** a state of charge.

## Controls (changing settings)

The `switch`, `select`, `number` and `button` platforms of the component send the inverter's setting commands: the same set as the Home Assistant integration ([`commands.py`](../custom_components/voltronic_solar_inverter/protocol/commands.py)), ported to C++. They are listed in the opt-in package [`esphome/packages/voltronic-controls.yaml`](../esphome/packages/voltronic-controls.yaml):

```yaml
voltronic:
  id: inverter
  uart_id: rs232
  enable_writes: true          # default false: without it every change is refused and logged

packages:
  inverter: ...voltronic-inverter.yaml     # all read entities
  controls: ...voltronic-controls.yaml     # the controls below
```

**Every write is unverified on the owner's unit.** Nothing is sent by the agent: the owner changes one value, checks it on the LCD and in the read-back entity, restores it, and the Status column of [settings-map.md](settings-map.md) is updated. Safety rules in the code ([`protocol.h`](../esphome/components/voltronic/protocol.h) `is_allowed_write`, [`voltronic.cpp`](../esphome/components/voltronic/voltronic.cpp)):

- `enable_writes: false` (default): every request is refused with a warning, nothing is sent.
- Only the exact shapes below can be sent, with the ranges below; anything else (`PF`, `PBT`, `PBFT`, `PGR`, `PEd`, `PBATCD011`, `F50`, queries, …) is refused. The list is compared with `commands.py` by `tests/test_esphome_controls.py`.
- At most one setting every 2 s, never retried (a timeout is reported, not repeated), duplicates in the queue are dropped, the queue holds 8.
- A setting waits in IDLE (never in the middle of a query's retry). After an ACK the hub polls the parameter's read-back command at once; the entity shows what the inverter reports. NAK / timeout / bad answer: the entity goes back to its old value and the log says why.
- Answers `(ACK` / `(NAK` (CRC) and the PI18-style `^1` / `^0` (with or without CRC) of the service-tool setters are understood.

| Platform | Entity keys (see `entities.py`) | Setting | Read back |
|---|---|---|---|
| `switch` | `buzzer` P18, `overload_bypass` P23, `power_saving` P08, `lcd_return_to_default` P19, `overload_restart` P06, `over_temperature_restart` P07, `backlight` P20, `primary_source_interrupt_alarm` P22, `fault_code_record` P25 | `PE<x>` / `PD<x>` | `QFLAG` |
| `switch` | `second_output_mode` (P60) / `second_output` | `PDAULC01/00` / `PDAULON01/00` | `HEEP2[0]` / `HSTS[2]` char 4 |
| `select` | `output_source_priority` P01 (Solar first, SBU) | `POP00/01` | `QPIRI[16]` |
| `select` | `charger_source_priority` P16 | `PCP00/01/02` | `QPIRI[17]` |
| `select` | `solar_supply_priority` P43 | `PVENGUSE00/01` | `HEEP1[3]` char 3 |
| `select` | `max_charging_current` P02 (10..80 A), `max_ac_charging_current` P11 (2, 10..60 A): the lists this unit reports | `MNCHGC<nnn>` / `MUCHGC<nnn>` | `QPIRI[14]` / `QPIRI[13]` |
| `select` | `battery_control` (Auto, No discharge, No charge, Neither) | `PBATCD000/101/110/100` (never `011`, `010`) | none: shows the last accepted option, restored after a reboot |
| `number` | `battery_recharge_voltage` P12 (22.0–25.5 step 0.5), `battery_redischarge_voltage` P13 (24.0–29.0 step 0.5), `battery_under_voltage` P29 (20.0–26.0), `battery_bulk_voltage` P26 (24.0–30.0) | `PBCV` / `PBDV` / `PSDV` / `PCVV` `<nn.n>` | `QPIRI[8]` / `[22]` / `[9]` / `[10]` |
| `number` | `battery_low_alarm_voltage` P24 (20.0–27.0), `second_output_cutoff_voltage`, `second_output_recover_voltage` (20.0–30.0) | `PSLV` / `PDSDV` / `PDSRV` | `HEEP2[3]` / `[1]` / `[15]` |
| `number` | `second_output_cutoff_soc`, `second_output_recover_soc`, `second_output_recover_delay` (step 5 min), `second_output_discharge_time` (step 5 min) | `PDSDS` / `PDSRS` / `PDDLYT` / `PDDCGT` | `HEEP2[2]` / `[16]` / `[13]` / `[16]` |
| `number` | `bms_lock_soc` P38, `bms_back_to_ac_soc` P39, `bms_back_to_battery_soc` P40, `bms_restart_soc` P41 (not in the package: no BMS link here) | `BMSSDC` / `BMSB2UC` / `BMSU2BC` / `BMSSRC` | `HEEP1[10]` / `[11]` / `[12]` / `[13]` |
| `number` | `ac_output_on_hour` P48 / `ac_output_off_hour` P49, `ac_charger_start_hour` P46 / `ac_charger_stop_hour` P47 (0–23) | `^S???ACLT` / `^S???ACCT` `<HH>-<HH>`: a change sends the whole window, the other hour comes from the last read | `HEEP2[12]` / `[11]` |
| `number` | `battery_discharge_current_limit`, `max_discharging_current` | `DISCC<nnn>`, `PBATMAXDISC<nnn>` (0 or 30..150) | none: last accepted value, restored |
| `button` | `set_clock` (needs a `time:` component; the package adds one) | `^S???DAT<yymmddhhmmss>` from the ESP's local time | `inverter_clock` (HGEN) |

The voltage ranges are for a 24 V battery system. The two charging-current lists are those of the owner's unit (`QMCHGCR`, `QMUCHGCR`); other units need their own lists in `entities.py`.

## Files

| File | Role |
|---|---|
| [`__init__.py`](../esphome/components/voltronic/__init__.py) | Hub schema (`uart_id`, `fast_interval`, `slow_interval`, `enable_writes`), requires 2400 baud and both pins; auto-loads the platforms the controls need |
| [`sensor.py`](../esphome/components/voltronic/sensor.py), [`binary_sensor.py`](../esphome/components/voltronic/binary_sensor.py), [`text_sensor.py`](../esphome/components/voltronic/text_sensor.py) | Platforms; schemas are generated from the tables in `entities.py` |
| [`switch.py`](../esphome/components/voltronic/switch.py), [`select.py`](../esphome/components/voltronic/select.py), [`number.py`](../esphome/components/voltronic/number.py), [`button.py`](../esphome/components/voltronic/button.py) | Control platforms; schemas from the control tables in `entities.py` |
| [`entities.py`](../esphome/components/voltronic/entities.py) | Entity tables: key → command, token index, sub-string, unit, device class, text map; control tables `SWITCHES`, `SELECTS`, `NUMBERS`, `BUTTONS` |
| [`controls.h`](../esphome/components/voltronic/controls.h) / [`.cpp`](../esphome/components/voltronic/controls.cpp) | The control entities (`VoltronicSwitch/Select/Number/Button`): ask the hub to write, show the read-back, assumed state with restore |
| [`voltronic.h`](../esphome/components/voltronic/voltronic.h) / [`.cpp`](../esphome/components/voltronic/voltronic.cpp) | The driver: command table (allow-list), scheduler, state machine, publishing, write queue |
| [`protocol.h`](../esphome/components/voltronic/protocol.h) | Pure protocol code, no ESPHome includes, host-tested: framing, validators, setting builders, the write allow-list, answer decoding |
| [`tests/esphome/protocol_test.cpp`](../tests/esphome/protocol_test.cpp), [`tests/test_esphome_protocol.py`](../tests/test_esphome_protocol.py) | Host test: compiles the header with g++ / clang++ / `python -m ziglang c++` (skipped without a compiler) and compares it with the Python protocol layer on all recorded frames in `tests/fixtures/` |
| [`tests/test_esphome_controls.py`](../tests/test_esphome_controls.py) | The same binary: every setting builder and the allow-list against `commands.py` (all ranges, steps, boundaries, refused values), the answers `ACK` / `NAK` / `^1` / `^0`, the entity tables against the Python ranges, the never-send list |
| [`tests/esphome/driver_write_test.cpp`](../tests/esphome/driver_write_test.cpp), [`tests/test_esphome_driver_writes.py`](../tests/test_esphome_driver_writes.py) | Runs the real driver (`voltronic.cpp`) against stand-ins for the ESPHome classes (`tests/esphome/stubs/`) and a fake inverter: writes off by default, allow-list, ACK / NAK / `^1` / timeout without a second try, 2 s gap, duplicates, bounded queue, read-back after an ACK |

## How to add an entity

1. Find the token in [inverter-protocol.md](inverter-protocol.md) (0-based index). Add a line to `SENSORS`, `TEXT_SENSORS` or `BINARY_SENSORS` in `entities.py` (`pos`/`len` take a sub-string of the token, e.g. `HEEP2[12]` = `HHhh`).
2. If its command is new, add it to `COMMAND_TABLE` in `voltronic.cpp`, a case to `proto::validate` in `protocol.h`, and a fixture-based case to `tests/test_esphome_protocol.py` (`POLLED`). The command must answer on the real unit and be on the owner-approved read-only list ([AGENTS.md](../AGENTS.md) section 0).
3. List the key in `packages/voltronic-inverter.yaml`.

## Status

| Check | Result |
|---|---|
| `esphome config` with every entity (ESPHome 2026.10.2) | valid |
| Host tests `tests/test_esphome_protocol.py` (8 tests: request frames, 30+ recorded answers decoded and validated, corrupted CRC rejected, QPIWS classes / QFLAG / number parsing match Python, foreign H answers rejected) | pass |
| Firmware compile (`esp32` variant, ESP-IDF 5.5.6, all read entities **and all controls** of the two packages, `enable_writes: true`) | success; RAM 30.0 %, flash 42.0 % (on Windows run it from PowerShell, not Git Bash, and with short paths: `ESPHOME_ESP_IDF_PREFIX`, `ESPHOME_DATA_DIR`, `PLATFORMIO_CORE_DIR`) |
| Host tests of the controls (`tests/test_esphome_controls.py`, 13 tests; `tests/test_esphome_driver_writes.py`) | pass |
| Controls on the real inverter | **never sent**; the owner tests each one (Status column in [settings-map.md](settings-map.md)) |
| Reading on the real inverter | the owner's ESP32 reads `QPIGS` over the RS232 port (checked in the trial code); the component itself has run on it since 2026-11-14 without a crash. First check: log at `DEBUG`, look for `H dialect present`, no `bad frame` / `rejected` lines for an hour, compare `QPIGS` and `HGRID` values with the Home Assistant integration (mixed `Q`/`H` on one line is still unverified) |

## Next stages

Per [esphome-full-control.md](esphome-full-control.md#8-implementation-steps-each-with-a-check): the controls (stage 6) are written and host-tested; the owner tests them one by one on the real unit. Still open: derived values (stage 5: daily energies, power balance, smoothing), then switching the Hall package's PV voltage from the Home Assistant entity to this component's `pv_input_voltage` (the owner will do that later, after more testing) and turning off the Elfin gateway and the HACS integration.
