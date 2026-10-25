"""Pure checks for the fleet soak harness; no browser or server is started."""

from pathlib import Path

import pytest

from simulator.browser import fleet_soak


def test_playlist_alternates_a_still_and_a_video():
    items = fleet_soak.playlist_items("sha256:still", "sha256:video")
    assert [item["asset"] for item in items] == ["sha256:still", "sha256:video"]
    assert items[0]["dwell_ms"] == fleet_soak.STILL_DWELL_MS


def test_proc_parsers_tolerate_a_parenthesised_process_name():
    status = "Name:\tuvicorn worker (x)\nVmRSS:\t  123456 kB\nThreads:\t3\n"
    stat = "999 (uvicorn (worker)) S 1 2 3 4 5 6 7 8 9 10 11 12 13"
    assert fleet_soak.parse_status_rss_kb(status) == 123456
    assert fleet_soak.parse_stat_cpu_ticks(stat) == 23


def test_process_resources_report_a_dead_pid_explicitly(tmp_path: Path):
    alive = tmp_path / "42"
    alive.mkdir()
    (alive / "status").write_text("Name:\tx\nVmRSS:\t  99 kB\n")
    (alive / "stat").write_text("42 (x) S 1 2 3 4 5 6 7 8 9 10 11 12 13")
    assert fleet_soak.read_process_resources(42, tmp_path) == {
        "alive": True, "rss_kb": 99, "cpu_ticks": 23,
    }
    assert fleet_soak.read_process_resources(7, tmp_path) == {
        "alive": False, "rss_kb": None, "cpu_ticks": None,
    }


def test_sampling_summary_classifies_a_deliberate_pause_only_when_it_overlaps():
    offsets = [0.0, 0.5, 1.0, 3.0, 3.5]
    summary = fleet_soak.sampling_summary(
        offsets, 0.5, 4.0,
        [{"from_s": 0.9, "to_s": 3.1, "kind": "recovery"}],
    )
    assert summary["gaps"][0]["deliberate"] is True
    assert summary["unexplained_gap_count"] == 0
    assert summary["max_gap_s"] == 2.0
    assert summary["samples"] == 5
    assert summary["expected_samples"] == 9


def test_sampling_summary_leaves_an_unexplained_gap_visible():
    summary = fleet_soak.sampling_summary([0.0, 2.0], 0.5, 3.0)
    assert summary["unexplained_gap_count"] >= 1
    assert summary["unexplained_max_gap_s"] >= 1.5


def test_issue_rows_keep_defects_and_ignore_clean_closes():
    events = [
        {"time": 10.0, "kind": "page_error", "text": "boom"},
        {"time": 10.1, "kind": "console", "level": "warning", "text": "careful"},
        {"time": 10.2, "kind": "console", "level": "log", "text": "ignored"},
        {"time": 10.3, "kind": "request_failed", "url": "/x", "error": "ERR_X"},
        {"time": 10.4, "kind": "http", "url": "/y", "status": 503},
        {"time": 10.5, "kind": "http", "url": "/z", "status": 204},
        {"time": 10.6, "kind": "ws_close", "code": 1000, "reason": ""},
        {"time": 10.7, "kind": "ws_close", "code": 1006, "reason": "lost"},
    ]
    rows = fleet_soak.issue_rows(events, since=10.0)
    assert [row["kind"] for row in rows] == [
        "page_error", "console_warning", "request_failed", "http_error", "ws_close",
    ]
    assert rows[-1]["code"] == 1006


def test_expected_network_noise_is_scoped_to_the_recovered_client_and_window():
    issues = [
        {"time": 100.0, "client": "fleet-1", "kind": "request_failed",
         "url": "http://x", "error": "net::ERR_INTERNET_DISCONNECTED"},
        {"time": 100.1, "client": "fleet-1", "kind": "console_warning",
         "text": "connection attempt failed: Failed to fetch"},
        {"time": 100.2, "client": "fleet-1", "kind": "page_error", "text": "boom"},
        {"time": 100.3, "client": "fleet-2", "kind": "request_failed",
         "url": "http://x", "error": "net::ERR_INTERNET_DISCONNECTED"},
        {"time": 200.0, "client": "fleet-1", "kind": "request_failed",
         "url": "http://x", "error": "net::ERR_INTERNET_DISCONNECTED"},
    ]
    expected, unexpected = fleet_soak.split_expected_issues(
        issues, "fleet-1", (99.0, 110.0))
    assert len(expected) == 2
    assert {row["kind"] for row in unexpected} == {"page_error", "request_failed"}


def test_a_complete_soak_report_keeps_the_hardware_gate_missing():
    report = fleet_soak.build_soak_report(
        started_at="2026-10-25T00:00:00Z",
        finished_at="2026-10-25T00:01:00Z",
        checks=[{"name": "duration", "passed": True}],
        scenarios=[
            {"id": scenario, "status": "passed", "detail": None}
            for scenario in fleet_soak.SCENARIOS
        ],
        artifacts={},
        cohort=["a", "b"],
        tools={"browser": "test"},
        skipped=[],
        unobserved=["one deliberate pause"],
        limitations=["software only", "the two-hour physical soak remains MISSING"],
        repository={"head": "x", "branch": "y", "dirty": False},
    )
    assert report["schema"] == "tablet-wall-validation-evidence/1"
    assert report["gate"] == "soak"
    assert report["evidence_kind"] == "software-simulation"
    assert report["hardware_gate_status"] == "MISSING"
    assert report["hardware_claim"] is False
    assert report["completion"] == "complete"
    assert report["checks_passed"] == 1
    assert report["scenarios_passed"] == len(fleet_soak.SCENARIOS)


def test_a_failed_soak_check_blocks_completion_and_names_the_failure():
    report = fleet_soak.build_soak_report(
        started_at="2026-10-25T00:00:00Z",
        finished_at="2026-10-25T00:01:00Z",
        checks=[{"name": "no video stall was detected", "passed": False}],
        scenarios=[
            {"id": scenario, "status": "passed", "detail": None}
            for scenario in fleet_soak.SCENARIOS
        ],
        artifacts={},
        cohort=[],
        tools={},
        skipped=[],
        unobserved=[],
        limitations=[],
        repository={},
    )
    assert report["completion"] == "incomplete"
    assert report["failure_reasons"] == ["no video stall was detected"]


@pytest.mark.parametrize("argv", [
    ["--clients", "0"],
    ["--clients", "9"],
    ["--duration", "1"],
    ["--interval", "0"],
    ["--recovery-offline-seconds", "0"],
])
def test_cli_rejects_values_outside_the_harness_contract(argv):
    with pytest.raises(SystemExit):
        fleet_soak.main(argv)
