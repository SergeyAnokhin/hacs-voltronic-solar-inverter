"""All setting (write) commands, in one place.

Every builder validates its argument and returns a WriteCommand; only a
WriteCommand can be sent through InverterClient.write(). Nothing here talks to
the device. None of these commands has been verified on the Vevor GD5548JMH
yet: the owner tests them on the real unit (see docs/integration.md).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
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


def set_battery_voltage(key: str, volts: float) -> WriteCommand:
    """PBCV/PBDV/PSDV/PCVV<nn.n> for a 24 V system."""
    setting = VOLTAGE_SETTINGS_24V.get(key)
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
