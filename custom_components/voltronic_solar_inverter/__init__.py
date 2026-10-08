"""The Voltronic Solar Inverter integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_FAST_INTERVAL,
    CONF_SLOW_INTERVAL,
    DEFAULT_FAST_INTERVAL,
    DEFAULT_SLOW_INTERVAL,
    DISABLED_KEYS,
    DOMAIN,
    HIDDEN_KEYS,
    LOGGER,
    RENAMED_KEYS,
)
from .coordinator import (
    VoltronicConfigEntry,
    VoltronicFastCoordinator,
    VoltronicRuntimeData,
    VoltronicSlowCoordinator,
)
from .protocol import InverterClient, InverterError

# number/select/switch send setting commands (always set up; changes are at the user's risk).
PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


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

    entry.runtime_data = VoltronicRuntimeData(client=client, identity=identity, fast=fast, slow=slow)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: VoltronicConfigEntry) -> bool:
    """1.1 -> 1.3: rename keys (keeping history), hide static and disable equalization entities.

    Registry defaults only apply to new entities, so existing ones are updated
    here once. Entities the user already hid or disabled are left alone.
    1.2 -> 1.3 only renames (the calculated PV sensors became "full").
    """
    if entry.version > 1:
        return False
    if entry.minor_version < 3:
        registry = er.async_get(hass)
        prefix = f"{entry.unique_id}_"
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            if not entity.unique_id.startswith(prefix):
                continue
            key = entity.unique_id.removeprefix(prefix)
            changes: dict = {}
            if (new_key := RENAMED_KEYS.get(key)) is not None:
                changes["new_unique_id"] = f"{prefix}{new_key}"
                new_entity_id = entity.entity_id.removesuffix(key) + new_key
                if entity.entity_id.endswith(key) and registry.async_get(new_entity_id) is None:
                    changes["new_entity_id"] = new_entity_id
            if entry.minor_version < 2:
                if key in HIDDEN_KEYS and entity.hidden_by is None:
                    changes["hidden_by"] = er.RegistryEntryHider.INTEGRATION
                if key in DISABLED_KEYS and entity.disabled_by is None:
                    changes["disabled_by"] = er.RegistryEntryDisabler.INTEGRATION
            if changes:
                registry.async_update_entity(entity.entity_id, **changes)
        hass.config_entries.async_update_entry(entry, minor_version=3)
        LOGGER.debug("Migrated config entry %s to version 1.3", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VoltronicConfigEntry) -> bool:
    """Unload a config entry and close the gateway connection."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.close()
    return unloaded
