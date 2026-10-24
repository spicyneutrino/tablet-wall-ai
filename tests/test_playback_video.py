"""R4 video preparation, readiness evidence, commit anchor and samples."""

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
