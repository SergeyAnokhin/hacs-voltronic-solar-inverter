"""Numbers for charge currents, the max discharge current (PBATMAXDISC, not
readable: shows the last ACKed value) and battery voltage thresholds, plus four
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
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SlowData, VoltronicConfigEntry, VoltronicFastCoordinator
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
        raise InvalidCommandError(f"{value} is not a whole number")
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
    async_add_entities([VoltronicDischargeCurrentNumber(data.slow, MAX_DISCHARGING_CURRENT)])
    if identity.h_protocol is not None:  # these settings are read through HEEP1 / HEEP2
        async_add_entities(VoltronicScheduleNumber(data.slow, d) for d in SCHEDULE_NUMBERS)
        eeprom = list(EEPROM_INTEGER_NUMBERS)
        if data.slow.data.rated.battery_rating_voltage == 24.0:  # the voltage ranges are 24 V ones
            eeprom += EEPROM_VOLTAGE_NUMBERS
        async_add_entities(VoltronicEepromNumber(data.slow, d) for d in eeprom)
        async_add_entities(
            [VoltronicBatteryDischargeLimitNumber(data.slow, BATTERY_DISCHARGE_CURRENT_LIMIT)]
        )
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


# PBATMAXDISC: 0 = no limit, 30..150 A (values 10 and 20 are rejected by the builder).
MAX_DISCHARGING_CURRENT = NumberEntityDescription(
    key="number_max_discharging_current",
    translation_key="max_discharging_current",
    entity_category=EntityCategory.CONFIG,
    device_class=NumberDeviceClass.CURRENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
    native_min_value=0,
    native_max_value=commands.MAX_DISCHARGING_CURRENT_RANGE[1],
    native_step=10,
    mode=NumberMode.BOX,
)


@dataclass(frozen=True, kw_only=True)
class VoltronicScheduleDescription(NumberEntityDescription):
    """One hour of a schedule window: P46/P47 (AC charger) or P48/P49 (AC output)."""

    schedule: str  # key in commands.SCHEDULE_PREFIXES, also the SettingsEeprom2 field suffix
    is_start: bool
    requires: str = "heep2"


def _schedule_description(schedule: str, is_start: bool, key: str) -> VoltronicScheduleDescription:
    low, high = commands.SCHEDULE_HOURS
    return VoltronicScheduleDescription(
        key=f"number_{key}",
        translation_key=key,
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=UnitOfTime.HOURS,
        native_min_value=low,
        native_max_value=high,
        native_step=1,
        mode=NumberMode.BOX,
        schedule=schedule,
        is_start=is_start,
    )


# Experimental: ^S???ACLT / ^S???ACCT come from the manufacturer's service tool and are
# not verified on the device yet (docs/settings-map.md). Each entity sends the whole window.
SCHEDULE_NUMBERS: tuple[VoltronicScheduleDescription, ...] = (
    _schedule_description("ac_output", True, "ac_output_on_hour"),  # P48
    _schedule_description("ac_output", False, "ac_output_off_hour"),  # P49
    _schedule_description("ac_charger", True, "ac_charger_start_hour"),  # P46
    _schedule_description("ac_charger", False, "ac_charger_stop_hour"),  # P47
)


@dataclass(frozen=True, kw_only=True)
class VoltronicEepromNumberDescription(NumberEntityDescription):
    """A setting read from HEEP1 / HEEP2 and written with a service-tool setter."""

    value_fn: Callable[[SlowData], float | None]
    command_fn: Callable[[float], WriteCommand]
    requires: str  # "heep1" or "heep2"


def _eeprom_voltage(key: str, value_fn, requires: str) -> VoltronicEepromNumberDescription:
    setting = commands.HEEP_VOLTAGE_SETTINGS_24V[key]
    return VoltronicEepromNumberDescription(
        key=f"number_{key}",
        translation_key=key,
        entity_category=EntityCategory.CONFIG,
        device_class=NumberDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        native_min_value=setting.minimum,
        native_max_value=setting.maximum,
        native_step=setting.step,
        mode=NumberMode.BOX,
        value_fn=value_fn,
        command_fn=lambda value: commands.set_heep_voltage(key, round(value, 1)),
        requires=requires,
    )


def _eeprom_integer(
    key: str, value_fn, requires: str, unit: str, *, enabled: bool = True
) -> VoltronicEepromNumberDescription:
    setting = commands.INTEGER_SETTINGS[key]
    return VoltronicEepromNumberDescription(
        key=f"number_{key}",
        translation_key=key,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=enabled,
        native_unit_of_measurement=unit,
        native_min_value=setting.minimum,
        native_max_value=setting.maximum,
        native_step=setting.step,
        mode=NumberMode.BOX,
        value_fn=value_fn,
        command_fn=lambda value: commands.set_integer_setting(key, _as_int(value)),
        requires=requires,
    )


# Experimental (owner's request 2026-11-12): setters from the manufacturer's service tool,
# never sent to the unit by an agent (docs/settings-map.md). The BMS ones are disabled by
# default: this installation has no BMS link.
EEPROM_VOLTAGE_NUMBERS: tuple[VoltronicEepromNumberDescription, ...] = (
    _eeprom_voltage(  # P24
        "battery_low_alarm_voltage", lambda d: d.heep2.battery_low_alarm_voltage, "heep2"
    ),
    _eeprom_voltage(
        "second_output_cutoff_voltage", lambda d: d.heep2.dual_output_cutoff_voltage, "heep2"
    ),
    _eeprom_voltage(
        "second_output_recover_voltage", lambda d: d.heep2.dual_output_recover_voltage, "heep2"
    ),
)
EEPROM_INTEGER_NUMBERS: tuple[VoltronicEepromNumberDescription, ...] = (
    _eeprom_integer(
        "second_output_cutoff_soc", lambda d: d.heep2.dual_output_cutoff_soc, "heep2", PERCENTAGE
    ),
    _eeprom_integer(
        "second_output_recover_soc", lambda d: d.heep2.dual_output_recover_soc, "heep2", PERCENTAGE
    ),
    _eeprom_integer(
        "second_output_recover_delay",
        lambda d: d.heep2.dual_output_recover_delay,
        "heep2",
        UnitOfTime.MINUTES,
    ),
    _eeprom_integer(
        "second_output_discharge_time",
        lambda d: d.heep2.dual_output_discharge_time,
        "heep2",
        UnitOfTime.MINUTES,
    ),
    _eeprom_integer(  # P38
        "bms_lock_soc", lambda d: d.heep1.bms_shutdown_soc, "heep1", PERCENTAGE, enabled=False
    ),
    _eeprom_integer(  # P39
        "bms_back_to_ac_soc", lambda d: d.heep1.bms_back_to_ac_soc, "heep1", PERCENTAGE, enabled=False
    ),
    _eeprom_integer(  # P40
        "bms_back_to_battery_soc",
        lambda d: d.heep1.bms_back_to_battery_soc,
        "heep1",
        PERCENTAGE,
        enabled=False,
    ),
    _eeprom_integer(  # P41
        "bms_restart_soc", lambda d: d.heep1.bms_restart_soc, "heep1", PERCENTAGE, enabled=False
    ),
)


class VoltronicEepromNumber(VoltronicControlEntity, NumberEntity):
    entity_description: VoltronicEepromNumberDescription

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_set_native_value(self, value: float) -> None:
        await self.async_send(lambda: self.entity_description.command_fn(value))


# DISCC<nnn> (service tool): battery discharge current limit. The tool reads it from
# HEEP3[6] on another device type; on this unit HEEP3 is not parsed, so like PBATMAXDISC
# the entity shows the last ACKed value.
BATTERY_DISCHARGE_CURRENT_LIMIT = NumberEntityDescription(
    key="number_battery_discharge_current_limit",
    translation_key="battery_discharge_current_limit",
    entity_category=EntityCategory.CONFIG,
    device_class=NumberDeviceClass.CURRENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
    native_min_value=commands.INTEGER_SETTINGS["battery_discharge_current_limit"].minimum,
    native_max_value=commands.INTEGER_SETTINGS["battery_discharge_current_limit"].maximum,
    native_step=1,
    mode=NumberMode.BOX,
)


class VoltronicBatteryDischargeLimitNumber(VoltronicControlEntity, RestoreNumber):
    """DISCC; the value is the last ACKed one (not read back)."""

    _attr_assumed_state = True
    _attr_native_value: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None:
            self._attr_native_value = last.native_value

    async def async_set_native_value(self, value: float) -> None:
        await self.async_send(
            lambda: commands.set_integer_setting("battery_discharge_current_limit", _as_int(value))
        )
        self._attr_native_value = value
        self.async_write_ha_state()


class VoltronicScheduleNumber(VoltronicControlEntity, NumberEntity):
    """An hour of a schedule read from HEEP2; a change sends the full window."""

    entity_description: VoltronicScheduleDescription

    def _window(self):
        heep2 = self.coordinator.data.heep2
        return getattr(heep2, f"{self.entity_description.schedule}_schedule")

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data.heep2 is None:
            return None
        window = self._window()
        return window.start_hour if self.entity_description.is_start else window.end_hour

    async def async_set_native_value(self, value: float) -> None:
        def build() -> WriteCommand:
            if self.coordinator.data.heep2 is None:
                raise InvalidCommandError("the current schedule has not been read yet")
            window = self._window()
            hour = _as_int(value)
            start, end = (hour, window.end_hour) if self.entity_description.is_start else (
                window.start_hour,
                hour,
            )
            return commands.set_schedule(self.entity_description.schedule, start, end)

        await self.async_send(build)


class VoltronicNumber(VoltronicControlEntity, NumberEntity):
    entity_description: VoltronicNumberDescription

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator.data.rated)

    async def async_set_native_value(self, value: float) -> None:
        await self.async_send(lambda: self.entity_description.command_fn(value))


class VoltronicDischargeCurrentNumber(VoltronicControlEntity, RestoreNumber):
    """PBATMAXDISC; the value is the last ACKed one (no query reads it back)."""

    _attr_assumed_state = True
    _attr_native_value: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None:
            self._attr_native_value = last.native_value

    async def async_set_native_value(self, value: float) -> None:
        await self.async_send(lambda: commands.set_max_discharging_current(_as_int(value)))
        self._attr_native_value = value
        self.async_write_ha_state()


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
