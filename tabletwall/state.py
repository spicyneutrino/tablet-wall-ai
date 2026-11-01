"""In-memory state for devices, sockets, and the wall (PROTOCOL.md).

Everything here is module-level mutable state plus the pure helpers that read
it. Tests mutate these objects directly through ``main``'s re-exports, so the
names must be imported, never copied.

The wall keeps its four contract pieces separate (PROTOCOL.md "Wall state"):
``layout`` (width, height, placements), ``scene`` (content plus its layout
reference), ``revision``, and ``generation``. Durable roster metadata and the
wall are stored in SQLite. Socket registries and live connection facts remain process-local.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from tabletwall import geometry, persist
from tabletwall.protocol import HEARTBEAT_TIMEOUT_S, _asset_url, _now_iso

# Wall defaults (PROTOCOL.md "Wall state"): a 2x1 wall of landscape panels.
DEFAULT_WALL_WIDTH = 2000
DEFAULT_WALL_HEIGHT = 1000

# A tablet's small display number is leased while it stays in contact. The
# number is not identity: a tablet that is gone for this long releases it for
# a replacement, so physical labels do not accumulate dead numbers.
DEVICE_NUMBER_LEASE_S = 15 * 60
ROSTER_CHECKPOINT_S = 60
_logger = logging.getLogger(__name__)


def _new_generation() -> str:
    """A fresh ``generation`` token (PROTOCOL.md "Revision and generation").

    Short lowercase hex, matching the example frame in the protocol. It is
    minted on every server start so a restarted, restored, or rolled-back
    server forces clients to resynchronise instead of rejecting its state as
    stale; revision monotonicity only orders frames within a generation.
    """
    return uuid.uuid4().hex[:8]


def _fresh_wall() -> dict[str, Any]:
    """A brand-new wall state: the PROTOCOL.md defaults, revision 0, a new
    generation."""
    return {
        "layout": {
            "width": DEFAULT_WALL_WIDTH,
            "height": DEFAULT_WALL_HEIGHT,
            "placements": {},
        },
        "scene": {"content": {"type": "color"}, "layout": "active"},
        "revision": 0,
        "generation": _new_generation(),
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

# The wall state (PROTOCOL.md "Version 2 — wall, placements, and scenes"),
# kept as its four pieces: ``layout`` {width, height, placements}, ``scene``
# {content, layout}, ``revision``, ``generation``. ``tabletwall.persist`` saves
# this dict to SQLite; tests reset it through ``_fresh_wall``.
wall: dict[str, Any] = _fresh_wall()


def restore_devices() -> None:
    """Restore metadata with no live sockets or negotiated connection facts."""
    restored = persist.load_devices()
    devices.clear()
    devices.update(restored)
    device_sockets.clear()
    controller_sockets.clear()
    controller_protocols.clear()


@contextmanager
def device_changes() -> Iterator[None]:
    """Commit synchronous roster and wall mutations together before notification."""
    original = dict(devices)
    previous = deepcopy(devices)
    previous_wall = deepcopy(wall)
    try:
        with persist.transaction():
            yield
            persist.save_devices(devices)
    except Exception:
        for key, record in original.items():
            record.clear()
            record.update(previous[key])
        devices.clear()
        devices.update(original)
        wall.clear()
        wall.update(previous_wall)
        raise


def checkpoint_devices() -> None:
    """Keep last contact times durable without a write for every heartbeat."""
    try:
        persist.save_devices(devices)
    except Exception:
        _logger.exception("could not checkpoint device metadata; the next checkpoint will retry")


async def checkpoint_loop() -> None:
    while True:
        await asyncio.sleep(ROSTER_CHECKPOINT_S)
        checkpoint_devices()


def _touch_device(device_id: str) -> None:
    """Record that ``device_id`` just made contact.

    Two clocks, for two jobs: ``last_seen`` is a UTC ISO timestamp for
    operators and logs, and ``last_seen_mono`` is a monotonic reading used for
    expiry. Presence must not be decided by the wall clock, because a clock
    step or an NTP correction could otherwise mark every tablet stale at once
    or keep a dead one online forever.
    """
    record = devices.get(device_id)
    if record is None:
        return
    record["last_seen"] = _now_iso()
    record["last_seen_mono"] = time.monotonic()


def _seconds_since_last_seen(device_id: str) -> float | None:
    """Seconds since this device last checked in, or None if it is unknown.

    Uses the monotonic contact reading while the process runs. Restored
    metadata has only its historical UTC contact time, which is used until
    the device contacts this process again.
    """
    record = devices.get(device_id)
    if record is None:
        return None
    monotonic = record.get("last_seen_mono")
    if isinstance(monotonic, (int, float)):
        return time.monotonic() - monotonic
    return (datetime.now(timezone.utc) - datetime.fromisoformat(record["last_seen"])).total_seconds()


def _is_online(device_id: str) -> bool:
    """True iff the device holds an open socket that has not timed out."""
    if device_id not in device_sockets:
        return False
    age = _seconds_since_last_seen(device_id)
    return age is not None and age <= HEARTBEAT_TIMEOUT_S


def _recycle_device_numbers(exclude: str | None = None) -> list[str]:
    """Release numbers held by tablets that have been gone for the lease.

    A device with an open socket keeps its number even if it is quiet: the
    socket is the stronger signal than a missed heartbeat. Releasing is lazy,
    at allocation time, because a number only needs to be free when someone
    asks for one. Returns the ids whose number was removed so the caller can
    tell controllers before the replacement takes it.
    """
    released: list[str] = []
    for device_id, record in list(devices.items()):
        if device_id == exclude:
            continue
        if not isinstance(record.get("number"), int):
            continue
        if device_id in device_sockets:
            continue
        age = _seconds_since_last_seen(device_id)
        if age is not None and age > DEVICE_NUMBER_LEASE_S:
            record.pop("number", None)
            released.append(device_id)
    return released


def _ensure_device_number(device_id: str, requested: int | None = None) -> list[str]:
    """Give ``device_id`` the lowest free display number.

    Returns any other device ids whose expired number was released first, so
    the caller can broadcast their updated record. An existing number is kept;
    a reconnecting tablet that already lost its number gets the lowest free
    one. The allocation runs before any caller awaits, so two simultaneous
    registrations cannot receive the same number.
    """
    record = devices.get(device_id)
    if record is None:
        return []
    current = record.get("number")
    if isinstance(current, int) and current > 0:
        return []
    released = _recycle_device_numbers(exclude=device_id)
    used = {
        value
        for other in devices.values()
        if isinstance((value := other.get("number")), int)
    }
    if isinstance(requested, int) and requested > 0 and requested not in used:
        record["number"] = requested
        return released
    number = 1
    while number in used:
        number += 1
    record["number"] = number
    return released


def _device_record(device_id: str) -> dict[str, Any]:
    """The wire shape of a device record (PROTOCOL.md "Device record").

    Also carries the version-2 additions: ``protocol`` (the major negotiated
    by the last socket, or None before any socket connected) and ``caps`` (the
    capabilities that socket advertised, empty until then). ``last_seen_mono``
    is process-local bookkeeping and never leaves the process.
    """
    record = devices[device_id]
    return {
        **{key: value for key, value in record.items() if key != "last_seen_mono"},
        "protocol": record.get("protocol"),
        "caps": list(record.get("caps") or []),
        "online": _is_online(device_id),
    }


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


def _project_scene(scene: dict[str, Any]) -> dict[str, Any]:
    """A detached scene copy with its wire-only fields composed in.

    Image content gains the server-composed same-origin URL, derived from the
    persisted asset ID alone (PROTOCOL.md "Still images": "The server composes
    the URL; it is not persisted"). A now-missing asset is projected exactly
    like any other — same ID, same derived dimensions, same URL — so the
    client can report an explicit failure instead of the wall silently
    becoming colour, and composing adds no state, so an inventory change can
    never bump the revision.
    """
    scene = deepcopy(scene)
    content = scene["content"]
    if content.get("type") == "image" and isinstance(content.get("asset"), str):
        content["url"] = _asset_url(content["asset"])
    return scene


def _wall_state() -> dict[str, Any]:
    """The whole wall state in one read, in the ``GET /wall`` wire shape.

    A detached copy, safe to hand to a caller or a frame: the layout fields
    are flattened to the top level, with ``scene``, ``revision``, and
    ``generation`` beside them (PROTOCOL.md "HTTP (v2 additions)"). The scene
    is projected through ``_project_scene``, so an image scene carries its
    composed asset URL here while the live (and persisted) wall never does.
    """
    layout = wall["layout"]
    if layout.get("kind") == "physical":
        return {
            "width": DEFAULT_WALL_WIDTH,
            "height": DEFAULT_WALL_HEIGHT,
            "revision": wall["revision"],
            "generation": wall["generation"],
            "placements": {},
            "scene": {"content": {"type": "color"}, "layout": "active"},
        }
    return {
        "width": layout["width"],
        "height": layout["height"],
        **({"sizing": deepcopy(layout["sizing"])} if "sizing" in layout else {}),
        "revision": wall["revision"],
        "generation": wall["generation"],
        "placements": {
            device_id: {**placement, "bezel": dict(placement["bezel"])}
            for device_id, placement in layout["placements"].items()
        },
        "scene": _project_scene(wall["scene"]),
    }


def _wall_frame(device_id: str, record: dict[str, Any]) -> dict[str, Any]:
    """Build the ``wall`` frame for one device (version 2 only).

    The frame is the complete presentation for this device: the wall's
    dimensions, its own placement, the scene, and both ordering tokens.

    Per-device content downgrade: a device that did not advertise a cap is
    never asked to render what that cap covers, so it is sent ``color``
    content instead. That applies to ``image`` as well — a legacy version-2
    client (no caps at all) or one without the ``image`` cap gets colour and
    no asset URL, while a capable device gets the full descriptor with its
    composed URL (PROTOCOL.md "Still images").
    """
    if wall["layout"].get("kind") == "physical":
        # A cached logical device never receives physical millimetres
        # relabelled as logical dimensions: it gets a fixed neutral envelope
        # with no placement, while its controller is told to upgrade.
        return {
            "type": "wall",
            "revision": wall["revision"],
            "generation": wall["generation"],
            "wall": {"width": DEFAULT_WALL_WIDTH, "height": DEFAULT_WALL_HEIGHT},
            "scene": {"content": {"type": "color"}, "layout": "active"},
            "placement": None,
        }
    scene = _project_scene(wall["scene"])
    caps = record.get("caps", ())
    content = scene["content"]
    if content.get("type") == "calibration" and "calibration" not in caps:
        # Replacing the whole content object drops any asset URL with it.
        scene["content"] = {"type": "color"}
    elif content.get("type") == "image" and "image" not in caps:
        scene["content"] = {"type": "color"}
    layout = wall["layout"]
    return {
        "type": "wall",
        "revision": wall["revision"],
        "generation": wall["generation"],
        "wall": {"width": layout["width"], "height": layout["height"]},
        "scene": scene,
        "placement": _placement_for_client(layout["placements"].get(device_id)),
    }


def _viewport_matches(calibration: dict[str, Any], viewport: dict[str, Any]) -> bool:
    """A live viewport signature must be the one the calibration measured."""
    try:
        return (
            abs(float(viewport["width"]) - calibration["viewport_width"]) <= 1
            and abs(float(viewport["height"]) - calibration["viewport_height"]) <= 1
            and abs(float(viewport["dpr"]) - calibration["dpr"]) <= 0.02
            and int(viewport["orientation"]) == calibration["orientation"]
            and str(viewport["mode"]) == calibration["mode"]
        )
    except (KeyError, TypeError, ValueError):
        return False


def _render_frame(
    device_id: str,
    record: dict[str, Any],
    profile: dict[str, Any] | None = None,
    calibration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The version-3 frame: a logical fallback or a physical render plan.

    The server owns ``G_N_to_P``; the client owns its calibrated
    ``U_C_to_P``. A device without a matching, current viewport calibration
    receives no plan and an explicit reason, never a guessed physical claim.
    """
    layout = wall["layout"]
    scene = _project_scene(wall["scene"])
    record["render_seq"] = int(record.get("render_seq", 0)) + 1
    if layout.get("kind") != "physical":
        logical_frame = _wall_frame(device_id, record)
        return {"type": "render", "mode": "logical", "render_seq": record["render_seq"], **logical_frame}

    bounds = layout["bounds"]
    slot = layout["slots"].get(device_id)
    frame: dict[str, Any] = {
        "type": "render",
        "mode": "physical",
        "render_seq": record["render_seq"],
        "revision": wall["revision"],
        "generation": wall["generation"],
        "wall": {"width": bounds["width"], "height": bounds["height"]},
        "scene": {"content": scene["content"]},
        "slot": slot,
        "calibration": {"status": "needs_calibration", "revision": None},
        "plan": None,
    }
    image_unsupported = scene["content"].get("type") == "image" and "image" not in record.get("caps", ())
    if image_unsupported:
        frame["scene"]["content"] = {"type": "color"}
    if slot is None:
        frame["calibration"]["reason"] = "no physical slot"
        return frame
    if image_unsupported:
        frame["calibration"]["reason"] = "tablet does not advertise image support"
        return frame
    if profile is None or calibration is None:
        frame["calibration"]["reason"] = "no measured profile or calibration"
        return frame
    if calibration.get("profile_revision") != slot.get("profile_revision"):
        frame["calibration"]["reason"] = "calibration does not match the slot profile"
        return frame
    if not _viewport_matches(calibration, record.get("viewport") or {}):
        frame["calibration"]["reason"] = "viewport does not match the calibration"
        return frame
    content = scene["content"]
    if content.get("type") != "image":
        frame["calibration"]["reason"] = "physical plans currently require image content"
        return frame
    source_width = content.get("intrinsicWidth")
    source_height = content.get("intrinsicHeight")
    if not isinstance(source_width, int) or not isinstance(source_height, int):
        frame["calibration"]["reason"] = "image dimensions are unknown"
        return frame
    plan = geometry.normalized_source_to_panel(
        active_size=(profile["active_width_mm"], profile["active_height_mm"]),
        bezels=profile["bezels"],
        center_mm=(slot["center_x_mm"], slot["center_y_mm"]),
        nudge_mm=(slot["nudge_x_mm"], slot["nudge_y_mm"]),
        mount_angle=slot["mount_angle"],
        bounds=(bounds["x"], bounds["y"], bounds["width"], bounds["height"]),
        source_size=(source_width, source_height),
        fit=content.get("fit", "cover"),
    )
    frame["plan"] = {
        **plan,
        "source": {"width": source_width, "height": source_height},
    }
    frame["calibration"] = {
        "status": "valid",
        "revision": calibration["revision"],
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
    }
    return frame
