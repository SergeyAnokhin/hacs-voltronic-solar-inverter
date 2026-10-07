"""Power balance of the inverter (no HA imports).

    PV + battery discharge + grid = load + battery charge + own consumption

"Own consumption" is everything the inverter itself uses (control board, power
stage, conversion losses). The user sets it per state (number entities); this
module knows how much of it the inverter's grid reading cannot see.

The inverter reports battery currents in whole amperes (~25 W steps on 24 V),
so single samples are noisy; the sensors built on this average over minutes.
Grid power comes from HGRID (+ = import, verified in mode L).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # no runtime import: tests load this file on its own
    from .protocol.parsers import GeneralStatus

# Modes in which the grid may supply power; without HGRID the balance is unknown there.
_GRID_MODES = frozenset({"line"})


def _grid(grid_power: int | None, mode: str | None) -> float | None:
    if grid_power is not None:
        return float(grid_power)
    return None if mode in _GRID_MODES else 0.0


# States with their own own-consumption setting (number entities).
BATTERY, LINE, STANDBY, SOLAR_CHARGING = "battery", "line", "standby", "solar_charging"

# Defaults = total own consumption with no load, measured on the owner's VMII-4000
# (external AC-input meter + BMS, 2026-10-05..07): battery mode 45 W from the
# battery (BMS at 0-3 W load, 2026-10-07 night) + 3 W from the grid; line mode
# 47 W; output off at night (standby, mode S) 12 W, all from the grid; output off
# while charging from PV (mode C) 31 W from the PV/battery side + 3 W from the grid.
DEFAULT_OWN_CONSUMPTION: dict[str, float] = {
    BATTERY: 48.0,
    LINE: 47.0,
    STANDBY: 12.0,
    SOLAR_CHARGING: 34.0,
}

# Part that grows with the load (conversion losses), as a fraction of the load:
# battery mode 3.5 % (BMS out - load), line mode 1.3 % (meter - load).
LOAD_FRACTION: dict[str, float] = {BATTERY: 0.035, LINE: 0.013}

# Part of the own consumption drawn from the grid that HGRID does not report
# (external meter - HGRID), counted only while the grid is present. In standby
# the inverter runs entirely on the grid and HGRID shows 0, so there it is the
# whole own consumption.
_GRID_UNSEEN_W: dict[str, float] = {BATTERY: 3.0, LINE: 17.0, SOLAR_CHARGING: 3.0}


def own_consumption_key(status: GeneralStatus, mode: str | None) -> str:
    """Which setting applies: output off (QPIGS status 2 b9, verified) -> standby or
    solar charging (mode C); output on -> line or battery mode."""
    output_on = status.switched_on if status.switched_on is not None else mode in ("line", "battery")
    if not output_on:
        return SOLAR_CHARGING if mode == "charging" else STANDBY
    return LINE if mode == "line" else BATTERY


def own_consumption(status: GeneralStatus, mode: str | None, settings: Mapping[str, float]) -> float:
    """Total own consumption (W) in the current state: the setting + the load-dependent part."""
    key = own_consumption_key(status, mode)
    return settings[key] + LOAD_FRACTION.get(key, 0.0) * status.ac_output_active_power


def _real_grid(
    status: GeneralStatus, mode: str | None, grid_power: int | None, settings: Mapping[str, float]
) -> float | None:
    """Grid import (W) including the own consumption HGRID does not report."""
    grid = _grid(grid_power, mode)
    if grid is None:
        return None
    if status.grid_voltage <= 0:
        return grid  # no grid: the inverter lives on battery / PV, which the balance sees
    key = own_consumption_key(status, mode)
    return max(0.0, grid) + (settings[key] if key == STANDBY else _GRID_UNSEEN_W[key])


def inverter_losses(status: GeneralStatus, mode: str | None, grid_power: int | None) -> float | None:
    """Inputs minus outputs, using the PV power the inverter reports (QPIGS[19]).

    At night (no PV) this is the inverter's own consumption plus conversion losses.
    """
    grid = _grid(grid_power, mode)
    if grid is None:
        return None
    battery = status.battery_voltage * (status.battery_discharge_current - status.battery_charge_current)
    pv = status.pv_charging_power or 0
    return round(pv + battery + grid - status.ac_output_active_power, 1)


def net_generation(
    status: GeneralStatus, mode: str | None, grid_power: int | None, settings: Mapping[str, float]
) -> float | None:
    """What the system gave beyond the grid (W) = PV minus the own consumption:
    load + battery charge - discharge - real grid import.

    A battery that charges or empties does not count. < 0 = the system consumed
    (night, own consumption). Grid export, if any, counts as 0 import.
    """
    if grid_power is None:
        return None
    grid = _real_grid(status, mode, grid_power, settings)
    battery = status.battery_voltage * (status.battery_charge_current - status.battery_discharge_current)
    return round(status.ac_output_active_power + battery - grid, 1)


def pv_power_calculated(
    status: GeneralStatus,
    mode: str | None,
    grid_power: int | None,
    settings: Mapping[str, float],
    battery_power: float | None = None,
) -> float | None:
    """PV power implied by the balance (>= 0):
    load + own consumption + battery charge - discharge - real grid import.

    ``battery_power`` (W, + = charging) comes from an external battery meter (BMS);
    without it the inverter's battery currents are used. In daylight those show
    the inverter stage's own DC draw instead of the battery current, so weak PV
    (up to ~90 W on the test unit) only becomes visible with an external meter.
    """
    grid = _real_grid(status, mode, grid_power, settings)
    if grid is None:
        return None
    if battery_power is None:
        battery_power = status.battery_voltage * (
            status.battery_charge_current - status.battery_discharge_current
        )
    load = status.ac_output_active_power
    own = own_consumption(status, mode, settings)
    return round(max(0.0, load + own + battery_power - grid), 1)
