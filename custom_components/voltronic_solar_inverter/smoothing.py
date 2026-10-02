"""Moving average with a publish threshold, for "smoothed" sensors (no HA imports).

The live sensor shows every sample; the smoothed sensor shows the mean of the
last ``window`` seconds but only *publishes* a new value (= a new state row in
the recorder) when it moved significantly, dropped to zero, or after
``heartbeat`` seconds with any change.
"""

from __future__ import annotations

from collections import deque
from datetime import date
from statistics import mean as _mean, median as _median

STATISTICS = {"mean": _mean, "median": _median, "max": max}


class DailyMax:
    """Highest sample of the current day (rounded to whole units); starts over on a new day."""

    def __init__(self) -> None:
        self.value: int | None = None
        self.day: date | None = None

    def restore(self, day: date, value: float) -> None:
        """Take over a value stored earlier the same day (after a restart)."""
        self.day, self.value = day, round(value)

    def add(self, day: date, sample: float | None) -> bool:
        """Add a sample taken on ``day``; True if the maximum changed."""
        if sample is None:
            return False
        sample = round(sample)
        if day != self.day:
            self.day, self.value = day, sample
            return True
        if self.value is None or sample > self.value:
            self.value = sample
            return True
        return False


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
        self._day: date | None = None
        self._published_at: float | None = None

    def add(self, now: float, sample: float | None, day: date | None = None) -> bool:
        """Add a sample taken at monotonic time ``now``; True if the published value changed.

        With ``day`` (use ``window=inf``) the statistic covers the current day only:
        a new day drops all samples and publishes afresh.
        """
        if sample is None:
            return False
        if day != self._day:
            self._day = day
            if day is not None and self._samples:
                self._samples.clear()
                self.value = None
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
