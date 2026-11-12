# Protocol Research Summary (resume point)

This page summarizes the read-only protocol research on the Vevor GD5548JMH (`VMII-4000`, fw 00040.09) done on 2026-10-02. It covers what was tried, what worked, what did not, the remaining blind spots, and a concrete plan for the next session. Details live in [inverter-protocol.md](inverter-protocol.md) (commands, field maps) and [settings-map.md](settings-map.md) (per-LCD-program read/write map). Start here when you resume the research.

## How to resume (checklist)

1. Read [AGENTS.md](../AGENTS.md) section 0. The agent may send **only** `Q…` queries (with CRC) and the owner-approved read-only H queries (no CRC, exact allow-list in [`tools/probe_inverter.py`](../tools/probe_inverter.py)). **No writes**: the owner tests every write command himself.
2. Make sure only the Elfin gateway is on the RS232 port; the owner swaps the Solar of Things Wi-Fi dongle in only occasionally. The gateway serves one client: stop HA polling while probing.
3. Probe, one command per run, with a pause between runs:

   ```bash
   python tools/probe_inverter.py --mode new --timeout 2.0 --cmds QPIGS Q1 QPIWS --save tests/fixtures/<name>.json
   ```

   ```bash
   python tools/probe_inverter.py --mode new --no-crc --timeout 2.0 --cmds HEEP2 --save tests/fixtures/<name>.json
   ```

   The first command after the gateway was idle is sometimes lost: list it twice or retry. H responses have no CRC, so read `raw_hex` (the tool's `text` field strips 2 characters).
4. For a setting, use the **delta method**: snapshot → the owner changes ONE LCD program → snapshot → byte-diff → the owner restores the value (or keeps it). Snapshot set: `QPIRI QFLAG QBEQI` (CRC) + `HEEP1 HEEP2 HEEP3` (no CRC).
5. Save every capture under [`tests/fixtures/`](../tests/fixtures/) and update [inverter-protocol.md](inverter-protocol.md), [settings-map.md](settings-map.md) and this page.

## Update 2026-11-12: the vendor's service tool (new main source)

The source code of the manufacturer's Windows service tool for this inverter family is public: [zhuaibai/TQF-AllInOne](https://github.com/zhuaibai/TQF-AllInOne) (WPF, C#). It detects the device with `QPRTL` and has a page for `HPVINV02`, the type this unit reports. Its `HEEP1` decoder matches this unit's reply character by character (packed `HEEP1[3]`, `HEEP1[4]`), so it describes this firmware family, not just a similar one. Found with a GitHub code search for the rare setter names (`PVENGUSE`, `BMSSDC`, `PDDLYT`). A second independent source, [filipsworks/SoT-RWB1-Server-Emulator](https://github.com/filipsworks/SoT-RWB1-Server-Emulator) (Solar of Things dongle, Easun SMT 4 kW 24 V), lists the same setter names as dongle channels (`PSLV`, `DISCC`, `PDSDS`, `PDSRV`, `PDDCGT`, `PDAULC`, `BMSSRC`, `BMSB2UC`, `BMSU2BC`).

What it gave:

- **Setters for the schedules:** `^S???ACCT<HH>-<HH>` (P46/P47 AC charging time) and `^S???ACLT<HH>-<HH>` (P48/P49 inverter output time). The `???` are three literal question marks; the frame ends with the usual CRC + CR. **Not sent by the agent; the owner tests them** ([settings-map.md](settings-map.md#writing-the-schedules-p46p49-candidate-found-2026-11-12)).
- **More setters** not known before: `PSLV` (P24 low-battery alarm), `PDSDV` / `PDSDS` / `PDSRV` / `PDDCGT` / `PDAULC` (second output), `PDAULON00` / `PDAULON01` (second output off / on now), `DISCC` (battery discharge current limit), `BMSB2UC` / `BMSU2BC` / `BMSSRC` (P39 / P40 / P41), `GRIDFEED`, `^S???RS`, `EXTCT`, `POPM`, `PGFP`, `^S???CLE`, `HOSTCRC`.
- **No command for the main AC output on/off** on the `HPVINV02` page. The same tool has `SWON` / `SWOFF<delay>` only on the pages of the vendor's UPS types (`UPSCYX01`, `LB6`).
- **Decoders** for `HSTS`, `HEEP1`, `HEEP2`, `HEEP3`, `HBAT`, `HOP`, `HTEMP`, `HIMSG2`: [inverter-protocol.md](inverter-protocol.md#field-meanings-from-the-vendor-service-tool-2026-11-12). They close blind spots 4, 5 and most of 8.
- **Two unused query names** in the tool, `QCVV` and `QBFT`. Probed read-only on the unit on 2026-11-12 (mode S): both answer. By analogy `QOP` and `QCP` answer too; 15 other analogues are silent ([`probe_vendor_tool_queries.json`](../tests/fixtures/probe_vendor_tool_queries.json)).

| New query (with CRC) | Reply | Meaning | Checked against |
|---|---|---|---|
| `QCVV` | `28.2` | bulk (CV) voltage, P26 | `HEEP1[14]` = `028.2` |
| `QBFT` | `27.2` | float voltage, P27 | `HEEP1[15]` = `027.2` |
| `QOP` | `01` | output source priority as the `POP` code (01 = SBU) | `HEEP1[0]` = `1` |
| `QCP` | `02` | charger priority as the `PCP` code (02 = only solar) | `HEEP1[4]` 3rd char = `2` |

`QOP` / `QCP` return exactly the argument of `POP` / `PCP`, which confirms `POP01` = SBU and `PCP02` = only solar on this unit. The answers also show that this firmware implements the tool's command names, which raises the confidence in the untested setters above.

## What was tried

| Area | Tried | Result |
|---|---|---|
| Vendor service tool source (2026-11-12) | Read the C# source of TQF-AllInOne offline; 19 derived `Q…` queries probed with CRC, one per connection | 4 answer (`QCVV`, `QBFT`, `QOP`, `QCP`), 15 silent; see the update above |
| Community/official sources | mpp-solar protocols, 7 official Voltronic PDFs (PI30 2014/2015, PI30MAX, GK/MK, REVO, PI41, PI00), the VMII-based remote-panel protocol, MKS II–IV, NUT UPS protocol, esphome-pipsolar, solarplug-esphome, forums | Sources table in [inverter-protocol.md](inverter-protocol.md#sources) |
| PI30-family `Q` commands with CRC | ~110 commands, one per connection | 24 answer, 2 NAK (`QPIHF`, `QPICF`), the rest silent ([catalogue](inverter-protocol.md#command-catalogue)) |
| PI17/PI18 (`^P…`) | not sent: frames do not start with `Q` | — |
| `Q` commands without CRC | 11 (incl. `QPIGS`, `QT`, `QET`, `QDOP`) | all silent → PI30 needs CRC |
| Solar Plug H dialect (no CRC) | `QPRTL` + 14 known H queries + 33 name variants | all 14 answer; variants: `HIMSG2`, `HEEP3` answer, 31 silent |
| State changes (snapshots + byte diff) | output schedule on/off, 300 W load, grid unplugged/replugged, battery fell to the P12 voltage (mode L, AC charging), output switched off by the schedule (mode S) | see [State dependence](inverter-protocol.md#state-dependence) |
| Setting deltas (owner on the LCD) | P48/P49, P46/P47, P43, P02, P12, P13, P26, P27, P29 | all found; positions verified ([settings-map.md](settings-map.md)) |
| Timing | 30 back-to-back connections, idle tests, silent-command-then-query | latency 0.2–0.67 s; first command after idle sometimes lost |

## What worked (verified on the unit)

- Live data: `QPIGS` (21 fields), `QMOD`, `Q1` temperatures and charge stage (`11` = bulk seen), `QPIWS` a5 = grid lost.
- Status bits: `QPIGS` b4 load on, b2 charging, b0 AC charging, status-2 b9 = output switched on (`000` in mode S).
- Settings: `QPIRI` (25 fields; priority codes = LCD menu position: P01 `1` = SBU, P16 `2` = only solar), `QFLAG`, `QBEQI`, `QDI` (factory defaults).
- **H dialect**: `HGEN` = inverter clock + PV energy today/month/year/total (matches the app); `HEEP2[11]` = P46/P47 and `HEEP2[12]` = P48/P49 schedules (`HHhh`); `HEEP1[3]` 4th char = P43 (0 BLU / 1 LBU); `HEEP1`/`HEEP2` mirror P02, P12, P13, P26, P27, P29; `HTEMP` = 4 temperatures (= `Q1[8..11]`) + fans; `HIMSG1` firmware date; `HIMSG2` ratings.
- Behaviour: in SBU the unit goes to line mode at P12 and charges from the grid at the P11 limit (2 A) even with P16 = only solar. A schedule-off switches to mode S and stops AC charging. The inverter clock runs ~10 min slow, and schedules follow it.

## What did not work (verified, do not retry)

- Through PI30: clock, energy counters, schedules, dual output, BMS, charge stage/CV time, extra temperatures (full silent list in [inverter-protocol.md](inverter-protocol.md#no-reply-verified-silent-do-not-retry)).
- Load (output) energy counters: in neither dialect.
- True SOC: no BMS link. Every battery % (`QPIGS[10]`, `QBV`, `HBAT[2]`, the app) is the same voltage estimate, and it jumped 95 % / 15 % / 50 % within an hour.
- Fault history `QPIHF`/`QPICF`: `NAK` (fault recording P25 is off).
- Inverter idle consumption: below the 1 A resolution of the battery current; measured from the grid side instead on 2026-10-05 (13 W output off, 40–45 W line mode no load; see [integration.md](integration.md#power-balance-and-self-consumption)).
- UPS-protocol `QWS` stays zero during real warnings.
- No public Voltronic spec or dongle capture has a command for P46–P49. Since 2026-11-12 the vendor service tool gives candidates (`^S???ACCT`, `^S???ACLT`, untested; see the update above).
- Analogue queries built from setter names (`Q` + name without `P`), silent on 2026-11-12: `QSLV QSDV QBDV QDISCC QACLT QACCT QDAULC QDAULON QDSDV QDSRV QDDCGT QDDLYT QGFP QGFC QPVENGUSE`.

## Blind spots (open questions)

| # | Unknown | Best next step |
|---|---|---|
| 1 | All PV-side fields: `QPIGS` 12–14/19, `HPV`, `HPVB`, `QPIWS` a0 "PV loss", `Q1` 2/3/16 timers, absorb/float stages (`Q1[17]` 12/13), status bits b1/b10 | **Daytime snapshot with PV connected**, again while charging reaches absorb/float |
| 2 | Does `HGEN` count up live, and when does "today" roll over (inverter clock)? | Read `HGEN` every ~10 min during production and once after midnight |
| 3 | ~~`HGRID[6]` sign~~ verified 2026-10-05 (+ = import, 1 W steps, occasional single 0 samples, ~16 W + ~2 % low vs an external meter); flow direction code still unknown | Snapshot while AC charging with real current |
| 4 | ~~Remaining characters of packed `HEEP1[3]`, `HEEP2[16]`~~ decoded by the vendor tool (2026-11-12), not yet confirmed by a change on the unit | Optional delta check when the owner changes one of them anyway |
| 5 | ~~Dual output positions~~ decoded by the vendor tool: `HEEP2[1]` / `[2]` shutdown voltage / SOC, `HEEP2[15]` / `[16]` chars 0–1 restore voltage / SOC, `HEEP2[16]` chars 2–4 discharge time, `HEEP2[0]` dual output mode | Same |
| 6 | P44 = `HEEP1[18]` (grid-connected function), P50 = `HEEP1[3]` 2nd character (grid protocol mode), per the vendor tool | Same; leave P44 off |
| 7 | P37–P41 BMS rows | Cannot be tested here (no BMS link); keep them unverified and disabled by default |
| 8 | `HEEP3` (`2048 2048 2048 0150 04500 …`), `HOP[5]`/`[7]`/`[8]`, `HPV[6..8]`, `HSTS` bit meanings, `HBAT` flag strings | Compare across modes (B/L/S, PV, charging) |
| 9 | `Q1[0]`, `[1]`, `[15]` (constant `030 5472 … 5472`) and `Q1[4..7]` flipping `65535 65535 00 00` ↔ `05472 05472 01 01` | Log `Q1` with timestamps across a whole day; correlate with mode/PV/charging |
| 10 | `QFS` layout (all zero so far) | Read after a real fault (do not provoke one) |
| 11 | Write commands: `POP`/`PCP` codes, `PVENGUSE`, `MNCHGC` vs `MCHGC`, `PBCV`/`PBDV`, `PCVV`/`PBFT` acceptance on this firmware | **Owner tests**, one at a time, with read-back (`QPIRI`/`HEEP*`) |
| 12 | Do `^S???ACLT` / `^S???ACCT` work on fw 00040.09, which hours are accepted (LCD 00–23, tool list 01–24), may the window wrap midnight, does the output react at once | **Owner tests** via the new experimental number entities (since 2026-11-12) or by hand, with read-back of `HEEP2[12]` / `[11]`, then restores ([settings-map.md](settings-map.md#writing-the-schedules-p46p49-candidate-found-2026-11-12)) |
| 14 | Main AC output on/off: no command on the tool's `HPVINV02` page; `SWON` / `SWOFF` exist only for the vendor's UPS types; `PDAULON` switches the second output | Owner decides whether to try; see the on/off options in [settings-map.md](settings-map.md#switching-the-ac-output-from-home-assistant-options) |
| 15 | `HSTS2`, `HCTMSG1` (H queries of other device types in the vendor tool) | Not on the approved H list; probe only after the owner adds them |
| 13 | Root cause of the lost first command after idle | Optional: compare with a USB-RS232 cable instead of the Elfin gateway |

## Suggested next session (daytime, PV connected)

1. Full snapshot: `QMOD QPIGS Q1 QPIWS QFS` + `HSTS HGRID HOP HBAT HPV HPVB HTEMP HGEN` → fixture `snapshot_B_day_pv.json`.
2. Repeat every 10–15 min while the battery charges, until float (look for `Q1[17]` 12/13 and status-2 b10).
3. Compare `QPIGS[19]` with `HPV[2]` and the LCD PV power, and check that `HGEN` daily energy grows.
4. If convenient, run the delta method for blind spots 4–6.
5. Update this page: move solved items from "Blind spots" to "What worked".
