# Integration Architecture

How the Home Assistant integration in [`custom_components/voltronic_solar_inverter/`](../custom_components/voltronic_solar_inverter/) is built: a protocol layer with no Home Assistant imports (framing, async TCP client, parsers, write commands), two `DataUpdateCoordinator`s that poll it, and entity platforms that map parsed fields to entities. Read-only entities (sensor, binary_sensor) are always set up; write entities (switch, select, number) only when the **Enable control entities** option is on (default off). Field meanings live in [inverter-protocol.md](inverter-protocol.md); this doc covers structure and data flow.

## Layers

```text
Elfin gateway (TCP 8899, one client)
   ^  frames: CMD + CRC + CR / '(' payload CRC CR
protocol/client.py   InverterClient: 1 persistent connection, asyncio.Lock,
   |                 read until CR, CRC check, 2 s timeout, 1 retry for Q queries,
   |                 0.1 s gap, transparent reconnect; write() = ACK/NAK, no retry
protocol/parsers.py  QPIGS/QPIRI/QPIWS/QFLAG/QMOD/QVFW/QM*CHGCR -> dataclasses
protocol/commands.py all setting commands (validated WriteCommand builders)
   |
coordinator.py       fast: QPIGS + QMOD (default 10 s)
   |                 slow: QPIRI + QFLAG + QPIWS (default 60 s)
   |                 InverterError -> UpdateFailed -> entities unavailable
__init__.py          read_identity() once (QPI QMN QID QVFW QVFW2 QMCHGCR QMUCHGCR),
   |                 ConfigEntryNotReady if offline; runtime_data = VoltronicRuntimeData
entity platforms     sensor, binary_sensor (+ number, select, switch if controls on)
```

Only answering commands are polled (see "No reply" in [inverter-protocol.md](inverter-protocol.md)); silent ones such as `QT`, `QET`, `QOPPT`, `QBMS` would cost a full timeout each. `Q1`, `QDI`, `QBEQI` are not polled yet.

## Files

| File | Role |
|---|---|
| [`__init__.py`](../custom_components/voltronic_solar_inverter/__init__.py) | Setup/unload; picks platforms; removes control entities from the registry when controls are off |
| [`config_flow.py`](../custom_components/voltronic_solar_inverter/config_flow.py) | User step (host, port, both intervals; probes `QPI`/`QMN`/`QID`, unique id = serial). Options flow (`OptionsFlowWithReload`): intervals + `enable_controls` |
| [`coordinator.py`](../custom_components/voltronic_solar_inverter/coordinator.py) | `FastData`, `SlowData`, `VoltronicRuntimeData`, the two coordinators |
| [`entity.py`](../custom_components/voltronic_solar_inverter/entity.py) | `VoltronicEntity` (unique id `<serial>_<key>`, device info); `VoltronicControlEntity.async_send()` = the single write path |
| [`sensor.py`](../custom_components/voltronic_solar_inverter/sensor.py), [`binary_sensor.py`](../custom_components/voltronic_solar_inverter/binary_sensor.py) | Read entities, declared as `EntityDescription` tuples with `value_fn` |
| [`switch.py`](../custom_components/voltronic_solar_inverter/switch.py), [`select.py`](../custom_components/voltronic_solar_inverter/select.py), [`number.py`](../custom_components/voltronic_solar_inverter/number.py) | Control entities |
| [`diagnostics.py`](../custom_components/voltronic_solar_inverter/diagnostics.py) | Parsed data + last raw payloads; serial, unique id and host redacted |
| [`strings.json`](../custom_components/voltronic_solar_inverter/strings.json) = [`translations/en.json`](../custom_components/voltronic_solar_inverter/translations/en.json) | All UI text (English only; keep the two files identical) |
| [`icons.json`](../custom_components/voltronic_solar_inverter/icons.json) | Icons for entities without a device class |
| [`protocol/`](../custom_components/voltronic_solar_inverter/protocol/) | `framing.py`, `client.py`, `parsers.py`, `commands.py`, `errors.py` |

## Entities

Entity ids are `<domain>.<device name>_<translated name>`, e.g. `sensor.inverter_vmii_4000_grid_voltage`. "Diag" = entity category diagnostic; "off" = disabled by default.

| Group | Entities | Source |
|---|---|---|
| Live sensors (fast) | grid voltage/frequency, AC output voltage/frequency, apparent power (VA), active power (W), load %, battery voltage, charge current, discharge current, battery power (signed, derived V × (I<sub>chg</sub> − I<sub>dis</sub>)), heat-sink temperature, PV current, PV voltage, PV charging power, mode (enum) | `QPIGS` 0–6, 8, 9, 11–13, 15, 19; `QMOD` |
| Live sensors, off | bus voltage (diag), SCC battery voltage (diag), battery level estimate (voltage-based %, **not SOC**) | `QPIGS` 7, 14, 10 |
| Settings / ratings (diag, slow) | rated output V/Hz/VA/W, battery rating V, back-to-utility, back-to-battery, cut-off, bulk, float voltages, max charging current, max utility charging current, output source priority, charger source priority, battery type, AC input range (enums carry a `code` attribute); off: grid rating V/A, rated output current, machine type, topology, output mode | `QPIRI` |
| Identity (diag) | serial number, firmware version; off: SCC firmware, protocol | `QID`, `QVFW`, `QVFW2`, `QPI` |
| Binary (fast) | AC output (`QMOD` ∈ L/B), load on (b4), charging (b2), solar charging (b1), grid charging (b0); off: charging to float (status2 b10) | `QMOD`, `QPIGS` 16/20 |
| Binary (slow) | SBU priority (`QPIRI[16]` = 1), fault (any fault bit or `QMOD` = F; attribute `faults`), warning (any warning bit; attribute `warnings`; a0 ignored) | `QPIRI`, `QPIWS`, `QMOD` |
| Binary, `QPIWS` bits (diag) | one problem sensor per bit a1–a30 except a13; on by default: grid lost (a5), battery low (a12), battery under-voltage shutdown (a14), overload (a16), over-temperature (a9) | `QPIWS` |
| Binary, `QFLAG` (diag) | buzzer, overload bypass, power saving, return to default LCD screen, auto restart on overload / over-temperature, LCD backlight, beep on primary source interrupt, record fault codes | `QFLAG` |

### Control entities (only with "Enable control entities")

| Entity | Command | Values offered | Status |
|---|---|---|---|
| 9 switches (one per `QFLAG` flag, entity category config) | `PE<x>` / `PD<x>` (x = a, b, j, k, u, v, x, y, z) | on/off | unverified on this unit |
| Select: output source priority | `POP<NN>` | only SBU (code 01) | code 1 = SBU confirmed for `QPIRI`; that `POP01` sets SBU is **unverified** |
| Select: charger source priority | `PCP<NN>` | only "Only solar" (code 02) | same caveat (`PCP02`) |
| Number: max charging current | `MCHGC0<nn>` | values from `QMCHGCR` (10…80 A, step 10) | unverified |
| Number: max utility charging current | `MUCHGC<nnn>` | values from `QMUCHGCR` (2, 10…60 A) | unverified |
| Numbers: back to utility / back to battery / cut-off / bulk voltage | `PBCV` / `PBDV` / `PSDV` / `PCVV` `<nn.n>` | 22.0–25.5 step 0.5 / 24.0–29.0 step 0.5 / 20.0–26.0 step 0.1 / 24.0–30.0 step 0.1 | created only if battery rating = 24 V; ranges from the Vevor manual; unverified |

Codes not confirmed by the owner (output priority 0 "solar first", 2 "battery first"; charger priority 0 "solar first", 1 "solar and utility") are rejected by the builders and not offered in the selects. To publish one after the owner confirms it, add the code to `OUTPUT_SOURCE_PRIORITIES_VERIFIED` / `CHARGER_SOURCE_PRIORITIES_VERIFIED` in [`parsers.py`](../custom_components/voltronic_solar_inverter/protocol/parsers.py) and add the `select` state string.

**Not implemented (TODO):** float voltage `PBFT` (range undocumented), battery low-alarm voltage (no known command), equalization (`PBEQ*`), battery type `PBT`, AC output on/off and the P46–P49 schedules (no public command exists; output state is only observed via `QMOD`).

### Write path

```text
service call -> entity -> VoltronicControlEntity.async_send(build)
  build() -> commands.*  (InvalidCommandError -> ServiceValidationError, nothing sent)
  client.write(cmd)       ACK -> slow coordinator async_refresh()
                          NAK -> HomeAssistantError "command_rejected"
                          timeout/connection -> HomeAssistantError "command_failed" (never retried)
```

## How to add a read entity

1. Make sure the field is parsed in [`parsers.py`](../custom_components/voltronic_solar_inverter/protocol/parsers.py) (add a dataclass field + a test in [`tests/test_parsers.py`](../tests/test_parsers.py) against a fixture).
2. Add an `EntityDescription` with a `value_fn` to the right tuple in `sensor.py` / `binary_sensor.py` (fast = `QPIGS`/`QMOD`, slow = `QPIRI`/`QFLAG`/`QPIWS`). Unconfirmed fields: `entity_registry_enabled_default=False`, diagnostic.
3. Add its name (and enum states) under `entity.<platform>.<translation_key>` in `strings.json` and copy the file to `translations/en.json`.
4. A new command must be an answering one; add it to a coordinator's `_fetch` and to the poll list in this doc.

## Tests

See README "Development". Protocol tests run with plain `pytest`; [`tests/test_ha_integration.py`](../tests/test_ha_integration.py) (config flow, entities, control entities with a fake gateway, diagnostics) needs `pytest-homeassistant-custom-component`. Home Assistant does not support Windows: there the HA tests need Python ≥ 3.14, a venv path short enough for `MAX_PATH`, and local stubs for `fcntl`/`resource` plus a `socket.socketpair` shim; on Linux/WSL/CI they run as is.
