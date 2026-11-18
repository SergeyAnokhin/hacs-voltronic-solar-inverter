"""Host test of the write path of the ESPHome driver (voltronic.cpp).

Compiles the real driver against stand-ins for the ESPHome base classes (tests/esphome/stubs) and a
fake inverter, then runs tests/esphome/driver_write_test.cpp: writes refused without `enable_writes`,
refused when not on the allow-list, ACK / NAK / PI18 answers, timeout without a second try, 2 s gap
between settings, duplicates dropped, bounded queue, read-back requested after an ACK. Nothing here
touches a real inverter. Skipped when no C++ compiler (g++, clang++, or `python -m ziglang c++`).
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "esphome" / "components" / "voltronic"
TESTS = Path(__file__).parent / "esphome"


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


def test_driver_write_path(tmp_path):
    compiler = _compiler()
    if compiler is None:
        pytest.skip("no C++ compiler (g++, clang++ or ziglang) available")
    exe = tmp_path / "driver_write_test.exe"
    cmd = compiler + [
        "-std=c++17", "-O1", "-Wall", "-Wno-unused-function",
        "-I", str(TESTS / "stubs"), "-I", str(COMPONENT),
        str(TESTS / "driver_write_test.cpp"), str(COMPONENT / "voltronic.cpp"), "-o", str(exe),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0 and "ALL OK" in run.stdout, run.stdout + run.stderr
