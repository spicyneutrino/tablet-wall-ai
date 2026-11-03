"""Bounded, process-local evidence that a tablet drew the instruction it was sent.

This module implements the "Render acknowledgement and operator truth" contract
in ``docs/tablet-wall-readiness/ARCHITECTURE.md``. It depends only on
``tabletwall.protocol`` and caller-supplied values: it never imports ``state``
(the state projection reads render status, so the dependency cannot also point
back), ``hub``, or ``main``.

What is stored, and what is not
-------------------------------
At most one evidence record per device holds:

* the latest expected :class:`RenderToken`,
* the latest accepted :class:`RenderAck` (kept so the operator can see that
  older pixels exist while a new expectation is loading),
* the connection that owns the accepted report sequence, and
* the monotonic receipt time of the accepted report.

Evidence is process-local only. It is never persisted in roster metadata or the
database, and it is cleared on startup, disconnect, takeover, Forget, rebind,
replacement, and any writer enqueue with a different token. Nothing here is a
claim about pixels, panel power, or hardware: it is a bounded report of
application activity from a client. Online presence alone can never become
``displayed``.

Acceptance rules (all must hold; any failure returns ``False`` without
mutating stored evidence):

1. The serialized report is at most :data:`MAX_REPORT_BYTES` bytes and parses
   to an object with exactly the documented keys.
2. The report is a valid :class:`RenderAck`: ``type``, status/reason enums,
   strict integer sequence numbers, positive finite viewport numbers, and a
   boolean ``visible``. Booleans are never accepted as numbers, and NaN or
   infinity is never accepted anywhere.
3. ``owned_connection_id`` is the connection that currently owns the device
   socket, and it matches both the token and the latest expected token.
4. The full token matches the latest expected token exactly, including the
   exact asset or ``None``.
5. The caller's current server ``generation``, wall ``revision``, and mapping
   revision still equal the expected token's values, so an expectation issued
   before a commit but broadcast after it cannot confirm.
6. ``report_seq`` is strictly increasing for that connection.
7. The report's viewport matches the validated viewport in the mapping fence.
8. ``displayed`` additionally requires a ready mapping, image support when the
   token names an asset, a positive validated surface, ``visible: true``, and
   no active experimental presentation. A less healthy client report (hidden,
   zoom, failure) may not override a blocked server mapping to claim display.

The derived :class:`RenderStatus` distinguishes ``offline``, ``unsupported``,
``unplaced``, ``blocked``, ``loading``, ``failed``, ``hidden``, ``stale``,
``unknown``, ``identifying``, and ``displayed``. Only a fresh, current,
matching ``displayed`` acknowledgement sets ``current=True`` and may contribute
to "N of M showing".
"""

import json
import math
import time
from collections.abc import Iterable, Mapping as MappingABC
from dataclasses import asdict, dataclass
from typing import Any, Final

from tabletwall.protocol import HEARTBEAT_TIMEOUT_S, MAX_DEVICES, _is_asset_id

# The serialized acknowledgement bound, checked before any field is parsed.
MAX_REPORT_BYTES: Final = 4096
# Identifiers in a token are server/client connection facts, not free text.
MAX_IDENTIFIER_LENGTH: Final = 128

# Wire enumerations from the architecture contract. Unknown values are invalid
# input, never guessed into a nearby state.
STATUSES: Final = frozenset(
    {
        "loading",
        "displayed",
        "failed",
        "hidden",
        "blocked",
        "unplaced",
        "unsupported",
    }
)
REASONS: Final = frozenset(
    {
        "fetch",
        "decode",
        "size",
        "surface",
        "transform",
        "calibration",
        "viewport",
        "zoom",
        "no_slot",
        "capability",
        "auth",
        "playback",
    }
)
ORIENTATIONS: Final = frozenset({0, 90, 180, 270})
VIEWPORT_MODES: Final = frozenset({"tab", "fullscreen", "standalone"})
MAPPING_STATES: Final = frozenset(
    {
        "ready",
        "unplaced",
        "needs_calibration",
        "viewport_mismatch",
        "zoom_changed",
        "unsupported_content",
        "unsupported_client",
    }
)
# The derived status vocabulary used by ``RenderStatus.state``.
RENDER_STATES: Final = frozenset(
    {
        "offline",
        "unsupported",
        "unplaced",
        "blocked",
        "loading",
        "failed",
        "hidden",
        "stale",
        "unknown",
        "identifying",
        "displayed",
    }
)

_TOKEN_KEYS: Final = frozenset(
    {
        "connection_id",
        "generation",
        "revision",
        "render_seq",
        "mapping_revision",
        "asset",
    }
)
_VIEWPORT_KEYS: Final = frozenset(
    {"width", "height", "dpr", "orientation", "mode", "visual_scale"}
)
_ACK_KEYS: Final = frozenset(
    {"type", "token", "report_seq", "status", "reason", "viewport", "visible"}
)


@dataclass(frozen=True, slots=True)
class RenderToken:
    """The identity of one static device instruction.

    ``connection_id`` is the server's per-socket UUID (an identity fence, not a
    credential). ``render_seq`` advances for every issued instruction and
    retry. ``mapping_revision`` is the opaque static-mapping digest, which can
    change without a wall revision when the effective viewport changes.
    """

    connection_id: str
    generation: str
    revision: int
    render_seq: int
    mapping_revision: str
    asset: str | None


@dataclass(frozen=True, slots=True)
class Viewport:
    """The validated viewport a client reported for one instruction."""

    width: float
    height: float
    dpr: float
    orientation: int
    mode: str
    visual_scale: float


@dataclass(frozen=True, slots=True)
class RenderAck:
    """One acknowledgement after the client actually drew (or failed to)."""

    type: str
    token: RenderToken
    report_seq: int
    status: str
    reason: str | None
    viewport: Viewport
    visible: bool


@dataclass(frozen=True, slots=True)
class RenderMapping:
    """The server's current mapping fence for one device.

    ``revision`` is the opaque mapping digest that must match the expected
    token. ``state`` is the mapping decision (``ready`` or a reason it is not
    usable). ``viewport`` is the validated effective viewport, if known.
    ``image_supported`` is the negotiated image capability decision, and
    ``experimental`` marks an active experimental presentation (playback) that
    suppresses a displayed contribution.
    """

    revision: str
    state: str = "ready"
    viewport: Viewport | None = None
    image_supported: bool = True
    experimental: bool = False


@dataclass(frozen=True, slots=True)
class RenderStatus:
    """Derived operator truth for one device's static rendering.

    ``state`` is one of :data:`RENDER_STATES`. ``current`` is true only for a
    fresh, current, server-confirmed ``displayed`` report; it is the flag that
    may contribute to "N of M showing". ``received_at`` is a process-local
    monotonic reading (never a client timestamp), ``age_ms`` its computed age,
    and ``reason`` the most specific honest explanation, if any.
    """

    state: str
    current: bool
    expected_token: RenderToken | None
    accepted_token: RenderToken | None
    accepted_status: str | None
    received_at: float | None
    age_ms: int | None
    reason: str | None


@dataclass(slots=True)
class _Evidence:
    expected: RenderToken
    expected_at: float
    accepted: RenderAck | None = None
    received_at: float | None = None
    seq_connection: str | None = None
    last_report_seq: int = 0


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def _provided_monotonic(value: object) -> float | None:
    """A finite monotonic reading, or ``None`` when the input is unusable.

    ``None`` as an argument means "read the clock now"; an explicit invalid
    value (bool, string, NaN, infinity) is rejected rather than coerced.
    """
    if value is None:
        return time.monotonic()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _bounded_text(value: object, *, limit: int = MAX_IDENTIFIER_LENGTH) -> str | None:
    """A non-empty bounded string without control characters, or ``None``."""
    if not isinstance(value, str) or not value or len(value) > limit:
        return None
    if any(character < " " or character == "\x7f" or "\ud800" <= character <= "\udfff" for character in value):
        return None
    return value


def _positive_int(value: object) -> int | None:
    """A strictly positive integer that is not a boolean."""
    if type(value) is not int or value <= 0:
        return None
    return value


def _nonnegative_int(value: object) -> int | None:
    """A nonnegative integer that is not a boolean."""
    if type(value) is not int or value < 0:
        return None
    return value


def _positive_finite(value: object) -> float | None:
    """A finite number greater than zero that is not a boolean."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _valid_viewport(value: object) -> Viewport | None:
    """Validate a :class:`Viewport` instance, or return ``None``."""
    if not isinstance(value, Viewport):
        return None
    if _positive_finite(value.width) is None:
        return None
    if _positive_finite(value.height) is None:
        return None
    if _positive_finite(value.dpr) is None:
        return None
    if _positive_finite(value.visual_scale) is None:
        return None
    if type(value.orientation) is not int or value.orientation not in ORIENTATIONS:
        return None
    if not isinstance(value.mode, str) or value.mode not in VIEWPORT_MODES:
        return None
    return value


def _valid_token(value: object) -> RenderToken | None:
    """Validate a :class:`RenderToken` instance, or return ``None``."""
    if not isinstance(value, RenderToken):
        return None
    if _bounded_text(value.connection_id) is None:
        return None
    if _bounded_text(value.generation) is None:
        return None
    if _nonnegative_int(value.revision) is None:
        return None
    if _positive_int(value.render_seq) is None:
        return None
    if _bounded_text(value.mapping_revision) is None:
        return None
    if value.asset is not None:
        if not isinstance(value.asset, str) or not _is_asset_id(value.asset):
            return None
    return value


def _valid_mapping(value: object) -> RenderMapping | None:
    """Validate a :class:`RenderMapping` instance, or return ``None``."""
    if not isinstance(value, RenderMapping):
        return None
    if _bounded_text(value.revision) is None:
        return None
    if not isinstance(value.state, str) or value.state not in MAPPING_STATES:
        return None
    if type(value.image_supported) is not bool or type(value.experimental) is not bool:
        return None
    if value.viewport is not None and _valid_viewport(value.viewport) is None:
        return None
    return value


def _token_from_payload(raw: object) -> RenderToken | None:
    """Parse the exact :class:`RenderToken` wire shape, rejecting any extra key."""
    if not isinstance(raw, MappingABC):
        return None
    if set(raw) != _TOKEN_KEYS:
        return None
    connection_id = _bounded_text(raw.get("connection_id"))
    generation = _bounded_text(raw.get("generation"))
    revision = _nonnegative_int(raw.get("revision"))
    render_seq = _positive_int(raw.get("render_seq"))
    mapping_revision = _bounded_text(raw.get("mapping_revision"))
    asset = raw.get("asset")
    if connection_id is None or generation is None or mapping_revision is None:
        return None
    if revision is None or render_seq is None:
        return None
    if asset is not None and (not isinstance(asset, str) or not _is_asset_id(asset)):
        return None
    return RenderToken(
        connection_id=connection_id,
        generation=generation,
        revision=revision,
        render_seq=render_seq,
        mapping_revision=mapping_revision,
        asset=asset,
    )


def _viewport_from_payload(raw: object) -> Viewport | None:
    """Parse the exact :class:`Viewport` wire shape, rejecting any extra key."""
    if not isinstance(raw, MappingABC):
        return None
    if set(raw) != _VIEWPORT_KEYS:
        return None
    width = _positive_finite(raw.get("width"))
    height = _positive_finite(raw.get("height"))
    dpr = _positive_finite(raw.get("dpr"))
    visual_scale = _positive_finite(raw.get("visual_scale"))
    orientation = raw.get("orientation")
    mode = raw.get("mode")
    if width is None or height is None or dpr is None or visual_scale is None:
        return None
    if type(orientation) is not int or orientation not in ORIENTATIONS:
        return None
    if not isinstance(mode, str) or mode not in VIEWPORT_MODES:
        return None
    return Viewport(
        width=width,
        height=height,
        dpr=dpr,
        orientation=orientation,
        mode=mode,
        visual_scale=visual_scale,
    )


def _ack_from_payload(raw: object) -> RenderAck | None:
    """Parse the exact :class:`RenderAck` wire shape, rejecting any extra key."""
    if not isinstance(raw, MappingABC):
        return None
    if set(raw) != _ACK_KEYS:
        return None
    if raw.get("type") != "render_ack":
        return None
    token = _token_from_payload(raw.get("token"))
    report_seq = _positive_int(raw.get("report_seq"))
    status = raw.get("status")
    reason = raw.get("reason")
    viewport = _viewport_from_payload(raw.get("viewport"))
    visible = raw.get("visible")
    if token is None or report_seq is None or viewport is None:
        return None
    if not isinstance(status, str) or status not in STATUSES:
        return None
    if reason is not None and (not isinstance(reason, str) or reason not in REASONS):
        return None
    if type(visible) is not bool:
        return None
    # A displayed report is a claim of a completed draw; attaching a failure
    # reason contradicts it.
    if status == "displayed" and reason is not None:
        return None
    return RenderAck(
        type="render_ack",
        token=token,
        report_seq=report_seq,
        status=status,
        reason=reason,
        viewport=viewport,
        visible=visible,
    )


def _bounded_payload(report: object) -> dict[str, Any] | None:
    """Bound, parse, and object-shape a report before any field is trusted.

    Raw ``bytes``/``str`` are measured at the wire size. A pre-parsed mapping
    or a typed :class:`RenderAck` is measured after a compact re-encoding, so
    the 4096-byte bound is still enforced; nonfinite floats make that
    encoding fail and the report is rejected.
    """
    try:
        if isinstance(report, RenderAck):
            report = asdict(report)
        if isinstance(report, MappingABC):
            text = json.dumps(
                dict(report), separators=(",", ":"), allow_nan=False, ensure_ascii=False
            )
        elif isinstance(report, (bytes, bytearray)):
            if len(report) > MAX_REPORT_BYTES:
                return None
            text = report.decode("utf-8")
        elif isinstance(report, str):
            text = report
        else:
            return None
        if len(text) > MAX_REPORT_BYTES or len(text.encode("utf-8")) > MAX_REPORT_BYTES:
            return None
        parsed = json.loads(text)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return None
    if not isinstance(parsed, MappingABC):
        return None
    return dict(parsed)


def _viewports_match(left: Viewport, right: Viewport) -> bool:
    """A reported viewport must be the validated one within pixel tolerance.

    Tolerances match the existing calibration viewport signature (1 CSS pixel,
    0.02 DPR); orientation and mode are exact. ``visual_scale`` is compared
    with the same small tolerance rather than exactly, because clients round it
    before sending.
    """
    return (
        abs(left.width - right.width) <= 1.0
        and abs(left.height - right.height) <= 1.0
        and abs(left.dpr - right.dpr) <= 0.02
        and abs(left.visual_scale - right.visual_scale) <= 0.02
        and left.orientation == right.orientation
        and left.mode == right.mode
    )


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------


class RenderRegistry:
    """One process-local evidence record per device.

    The registry is deliberately small: callers set the expectation when a
    writer enqueues an instruction, pass every client acknowledgement through
    :meth:`accept`, and read :meth:`project` for operator truth. The registry
    owns no sockets and no wall state; integration supplies the owned
    connection, current generation/revision, and mapping fence.
    """

    def __init__(self) -> None:
        self._evidence: dict[str, _Evidence] = {}

    # -- expectation -------------------------------------------------------

    def expect(
        self,
        device_id: str,
        token: RenderToken,
        *,
        now_mono: float | None = None,
    ) -> None:
        """Record the latest instruction this device was sent.

        Called by the writer immediately before enqueue. A different token
        makes any accepted report historical (it projects as ``stale``); an
        identical token keeps its evidence because it is the same instruction.
        Raises ``ValueError`` for an invalid device id, token, or clock reading
        because these are server-side construction bugs, not client input.
        """
        if _bounded_text(device_id) is None:
            raise ValueError("device_id must be a bounded non-empty string")
        valid_token = _valid_token(token)
        if valid_token is None:
            raise ValueError("token is not a valid RenderToken")
        now = _provided_monotonic(now_mono)
        if now is None:
            raise ValueError("now_mono must be a finite monotonic reading")
        evidence = self._evidence.get(device_id)
        if evidence is None:
            if len(self._evidence) >= MAX_DEVICES:
                self._evict_oldest()
            self._evidence[device_id] = _Evidence(
                expected=valid_token, expected_at=now
            )
            return
        evidence.expected = valid_token
        evidence.expected_at = now

    def _evict_oldest(self) -> None:
        """Keep the map bounded; evicting evidence only degrades to unknown."""
        if not self._evidence:
            return
        oldest = min(self._evidence, key=lambda key: self._evidence[key].expected_at)
        self._evidence.pop(oldest, None)

    # -- acceptance --------------------------------------------------------

    def accept(
        self,
        device_id: str,
        *,
        owned_connection_id: str | None,
        report: object,
        generation: str,
        revision: int,
        mapping: RenderMapping,
        now_mono: float | None = None,
    ) -> bool:
        """Accept one client report, or reject it without changing evidence.

        ``owned_connection_id`` must be the connection that currently owns the
        device socket (``None`` when it has no socket). ``generation`` and
        ``revision`` are the server's *current* values, not the values that
        were current when the expectation was written, so a commit-before-
        broadcast gap cannot be confirmed by stale evidence.
        """
        if _bounded_text(device_id) is None:
            return False
        if _bounded_text(generation) is None:
            return False
        if _nonnegative_int(revision) is None:
            return False
        payload = _bounded_payload(report)
        if payload is None:
            return False
        ack = _ack_from_payload(payload)
        if ack is None:
            return False
        fence = _valid_mapping(mapping)
        if fence is None:
            return False
        if _bounded_text(owned_connection_id) is None:
            return False
        evidence = self._evidence.get(device_id)
        if evidence is None:
            return False
        expected = evidence.expected
        token = ack.token
        if owned_connection_id != token.connection_id:
            return False
        if token != expected:
            return False
        if expected.generation != generation:
            return False
        if expected.revision != revision:
            return False
        if expected.mapping_revision != fence.revision:
            return False
        if ack.status == "displayed":
            if fence.state != "ready" or fence.experimental:
                return False
            if token.asset is not None and not fence.image_supported:
                return False
            if not ack.visible:
                return False
            if fence.viewport is None:
                return False
            if not _viewports_match(ack.viewport, fence.viewport):
                return False
        elif fence.viewport is not None and not _viewports_match(
            ack.viewport, fence.viewport
        ):
            return False
        now = _provided_monotonic(now_mono)
        if now is None:
            return False
        if evidence.seq_connection == token.connection_id:
            if ack.report_seq <= evidence.last_report_seq:
                return False
        evidence.accepted = ack
        evidence.received_at = now
        evidence.seq_connection = token.connection_id
        evidence.last_report_seq = ack.report_seq
        return True

    # -- projection --------------------------------------------------------

    def project(
        self,
        device_id: str,
        *,
        now_mono: float | None = None,
        online: bool,
        caps: Iterable[str] | None = None,
        mapping: RenderMapping | None = None,
        generation: str | None = None,
        revision: int | None = None,
        identify_active: bool = False,
        presentation_active: bool = False,
    ) -> RenderStatus:
        """Derive operator truth for one device from stored evidence.

        ``online`` is socket/heartbeat presence only; it never implies paint.
        ``caps`` is the negotiated capability list (``None`` means unknown,
        which skips the capability fence). ``generation``/``revision`` are the
        current durable values when the caller has them; a mismatch with the
        expected token projects ``stale``. ``identify_active`` and
        ``presentation_active`` suppress contribution without inventing a
        different scene.
        """
        now = _provided_monotonic(now_mono)
        if now is None:
            raise ValueError("now_mono must be a finite monotonic reading")
        if type(online) is not bool:
            raise ValueError("online must be a bool")
        if type(identify_active) is not bool:
            raise ValueError("identify_active must be a bool")
        if type(presentation_active) is not bool:
            raise ValueError("presentation_active must be a bool")
        if generation is not None and _bounded_text(generation) is None:
            raise ValueError("generation must be a bounded string")
        if revision is not None and _nonnegative_int(revision) is None:
            raise ValueError("revision must be a nonnegative integer")
        evidence = self._evidence.get(device_id)
        expected = evidence.expected if evidence is not None else None
        accepted = evidence.accepted if evidence is not None else None
        received_at = evidence.received_at if evidence is not None else None
        age_ms: int | None = None
        if received_at is not None:
            age_ms = int(max(0.0, now - received_at) * 1000.0)

        def result(
            state: str, reason: str | None = None, *, current: bool = False
        ) -> RenderStatus:
            return RenderStatus(
                state=state,
                current=current,
                expected_token=expected,
                accepted_token=accepted.token if accepted is not None else None,
                accepted_status=accepted.status if accepted is not None else None,
                received_at=received_at,
                age_ms=age_ms,
                reason=reason,
            )

        if not online:
            return result("offline")
        if caps is not None:
            cap_set = {caps} if isinstance(caps, str) else set(caps)
            if (
                "image" not in cap_set
                and expected is not None
                and expected.asset is not None
            ):
                return result("unsupported", "capability")
            if "render_ack" not in cap_set:
                return result("unknown", "capability")
        if identify_active:
            return result("identifying")
        if presentation_active:
            return result("blocked", "playback")

        current_mapping = _valid_mapping(mapping) if mapping is not None else None
        if mapping is not None and current_mapping is None:
            return result("blocked", "mapping")
        if current_mapping is not None:
            if current_mapping.state == "unplaced":
                return result("unplaced", "no_slot")
            if current_mapping.state in ("unsupported_content", "unsupported_client"):
                return result("unsupported", current_mapping.state)
            if current_mapping.state != "ready":
                return result("blocked", current_mapping.state)

        if expected is None:
            return result("unknown")
        if generation is not None and expected.generation != generation:
            return result("stale", "superseded")
        if revision is not None and expected.revision != revision:
            return result("stale", "superseded")
        if (
            current_mapping is not None
            and expected.mapping_revision != current_mapping.revision
        ):
            return result("stale", "superseded")
        if accepted is None:
            return result("unknown")
        if accepted.token != expected:
            return result("stale", "superseded")
        timeout = HEARTBEAT_TIMEOUT_S
        if received_at is None or now - received_at > timeout:
            return result("stale", "expired")

        status = accepted.status
        if status == "displayed":
            if current_mapping is None:
                return result("blocked", "mapping")
            if current_mapping.experimental:
                return result("blocked", "playback")
            if not current_mapping.image_supported and accepted.token.asset is not None:
                return result("unsupported", "capability")
            if not accepted.visible:
                return result("blocked", "surface")
            if current_mapping.viewport is None or not _viewports_match(
                accepted.viewport, current_mapping.viewport
            ):
                return result("blocked", "viewport")
            return result("displayed", current=True)
        return result(status, accepted.reason)

    # -- lifecycle ---------------------------------------------------------

    def clear(self, device_id: str) -> bool:
        """Drop all evidence for one device; ``True`` when something was held.

        Used by Forget, layout replacement, rebind, and takeover cleanup.
        """
        return self._evidence.pop(device_id, None) is not None

    def reset(self) -> None:
        """Drop every record. Called at server startup; nothing is persisted."""
        self._evidence.clear()

    def disconnect(self, device_id: str, connection_id: str) -> bool:
        """Clear evidence only when ``connection_id`` is still the expected one.

        A late disconnect from an older socket of the same device must not
        erase evidence belonging to its replacement connection.
        """
        evidence = self._evidence.get(device_id)
        if evidence is None:
            return False
        if evidence.expected.connection_id != connection_id:
            return False
        return self._evidence.pop(device_id, None) is not None

    def replace(self, old_device_id: str, new_device_id: str) -> None:
        """Clear both identities at a rebind/replacement boundary."""
        self._evidence.pop(old_device_id, None)
        self._evidence.pop(new_device_id, None)


# The process-local default registry. Integration keeps exactly one instance
# and routes writer expectations, socket acknowledgements, and state reads
# through it; tests construct their own ``RenderRegistry``.
registry = RenderRegistry()


def expect(
    device_id: str, token: RenderToken, *, now_mono: float | None = None
) -> None:
    """Module-level :meth:`RenderRegistry.expect` on the default registry."""
    registry.expect(device_id, token, now_mono=now_mono)


def accept(
    device_id: str,
    *,
    owned_connection_id: str | None,
    report: object,
    generation: str,
    revision: int,
    mapping: RenderMapping,
    now_mono: float | None = None,
) -> bool:
    """Module-level :meth:`RenderRegistry.accept` on the default registry."""
    return registry.accept(
        device_id,
        owned_connection_id=owned_connection_id,
        report=report,
        generation=generation,
        revision=revision,
        mapping=mapping,
        now_mono=now_mono,
    )


def project(
    device_id: str,
    *,
    now_mono: float | None = None,
    online: bool,
    caps: Iterable[str] | None = None,
    mapping: RenderMapping | None = None,
    generation: str | None = None,
    revision: int | None = None,
    identify_active: bool = False,
    presentation_active: bool = False,
) -> RenderStatus:
    """Module-level :meth:`RenderRegistry.project` on the default registry."""
    return registry.project(
        device_id,
        now_mono=now_mono,
        online=online,
        caps=caps,
        mapping=mapping,
        generation=generation,
        revision=revision,
        identify_active=identify_active,
        presentation_active=presentation_active,
    )


def clear(device_id: str) -> bool:
    """Module-level :meth:`RenderRegistry.clear` on the default registry."""
    return registry.clear(device_id)


def reset() -> None:
    """Module-level :meth:`RenderRegistry.reset` on the default registry."""
    registry.reset()


def disconnect(device_id: str, connection_id: str) -> bool:
    """Module-level :meth:`RenderRegistry.disconnect` on the default registry."""
    return registry.disconnect(device_id, connection_id)


def replace(old_device_id: str, new_device_id: str) -> None:
    """Module-level :meth:`RenderRegistry.replace` on the default registry."""
    registry.replace(old_device_id, new_device_id)
