"""Selects for output (POP) and charger (PCP) source priority.

Only owner-verified codes are offered (see *_VERIFIED in protocol/parsers.py);
only set up when controls are enabled.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import VoltronicConfigEntry
from .entity import VoltronicControlEntity
from .protocol import RatedInfo, WriteCommand, commands
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
    code_fn: Callable[[RatedInfo], int]
    command_fn: Callable[[int], WriteCommand]


SELECTS = (
    VoltronicSelectDescription(
        key="select_output_source_priority",
        translation_key="output_source_priority",
        entity_category=EntityCategory.CONFIG,
        codes={c: OUTPUT_SOURCE_PRIORITIES[c] for c in sorted(OUTPUT_SOURCE_PRIORITIES_VERIFIED)},
        code_fn=lambda r: r.output_source_priority,
        command_fn=commands.set_output_source_priority,
    ),
    VoltronicSelectDescription(
        key="select_charger_source_priority",
        translation_key="charger_source_priority",
        entity_category=EntityCategory.CONFIG,
        codes={c: CHARGER_SOURCE_PRIORITIES[c] for c in sorted(CHARGER_SOURCE_PRIORITIES_VERIFIED)},
        code_fn=lambda r: r.charger_source_priority,
        command_fn=commands.set_charger_source_priority,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VoltronicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    slow = entry.runtime_data.slow
    async_add_entities(VoltronicPrioritySelect(slow, d) for d in SELECTS)


class VoltronicPrioritySelect(VoltronicControlEntity, SelectEntity):
    entity_description: VoltronicSelectDescription

    def __init__(self, coordinator, description: VoltronicSelectDescription) -> None:
        super().__init__(coordinator, description)
        self._attr_options = list(description.codes.values())

    @property
    def current_option(self) -> str | None:
        """None when the inverter currently uses a code that is not offered."""
        code = self.entity_description.code_fn(self.coordinator.data.rated)
        return self.entity_description.codes.get(code)

    async def async_select_option(self, option: str) -> None:
        code = next(c for c, o in self.entity_description.codes.items() if o == option)
        await self.async_send(lambda: self.entity_description.command_fn(code))
