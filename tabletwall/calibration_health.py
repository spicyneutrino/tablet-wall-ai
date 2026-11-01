"""Pure calibration provenance, pinned-health, and ruler-scale rules.

Every input is supplied by the caller: the slot's pinned profile and
calibration revisions, the model assignment snapshot, and the live viewport.
This module never reads SQLite, module globals, or the latest profile for a
device, and it never substitutes a newer record for a pinned one. The returned
mapping is JSON-ready and echoes the supplied measured values unchanged.

Model-derived scale remains approximate even after the model is explicitly
confirmed. A signature match is a suggestion until a pinned assignment says
otherwise. A tab or standalone usable viewport is never reported as a full
panel.
"""

from __future__ import annotations

import copy
import math
import re
from collections.abc import Mapping
from typing import Any

ORIENTATIONS = (0, 90, 180, 270)
LAUNCH_MODES = ("tab", "fullscreen", "standalone")
MANUAL_TOKENS = frozenset({"manual", "measured", "ruler", "tape"})
DEFAULT_MODEL_UNCERTAINTY_MM = 3.0
COMPARISON_TOLERANCE_FLOOR_MM = 0.5
SHORT_SPAN_FACTOR = 2.0
FULL_SPAN_FACTOR = 1.05
MAX_SPAN_COUNT = 64
MAX_RULER_SPAN_MM = 100_000.0
MAX_USABLE_PX = 1_000_000.0

_SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}
_WARNING_ORDER = {
    "profile_or_calibration_missing": 0,
    "pinned_pair_mismatch": 1,
    "unknown_provenance": 2,
    "viewport_unavailable": 3,
    "zoom_changed": 4,
    "viewport_mismatch": 5,
    "model_confirmation_required": 6,
    "model_snapshot_unavailable": 7,
    "model_snapshot_revision_mismatch": 8,
    "model_scale_disagreement": 9,
    "scale_discrepancy": 10,
    "uncertainty_missing": 11,
    "uncertainty_disagreement": 12,
    "tab_viewport_not_full_panel": 13,
    "full_panel_comparison_unavailable": 14,
    "visual_scale_unavailable": 15,
}


class CalibrationHealthError(ValueError):
    """A supplied profile, calibration, assignment, model or viewport is invalid."""


def _number(
    value: Any,
    field: str,
    *,
    positive: bool = False,
    nonnegative: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalibrationHealthError(f"{field} must be a finite number")
    try:
        number = float(value)
    except OverflowError as error:
        raise CalibrationHealthError(f"{field} must be finite") from error
    if not math.isfinite(number):
        raise CalibrationHealthError(f"{field} must be finite")
    if positive and number <= 0:
        raise CalibrationHealthError(f"{field} must be positive")
    if nonnegative and number < 0:
        raise CalibrationHealthError(f"{field} must not be negative")
    return number


def _revision(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CalibrationHealthError(f"{field} must be a positive integer")
    return value


def _optional_revision(value: Any, field: str) -> int | None:
    return None if value is None else _revision(value, field)


def _pair(value: Any, field: str, *, positive: bool) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise CalibrationHealthError(f"{field} must be two numbers")
    return [
        _number(value[0], f"{field}[0]", positive=positive),
        _number(value[1], f"{field}[1]", positive=positive),
    ]


def _text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CalibrationHealthError(f"{field} must be text")
    return value


def _mode(value: Any, field: str) -> str:
    if value not in LAUNCH_MODES:
        raise CalibrationHealthError(
            f"{field} must be one of {', '.join(LAUNCH_MODES)}"
        )
    return str(value)


def _orientation(value: Any, field: str) -> int:
    if isinstance(value, bool) or value not in ORIENTATIONS:
        raise CalibrationHealthError(f"{field} must be 0, 90, 180 or 270")
    return int(value)


def _profile_values(profile: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if profile is None:
        return None
    if not isinstance(profile, Mapping):
        raise CalibrationHealthError("profile must be an object or null")
    revision = _revision(profile.get("revision"), "profile.revision")
    width = _number(profile.get("active_width_mm"), "profile.active_width_mm", positive=True)
    height = _number(profile.get("active_height_mm"), "profile.active_height_mm", positive=True)
    bezels = profile.get("bezels")
    if bezels is not None:
        if not isinstance(bezels, Mapping):
            raise CalibrationHealthError("profile.bezels must be an object")
        for edge in ("left", "right", "top", "bottom"):
            _number(bezels.get(edge), f"profile.bezels.{edge}", nonnegative=True)
    provenance = _text(profile.get("provenance"), "profile.provenance")
    return {
        "revision": revision,
        "active_width_mm": width,
        "active_height_mm": height,
        "provenance": provenance,
        "raw": copy.deepcopy(dict(profile)),
    }


def _calibration_values(calibration: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if calibration is None:
        return None
    if not isinstance(calibration, Mapping):
        raise CalibrationHealthError("calibration must be an object or null")
    revision = _revision(calibration.get("revision"), "calibration.revision")
    profile_revision = _revision(
        calibration.get("profile_revision"), "calibration.profile_revision"
    )
    width = _number(
        calibration.get("viewport_width"), "calibration.viewport_width", positive=True
    )
    height = _number(
        calibration.get("viewport_height"), "calibration.viewport_height", positive=True
    )
    dpr = _number(calibration.get("dpr"), "calibration.dpr", positive=True)
    orientation = _orientation(
        calibration.get("orientation"), "calibration.orientation"
    )
    mode = _mode(calibration.get("mode"), "calibration.mode")
    quarter_turn = calibration.get("quarter_turn")
    if isinstance(quarter_turn, bool) or quarter_turn not in (0, 1, 2, 3):
        raise CalibrationHealthError("calibration.quarter_turn must be 0, 1, 2 or 3")
    offset = _pair(
        calibration.get("panel_offset_mm"), "calibration.panel_offset_mm", positive=False
    )
    scale = _pair(
        calibration.get("mm_per_css"), "calibration.mm_per_css", positive=True
    )
    uncertainty_value = calibration.get("uncertainty_mm")
    uncertainty = (
        None
        if uncertainty_value is None
        else _number(uncertainty_value, "calibration.uncertainty_mm", nonnegative=True)
    )
    method = _text(calibration.get("method"), "calibration.method")
    anchor_edge = _text(calibration.get("anchor_edge"), "calibration.anchor_edge")
    if anchor_edge is not None and anchor_edge not in (
        "top-left", "top-right", "bottom-left", "bottom-right"
    ):
        raise CalibrationHealthError("calibration.anchor_edge is not a supported edge")
    return {
        "revision": revision,
        "profile_revision": profile_revision,
        "viewport_width": width,
        "viewport_height": height,
        "dpr": dpr,
        "orientation": orientation,
        "mode": mode,
        "quarter_turn": int(quarter_turn),
        "panel_offset_mm": offset,
        "mm_per_css": scale,
        "uncertainty_mm": uncertainty,
        "method": method,
        "anchor_edge": anchor_edge,
        "raw": copy.deepcopy(dict(calibration)),
    }


def _assignment_values(assignment: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if assignment is None:
        return None
    if not isinstance(assignment, Mapping):
        raise CalibrationHealthError("assignment must be an object or null")
    mode = _text(assignment.get("mode"), "assignment.mode")
    model_id = _text(assignment.get("model_id"), "assignment.model_id")
    for key in ("confirmed", "model_confirmed"):
        if key in assignment and not isinstance(assignment[key], bool):
            raise CalibrationHealthError(f"assignment.{key} must be a boolean")
    return {
        "mode": mode,
        "model_id": model_id,
        "profile_revision": _optional_revision(
            assignment.get("profile_revision"), "assignment.profile_revision"
        ),
        "calibration_revision": _optional_revision(
            assignment.get("calibration_revision"), "assignment.calibration_revision"
        ),
        "confirmed": assignment.get("confirmed") is True,
        "model_confirmed": assignment.get("model_confirmed") is True,
        "model": assignment.get("model"),
        "raw": copy.deepcopy(dict(assignment)),
    }


def _model_values(model: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if model is None:
        return None
    if not isinstance(model, Mapping):
        raise CalibrationHealthError("model must be an object or null")
    screen_width = _number(model.get("screen_width"), "model.screen_width", positive=True)
    screen_height = _number(model.get("screen_height"), "model.screen_height", positive=True)
    dpr = _number(model.get("dpr"), "model.dpr", positive=True)
    portrait_angle = _orientation(model.get("portrait_angle"), "model.portrait_angle")
    scale = _pair(model.get("mm_per_css"), "model.mm_per_css", positive=True)
    uncertainty_value = model.get("uncertainty_mm")
    uncertainty = (
        None
        if uncertainty_value is None
        else _number(uncertainty_value, "model.uncertainty_mm", nonnegative=True)
    )
    if uncertainty is None:
        uncertainty = DEFAULT_MODEL_UNCERTAINTY_MM
    label = _text(model.get("label"), "model.label")
    model_id = _text(model.get("model_id"), "model.model_id")
    return {
        "screen_width": screen_width,
        "screen_height": screen_height,
        "dpr": dpr,
        "portrait_angle": portrait_angle,
        "mm_per_css": scale,
        "uncertainty_mm": uncertainty,
        "label": label,
        "model_id": model_id,
        "fullspan_mm": [screen_width * scale[0], screen_height * scale[1]],
    }


def _viewport_values(viewport: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if viewport is None:
        return None
    if not isinstance(viewport, Mapping):
        raise CalibrationHealthError("viewport must be an object or null")
    width = _number(viewport.get("width"), "viewport.width", positive=True)
    height = _number(viewport.get("height"), "viewport.height", positive=True)
    dpr = _number(viewport.get("dpr"), "viewport.dpr", positive=True)
    orientation = _orientation(viewport.get("orientation"), "viewport.orientation")
    mode = _mode(viewport.get("mode"), "viewport.mode")
    scale_supplied = viewport.get("visual_scale") is not None
    visual_scale = (
        _number(viewport.get("visual_scale"), "viewport.visual_scale", positive=True)
        if scale_supplied
        else 1.0
    )
    return {
        "width": width,
        "height": height,
        "dpr": dpr,
        "orientation": orientation,
        "mode": mode,
        "visual_scale": visual_scale,
        "visual_scale_supplied": scale_supplied,
    }


def _tokens(*values: str | None) -> frozenset[str]:
    text = " ".join(value for value in values if value).lower()
    return frozenset(token for token in re.split(r"[^a-z]+", text) if token)


def _assignment_is_confirmed(assignment: dict[str, Any] | None) -> bool:
    if assignment is None:
        return False
    if assignment["confirmed"] or assignment["model_confirmed"]:
        return True
    return assignment["mode"] in ("confirmed", "explicit")


def _warning(
    code: str, severity: str, message: str, action: str
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "action": action,
    }


def _pick_actionable(warnings: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not warnings:
        return None
    return min(
        warnings,
        key=lambda item: (
            _SEVERITY_RANK.get(str(item["severity"]), 9),
            _WARNING_ORDER.get(str(item["code"]), 99),
        ),
    )


def _format_mm(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.2f} mm".rstrip("0").rstrip(".")


def assess_calibration(
    *,
    profile: Mapping[str, Any] | None,
    calibration: Mapping[str, Any] | None,
    assignment: Mapping[str, Any] | None = None,
    model: Mapping[str, Any] | None = None,
    viewport: Mapping[str, Any] | None = None,
    device_id: str | None = None,
) -> dict[str, Any]:
    """Describe one slot's pinned calibration without reading live state.

    ``profile`` and ``calibration`` must be the exact records the slot pins.
    ``model`` is the pinned model snapshot when the caller has one; otherwise a
    matching assignment's embedded snapshot is used. ``viewport`` is the live
    report. Missing profile/calibration returns a JSON ``needs_calibration``
    result instead of raising; malformed supplied values raise
    :class:`CalibrationHealthError`.
    """
    if device_id is not None and not isinstance(device_id, str):
        raise CalibrationHealthError("device_id must be text or null")
    pinned_profile = _profile_values(profile)
    pinned_calibration = _calibration_values(calibration)
    assigned = _assignment_values(assignment)
    live = _viewport_values(viewport)

    pinned_profile_revision = (
        pinned_profile["revision"] if pinned_profile is not None else None
    )
    pinned_calibration_revision = (
        pinned_calibration["revision"] if pinned_calibration is not None else None
    )
    pinned_pair_agrees: bool | None = None
    if pinned_profile is not None and pinned_calibration is not None:
        pinned_pair_agrees = (
            pinned_calibration["profile_revision"] == pinned_profile_revision
        )

    assignment_pinned = bool(
        assigned is not None
        and assigned["profile_revision"] == pinned_profile_revision
        and assigned["calibration_revision"] == pinned_calibration_revision
    )

    explicit_model = _model_values(model)
    model_source: str | None = None
    model_values: dict[str, Any] | None = None
    if explicit_model is not None:
        model_values = explicit_model
        model_source = "explicit_pinned_snapshot"
    elif assigned is not None and assigned["model"] is not None and assignment_pinned:
        model_values = _model_values(assigned["model"])
        model_source = "pinned_assignment_snapshot"
    if model_values is not None and model_values["model_id"] is None:
        model_values["model_id"] = assigned["model_id"] if assigned else None

    tokens = _tokens(
        pinned_calibration["method"] if pinned_calibration else None,
    )
    manual = bool(tokens & MANUAL_TOKENS)
    model_text = "model" in tokens
    if manual:
        kind = "manual"
    elif model_text or (pinned_calibration is None and model_values is not None):
        kind = "model"
    else:
        kind = "unknown"

    model_confirmed = bool(
        kind == "model" and assignment_pinned and _assignment_is_confirmed(assigned)
    )
    calibration_uncertainty = (
        pinned_calibration["uncertainty_mm"] if pinned_calibration else None
    )
    model_uncertainty = model_values["uncertainty_mm"] if model_values else None
    if kind == "model":
        uncertainty = (
            calibration_uncertainty
            if calibration_uncertainty is not None
            else model_uncertainty
        )
        uncertainty_source = (
            "pinned_calibration"
            if calibration_uncertainty is not None
            else ("model_snapshot" if model_uncertainty is not None else None)
        )
    elif kind == "manual":
        uncertainty = calibration_uncertainty
        uncertainty_source = (
            "pinned_calibration" if calibration_uncertainty is not None else None
        )
    else:
        uncertainty = calibration_uncertainty
        uncertainty_source = (
            "pinned_calibration" if calibration_uncertainty is not None else None
        )

    warnings: list[dict[str, Any]] = []
    assumptions = [
        "The caller supplied the pinned profile and calibration revisions; this helper performs no database or global reads and does not substitute the latest record.",
        "Every supplied measured value is echoed unchanged; no averaging or rewriting occurred.",
        "No real-world accuracy is claimed.",
    ]

    if pinned_profile is None or pinned_calibration is None:
        warnings.append(_warning(
            "profile_or_calibration_missing",
            "error",
            "The slot has no pinned profile and calibration pair, so no scale can be mapped.",
            "Measure this tablet or pin an existing profile/calibration before mapping.",
        ))
    if (
        pinned_pair_agrees is False
        and pinned_profile is not None
        and pinned_calibration is not None
    ):
        warnings.append(_warning(
            "pinned_pair_mismatch",
            "error",
            "The pinned calibration names profile revision "
            f"{pinned_calibration['profile_revision']} but the pinned profile is "
            f"revision {pinned_profile['revision']}.",
            "Repair the slot's pinned revisions; do not substitute a newer pair implicitly.",
        ))
    if kind == "unknown":
        warnings.append(_warning(
            "unknown_provenance",
            "error",
            "The calibration method is not recorded as a manual/ruler measurement or a model estimate.",
            "Record whether this calibration was measured with a ruler or derived from a model.",
        ))

    if (
        assigned is not None
        and not assignment_pinned
        and (
            assigned["profile_revision"] is not None
            or assigned["calibration_revision"] is not None
        )
    ):
        warnings.append(_warning(
            "model_snapshot_revision_mismatch",
            "warning",
            "The passed assignment names profile/calibration revisions "
            f"{assigned['profile_revision']}/{assigned['calibration_revision']}; "
            f"the slot pins {pinned_profile_revision}/{pinned_calibration_revision}. "
            "The assignment is not used for this pinned slot.",
            "Confirm the pinned snapshot or re-measure; a newer assignment does not change this slot's health.",
        ))
    if kind == "model" and model_values is None:
        warnings.append(_warning(
            "model_snapshot_unavailable",
            "warning",
            "The pinned calibration is model-derived, but no matching model snapshot is available for viewport adaptation or model labelling.",
            "Confirm the pinned snapshot or take a ruler measurement; do not apply a newer assignment's scale.",
        ))
    if kind == "model" and not model_confirmed:
        model_label = (
            model_values["label"]
            if model_values is not None and model_values["label"]
            else "this tablet model"
        )
        if assignment_pinned:
            message = (
                f"This existing assignment looks like {model_label}, but it is not "
                "explicitly confirmed. The scale is an approximation, not proof."
            )
            action = (
                f"Confirm {model_label} explicitly, or take a ruler measurement. "
                "Confirmation still leaves the scale approximate."
            )
        else:
            message = (
                f"Looks like {model_label}. A signature is a suggestion, not proof, "
                "so no confirmed physical scale is assigned."
            )
            action = f"Confirm {model_label} explicitly, or take a ruler measurement."
        warnings.append(_warning(
            "model_confirmation_required", "warning", message, action
        ))
    if kind == "manual" and uncertainty is None:
        warnings.append(_warning(
            "uncertainty_missing",
            "warning",
            "The manual calibration does not supply a measurement uncertainty.",
            "Enter the ruler span error so the plan can show a real uncertainty instead of implying precision.",
        ))
    if (
        calibration_uncertainty is not None
        and model_uncertainty is not None
        and abs(calibration_uncertainty - model_uncertainty) > 1e-9
    ):
        warnings.append(_warning(
            "uncertainty_disagreement",
            "warning",
            "The pinned calibration uncertainty "
            f"({_format_mm(calibration_uncertainty)}) differs from the model "
            f"uncertainty ({_format_mm(model_uncertainty)}); both are preserved.",
            "Choose which uncertainty describes this plan; the helper does not average or overwrite either value.",
        ))

    if not live:
        viewport_report = _viewport_report(
            pinned_calibration=pinned_calibration,
            live=None,
            model_values=model_values if kind == "model" else None,
        )
        warnings.append(_warning(
            "viewport_unavailable",
            "error",
            "No live viewport was supplied, so the pinned scale cannot be checked against the tablet's current mapping.",
            "Wait for a viewport report or reconnect the tablet before relying on this plan.",
        ))
    else:
        viewport_report = _viewport_report(
            pinned_calibration=pinned_calibration,
            live=live,
            model_values=model_values if kind == "model" else None,
        )
        for fence in viewport_report["fences"]:
            warnings.append(_warning(
                str(fence["code"]), str(fence["severity"]),
                str(fence["message"]), str(fence["action"]),
            ))
        if not live["visual_scale_supplied"]:
            warnings.append(_warning(
                "visual_scale_unavailable",
                "info",
                "visual_scale was not supplied; 1.0 was assumed for the zoom check.",
                "Report the browser visual scale so zoom changes can be fenced explicitly.",
            ))
            assumptions.append(
                "visual_scale was not supplied; 1.0 was assumed for the zoom check."
            )

    zoom_changed = bool(
        live is not None and abs(live["visual_scale"] - 1.0) > 1e-9
    )
    viewport_mismatch = bool(
        live is None or any(
            fence["code"] in ("viewport_mismatch", "dpr_mismatch", "viewport_too_large")
            for fence in viewport_report["fences"]
        )
    )

    scale_values: dict[str, Any] | None = None
    scale_reason: str | None = None
    if pinned_calibration is None:
        scale_reason = "missing pinned calibration"
    else:
        if kind == "model" and model_values is not None:
            effective_scale = list(model_values["mm_per_css"])
            scale_source = "model_snapshot"
        else:
            effective_scale = list(pinned_calibration["mm_per_css"])
            scale_source = "pinned_calibration"
        usable = True
        if pinned_profile is None or pinned_pair_agrees is False:
            usable = False
            scale_reason = "missing or mismatched pinned profile/calibration pair"
        elif kind == "unknown":
            usable = False
            scale_reason = "provenance is unknown; confirm how this calibration was measured"
        elif live is None:
            usable = False
            scale_reason = "no live viewport to validate the mapping"
        elif zoom_changed:
            usable = False
            scale_reason = "browser zoom is not 100%"
        elif viewport_mismatch:
            usable = False
            scale_reason = "live viewport does not match the pinned calibration"
        scale_values = {
            "mm_per_css": effective_scale,
            "source": scale_source,
            "usable": usable,
            "approximate": kind in ("model", "unknown"),
            "confirmed": bool(kind == "manual" or model_confirmed),
            "uncertainty_mm": uncertainty,
            "quarter_turn": (
                viewport_report["orientation"]["quarter_turn"]
                if live is not None and viewport_report["orientation"]["quarter_turn"] is not None
                else pinned_calibration["quarter_turn"]
            ),
            "calibration_mm_per_css": list(pinned_calibration["mm_per_css"]),
            "model_mm_per_css": (
                list(model_values["mm_per_css"]) if model_values is not None else None
            ),
            "note": (
                "Model-derived scale remains approximate even after explicit confirmation."
                if kind == "model"
                else "Manual scale is measured; its supplied uncertainty is preserved, not averaged."
            ),
        }
        if not usable:
            scale_values["unusable_reason"] = scale_reason
        if (
            model_values is not None
            and list(pinned_calibration["mm_per_css"]) != list(model_values["mm_per_css"])
        ):
            warnings.append(_warning(
                "model_scale_disagreement",
                "warning",
                "The pinned calibration mm_per_css "
                f"{pinned_calibration['mm_per_css']} differs from the model snapshot "
                f"{model_values['mm_per_css']}; both values are preserved.",
                "Choose the scale that describes this installation; nothing is averaged or overwritten.",
            ))

    predicted = _predicted_full_panel(
        pinned_profile=pinned_profile,
        pinned_calibration=pinned_calibration,
        model_values=model_values,
        viewport_report=viewport_report,
        kind=kind,
        scale_usable=bool(scale_values and scale_values["usable"]),
    )
    comparison = _comparison(
        predicted=predicted,
        pinned_profile=pinned_profile,
        uncertainty=uncertainty,
        uncertainty_source=uncertainty_source,
        kind=kind,
        scale_usable=bool(scale_values and scale_values["usable"]),
    )
    if comparison["valid"] and comparison["discrepancy"]:
        warnings.append(_warning(
            "scale_discrepancy",
            "warning",
            str(comparison["message"]),
            str(comparison["action"]),
        ))
    if (
        not comparison["valid"]
        and kind == "manual"
        and predicted["reason_code"] == "tab_viewport"
    ):
        warnings.append(_warning(
            "full_panel_comparison_unavailable",
            "warning",
            "The manual calibration used a tab or standalone viewport. The usable viewport is not the full panel, so its scale cannot be extrapolated to the complete panel.",
            "Use a fullscreen measurement for a full-panel comparison, or measure the full lit span explicitly.",
        ))

    status, status_reason = _status(
        pinned_profile=pinned_profile,
        pinned_calibration=pinned_calibration,
        pinned_pair_agrees=pinned_pair_agrees,
        kind=kind,
        live=live,
        zoom_changed=zoom_changed,
        viewport_mismatch=viewport_mismatch,
    )

    if kind == "manual":
        approximate = False
        confirmed = True
    elif kind == "model":
        approximate = True
        confirmed = model_confirmed
    else:
        approximate = True
        confirmed = False

    uncertainty_text = (
        f" ±{uncertainty:g} mm" if uncertainty is not None else " (uncertainty not supplied)"
    )
    full_panel_known = bool(predicted["valid"])
    scale_discrepancy = bool(
        comparison["valid"] and comparison["discrepancy"]
    )
    if status == "ready":
        if kind == "manual":
            status_label = f"Ready — measured{uncertainty_text}"
            if not full_panel_known:
                status_label = f"Ready — measured{uncertainty_text} (usable viewport, not a confirmed full panel)"
            if scale_discrepancy:
                status_label = f"Ready — measured{uncertainty_text} — scale discrepancy"
        elif model_confirmed:
            status_label = f"Ready — approximate model (confirmed{uncertainty_text})"
        else:
            status_label = f"Ready — unconfirmed model estimate (approximate{uncertainty_text})"
    elif status == "needs_calibration":
        if (
            pinned_profile is None
            or pinned_calibration is None
            or pinned_pair_agrees is False
            or kind == "unknown"
        ):
            status_label = "Needs measurement"
        else:
            status_label = "Needs model confirmation"
    elif status == "zoom_changed":
        status_label = "Browser zoom changed"
    else:
        status_label = "Viewport mismatch"

    model_identity = model_values["label"] if model_values is not None else None
    if model_identity is None and assignment_pinned and assigned is not None:
        model_identity = assigned["model_id"]
    provenance = {
        "kind": kind,
        "manual": kind == "manual",
        "model": kind == "model",
        "unknown": kind == "unknown",
        "label": (
            "Measured"
            if kind == "manual"
            else ("Model estimate" if kind == "model" else "Unknown")
        ),
        "description": status_label,
        "method": pinned_calibration["method"] if pinned_calibration else None,
        "profile_provenance": pinned_profile["provenance"] if pinned_profile else None,
        "approximate": approximate,
        "confirmed": confirmed,
        "confirmation_required": bool(kind == "model" and not confirmed),
        "accuracy_claimed": False,
        "model_id": (
            model_values["model_id"]
            if model_values is not None and model_values["model_id"] is not None
            else (assigned["model_id"] if assignment_pinned and assigned else None)
        ),
        "model_label": model_identity,
        "manual_value": (
            {
                "mm_per_css": list(pinned_calibration["mm_per_css"]),
                "uncertainty_mm": calibration_uncertainty,
                "method": pinned_calibration["method"],
            }
            if kind == "manual" and pinned_calibration is not None
            else None
        ),
        "model_snapshot": {
            "available": model_values is not None,
            "source": model_source,
            "pinned_assignment": assignment_pinned,
            "confirmed": model_confirmed,
            "mode": assigned["mode"] if assigned is not None else None,
        },
        "model_signature": (
            {
                "model_id": model_values["model_id"],
                "label": model_values["label"],
                "screen_width": model_values["screen_width"],
                "screen_height": model_values["screen_height"],
                "mm_per_css": list(model_values["mm_per_css"]),
                "uncertainty_mm": model_values["uncertainty_mm"],
                "fullspan_mm": list(model_values["fullspan_mm"]),
                "source": model_source,
            }
            if model_values is not None
            else None
        ),
    }

    if kind == "model":
        assumptions.append(
            "Model-derived scale remains approximate even after the model is explicitly confirmed."
        )
    if live is not None and live["mode"] != "fullscreen":
        assumptions.append(
            "Only fullscreen is treated as a full-panel launch mode; a tab or standalone viewport may include browser or PWA insets."
        )
    quarter_turn = viewport_report["orientation"]["quarter_turn"]
    if quarter_turn:
        assumptions.append(
            "The comparison uses the pinned/effective quarter turn "
            f"{quarter_turn} to orient the predicted panel extent."
        )
    if comparison["valid"] and comparison["orientation_swapped"]:
        assumptions.append(
            "Predicted dimensions were swapped by the pinned quarter turn before comparison."
        )

    return {
        "schema": 1,
        "device_id": device_id,
        "status": status,
        "status_reason": status_reason,
        "status_label": status_label,
        "ok": bool(
            status == "ready"
            and kind == "manual"
            and predicted["valid"]
            and not approximate
            and not scale_discrepancy
        ),
        "provenance": provenance,
        "approximate": approximate,
        "confirmed": confirmed,
        "accuracy_claimed": False,
        "uncertainty_mm": uncertainty,
        "uncertainty": {
            "mm": uncertainty,
            "source": uncertainty_source,
            "calibration_mm": calibration_uncertainty,
            "model_mm": model_uncertainty,
            "agreement": (
                None
                if calibration_uncertainty is None or model_uncertainty is None
                else abs(calibration_uncertainty - model_uncertainty) <= 1e-9
            ),
            "note": (
                "The supplied uncertainty is preserved. It is not an accuracy claim."
                if uncertainty is not None
                else "No uncertainty was supplied; no precision is implied."
            ),
        },
        "revisions": {
            "profile_revision": pinned_profile_revision,
            "calibration_revision": pinned_calibration_revision,
            "calibration_pins_profile_revision": (
                pinned_calibration["profile_revision"]
                if pinned_calibration is not None
                else None
            ),
            "pinned_pair_agrees": pinned_pair_agrees,
            "assignment": {
                "present": assigned is not None,
                "profile_revision": (
                    assigned["profile_revision"] if assigned is not None else None
                ),
                "calibration_revision": (
                    assigned["calibration_revision"] if assigned is not None else None
                ),
                "pinned_match": assignment_pinned,
                "model_id": assigned["model_id"] if assigned is not None else None,
                "mode": assigned["mode"] if assigned is not None else None,
                "confirmed": model_confirmed,
            },
            "latest_substitution": False,
            "source": "pinned slot revisions",
        },
        "scale": scale_values,
        "scale_unavailable_reason": scale_reason if scale_values is None else None,
        "predicted_full_panel": predicted,
        "comparison": comparison,
        "viewport": viewport_report,
        "warnings": warnings,
        "actionable_warning": _pick_actionable(warnings),
        "measurements": {
            "profile": (
                copy.deepcopy(pinned_profile["raw"])
                if pinned_profile is not None
                else None
            ),
            "calibration": (
                copy.deepcopy(pinned_calibration["raw"])
                if pinned_calibration is not None
                else None
            ),
            "lit_dimensions_mm": (
                [
                    pinned_profile["active_width_mm"],
                    pinned_profile["active_height_mm"],
                ]
                if pinned_profile is not None
                else None
            ),
            "calibration_mm_per_css": (
                list(pinned_calibration["mm_per_css"])
                if pinned_calibration is not None
                else None
            ),
            "model_mm_per_css": (
                list(model_values["mm_per_css"])
                if model_values is not None
                else None
            ),
            "uncertainty_mm": calibration_uncertainty,
            "model_uncertainty_mm": model_uncertainty,
        },
        "assumptions": assumptions,
        "notes": [
            "A signature match is a suggestion, not proof.",
            "A model plan is never presented as a plain verified ok.",
        ],
    }


def _viewport_report(
    *,
    pinned_calibration: dict[str, Any] | None,
    live: dict[str, Any] | None,
    model_values: dict[str, Any] | None,
) -> dict[str, Any]:
    if pinned_calibration is None:
        return {
            "supplied": live is not None,
            "live": live,
            "pinned": None,
            "mode": {"pinned": None, "live": None, "matches": None, "adapted": False},
            "orientation": {
                "pinned": None,
                "live": None,
                "matches": None,
                "quarter_turn": None,
            },
            "dpr": {"pinned": None, "live": None, "matches": None},
            "size": {"pinned": None, "live": None, "matches": None},
            "zoom": {"visual_scale": None, "matches": None},
            "full_panel": None,
            "usable_extent_mm": None,
            "insets": {
                "assumed": True,
                "source": "no pinned calibration",
                "left_mm": None,
                "top_mm": None,
                "right_mm": None,
                "bottom_mm": None,
                "panel_offset_mm": None,
            },
            "fences": [],
        }

    pinned = {
        "width": pinned_calibration["viewport_width"],
        "height": pinned_calibration["viewport_height"],
        "dpr": pinned_calibration["dpr"],
        "orientation": pinned_calibration["orientation"],
        "mode": pinned_calibration["mode"],
        "quarter_turn": pinned_calibration["quarter_turn"],
        "panel_offset_mm": list(pinned_calibration["panel_offset_mm"]),
        "mm_per_css": list(pinned_calibration["mm_per_css"]),
    }
    if live is None:
        return {
            "supplied": False,
            "live": None,
            "pinned": pinned,
            "mode": {
                "pinned": pinned_calibration["mode"],
                "live": None,
                "matches": None,
                "adapted": False,
            },
            "orientation": {
                "pinned": pinned_calibration["orientation"],
                "live": None,
                "matches": None,
                "quarter_turn": pinned_calibration["quarter_turn"],
            },
            "dpr": {
                "pinned": pinned_calibration["dpr"],
                "live": None,
                "matches": None,
            },
            "size": {
                "pinned": [
                    pinned_calibration["viewport_width"],
                    pinned_calibration["viewport_height"],
                ],
                "live": None,
                "matches": None,
            },
            "zoom": {"visual_scale": None, "matches": None},
            "full_panel": None,
            "usable_extent_mm": [
                pinned_calibration["viewport_width"] * pinned_calibration["mm_per_css"][0],
                pinned_calibration["viewport_height"] * pinned_calibration["mm_per_css"][1],
            ],
            "insets": {
                "assumed": True,
                "source": "pinned calibration panel_offset_mm; live inset not supplied",
                "left_mm": pinned_calibration["panel_offset_mm"][0],
                "top_mm": pinned_calibration["panel_offset_mm"][1],
                "right_mm": None,
                "bottom_mm": None,
                "panel_offset_mm": list(pinned_calibration["panel_offset_mm"]),
            },
            "fences": [],
        }

    fences: list[dict[str, Any]] = []
    zoom_changed = abs(live["visual_scale"] - 1.0) > 1e-9
    if zoom_changed:
        fences.append({
            "code": "zoom_changed",
            "severity": "error",
            "message": (
                "The live browser visual scale is "
                f"{live['visual_scale']} instead of 1.0, so CSS pixels no longer match the pinned calibration."
            ),
            "action": "Reset browser zoom to 100% and wait for a fresh viewport report.",
        })

    if model_values is not None:
        portrait_angle = model_values["portrait_angle"]
        quarter = ((portrait_angle - live["orientation"]) // 90) % 4
        screen_width, screen_height = (
            model_values["screen_width"],
            model_values["screen_height"],
        )
        if quarter % 2:
            screen_width, screen_height = screen_height, screen_width
        dpr_matches = abs(live["dpr"] - model_values["dpr"]) < 0.02
        size_matches = (
            live["width"] <= screen_width + 1
            and live["height"] <= screen_height + 1
        )
        mode_matches = pinned_calibration["mode"] == live["mode"]
        if not dpr_matches:
            fences.append({
                "code": "dpr_mismatch",
                "severity": "error",
                "message": (
                    f"The live DPR {live['dpr']} does not match the pinned model DPR "
                    f"{model_values['dpr']}."
                ),
                "action": "Use the model's native device pixel ratio or re-measure this tablet.",
            })
        if not size_matches:
            fences.append({
                "code": "viewport_too_large",
                "severity": "error",
                "message": (
                    f"The live viewport {live['width']}x{live['height']} CSS px exceeds "
                    f"the model's {screen_width}x{screen_height} native panel; a usable "
                    "viewport cannot be treated as a larger full panel."
                ),
                "action": "Clear browser zoom/scale, use the native screen size, or take a fresh measurement.",
            })
        if live["mode"] == "fullscreen":
            full_panel = bool(
                size_matches
                and abs(live["width"] - screen_width) <= 1
                and abs(live["height"] - screen_height) <= 1
                and not zoom_changed
            )
        else:
            full_panel = False
        if live["mode"] == "fullscreen":
            insets = {
                "assumed": True,
                "source": "fullscreen launch mode; zero browser inset assumed",
                "left_mm": 0.0,
                "top_mm": 0.0,
                "right_mm": 0.0,
                "bottom_mm": 0.0,
                "panel_offset_mm": list(pinned_calibration["panel_offset_mm"]),
            }
        else:
            dx = max(0.0, screen_width - live["width"]) / 2
            dy = max(0.0, screen_height - live["height"]) / 2
            scale_x, scale_y = model_values["mm_per_css"]
            offset_x, offset_y = (
                (dy * scale_y, dx * scale_x)
                if quarter % 2
                else (dx * scale_x, dy * scale_y)
            )
            insets = {
                "assumed": True,
                "source": (
                    "model tab/standalone centering; the usable viewport is not the full panel"
                ),
                "left_mm": offset_x,
                "top_mm": offset_y,
                "right_mm": offset_x,
                "bottom_mm": offset_y,
                "panel_offset_mm": list(pinned_calibration["panel_offset_mm"]),
            }
        if not full_panel:
            fences.append({
                "code": (
                    "tab_viewport_not_full_panel"
                    if live["mode"] != "fullscreen"
                    else "viewport_not_full_panel"
                ),
                "severity": "info",
                "message": (
                    "This is not the full panel. The model's native fullspan is compared, "
                    "but the live viewport extent is not a full-panel extent."
                ),
                "action": "Use fullscreen at the native panel size for a full-panel view, or compare the model signature separately.",
            })
        return {
            "supplied": True,
            "live": live,
            "pinned": pinned,
            "mode": {
                "pinned": pinned_calibration["mode"],
                "live": live["mode"],
                "matches": mode_matches,
                "adapted": not mode_matches or quarter != pinned_calibration["quarter_turn"],
            },
            "orientation": {
                "pinned": pinned_calibration["orientation"],
                "live": live["orientation"],
                "matches": live["orientation"] == pinned_calibration["orientation"],
                "quarter_turn": quarter,
            },
            "dpr": {
                "pinned": model_values["dpr"],
                "live": live["dpr"],
                "matches": dpr_matches,
            },
            "size": {
                "pinned": [screen_width, screen_height],
                "live": [live["width"], live["height"]],
                "matches": size_matches,
            },
            "zoom": {
                "visual_scale": live["visual_scale"],
                "matches": not zoom_changed,
            },
            "full_panel": full_panel,
            "usable_extent_mm": [
                live["width"] * model_values["mm_per_css"][0],
                live["height"] * model_values["mm_per_css"][1],
            ],
            "insets": insets,
            "fences": fences,
        }

    dpr_matches = abs(live["dpr"] - pinned_calibration["dpr"]) < 0.02
    size_matches = (
        abs(live["width"] - pinned_calibration["viewport_width"]) <= 0.5
        and abs(live["height"] - pinned_calibration["viewport_height"]) <= 0.5
    )
    orientation_matches = live["orientation"] == pinned_calibration["orientation"]
    mode_matches = live["mode"] == pinned_calibration["mode"]
    if not size_matches:
        fences.append({
            "code": "viewport_mismatch",
            "severity": "error",
            "message": (
                f"The live viewport {live['width']}x{live['height']} CSS px does not match "
                f"the pinned calibration {pinned_calibration['viewport_width']}x{pinned_calibration['viewport_height']}."
            ),
            "action": "Refresh the tablet viewport and re-measure if the window size truly changed; do not reuse this scale silently.",
        })
    if not orientation_matches:
        fences.append({
            "code": "viewport_mismatch",
            "severity": "error",
            "message": (
                f"The live orientation {live['orientation']}° does not match the pinned "
                f"calibration {pinned_calibration['orientation']}°."
            ),
            "action": "Rotate the tablet back or take a new calibration for the current orientation.",
        })
    if not dpr_matches:
        fences.append({
            "code": "dpr_mismatch",
            "severity": "error",
            "message": (
                f"The live DPR {live['dpr']} does not match the pinned calibration "
                f"{pinned_calibration['dpr']}."
            ),
            "action": "Use the measured device pixel ratio or take a new calibration.",
        })
    if not mode_matches:
        fences.append({
            "code": "viewport_mismatch",
            "severity": "error",
            "message": (
                f"The launch mode changed from {pinned_calibration['mode']} to "
                f"{live['mode']}, so browser insets differ from the measurement."
            ),
            "action": "Restore the calibrated launch mode or measure again in this mode.",
        })
    full_panel = bool(
        pinned_calibration["mode"] == "fullscreen"
        and live["mode"] == "fullscreen"
        and size_matches
        and orientation_matches
        and not zoom_changed
    )
    return {
        "supplied": True,
        "live": live,
        "pinned": pinned,
        "mode": {
            "pinned": pinned_calibration["mode"],
            "live": live["mode"],
            "matches": mode_matches,
            "adapted": False,
        },
        "orientation": {
            "pinned": pinned_calibration["orientation"],
            "live": live["orientation"],
            "matches": orientation_matches,
            "quarter_turn": pinned_calibration["quarter_turn"],
        },
        "dpr": {
            "pinned": pinned_calibration["dpr"],
            "live": live["dpr"],
            "matches": dpr_matches,
        },
        "size": {
            "pinned": [
                pinned_calibration["viewport_width"],
                pinned_calibration["viewport_height"],
            ],
            "live": [live["width"], live["height"]],
            "matches": size_matches,
        },
        "zoom": {
            "visual_scale": live["visual_scale"],
            "matches": not zoom_changed,
        },
        "full_panel": full_panel,
        "usable_extent_mm": [
            live["width"] * pinned_calibration["mm_per_css"][0],
            live["height"] * pinned_calibration["mm_per_css"][1],
        ],
        "insets": {
            "assumed": True,
            "source": (
                "fullscreen launch mode; zero browser inset assumed"
                if full_panel
                else "pinned calibration panel_offset_mm; total tab/standalone inset is not supplied"
            ),
            "left_mm": (
                0.0 if full_panel else pinned_calibration["panel_offset_mm"][0]
            ),
            "top_mm": (
                0.0 if full_panel else pinned_calibration["panel_offset_mm"][1]
            ),
            "right_mm": 0.0 if full_panel else None,
            "bottom_mm": 0.0 if full_panel else None,
            "panel_offset_mm": list(pinned_calibration["panel_offset_mm"]),
        },
        "fences": fences,
    }


def _predicted_full_panel(
    *,
    pinned_profile: dict[str, Any] | None,
    pinned_calibration: dict[str, Any] | None,
    model_values: dict[str, Any] | None,
    viewport_report: dict[str, Any],
    kind: str,
    scale_usable: bool,
) -> dict[str, Any]:
    if kind == "model" and model_values is not None:
        return {
            "valid": True,
            "basis": "model_native_fullspan",
            "reason_code": None,
            "reason": (
                "Model screen dimensions at the native portrait angle multiplied by the pinned model mm_per_css."
            ),
            "mm": list(model_values["fullspan_mm"]),
            "source": "model signature",
            "usable_for_mapping": bool(scale_usable and kind == "model"),
            "estimate_only": True,
            "orientation_swapped": False,
        }
    if pinned_calibration is None or pinned_profile is None:
        return {
            "valid": False,
            "basis": None,
            "reason_code": "missing_measurement",
            "reason": "No pinned profile and calibration pair exists.",
            "mm": None,
            "source": None,
            "usable_for_mapping": False,
            "estimate_only": True,
            "orientation_swapped": False,
        }
    if not viewport_report["full_panel"]:
        fence_codes = {str(fence["code"]) for fence in viewport_report["fences"]}
        if viewport_report["live"] is None:
            reason_code = "viewport_unavailable"
            reason = "No live viewport is available, so a full-panel extent cannot be confirmed."
        elif "zoom_changed" in fence_codes:
            reason_code = "zoom_changed"
            reason = (
                "Browser zoom is not 100%, so the usable viewport cannot be treated as a full panel."
            )
        elif fence_codes & {
            "viewport_mismatch", "dpr_mismatch", "viewport_too_large"
        }:
            reason_code = "viewport_mismatch"
            reason = (
                "The live viewport does not match the pinned full-panel mapping, so extrapolating to the full panel is not valid."
            )
        else:
            reason_code = "tab_viewport"
            reason = (
                "The pinned calibration uses a tab or standalone usable viewport, not a full panel. "
                "Total browser/PWA insets are not supplied, so extrapolating to the full panel is not valid."
            )
        return {
            "valid": False,
            "basis": None,
            "reason_code": reason_code,
            "reason": reason,
            "mm": None,
            "source": "pinned calibration usable viewport",
            "usable_for_mapping": False,
            "estimate_only": False,
            "orientation_swapped": False,
        }
    predicted = [
        pinned_calibration["viewport_width"] * pinned_calibration["mm_per_css"][0],
        pinned_calibration["viewport_height"] * pinned_calibration["mm_per_css"][1],
    ]
    swapped = pinned_calibration["quarter_turn"] % 2 == 1
    oriented = [predicted[1], predicted[0]] if swapped else predicted
    return {
        "valid": True,
        "basis": "pinned_full_panel_viewport",
        "reason_code": None,
        "reason": "Pinned fullscreen viewport extent multiplied by the pinned manual mm_per_css.",
        "mm": oriented,
        "source": "pinned calibration",
        "usable_for_mapping": bool(scale_usable and kind == "manual"),
        "estimate_only": False,
        "orientation_swapped": swapped,
    }


def _comparison(
    *,
    predicted: dict[str, Any],
    pinned_profile: dict[str, Any] | None,
    uncertainty: float | None,
    uncertainty_source: str | None,
    kind: str,
    scale_usable: bool,
) -> dict[str, Any]:
    if pinned_profile is None:
        return {
            "valid": False,
            "reason_code": "missing_lit_dimensions",
            "reason": "No pinned profile supplies the lit active dimensions.",
            "basis": predicted["basis"],
            "lit_dimensions_mm": None,
            "predicted_mm": predicted["mm"],
            "axes": [],
            "discrepancy": None,
            "requires_operator_decision": False,
            "message": "No lit dimensions were supplied, so no scale comparison is possible.",
            "action": "Pin the tablet's measured active width and height before comparing a scale.",
            "orientation_swapped": predicted["orientation_swapped"],
        }
    if not predicted["valid"]:
        return {
            "valid": False,
            "reason_code": predicted["reason_code"],
            "reason": predicted["reason"],
            "basis": predicted["basis"],
            "lit_dimensions_mm": [
                pinned_profile["active_width_mm"],
                pinned_profile["active_height_mm"],
            ],
            "predicted_mm": predicted["mm"],
            "axes": [],
            "discrepancy": None,
            "requires_operator_decision": False,
            "message": predicted["reason"],
            "action": (
                "Use a fullscreen measurement or compare the model signature separately; do not call the usable viewport a full panel."
            ),
            "orientation_swapped": predicted["orientation_swapped"],
        }
    lit = [
        pinned_profile["active_width_mm"],
        pinned_profile["active_height_mm"],
    ]
    predicted_mm = list(predicted["mm"])
    tolerance_base = uncertainty if uncertainty is not None else 0.0
    tolerance = max(tolerance_base, COMPARISON_TOLERANCE_FLOOR_MM)
    axes: list[dict[str, Any]] = []
    discrepancy = False
    for name, predicted_value, lit_value in zip(
        ("x", "y"), predicted_mm, lit, strict=True
    ):
        delta = predicted_value - lit_value
        percent = (delta / lit_value * 100.0) if lit_value else None
        within = abs(delta) <= tolerance
        if not within:
            discrepancy = True
        axes.append({
            "axis": name,
            "predicted_mm": predicted_value,
            "lit_mm": lit_value,
            "delta_mm": delta,
            "delta_percent": percent,
            "tolerance_mm": tolerance,
            "within_uncertainty": within,
        })
    adjusted = "x" if abs(axes[0]["delta_mm"]) >= abs(axes[1]["delta_mm"]) else "y"
    worst = axes[0] if adjusted == "x" else axes[1]
    if discrepancy:
        message = (
            f"The predicted full-panel {worst['axis']} extent {worst['predicted_mm']:.2f} mm "
            f"differs from the supplied lit dimension {worst['lit_mm']:.2f} mm by "
            f"{worst['delta_mm']:+.2f} mm "
            f"({worst['delta_percent']:+.2f}%). The comparison tolerance is "
            f"{tolerance:.2f} mm"
            + (
                " from the supplied uncertainty."
                if uncertainty is not None
                else " from the minimum comparison floor; no uncertainty was supplied."
            )
        )
        action = (
            "Re-measure the full span or correct the supplied lit dimensions. "
            "The helper does not average, overwrite, or choose either value."
        )
        if predicted["estimate_only"] and not predicted["usable_for_mapping"]:
            message = (
                "The model signature suggests a "
                f"{worst['predicted_mm']:.2f} mm {worst['axis']} fullspan, which differs "
                f"from the supplied lit dimension {worst['lit_mm']:.2f} mm by "
                f"{worst['delta_mm']:+.2f} mm. A signature is not a confirmed scale."
            )
            action = (
                "Do not confirm this model from the signature alone. Take a ruler "
                "measurement or correct the supplied lit dimensions; nothing was changed."
            )
    else:
        message = (
            f"The predicted full-panel extent agrees with the supplied lit dimensions within "
            f"{tolerance:.2f} mm"
            + (
                f" ({uncertainty_source} uncertainty)."
                if uncertainty is not None
                else " (minimum comparison floor; no uncertainty supplied)."
            )
        )
        action = "No operator decision is required for this comparison."
    return {
        "valid": True,
        "reason_code": None,
        "reason": predicted["reason"],
        "basis": predicted["basis"],
        "lit_dimensions_mm": lit,
        "predicted_mm": predicted_mm,
        "axes": axes,
        "discrepancy": discrepancy,
        "requires_operator_decision": discrepancy,
        "message": message,
        "action": action,
        "tolerance_mm": tolerance,
        "uncertainty_source": uncertainty_source,
        "estimate_only": predicted["estimate_only"],
        "usable_for_mapping": bool(scale_usable and predicted["usable_for_mapping"]),
        "orientation_swapped": predicted["orientation_swapped"],
    }


def _status(
    *,
    pinned_profile: dict[str, Any] | None,
    pinned_calibration: dict[str, Any] | None,
    pinned_pair_agrees: bool | None,
    kind: str,
    live: dict[str, Any] | None,
    zoom_changed: bool,
    viewport_mismatch: bool,
) -> tuple[str, str]:
    if pinned_profile is None or pinned_calibration is None:
        return "needs_calibration", "missing pinned profile or calibration"
    if pinned_pair_agrees is False:
        return "needs_calibration", "pinned profile and calibration revisions disagree"
    if kind == "unknown":
        return "needs_calibration", "provenance is unknown"
    if live is None:
        return "viewport_mismatch", "no live viewport"
    if zoom_changed:
        return "zoom_changed", "visual_scale is not 1.0"
    if viewport_mismatch:
        return "viewport_mismatch", "live viewport does not match the pinned mapping"
    return "ready", "pinned mapping is usable"


def check_ruler_scale(
    *,
    span_px: float,
    span_mm: float,
    span_error_mm: float,
    usable_width_px: float,
    usable_height_px: float,
    axis: str = "x",
    supplied_width_mm: float | None = None,
    supplied_height_mm: float | None = None,
    span_count: int = 1,
) -> dict[str, Any]:
    """Check a prospective ruler span without saving or changing anything.

    ``span_px`` and ``span_mm`` are the explicit total ruler span after any
    multi-span segments are combined. ``span_error_mm`` is the operator's
    explicit ruler error. The result shows the derived mm/CSS, the implied
    dimensions, and the uncertainty extrapolated to those dimensions. A
    disagreement with a supplied lit dimension is returned as a decision for
    the operator; no value is averaged, chosen, or written.
    """
    if not isinstance(axis, str) or axis not in ("x", "y"):
        raise CalibrationHealthError("axis must be 'x' or 'y'")
    px = _number(span_px, "span_px", positive=True)
    mm = _number(span_mm, "span_mm", positive=True)
    error = _number(span_error_mm, "span_error_mm", nonnegative=True)
    usable_width = _number(usable_width_px, "usable_width_px", positive=True)
    usable_height = _number(usable_height_px, "usable_height_px", positive=True)
    if usable_width > MAX_USABLE_PX or usable_height > MAX_USABLE_PX:
        raise CalibrationHealthError("the usable viewport is absurdly large")
    if isinstance(span_count, bool) or not isinstance(span_count, int):
        raise CalibrationHealthError("span_count must be a positive integer")
    if span_count < 1 or span_count > MAX_SPAN_COUNT:
        raise CalibrationHealthError(
            f"span_count must be between 1 and {MAX_SPAN_COUNT}"
        )
    if px > MAX_USABLE_PX or mm > MAX_RULER_SPAN_MM:
        raise CalibrationHealthError("the ruler span is absurdly large")
    supplied_width_value = (
        None
        if supplied_width_mm is None
        else _number(supplied_width_mm, "supplied_width_mm", positive=True)
    )
    supplied_height_value = (
        None
        if supplied_height_mm is None
        else _number(supplied_height_mm, "supplied_height_mm", positive=True)
    )
    usable_axis = usable_width if axis == "x" else usable_height
    if px > usable_axis + 0.5:
        raise CalibrationHealthError(
            f"span_px {px} exceeds the usable {axis} viewport {usable_axis}"
        )
    supplied = supplied_width_value if axis == "x" else supplied_height_value

    mm_per_css = mm / px
    relative_error = error / mm
    extrapolation_factor = usable_axis / px
    short_span = extrapolation_factor > SHORT_SPAN_FACTOR
    if span_count > 1:
        quality = "multi-span"
    elif extrapolation_factor <= FULL_SPAN_FACTOR:
        quality = "full-span"
    elif short_span:
        quality = "short-span"
    else:
        quality = "partial-span"
    if quality == "short-span":
        quality_label = (
            f"Short span — higher extrapolation ({extrapolation_factor:.2f}x the usable {axis} axis)"
        )
    elif quality == "full-span":
        quality_label = "Full usable span — low extrapolation"
    elif quality == "multi-span":
        quality_label = (
            f"Multi-span measurement ({span_count} spans, {extrapolation_factor:.2f}x)"
        )
    else:
        quality_label = f"Partial span — {extrapolation_factor:.2f}x extrapolation"

    implied_width = usable_width * mm_per_css
    implied_height = usable_height * mm_per_css
    implied_measured = implied_width if axis == "x" else implied_height
    uncertainty_width = implied_width * relative_error
    uncertainty_height = implied_height * relative_error
    uncertainty_measured = (
        uncertainty_width if axis == "x" else uncertainty_height
    )
    mm_per_css_uncertainty = mm_per_css * relative_error
    if mm_per_css <= 0 or not all(math.isfinite(value) for value in (
        mm_per_css, relative_error, extrapolation_factor, implied_width,
        implied_height, uncertainty_width, uncertainty_height, mm_per_css_uncertainty,
    )):
        raise CalibrationHealthError("ruler values produce an unrepresentable scale or uncertainty")

    warnings: list[dict[str, Any]] = []
    if short_span:
        warnings.append(_warning(
            "short_span",
            "warning",
            f"The span {px:g} px is {extrapolation_factor:.2f}x smaller than the usable {axis} axis, so the derived scale is extrapolated.",
            f"Measure the full usable {axis} axis, or combine multiple spans into one explicit span, to reduce extrapolation.",
        ))

    if supplied is None:
        comparison: dict[str, Any] = {
            "valid": False,
            "reason_code": "supplied_dimension_missing",
            "reason": f"No supplied lit {axis} dimension was given.",
            "axis": axis,
            "implied_mm": implied_measured,
            "supplied_mm": None,
            "delta_mm": None,
            "delta_percent": None,
            "tolerance_mm": max(uncertainty_measured, COMPARISON_TOLERANCE_FLOOR_MM),
            "disagreement": None,
        }
        warnings.append(_warning(
            "supplied_dimension_missing",
            "info",
            f"No supplied lit {axis} dimension was given, so the ruler scale cannot be checked against the profile.",
            "Supply the current measured width and height to see both values and the consequences.",
        ))
        disagreement = False
    else:
        delta = implied_measured - supplied
        percent = delta / supplied * 100.0
        if not math.isfinite(percent):
            raise CalibrationHealthError("ruler comparison is not representable")
        tolerance = max(uncertainty_measured, COMPARISON_TOLERANCE_FLOOR_MM)
        disagreement = abs(delta) > tolerance
        comparison = {
            "valid": True,
            "reason_code": None,
            "reason": None,
            "axis": axis,
            "implied_mm": implied_measured,
            "supplied_mm": supplied,
            "delta_mm": delta,
            "delta_percent": percent,
            "tolerance_mm": tolerance,
            "disagreement": disagreement,
        }

    choices: list[dict[str, str]] = []
    if disagreement and supplied is not None:
        choices = [
            {
                "id": "keep_supplied",
                "label": "Keep the supplied dimension",
                "consequence": (
                    f"Keep {supplied:.2f} mm for the {axis} dimension. The ruler scale is not saved, "
                    "so the existing mapping remains unchanged."
                ),
            },
            {
                "id": "use_ruler",
                "label": "Save the ruler scale",
                "consequence": (
                    f"Save a new calibration revision with {mm_per_css:.8g} mm/CSS and an implied "
                    f"{implied_measured:.2f} mm {axis} extent. Existing revisions and layouts that pin them stay unchanged."
                ),
            },
            {
                "id": "remeasure",
                "label": "Measure again",
                "consequence": (
                    "Repeat the measurement with a longer span to reduce extrapolation, then compare both values again."
                ),
            },
        ]
        decision_message = (
            f"The ruler implies {implied_measured:.2f} mm for the {axis} dimension; the supplied "
            f"dimension is {supplied:.2f} mm. Both are shown. Choose which value to keep or re-measure; "
            "nothing has been changed."
        )
    elif supplied is not None:
        decision_message = (
            f"The ruler and supplied {axis} dimension agree within the propagated "
            f"{comparison['tolerance_mm']:.2f} mm tolerance. Nothing has been changed."
        )
    else:
        decision_message = (
            "The ruler scale is derived, but no supplied dimension was available for a comparison. "
            "Nothing has been changed."
        )

    actionable = _pick_actionable(warnings)
    if disagreement:
        actionable = {
            "code": "scale_disagreement",
            "severity": "warning",
            "message": decision_message,
            "action": "Choose keep_supplied, use_ruler, or remeasure; this helper never changes the supplied value.",
        }

    return {
        "schema": 1,
        "axis": axis,
        "status": (
            "uncompared"
            if supplied is None
            else ("disagreement" if disagreement else "agree")
        ),
        "derived": {
            "mm_per_css": mm_per_css,
            "mm_per_css_uncertainty": mm_per_css_uncertainty,
            "relative_error": relative_error,
            "span_quality": quality,
            "quality_label": quality_label,
            "short_span": short_span,
            "extrapolation_factor": extrapolation_factor,
            "span_count": span_count,
        },
        "inputs": {
            "span_px": px,
            "span_mm": mm,
            "span_error_mm": error,
            "span_count": span_count,
            "axis": axis,
            "usable_width_px": usable_width,
            "usable_height_px": usable_height,
            "supplied_width_mm": supplied_width_value,
            "supplied_height_mm": supplied_height_value,
        },
        "implied_dimensions_mm": {
            "width": implied_width,
            "height": implied_height,
            "measured_axis": axis,
            "measured": implied_measured,
            "assumes_uniform_scale": True,
            "note": (
                "The same mm/CSS value is applied to the unmeasured axis; that is an assumption, not a second measurement."
            ),
        },
        "extrapolated_uncertainty": {
            "width_mm": uncertainty_width,
            "height_mm": uncertainty_height,
            "measured_mm": uncertainty_measured,
            "mm_per_css": mm_per_css_uncertainty,
            "relative": relative_error,
            "formula": "span_error_mm / span_mm × implied dimension",
        },
        "comparison": comparison,
        "decision": {
            "required": disagreement,
            "code": "scale_disagreement" if disagreement else None,
            "message": decision_message,
            "choices": choices,
            "changes_nothing": True,
            "saved": False,
        },
        "warnings": warnings,
        "actionable_warning": actionable,
        "assumptions": [
            "The ruler span and error are explicit inputs; no model substitution occurred.",
            "Implied dimensions use the supplied usable viewport CSS size.",
            "The unmeasured axis uses the same scale as an explicit assumption.",
            "This arithmetic does not establish a 2 mm accuracy target.",
        ],
        "accuracy_claimed": False,
        "note": (
            "Prospective calculation only. No profile, calibration revision, saved layout, or live mapping was written."
        ),
    }
