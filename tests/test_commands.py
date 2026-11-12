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


def test_output_source_priority_sub_frame():
    assert commands.set_output_source_priority(0).text == "POP00"


@pytest.mark.parametrize("code", [2, 3, -1, "1", None])
def test_output_source_priority_rejects_unverified(code):
    with pytest.raises(InvalidCommandError):
        commands.set_output_source_priority(code)


def test_charger_source_priority_solar_first_frame():
    assert commands.set_charger_source_priority(0).text == "PCP00"


def test_charger_source_priority_solar_and_utility_frame():
    assert commands.set_charger_source_priority(1).text == "PCP01"


def test_charger_source_priority_only_solar_frame():
    cmd = commands.set_charger_source_priority(2)
    assert cmd.text == "PCP02"
    assert cmd.frame == bytes.fromhex("50435030 32ad380d".replace(" ", ""))


@pytest.mark.parametrize("code", [3, -1, "2"])
def test_charger_source_priority_rejects_unverified(code):
    with pytest.raises(InvalidCommandError):
        commands.set_charger_source_priority(code)


def test_escaped_crc_in_a_write_frame():
    # POP02 has CRC 0xE20A; the low byte must go out as 0x0B. Built only via
    # WriteCommand directly, because code 2 is not verified for the builder.
    assert commands.WriteCommand("POP02").frame == bytes.fromhex("504f503032e20b0d")


@pytest.mark.parametrize(
    ("amps", "text", "frame_hex"),
    [(10, "MNCHGC010", "4d4e434847433031304db90d"), (50, "MNCHGC050", "4d4e43484743303530817d0d")],
)
def test_max_charging_current_frames(amps, text, frame_hex):
    cmd = commands.set_max_charging_current(amps, CHARGE_OPTIONS)
    assert cmd.text == text
    assert cmd.frame == bytes.fromhex(frame_hex)


@pytest.mark.parametrize("amps", [0, 15, 90, 100, 50.0, True, "50"])
def test_max_charging_current_rejects(amps):
    with pytest.raises(InvalidCommandError):
        commands.set_max_charging_current(amps, CHARGE_OPTIONS)


def test_max_charging_current_three_digits():
    assert commands.set_max_charging_current(120, (100, 120)).text == "MNCHGC120"
    with pytest.raises(InvalidCommandError):
        commands.set_max_charging_current(1000, (1000,))


@pytest.mark.parametrize(
    ("code", "frame_hex"),
    [(0, "5056454e4755534530305e610d"), (1, "5056454e4755534530314e400d")],
)
def test_solar_supply_priority_frames(code, frame_hex):
    assert commands.set_solar_supply_priority(code).frame == bytes.fromhex(frame_hex)


@pytest.mark.parametrize("code", [2, -1, "1", True, None])
def test_solar_supply_priority_rejects(code):
    with pytest.raises(InvalidCommandError):
        commands.set_solar_supply_priority(code)


def test_priority_builders_reject_bool():
    with pytest.raises(InvalidCommandError):
        commands.set_output_source_priority(True)


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


@pytest.mark.parametrize(
    ("mode", "text"),
    [
        ("auto", "PBATCD000"),
        ("no_discharge", "PBATCD101"),
        ("no_charge", "PBATCD110"),
        ("no_charge_no_discharge", "PBATCD100"),
    ],
)
def test_battery_control_frames(mode, text):
    assert commands.set_battery_control(mode).text == text


@pytest.mark.parametrize("mode", ["shutdown", "011", "010", None, 1])
def test_battery_control_rejects_unknown(mode):
    with pytest.raises(InvalidCommandError):
        commands.set_battery_control(mode)


@pytest.mark.parametrize(
    ("amps", "text"), [(0, "PBATMAXDISC000"), (30, "PBATMAXDISC030"), (150, "PBATMAXDISC150")]
)
def test_max_discharging_current_frame(amps, text):
    assert commands.set_max_discharging_current(amps).text == text


@pytest.mark.parametrize("amps", [10, 29, 151, -1, True, 30.0, "30"])
def test_max_discharging_current_rejects(amps):
    with pytest.raises(InvalidCommandError):
        commands.set_max_discharging_current(amps)


@pytest.mark.parametrize(
    ("kind", "start", "end", "text"),
    [
        ("ac_output", 12, 20, "^S???ACLT12-20"),
        ("ac_output", 23, 0, "^S???ACLT23-00"),
        ("ac_charger", 1, 2, "^S???ACCT01-02"),
        ("ac_charger", 0, 23, "^S???ACCT00-23"),
    ],
)
def test_schedule_frames(kind, start, end, text):
    assert commands.set_schedule(kind, start, end).text == text


def test_schedule_frame_bytes():
    # Frame bytes worked out from the service tool's format (CRC-16/XMODEM, three literal "?").
    assert commands.set_schedule("ac_output", 12, 20).frame == bytes.fromhex(
        "5e533f3f3f41434c5431322d3230ce290d"
    )


@pytest.mark.parametrize(
    ("kind", "start", "end"),
    [
        ("dual_output", 1, 2),
        (None, 1, 2),
        ("ac_output", 24, 1),
        ("ac_output", 1, -1),
        ("ac_output", True, 2),
        ("ac_output", 1.0, 2),
        ("ac_output", "01", 2),
    ],
)
def test_schedule_rejects(kind, start, end):
    with pytest.raises(InvalidCommandError):
        commands.set_schedule(kind, start, end)


@pytest.mark.parametrize(
    ("key", "volts", "text"),
    [
        ("battery_low_alarm_voltage", 23.6, "PSLV23.6"),
        ("battery_low_alarm_voltage", 20, "PSLV20.0"),
        ("battery_low_alarm_voltage", 27.0, "PSLV27.0"),
        ("second_output_cutoff_voltage", 22.0, "PDSDV22.0"),
        ("second_output_recover_voltage", 26.0, "PDSRV26.0"),
    ],
)
def test_heep_voltage_frames(key, volts, text):
    assert commands.set_heep_voltage(key, volts).text == text


@pytest.mark.parametrize(
    ("key", "volts"),
    [
        ("battery_low_alarm_voltage", 19.9),
        ("battery_low_alarm_voltage", 27.1),
        ("battery_low_alarm_voltage", 23.65),
        ("second_output_cutoff_voltage", 31),
        ("battery_bulk_voltage", 28.2),  # not an EEPROM voltage setting
        ("second_output_recover_voltage", "26.0"),
        ("second_output_recover_voltage", True),
    ],
)
def test_heep_voltage_rejects(key, volts):
    with pytest.raises(InvalidCommandError):
        commands.set_heep_voltage(key, volts)


@pytest.mark.parametrize(
    ("key", "value", "text"),
    [
        ("bms_lock_soc", 20, "BMSSDC020"),
        ("bms_back_to_ac_soc", 100, "BMSB2UC100"),
        ("bms_back_to_battery_soc", 95, "BMSU2BC095"),
        ("bms_restart_soc", 0, "BMSSRC000"),
        ("second_output_cutoff_soc", 20, "PDSDS020"),
        ("second_output_recover_soc", 50, "PDSRS050"),
        ("second_output_recover_delay", 5, "PDDLYT005"),
        ("second_output_recover_delay", 60, "PDDLYT060"),
        ("second_output_discharge_time", 0, "PDDCGT0000"),
        ("second_output_discharge_time", 990, "PDDCGT0990"),
        ("battery_discharge_current_limit", 80, "DISCC080"),
    ],
)
def test_integer_setting_frames(key, value, text):
    assert commands.set_integer_setting(key, value).text == text


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("bms_lock_soc", 101),
        ("bms_lock_soc", -1),
        ("second_output_recover_soc", 51),  # range of the sibling unit: 0-50 %
        ("second_output_recover_delay", 4),  # 5-minute steps
        ("second_output_discharge_time", 7),
        ("second_output_discharge_time", 995),
        ("battery_discharge_current_limit", 251),
        ("bms_restart_soc", 50.0),
        ("bms_restart_soc", "50"),
        ("bms_restart_soc", True),
        ("battery_bulk_voltage", 28),  # unknown key
    ],
)
def test_integer_setting_rejects(key, value):
    with pytest.raises(InvalidCommandError):
        commands.set_integer_setting(key, value)


def test_dual_output_frames():
    assert commands.set_dual_output_mode(True).text == "PDAULC01"
    assert commands.set_dual_output_mode(False).text == "PDAULC00"
    assert commands.set_second_output(True).text == "PDAULON01"
    assert commands.set_second_output(False).text == "PDAULON00"
    for bad in (1, 0, "on", None):
        with pytest.raises(InvalidCommandError):
            commands.set_dual_output_mode(bad)
        with pytest.raises(InvalidCommandError):
            commands.set_second_output(bad)


def test_clock_frame():
    from datetime import datetime

    command = commands.set_clock(datetime(2026, 11, 12, 21, 5, 9))
    assert command.text == "^S???DAT261112210509"
    assert command.frame.startswith(b"^S???DAT261112210509") and command.frame.endswith(b"\r")


@pytest.mark.parametrize("moment", [None, "2026-11-12", 20261112])
def test_clock_rejects_non_datetime(moment):
    with pytest.raises(InvalidCommandError):
        commands.set_clock(moment)


def test_clock_rejects_years_outside_the_lcd_range():
    from datetime import datetime

    with pytest.raises(InvalidCommandError):
        commands.set_clock(datetime(2015, 1, 1))
