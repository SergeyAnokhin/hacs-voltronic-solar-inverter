"""Sensors: live values (fast), ratings/settings (slow) and device identity."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
import time
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
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_UPDATE_GROUP,
    CONTROL_DUPLICATE_KEYS,
    DISABLED_KEYS,
    HIDDEN_KEYS,
    MEDIAN_WINDOW,
    SMOOTHING_ABSOLUTE_THRESHOLD_W,
    SMOOTHING_HEARTBEAT,
    SMOOTHING_RELATIVE_THRESHOLD,
    SMOOTHING_WINDOW,
    UPDATE_GROUP_SLOW,
)
from .coordinator import (
    FastData,
    SlowData,
    VoltronicConfigEntry,
    VoltronicFastCoordinator,
    VoltronicRuntimeData,
)
from .entity import VoltronicEntity, is_supported, remove_entities
from .protocol.h_parsers import SOLAR_SUPPLY_PRIORITIES, Schedule
from .smoothing import DailyMax, SmoothedValue
from .protocol.parsers import (
    BATTERY_TYPES,
    CHARGE_STAGES,
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
    requires: str | None = None  # FastData field that must have been read
    precision: int | None = None  # decimals of the state itself (rounded before it is recorded)
    smoothing_window: float = SMOOTHING_WINDOW  # smoothed sensors only
    smoothing_statistic: str = "mean"  # "mean", "median" or "max"
    smoothing_daily: bool = False  # statistic over the current local day instead of a window


@dataclass(frozen=True, kw_only=True)
class VoltronicSlowSensorDescription(SensorEntityDescription):
    value_fn: Callable[[SlowData], StateType | datetime]
    code_fn: Callable[[SlowData], Any] | None = None  # raw code shown as attribute for enums
    requires: str | None = None  # SlowData field that must have been read
    precision: int | None = None  # decimals of the state itself (rounded before it is recorded)


def _round(value: StateType | datetime, precision: int | None) -> StateType | datetime:
    """Round numbers to ``precision`` decimals (int for 0) so the recorder never sees noise digits."""
    if precision is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    rounded = round(value, precision)
    return int(rounded) if precision == 0 else rounded


@dataclass(frozen=True, kw_only=True)
class VoltronicIdentitySensorDescription(SensorEntityDescription):
    value_fn: Callable[[DeviceIdentity], StateType]


def _voltage(key: str, value_fn, precision: int = 1, **kwargs) -> dict[str, Any]:
    """Battery/PV voltages keep one decimal; mains voltages (~230 V) pass precision=0."""
    return dict(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        precision=precision,
        suggested_display_precision=precision,
        value_fn=value_fn,
        **kwargs,
    )


def _current(key: str, value_fn, **kwargs) -> dict[str, Any]:
    """Currents are whole amperes."""
    return dict(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        precision=0,
        suggested_display_precision=0,
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
    VoltronicFastSensorDescription(**_voltage("grid_voltage", lambda d: d.status.grid_voltage, 0)),
    VoltronicFastSensorDescription(**_frequency("grid_frequency", lambda d: d.status.grid_frequency)),
    VoltronicFastSensorDescription(
        **_voltage("ac_output_voltage", lambda d: d.status.ac_output_voltage, 0)
    ),
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
        # Every sample; exclude it from the recorder if the interval is short
        **_power("ac_output_active_power_raw", lambda d: d.status.ac_output_active_power)
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
        # Every sample; exclude it from the recorder if the interval is short
        **_power("pv_power_raw", lambda d: d.status.pv_charging_power)
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
        # HGRID[6]; sign convention not verified yet. Every sample, like the other *_raw.
        **_power("grid_power_raw", lambda d: d.grid_power, requires="grid_power")
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
    requires: str | None = None,
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
        requires=requires,
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
        **_diag(_voltage("grid_rating_voltage", lambda d: d.rated.grid_rating_voltage, 0), False)
    ),
    VoltronicSlowSensorDescription(
        **_diag(_current("grid_rating_current", lambda d: d.rated.grid_rating_current), False)
    ),
    VoltronicSlowSensorDescription(
        **_diag(_voltage("ac_output_rating_voltage", lambda d: d.rated.ac_output_rating_voltage, 0))
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

def _hour(schedule_fn: Callable[[SlowData], Schedule], start: bool) -> Callable[[SlowData], str]:
    def value(d: SlowData) -> str:
        schedule = schedule_fn(d)
        return f"{schedule.start_hour if start else schedule.end_hour:02d}:00"

    return value


def _pv_energy(key: str, value_fn) -> VoltronicSlowSensorDescription:
    return VoltronicSlowSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=value_fn,
        requires="generation",
    )


def _temperature(key: str, value_fn) -> VoltronicSlowSensorDescription:
    return VoltronicSlowSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=value_fn,
        requires="temperatures",
    )


def _diag_voltage(
    key: str, value_fn, requires: str, enabled: bool = True
) -> VoltronicSlowSensorDescription:
    return VoltronicSlowSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=enabled,
        precision=1,
        suggested_display_precision=1,
        value_fn=value_fn,
        requires=requires,
    )


def _extra(key: str, value_fn, requires: str, enabled: bool = True, **kwargs):
    return VoltronicSlowSensorDescription(
        key=key,
        translation_key=key,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=enabled,
        value_fn=value_fn,
        requires=requires,
        **kwargs,
    )


_MINUTES = {"device_class": SensorDeviceClass.DURATION, "native_unit_of_measurement": UnitOfTime.MINUTES}
_PERCENT = {"native_unit_of_measurement": PERCENTAGE}

# Optional sources: QBEQI, Q1 and the H dialect (HGEN, HEEP1, HEEP2, HTEMP).
EXTRA_SLOW_SENSORS: tuple[VoltronicSlowSensorDescription, ...] = (
    # PV energy counters (HGEN); same values as the vendor app
    _pv_energy("pv_energy_today", lambda d: d.generation.pv_energy_today),
    _pv_energy("pv_energy_month", lambda d: d.generation.pv_energy_month),
    _pv_energy("pv_energy_year", lambda d: d.generation.pv_energy_year),
    _pv_energy("pv_energy_total", lambda d: d.generation.pv_energy_total),
    # Inverter clock (HGEN); the schedules follow this clock
    _extra(
        "inverter_clock",
        lambda d: d.generation.clock.replace(tzinfo=dt_util.get_default_time_zone()),
        "generation",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    _extra(
        "inverter_clock_offset",
        lambda d: d.clock_offset,
        "generation",
        state_class=SensorStateClass.MEASUREMENT,
        **_MINUTES,
    ),
    # Schedules (HEEP2): P48/P49 AC output, P46/P47 AC charger
    VoltronicSlowSensorDescription(
        key="ac_output_on_time",
        translation_key="ac_output_on_time",
        value_fn=_hour(lambda d: d.heep2.ac_output_schedule, True),
        requires="heep2",
    ),
    VoltronicSlowSensorDescription(
        key="ac_output_off_time",
        translation_key="ac_output_off_time",
        value_fn=_hour(lambda d: d.heep2.ac_output_schedule, False),
        requires="heep2",
    ),
    VoltronicSlowSensorDescription(
        key="ac_charger_start_time",
        translation_key="ac_charger_start_time",
        value_fn=_hour(lambda d: d.heep2.ac_charger_schedule, True),
        requires="heep2",
    ),
    VoltronicSlowSensorDescription(
        key="ac_charger_stop_time",
        translation_key="ac_charger_stop_time",
        value_fn=_hour(lambda d: d.heep2.ac_charger_schedule, False),
        requires="heep2",
    ),
    # P43 solar supply priority (HEEP1)
    _setting_enum(
        "solar_supply_priority",
        SOLAR_SUPPLY_PRIORITIES,
        lambda d: d.heep1.solar_supply_priority,
        requires="heep1",
    ),
    # Charge stage (Q1[17]): idle/bulk verified, absorb/float generic
    VoltronicSlowSensorDescription(
        key="charge_stage",
        translation_key="charge_stage",
        device_class=SensorDeviceClass.ENUM,
        options=list(CHARGE_STAGES.values()),
        value_fn=lambda d: d.charge_stage,
        requires="has_q1",
    ),
    # Temperatures and fans (HTEMP); boost temperature = the heat-sink sensor
    _temperature("inverter_temperature", lambda d: d.temperatures.inverter),
    _temperature("transformer_temperature", lambda d: d.temperatures.transformer),
    _temperature("pv_temperature", lambda d: d.temperatures.pv),
    _extra(
        "fan_1_speed",
        lambda d: d.temperatures.fan_1_speed,
        "temperatures",
        state_class=SensorStateClass.MEASUREMENT,
        **_PERCENT,
    ),
    _extra(
        "fan_2_speed",
        lambda d: d.temperatures.fan_2_speed,
        "temperatures",
        state_class=SensorStateClass.MEASUREMENT,
        **_PERCENT,
    ),
    # Battery low-alarm voltage (HEEP2[1], P24)
    _diag_voltage("battery_low_alarm_voltage", lambda d: d.heep2.battery_low_alarm_voltage, "heep2"),
    # Equalization (QBEQI), read-only
    _diag_voltage("equalization_voltage", lambda d: d.equalization.voltage, "equalization"),
    _extra("equalization_time", lambda d: d.equalization.time, "equalization", **_MINUTES),
    _extra("equalization_timeout", lambda d: d.equalization.timeout, "equalization", **_MINUTES),
    _extra(
        "equalization_interval",
        lambda d: d.equalization.interval,
        "equalization",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
    ),
    # Dual (second) output (HEEP2): off by default
    _diag_voltage(
        "dual_output_cutoff_voltage", lambda d: d.heep2.dual_output_cutoff_voltage, "heep2", False
    ),
    _diag_voltage(
        "dual_output_recover_voltage", lambda d: d.heep2.dual_output_recover_voltage, "heep2", False
    ),
    _extra(
        "dual_output_recover_delay",
        lambda d: d.heep2.dual_output_recover_delay,
        "heep2",
        False,
        **_MINUTES,
    ),
    # BMS SOC thresholds (HEEP1): no BMS link on the owner's unit -> off by default
    _extra("bms_shutdown_soc", lambda d: d.heep1.bms_shutdown_soc, "heep1", False, **_PERCENT),
    _extra(
        "bms_back_to_battery_soc", lambda d: d.heep1.bms_back_to_battery_soc, "heep1", False, **_PERCENT
    ),
    # Grid-tie (feed-in) current, P56 (HEEP1[17]); feed-in is off on the owner's unit
    _extra(
        "grid_tie_current",
        lambda d: d.heep1.grid_tie_current,
        "heep1",
        False,
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        precision=0,
        suggested_display_precision=0,
    ),
)

# Same source as the matching *_raw sensor, published only on significant changes.
SMOOTHED_SENSORS: tuple[VoltronicFastSensorDescription, ...] = (
    VoltronicFastSensorDescription(**_power("pv_power", lambda d: d.status.pv_charging_power)),
    VoltronicFastSensorDescription(
        **_power("grid_power", lambda d: d.grid_power, requires="grid_power")
    ),
    VoltronicFastSensorDescription(
        **_power("ac_output_active_power", lambda d: d.status.ac_output_active_power)
    ),
    # Median / maximum of the last 10 minutes and the median of today (from local midnight):
    # how the PV power has really been running lately.
    VoltronicFastSensorDescription(
        **_power(
            "pv_power_median_10min",
            lambda d: d.status.pv_charging_power,
            smoothing_window=MEDIAN_WINDOW,
            smoothing_statistic="median",
        )
    ),
    VoltronicFastSensorDescription(
        **_power(
            "pv_power_max_10min",
            lambda d: d.status.pv_charging_power,
            smoothing_window=MEDIAN_WINDOW,
            smoothing_statistic="max",
        )
    ),
    VoltronicFastSensorDescription(
        **_power(
            "pv_power_median_today",
            lambda d: d.status.pv_charging_power,
            smoothing_window=float("inf"),
            smoothing_statistic="median",
            smoothing_daily=True,
        )
    ),
)

# Highest PV power since midnight (HA local time).
DAILY_MAX_SENSORS: tuple[VoltronicFastSensorDescription, ...] = (
    VoltronicFastSensorDescription(
        **_power("pv_power_max_today", lambda d: d.status.pv_charging_power)
    ),
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
        key="firmware_date",
        translation_key="firmware_date",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda i: i.firmware_date,
    ),
    VoltronicIdentitySensorDescription(
        key="protocol_id",
        translation_key="protocol_id",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda i: i.protocol_id,
    ),
)


def _with_defaults[DescriptionT: SensorEntityDescription](
    descriptions: tuple[DescriptionT, ...],
) -> tuple[DescriptionT, ...]:
    """Hide static values (HIDDEN_KEYS) and disable DISABLED_KEYS by default."""
    result = []
    for description in descriptions:
        if description.key in HIDDEN_KEYS:
            description = replace(description, entity_registry_visible_default=False)
        if description.key in DISABLED_KEYS:
            description = replace(description, entity_registry_enabled_default=False)
        result.append(description)
    return tuple(result)


SLOW_SENSORS = _with_defaults(SLOW_SENSORS)
EXTRA_SLOW_SENSORS = _with_defaults(EXTRA_SLOW_SENSORS)
IDENTITY_SENSORS = _with_defaults(IDENTITY_SENSORS)


def _duplicates_control(key: str, data: VoltronicRuntimeData) -> bool:
    """True if a control entity (select/number) already shows and sets this value."""
    if key not in CONTROL_DUPLICATE_KEYS:
        return False
    identity = data.identity
    if key in ("output_source_priority", "charger_source_priority"):
        return True
    if key == "solar_supply_priority":
        return identity.h_protocol is not None
    if key == "max_charging_current":
        return bool(identity.charging_current_options)
    if key == "max_ac_charging_current":
        return bool(identity.utility_charging_current_options)
    return data.slow.data.rated.battery_rating_voltage == 24.0  # the voltage numbers


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VoltronicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    data = entry.runtime_data
    identity = data.identity
    all_slow = SLOW_SENSORS + EXTRA_SLOW_SENSORS
    duplicates = {d.key for d in all_slow if _duplicates_control(d.key, data)}
    slow_descriptions = [d for d in all_slow if d.key not in duplicates and is_supported(d, identity)]
    # Sensors dropped in 0.4.0 (they repeat a control entity): clean up the old registry entries.
    remove_entities(hass, identity, "sensor", duplicates)
    entities: list[SensorEntity] = [
        VoltronicFastSensor(data.fast, d) for d in FAST_SENSORS if is_supported(d, identity)
    ]
    entities += [
        VoltronicSmoothedSensor(data.fast, d) for d in SMOOTHED_SENSORS if is_supported(d, identity)
    ]
    entities += [VoltronicDailyMaxSensor(data.fast, d) for d in DAILY_MAX_SENSORS]
    entities += [VoltronicSlowSensor(data.slow, d) for d in slow_descriptions]
    entities += [
        VoltronicIdentitySensor(data.slow, d)
        for d in IDENTITY_SENSORS
        if d.value_fn(identity) is not None
    ]
    async_add_entities(entities)


class VoltronicFastSensor(VoltronicEntity, SensorEntity):
    entity_description: VoltronicFastSensorDescription

    @property
    def native_value(self) -> StateType:
        description = self.entity_description
        return _round(description.value_fn(self.coordinator.data), description.precision)


class VoltronicSmoothedSensor(VoltronicEntity, SensorEntity):
    """Moving average (or median) that writes a new state only on a significant change.

    Skipping async_write_ha_state() for insignificant changes is what keeps the
    recorder database small; availability changes are always written.
    """

    entity_description: VoltronicFastSensorDescription

    def __init__(
        self, coordinator: VoltronicFastCoordinator, description: VoltronicFastSensorDescription
    ) -> None:
        super().__init__(coordinator, description)
        self._smoother = SmoothedValue(
            window=description.smoothing_window,
            statistic=description.smoothing_statistic,
            relative_threshold=SMOOTHING_RELATIVE_THRESHOLD,
            absolute_threshold=SMOOTHING_ABSOLUTE_THRESHOLD_W,
            heartbeat=SMOOTHING_HEARTBEAT,
        )
        if coordinator.data is not None:
            self._smoother.add(time.monotonic(), description.value_fn(coordinator.data), self._day())
        self._written_available = coordinator.last_update_success  # state written on add

    def _day(self):
        return dt_util.now().date() if self.entity_description.smoothing_daily else None

    @property
    def native_value(self) -> StateType:
        return self._smoother.value

    @callback
    def _handle_coordinator_update(self) -> None:
        changed = False
        if self.coordinator.last_update_success:
            changed = self._smoother.add(
                time.monotonic(),
                self.entity_description.value_fn(self.coordinator.data),
                self._day(),
            )
        if changed or self.available != self._written_available:
            self._written_available = self.available
            self.async_write_ha_state()


class VoltronicDailyMaxSensor(VoltronicEntity, RestoreEntity, SensorEntity):
    """Highest value since local midnight; restored after a restart on the same day.

    Writes a state only when the maximum rises (or the day changes), so it adds
    next to nothing to the recorder.
    """

    entity_description: VoltronicFastSensorDescription

    def __init__(
        self, coordinator: VoltronicFastCoordinator, description: VoltronicFastSensorDescription
    ) -> None:
        super().__init__(coordinator, description)
        self._max = DailyMax()
        self._written_available = coordinator.last_update_success

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        today = dt_util.now().date()
        if (
            last is not None
            and last.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
            and dt_util.as_local(last.last_updated).date() == today
        ):
            try:
                self._max.restore(today, float(last.state))
            except ValueError:
                pass
        if self.coordinator.data is not None:
            self._max.add(today, self.entity_description.value_fn(self.coordinator.data))

    @property
    def native_value(self) -> StateType:
        return self._max.value

    @callback
    def _handle_coordinator_update(self) -> None:
        changed = False
        if self.coordinator.last_update_success:
            changed = self._max.add(
                dt_util.now().date(), self.entity_description.value_fn(self.coordinator.data)
            )
        if changed or self.available != self._written_available:
            self._written_available = self.available
            self.async_write_ha_state()


class VoltronicSlowSensor(VoltronicEntity, SensorEntity):
    entity_description: VoltronicSlowSensorDescription

    @property
    def native_value(self) -> StateType | datetime:
        description = self.entity_description
        return _round(description.value_fn(self.coordinator.data), description.precision)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attributes: dict[str, Any] = {ATTR_UPDATE_GROUP: UPDATE_GROUP_SLOW}
        if self.entity_description.code_fn is not None:
            attributes["code"] = self.entity_description.code_fn(self.coordinator.data)
        return attributes


class VoltronicIdentitySensor(VoltronicEntity, SensorEntity):
    """Static values read at start-up; availability follows the slow coordinator."""

    entity_description: VoltronicIdentitySensorDescription

    @property
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.coordinator.identity)
