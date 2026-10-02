"""Binary sensors: status bits, mode, fault/warning summary, QPIWS bits, QFLAG flags."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import FastData, SlowData, VoltronicConfigEntry, VoltronicFastCoordinator
from .entity import VoltronicEntity
from .protocol.parsers import FLAGS, OUTPUT_ACTIVE_MODES, WARNING_BITS

PARALLEL_UPDATES = 0

# Output priority code for SBU on this firmware (menu position, owner-confirmed).
SBU_CODE = 1

# QPIWS bits shown by default; the rest are created disabled.
DEFAULT_ENABLED_WARNING_BITS = frozenset(
    {"line_fail", "battery_low_alarm", "battery_under_shutdown", "overload", "over_temperature"}
)


@dataclass(frozen=True, kw_only=True)
class VoltronicFastBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[FastData], bool | None]


@dataclass(frozen=True, kw_only=True)
class VoltronicSlowBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[SlowData], bool | None]
    requires: str | None = None  # SlowData field that must have been read


FAST_BINARY_SENSORS: tuple[VoltronicFastBinaryDescription, ...] = (
    VoltronicFastBinaryDescription(
        key="ac_output_active",
        translation_key="ac_output_active",
        device_class=BinarySensorDeviceClass.POWER,
        value_fn=lambda d: d.mode in OUTPUT_ACTIVE_MODES,
    ),
    VoltronicFastBinaryDescription(
        key="load_on",
        translation_key="load_on",
        device_class=BinarySensorDeviceClass.POWER,
        value_fn=lambda d: d.status.load_on,
    ),
    VoltronicFastBinaryDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda d: d.status.charging,
    ),
    VoltronicFastBinaryDescription(
        key="solar_charging",
        translation_key="solar_charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda d: d.status.scc_charging,
    ),
    VoltronicFastBinaryDescription(
        key="grid_charging",
        translation_key="grid_charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda d: d.status.ac_charging,
    ),
    VoltronicFastBinaryDescription(
        key="charging_to_float",
        translation_key="charging_to_float",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.status.charging_to_float,
    ),
)

SLOW_BINARY_SENSORS: tuple[VoltronicSlowBinaryDescription, ...] = (
    VoltronicSlowBinaryDescription(
        key="sbu_priority",
        translation_key="sbu_priority",
        value_fn=lambda d: d.rated.output_source_priority == SBU_CODE,
    ),
    VoltronicSlowBinaryDescription(
        key="equalization_enabled",
        translation_key="equalization_enabled",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.equalization.enabled,
        requires="equalization",
    ),
    VoltronicSlowBinaryDescription(
        key="equalization_active",
        translation_key="equalization_active",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.equalization.active,
        requires="equalization",
    ),
    *(
        VoltronicSlowBinaryDescription(
            key=f"warning_{key}",
            translation_key=key,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=key in DEFAULT_ENABLED_WARNING_BITS,
            value_fn=lambda d, index=index: d.warnings.is_set(index),
        )
        for index, (key, _kind) in WARNING_BITS.items()
    ),
    *(
        VoltronicSlowBinaryDescription(
            key=f"flag_{flag}",
            translation_key=f"flag_{flag}",
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda d, flag=flag: d.flags.get(flag),
        )
        for flag in FLAGS.values()
    ),
)

FAULT_DESCRIPTION = BinarySensorEntityDescription(
    key="fault", translation_key="fault", device_class=BinarySensorDeviceClass.PROBLEM
)
WARNING_DESCRIPTION = BinarySensorEntityDescription(
    key="warning", translation_key="warning", device_class=BinarySensorDeviceClass.PROBLEM
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VoltronicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    data = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        VoltronicFastBinarySensor(data.fast, d) for d in FAST_BINARY_SENSORS
    ]
    entities += [VoltronicSlowBinarySensor(data.slow, d) for d in SLOW_BINARY_SENSORS]
    entities += [
        VoltronicFaultSensor(data.slow, FAULT_DESCRIPTION, data.fast),
        VoltronicWarningSensor(data.slow, WARNING_DESCRIPTION),
    ]
    async_add_entities(entities)


class VoltronicFastBinarySensor(VoltronicEntity, BinarySensorEntity):
    entity_description: VoltronicFastBinaryDescription

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)


class VoltronicSlowBinarySensor(VoltronicEntity, BinarySensorEntity):
    entity_description: VoltronicSlowBinaryDescription

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)


class VoltronicFaultSensor(VoltronicEntity, BinarySensorEntity):
    """On when QPIWS reports a fault or QMOD reports fault mode."""

    def __init__(self, coordinator, description, fast: VoltronicFastCoordinator) -> None:
        super().__init__(coordinator, description)
        self._fast = fast

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._fast.async_add_listener(self._handle_coordinator_update))

    @property
    def _fault_mode(self) -> bool:
        return bool(self._fast.last_update_success and self._fast.data.mode == "fault")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.warnings.faults) or self._fault_mode

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"faults": self.coordinator.data.warnings.faults, "fault_mode": self._fault_mode}


class VoltronicWarningSensor(VoltronicEntity, BinarySensorEntity):
    """On when QPIWS reports any warning (bit a0 'PV loss' is ignored)."""

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.warnings.warnings)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"warnings": self.coordinator.data.warnings.warnings}
