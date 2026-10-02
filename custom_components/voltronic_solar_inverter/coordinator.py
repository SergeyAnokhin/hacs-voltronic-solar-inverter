"""Polling coordinators: fast (live status) and slow (settings, flags, warnings)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, LOGGER
from .protocol import (
    DeviceIdentity,
    GeneralStatus,
    InverterClient,
    InverterError,
    RatedInfo,
    WarningStatus,
)


@dataclass(frozen=True, slots=True)
class FastData:
    """QPIGS + QMOD."""

    status: GeneralStatus
    mode: str


@dataclass(frozen=True, slots=True)
class SlowData:
    """QPIRI + QFLAG + QPIWS."""

    rated: RatedInfo
    flags: dict[str, bool]
    warnings: WarningStatus


@dataclass(slots=True)
class VoltronicRuntimeData:
    """Stored in ConfigEntry.runtime_data."""

    client: InverterClient
    identity: DeviceIdentity
    fast: VoltronicFastCoordinator
    slow: VoltronicSlowCoordinator
    controls_enabled: bool


type VoltronicConfigEntry = ConfigEntry[VoltronicRuntimeData]


class _VoltronicCoordinator[DataT](DataUpdateCoordinator[DataT]):
    """Shared plumbing: one client, translated UpdateFailed on any inverter error."""

    config_entry: VoltronicConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: VoltronicConfigEntry,
        client: InverterClient,
        identity: DeviceIdentity,
        name: str,
        interval: int,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {name}",
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.identity = identity

    async def _async_update_data(self) -> DataT:
        try:
            return await self._fetch()
        except InverterError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err

    async def _fetch(self) -> DataT:
        raise NotImplementedError


class VoltronicFastCoordinator(_VoltronicCoordinator[FastData]):
    """Live values: QPIGS and QMOD."""

    async def _fetch(self) -> FastData:
        status = await self.client.read_general_status()
        mode = await self.client.read_mode()
        return FastData(status=status, mode=mode)


class VoltronicSlowCoordinator(_VoltronicCoordinator[SlowData]):
    """Ratings/settings, option flags and warning bits: QPIRI, QFLAG, QPIWS."""

    async def _fetch(self) -> SlowData:
        rated = await self.client.read_rated_info()
        flags = await self.client.read_flags()
        warnings = await self.client.read_warnings()
        return SlowData(rated=rated, flags=flags, warnings=warnings)
