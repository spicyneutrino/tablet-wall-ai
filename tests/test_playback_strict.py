"""Strict slots: never commit with a frozen-cohort member missing (R3)."""

import pytest

from tabletwall import playback

A = "sha256:" + "a" * 64
B = "sha256:" + "b" * 64
ITEMS = [{"asset": A, "dwell_ms": 5000}, {"asset": B, "dwell_ms": 5000}]


DEFAULT = object()


def make(policy=DEFAULT, *, now=1000):
    cohort = ["dev-1", "dev-2"]
    extra = {} if policy is DEFAULT else {"policy": policy}
    return playback.start(
        ITEMS, False, cohort, now, generation="gen", clock_epoch="epoch",
        connections={device: "conn-" + device for device in cohort}, **extra,
    )


def ready(s, device, now, *, lease=2000, seq=1, prep=None, version=None, connection=None):
    pending = s.pending
    return playback.accept_ready(
        s, device_id=device, connection_id=connection or "conn-" + device,
        preparation_id=prep or pending.id,
        version=version if version is not None else pending.version,
        evidence_seq=seq, mapping_revision=1, clock_ok=True,
        lease_ms=lease, now_ms=now,
    )


def test_the_default_policy_is_online_and_unknown_policies_are_refused():
    assert make().policy == "online"
    assert make("strict").policy == "strict"
    for bad in ("", "Strict", "lenient", None, 1):
        with pytest.raises(playback.PlaybackError):
            make(bad)


def test_online_still_holds_then_commits_a_partial_cohort():
    s = make("online")
    assert ready(s, "dev-1", 1500)
    assert playback.tick(s, 2000)[0]["type"] == "hold"
    assert s.state == "armed"
    commit = playback.tick(s, 7000)[0]
    assert commit["type"] == "commit" and commit["missed"] == ["dev-2"]
    assert s.state == "playing" and s.blocked_reason is None


def test_strict_commits_when_the_whole_cohort_is_ready():
    s = make("strict")
    assert ready(s, "dev-1", 1100) and ready(s, "dev-2", 1100)
    actions = playback.tick(s, 1000)
    assert [action["type"] for action in actions] == ["commit"]
    assert actions[0]["devices"] == ["dev-1", "dev-2"]
    assert "missed" not in actions[0]
    assert s.state == "playing"


def test_strict_never_commits_without_a_member_and_blocks_at_the_deadline():
    s = make("strict")
    deadline = s.pending.deadline_ms
    seq = 0
    for now in range(1500, int(deadline), 500):
        seq += 1
        ready(s, "dev-1", now, seq=seq)
        assert playback.tick(s, now) == [], now
        assert s.state == "preparing"
    actions = playback.tick(s, deadline)
    assert [action["type"] for action in actions] == ["blocked"]
    assert actions[0]["missing"] == ["dev-2"]
    assert s.state == "blocked"
    assert s.blocked_reason and s.missed == ["dev-2"]
    assert s.current is None
    assert playback.tick(s, deadline + 10_000) == []
    assert ready(s, "dev-1", deadline + 10, seq=10_000) is False


def test_strict_slides_the_cut_so_a_late_member_can_still_join():
    s = make("strict")
    assert ready(s, "dev-1", 1500)
    assert playback.tick(s, 2000) == []
    assert s.pending.effective_ms == 3000
    assert ready(s, "dev-1", 2100, seq=2)
    assert ready(s, "dev-2", 2200)
    commit = playback.tick(s, 2200)[0]
    assert commit["type"] == "commit" and commit["effective_server_ms"] == 3000


def test_a_stale_lease_cannot_commit_in_strict():
    s = make("strict")
    assert ready(s, "dev-1", 1100, lease=1000)  # expires 2100, covers the 2000 cut
    assert playback.tick(s, 2000) == []  # the cut slides to 3000
    assert ready(s, "dev-2", 2500)
    assert s.pending.leases["dev-1"].lease_expires_ms == 2100
    assert playback.tick(s, 2500) == []
    assert s.state == "preparing" and s.current is None
    assert playback.tick(s, s.pending.deadline_ms)[0]["type"] == "blocked"


def test_retry_after_blocked_bumps_the_version_and_supersedes():
    s = make("strict")
    ready(s, "dev-1", 1500)
    playback.tick(s, s.pending.deadline_ms)
    assert s.state == "blocked"
    old, version = s.pending, s.version
    fresh = playback.retry(s, 40_000, {"dev-2": "conn-new"})
    assert s.version == version + 1 and s.state == "preparing"
    assert s.blocked_reason is None and s.missed == []
    assert fresh.id != old.id and fresh.version == s.version
    assert fresh.occurrence == old.occurrence
    assert s.cohort == ["dev-1", "dev-2"]
    assert fresh.leases["dev-2"].connection_id == "conn-new"
    assert fresh.leases["dev-1"].connection_id == "conn-dev-1"
    assert ready(s, "dev-1", 40_100, prep=old.id, version=old.version) is False
    assert ready(s, "dev-1", 40_100) is True
    assert ready(s, "dev-2", 40_100, connection="conn-new") is True
    assert playback.tick(s, 40_100)[0]["type"] == "commit"


def test_retry_is_only_legal_from_blocked_and_stop_works_from_blocked():
    s = make("strict")
    with pytest.raises(playback.PlaybackError):
        playback.retry(s, 2000)
    with pytest.raises(playback.PlaybackError):
        playback.retry(make("online"), 2000)
    playback.tick(s, s.pending.deadline_ms)
    assert s.state == "blocked"
    version = s.version
    playback.stop(s, 40_000)
    assert s.state == "stopped" and s.pending is None and s.version == version + 1


def test_start_rejects_an_unknown_policy_over_http():
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app) as client:
        for bad in ("lenient", "STRICT", 3, None):
            response = client.post("/api/v3/playback/start", json={"policy": bad})
            assert response.status_code == 422, bad
        assert client.post("/api/v3/playback/retry").status_code == 404
