"""Playback transitions over HTTP and the device socket (R3 corrections)."""

import os
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import main
from tabletwall import displays, media, playback
from video_fixtures import make_video, needs_ffmpeg, video_dir  # noqa: F401

A = "0f8fad5b-d9cb-469f-a165-70867728950e"
B = "2b1c4d5e-6f70-4819-a2b3-c4d5e6f70819"


def measurement(device_id: str) -> None:
    displays.save_profile(
        device_id, active_width_mm=100, active_height_mm=60,
        bezels={"left": 13, "top": 13, "right": 7, "bottom": 17},
        panel_pixels={"width": 2000, "height": 1200},
        label="fixture", provenance="hand-derived",
    )
    displays.save_calibration(
        device_id, profile_revision=1, viewport_width=240, viewport_height=160,
        dpr=1, orientation=0, mode="tab", quarter_turn=0,
        panel_offset_mm=(0, 0), mm_per_css=(0.5, 0.5),
        anchor_edge="top-left", uncertainty_mm=0.5, method="hand-derived",
    )


def layout() -> dict:
    return {
        "bounds": {"x": 0, "y": 0, "width": 200, "height": 120},
        "slots": {
            A: {"center_x_mm": 50, "center_y_mm": 50, "mount_angle": 0,
                "nudge_x_mm": 0, "nudge_y_mm": 0, "profile_revision": 1,
                "calibration_revision": 1, "participating": True},
            B: {"center_x_mm": 150, "center_y_mm": 50, "mount_angle": 0,
                "nudge_x_mm": 0, "nudge_y_mm": 0, "profile_revision": 1,
                "calibration_revision": 1, "participating": True},
        },
    }


def playlist(client: TestClient) -> None:
    directory = Path(os.environ["TABLET_WALL_ASSET_DIR"])
    directory.mkdir(parents=True, exist_ok=True)
    buffer = BytesIO()
    Image.new("RGB", (200, 100), (30, 120, 200)).save(buffer, format="JPEG", quality=90)
    (directory / "solid.jpg").write_bytes(buffer.getvalue())
    from tabletwall import assets
    entry = assets.list_assets()[0]
    etag = client.get("/api/v3/playlist").json()["etag"]
    headers = {"If-Match": etag}
    if os.environ.get("TABLET_WALL_OPERATOR_ORIGIN"):
        headers["Origin"] = os.environ["TABLET_WALL_OPERATOR_ORIGIN"]
    saved = client.put("/api/v3/playlist", json={
        "items": [{"asset": entry["id"], "dwell_ms": 5000}], "loop": False,
    }, headers=headers)
    assert saved.status_code == 200, saved.text


def register(client: TestClient, device_id: str) -> None:
    response = client.post("/devices/register", json={
        "device_id": device_id, "width": 240, "height": 160, "device_type": "fixture",
    })
    assert response.status_code == 200, response.text


def socket_url(device_id: str) -> str:
    return (f"/ws/device?device_id={device_id}&protocol=3"
            "&caps=calibration,image,physical&w=240&h=160&dpr=1&orientation=0&mode=tab")


def video_asset_id() -> str:
    from tabletwall import assets
    return assets.list_assets()[0]["id"]


def playing_video_session(asset_id: str, connections: dict[str, str]) -> playback.Session:
    """A committed video occurrence, as if the server had already cut it."""
    now = main._now_ms()
    session = playback.start(
        [{"asset": asset_id, "dwell_ms": 1000}, {"asset": asset_id, "dwell_ms": 5000}],
        False, [A, B], now, generation=main.wall["generation"],
        clock_epoch=main._server_clock.epoch, connections=connections,
        policy="strict", videos={asset_id: 4000},
    )
    media = session.pending.media
    session.version = 2
    session.state = "playing"
    session.current = session.occurrence_at(0)
    session.displayed = session.current
    session.current_effective_ms = now
    session.current_media = media
    session.current_connections = dict(connections)
    session.playing = [A, B]
    session.pending = None
    return session


def video_fault(session: playback.Session, position_ms: int = 1500) -> dict:
    return {
        "type": "video_fault", "session_id": session.id,
        "version": session.version,
        "occurrence": session.current.as_dict(),
        "position_ms": position_ms, "reason": "stalled",
    }


def prepare_physical(client: TestClient) -> None:
    register(client, A)
    register(client, B)
    measurement(A)
    measurement(B)
    config = client.get("/api/v3/config").json()
    headers = {"If-Match": config["etag"]}
    if os.environ.get("TABLET_WALL_OPERATOR_ORIGIN"):
        headers["Origin"] = os.environ["TABLET_WALL_OPERATOR_ORIGIN"]
    response = client.put("/api/v3/layout", json=layout(), headers=headers)
    assert response.status_code == 200, response.text
    playlist(client)


def test_strict_start_includes_an_offline_required_slot_and_blocks():
    with TestClient(main.app) as client:
        prepare_physical(client)
        with client.websocket_connect(socket_url(A)) as socket:
            socket.receive_json()  # welcome
            socket.receive_json()  # clock bootstrap
            socket.receive_json()  # render
            started = client.post("/api/v3/playback/start", json={"policy": "strict"})
            assert started.status_code == 200, started.text
            status = started.json()
            assert status["policy"] == "strict"
            assert set(status["cohort"]) == {A, B}
            session = main._playback_session
            assert session is not None
            actions = playback.tick(session, session.pending.deadline_ms)
            assert actions[0]["type"] == "blocked"
            assert set(actions[0]["missing"]) == {A, B}
            assert client.get("/api/v3/playback").json()["state"] == "blocked"


def test_pause_then_start_resumes_the_current_item():
    with TestClient(main.app) as client:
        prepare_physical(client)
        with client.websocket_connect(socket_url(A)) as socket:
            socket.receive_json()
            socket.receive_json()
            socket.receive_json()
            started = client.post("/api/v3/playback/start", headers={"Origin": "http://testserver"})
            assert started.status_code == 200, started.text
            version = started.json()["version"]
            paused = client.post("/api/v3/playback/pause",
                                 headers={"If-Match": str(version)})
            assert paused.status_code == 200, paused.text
            assert paused.json()["state"] == "paused"
            resumed = client.post("/api/v3/playback/start")
            assert resumed.status_code == 200, resumed.text
            body = resumed.json()
            assert body["state"] == "preparing"
            assert body["version"] > version
            assert body["pending"]["occurrence"]["item_index"] == 0
            assert body["policy"] == "online"


def test_a_video_playlist_defaults_to_strict_and_uses_its_duration(
    monkeypatch, make_video
):
    monkeypatch.setenv("TABLET_WALL_UPLOAD_MODE", "loopback")
    monkeypatch.setenv("TABLET_WALL_OPERATOR_ORIGIN", "http://testserver")
    monkeypatch.setattr(media, "_loopback_peer", lambda _request: True)
    with TestClient(main.app) as client:
        prepare_physical(client)
        clip = make_video("baseline.mp4")
        uploaded = client.post(
            "/uploads?name=clip.mp4", content=clip.read_bytes(),
            headers={"Origin": "http://testserver", "Content-Type": "video/mp4"},
        )
        assert uploaded.status_code == 201, uploaded.text
        asset = uploaded.json()["asset"]
        etag = client.get("/api/v3/playlist").json()["etag"]
        saved = client.put("/api/v3/playlist", json={
            "items": [{"asset": asset["id"], "dwell_ms": 1000}], "loop": False,
        }, headers={"If-Match": etag, "Origin": "http://testserver"})
        assert saved.status_code == 200, saved.text
        assert saved.json()["playlist"]["items"][0]["dwell_ms"] == asset["durationMs"]
        with client.websocket_connect(socket_url(A)) as socket:
            socket.receive_json()
            socket.receive_json()
            socket.receive_json()
            started = client.post("/api/v3/playback/start", headers={"Origin": "http://testserver"})
            assert started.status_code == 200, started.text
            status = started.json()
            assert status["policy"] == "strict"
            assert set(status["cohort"]) == {A, B}
            assert status["pending"]["media"]["kind"] == "video"


def test_a_layout_change_aborts_an_active_session():
    with TestClient(main.app) as client:
        prepare_physical(client)
        with client.websocket_connect(socket_url(A)) as socket:
            socket.receive_json()
            socket.receive_json()
            socket.receive_json()
            started = client.post("/api/v3/playback/start")
            assert started.status_code == 200, started.text
            assert client.get("/api/v3/playback").json()["state"] != "stopped"

            config = client.get("/api/v3/config").json()
            changed = layout()
            changed["bounds"]["width"] = 210
            headers = {"If-Match": config["etag"]}
            if os.environ.get("TABLET_WALL_OPERATOR_ORIGIN"):
                headers["Origin"] = os.environ["TABLET_WALL_OPERATOR_ORIGIN"]
            response = client.put("/api/v3/layout", json=changed, headers=headers)
            assert response.status_code == 200, response.text
            assert client.get("/api/v3/playback").json() == {"state": "stopped"}


def test_rebind_aborts_an_active_session():
    with TestClient(main.app) as client:
        prepare_physical(client)
        replacement = "5c6d7e8f-9012-4a3b-8c4d-5e6f708192a3"
        register(client, replacement)
        with client.websocket_connect(socket_url(A)) as socket:
            socket.receive_json()
            socket.receive_json()
            socket.receive_json()
            started = client.post("/api/v3/playback/start")
            assert started.status_code == 200, started.text
            response = client.post(
                f"/devices/{replacement}/rebind", json={"replaces": B}
            )
            assert response.status_code == 200, response.text
            assert client.get("/api/v3/playback").json() == {"state": "stopped"}


def test_a_video_fault_over_the_socket_prepares_the_group_at_its_position():
    with TestClient(main.app) as client:
        prepare_physical(client)
        asset_id = video_asset_id()
        with client.websocket_connect(socket_url(A)) as socket:
            socket.receive_json()  # welcome
            socket.receive_json()  # clock bootstrap
            socket.receive_json()  # render
            connections = {
                device_id: main.devices[device_id].get("connection_id", "")
                for device_id in (A, B) if device_id in main.devices
            }
            session = playing_video_session(asset_id, connections)
            main._playback_session = session
            sent_at = main._now_ms()
            socket.send_json(video_fault(session))
            frame = socket.receive_json()
            assert frame["type"] == "prepare"
            assert frame["occurrence"] == session.current.as_dict()
            assert frame["start_media_ms"] == 1500
            assert frame["media"]["kind"] == "video"
            assert frame["effective_server_ms"] >= sent_at + 900
            assert session.state == "recovering"
            assert session.pending.occurrence == session.current
            assert session.pending.start_media_ms == 1500
            assert session.recovery.attempts == 1
            # A duplicate for the active recovery prepares nothing again.
            version = session.version
            socket.send_json(video_fault(session, position_ms=1400))
            assert main._playback_status()["recovery"]["attempts"] == 1
            assert session.version == version
            assert session.pending.start_media_ms == 1500


def test_a_layout_change_aborts_a_recovery():
    with TestClient(main.app) as client:
        prepare_physical(client)
        session = playing_video_session(video_asset_id(), {})
        main._playback_session = session
        assert playback.accept_fault(
            session, device_id=A, payload=video_fault(session),
            now_ms=session.current_effective_ms,
        ) == "preparing"
        assert client.get("/api/v3/playback").json()["state"] == "recovering"

        config = client.get("/api/v3/config").json()
        changed = layout()
        changed["bounds"]["width"] = 210
        headers = {"If-Match": config["etag"]}
        if os.environ.get("TABLET_WALL_OPERATOR_ORIGIN"):
            headers["Origin"] = os.environ["TABLET_WALL_OPERATOR_ORIGIN"]
        response = client.put("/api/v3/layout", json=changed, headers=headers)
        assert response.status_code == 200, response.text
        assert client.get("/api/v3/playback").json() == {"state": "stopped"}
        assert main._playback_session is None
        assert session.state == "stopped" and session.recovery is None


def test_a_mapping_change_aborts_a_recovery():
    with TestClient(main.app) as client:
        prepare_physical(client)
        session = playing_video_session(video_asset_id(), {})
        main._playback_session = session
        assert playback.accept_fault(
            session, device_id=A, payload=video_fault(session),
            now_ms=session.current_effective_ms,
        ) == "preparing"
        config = client.get("/api/v3/config").json()
        headers = {"If-Match": config["etag"]}
        if os.environ.get("TABLET_WALL_OPERATOR_ORIGIN"):
            headers["Origin"] = os.environ["TABLET_WALL_OPERATOR_ORIGIN"]
        response = client.put(f"/api/v3/displays/{A}", json={
            "active_width_mm": 101, "active_height_mm": 60,
            "bezels": {"left": 13, "top": 13, "right": 7, "bottom": 17},
            "label": "changed", "provenance": "hand-derived",
        }, headers=headers)
        assert response.status_code == 200, response.text
        assert main._playback_session is None
        assert session.state == "stopped" and session.recovery is None


def test_a_host_suspend_epoch_change_aborts_a_recovery():
    import asyncio

    with TestClient(main.app) as client:
        prepare_physical(client)
        session = playing_video_session(video_asset_id(), {})
        main._playback_session = session
        assert playback.accept_fault(
            session, device_id=A, payload=video_fault(session),
            now_ms=session.current_effective_ms,
        ) == "preparing"
        asyncio.run(main._abort_playback("host suspend"))
        assert main._playback_session is None
        assert client.get("/api/v3/playback").json() == {"state": "stopped"}
        assert session.state == "stopped" and session.recovery is None
