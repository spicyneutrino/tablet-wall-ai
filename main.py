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
from math import sqrt
from typing import Any, Literal

import anyio
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, UUID4, Field, field_validator, model_validator

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
# Post-handshake close for a present-but-unsupported ``protocol`` query param,
# so a browser can observe the code rather than a bare 1006 (PROTOCOL.md
# "Protocol versions").
WS_CLOSE_UNSUPPORTED_PROTOCOL = 4426

# Protocol negotiation (PROTOCOL.md "Protocol versions"). An absent ``protocol``
# means version 1; only these majors are accepted.
SUPPORTED_PROTOCOLS = (1, 2)

# What this server can render/serve for version-2 clients.
SERVER_CAPS = ["calibration"]

# Wall defaults (PROTOCOL.md "Wall state"): a 2x1 wall of landscape panels.
DEFAULT_WALL_WIDTH = 2000
DEFAULT_WALL_HEIGHT = 1000


def _fresh_wall() -> dict[str, Any]:
    """A brand-new wall state: the PROTOCOL.md defaults, revision 0."""
    return {
        "width": DEFAULT_WALL_WIDTH,
        "height": DEFAULT_WALL_HEIGHT,
        "mode": "color",
        "revision": 0,
        "placements": {},
    }


# Roster: device_id -> device record. Only metadata is stored; ``online`` is
# derived from the presence of a live socket plus ``last_seen``.
devices: dict[str, dict[str, Any]] = {}

# One open socket per device, and every open controller socket.
device_sockets: dict[str, WebSocket] = {}
controller_sockets: set[WebSocket] = set()

# The negotiated protocol major for every connected controller. Kept beside
# ``controller_sockets`` so version-1 controllers never see a version-2 frame.
controller_protocols: dict[WebSocket, int] = {}

# In-memory wall state (PROTOCOL.md "Version 2 — wall, placements, and scenes").
# Persistence is a later increment; tests reset it via ``_fresh_wall``.
wall: dict[str, Any] = _fresh_wall()

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


def _parse_protocol(raw: str | None) -> int | None:
    """Negotiate the major protocol version from the ``protocol`` query param.

    Absent means version 1 (PROTOCOL.md "Protocol versions"). Returns None
    when the param is present but unparseable or unsupported — the caller
    accepts the handshake first and then closes with 4426, so a browser can
    observe the real close code.
    """
    if raw is None:
        return 1
    try:
        version = int(raw)
    except (TypeError, ValueError):
        return None
    return version if version in SUPPORTED_PROTOCOLS else None


def _parse_caps(raw: str | None) -> list[str]:
    """Split the comma-separated ``caps`` query param into a clean list."""
    if not raw:
        return []
    return [cap.strip() for cap in raw.split(",") if cap.strip()]


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
    """The wire shape of a device record (PROTOCOL.md "Device record").

    Also carries the version-2 additions: ``protocol`` (the major negotiated
    by the last socket, or None before any socket connected) and ``caps`` (the
    capabilities that socket advertised, empty until then).
    """
    record = devices[device_id]
    return {
        **record,
        "protocol": record.get("protocol"),
        "caps": list(record.get("caps") or []),
        "online": _is_online(device_id),
    }


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
# wall state (PROTOCOL.md "Version 2 — wall, placements, and scenes")
# ---------------------------------------------------------------------------


def _placement_for_client(placement: dict[str, Any] | None) -> dict[str, Any] | None:
    """The wire shape of a placement: the example frame carries no device_id
    (the frame is already about the receiving device); the stored copy keeps
    it, matching the canonical placement example in PROTOCOL.md."""
    if placement is None:
        return None
    return {
        "x": placement["x"],
        "y": placement["y"],
        "w": placement["w"],
        "h": placement["h"],
        "bezel": dict(placement["bezel"]),
    }


def _wall_state() -> dict[str, Any]:
    """A detached copy of the wall state, safe to hand to a caller or a frame."""
    return {
        "width": wall["width"],
        "height": wall["height"],
        "mode": wall["mode"],
        "revision": wall["revision"],
        "placements": {
            device_id: {**placement, "bezel": dict(placement["bezel"])}
            for device_id, placement in wall["placements"].items()
        },
    }


def _wall_frame(device_id: str, record: dict[str, Any]) -> dict[str, Any]:
    """Build the ``wall`` frame for one device (version 2 only).

    Per-device mode downgrade: a device that did not advertise the
    ``calibration`` cap is never asked to render a calibration pattern, so it
    is told the wall is in ``color`` mode instead.
    """
    mode = wall["mode"]
    if mode == "calibration" and "calibration" not in record.get("caps", ()):
        mode = "color"
    return {
        "type": "wall",
        "revision": wall["revision"],
        "mode": mode,
        "wall": {"width": wall["width"], "height": wall["height"]},
        "placement": _placement_for_client(wall["placements"].get(device_id)),
    }


async def _send_wall_to_device(
    device_id: str, websocket: WebSocket, record: dict[str, Any]
) -> None:
    """Send the current ``wall`` frame to one version-2 device socket."""
    try:
        await websocket.send_json(_wall_frame(device_id, record))
    except Exception:
        # Drop *and* close (the pattern from ``_broadcast``), then report the
        # device offline: a failed send means the socket is gone, and dropping
        # the slot silently would leave controllers rendering a live-looking
        # tablet forever — the device task's own finally block skips the
        # broadcast once somebody else owns the slot.
        if device_sockets.get(device_id) is websocket:
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
        if controller_protocols.get(websocket, 1) != 2:
            continue
        try:
            await websocket.send_json(wall_updated)
        except Exception:
            controller_sockets.discard(websocket)
            controller_protocols.pop(websocket, None)
            with contextlib.suppress(Exception):
                await websocket.close(code=WS_CLOSE_NORMAL)

    for device_id, websocket in list(device_sockets.items()):
        record = devices.get(device_id)
        if record is None or record.get("protocol") != 2:
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
