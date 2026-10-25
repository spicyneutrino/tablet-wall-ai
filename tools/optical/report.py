"""CSV/JSON/Markdown outputs and the evidence report.

The evidence report is built with :func:`tools.validation.evidence.build_report`
so it carries the shared schema, artifact hashes, failures and the permanent
``hardware_gate_status = MISSING`` marker.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Sequence

from tools.validation import evidence

from . import TOOL_NAME, TOOL_VERSION
from .model import Analysis, EventResult, PanelObservation
from .video import tool_versions

SOURCE_FRAME_LIMITATION = (
    "A cut detector is not video synchronization. Source-frame alignment is "
    "claimed only when a burned-in frame ROI was read successfully."
)


def _round(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(float(value), digits)


def panel_to_dict(panel: PanelObservation) -> dict[str, Any]:
    return {
        "panel_id": panel.panel_id,
        "status": panel.status,
        "onset_lower_s": panel.onset_lower_s,
        "onset_point_s": panel.onset_point_s,
        "onset_upper_s": panel.onset_upper_s,
        "point_offset_ms": panel.point_offset_ms,
        "lower_offset_ms": panel.lower_offset_ms,
        "upper_offset_ms": panel.upper_offset_ms,
        "width_ms": panel.width_ms,
        "confidence": panel.confidence,
        "target_fraction": panel.target_fraction,
        "changed_fraction": panel.changed_fraction,
        "noise_rms": panel.noise_rms,
        "transition_points": panel.transition_points,
        "readout_offset_min_ms": panel.readout_offset_min_ms,
        "readout_offset_max_ms": panel.readout_offset_max_ms,
        "onset_frame": panel.onset_frame,
        "reason": panel.reason,
    }


def event_to_dict(result: EventResult) -> dict[str, Any]:
    return {
        "event_id": result.event.event_id,
        "status": result.status,
        "steady_state": result.event.steady_state,
        "reference": {
            "frame_index": result.reference_frame_index,
            "time_s": result.reference_time_s,
            "source": result.reference_source,
        },
        "search_window": {
            "start_s": result.window_start_s,
            "end_s": result.window_end_s,
            "before_ms": round(result.event.search_before_s * 1000.0, 3),
            "after_ms": round(result.event.search_after_s * 1000.0, 3),
        },
        "expected_panels": list(result.event.expected_panels),
        "target": {
            "rgb": [round(value, 3) for value in result.event.target_rgb],
            "tolerance": result.event.target_tolerance,
            "min_target_fraction": result.event.min_target_fraction,
        },
        "counts": result.counts,
        "wall_skew_ms": result.skew_point_ms,
        "wall_skew_lower_ms": result.skew_lower_ms,
        "wall_skew_upper_ms": result.skew_upper_ms,
        "failure_reason": result.failure_reason,
        "source_frame": result.source_frame,
        "panels": [panel_to_dict(panel) for panel in result.panels],
        "notes": result.event.notes,
    }


def analysis_to_dict(analysis: Analysis) -> dict[str, Any]:
    capture = analysis.capture
    frames = capture.frames
    return {
        "schema": "tablet-wall-optical-analysis/1",
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "capture": {
            "capture_id": capture.capture_id,
            "evidence_kind": capture.evidence_kind,
            "manifest_path": str(capture.manifest_path),
            "timestamp_basis": capture.timestamp_basis,
            "timing_source": analysis.timing_source,
            "frame_count": len(frames),
            "first_frame_s": _round(frames[0].timestamp_s, 9) if frames else None,
            "last_frame_s": _round(frames[-1].timestamp_s, 9) if frames else None,
            "dropped_frames": sorted(capture.dropped_frames),
            "duplicated_frames": sorted(capture.duplicated_frames),
            "clock": capture.clock,
            "panel_scanout": capture.panel_scanout,
            "warnings": list(capture.warnings),
            "notes": capture.notes,
            "camera": {
                "model": capture.camera.model,
                "gain": capture.camera.gain,
                "white_balance": capture.camera.white_balance,
                "exposure_us": capture.camera.exposure_us,
                "orientation_deg": capture.camera.orientation_deg,
                "resolution": {
                    "width": capture.camera.width,
                    "height": capture.camera.height,
                },
                "rolling_shutter": {
                    "readout_us": capture.camera.readout_us,
                    "direction": capture.camera.readout_direction,
                    "measured": capture.camera.readout_measured,
                },
                "nominal_fps_metadata_only": capture.camera.nominal_fps,
            },
        },
        "rois": {
            "coordinate_space": "delivered",
            "input_coordinate_space": analysis.rois.coordinate_space,
            "panels": {
                panel_id: {
                    "polygon": [list(point) for point in panel.region.polygon],
                    "sample_points": [list(point) for point in panel.region.sample_points],
                    "sample_radius": panel.region.sample_radius,
                    "noise_polygon": (
                        [list(point) for point in panel.noise_region.polygon]
                        if panel.noise_region is not None else None
                    ),
                    "noise_sample_points": (
                        [list(point) for point in panel.noise_region.sample_points]
                        if panel.noise_region is not None else None
                    ),
                }
                for panel_id, panel in analysis.rois.panels.items()
            },
            "source_frame_roi": (
                list(analysis.rois.source_frame_roi)
                if analysis.rois.source_frame_roi is not None else None
            ),
        },
        "config": analysis.config.as_dict(),
        "timing": analysis.metrics["timing"],
        "events": [event_to_dict(result) for result in analysis.events],
        "metrics": analysis.metrics,
        "unobserved_intervals": analysis.unobserved_intervals,
        "recovery_intervals": analysis.recovery_intervals,
        "frame_errors": analysis.frame_errors,
        "source_frame_tracking": analysis.source_frame_tracking,
        "video_sync": analysis.video_sync,
        "video_sync_detail": analysis.video_sync_detail,
        "started_at": analysis.started_at,
        "finished_at": analysis.finished_at,
    }


def _write_events_csv(path: Path, analysis: Analysis) -> None:
    columns = [
        "event_id",
        "status",
        "steady_state",
        "reference_frame",
        "reference_time_s",
        "window_start_s",
        "window_end_s",
        "expected_panels",
        "panels_observed",
        "panels_missing",
        "panels_ambiguous",
        "panels_partial",
        "panels_wrong_target",
        "panels_unobserved",
        "wall_skew_ms",
        "wall_skew_lower_ms",
        "wall_skew_upper_ms",
        "failure_reason",
        "source_frame_expected",
        "source_frame_observed",
        "source_frame_status",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for result in analysis.events:
            counts = result.counts
            source = result.source_frame or {}
            writer.writerow({
                "event_id": result.event.event_id,
                "status": result.status,
                "steady_state": result.event.steady_state,
                "reference_frame": result.reference_frame_index,
                "reference_time_s": result.reference_time_s,
                "window_start_s": result.window_start_s,
                "window_end_s": result.window_end_s,
                "expected_panels": ";".join(result.event.expected_panels),
                "panels_observed": counts["observed"],
                "panels_missing": counts["missing"],
                "panels_ambiguous": counts["ambiguous"],
                "panels_partial": counts["partial"],
                "panels_wrong_target": counts["wrong_target"],
                "panels_unobserved": counts["unobserved"],
                "wall_skew_ms": result.skew_point_ms,
                "wall_skew_lower_ms": result.skew_lower_ms,
                "wall_skew_upper_ms": result.skew_upper_ms,
                "failure_reason": result.failure_reason or "",
                "source_frame_expected": source.get("expected"),
                "source_frame_observed": source.get("observed"),
                "source_frame_status": source.get("status"),
            })


def _write_panels_csv(path: Path, analysis: Analysis) -> None:
    columns = [
        "event_id",
        "panel_id",
        "status",
        "onset_lower_s",
        "onset_point_s",
        "onset_upper_s",
        "point_offset_ms",
        "lower_offset_ms",
        "upper_offset_ms",
        "width_ms",
        "confidence",
        "target_fraction",
        "changed_fraction",
        "noise_rms",
        "transition_points",
        "readout_offset_min_ms",
        "readout_offset_max_ms",
        "onset_frame",
        "reason",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for result in analysis.events:
            for panel in result.panels:
                row = panel_to_dict(panel)
                row["event_id"] = result.event.event_id
                row["reason"] = panel.reason or ""
                writer.writerow({column: row.get(column) for column in columns})


def _md(value: Any) -> str:
    if value is None:
        return "—"
    return str(value).replace("|", "\\|")


def _stats_cell(stats: dict[str, Any]) -> str:
    if not stats or not stats.get("count"):
        return "—"
    return f"{stats['p50']:.1f} / {stats['p95']:.1f} / {stats['max']:.1f}"


def _write_summary_markdown(path: Path, analysis: Analysis) -> None:
    capture = analysis.capture
    metrics = analysis.metrics
    thresholds = metrics["thresholds"]
    full = metrics["full_run"]
    steady = metrics["steady_state"]
    lines: list[str] = [
        f"# Optical cut analysis: {capture.capture_id}",
        "",
        "**Gate: `optical-cut-timing` — MISSING.** This report is kit/logic evidence, "
        "not hardware acceptance. No optical gate is claimed.",
        "",
        f"- Evidence kind: `{capture.evidence_kind}`",
        f"- Manifest: `{capture.manifest_path}`",
        f"- Tool: `{TOOL_NAME}` {TOOL_VERSION}",
        f"- Timing source: `{analysis.timing_source}`; nominal fps is metadata only.",
        f"- Started/finished: {analysis.started_at} / {analysis.finished_at}",
        "",
    ]
    if capture.evidence_kind == "synthetic":
        lines.extend([
            "> Synthetic fixtures validate the analyzer only. They are not panel, "
            "capture or hardware evidence.",
            "",
        ])

    lines.extend([
        "## Verdict",
        "",
        f"- Threshold observation: **{thresholds['status']}** "
        f"(`{thresholds['observation']}`)",
        f"- Gate-evaluable: **{thresholds['gate_evaluable']}** "
        f"({full['complete_events']} complete events; "
        f"{thresholds['minimum_complete_events']} required)",
        f"- Full-run p50 / p95 / max point skew: "
        f"{_stats_cell(full['skew_ms'])} ms",
        f"- Full-run conservative p95 / max bound: "
        f"{_md(full['skew_upper_ms']['p95'])} / {_md(full['skew_upper_ms']['max'])} ms",
        f"- Steady-state p50 / p95 / max point skew: {_stats_cell(steady['skew_ms'])} ms",
        f"- Failed events: {len(full['failed_event_ids'])}; "
        f"ambiguous: {len(full['ambiguous_event_ids'])}; "
        f"unobserved: {len(full['unobserved_event_ids'])}",
        "",
    ])
    if thresholds["reasons"]:
        lines.append("Reasons:")
        lines.extend(f"- {reason}" for reason in thresholds["reasons"])
        lines.append("")

    lines.extend([
        "## Capture timing",
        "",
        f"- Frames: {metrics['timing']['count']}",
        f"- Actual median frame interval: {metrics['timing']['median_ms']} ms "
        f"(p95 {metrics['timing']['p95_ms']} ms, max {metrics['timing']['maximum_ms']} ms)",
        f"- Nominal fps (metadata only): {metrics['timing']['nominal_fps_metadata_only']}",
        f"- Exposure: {capture.camera.exposure_us} µs; "
        f"orientation: {capture.camera.orientation_deg}°",
        f"- Rolling shutter: {capture.camera.readout_us} µs "
        f"{capture.camera.readout_direction}, "
        f"measured={capture.camera.readout_measured}",
        f"- Gain: {capture.camera.gain}; white balance: {capture.camera.white_balance}",
        f"- Dropped frames: {sorted(capture.dropped_frames) or 'none'}",
        f"- Duplicated frames: {sorted(capture.duplicated_frames) or 'none'}",
        "",
    ])
    if capture.warnings:
        lines.append("Capture warnings:")
        lines.extend(f"- {warning}" for warning in capture.warnings)
        lines.append("")

    lines.extend([
        "## Windows",
        "",
        "| Window | Complete | Observed | Failed | Ambiguous | Unobserved | "
        "p95 point | max point | p95 upper | max upper | Evaluable |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ])
    for name, window in (("full run", full), ("steady state", steady)):
        lines.append(
            f"| {name} | {window['complete_events']} | {window['events_observed']} | "
            f"{len(window['failed_event_ids'])} | {len(window['ambiguous_event_ids'])} | "
            f"{len(window['unobserved_event_ids'])} | "
            f"{_md(window['skew_ms']['p95'])} | {_md(window['skew_ms']['max'])} | "
            f"{_md(window['skew_upper_ms']['p95'])} | {_md(window['skew_upper_ms']['max'])} | "
            f"{window['gate_evaluable']} |"
        )
    lines.append("")

    lines.extend([
        "## Events",
        "",
        "| Event | Status | Steady | Skew ms | Conservative bound ms | "
        "Observed/expected | Failure |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ])
    for result in analysis.events:
        counts = result.counts
        bound = (
            f"{result.skew_lower_ms}–{result.skew_upper_ms}"
            if result.skew_lower_ms is not None and result.skew_upper_ms is not None
            else "—"
        )
        lines.append(
            f"| {_md(result.event.event_id)} | {result.status} | "
            f"{result.event.steady_state} | {_md(result.skew_point_ms)} | {_md(bound)} | "
            f"{counts['observed']}/{counts['expected']} | {_md(result.failure_reason)} |"
        )
    lines.append("")

    lines.extend([
        "## Panel rows",
        "",
        "| Event | Panel | Status | Point ms | Lower–upper ms | Width ms | "
        "Confidence | Target fraction | Reason |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ])
    for result in analysis.events:
        for panel in result.panels:
            bounds = (
                f"{panel.lower_offset_ms}–{panel.upper_offset_ms}"
                if panel.lower_offset_ms is not None and panel.upper_offset_ms is not None
                else "—"
            )
            lines.append(
                f"| {_md(result.event.event_id)} | {_md(panel.panel_id)} | {panel.status} | "
                f"{_md(panel.point_offset_ms)} | {_md(bounds)} | {_md(panel.width_ms)} | "
                f"{panel.confidence} | {panel.target_fraction} | {_md(panel.reason)} |"
            )
    lines.append("")

    failed_rows = [
        (result, panel)
        for result in analysis.events
        for panel in result.panels
        if panel.status != "observed"
    ]
    lines.extend(["## Failure rows retained", ""])
    if failed_rows:
        for result, panel in failed_rows:
            lines.append(
                f"- `{result.event.event_id}` / `{panel.panel_id}`: **{panel.status}** — "
                f"{panel.reason or 'no detail'}"
            )
    else:
        lines.append("None.")
    lines.append("")

    lines.extend(["## Unobserved intervals", ""])
    if analysis.unobserved_intervals:
        for interval in analysis.unobserved_intervals:
            lines.append(
                f"- `{_md(interval.get('event_id') or 'capture')}` "
                f"[{_md(interval.get('start_s'))}, {_md(interval.get('end_s'))}] s: "
                f"{interval.get('reason')}"
            )
    else:
        lines.append("None.")
    lines.append("")

    lines.extend(["## Recovery intervals", ""])
    if analysis.recovery_intervals:
        for interval in analysis.recovery_intervals:
            lines.append(
                f"- `{interval['event_id']}` "
                f"[{interval['start_s']}, {interval['end_s']}] s "
                f"({interval['kind']})"
            )
    else:
        lines.append("None declared.")
    lines.append("")

    lines.extend([
        "## Source-frame alignment",
        "",
        f"- Tracking available: **{analysis.source_frame_tracking}**",
        f"- Video sync: **{analysis.video_sync}** — {analysis.video_sync_detail}",
        "",
    ])

    if analysis.frame_errors:
        lines.extend(["## Frame decode errors", ""])
        for error in analysis.frame_errors:
            lines.append(
                f"- frame {error.get('frame_index')}: {error.get('error')} "
                f"({_md(error.get('path'))})"
            )
        lines.append("")

    lines.extend(["## Limitations", ""])
    for limitation in limitations_for(analysis):
        lines.append(f"- {limitation}")
    lines.append("")
    path.write_text("\n".join(lines) + "\n")


def limitations_for(analysis: Analysis) -> list[str]:
    limitations = [
        "The optical gate remains MISSING; this tool cannot change a hardware gate.",
        "Visible onset is inferred from captured frames, not from panel photon emission "
        "or capture-to-glass latency.",
        "Camera-clock mapping, reference-flash alignment and rolling-shutter readout are "
        "supplied metadata, not independently verified by this analyzer.",
        "Nominal fps is metadata only; all timing uses actual frame timestamps.",
    ]
    if analysis.capture.evidence_kind == "synthetic":
        limitations.append(
            "Synthetic fixtures validate the analyzer only; they are not panel or "
            "hardware evidence."
        )
    if not analysis.capture.camera.readout_measured:
        limitations.append(
            "The rolling-shutter readout was not marked measured; row-offset timing "
            "relies on an operator estimate."
        )
    if analysis.capture.panel_scanout:
        limitations.append(
            "Panel scanout is an operator note, not a measurement made by this tool."
        )
    if not analysis.source_frame_tracking:
        limitations.append(SOURCE_FRAME_LIMITATION)
    if analysis.metrics["full_run"]["complete_events"] < analysis.config.minimum_complete_events:
        limitations.append(
            f"Only {analysis.metrics['full_run']['complete_events']} complete events "
            f"were analysed; the published gate needs at least "
            f"{analysis.config.minimum_complete_events}."
        )
    limitations.append(
        "Raw camera captures are expected to stay outside the repository; only bounded "
        "analysis artifacts are hashed here."
    )
    return limitations


def _event_scenarios(analysis: Analysis) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in analysis.events:
        if result.status == "observed":
            status = "passed"
        elif result.status in ("missing", "wrong-target", "partial", "ambiguous"):
            status = "failed"
        else:
            status = "incomplete"
        rows.append(evidence.scenario_row(
            result.event.event_id,
            status,
            detail={
                "event_status": result.status,
                "counts": result.counts,
                "wall_skew_ms": result.skew_point_ms,
                "wall_skew_upper_ms": result.skew_upper_ms,
                "failure_reason": result.failure_reason,
            },
        ))
    return rows


def _checks(analysis: Analysis) -> list[dict[str, Any]]:
    full = analysis.metrics["full_run"]
    steady = analysis.metrics["steady_state"]
    thresholds = analysis.metrics["thresholds"]
    timing = analysis.metrics["timing"]
    search_gaps = [
        interval for interval in analysis.unobserved_intervals
        if str(interval.get("reason", "")).startswith("search window")
    ]
    p95 = full["skew_ms"]["p95"]
    maximum = full["skew_ms"]["max"]
    upper_p95 = full["skew_upper_ms"]["p95"]
    upper_max = full["skew_upper_ms"]["max"]
    timestamps_present = (
        len(analysis.capture.frames) >= 2
        and timing["count"] == len(analysis.capture.frames)
        and all(frame.timestamp_s is not None for frame in analysis.capture.frames)
    )
    checks = [
        evidence.check_row(
            "capture frames carry actual timestamps",
            timestamps_present,
            frame_count=len(analysis.capture.frames),
            timing_source=analysis.timing_source,
            median_frame_interval_ms=timing["median_ms"],
        ),
        evidence.check_row(
            "timing source is manifest or ffprobe",
            analysis.timing_source in ("manifest", "ffprobe"),
            timing_source=analysis.timing_source,
            nominal_fps_metadata_only=analysis.capture.camera.nominal_fps,
        ),
        evidence.check_row(
            "rolling-shutter readout measured",
            analysis.capture.camera.readout_measured,
            readout_us=analysis.capture.camera.readout_us,
            direction=analysis.capture.camera.readout_direction,
        ),
        evidence.check_row(
            "all manifest frames decoded",
            not analysis.frame_errors,
            frame_errors=len(analysis.frame_errors),
        ),
        evidence.check_row(
            "all search windows fully observed",
            not search_gaps,
            gaps=len(search_gaps),
        ),
        evidence.check_row(
            "at least 100 complete events",
            full["complete_events"] >= analysis.config.minimum_complete_events,
            complete_events=full["complete_events"],
            required=analysis.config.minimum_complete_events,
        ),
        evidence.check_row(
            "no failed events",
            not full["failed_event_ids"],
            failed_event_ids=full["failed_event_ids"],
        ),
        evidence.check_row(
            "no ambiguous or unobserved events",
            not full["ambiguous_event_ids"] and not full["unobserved_event_ids"],
            ambiguous_event_ids=full["ambiguous_event_ids"],
            unobserved_event_ids=full["unobserved_event_ids"],
        ),
        evidence.check_row(
            "p95 point skew within 100 ms",
            p95 is not None and p95 <= analysis.config.p95_limit_ms,
            p95_ms=p95,
            limit_ms=analysis.config.p95_limit_ms,
        ),
        evidence.check_row(
            "max point skew within 250 ms",
            maximum is not None and maximum <= analysis.config.max_limit_ms,
            max_ms=maximum,
            limit_ms=analysis.config.max_limit_ms,
        ),
        evidence.check_row(
            "conservative p95 bound within 100 ms",
            upper_p95 is not None and upper_p95 <= analysis.config.p95_limit_ms,
            p95_upper_ms=upper_p95,
            limit_ms=analysis.config.p95_limit_ms,
        ),
        evidence.check_row(
            "conservative max bound within 250 ms",
            upper_max is not None and upper_max <= analysis.config.max_limit_ms,
            max_upper_ms=upper_max,
            limit_ms=analysis.config.max_limit_ms,
        ),
        evidence.check_row(
            "threshold observation is within-threshold-observation-only",
            thresholds["status"] == "within-threshold",
            threshold_status=thresholds["status"],
            observation=thresholds["observation"],
            failed_events=len(full["failed_event_ids"]),
            ambiguous_events=len(full["ambiguous_event_ids"]),
            unobserved_events=len(full["unobserved_event_ids"]),
        ),
        evidence.check_row(
            "steady-state threshold observation is separate",
            steady["events_total"] == 0
            or thresholds["steady_state"]["status"] in ("within-threshold", "insufficient-events"),
            steady_status=thresholds["steady_state"]["status"],
            steady_complete_events=steady["complete_events"],
        ),
    ]
    if analysis.ocr_requested:
        checks.append(evidence.check_row(
            "burned-in source frames verified",
            analysis.video_sync == "verified-by-burned-in-frames",
            video_sync=analysis.video_sync,
            source_frame_tracking=analysis.source_frame_tracking,
        ))
    if steady["events_total"] > 0:
        checks.append(evidence.check_row(
            "steady-state window is separately reported",
            thresholds["steady_state"]["complete_events"] == steady["complete_events"]
            and thresholds["steady_state"]["p95_ms"] == steady["skew_ms"]["p95"],
            complete_events=steady["complete_events"],
            p95_ms=steady["skew_ms"]["p95"],
            max_ms=steady["skew_ms"]["max"],
        ))
    return checks


def _unobserved_strings(analysis: Analysis) -> list[str]:
    rows: list[str] = []
    for interval in analysis.unobserved_intervals:
        rows.append(
            f"{interval.get('event_id') or 'capture'} "
            f"[{interval.get('start_s')}, {interval.get('end_s')}]: "
            f"{interval.get('reason')}"
        )
    return rows


def build_evidence_report(
    analysis: Analysis,
    *,
    artifacts: dict[str, dict[str, Any]],
    repository: dict[str, Any] | None = None,
) -> dict[str, Any]:
    full = analysis.metrics["full_run"]
    return evidence.build_report(
        tool=TOOL_NAME,
        tool_version=TOOL_VERSION,
        gate="optical-cut-timing",
        evidence_kind=analysis.capture.evidence_kind,
        started_at=analysis.started_at,
        finished_at=analysis.finished_at,
        checks=_checks(analysis),
        scenarios=_event_scenarios(analysis),
        expected_scenarios=[result.event.event_id for result in analysis.events],
        cohort=list(analysis.rois.panels),
        artifacts=artifacts,
        tools={
            "analyzer": {
                "name": TOOL_NAME,
                "version": TOOL_VERSION,
                "config": analysis.config.as_dict(),
            },
            "camera": {
                "model": analysis.capture.camera.model,
                "exposure_us": analysis.capture.camera.exposure_us,
                "gain": analysis.capture.camera.gain,
                "white_balance": analysis.capture.camera.white_balance,
                "orientation_deg": analysis.capture.camera.orientation_deg,
                "resolution": {
                    "width": analysis.capture.camera.width,
                    "height": analysis.capture.camera.height,
                },
                "rolling_shutter": {
                    "readout_us": analysis.capture.camera.readout_us,
                    "direction": analysis.capture.camera.readout_direction,
                    "measured": analysis.capture.camera.readout_measured,
                },
                "nominal_fps_metadata_only": analysis.capture.camera.nominal_fps,
            },
            "timing": analysis.metrics["timing"],
            "source_frame": {
                "tracking": analysis.source_frame_tracking,
                "video_sync": analysis.video_sync,
                "detail": analysis.video_sync_detail,
            },
            "external": tool_versions(),
        },
        skipped=[],
        unobserved=_unobserved_strings(analysis),
        limitations=limitations_for(analysis),
        repository=repository,
    )


def write_outputs(
    analysis: Analysis,
    out_dir: Path | str,
    *,
    input_paths: Sequence[Path] = (),
    repo_root: Path | None = None,
) -> dict[str, Any]:
    destination = Path(out_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    analysis_path = destination / "analysis.json"
    events_csv = destination / "events.csv"
    panels_csv = destination / "panels.csv"
    summary_path = destination / "summary.md"
    report_path = destination / "report.json"

    analysis_path.write_text(
        json.dumps(analysis_to_dict(analysis), indent=2, sort_keys=True) + "\n"
    )
    _write_events_csv(events_csv, analysis)
    _write_panels_csv(panels_csv, analysis)
    _write_summary_markdown(summary_path, analysis)

    artifact_paths = [
        *[Path(path) for path in input_paths],
        analysis_path,
        events_csv,
        panels_csv,
        summary_path,
    ]
    artifacts = evidence.artifact_hashes(artifact_paths)
    report = build_evidence_report(
        analysis,
        artifacts=artifacts,
        repository=evidence.repository_state(repo_root) if repo_root else None,
    )
    evidence.write_report(report_path, report)
    return {
        "out_dir": str(destination),
        "analysis": str(analysis_path),
        "events_csv": str(events_csv),
        "panels_csv": str(panels_csv),
        "summary_md": str(summary_path),
        "report": str(report_path),
        "report_data": report,
    }
