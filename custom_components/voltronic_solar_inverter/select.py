"""Selects for output (POP), charger (PCP) and solar supply (PVENGUSE, P43) priority,
and the battery charge / discharge override (PBATCD).

Only owner-verified priority codes are offered (see *_VERIFIED in
protocol/parsers.py). PBATCD cannot be read back: its select shows the last
mode the inverter ACKed (restored after a restart).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import VoltronicConfigEntry
from .coordinator import SlowData
from .entity import VoltronicControlEntity, is_supported
from .protocol import WriteCommand, commands
from .protocol.h_parsers import SOLAR_SUPPLY_PRIORITIES, SOLAR_SUPPLY_PRIORITIES_VERIFIED
from .protocol.parsers import (
    CHARGER_SOURCE_PRIORITIES,
    CHARGER_SOURCE_PRIORITIES_VERIFIED,
    OUTPUT_SOURCE_PRIORITIES,
    OUTPUT_SOURCE_PRIORITIES_VERIFIED,
)

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class VoltronicSelectDescription(SelectEntityDescription):
    codes: dict[int, str]  # verified code -> option
    code_fn: Callable[[SlowData], int]
    command_fn: Callable[[int], WriteCommand]
    requires: str | None = None  # SlowData field that must have been read


SELECTS = (
    VoltronicSelectDescription(
        key="select_output_source_priority",
        translation_key="output_source_priority",
        entity_category=EntityCategory.CONFIG,
        codes={c: OUTPUT_SOURCE_PRIORITIES[c] for c in sorted(OUTPUT_SOURCE_PRIORITIES_VERIFIED)},
        code_fn=lambda d: d.rated.output_source_priority,
        command_fn=commands.set_output_source_priority,
    ),
    VoltronicSelectDescription(
        key="select_charger_source_priority",
        translation_key="charger_source_priority",
        entity_category=EntityCategory.CONFIG,
        codes={c: CHARGER_SOURCE_PRIORITIES[c] for c in sorted(CHARGER_SOURCE_PRIORITIES_VERIFIED)},
        code_fn=lambda d: d.rated.charger_source_priority,
        command_fn=commands.set_charger_source_priority,
    ),
    VoltronicSelectDescription(
        # P43, read from HEEP1 (H dialect), written with PVENGUSE<NN>
        key="select_solar_supply_priority",
        translation_key="solar_supply_priority",
        entity_category=EntityCategory.CONFIG,
        codes={c: SOLAR_SUPPLY_PRIORITIES[c] for c in sorted(SOLAR_SUPPLY_PRIORITIES_VERIFIED)},
        code_fn=lambda d: d.heep1.solar_supply_priority,
        command_fn=commands.set_solar_supply_priority,
        requires="heep1",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VoltronicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    data = entry.runtime_data
    async_add_entities(
        VoltronicPrioritySelect(data.slow, d) for d in SELECTS if is_supported(d, data.identity)
    )
    async_add_entities([VoltronicBatteryControlSelect(data.slow, BATTERY_CONTROL)])


BATTERY_CONTROL = SelectEntityDescription(
    key="select_battery_control",
    translation_key="battery_control",
    entity_category=EntityCategory.CONFIG,
    options=list(commands.BATTERY_CONTROL_MODES),
)


class VoltronicPrioritySelect(VoltronicControlEntity, SelectEntity):
    entity_description: VoltronicSelectDescription

    def __init__(self, coordinator, description: VoltronicSelectDescription) -> None:
        super().__init__(coordinator, description)
        self._attr_options = list(description.codes.values())

    @property
    def current_option(self) -> str | None:
        """None when the inverter currently uses a code that is not offered."""
        code = self.entity_description.code_fn(self.coordinator.data)
        return self.entity_description.codes.get(code)

    async def async_select_option(self, option: str) -> None:
        code = next(c for c, o in self.entity_description.codes.items() if o == option)
        await self.async_send(lambda: self.entity_description.command_fn(code))


class VoltronicBatteryControlSelect(VoltronicControlEntity, SelectEntity, RestoreEntity):
    """PBATCD override; the state is the last ACKed mode (no query reads it back)."""

    _attr_assumed_state = True
    _attr_current_option: str | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in self.options:
            self._attr_current_option = last.state

    async def async_select_option(self, option: str) -> None:
        await self.async_send(lambda: commands.set_battery_control(option))
        self._attr_current_option = option
        self.async_write_ha_state()
