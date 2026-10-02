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
```

Full file map: [code-map.md](code-map.md).

## Open items / roadmap

1. **HACS packaging (owner's decision):** HACS installs the *first* folder under `custom_components/`, currently the reference `detailed_hello_world_push`. The reference examples must move elsewhere (e.g. `reference/`) before HACS works; until then install manually.
2. **Owner to verify write commands on the real unit** (read back with `QPIRI`/`QFLAG` after each): `PE<x>`/`PD<x>` for each flag; `POP01` really selects SBU and `PCP02` "only solar" under this firmware's menu-position codes; `MCHGC0nn`, `MUCHGCnnn`; `PBCV`/`PBDV`/`PSDV`/`PCVV` ranges. Then confirm the remaining priority codes (output 0/2, charger 0/1) so they can be added to the `*_VERIFIED` sets.
3. Not implemented: float voltage `PBFT` (range unknown), battery low-alarm voltage, equalization, battery type, AC output on/off / schedules P46–P49 (no public command; output state only via `QMOD`).
4. **Still to do with PV producing:** snapshot `QPIGS`/`Q1`/`QPIWS` with the array connected and charging (PV fields 12–14/19, status bits b1/b2, `QPIWS` a0 "PV loss" clearing, `Q1` charge status/timers), then record fixtures and adjust entity defaults.
5. Optional entities: `Q1` temperatures / charge stage, `QBEQI` equalization status (spec layouts known, not polled).
6. ~~Owner to re-check LCD P16~~ done 2026-10-02: P16 shows "Only solar" while `QPIRI[17]` = 2, so the menu-position reading is confirmed (see "Priority-code check" in [inverter-protocol.md](inverter-protocol.md)). P01 codes 0 and 2 are still unconfirmed.
7. Optional, owner's decision: enable P25 "Record fault code", then re-test `QPIHF`/`QPICF` (they currently answer `NAK`).
8. Optional: CI workflow (GitHub Actions on Linux) running `pytest` and hassfest/HACS validation.

## Protocol research results (2026-10-02)

About 80 candidate `Q` commands from mpp-solar, the official Voltronic PDFs (PI30, PI30MAX, the VMII-based remote-panel protocol, PI00, NUT's UPS protocol) and forums were tried one at a time. Full catalogue with sources: [inverter-protocol.md](inverter-protocol.md#command-catalogue).

- **New answering commands:** `QMD`, `QBV`, `QWS`, `QBT`, `QGR` (UPS protocol). They add nothing over `QPIRI`/`QPIGS`, so they are not worth polling. `QPIHF`/`QPICF` are known but answer `NAK`.
- **Verified unreadable (do not retry):** clock (`QT`), energy counters (`QET`/`QE*`/`QL*`), schedules (`QOPPT`/`QCHPT`/P46–P49), dual output (`QDOP`), BMS (`QBMS`/`QLITH0`), charge stage/CV time (`QCST`/`QCVT`), temperatures (`QTPR`), PV2/parallel, plus about 50 more.
- **Newly understood:** `QDI` fully decoded (factory defaults); `QBEQI` decoded; `QPIGS[17..20]` = fan voltage offset, EEPROM version, **PV charging power**, status 2 (switched on); `QPIWS` a5 LINE_FAIL verified by pulling the grid; a0 = "PV loss" (spec); `Q1[9]` = heat-sink temperature, `Q1[8,10,11]` = other internal temperatures (probable).
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
| PV energy, load energy | integrate PV power / load power | HA Riemann-sum helper + utility meter (the inverter does not expose counters) | user-side |

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
| 2026-10-02 | Energy counters, clock, schedules, dual output and BMS data are confirmed unreadable over RS232. Energy will be computed in HA from power. |
| 2026-10-02 | PV-related verification postponed to a daytime session (owner disconnects PV at night). |
| 2026-10-02 | Integration 0.1.0 implemented: protocol layer without HA imports (`protocol/`), fast (`QPIGS`+`QMOD`, 10 s) and slow (`QPIRI`+`QFLAG`+`QPIWS`, 60 s) coordinators, config + options flow, diagnostics with serial redaction. |
| 2026-10-02 | Priority codes follow the owner's reading of this firmware (LCD menu position): output 0 solar first, 1 SBU (confirmed), 2 battery first (guess); charger 0 solar first, 1 solar+utility, 2 only solar (confirmed). Only confirmed codes are writable. |
| 2026-10-02 | Write commands allowed **as code** (owner lifted the rule for this task only for code/tests): all builders in `protocol/commands.py`, entities only with "Enable control entities" (default off), writes never retried, after ACK the slow coordinator refreshes. Agent still sends only `Q` queries to the device. |
| 2026-10-02 | Battery level % kept as a disabled-by-default "estimate" sensor; energy is computed in HA (Integral + Utility meter helpers), documented in README. |
| 2026-10-02 | QPIWS is polled by the slow coordinator (owner's spec), so warnings lag by up to the slow interval (default 60 s). |
| 2026-10-02 | Owner re-checked the LCD: P16 = "Only solar" while `QPIRI[17]` = 2, so the menu-position reading is confirmed despite the `QDI`/manual hint. Grid charging at the P11 limit (2 A) after falling back to line mode at P12 is expected with "Only solar" (it restricts battery mode only), not a bug. |
