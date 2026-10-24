"""Pure analysis of hard-cut software evidence. Software onset, not optical.

Every figure produced here is the time a page called ``drawImage`` for the new
asset, read from ``performance.timeOrigin + performance.now()`` in each
renderer. Pages share one host clock, so the figures are comparable between
clients. They exclude decode-to-glass, compositor, panel scanout and camera
uncertainty, and they never close the optical gate.

An event is one committed occurrence (``loop * items + item_index``). It is
complete only when every member of the planned cohort painted the right
content. A member without a commit, without a paint, or with the wrong pixel
makes the event failed. A failed event is counted, never dropped, and the
whole-show percentiles treat it as unbounded.
"""

from __future__ import annotations

import math
from typing import Any

LABEL = "software, not optical"
PIXEL_TOLERANCE = 40
# A commit that arrives later than the item's dwell would imply is a re-anchor.
GAP_TOLERANCE_MS = 150.0


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile; ``inf`` sorts last. None for no samples."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def _finite(value: float | None) -> float | None:
    if value is None or math.isinf(value) or math.isnan(value):
        return None
    return round(value, 3)


def summarize(values: list[float]) -> dict[str, Any]:
    """p50/p95/max with ``None`` when a statistic is unbounded or unavailable."""
    return {
        "n": len(values),
        "p50": _finite(percentile(values, 50)),
        "p95": _finite(percentile(values, 95)),
        "max": _finite(max(values)) if values else None,
        "min": _finite(min(values)) if values else None,
    }


def sequence(occurrence: dict[str, Any], period: int) -> int:
    return int(occurrence["loop"]) * period + int(occurrence["item_index"])


def _colour_ok(pixel: Any, expected: Any) -> bool:
    if not pixel or not expected:
        return False
    return max(abs(a - b) for a, b in zip(pixel[:3], expected[:3], strict=True)) <= PIXEL_TOLERANCE


def analyze_cuts(
    *,
    cohort: list[str],
    ids: dict[str, str],
    period: int,
    target: int,
    dwell_ms: int,
    commits: dict[str, list[dict[str, Any]]],
    draws: dict[str, list[dict[str, Any]]],
    expected_colour: dict[str, Any],
    server_to_epoch_ms: float,
) -> dict[str, Any]:
    """Per-event onset deltas for events ``0..target-1``.

    ``commits[name]`` rows: ``t`` (page epoch ms at receipt), ``occurrence``,
    ``asset`` (``id`` and ``url``), ``effective_server_ms``, ``missed`` (device
    ids). ``draws[name]`` rows: ``t``, ``src``, ``pixel``. ``server_to_epoch_ms``
    is added to a server monotonic stamp to get the page timebase.
    """
    by_seq: dict[str, dict[int, dict[str, Any]]] = {}
    for name in cohort:
        rows: dict[int, dict[str, Any]] = {}
        for row in sorted(commits.get(name, []), key=lambda item: item["t"]):
            rows.setdefault(sequence(row["occurrence"], period), row)
        by_seq[name] = rows
    names_by_id = {device: name for name, device in ids.items()}

    events: list[dict[str, Any]] = []
    for seq in range(target):
        members: dict[str, dict[str, Any]] = {}
        reference: dict[str, Any] | None = None
        server_missed: set[str] = set()
        for name in cohort:
            commit = by_seq[name].get(seq)
            member: dict[str, Any] = {
                "commit_received": commit is not None, "painted": False,
                "onset_ms": None, "pixel_ok": False, "pixel": None,
                "lateness_ms": None, "failure": None,
            }
            members[name] = member
            if commit is None:
                member["failure"] = "no commit delivered"
                continue
            if reference is None:
                reference = commit
            server_missed.update(names_by_id.get(device, device) for device in commit.get("missed", []))
            ceiling = by_seq[name].get(seq + period, {}).get("t", math.inf)
            digest = commit["asset"]["id"].rsplit(":", 1)[-1]
            draw = next((row for row in sorted(draws.get(name, []), key=lambda item: item["t"])
                         if commit["t"] <= row["t"] < ceiling and digest in row["src"]), None)
            if draw is None:
                member["failure"] = "no paint after commit"
                continue
            member["painted"] = True
            member["onset_ms"] = draw["t"]
            member["pixel"] = draw.get("pixel")
            member["pixel_ok"] = _colour_ok(draw.get("pixel"), expected_colour.get(commit["asset"]["id"]))
            if not member["pixel_ok"]:
                member["failure"] = "wrong or unverified pixel"
            member["lateness_ms"] = draw["t"] - (commit["effective_server_ms"] + server_to_epoch_ms)
        good = [name for name in cohort if members[name]["painted"] and members[name]["pixel_ok"]]
        onsets = [members[name]["onset_ms"] for name in cohort if members[name]["painted"]]
        complete = len(good) == len(cohort)
        events.append({
            "seq": seq,
            "occurrence": reference["occurrence"] if reference else None,
            "effective_server_ms": reference["effective_server_ms"] if reference else None,
            "cohort_size": len(cohort),
            "completed": len(good),
            "complete": complete,
            "missing_members": [name for name in cohort if name not in good],
            "server_missed": sorted(server_missed),
            "delta_ms": (max(onsets) - min(onsets)) if complete else None,
            "partial_delta_ms": (max(onsets) - min(onsets)) if not complete and len(onsets) >= 2 else None,
            "members": members,
        })

    deltas = [event["delta_ms"] for event in events if event["complete"]]
    failed = [event for event in events if not event["complete"]]
    whole = deltas + [math.inf] * len(failed)
    lateness = {
        name: summarize([event["members"][name]["lateness_ms"] for event in events
                         if event["members"][name]["lateness_ms"] is not None])
        for name in cohort
    }
    return {
        "label": LABEL,
        "definition": "max minus min software onset per event across the planned cohort; "
                      "onset is the page's drawImage call for the new asset",
        "percentile_rule": "nearest rank",
        "events_requested": target,
        "events_committed": sum(1 for event in events if event["occurrence"] is not None),
        "events_complete": len(deltas),
        "events_failed": len(failed),
        "cohort": cohort,
        "completion_by_member": {
            name: sum(1 for event in events if event["members"][name]["painted"]
                      and event["members"][name]["pixel_ok"]) for name in cohort
        },
        "healthy_subset": {"scope": "complete events only", **summarize(deltas)},
        "whole_show": {
            "scope": "failed events counted as unbounded",
            **{key: value for key, value in summarize(whole).items() if key in ("n", "p50", "p95", "max")},
        },
        "lateness_vs_effective_ms": {
            "scope": "onset minus planned effective time, per member, painted events; includes "
                     "clock-estimate and clock-mapping error",
            **{name: lateness[name] for name in cohort},
        },
        "failed_events": [
            {"seq": event["seq"], "missing_members": event["missing_members"],
             "reasons": {name: event["members"][name]["failure"] for name in event["missing_members"]}}
            for event in failed
        ],
        "degradation_windows": degradation_windows(events, dwell_ms),
        "events": events,
    }


def degradation_windows(events: list[dict[str, Any]], dwell_ms: int) -> list[dict[str, Any]]:
    """Runs of consecutive degraded events, reported apart from the healthy stats.

    Degraded: failed, a non-empty server ``missed`` list, or an effective-time
    gap from the previous event that differs from the dwell (a hold re-anchor).
    """
    flags: list[tuple[int, set[str]]] = []
    previous: float | None = None
    for event in events:
        reasons: set[str] = set()
        effective = event["effective_server_ms"]
        if not event["complete"]:
            reasons.add("failed event")
        if event["server_missed"]:
            reasons.add("server-declared miss")
        if effective is not None and previous is not None and abs(effective - previous - dwell_ms) > GAP_TOLERANCE_MS:
            reasons.add("re-anchor or hold")
        if effective is not None:
            previous = effective
        if reasons:
            flags.append((event["seq"], reasons))
    windows: list[dict[str, Any]] = []
    for seq, reasons in flags:
        if windows and windows[-1]["last_seq"] == seq - 1:
            windows[-1]["last_seq"] = seq
            windows[-1]["events"] += 1
            windows[-1]["reasons"] = sorted(set(windows[-1]["reasons"]) | reasons)
        else:
            windows.append({"first_seq": seq, "last_seq": seq, "events": 1, "reasons": sorted(reasons)})
    by_seq = {event["seq"]: event for event in events}
    for window in windows:
        start = by_seq[window["first_seq"]]["effective_server_ms"]
        end = by_seq[window["last_seq"]]["effective_server_ms"]
        window["effective_span_ms"] = None if start is None or end is None else round(end - start, 3)
    return windows
