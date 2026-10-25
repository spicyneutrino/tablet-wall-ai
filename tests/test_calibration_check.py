"""Calibration checker: physical measurements, 2 mm gate, uncertainty and revisions.

The fixtures are synthetic worksheets, not measurements of a panel. Each test
names the defect it proves: a numeric failure, an uncertainty crossing the
threshold, asymmetric bezels, a rotated mount, a missing/duplicate edge, a
stale revision, a missing photo or a derived-geometry row. An inconclusive row
is never reported as a pass, and the hardware gate is never promoted.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from tools.calibration import check_measurements as calibration
from tools.validation import evidence

COLUMNS = list(calibration.REQUIRED_COLUMNS) + list(calibration.OPTIONAL_COLUMNS)


def row(**overrides: object) -> dict[str, str]:
    base: dict[str, str] = {
        "edge_id": "e1",
        "left_panel_id": "ipad-a",
        "right_panel_id": "ipad-b",
        "left_active_width_mm": "196.0",
        "left_active_height_mm": "261.0",
        "left_bezel_left_mm": "6",
        "left_bezel_top_mm": "6",
        "left_bezel_right_mm": "6",
        "left_bezel_bottom_mm": "6",
        "right_active_width_mm": "196.0",
        "right_active_height_mm": "261.0",
        "right_bezel_left_mm": "6",
        "right_bezel_top_mm": "6",
        "right_bezel_right_mm": "6",
        "right_bezel_bottom_mm": "6",
        "intended_gap_mm": "3",
        "measured_seam_displacement_mm": "0.8",
        "uncertainty_mm": "0.3",
        "left_profile_revision": "1",
        "left_calibration_revision": "4",
        "right_profile_revision": "1",
        "right_calibration_revision": "4",
        "view_revision": "view-7",
        "photo_path": "photos/e1.jpg",
        "method": "steel ruler with tripod photo",
        "axis": "horizontal",
    }
    base.update({key: str(value) for key, value in overrides.items()})
    return base


def write_sheet(tmp_path: Path, rows: list[dict[str, str]], *,
                photos: list[str] | None = None) -> Path:
    directory = tmp_path / "photos"
    directory.mkdir(parents=True, exist_ok=True)
    for index, name in enumerate(photos if photos is not None else ["e1.jpg"]):
        (directory / name).write_bytes(b"photo-%d" % index)
    path = tmp_path / "sheet.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def evaluate(tmp_path: Path, rows: list[dict[str, str]], *,
             options: calibration.Options | None = None,
             photos: list[str] | None = None):
    path = write_sheet(tmp_path, rows, photos=photos)
    report, results, global_checks = calibration.evaluate_file(
        path, options or calibration.Options(), "synthetic",
        started_at="2026-10-25T00:00:00Z",
    )
    return report, results, global_checks, path


def only(report: dict) -> dict:
    [check] = [item for item in report["checks"] if item["name"].startswith("edge ")]
    return check


def test_a_physical_row_inside_the_gate_passes_with_its_expected_gap(tmp_path: Path) -> None:
    report, results, global_checks, path = evaluate(tmp_path, [row()])
    assert global_checks == []
    assert report["completion"] == "complete"
    assert report["gate"] == "mixed-model-calibration"
    assert report["hardware_gate_status"] == "MISSING"
    assert report["hardware_claim"] is False
    assert results[0].status == "passed"
    assert results[0].expected_visible_gap_mm == 15.0
    assert results[0].expected_body_span_mm == 208.0 + 3 + 208.0
    assert only(report)["detail"]["outcome"] == "passed"
    assert report["artifacts"][str(path)]["sha256"]
    photo = path.parent / "photos" / "e1.jpg"
    assert report["artifacts"][str(photo)]["exists"] is True


def test_a_displacement_beyond_two_millimetres_fails_even_with_low_uncertainty(
    tmp_path: Path,
) -> None:
    report, results, _, _ = evaluate(
        tmp_path, [row(measured_seam_displacement_mm="2.5", uncertainty_mm="0.2")],
    )
    assert results[0].status == "failed"
    assert "exceeds the 2 mm gate" in " ".join(results[0].reasons)
    assert report["completion"] == "incomplete"
    assert "edge e1 -> failed" in report["failure_reasons"]


def test_uncertainty_crossing_the_gate_is_inconclusive_not_a_pass(tmp_path: Path) -> None:
    report, results, _, _ = evaluate(
        tmp_path, [row(measured_seam_displacement_mm="2.2", uncertainty_mm="0.4")],
    )
    result = results[0]
    assert result.status == "inconclusive"
    assert result.status != "passed"
    assert result.lower_bound_mm == pytest.approx(1.8)
    assert result.upper_bound_mm == pytest.approx(2.6)
    assert "threshold:inconclusive" in result.flags
    check = only(report)
    assert check["passed"] is False
    assert check["detail"]["outcome"] == "inconclusive"
    assert report["completion"] == "incomplete"
    [scenario] = [item for item in report["scenarios"] if item["id"] == "e1"]
    assert scenario["status"] == "failed"
    assert scenario["detail"]["outcome"] == "inconclusive"


def test_uncertainty_that_stays_inside_the_gate_still_passes(tmp_path: Path) -> None:
    report, results, _, _ = evaluate(
        tmp_path, [row(measured_seam_displacement_mm="1.8", uncertainty_mm="0.2")],
    )
    assert results[0].status == "passed"
    assert results[0].upper_bound_mm == pytest.approx(2.0)
    assert report["completion"] == "complete"


def test_asymmetric_seam_bezels_are_used_individually_and_flagged(tmp_path: Path) -> None:
    report, results, _, _ = evaluate(
        tmp_path,
        [row(left_bezel_right_mm="3", right_bezel_left_mm="9",
             intended_gap_mm="2", measured_seam_displacement_mm="0.4")],
    )
    result = results[0]
    assert result.expected_visible_gap_mm == 14.0
    assert "asymmetric-seam-bezels" in result.flags
    assert result.status == "passed"
    assert only(report)["detail"]["expected_visible_gap_mm"] == 14.0


def test_a_rotated_mount_remaps_the_seam_facing_bezel(tmp_path: Path) -> None:
    # Native left/right bezels are 10/2 mm. Rotating the right panel 180
    # degrees puts its native right bezel (2 mm) on the wall-left seam. A naive
    # native-edge reader would compute 6 + 3 + 10 = 19 mm instead of 11 mm.
    report, results, _, _ = evaluate(
        tmp_path,
        [row(right_bezel_left_mm="10", right_bezel_right_mm="2",
             right_rotation_deg="180", measured_seam_displacement_mm="0.1")],
    )
    result = results[0]
    assert result.expected_visible_gap_mm == 11.0
    assert "rotated-mount" in result.flags
    assert result.status == "passed"
    assert only(report)["detail"]["expected_visible_gap_mm"] == 11.0


def test_a_quarter_turn_swaps_the_active_dimensions_on_the_wall(tmp_path: Path) -> None:
    report, results, _, _ = evaluate(
        tmp_path,
        [row(right_rotation_deg="90", right_bezel_bottom_mm="4",
             measured_seam_displacement_mm="0.2")],
    )
    result = results[0]
    assert result.row.secondary.wall_active == (261.0, 196.0)
    assert result.expected_visible_gap_mm == 6 + 3 + 4
    assert result.expected_active_span_mm == 196 + 13 + 261
    assert result.status == "passed"
    assert "rotated-mount" in result.flags


def test_a_vertical_edge_uses_the_bottom_and_top_bezels(tmp_path: Path) -> None:
    report, results, _, _ = evaluate(
        tmp_path,
        [row(axis="vertical", left_bezel_bottom_mm="5",
             right_bezel_top_mm="4", intended_gap_mm="2",
             measured_seam_displacement_mm="-0.5", uncertainty_mm="0.2")],
    )
    result = results[0]
    assert result.expected_visible_gap_mm == 11.0
    assert result.status == "passed"
    assert report["completion"] == "complete"


def test_a_missing_expected_edge_fails_the_worksheet(tmp_path: Path) -> None:
    report, results, checks, _ = evaluate(
        tmp_path,
        [row()],
        options=calibration.Options(expected_edges=("e1", "e2")),
    )
    assert "expected edge 'e2' has no row" in checks
    assert any("expected edge 'e2'" in check["name"]
               for check in report["checks"] if not check["passed"])
    assert any(item["id"] == "expected-edge-set" and item["status"] == "failed"
               for item in report["scenarios"])
    assert report["completion"] == "incomplete"


def test_duplicate_edge_ids_and_panel_pairs_are_both_rejected(tmp_path: Path) -> None:
    report, results, checks, _ = evaluate(
        tmp_path,
        [
            row(),
            row(edge_id="e1"),
            row(edge_id="e2", left_panel_id="ipad-c", right_panel_id="ipad-d"),
            row(edge_id="e3", left_panel_id="ipad-c", right_panel_id="ipad-d"),
        ],
        photos=["e1.jpg", "e2.jpg"],
    )
    assert any("duplicate edge_id 'e1'" in message for message in checks)
    assert any("panel pair 'ipad-a'/'ipad-b'" in message for message in checks)
    assert any("panel pair 'ipad-c'/'ipad-d'" in message for message in checks)
    assert all(result.status == "failed" for result in results)
    assert report["completion"] == "incomplete"


def test_stale_calibration_and_view_revisions_are_rejected(tmp_path: Path) -> None:
    report, results, _, _ = evaluate(
        tmp_path,
        [row(left_calibration_revision="3", view_revision="view-6")],
        options=calibration.Options(
            expected_calibration_revision="4",
            expected_view_revision="view-7",
        ),
    )
    reasons = " ".join(results[0].reasons)
    assert "stale left calibration revision" in reasons
    assert "stale view revision" in reasons
    assert results[0].status == "failed"
    assert report["completion"] == "incomplete"


def test_inconsistent_revisions_for_the_same_panel_are_rejected(tmp_path: Path) -> None:
    report, results, checks, _ = evaluate(
        tmp_path,
        [
            row(),
            row(edge_id="e2", left_panel_id="ipad-b", right_panel_id="ipad-c",
                left_profile_revision="2", photo_path="photos/e2.jpg"),
        ],
        photos=["e1.jpg", "e2.jpg"],
    )
    assert any("panel 'ipad-b' uses inconsistent" in message for message in checks)
    assert all(result.status == "failed" for result in results)
    assert report["completion"] == "incomplete"


def test_a_missing_photo_is_a_failure_not_a_warning(tmp_path: Path) -> None:
    report, results, _, _ = evaluate(
        tmp_path, [row(photo_path="photos/absent.jpg")],
    )
    assert results[0].photo_present is False
    assert "photo does not exist" in " ".join(results[0].reasons)
    assert results[0].status == "failed"
    assert report["completion"] == "incomplete"


def test_a_derived_geometry_row_is_rejected_regardless_of_its_numbers(
    tmp_path: Path,
) -> None:
    report, results, _, _ = evaluate(
        tmp_path, [row(method="DPR and viewport arithmetic, no ruler",
                       measured_seam_displacement_mm="0.0")],
    )
    result = results[0]
    assert result.derived_only is True
    assert result.status == "failed"
    assert "derived/browser source" in " ".join(result.reasons)
    assert report["completion"] == "incomplete"


def test_a_method_without_a_named_instrument_is_insufficient(tmp_path: Path) -> None:
    _, results, _, _ = evaluate(tmp_path, [row(method="looks straight")])
    assert results[0].status == "failed"
    assert "physical instrument" in " ".join(results[0].reasons)


def test_out_of_range_measurements_and_non_numbers_fail_their_row(tmp_path: Path) -> None:
    _, results, _, _ = evaluate(
        tmp_path,
        [row(left_active_width_mm="0"), row(edge_id="e2", uncertainty_mm="abc",
                                           photo_path="photos/e2.jpg")],
        photos=["e1.jpg", "e2.jpg"],
    )
    assert results[0].status == "failed"
    assert "outside 20..1500" in " ".join(results[0].reasons)
    assert results[1].status == "failed"
    assert "uncertainty_mm is not a number" in " ".join(results[1].reasons)


def test_an_independent_gap_measurement_must_agree_with_the_reported_displacement(
    tmp_path: Path,
) -> None:
    # Expected visible gap is 15 mm; a measured 17.5 mm gap implies +2.5 mm,
    # while the row reports +0.1 mm. The two physical readings disagree.
    report, results, _, _ = evaluate(
        tmp_path,
        [row(measured_visible_gap_mm="17.5",
             measured_seam_displacement_mm="0.1", uncertainty_mm="0.2")],
    )
    assert results[0].status == "failed"
    assert "measured gap implies" in " ".join(results[0].reasons)
    assert report["completion"] == "incomplete"


def test_a_consistent_gap_cross_check_passes(tmp_path: Path) -> None:
    _, results, _, _ = evaluate(
        tmp_path,
        [row(measured_visible_gap_mm="15.3",
             measured_seam_displacement_mm="0.3", uncertainty_mm="0.3")],
    )
    assert results[0].status == "passed"
    assert any(flag.startswith("gap-derived-displacement:") for flag in results[0].flags)


def test_the_cli_writes_json_and_markdown_and_keeps_the_gate_missing(tmp_path: Path) -> None:
    sheet = write_sheet(tmp_path, [row()])
    json_out = tmp_path / "report" / "calibration.json"
    code = calibration.main([
        "--csv", str(sheet),
        "--json-out", str(json_out),
        "--evidence-kind", "synthetic",
        "--expect-calibration-revision", "4",
        "--expect-view-revision", "view-7",
        "--expect-edges", "e1",
    ])
    assert code == 0
    report = evidence.load_report(json_out)
    assert report["completion"] == "complete"
    assert report["hardware_gate_status"] == "MISSING"
    assert report["tools"]["gate_limit_mm"] == 2.0
    summary = json_out.with_suffix(".md")
    text = summary.read_text()
    assert "Gate status: **MISSING**" in text
    assert "| e1 | ipad-a / ipad-b | horizontal | 15.00 | +0.80 |" in text
    assert "never a pass" in text


def test_the_cli_exits_nonzero_on_a_failed_row_and_writes_both_outputs(tmp_path: Path) -> None:
    sheet = write_sheet(
        tmp_path, [row(measured_seam_displacement_mm="3.0")],
    )
    json_out = tmp_path / "fail.json"
    code = calibration.main([
        "--csv", str(sheet), "--json-out", str(json_out),
        "--evidence-kind", "synthetic",
    ])
    assert code == 1
    report = evidence.load_report(json_out)
    assert report["completion"] == "incomplete"
    assert "edge e1 -> failed" in report["failure_reasons"]
    assert json_out.with_suffix(".md").exists()


def test_a_csv_missing_required_columns_is_a_usage_error_not_a_pass(tmp_path: Path) -> None:
    path = tmp_path / "broken.csv"
    path.write_text("edge_id,left_panel_id\n1,a\n")
    code = calibration.main([
        "--csv", str(path), "--json-out", str(tmp_path / "broken.json"),
        "--evidence-kind", "synthetic",
    ])
    assert code == 2
    assert not (tmp_path / "broken.json").exists()
