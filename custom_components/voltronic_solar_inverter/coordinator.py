"""Polling coordinators: fast (live status) and slow (settings, flags, warnings)."""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, LOGGER, MAX_MISSED_UPDATES
from .power_balance import DEFAULT_OWN_CONSUMPTION
from .protocol import (
    DeviceIdentity,
    GeneralStatus,
    InverterClient,
    InverterError,
    InverterNakError,
    InverterProtocolError,
    InverterTimeoutError,
    RatedInfo,
    WarningStatus,
)
from .protocol.h_parsers import Generation, SettingsEeprom1, SettingsEeprom2, Temperatures
from .protocol.parsers import Equalization, parse_q1_charge_stage


@dataclass(frozen=True, slots=True)
class FastData:
    """QPIGS + QMOD (required), HGRID (optional, H dialect)."""

    status: GeneralStatus
    mode: str | None  # None = QMOD answered with a letter not in DEVICE_MODES
    grid_power: int | None = None


@dataclass(frozen=True, slots=True)
class SlowData:
    """QPIRI + QFLAG + QPIWS (required); the rest is optional (None = not read)."""

    rated: RatedInfo
    flags: dict[str, bool]
    warnings: WarningStatus
    fetched_at: datetime | None = None
    equalization: Equalization | None = None  # QBEQI
    charge_stage: str | None = None  # Q1[17]; None also for an unknown code
    has_q1: bool = False
    heep1: SettingsEeprom1 | None = None  # H dialect
    heep2: SettingsEeprom2 | None = None
    generation: Generation | None = None
    temperatures: Temperatures | None = None

    @property
    def clock_offset(self) -> int | None:
        """Inverter clock minus HA time, in whole minutes (positive = inverter ahead)."""
        if self.generation is None or self.fetched_at is None:
            return None
        clock = self.generation.clock.replace(tzinfo=dt_util.get_default_time_zone())
        return round((clock - self.fetched_at).total_seconds() / 60)


@dataclass(slots=True)
class VoltronicRuntimeData:
    """Stored in ConfigEntry.runtime_data."""

    client: InverterClient
    identity: DeviceIdentity
    fast: VoltronicFastCoordinator
    slow: VoltronicSlowCoordinator
    # The inverter's total own consumption in W per state, set by the user (number
    # entities), keyed by power_balance.BATTERY / LINE / STANDBY / SOLAR_CHARGING;
    # used by the calculated PV power and the daily energy balance.
    own_consumption: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_OWN_CONSUMPTION)
    )


type VoltronicConfigEntry = ConfigEntry[VoltronicRuntimeData]


class _VoltronicCoordinator[DataT](DataUpdateCoordinator[DataT]):
    """Shared plumbing: one client, translated UpdateFailed on any inverter error."""

    config_entry: VoltronicConfigEntry
    failures = 0  # consecutive failed updates; entities ride out MAX_MISSED_UPDATES

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
        self._misses: dict[str, int] = {}  # consecutive misses per optional field

    async def _async_update_data(self) -> DataT:
        try:
            data = await self._fetch()
        except InverterError as err:
            self.failures += 1
            LOGGER.debug(
                "%s update failed (%d in a row, entities %s): %s",
                self.name,
                self.failures,
                "kept" if self.failures <= MAX_MISSED_UPDATES else "unavailable",
                err,
            )
            if self.failures == MAX_MISSED_UPDATES + 1:
                # HA notifies listeners only when last_update_success flips, which
                # happened on the first failure: tell entities the grace is over.
                self.async_update_listeners()
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        if self.failures:
            LOGGER.debug("%s update recovered after %d failure(s)", self.name, self.failures)
        self.failures = 0
        return data

    async def _fetch(self) -> DataT:
        raise NotImplementedError

    @property
    def h_supported(self) -> bool:
        return self.identity.h_protocol is not None

    async def _optional[T](self, request: Awaitable[T], field: str | None = None) -> T | None:
        """Run a query whose failure must not make every entity unavailable.

        Timeouts, NAK and malformed answers give None; connection errors still
        fail the whole update. With ``field`` (a data field name), a failed read
        returns that field's previous value for up to MAX_MISSED_UPDATES cycles.
        """
        try:
            value = await request
        except (InverterTimeoutError, InverterNakError, InverterProtocolError) as err:
            if field is None:
                LOGGER.debug("Optional query failed: %s", err)
                return None
            misses = self._misses[field] = self._misses.get(field, 0) + 1
            previous = getattr(self.data, field, None)
            keep = previous is not None and misses <= MAX_MISSED_UPDATES
            LOGGER.debug(
                "Optional query for %s failed (%d in a row, %s): %s",
                field,
                misses,
                "last value kept" if keep else "entities unavailable",
                err,
            )
            return previous if keep else None
        if field is not None:
            self._misses.pop(field, None)
        return value


class VoltronicFastCoordinator(_VoltronicCoordinator[FastData]):
    """Live values: QPIGS and QMOD, plus HGRID grid power when the H dialect exists."""

    _mode_error: str | None = None  # last unknown-mode message, logged once

    async def _fetch(self) -> FastData:
        status = await self.client.read_general_status()
        try:
            mode = await self.client.read_mode()
        except InverterProtocolError as err:
            # An unknown mode letter must not make every live entity unavailable.
            if str(err) != self._mode_error:
                LOGGER.warning("%s; the mode sensor shows unknown", err)
            self._mode_error = str(err)
            mode = None
        else:
            self._mode_error = None
        grid_power = None
        if self.h_supported:
            grid_power = await self._optional(self.client.read_grid_power(), "grid_power")
        return FastData(status=status, mode=mode, grid_power=grid_power)


class VoltronicSlowCoordinator(_VoltronicCoordinator[SlowData]):
    """Settings, flags, warnings (QPIRI, QFLAG, QPIWS), plus optional QBEQI, Q1
    and the H-dialect snapshots HEEP1, HEEP2, HGEN, HTEMP."""

    async def _fetch(self) -> SlowData:
        client = self.client
        rated = await client.read_rated_info()
        flags = await client.read_flags()
        warnings = await client.read_warnings()
        equalization = await self._optional(client.read_equalization(), "equalization")
        q1 = await self._optional(client.query("Q1"))
        charge_stage = None
        if q1 is not None:
            charge_stage = await self._optional(_parse_charge_stage(q1))
        heep1 = heep2 = generation = temperatures = None
        if self.h_supported:
            heep1 = await self._optional(client.read_settings_1(), "heep1")
            heep2 = await self._optional(client.read_settings_2(), "heep2")
            generation = await self._optional(client.read_generation(), "generation")
            temperatures = await self._optional(client.read_temperatures(), "temperatures")
        return SlowData(
            rated=rated,
            flags=flags,
            warnings=warnings,
            fetched_at=dt_util.now(),
            equalization=equalization,
            charge_stage=charge_stage,
            has_q1=q1 is not None,
            heep1=heep1,
            heep2=heep2,
            generation=generation,
            temperatures=temperatures,
        )


async def _parse_charge_stage(payload: str) -> str | None:
    return parse_q1_charge_stage(payload)
