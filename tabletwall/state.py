"""In-memory state for devices, sockets, and the wall (PROTOCOL.md).

Everything here is module-level mutable state plus the pure helpers that read
it. Tests mutate these objects directly through ``main``'s re-exports, so the
names must be imported, never copied.

The wall keeps its four contract pieces separate (PROTOCOL.md "Wall state"):
``layout`` (width, height, placements), ``scene`` (content plus its layout
reference), ``revision``, and ``generation``. The roster and the socket
registries are memory-only; ``tabletwall.persist`` writes the wall dict to
SQLite.
"""

import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from tabletwall.protocol import HEARTBEAT_TIMEOUT_S, _asset_url, _now_iso

# Wall defaults (PROTOCOL.md "Wall state"): a 2x1 wall of landscape panels.
DEFAULT_WALL_WIDTH = 2000
DEFAULT_WALL_HEIGHT = 1000


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

    Uses the monotonic contact reading; a record that predates it (only
    possible in tests or within one process, never across a restart) falls
    back to its UTC timestamp so presence still degrades to a sane answer.
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
    return {
        "width": layout["width"],
        "height": layout["height"],
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
