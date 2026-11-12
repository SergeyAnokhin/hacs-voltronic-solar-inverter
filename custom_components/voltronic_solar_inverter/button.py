"""Button that sets the inverter clock to Home Assistant's local time (^S???DAT, experimental).

The schedules P46-P49 follow the inverter clock, which runs about 10 minutes slow on the
test unit. The command comes from the manufacturer's service tool and is not verified on
this unit yet (docs/settings-map.md). The result shows in the clock offset sensor.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import VoltronicConfigEntry
from .entity import VoltronicControlEntity
from .protocol import commands

PARALLEL_UPDATES = 1

SET_CLOCK = ButtonEntityDescription(
    key="button_set_clock",
    translation_key="set_clock",
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VoltronicConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    data = entry.runtime_data
    if data.identity.h_protocol is not None:  # the clock is read through HGEN
        async_add_entities([VoltronicSetClockButton(data.slow, SET_CLOCK)])


class VoltronicSetClockButton(VoltronicControlEntity, ButtonEntity):
    async def async_press(self) -> None:
        await self.async_send(lambda: commands.set_clock(dt_util.now()))
