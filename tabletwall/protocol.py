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
