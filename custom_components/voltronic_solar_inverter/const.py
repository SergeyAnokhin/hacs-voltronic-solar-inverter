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
CONF_ENABLE_CONTROLS: Final = "enable_controls"

DEFAULT_FAST_INTERVAL: Final = 10  # s, QPIGS + QMOD
DEFAULT_SLOW_INTERVAL: Final = 60  # s, QPIRI + QFLAG + QPIWS
MIN_FAST_INTERVAL: Final = 5
MAX_FAST_INTERVAL: Final = 300
MIN_SLOW_INTERVAL: Final = 30
MAX_SLOW_INTERVAL: Final = 3600
