# LCD Settings Map (P01–P64): read sources and write commands

For every LCD program of the Vevor GD5548JMH (see [inverter-vevor-gd5548jmh.md](inverter-vevor-gd5548jmh.md#3-lcd-settings-programs)), this page lists where its current value can be **read** over RS232 and which command is known to **write** it. Reads come from the PI30 dialect (`Q…` + CRC) and the CRC-less Solar Plug H dialect; both are described in [inverter-protocol.md](inverter-protocol.md). Values in the "Now" column were read on 2026-10-02 before the owner's test changes (at 21:45 the owner left P02 = 40 A, P12 = 22.5, P13 = 25.5, P26 = 29.1, P27 = 29.0, P29 = 21.7) and match the owner's Solar of Things screenshots ([`docs/screenshots/solar_of_things/`](screenshots/solar_of_things/)).

**Write commands are NOT tested by agents.** Agents never send them (see [AGENTS.md](../AGENTS.md)); the owner verifies each one on the real unit, one at a time, and reads the value back afterwards. A "Ref" write was ACKed on the sibling `VMII-6200` fw 40.05 in [solarplug-esphome](https://github.com/rutgerputter/solarplug-esphome/blob/main/docs/protocol/WRITE_SURFACE.md). "Spec" means it appears in an official Voltronic protocol PDF but was not observed on a VMII unit. All write commands are sent **with** CRC-16/XMODEM (same framing as PI30 queries) and answer `(ACK` or `(NAK`.

Confidence of the read position: **V** = verified here by a change (owner changed the setting, the value followed); **M** = value matches the app/LCD but was not changed; **R** = only the reference project's mapping; **?** = unknown.

| P | Setting | Now | Read source | Conf. | Write command (owner to test) | Write source |
|---|---|---|---|---|---|---|
| 01 | Output source priority | SBU | `QPIRI[16]` (`1` = SBU, menu-position codes) | V (owner) | `POP<NN>`: `POP00` SUB / solar first, `POP01` SBU, `POP02` utility first | Ref (mapping best-guess there too); PI30 spec |
| 02 | Max total charge current | 50 A | `QPIRI[14]`, `HEEP1[1]` | **V** (50 → 40 A moved both; `QBEQI[3]` equalization max current follows P02) | `MNCHGC<nnn>` (Ref, ACK + readback) or PI30 `MCHGC<nnn>`; allowed values = `QMCHGCR` | Ref / spec |
| 03 | AC input range | Appliance | `QPIRI[15]`, `QGR` | M | `PGR<NN>` (00 Appliance, 01 UPS) | Spec |
| 05 | Battery type | User ("USE", 3rd on the LCD list AGM / FLd / USE → code `2`) | `QPIRI[12]`, `QBT`, `HBAT[0]` | M | `PBT<NN>` (Ref: `03` = LIA, `04` = PYL on its firmware). ⚠ Changing the type may overwrite P26/P27/P29 with the type's presets; re-read them afterwards | Ref |
| 06 | Overload auto-restart | off | `QFLAG` `u` | M | `PEu` / `PDu` | Ref |
| 07 | Over-temp auto-restart | on | `QFLAG` `v` | M | `PEv` / `PDv` | Ref |
| 08 | Power saving (ECD) | on | `QFLAG` `j` | M | `PEj` / `PDj` | Spec |
| 09 | Output frequency | 50 Hz | `QPIRI[3]` | M | `F50` / `F60` (spec says standby only) | Spec |
| 10 | Output voltage | 230 V | `QPIRI[2]`, `HEEP1[3]` tail `…230`? | M / ? | `V<nnn>` (remote-panel spec "for VMIII") | Spec |
| 11 | Max AC (utility) charge current | 2 A | `QPIRI[13]`, `HEEP1[2]` | M (2 A seen as real charge current) | `MUCHGC<nnn>`; allowed = `QMUCHGCR` (`002 010 … 060`) | Ref (ACK + readback) |
| 12 | Back-to-grid voltage | 22.0 V | `QPIRI[8]`, `HEEP2[4]` | **V** (22.0 → 22.5) | `PBCV<nn.n>` | Ref (ACK + readback) |
| 13 | Back-to-battery voltage | 25.0 V | `QPIRI[22]`, `HEEP2[5]` | **V** (25.0 → 25.5) | `PBDV<nn.n>` | Ref (ACK + readback) |
| 16 | Charger source priority | Only solar | `QPIRI[17]` (`2`) | V (owner, LCD) | `PCP<NN>`: `PCP00` solar first, `PCP01` solar + utility, `PCP02` only solar | Ref (round-trip confirmed there, same codes) |
| 18 | Buzzer | on | `QFLAG` `a` | M | `PEa` / `PDa` | Ref |
| 19 | Return to default screen | off | `QFLAG` `k`, `HEEP1[4]` (`002` = off, ref `012` = on) | M / R | `PEk` / `PDk` | Ref |
| 20 | Backlight | on | `QFLAG` `x` | M | `PEx` / `PDx` | Ref |
| 22 | Beep on source loss | on | `QFLAG` `y` | M | `PEy` / `PDy` | Ref |
| 23 | Overload bypass | on | `QFLAG` `b` | M | `PEb` / `PDb` | Spec |
| 24 | Battery low-alarm voltage | 22.0 V | `HEEP2[1]` | M (app 22; did **not** move when P12 changed) | none known; Ref portal: "Command not supported" | — |
| 25 | Record fault codes | off | `QFLAG` `z` | M | `PEz` / `PDz` | Spec |
| 26 | Bulk (CV) voltage | 29.2 V | `QPIRI[10]`, `HEEP1[14]` | **V** (29.2 → 29.1) | `PCVV<nn.n>` (Ref portal: not supported on its firmware) | Spec |
| 27 | Float voltage | 29.1 V | `QPIRI[11]`, `HEEP1[15]` | **V** (29.1 → 29.0) | `PBFT<nn.n>` (Ref: NAK on tested values) | Spec |
| 29 | Low DC cut-off | 21.6 V | `QPIRI[9]`, `HEEP1[16]` | **V** (21.6 → 21.7) | `PSDV<nn.n>` | Spec / Ref frame |
| 30 | Equalization enable | off | `QBEQI[0]` | M | `PBEQE1` / `PBEQE0` | Ref |
| 31 | Equalization voltage | 29.2 V | `QBEQI[5]`, `HEEP2[7]` | M | `PBEQV<nn.nn>` | Ref (ACK + readback) |
| 33 | Equalization time | 60 min | `QBEQI[1]`, `HEEP2[8]` | M | `PBEQT<nnn>` | Ref (ACK + readback) |
| 34 | Equalization timeout | 120 min | `QBEQI[7]`, `HEEP2[9]` | M | `PBEQOT<nnn>` | Ref (ACK + readback) |
| 35 | Equalization interval | 30 d | `QBEQI[2]`, `HEEP2[10]` | M | `PBEQP<nnn>` | Ref (ACK + readback) |
| 36 | Equalize now | — | `QBEQI[8]` (active flag) | M | `PBEQA<n>` | Spec |
| 37 | BMS function | off | ? (app "BMS Function Enable: Off") | ? | `BMSC00` / `BMSC01` | Ref |
| 38 | BMS SOC lock (shutdown) | 10 % | `HEEP1[10]` | M (app 10) | `BMSSDC<nnn>` (Ref: range unclear) | Ref |
| 39 | BMS SOC → switch to AC | 20 % | `HEEP1[11]` or `HEEP2[2]` (both `020`) | ? | `PBCC<nnn>` (re-charge capacity) | Spec |
| 40 | BMS SOC → back to battery | 95 % | `HEEP1[12]` | M (app 95) | `PBDC<nnn>` (re-discharge capacity) | Spec |
| 41 | BMS restart (startup) SOC | 50 % | `HEEP1[13]` or `HEEP2[16]` (`50000`) | ? | none known | — |
| 43 | Solar supply priority (PV to battery first = BLU, or to load first = LBU) | LBU (changed by the owner 2026-10-02) | `HEEP1[3]` **4th character**: `0` = BLU, `1` = LBU | **V** (BLU → LBU flipped it `0` → `1`) | `PVENGUSE00` = BLU, `PVENGUSE01` = LBU | Ref |
| 44 | Solar feed to grid (export PV surplus back through the AC input; needs grid-operator approval) | off (app "Grid Connection Function: Disable") | ? (probably another character of `HEEP1[3]`) | ? | `PEd` / `PDd` ("solar feed to grid", reserved feature) | Spec. Owner does not want export, so leave it off |
| 45 | Reset PV energy | — | — | — | `RTEY` (**erases** PV/load energy history; do not use casually) | Spec |
| 46 / 47 | AC charger start / stop hour | 01–02 (changed by the owner 2026-10-02) | `HEEP2[11]` (`HHhh`) | **V** (`0000` → `0102`) | **none known** | — |
| 48 / 49 | AC output on / off hour | 23–00 | `HEEP2[12]` (`HHhh`) | **V** (19–21 → 23–00) | **none known** (see below) | — |
| 50 | Grid regulation (feed-in) | Mode 2 (app) | ? | ? | `SRS<nn>` (remote-panel spec; country codes 00 India, 01 Germany, 02 South America) | Spec |
| 51–55 | Clock | ~10 min slow | `HGEN[0..1]` (YYMMDD HH:MM) | M (app) | PI30 `DAT<yymmddhhmmss>`; the dongle uses `^S???DAT<yymmddhhmmss>` (3 opaque bytes) | Spec / Ref |
| 56 | Grid-tie current | 12 A | `HEEP1[17]` | M (app 12; Ref readback-verified) | `PGFC<nnn>` | Ref (ACK + readback) |
| 57–64 | Dual (second) output | see below | see below | | see below | |

### Dual output (P57–P64, program numbers not legible in the manual)

| Item | Now (app) | Read source | Conf. | Write command | Source |
|---|---|---|---|---|---|
| Cut-off voltage point | 22.0 V (app "Parallel Shutdown Battery Voltage") | `HEEP2[3]` | M | `PTOPV<nn.n>` | Spec (remote panel) |
| Cut-off SOC point | 20 % (app "Parallel Shutdown Battery SOC") | `HEEP2[2]` or `HEEP1[11]` | ? | `PTOPVC<nnn>` | Spec |
| Recover voltage | 26.0 V | `HEEP2[15]` | M | none known | — |
| Recover SOC | 50 % | `HEEP1[13]` or `HEEP2[16]` | ? | `PDSRS<nnn>` (Ref: range 0–50 %) | Ref |
| Second-output discharge time | 0 min | `HEEP2[6]` or inside `HEEP2[16]` | ? | `PTOPD<nnn>` (999 = disable) | Spec; Ref portal: not supported |
| Recover delay | 5 min | `HEEP2[13]` | M | `PDDLYT<nnn>` (5-min steps; Ref NAK on 4 and 6) | Ref |
| Open/stop hours | 00–00 (app "INV Dual Output Time") | `HEEP2[14]` | M (format like `HEEP2[12]`) | `PTOPS<mm nn>` | Spec |
| Relay on/off (live) | — | `QDOP` silent; no H source found | — | `PTOPE<n>` (0 off, 1 on, 2/3 auto) | Spec |

## In the Home Assistant integration (0.2.0)

Read (sensors): P01, P02, P03, P05, P06–P08, P11–P13, P16, P18–P20, P22–P27, P29, P30, P31, P33–P35, P43, P46/P47, P48/P49, the clock (P51–P55), and, disabled by default, P38, P40, P56 and the dual-output cut-off / recover voltage / recover delay. Written (only with the "Enable control entities" option, owner to test): P01 (`POP01` only), P02 (`MNCHGC`), P06/P07/P08/P18–P20/P22/P23/P25 (`PE`/`PD`), P11 (`MUCHGC`), P12 (`PBCV`), P13 (`PBDV`), P16 (`PCP02` only), P26 (`PCVV`), P29 (`PSDV`), P43 (`PVENGUSE`). Details: [integration.md](integration.md#entities).

## Writing the AC output schedule (P48/P49)

No command for P46–P49 appears in any public Voltronic protocol (PI30, PI30MAX, MKS, the VMII-based remote panel), in mpp-solar, or in the solarplug-esphome captures. The Solar of Things app does not show these programs either, so the dongle traffic cannot reveal it. Guessing setter names on a live unit is unsafe: an unknown `P…` frame could match a different setting. Realistic paths:

1. **Use `QMOD`/`HEEP2[12]` to observe, and let HA drive the output another way.** There is no documented output on/off command. A smart relay on the load side is the practical alternative.
2. **Hourly priority tables do not exist here.** Newer Voltronic models schedule through 24-hour priority tables (`QOPPT`/`QCHPT`), but this firmware does not answer those queries.
3. **Ask Vevor / Voltronic support** for the "VMII RS232 protocol" revision matching fw 00040.09, or capture the traffic of the vendor PC tool (WatchPower) if it exposes P48/P49.

Note: on Voltronic units the AC-charger timer (P46/P47) is reset to 00:00 when the user enters menu 01 or 16 ([Voltacon knowledge base](https://blog.voltaconsolar.com/knowledge-base/why-does-the-inverter-reset-the-ac-charger-timers-to-0000/)). Check whether this unit does the same for P48/P49.

## How to pin the "?" rows (owner-driven, read-only for the agent)

Change **one** setting on the LCD, let the agent read `QPIRI QFLAG QBEQI HEEP1 HEEP2 HEEP3` and diff against the previous snapshot, then restore the setting. Done: P48/P49, P46/P47 and P43 (2026-10-02). Remaining: P44 (owner keeps it off), P50, the dual-output SOC and discharge-time items. BMS rows (P37–P41) cannot be tested on this installation (no BMS link), so they stay unverified.

**`HEEP1[3]` is a packed string** (`01210110230` now). Character 3 = P43. The tail `230` is probably the output voltage (P10). The other characters are still unknown (candidates: P44, P50, output mode).
