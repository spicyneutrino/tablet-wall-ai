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
        lease_ms=lease, now_ms=now, decoded=True,
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
        lease_ms=2000, now_ms=1100, decoded=True,
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
    assert ready(s, "dev-1", 4400, seq=2, lease=2000)
    actions = playback.tick(s, 4500)
    assert actions[0]["type"] == "commit"
    assert actions[0]["missed"] == ["dev-2"]
    assert actions[0]["effective_server_ms"] == 5500
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
    assert looping.pending.occurrence.item_index == 0
    assert looping.pending.occurrence.loop == 1
    assert looping.loop_count == 0
    ready(looping, "dev-1", 2000, prep="next", version=looping.version)
    ready(looping, "dev-2", 2000, prep="next", version=looping.version)


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


def test_the_next_boundary_uses_the_committed_items_dwell():
    items = [{"asset": A, "dwell_ms": 5000}, {"asset": B, "dwell_ms": 11000},
             {"asset": C, "dwell_ms": 17000}]
    s = session(items, now=1000)
    assert ready(s, "dev-1", 1100) and ready(s, "dev-2", 1100)
    commit = playback.tick(s, 1000)[0]
    assert commit["type"] == "commit" and commit["effective_server_ms"] == 2000
    assert s.pending.occurrence.item_index == 1
    assert s.pending.effective_ms == 7000
    assert ready(s, "dev-1", 6900, seq=2) and ready(s, "dev-2", 6900, seq=2)
    commit = playback.tick(s, 6999)[0]
    assert commit["occurrence"]["item_index"] == 1
    assert s.pending.occurrence.item_index == 2
    assert s.pending.effective_ms == 18000


def test_next_and_previous_act_on_the_displayed_item():
    s = session([{"asset": A, "dwell_ms": 5000}, {"asset": B, "dwell_ms": 5000},
                 {"asset": C, "dwell_ms": 5000}], now=1000)
    assert ready(s, "dev-1", 1100) and ready(s, "dev-2", 1100)
    playback.tick(s, 1000)
    playback.refresh_display(s, 2000)
    assert s.displayed.item_index == 0
    pending = playback.step(s, 1, 2000, {"dev-1": "conn-dev-1", "dev-2": "conn-dev-2"})
    assert pending.occurrence.item_index == 1
    assert ready(s, "dev-1", 2100, seq=2) and ready(s, "dev-2", 2100, seq=2)
    playback.tick(s, 2999)
    playback.refresh_display(s, 3000)
    assert s.displayed.item_index == 1
    previous = playback.step(s, -1, 3000, {"dev-1": "conn-dev-1", "dev-2": "conn-dev-2"})
    assert previous.occurrence.item_index == 0


def test_non_looping_endpoints_are_refused_and_the_last_item_is_final():
    s = session([{"asset": A, "dwell_ms": 5000}], now=1000)
    assert ready(s, "dev-1", 1100) and ready(s, "dev-2", 1100)
    commit = playback.tick(s, 1000)[0]
    assert commit["type"] == "commit"
    assert s.state == playback.FINAL and s.final is True
    assert s.current.item_index == 0 and s.pending is None
    assert playback.tick(s, 5000) == []
    with pytest.raises(playback.PlaybackError):
        playback.step(s, 1, 5000, {"dev-1": "conn-dev-1", "dev-2": "conn-dev-2"})
    playback.pause(s, 5000)
    assert s.state == "paused"


def test_an_expired_lease_cannot_commit_a_held_cut():
    s = session(now=1000)
    assert ready(s, "dev-1", 1500)
    assert playback.tick(s, 2000)[0]["type"] == "hold"
    actions = playback.tick(s, 4500)
    assert actions[0]["type"] == "failed"
    assert s.state == "failed"


def test_retry_rebuilds_the_blocked_occurrence_not_the_active_one():
    s = playback.start(
        [{"asset": A, "dwell_ms": 5000}, {"asset": B, "dwell_ms": 5000}],
        False, ["dev-1", "dev-2"], 1000, generation="gen", clock_epoch="epoch",
        connections={"dev-1": "conn-dev-1", "dev-2": "conn-dev-2"}, policy="strict")
    assert ready(s, "dev-1", 1100) and ready(s, "dev-2", 1100)
    playback.tick(s, 1000)
    assert s.current.item_index == 0
    assert s.pending.occurrence.item_index == 1
    assert ready(s, "dev-1", s.pending.deadline_ms, seq=2)
    actions = playback.tick(s, s.pending.deadline_ms)
    assert actions[0]["type"] == "blocked"
    fresh = playback.retry(s, s.pending.deadline_ms + 10,
                           {"dev-1": "conn-dev-1", "dev-2": "conn-dev-2"})
    assert fresh.occurrence.item_index == 1
    assert fresh.occurrence.loop == 0


def test_pause_before_the_effective_time_cancels_the_armed_cut():
    s = session(now=1000)
    assert ready(s, "dev-1", 1100) and ready(s, "dev-2", 1100)
    playback.tick(s, 1000)
    assert s.current is not None and s.current_effective_ms == 2000
    assert playback.pause(s, 1500) is None
    assert s.current is None and s.displayed is None
    assert s.pending is None and s.state == "paused"
    fresh = playback.resume(s, 1500, {"dev-1": "conn-dev-1", "dev-2": "conn-dev-2"})
    assert fresh.occurrence.item_index == 0 and fresh.effective_ms == 2500
    assert ready(s, "dev-1", 1600, seq=2) and ready(s, "dev-2", 1600, seq=2)
    assert playback.tick(s, 2499)[0]["type"] == "commit"


def test_readiness_requires_decoded_mapping_and_occurrence():
    s = session(now=1000)
    pending = s.pending
    common = dict(
        session=s, device_id="dev-1", connection_id="conn-dev-1",
        preparation_id=pending.id, version=pending.version, evidence_seq=1,
        mapping_revision=1, clock_ok=True, lease_ms=2000, now_ms=1100,
    )
    assert playback.accept_ready(**{**common, "evidence_seq": 1}, decoded=False) is False
    assert playback.accept_ready(**{**common, "evidence_seq": 2}, decoded=True,
                                 expected_mapping=2) is False
    assert playback.accept_ready(**{**common, "evidence_seq": 3}, decoded=True,
                                 occurrence={"playlist_revision": 1, "item_index": 1, "loop": 0}) is False
    assert playback.accept_ready(**{**common, "evidence_seq": 4}, decoded=True) is True
