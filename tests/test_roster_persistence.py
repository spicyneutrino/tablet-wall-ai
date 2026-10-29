"""Only durable device metadata survives process restarts."""

import json
import sqlite3
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

import main
from tabletwall import persist

DEVICE = "0f8fad5b-d9cb-469f-a165-70867728950e"
SECOND = "0f8fad5b-d9cb-469f-a165-70867728950f"


def register(client, payload, device_id=DEVICE):
    response = client.post("/devices/register", json={**payload, "device_id": device_id})
    assert response.status_code == 200, response.text


def test_restart_retains_identity_number_color_and_metadata_but_no_presence(device_payload):
    with TestClient(main.app) as client:
        register(client, device_payload)
        register(client, device_payload, SECOND)
        assert client.post(f"/devices/{DEVICE}/color", json={"color": "#123abc"}).status_code == 200
        with client.websocket_connect(f"/ws/device?device_id={DEVICE}&protocol=3&caps=image") as socket:
            socket.receive_json()
            assert client.get(f"/device/{DEVICE}").json()["online"] is True
            # The durable write must exclude negotiated and diagnostic facts.
            assert client.post(f"/devices/{DEVICE}/color", json={"color": "#123abc"}).status_code == 200
            durable = persist.load_devices()[DEVICE]
            assert set(durable) == persist._DEVICE_FIELDS
            assert durable["number"] == 1
    main.devices.clear()
    with TestClient(main.app) as restarted:
        record = restarted.get(f"/device/{DEVICE}").json()
        assert record["device_id"] == DEVICE
        assert record["number"] == 1
        assert record["width"] == device_payload["width"]
        assert record["height"] == device_payload["height"]
        assert record["type"] == device_payload["device_type"]
        assert record["color"] == "#123abc"
        assert record["online"] is False
        assert record["protocol"] is None
        assert record["caps"] == []
        assert not main.device_sockets
        register(restarted, device_payload, SECOND)
        assert restarted.get(f"/device/{SECOND}").json()["number"] == 2
        with restarted.websocket_connect(f"/ws/device?device_id={DEVICE}&protocol=2") as socket:
            assert socket.receive_json()["number"] == 1
            assert socket.receive_json()["type"] == "wall"
            assert socket.receive_json() == {"type": "set_color", "color": "#123abc"}


def test_delete_and_rebind_do_not_resurrect_old_identity(device_payload):
    with TestClient(main.app) as client:
        register(client, device_payload)
        register(client, device_payload, SECOND)
        assert client.post(f"/devices/{SECOND}/rebind", json={"replaces": DEVICE}).status_code == 200
        assert set(persist.load_devices()) == {SECOND}
    with TestClient(main.app) as client:
        assert client.get(f"/device/{SECOND}").json()["number"] == 1
        assert client.delete(f"/devices/{SECOND}").status_code == 200
    with TestClient(main.app) as client:
        assert client.get("/devices").json() == {}


@pytest.mark.parametrize("operation", ["register", "color", "all_colors", "delete"])
def test_failed_roster_write_restores_live_metadata(client, device_payload, monkeypatch, operation):
    register(client, device_payload)
    previous = deepcopy(main.devices)
    durable = persist.load_devices()
    original_record = main.devices[DEVICE]

    def fail(_records):
        raise sqlite3.OperationalError("injected write failure")

    monkeypatch.setattr(persist, "save_devices", fail)
    with pytest.raises(sqlite3.OperationalError, match="injected"):
        if operation == "register":
            client.post("/devices/register", json={**device_payload, "width": 800})
        elif operation == "color":
            client.post(f"/devices/{DEVICE}/color", json={"color": "#123abc"})
        elif operation == "all_colors":
            client.post("/devices/color", json={"color": "#123abc"})
        else:
            client.delete(f"/devices/{DEVICE}")
    assert main.devices == previous
    assert main.devices[DEVICE] is original_record
    assert persist.load_devices() == durable


@pytest.mark.parametrize("mutation", [
    {"number": True}, {"width": 0}, {"device_id": SECOND},
    {"color": "javascript:alert(1)"}, {"last_seen": "yesterday"},
    {"online": True}, {"protocol": 3}, {"last_seen_mono": 100.0},
])
def test_corrupt_durable_metadata_refuses_startup_without_rewrite(device_payload, mutation):
    with TestClient(main.app) as client:
        register(client, device_payload)
    document = persist.load_devices()
    document[DEVICE].update(mutation)
    persist.save_meta(persist._DEVICE_ROSTER_KEY, document)
    before = persist.load_meta(persist._DEVICE_ROSTER_KEY)
    with pytest.raises(persist.SchemaError, match="device roster"):
        with TestClient(main.app):
            pass
    assert persist.load_meta(persist._DEVICE_ROSTER_KEY) == before


def test_missing_roster_in_old_database_is_empty_and_wall_is_unchanged():
    persist.save_state(main._fresh_wall())
    before = persist.load_state()
    assert persist.load_devices() == {}
    assert persist.load_state() == before


def test_ephemeral_fields_cannot_be_serialized(device_payload):
    with TestClient(main.app) as client:
        register(client, device_payload)
        main.devices[DEVICE].update({"online": True, "socket": object(), "connection_id": "old"})
        persist.save_devices(main.devices)
    connection = sqlite3.connect(persist.db_path())
    try:
        document = json.loads(connection.execute(
            "SELECT value FROM schema_meta WHERE key = ?", (persist._DEVICE_ROSTER_KEY,)
        ).fetchone()[0])
    finally:
        connection.close()
    assert "online" not in document[DEVICE]
    assert "socket" not in document[DEVICE]
    assert "connection_id" not in document[DEVICE]


@pytest.mark.parametrize("document", [None, [], True, "invalid"])
def test_invalid_top_level_roster_refuses_startup_without_overwriting(document):
    persist.save_meta(persist._DEVICE_ROSTER_KEY, document)
    with pytest.raises(persist.SchemaError, match="device roster"):
        with TestClient(main.app):
            pass
    assert persist.load_meta(persist._DEVICE_ROSTER_KEY) == document


@pytest.mark.parametrize("operation", ["delete", "rebind"])
@pytest.mark.parametrize("stage", ["wall_before", "wall_after", "roster_after"])
def test_combined_mutations_roll_back_wall_roster_profiles_and_notifications(
    client, device_payload, monkeypatch, operation, stage,
):
    from tabletwall import displays

    register(client, device_payload)
    register(client, device_payload, SECOND)
    assert client.put(f"/devices/{DEVICE}/placement", json={
        "x": 0, "y": 0, "w": 1000, "h": 1000,
    }).status_code == 200
    displays.save_profile(
        DEVICE, active_width_mm=100, active_height_mm=60,
        bezels={"left": 0, "top": 0, "right": 0, "bottom": 0},
        panel_pixels=None, label="panel", provenance="ruler",
    )
    before_wall = deepcopy(main.wall)
    before_devices = deepcopy(main.devices)
    before_durable = persist.load_devices()
    before_database = persist.load_state()
    save_wall, save_roster = main.save_state, persist.save_devices

    def fail_wall(document):
        if stage == "wall_after":
            save_wall(document)
        raise sqlite3.OperationalError("injected transaction failure")

    def fail_roster(document):
        save_roster(document)
        raise sqlite3.OperationalError("injected transaction failure")

    socket_id = DEVICE if operation == "delete" else SECOND
    with client.websocket_connect(f"/ws/device?device_id={socket_id}&protocol=2") as socket:
        socket.receive_json()
        socket.receive_json()
        before_devices = deepcopy(main.devices)
        before_durable = persist.load_devices()
        with client.websocket_connect("/ws/controller?protocol=2") as controller:
            controller.receive_json()
            with monkeypatch.context() as patch:
                if stage.startswith("wall"):
                    patch.setattr(main, "save_state", fail_wall)
                else:
                    patch.setattr(persist, "save_devices", fail_roster)
                with pytest.raises(sqlite3.OperationalError, match="injected"):
                    if operation == "delete":
                        client.delete(f"/devices/{DEVICE}")
                    else:
                        client.post(f"/devices/{SECOND}/rebind", json={"replaces": DEVICE})
            assert main.wall == before_wall
            assert main.devices == before_devices
            assert socket_id in main.device_sockets
            assert persist.load_devices() == before_durable
            assert persist.load_state() == before_database
            assert displays.latest_profile(SECOND) is None
            assert client.post(f"/devices/{socket_id}/color", json={"color": "#abcdef"}).status_code == 200
            assert socket.receive_json() == {"type": "set_color", "color": "#abcdef"}
            assert controller.receive_json()["type"] == "device_updated"


def test_checkpoint_saves_heartbeat_contact_and_restores_it_offline(client, device_payload):
    from tabletwall import state

    register(client, device_payload)
    initial = persist.load_devices()[DEVICE]["last_seen"]
    state._touch_device(DEVICE)
    latest = main.devices[DEVICE]["last_seen"]
    assert latest != initial
    assert persist.load_devices()[DEVICE]["last_seen"] == initial
    state.checkpoint_devices()
    assert persist.load_devices()[DEVICE]["last_seen"] == latest
    state.restore_devices()
    assert main._device_record(DEVICE)["last_seen"] == latest
    assert main._device_record(DEVICE)["online"] is False


def test_checkpoint_failure_is_logged_and_next_attempt_can_succeed(client, device_payload, monkeypatch, caplog):
    from tabletwall import state

    register(client, device_payload)
    state._touch_device(DEVICE)
    with monkeypatch.context() as patch:
        def fail(_records):
            raise sqlite3.OperationalError("disk unavailable")

        patch.setattr(persist, "save_devices", fail)
        state.checkpoint_devices()
    assert "could not checkpoint device metadata" in caplog.text
    state.checkpoint_devices()
    assert persist.load_devices()[DEVICE]["last_seen"] == main.devices[DEVICE]["last_seen"]
