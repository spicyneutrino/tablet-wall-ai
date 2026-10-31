"""Wall sizing mode behavior for logical and measured physical layouts."""

import uuid

import pytest

import main
from tabletwall import displays, persist, sizing


def placement(x, y, w, h):
    return {
        "device_id": str(uuid.uuid4()), "x": x, "y": y, "w": w, "h": h,
        "bezel": {"top": 1, "right": 2, "bottom": 3, "left": 4},
    }


def test_logical_fit_moves_negative_placements_and_includes_reservations():
    layout = {
        "width": 99, "height": 88, "sizing": {"mode": "tablets", "padding": 5},
        "placements": {
            "a": placement(-20, -7, 20, 30),
            "b": placement(4, 10, 40, 10),
        },
    }
    sizing.fit_logical(layout)
    assert (layout["width"], layout["height"]) == (74, 40)
    assert [(p["x"], p["y"]) for p in layout["placements"].values()] == [(5, 5), (29, 22)]


def test_logical_fixed_keeps_dimensions_and_empty_fit_keeps_prior_size():
    fixed = {"width": 123, "height": 456, "placements": {"a": placement(-5, -2, 4, 3)}}
    sizing.fit_logical(fixed)
    assert (fixed["width"], fixed["height"], fixed["placements"]["a"]["x"]) == (123, 456, -5)
    empty = {"width": 123, "height": 456, "sizing": {"mode": "tablets", "padding": 0}, "placements": {}}
    sizing.fit_logical(empty)
    assert (empty["width"], empty["height"]) == (123, 456)


def test_wall_put_fit_mode_and_pack_mixed_sizes(client):
    a, b, c = placement(40, 10, 20, 10), placement(0, 0, 30, 20), placement(5, 30, 10, 25)
    main.wall["layout"]["placements"] = {a["device_id"]: a, b["device_id"]: b, c["device_id"]: c}
    switched = client.put("/wall", json={"sizing": {"mode": "tablets", "padding": 2}})
    assert switched.status_code == 200
    assert switched.json()["sizing"] == {"mode": "tablets", "padding": 2}
    assert client.post("/wall/auto").status_code == 409
    assert client.put("/wall", json={"width": 500}).status_code == 409
    packed = client.post("/wall/pack", json={"columns": 2, "gap": 3})
    assert packed.status_code == 200
    state = packed.json()
    ps = state["placements"]
    # Existing visual order is b, a, c. Row two begins after the tallest first row.
    assert (ps[b["device_id"]]["x"], ps[b["device_id"]]["y"]) == (2, 2)
    assert (ps[a["device_id"]]["x"], ps[a["device_id"]]["y"]) == (35, 2)
    assert (ps[c["device_id"]]["x"], ps[c["device_id"]]["y"]) == (2, 25)
    assert (state["width"], state["height"]) == (57, 52)
    assert client.put("/wall", json={"width": 80, "sizing": {"mode": "fixed"}}).status_code == 200
    assert client.get("/wall").json()["width"] == 80


def test_logical_sizing_validation_and_legacy_snapshot_recall(client):
    assert client.put("/wall", json={"sizing": {"mode": "tablets", "padding": 0.5}}).status_code == 422
    assert client.put("/wall", json={"sizing": {"mode": "tablets", "padding": -1}}).status_code == 422
    assert client.post("/wall/pack", json={}).status_code == 409
    assert client.put("/wall", json={"sizing": {"mode": "tablets"}}).status_code == 200
    assert client.post("/wall/pack", json={}).status_code == 422
    assert client.post("/wall/pack", json={"columns": 1.5}).status_code == 422
    legacy = {"width": 90, "height": 70, "placements": {}}
    assert main._valid_saved_layout(legacy)
    main.wall["layout"]["sizing"] = {"mode": "tablets", "padding": 1}
    assert persist.save_layout("legacy", legacy)
    recalled = client.post("/layouts/legacy/recall")
    assert recalled.status_code == 200
    assert "sizing" not in recalled.json()
    assert persist.load_state()["layout"] == legacy


def test_physical_fit_uses_rotated_body_nudge_and_persists_mode(client):
    device_id = str(uuid.uuid4())
    profile = displays.save_profile(
        device_id, active_width_mm=100, active_height_mm=60,
        bezels={"left": 10, "top": 5, "right": 20, "bottom": 15},
        panel_pixels=None, label="test", provenance="fixture",
    )
    calibration = displays.save_calibration(
        device_id, profile_revision=profile["revision"], viewport_width=600,
        viewport_height=800, dpr=1, orientation=0, mode="fullscreen",
        quarter_turn=0, panel_offset_mm=(0, 0), mm_per_css=(0.1, 0.1),
        anchor_edge="top-left", uncertainty_mm=0, method="fixture",
    )
    body = {
        "bounds": {"x": 0, "y": 0, "width": 400, "height": 300},
        "slots": {device_id: {
            "center_x_mm": 200, "center_y_mm": 100, "mount_angle": 90,
            "nudge_x_mm": 7, "nudge_y_mm": -4,
            "profile_revision": profile["revision"], "calibration_revision": calibration["revision"],
            "participating": False,
        }},
        "sizing": {"mode": "tablets", "padding": 10},
    }
    config = client.get("/api/v3/config").json()
    response = client.put("/api/v3/layout", json=body, headers={"If-Match": config["etag"]})
    assert response.status_code == 200, response.text
    bounds = response.json()["layout"]["bounds"]
    # At 90 degrees the 130x80 body occupies 80x130 around center+(7,-4).
    assert bounds == {"x": 157, "y": 21, "width": 100, "height": 150}
    assert response.json()["layout"]["sizing"] == body["sizing"]
    assert persist.load_state()["layout"]["sizing"] == body["sizing"]

    before = client.get("/api/v3/config").json()
    body["sizing"]["padding"] = 1e308
    rejected = client.put("/api/v3/layout", json=body, headers={"If-Match": before["etag"]})
    assert rejected.status_code == 422
    assert "finite" in rejected.json()["detail"]
    assert client.get("/api/v3/config").json() == before
    assert persist.load_state()["layout"]["sizing"]["padding"] == 10

    body.pop("sizing")
    updated = client.put("/api/v3/layout", json=body, headers={"If-Match": before["etag"]})
    assert updated.status_code == 200
    assert updated.json()["layout"]["sizing"] == {"mode": "tablets", "padding": 10}

    displays.save_profile(
        device_id, active_width_mm=200, active_height_mm=120,
        bezels={"left": 0, "top": 0, "right": 0, "bottom": 0},
        panel_pixels=None, label="new measurement", provenance="fixture",
    )
    historical = client.get("/api/v3/config").json()
    assert historical["displays"][0]["revision"] == 2
    assert historical["referenced_displays"][0]["revision"] == 1
    assert historical["referenced_displays"][0]["active_width_mm"] == 100
    assert historical["referenced_calibrations"][0]["revision"] == calibration["revision"]


def test_physical_tablet_fit_rejects_missing_profile_before_commit():
    layout = {
        "kind": "physical", "bounds": {"x": 1, "y": 2, "width": 3, "height": 4},
        "sizing": {"mode": "tablets", "padding": 0},
        "slots": {str(uuid.uuid4()): {
            "center_x_mm": 0, "center_y_mm": 0, "mount_angle": 0,
            "nudge_x_mm": 0, "nudge_y_mm": 0, "profile_revision": 1,
        }},
    }
    with pytest.raises(ValueError, match="profile"):
        sizing.fit_physical(layout, lambda _device_id, _revision: None)


def test_invalid_physical_profile_reference_does_not_commit(client):
    device_id = str(uuid.uuid4())
    before = client.get("/api/v3/config").json()
    body = {
        "bounds": {"x": 1, "y": 2, "width": 30, "height": 40},
        "slots": {device_id: {
            "center_x_mm": 10, "center_y_mm": 20, "mount_angle": 0,
            "nudge_x_mm": 0, "nudge_y_mm": 0,
            "profile_revision": 99, "calibration_revision": 99,
        }},
        "sizing": {"mode": "tablets", "padding": 0},
    }
    response = client.put("/api/v3/layout", json=body, headers={"If-Match": before["etag"]})
    assert response.status_code == 422
    after = client.get("/api/v3/config").json()
    assert after["revision"] == before["revision"]
    assert after["layout"] == before["layout"]
