# ESPHome full control: porting the whole integration to the ESP32

Specification and implementation plan for making the ESP32 (ESPHome) do everything the Home Assistant integration does today: all sensors, all derived values and all setting controls, without the Elfin gateway and without the HACS integration. It is a **plan, not code**: nothing in this document is implemented yet (owner's wish, 2026-11-08: documentation first, no package; the owner will try to build it, possibly with an agent in the ESPHome project). The current ESPHome files are described in [esphome.md](esphome.md); the wiring in [esphome-hardware.md](esphome-hardware.md). Protocol facts are in [inverter-protocol.md](inverter-protocol.md), the setting map in [settings-map.md](settings-map.md), the derived-value formulas in [sensors.md](sensors.md).

The starting point is the owner's `pvcontroller.yaml` (the trial that already talks to the inverter over RS232), reviewed in [section 10](#10-starting-point-the-owners-pvcontrolleryaml). The Hall sensors in that file are a separate topic; this plan is about the inverter side only.

## 1. Where we are

| Layer | What exists | Covers |
|---|---|---|
| HA integration + ESP32 as a bridge ([`vevor-bridge.yaml`](../esphome/vevor-bridge.yaml), TCP 8899) | everything in [integration.md](integration.md) | **100 % of the features**, but logic lives in Home Assistant |
| ESP32 native, core `pipsolar` ([`vevor-inverter.yaml`](../esphome/vevor-inverter.yaml) + [`vevor-controls.yaml`](../esphome/packages/vevor-controls.yaml)) | `QPIGS QPIRI QMOD QFLAG QPIWS` + 6 writes families | PI30 live values, settings, flags, 24 V voltage/current writes. No H dialect, no `Q1`/`QBEQI`/identity, no derived values |
| ESP32 Hall package ([`pv-string-current.yaml`](../esphome/packages/pv-string-current.yaml)) | two PV string currents via ADS1115 | independent of the inverter UART |

Note: the bridge already gives full functionality. Native "full control" is worth it only if the ESP32 should work **without Home Assistant logic** (own smoothing, daily energy, power balance, local automations, MQTT/other consumers) or if the owner wants one device instead of ESP32 + HACS integration.

### Gap: what `pipsolar` cannot do

| Missing in `pipsolar` | Needed for |
|---|---|
| CRC-less **H dialect** (`QPRTL`, `HGRID`, `HGEN`, `HTEMP`, `HEEP1/2`, `HIMSG1`) | grid power, PV energy counters, inverter clock, P46–P49 schedules, temperatures/fans, P43/P24/BMS/dual-output settings, firmware date |
| Free choice of polled queries | `Q1` (charge stage), `QBEQI` (equalization), `QID`/`QVFW`/`QPI` (identity), `QMCHGCR`/`QMUCHGCR` (allowed currents) |
| Generic write queue with ACK/NAK result | `PVENGUSE`, `PBATCD`, `PBATMAXDISC`, status feedback |
| Own validation of foreign/shifted answers | robustness (see section 3) |

`pipsolar` polls its fixed set in a loop, accepts a 10-command write buffer and exposes `output`/`switch` platforms; the docs mention no custom queries and no CRC-less frames. The repository's controls package calls `queue_command()` directly, which compiles with ESPHome 2026.9.1 but is **not documented** by ESPHome.

## 2. Architecture decision

**Only one component may own the UART.** `pipsolar`, `solarplug` and `stream_server` all read the same RX stream, so they cannot be combined on one port; two readers steal each other's bytes (the same effect as two clients on the Elfin gateway, see [project-overview.md](project-overview.md#environment-facts)).

| Option | Effort | Verdict |
|---|---|---|
| A. Keep bridge + HACS integration | none | already full; no standalone ESP32 |
| B. `pipsolar` + Hall package, derived values with ESPHome templates | low | no H dialect: loses grid power, PV energy counters, clock, schedules → **not full** |
| C. External component [`solarplug-esphome`](https://github.com/kOld/solarplug-esphome) (MIT; fork: rutgerputter) | medium | H dialect only (no PI30 `Q` queries with CRC; its writes are tuned to a 48 V VMII-6200 and are off by default). Cannot run next to `pipsolar` |
| **D. Own local external component `voltronic` (single UART owner, both dialects)** | high | **Recommended.** A port of `protocol/` + the polling plan of `coordinator.py`. Can borrow the queue design of solarplug (ring buffer, duplicate reads dropped, full queue drops with a warning; MIT) |

Recommended layout (local external component, no GitHub dependency):

```text
esphome/
  vevor-full.yaml                 # the device: wifi/api/ota, uart, voltronic:, entity lists
  components/voltronic/
    __init__.py                   # hub schema: uart_id, intervals, enable_writes, update groups
    sensor.py binary_sensor.py text_sensor.py number.py select.py switch.py
    voltronic.h / voltronic.cpp   # scheduler + framing + dispatch
    parsers.h / parsers.cpp       # pure functions, no ESPHome includes (host-testable)
  packages/pv-string-current.yaml # unchanged (ADS1115 on I2C, independent)
```

Keep `parsers.*` and the CRC/framing code free of ESPHome headers, exactly like `protocol/` is free of HA imports: it can then be unit-tested on the PC with the fixtures in [`tests/fixtures/`](../tests/fixtures/) (see section 8).

## 3. Protocol rules the component must implement

All of this is already proven in [`client.py`](../custom_components/voltronic_solar_inverter/protocol/client.py); port the behaviour, not just the commands.

| Rule | Detail |
|---|---|
| UART | 2400 baud 8N1 through the MAX3232. Pins are configurable: the repository configs use GPIO17 TX / GPIO16 RX, the owner's `pvcontroller.yaml` uses **GPIO25 TX / GPIO26 RX** (keep his pins; both are free of the Hall package's I²C on GPIO21/22) |
| PI30 request | `ASCII + CRC_hi + CRC_lo + 0x0D`; CRC-16/XMODEM (poly 0x1021, init 0); a CRC byte equal to `0x28`, `0x0D` or `0x0A` is incremented by 1 |
| PI30 response | `'(' payload CRC_hi CRC_lo 0x0D`; reject on CRC mismatch |
| H dialect | request `ASCII + 0x0D`, response `'(' payload 0x0D`, **no CRC either way**. PI30 commands are silent without CRC and H commands are silent with CRC |
| Dialect detection | at start-up send `QPRTL` without CRC; an answer (`HPVINV02`) enables all H queries, silence disables them (never poll them then) |
| One command in flight | read until `0x0D`; timeout 2 s; no pipelining |
| Gap | ≥ 0.1 s between exchanges |
| First command after idle can be lost (0 bytes) | retry a **query** once immediately; never retry a write |
| After a timeout | flush RX (drain ~0.2 s) before the next command: a late answer must never be read as the next command's reply (seen: `QMOD` receiving a `QPIGS` payload) |
| Validation of every answer | `QMOD` = exactly one letter; field count of each parser; `HGRID`: first field a voltage 0–300 V, power has a sign and `|P| ≤ 20 kW`; H answers have no CRC, so these checks are the only protection |
| Optional queries fail softly | a failed `Q1`/`QBEQI`/`H*` keeps the previous value for 5 misses, then only its own entities become unavailable (`NAN`/unknown); a failed `QPIGS`/`QMOD` counts towards unavailability after 5 misses |
| Silent commands cost a full timeout | poll only commands that answer (list in section 4); never add `QT`, `QET`, `QOPPT`, `QBMS`, … |
| Writes | `P…`/`M…` frames with CRC; answer `(ACK` or `(NAK`; no retry; after ACK trigger an immediate re-read of the owning query (`QPIRI`/`QFLAG`/`HEEP1`) so the entity shows the real value |

CRC code (a direct port of [`framing.py`](../custom_components/voltronic_solar_inverter/protocol/framing.py); **not compiled yet**, so check it against the CRC vectors of `tests/test_framing.py` in step 1):

```cpp
static uint16_t crc16_xmodem(const uint8_t *d, size_t n) {
  uint16_t crc = 0;
  for (size_t i = 0; i < n; i++) {
    crc ^= (uint16_t) d[i] << 8;
    for (int b = 0; b < 8; b++) crc = (crc & 0x8000) ? (uint16_t) ((crc << 1) ^ 0x1021) : (uint16_t) (crc << 1);
  }
  return crc;
}
static uint8_t esc(uint8_t v) { return (v == 0x28 || v == 0x0D || v == 0x0A) ? v + 1 : v; }
// frame = cmd bytes + esc(crc >> 8) + esc(crc & 0xFF) + 0x0D
```

⚠ **Not verified on the real unit:** `Q` (CRC) and `H` (no CRC) queries mixed on one persistent line. The research sent them on separate connections; the HA integration mixes them on one, owner check still open ([project-overview.md](project-overview.md#open-items--roadmap), item 5). The ESP32 will do the same, so test this first.

## 4. Polling plan

Same split as the integration (`coordinator.py`); a full slow cycle is 9 commands, ~4 s, a fast cycle ~1.5 s. Latencies: `QPIGS` 0.6–0.7 s, `QPIRI` 0.6 s, `Q1` 0.5 s, others 0.2–0.5 s ([inverter-protocol.md](inverter-protocol.md#timing-and-reliability-2026-10-02)). The queue schedules; the hub config sets `fast_interval` (default 10 s, minimum 2 s) and `slow_interval` (default 60 s).

| Group | Commands | Entities fed |
|---|---|---|
| once at boot | `QPI QMN QID QVFW` (+ `QVFW2`, `QMCHGCR`, `QMUCHGCR`, `QPRTL`, `HIMSG1`) | identity text sensors, allowed currents for the selects, H dialect flag |
| fast | `QPIGS`, `QMOD`, (`HGRID`) | live values, binary sensors, grid power, all derived power values |
| slow | `QPIRI`, `QFLAG`, `QPIWS`, (`QBEQI`), `Q1`, (`HEEP1`, `HEEP2`, `HGEN`, `HTEMP`) | settings, flags, warnings, equalization, charge stage, schedules, energy counters, clock, temperatures |
| on demand | any validated write, then re-read of its owner query | controls |

(…) = only when `QPRTL` answered. Never poll: `HSTS HOP HBAT HPV HPVB HBMS1-3 QDI QFS QWS QBV QBT QGR QMD`.

## 5. Read entities: field → ESPHome entity

Indices are the 0-based tokens of the reply ([inverter-protocol.md](inverter-protocol.md) has units, samples and caveats). Names follow the HA integration so dashboards can be reused; add `unique_id`-stable `id:`s.

### Fast

| Source | Entities |
|---|---|
| `QPIGS[0,1]` / `[2,3]` | grid V/Hz, AC output V/Hz |
| `QPIGS[4,5,6]` | apparent power VA, load power W (raw + smoothed), load % |
| `QPIGS[8]`, `[9]`, `[15]` | battery V, charge A, discharge A (whole amperes); `[10]` battery estimate % (disabled, **not SOC**); `[7]`, `[14]` bus V and SCC V (diagnostic) |
| `QPIGS[11]` | heat-sink °C |
| `QPIGS[12,13,19]` | PV current (one decimal, raw + smoothed + max today), PV voltage (raw + smoothed), PV power W (raw + smoothed + median/max 10 min + max today) |
| `QPIGS[16]` bits (char 0 = b7 … char 7 = b0) | binary: load on b4, charging b2, solar charging b1, grid charging b0 |
| `QPIGS[20]` | binary: output switched on b9 (verified), charging to float b10 |
| `QMOD` | text/enum mode: P, S, L, B, F, H, **C** (charging, output off); unknown letter → "unknown" + one warning; binary "AC output" = L or B |
| `HGRID[0,1]`, `[6]` | grid V/Hz (cross-check), **grid power W signed, + = import** (raw + smoothed) |

### Slow

| Source | Entities |
|---|---|
| `QPIRI` (25 fields, layout in the protocol doc) | rated V/Hz/VA/W, battery rating, P12/P13/P26/P27/P29 voltages, P02/P11 currents, battery type, input range, output and charger priority (menu-position codes), machine type, topology |
| `QFLAG` (`EabjvxyDkuz`) | nine flag switches (also the read side of the controls) |
| `QPIWS` (32-char bit string) | `warning`, `fault` (+ attribute lists as a text sensor), problem binary sensors for the bits in the table of [integration.md](integration.md#entities) (default on: a5 grid lost, a9 over-temperature, a12 battery low, a14 under-voltage shutdown, a16 overload) |
| `Q1[17]` | charge stage (10 idle, 11 bulk verified; 12 absorb, 13 float generic) |
| `QBEQI` | equalization voltage/time/timeout/interval, enabled, active (read-only on purpose) |
| `HGEN[0..1]` | inverter clock (YYMMDD HH:MM), clock offset vs ESPHome `time` in minutes |
| `HGEN[2..5]` | PV energy today / month / year / total, kWh, `total_increasing`; the inverter's own counters |
| `HEEP2[12]`, `[11]` | AC output on/off hour (P48/P49), AC charger start/stop hour (P46/P47), as `HHhh` |
| `HEEP1[3]` char 3 | solar supply priority P43 (0 battery first / 1 load first) |
| `HEEP2[3]` | battery low-alarm voltage P24 |
| `HEEP1[10,12,17]`, `HEEP2[1,2,13,15]` | BMS shutdown/back SOC, grid-tie current, dual-output values (disabled by default, unconfirmed positions) |
| `HTEMP[0,2,3,5,6]` | inverter / transformer / PV °C, fan 1/2 % |
| `HIMSG1`, `QID`, `QVFW` | firmware version/date, serial (text sensors, diagnostic) |

## 6. Control entities: command → ESPHome platform

Every write is **unverified** on the real unit unless the table says otherwise; **only the owner tests writes** ([AGENTS.md](../AGENTS.md) section 0, [settings-map.md](settings-map.md)). The component validates in C++ exactly like [`commands.py`](../custom_components/voltronic_solar_inverter/protocol/commands.py) does in Python (allow-list of command prefixes, argument ranges, nothing else can be sent) and exposes a hub option `enable_writes: false` by default; controls are created only when it is `true`.

| Entity (ESPHome platform) | Frame | Values | Read-back |
|---|---|---|---|
| 9 switches (P06 `u`, P07 `v`, P08 `j`, P18 `a`, P19 `k`, P20 `x`, P22 `y`, P23 `b`, P25 `z`) | `PE<x>` / `PD<x>` | on / off | `QFLAG` |
| select Output source priority (P01) | `POP<NN>` | 00 Solar first (SUB), 01 SBU, (02 utility first: not offered until the owner confirms) | `QPIRI[16]` |
| select Charger source priority (P16) | `PCP<NN>` | 00 solar first, 01 solar + utility, 02 only solar | `QPIRI[17]` |
| select Solar supply priority (P43) | `PVENGUSE<NN>` | 00 battery first, 01 load first (read codes verified) | `HEEP1[3]` char 3 |
| select Max charging current (P02) | `MNCHGC<nnn>` | values from `QMCHGCR` (10…80 A) | `QPIRI[14]` |
| select Max utility charging current (P11) | `MUCHGC<nnn>` | values from `QMUCHGCR` (2, 10…60 A) | `QPIRI[13]` |
| number Back to utility (P12) | `PBCV<nn.n>` | 22.0–25.5 step 0.5 (24 V) | `QPIRI[8]` |
| number Back to battery (P13) | `PBDV<nn.n>` | 24.0–29.0 step 0.5 | `QPIRI[22]` |
| number Low DC cut-off (P29) | `PSDV<nn.n>` | 20.0–26.0 step 0.1 | `QPIRI[9]` |
| number Bulk voltage (P26) | `PCVV<nn.n>` | 24.0–30.0 step 0.1 | `QPIRI[10]` |
| select Battery charge/discharge override | `PBATCD<abc>` | `000` auto, `101` no discharge, `110` no charge, `100` neither; shutdown codes `011`/`010` **never** | none (assumed state, `restore_value`) |
| number Max discharging current | `PBATMAXDISC<nnn>` | 0 = off, 30–150 | none (assumed state) |

Voltage numbers exist only when the battery rating read from `QPIRI[7]` is 24 V (ranges are the 24 V column of the manual). Prefer the component's own `number`/`select`/`switch` platforms over `template` + `queue_command` lambdas: they get the ACK/NAK result, the validation, the read-back refresh, and `assumed_state` for the two unreadable ones.

**Deliberately not written** (same list as the integration): float voltage `PBFT`, battery type `PBT`, equalization `PBEQ*`, input range `PGR`, clock `DAT`, dual output `PTOP*`, feed-in `PEd` (owner never exports), `RTEY`, `PF` (factory reset: never), `F50`/`F60`, and the P46–P49 schedules (no known command; read-only via `HEEP2`). Adding any of them needs the owner's explicit request.

Safety extras for the ESP32 (it can run automations without HA):

- no local automation may write more often than the owner asked for; rate-limit writes to one per 2 s and drop duplicates already queued;
- a write whose read-back differs after two slow cycles raises a warning text sensor ("write not applied");
- the component never sends anything that is not on its built-in allow-list, and it ignores raw strings from the API.

## 7. Derived values: HA integration → ESPHome

The HA integration computes these in Python ([`power_balance.py`](../custom_components/voltronic_solar_inverter/power_balance.py), [`smoothing.py`](../custom_components/voltronic_solar_inverter/smoothing.py)). On the ESP32 each has a standard ESPHome building block; check each against the current ESPHome docs when implementing.

| Integration feature | ESPHome mechanism | Notes |
|---|---|---|
| Battery power = V × (I<sub>chg</sub> − I<sub>dis</sub>) | `template` sensor, lambda over the three source sensors | positive = charging |
| `_raw` / smoothed pair (60 s mean, publish on ≥ 10 % **and** ≥ 20 W change, drop to 0, or every 10 min) | raw sensor with `filters`; smoothed = `sliding_window_moving_average` (window 60 s worth of samples) + `or: [delta: …, heartbeat: 10min]` | the AND of "10 % and 20 W" needs a small lambda filter; `delta` alone is OR-like |
| 10 min median / max | `median` and `max` filters (`window_size` = 600 s / fast interval) | |
| Max today + time reached | `template` sensor + `globals` reset by `time` `on_time` at 00:00 | attribute `max_time` → separate timestamp text sensor (no state attributes in ESPHome) |
| Daily energy (trapezoid, reset at midnight, restore) | `total_daily_energy` platform or `integration` (trapezoid) + `time` | integrate the **raw** power, not the smoothed one (same decision as the integration); keep `restore: true` |
| Inverter losses, PV power full, net generation | `template` sensors with the formulas of [sensors.md](sensors.md#power-balance-sensors), implemented once in C++ (`power_balance.h`) | formulas are shown as attributes in HA; in ESPHome publish the formula text as a diagnostic text sensor or document it |
| Own-consumption numbers (48 / 47 / 12 / 34 W) | `number` platform `template`, `optimistic`, `restore_value: true` | HA-only config, never sent to the inverter |
| Optional external battery power (BMS) | `homeassistant` sensor platform importing the HA entity | needs the API connection; unusable value → skip the sample (as in HA); if the ESP32 must run without HA, the inverter's currents are used |
| Clock offset, "last_period" attribute | `time` platform `homeassistant` for the offset; `last_period` as a separate sensor updated at midnight | |

Time source: `time: platform: homeassistant` (or `sntp`) is required for the daily resets and the offset. If Wi-Fi is down at boot, daily values are held (not reset) until time is valid.

## 8. Implementation steps (each with a check)

| # | Step | Check |
|---|---|---|
| 1 | Pure C++ `parsers`: framing, CRC, `QPIGS QPIRI QMOD QFLAG QPIWS Q1 QBEQI HGEN HGRID HTEMP HEEP1 HEEP2 HIMSG1` | host unit tests (g++/CMake/PlatformIO native) against the JSON fixtures in `tests/fixtures/`, expected values taken from `tests/test_parsers.py` / `test_h_parsers.py`; CRC vectors from `test_framing.py` |
| 2 | Scheduler + queue (one in flight, timeout, retry-once for queries, RX flush, gap) | host test with a fake UART script ("first command lost", "late answer", "garbled H answer", "silent command") |
| 3 | Read-only component with all sensors from section 5, `enable_writes` absent | `esphome config` + `esphome compile`; flash; compare with the HA integration side by side (bridge firmware on a second ESP32, or sequentially) |
| 4 | Mixed `Q`+`H` on one line: the first thing to verify on the real unit | log at DEBUG for an hour; zero shifted/garbled answers; compare `HGRID` power with the integration |
| 5 | Derived values (section 7) | compare daily energies and power balance with HA for a full day |
| 6 | Controls, `enable_writes: true`, **owner only** | per control: the owner writes one value, reads it back on the LCD and in `QPIRI`/`QFLAG`/`HEEP1`, then restores it; update the Status column of section 6 and [settings-map.md](settings-map.md) |
| 7 | Hall package stays as is ([hall-current-sensors.md](hall-current-sensors.md)) | I²C on GPIO21/22 does not collide with the UART pins (GPIO25/26 or GPIO16/17) |
| 8 | Docs: promote this plan to [esphome.md](esphome.md) once implemented (what exists now, not the plan) | `update-docs` |

The agent may write steps 1–5 and the code of step 6, and run only host tests and compilation; it never connects to the inverter with a write ([AGENTS.md](../AGENTS.md)). Read-only live checks follow the same allow-list as the integration (`Q…` with CRC and the 14 approved `H…`/`QPRTL` without CRC).

## 9. Open questions and risks

| Item | Status |
|---|---|
| Mixed `Q` and `H` on one line | unverified (step 4) |
| All writes on the GD5548JMH | unverified; some NAK on sibling units (`PSDV`, `PCVV`, `PBFT`) |
| `pvcontroller.yaml` | reviewed in section 10 |
| ESP32 as the only data path: a Wi-Fi/ESP failure loses daily sums | `restore_value` / `total_daily_energy` restore bridges reboots, not outages; HA keeps the recorder history |
| RAM/CPU: ~60 entities + filters on an ESP32 dev board | fine on `esp32dev`; avoid per-sample long `median` windows (the 10 min window at 2 s = 300 floats per sensor) |
| `queue_command()` of `pipsolar` is undocumented | irrelevant for option D, relevant if the owner keeps B for a while |
| Name of the planned component (`voltronic` vs `vevor_inverter`) | owner to choose |

## 10. Starting point: the owner's `pvcontroller.yaml`

The device `pvcontroller` (Denky32 / ESP32-WROOM-32, static IP 192.168.1.70, API + OTA + web server on port 80, `logger: DEBUG`) holds two independent parts:

| Part | What it does | Relation to this plan |
|---|---|---|
| Hall sensors | `packages:` pulls [`esphome/packages/pv-string-current.yaml`](../esphome/packages/pv-string-current.yaml) from this repository's `main` on GitHub (`refresh: 60s`), I²C on GPIO21/22, substitutions for zero trim and send intervals | separate topic ([hall-current-sensors.md](hall-current-sensors.md)); stays unchanged |
| Inverter trial | `uart` on **GPIO25 TX / GPIO26 RX**, 2400 baud; a `globals` string `rx_buf`; one `interval` (5 s) sends `QPIGS` with a hard-coded CRC, a second `interval` (100 ms) collects bytes until CR, strips `(` and the two CRC bytes, splits on spaces and logs battery V, charge A, level % and grid V | this is **step 1–3 of section 8 in embryo**; it is replaced by the component |

What the trial proves: the wiring and level shifter work, the unit answers `QPIGS`, and the field positions are right (`f[0]` grid V, `f[8]` battery V, `f[9]` charge A, `f[10]` level %). The hard-coded CRC bytes `0xB7 0xA9` for `QPIGS` match [`framing.py`](../custom_components/voltronic_solar_inverter/protocol/framing.py) (`crc_bytes(b"QPIGS")` = `b7a9`).

What the trial lacks (all of it is covered by section 3):

| Gap in the trial | Consequence | Fix in the component |
|---|---|---|
| CRC is hard-coded for one command | no other command can be sent | generic `crc16_xmodem` + escaping |
| The answer CRC is dropped, never checked | a shifted or garbled answer is parsed as data | verify the CRC; reject otherwise |
| Sends every 5 s regardless of the answer; no timeout; `rx_buf` is cleared at each send | a late answer (> 5 s) or a lost first command is not handled; a partial answer is discarded | one command in flight, 2 s timeout, retry once, flush after a timeout |
| `rx_buf` has no size limit | line noise without a CR grows the string until the heap is gone | cap the buffer (e.g. 512 bytes) and resync |
| Reads bytes in a 100 ms `interval` | up to 100 ms latency, wakes the loop for nothing | read in the component's `loop()` |
| Result goes to the log only | nothing reaches Home Assistant | sensors, binary sensors, text sensors from section 5 |
| `QPIGS` only | no mode, settings, flags, warnings, H dialect | polling plan of section 4 |

Migration path (keeps the device usable at every step):

1. Keep the file as is, remove only the two `interval` blocks and the `rx_buf` global when the component takes the UART (they would steal its bytes: **one UART owner**).
2. Add the component through the same mechanism already used for the Hall package, so updates arrive the same way:

```yaml
external_components:
  - source:
      type: git
      url: https://github.com/SergeyAnokhin/hacs-voltronic-solar-inverter
      ref: main
      path: esphome/components     # the folder holding voltronic/
    components: [voltronic]
    refresh: 60s                   # local during development: `type: local`, `path: components`
```

3. Point the hub at the existing `uart: id: rs232` (pins stay GPIO25/26). Keep `enable_writes` off until section 8, step 6.
4. Stage the work as in section 8; step 3 already replaces the trial by real entities, so there is no point in extending the `lambda` trial further.

Unrelated notes on the file (not changed): `logger: DEBUG` plus `web_server` costs RAM and CPU on a plain ESP32; consider `INFO` once the component logs its own debug lines under a dedicated tag. The `substitutions:` block sits after `packages:`, which ESPHome accepts.
