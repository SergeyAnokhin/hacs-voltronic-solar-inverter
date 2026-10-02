"""Numbers for charge currents and battery voltage thresholds.

Only set up when controls are enabled. Currents use the lists the inverter
reports (QMCHGCR / QMUCHGCR); voltage thresholds exist only for 24 V systems,
whose ranges are documented. Float voltage (PBFT) is not implemented: its
range is undocumented (see docs/integration.md).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import gcd

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfElectricCurrent, UnitOfElectricPotential
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import VoltronicConfigEntry
from .entity import VoltronicControlEntity
from .protocol import InvalidCommandError, RatedInfo, WriteCommand, commands

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class VoltronicNumberDescription(NumberEntityDescription):
    value_fn: Callable[[RatedInfo], float | None]
    command_fn: Callable[[float], WriteCommand]


def _as_int(value: float) -> int:
    if value != int(value):
        raise InvalidCommandError(f"{value} is not a whole number of amperes")
    return int(value)


def _current_description(
    key: str, options: tuple[int, ...], value_fn, builder
) -> VoltronicNumberDescription:
    step = 0
    for value in options:
        step = gcd(step, value)
    return VoltronicNumberDescription(
        key=f"number_{key}",
        translation_key=key,
        entity_category=EntityCategory.CONFIG,
        device_class=NumberDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        native_min_value=min(options),
        native_max_value=max(options),
        native_step=step or 1,
        mode=NumberMode.BOX,
        value_fn=value_fn,
        command_fn=lambda value: builder(_as_int(value), options),
    )


def _voltage_description(key: str) -> VoltronicNumberDescription:
    setting = commands.VOLTAGE_SETTINGS_24V[key]
    return VoltronicNumberDescription(
        key=f"number_{key}",
        translation_key=key,
        entity_category=EntityCategory.CONFIG,
        device_class=NumberDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        native_min_value=setting.minimum,
        native_max_value=setting.maximum,
        native_step=setting.step,
        mode=NumberMode.BOX,
        value_fn=lambda rated: getattr(rated, key),
        command_fn=lambda value: commands.set_battery_voltage(key, round(value, 1)),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VoltronicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    data = entry.runtime_data
    identity = data.identity
    descriptions: list[VoltronicNumberDescription] = []
    if identity.charging_current_options:
        descriptions.append(
            _current_description(
                "max_charging_current",
                identity.charging_current_options,
                lambda r: r.max_charging_current,
                commands.set_max_charging_current,
            )
        )
    if identity.utility_charging_current_options:
        descriptions.append(
            _current_description(
                "max_ac_charging_current",
                identity.utility_charging_current_options,
                lambda r: r.max_ac_charging_current,
                commands.set_max_utility_charging_current,
            )
        )
    if data.slow.data.rated.battery_rating_voltage == 24.0:
        descriptions += [_voltage_description(key) for key in commands.VOLTAGE_SETTINGS_24V]
    async_add_entities(VoltronicNumber(data.slow, d) for d in descriptions)


class VoltronicNumber(VoltronicControlEntity, NumberEntity):
    entity_description: VoltronicNumberDescription

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator.data.rated)

    async def async_set_native_value(self, value: float) -> None:
        await self.async_send(lambda: self.entity_description.command_fn(value))
