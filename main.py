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
import hashlib
import ipaddress
import json
import os
import re
import shutil
import time
import uuid
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
    MAX_DEVICE_DIMENSION,
    MAX_DEVICE_TYPE_LENGTH,
    MAX_DEVICES,
    SERVER_CAPS,
    SERVER_CAPS_V3,
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
from tabletwall import assets, clock, displays, geometry, media, media_serve, media_video, playback
from tabletwall import persist
from tabletwall import writer as writers
from tabletwall.media_limits import (
    FREE_RESERVE_BYTES,
    MAX_SOURCE_BYTES,
    MAX_VIDEO_BYTES,
    MAX_WAITING_UPLOADS,
    PIPELINE_VERSION,
    QUOTA_BYTES,
    VIDEO_RECEIVE_TIMEOUT_S,
)
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
    _ensure_device_number,
    _fresh_wall,
    _is_online,
    _new_generation,
    _touch_device,
    _viewport_matches,
    _wall_state,
    controller_protocols,
    controller_sockets,
    device_sockets,
    devices,
    wall,
)

_sweeper_task: asyncio.Task[Any] | None = None

# One decoder at a time, with at most two requests waiting (R1). Created in
# the lifespan so each app start gets a primitive bound to its own loop.
_upload_semaphore: asyncio.Semaphore | None = None
_upload_waiting = 0

# R3 process-local clock and playback session. A restart creates a new epoch
# and no session; the static wall content remains.
_server_clock: clock.ServerClock | None = None
_playback_session: playback.Session | None = None
_playback_task: asyncio.Task | None = None
_last_sample_broadcast_ms = 0.0


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
    global _sweeper_task, _upload_semaphore, _server_clock, _playback_task
    # Before the first yield: no socket may be accepted against state that
    # has not been loaded from the database.
    _restore_wall_state()
    # Startup scan (PROTOCOL.md "Still images"): inventory the curated image
    # directory before the first request, so a directory that exists but
    # cannot be read fails loudly at boot rather than on the first inventory
    # read. Every later read path re-scans anyway — this pass only establishes
    # the initial inventory (an absent directory is an empty one).
    assets.refresh()
    # Managed media (R1): create the store layout before the first upload and
    # remove only stale staging directories left by an interrupted job.
    media.ensure_dirs()
    media.cleanup_staging()
    _upload_semaphore = asyncio.Semaphore(1)
    _server_clock = clock.ServerClock()
    _sweeper_task = asyncio.create_task(_sweep_loop())
    _playback_task = asyncio.create_task(_playback_loop())
    try:
        yield
    finally:
        task = _sweeper_task
        _sweeper_task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        playback_task = _playback_task
        if playback_task is not None:
            playback_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await playback_task


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------


WAKE_LOCK_STATES = frozenset({"held", "released", "unsupported", "insecure", "denied"})


def _wake_lock_value(value: Any) -> str | None:
    """``value`` when it is one of the five reported states, else ``None``."""
    return value if isinstance(value, str) and value in WAKE_LOCK_STATES else None


class DeviceRegistration(BaseModel):
    """``POST /devices/register`` body — the one public write.

    Every field is bounded here, before the record can enter memory. The
    viewport numbers are a reporter's claim about its CSS size, not a
    credential, so they only need to be plausible: a non-positive or absurdly
    large value is a malformed registration, not a wall-size command.
    """

    device_id: UUID4
    width: int = Field(gt=0, le=MAX_DEVICE_DIMENSION)
    height: int = Field(gt=0, le=MAX_DEVICE_DIMENSION)
    device_type: str = Field(min_length=1, max_length=MAX_DEVICE_TYPE_LENGTH)
    # A returning tablet may ask for the display number it had before the
    # server restarted. The server honours it only while it is free.
    number: int | None = Field(default=None, ge=1, le=MAX_DEVICES)
    # Diagnostic only (R5): a value outside WAKE_LOCK_STATES is dropped rather
    # than rejected, so a bad report can never keep a tablet off the wall.
    wake_lock: Any = None

    @field_validator("device_type")
    @classmethod
    def printable_label(cls, value: str) -> str:
        # The label is rendered as text by the controller and carried in every
        # roster frame: control characters would break layouts and logs, and
        # there is no reason a device type needs them.
        if any(not 0x20 <= ord(ch) <= 0x7E for ch in value):
            raise ValueError("device_type must be printable ASCII")
        return value


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


class RevalidatedStaticFiles(StaticFiles):
    """Static files that browsers must revalidate on every load.

    Without a ``Cache-Control`` header a browser may reuse ``client.js`` and
    ``client.css`` for hours (heuristic freshness from ``Last-Modified``) while
    still re-fetching ``index.html``, so a tablet runs a new page against an
    old script. ``no-cache`` keeps the ETag: an unchanged file is a cheap 304.
    """

    def file_response(self, *args: Any, **kwargs: Any):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount(
    "/client",
    RevalidatedStaticFiles(directory="frontend/client", html=True),
    name="client"
)

app.mount(
    "/controller",
    RevalidatedStaticFiles(directory="frontend/controller", html=True),
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

    if existing is None and len(devices) >= MAX_DEVICES:
        # The roster is memory-only, so a full one is a process that has met a
        # lot of endpoints. Old tablets get replaced; keeping a dead record
        # forever would block the replacement. Evict the least recently
        # contacted *offline* record — never a live socket, never a placement
        # (placements are persisted separately and survive as reservations).
        offline = [
            (record.get("last_seen_mono", 0.0), key)
            for key, record in devices.items()
            if key not in device_sockets
        ]
        if not offline:
            raise HTTPException(
                status_code=429,
                detail="Device roster is full and every device is online",
            )
        evicted = min(offline)[1]
        devices.pop(evicted, None)
        # The controller may still render the evicted tile; removal is the
        # event that tells it to drop it. Its placement is left in the wall as
        # a reservation, so a later re-registration reclaims the same cell.
        await _broadcast({"type": "device_removed", "device_id": evicted})

    # The record is complete before anything is awaited; re-registering keeps
    # the assigned colour, any open socket, and the protocol negotiated by that
    # socket (the client re-registers before every connection attempt, so the
    # record would otherwise flap back to "no protocol" while still online).
    record: dict[str, Any] = {
        "device_id": device_id,
        "width": device.width,
        "height": device.height,
        "type": device.device_type,
        "color": existing["color"] if existing is not None else None,
        "protocol": existing.get("protocol") if existing is not None else None,
        "caps": list(existing.get("caps") or []) if existing is not None else [],
        "number": existing.get("number") if existing is not None else None,
        "last_seen": _now_iso(),
    }
    if existing is not None:
        # Re-registration keeps the live socket's ephemeral facts: a resize
        # re-registers while the same socket stays connected, and dropping
        # the viewport would silently invalidate a physical plan.
        for key in ("viewport", "connection_id", "clock", "clock_ok",
                    "clock_samples", "clock_pending", "render_seq", "wake_lock"):
            if key in existing:
                record[key] = existing[key]
    wake_lock = _wake_lock_value(device.wake_lock)
    if wake_lock is not None:
        record["wake_lock"] = wake_lock
    devices[device_id] = record
    # Stamp the monotonic contact reading too; presence expiry uses it.
    _touch_device(device_id)
    released = _ensure_device_number(device_id, device.number)
    for old_id in released:
        if old_id in devices:
            await _broadcast({"type": "device_updated", "device": _device_record(old_id)})
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
    _require_logical_wall()
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


class RebindCommand(BaseModel):
    """``POST /devices/{device_id}/rebind`` body.

    ``replaces`` is the id the wall remembers (a placement, slot or roster
    record). ``number`` is only needed when the server restarted too: numbers
    live in the roster, so the operator supplies the label on the glass.
    """

    replaces: UUID4
    number: int | None = Field(default=None, ge=1, le=MAX_DEVICES)


@app.post("/devices/{device_id}/rebind")
async def rebind_device(device_id: str, command: RebindCommand):
    """Move a lost identity's placement/slot, display records and number.

    A tablet that changed origin (http to https, new host) lost its
    localStorage and registered as a new device. The operator points that new
    registration at the id the wall still remembers. The old id must be
    offline: this is a hand-over, never a way to take a live tablet's place.
    Saved layouts keep naming the old id; recall one and save it again.
    """
    new_id = _parse_device_id(device_id)
    if new_id is None or new_id not in devices:
        raise HTTPException(status_code=404, detail="Unknown device")
    old_id = str(command.replaces)
    if old_id == new_id:
        raise HTTPException(status_code=422, detail="replaces must be a different device")
    if _is_online(old_id):
        raise HTTPException(status_code=409, detail="The replaced device is online")

    layout = wall["layout"]
    physical = layout.get("kind") == "physical"
    held = layout["slots"] if physical else layout["placements"]
    if old_id not in devices and old_id not in held:
        raise HTTPException(status_code=404, detail="Unknown device to replace")
    if new_id in held:
        raise HTTPException(status_code=409, detail="The new device is already placed")

    old_record = devices.get(old_id)
    number = command.number
    if number is None and old_record is not None:
        number = old_record.get("number")
    if number is not None and any(
        other.get("number") == number
        for key, other in devices.items()
        if key not in (old_id, new_id)
    ):
        raise HTTPException(status_code=409, detail="That display number is in use")

    try:
        copied = displays.copy_records(old_id, new_id)
    except displays.DisplayError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    moved = old_id in held
    if moved:
        def apply(target: dict[str, Any]) -> None:
            bucket = target["layout"]["slots" if physical else "placements"]
            entry = bucket.pop(old_id)
            if not physical:
                entry["device_id"] = new_id
            bucket[new_id] = entry

        _commit_wall(apply)

    record = devices[new_id]
    renumbered = number is not None and record.get("number") != number
    if number is not None:
        record["number"] = number
    devices.pop(old_id, None)
    stale_socket = device_sockets.pop(old_id, None)
    live_socket = device_sockets.get(new_id)

    if stale_socket is not None:
        with contextlib.suppress(Exception):
            await stale_socket.close(code=WS_CLOSE_NORMAL)
    if old_record is not None:
        await _broadcast({"type": "device_removed", "device_id": old_id})
    await _broadcast({"type": "device_updated", "device": _device_record(new_id)})
    if moved:
        await _broadcast_wall()
    if renumbered and live_socket is not None:
        # A tablet learns its number only from `welcome`; a normal close makes
        # it reconnect (4409 would park it on the takeover screen).
        with contextlib.suppress(Exception):
            await live_socket.close(code=WS_CLOSE_NORMAL)

    return {
        "rebound": True,
        "device_id": new_id,
        "replaces": old_id,
        "number": record.get("number"),
        "placed": moved,
        "display_records": copied,
    }


@app.get("/devices")
async def get_devices():
    return {device_id: _device_record(device_id) for device_id in list(devices)}


# ---------------------------------------------------------------------------
# Wall HTTP API (PROTOCOL.md "Version 2 — HTTP")
# ---------------------------------------------------------------------------


@app.get("/wall")
async def get_wall():
    _require_logical_wall()
    return _wall_state()


@app.put("/wall")
async def put_wall(update: WallUpdate):
    _require_logical_wall()
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
        # Managed uploads are indexed, so check them first; only an unknown
        # managed ID falls back to the curated scan. Intrinsic dimensions come
        # from the published record or the file this scan just validated —
        # never from the caller.
        managed = await asyncio.to_thread(media.find_object, content.asset)
        if managed is not None:
            asset_id, width, height = managed["id"], managed["width"], managed["height"]
        else:
            asset = await asyncio.to_thread(assets.find, content.asset)
            if asset is None:
                # Well-formed ID, no such asset: an invalid *body*, so 422 and
                # nothing is committed (PROTOCOL.md "PUT /scene").
                raise HTTPException(status_code=422, detail="Unknown asset")
            asset_id, width, height = asset.id, asset.width, asset.height
        # Persisted: ID, fit, and the derived dimensions. Deliberately no URL
        # — it is composed from the ID on the way out, so it can never go
        # stale in the database (PROTOCOL.md "Still images").
        scene_content: dict[str, Any] = {
            "type": "image",
            "asset": asset_id,
            "fit": content.fit,
            "intrinsicWidth": width,
            "intrinsicHeight": height,
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
    _require_logical_wall()
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
    _require_logical_wall()
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
    _require_logical_wall()
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
    _require_logical_wall()
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
    _require_logical_wall()
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
    _require_logical_wall()
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


@app.api_route("/assets/{asset_id}", methods=["GET", "HEAD"])
def get_asset(asset_id: str, request: Request):
    """Serve one asset's bytes, and only when they still hash to that ID.

    Managed uploads are checked first through the indexed media store, so a
    ready upload avoids re-scanning the curated directory entirely. Curated
    bytes remain the fallback. Unknown, malformed, removed, and replaced IDs
    are all ``404``: because the ID *is* the hash of the validated bytes,
    re-hashing what was just read proves this response is exactly those bytes.
    The bytes are content-addressed, hence cached as immutable; ``nosniff``
    keeps a browser from second-guessing the declared image type.

    A published video is the one object that is not buffered: it is streamed
    with byte ranges and a strong ETag (``tabletwall.media_serve``), after its
    hash has been checked once for the file's identity.
    """
    if _is_asset_id(asset_id):
        file = media.open_video(asset_id)
        if file is not None:
            return media_serve.video_response(request, file)
    managed = media.fetch_object(asset_id)
    if managed is not None:
        data, mime = managed
    else:
        served = assets.fetch(asset_id)
        if served is None:
            raise HTTPException(status_code=404, detail="Unknown asset")
        asset, data = served
        mime = asset.mime
    return Response(
        content=data,
        media_type=mime,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )


# ---------------------------------------------------------------------------
# managed uploads (R1)
# ---------------------------------------------------------------------------


def _store_error(error: media.StoreError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        content={"detail": error.message},
        headers={"Cache-Control": "no-store"},
    )


@asynccontextmanager
async def _upload_slot():
    """One active decoder and at most two waiting requests.

    The counter is decremented before the active holder yields the slot, so it
    counts waiters only. A third waiter is refused rather than queued without
    bound. The semaphore itself is created per app start in the lifespan.
    """
    global _upload_waiting
    semaphore = _upload_semaphore
    if semaphore is None:
        raise HTTPException(status_code=503, detail="upload service is not ready")
    if _upload_waiting >= MAX_WAITING_UPLOADS:
        raise HTTPException(status_code=429, detail="too many uploads are waiting")
    _upload_waiting += 1
    acquired = False
    try:
        await semaphore.acquire()
        acquired = True
        yield
    finally:
        _upload_waiting -= 1
        if acquired:
            semaphore.release()


def _require_logical_wall() -> None:
    """Fence legacy layout mutations while a physical layout is active."""
    if wall["layout"].get("kind") == "physical":
        raise HTTPException(
            status_code=409,
            detail="Upgrade controller: a physical layout is active",
        )


def _upload_display_name(raw: str | None) -> str:
    """A bounded display label, never a path and never control characters."""
    base = os.path.basename((raw or "").replace("\\", "/")).strip()
    base = "".join(ch for ch in base if 0x20 <= ord(ch) <= 0x7E)
    return base[:120] or "upload"


@app.post("/uploads")
async def upload_image(
    request: Request, name: str | None = Query(default=None, max_length=255)
):
    """Stream one JPEG, PNG, or H.264 MP4/MOV into the managed store and publish it.

    The response is the finished state: R1 has one decoder and a bounded
    request, so a durable job API would add a second state machine without
    changing what the controller can show. Progress during transmission is
    the browser's upload progress; after that the controller shows an
    indeterminate "processing" state until this response arrives. A video
    takes the same admission, the same single decoder slot and the same
    quota, with its own size cap, receive deadline and bounded worker.
    """
    try:
        media.admit_upload(request)
    except media.StoreError as error:
        return _store_error(error)

    content_type = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    is_video = content_type in ("video/mp4", "video/quicktime")
    if not is_video and content_type not in ("image/jpeg", "image/png"):
        return JSONResponse(
            status_code=415,
            content={"detail": "only image/jpeg, image/png, video/mp4 or video/quicktime is accepted"},
            headers={"Cache-Control": "no-store"},
        )
    if is_video and not media_video.tools_available():
        return JSONResponse(
            status_code=503,
            content={"detail": "ffmpeg and ffprobe are not installed; video uploads are unavailable"},
            headers={"Cache-Control": "no-store"},
        )
    limit = MAX_VIDEO_BYTES if is_video else MAX_SOURCE_BYTES
    noun = "video" if is_video else "image"

    raw_length = request.headers.get("content-length")
    declared: int | None = None
    if raw_length is not None:
        if not raw_length.isdigit():
            return JSONResponse(status_code=400, content={"detail": "invalid Content-Length"})
        declared = int(raw_length)
        if declared > limit:
            return JSONResponse(
                status_code=413,
                content={"detail": f"{noun} is larger than the {limit // (1024 * 1024)} MiB source limit"},
            )

    try:
        async with _upload_slot():
            job = media.new_job()
            try:
                incoming = declared if declared is not None else limit
                if is_video:
                    # The source and its remuxed copy share staging until publication.
                    media.check_capacity(2 * incoming)
                    received = await media.receive_body(
                        job, request.stream(), declared, limit=MAX_VIDEO_BYTES,
                        deadline_s=VIDEO_RECEIVE_TIMEOUT_S, noun="video",
                    )
                    media.check_capacity(received)
                    result = await media.run_video_worker(job)
                    publish = media.publish_video
                else:
                    media.check_capacity(incoming)
                    await media.receive_body(job, request.stream(), declared)
                    media.check_capacity(0)
                    result = await media.run_worker(job)
                    publish = media.publish
                descriptor = await asyncio.to_thread(
                    publish, job, result, _upload_display_name(name)
                )
            except BaseException:
                # ``receive_body`` and ``run_worker`` already remove failed
                # jobs; this also covers cancellation between them.
                shutil.rmtree(job.directory, ignore_errors=True)
                raise
    except media.StoreError as error:
        return _store_error(error)
    except HTTPException:
        raise
    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={"detail": f"upload failed ({type(error).__name__})"},
            headers={"Cache-Control": "no-store"},
        )
    if not descriptor:
        return JSONResponse(status_code=500, content={"detail": "upload did not publish"})
    return JSONResponse(
        status_code=201,
        content={"state": "ready", "asset": descriptor},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/media")
def get_media(request: Request):
    """The operator's managed-image library, newest first."""
    try:
        media.admit_library(request)
    except media.StoreError as error:
        return _store_error(error)
    return JSONResponse(
        content={"assets": media.list_assets(), "pipeline_version": PIPELINE_VERSION},
        headers={"Cache-Control": "no-store"},
    )


@app.post("/media/verify")
def verify_media(request: Request):
    """Re-hash every ready object and report mismatches; never mutates."""
    try:
        media.admit_upload(request)
    except media.StoreError as error:
        return _store_error(error)
    problems = media.verify_integrity()
    return JSONResponse(
        content={"ok": not problems, "problems": problems},
        headers={"Cache-Control": "no-store"},
    )


# ---------------------------------------------------------------------------
# diagnostics (R5)
# ---------------------------------------------------------------------------

BACKUP_DIR_ENV = "TABLET_WALL_BACKUP_DIR"


def _last_backup_at() -> str | None:
    """Newest ``created_utc`` among manifests under ``TABLET_WALL_BACKUP_DIR``.

    Read-only and best effort: the directory may itself be a snapshot or hold
    snapshots one level down. Unset, unreadable and oversized all answer
    ``None``; this server never writes backups.
    """
    root = os.environ.get(BACKUP_DIR_ENV)
    if not root:
        return None
    paths = [os.path.join(root, "manifest.json")]
    try:
        with os.scandir(root) as entries:
            paths += [
                os.path.join(entry.path, "manifest.json")
                for entry in entries
                if entry.is_dir(follow_symlinks=False)
            ]
    except OSError:
        pass
    newest: str | None = None
    for path in paths:
        try:
            if os.lstat(path).st_size > 16 * 1024 * 1024:
                continue
            with open(path, encoding="utf-8") as handle:
                created = json.load(handle).get("created_utc")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(created, str) and len(created) <= 40 and (newest is None or created > newest):
            newest = created
    return newest


def _media_diagnostics() -> dict[str, Any]:
    """Quota and store counts; ``orphans`` are object files no row lists."""
    media.ensure_dirs()
    with persist._connection() as connection:
        listed = {str(row[0]) for row in connection.execute("SELECT path FROM media_objects")}
        assets_ready = connection.execute(
            "SELECT COUNT(*) FROM media_assets WHERE state = 'ready'"
        ).fetchone()[0]
    root = media.media_dir()
    orphans = 0
    for directory, _dirs, names in os.walk(media.objects_dir()):
        for name in names:
            relative = os.path.relpath(os.path.join(directory, name), root)
            if relative.replace(os.sep, "/") not in listed:
                orphans += 1
    return {
        "quota_bytes": QUOTA_BYTES,
        "used_bytes": media._tree_bytes(root),
        "free_bytes": shutil.disk_usage(root).free,
        "reserve_bytes": FREE_RESERVE_BYTES,
        "objects": len(listed),
        "assets": assets_ready,
        "orphans": orphans,
    }


@app.get("/diagnostics")
def get_diagnostics(request: Request, verify: bool = Query(default=False)):
    """Operator-only storage and health readout.

    Admitted exactly like the managed library (``media.admit_library``), so
    it is unreachable on the tablet listener and fails closed while uploads
    are disabled. Cheap by default; ``?verify=1`` additionally re-hashes every
    ready object (``media.verify_integrity``) and reports objects whose bytes
    are missing or no longer match their ID under ``media.integrity``.
    """
    try:
        media.admit_library(request)
    except media.StoreError as error:
        return _store_error(error)
    store = _media_diagnostics()
    if verify:
        problems = media.verify_integrity()
        store["integrity"] = {"ok": not problems, "problems": problems}
    try:
        db_bytes = os.path.getsize(persist.db_path())
    except OSError:
        db_bytes = None
    roster = list(devices)
    wake_lock = {state: 0 for state in sorted(WAKE_LOCK_STATES)}
    for device_id in roster:
        state = devices[device_id].get("wake_lock")
        if state in wake_lock:
            wake_lock[state] += 1
    return JSONResponse(
        content={
            "media": store,
            "db": {"schema": persist.schema_version(), "bytes": db_bytes},
            "backup": {"last_manifest_at": _last_backup_at()},
            "clients": {
                "online": sum(1 for device_id in roster if _is_online(device_id)),
                "total": len(roster),
                "wake_lock": wake_lock,
            },
        },
        headers={"Cache-Control": "no-store"},
    )


# ---------------------------------------------------------------------------
# version 3 configuration (R2)
# ---------------------------------------------------------------------------


class ProfileCommand(BaseModel):
    active_width_mm: float
    active_height_mm: float
    bezels: dict[str, float]
    panel_pixels: dict[str, int] | None = None
    label: str = Field(min_length=1, max_length=80)
    provenance: str = Field(min_length=1, max_length=40)


class CalibrationCommand(BaseModel):
    profile_revision: int = Field(gt=0)
    viewport_width: float = Field(gt=0)
    viewport_height: float = Field(gt=0)
    dpr: float = Field(gt=0)
    orientation: int
    mode: str
    quarter_turn: int
    panel_offset_mm: list[float] = Field(min_length=2, max_length=2)
    mm_per_css: list[float] = Field(min_length=2, max_length=2)
    anchor_edge: str
    uncertainty_mm: float = 0
    method: str = Field(min_length=1, max_length=80)


class PhysicalLayoutCommand(BaseModel):
    bounds: dict[str, float]
    slots: dict[str, dict[str, Any]]


def _config_payload() -> dict[str, Any]:
    layout = wall["layout"]
    if layout.get("kind") == "physical":
        layout_state: dict[str, Any] = {
            "kind": "physical", "bounds": layout["bounds"], "slots": layout["slots"],
        }
    else:
        layout_state = {
            "kind": "logical", "width": layout["width"], "height": layout["height"],
            "placements": layout["placements"],
        }
    return {
        "schema": 2,
        "revision": wall["revision"],
        "generation": wall["generation"],
        "layout": layout_state,
        "displays": displays.list_profiles(),
        "calibrations": displays.list_calibrations(),
    }


def _config_etag(payload: dict[str, Any] | None = None) -> str:
    payload = payload if payload is not None else _config_payload()
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:32]


def _require_config_etag(request: Request) -> None:
    supplied = request.headers.get("if-match")
    if not supplied:
        raise HTTPException(status_code=428, detail="If-Match is required")
    if supplied.strip().strip('"') != _config_etag():
        raise HTTPException(status_code=412, detail="configuration changed; reload")


@app.get("/api/v3/config")
async def get_config_v3():
    payload = _config_payload()
    etag = _config_etag(payload)
    return JSONResponse(
        content={**payload, "etag": etag},
        headers={"ETag": etag, "Cache-Control": "no-store"},
    )


@app.put("/api/v3/displays/{device_id}")
async def put_display_v3(device_id: str, command: ProfileCommand, request: Request):
    _require_config_etag(request)
    try:
        profile = displays.save_profile(
            device_id,
            active_width_mm=command.active_width_mm,
            active_height_mm=command.active_height_mm,
            bezels=command.bezels,
            panel_pixels=command.panel_pixels,
            label=command.label,
            provenance=command.provenance,
        )
    except displays.DisplayError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"display": profile, "etag": _config_etag()}


@app.put("/api/v3/calibrations/{device_id}")
async def put_calibration_v3(
    device_id: str, command: CalibrationCommand, request: Request
):
    _require_config_etag(request)
    try:
        saved = displays.save_calibration(
            device_id,
            profile_revision=command.profile_revision,
            viewport_width=command.viewport_width,
            viewport_height=command.viewport_height,
            dpr=command.dpr,
            orientation=command.orientation,
            mode=command.mode,
            quarter_turn=command.quarter_turn,
            panel_offset_mm=(command.panel_offset_mm[0], command.panel_offset_mm[1]),
            mm_per_css=(command.mm_per_css[0], command.mm_per_css[1]),
            anchor_edge=command.anchor_edge,
            uncertainty_mm=command.uncertainty_mm,
            method=command.method,
        )
    except displays.DisplayError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"calibration": saved, "etag": _config_etag()}


@app.put("/api/v3/layout")
async def put_physical_layout_v3(command: PhysicalLayoutCommand, request: Request):
    """Atomically replace the active arrangement with a physical one."""
    _require_config_etag(request)
    bounds = command.bounds
    for field in ("x", "y", "width", "height"):
        if not isinstance(bounds.get(field), (int, float)):
            raise HTTPException(status_code=422, detail=f"bounds.{field} is required")
    if bounds["width"] <= 0 or bounds["height"] <= 0:
        raise HTTPException(status_code=422, detail="bounds must be positive")
    for device_id, slot in command.slots.items():
        if _parse_device_id(device_id) is None:
            raise HTTPException(status_code=422, detail="slot device_id must be a UUID4")
        for field in ("center_x_mm", "center_y_mm", "mount_angle",
                      "nudge_x_mm", "nudge_y_mm"):
            if not isinstance(slot.get(field), (int, float)):
                raise HTTPException(status_code=422, detail=f"slot {field} is required")
        profile_revision = slot.get("profile_revision")
        calibration_revision = slot.get("calibration_revision")
        if displays.profile(device_id, profile_revision) is None:
            raise HTTPException(status_code=422, detail="slot profile does not exist")
        calibration = displays.calibration(device_id, calibration_revision)
        if calibration is None or calibration["profile_revision"] != profile_revision:
            raise HTTPException(
                status_code=422,
                detail="slot calibration does not exist for its profile",
            )
        if not isinstance(slot.get("participating", True), bool):
            raise HTTPException(status_code=422, detail="slot participating is a boolean")

    def apply(target: dict[str, Any]) -> None:
        target["layout"] = {
            "kind": "physical",
            "bounds": {
                "x": float(bounds["x"]), "y": float(bounds["y"]),
                "width": float(bounds["width"]), "height": float(bounds["height"]),
            },
            "slots": deepcopy(command.slots),
        }

    _commit_wall(apply)
    # A cached logical controller cannot represent a physical wall: close it
    # with the upgrade code instead of letting it issue fenced writes.
    for socket in list(controller_sockets):
        if controller_protocols.get(socket, 1) != 3:
            controller_sockets.discard(socket)
            controller_protocols.pop(socket, None)
            with contextlib.suppress(Exception):
                await socket.close(code=WS_CLOSE_UNSUPPORTED_PROTOCOL)
    await _broadcast_wall()
    payload = _config_payload()
    return {**payload, "etag": _config_etag(payload)}


@app.get("/api/v3/layouts")
async def list_physical_layouts_v3():
    entries = [
        {"name": name, "layout": layout}
        for name, layout in load_layouts()
        if isinstance(layout, dict) and layout.get("kind") == "physical"
    ]
    return {"layouts": entries}


@app.put("/api/v3/layouts/{name}")
async def save_physical_layout_v3(
    name: str, request: Request, replace: bool = Query(default=False)
):
    _require_config_etag(request)
    if wall["layout"].get("kind") != "physical":
        raise HTTPException(status_code=409, detail="the active layout is logical")
    canonical = _snapshot_name(name)
    if not save_layout(canonical, deepcopy(wall["layout"]), replace=replace):
        raise HTTPException(status_code=409, detail="Layout name already exists")
    return {"saved": True, "name": canonical}


@app.post("/api/v3/layouts/{name}/recall")
async def recall_physical_layout_v3(name: str, request: Request):
    _require_config_etag(request)
    canonical = _snapshot_name(name)
    saved = load_layout(canonical)
    if saved is None:
        raise HTTPException(status_code=404, detail="Unknown layout")
    if not isinstance(saved, dict) or saved.get("kind") != "physical":
        raise HTTPException(status_code=422, detail="not a physical layout")

    def apply(target: dict[str, Any]) -> None:
        target["layout"] = deepcopy(saved)

    _commit_wall(apply)
    for socket in list(controller_sockets):
        if controller_protocols.get(socket, 1) != 3:
            controller_sockets.discard(socket)
            controller_protocols.pop(socket, None)
            with contextlib.suppress(Exception):
                await socket.close(code=WS_CLOSE_UNSUPPORTED_PROTOCOL)
    await _broadcast_wall()
    payload = _config_payload()
    return {**payload, "etag": _config_etag(payload)}


@app.delete("/api/v3/layouts/{name}")
async def delete_physical_layout_v3(name: str, request: Request):
    _require_config_etag(request)
    canonical = _snapshot_name(name)
    if not delete_layout(canonical):
        raise HTTPException(status_code=404, detail="Unknown layout")
    return {"deleted": True, "name": canonical}


# ---------------------------------------------------------------------------
# R3 clock, preparation and hard-cut playback
# ---------------------------------------------------------------------------


def _now_ms() -> float:
    return _server_clock.now_ms() if _server_clock is not None else time.monotonic_ns() / 1e6


async def _send_to(websocket: WebSocket, frame: dict[str, Any], stamp: Any = None) -> None:
    connection = writers.get(websocket)
    if connection is not None:
        await connection.send(frame, stamp=stamp)
    else:
        await websocket.send_json(frame)


def _asset_descriptor(asset_id: str) -> dict[str, Any] | None:
    video = media.video_descriptor(asset_id)
    if video is not None:
        return video
    managed = media.find_object(asset_id)
    if managed is not None:
        return {
            "id": managed["id"], "name": "playlist", "mime": managed["mime"],
            "intrinsicWidth": managed["width"], "intrinsicHeight": managed["height"],
            "bytes": managed["bytes"], "url": f"/assets/{managed['id']}",
        }
    curated = assets.find(asset_id)
    return curated.entry() if curated is not None else None


def _physical_plan_for(
    device_id: str, record: dict[str, Any], source_width: int, source_height: int
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    layout = wall["layout"]
    if layout.get("kind") != "physical":
        return None, None
    slot = layout["slots"].get(device_id)
    if slot is None:
        return None, None
    profile = displays.profile(device_id, int(slot["profile_revision"]))
    calibration = displays.calibration(device_id, int(slot["calibration_revision"]))
    if (
        profile is None
        or calibration is None
        or calibration["profile_revision"] != slot["profile_revision"]
        or not _viewport_matches(calibration, record.get("viewport") or {})
    ):
        return None, None
    bounds = layout["bounds"]
    plan = geometry.normalized_source_to_panel(
        active_size=(profile["active_width_mm"], profile["active_height_mm"]),
        bezels=profile["bezels"],
        center_mm=(slot["center_x_mm"], slot["center_y_mm"]),
        nudge_mm=(slot["nudge_x_mm"], slot["nudge_y_mm"]),
        mount_angle=slot["mount_angle"],
        bounds=(bounds["x"], bounds["y"], bounds["width"], bounds["height"]),
        source_size=(source_width, source_height),
        fit="cover",
    )
    return (
        {**plan, "source": {"width": source_width, "height": source_height}},
        {
            "status": "valid", "revision": calibration["revision"],
            "viewport_width": calibration["viewport_width"],
            "viewport_height": calibration["viewport_height"],
            "quarter_turn": calibration["quarter_turn"],
            "panel_offset_mm": calibration["panel_offset_mm"],
            "mm_per_css": calibration["mm_per_css"],
            "panel_width": profile["active_width_mm"],
            "panel_height": profile["active_height_mm"],
        },
    )


def _video_durations(items: Any) -> dict[str, int]:
    """Duration in ms of every ready video among raw playlist ``items``."""
    durations: dict[str, int] = {}
    for item in items if isinstance(items, list) else []:
        asset = item.get("asset") if isinstance(item, dict) else None
        if isinstance(asset, str) and asset not in durations:
            duration = media.video_duration_ms(asset)
            if duration is not None:
                durations[asset] = duration
    return durations


def _playback_status() -> dict[str, Any]:
    session = _playback_session
    if session is None:
        return {"state": "stopped"}
    now = _now_ms()
    playback.refresh_display(session, now)
    return {
        "now_ms": now,
        "session_id": session.id,
        "version": session.version,
        "generation": session.generation,
        "clock_epoch": session.clock_epoch,
        "state": session.state,
        "current": session.current.as_dict() if session.current else None,
        "displayed": session.displayed.as_dict() if session.displayed else None,
        "current_effective_ms": session.current_effective_ms,
        "pending": session.pending.as_frame() if session.pending else None,
        "cohort": session.cohort,
        "missed": session.missed,
        "held": session.held,
        "hold_deadline_ms": session.hold_deadline_ms,
        "policy": session.policy,
        "blocked_reason": session.blocked_reason,
        "final": session.final,
        "paused_at_ms": session.paused_at_ms,
        "video": playback.video_status(session, _now_ms()),
        "members": {
            device_id: {
                "ready": bool(
                    lease.ready
                    and lease.clock_ok
                    and lease.lease_expires_ms > now
                    and lease.lease_expires_ms >= max(now, session.pending.effective_ms)
                ),
                "video": lease.video,
            }
            for device_id, lease in (session.pending.leases.items() if session.pending else [])
        },
    }


async def _broadcast_playback() -> None:
    frame = {"type": "playback_status", **_playback_status()}
    for socket, protocol in list(controller_protocols.items()):
        if protocol != 3:
            continue
        try:
            await _send_to(socket, frame)
        except Exception:
            controller_sockets.discard(socket)
            controller_protocols.pop(socket, None)


async def _send_prepare(
    session: playback.Session, pending: playback.Preparation, device_id: str
) -> bool:
    record = devices.get(device_id)
    socket = device_sockets.get(device_id)
    if record is None or socket is None:
        return False
    descriptor = _asset_descriptor(pending.asset)
    if descriptor is None:
        return False
    plan, calibration = _physical_plan_for(
        device_id, record, descriptor["intrinsicWidth"], descriptor["intrinsicHeight"]
    )
    if plan is None or calibration is None:
        return False
    lease = pending.leases.get(device_id)
    connection_id = record.get("connection_id", "")
    if lease is not None:
        lease.connection_id = connection_id
        lease.mapping_revision = int(calibration["revision"])
        lease.ready = False
        lease.evidence_seq = 0
        lease.lease_expires_ms = 0
        lease.clock_ok = False
    frame = {
        "type": "prepare", **session.lineage(),
        "preparation_id": pending.id,
        "occurrence": pending.occurrence.as_dict(),
        "asset": descriptor,
        "plan": plan,
        "calibration": calibration,
        "prepare_deadline_ms": pending.deadline_ms,
        "effective_server_ms": pending.effective_ms,
        "connection_id": connection_id,
        "cohort": session.cohort,
    }
    if pending.media is not None:
        frame["media"] = pending.media
    await _send_to(socket, frame)
    return True


async def _prepare_playback(session: playback.Session) -> None:
    pending = session.pending
    if pending is None:
        return
    for device_id in session.cohort:
        await _send_prepare(session, pending, device_id)


async def _send_commit(session: playback.Session, action: dict[str, Any]) -> None:
    descriptor = _asset_descriptor(action["asset"])
    for device_id in action["devices"]:
        record = devices.get(device_id)
        socket = device_sockets.get(device_id)
        if record is None or socket is None:
            continue
        frame = {
            "type": "commit", **session.lineage(),
            "version": action["version"],
            "prepared_at_version": action["prepared_at_version"],
            "preparation_id": action["preparation_id"],
            "occurrence": action["occurrence"],
            "asset": descriptor,
            "effective_server_ms": action["effective_server_ms"],
            "connection_id": record.get("connection_id", ""),
            "missed": action.get("missed", []),
        }
        if "start_media_ms" in action:
            frame["start_media_ms"] = action["start_media_ms"]
        await _send_to(socket, frame)


async def _abort_playback(reason: str) -> None:
    global _playback_session
    session = _playback_session
    if session is None:
        return
    playback.stop(session, _now_ms())
    for device_id in session.cohort:
        socket = device_sockets.get(device_id)
        record = devices.get(device_id)
        if socket is None:
            continue
        with contextlib.suppress(Exception):
            await _send_to(socket, {
                "type": "playback", "state": "stopped", "reason": reason,
                "epoch": _server_clock.epoch if _server_clock else None,
            })
        if record is not None:
            with contextlib.suppress(Exception):
                await _send_wall_to_device(device_id, socket, record)
    _playback_session = None
    await _broadcast_playback()


async def _playback_loop() -> None:
    while True:
        await asyncio.sleep(0.1)
        try:
            if _server_clock is not None and _server_clock.check_suspend():
                await _abort_playback("host suspend")
            session = _playback_session
            if session is None:
                continue
            _revoke_missing_leases(session)
            actions = playback.tick(session, _now_ms())
            for action in actions:
                if action["type"] == "commit":
                    await _send_commit(session, action)
                    await _prepare_playback(session)
                if action["type"] in ("commit", "hold", "failed", "blocked", "reanchor"):
                    await _broadcast_playback()
        except asyncio.CancelledError:
            raise
        except Exception:
            continue


class PlaylistCommand(BaseModel):
    items: list[dict[str, Any]]
    loop: bool = False


def _playlist_etag(document: dict[str, Any] | None) -> str:
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:32]


@app.get("/api/v3/playlist")
async def get_playlist_v3():
    document = persist.load_meta("playlist")
    return {"playlist": document, "etag": _playlist_etag(document)}


@app.put("/api/v3/playlist")
async def put_playlist_v3(command: PlaylistCommand, request: Request):
    try:
        videos = _video_durations(command.items)
        items = playback.validate_playlist(command.items, loop=command.loop, videos=videos)
    except playback.PlaybackError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    for item in items:
        if _asset_descriptor(item["asset"]) is None:
            raise HTTPException(status_code=422, detail="playlist asset is unknown")
    document = {"items": items, "loop": command.loop, "revision": 1}
    supplied = request.headers.get("if-match")
    current = persist.load_meta("playlist")
    if not supplied:
        raise HTTPException(status_code=428, detail="If-Match is required")
    if supplied.strip().strip('"') != _playlist_etag(current):
        raise HTTPException(status_code=412, detail="playlist changed; reload")
    persist.save_meta("playlist", document)
    return {"playlist": document, "etag": _playlist_etag(document)}


def _require_session_version(request: Request) -> playback.Session:
    session = _playback_session
    if session is None:
        raise HTTPException(status_code=404, detail="no playback session")
    supplied = request.headers.get("if-match")
    if not supplied:
        raise HTTPException(status_code=428, detail="If-Match is required")
    if supplied.strip().strip('"') != str(session.version):
        raise HTTPException(status_code=412, detail="playback version is stale")
    return session


@app.get("/api/v3/playback")
async def get_playback_v3():
    return _playback_status()


class PlaybackStartCommand(BaseModel):
    policy: str | None = None


def _playback_connections(cohort: list[str]) -> dict[str, str]:
    return {
        device_id: devices[device_id].get("connection_id", "")
        for device_id in cohort
        if device_id in devices and _is_online(device_id)
    }


@app.post("/api/v3/playback/start")
async def start_playback_v3(command: PlaybackStartCommand | None = None):
    global _playback_session
    supplied = command is not None and "policy" in command.model_fields_set
    explicit = command.policy if supplied else None
    if supplied and explicit not in playback.POLICIES:
        raise HTTPException(status_code=422, detail='policy must be "online" or "strict"')
    document = persist.load_meta("playlist")
    if not isinstance(document, dict):
        raise HTTPException(status_code=409, detail="save a playlist first")
    layout = wall["layout"]
    if layout.get("kind") != "physical":
        raise HTTPException(status_code=409, detail="a physical layout is required")
    videos = _video_durations(document["items"])
    policy = explicit or ("strict" if videos else "online")
    required = sorted(
        device_id for device_id, slot in layout["slots"].items()
        if slot.get("participating", True) is not False
    )

    session = _playback_session
    if session is not None and session.state == "paused":
        playback.resume(session, _now_ms(), _playback_connections(session.cohort))
        await _prepare_playback(session)
        await _broadcast_playback()
        return _playback_status()
    if session is not None and session.state not in ("stopped", "failed"):
        raise HTTPException(status_code=409, detail="playback is already active")

    if policy == "strict":
        cohort = required
    else:
        cohort = [
            device_id for device_id in required
            if device_id in devices
            and devices[device_id].get("protocol") == 3
            and _is_online(device_id)
        ]
    if not cohort:
        raise HTTPException(status_code=409, detail="no eligible physical endpoints")
    connections = _playback_connections(cohort)
    _playback_session = playback.start(
        document["items"], bool(document.get("loop", False)), cohort, _now_ms(),
        generation=wall["generation"],
        clock_epoch=_server_clock.epoch if _server_clock else "",
        connections=connections,
        policy=policy,
        videos=videos,
    )
    await _prepare_playback(_playback_session)
    await _broadcast_playback()
    return _playback_status()


@app.post("/api/v3/playback/pause")
async def pause_playback_v3(request: Request):
    session = _require_session_version(request)
    playback.pause(session, _now_ms())
    for device_id in session.cohort:
        socket = device_sockets.get(device_id)
        if socket is not None:
            with contextlib.suppress(Exception):
                await _send_to(socket, {"type": "playback", "state": "paused",
                                        **session.lineage()})
    await _broadcast_playback()
    return _playback_status()


@app.post("/api/v3/playback/stop")
async def stop_playback_v3(request: Request):
    global _playback_session
    session = _require_session_version(request)
    playback.stop(session, _now_ms())
    for device_id in session.cohort:
        socket = device_sockets.get(device_id)
        record = devices.get(device_id)
        if socket is not None:
            with contextlib.suppress(Exception):
                await _send_to(socket, {"type": "playback", "state": "stopped",
                                        **session.lineage()})
            if record is not None:
                with contextlib.suppress(Exception):
                    await _send_wall_to_device(device_id, socket, record)
    _playback_session = None
    await _broadcast_playback()
    return {"state": "stopped"}


async def _step_playback(request: Request, delta: int) -> dict[str, Any]:
    session = _require_session_version(request)
    try:
        playback.step(
            session, delta, _now_ms(), _playback_connections(session.cohort)
        )
    except playback.PlaybackError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    for device_id in session.cohort:
        socket = device_sockets.get(device_id)
        if socket is not None:
            with contextlib.suppress(Exception):
                await _send_to(socket, {"type": "cancel", **session.lineage(),
                                        "reason": "superseded"})
    await _prepare_playback(session)
    await _broadcast_playback()
    return _playback_status()


@app.post("/api/v3/playback/retry")
async def retry_playback_v3(request: Request):
    session = _require_session_version(request)
    connections = {
        device_id: devices[device_id].get("connection_id", "")
        for device_id in session.cohort if device_id in devices
    }
    try:
        playback.retry(session, _now_ms(), connections)
    except playback.PlaybackError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    for device_id in session.cohort:
        socket = device_sockets.get(device_id)
        if socket is not None:
            with contextlib.suppress(Exception):
                await _send_to(socket, {"type": "cancel", **session.lineage(),
                                        "reason": "superseded"})
    await _prepare_playback(session)
    await _broadcast_playback()
    return _playback_status()


@app.post("/api/v3/playback/next")
async def next_playback_v3(request: Request):
    return await _step_playback(request, 1)


@app.post("/api/v3/playback/previous")
async def previous_playback_v3(request: Request):
    return await _step_playback(request, -1)


# ---------------------------------------------------------------------------
# WebSockets
# ---------------------------------------------------------------------------


def _revoke_missing_leases(session: playback.Session) -> None:
    """Revoke leases for cohort members with no live socket, before a tick."""
    for device_id in session.cohort:
        if device_id not in device_sockets:
            _revoke_playback_lease(device_id)


def _revoke_playback_lease(device_id: str, connection_id: str | None = None) -> None:
    """A closed or replaced socket can no longer answer for a preparation."""
    session = _playback_session
    if session is None or session.pending is None:
        return
    lease = session.pending.leases.get(device_id)
    if lease is None:
        return
    if connection_id is not None and lease.connection_id != connection_id:
        return
    lease.ready = False
    lease.evidence_seq = 0
    lease.lease_expires_ms = 0
    lease.clock_ok = False


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

        if isinstance(payload, dict) and payload.get("type") == "clock_sample":
            sample_id = payload.get("id")
            c0 = payload.get("c0")
            if (
                isinstance(sample_id, str)
                and isinstance(c0, (int, float))
                and not isinstance(c0, bool)
                and device_sockets.get(device_id) is websocket
                and device_id in devices
            ):
                pending = {"c0": float(c0), "s1": _now_ms(), "s2": None}
                exchanges = devices[device_id].setdefault("clock_pending", {})
                exchanges[sample_id] = pending
                while len(exchanges) > 16:
                    exchanges.pop(next(iter(exchanges)))
                frame = {
                    "type": "clock_sample", "id": sample_id,
                    "c0": pending["c0"], "s1": pending["s1"],
                }
                def stamp(target: dict[str, Any], state: dict[str, Any] = pending) -> None:
                    state["s2"] = _now_ms()
                    target["s2"] = state["s2"]
                connection = writers.get(websocket)
                if connection is not None:
                    await connection.send(frame, stamp=stamp)
        elif isinstance(payload, dict) and payload.get("type") == "clock_result":
            sample_id = payload.get("id")
            c3 = payload.get("c3")
            record = devices.get(device_id)
            if (
                record is not None
                and isinstance(sample_id, str)
                and isinstance(c3, (int, float))
                and not isinstance(c3, bool)
            ):
                pending = record.get("clock_pending", {}).pop(sample_id, None)
                if pending is not None and pending.get("s2") is not None:
                    estimate = clock.estimate(
                        pending["c0"], pending["s1"], pending["s2"], float(c3)
                    )
                    if estimate is not None:
                        samples = record.setdefault("clock_samples", [])
                        samples.append({
                            "server_ms": pending["s2"],
                            "offset_ms": estimate.offset_ms,
                            "rtt_ms": estimate.rtt_ms,
                            "uncertainty_ms": estimate.uncertainty_ms,
                        })
                        del samples[:-16]
                        best = clock.best_sample(samples, _now_ms())
                        record["clock"] = best
                        record["clock_ok"] = bool(
                            best is not None
                            and best["uncertainty_ms"] <= clock.MAX_UNCERTAINTY_MS
                        )
        elif isinstance(payload, dict) and payload.get("type") == "ready":
            session = _playback_session
            record = devices.get(device_id)
            if (
                session is not None
                and record is not None
                and device_sockets.get(device_id) is websocket
            ):
                best = clock.best_sample(record.get("clock_samples", []), _now_ms())
                clock_ok = bool(
                    best is not None
                    and best["uncertainty_ms"] <= clock.MAX_UNCERTAINTY_MS
                )
                pending = session.pending
                expected = (
                    pending.leases[device_id].mapping_revision
                    if pending is not None and device_id in pending.leases else None
                )
                try:
                    accepted = playback.accept_ready(
                        session,
                        device_id=device_id,
                        connection_id=record.get("connection_id", ""),
                        preparation_id=str(payload["preparation_id"]),
                        version=int(payload["version"]),
                        evidence_seq=int(payload.get("evidence_seq", 0)),
                        mapping_revision=int(payload.get("mapping_revision", 0)),
                        clock_ok=clock_ok,
                        lease_ms=2000,
                        now_ms=_now_ms(),
                        decoded=payload.get("decoded") is True,
                        occurrence=payload.get("occurrence"),
                        expected_mapping=expected,
                        video=payload.get("video"),
                    )
                except (KeyError, TypeError, ValueError):
                    accepted = False
                if accepted:
                    await _broadcast_playback()
        elif isinstance(payload, dict) and payload.get("type") == "video_sample":
            global _last_sample_broadcast_ms
            session = _playback_session
            if (
                session is not None
                and device_sockets.get(device_id) is websocket
                and playback.accept_sample(
                    session, device_id=device_id, payload=payload, now_ms=_now_ms()
                )
            ):
                if _now_ms() - _last_sample_broadcast_ms >= 1000:
                    _last_sample_broadcast_ms = _now_ms()
                    await _broadcast_playback()
        elif isinstance(payload, dict) and payload.get("type") == "heartbeat":
            # A replaced socket must not keep the new one alive.
            if device_sockets.get(device_id) is websocket and device_id in devices:
                _touch_device(device_id)
                wake_lock = _wake_lock_value(payload.get("wake_lock"))
                if wake_lock is not None and devices[device_id].get("wake_lock") != wake_lock:
                    devices[device_id]["wake_lock"] = wake_lock
                    await _broadcast(
                        {"type": "device_updated", "device": _device_record(device_id)}
                    )
        elif isinstance(payload, dict) and payload.get("type") == "viewport":
            viewport = payload.get("viewport")
            if (
                isinstance(viewport, dict)
                and device_sockets.get(device_id) is websocket
                and device_id in devices
            ):
                try:
                    devices[device_id]["viewport"] = {
                        "width": float(viewport["width"]),
                        "height": float(viewport["height"]),
                        "dpr": float(viewport["dpr"]),
                        "orientation": int(viewport["orientation"]),
                        "mode": str(viewport["mode"]),
                    }
                except (KeyError, TypeError, ValueError):
                    continue
                record = devices[device_id]
                if record.get("protocol") == 3:
                    await _send_wall_to_device(device_id, websocket, record)


@app.websocket("/ws/device")
async def ws_device(
    websocket: WebSocket,
    device_id: str | None = Query(default=None),
    protocol: str | None = Query(default=None),
    caps: str | None = Query(default=None, max_length=2048),
    w: str | None = Query(default=None, max_length=16),
    h: str | None = Query(default=None, max_length=16),
    dpr: str | None = Query(default=None, max_length=32),
    orientation: str | None = Query(default=None, max_length=8),
    mode: str | None = Query(default=None, max_length=16),
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
    _touch_device(key)
    released = _ensure_device_number(key)
    for old_id in released:
        if old_id in devices:
            await _broadcast({"type": "device_updated", "device": _device_record(old_id)})
    record["protocol"] = negotiated
    record["caps"] = _parse_caps(caps)
    record["connection_id"] = uuid.uuid4().hex
    if None not in (w, h, dpr, orientation, mode):
        try:
            record["viewport"] = {
                "width": float(w), "height": float(h), "dpr": float(dpr),
                "orientation": int(orientation), "mode": str(mode),
            }
        except (TypeError, ValueError):
            record.pop("viewport", None)

    if replaced is not None and replaced is not websocket:
        with contextlib.suppress(Exception):
            await replaced.close(code=WS_CLOSE_REPLACED)

    connection = writers.attach(websocket)
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
            welcome["number"] = record.get("number")
        elif negotiated == 3:
            welcome["protocol"] = 3
            welcome["server_caps"] = list(SERVER_CAPS_V3)
            welcome["number"] = record.get("number")
        await connection.send(welcome)
        if negotiated == 3 and _server_clock is not None:
            await connection.send({
                "type": "clock_bootstrap",
                "epoch": _server_clock.epoch,
                "server_ms": _now_ms(),
            })

        if negotiated in (2, 3):
            # Replay the wall or render plan right after welcome so a
            # reconnecting tablet restores the current state.
            await _send_wall_to_device(key, websocket, record)

        session = _playback_session
        if session is not None and key in session.cohort:
            pending = session.pending
            if pending is not None and key in pending.leases:
                lease = pending.leases[key]
                lease.connection_id = record.get("connection_id", "")
                lease.ready = False
                lease.evidence_seq = 0
                lease.lease_expires_ms = 0
                lease.clock_ok = False
            if pending is not None:
                await _send_prepare(session, pending, key)

        color = record.get("color")
        if color:
            await connection.send({"type": "set_color", "color": color})
        await _broadcast({"type": "device_online", "device": _device_record(key)})
        await _device_loop(websocket, key)
    except WebSocketDisconnect:
        pass
    finally:
        # Revoke before the first await: a playback tick queued on the loop
        # must not see a ready lease for a socket that has already gone.
        if device_sockets.get(key) is websocket:
            _revoke_playback_lease(key, record.get("connection_id"))
        await writers.detach(websocket)
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

    connection = writers.attach(websocket)
    try:
        # The snapshot is built and enqueued before the socket is published
        # to broadcasts, so it is guaranteed to be this controller's first
        # frame and no later wall update can overtake it.
        snapshot = [_device_record(device_id) for device_id in list(devices)]
        frame: dict[str, Any] = {"type": "snapshot", "devices": snapshot}
        if negotiated == 2:
            # Version-1 snapshots stay exactly as originally specified.
            frame["wall"] = _wall_state()
        elif negotiated == 3:
            payload = _config_payload()
            frame["config"] = {**payload, "etag": _config_etag(payload)}
        await connection.send(frame)
        controller_sockets.add(websocket)
        controller_protocols[websocket] = negotiated

        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
    except WebSocketDisconnect:
        return
    finally:
        await writers.detach(websocket)
        controller_sockets.discard(websocket)
        controller_protocols.pop(websocket, None)
