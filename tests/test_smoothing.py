"""SmoothedValue: moving average that publishes only significant changes."""

import importlib.util
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "voltronic_solar_inverter"
    / "smoothing.py"
)
_spec = importlib.util.spec_from_file_location("smoothing", _PATH)
smoothing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoothing)
SmoothedValue = smoothing.SmoothedValue


def make() -> SmoothedValue:
    return SmoothedValue(window=60, relative_threshold=0.10, absolute_threshold=20, heartbeat=600)


def test_first_sample_is_published():
    s = make()
    assert s.add(0, 1000) is True
    assert s.value == 1000


def test_none_sample_is_ignored():
    s = make()
    assert s.add(0, None) is False
    assert s.value is None


def test_small_changes_are_not_published():
    s = make()
    s.add(0, 1000)
    for t, v in ((10, 1040), (20, 980), (30, 1030)):  # mean stays within 10 %
        assert s.add(t, v) is False
    assert s.value == 1000


def test_significant_change_is_published():
    s = make()
    s.add(0, 1000)
    # Clouds: the mean falls by more than 10 % within a few samples.
    published = [s.add(t, 300) for t in (10, 20)]
    assert published == [True, True]  # 650 (-35 %), then 533 (-18 %)
    assert s.value == 533


def test_absolute_threshold_for_low_power():
    s = make()
    s.add(0, 50)
    assert s.add(10, 60) is False  # mean 55: +10 % but only 5 W
    assert s.add(20, 120) is True  # mean 77: +27 W
    assert s.value == 77


def test_drop_to_zero_is_always_published():
    s = make()
    s.add(0, 15)
    assert s.add(61, 0) is True  # old sample left the window, mean 0
    assert s.value == 0


def test_window_drops_old_samples():
    s = make()
    s.add(0, 1000)
    assert s.add(100, 500) is True  # 1000 left the 60 s window
    assert s.value == 500


def test_heartbeat_publishes_small_drift():
    s = make()
    s.add(0, 1000)
    assert s.add(300, 1050) is False
    assert s.add(601, 1050) is True  # 10 min since the last publish
    assert s.value == 1050


def test_unchanged_mean_never_publishes():
    s = make()
    s.add(0, 0)
    assert all(s.add(t, 0) is False for t in range(10, 2000, 10))
