"""Shared evidence report contract for the hardware-validation kit.

The kit executes tools; it does not close a physical gate. Every report keeps
the application lineage, tool versions, original cohort, expected and observed
scenarios, failures, skipped/unobserved intervals, artifact hashes and an
explicit completion state. A caller may not label a desktop or synthetic run
as hardware acceptance.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

SCHEMA = "tablet-wall-validation-evidence/1"
EVIDENCE_KINDS = (
    "synthetic",
    "desktop-browser",
    "software-simulation",
    "disposable-ingress",
    "operator-hardware",
)
HARDWARE_GATES = (
    "optical-cut-timing",
    "physical-decode-suspend",
    "ios-safari",
    "mixed-model-calibration",
    "installed-ca-trust",
    "real-wifi-os",
    "kiosk",
    "soak",
)


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def repository_state(root: Path) -> dict[str, Any]:
    """Head, branch and dirty state without fetching or changing refs."""
    def run(*args: str) -> str:
        try:
            done = subprocess.run(
                ["git", "-C", str(root), *args],
                capture_output=True, text=True, timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        return done.stdout.strip()

    return {
        "head": run("rev-parse", "HEAD") or None,
        "branch": run("rev-parse", "--abbrev-ref", "HEAD") or None,
        "dirty": bool(run("status", "--porcelain")),
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_hashes(paths: list[Path]) -> dict[str, dict[str, Any]]:
    """Map each existing path to size/sha256; missing paths stay explicit."""
    rows: dict[str, dict[str, Any]] = {}
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            rows[str(path)] = {"exists": False, "bytes": None, "sha256": None}
            continue
        rows[str(path)] = {
            "exists": True,
            "bytes": stat.st_size,
            "sha256": file_sha256(path) if path.is_file() else None,
        }
    return rows


def check_row(name: str, passed: bool, **detail: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), **detail}


def scenario_row(
    scenario_id: str, status: str, *, detail: Any = None,
) -> dict[str, Any]:
    if status not in ("passed", "failed", "skipped", "incomplete", "unsupported"):
        raise ValueError("scenario status is not part of the evidence contract")
    return {"id": scenario_id, "status": status, "detail": detail}


def failure_reasons(checks: list[dict[str, Any]]) -> list[str]:
    return [
        str(item.get("name", "unnamed check"))
        for item in checks if not item.get("passed")
    ]


def build_report(
    *,
    tool: str,
    tool_version: str,
    gate: str,
    evidence_kind: str,
    started_at: str,
    checks: list[dict[str, Any]],
    scenarios: list[dict[str, Any]] | None = None,
    artifacts: dict[str, dict[str, Any]] | None = None,
    cohort: list[str] | None = None,
    expected_scenarios: list[str] | None = None,
    tools: dict[str, Any] | None = None,
    skipped: list[str] | None = None,
    unobserved: list[str] | None = None,
    limitations: list[str] | None = None,
    error: dict[str, Any] | None = None,
    repository: dict[str, Any] | None = None,
    finished_at: str | None = None,
) -> dict[str, Any]:
    """Build one bounded report. It never promotes evidence to a hardware gate."""
    if gate not in HARDWARE_GATES:
        raise ValueError("gate is not one of the published hardware gates")
    if evidence_kind not in EVIDENCE_KINDS:
        raise ValueError("evidence kind is not part of the contract")
    rows = list(scenarios or [])
    if expected_scenarios is not None:
        present = {row["id"] for row in rows}
        for scenario_id in expected_scenarios:
            if scenario_id not in present:
                rows.append(scenario_row(scenario_id, "incomplete"))
    failed = failure_reasons(checks)
    scenarios_failed = [row["id"] for row in rows if row["status"] == "failed"]
    scenarios_skipped = [row["id"] for row in rows if row["status"] == "skipped"]
    scenarios_unsupported = [row["id"] for row in rows if row["status"] == "unsupported"]
    complete = (
        not failed and not scenarios_failed and not scenarios_skipped
        and not scenarios_unsupported and error is None
        and all(row["status"] in ("passed", "incomplete") for row in rows)
    )
    return {
        "schema": SCHEMA,
        "tool": tool,
        "tool_version": tool_version,
        "gate": gate,
        "evidence_kind": evidence_kind,
        "hardware_gate_status": "MISSING",
        "hardware_claim": False,
        "repository": repository or {},
        "started_at": started_at,
        "finished_at": finished_at or iso_now(),
        "cohort": list(cohort or []),
        "expected_scenarios": list(expected_scenarios or []),
        "scenarios": rows,
        "checks": list(checks),
        "checks_passed": sum(1 for item in checks if item.get("passed")),
        "checks_total": len(checks),
        "failure_reasons": failed + scenarios_failed,
        "scenarios_passed": sum(1 for row in rows if row["status"] == "passed"),
        "scenarios_total": len(rows),
        "skipped": list(skipped or []) + scenarios_skipped,
        "unobserved": list(unobserved or []),
        "tools": tools or {},
        "artifacts": artifacts or {},
        "limitations": list(limitations or []),
        "completion": "complete" if complete else "incomplete",
        "error": error,
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def load_report(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text())
    if report.get("schema") != SCHEMA:
        raise ValueError("not a validation evidence report")
    return report
