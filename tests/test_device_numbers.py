"""Display numbers: lowest free, stable, and leased for 15 minutes.

The number is a small physical-identification label, not the device identity.
These tests use the in-memory roster directly and move last_seen_mono rather
than sleeping.
"""

import time
import uuid

import main
from tabletwall.state import DEVICE_NUMBER_LEASE_S


def _payload(device_id: str, number: int | None = None) -> dict[str, object]:
    body = {
        "device_id": device_id,
        "width": 768,
        "height": 393,
        "device_type": "ipad",
    }
    if number is not None:
        body["number"] = number
    return body


def _register(client, device_id: str, number: int | None = None) -> dict[str, object]:
    response = client.post("/devices/register", json=_payload(device_id, number))
    assert response.status_code == 200, response.text
    return client.get("/devices").json()[device_id]


def _three_ids() -> tuple[str, str, str]:
    return str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())


def test_number_is_lowest_free_and_survives_reregistration(client):
    first, second, third = _three_ids()
    assert _register(client, first)["number"] == 1
    assert _register(client, second)["number"] == 2
    assert _register(client, first)["number"] == 1
    assert _register(client, third)["number"] == 3

    numbers = {record["number"] for record in main.devices.values()}
    assert numbers == {1, 2, 3}


def test_number_is_in_welcome_and_device_record(client):
    first, _, _ = _three_ids()
    record = _register(client, first)
    assert record["number"] == 1

    with client.websocket_connect(
        f"/ws/device?device_id={first}&protocol=3"
    ) as socket:
        welcome = socket.receive_json()

    assert welcome["type"] == "welcome"
    assert welcome["number"] == 1


def test_v1_welcome_does_not_gain_the_number_field(client):
    first, _, _ = _three_ids()
    _register(client, first)

    with client.websocket_connect(
        f"/ws/device?device_id={first}&protocol=1"
    ) as socket:
        welcome = socket.receive_json()

    assert welcome["type"] == "welcome"
    assert "number" not in welcome


def test_number_is_released_after_fifteen_minutes(client):
    first, second, third = _three_ids()
    _register(client, first)
    _register(client, second)
    main.devices[first]["last_seen_mono"] = (
        time.monotonic() - DEVICE_NUMBER_LEASE_S - 1
    )

    assert _register(client, third)["number"] == 1
    assert "number" not in main.devices[first]
    assert main.devices[second]["number"] == 2
    assert main.devices[third]["number"] == 1


def test_number_is_kept_while_the_lease_has_not_expired(client):
    first, second, third = _three_ids()
    _register(client, first)
    _register(client, second)
    main.devices[first]["last_seen_mono"] = (
        time.monotonic() - DEVICE_NUMBER_LEASE_S + 1
    )

    assert _register(client, third)["number"] == 3
    assert main.devices[first]["number"] == 1


def test_an_open_socket_keeps_the_number(client):
    first, second, third = _three_ids()
    _register(client, first)
    _register(client, second)

    with client.websocket_connect(
        f"/ws/device?device_id={first}&protocol=3"
    ) as socket:
        socket.receive_json()  # welcome
        main.devices[first]["last_seen_mono"] = (
            time.monotonic() - DEVICE_NUMBER_LEASE_S - 1
        )
        assert _register(client, third)["number"] == 3

    assert main.devices[first]["number"] == 1


def _etag(client) -> str:
    return client.get("/api/v3/config").json()["etag"]


def test_delete_frees_the_number_for_reuse(client):
    first, second, third = _three_ids()
    _register(client, first)
    _register(client, second)

    response = client.delete(
        f"/devices/{first}", headers={"If-Match": _etag(client)})
    assert response.status_code == 200, response.text
    assert _register(client, third)["number"] == 1


def test_released_number_is_broadcast_to_the_controller(client):
    first, second, third = _three_ids()
    _register(client, first)
    _register(client, second)
    main.devices[first]["last_seen_mono"] = (
        time.monotonic() - DEVICE_NUMBER_LEASE_S - 1
    )

    with client.websocket_connect("/ws/controller?protocol=2") as controller:
        controller.receive_json()  # snapshot
        _register(client, third)
        frames = [controller.receive_json() for _ in range(2)]

    updated = {
        frame["device"]["device_id"]: frame["device"].get("number")
        for frame in frames
        if frame["type"] == "device_updated"
    }
    assert updated[first] is None
    assert updated[third] == 1


def test_reconnect_after_release_receives_a_new_number(client):
    first, second, third = _three_ids()
    _register(client, first)
    _register(client, second)
    main.devices[first]["last_seen_mono"] = (
        time.monotonic() - DEVICE_NUMBER_LEASE_S - 1
    )
    _register(client, third)  # takes number 1 from first

    with client.websocket_connect(
        f"/ws/device?device_id={first}&protocol=3"
    ) as socket:
        welcome = socket.receive_json()

    assert welcome["number"] == 3
    assert main.devices[first]["number"] == 3


def test_returning_tablet_can_reclaim_its_number_after_restart(client):
    first, second, third = _three_ids()
    _register(client, first)
    _register(client, second)
    # A restart drops the in-memory roster. The browser remembers its number
    # in localStorage and asks for it on the next registration.
    main.devices.clear()
    main.device_sockets.clear()
    assert _register(client, second, number=2)["number"] == 2
    assert _register(client, first, number=1)["number"] == 1
    assert _register(client, third, number=3)["number"] == 3


def test_requested_number_that_is_taken_falls_back_to_the_lowest_free(client):
    first, second, third = _three_ids()
    _register(client, first)   # 1
    _register(client, second)  # 2
    _register(client, third)   # 3
    main.devices.pop(second)

    # 2 is free, but 1 is still held by first. A stale or malicious claim for
    # 1 must not overwrite it; the replacement gets the lowest free number.
    assert _register(client, second, number=1)["number"] == 2
    assert main.devices[first]["number"] == 1
