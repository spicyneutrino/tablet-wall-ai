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
import logging
import os
import re
import shutil
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict
from contextlib import asynccontextmanager
from copy import deepcopy
from math import isfinite, sqrt
from pathlib import Path
from typing import Literal, Any
from urllib.parse import urlsplit

from fastapi import (
    FastAPI,
    HTTPException,
    Query,
    Request,
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
from tabletwall import hub as hub
from tabletwall.auth import AuthMiddleware
from tabletwall import operability
from tabletwall.routes import calibration_check, health as health_routes
from tabletwall.security_headers import ConfiguredHostMiddleware, SecurityHeadersMiddleware
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
from tabletwall import assets, clock, displays, geometry, media, media_video, playback
from tabletwall import layouts, operator_images, persist, workers, tablet_models
from tabletwall import device_lifecycle, grid, operator_state, render_status, test_pattern
from tabletwall import sizing as wall_sizing
from tabletwall import writer as writers
from tabletwall.media_limits import (
    MAX_SOURCE_BYTES,
    MAX_VIDEO_BYTES,
    MAX_WAITING_UPLOADS,
    PIPELINE_VERSION,
    VIDEO_RECEIVE_TIMEOUT_S,
)
# Durable wall and roster metadata. Sockets and live presence stay in
# memory. The snapshot
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
    current_mapping,
    render_mapping,
    validated_viewport,
    identify_commands,
    device_changes,
    checkpoint_devices,
    checkpoint_loop,
    restore_devices,
    _ensure_device_number,
    _fresh_wall,
    _is_online,
    _new_generation,
    _project_scene,
    _touch_device,
    _viewport_matches,
    _wall_state,
    controller_protocols,
    controller_sockets,
    device_sockets,
    devices,
    wall,
)

from tabletwall.routes.assets import router as assets_router
from tabletwall.routes.devices import router as devices_router
from tabletwall.routes.diagnostics import router as diagnostics_router

_sweeper_task: asyncio.Task[Any] | None = None
_roster_checkpoint_task: asyncio.Task[None] | None = None

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
    global _sweeper_task, _upload_semaphore, _server_clock, _playback_task, _roster_checkpoint_task
    with workers.single_worker():
        # Before the first yield: no socket may be accepted against state that
        # has not been loaded from the database.
        restore_devices()
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
        _roster_checkpoint_task = asyncio.create_task(checkpoint_loop())
        _playback_task = asyncio.create_task(_playback_loop())
        try:
            yield
        finally:
            for identify_task in list(_identify_tasks):
                identify_task.cancel()
            for identify_task in list(_identify_tasks):
                with contextlib.suppress(asyncio.CancelledError):
                    await identify_task
            _identify_tasks.clear()
            checkpoint_task = _roster_checkpoint_task
            _roster_checkpoint_task = None
            if checkpoint_task is not None:
                checkpoint_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await checkpoint_task
            checkpoint_devices()
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
    screen_width: int | None = Field(default=None, gt=0, le=MAX_DEVICE_DIMENSION)
    screen_height: int | None = Field(default=None, gt=0, le=MAX_DEVICE_DIMENSION)
    screen_dpr: float | None = Field(default=None, gt=0, le=10, allow_inf_nan=False)
    platform_family: Literal["ios", "android", "other"] | None = None

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
    sizing: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("width", "height")
    @classmethod
    def positive_dimension(cls, value: int | None) -> int | None:
        # Raises ValueError for a dimension that is not a positive int,
        # which FastAPI turns into a 422.
        if value is not None and value <= 0:
            raise ValueError("width and height must be positive integers")
        return value

    @field_validator("sizing")
    @classmethod
    def valid_sizing(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None:
            normalized = wall_sizing.validate_sizing(value, logical=True)
            if normalized is None:
                raise ValueError("sizing requires mode fixed/tablets and a non-negative whole-unit padding")
            return normalized
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
    background: str | None = None

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
        # centered ``cover`` and ``contain`` (PROTOCOL.md "Still images").
        if value is not None and value not in SUPPORTED_FITS:
            raise ValueError("only cover and contain fits are supported")
        return value

    @field_validator("background")
    @classmethod
    def supported_background(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("background must be #rrggbb")
        return value.lower()

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
        elif self.asset is not None or self.fit is not None or "background" in self.model_fields_set:
            raise ValueError(f"{self.type} content takes no asset, fit, or background")
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


class WallPackCommand(BaseModel):
    columns: int | None = Field(default=None, ge=1)
    gap: int = 0

    model_config = ConfigDict(extra="forbid")

    @field_validator("columns", "gap", mode="before")
    @classmethod
    def whole_number(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not float(value).is_integer():
            raise ValueError("columns and gap must be whole numbers")
        return int(value)

    @field_validator("gap")
    @classmethod
    def nonnegative_gap(cls, value: int) -> int:
        if value < 0:
            raise ValueError("gap must be non-negative")
        return value


# ---------------------------------------------------------------------------
# commit boundary (PROTOCOL.md "Persistence")
# ---------------------------------------------------------------------------


def _commit_wall(
    change: Callable[[dict[str, Any]], None], *, backup_layout_name: str | None = None
) -> None:
    """Persist a wall change, and only then let it into memory.

    ``change`` applies one logical mutation to a wall-state dict. It runs
    first on a detached copy, including derived tablet-fit bounds. Its row
    is written before that complete proposal replaces the live contents.
    The ``wall`` dict retains its identity for modules that hold it.

    The ordering is the whole point: if ``save_state`` raises, nothing has
    touched memory yet, so the live state, the database, and what subscribers
    have been told all still agree, the route fails loudly as a 5xx, and no
    broadcast follows (PROTOCOL.md "A commit happens before notification, so
    a controller is never told about state that would not survive a
    restart"). Layout and scene routes use this boundary; lifecycle routes use
    ``_commit_lifecycle`` to include roster and history writes in their commit.
    """
    proposed = deepcopy(wall)
    change(proposed)
    try:
        _fit_wall_layout(proposed["layout"])
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    proposed["revision"] += 1
    with persist.transaction():
        if backup_layout_name is not None:
            if not save_layout(backup_layout_name, wall["layout"]):
                raise HTTPException(status_code=409, detail="could not save the previous layout")
        save_state(proposed)

    # Reached only when the write committed.
    wall.clear()
    wall.update(proposed)


def _fit_wall_layout(layout: dict[str, Any]) -> None:
    if layout.get("kind") == "physical":
        wall_sizing.fit_physical(layout, displays.profile)
    else:
        wall_sizing.fit_logical(layout)


def _replace_layout(layout: dict[str, Any], *, allow_empty: bool = False) -> str | None:
    try:
        proposed = layouts.normalize(layout, profile_for=displays.profile,
                                     calibration_for=displays.calibration)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if layouts.entries(wall["layout"]) and not layouts.entries(proposed) and not allow_empty:
        raise HTTPException(status_code=409, detail="Empty layout would remove every tablet; use Clear wall explicitly")
    backup = None
    if layouts.kind(wall["layout"]) != layouts.kind(proposed):
        backup = "Before " + layouts.kind(proposed) + " " + uuid.uuid4().hex[:12]

    def apply(target: dict[str, Any]) -> None:
        target["layout"] = proposed

    _commit_wall(apply, backup_layout_name=backup)
    return backup


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
    if not isinstance(saved, dict) or set(saved) - {"width", "height", "placements", "sizing"} or not {"width", "height", "placements"}.issubset(saved):
        return False
    if "sizing" in saved and wall_sizing.validate_sizing(saved["sizing"], logical=True) is None:
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
    required = {"type", "asset", "intrinsicWidth", "intrinsicHeight"}
    if kind != "image" or not required <= set(saved) or set(saved) - required - {"fit", "background"}:
        return False
    return (
        isinstance(saved["asset"], str) and _is_asset_id(saved["asset"])
        and saved.get("fit", "cover") in SUPPORTED_FITS
        and ("background" not in saved or isinstance(saved["background"], str)
             and re.fullmatch(r"#[0-9a-f]{6}", saved["background"]) is not None)
        and type(saved["intrinsicWidth"]) is int and saved["intrinsicWidth"] > 0
        and type(saved["intrinsicHeight"]) is int and saved["intrinsicHeight"] > 0
    )


# ---------------------------------------------------------------------------
# app
# ---------------------------------------------------------------------------

app = FastAPI(lifespan=lifespan)


app.include_router(assets_router)


app.include_router(devices_router)
app.include_router(diagnostics_router)
app.include_router(health_routes.create_router())
app.include_router(calibration_check.create_router())


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
    RevalidatedStaticFiles(directory=Path(__file__).resolve().parent / "frontend/client", html=True),
    name="client"
)

app.mount(
    "/controller",
    RevalidatedStaticFiles(directory=Path(__file__).resolve().parent / "frontend/controller", html=True),
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
# authorization. An ``Origin`` header is trivially forged by anything that is
# not a browser, so this only constrains browsers. Optional shared-secret
# authentication lives in ``tabletwall.auth`` and remains independent of this
# guard. A reverse proxy can also authenticate the operator.
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
    if state == _ORIGIN_INVALID or origin is None:
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


def _deployment_hosts() -> set[str] | None:
    origins = [_origin_env_state(name) for name in (OPERATOR_ORIGIN_ENV, TABLET_ORIGIN_ENV)]
    if all(state == _ORIGIN_UNSET for state, _origin in origins):
        return None
    hosts = {"127.0.0.1", "localhost", "::1"}
    for _state, origin in origins:
        if origin is not None:
            host = urlsplit(origin).hostname
            if host is not None:
                hosts.add(host.lower().rstrip("."))
    return hosts


app.add_middleware(AuthMiddleware)
app.add_middleware(ConfiguredHostMiddleware, allowed_hosts=_deployment_hosts)
app.add_middleware(SecurityHeadersMiddleware)


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
    *who* may see the answer is decided by optional application authentication
    and the proxy. The operator listener authenticates it, and the tablet
    listener denies it (deploy/smoke.sh pins both).
    """
    state, origin = _origin_env_state(TABLET_ORIGIN_ENV)
    if state == _ORIGIN_UNSET:
        return {"tablet_origin": None}
    if state == _ORIGIN_INVALID or origin is None:
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








@app.post("/devices/register")
async def device_register(device: DeviceRegistration):
    device_id = str(device.device_id)
    existing = devices.get(device_id)

    with device_changes():
        evicted = None
        if existing is None and len(devices) >= MAX_DEVICES:
            # A full roster has met many endpoints. Old tablets get replaced; keeping a dead record
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
            "label": existing.get("label") if existing is not None else None,
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
        for key in ("screen_width", "screen_height", "screen_dpr", "platform_family"):
            value = getattr(device, key)
            if value is not None:
                record[key] = value
            elif existing is not None and key in existing:
                record[key] = existing[key]
        devices[device_id] = record
        current_assignment = tablet_models.assignments().get(device_id)
        if current_assignment is None and displays.latest_profile(device_id) is not None:
            current_assignment = tablet_models.assign(device_id, "manual")
        if current_assignment is None:
            tablet_models.assign(device_id, "auto")
        # Stamp the monotonic contact reading too; presence expiry uses it.
        _touch_device(device_id)
        released = _ensure_device_number(device_id, device.number)
    if evicted is not None:
        await _broadcast({"type": "device_removed", "device_id": evicted})
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

    with device_changes():
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
    with device_changes():
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
    result = await _forget_device(key, device_lifecycle.ForgetCommand(remove_active=True, saved_layouts="keep"))
    return {"removed": True, "device_id": key, **({"remaining_saved": result} if result else {})}


class RebindCommand(BaseModel):
    """``POST /devices/{device_id}/rebind`` body.

    ``replaces`` is the id the wall remembers in its placement, slot, or
    roster. ``number`` can recover a physical label absent from legacy
    metadata. Current metadata preserves numbers across a server restart.
    """

    replaces: UUID4
    number: int | None = Field(default=None, ge=1, le=MAX_DEVICES)


@app.post("/devices/{device_id}/rebind")
async def rebind_device(device_id: str, command: RebindCommand):
    key = _parse_device_id(device_id)
    if key is None:
        raise HTTPException(status_code=404, detail="Unknown device")
    command_v3 = device_lifecycle.RebindApply(
        replaces=str(command.replaces), hardware="same_hardware", active=True,
        saved_layouts=[], transfer_label=True, number=command.number,
        new_connection_id=devices.get(key, {}).get("connection_id") if key in device_sockets else None,
    )
    plan = await _apply_rebind(key, command_v3)
    return {"rebound": True, "device_id": key, "replaces": str(command.replaces),
            "number": plan.preview.number_after, "placed": plan.preview.affected_active,
            "display_records": {"profiles": len(plan.preview.profile_revision_map),
                                "calibrations": len(plan.preview.calibration_revision_map)},
            **({"remaining_saved": [asdict(item) for item in plan.preview.untouched_saved]}
               if plan.preview.untouched_saved else {})}


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
        current_sizing = wall_sizing.sizing_config(layout)
        next_sizing = update.sizing or current_sizing
        if next_sizing["mode"] == "tablets" and (update.width is not None or update.height is not None):
            raise HTTPException(status_code=409, detail="manual dimensions require fixed sizing mode")
        if update.width is not None:
            layout["width"] = update.width
        if update.height is not None:
            layout["height"] = update.height
        if update.sizing is not None:
            layout["sizing"] = deepcopy(update.sizing)

    _commit_wall(apply)
    await _broadcast_wall()
    return _wall_state()


@app.post("/wall/pack")
async def pack_wall(command: WallPackCommand):
    _require_logical_wall()
    layout = wall["layout"]
    if wall_sizing.sizing_config(layout)["mode"] != "tablets":
        raise HTTPException(status_code=409, detail="packing requires tablet sizing mode")
    if not layout["placements"]:
        raise HTTPException(status_code=422, detail="there are no placed tablets to pack")
    columns = command.columns or len(layout["placements"])

    def apply(target: dict[str, Any]) -> None:
        wall_sizing.pack_logical(target["layout"], columns, command.gap)

    _commit_wall(apply)
    await _broadcast_wall()
    return _wall_state()


@app.put("/scene")
async def put_scene(update: SceneUpdate):
    _require_logical_wall()
    # Content only: the layout is untouched, the revision bumps, the new
    # state is committed, and only then is it broadcast — same ordering as
    # ``PUT /wall`` above.
    scene_content = await _resolve_scene_content(update.content)

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
    # remove. Legacy snapshots and evictions can leave placements owned by
    # devices absent from the roster. Such a placement
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
    if wall_sizing.sizing_config(wall["layout"])["mode"] == "tablets":
        raise HTTPException(status_code=409, detail="Equal-cell tiling requires fixed sizing; use /wall/pack to preserve tablet sizes")
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
    await hub._broadcast_config_updated()
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
        if "sizing" in saved:
            layout["sizing"] = deepcopy(saved["sizing"])
        else:
            layout.pop("sizing", None)

    _commit_wall(apply)
    await _broadcast_wall()
    return _wall_state()


@app.delete("/layouts/{name}")
async def delete_saved_layout(name: str):
    """Drop a saved layout: ``200`` ``{"deleted": true, "name"}``, else ``404``.

    Deleting a snapshot changes no wall revision. V3 controllers refetch config.
    """
    _require_logical_wall()
    canonical = _snapshot_name(name)
    if not delete_layout(canonical):
        raise HTTPException(status_code=404, detail="Unknown layout")
    await hub._broadcast_config_updated()
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
    await hub._broadcast_config_updated()
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
    _require_logical_wall()
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
    showing whatever it was showing. V3 controllers refetch config.
    """
    canonical = _snapshot_name(name)
    if not delete_scene(canonical):
        raise HTTPException(status_code=404, detail="Unknown scene")
    await hub._broadcast_config_updated()
    return {"deleted": True, "name": canonical}





# ---------------------------------------------------------------------------
# Still images (PROTOCOL.md "Still images")
# ---------------------------------------------------------------------------





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
    viewport_guard: bool = False


class PhysicalLayoutCommand(BaseModel):
    bounds: dict[str, Any]
    slots: dict[str, dict[str, Any]]
    sizing: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("sizing")
    @classmethod
    def valid_sizing(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None:
            normalized = wall_sizing.validate_sizing(value)
            if normalized is None:
                raise ValueError("sizing requires mode fixed/tablets and finite non-negative padding")
            return normalized
        return value


class LogicalLayoutCommand(BaseModel):
    width: int = Field(gt=0, strict=True)
    height: int = Field(gt=0, strict=True)
    placements: dict[str, dict[str, Any]]
    sizing: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class ClearLayoutCommand(BaseModel):
    confirm: bool = Field(strict=True)

    model_config = ConfigDict(extra="forbid")


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
    if "sizing" in layout:
        layout_state["sizing"] = deepcopy(layout["sizing"])
    payload = {
        "schema": 2,
        "revision": wall["revision"],
        "generation": wall["generation"],
        "layout": layout_state,
        "scene": _project_scene(wall["scene"]),
        "displays": displays.list_profiles(),
        "calibrations": displays.list_calibrations(),
        "tablet_models": tablet_models.BUILTINS,
        "tablet_assignments": tablet_models.assignments(),
    }
    if layout.get("kind") == "physical":
        profiles = []
        calibrations = []
        for device_id, slot in layout["slots"].items():
            profile = displays.profile(device_id, slot["profile_revision"])
            calibration = displays.calibration(device_id, slot["calibration_revision"])
            if profile is not None:
                profiles.append(profile)
            if calibration is not None:
                calibrations.append(calibration)
        payload["referenced_displays"] = profiles
        payload["referenced_calibrations"] = calibrations
    if payload["scene"]["content"].get("type") == "image":
        payload["scene"]["content"].setdefault("fit", "cover")
        payload["scene"]["content"].setdefault("background", "#0b1120")
        payload["scene"]["content"]["available"] = operability.asset_available(
            payload["scene"]["content"]["asset"])
    payload["operator_state_version"] = 1
    payload["layout"].setdefault("sizing", {"mode": "fixed", "padding": 0})
    payload.setdefault("referenced_displays", [])
    payload.setdefault("referenced_calibrations", [])
    payload["device_labels"] = {key: record.get("label") for key, record in sorted(devices.items())}
    payload["snapshots"] = operator_state.snapshots(_valid_any_layout, _valid_saved_content)
    payload["capabilities"] = {"layout_kinds": ["logical", "physical"], "fits": ["cover", "contain"],
        "render_ack": True, "identify": True, "image_contain": True, "grid": True,
        "test_patterns": ["grid", "black"], "uploads": media.upload_mode() in ("loopback", "proxy"),
        "diagnostics": True,
        "login_supported": bool(os.environ.get("TABLET_WALL_AUTH_TOKEN"))}
    active = _presentation_active()
    payload["runtime"] = operator_state.runtime(presentation_active=active,
        presentation_state=_playback_session.state if active and _playback_session else "static")
    return payload


def _valid_any_layout(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        layouts.normalize(value, profile_for=displays.profile, calibration_for=displays.calibration)
        return True
    except (ValueError, TypeError, KeyError):
        return False


def _config_etag(payload: dict[str, Any] | None = None) -> str:
    payload = payload if payload is not None else _config_payload()
    return operator_state.durable_etag(payload)


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


@app.get("/api/v3/images")
def get_images_v3(request: Request):
    try:
        media.admit_operator_read(request)
    except media.StoreError as error:
        return _store_error(error)
    return JSONResponse(
        content={"images": operator_images.list_images()},
        headers={"Cache-Control": "no-store"},
    )


async def _resolve_scene_content(content: SceneContent) -> dict[str, Any]:
    if content.type != "image":
        return {"type": content.type}
    assert content.asset is not None
    managed = await asyncio.to_thread(media.find_object, content.asset)
    if managed is not None:
        asset_id, width, height = managed["id"], managed["width"], managed["height"]
    else:
        asset = await asyncio.to_thread(assets.find, content.asset)
        if asset is None:
            raise HTTPException(status_code=422, detail="Unknown asset")
        asset_id, width, height = asset.id, asset.width, asset.height
    return {
        "type": "image",
        "asset": asset_id,
        "fit": content.fit,
        **({"background": content.background} if content.background is not None else {}),
        "intrinsicWidth": width,
        "intrinsicHeight": height,
    }


@app.put("/api/v3/scene")
async def put_scene_v3(update: SceneUpdate, request: Request):
    _require_config_etag(request)
    scene_content = await _resolve_scene_content(update.content)
    # Resolution yields to other requests; fence the actual commit as well.
    _require_config_etag(request)

    def apply(target: dict[str, Any]) -> None:
        target["scene"]["content"] = scene_content

    _commit_wall(apply)
    await _abort_playback("static scene selected")
    await _broadcast_wall()
    return await get_config_v3()


class TabletAssignmentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["auto", "explicit", "manual"]
    model_id: str | None = None


@app.put("/api/v3/tablet-assignments/{device_id}")
async def put_tablet_assignment(device_id: UUID4, command: TabletAssignmentCommand, request: Request):
    _require_config_etag(request)
    key = str(device_id)
    model_id = command.model_id
    if command.mode == "auto":
        model_id = None
    try:
        with persist.transaction():
            assignment = tablet_models.assign(key, command.mode, model_id)
    except (ValueError, displays.DisplayError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    await _abort_playback("mapping changed")
    await _broadcast_wall()
    return {"assignment": assignment, "suggestions": tablet_models.match(devices.get(key, {})), "etag": _config_etag()}


@app.put("/api/v3/displays/{device_id}")
async def put_display_v3(device_id: str, command: ProfileCommand, request: Request):
    _require_config_etag(request)
    try:
        with persist.transaction():
            profile = displays.save_profile(
                device_id,
                active_width_mm=command.active_width_mm,
                active_height_mm=command.active_height_mm,
                bezels=command.bezels,
                panel_pixels=command.panel_pixels,
                label=command.label,
                provenance=command.provenance,
            )
            tablet_models.assign(device_id, "manual")
    except displays.DisplayError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    await _abort_playback("mapping changed")
    await _broadcast_wall()
    return {"display": profile, "etag": _config_etag()}


@app.put("/api/v3/calibrations/{device_id}")
async def put_calibration_v3(
    device_id: str, command: CalibrationCommand, request: Request
):
    _require_config_etag(request)
    if command.viewport_guard:
        record = devices.get(device_id)
        if record is None or not _is_online(device_id) or not _viewport_matches(
            command.model_dump(), record.get("viewport") or {}
        ):
            raise HTTPException(
                status_code=409,
                detail="Tablet is offline or its viewport changed. Capture its viewport again and repeat the ruler measurement.",
            )
    try:
        with persist.transaction():
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
            tablet_models.remember_calibration(device_id, saved)
            tablet_models.assign(device_id, "manual")
    except (displays.DisplayError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    await _abort_playback("mapping changed")
    await _broadcast_wall()
    return {"calibration": saved, "etag": _config_etag()}


async def _layout_response(previous_layout_saved: str | None) -> JSONResponse:
    await _abort_playback("layout changed")
    if wall["layout"].get("kind") == "physical":
        for socket in list(controller_sockets):
            if controller_protocols.get(socket, 1) != 3:
                controller_sockets.discard(socket)
                controller_protocols.pop(socket, None)
                with contextlib.suppress(Exception):
                    await socket.close(code=WS_CLOSE_UNSUPPORTED_PROTOCOL)
    await _broadcast_wall()
    payload = _config_payload()
    etag = _config_etag(payload)
    return JSONResponse(
        content={**payload, "etag": etag, "previous_layout_saved": previous_layout_saved},
        headers={"ETag": etag, "Cache-Control": "no-store"},
    )


@app.put("/api/v3/layout")
async def put_physical_layout_v3(command: PhysicalLayoutCommand, request: Request):
    _require_config_etag(request)
    layout = {"kind": "physical", "bounds": command.bounds, "slots": command.slots}
    if command.sizing is not None:
        layout["sizing"] = command.sizing
    elif wall["layout"].get("kind") == "physical" and "sizing" in wall["layout"]:
        layout["sizing"] = wall["layout"]["sizing"]
    previous = _replace_layout(layout)
    return await _layout_response(previous)


@app.put("/api/v3/logical-layout")
async def put_logical_layout_v3(command: LogicalLayoutCommand, request: Request):
    _require_config_etag(request)
    layout = command.model_dump(exclude_none=True)
    previous = _replace_layout(layout)
    return await _layout_response(previous)


@app.post("/api/v3/layout/clear")
async def clear_layout_v3(command: ClearLayoutCommand, request: Request):
    _require_config_etag(request)
    if not command.confirm:
        raise HTTPException(status_code=422, detail="Clear wall requires explicit confirmation")
    layout = deepcopy(wall["layout"])
    layout["slots" if layouts.kind(layout) == "physical" else "placements"] = {}
    previous = _replace_layout(layout, allow_empty=True)
    return await _layout_response(previous)


@app.get("/api/v3/logical-layouts")
async def list_logical_layouts_v3():
    return _snapshot_layout_listing("logical")


@app.post("/api/v3/logical-layouts/{name}/recall")
async def recall_logical_layout_v3(name: str, request: Request):
    _require_config_etag(request)
    try:
        saved = load_layout(_snapshot_name(name))
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="Saved layout is invalid") from None
    if saved is None:
        raise HTTPException(status_code=404, detail="Unknown logical layout")
    if not isinstance(saved, dict) or not _valid_saved_layout(saved):
        raise HTTPException(status_code=422, detail="Saved logical layout is invalid")
    previous = _replace_layout(saved, allow_empty=True)
    return await _layout_response(previous)


@app.get("/api/v3/layouts")
async def list_physical_layouts_v3():
    return _snapshot_layout_listing("physical")


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
    return await _snapshot_response(saved=True, name=canonical)


@app.post("/api/v3/layouts/{name}/recall")
async def recall_physical_layout_v3(name: str, request: Request):
    _require_config_etag(request)
    canonical = _snapshot_name(name)
    try:
        saved = load_layout(canonical)
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="Saved layout is invalid") from None
    if saved is None:
        raise HTTPException(status_code=404, detail="Unknown layout")
    if not isinstance(saved, dict) or saved.get("kind") != "physical":
        raise HTTPException(status_code=422, detail="not a physical layout")
    previous = _replace_layout(saved, allow_empty=True)
    return await _layout_response(previous)


@app.delete("/api/v3/layouts/{name}")
async def delete_physical_layout_v3(name: str, request: Request):
    _require_config_etag(request)
    canonical = _snapshot_name(name)
    if not delete_layout(canonical):
        raise HTTPException(status_code=404, detail="Unknown layout")
    return await _snapshot_response(deleted=True, name=canonical)


def _presentation_active() -> bool:
    return _playback_session is not None and _playback_session.state != "stopped"


def _lifecycle_inputs(new_id: str | None = None) -> device_lifecycle.LifecycleInputs:
    profiles, calibrations = displays.histories()
    digests = persist.snapshot_digests("layout")
    values = dict(base_etag=_config_etag(), roster=deepcopy(devices),
        active_layout=deepcopy(wall["layout"]),
        saved_layouts={name: device_lifecycle.SavedLayout(digests[name], value)
                       for name, value in load_layouts()},
        connections={key: devices[key]["connection_id"] for key in device_sockets if key in devices},
        profiles=profiles, calibrations=calibrations, assignments=tablet_models.assignments(),
        model_history=persist.load_meta("tablet_model_calibrations") or {})
    if new_id is not None:
        return device_lifecycle.RebindInputs(new_id=new_id, **values)
    return device_lifecycle.LifecycleInputs(**values)


def _lifecycle_error(error: device_lifecycle.LifecycleError) -> HTTPException:
    return HTTPException(status_code=error.status, detail=error.detail)


def _commit_lifecycle(roster: dict[str, Any], layout: dict[str, Any], *, active_changed: bool,
                      rebind: device_lifecycle.RebindPlan | None = None) -> None:
    proposed = deepcopy(wall)
    with persist.transaction():
        if rebind is not None:
            copied = rebind.measurements
            if copied is not None:
                displays.copy_records(rebind.delete_roster_id, rebind.preview.new_id,
                    revision_offsets=(copied.profile_offset, copied.calibration_offset))
                tablet_models.copy_assignment(rebind.delete_roster_id, rebind.preview.new_id,
                    copied.profile_offset, copied.calibration_offset)
            for name, saved in rebind.selected_snapshots.items():
                if not save_layout(name, saved, replace=True):
                    raise HTTPException(status_code=409, detail="snapshot replacement failed")
        if active_changed:
            proposed["layout"] = deepcopy(layout)
            _fit_wall_layout(proposed["layout"])
            proposed["revision"] += 1
            save_state(proposed)
        persist.save_devices(roster)
    devices.clear()
    devices.update(roster)
    if active_changed:
        wall.clear()
        wall.update(proposed)


async def _forget_device(key: str, command: device_lifecycle.ForgetCommand) -> list[dict[str, Any]]:
    try:
        plan = device_lifecycle.plan_forget(key, command, _lifecycle_inputs())
    except device_lifecycle.LifecycleError as error:
        raise _lifecycle_error(error) from error
    roster = deepcopy(devices)
    roster.pop(key, None)
    _commit_lifecycle(roster, plan.active_layout, active_changed=plan.active_changed)
    render_status.clear(key)
    identify_commands.pop(key, None)
    await _abort_playback("device forgotten")
    await _broadcast({"type": "device_removed", "device_id": key})
    if plan.active_changed:
        await _broadcast_wall()
    else:
        await hub._broadcast_config_updated()
    return [asdict(item) for item in plan.remaining_saved]


async def _apply_rebind(key: str, command: device_lifecycle.RebindApply) -> device_lifecycle.RebindPlan:
    try:
        inputs = _lifecycle_inputs(key)
        assert isinstance(inputs, device_lifecycle.RebindInputs)
        plan = device_lifecycle.plan_rebind(command, inputs)
    except device_lifecycle.LifecycleError as error:
        raise _lifecycle_error(error) from error
    roster = deepcopy(devices)
    roster.pop(plan.delete_roster_id, None)
    roster[key] = plan.target_record
    _commit_lifecycle(roster, plan.active_layout, active_changed=plan.preview.affected_active, rebind=plan)
    render_status.replace(plan.delete_roster_id, key)
    identify_commands.pop(plan.delete_roster_id, None)
    identify_commands.pop(key, None)
    await _abort_playback("rebind")
    await _broadcast({"type": "device_removed", "device_id": plan.delete_roster_id})
    await _broadcast({"type": "device_updated", "device": _device_record(key)})
    if plan.preview.affected_active:
        await _broadcast_wall()
    else:
        await hub._broadcast_config_updated()
    socket = device_sockets.get(key)
    if socket is not None:
        with contextlib.suppress(Exception):
            await socket.close(code=WS_CLOSE_NORMAL)
    return plan


@app.patch("/api/v3/devices/{device_id}")
async def label_device_v3(device_id: UUID4, command: device_lifecycle.LabelCommand, request: Request):
    _require_config_etag(request)
    key = str(device_id)
    if key not in devices:
        raise HTTPException(status_code=404, detail="Unknown device")
    roster = deepcopy(devices)
    roster[key]["label"] = command.label
    _commit_lifecycle(roster, wall["layout"], active_changed=False)
    await hub._broadcast_config_updated()
    await hub._broadcast_device_status(key, presentation_active=_presentation_active())
    return await get_config_v3()


@app.get("/api/v3/devices/{device_id}/impact")
async def device_impact_v3(device_id: UUID4):
    try:
        return asdict(device_lifecycle.preview_impact(str(device_id), _lifecycle_inputs()))
    except device_lifecycle.LifecycleError as error:
        raise _lifecycle_error(error) from error


@app.delete("/api/v3/devices/{device_id}/placement")
@app.post("/api/v3/devices/{device_id}/remove")
async def remove_device_v3(device_id: UUID4, request: Request):
    _require_config_etag(request)
    try:
        plan = device_lifecycle.plan_remove(str(device_id), _lifecycle_inputs())
    except device_lifecycle.LifecycleError as error:
        raise _lifecycle_error(error) from error
    _commit_lifecycle(deepcopy(devices), plan.active_layout, active_changed=plan.active_changed)
    if plan.active_changed:
        await _abort_playback("device removed from wall")
        await _broadcast_wall()
    return await get_config_v3()


@app.delete("/api/v3/devices/{device_id}")
async def forget_device_v3(device_id: UUID4, command: device_lifecycle.ForgetCommand, request: Request):
    _require_config_etag(request)
    remaining = await _forget_device(str(device_id), command)
    return await _snapshot_response(notify=False, removed=True, device_id=str(device_id), remaining_saved=remaining)


@app.post("/api/v3/devices/{device_id}/rebind/preview")
async def preview_rebind_v3(device_id: UUID4, command: device_lifecycle.RebindCommand, request: Request):
    _require_config_etag(request)
    try:
        inputs = _lifecycle_inputs(str(device_id))
        assert isinstance(inputs, device_lifecycle.RebindInputs)
        return asdict(device_lifecycle.preview_rebind(command, inputs))
    except device_lifecycle.LifecycleError as error:
        raise _lifecycle_error(error) from error


@app.post("/api/v3/devices/{device_id}/rebind")
async def rebind_v3(device_id: UUID4, command: device_lifecycle.RebindApply, request: Request):
    _require_config_etag(request)
    plan = await _apply_rebind(str(device_id), command)
    return await _snapshot_response(notify=False, rebound=True, rebind=asdict(plan.preview))


_identify_tasks: set[asyncio.Task[Any]] = set()


async def _identify_expiry(key: str, command: dict[str, Any]) -> None:
    await asyncio.sleep(max(0, command["expires_mono"] - time.monotonic()))
    record = devices.get(key)
    socket = device_sockets.get(key)
    if (identify_commands.get(key) is command and record and socket
            and record.get("connection_id") == command["connection_id"]
            and wall["generation"] == command["generation"]):
        identify_commands.pop(key, None)
        await _send_wall_to_device(key, socket, record)
        await hub._broadcast_device_status(key, presentation_active=_presentation_active())


def _owned_device(key: str, *, capability: str | None = None) -> tuple[dict[str, Any], WebSocket]:
    if key not in devices:
        raise HTTPException(status_code=404, detail="Unknown device")
    socket = device_sockets.get(key)
    if socket is None:
        raise HTTPException(status_code=409, detail={"code": "offline", "message": "Tablet is offline"})
    record = devices[key]
    if capability and (record.get("protocol") != 3 or capability not in (record.get("caps") or [])):
        raise HTTPException(status_code=409, detail={"code": "unsupported_client", "message": "Upgrade tablet client"})
    return record, socket


@app.post("/api/v3/devices/{device_id}/identify")
async def identify_device_v3(device_id: UUID4, request: Request,
                             command: device_lifecycle.IdentifyCommand = device_lifecycle.IdentifyCommand()):
    _require_config_etag(request)
    key = str(device_id)
    record, socket = _owned_device(key, capability="identify")
    now = _now_ms()
    command_state = {"command_id": uuid.uuid4().hex, "connection_id": record["connection_id"],
        "generation": wall["generation"], "state": "queued", "duration_ms": command.duration_ms,
        "expires_mono": time.monotonic() + command.duration_ms / 1000,
        "expires_ms": now + command.duration_ms}
    identify_commands[key] = command_state
    frame = {"type": "identify", "command_id": command_state["command_id"],
        "connection_id": command_state["connection_id"], "generation": wall["generation"],
        "server_ms": now, "expires_ms": command_state["expires_ms"], "duration_ms": command.duration_ms,
        "remaining_ms": float(command.duration_ms), "label": record.get("label"), "number": record.get("number")}
    def stamp(target: dict[str, Any]) -> None:
        target["remaining_ms"] = device_lifecycle.identify_remaining_ms(
            command_state["expires_mono"], time.monotonic(), command.duration_ms)
        target["server_ms"] = _now_ms()
        if (device_sockets.get(key) is not socket or identify_commands.get(key) is not command_state
                or wall["generation"] != command_state["generation"]):
            target["remaining_ms"] = 0
    await _send_to(socket, frame, stamp=stamp)
    task = asyncio.create_task(_identify_expiry(key, command_state))
    _identify_tasks.add(task)
    task.add_done_callback(_identify_tasks.discard)
    await hub._broadcast_device_status(key, presentation_active=_presentation_active())
    return await get_config_v3()


@app.post("/api/v3/devices/{device_id}/retry-image")
async def retry_image_v3(device_id: UUID4, request: Request):
    _require_config_etag(request)
    record, socket = _owned_device(str(device_id), capability="render_ack")
    await _send_wall_to_device(str(device_id), socket, record)
    await hub._broadcast_device_status(str(device_id), presentation_active=_presentation_active())
    return await get_config_v3()


@app.post("/api/v3/devices/{device_id}/reconnect")
async def reconnect_device_v3(device_id: UUID4, request: Request):
    _require_config_etag(request)
    record, socket = _owned_device(str(device_id))
    render_status.disconnect(str(device_id), record["connection_id"])
    identify_commands.pop(str(device_id), None)
    await socket.close(code=WS_CLOSE_NORMAL)
    return await get_config_v3()


def _grid_inputs(command: grid.GridCommand) -> grid.GridInputs:
    profiles, calibrations = displays.histories()
    assignments = tablet_models.assignments()
    ids = set(devices) | set(layouts.entries(wall["layout"]))
    return grid.GridInputs(active_layout=wall["layout"], base_etag=_config_etag(), devices=[
        grid.GridDevice(device_id=key, online=_is_online(key),
            connection_id=devices.get(key, {}).get("connection_id") if key in device_sockets else None,
            viewport=devices.get(key, {}).get("viewport"), profiles=profiles.get(key, {}),
            calibrations=calibrations.get(key, {}), model=grid.confirmed_model(
                tablet_models.pinned_assignment(key, calibrations.get(key, {}).get(command.physical_revisions[key].calibration_revision))
                if key in command.physical_revisions else assignments.get(key)))
        for key in ids])


def _grid_error(error: grid.GridError) -> HTTPException:
    return HTTPException(status_code=error.status, detail={"code": error.code, "message": str(error),
        "conflicts": error.conflicts})


@app.post("/api/v3/grid/preview")
async def preview_grid_v3(request: Request, payload: dict[str, Any]):
    _require_config_etag(request)
    try:
        command = grid.GridCommand.from_payload(payload)
        return grid.build_grid(command, _grid_inputs(command))
    except grid.GridError as error:
        raise _grid_error(error) from error


@app.post("/api/v3/grid")
async def apply_grid_v3(request: Request, payload: dict[str, Any]):
    _require_config_etag(request)
    try:
        command = grid.GridCommand.from_payload(payload)
        inputs = _grid_inputs(command)
        preview = grid.build_grid(command, inputs)
        _require_config_etag(request)
        grid.validate_guards(command.guards, grid.connection_guards(_grid_inputs(command), command.device_ids))
        previous = _replace_layout(preview["layout"])
    except grid.GridError as error:
        raise _grid_error(error) from error
    return await _layout_response(previous)


def _snapshot_layout_listing(kind: str) -> dict[str, Any]:
    summaries = {row["name"]: row for row in operator_state.snapshots(_valid_any_layout, _valid_saved_content)["layouts"]}
    return {"layouts": [{**summaries[name], "layout": value} for name, value in load_layouts()
        if not summaries[name]["valid"] or layouts.kind(value) == kind]}


async def _snapshot_response(*, notify: bool = True, **metadata: Any) -> JSONResponse:
    if notify:
        await hub._broadcast_config_updated()
    payload = _config_payload()
    etag = _config_etag(payload)
    return JSONResponse({**payload, **metadata, "etag": etag}, headers={"ETag": etag, "Cache-Control": "no-store"})


@app.put("/api/v3/logical-layouts/{name}")
async def save_logical_layout_v3(name: str, request: Request, replace: bool = Query(default=False)):
    _require_config_etag(request)
    if layouts.kind(wall["layout"]) != "logical":
        raise HTTPException(status_code=409, detail="the active layout is physical")
    canonical = _snapshot_name(name)
    if not save_layout(canonical, deepcopy(wall["layout"]), replace=replace):
        raise HTTPException(status_code=409, detail="Layout name already exists")
    return await _snapshot_response(saved=True, name=canonical)


@app.delete("/api/v3/logical-layouts/{name}")
async def delete_logical_layout_v3(name: str, request: Request):
    _require_config_etag(request)
    canonical = _snapshot_name(name)
    rows = dict(load_layouts())
    if canonical not in rows:
        raise HTTPException(status_code=404, detail="Unknown layout")
    if _valid_any_layout(rows[canonical]) and layouts.kind(rows[canonical]) != "logical":
        raise HTTPException(status_code=409, detail="not a logical layout")
    delete_layout(canonical)
    return await _snapshot_response(deleted=True, name=canonical)


@app.get("/api/v3/scenes")
async def list_scenes_v3():
    summaries = {row["name"]: row for row in operator_state.snapshots(_valid_any_layout, _valid_saved_content)["scenes"]}
    return {"scenes": [{**summaries[name], "content": value} for name, value in load_scenes()]}


@app.put("/api/v3/scenes/{name}")
async def save_scene_v3(name: str, request: Request, replace: bool = Query(default=False)):
    _require_config_etag(request)
    canonical = _snapshot_name(name)
    if not save_scene(canonical, deepcopy(wall["scene"]["content"]), replace=replace):
        raise HTTPException(status_code=409, detail="Scene name already exists")
    return await _snapshot_response(saved=True, name=canonical)


@app.delete("/api/v3/scenes/{name}")
async def delete_scene_v3(name: str, request: Request):
    _require_config_etag(request)
    canonical = _snapshot_name(name)
    if not delete_scene(canonical):
        raise HTTPException(status_code=404, detail="Unknown scene")
    return await _snapshot_response(deleted=True, name=canonical)


@app.post("/api/v3/scenes/{name}/recall")
async def recall_scene_v3(name: str, request: Request):
    _require_config_etag(request)
    try:
        saved = load_scene(_snapshot_name(name))
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="Saved scene is invalid") from None
    if saved is None:
        raise HTTPException(status_code=404, detail="Unknown scene")
    if not _valid_saved_content(saved):
        raise HTTPException(status_code=422, detail="Saved scene is invalid")
    content = SceneContent(**{key: saved[key] for key in ("type", "asset", "fit", "background") if key in saved})
    return await put_scene_v3(SceneUpdate(content=content), request)


class TestPatternCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    pattern: Literal["grid", "black"]


def _publish_pattern(data: bytes) -> str:
    """Publish immutable bytes into the existing curated store without following links."""
    directory = assets.asset_dir()
    os.makedirs(directory, exist_ok=True)
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    name = "wall-pattern-" + hashlib.sha256(data).hexdigest() + ".png"
    temporary = ".pattern-" + uuid.uuid4().hex
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
        except FileExistsError:
            existing_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
            with os.fdopen(existing_fd, "rb") as stream:
                if stream.read(len(data) + 1) != data:
                    raise HTTPException(status_code=409, detail="Generated pattern path contains different bytes")
        os.fsync(directory_fd)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=directory_fd)
        os.close(directory_fd)
    return "sha256:" + hashlib.sha256(data).hexdigest()


@app.post("/api/v3/test-pattern")
async def test_pattern_v3(command: TestPatternCommand, request: Request):
    _require_config_etag(request)
    if command.pattern == "grid" and layouts.kind(wall["layout"]) != "physical":
        raise HTTPException(status_code=422, detail="grid requires a physical layout")
    bounds = deepcopy(wall["layout"].get("bounds"))
    try:
        generated = await asyncio.to_thread(test_pattern.generate_test_pattern, command.pattern, bounds=bounds)
    except test_pattern.PatternError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    _require_config_etag(request)
    asset_id = _publish_pattern(generated.data)
    asset = assets.find(asset_id)
    if asset is None:
        raise HTTPException(status_code=500, detail="Generated pattern failed curated validation")
    return {**asset.entry(), "width": asset.width, "height": asset.height, "source": "curated",
            "thumbnail_url": asset.entry()["url"], "metadata": generated.metadata, "etag": _config_etag()}


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
    calibration = tablet_models.effective(device_id, calibration, record.get("viewport") or {})
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
            "dpr": calibration["dpr"],
            "orientation": calibration["orientation"],
            "mode": calibration["mode"],
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
        "playlist_revision": session.playlist_revision,
        "live": {
            "current": playback.item_metadata(session, session.current),
            "displayed": playback.item_metadata(session, session.displayed),
            "pending": playback.item_metadata(
                session, session.pending.occurrence if session.pending else None
            ),
        },
        "cohort": session.cohort,
        "required": sorted(session.required),
        "excluded": sorted(session.excluded),
        "missed": session.missed,
        "held": session.held,
        "hold_deadline_ms": session.hold_deadline_ms,
        "policy": session.policy,
        "blocked_reason": session.blocked_reason,
        "final": session.final,
        "paused_at_ms": session.paused_at_ms,
        "recovery": playback.recovery_status(session, now),
        "video": playback.video_status(session, _now_ms()),
        "members": {
            device_id: {
                "ready": bool(
                    lease.ready
                    and lease.clock_ok
                    and lease.lease_expires_ms > now
                    and session.pending is not None
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
    if descriptor.get("kind") != "video" and "image" not in record.get("caps", ()):
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
        "type": "prepare",
        **pending.as_frame(),
        **session.lineage(),
        "asset": {**descriptor, **({"fit": "cover", "background": "#0b1120"} if descriptor.get("kind") != "video" else {})},
        "plan": plan,
        "calibration": calibration,
        "connection_id": connection_id,
        "cohort": session.cohort,
    }
    await _send_to(socket, frame)
    return True


async def _prepare_playback(session: playback.Session) -> None:
    pending = session.pending
    if pending is None:
        return
    for device_id in session.cohort:
        with contextlib.suppress(Exception):
            await _send_prepare(session, pending, device_id)


async def _send_excluded_stopped(session: playback.Session) -> None:
    """Tell each reachable excluded device to show the persisted scene.

    Excluded slots are not in the effective cohort, so they never receive a
    prepare. The frame is built once and a broken writer cannot skip another
    excluded device.
    """
    frame = {
        "type": "playback", "state": "stopped", "reason": "excluded",
        **session.lineage(),
    }
    for device_id in session.excluded:
        socket = device_sockets.get(device_id)
        if socket is None:
            continue
        try:
            await _send_to(socket, frame)
        except Exception:
            continue


async def _playback_after_reconnect(
    session: playback.Session, device_id: str
) -> None:
    """Rejoin one replacement socket to the active session.

    A recovery or ordinary preparation already in flight is only re-sent to
    this socket; the attempt and deadline stay frozen. A playing video starts
    one server-authoritative group recovery, while every operator-controlled
    or near-end state stays on the persisted scene.
    """
    if session is not _playback_session or device_id not in session.cohort:
        # A session replaced while the welcome/render was being written must
        # not start a recovery under its old lineage.
        return
    if session.state in ("recovering", "preparing", "armed"):
        pending = session.pending
        if pending is not None:
            with contextlib.suppress(Exception):
                await _send_prepare(session, pending, device_id)
        return
    if (
        session.state == "playing"
        and session.current_media is None
        and session.pending is not None
    ):
        # A still occurrence has no video picture to recover. Re-send the
        # routine next preparation so the replacement can join the next cut.
        with contextlib.suppress(Exception):
            await _send_prepare(session, session.pending, device_id)
        return
    result = playback.accept_reconnect(
        session,
        device_id=device_id,
        now_ms=_now_ms(),
        connections=_playback_connections(session.cohort),
    )
    if result != "started":
        return
    await _prepare_playback(session)
    await _broadcast_playback()


async def _send_terminal_hold(session: playback.Session) -> None:
    """Freeze every reachable cohort socket on a terminal blocked/failed state.

    The frame is built once, before any await, so every device receives the
    same lineage and missing set. A broken writer is isolated: it must not
    skip the remaining members. No prepare follows a terminal transition.
    """
    frame = {
        "type": "playback",
        "state": session.state,
        "reason": session.blocked_reason,
        "missing": sorted(session.missed),
        **session.lineage(),
    }
    for device_id in session.cohort:
        socket = device_sockets.get(device_id)
        if socket is None:
            continue
        try:
            await _send_to(socket, frame)
        except Exception:
            continue


async def _send_commit(session: playback.Session, action: dict[str, Any]) -> None:
    descriptor = _asset_descriptor(action["asset"])
    expected = action.get("connections") or {}
    failed: list[str] = []
    for device_id in action["devices"]:
        record = devices.get(device_id)
        socket = device_sockets.get(device_id)
        if record is None or socket is None:
            failed.append(device_id)
            continue
        if device_id in expected and record.get("connection_id") != expected[device_id]:
            # A replacement socket has not prepared this occurrence.
            failed.append(device_id)
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
        try:
            await _send_to(socket, frame)
        except Exception:
            failed.append(device_id)
    if failed:
        session.missed = sorted(set(session.missed) | set(failed))


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
    last_fault_log = float("-inf")
    while True:
        await asyncio.sleep(0.1)
        try:
            if _server_clock is not None and _server_clock.check_suspend():
                await _abort_playback("host suspend")
            session = _playback_session
            if session is None or session.state in ("stopped", "failed"):
                continue
            _revoke_missing_leases(session)
            actions = playback.tick(session, _now_ms())
            for action in actions:
                if action["type"] == "commit":
                    await _send_commit(session, action)
                if action["type"] in ("commit", "recover"):
                    await _prepare_playback(session)
                if action["type"] in ("blocked", "failed"):
                    # Every blocked/failed state is terminal for the session:
                    # the attempt cap, a recovery timeout or a preparation
                    # timeout leaves no next commit. The hold is idempotent
                    # and carries no prepare.
                    await _send_terminal_hold(session)
                if action["type"] in (
                    "commit", "hold", "failed", "blocked", "reanchor", "recover",
                ):
                    await _broadcast_playback()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            now = time.monotonic()
            if now - last_fault_log >= 60:
                logging.getLogger(__name__).error(
                    "Experimental playback loop failed (%s)", type(error).__name__
                )
                last_fault_log = now
            session = _playback_session
            if session is not None and session.state not in ("stopped", "failed"):
                session.state = "failed"
                session.blocked_reason = "Internal experimental playback error. Stop and return to still images."
                session.pending = None
                with contextlib.suppress(Exception):
                    await _send_terminal_hold(session)
                    await _broadcast_playback()


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
    supplied = request.headers.get("if-match")
    current = persist.load_meta("playlist")
    if not supplied:
        raise HTTPException(status_code=428, detail="If-Match is required")
    if supplied.strip().strip('"') != _playlist_etag(current):
        raise HTTPException(status_code=412, detail="playlist changed; reload")
    # A legacy document without a revision is revision 1, so its first
    # successful save writes 2. Nothing advances until If-Match matched.
    revision = int(current.get("revision", 1)) + 1 if isinstance(current, dict) else 1
    document = {"items": items, "loop": command.loop, "revision": revision}
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
    exclusions: list[str] = Field(default_factory=list)


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
    explicit = command.policy if command is not None and supplied else None
    if supplied and explicit not in playback.POLICIES:
        raise HTTPException(status_code=422, detail='policy must be "online" or "strict"')
    session = _playback_session
    if session is not None and session.state == "paused":
        # A paused Start is a Resume of the frozen selection. Exclusions are a
        # Start-time choice and are ignored here, so a stale picker or a
        # changed layout cannot block the resume.
        playback.resume(session, _now_ms(), _playback_connections(session.cohort))
        await _prepare_playback(session)
        await _broadcast_playback()
        return _playback_status()
    exclusions = list(command.exclusions) if command is not None else []
    document = persist.load_meta("playlist")
    if not isinstance(document, dict):
        raise HTTPException(status_code=409, detail="save a playlist first")
    layout = wall["layout"]
    if layout.get("kind") != "physical":
        raise HTTPException(status_code=409, detail="a physical layout is required")
    videos = _video_durations(document["items"])
    policy = explicit or ("strict" if videos else "online")
    slots = layout["slots"]
    required = sorted(
        device_id for device_id, slot in slots.items()
        if slot.get("participating", True) is not False
    )

    if len(set(exclusions)) != len(exclusions):
        raise HTTPException(status_code=422, detail="exclusions must be unique")
    if any(
        device_id not in slots
        or slots[device_id].get("participating", True) is False
        for device_id in exclusions
    ):
        raise HTTPException(
            status_code=422,
            detail="exclusions must name participating physical slots",
        )
    excluded = set(exclusions)
    if required and set(required) <= excluded:
        raise HTTPException(
            status_code=409, detail="all participating slots are excluded"
        )

    session = _playback_session
    if session is not None and session.state not in ("stopped", "failed"):
        raise HTTPException(status_code=409, detail="playback is already active")

    if policy == "strict":
        cohort = [
            device_id for device_id in required if device_id not in excluded
        ]
    else:
        cohort = [
            device_id for device_id in required
            if device_id not in excluded
            and device_id in devices
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
        playlist_revision=int(document.get("revision", 1)),
        policy=policy,
        videos=videos,
        required=required,
        excluded=sorted(excluded),
    )
    await _prepare_playback(_playback_session)
    await _send_excluded_stopped(_playback_session)
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


def _claim_device_socket(
    device_id: str, websocket: Any, record: dict[str, Any]
) -> Any:
    """Take the one socket slot, revoking the old connection's lease first.

    The replacement is visible to the playback loop immediately. Any await
    before the old lease is cleared would let a tick commit to a preparation
    the new page never saw, so the revocation is synchronous.
    """
    _revoke_playback_lease(device_id, record.get("connection_id"))
    render_status.clear(device_id)
    identify_commands.pop(device_id, None)
    replaced = device_sockets.get(device_id)
    device_sockets[device_id] = websocket
    return replaced


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
        if not text or len(text.encode("utf-8")) > 4096:
            continue
        try:
            payload = json.loads(text)
        except ValueError:
            continue  # unrecognised frames are ignored, not fatal

        if isinstance(payload, dict) and payload.get("type") == "render_ack":
            record = devices.get(device_id)
            if (record is not None and record.get("protocol") == 3
                    and "render_ack" in (record.get("caps") or [])
                    and device_sockets.get(device_id) is websocket):
                mapping, _, _ = current_mapping(device_id, record)
                identifying = operator_state.identify_status(device_id)
                if identifying and identifying["active"] and payload.get("status") == "displayed":
                    continue
                if render_status.accept(device_id, owned_connection_id=record.get("connection_id"),
                        report=text, generation=wall["generation"], revision=wall["revision"],
                        mapping=render_mapping(mapping, record, experimental=_presentation_active())):
                    _touch_device(device_id)
                    await hub._broadcast_device_status(device_id, presentation_active=_presentation_active())
        elif isinstance(payload, dict) and payload.get("type") == "identify_status":
            command = identify_commands.get(device_id)
            if (command is not None and device_sockets.get(device_id) is websocket
                    and payload.get("command_id") == command["command_id"]
                    and payload.get("connection_id") == command["connection_id"]
                    and wall["generation"] == command["generation"]
                    and payload.get("status") in ("shown", "cleared")
                    and command["state"] != "cleared"
                    and time.monotonic() < command["expires_mono"]):
                command["state"] = payload["status"]
                if command["state"] == "cleared":
                    identify_commands.pop(device_id, None)
                    await _send_wall_to_device(device_id, websocket, devices[device_id])
                await hub._broadcast_device_status(device_id, presentation_active=_presentation_active())
        elif isinstance(payload, dict) and payload.get("type") == "clock_sample":
            sample_id = payload.get("id")
            c0 = payload.get("c0")
            if (
                isinstance(sample_id, str)
                and isinstance(c0, (int, float))
                and not isinstance(c0, bool)
                and isfinite(c0)
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
                and device_sockets.get(device_id) is websocket
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
                preparation = session.pending
                expected = (
                    preparation.leases[device_id].mapping_revision
                    if preparation is not None and device_id in preparation.leases else None
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
        elif isinstance(payload, dict) and payload.get("type") == "video_fault":
            session = _playback_session
            record = devices.get(device_id)
            if (
                session is not None
                and record is not None
                and device_sockets.get(device_id) is websocket
            ):
                result = playback.accept_fault(
                    session,
                    device_id=device_id,
                    payload=payload,
                    now_ms=_now_ms(),
                    connections=_playback_connections(session.cohort),
                )
                if result == "preparing":
                    await _prepare_playback(session)
                elif result in ("blocked", "failed"):
                    # The cap spent its last attempt: freeze the cohort and do
                    # not prepare a fourth time.
                    await _send_terminal_hold(session)
                if result != "ignored":
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
                previous_viewport = devices[device_id].get("viewport")
                validated = validated_viewport(viewport)
                if validated is None:
                    continue
                devices[device_id]["viewport"] = validated
                record = devices[device_id]
                if record.get("protocol") == 3:
                    changed = previous_viewport != record.get("viewport")
                    if changed:
                        _revoke_playback_lease(device_id, record.get("connection_id"))
                    await _send_wall_to_device(device_id, websocket, record)
                    await hub._broadcast_device_status(device_id, presentation_active=_presentation_active())
                    if changed and _playback_session is not None:
                        await _playback_after_reconnect(_playback_session, device_id)


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
    visual_scale: str | None = Query(default=None, max_length=32),
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
    record = devices[key]
    with device_changes():
        _touch_device(key)
        released = _ensure_device_number(key)
    replaced = _claim_device_socket(key, websocket, record)
    record["protocol"] = negotiated
    record["caps"] = _parse_caps(caps)
    record["connection_id"] = uuid.uuid4().hex
    viewport = validated_viewport({"width": w, "height": h, "dpr": dpr,
        "orientation": orientation, "mode": mode, "visual_scale": visual_scale or "1"}, query=True)
    if viewport is not None:
        record["viewport"] = viewport
    else:
        record.pop("viewport", None)
    owned_connection_id = record["connection_id"]

    if replaced is not None and replaced is not websocket:
        with contextlib.suppress(Exception):
            await replaced.close(code=WS_CLOSE_REPLACED)

    for old_id in released:
        if old_id in devices:
            await _broadcast({"type": "device_updated", "device": _device_record(old_id)})
    if device_sockets.get(key) is not websocket:
        await websocket.close(code=WS_CLOSE_REPLACED)
        return

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
            welcome["connection_id"] = owned_connection_id
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
            await _playback_after_reconnect(session, key)

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
            _revoke_playback_lease(key, owned_connection_id)
            render_status.disconnect(key, owned_connection_id)
            identify_commands.pop(key, None)
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
    if negotiated is None or (negotiated != 3 and wall["layout"].get("kind") == "physical"):
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
