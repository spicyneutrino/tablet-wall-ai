"""Server monotonic time, clock epoch, suspend detection and offset samples.

All timed scheduling uses a monotonic millisecond origin. UTC is for logs and
durable metadata only. A suspend is detected as the difference between the
boot-time clock (which counts suspend on Linux) and the monotonic clock
(which does not); when that gap is real, the epoch changes and every pending
preparation must be discarded.

The four-timestamp estimate is the NTP relation:

    offset = ((s1 - c0) + (s2 - c3)) / 2
    rtt    = (c3 - c0) - (s2 - s1)

A sample with a negative or non-finite RTT is invalid, not a zero-delay
miracle. Uncertainty is half the RTT; it excludes timer, decoder, compositor
and panel delay and is not an optical-skew claim.
"""

import math
import time
import uuid
from dataclasses import dataclass
from typing import Any

SUSPEND_THRESHOLD_MS = 2000
MAX_SAMPLE_AGE_MS = 15000
MAX_UNCERTAINTY_MS = 25


def _now_pair() -> tuple[float, float]:
    """``(boottime, monotonic)`` in milliseconds."""
    boot = time.clock_gettime_ns(time.CLOCK_BOOTTIME) / 1_000_000
    mono = time.monotonic_ns() / 1_000_000
    return boot, mono


@dataclass(frozen=True)
class Estimate:
    offset_ms: float
    rtt_ms: float
    uncertainty_ms: float

    def as_frame(self) -> dict[str, float]:
        return {
            "offset_ms": round(self.offset_ms, 3),
            "rtt_ms": round(self.rtt_ms, 3),
            "uncertainty_ms": round(self.uncertainty_ms, 3),
        }


def estimate(c0: float, s1: float, s2: float, c3: float) -> Estimate | None:
    """One valid offset sample, or None when the timestamps are impossible."""
    values = (c0, s1, s2, c3)
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
        return None
    if c3 < c0 or s2 < s1:
        return None
    rtt = (c3 - c0) - (s2 - s1)
    if rtt < 0 or rtt > 60_000:
        return None
    offset = ((s1 - c0) + (s2 - c3)) / 2
    return Estimate(offset_ms=offset, rtt_ms=rtt, uncertainty_ms=rtt / 2)


def best_sample(samples: list[dict[str, Any]], now_ms: float) -> dict[str, Any] | None:
    """The lowest-delay valid sample that is still fresh."""
    valid = []
    for sample in samples:
        try:
            age = now_ms - float(sample["server_ms"])
            rtt = float(sample["rtt_ms"])
            uncertainty = float(sample["uncertainty_ms"])
            offset = float(sample["offset_ms"])
        except (KeyError, TypeError, ValueError):
            continue
        if not all(math.isfinite(value) for value in (age, rtt, uncertainty, offset)):
            continue
        if age < 0 or age > MAX_SAMPLE_AGE_MS:
            continue
        if rtt < 0 or uncertainty < 0 or uncertainty > MAX_UNCERTAINTY_MS:
            continue
        valid.append({
            "offset_ms": offset, "rtt_ms": rtt,
            "uncertainty_ms": uncertainty, "age_ms": age,
            "server_ms": float(sample["server_ms"]),
        })
    if not valid:
        return None
    chosen = min(valid, key=lambda sample: (sample["rtt_ms"], sample["age_ms"]))
    return {**chosen, "fresh": chosen["age_ms"] <= MAX_SAMPLE_AGE_MS}


class ServerClock:
    """Process-local monotonic origin plus an epoch that survives no restart."""

    def __init__(self, sample=_now_pair) -> None:
        self._sample = sample
        self.epoch = uuid.uuid4().hex[:8]
        self._last_boot, self._last_mono = sample()
        self.suspended = False

    def now_ms(self) -> float:
        return time.monotonic_ns() / 1_000_000

    def check_suspend(self) -> bool:
        """Advance the epoch when the host slept; return whether it did."""
        boot, mono = self._sample()
        boot_delta = boot - self._last_boot
        mono_delta = mono - self._last_mono
        self._last_boot, self._last_mono = boot, mono
        if boot_delta - mono_delta > SUSPEND_THRESHOLD_MS:
            self.epoch = uuid.uuid4().hex[:8]
            self.suspended = True
            return True
        return False

    def accept_sample(
        self, c0: float, c3: float, *, received_ms: float, sent_ms: float
    ) -> Estimate | None:
        """Estimate from the client's two timestamps and the server's two."""
        return estimate(c0, received_ms, sent_ms, c3)
