"""Input parsing for capture manifests, ROI sets and event lists.

The manifest is authoritative for frame timestamps. A nominal frame rate may
be recorded, but it is metadata only and is never used for timing. When a
manifest names a video and no frame list, ffmpeg extracts every frame and
ffprobe supplies the decoded presentation timestamps.
"""

from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

from PIL import Image, ImageStat

from .model import (
    EVENTS_SCHEMA,
    MANIFEST_SCHEMA,
    ROIS_SCHEMA,
    Camera,
    Capture,
    Event,
    Frame,
    PanelROI,
    Region,
    ROISet,
    RGB,
    EVIDENCE_KINDS,
    READOUT_DIRECTIONS,
    TIMESTAMP_BASES,
)
from .timing import sensor_to_delivered


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read JSON {path}: {error}") from error


def _number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a number") from error
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be an integer") from error
    if not math.isfinite(number) or not number.is_integer():
        raise ValueError(f"{field} must be an integer")
    return int(number)


def _boolean(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off", ""):
        return False
    raise ValueError(f"{field} must be a boolean")


def _text_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def _parse_rgb(value: Any, field: str) -> RGB:
    if isinstance(value, str):
        parts = [part for part in re.split(r"[,;\s]+", value.strip()) if part]
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        raise ValueError(f"{field} must be a three-component colour")
    if len(parts) != 3:
        raise ValueError(f"{field} must have exactly three components")
    channels = tuple(_number(part, f"{field} component") for part in parts)
    if any(channel < 0 or channel > 255 for channel in channels):
        raise ValueError(f"{field} components must be between 0 and 255")
    return channels  # type: ignore[return-value]


def _parse_panels(value: Any, field: str) -> tuple[str, ...]:
    if isinstance(value, str):
        parts = [part.strip() for part in re.split(r"[,;]", value) if part.strip()]
    elif isinstance(value, (list, tuple)):
        parts = [str(part).strip() for part in value if str(part).strip()]
    else:
        raise ValueError(f"{field} must be a panel id list")
    if not parts:
        raise ValueError(f"{field} cannot be empty")
    if len(set(parts)) != len(parts):
        raise ValueError(f"{field} contains a duplicate panel")
    return tuple(parts)


def _frame_from_row(row: dict[str, Any], base: Path, source: str) -> Frame:
    if "index" not in row:
        raise ValueError(f"{source}: every frame needs an index")
    index = _integer(row["index"], f"{source} frame index")
    if index < 0:
        raise ValueError(f"{source}: frame index cannot be negative")
    if "path" not in row or not str(row["path"]).strip():
        raise ValueError(f"{source}: frame {index} has no path")
    path = Path(str(row["path"]))
    if not path.is_absolute():
        path = (base / path).resolve()
    if "timestamp_s" in row and row["timestamp_s"] not in (None, ""):
        timestamp = _number(row["timestamp_s"], f"{source} frame {index} timestamp_s")
    elif "timestamp_us" in row and row["timestamp_us"] not in (None, ""):
        timestamp = _number(row["timestamp_us"], f"{source} frame {index} timestamp_us") / 1_000_000.0
    else:
        raise ValueError(
            f"{source}: frame {index} needs timestamp_s or timestamp_us; "
            "a nominal fps is not a timestamp"
        )
    return Frame(index=index, path=path, timestamp_s=timestamp)


def _parse_camera(raw: dict[str, Any]) -> Camera:
    if not isinstance(raw, dict):
        raise ValueError("camera must be an object")
    if "exposure_us" not in raw:
        raise ValueError("camera.exposure_us is required")
    exposure_us = _number(raw["exposure_us"], "camera.exposure_us")
    if exposure_us <= 0:
        raise ValueError("camera.exposure_us must be positive")

    resolution = raw.get("resolution")
    if resolution is None:
        if "width" in raw and "height" in raw:
            resolution = {"width": raw["width"], "height": raw["height"]}
        else:
            raise ValueError("camera.resolution is required")
    width = _integer(resolution.get("width"), "camera.resolution.width")
    height = _integer(resolution.get("height"), "camera.resolution.height")
    if width <= 0 or height <= 0:
        raise ValueError("camera.resolution must be positive")

    rolling = raw.get("rolling_shutter")
    if not isinstance(rolling, dict):
        raise ValueError("camera.rolling_shutter is required (readout_us, direction, measured)")
    readout_us = _number(rolling.get("readout_us"), "camera.rolling_shutter.readout_us")
    if readout_us < 0:
        raise ValueError("camera.rolling_shutter.readout_us cannot be negative")
    direction = str(rolling.get("direction", "")).strip()
    if direction not in READOUT_DIRECTIONS:
        raise ValueError(
            "camera.rolling_shutter.direction must be one of "
            f"{READOUT_DIRECTIONS}"
        )
    measured = _boolean(rolling.get("measured", False), "camera.rolling_shutter.measured")

    if "orientation_deg" not in raw and "orientation" not in raw:
        raise ValueError("camera.orientation_deg is required")
    orientation = raw.get("orientation_deg", raw.get("orientation"))
    if isinstance(orientation, str) and orientation.strip().lower() == "landscape":
        orientation = 0
    orientation_deg = _integer(orientation, "camera.orientation_deg")
    if orientation_deg not in (0, 90, 180, 270):
        raise ValueError("camera.orientation_deg must be 0, 90, 180 or 270")

    gain = _text_value(raw.get("gain"))
    if not gain:
        raise ValueError("camera.gain is required (record manual gain or 'auto')")
    white_balance = _text_value(raw.get("white_balance"))
    if not white_balance:
        raise ValueError(
            "camera.white_balance is required (record manual white balance or 'auto')"
        )

    nominal = raw.get("nominal_fps")
    nominal_fps = _number(nominal, "camera.nominal_fps") if nominal not in (None, "") else None
    if nominal_fps is not None and nominal_fps <= 0:
        raise ValueError("camera.nominal_fps must be positive when supplied")

    return Camera(
        exposure_us=exposure_us,
        orientation_deg=orientation_deg,
        width=width,
        height=height,
        readout_us=readout_us,
        readout_direction=direction,
        readout_measured=measured,
        model=_text_value(raw.get("model")),
        gain=gain,
        white_balance=white_balance,
        nominal_fps=nominal_fps,
    )


def load_capture(
    path: Path | str,
    *,
    decoded_dir: Path | str | None = None,
    force_video_decode: bool = False,
    ffmpeg_cmd: str = "ffmpeg",
    ffprobe_cmd: str = "ffprobe",
) -> Capture:
    manifest_path = Path(path).resolve()
    raw = _read_json(manifest_path)
    if not isinstance(raw, dict):
        raise ValueError("capture manifest must be a JSON object")
    if raw.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"capture manifest schema must be {MANIFEST_SCHEMA}")

    evidence_kind = str(raw.get("evidence_kind", "")).strip()
    if evidence_kind not in EVIDENCE_KINDS:
        raise ValueError(
            "capture evidence_kind must be 'synthetic' or 'operator-hardware'"
        )

    camera = _parse_camera(raw.get("camera", {}))
    timestamp_basis = str(raw.get("timestamp_basis", "exposure_start")).strip()
    if timestamp_basis not in TIMESTAMP_BASES:
        raise ValueError(f"timestamp_basis must be one of {TIMESTAMP_BASES}")

    warnings: list[str] = []
    frames: list[Frame] = []
    frame_rows = raw.get("frames") or []
    video = raw.get("video")
    if force_video_decode:
        if not isinstance(video, dict) or not video.get("path"):
            raise ValueError("force_video_decode needs manifest.video.path")
        frame_rows = []

    if frame_rows:
        for row in frame_rows:
            frames.append(_frame_from_row(row, manifest_path.parent, "manifest"))
    elif isinstance(video, dict) and video.get("path"):
        if decoded_dir is None:
            raise ValueError(
                "manifest lists a video but no frames; provide a decoded frame directory"
            )
        from .video import decode_video

        video_path = Path(str(video["path"]))
        if not video_path.is_absolute():
            video_path = (manifest_path.parent / video_path).resolve()
        frames = list(
            decode_video(
                video_path,
                Path(decoded_dir),
                ffmpeg_cmd=ffmpeg_cmd,
                ffprobe_cmd=ffprobe_cmd,
            )
        )
        warnings.append("frames decoded with ffmpeg; timestamps came from ffprobe")
    else:
        raise ValueError("manifest must provide frames[] or video.path")

    if not frames:
        raise ValueError("manifest produced no frames")

    indices = [frame.index for frame in frames]
    if len(indices) != len(set(indices)):
        raise ValueError("manifest frame indices are not unique")
    frames.sort(key=lambda frame: frame.index)
    if len(frames) < 2:
        raise ValueError("at least two frames are required")

    timestamps = [frame.timestamp_s for frame in frames]
    for earlier, later in zip(timestamps, timestamps[1:]):
        if later < earlier:
            raise ValueError("frame timestamps run backwards; the capture clock is unusable")
        if later == earlier:
            warnings.append("two frames share a timestamp; timing is ambiguous around it")

    dropped = frozenset(int(item) for item in raw.get("dropped_frames", []))
    duplicated = frozenset(int(item) for item in raw.get("duplicated_frames", []))
    present = set(indices)
    contradictions = sorted(dropped & present)
    if contradictions:
        raise ValueError(
            f"dropped_frames {contradictions} are still present in frames"
        )
    missing_duplicates = sorted(duplicated - present)
    if missing_duplicates:
        raise ValueError(
            f"duplicated_frames {missing_duplicates} are not present in frames"
        )

    inferred = sorted(
        index
        for index in range(min(indices), max(indices) + 1)
        if index not in present and index not in dropped
    )
    if inferred:
        warnings.append(f"inferred missing frame indices not declared dropped: {inferred}")

    if camera.nominal_fps is not None:
        warnings.append(
            "camera.nominal_fps is recorded as metadata only; frame timing uses "
            "the actual timestamps"
        )

    return Capture(
        capture_id=str(raw.get("capture_id") or manifest_path.parent.name),
        evidence_kind=evidence_kind,
        camera=camera,
        frames=tuple(frames),
        dropped_frames=dropped,
        duplicated_frames=duplicated,
        timestamp_basis=timestamp_basis,
        manifest_path=manifest_path,
        clock=dict(raw.get("clock") or {}),
        panel_scanout=raw.get("panel_scanout"),
        notes=raw.get("notes"),
        warnings=tuple(warnings),
        video=dict(video) if isinstance(video, dict) else None,
    )


def point_in_polygon(x: float, y: float, polygon: Sequence[tuple[float, float]]) -> bool:
    inside = False
    count = len(polygon)
    if count < 3:
        return False
    j = count - 1
    for i in range(count):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y):
            crossing = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < crossing:
                inside = not inside
        j = i
    return inside


def polygon_bounds(
    polygon: Sequence[tuple[float, float]],
) -> tuple[float, float, float, float]:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _parse_polygon(value: Any, field: str) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        raise ValueError(f"{field} must have at least three points")
    points: list[tuple[float, float]] = []
    for index, point in enumerate(value):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError(f"{field}[{index}] must be [x, y]")
        points.append((
            _number(point[0], f"{field}[{index}].x"),
            _number(point[1], f"{field}[{index}].y"),
        ))
    return tuple(points)


def _parse_sample_points(
    value: Any,
    field: str,
    polygon: Sequence[tuple[float, float]],
) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        raise ValueError(f"{field} must have at least three sample points")
    points: list[tuple[float, float]] = []
    for index, point in enumerate(value):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError(f"{field}[{index}] must be [x, y]")
        x = _number(point[0], f"{field}[{index}].x")
        y = _number(point[1], f"{field}[{index}].y")
        if not point_in_polygon(x, y, polygon):
            raise ValueError(f"{field}[{index}] lies outside the polygon")
        points.append((x, y))
    return tuple(points)


def _fraction_list(value: Any, field: str, default: tuple[float, ...]) -> tuple[float, ...]:
    if value is None:
        return default
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"{field} must be a non-empty list of fractions")
    result: list[float] = []
    for item in value:
        fraction = _number(item, field)
        if not 0.0 < fraction < 1.0:
            raise ValueError(f"{field} values must be strictly between 0 and 1")
        result.append(fraction)
    return tuple(result)


def _grid_points(
    polygon: Sequence[tuple[float, float]],
    rows: Sequence[float],
    columns: Sequence[float],
) -> tuple[tuple[float, float], ...]:
    left, top, right, bottom = polygon_bounds(polygon)
    points: list[tuple[float, float]] = []
    for row in rows:
        y = top + (bottom - top) * row
        for column in columns:
            x = left + (right - left) * column
            if point_in_polygon(x, y, polygon):
                points.append((x, y))
    return tuple(points)


def _parse_region(
    raw: dict[str, Any],
    field: str,
    *,
    default_rows: tuple[float, ...] = (0.2, 0.4, 0.6, 0.8),
    default_columns: tuple[float, ...] = (0.15, 0.35, 0.5, 0.65, 0.85),
) -> Region:
    polygon = _parse_polygon(raw.get("polygon"), f"{field}.polygon")
    radius = _integer(raw.get("sample_radius", 1), f"{field}.sample_radius")
    if radius < 0 or radius > 50:
        raise ValueError(f"{field}.sample_radius must be between 0 and 50")
    if raw.get("sample_points") is not None:
        points = _parse_sample_points(raw["sample_points"], f"{field}.sample_points", polygon)
    else:
        rows = _fraction_list(raw.get("sample_rows"), f"{field}.sample_rows", default_rows)
        columns = _fraction_list(
            raw.get("sample_columns"), f"{field}.sample_columns", default_columns
        )
        points = _grid_points(polygon, rows, columns)
        if len(points) < 3:
            raise ValueError(
                f"{field} generated fewer than three probe points inside the polygon"
            )
    xs = {round(point[0], 6) for point in points}
    ys = {round(point[1], 6) for point in points}
    if len(xs) < 2 or len(ys) < 2:
        raise ValueError(
            f"{field} probe points must span at least two rows and two columns"
        )
    return Region(polygon=polygon, sample_points=points, sample_radius=radius)


def load_rois(
    path: Path | str,
    *,
    capture: Capture | None = None,
) -> ROISet:
    roi_path = Path(path).resolve()
    raw = _read_json(roi_path)
    if not isinstance(raw, dict):
        raise ValueError("ROI file must be a JSON object")
    if raw.get("schema") != ROIS_SCHEMA:
        raise ValueError(f"ROI schema must be {ROIS_SCHEMA}")

    coordinate_space = str(raw.get("coordinate_space", "delivered")).strip().lower()
    if coordinate_space not in ("delivered", "sensor"):
        raise ValueError("ROI coordinate_space must be 'delivered' or 'sensor'")
    if coordinate_space == "sensor" and capture is None:
        raise ValueError(
            "sensor-space ROIs need the capture camera metadata for conversion"
        )

    panel_rows = raw.get("panels")
    if not isinstance(panel_rows, list) or not panel_rows:
        raise ValueError("ROI file must contain a non-empty panels list")
    panels: dict[str, PanelROI] = {}
    for index, panel_raw in enumerate(panel_rows):
        if not isinstance(panel_raw, dict):
            raise ValueError(f"panels[{index}] must be an object")
        panel_id = str(panel_raw.get("panel_id") or panel_raw.get("id") or "").strip()
        if not panel_id:
            raise ValueError(f"panels[{index}] needs panel_id")
        if panel_id in panels:
            raise ValueError(f"duplicate panel id {panel_id!r}")
        region = _parse_region(panel_raw, f"panels[{index}]")
        noise_raw = panel_raw.get("noise_reference")
        if not isinstance(noise_raw, dict):
            raise ValueError(
                f"panels[{index}].noise_reference is required and must be an object"
            )
        noise_region = _parse_region(
            noise_raw,
            f"panels[{index}].noise_reference",
            default_rows=(0.35, 0.65),
            default_columns=(0.35, 0.65),
        )
        for vertex in noise_region.polygon:
            if not point_in_polygon(vertex[0], vertex[1], region.polygon):
                raise ValueError(
                    f"panels[{index}].noise_reference lies outside the panel polygon"
                )
        for point in noise_region.sample_points:
            if not point_in_polygon(point[0], point[1], region.polygon):
                raise ValueError(
                    f"panels[{index}].noise_reference probe lies outside the panel polygon"
                )
        panels[panel_id] = PanelROI(
            panel_id=panel_id,
            region=region,
            noise_region=noise_region,
        )

    if coordinate_space == "sensor":
        assert capture is not None
        camera = capture.camera

        def transform(region: Region) -> Region:
            return Region(
                polygon=tuple(
                    sensor_to_delivered(x, y, camera) for x, y in region.polygon
                ),
                sample_points=tuple(
                    sensor_to_delivered(x, y, camera) for x, y in region.sample_points
                ),
                sample_radius=region.sample_radius,
            )

        panels = {
            panel_id: PanelROI(
                panel_id=panel_id,
                region=transform(panel.region),
                noise_region=(
                    transform(panel.noise_region)
                    if panel.noise_region is not None else None
                ),
            )
            for panel_id, panel in panels.items()
        }

    source_roi = raw.get("source_frame_roi")
    digits = _integer(raw.get("source_frame_digits", 6), "source_frame_digits")
    source_frame = raw.get("source_frame")
    if source_roi is None and isinstance(source_frame, dict):
        source_roi = source_frame.get("roi")
        digits = _integer(source_frame.get("digits", digits), "source_frame.digits")
    if source_roi is not None:
        if not isinstance(source_roi, (list, tuple)) or len(source_roi) != 4:
            raise ValueError("source_frame_roi must be [x, y, width, height]")
        source_roi = tuple(
            _integer(item, "source_frame_roi component") for item in source_roi
        )
        if source_roi[2] <= 0 or source_roi[3] <= 0:
            raise ValueError("source_frame_roi width and height must be positive")
    if digits < 1 or digits > 12:
        raise ValueError("source_frame_digits must be between 1 and 12")

    if capture is not None:
        if capture.video and capture.video.get("path") and source_roi is None:
            video_roi = capture.video.get("source_frame_roi")
            if isinstance(video_roi, (list, tuple)) and len(video_roi) == 4:
                source_roi = tuple(
                    _integer(item, "video.source_frame_roi component")
                    for item in video_roi
                )
        for panel in panels.values():
            for x, y in panel.region.sample_points:
                if not (0 <= x < capture.camera.width and 0 <= y < capture.camera.height):
                    raise ValueError(
                        f"panel {panel.panel_id} has a probe point outside the "
                        f"{capture.camera.width}x{capture.camera.height} frame"
                    )
            if panel.noise_region is not None:
                for x, y in panel.noise_region.sample_points:
                    if not (
                        0 <= x < capture.camera.width and 0 <= y < capture.camera.height
                    ):
                        raise ValueError(
                            f"panel {panel.panel_id} noise probe is outside the frame"
                        )
        if source_roi is not None:
            x, y, width, height = source_roi
            if x < 0 or y < 0 or x + width > capture.camera.width or y + height > capture.camera.height:
                raise ValueError("source_frame_roi is outside the captured frame")

    return ROISet(
        panels=panels,
        source_frame_roi=source_roi,  # type: ignore[arg-type]
        source_frame_digits=digits,
        coordinate_space=coordinate_space,
    )


def _target_from_patch(path: Path) -> RGB:
    try:
        with Image.open(path) as image:
            image = image.convert("RGB")
            mean = ImageStat.Stat(image).mean
    except OSError as error:
        raise ValueError(f"cannot read target patch {path}: {error}") from error
    return (float(mean[0]), float(mean[1]), float(mean[2]))


def _event_from_mapping(
    raw: dict[str, Any],
    *,
    base: Path,
    source: str,
) -> Event:
    event_id = str(raw.get("event_id") or raw.get("id") or "").strip()
    if not event_id:
        raise ValueError(f"{source}: event_id is required")

    reference = raw.get("reference")
    reference_frame = raw.get("reference_frame")
    reference_time = raw.get("reference_time_s", raw.get("reference_time"))
    if isinstance(reference, dict):
        reference_frame = reference.get("frame", reference.get("frame_index", reference_frame))
        reference_time = reference.get("time_s", reference.get("time", reference_time))
    if reference_frame in (None, "") and reference_time in (None, ""):
        raise ValueError(f"{source}: event {event_id} needs reference_frame or reference_time_s")
    ref_frame = (
        _integer(reference_frame, f"{source}: event {event_id} reference_frame")
        if reference_frame not in (None, "")
        else None
    )
    ref_time = (
        _number(reference_time, f"{source}: event {event_id} reference_time_s")
        if reference_time not in (None, "")
        else None
    )
    if ref_frame is not None and ref_frame < 0:
        raise ValueError(f"{source}: event {event_id} reference_frame cannot be negative")
    if ref_time is not None and ref_time < 0:
        raise ValueError(f"{source}: event {event_id} reference_time_s cannot be negative")

    window = raw.get("search_window")
    if isinstance(window, dict):
        before = window.get("before_ms", window.get("before", 0))
        after = window.get("after_ms", window.get("after", 200))
    else:
        before = raw.get("search_before_ms", raw.get("before_ms", 0))
        after = raw.get("search_after_ms", raw.get("after_ms", 200))
    before_s = _number(before, f"{source}: event {event_id} search before") / 1000.0
    after_s = _number(after, f"{source}: event {event_id} search after") / 1000.0
    if before_s < 0 or after_s < 0:
        raise ValueError(f"{source}: event {event_id} search window cannot be negative")
    if before_s == 0 and after_s == 0:
        raise ValueError(f"{source}: event {event_id} search window is empty")

    expected = raw.get("expected_panels", raw.get("panels"))
    if expected is None:
        raise ValueError(f"{source}: event {event_id} needs expected_panels")
    expected_panels = _parse_panels(expected, f"{source}: event {event_id} expected_panels")
    if len(expected_panels) < 2:
        raise ValueError(
            f"{source}: event {event_id} must name at least two expected panels; "
            "a single panel cannot measure wall-wide skew"
        )

    target = raw.get("target")
    tolerance_default = raw.get("target_tolerance")
    if isinstance(target, dict):
        rgb_value = (
            target.get("rgb", target.get("colour", target.get("color")))
        )
        patch_value = target.get("patch")
        tolerance_value = target.get("tolerance", tolerance_default)
    elif isinstance(target, (list, tuple)):
        rgb_value = target
        patch_value = None
        tolerance_value = tolerance_default
    else:
        rgb_value = (
            raw.get("target_rgb")
            or raw.get("target_colour")
            or raw.get("target_color")
        )
        patch_value = raw.get("target_patch")
        tolerance_value = tolerance_default

    if rgb_value not in (None, ""):
        target_rgb = _parse_rgb(rgb_value, f"{source}: event {event_id} target colour")
    elif patch_value not in (None, ""):
        patch_path = Path(str(patch_value))
        if not patch_path.is_absolute():
            patch_path = (base / patch_path).resolve()
        target_rgb = _target_from_patch(patch_path)
    else:
        raise ValueError(f"{source}: event {event_id} needs a target colour or patch")

    tolerance = (
        _number(tolerance_value, f"{source}: event {event_id} target_tolerance")
        if tolerance_value not in (None, "")
        else 30.0
    )
    if tolerance <= 0:
        raise ValueError(f"{source}: event {event_id} target_tolerance must be positive")
    fraction = raw.get("min_target_fraction")
    min_target_fraction = (
        _number(fraction, f"{source}: event {event_id} min_target_fraction")
        if fraction not in (None, "")
        else 0.60
    )
    if not 0.0 < min_target_fraction <= 1.0:
        raise ValueError(
            f"{source}: event {event_id} min_target_fraction must be in (0, 1]"
        )
    source_frame = raw.get("source_frame")
    source_frame_value = (
        _integer(source_frame, f"{source}: event {event_id} source_frame")
        if source_frame not in (None, "")
        else None
    )
    return Event(
        event_id=event_id,
        reference_frame=ref_frame,
        reference_time_s=ref_time,
        search_before_s=before_s,
        search_after_s=after_s,
        expected_panels=expected_panels,
        target_rgb=target_rgb,
        target_tolerance=tolerance,
        min_target_fraction=min_target_fraction,
        steady_state=_boolean(raw.get("steady_state"), f"{source}: event {event_id} steady_state"),
        source_frame=source_frame_value,
        notes=_text_value(raw.get("notes")),
    )


def _normalise_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    normalised: dict[str, Any] = {}
    for key, value in row.items():
        if key is None:
            continue
        name = key.strip().lower()
        if isinstance(value, str):
            value = value.strip()
        normalised[name] = value
    return normalised


def _events_from_csv(path: Path) -> list[Event]:
    try:
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            rows = [dict(row) for row in reader]
    except OSError as error:
        raise ValueError(f"cannot read events CSV {path}: {error}") from error
    if not rows:
        raise ValueError("events CSV is empty")
    events: list[Event] = []
    for line, row in enumerate(rows, start=2):
        raw = _normalise_csv_row(row)
        if "target_rgb" not in raw and "target_colour" not in raw and "target_color" not in raw:
            red = raw.get("target_r", raw.get("r"))
            green = raw.get("target_g", raw.get("g"))
            blue = raw.get("target_b", raw.get("b"))
            if red not in (None, "") and green not in (None, "") and blue not in (None, ""):
                raw["target_rgb"] = f"{red},{green},{blue}"
        if "expected_panels" not in raw and "panels" in raw:
            raw["expected_panels"] = raw["panels"]
        if "reference_time_s" not in raw and "reference_time" in raw:
            raw["reference_time_s"] = raw["reference_time"]
        try:
            events.append(_event_from_mapping(raw, base=path.parent, source=f"events.csv line {line}"))
        except ValueError as error:
            raise ValueError(f"events.csv line {line}: {error}") from error
    return events


def load_events(path: Path | str) -> list[Event]:
    event_path = Path(path).resolve()
    if event_path.suffix.lower() == ".csv":
        events = _events_from_csv(event_path)
    else:
        raw = _read_json(event_path)
        if isinstance(raw, dict):
            if raw.get("schema") not in (None, EVENTS_SCHEMA):
                raise ValueError(f"events schema must be {EVENTS_SCHEMA}")
            rows = raw.get("events")
        else:
            rows = raw
        if not isinstance(rows, list) or not rows:
            raise ValueError("events file must contain a non-empty events list")
        events = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"events[{index}] must be an object")
            events.append(_event_from_mapping(row, base=event_path.parent, source=f"events[{index}]"))
    if not events:
        raise ValueError("events file contains no events")
    ids = [event.event_id for event in events]
    if len(ids) != len(set(ids)):
        raise ValueError("event ids are not unique")
    return events


def validate_panel_coverage(events: Iterable[Event], rois: ROISet) -> None:
    known = set(rois.panels)
    for event in events:
        missing = [panel for panel in event.expected_panels if panel not in known]
        if missing:
            raise ValueError(
                f"event {event.event_id} expects panels without ROIs: {missing}"
            )
