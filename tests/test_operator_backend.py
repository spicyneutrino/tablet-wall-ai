"""Operator composition contracts through HTTP and owned device sockets."""
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

import main
from tabletwall import assets, displays, persist, render_status, tablet_models

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
C = "33333333-3333-4333-8333-333333333333"
VP = {"width": 600, "height": 800, "dpr": 1, "orientation": 0,
      "mode": "fullscreen", "visual_scale": 1}
CAPS = "image,physical,render_ack,identify,image_contain,calibration"


def test_mounted_readiness_health_and_qr_use_live_wall(client, monkeypatch):
    from tabletwall import media
    monkeypatch.setattr(media, "_loopback_peer", lambda _request: True)
    monkeypatch.delenv(media.OPERATOR_CREDENTIAL_ENV, raising=False)
    monkeypatch.setenv("TABLET_WALL_TABLET_ORIGIN", "http://10.42.0.1:8080")
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["revision"] == main.wall["revision"]
    readiness = client.get("/api/v3/readiness")
    assert readiness.status_code == 200
    assert readiness.json()["tablet_url"] == "http://10.42.0.1:8080/client/"
    qr = client.get("/api/v3/join-qr")
    assert qr.status_code == 200 and qr.headers["content-type"] == "image/png"
    for response in (health, readiness, qr, client.get("/controller/physical.html")):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "script-src 'self'" in response.headers["content-security-policy"]
    monkeypatch.setattr(media, "_loopback_peer", lambda _request: False)
    for path in ("/healthz", "/api/v3/readiness", "/api/v3/join-qr"):
        response = client.get(path)
        assert response.status_code == 403
        assert response.headers["x-frame-options"] == "DENY"


def config(client):
    return client.get("/api/v3/config").json()


def headers(client):
    return {"If-Match": config(client)["etag"]}


def register(client, key=A, **fields):
    response = client.post("/devices/register", json={"device_id": key, "width": 600,
        "height": 800, "device_type": "test", **fields})
    response.raise_for_status()
    return response


def logical(client, ids=(A,), width=600):
    body = {"width": width * len(ids), "height": 800, "placements": {key: {
        "device_id": key, "x": index * width, "y": 0, "w": width, "h": 800,
        "bezel": dict(left=0, right=0, top=0, bottom=0)} for index, key in enumerate(ids)},
        "sizing": {"mode": "fixed", "padding": 0}}
    response = client.put("/api/v3/logical-layout", headers=headers(client), json=body)
    response.raise_for_status()
    return response.json()


def image_scene(client, asset_dir, *, fit="cover", background=None):
    Image.new("RGB", (1200, 800), "navy").save(asset_dir / "image.png")
    asset = assets.list_assets()[0]["id"]
    content = {"type": "image", "asset": asset, "fit": fit}
    if background is not None:
        content["background"] = background
    response = client.put("/api/v3/scene", headers=headers(client), json={"content": content})
    response.raise_for_status()
    return response.json()


def url(key=A, caps=CAPS, **changes):
    viewport = {**VP, **changes}
    params = {"device_id": key, "protocol": 3, "caps": caps, "w": viewport["width"],
        "h": viewport["height"], **{key: viewport[key] for key in ("dpr", "orientation", "mode", "visual_scale")}}
    return "/ws/device?" + "&".join(f"{key}={value}" for key, value in params.items())


def receive(socket, kind):
    for _ in range(30):
        frame = socket.receive_json()
        if frame["type"] == kind:
            return frame
    raise AssertionError(f"No {kind} frame")


def barrier(socket):
    socket.send_json({"type": "clock_sample", "id": "barrier", "c0": 1})
    receive(socket, "clock_sample")


def ack(socket, frame, seq=1, **changes):
    report = {"type": "render_ack", "token": frame["token"], "report_seq": seq,
        "status": "displayed", "reason": None, "viewport": VP, "visible": True, **changes}
    socket.send_json(report)
    barrier(socket)


def status(client, key=A):
    return config(client)["runtime"]["devices"][key]


def measurements(key=A, revision=1):
    profile = displays.save_profile(key, active_width_mm=120, active_height_mm=160,
        bezels=dict(left=5, right=5, top=5, bottom=5), provenance="ruler", panel_pixels=None, label="Measured panel")
    calibration = displays.save_calibration(key, profile_revision=profile["revision"],
        viewport_width=600, viewport_height=800, dpr=1, orientation=0, mode="fullscreen",
        quarter_turn=0, panel_offset_mm=(0, 0), mm_per_css=(.2, .2), method="ruler", uncertainty_mm=1, anchor_edge="top-left")
    return profile, calibration


def physical(client, key=A, revision=1):
    response = client.put("/api/v3/layout", headers=headers(client), json={
        "bounds": {"x": -65, "y": -85, "width": 130, "height": 170}, "slots": {key: {
            "center_x_mm": 0, "center_y_mm": 0, "mount_angle": 0, "nudge_x_mm": 0,
            "nudge_y_mm": 0, "profile_revision": revision, "calibration_revision": revision,
            "participating": True}}})
    response.raise_for_status()
    return response.json()


def test_runtime_does_not_change_durable_etag_or_issue_instructions(client, asset_dir):
    register(client)
    logical(client)
    image_scene(client, asset_dir)
    before = config(client)
    with client.websocket_connect(url()) as socket:
        welcome = receive(socket, "welcome")
        frame = receive(socket, "render")
        assert frame["token"]["connection_id"] == welcome["connection_id"]
        assert frame["type"] == "render" and frame["mode"] == "logical"
        seq = main.devices[A]["render_seq"]
        for _ in range(3):
            assert config(client)["etag"] == before["etag"]
            assert main.devices[A]["render_seq"] == seq
        ack(socket, frame)
        assert status(client)["render"]["current"] is True
        assert config(client)["etag"] == before["etag"]
        socket.send_json({"type": "viewport", "viewport": {**VP, "width": 599}})
        changed = receive(socket, "render")
        assert changed["revision"] == frame["revision"]
        assert changed["token"]["mapping_revision"] != frame["token"]["mapping_revision"]
        assert config(client)["etag"] == before["etag"]
    assert render_status.registry._evidence == {}


@pytest.mark.parametrize("field,value", [("connection_id", "other"), ("generation", "other"),
    ("revision", 0), ("render_seq", 999), ("mapping_revision", "wrong"), ("asset", "sha256:" + "f" * 64)])
def test_stale_or_inexact_tokens_cannot_confirm(client, asset_dir, field, value):
    register(client)
    logical(client)
    image_scene(client, asset_dir)
    with client.websocket_connect(url()) as socket:
        frame = receive(socket, "render")
        bad = {**frame["token"], field: value}
        ack(socket, frame, token=bad)
        assert status(client)["render"]["current"] is False
        ack(socket, frame, seq=2)
        assert status(client)["render"]["current"] is True


def test_retry_sequence_visibility_and_raw_report_bounds(client, asset_dir):
    register(client)
    logical(client)
    image_scene(client, asset_dir)
    with client.websocket_connect(url()) as socket:
        first = receive(socket, "render")
        ack(socket, first, seq=8)
        assert status(client)["render"]["current"]
        revision = config(client)["revision"]
        client.post(f"/api/v3/devices/{A}/retry-image", headers=headers(client)).raise_for_status()
        second = receive(socket, "render")
        assert second["token"] != first["token"] and second["revision"] == revision
        assert not status(client)["render"]["current"]
        ack(socket, second, seq=8)
        assert not status(client)["render"]["current"]
        ack(socket, second, seq=9, visible=False)
        assert not status(client)["render"]["current"]
        ack(socket, second, seq=10, padding="x" * 5000)
        assert not status(client)["render"]["current"]
        ack(socket, second, seq=11)
        assert status(client)["render"]["current"]
        ack(socket, second, seq=10, status="failed", reason="decode")
        assert status(client)["render"]["current"]


def test_takeover_and_zoom_fences(client, asset_dir):
    register(client)
    logical(client)
    image_scene(client, asset_dir)
    with client.websocket_connect(url()) as old:
        old_frame = receive(old, "render")
        with client.websocket_connect(url()) as new:
            frame = receive(new, "render")
            assert frame["token"]["connection_id"] != old_frame["token"]["connection_id"]
            ack(new, frame, token=old_frame["token"])
            assert not status(client)["render"]["current"]
            ack(new, frame, seq=2)
            assert status(client)["render"]["current"]
            new.send_json({"type": "viewport", "viewport": {**VP, "visual_scale": 2}})
            zoomed = receive(new, "render")
            assert status(client)["mapping"]["state"] == "zoom_changed"
            ack(new, zoomed, seq=3, viewport={**VP, "visual_scale": 2})
            assert not status(client)["render"]["current"]


@pytest.mark.parametrize("physical_kind", [False, True])
def test_contain_requires_capability_and_cached_logical_v3_still_works(client, asset_dir, physical_kind):
    register(client)
    if physical_kind:
        measurements()
        physical(client)
    else:
        logical(client)
    image_scene(client, asset_dir, fit="contain", background="#Ab12EF")
    assert config(client)["scene"]["content"]["background"] == "#ab12ef"
    with client.websocket_connect(url(caps="image,physical")) as socket:
        frame = receive(socket, "render" if physical_kind else "wall")
        assert frame["scene"]["content"] == {"type": "color"}
        assert status(client)["mapping"]["state"] == "unsupported_client"
    image_scene(client, asset_dir, fit="cover")
    with client.websocket_connect(url(caps="image,physical")) as socket:
        frame = receive(socket, "render" if physical_kind else "wall")
        assert frame["scene"]["content"]["type"] == "image"
        assert not status(client)["render"]["current"]


def test_physical_colour_and_pinned_calibration_health(client):
    register(client)
    measurements()
    physical(client)
    measurements()
    with client.websocket_connect(url()) as socket:
        frame = receive(socket, "render")
        assert frame["scene"]["content"] == {"type": "color"}
        assert frame["plan"] is None
        assert status(client)["mapping"]["state"] == "ready"
        health = status(client)["mapping"]["health"]
        assert health["revisions"]["profile_revision"] == 1
        assert health["uncertainty_mm"] == 1
        assert health["accuracy_claimed"] is False
        ack(socket, frame)
        assert status(client)["render"]["current"]
        client.put("/api/v3/scene", headers=headers(client), json={"content": {"type": "calibration"}}).raise_for_status()
        receive(socket, "render")
        assert status(client)["mapping"]["state"] == "unsupported_content"


def test_identify_expires_over_new_scene_with_fresh_token(client, asset_dir):
    register(client)
    logical(client)
    image_scene(client, asset_dir)
    with client.websocket_connect(url()) as socket:
        frame = receive(socket, "render")
        ack(socket, frame)
        before = config(client)
        client.post(f"/api/v3/devices/{A}/identify", headers=headers(client), json={"duration_ms": 1000}).raise_for_status()
        identify = receive(socket, "identify")
        assert 0 < identify["remaining_ms"] <= 1000
        assert config(client)["etag"] == before["etag"]
        assert status(client)["render"]["state"] == "identifying"
        client.put("/api/v3/scene", headers=headers(client), json={"content": {"type": "color"}}).raise_for_status()
        behind = receive(socket, "render")
        ack(socket, behind, seq=2)
        assert not status(client)["render"]["current"]
        expired = receive(socket, "render")
        assert expired["scene"]["content"] == {"type": "color"}
        assert expired["token"]["render_seq"] > behind["token"]["render_seq"]
        assert not status(client)["render"]["current"]
        ack(socket, expired, seq=3)
        assert status(client)["render"]["current"]


def grid_command(ids=(A, B)):
    return {"kind": "logical", "device_ids": list(ids), "rows": 1, "columns": len(ids),
        "gap": 0, "padding": 0, "sizing": "tablets", "orientation": "preserve",
        "logical_sizes": {key: {"w": 600, "h": 800} for key in ids},
        "allow_empty_cells": False, "release_unselected": []}


def test_grid_one_revision_order_and_viewport_guards(client, monkeypatch):
    for key in (A, B):
        register(client, key)
    command = grid_command((B, A))
    before = config(client)
    with client.websocket_connect(url()) as socket:
        receive(socket, "render")
        preview = client.post("/api/v3/grid/preview", headers=headers(client), json=command).json()
        assert preview["order"] == [B, A]
        assert config(client)["revision"] == before["revision"]
        socket.send_json({"type": "viewport", "viewport": {**VP, "width": 500}})
        receive(socket, "render")
        command["guards"] = preview["guards"]
        assert client.post("/api/v3/grid", headers=headers(client), json=command).status_code == 412
        preview = client.post("/api/v3/grid/preview", headers=headers(client), json=command).json()
        command["guards"] = preview["guards"]
        broadcasts = []
        original = main._broadcast_wall
        async def broadcast():
            broadcasts.append(True)
            await original()
        monkeypatch.setattr(main, "_broadcast_wall", broadcast)
        result = client.post("/api/v3/grid", headers=headers(client), json=command)
        result.raise_for_status()
        assert result.json()["revision"] == before["revision"] + 1
        assert len(broadcasts) == 1
        placements = result.json()["layout"]["placements"]
        assert placements[B]["x"] < placements[A]["x"]
        smaller = grid_command((A,))
        assert client.post("/api/v3/grid/preview", headers=headers(client), json=smaller).status_code == 409
        smaller["release_unselected"] = [B]
        assert client.post("/api/v3/grid/preview", headers=headers(client), json=smaller).status_code == 200


def test_labels_snapshots_durable_etags_and_restart(client):
    register(client)
    initial = config(client)
    response = client.patch(f"/api/v3/devices/{A}", headers=headers(client), json={"label": "  Wall α  "})
    response.raise_for_status()
    labelled = response.json()
    assert labelled["etag"] != initial["etag"] and labelled["revision"] == initial["revision"]
    register(client)
    assert config(client)["device_labels"][A] == "Wall α"
    main.restore_devices()
    assert main.devices[A]["label"] == "Wall α"
    saved = client.put("/api/v3/logical-layouts/first", headers=headers(client)).json()
    assert saved["etag"] != labelled["etag"] and saved["revision"] == labelled["revision"]
    digest = saved["snapshots"]["layouts"][0]["etag"]
    changed = deepcopy(main.wall["layout"])
    changed["width"] += 1
    persist.save_layout("first", changed, replace=True)
    current = config(client)
    assert current["snapshots"]["layouts"][0]["etag"] != digest
    assert current["etag"] != saved["etag"]
    client.put("/api/v3/scenes/colour", headers=headers(client)).raise_for_status()
    assert client.get("/api/v3/scenes").json()["scenes"][0]["valid"]
    assert client.delete("/api/v3/scenes/colour", headers=headers(client)).status_code == 200


def test_model_match_is_suggestion_until_confirmed_and_preserves_decisions(client):
    telemetry = dict(screen_width=768, screen_height=1024, screen_dpr=2, platform_family="ios")
    register(client, **telemetry)
    current = config(client)
    assert current["runtime"]["devices"][A]["model_suggestions"] == ["ipad-air-2"]
    assert current["displays"] == []
    response = client.put(f"/api/v3/tablet-assignments/{A}", headers=headers(client),
        json={"mode": "explicit", "model_id": "ipad-air-2"})
    response.raise_for_status()
    assignment = tablet_models.assignments()[A]
    register(client, screen_width=900, screen_height=1280, screen_dpr=2, platform_family="android")
    assert tablet_models.assignments()[A] == assignment
    assert displays.latest_calibration(A)["mm_per_css"] == [.187725, .187725]


@pytest.mark.parametrize("kind", ["logical", "physical"])
def test_remove_and_offline_only_forget_preserve_saved_reservations(client, kind):
    register(client)
    if kind == "physical":
        measurements()
        physical(client)
    else:
        logical(client)
    client.put(f"/api/v3/{'layouts' if kind == 'physical' else 'logical-layouts'}/kept", headers=headers(client)).raise_for_status()
    with client.websocket_connect(url()) as socket:
        receive(socket, "render")
        assert client.request("DELETE", f"/api/v3/devices/{A}", headers=headers(client),
            json={"remove_active": True, "saved_layouts": "keep"}).status_code == 409
        assert client.delete(f"/devices/{A}").status_code == 409
    body = {"remove_active": False, "saved_layouts": "keep"}
    assert client.request("DELETE", f"/api/v3/devices/{A}", headers=headers(client), json=body).status_code == 409
    body["remove_active"] = True
    response = client.request("DELETE", f"/api/v3/devices/{A}", headers=headers(client), json=body)
    response.raise_for_status()
    assert A not in main.devices
    assert [item["name"] for item in response.json()["remaining_saved"]] == ["kept"]
    assert A in persist.load_layout("kept")["slots" if kind == "physical" else "placements"]
    if kind == "physical":
        assert displays.profile(A, 1) is not None


def rebind_setup(client):
    register(client)
    logical(client)
    client.put("/api/v3/logical-layouts/logical", headers=headers(client)).raise_for_status()
    measurements()
    physical(client)
    client.put("/api/v3/layouts/physical", headers=headers(client)).raise_for_status()
    measurements()
    physical(client, revision=2)
    register(client, B)
    client.patch(f"/api/v3/devices/{A}", headers=headers(client), json={"label": "Original"}).raise_for_status()
    snapshots = config(client)["snapshots"]["layouts"]
    return {"replaces": A, "hardware": "same_hardware", "active": True,
        "saved_layouts": [{"name": item["name"], "etag": item["etag"]} for item in snapshots if item["name"] in ("logical", "physical")],
        "transfer_label": True}


@pytest.mark.parametrize("failure", [None, "roster", "last_snapshot"])
def test_rebind_all_histories_saved_recall_and_final_write_rollback(client, monkeypatch, failure):
    body = rebind_setup(client)
    before = config(client)
    old_roster = deepcopy(main.devices)
    old_saved = persist.load_layouts()
    preview = client.post(f"/api/v3/devices/{B}/rebind/preview", headers=headers(client), json=body)
    preview.raise_for_status()
    assert preview.json()["profile_revision_map"] == {"1": 1, "2": 2}
    body["new_connection_id"] = preview.json()["new_connection_id"]
    if failure == "roster":
        original = persist.save_devices
        def fail(records):
            original(records)
            assert main.devices == old_roster
            assert main.wall["layout"]["slots"].get(A) is not None
            raise RuntimeError("last roster write failed")
        monkeypatch.setattr(persist, "save_devices", fail)
    elif failure == "last_snapshot":
        original_save = main.save_layout
        def fail_save(name, *args, **kwargs):
            result = original_save(name, *args, **kwargs)
            if name == "physical":
                raise RuntimeError("last snapshot write failed")
            return result
        monkeypatch.setattr(main, "save_layout", fail_save)
    if failure:
        with pytest.raises(RuntimeError, match="last .* write failed"):
            client.post(f"/api/v3/devices/{B}/rebind", headers=headers(client), json=body)
        assert config(client) == before
        assert persist.load_layouts() == old_saved
        assert displays.profile(B, 1) is None
        assert main.devices == old_roster
        monkeypatch.undo()
    else:
        response = client.post(f"/api/v3/devices/{B}/rebind", headers=headers(client), json=body)
        response.raise_for_status()
        assert A not in main.devices and main.devices[B]["label"] == "Original"
        assert displays.profile(B, 1) and displays.profile(B, 2)
        assert response.json()["revision"] == before["revision"] + 1
        for name, route, bucket in (("logical", "logical-layouts", "placements"), ("physical", "layouts", "slots")):
            recalled = client.post(f"/api/v3/{route}/{name}/recall", headers=headers(client))
            recalled.raise_for_status()
            assert B in recalled.json()["layout"][bucket]
            assert A not in recalled.json()["layout"][bucket]
            assert recalled.json()["previous_layout_saved"]


def test_different_hardware_rebind_refuses_physical_scale(client):
    body = rebind_setup(client)
    body.update(hardware="different_hardware", new_connection_id=None)
    before = config(client)
    response = client.post(f"/api/v3/devices/{B}/rebind", headers=headers(client), json=body)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "physical_rebuild_required"
    assert config(client) == before


@pytest.mark.parametrize("kind,pattern", [("logical", "black"), ("physical", "black"), ("physical", "grid")])
def test_generated_patterns_are_ordinary_curated_assets(client, kind, pattern):
    if kind == "physical":
        register(client)
        measurements()
        physical(client)
    before = config(client)
    response = client.post("/api/v3/test-pattern", headers=headers(client), json={"pattern": pattern})
    response.raise_for_status()
    generated = response.json()
    assert generated["etag"] == before["etag"]
    assert generated["metadata"]["accuracy_claimed"] is False
    assert config(client) == before
    served = client.get(generated["url"])
    assert served.status_code == 200
    assert Image.open(BytesIO(served.content)).format == "PNG"
    repeat = client.post("/api/v3/test-pattern", headers=headers(client), json={"pattern": pattern}).json()
    assert repeat["id"] == generated["id"]
    selected = client.put("/api/v3/scene", headers=headers(client), json={"content": {"type": "image", "asset": generated["id"]}})
    selected.raise_for_status()
    assert selected.json()["scene"]["content"]["asset"] == generated["id"]


def test_invalid_snapshots_remain_visible_and_change_etag(client):
    with persist._connection() as connection:
        connection.execute("INSERT INTO saved_layouts(name, layout) VALUES (?, ?)", ("damaged", "{bad"))
    before = config(client)
    summary = before["snapshots"]["layouts"][0]
    assert summary["valid"] is False
    assert client.get("/api/v3/logical-layouts").json()["layouts"][0]["valid"] is False
    with persist._connection() as connection:
        connection.execute("UPDATE saved_layouts SET layout = ? WHERE name = ?", ("{other", "damaged"))
    assert config(client)["etag"] != before["etag"]
    assert client.post("/api/v3/logical-layouts/damaged/recall", headers=headers(client)).status_code == 422


@pytest.mark.parametrize("bad", [True, 0, -1, "nan", "inf"])
def test_viewport_rejects_invalid_visual_scale(client, bad):
    register(client)
    logical(client)
    with client.websocket_connect(url()) as socket:
        frame = receive(socket, "render")
        socket.send_json({"type": "viewport", "viewport": {**VP, "visual_scale": bad}})
        barrier(socket)
        assert main.devices[A]["viewport"] == VP
        assert main.devices[A]["render_seq"] == frame["render_seq"]


def test_physical_grid_uses_every_selected_revision_and_commits_once(client):
    for key in (A, B):
        register(client, key)
        measurements(key)
        measurements(key)
    body = {"kind": "physical", "device_ids": [B, A], "rows": 1, "columns": 2,
        "gap": 0, "padding": 2, "sizing": "tablets", "orientation": "preserve",
        "mount_angles": {A: 0, B: 90}, "physical_revisions": {key: {
            "profile_revision": 1, "calibration_revision": 1} for key in (A, B)},
        "allow_empty_cells": False, "release_unselected": []}
    before = config(client)
    preview = client.post("/api/v3/grid/preview", headers=headers(client), json=body)
    preview.raise_for_status()
    assert preview.json()["layout"]["slots"][A]["profile_revision"] == 1
    assert config(client) == before
    body["guards"] = preview.json()["guards"]
    result = client.post("/api/v3/grid", headers=headers(client), json=body)
    result.raise_for_status()
    assert result.json()["revision"] == before["revision"] + 1
    assert result.json()["previous_layout_saved"]
    assert result.json()["layout"]["slots"][B]["center_x_mm"] < result.json()["layout"]["slots"][A]["center_x_mm"]


def test_inherited_model_estimate_is_not_overwritten_or_verified(client):
    register(client)
    inherited = tablet_models.assign(A, "auto", "ipad-air-2")
    physical(client)
    register(client, screen_width=900, screen_height=1280, screen_dpr=2, platform_family="android")
    assert tablet_models.assignments()[A] == inherited
    with client.websocket_connect(url(width=768, height=1024, dpr=2)) as socket:
        receive(socket, "render")
        health = status(client)["mapping"]["health"]
        assert health["approximate"] is True
        assert health["provenance"]["model_snapshot"]["confirmed"] is False
        assert health["measurements"]["model_mm_per_css"] == [.187725, .187725]


def test_model_history_changes_etag_without_wall_revision(client):
    register(client)
    tablet_models.assign(A, "explicit", "ipad-air-2")
    before = config(client)
    history = persist.load_meta("tablet_model_calibrations")
    history[A]["1"]["model"]["uncertainty_mm"] = 4
    persist.save_meta("tablet_model_calibrations", history)
    after = config(client)
    assert after["etag"] != before["etag"]
    assert after["revision"] == before["revision"]


def test_missing_asset_availability_does_not_invalidate_durable_etag(client, asset_dir):
    before = image_scene(client, asset_dir)
    assert before["scene"]["content"]["available"] is True
    (asset_dir / "image.png").unlink()
    after = config(client)
    assert after["scene"]["content"]["available"] is False
    assert after["scene"]["content"]["asset"] == before["scene"]["content"]["asset"]
    assert after["etag"] == before["etag"]


def test_generated_pattern_rechecks_etag_after_generation(client, monkeypatch):
    original = main.test_pattern.generate_test_pattern
    def generate(*args, **kwargs):
        result = original(*args, **kwargs)
        main.save_scene("concurrent", {"type": "color"})
        return result
    monkeypatch.setattr(main.test_pattern, "generate_test_pattern", generate)
    response = client.post("/api/v3/test-pattern", headers=headers(client), json={"pattern": "black"})
    assert response.status_code == 412
    assert assets.list_assets() == []
    assert main.wall["revision"] == 0


def test_scene_snapshot_recall_validates_availability_and_fit(client, asset_dir):
    image_scene(client, asset_dir, fit="contain", background="#123456")
    client.put("/api/v3/scenes/image", headers=headers(client)).raise_for_status()
    client.put("/api/v3/scene", headers=headers(client), json={"content": {"type": "color"}}).raise_for_status()
    response = client.post("/api/v3/scenes/image/recall", headers=headers(client))
    response.raise_for_status()
    assert response.json()["scene"]["content"]["fit"] == "contain"
    assert response.json()["scene"]["content"]["background"] == "#123456"
    (asset_dir / "image.png").unlink()
    before = config(client)
    assert client.post("/api/v3/scenes/image/recall", headers=headers(client)).status_code == 422
    assert config(client) == before


def test_rebind_saved_digest_and_connection_guards(client):
    body = rebind_setup(client)
    body["saved_layouts"][0]["etag"] = "obsolete"
    assert client.post(f"/api/v3/devices/{B}/rebind/preview", headers=headers(client), json=body).status_code == 412
    body = rebind_setup_selection(client)
    preview = client.post(f"/api/v3/devices/{B}/rebind/preview", headers=headers(client), json=body).json()
    assert preview["new_connection_id"] is None
    with client.websocket_connect(url(key=B)) as socket:
        receive(socket, "render")
        assert client.post(f"/api/v3/devices/{B}/rebind", headers=headers(client),
            json={**body, "new_connection_id": None}).status_code == 412


def rebind_setup_selection(client):
    return {"replaces": A, "hardware": "same_hardware", "active": True,
        "saved_layouts": [{"name": row["name"], "etag": row["etag"]}
            for row in config(client)["snapshots"]["layouts"] if row["name"] in ("logical", "physical")],
        "transfer_label": True}


def test_identify_status_is_connection_and_command_owned(client):
    register(client)
    logical(client)
    with client.websocket_connect(url()) as socket:
        first = receive(socket, "render")
        ack(socket, first, seq=20)
        client.post(f"/api/v3/devices/{A}/identify", headers=headers(client)).raise_for_status()
        command = receive(socket, "identify")
        socket.send_json({"type": "identify_status", "connection_id": command["connection_id"],
            "command_id": "obsolete", "status": "cleared"})
        barrier(socket)
        assert status(client)["identify"]["active"]
        socket.send_json({"type": "identify_status", "connection_id": command["connection_id"],
            "command_id": command["command_id"], "status": "cleared"})
        fresh = receive(socket, "render")
        assert fresh["token"] != first["token"]
        ack(socket, fresh, seq=20)
        assert not status(client)["render"]["current"]
        ack(socket, fresh, seq=21)
        assert status(client)["render"]["current"]


def test_v3_status_notifications_preserve_device_fields(client):
    register(client)
    logical(client)
    with client.websocket_connect("/ws/controller?protocol=3") as controller:
        initial = receive(controller, "snapshot")
        assert initial["config"]["operator_state_version"] == 1
        with client.websocket_connect(url()) as socket:
            frame = receive(socket, "render")
            ack(socket, frame)
            event = receive(controller, "device_updated")
            assert event["device"]["width"] == 600
            assert event["device"]["mapping"]["state"] == "ready"
            assert event["device"]["render"]["current"]


def test_failed_experimental_presentation_still_fences_static_evidence(client, monkeypatch):
    register(client)
    logical(client)
    with client.websocket_connect(url()) as socket:
        frame = receive(socket, "render")
        ack(socket, frame)
        assert status(client)["render"]["current"]
        monkeypatch.setattr(main, "_playback_session", SimpleNamespace(state="failed"))
        assert config(client)["runtime"]["presentation"]["owner"] == "playback"
        ack(socket, frame, seq=2)
        assert not status(client)["render"]["current"]
        assert status(client)["render"]["reason"] == "playback"
        monkeypatch.setattr(main, "_playback_session", None)


def test_heartbeat_age_expires_render_evidence_without_changing_config(client, monkeypatch):
    register(client)
    logical(client)
    with client.websocket_connect(url()) as socket:
        frame = receive(socket, "render")
        ack(socket, frame)
        before = config(client)
        monkeypatch.setattr(render_status, "HEARTBEAT_TIMEOUT_S", 0)
        after = config(client)
        assert after["runtime"]["devices"][A]["render"]["state"] == "stale"
        assert after["runtime"]["devices"][A]["render"]["age_ms"] >= 0
        assert after["etag"] == before["etag"]


def test_old_socket_cannot_report_for_or_clear_its_replacement(client):
    register(client)
    logical(client)
    old_context = client.websocket_connect(url())
    old = old_context.__enter__()
    receive(old, "render")
    try:
        with client.websocket_connect(url()) as new:
            fresh = receive(new, "render")
            old.send_json({"type": "render_ack", "token": fresh["token"], "report_seq": 1,
                "status": "displayed", "reason": None, "viewport": VP, "visible": True})
            old_context.__exit__(None, None, None)
            old_context = None
            barrier(new)
            assert not status(client)["render"]["current"]
            ack(new, fresh, seq=2)
            assert status(client)["render"]["current"]
    finally:
        if old_context is not None:
            old_context.__exit__(None, None, None)


def test_logical_background_is_image_only_and_new_mutations_are_cas_guarded(client):
    register(client)
    before = config(client)
    assert client.put("/api/v3/scene", headers=headers(client),
        json={"content": {"type": "color", "background": None}}).status_code == 422
    requests = [("PATCH", f"/api/v3/devices/{A}", {"label": "label"}),
        ("POST", f"/api/v3/devices/{A}/identify", {"duration_ms": 1000}),
        ("POST", "/api/v3/grid/preview", grid_command((A,))),
        ("POST", "/api/v3/grid", grid_command((A,))),
        ("POST", "/api/v3/test-pattern", {"pattern": "black"}),
        ("DELETE", f"/api/v3/devices/{A}", {"remove_active": True, "saved_layouts": "keep"}),
        ("PUT", "/api/v3/scenes/test", None), ("PUT", "/api/v3/logical-layouts/test", None)]
    for method, path, body in requests:
        assert client.request(method, path, json=body).status_code == 428
        assert client.request(method, path, json=body, headers={"If-Match": "stale"}).status_code == 412
    assert config(client) == before


def test_grid_auto_orientation_uses_selected_historical_model_after_google_and_manual_assignment(client):
    register(client)
    for model_id in ("ipad-air-2", "google-pixel-c"):
        client.put(f"/api/v3/tablet-assignments/{A}", headers=headers(client),
            json={"mode": "explicit", "model_id": model_id}).raise_for_status()
    assert tablet_models.assignments()[A]["model_id"] == "google-pixel-c"
    command = {"kind": "physical", "device_ids": [A], "rows": 1, "columns": 1,
        "gap": 0, "padding": 0, "sizing": "tablets", "orientation": "auto",
        "physical_revisions": {A: {"profile_revision": 1, "calibration_revision": 1}},
        "allow_empty_cells": False, "release_unselected": []}
    with client.websocket_connect(url(width=768, height=1024, dpr=2)) as socket:
        receive(socket, "render")
        google_current = client.post("/api/v3/grid/preview", headers=headers(client), json=command)
        google_current.raise_for_status()
        assert google_current.json()["layout"]["slots"][A]["mount_angle"] == 0
        client.put(f"/api/v3/tablet-assignments/{A}", headers=headers(client),
            json={"mode": "manual"}).raise_for_status()
        receive(socket, "render")
        manual_current = client.post("/api/v3/grid/preview", headers=headers(client), json=command)
        manual_current.raise_for_status()
        assert manual_current.json()["layout"] == google_current.json()["layout"]
        command["guards"] = manual_current.json()["guards"]
        applied = client.post("/api/v3/grid", headers=headers(client), json=command)
        applied.raise_for_status()
        slot = applied.json()["layout"]["slots"][A]
        assert slot["mount_angle"] == 0
        assert slot["profile_revision"] == slot["calibration_revision"] == 1
        frame = receive(socket, "render")
        assert frame["mapping"]["health"]["provenance"]["model_id"] == "ipad-air-2"
        assert frame["mapping"]["health"]["revisions"]["assignment"]["pinned_match"] is True
