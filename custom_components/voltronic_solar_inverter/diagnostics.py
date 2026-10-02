"""Diagnostics download (serial number and gateway address are redacted)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import VoltronicConfigEntry

TO_REDACT = {CONF_HOST, "serial_number", "unique_id", "QID", "QSID"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VoltronicConfigEntry
) -> dict[str, Any]:
    data = entry.runtime_data
    slow = data.slow.data
    return async_redact_data(
        {
            "entry": {
                "title": entry.title,
                "unique_id": entry.unique_id,
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            "identity": asdict(data.identity),
            "fast": {
                "last_update_success": data.fast.last_update_success,
                "data": asdict(data.fast.data) if data.fast.data else None,
            },
            "slow": {
                "last_update_success": data.slow.last_update_success,
                "data": asdict(slow) if slow else None,
                "active_warning_bits": slow.warnings.active if slow else None,
            },
            "raw_responses": dict(data.client.last_responses),
        },
        TO_REDACT,
    )
