"""Visible-onset detection over sampled panel ROIs."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Iterable, Sequence

from PIL import Image, ImageStat

from tools.validation.evidence import iso_now

from . import TOOL_VERSION
from .inputs import validate_panel_coverage
from .model import (
    Analysis,
    AnalysisConfig,
    Camera,
    Capture,
    Event,
    EventResult,
    Frame,
    PanelObservation,
    PanelROI,
    RGB,
    Region,
    ROISet,
)
from .timing import (
    capture_unobserved_intervals,
    frame_start_s,
    panel_onset_interval,
    readout_offset_s,
)
from .metrics import build_metrics
from .video import ToolUnavailable, read_source_frame


@dataclass(frozen=True)
class FrameSamples:
    frame: Frame
    start_s: float
    panels: dict[str, tuple[RGB, ...]]
    noise: dict[str, tuple[RGB, ...] | None]


@dataclass(frozen=True)
class _FrameStats:
    samples: FrameSamples
    target_fraction: float
    changed_fraction: float
    target_distances: tuple[float, ...]
    confirmed: tuple[bool, ...]


def _distance(colour: Sequence[float], target: Sequence[float]) -> float:
    return math.sqrt(
        sum((float(a) - float(b)) ** 2 for a, b in zip(colour, target)) / 3.0
    )


def _sample_region(image: Image.Image, selected: Region) -> tuple[RGB, ...]:
    colours: list[RGB] = []
    width, height = image.size
    radius = selected.sample_radius
    for x, y in selected.sample_points:
        centre_x = int(round(x))
        centre_y = int(round(y))
        left = max(0, centre_x - radius)
        top = max(0, centre_y - radius)
        right = min(width, centre_x + radius + 1)
        bottom = min(height, centre_y + radius + 1)
        if right <= left or bottom <= top:
            raise ValueError(f"sample point ({x}, {y}) is outside the frame")
        crop = image.crop((left, top, right, bottom))
        mean = ImageStat.Stat(crop).mean
        colours.append((float(mean[0]), float(mean[1]), float(mean[2])))
    return tuple(colours)


def load_samples(
    capture: Capture,
    rois: ROISet,
    *,
    frame_errors: list[dict[str, object]] | None = None,
) -> dict[int, FrameSamples]:
    """Decode every frame once and reduce each ROI to mean probe colours."""
    samples: dict[int, FrameSamples] = {}
    errors = frame_errors if frame_errors is not None else []
    expected_size = (capture.camera.width, capture.camera.height)
    for frame in capture.frames:
        if frame.path is None:
            errors.append({"frame_index": frame.index, "error": "frame has no path"})
            continue
        try:
            with Image.open(frame.path) as image:
                image = image.convert("RGB")
                if image.size != expected_size:
                    raise ValueError(
                        f"frame is {image.size[0]}x{image.size[1]}, manifest says "
                        f"{expected_size[0]}x{expected_size[1]}"
                    )
                panel_colours = {
                    panel_id: _sample_region(image, panel.region)
                    for panel_id, panel in rois.panels.items()
                }
                noise_colours = {
                    panel_id: (
                        _sample_region(image, panel.noise_region)
                        if panel.noise_region is not None
                        else None
                    )
                    for panel_id, panel in rois.panels.items()
                }
        except (OSError, ValueError) as error:
            errors.append({
                "frame_index": frame.index,
                "path": str(frame.path),
                "error": str(error),
            })
            continue
        samples[frame.index] = FrameSamples(
            frame=frame,
            start_s=frame_start_s(frame, capture.camera, capture.timestamp_basis),
            panels=panel_colours,
            noise=noise_colours,
        )
    return samples


def _median(values: Sequence[float]) -> float:
    return float(statistics.median(values))


def _baseline_for_panel(
    panel_id: str,
    baseline_samples: Sequence[FrameSamples],
) -> tuple[tuple[RGB, ...], float, float]:
    if not baseline_samples:
        raise ValueError("no baseline")
    count = len(baseline_samples[0].panels[panel_id])
    baseline: list[RGB] = []
    for point in range(count):
        colours = [sample.panels[panel_id][point] for sample in baseline_samples]
        baseline.append((
            _median([colour[0] for colour in colours]),
            _median([colour[1] for colour in colours]),
            _median([colour[2] for colour in colours]),
        ))

    squared = 0.0
    entries = 0
    for sample in baseline_samples:
        for point, colour in enumerate(sample.panels[panel_id]):
            for channel in range(3):
                squared += (colour[channel] - baseline[point][channel]) ** 2
                entries += 1
    temporal_noise = math.sqrt(squared / entries) if entries else 0.0

    reference_colours: list[RGB] = []
    for sample in baseline_samples:
        reference_colours.extend(sample.noise.get(panel_id) or ())
    if reference_colours:
        channel_means = [
            sum(colour[channel] for colour in reference_colours) / len(reference_colours)
            for channel in range(3)
        ]
        noise_squared = 0.0
        entries = 0
        for colour in reference_colours:
            for channel in range(3):
                noise_squared += (colour[channel] - channel_means[channel]) ** 2
                entries += 1
        reference_noise = math.sqrt(noise_squared / entries) if entries else 0.0
    else:
        reference_noise = 0.0
    return tuple(baseline), temporal_noise, reference_noise


def _frame_stats(
    sample: FrameSamples,
    panel_id: str,
    baseline: Sequence[RGB],
    target: RGB,
    tolerance: float,
    change_threshold: float,
) -> _FrameStats:
    distances: list[float] = []
    changed: list[bool] = []
    matches: list[bool] = []
    for point, colour in enumerate(sample.panels[panel_id]):
        target_distance = _distance(colour, target)
        baseline_distance = _distance(colour, baseline[point])
        distances.append(target_distance)
        changed.append(baseline_distance >= change_threshold)
        matches.append(target_distance <= tolerance)
    confirmed = tuple(match and change for match, change in zip(matches, changed))
    count = len(confirmed)
    return _FrameStats(
        samples=sample,
        target_fraction=sum(confirmed) / count if count else 0.0,
        changed_fraction=sum(changed) / count if count else 0.0,
        target_distances=tuple(distances),
        confirmed=confirmed,
    )


def _confidence(
    target_fraction: float,
    min_fraction: float,
    distances: Sequence[float],
    tolerance: float,
    noise: float,
    width_s: float,
    max_baseline_noise: float,
) -> float:
    margin = max(0.0, min(1.0, (target_fraction - min_fraction) / max(1.0 - min_fraction, 1e-9)))
    if distances:
        colour = sum(
            max(0.0, min(1.0, (tolerance - value) / max(tolerance, 1e-9)))
            for value in distances
        ) / len(distances)
    else:
        colour = 0.0
    noise_score = max(0.0, min(1.0, 1.0 - noise / max(max_baseline_noise, 1e-9)))
    timing_score = max(0.0, min(1.0, 1.0 - width_s / 0.020))
    return round(0.35 * margin + 0.30 * colour + 0.20 * noise_score + 0.15 * timing_score, 3)


def _unobserved_panel(panel_id: str, reason: str, camera: Camera, roi: PanelROI) -> PanelObservation:
    offsets = [
        readout_offset_s(x, y, camera) * 1000.0
        for x, y in roi.region.sample_points
    ]
    return PanelObservation(
        panel_id=panel_id,
        status="unobserved",
        reason=reason,
        readout_offset_min_ms=min(offsets),
        readout_offset_max_ms=max(offsets),
    )


def _analyse_panel(
    event: Event,
    panel: PanelROI,
    *,
    ordered_samples: Sequence[FrameSamples],
    baseline_samples: Sequence[FrameSamples],
    candidate_samples: Sequence[FrameSamples],
    camera: Camera,
    config: AnalysisConfig,
) -> PanelObservation:
    panel_id = panel.panel_id
    offsets = [
        readout_offset_s(x, y, camera) * 1000.0
        for x, y in panel.region.sample_points
    ]
    base = dict(
        panel_id=panel_id,
        readout_offset_min_ms=min(offsets),
        readout_offset_max_ms=max(offsets),
    )
    if len(baseline_samples) < config.min_baseline_frames:
        return PanelObservation(
            status="unobserved",
            reason=(
                f"only {len(baseline_samples)} baseline frames before the search "
                f"window (need {config.min_baseline_frames})"
            ),
            **base,
        )
    if not candidate_samples:
        return PanelObservation(
            status="unobserved",
            reason="no frames inside the declared search window",
            **base,
        )

    baseline, temporal_noise, reference_noise = _baseline_for_panel(panel_id, baseline_samples)
    noise = max(temporal_noise, reference_noise, 0.5)
    if noise > config.max_baseline_noise:
        return PanelObservation(
            status="ambiguous",
            noise_rms=round(noise, 3),
            reason=(
                f"baseline noise {noise:.1f} exceeds the configured "
                f"{config.max_baseline_noise:.1f}; onset cannot be separated"
            ),
            **base,
        )

    tolerance = event.target_tolerance + 2.0 * noise
    change_threshold = max(config.min_change, 3.0 * noise)
    baseline_target_fraction = sum(
        1 for colour in baseline if _distance(colour, event.target_rgb) <= tolerance
    ) / len(baseline)
    if baseline_target_fraction >= event.min_target_fraction:
        return PanelObservation(
            status="ambiguous",
            target_fraction=round(baseline_target_fraction, 3),
            changed_fraction=0.0,
            noise_rms=round(noise, 3),
            reason=(
                "expected target was already present across the baseline; "
                "no visible transition exists to time"
            ),
            **base,
        )

    stats = [
        _frame_stats(
            sample,
            panel_id,
            baseline,
            event.target_rgb,
            tolerance,
            change_threshold,
        )
        for sample in candidate_samples
    ]
    confirm = max(1, config.confirm_frames)
    onset_index: int | None = None
    for index in range(len(stats) - confirm + 1):
        window = stats[index:index + confirm]
        if len(window) == confirm and all(
            item.target_fraction >= event.min_target_fraction for item in window
        ):
            onset_index = index
            break

    if onset_index is None:
        max_target = max(item.target_fraction for item in stats)
        max_changed = max(item.changed_fraction for item in stats)
        if max_target >= config.partial_fraction:
            return PanelObservation(
                status="partial",
                target_fraction=round(max_target, 3),
                changed_fraction=round(max_changed, 3),
                noise_rms=round(noise, 3),
                reason=(
                    f"only {max_target:.0%} of probe points reached the target "
                    f"(need {event.min_target_fraction:.0%})"
                ),
                **base,
            )
        if max_changed >= config.min_changed_fraction:
            return PanelObservation(
                status="wrong-target",
                target_fraction=round(max_target, 3),
                changed_fraction=round(max_changed, 3),
                noise_rms=round(noise, 3),
                reason=(
                    f"{max_changed:.0%} of probe points changed but did not match "
                    "the expected target colour"
                ),
                **base,
            )
        if max_changed >= config.partial_fraction or max_target > 0.0:
            return PanelObservation(
                status="ambiguous",
                target_fraction=round(max_target, 3),
                changed_fraction=round(max_changed, 3),
                noise_rms=round(noise, 3),
                reason="weak or inconsistent colour change below the detection thresholds",
                **base,
            )
        return PanelObservation(
            status="missing",
            target_fraction=round(max_target, 3),
            changed_fraction=round(max_changed, 3),
            noise_rms=round(noise, 3),
            reason="no visible change towards the expected target inside the window",
            **base,
        )

    onset = stats[onset_index]
    previous = _previous_sample(ordered_samples, onset.samples.frame.index)
    if previous is None:
        return PanelObservation(
            status="ambiguous",
            target_fraction=round(onset.target_fraction, 3),
            changed_fraction=round(onset.changed_fraction, 3),
            noise_rms=round(noise, 3),
            onset_frame=onset.samples.frame.index,
            reason="no earlier frame exists to bound the onset",
            **base,
        )
    previous_stats = _frame_stats(
        previous,
        panel_id,
        baseline,
        event.target_rgb,
        tolerance,
        change_threshold,
    )
    transition_points = [
        panel.region.sample_points[point]
        for point, (was_confirmed, now_confirmed) in enumerate(
            zip(previous_stats.confirmed, onset.confirmed)
        )
        if now_confirmed and not was_confirmed
    ]
    if not transition_points:
        return PanelObservation(
            status="ambiguous",
            target_fraction=round(onset.target_fraction, 3),
            changed_fraction=round(onset.changed_fraction, 3),
            noise_rms=round(noise, 3),
            onset_frame=onset.samples.frame.index,
            reason="the target appeared without an identifiable transition point",
            **base,
        )

    interval = panel_onset_interval(
        previous.start_s,
        onset.samples.start_s,
        transition_points,
        camera,
    )
    if not interval.consistent or interval.width_s > config.max_onset_width_s:
        return PanelObservation(
            status="ambiguous",
            onset_lower_s=round(interval.lower_s, 6),
            onset_point_s=round(interval.point_s, 6),
            onset_upper_s=round(interval.upper_s, 6),
            width_ms=round(interval.width_ms, 3),
            target_fraction=round(onset.target_fraction, 3),
            changed_fraction=round(onset.changed_fraction, 3),
            noise_rms=round(noise, 3),
            transition_points=len(transition_points),
            onset_frame=onset.samples.frame.index,
            reason=(
                "onset bounds are inconsistent or wider than "
                f"{config.max_onset_width_s * 1000.0:.0f} ms"
            ),
            **base,
        )

    confidence = _confidence(
        onset.target_fraction,
        event.min_target_fraction,
        [onset.target_distances[point] for point, value in enumerate(onset.confirmed) if value],
        tolerance,
        noise,
        interval.width_s,
        config.max_baseline_noise,
    )
    return PanelObservation(
        status="observed",
        onset_lower_s=round(interval.lower_s, 6),
        onset_point_s=round(interval.point_s, 6),
        onset_upper_s=round(interval.upper_s, 6),
        width_ms=round(interval.width_ms, 3),
        confidence=confidence,
        target_fraction=round(onset.target_fraction, 3),
        changed_fraction=round(onset.changed_fraction, 3),
        noise_rms=round(noise, 3),
        transition_points=len(transition_points),
        onset_frame=onset.samples.frame.index,
        **base,
    )


def _previous_sample(
    ordered_samples: Sequence[FrameSamples],
    frame_index: int,
) -> FrameSamples | None:
    previous = None
    for sample in ordered_samples:
        if sample.frame.index >= frame_index:
            break
        previous = sample
    return previous


def _resolve_reference(
    event: Event,
    capture: Capture,
    samples: dict[int, FrameSamples],
) -> tuple[int | None, float | None, str, str | None]:
    if event.reference_frame is not None:
        frame = capture.frame_by_index(event.reference_frame)
        if frame is None:
            if event.reference_time_s is not None:
                return (
                    None,
                    float(event.reference_time_s),
                    "explicit-time",
                    f"reference frame {event.reference_frame} is absent; used reference_time_s",
                )
            return None, None, "missing-frame", (
                f"reference frame {event.reference_frame} is absent from the capture"
            )
        if frame.index not in samples:
            if event.reference_time_s is not None:
                return (
                    None,
                    float(event.reference_time_s),
                    "explicit-time",
                    f"reference frame {event.reference_frame} could not be decoded",
                )
            return None, None, "undecodable-frame", (
                f"reference frame {event.reference_frame} could not be decoded"
            )
        return (
            frame.index,
            samples[frame.index].start_s,
            "frame",
            None,
        )
    if event.reference_time_s is not None:
        return None, float(event.reference_time_s), "explicit-time", None
    return None, None, "missing", "event has no usable reference"


def _analyse_event(
    event: Event,
    capture: Capture,
    rois: ROISet,
    samples: dict[int, FrameSamples],
    ordered_samples: Sequence[FrameSamples],
    config: AnalysisConfig,
) -> EventResult:
    reference_index, reference_time, reference_source, reference_error = _resolve_reference(
        event, capture, samples
    )
    if reference_time is None:
        panels = [
            _unobserved_panel(panel_id, reference_error or "no reference", capture.camera, rois.panels[panel_id])
            for panel_id in event.expected_panels
        ]
        return EventResult(
            event=event,
            reference_frame_index=reference_index,
            reference_time_s=None,
            reference_source=reference_source,
            window_start_s=None,
            window_end_s=None,
            panels=panels,
            status="unobserved",
            failure_reason=reference_error or "no usable reference",
        )

    window_start = reference_time - event.search_before_s
    window_end = reference_time + event.search_after_s
    camera = capture.camera
    baseline_samples = [
        sample for sample in ordered_samples
        if sample.start_s + camera.exposure_s + camera.readout_s <= window_start
    ][-config.baseline_frames:]
    candidate_samples = [
        sample for sample in ordered_samples
        if sample.start_s <= window_end
        and sample.start_s + camera.exposure_s + camera.readout_s > window_start
    ]

    panel_results = [
        _analyse_panel(
            event,
            rois.panels[panel_id],
            ordered_samples=ordered_samples,
            baseline_samples=baseline_samples,
            candidate_samples=candidate_samples,
            camera=camera,
            config=config,
        )
        for panel_id in event.expected_panels
    ]

    last_available_end = max(
        sample.start_s + camera.exposure_s + camera.readout_s
        for sample in ordered_samples
    )
    if window_end > last_available_end:
        for panel in panel_results:
            if panel.status == "missing":
                panel.status = "unobserved"
                panel.reason = (
                    "search window extends past the last decoded frame; "
                    "a later transition cannot be excluded"
                )

    for panel in panel_results:
        if panel.onset_point_s is not None and reference_time is not None:
            panel.point_offset_ms = round((panel.onset_point_s - reference_time) * 1000.0, 3)
            panel.lower_offset_ms = round((panel.onset_lower_s - reference_time) * 1000.0, 3)  # type: ignore[operator]
            panel.upper_offset_ms = round((panel.onset_upper_s - reference_time) * 1000.0, 3)  # type: ignore[operator]

    status = "observed"
    for candidate in ("unobserved", "missing", "wrong-target", "partial", "ambiguous"):
        if any(panel.status == candidate for panel in panel_results):
            status = candidate
            break
    failures = [
        f"{panel.panel_id}: {panel.status}"
        + (f" ({panel.reason})" if panel.reason else "")
        for panel in panel_results
        if panel.status != "observed"
    ]

    observed = [panel for panel in panel_results if panel.status == "observed"]
    skew_point = skew_lower = skew_upper = None
    if observed and all(
        panel.point_offset_ms is not None
        and panel.lower_offset_ms is not None
        and panel.upper_offset_ms is not None
        for panel in observed
    ):
        point_offsets = [panel.point_offset_ms for panel in observed]  # type: ignore[list-item]
        lower_offsets = [panel.lower_offset_ms for panel in observed]  # type: ignore[list-item]
        upper_offsets = [panel.upper_offset_ms for panel in observed]  # type: ignore[list-item]
        skew_point = round(max(point_offsets) - min(point_offsets), 3)
        skew_lower = round(max(0.0, max(lower_offsets) - min(upper_offsets)), 3)
        skew_upper = round(max(0.0, max(upper_offsets) - min(lower_offsets)), 3)
        if len(observed) != len(panel_results):
            failures.append(
                "wall skew is diagnostic only: not every expected panel was observed"
            )

    return EventResult(
        event=event,
        reference_frame_index=reference_index,
        reference_time_s=reference_time,
        reference_source=reference_source,
        window_start_s=window_start,
        window_end_s=window_end,
        panels=panel_results,
        status=status,
        failure_reason="; ".join(failures) if failures else None,
        skew_point_ms=skew_point,
        skew_lower_ms=skew_lower,
        skew_upper_ms=skew_upper,
    )


def _event_unobserved_intervals(
    events: Iterable[EventResult],
    ordered_samples: Sequence[FrameSamples],
    camera: Camera,
) -> list[dict[str, object]]:
    if not ordered_samples:
        return []
    first = ordered_samples[0].start_s
    last = ordered_samples[-1].start_s + camera.exposure_s + camera.readout_s
    intervals: list[dict[str, object]] = []
    for result in events:
        if result.window_start_s is None or result.window_end_s is None:
            intervals.append({
                "start_s": None,
                "end_s": None,
                "reason": "event has no usable reference or window",
                "declared_dropped": False,
                "event_id": result.event.event_id,
            })
            continue
        if result.window_start_s < first:
            intervals.append({
                "start_s": round(result.window_start_s, 6),
                "end_s": round(first, 6),
                "reason": "search window starts before the first decoded frame",
                "declared_dropped": False,
                "event_id": result.event.event_id,
            })
        if result.window_end_s > last:
            intervals.append({
                "start_s": round(last, 6),
                "end_s": round(result.window_end_s, 6),
                "reason": "search window extends past the last decoded frame",
                "declared_dropped": False,
                "event_id": result.event.event_id,
            })
        if any(
            panel.status == "unobserved" and "baseline" in (panel.reason or "")
            for panel in result.panels
        ) and result.window_start_s > first:
            intervals.append({
                "start_s": round(first, 6),
                "end_s": round(result.window_start_s, 6),
                "reason": "baseline window is not covered by enough decoded frames",
                "declared_dropped": False,
                "event_id": result.event.event_id,
            })
    return intervals


def _attach_source_frames(
    results: Sequence[EventResult],
    capture: Capture,
    rois: ROISet,
    *,
    enabled: bool,
    tesseract_cmd: str,
) -> tuple[bool, str, str]:
    roi = rois.source_frame_roi
    if roi is None:
        for result in results:
            result.source_frame = {
                "expected": result.event.source_frame,
                "observed": None,
                "status": "no-source-frame-roi",
            }
        return False, "not-verified", "No burned-in source-frame ROI is configured."
    if not enabled:
        for result in results:
            result.source_frame = {
                "expected": result.event.source_frame,
                "observed": None,
                "status": "ocr-not-requested",
            }
        return False, "not-verified", "Burned-in source-frame OCR was not requested."

    cache: dict[int, tuple[int | None, str | None]] = {}
    checks: list[dict[str, object]] = []
    for result in results:
        expected = result.event.source_frame
        result.source_frame = {
            "expected": expected,
            "observed": None,
            "status": "not-run",
        }
        if expected is None:
            result.source_frame["status"] = "no-expected-source-frame"
            continue
        if result.reference_frame_index is None:
            result.source_frame["status"] = "no-reference-frame"
            result.source_frame["error"] = "event has no reference frame for OCR"
            checks.append({
                "event_id": result.event.event_id,
                "expected": expected,
                "observed": None,
                "status": "no-reference-frame",
                "reference_time_s": result.reference_time_s,
            })
            continue
        frame_index = result.reference_frame_index
        if frame_index not in cache:
            frame = capture.frame_by_index(frame_index)
            if frame is None or frame.path is None:
                cache[frame_index] = (None, "reference frame has no path")
            else:
                try:
                    observed = read_source_frame(
                        frame.path,
                        roi,
                        rois.source_frame_digits,
                        tesseract_cmd=tesseract_cmd,
                    )
                    cache[frame_index] = (observed, None if observed is not None else "no digits read")
                except ToolUnavailable as error:
                    cache[frame_index] = (None, str(error))
                except (OSError, ValueError) as error:
                    cache[frame_index] = (None, str(error))
        observed, error = cache[frame_index]
        result.source_frame["observed"] = observed
        if error is not None:
            result.source_frame["status"] = "unreadable"
            result.source_frame["error"] = error
        elif observed is None:
            result.source_frame["status"] = "unreadable"
        elif observed == expected:
            result.source_frame["status"] = "match"
        else:
            result.source_frame["status"] = "mismatch"
        checks.append({
            "event_id": result.event.event_id,
            "expected": expected,
            "observed": observed,
            "status": result.source_frame["status"],
            "reference_time_s": result.reference_time_s,
        })

    declared = [result for result in results if result.event.source_frame is not None]
    if not declared:
        return False, "not-verified", "No event declares an expected source frame."
    if len(checks) != len(declared):
        return False, "not-verified", (
            f"{len(checks)} of {len(declared)} declared source frames were checked."
        )
    reads_ok = all(check["observed"] is not None for check in checks)
    ordered = sorted(
        checks,
        key=lambda item: (
            item["reference_time_s"] is None,
            item["reference_time_s"] or 0.0,
        ),
    )
    expected_values = [int(item["expected"]) for item in ordered]
    observed_values = [
        int(item["observed"]) for item in ordered if item["observed"] is not None
    ]
    expected_increasing = all(
        earlier < later for earlier, later in zip(expected_values, expected_values[1:])
    )
    observed_increasing = all(
        earlier < later for earlier, later in zip(observed_values, observed_values[1:])
    )
    tracking = reads_ok and expected_increasing and observed_increasing
    matches = [item for item in checks if item["status"] == "match"]
    if not reads_ok:
        return tracking, "not-verified", (
            "Burned-in source frames could not be read for every declared check."
        )
    if not expected_increasing:
        return tracking, "not-verified", (
            "Declared source-frame values are not strictly increasing and unique."
        )
    if not observed_increasing:
        return tracking, "not-verified", (
            "Burned-in source-frame values are not strictly increasing and unique."
        )
    if len(matches) != len(checks):
        return tracking, "mismatch", "Burned-in source frames do not match the event records."
    if len(checks) < 2:
        return tracking, "insufficient-checks", "Only one burned-in source-frame check was available."
    return tracking, "verified-by-burned-in-frames", (
        f"{len(checks)} burned-in source-frame checks matched and were strictly increasing."
    )


def analyze_capture(
    capture: Capture,
    rois: ROISet,
    events: Sequence[Event],
    *,
    config: AnalysisConfig | None = None,
    ocr: bool = False,
    tesseract_cmd: str = "tesseract",
    timing_source: str = "manifest",
    started_at: str = "",
    finished_at: str = "",
) -> Analysis:
    config = config or AnalysisConfig()
    validate_panel_coverage(events, rois)
    frame_errors: list[dict[str, object]] = []
    samples = load_samples(capture, rois, frame_errors=frame_errors)
    ordered_samples = sorted(samples.values(), key=lambda item: item.frame.index)
    if not ordered_samples:
        raise ValueError("no frames could be decoded")

    results = [
        _analyse_event(event, capture, rois, samples, ordered_samples, config)
        for event in events
    ]
    source_frame_tracking, video_sync, video_sync_detail = _attach_source_frames(
        results,
        capture,
        rois,
        enabled=ocr,
        tesseract_cmd=tesseract_cmd,
    )

    intervals = capture_unobserved_intervals(capture, config.gap_factor)
    intervals.extend(_event_unobserved_intervals(results, ordered_samples, capture.camera))
    recovery: list[dict[str, object]] = []
    for result in results:
        if not result.event.steady_state and result.window_start_s is not None:
            recovery.append({
                "event_id": result.event.event_id,
                "start_s": round(result.window_start_s, 6),
                "end_s": round(result.window_end_s or result.window_start_s, 6),
                "kind": "declared-recovery-or-startup",
            })

    metrics = build_metrics(results, config, timing_source=timing_source, capture=capture)
    return Analysis(
        capture=capture,
        rois=rois,
        events=list(results),
        config=config,
        metrics=metrics,
        unobserved_intervals=intervals,
        recovery_intervals=recovery,
        frame_errors=frame_errors,
        source_frame_tracking=source_frame_tracking,
        video_sync=video_sync,
        video_sync_detail=video_sync_detail,
        ocr_requested=ocr,
        started_at=started_at or iso_now(),
        finished_at=finished_at or iso_now(),
        timing_source=timing_source,
        tool_version=TOOL_VERSION,
    )
