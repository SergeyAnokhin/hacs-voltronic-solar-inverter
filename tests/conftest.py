"""Shared test helpers.

The protocol package has no Home Assistant dependency; it is imported as the
top-level package ``protocol`` so these tests run without Home Assistant.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_DIR = ROOT / "custom_components" / "voltronic_solar_inverter"
FIXTURES = Path(__file__).parent / "fixtures"

for path in (INTEGRATION_DIR, ROOT):  # ROOT: lets Home Assistant import custom_components
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def load_fixture(name: str, strategy: str = "stream") -> dict[str, dict]:
    """Return {command: {raw_hex, text, crc_ok, ...}} from a recorded probe file."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))[strategy]


def answered(name: str, strategy: str = "stream") -> dict[str, str]:
    """Return {command: payload text} for commands that answered with a valid CRC."""
    return {
        cmd: entry["text"]
        for cmd, entry in load_fixture(name, strategy).items()
        if entry.get("crc_ok")
    }


def all_recorded_frames() -> list[tuple[str, bytes, str]]:
    """(label, raw frame, payload) for every CRC-valid answer in every fixture file."""
    frames = []
    for path in sorted(FIXTURES.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for strategy in ("legacy", "stream"):
            for cmd, entry in data.get(strategy, {}).items():
                if entry.get("crc_ok"):
                    frames.append(
                        (f"{path.stem}:{strategy}:{cmd}", bytes.fromhex(entry["raw_hex"]), entry["text"])
                    )
    return frames


Responder = Callable[[bytes], "list[bytes] | None"]


class FakeWriter:
    """Stands in for asyncio.StreamWriter; feeds scripted answers into the reader."""

    def __init__(self, gateway: FakeGateway, reader: asyncio.StreamReader) -> None:
        self._gateway = gateway
        self._reader = reader
        self.closed = False

    def write(self, data: bytes) -> None:
        if self.closed:
            raise ConnectionResetError("writer closed")
        self._gateway.sent.append(data)
        chunks = self._gateway.responder(data)
        loop = asyncio.get_running_loop()
        for i, chunk in enumerate(chunks or []):
            loop.call_later(0.005 * (i + 1), self._feed, chunk)

    def _feed(self, chunk: bytes) -> None:
        if not self.closed:
            self._reader.feed_data(chunk)

    async def drain(self) -> None:
        if self.closed:
            raise ConnectionResetError("writer closed")

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class FakeGateway:
    """Fake RS232<->TCP gateway: no real socket is opened."""

    def __init__(self, responder: Responder) -> None:
        self.responder = responder
        self.sent: list[bytes] = []
        self.connections: list[tuple[asyncio.StreamReader, FakeWriter]] = []
        self.refuse = False

    async def open_connection(self, host: str, port: int):
        if self.refuse:
            raise ConnectionRefusedError("refused")
        reader = asyncio.StreamReader()
        writer = FakeWriter(self, reader)
        self.connections.append((reader, writer))
        return reader, writer


@pytest.fixture
def fake_gateway_factory():
    return FakeGateway
