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
import hashlib
import json
import math
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from tabletwall import calibration_health, displays, geometry, persist, render_status, tablet_models
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
identify_commands: dict[str, dict[str, Any]] = {}


def restore_devices() -> None:
    """Restore metadata with no live sockets or negotiated connection facts."""
    render_status.reset()
    identify_commands.clear()
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
    elif content.get("type") == "image" and ("image" not in caps or
            (content.get("fit", "cover") == "contain" and "image_contain" not in caps)):
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


def validated_viewport(value: Any, *, query: bool = False) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    try:
        numeric = ("width", "height", "dpr", "visual_scale")
        if not query and any(not isinstance(value.get(key, 1), (int, float)) for key in numeric):
            return None
        result = {key: float(value.get(key, 1) if key == "visual_scale" else value[key])
                  for key in numeric}
        if any(isinstance(value.get(key), bool) for key in numeric):
            return None
        if not all(math.isfinite(v) and v > 0 for v in result.values()):
            return None
        angle = value["orientation"]
        if (isinstance(angle, bool) or (not query and type(angle) is not int)
                or float(angle) not in (0, 90, 180, 270)):
            return None
        mode = value["mode"]
        if mode not in ("tab", "fullscreen", "standalone"):
            return None
        return {**result, "orientation": int(angle), "mode": mode}
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def measurement_for(device_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    slot = wall["layout"].get("slots", {}).get(device_id)
    if slot is None:
        return None, None
    return (displays.profile(device_id, slot["profile_revision"]),
            displays.calibration(device_id, slot["calibration_revision"]))


def mapping_decision(
    device_id: str, record: dict[str, Any], current_wall: dict[str, Any],
    profile: dict[str, Any] | None, calibration: dict[str, Any] | None,
    assignment: dict[str, Any] | None,
) -> dict[str, Any]:
    """Pure mapping decision shared by readback and static instruction construction."""
    layout = current_wall["layout"]
    content = current_wall["scene"]["content"]
    physical = layout.get("kind") == "physical"
    entry = layout.get("slots" if physical else "placements", {}).get(device_id)
    viewport = validated_viewport(record.get("viewport"))
    caps = record.get("caps") or []
    health = calibration_health.assess_calibration(
        profile=profile, calibration=calibration, assignment=assignment,
        viewport=viewport, device_id=device_id,
    ) if physical else None
    state, reason = "ready", None
    if entry is None or (physical and entry.get("participating", True) is False):
        state, reason = "unplaced", "no physical slot" if physical else "no logical placement"
    elif record.get("protocol") not in (2, 3) or (physical and
            (record.get("protocol") != 3 or "physical" not in caps)):
        state, reason = "unsupported_client", ("tablet does not advertise image support" if content["type"] == "image" and "image" not in caps else "upgrade tablet client for this layout")
    elif content["type"] == "calibration" and physical:
        state, reason = "unsupported_content", "calibration pattern is logical-only"
    elif content["type"] == "calibration" and "calibration" not in caps:
        state, reason = "unsupported_client", "tablet does not advertise calibration support"
    elif content["type"] == "image" and ("image" not in caps or
            (content.get("fit", "cover") == "contain" and "image_contain" not in caps)):
        state, reason = "unsupported_client", ("tablet does not advertise image support" if "image" not in caps else "upgrade tablet client for image fit support")
    elif viewport is not None and abs(viewport["visual_scale"] - 1) > 0.01:
        state, reason = "zoom_changed", "reset browser zoom to 100%"
    elif physical and content["type"] != "color":
        if profile is None or calibration is None:
            state, reason = "needs_calibration", "no pinned profile or calibration"
        elif calibration.get("profile_revision") != entry["profile_revision"]:
            state, reason = "needs_calibration", "calibration does not match pinned profile"
        elif not _viewport_matches(calibration, viewport or {}):
            state, reason = "viewport_mismatch", "viewport does not match pinned calibration"
    digest = hashlib.sha256(json.dumps({
        "layout": layout, "entry": entry, "profile": profile, "calibration": calibration,
        "viewport": viewport, "caps": sorted(caps), "content": content,
        "state": state,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:32]
    return {"state": state, "reason": reason, "revision": digest,
            "profile_revision": entry.get("profile_revision") if physical and entry else None,
            "calibration_revision": entry.get("calibration_revision") if physical and entry else None,
            "health": health, "viewport": viewport}


def current_mapping(device_id: str, record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    profile, pinned = measurement_for(device_id)
    calibration = tablet_models.effective(device_id, pinned, record.get("viewport") or {})
    assignment = tablet_models.pinned_assignment(device_id, pinned)
    return mapping_decision(device_id, record, wall, profile, calibration, assignment), profile, calibration


def render_mapping(mapping: dict[str, Any], record: dict[str, Any], *, experimental: bool = False) -> render_status.RenderMapping:
    viewport = mapping["viewport"]
    return render_status.RenderMapping(
        revision=mapping["revision"], state=mapping["state"],
        viewport=render_status.Viewport(**viewport) if viewport else None,
        image_supported="image" in (record.get("caps") or []), experimental=experimental,
    )


def _render_frame(
    device_id: str, record: dict[str, Any], profile: dict[str, Any] | None = None,
    calibration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    layout = wall["layout"]
    scene = _project_scene(wall["scene"])
    record["render_seq"] = int(record.get("render_seq", 0)) + 1
    mapping = mapping_decision(device_id, record, wall, profile, calibration,
                               tablet_models.pinned_assignment(device_id, calibration))
    if layout.get("kind") != "physical":
        frame = {**_wall_frame(device_id, record), "mode": "logical", "render_seq": record["render_seq"]}
        if "render_ack" in (record.get("caps") or []):
            frame["type"] = "render"
    else:
        bounds = layout["bounds"]
        slot = layout["slots"].get(device_id)
        frame = {
            "type": "render", "mode": "physical", "render_seq": record["render_seq"],
            "revision": wall["revision"], "generation": wall["generation"],
            "wall": {"width": bounds["width"], "height": bounds["height"]},
            "scene": scene, "slot": slot, "plan": None,
            "calibration": {"status": "needs_calibration", "revision": None,
                            "reason": mapping["reason"]},
        }
        if mapping["state"] == "ready":
            frame["calibration"] = {"status": "valid", "revision": calibration["revision"] if calibration else None}
            if scene["content"]["type"] == "image" and profile and calibration and slot:
                content = scene["content"]
                plan = geometry.normalized_source_to_panel(
                    active_size=(profile["active_width_mm"], profile["active_height_mm"]),
                    bezels=profile["bezels"], center_mm=(slot["center_x_mm"], slot["center_y_mm"]),
                    nudge_mm=(slot["nudge_x_mm"], slot["nudge_y_mm"]), mount_angle=slot["mount_angle"],
                    bounds=(bounds["x"], bounds["y"], bounds["width"], bounds["height"]),
                    source_size=(content["intrinsicWidth"], content["intrinsicHeight"]), fit=content.get("fit", "cover"),
                )
                frame["plan"] = {**plan, "source": {"width": content["intrinsicWidth"], "height": content["intrinsicHeight"]}}
                frame["calibration"].update({key: calibration[key] for key in (
                    "viewport_width", "viewport_height", "dpr", "orientation", "mode", "quarter_turn", "panel_offset_mm", "mm_per_css")})
                frame["calibration"].update(panel_width=profile["active_width_mm"], panel_height=profile["active_height_mm"])
        if scene["content"]["type"] == "image" and ("image" not in (record.get("caps") or []) or
                (scene["content"].get("fit", "cover") == "contain" and "image_contain" not in (record.get("caps") or []))):
            frame["scene"]["content"] = {"type": "color"}
    frame["mapping"] = mapping
    if record.get("connection_id"):
        frame["token"] = {"connection_id": record["connection_id"], "generation": wall["generation"],
                          "revision": wall["revision"], "render_seq": record["render_seq"],
                          "mapping_revision": mapping["revision"], "asset": wall["scene"]["content"].get("asset")}
    return frame
