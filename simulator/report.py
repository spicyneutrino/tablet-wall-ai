"""Scenario records and the JSON report the simulator writes.

A run produces one :class:`Recorder` with a :class:`ScenarioResult` per
scenario; each result carries the checks that ran (name, ok, expected,
actual) and the informational notes (measured geometry, timings, counts).
``run.py`` turns that into the JSON file and the process exit code.

Checks fail *loudly and locally*: a failing ``expect`` raises
:class:`ScenarioAbort`, which stops that one scenario — later checks in it
would be meaningless — while every other scenario still runs, so one report
shows the whole picture.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ScenarioAbort(Exception):
    """A check failed; stop this scenario, keep the run going."""


@dataclass
class Check:
    name: str
    ok: bool
    expected: Any = None
    actual: Any = None
    detail: str = ""


@dataclass
class ScenarioResult:
    id: str
    title: str
    status: str = "pending"  # passed | failed | error
    duration_s: float = 0.0
    checks: list[Check] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""


def _jsonable(value: Any) -> Any:
    """Best-effort conversion so an odd object never breaks the report."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)


class Recorder:
    """Collects checks/notes for the scenario that is currently running."""

    def __init__(self) -> None:
        self.scenarios: list[ScenarioResult] = []
        self._current: ScenarioResult | None = None

    # -- lifecycle ---------------------------------------------------------
    def begin(self, scenario_id: str, title: str) -> ScenarioResult:
        result = ScenarioResult(id=scenario_id, title=title)
        self.scenarios.append(result)
        self._current = result
        return result

    def finish(self, status: str, duration_s: float, error: str = "") -> None:
        if self._current is None:
            return
        self._current.status = status
        self._current.duration_s = round(duration_s, 4)
        self._current.error = error
        self._current = None

    # -- recording ---------------------------------------------------------
    def observe(
        self,
        name: str,
        ok: bool,
        expected: Any = None,
        actual: Any = None,
        detail: str = "",
    ) -> Check:
        """Record a check result without aborting; returns the Check.

        Used by audits (``run.py``'s teardown) where every check must be
        recorded even when an earlier one failed — and where the *steps*
        between the checks (removing the temp dir, fingerprinting the repo)
        must not be skipped by a failure either. Scenario checks go through
        :meth:`expect`, which raises on the first failure instead.
        """
        normalised_expected = _jsonable(expected)
        normalised_actual = _jsonable(actual)
        check = Check(
            name=name,
            ok=bool(ok),
            expected=(
                None
                if ok and normalised_expected == normalised_actual
                else normalised_expected
            ),
            actual=normalised_actual,
            detail=detail,
        )
        if self._current is not None:
            self._current.checks.append(check)
        return check

    def expect(
        self,
        name: str,
        ok: bool,
        expected: Any = None,
        actual: Any = None,
        detail: str = "",
    ) -> None:
        """Record a pass/fail check; a failure aborts the current scenario.

        A *passing* check drops ``expected`` when it equals ``actual``: the
        name plus the observed value already say what was asserted, and
        keeping both doubles the report for no information. Failures always
        keep both, because the difference is the whole point.
        """
        check = self.observe(name, ok, expected=expected, actual=actual, detail=detail)
        if not check.ok:
            raise ScenarioAbort(
                f"{name}: expected {check.expected!r}, got {check.actual!r}"
                + (f" ({detail})" if detail else "")
            )

    def eq(self, name: str, actual: Any, expected: Any, detail: str = "") -> None:
        """Equality shorthand: ``actual`` is what the system really did."""
        self.expect(
            name,
            actual == expected,
            expected=_jsonable(expected),
            actual=_jsonable(actual),
            detail=detail,
        )

    def note(self, name: str, value: Any, unit: str = "") -> None:
        """Record a measurement that is reported but never fails a run."""
        if self._current is None:
            return
        entry: dict[str, Any] = {"name": name, "value": _jsonable(value)}
        if unit:
            entry["unit"] = unit
        self.current_notes().append(entry)

    def current_notes(self) -> list[dict[str, Any]]:
        if self._current is None:
            return []
        return self._current.notes

    # -- summary -----------------------------------------------------------
    @property
    def check_counts(self) -> dict[str, int]:
        passed = failed = 0
        for scenario in self.scenarios:
            for check in scenario.checks:
                if check.ok:
                    passed += 1
                else:
                    failed += 1
        return {"total": passed + failed, "passed": passed, "failed": failed}

    @property
    def scenario_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for scenario in self.scenarios:
            counts[scenario.status] = counts.get(scenario.status, 0) + 1
        return counts

    @property
    def ok(self) -> bool:
        """True only when every began scenario finished as ``passed``.

        A scenario that was begun but never finished stays ``pending`` and
        *fails* the run: a half-run must never read as green. So does a run
        that recorded no scenario at all.
        """
        counts = self.check_counts
        return (
            counts["failed"] == 0
            and bool(self.scenarios)
            and all(scenario.status == "passed" for scenario in self.scenarios)
        )

    def reconcile_pending(self) -> list[str]:
        """Close out scenarios begun but never finished; returns their ids.

        ``run.py`` calls this once after the scenario loop: anything still
        ``pending`` (an interruption between ``begin`` and ``finish`` that
        the loop's own handlers did not cover) is marked as an error, so
        the summary and the exit code cannot miss it.
        """
        pending = [
            scenario for scenario in self.scenarios if scenario.status == "pending"
        ]
        for scenario in pending:
            scenario.status = "error"
            if not scenario.error:
                scenario.error = "scenario did not finish"
        self._current = None
        return [scenario.id for scenario in pending]

    def failures(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for scenario in self.scenarios:
            # Anything not passed is a failure to report — including a
            # "pending" scenario that never finished, not just failed/error.
            if scenario.status != "passed":
                out.append(
                    {
                        "scenario": scenario.id,
                        "title": scenario.title,
                        "status": scenario.status,
                        "error": scenario.error,
                        "failed_checks": [
                            {
                                "name": check.name,
                                "expected": check.expected,
                                "actual": check.actual,
                                "detail": check.detail,
                            }
                            for check in scenario.checks
                            if not check.ok
                        ],
                    }
                )
        return out

    def to_dict(self, meta: dict[str, Any]) -> dict[str, Any]:
        payload = dict(meta)
        payload["summary"] = {
            "scenarios": self.scenario_counts,
            "checks": self.check_counts,
            "ok": self.ok,
        }
        payload["scenarios"] = [
            {
                "id": scenario.id,
                "title": scenario.title,
                "status": scenario.status,
                "duration_s": scenario.duration_s,
                "error": scenario.error,
                "checks": [check.__dict__ for check in scenario.checks],
                "notes": scenario.notes,
            }
            for scenario in self.scenarios
        ]
        payload["failures"] = self.failures()
        payload["exit_code"] = 0 if self.ok else 1
        return payload

    def write(self, path: str | Path, meta: dict[str, Any]) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = self.to_dict(meta)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return target
