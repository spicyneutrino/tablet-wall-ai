"""Hard-cut still playlist state (R3).

The model owns identity and transitions, not sockets or timers. A caller
injects the current server monotonic time, sends the frames the returned
actions describe, and re-checks the real clock at callback time. Every
occurrence is identified by playlist revision, item index and loop count, so
the same asset used twice is still two occurrences.

Only one pending preparation exists. A version advance supersedes it; the
currently displayed occurrence is kept until an accepted commit replaces it.
The displayed picture is never mutated by preparation or readiness.

``current`` is the last committed occurrence and may still be in the future.
``displayed`` is what is on the glass: the previous occurrence until the
committed one's effective time, then the committed one. A command issued
before that time cancels the armed commit and acts on ``displayed``.

``policy`` is ``online`` (a bounded hold, then a partial commit that records
the miss) or ``strict`` (never commit with a required member missing: at the
preparation deadline the session is ``blocked`` until Retry or Stop). The
caller supplies the required cohort; a strict cohort includes offline slots.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

LEAD_MS = 1000
PREPARE_TIMEOUT_MS = 30_000
LEASE_MS = 2000
MIN_DWELL_MS = 1000
MAX_DWELL_MS = 600_000
MAX_ITEMS = 64
HOLD_CAP_MS = 5000
POLICIES = ("online", "strict")
FINAL = "final"
STALE_SAMPLE_MS = 3000
RECOVERY_ATTEMPTS = 3
FAULT_REASONS = ("stalled", "play_failed", "buffer_lost")
RECOVERY_TIMEOUT_REASON = "recovery_timeout"
RECOVERY_FAILED_REASON = "recovery_failed"
RECOVERY_LIMIT_REASON = "recovery attempt limit reached"


class PlaybackError(ValueError):
    """An invalid playlist or a transition the session cannot make."""


@dataclass(frozen=True)
class Occurrence:
    playlist_revision: int
    item_index: int
    loop: int

    def as_dict(self) -> dict[str, int]:
        return {
            "playlist_revision": self.playlist_revision,
            "item_index": self.item_index,
            "loop": self.loop,
        }


@dataclass
class Lease:
    device_id: str
    connection_id: str
    ready: bool = False
    evidence_seq: int = 0
    lease_expires_ms: float = 0.0
    mapping_revision: int = 0
    clock_ok: bool = False
    video: dict[str, Any] | None = None


@dataclass
class Preparation:
    id: str
    version: int
    occurrence: Occurrence
    asset: str
    created_ms: float
    deadline_ms: float
    effective_ms: float
    leases: dict[str, Lease] = field(default_factory=dict)
    media: dict[str, Any] | None = None
    start_media_ms: int = 0
    recovery_id: str | None = None

    def as_frame(self) -> dict[str, Any]:
        frame = {
            "preparation_id": self.id,
            "version": self.version,
            "occurrence": self.occurrence.as_dict(),
            "asset": self.asset,
            "prepare_deadline_ms": self.deadline_ms,
            "effective_server_ms": self.effective_ms,
        }
        if self.media is not None:
            frame["media"] = self.media
            frame["start_media_ms"] = self.start_media_ms
        return frame


@dataclass
class Recovery:
    """One bounded group re-preparation of a playing video occurrence."""

    id: str
    occurrence: Occurrence
    position_ms: int
    reason: str
    device_id: str
    started_ms: float
    deadline_ms: float
    attempts: int
    degraded_since_ms: float
    missing: list[str] = field(default_factory=list)
    state: str = "preparing"


@dataclass
class Session:
    id: str
    version: int
    generation: str
    clock_epoch: str
    playlist_revision: int
    items: list[dict[str, Any]]
    loop: bool
    cohort: list[str]
    state: str = "preparing"
    index: int = 0
    loop_count: int = 0
    current: Occurrence | None = None
    displayed: Occurrence | None = None
    previous: Occurrence | None = None
    current_effective_ms: float | None = None
    previous_effective_ms: float | None = None
    pending: Preparation | None = None
    target_ms: float = 0.0
    hold_deadline_ms: float | None = None
    held: bool = False
    missed: list[str] = field(default_factory=list)
    last_commit_ms: float | None = None
    policy: str = "online"
    blocked_reason: str | None = None
    paused_at_ms: float | None = None
    final: bool = False
    videos: dict[str, int] = field(default_factory=dict)
    current_media: dict[str, Any] | None = None
    current_start_media_ms: int = 0
    current_connections: dict[str, str] = field(default_factory=dict)
    playing: list[str] = field(default_factory=list)
    samples: dict[str, dict[str, Any]] = field(default_factory=dict)
    recovery: Recovery | None = None
    recovery_occurrence: Occurrence | None = None
    recovery_attempts: int = 0

    def lineage(self) -> dict[str, Any]:
        return {
            "session_id": self.id,
            "version": self.version,
            "generation": self.generation,
            "clock_epoch": self.clock_epoch,
        }

    def occurrence_at(self, index: int) -> Occurrence:
        if not 0 <= index < len(self.items):
            raise PlaybackError("occurrence index is outside the playlist")
        return Occurrence(self.playlist_revision, index, self.loop_count)

    def next_index(self) -> tuple[int, int] | None:
        index = self.index + 1
        loop_count = self.loop_count
        if index >= len(self.items):
            if not self.loop:
                return None
            index = 0
            loop_count += 1
        return index, loop_count

    def dwell_ms(self) -> int:
        return int(self.items[self.index]["dwell_ms"])


def refresh_display(session: Session, now_ms: float) -> None:
    """Promote the committed occurrence to ``displayed`` once its time passed."""
    if (
        session.current is not None
        and session.current_effective_ms is not None
        and now_ms >= session.current_effective_ms
    ):
        session.displayed = session.current


def _cancel_future_commit(session: Session, now_ms: float) -> None:
    """A command before a committed cut acts on what is actually on the glass."""
    refresh_display(session, now_ms)
    if (
        session.current is not None
        and session.current_effective_ms is not None
        and now_ms < session.current_effective_ms
    ):
        session.current = session.previous
        session.current_effective_ms = session.previous_effective_ms
        session.previous = None
        session.previous_effective_ms = None
        session.displayed = session.current
        session.final = False
        if session.current is not None:
            session.index = session.current.item_index
            session.loop_count = session.current.loop


def validate_playlist(
    items: Any, *, loop: Any, videos: dict[str, int] | None = None
) -> list[dict[str, Any]]:
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
        raise PlaybackError("playlist must contain 1..64 items")
    if not isinstance(loop, bool):
        raise PlaybackError("loop must be a boolean")
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            raise PlaybackError("playlist item must be an object")
        asset = item.get("asset")
        if not isinstance(asset, str) or not asset.startswith("sha256:"):
            raise PlaybackError("playlist asset must be a content id")
        if videos is not None and asset in videos:
            dwell = videos[asset]
            if type(dwell) is not int or not MIN_DWELL_MS <= dwell <= MAX_DWELL_MS:
                raise PlaybackError("video duration must be 1000..600000 ms")
            cleaned.append({"asset": asset, "dwell_ms": dwell})
            continue
        dwell = item.get("dwell_ms")
        if type(dwell) is not int or not MIN_DWELL_MS <= dwell <= MAX_DWELL_MS:
            raise PlaybackError("dwell_ms must be 1000..600000")
        cleaned.append({"asset": asset, "dwell_ms": dwell})
    return cleaned


def _preparation(
    session: Session,
    occurrence: Occurrence,
    now_ms: float,
    effective_ms: float,
    connections: dict[str, str] | None,
    *,
    start_media_ms: int = 0,
    recovery_id: str | None = None,
) -> Preparation:
    """The one place a preparation is built, so no path forgets a field."""
    media = None
    if occurrence.item_index < len(session.items):
        asset = session.items[occurrence.item_index]["asset"]
        if asset in session.videos:
            media = {
                "kind": "video",
                "duration_ms": session.videos[asset],
                "buffer_goal_ms": 5000,
                "start_lead_ms": LEAD_MS,
                "prepare_timeout_ms": PREPARE_TIMEOUT_MS,
            }
    timeout = int(media["prepare_timeout_ms"]) if media else PREPARE_TIMEOUT_MS
    preparation = Preparation(
        id=uuid.uuid4().hex,
        version=session.version,
        occurrence=occurrence,
        asset=session.items[occurrence.item_index]["asset"],
        created_ms=now_ms,
        deadline_ms=effective_ms + timeout,
        effective_ms=effective_ms,
        media=media,
        start_media_ms=int(start_media_ms),
        recovery_id=recovery_id,
    )
    preparation.leases = {
        device_id: Lease(device_id, (connections or {}).get(device_id, ""))
        for device_id in session.cohort
    }
    return preparation


def start(
    items: list[dict[str, Any]],
    loop: bool,
    cohort: list[str],
    now_ms: float,
    *,
    generation: str,
    clock_epoch: str,
    connections: dict[str, str] | None = None,
    playlist_revision: int = 1,
    policy: str = "online",
    videos: dict[str, int] | None = None,
) -> Session:
    if not cohort:
        raise PlaybackError("a playback session needs at least one participant")
    if policy not in POLICIES:
        raise PlaybackError('policy must be "online" or "strict"')
    session = Session(
        id=uuid.uuid4().hex,
        version=1,
        generation=generation,
        clock_epoch=clock_epoch,
        playlist_revision=playlist_revision,
        items=validate_playlist(items, loop=loop, videos=videos),
        loop=loop,
        cohort=sorted(set(cohort)),
        state="preparing",
        target_ms=now_ms + LEAD_MS,
        policy=policy,
        videos=dict(videos or {}),
    )
    session.pending = _preparation(
        session, session.occurrence_at(0), now_ms, session.target_ms, connections
    )
    return session


def accept_ready(
    session: Session,
    *,
    device_id: str,
    connection_id: str,
    preparation_id: str,
    version: int,
    evidence_seq: int,
    mapping_revision: int,
    clock_ok: bool,
    lease_ms: int,
    now_ms: float,
    decoded: bool = False,
    occurrence: Any = None,
    expected_mapping: int | None = None,
    video: Any = None,
) -> bool:
    """Accept one readiness lease only when it covers the planned cut.

    ``decoded`` is required for a still. A video preparation passes its
    evidence in ``video`` instead. ``expected_mapping`` is the calibration
    revision the preparation was built with; a different report is stale.
    """
    pending = session.pending
    if pending is None or session.state not in ("preparing", "armed", "playing", "recovering"):
        return False
    if pending.id != preparation_id or pending.version != version:
        return False
    if device_id not in pending.leases:
        return False
    if not connection_id or connection_id != pending.leases[device_id].connection_id:
        return False
    if occurrence is not None and occurrence != pending.occurrence.as_dict():
        return False
    if expected_mapping is not None and mapping_revision != expected_mapping:
        return False
    if not clock_ok or not 0 < lease_ms <= LEASE_MS:
        return False
    if evidence_seq <= pending.leases[device_id].evidence_seq:
        return False
    expiry = now_ms + lease_ms
    if expiry < pending.effective_ms:
        return False
    lease = pending.leases[device_id]
    lease.evidence_seq = evidence_seq
    lease.mapping_revision = mapping_revision
    lease.clock_ok = clock_ok
    lease.video = video
    if pending.media is not None:
        evidence = _video_evidence(video)
        lease.video = evidence
        if not _video_ready(pending.media, evidence, pending.start_media_ms):
            lease.ready = False
            return False
    elif not decoded:
        lease.ready = False
        return False
    lease.ready = True
    lease.lease_expires_ms = expiry
    return True


def _bounded(value: Any, low: float, high: float) -> bool:
    return type(value) in (int, float) and low <= value <= high


def _video_evidence(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    metadata, seeked = raw.get("metadata"), raw.get("seeked")
    buffered, play_ok = raw.get("buffered_ahead_ms"), raw.get("play_ok")
    if type(metadata) is not bool or type(seeked) is not bool:
        return None
    if type(buffered) is not int or not 0 <= buffered <= MAX_DWELL_MS:
        return None
    if not isinstance(play_ok, str) or play_ok not in ("yes", "needs_gesture", "no"):
        return None
    return {
        "metadata": metadata,
        "seeked": seeked,
        "buffered_ahead_ms": buffered,
        "play_ok": play_ok,
        "rvfc": raw.get("rvfc") is True,
    }


def _video_ready(
    media: dict[str, Any], video: dict[str, Any] | None, start_media_ms: int = 0
) -> bool:
    if video is None:
        return False
    remaining = max(0, int(media["duration_ms"]) - int(start_media_ms))
    required = min(int(media["buffer_goal_ms"]), remaining)
    return (
        video["metadata"]
        and video["seeked"]
        and video["play_ok"] == "yes"
        and video["buffered_ahead_ms"] >= required
    )


def _valid_leases(session: Session, now_ms: float, cut_ms: float) -> list[Lease]:
    pending = session.pending
    if pending is None:
        return []
    return [
        lease for lease in pending.leases.values()
        if lease.ready
        and lease.clock_ok
        and lease.lease_expires_ms >= cut_ms
        and lease.lease_expires_ms > now_ms
    ]


def _pending_connections(session: Session) -> dict[str, str]:
    if session.pending is None:
        return {}
    return {
        device_id: lease.connection_id
        for device_id, lease in session.pending.leases.items()
    }


def _recovery_attempts_for(session: Session, occurrence: Occurrence) -> int:
    if session.recovery_occurrence == occurrence:
        return session.recovery_attempts
    return 0


def _playhead_ms(session: Session, now_ms: float) -> int:
    """The committed video position at ``now_ms``, bounded by its duration."""
    duration = int(session.current_media["duration_ms"])
    elapsed = 0.0
    if session.current_effective_ms is not None:
        elapsed = max(0.0, now_ms - session.current_effective_ms)
    return int(min(duration, session.current_start_media_ms + elapsed))


def stalled_device(session: Session, now_ms: float) -> tuple[str, int] | None:
    """The first playing device with no accepted sample for over 3 seconds.

    Returns ``(device_id, position_ms)``; the position is the occurrence's
    playhead, so the recovery re-prepares from where the glass should be.
    """
    if session.state not in ("playing", FINAL):
        return None
    if session.current is None or session.current_media is None:
        return None
    if session.current_effective_ms is None or now_ms < session.current_effective_ms:
        return None
    duration = int(session.current_media["duration_ms"])
    position = _playhead_ms(session, now_ms)
    if position >= duration - 250:
        # The clip reached its natural end; a final occurrence has no next
        # cut, and a non-final one is already being prepared for the boundary.
        return None
    for device_id in sorted(session.playing):
        sample = session.samples.get(device_id)
        last_ms = sample["at_ms"] if sample is not None else session.current_effective_ms
        if now_ms - last_ms > STALE_SAMPLE_MS:
            return device_id, position
    return None


def _start_recovery(
    session: Session,
    occurrence: Occurrence,
    position_ms: int,
    reason: str,
    device_id: str,
    now_ms: float,
    connections: dict[str, str] | None = None,
) -> Preparation:
    """Freeze the cohort and re-prepare the current occurrence at a position."""
    if connections is None:
        connections = dict(session.current_connections)
        connections.update(_pending_connections(session))
    recovery_id = uuid.uuid4().hex
    attempts = _recovery_attempts_for(session, occurrence) + 1
    session.version += 1
    session.state = "recovering"
    session.held = False
    session.hold_deadline_ms = None
    session.blocked_reason = None
    session.missed = []
    session.final = False
    pending = _preparation(
        session, occurrence, now_ms, now_ms + LEAD_MS, connections,
        start_media_ms=position_ms, recovery_id=recovery_id,
    )
    session.pending = pending
    session.recovery = Recovery(
        id=recovery_id,
        occurrence=occurrence,
        position_ms=int(position_ms),
        reason=reason,
        device_id=device_id,
        started_ms=now_ms,
        deadline_ms=pending.deadline_ms,
        attempts=attempts,
        degraded_since_ms=now_ms,
    )
    session.recovery_occurrence = occurrence
    session.recovery_attempts = attempts
    return pending


def _recovery_failure(
    session: Session,
    occurrence: Occurrence,
    position_ms: int,
    reason: str,
    device_id: str,
    now_ms: float,
) -> None:
    """The attempt cap is spent: stop preparing and expose the failed state."""
    attempts = _recovery_attempts_for(session, occurrence) + 1
    state = "blocked" if session.policy == "strict" else "failed"
    session.pending = None
    session.state = state
    session.held = False
    session.hold_deadline_ms = None
    session.final = False
    session.missed = []
    session.recovery = Recovery(
        id=uuid.uuid4().hex,
        occurrence=occurrence,
        position_ms=int(position_ms),
        reason=reason,
        device_id=device_id,
        started_ms=now_ms,
        deadline_ms=now_ms,
        attempts=attempts,
        degraded_since_ms=now_ms,
        state=state,
    )
    session.recovery_occurrence = occurrence
    session.recovery_attempts = attempts
    session.blocked_reason = (
        RECOVERY_LIMIT_REASON if state == "blocked" else RECOVERY_FAILED_REASON
    )


def accept_fault(
    session: Session,
    *,
    device_id: str,
    payload: Any,
    now_ms: float,
    connections: dict[str, str] | None = None,
) -> str:
    """Accept one ``video_fault`` and start its recovery.

    Returns ``"preparing"`` when a recovery preparation was built,
    ``"blocked"``/``"failed"`` when the occurrence has spent its attempts, and
    ``"ignored"`` for a duplicate, stale or malformed fault. The frame is
    accepted only from a playing device, for the current occurrence at the
    current version, from ``position_ms`` inside the clip.
    """
    occurrence = session.current
    if (
        session.state not in ("playing", FINAL)
        or occurrence is None
        or session.current_media is None
        or device_id not in session.playing
        or not isinstance(payload, dict)
    ):
        return "ignored"
    if payload.get("session_id") != session.id:
        return "ignored"
    version = payload.get("version")
    if type(version) is not int or version != session.version:
        return "ignored"
    if payload.get("occurrence") != occurrence.as_dict():
        return "ignored"
    if session.current_effective_ms is None or now_ms < session.current_effective_ms:
        # The occurrence is armed but not on the glass yet; a fault cannot
        # describe a picture the cohort has not started.
        return "ignored"
    reason = payload.get("reason")
    if not isinstance(reason, str) or reason not in FAULT_REASONS:
        return "ignored"
    duration = int(session.current_media["duration_ms"])
    position_ms = payload.get("position_ms")
    if not _bounded(position_ms, 0, duration - 1):
        return "ignored"
    if _recovery_attempts_for(session, occurrence) >= RECOVERY_ATTEMPTS:
        _recovery_failure(
            session, occurrence, position_ms, reason, device_id, now_ms
        )
        return session.state
    _start_recovery(
        session, occurrence, position_ms, reason, device_id, now_ms, connections
    )
    return "preparing"


def _recovery_tick(session: Session, now_ms: float) -> list[dict[str, Any]]:
    """Commit a recovery only with the whole frozen cohort, else fail at the deadline."""
    recovery = session.recovery
    pending = session.pending
    if recovery is None or pending is None:
        return []
    valid = _valid_leases(session, now_ms, pending.effective_ms)
    if len(valid) == len(session.cohort):
        cut = pending.effective_ms
        if now_ms >= cut:
            cut = now_ms + LEAD_MS
            valid = _valid_leases(session, now_ms, cut)
        if len(valid) == len(session.cohort):
            return _commit(session, valid, cut, now_ms)
    missing = sorted(set(session.cohort) - {lease.device_id for lease in valid})
    if now_ms < pending.deadline_ms:
        return []
    recovery.missing = missing
    session.missed = missing
    if session.policy == "strict":
        session.state = "blocked"
        recovery.state = "blocked"
        session.blocked_reason = RECOVERY_TIMEOUT_REASON
        return [{
            "type": "blocked", "reason": RECOVERY_TIMEOUT_REASON, "missing": missing,
        }]
    session.state = "failed"
    recovery.state = "failed"
    session.blocked_reason = RECOVERY_FAILED_REASON
    return [{"type": "failed", "reason": RECOVERY_FAILED_REASON}]


def tick(session: Session, now_ms: float) -> list[dict[str, Any]]:
    """Advance the model and return the actions to send.

    An action is ``commit``, ``hold``, ``reanchor``, ``recover``, ``blocked``
    or ``failed``. The caller must re-check the real clock immediately before
    sending a commit. A cut whose effective time already passed is re-anchored
    forward; it is never committed in the past.
    """
    if session.state in ("playing", FINAL):
        stalled = stalled_device(session, now_ms)
        if stalled is not None:
            occurrence = session.current
            assert occurrence is not None
            device_id, position_ms = stalled
            if _recovery_attempts_for(session, occurrence) >= RECOVERY_ATTEMPTS:
                _recovery_failure(
                    session, occurrence, position_ms, "stalled", device_id, now_ms
                )
                if session.state == "blocked":
                    return [{
                        "type": "blocked", "reason": RECOVERY_LIMIT_REASON,
                        "missing": [],
                    }]
                return [{"type": "failed", "reason": RECOVERY_FAILED_REASON}]
            _start_recovery(
                session, occurrence, position_ms, "stalled", device_id, now_ms
            )
            return [{
                "type": "recover",
                "occurrence": occurrence.as_dict(),
                "position_ms": position_ms,
                "reason": "stalled",
                "device_id": device_id,
                "version": session.version,
            }]
    if session.state == "recovering":
        return _recovery_tick(session, now_ms)
    if session.state not in ("preparing", "armed", "playing"):
        return []
    pending = session.pending
    if pending is None:
        return []
    refresh_display(session, now_ms)
    if pending.effective_ms - now_ms > LEAD_MS:
        return []

    valid = _valid_leases(session, now_ms, pending.effective_ms)
    if len(valid) == len(session.cohort):
        cut = pending.effective_ms
        if now_ms >= cut:
            cut = now_ms + LEAD_MS
            valid = _valid_leases(session, now_ms, cut)
        if len(valid) == len(session.cohort):
            return _commit(session, valid, cut, now_ms)

    if session.policy == "strict":
        if now_ms >= pending.deadline_ms:
            return _strict_wait(session, pending, valid, now_ms)
        if now_ms >= pending.effective_ms:
            pending.effective_ms = now_ms + LEAD_MS
            session.held = False
            session.hold_deadline_ms = None
            return [{
                "type": "reanchor",
                "effective_server_ms": pending.effective_ms,
                "occurrence": pending.occurrence.as_dict(),
                "version": pending.version,
            }]
        return []

    if now_ms < pending.effective_ms:
        return []

    if not session.held:
        session.held = True
        session.state = "armed"
        dwell = int(session.items[pending.occurrence.item_index]["dwell_ms"])
        session.hold_deadline_ms = now_ms + min(dwell / 2, HOLD_CAP_MS)
        return [{
            "type": "hold",
            "deadline_ms": session.hold_deadline_ms,
            "missing": sorted(set(session.cohort) - {lease.device_id for lease in valid}),
        }]

    if session.hold_deadline_ms is not None and now_ms >= session.hold_deadline_ms:
        cut = now_ms + LEAD_MS
        valid = _valid_leases(session, now_ms, cut)
        if not valid:
            session.state = "failed"
            return [{"type": "failed", "reason": "no participant became ready"}]
        missed = sorted(set(session.cohort) - {lease.device_id for lease in valid})
        session.missed.extend(missed)
        actions = _commit(session, valid, cut, now_ms)
        for action in actions:
            if action["type"] == "commit":
                action["missed"] = missed
        return actions
    return []


def _strict_wait(
    session: Session, pending: Preparation, valid: list[Lease], now_ms: float
) -> list[dict[str, Any]]:
    """Strict waits for the deadline, then blocks with the missing names."""
    if now_ms < pending.deadline_ms:
        return []
    missing = sorted(set(session.cohort) - {lease.device_id for lease in valid})
    session.state = "blocked"
    session.blocked_reason = "preparation deadline passed before the cohort was ready"
    session.missed = missing
    return [{"type": "blocked", "reason": session.blocked_reason, "missing": missing}]


def _commit(
    session: Session, leases: list[Lease], effective_ms: float, now_ms: float
) -> list[dict[str, Any]]:
    pending = session.pending
    assert pending is not None
    occurrence = pending.occurrence
    session.version += 1
    session.previous = session.current
    session.previous_effective_ms = session.current_effective_ms
    session.current = occurrence
    session.current_effective_ms = effective_ms
    session.displayed = occurrence if now_ms >= effective_ms else session.previous
    session.state = "playing"
    session.last_commit_ms = now_ms
    session.held = False
    session.hold_deadline_ms = None
    session.blocked_reason = None
    commit = {
        "type": "commit",
        "version": session.version,
        "prepared_at_version": pending.version,
        "preparation_id": pending.id,
        "occurrence": occurrence.as_dict(),
        "asset": pending.asset,
        "effective_server_ms": effective_ms,
        "devices": [lease.device_id for lease in leases],
        "connections": {lease.device_id: lease.connection_id for lease in leases},
    }
    if pending.media is not None:
        commit["start_media_ms"] = pending.start_media_ms
    session.current_media = pending.media
    session.current_start_media_ms = pending.start_media_ms
    session.current_connections = {
        device_id: lease.connection_id
        for device_id, lease in pending.leases.items()
    }
    session.playing = [lease.device_id for lease in leases]
    session.samples = {}
    session.index = occurrence.item_index
    session.loop_count = occurrence.loop
    next_step = session.next_index()
    session.pending = None
    recovery = session.recovery
    if (
        pending.recovery_id is not None
        and recovery is not None
        and recovery.id == pending.recovery_id
    ):
        recovery.state = "playing"
        recovery.missing = []
    else:
        session.recovery = None
        session.recovery_occurrence = None
        session.recovery_attempts = 0
    if next_step is None:
        session.final = True
        session.state = FINAL
        return [commit]
    session.final = False
    index, loop_count = next_step
    next_occurrence = Occurrence(session.playlist_revision, index, loop_count)
    if pending.media is not None:
        dwell = max(0, int(pending.media["duration_ms"]) - pending.start_media_ms)
    else:
        dwell = int(session.items[occurrence.item_index]["dwell_ms"])
    session.pending = _preparation(
        session, next_occurrence, now_ms, effective_ms + dwell,
        {device_id: lease.connection_id for device_id, lease in pending.leases.items()},
    )
    return [commit]


def pause(session: Session, now_ms: float) -> int | None:
    """Freeze at the displayed occurrence; cancel an armed future commit."""
    _cancel_future_commit(session, now_ms)
    session.version += 1
    session.pending = None
    session.held = False
    session.hold_deadline_ms = None
    session.blocked_reason = None
    session.recovery = None
    session.recovery_occurrence = None
    session.recovery_attempts = 0
    session.state = "paused"
    session.paused_at_ms = now_ms
    return session.displayed.item_index if session.displayed is not None else None


def resume(
    session: Session, now_ms: float, connections: dict[str, str] | None = None
) -> Preparation:
    """Restart the displayed occurrence at a new anchor."""
    if session.state != "paused":
        raise PlaybackError("only a paused session can resume")
    occurrence = session.displayed or session.current
    if occurrence is None and session.pending is not None:
        occurrence = session.pending.occurrence
    if occurrence is None:
        occurrence = session.occurrence_at(session.index)
    session.version += 1
    session.state = "preparing"
    session.blocked_reason = None
    session.missed = []
    session.paused_at_ms = None
    session.final = False
    session.recovery = None
    session.recovery_occurrence = None
    session.recovery_attempts = 0
    session.pending = _preparation(
        session, occurrence, now_ms, now_ms + LEAD_MS, connections
    )
    return session.pending


def stop(session: Session, now_ms: float) -> None:
    session.version += 1
    session.pending = None
    session.held = False
    session.hold_deadline_ms = None
    session.state = "stopped"
    session.final = False
    session.paused_at_ms = None
    session.recovery = None
    session.recovery_occurrence = None
    session.recovery_attempts = 0


def _target_occurrence(
    session: Session, delta: int, now_ms: float
) -> Occurrence:
    refresh_display(session, now_ms)
    base = session.displayed
    if base is None and session.current is not None:
        base = session.current
    if base is None and session.pending is not None:
        base = session.pending.occurrence
    if base is None:
        base = session.occurrence_at(0)
    index, loop = base.item_index + delta, base.loop
    if index < 0:
        if not session.loop:
            raise PlaybackError("there is no previous item")
        index, loop = len(session.items) - 1, max(0, loop - 1)
    elif index >= len(session.items):
        if not session.loop:
            raise PlaybackError("there is no next item")
        index, loop = 0, loop + 1
    return Occurrence(session.playlist_revision, index, loop)


def step(
    session: Session,
    delta: int,
    now_ms: float,
    connections: dict[str, str] | None = None,
) -> Preparation:
    """Next/previous creates a new version and a fresh preparation.

    Nothing active changes until that preparation commits. An armed future
    commit is cancelled; the command acts on the displayed item.
    """
    if not session.items:
        raise PlaybackError("playlist is empty")
    occurrence = _target_occurrence(session, delta, now_ms)
    _cancel_future_commit(session, now_ms)
    session.version += 1
    session.state = "preparing"
    session.blocked_reason = None
    session.missed = []
    session.paused_at_ms = None
    session.final = False
    session.recovery = None
    session.recovery_occurrence = None
    session.recovery_attempts = 0
    session.pending = _preparation(
        session, occurrence, now_ms, now_ms + LEAD_MS, connections
    )
    return session.pending


def retry(
    session: Session, now_ms: float, connections: dict[str, str] | None = None
) -> Preparation:
    """Leave ``blocked``: a new version of the same blocked occurrence."""
    recovery = session.recovery
    if session.state == "blocked" and recovery is not None and recovery.state == "blocked":
        occurrence = recovery.occurrence
        previous = (
            {
                device_id: lease.connection_id
                for device_id, lease in session.pending.leases.items()
            }
            if session.pending is not None
            else dict(session.current_connections)
        )
        merged = dict(previous)
        merged.update(connections or {})
        session.version += 1
        session.state = "recovering"
        session.blocked_reason = None
        session.missed = []
        session.final = False
        # An operator Retry after the automatic cap gets one fresh episode;
        # another automatic fault on the same occurrence is still bounded.
        recovery.attempts = (
            1 if recovery.attempts >= RECOVERY_ATTEMPTS else recovery.attempts + 1
        )
        recovery.started_ms = now_ms
        recovery.state = "preparing"
        recovery.missing = []
        session.recovery_occurrence = occurrence
        session.recovery_attempts = recovery.attempts
        pending = _preparation(
            session, occurrence, now_ms, now_ms + LEAD_MS, merged,
            start_media_ms=recovery.position_ms, recovery_id=recovery.id,
        )
        recovery.deadline_ms = pending.deadline_ms
        session.pending = pending
        return pending
    if session.state != "blocked" or session.pending is None:
        raise PlaybackError("only a blocked session can retry")
    occurrence = session.pending.occurrence
    previous = {
        device_id: lease.connection_id for device_id, lease in session.pending.leases.items()
    }
    merged = dict(previous)
    merged.update(connections or {})
    session.version += 1
    session.state = "preparing"
    session.blocked_reason = None
    session.missed = []
    session.pending = _preparation(
        session, occurrence, now_ms, now_ms + LEAD_MS, merged
    )
    return session.pending


def recovery_status(session: Session, now_ms: float) -> dict[str, Any] | None:
    """The active or last recovery record, including its degraded interval."""
    recovery = session.recovery
    if recovery is None:
        return None
    end_ms = now_ms
    if recovery.state == "playing" and session.current_effective_ms is not None:
        end_ms = min(now_ms, session.current_effective_ms)
    return {
        "id": recovery.id,
        "occurrence": recovery.occurrence.as_dict(),
        "position_ms": recovery.position_ms,
        "reason": recovery.reason,
        "device_id": recovery.device_id,
        "attempts": recovery.attempts,
        "started_ms": recovery.started_ms,
        "deadline_ms": recovery.deadline_ms,
        "degraded_ms": max(0, round(end_ms - recovery.degraded_since_ms)),
        "state": recovery.state,
        "missing": sorted(recovery.missing),
    }


def video_status(session: Session, now_ms: float) -> dict[str, dict[str, Any]]:
    """Per-device latest drift reading, without readings older than 5 seconds."""
    return {
        device_id: {
            "drift_ms": sample["drift_ms"], "rate": sample["rate"],
            "source": sample["source"], "media_ms": sample["media_ms"],
            "age_ms": max(0, round(now_ms - sample["at_ms"])),
        }
        for device_id, sample in sorted(session.samples.items())
        if now_ms - sample["at_ms"] <= 5000
    }


SAMPLE_MIN_INTERVAL_MS = 1000
MAX_DRIFT_MS = 60_000
SAMPLE_SOURCES = ("rvfc", "time")


def accept_sample(
    session: Session, *, device_id: str, payload: Any, now_ms: float
) -> bool:
    """Keep the latest ``video_sample`` of a playing device, or refuse it.

    A sample must name the current socket's session, version and occurrence,
    come from a device that committed the clip, carry finite bounded numbers,
    and arrive at least one second after the previous accepted sample.
    """
    if (
        not isinstance(payload, dict)
        or session.state not in ("playing", "armed", FINAL)
        or session.current is None
        or session.current_media is None
        or device_id not in session.playing
    ):
        return False
    if payload.get("session_id") != session.id:
        return False
    version = payload.get("version")
    if type(version) is not int or version != session.version:
        return False
    if payload.get("occurrence") != session.current.as_dict():
        return False
    duration = int(session.current_media["duration_ms"])
    media_ms, target_ms = payload.get("media_ms"), payload.get("target_ms")
    drift, rate, source = payload.get("drift_ms"), payload.get("rate"), payload.get("source")
    if not (
        _bounded(media_ms, 0, duration + 1000)
        and _bounded(target_ms, 0, duration + 1000)
        and _bounded(drift, -MAX_DRIFT_MS, MAX_DRIFT_MS)
        and _bounded(rate, 0.5, 2.0)
        and isinstance(source, str)
        and source in SAMPLE_SOURCES
    ):
        return False
    previous = session.samples.get(device_id)
    if previous is not None and now_ms - previous["at_ms"] < SAMPLE_MIN_INTERVAL_MS:
        return False
    session.samples[device_id] = {
        "media_ms": media_ms, "target_ms": target_ms, "drift_ms": drift,
        "rate": rate, "source": source, "at_ms": now_ms,
    }
    return True
