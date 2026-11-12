"""Switches for QFLAG options (PE<x>/PD<x>) and, experimental, the second output.

The second-output switches use the service tool's PDAULC (dual output mode, read from
HEEP2[0]) and PDAULON (second output on / off now; no query is used, so the switch shows
the last ACKed state, restored after a restart).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import STATE_OFF, STATE_ON, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

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


@dataclass(frozen=True, kw_only=True)
class VoltronicSecondOutputDescription(SwitchEntityDescription):
    requires: str | None = None  # SlowData field that must have been read


DUAL_OUTPUT_MODE = VoltronicSecondOutputDescription(
    key="switch_second_output_mode",
    translation_key="second_output_mode",
    entity_category=EntityCategory.CONFIG,
    requires="heep2",
)
SECOND_OUTPUT = VoltronicSecondOutputDescription(
    key="switch_second_output",
    translation_key="second_output",
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VoltronicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    data = entry.runtime_data
    slow = data.slow
    async_add_entities(VoltronicFlagSwitch(slow, d) for d in FLAG_SWITCHES)
    if data.identity.h_protocol is not None:
        async_add_entities(
            [
                VoltronicDualOutputModeSwitch(slow, DUAL_OUTPUT_MODE),
                VoltronicSecondOutputSwitch(slow, SECOND_OUTPUT),
            ]
        )


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


class VoltronicDualOutputModeSwitch(VoltronicControlEntity, SwitchEntity):
    """PDAULC01 / PDAULC00; the state is HEEP2[0]."""

    @property
    def is_on(self) -> bool | None:
        heep2 = self.coordinator.data.heep2
        return None if heep2 is None else heep2.dual_output_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.async_send(lambda: commands.set_dual_output_mode(True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.async_send(lambda: commands.set_dual_output_mode(False))


class VoltronicSecondOutputSwitch(VoltronicControlEntity, SwitchEntity, RestoreEntity):
    """PDAULON01 / PDAULON00; shows the last ACKed state (the real state is HSTS[2], char 4)."""

    _attr_assumed_state = True
    _attr_is_on: bool | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in (STATE_ON, STATE_OFF):
            self._attr_is_on = last.state == STATE_ON

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.async_send(lambda: commands.set_second_output(True))
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.async_send(lambda: commands.set_second_output(False))
        self._attr_is_on = False
        self.async_write_ha_state()
