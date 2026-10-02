"""Parsers for the CRC-less Solar Plug "H" dialect (Solar of Things dongle).

Layouts from docs/inverter-protocol.md ("Solar Plug H-protocol") and
docs/settings-map.md; only positions that are verified (V) or match the
vendor app (M) are parsed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from .errors import InverterProtocolError
from .parsers import _fields, _float, _int

# HEEP1[3] 4th character, P43: where PV power goes first (verified).
SOLAR_SUPPLY_PRIORITIES: Final = {0: "battery_first", 1: "load_first"}
SOLAR_SUPPLY_PRIORITIES_VERIFIED: Final = frozenset({0, 1})


@dataclass(frozen=True, slots=True)
class Schedule:
    """An hour window 'HHhh' (start hour, end hour), e.g. P48/P49."""

    start_hour: int
    end_hour: int


def parse_schedule(value: str, command: str) -> Schedule:
    if len(value) != 4 or not value.isdigit():
        raise InverterProtocolError(f"{command}: schedule must be HHhh: {value!r}")
    start, end = int(value[:2]), int(value[2:])
    if start > 23 or end > 23:
        raise InverterProtocolError(f"{command}: hour out of range: {value!r}")
    return Schedule(start_hour=start, end_hour=end)


@dataclass(frozen=True, slots=True)
class SettingsEeprom1:
    """HEEP1 (settings snapshot 1), parsed positions only."""

    solar_supply_priority: int  # [3] 4th char, P43
    bms_shutdown_soc: int  # [10] %, P38
    bms_back_to_battery_soc: int  # [12] %, P40
    grid_tie_current: int  # [17] A, P56


def parse_heep1(payload: str) -> SettingsEeprom1:
    cmd = "HEEP1"
    f = _fields(payload, cmd, 18)
    packed = f[3]
    if len(packed) < 4 or not packed[3].isdigit():
        raise InverterProtocolError(f"{cmd}: unexpected packed field {packed!r}")
    return SettingsEeprom1(
        solar_supply_priority=int(packed[3]),
        bms_shutdown_soc=_int(f[10], cmd),
        bms_back_to_battery_soc=_int(f[12], cmd),
        grid_tie_current=_int(f[17], cmd),
    )


@dataclass(frozen=True, slots=True)
class SettingsEeprom2:
    """HEEP2 (settings snapshot 2), parsed positions only."""

    battery_low_alarm_voltage: float  # [1] V, P24
    dual_output_cutoff_voltage: float  # [3] V
    ac_charger_schedule: Schedule  # [11], P46/P47 (verified)
    ac_output_schedule: Schedule  # [12], P48/P49 (verified)
    dual_output_recover_delay: int  # [13] min
    dual_output_schedule: Schedule  # [14]
    dual_output_recover_voltage: float  # [15] V


def parse_heep2(payload: str) -> SettingsEeprom2:
    cmd = "HEEP2"
    f = _fields(payload, cmd, 16)
    return SettingsEeprom2(
        battery_low_alarm_voltage=_float(f[1], cmd),
        dual_output_cutoff_voltage=_float(f[3], cmd),
        ac_charger_schedule=parse_schedule(f[11], cmd),
        ac_output_schedule=parse_schedule(f[12], cmd),
        dual_output_recover_delay=_int(f[13], cmd),
        dual_output_schedule=parse_schedule(f[14], cmd),
        dual_output_recover_voltage=_float(f[15], cmd),
    )


@dataclass(frozen=True, slots=True)
class Generation:
    """HGEN: inverter clock (local, minute resolution) and PV energy counters."""

    clock: datetime  # naive, inverter local time
    pv_energy_today: float  # kWh
    pv_energy_month: float  # kWh
    pv_energy_year: float  # kWh
    pv_energy_total: float  # kWh


def parse_hgen(payload: str) -> Generation:
    cmd = "HGEN"
    f = _fields(payload, cmd, 6)
    try:
        clock = datetime.strptime(f"{f[0]} {f[1]}", "%y%m%d %H:%M")
    except ValueError as err:
        raise InverterProtocolError(f"{cmd}: bad clock {f[0]!r} {f[1]!r}") from err
    return Generation(
        clock=clock,
        pv_energy_today=_float(f[2], cmd),
        pv_energy_month=_float(f[3], cmd),
        pv_energy_year=_float(f[4], cmd),
        pv_energy_total=_float(f[5], cmd),
    )


@dataclass(frozen=True, slots=True)
class Temperatures:
    """HTEMP: temperatures in °C (equal to Q1[8..11]) and fan speeds in %."""

    inverter: int  # [0]
    boost: int  # [1] = QPIGS heat sink
    transformer: int  # [2]
    pv: int  # [3]
    fan_1_speed: int  # [5]
    fan_2_speed: int  # [6]


def parse_htemp(payload: str) -> Temperatures:
    cmd = "HTEMP"
    f = _fields(payload, cmd, 7)
    return Temperatures(
        inverter=_int(f[0], cmd),
        boost=_int(f[1], cmd),
        transformer=_int(f[2], cmd),
        pv=_int(f[3], cmd),
        fan_1_speed=_int(f[5], cmd),
        fan_2_speed=_int(f[6], cmd),
    )


def parse_hgrid_power(payload: str) -> int:
    """HGRID[6]: signed grid power in W (sign convention still to be verified)."""
    return _int(_fields(payload, "HGRID", 7)[6], "HGRID")


def parse_himsg1_firmware_date(payload: str) -> str:
    """HIMSG1[1] '20260119' -> '2026-01-19'."""
    value = _fields(payload, "HIMSG1", 2)[1]
    try:
        return datetime.strptime(value, "%Y%m%d").date().isoformat()
    except ValueError as err:
        raise InverterProtocolError(f"HIMSG1: bad date {value!r}") from err
