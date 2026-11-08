# ESPHome component `voltronic` (read-only, stage 1)

An ESPHome external component that owns the ESP32's UART, polls the inverter in **both** protocol dialects (PI30 with CRC and the Solar Plug "H" dialect without CRC) and publishes sensors, binary sensors and text sensors. It is stage 1 of the plan in [esphome-full-control.md](esphome-full-control.md): everything readable, **no setting commands yet**. Folder: [`esphome/components/voltronic/`](../esphome/components/voltronic/); ready entity list: [`esphome/packages/voltronic-inverter.yaml`](../esphome/packages/voltronic-inverter.yaml). Checked so far: `esphome config` (ESPHome 2026.10.2) is valid with every entity enabled, the C++ protocol layer passes host tests against the frames recorded from the real inverter, and the firmware compile result is in [Status](#status). **Not yet run on the real inverter.**

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
| Commands | Built-in allow-list, all read-only: PI30 `QPI QMN QID QVFW QPIGS QMOD QPIRI QFLAG QPIWS Q1 QBEQI` (CRC) and `QPRTL HIMSG1 HGRID HGEN HTEMP HEEP1 HEEP2` (no CRC). Nothing else can be sent |
| Groups | boot (identity, once; retried every 60 s until answered), **fast** (`QPIGS QMOD HGRID`, default 10 s), **slow** (`QPIRI QFLAG QPIWS Q1 QBEQI HGEN HTEMP HEEP1 HEEP2`, default 60 s). The most overdue command goes first, so slow ones are not starved |
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

Raw values only: there is no smoothing, no daily energy and no power balance yet (use ESPHome filters or Home Assistant helpers; plan in [esphome-full-control.md](esphome-full-control.md#7-derived-values-ha-integration--esphome)). `battery_capacity_percent` is the inverter's voltage-based estimate, **not** a state of charge.

## Files

| File | Role |
|---|---|
| [`__init__.py`](../esphome/components/voltronic/__init__.py) | Hub schema (`uart_id`, `fast_interval`, `slow_interval`), requires 2400 baud and both pins |
| [`sensor.py`](../esphome/components/voltronic/sensor.py), [`binary_sensor.py`](../esphome/components/voltronic/binary_sensor.py), [`text_sensor.py`](../esphome/components/voltronic/text_sensor.py) | Platforms; schemas are generated from the tables in `entities.py` |
| [`entities.py`](../esphome/components/voltronic/entities.py) | Entity tables: key → command, token index, sub-string, unit, device class, text map |
| [`voltronic.h`](../esphome/components/voltronic/voltronic.h) / [`.cpp`](../esphome/components/voltronic/voltronic.cpp) | The driver: command table (allow-list), scheduler, state machine, publishing |
| [`protocol.h`](../esphome/components/voltronic/protocol.h) | Pure protocol code, no ESPHome includes, host-tested |
| [`tests/esphome/protocol_test.cpp`](../tests/esphome/protocol_test.cpp), [`tests/test_esphome_protocol.py`](../tests/test_esphome_protocol.py) | Host test: compiles the header with g++ / clang++ / `python -m ziglang c++` (skipped without a compiler) and compares it with the Python protocol layer on all recorded frames in `tests/fixtures/` |

## How to add an entity

1. Find the token in [inverter-protocol.md](inverter-protocol.md) (0-based index). Add a line to `SENSORS`, `TEXT_SENSORS` or `BINARY_SENSORS` in `entities.py` (`pos`/`len` take a sub-string of the token, e.g. `HEEP2[12]` = `HHhh`).
2. If its command is new, add it to `COMMAND_TABLE` in `voltronic.cpp`, a case to `proto::validate` in `protocol.h`, and a fixture-based case to `tests/test_esphome_protocol.py` (`POLLED`). The command must answer on the real unit and be on the owner-approved read-only list ([AGENTS.md](../AGENTS.md) section 0).
3. List the key in `packages/voltronic-inverter.yaml`.

## Status

| Check | Result |
|---|---|
| `esphome config` with every entity (ESPHome 2026.10.2) | valid |
| Host tests `tests/test_esphome_protocol.py` (8 tests: request frames, 30+ recorded answers decoded and validated, corrupted CRC rejected, QPIWS classes / QFLAG / number parsing match Python, foreign H answers rejected) | pass |
| Firmware compile (`esp32` variant, ESP-IDF 5.5.6, all entities of the package) | success; RAM 26.6 %, flash 40.3 % (on Windows run it from PowerShell, not Git Bash, and with short paths: `ESPHOME_ESP_IDF_PREFIX`, `ESPHOME_DATA_DIR`, `PLATFORMIO_CORE_DIR`) |
| On the real inverter | **not done**. First check: log at `DEBUG`, look for `H dialect present`, no `bad frame` / `rejected` lines for an hour, compare `QPIGS` and `HGRID` values with the Home Assistant integration (mixed `Q`/`H` on one line is still unverified) |

## Next stages

Per [esphome-full-control.md](esphome-full-control.md#8-implementation-steps-each-with-a-check): derived values (stage 5), then controls with `enable_writes` (stage 6, owner tests every write on the real unit).
