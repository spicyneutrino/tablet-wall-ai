"""Hand-checked cases for the hard-cut analysis. No browser needed."""

import math

import pytest

from simulator.browser import evidence

RED, GREEN = (220, 30, 30), (30, 200, 60)
ASSETS = {
    0: {"id": "sha256:red", "url": "/assets/sha256:red"},
    1: {"id": "sha256:green", "url": "/assets/sha256:green"},
}
COLOURS = {"sha256:red": RED, "sha256:green": GREEN}
IDS = {"a": "id-a", "b": "id-b"}


def scenario(onsets, *, skip_commit=(), skip_paint=(), wrong_pixel=(), missed=None, effective_step=1000):
    """Two members, two alternating assets, one commit per event.

    ``onsets[seq]`` is ``{member: onset_ms}``; commits arrive 500 ms before the
    planned time ``effective = 10_000 + seq * effective_step``.
    """
    commits = {"a": [], "b": []}
    draws = {"a": [], "b": []}
    for seq, row in enumerate(onsets):
        asset = ASSETS[seq % 2]
        effective = 10_000 + seq * effective_step
        for member, onset in row.items():
            if (member, seq) in skip_commit:
                continue
            commits[member].append({
                "t": effective - 500,
                "occurrence": {"loop": seq // 2, "item_index": seq % 2},
                "asset": asset, "effective_server_ms": effective,
                "missed": (missed or {}).get(seq, []),
            })
            if (member, seq) in skip_paint:
                continue
            colour = RED if seq % 2 else GREEN  # deliberately wrong when requested
            if (member, seq) not in wrong_pixel:
                colour = COLOURS[asset["id"]]
            draws[member].append({"t": onset, "src": "http://x" + asset["url"], "pixel": list(colour)})
    return commits, draws


def analyze(onsets, target=None, **options):
    commits, draws = scenario(onsets, **options)
    return evidence.analyze_cuts(
        cohort=["a", "b"], ids=IDS, period=2, target=target or len(onsets), dwell_ms=1000,
        commits=commits, draws=draws, expected_colour=COLOURS, server_to_epoch_ms=0.0,
    )


def test_nearest_rank_percentiles():
    values = list(range(1, 101))
    assert evidence.percentile(values, 50) == 50
    assert evidence.percentile(values, 95) == 95
    assert evidence.percentile(values, 100) == 100
    assert evidence.percentile([5.0], 95) == 5.0
    assert evidence.percentile([], 50) is None


def test_delta_is_per_event_max_minus_min_not_pooled():
    result = analyze([
        {"a": 10_000, "b": 10_004},
        {"a": 11_010, "b": 11_000},
        {"a": 12_000, "b": 12_090},
    ])
    assert [event["delta_ms"] for event in result["events"]] == [4, 10, 90]
    assert result["events_complete"] == 3 and result["events_failed"] == 0
    assert result["healthy_subset"]["max"] == 90
    assert result["healthy_subset"]["p50"] == 10
    assert result["whole_show"]["max"] == 90
    assert result["label"] == "software, not optical"


def test_missing_paint_is_a_failed_event_and_makes_the_whole_show_unbounded():
    onsets = [{"a": 10_000 + 1000 * i, "b": 10_000 + 1000 * i + 3} for i in range(20)]
    result = analyze(onsets, skip_paint={("b", 7)})
    assert result["events_failed"] == 1 and result["events_complete"] == 19
    assert result["failed_events"] == [{
        "seq": 7, "missing_members": ["b"], "reasons": {"b": "no paint after commit"},
    }]
    # Nineteen finite 3 ms deltas stay the healthy subset.
    assert result["healthy_subset"]["n"] == 19 and result["healthy_subset"]["max"] == 3
    # One failure in twenty is exactly the 5 percent tail, so p95 is still finite
    # but the maximum is unbounded.
    assert result["whole_show"]["n"] == 20
    assert result["whole_show"]["max"] is None
    assert result["events"][7]["delta_ms"] is None
    assert result["completion_by_member"] == {"a": 20, "b": 19}


def test_two_failures_push_the_whole_show_p95_to_unbounded():
    onsets = [{"a": 10_000 + 1000 * i, "b": 10_000 + 1000 * i + 3} for i in range(20)]
    result = analyze(onsets, skip_paint={("b", 3), ("a", 9)})
    assert result["whole_show"]["p95"] is None
    assert result["healthy_subset"]["p95"] == 3


def test_a_member_without_a_commit_fails_the_event_and_server_misses_are_named():
    result = analyze(
        [{"a": 10_000, "b": 10_000}, {"a": 11_000, "b": 11_000}],
        skip_commit={("b", 1)}, missed={1: ["id-b"]},
    )
    event = result["events"][1]
    assert not event["complete"]
    assert event["members"]["b"]["failure"] == "no commit delivered"
    assert event["server_missed"] == ["b"]
    assert {"failed event", "server-declared miss"} <= set(result["degradation_windows"][0]["reasons"])


def test_event_with_no_commit_for_any_member_is_not_omitted():
    commits, draws = scenario([{"a": 10_000, "b": 10_000}, {"a": 11_000, "b": 11_000}])
    result = evidence.analyze_cuts(
        cohort=["a", "b"], ids=IDS, period=2, target=3, dwell_ms=1000,
        commits=commits, draws=draws, expected_colour=COLOURS, server_to_epoch_ms=0.0,
    )
    assert result["events_requested"] == 3 and len(result["events"]) == 3
    assert result["events_committed"] == 2
    assert result["events_failed"] == 1 and result["failed_events"][0]["seq"] == 2
    assert result["failed_events"][0]["reasons"] == {
        "a": "no commit delivered", "b": "no commit delivered",
    }


def test_wrong_pixel_is_not_a_completed_cut():
    result = analyze([{"a": 10_000, "b": 10_002}], wrong_pixel={("b", 0)})
    assert not result["events"][0]["complete"]
    assert result["events"][0]["members"]["b"]["failure"] == "wrong or unverified pixel"
    assert result["events"][0]["partial_delta_ms"] == 2
    assert result["healthy_subset"]["n"] == 0
    assert result["healthy_subset"]["p95"] is None


def test_a_late_paint_for_a_repeated_asset_is_not_borrowed_from_the_next_occurrence():
    # Member b never paints event 0 (red). It paints event 2 (red again) later.
    onsets = [{"a": 10_000, "b": 10_000}, {"a": 11_000, "b": 11_000}, {"a": 12_000, "b": 12_000}]
    result = analyze(onsets, skip_paint={("b", 0)})
    assert result["failed_events"][0]["seq"] == 0
    assert result["events"][2]["complete"] and result["events"][2]["delta_ms"] == 0


def test_degradation_windows_merge_consecutive_events_and_report_the_reanchor():
    onsets = [{"a": 10_000 + 1000 * i, "b": 10_000 + 1000 * i} for i in range(6)]
    commits, draws = scenario(onsets)
    # A hold pushes event 3 two seconds late and re-anchors the rest.
    for member in commits:
        for row in commits[member]:
            if sequence_of(row) >= 3:
                row["effective_server_ms"] += 2000
    result = evidence.analyze_cuts(
        cohort=["a", "b"], ids=IDS, period=2, target=6, dwell_ms=1000,
        commits=commits, draws=draws, expected_colour=COLOURS, server_to_epoch_ms=0.0,
    )
    assert result["degradation_windows"] == [{
        "first_seq": 3, "last_seq": 3, "events": 1, "reasons": ["re-anchor or hold"],
        "effective_span_ms": 0.0,
    }]
    assert result["events_failed"] == 0


def sequence_of(row):
    return evidence.sequence(row["occurrence"], 2)


def test_lateness_uses_the_server_to_page_clock_mapping():
    commits, draws = scenario([{"a": 10_025, "b": 10_040}])
    result = evidence.analyze_cuts(
        cohort=["a", "b"], ids=IDS, period=2, target=1, dwell_ms=1000,
        commits=commits, draws=draws, expected_colour=COLOURS, server_to_epoch_ms=0.0,
    )
    assert result["lateness_vs_effective_ms"]["a"]["p50"] == 25
    assert result["lateness_vs_effective_ms"]["b"]["max"] == 40
    assert math.isclose(result["events"][0]["delta_ms"], 15)


@pytest.mark.parametrize("count", [0, 1])
def test_small_samples_do_not_crash(count):
    summary = evidence.summarize([float(i) for i in range(count)])
    assert summary["n"] == count
