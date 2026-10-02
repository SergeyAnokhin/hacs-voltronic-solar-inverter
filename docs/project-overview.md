# Project Overview

A Home Assistant custom integration, distributed through HACS, that polls a Voltronic-compatible solar inverter (the owner has a **Vevor GD5548JMH** hybrid inverter) and exposes its data as Home Assistant sensors. Existing community integrations do not work with this newer Vevor model, but the owner's Python prototype ([`python_scripts/get_inverter_info.py`](../python_scripts/get_inverter_info.py)) already reads it reliably; the integration is meant to productize that, expose far more data, and be installable by anyone with HACS.

## Goals and owner wishes (recorded from the first session)

| # | Wish | Status |
|---|---|---|
| 1 | Custom HA integration installable via HACS, repo hosted on GitHub | Implemented (0.1.0, see [integration.md](integration.md)). HACS install blocked until the example integrations leave `custom_components/` (open item) |
| 2 | Turn inverter parameters into HA sensors (live values, nominal values, settings, status flags, warnings) | Implemented: sensors + binary sensors from `QPIGS`, `QMOD`, `QPIRI`, `QPIWS`, `QFLAG` |
| 3 | Extract **more** data than the prototype: research what other `Q…` commands / fields this or similar Voltronic/Axpert/Vevor inverters expose (internet, community projects), including undocumented ones | Done at night on 2026-10-02 (see [results](#protocol-research-results-2026-10-02)); PV-side checks still pending |
| 4 | Allow **changing settings** from HA | Code written on 2026-10-02 at the owner's request: switches/selects/numbers behind the "Enable control entities" option (default off). The agent never sends them to the device; the owner tests them on the real unit (see [AGENTS.md](../AGENTS.md) section 0) |
| 5 | Documentation in English; integration UI in English only (no translations) | Decided |
| 6 | `README.md` in the usual HACS-integration style: install, config, entities; kept up to date | Done |
| 7 | Agent keeps `docs/` current and consults it first in each session (see [AGENTS.md](../AGENTS.md)) | In place |

## Environment facts

- Inverter: Vevor GD5548JMH (reports as `VMII-4000`), 24 V battery system, 4 kW; details in [inverter-vevor-gd5548jmh.md](inverter-vevor-gd5548jmh.md).
- Transport: inverter RS232 → Elfin RS232↔TCP gateway (default prototype address `192.168.1.47`, port `8899`) → LAN. The gateway serves one client at a time.
- Owner's current settings: output priority PV → battery → grid (SBU), charge from solar only, AC output scheduled ON by P48/P49 (23:00–00:00; temporarily 19:00–21:00 for the experiment) to save battery (the inverter stage itself draws a lot). He wants HA to be able to see/control this output state eventually.
- The owner switches PV on/off manually (PV was off during the first tests, battery mode at night).
- Home Assistant runs elsewhere; `python_scripts/` is HA's `python_script` folder (the prototype is used from there).
- The vendor PDF manual was distilled into docs and has been deleted by the owner.

## Repository layout (summary)

```text
AGENTS.md / CLAUDE.md      agent rules (CLAUDE.md just imports AGENTS.md)
README.md                  public GitHub page
docs/                      living documentation (this folder)
.claude/skills/            update-docs, session-retro
python_scripts/            working prototype (get_inverter_info.py) + HA examples
custom_components/         official HA example integrations (reference, read-only) + the future integration
esphome/                   ESPHome configs for ESP32 + MAX3232 (native pipsolar, or RS232-TCP bridge)
```

Full file map: [code-map.md](code-map.md).

## Open items / roadmap

1. **HACS packaging (owner's decision):** HACS installs the *first* folder under `custom_components/`, currently the reference `detailed_hello_world_push`. The reference examples must move elsewhere (e.g. `reference/`) before HACS works; until then install manually.
2. **Owner to verify write commands on the real unit** (read back with `QPIRI`/`QFLAG` after each): `PE<x>`/`PD<x>` for each flag; `POP01` really selects SBU and `PCP02` "only solar" under this firmware's menu-position codes; `MCHGC0nn`, `MUCHGCnnn`; `PBCV`/`PBDV`/`PSDV`/`PCVV` ranges. Then confirm the remaining priority codes (output 0/2, charger 0/1) so they can be added to the `*_VERIFIED` sets.
3. Not implemented as writes: float voltage `PBFT` (range unknown, NAK on the reference unit), battery low-alarm voltage (no command), equalization (`PBEQ*`, deliberately left read-only: equalizing a LiFePO4 bank is harmful), battery type `PBT`, input range `PGR`, clock `DAT`, dual output, feed-in `PEd` (owner keeps it off), and the P46–P49 schedules / AC output on/off (no known command). The schedules are **read** via `HEEP2`.
4. **Still to do with PV producing:** snapshot `QPIGS`/`Q1`/`QPIWS` with the array connected and charging (PV fields 12–14/19, status bits b1/b2, `QPIWS` a0 "PV loss" clearing, `Q1` charge status/timers), then record fixtures and adjust entity defaults.
5. ~~Optional entities `Q1` charge stage, `QBEQI`~~ done (0.2.0). **Owner to check on the real unit** that `Q…` (CRC) and `H…` (no CRC) queries mixed on one persistent connection keep answering (research sent them one per connection); and the sign of `HGRID[6]` grid power in mode L.
6. ~~Owner to re-check LCD P16~~ done 2026-10-02: P16 shows "Only solar" while `QPIRI[17]` = 2, so the menu-position reading is confirmed (see "Priority-code check" in [inverter-protocol.md](inverter-protocol.md)). P01 codes 0 and 2 are still unconfirmed.
7. Optional, owner's decision: enable P25 "Record fault code", then re-test `QPIHF`/`QPICF` (they currently answer `NAK`).
8. Pin the unknown read positions in [settings-map.md](settings-map.md) (rows marked `?`): the owner changes one LCD setting at a time and the agent diffs `QPIRI QFLAG QBEQI HEEP1 HEEP2 HEEP3`.
9. Optional: CI workflow (GitHub Actions on Linux) running `pytest` and hassfest/HACS validation.

## Protocol research results (2026-10-02)

Resume point with tried/worked/failed, blind spots and the next test plan: [research-summary.md](research-summary.md).

About 80 candidate `Q` commands from mpp-solar, the official Voltronic PDFs (PI30, PI30MAX, the VMII-based remote-panel protocol, PI00, NUT's UPS protocol) and forums were tried one at a time. Full catalogue with sources: [inverter-protocol.md](inverter-protocol.md#command-catalogue).

- **New answering commands:** `QMD`, `QBV`, `QWS`, `QBT`, `QGR` (UPS protocol). They add nothing over `QPIRI`/`QPIGS`, so they are not worth polling. `QPIHF`/`QPICF` are known but answer `NAK`.
- **Verified silent in PI30 (do not retry):** `QT`, `QET`/`QE*`/`QL*`, `QOPPT`/`QCHPT`, `QDOP`, `QBMS`/`QLITH0`, `QCST`/`QCVT`, `QTPR`, PV2/parallel, plus about 50 more.
- **Breakthrough: the Solar Plug H-protocol (no CRC).** The Solar of Things app screenshots (`docs/screenshots/solar_of_things/`) showed values PI30 cannot give. The vendor Wi-Fi dongle uses a second, CRC-less dialect (`QPRTL` → `HPVINV02`). With the owner's approval, 14 read-only H queries were sent and all answered: **`HGEN` = inverter clock + PV energy today/month/year/total (matches the app)**, **`HEEP2[12]` = AC output schedule P48/P49 (verified by changing 19–21 → 23–00)**, `HTEMP` = inverter/boost/transformer/PV temperatures + fans, `HGRID` = signed grid power, `HEEP1/2` = full settings snapshots (dual output, BMS-SOC thresholds, equalization). Details: [inverter-protocol.md](inverter-protocol.md#solar-plug-h-protocol-no-crc).
- **Still not readable:** load-energy counters, true SOC (no BMS), fault history.
- **Newly understood:** `QDI` fully decoded (factory defaults); `QBEQI` decoded; `QPIGS[17..20]` = fan voltage offset, EEPROM version, **PV charging power**, status 2 (switched on); `QPIWS` a5 LINE_FAIL verified by pulling the grid; a0 = "PV loss" (spec); `Q1[8..11]` = inverter / boost (= `QPIGS` "heat sink") / transformer / PV temperatures (equal to `HTEMP[0..3]`); `QPIGS` status 2 b9 = output on (verified in mode S).
- **Not available at all:** true SOC (no BMS link; the voltage-based % is wrong for LiFePO4), battery temperature (no sensor), the inverter's own idle consumption (below the 1 A resolution of the discharge current).
- **Reliability:** the first command of a new connection is occasionally lost after the gateway has been idle; retry once.

### Entity plan from the research (implemented; the current list is in [integration.md](integration.md#entities))

| Entity | Source | Type / unit | Default |
|---|---|---|---|
| Grid voltage, grid frequency | `QPIGS` 0/1 | sensor V / Hz | on |
| AC output voltage, frequency | `QPIGS` 2/3 | sensor V / Hz | on |
| Load active power, apparent power, load % | `QPIGS` 5/4/6 | sensor W / VA / % | on |
| Battery voltage | `QPIGS` 8 | sensor V | on |
| Battery charge current, discharge current | `QPIGS` 9/15 | sensor A | on |
| Battery power (signed, derived) | `QPIGS` 8 × (9 − 15) | sensor W | on |
| PV voltage, PV current, PV power | `QPIGS` 13/12/19 | sensor V / A / W | on (verify with PV) |
| SCC battery voltage | `QPIGS` 14 | sensor V | off (diagnostic) |
| Bus voltage | `QPIGS` 7 | sensor V | off (diagnostic) |
| Heat-sink temperature | `QPIGS` 11 | sensor °C | on |
| Internal temperatures 1/2/3 | `Q1` 8/10/11 | sensor °C | off (diagnostic, unconfirmed) |
| Inverter battery estimate | `QPIGS` 10 | sensor % (named so it is not taken for SOC) | off |
| Device mode | `QMOD` | enum sensor (Standby / Line / Battery / Fault / Power saving) | on |
| AC output active | `QMOD` ∈ {B, L} or `QPIGS` b4 | binary sensor | on |
| Grid present | `QPIGS` 0 > 0 / `QPIWS` a5 | binary sensor | on |
| Charging, SCC charging, AC charging | `QPIGS` b2/b1/b0 | binary sensors | on |
| Charging to float | `QPIGS` status2 b10 | binary sensor | off |
| Charge stage | `Q1` 17 | enum (idle/bulk/absorb/float) | off until verified |
| Warnings / faults | `QPIWS` | one "problem" binary sensor + attribute list of active bits; a5/a12/a16 etc. as individual binary sensors | on |
| Settings (diagnostic): output priority, charger priority, battery type, bulk/float/under/re-charge/re-discharge voltages, max charge / AC-charge current, input range | `QPIRI` | diagnostic sensors | on |
| Flags (diagnostic): buzzer, power saving, overload bypass/restart, over-temp restart, backlight, fault record | `QFLAG` | diagnostic binary sensors | off |
| Equalization enabled/active, voltage, period | `QBEQI` | diagnostic | off |
| Device info: model, serial, firmware 1/2, protocol | `QMN`, `QID`, `QVFW`, `QVFW2`, `QPI` | device registry | — |
| PV energy, load energy | integrate PV power / load power | HA Riemann-sum helper + utility meter | user-side (superseded for PV by `HGEN`, see below) |

### Additional entities via the H-protocol (implemented in 0.2.0; current list in [integration.md](integration.md#entities))

| Entity | Source | Type / unit | Note |
|---|---|---|---|
| PV energy today / month / year / total | `HGEN` 2–5 | sensor kWh, `total_increasing` (total) | native counters, match the app; replaces the Riemann helper for PV |
| Inverter clock / clock offset | `HGEN` 0–1 | diagnostic timestamp | unit runs ~10 min slow; minute resolution |
| AC output schedule (on hour, off hour) | `HEEP2[12]` | diagnostic sensors | verified |
| AC charger schedule | `HEEP2[11]` | diagnostic | unverified |
| Inverter / boost / transformer / PV temperature, fan 1/2 speed | `HTEMP` | sensors °C / % | temps also in `Q1` |
| Grid power (signed) | `HGRID[6]` | sensor W | verify in mode L |
| Low-battery alarm voltage, dual-output and BMS-SOC thresholds | `HEEP1`/`HEEP2` | diagnostic | positions from the reference project + app screenshots |
| Firmware date | `HIMSG1` | device info | |

## Decisions log

| Date | Decision |
|---|---|
| 2026-10-02 | Read-only integration; agent must never send non-`Q` commands to the inverter. |
| 2026-10-02 | Docs/code/UI in English; chat with the owner in Russian. |
| 2026-10-02 | Integration domain/folder: `voltronic_solar_inverter`. |
| 2026-10-02 | Real unit is **24 V / 4000 W** (`VMII-4000`, PI30), not 48 V; 5 prototype discovery commands never answer and cost ~10 s per poll. Details: [inverter-protocol.md](inverter-protocol.md). |
| 2026-10-02 | Output schedule (P46–P49) is not readable via `Q` commands (diff of 13 responses showed nothing); output on/off is observed through `QMOD` `S`↔`B`. |
| 2026-10-02 | `CLAUDE.md` imports `AGENTS.md` so both Claude Code and other agents use the same rules. |
| 2026-10-02 | Owner's battery is a 24 V LiFePO4 bank set as "User-defined", no BMS. Keep the inverter's battery % only as an "estimate" sensor (owner: "it can stay, but it is calculated wrongly"). |
| 2026-10-02 | Energy counters, clock, schedules, dual output and BMS data are not readable through **PI30**; later the same day they were found in the Solar Plug H-protocol (see the next rows). |
| 2026-10-02 | PV-related verification postponed to a daytime session (owner disconnects PV at night). |
| 2026-10-02 | Integration 0.1.0 implemented: protocol layer without HA imports (`protocol/`), fast (`QPIGS`+`QMOD`, 10 s) and slow (`QPIRI`+`QFLAG`+`QPIWS`, 60 s) coordinators, config + options flow, diagnostics with serial redaction. |
| 2026-10-02 | Priority codes follow the owner's reading of this firmware (LCD menu position): output 0 solar first, 1 SBU (confirmed), 2 battery first (guess); charger 0 solar first, 1 solar+utility, 2 only solar (confirmed). Only confirmed codes are writable. |
| 2026-10-02 | Write commands allowed **as code** (owner lifted the rule for this task only for code/tests): all builders in `protocol/commands.py`, entities only with "Enable control entities" (default off), writes never retried, after ACK the slow coordinator refreshes. Agent still sends only `Q` queries to the device. |
| 2026-10-02 | Battery level % kept as a disabled-by-default "estimate" sensor; energy is computed in HA (Integral + Utility meter helpers), documented in README. |
| 2026-10-02 | QPIWS is polled by the slow coordinator (owner's spec), so warnings lag by up to the slow interval (default 60 s). |
| 2026-10-02 | Owner re-checked the LCD: P16 = "Only solar" while `QPIRI[17]` = 2, so the menu-position reading is confirmed despite the `QDI`/manual hint. Grid charging at the P11 limit (2 A) after falling back to line mode at P12 is expected with "Only solar" (it restricts battery mode only), not a bug. |
| 2026-10-02 | Owner approved sending the read-only Solar Plug H queries `HSTS HGRID HOP HBAT HPV HPVB HTEMP HGEN HIMSG1 HBMS1 HBMS2 HBMS3 HEEP1 HEEP2` (no CRC) and `QPRTL`; enforced by an exact allow-list in `tools/probe_inverter.py`. H-dialect writes stay forbidden. |
| 2026-10-02 | P48/P49 AC output schedule is readable as `HEEP2[12]` (`HHhh`), verified 19–21 → 23–00. The inverter clock runs ~10 min slow (owner noticed the output switched off at ~21:10). |
| 2026-10-02 | Owner wants every LCD program at least readable, and later writable (priorities, P48/P49 schedule). Mapping and candidate write commands collected in [settings-map.md](settings-map.md). Writes are documented only; the owner tests them himself. No public command writes P46–P49. |
| 2026-10-02 | H name-variant probing found `HIMSG2` (ratings) and `HEEP3` (unknown); 31 other variants are silent. The Wi-Fi dongle and the Elfin gateway are never connected at the same time (owner swaps them), so no bus conflict. |
| 2026-10-02 | Verified: `HEEP2[11]` = P46/P47 AC-charger schedule (owner set 01–02); `HEEP1[3]` 4th char = P43 solar supply priority (owner switched BLU → LBU, PV now feeds the load first). |
| 2026-10-02 | Owner's interests for control: P46/P47 and P48/P49 schedules, output/charger priorities, P43. P44 (feed-in to grid) must stay off: the owner does not export energy. |
| 2026-10-02 | BMS settings/values (P37–P41, `HBMS*`): keep them in the integration when the H-protocol is added, but **disabled by default** (HA `entity_registry_enabled_default=False`); the owner cannot test them (no BMS link). |
| 2026-10-02 | Owner changed P02/P12/P13/P26/P27/P29 by one step on the LCD; every change appeared in both `QPIRI` and `HEEP1`/`HEEP2`, so these read positions are verified ([settings-map.md](settings-map.md)). P05 (battery type) deliberately not touched (may reset P26/P27/P29 presets). |
| 2026-10-02 | Integration 0.2.0: the research findings were added. The client sends the owner-approved H queries without CRC (exact allow-list `PLAIN_QUERIES`); the H dialect is detected at start-up with `QPRTL`. New read entities: PV energy today/month/year/total (`HGEN`), inverter clock + offset, AC output (P48/P49) and AC charger (P46/P47) schedules, P43, battery low-alarm voltage, temperatures/fans (`HTEMP`), grid power (`HGRID`), charge stage (`Q1`), equalization (`QBEQI`); dual-output, BMS-SOC and grid-tie values disabled by default. Optional queries (Q1, QBEQI, H*) fail softly: only their entities become unavailable. |
| 2026-10-02 | New writes (controls option only): P43 select (`PVENGUSE00/01`, both read codes owner-verified). Max charging current now uses `MNCHGC<nnn>` (ACKed + read back on the sibling VMII-6200) instead of PI30 `MCHGC<mnn>`. Output priority code 2 relabelled "utility first" (POP mapping of the reference project), still not selectable. Equalization stays read-only on purpose (LiFePO4). |
| 2026-10-02 | Owner asked for an ESPHome alternative (ESP32 + MAX3232 on the RS232 port, read and write). Added `esphome/`: native config on core `pipsolar` (PI30 only, no H dialect/energy counters) with an opt-in controls package, and a stream-server bridge on port 8899 so the HACS integration works unchanged. Both pass `esphome config`; not yet tried on the real unit. The GD5548JMH RJ45 pinout is unknown: reuse the Elfin cable or measure. See [esphome.md](esphome.md). |
