"""Host test of the setting (write) layer of the ESPHome component.

The C++ builders and the allow-list in esphome/components/voltronic/protocol.h must give exactly the
texts of custom_components/.../protocol/commands.py (the Python integration, tested separately) and
refuse the same arguments; the control entity tables in entities.py must only use settings the
allow-list accepts. Nothing here talks to an inverter. Skipped when no C++ compiler (g++, clang++, or
`python -m ziglang c++`) is found.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from protocol import commands
from protocol.errors import InvalidCommandError
from protocol.framing import CR, crc_bytes, decode_write_answer
from protocol.parsers import FLAGS

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "esphome" / "components" / "voltronic"
SOURCE = Path(__file__).parent / "esphome" / "protocol_test.cpp"


def _entities():
    spec = importlib.util.spec_from_file_location("voltronic_entities", COMPONENT / "entities.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ENT = _entities()


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


def _py(builder, *args) -> str:
    try:
        return builder(*args).text
    except InvalidCommandError:
        return "INVALID"


def _frange(low: float, high: float, step: float) -> list[float]:
    count = round((high - low) / step)
    return [round(low + i * step, 4) for i in range(count + 1)]


def _volt_cases(setting) -> list[float]:
    values = _frange(setting.minimum, setting.maximum, setting.step)
    return values + [
        round(setting.minimum - 0.1, 4),
        round(setting.maximum + 0.1, 4),
        round(setting.minimum + setting.step / 3, 4),  # not a multiple of the step
        0.0,
        100.0,
        -1.0,
    ]


def _int_cases(setting) -> list[int]:
    values = list(range(setting.minimum, setting.maximum + 1, max(setting.step, 1)))
    mid = (setting.minimum + setting.maximum) // 2
    return sorted(set(values + [setting.minimum - 1, setting.maximum + 1, mid + 1, mid + 2, 1, 7]))


def test_voltage_builders_match_python(tester):
    cases: list[tuple[str, float, str]] = []
    for key, setting in commands.VOLTAGE_SETTINGS_24V.items():
        for v in _volt_cases(setting):
            cases.append((setting.prefix, v, _py(commands.set_battery_voltage, key, v)))
    for key, setting in commands.HEEP_VOLTAGE_SETTINGS_24V.items():
        for v in _volt_cases(setting):
            cases.append((setting.prefix, v, _py(commands.set_heep_voltage, key, v)))
    out = tester([f"WVAL {prefix} {v:.4f}" for prefix, v, _ in cases])
    for (prefix, v, expected), line in zip(cases, out):
        assert line == expected, (prefix, v)


def test_integer_builders_match_python(tester):
    cases: list[tuple[str, int, str]] = []
    for key, setting in commands.INTEGER_SETTINGS.items():
        for v in _int_cases(setting):
            cases.append((setting.prefix, v, _py(commands.set_integer_setting, key, v)))
    out = tester([f"WVAL {prefix} {v}" for prefix, v, _ in cases])
    for (prefix, v, expected), line in zip(cases, out):
        assert line == expected, (prefix, v)
    assert tester(["WVAL DISCC 12.5", "WVAL NOPE 5"]) == ["INVALID", "INVALID"]


def test_charging_current_builders_match_python(tester):
    options = (10, 20, 30, 40, 50, 60, 70, 80)
    cases = []
    for prefix, builder in (("MNCHGC", commands.set_max_charging_current), ("MUCHGC", commands.set_max_utility_charging_current)):
        for amps in options:
            cases.append((prefix, amps, _py(builder, amps, options)))
        for amps in (0, 1000, -5):  # outside 1..999: refused by both
            cases.append((prefix, amps, _py(builder, amps, (0, 1000, -5))))
    out = tester([f"WVAL {prefix} {a}" for prefix, a, _ in cases])
    for (prefix, a, expected), line in zip(cases, out):
        assert line == expected, (prefix, a)


def test_code_flag_and_special_builders_match_python(tester):
    lines: list[str] = []
    expected: list[str] = []

    for code in range(0, 4):
        lines += [f"WCODE POP {code}", f"WCODE PCP {code}", f"WCODE PVENGUSE {code}"]
        expected += [
            _py(commands.set_output_source_priority, code),
            _py(commands.set_charger_source_priority, code),
            _py(commands.set_solar_supply_priority, code),
        ]
    for enabled in (True, False):
        lines += [f"WCODE PDAULC {int(enabled)}", f"WCODE PDAULON {int(enabled)}"]
        expected += [_py(commands.set_dual_output_mode, enabled), _py(commands.set_second_output, enabled)]
    for letter, flag in FLAGS.items():
        for enabled in (True, False):
            lines.append(f"WFLAG {letter} {int(enabled)}")
            expected.append(_py(commands.set_flag, flag, enabled))
    lines.append("WFLAG q 1")
    expected.append("INVALID")  # a QFLAG letter this component does not change
    for amps in (0, 10, 20, 29, 30, 35, 150, 151, 160, -1):
        lines.append(f"WMAXD {amps}")
        expected.append(_py(commands.set_max_discharging_current, amps))
    for kind, output in (("ac_output", 1), ("ac_charger", 0)):
        for start, end in ((0, 0), (23, 0), (7, 22), (24, 1), (1, 24), (-1, 5), (12, 12)):
            lines.append(f"WSCHED {output} {start} {end}")
            expected.append(_py(commands.set_schedule, kind, start, end))

    assert tester(lines) == expected


def test_clock_builder_matches_python(tester):
    from datetime import datetime

    moments = [datetime(2026, 11, 14, 22, 5, 9), datetime(2099, 12, 31, 23, 59, 59), datetime(2016, 1, 1, 0, 0, 0)]
    lines = [f"WCLOCK {m.year} {m.month} {m.day} {m.hour} {m.minute} {m.second}" for m in moments]
    assert tester(lines) == [commands.set_clock(m).text for m in moments]
    assert tester(["WCLOCK 2015 1 1 0 0 0", "WCLOCK 2100 1 1 0 0 0", "WCLOCK 2026 13 1 0 0 0"]) == ["INVALID"] * 3


def test_battery_control_texts_are_allowed_and_dangerous_ones_are_not(tester):
    modes = [commands.set_battery_control(m).text for m in commands.BATTERY_CONTROL_MODES]
    assert tester([f"ALLOWED {t}" for t in modes]) == ["1"] * len(modes)
    assert tester(["ALLOWED PBATCD011", "ALLOWED PBATCD010", "ALLOWED PBATCD111", "ALLOWED PBATCD"]) == ["0"] * 4


def test_everything_python_can_build_is_allowed(tester):
    texts = [
        commands.set_output_source_priority(0).text,
        commands.set_output_source_priority(1).text,
        commands.set_charger_source_priority(2).text,
        commands.set_solar_supply_priority(1).text,
        commands.set_max_discharging_current(0).text,
        commands.set_max_discharging_current(150).text,
        commands.set_schedule("ac_output", 23, 0).text,
        commands.set_schedule("ac_charger", 1, 6).text,
        commands.set_dual_output_mode(True).text,
        commands.set_second_output(False).text,
        commands.set_max_charging_current(60, (60,)).text,
        commands.set_max_utility_charging_current(2, (2,)).text,
    ]
    texts += [commands.set_flag(flag, on).text for flag in FLAGS.values() for on in (True, False)]
    texts += [commands.set_battery_voltage(k, s.maximum).text for k, s in commands.VOLTAGE_SETTINGS_24V.items()]
    texts += [commands.set_heep_voltage(k, s.minimum).text for k, s in commands.HEEP_VOLTAGE_SETTINGS_24V.items()]
    texts += [commands.set_integer_setting(k, s.minimum).text for k, s in commands.INTEGER_SETTINGS.items()]
    from datetime import datetime

    texts.append(commands.set_clock(datetime(2026, 11, 14, 22, 5, 9)).text)
    assert tester([f"ALLOWED {t}" for t in texts]) == ["1"] * len(texts)


def test_commands_that_must_never_be_sent_are_refused(tester):
    forbidden = [
        "PF", "PBT00", "PBT02", "PBFT27.0", "PBEQE", "PBEQT030", "PBEQP00", "PGR00", "PGR01", "PEd", "PDd",
        "PEq", "PDq", "POP02", "PCP03", "PVENGUSE02", "PBATCD011", "PBATMAXDISC020", "PBATMAXDISC160",
        "F50", "F60", "RTEY2026", "PTOP01", "PBCV30.0", "PBCV23.7", "PBDV24.2", "PSDV19.9", "PCVV31.0",
        "PDSRS060", "PDDLYT007", "MNCHGC000", "MNCHGC1000", "^S???ACLT24-01", "^S???ACCT01-24", "^S???DAT26",
        "^S???DAT26111422050x", "QPIGS", "QMOD", "HEEP2", "", "PE", "PEaa", "POP0", "POP001", "pEa",
    ]
    assert tester([f"ALLOWED {t}" for t in forbidden if t]) == ["0"] * len([t for t in forbidden if t])


def test_write_answers_match_python(tester):
    def pi30(payload: bytes) -> bytes:
        return payload + crc_bytes(payload) + CR

    answers = [
        pi30(b"(ACK"),
        pi30(b"(NAK"),
        pi30(b"(XYZ"),
        b"(ACK" + b"\x00\x00" + CR,  # wrong CRC
        b"^1" + CR,
        b"^0" + CR,
        b"^1" + crc_bytes(b"^1") + CR,
        b"^0" + crc_bytes(b"^0") + CR,
        b"^1\x00\x00" + CR,  # wrong CRC
        b"^2" + CR,
        b"^" + CR,
        CR,
    ]
    out = tester([f"WANS {a.hex()}" for a in answers])
    for answer, line in zip(answers, out):
        try:
            result = decode_write_answer(answer)
            expected = result if result in ("ACK", "NAK") else "BAD"
        except Exception:
            expected = "BAD"
        assert line == expected, answer


# ---- the control entity tables --------------------------------------------------------------


def test_entity_tables_use_the_python_ranges():
    volt = {s.prefix: s for s in (*commands.VOLTAGE_SETTINGS_24V.values(), *commands.HEEP_VOLTAGE_SETTINGS_24V.values())}
    ints = {s.prefix: s for s in commands.INTEGER_SETTINGS.values()}
    for key, spec in ENT.NUMBERS.items():
        if spec["kind"] == "value":
            ref = volt.get(spec["prefix"]) or ints.get(spec["prefix"])
            assert ref is not None, key
            assert (spec["min"], spec["max"]) == (ref.minimum, ref.maximum), key
            assert spec["step"] == getattr(ref, "step"), key
        elif spec["kind"] == "max_discharge":
            assert spec["max"] == commands.MAX_DISCHARGING_CURRENT_RANGE[1], key
        else:
            assert (spec["min"], spec["max"]) == commands.SCHEDULE_HOURS, key


def test_entity_tables_only_use_allowed_settings(tester):
    texts = []
    for spec in ENT.SWITCHES.values():
        texts += [spec["on"], spec["off"]]
    for spec in ENT.SELECTS.values():
        texts += list(spec["options"].values())
    for spec in ENT.NUMBERS.values():
        if spec["kind"] == "value":
            texts.append(None)  # built from the value below
    texts = [t for t in texts if t]
    assert tester([f"ALLOWED {t}" for t in texts]) == ["1"] * len(texts)

    # every number spec builds a valid text at its minimum and maximum
    lines, expected = [], []
    for key, spec in ENT.NUMBERS.items():
        if spec["kind"] != "value":
            continue
        for value in (spec["min"], spec["max"]):
            lines.append(f"WVAL {spec['prefix']} {value}")
            expected.append(key)
    out = tester(lines)
    assert all(line != "INVALID" for line in out), [e for e, line in zip(expected, out) if line == "INVALID"]


def test_switch_flags_cover_exactly_the_integration_flags():
    letters = {spec["letters"] for spec in ENT.SWITCHES.values() if spec["kind"] == ENT.KIND_FLAG}
    assert letters == set(FLAGS)


def test_select_options_match_the_verified_codes():
    from protocol.h_parsers import SOLAR_SUPPLY_PRIORITIES_VERIFIED
    from protocol.parsers import CHARGER_SOURCE_PRIORITIES_VERIFIED, OUTPUT_SOURCE_PRIORITIES_VERIFIED

    def codes(key, prefix):
        return {int(t[len(prefix):]) for t in ENT.SELECTS[key]["options"].values()}

    assert codes("output_source_priority", "POP") == set(OUTPUT_SOURCE_PRIORITIES_VERIFIED)
    assert codes("charger_source_priority", "PCP") == set(CHARGER_SOURCE_PRIORITIES_VERIFIED)
    assert codes("solar_supply_priority", "PVENGUSE") == set(SOLAR_SUPPLY_PRIORITIES_VERIFIED)
    battery = {t[6:] for t in ENT.SELECTS["battery_control"]["options"].values()}
    assert battery == set(commands.BATTERY_CONTROL_MODES.values())
