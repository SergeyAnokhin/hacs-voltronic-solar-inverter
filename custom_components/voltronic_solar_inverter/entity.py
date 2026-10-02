"""Base entity and the single write path used by all control entities."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import VoltronicFastCoordinator, VoltronicSlowCoordinator
from .protocol import InvalidCommandError, InverterError, InverterNakError, WriteCommand

type VoltronicCoordinator = VoltronicFastCoordinator | VoltronicSlowCoordinator


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
