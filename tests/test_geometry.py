"""Independent fixtures for the v3 physical transform."""

import json
from pathlib import Path

import pytest

from tabletwall import geometry

FIXTURES = Path(__file__).parent / "fixtures" / "geometry" / "render_cases.json"


def cases():
    return json.loads(FIXTURES.read_text())["cases"]


def close(left, right, tolerance=1e-9):
    if isinstance(left, (list, tuple)):
        assert len(left) == len(right)
        for a, b in zip(left, right):
            assert abs(a - b) <= tolerance, (a, b)
    elif isinstance(left, dict):
        assert set(left) == set(right)
        for key in left:
            close(left[key], right[key], tolerance)
    else:
        assert abs(left - right) <= tolerance, (left, right)


@pytest.mark.parametrize("case", cases(), ids=lambda case: case["name"])
def test_fixture(case):
    plan = geometry.normalized_source_to_panel(
        active_size=tuple(case["active_size"]),
        bezels=case["bezels"],
        center_mm=tuple(case["center_mm"]),
        nudge_mm=tuple(case["nudge_mm"]),
        mount_angle=case["mount_angle"],
        bounds=tuple(case["bounds"]),
        source_size=tuple(case["source_size"]),
        fit=case["fit"],
    )
    expected = case["expected"]
    close(plan["body"], expected["body"])
    close(plan["active"], expected["active"])
    close(plan["panel_to_wall"], expected["panel_to_wall"])
    close(plan["panel_from_source"], expected["panel_from_source"])

    calibration = case["calibration"]
    u = geometry.css_to_panel(
        viewport_width=calibration["viewport_width"],
        viewport_height=calibration["viewport_height"],
        quarter=calibration["quarter_turn"],
        panel_offset_mm=tuple(calibration["panel_offset_mm"]),
        mm_per_css=tuple(calibration["mm_per_css"]),
    )
    close(u, expected["u_c_to_p"])

    components = geometry.canvas_transform_components(
        backing=tuple(case["backing"]),
        rect=tuple(case["rect"]),
        calibration=calibration,
        panel_from_source=tuple(plan["panel_from_source"]),
        source_size=tuple(case["source_size"]),
    )
    close(components["matrix"], expected["canvas"])
    close(components["clip"], expected["clip"])
    for point in expected["points"]:
        close(geometry.apply(tuple(components["matrix"]), tuple(point["source"])),
              point["backing"])


def test_the_panel_matrix_is_invertible_and_maps_the_expected_corners():
    plan = geometry.normalized_source_to_panel(
        active_size=(100, 60),
        bezels={"left": 13, "top": 13, "right": 7, "bottom": 17},
        center_mm=(300, 400),
        nudge_mm=(5, -3),
        mount_angle=90,
        bounds=(0, 0, 1200, 800),
        source_size=(2000, 1000),
    )
    matrix = tuple(plan["panel_from_source"])
    inverse = geometry.inverse(matrix)
    for point in ((0.0, 0.0), (0.5, 0.25), (1.0, 1.0)):
        close(geometry.apply(inverse, geometry.apply(matrix, point)), point)


def test_cover_and_contain_share_the_centre_but_not_the_extent():
    cover = geometry.fit_matrix((0, 0, 200, 100), 400, 200, "cover")
    contain = geometry.fit_matrix((0, 0, 200, 100), 100, 100, "contain")
    assert cover == (200, 0, 0, 100, 0, 0)
    assert contain == (100, 0, 0, 100, 50, 0)


def test_negative_or_missing_bezels_are_refused():
    with pytest.raises(geometry.GeometryError):
        geometry.body_geometry(100, 60, {"left": -1, "top": 0, "right": 0, "bottom": 0})
    with pytest.raises(geometry.GeometryError):
        geometry.body_geometry(100, 60, {"left": 0, "top": 0, "right": 0})
    with pytest.raises(geometry.GeometryError):
        geometry.quarter_turn(4, 100, 100)


def test_identical_css_sizes_with_different_physical_sizes_differ():
    small = geometry.normalized_source_to_panel(
        active_size=(60, 60),
        bezels={"left": 0, "top": 0, "right": 0, "bottom": 0},
        center_mm=(100, 100), nudge_mm=(0, 0), mount_angle=0,
        bounds=(0, 0, 200, 200), source_size=(200, 200),
    )
    large = geometry.normalized_source_to_panel(
        active_size=(120, 120),
        bezels={"left": 0, "top": 0, "right": 0, "bottom": 0},
        center_mm=(100, 100), nudge_mm=(0, 0), mount_angle=0,
        bounds=(0, 0, 200, 200), source_size=(200, 200),
    )
    assert small["panel_from_source"] != large["panel_from_source"]
