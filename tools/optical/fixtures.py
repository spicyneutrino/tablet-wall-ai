"""Deterministic synthetic captures for the optical analyzer.

The fixtures exist to validate the analyzer, not a panel. Each case writes a
manifest with actual frame timestamps, a ROI file and an event file, plus an
``expectations.json`` that records the known onset times. ``python -m
tools.optical.cli fixtures --out DIR`` reproduces the whole suite.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from PIL import Image, ImageChops, ImageDraw

from .model import (
    EVENTS_SCHEMA,
    MANIFEST_SCHEMA,
    ROIS_SCHEMA,
    Camera,
)
from .timing import readout_fraction

FIXTURE_FPS = 240.0
FIXTURE_PERIOD = 1.0 / FIXTURE_FPS
REFERENCE_FRAME = 20
FRAME_WIDTH = 320
FRAME_HEIGHT = 240
BACKGROUND = (12, 12, 12)
TARGET_GREEN = (0, 200, 0)
TARGET_BLUE = (0, 0, 210)
BAND_COUNT = 12

DEFAULT_BOXES = {
    "left": (28, 48, 150, 208),
    "right": (170, 48, 292, 208),
}
ROLLING_BOXES = {
    "left": (28, 20, 150, 104),
    "right": (170, 136, 292, 220),
}


@dataclass(frozen=True)
class PanelPlan:
    panel_id: str
    box: tuple[int, int, int, int]
    base_rgb: tuple[int, int, int]
    on_rgb: tuple[int, int, int]
    on_time_s: float | None
    partial_columns: float | None = None


def _lerp(
    first: Sequence[int],
    second: Sequence[int],
    fraction: float,
) -> tuple[int, int, int]:
    fraction = max(0.0, min(1.0, fraction))
    return tuple(
        int(round(a + (b - a) * fraction)) for a, b in zip(first, second)
    )  # type: ignore[return-value]


def _add_noise(image: Image.Image, sigma: float, seed: str) -> Image.Image:
    if sigma <= 0:
        return image
    rng = random.Random(seed)
    width, height = image.size
    raw = Image.frombytes("L", (width, height), rng.randbytes(width * height))
    solid = Image.new("L", (width, height), 128)
    factor = max(0.0, min(1.0, sigma / 73.9))
    noise = Image.blend(solid, raw, factor).convert("RGB")
    return ImageChops.add(image, noise, scale=1.0, offset=-128)


def _render_frame(
    panels: Sequence[PanelPlan],
    timestamp_s: float,
    camera: Camera,
    noise_sigma: float,
    seed: str,
) -> Image.Image:
    image = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    exposure = camera.exposure_s
    for panel in panels:
        left, top, right, bottom = panel.box
        height = bottom - top
        width = right - left
        changed_right = left + int(round(width * (panel.partial_columns or 1.0)))
        for band in range(BAND_COUNT):
            band_top = top + int(round(height * band / BAND_COUNT))
            band_bottom = top + int(round(height * (band + 1) / BAND_COUNT))
            if band_bottom <= band_top:
                continue
            centre_y = (band_top + band_bottom - 1) / 2.0
            fraction = readout_fraction(left + width / 2.0, centre_y, camera)
            row_start = timestamp_s + fraction * camera.readout_s
            if panel.on_time_s is None:
                weight = 0.0
            elif row_start >= panel.on_time_s:
                weight = 1.0
            elif row_start + exposure <= panel.on_time_s:
                weight = 0.0
            else:
                weight = (row_start + exposure - panel.on_time_s) / exposure
            colour = _lerp(panel.base_rgb, panel.on_rgb, weight)
            if panel.partial_columns is None:
                draw.rectangle(
                    (left, band_top, right - 1, band_bottom - 1),
                    fill=colour,
                )
            else:
                if changed_right > left:
                    draw.rectangle(
                        (left, band_top, changed_right - 1, band_bottom - 1),
                        fill=colour,
                    )
                if changed_right < right:
                    draw.rectangle(
                        (changed_right, band_top, right - 1, band_bottom - 1),
                        fill=panel.base_rgb,
                    )
    return _add_noise(image, noise_sigma, seed)


def _timestamps(
    reference_time_s: float,
    end_time_s: float,
    *,
    variable: bool,
    seed: str,
) -> list[tuple[int, float]]:
    rng = random.Random(seed)
    rows: list[tuple[int, float]] = []
    index = 0
    previous = -1.0
    while True:
        nominal = index * FIXTURE_PERIOD
        if nominal > end_time_s:
            break
        timestamp = nominal
        if variable and index != REFERENCE_FRAME:
            timestamp += rng.uniform(-0.0003, 0.0003)
        if index == REFERENCE_FRAME:
            timestamp = reference_time_s
        if timestamp <= previous:
            timestamp = previous + FIXTURE_PERIOD * 0.8
        rows.append((index, timestamp))
        previous = timestamp
        index += 1
    return rows


def _polygon(box: tuple[int, int, int, int]) -> list[list[float]]:
    left, top, right, bottom = box
    inset = 8
    return [
        [left + inset, top + inset],
        [right - inset, top + inset],
        [right - inset, bottom - inset],
        [left + inset, bottom - inset],
    ]


def _noise_polygon(box: tuple[int, int, int, int]) -> list[list[float]]:
    left, top, right, bottom = box
    return [
        [left + 10, bottom - 24],
        [left + 34, bottom - 24],
        [left + 34, bottom - 10],
        [left + 10, bottom - 10],
    ]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _build_case(
    root: Path,
    case_id: str,
    *,
    offsets_ms: dict[str, float | None],
    description: str,
    exposure_us: float = 600.0,
    readout_us: float = 4000.0,
    boxes: dict[str, tuple[int, int, int, int]] | None = None,
    partial_columns: dict[str, float] | None = None,
    wrong_colour: dict[str, tuple[int, int, int]] | None = None,
    base_colour: dict[str, tuple[int, int, int]] | None = None,
    already_target: set[str] | None = None,
    noise_sigma: float = 0.0,
    variable: bool = False,
    dropped: set[int] | None = None,
    duplicated: set[int] | None = None,
    truncated_after_ms: float | None = None,
    expected_event_status: str = "observed",
    expected_panel_status: dict[str, str] | None = None,
    steady_state: bool = True,
    notes: str = "",
) -> dict[str, Any]:
    boxes = boxes or DEFAULT_BOXES
    partial_columns = partial_columns or {}
    wrong_colour = wrong_colour or {}
    base_colour = base_colour or {}
    already_target = already_target or set()
    dropped = dropped or set()
    duplicated = duplicated or set()

    camera = Camera(
        exposure_us=exposure_us,
        orientation_deg=0,
        width=FRAME_WIDTH,
        height=FRAME_HEIGHT,
        readout_us=readout_us,
        readout_direction="top-to-bottom",
        readout_measured=True,
        model="synthetic 240 fps fixture camera",
        gain="synthetic",
        white_balance="synthetic",
        nominal_fps=FIXTURE_FPS,
    )
    reference_time = REFERENCE_FRAME * FIXTURE_PERIOD
    max_offset = max(
        (value for value in offsets_ms.values() if value is not None),
        default=0.0,
    )
    after_ms = max(max_offset, 0.0) + 80.0
    if truncated_after_ms is not None:
        end_time = reference_time + truncated_after_ms / 1000.0
    else:
        end_time = reference_time + after_ms / 1000.0 + 0.010

    panels: list[PanelPlan] = []
    for panel_id, box in boxes.items():
        base = base_colour.get(
            panel_id,
            (30, 30, 42) if panel_id == "left" else (42, 32, 30),
        )
        if panel_id in already_target:
            panels.append(PanelPlan(
                panel_id=panel_id,
                box=box,
                base_rgb=TARGET_GREEN,
                on_rgb=TARGET_GREEN,
                on_time_s=None,
                partial_columns=None,
            ))
            continue
        offset = offsets_ms.get(panel_id)
        on_time = (
            None if offset is None else reference_time + offset / 1000.0
        )
        panels.append(PanelPlan(
            panel_id=panel_id,
            box=box,
            base_rgb=base,
            on_rgb=wrong_colour.get(panel_id, TARGET_GREEN),
            on_time_s=on_time,
            partial_columns=partial_columns.get(panel_id),
        ))

    case_dir = root / "cases" / case_id
    frames_dir = case_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    timestamps = _timestamps(
        reference_time,
        end_time,
        variable=variable,
        seed=f"{case_id}:clock",
    )
    previous_timestamp = None
    previous_row_timestamp = None
    frame_rows: list[dict[str, Any]] = []
    for index, timestamp in timestamps:
        if index in dropped:
            continue
        duplicate = index in duplicated and previous_timestamp is not None
        render_time = previous_timestamp if duplicate else timestamp
        row_timestamp = previous_row_timestamp if duplicate else timestamp
        image = _render_frame(
            panels,
            render_time,
            camera,
            noise_sigma,
            seed=f"{case_id}:{index}:noise",
        )
        path = frames_dir / f"{index:06d}.png"
        image.save(path)
        frame_rows.append({
            "index": index,
            "path": f"frames/{path.name}",
            "timestamp_s": round(row_timestamp, 9),
        })
        previous_timestamp = render_time
        previous_row_timestamp = row_timestamp

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "capture_id": f"synthetic-{case_id}",
        "evidence_kind": "synthetic",
        "camera": {
            "model": camera.model,
            "exposure_us": camera.exposure_us,
            "gain": camera.gain,
            "white_balance": camera.white_balance,
            "orientation_deg": camera.orientation_deg,
            "resolution": {"width": FRAME_WIDTH, "height": FRAME_HEIGHT},
            "rolling_shutter": {
                "readout_us": camera.readout_us,
                "direction": camera.readout_direction,
                "measured": True,
                "method": "fixture: per-band row offsets emulate the readout",
            },
            "nominal_fps": FIXTURE_FPS,
        },
        "timestamp_basis": "exposure_start",
        "clock": {
            "source": "synthetic monotonic clock",
            "mapping": "event reference_frame indexes these actual frame timestamps",
        },
        "frames": frame_rows,
        "dropped_frames": sorted(dropped),
        "duplicated_frames": sorted(duplicated),
        "panel_scanout": (
            "fixture panel rows are drawn in readout order; no panel scanout is modelled"
            if not notes else notes
        ),
        "notes": "Synthetic fixture: validates the analyzer only, never a panel.",
    }
    _write_json(case_dir / "manifest.json", manifest)

    roi_panels = []
    for panel in panels:
        roi_panels.append({
            "panel_id": panel.panel_id,
            "polygon": _polygon(panel.box),
            "sample_rows": [0.2, 0.5, 0.8],
            "sample_columns": [0.15, 0.38, 0.62, 0.85],
            "sample_radius": 2,
            "noise_reference": {
                "polygon": _noise_polygon(panel.box),
                "sample_rows": [0.3, 0.7],
                "sample_columns": [0.25, 0.75],
                "sample_radius": 1,
            },
        })
    _write_json(case_dir / "rois.json", {
        "schema": ROIS_SCHEMA,
        "coordinate_space": "delivered",
        "panels": roi_panels,
    })

    event = {
        "event_id": case_id,
        "reference_frame": REFERENCE_FRAME,
        "search_window": {
            "before_ms": 40.0,
            "after_ms": after_ms,
        },
        "expected_panels": list(boxes),
        "target": {"rgb": list(TARGET_GREEN), "tolerance": 30.0},
        "min_target_fraction": 0.60,
        "steady_state": steady_state,
        "notes": description,
    }
    _write_json(case_dir / "events.json", {
        "schema": EVENTS_SCHEMA,
        "events": [event],
    })

    if expected_panel_status is None:
        expected_panel_status = {
            panel_id: "observed" for panel_id in boxes
        }
    expectations = {
        "case_id": case_id,
        "description": description,
        "nominal_fps_metadata_only": FIXTURE_FPS,
        "frame_period_ms": round(FIXTURE_PERIOD * 1000.0, 4),
        "reference_frame": REFERENCE_FRAME,
        "reference_time_s": round(reference_time, 9),
        "search_before_ms": 40.0,
        "search_after_ms": after_ms,
        "true_onset_ms": {
            panel_id: offsets_ms.get(panel_id) for panel_id in boxes
        },
        "target_skew_ms": (
            abs(
                (offsets_ms.get("right") or 0.0)
                - (offsets_ms.get("left") or 0.0)
            )
        ),
        "expected_event_status": expected_event_status,
        "expected_panel_status": expected_panel_status,
        "exposure_us": exposure_us,
        "readout_us": readout_us,
        "noise_sigma": noise_sigma,
        "variable_timing": variable,
        "dropped_frames": sorted(dropped),
        "duplicated_frames": sorted(duplicated),
        "truncated_after_ms": truncated_after_ms,
        "steady_state": steady_state,
        "frame_count": len(frame_rows),
        "notes": notes,
    }
    _write_json(case_dir / "expectations.json", expectations)
    return {
        "case_id": case_id,
        "directory": str(case_dir),
        "manifest": str(case_dir / "manifest.json"),
        "rois": str(case_dir / "rois.json"),
        "events": str(case_dir / "events.json"),
        "expectations": expectations,
    }


def generate_suite(root: Path | str) -> dict[str, Any]:
    """Write the reproducible fixture suite and return its index."""
    suite_root = Path(root).resolve()
    suite_root.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []

    cases.append(_build_case(
        suite_root, "offset-0",
        offsets_ms={"left": 0.0, "right": 0.0},
        description="both panels switch together",
        notes="both panels at the same readout rows",
    ))
    cases.append(_build_case(
        suite_root, "offset-30",
        offsets_ms={"left": 0.0, "right": 30.0},
        description="right panel 30 ms after left",
    ))
    cases.append(_build_case(
        suite_root, "offset-80",
        offsets_ms={"left": 0.0, "right": 80.0},
        description="right panel 80 ms after left",
    ))
    cases.append(_build_case(
        suite_root, "subframe",
        offsets_ms={"left": 0.0, "right": 10.4},
        description="2.5 frame periods: a subframe phase offset",
    ))
    cases.append(_build_case(
        suite_root, "threshold-100",
        offsets_ms={"left": 0.0, "right": 100.0},
        description="point skew exactly at the 100 ms p95 limit",
    ))
    cases.append(_build_case(
        suite_root, "exceed-300",
        offsets_ms={"left": 0.0, "right": 300.0},
        description="point skew beyond the 250 ms maximum",
    ))
    cases.append(_build_case(
        suite_root, "rolling",
        offsets_ms={"left": 0.0, "right": 0.0},
        description="simultaneous panels at different sensor rows",
        boxes=ROLLING_BOXES,
        exposure_us=800.0,
        readout_us=6000.0,
        notes="panels occupy different rows; rolling readout shifts their exposure",
    ))
    cases.append(_build_case(
        suite_root, "exposure-blur",
        offsets_ms={"left": 0.0, "right": 30.0},
        description="long exposure blends the transition",
        exposure_us=3800.0,
        readout_us=2500.0,
    ))
    cases.append(_build_case(
        suite_root, "noise",
        offsets_ms={"left": 0.0, "right": 30.0},
        description="camera noise above the flat-fixture floor",
        noise_sigma=10.0,
    ))
    cases.append(_build_case(
        suite_root, "partial",
        offsets_ms={"left": 0.0, "right": 30.0},
        description="right panel only partially reaches the target",
        partial_columns={"right": 0.30},
        expected_event_status="partial",
        expected_panel_status={"left": "observed", "right": "partial"},
    ))
    cases.append(_build_case(
        suite_root, "wrong-target",
        offsets_ms={"left": 0.0, "right": 30.0},
        description="right panel shows blue while green was expected",
        wrong_colour={"right": TARGET_BLUE},
        expected_event_status="wrong-target",
        expected_panel_status={"left": "observed", "right": "wrong-target"},
    ))
    cases.append(_build_case(
        suite_root, "repeated-colours",
        offsets_ms={"left": 30.0, "right": None},
        description="right panel already shows the target colour at baseline",
        already_target={"right"},
        expected_event_status="ambiguous",
        expected_panel_status={"left": "observed", "right": "ambiguous"},
    ))
    cases.append(_build_case(
        suite_root, "repeated-drift",
        offsets_ms={"left": 0.0, "right": 30.0},
        description="baseline is already inside the target tolerance, then drifts within it",
        base_colour={"right": (0, 220, 0)},
        wrong_colour={"right": (0, 180, 0)},
        expected_event_status="ambiguous",
        expected_panel_status={"left": "observed", "right": "ambiguous"},
    ))
    cases.append(_build_case(
        suite_root, "missing",
        offsets_ms={"left": 0.0, "right": None},
        description="right panel never changes",
        expected_event_status="missing",
        expected_panel_status={"left": "observed", "right": "missing"},
    ))
    cases.append(_build_case(
        suite_root, "variable-timing",
        offsets_ms={"left": 0.0, "right": 30.0},
        description="actual timestamps jitter around the nominal grid",
        variable=True,
    ))
    cases.append(_build_case(
        suite_root, "dropped-duplicated",
        offsets_ms={"left": 0.0, "right": 30.0},
        description="one dropped frame at the right onset and one duplicated image",
        dropped={27},
        duplicated={24},
        notes="dropped frame 27 widens the right onset interval; frame 24 is a duplicate",
    ))
    cases.append(_build_case(
        suite_root, "truncated",
        offsets_ms={"left": 0.0, "right": 30.0},
        description="capture ends before the right panel transition",
        truncated_after_ms=15.0,
        expected_event_status="unobserved",
        expected_panel_status={"left": "observed", "right": "unobserved"},
    ))
    cases.append(_build_case(
        suite_root, "early-cut",
        offsets_ms={"left": -25.0, "right": -10.0},
        description="both panels switch before the reference frame",
    ))
    cases.append(_build_case(
        suite_root, "startup",
        offsets_ms={"left": 0.0, "right": 80.0},
        description="declared startup event, excluded from steady-state metrics",
        steady_state=False,
    ))

    index = {
        "schema": "tablet-wall-optical-fixture-suite/1",
        "note": "Synthetic fixtures validate the analyzer only; they are not panel evidence.",
        "nominal_fps_metadata_only": FIXTURE_FPS,
        "reference_frame": REFERENCE_FRAME,
        "frame_size": [FRAME_WIDTH, FRAME_HEIGHT],
        "cases": cases,
    }
    _write_json(suite_root / "suite.json", index)
    return {"root": str(suite_root), "suite_path": str(suite_root / "suite.json"), "cases": cases}
