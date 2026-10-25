"""Synthetic and metric tests for the optical cut analyzer.

The fixtures validate the analyzer. They do not validate a panel, a camera or a
wall, and every evidence report must keep the optical gate MISSING.
"""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from tools.optical import fixtures
from tools.optical.cli import main as optical_main
from tools.optical.detect import analyze_capture
from tools.optical.inputs import load_capture, load_events, load_rois
from tools.optical.metrics import (
    EventMeasurement,
    build_metrics,
    evaluate_thresholds,
    window_metrics,
)
from tools.optical.model import AnalysisConfig, Camera, Capture, Frame
from tools.optical.report import build_evidence_report, write_outputs
from tools.optical.timing import (
    exposure_start_s,
    frame_interval_stats,
    panel_onset_interval,
    readout_fraction,
    sensor_to_delivered,
)
from tools.optical.video import (
    ToolUnavailable,
    decode_video,
    probe_frame_timestamps,
    read_source_frame,
)
from tools.validation import evidence

CASE_IDS = {
    "offset-0",
    "offset-30",
    "offset-80",
    "subframe",
    "threshold-100",
    "exceed-300",
    "rolling",
    "exposure-blur",
    "noise",
    "partial",
    "wrong-target",
    "repeated-colours",
    "repeated-drift",
    "missing",
    "variable-timing",
    "dropped-duplicated",
    "truncated",
    "early-cut",
    "startup",
}


@pytest.fixture(scope="module")
def suite(tmp_path_factory: pytest.TempPathFactory) -> dict:
    root = tmp_path_factory.mktemp("optical-suite")
    return fixtures.generate_suite(root)


@pytest.fixture(scope="module")
def analyses(suite: dict) -> dict[str, object]:
    config = AnalysisConfig()
    results: dict[str, object] = {}
    for case in suite["cases"]:
        case_dir = Path(case["directory"])
        capture = load_capture(case_dir / "manifest.json")
        rois = load_rois(case_dir / "rois.json", capture=capture)
        events = load_events(case_dir / "events.json")
        results[case["case_id"]] = analyze_capture(
            capture, rois, events, config=config
        )
    return results


def _case(suite: dict, case_id: str) -> dict:
    for case in suite["cases"]:
        if case["case_id"] == case_id:
            return case
    raise AssertionError(f"missing fixture case {case_id}")


def _analysis(analyses: dict[str, object], case_id: str):
    return analyses[case_id]  # type: ignore[return-value]


def _panel(analysis, panel_id: str):
    for panel in analysis.events[0].panels:
        if panel.panel_id == panel_id:
            return panel
    raise AssertionError(f"missing panel {panel_id}")


def _measurement(
    event_id: str,
    skew_ms: float,
    *,
    upper_ms: float | None = None,
    status: str = "observed",
    steady_state: bool = True,
    expected_panels: tuple[str, ...] = ("left", "right"),
    panel_statuses: dict[str, str] | None = None,
) -> EventMeasurement:
    if panel_statuses is None:
        panel_statuses = {
            panel: ("observed" if status == "observed" else "missing")
            for panel in expected_panels
        }
    return EventMeasurement(
        event_id=event_id,
        status=status,
        steady_state=steady_state,
        expected_panels=expected_panels,
        panel_statuses=panel_statuses,
        panel_offsets_ms={
            panel: 0.0 for panel in expected_panels if panel_statuses[panel] == "observed"
        },
        skew_ms=skew_ms if status == "observed" else None,
        skew_lower_ms=0.0 if status == "observed" else None,
        skew_upper_ms=(
            upper_ms if upper_ms is not None else skew_ms + 3.0
        ) if status == "observed" else None,
        width_ms=3.0 if status == "observed" else None,
        window_start_s=0.0,
        window_end_s=1.0,
        failure_reason=None if status == "observed" else "synthetic failure row",
    )


def test_suite_is_reproducible_and_declares_synthetic_evidence(suite: dict):
    assert set(CASE_IDS) == {case["case_id"] for case in suite["cases"]}
    index = json.loads(Path(suite["suite_path"]).read_text())
    assert "analyzer only" in index["note"]
    for case in suite["cases"]:
        manifest = json.loads(Path(case["manifest"]).read_text())
        assert manifest["schema"] == "tablet-wall-optical-capture/1"
        assert manifest["evidence_kind"] == "synthetic"
        assert manifest["camera"]["nominal_fps"] == 240
        assert len(manifest["frames"]) >= 2
        for row in manifest["frames"]:
            assert row["path"].startswith("frames/")
            assert isinstance(row["timestamp_s"], float)
            assert (Path(case["directory"]) / row["path"]).exists()


def test_known_offsets_are_recovered_within_the_stated_interval(analyses, suite):
    for case_id in ("offset-0", "offset-30", "offset-80"):
        analysis = _analysis(analyses, case_id)
        expectations = _case(suite, case_id)["expectations"]
        result = analysis.events[0]
        assert result.status == "observed"
        assert result.counts["observed"] == 2
        for panel_id in ("left", "right"):
            panel = _panel(analysis, panel_id)
            truth = expectations["true_onset_ms"][panel_id]
            assert panel.status == "observed"
            assert panel.lower_offset_ms - 1e-6 <= truth <= panel.upper_offset_ms + 1e-6, (
                case_id,
                panel_id,
                truth,
                panel.lower_offset_ms,
                panel.upper_offset_ms,
            )
            assert panel.confidence > 0.5
        assert result.skew_lower_ms - 1e-6 <= expectations["target_skew_ms"] <= result.skew_upper_ms + 1e-6
        assert abs(result.skew_point_ms - expectations["target_skew_ms"]) <= 3.5


def test_subframe_phase_interval_contains_the_true_phase(analyses, suite):
    analysis = _analysis(analyses, "subframe")
    expectations = _case(suite, "subframe")["expectations"]
    panel = _panel(analysis, "right")
    truth = expectations["true_onset_ms"]["right"]
    assert panel.status == "observed"
    assert panel.lower_offset_ms <= truth <= panel.upper_offset_ms
    # 10.4 ms is not an integer number of 4.167 ms frames.
    assert panel.onset_point_s is not None
    assert analysis.events[0].status == "observed"


def test_rolling_shutter_and_exposure_blur_keep_the_truth_in_the_interval(analyses, suite):
    rolling = _analysis(analyses, "rolling")
    for panel_id in ("left", "right"):
        panel = _panel(rolling, panel_id)
        assert panel.status == "observed"
        assert panel.lower_offset_ms <= 0.0 <= panel.upper_offset_ms
        assert panel.readout_offset_min_ms is not None
        assert panel.readout_offset_max_ms is not None
        assert panel.readout_offset_max_ms > panel.readout_offset_min_ms
    left = _panel(rolling, "left")
    right = _panel(rolling, "right")
    assert abs(left.readout_offset_min_ms - right.readout_offset_min_ms) > 0.5
    assert rolling.events[0].skew_lower_ms <= 0.0 <= rolling.events[0].skew_upper_ms

    blur = _analysis(analyses, "exposure-blur")
    expectations = _case(suite, "exposure-blur")["expectations"]
    for panel_id in ("left", "right"):
        panel = _panel(blur, panel_id)
        assert panel.status == "observed"
        assert panel.lower_offset_ms <= expectations["true_onset_ms"][panel_id] <= panel.upper_offset_ms
        assert panel.width_ms is not None and panel.width_ms >= 6.0


def test_orientation_and_exposure_basis_change_the_row_clock():
    camera = Camera(
        exposure_us=1000,
        orientation_deg=90,
        width=100,
        height=200,
        readout_us=1000,
        readout_direction="top-to-bottom",
        readout_measured=True,
    )
    # A 90-degree clockwise delivery maps delivered x to sensor y descending.
    assert readout_fraction(99, 0, camera) == pytest.approx(0.0)
    assert readout_fraction(0, 0, camera) == pytest.approx(1.0)
    turned = Camera(
        exposure_us=1000,
        orientation_deg=180,
        width=100,
        height=200,
        readout_us=1000,
        readout_direction="bottom-to-top",
        readout_measured=True,
    )
    assert readout_fraction(0, 0, turned) == pytest.approx(0.0)
    assert readout_fraction(0, 199, turned) == pytest.approx(1.0)
    assert exposure_start_s(10.0, "exposure_start", 1000) == 10.0
    assert exposure_start_s(10.0, "exposure_centre", 1000) == pytest.approx(9.9995)
    assert exposure_start_s(10.0, "exposure_end", 1000) == pytest.approx(9.999)


def test_onset_interval_uses_previous_exposure_end_and_onset_start():
    camera = Camera(
        exposure_us=1000,
        orientation_deg=0,
        width=10,
        height=10,
        readout_us=0,
        readout_direction="top-to-bottom",
        readout_measured=True,
    )
    interval = panel_onset_interval(1.0, 1.005, [(0.0, 0.0)], camera)
    assert interval.lower_s == pytest.approx(1.0)
    assert interval.upper_s == pytest.approx(1.006)
    assert interval.point_s == pytest.approx(1.003)
    assert interval.consistent


def test_partial_wrong_target_missing_and_repeated_colours_are_counted(analyses):
    partial = _analysis(analyses, "partial")
    assert partial.events[0].status == "partial"
    assert partial.events[0].counts["partial"] == 1
    assert _panel(partial, "right").status == "partial"
    assert _panel(partial, "right").target_fraction < 0.6

    wrong = _analysis(analyses, "wrong-target")
    assert wrong.events[0].status == "wrong-target"
    assert wrong.events[0].counts["wrong_target"] == 1
    assert _panel(wrong, "right").status == "wrong-target"

    missing = _analysis(analyses, "missing")
    assert missing.events[0].status == "missing"
    assert missing.events[0].counts["missing"] == 1
    assert _panel(missing, "right").status == "missing"

    repeated = _analysis(analyses, "repeated-colours")
    assert repeated.events[0].status == "ambiguous"
    assert repeated.events[0].counts["ambiguous"] == 1
    right = _panel(repeated, "right")
    assert right.status == "ambiguous"
    assert "already present" in (right.reason or "")
    assert _panel(repeated, "left").status == "observed"

    drifting = _analysis(analyses, "repeated-drift")
    assert drifting.events[0].status == "ambiguous"
    assert _panel(drifting, "right").status == "ambiguous"
    assert "already present" in (_panel(drifting, "right").reason or "")


def test_missing_wrong_partial_and_ambiguous_fail_their_events(tmp_path, analyses, suite):
    for case_id in ("missing", "wrong-target", "partial", "repeated-colours"):
        analysis = _analysis(analyses, case_id)
        case = _case(suite, case_id)
        out = tmp_path / case_id
        result = write_outputs(
            analysis,
            out,
            input_paths=[
                Path(case["manifest"]),
                Path(case["rois"]),
                Path(case["events"]),
            ],
            repo_root=Path.cwd(),
        )
        report = evidence.load_report(Path(result["report"]))
        assert report["completion"] == "incomplete"
        assert report["hardware_gate_status"] == "MISSING"
        assert report["hardware_claim"] is False
        assert case_id in report["failure_reasons"]
        with (out / "events.csv").open() as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == 1
        assert rows[0]["status"] != "observed"
        assert rows[0]["failure_reason"]


def test_variable_timing_dropped_and_duplicated_frames_are_reported(analyses):
    variable = _analysis(analyses, "variable-timing")
    assert variable.events[0].status == "observed"
    timing = variable.metrics["timing"]
    assert timing["source"] == "manifest"
    assert timing["maximum_ms"] > timing["minimum_ms"]
    assert 4.0 < timing["median_ms"] < 4.4

    dropped = _analysis(analyses, "dropped-duplicated")
    assert dropped.events[0].status == "observed"
    assert 27 in dropped.capture.dropped_frames
    assert 24 in dropped.capture.duplicated_frames
    assert any(
        "27" in str(interval["reason"])
        for interval in dropped.unobserved_intervals
    )
    assert any(
        "duplicate frame timestamp" in str(interval["reason"])
        for interval in dropped.unobserved_intervals
    )
    baseline = _analysis(analyses, "offset-30")
    assert _panel(dropped, "right").width_ms > _panel(baseline, "right").width_ms


def test_truncated_capture_is_unobserved_not_missing(analyses):
    truncated = _analysis(analyses, "truncated")
    assert truncated.events[0].status == "unobserved"
    right = _panel(truncated, "right")
    assert right.status == "unobserved"
    assert "past the last decoded frame" in (right.reason or "")
    assert any(
        "past the last decoded frame" in str(interval["reason"])
        for interval in truncated.unobserved_intervals
    )
    assert truncated.metrics["thresholds"]["gate_evaluable"] is False


def test_early_cut_before_the_reference_is_observed(analyses, suite):
    analysis = _analysis(analyses, "early-cut")
    expectations = _case(suite, "early-cut")["expectations"]
    assert analysis.events[0].status == "observed"
    for panel_id in ("left", "right"):
        panel = _panel(analysis, panel_id)
        truth = expectations["true_onset_ms"][panel_id]
        assert truth < 0
        assert panel.point_offset_ms < 0
        assert panel.lower_offset_ms <= truth <= panel.upper_offset_ms


def test_declared_steady_state_and_recovery_are_separate(analyses):
    startup = _analysis(analyses, "startup")
    assert startup.events[0].status == "observed"
    assert startup.metrics["full_run"]["events_total"] == 1
    assert startup.metrics["steady_state"]["events_total"] == 0
    assert startup.metrics["recovery"]["events_total"] == 1
    assert startup.metrics["recovery"]["event_ids"] == ["startup"]
    assert startup.recovery_intervals[0]["event_id"] == "startup"


def test_threshold_boundary_uncertainty_is_inconclusive(analyses):
    analysis = _analysis(analyses, "threshold-100")
    assert analysis.events[0].status == "observed"
    assert analysis.events[0].skew_point_ms == pytest.approx(100.0, abs=1.5)
    assert analysis.events[0].skew_upper_ms > 100.0
    thresholds = analysis.metrics["thresholds"]
    assert thresholds["status"] == "inconclusive"
    assert thresholds["within_threshold_observation_only"] is False
    assert thresholds["observation"] == "not-evaluable"


def test_overshoot_max_and_p95_are_not_reported_as_a_pass(analyses):
    analysis = _analysis(analyses, "exceed-300")
    result = analysis.events[0]
    assert result.status == "observed"
    assert result.skew_point_ms > 250
    thresholds = analysis.metrics["thresholds"]
    assert thresholds["status"] == "exceeded"
    assert thresholds["observation"] != "pass"
    assert thresholds["within_threshold_observation_only"] is False


def test_p95_and_conservative_upper_bounds_drive_the_status():
    config = AnalysisConfig()
    good = [_measurement(f"good-{index}", 80.0, upper_ms=95.0) for index in range(100)]
    good_window = window_metrics(good, config)
    verdict = evaluate_thresholds(good_window, good_window, config)
    assert verdict["status"] == "within-threshold"
    assert verdict["gate_evaluable"] is True
    assert verdict["observation"] == "within-threshold-observation-only"
    assert verdict["observation"] != "pass"
    assert verdict["within_threshold_observation_only"] is True

    short = window_metrics(good[:99], config)
    short_verdict = evaluate_thresholds(short, short, config)
    assert short_verdict["status"] == "within-threshold"
    assert short_verdict["gate_evaluable"] is False
    assert short_verdict["observation"] == "not-evaluable"
    assert short_verdict["within_threshold_observation_only"] is False

    high_p95 = [
        _measurement(f"low-{index}", 80.0, upper_ms=95.0) for index in range(90)
    ] + [
        _measurement(f"high-{index}", 150.0, upper_ms=160.0) for index in range(10)
    ]
    high_window = window_metrics(high_p95, config)
    high_verdict = evaluate_thresholds(high_window, high_window, config)
    assert high_window["skew_ms"]["p95"] > 100.0
    assert high_verdict["status"] == "exceeded"

    high_max = [
        _measurement(f"low-{index}", 80.0, upper_ms=95.0) for index in range(99)
    ] + [_measurement("max", 300.0, upper_ms=310.0)]
    max_window = window_metrics(high_max, config)
    max_verdict = evaluate_thresholds(max_window, max_window, config)
    assert max_window["skew_ms"]["max"] > 250.0
    assert max_verdict["status"] == "exceeded"

    uncertain = [_measurement(f"uncertain-{index}", 90.0, upper_ms=110.0) for index in range(100)]
    uncertain_window = window_metrics(uncertain, config)
    uncertain_verdict = evaluate_thresholds(uncertain_window, uncertain_window, config)
    assert uncertain_verdict["status"] == "inconclusive"
    assert uncertain_verdict["within_threshold_observation_only"] is False


def test_failures_survive_a_hundred_complete_events():
    config = AnalysisConfig()
    good = [_measurement(f"good-{index}", 80.0, upper_ms=95.0) for index in range(100)]
    bad = _measurement(
        "missing-participant",
        0.0,
        status="missing",
        panel_statuses={"left": "observed", "right": "missing"},
    )
    all_events = window_metrics([*good, bad], config)
    assert all_events["complete_events"] == 100
    assert all_events["events_total"] == 101
    assert all_events["failed_event_ids"] == ["missing-participant"]
    assert all_events["failures"][0]["event_id"] == "missing-participant"
    assert all_events["gate_evaluable"] is False
    verdict = evaluate_thresholds(all_events, all_events, config)
    assert verdict["status"] == "within-threshold"
    assert verdict["observation"] == "not-evaluable"
    assert verdict["within_threshold_observation_only"] is False


def test_full_run_and_steady_state_are_evaluated_separately():
    config = AnalysisConfig()
    steady = [_measurement(f"steady-{index}", 80.0, upper_ms=95.0) for index in range(100)]
    recovery = _measurement("recovery", 300.0, upper_ms=310.0, steady_state=False)
    full = window_metrics([*steady, recovery], config)
    steady_only = window_metrics(steady, config)
    verdict = evaluate_thresholds(full, steady_only, config)
    assert full["events_total"] == 101
    assert steady_only["events_total"] == 100
    assert full["skew_ms"]["max"] > 250.0
    assert steady_only["skew_ms"]["max"] < 100.0
    assert verdict["status"] == "exceeded"
    assert verdict["full_run"]["status"] == "exceeded"
    assert verdict["steady_state"]["status"] == "within-threshold"


def test_evidence_report_keeps_the_gate_missing_and_hashes_artifacts(
    tmp_path, analyses, suite
):
    case = _case(suite, "offset-30")
    analysis = _analysis(analyses, "offset-30")
    result = write_outputs(
        analysis,
        tmp_path / "out",
        input_paths=[Path(case["manifest"]), Path(case["rois"]), Path(case["events"])],
        repo_root=Path.cwd(),
    )
    report = evidence.load_report(Path(result["report"]))
    assert report["schema"] == "tablet-wall-validation-evidence/1"
    assert report["gate"] == "optical-cut-timing"
    assert report["evidence_kind"] == "synthetic"
    assert report["hardware_gate_status"] == "MISSING"
    assert report["hardware_claim"] is False
    assert report["completion"] == "incomplete"
    assert report["checks_total"] >= 10
    assert any("at least 100 complete events" in reason for reason in report["failure_reasons"])
    assert any("analyzer only" in limitation for limitation in report["limitations"])
    assert report["scenarios_total"] == 1
    assert report["scenarios"][0]["id"] == "offset-30"
    assert report["scenarios"][0]["status"] == "passed"
    assert report["artifacts"]
    for path, row in report["artifacts"].items():
        assert row["exists"] is True
        assert row["bytes"] is not None
        assert len(row["sha256"]) == 64
    analysis_json = json.loads(Path(result["analysis"]).read_text())
    assert "gate" not in analysis_json
    assert "hardware_gate_status" not in json.dumps(analysis_json)
    assert analysis_json["metrics"]["full_run"]["complete_events"] == 1
    assert len(analysis_json["events"]) == 1
    assert analysis_json["timing"]["source"] == "manifest"
    assert analysis_json["rois"]["coordinate_space"] == "delivered"
    assert (Path(result["out_dir"]) / "summary.md").read_text().count("MISSING") >= 1


def test_a_hundred_event_report_can_complete_but_the_gate_stays_missing(analyses):
    real = _analysis(analyses, "offset-30")
    config = AnalysisConfig()
    good = [
        _measurement(f"cut-{index:03d}", 80.0, upper_ms=95.0)
        for index in range(100)
    ]
    full = window_metrics(good, config)
    steady = window_metrics(good, config)
    thresholds = evaluate_thresholds(full, steady, config)
    metrics = {
        "timing": real.metrics["timing"],
        "full_run": full,
        "steady_state": steady,
        "recovery": {"events_total": 0, "event_ids": [], "intervals": []},
        "thresholds": thresholds,
    }
    analysis = replace(real, events=[], metrics=metrics)
    report = build_evidence_report(analysis, artifacts={}, repository={})
    assert report["completion"] == "complete"
    assert report["checks_passed"] == report["checks_total"]
    assert report["hardware_gate_status"] == "MISSING"
    assert report["hardware_claim"] is False
    assert report["scenarios_total"] == 0
    assert report["failure_reasons"] == []


def test_events_csv_and_patch_target_parse(tmp_path):
    patch = tmp_path / "patch.png"
    Image.new("RGB", (8, 8), (10, 20, 30)).save(patch)
    csv_path = tmp_path / "events.csv"
    csv_path.write_text(
        "event_id,reference_frame,search_before_ms,search_after_ms,"
        "expected_panels,target_r,target_g,target_b,target_tolerance,"
        "min_target_fraction,steady_state,source_frame\n"
        "cut-1,10,50,200,left;right,0,200,0,30,0.6,true,42\n"
        "cut-2,12,0,150,left;right,1,2,3,25,0.7,yes,\n"
    )
    events = load_events(csv_path)
    assert [event.event_id for event in events] == ["cut-1", "cut-2"]
    assert events[0].expected_panels == ("left", "right")
    assert events[0].target_rgb == (0.0, 200.0, 0.0)
    assert events[0].steady_state is True
    assert events[0].source_frame == 42
    assert events[1].search_before_s == 0.0
    assert events[1].steady_state is True

    json_path = tmp_path / "events.json"
    json_path.write_text(json.dumps({
        "schema": "tablet-wall-optical-events/1",
        "events": [{
            "event_id": "patch-event",
            "reference_time_s": 1.0,
            "expected_panels": ["left", "right"],
            "target": {"patch": "patch.png", "tolerance": 20},
            "search_window": {"before_ms": 10, "after_ms": 20},
        }],
    }))
    patch_events = load_events(json_path)
    assert patch_events[0].target_rgb == pytest.approx((10.0, 20.0, 30.0))


def test_manifest_requires_actual_timestamps_and_nominal_fps_is_not_timing(tmp_path):
    manifest = {
        "schema": "tablet-wall-optical-capture/1",
        "capture_id": "bad",
        "evidence_kind": "synthetic",
        "camera": {
            "exposure_us": 500,
            "orientation_deg": 0,
            "gain": "manual fixed",
            "white_balance": "manual 5600 K",
            "resolution": {"width": 10, "height": 10},
            "rolling_shutter": {
                "readout_us": 1000,
                "direction": "top-to-bottom",
                "measured": True,
            },
            "nominal_fps": 240,
        },
        "frames": [
            {"index": 0, "path": "frame.png"},
            {"index": 1, "path": "frame.png", "timestamp_s": 0.01},
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="timestamp"):
        load_capture(path)

    good = json.loads(path.read_text())
    good["frames"] = [
        {"index": 0, "path": "frame.png", "timestamp_s": 0.0},
        {"index": 1, "path": "frame.png", "timestamp_s": 0.01},
    ]
    path.write_text(json.dumps(good))
    capture = load_capture(path)
    stats = frame_interval_stats(capture)
    assert stats.median_s == pytest.approx(0.01)
    assert stats.nominal_fps == 240
    assert any("metadata only" in warning for warning in capture.warnings)


def test_fixture_cli_reproduces_the_suite(tmp_path):
    code = optical_main(["fixtures", "--out", str(tmp_path / "generated")])
    assert code == 0
    suite = json.loads((tmp_path / "generated" / "suite.json").read_text())
    assert {case["case_id"] for case in suite["cases"]} == CASE_IDS
    manifest = json.loads(
        (tmp_path / "generated" / "cases" / "offset-30" / "manifest.json").read_text()
    )
    assert manifest["camera"]["nominal_fps"] == 240
    assert len(manifest["frames"]) > 10


def test_video_decode_uses_ffprobe_timestamps(tmp_path, suite):
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe not installed")
    frame_dir = Path(_case(suite, "offset-30")["directory"]) / "frames"
    work = tmp_path / "video-input"
    work.mkdir()
    for index, path in enumerate(sorted(frame_dir.glob("*.png"))[:8]):
        shutil.copy(path, work / f"{index:06d}.png")
    video = tmp_path / "clip.mp4"
    encode = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-framerate", "60",
            "-i", str(work / "%06d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(video),
        ],
        capture_output=True,
    )
    if encode.returncode != 0:
        pytest.skip("ffmpeg cannot encode the test clip")
    timestamps = probe_frame_timestamps(video)
    decoded_dir = tmp_path / "decoded"
    decoded_dir.mkdir()
    sentinel = decoded_dir / "important.png"
    sentinel.write_bytes(b"keep me")
    unicode_sentinel = decoded_dir / "\u0660\u0660\u0660\u0660\u0660\u0660.png"
    unicode_sentinel.write_bytes(b"keep me too")
    frames = decode_video(video, decoded_dir)
    assert sentinel.exists()
    assert unicode_sentinel.exists()
    assert len(timestamps) == 8
    assert len(frames) == 8
    intervals = [
        later - earlier for earlier, later in zip(timestamps, timestamps[1:])
    ]
    assert all(0.015 <= interval <= 0.018 for interval in intervals)
    assert all((tmp_path / "decoded" / f"{index:06d}.png").exists() for index in range(8))

    manifest_path = tmp_path / "video-manifest.json"
    manifest_path.write_text(json.dumps({
        "schema": "tablet-wall-optical-capture/1",
        "capture_id": "video-fixture",
        "evidence_kind": "synthetic",
        "camera": {
            "exposure_us": 500,
            "orientation_deg": 0,
            "gain": "synthetic",
            "white_balance": "synthetic",
            "resolution": {"width": 320, "height": 240},
            "rolling_shutter": {
                "readout_us": 4000,
                "direction": "top-to-bottom",
                "measured": True,
            },
            "nominal_fps": 240,
        },
        "video": {"path": str(video)},
        "frames": [],
    }))
    capture = load_capture(manifest_path, decoded_dir=tmp_path / "manifest-decoded")
    assert len(capture.frames) == 8
    assert capture.frames[0].path is not None and capture.frames[0].path.exists()
    assert any("ffprobe" in warning for warning in capture.warnings)
    assert frame_interval_stats(capture, timing_source="ffprobe").median_s == pytest.approx(
        intervals[0], abs=1e-6
    )


def test_source_frame_tracking_is_false_without_a_burned_in_roi(analyses):
    analysis = _analysis(analyses, "offset-30")
    assert analysis.source_frame_tracking is False
    assert analysis.video_sync == "not-verified"
    assert "OCR was not requested" in analysis.video_sync_detail or "ROI" in analysis.video_sync_detail
    assert analysis.events[0].source_frame["status"] == "no-source-frame-roi"


def test_tesseract_reads_a_burned_in_frame_number(tmp_path):
    if shutil.which("tesseract") is None:
        pytest.skip("tesseract not installed")
    image = Image.new("RGB", (400, 120), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 64)
    except OSError:
        font = ImageFont.load_default(size=64)
    draw.text((20, 20), "000123", fill="black", font=font)
    path = tmp_path / "burned.png"
    image.save(path)
    try:
        value = read_source_frame(path, (0, 0, 400, 120), 6)
    except ToolUnavailable as error:
        pytest.skip(str(error))
    assert value == 123


@pytest.mark.parametrize(("key", "message"), [
    ("orientation_deg", "orientation_deg is required"),
    ("gain", "gain is required"),
    ("white_balance", "white_balance is required"),
])
def test_camera_metadata_is_required(tmp_path, suite, key, message):
    manifest = json.loads(
        (Path(_case(suite, "offset-30")["directory"]) / "manifest.json").read_text()
    )
    del manifest["camera"][key]
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match=message):
        load_capture(path)


def test_fractional_integer_metadata_is_rejected(tmp_path, suite):
    manifest = json.loads(
        (Path(_case(suite, "offset-30")["directory"]) / "manifest.json").read_text()
    )
    for value in (90.5, -0.5):
        broken = json.loads(json.dumps(manifest))
        broken["camera"]["orientation_deg"] = value
        path = tmp_path / f"orientation-{value}.json"
        path.write_text(json.dumps(broken))
        with pytest.raises(ValueError, match="must be an integer"):
            load_capture(path)


def test_noise_reference_is_required_and_must_stay_inside_the_panel(tmp_path, suite):
    case_dir = Path(_case(suite, "offset-30")["directory"])
    capture = load_capture(case_dir / "manifest.json")
    raw = json.loads((case_dir / "rois.json").read_text())

    missing = json.loads(json.dumps(raw))
    del missing["panels"][0]["noise_reference"]
    missing_path = tmp_path / "missing-noise.json"
    missing_path.write_text(json.dumps(missing))
    with pytest.raises(ValueError, match="noise_reference is required"):
        load_rois(missing_path, capture=capture)

    outside = json.loads(json.dumps(raw))
    outside["panels"][1]["noise_reference"] = {
        "polygon": [[0, 0], [5, 0], [5, 5], [0, 5]],
        "sample_points": [[1, 1], [2, 2], [3, 3], [4, 4]],
        "sample_radius": 1,
    }
    outside_path = tmp_path / "outside-noise.json"
    outside_path.write_text(json.dumps(outside))
    with pytest.raises(ValueError, match="outside the panel polygon"):
        load_rois(outside_path, capture=capture)


def test_explicit_probe_points_must_span_rows_and_columns(tmp_path, suite):
    case_dir = Path(_case(suite, "offset-30")["directory"])
    capture = load_capture(case_dir / "manifest.json")
    raw = json.loads((case_dir / "rois.json").read_text())
    raw["panels"][0]["sample_points"] = [[40, 80], [60, 80], [80, 80]]
    path = tmp_path / "collapsed-roi.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="at least two rows and two columns"):
        load_rois(path, capture=capture)


def test_sensor_space_rois_are_mapped_through_orientation(tmp_path):
    camera = Camera(
        exposure_us=1000,
        orientation_deg=90,
        width=100,
        height=200,
        readout_us=1000,
        readout_direction="top-to-bottom",
        readout_measured=True,
    )
    capture = Capture(
        capture_id="oriented",
        evidence_kind="synthetic",
        camera=camera,
        frames=(Frame(0, None, 0.0), Frame(1, None, 0.005)),
        dropped_frames=frozenset(),
        duplicated_frames=frozenset(),
        timestamp_basis="exposure_start",
        manifest_path=tmp_path / "manifest.json",
    )
    payload = {
        "schema": "tablet-wall-optical-rois/1",
        "coordinate_space": "sensor",
        "panels": [{
            "panel_id": "left",
            "polygon": [[10, 10], [190, 10], [190, 90], [10, 90]],
            "sample_points": [[20, 20], [180, 20], [180, 80], [20, 80]],
            "sample_radius": 1,
            "noise_reference": {
                "polygon": [[30, 30], [60, 30], [60, 60], [30, 60]],
                "sample_points": [[35, 35], [55, 35], [55, 55], [35, 55]],
                "sample_radius": 1,
            },
        }],
    }
    path = tmp_path / "sensor-rois.json"
    path.write_text(json.dumps(payload))
    rois = load_rois(path, capture=capture)
    assert rois.coordinate_space == "sensor"
    assert rois.panels["left"].region.polygon[0] == pytest.approx(
        sensor_to_delivered(10, 10, camera)
    )
    for x, y in rois.panels["left"].region.sample_points:
        assert 0 <= x < camera.width and 0 <= y < camera.height


def test_single_panel_event_is_rejected(tmp_path):
    payload = {
        "schema": "tablet-wall-optical-events/1",
        "events": [{
            "event_id": "single",
            "reference_frame": 20,
            "expected_panels": ["left"],
            "target": {"rgb": [0, 200, 0]},
        }],
    }
    path = tmp_path / "events.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="at least two expected panels"):
        load_events(path)


def test_unmeasured_readout_is_not_gate_evaluable(tmp_path, suite):
    case_dir = Path(_case(suite, "offset-30")["directory"])
    manifest = json.loads((case_dir / "manifest.json").read_text())
    manifest["camera"]["rolling_shutter"]["measured"] = False
    for frame in manifest["frames"]:
        frame["path"] = str(case_dir / frame["path"])
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    capture = load_capture(manifest_path)
    rois = load_rois(case_dir / "rois.json", capture=capture)
    events = load_events(case_dir / "events.json")
    one = analyze_capture(capture, rois, events)

    template = one.events[0]
    results = [
        replace(
            template,
            event=replace(template.event, event_id=f"cut-{index:03d}"),
            panels=[replace(panel) for panel in template.panels],
        )
        for index in range(100)
    ]
    config = AnalysisConfig()
    metrics = build_metrics(
        results, config, timing_source="manifest", capture=capture
    )
    assert any(
        "not marked measured" in reason
        for reason in metrics["full_run"]["evaluable_reasons"]
    )
    assert metrics["full_run"]["complete_events"] == 100
    assert metrics["thresholds"]["gate_evaluable"] is False
    assert metrics["thresholds"]["status"] == "within-threshold"
    assert metrics["thresholds"]["within_threshold_observation_only"] is False

    analysis = replace(one, events=results, metrics=metrics)
    result = write_outputs(analysis, tmp_path / "out", repo_root=Path.cwd())
    report = evidence.load_report(Path(result["report"]))
    check = next(
        item for item in report["checks"]
        if item["name"] == "rolling-shutter readout measured"
    )
    assert check["passed"] is False
    threshold_check = next(
        item for item in report["checks"]
        if item["name"] == "threshold observation is within-threshold-observation-only"
    )
    assert threshold_check["passed"] is False
    assert report["hardware_gate_status"] == "MISSING"
    assert report["hardware_claim"] is False


def test_cli_error_report_preserves_synthetic_evidence_kind(tmp_path, suite):
    case_dir = Path(_case(suite, "offset-30")["directory"])
    out = tmp_path / "out"
    code = optical_main([
        "analyze",
        "--manifest", str(case_dir / "manifest.json"),
        "--rois", str(case_dir / "missing-rois.json"),
        "--events", str(case_dir / "events.json"),
        "--out", str(out),
    ])
    assert code == 2
    report = evidence.load_report(out / "report.json")
    assert report["evidence_kind"] == "synthetic"
    assert report["gate"] == "optical-cut-timing"
    assert report["hardware_gate_status"] == "MISSING"
    assert report["hardware_claim"] is False
    assert "analysis completed" in report["failure_reasons"]


@pytest.mark.parametrize(("declared", "expected"), [
    ("operator-hardware", "operator-hardware"),
    (" synthetic ", "synthetic"),
])
def test_cli_error_report_preserves_declared_kind(tmp_path, suite, declared, expected):
    case_dir = Path(_case(suite, "offset-30")["directory"])
    manifest = json.loads((case_dir / "manifest.json").read_text())
    manifest["evidence_kind"] = declared
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    out = tmp_path / "out"
    code = optical_main([
        "analyze",
        "--manifest", str(manifest_path),
        "--rois", str(case_dir / "missing-rois.json"),
        "--events", str(case_dir / "events.json"),
        "--out", str(out),
    ])
    assert code == 2
    report = evidence.load_report(out / "report.json")
    assert report["evidence_kind"] == expected
    assert report["hardware_gate_status"] == "MISSING"


def test_cli_writes_evidence_for_an_unreadable_manifest(tmp_path, suite):
    case_dir = Path(_case(suite, "offset-30")["directory"])
    manifest = json.loads((case_dir / "manifest.json").read_text())
    manifest_path = tmp_path / "manifest-utf16.json"
    manifest_path.write_bytes(json.dumps(manifest).encode("utf-16"))
    out = tmp_path / "out"
    code = optical_main([
        "analyze",
        "--manifest", str(manifest_path),
        "--rois", str(case_dir / "rois.json"),
        "--events", str(case_dir / "events.json"),
        "--out", str(out),
    ])
    assert code == 2
    report = evidence.load_report(out / "report.json")
    assert report["gate"] == "optical-cut-timing"
    assert report["hardware_gate_status"] == "MISSING"
    assert report["hardware_claim"] is False
    assert "analysis completed" in report["failure_reasons"]


def _source_frame_events(tmp_path, suite, sources, references):
    tmp_path.mkdir(parents=True, exist_ok=True)
    case_dir = Path(_case(suite, "offset-30")["directory"])
    rois = json.loads((case_dir / "rois.json").read_text())
    rois["source_frame_roi"] = [0, 0, 20, 20]
    rois["source_frame_digits"] = 6
    rois_path = tmp_path / "rois.json"
    rois_path.write_text(json.dumps(rois))
    events = {
        "schema": "tablet-wall-optical-events/1",
        "events": [
            {
                "event_id": f"event-{index}",
                "reference_frame": reference,
                "search_window": {"before_ms": 40, "after_ms": 160},
                "expected_panels": ["left", "right"],
                "target": {"rgb": [0, 200, 0]},
                "source_frame": source,
            }
            for index, (source, reference) in enumerate(zip(sources, references))
        ],
    }
    events_path = tmp_path / "events.json"
    events_path.write_text(json.dumps(events))
    return case_dir, rois_path, events_path


def test_video_failure_leaves_the_existing_frame_set_untouched(tmp_path):
    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe not installed")
    destination = tmp_path / "decoded"
    destination.mkdir()
    old_frame = destination / "000000.png"
    old_frame.write_bytes(b"old frame")
    sentinel = destination / "keep.png"
    sentinel.write_bytes(b"keep")
    bad_video = tmp_path / "bad.mp4"
    bad_video.write_bytes(b"not a video")
    with pytest.raises((ValueError, ToolUnavailable)):
        decode_video(bad_video, destination)
    assert old_frame.exists()
    assert sentinel.exists()


def test_source_frame_tracking_requires_every_declared_check(tmp_path, suite, monkeypatch):
    def fake_read(image_path, roi, digits, *, tesseract_cmd="tesseract"):
        return {"000020": 42, "000021": 43}[Path(image_path).stem]

    monkeypatch.setattr("tools.optical.detect.read_source_frame", fake_read)
    case_dir = Path(_case(suite, "offset-30")["directory"])
    capture = load_capture(case_dir / "manifest.json")

    positive = _source_frame_events(
        tmp_path / "positive", suite, [42, 43], [20, 21]
    )
    rois = load_rois(positive[1], capture=capture)
    events = load_events(positive[2])
    verified = analyze_capture(capture, rois, events, ocr=True)
    assert verified.source_frame_tracking is True
    assert verified.video_sync == "verified-by-burned-in-frames"

    skipped_root = tmp_path / "skipped"
    skipped_root.mkdir()
    skipped = _source_frame_events(
        skipped_root, suite, [42, 43, 44], [20, 21, 999]
    )
    skipped_analysis = analyze_capture(
        capture, load_rois(skipped[1], capture=capture), load_events(skipped[2]), ocr=True
    )
    assert skipped_analysis.source_frame_tracking is False
    assert skipped_analysis.video_sync == "not-verified"
    assert "every declared check" in skipped_analysis.video_sync_detail

    duplicate_root = tmp_path / "duplicate"
    duplicate_root.mkdir()
    duplicate = _source_frame_events(
        duplicate_root, suite, [42, 42], [20, 21]
    )
    duplicate_analysis = analyze_capture(
        capture,
        load_rois(duplicate[1], capture=capture),
        load_events(duplicate[2]),
        ocr=True,
    )
    assert duplicate_analysis.source_frame_tracking is False
    assert duplicate_analysis.video_sync == "not-verified"
    assert "not strictly increasing" in duplicate_analysis.video_sync_detail
