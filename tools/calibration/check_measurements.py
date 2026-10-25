#!/usr/bin/env python3
"""Check measured tablet-wall seam rows against the published 2 mm gate.

Input is the operator's calibration worksheet as CSV: one row per adjacent
edge, with **independently measured** active panel dimensions, all four bezel
values per panel, the intended body gap, the signed measured seam displacement
and its uncertainty, the exact profile/calibration/view revisions and a photo
path per edge.

Definitions used here (also stated in ``docs/validation/CALIBRATION-SHEET.md``):

* The two panels lie side by side (``axis=horizontal``, the default) or one
  above the other (``axis=vertical``). ``left_panel_id`` is the panel on the
  left/top; ``right_panel_id`` is the panel on the right/bottom.
* ``intended_gap_mm`` is the intended gap between the two **bodies** (the
  spacer/jig), not the observed gap between lit active areas.
* The expected **visible gap** is therefore::

      primary seam-facing bezel + intended_gap + secondary seam-facing bezel

  computed after applying each panel's quarter-turn rotation to its native
  bezel edges. This is geometry derived from the operator's measurements, not
  a substitute for one.
* ``measured_seam_displacement_mm`` is the signed difference between the
  measured active-edge separation and that expected visible gap. Positive
  means the seam is wider than intended, negative means tighter or overlapping.
  It must be a physical measurement (ruler, vernier, caliper, feeler taper,
  tape or straight-edge), never DPR/viewport arithmetic.

Gate rule (frozen, not revised by this tool):

* pass only when ``|displacement| + uncertainty <= 2 mm``;
* fail when ``|displacement| - uncertainty > 2 mm``;
* otherwise **inconclusive**: uncertainty crosses the threshold. Inconclusive
  is reported as a failed scenario with ``outcome: inconclusive`` and never as
  a pass.

A row whose geometry was derived from DPR, a browser viewport or a screenshot
is rejected as insufficient regardless of its numbers. A row without an
existing photo is rejected. Derived geometry never yields a physical pass.

Output is one ``tablet-wall-validation-evidence/1`` JSON report plus a readable
Markdown summary. ``hardware_gate_status`` is always ``MISSING``.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.validation import evidence  # noqa: E402

TOOL = "calibration-check"
TOOL_VERSION = "1"
GATE = "mixed-model-calibration"
LIMIT_MM = 2.0
STRETCH_LIMIT_MM = 1.0

ACTIVE_RANGE_MM = (20.0, 1500.0)
BEZEL_RANGE_MM = (0.0, 250.0)
GAP_RANGE_MM = (0.0, 100.0)
UNCERTAINTY_RANGE_MM = (0.0, 20.0)
DISPLACEMENT_RANGE_MM = (-200.0, 200.0)

REQUIRED_COLUMNS = (
    "edge_id",
    "left_panel_id",
    "right_panel_id",
    "left_active_width_mm",
    "left_active_height_mm",
    "left_bezel_left_mm",
    "left_bezel_top_mm",
    "left_bezel_right_mm",
    "left_bezel_bottom_mm",
    "right_active_width_mm",
    "right_active_height_mm",
    "right_bezel_left_mm",
    "right_bezel_top_mm",
    "right_bezel_right_mm",
    "right_bezel_bottom_mm",
    "intended_gap_mm",
    "measured_seam_displacement_mm",
    "uncertainty_mm",
    "left_profile_revision",
    "left_calibration_revision",
    "right_profile_revision",
    "right_calibration_revision",
    "view_revision",
    "photo_path",
    "method",
)
OPTIONAL_COLUMNS = (
    "axis",
    "left_rotation_deg",
    "right_rotation_deg",
    "measured_visible_gap_mm",
)

# A method must name an independent physical instrument. Derived geometry is
# an explicit rejection, not an accepted method with a warning.
PHYSICAL_METHOD_TOKENS = (
    "ruler", "vernier", "caliper", "micrometer", "feeler", "tape",
    "straightedge", "straight-edge", "steel-rule", "steel rule",
)
DERIVED_METHOD_TOKENS = (
    "dpr", "device-pixel", "devicepixel", "pixel-ratio", "viewport",
    "screenshot", "screen-shot", "derived", "computed", "calculated",
    "estimated", "estimate", "css-pixel", "browser",
)
REVISION_DIGITS = re.compile(r"^\d+$")


class CsvContractError(ValueError):
    """The CSV cannot be interpreted as a measurement sheet."""


# ---------------------------------------------------------------------------
# data shapes
# ---------------------------------------------------------------------------


@dataclass
class Panel:
    panel_id: str
    active_width_mm: float
    active_height_mm: float
    bezels: dict[str, float]
    rotation_deg: int
    profile_revision: str
    calibration_revision: str

    @property
    def wall_active(self) -> tuple[float, float]:
        if self.rotation_deg in (90, 270):
            return self.active_height_mm, self.active_width_mm
        return self.active_width_mm, self.active_height_mm

    @property
    def wall_bezels(self) -> dict[str, float]:
        if self.rotation_deg == 0:
            return dict(self.bezels)
        if self.rotation_deg == 90:
            return {
                "left": self.bezels["bottom"],
                "top": self.bezels["left"],
                "right": self.bezels["top"],
                "bottom": self.bezels["right"],
            }
        if self.rotation_deg == 180:
            return {
                "left": self.bezels["right"],
                "top": self.bezels["bottom"],
                "right": self.bezels["left"],
                "bottom": self.bezels["top"],
            }
        return {
            "left": self.bezels["top"],
            "top": self.bezels["right"],
            "right": self.bezels["bottom"],
            "bottom": self.bezels["left"],
        }

    @property
    def wall_body(self) -> tuple[float, float]:
        width, height = self.wall_active
        bezels = self.wall_bezels
        return (
            width + bezels["left"] + bezels["right"],
            height + bezels["top"] + bezels["bottom"],
        )


@dataclass
class EdgeRow:
    line: int
    edge_id: str
    axis: str
    primary: Panel
    secondary: Panel
    intended_gap_mm: float
    displacement_mm: float
    uncertainty_mm: float
    measured_visible_gap_mm: float | None
    view_revision: str
    photo_path: str
    method: str


@dataclass
class EdgeResult:
    row: EdgeRow
    status: str = "passed"
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    expected_visible_gap_mm: float | None = None
    expected_active_span_mm: float | None = None
    expected_body_span_mm: float | None = None
    lower_bound_mm: float | None = None
    upper_bound_mm: float | None = None
    cross_axis_delta_mm: float | None = None
    photo_present: bool | None = None
    method_insufficient: bool = False
    derived_only: bool = False

    def fail(self, reason: str) -> None:
        self.status = "failed"
        if reason not in self.reasons:
            self.reasons.append(reason)


@dataclass
class Options:
    expected_profile_revision: str | None = None
    expected_calibration_revision: str | None = None
    expected_view_revision: str | None = None
    expected_edges: tuple[str, ...] | None = None
    photo_root: Path | None = None


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise CsvContractError("CSV has no header row")
        missing = [name for name in REQUIRED_COLUMNS if name not in reader.fieldnames]
        if missing:
            raise CsvContractError(
                "CSV is missing required column(s): " + ", ".join(missing)
            )
        rows: list[dict[str, str]] = []
        for raw in reader:
            if not raw:
                continue
            if not any((value or "").strip() for value in raw.values()):
                continue
            rows.append({key: (value or "").strip() for key, value in raw.items()})
        return rows


def _text(row: Mapping[str, str], column: str, errors: list[str]) -> str:
    value = (row.get(column) or "").strip()
    if not value:
        errors.append(f"{column} is blank")
    return value


def _number(row: Mapping[str, str], column: str, errors: list[str], *,
            minimum: float, maximum: float) -> float | None:
    raw = (row.get(column) or "").strip()
    if not raw:
        errors.append(f"{column} is blank")
        return None
    try:
        value = float(raw)
    except ValueError:
        errors.append(f"{column} is not a number: {raw!r}")
        return None
    if not math.isfinite(value):
        errors.append(f"{column} is not finite: {raw!r}")
        return None
    if not minimum <= value <= maximum:
        errors.append(f"{column} {value:g} is outside {minimum:g}..{maximum:g}")
        return None
    return value


def _rotation(row: Mapping[str, str], column: str, errors: list[str]) -> int:
    raw = (row.get(column) or "").strip()
    if not raw:
        return 0
    try:
        value = float(raw)
    except ValueError:
        errors.append(f"{column} is not a number: {raw!r}")
        return 0
    if not math.isfinite(value) or value % 90 != 0:
        errors.append(f"{column} must be a multiple of 90")
        return 0
    return int(value) % 360


def _measure(row: Mapping[str, str], column: str, errors: list[str],
             limits: tuple[float, float]) -> float | None:
    return _number(row, column, errors, minimum=limits[0], maximum=limits[1])


def _panel(row: Mapping[str, str], prefix: str, errors: list[str]) -> Panel:
    return Panel(
        panel_id=_text(row, f"{prefix}_panel_id", errors),
        active_width_mm=_measure(
            row, f"{prefix}_active_width_mm", errors, ACTIVE_RANGE_MM) or 0.0,
        active_height_mm=_measure(
            row, f"{prefix}_active_height_mm", errors, ACTIVE_RANGE_MM) or 0.0,
        bezels={
            edge: _measure(row, f"{prefix}_bezel_{edge}_mm", errors,
                           BEZEL_RANGE_MM) or 0.0
            for edge in ("left", "top", "right", "bottom")
        },
        rotation_deg=_rotation(row, f"{prefix}_rotation_deg", errors),
        profile_revision=_text(row, f"{prefix}_profile_revision", errors),
        calibration_revision=_text(row, f"{prefix}_calibration_revision", errors),
    )


def parse_edge(row: Mapping[str, str], line: int, errors: list[str]) -> EdgeRow | None:
    axis = (row.get("axis") or "horizontal").strip().lower()
    if axis not in ("horizontal", "vertical"):
        errors.append("axis must be 'horizontal' or 'vertical'")
    edge_id = _text(row, "edge_id", errors)
    primary = _panel(row, "left", errors)
    secondary = _panel(row, "right", errors)
    if primary.panel_id and primary.panel_id == secondary.panel_id:
        errors.append("left_panel_id and right_panel_id are the same panel")
    intended_gap = _measure(row, "intended_gap_mm", errors, GAP_RANGE_MM)
    displacement = _measure(
        row, "measured_seam_displacement_mm", errors, DISPLACEMENT_RANGE_MM)
    uncertainty = _measure(row, "uncertainty_mm", errors, UNCERTAINTY_RANGE_MM)
    measured_gap = None
    if (row.get("measured_visible_gap_mm") or "").strip():
        measured_gap = _number(
            row, "measured_visible_gap_mm", errors, minimum=0.0, maximum=2000.0)
    view_revision = _text(row, "view_revision", errors)
    photo_path = _text(row, "photo_path", errors)
    method = _text(row, "method", errors)
    if errors:
        return None
    return EdgeRow(
        line=line,
        edge_id=edge_id,
        axis=axis,
        primary=primary,
        secondary=secondary,
        intended_gap_mm=float(intended_gap),
        displacement_mm=float(displacement),
        uncertainty_mm=float(uncertainty),
        measured_visible_gap_mm=measured_gap,
        view_revision=view_revision,
        photo_path=photo_path,
        method=method,
    )


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------


def classify_method(method: str) -> tuple[bool, bool, str | None]:
    """Return ``(physical, derived, reason)`` for one operator method."""
    text = method.lower()
    derived = [token for token in DERIVED_METHOD_TOKENS if token in text]
    if derived:
        return False, True, (
            "method names a derived/browser source (" + ", ".join(derived) +
            "); DPR, viewport and screenshot geometry cannot measure a panel"
        )
    physical = [token for token in PHYSICAL_METHOD_TOKENS if token in text]
    if not physical:
        return False, False, (
            "method names no independent physical instrument "
            "(ruler, vernier, caliper, micrometer, feeler, tape or straight-edge)"
        )
    return True, False, None


def _same_revision(left: str, right: str) -> bool:
    if left == right:
        return True
    if REVISION_DIGITS.match(left) and REVISION_DIGITS.match(right):
        return int(left) == int(right)
    return False


def _photo_exists(path: str, root: Path | None, csv_dir: Path) -> tuple[bool, Path]:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = (root or csv_dir) / candidate
    return candidate.is_file(), candidate


def evaluate_edge(row: EdgeRow, options: Options, csv_dir: Path) -> EdgeResult:
    result = EdgeResult(row=row)
    physical, derived, method_reason = classify_method(row.method)
    if not physical:
        result.method_insufficient = True
        result.derived_only = derived
        result.fail(method_reason or "method is not a physical measurement")

    photo_present, photo_file = _photo_exists(row.photo_path, options.photo_root, csv_dir)
    result.photo_present = photo_present
    if not photo_present:
        result.fail(f"photo does not exist: {photo_file}")

    revision_checks = (
        ("left profile revision", row.primary.profile_revision,
         options.expected_profile_revision),
        ("right profile revision", row.secondary.profile_revision,
         options.expected_profile_revision),
        ("left calibration revision", row.primary.calibration_revision,
         options.expected_calibration_revision),
        ("right calibration revision", row.secondary.calibration_revision,
         options.expected_calibration_revision),
        ("view revision", row.view_revision, options.expected_view_revision),
    )
    for label, actual, expected in revision_checks:
        if expected is not None and not _same_revision(actual.strip(), expected.strip()):
            result.fail(f"stale {label}: row has {actual!r}, expected {expected!r}")

    primary_bezels = row.primary.wall_bezels
    secondary_bezels = row.secondary.wall_bezels
    if row.axis == "horizontal":
        primary_edge = "right"
        secondary_edge = "left"
        primary_active, secondary_active = row.primary.wall_active[0], row.secondary.wall_active[0]
        primary_body, secondary_body = row.primary.wall_body[0], row.secondary.wall_body[0]
        cross_axis = row.primary.wall_active[1] - row.secondary.wall_active[1]
    else:
        primary_edge = "bottom"
        secondary_edge = "top"
        primary_active, secondary_active = row.primary.wall_active[1], row.secondary.wall_active[1]
        primary_body, secondary_body = row.primary.wall_body[1], row.secondary.wall_body[1]
        cross_axis = row.primary.wall_active[0] - row.secondary.wall_active[0]

    primary_seam = primary_bezels[primary_edge]
    secondary_seam = secondary_bezels[secondary_edge]
    expected_visible = primary_seam + row.intended_gap_mm + secondary_seam
    result.expected_visible_gap_mm = round(expected_visible, 3)
    result.expected_body_span_mm = round(primary_body + row.intended_gap_mm + secondary_body, 3)
    result.expected_active_span_mm = round(primary_active + expected_visible + secondary_active, 3)
    result.cross_axis_delta_mm = round(cross_axis, 3)

    if not math.isclose(primary_seam, secondary_seam, abs_tol=0.05):
        result.flags.append("asymmetric-seam-bezels")
    if row.primary.rotation_deg or row.secondary.rotation_deg:
        result.flags.append("rotated-mount")
    if abs(cross_axis) > 0.05:
        result.flags.append("cross-axis-size-difference")

    if row.measured_visible_gap_mm is not None:
        derived_displacement = row.measured_visible_gap_mm - expected_visible
        tolerance = max(row.uncertainty_mm, 0.5)
        result.flags.append("gap-cross-checked")
        if abs(derived_displacement - row.displacement_mm) > tolerance:
            result.fail(
                "measured gap implies displacement "
                f"{derived_displacement:.2f} mm but the row reports "
                f"{row.displacement_mm:.2f} mm (tolerance {tolerance:.2f} mm)"
            )
        result.flags.append(f"gap-derived-displacement:{derived_displacement:.2f}")

    magnitude = abs(row.displacement_mm)
    result.lower_bound_mm = round(magnitude - row.uncertainty_mm, 3)
    result.upper_bound_mm = round(magnitude + row.uncertainty_mm, 3)
    if result.upper_bound_mm <= LIMIT_MM:
        disposition = "passed"
    elif result.lower_bound_mm > LIMIT_MM:
        disposition = "failed"
        result.fail(
            f"displacement {row.displacement_mm:+.2f} mm minus uncertainty "
            f"{row.uncertainty_mm:.2f} mm exceeds the {LIMIT_MM:g} mm gate"
        )
    else:
        disposition = "inconclusive"
        if result.status == "passed":
            result.status = "inconclusive"
        result.reasons.append(
            f"inconclusive: uncertainty crosses the {LIMIT_MM:g} mm gate "
            f"(|{row.displacement_mm:+.2f}| + {row.uncertainty_mm:.2f} = "
            f"{result.upper_bound_mm:.2f} mm)"
        )
    result.flags.append(f"threshold:{disposition}")
    return result


def evaluate_rows(raw_rows: Sequence[Mapping[str, str]], options: Options,
                  csv_dir: Path) -> tuple[list[EdgeResult], list[str]]:
    checks: list[str] = []
    results: list[EdgeResult] = []
    for index, raw in enumerate(raw_rows, start=2):
        errors: list[str] = []
        parsed = parse_edge(raw, index, errors)
        fallback_id = raw.get("edge_id", "").strip() or f"row-{index}"
        if parsed is None:
            result = EdgeResult(
                row=EdgeRow(
                    line=index, edge_id=fallback_id, axis="horizontal",
                    primary=Panel(fallback_id, 0, 0, {}, 0, "", ""),
                    secondary=Panel("", 0, 0, {}, 0, "", ""),
                    intended_gap_mm=0, displacement_mm=0, uncertainty_mm=0,
                    measured_visible_gap_mm=None, view_revision="", photo_path="",
                    method="",
                ),
            )
            for error in errors:
                result.fail(error)
            results.append(result)
            continue
        result = evaluate_edge(parsed, options, csv_dir)
        for error in errors:
            result.fail(error)
        results.append(result)

    # Duplicate edge ids and duplicate unordered panel pairs are worksheet
    # defects: both rows lose their claim rather than one silently winning.
    by_edge: dict[str, list[EdgeResult]] = {}
    by_pair: dict[tuple[str, str], list[EdgeResult]] = {}
    for result in results:
        edge_id = result.row.edge_id
        if edge_id:
            by_edge.setdefault(edge_id, []).append(result)
        ids = {result.row.primary.panel_id, result.row.secondary.panel_id}
        if len(ids) == 2 and all(ids):
            by_pair.setdefault(tuple(sorted(ids)), []).append(result)
    for edge_id, group in by_edge.items():
        if len(group) > 1:
            checks.append(f"duplicate edge_id {edge_id!r} appears {len(group)} times")
            for result in group:
                result.fail(f"duplicate edge_id {edge_id!r}")
    for pair, group in by_pair.items():
        if len(group) > 1:
            checks.append(f"panel pair {pair[0]!r}/{pair[1]!r} appears {len(group)} times")
            for result in group:
                result.fail("duplicate panel pair (one adjacent edge per pair)")

    # Same panel must not carry two different revisions across edges.
    revisions: dict[str, set[tuple[str, str]]] = {}
    for result in results:
        for panel in (result.row.primary, result.row.secondary):
            if panel.panel_id and panel.profile_revision and panel.calibration_revision:
                revisions.setdefault(panel.panel_id, set()).add(
                    (panel.profile_revision, panel.calibration_revision)
                )
    for panel_id, values in revisions.items():
        if len(values) > 1:
            checks.append(
                f"panel {panel_id!r} uses inconsistent profile/calibration revisions: "
                + ", ".join(sorted(f"{p}/{c}" for p, c in values))
            )
            for result in results:
                if panel_id in (result.row.primary.panel_id, result.row.secondary.panel_id):
                    result.fail(f"panel {panel_id!r} revision is inconsistent across edges")

    # A grid-wide view revision is one value. Mixed values mean some rows are
    # from a different client build or recall.
    view_values = {result.row.view_revision for result in results if result.row.view_revision}
    if len(view_values) > 1:
        checks.append("view_revision differs across rows: " + ", ".join(sorted(view_values)))
        for result in results:
            result.fail("view_revision is inconsistent across the worksheet")

    if options.expected_edges:
        present = {result.row.edge_id for result in results}
        for edge_id in options.expected_edges:
            if edge_id not in present:
                checks.append(f"expected edge {edge_id!r} has no row")
    return results, checks


# ---------------------------------------------------------------------------
# report and Markdown
# ---------------------------------------------------------------------------


def _status_for_evidence(result: EdgeResult) -> str:
    return "passed" if result.status == "passed" else "failed"


def _scenario_ids(results: Sequence[EdgeResult]) -> dict[int, str]:
    """Stable ids; a duplicated edge id gets its line number so rows stay distinct."""
    counts: dict[str, int] = {}
    for result in results:
        counts[result.row.edge_id] = counts.get(result.row.edge_id, 0) + 1
    ids: dict[int, str] = {}
    for result in results:
        edge_id = result.row.edge_id or f"row-{result.row.line}"
        ids[result.row.line] = (
            edge_id if counts.get(result.row.edge_id, 0) <= 1
            else f"{edge_id}@{result.row.line}"
        )
    return ids


def build_report(
    results: Sequence[EdgeResult], global_checks: Sequence[str], *,
    csv_path: Path, options: Options, evidence_kind: str,
    started_at: str,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    scenarios: list[dict[str, Any]] = []
    scenario_ids = _scenario_ids(results)
    for message in global_checks:
        checks.append(evidence.check_row(f"worksheet: {message}", False))
    for result in results:
        row = result.row
        status = _status_for_evidence(result)
        scenario_id = scenario_ids[row.line]
        checks.append(evidence.check_row(
            f"edge {row.edge_id} -> {result.status}",
            result.status == "passed",
            detail={
                "outcome": result.status,
                "reasons": result.reasons,
                "flags": result.flags,
                "expected_visible_gap_mm": result.expected_visible_gap_mm,
                "expected_active_span_mm": result.expected_active_span_mm,
                "measured_seam_displacement_mm": row.displacement_mm,
                "measured_visible_gap_mm": row.measured_visible_gap_mm,
                "intended_gap_mm": row.intended_gap_mm,
                "uncertainty_mm": row.uncertainty_mm,
                "bounds_mm": [result.lower_bound_mm, result.upper_bound_mm],
                "revisions": {
                    "left_profile": row.primary.profile_revision,
                    "left_calibration": row.primary.calibration_revision,
                    "right_profile": row.secondary.profile_revision,
                    "right_calibration": row.secondary.calibration_revision,
                    "view": row.view_revision,
                },
                "method": row.method,
                "insufficient_physical_measurement": result.method_insufficient,
                "derived_geometry_only": result.derived_only,
                "photo_present": result.photo_present,
                "line": row.line,
            },
        ))
        scenarios.append(evidence.scenario_row(
            scenario_id, status,
            detail={"outcome": result.status, "reasons": result.reasons},
        ))
    if options.expected_edges:
        present = {result.row.edge_id for result in results}
        missing = [edge_id for edge_id in options.expected_edges if edge_id not in present]
        scenarios.append(evidence.scenario_row(
            "expected-edge-set",
            "failed" if missing else "passed",
            detail={"expected": list(options.expected_edges), "missing": missing},
        ))
        checks.append(evidence.check_row(
            "expected edge set is complete", not missing,
            detail={"missing": missing},
        ))

    cohort = sorted({
        panel_id
        for result in results
        for panel_id in (result.row.primary.panel_id, result.row.secondary.panel_id)
        if panel_id
    })
    expected = [scenario_ids[result.row.line] for result in results]
    if options.expected_edges:
        expected.append("expected-edge-set")
    artifacts = evidence.artifact_hashes([csv_path] + [
        _photo_exists(result.row.photo_path, options.photo_root, csv_path.parent)[1]
        for result in results if result.row.photo_path
    ])
    unobserved = [
        "installation, ruler/vernier placement and the visual seam: manual",
        "photo content and framing were checked for existence only, not inspected",
        "camera perspective and lens distortion were not modelled",
    ]
    limitations = [
        f"The published {LIMIT_MM:g} mm displacement gate is used unchanged; "
        f"the {STRETCH_LIMIT_MM:g} mm stretch goal is not applied.",
        "Only rows with an independently measured displacement and a physical "
        "instrument method can pass; derived geometry never yields a physical pass.",
        "A post-check is not a replacement for the operator's sign-off; the "
        "hardware gate remains MISSING.",
        "Uncertainty is the operator's stated value; the checker does not "
        "recompute instrument or camera uncertainty.",
        "Raw photos stay outside the repository unless the operator authorizes a "
        "bounded sample; only their presence and hashes are recorded.",
    ]
    tools = {
        "gate_limit_mm": LIMIT_MM,
        "stretch_limit_mm": STRETCH_LIMIT_MM,
        "rule": "pass iff |d|+u <= 2; fail iff |d|-u > 2; otherwise inconclusive",
        "physical_method_tokens": list(PHYSICAL_METHOD_TOKENS),
        "derived_method_tokens": list(DERIVED_METHOD_TOKENS),
        "axis_default": "horizontal",
        "rotation_unit": "clockwise quarter turns in wall space",
        "expected_profile_revision": options.expected_profile_revision,
        "expected_calibration_revision": options.expected_calibration_revision,
        "expected_view_revision": options.expected_view_revision,
        "expected_edges": list(options.expected_edges) if options.expected_edges else None,
        "photo_root": str(options.photo_root) if options.photo_root else None,
        "csv": str(csv_path),
    }
    return evidence.build_report(
        tool=TOOL,
        tool_version=TOOL_VERSION,
        gate=GATE,
        evidence_kind=evidence_kind,
        started_at=started_at,
        checks=checks,
        scenarios=scenarios,
        expected_scenarios=expected,
        artifacts=artifacts,
        cohort=cohort,
        tools=tools,
        unobserved=unobserved,
        limitations=limitations,
        repository=evidence.repository_state(ROOT),
    )


def markdown_summary(report: Mapping[str, Any], results: Sequence[EdgeResult],
                     global_checks: Sequence[str]) -> str:
    lines = [
        "# Seam calibration check",
        "",
        f"Generated: {report['finished_at']}  ",
        f"Repository: `{report['repository'].get('head')}` "
        f"({report['repository'].get('branch')})  ",
        f"Evidence kind: `{report['evidence_kind']}`  ",
        f"Gate status: **{report['hardware_gate_status']}**  ",
        f"Completion: **{report['completion']}** "
        f"({report['checks_passed']}/{report['checks_total']} checks)",
        "",
        f"Gate rule: `|displacement| + uncertainty <= {LIMIT_MM:g} mm` passes; "
        f"`|displacement| - uncertainty > {LIMIT_MM:g} mm` fails; otherwise "
        "**inconclusive** (never a pass).",
        "",
    ]
    if global_checks:
        lines.extend(["## Worksheet defects", ""])
        lines.extend(f"- {message}" for message in global_checks)
        lines.append("")
    lines.extend([
        "## Rows",
        "",
        "| Edge | Panels | Axis | Expected gap mm | Displacement mm | "
        "Uncertainty mm | Bounds mm | Outcome | Flags / reasons |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |",
    ])
    for result in results:
        row = result.row
        flags = ", ".join(result.flags + result.reasons)
        bounds = (
            f"{result.lower_bound_mm:g}..{result.upper_bound_mm:g}"
            if result.lower_bound_mm is not None and result.upper_bound_mm is not None
            else "-"
        )
        expected = (
            f"{result.expected_visible_gap_mm:.2f}"
            if result.expected_visible_gap_mm is not None else "-"
        )
        lines.append(
            "| {edge} | {left} / {right} | {axis} | {expected} | {disp:+.2f} | "
            "{unc:.2f} | {bounds} | {outcome} | {flags} |".format(
                edge=row.edge_id or f"row-{row.line}",
                left=row.primary.panel_id or "?",
                right=row.secondary.panel_id or "?",
                axis=row.axis,
                expected=expected,
                disp=row.displacement_mm,
                unc=row.uncertainty_mm,
                bounds=bounds,
                outcome=result.status,
                flags=flags or "-",
            )
        )
    lines.extend([
        "",
        "## Revisions and method",
        "",
        "| Edge | Left profile/calibration | Right profile/calibration | View | Method |",
        "| --- | --- | --- | --- | --- |",
    ])
    for result in results:
        row = result.row
        lines.append(
            "| {edge} | {lp}/{lc} | {rp}/{rc} | {view} | {method} |".format(
                edge=row.edge_id or f"row-{row.line}",
                lp=row.primary.profile_revision or "?",
                lc=row.primary.calibration_revision or "?",
                rp=row.secondary.profile_revision or "?",
                rc=row.secondary.calibration_revision or "?",
                view=row.view_revision or "?",
                method=row.method or "?",
            )
        )
    lines.extend([
        "",
        "## Not proven",
        "",
    ])
    lines.extend(f"- {item}" for item in report.get("limitations", []))
    lines.extend(f"- Unobserved: {item}" for item in report.get("unobserved", []))
    lines.extend([
        "",
        "The hardware gate stays MISSING until the operator signs the physical row.",
        "",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _revision(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        raise argparse.ArgumentTypeError("revision must not be blank")
    return text


def _edge_list(value: str | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    edges = tuple(item.strip() for item in value.split(",") if item.strip())
    if not edges:
        raise argparse.ArgumentTypeError("--expect-edges needs at least one id")
    return edges


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check_measurements.py",
        description=(
            "Check measured adjacent-edge seam rows against the published 2 mm "
            "gate. Physical measurements and photos are required; derived "
            "geometry never passes. The hardware gate stays MISSING."
        ),
    )
    parser.add_argument("--csv", required=True, help="calibration worksheet CSV")
    parser.add_argument("--json-out", required=True, help="evidence JSON output path")
    parser.add_argument("--markdown-out", default=None,
                        help="Markdown summary path (default: JSON path with .md)")
    parser.add_argument("--evidence-kind", required=True,
                        choices=("synthetic", "operator-hardware"),
                        help="synthetic validates the checker; operator-hardware is a real sheet")
    parser.add_argument("--expect-profile-revision", type=_revision, default=None)
    parser.add_argument("--expect-calibration-revision", type=_revision, default=None)
    parser.add_argument("--expect-view-revision", type=_revision, default=None)
    parser.add_argument("--expect-edges", type=_edge_list, default=None,
                        help="comma-separated edge ids that must all be present")
    parser.add_argument("--photo-root", type=Path, default=None,
                        help="directory for relative photo paths (default: CSV directory)")
    return parser


def evaluate_file(csv_path: Path, options: Options, evidence_kind: str,
                  started_at: str | None = None
                  ) -> tuple[dict[str, Any], list[EdgeResult], list[str]]:
    raw_rows = load_rows(csv_path)
    results, global_checks = evaluate_rows(raw_rows, options, csv_path.parent)
    report = build_report(
        results, global_checks, csv_path=csv_path, options=options,
        evidence_kind=evidence_kind, started_at=started_at or evidence.iso_now(),
    )
    return report, results, global_checks


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    csv_path = Path(args.csv)
    options = Options(
        expected_profile_revision=args.expect_profile_revision,
        expected_calibration_revision=args.expect_calibration_revision,
        expected_view_revision=args.expect_view_revision,
        expected_edges=args.expect_edges,
        photo_root=args.photo_root,
    )
    try:
        report, results, global_checks = evaluate_file(
            csv_path, options, args.evidence_kind,
        )
    except (OSError, CsvContractError) as exc:
        print(f"calibration-check: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    json_path = Path(args.json_out)
    evidence.write_report(json_path, report)
    markdown_path = Path(args.markdown_out) if args.markdown_out else json_path.with_suffix(".md")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown_summary(report, results, global_checks))
    print(f"calibration-check: {report['completion']} "
          f"({report['checks_passed']}/{report['checks_total']} checks, "
          f"{report['scenarios_passed']}/{report['scenarios_total']} scenarios)")
    for result in results:
        print(f"{result.status.upper():12s} edge {result.row.edge_id or result.row.line}"
              + (f": {', '.join(result.reasons)}" if result.reasons else ""))
    for message in global_checks:
        print(f"FAIL worksheet: {message}")
    print(f"report: {json_path} sha256:{evidence.file_sha256(json_path)}")
    print(f"summary: {markdown_path}")
    return 0 if report["completion"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
