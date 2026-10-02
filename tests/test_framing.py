"""CRC and frame encoding/decoding."""

import pytest

from conftest import all_recorded_frames
from protocol.errors import InverterProtocolError
from protocol.framing import crc16_xmodem, crc_bytes, decode_frame, encode_frame


def test_crc16_xmodem_reference_value():
    # CRC-16/XMODEM check value for "123456789".
    assert crc16_xmodem(b"123456789") == 0x31C3


@pytest.mark.parametrize(
    ("command", "frame"),
    [
        ("QPIGS", b"QPIGS\xb7\xa9\r"),
        ("QPIRI", b"QPIRI\xf8\x54\r"),
        ("QMOD", b"QMOD\x49\xc1\r"),
    ],
)
def test_encode_query_frames(command, frame):
    assert encode_frame(command) == frame


@pytest.mark.parametrize(
    ("data", "raw_crc", "escaped"),
    [
        (b"QAAA", 0x4F0A, b"\x4f\x0b"),  # low byte 0x0A -> 0x0B
        (b"QAH9", 0x0A0D, b"\x0b\x0e"),  # both bytes reserved
        (b"QAAT", 0x0D9E, b"\x0e\x9e"),  # high byte 0x0D -> 0x0E
        (b"QABS", 0x282A, b"\x29\x2a"),  # high byte 0x28 -> 0x29
        (b"QAFU", 0x8428, b"\x84\x29"),  # low byte 0x28 -> 0x29
    ],
)
def test_crc_escaping(data, raw_crc, escaped):
    assert crc16_xmodem(data) == raw_crc
    assert crc_bytes(data) == escaped
    assert encode_frame(data.decode()) == data + escaped + b"\r"


@pytest.mark.parametrize(("label", "frame", "payload"), all_recorded_frames())
def test_decode_every_recorded_frame(label, frame, payload):
    assert decode_frame(frame) == payload


def test_decode_without_trailing_cr():
    assert decode_frame(bytes.fromhex("2842e7c9")) == "B"


@pytest.mark.parametrize(
    "frame",
    [
        bytes.fromhex("2842e7c80d"),  # CRC off by one
        b"B\xe7\xc9\r",  # no '('
        b"(\r",  # too short
        b"",
    ],
)
def test_decode_rejects_bad_frames(frame):
    with pytest.raises(InverterProtocolError):
        decode_frame(frame)


def test_decode_nak_and_ack():
    assert decode_frame(b"(NAK" + crc_bytes(b"(NAK") + b"\r") == "NAK"
    assert decode_frame(b"(ACK" + crc_bytes(b"(ACK") + b"\r") == "ACK"
