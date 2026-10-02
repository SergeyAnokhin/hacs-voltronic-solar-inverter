# Vevor Hybrid Solar Inverter GD5548JMH — Device Reference

Distilled from the vendor's English user manual (the PDF was a 336-page multi-language manual; only the English part, ~40 pages, is relevant). This is a Voltronic-compatible off-grid/hybrid inverter-charger (pure sine wave, MPPT solar charger, AC charger, optional grid-feed-in) sold by VEVOR (manufacturer: Guangdong Huahu New Energy Technology Co., Ltd.). The "LCD program" numbers below (P01…P6x) are the settings the user can change on the device; they map to values reported by the `QPIRI`/`QFLAG`/… query commands (see [inverter-protocol.md](inverter-protocol.md)). The manual is a generic family manual (models 3624 / GD5548JMH / 5548 / 6248 / 11048) and its tables are partly garbled; where it is ambiguous this is noted.

## 1. Key specifications (GD5548JMH column)

| Item | Value |
|---|---|
| System (battery) voltage | **24 V DC — confirmed on this unit** (`QPIRI` battery rating 24.0 V, model name `VMII-4000`). The manual's 48 V columns do not apply; use the 24 V values below |
| Rated output | **4000 VA / 4000 W — confirmed** (`QPIRI`); the manual's table lists 4000 / 5500 / 6200 / 11000 W per model column |
| Peak power / overload | 11000 VA peak; battery mode: 10 s @ 110–140 % load, 5 s @ > 140 % |
| AC input | 220/230/240 VAC, 90–280 VAC (Appliance mode) or 170–280 VAC (UPS mode), 50/60 Hz auto |
| AC output | 220/230/240 VAC ±5 %, 50/60 Hz ±0.1 %, pure sine |
| Transfer time | UPS mode 10 ms, Appliance mode 20 ms |
| PV (MPPT) | single MPPT, 60–500 VDC tracking range, best 300–400 V, max Voc 500 VDC, max 18 A, max PV power 6200 W (column ambiguity) |
| Max PV charge current | 100 A (column ambiguity: 100–120 A) |
| Max AC charge current | 100 A (note: P02 default total 60 A) |
| Efficiency (DC/AC) | 98 % |
| Grid-feed-in (when enabled) | 170–265 VAC, 49–51 Hz / 59–61 Hz |
| Interfaces | RS232 (RJ45, **2400 baud**), BMS/RS485 (RJ45: pin1 = 485B, pin2 = 485A), WiFi/BLE plug "Wi-Fi Plug Pro" (RS232 port, "Solar of Things" app), dry contact 3 A/250 VAC (NC/C/NO), parallel port (network function on parallel models) |
| Environment | -10…50 °C operating, -15…60 °C storage, 20–95 % RH non-condensing, ≤ 1000 m (derate above, max 4000 m), ~50 dB |
| Battery fuse | 150 A provided; recommended AC breaker 32 A (24 V system) |

> Our setup reaches the RS232 port through an Elfin RS232↔TCP gateway (TCP port 8899), not through the WiFi plug.

### Confirmed on this unit (2026-10-02, from live read-only queries)

Protocol `PI30`, model name `VMII-4000`, firmware `VERFW:00040.09`, 24 V / 4000 W. Settings read back via `QPIRI`: battery type = 2 (user-defined), bulk 29.2 V, float 29.1 V, under-voltage 21.6 V, re-charge 22.0 V, re-discharge 25.0 V, max AC charge 2 A, max total charge 50 A, input range 0 (Appliance). See [inverter-protocol.md](inverter-protocol.md) for the full mapping.

- **Battery:** the owner's bank is a standard 24 V **LiFePO4** battery run as "User-defined" (P05), with no BMS link. The inverter's battery % (`QPIGS`, `QBV`) is a lead-acid-style voltage estimate and is meaningless for LiFePO4: it read 80–95 % while the real charge was ~12 %.
- **Factory defaults** (`QDI`) match this manual's 24 V defaults exactly: cut-off 21.0 V, float 27.0 V, bulk 28.2 V, P12 23.0 V, P13 27.0 V, max AC charge 30 A, AGM. Default max total charge is 50 A (the manual says 60 A).
- The UPS-style `QMD` query reports the internal model string `INVERTEX3K`, 3000 VA, 2 × 12 V; the VA figure is wrong for this unit.
- **P25 "Record fault code" is disabled** (`QFLAG` `z`). The fault-history queries (`QPIHF`/`QPICF`) answer `NAK`, possibly for that reason.
- A sibling model, GD3024EMH (24 V, `VMII-3000`, fw 00010.13), behaves the same over RS232 ([diysolarforum thread](https://diysolarforum.com/threads/figuring-out-gd3024emh-inverter-comms.122039/)).
- **Two RS232 dialects:** PI30 (`Q…` + CRC) and the CRC-less Solar Plug / Solar of Things "H" dialect used by the vendor Wi-Fi dongle (device type `HPVINV02`, firmware date 2026-01-19). The H dialect gives the **inverter clock and PV energy counters** (`HGEN`), the **AC output schedule P48/P49** (`HEEP2[12]`, verified), dual-output and BMS-SOC settings, and four temperatures plus fan speeds. See [inverter-protocol.md](inverter-protocol.md#solar-plug-h-protocol-no-crc).
- **Inverter clock runs ~10 min slow** (2026-10-02). Schedules follow this clock: the 21:00 output-off happened at ~21:10 wall time.
- With the output switched off by the schedule (mode S), grid charging stops as well; in mode L the output stays on (fed from the grid) until the scheduled hour.
- **Not readable at all:** load-energy counters, a true SOC (no BMS), fault history (P25 off).

## 2. Operating modes (what the `QMOD` letter means)

| Mode | Meaning |
|---|---|
| Standby | Inverter not turned on (no AC output) but chargers (PV and/or utility) can still charge the battery |
| Line | Output powered from utility; charger available. Sub-states: utility charges battery + feeds load; utility+battery to load; PV+battery+utility to load; PV charges battery + utility feeds load; (if feed-in enabled) PV feeds load and grid |
| Battery | Output from battery and/or PV (PV supplies load, surplus charges battery; battery tops up when PV is insufficient) |
| Only-PV | PV alone powers the load |
| Fault | Fault code on LCD, red LED solid, buzzer |
| Power-saving (ECD) | If P08 enabled, output temporarily stops when load is very low in battery mode |

LEDs: green solid = output from battery/PV (green flashing = output from utility in Line mode); yellow solid = battery charging (flashing = battery full); red flashing = warning, red solid = fault.

LCD screens cycle with UP/DOWN: input V/output V (default) → input Hz/output Hz → battery V/output V → battery V/load % → battery V/load VA → battery V/load W → PV1 V/PV1 charge power → charge A/discharge A → PV energy today / this month / this year / total → date → time → main-board FW version → SCC FW version.

## 3. LCD settings (programs)

Entered by holding ENTER 3 s; UP/DOWN selects, ENTER confirms. These are the device's user settings. The integration reads them; some can be written by the integration's control entities (at the user's risk, partly unverified, see [integration.md](integration.md#control-entities)). Agents never write them (see [AGENTS.md](../AGENTS.md)). The values below are for the **24 V system** (this unit). Values shown by `QPIRI` correspond to P01 (output priority), P02 (max charge current), P03 (input range), P05 (battery type), P11 (max AC charge current), P16 (charger priority), P26/P27/P29 (bulk/float/cut-off), etc.

| # | Name | Options / range (default) | Why it matters |
|---|---|---|---|
| 00 | Exit | — | |
| 01 | Output source priority | Utility first / Solar first (SUB) / **SBU** (solar → battery → utility; utility only when battery falls to P12 threshold or low-voltage warning) | Main energy-flow strategy |
| 02 | Max total charging current (solar + utility) | 10 A … max, step 10 A (60 A) | Limits total battery charge current |
| 03 | AC input voltage range | Appliance 90–280 V (default) / UPS 170–280 V | Tolerance to poor grid/generator |
| 05 | Battery type | AGM (default), Flooded, User-defined, LIA, Pylontech, Techfine, Growatt, LIB-protocol, 3rd-party lithium | Lithium types auto-set P24/26/27/29; User-defined unlocks P24/26/27/29/61 |
| 06 | Auto restart on overload | disable (default) / enable | |
| 07 | Auto restart on over-temperature | disable (default) / enable | |
| 08 | ECD / power saving | disable (default) / enable | Output off at very low load in battery mode |
| 09 | Output frequency | 50 Hz (default) / 60 Hz | |
| 10 | Output voltage | 220 / **230** (default) / 240 V | |
| 11 | Max utility (AC) charging current | 2 A, then 10 A … max AC charge, step 10 A (30 A). If P02 < P11, P02 wins | |
| 12 | Voltage to return to utility (SBU mode) | 24 V system: 22–25.5 V step 0.5 V (23.0 V) | Battery level at which load switches to grid |
| 13 | Voltage to return to battery mode (SBU mode) | 24 V system: 24–29 V step 0.5 V (27.0 V, "fully charged") | Battery level at which load switches back to battery |
| 16 | Charger source priority | Solar first / Solar+Utility (default) / Only solar (in battery mode only solar charges) | |
| 18 | Alarm (buzzer) | on (default) / off | |
| 19 | Auto return to default screen | return (default) / stay | |
| 20 | Backlight | on (default) / off | |
| 22 | Beep when primary source interrupted | on (default) / off | |
| 23 | Overload bypass | disable (default) / enable (switch to line on overload in battery mode) | |
| 24 | Battery low-voltage alarm | 20.0–27.0 V (battery low alarm) | Alarm level when battery is the only source |
| 25 | Record fault codes | enable (default) / disable | |
| 26 | Bulk (CV) charge voltage | 24.0–30.0 V step 0.1 (28.2 V); user-defined battery only | |
| 27 | Float charge voltage | (27.0 V); user-defined only | |
| 28 | Reset to factory defaults | — | |
| 29 | Low DC cut-off voltage | 20.0–26.0 V step 0.1 (21.0 V); fixed regardless of load. If PV+battery present, charges without AC output | |
| 30 | Battery equalization | disable (default) / enable (Flooded or User-defined only) | |
| 31 | Equalization voltage | 24.0–30.0 V (29.2 V) | |
| 33 | Equalization time | 5–900 min step 5 (60) | |
| 34 | Equalization timeout | 5–900 min step 5 (120) | |
| 35 | Equalization interval | 0–90 days, step 1 (default not stated) | |
| 36 | Activate equalization now | disable (default) / enable | |
| 37 | BMS function switch | off (default) / on | Enables BMS comms (RS485/CAN) |
| 38 | BMS SOC under-lock | — | Lithium only: inverter shuts down when BMS SOC below value |
| 39 | BMS SOC switch to AC | — | Lithium + battery-priority: force utility charging below value |
| 40 | BMS SOC switch back to DC | — | Lithium: resume battery mode above value |
| 41 | BMS restart SOC | — | Lithium: SOC must exceed value at power-on |
| 43 | Solar supply priority | battery first / load first | Whether PV charges the battery or feeds the load first |
| 44 | Solar feed to grid | disable (default) / enable | Grid-tie feed-in |
| 45 | Reset PV energy storage | not set / reset | Clears kWh counters |
| 46 / 47 | AC charger start / stop time | 00:00–23:00, 1 h step | Scheduled utility charging window |
| 48 / 49 | AC output on / off schedule | 00:00–23:00, 1 h step | Scheduled output |
| 50 | Country grid regulation (feed-in limits) | Mode 1: 195.5–253 V, 49–51 Hz; Mode 2: 184–264.5 V, 47.5–51.5 Hz; Mode 3: 184–264.5 V, 57–62 Hz; **Mode 4 (default)**: 170–264.5 V, 47.5–51.5 Hz | |
| 51–55 | Time set: minute, hour, day, month, year | year 16–99 | Device clock (used for schedules and energy history) |
| 56 | Grid-tie current | step 1 A | Feed-in current limit |
| ~57–64 | **Dual output** group | enable/disable; voltage point (default 22 V on 24 V system), SOC point, recover voltage (default 26 V), recover SOC (default 50 %), second-output discharge time 0 / 5…990 min (P61), recover delay 0–60 min, output open/stop hour 0–23 | Second output is shed when battery is low; exact program numbers are not legible in the manual text |

Notes: 48 V-system values from the manual are omitted. Programs 04, 14, 15, 17, 21, 32, 42 are not listed in the manual.

## 4. Battery equalization (for flooded / user-defined batteries)

Enable P30, then trigger by interval (P35) or immediately (P36). Stages: Bulk → Absorption → Float, plus periodic Equalize: charges to the equalization voltage (P31), holds for P33 minutes; if voltage is not reached, time is extended until P34 timeout, then returns to float. LCD shows an equalization icon while active (and the "Battery equalization" warning is raised).

## 5. Dry contact

3 A / 250 VAC relay (NC–C–NO) signalling battery state. Powered off: NC–C closed. Normal mode: opens/closes around the low-DC-warning and float voltages. In "solar first" mode it follows the "solar to AC" / "AC to DC" voltage thresholds (P12/P13). Not readable via the serial protocol as a separate value.

## 6. Faults (red LED solid, output stops) — `QPIWS` / LCD

| Code | Event | Code | Event |
|---|---|---|---|
| 01 | Fan locked while inverter off | 08 | Bus voltage too high |
| 02 | Over-temperature / NTC not connected | 09 | Bus soft-start failed |
| 03 | Battery voltage too high | 51 | Over-current or surge |
| 04 | Battery voltage too low | 52 | Bus voltage too low |
| 05 | Output short circuit / converter over-temperature | 53 | Inverter soft-start failed |
| 06 | Output voltage too high | 55 | Over DC voltage in AC output |
| 07 | Overload time-out | 57 | Current sensor failed |
| 58 | Output voltage too low | 59 | PV voltage over limit |

## 7. Warnings (red LED flashing, inverter keeps running)

| Code | Event | Buzzer |
|---|---|---|
| 01 | Fan locked while inverter on | 3 beeps / s |
| 02 | Over-temperature | none |
| 03 | Battery over-charged | 1 beep / s |
| 04 | Low battery | 1 beep / s |
| 07 | Overload | 1 beep / 0.5 s |
| 10 | Output power derating | 2 beeps / 3 s |
| 15 | PV energy low | 2 beeps / 3 s |
| 16 | High AC input (> 280 VAC) during bus soft-start | none |
| — | Battery equalization active; battery not connected | none |

BMS information codes (lithium with comms): 60 = battery forbids charge+discharge, 69 = forbids charge, 70 = must charge, 71 = forbids discharge; "communication lost" beeps after 1 min without BMS signal at start, immediately if lost after a successful link.

## 8. Troubleshooting hints (from the manual)

| Symptom | Likely cause |
|---|---|
| Shuts down at startup after 3 s | Battery < 1.91 V/cell — recharge/replace |
| No response at power-on | Battery < 1.4 V/cell, internal fuse tripped, or AC breaker tripped |
| Mains present but runs on battery | Poor AC quality, or output priority set to Solar first; check input range (P03) |
| Relay clicks repeatedly at power-up | Battery disconnected |
| Fault 07 | Overload > 105 % timed out; also PV overvoltage derates output power |
| Fault 05 | Output short circuit; or converter > 120 °C |
| Faults 02/03 | Internal > 100 °C / battery over-charged |
| Fault 01 | Fan fault; 06/58 = output voltage < 190 V or > 260 V |

## 9. Installation facts worth remembering

- Battery cable: 25 mm² class for 3.6–4 kVA (165 A, 200 Ah typical); bolts 2 Nm; positive to positive. AC wire 12 AWG (3.6–4 kVA), PV wire 12 AWG (30 A). AC breaker 32 A (24 V system). PV must have its own DC breaker.
- Inverter needs ~20 cm side and ~50 cm top/bottom clearance; wall mounted vertically.
- Air-conditioners need 2–3 min restart delay; fast grid recovery can trip overload.
- Cold start works from battery (> 23 V) or AC.
- Never charge a frozen battery; only deep-cycle lead-acid or the listed lithium types.
