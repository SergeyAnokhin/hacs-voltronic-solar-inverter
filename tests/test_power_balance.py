"""Power balance: inverter losses and calculated PV power from recorded QPIGS samples."""

import importlib.util
from pathlib import Path

from conftest import answered
from protocol.parsers import parse_qpigs

_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "voltronic_solar_inverter"
    / "power_balance.py"
)
_spec = importlib.util.spec_from_file_location("power_balance", _PATH)
balance = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(balance)

# Night, mode B, ~300 W load: 25.10 V x 15 A discharge, 317 W load, no PV.
LOAD = parse_qpigs(answered("snapshot_B_night_load_300w.json")["QPIGS"])
# Mode L, AC charging 2 A at 22.8 V, no discharge.
AC_CHARGING = parse_qpigs(answered("snapshot_L_night_ac_charging.json")["QPIGS"])


def test_losses_at_night_battery_mode():
    # 25.10 x 15 - 317 = 59.5 W
    assert balance.inverter_losses(LOAD, "battery", 0) == 59.5
    # Without HGRID the grid counts as 0 outside line mode.
    assert balance.inverter_losses(LOAD, "battery", None) == 59.5


def test_losses_unknown_in_line_mode_without_grid_power():
    assert balance.inverter_losses(AC_CHARGING, "line", None) is None
    assert balance.pv_power_calculated(AC_CHARGING, "line", None, 50) is None


def test_losses_with_grid_power():
    s = AC_CHARGING
    expected = round(s.battery_voltage * -s.battery_charge_current + 400 - s.ac_output_active_power, 1)
    assert balance.inverter_losses(s, "line", 400) == expected


def test_pv_power_calculated():
    # Battery delivers 376.5 W, load 317 W: with 59.5 W own use there is no PV.
    assert balance.pv_power_calculated(LOAD, "battery", 0, 59.5) == 0
    # With 100 W own use, 40.5 W must come from somewhere else (PV).
    assert balance.pv_power_calculated(LOAD, "battery", 0, 100) == 40.5
    # Never negative.
    assert balance.pv_power_calculated(LOAD, "battery", 0, 0) == 0


def test_self_consumption_key():
    assert balance.self_consumption_key(LOAD, "battery") == "battery"
    assert balance.self_consumption_key(AC_CHARGING, "line") == "line"
    assert balance.self_consumption_key(LOAD, "standby") == "battery"  # status 2 b9 (output on) wins
    standby = parse_qpigs(answered("snapshot_S_night_output_off.json")["QPIGS"])
    assert balance.self_consumption_key(standby, "standby") == "output_off"


def test_net_generation():
    # Night on battery: 317 W load - 376.5 W discharge = -59.5 W (losses only, no PV).
    assert balance.net_generation(LOAD, 0, 0) == -59.5
    # The unseen own consumption is a loss too.
    assert balance.net_generation(LOAD, 0, 10) == -69.5
    # Grid export does not count as negative import.
    assert balance.net_generation(LOAD, -50, 0) == -59.5
    assert balance.net_generation(LOAD, None, 0) is None
    # Line mode, AC charging: all of load + charge came from the grid (and some more).
    s = AC_CHARGING
    charge = s.battery_voltage * s.battery_charge_current
    assert balance.net_generation(s, 400, 16) == round(s.ac_output_active_power + charge - 400 - 16, 1)
