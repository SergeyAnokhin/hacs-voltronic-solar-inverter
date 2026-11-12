"""All setting (write) commands, in one place.

Every builder validates its argument and returns a WriteCommand; only a
WriteCommand can be sent through InverterClient.write(). Nothing here talks to
the device. None of these commands has been verified on the Vevor GD5548JMH
yet: the owner tests them on the real unit (see docs/integration.md).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Final

from .errors import InvalidCommandError
from .framing import encode_frame
from .h_parsers import SOLAR_SUPPLY_PRIORITIES_VERIFIED
from .parsers import (
    CHARGER_SOURCE_PRIORITIES_VERIFIED,
    FLAGS,
    OUTPUT_SOURCE_PRIORITIES_VERIFIED,
)

QUERY_RE: Final = re.compile(r"Q[A-Z0-9]{1,14}")

# Read-only queries sent WITHOUT CRC (Solar Plug H dialect), exactly as approved
# by the owner on 2026-10-02. Anything else is refused by the client.
PLAIN_QUERIES: Final = frozenset(
    {
        "QPRTL",
        "HSTS", "HGRID", "HOP", "HBAT", "HPV", "HPVB", "HTEMP", "HGEN", "HIMSG1",
        "HBMS1", "HBMS2", "HBMS3", "HEEP1", "HEEP2",
    }
)

FLAG_LETTERS: Final = {key: letter for letter, key in FLAGS.items()}


@dataclass(frozen=True, slots=True)
class WriteCommand:
    """A validated setting command; the inverter answers ACK or NAK."""

    text: str

    @property
    def frame(self) -> bytes:
        return encode_frame(self.text)


def set_flag(flag: str, enabled: bool) -> WriteCommand:
    """PE<x> / PD<x>: enable or disable a QFLAG option (flag key from FLAGS)."""
    letter = FLAG_LETTERS.get(flag)
    if letter is None:
        raise InvalidCommandError(f"unknown flag {flag!r}")
    return WriteCommand(f"{'PE' if enabled else 'PD'}{letter}")


def set_output_source_priority(code: int) -> WriteCommand:
    """POP<NN>, using this firmware's menu-position codes (only verified codes allowed)."""
    if isinstance(code, bool) or code not in OUTPUT_SOURCE_PRIORITIES_VERIFIED:
        raise InvalidCommandError(f"output source priority code {code!r} is not verified")
    return WriteCommand(f"POP{code:02d}")


def set_charger_source_priority(code: int) -> WriteCommand:
    """PCP<NN>, using this firmware's menu-position codes (only verified codes allowed)."""
    if isinstance(code, bool) or code not in CHARGER_SOURCE_PRIORITIES_VERIFIED:
        raise InvalidCommandError(f"charger source priority code {code!r} is not verified")
    return WriteCommand(f"PCP{code:02d}")


def set_solar_supply_priority(code: int) -> WriteCommand:
    """PVENGUSE<NN> (P43): 00 = battery first (BLU), 01 = load first (LBU)."""
    if isinstance(code, bool) or code not in SOLAR_SUPPLY_PRIORITIES_VERIFIED:
        raise InvalidCommandError(f"solar supply priority code {code!r} is not verified")
    return WriteCommand(f"PVENGUSE{code:02d}")


# PBATCD<abc> from the Axpert MAX protocol (PI30MAX): a = discharge off/on,
# b = discharge off/on with standby kept, c = charge off/on; 000 clears the
# overrides. No query reads it back. Codes that shut the unit down (011, 010)
# are left out. Unverified on VMII firmware.
BATTERY_CONTROL_MODES: Final = {
    "auto": "000",
    "no_discharge": "101",
    "no_charge": "110",
    "no_charge_no_discharge": "100",
}


def set_battery_control(mode: str) -> WriteCommand:
    """PBATCD<abc>: battery charge / discharge override (mode from BATTERY_CONTROL_MODES)."""
    code = BATTERY_CONTROL_MODES.get(mode) if isinstance(mode, str) else None
    if code is None:
        raise InvalidCommandError(f"unknown battery control mode {mode!r}")
    return WriteCommand(f"PBATCD{code}")


# PBATMAXDISC<nnn> from the Axpert MAX protocol: 000 = no limit, else 30..150 A
# (documented for 48 V units only; no query reads it back on this firmware).
MAX_DISCHARGING_CURRENT_RANGE: Final = (30, 150)


def set_max_discharging_current(amps: int) -> WriteCommand:
    """PBATMAXDISC<nnn>: 0 disables the limit, otherwise 30..150 A."""
    low, high = MAX_DISCHARGING_CURRENT_RANGE
    if isinstance(amps, bool) or not isinstance(amps, int) or not (amps == 0 or low <= amps <= high):
        raise InvalidCommandError(f"max discharging current {amps!r} A is not 0 or {low}..{high} A")
    return WriteCommand(f"PBATMAXDISC{amps:03d}")


# Schedule setters from the manufacturer's service tool (page of device type HPVINV02),
# found 2026-11-12: "^S???ACLT<HH>-<HH>" = AC output time (P48/P49), "^S???ACCT<HH>-<HH>" =
# AC charging time (P46/P47). The three "?" are literal. The tool offers hours 01-24 with
# start < end, the LCD 00-23 (and the owner uses 23-00), so only 0..23 is checked here and
# the inverter decides. Read back through HEEP2[12] / HEEP2[11]. Unverified on this unit.
SCHEDULE_PREFIXES: Final = {"ac_output": "^S???ACLT", "ac_charger": "^S???ACCT"}
SCHEDULE_HOURS: Final = (0, 23)


def set_schedule(kind: str, start_hour: int, end_hour: int) -> WriteCommand:
    """^S???ACLT / ^S???ACCT<HH>-<HH>: hour window of the AC output or the AC charger."""
    prefix = SCHEDULE_PREFIXES.get(kind) if isinstance(kind, str) else None
    if prefix is None:
        raise InvalidCommandError(f"unknown schedule {kind!r}")
    low, high = SCHEDULE_HOURS
    for name, hour in (("start", start_hour), ("end", end_hour)):
        if isinstance(hour, bool) or not isinstance(hour, int) or not low <= hour <= high:
            raise InvalidCommandError(f"{kind} {name} hour {hour!r} is not a whole hour {low}..{high}")
    return WriteCommand(f"{prefix}{start_hour:02d}-{end_hour:02d}")


def _check_current(amps: int, options: Iterable[int], name: str) -> None:
    allowed = tuple(options)
    if isinstance(amps, bool) or not isinstance(amps, int) or amps not in allowed:
        raise InvalidCommandError(f"{name} {amps!r} A is not one of {allowed}")
    if not 0 < amps < 1000:
        raise InvalidCommandError(f"{name} {amps!r} A is outside 1..999 A")


def set_max_charging_current(amps: int, options: Iterable[int]) -> WriteCommand:
    """MNCHGC<nnn>; amps must come from QMCHGCR.

    MNCHGC (not the PI30 MCHGC<mnn>) is the form ACKed and read back on a sibling
    VMII-6200 in solarplug-esphome.
    """
    _check_current(amps, options, "max charging current")
    return WriteCommand(f"MNCHGC{amps:03d}")


def set_max_utility_charging_current(amps: int, options: Iterable[int]) -> WriteCommand:
    """MUCHGC<nnn>: amps must come from QMUCHGCR."""
    _check_current(amps, options, "max utility charging current")
    return WriteCommand(f"MUCHGC{amps:03d}")


@dataclass(frozen=True, slots=True)
class VoltageSetting:
    """A battery voltage setter with its documented range (24 V system)."""

    prefix: str
    minimum: float
    maximum: float
    step: float


# Ranges from the Vevor manual's 24 V column (docs/inverter-vevor-gd5548jmh.md).
# Float voltage (PBFT, P27) is missing on purpose: its range is not documented.
VOLTAGE_SETTINGS_24V: Final = {
    "battery_recharge_voltage": VoltageSetting("PBCV", 22.0, 25.5, 0.5),  # P12
    "battery_redischarge_voltage": VoltageSetting("PBDV", 24.0, 29.0, 0.5),  # P13
    "battery_under_voltage": VoltageSetting("PSDV", 20.0, 26.0, 0.1),  # P29
    "battery_bulk_voltage": VoltageSetting("PCVV", 24.0, 30.0, 0.1),  # P26
}


def _voltage_command(settings: dict[str, VoltageSetting], key: str, volts: float) -> WriteCommand:
    setting = settings.get(key)
    if setting is None:
        raise InvalidCommandError(f"unknown voltage setting {key!r}")
    if isinstance(volts, bool) or not isinstance(volts, (int, float)):
        raise InvalidCommandError(f"{key}: {volts!r} is not a number")
    if not setting.minimum - 1e-6 <= volts <= setting.maximum + 1e-6:
        raise InvalidCommandError(
            f"{key}: {volts} V is outside {setting.minimum}..{setting.maximum} V"
        )
    steps = (volts - setting.minimum) / setting.step
    if abs(steps - round(steps)) > 1e-6:
        raise InvalidCommandError(f"{key}: {volts} V is not a multiple of {setting.step} V")
    return WriteCommand(f"{setting.prefix}{volts:04.1f}")


def set_battery_voltage(key: str, volts: float) -> WriteCommand:
    """PBCV/PBDV/PSDV/PCVV<nn.n> for a 24 V system."""
    return _voltage_command(VOLTAGE_SETTINGS_24V, key, volts)


# Setters found in the manufacturer's service tool (2026-11-12), read back from HEEP1/HEEP2.
# Ranges: P24 from the Vevor manual; the second-output voltages are not documented (the
# manual only gives the defaults 22 V / 26 V), so a wide window is used and the inverter
# decides. Unverified on this unit.
HEEP_VOLTAGE_SETTINGS_24V: Final = {
    "battery_low_alarm_voltage": VoltageSetting("PSLV", 20.0, 27.0, 0.1),  # P24
    "second_output_cutoff_voltage": VoltageSetting("PDSDV", 20.0, 30.0, 0.1),  # dual output
    "second_output_recover_voltage": VoltageSetting("PDSRV", 20.0, 30.0, 0.1),  # dual output
}


def set_heep_voltage(key: str, volts: float) -> WriteCommand:
    """PSLV / PDSDV / PDSRV<nn.n> for a 24 V system (key from HEEP_VOLTAGE_SETTINGS_24V)."""
    return _voltage_command(HEEP_VOLTAGE_SETTINGS_24V, key, volts)


@dataclass(frozen=True, slots=True)
class IntegerSetting:
    """A whole-number setter written as prefix + zero-padded digits."""

    prefix: str
    digits: int
    minimum: int
    maximum: int
    step: int = 1


# From the service tool (2026-11-12); the "?" ranges are not documented anywhere and are
# deliberately wide: the inverter decides (the sibling unit rejected BMSSDC 21 but accepted
# 20 and PDDLYT 4 but not 5-minute steps). Unverified on this unit.
INTEGER_SETTINGS: Final = {
    "bms_lock_soc": IntegerSetting("BMSSDC", 3, 0, 100),  # P38
    "bms_back_to_ac_soc": IntegerSetting("BMSB2UC", 3, 0, 100),  # P39
    "bms_back_to_battery_soc": IntegerSetting("BMSU2BC", 3, 0, 100),  # P40
    "bms_restart_soc": IntegerSetting("BMSSRC", 3, 0, 100),  # P41
    "second_output_cutoff_soc": IntegerSetting("PDSDS", 3, 0, 100),
    "second_output_recover_soc": IntegerSetting("PDSRS", 3, 0, 50),  # range from the sibling unit
    "second_output_recover_delay": IntegerSetting("PDDLYT", 3, 0, 60, 5),  # minutes, manual: 0-60
    "second_output_discharge_time": IntegerSetting("PDDCGT", 4, 0, 990, 5),  # minutes, manual: 0 / 5..990
    "battery_discharge_current_limit": IntegerSetting("DISCC", 3, 0, 250),  # A, meaning of 0 unknown
}


def set_integer_setting(key: str, value: int) -> WriteCommand:
    """BMS* / PDS* / PDD* / DISCC<digits> (key from INTEGER_SETTINGS)."""
    setting = INTEGER_SETTINGS.get(key)
    if setting is None:
        raise InvalidCommandError(f"unknown setting {key!r}")
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidCommandError(f"{key}: {value!r} is not a whole number")
    if not setting.minimum <= value <= setting.maximum:
        raise InvalidCommandError(f"{key}: {value} is outside {setting.minimum}..{setting.maximum}")
    if (value - setting.minimum) % setting.step:
        raise InvalidCommandError(f"{key}: {value} is not a multiple of {setting.step}")
    return WriteCommand(f"{setting.prefix}{value:0{setting.digits}d}")


def set_dual_output_mode(enabled: bool) -> WriteCommand:
    """PDAULC01 / PDAULC00: dual (second) output mode on / off (read back: HEEP2[0])."""
    if not isinstance(enabled, bool):
        raise InvalidCommandError(f"dual output mode {enabled!r} is not a bool")
    return WriteCommand(f"PDAULC{int(enabled):02d}")


def set_second_output(enabled: bool) -> WriteCommand:
    """PDAULON01 / PDAULON00: switch the second output on / off now (no read-back is used)."""
    if not isinstance(enabled, bool):
        raise InvalidCommandError(f"second output {enabled!r} is not a bool")
    return WriteCommand(f"PDAULON{int(enabled):02d}")


CLOCK_YEARS: Final = (2016, 2099)  # the LCD takes 16..99


def set_clock(moment: datetime) -> WriteCommand:
    """^S???DAT<yymmddhhmmss>: set the inverter clock (local time, three literal "?").

    Same frame as the service tool and the Solar of Things dongle; the schedules
    (P46-P49) follow this clock. Read back through HGEN (minute resolution).
    """
    if not isinstance(moment, datetime):
        raise InvalidCommandError(f"clock {moment!r} is not a datetime")
    low, high = CLOCK_YEARS
    if not low <= moment.year <= high:
        raise InvalidCommandError(f"clock year {moment.year} is outside {low}..{high}")
    return WriteCommand(f"^S???DAT{moment:%y%m%d%H%M%S}")
