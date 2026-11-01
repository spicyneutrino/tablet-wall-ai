"""Pinned calibration provenance, health, and prospective ruler scale checks."""

import copy
import json
import math

import pytest

from tabletwall import calibration_health

DEVICE = "10000000-0000-4000-8000-000000000001"


def model_profile(width=144.1728, height=192.2304):
    return {
        "device_id": DEVICE,
        "revision": 4,
        "active_width_mm": width,
        "active_height_mm": height,
        "bezels": {"left": 10.52, "right": 10.52, "top": 21.1, "bottom": 21.1},
        "panel_pixels": {"width": 1536, "height": 2048},
        "label": "iPad Air 2",
        "provenance": "tablet-model",
        "created_at": "2026-11-01T12:00:00Z",
    }


def manual_profile():
    return {
        "device_id": DEVICE,
        "revision": 4,
        "active_width_mm": 120.0,
        "active_height_mm": 160.0,
        "bezels": {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0},
        "label": "fixture",
        "provenance": "ruler fixture",
    }


def model_snapshot():
    return {
        "label": "iPad Air 2",
        "screen_width": 768,
        "screen_height": 1024,
        "portrait_angle": 0,
        "dpr": 2.0,
        "mm_per_css": [0.187725, 0.187725],
        "uncertainty_mm": 3.0,
    }


def model_calibration():
    return {
        "device_id": DEVICE,
        "revision": 9,
        "profile_revision": 4,
        "viewport_width": 768.0,
        "viewport_height": 1024.0,
        "dpr": 2.0,
        "orientation": 0,
        "mode": "fullscreen",
        "quarter_turn": 0,
        "panel_offset_mm": [0.0, 0.0],
        "mm_per_css": [0.187725, 0.187725],
        "anchor_edge": "top-left",
        "uncertainty_mm": 3.0,
        "method": "tablet-model approximate",
        "created_at": "2026-11-01T12:00:00Z",
    }


def manual_calibration():
    return {
        "device_id": DEVICE,
        "revision": 9,
        "profile_revision": 4,
        "viewport_width": 600.0,
        "viewport_height": 800.0,
        "dpr": 2.0,
        "orientation": 0,
        "mode": "fullscreen",
        "quarter_turn": 0,
        "panel_offset_mm": [0.0, 0.0],
        "mm_per_css": [0.2, 0.2],
        "anchor_edge": "top-left",
        "uncertainty_mm": 0.5,
        "method": "ruler-measured",
        "created_at": "2026-11-01T12:00:00Z",
    }


def model_assignment(**overrides):
    assignment = {
        "mode": "auto",
        "model_id": "ipad-air-2",
        "model": model_snapshot(),
        "profile_revision": 4,
        "calibration_revision": 9,
    }
    assignment.update(overrides)
    return assignment


def full_viewport(**overrides):
    viewport = {
        "width": 768.0,
        "height": 1024.0,
        "dpr": 2.0,
        "orientation": 0,
        "mode": "fullscreen",
        "visual_scale": 1.0,
    }
    viewport.update(overrides)
    return viewport


def manual_viewport(**overrides):
    viewport = {
        "width": 600.0,
        "height": 800.0,
        "dpr": 2.0,
        "orientation": 0,
        "mode": "fullscreen",
        "visual_scale": 1.0,
    }
    viewport.update(overrides)
    return viewport


def evaluate(**overrides):
    arguments = {
        "profile": model_profile(),
        "calibration": model_calibration(),
        "assignment": model_assignment(),
        "model": None,
        "viewport": full_viewport(),
        "device_id": DEVICE,
    }
    arguments.update(overrides)
    return calibration_health.assess_calibration(**arguments)


def warning_codes(result):
    return {warning["code"] for warning in result["warnings"]}


def test_missing_measurement_is_needs_calibration_and_a_model_is_only_a_suggestion():
    result = evaluate(
        profile=None,
        calibration=None,
        assignment=None,
        model=model_snapshot(),
    )
    assert result["status"] == "needs_calibration"
    assert result["provenance"]["kind"] == "model"
    assert result["provenance"]["confirmed"] is False
    assert result["provenance"]["confirmation_required"] is True
    assert result["scale"] is None
    assert result["scale_unavailable_reason"] == "missing pinned calibration"
    assert result["predicted_full_panel"]["valid"] is True
    assert result["predicted_full_panel"]["basis"] == "model_native_fullspan"
    assert result["predicted_full_panel"]["mm"] == pytest.approx([144.1728, 192.2304])
    assert result["comparison"]["valid"] is False
    assert result["comparison"]["reason_code"] == "missing_lit_dimensions"
    assert result["ok"] is False
    assert {"profile_or_calibration_missing", "model_confirmation_required"} <= warning_codes(result)
    assert result["actionable_warning"]["severity"] == "error"


def test_auto_existing_assignment_is_visible_but_unconfirmed():
    result = evaluate()
    assert result["status"] == "ready"
    assert result["status_label"].startswith("Ready — unconfirmed model estimate")
    assert result["ok"] is False
    assert result["approximate"] is True
    assert result["confirmed"] is False
    assert result["provenance"]["kind"] == "model"
    assert result["provenance"]["model_snapshot"]["source"] == "pinned_assignment_snapshot"
    assert result["scale"]["usable"] is True
    assert result["scale"]["source"] == "model_snapshot"
    assert result["scale"]["approximate"] is True
    assert result["scale"]["confirmed"] is False
    assert result["revisions"]["assignment"]["pinned_match"] is True
    assert result["comparison"]["valid"] is True
    assert result["comparison"]["discrepancy"] is False
    assert "model_confirmation_required" in warning_codes(result)


def test_realistic_model_fullspan_discrepancy_is_reported_not_hidden():
    result = evaluate(
        profile=model_profile(146.75, 196.0),
        model=model_snapshot(),
    )
    assert result["comparison"]["valid"] is True
    assert result["comparison"]["discrepancy"] is True
    assert result["comparison"]["requires_operator_decision"] is True
    axes = {axis["axis"]: axis for axis in result["comparison"]["axes"]}
    assert axes["x"]["delta_mm"] == pytest.approx(-2.5772, abs=1e-6)
    assert axes["y"]["delta_mm"] == pytest.approx(-3.7696, abs=1e-6)
    assert axes["y"]["within_uncertainty"] is False
    assert "scale_discrepancy" in warning_codes(result)
    assert "does not average" in result["comparison"]["action"]
    assert result["status"] == "ready"
    assert result["ok"] is False


def test_confirmed_model_stays_approximate_and_never_plain_ok():
    result = evaluate(
        assignment=model_assignment(confirmed=True),
        model=model_snapshot(),
    )
    assert result["status"] == "ready"
    assert result["confirmed"] is True
    assert result["approximate"] is True
    assert result["ok"] is False
    assert result["provenance"]["confirmed"] is True
    assert result["provenance"]["confirmation_required"] is False
    assert result["scale"]["confirmed"] is True
    assert result["scale"]["approximate"] is True
    assert "confirmed" in result["status_label"]
    assert "approximate" in result["status_label"]
    assert "model_confirmation_required" not in warning_codes(result)


def test_manual_full_panel_measurement_is_ready_and_compared_with_its_lit_dimensions():
    result = evaluate(
        profile=manual_profile(),
        calibration=manual_calibration(),
        assignment=None,
        model=None,
        viewport=manual_viewport(),
    )
    assert result["status"] == "ready"
    assert result["ok"] is True
    assert result["provenance"]["kind"] == "manual"
    assert result["provenance"]["manual"] is True
    assert result["provenance"]["manual_value"]["mm_per_css"] == [0.2, 0.2]
    assert result["approximate"] is False
    assert result["confirmed"] is True
    assert result["scale"]["usable"] is True
    assert result["scale"]["source"] == "pinned_calibration"
    assert result["uncertainty_mm"] == 0.5
    assert result["uncertainty"]["source"] == "pinned_calibration"
    assert result["predicted_full_panel"]["valid"] is True
    assert result["predicted_full_panel"]["mm"] == pytest.approx([120.0, 160.0])
    assert result["comparison"]["valid"] is True
    assert result["comparison"]["discrepancy"] is False
    assert result["warnings"] == []


def test_manual_discrepancy_is_shown_and_is_not_plain_ok():
    profile = manual_profile()
    profile["active_width_mm"] = 130.0
    result = evaluate(
        profile=profile,
        calibration=manual_calibration(),
        assignment=None,
        model=None,
        viewport=manual_viewport(),
    )
    assert result["status"] == "ready"
    assert result["ok"] is False
    assert result["comparison"]["discrepancy"] is True
    assert "scale_discrepancy" in warning_codes(result)
    assert "scale discrepancy" in result["status_label"]
    assert result["comparison"]["requires_operator_decision"] is True
    assert result["comparison"]["axes"][0]["delta_mm"] == pytest.approx(-10.0)


def test_manual_tab_viewport_is_not_mistaken_for_a_full_panel():
    result = evaluate(
        profile=manual_profile(),
        calibration={**manual_calibration(), "mode": "tab"},
        assignment=None,
        model=None,
        viewport=manual_viewport(mode="tab"),
    )
    assert result["status"] == "ready"
    assert result["viewport"]["full_panel"] is False
    assert result["predicted_full_panel"]["valid"] is False
    assert result["predicted_full_panel"]["reason_code"] == "tab_viewport"
    assert result["comparison"]["valid"] is False
    assert "full_panel_comparison_unavailable" in warning_codes(result)
    assert result["viewport"]["usable_extent_mm"] == pytest.approx([120.0, 160.0])
    assert result["viewport"]["insets"]["right_mm"] is None
    assert result["ok"] is False
    assert "usable viewport, not a confirmed full panel" in result["status_label"]


def test_manual_zoom_change_is_a_specific_fence():
    result = evaluate(
        profile=manual_profile(),
        calibration=manual_calibration(),
        assignment=None,
        model=None,
        viewport=manual_viewport(visual_scale=1.25),
    )
    assert result["status"] == "zoom_changed"
    assert result["scale"]["usable"] is False
    assert result["scale"]["unusable_reason"] == "browser zoom is not 100%"
    assert "zoom_changed" in warning_codes(result)
    assert result["predicted_full_panel"]["reason_code"] == "zoom_changed"


def test_manual_viewport_size_change_is_a_specific_fence():
    result = evaluate(
        profile=manual_profile(),
        calibration=manual_calibration(),
        assignment=None,
        model=None,
        viewport=manual_viewport(width=601.0),
    )
    assert result["status"] == "viewport_mismatch"
    assert result["scale"]["usable"] is False
    assert "viewport_mismatch" in warning_codes(result)
    assert result["status_label"] == "Viewport mismatch"


def test_newer_assignment_does_not_mark_a_valid_pinned_slot_as_needing_calibration():
    assignment = model_assignment(
        profile_revision=5,
        calibration_revision=10,
        confirmed=True,
    )
    result = evaluate(
        profile=manual_profile(),
        calibration=manual_calibration(),
        assignment=assignment,
        model=None,
        viewport=manual_viewport(),
    )
    assert result["status"] == "ready"
    assert result["status"] != "needs_calibration"
    assert result["revisions"]["profile_revision"] == 4
    assert result["revisions"]["calibration_revision"] == 9
    assert result["revisions"]["pinned_pair_agrees"] is True
    assert result["revisions"]["assignment"]["profile_revision"] == 5
    assert result["revisions"]["assignment"]["calibration_revision"] == 10
    assert result["revisions"]["assignment"]["pinned_match"] is False
    assert result["revisions"]["latest_substitution"] is False
    assert "model_snapshot_revision_mismatch" in warning_codes(result)
    assert result["scale"]["usable"] is True
    assert result["measurements"]["calibration"] == manual_calibration()


def test_mismatched_pinned_pair_is_needs_calibration():
    result = evaluate(
        profile=manual_profile(),
        calibration={**manual_calibration(), "profile_revision": 3},
        assignment=None,
        model=None,
        viewport=manual_viewport(),
    )
    assert result["status"] == "needs_calibration"
    assert result["status_reason"] == "pinned profile and calibration revisions disagree"
    assert result["status_label"] == "Needs measurement"
    assert result["revisions"]["pinned_pair_agrees"] is False
    assert result["scale"]["usable"] is False
    assert "pinned_pair_mismatch" in warning_codes(result)


def test_bare_manual_assignment_does_not_emit_a_revision_mismatch_warning():
    result = evaluate(
        profile=manual_profile(),
        calibration=manual_calibration(),
        assignment={"mode": "manual", "model_id": None},
        model=None,
        viewport=manual_viewport(),
    )
    assert result["status"] == "ready"
    assert "model_snapshot_revision_mismatch" not in warning_codes(result)
    assert result["revisions"]["assignment"]["present"] is True
    assert result["revisions"]["assignment"]["pinned_match"] is False


def test_uncertainty_is_preserved_for_both_sources_and_never_averaged():
    result = evaluate(
        calibration={**model_calibration(), "uncertainty_mm": 0.5},
        model=model_snapshot(),
    )
    assert result["uncertainty_mm"] == 0.5
    assert result["uncertainty"]["calibration_mm"] == 0.5
    assert result["uncertainty"]["model_mm"] == 3.0
    assert result["uncertainty"]["agreement"] is False
    assert result["scale"]["uncertainty_mm"] == 0.5
    assert "uncertainty_disagreement" in warning_codes(result)
    assert result["uncertainty_mm"] != pytest.approx(1.75)


def test_pinned_and_model_mm_per_css_are_both_preserved_when_they_differ():
    result = evaluate(
        calibration={**model_calibration(), "mm_per_css": [0.2, 0.2]},
        model=model_snapshot(),
    )
    assert result["scale"]["mm_per_css"] == [0.187725, 0.187725]
    assert result["scale"]["calibration_mm_per_css"] == [0.2, 0.2]
    assert result["scale"]["model_mm_per_css"] == [0.187725, 0.187725]
    assert result["measurements"]["calibration_mm_per_css"] == [0.2, 0.2]
    assert result["measurements"]["model_mm_per_css"] == [0.187725, 0.187725]
    assert "model_scale_disagreement" in warning_codes(result)


def test_model_calibration_without_a_snapshot_is_approximate_and_unconfirmed():
    result = evaluate(
        assignment=None,
        model=None,
    )
    assert result["status"] == "ready"
    assert result["provenance"]["kind"] == "model"
    assert result["approximate"] is True
    assert result["confirmed"] is False
    assert result["scale"]["usable"] is True
    assert result["scale"]["source"] == "pinned_calibration"
    assert {"model_snapshot_unavailable", "model_confirmation_required"} <= warning_codes(result)


def test_unknown_provenance_has_no_usable_scale():
    result = evaluate(
        calibration={**manual_calibration(), "method": "unrecorded"},
        profile={**manual_profile(), "provenance": "legacy"},
        assignment=None,
        model=None,
        viewport=manual_viewport(),
    )
    assert result["status"] == "needs_calibration"
    assert result["provenance"]["kind"] == "unknown"
    assert result["scale"]["usable"] is False
    assert "unknown_provenance" in warning_codes(result)


def test_result_is_json_ready_and_does_not_mutate_supplied_mappings():
    profile = model_profile()
    calibration = model_calibration()
    assignment = model_assignment()
    model = model_snapshot()
    viewport = full_viewport()
    originals = copy.deepcopy((profile, calibration, assignment, model, viewport))
    result = evaluate(
        profile=profile,
        calibration=calibration,
        assignment=assignment,
        model=model,
        viewport=viewport,
    )
    assert (profile, calibration, assignment, model, viewport) == originals
    assert result["measurements"]["profile"] == originals[0]
    assert result["measurements"]["calibration"] == originals[1]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize(
    "field, value",
    [
        ("viewport_width", True),
        ("viewport_height", math.nan),
        ("dpr", math.inf),
        ("orientation", 45),
        ("mode", "kiosk"),
        ("quarter_turn", True),
        ("panel_offset_mm", [0.0]),
        ("mm_per_css", [0.0, 0.2]),
        ("uncertainty_mm", -1.0),
        ("revision", 0),
    ],
)
def test_invalid_calibration_values_are_rejected(field, value):
    calibration = manual_calibration()
    calibration[field] = value
    with pytest.raises(calibration_health.CalibrationHealthError):
        evaluate(
            profile=manual_profile(),
            calibration=calibration,
            assignment=None,
            model=None,
            viewport=manual_viewport(),
        )


@pytest.mark.parametrize(
    "field, value",
    [
        ("revision", 0),
        ("active_width_mm", True),
        ("active_height_mm", math.inf),
        ("bezels", {"left": -1.0, "right": 0.0, "top": 0.0, "bottom": 0.0}),
    ],
)
def test_invalid_profile_values_are_rejected(field, value):
    profile = manual_profile()
    profile[field] = value
    with pytest.raises(calibration_health.CalibrationHealthError):
        evaluate(
            profile=profile,
            calibration=manual_calibration(),
            assignment=None,
            model=None,
            viewport=manual_viewport(),
        )


@pytest.mark.parametrize(
    "field, value",
    [
        ("screen_width", 0),
        ("screen_height", math.nan),
        ("dpr", math.inf),
        ("portrait_angle", 45),
        ("mm_per_css", [0.2]),
        ("uncertainty_mm", -1.0),
    ],
)
def test_invalid_model_values_are_rejected(field, value):
    model = model_snapshot()
    model[field] = value
    with pytest.raises(calibration_health.CalibrationHealthError):
        evaluate(model=model)


@pytest.mark.parametrize(
    "field, value",
    [
        ("width", True),
        ("height", math.nan),
        ("dpr", math.inf),
        ("orientation", 45),
        ("mode", "kiosk"),
        ("visual_scale", 0.0),
    ],
)
def test_invalid_viewport_values_are_rejected(field, value):
    viewport = full_viewport()
    viewport[field] = value
    with pytest.raises(calibration_health.CalibrationHealthError):
        evaluate(viewport=viewport)


def test_invalid_assignment_confirmation_is_rejected():
    with pytest.raises(calibration_health.CalibrationHealthError):
        evaluate(assignment=model_assignment(confirmed="yes"))


def test_model_tab_viewport_reports_usable_extent_separately_from_native_fullspan():
    result = evaluate(
        profile=model_profile(width=144.1728, height=192.2304),
        model=model_snapshot(),
        viewport=full_viewport(height=1000.0, mode="tab"),
    )
    assert result["status"] == "ready"
    assert result["viewport"]["full_panel"] is False
    assert result["viewport"]["mode"]["adapted"] is True
    assert result["predicted_full_panel"]["basis"] == "model_native_fullspan"
    assert result["predicted_full_panel"]["mm"] == pytest.approx([144.1728, 192.2304])
    assert result["viewport"]["usable_extent_mm"][1] == pytest.approx(187.725)
    assert result["viewport"]["insets"]["top_mm"] == pytest.approx(2.2527)
    assert result["viewport"]["insets"]["left_mm"] == pytest.approx(0.0)
    assert result["comparison"]["valid"] is True
    assert "tab_viewport_not_full_panel" in warning_codes(result)


def test_ruler_full_span_derives_scale_and_agrees():
    result = calibration_health.check_ruler_scale(
        span_px=600,
        span_mm=120,
        span_error_mm=0.5,
        usable_width_px=600,
        usable_height_px=800,
        supplied_width_mm=120,
        supplied_height_mm=160,
    )
    assert result["status"] == "agree"
    assert result["derived"]["mm_per_css"] == pytest.approx(0.2)
    assert result["derived"]["mm_per_css_uncertainty"] == pytest.approx(0.0008333333)
    assert result["derived"]["span_quality"] == "full-span"
    assert result["derived"]["short_span"] is False
    assert result["implied_dimensions_mm"]["width"] == pytest.approx(120)
    assert result["implied_dimensions_mm"]["height"] == pytest.approx(160)
    assert result["comparison"]["valid"] is True
    assert result["comparison"]["disagreement"] is False
    assert result["decision"]["required"] is False
    assert result["decision"]["choices"] == []
    assert result["decision"]["changes_nothing"] is True
    assert result["accuracy_claimed"] is False
    json.dumps(result, allow_nan=False)


def test_default_200px_span_is_labelled_short_and_higher_extrapolation():
    result = calibration_health.check_ruler_scale(
        span_px=200,
        span_mm=40,
        span_error_mm=0.5,
        usable_width_px=600,
        usable_height_px=800,
        supplied_width_mm=120,
        supplied_height_mm=160,
    )
    assert result["derived"]["mm_per_css"] == pytest.approx(0.2)
    assert result["derived"]["short_span"] is True
    assert result["derived"]["span_quality"] == "short-span"
    assert result["derived"]["extrapolation_factor"] == pytest.approx(3.0)
    assert "Short span" in result["derived"]["quality_label"]
    assert "short_span" in warning_codes(result)
    assert "higher extrapolation" in result["derived"]["quality_label"]


def test_multi_span_measurement_is_labelled():
    result = calibration_health.check_ruler_scale(
        span_px=600,
        span_mm=120,
        span_error_mm=0.5,
        usable_width_px=600,
        usable_height_px=800,
        supplied_width_mm=120,
        supplied_height_mm=160,
        span_count=3,
    )
    assert result["derived"]["span_quality"] == "multi-span"
    assert result["derived"]["span_count"] == 3
    assert result["inputs"]["span_count"] == 3
    assert "Multi-span" in result["derived"]["quality_label"]


def test_ruler_disagreement_requires_an_operator_decision_and_changes_nothing():
    result = calibration_health.check_ruler_scale(
        span_px=600,
        span_mm=120,
        span_error_mm=0.5,
        usable_width_px=600,
        usable_height_px=800,
        supplied_width_mm=150,
        supplied_height_mm=160,
    )
    assert result["status"] == "disagreement"
    assert result["comparison"]["valid"] is True
    assert result["comparison"]["implied_mm"] == pytest.approx(120)
    assert result["comparison"]["supplied_mm"] == pytest.approx(150)
    assert result["comparison"]["delta_mm"] == pytest.approx(-30)
    assert result["comparison"]["disagreement"] is True
    assert result["decision"]["required"] is True
    assert result["decision"]["code"] == "scale_disagreement"
    assert result["decision"]["changes_nothing"] is True
    assert result["decision"]["saved"] is False
    assert {choice["id"] for choice in result["decision"]["choices"]} == {
        "keep_supplied",
        "use_ruler",
        "remeasure",
    }
    assert result["actionable_warning"]["code"] == "scale_disagreement"
    assert "nothing has been changed" in result["decision"]["message"]
    assert result["inputs"]["supplied_width_mm"] == 150


def test_ruler_extrapolated_uncertainty_is_computed_from_the_explicit_error():
    result = calibration_health.check_ruler_scale(
        span_px=100,
        span_mm=20,
        span_error_mm=0.5,
        usable_width_px=600,
        usable_height_px=800,
        supplied_width_mm=120,
        supplied_height_mm=160,
    )
    assert result["derived"]["mm_per_css"] == pytest.approx(0.2)
    assert result["derived"]["relative_error"] == pytest.approx(0.025)
    assert result["derived"]["mm_per_css_uncertainty"] == pytest.approx(0.005)
    assert result["implied_dimensions_mm"]["width"] == pytest.approx(120)
    assert result["implied_dimensions_mm"]["height"] == pytest.approx(160)
    assert result["extrapolated_uncertainty"]["width_mm"] == pytest.approx(3.0)
    assert result["extrapolated_uncertainty"]["height_mm"] == pytest.approx(4.0)
    assert result["extrapolated_uncertainty"]["measured_mm"] == pytest.approx(3.0)
    assert "span_error_mm / span_mm" in result["extrapolated_uncertainty"]["formula"]


def test_ruler_without_supplied_dimension_is_uncompared():
    result = calibration_health.check_ruler_scale(
        span_px=600,
        span_mm=120,
        span_error_mm=0.5,
        usable_width_px=600,
        usable_height_px=800,
    )
    assert result["status"] == "uncompared"
    assert result["comparison"]["valid"] is False
    assert result["comparison"]["reason_code"] == "supplied_dimension_missing"
    assert result["decision"]["required"] is False
    assert "supplied_dimension_missing" in warning_codes(result)


@pytest.mark.parametrize(
    "overrides",
    [
        {"span_px": 0},
        {"span_px": True},
        {"span_px": math.nan},
        {"span_mm": math.inf},
        {"span_mm": 0},
        {"span_error_mm": -1},
        {"span_error_mm": math.nan},
        {"usable_width_px": 0},
        {"usable_width_px": True},
        {"span_px": 601},
        {"axis": "z"},
        {"span_count": 0},
        {"span_count": 65},
        {"span_count": True},
        {"supplied_width_mm": -1},
        {"supplied_height_mm": math.nan},
    ],
)
def test_ruler_rejects_invalid_or_unbounded_inputs(overrides):
    arguments = {
        "span_px": 600,
        "span_mm": 120,
        "span_error_mm": 0.5,
        "usable_width_px": 600,
        "usable_height_px": 800,
        "supplied_width_mm": 120,
        "supplied_height_mm": 160,
    }
    arguments.update(overrides)
    with pytest.raises(calibration_health.CalibrationHealthError):
        calibration_health.check_ruler_scale(**arguments)


def test_ruler_y_axis_uses_the_usable_height():
    result = calibration_health.check_ruler_scale(
        span_px=800,
        span_mm=160,
        span_error_mm=0.5,
        usable_width_px=600,
        usable_height_px=800,
        axis="y",
        supplied_width_mm=120,
        supplied_height_mm=160,
    )
    assert result["axis"] == "y"
    assert result["derived"]["mm_per_css"] == pytest.approx(0.2)
    assert result["implied_dimensions_mm"]["measured"] == pytest.approx(160)
    assert result["comparison"]["axis"] == "y"
    assert result["comparison"]["supplied_mm"] == pytest.approx(160)
    assert result["comparison"]["disagreement"] is False
