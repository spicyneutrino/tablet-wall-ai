"""Bounded diagnostic PNG bytes and their deterministic metadata."""

import copy
import json

import pytest
from PIL import Image
from io import BytesIO

from tabletwall import test_pattern

BACKGROUND = test_pattern.BACKGROUND
MAJOR_LINE = test_pattern.MAJOR_LINE
MINOR_LINE = test_pattern.MINOR_LINE


def bounds():
    return {"x": -125.0, "y": -75.0, "width": 350.0, "height": 300.0}


def decode(result):
    image = Image.open(BytesIO(result.data))
    image.load()
    return image


def pixel_at(result, x, y):
    return decode(result).getpixel((x, y))


def test_grid_is_an_ordinary_rgb_png_with_bounded_deterministic_dims():
    result = test_pattern.generate_test_pattern("grid", bounds=bounds())
    metadata = result.metadata
    image = decode(result)
    assert image.format == "PNG"
    assert image.mode == "RGB"
    assert image.size == (metadata["width"], metadata["height"])
    assert metadata["width"] <= test_pattern.MAX_EDGE_PX
    assert metadata["height"] <= test_pattern.MAX_EDGE_PX
    assert metadata["width"] * metadata["height"] <= test_pattern.MAX_PIXELS
    assert metadata["mode"] == "RGB"
    assert metadata["opaque"] is True
    assert result.data[25] == 2  # PNG IHDR colour type 2: truecolour, no alpha.
    assert image.convert("RGBA").getextrema()[3] == (255, 255)
    assert metadata["byte_length"] == len(result.data)
    assert metadata["sha256"] == __import__("hashlib").sha256(result.data).hexdigest()
    assert result.png == result.data
    json.dumps(metadata, allow_nan=False)


def test_grid_is_deterministic_for_identical_bounds():
    first = test_pattern.generate_grid(bounds())
    second = test_pattern.generate_grid(bounds())
    assert first.data == second.data
    assert first.metadata == second.metadata


def test_grid_preserves_wall_aspect_and_anchors_at_the_supplied_negative_origin():
    result = test_pattern.generate_grid(bounds())
    metadata = result.metadata
    assert metadata["bounds_mm"] == bounds()
    assert metadata["origin_mm"] == [-125.0, -75.0]
    assert metadata["negative_bounds"] is True
    assert metadata["aspect"]["preserved"] is True
    assert metadata["aspect"]["deviation"] < 0.02
    assert metadata["pixels_per_mm"] == pytest.approx(
        metadata["width"] / bounds()["width"], rel=1e-3
    )


def test_grid_uses_50mm_ticks_and_absolute_coordinate_labels():
    result = test_pattern.generate_grid(bounds())
    grid = result.metadata["grid"]
    assert grid["interval_mm"] == 50.0
    assert grid["x_ticks_mm"] == [-100.0, -50.0, 0.0, 50.0, 100.0, 150.0, 200.0]
    assert grid["y_ticks_mm"] == [-50.0, 0.0, 50.0, 100.0, 150.0, 200.0]
    assert grid["vertical_lines"] == 7
    assert grid["horizontal_lines"] == 6
    assert grid["total_lines"] == 13
    assert grid["x_labels_mm"]
    assert grid["y_labels_mm"]
    assert grid["x_labels_mm"][0] == -100.0
    assert grid["y_labels_mm"][0] == -50.0
    assert grid["label_interval_mm"]["x"] == 50.0
    assert grid["label_interval_mm"]["y"] == 50.0
    assert grid["label_count"] == len(grid["x_labels_mm"]) + len(grid["y_labels_mm"])
    assert set(grid["x_labels_mm"]) <= set(grid["x_ticks_mm"])
    assert set(grid["y_labels_mm"]) <= set(grid["y_ticks_mm"])


def test_grid_draws_selected_lines_at_the_negative_origin_coordinates():
    result = test_pattern.generate_grid(bounds())
    metadata = result.metadata
    scale = metadata["pixels_per_mm"]
    x0 = bounds()["x"]
    y0 = bounds()["y"]
    px_width = metadata["width"]
    px_height = metadata["height"]
    probe_y = px_height // 5
    probe_x = px_width // 5

    # 0 mm is a major x line; -100 mm is a minor x line.
    major_x = round((0.0 - x0) * scale)
    minor_x = round((-100.0 - x0) * scale)
    assert pixel_at(result, major_x, probe_y) == MAJOR_LINE
    assert pixel_at(result, minor_x, probe_y) == MINOR_LINE

    # 0 mm is a major y line; -50 mm is a minor y line.
    major_y = round((0.0 - y0) * scale)
    minor_y = round((-50.0 - y0) * scale)
    assert pixel_at(result, probe_x, major_y) == MAJOR_LINE
    assert pixel_at(result, probe_x, minor_y) == MINOR_LINE


def test_grid_has_four_corner_orientation_markers_at_drawn_pixels():
    result = test_pattern.generate_grid(bounds())
    metadata = result.metadata
    markers = metadata["grid"]["corner_markers"]
    assert [marker["label"] for marker in markers] == ["TL", "TR", "BR", "BL"]
    assert metadata["grid"]["cross_axis"] is True
    image = decode(result)
    for marker in markers:
        left, top, right, bottom = marker["box_px"]
        assert 0 <= left < right <= image.width
        assert 0 <= top < bottom <= image.height
        assert image.getpixel((left + 1, top + 1)) == tuple(marker["color"])
    assert metadata["grid"]["shape_target_mm"] > 0
    assert metadata["grid"]["scale_bar_mm"] > 0
    assert metadata["grid"]["scale_bar_px"] > 0


def test_grid_metadata_states_mm_are_intended_not_an_accuracy_claim():
    result = test_pattern.generate_grid(bounds())
    metadata = result.metadata
    assert metadata["accuracy_claimed"] is False
    assert "intended coordinates" in metadata["note"]
    assert "does not" in metadata["note"]
    assert metadata["provenance"]["interval_mm"] == 50.0


def test_grid_rejects_bool_nonfinite_and_missing_bounds():
    invalid = [
        {"x": 0, "y": 0, "width": True, "height": 100},
        {"x": 0, "y": 0, "width": 100, "height": False},
        {"x": float("nan"), "y": 0, "width": 100, "height": 100},
        {"x": 0, "y": float("inf"), "width": 100, "height": 100},
        {"x": 0, "y": 0, "width": 100},
    ]
    for value in invalid:
        with pytest.raises(test_pattern.PatternError):
            test_pattern.generate_grid(value)


def test_grid_rejects_absurd_or_degenerate_wall_bounds():
    for value in (
        {"x": 0, "y": 0, "width": 0, "height": 100},
        {"x": 0, "y": 0, "width": -100, "height": 100},
        {"x": 0, "y": 0, "width": 49, "height": 100},
        {"x": 0, "y": 0, "width": 100, "height": 49},
        {"x": 0, "y": 0, "width": 10_001, "height": 100},
        {"x": 0, "y": 0, "width": 10_000, "height": 50},
    ):
        with pytest.raises(test_pattern.PatternError):
            test_pattern.generate_grid(value)


def test_grid_pixel_budget_bounds_a_large_square_wall():
    result = test_pattern.generate_grid({"x": 0, "y": 0, "width": 10_000, "height": 10_000})
    metadata = result.metadata
    assert metadata["width"] <= test_pattern.MAX_EDGE_PX
    assert metadata["height"] <= test_pattern.MAX_EDGE_PX
    assert metadata["width"] * metadata["height"] <= test_pattern.MAX_PIXELS
    assert metadata["width"] == metadata["height"]
    assert metadata["grid"]["interval_mm"] == 50.0


def test_grid_rejects_an_unbounded_tick_count(monkeypatch):
    monkeypatch.setattr(test_pattern, "MAX_AXIS_TICKS", 10)
    with pytest.raises(test_pattern.PatternError):
        test_pattern.generate_grid({"x": 0, "y": 0, "width": 1_000, "height": 1_000})


def test_grid_does_not_mutate_supplied_bounds():
    supplied = bounds()
    original = copy.deepcopy(supplied)
    result = test_pattern.generate_grid(supplied)
    assert supplied == original
    assert result.metadata["bounds_mm"] == original


def test_black_is_a_small_opaque_ordinary_png():
    result = test_pattern.generate_test_pattern("black")
    metadata = result.metadata
    image = decode(result)
    assert image.format == "PNG"
    assert image.mode == "RGB"
    assert image.size == (test_pattern.BLACK_SIZE_PX, test_pattern.BLACK_SIZE_PX)
    assert image.getextrema() == ((0, 0), (0, 0), (0, 0))
    assert image.convert("RGBA").getextrema()[3] == (255, 255)
    assert result.data[25] == 2
    assert metadata["pattern"] == "black"
    assert metadata["opaque"] is True
    assert metadata["width"] == metadata["height"] == test_pattern.BLACK_SIZE_PX
    assert metadata["byte_length"] == len(result.data)
    assert metadata["byte_length"] < 2_000
    assert metadata["purpose"] == "Blank wall"
    assert metadata["accuracy_claimed"] is False
    assert test_pattern.generate_black().data == result.data
    json.dumps(metadata, allow_nan=False)


def test_pattern_dispatch_rejects_unknown_pattern_and_missing_grid_bounds():
    with pytest.raises(test_pattern.PatternError):
        test_pattern.generate_test_pattern("colour")
    with pytest.raises(test_pattern.PatternError):
        test_pattern.generate_test_pattern("grid")
    black = test_pattern.generate_test_pattern("black", bounds={"invalid": True})
    assert black.metadata["pattern"] == "black"
