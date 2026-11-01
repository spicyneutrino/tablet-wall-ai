"""Measured tablet models and revision-pinned viewport adaptation."""
import math
from collections.abc import Iterable
from copy import deepcopy
from typing import Any

from tabletwall import displays, persist

BUILTINS: dict[str, dict[str, Any]] = {
    "ipad-air-2": {"label": "iPad Air 2", "active_width_mm": 146.75, "active_height_mm": 196.0,
        "bezels": {"left": 10.52, "right": 10.52, "top": 21.1, "bottom": 21.1},
        "screen_width": 768, "screen_height": 1024, "portrait_angle": 0, "dpr": 2.0, "platform": "ios", "mm_per_css": [0.187725, 0.187725], "uncertainty_mm": 3.0},
    "google-pixel-c": {"label": "Google Pixel C", "active_width_mm": 147.0, "active_height_mm": 210.0,
        "bezels": {"left": 15.2, "right": 15.2, "top": 15.2, "bottom": 15.2},
        "screen_width": 900, "screen_height": 1280, "portrait_angle": 270, "dpr": 2.0, "platform": "android", "mm_per_css": [0.16195, 0.16195], "uncertainty_mm": 3.0},
}


def assignments() -> dict[str, Any]:
    value = persist.load_meta("tablet_model_assignments")
    return value if isinstance(value, dict) else {}


def snapshot_for_calibration(
    calibration: dict[str, Any], candidates: Iterable[dict[str, Any]],
) -> dict[str, Any] | None:
    """Inherit only an unambiguous historical model with this profile and CSS scale."""
    if calibration.get("method") != "tablet-model approximate":
        return None
    css_scale = calibration.get("mm_per_css")
    if not isinstance(css_scale, list) or len(css_scale) != 2:
        return None
    matches = [candidate for candidate in candidates
        if isinstance(candidate, dict) and isinstance(candidate.get("model"), dict)
        and candidate.get("model_id")
        and candidate.get("profile_revision") == calibration.get("profile_revision")
        and candidate["model"].get("mm_per_css") == css_scale]
    if not matches or any((match["model_id"], match["model"]) != (
        matches[0]["model_id"], matches[0]["model"]) for match in matches):
        return None
    source = next((match for match in matches if match.get("mode") == "explicit"), matches[0])
    return {**deepcopy(source), "profile_revision": calibration["profile_revision"],
            "calibration_revision": calibration["revision"]}


def remember_calibration(device_id: str, calibration: dict[str, Any]) -> None:
    if calibration.get("method") != "tablet-model approximate":
        return
    snapshot = pinned_assignment(device_id, calibration)
    if not snapshot:
        raise ValueError("No unambiguous historical model matches this profile and CSS scale. Confirm the model or record a measured manual calibration.")
    history = persist.load_meta("tablet_model_calibrations") or {}
    history.setdefault(device_id, {})[str(calibration["revision"])] = snapshot
    persist.save_meta("tablet_model_calibrations", history)


def match(telemetry: dict[str, Any]) -> list[str]:
    try:
        size = sorted((int(telemetry["screen_width"]), int(telemetry["screen_height"])))
        dpr = float(telemetry["screen_dpr"])
        platform = telemetry["platform_family"]
    except (KeyError, TypeError, ValueError):
        return []
    return [key for key, model in BUILTINS.items()
            if size == sorted((model["screen_width"], model["screen_height"]))
            and abs(dpr - model["dpr"]) < 0.02 and platform == model["platform"]]


def assign(device_id: str, mode: str, model_id: str | None = None) -> dict[str, Any]:
    all_assignments = assignments()
    history = persist.load_meta("tablet_model_calibrations") or {}
    revisions = history.setdefault(device_id, {})
    current = all_assignments.get(device_id, {})
    if current.get("model"):
        revisions[str(current["calibration_revision"])] = deepcopy(current)
    result: dict[str, Any]
    if mode == "manual" or (mode == "auto" and model_id is None):
        result = {"mode": mode, "model_id": None}
    else:
        if model_id not in BUILTINS:
            raise ValueError("Unknown tablet model")
        model = BUILTINS[model_id]
        if current.get("model_id") == model_id and current.get("model") == model:
            result = {**current, "mode": mode}
        else:
            profile = displays.latest_profile(device_id)
            if (profile is None or profile["active_width_mm"] != model["active_width_mm"]
                or profile["active_height_mm"] != model["active_height_mm"]
                or profile["bezels"] != model["bezels"]):
                profile = displays.save_profile(device_id, active_width_mm=model["active_width_mm"],
                    active_height_mm=model["active_height_mm"], bezels=model["bezels"],
                    panel_pixels={"width": model["screen_width"] * model["dpr"], "height": model["screen_height"] * model["dpr"]},
                    label=model["label"], provenance="tablet-model")
            cal = displays.save_calibration(device_id, profile_revision=profile["revision"],
                viewport_width=model["screen_width"], viewport_height=model["screen_height"],
                dpr=model["dpr"], orientation=model["portrait_angle"], mode="fullscreen", quarter_turn=0,
                panel_offset_mm=(0, 0), mm_per_css=(model["mm_per_css"][0], model["mm_per_css"][1]),
                anchor_edge="top-left", uncertainty_mm=model["uncertainty_mm"], method="tablet-model approximate")
            result = {"mode": mode, "model_id": model_id, "model": deepcopy(model),
                "profile_revision": profile["revision"], "calibration_revision": cal["revision"]}
        revisions[str(result["calibration_revision"])] = deepcopy(result)
    all_assignments[device_id] = result
    persist.save_meta("tablet_model_calibrations", history)
    persist.save_meta("tablet_model_assignments", all_assignments)
    return result


def copy_assignment(source_id: str, target_id: str, profile_offset: int, calibration_offset: int) -> None:
    """Carry model snapshots alongside copied measurement revisions during rebind."""
    all_assignments = assignments()
    source = all_assignments.get(source_id, {"mode": "manual", "model_id": None})
    history = persist.load_meta("tablet_model_calibrations") or {}
    source_revisions = dict(history.get(source_id, {}))
    if source.get("model"):
        source_revisions[str(source["calibration_revision"])] = source
    target_revisions = history.setdefault(target_id, {})
    for snapshot in source_revisions.values():
        copied = deepcopy(snapshot)
        copied["profile_revision"] += profile_offset
        copied["calibration_revision"] += calibration_offset
        target_revisions[str(copied["calibration_revision"])] = copied
    assignment = deepcopy(source)
    if assignment.get("model"):
        assignment["profile_revision"] += profile_offset
        assignment["calibration_revision"] += calibration_offset
    all_assignments[target_id] = assignment
    persist.save_meta("tablet_model_calibrations", history)
    persist.save_meta("tablet_model_assignments", all_assignments)


def pinned_assignment(device_id: str, calibration: dict[str, Any] | None) -> dict[str, Any]:
    if calibration is None or calibration.get("method") != "tablet-model approximate":
        return {}
    history = persist.load_meta("tablet_model_calibrations") or {}
    assignment = history.get(device_id, {}).get(str(calibration.get("revision")))
    if assignment is None:
        assignment = snapshot_for_calibration(calibration,
            [*history.get(device_id, {}).values(), assignments().get(device_id, {})]) or {}
    if (assignment.get("profile_revision") != calibration.get("profile_revision")
            or assignment.get("calibration_revision") != calibration.get("revision")):
        return {}
    return deepcopy(assignment)


def effective(device_id: str, calibration: dict[str, Any] | None, viewport: dict[str, Any]) -> dict[str, Any] | None:
    if calibration is None:
        return None
    assignment = pinned_assignment(device_id, calibration)
    model = assignment.get("model")
    if not isinstance(model, dict):
        return calibration
    try:
        width, height, dpr = float(viewport["width"]), float(viewport["height"]), float(viewport["dpr"])
        orientation, mode = int(viewport["orientation"]) % 360, str(viewport["mode"])
        if (not all(math.isfinite(v) for v in (width, height, dpr)) or width <= 0 or height <= 0
            or abs(dpr - model["dpr"]) >= 0.02 or orientation not in (0, 90, 180, 270)
            or mode not in ("tab", "fullscreen", "standalone")):
            return calibration
        sw, sh = model["screen_width"], model["screen_height"]
        quarter = ((model["portrait_angle"] - orientation) // 90) % 4
        if quarter % 2:
            sw, sh = sh, sw
        if width > sw + 1 or height > sh + 1:
            return calibration
        dx = 0 if mode == "fullscreen" else max(0, sw - width) / 2
        dy = 0 if mode == "fullscreen" else max(0, sh - height) / 2
        sx, sy = model["mm_per_css"]
        offsets = [(dx*sx, dy*sy), (dy*sy, dx*sx), (dx*sx, dy*sy), (dy*sy, dx*sx)]
        return {**calibration, "viewport_width": width, "viewport_height": height, "dpr": dpr,
                "orientation": orientation, "mode": mode, "quarter_turn": quarter,
                "panel_offset_mm": list(offsets[quarter]), "mm_per_css": [sx, sy]}
    except (KeyError, TypeError, ValueError):
        return calibration
