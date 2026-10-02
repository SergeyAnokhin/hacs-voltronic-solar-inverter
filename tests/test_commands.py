"""Write-command builders: exact frames and argument validation.

These only build bytes; nothing is sent to a device.
"""

import pytest

from protocol import commands
from protocol.errors import InvalidCommandError

CHARGE_OPTIONS = (10, 20, 30, 40, 50, 60, 70, 80)
UTILITY_OPTIONS = (2, 10, 20, 30, 40, 50, 60)


@pytest.mark.parametrize(
    ("flag", "enabled", "frame_hex"),
    [
        ("buzzer", True, "504561d0700d"),
        ("buzzer", False, "504461e3410d"),
        ("overload_bypass", True, "504562e0130d"),
        ("overload_bypass", False, "504462d3220d"),
        ("power_saving", True, "50456a611b0d"),
        ("power_saving", False, "50446a522a0d"),
        ("lcd_return_to_default", True, "50456b713a0d"),
        ("lcd_return_to_default", False, "50446b420b0d"),
        ("overload_restart", True, "50457582c50d"),
        ("overload_restart", False, "504475b1f40d"),
        ("over_temperature_restart", True, "504576b2a60d"),
        ("over_temperature_restart", False, "50447681970d"),
        ("backlight", True, "50457853680d"),
        ("backlight", False, "50447860590d"),
        ("primary_source_interrupt_alarm", True, "50457943490d"),
        ("primary_source_interrupt_alarm", False, "50447970780d"),
        ("fault_code_record", True, "50457a732a0d"),
        ("fault_code_record", False, "50447a401b0d"),
    ],
)
def test_set_flag_frames(flag, enabled, frame_hex):
    assert commands.set_flag(flag, enabled).frame == bytes.fromhex(frame_hex)


def test_set_flag_rejects_unknown():
    with pytest.raises(InvalidCommandError):
        commands.set_flag("a", True)  # letters are not keys
    with pytest.raises(InvalidCommandError):
        commands.set_flag("factory_reset", True)


def test_output_source_priority_sbu_frame():
    cmd = commands.set_output_source_priority(1)
    assert cmd.text == "POP01"
    assert cmd.frame == bytes.fromhex("504f503031d2690d")


@pytest.mark.parametrize("code", [0, 2, 3, -1, "1", None])
def test_output_source_priority_rejects_unverified(code):
    with pytest.raises(InvalidCommandError):
        commands.set_output_source_priority(code)


def test_charger_source_priority_only_solar_frame():
    cmd = commands.set_charger_source_priority(2)
    assert cmd.text == "PCP02"
    assert cmd.frame == bytes.fromhex("50435030 32ad380d".replace(" ", ""))


@pytest.mark.parametrize("code", [0, 1, 3, "2"])
def test_charger_source_priority_rejects_unverified(code):
    with pytest.raises(InvalidCommandError):
        commands.set_charger_source_priority(code)


def test_escaped_crc_in_a_write_frame():
    # POP02 has CRC 0xE20A; the low byte must go out as 0x0B. Built only via
    # WriteCommand directly, because code 2 is not verified for the builder.
    assert commands.WriteCommand("POP02").frame == bytes.fromhex("504f503032e20b0d")


@pytest.mark.parametrize(
    ("amps", "text", "frame_hex"),
    [(10, "MCHGC010", "4d43484743303130 84260d"), (50, "MCHGC050", "4d43484743303530 48e20d")],
)
def test_max_charging_current_frames(amps, text, frame_hex):
    cmd = commands.set_max_charging_current(amps, CHARGE_OPTIONS)
    assert cmd.text == text
    assert cmd.frame == bytes.fromhex(frame_hex.replace(" ", ""))


@pytest.mark.parametrize("amps", [0, 15, 90, 100, 50.0, True, "50"])
def test_max_charging_current_rejects(amps):
    with pytest.raises(InvalidCommandError):
        commands.set_max_charging_current(amps, CHARGE_OPTIONS)


def test_max_charging_current_rejects_three_digit_option():
    with pytest.raises(InvalidCommandError):
        commands.set_max_charging_current(100, (100,))


@pytest.mark.parametrize(
    ("amps", "text", "frame_hex"),
    [(2, "MUCHGC002", "4d55434847433030 32b5d10d"), (30, "MUCHGC030", "4d55434847433033 30c0c00d")],
)
def test_max_utility_charging_current_frames(amps, text, frame_hex):
    cmd = commands.set_max_utility_charging_current(amps, UTILITY_OPTIONS)
    assert cmd.text == text
    assert cmd.frame == bytes.fromhex(frame_hex.replace(" ", ""))


@pytest.mark.parametrize("amps", [0, 1, 5, 70])
def test_max_utility_charging_current_rejects(amps):
    with pytest.raises(InvalidCommandError):
        commands.set_max_utility_charging_current(amps, UTILITY_OPTIONS)


@pytest.mark.parametrize(
    ("key", "volts", "text", "frame_hex"),
    [
        ("battery_recharge_voltage", 22.0, "PBCV22.0", "5042435632322e30 73d20d"),
        ("battery_redischarge_voltage", 27.0, "PBDV27.0", "5042445632372e30 50630d"),
        ("battery_under_voltage", 21.0, "PSDV21.0", "5053445632312e30 6dd90d"),
        ("battery_bulk_voltage", 28.2, "PCVV28.2", "5043565632382e32 75b50d"),
    ],
)
def test_battery_voltage_frames(key, volts, text, frame_hex):
    cmd = commands.set_battery_voltage(key, volts)
    assert cmd.text == text
    assert cmd.frame == bytes.fromhex(frame_hex.replace(" ", ""))


def test_battery_voltage_range_edges():
    assert commands.set_battery_voltage("battery_recharge_voltage", 25.5).text == "PBCV25.5"
    assert commands.set_battery_voltage("battery_under_voltage", 20.0).text == "PSDV20.0"
    assert commands.set_battery_voltage("battery_bulk_voltage", 30).text == "PCVV30.0"


@pytest.mark.parametrize(
    ("key", "volts"),
    [
        ("battery_recharge_voltage", 21.5),  # below range
        ("battery_recharge_voltage", 26.0),  # above range
        ("battery_recharge_voltage", 22.3),  # not a 0.5 V step
        ("battery_redischarge_voltage", 0.0),  # "battery full" code is not documented for this unit
        ("battery_under_voltage", 26.1),
        ("battery_under_voltage", 21.05),
        ("battery_bulk_voltage", 23.9),
        ("battery_float_voltage", 27.0),  # PBFT intentionally not implemented
        ("battery_bulk_voltage", "28.2"),
        ("battery_bulk_voltage", True),
    ],
)
def test_battery_voltage_rejects(key, volts):
    with pytest.raises(InvalidCommandError):
        commands.set_battery_voltage(key, volts)
