"""The Voltronic Solar Inverter integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_ENABLE_CONTROLS,
    CONF_FAST_INTERVAL,
    CONF_SLOW_INTERVAL,
    DEFAULT_FAST_INTERVAL,
    DEFAULT_SLOW_INTERVAL,
    DOMAIN,
)
from .coordinator import (
    VoltronicConfigEntry,
    VoltronicFastCoordinator,
    VoltronicRuntimeData,
    VoltronicSlowCoordinator,
)
from .protocol import InverterClient, InverterError

READ_PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]
# Write-capable platforms, only set up when the "Enable control entities" option is on.
CONTROL_PLATFORMS = [Platform.NUMBER, Platform.SELECT, Platform.SWITCH]


def _platforms(controls_enabled: bool) -> list[Platform]:
    return READ_PLATFORMS + CONTROL_PLATFORMS if controls_enabled else READ_PLATFORMS


async def async_setup_entry(hass: HomeAssistant, entry: VoltronicConfigEntry) -> bool:
    """Set up the inverter from a config entry."""
    client = InverterClient(entry.data[CONF_HOST], entry.data[CONF_PORT])
    try:
        identity = await client.read_identity()
    except InverterError as err:
        await client.close()
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"error": str(err)},
        ) from err

    options = entry.options
    fast = VoltronicFastCoordinator(
        hass, entry, client, identity, "fast",
        options.get(CONF_FAST_INTERVAL, DEFAULT_FAST_INTERVAL),
    )
    slow = VoltronicSlowCoordinator(
        hass, entry, client, identity, "slow",
        options.get(CONF_SLOW_INTERVAL, DEFAULT_SLOW_INTERVAL),
    )
    try:
        await fast.async_config_entry_first_refresh()
        await slow.async_config_entry_first_refresh()
    except Exception:
        await client.close()
        raise

    controls_enabled = options.get(CONF_ENABLE_CONTROLS, False)
    entry.runtime_data = VoltronicRuntimeData(
        client=client,
        identity=identity,
        fast=fast,
        slow=slow,
        controls_enabled=controls_enabled,
    )
    if not controls_enabled:
        _remove_control_entities(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, _platforms(controls_enabled))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VoltronicConfigEntry) -> bool:
    """Unload a config entry and close the gateway connection."""
    data = entry.runtime_data
    unloaded = await hass.config_entries.async_unload_platforms(
        entry, _platforms(data.controls_enabled)
    )
    if unloaded:
        await data.client.close()
    return unloaded


def _remove_control_entities(hass: HomeAssistant, entry: VoltronicConfigEntry) -> None:
    """Drop number/select/switch entities left over from when controls were enabled."""
    registry = er.async_get(hass)
    control_domains = {str(platform) for platform in CONTROL_PLATFORMS}
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.domain in control_domains:
            registry.async_remove(entity.entity_id)
