"""Cases for the browser report adapter. No browser or /tmp dependency."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from simulator.browser import report

REPO = Path(__file__).resolve().parents[2]


def top_level_report(*, passed=1, total=2, failed=1, state="failed"):
    return {
        "runner": "video_run",
        "runner_version": 2,
        "evidence_kind": "software browser; not optical or physical",
        "head_sha": "a" * 40,
        "branch": "main",
        "dirty": False,
        "started_at": "2026-10-25T00:00:00Z",
        "finished_at": "2026-10-25T00:05:00Z",
        "browser_version": "141.0.7390.0",
        "state": state,
        "artifacts": "/artifacts/video",
        "checks": [
            {"name": "the video upload succeeds", "passed": True},
            {"name": "the picture stays visible", "passed": False,
             "error": "the element was hidden"},
        ],
        "checks_passed": passed,
        "checks_total": total,
        "checks_failed": failed,
        "error": None,
    }


def restore_report():
    return {
        "label": "software, not optical or physical",
        "started_utc": "2026-10-25T00:00:00+00:00",
        "finished_utc": "2026-10-25T00:01:00+00:00",
        "artifacts": "/artifacts/restore",
        "limitations": [
            "software evidence on one host clock; not optical output",
            "no physical decode, tablet, TLS, Caddy ingress or host restart",
        ],
        "checks": {
            "closure": [
                {"name": "the operator route publishes the still", "passed": True},
            ],
            "playback": [
                {"name": "the restored client plays the video", "passed": False,
                 "error": "the restored player stayed paused"},
            ],
        },
        "summary": {"checks_passed": 1, "checks_total": 2, "passed": False},
    }


def scenario_report():
    return {
        "runner": "video_transitions_run",
        "runner_version": 1,
        "evidence_kind": "software browser; not optical or physical",
        "state": "failed",
        "checks": [
            {"scenario": "T1", "name": "the cut ran", "passed": True},
            {"scenario": "T2", "name": "b", "passed": False,
             "reason": "the frame did not advance"},
            {"scenario": "T3", "name": "the environment check ran", "passed": True},
        ],
        "checks_passed": 2,
        "checks_total": 3,
        "checks_failed": 1,
        "scenario_order": ["T1", "T2", "T3"],
        "scenarios": {
            "T1": {
                "id": "T1", "title": "the cut", "status": "passed",
                "checks": [{"name": "the cut ran", "passed": True}],
                "checks_passed": 1, "checks_total": 1,
            },
            "T2": {
                "id": "T2", "title": "the loop", "status": "failed",
                "checks": [{"name": "b", "passed": False,
                            "reason": "the frame did not advance"}],
                "checks_passed": 0, "checks_total": 1,
            },
            "T3": {
                "id": "T3", "title": "the environment check", "status": "skipped",
                "checks": [], "checks_passed": 0, "checks_total": 0,
            },
        },
    }


def test_top_level_report_is_normalized():
    summary = report.normalize_report(top_level_report())

    assert summary["runner"] == "video_run"
    assert summary["runner_version"] == 2
    assert summary["evidence_kind"] == "software browser; not optical or physical"
    assert summary["head_sha"] == "a" * 40
    assert summary["dirty"] is False
    assert summary["started_at"] == "2026-10-25T00:00:00Z"
    assert summary["finished_at"] == "2026-10-25T00:05:00Z"
    assert summary["browser_version"] == "141.0.7390.0"
    assert summary["state"] == "failed"
    assert summary["incomplete"] is False
    assert summary["expected_scenario_ids"] is None
    assert summary["scenario_results"] is None
    assert summary["scenario_counts"] == {
        "passed": None, "failed": None, "skipped": None,
        "incomplete": None, "total": None,
    }
    assert summary["checks"] == {"passed": 1, "total": 2, "failed": 1}
    assert summary["failure_reasons"] == [{
        "scope": "check",
        "group": None,
        "scenario": None,
        "name": "the picture stays visible",
        "reason": "the element was hidden",
    }]
    assert summary["error"] is None
    assert summary["artifacts"] == "/artifacts/video"
    assert summary["limitations"] is None
    assert summary["validation_problems"] == []
    assert summary["consistent"] is True


def test_restore_grouped_checks_use_summary_counts_without_runner_identity():
    summary = report.normalize_report(restore_report())

    assert summary["runner"] is None
    assert summary["runner_version"] is None
    assert summary["evidence_kind"] is None
    assert summary["head_sha"] is None
    assert summary["dirty"] is None
    assert summary["started_at"] == "2026-10-25T00:00:00+00:00"
    assert summary["finished_at"] == "2026-10-25T00:01:00+00:00"
    assert summary["state"] is None
    assert summary["incomplete"] is None
    assert summary["expected_scenario_ids"] is None
    assert summary["scenario_results"] is None
    assert summary["checks"] == {"passed": 1, "total": 2, "failed": 1}
    assert summary["failure_reasons"] == [{
        "scope": "check",
        "group": "playback",
        "scenario": None,
        "name": "the restored client plays the video",
        "reason": "the restored player stayed paused",
    }]
    assert summary["artifacts"] == "/artifacts/restore"
    assert summary["limitations"] == [
        "software evidence on one host clock; not optical output",
        "no physical decode, tablet, TLS, Caddy ingress or host restart",
    ]
    assert summary["consistent"] is True


def test_scenario_rows_and_counts_are_not_summed_into_checks():
    summary = report.normalize_report(scenario_report())

    assert summary["expected_scenario_ids"] == ["T1", "T2", "T3"]
    assert [row["id"] for row in summary["scenario_results"]] == ["T1", "T2", "T3"]
    assert summary["scenario_counts"] == {
        "passed": 1, "failed": 1, "skipped": 1, "incomplete": 0, "total": 3,
    }
    assert summary["scenario_results"][1] == {
        "id": "T2",
        "name": "the loop",
        "status": "failed",
        "checks_passed": 0,
        "checks_total": 1,
        "checks_failed": None,
        "failure_reasons": ["b: the frame did not advance"],
        "error": None,
    }
    # The runner's top-level checks total is authoritative. Scenario checks
    # overlap it and are never added to it.
    assert summary["checks"] == {"passed": 2, "total": 3, "failed": 1}
    assert summary["consistent"] is True


def test_partial_report_keeps_its_state_and_does_not_gain_counts():
    summary = report.normalize_report({
        "runner": "video_run",
        "runner_version": 2,
        "state": "incomplete",
        "checks": [{"name": "the upload succeeded", "passed": True}],
        "checks_passed": 1,
        "checks_total": 1,
        "error": "RuntimeError: the browser closed",
        "artifacts": "/artifacts/partial",
    })

    assert summary["state"] == "incomplete"
    assert summary["incomplete"] is True
    assert summary["error"] == "RuntimeError: the browser closed"
    assert summary["checks"] == {"passed": 1, "total": 1, "failed": 0}
    assert summary["scenario_counts"] == {
        "passed": None, "failed": None, "skipped": None,
        "incomplete": None, "total": None,
    }
    assert summary["head_sha"] is None
    assert summary["browser_version"] is None
    assert summary["validation_problems"] == []
    assert summary["consistent"] is True


def test_controller_scenario_results_keep_their_ids_and_counts():
    summary = report.normalize_report({
        "runner": "controller_run",
        "runner_version": 1,
        "head": "b" * 40,
        "dirty": True,
        "status": "failed",
        "scenarios_expected": {"S1": "pause", "S2": "resume"},
        "checks": [
            {"scenario": "S1", "name": "the pause chip updates", "passed": True},
            {"scenario": "S2", "name": "the resume summary updates", "passed": True},
        ],
        "checks_passed": 1,
        "checks_total": 2,
        "scenario_results": [
            {"id": "S1", "name": "pause", "status": "passed", "checks": 1, "failed": 0},
            {"id": "S2", "name": "resume", "status": "failed", "checks": 1, "failed": 1},
        ],
    })

    assert summary["expected_scenario_ids"] == ["S1", "S2"]
    assert summary["scenario_results"][1] == {
        "id": "S2",
        "name": "resume",
        "status": "failed",
        "checks_passed": None,
        "checks_total": 1,
        "checks_failed": 1,
        "failure_reasons": [],
        "error": None,
    }
    assert summary["scenario_counts"] == {
        "passed": 1, "failed": 1, "skipped": 0, "incomplete": 0, "total": 2,
    }
    assert summary["incomplete"] is False
    assert summary["consistent"] is True


def test_legacy_metadata_and_failure_are_read_without_inventing_a_state():
    summary = report.normalize_report({
        "app_head": "c" * 40,
        "worktree": {"dirty": True},
        "started_utc": "2026-10-25T00:00:00+00:00",
        "checks": [{"name": "the app loaded", "passed": True}],
        "failure": {"type": "CancelledError", "message": "signal SIGTERM"},
    })

    assert summary["head_sha"] == "c" * 40
    assert summary["dirty"] is True
    assert summary["state"] is None
    assert summary["error"] == "CancelledError: signal SIGTERM"
    assert summary["incomplete"] is True
    assert summary["checks"] == {"passed": None, "total": None, "failed": None}
    assert summary["consistent"] is True


@pytest.mark.parametrize(
    ("report_dict", "problem"),
    [
        (
            {
                "checks_passed": 1,
                "checks_total": 2,
                "checks": [{"name": "one", "passed": True}],
                "summary": {"checks_passed": 2, "checks_total": 2},
            },
            "disagrees",
        ),
        (
            {
                "checks_passed": 2,
                "checks_total": 3,
                "checks": [{"name": "one", "passed": True},
                           {"name": "two", "passed": True}],
            },
            "exceeds",
        ),
        (
            {
                "checks_passed": -1,
                "checks_total": 1,
                "checks": [{"name": "one", "passed": True}],
            },
            "negative",
        ),
        (
            {"checks_passed": 1, "checks": [{"name": "one", "passed": True}]},
            "absent",
        ),
        (
            {
                "checks_passed": 1,
                "checks_total": 1,
                "checks_failed": 1,
                "checks": [{"name": "one", "passed": True}],
            },
            "checks_failed",
        ),
        (
            {
                "scenarios_passed": 2,
                "scenarios_total": 2,
                "scenarios": [{"id": "S1", "status": "passed"}],
            },
            "scenarios_passed",
        ),
        (
            {
                "scenario_results": [{
                    "id": "S1",
                    "status": "passed",
                    "checks_passed": 2,
                    "checks_total": 2,
                    "checks": [{"name": "one", "passed": True}],
                }],
            },
            "checks_total",
        ),
    ],
)
def test_inconsistent_reports_are_flagged(report_dict, problem):
    summary = report.normalize_report(report_dict)

    assert summary["consistent"] is False
    assert summary["validation_problems"]
    assert any(problem in item for item in summary["validation_problems"])


def test_cli_prints_one_object_per_report_and_exits_one_on_inconsistency(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({
        "runner": "video_run",
        "checks": [{"name": "one", "passed": True}],
        "checks_passed": 1,
        "checks_total": 1,
    }))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({
        "checks_passed": 2,
        "checks_total": 3,
        "checks": [{"name": "one", "passed": True}],
    }))

    result = subprocess.run(
        [sys.executable, "-m", "simulator.browser.report", str(good), str(bad)],
        cwd=REPO, capture_output=True, text=True, timeout=30,
    )

    assert result.returncode == 1, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert [row["source"] for row in rows] == [str(good), str(bad)]
    assert rows[0]["consistent"] is True
    assert rows[1]["consistent"] is False
    assert rows[1]["checks"] == {"passed": 2, "total": 3, "failed": 1}


def test_cli_exits_zero_when_every_report_is_consistent(tmp_path):
    path = tmp_path / "ok.json"
    path.write_text(json.dumps({
        "checks": [{"name": "one", "passed": True}],
        "checks_passed": 1,
        "checks_total": 1,
    }))

    result = subprocess.run(
        [sys.executable, "-m", "simulator.browser.report", str(path)],
        cwd=REPO, capture_output=True, text=True, timeout=30,
    )

    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["consistent"] is True
