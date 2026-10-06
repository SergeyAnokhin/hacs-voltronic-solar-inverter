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
DailyMax = smoothing.DailyMax
DailyEnergy = smoothing.DailyEnergy


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


def test_median_window_ignores_outliers():
    value = SmoothedValue(window=600, statistic="median", relative_threshold=0, absolute_threshold=0)
    for i, sample in enumerate((100, 110, 5000, 120, 105)):
        value.add(float(i * 10), sample)
    assert value.value == 110


def test_max_window():
    peak = SmoothedValue(window=600, statistic="max", relative_threshold=0, absolute_threshold=0)
    for i, sample in enumerate((100, 900, 300)):
        peak.add(float(i * 10), sample)
    assert peak.value == 900
    peak.add(700.0, 300)  # the 900 left the 10 min window
    assert peak.value == 300


def test_daily_max_rises_and_resets_on_new_day():
    from datetime import date

    daily = DailyMax()
    monday, tuesday = date(2026, 10, 5), date(2026, 10, 6)
    assert daily.add(monday, 300.4) is True
    assert daily.add(monday, 200) is False
    assert daily.add(monday, 900.6) is True
    assert daily.value == 901
    assert daily.add(monday, None) is False
    assert daily.add(tuesday, 0) is True  # new day starts from the current sample
    assert daily.value == 0


def test_daily_max_restore():
    from datetime import date

    daily = DailyMax()
    daily.restore(date(2026, 10, 5), 1234.0)
    assert daily.add(date(2026, 10, 5), 1000) is False
    assert daily.value == 1234


def test_daily_max_keeps_time_of_first_maximum():
    from datetime import date, datetime

    daily = DailyMax()
    monday = date(2026, 10, 5)
    t1, t2, t3 = (datetime(2026, 10, 5, h) for h in (9, 12, 13))
    daily.add(monday, 10, t1)
    assert daily.add(monday, 25, t2) is True
    assert daily.add(monday, 25, t3) is False  # equal value: time of the first one stays
    assert (daily.value, daily.at) == (25, t2)
    daily.restore(monday, 30, t3)
    assert (daily.value, daily.at) == (30, t3)


def test_daily_energy_is_the_trapezoidal_integral():
    from datetime import date

    monday = date(2026, 10, 5)
    energy = DailyEnergy(max_gap=30, step=0.05, heartbeat=600)
    assert energy.add(monday, 0, 1000) is True  # first sample: 0 kWh published
    assert energy.value == 0
    # 1000 W -> 2000 W over 36 s: 1500 W x 0.01 h = 0.015 kWh, below the step
    assert energy.add(monday, 36, 2000) is False
    assert energy.value == 0
    for t in range(46, 136, 10):  # 90 s at 2000 W = 0.05 kWh more: 0.065 kWh in total
        energy.add(monday, t, 2000)
    assert energy.value == 0.05  # written when it crossed the step, not on every 0.01


def test_daily_energy_heartbeat_gap_and_new_day():
    from datetime import date

    monday, tuesday = date(2026, 10, 5), date(2026, 10, 6)
    energy = DailyEnergy(max_gap=30, step=0.05, heartbeat=600)
    energy.add(monday, 0, 36)
    for t in range(10, 600, 10):  # 36 W: 0.01 kWh every 1000 s
        assert energy.add(monday, t, 36) is False
    assert energy.add(monday, 600, 36) is True  # heartbeat: written after 10 min
    assert energy.value == 0.01
    energy.add(monday, 1000, 36000)  # 400 s gap > max_gap: nothing added
    assert energy.value == 0.01
    assert energy.add(monday, 1010, 36000) is True  # 0.1 kWh in 10 s
    assert energy.value == 0.11
    assert energy.add(monday, 1011, None) is False  # missing sample breaks the interval
    assert energy.add(tuesday, 1020, 360) is True  # new day starts from 0
    assert energy.value == 0


def test_daily_energy_can_go_negative_and_restores():
    from datetime import date

    monday = date(2026, 10, 5)
    energy = DailyEnergy(max_gap=30, step=0.05, heartbeat=600)
    energy.restore(monday, 1.23)
    assert energy.add(monday, 0, -3600) is False  # restored value is already written
    assert energy.add(monday, 30, -3600) is False  # -0.03 kWh, below the step
    assert energy.add(monday, 60, -3600) is True
    assert energy.value == 1.17
