"""Protocol constants and validation helpers (PROTOCOL.md).

Pure data and pure functions: no imports from the rest of the package, so
``tabletwall.state`` and ``tabletwall.hub`` can both depend on it safely.
"""

import re
import uuid
from datetime import datetime, timezone

# Timing constants (PROTOCOL.md "Timing constants"). Tests monkeypatch these,
# so every read must happen at call time rather than being captured at import.
HEARTBEAT_INTERVAL_MS = 5000
HEARTBEAT_TIMEOUT_S = 15
SWEEP_INTERVAL_S = 2

# Registration bounds (PROTOCOL.md "Device record"). Registration is the one
# public write, so every field is bounded before it can enter memory: a CSS
# viewport beyond 16384 px is not a tablet, a device type is a short label,
# and the roster has a hard ceiling so an unauthenticated caller cannot grow
# the process without limit. Caps are advisory strings used only for content
# downgrade; overlong values are dropped rather than rejected so a hostile
# query cannot make the socket handshake fail open or closed unpredictably.
MAX_DEVICE_DIMENSION = 16384
MAX_DEVICE_TYPE_LENGTH = 32
MAX_DEVICE_CAPS = 32
MAX_DEVICE_CAP_LENGTH = 32
MAX_DEVICES = 512

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
# A connection whose bounded writer queue overflowed or timed out.
WS_CLOSE_WRITER_OVERFLOW = 4429

# Protocol negotiation (PROTOCOL.md "Protocol versions"). An absent ``protocol``
# means version 1; only these majors are accepted.
SUPPORTED_PROTOCOLS = (1, 2, 3)

# What this server can render/serve for version-2 clients. ``image`` joined
# with the curated-asset endpoints (PROTOCOL.md "Still images"); a client only
# sees image content after it advertises the matching cap.
SERVER_CAPS = ["calibration", "image"]
SERVER_CAPS_V3 = ["calibration", "image", "physical", "render_ack", "identify", "image_contain"]

# Still images (PROTOCOL.md "Still images"): a content ID is ``sha256:`` plus
# the lowercase SHA-256 of the file bytes, and the URL a descriptor carries is
# composed by the server from that ID alone — never persisted, never accepted
# from a caller.
ASSET_ID_PREFIX = "sha256:"
_ASSET_ID_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")

# Global image fits are matched exactly.
SUPPORTED_FITS = ("cover", "contain")
DEFAULT_FIT = "cover"

# Named save/recall: one pattern decides whether a path segment is a name at
# all. The first character must be an ASCII letter or digit, the rest may be
# letters, digits, space, and ``.`` ``_`` ``-``; the leading character plus at
# most 63 more is the 64-character cap. Anything outside it is a malformed
# request (422), while a well-formed name that was simply never saved is an
# absence (404).
_SNAPSHOT_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}")

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
    """Split the comma-separated ``caps`` query param into a bounded clean list.

    Caps are advisory: the server uses them only to downgrade content a client
    cannot render. A malformed or oversized entry is therefore dropped rather
    than failing the handshake — the safe outcome is "this client did not
    advertise that capability", which never sends it more than it asked for.
    The list itself is capped so a long query cannot retain unbounded memory.
    """
    if not raw:
        return []
    caps: list[str] = []
    for cap in raw.split(","):
        cap = cap.strip()
        if not cap or len(cap) > MAX_DEVICE_CAP_LENGTH:
            continue
        if cap not in caps:
            caps.append(cap)
        if len(caps) >= MAX_DEVICE_CAPS:
            break
    return caps


def _parse_snapshot_name(raw: str) -> str | None:
    """The canonical name of a saved layout or scene, or None if malformed.

    Outer whitespace is trimmed first, so ``"  Lobby  "`` and ``"Lobby"`` are
    the *same* saved item: the returned string is what gets stored and what a
    caller has to use to read it back or recall it. Trimming happens before
    the pattern is applied, so a canonical name never begins or ends with
    whitespace, and case is significant — ``"Lobby"`` and ``"lobby"`` are two
    different names, neither a synonym for the other. Returns None for
    anything that cannot be a name (empty after trimming, wrong first
    character, forbidden characters, or over 64 characters), which callers
    turn into a 422 rather than storing something they would refuse to read.
    """
    name = raw.strip()
    if not _SNAPSHOT_NAME_PATTERN.fullmatch(name):
        return None
    return name


def _is_asset_id(value: str) -> bool:
    """True for ``sha256:<64 lowercase hex digits>`` — the only ID shape."""
    return _ASSET_ID_PATTERN.fullmatch(value) is not None


def _asset_url(asset_id: str) -> str:
    """The same-origin URL an asset is served from, composed from its ID."""
    return f"/assets/{asset_id}"
