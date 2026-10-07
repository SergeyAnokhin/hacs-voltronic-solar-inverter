# Integration Architecture

How the Home Assistant integration in [`custom_components/voltronic_solar_inverter/`](../custom_components/voltronic_solar_inverter/) is built: a protocol layer with no Home Assistant imports (framing for both the PI30 dialect with CRC and the CRC-less Solar Plug "H" dialect, async TCP client, parsers, write commands), two `DataUpdateCoordinator`s that poll it, and entity platforms that map parsed fields to entities. Read entities (sensor, binary_sensor) and write entities (switch, select, number) are always set up; the README warns that changes are at the user's risk. Field meanings live in [inverter-protocol.md](inverter-protocol.md); this doc covers structure and data flow.

## Layers

```text
Elfin gateway (TCP 8899, one client)
   ^  PI30: CMD + CRC + CR / '(' payload CRC CR    H dialect: CMD + CR / '(' payload CR
protocol/client.py    InverterClient: 1 persistent connection, asyncio.Lock,
   |                  read until CR, 2 s timeout, 1 retry for queries, 0.1 s gap,
   |                  reconnect after a timeout (late answers never reach the next
   |                  command); query() = Q + CRC, query_plain() = only
   |                  PLAIN_QUERIES without CRC; write() = ACK/NAK, never retried
protocol/parsers.py   QPIGS/QPIRI/QPIWS/QFLAG/QMOD/QVFW/QM*CHGCR/Q1/QBEQI -> dataclasses
protocol/h_parsers.py HGEN/HEEP1/HEEP2/HTEMP/HGRID/HIMSG1 -> dataclasses
protocol/commands.py  all setting commands (validated WriteCommand builders), allow-lists
   |
coordinator.py        fast: QPIGS + QMOD (+ HGRID)                       default 10 s
   |                  slow: QPIRI + QFLAG + QPIWS, optional QBEQI, Q1    default 60 s
   |                        (+ HEEP1, HEEP2, HGEN, HTEMP)
   |                  required query fails -> UpdateFailed; entities keep their last
   |                  value for MAX_MISSED_UPDATES (5) failures in a row, then unavailable
   |                  (coordinator notifies listeners once at failure 6: HA does not)
   |                  optional query times out/NAK/garbled -> previous field value for
   |                  up to 5 misses, then None -> only its entities unavailable
   |                  (connection errors still fail the update)
__init__.py           read_identity() once (QPI QMN QID QVFW, optional QVFW2 QMCHGCR
   |                  QMUCHGCR, QPRTL without CRC -> H dialect present?, HIMSG1),
   |                  ConfigEntryNotReady if offline; runtime_data = VoltronicRuntimeData
entity platforms      sensor, binary_sensor (+ number, select, switch if controls on)
```

(+ …) = only when `QPRTL` answered at start-up (`identity.h_protocol`, e.g. `HPVINV02`); otherwise those queries are never sent and their entities are not created (`entity.is_supported`). Entity descriptions name the data field they need in `requires`; `VoltronicEntity.available` checks it.

Only answering commands are polled (see "No reply" in [inverter-protocol.md](inverter-protocol.md)); silent ones such as `QT`, `QET`, `QOPPT`, `QBMS` would cost a full timeout each. `QDI` and `HSTS`/`HOP`/`HBAT`/`HPV`/`HPVB`/`HBMS*` are not polled (duplicate data or unknown layout). A slow cycle is 9 commands (~4 s).

⚠ The research sent H and Q queries on separate connections; mixing them on one connection, as the integration does, is not yet verified on the real unit.

## Files

| File | Role |
|---|---|
| [`__init__.py`](../custom_components/voltronic_solar_inverter/__init__.py) | Setup/unload; picks platforms; removes control entities from the registry when controls are off |
| [`config_flow.py`](../custom_components/voltronic_solar_inverter/config_flow.py) | User step (host, port, both intervals; probes `QPI`/`QMN`/`QID`, unique id = serial). Options flow (`OptionsFlowWithReload`): the two intervals and the optional external battery power sensor (`battery_power_sensor`, entity selector, sensor with device class power) |
| [`coordinator.py`](../custom_components/voltronic_solar_inverter/coordinator.py) | `FastData`, `SlowData`, `VoltronicRuntimeData` (incl. the `self_consumption` settings), the two coordinators |
| [`power_balance.py`](../custom_components/voltronic_solar_inverter/power_balance.py) | Power balance (no HA imports): inverter losses, calculated PV power, which self-consumption setting applies, measured defaults |
| [`entity.py`](../custom_components/voltronic_solar_inverter/entity.py) | `VoltronicEntity` (unique id `<serial>_<key>`, device info); `VoltronicControlEntity.async_send()` = the single write path |
| [`sensor.py`](../custom_components/voltronic_solar_inverter/sensor.py), [`binary_sensor.py`](../custom_components/voltronic_solar_inverter/binary_sensor.py) | Read entities, declared as `EntityDescription` tuples with `value_fn` |
| [`switch.py`](../custom_components/voltronic_solar_inverter/switch.py), [`select.py`](../custom_components/voltronic_solar_inverter/select.py), [`number.py`](../custom_components/voltronic_solar_inverter/number.py) | Control entities; `number.py` also holds the three HA-only self-consumption numbers |
| [`diagnostics.py`](../custom_components/voltronic_solar_inverter/diagnostics.py) | Parsed data + last raw payloads; serial, unique id and host redacted |
| [`strings.json`](../custom_components/voltronic_solar_inverter/strings.json) = [`translations/en.json`](../custom_components/voltronic_solar_inverter/translations/en.json) | All UI text (English only; keep the two files identical) |
| [`icons.json`](../custom_components/voltronic_solar_inverter/icons.json) | Icons for entities without a device class |
| [`protocol/`](../custom_components/voltronic_solar_inverter/protocol/) | `framing.py`, `client.py`, `parsers.py` (PI30), `h_parsers.py` (H dialect), `commands.py`, `errors.py` |

## Entities

Per-sensor meaning and formulas of the derived values: [sensors.md](sensors.md). Entity ids are `<domain>.<device name>_<translated name>`, e.g. `sensor.inverter_vmii_4000_grid_voltage`. "Diag" = entity category diagnostic; "off" = disabled by default.

| Group | Entities | Source |
|---|---|---|
| Live sensors (fast) | grid voltage/frequency, AC output voltage/frequency, apparent power (VA), active power (W), load %, battery voltage, charge current, discharge current, battery power (signed, derived V × (I<sub>chg</sub> − I<sub>dis</sub>)), heat-sink temperature, PV current, PV voltage raw (every sample), PV voltage (smoothed, 5 % / 1 V publish thresholds), PV power raw (every sample), PV power (smoothed, see below), PV power median / max (10 min), PV power median / max today, mode (enum incl. `charging` = `QMOD` C, output off; an unknown letter gives state *unknown* and one log warning, the other fast entities stay available); active power also as `_raw`/smoothed pair | `QPIGS` 0–6, 8, 9, 11–13, 15, 19; `QMOD` |
| Live sensors, off | bus voltage (diag), SCC battery voltage (diag), battery level estimate (voltage-based %, **not SOC**) | `QPIGS` 7, 14, 10 |
| Grid power (fast, H) | signed W as `grid_power_raw` + smoothed `grid_power`; positive = import (verified in mode L on 2026-10-05); reads ~16 W + ~2 % low against an external meter | `HGRID[6]` |
| Power balance (fast) | *Inverter losses* (PV `QPIGS[19]` + battery V × (I<sub>dis</sub> − I<sub>chg</sub>) + grid − load) and *PV power calculated* (load + loss model + battery power − grid, ≥ 0; battery power from the optional external sensor, else the inverter's currents); means over 10 min (losses) and 60 s (calculated PV, like *PV power*) with the smoothed publish rules. Unknown in mode L without `HGRID`; grid counts as 0 in other modes without it. See [Power balance](#power-balance-and-self-consumption) | `QPIGS`, `QMOD`, `HGRID[6]`, optional external battery sensor |
| Daily energy (fast) | *Load daily energy* (`load_daily_energy`, AC output power), *Grid daily energy* (`grid_daily_energy`, grid import = max(0, `HGRID[6]`)), *Battery daily energy* (`battery_daily_energy`, battery power V × (I<sub>chg</sub> − I<sub>dis</sub>), + = charged), *Balance daily energy* (`balance_daily_energy`, [`power_balance.net_generation`](../custom_components/voltronic_solar_inverter/power_balance.py): load + battery − grid import − self-consumption of the current mode = PV minus all losses), *PV calculated daily energy* (`pv_calculated_daily_energy`, integral of the unsmoothed *PV power calculated*, `total_increasing`; with the external battery sensor; `uses_battery_sensor` skips samples while it is unusable). kWh, 2 decimals; battery and balance may be negative: `state_class` `total` + `last_reset` = local midnight, the other two `total_increasing`; grid and balance only with `HGRID`. See [Daily energy](#daily-energy) | `QPIGS` 5, 8, 9, 15; `HGRID[6]`, self-consumption numbers |
| PV energy (slow, H) | today, this month, this year, total (kWh, `total_increasing`; the inverter's own counters, match the vendor app) | `HGEN` 2–5 |
| Schedules (slow, H) | AC output on / off time (P48/P49, verified), AC charger start / stop time (P46/P47, verified), shown as `HH:00` | `HEEP2[12]`, `HEEP2[11]` |
| Clock (diag, slow, H) | inverter clock (timestamp, inverter local time interpreted in HA's time zone), clock offset (min, inverter − HA; ~ −10 on the test unit) | `HGEN` 0–1 |
| Temperatures (slow, H) | inverter, transformer, PV temperature; diag: fan 1 / fan 2 speed %. Boost temperature = the heat-sink sensor | `HTEMP` 0, 2, 3, 5, 6 |
| Other settings (diag, slow) | solar supply priority P43 (battery first / load first, verified), battery low-alarm voltage P24, charge stage (`Q1[17]`: idle/bulk verified, absorb/float generic), equalization voltage / time / timeout / interval + binary enabled / active; off: second-output cut-off voltage, recover voltage, recover delay, BMS shutdown SOC (P38), BMS back-to-battery SOC (P40), grid-tie current (P56), firmware date | `HEEP1`, `HEEP2`, `Q1`, `QBEQI`, `HIMSG1` |
| Settings / ratings (diag, slow) | rated output V/Hz/VA/W, battery rating V, float voltage, battery type, AC input range (enums carry a `code` attribute). **Not created while a control entity shows the same value** (`CONTROL_DUPLICATE_KEYS` in `const.py`, rule in `sensor._duplicates_control`): output/charger/solar-supply priority, max (utility) charging current, back-to-utility / back-to-battery / cut-off / bulk voltage (only when battery rating = 24 V, i.e. the numbers exist). Stale registry entries are removed at setup (`entity.remove_entities`; dropped sensors such as `pv_power_median_today` are listed in `REMOVED_KEYS` in `const.py` and removed the same way); off: grid rating V/A, rated output current, machine type, topology, output mode | `QPIRI` |
| Identity (diag) | serial number, firmware version; off: SCC firmware, protocol | `QID`, `QVFW`, `QVFW2`, `QPI` |
| Binary (fast) | AC output (`QMOD` ∈ L/B; unknown when the `QMOD` letter is not in `DEVICE_MODES`), load on (b4), charging (b2), solar charging (b1), grid charging (b0); off: charging to float (status2 b10) | `QMOD`, `QPIGS` 16/20 |
| Binary (slow) | SBU priority (`QPIRI[16]` = 1), fault (any fault bit or `QMOD` = F; attribute `faults`), warning (any warning bit; attribute `warnings`; a0 ignored) | `QPIRI`, `QPIWS`, `QMOD` |
| Binary, `QPIWS` bits (diag) | one problem sensor per bit a1–a30 except a13; on by default: grid lost (a5), battery low (a12), battery under-voltage shutdown (a14), overload (a16), over-temperature (a9) | `QPIWS` |
| ~~Binary, `QFLAG`~~ | removed in 0.4.0: the nine flags are shown only by the switches | `QFLAG` |

### Control entities

| Entity | Command | Values offered | Status |
|---|---|---|---|
| 9 switches (one per `QFLAG` flag, entity category config) | `PE<x>` / `PD<x>` (x = a, b, j, k, u, v, x, y, z) | on/off | unverified on this unit |
| Select: output source priority | `POP<NN>` | only SBU (code 01) | code 1 = SBU confirmed for `QPIRI`; that `POP01` sets SBU is **unverified** |
| Select: charger source priority | `PCP<NN>` | only "Only solar" (code 02) | same caveat (`PCP02`) |
| Select: solar supply priority (P43, needs the H dialect to read) | `PVENGUSE00` battery first (BLU) / `PVENGUSE01` load first (LBU) | both | read codes verified by the owner; command ACKed + read back on the sibling VMII-6200; unverified here |
| Number: max charging current | `MNCHGC<nnn>` | values from `QMCHGCR` (10…80 A, step 10) | ACKed + read back on the sibling VMII-6200; unverified here |
| Number: max utility charging current | `MUCHGC<nnn>` | values from `QMUCHGCR` (2, 10…60 A) | unverified |
| Numbers: back to utility / back to battery / cut-off / bulk voltage | `PBCV` / `PBDV` / `PSDV` / `PCVV` `<nn.n>` | 22.0–25.5 step 0.5 / 24.0–29.0 step 0.5 / 20.0–26.0 step 0.1 / 24.0–30.0 step 0.1 | created only if battery rating = 24 V; ranges from the Vevor manual; unverified (`PBCV`/`PBDV` ACKed on the sibling; `PSDV` NAKed there, `PCVV` "not supported" there) |

**HA-only numbers (config, never sent to the inverter):** *Self-consumption (battery mode / line mode / output off)*, 0–500 W, restored after a restart (`RestoreNumber`), read by the daily energy balance (not by *PV power calculated* since 0.4.7). Defaults 0 / 16 / 13 W (owner's measurement, see below).

Codes not confirmed by the owner (output priority 0 "solar first (SUB)", 2 "utility first"; charger priority 0 "solar first", 1 "solar and utility") are rejected by the builders and not offered in the selects. To publish one after the owner confirms it, add the code to `OUTPUT_SOURCE_PRIORITIES_VERIFIED` / `CHARGER_SOURCE_PRIORITIES_VERIFIED` in [`parsers.py`](../custom_components/voltronic_solar_inverter/protocol/parsers.py) and add the `select` state string.

**Not implemented as writes:** float voltage `PBFT` (range undocumented, NAK on the sibling), battery low-alarm voltage (no known command), equalization `PBEQ*` (read-only on purpose: equalizing a LiFePO4 bank is harmful), battery type `PBT` (may overwrite P26/P27/P29), input range `PGR`, clock `DAT`, dual output `PTOP*`, feed-in `PEd`, PV energy reset `RTEY`, and the P46–P49 schedules / AC output on-off (no known command: the schedules are only **read**, via `HEEP2`). Full per-program list: [settings-map.md](settings-map.md).

### Write path

```text
service call -> entity -> VoltronicControlEntity.async_send(build)
  build() -> commands.*  (InvalidCommandError -> ServiceValidationError, nothing sent)
  client.write(cmd)       ACK -> slow coordinator async_refresh()
                          NAK -> HomeAssistantError "command_rejected"
                          timeout/connection -> HomeAssistantError "command_failed" (never retried)
```

### Fast and slow groups

Fast coordinator (default 10 s): live values — the sensors/binary sensors from `QPIGS`, `QMOD`, `HGRID` (voltages, currents, powers and their smoothed/median/max variants, temperatures of the heat sink, mode, charging bits). Slow coordinator (default 60 s): everything that changes rarely — ratings, settings, `QFLAG` flags, `QPIWS` warnings/faults, PV energy counters, schedules, clock, temperatures/fans (`HTEMP`), charge stage, equalization. Every sensor and binary sensor of the slow group carries the attribute `update_group: slow` (`ATTR_UPDATE_GROUP` in `const.py`); fast ones have none.

### Raw / smoothed pairs and registry defaults

- Whole-state rounding: descriptions carry `precision`; `sensor._round` rounds the native value, so the recorder sees only rounded values (default 1 decimal for voltages, 0 for mains voltages `grid_voltage`/`ac_output_voltage` and their ratings, 0 for all currents).
- `<x>_raw` sensors publish every sample (meant for live cards and to be excluded from the recorder); the plain `<x>` sensor ([`VoltronicSmoothedSensor`](../custom_components/voltronic_solar_inverter/sensor.py)) shows the mean of the last 60 s and calls `async_write_ha_state()` only when [`smoothing.SmoothedValue`](../custom_components/voltronic_solar_inverter/smoothing.py) publishes: change ≥ 10 % and ≥ 20 W, a drop to 0, or 10 min since the last publish with any change (constants `SMOOTHING_*` in [`const.py`](../custom_components/voltronic_solar_inverter/const.py)). Availability changes are always written. Pairs: PV power (`QPIGS[19]`), grid power (`HGRID[6]`), AC output active power. Add more by putting a description in `SMOOTHED_SENSORS` (and renaming the live one to `<x>_raw`; the old key then becomes the smoothed sensor, so its history stays). `pv_power_median_10min` / `pv_power_max_10min` are `SMOOTHED_SENSORS` entries with `smoothing_window=600` and `smoothing_statistic` `median` / `max` (there is no daily median: removed in 0.4.6, see the decision log). The AC output active power is named *Load power* (key `ac_output_active_power`). `pv_power_max_today` ([`VoltronicDailyMaxSensor`](../custom_components/voltronic_solar_inverter/sensor.py), `smoothing.DailyMax`) writes only when the maximum rises, resets on the first sample of a new local day and restores its value after a restart on the same day. `DAILY_MAX_SENSORS` also has `pv_input_current_max_today`, `battery_charge_current_max_today`, `battery_discharge_current_max_today` (`QPIGS` 12 / 9 / 15; entity ids follow the names, e.g. `…_pv_current_max_today`); all of them expose the attribute `max_time` (ISO local time, seconds, of the first sample that reached the maximum; restored with the state). The inverter has no measured grid input or AC output current.
- `HIDDEN_KEYS` (ratings, identity) are created hidden; `DISABLED_KEYS` (equalization) are created disabled; both in `const.py`.
- Config entry **1.2** (`async_migrate_entry` in [`__init__.py`](../custom_components/voltronic_solar_inverter/__init__.py)) applies the same defaults to entities created before, unless the user already hid/disabled them, and renames `pv_charging_power` → `pv_power` (same registry entry, so the recorder keeps the history). Registry defaults alone never touch existing entities.

### Power balance and self-consumption

```text
PV + battery discharge + grid import = load + battery charge + inverter consumption
```

The self-consumption numbers hold the part of the inverter's own consumption that **its sensors do not show**, not its total draw. The setting used is picked by [`power_balance.self_consumption_key`](../custom_components/voltronic_solar_inverter/power_balance.py): output off (`QPIGS` status 2 b9 = 0, i.e. modes S/C) → *output off*; mode L → *line mode*; otherwise *battery mode*. Measured on the owner's VMII-4000 on 2026-10-05 with an external meter on the AC input (log: [`tests/fixtures/balance_log_2026-10-05_night.csv`](../tests/fixtures/balance_log_2026-10-05_night.csv), tool: [`tools/balance_logger.py`](../tools/balance_logger.py)):

| State (no load) | Real draw (meter) | Inverter shows | Default |
|---|---|---|---|
| Output off (S), grid present | 13 W | `HGRID` 0 W | 13 W |
| Line mode (L), output on, charger flagged on with 0 A | 40–45 W | `HGRID` ~25 W | 16 W |
| Line mode, 1.3 kW load | ~1350 W input | `HGRID` ~1308 W, load ~1280 W | (16 W + ~2 %) |
| Battery mode (B), night | 50 W + 3.5 % of the load from the battery (BMS) | battery current × V ≈ 1.03 × BMS | 0 W (see below) |

Single samples are noisy (battery currents are whole amperes, ~25 W on 24 V), hence the 10 min mean.

**History check (2026-10-06, ~4 days of the owner's recorder database, 10 min bins, BMS = battery meter, meter = AC input meter; see [local-data.md](local-data.md)):**

| Finding | Value |
|---|---|
| Line mode, battery idle | meter = 16.9 W + 1.029 × `HGRID` (sd 4 W); `HGRID` = load + 28 W + 1 % (sd 5 W); total own draw = 46.6 W + 1.3 % of load. Confirms the night test |
| Output off (S) | meter median 12.5 W, `HGRID` 0 |
| Modes B and C | meter ~3 W: the inverter still draws ~3 W from the grid while running from battery / PV |
| Battery mode, night | true losses (BMS out − load) = 50.2 W + 3.45 % of load (sd 5 W, load 136–1145 W); inverter's battery power = 1.03 × BMS |
| Battery mode, daylight, `QPIGS[19]` low | the inverter's discharge current stays at its own DC draw (load + losses) while the BMS shows less: PV ≈ load + losses + BMS power is **~85–95 W above `QPIGS[19]`** for reported 0–200 W, ~45–60 W above at 600–870 W; reported 0 W with ~30–90 W real is common in the morning and afternoon. Daily PV energy in these bins: reported 1.2–1.5 kWh vs ~1.7–2.1 kWh |
| Mode C (output off, PV charging) | BMS charge ≈ `QPIGS[19]` + 30–40 W |
| Line mode, AC charger | outside the P46/P47 window the charger is flagged on with 0 A (not a BMS block); inside (01–02) it charges 2.0 A by the inverter, 1.8 A by the BMS |
| `QPIGS[12]` × `[13]` | = `QPIGS[19]` within 1 % (no extra information; the integration rounds the PV current to whole amperes) |

Consequence (implemented in 0.4.7): *PV power calculated* = load + `LOSS_MODEL` (50 W + 3.5 % of load in mode B, 28 W + 1 % in mode L, 31 W output off in mode C, 0 in standby; [`power_balance.py`](../custom_components/voltronic_solar_inverter/power_balance.py)) + battery power (+ = charging) − grid. With the inverter's currents it stays near the reported PV, because in daylight the inverter's discharge current already contains the PV shortfall. With the options' external battery sensor (e.g. the BMS) it shows the hidden PV. The sensor state is read on every fast poll (W or kW); an unusable state skips the sample (no fallback to the inverter's currents, which would make the mean jump). A BMS that freezes (as on 2026-10-06 11:00–16:30, constant 97 W) is not detected.

**Output off, charging from PV (mode C), 2026-10-07** (a dull day, load disconnected, grid connected; history check): the inverter drew 3 W from the grid all day (12 W in standby at night). At dusk, with the PV voltage stuck at 60 V and PV gone, the BMS showed **−31 W** for 40 min while `QPIGS` showed 0 everywhere; before that, weak PV covered exactly those 31 W, so battery, PV and grid all read 0 while the inverter kept running (the owner's clamp meter: ~0.5 A on the PV cable ≈ 30 W at 60 V). `QPIGS[19]` = BMS charge − 37 W (sd 7 W), i.e. the reported PV is *smaller than what reaches the battery*, and ~68 W below the real PV. The inverter's charge current read 1.10 × the BMS. Day totals: inverter PV counter (`HGEN`) 0.27 kWh, BMS charge 0.46 kWh (SOC 9 → 27 %), real PV ≈ BMS + 31 W × 10.8 h ≈ 0.77 kWh. Hence `LOSS_MODEL` mode C = 31 W (0.4.8).

`HGRID` answers have no CRC: since 0.4.7 [`parse_hgrid_power`](../custom_components/voltronic_solar_inverter/protocol/h_parsers.py) rejects an answer whose first field is not a voltage (0–300 V), whose power has no sign, or whose power exceeds ±20 kW (`MAX_GRID_POWER_W`); the coordinator then keeps the last value (optional-field grace). This blocks foreign answers like the 710 000 W sample of 2026-10-05.

### Daily energy

[`VoltronicDailyEnergySensor`](../custom_components/voltronic_solar_inverter/sensor.py) (`DAILY_ENERGY_SENSORS`, `VoltronicEnergySensorDescription.power_fn(data, self_consumption)`) feeds every fast sample to [`smoothing.DailyEnergy`](../custom_components/voltronic_solar_inverter/smoothing.py): trapezoidal rule (the default method of HA's Riemann sum *Integral* helper; that helper is not an importable API, so the few lines are re-implemented), kWh, reset on the first sample of a new local day. Raw samples are integrated, not the smoothed sensors: the recorded smoothed value may lag the real mean by up to 10 % for up to 10 min, which would bias the sum. Writes are thinned instead: a new state when the rounded value (0.01 kWh) moved by ≥ `ENERGY_STEP_KWH` (0.05), after `SMOOTHING_HEARTBEAT` (10 min) with any change, or on a new day. An interval longer than `ENERGY_MAX_GAP_INTERVALS` (3) × the fast interval adds nothing (outage, failed updates, restart); a missing value (`None`) breaks the interval. The value is restored after a restart if the last state was written today (`RestoreEntity`).

```text
fast sample (W) --> DailyEnergy.add(day, monotonic, W)
                      total += (W_prev + W) / 2 * dt / 3.6e6   if 0 < dt <= max_gap
                      write state if |rounded - published| >= 0.05 kWh or 10 min passed or new day
```

## How to add a read entity

1. Make sure the field is parsed in [`parsers.py`](../custom_components/voltronic_solar_inverter/protocol/parsers.py) (add a dataclass field + a test in [`tests/test_parsers.py`](../tests/test_parsers.py) against a fixture).
2. Add an `EntityDescription` with a `value_fn` to the right tuple in `sensor.py` / `binary_sensor.py` (fast = `QPIGS`/`QMOD`/`HGRID`, slow = everything else). If the field comes from an optional query, set `requires="<data field>"`. Unconfirmed fields: `entity_registry_enabled_default=False`, diagnostic.
3. Add its name (and enum states) under `entity.<platform>.<translation_key>` in `strings.json` and copy the file to `translations/en.json`.
4. A new command must be an answering one; add it to a coordinator's `_fetch` (wrapped in `_optional()` unless every supported inverter answers it) and to the poll list in this doc. A new H query must also be owner-approved and added to `PLAIN_QUERIES`.

## Logging

Logger `custom_components.voltronic_solar_inverter` (the client logs under `….protocol.client`). Home Assistant itself logs the first failed update of each coordinator at ERROR ("Error fetching voltronic_solar_inverter fast data: …") and the recovery at INFO. At DEBUG the integration adds: every failed update with its count and whether entities were kept, recoveries, failed optional queries per field, retries, connect / reconnect / close of the gateway connection, discarded stale bytes.

## Tests

See README "Development". Protocol tests run with plain `pytest`; [`tests/test_ha_integration.py`](../tests/test_ha_integration.py) (config flow, entities, control entities with a fake gateway, diagnostics) needs `pytest-homeassistant-custom-component`. Home Assistant does not support Windows: there the HA tests need Python ≥ 3.14, a venv path short enough for `MAX_PATH`, and local stubs for `fcntl`/`resource` plus a `socket.socketpair` shim; on Linux/WSL/CI they run as is. A ready Windows venv on the owner's PC: `%TEMP%si-ha` (Python 3.14); put a folder with `fcntl.py` (no-op `flock`/`fcntl`/`ioctl`), `resource.py` (`getrlimit`/`setrlimit`) and a `sitecustomize.py` on `PYTHONPATH`, where `sitecustomize` replaces `socket.socketpair` with a version that keeps a reference to the original `socket.socket` class and uses `lsock._accept()` (pytest-socket blocks AF_INET sockets created later).
