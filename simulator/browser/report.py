"""Normalize one browser evidence report into a common summary.

The browser runners do not share a report schema. Video, field, controller and
group recovery publish counts at the top level. Restore groups its checks by
area and publishes counts under ``summary``. Scenario runners publish
``scenario_results`` or ``scenarios`` instead. This adapter reads one report
at a time and returns the same fields for each shape. It never aggregates
reports or overlapping suites, and it never invents a count: an absent value
stays ``None`` and a contradiction is recorded in ``validation_problems``.

Summary shape::

    source, runner, runner_version, evidence_kind, head_sha, dirty,
    started_at, finished_at, browser_version, state, incomplete,
    expected_scenario_ids, scenario_results, scenario_counts,
    checks {passed, total, failed}, failure_reasons, error, artifacts,
    limitations, validation_problems, consistent

Runner identity is copied only when the report states it; it is not inferred
from the file path. ``failure_reasons`` holds objects with ``scope``,
``group``, ``scenario``, ``name`` and ``reason``. Each scenario row carries
its own reason strings. Scenario counts are derived from reported statuses
when the report has no explicit count, but check counts are read only from
explicit fields.

Usage::

    python -m simulator.browser.report PATH [PATH ...]

The command prints one JSON object per report and exits 1 when any report is
inconsistent.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCENARIO_STATUSES = ("passed", "failed", "skipped", "incomplete")


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _count(value: Any, label: str, problems: list[str]) -> int | None:
    """Accept an explicit integer count and record why it is unusable."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        problems.append(f"{label} is not an integer: {value!r}")
        return None
    if value < 0:
        problems.append(f"{label} is negative: {value}")
        return None
    return value


def _merged_count(
    label: str,
    primary: int | None,
    secondary: int | None,
    secondary_label: str,
    problems: list[str],
) -> int | None:
    if primary is not None and secondary is not None and primary != secondary:
        problems.append(f"{label} {primary} disagrees with {secondary_label} {secondary}")
    return primary if primary is not None else secondary


def _error_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, Mapping):
        kind = _text(value.get("type"))
        message = _text(value.get("message"))
        if kind and message:
            return f"{kind}: {message}"
        return message or kind
    return str(value)


def _reason(row: Mapping[str, Any]) -> str | None:
    for key in ("error", "reason", "failure", "message"):
        if key in row:
            text = _error_text(row[key])
            if text:
                return text
    return None


def _state(data: Mapping[str, Any]) -> str | None:
    return _text(data.get("state")) or _text(data.get("status"))


def _error(data: Mapping[str, Any]) -> str | None:
    return _error_text(data.get("error")) or _error_text(data.get("failure"))


def _incomplete(state: str | None, error: str | None) -> bool | None:
    if state:
        lowered = state.casefold()
        if lowered in {"incomplete", "partial", "running"}:
            return True
        if lowered in {"passed", "failed", "complete", "completed"}:
            return False
    if error is not None:
        return True
    return None


def _head_sha(data: Mapping[str, Any]) -> str | None:
    for key in ("head_sha", "head", "app_head"):
        text = _text(data.get(key))
        if text:
            return text
    repository = _mapping(data.get("repository"))
    return _text(repository.get("head")) if repository else None


def _dirty(data: Mapping[str, Any]) -> bool | None:
    if isinstance(data.get("dirty"), bool):
        return data["dirty"]
    for key in ("repository", "worktree"):
        container = _mapping(data.get(key))
        if container is not None and isinstance(container.get("dirty"), bool):
            return container["dirty"]
    return None


def _check_rows(
    checks: Any, problems: list[str]
) -> list[tuple[str | None, Mapping[str, Any]]] | None:
    """Return ``(group, row)`` pairs, or ``None`` when no check container exists."""
    if checks is None:
        return None
    rows: list[tuple[str | None, Mapping[str, Any]]] = []
    if isinstance(checks, list):
        for index, item in enumerate(checks):
            if isinstance(item, Mapping):
                rows.append((None, item))
            else:
                problems.append(f"checks[{index}] is not an object")
        return rows
    if isinstance(checks, Mapping):
        for group, items in checks.items():
            if not isinstance(items, list):
                problems.append(f"checks group {group!r} is not a list")
                continue
            for index, item in enumerate(items):
                if isinstance(item, Mapping):
                    rows.append((str(group), item))
                else:
                    problems.append(f"checks group {group!r}[{index}] is not an object")
        return rows
    problems.append("checks is neither a list nor a mapping of groups")
    return []


def _scenario_expected(data: Mapping[str, Any]) -> list[str] | None:
    raw = data.get("scenarios_expected")
    if isinstance(raw, Mapping):
        return [str(key) for key in raw]
    if isinstance(raw, list):
        expected: list[str] = []
        for item in raw:
            if isinstance(item, str):
                expected.append(item)
            elif isinstance(item, Mapping):
                ident = _text(item.get("id")) or _text(item.get("name"))
                if ident:
                    expected.append(ident)
        return expected
    order = data.get("scenario_order")
    if isinstance(order, list):
        return [item for item in order if isinstance(item, str)]
    scenarios = data.get("scenarios")
    if isinstance(scenarios, Mapping):
        return [str(key) for key in scenarios]
    return None


def _scenario_reasons(entry: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for key in ("error", "reason", "failure"):
        text = _error_text(entry.get(key))
        if text:
            reasons.append(text)
    checks = entry.get("checks")
    if isinstance(checks, list):
        for item in checks:
            if isinstance(item, Mapping) and item.get("passed") is False:
                name = _text(item.get("name")) or "check"
                reason = _reason(item)
                reasons.append(f"{name}: {reason}" if reason else name)
    return list(dict.fromkeys(reasons))


def _scenario_row(
    entry: Mapping[str, Any], fallback_id: str | None, problems: list[str]
) -> dict[str, Any]:
    ident = (
        _text(entry.get("id"))
        or _text(entry.get("scenario"))
        or fallback_id
        or _text(entry.get("name"))
    )
    name = _text(entry.get("name")) or _text(entry.get("title"))
    status = _text(entry.get("status")) or _text(entry.get("state"))
    checks = entry.get("checks")
    check_list = checks if isinstance(checks, list) else None
    if checks is not None and check_list is None and not isinstance(checks, int):
        problems.append(f"scenario {ident!r} checks is neither a count nor a list")

    total = _count(entry.get("checks_total"), f"scenario {ident!r} checks_total", problems)
    if total is None and isinstance(checks, int) and not isinstance(checks, bool):
        total = _count(checks, f"scenario {ident!r} checks", problems)
    passed = _count(entry.get("checks_passed"), f"scenario {ident!r} checks_passed", problems)
    failed = _count(entry.get("checks_failed"), f"scenario {ident!r} checks_failed", problems)
    if failed is None and entry.get("failed") is not None:
        failed = _count(entry["failed"], f"scenario {ident!r} failed", problems)

    if passed is not None and total is None:
        problems.append(f"scenario {ident!r} checks_passed is present while checks_total is absent")
    if passed is not None and total is not None and passed > total:
        problems.append(f"scenario {ident!r} checks_passed {passed} exceeds checks_total {total}")
    if check_list is not None and total is not None:
        if total > len(check_list):
            problems.append(
                f"scenario {ident!r} checks_total {total} exceeds the "
                f"{len(check_list)} check row(s) present"
            )
        elif total < len(check_list):
            problems.append(
                f"scenario {ident!r} checks_total {total} is less than the "
                f"{len(check_list)} check row(s) present"
            )

    return {
        "id": ident,
        "name": name,
        "status": status,
        "checks_passed": passed,
        "checks_total": total,
        "checks_failed": failed,
        "failure_reasons": _scenario_reasons(entry),
        "error": (
            _error_text(entry.get("error"))
            or _error_text(entry.get("reason"))
            or _error_text(entry.get("failure"))
        ),
    }


def _scenario_rows(
    data: Mapping[str, Any], problems: list[str]
) -> list[dict[str, Any]] | None:
    published = data.get("scenario_results")
    if published is not None:
        if not isinstance(published, list):
            problems.append("scenario_results is not a list")
            return []
        rows: list[dict[str, Any]] = []
        for index, entry in enumerate(published):
            if isinstance(entry, Mapping):
                rows.append(_scenario_row(entry, None, problems))
            else:
                problems.append(f"scenario_results[{index}] is not an object")
        return rows

    scenarios = data.get("scenarios")
    if scenarios is None:
        return None
    if isinstance(scenarios, Mapping):
        rows = []
        for key, entry in scenarios.items():
            if isinstance(entry, Mapping):
                rows.append(_scenario_row(entry, str(key), problems))
            else:
                problems.append(f"scenarios[{key!r}] is not an object")
        return rows
    if isinstance(scenarios, list):
        rows = []
        for index, entry in enumerate(scenarios):
            if isinstance(entry, Mapping):
                rows.append(_scenario_row(entry, None, problems))
            else:
                problems.append(f"scenarios[{index}] is not an object")
        return rows
    problems.append("scenarios is neither a list nor a mapping")
    return []


def _scenario_counts(
    data: Mapping[str, Any],
    rows: list[dict[str, Any]] | None,
    problems: list[str],
) -> dict[str, int | None]:
    explicit = {
        status: _count(data.get(f"scenarios_{status}"), f"scenarios_{status}", problems)
        for status in SCENARIO_STATUSES
    }
    explicit["total"] = _count(data.get("scenarios_total"), "scenarios_total", problems)

    if rows is None:
        derived: dict[str, int] | None = None
    else:
        derived = {status: 0 for status in SCENARIO_STATUSES}
        for row in rows:
            status = (row["status"] or "").casefold()
            if status == "running":
                status = "incomplete"
            if status in derived:
                derived[status] += 1

    counts: dict[str, int | None] = {}
    for status in SCENARIO_STATUSES:
        counts[status] = (
            explicit[status]
            if explicit[status] is not None
            else (derived[status] if derived is not None else None)
        )
    counts["total"] = (
        explicit["total"]
        if explicit["total"] is not None
        else (len(rows) if rows is not None else None)
    )

    if explicit["passed"] is not None and explicit["total"] is None:
        problems.append("scenarios_passed is present while scenarios_total is absent")
    if rows is not None and derived is not None:
        for status in SCENARIO_STATUSES:
            if explicit[status] is not None and explicit[status] != derived[status]:
                problems.append(
                    f"scenarios_{status} {explicit[status]} disagrees with "
                    f"{derived[status]} scenario row(s) marked {status}"
                )
        if explicit["total"] is not None and explicit["total"] != len(rows):
            if explicit["total"] > len(rows):
                problems.append(
                    f"scenarios_total {explicit['total']} exceeds the "
                    f"{len(rows)} scenario row(s) present"
                )
            else:
                problems.append(
                    f"scenarios_total {explicit['total']} is less than the "
                    f"{len(rows)} scenario row(s) present"
                )
    known = [counts[status] for status in SCENARIO_STATUSES]
    if counts["total"] is not None and all(value is not None for value in known):
        if sum(value for value in known if value is not None) > counts["total"]:
            problems.append("scenario pass/fail/skip counts exceed scenarios_total")
    return counts


def _failure_reasons(
    rows: list[tuple[str | None, Mapping[str, Any]]] | None,
    scenario_rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    def add(scope: str, group: str | None, scenario: str | None,
            name: str | None, reason: str | None) -> None:
        key = (scope, group, scenario, name, reason)
        if key in seen:
            return
        seen.add(key)
        reasons.append({
            "scope": scope,
            "group": group,
            "scenario": scenario,
            "name": name,
            "reason": reason,
        })

    for group, row in rows or []:
        if row.get("passed") is not False:
            continue
        add(
            "check",
            group,
            _text(row.get("scenario")),
            _text(row.get("name")) or _text(row.get("id")),
            _reason(row),
        )
    for row in scenario_rows or []:
        if row["error"]:
            add("scenario", None, row["id"], row["name"], row["error"])
    return reasons


def _empty_summary(source: str | None = None) -> dict[str, Any]:
    return {
        "source": source,
        "runner": None,
        "runner_version": None,
        "evidence_kind": None,
        "head_sha": None,
        "dirty": None,
        "started_at": None,
        "finished_at": None,
        "browser_version": None,
        "state": None,
        "incomplete": None,
        "expected_scenario_ids": None,
        "scenario_results": None,
        "scenario_counts": {
            **{status: None for status in SCENARIO_STATUSES},
            "total": None,
        },
        "checks": {"passed": None, "total": None, "failed": None},
        "failure_reasons": [],
        "error": None,
        "artifacts": None,
        "limitations": None,
        "validation_problems": [],
        "consistent": True,
    }


def normalize_report(
    report: Mapping[str, Any], *, source: str | None = None
) -> dict[str, Any]:
    """Normalize one report dict; never merge it with another report."""
    if not isinstance(report, Mapping):
        raise TypeError("report must be a mapping")

    summary = _empty_summary(source)
    problems = summary["validation_problems"]

    summary["runner"] = _text(report.get("runner")) or _text(report.get("runner_name"))
    summary["runner_version"] = report.get("runner_version")
    summary["evidence_kind"] = _text(report.get("evidence_kind"))
    summary["head_sha"] = _head_sha(report)
    summary["dirty"] = _dirty(report)
    summary["started_at"] = _text(report.get("started_at")) or _text(report.get("started_utc"))
    summary["finished_at"] = _text(report.get("finished_at")) or _text(report.get("finished_utc"))
    summary["browser_version"] = _text(report.get("browser_version"))
    summary["state"] = _state(report)
    summary["error"] = _error(report)
    summary["incomplete"] = _incomplete(summary["state"], summary["error"])
    summary["artifacts"] = _text(report.get("artifacts"))
    limitations = report.get("limitations")
    summary["limitations"] = (
        [item for item in limitations if isinstance(item, str)]
        if isinstance(limitations, list)
        else None
    )

    summary["expected_scenario_ids"] = _scenario_expected(report)
    scenario_rows = _scenario_rows(report, problems)
    summary["scenario_results"] = scenario_rows
    summary["scenario_counts"] = _scenario_counts(report, scenario_rows, problems)

    rows = _check_rows(report.get("checks"), problems)
    summary["checks"] = _check_counts(report, rows, problems)
    summary["failure_reasons"] = _failure_reasons(rows, scenario_rows)
    summary["consistent"] = not problems
    return summary


def _check_counts(
    report: Mapping[str, Any],
    rows: list[tuple[str | None, Mapping[str, Any]]] | None,
    problems: list[str],
) -> dict[str, int | None]:
    summary = _mapping(report.get("summary"))
    if report.get("summary") is not None and summary is None:
        problems.append("summary is not an object")
    summary = summary or {}

    top_passed = _count(report.get("checks_passed"), "checks_passed", problems)
    top_total = _count(report.get("checks_total"), "checks_total", problems)
    top_failed = _count(report.get("checks_failed"), "checks_failed", problems)

    summary_passed = _count(
        summary.get("checks_passed"), "summary.checks_passed", problems
    )
    summary_total = _count(summary.get("checks_total"), "summary.checks_total", problems)

    passed = _merged_count(
        "checks_passed", top_passed, summary_passed, "summary.checks_passed", problems
    )
    total = _merged_count(
        "checks_total", top_total, summary_total, "summary.checks_total", problems
    )
    failed = top_failed
    if failed is None:
        failed = _count(summary.get("checks_failed"), "summary.checks_failed", problems)

    if passed is not None and total is None:
        problems.append("checks_passed is present while checks_total is absent")
    if passed is not None and total is not None and passed > total:
        problems.append(f"checks_passed {passed} exceeds checks_total {total}")

    derived_failed = (
        total - passed
        if total is not None and passed is not None and total >= passed
        else None
    )
    if failed is not None and derived_failed is not None and failed != derived_failed:
        problems.append(
            f"checks_failed {failed} disagrees with "
            f"checks_total - checks_passed ({derived_failed})"
        )
    if failed is None:
        failed = derived_failed

    if rows is not None:
        present = len(rows)
        for label, value in (
            ("checks_total", total),
            ("checks_passed", passed),
            ("checks_failed", failed),
        ):
            if value is not None and value > present:
                problems.append(f"{label} {value} exceeds the {present} check row(s) present")
        if total is not None and total < present:
            problems.append(f"checks_total {total} is less than the {present} check row(s) present")

    return {"passed": passed, "total": total, "failed": failed}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m simulator.browser.report",
        description="Normalize browser evidence reports; exit 1 on inconsistency.",
    )
    parser.add_argument("paths", metavar="PATH", nargs="+", type=Path)
    args = parser.parse_args(argv)

    status = 0
    for path in args.paths:
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(report, dict):
                raise ValueError("report is not a JSON object")
        except (OSError, ValueError) as error:
            summary = _empty_summary(str(path))
            summary["validation_problems"] = [f"cannot read report: {error}"]
            summary["consistent"] = False
        else:
            summary = normalize_report(report, source=str(path))
        print(json.dumps(summary, sort_keys=True))
        if not summary["consistent"]:
            status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
