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
from dataclasses import dataclass, field
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # no runtime import: tests load this file on its own
    from .protocol.parsers import GeneralStatus


def fmt(value: Any) -> str:
    """Compact number (1 decimal at most, no trailing zeros); anything else as text."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


@dataclass(frozen=True)
class Breakdown:
    """A derived value that explains itself: ``value`` = ``formula`` evaluated with ``terms``.

    Shown as state attributes: the formula, one attribute per term, one
    ``<term>_formula`` per term that is composite itself (``notes``) and the
    formula with the values filled in. The value is built from the same terms
    in the same function, so the explanation and the state cannot drift apart.
    """

    formula: str
    terms: dict[str, Any]
    value: float | None
    notes: dict[str, str] = field(default_factory=dict)

    def filled(self) -> str:
        """The formula with every term replaced by its value, followed by ``= result``."""
        names = sorted(self.terms, key=len, reverse=True)
        pattern = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b")

        def replace(match: re.Match[str]) -> str:
            text = fmt(self.terms[match.group(1)])
            return f"({text})" if text.startswith("-") else text

        return f"{pattern.sub(replace, self.formula)} = {fmt(self.value)}"

    def attributes(self) -> dict[str, Any]:
        attributes: dict[str, Any] = {"formula": self.formula}
        attributes.update(
            {name: round(v, 1) if isinstance(v, float) else v for name, v in self.terms.items()}
        )
        attributes.update({f"{name}_formula": text for name, text in self.notes.items()})
        attributes["formula_values"] = self.filled()
        return attributes

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
) -> tuple[float, str] | None:
    """(grid import in W including the own consumption HGRID does not report, how it was
    put together); None while the balance is unknown."""
    grid = _grid(grid_power, mode)
    if grid is None:
        return None
    if status.grid_voltage <= 0:
        # no grid: the inverter lives on battery / PV, which the balance sees
        return grid, f"grid_power (no grid voltage, nothing unseen) = {fmt(grid)}"
    key = own_consumption_key(status, mode)
    unseen = settings[key] if key == STANDBY else _GRID_UNSEEN_W[key]
    what = "own consumption setting (standby)" if key == STANDBY else f"built-in unseen part ({key})"
    return (
        max(0.0, grid) + unseen,
        f"max(0, grid_power) + {what} = max(0, {fmt(grid)}) + {fmt(unseen)}",
    )


def _battery_charge_power(status: GeneralStatus) -> tuple[float, str]:
    battery = status.battery_voltage * (status.battery_charge_current - status.battery_discharge_current)
    return battery, (
        "battery_voltage * (battery_charge_current - battery_discharge_current) = "
        f"{fmt(status.battery_voltage)} * ({status.battery_charge_current} - {status.battery_discharge_current})"
    )


def battery_power_breakdown(status: GeneralStatus) -> Breakdown:
    """Signed battery power (W): positive = charging."""
    return Breakdown(
        "battery_voltage * (battery_charge_current - battery_discharge_current)",
        {
            "battery_voltage": status.battery_voltage,
            "battery_charge_current": status.battery_charge_current,
            "battery_discharge_current": status.battery_discharge_current,
        },
        status.battery_power,
    )


def inverter_losses_breakdown(
    status: GeneralStatus, mode: str | None, grid_power: int | None
) -> Breakdown | None:
    """Inputs minus outputs, using the PV power the inverter reports (QPIGS[19]).

    At night (no PV) this is the inverter's own consumption plus conversion losses.
    """
    grid = _grid(grid_power, mode)
    if grid is None:
        return None
    battery = status.battery_voltage * (status.battery_discharge_current - status.battery_charge_current)
    pv = status.pv_charging_power or 0
    load = status.ac_output_active_power
    notes = {
        "battery_discharge_power": (
            "battery_voltage * (battery_discharge_current - battery_charge_current) = "
            f"{fmt(status.battery_voltage)} * ({status.battery_discharge_current} - {status.battery_charge_current})"
        )
    }
    if grid_power is None:
        notes["grid_power"] = "HGRID not read, counted as 0"
    return Breakdown(
        "pv_power + battery_discharge_power + grid_power - load",
        {"pv_power": pv, "battery_discharge_power": battery, "grid_power": grid, "load": load},
        round(pv + battery + grid - load, 1),
        notes,
    )


def inverter_losses(status: GeneralStatus, mode: str | None, grid_power: int | None) -> float | None:
    breakdown = inverter_losses_breakdown(status, mode, grid_power)
    return None if breakdown is None else breakdown.value


def net_generation_breakdown(
    status: GeneralStatus, mode: str | None, grid_power: int | None, settings: Mapping[str, float]
) -> Breakdown | None:
    """What the system gave beyond the grid (W) = PV minus the own consumption:
    load + battery charge - discharge - real grid import.

    A battery that charges or empties does not count. < 0 = the system consumed
    (night, own consumption). Grid export, if any, counts as 0 import.
    """
    if grid_power is None:
        return None
    grid, grid_note = _real_grid(status, mode, grid_power, settings)
    battery, battery_note = _battery_charge_power(status)
    load = status.ac_output_active_power
    return Breakdown(
        "load + battery_power - real_grid",
        {"load": load, "battery_power": battery, "real_grid": grid},
        round(load + battery - grid, 1),
        {"battery_power": battery_note, "real_grid": grid_note},
    )


def net_generation(
    status: GeneralStatus, mode: str | None, grid_power: int | None, settings: Mapping[str, float]
) -> float | None:
    breakdown = net_generation_breakdown(status, mode, grid_power, settings)
    return None if breakdown is None else breakdown.value


def pv_power_full_breakdown(
    status: GeneralStatus,
    mode: str | None,
    grid_power: int | None,
    settings: Mapping[str, float],
    battery_power: float | None = None,
) -> Breakdown | None:
    """The full PV power implied by the balance (>= 0), including the part the inverter's
    own PV reading misses: load + own consumption + battery charge - discharge - real grid import.

    ``battery_power`` (W, + = charging) comes from an external battery meter (BMS);
    without it the inverter's battery currents are used. In daylight those show
    the inverter stage's own DC draw instead of the battery current, so weak PV
    (up to ~90 W on the test unit) only becomes visible with an external meter.
    """
    real_grid = _real_grid(status, mode, grid_power, settings)
    if real_grid is None:
        return None
    grid, grid_note = real_grid
    if battery_power is None:
        battery_power, battery_note = _battery_charge_power(status)
    else:
        battery_note = "external battery power sensor"
    load = status.ac_output_active_power
    key = own_consumption_key(status, mode)
    fraction = LOAD_FRACTION.get(key, 0.0)
    own = own_consumption(status, mode, settings)
    return Breakdown(
        "max(0, load + own + battery_power - real_grid)",
        {"load": load, "own": own, "battery_power": battery_power, "real_grid": grid},
        round(max(0.0, load + own + battery_power - grid), 1),
        {
            "own": (
                f"own consumption setting ({key}) + load fraction * load = "
                f"{fmt(settings[key])} + {fraction} * {fmt(load)}"
            ),
            "battery_power": battery_note,
            "real_grid": grid_note,
        },
    )


def pv_power_full(
    status: GeneralStatus,
    mode: str | None,
    grid_power: int | None,
    settings: Mapping[str, float],
    battery_power: float | None = None,
) -> float | None:
    breakdown = pv_power_full_breakdown(status, mode, grid_power, settings, battery_power)
    return None if breakdown is None else breakdown.value
