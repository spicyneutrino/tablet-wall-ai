"""Atomic layout replacement and safe return points in both unit systems."""

from copy import deepcopy

import pytest

import main
from tabletwall import displays, persist

DEVICE = "0f8fad5b-d9cb-469f-a165-70867728950e"


def fixtures(client):
    client.post("/devices/register", json={
        "device_id": DEVICE, "width": 768, "height": 1024, "device_type": "ipad",
    }).raise_for_status()
    client.put(f"/devices/{DEVICE}/placement", json={
        "x": 0, "y": 0, "w": 100, "h": 200,
    }).raise_for_status()
    logical = deepcopy(main.wall["layout"])
    profile = displays.save_profile(
        DEVICE, active_width_mm=100, active_height_mm=200,
        bezels={"left": 5, "right": 5, "top": 5, "bottom": 5},
        panel_pixels=None, label="test tablet", provenance="fixture",
    )
    calibration = displays.save_calibration(
        DEVICE, profile_revision=profile["revision"], viewport_width=768,
        viewport_height=1024, dpr=2, orientation=0, mode="fullscreen",
        quarter_turn=0, panel_offset_mm=(0, 0), mm_per_css=(100 / 768, 200 / 1024),
        anchor_edge="top-left", uncertainty_mm=1, method="fixture",
    )
    physical = {
        "kind": "physical", "bounds": {"x": 0, "y": 0, "width": 110, "height": 210},
        "slots": {DEVICE: {
            "center_x_mm": 55, "center_y_mm": 105, "mount_angle": 0,
            "nudge_x_mm": 0, "nudge_y_mm": 0, "participating": True,
            "profile_revision": profile["revision"],
            "calibration_revision": calibration["revision"],
        }},
    }
    return logical, physical


def apply_physical(client, layout):
    return client.put("/api/v3/layout", json={k: v for k, v in layout.items() if k != "kind"},
                      headers={"If-Match": client.get("/api/v3/config").json()["etag"]})


@pytest.mark.parametrize("target_kind, action", [
    ("physical", "apply"), ("physical", "recall"),
    ("logical", "apply"), ("logical", "recall"),
])
def test_every_cross_kind_replacement_saves_the_previous_layout(client, target_kind, action):
    logical, physical = fixtures(client)
    if target_kind == "logical":
        apply_physical(client, physical).raise_for_status()
    target = physical if target_kind == "physical" else logical
    persist.save_layout("Target", target)
    before = deepcopy(main.wall)
    headers = {"If-Match": client.get("/api/v3/config").json()["etag"]}
    if action == "apply":
        url = "/api/v3/layout" if target_kind == "physical" else "/api/v3/logical-layout"
        response = client.put(url, json={k: v for k, v in target.items() if k != "kind"}, headers=headers)
    else:
        prefix = "layouts" if target_kind == "physical" else "logical-layouts"
        response = client.post(f"/api/v3/{prefix}/Target/recall", headers=headers)
    assert response.status_code == 200, response.text
    saved_name = response.json().get("previous_layout_saved")
    assert saved_name and saved_name.startswith(f"Before {target_kind} ")
    assert persist.load_layout(saved_name) == before["layout"]
    assert main.wall["revision"] == before["revision"] + 1
    assert main.wall["scene"] == before["scene"]
    assert main.wall["layout"].get("kind", "logical") == target_kind


@pytest.mark.parametrize("failure", ["snapshot", "wall"])
def test_cross_kind_replacement_rolls_back_late_writes(client, monkeypatch, failure):
    logical, physical = fixtures(client)
    apply_physical(client, physical).raise_for_status()
    persist.save_layout("Return", logical)
    before = deepcopy(main.wall)
    saved = persist.load_layouts()
    notifications = []

    async def notified():
        notifications.append(True)

    monkeypatch.setattr(main, "_broadcast_wall", notified)
    function = "save_layout" if failure == "snapshot" else "save_state"
    original = getattr(main, function)

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("late write failure")

    monkeypatch.setattr(main, function, fail)
    headers = {"If-Match": client.get("/api/v3/config").json()["etag"]}
    with pytest.raises(RuntimeError, match="late write failure"):
        client.post("/api/v3/logical-layouts/Return/recall", headers=headers)
    assert main.wall == before
    assert persist.load_state() == before
    assert persist.load_layouts() == saved
    assert notifications == []


def test_empty_default_physical_apply_cannot_erase_a_populated_wall(client):
    fixtures(client)
    before = deepcopy(main.wall)
    response = apply_physical(client, {
        "bounds": {"x": 0, "y": 0, "width": 100, "height": 100}, "slots": {},
    })
    assert response.status_code == 409
    assert main.wall == before
    assert persist.load_layouts() == []


def test_clear_is_an_explicit_same_kind_command(client):
    fixtures(client)
    before = deepcopy(main.wall)
    headers = {"If-Match": client.get("/api/v3/config").json()["etag"]}
    for body in ({"confirm": False}, {"confirm": 1}, {"confirm": True, "other": 1}):
        assert client.post("/api/v3/layout/clear", json=body, headers=headers).status_code == 422
        assert main.wall == before
    response = client.post("/api/v3/layout/clear", json={"confirm": True}, headers=headers)
    assert response.status_code == 200, response.text
    assert main.wall["layout"] == {**before["layout"], "placements": {}}
    assert main.wall["scene"] == before["scene"]
    assert main.wall["revision"] == before["revision"] + 1


def test_damaged_physical_recall_is_refused_before_commit(client):
    _, physical = fixtures(client)
    physical["slots"][DEVICE]["profile_revision"] = 999
    persist.save_layout("Damaged", physical)
    before = deepcopy(main.wall)
    response = client.post("/api/v3/layouts/Damaged/recall", headers={
        "If-Match": client.get("/api/v3/config").json()["etag"],
    })
    assert response.status_code == 422
    assert main.wall == before


@pytest.mark.parametrize("invalid", ["boolean_revision", "boolean_bound", "unknown_slot", "nonfinite"])
def test_physical_replacement_validates_every_slot_before_writing(client, invalid):
    import json

    _, physical = fixtures(client)
    if invalid == "boolean_revision":
        physical["slots"][DEVICE]["profile_revision"] = True
    elif invalid == "boolean_bound":
        physical["bounds"]["width"] = True
    elif invalid == "unknown_slot":
        physical["slots"][DEVICE]["unknown"] = 1
    else:
        physical["bounds"]["x"] = float("nan")
    before = deepcopy(main.wall)
    response = client.put("/api/v3/layout", content=json.dumps({
        key: value for key, value in physical.items() if key != "kind"
    }), headers={"If-Match": client.get("/api/v3/config").json()["etag"],
                 "Content-Type": "application/json"})
    assert response.status_code == 422
    assert main.wall == before
    assert persist.load_layouts() == []


def test_safety_copy_name_collision_refuses_the_switch(client, monkeypatch):
    from types import SimpleNamespace

    _, physical = fixtures(client)
    before = deepcopy(main.wall)
    name = "Before physical " + "a" * 12
    persist.save_layout(name, before["layout"])
    monkeypatch.setattr(main.uuid, "uuid4", lambda: SimpleNamespace(hex="a" * 32))
    response = apply_physical(client, physical)
    assert response.status_code == 409
    assert main.wall == before
    assert persist.load_layouts() == [(name, before["layout"])]
