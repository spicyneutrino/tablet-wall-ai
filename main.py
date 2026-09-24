"""FastAPI backend for tablet-wall-ai.

Phase 1 adds the realtime layer described in ``PROTOCOL.md``: WebSocket
endpoints for devices and the controller, heartbeat-driven presence, and
colour commands. Everything intentionally lives in this module — a later
phase will split it up.
"""

import asyncio
import contextlib
import json
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import anyio
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, UUID4, field_validator

# Timing constants (PROTOCOL.md "Timing constants"). Tests monkeypatch these,
# so every read must happen at call time rather than being captured at import.
HEARTBEAT_INTERVAL_MS = 5000
HEARTBEAT_TIMEOUT_S = 15
SWEEP_INTERVAL_S = 2

# WebSocket close codes (PROTOCOL.md "WebSocket close codes").
WS_CLOSE_BAD_REQUEST = 4400
WS_CLOSE_UNKNOWN_DEVICE = 4404
WS_CLOSE_HEARTBEAT_TIMEOUT = 4408
WS_CLOSE_REPLACED = 4409
WS_CLOSE_NORMAL = 1000

# Roster: device_id -> device record. Only metadata is stored; ``online`` is
# derived from the presence of a live socket plus ``last_seen``.
devices: dict[str, dict[str, Any]] = {}

# One open socket per device, and every open controller socket.
device_sockets: dict[str, WebSocket] = {}
controller_sockets: set[WebSocket] = set()

_sweeper_task: asyncio.Task[Any] | None = None

_COLOR_PATTERN = re.compile(r"#?[0-9a-fA-F]{6}")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Current UTC time as ISO-8601 with an explicit ``+00:00`` offset."""
    return datetime.now(timezone.utc).isoformat()


def _normalise_color(value: str) -> str:
    """Validate ``^#?[0-9a-fA-F]{6}$`` and normalise to lowercase ``#rrggbb``."""
    if not _COLOR_PATTERN.fullmatch(value):
        raise ValueError("color must be 6 hex digits, optionally prefixed with #")
    return "#" + value.lower().removeprefix("#")


def _parse_device_id(raw: str | None) -> str | None:
    """Return the canonical lowercase UUID4 string, or None if it is not one."""
    if not raw:
        return None
    try:
        parsed = uuid.UUID(raw)
    except (AttributeError, TypeError, ValueError):
        return None
    if parsed.version != 4:
        return None
    return str(parsed)


def _seconds_since_last_seen(device_id: str) -> float | None:
    """Seconds since this device last checked in, or None if it is unknown."""
    record = devices.get(device_id)
    if record is None:
        return None
    return (datetime.now(timezone.utc) - datetime.fromisoformat(record["last_seen"])).total_seconds()


def _is_online(device_id: str) -> bool:
    """True iff the device holds an open socket that has not timed out."""
    if device_id not in device_sockets:
        return False
    age = _seconds_since_last_seen(device_id)
    return age is not None and age <= HEARTBEAT_TIMEOUT_S


def _device_record(device_id: str) -> dict[str, Any]:
    """The wire shape of a device record (PROTOCOL.md "Device record")."""
    return {**devices[device_id], "online": _is_online(device_id)}


async def _broadcast(frame: dict[str, Any]) -> None:
    """Send one frame to every controller.

    Iterates a copy of the socket collection and wraps each send so that one
    dead socket does not abort the remaining sends.
    """
    for websocket in list(controller_sockets):
        try:
            await websocket.send_json(frame)
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
        await websocket.send_json({"type": "set_color", "color": color})
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _sweeper_task
    _sweeper_task = asyncio.create_task(_sweep_loop())
    try:
        yield
    finally:
        task = _sweeper_task
        _sweeper_task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------


class DeviceRegistration(BaseModel):
    device_id: UUID4
    width: int
    height: int
    device_type: str


class ColorCommand(BaseModel):
    color: str

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str) -> str:
        # Raises ValueError for anything that is not ^#?[0-9a-fA-F]{6}$,
        # which FastAPI turns into a 422.
        return _normalise_color(value)


# ---------------------------------------------------------------------------
# app
# ---------------------------------------------------------------------------

app = FastAPI(lifespan=lifespan)

app.mount(
    "/client",
    StaticFiles(directory="frontend/client", html=True),
    name="client"
)

app.mount(
    "/controller",
    StaticFiles(directory="frontend/controller", html=True),
    name="controller"
)


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------


@app.get("/device/{device_id}")
async def get_device(device_id: str):
    key = _parse_device_id(device_id)
    if key is None or key not in devices:
        raise HTTPException(status_code=404, detail="Unknown device")
    return _device_record(key)


@app.get("/devices/register")
async def registration_info():
    return {"message": "Use POST to register a device"}


@app.post("/devices/register")
async def device_register(device: DeviceRegistration):
    device_id = str(device.device_id)
    existing = devices.get(device_id)

    # The record is complete before anything is awaited; re-registering keeps
    # the assigned colour and any open socket.
    devices[device_id] = {
        "device_id": device_id,
        "width": device.width,
        "height": device.height,
        "type": device.device_type,
        "color": existing["color"] if existing is not None else None,
        "last_seen": _now_iso(),
    }
    record = _device_record(device_id)

    await _broadcast({"type": "device_updated", "device": record})

    return {
        "registered": True,
        "device": device_id
    }


@app.post("/devices/color")
async def change_all_colors(command: ColorCommand):
    color = command.color
    device_ids = list(devices)

    for device_id in device_ids:
        devices[device_id]["color"] = color
    records = [_device_record(device_id) for device_id in device_ids]

    delivered = 0
    for device_id in device_ids:
        if await _send_color_to_device(device_id, color):
            delivered += 1
    for record in records:
        await _broadcast({"type": "device_updated", "device": record})

    return {"color": color, "updated": len(device_ids), "delivered": delivered}


@app.post("/devices/{device_id}/color")
async def change_color(device_id: str, command: ColorCommand):
    key = _parse_device_id(device_id)
    if key is None or key not in devices:
        raise HTTPException(status_code=404, detail="Unknown device")

    color = command.color
    devices[key]["color"] = color
    record = _device_record(key)

    delivered = await _send_color_to_device(key, color)
    await _broadcast({"type": "device_updated", "device": record})

    return {"device_id": key, "color": color, "delivered": delivered}


@app.delete("/devices/{device_id}")
async def delete_device(device_id: str):
    key = _parse_device_id(device_id)
    if key is None or key not in devices:
        raise HTTPException(status_code=404, detail="Unknown device")

    # Both mutations happen before the first await, so no request can observe
    # a half-removed device.
    record = devices.pop(key)
    websocket = device_sockets.pop(key, None)

    if websocket is not None:
        with contextlib.suppress(Exception):
            await websocket.close(code=WS_CLOSE_NORMAL)
        await _broadcast_offline(key, record["last_seen"])

    # device_offline says "its socket is gone"; device_removed says "drop the
    # tile". A controller that did not issue the DELETE needs the second one,
    # otherwise it keeps rendering a device that no longer exists.
    await _broadcast({"type": "device_removed", "device_id": key})

    return {"removed": True, "device_id": key}


@app.get("/devices")
async def get_devices():
    return {device_id: _device_record(device_id) for device_id in list(devices)}


@app.get("/")
async def root():
    return {
        "message": "Hello Tablet Wall"
    }


# ---------------------------------------------------------------------------
# WebSockets
# ---------------------------------------------------------------------------


async def _device_loop(websocket: WebSocket, device_id: str) -> None:
    """Read frames from a device socket until it goes away."""
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return

        text = message.get("text")
        if not text:
            continue
        try:
            payload = json.loads(text)
        except ValueError:
            continue  # unrecognised frames are ignored, not fatal

        if isinstance(payload, dict) and payload.get("type") == "heartbeat":
            # A replaced socket must not keep the new one alive.
            if device_sockets.get(device_id) is websocket and device_id in devices:
                devices[device_id]["last_seen"] = _now_iso()


@app.websocket("/ws/device")
async def ws_device(websocket: WebSocket, device_id: str | None = Query(default=None)):
    # Accept first so a browser can observe the protocol's custom close codes
    # (a rejected handshake would only ever surface as 1006 to the client).
    await websocket.accept()

    key = _parse_device_id(device_id)
    if key is None:
        await websocket.close(code=WS_CLOSE_BAD_REQUEST)
        return
    if key not in devices:
        await websocket.close(code=WS_CLOSE_UNKNOWN_DEVICE)
        return

    # One socket per device: this one takes over the slot before the first
    # await, and the replaced socket's own task finds it no longer owns the
    # slot, so it closes with 4409 without broadcasting device_offline.
    replaced = device_sockets.get(key)
    device_sockets[key] = websocket
    devices[key]["last_seen"] = _now_iso()

    if replaced is not None and replaced is not websocket:
        with contextlib.suppress(Exception):
            await replaced.close(code=WS_CLOSE_REPLACED)

    try:
        await websocket.send_json({
            "type": "welcome",
            "device_id": key,
            "heartbeat_interval_ms": HEARTBEAT_INTERVAL_MS,
        })
        color = devices[key].get("color")
        if color:
            await websocket.send_json({"type": "set_color", "color": color})
        await _broadcast({"type": "device_online", "device": _device_record(key)})
        await _device_loop(websocket, key)
    except WebSocketDisconnect:
        pass
    finally:
        if device_sockets.get(key) is websocket:
            device_sockets.pop(key, None)
            last_seen = devices.get(key, {}).get("last_seen", _now_iso())
            await _broadcast_offline(key, last_seen)


@app.websocket("/ws/controller")
async def ws_controller(websocket: WebSocket):
    await websocket.accept()
    controller_sockets.add(websocket)
    try:
        # The snapshot is built and sent with no await in between, so it is
        # guaranteed to be this controller's first frame.
        snapshot = [_device_record(device_id) for device_id in list(devices)]
        await websocket.send_json({"type": "snapshot", "devices": snapshot})

        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
    except WebSocketDisconnect:
        return
    finally:
        controller_sockets.discard(websocket)
