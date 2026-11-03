"""Validate a complete tagged layout before it replaces the active arrangement."""

from collections.abc import Callable
from copy import deepcopy
from math import isfinite
from typing import Any

from tabletwall import sizing
from tabletwall.protocol import MAX_DEVICES, _parse_device_id

RecordReader = Callable[[str, int], dict[str, Any] | None]


def kind(layout: dict[str, Any]) -> str:
    return "physical" if layout.get("kind") == "physical" else "logical"


def entries(layout: dict[str, Any]) -> dict[str, Any]:
    return layout["slots"] if kind(layout) == "physical" else layout["placements"]


def normalize(
    document: dict[str, Any], *, profile_for: RecordReader, calibration_for: RecordReader,
) -> dict[str, Any]:
    physical = document.get("kind") == "physical"
    allowed = {"kind", "bounds", "slots", "sizing"} if physical else {
        "kind", "width", "height", "placements", "sizing",
    }
    if set(document) - allowed or document.get("kind", "logical") not in ("logical", "physical"):
        raise ValueError("layout has unknown fields or kind")
    result = deepcopy(document)
    if "sizing" in result:
        config = sizing.validate_sizing(result["sizing"], logical=not physical)
        if config is None:
            raise ValueError("invalid layout sizing")
        result["sizing"] = config
    if physical:
        _physical(result, profile_for, calibration_for)
    else:
        result.pop("kind", None)
        _logical(result)
    return result


def _identities(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or len(value) > MAX_DEVICES:
        raise ValueError("layout entries must be a bounded mapping")
    for device_id in value:
        if not isinstance(device_id, str) or _parse_device_id(device_id) != device_id:
            raise ValueError("layout device_id must be a canonical UUID4")
    return value


def _logical(layout: dict[str, Any]) -> None:
    for key in ("width", "height"):
        if type(layout.get(key)) is not int or layout[key] <= 0:
            raise ValueError(f"layout.{key} must be a positive integer")
    for device_id, placement in _identities(layout.get("placements")).items():
        if not isinstance(placement, dict) or set(placement) != {
            "device_id", "x", "y", "w", "h", "bezel",
        } or placement["device_id"] != device_id:
            raise ValueError("logical placement has invalid fields or identity")
        if any(type(placement.get(key)) is not int for key in ("x", "y", "w", "h")):
            raise ValueError("logical placement coordinates must be integers")
        bezel = placement["bezel"]
        if not isinstance(bezel, dict) or set(bezel) != {"left", "right", "top", "bottom"}:
            raise ValueError("logical bezel requires all four edges")
        if any(type(value) is not int or value < 0 for value in bezel.values()):
            raise ValueError("logical bezel edges must be non-negative integers")
        if (placement["w"] - bezel["left"] - bezel["right"] <= 0
                or placement["h"] - bezel["top"] - bezel["bottom"] <= 0):
            raise ValueError("logical bezel must leave a positive visible rectangle")


def _physical(layout: dict[str, Any], profile_for: RecordReader, calibration_for: RecordReader) -> None:
    bounds = layout.get("bounds")
    if not isinstance(bounds, dict) or set(bounds) != {"x", "y", "width", "height"}:
        raise ValueError("physical bounds require x, y, width and height")
    for value in bounds.values():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise ValueError("physical bounds must be finite numbers")
    if bounds["width"] <= 0 or bounds["height"] <= 0:
        raise ValueError("physical bounds must be positive")
    layout["bounds"] = {key: float(value) for key, value in bounds.items()}
    pose = {"center_x_mm", "center_y_mm", "mount_angle", "nudge_x_mm", "nudge_y_mm"}
    required = pose | {"profile_revision", "calibration_revision"}
    for device_id, slot in _identities(layout.get("slots")).items():
        if not isinstance(slot, dict) or not required <= set(slot) or set(slot) - required - {"participating"}:
            raise ValueError("physical slot has missing or unknown fields")
        for key in pose:
            value = slot[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                raise ValueError(f"slot.{key} must be a finite number")
        for key in ("profile_revision", "calibration_revision"):
            if type(slot[key]) is not int or slot[key] <= 0:
                raise ValueError(f"slot.{key} must be a positive integer")
        profile = profile_for(device_id, slot["profile_revision"])
        calibration = calibration_for(device_id, slot["calibration_revision"])
        if profile is None or calibration is None or calibration["profile_revision"] != slot["profile_revision"]:
            raise ValueError("slot measurements do not exist or refer to different revisions")
        if "participating" in slot and type(slot["participating"]) is not bool:
            raise ValueError("slot.participating must be a boolean")
