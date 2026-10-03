"""Base entity and the single write path used by all control entities."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MAX_MISSED_UPDATES
from .coordinator import VoltronicFastCoordinator, VoltronicSlowCoordinator
from .protocol import (
    DeviceIdentity,
    InvalidCommandError,
    InverterError,
    InverterNakError,
    WriteCommand,
)

type VoltronicCoordinator = VoltronicFastCoordinator | VoltronicSlowCoordinator

# Coordinator data fields that come from the CRC-less H dialect.
H_FIELDS = frozenset({"grid_power", "heep1", "heep2", "generation", "temperatures"})


def is_supported(description: EntityDescription, identity: DeviceIdentity) -> bool:
    """False for H-dialect entities on inverters that do not answer QPRTL."""
    requires = getattr(description, "requires", None)
    return requires not in H_FIELDS or identity.h_protocol is not None


def remove_entities(
    hass: HomeAssistant, identity: DeviceIdentity, domain: str, keys: Iterable[str]
) -> None:
    """Delete registry entries of entities that are no longer created (by description key)."""
    registry = er.async_get(hass)
    for key in keys:
        unique_id = f"{identity.serial_number}_{key}"
        if entity_id := registry.async_get_entity_id(domain, DOMAIN, unique_id):
            registry.async_remove(entity_id)


class VoltronicEntity[CoordinatorT: VoltronicCoordinator](CoordinatorEntity[CoordinatorT]):
    """Common device info and unique id (<serial>_<description key>)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CoordinatorT, description: EntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        identity = coordinator.identity
        self._attr_unique_id = f"{identity.serial_number}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identity.serial_number)},
            manufacturer=MANUFACTURER,
            model=identity.model,
            name=coordinator.config_entry.title,
            serial_number=identity.serial_number,
            sw_version=identity.firmware_version,
        )

    @property
    def available(self) -> bool:
        """Unavailable only after MAX_MISSED_UPDATES failed updates in a row.

        Also unavailable when the optional part this entity needs was not read;
        descriptions may set ``requires`` to a coordinator data field name.
        """
        coordinator = self.coordinator
        if coordinator.data is None or (
            not coordinator.last_update_success and coordinator.failures > MAX_MISSED_UPDATES
        ):
            return False
        requires = getattr(self.entity_description, "requires", None)
        if requires is None:
            return True
        value = getattr(self.coordinator.data, requires)
        return value is not None and value is not False


class VoltronicControlEntity(VoltronicEntity[VoltronicSlowCoordinator]):
    """Base for switch/select/number: sends one setting command, then refreshes settings."""

    async def async_send(self, build: Callable[[], WriteCommand]) -> None:
        """Validate and send a setting command; raise a HA error unless it is ACKed."""
        try:
            command = build()
        except InvalidCommandError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_value",
                translation_placeholders={"error": str(err)},
            ) from err
        client = self.coordinator.config_entry.runtime_data.client
        try:
            await client.write(command)
        except InverterNakError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_rejected",
                translation_placeholders={"command": command.text},
            ) from err
        except InverterError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"command": command.text, "error": str(err)},
            ) from err
        await self.coordinator.async_refresh()
