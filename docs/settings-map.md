# LCD Settings Map (P01–P68): read sources and write commands

For every LCD program of the Vevor GD5548JMH (see [inverter-vevor-gd5548jmh.md](inverter-vevor-gd5548jmh.md#3-lcd-settings-programs)), this page lists where its current value can be **read** over RS232 and which command is known to **write** it. Reads come from the PI30 dialect (`Q…` + CRC) and the CRC-less Solar Plug H dialect; both are described in [inverter-protocol.md](inverter-protocol.md). Values in the "Now" column were read on 2026-10-02 before the owner's test changes (at 21:45 the owner left P02 = 40 A, P12 = 22.5, P13 = 25.5, P26 = 29.1, P27 = 29.0, P29 = 21.7) and match the owner's Solar of Things screenshots (`docs/screenshots/solar_of_things/`, not in the repository).

**Write commands are NOT tested by agents.** Agents never send them (see [AGENTS.md](../AGENTS.md)); the owner verifies each one on the real unit, one at a time, and reads the value back afterwards. A "Ref" write was ACKed on the sibling `VMII-6200` fw 40.05 in [solarplug-esphome](https://github.com/rutgerputter/solarplug-esphome/blob/main/docs/protocol/WRITE_SURFACE.md). "Spec" means it appears in an official Voltronic protocol PDF but was not observed on a VMII unit. All write commands are sent **with** CRC-16/XMODEM (same framing as PI30 queries) and answer `(ACK` or `(NAK`.

Confidence of the read position: **V** = verified here by a change (owner changed the setting, the value followed); **M** = value matches the app/LCD but was not changed; **R** = only the reference project's mapping; **?** = unknown.

| P | Setting | Now | Read source | Conf. | Write command (owner to test) | Write source |
|---|---|---|---|---|---|---|
| 01 | Output source priority | SUB (owner switched 2026-10-11 from SBU) | `QPIRI[16]` (`0` = SUB solar → utility → battery, `1` = SBU, menu-position codes) | V (owner, both codes) | `POP<NN>`: `POP00` SUB / solar first, `POP01` SBU, `POP02` utility first | Ref (mapping best-guess there too); PI30 spec |
| 02 | Max total charge current | 50 A | `QPIRI[14]`, `HEEP1[1]` | **V** (50 → 40 A moved both; `QBEQI[3]` equalization max current follows P02) | `MNCHGC<nnn>` (Ref, ACK + readback) or PI30 `MCHGC<nnn>`; allowed values = `QMCHGCR` | Ref / spec |
| 03 | AC input range | Appliance | `QPIRI[15]`, `QGR` | M | `PGR<NN>` (00 Appliance, 01 UPS) | Spec |
| 05 | Battery type | User ("USE", 3rd on the LCD list AGM / FLd / USE → code `2`) | `QPIRI[12]`, `QBT`, `HBAT[0]` | M | `PBT<NN>` (Ref: `03` = LIA, `04` = PYL on its firmware). ⚠ Changing the type may overwrite P26/P27/P29 with the type's presets; re-read them afterwards | Ref |
| 06 | Overload auto-restart | off | `QFLAG` `u` | M | `PEu` / `PDu` | Ref |
| 07 | Over-temp auto-restart | on | `QFLAG` `v` | M | `PEv` / `PDv` | Ref |
| 08 | Power saving (ECD) | on | `QFLAG` `j` | M | `PEj` / `PDj` | Spec |
| 09 | Output frequency | 50 Hz | `QPIRI[3]` | M | `F50` / `F60` (spec says standby only) | Spec |
| 10 | Output voltage | 230 V | `QPIRI[2]`, `HEEP1[3]` chars 8–10 (vendor tool) | M | `V<nnn>` (vendor tool; remote-panel spec "for VMIII") | Tool / spec |
| 11 | Max AC (utility) charge current | 2 A | `QPIRI[13]`, `HEEP1[2]` | M (2 A seen as real charge current) | `MUCHGC<nnn>`; allowed = `QMUCHGCR` (`002 010 … 060`) | Ref (ACK + readback) |
| 12 | Back-to-grid voltage | 22.0 V | `QPIRI[8]`, `HEEP2[4]` | **V** (22.0 → 22.5) | `PBCV<nn.n>` | Ref (ACK + readback) |
| 13 | Back-to-battery voltage | 25.0 V | `QPIRI[22]`, `HEEP2[5]` | **V** (25.0 → 25.5) | `PBDV<nn.n>` | Ref (ACK + readback) |
| 16 | Charger source priority | Solar and utility (owner switched 2026-10-11; before: solar first, only solar) | `QPIRI[17]` (`0` = solar first, `1` = solar + utility, `2` = only solar) | V (owner, all three) | `PCP<NN>`: `PCP00` solar first, `PCP01` solar + utility, `PCP02` only solar | Ref (round-trip confirmed there, same codes) |
| 18 | Buzzer | on | `QFLAG` `a` | M | `PEa` / `PDa` | Ref |
| 19 | Return to default screen | off | `QFLAG` `k`, `HEEP1[4]` (`002` = off, ref `012` = on) | M / R | `PEk` / `PDk` | Ref |
| 20 | Backlight | on | `QFLAG` `x` | M | `PEx` / `PDx` | Ref |
| 22 | Beep on source loss | on | `QFLAG` `y` | M | `PEy` / `PDy` | Ref |
| 23 | Overload bypass | on | `QFLAG` `b` | M | `PEb` / `PDb` | Spec |
| 24 | Battery low-alarm voltage | 23.6 V (owner, 2026-10-11) | `HEEP2[3]` | **V** (LCD 23.2 → 23.6 moved `HEEP2[3]`; until 0.4.12 the integration wrongly read `HEEP2[1]`) | `PSLV<nn.n>` (vendor tool, SoT dongle channel; untested here. Ref portal on fw 40.05: "Command not supported") | Tool |
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
| 39 | BMS SOC → switch to AC | 20 % | `HEEP1[11]` (vendor tool; `HEEP2[2]` is the second-output shutdown SOC) | M | `BMSB2UC<nnn>` (vendor tool); PI30 `PBCC<nnn>` | Tool / spec |
| 40 | BMS SOC → back to battery | 95 % | `HEEP1[12]` | M (app 95) | `BMSU2BC<nnn>` (vendor tool); PI30 `PBDC<nnn>` | Tool / spec |
| 41 | BMS restart (startup) SOC | 50 % | `HEEP1[13]` (vendor tool; `HEEP2[16]` chars 0–1 are the second-output restore SOC) | M | `BMSSRC<nnn>` (vendor tool) | Tool |
| 43 | Solar supply priority (PV to battery first = BLU, or to load first = LBU) | LBU (changed by the owner 2026-10-02) | `HEEP1[3]` **4th character**: `0` = BLU, `1` = LBU | **V** (BLU → LBU flipped it `0` → `1`) | `PVENGUSE00` = BLU, `PVENGUSE01` = LBU | Ref |
| 44 | Solar feed to grid (export PV surplus back through the AC input; needs grid-operator approval) | off (app "Grid Connection Function: Disable") | `HEEP1[18]` (vendor tool; `0` now) | M | `GRIDFEED00` / `GRIDFEED01` (vendor tool); PI30 `PEd` / `PDd` | Tool / spec. Owner does not want export, so leave it off |
| 45 | Reset PV energy | — | — | — | `^S???CLE` (vendor tool "clear generation data"); PI30 `RTEY`. Both **erase** the PV energy history; do not use casually | Tool / spec |
| 46 / 47 | AC charger start / stop hour | 01–02 (changed by the owner 2026-10-02) | `HEEP2[11]` (`HHhh`) | **V** (`0000` → `0102`) | `^S???ACCT<HH>-<HH>` (untested here, see below) | Tool |
| 48 / 49 | AC output on / off hour | 23–00 | `HEEP2[12]` (`HHhh`) | **V** (19–21 → 23–00) | `^S???ACLT<HH>-<HH>` (untested here, see below) | Tool |
| 50 | Grid regulation (feed-in) | Mode 2 (app) | `HEEP1[3]` char 1 (vendor tool; reads `1`, so the app's mode numbers may start at 1) | ? | `^S???RS<NN>` with `00`–`04` = Mode0–Mode4 (vendor tool); remote-panel spec `SRS<nn>` | Tool / spec |
| 51–55 | Clock | ~10 min slow | `HGEN[0..1]` (YYMMDD HH:MM) | M (app) | `^S???DAT<yymmddhhmmss>` (vendor tool and dongle; the `???` are three literal question marks; the reference unit answered `^1`); PI30 `DAT<yymmddhhmmss>` | Tool / Ref / spec |
| 56 | Grid-tie current | 12 A | `HEEP1[17]` | M (app 12; Ref readback-verified) | `PGFC<nnn>` | Ref (ACK + readback) |
| 60–68 | Dual (second) output | see below | see below | | see below | |

### Dual output (P60–P68)

**Numbers and meaning from the vendor manual** (read on 2026-11-12 from the owner's copy of the vendor manual (`HYBRID-SOLAR-INVERTER（GD5548JMH）_1784720921157.pdf`, 336 pages, several languages; English program tables on PDF pages 30-31 = printed pages 27-29); the text layer loses the numbering, render the page with `pdftoppm -f 30 -l 31 -r 90 -png`): P60 dual output **Disable (default) / Use**; P61 voltage point (default 44.0 V on 48 V, **22.0 V on 24 V**; the second output is cut off when the battery voltage is lower); P62 SOC point (lithium with BMS only); P63 recover voltage (default 52 V / **26 V**); P64 recover SOC (default 50 %, lithium with BMS only); P65 discharge time on the second output (disable, then 0–990 min, step 5; "if the battery discharge time reaches the P65 time and the P60 function is not triggered, the output is turned off"); P66 recover delay time 0–60 min; **P67 Output Open Time and P68 Output Stop Time, 0–23 h** (their LCD pages carry the same OUTPUT icon as P48/P49). Earlier notes called the group "P57–P64, numbers not legible"; that was wrong.

**Correction (owner, 2026-11-12):** P48/P49 are the schedule of the **main** output only; the second output has its own time program, P67/P68 (`HEEP2[14]`, app "INV Dual Output Time"). Earlier notes and a test plan that tied the second output to P48/P49 were wrong. The manual does not say whether the second output needs the main output to be on. See [research-summary.md](research-summary.md#correction-owner-2026-11-12).

| Item | Now (app) | Read source | Conf. | Write command | Source |
|---|---|---|---|---|---|
| P60 Dual output enable (0 disable / 1 use) | `1` (the owner set it to `0` on the LCD, then `PDAULC01` flipped it back on 2026-11-12) | `HEEP2[0]` | **V** (`PDAULC01` ACKed and `HEEP2[0]` 0 → 1) | `PDAULC00` / `PDAULC01` | Tool (SoT dongle channel "dual remote switch"); **verified on the unit** |
| P61 Cut-off voltage point | 22.0 V (app "Parallel Shutdown Battery Voltage") | `HEEP2[1]` | M (vendor tool) | `PDSDV<nn.n>` (vendor tool); remote-panel spec `PTOPV<nn.n>` | Tool / spec |
| P62 Cut-off SOC point | 20 % (app "Parallel Shutdown Battery SOC") | `HEEP2[2]` | M (vendor tool) | `PDSDS<nnn>` (vendor tool); remote-panel spec `PTOPVC<nnn>` | Tool / spec |
| P63 Recover voltage | 26.0 V | `HEEP2[15]` | M | `PDSRV<nn.n>` | Tool |
| P64 Recover SOC | 50 % | `HEEP2[16]` chars 0–1 | M (vendor tool) | `PDSRS<nnn>` (Ref: range 0–50 %) | Ref / tool |
| P65 Second-output discharge time (disable / 0–990 min) | 0 (= disable?) | `HEEP2[16]` chars 2–4 | M (vendor tool) | `PDDCGT<nnnn>` (4 digits, vendor tool); remote-panel spec `PTOPD<nnn>` | Tool / spec; Ref portal: not supported |
| P66 Recover delay | 5 min | `HEEP2[13]` | M | `PDDLYT<nnn>` (5-min steps; Ref NAK on 4 and 6) | Ref |
| P67 / P68 Output open / stop time (0–23 h) | 00–00 (app "INV Dual Output Time") | `HEEP2[14]` | M (format like `HEEP2[12]`) | no setter in the vendor tool; remote-panel spec `PTOPS<mm nn>` (untested) | Spec |
| Relay on/off (live) | on in mode L with P60 on; off in mode S | `HSTS[2]` char 4 (1 = on) | **V** (both directions: `PDAULON00` 1 → 0 and `PDAULON01` 0 → 1, mode L, 2026-11-12) | `PDAULON00` off / `PDAULON01` on (vendor tool "auxiliary output off / on"); remote-panel spec `PTOPE<n>` | Tool / spec |

## In the Home Assistant integration (0.2.0; extended 2026-11-12)

Since 2026-11-12 (owner's request) the service-tool setters below are **also exposed as experimental control entities**, none of them verified on the device: the four schedule hours (`^S???ACLT` / `^S???ACCT`), P24 `PSLV`, the second-output mode switch (`PDAULC`), the second-output on/off switch (`PDAULON`, assumed state), `PDSDV` / `PDSDS` / `PDSRV` / `PDSRS` / `PDDLYT` / `PDDCGT`, the battery discharge current limit `DISCC` (assumed state), the BMS SOC points `BMSSDC` / `BMSB2UC` / `BMSU2BC` / `BMSSRC` (disabled by default) and a button that sets the inverter clock (`^S???DAT`). Not exposed on purpose: the "never send" list, `GRIDFEED` (the owner keeps feed-in off), `^S???RS`, `EXTCT`, `POPM`, `V`, `PGFP`, `EZCTP`. Details: [integration.md](integration.md#control-entities).

Read (sensors): P01, P02, P03, P05, P06–P08, P11–P13, P16, P18–P20, P22–P27, P29, P30, P31, P33–P35, P43, P46/P47, P48/P49, the clock (P51–P55), and, disabled by default, P38, P40, P56 and the dual-output cut-off / recover voltage / recover delay. Written (control entities, at the user's risk, owner to test): P01 (`POP00`, `POP01`), P02 (`MNCHGC`), P06/P07/P08/P18–P20/P22/P23/P25 (`PE`/`PD`), P11 (`MUCHGC`), P12 (`PBCV`), P13 (`PBDV`), P16 (`PCP00`, `PCP01`, `PCP02`), P26 (`PCVV`), P29 (`PSDV`), P43 (`PVENGUSE`). Details: [integration.md](integration.md#entities).

## Other community-known setters (not used here)

Checked 2026-10-11 against [mpp-solar `pi30.py`](https://github.com/jblance/mpp-solar/blob/master/mppsolar/protocols/pi30.py) and the solarplug-esphome write surface. Besides the commands in the table above, the community lists these; none is known to work on VMII firmware. `PBATCD` and `PBATMAXDISC` are implemented at the owner's request (2026-10-11, owner tests them; see [integration.md](integration.md#control-entities)); the rest are not:

| Command | Meaning (source) | Note |
|---|---|---|
| `PBATCD<abc>` | Battery charge / discharge enable bits (mpp-solar, PI30 MAX family) | Implemented (select). Bits: a = discharge, b = discharge with standby kept, c = charge; `000` clears the overrides; `011`/`010` shut the unit down when PV and grid are missing (left out). No read-back query. Forum report: both off gave warning 60 on a MAX |
| `PBATMAXDISC<nnn>` | Max battery discharge current (MAX family; `000` = off, 30–150 A on 48 V) | Implemented (number); read-back only via `QPIRI` on MAX units, absent here |
| `POPLG`, `POPM`, `PPCP`, `PPVOKC`, `PSPB` | Operation logic, output mode / parallel, PV-OK condition, solar power balance (mpp-solar, MAX / 4000–5000 models) | other model families |
| `BTA<±0n>` | Battery voltage reading calibration (mpp-solar) | changes measurements; avoid |
| `PSAVE` | Save EEPROM (mpp-solar) | not needed on VMII (ACK already persists) |
| `PF` | Reset all settings to defaults | **never** send |
| `PCP03`, `PVENGUSE02` | Extra codes (solarplug-esphome: untested) | not offered by this firmware's LCD |

## Setters from the vendor service tool (2026-11-12)

The manufacturer's service tool ([zhuaibai/TQF-AllInOne](https://github.com/zhuaibai/TQF-AllInOne), source in [inverter-protocol.md](inverter-protocol.md#sources)) has a settings page for device type `HPVINV02`, which this unit reports. It confirms the names and value formats of the commands in the table above (voltages as `nn.n`, currents and percentages as three digits, `POP00` SUB / `POP01` SBU, `PCP00` solar first / `PCP01` solar + utility / `PCP02` only solar, `PBT00`–`PBT08` = AGM, FLD, USE, LIA, PYL, TQF, GRO, LIB, LIC) and adds the ones below. Every setter is sent like the PI30 ones: ASCII + CRC-16/XMODEM + CR. **None of them was sent to this unit; the agent never sends them, the owner tests each one.** The read-back queries `QCVV`, `QBFT`, `QOP`, `QCP` answer on this unit, which shows that the firmware implements this tool's command set.

| Command | Meaning (tool label) | Read-back | Note |
|---|---|---|---|
| `^S???ACCT<HH>-<HH>` | AC charging time, P46/P47 | `HEEP2[11]` | see the next section |
| `^S???ACLT<HH>-<HH>` | Inverter (AC) output time, P48/P49 | `HEEP2[12]` | see the next section |
| `^S???DAT<yymmddhhmmss>` | System clock | `HGEN[0..1]` | also seen from the dongle on the sibling unit (answer `^1`) |
| `PSLV<nn.n>` | Low-battery alarm voltage, P24 | `HEEP2[3]` | the sibling's cloud portal reported "not supported" on fw 40.05 |
| `PDAULC00` / `PDAULC01` | Dual output mode off / on | `HEEP2[0]` | |
| `PDAULON00` / `PDAULON01` | Second (auxiliary) output off / on now | `HSTS[2]` char 4 | see [on/off options](#switching-the-ac-output-from-home-assistant-options) |
| `PDSDV<nn.n>` / `PDSDS<nnn>` | Second-output shutdown voltage / SOC | `HEEP2[1]` / `[2]` | |
| `PDSRV<nn.n>` / `PDSRS<nnn>` | Second-output restore voltage / SOC | `HEEP2[15]` / `[16]` chars 0–1 | |
| `PDDLYT<nnn>` / `PDDCGT<nnnn>` | Second-output restore delay / discharge time | `HEEP2[13]` / `[16]` chars 2–4 | |
| `BMSB2UC<nnn>` / `BMSU2BC<nnn>` / `BMSSRC<nnn>` | BMS SOC: back to AC (P39) / back to battery (P40) / restart after low power (P41) | `HEEP1[11]` / `[12]` / `[13]` | no BMS link here, cannot be checked |
| `GRIDFEED00` / `GRIDFEED01` | Grid-connected (feed-in) function off / on, P44 | `HEEP1[18]` | owner keeps it off |
| `^S???RS<NN>` | Grid-connection protocol Mode0–Mode4, P50 | `HEEP1[3]` char 1 | |
| `EXTCT00` / `EXTCT01` | External CT off / on | `HEEP1[3]` char 7 | |
| `DISCC<nnn>` | Battery discharge current limit (A) | `HEEP3[6]` (layout of another device type) | on the page of another type of the tool; also a Solar of Things dongle channel. The vendor's counterpart of `PBATMAXDISC` |
| `PGFP<nnnnn>` / `EZCTP<nnnn>` | Grid-connected power / zero-adjust power (CT) | `HEEP3[5]` / `[3]` | other device type of the tool |
| `POPM<NN>` | Output mode: 00 single, 01 parallel, 02–04 three-phase | `HEEP1[8]` | never change on a single unit |
| `V<nnn>` | Output voltage, P10 | `HEEP1[3]` chars 8–10 | |
| `PEb` / `PDb`, `PEk` / `PDk`, `PEy` / `PDy`, `PEz` / `PDz` | Overload bypass, auto return to home screen, input-source prompt sound, fault history | `QFLAG` | same as the table above |

**Never send** (present in the tool as service functions): `PF` (labelled "system reset"; factory reset in PI30), `^S???CLE` (clears the PV energy counters), `BTA+1` / `BTA-1` and `IVA+01` / `IVA-01` (shift the battery / inverter voltage calibration), `F…` (output frequency; the tool's argument mapping is unclear), `HOSTCRCEN` (makes the unit add a CRC to its H replies; this integration's H parser expects none; `HOSTCRCDN` switches it back), `PSAVE`.

### Owner's first results (2026-11-12, v0.4.17)

| Command | Result on the unit |
|---|---|
| `^S???DAT…` (HA button) | **works**: the clock offset went from −3 to −1 min (minute resolution, so the `^S` family is understood) |
| `PDAULON01` (HA switch) | ACKed; the *Second output* switch is an assumed state and does not follow changes made on the inverter. The tool's read-back `HSTS[2]` char 4 is still unverified here (it read `0` both times it was sampled with the output off); `tools/write_probe.py PDAULON01` diffs the snapshot to find the real read-back |
| `^S???ACLT11-19`, `^S???ACLT12-18` (HA numbers) | **no answer at all** within 2 s, nothing changed on the LCD. The frame is built like the dongle's verified `^S???DAT` frame (CRC checked) |
| `write_probe.py --try ACLT 12 18` and `--try ACCT 1 2` (4 variants each, 8 s wait) | **all 8 silent**; `HEEP2` unchanged. The firmware does not know these commands in any form tried. Details and untried ideas: [research-summary.md](research-summary.md#research-log-2026-11-12-how-the-findings-were-made-results-failures) |
| `PDAULON01` / `PDAULON00` via `write_probe.py` | `(ACK` in 0.15 s each, **no token changed** in `HSTS HEEP1 HEEP2 HGEN QMOD`, both with the dual output off and, after `PDAULC01` (P60 on), still in mode S: effect and read-back unknown. To test with the main output on |
| `PDAULON00` via `write_probe.py`, **mode L**, P60 on | `(ACK`; **`HSTS[2]` char 4 `1` → `0`**: `PDAULON00` switches the second output off and `HSTS[2]` char 4 is the read-back. (The second output was already on before `PDAULON01`, so `PDAULON01` showed no change.) HA reads it since 0.4.18, the switch is no longer an assumed state. Later run: `PDAULON00` 1 → 0 and `PDAULON01` 0 → 1 both confirmed; one earlier run found the value back at `1` after an `OFF` without a known cause (self-restore not excluded) |
| `PDAULC01` via `write_probe.py` | `(ACK`, `HEEP2[0]` 0 → 1: **works, `PDAULC` = P60** |

## Writing the schedules (P46–P49): candidate found 2026-11-12

No public Voltronic protocol has a command for P46–P49 (checked: PI30, PI30MAX, MKS, the VMII-based remote panel, the official *Axpert KS&MKS&V RS232 Protocol*, mpp-solar, the solarplug-esphome dongle captures; the Solar of Things app does not show these programs). The vendor service tool does:

```text
^S???ACCT<start>-<end>   AC charging time   (P46/P47), e.g. ^S???ACCT01-02
^S???ACLT<start>-<end>   AC output time     (P48/P49), e.g. ^S???ACLT12-19
```

- `???` are three literal question marks (the tool sends the string as is). Hours are two digits, joined by `-`, followed by CRC + CR.
- The tool pauses its polling and waits 1–2 s before sending ("without this delay it errors"), and its drop-downs offer `01`–`24` with start < end. The LCD allows 00–23 and windows across midnight (the owner uses 23–00), so the tool's limits are probably only its own.
- Expected answer: `(ACK`, or the PI18-style `^1` that the sibling unit gave to `^S???DAT`; `(NAK` / `^0` = refused; no answer = the firmware does not know the command.
- Example frames (computed, not sent): `^S???ACLT12-20` = `5e 53 3f 3f 3f 41 43 4c 54 31 32 2d 32 30 ce 29 0d`, `^S???ACLT12-19` = `5e 53 3f 3f 3f 41 43 4c 54 31 32 2d 31 39 0b 52 0d`, `^S???ACCT01-02` = `5e 53 3f 3f 3f 41 43 43 54 30 31 2d 30 32 33 6c 0d`.

**Status 2026-11-12: these commands got no answer on the unit (all variants), so the four hour numbers in HA do not work; the plan below is kept for reference.** First test for the owner (one change, read back, restore): either with the new number entities in HA (change one hour, check *AC output off time* / the LCD, restore it), or by hand with the integration disabled: read `HEEP2`; send one `^S???ACLT` frame that moves only the off hour by one (both hours inside 01–23, start < end); read `HEEP2[12]` and check P48/P49 on the LCD; restore the old window the same way. Only after that try: hour `00`, a window across midnight, equal hours, and whether the output reacts at once when the current hour enters or leaves the window. Then the same for `^S???ACCT` and `HEEP2[11]`.

Notes: the schedules run on the inverter clock (`HGEN`, about 10 min slow here; `^S???DAT` could correct it). On Voltronic units the AC-charger timer (P46/P47) is reset to 00:00 when the user enters menu 01 or 16 ([Voltacon knowledge base](https://blog.voltaconsolar.com/knowledge-base/why-does-the-inverter-reset-the-ac-charger-timers-to-0000/)); check whether this unit does the same. Since 2026-11-12 (owner's request) the integration has four experimental number entities that send these commands (*AC output on / off hour*, *AC charger start / stop hour*; see [integration.md](integration.md#control-entities)). Each sends the whole window and accepts answers `(ACK` / `(NAK` as well as `^1` / `^0`. The commands are still unverified on this unit.

## Switching the AC output from Home Assistant: options

No command that switches the main AC output on or off is known for this device type: none in the public protocols, and none on the vendor tool's `HPVINV02` page. The live state is readable (`QMOD` S/C = off, `QPIGS` status 2 b9, `HSTS[1]` char 2, `HSTS[2]` char 3). Ways to get there, most promising first:

| # | Way | Command(s) | Confidence / risk |
|---|---|---|---|
| 1 | Use the output schedule as the switch: "on" = a window that contains the current inverter-clock hour, "off" = a window that does not | `^S???ACLT<HH>-<HH>` | Command very likely exists (vendor tool page of this device type), untested. Unknown: whether the output reacts at once, hour `00`, windows across midnight. Whole hours only. It is the setting the owner already uses on the LCD, so the inverter's behaviour is the known one |
| 2 | Second (dual) output, if the unit has the second output terminals and the load is moved to them | `PDAULON00` / `PDAULON01`, mode `PDAULC00` / `PDAULC01` | Commands on the tool's `HPVINV02` page ("auxiliary output off / on"); `HEEP2[0]` = `1` says the dual output mode is on. Untested; the inverter stage keeps running, so its own consumption stays |
| 3 | Power switch command of the vendor's UPS types | `SWON`, `SWOFF<NN>` (`00` cancel, `01` shut down, further codes = delay 10–30 min) | Only on the tool's `UPSCYX01` / `LB6` pages, not on `HPVINV02`: a guess for this firmware. A full shut-down may not be reversible over RS232 (Axpert owners report that a switched-off unit only wakes by its switch or PV). Only with the owner at the unit |
| 4 | Keep the output on and steer the sources instead | `POP`, `PCP`, `MUCHGC`, `PBATCD`, `DISCC` | Already implemented or listed; does not switch the 230 V off |
| 5 | Hardware: a contactor / smart relay on the load side, or a relay across the unit's power switch | — | No protocol risk |

## How to pin the "?" rows (owner-driven, read-only for the agent)

Change **one** setting on the LCD, let the agent read `QPIRI QFLAG QBEQI HEEP1 HEEP2 HEEP3` and diff against the previous snapshot, then restore the setting. Done: P48/P49, P46/P47 and P43 (2026-10-02). Remaining: P44 (owner keeps it off), P50, the dual-output SOC and discharge-time items; since 2026-11-12 the vendor service tool gives their positions, so a change would only confirm them. BMS rows (P37–P41) cannot be tested on this installation (no BMS link), so they stay unverified.

**`HEEP1[3]` is a packed string** (`01210110230` now). Character 3 = P43 (verified). The vendor service tool gives the rest: AC input range, grid protocol (P50), battery type, P43, overload restart, input-source prompt, over-temperature restart, external CT, then the output voltage `230` ([field table](inverter-protocol.md#field-meanings-from-the-vendor-service-tool-2026-11-12)); these are not yet confirmed by a change on this unit.
