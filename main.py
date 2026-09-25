"""FastAPI backend for tablet-wall-ai.

Phase 1 adds the realtime layer described in ``PROTOCOL.md``: WebSocket
endpoints for devices and the controller, heartbeat-driven presence, and
colour commands. The implementation lives in the ``tabletwall`` package —
``protocol`` (constants and validation helpers), ``state`` (the in-memory
registries), ``hub`` (frame delivery and the heartbeat sweeper), and
``assets`` (the curated still-image inventory behind ``GET /assets``) — while
this module keeps the FastAPI app, lifespan, and routes.
"""

import asyncio
import contextlib
import ipaddress
import json
import os
import re
from collections.abc import Callable
from contextlib import asynccontextmanager
from copy import deepcopy
from math import sqrt
from typing import Any
from urllib.parse import urlsplit

from fastapi import (
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, UUID4, ConfigDict, Field, field_validator, model_validator
from starlette.datastructures import Headers

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
    DEFAULT_FIT,
    HEARTBEAT_INTERVAL_MS,
    SERVER_CAPS,
    SUPPORTED_FITS,
    WS_CLOSE_BAD_REQUEST,
    WS_CLOSE_NORMAL,
    WS_CLOSE_REPLACED,
    WS_CLOSE_UNKNOWN_DEVICE,
    WS_CLOSE_UNSUPPORTED_PROTOCOL,
    _is_asset_id,
    _now_iso,
    _normalise_color,
    _parse_caps,
    _parse_device_id,
    _parse_protocol,
    _parse_snapshot_name,
)
# Curated still-image assets (PROTOCOL.md "Still images"): the directory scan,
# content IDs, and byte-verified serving behind ``GET /assets``.
from tabletwall import assets
# Persistence of the wall state (PROTOCOL.md "Persistence"): the roster,
# sockets, presence, and heartbeat timestamps stay in memory. The snapshot
# calls save and read the named layouts/scenes beside that one row and never
# write to it themselves.
from tabletwall.persist import (
    delete_layout,
    delete_scene,
    load_layout,
    load_layouts,
    load_scene,
    load_scenes,
    load_state,
    save_layout,
    save_scene,
    save_state,
)
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
    # Startup scan (PROTOCOL.md "Still images"): inventory the curated image
    # directory before the first request, so a directory that exists but
    # cannot be read fails loudly at boot rather than on the first inventory
    # read. Every later read path re-scans anyway — this pass only establishes
    # the initial inventory (an absent directory is an empty one).
    assets.refresh()
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
    bodies: a client still sending the removed ``mode`` field — or echoing
    the server's derived fields (``url``, ``intrinsicWidth``,
    ``intrinsicHeight``) back at it — gets a 422 rather than having it
    quietly ignored (PROTOCOL.md "Unknown keys").

    An ``image`` variant carries an ``asset`` content ID and an optional
    ``fit``; the URL and intrinsic dimensions are derived by the server, so
    they are not accepted here. Whether the ID names a real file is decided
    by ``PUT /scene`` itself, against a freshly scanned inventory, which is
    also a 422.
    """

    type: str
    asset: str | None = None
    fit: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("type")
    @classmethod
    def supported_type(cls, value: str) -> str:
        # Raises ValueError — FastAPI turns it into a 422 — for a type the
        # server cannot render, or anything unknown (PROTOCOL.md
        # "HTTP (v2 additions)").
        if value not in ("color", "calibration", "image"):
            raise ValueError("unknown content type")
        return value

    @field_validator("fit")
    @classmethod
    def supported_fit(cls, value: str | None) -> str | None:
        # Raises ValueError for anything the renderer cannot honour; only
        # ``cover`` exists today (PROTOCOL.md "Still images").
        if value is not None and value not in SUPPORTED_FITS:
            raise ValueError("only the cover fit is supported")
        return value

    @model_validator(mode="after")
    def validate_variant(self) -> "SceneContent":
        if self.type == "image":
            if self.asset is None:
                raise ValueError("image content requires an asset id")
            if not _is_asset_id(self.asset):
                raise ValueError("asset must be sha256:<64 lowercase hex digits>")
            if self.fit is None:
                # Resolved here so the scene is persisted with the fit it
                # will actually be rendered with, never an implied one.
                self.fit = DEFAULT_FIT
        elif self.asset is not None or self.fit is not None:
            raise ValueError(f"{self.type} content takes neither asset nor fit")
        return self


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


def _snapshot_name(raw: str) -> str:
    """Canonical saved-name for a layout or scene, or a 422 if there isn't one.

    Every save/recall/delete route runs its path segment through here first,
    so all six of them agree on what a name is (PROTOCOL.md "Scene": trimmed,
    1-64 characters, ASCII letter or digit first, then letters, digits, space,
    and ``.`` ``_`` ``-``). Malformed is the caller's mistake and answers 422
    *before* any database access; a well-formed name that was simply never
    saved is an absence and is left to the route, which answers 404.
    """
    name = _parse_snapshot_name(raw)
    if name is None:
        raise HTTPException(status_code=422, detail="Invalid name")
    return name


def _valid_saved_layout(saved: Any) -> bool:
    """Check a stored snapshot before it can replace the active wall.

    SQLite is server-owned, but a damaged/older row must not commit a wall
    that fails later in ``_wall_state`` or the device frame projector.
    Accept the same placement shape we persist, including vacant reservations;
    the roster is deliberately irrelevant here.
    """
    if not isinstance(saved, dict) or set(saved) != {"width", "height", "placements"}:
        return False
    if any(type(saved[k]) is not int or saved[k] <= 0 for k in ("width", "height")):
        return False
    placements = saved["placements"]
    if not isinstance(placements, dict):
        return False
    for device_id, placement in placements.items():
        if _parse_device_id(device_id) != device_id or not isinstance(placement, dict):
            return False
        if set(placement) != {"device_id", "x", "y", "w", "h", "bezel"}:
            return False
        if placement["device_id"] != device_id:
            return False
        if any(type(placement[k]) is not int for k in ("x", "y", "w", "h")):
            return False
        if placement["w"] <= 0 or placement["h"] <= 0:
            return False
        bezel = placement["bezel"]
        if not isinstance(bezel, dict) or set(bezel) != {"top", "right", "bottom", "left"}:
            return False
        if any(type(value) is not int for value in bezel.values()):
            return False
        if (placement["w"] - bezel["left"] - bezel["right"] <= 0 or
                placement["h"] - bezel["top"] - bezel["bottom"] <= 0):
            return False
    return True


def _valid_saved_content(saved: Any) -> bool:
    """Reject malformed stored content without checking image availability."""
    if not isinstance(saved, dict):
        return False
    kind = saved.get("type")
    if kind in ("color", "calibration"):
        return set(saved) == {"type"}
    if kind != "image" or set(saved) != {
        "type", "asset", "fit", "intrinsicWidth", "intrinsicHeight"
    }:
        return False
    return (
        isinstance(saved["asset"], str)
        and _is_asset_id(saved["asset"])
        and saved["fit"] in SUPPORTED_FITS
        and type(saved["intrinsicWidth"]) is int
        and saved["intrinsicWidth"] > 0
        and type(saved["intrinsicHeight"]) is int
        and saved["intrinsicHeight"] > 0
    )


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
# Operator origin guard (DEFENSE-IN-DEPTH, NOT AUTHENTICATION)
# ---------------------------------------------------------------------------
#
# ``TABLET_WALL_OPERATOR_ORIGIN`` (e.g. ``https://operator.wall.test``)
# optionally pins which browser origin is allowed to drive a *write*: when it
# is set, every state-changing HTTP request must carry exactly one ``Origin``
# header equal to it, and the ``/ws/controller`` handshake must prove the same
# before it is upgraded.
#
# What this is: a CSRF/cross-site request fence. It says "the request came
# from the operator page we serve", nothing more.
#
# What this is NOT, and must never be described as: authentication or
# authorization. There is no identity, credential, token, or session scheme
# here at all — an ``Origin`` header is trivially forged by anything that is
# not a browser, so this only constrains browsers. Authenticating the operator
# is the reverse proxy's job in front of this app; treat this guard as a
# second, independent line of defence, never as the only one.
#
# With the variable unset (the default, and how ``make dev`` runs) the guard
# is inert: no header is required and nothing about direct local development
# changes. The environment is read per request, so a running server picks up
# a change without a code change, and tests can flip it per case.
#
# ``GET /operator-config`` (below) reports where the *tablet* page is served
# from; it is a plain read and is not guarded — who may read it is the
# proxy's call, not this guard's.

OPERATOR_ORIGIN_ENV = "TABLET_WALL_OPERATOR_ORIGIN"
TABLET_ORIGIN_ENV = "TABLET_WALL_TABLET_ORIGIN"

# The methods that change something. Reads (GET/HEAD/OPTIONS) are never
# guarded, so the pages, the asset inventory, and CORS preflight traffic are
# untouched.
_GUARDED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# The one state-changing endpoint reachable without a matching operator
# origin: a tablet registers itself from the tablet page, which is served
# under the *tablet* origin and can never present the operator's. Registration
# is the protocol's deliberately public write (it carries no privilege beyond
# "here is my id and size"), and a tablet must be able to introduce itself
# before anything else can be arranged around it.
_ORIGIN_EXEMPT_POST_PATHS = frozenset({"/devices/register"})

# Outcome of reading an origin variable: unset (guard off), valid (compare
# exactly), invalid (fail closed). "Invalid" is deliberately not "unset".
_ORIGIN_UNSET = "unset"
_ORIGIN_VALID = "valid"
_ORIGIN_INVALID = "invalid"

# A DNS hostname: labels of alphanumerics and inner hyphens, dots between.
_ORIGIN_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_ORIGIN_HOSTNAME = re.compile(rf"^{_ORIGIN_LABEL}(?:\.{_ORIGIN_LABEL})*$")


def _validated_origin(value: str) -> str | None:
    """``value`` when it is *exactly* ``scheme://host[:port]``, else ``None``.

    Strictness is the feature. The guard compares this string byte for byte
    against the request's ``Origin`` header — that is what makes the check
    unambiguous — so a configured value the browser could never send is a
    *configuration* error and must be rejected rather than quietly repaired:
    a path (even a bare ``/``), a query, a fragment, userinfo, a wildcard
    host, a missing or non-http(s) scheme, whitespace/control characters, a
    port that does not parse, a hostname that is neither a DNS name nor an IP
    literal, or anything ``urlsplit`` would silently normalise away (a
    uppercased scheme, say) all yield ``None``.

    Callers must never treat ``None`` as "not configured": for the guard that
    would open the gate the operator meant to close, and for
    ``GET /operator-config`` it would hand out a value nobody can trust.
    """
    if not value or not value.isascii():
        return None
    # No whitespace anywhere — ``urlsplit``/``URL`` strip tabs and newlines
    # on their own, which would turn "something the browser cannot send"
    # into something it can. Everything must stay printable ASCII.
    if any(ch.isspace() or not 0x21 <= ord(ch) <= 0x7E for ch in value):
        return None
    # No wildcards (never valid in an origin), no userinfo at all (credentials
    # do not belong in an origin), no backslash (several parsers read it as a
    # path separator, so it would mean two different things to two readers).
    if any(ch in value for ch in "*@\\"):
        return None
    try:
        parts = urlsplit(value)
        hostname = parts.hostname
        port = parts.port
    except ValueError:
        # Unbalanced IPv6 brackets, or a port that is not a number.
        return None
    if parts.scheme not in ("http", "https"):
        return None
    if not parts.netloc:
        return None
    if parts.username is not None or parts.password is not None:
        return None
    if parts.path or parts.query or parts.fragment:
        return None
    if port is not None and not 1 <= port <= 65535:
        return None
    # Round-trip: the pieces must rebuild the input exactly, so nothing was
    # folded, dropped, or lowercased on the way in. This is also why the
    # scheme must be written lowercase — the browser will send it that way.
    if f"{parts.scheme}://{parts.netloc}" != value:
        return None
    if not hostname:
        return None
    if ":" in hostname:
        # An IPv6 literal; ``urlsplit`` has already removed the brackets.
        try:
            ipaddress.IPv6Address(hostname)
        except ValueError:
            return None
    elif not _ORIGIN_HOSTNAME.fullmatch(hostname):
        return None
    return value


def _origin_env_state(name: str) -> tuple[str, str | None]:
    """Read ``name`` as ``(state, origin)``.

    Unset *and* empty both mean "not configured": an empty variable in a
    deployment manifest is how you switch a value off, and it must behave
    exactly like never having set it (the guard then stays inert, as it is in
    a plain dev run). A value that is set but does not validate is something
    else again — it comes back ``_ORIGIN_INVALID`` with no origin, so callers
    fail closed instead of silently disabling the guard.
    """
    raw = os.environ.get(name)
    if not raw:
        return _ORIGIN_UNSET, None
    origin = _validated_origin(raw)
    if origin is None:
        return _ORIGIN_INVALID, None
    return _ORIGIN_VALID, origin


def _origin_allowed(origin: str, headers: Headers) -> bool:
    """Exactly one ``Origin`` header, byte for byte equal to ``origin``.

    Absent fails (a browser always sends ``Origin`` on a state-changing
    request, so its absence means a non-browser client — or a request that
    was not shaped the way this guard expects). Duplicated fails, because two
    ``Origin`` headers mean some hop re-sent or merged them and the comparison
    is no longer trustworthy. So does the literal ``null`` a sandboxed iframe
    or a ``file://`` page sends.
    """
    values = headers.getlist("origin")
    return len(values) == 1 and values[0] == origin


def _origin_denial(headers: Headers) -> JSONResponse | None:
    """A 403 response when these headers do not satisfy the guard, else ``None``.

    ``None`` means "allowed" — either no operator origin is configured at
    all, or the single ``Origin`` header matches the configured one exactly.
    """
    state, origin = _origin_env_state(OPERATOR_ORIGIN_ENV)
    if state == _ORIGIN_UNSET:
        return None
    if state == _ORIGIN_INVALID:
        # Fail closed, loudly: the operator asked for the guard and the value
        # they gave it cannot match anything a browser sends.
        return JSONResponse(
            status_code=403,
            content={
                "detail": (
                    f"{OPERATOR_ORIGIN_ENV} is not an origin of the form "
                    "scheme://host[:port]; every state-changing request is "
                    "refused until it is fixed"
                )
            },
        )
    if not _origin_allowed(origin, headers):
        return JSONResponse(
            status_code=403,
            content={"detail": "Origin is missing or does not match the operator origin"},
        )
    return None


def _http_origin_denial(method: str, path: str, headers: Headers) -> JSONResponse | None:
    """The guard's decision for one HTTP request, exemptions included."""
    if method not in _GUARDED_METHODS:
        return None
    # Only ever exempts the exact tablet registration POST; every other
    # write — including a ``PUT`` aimed at the same path — is guarded.
    if method == "POST" and path in _ORIGIN_EXEMPT_POST_PATHS:
        return None
    return _origin_denial(headers)


@app.middleware("http")
async def operator_origin_guard(request: Request, call_next):
    """Refuse a state-changing request whose ``Origin`` does not match.

    Deliberately an ordinary HTTP middleware and nothing more exotic: an HTTP
    middleware only ever sees ``scope["type"] == "http"`` (``BaseHTTPMiddleware``
    hands every other scope straight through), so WebSocket handshakes are not
    routed, wrapped, or re-implemented here — ``/ws/controller`` guards itself
    inside its own endpoint, before it accepts. No ASGI wrapper around the
    router, no body sniffing, no dependency on how the app is mounted.

    The denial is returned *before* ``call_next``, so a refused request never
    reaches a route: no commit, no database write, no broadcast, no validation
    — and a 403 can never be confused with a route's own 404/405/422, nor can
    a hostile request learn anything about the wall it asked to change.
    """
    denial = _http_origin_denial(request.method, request.url.path, request.headers)
    if denial is not None:
        return denial
    return await call_next(request)


@app.get("/operator-config")
async def operator_config():
    """``{"tablet_origin": <origin or null>}`` — where the tablet page lives.

    The controller page reads this once at boot to show the address a tablet
    should open: in a two-origin deployment that address is not its own
    origin, and the server is the only party that knows the right one.

    ``TABLET_WALL_TABLET_ORIGIN`` unset (or empty) means "not configured" and
    answers ``null``, which is the caller's cue to fall back to the
    single-origin dev default. A value that is set but is not exactly
    ``scheme://host[:port]`` answers ``500`` instead: loud is the point.
    Silently answering ``null`` would read as "not configured" and push the
    caller to guess an origin — a wrong URL in a two-origin deployment is
    worse than no URL — and handing the value back unvalidated would pass a
    malformed origin straight through to whoever is reading.

    This is a plain read: the Origin guard above fences writes, not reads, so
    *who* may see the answer is decided at the proxy — the operator listener
    authenticates it, the tablet listener denies it (deploy/smoke.sh pins
    both). There is no authentication here to lean on.
    """
    state, origin = _origin_env_state(TABLET_ORIGIN_ENV)
    if state == _ORIGIN_UNSET:
        return {"tablet_origin": None}
    if state == _ORIGIN_INVALID:
        return JSONResponse(
            status_code=500,
            content={
                "detail": (
                    f"{TABLET_ORIGIN_ENV} is not an origin of the form "
                    "scheme://host[:port]"
                )
            },
        )
    return {"tablet_origin": origin}


async def _deny_websocket(websocket: WebSocket, response: JSONResponse) -> None:
    """Refuse the handshake itself, with a real HTTP status.

    ``send_denial_response`` answers the upgrade request with ``response``
    (403) instead of upgrading, so the client sees a *denied handshake* —
    never a socket that opens and immediately drops, which would look to a
    controller like an ordinary disconnect. A server that does not implement
    the ASGI ``websocket.http.response`` extension cannot carry a body;
    closing before accept is the spec's fallback, and conforming servers
    (uvicorn included) answer it with HTTP 403 anyway — either way the
    handshake fails, which is the requirement.

    Cosmetic caveat: uvicorn's ``websockets-sansio`` implementation logs
    "ASGI callable returned without completing handshake" after an
    extension-based denial, because an initial HTTP response does not set its
    internal handshake-complete flag. The 403 is still written and no 500 is
    substituted (the protocol guards 500s once a response is recorded).
    """
    try:
        await websocket.send_denial_response(response)
    except RuntimeError:
        await websocket.close()


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
    content = update.content
    if content.type == "image":
        # The directory is re-scanned here, so a file copied in after the
        # last read is usable immediately, and the intrinsic dimensions come
        # from the file this scan just validated — never from the caller. The
        # scan reads and hashes every candidate, so it runs in a worker
        # thread: heartbeats and broadcasts must not wait behind it.
        asset = await asyncio.to_thread(assets.find, content.asset)
        if asset is None:
            # Well-formed ID, no such asset: an invalid *body*, so 422 and
            # nothing is committed (PROTOCOL.md "PUT /scene").
            raise HTTPException(status_code=422, detail="Unknown asset")
        # Persisted: ID, fit, and the derived dimensions. Deliberately no URL
        # — it is composed from the ID on the way out, so it can never go
        # stale in the database (PROTOCOL.md "Still images").
        scene_content: dict[str, Any] = {
            "type": "image",
            "asset": asset.id,
            "fit": content.fit,
            "intrinsicWidth": asset.width,
            "intrinsicHeight": asset.height,
        }
    else:
        scene_content = {"type": content.type}

    def apply(target: dict[str, Any]) -> None:
        target["scene"]["content"] = scene_content

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


def _rects_overlap(first: dict[str, Any], second: dict[str, Any]) -> bool:
    """True when two placement-shaped rects share a **positive** area.

    Axis-aligned intersection with strict inequalities, so two rects that only
    meet along an edge (or at a corner) do not count as overlapping: the auto
    grid tiles its cells exactly and neighbouring cells are *meant* to share
    one. Footprint is all that matters here, so ``bezel`` — which only shrinks
    the visible area *inside* the rect — plays no part.
    """
    return (
        first["x"] < second["x"] + second["w"]
        and second["x"] < first["x"] + first["w"]
        and first["y"] < second["y"] + second["h"]
        and second["y"] < first["y"] + first["h"]
    )


@app.post("/wall/auto")
async def wall_auto(command: WallAutoCommand | None = None):
    """Place every online device in a regular grid covering the wall.

    Offline devices keep whatever placement they had, and reservations whose
    device is absent from the roster entirely are left alone too: releasing a
    vacant slot is an explicit, separate action (PROTOCOL.md
    ``POST /wall/auto``). With no ``columns`` the default is
    ``max(1, round(sqrt(n)))`` where n is the number of online devices; cell
    edges are rounded so the grid tiles the wall in whole units.

    Keeping those reservations is not the same as ignoring them: a grid that
    would cover one is refused with ``409`` instead of silently overlaying
    saved space. The check runs synchronously on the freshly built assignment,
    before the commit boundary, so a rejected request changes neither memory,
    nor the database, nor the revision, nor anything a socket is told — and
    nothing is released or moved on the operator's behalf. They can then
    release or move the conflicting reservations explicitly and retry.
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

    # Too many columns/rows for the logical wall can round a cell down to
    # zero. Such a placement is invalid (and has no positive area to test
    # against reservations), so reject the whole assignment before conflict
    # checks or persistence rather than saving a wall that cannot be recalled.
    if any(cell["w"] <= 0 or cell["h"] <= 0 for cell in assigned.values()):
        raise HTTPException(
            status_code=422,
            detail="Auto-arrange grid is too fine for the wall dimensions",
        )

    # Reservations are every placement this run does *not* own: an offline
    # tablet, or one the roster has forgotten entirely. They are saved space a
    # tablet is expected to come back to, so the proposed cells may not cover
    # them. Online placements are in ``assigned`` and therefore never counted
    # here — they are what the grid replaces.
    conflicts = sorted(
        device_id
        for device_id, placement in wall["layout"]["placements"].items()
        if device_id not in assigned
        and any(_rects_overlap(cell, placement) for cell in assigned.values())
    )
    if conflicts:
        # Raised before ``_commit_wall`` with no await in between, so the wall,
        # the row, the revision and the subscribers are all untouched.
        raise HTTPException(
            status_code=409,
            detail=(
                "Auto-arrange would overlap the reserved placement(s) of "
                + ", ".join(conflicts)
                + ". Nothing was changed: release them with "
                "DELETE /devices/{device_id}/placement or move them clear of "
                "the grid, then arrange again."
            ),
        )

    def apply(target: dict[str, Any]) -> None:
        # Only the online devices are assigned; everything else in the
        # placements map — offline devices and vacant reservations alike —
        # survives untouched.
        target["layout"]["placements"].update(assigned)

    _commit_wall(apply)
    await _broadcast_wall()
    return _wall_state()


# ---------------------------------------------------------------------------
# Named save/recall (saved layouts and scenes)
# ---------------------------------------------------------------------------


@app.get("/layouts")
async def get_saved_layouts():
    """Every saved layout: ``{"layouts": [{"name", "layout"}, …]}``, name-sorted.

    The payload is exactly the active layout object — width, height, and the
    placements map with their ``device_id`` — because that is what a recall
    puts back. Wrapped in an object rather than a bare array so the payload
    can grow metadata later without breaking readers.
    """
    entries = []
    for name, layout in load_layouts():
        valid = _valid_saved_layout(layout)
        entry = {"name": name, "layout": layout if valid else None}
        if not valid:
            entry["invalid"] = True
        entries.append(entry)
    return {"layouts": entries}


@app.put("/layouts/{name}")
async def put_saved_layout(name: str, replace: bool = Query(default=False)):
    """Save the active layout under ``name`` — there is deliberately no body.

    The snapshot is written straight to its own table: the live wall is not
    touched, so saving never bumps the revision and never broadcasts. ``422``
    for a malformed name, ``409`` when the name is already taken unless
    ``?replace=true`` asks for the overwrite explicitly.
    """
    canonical = _snapshot_name(name)
    if not save_layout(canonical, deepcopy(wall["layout"]), replace=replace):
        raise HTTPException(status_code=409, detail="Layout name already exists")
    return {"saved": True, "name": canonical}


@app.post("/layouts/{name}/recall")
async def recall_saved_layout(name: str):
    """Put a saved arrangement back on the wall; the scene is untouched.

    ``200`` with the full wall state, ``404`` when the name was never saved.
    This is a wall change like any other, so it runs through the commit
    boundary — persisted first, applied second, broadcast last — and bumps
    the revision (PROTOCOL.md "Revision and generation").
    """
    canonical = _snapshot_name(name)
    try:
        saved = load_layout(canonical)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=409, detail="Saved layout is invalid; active wall unchanged") from None
    if saved is None:
        raise HTTPException(status_code=404, detail="Unknown layout")
    if not _valid_saved_layout(saved):
        raise HTTPException(status_code=409, detail="Saved layout is invalid; active wall unchanged")

    def apply(target: dict[str, Any]) -> None:
        layout = target["layout"]
        # Dimensions and *every* placement come back exactly as they were
        # saved (PROTOCOL.md "Named snapshots"), while the scene is left
        # alone — content is the other recall's business. Reservations are
        # part of the saved map like anything else and are never filtered out
        # for belonging to a tablet the roster has forgotten: after a restart
        # every tablet is absent until it re-registers, and those slots are
        # the whole point of persisting placements (PROTOCOL.md "DELETE
        # /devices/{device_id}/placement").
        layout["width"] = saved["width"]
        layout["height"] = saved["height"]
        layout["placements"] = deepcopy(saved["placements"])

    _commit_wall(apply)
    await _broadcast_wall()
    return _wall_state()


@app.delete("/layouts/{name}")
async def delete_saved_layout(name: str):
    """Drop a saved layout: ``200`` ``{"deleted": true, "name"}``, else ``404``.

    The wall is not involved, so deleting a snapshot changes no revision and
    broadcasts nothing.
    """
    canonical = _snapshot_name(name)
    if not delete_layout(canonical):
        raise HTTPException(status_code=404, detail="Unknown layout")
    return {"deleted": True, "name": canonical}


@app.get("/scenes")
async def get_saved_scenes():
    """Every saved scene: ``{"scenes": [{"name", "content"}, …]}``, name-sorted.

    Stored content only, never the projected descriptor: the asset URL is
    composed on the way out of ``GET /wall`` and the frames, so it can never
    be listed (or stored) here.
    """
    entries = []
    for name, content in load_scenes():
        valid = _valid_saved_content(content)
        entry = {"name": name, "content": content if valid else None}
        if not valid:
            entry["invalid"] = True
        entries.append(entry)
    return {"scenes": entries}


@app.put("/scenes/{name}")
async def put_saved_scene(name: str, replace: bool = Query(default=False)):
    """Save the active scene's *content* under ``name`` — no request body.

    Layouts and scenes are saved independently, so recalling one can never
    smuggle the other in. The live content never carries a projected URL, and
    the copy stored here drops one anyway so a URL cannot reach the database
    even by accident (PROTOCOL.md "Still images": "The server composes the
    URL; it is not persisted"). Status codes mirror the layout save: ``422``
    for a malformed name, ``409`` when taken unless ``?replace=true``.
    """
    canonical = _snapshot_name(name)
    content = deepcopy(wall["scene"]["content"])
    content.pop("url", None)
    if not save_scene(canonical, content, replace=replace):
        raise HTTPException(status_code=409, detail="Scene name already exists")
    return {"saved": True, "name": canonical}


@app.post("/scenes/{name}/recall")
async def recall_saved_scene(name: str):
    """Apply a saved scene's content to the layout that is active right now.

    PROTOCOL.md "Recall semantics": content only — the arrangement is never
    replaced, so placement work done after the save survives a content
    recall. There is deliberately no inventory check either: the stored
    reference goes in verbatim, so a scene whose image file has since
    disappeared stays the explicit broken scene it already is rather than
    failing the recall (``PUT /scene`` is where an unknown asset is a 422).
    """
    canonical = _snapshot_name(name)
    try:
        saved = load_scene(canonical)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=409, detail="Saved scene is invalid; active wall unchanged") from None
    if saved is None:
        raise HTTPException(status_code=404, detail="Unknown scene")
    if not _valid_saved_content(saved):
        raise HTTPException(status_code=409, detail="Saved scene is invalid; active wall unchanged")

    def apply(target: dict[str, Any]) -> None:
        target["scene"]["content"] = deepcopy(saved)

    _commit_wall(apply)
    await _broadcast_wall()
    return _wall_state()


@app.delete("/scenes/{name}")
async def delete_saved_scene(name: str):
    """Drop a saved scene: ``200`` ``{"deleted": true, "name"}``, else ``404``.

    Deleting a snapshot never touches the active scene — the wall keeps
    showing whatever it was showing — so no revision moves and nothing is
    broadcast.
    """
    canonical = _snapshot_name(name)
    if not delete_scene(canonical):
        raise HTTPException(status_code=404, detail="Unknown scene")
    return {"deleted": True, "name": canonical}


@app.get("/")
async def root():
    return {
        "message": "Hello Tablet Wall"
    }


# ---------------------------------------------------------------------------
# Still images (PROTOCOL.md "Still images")
# ---------------------------------------------------------------------------


@app.get("/assets")
def get_assets():
    """The curated inventory: ``{"assets": [<entry>, …]}`` with each entry
    carrying ID, display name, MIME type, intrinsic dimensions, byte size,
    and the same-origin URL the asset is served from.

    Wrapped in an object rather than a bare array so the payload can grow
    metadata later without breaking readers. ``Cache-Control: no-store`` is
    part of the contract: the inventory is a snapshot of a directory that
    changes by files being copied in, so a browser must re-read it on every
    refresh instead of answering from a cached copy.

    Sync rather than async on purpose: this re-scans, re-hashes, and now
    fully decodes every file in the directory, and Starlette runs a plain
    ``def`` route in a worker thread, so the event loop — which is also
    pushing heartbeats — never waits on the filesystem. The re-scan itself is
    the contract: inventory refreshes on request.
    """
    return JSONResponse(
        content={"assets": assets.list_assets()},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/assets/{asset_id}")
def get_asset(asset_id: str):
    """Serve one asset's bytes, and only when they still hash to that ID.

    Unknown, malformed, removed, and replaced IDs are all ``404``: because
    the ID *is* the hash of the validated bytes, re-hashing what was just
    read proves this response is exactly the bytes that passed validation, so
    no stale copy can be served under an old ID (PROTOCOL.md "Still images").
    The bytes are content-addressed, hence cached as immutable; ``nosniff``
    keeps a browser from second-guessing the declared image type.
    """
    served = assets.fetch(asset_id)
    if served is None:
        raise HTTPException(status_code=404, detail="Unknown asset")
    asset, data = served
    return Response(
        content=data,
        media_type=asset.mime,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )


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
    # Checked on the handshake, BEFORE accept: a controller whose Origin is
    # missing or not the configured operator origin is never upgraded, never
    # enters ``controller_sockets``, and never receives a snapshot — there is
    # no frame, and no state, for a rejected caller to observe. The socket
    # endpoint is deliberately not guarded (a tablet is reached on the tablet
    # origin); this one is the operator's, so it carries the same fence as a
    # state-changing POST.
    denial = _origin_denial(websocket.headers)
    if denial is not None:
        await _deny_websocket(websocket, denial)
        return

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
