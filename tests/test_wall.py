"""Version-2 contract tests: negotiation, wall state, and placements.

These cover PROTOCOL.md's "Version 2 — wall, placements, and scenes" section
plus the protocol negotiation on both sockets. Version 1 is frozen, so a
recurring theme here is proving that version-1 sockets never see a version-2
frame (and that their ``welcome`` / ``snapshot`` shapes did not change).

``TestClient.websocket_connect`` is context-manager based: entering the block
performs the handshake, and exiting it simulates a clean disconnect.
"""

import re
import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import main
from tabletwall import persist

DEVICE_ID = "0f8fad5b-d9cb-469f-a165-70867728950e"
SECOND_ID = str(uuid.uuid4())
THIRD_ID = str(uuid.uuid4())

ZERO_BEZEL = {"top": 0, "right": 0, "bottom": 0, "left": 0}


def config_etag(client) -> str:
    return client.get("/api/v3/config").json()["etag"]


def device_url(
    device_id: str = DEVICE_ID, protocol: object = None, caps: str | None = None
) -> str:
    url = f"/ws/device?device_id={device_id}"
    if protocol is not None:
        url += f"&protocol={protocol}"
    if caps is not None:
        url += f"&caps={caps}"
    return url


def controller_url(protocol: object = None) -> str:
    if protocol is None:
        return "/ws/controller"
    return f"/ws/controller?protocol={protocol}"


def register(client, device_payload, device_id: str) -> None:
    response = client.post(
        "/devices/register", json={**device_payload, "device_id": device_id}
    )
    assert response.status_code == 200


def wall_state(client) -> dict:
    response = client.get("/wall")
    assert response.status_code == 200
    return response.json()


class TestDeviceNegotiation:
    def test_absent_protocol_means_version_1(self, client, device_payload):
        """A cached client.js that predates the version param keeps working."""
        register(client, device_payload, DEVICE_ID)

        with client.websocket_connect(device_url()) as device:
            welcome = device.receive_json()

        assert welcome == {
            "type": "welcome",
            "device_id": DEVICE_ID,
            "heartbeat_interval_ms": 5000,
        }

    @pytest.mark.parametrize("value", [None, 1])
    def test_version_1_welcome_has_no_extra_keys(self, client, device_payload, value):
        """Explicit ``protocol=1`` is byte-for-byte today's welcome too."""
        register(client, device_payload, DEVICE_ID)

        with client.websocket_connect(device_url(protocol=value)) as device:
            welcome = device.receive_json()

        assert welcome == {
            "type": "welcome",
            "device_id": DEVICE_ID,
            "heartbeat_interval_ms": 5000,
        }

    def test_protocol_2_welcome_carries_version_and_server_caps(
        self, client, device_payload
    ):
        register(client, device_payload, DEVICE_ID)

        with client.websocket_connect(device_url(protocol=2)) as device:
            welcome = device.receive_json()

        assert welcome["type"] == "welcome"
        assert welcome["device_id"] == DEVICE_ID
        assert welcome["heartbeat_interval_ms"] == 5000
        assert welcome["protocol"] == 2
        assert welcome["server_caps"] == ["calibration", "image"]

    @pytest.mark.parametrize("bad", ["4", "0", "-1", "2.5", "garbage", ""])
    def test_unsupported_device_protocol_closes_with_4426(
        self, client, device_payload, bad
    ):
        """Accepted first, then closed, so a browser can observe the code."""
        register(client, device_payload, DEVICE_ID)

        with client.websocket_connect(device_url(protocol=bad)) as device:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                device.receive_json()

        assert exc_info.value.code == 4426

    @pytest.mark.parametrize("bad", ["4", "garbage"])
    def test_unsupported_controller_protocol_closes_with_4426(self, client, bad):
        with client.websocket_connect(controller_url(bad)) as controller:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                controller.receive_json()

        assert exc_info.value.code == 4426

    def test_device_record_starts_with_no_protocol(self, client, device_payload):
        register(client, device_payload, DEVICE_ID)

        entry = client.get(f"/device/{DEVICE_ID}").json()

        assert entry["protocol"] is None
        assert entry["caps"] == []

    def test_v1_socket_records_protocol_1_and_empty_caps(self, client, device_payload):
        register(client, device_payload, DEVICE_ID)

        with client.websocket_connect(device_url()) as device:
            device.receive_json()  # welcome
            entry = client.get(f"/device/{DEVICE_ID}").json()

        assert entry["protocol"] == 1
        assert entry["caps"] == []

    def test_v2_socket_records_protocol_and_caps(self, client, device_payload):
        register(client, device_payload, DEVICE_ID)

        with client.websocket_connect(
            device_url(protocol=2, caps="calibration,image")
        ) as device:
            device.receive_json()  # welcome
            device.receive_json()  # wall
            entry = client.get(f"/device/{DEVICE_ID}").json()

        assert entry["protocol"] == 2
        assert entry["caps"] == ["calibration", "image"]

    def test_empty_caps_stay_empty(self, client, device_payload):
        register(client, device_payload, DEVICE_ID)

        with client.websocket_connect(device_url(protocol=2, caps="")) as device:
            device.receive_json()  # welcome
            device.receive_json()  # wall
            entry = client.get(f"/device/{DEVICE_ID}").json()

        assert entry["caps"] == []

    def test_reregistration_preserves_negotiated_protocol(self, client, device_payload):
        """The client re-registers before every connection attempt; the record
        must not flap back to "no protocol" while its v2 socket is open."""
        register(client, device_payload, DEVICE_ID)

        with client.websocket_connect(
            device_url(protocol=2, caps="calibration")
        ) as device:
            device.receive_json()  # welcome
            device.receive_json()  # wall
            register(client, device_payload, DEVICE_ID)
            entry = client.get(f"/device/{DEVICE_ID}").json()

        assert entry["protocol"] == 2
        assert entry["caps"] == ["calibration"]


class TestWallFramesToDevice:
    @pytest.mark.parametrize("protocol_arg", [None, 1])
    def test_v1_device_never_receives_wall(
        self, client, device_payload, protocol_arg
    ):
        """A wall change happens while a v1 device sits connected; the next
        frame it receives must be the colour replay, not a ``wall`` frame."""
        register(client, device_payload, DEVICE_ID)

        with client.websocket_connect(device_url(protocol=protocol_arg)) as device:
            welcome = device.receive_json()
            assert welcome["type"] == "welcome"

            assert client.put("/wall", json={"width": 3000}).status_code == 200

            client.post(f"/devices/{DEVICE_ID}/color", json={"color": "#3b82f6"})
            assert device.receive_json() == {
                "type": "set_color",
                "color": "#3b82f6",
            }

    def test_v2_device_receives_wall_after_welcome(self, client, device_payload):
        register(client, device_payload, DEVICE_ID)

        with client.websocket_connect(device_url(protocol=2)) as device:
            welcome = device.receive_json()
            frame = device.receive_json()

        assert welcome["type"] == "welcome"
        assert frame == {
            "type": "wall",
            "revision": 0,
            "generation": wall_state(client)["generation"],
            "scene": {"content": {"type": "color"}, "layout": "active"},
            "wall": {"width": 2000, "height": 1000},
            "placement": None,
        }

    def test_wall_frame_carries_the_placement(self, client, device_payload):
        register(client, device_payload, DEVICE_ID)
        client.put(
            f"/devices/{DEVICE_ID}/placement",
            json={"x": 10, "y": 20, "w": 1000, "h": 800},
        )

        with client.websocket_connect(device_url(protocol=2)) as device:
            device.receive_json()  # welcome
            frame = device.receive_json()

        assert frame["revision"] == 1
        # The example frame carries no device_id: it is already about the
        # receiving device.
        assert frame["placement"] == {
            "x": 10,
            "y": 20,
            "w": 1000,
            "h": 800,
            "bezel": dict(ZERO_BEZEL),
        }

    def test_wall_replays_on_reconnect(self, client, device_payload):
        """A tablet restores the current wall without being told again."""
        register(client, device_payload, DEVICE_ID)
        client.put(
            f"/devices/{DEVICE_ID}/placement",
            json={"x": 0, "y": 0, "w": 500, "h": 500},
        )

        with client.websocket_connect(device_url(protocol=2)) as device:
            device.receive_json()  # welcome
            first = device.receive_json()
        assert first["revision"] == 1

        # The wall changes while the tablet is away.
        client.put("/wall", json={"width": 3000, "height": 1500})

        with client.websocket_connect(device_url(protocol=2)) as device:
            device.receive_json()  # welcome
            second = device.receive_json()

        assert second["revision"] == 2
        assert second["revision"] > first["revision"]
        assert second["wall"] == {"width": 3000, "height": 1500}
        # The placement survives the disconnect (PROTOCOL.md: "The device keeps
        # its placement across a reconnect").
        assert second["placement"] == {
            "x": 0,
            "y": 0,
            "w": 500,
            "h": 500,
            "bezel": dict(ZERO_BEZEL),
        }

    def test_wall_change_is_pushed_to_a_connected_v2_device(
        self, client, device_payload
    ):
        register(client, device_payload, DEVICE_ID)

        with client.websocket_connect(
            device_url(protocol=2, caps="calibration")
        ) as device:
            device.receive_json()  # welcome
            initial = device.receive_json()
            assert initial["revision"] == 0

            assert client.put(
                "/scene", json={"content": {"type": "calibration"}}
            ).status_code == 200
            pushed = device.receive_json()

        assert pushed == {
            "type": "wall",
            "revision": 1,
            "generation": wall_state(client)["generation"],
            "scene": {"content": {"type": "calibration"}, "layout": "active"},
            "wall": {"width": 2000, "height": 1000},
            "placement": None,
        }

    def test_content_downgrades_without_the_calibration_cap(
        self, client, device_payload
    ):
        register(client, device_payload, DEVICE_ID)
        client.put("/scene", json={"content": {"type": "calibration"}})
        client.put(
            f"/devices/{DEVICE_ID}/placement",
            json={"x": 0, "y": 0, "w": 1000, "h": 1000},
        )

        with client.websocket_connect(device_url(protocol=2)) as device:
            device.receive_json()  # welcome
            frame = device.receive_json()

        assert frame["scene"]["content"] == {"type": "color"}, (
            "a device without the calibration cap must never be asked "
            "to render a calibration pattern"
        )
        assert frame["revision"] == 2
        assert frame["placement"] is not None

    def test_calibration_cap_keeps_calibration_content(self, client, device_payload):
        register(client, device_payload, DEVICE_ID)
        client.put("/scene", json={"content": {"type": "calibration"}})

        with client.websocket_connect(
            device_url(protocol=2, caps="calibration")
        ) as device:
            device.receive_json()  # welcome
            frame = device.receive_json()

        assert frame["scene"]["content"] == {"type": "calibration"}


class TestControllerWall:
    def test_v1_snapshot_has_no_wall_key(self, client, device_payload):
        register(client, device_payload, DEVICE_ID)

        with client.websocket_connect(controller_url()) as controller:
            frame = controller.receive_json()

        assert frame["type"] == "snapshot"
        # Exactly today's snapshot: no version-2 keys at all.
        assert set(frame) == {"type", "devices"}
        assert [d["device_id"] for d in frame["devices"]] == [DEVICE_ID]

    def test_v1_controller_never_gets_wall_updated(self, client, device_payload):
        """A wall change happens, then a device event. If ``wall_updated``
        were ever broadcast to a v1 controller it would arrive first."""
        with client.websocket_connect(controller_url()) as controller:
            controller.receive_json()  # snapshot

            assert client.put("/wall", json={"width": 3000}).status_code == 200
            register(client, device_payload, DEVICE_ID)

            event = controller.receive_json()

        assert event["type"] == "device_updated"

    def test_v2_snapshot_carries_the_wall(self, client, device_payload):
        register(client, device_payload, DEVICE_ID)

        with client.websocket_connect(controller_url(protocol=2)) as controller:
            frame = controller.receive_json()

        assert frame["type"] == "snapshot"
        assert frame["wall"] == {
            "width": 2000,
            "height": 1000,
            "scene": {"content": {"type": "color"}, "layout": "active"},
            "revision": 0,
            "generation": wall_state(client)["generation"],
            "placements": {},
        }
        assert [d["device_id"] for d in frame["devices"]] == [DEVICE_ID]

    def test_snapshot_shape_differs_between_v1_and_v2(
        self, client, device_payload
    ):
        register(client, device_payload, DEVICE_ID)

        with client.websocket_connect(controller_url()) as controller:
            v1 = controller.receive_json()
        with client.websocket_connect(controller_url(protocol=2)) as controller:
            v2 = controller.receive_json()

        assert "wall" not in v1
        assert "wall" in v2
        # Only the wall differs: the roster is the same in both.
        assert v1["devices"] == v2["devices"]

    def test_wall_updated_is_broadcast_on_every_change(self, client):
        with client.websocket_connect(controller_url(protocol=2)) as controller:
            controller.receive_json()  # snapshot

            assert client.put("/wall", json={"width": 1500}).status_code == 200
            first = controller.receive_json()

            assert client.put(
                "/scene", json={"content": {"type": "calibration"}}
            ).status_code == 200
            second = controller.receive_json()

        generation = wall_state(client)["generation"]
        assert first == {
            "type": "wall_updated",
            "wall": {
                "width": 1500,
                "height": 1000,
                "scene": {"content": {"type": "color"}, "layout": "active"},
                "revision": 1,
                "generation": generation,
                "placements": {},
            },
        }
        assert second == {
            "type": "wall_updated",
            "wall": {
                "width": 1500,
                "height": 1000,
                "scene": {"content": {"type": "calibration"}, "layout": "active"},
                "revision": 2,
                "generation": generation,
                "placements": {},
            },
        }


class TestGetWall:
    def test_default_wall_state(self, client):
        state = client.get("/wall").json()

        # The whole state in one read, with the generation isolated because
        # its value is minted fresh on every server start (only its shape is
        # part of the contract here).
        generation = state.pop("generation")
        assert state == {
            "width": 2000,
            "height": 1000,
            "scene": {"content": {"type": "color"}, "layout": "active"},
            "revision": 0,
            "placements": {},
        }
        assert re.fullmatch(r"[0-9a-f]{8}", generation), (
            "a fresh server starts a fresh generation lineage"
        )


class TestPutWall:
    def test_put_wall_accepts_any_subset(self, client):
        generation = wall_state(client)["generation"]

        response = client.put("/wall", json={"width": 3000})
        assert response.status_code == 200
        assert response.json() == {
            "width": 3000,
            "height": 1000,
            "scene": {"content": {"type": "color"}, "layout": "active"},
            "revision": 1,
            "generation": generation,
            "placements": {},
        }

        client.put("/wall", json={"height": 500})
        assert client.put(
            "/scene", json={"content": {"type": "calibration"}}
        ).status_code == 200

        assert wall_state(client) == {
            "width": 3000,
            "height": 500,
            "scene": {"content": {"type": "calibration"}, "layout": "active"},
            "revision": 3,
            "generation": generation,
            "placements": {},
        }

    @pytest.mark.parametrize(
        "body",
        [
            {"width": 0},
            {"width": -1},
            {"height": 0},
            {"height": -10},
            {"width": "wide"},
            {"width": 1.5},
            # ``mode`` is content, not layout: it now belongs to PUT /scene, so
            # sending it here is an unknown key rather than a bad value. It is
            # still 422 either way, and still must not mutate (the valid and
            # invalid content values themselves are covered by TestPutScene).
            {"mode": "rainbow"},
            {"mode": 5},
        ],
    )
    def test_put_wall_rejects_bad_values_with_422(self, client, body):
        before = wall_state(client)

        response = client.put("/wall", json=body)

        assert response.status_code == 422
        assert wall_state(client) == before, "a rejected update must not mutate"


class TestPutScene:
    """``PUT /scene``: content only, with the layout left untouched."""

    def test_put_scene_replaces_the_content_and_bumps_the_revision(self, client):
        generation = wall_state(client)["generation"]

        response = client.put("/scene", json={"content": {"type": "calibration"}})

        assert response.status_code == 200
        assert response.json() == {
            "width": 2000,
            "height": 1000,
            "scene": {"content": {"type": "calibration"}, "layout": "active"},
            "revision": 1,
            "generation": generation,
            "placements": {},
        }
        assert wall_state(client) == response.json()

        # A second accepted scene change keeps climbing within the generation.
        client.put("/scene", json={"content": {"type": "color"}})
        state = wall_state(client)
        assert state["scene"] == {"content": {"type": "color"}, "layout": "active"}
        assert state["revision"] == 2
        assert state["generation"] == generation

    def test_put_scene_leaves_the_layout_alone(self, client, device_payload):
        register(client, device_payload, DEVICE_ID)
        client.put("/wall", json={"width": 3000, "height": 1500})
        client.put(
            f"/devices/{DEVICE_ID}/placement",
            json={"x": 0, "y": 0, "w": 1000, "h": 1000},
        )
        before = wall_state(client)

        assert client.put(
            "/scene", json={"content": {"type": "calibration"}}
        ).status_code == 200

        after = wall_state(client)
        assert after["width"] == before["width"] == 3000
        assert after["height"] == before["height"] == 1500
        assert after["placements"] == before["placements"]
        assert after["revision"] == before["revision"] + 1

    @pytest.mark.parametrize(
        "body",
        [
            # Unknown content types.
            {"content": {"type": "rainbow"}},
            {"content": {"type": ""}},
            # ``image`` is implemented, but these two still lack what an
            # image scene requires: an asset is mandatory (422 when absent),
            # and it must be a ``sha256:<64 hex>`` content ID, not a
            # filename. Rejection with a real, known asset is covered by
            # ``tests/test_assets.py``.
            {"content": {"type": "image"}},
            {"content": {"type": "image", "asset": "poster-1"}},
            # Malformed bodies.
            {"content": {}},
            {"content": {"type": 5}},
            {"content": "calibration"},
            {},
            {"content": {"type": "calibration"}, "layout": "saved-wall"},
            # Unknown keys *inside* the content object are 422 as well
            # (PROTOCOL.md "Unknown keys"): ``mode`` was removed from the
            # contract, so a client still sending it must be told no.
            {"content": {"type": "color", "mode": "rainbow"}},
            # ``asset`` is known only on the image variant, so it is an
            # unexpected field on a calibration scene.
            {"content": {"type": "calibration", "asset": "poster-1"}},
        ],
    )
    def test_put_scene_rejects_bad_bodies_with_422(self, client, body):
        before = wall_state(client)

        response = client.put("/scene", json=body)

        assert response.status_code == 422
        assert wall_state(client) == before, "a rejected update must not mutate"


class TestPlacement:
    def test_placement_defaults_bezel_to_zero(self, client, device_payload):
        register(client, device_payload, DEVICE_ID)

        response = client.put(
            f"/devices/{DEVICE_ID}/placement",
            json={"x": 0, "y": 0, "w": 1000, "h": 1000},
        )

        assert response.status_code == 200
        state = response.json()
        assert state["placements"] == {
            DEVICE_ID: {
                "device_id": DEVICE_ID,
                "x": 0,
                "y": 0,
                "w": 1000,
                "h": 1000,
                "bezel": dict(ZERO_BEZEL),
            }
        }
        assert state["revision"] == 1
        assert wall_state(client) == state

    def test_placement_records_a_full_bezel(self, client, device_payload):
        register(client, device_payload, DEVICE_ID)

        client.put(
            f"/devices/{DEVICE_ID}/placement",
            json={
                "x": 10,
                "y": 20,
                "w": 400,
                "h": 300,
                "bezel": {"top": 5, "right": 6, "bottom": 7, "left": 8},
            },
        )

        placement = wall_state(client)["placements"][DEVICE_ID]
        assert placement == {
            "device_id": DEVICE_ID,
            "x": 10,
            "y": 20,
            "w": 400,
            "h": 300,
            "bezel": {"top": 5, "right": 6, "bottom": 7, "left": 8},
        }

    def test_partial_bezel_defaults_the_other_edges_to_zero(
        self, client, device_payload
    ):
        register(client, device_payload, DEVICE_ID)

        client.put(
            f"/devices/{DEVICE_ID}/placement",
            json={"x": 0, "y": 0, "w": 100, "h": 100, "bezel": {"left": 40}},
        )

        placement = wall_state(client)["placements"][DEVICE_ID]
        assert placement["bezel"] == {"top": 0, "right": 0, "bottom": 0, "left": 40}

    @pytest.mark.parametrize(
        "body",
        [
            # Degenerate rects.
            {"x": 0, "y": 0, "w": 0, "h": 100},
            {"x": 0, "y": 0, "w": 100, "h": 0},
            {"x": 0, "y": 0, "w": -5, "h": 100},
            {"x": 0, "y": 0, "w": 100, "h": -5},
            # Bezel leaves no visible area.
            {"x": 0, "y": 0, "w": 100, "h": 100, "bezel": {"left": 60, "right": 60}},
            {"x": 0, "y": 0, "w": 100, "h": 100, "bezel": {"top": 50, "bottom": 50}},
            # Type errors are 422 too (the body is invalid, not the id).
            {"x": 0, "y": 0, "w": 100, "h": 100, "bezel": {"left": "wide"}},
            {"x": 0, "y": 0, "w": "wide", "h": 100},
        ],
    )
    def test_bad_placement_is_422(self, client, device_payload, body):
        register(client, device_payload, DEVICE_ID)

        response = client.put(f"/devices/{DEVICE_ID}/placement", json=body)

        assert response.status_code == 422
        assert wall_state(client)["placements"] == {}

    def test_placement_for_unknown_device_is_404(self, client):
        response = client.put(
            f"/devices/{uuid.uuid4()}/placement",
            json={"x": 0, "y": 0, "w": 100, "h": 100},
        )

        assert response.status_code == 404

    def test_placement_for_malformed_id_is_404(self, client):
        response = client.put(
            "/devices/not-a-uuid/placement",
            json={"x": 0, "y": 0, "w": 100, "h": 100},
        )

        assert response.status_code == 404

    def test_delete_without_a_placement_is_200(self, client, device_payload):
        register(client, device_payload, DEVICE_ID)

        response = client.delete(f"/devices/{DEVICE_ID}/placement")

        assert response.status_code == 200
        assert response.json()["placements"] == {}

    def test_delete_clears_the_placement(self, client, device_payload):
        register(client, device_payload, DEVICE_ID)
        client.put(
            f"/devices/{DEVICE_ID}/placement",
            json={"x": 0, "y": 0, "w": 100, "h": 100},
        )

        response = client.delete(f"/devices/{DEVICE_ID}/placement")

        assert response.status_code == 200
        assert response.json()["placements"] == {}
        assert wall_state(client)["placements"] == {}

    def test_delete_of_an_absent_device_with_a_placement_is_200(
        self, client, device_payload
    ):
        """A reservation can outlive the roster (PROTOCOL.md).

        Placements are persisted and the roster is not, so the device behind a
        placement may be unknown. Releasing it is an explicit operator action
        and must succeed on the strength of the placement alone.
        """
        register(client, device_payload, DEVICE_ID)
        client.put(
            f"/devices/{DEVICE_ID}/placement",
            json={"x": 0, "y": 0, "w": 100, "h": 100},
        )
        before = wall_state(client)
        # The roster is memory-only: exactly what a restart leaves behind.
        main.devices.clear()

        response = client.delete(f"/devices/{DEVICE_ID}/placement")

        assert response.status_code == 200
        state = response.json()
        assert state["placements"] == {}
        assert state["revision"] == before["revision"] + 1, (
            "releasing a vacant slot is a real commit, not a silent no-op"
        )
        assert wall_state(client) == state

    def test_a_reservation_survives_a_restart_and_can_be_released(
        self, device_payload
    ):
        """A legacy snapshot can retain a placement without device metadata."""
        with TestClient(main.app) as first:
            register(first, device_payload, DEVICE_ID)
            assert first.put(
                f"/devices/{DEVICE_ID}/placement",
                json={"x": 0, "y": 0, "w": 1000, "h": 1000},
            ).status_code == 200

        # Databases from before durable roster metadata keep reservations.
        persist.save_devices({})
        main.devices.clear()
        main.device_sockets.clear()

        with TestClient(main.app) as second:
            # A missing legacy roster must not hide a persisted reservation.
            assert DEVICE_ID not in second.get("/devices").json()
            assert DEVICE_ID in second.get("/wall").json()["placements"]

            response = second.delete(f"/devices/{DEVICE_ID}/placement")

            assert response.status_code == 200
            assert response.json()["placements"] == {}

        with TestClient(main.app) as third:
            # The release was committed, not merely applied to memory.
            assert third.get("/wall").json()["placements"] == {}

    @pytest.mark.parametrize(
        "device_id", [lambda: str(uuid.uuid4()), lambda: "not-a-uuid"]
    )
    def test_delete_placement_of_unknown_or_malformed_id_is_404(
        self, client, device_id
    ):
        assert client.delete(f"/devices/{device_id()}/placement").status_code == 404


class TestWallAuto:
    def test_a_zero_width_cell_is_rejected_before_reservation_checks(
        self, client, device_payload
    ):
        register(client, device_payload, DEVICE_ID)   # offline reservation
        client.put(
            f"/devices/{DEVICE_ID}/placement",
            json={"x": 0, "y": 0, "w": 50, "h": 50},
        )
        register(client, device_payload, SECOND_ID)   # online below
        before = wall_state(client)
        persisted_before = persist.load_state()

        with client.websocket_connect(device_url(SECOND_ID)):
            response = client.post("/wall/auto", json={"columns": 5000})

        assert response.status_code == 422
        assert "too fine" in response.json()["detail"]
        assert wall_state(client) == before
        assert persist.load_state() == persisted_before

    def test_a_zero_height_cell_is_rejected(self, client, device_payload):
        assert client.put("/wall", json={"height": 1}).status_code == 200
        register(client, device_payload, DEVICE_ID)
        register(client, device_payload, SECOND_ID)
        before = wall_state(client)

        with (
            client.websocket_connect(device_url(DEVICE_ID)),
            client.websocket_connect(device_url(SECOND_ID)),
        ):
            response = client.post("/wall/auto", json={"columns": 1})

        assert response.status_code == 422
        assert wall_state(client) == before

    def test_default_columns_grid_for_three_online_devices(
        self, client, device_payload
    ):
        """n=3 online ⇒ columns = round(sqrt(3)) = 2, rows = 2."""
        for device_id in (DEVICE_ID, SECOND_ID, THIRD_ID):
            register(client, device_payload, device_id)

        with (
            client.websocket_connect(device_url(DEVICE_ID)),
            client.websocket_connect(device_url(SECOND_ID)),
            client.websocket_connect(device_url(THIRD_ID)),
        ):
            response = client.post("/wall/auto")

        assert response.status_code == 200
        state = response.json()
        assert state["placements"] == {
            DEVICE_ID: {
                "device_id": DEVICE_ID,
                "x": 0,
                "y": 0,
                "w": 1000,
                "h": 500,
                "bezel": dict(ZERO_BEZEL),
            },
            SECOND_ID: {
                "device_id": SECOND_ID,
                "x": 1000,
                "y": 0,
                "w": 1000,
                "h": 500,
                "bezel": dict(ZERO_BEZEL),
            },
            THIRD_ID: {
                "device_id": THIRD_ID,
                "x": 0,
                "y": 500,
                "w": 1000,
                "h": 500,
                "bezel": dict(ZERO_BEZEL),
            },
        }
        assert state["revision"] == 1
        assert wall_state(client) == state

    def test_explicit_columns_tile_the_wall_exactly(
        self, client, device_payload
    ):
        """2000 units / 3 columns rounds to 667 + 666 + 667 — no gap, no overlap."""
        for device_id in (DEVICE_ID, SECOND_ID, THIRD_ID):
            register(client, device_payload, device_id)

        with (
            client.websocket_connect(device_url(DEVICE_ID)),
            client.websocket_connect(device_url(SECOND_ID)),
            client.websocket_connect(device_url(THIRD_ID)),
        ):
            response = client.post("/wall/auto", json={"columns": 3})

        assert response.status_code == 200
        placements = response.json()["placements"]
        assert placements[DEVICE_ID]["x"] == 0
        assert placements[DEVICE_ID]["w"] == 667
        assert placements[SECOND_ID]["x"] == 667
        assert placements[SECOND_ID]["w"] == 666
        assert placements[THIRD_ID]["x"] == 1333
        assert placements[THIRD_ID]["w"] == 667
        # rows = ceil(3/3) = 1, so every cell is full height.
        for placement in placements.values():
            assert placement["y"] == 0
            assert placement["h"] == 1000

    def test_auto_replaces_online_and_leaves_offline_untouched(
        self, client, device_payload
    ):
        register(client, device_payload, DEVICE_ID)   # online below
        register(client, device_payload, SECOND_ID)   # offline, manual placement
        register(client, device_payload, THIRD_ID)    # offline, never placed

        # Parked in the half of the wall the two-column grid leaves free, so it
        # reads as a *preserved* reservation rather than the conflict asserted
        # by the 409 tests below: the online device's cell stops at x=1000.
        manual = {"x": 1500, "y": 6, "w": 7, "h": 8}
        client.put(f"/devices/{SECOND_ID}/placement", json=manual)
        # An existing (wrong) placement for the online device must be replaced.
        client.put(
            f"/devices/{DEVICE_ID}/placement",
            json={"x": 99, "y": 99, "w": 42, "h": 42},
        )

        with client.websocket_connect(device_url(DEVICE_ID)):
            response = client.post("/wall/auto", json={"columns": 2})

        assert response.status_code == 200
        placements = response.json()["placements"]
        # n=1 online, columns=2 ⇒ rows = 1, so the online device takes the
        # left cell — over the top of what it had — and the right half of the
        # wall stays free.
        assert placements[DEVICE_ID]["x"] == 0
        assert placements[DEVICE_ID]["y"] == 0
        assert placements[DEVICE_ID]["w"] == 1000
        assert placements[DEVICE_ID]["h"] == 1000
        # The offline device keeps exactly what it had; the unplaced one stays
        # unplaced.
        assert placements[SECOND_ID] == {
            "device_id": SECOND_ID,
            **manual,
            "bezel": dict(ZERO_BEZEL),
        }
        assert THIRD_ID not in placements

    def test_auto_rejects_a_grid_that_would_cover_a_vacant_reservation(
        self, client, device_payload
    ):
        """Auto-arranging must not silently destroy — or overlay — a slot a
        tablet is expected to return to (PROTOCOL.md ``POST /wall/auto``)."""
        register(client, device_payload, DEVICE_ID)
        reserved = {"x": 7, "y": 8, "w": 900, "h": 400}
        client.put(f"/devices/{DEVICE_ID}/placement", json=reserved)
        before = wall_state(client)
        # The roster is memory-only: the tablet never came back after a
        # restart, so its placement is a reservation with no known device.
        main.devices.clear()
        register(client, device_payload, SECOND_ID)

        with client.websocket_connect(device_url(SECOND_ID)):
            response = client.post("/wall/auto", json={"columns": 1})

        assert response.status_code == 409
        # The operator is told which slot is in the way …
        assert DEVICE_ID in response.json()["detail"]
        # … and nothing was released, moved, or published on their behalf.
        assert wall_state(client) == before
        assert wall_state(client)["placements"][DEVICE_ID] == {
            "device_id": DEVICE_ID,
            **reserved,
            "bezel": dict(ZERO_BEZEL),
        }

    def test_auto_rejects_a_grid_that_would_cover_an_offline_reservation(
        self, client, device_payload
    ):
        """An offline tablet's placement is a reservation too, and every
        conflicting id is named in the detail."""
        register(client, device_payload, DEVICE_ID)   # offline, reserved below
        register(client, device_payload, THIRD_ID)    # offline, reserved below
        register(client, device_payload, SECOND_ID)   # online below
        first = {"x": 0, "y": 0, "w": 400, "h": 300}
        second = {"x": 1500, "y": 700, "w": 400, "h": 200}
        client.put(f"/devices/{DEVICE_ID}/placement", json=first)
        client.put(f"/devices/{THIRD_ID}/placement", json=second)
        before = wall_state(client)

        with client.websocket_connect(device_url(SECOND_ID)):
            response = client.post("/wall/auto")  # n=1 online ⇒ columns = 1

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert DEVICE_ID in detail and THIRD_ID in detail
        # Both reservations are still exactly where they were.
        assert wall_state(client) == before

    def test_auto_accepts_a_grid_that_only_touches_a_reservation(
        self, client, device_payload
    ):
        """Sharing an edge is tiling, not overlapping.

        The proposed cell for the one online device spans x 0..667, so a
        reservation starting at exactly 667 merely abuts it; a second one sits
        well clear. Both are preserved and the arrange succeeds.
        """
        register(client, device_payload, DEVICE_ID)   # offline, abuts the cell
        register(client, device_payload, THIRD_ID)    # offline, clear of it
        register(client, device_payload, SECOND_ID)   # online below
        touching = {"x": 667, "y": 0, "w": 200, "h": 1000}
        clear = {"x": 1400, "y": 100, "w": 100, "h": 100}
        client.put(f"/devices/{DEVICE_ID}/placement", json=touching)
        client.put(f"/devices/{THIRD_ID}/placement", json=clear)

        with client.websocket_connect(device_url(SECOND_ID)):
            response = client.post("/wall/auto", json={"columns": 3})

        assert response.status_code == 200
        placements = response.json()["placements"]
        assert placements[SECOND_ID] == {
            "device_id": SECOND_ID,
            "x": 0,
            "y": 0,
            "w": 667,
            "h": 1000,
            "bezel": dict(ZERO_BEZEL),
        }
        assert placements[DEVICE_ID] == {
            "device_id": DEVICE_ID,
            **touching,
            "bezel": dict(ZERO_BEZEL),
        }
        assert placements[THIRD_ID] == {
            "device_id": THIRD_ID,
            **clear,
            "bezel": dict(ZERO_BEZEL),
        }

    def test_auto_judges_overlap_by_footprint_not_by_visible_area(
        self, client, device_payload
    ):
        """Bezel only shrinks what is shown *inside* a rect, so it cannot make
        a reservation stop conflicting: the grid covers footprints."""
        register(client, device_payload, DEVICE_ID)   # offline, reserved below
        register(client, device_payload, SECOND_ID)   # online below
        # Visible from x=750 (left bezel 150), which is clear of the cell that
        # ends at x=667 — but the rect itself, x 600..800, still intrudes.
        reservation = {
            "x": 600,
            "y": 0,
            "w": 200,
            "h": 100,
            "bezel": {"top": 0, "right": 0, "bottom": 0, "left": 150},
        }
        client.put(f"/devices/{DEVICE_ID}/placement", json=reservation)
        before = wall_state(client)

        with client.websocket_connect(device_url(SECOND_ID)):
            response = client.post("/wall/auto", json={"columns": 3})

        assert response.status_code == 409
        assert DEVICE_ID in response.json()["detail"]
        assert wall_state(client) == before

    def test_an_existing_online_placement_is_not_a_reservation(
        self, client, device_payload
    ):
        """What the grid replaces can never block it — only offline and
        roster-absent placements are reservations."""
        register(client, device_payload, DEVICE_ID)
        # Deliberately straddling where the new cell is about to land.
        client.put(
            f"/devices/{DEVICE_ID}/placement",
            json={"x": 10, "y": 20, "w": 900, "h": 700},
        )

        with client.websocket_connect(device_url(DEVICE_ID)):
            response = client.post("/wall/auto", json={"columns": 3})

        assert response.status_code == 200
        assert response.json()["placements"][DEVICE_ID] == {
            "device_id": DEVICE_ID,
            "x": 0,
            "y": 0,
            "w": 667,
            "h": 1000,
            "bezel": dict(ZERO_BEZEL),
        }

    def test_a_rejected_auto_changes_nothing_anywhere(
        self, client, device_payload
    ):
        """The 409 arrives before the commit boundary: all three stay put."""
        register(client, device_payload, DEVICE_ID)   # offline reservation
        client.put(
            f"/devices/{DEVICE_ID}/placement",
            json={"x": 0, "y": 0, "w": 800, "h": 600},
        )
        register(client, device_payload, SECOND_ID)   # online below
        before = wall_state(client)
        persisted_before = persist.load_state()

        # The device socket opens before the controller does, so its
        # ``device_online`` is not queued for the controller either: every
        # frame the controller sees below was raised on purpose.
        with (
            client.websocket_connect(device_url(SECOND_ID)),
            client.websocket_connect(controller_url(protocol=2)) as controller,
        ):
            controller.receive_json()  # snapshot
            response = client.post("/wall/auto", json={"columns": 1})

            assert response.status_code == 409
            # Memory did not move …
            assert wall_state(client) == before
            # … and neither did the database row.
            assert persist.load_state() == persisted_before
            # A rejected request queues no wall frame, so the next one out is
            # the roster event fired after it.
            register(client, device_payload, THIRD_ID)
            event = controller.receive_json()

        assert event["type"] == "device_updated"
        assert event["device"]["device_id"] == THIRD_ID

    def test_auto_with_an_empty_roster(self, client):
        response = client.post("/wall/auto")

        assert response.status_code == 200
        assert response.json()["placements"] == {}

    @pytest.mark.parametrize("body", [{"columns": 0}, {"columns": -1}, {"columns": "two"}])
    def test_auto_rejects_bad_columns_with_422(self, client, body):
        assert client.post("/wall/auto", json=body).status_code == 422


class TestRevisionMonotonic:
    def test_every_mutation_strictly_bumps_the_revision(
        self, client, device_payload
    ):
        register(client, device_payload, DEVICE_ID)

        revisions = [wall_state(client)["revision"]]
        assert revisions == [0], "a fresh server starts at revision 0"

        client.put("/wall", json={"width": 1500})
        revisions.append(wall_state(client)["revision"])

        client.put("/scene", json={"content": {"type": "calibration"}})
        revisions.append(wall_state(client)["revision"])

        client.put(
            f"/devices/{DEVICE_ID}/placement",
            json={"x": 0, "y": 0, "w": 1000, "h": 1000},
        )
        revisions.append(wall_state(client)["revision"])

        with client.websocket_connect(device_url(DEVICE_ID)):
            client.post("/wall/auto", json={"columns": 1})
            revisions.append(wall_state(client)["revision"])

            client.delete(f"/devices/{DEVICE_ID}/placement")
            revisions.append(wall_state(client)["revision"])

        # Stale-revision rejection is the client's job, so all the server has
        # to guarantee is that a newer wall always carries a larger revision.
        assert revisions == sorted(revisions)
        assert all(new > old for old, new in zip(revisions, revisions[1:]))


class TestDeletingADevice:
    def test_delete_drops_its_placement(self, client, device_payload):
        """A deleted device must not keep reserving a hole on the wall."""
        register(client, device_payload, DEVICE_ID)
        client.put(
            f"/devices/{DEVICE_ID}/placement",
            json={"x": 0, "y": 0, "w": 1000, "h": 1000},
        )
        before = wall_state(client)
        assert DEVICE_ID in before["placements"]

        assert client.delete(f"/devices/{DEVICE_ID}", headers={"If-Match": config_etag(client)}).status_code == 200

        after = wall_state(client)
        assert DEVICE_ID not in after["placements"]
        assert after["revision"] > before["revision"]

    def test_delete_without_a_placement_leaves_the_revision_alone(
        self, client, device_payload
    ):
        """The wall did not change, so there is no new revision to publish."""
        register(client, device_payload, DEVICE_ID)
        before = wall_state(client)

        assert client.delete(f"/devices/{DEVICE_ID}", headers={"If-Match": config_etag(client)}).status_code == 200

        assert wall_state(client)["revision"] == before["revision"]
