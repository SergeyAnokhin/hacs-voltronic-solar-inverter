"""Host test of the C++ protocol layer of the ESPHome component.

Compiles tests/esphome/protocol_test.cpp (which includes
esphome/components/voltronic/protocol.h) with a local C++ compiler and compares its answers
with the Python implementation on the frames recorded from the real inverter. Skipped when
no C++ compiler is found (g++, clang++, or `python -m ziglang c++`).
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from protocol.framing import decode_frame, decode_plain_frame, encode_frame
from protocol.parsers import WARNING_BITS, FAULT, FAULT_IF_INVERTER_FAULT, WarningStatus, parse_qflag, FLAGS

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "esphome" / "components" / "voltronic"
SOURCE = Path(__file__).parent / "esphome" / "protocol_test.cpp"
FIXTURES = Path(__file__).parent / "fixtures"

# commands the component polls (entities.py / voltronic.cpp)
POLLED = {
    "QPI", "QMN", "QID", "QVFW", "QPIGS", "QMOD", "QPIRI", "QFLAG", "QPIWS", "Q1", "QBEQI",
    "HGRID", "HGEN", "HTEMP", "HEEP1", "HEEP2", "HIMSG1",
}
PLAIN = {"HGRID", "HGEN", "HTEMP", "HEEP1", "HEEP2", "HIMSG1", "QPRTL"}


def _compiler() -> list[str] | None:
    for name in ("g++", "clang++", "c++"):
        path = shutil.which(name)
        if path:
            return [path]
    try:
        out = subprocess.run([sys.executable, "-m", "ziglang", "version"], capture_output=True, timeout=60)
        if out.returncode == 0:
            return [sys.executable, "-m", "ziglang", "c++"]
    except (OSError, subprocess.SubprocessError):
        pass
    return None


@pytest.fixture(scope="module")
def tester(tmp_path_factory):
    compiler = _compiler()
    if compiler is None:
        pytest.skip("no C++ compiler (g++, clang++ or ziglang) available")
    exe = tmp_path_factory.mktemp("cpp") / "protocol_test.exe"
    cmd = compiler + ["-std=c++17", "-O1", "-Wall", "-I", str(COMPONENT), str(SOURCE), "-o", str(exe)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    def run(lines: list[str]) -> list[str]:
        out = subprocess.run([str(exe)], input="\n".join(lines) + "\n", capture_output=True, text=True, timeout=60)
        assert out.returncode == 0
        return out.stdout.splitlines()

    return run


def _recorded_frames():
    """(cmd, plain, raw bytes, expected payload) from every recorded probe/snapshot."""
    seen = set()
    for path in sorted(FIXTURES.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        stream = data.get("stream") if isinstance(data, dict) else None
        if not isinstance(stream, dict):
            continue
        for cmd, entry in stream.items():
            if cmd not in POLLED or not isinstance(entry, dict) or not entry.get("raw_hex"):
                continue
            raw = bytes.fromhex(entry["raw_hex"])
            plain = cmd in PLAIN
            try:
                payload = decode_plain_frame(raw) if plain else decode_frame(raw)
            except Exception:  # a recorded bad frame; not a test vector
                continue
            if (cmd, raw) in seen:
                continue
            seen.add((cmd, raw))
            yield cmd, plain, raw, payload


def test_request_frames_match_python(tester):
    commands = sorted(POLLED - PLAIN) + ["PEa", "PDa", "POP01", "MNCHGC050", "PBCV23.0", "PVENGUSE01"]
    out = tester([f"ENC {c}" for c in commands])
    assert out == [encode_frame(c).hex() for c in commands]


def test_recorded_answers_decode_and_validate(tester):
    frames = list(_recorded_frames())
    assert len(frames) > 30
    out = tester([f"FRAME {cmd} {int(plain)} {raw.hex()}" for cmd, plain, raw, _ in frames])
    for (cmd, _plain, _raw, payload), line in zip(frames, out):
        assert line == f"VALID {payload}", (cmd, line)


def test_corrupted_crc_is_rejected(tester):
    for cmd, plain, raw, _ in _recorded_frames():
        if plain:
            continue
        bad = bytearray(raw)
        bad[-3] ^= 0x01  # flip one bit of a CRC byte (index -1 is the CR)
        assert tester([f"FRAME {cmd} 0 {bad.hex()}"]) == ["BAD"], cmd


def test_qpiws_classes_match_python_table(tester):
    expected = ["-"] * 32
    for index, (_key, kind) in WARNING_BITS.items():
        expected[index] = "F" if kind == FAULT else "X" if kind == FAULT_IF_INVERTER_FAULT else "W"
    assert tester(["CLASSES"]) == ["".join(expected)]


def test_qpiws_any_matches_python(tester):
    cases = ["0" * 32, "01000000000000000000000000000000", "00000100000000000000000000000000",
             "00000000010000000000000000000000", "01000000010000000000000000000000",
             "10000000000000000000000000000000", "00000000000000000000000000000010"]
    out = tester([f"WS {bits}" for bits in cases])
    for bits, line in zip(cases, out):
        status = WarningStatus(bits=bits)
        assert line == f"{int(bool(status.faults))} {int(bool(status.warnings))}", bits


def test_qflag_state_matches_python(tester):
    payload = "EabjvxyDkuz"
    parsed = parse_qflag(payload)
    letters = list(FLAGS)
    out = tester([f"FLAG {payload} {letter}" for letter in letters])
    for letter, line in zip(letters, out):
        assert line == str(int(parsed[FLAGS[letter]])), letter
    assert tester([f"FLAG {payload} q"]) == ["-1"]


def test_foreign_h_answers_are_rejected(tester):
    # the 710 000 W grid power seen on a shared gateway, and a QPIGS payload sent for HGRID
    hgrid = "(239.0 50.0 280 090 70 40 +710000 0 04500 11+00000\r"
    qpigs = "(234.1 50.0 230.1 50.0 0483 0317 012 372 25.10 000 082 0041 00.0 000.0 00.00 00015 00010000 00 00 00000 010\r"
    out = tester([f"FRAME HGRID 1 {hgrid.encode().hex()}", f"FRAME HGRID 1 {qpigs.encode().hex()}"])
    assert out[0].startswith("INVALID") and out[1].startswith("INVALID")


def test_number_parsing_is_strict(tester):
    out = tester(["NUM +00000", "NUM -0012", "NUM 29.20", "NUM 12x", "NUM --1"])
    assert out[:3] == ["0", "-12", "29.2"]
    assert out[3:] == ["NAN", "NAN"]
