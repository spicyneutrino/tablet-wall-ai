"""R4 video preparation, readiness evidence, commit anchor and samples."""

import pytest

from tabletwall import playback

A = "sha256:" + "a" * 64
B = "sha256:" + "b" * 64
VIDEO_MS = 4000


def session(*, policy="strict"):
    return playback.start(
        [{"asset": A, "dwell_ms": 1000}, {"asset": B, "dwell_ms": 1000}],
        False, ["dev-1", "dev-2"], 1000,
        generation="gen", clock_epoch="epoch",
        connections={"dev-1": "conn-dev-1", "dev-2": "conn-dev-2"},
        policy=policy, videos={A: VIDEO_MS},
    )


def ready(s, device, now, *, seq=1, video=None):
    pending = s.pending
    return playback.accept_ready(
        s, device_id=device, connection_id="conn-" + device,
        preparation_id=pending.id, version=pending.version, evidence_seq=seq,
        mapping_revision=1, clock_ok=True, lease_ms=2000, now_ms=now,
        decoded=False, occurrence=pending.occurrence.as_dict(), video=video,
    )


GOOD = {"metadata": True, "seeked": True, "buffered_ahead_ms": 5000,
        "play_ok": "yes", "rvfc": True}


def test_a_video_preparation_sets_dwell_and_media():
    s = session()
    assert s.items[0]["dwell_ms"] == VIDEO_MS
    assert s.pending.media == {
        "kind": "video", "duration_ms": VIDEO_MS, "buffer_goal_ms": 5000,
        "start_lead_ms": 1000, "prepare_timeout_ms": 30000,
    }
    assert s.pending.deadline_ms == s.pending.effective_ms + 30000
    assert s.pending.as_frame()["media"]["kind"] == "video"


def test_video_ready_needs_every_field_and_the_buffer_goal():
    s = session()
    assert ready(s, "dev-1", 1100, video={**GOOD, "buffered_ahead_ms": 3999}) is False
    assert ready(s, "dev-1", 1100, video={**GOOD, "metadata": False}, seq=2) is False
    assert ready(s, "dev-1", 1100, video={**GOOD, "seeked": False}, seq=3) is False
    assert ready(s, "dev-1", 1100, video={**GOOD, "play_ok": "needs_gesture"}, seq=4) is False
    assert ready(s, "dev-1", 1100, video=GOOD, seq=5) is True
    assert s.pending.leases["dev-1"].ready is True


def test_a_negative_video_report_clears_readiness():
    s = session()
    assert ready(s, "dev-1", 1000, video=GOOD) is True
    assert ready(s, "dev-1", 1200, seq=2,
                 video={**GOOD, "buffered_ahead_ms": 0}) is False
    assert s.pending.leases["dev-1"].ready is False


def test_video_commit_carries_the_start_anchor():
    s = session()
    assert ready(s, "dev-1", 1000, video=GOOD)
    assert ready(s, "dev-2", 1000, video=GOOD)
    action = playback.tick(s, 1000)[0]
    assert action["type"] == "commit" and action["start_media_ms"] == 0
    assert s.current_media["duration_ms"] == VIDEO_MS
    assert sorted(s.playing) == ["dev-1", "dev-2"]
    assert s.pending is not None and s.pending.occurrence.item_index == 1
    assert s.pending.effective_ms == action["effective_server_ms"] + VIDEO_MS


def test_samples_are_bounded_attributed_and_rate_limited():
    s = session()
    assert ready(s, "dev-1", 1000, video=GOOD)
    assert ready(s, "dev-2", 1000, video=GOOD)
    action = playback.tick(s, 1000)[0]
    payload = {
        "session_id": s.id, "version": action["version"],
        "occurrence": action["occurrence"], "media_ms": 500, "target_ms": 500,
        "drift_ms": 1.5, "rate": 1, "source": "rvfc",
    }
    assert playback.accept_sample(s, device_id="dev-1", payload=payload, now_ms=1500)
    assert playback.accept_sample(s, device_id="dev-2", payload=payload, now_ms=1500)
    assert not playback.accept_sample(s, device_id="dev-1", payload=payload, now_ms=2000)
    later = {**payload, "media_ms": 1600, "target_ms": 1600}
    assert playback.accept_sample(s, device_id="dev-1", payload=later, now_ms=2600)
    assert set(playback.video_status(s, 2700)) == {"dev-1", "dev-2"}
    assert playback.video_status(s, 8000) == {}
    assert not playback.accept_sample(
        s, device_id="dev-3", payload=payload, now_ms=9000
    )
    assert not playback.accept_sample(
        s, device_id="dev-1", payload={**later, "drift_ms": 999999}, now_ms=9000
    )


def test_single_nonloop_video_stays_final_and_accepts_samples():
    s = playback.start(
        [{"asset": A, "dwell_ms": 1000}], False, ["dev-1", "dev-2"], 1000,
        generation="gen", clock_epoch="epoch",
        connections={"dev-1": "conn-dev-1", "dev-2": "conn-dev-2"},
        policy="strict", videos={A: VIDEO_MS},
    )
    assert ready(s, "dev-1", 1000, video=GOOD)
    assert ready(s, "dev-2", 1000, video=GOOD)
    action = playback.tick(s, 1000)[0]
    assert s.state == playback.FINAL and s.pending is None
    payload = {
        "session_id": s.id, "version": action["version"],
        "occurrence": action["occurrence"], "media_ms": 500, "target_ms": 500,
        "drift_ms": 0, "rate": 1, "source": "time",
    }
    assert playback.accept_sample(s, device_id="dev-1", payload=payload, now_ms=2000)


# ---------------------------------------------------------------------------
# Bounded group video recovery (R4.1)
# ---------------------------------------------------------------------------


def committed(*, policy="strict", items=None, videos=None, now=1000):
    """A session whose first video occurrence is already on the glass."""
    s = playback.start(
        items or [{"asset": A, "dwell_ms": 1000}, {"asset": B, "dwell_ms": 1000}],
        False, ["dev-1", "dev-2"], now, generation="gen", clock_epoch="epoch",
        connections={"dev-1": "conn-dev-1", "dev-2": "conn-dev-2"},
        policy=policy, videos={A: VIDEO_MS} if videos is None else videos,
    )
    assert ready(s, "dev-1", now + 100, video=GOOD)
    assert ready(s, "dev-2", now + 100, video=GOOD)
    action = playback.tick(s, now)[0]
    assert action["type"] == "commit"
    return s


def fault(s, *, now=3000, position=2400, reason="stalled", device="dev-1", **overrides):
    payload = {
        "type": "video_fault", "session_id": s.id, "version": s.version,
        "occurrence": s.current.as_dict(), "position_ms": position,
        "reason": reason,
    }
    payload.update(overrides)
    return playback.accept_fault(
        s, device_id=device, payload=payload, now_ms=now
    )


def test_a_fault_re_prepares_the_current_occurrence_at_its_position():
    s = committed()
    version = s.version
    assert s.pending.occurrence.item_index == 1  # the next item is pending
    assert fault(s) == "preparing"
    assert s.version == version + 1
    assert s.state == "recovering"
    assert s.pending.occurrence == s.current
    assert s.pending.start_media_ms == 2400
    assert s.pending.effective_ms == 4000  # now + LEAD_MS
    assert s.pending.deadline_ms == 34000
    assert s.recovery.occurrence == s.current
    assert s.recovery.position_ms == 2400 and s.recovery.attempts == 1
    frame = s.pending.as_frame()
    assert frame["start_media_ms"] == 2400 and frame["media"]["kind"] == "video"
    # The required buffer is measured from the position: 4000 - 2400.
    assert ready(s, "dev-1", 3900, seq=2,
                 video={**GOOD, "buffered_ahead_ms": 1599}) is False
    assert ready(s, "dev-1", 3900, seq=3,
                 video={**GOOD, "buffered_ahead_ms": 1600}) is True
    assert ready(s, "dev-2", 3900, seq=2, video=GOOD) is True
    action = playback.tick(s, 3999)[0]
    assert action["type"] == "commit"
    assert action["start_media_ms"] == 2400
    assert action["effective_server_ms"] == 4000
    assert s.current_start_media_ms == 2400
    assert s.pending.occurrence.item_index == 1
    assert s.pending.effective_ms == 5600  # 4000 + (4000 - 2400)
    assert s.recovery.state == "playing"
    assert playback.recovery_status(s, 4500)["state"] == "playing"


def test_a_fault_before_the_commit_anchor_is_ignored():
    s = committed()
    anchor = s.current_effective_ms
    assert anchor is not None
    assert fault(s, now=anchor - 1) == "ignored"
    assert s.state == "playing" and s.recovery is None
    assert fault(s, now=anchor) == "preparing"


def test_a_fault_must_be_current_bounded_and_is_deduplicated():
    s = committed()
    assert fault(s, position=-1) == "ignored"
    assert fault(s, position=VIDEO_MS + 1) == "ignored"
    assert fault(s, position=True) == "ignored"
    assert fault(s, reason="buffering") == "ignored"
    assert fault(
        s, occurrence={"playlist_revision": 1, "item_index": 1, "loop": 0}
    ) == "ignored"
    assert fault(s, version=s.version + 1) == "ignored"
    assert fault(s, device="dev-3") == "ignored"
    assert fault(s, session_id="other") == "ignored"
    assert s.state == "playing" and s.recovery is None
    assert fault(s, position=0) == "preparing"
    assert fault(s, position=1000) == "ignored"  # one recovery at a time
    assert s.recovery.attempts == 1
    assert s.pending.start_media_ms == 0
    assert playback.tick(s, 3100) == []
    assert s.state == "recovering"


def test_a_stale_sample_starts_one_recovery_from_the_playhead():
    s = committed()
    assert playback.tick(s, 4999) == []  # 2999 ms without a sample is fine
    actions = playback.tick(s, 5001)
    assert [action["type"] for action in actions] == ["recover"]
    assert actions[0]["device_id"] == "dev-1"
    assert actions[0]["position_ms"] == 3001
    assert s.state == "recovering"
    assert s.recovery.reason == "stalled"
    assert s.pending.start_media_ms == 3001
    assert playback.tick(s, 5001) == []  # already recovering


def test_an_accepted_sample_delays_stale_detection():
    s = committed(items=[{"asset": A, "dwell_ms": 1000}])
    assert s.state == playback.FINAL
    payload = {
        "session_id": s.id, "version": s.version,
        "occurrence": s.current.as_dict(), "media_ms": 2000, "target_ms": 2000,
        "drift_ms": 0, "rate": 1, "source": "rvfc",
    }
    assert playback.accept_sample(s, device_id="dev-1", payload=payload, now_ms=2500)
    assert playback.accept_sample(s, device_id="dev-2", payload=payload, now_ms=2500)
    assert playback.tick(s, 5500) == []  # exactly 3000 ms is not stale
    assert [action["type"] for action in playback.tick(s, 5501)] == ["recover"]


def test_a_recovery_without_the_whole_cohort_blocks_in_strict():
    s = committed()
    assert fault(s) == "preparing"
    assert ready(s, "dev-1", 33000, seq=2, video=GOOD)  # expires at 35000
    assert playback.tick(s, 33999) == []
    actions = playback.tick(s, 34000)
    assert actions == [{
        "type": "blocked", "reason": "recovery_timeout", "missing": ["dev-2"],
    }]
    assert s.state == "blocked"
    assert s.blocked_reason == "recovery_timeout"
    assert s.recovery is not None and s.recovery.state == "blocked"
    assert s.recovery.missing == ["dev-2"]
    assert playback.tick(s, 100_000) == []


def test_a_recovery_without_the_whole_cohort_fails_online():
    s = committed(policy="online")
    assert fault(s) == "preparing"
    actions = playback.tick(s, s.pending.deadline_ms)
    assert actions == [{"type": "failed", "reason": "recovery_failed"}]
    assert s.state == "failed"
    assert s.recovery.state == "failed"
    assert s.blocked_reason == "recovery_failed"


def test_retry_rebuilds_the_same_recovery_occurrence_and_position():
    s = committed()
    assert fault(s, position=2400) == "preparing"
    old = s.pending
    playback.tick(s, old.deadline_ms)
    assert s.state == "blocked"
    fresh = playback.retry(s, 40000)
    assert s.state == "recovering"
    assert s.version == fresh.version
    assert fresh.occurrence == s.current
    assert fresh.start_media_ms == 2400
    assert fresh.effective_ms == 41000 and fresh.deadline_ms == 71000
    assert fresh.id != old.id
    assert s.recovery.attempts == 2 and s.recovery.started_ms == 40000
    assert playback.accept_ready(
        s, device_id="dev-1", connection_id="conn-dev-1",
        preparation_id=old.id, version=old.version, evidence_seq=1,
        mapping_revision=1, clock_ok=True, lease_ms=2000, now_ms=40000,
        decoded=False, occurrence=old.occurrence.as_dict(), video=GOOD,
    ) is False
    assert ready(s, "dev-1", 40900, seq=2, video=GOOD)
    assert ready(s, "dev-2", 40900, seq=2, video=GOOD)
    action = playback.tick(s, 40999)[0]
    assert action["type"] == "commit" and action["start_media_ms"] == 2400
    assert action["effective_server_ms"] == 41000
    assert s.pending.effective_ms == 42600


def test_a_fourth_recovery_for_one_occurrence_blocks_without_a_prepare():
    s = committed()
    now = 2500
    for attempt in (1, 2, 3):
        assert fault(s, now=now) == "preparing"
        assert s.recovery.attempts == attempt
        assert ready(s, "dev-1", now + 900, seq=attempt + 1, video=GOOD)
        assert ready(s, "dev-2", now + 900, seq=attempt + 1, video=GOOD)
        commit = playback.tick(s, now + 999)[0]
        assert commit["type"] == "commit" and commit["start_media_ms"] == 2400
        now = int(s.current_effective_ms) + 100
    version = s.version
    assert s.state == "playing"
    assert fault(s, now=now) == "blocked"
    assert s.version == version
    assert s.state == "blocked" and s.pending is None
    assert s.recovery.attempts == 4 and s.recovery.state == "blocked"
    fresh = playback.retry(s, now + 100)
    assert s.state == "recovering" and fresh.start_media_ms == 2400
    assert s.recovery.attempts == 1
    assert ready(s, "dev-1", now + 200, seq=9, video=GOOD)
    assert ready(s, "dev-2", now + 200, seq=9, video=GOOD)
    assert playback.tick(s, now + 1199)[0]["type"] == "commit"


def test_a_recovered_final_item_stays_final():
    s = playback.start(
        [{"asset": A, "dwell_ms": 1000}], False, ["dev-1", "dev-2"], 1000,
        generation="gen", clock_epoch="epoch",
        connections={"dev-1": "conn-dev-1", "dev-2": "conn-dev-2"},
        policy="strict", videos={A: VIDEO_MS},
    )
    assert ready(s, "dev-1", 1100, video=GOOD)
    assert ready(s, "dev-2", 1100, video=GOOD)
    playback.tick(s, 1000)
    assert s.state == playback.FINAL and s.pending is None
    assert fault(s, position=1500) == "preparing"
    assert s.state == "recovering" and s.final is False
    assert ready(s, "dev-1", 3900, seq=2, video=GOOD)
    assert ready(s, "dev-2", 3900, seq=2, video=GOOD)
    action = playback.tick(s, 3999)[0]
    assert action["start_media_ms"] == 1500
    assert s.state == playback.FINAL and s.final is True
    assert s.pending is None


def test_stop_and_step_supersede_a_recovery():
    s = committed()
    assert fault(s) == "preparing"
    playback.stop(s, 3500)
    assert s.state == "stopped"
    assert s.recovery is None and s.pending is None
    assert s.recovery_attempts == 0

    fresh = committed()
    assert fault(fresh) == "preparing"
    pending = playback.step(
        fresh, 1, 3500,
        {"dev-1": "conn-dev-1", "dev-2": "conn-dev-2"},
    )
    assert fresh.recovery is None
    assert fresh.state == "preparing"
    assert pending.occurrence.item_index == 1


def test_recovery_status_reports_the_degraded_interval():
    s = committed()
    assert fault(s, now=3000, position=2400, reason="buffer_lost") == "preparing"
    status = playback.recovery_status(s, 3500)
    assert status == {
        "id": s.recovery.id,
        "occurrence": {"playlist_revision": 1, "item_index": 0, "loop": 0},
        "position_ms": 2400, "reason": "buffer_lost", "device_id": "dev-1",
        "attempts": 1, "started_ms": 3000, "deadline_ms": 34000,
        "degraded_ms": 500, "state": "preparing", "missing": [],
    }
    playback.tick(s, 34000)
    blocked = playback.recovery_status(s, 40000)
    assert blocked["state"] == "blocked" and blocked["degraded_ms"] == 37000
    assert blocked["missing"] == ["dev-1", "dev-2"]
