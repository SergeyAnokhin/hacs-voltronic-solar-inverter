"""InverterClient against a fake gateway (no real socket, no real inverter)."""

from __future__ import annotations

import asyncio

import pytest

from conftest import FakeGateway, answered
from protocol import commands
from protocol.client import InverterClient
from protocol.errors import (
    InvalidCommandError,
    InverterConnectionError,
    InverterNakError,
    InverterProtocolError,
    InverterTimeoutError,
)
from protocol.framing import crc_bytes, encode_frame

FULL = answered("snapshot_B_night_output_on.json")


def reply(payload: str) -> bytes:
    body = b"(" + payload.encode("ascii")
    return body + crc_bytes(body) + b"\r"


def table_responder(table: dict[str, str]):
    """Answer known commands from a table; stay silent otherwise (like the inverter)."""

    def responder(frame: bytes):
        command = frame[:-3].decode("ascii")
        return [reply(table[command])] if command in table else None

    return responder


def make_client(gateway: FakeGateway, **kwargs) -> InverterClient:
    kwargs.setdefault("timeout", 0.2)
    kwargs.setdefault("min_gap", 0)
    return InverterClient("gw", 8899, open_connection=gateway.open_connection, **kwargs)


def run(coro):
    return asyncio.run(coro)


def test_query_returns_payload_and_reuses_connection():
    gw = FakeGateway(table_responder(FULL))

    async def scenario():
        client = make_client(gw)
        status = await client.read_general_status()
        mode = await client.read_mode()
        await client.close()
        return status, mode

    status, mode = run(scenario())
    assert status.battery_voltage == 25.60
    assert mode == "battery"
    assert gw.sent == [encode_frame("QPIGS"), encode_frame("QMOD")]
    assert len(gw.connections) == 1


def test_frame_split_into_many_chunks():
    frame = reply(FULL["QPIRI"])

    def responder(_frame):
        return [frame[i : i + 7] for i in range(0, len(frame), 7)]

    gw = FakeGateway(responder)
    rated = run(make_client(gw).read_rated_info())
    assert rated.battery_rating_voltage == 24.0


def test_timeout_then_retry_succeeds():
    calls = 0

    def responder(frame):
        nonlocal calls
        calls += 1
        return None if calls == 1 else [reply(FULL["QPIGS"])]  # first command lost

    gw = FakeGateway(responder)
    status = run(make_client(gw).read_general_status())
    assert status.ac_output_voltage == 230.0
    assert gw.sent == [encode_frame("QPIGS")] * 2


def test_timeout_after_all_retries():
    gw = FakeGateway(lambda frame: None)
    with pytest.raises(InverterTimeoutError):
        run(make_client(gw, retries=1).query("QT"))
    assert len(gw.sent) == 2


def test_incomplete_frame_times_out():
    gw = FakeGateway(lambda frame: [reply(FULL["QPIGS"])[:20]])  # no CR
    with pytest.raises(InverterTimeoutError):
        run(make_client(gw, retries=0).query("QPIGS"))


def test_late_answer_is_discarded_before_next_command():
    """A reply that arrives after the timeout must not be taken as the next answer."""
    late = reply(FULL["QPIGS"])

    def responder(frame):
        command = frame[:-3].decode()
        if command == "QPIGS":
            return None  # answered "late" below
        return [reply(FULL[command])]

    gw = FakeGateway(responder)

    async def scenario():
        client = make_client(gw, retries=0)
        with pytest.raises(InverterTimeoutError):
            await client.query("QPIGS")
        gw.connections[-1][0].feed_data(late)  # stale bytes in the stream
        return await client.query("QMOD")

    assert run(scenario()) == "B"


def test_late_answer_after_timeout_does_not_shift_answers():
    """Seen on the real unit: QPIGS answered after the timeout, then QMOD got a QPIGS payload."""
    calls = 0

    def responder(frame):
        nonlocal calls
        command = frame[:-3].decode()
        if command == "QPIGS":
            calls += 1
            if calls == 1:
                writer = gw.connections[-1][1]
                asyncio.get_running_loop().call_later(0.25, writer._feed, reply(FULL["QPIGS"]))
                return None
        return [reply(FULL[command])]

    gw = FakeGateway(responder)

    async def scenario():
        client = make_client(gw)
        status = await client.read_general_status()
        await asyncio.sleep(0.1)  # the late answer arrives meanwhile
        return status, await client.read_mode()

    status, mode = run(scenario())
    assert status.battery_voltage == 25.60
    assert mode == "battery"
    assert len(gw.connections) == 2  # dropped after the timeout


def test_out_of_sync_qmod_answer_is_asked_again():
    answers = iter([FULL["QPIGS"], "B"])
    gw = FakeGateway(lambda frame: [reply(next(answers))])
    assert run(make_client(gw).read_mode()) == "battery"
    assert gw.sent == [encode_frame("QMOD")] * 2
    assert len(gw.connections) == 2


def test_crc_error_is_retried():
    calls = 0

    def responder(frame):
        nonlocal calls
        calls += 1
        good = reply("B")
        return [good[:-2] + b"\x00\r"] if calls == 1 else [good]

    gw = FakeGateway(responder)
    assert run(make_client(gw).query("QMOD")) == "B"
    with pytest.raises(InverterProtocolError):
        run(make_client(FakeGateway(lambda f: [b"(B\x00\x00\r"]), retries=0).query("QMOD"))


def test_nak_on_query():
    gw = FakeGateway(lambda frame: [reply("NAK")])
    with pytest.raises(InverterNakError):
        run(make_client(gw).query("QPIHF"))
    assert len(gw.sent) == 1  # NAK is an answer, not retried


def test_reconnect_after_gateway_closed_connection():
    gw = FakeGateway(table_responder(FULL))

    async def scenario():
        client = make_client(gw)
        await client.query("QMOD")
        gw.connections[-1][0].feed_eof()  # gateway dropped the idle connection
        return await client.query("QMOD")

    assert run(scenario()) == "B"
    assert len(gw.connections) == 2


def test_connection_refused():
    gw = FakeGateway(table_responder(FULL))
    gw.refuse = True
    with pytest.raises(InverterConnectionError):
        run(make_client(gw).query("QMOD"))


def test_query_refuses_non_query_commands():
    gw = FakeGateway(table_responder(FULL))
    for bad in ("POP01", "PEa", "MCHGC010", "qpigs", "QPIGS\r", ""):
        with pytest.raises(InvalidCommandError):
            run(make_client(gw).query(bad))
    assert gw.sent == []


def test_write_ack():
    gw = FakeGateway(lambda frame: [reply("ACK")])
    run(make_client(gw).write(commands.set_flag("buzzer", False)))
    assert gw.sent == [bytes.fromhex("504461e3410d")]


def test_write_nak_raises_and_is_not_retried():
    gw = FakeGateway(lambda frame: [reply("NAK")])
    with pytest.raises(InverterNakError):
        run(make_client(gw).write(commands.set_output_source_priority(1)))
    assert gw.sent == [encode_frame("POP01")]


def test_write_timeout_is_not_retried():
    gw = FakeGateway(lambda frame: None)
    with pytest.raises(InverterTimeoutError):
        run(make_client(gw, retries=3).write(commands.set_charger_source_priority(2)))
    assert len(gw.sent) == 1


def test_write_unexpected_answer():
    gw = FakeGateway(lambda frame: [reply("B")])
    with pytest.raises(InverterProtocolError):
        run(make_client(gw).write(commands.set_flag("backlight", True)))


def test_write_accepts_only_write_commands():
    gw = FakeGateway(lambda frame: [reply("ACK")])
    with pytest.raises(InvalidCommandError):
        run(make_client(gw).write("PEa"))  # type: ignore[arg-type]
    assert gw.sent == []


def test_concurrent_requests_are_serialized():
    in_flight = 0
    max_in_flight = 0

    def responder(frame):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        command = frame[:-3].decode()

        def done():
            nonlocal in_flight
            in_flight -= 1

        asyncio.get_running_loop().call_later(0.004, done)
        return [reply(FULL[command])]

    gw = FakeGateway(responder)

    async def scenario():
        client = make_client(gw)
        return await asyncio.gather(*(client.query(c) for c in ("QPIGS", "QMOD", "QPIRI", "QFLAG")))

    results = run(scenario())
    assert results == [FULL["QPIGS"], "B", FULL["QPIRI"], FULL["QFLAG"]]
    assert max_in_flight == 1


def plain_responder(table: dict[str, str], plain: dict[str, str]):
    """Q commands need a valid CRC; H commands answer only without CRC (like the unit)."""

    def responder(frame: bytes):
        plain_cmd = frame[:-1].decode("ascii", "replace")
        if plain_cmd in plain:
            return [b"(" + plain[plain_cmd].encode() + b"\r"]
        command = frame[:-3].decode("ascii", "replace")
        if command in table and encode_frame(command) == frame:
            return [reply(table[command])]
        return None

    return responder


def test_query_plain_sends_without_crc():
    gw = FakeGateway(plain_responder({}, {"HGEN": "261002 21:01 01.765 0003.1 0008.5 000000008.5 0"}))
    generation = run(make_client(gw).read_generation())
    assert generation.pv_energy_today == 1.765
    assert gw.sent == [b"HGEN\r"]


def test_query_plain_refuses_unapproved_commands():
    gw = FakeGateway(plain_responder({}, {}))
    for bad in ("HEEP3", "HIMSG2", "QPIGS", "PVENGUSE01", "hgen", ""):
        with pytest.raises(InvalidCommandError):
            run(make_client(gw).query_plain(bad))
    assert gw.sent == []


def test_mixed_crc_and_plain_on_one_connection():
    gw = FakeGateway(plain_responder(FULL, {"HTEMP": "028 039 032 032 039 030 030 0"}))

    async def scenario():
        client = make_client(gw)
        mode = await client.read_mode()
        temps = await client.read_temperatures()
        stage_payload = await client.query("QMOD")
        return mode, temps, stage_payload

    mode, temps, again = run(scenario())
    assert (mode, temps.transformer, again) == ("battery", 32, "B")
    assert len(gw.connections) == 1


def test_read_identity_detects_h_dialect():
    gw = FakeGateway(plain_responder(FULL, {"QPRTL": "HPVINV02", "HIMSG1": "0040.09 20260119 11"}))
    identity = run(make_client(gw).read_identity())
    assert identity.h_protocol == "HPVINV02"
    assert identity.firmware_date == "2026-01-19"
    assert b"QPRTL\r" in gw.sent  # QPRTL goes out without CRC


def test_read_identity_with_optional_commands_missing():
    table = {k: FULL[k] for k in ("QPI", "QMN", "QID", "QVFW")}
    gw = FakeGateway(table_responder(table))
    identity = run(make_client(gw, timeout=0.05, retries=0).read_identity())
    assert identity.protocol_id == "PI30"
    assert identity.model == "VMII-4000"
    assert identity.serial_number == FULL["QID"]
    assert identity.firmware_version == "00040.09"
    assert identity.firmware_version_2 is None
    assert identity.charging_current_options == ()
    assert identity.h_protocol is None
    assert identity.firmware_date is None


def test_read_identity_full():
    gw = FakeGateway(table_responder(FULL))
    identity = run(make_client(gw).read_identity())
    assert identity.firmware_version_2 == "00000.00"
    assert identity.charging_current_options == (10, 20, 30, 40, 50, 60, 70, 80)
    assert identity.utility_charging_current_options == (2, 10, 20, 30, 40, 50, 60)


def test_min_gap_between_exchanges():
    gw = FakeGateway(table_responder(FULL))

    async def scenario():
        client = make_client(gw, min_gap=0.15)
        loop = asyncio.get_running_loop()
        await client.query("QMOD")
        start = loop.time()
        await client.query("QMOD")
        return loop.time() - start

    assert run(scenario()) >= 0.14
