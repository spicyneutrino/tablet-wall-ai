"""Delivery failures must remove only the connection that actually failed."""

import asyncio
from collections.abc import Callable

import pytest

from tabletwall import hub
from tabletwall.protocol import WS_CLOSE_HEARTBEAT_TIMEOUT, WS_CLOSE_NORMAL

DEVICE = "0f8fad5b-d9cb-469f-a165-70867728950e"
LAST_SEEN = "2026-10-28T12:00:00+00:00"


class Socket:
    def __init__(self, *, fail_send=False, fail_close=False, on_send=None, on_close=None):
        self.fail_send = fail_send
        self.fail_close = fail_close
        self.on_send: Callable | None = on_send
        self.on_close: Callable | None = on_close
        self.frames = []
        self.closed = []

    async def send_json(self, frame):
        if self.on_send:
            self.on_send()
        if self.fail_send:
            raise ConnectionError("socket disconnected during send")
        self.frames.append(frame)

    async def close(self, *, code):
        self.closed.append(code)
        if self.on_close:
            self.on_close()
        if self.fail_close:
            raise ConnectionError("socket is already closed")


def test_controller_failure_does_not_interrupt_other_recipients():
    failed = Socket(fail_send=True, fail_close=True)
    healthy = Socket()
    hub.controller_sockets.update((failed, healthy))
    frame = {"type": "device_offline", "device_id": DEVICE, "last_seen": LAST_SEEN}

    asyncio.run(hub._broadcast(frame))

    assert healthy.frames == [frame]
    assert hub.controller_sockets == {healthy}
    assert failed.closed == [WS_CLOSE_NORMAL]


@pytest.mark.parametrize(("protocol", "frame_type"), [(2, "wall_updated"), (3, "config_updated")])
def test_wall_controller_failure_cleans_protocol_and_continues(protocol, frame_type):
    failed = Socket(fail_send=True, fail_close=True)
    healthy = Socket()
    hub.controller_sockets.update((failed, healthy))
    hub.controller_protocols.update({failed: protocol, healthy: protocol})

    asyncio.run(hub._broadcast_wall())

    assert [frame["type"] for frame in healthy.frames] == [frame_type]
    assert hub.controller_sockets == {healthy}
    assert hub.controller_protocols == {healthy: protocol}
    assert failed.closed == [WS_CLOSE_NORMAL]


def test_device_send_failure_reports_offline_but_keeps_registration():
    failed = Socket(fail_send=True, fail_close=True)
    controller = Socket()
    record = {"protocol": 2, "last_seen": LAST_SEEN}
    hub.devices[DEVICE] = record
    hub.device_sockets[DEVICE] = failed
    hub.controller_sockets.add(controller)

    asyncio.run(hub._send_wall_to_device(DEVICE, failed, record))

    assert DEVICE not in hub.device_sockets
    assert hub.devices[DEVICE] is record
    assert failed.closed == [WS_CLOSE_NORMAL]
    assert controller.frames == [{
        "type": "device_offline", "device_id": DEVICE, "last_seen": LAST_SEEN,
    }]


def test_old_send_failure_cannot_disconnect_a_replacement():
    replacement = Socket()
    failed = Socket(
        fail_send=True,
        on_send=lambda: hub.device_sockets.update({DEVICE: replacement}),
    )
    controller = Socket()
    record = {"protocol": 2, "last_seen": LAST_SEEN}
    hub.devices[DEVICE] = record
    hub.device_sockets[DEVICE] = failed
    hub.controller_sockets.add(controller)

    asyncio.run(hub._send_wall_to_device(DEVICE, failed, record))

    assert hub.device_sockets[DEVICE] is replacement
    assert replacement.closed == []
    assert failed.closed == []
    assert controller.frames == []


def test_color_delivery_reports_missing_failed_and_live_connections():
    async def exercise():
        assert await hub._send_color_to_device(DEVICE, "#123456") is False
        failed = Socket(fail_send=True)
        hub.device_sockets[DEVICE] = failed
        assert await hub._send_color_to_device(DEVICE, "#123456") is False
        healthy = Socket()
        hub.device_sockets[DEVICE] = healthy
        assert await hub._send_color_to_device(DEVICE, "#123456") is True
        assert healthy.frames == [{"type": "set_color", "color": "#123456"}]

    asyncio.run(exercise())


def test_heartbeat_close_failure_still_reports_offline(monkeypatch):
    failed = Socket(fail_close=True)
    controller = Socket()
    hub.devices[DEVICE] = {"last_seen": LAST_SEEN}
    hub.device_sockets[DEVICE] = failed
    hub.controller_sockets.add(controller)
    monkeypatch.setattr(hub, "_seconds_since_last_seen", lambda device: None)

    asyncio.run(hub._sweep_once())

    assert DEVICE not in hub.device_sockets
    assert failed.closed == [WS_CLOSE_HEARTBEAT_TIMEOUT]
    assert controller.frames == [{
        "type": "device_offline", "device_id": DEVICE, "last_seen": LAST_SEEN,
    }]


def test_reconnect_during_heartbeat_close_stays_online(monkeypatch):
    replacement = Socket()
    stale = Socket(on_close=lambda: hub.device_sockets.update({DEVICE: replacement}))
    controller = Socket()
    hub.devices[DEVICE] = {"last_seen": LAST_SEEN}
    hub.device_sockets[DEVICE] = stale
    hub.controller_sockets.add(controller)
    monkeypatch.setattr(hub, "_seconds_since_last_seen", lambda device: hub.HEARTBEAT_TIMEOUT_S + 1)

    asyncio.run(hub._sweep_once())

    assert hub.device_sockets[DEVICE] is replacement
    assert stale.closed == [WS_CLOSE_HEARTBEAT_TIMEOUT]
    assert replacement.closed == []
    assert controller.frames == []


def test_heartbeat_refresh_during_another_close_prevents_expiry(monkeypatch):
    ages = {"first": hub.HEARTBEAT_TIMEOUT_S + 1, "second": hub.HEARTBEAT_TIMEOUT_S + 1}
    first = Socket(on_close=lambda: ages.update(second=0))
    second = Socket()
    controller = Socket()
    hub.devices.update({"first": {"last_seen": LAST_SEEN}, "second": {"last_seen": LAST_SEEN}})
    hub.device_sockets.update(first=first, second=second)
    hub.controller_sockets.add(controller)
    monkeypatch.setattr(hub, "_seconds_since_last_seen", ages.get)

    asyncio.run(hub._sweep_once())

    assert hub.device_sockets == {"second": second}
    assert second.closed == []
    assert [frame["device_id"] for frame in controller.frames] == ["first"]
