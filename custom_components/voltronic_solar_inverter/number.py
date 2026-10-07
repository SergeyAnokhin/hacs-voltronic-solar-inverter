"""Numbers for charge currents and battery voltage thresholds, plus four
HA-only settings: the inverter's total own consumption (battery mode / line
mode / standby / solar charging).

Currents use the lists the inverter reports (QMCHGCR / QMUCHGCR); voltage
thresholds exist only for 24 V systems, whose ranges are documented. Float
voltage (PBFT) is not implemented: its range is undocumented (see
docs/integration.md).
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
    RestoreNumber,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import VoltronicConfigEntry, VoltronicFastCoordinator
from .entity import VoltronicControlEntity, VoltronicEntity, remove_entities
from .power_balance import BATTERY, LINE, SOLAR_CHARGING, STANDBY
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
    # 0.4.5-0.4.8 stored only the part the inverter's sensors miss, under other keys;
    # drop them so the new settings start from the measured totals.
    remove_entities(hass, identity, "number", REMOVED_NUMBER_KEYS)
    async_add_entities(
        VoltronicOwnConsumptionNumber(data.fast, d, setting)
        for d, setting in OWN_CONSUMPTION_NUMBERS
    )


REMOVED_NUMBER_KEYS = (
    "self_consumption_battery_mode",
    "self_consumption_line_mode",
    "self_consumption_output_off",
)


def _own_consumption_description(key: str) -> NumberEntityDescription:
    return NumberEntityDescription(
        key=key,
        translation_key=key,
        entity_category=EntityCategory.CONFIG,
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_min_value=0,
        native_max_value=500,
        native_step=1,
        mode=NumberMode.BOX,
    )


# Stored in HA only (never sent to the inverter): what the inverter uses itself
# with no load, per operating state.
OWN_CONSUMPTION_NUMBERS: tuple[tuple[NumberEntityDescription, str], ...] = (
    (_own_consumption_description("own_consumption_battery_mode"), BATTERY),
    (_own_consumption_description("own_consumption_line_mode"), LINE),
    (_own_consumption_description("own_consumption_standby"), STANDBY),
    (_own_consumption_description("own_consumption_solar_charging"), SOLAR_CHARGING),
)


class VoltronicNumber(VoltronicControlEntity, NumberEntity):
    entity_description: VoltronicNumberDescription

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator.data.rated)

    async def async_set_native_value(self, value: float) -> None:
        await self.async_send(lambda: self.entity_description.command_fn(value))


class VoltronicOwnConsumptionNumber(VoltronicEntity[VoltronicFastCoordinator], RestoreNumber):
    """User's estimate of the inverter's own consumption; restored after a restart."""

    def __init__(
        self,
        coordinator: VoltronicFastCoordinator,
        description: NumberEntityDescription,
        setting: str,
    ) -> None:
        super().__init__(coordinator, description)
        self._setting = setting

    @property
    def _values(self) -> dict[str, float]:
        return self.coordinator.config_entry.runtime_data.own_consumption

    @property
    def available(self) -> bool:
        return True  # a stored setting, not a reading

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._values[self._setting] = float(last.native_value)

    @property
    def native_value(self) -> float:
        return self._values[self._setting]

    async def async_set_native_value(self, value: float) -> None:
        self._values[self._setting] = value
        self.async_write_ha_state()
