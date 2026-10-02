"""Sensors: live values (fast), ratings/settings (slow) and device identity."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import FastData, SlowData, VoltronicConfigEntry
from .entity import VoltronicEntity
from .protocol.parsers import (
    BATTERY_TYPES,
    CHARGER_SOURCE_PRIORITIES,
    DEVICE_MODES,
    INPUT_VOLTAGE_RANGES,
    MACHINE_TYPES,
    OUTPUT_MODES,
    OUTPUT_SOURCE_PRIORITIES,
    TOPOLOGIES,
    DeviceIdentity,
)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class VoltronicFastSensorDescription(SensorEntityDescription):
    value_fn: Callable[[FastData], StateType]


@dataclass(frozen=True, kw_only=True)
class VoltronicSlowSensorDescription(SensorEntityDescription):
    value_fn: Callable[[SlowData], StateType]
    code_fn: Callable[[SlowData], Any] | None = None  # raw code shown as attribute for enums


@dataclass(frozen=True, kw_only=True)
class VoltronicIdentitySensorDescription(SensorEntityDescription):
    value_fn: Callable[[DeviceIdentity], StateType]


def _voltage(key: str, value_fn, **kwargs) -> dict[str, Any]:
    return dict(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=value_fn,
        **kwargs,
    )


def _current(key: str, value_fn, **kwargs) -> dict[str, Any]:
    return dict(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=value_fn,
        **kwargs,
    )


def _frequency(key: str, value_fn, **kwargs) -> dict[str, Any]:
    return dict(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=value_fn,
        **kwargs,
    )


def _power(key: str, value_fn, **kwargs) -> dict[str, Any]:
    return dict(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=value_fn,
        **kwargs,
    )


FAST_SENSORS: tuple[VoltronicFastSensorDescription, ...] = (
    VoltronicFastSensorDescription(**_voltage("grid_voltage", lambda d: d.status.grid_voltage)),
    VoltronicFastSensorDescription(**_frequency("grid_frequency", lambda d: d.status.grid_frequency)),
    VoltronicFastSensorDescription(**_voltage("ac_output_voltage", lambda d: d.status.ac_output_voltage)),
    VoltronicFastSensorDescription(
        **_frequency("ac_output_frequency", lambda d: d.status.ac_output_frequency)
    ),
    VoltronicFastSensorDescription(
        key="ac_output_apparent_power",
        translation_key="ac_output_apparent_power",
        device_class=SensorDeviceClass.APPARENT_POWER,
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.status.ac_output_apparent_power,
    ),
    VoltronicFastSensorDescription(
        **_power("ac_output_active_power", lambda d: d.status.ac_output_active_power)
    ),
    VoltronicFastSensorDescription(
        key="load_percent",
        translation_key="load_percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.status.load_percent,
    ),
    VoltronicFastSensorDescription(
        **_voltage(
            "bus_voltage",
            lambda d: d.status.bus_voltage,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        )
    ),
    VoltronicFastSensorDescription(**_voltage("battery_voltage", lambda d: d.status.battery_voltage)),
    VoltronicFastSensorDescription(
        **_current("battery_charge_current", lambda d: d.status.battery_charge_current)
    ),
    VoltronicFastSensorDescription(
        **_current("battery_discharge_current", lambda d: d.status.battery_discharge_current)
    ),
    VoltronicFastSensorDescription(**_power("battery_power", lambda d: d.status.battery_power)),
    VoltronicFastSensorDescription(
        # Voltage-based estimate from the inverter, NOT a state of charge: no
        # battery device class, disabled by default.
        key="battery_capacity_estimate",
        translation_key="battery_capacity_estimate",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.status.battery_capacity_estimate,
    ),
    VoltronicFastSensorDescription(
        key="heatsink_temperature",
        translation_key="heatsink_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.status.heatsink_temperature,
    ),
    VoltronicFastSensorDescription(**_current("pv_input_current", lambda d: d.status.pv_input_current)),
    VoltronicFastSensorDescription(**_voltage("pv_input_voltage", lambda d: d.status.pv_input_voltage)),
    VoltronicFastSensorDescription(
        **_power("pv_charging_power", lambda d: d.status.pv_charging_power)
    ),
    VoltronicFastSensorDescription(
        **_voltage(
            "scc_battery_voltage",
            lambda d: d.status.scc_battery_voltage,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        )
    ),
    VoltronicFastSensorDescription(
        key="device_mode",
        translation_key="device_mode",
        device_class=SensorDeviceClass.ENUM,
        options=list(DEVICE_MODES.values()),
        value_fn=lambda d: d.mode,
    ),
)


def _setting_enum(
    key: str,
    mapping: Mapping[Any, str],
    code_fn: Callable[[SlowData], Any],
    enabled: bool = True,
) -> VoltronicSlowSensorDescription:
    return VoltronicSlowSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.ENUM,
        options=list(mapping.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=enabled,
        value_fn=lambda d: mapping.get(code_fn(d)),
        code_fn=code_fn,
    )


def _diag(kwargs: dict[str, Any], enabled: bool = True) -> dict[str, Any]:
    kwargs.pop("state_class", None)  # settings/ratings are not measurements
    return {
        **kwargs,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "entity_registry_enabled_default": enabled,
    }


SLOW_SENSORS: tuple[VoltronicSlowSensorDescription, ...] = (
    # Ratings
    VoltronicSlowSensorDescription(
        **_diag(_voltage("grid_rating_voltage", lambda d: d.rated.grid_rating_voltage), False)
    ),
    VoltronicSlowSensorDescription(
        **_diag(_current("grid_rating_current", lambda d: d.rated.grid_rating_current), False)
    ),
    VoltronicSlowSensorDescription(
        **_diag(_voltage("ac_output_rating_voltage", lambda d: d.rated.ac_output_rating_voltage))
    ),
    VoltronicSlowSensorDescription(
        **_diag(_frequency("ac_output_rating_frequency", lambda d: d.rated.ac_output_rating_frequency))
    ),
    VoltronicSlowSensorDescription(
        **_diag(_current("ac_output_rating_current", lambda d: d.rated.ac_output_rating_current), False)
    ),
    VoltronicSlowSensorDescription(
        key="ac_output_rating_apparent_power",
        translation_key="ac_output_rating_apparent_power",
        device_class=SensorDeviceClass.APPARENT_POWER,
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.rated.ac_output_rating_apparent_power,
    ),
    VoltronicSlowSensorDescription(
        **_diag(_power("ac_output_rating_active_power", lambda d: d.rated.ac_output_rating_active_power))
    ),
    VoltronicSlowSensorDescription(
        **_diag(_voltage("battery_rating_voltage", lambda d: d.rated.battery_rating_voltage))
    ),
    # Battery thresholds
    VoltronicSlowSensorDescription(
        **_diag(_voltage("battery_recharge_voltage", lambda d: d.rated.battery_recharge_voltage))
    ),
    VoltronicSlowSensorDescription(
        **_diag(_voltage("battery_redischarge_voltage", lambda d: d.rated.battery_redischarge_voltage))
    ),
    VoltronicSlowSensorDescription(
        **_diag(_voltage("battery_under_voltage", lambda d: d.rated.battery_under_voltage))
    ),
    VoltronicSlowSensorDescription(
        **_diag(_voltage("battery_bulk_voltage", lambda d: d.rated.battery_bulk_voltage))
    ),
    VoltronicSlowSensorDescription(
        **_diag(_voltage("battery_float_voltage", lambda d: d.rated.battery_float_voltage))
    ),
    # Charge currents
    VoltronicSlowSensorDescription(
        **_diag(_current("max_charging_current", lambda d: d.rated.max_charging_current))
    ),
    VoltronicSlowSensorDescription(
        **_diag(_current("max_ac_charging_current", lambda d: d.rated.max_ac_charging_current))
    ),
    # Enumerated settings
    _setting_enum("output_source_priority", OUTPUT_SOURCE_PRIORITIES, lambda d: d.rated.output_source_priority),
    _setting_enum("charger_source_priority", CHARGER_SOURCE_PRIORITIES, lambda d: d.rated.charger_source_priority),
    _setting_enum("battery_type", BATTERY_TYPES, lambda d: d.rated.battery_type),
    _setting_enum("input_voltage_range", INPUT_VOLTAGE_RANGES, lambda d: d.rated.input_voltage_range),
    _setting_enum("machine_type", MACHINE_TYPES, lambda d: d.rated.machine_type, enabled=False),
    _setting_enum("topology", TOPOLOGIES, lambda d: d.rated.topology, enabled=False),
    _setting_enum("output_mode", OUTPUT_MODES, lambda d: d.rated.output_mode, enabled=False),
)

IDENTITY_SENSORS: tuple[VoltronicIdentitySensorDescription, ...] = (
    VoltronicIdentitySensorDescription(
        key="serial_number",
        translation_key="serial_number",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda i: i.serial_number,
    ),
    VoltronicIdentitySensorDescription(
        key="firmware_version",
        translation_key="firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda i: i.firmware_version,
    ),
    VoltronicIdentitySensorDescription(
        key="firmware_version_2",
        translation_key="firmware_version_2",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda i: i.firmware_version_2,
    ),
    VoltronicIdentitySensorDescription(
        key="protocol_id",
        translation_key="protocol_id",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda i: i.protocol_id,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VoltronicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    data = entry.runtime_data
    entities: list[SensorEntity] = [VoltronicFastSensor(data.fast, d) for d in FAST_SENSORS]
    entities += [VoltronicSlowSensor(data.slow, d) for d in SLOW_SENSORS]
    entities += [VoltronicIdentitySensor(data.slow, d) for d in IDENTITY_SENSORS]
    async_add_entities(entities)


class VoltronicFastSensor(VoltronicEntity, SensorEntity):
    entity_description: VoltronicFastSensorDescription

    @property
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.coordinator.data)


class VoltronicSlowSensor(VoltronicEntity, SensorEntity):
    entity_description: VoltronicSlowSensorDescription

    @property
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.code_fn is None:
            return None
        return {"code": self.entity_description.code_fn(self.coordinator.data)}


class VoltronicIdentitySensor(VoltronicEntity, SensorEntity):
    """Static values read at start-up; availability follows the slow coordinator."""

    entity_description: VoltronicIdentitySensorDescription

    @property
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.coordinator.identity)
