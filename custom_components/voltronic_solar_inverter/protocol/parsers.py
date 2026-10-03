"""Parsers for PI30 query responses (payload text without '(' and CRC).

Field layouts are documented in docs/inverter-protocol.md. Each parser raises
InverterProtocolError when the payload does not match the expected layout.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .errors import InverterProtocolError


def _fields(payload: str, command: str, minimum: int) -> list[str]:
    fields = payload.split()
    if len(fields) < minimum:
        raise InverterProtocolError(
            f"{command}: expected at least {minimum} fields, got {len(fields)}: {payload!r}"
        )
    return fields


def _float(value: str, command: str) -> float:
    try:
        return float(value)
    except ValueError as err:
        raise InverterProtocolError(f"{command}: not a number: {value!r}") from err


def _int(value: str, command: str) -> int:
    try:
        return int(value)
    except ValueError as err:
        raise InverterProtocolError(f"{command}: not an integer: {value!r}") from err


def _bits(value: str, command: str) -> str:
    if not value or any(c not in "01" for c in value):
        raise InverterProtocolError(f"{command}: not a bit string: {value!r}")
    return value


# --- QPIGS: live status ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GeneralStatus:
    """QPIGS response (indices in docs/inverter-protocol.md)."""

    grid_voltage: float  # 0
    grid_frequency: float  # 1
    ac_output_voltage: float  # 2
    ac_output_frequency: float  # 3
    ac_output_apparent_power: int  # 4
    ac_output_active_power: int  # 5
    load_percent: int  # 6
    bus_voltage: int  # 7
    battery_voltage: float  # 8
    battery_charge_current: int  # 9
    battery_capacity_estimate: int  # 10, voltage-based estimate, NOT a state of charge
    heatsink_temperature: int  # 11
    pv_input_current: float  # 12
    pv_input_voltage: float  # 13
    scc_battery_voltage: float  # 14
    battery_discharge_current: int  # 15
    status_bits: str  # 16, char 0 = b7 ... char 7 = b0
    pv_charging_power: int | None = None  # 19 (spec; absent on older firmware)
    status2_bits: str | None = None  # 20, char 0 = b10, char 1 = b9, char 2 = b8

    def _bit(self, bit: int) -> bool:
        return self.status_bits[7 - bit] == "1"

    @property
    def load_on(self) -> bool:
        return self._bit(4)

    @property
    def charging(self) -> bool:
        return self._bit(2)

    @property
    def scc_charging(self) -> bool:
        return self._bit(1)

    @property
    def ac_charging(self) -> bool:
        return self._bit(0)

    @property
    def charging_to_float(self) -> bool | None:
        return None if self.status2_bits is None else self.status2_bits[0] == "1"

    @property
    def switched_on(self) -> bool | None:
        return None if self.status2_bits is None else self.status2_bits[1] == "1"

    @property
    def battery_power(self) -> float:
        """Signed battery power in W: positive = charging, negative = discharging."""
        return round(
            self.battery_voltage * (self.battery_charge_current - self.battery_discharge_current), 1
        )


def parse_qpigs(payload: str) -> GeneralStatus:
    cmd = "QPIGS"
    f = _fields(payload, cmd, 17)
    status_bits = _bits(f[16], cmd)
    if len(status_bits) != 8:
        raise InverterProtocolError(f"{cmd}: status field must have 8 bits: {f[16]!r}")
    status2 = None
    if len(f) > 20:
        status2 = _bits(f[20], cmd)
        if len(status2) != 3:
            raise InverterProtocolError(f"{cmd}: status2 field must have 3 bits: {f[20]!r}")
    return GeneralStatus(
        grid_voltage=_float(f[0], cmd),
        grid_frequency=_float(f[1], cmd),
        ac_output_voltage=_float(f[2], cmd),
        ac_output_frequency=_float(f[3], cmd),
        ac_output_apparent_power=_int(f[4], cmd),
        ac_output_active_power=_int(f[5], cmd),
        load_percent=_int(f[6], cmd),
        bus_voltage=_int(f[7], cmd),
        battery_voltage=_float(f[8], cmd),
        battery_charge_current=_int(f[9], cmd),
        battery_capacity_estimate=_int(f[10], cmd),
        heatsink_temperature=_int(f[11], cmd),
        pv_input_current=_float(f[12], cmd),
        pv_input_voltage=_float(f[13], cmd),
        scc_battery_voltage=_float(f[14], cmd),
        battery_discharge_current=_int(f[15], cmd),
        status_bits=status_bits,
        pv_charging_power=_int(f[19], cmd) if len(f) > 19 else None,
        status2_bits=status2,
    )


# --- QMOD: device mode ---------------------------------------------------------

DEVICE_MODES: Final = {
    "P": "power_on",
    "S": "standby",
    "L": "line",
    "B": "battery",
    "F": "fault",
    "H": "power_saving",
    "D": "shutdown",
    "C": "charging",  # output off, battery charging (seen 2026-10-03: PV charging, no grid)
}
OUTPUT_ACTIVE_MODES: Final = frozenset({"line", "battery"})


def parse_qmod(payload: str) -> str:
    """Return the mode key (see DEVICE_MODES); unknown letters raise."""
    code = payload.strip()
    if code not in DEVICE_MODES:
        raise InverterProtocolError(f"QMOD: unknown mode {payload!r}")
    return DEVICE_MODES[code]


# --- QPIRI: ratings and current settings ---------------------------------------

# Codes on this firmware follow the LCD menu position, NOT the generic Voltronic
# numbering (owner-confirmed values are listed in *_VERIFIED). Code 2 of the
# output priority is "utility first" per the solarplug-esphome POP mapping.
OUTPUT_SOURCE_PRIORITIES: Final = {0: "solar_first", 1: "sbu", 2: "utility_first"}
OUTPUT_SOURCE_PRIORITIES_VERIFIED: Final = frozenset({1})
CHARGER_SOURCE_PRIORITIES: Final = {0: "solar_first", 1: "solar_and_utility", 2: "only_solar"}
CHARGER_SOURCE_PRIORITIES_VERIFIED: Final = frozenset({2})
BATTERY_TYPES: Final = {0: "agm", 1: "flooded", 2: "user_defined"}
INPUT_VOLTAGE_RANGES: Final = {0: "appliance", 1: "ups"}
MACHINE_TYPES: Final = {"00": "grid_tie", "01": "off_grid", "10": "hybrid"}
TOPOLOGIES: Final = {0: "transformerless", 1: "transformer"}
OUTPUT_MODES: Final = {0: "single", 1: "parallel"}


@dataclass(frozen=True, slots=True)
class RatedInfo:
    """QPIRI response."""

    grid_rating_voltage: float  # 0
    grid_rating_current: float  # 1
    ac_output_rating_voltage: float  # 2
    ac_output_rating_frequency: float  # 3
    ac_output_rating_current: float  # 4
    ac_output_rating_apparent_power: int  # 5
    ac_output_rating_active_power: int  # 6
    battery_rating_voltage: float  # 7
    battery_recharge_voltage: float  # 8, back to utility (P12)
    battery_under_voltage: float  # 9, low DC cut-off (P29)
    battery_bulk_voltage: float  # 10 (P26)
    battery_float_voltage: float  # 11 (P27)
    battery_type: int  # 12
    max_ac_charging_current: int  # 13
    max_charging_current: int  # 14
    input_voltage_range: int  # 15
    output_source_priority: int  # 16, menu-position code
    charger_source_priority: int  # 17, menu-position code
    parallel_max_num: int  # 18
    machine_type: str  # 19
    topology: int  # 20
    output_mode: int  # 21
    battery_redischarge_voltage: float | None = None  # 22, back to battery (P13)
    pv_ok_condition: int | None = None  # 23
    pv_power_balance: int | None = None  # 24


def parse_qpiri(payload: str) -> RatedInfo:
    cmd = "QPIRI"
    f = _fields(payload, cmd, 22)
    return RatedInfo(
        grid_rating_voltage=_float(f[0], cmd),
        grid_rating_current=_float(f[1], cmd),
        ac_output_rating_voltage=_float(f[2], cmd),
        ac_output_rating_frequency=_float(f[3], cmd),
        ac_output_rating_current=_float(f[4], cmd),
        ac_output_rating_apparent_power=_int(f[5], cmd),
        ac_output_rating_active_power=_int(f[6], cmd),
        battery_rating_voltage=_float(f[7], cmd),
        battery_recharge_voltage=_float(f[8], cmd),
        battery_under_voltage=_float(f[9], cmd),
        battery_bulk_voltage=_float(f[10], cmd),
        battery_float_voltage=_float(f[11], cmd),
        battery_type=_int(f[12], cmd),
        max_ac_charging_current=_int(f[13], cmd),
        max_charging_current=_int(f[14], cmd),
        input_voltage_range=_int(f[15], cmd),
        output_source_priority=_int(f[16], cmd),
        charger_source_priority=_int(f[17], cmd),
        parallel_max_num=_int(f[18], cmd),
        machine_type=f[19],
        topology=_int(f[20], cmd),
        output_mode=_int(f[21], cmd),
        battery_redischarge_voltage=_float(f[22], cmd) if len(f) > 22 else None,
        pv_ok_condition=_int(f[23], cmd) if len(f) > 23 else None,
        pv_power_balance=_int(f[24], cmd) if len(f) > 24 else None,
    )


# --- QPIWS: warning / fault bits ------------------------------------------------

FAULT: Final = "fault"
WARNING: Final = "warning"
FAULT_IF_INVERTER_FAULT: Final = "fault_or_warning"  # fault when a1 is set, else warning

# index -> (key, kind). a0 (PV loss) is deliberately left out: it is set whenever
# the PV array is disconnected. a13 and a31 are reserved.
WARNING_BITS: Final[dict[int, tuple[str, str]]] = {
    1: ("inverter_fault", FAULT),
    2: ("bus_over", FAULT),
    3: ("bus_under", FAULT),
    4: ("bus_soft_fail", FAULT),
    5: ("line_fail", WARNING),
    6: ("opv_short", FAULT),
    7: ("inverter_voltage_too_low", FAULT),
    8: ("inverter_voltage_too_high", FAULT),
    9: ("over_temperature", FAULT_IF_INVERTER_FAULT),
    10: ("fan_locked", FAULT_IF_INVERTER_FAULT),
    11: ("battery_voltage_high", FAULT_IF_INVERTER_FAULT),
    12: ("battery_low_alarm", WARNING),
    14: ("battery_under_shutdown", WARNING),
    15: ("battery_derating", WARNING),
    16: ("overload", FAULT_IF_INVERTER_FAULT),
    17: ("eeprom_fault", WARNING),
    18: ("inverter_over_current", FAULT),
    19: ("inverter_soft_fail", FAULT),
    20: ("self_test_fail", FAULT),
    21: ("op_dc_voltage_over", FAULT),
    22: ("battery_open", WARNING),
    23: ("current_sensor_fail", FAULT),
    24: ("battery_short", FAULT),
    25: ("power_limit", WARNING),
    26: ("pv_voltage_high", WARNING),
    27: ("mppt_overload_fault", FAULT),
    28: ("mppt_overload_warning", WARNING),
    29: ("battery_too_low_to_charge", WARNING),
    30: ("dc_dc_over_current", FAULT),
}


@dataclass(frozen=True, slots=True)
class WarningStatus:
    """QPIWS response as a bit string (char index = bit number)."""

    bits: str

    def is_set(self, index: int) -> bool:
        return index < len(self.bits) and self.bits[index] == "1"

    @property
    def active(self) -> dict[str, str]:
        """Active known bits as {key: "fault" | "warning"}."""
        inverter_fault = self.is_set(1)
        result: dict[str, str] = {}
        for index, (key, kind) in WARNING_BITS.items():
            if not self.is_set(index):
                continue
            if kind == FAULT_IF_INVERTER_FAULT:
                kind = FAULT if inverter_fault else WARNING
            result[key] = kind
        return result

    @property
    def faults(self) -> list[str]:
        return [key for key, kind in self.active.items() if kind == FAULT]

    @property
    def warnings(self) -> list[str]:
        return [key for key, kind in self.active.items() if kind == WARNING]


def parse_qpiws(payload: str) -> WarningStatus:
    bits = _bits(payload.strip(), "QPIWS")
    if len(bits) < 31:
        raise InverterProtocolError(f"QPIWS: expected at least 31 bits, got {len(bits)}")
    return WarningStatus(bits=bits)


# --- QFLAG: option flags ----------------------------------------------------------

FLAGS: Final = {
    "a": "buzzer",
    "b": "overload_bypass",
    "j": "power_saving",
    "k": "lcd_return_to_default",
    "u": "overload_restart",
    "v": "over_temperature_restart",
    "x": "backlight",
    "y": "primary_source_interrupt_alarm",
    "z": "fault_code_record",
}


def parse_qflag(payload: str) -> dict[str, bool]:
    """Return {flag key: enabled} for every known flag letter present.

    Format: 'E' followed by enabled letters, 'D' followed by disabled letters.
    """
    text = payload.strip()
    if not text or text[0] not in "ED":
        raise InverterProtocolError(f"QFLAG: unexpected payload {payload!r}")
    result: dict[str, bool] = {}
    enabled = True
    for char in text:
        if char == "E":
            enabled = True
        elif char == "D":
            enabled = False
        elif char in FLAGS:
            result[FLAGS[char]] = enabled
        elif not char.isalpha():
            raise InverterProtocolError(f"QFLAG: unexpected character {char!r}")
    return result


# --- Static identification ----------------------------------------------------------


def parse_firmware(payload: str) -> str:
    """'VERFW:00040.09' -> '00040.09' (also 'VERFW2:...')."""
    _, sep, version = payload.strip().partition(":")
    if not sep or not version:
        raise InverterProtocolError(f"QVFW: unexpected payload {payload!r}")
    return version


def parse_current_options(payload: str) -> tuple[int, ...]:
    """QMCHGCR / QMUCHGCR: '010 020 030' -> (10, 20, 30)."""
    values = tuple(_int(v, "QM*CHGCR") for v in payload.split())
    if not values:
        raise InverterProtocolError(f"QM*CHGCR: empty payload {payload!r}")
    return values


@dataclass(frozen=True, slots=True)
class DeviceIdentity:
    """Static identification read once at start-up."""

    protocol_id: str  # QPI
    model: str  # QMN
    serial_number: str  # QID
    firmware_version: str  # QVFW
    firmware_version_2: str | None = None  # QVFW2 (SCC CPU)
    charging_current_options: tuple[int, ...] = ()  # QMCHGCR
    utility_charging_current_options: tuple[int, ...] = ()  # QMUCHGCR
    h_protocol: str | None = None  # QPRTL without CRC, e.g. "HPVINV02"; None = no H dialect
    firmware_date: str | None = None  # HIMSG1, ISO date


# --- Q1: extra status (only the verified charge stage is used) -------------------

# Q1[17]: 10 idle and 11 bulk verified; 12 absorb and 13 float are generic.
CHARGE_STAGES: Final = {10: "idle", 11: "bulk", 12: "absorb", 13: "float"}


def parse_q1_charge_stage(payload: str) -> str | None:
    """Return the charge stage key from Q1[17]; None for an unknown code."""
    fields = _fields(payload, "Q1", 18)
    return CHARGE_STAGES.get(_int(fields[17], "Q1"))


# --- QBEQI: battery equalization ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class Equalization:
    """QBEQI response (spec layout)."""

    enabled: bool  # 0, P30
    time: int  # 1, min, P33
    interval: int  # 2, days, P35
    max_current: int  # 3, A (follows P02)
    voltage: float  # 5, V, P31
    timeout: int  # 7, min, P34
    active: bool  # 8
    elapsed: int  # 9, h


def parse_qbeqi(payload: str) -> Equalization:
    cmd = "QBEQI"
    f = _fields(payload, cmd, 10)
    return Equalization(
        enabled=_int(f[0], cmd) == 1,
        time=_int(f[1], cmd),
        interval=_int(f[2], cmd),
        max_current=_int(f[3], cmd),
        voltage=_float(f[5], cmd),
        timeout=_int(f[7], cmd),
        active=_int(f[8], cmd) == 1,
        elapsed=_int(f[9], cmd),
    )
