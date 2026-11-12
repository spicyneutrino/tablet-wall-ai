"""Field readiness (R5): diagnostics, wake-lock reports and origin rebinding.

Diagnostics use operator-read admission (independent of upload admission),
rebinding is the manual recovery for a tablet whose localStorage was wiped by
an origin change, and the wake-lock field is a diagnostic the roster echoes.
All three use the same temp database and media directory as the rest of the
suite.
"""

import json
import os
import uuid
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from starlette.websockets import WebSocketDisconnect

import main
import tabletwall.media as media
from tabletwall import displays, persist

ORIGIN = "https://operator.wall.test:8444"


@pytest.fixture
def operator(monkeypatch):
    monkeypatch.setenv("TABLET_WALL_UPLOAD_MODE", "loopback")
    monkeypatch.setenv("TABLET_WALL_OPERATOR_ORIGIN", ORIGIN)
    monkeypatch.setattr(media, "_loopback_peer", lambda _request: True)


def jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (64, 48), (30, 120, 200)).save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def register(client, device_id=None, number=None, **extra):
    device_id = device_id or str(uuid.uuid4())
    body = {"device_id": device_id, "width": 800, "height": 600,
            "device_type": "ipad", **extra}
    if number is not None:
        body["number"] = number
    response = client.post("/devices/register", json=body)
    assert response.status_code == 200, response.text
    return device_id


def placement(x=0):
    return {"x": x, "y": 0, "w": 1000, "h": 1000,
            "bezel": {"top": 0, "right": 0, "bottom": 0, "left": 0}}


def etag(client):
    return client.get("/api/v3/config").json()["etag"]


def rebind_request(client, target, body):
    """Rebind through the legacy route with its current config guard."""
    return client.post(
        f"/devices/{target}/rebind", json=body, headers={"If-Match": etag(client)})


# ---------------------------------------------------------------------------
# diagnostics
# ---------------------------------------------------------------------------


def test_diagnostics_is_denied_while_uploads_are_disabled_to_a_tablet_peer(client, monkeypatch):
    # The TestClient peer is "testclient", i.e. not loopback: the app itself
    # refuses a tablet-side caller even when uploads are disabled.
    assert media.upload_mode() == "disabled"
    assert client.get("/diagnostics").status_code == 403

    def must_not_verify():
        pytest.fail("verify is opt-in and must not run for a plain read")

    monkeypatch.setattr(media, "verify_integrity", must_not_verify)
    monkeypatch.setattr(media, "_loopback_peer", lambda _request: True)
    response = client.get("/diagnostics")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert "integrity" not in response.json()["media"]
    # A forwarded request is a proxy hop, not a local operator.
    assert client.get(
        "/diagnostics", headers={"X-Forwarded-For": "192.168.137.2"}
    ).status_code == 403


def test_diagnostics_while_uploads_are_disabled_accepts_only_the_proxy_credential(client, monkeypatch):
    credential = "diagnostics-credential-0123456789"
    monkeypatch.setenv("TABLET_WALL_UPLOAD_MODE", "disabled")
    monkeypatch.setenv("TABLET_WALL_OPERATOR_CREDENTIAL", credential)
    assert client.get("/diagnostics").status_code == 403
    forged = {"X-Tablet-Wall-Operator": "forged-by-a-tablet-0123456789"}
    assert client.get("/diagnostics", headers=forged).status_code == 403
    allowed = client.get("/diagnostics", headers={"X-Tablet-Wall-Operator": credential})
    assert allowed.status_code == 200, allowed.text
    assert allowed.headers["cache-control"] == "no-store"
    assert "integrity" not in allowed.json()["media"]


def test_diagnostics_is_denied_to_a_non_loopback_peer(client, monkeypatch):
    monkeypatch.setenv("TABLET_WALL_UPLOAD_MODE", "loopback")
    monkeypatch.setenv("TABLET_WALL_OPERATOR_ORIGIN", ORIGIN)
    # The TestClient peer is "testclient", i.e. not loopback: a tablet-side
    # caller must be refused by the app itself, not only by the proxy.
    assert client.get("/diagnostics").status_code == 403


def test_diagnostics_in_proxy_mode_needs_the_credential(client, monkeypatch):
    credential = "diagnostics-credential-0123456789"
    monkeypatch.setenv("TABLET_WALL_UPLOAD_MODE", "proxy")
    monkeypatch.setenv("TABLET_WALL_OPERATOR_ORIGIN", ORIGIN)
    monkeypatch.setenv("TABLET_WALL_OPERATOR_CREDENTIAL", credential)
    assert client.get("/diagnostics").status_code == 403
    forged = {"X-Tablet-Wall-Operator": "forged-by-a-tablet-0123456789"}
    assert client.get("/diagnostics", headers=forged).status_code == 403
    allowed = client.get("/diagnostics", headers={"X-Tablet-Wall-Operator": credential})
    assert allowed.status_code == 200


def test_diagnostics_reports_storage_db_clients_and_orphans(client, operator, monkeypatch, tmp_path):
    uploaded = client.post(
        "/uploads?name=a.jpg", content=jpeg(),
        headers={"Origin": ORIGIN, "Content-Type": "image/jpeg"},
    )
    assert uploaded.status_code == 201, uploaded.text
    one = register(client, wake_lock="held")
    register(client)

    report = client.get("/diagnostics")
    assert report.status_code == 200, report.text
    assert report.headers["cache-control"] == "no-store"
    body = report.json()
    store = body["media"]
    assert store["quota_bytes"] == 2 * 1024 ** 3
    assert store["reserve_bytes"] == 512 * 1024 ** 2
    assert store["used_bytes"] > 0
    assert store["free_bytes"] > 0
    assert store["assets"] == 1
    with persist._connection() as connection:
        rows = connection.execute("SELECT COUNT(*) FROM media_objects").fetchone()[0]
    assert store["objects"] == rows >= 1
    assert store["orphans"] == 0
    assert "integrity" not in store
    assert body["db"]["schema"] == persist.SCHEMA_VERSION
    assert body["db"]["bytes"] > 0
    assert body["backup"] == {"last_manifest_at": None}
    assert body["clients"]["total"] == 2
    assert body["clients"]["online"] == 0
    assert body["clients"]["wake_lock"]["held"] == 1

    stray = os.path.join(media.objects_dir(), "zz", "unlisted.bin")
    os.makedirs(os.path.dirname(stray), exist_ok=True)
    with open(stray, "wb") as handle:
        handle.write(b"left behind by a crash before commit")
    assert client.get("/diagnostics").json()["media"]["orphans"] == 1

    with client.websocket_connect("ws://127.0.0.1" + (f"/ws/device?device_id={one}&protocol=3")):
        assert client.get("/diagnostics").json()["clients"]["online"] == 1


def test_diagnostics_verify_flags_a_damaged_object(client, operator):
    uploaded = client.post(
        "/uploads?name=a.jpg", content=jpeg(),
        headers={"Origin": ORIGIN, "Content-Type": "image/jpeg"},
    )
    assert uploaded.status_code == 201, uploaded.text
    clean = client.get("/diagnostics?verify=1").json()["media"]["integrity"]
    assert clean == {"ok": True, "problems": []}

    with persist._connection() as connection:
        relative = connection.execute("SELECT path FROM media_objects LIMIT 1").fetchone()[0]
    with open(os.path.join(media.media_dir(), relative), "ab") as handle:
        handle.write(b"x")
    damaged = client.get("/diagnostics?verify=1").json()["media"]["integrity"]
    assert damaged["ok"] is False
    assert len(damaged["problems"]) >= 1


def test_diagnostics_backup_age_reads_the_newest_manifest(client, operator, monkeypatch, tmp_path):
    root = tmp_path / "backups"
    for name, stamp in (("old", "2026-10-01T00:00:00Z"), ("new", "2026-10-20T12:30:00Z")):
        (root / name).mkdir(parents=True)
        (root / name / "manifest.json").write_text(json.dumps({"created_utc": stamp}))
    (root / "broken").mkdir()
    (root / "broken" / "manifest.json").write_text("{not json")
    monkeypatch.setenv("TABLET_WALL_BACKUP_DIR", str(root))
    assert client.get("/diagnostics").json()["backup"]["last_manifest_at"] == "2026-10-20T12:30:00Z"


# ---------------------------------------------------------------------------
# wake-lock reports
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state", ["held", "released", "unsupported", "insecure", "denied"])
def test_registration_echoes_each_wake_lock_state(client, state):
    device_id = register(client, wake_lock=state)
    assert client.get("/devices").json()[device_id]["wake_lock"] == state


@pytest.mark.parametrize("bad", ["", "HELD", "held ", "x" * 100_000, 5, True, ["held"], {"a": 1}])
def test_registration_drops_an_invalid_wake_lock(client, bad):
    device_id = register(client, wake_lock=bad)
    assert "wake_lock" not in client.get("/devices").json()[device_id]


def test_reregistration_without_a_report_keeps_the_last_one(client):
    device_id = register(client, wake_lock="held")
    register(client, device_id)
    assert client.get("/devices").json()[device_id]["wake_lock"] == "held"
    register(client, device_id, wake_lock="denied")
    assert client.get("/devices").json()[device_id]["wake_lock"] == "denied"


def test_heartbeat_reports_wake_lock_and_tells_controllers_once(client):
    device_id = register(client)
    with client.websocket_connect("ws://127.0.0.1/ws/controller?protocol=3") as controller:
        assert controller.receive_json()["type"] == "snapshot"
        with client.websocket_connect("ws://127.0.0.1" + (f"/ws/device?device_id={device_id}&protocol=3")) as device:
            device.receive_json()  # welcome
            device.send_json({"type": "heartbeat", "wake_lock": "held"})
            device.send_json({"type": "heartbeat", "wake_lock": "held"})
            device.send_json({"type": "heartbeat", "wake_lock": "bogus"})
            device.send_json({"type": "heartbeat", "wake_lock": ["held"]})
            device.send_json({"type": "heartbeat", "wake_lock": "released"})
            seen = []
            while "released" not in seen:
                frame = controller.receive_json()
                if frame["type"] == "device_updated":
                    seen.append(frame["device"].get("wake_lock"))
            # One broadcast per change, none for the repeat or the bad values.
            assert seen == ["held", "released"]
    assert client.get("/devices").json()[device_id]["wake_lock"] == "released"


# ---------------------------------------------------------------------------
# origin rebinding
# ---------------------------------------------------------------------------


def lost_tablet_scenario(client):
    """Two placed tablets; the first one then returns as a brand-new identity."""
    old = register(client, number=1)
    other = register(client, number=2)
    assert client.put(f"/devices/{old}/placement", json=placement(0)).status_code == 200
    assert client.put(f"/devices/{other}/placement", json=placement(1000)).status_code == 200
    new = register(client)
    assert client.get("/devices").json()[new]["number"] == 3
    return old, other, new


def test_rebind_moves_the_placement_and_the_number(client):
    old, other, new = lost_tablet_scenario(client)
    revision = client.get("/wall").json()["revision"]

    response = rebind_request(client, new, {"replaces": old})
    assert response.status_code == 200, response.text
    assert response.json() == {
        "rebound": True, "device_id": new, "replaces": old, "number": 1,
        "placed": True, "display_records": {"profiles": 0, "calibrations": 0},
    }

    wall = client.get("/wall").json()
    assert set(wall["placements"]) == {new, other}
    assert wall["placements"][new] == {**placement(0), "device_id": new}
    assert wall["revision"] == revision + 1
    roster = client.get("/devices").json()
    assert old not in roster
    assert roster[new]["number"] == 1
    assert roster[other]["number"] == 2

    persisted = persist.load_state()
    assert set(persisted["layout"]["placements"]) == {new, other}


def test_rebind_survives_a_server_restart_in_between(client):
    old = register(client, number=1)
    assert client.put(f"/devices/{old}/placement", json=placement()).status_code == 200
    main.devices.clear()  # the roster is memory-only: a restart forgets the old record
    new = register(client)
    assert client.get("/devices").json()[new]["number"] == 1

    # The old id is only a vacant reservation now, and its number is unknown.
    missing = rebind_request(client, new, {"replaces": str(uuid.uuid4())})
    assert missing.status_code == 404

    other = register(client, number=2)
    clash = rebind_request(client, new, {"replaces": old, "number": 2})
    assert clash.status_code == 409
    assert other in client.get("/devices").json()

    response = rebind_request(client, new, {"replaces": old, "number": 4})
    assert response.status_code == 200, response.text
    assert response.json()["number"] == 4 and response.json()["placed"] is True
    assert list(client.get("/wall").json()["placements"]) == [new]


def test_rebind_refuses_a_live_old_device(client):
    old, _other, new = lost_tablet_scenario(client)
    with client.websocket_connect("ws://127.0.0.1" + (f"/ws/device?device_id={old}&protocol=3")) as socket:
        socket.receive_json()
        response = rebind_request(client, new, {"replaces": old})
        assert response.status_code == 409
    assert old in client.get("/wall").json()["placements"]


def test_rebind_refuses_unknown_or_already_placed_targets(client):
    old, other, new = lost_tablet_scenario(client)
    ghost = str(uuid.uuid4())
    assert rebind_request(client, ghost, {"replaces": old}).status_code == 404
    assert rebind_request(client, new, {"replaces": new}).status_code == 422
    assert rebind_request(client, new, {"replaces": "nope"}).status_code == 422
    assert rebind_request(client, other, {"replaces": old}).status_code == 409
    assert set(client.get("/wall").json()["placements"]) == {old, other}


def test_rebind_closes_a_connected_tablet_so_it_learns_its_new_number(client):
    old, _other, new = lost_tablet_scenario(client)
    with client.websocket_connect("ws://127.0.0.1" + (f"/ws/device?device_id={new}&protocol=3")) as socket:
        assert socket.receive_json()["number"] == 3
        assert rebind_request(client, new, {"replaces": old}).status_code == 200
        with pytest.raises(WebSocketDisconnect) as closed:
            while True:
                socket.receive_json()
        assert closed.value.code == 1000  # 4409 would park the tablet on "takeover"

    again = register(client, new, number=3)  # what the tablet re-sends: its stale 3
    assert client.get("/devices").json()[again]["number"] == 1


def test_rebind_is_a_guarded_write(client, monkeypatch):
    old, _other, new = lost_tablet_scenario(client)
    monkeypatch.setenv("TABLET_WALL_OPERATOR_ORIGIN", ORIGIN)
    assert rebind_request(client, new, {"replaces": old}).status_code == 403
    allowed = client.post(
        f"/devices/{new}/rebind", json={"replaces": old},
        headers={"Origin": ORIGIN, "If-Match": etag(client)},
    )
    assert allowed.status_code == 200


def test_rebind_requires_the_current_config_etag_before_any_mutation(client):
    old, other, new = lost_tablet_scenario(client)
    before_wall = client.get("/wall").json()
    before_roster = client.get("/devices").json()
    body = {"replaces": old}

    missing = client.post(f"/devices/{new}/rebind", json=body)
    assert missing.status_code == 428
    stale = client.post(
        f"/devices/{new}/rebind", json=body, headers={"If-Match": "not-current"})
    assert stale.status_code == 412
    assert client.get("/wall").json() == before_wall
    assert client.get("/devices").json() == before_roster

    # An unknown or malformed target stays 404 before the guard can demand a
    # header, so a stale caller cannot turn identity failure into 428/412.
    ghost = str(uuid.uuid4())
    assert client.post(f"/devices/{ghost}/rebind", json=body).status_code == 404
    assert client.post("/devices/not-a-uuid/rebind", json=body).status_code == 404

    accepted = rebind_request(client, new, body)
    assert accepted.status_code == 200, accepted.text
    assert set(client.get("/wall").json()["placements"]) == {new, other}


def test_rebind_carries_a_physical_slot_and_its_display_records(client):
    old = register(client, number=1)
    displays.save_profile(
        old, active_width_mm=100, active_height_mm=60,
        bezels={"left": 13, "top": 13, "right": 7, "bottom": 17},
        panel_pixels={"width": 2360, "height": 1640},
        label="fixture", provenance="hand-derived",
    )
    displays.save_calibration(
        old, profile_revision=1, viewport_width=600, viewport_height=800,
        dpr=1.25, orientation=0, mode="fullscreen", quarter_turn=1,
        panel_offset_mm=(10, 20), mm_per_css=(1 / 6, 1 / 6),
        anchor_edge="top-left", uncertainty_mm=0.5, method="hand-derived",
    )
    slot = {"center_x_mm": 300, "center_y_mm": 400, "mount_angle": 90,
            "nudge_x_mm": 5, "nudge_y_mm": -3, "profile_revision": 1,
            "calibration_revision": 1, "participating": True}
    config = client.get("/api/v3/config").json()
    switched = client.put(
        "/api/v3/layout",
        json={"bounds": {"x": 0, "y": 0, "width": 1200, "height": 800}, "slots": {old: slot}},
        headers={"If-Match": config["etag"]},
    )
    assert switched.status_code == 200, switched.text

    new = register(client)
    response = rebind_request(client, new, {"replaces": old})
    assert response.status_code == 200, response.text
    assert response.json()["display_records"] == {"profiles": 1, "calibrations": 1}

    config = client.get("/api/v3/config").json()
    assert config["layout"]["slots"] == {new: slot}
    by_device = {entry["device_id"] for entry in config["displays"]}
    assert by_device == {old, new}
    assert displays.calibration(new, 1)["profile_revision"] == 1
    assert displays.profile(old, 1) is not None  # history is never rewritten
    assert persist.load_state()["layout"]["slots"] == {new: slot}


def test_rebind_refuses_a_new_device_that_has_its_own_display_records(client):
    old = register(client)
    displays.save_profile(
        old, active_width_mm=100, active_height_mm=60,
        bezels={"left": 1, "top": 1, "right": 1, "bottom": 1},
        panel_pixels=None, label="old", provenance="hand-derived",
    )
    new = register(client)
    displays.save_profile(
        new, active_width_mm=90, active_height_mm=50,
        bezels={"left": 1, "top": 1, "right": 1, "bottom": 1},
        panel_pixels=None, label="new", provenance="hand-derived",
    )
    response = rebind_request(client, new, {"replaces": old})
    assert response.status_code == 409
    assert old in client.get("/devices").json()


def test_rebind_from_an_unmeasured_old_device_ignores_the_new_devices_records(client):
    old = register(client)
    new = register(client)
    displays.save_profile(
        new, active_width_mm=90, active_height_mm=50,
        bezels={"left": 1, "top": 1, "right": 1, "bottom": 1},
        panel_pixels=None, label="new", provenance="hand-derived",
    )
    response = rebind_request(client, new, {"replaces": old})
    assert response.status_code == 200, response.text
    assert response.json()["display_records"] == {"profiles": 0, "calibrations": 0}
    assert displays.profile(new, 1)["label"] == "new"
