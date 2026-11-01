"""Immutable display measurements and calibrations (schema 2, R2).

A display ID names a browser endpoint, not a hardware fingerprint. Every
update appends a revision; a saved layout keeps the revision it was built
against, so editing a measurement never silently changes an old layout.
"""

import math
import uuid
from datetime import datetime, timezone
from typing import Any, cast

from tabletwall import persist


class DisplayError(ValueError):
    """An invalid measurement or calibration."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _positive(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise DisplayError(f"{label} must be a number")
    if not math.isfinite(value) or value <= 0:
        raise DisplayError(f"{label} must be finite and positive")
    return float(value)


def _nonnegative(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise DisplayError(f"{label} must be a number")
    if not math.isfinite(value) or value < 0:
        raise DisplayError(f"{label} must be finite and non-negative")
    return float(value)


def _device(device_id: str) -> str:
    try:
        parsed = uuid.UUID(device_id)
    except (TypeError, ValueError) as error:
        raise DisplayError("device_id must be a UUID4") from error
    if parsed.version != 4:
        raise DisplayError("device_id must be a UUID4")
    return str(parsed)


def save_profile(
    device_id: str,
    *,
    active_width_mm: float,
    active_height_mm: float,
    bezels: dict[str, Any],
    panel_pixels: dict[str, Any] | None,
    label: str,
    provenance: str,
) -> dict[str, Any]:
    """Append one immutable display profile revision."""
    device = _device(device_id)
    width = _positive(active_width_mm, "active_width_mm")
    height = _positive(active_height_mm, "active_height_mm")
    left = _nonnegative(bezels.get("left"), "bezel left")
    top = _nonnegative(bezels.get("top"), "bezel top")
    right = _nonnegative(bezels.get("right"), "bezel right")
    bottom = _nonnegative(bezels.get("bottom"), "bezel bottom")
    pixel_width: float | None
    pixel_height: float | None
    if panel_pixels is not None:
        pixel_width = _positive(panel_pixels.get("width"), "panel pixel width")
        pixel_height = _positive(panel_pixels.get("height"), "panel pixel height")
    else:
        pixel_width = pixel_height = None
    if not isinstance(label, str) or not 1 <= len(label) <= 80:
        raise DisplayError("label must be 1..80 characters")
    if not isinstance(provenance, str) or not 1 <= len(provenance) <= 40:
        raise DisplayError("provenance must be 1..40 characters")
    with persist._connection() as connection:
        revision = int(connection.execute(
            "SELECT COALESCE(MAX(revision), 0) + 1 FROM display_profiles "
            "WHERE device_id = ?", (device,),
        ).fetchone()[0])
        connection.execute(
            "INSERT INTO display_profiles (device_id, revision, active_width_mm, "
            "active_height_mm, bezel_left_mm, bezel_top_mm, bezel_right_mm, "
            "bezel_bottom_mm, panel_pixels_width, panel_pixels_height, label, "
            "provenance, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (device, revision, width, height, left, top, right, bottom,
             pixel_width, pixel_height, label, provenance, _now()),
        )
    return cast(dict[str, Any], profile(device, revision))


def save_calibration(
    device_id: str,
    *,
    profile_revision: int,
    viewport_width: float,
    viewport_height: float,
    dpr: float,
    orientation: int,
    mode: str,
    quarter_turn: int,
    panel_offset_mm: tuple[float, float],
    mm_per_css: tuple[float, float],
    anchor_edge: str,
    uncertainty_mm: float,
    method: str,
) -> dict[str, Any]:
    """Append one immutable calibration revision for a measured profile."""
    device = _device(device_id)
    if not isinstance(profile_revision, int) or profile_revision < 1:
        raise DisplayError("profile_revision must be a positive integer")
    if profile(device, profile_revision) is None:
        raise DisplayError("profile_revision does not exist")
    width = _positive(viewport_width, "viewport_width")
    height = _positive(viewport_height, "viewport_height")
    ratio = _positive(dpr, "dpr")
    if orientation not in (0, 90, 180, 270):
        raise DisplayError("orientation must be 0, 90, 180 or 270")
    if mode not in ("tab", "fullscreen", "standalone"):
        raise DisplayError("mode must be tab, fullscreen or standalone")
    if quarter_turn not in (0, 1, 2, 3):
        raise DisplayError("quarter_turn must be 0, 1, 2 or 3")
    offset_x = _negative_number(panel_offset_mm[0], "panel offset x")
    offset_y = _negative_number(panel_offset_mm[1], "panel offset y")
    mm_x = _positive(mm_per_css[0], "mm_per_css x")
    mm_y = _positive(mm_per_css[1], "mm_per_css y")
    if anchor_edge not in ("top-left", "top-right", "bottom-left", "bottom-right"):
        raise DisplayError("anchor_edge is not a supported edge")
    uncertainty = _nonnegative(uncertainty_mm, "uncertainty_mm")
    if not isinstance(method, str) or not 1 <= len(method) <= 80:
        raise DisplayError("method must be 1..80 characters")
    with persist._connection() as connection:
        revision = int(connection.execute(
            "SELECT COALESCE(MAX(revision), 0) + 1 FROM calibrations "
            "WHERE device_id = ?", (device,),
        ).fetchone()[0])
        connection.execute(
            "INSERT INTO calibrations (device_id, revision, profile_revision, "
            "viewport_width, viewport_height, dpr, orientation, mode, quarter_turn, "
            "panel_offset_x_mm, panel_offset_y_mm, mm_per_css_x, mm_per_css_y, "
            "anchor_edge, uncertainty_mm, method, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (device, revision, profile_revision, width, height, ratio, orientation,
             mode, quarter_turn, offset_x, offset_y, mm_x, mm_y, anchor_edge,
             uncertainty, method, _now()),
        )
    return cast(dict[str, Any], calibration(device, revision))


def copy_records(
    source_id: str, target_id: str, *, revision_offsets: tuple[int, int] | None = None
) -> dict[str, int]:
    """Copy every profile and calibration revision from one device to another.

    Origin migration gives a physical tablet a new ID; a saved slot names
    revisions, so rows retain their revision numbers unless offsets are supplied. The
    source rows are never touched (they stay the history older layouts name).
    Offsets append after an automatically profiled target's existing revisions.
    Without offsets, a target with its own records is refused.
    """
    source, target = _device(source_id), _device(target_id)
    with persist._connection() as connection:
        count = (
            "SELECT (SELECT COUNT(*) FROM display_profiles WHERE device_id = ?) + "
            "(SELECT COUNT(*) FROM calibrations WHERE device_id = ?)"
        )
        if not connection.execute(count, (source, source)).fetchone()[0]:
            return {"profiles": 0, "calibrations": 0}
        if revision_offsets is None and connection.execute(count, (target, target)).fetchone()[0]:
            raise DisplayError("the new device already has display records")
        profile_offset, calibration_offset = revision_offsets or (0, 0)
        profiles = connection.execute(
            "INSERT INTO display_profiles SELECT ?, revision + ?, active_width_mm, "
            "active_height_mm, bezel_left_mm, bezel_top_mm, bezel_right_mm, "
            "bezel_bottom_mm, panel_pixels_width, panel_pixels_height, label, "
            "provenance, created_at FROM display_profiles WHERE device_id = ?",
            (target, profile_offset, source),
        ).rowcount
        calibrations = connection.execute(
            "INSERT INTO calibrations SELECT ?, revision + ?, profile_revision + ?, "
            "viewport_width, viewport_height, dpr, orientation, mode, quarter_turn, "
            "panel_offset_x_mm, panel_offset_y_mm, mm_per_css_x, mm_per_css_y, "
            "anchor_edge, uncertainty_mm, method, created_at "
            "FROM calibrations WHERE device_id = ?",
            (target, calibration_offset, profile_offset, source),
        ).rowcount
    return {"profiles": profiles, "calibrations": calibrations}


def _negative_number(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise DisplayError(f"{label} must be a number")
    if not math.isfinite(value):
        raise DisplayError(f"{label} must be finite")
    return float(value)


def profile(device_id: str, revision: int) -> dict[str, Any] | None:
    with persist._connection() as connection:
        row = connection.execute(
            "SELECT device_id, revision, active_width_mm, active_height_mm, "
            "bezel_left_mm, bezel_top_mm, bezel_right_mm, bezel_bottom_mm, "
            "panel_pixels_width, panel_pixels_height, label, provenance, created_at "
            "FROM display_profiles WHERE device_id = ? AND revision = ?",
            (device_id, revision),
        ).fetchone()
    return _profile_row(row)


def latest_profile(device_id: str) -> dict[str, Any] | None:
    with persist._connection() as connection:
        row = connection.execute(
            "SELECT device_id, revision, active_width_mm, active_height_mm, "
            "bezel_left_mm, bezel_top_mm, bezel_right_mm, bezel_bottom_mm, "
            "panel_pixels_width, panel_pixels_height, label, provenance, created_at "
            "FROM display_profiles WHERE device_id = ? ORDER BY revision DESC LIMIT 1",
            (device_id,),
        ).fetchone()
    return _profile_row(row)


def calibration(device_id: str, revision: int) -> dict[str, Any] | None:
    with persist._connection() as connection:
        row = connection.execute(
            "SELECT device_id, revision, profile_revision, viewport_width, "
            "viewport_height, dpr, orientation, mode, quarter_turn, "
            "panel_offset_x_mm, panel_offset_y_mm, mm_per_css_x, mm_per_css_y, "
            "anchor_edge, uncertainty_mm, method, created_at FROM calibrations "
            "WHERE device_id = ? AND revision = ?",
            (device_id, revision),
        ).fetchone()
    return _calibration_row(row)


def latest_calibration(device_id: str) -> dict[str, Any] | None:
    with persist._connection() as connection:
        row = connection.execute(
            "SELECT device_id, revision, profile_revision, viewport_width, "
            "viewport_height, dpr, orientation, mode, quarter_turn, "
            "panel_offset_x_mm, panel_offset_y_mm, mm_per_css_x, mm_per_css_y, "
            "anchor_edge, uncertainty_mm, method, created_at FROM calibrations "
            "WHERE device_id = ? ORDER BY revision DESC LIMIT 1",
            (device_id,),
        ).fetchone()
    return _calibration_row(row)


def calibration_for(
    device_id: str, profile_revision: int
) -> dict[str, Any] | None:
    with persist._connection() as connection:
        row = connection.execute(
            "SELECT device_id, revision, profile_revision, viewport_width, "
            "viewport_height, dpr, orientation, mode, quarter_turn, "
            "panel_offset_x_mm, panel_offset_y_mm, mm_per_css_x, mm_per_css_y, "
            "anchor_edge, uncertainty_mm, method, created_at FROM calibrations "
            "WHERE device_id = ? AND profile_revision = ? "
            "ORDER BY revision DESC LIMIT 1",
            (device_id, profile_revision),
        ).fetchone()
    return _calibration_row(row)


def list_profiles() -> list[dict[str, Any]]:
    with persist._connection() as connection:
        rows = connection.execute(
            "SELECT p.device_id, p.revision, p.active_width_mm, p.active_height_mm, "
            "p.bezel_left_mm, p.bezel_top_mm, p.bezel_right_mm, p.bezel_bottom_mm, "
            "p.panel_pixels_width, p.panel_pixels_height, p.label, p.provenance, "
            "p.created_at FROM display_profiles p JOIN ("
            "SELECT device_id, MAX(revision) AS revision FROM display_profiles "
            "GROUP BY device_id) latest "
            "ON latest.device_id = p.device_id AND latest.revision = p.revision "
            "ORDER BY p.device_id"
        ).fetchall()
    return [cast(dict[str, Any], _profile_row(row)) for row in rows]


def list_calibrations() -> list[dict[str, Any]]:
    with persist._connection() as connection:
        rows = connection.execute(
            "SELECT c.device_id, c.revision, c.profile_revision, c.viewport_width, "
            "c.viewport_height, c.dpr, c.orientation, c.mode, c.quarter_turn, "
            "c.panel_offset_x_mm, c.panel_offset_y_mm, c.mm_per_css_x, "
            "c.mm_per_css_y, c.anchor_edge, c.uncertainty_mm, c.method, c.created_at "
            "FROM calibrations c JOIN ("
            "SELECT device_id, MAX(revision) AS revision FROM calibrations "
            "GROUP BY device_id) latest "
            "ON latest.device_id = c.device_id AND latest.revision = c.revision "
            "ORDER BY c.device_id"
        ).fetchall()
    return [cast(dict[str, Any], _calibration_row(row)) for row in rows]


def _profile_row(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "device_id": str(row[0]),
        "revision": int(row[1]),
        "active_width_mm": float(row[2]),
        "active_height_mm": float(row[3]),
        "bezels": {"left": float(row[4]), "top": float(row[5]),
                   "right": float(row[6]), "bottom": float(row[7])},
        "panel_pixels": (
            {"width": int(row[8]), "height": int(row[9])}
            if row[8] is not None and row[9] is not None else None
        ),
        "label": str(row[10]),
        "provenance": str(row[11]),
        "created_at": str(row[12]),
    }


def _calibration_row(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "device_id": str(row[0]),
        "revision": int(row[1]),
        "profile_revision": int(row[2]),
        "viewport_width": float(row[3]),
        "viewport_height": float(row[4]),
        "dpr": float(row[5]),
        "orientation": int(row[6]),
        "mode": str(row[7]),
        "quarter_turn": int(row[8]),
        "panel_offset_mm": [float(row[9]), float(row[10])],
        "mm_per_css": [float(row[11]), float(row[12])],
        "anchor_edge": str(row[13]),
        "uncertainty_mm": float(row[14]),
        "method": str(row[15]),
        "created_at": str(row[16]),
    }


def histories() -> tuple[dict[str, dict[int, dict[str, Any]]], dict[str, dict[int, dict[str, Any]]]]:
    """All revisions for transactional lifecycle plans and durable digests."""
    profiles: dict[str, dict[int, dict[str, Any]]] = {}
    calibrations: dict[str, dict[int, dict[str, Any]]] = {}
    with persist._connection() as connection:
        profile_keys = connection.execute("SELECT device_id, revision FROM display_profiles ORDER BY device_id, revision").fetchall()
        calibration_keys = connection.execute("SELECT device_id, revision FROM calibrations ORDER BY device_id, revision").fetchall()
    for device_id, revision in profile_keys:
        value = profile(device_id, revision)
        if value is not None:
            profiles.setdefault(device_id, {})[revision] = value
    for device_id, revision in calibration_keys:
        value = calibration(device_id, revision)
        if value is not None:
            calibrations.setdefault(device_id, {})[revision] = value
    return profiles, calibrations
