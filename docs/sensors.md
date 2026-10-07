# Sensor Reference

What every sensor of the integration shows and, for the ones that are **not** a plain inverter field, exactly how the value is computed. Structure, coordinators and how to add an entity are in [integration.md](integration.md); field layouts of the replies are in [inverter-protocol.md](inverter-protocol.md). Entity keys below are the `key` / `translation_key` of the descriptions in [`sensor.py`](../custom_components/voltronic_solar_inverter/sensor.py); the displayed names are in [`strings.json`](../custom_components/voltronic_solar_inverter/strings.json). Fast = polled every 10 s by default, slow = every 60 s. "Diag" = diagnostic category, "off" = disabled by default.

## Kinds of sensors

| Kind | What the state is |
|---|---|
| Direct | The parsed inverter field, rounded to a fixed precision (`sensor._round`) |
| Raw / smoothed pair | `<x>_raw` = every sample; `<x>` = moving average that is written only on a significant change (see [Smoothing](#smoothing-and-publishing-rules)) |
| 10 min median / max | Median or maximum of the samples of the last 600 s, same publish rules |
| Power balance | Mean of the last 10 min of a value computed from several fields (see [Power balance](#power-balance-sensors)) |
| Daily maximum | Highest value since local midnight plus attribute `max_time` |
| Daily energy | Power integrated over the day, kWh (see [Daily energy](#daily-energy-sensors)) |
| Derived (slow) | Computed from a slow field and HA's clock (clock offset, schedules shown as `HH:00`) |

## Fast sensors (`QPIGS`, `QMOD`, `HGRID`)

`QPIGS[n]` = field index n of the `QPIGS` reply (see [inverter-protocol.md](inverter-protocol.md)).

| Key | Source / formula | Notes |
|---|---|---|
| `grid_voltage`, `grid_frequency` | `QPIGS[0]`, `[1]` | voltage rounded to 0 decimals |
| `ac_output_voltage`, `ac_output_frequency` | `QPIGS[2]`, `[3]` | |
| `ac_output_apparent_power` | `QPIGS[4]` | VA |
| `ac_output_active_power_raw` / `ac_output_active_power` | `QPIGS[5]` | W; shown as *Load power*; raw + smoothed pair |
| `load_percent` | `QPIGS[6]` | % of rated power |
| `bus_voltage` (diag, off) | `QPIGS[7]` | |
| `battery_voltage` | `QPIGS[8]` | |
| `battery_charge_current` | `QPIGS[9]` | whole amperes |
| `battery_discharge_current` | `QPIGS[15]` | whole amperes |
| **`battery_power`** | **battery voltage × (charge current − discharge current)**, rounded to 0.1 W | Derived. Positive = charging, negative = discharging. The currents are whole amperes (~25 W steps on 24 V), so it is coarse |
| `battery_capacity_estimate` (off) | `QPIGS[10]` | Voltage-based estimate computed by the inverter, **not** a state of charge |
| `heatsink_temperature` | `QPIGS[11]` | °C; equals the "boost temperature" |
| `pv_input_current` | `QPIGS[12]` | |
| `pv_input_voltage_raw` / `pv_input_voltage` | `QPIGS[13]` | raw every sample; smoothed uses 5 % / 1 V thresholds |
| `pv_power_raw` / `pv_power` | `QPIGS[19]` | The inverter's own PV charging power; raw + smoothed pair |
| `scc_battery_voltage` (diag, off) | `QPIGS[14]` | |
| `grid_power_raw` / `grid_power` | `HGRID[6]` | Signed W, positive = import (verified in mode L, 2026-10-05); needs the H dialect. Reads ~16 W + ~2 % low against an external meter. Raw + smoothed pair |
| `device_mode` | `QMOD` letter mapped through `DEVICE_MODES` | Enum; an unknown letter gives *unknown* and one log warning |
| **`pv_power_median_10min`** | median of the `QPIGS[19]` samples of the last 10 min | Derived; filters out spikes |
| **`pv_power_max_10min`** | maximum of the `QPIGS[19]` samples of the last 10 min | Derived |

## Smoothing and publishing rules

Implemented by [`smoothing.SmoothedValue`](../custom_components/voltronic_solar_inverter/smoothing.py); constants in [`const.py`](../custom_components/voltronic_solar_inverter/const.py).

- Every fast sample is added to a window: 60 s for the plain smoothed sensors (statistic *mean*), 600 s for the 10 min median / max / power-balance sensors.
- The statistic of the window (mean, median or max) is the sensor's value, rounded.
- A new state is **written** (and therefore recorded) only when the value changed by ≥ 10 % *and* ≥ 20 W (PV voltage: ≥ 5 % *and* ≥ 1 V), or dropped to 0, or 10 min have passed since the last write and the value changed at all. Availability changes are always written.
- The `_raw` sensors publish every sample; exclude them from the recorder if the interval is short.

## Power balance sensors

Fast, power (W), written with the smoothing rules above: `inverter_losses` is the mean of the last 10 min (single samples jump by ~25 W because of the whole-ampere battery currents), `pv_power_calculated` the mean of the last 60 s like `pv_power` (since 0.4.8), so the two can be compared. Code: [`power_balance.py`](../custom_components/voltronic_solar_inverter/power_balance.py).

```text
PV + battery discharge + grid import = load + battery charge + own consumption
```

Definitions: *load* = `QPIGS[5]`; *battery* term = battery voltage × (I<sub>discharge</sub> − I<sub>charge</sub>), positive when the battery gives power; *grid* = `HGRID[6]`.

| Key | Formula | Notes |
|---|---|---|
| `inverter_losses` | `PV(QPIGS[19]) + battery + grid − load` | Inputs minus outputs: conversion losses plus the inverter's own consumption (at night with no PV, just that). Unknown (`None`) in mode L (line) without `HGRID`; in other modes a missing `HGRID` counts as 0 W |
| `pv_power_calculated` | `max(0, load + own + battery_power − real grid)` | The PV power the balance implies. `own` = `power_balance.own_consumption` (the setting of the current state + the load-dependent part, below). `battery_power` (+ = charging) comes from the optional external battery sensor (options; W or kW; an unusable state skips the sample), else from the inverter's currents (−*battery* term) — those cannot show weak PV in daylight. *Real grid* = `HGRID[6]` + the part of the own consumption `HGRID` does not report (below), only while the grid is present. Same `HGRID` rule as above. Clamped at 0 |

**Own consumption** (since 0.4.9) = everything the inverter uses itself (control board, power stage, conversion losses), in W. Four HA-only number entities (never sent to the inverter, restored after a restart, 0–500 W) hold it **with no load**; the state is picked by `power_balance.own_consumption_key`. Used by `pv_power_calculated`, `pv_calculated_daily_energy` and `balance_daily_energy`.

| State (condition) | Setting | Default | + per W of load | Drawn from the grid without `HGRID` showing it (built in) |
|---|---|---|---|---|
| Battery mode (output on, not L) | *Own consumption (battery mode)* | 48 W | 3.5 % | 3 W |
| Line mode (`QMOD` L) | *Own consumption (line mode)* | 47 W | 1.3 % | 17 W |
| Output off, standby (`QPIGS` status 2 b9 = 0, mode not C) | *Own consumption (output off, standby)* | 12 W | — | all of it (the setting) |
| Output off, solar charging (b9 = 0, `QMOD` C) | *Own consumption (output off, solar charging)* | 34 W | — | 3 W |

Defaults and the built-in parts were measured on the owner's VMII-4000 on 2026-10-05..07 with an external AC-input meter and the BMS (details in [integration.md](integration.md#power-balance-and-self-consumption)). The unseen grid part matters because the balance must count the energy that came in: without the grid (`QPIGS[0]` = 0) it is 0 and the battery supplies all of the own consumption. 0.4.5–0.4.8 had three *Self-consumption* numbers that held only that unseen part; they are removed from the registry at setup.

## Daily energy sensors

Fast, kWh, 2 decimals. Every raw fast sample of a power is integrated with the trapezoidal rule (`total += (W_prev + W) / 2 × dt / 3.6e6`), the sum resets on the first sample of a new local day and is restored after a restart if the last state was written today. An interval longer than 3 × the fast interval adds nothing (outage, failed updates, restart) and a missing value breaks the interval. Writes are thinned: a new state only when the rounded value moved by ≥ 0.05 kWh, after 10 min with any change, or on a new day. Code: [`smoothing.DailyEnergy`](../custom_components/voltronic_solar_inverter/smoothing.py), [`VoltronicDailyEnergySensor`](../custom_components/voltronic_solar_inverter/sensor.py).

| Key | Integrated power | `state_class` | Notes |
|---|---|---|---|
| `load_daily_energy` | load = `QPIGS[5]` | `total_increasing` | |
| `grid_daily_energy` | grid import = `max(0, HGRID[6])` | `total_increasing` | Export, if any, counts as 0. Only with the H dialect |
| `battery_daily_energy` | `battery_power` = V × (I<sub>chg</sub> − I<sub>dis</sub>) | `total` + `last_reset` = local midnight | + = charged, − = discharged; may be negative; rough (whole amperes) |
| `balance_daily_energy` | `power_balance.net_generation` = load + battery(charge − discharge) − real grid import (`HGRID` + the unseen part of the own consumption, see above) | `total` + `last_reset` | = PV energy minus all losses; may be negative (night). Only with the H dialect |
| `pv_calculated_daily_energy` | `power_balance.pv_power_calculated` (each raw sample, not the 60 s mean) | `total_increasing` | The real PV energy. Uses the external battery sensor when configured; while it is unusable the sample is `None`, which breaks the interval (nothing added) |

## Daily maximum sensors

Fast. Highest value since local midnight; the state is written only when the maximum rises. Attribute `max_time` = ISO local time (seconds) of the first sample that reached it. Reset on the first sample of a new local day; restored after a restart on the same day. Code: `smoothing.DailyMax`.

| Key | Source |
|---|---|
| `pv_power_max_today` | `QPIGS[19]` |
| `pv_input_current_max_today` | `QPIGS[12]` |
| `battery_charge_current_max_today` | `QPIGS[9]` |
| `battery_discharge_current_max_today` | `QPIGS[15]` |

There is no daily median (removed in 0.4.6). The inverter has no measured grid input or AC output current.

## Slow sensors

| Group | Keys | Source / formula |
|---|---|---|
| PV energy | `pv_energy_today`, `_month`, `_year`, `_total` | `HGEN[2..5]`, the inverter's own counters (match the vendor app), kWh |
| Clock | `inverter_clock` | `HGEN[0..1]` (inverter local time), interpreted in HA's time zone |
| **Clock offset** | `inverter_clock_offset` | **Derived**: (inverter clock − HA time of the poll) in whole minutes; positive = inverter ahead |
| **Schedules** | `ac_output_on_time` / `_off_time` (P48/P49), `ac_charger_start_time` / `_stop_time` (P46/P47) | `HEEP2[12]` / `[11]`; hour fields shown as `HH:00` text |
| Temperatures | `inverter_temperature`, `transformer_temperature`, `pv_temperature`, fan 1 / 2 speed % | `HTEMP` 0, 2, 3, 5, 6 |
| Charge stage | `charge_stage` | `Q1[17]` mapped through `CHARGE_STAGES` (idle/bulk verified, absorb/float generic) |
| Solar supply priority | `solar_supply_priority` | `HEEP1`, enum (P43) |
| Battery alarm / dual output | `battery_low_alarm_voltage` (P24), `dual_output_*` | `HEEP2` |
| BMS / grid-tie | `bms_shutdown_soc`, `bms_back_to_battery_soc`, `grid_tie_current` | `HEEP1` |
| Equalization | `equalization_voltage`, `_time`, `_timeout`, `_interval` | `QBEQI` (read-only) |
| Ratings and settings | rated grid / output V, Hz, A, VA, W; battery rating, recharge, redischarge, under, bulk, float voltage; max charging currents; output / charger priority, battery type, input range, machine type, topology, output mode | `QPIRI` fields (see [inverter-protocol.md](inverter-protocol.md)); a sensor is not created while a control entity shows the same value |
| Identity | `serial_number`, `firmware_version`, `firmware_version_2`, `firmware_date`, `protocol_id` | `QID`, `QVFW`, `QVFW2`, `HIMSG1`, `QPI`; read once at start-up |

## Binary sensors that are not a single bit

The full binary list is in [integration.md](integration.md#entities). Computed ones:

| Key | Rule |
|---|---|
| `ac_output` | `QMOD` is L or B (unknown if the letter is not in `DEVICE_MODES`) |
| `fault` | any `QPIWS` fault bit is set, or `QMOD` = F; attribute `faults` lists them |
| `warning` | any `QPIWS` warning bit is set (a0 ignored); attribute `warnings` lists them |
| SBU priority | `QPIRI[16]` = 1 |
