from copy import deepcopy

import main
import pytest
from tabletwall import assets, displays, persist, tablet_models
from tabletwall.state import _render_frame

DEVICE = "ad9d08f6-80e9-453e-8961-33e2de09f93c"


@pytest.mark.parametrize("orientation,width,height,quarter", [
    (270, 900, 1280, 0), (0, 1280, 900, 3),
    (90, 900, 1280, 2), (180, 1280, 900, 1),
])
def test_google_native_landscape_keeps_the_measured_portrait_panel(client, orientation, width, height, quarter):
    assert register(client, screen_width=1280, screen_height=900, device_type="android",
                    platform_family="android").status_code == 200
    assignment = tablet_models.assignments()[DEVICE]
    calibration = displays.calibration(DEVICE, assignment["calibration_revision"])
    effective = tablet_models.effective(DEVICE, calibration, {
        "width": width, "height": height, "dpr": 2, "orientation": orientation, "mode": "fullscreen",
    })
    assert effective["viewport_width"] == width
    assert effective["viewport_height"] == height
    assert effective["orientation"] == orientation
    assert effective["quarter_turn"] == quarter
    assert effective["mm_per_css"] == [.16195, .16195]


def register(client, **changes):
    data = {"device_id": DEVICE, "width": 768, "height": 1024, "device_type": "ios",
            "screen_width": 768, "screen_height": 1024, "screen_dpr": 2, "platform_family": "ios"}
    data.update(changes)
    return client.post("/devices/register", json=data)


def test_recognition_override_and_persistence(client):
    assert register(client).status_code == 200
    config = client.get("/api/v3/config").json()
    assignment = config["tablet_assignments"][DEVICE]
    assert assignment["model_id"] == "ipad-air-2"
    assert assignment["profile_revision"] == 1
    assert config["calibrations"][0]["mm_per_css"] == [0.187725, 0.187725]
    assert register(client, screen_width=1024, screen_height=768).status_code == 200
    assert client.get("/api/v3/config").json()["displays"][0]["revision"] == 1
    url = f"/api/v3/tablet-assignments/{DEVICE}"
    assert client.put(url, json={"mode": "manual"}).status_code == 428
    response = client.put(url, json={"mode": "manual"}, headers={"If-Match": config["etag"]})
    assert response.status_code == 200
    assert register(client).status_code == 200
    assert tablet_models.assignments()[DEVICE] == {"mode": "manual", "model_id": None}
    config = client.get("/api/v3/config").json()
    response = client.put(url, json={"mode": "explicit", "model_id": "google-pixel-c"}, headers={"If-Match": config["etag"]})
    assert response.status_code == 200
    assert register(client).status_code == 200
    assert tablet_models.assignments()[DEVICE]["model_id"] == "google-pixel-c"


def test_unknown_and_ambiguous_stay_unknown(client, monkeypatch):
    assert register(client, screen_width=700).status_code == 200
    assert tablet_models.assignments()[DEVICE]["model_id"] is None
    monkeypatch.setitem(tablet_models.BUILTINS, "duplicate", deepcopy(tablet_models.BUILTINS["ipad-air-2"]))
    assert register(client).status_code == 200
    assert tablet_models.assignments()[DEVICE]["model_id"] is None


def test_rotation_matches_render_and_playback_and_keeps_revision_pin(client):
    assert register(client).status_code == 200
    assignment = tablet_models.assignments()[DEVICE]
    profile = displays.profile(DEVICE, assignment["profile_revision"])
    cal = displays.calibration(DEVICE, assignment["calibration_revision"])
    viewport = {"width": 1024, "height": 768, "dpr": 2, "orientation": 90, "mode": "fullscreen"}
    effective = tablet_models.effective(DEVICE, cal, viewport)
    assert effective["quarter_turn"] == 3
    assert effective["panel_offset_mm"] == [0, 0]
    slot = {"profile_revision": profile["revision"], "calibration_revision": cal["revision"],
            "center_x_mm": 90, "center_y_mm": 120, "nudge_x_mm": 0, "nudge_y_mm": 0,
            "mount_angle": 0, "participating": True}
    main.wall["layout"] = {"kind": "physical", "bounds": {"x": 0, "y": 0, "width": 180, "height": 240}, "slots": {DEVICE: slot}}
    main.wall["scene"]["content"] = {"type": "image", "intrinsicWidth": 1800, "intrinsicHeight": 2400, "fit": "cover"}
    record = {"viewport": viewport, "caps": ["image", "physical"]}
    frame = _render_frame(DEVICE, record, profile, effective)
    plan, playback_cal = main._physical_plan_for(DEVICE, record, 1800, 2400)
    assert frame["calibration"] == playback_cal
    assert frame["plan"] == plan
    tablet_models.assign(DEVICE, "explicit", "google-pixel-c")
    assert tablet_models.effective(DEVICE, cal, viewport) == effective
    assert main._physical_plan_for(DEVICE, record, 1800, 2400) == (plan, playback_cal)
    tablet_models.assign(DEVICE, "manual")
    assert main._physical_plan_for(DEVICE, record, 1800, 2400) == (plan, playback_cal)


def test_logical_wall_is_saved_and_can_be_restored(client):
    assert register(client).status_code == 200
    original = deepcopy(main.wall["layout"])
    assignment = tablet_models.assignments()[DEVICE]
    config = client.get("/api/v3/config").json()
    slot = {"profile_revision": assignment["profile_revision"], "calibration_revision": assignment["calibration_revision"],
            "center_x_mm": 90, "center_y_mm": 120, "nudge_x_mm": 0, "nudge_y_mm": 0,
            "mount_angle": 0, "participating": True}
    response = client.put("/api/v3/layout", headers={"If-Match": config["etag"]},
        json={"bounds": {"x": 0, "y": 0, "width": 180, "height": 240}, "slots": {DEVICE: slot}})
    assert response.status_code == 200
    name = response.json()["previous_layout_saved"]
    assert any(item["name"] == name for item in client.get("/api/v3/logical-layouts").json()["layouts"])
    response = client.post(f"/api/v3/logical-layouts/{name}/recall", headers={"If-Match": response.json()["etag"]})
    assert response.status_code == 200
    assert main.wall["layout"] == original
    response = client.delete(f"/api/v3/layouts/{name}", headers={"If-Match": response.json()["etag"]})
    assert response.status_code == 200
    assert not any(item["name"] == name for item in client.get("/api/v3/logical-layouts").json()["layouts"])


def test_offline_assignment_survives_reconnect_without_screen_telemetry(client):
    config = client.get("/api/v3/config").json()
    response = client.put(f"/api/v3/tablet-assignments/{DEVICE}", headers={"If-Match": config["etag"]},
                          json={"mode": "explicit", "model_id": "ipad-air-2"})
    assert response.status_code == 200
    original = tablet_models.assignments()[DEVICE]
    main.devices.clear()
    assert client.post("/devices/register", json={"device_id": DEVICE, "width": 768,
                       "height": 1024, "device_type": "ios"}).status_code == 200
    assert tablet_models.assignments()[DEVICE] == original
    assert displays.latest_profile(DEVICE)["revision"] == original["profile_revision"]


def test_turning_tablet_refreshes_pending_slideshow_mapping(client, asset_dir, monkeypatch):
    from PIL import Image

    monkeypatch.setenv("TABLET_WALL_ASSET_DIR", str(asset_dir))
    Image.new("RGB", (240, 320), "navy").save(asset_dir / "slide.png")
    asset = assets.list_assets()[0]["id"]
    assert register(client).status_code == 200
    assignment = tablet_models.assignments()[DEVICE]
    main.wall["layout"] = {
        "kind": "physical", "bounds": {"x": 0, "y": 0, "width": 180, "height": 240},
        "slots": {DEVICE: {
            "profile_revision": assignment["profile_revision"], "calibration_revision": assignment["calibration_revision"],
            "center_x_mm": 90, "center_y_mm": 120, "mount_angle": 0,
            "nudge_x_mm": 0, "nudge_y_mm": 0, "participating": True,
        }},
    }
    persist.save_meta("playlist", {"items": [{"asset": asset, "dwell_ms": 5000}], "loop": True, "revision": 1})

    def receive_prepare(socket):
        while True:
            frame = socket.receive_json()
            if frame["type"] == "prepare":
                return frame

    url = f"/ws/device?device_id={DEVICE}&protocol=3&caps=calibration,image,physical&w=768&h=1024&dpr=2&orientation=0&mode=fullscreen"
    with client.websocket_connect(url) as socket:
        client.post("/api/v3/playback/start", json={"policy": "strict"}).raise_for_status()
        before = receive_prepare(socket)
        session = main._playback_session
        for width in (700, 768):
            newcomer = {"device_id": "11111111-1111-4111-8111-111111111111",
                        "width": width, "height": 1024, "device_type": "ios",
                        "screen_width": width, "screen_height": 1024,
                        "screen_dpr": 2, "platform_family": "ios"}
            client.post("/devices/register", json=newcomer).raise_for_status()
            assert main._playback_session is session
        socket.send_json({"type": "viewport", "viewport": {
            "width": 1024, "height": 768, "dpr": 2, "orientation": 90, "mode": "fullscreen",
        }})
        after = receive_prepare(socket)
        assert after["preparation_id"] == before["preparation_id"]
        assert after["calibration"]["orientation"] == 90
        assert after["calibration"]["viewport_width"] == 1024
        assert after["calibration"]["quarter_turn"] == 3
        assert after["calibration"]["mm_per_css"] == [.187725, .187725]


@pytest.mark.parametrize("resource", ["displays", "calibrations"])
def test_manual_measurement_and_assignment_roll_back_together(client, monkeypatch, resource):
    register(client).raise_for_status()
    before = client.get("/api/v3/config").json()
    history = persist.load_meta("tablet_model_calibrations")
    if resource == "displays":
        body = {key: before["displays"][0][key] for key in (
            "active_width_mm", "active_height_mm", "bezels", "label", "provenance")}
        body["active_width_mm"] += 1
    else:
        body = {key: value for key, value in before["calibrations"][0].items()
                if key not in ("device_id", "revision", "created_at")}
        body["method"] = "manual test"
    original_assign = tablet_models.assign

    def failed_assignment(*args):
        original_assign(*args)
        raise RuntimeError("assignment write failed")

    monkeypatch.setattr(tablet_models, "assign", failed_assignment)
    with pytest.raises(RuntimeError, match="assignment write failed"):
        client.put(f"/api/v3/{resource}/{DEVICE}", headers={"If-Match": before["etag"]}, json=body)
    assert client.get("/api/v3/config").json() == before
    assert persist.load_meta("tablet_model_calibrations") == history


@pytest.mark.parametrize("failure", ["fit", "save"])
def test_failed_physical_apply_does_not_leave_a_logical_backup(client, monkeypatch, failure):
    register(client).raise_for_status()
    before = client.get("/api/v3/config").json()
    assignment = before["tablet_assignments"][DEVICE]
    body = {"bounds": {"x": 0, "y": 0, "width": 180, "height": 240},
            "slots": {DEVICE: {
                "profile_revision": assignment["profile_revision"],
                "calibration_revision": assignment["calibration_revision"],
                "center_x_mm": 90, "center_y_mm": 120, "mount_angle": 0,
                "nudge_x_mm": 0, "nudge_y_mm": 0, "participating": True,
            }}, "sizing": {"mode": "tablets", "padding": 0}}
    if failure == "fit":
        body["sizing"]["padding"] = 1e308
        assert client.put("/api/v3/layout", headers={"If-Match": before["etag"]}, json=body).status_code == 422
    else:
        original_save = main.save_state

        def failed_save(proposed):
            original_save(proposed)
            raise RuntimeError("wall write failed")

        monkeypatch.setattr(main, "save_state", failed_save)
        with pytest.raises(RuntimeError, match="wall write failed"):
            client.put("/api/v3/layout", headers={"If-Match": before["etag"]}, json=body)
    assert client.get("/api/v3/config").json() == before
    assert persist.load_layouts() == []
    assert persist.load_state()["layout"]["width"] == before["layout"]["width"]


@pytest.mark.parametrize("auto_detect_target", [False, True])
def test_rebind_keeps_model_rotation_and_existing_measurement_history(client, auto_detect_target):
    register(client).raise_for_status()
    config = client.get("/api/v3/config").json()
    assignment = config["tablet_assignments"][DEVICE]
    body = {"bounds": {"x": 0, "y": 0, "width": 180, "height": 240},
            "slots": {DEVICE: {
                "profile_revision": assignment["profile_revision"],
                "calibration_revision": assignment["calibration_revision"],
                "center_x_mm": 90, "center_y_mm": 120, "mount_angle": 0,
                "nudge_x_mm": 0, "nudge_y_mm": 0, "participating": True,
            }}}
    client.put("/api/v3/layout", headers={"If-Match": config["etag"]}, json=body).raise_for_status()
    target = "11111111-1111-4111-8111-111111111111"
    if auto_detect_target:
        register(client, device_id=target).raise_for_status()
    else:
        client.post("/devices/register", json={"device_id": target, "width": 1024,
                                             "height": 768, "device_type": "ios"}).raise_for_status()
    original_target_profile = displays.profile(target, 1)
    original_source_profile = displays.profile(DEVICE, 1)
    response = client.post(f"/devices/{target}/rebind", json={"replaces": DEVICE})
    assert response.status_code == 200, response.text
    config = client.get("/api/v3/config").json()
    slot = config["layout"]["slots"][target]
    expected_revision = 2 if auto_detect_target else 1
    assert slot["profile_revision"] == slot["calibration_revision"] == expected_revision
    assert displays.profile(DEVICE, 1) == original_source_profile
    if auto_detect_target:
        assert displays.profile(target, 1) == original_target_profile
    assert config["tablet_assignments"][target]["calibration_revision"] == expected_revision
    record = {"viewport": {"width": 1024, "height": 768, "dpr": 2,
                           "orientation": 90, "mode": "tab"}}
    plan, calibration = main._physical_plan_for(target, record, 1800, 2400)
    assert plan is not None
    assert calibration["quarter_turn"] == 3
    assert calibration["mm_per_css"] == [.187725, .187725]
    assert persist.load_state()["layout"]["slots"][target] == slot
