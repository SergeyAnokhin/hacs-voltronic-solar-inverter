"""Solar Plug H dialect, Q1 and QBEQI parsers against recorded responses."""

from datetime import datetime

import pytest

from conftest import answered, plain_answered
from protocol.errors import InverterProtocolError
from protocol.framing import decode_plain_frame, encode_plain_frame
from protocol.h_parsers import (
    Schedule,
    parse_heep1,
    parse_heep2,
    parse_hgen,
    parse_hgrid_power,
    parse_himsg1_firmware_date,
    parse_htemp,
    parse_schedule,
)
from protocol.parsers import parse_q1_charge_stage, parse_qbeqi

H_S = plain_answered("probe_h_commands_S.json")  # schedule 19-21, P43 BLU, P46/P47 00-00
H_SCHED = plain_answered("probe_heep2_schedule_23-00.json")
H_LBU = plain_answered("snapshot_p46-47_01-02_p43_LBU_h.json")  # P46/P47 01-02, P43 LBU
H_BATT = plain_answered("snapshot_battery_settings_after_h.json")
S_OFF = answered("snapshot_S_night_output_off.json")
L_CHG = answered("snapshot_L_night_ac_charging.json")
Q_LBU = answered("snapshot_p46-47_01-02_p43_LBU_q.json")


def test_plain_framing():
    assert encode_plain_frame("HGEN") == b"HGEN\r"
    assert decode_plain_frame(b"(HPVINV02\r") == "HPVINV02"
    assert decode_plain_frame(b"(1 2 \r") == "1 2 "
    for bad in (b"HPVINV02\r", b"(", b""):
        with pytest.raises(InverterProtocolError):
            decode_plain_frame(bad)


def test_hgen_clock_and_energy():
    g = parse_hgen(H_S["HGEN"])
    assert g.clock == datetime(2026, 10, 2, 21, 1)
    assert g.pv_energy_today == 1.765
    assert g.pv_energy_month == 3.1
    assert g.pv_energy_year == 8.5
    assert g.pv_energy_total == 8.5


def test_hgen_rejects_bad_clock():
    with pytest.raises(InverterProtocolError):
        parse_hgen("261302 21:01 01.765 0003.1 0008.5 000000008.5")


def test_heep2_ac_output_schedule_verified_change():
    assert parse_heep2(H_S["HEEP2"]).ac_output_schedule == Schedule(19, 21)
    assert parse_heep2(H_SCHED["HEEP2"]).ac_output_schedule == Schedule(23, 0)


def test_heep2_ac_charger_schedule_verified_change():
    assert parse_heep2(H_S["HEEP2"]).ac_charger_schedule == Schedule(0, 0)
    assert parse_heep2(H_LBU["HEEP2"]).ac_charger_schedule == Schedule(1, 2)


def test_heep2_other_positions():
    s = parse_heep2(H_LBU["HEEP2"])
    assert s.battery_low_alarm_voltage == 22.0
    assert s.dual_output_cutoff_voltage == 22.0
    assert s.dual_output_recover_delay == 5
    assert s.dual_output_schedule == Schedule(0, 0)
    assert s.dual_output_recover_voltage == 26.0


def test_heep1_solar_supply_priority_verified_change():
    assert parse_heep1(H_S["HEEP1"]).solar_supply_priority == 0  # BLU
    lbu = parse_heep1(H_LBU["HEEP1"])
    assert lbu.solar_supply_priority == 1  # LBU
    assert lbu.bms_shutdown_soc == 10
    assert lbu.bms_back_to_battery_soc == 95
    assert lbu.grid_tie_current == 12


def test_heep_mirror_battery_settings_after_change():
    # HEEP2[4]/[5] follow P12/P13 (also visible in QPIRI) - parser must not break.
    assert parse_heep1(H_BATT["HEEP1"]).solar_supply_priority == 1
    assert parse_heep2(H_BATT["HEEP2"]).ac_output_schedule == Schedule(23, 0)


@pytest.mark.parametrize("value", ["123", "2400", "0a00", "19210"])
def test_schedule_rejects(value):
    with pytest.raises(InverterProtocolError):
        parse_schedule(value, "HEEP2")


def test_htemp():
    t = parse_htemp(H_S["HTEMP"])
    assert (t.inverter, t.boost, t.transformer, t.pv) == (28, 39, 32, 32)
    assert (t.fan_1_speed, t.fan_2_speed) == (30, 30)


def test_hgrid_power_signed():
    assert parse_hgrid_power(H_S["HGRID"]) == 0
    assert parse_hgrid_power("239.0 50.0 280 090 70 40 +00412 1 04500 11+00000") == 412
    assert parse_hgrid_power("239.0 50.0 280 090 70 40 -00100 2 04500 11+00000") == -100


def test_himsg1_firmware_date():
    assert parse_himsg1_firmware_date(H_S["HIMSG1"]) == "2026-01-19"
    with pytest.raises(InverterProtocolError):
        parse_himsg1_firmware_date("0040.09 2026")


def test_q1_charge_stage():
    assert parse_q1_charge_stage(S_OFF["Q1"]) == "idle"
    assert parse_q1_charge_stage(L_CHG["Q1"]) == "bulk"
    with pytest.raises(InverterProtocolError):
        parse_q1_charge_stage("030 5472")


def test_qbeqi():
    e = parse_qbeqi(Q_LBU["QBEQI"])
    assert e.enabled is False
    assert (e.time, e.interval, e.max_current, e.timeout) == (60, 30, 50, 120)
    assert e.voltage == 29.2
    assert e.active is False
    assert e.elapsed == 0
