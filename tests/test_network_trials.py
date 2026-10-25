"""Pure checks for the network-trial harness; no network is touched."""

import asyncio
from datetime import datetime, timezone

import pytest

from deploy import network_trials


def test_is_instant_accepts_iso_offsets_naive_utc_and_epochs():
    expected = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc).timestamp()
    assert network_trials.parse_instant("2026-10-25T12:00:00Z") == expected
    assert network_trials.parse_instant("2026-10-25T14:00:00+02:00") == expected
    assert network_trials.parse_instant("2026-10-25T12:00:00") == expected
    assert network_trials.parse_instant(str(int(expected))) == expected
    assert network_trials.iso_utc(expected) == "2026-10-25T12:00:00.000000Z"


def test_a_restore_marker_carries_the_exact_time_and_optional_labels():
    row = network_trials.parse_restore_line(
        "2026-10-25T12:00:00.123456Z | ap-loss | channel 36")
    assert row["iso"] == "2026-10-25T12:00:00.123456Z"
    assert row["case"] == "ap-loss"
    assert row["note"] == "channel 36"
    assert network_trials.parse_restore_line("2026-10-25T12:00:00Z")["case"] is None


def test_a_trial_within_the_target_passes_only_with_timing_and_outage_evidence():
    passed = network_trials.trial_row(
        1, case="ap-loss", restored_at=100.0, seconds=7.5,
        outage_observed=True, origin_seconds=3.0, tablet_seconds=7.5,
        success=True,
    )
    assert passed["trial"] == "trial-01"
    assert passed["ok"] is True
    assert passed["restored_at"].endswith("Z")

    too_slow = network_trials.trial_row(
        2, case="ap-loss", restored_at=100.0, seconds=10.5,
        outage_observed=True, success=True, failure="too slow",
    )
    assert too_slow["ok"] is False
    no_outage = network_trials.trial_row(
        3, case="wan-loss", restored_at=100.0, seconds=2.0,
        outage_observed=False, success=True,
    )
    assert no_outage["ok"] is False
    no_time = network_trials.trial_row(
        4, case="wan-loss", restored_at=None, seconds=None,
        outage_observed=True, success=False, failure="no marker",
    )
    assert no_time["ok"] is False


def test_summary_keeps_failures_and_reports_nearest_rank_distribution():
    rows = [
        network_trials.trial_row(
            index, case="ap-loss", restored_at=100.0, seconds=index * 0.5,
            outage_observed=True, success=True,
        )
        for index in range(1, 21)
    ]
    rows[4] = network_trials.trial_row(
        5, case="ap-loss", restored_at=100.0, seconds=19.0,
        outage_observed=True, success=True, failure="over target",
    )
    rows[4]["ok"] = False
    summary = network_trials.summarize_trials(rows)
    assert summary["trials"] == 20
    assert summary["failures"] == 1
    assert summary["failure_ids"] == ["trial-05"]
    assert summary["p50_seconds"] == 5.5
    assert summary["p95_seconds"] == 10.0
    assert summary["max_seconds"] == 19.0
    assert summary["all_within_target"] is False


def test_live_trial_uses_the_slower_of_origin_and_tablet_and_records_skew():
    outage = {"at": 90.0}
    restore = {"at": 100.0, "source": "marker", "case": None, "note": None}
    origin = {"at": 103.0}
    tablet = {"at": 108.0, "wake_lock": "held"}
    row = network_trials._live_trial(
        1, "ap-loss", outage, restore, origin, tablet, receipt=100.2)
    assert row["origin_seconds"] == 3.0
    assert row["tablet_seconds"] == 8.0
    assert row["seconds"] == 8.0
    assert row["ok"] is True
    assert row["clock_skew_s"] == 0.2
    assert row["tablet_wake_lock"] == "held"

    skewed = network_trials._live_trial(
        2, "ap-loss", outage, restore, origin, tablet, receipt=200.0)
    assert skewed["ok"] is False
    assert "clock" in skewed["failure"]


def test_a_live_trial_without_an_observed_outage_fails():
    row = network_trials._live_trial(
        1, "ap-loss", None,
        {"at": 100.0, "source": "supplied", "case": "ap-loss", "note": None},
        {"at": 102.0}, {"at": 103.0}, receipt=100.0)
    assert row["ok"] is False
    assert "outage" in row["failure"]


def test_a_complete_report_has_twenty_scenarios_and_never_a_hardware_claim():
    trials = [
        network_trials.trial_row(
            index, case="wan-loss", restored_at=100.0, seconds=2.0,
            outage_observed=True, success=True,
        )
        for index in range(1, 21)
    ]
    report = network_trials.build_network_report(
        started_at="2026-10-25T00:00:00Z",
        finished_at="2026-10-25T00:10:00Z",
        trials=trials,
        checks=[{"name": "all 20 restores were within 10 s", "passed": True}],
        artifacts={},
        evidence_kind="operator-hardware",
        tools={"ap": "lab"},
        unobserved=[],
        limitations=["operator hardware only"],
        repository={"head": "x", "branch": "y", "dirty": False},
    )
    assert report["gate"] == "real-wifi-os"
    assert report["evidence_kind"] == "operator-hardware"
    assert report["hardware_gate_status"] == "MISSING"
    assert report["hardware_claim"] is False
    assert report["scenarios_total"] == 20
    assert report["scenarios_passed"] == 20
    assert report["completion"] == "complete"


def test_a_missing_trial_becomes_incomplete_and_a_failed_trial_blocks():
    trials = [
        network_trials.trial_row(
            index, case="wan-loss", restored_at=100.0, seconds=2.0,
            outage_observed=True, success=True,
        )
        for index in range(1, 20)
    ]
    trials.append(network_trials.trial_row(
        20, case="tablet-airplane", restored_at=100.0, seconds=12.0,
        outage_observed=True, success=True, failure="over target",
    ))
    report = network_trials.build_network_report(
        started_at="2026-10-25T00:00:00Z",
        finished_at="2026-10-25T00:10:00Z",
        trials=trials,
        checks=[{"name": "all 20 restores were within 10 s", "passed": False}],
        artifacts={},
        evidence_kind="software-simulation",
        tools={},
        unobserved=[],
        limitations=[],
        repository={},
    )
    assert report["scenarios_total"] == 20
    assert report["scenarios_passed"] == 19
    assert report["completion"] == "incomplete"
    assert "trial-20" in report["failure_reasons"]
    assert report["scenarios"][-1]["status"] == "failed"


def test_marker_source_ignores_history_and_reads_the_next_appended_line(tmp_path):
    marker = tmp_path / "restores.txt"
    marker.write_text("2026-10-25T11:00:00Z | old\n")
    source = network_trials.MarkerSource(marker)
    with marker.open("a") as handle:
        handle.write("2026-10-25T12:00:00Z | ap-loss | next\n")
    row = asyncio.run(source.next(timeout=1))
    assert row["iso"] == "2026-10-25T12:00:00.000000Z"
    assert row["case"] == "ap-loss"
    assert row["note"] == "next"


def test_origin_validation_rejects_paths_and_normalizes_a_trailing_slash():
    assert network_trials._origin("https://192.168.1.2:8443/") == "https://192.168.1.2:8443"
    with pytest.raises(ValueError):
        network_trials._origin("https://192.168.1.2:8443/client/")
    with pytest.raises(ValueError):
        network_trials._origin("ftp://192.168.1.2")


def test_dry_mode_rejects_a_live_base_url():
    with pytest.raises(SystemExit):
        network_trials.main(["--dry", "--base-url", "https://192.168.1.2"])


def test_live_mode_needs_a_base_url_tablet_and_metadata():
    with pytest.raises(SystemExit):
        network_trials.main(["--restored-stdin"])
    with pytest.raises(SystemExit):
        network_trials.main([
            "--base-url", "https://192.168.1.2", "--tablet-device-id", "x",
            "--restored-stdin",
        ])


def test_restored_at_needs_exactly_twenty_values():
    with pytest.raises(SystemExit):
        network_trials.main([
            "--base-url", "https://192.168.1.2", "--tablet-device-id", "x",
            "--ap", "ap", "--wan", "fibre",
            "--restored-at", "2026-10-25T12:00:00Z",
        ])
