"""Hard-cut still playlist model: identity, leases, hold and supersession."""

import pytest

from tabletwall import playback

A = "sha256:" + "a" * 64
B = "sha256:" + "b" * 64
C = "sha256:" + "c" * 64
D = "sha256:" + "d" * 64


def session(items=None, *, loop=False, cohort=None, now=1000):
    cohort = cohort or ["dev-1", "dev-2"]
    return playback.start(
        items or [{"asset": A, "dwell_ms": 5000}, {"asset": B, "dwell_ms": 5000}],
        loop, cohort, now, generation="gen", clock_epoch="epoch",
        connections={device: "conn-" + device for device in cohort},
    )


def ready(s, device, now, *, lease=2000, seq=1, version=None, prep=None):
    pending = s.pending
    return playback.accept_ready(
        s, device_id=device, connection_id="conn-" + device,
        preparation_id=prep or pending.id,
        version=version if version is not None else pending.version,
        evidence_seq=seq, mapping_revision=1, clock_ok=True,
        lease_ms=lease, now_ms=now,
    )


def test_a_full_cohort_commits_once_and_prepares_the_next_occurrence():
    s = session(now=1000)
    assert s.state == "preparing"
    assert s.pending.effective_ms == 2000
    assert ready(s, "dev-1", 1100)
    assert ready(s, "dev-2", 1100)
    assert playback.tick(s, 999) == []
    actions = playback.tick(s, 1000)
    assert [action["type"] for action in actions] == ["commit"]
    commit = actions[0]
    assert commit["version"] == 2
    assert commit["occurrence"] == {"playlist_revision": 1, "item_index": 0, "loop": 0}
    assert commit["effective_server_ms"] == 2000
    assert commit["devices"] == ["dev-1", "dev-2"]
    assert s.current.item_index == 0
    assert s.pending.occurrence.item_index == 1
    assert s.pending.effective_ms == 7000


def test_a_lease_that_does_not_cover_the_cut_is_rejected():
    s = session(now=1000)
    assert ready(s, "dev-1", 1500, lease=400) is False
    assert s.pending.leases["dev-1"].ready is False


def test_wrong_lineage_connection_and_evidence_are_rejected():
    s = session(now=1000)
    assert ready(s, "dev-1", 1100, version=99) is False
    assert ready(s, "dev-1", 1100, prep="other") is False
    assert ready(s, "dev-1", 1100, seq=0) is False
    assert playback.accept_ready(
        s, device_id="dev-1", connection_id="wrong", preparation_id=s.pending.id,
        version=1, evidence_seq=1, mapping_revision=1, clock_ok=True,
        lease_ms=2000, now_ms=1100,
    ) is False
    assert ready(s, "dev-1", 1100, seq=2) is True
    assert ready(s, "dev-1", 1100, seq=2) is False  # replay


def test_bounded_hold_names_the_miss_and_reanchors():
    s = session(now=1000)
    assert ready(s, "dev-1", 1500)
    actions = playback.tick(s, 2000)
    assert actions[0]["type"] == "hold"
    assert actions[0]["missing"] == ["dev-2"]
    assert s.held is True
    assert playback.tick(s, 3000) == []
    actions = playback.tick(s, 7000)
    assert actions[0]["type"] == "commit"
    assert actions[0]["missed"] == ["dev-2"]
    assert actions[0]["effective_server_ms"] == 8000
    assert "dev-2" in s.missed


def test_supersession_invalidates_pending_readiness():
    s = session(now=1000)
    assert ready(s, "dev-1", 1100) is True
    old = s.pending
    new = playback.step(s, 1, 1200)
    assert new.version != old.version
    assert old.id != new.id
    assert playback.tick(s, 2200)[0]["type"] == "hold"
    assert ready(s, "dev-1", 2200, prep=old.id, version=old.version) is False


def test_repeated_assets_are_distinct_occurrences():
    s = session([{"asset": A, "dwell_ms": 1000}, {"asset": A, "dwell_ms": 1000}], now=1000)
    ready(s, "dev-1", 1100)
    ready(s, "dev-2", 1100)
    playback.tick(s, 1000)
    assert s.pending.occurrence.item_index == 1
    assert s.pending.asset == A
    assert s.current.item_index == 0


def test_loop_wraps_with_a_new_loop_count_and_false_loop_stops():
    looping = session([{"asset": A, "dwell_ms": 1000}, {"asset": B, "dwell_ms": 1000}],
                      loop=True, now=1000)
    looping.index = 1
    looping.loop_count = 0
    looping.current = looping.occurrence_at(1)
    looping.version += 1
    looping.pending = playback.Preparation(
        id="next", version=looping.version, occurrence=looping.occurrence_at(1),
        asset=B, created_ms=1000, deadline_ms=31000, effective_ms=2000,
    )
    looping.pending.leases = {
        "dev-1": playback.Lease("dev-1", "conn-dev-1"),
        "dev-2": playback.Lease("dev-2", "conn-dev-2"),
    }
    ready(looping, "dev-1", 1100, prep="next", version=looping.version)
    ready(looping, "dev-2", 1100, prep="next", version=looping.version)
    playback.tick(looping, 1000)
    assert looping.loop_count == 1
    assert looping.pending.occurrence.item_index == 0
    assert looping.pending.occurrence.loop == 1


def test_pause_and_stop_cancel_pending_work():
    s = session(now=1000)
    ready(s, "dev-1", 1100)
    ready(s, "dev-2", 1100)
    playback.tick(s, 1000)
    assert s.pending is not None
    version = s.version
    assert playback.pause(s, 2000) == 0
    assert s.state == "paused" and s.pending is None and s.version == version + 1
    playback.stop(s, 3000)
    assert s.state == "stopped" and s.pending is None


def test_malformed_playlists_are_refused():
    for items, loop in (([], False), ([{"asset": "nope", "dwell_ms": 1000}], False),
                        ([{"asset": A, "dwell_ms": 10}], False),
                        ([{"asset": A, "dwell_ms": 700_000}], False)):
        with pytest.raises(playback.PlaybackError):
            playback.validate_playlist(items, loop=loop)


def test_readiness_is_renewed_until_it_covers_the_effective_time():
    s = session(now=1000)
    # A lease renewed at 1500 for 500 ms expires at 2000 and just covers the
    # cut; an earlier 500 ms lease at 1000 expires at 1500 and does not.
    assert ready(s, "dev-1", 1000, lease=500) is False
    assert ready(s, "dev-1", 1500, lease=500) is True
    assert s.pending.leases["dev-1"].lease_expires_ms == 2000
