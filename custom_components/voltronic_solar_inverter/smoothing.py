"""Moving average with a publish threshold, for "smoothed" sensors (no HA imports).

The live sensor shows every sample; the smoothed sensor shows the mean of the
last ``window`` seconds but only *publishes* a new value (= a new state row in
the recorder) when it moved significantly, dropped to zero, or after
``heartbeat`` seconds with any change.
"""

from __future__ import annotations

from collections import deque


class SmoothedValue:
    """Time-window mean that changes its published value only on significant moves."""

    def __init__(
        self,
        *,
        window: float = 60.0,
        relative_threshold: float = 0.10,
        absolute_threshold: float = 20.0,
        heartbeat: float = 600.0,
        precision: int = 0,
    ) -> None:
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
        mean = sum(v for _, v in self._samples) / len(self._samples)
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
