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
5. Setting commands are tried only by the owner, one at a time, with [`tools/write_probe.py`](../tools/write_probe.py) (raw answer, waits 8 s, snapshot diff; the integration stopped). Record every result, also failures, in the log below.
6. Save every capture under [`tests/fixtures/`](../tests/fixtures/) and update [inverter-protocol.md](inverter-protocol.md), [settings-map.md](settings-map.md) and this page.

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

## Research log 2026-11-12 (how the findings were made, results, failures)

Written so the research can be repeated or continued without redoing the dead ends.

### Sources searched

| Source | Query / method | Result |
|---|---|---|
| Web search | VMII RS232 command set, AC output timer, "program 48", HEEP2 | nothing about a timer command; only PI30 / PI30MAX docs (no timer entry) |
| Web search | `HPVINV02` / `HEEP1` / `HEEP2` / "Solar of Things" command set | nothing indexed (only unrelated Modbus documents) |
| Web search | Vevor GD5548JMH / GD3024EMH / VMII-4000 RS232 remote on/off | only this project's own HA forum thread and unrelated Vevor Modbus models |
| Web search | PowMr POW-HVM6.2KP protocol (`PVENGUSE`, `MNCHGC`, `HEEP1`) | manual only (timer = LCD program, hours 00–23); no command table; [leodesigner/powmr_comm](https://github.com/leodesigner/powmr_comm) is a Modbus-style protocol of other PowMr models |
| Web search + forum | [Power Forum: MKS inverter on/off via serial command](https://powerforum.co.za/topic/5227-voltronics-mks-inverter-on-off-via-serial-command/), [Axpert standby/off mode](https://powerforum.co.za/topic/7027-axpert-standbyoff-mode/) | **no serial command switches the AC output of an Axpert/MKS on or off**; a fully switched-off unit does not wake up by a command |
| [NUT Voltronic protocol](https://networkupstools.org/protocols/voltronic.html) | `SON` / `SOFF` search | those exist only in the UPS protocol (QS family), not in PI30 solar inverters |
| GitHub code search (`gh search code`) | rare setter names `PVENGUSE`, `PDDLYT`, `MNCHGC`, `BMSSDC`, `PDSRS`, `PDAULON`, `PSLV` | hits: `rutgerputter/solarplug-esphome` (and a mirror), **`zhuaibai/TQF-AllInOne`** (the vendor service tool), `filipsworks/SoT-RWB1-Server-Emulator`, `GamesterUnknown/ECGSolax_ESPHome`, `ljulina/esphome-easun-smt-iii` (the last two not read in detail) |
| GitHub code search | `ACLT ACCT`, `"S???ACLT"` | **no hit outside the vendor tool**: `^S???ACLT` / `^S???ACCT` are known from one source only |
| Source of the vendor tool (read offline, files downloaded to a scratch folder, not stored in the repo) | `Command/Comand_GB3024/Special_Command.cs` (timers, clock, special commands), `Command/GB_General/HEEP1_HPVINV04_ViewModel.cs` (class `HEEP1_HPVINV02_ViewModel`, the `HPVINV02` settings), `Command/Comand_GB3024/HEEP2_ViewModel.cs` (second output, equalization), `Services/SerialCommunicationService.cs` (framing), `Dictionary/Lan-en-us.xaml` (English labels), `UserControls/GB_MonitorUC.xaml` (the page shown for `HPVINV02`) | all findings in [inverter-protocol.md](inverter-protocol.md#field-meanings-from-the-vendor-service-tool-2026-11-12) and [settings-map.md](settings-map.md#setters-from-the-vendor-service-tool-2026-11-12) |
| Reference capture | [solarplug-esphome](https://github.com/rutgerputter/solarplug-esphome) `tests/test_decode_h_protocol.py` | the clock setter really is `5E 53 3F 3F 3F 44 41 54 …` (**literal `?` bytes**) + CRC `E8 57` + CR; our CRC code gives the same bytes |

Notes on the vendor tool: the three `?` are literal in its source (hex-dumped); its `SWON` / `SWOFF` commands exist only on the pages of the UPS types `UPSCYX01` / `LB6`; the `HPVINV02` page has no output on/off button; it waits 1–2 s before sending the two timer commands ("without the delay it errors", probably a race in its own polling thread).

### Read-only probes on the unit (agent, 2026-11-12, mode S)

`QCVV`, `QBFT`, `QOP`, `QCP` answer (see the table above); 15 analogue names are silent (`QSLV QSDV QBDV QDISCC QACLT QACCT QDAULC QDAULON QDSDV QDSRV QDDCGT QDDLYT QGFP QGFC QPVENGUSE`). Raw: [`probe_vendor_tool_queries.json`](../tests/fixtures/probe_vendor_tool_queries.json), H snapshot [`snapshot_S_2026-11-12_h.json`](../tests/fixtures/snapshot_S_2026-11-12_h.json). Note: a probe run while the HA integration was polling got mixed answers (`QPRTL` answered with a `QPIGS` payload): always stop the integration first.

### Owner tests of the setters (v0.4.17 and [`tools/write_probe.py`](../tools/write_probe.py))

| When | Test | Result |
|---|---|---|
| 2026-11-12 ~22:19 | HA numbers *AC output on/off hour*: `^S???ACLT11-19`, `^S???ACLT12-18` | HA error "no answer … in 2.0 s", LCD unchanged |
| same evening | HA button *Set inverter clock to HA time* (`^S???DAT…`) | **works**: clock offset sensor −3 → −1 min (HGEN has minute resolution). So the `^S` family is understood |
| same evening | HA switch *Second output* (`PDAULON01`) | accepted (switch turned on). The owner then switched the second output off on the inverter; the switch stayed on (assumed state, no read-back) |
| 22:32–22:36 | `write_probe.py --try ACLT 12 18` and `--try ACCT 1 2`, 4 variants each, 8 s wait: `^S???ACLT12-18`; same after a 2 s pause; `^S012ACLT12-18` (PI18 length digits); `^S???ACLT1218` (no hyphen); the same four for `ACCT01-02` | **all 8 silent**, `HEEP2` unchanged (only the clock minute moved) |
| 22:37–22:38 | `write_probe.py "PDAULON01"`, then `"PDAULON00"` | both answered `(ACK` + CRC in 0.14–0.17 s; **no token changed** in `HSTS HEEP1 HEEP2 HGEN QMOD` |
| later the same evening (mode S, main output off) | `write_probe.py "PDAULC01" --snapshot HSTS HEEP2 QMOD HOP`, then `"PDAULON01"`, then `"PDAULON00"` | `PDAULC01`: `(ACK` in 0.20 s, **`HEEP2[0]` 0 → 1: `PDAULC` = P60 (dual output enable) verified**. `PDAULON01` / `PDAULON00`: `(ACK` in 0.16–0.22 s, **`HSTS`, `QMOD` unchanged** (dual output now enabled, main output still off). `HOP[8]` changed `00000 → 00002 → 00001` during the run (also with no relation to the command: the tool's "inductor power", noise, ignore it) |
| night, **mode L** (grid feeds the output, battery 23.5 V and not discharging, no load), P60 on; P48/P49 set to 23–00 on the LCD | `quick_check.py`, then `write_probe.py "PDAULON01"` and `"PDAULON00"` with `--snapshot HSTS HEEP2 QMOD HOP QPIGS` | `HSTS` in mode L: `00 L010000000000 11211001000L112000000`. **Before** `PDAULON01` the second output was already on (`HSTS[2]` char 4 = `1`, switched on by P60 itself); `PDAULON01` changed nothing. **`PDAULON00` changed `HSTS[2]` char 4 from `1` to `0`: `PDAULON` switches the second output and `HSTS[2]` char 4 is its read-back (1 = on)**, as the vendor tool says. Also in L: `HSTS[1]` char 2 = `1` (machine has output) and `HSTS[2]` char 3 = `1` (main relay) versus `0` in mode S. The reverse step (`PDAULON01` from the off state) was not run yet. Caveat: this run was line mode (grid), not battery mode; the cutoff / restore points P61–P66 apply to battery operation and were not exercised. Fixture: [`snapshot_L_2026-11-12_second_output.json`](../tests/fixtures/snapshot_L_2026-11-12_second_output.json) |

Snapshot at the time of the last tests (mode S, output off by P48/P49 = 12–19): `HSTS` `00 S000000000000 10200002000S000000000`, `HEEP2` `0 022.0 020 023.6 024.0 026.0 0 029.2 060 120 030 0000 1219 05 0000 26.0 50000`, `HEEP1` `1 040 002 01210110230 002 1 1 1 0 0 010 020 095 050 028.2 027.2 022.4 012 0 1`. `HEEP2[0]` (dual output mode) was `0`; at the start of the day it was `1`. Who changed it is not recorded (probably the owner, via the HA switch or the LCD).

### Conclusions and what is NOT known

- **`^S???ACLT` / `^S???ACCT` are not understood by fw 00040.09** in any form tried (answer-less, like every unknown command). Not tried, and why: sending without CRC (`write_probe.py --no-crc`, cheap), `HOSTCRCEN` first (the vendor tool enables it for some device types; it changes the format of the unit's H answers, so risky for the integration), other selector bytes, a different hour format. Do not retry the eight frames above. Realistic paths: ask Vevor for the protocol of fw 00040.09; emulate the charger window with HA automations (`PCP`, `MUCHGC`); a relay on the load side for the 230 V output.
- **`PDAULON` is accepted, but its effect and read-back are unknown.** `HSTS[2]` char 4 (the tool's "second output state") did not change. The test was done with the dual output mode off (`HEEP2[0]` = 0) and the inverter in mode S, so it proves nothing about the effect. See the correction below.
- **No command is known that switches the main 230 V output on/off** (see the options table in [settings-map.md](settings-map.md#switching-the-ac-output-from-home-assistant-options)).

### Correction (owner, 2026-11-12)

The agent wrote that the second output could not work while the main output was off by P48/P49 and proposed changing P48/P49 on the LCD for the test. That was an **unfounded assumption** and mixed two things up: **P48/P49 are the schedule of the MAIN output only.** The second output has its **own time program** (the owner remembers P67/P68; this project's manual extract only has "dual output group, programs ~57–64, numbers not legible", and the Solar of Things app calls it "INV Dual Output Time", read here as `HEEP2[14]` = `0000`). No setter is known for that time program (the vendor tool has none; the remote-panel spec has `PTOPS`, untested). Whether the second output needs the main output to be on is unknown. **Resolved the same day:** the owner gave the vendor manual; the dual output group is **P60–P68** (P60 enable, P61/P62 cut-off voltage / SOC, P63/P64 restore voltage / SOC, P65 discharge time, P66 restore delay, **P67/P68 open / stop time**), see [settings-map.md](settings-map.md#dual-output-p60p68). The manual does not say whether the second output needs the main output to be on. `HEEP2[0]` is P60: it read `1` in the morning and `0` in the evening (the owner disabled the dual output on the LCD), which explains why `PDAULON` changed nothing in the snapshot: **the dual output was disabled**. Test plan for the read-back of the second output state: (1) `python tools/write_probe.py "PDAULC01" --snapshot HSTS HEEP2 QMOD HOP` should flip `HEEP2[0]` 0 → 1 (confirms `PDAULC` = P60); (2) then `PDAULON01` and `PDAULON00` with the same snapshot, once with the main output off (mode S) and once with it on (mode B/L, e.g. inside the P48/P49 window, no LCD change needed); (3) note which token of `HSTS` (expected `HSTS[2]` char 4) follows, and whether a load / multimeter on the second output terminals (if the unit has them) follows; (4) restore `PDAULC00` if the owner wants it off. Not done yet.

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
