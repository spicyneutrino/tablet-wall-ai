"""Pure wall fitting and packing calculations."""

from __future__ import annotations

import math
from typing import Any, Callable


def sizing_config(layout: dict[str, Any]) -> dict[str, Any]:
    value = layout.get("sizing")
    if not isinstance(value, dict):
        return {"mode": "fixed", "padding": 0}
    return value


def validate_sizing(value: Any, *, logical: bool = False) -> dict[str, Any] | None:
    if not isinstance(value, dict) or set(value) - {"mode", "padding"}:
        return None
    mode = value.get("mode")
    padding = value.get("padding", 0)
    if mode not in ("fixed", "tablets") or isinstance(padding, bool):
        return None
    if not isinstance(padding, (int, float)) or not math.isfinite(padding) or padding < 0:
        return None
    if logical and not float(padding).is_integer():
        return None
    return {"mode": mode, "padding": int(padding) if logical else float(padding)}


def fit_logical(layout: dict[str, Any]) -> None:
    config = sizing_config(layout)
    if config["mode"] != "tablets":
        return
    placements = layout["placements"]
    if not placements:
        return
    left = min(p["x"] for p in placements.values())
    top = min(p["y"] for p in placements.values())
    right = max(p["x"] + p["w"] for p in placements.values())
    bottom = max(p["y"] + p["h"] for p in placements.values())
    padding = int(config["padding"])
    dx, dy = padding - left, padding - top
    for placement in placements.values():
        placement["x"] += dx
        placement["y"] += dy
    layout["width"] = max(1, right - left + padding * 2)
    layout["height"] = max(1, bottom - top + padding * 2)


def fit_physical(
    layout: dict[str, Any], profile_for: Callable[[str, int], dict[str, Any] | None]
) -> None:
    config = sizing_config(layout)
    if config["mode"] != "tablets":
        return
    slots = layout["slots"]
    if not slots:
        return
    extents: list[tuple[float, float, float, float]] = []
    for device_id, slot in slots.items():
        profile = profile_for(device_id, slot["profile_revision"])
        if profile is None:
            raise ValueError("slot display profile does not exist")
        values = [
            slot.get(key)
            for key in (
                "center_x_mm", "center_y_mm", "mount_angle", "nudge_x_mm", "nudge_y_mm"
            )
        ]
        values.extend((profile.get("active_width_mm"), profile.get("active_height_mm")))
        bezels = profile.get("bezels")
        if not isinstance(bezels, dict):
            raise ValueError("slot display profile has invalid bezels")
        values.extend(bezels.get(key) for key in ("left", "right", "top", "bottom"))
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
            raise ValueError("physical layout values must be finite numbers")
        if (
            profile["active_width_mm"] <= 0
            or profile["active_height_mm"] <= 0
            or any(bezels[k] < 0 for k in ("left", "right", "top", "bottom"))
        ):
            raise ValueError("slot display profile has invalid dimensions")
        width = profile["active_width_mm"] + bezels["left"] + bezels["right"]
        height = profile["active_height_mm"] + bezels["top"] + bezels["bottom"]
        angle = math.radians(slot["mount_angle"])
        half_x = (abs(math.cos(angle)) * width + abs(math.sin(angle)) * height) / 2
        half_y = (abs(math.sin(angle)) * width + abs(math.cos(angle)) * height) / 2
        cx = slot["center_x_mm"] + slot["nudge_x_mm"]
        cy = slot["center_y_mm"] + slot["nudge_y_mm"]
        extents.append((cx - half_x, cy - half_y, cx + half_x, cy + half_y))
    padding = config["padding"]
    min_x = min(box[0] for box in extents)
    min_y = min(box[1] for box in extents)
    max_x = max(box[2] for box in extents)
    max_y = max(box[3] for box in extents)
    bounds = {
        "x": min_x - padding,
        "y": min_y - padding,
        "width": max_x - min_x + 2 * padding,
        "height": max_y - min_y + 2 * padding,
    }
    if not all(math.isfinite(value) for value in bounds.values()) or bounds["width"] <= 0 or bounds["height"] <= 0:
        raise ValueError("computed wall bounds must be finite and positive")
    layout["bounds"] = bounds


def pack_logical(layout: dict[str, Any], columns: int, gap: int) -> None:
    placements = layout["placements"]
    ordered = sorted(placements.values(), key=lambda p: (p["y"], p["x"], p["device_id"]))
    row_heights = [max(p["h"] for p in ordered[i:i + columns]) for i in range(0, len(ordered), columns)]
    row_y: list[int] = []
    y = 0
    for height in row_heights:
        row_y.append(y)
        y += height + gap
    for i, placement in enumerate(ordered):
        row, col = divmod(i, columns)
        placement["x"] = sum(ordered[row * columns + j]["w"] + gap for j in range(col))
        placement["y"] = row_y[row]
