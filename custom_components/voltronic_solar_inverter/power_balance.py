"""Power balance of the inverter (no HA imports).

    PV + battery discharge + grid = load + battery charge + inverter losses

The inverter reports battery currents in whole amperes (~25 W steps on 24 V),
so single samples are noisy; the sensors built on this average over minutes.
Grid power comes from HGRID (sign not verified yet: positive = import assumed).
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


# Keys of the self-consumption settings (number entities).
BATTERY, LINE, OUTPUT_OFF = "battery", "line", "output_off"
# Measured on the owner's VMII-4000 with an external meter (2026-10-05): the
# inverter's own sensors miss ~16 W in line mode (HGRID) and all 13 W with the
# output off. Battery mode is not measured yet.
DEFAULT_SELF_CONSUMPTION = {BATTERY: 0.0, LINE: 16.0, OUTPUT_OFF: 13.0}


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


def pv_power_calculated(
    status: GeneralStatus, mode: str | None, grid_power: int | None, self_consumption: float
) -> float | None:
    """PV power implied by the balance: load + charge + own consumption - discharge - grid (>= 0).

    ``self_consumption`` is what the inverter's sensors do not show, not its total draw.
    """
    grid = _grid(grid_power, mode)
    if grid is None:
        return None
    battery = status.battery_voltage * (status.battery_discharge_current - status.battery_charge_current)
    return round(max(0.0, status.ac_output_active_power + self_consumption - battery - grid), 1)
