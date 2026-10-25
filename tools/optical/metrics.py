"""Cohort metrics and threshold observations for the optical analyzer.

The metrics never produce a pass. A window is gate-evaluable only when it has
at least 100 complete events and no failed, ambiguous or unobserved event.
The conservative skew upper bound is checked separately: if it crosses the
published threshold while the point estimate does not, the window is
``inconclusive``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .model import AnalysisConfig, Capture, EventResult
from .timing import frame_interval_stats, percentile

FAILURE_STATUSES = ("missing", "wrong-target", "partial")


@dataclass(frozen=True)
class EventMeasurement:
    event_id: str
    status: str
    steady_state: bool
    expected_panels: tuple[str, ...]
    panel_statuses: dict[str, str]
    panel_offsets_ms: dict[str, float]
    skew_ms: float | None
    skew_lower_ms: float | None
    skew_upper_ms: float | None
    width_ms: float | None
    window_start_s: float | None
    window_end_s: float | None
    failure_reason: str | None

    @property
    def complete(self) -> bool:
        return (
            self.status == "observed"
            and len(self.expected_panels) > 0
            and all(
                self.panel_statuses.get(panel) == "observed"
                for panel in self.expected_panels
            )
        )


def measurement_from_result(result: EventResult) -> EventMeasurement:
    panel_offsets = {
        panel.panel_id: panel.point_offset_ms
        for panel in result.panels
        if panel.point_offset_ms is not None
    }
    return EventMeasurement(
        event_id=result.event.event_id,
        status=result.status,
        steady_state=result.event.steady_state,
        expected_panels=result.event.expected_panels,
        panel_statuses={panel.panel_id: panel.status for panel in result.panels},
        panel_offsets_ms=panel_offsets,  # type: ignore[arg-type]
        skew_ms=result.skew_point_ms,
        skew_lower_ms=result.skew_lower_ms,
        skew_upper_ms=result.skew_upper_ms,
        width_ms=(
            max(
                (panel.width_ms for panel in result.panels if panel.width_ms is not None),
                default=None,
            )
        ),
        window_start_s=result.window_start_s,
        window_end_s=result.window_end_s,
        failure_reason=result.failure_reason,
    )


def _stats(values: Sequence[float | None]) -> dict[str, float | int | None]:
    present = [float(value) for value in values if value is not None]
    if not present:
        return {
            "count": 0,
            "min": None,
            "p50": None,
            "p95": None,
            "max": None,
            "mean": None,
        }
    return {
        "count": len(present),
        "min": round(min(present), 3),
        "p50": round(percentile(present, 50) or 0.0, 3),
        "p95": round(percentile(present, 95) or 0.0, 3),
        "max": round(max(present), 3),
        "mean": round(sum(present) / len(present), 3),
    }


def window_metrics(
    measurements: Sequence[EventMeasurement],
    config: AnalysisConfig,
) -> dict[str, Any]:
    counts = {
        "events_total": 0,
        "events_observed": 0,
        "events_missing": 0,
        "events_wrong_target": 0,
        "events_partial": 0,
        "events_ambiguous": 0,
        "events_unobserved": 0,
    }
    panel_counts = {
        "expected": 0,
        "observed": 0,
        "missing": 0,
        "ambiguous": 0,
        "partial": 0,
        "wrong_target": 0,
        "unobserved": 0,
    }
    failed_ids: list[str] = []
    failures: list[dict[str, Any]] = []
    ambiguous_ids: list[str] = []
    unobserved_ids: list[str] = []
    complete: list[EventMeasurement] = []

    for measurement in measurements:
        counts["events_total"] += 1
        if measurement.status == "observed":
            counts["events_observed"] += 1
        elif measurement.status == "missing":
            counts["events_missing"] += 1
            failed_ids.append(measurement.event_id)
        elif measurement.status == "wrong-target":
            counts["events_wrong_target"] += 1
            failed_ids.append(measurement.event_id)
        elif measurement.status == "partial":
            counts["events_partial"] += 1
            failed_ids.append(measurement.event_id)
        elif measurement.status == "ambiguous":
            counts["events_ambiguous"] += 1
            ambiguous_ids.append(measurement.event_id)
        elif measurement.status == "unobserved":
            counts["events_unobserved"] += 1
            unobserved_ids.append(measurement.event_id)

        for panel in measurement.expected_panels:
            status = measurement.panel_statuses.get(panel, "unobserved")
            panel_counts["expected"] += 1
            key = "wrong_target" if status == "wrong-target" else status
            if key in panel_counts:
                panel_counts[key] += 1

        if measurement.complete:
            complete.append(measurement)
        else:
            failures.append({
                "event_id": measurement.event_id,
                "status": measurement.status,
                "reason": measurement.failure_reason,
            })

    windows = [
        (measurement.window_start_s, measurement.window_end_s)
        for measurement in measurements
        if measurement.window_start_s is not None and measurement.window_end_s is not None
    ]
    declared_window = {
        "start_s": round(min(start for start, _ in windows), 6) if windows else None,
        "end_s": round(max(end for _, end in windows), 6) if windows else None,
    }
    panel_ids = sorted({
        panel for measurement in measurements for panel in measurement.expected_panels
    })
    panel_offsets = {
        panel: _stats([
            measurement.panel_offsets_ms.get(panel)
            for measurement in complete
        ])
        for panel in panel_ids
    }

    complete_count = len(complete)
    evaluable = (
        complete_count >= config.minimum_complete_events
        and not failed_ids
        and not ambiguous_ids
        and not unobserved_ids
    )
    reasons: list[str] = []
    if complete_count < config.minimum_complete_events:
        reasons.append(
            f"only {complete_count} complete events; at least "
            f"{config.minimum_complete_events} are required for a gate-evaluable observation"
        )
    if failed_ids:
        reasons.append(f"{len(failed_ids)} event(s) failed and are retained")
    if ambiguous_ids:
        reasons.append(f"{len(ambiguous_ids)} event(s) were ambiguous")
    if unobserved_ids:
        reasons.append(f"{len(unobserved_ids)} event(s) were unobserved")

    return {
        **counts,
        "complete_events": complete_count,
        "complete_event_ids": [measurement.event_id for measurement in complete],
        "failed_event_ids": failed_ids,
        "ambiguous_event_ids": ambiguous_ids,
        "unobserved_event_ids": unobserved_ids,
        "failures": failures,
        "panel_counts": panel_counts,
        "skew_ms": _stats([measurement.skew_ms for measurement in complete]),
        "skew_lower_ms": _stats([measurement.skew_lower_ms for measurement in complete]),
        "skew_upper_ms": _stats([measurement.skew_upper_ms for measurement in complete]),
        "onset_width_ms": _stats([measurement.width_ms for measurement in complete]),
        "panel_offsets_ms": panel_offsets,
        "declared_window": declared_window,
        "gate_evaluable": evaluable,
        "evaluable_reasons": reasons,
    }


def _threshold_status(window: dict[str, Any], config: AnalysisConfig) -> str:
    skew = window["skew_ms"]
    if skew["count"] == 0:
        return "insufficient-events"
    if (
        (skew["p95"] is not None and skew["p95"] > config.p95_limit_ms)
        or (skew["max"] is not None and skew["max"] > config.max_limit_ms)
    ):
        return "exceeded"
    upper = window["skew_upper_ms"]
    if (
        (upper["p95"] is not None and upper["p95"] > config.p95_limit_ms)
        or (upper["max"] is not None and upper["max"] > config.max_limit_ms)
    ):
        return "inconclusive"
    return "within-threshold"


def _threshold_detail(window: dict[str, Any], status: str, config: AnalysisConfig) -> dict[str, Any]:
    return {
        "status": status,
        "gate_evaluable": window["gate_evaluable"],
        "complete_events": window["complete_events"],
        "p95_ms": window["skew_ms"]["p95"],
        "max_ms": window["skew_ms"]["max"],
        "p95_upper_ms": window["skew_upper_ms"]["p95"],
        "max_upper_ms": window["skew_upper_ms"]["max"],
        "limits": {
            "p95_ms": config.p95_limit_ms,
            "max_ms": config.max_limit_ms,
            "minimum_complete_events": config.minimum_complete_events,
        },
        "reasons": list(window["evaluable_reasons"]),
    }


def evaluate_thresholds(
    full_run: dict[str, Any],
    steady_state: dict[str, Any],
    config: AnalysisConfig,
) -> dict[str, Any]:
    full_status = _threshold_status(full_run, config)
    steady_status = _threshold_status(steady_state, config)
    severity = {
        "insufficient-events": 0,
        "within-threshold": 1,
        "inconclusive": 2,
        "exceeded": 3,
    }
    statuses = [full_status]
    if steady_state["events_total"] > 0:
        statuses.append(steady_status)
    overall = max(statuses, key=lambda value: severity[value])
    if overall == "within-threshold" and full_status == "insufficient-events":
        overall = "insufficient-events"

    gate_evaluable = full_run["gate_evaluable"]
    if not gate_evaluable:
        observation = "not-evaluable"
    elif overall == "exceeded":
        observation = "exceeded"
    elif overall == "inconclusive":
        observation = "inconclusive"
    elif overall == "within-threshold":
        observation = "within-threshold-observation-only"
    else:
        observation = "not-evaluable"

    reasons = list(full_run["evaluable_reasons"])
    if overall == "exceeded":
        reasons.append("point-estimate skew exceeds the published threshold")
    elif overall == "inconclusive":
        reasons.append(
            "conservative onset uncertainty crosses the published threshold; "
            "the observation is inconclusive, not a pass"
        )
    elif not gate_evaluable:
        reasons.append("the run is not gate-evaluable")

    return {
        "p95_limit_ms": config.p95_limit_ms,
        "max_limit_ms": config.max_limit_ms,
        "minimum_complete_events": config.minimum_complete_events,
        "status": overall,
        "observation": observation,
        "gate_evaluable": gate_evaluable,
        "within_threshold_observation_only": (
            gate_evaluable and overall == "within-threshold"
        ),
        "reasons": reasons,
        "full_run": _threshold_detail(full_run, full_status, config),
        "steady_state": _threshold_detail(steady_state, steady_status, config),
    }


def build_metrics(
    results: Sequence[EventResult],
    config: AnalysisConfig,
    *,
    timing_source: str,
    capture: Capture,
) -> dict[str, Any]:
    measurements = [measurement_from_result(result) for result in results]
    full_run = window_metrics(measurements, config)
    steady = [measurement for measurement in measurements if measurement.steady_state]
    steady_state = window_metrics(steady, config)
    if not capture.camera.readout_measured:
        note = (
            "rolling-shutter readout was not marked measured; row-offset "
            "uncertainty cannot support a gate-evaluable observation"
        )
        for window in (full_run, steady_state):
            if window["events_total"]:
                window["gate_evaluable"] = False
                window["evaluable_reasons"].append(note)
    recovery = [measurement for measurement in measurements if not measurement.steady_state]
    timing = frame_interval_stats(capture, timing_source=timing_source).as_dict()
    return {
        "timing": timing,
        "full_run": full_run,
        "steady_state": steady_state,
        "recovery": {
            "events_total": len(recovery),
            "event_ids": [measurement.event_id for measurement in recovery],
            "intervals": [
                {
                    "event_id": measurement.event_id,
                    "start_s": measurement.window_start_s,
                    "end_s": measurement.window_end_s,
                }
                for measurement in recovery
            ],
        },
        "thresholds": evaluate_thresholds(full_run, steady_state, config),
    }
