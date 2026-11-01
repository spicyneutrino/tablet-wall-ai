"""Version 3 physical negotiation, render plan, and legacy fences (R2)."""

import asyncio
import hashlib
import json
import os
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import main
from tabletwall import assets, displays


DEVICE = "0f8fad5b-d9cb-469f-a165-70867728950e"


def jpeg() -> bytes:
    buffer = BytesIO()
    image = Image.new("RGB", (2000, 1000), (20, 120, 200))
    image.paste((220, 40, 40), (0, 0, 1000, 1000))
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def setup_measurement():
    displays.save_profile(
        DEVICE, active_width_mm=100, active_height_mm=60,
        bezels={"left": 13, "top": 13, "right": 7, "bottom": 17},
        panel_pixels={"width": 2360, "height": 1640},
        label="fixture", provenance="hand-derived",
    )
    displays.save_calibration(
        DEVICE, profile_revision=1, viewport_width=600, viewport_height=800,
        dpr=1.25, orientation=0, mode="fullscreen", quarter_turn=1,
        panel_offset_mm=(10, 20), mm_per_css=(1 / 6, 1 / 6),
        anchor_edge="top-left", uncertainty_mm=0.5, method="hand-derived",
    )


def setup_scene(client):
    registered = client.post("/devices/register", json={
        "device_id": DEVICE, "width": 600, "height": 800,
        "device_type": "fixture",
    })
    assert registered.status_code == 200, registered.text
    directory = Path(os.environ["TABLET_WALL_ASSET_DIR"])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "fixture.jpg").write_bytes(jpeg())
    entry = assets.list_assets()[0]
    response = client.put(
        "/scene", json={"content": {"type": "image", "asset": entry["id"], "fit": "cover"}}
    )
    assert response.status_code == 200, response.text
    return entry


def layout_body():
    return {
        "bounds": {"x": 0, "y": 0, "width": 1200, "height": 800},
        "slots": {
            DEVICE: {
                "center_x_mm": 300, "center_y_mm": 400, "mount_angle": 90,
                "nudge_x_mm": 5, "nudge_y_mm": -3,
                "profile_revision": 1, "calibration_revision": 1,
                "participating": True,
            }
        },
    }


def switch_physical(client):
    config = client.get("/api/v3/config").json()
    response = client.put(
        "/api/v3/layout", json=layout_body(),
        headers={"If-Match": config["etag"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def device_url(protocol=3, **viewport):
    params = {"device_id": DEVICE, "protocol": protocol,
              "caps": "calibration,image,physical"}
    params.update(viewport)
    return "/ws/device?" + "&".join(f"{key}={value}" for key, value in params.items())


def test_v3_render_plan_matches_the_hand_derived_matrix():
    with TestClient(main.app) as client:
        setup_measurement()
        setup_scene(client)
        config = switch_physical(client)
        assert config["layout"]["kind"] == "physical"

        with client.websocket_connect(device_url(
            w=600, h=800, dpr=1.25, orientation=0, mode="fullscreen"
        )) as socket:
            welcome = socket.receive_json()
            assert welcome["protocol"] == 3
            assert "physical" in welcome["server_caps"]
            assert socket.receive_json()["type"] == "clock_bootstrap"
            frame = socket.receive_json()
        assert frame["type"] == "render" and frame["mode"] == "physical"
        assert frame["calibration"]["status"] == "valid"
        assert frame["render_seq"] == 1
        plan = frame["plan"]
        expected = [-6, 0, 0, -6, 3877.5, 3700]
        assert len(plan["panel_from_source"]) == 6
        for actual, wanted in zip(plan["panel_from_source"], [0, -1600, 800, 0, -350, 537]):
            assert abs(actual - wanted) < 1e-9
        assert plan["body"] == {"width": 120, "height": 90}
        assert plan["active"] == {"x": -47, "y": -32, "width": 100, "height": 60}
        assert plan["source"] == {"width": 2000, "height": 1000}
        from tabletwall import geometry
        matrix = geometry.canvas_transform_components(
            backing=(750, 1000), rect=(600, 800),
            calibration={
                "viewport_width": 600, "viewport_height": 800, "quarter_turn": 1,
                "panel_offset_mm": [10, 20], "mm_per_css": [1 / 6, 1 / 6],
                "panel_width": 100, "panel_height": 60,
            },
            panel_from_source=tuple(plan["panel_from_source"]),
            source_size=(2000, 1000),
        )["matrix"]
        for actual, wanted in zip(matrix, expected):
            assert abs(actual - wanted) < 1e-9


@pytest.mark.parametrize("caps", ["physical", "calibration,physical", ""])
def test_physical_image_is_not_sent_without_advertised_support(caps):
    with TestClient(main.app) as client:
        setup_measurement()
        setup_scene(client)
        switch_physical(client)
        with client.websocket_connect(device_url(
            w=600, h=800, dpr=1.25, orientation=0, mode="fullscreen", caps=caps
        )) as socket:
            socket.receive_json()
            socket.receive_json()
            frame = socket.receive_json()
        assert frame["scene"]["content"] == {"type": "color"}
        assert frame["plan"] is None
        assert frame["calibration"]["reason"] == "tablet does not advertise image support"


@pytest.mark.parametrize("caps, allowed", [([], False), (["physical"], False), (["image", "physical"], True)])
def test_prepared_image_requires_advertised_image_support(monkeypatch, caps, allowed):
    main.devices[DEVICE] = {"caps": caps}
    main.device_sockets[DEVICE] = object()
    monkeypatch.setattr(main, "_asset_descriptor", lambda _: {
        "mime": "image/png", "intrinsicWidth": 200, "intrinsicHeight": 100,
    })
    monkeypatch.setattr(main, "_physical_plan_for", lambda *args: ({}, {}))
    sent = []

    async def send(socket, frame):
        sent.append(frame)

    monkeypatch.setattr(main, "_send_to", send)
    pending = SimpleNamespace(asset="fixture", leases={}, as_frame=lambda: {})
    session = SimpleNamespace(cohort=[DEVICE], lineage=lambda: {})
    assert asyncio.run(main._send_prepare(session, pending, DEVICE)) is allowed
    assert len(sent) == int(allowed)
    if sent:
        assert sent[0]["type"] == "prepare"


def test_a_stale_viewport_gets_no_physical_claim():
    with TestClient(main.app) as client:
        setup_measurement()
        setup_scene(client)
        switch_physical(client)
        with client.websocket_connect(device_url(
            w=700, h=800, dpr=1.25, orientation=0, mode="fullscreen"
        )) as socket:
            socket.receive_json()
            socket.receive_json()  # clock_bootstrap
            frame = socket.receive_json()
        assert frame["plan"] is None
        assert frame["calibration"]["status"] == "needs_calibration"
        assert "viewport" in frame["calibration"]["reason"]


def test_a_v2_device_gets_a_neutral_envelope_not_physical_units():
    with TestClient(main.app) as client:
        setup_measurement()
        setup_scene(client)
        switch_physical(client)
        with client.websocket_connect(
            f"/ws/device?device_id={DEVICE}&protocol=2&caps=image"
        ) as socket:
            socket.receive_json()  # welcome
            frame = socket.receive_json()
        assert frame["type"] == "wall"
        assert frame["wall"] == {"width": 2000, "height": 1000}
        assert frame["placement"] is None
        assert frame["scene"]["content"] == {"type": "color"}


def test_legacy_layout_routes_are_fenced_while_physical():
    with TestClient(main.app) as client:
        setup_measurement()
        setup_scene(client)
        switch_physical(client)
        assert client.get("/wall").status_code == 409
        assert client.put("/wall", json={"width": 10}).status_code == 409
        assert client.put(
            f"/devices/{DEVICE}/placement",
            json={"x": 0, "y": 0, "w": 10, "h": 10},
        ).status_code == 409
        assert client.post("/wall/auto").status_code == 409
        assert client.put("/layouts/lobby").status_code == 409


def test_config_writes_require_a_current_etag():
    with TestClient(main.app) as client:
        setup_measurement()
        payload = {
            "active_width_mm": 120, "active_height_mm": 70,
            "bezels": {"left": 1, "top": 1, "right": 1, "bottom": 1},
            "label": "second", "provenance": "ruler",
        }
        assert client.put(f"/api/v3/displays/{DEVICE}", json=payload).status_code == 428
        config = client.get("/api/v3/config").json()
        stale = client.put(
            f"/api/v3/displays/{DEVICE}", json=payload,
            headers={"If-Match": "not-the-current-etag"},
        )
        assert stale.status_code == 412
        accepted = client.put(
            f"/api/v3/displays/{DEVICE}", json=payload,
            headers={"If-Match": config["etag"]},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["display"]["revision"] == 2
        assert accepted.json()["etag"] != config["etag"]


def test_a_missing_calibration_for_a_slot_is_refused():
    with TestClient(main.app) as client:
        setup_measurement()
        setup_scene(client)
        config = client.get("/api/v3/config").json()
        body = layout_body()
        body["slots"][DEVICE]["calibration_revision"] = 99
        response = client.put(
            "/api/v3/layout", json=body, headers={"If-Match": config["etag"]}
        )
        assert response.status_code == 422


def test_physical_layouts_save_recall_and_delete():
    with TestClient(main.app) as client:
        setup_measurement()
        setup_scene(client)
        config = switch_physical(client)
        assert client.get("/api/v3/layouts").json() == {"layouts": []}

        saved = client.put(
            "/api/v3/layouts/lobby",
            headers={"If-Match": config["etag"]},
        )
        assert saved.status_code == 200, saved.text
        names = [entry["name"] for entry in client.get("/api/v3/layouts").json()["layouts"]]
        assert names == ["lobby"]

        moved = layout_body()
        moved["slots"][DEVICE]["center_x_mm"] = 350
        current = client.get("/api/v3/config").json()
        changed = client.put(
            "/api/v3/layout", json=moved, headers={"If-Match": current["etag"]}
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["layout"]["slots"][DEVICE]["center_x_mm"] == 350

        recalled = client.post(
            "/api/v3/layouts/lobby/recall",
            headers={"If-Match": changed.json()["etag"]},
        )
        assert recalled.status_code == 200, recalled.text
        assert recalled.json()["layout"]["slots"][DEVICE]["center_x_mm"] == 300

        deleted = client.delete(
            "/api/v3/layouts/lobby",
            headers={"If-Match": recalled.json()["etag"]},
        )
        assert deleted.status_code == 200
        assert client.get("/api/v3/layouts").json() == {"layouts": []}


def test_playlist_save_requires_a_valid_asset_and_current_etag():
    with TestClient(main.app) as client:
        setup_measurement()
        entry = setup_scene(client)
        empty = client.get("/api/v3/playlist").json()
        unknown = client.put(
            "/api/v3/playlist",
            json={"items": [{"asset": "sha256:" + "0" * 64, "dwell_ms": 1500}],
                  "loop": False},
            headers={"If-Match": empty["etag"]},
        )
        assert unknown.status_code == 422
        missing = client.put(
            "/api/v3/playlist",
            json={"items": [{"asset": entry["id"], "dwell_ms": 1500}], "loop": False},
        )
        assert missing.status_code == 428
        saved = client.put(
            "/api/v3/playlist",
            json={"items": [{"asset": entry["id"], "dwell_ms": 1500}], "loop": False},
            headers={"If-Match": empty["etag"]},
        )
        assert saved.status_code == 200, saved.text
        stale = client.put(
            "/api/v3/playlist",
            json={"items": [{"asset": entry["id"], "dwell_ms": 1500}], "loop": False},
            headers={"If-Match": empty["etag"]},
        )
        assert stale.status_code == 412
        assert client.get("/api/v3/playlist").json()["playlist"]["items"][0]["asset"] == entry["id"]


def test_playback_start_needs_a_playlist_and_actions_need_a_session():
    with TestClient(main.app) as client:
        assert client.get("/api/v3/playback").json() == {"state": "stopped"}
        no_playlist = client.post("/api/v3/playback/start")
        assert no_playlist.status_code == 409
        assert client.post("/api/v3/playback/pause").status_code == 404
        assert client.post("/api/v3/playback/stop").status_code == 404
