"""Twenty connectivity-restore trials against an operator-supplied origin.

    uv run python deploy/network_trials.py --artifacts /tmp/tw-net \\
        --base-url https://192.168.50.1:8443 --tablet-device-id <uuid> \\
        --ap "living-room AP" --wan fibre --restored-marker /tmp/restores.txt

Timing starts at an independently recorded restoration. The operator appends
one line to the marker file (or stdin) at the moment connectivity returns.
The harness observes the outage first, waits for that marker, then measures
until the origin and the named tablet's roster entry are both back.

A line is ``ISO-8601 | case | note``; only the timestamp is required. The
``--restored-at`` mode accepts twenty such values for a pre-scheduled run.
A past value that cannot be preceded by an observed outage fails its trial.

The dry mode uses a disposable loopback server and a Playwright context that
is switched offline and online. It proves the harness and is labelled
software-simulation. It does not model Wi-Fi, an AP, a radio or an OS.

The existing simulator/browser/recovery_run.py remains the network-emulation
control for a browser client. Neither tool closes the real-wifi-os gate.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import math
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.validation import evidence  # noqa: E402

TOOL = "network-trials"
TOOL_VERSION = "1"
TRIALS = 20
TARGET_SECONDS = 10.0
DEFAULT_PROBE_TIMEOUT = 1.0
DEFAULT_RESTORE_TIMEOUT = 30.0
DEFAULT_OUTAGE_TIMEOUT = 600.0
DRY_CASE = "loopback-context-offline"
TRIAL_IDS = tuple(f"trial-{index:02d}" for index in range(1, TRIALS + 1))


def parse_instant(value: str) -> float:
    """Seconds since the epoch from ISO-8601 (Z or offset) or an epoch number."""
    text = value.strip()
    if not text:
        raise ValueError("empty timestamp")
    try:
        number = float(text)
    except ValueError:
        iso = text[:-1] + "+00:00" if text.endswith("Z") else text
        parsed = datetime.fromisoformat(iso)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    if number > 1e11:
        number /= 1000.0
    return number


def iso_utc(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


def parse_restore_line(line: str) -> dict[str, Any]:
    parts = [part.strip() for part in line.strip().split("|")]
    if not parts or not parts[0]:
        raise ValueError("restore marker has no timestamp")
    at = parse_instant(parts[0])
    return {
        "at": at,
        "iso": iso_utc(at),
        "case": parts[1] if len(parts) > 1 and parts[1] else None,
        "note": parts[2] if len(parts) > 2 and parts[2] else None,
    }


def clock_offset_seconds(samples: int = 5) -> float:
    pairs = [time.time() - time.monotonic() for _ in range(samples)]
    return sorted(pairs)[len(pairs) // 2]


def nearest_rank(sorted_values: list[float], percent: float) -> float | None:
    if not sorted_values:
        return None
    index = min(len(sorted_values) - 1,
                max(0, math.ceil(percent / 100 * len(sorted_values)) - 1))
    return sorted_values[index]


def trial_row(
    trial: int,
    *,
    case: str,
    restored_at: float | None,
    seconds: float | None,
    outage_observed: bool | None,
    origin_seconds: float | None = None,
    tablet_seconds: float | None = None,
    success: bool = False,
    failure: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    ok = bool(
        success and restored_at is not None and seconds is not None
        and 0 <= seconds <= TARGET_SECONDS and outage_observed is not False
    )
    if ok:
        failure = None
    return {
        "trial": f"trial-{trial:02d}",
        "case": case,
        "restored_at": iso_utc(restored_at) if restored_at is not None else None,
        "restored_epoch": restored_at,
        "outage_observed": outage_observed,
        "seconds": round(seconds, 3) if seconds is not None else None,
        "origin_seconds": round(origin_seconds, 3) if origin_seconds is not None else None,
        "tablet_seconds": round(tablet_seconds, 3) if tablet_seconds is not None else None,
        "ok": ok,
        "failure": failure,
        **extra,
    }


def summarize_trials(trials: list[dict[str, Any]], target: float = TARGET_SECONDS) -> dict[str, Any]:
    seconds = sorted(
        row["seconds"] for row in trials
        if row["seconds"] is not None and row["seconds"] >= 0
    )
    failures = [row["trial"] for row in trials if not row["ok"]]
    return {
        "trials": len(trials),
        "failures": len(failures),
        "failure_ids": failures,
        "target_seconds": target,
        "p50_seconds": nearest_rank(seconds, 50),
        "p95_seconds": nearest_rank(seconds, 95),
        "min_seconds": seconds[0] if seconds else None,
        "max_seconds": seconds[-1] if seconds else None,
        "seconds": [round(value, 3) for value in seconds],
        "all_within_target": bool(
            len(trials) == TRIALS and not failures and seconds
            and seconds[-1] <= target
        ),
        "cases": sorted({row["case"] for row in trials}),
    }


def build_network_report(
    *,
    started_at: str,
    finished_at: str,
    trials: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    artifacts: dict[str, dict[str, Any]],
    evidence_kind: str,
    tools: dict[str, Any],
    unobserved: list[str],
    limitations: list[str],
    repository: dict[str, Any],
    skipped: list[str] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    by_id = {row["trial"]: row for row in trials}
    scenarios = [
        evidence.scenario_row(
            trial_id,
            "passed" if by_id[trial_id]["ok"] else "failed",
            detail=by_id[trial_id],
        )
        for trial_id in TRIAL_IDS if trial_id in by_id
    ]
    return evidence.build_report(
        tool=TOOL,
        tool_version=TOOL_VERSION,
        gate="real-wifi-os",
        evidence_kind=evidence_kind,
        started_at=started_at,
        finished_at=finished_at,
        checks=checks,
        scenarios=scenarios,
        expected_scenarios=list(TRIAL_IDS),
        cohort=list(TRIAL_IDS),
        artifacts=artifacts,
        tools=tools,
        skipped=skipped or [],
        unobserved=unobserved,
        limitations=limitations,
        repository=repository,
        error=error,
    )


def _artifact_directory(path: Path | None) -> Path:
    if path is None:
        path = Path(tempfile.gettempdir()) / ("tablet-wall-network-" + str(time.time_ns()))
    path = path.expanduser().resolve()
    if path == REPO or REPO in path.parents:
        raise ValueError("artifacts must be outside the repository")
    path.mkdir(parents=True, exist_ok=False)
    return path


def _origin(value: str) -> str:
    from urllib.parse import urlsplit

    parsed = urlsplit(value)
    if (
        parsed.scheme not in ("http", "https") or not parsed.netloc
        or parsed.path not in ("", "/") or parsed.query or parsed.fragment
        or parsed.username or parsed.password
    ):
        raise ValueError("--base-url must be an HTTP(S) origin without a path")
    return f"{parsed.scheme}://{parsed.netloc}"


def _start_server(root: Path, artifacts: Path) -> subprocess.Popen:
    from simulator.browser.run import child_environment

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    base = f"http://127.0.0.1:{listener.getsockname()[1]}"
    env = child_environment(root)
    env.update({
        "TABLET_WALL_UPLOAD_MODE": "loopback",
        "TABLET_WALL_OPERATOR_ORIGIN": base,
    })
    log = (artifacts / "server.log").open("x")
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--fd", str(listener.fileno()),
         "--workers", "1", "--no-access-log"],
        cwd=REPO, env=env, pass_fds=(listener.fileno(),),
        stdout=log, stderr=subprocess.STDOUT,
    )
    process.base_url = base  # type: ignore[attr-defined]
    process.log_handle = log  # type: ignore[attr-defined]
    listener.close()
    return process


class MarkerSource:
    """Append-only newline file of ISO timestamps, one per restoration."""

    def __init__(self, path: Path):
        self.path = path
        self.path.touch(exist_ok=True)
        self.offset = self.path.stat().st_size

    async def next(self, timeout: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.path.exists():
                if self.path.stat().st_size < self.offset:
                    self.offset = 0
                with self.path.open("r", encoding="utf-8") as handle:
                    handle.seek(self.offset)
                    line = handle.readline()
                    self.offset = handle.tell()
                if line.strip():
                    return {**parse_restore_line(line), "source": "marker"}
            await asyncio.sleep(0.1)
        raise TimeoutError(f"no restore marker within {timeout:.0f} s")


class StdinSource:
    async def next(self, timeout: float) -> dict[str, Any]:
        line = await asyncio.wait_for(asyncio.to_thread(sys.stdin.readline), timeout)
        if not line:
            raise TimeoutError("stdin closed before a restore marker")
        return {**parse_restore_line(line), "source": "stdin"}


class TimestampSource:
    def __init__(self, values: list[str]):
        self.items = [parse_restore_line(value) for value in values]
        for item in self.items:
            item["source"] = "supplied"
        self.index = 0

    def peek(self) -> dict[str, Any] | None:
        return self.items[self.index] if self.index < len(self.items) else None

    async def next(self, timeout: float) -> dict[str, Any]:
        item = self.peek()
        if item is None:
            raise TimeoutError("no supplied restoration timestamps remain")
        self.index += 1
        return item


def make_http_probe(base: str, tablet_id: str, timeout: float):
    import httpx

    def origin() -> dict[str, Any]:
        at = time.time()
        try:
            response = httpx.get(base + "/wall", timeout=timeout)
            return {"at": at, "reachable": response.status_code in (200, 409),
                    "status": response.status_code, "error": None}
        except Exception as error:
            return {"at": at, "reachable": False, "status": None,
                    "error": f"{type(error).__name__}: {error}"}

    def tablet() -> dict[str, Any]:
        at = time.time()
        try:
            roster = httpx.get(base + "/devices", timeout=timeout).json()
        except Exception as error:
            return {"at": at, "present": None, "online": None,
                    "error": f"{type(error).__name__}: {error}"}
        record = roster.get(tablet_id)
        return {
            "at": at,
            "present": record is not None,
            "online": None if record is None else bool(record.get("online")),
            "wake_lock": None if record is None else record.get("wake_lock"),
            "error": None,
        }

    return origin, tablet


async def _poll(probe, predicate, timeout: float, interval: float = 0.1,
                threaded: bool = False) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = await asyncio.to_thread(probe) if threaded else await probe()
        if predicate(state):
            return state
        await asyncio.sleep(interval)
    return None


async def _wait_for_outage(origin, tablet, timeout: float) -> dict[str, Any] | None:
    """Two consecutive observations of a lost origin or an offline tablet."""
    deadline = time.monotonic() + timeout
    misses = 0
    first = None
    while time.monotonic() < deadline:
        origin_state, tablet_state = await asyncio.gather(
            asyncio.to_thread(origin), asyncio.to_thread(tablet))
        down = not origin_state["reachable"] or tablet_state.get("online") is False
        if down:
            misses += 1
            first = first or {"at": origin_state["at"],
                              "origin": origin_state, "tablet": tablet_state}
            if misses >= 2:
                return first
        else:
            misses = 0
            first = None
        await asyncio.sleep(0.2)
    return None


async def _measure_restore(origin, tablet, restored_at: float,
                           timeout: float) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    origin_ok = await _poll(origin, lambda state: state["reachable"], timeout, threaded=True)
    tablet_ok = None
    if origin_ok is not None:
        tablet_ok = await _poll(
            tablet,
            lambda state: state.get("online") is True,
            max(0.0, timeout - (time.time() - restored_at)),
            threaded=True,
        )
    return origin_ok, tablet_ok


def _live_trial(
    index: int, case: str, outage: dict[str, Any] | None,
    restore: dict[str, Any], origin_ok: dict[str, Any] | None,
    tablet_ok: dict[str, Any] | None, receipt: float,
) -> dict[str, Any]:
    restored_at = restore["at"]
    origin_seconds = (
        max(0.0, origin_ok["at"] - restored_at) if origin_ok is not None else None)
    tablet_seconds = (
        max(0.0, tablet_ok["at"] - restored_at) if tablet_ok is not None else None)
    both = [value for value in (origin_seconds, tablet_seconds) if value is not None]
    seconds = max(both) if len(both) == 2 else None
    failure = None
    if outage is None:
        failure = "no outage was observed before this restoration"
    elif origin_ok is None:
        failure = "the origin did not become reachable within the observation window"
    elif tablet_ok is None:
        failure = "the tablet roster entry did not become online within the observation window"
    elif seconds is not None and seconds > TARGET_SECONDS:
        failure = f"restore took {seconds:.2f} s, above the {TARGET_SECONDS:.0f} s target"
    skew = receipt - restored_at
    if failure is None and abs(skew) > 60:
        failure = f"restoration timestamp differs from the harness clock by {skew:.1f} s"
    return trial_row(
        index,
        case=restore.get("case") or case,
        restored_at=restored_at,
        seconds=seconds,
        outage_observed=None if outage is None else True,
        origin_seconds=origin_seconds,
        tablet_seconds=tablet_seconds,
        success=failure is None,
        failure=failure,
        restore_source=restore.get("source"),
        note=restore.get("note"),
        outage_at=iso_utc(outage["at"]) if outage else None,
        clock_skew_s=round(skew, 3),
        tablet_wake_lock=None if tablet_ok is None else tablet_ok.get("wake_lock"),
    )


async def run_live(args: argparse.Namespace) -> int:
    import httpx

    started_at = evidence.iso_now()
    started_mono = time.monotonic()
    offset = clock_offset_seconds()
    artifacts = _artifact_directory(args.artifacts)
    repository = evidence.repository_state(REPO)
    checks: list[dict[str, Any]] = []
    trials: list[dict[str, Any]] = []
    unobserved: list[str] = []
    error: dict[str, Any] | None = None
    tools: dict[str, Any] = {
        "base_url": args.base_url,
        "tablet_device_id": args.tablet_device_id,
        "clock_offset_s": round(offset, 6),
    }
    origin, tablet = make_http_probe(args.base_url, args.tablet_device_id, args.probe_timeout)
    source: MarkerSource | StdinSource | TimestampSource
    if args.restored_marker is not None:
        source = MarkerSource(args.restored_marker)
        source_name = "marker"
    elif args.restored_stdin:
        source = StdinSource()
        source_name = "stdin"
    else:
        source = TimestampSource(args.restored_at or [])
        source_name = "supplied"
    tools["restore_source"] = source_name

    def check(name: str, ok: bool, **detail: Any) -> None:
        checks.append(evidence.check_row(name, bool(ok), **detail))

    try:
        first_origin = await asyncio.to_thread(origin)
        first_tablet = await asyncio.to_thread(tablet)
        if not first_origin["reachable"]:
            raise RuntimeError(f"origin is not reachable at the start: {first_origin}")
        if first_tablet.get("present") is not True:
            raise RuntimeError(
                f"tablet {args.tablet_device_id} is not present in the roster: {first_tablet}")
        if first_tablet.get("online") is not True:
            raise RuntimeError(
                f"tablet {args.tablet_device_id} is not online at the start: {first_tablet}")
        tools = {
            "python": platform.python_version(),
            "httpx": getattr(httpx, "__version__", None),
            "base_url": args.base_url,
            "tablet_device_id": args.tablet_device_id,
            "ap": args.ap,
            "wan": args.wan,
            "band": args.band,
            "channel": args.channel,
            "operator": args.operator,
            "note": args.note,
            "target_seconds": TARGET_SECONDS,
            "probe_timeout_s": args.probe_timeout,
            "restore_timeout_s": args.restore_timeout,
            "outage_timeout_s": args.outage_timeout,
            "restore_source": source_name,
            "clock_offset_s": round(offset, 6),
            "argv": [value for value in sys.argv if value != "--restored-stdin"],
        }
        for index in TRIAL_IDS:
            number = int(index.split("-")[1])
            now = time.time()
            restore_hint = source.peek() if isinstance(source, TimestampSource) else None
            if restore_hint is not None and restore_hint["at"] > now:
                budget = min(args.outage_timeout, max(0.1, restore_hint["at"] - now))
            else:
                budget = 0.1 if restore_hint is not None else args.outage_timeout
            outage = await _wait_for_outage(origin, tablet, budget)
            restore = await source.next(args.restore_timeout)
            wait = restore["at"] - time.time()
            if wait > 0:
                await asyncio.sleep(wait)
            receipt = time.time()
            origin_ok, tablet_ok = await _measure_restore(
                origin, tablet, restore["at"], args.restore_timeout)
            row = _live_trial(
                number, args.case, outage, restore, origin_ok, tablet_ok, receipt)
            trials.append(row)
            print(json.dumps({key: row[key] for key in (
                "trial", "case", "restored_at", "seconds", "ok", "failure")}))
            if row["outage_observed"] is None:
                unobserved.append(
                    f"{row['trial']} outage before {row['restored_at']}: "
                    "the supplied timestamp was not preceded by an observed loss")
        summary = summarize_trials(trials)
        observed_outages = [row for row in trials if row["outage_observed"] is True]
        check("all 20 trials were recorded", len(trials) == TRIALS,
              recorded=len(trials), expected=TRIALS)
        check("every trial carries an exact restoration timestamp",
              all(row["restored_at"] for row in trials))
        check("no trial proved the network was still up before its restoration",
              all(row["outage_observed"] is not False for row in trials),
              observed=len(observed_outages), unobserved=len(unobserved))
        check("origin and named tablet were both re-observed for every trial",
              all(row["origin_seconds"] is not None and row["tablet_seconds"] is not None
                  for row in trials))
        check(f"all 20 restores were within {TARGET_SECONDS:.0f} s",
              summary["all_within_target"], **summary)
        check("no trial failed", summary["failures"] == 0, **summary)
        check("AP and WAN metadata were supplied", bool(args.ap and args.wan))
        tools["summary"] = summary
        tools["evidence_note"] = (
            "operator-hardware run; the report still keeps hardware_gate_status MISSING")
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc),
                 "traceback": traceback.format_exc()}
        traceback.print_exc()

    finished_at = evidence.iso_now()
    tools["duration_s"] = round(time.monotonic() - started_mono, 3)
    (artifacts / "trials.json").write_text(json.dumps(trials, indent=2))
    hashed = evidence.artifact_hashes([artifacts / "trials.json"])
    limitations = [
        "the harness measures origin reachability and the named tablet's roster state; "
        "it cannot see the tablet's decoded picture or physical radio state",
        "the exact restoration timestamp must come from a clock aligned with the "
        "harness host; clock skew is recorded per trial",
        "AP, WAN, band, channel and case labels are operator-supplied metadata, "
        "not measurements",
        "one vantage point and one origin; this is not a site survey",
        "hardware_gate_status stays MISSING; only the operator's separate physical "
        "record can close the real-wifi-os gate",
    ]
    report = build_network_report(
        started_at=started_at,
        finished_at=finished_at,
        trials=trials,
        checks=checks,
        artifacts=hashed,
        evidence_kind="operator-hardware",
        tools=tools,
        unobserved=unobserved,
        limitations=limitations,
        repository=repository,
        error=error,
    )
    evidence.write_report(artifacts / "report.json", report)
    print(json.dumps({
        "tool": TOOL,
        "mode": "live",
        "completion": report["completion"],
        "checks": f"{report['checks_passed']}/{report['checks_total']}",
        "trials": len(trials),
        "summary": summarize_trials(trials),
        "failures": report["failure_reasons"],
        "artifacts": str(artifacts),
    }, indent=1))
    if error is not None:
        return 2
    return 0 if report["completion"] == "complete" else 1


async def run_dry(args: argparse.Namespace) -> int:
    from playwright.async_api import async_playwright

    started_at = evidence.iso_now()
    started_mono = time.monotonic()
    artifacts = _artifact_directory(args.artifacts)
    root = Path(tempfile.mkdtemp(prefix="tw-net-", dir="/tmp"))
    for name in ("assets", "media", "tmp"):
        (root / name).mkdir()
    repository = evidence.repository_state(REPO)
    checks: list[dict[str, Any]] = []
    trials: list[dict[str, Any]] = []
    unobserved: list[str] = []
    error: dict[str, Any] | None = None
    process = None
    playwright = None
    log = None
    http = None
    tools: dict[str, Any] = {
        "python": platform.python_version(),
        "target_seconds": TARGET_SECONDS,
        "mode": "dry",
        "dry_outage_seconds": args.dry_outage_seconds,
        "restore_source": "emulated-context",
    }

    def check(name: str, ok: bool, **detail: Any) -> None:
        checks.append(evidence.check_row(name, bool(ok), **detail))

    try:
        process = _start_server(root, artifacts)
        log = process.log_handle  # type: ignore[attr-defined]
        base = process.base_url  # type: ignore[attr-defined]
        import httpx

        http = httpx.Client(base_url=base, headers={"Origin": base}, timeout=10)
        deadline = time.monotonic() + 20
        while True:
            try:
                if http.get("/wall").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("dry-mode server did not become ready")
            await asyncio.sleep(0.1)
        from simulator.browser.run import ClientSpec, watch_page

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            env={**os.environ, "TMPDIR": str(root / "tmp")})
        tools["browser"] = browser.version
        context = await browser.new_context(viewport={"width": 320, "height": 200})
        page, _observation = await watch_page(
            context, ClientSpec("net-dry", 320, 200, 1), [])
        await page.goto(base + "/client/")
        await page.wait_for_function(
            "document.querySelector('#status').dataset.state === 'connected'")

        async def probe() -> dict[str, Any]:
            at = time.time()
            try:
                result = await page.evaluate("""() => fetch('/wall', {cache: 'no-store'})
                    .then(r => ({status: r.status, ok: r.status === 200 || r.status === 409}))
                    .catch(e => ({status: null, ok: false, error: String(e)}))""")
            except Exception as exc:
                result = {"status": None, "ok": False,
                          "error": f"{type(exc).__name__}: {exc}"}
            state = await page.evaluate(
                "() => document.querySelector('#status')?.dataset.state || null")
            return {"at": at, "reachable": bool(result.get("ok")),
                    "status": result.get("status"), "error": result.get("error"),
                    "client_connected": state == "connected"}

        for index in TRIAL_IDS:
            number = int(index.split("-")[1])
            await context.set_offline(True)
            socket_closed = await page.evaluate("""() => {
                const sockets = [...(window.__fleetSockets || [])];
                const open = sockets.reverse().find(s => s.readyState === 1);
                if (!open) return false;
                open.close(4000, 'network dry trial');
                return true;
            }""")
            if not socket_closed:
                raise RuntimeError(f"{index} had no open device socket to drop")
            outage = await _poll(probe, lambda state: not state["reachable"], 5.0)
            if outage is None:
                raise RuntimeError(f"{index} never observed the emulated outage")
            await asyncio.sleep(args.dry_outage_seconds)
            restored_at = time.time()
            await context.set_offline(False)
            origin_ok = await _poll(probe, lambda state: state["reachable"],
                                    args.restore_timeout)
            client_ok = await _poll(
                probe, lambda state: state["client_connected"], args.restore_timeout)
            origin_seconds = (
                max(0.0, origin_ok["at"] - restored_at) if origin_ok else None)
            client_seconds = (
                max(0.0, client_ok["at"] - restored_at) if client_ok else None)
            both = [value for value in (origin_seconds, client_seconds) if value is not None]
            seconds = max(both) if len(both) == 2 else None
            failure = None
            if origin_ok is None:
                failure = "the loopback origin did not answer again within the window"
            elif client_ok is None:
                failure = "the client page did not report connected again within the window"
            elif seconds is not None and seconds > TARGET_SECONDS:
                failure = f"restore took {seconds:.2f} s, above the target"
            trials.append(trial_row(
                number, case=DRY_CASE, restored_at=restored_at, seconds=seconds,
                outage_observed=True, origin_seconds=origin_seconds,
                tablet_seconds=client_seconds, success=failure is None,
                failure=failure, restore_source="emulated-context",
                client_connected=bool(client_ok), socket_closed=True,
            ))
            print(json.dumps({"trial": trials[-1]["trial"],
                              "seconds": trials[-1]["seconds"],
                              "ok": trials[-1]["ok"]}))
        summary = summarize_trials(trials)
        check("all 20 dry trials were recorded", len(trials) == TRIALS,
              recorded=len(trials))
        check("every dry trial observed its emulated offline interval",
              all(row["outage_observed"] is True for row in trials))
        check("every dry trial dropped the device socket",
              all(row.get("socket_closed") is True for row in trials))
        check("the loopback origin and client page both recovered for every trial",
              all(row["origin_seconds"] is not None
                  and row["tablet_seconds"] is not None for row in trials))
        check(f"all 20 emulated restores were within {TARGET_SECONDS:.0f} s",
              summary["all_within_target"], **summary)
        check("no dry trial failed", summary["failures"] == 0, **summary)
        check("the dry mode makes no AP, WAN or radio claim",
              True, evidence_kind="software-simulation")
        tools["summary"] = summary
        tools["origin"] = base
        await page.screenshot(path=str(artifacts / "dry-client.png"))
        http.close()
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc),
                 "traceback": traceback.format_exc()}
        traceback.print_exc()
    finally:
        with contextlib.suppress(Exception):
            if http is not None:
                http.close()
        with contextlib.suppress(Exception):
            if playwright is not None:
                await playwright.stop()
        with contextlib.suppress(Exception):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
        with contextlib.suppress(Exception):
            if log is not None:
                log.close()
        shutil.rmtree(root, ignore_errors=True)

    finished_at = evidence.iso_now()
    tools["duration_s"] = round(time.monotonic() - started_mono, 3)
    (artifacts / "trials.json").write_text(json.dumps(trials, indent=2))
    hashed = evidence.artifact_hashes([
        artifacts / "trials.json", artifacts / "server.log",
        artifacts / "dry-client.png",
    ])
    limitations = [
        "the dry mode is a Playwright context switched offline and online on loopback; "
        "it is not Wi-Fi, an AP, a radio, an OS or a physical tablet",
        "it proves the timing and reporting path, not a real-wifi-os restore",
        "the server and client share one host and one clock",
        "hardware_gate_status stays MISSING",
    ]
    report = build_network_report(
        started_at=started_at,
        finished_at=finished_at,
        trials=trials,
        checks=checks,
        artifacts=hashed,
        evidence_kind="software-simulation",
        tools=tools,
        unobserved=unobserved,
        limitations=limitations,
        repository=repository,
        error=error,
    )
    evidence.write_report(artifacts / "report.json", report)
    print(json.dumps({
        "tool": TOOL,
        "mode": "dry",
        "completion": report["completion"],
        "checks": f"{report['checks_passed']}/{report['checks_total']}",
        "trials": len(trials),
        "summary": summarize_trials(trials),
        "failures": report["failure_reasons"],
        "artifacts": str(artifacts),
    }, indent=1))
    if error is not None:
        return 2
    return 0 if report["completion"] == "complete" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path,
                        help="New directory outside the repository for evidence")
    parser.add_argument("--dry", action="store_true",
                        help="Prove the harness on a disposable loopback server")
    parser.add_argument("--dry-outage-seconds", type=float, default=0.4)
    parser.add_argument("--base-url",
                        help="Operator-supplied HTTPS origin (no path)")
    parser.add_argument("--tablet-device-id",
                        help="The tablet's stable device id in the roster")
    parser.add_argument("--restored-marker", type=Path,
                        help="Append-only file of ISO timestamps, one per restore")
    parser.add_argument("--restored-stdin", action="store_true",
                        help="Read one restore timestamp per line from stdin")
    parser.add_argument("--restored-at", nargs="+",
                        help="Pre-recorded ISO timestamps, one per trial")
    parser.add_argument("--case", default="operator-trial",
                        help="Default case label: ap-loss, wan-loss or tablet-airplane")
    parser.add_argument("--ap", help="Access point label and firmware")
    parser.add_argument("--wan", help="WAN uplink state at the start")
    parser.add_argument("--band", help="Wi-Fi band, for example 5 GHz")
    parser.add_argument("--channel", help="Wi-Fi channel")
    parser.add_argument("--tablet", help="Tablet model and OS")
    parser.add_argument("--operator", help="Operator name")
    parser.add_argument("--note", help="Free-form run note")
    parser.add_argument("--probe-timeout", type=float, default=DEFAULT_PROBE_TIMEOUT)
    parser.add_argument("--restore-timeout", type=float,
                        default=DEFAULT_RESTORE_TIMEOUT)
    parser.add_argument("--outage-timeout", type=float,
                        default=DEFAULT_OUTAGE_TIMEOUT)
    args = parser.parse_args(argv)
    if args.dry:
        if args.base_url or args.restored_marker or args.restored_stdin or args.restored_at:
            parser.error("--dry does not take --base-url or a restore source")
        if not 0 <= args.dry_outage_seconds <= 10:
            parser.error("--dry-outage-seconds must be 0..10")
        return asyncio.run(run_dry(args))
    if not args.base_url or not args.tablet_device_id:
        parser.error("live mode requires --base-url and --tablet-device-id")
    sources = [bool(args.restored_marker), bool(args.restored_stdin), bool(args.restored_at)]
    if sum(sources) != 1:
        parser.error("choose exactly one of --restored-marker, --restored-stdin, --restored-at")
    if args.restored_at is not None:
        if len(args.restored_at) != TRIALS:
            parser.error(f"--restored-at needs exactly {TRIALS} timestamps")
        for value in args.restored_at:
            try:
                parse_instant(value.split("|", 1)[0])
            except ValueError as exc:
                parser.error(f"bad --restored-at value {value!r}: {exc}")
    if args.restored_marker is not None and not args.restored_marker.parent.exists():
        parser.error(f"--restored-marker parent does not exist: {args.restored_marker.parent}")
    if not args.ap or not args.wan:
        parser.error("live mode requires --ap and --wan metadata")
    try:
        args.base_url = _origin(args.base_url)
    except ValueError as exc:
        parser.error(str(exc))
    return asyncio.run(run_live(args))


if __name__ == "__main__":
    raise SystemExit(main())
