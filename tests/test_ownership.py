"""Ownership contention and registration bounds (T2).

Two browser pages on one origin share the tablet identity stored in
``localStorage``. The server can keep only one socket per identity, so the
loser is closed with 4409 — and a client that reconnects on a timer turns that
into an endless replacement storm. These tests pin the server half: bounded
registration, bounded caps, monotonic presence expiry, and the 4409 ownership
rule itself. The client half lives in ``tests/client_image.test.js`` and the
real-browser reproduction in ``simulator/browser``.
"""

import time
import uuid

import pytest
from fastapi import WebSocketDisconnect

import main
import tabletwall.protocol as protocol


def _register(client, device_id, **overrides):
    payload = {
        "device_id": device_id,
        "width": 1024,
        "height": 768,
        "device_type": "ipad",
    }
    payload.update(overrides)
    return client.post("/devices/register", json=payload)


class TestRegistrationBounds:
    @pytest.mark.parametrize("field", ["width", "height"])
    @pytest.mark.parametrize("value", [0, -1, protocol.MAX_DEVICE_DIMENSION + 1])
    def test_implausible_viewport_is_rejected(self, client, device_id, field, value):
        response = _register(client, device_id, **{field: value})
        assert response.status_code == 422

    def test_viewport_at_the_cap_is_accepted(self, client, device_id):
        response = _register(
            client, device_id, width=protocol.MAX_DEVICE_DIMENSION,
            height=protocol.MAX_DEVICE_DIMENSION,
        )
        assert response.status_code == 200

    @pytest.mark.parametrize("value", ["", "x" * (protocol.MAX_DEVICE_TYPE_LENGTH + 1)])
    def test_device_type_length_is_bounded(self, client, device_id, value):
        assert _register(client, device_id, device_type=value).status_code == 422

    def test_device_type_cannot_carry_control_characters(self, client, device_id):
        assert _register(client, device_id, device_type="bad\tlabel").status_code == 422

    def test_wire_record_has_no_monotonic_bookkeeping(self, client, device_id):
        _register(client, device_id)
        record = client.get(f"/device/{device_id}").json()
        assert "last_seen_mono" not in record

    def test_full_roster_evicts_the_oldest_offline_record(
        self, client, device_id, monkeypatch
    ):
        monkeypatch.setattr(main, "MAX_DEVICES", 2)
        older, newer = str(uuid.uuid4()), str(uuid.uuid4())
        _register(client, older)
        _register(client, newer)
        main.devices[older]["last_seen_mono"] = 1.0
        main.devices[newer]["last_seen_mono"] = 2.0

        replacement = str(uuid.uuid4())
        assert _register(client, replacement).status_code == 200

        assert older not in main.devices
        assert {newer, replacement} <= set(main.devices)

    def test_full_roster_refuses_a_new_endpoint_when_everyone_is_online(
        self, client, device_id, monkeypatch
    ):
        monkeypatch.setattr(main, "MAX_DEVICES", 1)
        _register(client, device_id)
        main.device_sockets[device_id] = object()
        main.devices[device_id]["last_seen_mono"] = time.monotonic()

        response = _register(client, str(uuid.uuid4()))
        assert response.status_code == 429

    def test_eviction_tells_controllers_to_drop_the_old_tile(
        self, client, device_id, monkeypatch
    ):
        monkeypatch.setattr(main, "MAX_DEVICES", 1)
        with client.websocket_connect("/ws/controller?protocol=2") as controller:
            controller.receive_json()  # snapshot
            _register(client, device_id)
            assert controller.receive_json()["type"] == "device_updated"

            replacement = str(uuid.uuid4())
            _register(client, replacement)

            removal = controller.receive_json()
            assert removal == {"type": "device_removed", "device_id": device_id}
            assert controller.receive_json()["type"] == "device_updated"
        assert device_id not in main.devices
        assert replacement in main.devices


class TestCapabilityBounds:
    def test_caps_are_deduplicated_truncated_and_dropped(self, device_id, client):
        _register(client, device_id)
        long_cap = "c" * (protocol.MAX_DEVICE_CAP_LENGTH + 1)
        caps = ",".join(
            ["calibration", "image", "calibration", long_cap]
            + [f"cap{n}" for n in range(protocol.MAX_DEVICE_CAPS + 5)]
        )
        with client.websocket_connect(
            f"/ws/device?device_id={device_id}&protocol=2&caps={caps}"
        ) as socket:
            socket.receive_json()  # welcome

        recorded = main.devices[device_id]["caps"]
        assert len(recorded) <= protocol.MAX_DEVICE_CAPS
        assert recorded[:2] == ["calibration", "image"]
        assert recorded.count("calibration") == 1
        assert long_cap not in recorded
        assert all(len(cap) <= protocol.MAX_DEVICE_CAP_LENGTH for cap in recorded)


class TestPresenceExpiry:
    def test_expiry_uses_monotonic_time_not_the_wall_clock(self, client, device_id):
        _register(client, device_id)
        main.device_sockets[device_id] = object()
        # A wall clock that disagrees with the monotonic reading must not
        # decide presence: NTP can step backwards, suspend can skip forward.
        main.devices[device_id]["last_seen"] = "2000-01-01T00:00:00+00:00"
        main.devices[device_id]["last_seen_mono"] = time.monotonic()
        assert main._is_online(device_id) is True

        main.devices[device_id]["last_seen"] = "2999-01-01T00:00:00+00:00"
        main.devices[device_id]["last_seen_mono"] = (
            time.monotonic() - protocol.HEARTBEAT_TIMEOUT_S - 1
        )
        assert main._is_online(device_id) is False

    def test_a_heartbeat_refreshes_the_monotonic_reading(self, client, device_id):
        _register(client, device_id)
        with client.websocket_connect(
            f"/ws/device?device_id={device_id}&protocol=2&caps=image"
        ) as socket:
            socket.receive_json()  # welcome
            stale = time.monotonic() - 1.0
            main.devices[device_id]["last_seen_mono"] = stale

            socket.send_json({"type": "heartbeat"})
            # The GET is answered after the server has read the frame it was
            # already queued behind, the same ordering the existing presence
            # test relies on.
            assert client.get("/devices").json()[device_id]["online"] is True
            assert main.devices[device_id]["last_seen_mono"] > stale


class TestOwnership:
    def test_a_replacement_socket_closes_the_old_one_with_4409(
        self, client, device_id
    ):
        _register(client, device_id)
        url = f"/ws/device?device_id={device_id}&protocol=2&caps=image"
        with client.websocket_connect(url) as first:
            assert first.receive_json()["type"] == "welcome"
            # Version 2 replays the wall right after welcome; that frame is
            # already queued before the replacement arrives.
            assert first.receive_json()["type"] == "wall"
            with client.websocket_connect(url) as second:
                assert second.receive_json()["type"] == "welcome"
                with pytest.raises(WebSocketDisconnect) as closed:
                    first.receive_json()
                assert closed.value.code == 4409
        # The surviving socket still owns the identity.
        assert main.device_sockets == {}


@pytest.fixture
def device_id() -> str:
    return str(uuid.uuid4())
