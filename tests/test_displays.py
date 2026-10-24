"""Immutable display profiles and calibrations (schema 2)."""

import pytest

from tabletwall import displays

DEVICE = "0f8fad5b-d9cb-469f-a165-70867728950e"


def profile(device=DEVICE, width=100, height=60):
    return displays.save_profile(
        device,
        active_width_mm=width,
        active_height_mm=height,
        bezels={"left": 13, "top": 13, "right": 7, "bottom": 17},
        panel_pixels={"width": 2360, "height": 1640},
        label="iPad 9.7",
        provenance="ruler",
    )


def calibration(device=DEVICE, profile_revision=1):
    return displays.save_calibration(
        device,
        profile_revision=profile_revision,
        viewport_width=600,
        viewport_height=800,
        dpr=1.25,
        orientation=0,
        mode="fullscreen",
        quarter_turn=1,
        panel_offset_mm=(10, 20),
        mm_per_css=(1 / 6, 1 / 6),
        anchor_edge="top-left",
        uncertainty_mm=0.5,
        method="ruler",
    )


def test_profiles_append_revisions_and_keep_their_measurement():
    first = profile()
    assert first["revision"] == 1
    second = profile(width=120, height=80)
    assert second["revision"] == 2
    assert displays.profile(DEVICE, 1)["active_width_mm"] == 100
    assert displays.latest_profile(DEVICE)["active_width_mm"] == 120
    assert [entry["revision"] for entry in displays.list_profiles()] == [2]


def test_calibration_requires_an_existing_profile_and_valid_fields():
    with pytest.raises(displays.DisplayError, match="does not exist"):
        calibration(profile_revision=9)
    profile()
    saved = calibration()
    assert saved["profile_revision"] == 1
    assert saved["quarter_turn"] == 1
    with pytest.raises(displays.DisplayError):
        displays.save_calibration(
            DEVICE, profile_revision=1, viewport_width=600, viewport_height=800,
            dpr=1, orientation=0, mode="tab", quarter_turn=4,
            panel_offset_mm=(0, 0), mm_per_css=(1, 1),
            anchor_edge="top-left", uncertainty_mm=0, method="ruler",
        )
    with pytest.raises(displays.DisplayError):
        displays.save_calibration(
            DEVICE, profile_revision=1, viewport_width=600, viewport_height=800,
            dpr=1, orientation=0, mode="tab", quarter_turn=0,
            panel_offset_mm=(0, 0), mm_per_css=(0, 1),
            anchor_edge="top-left", uncertainty_mm=0, method="ruler",
        )


def test_latest_calibration_is_the_one_matching_the_profile():
    profile()
    first = calibration()
    profile(width=120, height=80)
    second = displays.save_calibration(
        DEVICE, profile_revision=2, viewport_width=800, viewport_height=600,
        dpr=1, orientation=90, mode="standalone", quarter_turn=0,
        panel_offset_mm=(0, 0), mm_per_css=(1, 1),
        anchor_edge="top-left", uncertainty_mm=0, method="spec",
    )
    assert displays.calibration(DEVICE, first["revision"])["profile_revision"] == 1
    assert displays.latest_calibration(DEVICE)["revision"] == second["revision"]
    assert displays.calibration_for(DEVICE, 1)["revision"] == first["revision"]
    assert displays.calibration_for(DEVICE, 2)["revision"] == second["revision"]


def test_negative_bezels_and_non_uuid_devices_are_refused():
    with pytest.raises(displays.DisplayError):
        displays.save_profile(
            DEVICE, active_width_mm=100, active_height_mm=60,
            bezels={"left": -1, "top": 0, "right": 0, "bottom": 0},
            panel_pixels=None, label="x", provenance="ruler",
        )
    with pytest.raises(displays.DisplayError):
        displays.save_profile(
            "not-a-uuid", active_width_mm=100, active_height_mm=60,
            bezels={"left": 0, "top": 0, "right": 0, "bottom": 0},
            panel_pixels=None, label="x", provenance="ruler",
        )
