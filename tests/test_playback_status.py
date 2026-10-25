"""Status and socket-disconnect evidence for an active playback session."""

import main
from tabletwall import playback

A = "sha256:" + "a" * 64
B = "sha256:" + "b" * 64
VIDEO_MS = 4000
VIDEO = {
    "metadata": True, "seeked": True, "buffered_ahead_ms": 5000,
    "play_ok": "yes", "rvfc": True,
}


def session():
    return playback.start(
        [{"asset": A, "dwell_ms": 5000}, {"asset": B, "dwell_ms": 5000}],
        False, ["dev-1", "dev-2"], 1000, generation="gen", clock_epoch="epoch",
        connections={"dev-1": "conn-dev-1", "dev-2": "conn-dev-2"},
        policy="strict",
    )


def video_session():
    """A strict session whose first video occurrence has committed."""
    s = playback.start(
        [{"asset": A, "dwell_ms": 1000}, {"asset": B, "dwell_ms": 5000}],
        False, ["dev-1", "dev-2"], 1000, generation="gen", clock_epoch="epoch",
        connections={"dev-1": "conn-dev-1", "dev-2": "conn-dev-2"},
        policy="strict", videos={A: VIDEO_MS},
    )
    for device_id in ("dev-1", "dev-2"):
        pending = s.pending
        assert playback.accept_ready(
            s, device_id=device_id, connection_id="conn-" + device_id,
            preparation_id=pending.id, version=pending.version, evidence_seq=1,
            mapping_revision=1, clock_ok=True, lease_ms=2000, now_ms=1100,
            decoded=False, occurrence=pending.occurrence.as_dict(), video=VIDEO,
        )
    assert playback.tick(s, 1000)[0]["type"] == "commit"
    return s


def fault(s, *, now=3000, position=2400):
    return playback.accept_fault(
        s, device_id="dev-1", now_ms=now,
        payload={
            "type": "video_fault", "session_id": s.id, "version": s.version,
            "occurrence": s.current.as_dict(),
            "position_ms": position, "reason": "stalled",
        },
    )


def test_status_does_not_call_an_expired_lease_ready():
    main._playback_session = session()
    pending = main._playback_session.pending
    lease = pending.leases["dev-1"]
    lease.ready = True
    lease.clock_ok = True
    lease.lease_expires_ms = main._now_ms() + 5000
    assert main._playback_status()["members"]["dev-1"]["ready"] is True
    lease.lease_expires_ms = main._now_ms() - 1
    assert main._playback_status()["members"]["dev-1"]["ready"] is False


def test_revoking_a_closed_socket_clears_the_pending_lease():
    main._playback_session = session()
    pending = main._playback_session.pending
    lease = pending.leases["dev-1"]
    lease.ready = True
    lease.clock_ok = True
    lease.lease_expires_ms = main._now_ms() + 5000
    lease.evidence_seq = 4
    main._revoke_playback_lease("dev-1", "conn-dev-1")
    assert lease.ready is False
    assert lease.clock_ok is False
    assert lease.evidence_seq == 0
    assert lease.lease_expires_ms == 0
    # A strict session cannot commit while a required lease is revoked.
    main._playback_session.pending.leases["dev-2"].ready = True
    main._playback_session.pending.leases["dev-2"].clock_ok = True
    main._playback_session.pending.leases["dev-2"].lease_expires_ms = 32000
    assert playback.tick(main._playback_session, 1500) == []


def test_a_missing_socket_revokes_before_the_next_tick():
    main._playback_session = session()
    pending = main._playback_session.pending
    for device_id in ("dev-1", "dev-2"):
        lease = pending.leases[device_id]
        lease.ready = True
        lease.clock_ok = True
        lease.lease_expires_ms = main._now_ms() + 5000
    main.device_sockets.pop("dev-1", None)
    main.device_sockets["dev-2"] = object()
    main._revoke_missing_leases(main._playback_session)
    assert pending.leases["dev-1"].ready is False
    assert pending.leases["dev-2"].ready is True


def test_replacing_a_socket_revokes_before_a_tick():
    main._playback_session = session()
    pending = main._playback_session.pending
    lease = pending.leases["dev-1"]
    lease.ready = True
    lease.clock_ok = True
    lease.lease_expires_ms = main._now_ms() + 5000
    record = {"connection_id": "conn-dev-1"}
    old = object()
    new = object()
    main.device_sockets["dev-1"] = old
    assert main._claim_device_socket("dev-1", new, record) is old
    assert lease.ready is False
    assert main.device_sockets["dev-1"] is new
    main._playback_session.pending.leases["dev-2"].ready = False
    assert playback.tick(main._playback_session, 1500) == []


def test_commit_reaches_the_other_members_when_one_writer_fails(monkeypatch):
    import asyncio

    main._playback_session = session()
    pending = main._playback_session.pending
    action = {
        "type": "commit", "version": 2, "prepared_at_version": 1,
        "preparation_id": pending.id, "occurrence": pending.occurrence.as_dict(),
        "asset": A, "effective_server_ms": main._now_ms() + 1000,
        "devices": ["dev-1", "dev-2"],
        "connections": {"dev-1": "conn-dev-1", "dev-2": "conn-dev-2"},
    }
    first, second = object(), object()
    main.devices["dev-1"] = {"device_id": "dev-1", "connection_id": "conn-dev-1"}
    main.devices["dev-2"] = {"device_id": "dev-2", "connection_id": "conn-dev-2"}
    main.device_sockets["dev-1"] = first
    main.device_sockets["dev-2"] = second
    sent = []

    async def send(socket, frame, stamp=None):
        if socket is first:
            raise RuntimeError("writer closed")
        sent.append(socket)

    monkeypatch.setattr(main, "_send_to", send)
    asyncio.run(main._send_commit(main._playback_session, action))
    assert sent == [second]
    assert main._playback_session.missed == ["dev-1"]


def test_status_reports_a_recovery_record_and_the_degraded_interval():
    main._playback_session = video_session()
    current = main._playback_session
    assert fault(current) == "preparing"
    status = main._playback_status()
    record = status["recovery"]
    assert status["state"] == "recovering"
    assert record["id"] == current.recovery.id
    assert record["occurrence"] == current.current.as_dict()
    assert record["position_ms"] == 2400
    assert record["reason"] == "stalled" and record["device_id"] == "dev-1"
    assert record["attempts"] == 1
    assert record["started_ms"] == 3000 and record["deadline_ms"] == 34000
    assert record["degraded_ms"] >= 0
    assert record["state"] == "preparing" and record["missing"] == []
    assert status["pending"]["start_media_ms"] == 2400

    playback.tick(current, current.pending.deadline_ms)
    blocked = main._playback_status()
    assert blocked["state"] == "blocked"
    assert blocked["recovery"]["state"] == "blocked"
    assert blocked["recovery"]["missing"] == ["dev-1", "dev-2"]


def test_a_replacement_socket_revokes_the_recovery_lease_but_keeps_the_recovery():
    main._playback_session = video_session()
    current = main._playback_session
    assert fault(current) == "preparing"
    lease = current.pending.leases["dev-1"]
    lease.ready = True
    lease.clock_ok = True
    lease.lease_expires_ms = main._now_ms() + 5000
    lease.evidence_seq = 3
    record = {"connection_id": "conn-dev-1"}
    assert main._claim_device_socket("dev-1", object(), record) is None
    assert lease.ready is False and lease.evidence_seq == 0
    assert current.state == "recovering"
    assert current.recovery is not None
