"""Delivery of frames to sockets plus the heartbeat sweeper.

Depends on ``tabletwall.protocol`` (constants) and ``tabletwall.state`` (the
socket registries); nothing depends on this module except ``main``.
"""

import asyncio
import contextlib
from typing import Any

import anyio
from fastapi import WebSocket

from tabletwall import operator_state, render_status, tablet_models
from tabletwall import writer as writers
from tabletwall.protocol import (
    HEARTBEAT_TIMEOUT_S,
    SWEEP_INTERVAL_S,
    WS_CLOSE_HEARTBEAT_TIMEOUT,
    WS_CLOSE_NORMAL,
    _now_iso,
)
from tabletwall.state import (
    _render_frame,
    _device_record,
    measurement_for,
    identify_commands,
    _seconds_since_last_seen,
    _wall_frame,
    _wall_state,
    controller_protocols,
    controller_sockets,
    device_sockets,
    devices,
    wall,
)


async def _send(websocket: WebSocket, frame: dict[str, Any]) -> None:
    writer = writers.get(websocket)
    if writer is not None:
        await writer.send(frame)
    else:
        await websocket.send_json(frame)


async def _broadcast(frame: dict[str, Any]) -> None:
    """Send one frame to every controller.

    Iterates a copy of the socket collection and wraps each send so that one
    dead socket does not abort the remaining sends.
    """
    for websocket in list(controller_sockets):
        try:
            await _send(websocket, frame)
        except Exception:
            # Drop *and* close. Discarding alone would leave a controller
            # holding an open socket that is never sent to again: it would go
            # silently stale, with no close event to trigger its reconnect.
            controller_sockets.discard(websocket)
            with contextlib.suppress(Exception):
                await websocket.close(code=WS_CLOSE_NORMAL)


async def _send_color_to_device(device_id: str, color: str) -> bool:
    """Push a ``set_color`` frame to a device; True when it was handed over."""
    websocket = device_sockets.get(device_id)
    if websocket is None:
        return False
    try:
        await _send(websocket, {"type": "set_color", "color": color})
    except Exception:
        return False
    return True


async def _broadcast_offline(device_id: str, last_seen: str) -> None:
    """Tell controllers a device went away.

    The device task may be unwinding from a cancellation (the test client
    cancels a socket task when its session closes), so the send is shielded:
    controllers must still learn about the disconnect.
    """
    frame = {"type": "device_offline", "device_id": device_id, "last_seen": last_seen}
    with anyio.CancelScope(shield=True):
        await _broadcast(frame)


def _measurement_for(device_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    return measurement_for(device_id)


async def _send_wall_to_device(
    device_id: str, websocket: WebSocket, record: dict[str, Any]
) -> None:
    """Send the current wall or v3 render frame to one device socket."""
    if device_sockets.get(device_id) is not websocket:
        return
    try:
        if record.get("protocol") == 3:
            profile, calibration = _measurement_for(device_id)
            calibration = tablet_models.effective(device_id, calibration, record.get("viewport") or {})
            frame = _render_frame(device_id, record, profile, calibration)
            if "token" in frame:
                render_status.expect(device_id, render_status.RenderToken(**frame["token"]))
            await _send(websocket, frame)
        else:
            await _send(websocket, _wall_frame(device_id, record))
    except Exception:
        # Drop *and* close (the pattern from ``_broadcast``), then report the
        # device offline: a failed send means the socket is gone, and dropping
        # the slot silently would leave controllers rendering a live-looking
        # tablet forever — the device task's own finally block skips the
        # broadcast once somebody else owns the slot.
        if device_sockets.get(device_id) is websocket:
            render_status.disconnect(device_id, record.get("connection_id", ""))
            identify_commands.pop(device_id, None)
            device_sockets.pop(device_id, None)
            with contextlib.suppress(Exception):
                await websocket.close(code=WS_CLOSE_NORMAL)
            await _broadcast_offline(device_id, record.get("last_seen", _now_iso()))


async def _broadcast_wall() -> None:
    """Push the current wall to every version-2 socket.

    State is fully mutated before this is called (no await mid-mutation).
    Iterates copies of both socket collections; every send is individually
    guarded so one dead socket cannot abort the rest (PROTOCOL.md
    "Concurrency rules"). Version-1 sockets never receive a version-2 frame.
    """
    wall_updated = {"type": "wall_updated", "wall": _wall_state()}
    for websocket in list(controller_sockets):
        protocol = controller_protocols.get(websocket, 1)
        if protocol == 3:
            try:
                await _send(websocket, {
                    "type": "config_updated",
                    "revision": wall["revision"],
                    "generation": wall["generation"],
                })
            except Exception:
                controller_sockets.discard(websocket)
                controller_protocols.pop(websocket, None)
                with contextlib.suppress(Exception):
                    await websocket.close(code=WS_CLOSE_NORMAL)
            continue
        if protocol != 2:
            continue
        try:
            await _send(websocket, wall_updated)
        except Exception:
            controller_sockets.discard(websocket)
            controller_protocols.pop(websocket, None)
            with contextlib.suppress(Exception):
                await websocket.close(code=WS_CLOSE_NORMAL)

    for device_id, websocket in list(device_sockets.items()):
        record = devices.get(device_id)
        if record is None or record.get("protocol") not in (2, 3):
            continue
        await _send_wall_to_device(device_id, websocket, record)


# ---------------------------------------------------------------------------
# heartbeat sweeper
# ---------------------------------------------------------------------------


async def _sweep_once() -> None:
    # Timing constants are read here, inside the loop, so tests can patch them.
    timeout = HEARTBEAT_TIMEOUT_S

    stale: list[tuple[str, WebSocket]] = []
    for device_id, websocket in list(device_sockets.items()):
        age = _seconds_since_last_seen(device_id)
        if age is None or age > timeout:
            stale.append((device_id, websocket))

    for device_id, websocket in stale:
        if device_sockets.get(device_id) is not websocket:
            continue  # replaced by a newer socket in the meantime

        # Re-check immediately before acting: closing the sockets above
        # yielded, so this device may have sent a heartbeat in the meantime.
        age = _seconds_since_last_seen(device_id)
        if age is not None and age <= timeout:
            continue  # it came back while we were working through the list

        render_status.disconnect(device_id, devices.get(device_id, {}).get("connection_id", ""))
        identify_commands.pop(device_id, None)
        device_sockets.pop(device_id, None)
        with contextlib.suppress(Exception):
            await websocket.close(code=WS_CLOSE_HEARTBEAT_TIMEOUT)

        record = devices.get(device_id)
        if record is not None and device_id not in device_sockets:
            # Skips the broadcast only when the device reconnected or was
            # deleted while we were closing the dead socket: somebody else has
            # already reported the change in those cases.
            await _broadcast_offline(device_id, record["last_seen"])


async def _sweep_loop() -> None:
    while True:
        # Sleep first and re-read the interval on every pass: tests patch it.
        await asyncio.sleep(SWEEP_INTERVAL_S)
        await _sweep_once()


async def _broadcast_device_status(device_id: str, *, presentation_active: bool = False) -> None:
    status = operator_state.device_status(device_id, presentation_active=presentation_active)
    device = _device_record(device_id) if device_id in devices else {"device_id": device_id}
    frame = {"type": "device_updated", "device": {**device, **status}}
    for socket in list(controller_sockets):
        if controller_protocols.get(socket) != 3:
            continue
        try:
            await _send(socket, frame)
        except Exception:
            controller_sockets.discard(socket)
            controller_protocols.pop(socket, None)
            with contextlib.suppress(Exception):
                await socket.close(code=WS_CLOSE_NORMAL)


async def _broadcast_config_updated() -> None:
    for socket in list(controller_sockets):
        if controller_protocols.get(socket) != 3:
            continue
        try:
            await _send(socket, {"type": "config_updated", "generation": wall["generation"], "revision": wall["revision"]})
        except Exception:
            controller_sockets.discard(socket)
            controller_protocols.pop(socket, None)
            with contextlib.suppress(Exception):
                await socket.close(code=WS_CLOSE_NORMAL)
