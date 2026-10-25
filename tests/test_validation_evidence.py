"""The shared validation evidence contract keeps gates open and failures visible."""

from pathlib import Path

import pytest

from tools.validation import evidence


def test_a_passing_report_is_complete_but_never_a_hardware_claim():
    report = evidence.build_report(
        tool="optical-analyzer",
        tool_version="1",
        gate="optical-cut-timing",
        evidence_kind="synthetic",
        started_at="2026-10-25T00:00:00Z",
        checks=[evidence.check_row("known offset recovered", True)],
        scenarios=[evidence.scenario_row("offset-30ms", "passed")],
        expected_scenarios=["offset-30ms"],
        limitations=["synthetic only"],
    )
    assert report["completion"] == "complete"
    assert report["hardware_gate_status"] == "MISSING"
    assert report["hardware_claim"] is False
    assert report["checks_passed"] == 1
    assert report["scenarios_passed"] == 1
    assert report["failure_reasons"] == []


def test_a_failed_check_and_missing_scenario_block_completion():
    report = evidence.build_report(
        tool="trust-check",
        tool_version="1",
        gate="installed-ca-trust",
        evidence_kind="disposable-ingress",
        started_at="2026-10-25T00:00:00Z",
        checks=[evidence.check_row("backend blocked", False)],
        scenarios=[evidence.scenario_row("operator", "passed")],
        expected_scenarios=["operator", "tablet"],
        skipped=["tablet trust install"],
    )
    assert report["completion"] == "incomplete"
    assert "backend blocked" in report["failure_reasons"]
    assert any(row["id"] == "tablet" and row["status"] == "incomplete"
               for row in report["scenarios"])
    assert "tablet trust install" in report["skipped"]


def test_an_unsupported_scenario_and_error_stay_explicit():
    report = evidence.build_report(
        tool="device-probe",
        tool_version="1",
        gate="ios-safari",
        evidence_kind="desktop-browser",
        started_at="2026-10-25T00:00:00Z",
        checks=[],
        scenarios=[evidence.scenario_row("ios", "unsupported", detail="no device")],
        error={"type": "Unavailable"},
    )
    assert report["completion"] == "incomplete"
    assert report["error"] == {"type": "Unavailable"}


def test_the_contract_rejects_unknown_gates_and_evidence_kinds():
    with pytest.raises(ValueError):
        evidence.build_report(
            tool="x", tool_version="1", gate="made-up", evidence_kind="synthetic",
            started_at="now", checks=[],
        )
    with pytest.raises(ValueError):
        evidence.build_report(
            tool="x", tool_version="1", gate="soak", evidence_kind="made-up",
            started_at="now", checks=[],
        )


def test_artifact_hashes_and_missing_paths_are_explicit(tmp_path: Path):
    present = tmp_path / "frame.png"
    present.write_bytes(b"frame")
    rows = evidence.artifact_hashes([present, tmp_path / "missing.bin"])
    assert rows[str(present)]["exists"] is True
    assert rows[str(present)]["bytes"] == 5
    assert len(rows[str(present)]["sha256"]) == 64
    assert rows[str(tmp_path / "missing.bin")]["exists"] is False


def test_repository_state_never_claims_a_fetch():
    state = evidence.repository_state(Path(__file__).resolve().parents[1])
    assert "head" in state and "dirty" in state and "branch" in state
