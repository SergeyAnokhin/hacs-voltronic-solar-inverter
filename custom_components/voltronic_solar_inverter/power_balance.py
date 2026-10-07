"""Power balance of the inverter (no HA imports).

    PV + battery discharge + grid = load + battery charge + inverter losses

The inverter reports battery currents in whole amperes (~25 W steps on 24 V),
so single samples are noisy; the sensors built on this average over minutes.
Grid power comes from HGRID (+ = import, verified in mode L).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # no runtime import: tests load this file on its own
    from .protocol.parsers import GeneralStatus

# Modes in which the grid may supply power; without HGRID the balance is unknown there.
_GRID_MODES = frozenset({"line"})


def _grid(grid_power: int | None, mode: str | None) -> float | None:
    if grid_power is not None:
        return float(grid_power)
    return None if mode in _GRID_MODES else 0.0


# Keys of the self-consumption settings (number entities, used by the daily
# energy balance) and of LOSS_MODEL.
BATTERY, LINE, OUTPUT_OFF = "battery", "line", "output_off"
# Measured on the owner's VMII-4000 with an external meter (2026-10-05/06): the
# inverter's own sensors miss ~16 W in line mode (HGRID) and all 13 W with the
# output off; in battery mode its battery current already contains its losses.
DEFAULT_SELF_CONSUMPTION = {BATTERY: 0.0, LINE: 16.0, OUTPUT_OFF: 13.0}


# Inverter losses already contained in the inputs the balance uses (battery power
# in mode B, HGRID in mode L), as (constant W, fraction of the load). Fitted on
# ~4 days of the owner's history (2026-10-06): BMS out - load = 50.2 W + 3.45 %
# at night; HGRID - load = 28 W + 1 % with the battery idle. The part of the own
# draw that comes unseen from the grid (16 W in L, 13 W output off) cancels out.
# Output off while charging from PV (mode C, 2026-10-07): the solar charger stage
# draws ~31 W from the DC side (the BMS showed -31 W at dusk with PV gone, and
# exactly 0 while weak PV still covered it); in standby (S) it draws from the grid.
CHARGING = "charging"
LOSS_MODEL: dict[str, tuple[float, float]] = {
    BATTERY: (50.0, 0.035),
    LINE: (28.0, 0.01),
    OUTPUT_OFF: (0.0, 0.0),
    CHARGING: (31.0, 0.0),
}


def self_consumption_key(status: GeneralStatus, mode: str | None) -> str:
    """Which setting applies: output off (QPIGS status 2 b9, verified), line or battery mode."""
    output_on = status.switched_on if status.switched_on is not None else mode in ("line", "battery")
    if not output_on:
        return OUTPUT_OFF
    return LINE if mode == "line" else BATTERY


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


def net_generation(status: GeneralStatus, grid_power: int | None, self_consumption: float) -> float | None:
    """What the system gave beyond the grid (W): load + battery charge - discharge - grid import - unseen own consumption.

    Equals the PV power minus all inverter losses, so a battery that charges or
    empties does not count. < 0 = the system consumed (night, losses). Grid
    export, if any, counts as 0 import.
    """
    if grid_power is None:
        return None
    battery = status.battery_voltage * (status.battery_charge_current - status.battery_discharge_current)
    return round(status.ac_output_active_power + battery - max(0, grid_power) - self_consumption, 1)


def pv_power_calculated(
    status: GeneralStatus,
    mode: str | None,
    grid_power: int | None,
    battery_power: float | None = None,
) -> float | None:
    """PV power implied by the balance: load + losses + charge - discharge - grid (>= 0).

    ``battery_power`` (W, + = charging) comes from an external battery meter (BMS);
    without it the inverter's battery currents are used. In daylight those show
    the inverter stage's own DC draw instead of the battery current, so weak PV
    (up to ~90 W on the test unit) only becomes visible with an external meter.
    """
    grid = _grid(grid_power, mode)
    if grid is None:
        return None
    if battery_power is None:
        battery_power = status.battery_voltage * (
            status.battery_charge_current - status.battery_discharge_current
        )
    load = status.ac_output_active_power
    key = self_consumption_key(status, mode)
    if key == OUTPUT_OFF and mode == CHARGING:
        key = CHARGING
    constant, fraction = LOSS_MODEL[key]
    return round(max(0.0, load + constant + fraction * load + battery_power - grid), 1)
