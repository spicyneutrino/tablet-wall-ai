"""FastAPI backend for tablet-wall-ai.

Phase 1 adds the realtime layer described in ``PROTOCOL.md``: WebSocket
endpoints for devices and the controller, heartbeat-driven presence, and
colour commands. The implementation lives in the ``tabletwall`` package —
``protocol`` (constants and validation helpers), ``state`` (the in-memory
registries), and ``hub`` (frame delivery and the heartbeat sweeper) — while
this module keeps the FastAPI app, lifespan, and routes.
"""

import asyncio
import contextlib
import json
from contextlib import asynccontextmanager
from math import sqrt
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, UUID4, Field, field_validator, model_validator

# ``tabletwall.hub`` is imported both as a module and as its individual names:
# the tests patch the sweeper's timing constants on the reader module, i.e.
# ``monkeypatch.setattr(main.hub, "HEARTBEAT_TIMEOUT_S", ...)``.
from tabletwall import hub
from tabletwall.hub import (
    _broadcast,
    _broadcast_offline,
    _broadcast_wall,
    _send_color_to_device,
    _send_wall_to_device,
    _sweep_loop,
)
from tabletwall.protocol import (
    HEARTBEAT_INTERVAL_MS,
    SERVER_CAPS,
    WS_CLOSE_BAD_REQUEST,
    WS_CLOSE_NORMAL,
    WS_CLOSE_REPLACED,
    WS_CLOSE_UNKNOWN_DEVICE,
    WS_CLOSE_UNSUPPORTED_PROTOCOL,
    _now_iso,
    _normalise_color,
    _parse_caps,
    _parse_device_id,
    _parse_protocol,
)
# Re-exports of the state objects (never copies): tests clear and reset them
# through ``main`` (``main.devices.clear()``, ``main.wall.update(...)``, …)
# and must keep mutating what the running app uses.
from tabletwall.state import (
    _device_record,
    _fresh_wall,
    _is_online,
    _wall_state,
    controller_protocols,
    controller_sockets,
    device_sockets,
    devices,
    wall,
)

_sweeper_task: asyncio.Task[Any] | None = None


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


class WallUpdate(BaseModel):
    """``PUT /wall`` body — any subset of ``width``/``height``/``mode``."""

    width: int | None = None
    height: int | None = None
    mode: Literal["color", "calibration"] | None = None

    @field_validator("width", "height")
    @classmethod
    def positive_dimension(cls, value: int | None) -> int | None:
        # Raises ValueError for a dimension that is not a positive int,
        # which FastAPI turns into a 422.
        if value is not None and value <= 0:
            raise ValueError("width and height must be positive integers")
        return value


class Bezel(BaseModel):
    """How much of each edge the device frame covers, in wall units."""

    top: int = 0
    right: int = 0
    bottom: int = 0
    left: int = 0


class PlacementCommand(BaseModel):
    """``PUT /devices/{device_id}/placement`` body.

    ``bezel`` is optional and defaults to zero on every edge. The rect must be
    positive and the bezel must leave a positive visible rect — otherwise the
    model raises, which FastAPI turns into a 422 (PROTOCOL.md "Wall coordinate
    space").
    """

    x: int
    y: int
    w: int
    h: int
    bezel: Bezel = Field(default_factory=Bezel)

    @model_validator(mode="after")
    def validate_rect(self) -> "PlacementCommand":
        if self.w <= 0 or self.h <= 0:
            raise ValueError("placement rect must have positive width and height")
        if self.w - self.bezel.left - self.bezel.right <= 0:
            raise ValueError("bezel must leave a positive visible width")
        if self.h - self.bezel.top - self.bezel.bottom <= 0:
            raise ValueError("bezel must leave a positive visible height")
        return self


class WallAutoCommand(BaseModel):
    """``POST /wall/auto`` body — ``columns`` is optional."""

    columns: int | None = None

    @field_validator("columns")
    @classmethod
    def positive_columns(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("columns must be a positive integer")
        return value


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
    # the assigned colour, any open socket, and the protocol negotiated by that
    # socket (the client re-registers before every connection attempt, so the
    # record would otherwise flap back to "no protocol" while still online).
    devices[device_id] = {
        "device_id": device_id,
        "width": device.width,
        "height": device.height,
        "type": device.device_type,
        "color": existing["color"] if existing is not None else None,
        "protocol": existing.get("protocol") if existing is not None else None,
        "caps": list(existing.get("caps") or []) if existing is not None else [],
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
    # a half-removed device. The placement goes with the device: left behind,
    # it keeps the wall map drawing a panel that no longer exists and reserves
    # a hole on the wall that nothing can ever fill.
    record = devices.pop(key)
    websocket = device_sockets.pop(key, None)
    dropped_placement = wall["placements"].pop(key, None) is not None
    if dropped_placement:
        wall["revision"] += 1

    if websocket is not None:
        with contextlib.suppress(Exception):
            await websocket.close(code=WS_CLOSE_NORMAL)
        await _broadcast_offline(key, record["last_seen"])

    # device_offline says "its socket is gone"; device_removed says "drop the
    # tile". A controller that did not issue the DELETE needs the second one,
    # otherwise it keeps rendering a device that no longer exists.
    await _broadcast({"type": "device_removed", "device_id": key})

    if dropped_placement:
        await _broadcast_wall()

    return {"removed": True, "device_id": key}


@app.get("/devices")
async def get_devices():
    return {device_id: _device_record(device_id) for device_id in list(devices)}


# ---------------------------------------------------------------------------
# Wall HTTP API (PROTOCOL.md "Version 2 — HTTP")
# ---------------------------------------------------------------------------


@app.get("/wall")
async def get_wall():
    return _wall_state()


@app.put("/wall")
async def put_wall(update: WallUpdate):
    # The whole state is mutated before the first await, then the revision is
    # bumped and the new state broadcast — no request can observe a half-updated
    # wall (PROTOCOL.md "Concurrency rules").
    if update.width is not None:
        wall["width"] = update.width
    if update.height is not None:
        wall["height"] = update.height
    if update.mode is not None:
        wall["mode"] = update.mode
    wall["revision"] += 1

    await _broadcast_wall()
    return _wall_state()


@app.put("/devices/{device_id}/placement")
async def put_placement(device_id: str, placement: PlacementCommand):
    key = _parse_device_id(device_id)
    if key is None or key not in devices:
        raise HTTPException(status_code=404, detail="Unknown device")

    # Stored with its device_id (PROTOCOL.md's canonical placement shape); the
    # per-device ``wall`` frame strips it again.
    wall["placements"][key] = {
        "device_id": key,
        "x": placement.x,
        "y": placement.y,
        "w": placement.w,
        "h": placement.h,
        "bezel": {
            "top": placement.bezel.top,
            "right": placement.bezel.right,
            "bottom": placement.bezel.bottom,
            "left": placement.bezel.left,
        },
    }
    wall["revision"] += 1

    await _broadcast_wall()
    return _wall_state()


@app.delete("/devices/{device_id}/placement")
async def delete_placement(device_id: str):
    key = _parse_device_id(device_id)
    if key is None or key not in devices:
        raise HTTPException(status_code=404, detail="Unknown device")

    # 200 even when there was no placement to clear.
    wall["placements"].pop(key, None)
    wall["revision"] += 1

    await _broadcast_wall()
    return _wall_state()


@app.post("/wall/auto")
async def wall_auto(command: WallAutoCommand | None = None):
    """Place every online device in a regular grid covering the wall.

    Offline devices keep whatever placement they had. With no ``columns`` the
    default is ``max(1, round(sqrt(n)))`` where n is the number of online
    devices; cell edges are rounded so the grid tiles the wall in whole units.
    """
    online = [device_id for device_id in list(devices) if _is_online(device_id)]
    count = len(online)

    if command is not None and command.columns is not None:
        columns = command.columns
    else:
        columns = max(1, round(sqrt(count)))
    rows = max(1, -(-count // columns))

    width = wall["width"]
    height = wall["height"]
    # Cell edges are rounded so the grid tiles the wall exactly in integer
    # units: adjacent cells share an edge and nothing overlaps or gaps.
    for index, device_id in enumerate(online):
        column = index % columns
        row = index // columns
        x0 = round(column * width / columns)
        x1 = round((column + 1) * width / columns)
        y0 = round(row * height / rows)
        y1 = round((row + 1) * height / rows)
        wall["placements"][device_id] = {
            "device_id": device_id,
            "x": x0,
            "y": y0,
            "w": x1 - x0,
            "h": y1 - y0,
            "bezel": {"top": 0, "right": 0, "bottom": 0, "left": 0},
        }
    wall["revision"] += 1

    await _broadcast_wall()
    return _wall_state()


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
async def ws_device(
    websocket: WebSocket,
    device_id: str | None = Query(default=None),
    protocol: str | None = Query(default=None),
    caps: str | None = Query(default=None),
):
    # Accept first so a browser can observe the protocol's custom close codes
    # (a rejected handshake would only ever surface as 1006 to the client).
    await websocket.accept()

    # Negotiate before anything else: the version decides how the rest of the
    # conversation is framed. An unsupported or unparseable major is reported
    # with 4426 after the handshake so the client can see the code.
    negotiated = _parse_protocol(protocol)
    if negotiated is None:
        await websocket.close(code=WS_CLOSE_UNSUPPORTED_PROTOCOL)
        return

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
    record = devices[key]
    record["last_seen"] = _now_iso()
    record["protocol"] = negotiated
    record["caps"] = _parse_caps(caps)

    if replaced is not None and replaced is not websocket:
        with contextlib.suppress(Exception):
            await replaced.close(code=WS_CLOSE_REPLACED)

    try:
        welcome: dict[str, Any] = {
            "type": "welcome",
            "device_id": key,
            "heartbeat_interval_ms": HEARTBEAT_INTERVAL_MS,
        }
        if negotiated == 2:
            # Version-1 welcomes stay byte-for-byte identical to the original
            # contract; the version-2 keys are added only when negotiated.
            welcome["protocol"] = 2
            welcome["server_caps"] = list(SERVER_CAPS)
        await websocket.send_json(welcome)

        if negotiated == 2:
            # Replay the wall right after welcome so a reconnecting tablet
            # restores the current wall without being told again.
            await _send_wall_to_device(key, websocket, record)

        color = record.get("color")
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
async def ws_controller(
    websocket: WebSocket, protocol: str | None = Query(default=None)
):
    await websocket.accept()

    negotiated = _parse_protocol(protocol)
    if negotiated is None:
        await websocket.close(code=WS_CLOSE_UNSUPPORTED_PROTOCOL)
        return

    controller_sockets.add(websocket)
    controller_protocols[websocket] = negotiated
    try:
        # The snapshot is built and sent with no await in between, so it is
        # guaranteed to be this controller's first frame.
        snapshot = [_device_record(device_id) for device_id in list(devices)]
        frame: dict[str, Any] = {"type": "snapshot", "devices": snapshot}
        if negotiated == 2:
            # Version-1 snapshots stay exactly as originally specified.
            frame["wall"] = _wall_state()
        await websocket.send_json(frame)

        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
    except WebSocketDisconnect:
        return
    finally:
        controller_sockets.discard(websocket)
        controller_protocols.pop(websocket, None)
