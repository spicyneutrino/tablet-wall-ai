"""Realtime contract tests for the WebSocket layer described in PROTOCOL.md.

The HTTP colour/delete commands live here as well because they are only
meaningful next to a live socket: ``delivered`` and the ``device_online`` /
``device_offline`` / ``device_updated`` frames are two halves of the same
contract.

``TestClient.websocket_connect`` is context-manager based: entering the block
performs the handshake, and exiting it simulates a clean disconnect.
"""

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import main

DEVICE_ID = "0f8fad5b-d9cb-469f-a165-70867728950e"


def device_url(device_id: str = DEVICE_ID) -> str:
    return f"/ws/device?device_id={device_id}"


class TestControllerSocket:
    def test_snapshot_is_the_first_frame(self, client):
        with client.websocket_connect("/ws/controller") as controller:
            frame = controller.receive_json()

        assert frame["type"] == "snapshot"
        assert frame["devices"] == []

    def test_snapshot_lists_the_roster(self, client, device_payload):
        client.post("/devices/register", json=device_payload)

        with client.websocket_connect("/ws/controller") as controller:
            frame = controller.receive_json()

        assert frame["type"] == "snapshot"
        assert [device["device_id"] for device in frame["devices"]] == [DEVICE_ID]
        assert frame["devices"][0]["online"] is False

    def test_device_connect_marks_it_online(self, client, device_payload):
        client.post("/devices/register", json=device_payload)

        with client.websocket_connect("/ws/controller") as controller:
            assert controller.receive_json()["type"] == "snapshot"

            with client.websocket_connect(device_url()) as device:
                welcome = device.receive_json()
                event = controller.receive_json()

                assert welcome["type"] == "welcome"
                assert event["type"] == "device_online"
                assert event["device"]["device_id"] == DEVICE_ID
                assert event["device"]["online"] is True
                assert client.get("/devices").json()[DEVICE_ID]["online"] is True

    def test_device_accepts_a_long_browser_dpr(self, client, device_payload):
        """Browsers serialize devicePixelRatio with full double precision."""
        client.post("/devices/register", json=device_payload)
        url = (
            device_url()
            + "&protocol=3&caps=calibration,image,physical"
            + "&w=768&h=393&dpr=1.4666666984558105&orientation=0&mode=tab"
        )

        with client.websocket_connect(url) as device:
            welcome = device.receive_json()

        assert welcome["type"] == "welcome"
        assert welcome["protocol"] == 3

    def test_device_disconnect_marks_it_offline_but_keeps_the_roster(
        self, client, device_payload
    ):
        client.post("/devices/register", json=device_payload)

        with client.websocket_connect("/ws/controller") as controller:
            controller.receive_json()  # snapshot

            with client.websocket_connect(device_url()) as device:
                device.receive_json()  # welcome
                controller.receive_json()  # device_online

            # Leaving the `with` block is a clean disconnect.
            event = controller.receive_json()
            assert event["type"] == "device_offline"
            assert event["device_id"] == DEVICE_ID
            assert event["last_seen"]
            assert client.get("/devices").json()[DEVICE_ID]["online"] is False

        roster = client.get("/devices").json()
        assert DEVICE_ID in roster, "disconnecting must not remove the device"

    def test_second_socket_replaces_the_first(self, client, device_payload):
        client.post("/devices/register", json=device_payload)

        with client.websocket_connect("/ws/controller") as controller:
            controller.receive_json()  # snapshot

            with client.websocket_connect(device_url()) as first:
                first.receive_json()  # welcome
                controller.receive_json()  # device_online

                with client.websocket_connect(device_url()) as second:
                    second.receive_json()  # welcome on the replacement
                    controller.receive_json()  # device_online for the new socket

                    with pytest.raises(WebSocketDisconnect) as exc_info:
                        first.receive_json()
                    assert exc_info.value.code == 4409

                    # Walk away from the replaced socket while the replacement
                    # stays open. Its task must not broadcast device_offline,
                    # so the next controller frame is the re-registration's
                    # device_updated.
                    first.close()
                    client.post("/devices/register", json=device_payload)
                    event = controller.receive_json()

                    assert event["type"] == "device_updated"
                    assert event["device"]["device_id"] == DEVICE_ID
                    assert event["device"]["online"] is True


class TestDeviceSocket:
    def test_replaced_socket_cannot_consume_clock_sample(self, client, device_payload):
        client.post("/devices/register", json=device_payload)
        record = main.devices[DEVICE_ID]
        record["clock_pending"] = {
            "probe": {"c0": 1.0, "s1": 2.0, "s2": 3.0}
        }
        replaced = SimpleNamespace(receive=AsyncMock(side_effect=[
            {"type": "websocket.receive",
             "text": '{"type":"clock_result","id":"probe","c3":4.0}'},
            {"type": "websocket.disconnect"},
        ]))
        main.device_sockets[DEVICE_ID] = object()

        asyncio.run(main._device_loop(replaced, DEVICE_ID))

        assert "probe" in record["clock_pending"]
        assert "clock_samples" not in record
        assert "clock" not in record

    def test_welcome_carries_the_heartbeat_interval(self, client, device_payload):
        client.post("/devices/register", json=device_payload)

        with client.websocket_connect(device_url()) as device:
            welcome = device.receive_json()

        assert welcome == {
            "type": "welcome",
            "device_id": DEVICE_ID,
            "heartbeat_interval_ms": 5000,
        }

    def test_assigned_color_is_replayed_right_after_welcome(
        self, client, device_payload
    ):
        client.post("/devices/register", json=device_payload)
        client.post(f"/devices/{DEVICE_ID}/color", json={"color": "#3b82f6"})

        with client.websocket_connect(device_url()) as device:
            assert device.receive_json()["type"] == "welcome"
            assert device.receive_json() == {
                "type": "set_color",
                "color": "#3b82f6",
            }

    @pytest.mark.parametrize(
        "query",
        [
            "not-a-uuid",
            "",
            # Well formed, but not a version 4 UUID.
            "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        ],
    )
    def test_malformed_device_id_closes_with_4400(self, client, query):
        with client.websocket_connect(f"/ws/device?device_id={query}") as device:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                device.receive_json()

        assert exc_info.value.code == 4400

    def test_missing_device_id_closes_with_4400(self, client):
        with client.websocket_connect("/ws/device") as device:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                device.receive_json()

        assert exc_info.value.code == 4400

    def test_unregistered_device_id_closes_with_4404(self, client):
        with client.websocket_connect(device_url(str(uuid.uuid4()))) as device:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                device.receive_json()

        assert exc_info.value.code == 4404

    def test_unrecognised_frames_are_ignored_not_fatal(self, client, device_payload):
        client.post("/devices/register", json=device_payload)

        with client.websocket_connect(device_url()) as device:
            device.receive_json()  # welcome

            # Old enough to be recognisable, but well inside the heartbeat
            # timeout so the sweeper leaves the socket alone.
            stale = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
            main.devices[DEVICE_ID]["last_seen"] = stale

            device.send_text("this is not json at all")
            device.send_json({"type": "something-else", "payload": 1})
            device.send_json({"type": "heartbeat"})

            # The socket survived the junk and the heartbeat refreshed
            # last_seen (the GET is queued after the frames, so the server has
            # already processed them by the time it answers).
            refreshed = client.get("/devices").json()[DEVICE_ID]["last_seen"]
            assert refreshed != stale

        assert client.get("/devices").json()[DEVICE_ID]["online"] is False


class TestColorCommands:
    def test_color_reaches_a_live_device(self, client, device_payload):
        client.post("/devices/register", json=device_payload)

        with client.websocket_connect(device_url()) as device:
            device.receive_json()  # welcome
            response = client.post(
                f"/devices/{DEVICE_ID}/color", json={"color": "3B82f6"}
            )

            assert response.status_code == 200
            assert response.json() == {
                "device_id": DEVICE_ID,
                "color": "#3b82f6",
                "delivered": True,
            }
            assert device.receive_json() == {
                "type": "set_color",
                "color": "#3b82f6",
            }

        assert client.get("/devices").json()[DEVICE_ID]["color"] == "#3b82f6"

    def test_color_persists_while_offline_and_replays_on_reconnect(
        self, client, device_payload
    ):
        client.post("/devices/register", json=device_payload)

        response = client.post(f"/devices/{DEVICE_ID}/color", json={"color": "#ABCDEF"})

        assert response.status_code == 200
        assert response.json() == {
            "device_id": DEVICE_ID,
            "color": "#abcdef",
            "delivered": False,
        }
        assert client.get("/devices").json()[DEVICE_ID]["color"] == "#abcdef"

        with client.websocket_connect(device_url()) as device:
            assert device.receive_json()["type"] == "welcome"
            assert device.receive_json() == {"type": "set_color", "color": "#abcdef"}

    def test_color_survives_reregistration(self, client, device_payload):
        client.post("/devices/register", json=device_payload)
        client.post(f"/devices/{DEVICE_ID}/color", json={"color": "#3b82f6"})
        client.post("/devices/register", json=device_payload)

        assert client.get("/devices").json()[DEVICE_ID]["color"] == "#3b82f6"

    @pytest.mark.parametrize(
        "color",
        ["blue", "#12345g", "#12345", "#1234567", "123456789"],
    )
    def test_malformed_color_is_rejected_with_422(self, client, device_payload, color):
        client.post("/devices/register", json=device_payload)

        response = client.post(f"/devices/{DEVICE_ID}/color", json={"color": color})

        assert response.status_code == 422
        assert client.get("/devices").json()[DEVICE_ID]["color"] is None

    def test_malformed_color_for_all_devices_is_rejected_with_422(self, client):
        response = client.post("/devices/color", json={"color": "nope"})

        assert response.status_code == 422

    def test_color_for_unknown_device_is_404(self, client):
        response = client.post(
            f"/devices/{uuid.uuid4()}/color", json={"color": "#3b82f6"}
        )

        assert response.status_code == 404

    def test_color_to_every_device(self, client, device_payload):
        other_id = str(uuid.uuid4())
        client.post("/devices/register", json=device_payload)
        client.post("/devices/register", json={**device_payload, "device_id": other_id})

        with client.websocket_connect(device_url()) as device:
            device.receive_json()  # welcome

            with client.websocket_connect("/ws/controller") as controller:
                controller.receive_json()  # snapshot
                response = client.post("/devices/color", json={"color": "aAbBcC"})

                assert response.status_code == 200
                assert response.json() == {
                    "color": "#aabbcc",
                    "updated": 2,
                    "delivered": 1,
                }
                assert device.receive_json() == {
                    "type": "set_color",
                    "color": "#aabbcc",
                }
                events = [controller.receive_json(), controller.receive_json()]

        assert {event["type"] for event in events} == {"device_updated"}
        roster = client.get("/devices").json()
        assert roster[DEVICE_ID]["color"] == "#aabbcc"
        assert roster[other_id]["color"] == "#aabbcc"

    def test_color_to_an_empty_roster(self, client):
        response = client.post("/devices/color", json={"color": "#3b82f6"})

        assert response.status_code == 200
        assert response.json() == {"color": "#3b82f6", "updated": 0, "delivered": 0}


class TestSingleDeviceRecord:
    def test_returns_the_real_record(self, client, device_payload):
        assert client.get(f"/device/{DEVICE_ID}").status_code == 404

        client.post("/devices/register", json=device_payload)
        response = client.get(f"/device/{DEVICE_ID}")

        assert response.status_code == 200
        record = response.json()
        assert record["device_id"] == DEVICE_ID
        assert record["width"] == 1024
        assert record["height"] == 768
        assert record["type"] == "ipad"
        assert record["color"] is None
        assert record["online"] is False
        assert datetime.fromisoformat(record["last_seen"]).tzinfo is not None

    @pytest.mark.parametrize("device_id", ["not-a-uuid", "0f8fad5b-d9cb-469f-a165-70867728950f"])
    def test_unknown_device_is_404(self, client, device_id):
        assert client.get(f"/device/{device_id}").status_code == 404


class TestDelete:
    def test_delete_refuses_a_device_with_an_owned_socket(self, client, device_payload):
        client.post("/devices/register", json=device_payload)
        with client.websocket_connect("/ws/controller") as controller:
            controller.receive_json()
            with client.websocket_connect(device_url()) as device:
                device.receive_json()
                controller.receive_json()
                response = client.delete(f"/devices/{DEVICE_ID}")
                assert response.status_code == 409
                assert response.json()["detail"]["code"] == "old_connected"
                assert client.get(f"/device/{DEVICE_ID}").json()["online"] is True
                client.post(f"/devices/{DEVICE_ID}/color", json={"color": "#123456"}).raise_for_status()
                assert device.receive_json() == {"type": "set_color", "color": "#123456"}
                assert controller.receive_json()["type"] == "device_updated"

    def test_delete_of_an_offline_device_announces_only_removal(
        self, client, device_payload
    ):
        """No socket to close, so there is no device_offline to send."""
        client.post("/devices/register", json=device_payload)

        with client.websocket_connect("/ws/controller") as controller:
            controller.receive_json()  # snapshot

            assert client.delete(f"/devices/{DEVICE_ID}").status_code == 200

            assert controller.receive_json() == {
                "type": "device_removed",
                "device_id": DEVICE_ID,
            }

    def test_delete_unknown_device_is_404(self, client):
        response = client.delete(f"/devices/{uuid.uuid4()}")

        assert response.status_code == 404

    def test_delete_malformed_device_id_is_404(self, client):
        assert client.delete("/devices/not-a-uuid").status_code == 404


class TestPresence:
    def test_heartbeat_timeout_closes_the_socket_with_4408(
        self, device_payload, monkeypatch
    ):
        # Patch before the app starts so the sweeper reads the short timings
        # from the very first pass of its loop.
        monkeypatch.setattr(main.hub, "HEARTBEAT_TIMEOUT_S", 0.3)
        monkeypatch.setattr(main.hub, "SWEEP_INTERVAL_S", 0.05)

        with TestClient(main.app) as client:
            client.post("/devices/register", json=device_payload)

            with client.websocket_connect("/ws/controller") as controller:
                controller.receive_json()  # snapshot

                with client.websocket_connect(device_url()) as device:
                    assert device.receive_json()["type"] == "welcome"
                    assert controller.receive_json()["type"] == "device_online"
                    assert client.get("/devices").json()[DEVICE_ID]["online"] is True

                    # No heartbeat is ever sent, so the sweeper must give up.
                    deadline = time.monotonic() + 5.0
                    while (
                        time.monotonic() < deadline
                        and DEVICE_ID in main.device_sockets
                    ):
                        time.sleep(0.01)
                    assert DEVICE_ID not in main.device_sockets, (
                        "the sweeper never closed the timed-out socket"
                    )

                    with pytest.raises(WebSocketDisconnect) as exc_info:
                        device.receive_json()
                    assert exc_info.value.code == 4408

                    # The sweep also has to tell the controllers about it.
                    event = controller.receive_json()
                    assert event["type"] == "device_offline"
                    assert event["device_id"] == DEVICE_ID

                assert client.get("/devices").json()[DEVICE_ID]["online"] is False
                assert DEVICE_ID in client.get("/devices").json()
