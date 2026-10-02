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

DEFAULT_FAST_INTERVAL: Final = 10  # s, QPIGS + QMOD
DEFAULT_SLOW_INTERVAL: Final = 60  # s, QPIRI + QFLAG + QPIWS
MIN_FAST_INTERVAL: Final = 2  # one fast cycle (QPIGS + QMOD + HGRID) takes ~1.5 s
MAX_FAST_INTERVAL: Final = 300
MIN_SLOW_INTERVAL: Final = 30
MAX_SLOW_INTERVAL: Final = 3600

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

# Smoothed sensors: mean over SMOOTHING_WINDOW s, published on a change of
# >= 10 % (and >= the absolute threshold), on a drop to 0, or after the heartbeat.
SMOOTHING_WINDOW: Final = 60.0
SMOOTHING_RELATIVE_THRESHOLD: Final = 0.10
SMOOTHING_ABSOLUTE_THRESHOLD_W: Final = 20.0
SMOOTHING_HEARTBEAT: Final = 600.0
