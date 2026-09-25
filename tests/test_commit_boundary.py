"""Commit-boundary tests: a failed save must not diverge memory from disk.

PROTOCOL.md "Persistence": "A commit happens before notification, so a
controller is never told about state that would not survive a restart."

Every wall-mutating route commits through ``main._commit_wall``: the change is
built on a detached copy, *that* copy is persisted, and only a successful write
lets the change into the live ``wall``. These tests break ``save_state`` on
purpose and assert the three consequences the contract needs — the live state
does not move, the database does not move, nothing is broadcast — plus the
fourth: the request fails loudly instead of swallowing the error.

The "nothing was broadcast" assertion uses the same trick as
``test_v1_controller_never_gets_wall_updated``: a roster event fired *after*
the failed request must be the next frame out of the socket, so a wall frame
queued during the failure would show up first.
"""

import pytest
from fastapi.testclient import TestClient

import main
from tabletwall import persist

DEVICE_ID = "0f8fad5b-d9cb-469f-a165-70867728950e"

ZERO_BEZEL = {"top": 0, "right": 0, "bottom": 0, "left": 0}


def controller_url() -> str:
    return "/ws/controller?protocol=2"


def device_url(caps: str | None = "calibration") -> str:
    url = f"/ws/device?device_id={DEVICE_ID}&protocol=2"
    if caps is not None:
        url += f"&caps={caps}"
    return url


def register(client, device_payload, device_id: str = DEVICE_ID) -> None:
    response = client.post(
        "/devices/register", json={**device_payload, "device_id": device_id}
    )
    assert response.status_code == 200


def wall_state(client) -> dict:
    response = client.get("/wall")
    assert response.status_code == 200
    return response.json()


def place(client) -> None:
    response = client.put(
        f"/devices/{DEVICE_ID}/placement",
        json={"x": 1, "y": 2, "w": 300, "h": 200, "bezel": {"top": 5}},
    )
    assert response.status_code == 200


def broken_save(wall_state_to_persist) -> None:
    """A database that refuses the write, loudly."""
    raise RuntimeError("disk full")


def assert_database_did_not_move(before: dict) -> None:
    persisted = persist.load_state()
    assert persisted["revision"] == before["revision"]
    assert persisted["layout"]["width"] == before["width"]
    assert persisted["layout"]["height"] == before["height"]
    assert persisted["layout"]["placements"] == before["placements"]
    assert persisted["scene"] == before["scene"]


# Every wall-mutating route, as (method, path, body).
MUTATIONS = [
    ("PUT", "/wall", {"width": 3000}),
    ("PUT", "/scene", {"content": {"type": "calibration"}}),
    ("PUT", f"/devices/{DEVICE_ID}/placement", {"x": 0, "y": 0, "w": 1000, "h": 1000}),
    ("DELETE", f"/devices/{DEVICE_ID}/placement", None),
    ("POST", "/wall/auto", {"columns": 1}),
]


class TestAFailedSaveChangesNothing:
    @pytest.mark.parametrize(("method", "path", "body"), MUTATIONS)
    def test_memory_disk_and_subscribers_stay_in_agreement(
        self, client, device_payload, monkeypatch, method, path, body
    ):
        """Patch ``save_state`` to raise: nothing may move but the response."""
        register(client, device_payload, DEVICE_ID)
        place(client)
        before = wall_state(client)

        with client.websocket_connect(controller_url()) as controller:
            controller.receive_json()  # snapshot
            monkeypatch.setattr(main, "save_state", broken_save)

            with pytest.raises(RuntimeError, match="disk full"):
                client.request(method, path, json=body)

            # Memory: the live wall is byte-for-byte what it was — the
            # proposed copy was never applied to it.
            assert wall_state(client) == before
            # Disk: the row never advanced either.
            assert_database_did_not_move(before)

            # Broadcast: a wall frame would have been queued *during* the
            # failed request, so the next frame out of the socket must be the
            # roster event raised afterwards.
            register(client, device_payload, DEVICE_ID)
            event = controller.receive_json()
            assert event["type"] == "device_updated"
            assert event["device"]["device_id"] == DEVICE_ID

    def test_a_failed_device_delete_keeps_the_device_and_its_placement(
        self, client, device_payload, monkeypatch
    ):
        """Device deletion commits the placement removal *before* it pops the
        roster and socket entries: a failed save must remove neither half."""
        register(client, device_payload, DEVICE_ID)
        place(client)
        before = wall_state(client)

        with client.websocket_connect(controller_url()) as controller:
            controller.receive_json()  # snapshot
            monkeypatch.setattr(main, "save_state", broken_save)

            with pytest.raises(RuntimeError, match="disk full"):
                client.delete(f"/devices/{DEVICE_ID}")

            # Still on the roster …
            assert DEVICE_ID in client.get("/devices").json()
            # … still on the wall, at the same revision …
            assert wall_state(client) == before
            # … and not a single frame went out.
            register(client, device_payload, DEVICE_ID)
            assert controller.receive_json()["type"] == "device_updated"

        assert persist.load_state()["layout"]["placements"].keys() == {DEVICE_ID}

    def test_a_failed_save_pushes_no_wall_frame_to_the_device(
        self, client, device_payload, monkeypatch
    ):
        """The device side of the same rule: its socket stays quiet until the
        next command, which arrives intact."""
        register(client, device_payload, DEVICE_ID)
        client.put("/scene", json={"content": {"type": "calibration"}})
        before = wall_state(client)

        with client.websocket_connect(device_url()) as device:
            device.receive_json()  # welcome
            device.receive_json()  # wall
            monkeypatch.setattr(main, "save_state", broken_save)

            with pytest.raises(RuntimeError, match="disk full"):
                client.put("/scene", json={"content": {"type": "color"}})

            assert wall_state(client) == before
            # The colour command does not persist, so it still succeeds — and
            # it being the *next* frame proves no wall frame was broadcast.
            assert client.post(
                f"/devices/{DEVICE_ID}/color", json={"color": "#3b82f6"}
            ).status_code == 200
            assert device.receive_json() == {
                "type": "set_color",
                "color": "#3b82f6",
            }

    def test_a_failed_save_is_reported_as_a_server_error(
        self, device_payload, monkeypatch
    ):
        """The failure is not swallowed: the request answers 5xx.

        ``raise_server_exceptions=False`` is what lets the assertion see the
        status code; the default test client re-raises into the test instead.
        """
        with TestClient(main.app, raise_server_exceptions=False) as client:
            register(client, device_payload, DEVICE_ID)
            place(client)
            before = wall_state(client)
            monkeypatch.setattr(main, "save_state", broken_save)

            response = client.put("/wall", json={"width": 3000})

            assert response.status_code == 500
            assert wall_state(client) == before
            assert_database_did_not_move(before)
