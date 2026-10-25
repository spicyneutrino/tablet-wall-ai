"""Camera-clock, rolling-shutter and onset-interval arithmetic.

All timestamps are seconds on the camera's monotonic clock. A frame timestamp
is converted to the start of that frame's exposure using ``timestamp_basis``;
the default is ``exposure_start``. The sample row is exposed at

    frame_exposure_start + readout_fraction(point) * readout_duration

and stays exposed for ``exposure_us``. A panel's onset interval uses the last
frame that still showed the baseline and the first frame that showed the
target. The interval is deliberately conservative: it allows a blended
exposure to be classified either way.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Iterable, Sequence

from .model import Camera, Capture, Frame, TIMESTAMP_BASES


def exposure_start_s(timestamp_s: float, basis: str, exposure_us: float) -> float:
    if basis not in TIMESTAMP_BASES:
        raise ValueError(f"timestamp_basis must be one of {TIMESTAMP_BASES}")
    if basis == "exposure_start":
        return float(timestamp_s)
    if basis == "exposure_centre":
        return float(timestamp_s) - exposure_us / 2_000_000.0
    return float(timestamp_s) - exposure_us / 1_000_000.0


def frame_start_s(frame: Frame, camera: Camera, basis: str) -> float:
    return exposure_start_s(frame.timestamp_s, basis, camera.exposure_us)


def map_to_sensor(x: float, y: float, camera: Camera) -> tuple[float, float]:
    """Map a delivered-frame point to sensor coordinates.

    ``orientation_deg`` is the clockwise rotation from sensor to delivered
    frame. The inverse rotation is applied here before the readout fraction is
    computed.
    """
    orientation = camera.orientation_deg
    if orientation == 0:
        return x, y
    if orientation == 90:
        return y, camera.sensor_height - 1.0 - x
    if orientation == 180:
        return camera.sensor_width - 1.0 - x, camera.sensor_height - 1.0 - y
    if orientation == 270:
        return camera.sensor_width - 1.0 - y, x
    raise ValueError("orientation must be 0, 90, 180 or 270 degrees")


def sensor_to_delivered(sx: float, sy: float, camera: Camera) -> tuple[float, float]:
    """Inverse of :func:`map_to_sensor` for sensor-space ROI files."""
    orientation = camera.orientation_deg
    if orientation == 0:
        return sx, sy
    if orientation == 90:
        return camera.sensor_height - 1.0 - sy, sx
    if orientation == 180:
        return camera.sensor_width - 1.0 - sx, camera.sensor_height - 1.0 - sy
    if orientation == 270:
        return sy, camera.sensor_width - 1.0 - sx
    raise ValueError("orientation must be 0, 90, 180 or 270 degrees")


def readout_fraction(x: float, y: float, camera: Camera) -> float:
    """Fraction of the full readout elapsed when this sensor point is read."""
    sx, sy = map_to_sensor(x, y, camera)
    direction = camera.readout_direction
    if direction == "top-to-bottom":
        span = max(camera.sensor_height - 1.0, 1.0)
        value = sy / span
    elif direction == "bottom-to-top":
        span = max(camera.sensor_height - 1.0, 1.0)
        value = (camera.sensor_height - 1.0 - sy) / span
    elif direction == "left-to-right":
        span = max(camera.sensor_width - 1.0, 1.0)
        value = sx / span
    elif direction == "right-to-left":
        span = max(camera.sensor_width - 1.0, 1.0)
        value = (camera.sensor_width - 1.0 - sx) / span
    else:
        raise ValueError("readout_direction is not recognised")
    return min(max(value, 0.0), 1.0)


def readout_offset_s(x: float, y: float, camera: Camera) -> float:
    return readout_fraction(x, y, camera) * camera.readout_s


@dataclass(frozen=True)
class OnsetInterval:
    """Conservative onset interval plus a narrower best-estimate point."""

    lower_s: float
    point_s: float
    upper_s: float
    width_s: float
    consistent: bool

    @property
    def width_ms(self) -> float:
        return self.width_s * 1000.0


def panel_onset_interval(
    previous_start_s: float,
    onset_start_s: float,
    transition_points: Sequence[tuple[float, float]],
    camera: Camera,
) -> OnsetInterval:
    """Bound a visible transition from two consecutive observations.

    For each point that was baseline in the previous frame and target in the
    onset frame:

    * previous frame row start is a weak lower bound on the change time;
    * onset frame row end is a weak upper bound.

    The conservative interval is ``[max(previous starts), min(onset ends)]``.
    The point estimate uses the gap between the previous exposure end and the
    onset exposure start when those do not overlap; otherwise it falls back to
    the conservative midpoint. The point estimate is never used as a bound.
    """
    if not transition_points:
        raise ValueError("an onset interval needs at least one transition point")

    previous_starts: list[float] = []
    previous_ends: list[float] = []
    onset_starts: list[float] = []
    onset_ends: list[float] = []
    exposure = camera.exposure_s
    for x, y in transition_points:
        offset = readout_offset_s(x, y, camera)
        previous_starts.append(previous_start_s + offset)
        previous_ends.append(previous_start_s + offset + exposure)
        onset_starts.append(onset_start_s + offset)
        onset_ends.append(onset_start_s + offset + exposure)

    lower = max(previous_starts)
    upper = min(onset_ends)
    consistent = lower <= upper
    gap_lower = max(previous_ends)
    gap_upper = min(onset_starts)
    if gap_lower <= gap_upper:
        point = (gap_lower + gap_upper) / 2.0
    else:
        point = (lower + upper) / 2.0
    return OnsetInterval(
        lower_s=lower,
        point_s=point,
        upper_s=upper,
        width_s=max(upper - lower, 0.0),
        consistent=consistent,
    )


@dataclass(frozen=True)
class FrameIntervalStats:
    source: str
    count: int
    median_s: float
    p95_s: float
    minimum_s: float
    maximum_s: float
    nominal_fps: float | None

    def as_dict(self) -> dict[str, float | int | str | None]:
        return {
            "source": self.source,
            "count": self.count,
            "median_ms": round(self.median_s * 1000.0, 3),
            "p95_ms": round(self.p95_s * 1000.0, 3),
            "minimum_ms": round(self.minimum_s * 1000.0, 3),
            "maximum_ms": round(self.maximum_s * 1000.0, 3),
            "nominal_fps_metadata_only": self.nominal_fps,
        }


def percentile(values: Sequence[float], q: float) -> float | None:
    """Linear-interpolation percentile, matching common percentile defaults."""
    if not values:
        return None
    if q < 0 or q > 100:
        raise ValueError("percentile must be between 0 and 100")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * (q / 100.0)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return ordered[low] * (1.0 - fraction) + ordered[high] * fraction


def frame_interval_stats(capture: Capture, timing_source: str = "manifest") -> FrameIntervalStats:
    """Use actual frame timestamps. Nominal fps is never timing evidence."""
    starts = sorted(
        frame_start_s(frame, capture.camera, capture.timestamp_basis)
        for frame in capture.frames
    )
    if len(starts) < 2:
        raise ValueError("at least two frames are needed to measure frame timing")
    deltas = [
        later - earlier
        for earlier, later in zip(starts, starts[1:])
        if later > earlier
    ]
    if not deltas:
        raise ValueError("frame timestamps do not advance")
    return FrameIntervalStats(
        source=timing_source,
        count=len(starts),
        median_s=statistics.median(deltas),
        p95_s=percentile(deltas, 95) or statistics.median(deltas),
        minimum_s=min(deltas),
        maximum_s=max(deltas),
        nominal_fps=capture.camera.nominal_fps,
    )


def _format_range(indices: Iterable[int]) -> str:
    ordered = sorted(set(indices))
    if not ordered:
        return ""
    if len(ordered) == 1:
        return str(ordered[0])
    if ordered == list(range(ordered[0], ordered[-1] + 1)):
        return f"{ordered[0]}-{ordered[-1]}"
    return ",".join(str(index) for index in ordered)


def capture_unobserved_intervals(
    capture: Capture,
    config_gap_factor: float = 1.5,
) -> list[dict[str, object]]:
    """Frame gaps, declared drops and duplicate timestamps with no observation."""
    frames = sorted(capture.frames, key=lambda item: item.index)
    intervals: list[dict[str, object]] = []
    if len(frames) < 2:
        return intervals
    starts = [frame_start_s(frame, capture.camera, capture.timestamp_basis) for frame in frames]
    positive = [b - a for a, b in zip(starts, starts[1:]) if b > a]
    median = statistics.median(positive) if positive else None

    for previous, current, previous_start, current_start in zip(
        frames, frames[1:], starts, starts[1:]
    ):
        index_gap = current.index - previous.index
        if index_gap > 1:
            missing = list(range(previous.index + 1, current.index))
            declared = set(missing).issubset(capture.dropped_frames)
            intervals.append({
                "start_s": round(previous_start, 6),
                "end_s": round(current_start, 6),
                "reason": f"missing frame indices {_format_range(missing)}",
                "declared_dropped": declared,
                "event_id": None,
            })
        elif current_start < previous_start:
            intervals.append({
                "start_s": round(current_start, 6),
                "end_s": round(previous_start, 6),
                "reason": "frame timestamps run backwards",
                "declared_dropped": False,
                "event_id": None,
            })
        elif current_start == previous_start:
            intervals.append({
                "start_s": round(previous_start, 6),
                "end_s": round(current_start, 6),
                "reason": "duplicate frame timestamp",
                "declared_dropped": False,
                "event_id": None,
            })
        elif median is not None and index_gap == 1:
            delta = current_start - previous_start
            if delta > config_gap_factor * median:
                intervals.append({
                    "start_s": round(previous_start, 6),
                    "end_s": round(current_start, 6),
                    "reason": (
                        f"frame timing gap {delta * 1000.0:.1f} ms vs "
                        f"median {median * 1000.0:.1f} ms"
                    ),
                    "declared_dropped": False,
                    "event_id": None,
                })
    return intervals
