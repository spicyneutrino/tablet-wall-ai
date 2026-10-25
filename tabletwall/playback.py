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
        return frame


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
    playing: list[str] = field(default_factory=list)
    samples: dict[str, dict[str, Any]] = field(default_factory=dict)

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
    if pending is None or session.state not in ("preparing", "armed", "playing"):
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
        if not _video_ready(pending.media, evidence):
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


def _video_ready(media: dict[str, Any], video: dict[str, Any] | None) -> bool:
    if video is None:
        return False
    required = min(int(media["buffer_goal_ms"]), int(media["duration_ms"]))
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


def tick(session: Session, now_ms: float) -> list[dict[str, Any]]:
    """Advance the model and return the actions to send.

    An action is ``commit``, ``hold``, ``reanchor``, ``blocked`` or ``failed``.
    The caller must re-check the real clock immediately before sending a
    commit. A cut whose effective time already passed is re-anchored forward;
    it is never committed in the past.
    """
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
    }
    if pending.media is not None:
        commit["start_media_ms"] = 0
    session.current_media = pending.media
    session.playing = [lease.device_id for lease in leases]
    session.samples = {}
    session.index = occurrence.item_index
    session.loop_count = occurrence.loop
    next_step = session.next_index()
    session.pending = None
    if next_step is None:
        session.final = True
        session.state = FINAL
        return [commit]
    session.final = False
    index, loop_count = next_step
    next_occurrence = Occurrence(session.playlist_revision, index, loop_count)
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
    _cancel_future_commit(session, now_ms)
    occurrence = _target_occurrence(session, delta, now_ms)
    session.version += 1
    session.state = "preparing"
    session.blocked_reason = None
    session.missed = []
    session.paused_at_ms = None
    session.final = False
    session.pending = _preparation(
        session, occurrence, now_ms, now_ms + LEAD_MS, connections
    )
    return session.pending


def retry(
    session: Session, now_ms: float, connections: dict[str, str] | None = None
) -> Preparation:
    """Leave ``blocked``: a new version of the same blocked occurrence."""
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
