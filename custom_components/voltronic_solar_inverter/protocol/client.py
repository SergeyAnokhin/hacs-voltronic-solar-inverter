"""Async TCP client for an inverter behind an RS232<->TCP gateway (e.g. Elfin).

One persistent connection, one exchange at a time (asyncio.Lock), read until
CR, CRC check, per-command timeout, retry of read-only queries, transparent
reconnect. The gateway serves a single client; unknown commands are silent.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import contextlib
import logging
import time

from .commands import PLAIN_QUERIES, QUERY_RE, WriteCommand
from .errors import (
    InvalidCommandError,
    InverterConnectionError,
    InverterError,
    InverterNakError,
    InverterProtocolError,
    InverterTimeoutError,
)
from .framing import CR, decode_frame, decode_plain_frame, encode_frame, encode_plain_frame
from .h_parsers import (
    Generation,
    SettingsEeprom1,
    SettingsEeprom2,
    Temperatures,
    parse_heep1,
    parse_heep2,
    parse_hgen,
    parse_hgrid_power,
    parse_himsg1_firmware_date,
    parse_htemp,
)
from .parsers import (
    DeviceIdentity,
    Equalization,
    GeneralStatus,
    RatedInfo,
    WarningStatus,
    parse_current_options,
    parse_firmware,
    parse_q1_charge_stage,
    parse_qbeqi,
    parse_qflag,
    parse_qmod,
    parse_qpigs,
    parse_qpiri,
    parse_qpiws,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 2.0  # QPIGS takes ~0.65 s; 2 s leaves margin for the gateway
DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_RETRIES = 1  # the first command after an idle period is sometimes lost
DEFAULT_MIN_GAP = 0.1  # pause between two exchanges
_DRAIN_WAIT = 0.01

OpenConnection = Callable[
    [str, int], Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]]
]


class InverterClient:
    """Talks to one inverter. Safe to share between coroutines."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        min_gap: float = DEFAULT_MIN_GAP,
        open_connection: OpenConnection | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self.retries = retries
        self.min_gap = min_gap
        self._open_connection = open_connection or asyncio.open_connection
        self._lock = asyncio.Lock()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._last_exchange = 0.0
        self.last_responses: dict[str, str] = {}

    # --- public API ------------------------------------------------------------

    async def query(self, command: str) -> str:
        """Send a read-only Q command and return the payload text."""
        if not QUERY_RE.fullmatch(command):
            raise InvalidCommandError(f"refusing to send non-query command {command!r}")
        payload = await self._request(command, encode_frame(command), decode_frame, self.retries)
        if payload == "NAK":
            raise InverterNakError(f"{command} answered NAK")
        return payload

    async def query_plain(self, command: str) -> str:
        """Send an owner-approved read-only query WITHOUT CRC (Solar Plug H dialect)."""
        if command not in PLAIN_QUERIES:
            raise InvalidCommandError(f"refusing to send {command!r}: not an approved H query")
        payload = await self._request(
            command, encode_plain_frame(command), decode_plain_frame, self.retries
        )
        if payload == "NAK":
            raise InverterNakError(f"{command} answered NAK")
        return payload

    async def write(self, command: WriteCommand) -> None:
        """Send a validated setting command; raise unless the inverter answers ACK.

        Never retried: a lost ACK may still mean the setting was applied.
        """
        if not isinstance(command, WriteCommand):
            raise InvalidCommandError("write() accepts only WriteCommand instances")
        payload = await self._request(command.text, command.frame, decode_frame, 0)
        if payload == "ACK":
            return
        if payload == "NAK":
            raise InverterNakError(f"{command.text} answered NAK")
        raise InverterProtocolError(f"{command.text}: unexpected answer {payload!r}")

    async def close(self) -> None:
        async with self._lock:
            await self._close()

    # --- typed helpers -----------------------------------------------------------

    async def read_general_status(self) -> GeneralStatus:
        return parse_qpigs(await self.query("QPIGS"))

    async def read_mode(self) -> str:
        return parse_qmod(await self.query("QMOD"))

    async def read_rated_info(self) -> RatedInfo:
        return parse_qpiri(await self.query("QPIRI"))

    async def read_warnings(self) -> WarningStatus:
        return parse_qpiws(await self.query("QPIWS"))

    async def read_flags(self) -> dict[str, bool]:
        return parse_qflag(await self.query("QFLAG"))

    async def read_equalization(self) -> Equalization:
        return parse_qbeqi(await self.query("QBEQI"))

    async def read_charge_stage(self) -> str | None:
        return parse_q1_charge_stage(await self.query("Q1"))

    async def read_settings_1(self) -> SettingsEeprom1:
        return parse_heep1(await self.query_plain("HEEP1"))

    async def read_settings_2(self) -> SettingsEeprom2:
        return parse_heep2(await self.query_plain("HEEP2"))

    async def read_generation(self) -> Generation:
        return parse_hgen(await self.query_plain("HGEN"))

    async def read_temperatures(self) -> Temperatures:
        return parse_htemp(await self.query_plain("HTEMP"))

    async def read_grid_power(self) -> int:
        return parse_hgrid_power(await self.query_plain("HGRID"))

    async def read_identity(self) -> DeviceIdentity:
        """Static identification. Everything after QVFW is optional.

        The H dialect is detected with a CRC-less QPRTL; inverters without it
        stay silent and only cost one timeout at start-up.
        """
        protocol_id = (await self.query("QPI")).strip()
        model = (await self.query("QMN")).strip()
        serial = (await self.query("QID")).strip()
        firmware = parse_firmware(await self.query("QVFW"))
        firmware_2 = None
        charging: tuple[int, ...] = ()
        utility: tuple[int, ...] = ()
        with contextlib.suppress(InverterError):
            firmware_2 = parse_firmware(await self.query("QVFW2"))
        with contextlib.suppress(InverterError):
            charging = parse_current_options(await self.query("QMCHGCR"))
        with contextlib.suppress(InverterError):
            utility = parse_current_options(await self.query("QMUCHGCR"))
        h_protocol = None
        firmware_date = None
        with contextlib.suppress(InverterError):
            h_protocol = (await self.query_plain("QPRTL")).strip() or None
        if h_protocol:
            with contextlib.suppress(InverterError):
                firmware_date = parse_himsg1_firmware_date(await self.query_plain("HIMSG1"))
        return DeviceIdentity(
            protocol_id=protocol_id,
            model=model,
            serial_number=serial,
            firmware_version=firmware,
            firmware_version_2=firmware_2,
            charging_current_options=charging,
            utility_charging_current_options=utility,
            h_protocol=h_protocol,
            firmware_date=firmware_date,
        )

    # --- internals -----------------------------------------------------------------

    async def _request(
        self, text: str, frame: bytes, decode: Callable[[bytes], str], retries: int
    ) -> str:
        async with self._lock:
            attempt = 0
            while True:
                try:
                    payload = await self._exchange(frame, decode)
                except (InverterTimeoutError, InverterProtocolError, InverterConnectionError) as err:
                    if attempt >= retries:
                        raise
                    attempt += 1
                    _LOGGER.debug("%s failed (%s), retry %d/%d", text, err, attempt, retries)
                    continue
                self.last_responses[text] = payload
                return payload

    async def _exchange(self, frame: bytes, decode: Callable[[bytes], str]) -> str:
        await self._connect()
        if not await self._drain():
            # The gateway closed the idle connection: reconnect once, transparently.
            await self._close()
            await self._connect()
        wait = self._last_exchange + self.min_gap - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        assert self._reader is not None and self._writer is not None
        try:
            self._writer.write(frame)
            await self._writer.drain()
            raw = await asyncio.wait_for(self._reader.readuntil(CR), self.timeout)
        except TimeoutError as err:
            # Keep the connection; a late answer is discarded by _drain() next time.
            raise InverterTimeoutError(f"no answer to {frame!r} in {self.timeout} s") from err
        except asyncio.IncompleteReadError as err:
            await self._close()
            raise InverterConnectionError("connection closed by gateway") from err
        except asyncio.LimitOverrunError as err:
            await self._close()
            raise InverterProtocolError("response too long") from err
        except OSError as err:
            await self._close()
            raise InverterConnectionError(f"connection error: {err}") from err
        finally:
            self._last_exchange = time.monotonic()
        return decode(raw)

    async def _connect(self) -> None:
        if self._writer is not None:
            return
        try:
            self._reader, self._writer = await asyncio.wait_for(
                self._open_connection(self.host, self.port), self.connect_timeout
            )
        except (OSError, TimeoutError) as err:
            raise InverterConnectionError(
                f"cannot connect to {self.host}:{self.port}: {err}"
            ) from err

    async def _drain(self) -> bool:
        """Discard stale bytes; return False if the gateway closed the connection."""
        assert self._reader is not None
        while True:
            try:
                chunk = await asyncio.wait_for(self._reader.read(1024), _DRAIN_WAIT)
            except TimeoutError:
                return True
            if not chunk:
                return False
            _LOGGER.debug("discarded stale bytes: %r", chunk)

    async def _close(self) -> None:
        writer, self._reader, self._writer = self._writer, None, None
        if writer is None:
            return
        writer.close()
        with contextlib.suppress(OSError, asyncio.TimeoutError):
            await asyncio.wait_for(writer.wait_closed(), 1.0)
