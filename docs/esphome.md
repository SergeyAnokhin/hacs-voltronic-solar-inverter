# ESPHome on an ESP32 + MAX3232 (alternative to the Elfin gateway)

The inverter's RS232 port can also be read by an ESP32 running ESPHome, connected through a MAX3232 RS232↔TTL level shifter. The folder [`esphome/`](../esphome/) holds two ready configurations: **native** ([`vevor-inverter.yaml`](../esphome/vevor-inverter.yaml)), where the ESP32 itself speaks PI30 through ESPHome's built-in [`pipsolar`](https://esphome.io/components/pipsolar/) component and publishes entities to Home Assistant over the ESPHome API, and **bridge** ([`vevor-bridge.yaml`](../esphome/vevor-bridge.yaml)), where the ESP32 is only a transparent RS232↔TCP bridge on port 8899 (drop-in for the Elfin gateway) and this repository's HACS integration keeps doing everything. Both configs pass `esphome config` and compile (ESPHome 2026.9.1, native with the controls package enabled). Neither has been run on the real inverter yet.

## Which one to use

| | Native (`vevor-inverter.yaml`) | Bridge (`vevor-bridge.yaml`) |
|---|---|---|
| Needs the HACS integration | no (ESPHome integration only) | yes, host = ESP32 IP, port 8899 |
| Protocol | PI30 only: `QPIGS`, `QPIRI`, `QMOD`, `QFLAG`, `QPIWS` | everything the integration does: PI30 + Solar Plug H dialect |
| PV energy counters, inverter clock, P46–P49 schedules, temperatures `HTEMP`, `Q1`, `QBEQI` | **no** (not in `pipsolar`; compute energy in HA with an Integral helper on "PV charging power") | yes |
| Writes | opt-in package [`packages/vevor-controls.yaml`](../esphome/packages/vevor-controls.yaml) | the integration: always on (README caution) |
| Extra component | none (core ESPHome) | [`oxan/esphome-stream-server`](https://github.com/oxan/esphome-stream-server) (external) |

A third option is the external [solarplug-esphome](https://github.com/rutgerputter/solarplug-esphome) component (H dialect, energy counters, beta writes). It was built on a 48 V PowMr VMII-6200; its write value ranges are for 48 V, so it is not configured here.

## Wiring

Full build guide with parts list, pin tables, how to find the RJ45 pins, first test and troubleshooting: [esphome-hardware.md](esphome-hardware.md).

![Wiring overview](images/esphome-wiring.svg)

Short version: ESP32 `3V3`/`GND`/`GPIO17`/`GPIO16` → MAX3232 `VCC`/`GND`/`TXD`/`RXD`; MAX3232 RS232 side `R1IN` ← inverter TX, `T1OUT` → inverter RX, `GND` ↔ GND. The GD5548JMH RJ45 pinout is unpublished, so measure it first. Only one master on the port (unplug the Elfin gateway and the Wi-Fi dongle).

## Setup

1. Copy [`esphome/secrets.yaml.example`](../esphome/secrets.yaml.example) to `esphome/secrets.yaml` (git-ignored) and fill it in.
2. Flash: `esphome run esphome/vevor-inverter.yaml` (or `vevor-bridge.yaml`), or paste the file into the ESPHome Dashboard add-on (copy `packages/` along if you enable controls).
3. Native: Home Assistant discovers the device; add it with the API encryption key. Bridge: add the HACS integration with the ESP32's IP and port 8899.
4. Check the log at `logger: level: DEBUG`: every `pipsolar` poll and timeout is printed. The first command after idle is sometimes lost on this unit (see [research-summary.md](research-summary.md)); `pipsolar` just times out (5 s) and moves on.

## Native config: entities

All from `pipsolar`, names in [`vevor-inverter.yaml`](../esphome/vevor-inverter.yaml). Poll: one command every 2 s, round-robin over the five queries.

| Source | Entities |
|---|---|
| `QPIGS` | grid/output voltage and frequency, output VA/W, load %, bus voltage, battery voltage, charge/discharge current, battery estimate (voltage based, not SOC), heat-sink temperature, PV voltage/current, PV charging power, SCC voltage; status bits load on, charging, solar charging, AC charging, output switched on |
| `QPIRI` | P12, P13, P29, P26, P27 voltages, P02/P11 currents (diagnostic sensors); P01, P16, P05 as text sensors (menu-position codes, see [settings-map.md](settings-map.md)) |
| `QMOD` | operating mode (P/S/L/B/F/H mapped to text) |
| `QPIWS` | warning present, fault present, grid lost, battery low, overload, over temperature |
| `QFLAG` | P06, P07, P08, P18, P19, P20, P22, P23, P25 options |

`pipsolar` also sends `QT` and `QMN` only if their text sensors are configured; `QT` is silent on this unit, so they are left out.

## Native config: controls package (writes)

Enabled by uncommenting the `packages:` block in `vevor-inverter.yaml`. Each control sends one PI30 frame (with CRC) through `pipsolar`'s command queue (`queue_command`) and shows the value read back from `QPIRI`/`QFLAG`, so a `NAK` simply snaps back on the next poll.

| Entity | Command | Values | Status on this unit ([settings-map.md](settings-map.md)) |
|---|---|---|---|
| Output source priority (P01) | `POP00/01/02` | Solar first / SBU / Utility first | read code 1 = SBU verified; codes 0/2 and the write untested |
| Charger source priority (P16) | `PCP00/01/02` | Solar first / Solar and utility / Only solar | read code 2 = only solar verified; write untested |
| Max utility charge current (P11) | `MUCHGC<nnn>` | 2, 10 … 60 A (`QMUCHGCR`) | untested here, ACK + readback on the sibling unit |
| Max charge current (P02) | `MNCHGC<nnn>` | 10 … 80 A (`QMCHGCR`) | untested here, ACK + readback on the sibling unit |
| P12 / P13 / P29 / P26 voltages | `PBCV` / `PBDV` / `PSDV` / `PCVV<nn.n>` | 24 V ranges from the manual (same as `VOLTAGE_SETTINGS_24V` in the integration) | untested |
| P06, P07, P08, P18, P19, P20, P22, P23, P25 | `PE<x>` / `PD<x>` | on / off | untested |

Deliberately left out (same as the integration): battery type, float voltage, equalization, P44 feed-in, clock, and the P46–P49 schedules (no known write command). Unlike the integration, the priority selects offer all three codes; the owner tests them on the real unit.
