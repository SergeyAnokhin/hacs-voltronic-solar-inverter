"""Host test of the PV power / energy lambdas in the ESPHome packages.

Extracts the `interval: 1s` lambdas of esphome/packages/pv-string-energy.yaml and
pv-string-current.yaml, compiles them with tests/esphome/pv_energy_test.cpp (stand-ins for the
ESPHome types, no ESP toolchain) and runs the scenarios there: parallel / series current,
integration, no energy without voltage / with stale or gapped data, day / month / year change.
Skipped when PyYAML or a C++ compiler (g++, clang++, or `python -m ziglang c++`) is missing.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "esphome" / "packages"
SOURCE = Path(__file__).parent / "esphome" / "pv_energy_test.cpp"


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


def _lambda(package: str) -> str:
    """The `interval: 1s` lambda with id() rewritten like esphome/cpp_generator.py does.

    `id(x).` -> `x->`, a bare `id(x)` -> `x` (a POINTER, so `&id(x)` would be a pointer to a
    pointer), a globals component -> `x->value()`.
    """
    import yaml

    data = yaml.safe_load((PACKAGES / package).read_text(encoding="utf-8"))
    code = next(i for i in data["interval"] if i["interval"] == "1s")["then"][0]["lambda"]
    globals_ids = {g["id"] for g in data.get("globals", [])}
    if package == "pv-string-energy.yaml":  # the Hall package's globals, used by the energy lambda
        other = yaml.safe_load((PACKAGES / "pv-string-current.yaml").read_text(encoding="utf-8"))
        globals_ids |= {g["id"] for g in other.get("globals", [])}

    def rewrite(m):
        name, dot = m.group(1), m.group(2)
        if name in globals_ids:
            return f"{name}->value(){dot}"
        return f"{name}->" if dot else name

    return re.sub(r"id\(\s*([a-zA-Z0-9_]+)\s*\)(\.?)", rewrite, code)


def test_pv_energy_lambdas(tmp_path):
    pytest.importorskip("yaml")
    compiler = _compiler()
    if compiler is None:
        pytest.skip("no C++ compiler (g++, clang++ or ziglang) available")
    (tmp_path / "energy_lambda.inc").write_text(_lambda("pv-string-energy.yaml"), encoding="utf-8")
    (tmp_path / "hall_lambda.inc").write_text(_lambda("pv-string-current.yaml"), encoding="utf-8")
    exe = tmp_path / "pv_energy_test.exe"
    cmd = compiler + ["-std=c++17", "-O1", "-Wall", "-Wno-unused-function", "-I", str(tmp_path), str(SOURCE), "-o", str(exe)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0 and "ALL OK" in run.stdout, run.stdout + run.stderr
