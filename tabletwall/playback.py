"""Pure hard-cut still playlist state (R3).

The model owns identity and transitions, not sockets or timers. A caller
injects the current server monotonic time, sends the frames the returned
actions describe, and re-checks the real clock at callback time. Every
occurrence is identified by playlist revision, item index and loop count, so
the same asset used twice is still two occurrences.

Only one pending preparation exists. A version advance supersedes it; the
currently displayed occurrence is kept until an accepted commit replaces it.
The displayed picture is never mutated by preparation or readiness.
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

    def as_frame(self) -> dict[str, Any]:
        return {
            "preparation_id": self.id,
            "version": self.version,
            "occurrence": self.occurrence.as_dict(),
            "asset": self.asset,
            "prepare_deadline_ms": self.deadline_ms,
            "effective_server_ms": self.effective_ms,
        }


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
    pending: Preparation | None = None
    target_ms: float = 0.0
    hold_deadline_ms: float | None = None
    held: bool = False
    missed: list[str] = field(default_factory=list)
    last_commit_ms: float | None = None

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


def validate_playlist(items: Any, *, loop: Any) -> list[dict[str, Any]]:
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
        dwell = item.get("dwell_ms")
        if type(dwell) is not int or not MIN_DWELL_MS <= dwell <= MAX_DWELL_MS:
            raise PlaybackError("dwell_ms must be 1000..600000")
        cleaned.append({"asset": asset, "dwell_ms": dwell})
    return cleaned


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
) -> Session:
    if not cohort:
        raise PlaybackError("a playback session needs at least one participant")
    session = Session(
        id=uuid.uuid4().hex,
        version=1,
        generation=generation,
        clock_epoch=clock_epoch,
        playlist_revision=playlist_revision,
        items=validate_playlist(items, loop=loop),
        loop=loop,
        cohort=sorted(set(cohort)),
        state="preparing",
        target_ms=now_ms + LEAD_MS,
    )
    session.pending = Preparation(
        id=uuid.uuid4().hex,
        version=session.version,
        occurrence=session.occurrence_at(0),
        asset=session.items[0]["asset"],
        created_ms=now_ms,
        deadline_ms=now_ms + PREPARE_TIMEOUT_MS,
        effective_ms=session.target_ms,
    )
    session.pending.leases = {
        device_id: Lease(device_id, connection_id=(connections or {}).get(device_id, ""))
        for device_id in session.cohort
    }
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
) -> bool:
    """Accept one readiness lease only when it covers the planned cut."""
    pending = session.pending
    if pending is None or session.state not in ("preparing", "armed"):
        return False
    if pending.id != preparation_id or pending.version != version:
        return False
    if device_id not in pending.leases:
        return False
    if not connection_id or connection_id != pending.leases[device_id].connection_id:
        return False
    if not clock_ok or not 0 < lease_ms <= LEASE_MS:
        return False
    if now_ms > pending.effective_ms:
        return False
    if evidence_seq <= pending.leases[device_id].evidence_seq:
        return False
    expiry = now_ms + lease_ms
    if expiry < pending.effective_ms:
        return False
    lease = pending.leases[device_id]
    lease.ready = True
    lease.evidence_seq = evidence_seq
    lease.lease_expires_ms = expiry
    lease.mapping_revision = mapping_revision
    lease.clock_ok = clock_ok
    return True


def _valid_leases(session: Session, now_ms: float) -> list[Lease]:
    pending = session.pending
    if pending is None:
        return []
    return [
        lease for lease in pending.leases.values()
        if lease.ready
        and lease.clock_ok
        and lease.lease_expires_ms >= pending.effective_ms
    ]


def tick(session: Session, now_ms: float) -> list[dict[str, Any]]:
    """Advance the model and return the actions to send.

    An action is ``{"type": "commit", ...}`` or a hold status. The caller
    must re-check the real clock immediately before sending a commit.
    """
    if session.state not in ("preparing", "armed", "playing"):
        return []
    pending = session.pending
    if pending is None:
        return []
    if pending.effective_ms - now_ms > LEAD_MS:
        return []

    valid = _valid_leases(session, now_ms)
    if len(valid) == len(session.cohort):
        return _commit(session, valid, pending.effective_ms, now_ms)

    if now_ms < pending.effective_ms:
        return []

    if not session.held:
        session.held = True
        session.state = "armed"
        session.hold_deadline_ms = min(
            pending.effective_ms + min(session.dwell_ms() / 2, HOLD_CAP_MS),
            pending.deadline_ms,
        )
        return [{"type": "hold", "deadline_ms": session.hold_deadline_ms,
                 "missing": sorted(set(session.cohort) - {lease.device_id for lease in valid})}]

    if session.hold_deadline_ms is not None and now_ms >= session.hold_deadline_ms:
        if not valid:
            session.state = "failed"
            return [{"type": "failed", "reason": "no participant became ready"}]
        missed = sorted(set(session.cohort) - {lease.device_id for lease in valid})
        session.missed.extend(missed)
        committed = _commit(session, valid, now_ms + LEAD_MS, now_ms)
        for action in committed:
            if action["type"] == "commit":
                action["missed"] = missed
        return committed
    return []


def _commit(
    session: Session, leases: list[Lease], effective_ms: float, now_ms: float
) -> list[dict[str, Any]]:
    pending = session.pending
    assert pending is not None
    session.version += 1
    session.current = pending.occurrence
    session.state = "playing"
    session.last_commit_ms = now_ms
    session.held = False
    session.hold_deadline_ms = None
    commit = {
        "type": "commit",
        "version": session.version,
        "prepared_at_version": pending.version,
        "preparation_id": pending.id,
        "occurrence": pending.occurrence.as_dict(),
        "asset": pending.asset,
        "effective_server_ms": effective_ms,
        "devices": [lease.device_id for lease in leases],
    }
    session.index = pending.occurrence.item_index
    session.loop_count = pending.occurrence.loop
    next_step = session.next_index()
    session.pending = None
    if next_step is None:
        session.state = "stopped"
        return [commit]
    index, loop_count = next_step
    session.index, session.loop_count = index, loop_count
    occurrence = session.occurrence_at(index)
    dwell = int(session.items[index]["dwell_ms"])
    session.pending = Preparation(
        id=uuid.uuid4().hex,
        version=session.version,
        occurrence=occurrence,
        asset=session.items[index]["asset"],
        created_ms=now_ms,
        deadline_ms=now_ms + PREPARE_TIMEOUT_MS,
        effective_ms=effective_ms + dwell,
    )
    session.pending.leases = {
        device_id: Lease(
            device_id,
            pending.leases[device_id].connection_id
            if device_id in pending.leases else "",
        )
        for device_id in session.cohort
    }
    return [commit]


def pause(session: Session, now_ms: float) -> int | None:
    """Freeze at the current occurrence; return the effective position."""
    if session.current is None:
        return None
    session.version += 1
    session.pending = None
    session.held = False
    session.hold_deadline_ms = None
    session.state = "paused"
    return session.current.item_index


def stop(session: Session, now_ms: float) -> None:
    session.version += 1
    session.pending = None
    session.held = False
    session.hold_deadline_ms = None
    session.state = "stopped"


def step(session: Session, delta: int, now_ms: float) -> Preparation:
    """Next/previous creates a new version and a fresh preparation."""
    if not session.items:
        raise PlaybackError("playlist is empty")
    connections = {
        device_id: lease.connection_id
        for device_id, lease in (session.pending.leases.items() if session.pending else [])
    }
    index = (session.index + delta) % len(session.items)
    if delta > 0 and index == 0:
        session.loop_count += 1
    session.index = index
    session.version += 1
    session.state = "preparing"
    session.pending = Preparation(
        id=uuid.uuid4().hex,
        version=session.version,
        occurrence=session.occurrence_at(index),
        asset=session.items[index]["asset"],
        created_ms=now_ms,
        deadline_ms=now_ms + PREPARE_TIMEOUT_MS,
        effective_ms=now_ms + LEAD_MS,
    )
    session.pending.leases = {
        device_id: Lease(device_id, connections.get(device_id, ""))
        for device_id in session.cohort
    }
    return session.pending
