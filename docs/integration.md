# Integration Architecture

How the Home Assistant integration in [`custom_components/voltronic_solar_inverter/`](../custom_components/voltronic_solar_inverter/) is built: a protocol layer with no Home Assistant imports (framing for both the PI30 dialect with CRC and the CRC-less Solar Plug "H" dialect, async TCP client, parsers, write commands), two `DataUpdateCoordinator`s that poll it, and entity platforms that map parsed fields to entities. Read entities (sensor, binary_sensor) and write entities (switch, select, number) are always set up; the README warns that changes are at the user's risk. Field meanings live in [inverter-protocol.md](inverter-protocol.md); this doc covers structure and data flow.

## Layers

```text
Elfin gateway (TCP 8899, one client)
   ^  PI30: CMD + CRC + CR / '(' payload CRC CR    H dialect: CMD + CR / '(' payload CR
protocol/client.py    InverterClient: 1 persistent connection, asyncio.Lock,
   |                  read until CR, 2 s timeout, 1 retry for queries, 0.1 s gap,
   |                  transparent reconnect; query() = Q + CRC, query_plain() = only
   |                  PLAIN_QUERIES without CRC; write() = ACK/NAK, never retried
protocol/parsers.py   QPIGS/QPIRI/QPIWS/QFLAG/QMOD/QVFW/QM*CHGCR/Q1/QBEQI -> dataclasses
protocol/h_parsers.py HGEN/HEEP1/HEEP2/HTEMP/HGRID/HIMSG1 -> dataclasses
protocol/commands.py  all setting commands (validated WriteCommand builders), allow-lists
   |
coordinator.py        fast: QPIGS + QMOD (+ HGRID)                       default 10 s
   |                  slow: QPIRI + QFLAG + QPIWS, optional QBEQI, Q1    default 60 s
   |                        (+ HEEP1, HEEP2, HGEN, HTEMP)
   |                  required query fails -> UpdateFailed -> all entities unavailable
   |                  optional query times out/NAK/garbled -> field None -> only its
   |                  entities unavailable (connection errors still fail the update)
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
| [`config_flow.py`](../custom_components/voltronic_solar_inverter/config_flow.py) | User step (host, port, both intervals; probes `QPI`/`QMN`/`QID`, unique id = serial). Options flow (`OptionsFlowWithReload`): the two intervals |
| [`coordinator.py`](../custom_components/voltronic_solar_inverter/coordinator.py) | `FastData`, `SlowData`, `VoltronicRuntimeData`, the two coordinators |
| [`entity.py`](../custom_components/voltronic_solar_inverter/entity.py) | `VoltronicEntity` (unique id `<serial>_<key>`, device info); `VoltronicControlEntity.async_send()` = the single write path |
| [`sensor.py`](../custom_components/voltronic_solar_inverter/sensor.py), [`binary_sensor.py`](../custom_components/voltronic_solar_inverter/binary_sensor.py) | Read entities, declared as `EntityDescription` tuples with `value_fn` |
| [`switch.py`](../custom_components/voltronic_solar_inverter/switch.py), [`select.py`](../custom_components/voltronic_solar_inverter/select.py), [`number.py`](../custom_components/voltronic_solar_inverter/number.py) | Control entities |
| [`diagnostics.py`](../custom_components/voltronic_solar_inverter/diagnostics.py) | Parsed data + last raw payloads; serial, unique id and host redacted |
| [`strings.json`](../custom_components/voltronic_solar_inverter/strings.json) = [`translations/en.json`](../custom_components/voltronic_solar_inverter/translations/en.json) | All UI text (English only; keep the two files identical) |
| [`icons.json`](../custom_components/voltronic_solar_inverter/icons.json) | Icons for entities without a device class |
| [`protocol/`](../custom_components/voltronic_solar_inverter/protocol/) | `framing.py`, `client.py`, `parsers.py` (PI30), `h_parsers.py` (H dialect), `commands.py`, `errors.py` |

## Entities

Entity ids are `<domain>.<device name>_<translated name>`, e.g. `sensor.inverter_vmii_4000_grid_voltage`. "Diag" = entity category diagnostic; "off" = disabled by default.

| Group | Entities | Source |
|---|---|---|
| Live sensors (fast) | grid voltage/frequency, AC output voltage/frequency, apparent power (VA), active power (W), load %, battery voltage, charge current, discharge current, battery power (signed, derived V × (I<sub>chg</sub> − I<sub>dis</sub>)), heat-sink temperature, PV current, PV voltage, PV power raw (every sample), PV power (smoothed, see below), PV power median / max (10 min), PV power median / max today, mode (enum); active power also as `_raw`/smoothed pair | `QPIGS` 0–6, 8, 9, 11–13, 15, 19; `QMOD` |
| Live sensors, off | bus voltage (diag), SCC battery voltage (diag), battery level estimate (voltage-based %, **not SOC**) | `QPIGS` 7, 14, 10 |
| Grid power (fast, H) | signed W as `grid_power_raw` + smoothed `grid_power`; sign convention not verified yet | `HGRID[6]` |
| PV energy (slow, H) | today, this month, this year, total (kWh, `total_increasing`; the inverter's own counters, match the vendor app) | `HGEN` 2–5 |
| Schedules (slow, H) | AC output on / off time (P48/P49, verified), AC charger start / stop time (P46/P47, verified), shown as `HH:00` | `HEEP2[12]`, `HEEP2[11]` |
| Clock (diag, slow, H) | inverter clock (timestamp, inverter local time interpreted in HA's time zone), clock offset (min, inverter − HA; ~ −10 on the test unit) | `HGEN` 0–1 |
| Temperatures (slow, H) | inverter, transformer, PV temperature; diag: fan 1 / fan 2 speed %. Boost temperature = the heat-sink sensor | `HTEMP` 0, 2, 3, 5, 6 |
| Other settings (diag, slow) | solar supply priority P43 (battery first / load first, verified), battery low-alarm voltage P24, charge stage (`Q1[17]`: idle/bulk verified, absorb/float generic), equalization voltage / time / timeout / interval + binary enabled / active; off: second-output cut-off voltage, recover voltage, recover delay, BMS shutdown SOC (P38), BMS back-to-battery SOC (P40), grid-tie current (P56), firmware date | `HEEP1`, `HEEP2`, `Q1`, `QBEQI`, `HIMSG1` |
| Settings / ratings (diag, slow) | rated output V/Hz/VA/W, battery rating V, float voltage, battery type, AC input range (enums carry a `code` attribute). **Not created while a control entity shows the same value** (`CONTROL_DUPLICATE_KEYS` in `const.py`, rule in `sensor._duplicates_control`): output/charger/solar-supply priority, max (utility) charging current, back-to-utility / back-to-battery / cut-off / bulk voltage (only when battery rating = 24 V, i.e. the numbers exist). Stale registry entries are removed at setup (`entity.remove_entities`); off: grid rating V/A, rated output current, machine type, topology, output mode | `QPIRI` |
| Identity (diag) | serial number, firmware version; off: SCC firmware, protocol | `QID`, `QVFW`, `QVFW2`, `QPI` |
| Binary (fast) | AC output (`QMOD` ∈ L/B), load on (b4), charging (b2), solar charging (b1), grid charging (b0); off: charging to float (status2 b10) | `QMOD`, `QPIGS` 16/20 |
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
- `<x>_raw` sensors publish every sample (meant for live cards and to be excluded from the recorder); the plain `<x>` sensor ([`VoltronicSmoothedSensor`](../custom_components/voltronic_solar_inverter/sensor.py)) shows the mean of the last 60 s and calls `async_write_ha_state()` only when [`smoothing.SmoothedValue`](../custom_components/voltronic_solar_inverter/smoothing.py) publishes: change ≥ 10 % and ≥ 20 W, a drop to 0, or 10 min since the last publish with any change (constants `SMOOTHING_*` in [`const.py`](../custom_components/voltronic_solar_inverter/const.py)). Availability changes are always written. Pairs: PV power (`QPIGS[19]`), grid power (`HGRID[6]`), AC output active power. Add more by putting a description in `SMOOTHED_SENSORS` (and renaming the live one to `<x>_raw`; the old key then becomes the smoothed sensor, so its history stays). `pv_power_median_10min` / `pv_power_max_10min` are `SMOOTHED_SENSORS` entries with `smoothing_window=600` and `smoothing_statistic` `median` / `max`; `pv_power_median_today` uses `smoothing_daily=True` (window = whole local day, `SmoothedValue.add(..., day)` restarts on a new day; not restored after a restart). The AC output active power is named *Load power* (key `ac_output_active_power`). `pv_power_max_today` ([`VoltronicDailyMaxSensor`](../custom_components/voltronic_solar_inverter/sensor.py), `smoothing.DailyMax`) writes only when the maximum rises, resets on the first sample of a new local day and restores its value after a restart on the same day.
- `HIDDEN_KEYS` (ratings, identity) are created hidden; `DISABLED_KEYS` (equalization) are created disabled; both in `const.py`.
- Config entry **1.2** (`async_migrate_entry` in [`__init__.py`](../custom_components/voltronic_solar_inverter/__init__.py)) applies the same defaults to entities created before, unless the user already hid/disabled them, and renames `pv_charging_power` → `pv_power` (same registry entry, so the recorder keeps the history). Registry defaults alone never touch existing entities.

## How to add a read entity

1. Make sure the field is parsed in [`parsers.py`](../custom_components/voltronic_solar_inverter/protocol/parsers.py) (add a dataclass field + a test in [`tests/test_parsers.py`](../tests/test_parsers.py) against a fixture).
2. Add an `EntityDescription` with a `value_fn` to the right tuple in `sensor.py` / `binary_sensor.py` (fast = `QPIGS`/`QMOD`/`HGRID`, slow = everything else). If the field comes from an optional query, set `requires="<data field>"`. Unconfirmed fields: `entity_registry_enabled_default=False`, diagnostic.
3. Add its name (and enum states) under `entity.<platform>.<translation_key>` in `strings.json` and copy the file to `translations/en.json`.
4. A new command must be an answering one; add it to a coordinator's `_fetch` (wrapped in `_optional()` unless every supported inverter answers it) and to the poll list in this doc. A new H query must also be owner-approved and added to `PLAIN_QUERIES`.

## Tests

See README "Development". Protocol tests run with plain `pytest`; [`tests/test_ha_integration.py`](../tests/test_ha_integration.py) (config flow, entities, control entities with a fake gateway, diagnostics) needs `pytest-homeassistant-custom-component`. Home Assistant does not support Windows: there the HA tests need Python ≥ 3.14, a venv path short enough for `MAX_PATH`, and local stubs for `fcntl`/`resource` plus a `socket.socketpair` shim; on Linux/WSL/CI they run as is.
