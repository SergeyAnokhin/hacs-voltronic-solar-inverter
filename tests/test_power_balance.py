"""Power balance: inverter losses and full PV power from recorded QPIGS samples."""

import importlib.util
from pathlib import Path
import sys

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
sys.modules["power_balance"] = balance  # dataclasses look their module up here
_spec.loader.exec_module(balance)

OWN = balance.DEFAULT_OWN_CONSUMPTION  # battery 48, line 47, standby 12, solar charging 34 W
# Night, mode B, ~300 W load: 25.10 V x 15 A discharge, 317 W load, no PV, grid present.
LOAD = parse_qpigs(answered("snapshot_B_night_load_300w.json")["QPIGS"])
# Mode L, AC charging 2 A at 22.8 V, no discharge.
AC_CHARGING = parse_qpigs(answered("snapshot_L_night_ac_charging.json")["QPIGS"])
# Output off (status 2 b9 = 0), grid present.
OFF = parse_qpigs(answered("snapshot_S_night_output_off.json")["QPIGS"])
# Mode B with the grid disconnected.
GRID_OFF = parse_qpigs(answered("snapshot_B_night_grid_off.json")["QPIGS"])


def test_losses_at_night_battery_mode():
    # 25.10 x 15 - 317 = 59.5 W
    assert balance.inverter_losses(LOAD, "battery", 0) == 59.5
    # Without HGRID the grid counts as 0 outside line mode.
    assert balance.inverter_losses(LOAD, "battery", None) == 59.5


def test_losses_unknown_in_line_mode_without_grid_power():
    assert balance.inverter_losses(AC_CHARGING, "line", None) is None
    assert balance.pv_power_full(AC_CHARGING, "line", None, OWN) is None


def test_losses_with_grid_power():
    s = AC_CHARGING
    expected = round(s.battery_voltage * -s.battery_charge_current + 400 - s.ac_output_active_power, 1)
    assert balance.inverter_losses(s, "line", 400) == expected


def test_own_consumption_key():
    assert balance.own_consumption_key(LOAD, "battery") == "battery"
    assert balance.own_consumption_key(AC_CHARGING, "line") == "line"
    assert balance.own_consumption_key(LOAD, "standby") == "battery"  # status 2 b9 (output on) wins
    assert balance.own_consumption_key(OFF, "standby") == "standby"
    assert balance.own_consumption_key(OFF, "charging") == "solar_charging"


def test_own_consumption_grows_with_the_load():
    # 48 W + 3.5 % of 317 W
    assert round(balance.own_consumption(LOAD, "battery", OWN), 3) == 59.095
    assert balance.own_consumption(OFF, "standby", OWN) == 12


def test_pv_power_full_from_inverter_currents():
    # 317 W load + 59.1 W own - 376.5 W from the battery - 3 W unseen grid draw: ~0 at night.
    assert balance.pv_power_full(LOAD, "battery", 0, OWN) == 0
    # Line mode, battery charging 2 A: load + own + charge - (HGRID + 17 W it does not show).
    s = AC_CHARGING
    charge = s.battery_voltage * s.battery_charge_current
    load = s.ac_output_active_power
    expected = round(load + 47 + 0.013 * load + charge - 400 - 17, 1)
    assert balance.pv_power_full(s, "line", 400, OWN) == max(0.0, expected)


def test_pv_power_full_from_external_battery():
    # BMS says only 300 W leave the battery: ~73 W must come from PV.
    assert balance.pv_power_full(LOAD, "battery", 0, OWN, -300) == 73.1
    # Charging 200 W while feeding the load: PV covers both plus own consumption.
    assert balance.pv_power_full(LOAD, "battery", 0, OWN, 200) == 573.1
    # Never negative.
    assert balance.pv_power_full(LOAD, "battery", 0, OWN, -1000) == 0


def test_pv_power_full_follows_the_settings():
    more = {**OWN, "battery": 63.0}
    assert balance.pv_power_full(LOAD, "battery", 0, more, -300) == 88.1


def test_pv_power_full_without_grid():
    # No grid: nothing is drawn unseen from it, the battery supplies all of the own use.
    load = GRID_OFF.ac_output_active_power
    out = GRID_OFF.battery_voltage * GRID_OFF.battery_discharge_current
    expected = max(0.0, round(load + 48 + 0.035 * load - out, 1))
    assert balance.pv_power_full(GRID_OFF, "battery", 0, OWN) == expected


def test_pv_power_full_output_off():
    # Solar charging (mode C): 34 W own, 3 W of it from the grid unseen.
    assert balance.pv_power_full(OFF, "charging", 0, OWN, 100) == 131
    assert balance.pv_power_full(OFF, "charging", 0, OWN, -31) == 0  # dusk: battery feeds it
    # Standby: the inverter lives on the grid (12 W, HGRID shows 0), nothing from PV.
    assert balance.pv_power_full(OFF, "standby", 0, OWN, 0) == 0


def test_net_generation():
    # Night on battery: 317 W load - 376.5 W discharge - 3 W unseen grid draw.
    assert balance.net_generation(LOAD, "battery", 0, OWN) == -62.5
    # Grid export does not count as negative import.
    assert balance.net_generation(LOAD, "battery", -50, OWN) == -62.5
    assert balance.net_generation(LOAD, "battery", None, OWN) is None
    # Standby at night: the 12 W from the grid are the whole (negative) result.
    assert balance.net_generation(OFF, "standby", 0, OWN) == -12
    # Line mode, AC charging: all of load + charge came from the grid (and some more).
    s = AC_CHARGING
    charge = s.battery_voltage * s.battery_charge_current
    assert balance.net_generation(s, "line", 400, OWN) == round(
        s.ac_output_active_power + charge - 400 - 17, 1
    )


def test_breakdown_explains_the_full_pv_power():
    bd = balance.pv_power_full_breakdown(LOAD, "battery", 0, OWN, -300)
    assert bd.value == 73.1
    attributes = bd.attributes()
    assert attributes["formula"] == "max(0, load + own + battery_power - real_grid)"
    assert attributes["load"] == 317
    assert attributes["own"] == 59.1
    assert attributes["battery_power"] == -300
    assert attributes["real_grid"] == 3
    assert attributes["battery_power_formula"] == "external battery power sensor"
    assert attributes["own_formula"].endswith("48 + 0.035 * 317")
    assert attributes["real_grid_formula"].endswith("max(0, 0) + 3")
    assert attributes["formula_values"] == "max(0, 317 + 59.1 + (-300) - 3) = 73.1"


def test_breakdown_of_losses_and_net_generation_match_their_values():
    losses = balance.inverter_losses_breakdown(LOAD, "battery", 0)
    assert losses.value == balance.inverter_losses(LOAD, "battery", 0) == 59.5
    assert losses.filled() == "0 + 376.5 + 0 - 317 = 59.5"
    net = balance.net_generation_breakdown(LOAD, "battery", 0, OWN)
    assert net.value == balance.net_generation(LOAD, "battery", 0, OWN)
    assert net.formula == "load + battery_power - real_grid"
    assert balance.net_generation_breakdown(LOAD, "battery", None, OWN) is None


def test_breakdown_notes_a_missing_grid_reading():
    bd = balance.inverter_losses_breakdown(LOAD, "battery", None)
    assert bd.attributes()["grid_power_formula"] == "HGRID not read, counted as 0"
