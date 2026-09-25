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
from collections.abc import Callable
from contextlib import asynccontextmanager
from copy import deepcopy
from math import sqrt
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, UUID4, ConfigDict, Field, field_validator, model_validator

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
# Persistence of the wall state (PROTOCOL.md "Persistence"): the roster,
# sockets, presence, and heartbeat timestamps stay in memory.
from tabletwall.persist import load_state, save_state
# Re-exports of the state objects (never copies): tests clear and reset them
# through ``main`` (``main.devices.clear()``, ``main.wall.update(...)``, …)
# and must keep mutating what the running app uses.
from tabletwall.state import (
    _device_record,
    _fresh_wall,
    _is_online,
    _new_generation,
    _wall_state,
    controller_protocols,
    controller_sockets,
    device_sockets,
    devices,
    wall,
)

_sweeper_task: asyncio.Task[Any] | None = None


def _restore_wall_state() -> None:
    """Load the persisted wall state before the app can accept a socket.

    The generation is minted fresh on **every** start: a normal restart, a
    restored backup, and a rolled-back database must all force clients to
    resynchronise rather than reject the server's state as stale
    (PROTOCOL.md "Revision and generation"). The revision itself is persisted
    and continues from where it left off, and the row is rewritten at once so
    the database always holds the lineage the running server is actually
    using.
    """
    persisted = load_state()
    wall.clear()
    wall.update(persisted if persisted is not None else _fresh_wall())
    wall["generation"] = _new_generation()
    save_state(wall)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _sweeper_task
    # Before the first yield: no socket may be accepted against state that
    # has not been loaded from the database.
    _restore_wall_state()
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
    """``PUT /wall`` body — layout only: any subset of ``width``/``height``.

    Content does not belong here any more, so an unknown key (``mode``, say)
    is a 422 rather than a silently ignored setting: ``PUT /scene`` owns it.
    """

    width: int | None = None
    height: int | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("width", "height")
    @classmethod
    def positive_dimension(cls, value: int | None) -> int | None:
        # Raises ValueError for a dimension that is not a positive int,
        # which FastAPI turns into a 422.
        if value is not None and value <= 0:
            raise ValueError("width and height must be positive integers")
        return value


class SceneContent(BaseModel):
    """The scene's ``content`` object, discriminated by ``type``.

    Unknown keys are forbidden here exactly as they are on the ``PUT``
    bodies: a client still sending the removed ``mode`` field gets a 422
    rather than having it quietly ignored (PROTOCOL.md "Unknown keys").
    """

    type: str

    model_config = ConfigDict(extra="forbid")

    @field_validator("type")
    @classmethod
    def supported_type(cls, value: str) -> str:
        # Raises ValueError — FastAPI turns it into a 422 — for a type the
        # server cannot render: the reserved-but-unimplemented ``image``, or
        # anything unknown (PROTOCOL.md "HTTP (v2 additions)").
        if value == "image":
            raise ValueError("image content is reserved but not implemented")
        if value not in ("color", "calibration"):
            raise ValueError("unknown content type")
        return value


class SceneUpdate(BaseModel):
    """``PUT /scene`` body — content only, nothing else may be set."""

    content: SceneContent

    model_config = ConfigDict(extra="forbid")


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
# commit boundary (PROTOCOL.md "Persistence")
# ---------------------------------------------------------------------------


def _commit_wall(change: Callable[[dict[str, Any]], None]) -> None:
    """Persist a wall change, and only then let it into memory.

    ``change`` applies one logical mutation to a wall-state dict. It runs
    first on a **detached copy** of the live state, whose revision is bumped
    and whose row is written; only once that write has committed does the same
    ``change`` run on the live ``wall`` — mutated in place, because ``wall``
    is re-exported through ``main`` and tests hold its identity — with the
    same revision bump.

    The ordering is the whole point: if ``save_state`` raises, nothing has
    touched memory yet, so the live state, the database, and what subscribers
    have been told all still agree, the route fails loudly as a 5xx, and no
    broadcast follows (PROTOCOL.md "A commit happens before notification, so
    a controller is never told about state that would not survive a
    restart"). Every wall-mutating route commits through here.
    """
    proposed = deepcopy(wall)
    change(proposed)
    proposed["revision"] += 1
    save_state(proposed)

    # Reached only when the write committed.
    change(wall)
    wall["revision"] += 1


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

    # The placement goes with the device: left behind, it keeps the wall map
    # drawing a panel that no longer exists and reserves a hole on the wall
    # that nothing can ever fill. The removal is *committed* first — the copy
    # is persisted before the live wall is touched and long before the roster
    # and socket entries are popped below — so a failed save cannot remove a
    # device in memory while leaving its placement on disk.
    dropped_placement = key in wall["layout"]["placements"]
    if dropped_placement:
        def apply(target: dict[str, Any]) -> None:
            target["layout"]["placements"].pop(key, None)

        _commit_wall(apply)

    # Both pops happen before the first await, so no request can observe a
    # half-removed device — and only after any wall change above is durable.
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
    # Layout only. The change is written to the database from a detached copy
    # before it touches the live wall (``_commit_wall``), so a failed save
    # leaves memory untouched and this route fails loudly instead of
    # diverging from disk; only after the commit is the new state broadcast —
    # no request can observe a half-updated wall (PROTOCOL.md "Concurrency
    # rules") and no controller hears about state that would not survive a
    # restart (PROTOCOL.md "Persistence").
    def apply(target: dict[str, Any]) -> None:
        layout = target["layout"]
        if update.width is not None:
            layout["width"] = update.width
        if update.height is not None:
            layout["height"] = update.height

    _commit_wall(apply)
    await _broadcast_wall()
    return _wall_state()


@app.put("/scene")
async def put_scene(update: SceneUpdate):
    # Content only: the layout is untouched, the revision bumps, the new
    # state is committed, and only then is it broadcast — same ordering as
    # ``PUT /wall`` above.
    content = update.content.model_dump()

    def apply(target: dict[str, Any]) -> None:
        target["scene"]["content"] = content

    _commit_wall(apply)
    await _broadcast_wall()
    return _wall_state()


@app.put("/devices/{device_id}/placement")
async def put_placement(device_id: str, placement: PlacementCommand):
    # Placing is reserved for a device the server knows: you cannot place a
    # device that has never registered, so an unknown (or malformed) id is a
    # 404. Only *releasing* has to work without the roster — see the DELETE
    # route below.
    key = _parse_device_id(device_id)
    if key is None or key not in devices:
        raise HTTPException(status_code=404, detail="Unknown device")

    def apply(target: dict[str, Any]) -> None:
        # Stored with its device_id (PROTOCOL.md's canonical placement shape);
        # the per-device ``wall`` frame strips it again. Built inside ``apply``
        # so the persisted copy and the live wall never share one dict.
        target["layout"]["placements"][key] = {
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

    _commit_wall(apply)
    await _broadcast_wall()
    return _wall_state()


@app.delete("/devices/{device_id}/placement")
async def delete_placement(device_id: str):
    key = _parse_device_id(device_id)
    # 404 only when there is *neither* a known device nor a placement to
    # remove. Placements are persisted and the roster is not, so a restart
    # can leave a placement owned by a device the server has forgotten: that
    # is a reservation the operator must be able to release, so a valid id
    # with a placement succeeds even when the device is absent (PROTOCOL.md
    # "DELETE /devices/{device_id}/placement").
    known = key is not None and key in devices
    reserved = key is not None and key in wall["layout"]["placements"]
    if not (known or reserved):
        raise HTTPException(status_code=404, detail="Unknown device")

    # 200 even when there was no placement to clear.
    def apply(target: dict[str, Any]) -> None:
        target["layout"]["placements"].pop(key, None)

    _commit_wall(apply)
    await _broadcast_wall()
    return _wall_state()


@app.post("/wall/auto")
async def wall_auto(command: WallAutoCommand | None = None):
    """Place every online device in a regular grid covering the wall.

    Offline devices keep whatever placement they had, and reservations whose
    device is absent from the roster entirely are left alone too: releasing a
    vacant slot is an explicit, separate action (PROTOCOL.md
    ``POST /wall/auto``). With no ``columns`` the default is
    ``max(1, round(sqrt(n)))`` where n is the number of online devices; cell
    edges are rounded so the grid tiles the wall in whole units.
    """
    online = [device_id for device_id in list(devices) if _is_online(device_id)]
    count = len(online)

    if command is not None and command.columns is not None:
        columns = command.columns
    else:
        columns = max(1, round(sqrt(count)))
    rows = max(1, -(-count // columns))

    width = wall["layout"]["width"]
    height = wall["layout"]["height"]
    # Cell edges are rounded so the grid tiles the wall exactly in integer
    # units: adjacent cells share an edge and nothing overlaps or gaps.
    assigned: dict[str, dict[str, Any]] = {}
    for index, device_id in enumerate(online):
        column = index % columns
        row = index // columns
        x0 = round(column * width / columns)
        x1 = round((column + 1) * width / columns)
        y0 = round(row * height / rows)
        y1 = round((row + 1) * height / rows)
        assigned[device_id] = {
            "device_id": device_id,
            "x": x0,
            "y": y0,
            "w": x1 - x0,
            "h": y1 - y0,
            "bezel": {"top": 0, "right": 0, "bottom": 0, "left": 0},
        }

    def apply(target: dict[str, Any]) -> None:
        # Only the online devices are assigned; everything else in the
        # placements map — offline devices and vacant reservations alike —
        # survives untouched.
        target["layout"]["placements"].update(assigned)

    _commit_wall(apply)
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
