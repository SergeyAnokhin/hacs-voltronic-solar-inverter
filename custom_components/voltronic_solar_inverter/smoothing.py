"""Moving average with a publish threshold, for "smoothed" sensors (no HA imports).

The live sensor shows every sample; the smoothed sensor shows the mean of the
last ``window`` seconds but only *publishes* a new value (= a new state row in
the recorder) when it moved significantly, dropped to zero, or after
``heartbeat`` seconds with any change.
"""

from __future__ import annotations

from collections import deque
from datetime import date, datetime
from statistics import mean as _mean, median as _median

STATISTICS = {"mean": _mean, "median": _median, "max": max}


class DailyMax:
    """Highest sample of the current day (rounded to whole units); starts over on a new day.

    ``at`` is when the maximum was first reached (the time passed with that sample).
    """

    def __init__(self) -> None:
        self.value: int | None = None
        self.day: date | None = None
        self.at: datetime | None = None

    def restore(self, day: date, value: float, at: datetime | None = None) -> None:
        """Take over a value stored earlier the same day (after a restart)."""
        self.day, self.value, self.at = day, round(value), at

    def add(self, day: date, sample: float | None, at: datetime | None = None) -> bool:
        """Add a sample taken on ``day`` (at ``at``); True if the maximum changed."""
        if sample is None:
            return False
        sample = round(sample)
        if day != self.day or self.value is None or sample > self.value:
            self.day, self.value, self.at = day, sample, at
            return True
        return False


class DailyEnergy:
    """Energy since local midnight (kWh) from power samples (W); starts over on a new day.

    Integrates every sample with the trapezoidal rule, the default method of
    Home Assistant's Riemann sum integral helper. A gap longer than ``max_gap``
    seconds (lost connection, restart) adds nothing. The published (recorded)
    value changes only when it moved by ``step`` kWh, after ``heartbeat`` seconds
    with any change, or on a new day.
    """

    def __init__(
        self, *, max_gap: float, step: float = 0.05, heartbeat: float = 600.0, precision: int = 2
    ) -> None:
        self.max_gap = max_gap
        self.step = step
        self.heartbeat = heartbeat
        self.precision = precision
        self.day: date | None = None
        self.value: float | None = None  # published value
        self._total = 0.0  # kWh, not rounded
        self._last: tuple[float, float] | None = None  # (monotonic time, W)
        self._published_at: float | None = None

    def restore(self, day: date, value: float) -> None:
        """Take over a value stored earlier the same day (after a restart)."""
        self.day, self.value, self._total = day, value, value

    def add(self, day: date, now: float, power: float | None) -> bool:
        """Add a sample taken on ``day`` at monotonic time ``now``; True if the published value changed."""
        if power is None:
            self._last = None
            return False
        new_day = day != self.day
        if new_day:
            self.day, self._total = day, 0.0
        if self._last is not None and 0 < now - self._last[0] <= self.max_gap:
            self._total += (self._last[1] + power) / 2 * (now - self._last[0]) / 3_600_000
        self._last = (now, float(power))
        value = round(self._total, self.precision)
        if not new_day and self.value is not None and self._published_at is not None:
            if value == self.value:
                return False
            if abs(value - self.value) < self.step and now - self._published_at < self.heartbeat:
                return False
        if not new_day and value == self.value:
            self._published_at = now  # restored value, nothing new to write
            return False
        self.value = value
        self._published_at = now
        return True


class SmoothedValue:
    """Time-window mean (or median) that changes its published value only on significant moves."""

    def __init__(
        self,
        *,
        window: float = 60.0,
        relative_threshold: float = 0.10,
        absolute_threshold: float = 20.0,
        heartbeat: float = 600.0,
        precision: int = 0,
        statistic: str = "mean",
    ) -> None:
        self._statistic = STATISTICS[statistic]
        self.window = window
        self.relative_threshold = relative_threshold
        self.absolute_threshold = absolute_threshold
        self.heartbeat = heartbeat
        self.precision = precision
        self._samples: deque[tuple[float, float]] = deque()
        self.value: float | None = None  # published value
        self._published_at: float | None = None

    def add(self, now: float, sample: float | None) -> bool:
        """Add a sample taken at monotonic time ``now``; True if the published value changed."""
        if sample is None:
            return False
        self._samples.append((now, float(sample)))
        while self._samples and self._samples[0][0] < now - self.window:
            self._samples.popleft()
        mean = self._statistic(v for _, v in self._samples)
        mean = round(mean, self.precision)
        if self.precision == 0:
            mean = int(mean)
        if self.value is not None and self._published_at is not None:
            delta = abs(mean - self.value)
            if delta == 0:
                return False
            significant = delta >= max(self.relative_threshold * abs(self.value), self.absolute_threshold)
            to_zero = mean == 0
            stale = now - self._published_at >= self.heartbeat
            if not (significant or to_zero or stale):
                return False
        self.value = mean
        self._published_at = now
        return True
