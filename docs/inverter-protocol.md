# Inverter Serial Protocol

The inverter (`QPI` → `PI30`, model `VMII-4000`, firmware `VERFW:00040.09`) speaks the Voltronic/Axpert PI30 ASCII protocol over RS232 (2400 baud), plus a handful of commands from Voltronic's **UPS** protocol (`QMD`, `QBV`, `QWS`, `QBT`, `QGR`). We reach it through an Elfin RS232↔TCP gateway (TCP port 8899), so the "serial port" is a plain TCP socket. Two tools exist: the owner's working prototype [`python_scripts/get_inverter_info.py`](../python_scripts/get_inverter_info.py) (one JSON document, unchanged) and the diagnostic [`tools/probe_inverter.py`](../tools/probe_inverter.py) (verbose, timed, CRC-checked, saves raw responses). **Agents may send only `Q…` queries**; the probe refuses anything else in code (see [AGENTS.md](../AGENTS.md)). Facts marked **(verified)** were observed on the real unit (raw samples in [`tests/fixtures/`](../tests/fixtures/)). **(spec)** means the field comes from an official Voltronic protocol document (see [Sources](#sources)) and is consistent with our samples but has not been proven by a state change. **(generic)** is community knowledge and remains a hypothesis.

## Framing (verified)

```text
request : <ASCII command> <CRC16 hi> <CRC16 lo> 0x0D
response: '(' <payload, space separated> <CRC16 hi> <CRC16 lo> 0x0D
```

- CRC-16/XMODEM (poly 0x1021, init 0) covers everything up to the CRC. A CRC byte equal to `0x28`, `0x0D` or `0x0A` is incremented by 1. **Response CRCs were OK on every answered command.**
- **Unknown commands get NO reply at all** (not even `(NAK`); the caller just times out. Verified with nonsense commands (`QPIZZ`, `QPIAB`, …).
- **`(NAK` means "command known, but refused / no data".** Only `QPIHF` and `QPICF` do this so far (see below).
- The gateway accepts both connect-per-command and one persistent connection; a connect takes ~0.03–0.05 s.
- PI17/PI18 (InfiniSolar) frames start with `^P`/`^S` (e.g. `^P005PI`), not `Q`. They were **not sent**: the read-only rule allows only `Q…`, and this unit identifies itself as PI30 anyway.

## Command catalogue

### Answering (verified)

| Command | Reply (sample) | Meaning | Poll class |
|---|---|---|---|
| `QPI` | `PI30` | Protocol id | static |
| `QMN` | `VMII-4000` | Model name | static |
| `QID` | 14-char serial | Serial number | static |
| `QSID` | `14` + serial + 6 extra chars | Serial with 2-digit length prefix (generic decode: `r[2:2+int(r[0:2])]`) | static |
| `QVFW` / `QVFW2` | `VERFW:00040.09` / `VERFW2:00000.00` | Main CPU / second (SCC) CPU firmware | static |
| `QMD` | `#####INVERTEX3K ###3000 99 1/1 230 230 02 12.0` | UPS-protocol "rated information": model `INVERTEX3K`, rated VA `3000`, PF 99 %, phases 1/1, in/out 230/230 V, 2 batteries × 12.0 V. ⚠ **Rated VA (3000) disagrees with `QPIRI` (4000 VA)**: a generic firmware string, not reliable | static |
| `QMOD` | `B` | Mode: P power-on, S standby (output off), L line, B battery, F fault, H power-saving (generic; S/B verified) | fast |
| `QPIGS` | 21 fields, see below | Live status | fast |
| `Q1` | 18 fields, see below | Extra live status (temperatures, flags) | medium |
| `QBV` | `25.6 095 ` | UPS-protocol battery info: battery voltage (V, 0.1 V resolution) and the same voltage-derived capacity % as `QPIGS[10]`. Only 2 of the 5 UPS fields are present. Redundant with `QPIGS` | not needed |
| `QPIRI` | 25 fields, see below | Ratings + current settings | slow |
| `QPIWS` | 32-char bit string | Warnings/faults (see below) | medium |
| `QFLAG` | `EabjvxyDkuz` | Option flags | slow |
| `QDI` | 25 fields | Factory-default settings (layout decoded below) | static |
| `QBEQI` | `0 060 030 050 030 29.20 000 120 0 0000` | Battery equalization (decoded below) | slow |
| `QMCHGCR` | `010 020 … 080` | Selectable *max total charge current* values (A) | static |
| `QMUCHGCR` | `002 010 … 060` | Selectable *max utility charge current* values (A) | static |
| `QOPM` | `00` | Output mode: 00 single machine | static |
| `QFS` | `00 00 00 0000 0000 0000 000.0 00.00 000.0 00.00 000.0 000.0 00.0 000 000` | Fault status. 15 fields, all zero in every state seen (incl. grid loss). Layout unknown: it matches neither the UPS-protocol `QFS` nor any PI30 document. Probably a snapshot of the last fault (code + V/I/temps) | slow |
| `QBOOT` | `0` | DSP has bootstrap: 0 = no (spec) | static |
| `QWS` | 64 × `0` | UPS-protocol warning bits. **Stayed all-zero during a real grid loss** (while `QPIWS` a5 was set), so it does not mirror the inverter's warnings. Not useful | not needed |
| `QBT` | `02` | Battery type, same code as `QPIRI[12]` (2 = user-defined) | not needed |
| `QGR` | `00` | Grid working range, same as `QPIRI[15]` (0 = Appliance) | not needed |

### Known but refused: `(NAK` (verified)

| Command | Spec meaning (PI00 InfiniSolar protocol) | Note |
|---|---|---|
| `QPIHF` | Historical fault inquiry; spec form `QPIHF<NN>` (fault index). `QPIHF00`, `QPIHF01`, `QPIHF02`, `QPIHF1` are **silent**, bare `QPIHF` answers `NAK` | Probably NAK because fault-code recording is **disabled** on this unit (`QFLAG` `z` disabled, LCD P25). Re-test if the owner enables P25 |
| `QPICF` | Current fault inquiry → `(KK NN` (fault kind, latest fault id) | NAK with no fault present (also NAK during grid loss, which is only a warning) |

### No reply: verified silent, do not retry

All were sent one per connection with a 1.0–2.0 s timeout, in mode B with grid present and PV disconnected (2026-10-02). Source column: where the command comes from.

| Command(s) | Purpose per source | Source |
|---|---|---|
| `QT` | Device clock `YYYYMMDDHHMMSS` | PI30MAX, remote-panel (VMII-based), PI00 |
| `QET`, `QEY2026`, `QEM202610`, `QED20261002`, `QEH2026100219` | PV energy total/year/month/day/hour | PI30MAX, PI00 |
| `QLT`, `QLY2026`, `QLM202610`, `QLD20261002` | Load energy total/year/month/day | PI30MAX |
| `QOPPT`, `QCHPT`, `QOPCHT` | 24-hour output / charger priority time tables | PI30MAX, GK/MK, MKS II–IV |
| `QDOP` | 2nd-output (dual output) relay status & thresholds | Remote-panel protocol, mpp-solar `pi30m044` |
| `QBATCD` | Battery charge/discharge control state | MKS II–IV, esphome-pipsolar |
| `QBMS`, `QLITH0` | BMS / lithium battery data | PI30MAX, PI30REVO |
| `QCST`, `QCVT`, `QMSCHGCR` | Charging stage, CV time, max solar charge current list | PI30 2015 customer spec |
| `QVFW3`, `QVFW4` | SCC2/SCC3 or remote-panel firmware | PI30 2015, PI30MAX |
| `QPIGS2`, `QPIGS3`, `QPGS0`, `QPGS1`, `QP2GS0` | PV2 status, parallel info | PI30MAX, PI30 2015, PI41 |
| `QGMN`, `QLED`, `QWFS` | General model number, LED strip, Wi-Fi status | PI30MAX, remote-panel |
| `QALL` | All-in-one status incl. daily/total PV energy | PI30REVO |
| `QPIBI` | Battery info | PI16 (mpp-solar) |
| `QTPR`, `QCHGS`, `QGOV`, `QGOF`, `QOPMP`, `QMPPTV`, `QPVIPV`, `QLST`, `QDI2`, `QGLTV`, `QVFTR` | Temperatures, charger status, grid/PV ranges, … | PI00 InfiniSolar spec |
| `QGS`, `QRI`, `QS`, `QMF`, `QPD`, `QHE`, `QFRE`, `QPAR`, `QLDL`, `QBYV`, `QBYF`, `QBDR`, `QSK1`–`QSK4`, `QSKT1`, `QSKT2`, `Q3PV`, `Q3PC`, `Q3OV`, `Q3OC`, `Q3LD`, `Q3YV` | UPS-protocol status, ranges, outlets, 3-phase | NUT Voltronic UPS protocol |
| `QBAT`, `QBCV`, `QBCHGS` | — | diysolarforum GD3024EMH thread (NAK there) |
| `QDAT`, `QTIME`, `QCLK`, `QRTC`, `QTM`, `QSCH`, `QTIMER`, `QPIRI2`, `QPIWS2`, `QDI3` | Guesses for clock/schedule/extended tables | own guesses |

Raw results: [`probe_candidates.json`](../tests/fixtures/probe_candidates.json), [`probe_extra.json`](../tests/fixtures/probe_extra.json), [`probe_extra2.json`](../tests/fixtures/probe_extra2.json), [`probe_run1.json`](../tests/fixtures/probe_run1.json).

**Consequences:** the device clock, **energy counters** (the LCD shows them, the serial port does not), the **P46–P49 schedules**, the dual-output state and BMS data are **not readable** on this firmware. HA must integrate `pv_watt`/`load_watt` over time (Riemann sum + utility meter) for energy.

## QPIGS fields (verified layout)

Sample (night, battery mode, grid present, 300 W load): `234.1 50.0 230.1 50.0 0483 0317 012 372 25.10 000 082 0041 00.0 000.0 00.00 00015 00010000 00 00 00000 010`

| Idx | Key (prototype) | Unit | Sample | Notes |
|---|---|---|---|---|
| 0 / 1 | `grid_voltage` / `grid_freq` | V / Hz | 234.1 / 50.0 | **Verified:** `000.0 00.0` when the grid is disconnected |
| 2 / 3 | `ac_output_voltage` / `ac_output_freq` | V / Hz | 230.1 / 50.0 | |
| 4 / 5 | `ac_output_apparent_power` / `load_watt` | VA / W | 483 / 317 | Verified against a known ~300 W load |
| 6 | `load_percent` | % | 12 | Max of W % and VA % (spec) |
| 7 | `bus_voltage` | V | 372 | |
| 8 | `battery_voltage` | V | 25.10 | |
| 9 | `battery_charge_current` | A | 0 | Integer amps |
| 10 | `battery_capacity_percent` | % | 82 | ⚠ **Voltage-derived estimate, not SOC.** The owner's LiFePO4 bank was ~12 % while this read 80–95 %. LiFePO4's flat voltage curve makes it meaningless; expose only as "inverter battery estimate" |
| 11 | `heatsink_temp` | °C | 41 | Equals `Q1[9]` exactly in every sample |
| 12 / 13 | `pv_current` / `pv_voltage` | A / V | 0.0 / 0.0 | PV disconnected; re-check with PV |
| 14 | `scc_voltage` | V | 0.00 | Battery voltage seen by the solar charger (0 when the SCC is idle) |
| 15 | `battery_discharge_current` | A | 15 | Integer amps. 15 A × 25.1 V ≈ 376 W DC for 317 W AC (≈ 84 % efficiency). With output on and 0 W load it read 0 A, so the inverter's **own idle draw is not visible** at 1 A resolution |
| 16 | status bits | — | `00010000` | Char 0 = b7 … char 7 = b0. b7 SBU priority version added, b6 configuration changed, b5 SCC firmware updated, b4 load on, b3 battery voltage steady while charging, b2 charging on, b1 SCC charging, b0 AC charging (spec). Only b4 (load on) seen so far, set in mode B even at 0 W |
| 17 | (not parsed) | 10 mV | `00` | Battery voltage offset for fans on (spec PI30 2015; older docs call it RSV1) |
| 18 | (not parsed) | — | `00` | EEPROM version (spec; older docs RSV2) |
| 19 | (not parsed) | W | `00000` | **PV charging power** (spec). Use this instead of `pv_current × pv_voltage`; re-check with PV |
| 20 | (not parsed) | — | `010` | Device status 2: b10 charging to float, b9 switched on, b8 dustproof installed (spec). `010` = switched on. See [mode S](#state-dependence) |

## Q1 fields (partly decoded)

18 fields on this unit; the community layout (mpp-solar `PI30 Q1`, 17 fields) does **not** align one-to-one. Observed samples:

```text
19:34 B, ~200 W load : 030 5472 00000 00000 65535 65535 00 00 028 039 032 032 00 00 000 5472 0000 10
19:40 B              : 030 5472 00000 00000 65535 65535 00 00 029 035 032 031 00 00 000 5472 0000 10
19:57 B, 0 W         : 030 5472 00000 00000 05472 05472 01 01 027 036 027 030 00 00 000 5472 0000 10
20:05 B, 300 W       : 030 5472 00000 00000 05472 05472 01 01 029 041 031 032 00 00 000 5472 0000 10
20:08 B, grid off    : 030 5472 00000 00000 05472 05472 01 01 027 038 027 030 00 00 000 5472 0000 10
```

| Idx | Observed | Best interpretation | Confidence |
|---|---|---|---|
| 0 | `030` constant | Unknown (not in community layout) | — |
| 1 | `5472` constant | Unknown; same value as idx 15 | — |
| 2 / 3 | `00000` | Time until end of absorb / float charging (s) | generic; consistent (not charging) |
| 4 / 5 | `65535` → `05472` | Unknown; `65535` = "invalid" placeholder. Changed between 19:40 and 19:57 together with idx 6/7 | — |
| 6 / 7 | `00` → `01` | SCC OK flag / "allow SCC on" flag | generic; plausible |
| 8 | 27–29 | Temperature (°C), probably SCC/PWM | generic |
| 9 | 35–41 | **Inverter/heat-sink temperature (°C) = `QPIGS[11]`** | verified |
| 10 / 11 | 27–32 | Temperatures (°C): community says battery / transformer. No battery sensor is fitted, so treat as internal sensors | generic |
| 12 / 13 / 14 | `00 00 000` | GPIO13 / fan lock / unused | generic |
| 15 | `5472` | Unknown (fan PWM per community, but constant) | — |
| 16 | `0000` | SCC charge power (W)? Re-check with PV | generic |
| 17 | `10` | Charge status: 10 idle, 11 bulk, 12 absorb, 13 float | generic; consistent (not charging) |

Not affected by load, grid loss or mode B. Re-check with PV producing and while charging.

## QPIRI fields (verified layout; sample `230.0 17.3 230.0 50.0 17.3 4000 4000 24.0 22.0 21.6 29.2 29.1 2 02 050 0 1 2 9 01 0 0 25.0 1 1`)

| Idx | Sample | Meaning / prototype key | Status |
|---|---|---|---|
| 0 / 1 | 230.0 / 17.3 | grid rating V / A | not parsed |
| 2 / 3 | 230.0 / 50.0 | `nominal_ac_output_voltage` / freq | verified |
| 4 | 17.3 | output rating current (A) | not parsed |
| 5 / 6 | 4000 / 4000 | `nominal_ac_output_apparent_power` / `…_active_power` | verified |
| 7 | 24.0 | `nominal_battery_voltage` → **24 V system** | verified |
| 8 | 22.0 | battery re-charge voltage (return to grid in SBU, program 12) | not parsed |
| 9 | 21.6 | `setting_batt_cutoff_voltage`, really "battery under voltage" | name misleading |
| 10 / 11 | 29.2 / 29.1 | bulk / float voltage | verified |
| 12 | 2 | battery type: 0 AGM, 1 Flooded, 2 User-defined (spec; same as `QBT`) | verified by owner |
| 13 | 02 | max AC charge current (A) | |
| 14 | 050 | max total charge current (A) | |
| 15 | 0 | input voltage range: 0 Appliance, 1 UPS (same as `QGR`) | |
| 16 | 1 | output source priority. The owner has SBU and gets `1`; the spec says 0 Utility / 1 Solar (SUB) / 2 SBU. Owner says the code is the LCD list position | see ⚠ below |
| 17 | 2 | charger source priority. The owner has "only solar" and gets `2`; the spec says 0 Utility / 1 Solar first / 2 Solar+Utility / 3 Only solar | see ⚠ below |
| 18 | 9 | max parallel units | not parsed |
| 19 | 01 | machine type: 00 grid-tie, 01 off-grid, 10 hybrid | |
| 20 | 0 | topology: 0 transformerless, 1 transformer | |
| 21 | 0 | output mode: 0 single | |
| 22 | 25.0 | battery re-discharge voltage (return to battery, program 13) | not parsed |
| 23 / 24 | 1 / 1 | PV OK condition / PV power balance | not parsed |

Newer protocols (PI30MAX) append max CV time, operation logic and max discharge current (idx 25–27); this firmware does not send them.

⚠ **Prototype off-by-one:** `get_inverter_info.py` labels idx 20 as `setting_machine_type` and idx 21 as `setting_topology`. On this unit idx 19 is the machine type, 20 the topology and 21 the output mode (values are all 0/1, so the error is invisible). **Fixed in the integration** (`parse_qpiri`, tested).

**Integration choice:** the owner's reading is used: `QPIRI[16]` 0 solar first, 1 SBU (confirmed), 2 battery first (guess); `QPIRI[17]` 0 solar first, 1 solar + utility, 2 only solar (confirmed). Unconfirmed codes are displayed but not writable.

**Priority-code check (resolved 2026-10-02):** `QDI` (factory defaults) reports charger priority `2`, and the Vevor manual names "Solar + Utility" as the P16 default, which is code 2 in the official numbering. That pointed to the official codes. On 2026-10-02 the owner re-checked the LCD while `QPIRI[17]` read `2`: P16 shows **"Only solar"**, so the menu-position reading stands. The `QDI` default `2` therefore means this firmware's factory default is "Only solar", and the manual is wrong on that point. P01 was not re-checked: `QDI` default `0` = "Solar first (SUB)" under the menu-position reading.

## QDI fields (spec layout, verified against the Vevor manual defaults)

Sample `230.0 50.0 0030 21.0 27.0 28.2 23.0 50 0 0 2 0 0 0 0 0 1 1 1 0 1 0 27.0 0 1`. These are factory defaults, not current settings. They match the manual's 24 V defaults (cut-off 21.0, float 27.0, bulk 28.2, P12 23.0, P13 27.0, AC charge 30 A, AGM).

| Idx | Value | Meaning |
|---|---|---|
| 0 / 1 | 230.0 / 50.0 | output voltage / frequency |
| 2 | 0030 | max AC charge current (A) |
| 3 / 4 / 5 | 21.0 / 27.0 / 28.2 | under-voltage / float / bulk (V) |
| 6 | 23.0 | re-charge voltage (back to grid) |
| 7 | 50 | max total charge current (A) |
| 8 / 9 / 10 / 11 | 0 / 0 / 2 / 0 | input range / output priority / charger priority / battery type (AGM) |
| 12 … 20 | 0 0 0 0 1 1 1 0 1 | buzzer (0 = on), power saving, overload restart, over-temp restart, backlight, alarm on source loss, fault-code record, overload bypass, return to default screen |
| 21 | 0 | output mode (single) |
| 22 | 27.0 | re-discharge voltage (back to battery) |
| 23 / 24 | 0 / 1 | PV OK condition / PV power balance |

## QBEQI fields (spec)

`0 060 030 050 030 29.20 000 120 0 0000` → equalization disabled, time 60 min (P33), period 30 days (P35), max current 50 A, reserved, voltage 29.20 V (P31), reserved, timeout 120 min (P34), not active, elapsed 0 h.

## QFLAG decoding (spec letters, consistent with sample)

`E` enabled / `D` disabled: `a` buzzer, `b` overload bypass, `j` power saving (ECD), `k` return to default LCD screen, `u` overload auto-restart, `v` over-temperature auto-restart, `x` backlight, `y` alarm on primary source interrupt, `z` fault code record. Sample `EabjvxyDkuz` → enabled: buzzer, overload bypass, power saving, over-temp restart, backlight, primary-interrupt alarm; disabled: return-to-default-screen, overload restart, fault record.

## QPIWS bits (spec; 32 chars on this unit)

Index = character position. Classification in brackets (F = fault, W = warning, "F/W" = fault if `a1` is set, else warning).

| Bit | Event | Bit | Event | Bit | Event |
|---|---|---|---|---|---|
| **a0** | **PV loss (W)**: reads `1` constantly while the PV array is disconnected; re-check with PV | a11 | Battery voltage high (F/W) | a22 | Battery open (W) |
| a1 | Inverter fault (F) | a12 | Battery low alarm (W) | a23 | Current sensor fail (F) |
| a2 | Bus over (F) | a13 | Reserved | a24 | Battery short (F) |
| a3 | Bus under (F) | a14 | Battery under shutdown (W) | a25 | Power limit (W) |
| a4 | Bus soft fail (F) | a15 | Battery derating (W) | a26 | PV voltage high (W) |
| **a5** | **LINE_FAIL (W): verified**, set while the grid was disconnected, cleared after reconnection | a16 | Overload (F/W) | a27 | MPPT overload fault |
| a6 | OPV short (F) | a17 | EEPROM fault (W) | a28 | MPPT overload warning |
| a7 | Inverter voltage too low (F) | a18 | Inverter over-current (F) | a29 | Battery too low to charge (W) |
| a8 | Inverter voltage too high (F) | a19 | Inverter soft fail (F) | a30 | DC/DC over-current (F) |
| a9 | Over-temperature (F/W) | a20 | Self-test fail (F) | a31 | Reserved / fault-code byte on other models |
| a10 | Fan locked (F/W) | a21 | OP DC voltage over (F) | | |

The a0 meaning comes from the PI30MAX and remote-panel (VMII-based) documents; the older HS/MS/MSX spec calls it "reserved".

## State dependence

Byte-wise diffs of snapshots, each taken with only the named condition changed:

| Change | What changed | What did **not** change |
|---|---|---|
| Schedule P48/P49 23–00 → 19–21 (output off → on) | `QMOD` S → B | `QPIRI`, `QDI`, `QFLAG`, `QBEQI`, `QMCHGCR`, `QMUCHGCR`, `QOPM`, `QPIWS`, `QFS`, `QBOOT`, `QVFW` (the schedule is unreadable) |
| Load 0 W → ~300 W (mode B) | `QPIGS` 4/5/6/8/10/11/15, `QBV`, `Q1` temperatures | `Q1` flags, `QPIWS`, `QWS`, `QFS` |
| Grid disconnected (mode B, 270 W load) | `QPIGS` 0/1 → 0, `QPIWS` a5 = 1 | `QWS`, `QFS`, `QFLAG`, `Q1` (except temps), `QPICF` stays NAK |
| Grid reconnected | `QPIWS` a5 back to 0, grid V/Hz back | — |
| Battery fell to 22.0 V (P12 back-to-grid) in SBU → **mode L**, AC charging (20:43) | `QMOD` B → L; `QPIGS` output V = grid V (bypass); charge current 2 A (= max AC charge setting); status `00010101` (**b2 charging, b0 AC charging verified**); `Q1[17]` 10 → **11 bulk (verified)**; `Q1[4..7]` back to `65535 65535 00 00`; battery % read **95 % at 22.8 V** (real ≈ 2 %) | `QPIWS`, `QWS`, `QFS`, `QPIRI` |

Snapshots: [`snapshot_schedule_23-00.json`](../tests/fixtures/snapshot_schedule_23-00.json), [`snapshot_schedule_19-21.json`](../tests/fixtures/snapshot_schedule_19-21.json), [`snapshot_B_night_output_on.json`](../tests/fixtures/snapshot_B_night_output_on.json) (all readable commands), [`snapshot_B_night_load_300w.json`](../tests/fixtures/snapshot_B_night_load_300w.json), [`snapshot_B_night_grid_off.json`](../tests/fixtures/snapshot_B_night_grid_off.json), [`snapshot_B_night_grid_restored.json`](../tests/fixtures/snapshot_B_night_grid_restored.json), [`snapshot_L_night_ac_charging.json`](../tests/fixtures/snapshot_L_night_ac_charging.json).

**Grid charging despite "Only solar" (verified, expected behaviour):** with P16 = Only solar (confirmed on the LCD), the unit still charges from the grid once it has fallen back to line mode at the P12 voltage. "Only solar" restricts charging only in battery mode, as the Vevor manual says. The current was exactly the P11 limit `QPIRI[13]` = 2 A (22.8 V × 2 A ≈ 46 W; the LCD showed ~43 W). The owner has seen this repeatedly after deep discharge. The unit returns to battery mode at `QPIRI[22]` = 25.0 V (P13).

Still to observe: PV producing (a0, `QPIGS` 12–14/19, status bits b1/b2, `Q1` 2/3/16/17), charging stages, mode S tail fields.

## Timing and reliability (2026-10-02)

Per-command inverter latency (persistent connection, verified many times): `QPIGS` 0.61–0.67 s, `QPIRI` ≈ 0.6 s, `Q1` ≈ 0.5 s, `QDI`/`QFS` ≈ 0.48 s, `QWS` ≈ 0.43 s, `QPIWS`/`QBEQI`/`QMCHGCR` ≈ 0.33 s, `QFLAG`/`QSID`/`QVFW` ≈ 0.27 s, short replies (`QMOD`, `QPI`, `QBV`, `QBT`, `QGR`, `QOPM`) ≈ 0.2 s. A silent command costs the full timeout and does **not** disturb the following command (`QT` → `QPIGS` answered normally).

| Strategy | 7 useful commands | Notes |
|---|---|---|
| Legacy (connect per command, 0.3 s gap, one `recv`) | ≈ 4.3 s | |
| Stream (1 connection, read until CR, CRC check, 0.1 s gap) | ≈ 3.3–4.8 s | |
| Original script's full list incl. `QT QET QED QOPPT QCHPT` | ≈ 16 s | those 5 commands **never answer**, so ~10 s of pure waiting |

**Lost first command after idle:** the first command of a new connection sometimes gets no reply at all (seen with `QPIGS` and `QMOD`), never later ones. All losses happened after the gateway had been idle for a minute or more: 4 of 5 manual snapshots taken after 1–5 min idle, and 1 of 5 in a controlled test (3 min idle, then connect, then `QMOD`). There were 0 losses in 39 connections made 0.2–3 s apart. The loss is a complete silence (0 bytes), and the next command on the same connection always answers. The root cause (gateway or inverter UART wake-up) is unknown. Mitigation for the integration: on a timeout, retry once immediately on the same connection (cheap, ≤ 0.7 s), or keep the connection open between polls.

Recommended poll set (all verified, ~3.5 s per full cycle on one connection):

| Class | Commands | Interval suggestion |
|---|---|---|
| fast | `QPIGS`, `QMOD` | 10–30 s |
| medium | `QPIWS`, `Q1` | 30–60 s |
| slow | `QPIRI`, `QFLAG`, `QBEQI`, `QFS` | 5–10 min (settings only change from the panel) |
| static (once at setup) | `QPI`, `QMN`, `QID`/`QSID`, `QVFW`, `QVFW2`, `QDI`, `QMCHGCR`, `QMUCHGCR`, `QOPM` | on start |
| never | everything in the "no reply" table; `QMD`/`QBV`/`QWS`/`QBT`/`QGR` add nothing over `QPIRI`/`QPIGS` | — |

Timeout per command: 1.0 s is enough (max observed answer 0.67 s), plus one retry.

## Timer settings (P46–P49): not readable (verified)

The official PI30 specs have **no read command** for the scheduled AC-output on/off or AC-charger start/stop times; `QOPPT`/`QCHPT`/`QOPCHT` (hourly priority tables, newer models) are silent, and so are all clock commands. Snapshot diff (see [State dependence](#state-dependence)): changing the schedule changed nothing except the resulting `QMOD`. HA plan: expose `QMOD` (B/L = output on, S = standby/output off) as the "AC output active" signal; the schedule itself stays on the panel.

## Setting commands (implemented, unverified on this unit)

Agents never send these to the device (see [AGENTS.md](../AGENTS.md)); the owner tests them. Implemented in [`protocol/commands.py`](../custom_components/voltronic_solar_inverter/protocol/commands.py) with exact-frame tests in [`tests/test_commands.py`](../tests/test_commands.py). Answer: `(ACK` or `(NAK`.

| Command | Meaning | Argument rule in code |
|---|---|---|
| `PE<x>` / `PD<x>` | Enable / disable a `QFLAG` option | x ∈ a b j k u v x y z |
| `POP<NN>` | Output source priority | only owner-verified codes (now `01` = SBU, assuming `POP` uses the same menu-position code as `QPIRI[16]`) |
| `PCP<NN>` | Charger source priority | only verified codes (now `02` = only solar) |
| `MCHGC<m><nn>` | Max total charging current, m = 0 (single unit) | value must be in `QMCHGCR`, < 100 A |
| `MUCHGC<nnn>` | Max utility charging current | value must be in `QMUCHGCR` |
| `PBCV<nn.n>` / `PBDV<nn.n>` | Back to utility (P12) / back to battery (P13) | 24 V: 22.0–25.5 / 24.0–29.0, step 0.5 |
| `PSDV<nn.n>` / `PCVV<nn.n>` | Cut-off (P29) / bulk (P26) voltage | 24 V: 20.0–26.0 / 24.0–30.0, step 0.1 |

Not implemented: `PBFT` float voltage (range not documented), `PBT` battery type, `PBEQ*` equalization, `PGR`, `DAT` clock, `PF` factory reset, `F50`/`F60`. There is no public power-on/off or timer command.

## Integration implementation notes

- [`protocol/client.py`](../custom_components/voltronic_solar_inverter/protocol/client.py): one persistent connection, `asyncio.Lock`, read until CR, CRC check, 2 s timeout, one retry for queries (first-command-after-idle loss), stale bytes drained before each command, transparent reconnect when the gateway closed the connection, 0.1 s gap between exchanges. Writes are never retried.
- Only answering commands are polled; see [integration.md](integration.md).
- The gateway address comes from the config flow (the prototype hard-codes `192.168.1.47:8899`).

## Sources

| Source | What it contributed |
|---|---|
| [jblance/mpp-solar `protocols/`](https://github.com/jblance/mpp-solar/tree/master/mppsolar/protocols) (`pi30.py`, `pi30max.py`, `pi30m044.py`, `pi30revo.py`, `pi16.py`, `pi41.py`) | Field layouts (`Q1`, `QPIGS` tail, `QBEQI`, `QDI`), `QDOP`, `QALL`, `QLITH0`, `QPIBI`, energy commands |
| [BMBIT-oss/Various-Solar-Protocols-Docs](https://github.com/BMBIT-oss/Various-Solar-Protocols-Docs) | Official PDFs: PI30 HS/MS/MSX 2014, PI30 customer 2015 (`QCST`, `QCVT`, `QMSCHGCR`, `QVFW3/4`, QPIGS fields 17/18 = fan offset / EEPROM version), PI30MAX 2021, PI30 GK/MK, PI30REVO, PI41, PI00 InfiniSolar (`QMD`, `QPIHF`, `QPICF`, `QTPR`, `QCHGS`, …) |
| [ardupic/voltronic-inverter-communication-protocols](https://github.com/ardupic/voltronic-inverter-communication-protocols) | *Axpert Remote Panel Protocol (VMIII/KING/MKSIII)*, explicitly "based on the Axpert VMII RS232 protocol": `QWFS`, `QDOP`, QPIWS a0 = PV loss; MKS II–IV (`QBATCD`, `QOPCHT`); MAX / MAXII / VMIV |
| [NUT Voltronic UPS protocol](https://networkupstools.org/protocols/voltronic.html) | UPS-protocol commands: `QMD`, `QBV`, `QWS`, `QBT`, `QGR` (answering here) and many silent ones |
| [syssi/esphome-pipsolar](https://github.com/syssi/esphome-pipsolar), [ned-kelly/docker-voltronic-homeassistant](https://github.com/ned-kelly/docker-voltronic-homeassistant), [fadmaz/siseli-ha](https://github.com/fadmaz/siseli-ha) | Command sets used in practice (`QBATCD`, `QPGS0`, `QPIGS2`, `QET/QLT`); nothing beyond the above |
| [diysolarforum: GD3024EMH comms](https://diysolarforum.com/threads/figuring-out-gd3024emh-inverter-comms.122039/) | A sibling 24 V VMII-3000 unit (fw 00010.13): identical `QDI`; `QT`, `QET`, `QEY`, `QVFW3`, `QBAT`, `QBCV`, `QBCHGS` NAK there |
