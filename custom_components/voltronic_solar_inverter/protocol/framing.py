"""Frame encoding/decoding for the Voltronic PI30 ASCII protocol (and the CRC-less H dialect).

request : <ASCII command> <CRC hi> <CRC lo> 0x0D
response: '(' <payload> <CRC hi> <CRC lo> 0x0D

CRC is CRC-16/XMODEM over everything before the CRC; a CRC byte equal to
0x28 '(', 0x0D CR or 0x0A LF is incremented by one.
"""

from __future__ import annotations

from .errors import InverterProtocolError

CR = b"\r"
_RESERVED_BYTES = (0x28, 0x0D, 0x0A)


def crc16_xmodem(data: bytes) -> int:
    """Return the CRC-16/XMODEM (poly 0x1021, init 0) of ``data``."""
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def _escape(byte: int) -> int:
    return byte + 1 if byte in _RESERVED_BYTES else byte


def crc_bytes(data: bytes) -> bytes:
    """Return the two (escaped) CRC bytes the inverter expects after ``data``."""
    crc = crc16_xmodem(data)
    return bytes((_escape(crc >> 8), _escape(crc & 0xFF)))


def encode_frame(command: str) -> bytes:
    """Encode an ASCII command into a complete request frame."""
    raw = command.encode("ascii")
    return raw + crc_bytes(raw) + CR


def decode_frame(frame: bytes) -> str:
    """Validate a response frame and return its payload text (without '(').

    Raises InverterProtocolError on a malformed frame or a CRC mismatch.
    """
    body = frame[:-1] if frame.endswith(CR) else frame
    if len(body) < 3 or body[:1] != b"(":
        raise InverterProtocolError(f"malformed response frame: {frame!r}")
    payload, received = body[:-2], body[-2:]
    if crc_bytes(payload) != received:
        raise InverterProtocolError(f"CRC mismatch in response frame: {frame!r}")
    try:
        return payload[1:].decode("ascii")
    except UnicodeDecodeError as err:
        raise InverterProtocolError(f"non-ASCII payload: {frame!r}") from err


# --- Solar Plug "H" dialect: no CRC in either direction ------------------------


def encode_plain_frame(command: str) -> bytes:
    """Encode a CRC-less request (Solar Plug H dialect, QPRTL): ASCII + CR."""
    return command.encode("ascii") + CR


def decode_plain_frame(frame: bytes) -> str:
    """Return the payload of a CRC-less response '(' <payload> CR."""
    body = frame[:-1] if frame.endswith(CR) else frame
    if len(body) < 2 or body[:1] != b"(":
        raise InverterProtocolError(f"malformed response frame: {frame!r}")
    try:
        return body[1:].decode("ascii")
    except UnicodeDecodeError as err:
        raise InverterProtocolError(f"non-ASCII payload: {frame!r}") from err
