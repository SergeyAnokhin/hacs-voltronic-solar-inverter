"""Entity tables of the voltronic component: key -> where the value sits in an answer.

Field indices are the 0-based tokens of the reply; layouts and verification status are in
docs/inverter-protocol.md and docs/settings-map.md. Keys follow the names of ESPHome's
core `pipsolar` component where one exists, so the entity names stay familiar.
"""

DIAG = "diagnostic"
MEAS = "measurement"
TOTAL_INC = "total_increasing"

# kind of binary sensor, same values as BinaryKind in voltronic.h
KIND_BIT = 0
KIND_FLAG = 1
KIND_MODE = 2
KIND_FAULTS = 3
KIND_WARNINGS = 4


def _s(cmd, field, unit=None, dec=0, dc=None, sc=MEAS, cat=None, pos=0, length=0, icon=None):
    return {
        "cmd": cmd,
        "field": field,
        "pos": pos,
        "len": length,
        "unit": unit,
        "dec": dec,
        "dc": dc,
        "sc": sc,
        "cat": cat,
        "icon": icon,
    }


SENSORS = {
    # QPIGS, fast
    "grid_voltage": _s("QPIGS", 0, "V", 1, "voltage"),
    "grid_frequency": _s("QPIGS", 1, "Hz", 1, "frequency"),
    "ac_output_voltage": _s("QPIGS", 2, "V", 1, "voltage"),
    "ac_output_frequency": _s("QPIGS", 3, "Hz", 1, "frequency"),
    "ac_output_apparent_power": _s("QPIGS", 4, "VA", 0, "apparent_power"),
    "ac_output_active_power": _s("QPIGS", 5, "W", 0, "power"),
    "output_load_percent": _s("QPIGS", 6, "%", 0, icon="mdi:percent"),
    "bus_voltage": _s("QPIGS", 7, "V", 0, "voltage", cat=DIAG),
    "battery_voltage": _s("QPIGS", 8, "V", 2, "voltage"),
    "battery_charging_current": _s("QPIGS", 9, "A", 0, "current"),
    # Voltage-derived estimate, NOT a state of charge (no BMS link on this unit).
    "battery_capacity_percent": _s("QPIGS", 10, "%", 0, cat=DIAG, icon="mdi:battery-unknown"),
    "heat_sink_temperature": _s("QPIGS", 11, "°C", 0, "temperature"),
    "pv_input_current": _s("QPIGS", 12, "A", 1, "current"),
    "pv_input_voltage": _s("QPIGS", 13, "V", 1, "voltage"),
    "battery_voltage_scc": _s("QPIGS", 14, "V", 2, "voltage", cat=DIAG),
    "battery_discharge_current": _s("QPIGS", 15, "A", 0, "current"),
    "pv_charging_power": _s("QPIGS", 19, "W", 0, "power"),
    # derived in C++: battery voltage * (charge A - discharge A), + = charging
    "battery_power": _s("QPIGS", -1, "W", 1, "power"),
    # HGRID (H dialect), fast: signed, + = import
    "grid_power": _s("HGRID", 6, "W", 0, "power"),
    # QPIRI, slow (current settings and ratings)
    "grid_rating_voltage": _s("QPIRI", 0, "V", 1, "voltage", cat=DIAG),
    "grid_rating_current": _s("QPIRI", 1, "A", 1, "current", cat=DIAG),
    "ac_output_rating_voltage": _s("QPIRI", 2, "V", 1, "voltage", cat=DIAG),
    "ac_output_rating_frequency": _s("QPIRI", 3, "Hz", 1, "frequency", cat=DIAG),
    "ac_output_rating_current": _s("QPIRI", 4, "A", 1, "current", cat=DIAG),
    "ac_output_rating_apparent_power": _s("QPIRI", 5, "VA", 0, "apparent_power", cat=DIAG),
    "ac_output_rating_active_power": _s("QPIRI", 6, "W", 0, "power", cat=DIAG),
    "battery_rating_voltage": _s("QPIRI", 7, "V", 1, "voltage", cat=DIAG),
    "battery_recharge_voltage": _s("QPIRI", 8, "V", 1, "voltage", cat=DIAG),  # P12
    "battery_under_voltage": _s("QPIRI", 9, "V", 1, "voltage", cat=DIAG),  # P29
    "battery_bulk_voltage": _s("QPIRI", 10, "V", 1, "voltage", cat=DIAG),  # P26
    "battery_float_voltage": _s("QPIRI", 11, "V", 1, "voltage", cat=DIAG),  # P27
    "max_ac_charging_current": _s("QPIRI", 13, "A", 0, "current", cat=DIAG),  # P11
    "max_charging_current": _s("QPIRI", 14, "A", 0, "current", cat=DIAG),  # P02
    "battery_redischarge_voltage": _s("QPIRI", 22, "V", 1, "voltage", cat=DIAG),  # P13
    # QBEQI, slow (equalization, read-only on purpose)
    "equalization_time": _s("QBEQI", 1, "min", 0, cat=DIAG, icon="mdi:timer-outline"),
    "equalization_interval": _s("QBEQI", 2, "d", 0, cat=DIAG, icon="mdi:calendar-clock"),
    "equalization_voltage": _s("QBEQI", 5, "V", 2, "voltage", cat=DIAG),
    "equalization_timeout": _s("QBEQI", 7, "min", 0, cat=DIAG, icon="mdi:timer-outline"),
    # HGEN (H dialect), slow: the inverter's own PV energy counters
    "pv_energy_today": _s("HGEN", 2, "kWh", 3, "energy", TOTAL_INC),
    "pv_energy_month": _s("HGEN", 3, "kWh", 3, "energy", TOTAL_INC),
    "pv_energy_year": _s("HGEN", 4, "kWh", 2, "energy", TOTAL_INC),
    "pv_energy_total": _s("HGEN", 5, "kWh", 2, "energy", TOTAL_INC),
    # HTEMP (H dialect), slow
    "inverter_temperature": _s("HTEMP", 0, "°C", 0, "temperature"),
    "transformer_temperature": _s("HTEMP", 2, "°C", 0, "temperature"),
    "pv_temperature": _s("HTEMP", 3, "°C", 0, "temperature"),
    "fan_1_speed": _s("HTEMP", 5, "%", 0, cat=DIAG, icon="mdi:fan"),
    "fan_2_speed": _s("HTEMP", 6, "%", 0, cat=DIAG, icon="mdi:fan"),
    # HEEP1 / HEEP2 (H dialect), slow
    "battery_low_alarm_voltage": _s("HEEP2", 3, "V", 1, "voltage", cat=DIAG),  # P24
    "ac_output_on_hour": _s("HEEP2", 12, "h", 0, cat=DIAG, pos=0, length=2),  # P48
    "ac_output_off_hour": _s("HEEP2", 12, "h", 0, cat=DIAG, pos=2, length=2),  # P49
    "ac_charger_start_hour": _s("HEEP2", 11, "h", 0, cat=DIAG, pos=0, length=2),  # P46
    "ac_charger_stop_hour": _s("HEEP2", 11, "h", 0, cat=DIAG, pos=2, length=2),  # P47
    "bms_shutdown_soc": _s("HEEP1", 10, "%", 0, cat=DIAG),  # P38, BMS not connected here
    "bms_back_to_battery_soc": _s("HEEP1", 12, "%", 0, cat=DIAG),  # P40
    "grid_tie_current": _s("HEEP1", 17, "A", 0, "current", cat=DIAG),  # P56
}


def _t(cmd, field, mapping=None, cat=None, pos=0, length=0, join_to=-1, icon=None):
    return {
        "cmd": cmd,
        "field": field,
        "pos": pos,
        "len": length,
        "join_to": join_to,
        "map": "|".join(f"{k}={v}" for k, v in (mapping or {}).items()),
        "cat": cat,
        "icon": icon,
    }


TEXT_SENSORS = {
    "device_mode": _t(
        "QMOD",
        0,
        {
            "P": "Power on",
            "S": "Standby",
            "L": "Line",
            "B": "Battery",
            "F": "Fault",
            "H": "Power saving",
            "D": "Shutdown",
            "C": "Charging",  # output off, battery charging (seen 2026-10-03)
        },
        icon="mdi:state-machine",
    ),
    # Codes follow the LCD menu position on this firmware (docs/settings-map.md)
    "output_source_priority": _t(
        "QPIRI", 16, {"0": "Solar first", "1": "SBU", "2": "Utility first"}, icon="mdi:transmission-tower"
    ),  # P01
    "charger_source_priority": _t(
        "QPIRI", 17, {"0": "Solar first", "1": "Solar and utility", "2": "Only solar"}, icon="mdi:battery-charging"
    ),  # P16
    "battery_type": _t("QPIRI", 12, {"0": "AGM", "1": "Flooded", "2": "User"}, cat="diagnostic"),  # P05
    "input_voltage_range": _t("QPIRI", 15, {"0": "Appliance", "1": "UPS"}, cat="diagnostic"),  # P03
    "charge_stage": _t(
        "Q1", 17, {"10": "Idle", "11": "Bulk", "12": "Absorption", "13": "Float"}, icon="mdi:battery-charging-medium"
    ),
    "solar_supply_priority": _t(
        "HEEP1", 3, {"0": "Battery first", "1": "Load first"}, pos=3, length=1, icon="mdi:solar-power"
    ),  # P43
    "inverter_clock": _t("HGEN", 0, cat="diagnostic", join_to=1, icon="mdi:clock-outline"),  # YYMMDD HH:MM
    # identity, read once at boot
    "protocol_id": _t("QPI", 0, cat="diagnostic"),
    "model": _t("QMN", 0, cat="diagnostic"),
    "serial_number": _t("QID", 0, cat="diagnostic"),
    "firmware_version": _t("QVFW", 0, cat="diagnostic"),
    "firmware_date": _t("HIMSG1", 1, cat="diagnostic"),
}


def _b(cmd, field, kind=KIND_BIT, pos=0, letters="", dc=None, cat=None, icon=None):
    return {
        "cmd": cmd,
        "field": field,
        "kind": kind,
        "pos": pos,
        "letters": letters,
        "dc": dc,
        "cat": cat,
        "icon": icon,
    }


BINARY_SENSORS = {
    # QPIGS status bits: char 0 = b7 ... char 7 = b0
    "load_status": _b("QPIGS", 16, pos=3, icon="mdi:power-plug"),  # b4
    "charging_status": _b("QPIGS", 16, pos=5, dc="battery_charging"),  # b2
    "scc_charging_status": _b("QPIGS", 16, pos=6, icon="mdi:solar-power"),  # b1
    "ac_charging_status": _b("QPIGS", 16, pos=7, icon="mdi:transmission-tower"),  # b0
    "switch_on": _b("QPIGS", 20, pos=1, icon="mdi:power"),  # status2 b9: AC output on (verified)
    "charging_to_float": _b("QPIGS", 20, pos=0, cat="diagnostic"),  # status2 b10
    "ac_output_active": _b("QMOD", 0, KIND_MODE, letters="LB", dc="running"),
    "warnings_present": _b("QPIWS", 0, KIND_WARNINGS, dc="problem"),
    "faults_present": _b("QPIWS", 0, KIND_FAULTS, dc="problem"),
    "equalization_enabled": _b("QBEQI", 0, cat="diagnostic"),
    "equalization_active": _b("QBEQI", 8, cat="diagnostic"),
    # QFLAG options (letter = flag), program numbers in docs/settings-map.md
    "buzzer": _b("QFLAG", 0, KIND_FLAG, letters="a", cat="diagnostic"),  # P18
    "overload_bypass": _b("QFLAG", 0, KIND_FLAG, letters="b", cat="diagnostic"),  # P23
    "power_saving": _b("QFLAG", 0, KIND_FLAG, letters="j", cat="diagnostic"),  # P08
    "lcd_return_to_default": _b("QFLAG", 0, KIND_FLAG, letters="k", cat="diagnostic"),  # P19
    "overload_restart": _b("QFLAG", 0, KIND_FLAG, letters="u", cat="diagnostic"),  # P06
    "over_temperature_restart": _b("QFLAG", 0, KIND_FLAG, letters="v", cat="diagnostic"),  # P07
    "backlight": _b("QFLAG", 0, KIND_FLAG, letters="x", cat="diagnostic"),  # P20
    "primary_source_interrupt_alarm": _b("QFLAG", 0, KIND_FLAG, letters="y", cat="diagnostic"),  # P22
    "fault_code_record": _b("QFLAG", 0, KIND_FLAG, letters="z", cat="diagnostic"),  # P25
}

# QPIWS bit number -> key (a0 PV loss is set whenever the array is disconnected; a13, a31 reserved)
QPIWS_BITS = {
    0: "pv_loss",
    1: "inverter_fault",
    2: "bus_over",
    3: "bus_under",
    4: "bus_soft_fail",
    5: "line_fail",
    6: "opv_short",
    7: "inverter_voltage_too_low",
    8: "inverter_voltage_too_high",
    9: "over_temperature",
    10: "fan_locked",
    11: "battery_voltage_high",
    12: "battery_low_alarm",
    14: "battery_under_shutdown",
    15: "battery_derating",
    16: "overload",
    17: "eeprom_fault",
    18: "inverter_over_current",
    19: "inverter_soft_fail",
    20: "self_test_fail",
    21: "op_dc_voltage_over",
    22: "battery_open",
    23: "current_sensor_fail",
    24: "battery_short",
    25: "power_limit",
    26: "pv_voltage_high",
    27: "mppt_overload_fault",
    28: "mppt_overload_warning",
    29: "battery_too_low_to_charge",
    30: "dc_dc_over_current",
}
for _bit, _key in QPIWS_BITS.items():
    BINARY_SENSORS[f"alarm_{_key}"] = _b("QPIWS", 0, pos=_bit, dc="problem")


# ---------------------------------------------------------------------------------------------
# Control entities (switch / select / number / button). Every setting text is checked again in
# C++ (protocol.h is_allowed_write), whose ranges must equal commands.py: tests/test_esphome_controls.py
# compares them. All writes are UNVERIFIED on the unit until the owner tests them one by one, and
# nothing is ever sent unless the hub has `enable_writes: true`.
# ---------------------------------------------------------------------------------------------


def _sw(on, off, cmd, field, kind, pos=0, letters="", icon=None):
    return {"on": on, "off": off, "cmd": cmd, "field": field, "kind": kind, "pos": pos, "letters": letters, "icon": icon}


SWITCHES = {
    # QFLAG options, P-number in docs/settings-map.md: PE<x> enables, PD<x> disables; read back from QFLAG
    "buzzer": _sw("PEa", "PDa", "QFLAG", 0, KIND_FLAG, letters="a", icon="mdi:volume-high"),  # P18
    "overload_bypass": _sw("PEb", "PDb", "QFLAG", 0, KIND_FLAG, letters="b"),  # P23
    "power_saving": _sw("PEj", "PDj", "QFLAG", 0, KIND_FLAG, letters="j"),  # P08
    "lcd_return_to_default": _sw("PEk", "PDk", "QFLAG", 0, KIND_FLAG, letters="k"),  # P19
    "overload_restart": _sw("PEu", "PDu", "QFLAG", 0, KIND_FLAG, letters="u"),  # P06
    "over_temperature_restart": _sw("PEv", "PDv", "QFLAG", 0, KIND_FLAG, letters="v"),  # P07
    "backlight": _sw("PEx", "PDx", "QFLAG", 0, KIND_FLAG, letters="x", icon="mdi:brightness-6"),  # P20
    "primary_source_interrupt_alarm": _sw("PEy", "PDy", "QFLAG", 0, KIND_FLAG, letters="y"),  # P22
    "fault_code_record": _sw("PEz", "PDz", "QFLAG", 0, KIND_FLAG, letters="z"),  # P25
    # service tool setters (docs/settings-map.md): dual output mode P60 (HEEP2[0]) and the second
    # output on / off now (HSTS[2] char 4, verified on 2026-11-12)
    "second_output_mode": _sw("PDAULC01", "PDAULC00", "HEEP2", 0, KIND_BIT, pos=0),
    "second_output": _sw("PDAULON01", "PDAULON00", "HSTS", 2, KIND_BIT, pos=4, icon="mdi:power-socket-eu"),
}


def _sel(options, cmd=None, field=0, mapping=None, pos=0, length=0, assumed=False, icon=None):
    return {
        "options": options,  # option text -> setting text
        "cmd": cmd,
        "field": field,
        "pos": pos,
        "len": length,
        "map": "|".join(f"{k}={v}" for k, v in (mapping or {}).items()),
        "assumed": assumed,
        "icon": icon,
    }


SELECTS = {
    # Codes follow the LCD menu position on this firmware (only owner-verified codes are offered)
    "output_source_priority": _sel(  # P01
        {"Solar first": "POP00", "SBU": "POP01"},
        "QPIRI", 16, {"0": "Solar first", "1": "SBU"}, icon="mdi:transmission-tower",
    ),
    "charger_source_priority": _sel(  # P16
        {"Solar first": "PCP00", "Solar and utility": "PCP01", "Only solar": "PCP02"},
        "QPIRI", 17, {"0": "Solar first", "1": "Solar and utility", "2": "Only solar"}, icon="mdi:battery-charging",
    ),
    "solar_supply_priority": _sel(  # P43
        {"Battery first": "PVENGUSE00", "Load first": "PVENGUSE01"},
        "HEEP1", 3, {"0": "Battery first", "1": "Load first"}, pos=3, length=1, icon="mdi:solar-power",
    ),
    # The lists the owner's unit reports (QMCHGCR 10..80 A, QMUCHGCR 2, 10..60 A); other units differ
    "max_charging_current": _sel(  # P02
        {f"{a} A": f"MNCHGC{a:03d}" for a in range(10, 90, 10)},
        "QPIRI", 14, {str(a): f"{a} A" for a in range(10, 90, 10)}, icon="mdi:current-dc",
    ),
    "max_ac_charging_current": _sel(  # P11
        {f"{a} A": f"MUCHGC{a:03d}" for a in (2, 10, 20, 30, 40, 50, 60)},
        "QPIRI", 13, {str(a): f"{a} A" for a in (2, 10, 20, 30, 40, 50, 60)}, icon="mdi:current-ac",
    ),
    # Axpert MAX protocol, cannot be read back: shows the last ACKed option
    "battery_control": _sel(
        {
            "Auto": "PBATCD000",
            "No discharge": "PBATCD101",
            "No charge": "PBATCD110",
            "No charge, no discharge": "PBATCD100",
        },
        assumed=True, icon="mdi:battery-lock",
    ),
}


def _n(kind, unit, lo, hi, step, cmd=None, field=0, pos=0, length=0, prefix="", dc=None, assumed=False,
       ac_output=False, is_start=False, icon=None):
    return {
        "kind": kind,  # "value" (prefix + value), "max_discharge", "schedule"
        "prefix": prefix,
        "unit": unit,
        "min": lo,
        "max": hi,
        "step": step,
        "cmd": cmd,
        "field": field,
        "pos": pos,
        "len": length,
        "dc": dc,
        "assumed": assumed,
        "ac_output": ac_output,
        "is_start": is_start,
        "icon": icon,
    }


NUMBERS = {
    # battery voltages, 24 V system (ranges: Vevor manual)
    "battery_recharge_voltage": _n("value", "V", 22.0, 25.5, 0.5, "QPIRI", 8, prefix="PBCV", dc="voltage"),  # P12
    "battery_redischarge_voltage": _n("value", "V", 24.0, 29.0, 0.5, "QPIRI", 22, prefix="PBDV", dc="voltage"),  # P13
    "battery_under_voltage": _n("value", "V", 20.0, 26.0, 0.1, "QPIRI", 9, prefix="PSDV", dc="voltage"),  # P29
    "battery_bulk_voltage": _n("value", "V", 24.0, 30.0, 0.1, "QPIRI", 10, prefix="PCVV", dc="voltage"),  # P26
    # service tool setters, read back from HEEP1 / HEEP2
    "battery_low_alarm_voltage": _n("value", "V", 20.0, 27.0, 0.1, "HEEP2", 3, prefix="PSLV", dc="voltage"),  # P24
    "second_output_cutoff_voltage": _n("value", "V", 20.0, 30.0, 0.1, "HEEP2", 1, prefix="PDSDV", dc="voltage"),
    "second_output_recover_voltage": _n("value", "V", 20.0, 30.0, 0.1, "HEEP2", 15, prefix="PDSRV", dc="voltage"),
    "second_output_cutoff_soc": _n("value", "%", 0, 100, 1, "HEEP2", 2, prefix="PDSDS"),
    "second_output_recover_soc": _n("value", "%", 0, 50, 1, "HEEP2", 16, pos=0, length=2, prefix="PDSRS"),
    "second_output_recover_delay": _n("value", "min", 0, 60, 5, "HEEP2", 13, prefix="PDDLYT"),
    "second_output_discharge_time": _n("value", "min", 0, 990, 5, "HEEP2", 16, pos=2, length=3, prefix="PDDCGT"),
    # BMS settings: this installation has no BMS link, list them only when you have one
    "bms_lock_soc": _n("value", "%", 0, 100, 1, "HEEP1", 10, prefix="BMSSDC"),  # P38
    "bms_back_to_ac_soc": _n("value", "%", 0, 100, 1, "HEEP1", 11, prefix="BMSB2UC"),  # P39
    "bms_back_to_battery_soc": _n("value", "%", 0, 100, 1, "HEEP1", 12, prefix="BMSU2BC"),  # P40
    "bms_restart_soc": _n("value", "%", 0, 100, 1, "HEEP1", 13, prefix="BMSSRC"),  # P41
    # not readable on this firmware: show the last ACKed value
    "battery_discharge_current_limit": _n("value", "A", 0, 250, 1, prefix="DISCC", dc="current", assumed=True),
    "max_discharging_current": _n("max_discharge", "A", 0, 150, 10, dc="current", assumed=True),
    # AC output (P48/P49) and AC charger (P46/P47) windows; a change sends the whole window
    "ac_output_on_hour": _n("schedule", "h", 0, 23, 1, "HEEP2", 12, pos=0, length=2, ac_output=True, is_start=True),
    "ac_output_off_hour": _n("schedule", "h", 0, 23, 1, "HEEP2", 12, pos=2, length=2, ac_output=True),
    "ac_charger_start_hour": _n("schedule", "h", 0, 23, 1, "HEEP2", 11, pos=0, length=2, is_start=True),
    "ac_charger_stop_hour": _n("schedule", "h", 0, 23, 1, "HEEP2", 11, pos=2, length=2),
}

BUTTONS = {
    # ^S???DAT: sets the inverter clock to the ESP32's local time (needs a `time:` component)
    "set_clock": {"icon": "mdi:clock-check-outline"},
}
