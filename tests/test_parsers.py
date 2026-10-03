"""Parsers against responses recorded from the real inverter (tests/fixtures)."""

import pytest

from conftest import answered
from protocol.errors import InverterProtocolError
from protocol.parsers import (
    parse_current_options,
    parse_firmware,
    parse_qflag,
    parse_qmod,
    parse_qpigs,
    parse_qpiri,
    parse_qpiws,
)

FULL = answered("snapshot_B_night_output_on.json")
LOAD = answered("snapshot_B_night_load_300w.json")
GRID_OFF = answered("snapshot_B_night_grid_off.json")
STANDBY = answered("snapshot_schedule_23-00.json")


def test_qpigs_battery_mode_with_load():
    s = parse_qpigs(LOAD["QPIGS"])
    assert s.grid_voltage == 234.1
    assert s.grid_frequency == 50.0
    assert s.ac_output_voltage == 230.1
    assert s.ac_output_frequency == 50.0
    assert s.ac_output_apparent_power == 483
    assert s.ac_output_active_power == 317
    assert s.load_percent == 12
    assert s.bus_voltage == 372
    assert s.battery_voltage == 25.10
    assert s.battery_charge_current == 0
    assert s.battery_capacity_estimate == 82
    assert s.heatsink_temperature == 41
    assert s.pv_input_current == 0.0
    assert s.pv_input_voltage == 0.0
    assert s.scc_battery_voltage == 0.0
    assert s.battery_discharge_current == 15
    assert s.pv_charging_power == 0
    assert s.battery_power == pytest.approx(-376.5)


def test_qpigs_status_bits():
    s = parse_qpigs(LOAD["QPIGS"])  # status 00010000, status2 010
    assert s.load_on is True
    assert s.charging is False
    assert s.scc_charging is False
    assert s.ac_charging is False
    assert s.switched_on is True
    assert s.charging_to_float is False


def test_qpigs_charging_bits_decoding():
    fields = LOAD["QPIGS"].split()
    fields[16] = "00010111"
    fields[20] = "110"
    s = parse_qpigs(" ".join(fields))
    assert (s.charging, s.scc_charging, s.ac_charging) == (True, True, True)
    assert s.charging_to_float is True


def test_qpigs_grid_off():
    s = parse_qpigs(GRID_OFF["QPIGS"])
    assert s.grid_voltage == 0.0
    assert s.grid_frequency == 0.0


def test_qpigs_short_legacy_layout_has_no_tail():
    fields = LOAD["QPIGS"].split()[:17]
    s = parse_qpigs(" ".join(fields))
    assert s.pv_charging_power is None
    assert s.switched_on is None


@pytest.mark.parametrize(
    "payload",
    ["", "234.1 50.0", LOAD["QPIGS"].replace("25.10", "x"), LOAD["QPIGS"].replace("00010000", "0001000")],
)
def test_qpigs_rejects_bad_payloads(payload):
    with pytest.raises(InverterProtocolError):
        parse_qpigs(payload)


def test_qmod():
    assert parse_qmod(FULL["QMOD"]) == "battery"
    assert parse_qmod(STANDBY["QMOD"]) == "standby"
    assert parse_qmod("L") == "line"
    assert parse_qmod("C") == "charging"  # live 2026-10-03: output off, PV charging, no grid
    with pytest.raises(InverterProtocolError):
        parse_qmod("X")


def test_qpiri_fixture():
    r = parse_qpiri(FULL["QPIRI"])
    assert r.grid_rating_voltage == 230.0
    assert r.grid_rating_current == 17.3
    assert r.ac_output_rating_voltage == 230.0
    assert r.ac_output_rating_frequency == 50.0
    assert r.ac_output_rating_current == 17.3
    assert r.ac_output_rating_apparent_power == 4000
    assert r.ac_output_rating_active_power == 4000
    assert r.battery_rating_voltage == 24.0
    assert r.battery_recharge_voltage == 22.0
    assert r.battery_under_voltage == 21.6
    assert r.battery_bulk_voltage == 29.2
    assert r.battery_float_voltage == 29.1
    assert r.battery_type == 2
    assert r.max_ac_charging_current == 2
    assert r.max_charging_current == 50
    assert r.input_voltage_range == 0
    assert r.output_source_priority == 1  # SBU on this firmware (owner-confirmed)
    assert r.charger_source_priority == 2  # only solar (owner-confirmed)
    assert r.parallel_max_num == 9
    # Prototype off-by-one fixed: 19 machine type, 20 topology, 21 output mode.
    assert r.machine_type == "01"
    assert r.topology == 0
    assert r.output_mode == 0
    assert r.battery_redischarge_voltage == 25.0
    assert r.pv_ok_condition == 1
    assert r.pv_power_balance == 1


def test_qpiri_too_short():
    with pytest.raises(InverterProtocolError):
        parse_qpiri("230.0 17.3 230.0")


def test_qpiws_pv_loss_only_is_not_a_problem():
    w = parse_qpiws(FULL["QPIWS"])  # a0 set (PV disconnected)
    assert w.is_set(0)
    assert w.active == {}
    assert w.faults == []
    assert w.warnings == []


def test_qpiws_line_fail_recorded():
    w = parse_qpiws(GRID_OFF["QPIWS"])  # a0 + a5
    assert w.active == {"line_fail": "warning"}
    assert w.warnings == ["line_fail"]


def test_qpiws_fault_or_warning_depends_on_a1():
    bits = ["0"] * 32
    bits[16] = "1"  # overload
    assert parse_qpiws("".join(bits)).active == {"overload": "warning"}
    bits[1] = "1"  # inverter fault
    w = parse_qpiws("".join(bits))
    assert w.active == {"inverter_fault": "fault", "overload": "fault"}
    assert w.warnings == []


def test_qpiws_reserved_bits_ignored():
    bits = ["0"] * 32
    bits[13] = bits[31] = "1"
    assert parse_qpiws("".join(bits)).active == {}


@pytest.mark.parametrize("payload", ["", "1000", "1" * 30 + "2" + "0"])
def test_qpiws_rejects_bad_payloads(payload):
    with pytest.raises(InverterProtocolError):
        parse_qpiws(payload)


def test_qflag_fixture():
    assert parse_qflag(FULL["QFLAG"]) == {
        "buzzer": True,
        "overload_bypass": True,
        "power_saving": True,
        "over_temperature_restart": True,
        "backlight": True,
        "primary_source_interrupt_alarm": True,
        "lcd_return_to_default": False,
        "overload_restart": False,
        "fault_code_record": False,
    }


def test_qflag_unknown_letters_are_skipped():
    assert parse_qflag("EaDbq") == {"buzzer": True, "overload_bypass": False}


@pytest.mark.parametrize("payload", ["", "abc", "Ea1"])
def test_qflag_rejects_bad_payloads(payload):
    with pytest.raises(InverterProtocolError):
        parse_qflag(payload)


def test_firmware_and_current_lists():
    assert parse_firmware(FULL["QVFW"]) == "00040.09"
    assert parse_firmware(FULL["QVFW2"]) == "00000.00"
    assert parse_current_options(FULL["QMCHGCR"]) == (10, 20, 30, 40, 50, 60, 70, 80)
    assert parse_current_options(FULL["QMUCHGCR"]) == (2, 10, 20, 30, 40, 50, 60)
    with pytest.raises(InverterProtocolError):
        parse_firmware("00040.09")
    with pytest.raises(InverterProtocolError):
        parse_current_options("")
