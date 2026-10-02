"""Switches for QFLAG options (PE<x>/PD<x>). Only set up when controls are enabled."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import VoltronicConfigEntry
from .entity import VoltronicControlEntity
from .protocol import commands
from .protocol.parsers import FLAGS

PARALLEL_UPDATES = 1

FLAG_SWITCHES = tuple(
    SwitchEntityDescription(
        key=f"switch_{flag}",
        translation_key=flag,
        entity_category=EntityCategory.CONFIG,
    )
    for flag in FLAGS.values()
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VoltronicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    slow = entry.runtime_data.slow
    async_add_entities(VoltronicFlagSwitch(slow, d) for d in FLAG_SWITCHES)


class VoltronicFlagSwitch(VoltronicControlEntity, SwitchEntity):
    @property
    def _flag(self) -> str:
        return self.entity_description.key.removeprefix("switch_")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.flags.get(self._flag)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.async_send(lambda: commands.set_flag(self._flag, True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.async_send(lambda: commands.set_flag(self._flag, False))
