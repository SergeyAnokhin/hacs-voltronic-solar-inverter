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

from .commands import QUERY_RE, WriteCommand
from .errors import (
    InvalidCommandError,
    InverterConnectionError,
    InverterError,
    InverterNakError,
    InverterProtocolError,
    InverterTimeoutError,
)
from .framing import CR, decode_frame, encode_frame
from .parsers import (
    DeviceIdentity,
    GeneralStatus,
    RatedInfo,
    WarningStatus,
    parse_current_options,
    parse_firmware,
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
        payload = await self._request(command, self.retries)
        if payload == "NAK":
            raise InverterNakError(f"{command} answered NAK")
        return payload

    async def write(self, command: WriteCommand) -> None:
        """Send a validated setting command; raise unless the inverter answers ACK.

        Never retried: a lost ACK may still mean the setting was applied.
        """
        if not isinstance(command, WriteCommand):
            raise InvalidCommandError("write() accepts only WriteCommand instances")
        payload = await self._request(command.text, 0)
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

    async def read_identity(self) -> DeviceIdentity:
        """Static identification. QVFW2 and the current lists are optional."""
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
        return DeviceIdentity(
            protocol_id=protocol_id,
            model=model,
            serial_number=serial,
            firmware_version=firmware,
            firmware_version_2=firmware_2,
            charging_current_options=charging,
            utility_charging_current_options=utility,
        )

    # --- internals -----------------------------------------------------------------

    async def _request(self, text: str, retries: int) -> str:
        frame = encode_frame(text)
        async with self._lock:
            attempt = 0
            while True:
                try:
                    payload = await self._exchange(frame)
                except (InverterTimeoutError, InverterProtocolError, InverterConnectionError) as err:
                    if attempt >= retries:
                        raise
                    attempt += 1
                    _LOGGER.debug("%s failed (%s), retry %d/%d", text, err, attempt, retries)
                    continue
                self.last_responses[text] = payload
                return payload

    async def _exchange(self, frame: bytes) -> str:
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
            raise InverterTimeoutError(f"no answer to {frame[:-3]!r} in {self.timeout} s") from err
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
        return decode_frame(raw)

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
