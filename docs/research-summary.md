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

## What was tried

| Area | Tried | Result |
|---|---|---|
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
- Inverter idle consumption: below the 1 A resolution.
- UPS-protocol `QWS` stays zero during real warnings.
- **No known command writes P46–P49** (searched every public spec and the dongle captures).

## Blind spots (open questions)

| # | Unknown | Best next step |
|---|---|---|
| 1 | All PV-side fields: `QPIGS` 12–14/19, `HPV`, `HPVB`, `QPIWS` a0 "PV loss", `Q1` 2/3/16 timers, absorb/float stages (`Q1[17]` 12/13), status bits b1/b10 | **Daytime snapshot with PV connected**, again while charging reaches absorb/float |
| 2 | Does `HGEN` count up live, and when does "today" roll over (inverter clock)? | Read `HGEN` every ~10 min during production and once after midnight |
| 3 | `HGRID[6]` signed grid power, flow direction code | Snapshot in mode L with load (and while AC charging at 01–02) |
| 4 | Remaining characters of packed `HEEP1[3]` (`01210110230`; tail `230` = output V?), `HEEP2[16]` (`50000`) | Delta method: P10 output voltage, P44, P50, dual-output SOC / discharge time |
| 5 | Dual output: which of `HEEP1[11]`/`HEEP2[2]` is the SOC point, which of `HEEP1[13]`/`HEEP2[16]` the recover SOC, discharge time position | Delta method on the dual-output programs |
| 6 | P44 (feed-in, owner keeps it off) and P50 (grid regulation) read positions | Delta method; leave P44 off afterwards |
| 7 | P37–P41 BMS rows | Cannot be tested here (no BMS link); keep them unverified and disabled by default |
| 8 | `HEEP3` (`2048 2048 2048 0150 04500 …`), `HOP[5]`/`[7]`/`[8]`, `HPV[6..8]`, `HSTS` bit meanings, `HBAT` flag strings | Compare across modes (B/L/S, PV, charging) |
| 9 | `Q1[0]`, `[1]`, `[15]` (constant `030 5472 … 5472`) and `Q1[4..7]` flipping `65535 65535 00 00` ↔ `05472 05472 01 01` | Log `Q1` with timestamps across a whole day; correlate with mode/PV/charging |
| 10 | `QFS` layout (all zero so far) | Read after a real fault (do not provoke one) |
| 11 | Write commands: `POP`/`PCP` codes, `PVENGUSE`, `MNCHGC` vs `MCHGC`, `PBCV`/`PBDV`, `PCVV`/`PBFT` acceptance on this firmware | **Owner tests**, one at a time, with read-back (`QPIRI`/`HEEP*`) |
| 12 | A write command for P46–P49 | Ask Vevor support for the VMII RS232 protocol for fw 00040.x; capture WatchPower traffic if it exposes timers. Do **not** guess setter names on the live unit |
| 13 | Root cause of the lost first command after idle | Optional: compare with a USB-RS232 cable instead of the Elfin gateway |

## Suggested next session (daytime, PV connected)

1. Full snapshot: `QMOD QPIGS Q1 QPIWS QFS` + `HSTS HGRID HOP HBAT HPV HPVB HTEMP HGEN` → fixture `snapshot_B_day_pv.json`.
2. Repeat every 10–15 min while the battery charges, until float (look for `Q1[17]` 12/13 and status-2 b10).
3. Compare `QPIGS[19]` with `HPV[2]` and the LCD PV power, and check that `HGEN` daily energy grows.
4. If convenient, run the delta method for blind spots 4–6.
5. Update this page: move solved items from "Blind spots" to "What worked".
