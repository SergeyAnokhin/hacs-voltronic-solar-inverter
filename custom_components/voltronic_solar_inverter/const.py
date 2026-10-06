"""Constants for the Voltronic Solar Inverter integration."""

from __future__ import annotations

import logging
from typing import Final

DOMAIN: Final = "voltronic_solar_inverter"
LOGGER = logging.getLogger(__package__)

MANUFACTURER: Final = "Voltronic Power"

DEFAULT_PORT: Final = 8899

CONF_FAST_INTERVAL: Final = "fast_scan_interval"
CONF_SLOW_INTERVAL: Final = "slow_scan_interval"
# Optional external battery power sensor (W or kW, + = charging), e.g. a BMS
CONF_BATTERY_POWER_SENSOR: Final = "battery_power_sensor"

# Attribute on every entity polled by the slow coordinator (settings, ratings, flags, warnings).
ATTR_UPDATE_GROUP: Final = "update_group"
UPDATE_GROUP_SLOW: Final = "slow"

DEFAULT_FAST_INTERVAL: Final = 10  # s, QPIGS + QMOD
DEFAULT_SLOW_INTERVAL: Final = 60  # s, QPIRI + QFLAG + QPIWS
MIN_FAST_INTERVAL: Final = 2  # one fast cycle (QPIGS + QMOD + HGRID) takes ~1.5 s
MAX_FAST_INTERVAL: Final = 300
MIN_SLOW_INTERVAL: Final = 30
MAX_SLOW_INTERVAL: Final = 3600
# A single lost answer must not make entities flicker: entities keep the last
# value for this many consecutive failed updates (and an optional H-dialect
# part keeps its last value for this many missed reads) before going unavailable.
MAX_MISSED_UPDATES: Final = 5

# Static values (ratings, identity): created hidden; they never change.
HIDDEN_KEYS: Final = frozenset(
    {
        "grid_rating_voltage",
        "grid_rating_current",
        "ac_output_rating_voltage",
        "ac_output_rating_frequency",
        "ac_output_rating_current",
        "ac_output_rating_apparent_power",
        "ac_output_rating_active_power",
        "battery_rating_voltage",
        "machine_type",
        "topology",
        "output_mode",
        "serial_number",
        "firmware_version",
        "firmware_version_2",
        "protocol_id",
        "firmware_date",
    }
)
# Equalization (not used with the owner's LiFePO4 bank): created disabled.
DISABLED_KEYS: Final = frozenset(
    {
        "equalization_voltage",
        "equalization_time",
        "equalization_timeout",
        "equalization_interval",
        "equalization_enabled",
        "equalization_active",
    }
)
# Entity keys renamed in config entry minor version 2 (old -> new); history is kept.
# The old PV power sensor becomes the smoothed, recorded one.
RENAMED_KEYS: Final = {"pv_charging_power": "pv_power"}
# Sensor keys no longer created; their registry entries are deleted at setup.
REMOVED_KEYS: Final = frozenset({"pv_power_median_today"})  # removed in 0.4.6

# Smoothed sensors: mean over SMOOTHING_WINDOW s, published on a change of
# >= 10 % (and >= the absolute threshold), on a drop to 0, or after the heartbeat.
SMOOTHING_WINDOW: Final = 60.0
SMOOTHING_RELATIVE_THRESHOLD: Final = 0.10
SMOOTHING_ABSOLUTE_THRESHOLD_W: Final = 20.0
# PV voltage: ~100-400 V, so a smaller relative step and a volt-sized absolute one.
SMOOTHING_RELATIVE_THRESHOLD_VOLTAGE: Final = 0.05
SMOOTHING_ABSOLUTE_THRESHOLD_VOLTAGE: Final = 1.0
SMOOTHING_HEARTBEAT: Final = 600.0
# PV power median sensor: median over this many seconds, same publish rules.
MEDIAN_WINDOW: Final = 600.0  # also used for the 10 min maximum
# Daily energy sensors: integrated from every sample, written on a change of
# >= ENERGY_STEP_KWH or after SMOOTHING_HEARTBEAT; a gap longer than
# ENERGY_MAX_GAP_INTERVALS fast intervals adds no energy.
ENERGY_STEP_KWH: Final = 0.05
ENERGY_MAX_GAP_INTERVALS: Final = 3

# Read-only sensors that only repeat a control entity (switch/select/number) are
# not created while that control exists (see sensor._duplicates_control).
CONTROL_DUPLICATE_KEYS: Final = frozenset(
    {
        "output_source_priority",
        "charger_source_priority",
        "solar_supply_priority",
        "max_charging_current",
        "max_ac_charging_current",
        "battery_recharge_voltage",
        "battery_redischarge_voltage",
        "battery_under_voltage",
        "battery_bulk_voltage",
    }
)
