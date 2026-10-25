"""Fleet soak harness for N disposable Chromium clients on one server.

    uv run --group browser python -m simulator.browser.fleet_soak --artifacts /tmp/tw-fleet

This is a software harness test. One host runs the server and every browser
client, so CPU, memory, GPU, clocks and the NIC are shared. It does not
measure tablet thermals, decoder behaviour, radio behaviour or an optical
wall. The required two-hour physical media soak and the overnight still soak
stay MISSING; see docs/validation/SOAK-AND-NETWORK.md.

A run opens a disposable server and N calibrated clients, loads a looping
still/video playlist, and samples server status, each original member's
visible picture, browser issues, socket events, server RSS and CPU ticks. It
performs one controlled offline recovery and one Stop/Start, then records
duration, sample gaps and an evidence report.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
from collections import Counter
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

from simulator.browser.evidence import PIXEL_TOLERANCE
from tools.validation import evidence

REPO = Path(__file__).resolve().parents[2]
TOOL = "fleet-soak"
TOOL_VERSION = "1"
TARGET_RESTORE_SECONDS = 10.0
DEFAULT_CLIENTS = 4
DEFAULT_DURATION_SECONDS = 60.0
DEFAULT_INTERVAL_SECONDS = 0.5
DEFAULT_RECOVERY_OFFLINE_SECONDS = 3.0
STILL_DWELL_MS = 1500
VIDEO_SECONDS = 4
SCENARIOS = (
    "boundaries",
    "controlled-recovery",
    "reconnect",
    "playback-stop-start",
    "sampling-coverage",
    "resources",
)
NETWORK_MARKERS = (
    "err_internet_disconnected",
    "err_network_changed",
    "err_connection_reset",
    "err_connection_refused",
    "err_aborted",
    "failed to fetch",
    "networkerror",
    "network error",
    "websocket is closed",
)

MEMBER_SAMPLE_JS = """() => {
    const describe = (element) => {
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        const opacity = Number.parseFloat(style.opacity);
        const finite = Number.isFinite(opacity);
        return {
            display: style.display,
            visibility: style.visibility,
            opacity: finite ? opacity : 1,
            width: rect.width,
            height: rect.height,
            visible: style.display !== 'none'
                && style.visibility !== 'hidden'
                && (!finite || opacity > 0.05)
                && rect.width > 1 && rect.height > 1,
        };
    };
    const canvas = document.querySelector('#surface');
    let pixel = null;
    let canvasVisible = false;
    if (canvas) {
        const style = getComputedStyle(canvas);
        const rect = canvas.getBoundingClientRect();
        canvasVisible = style.display !== 'none'
            && style.visibility !== 'hidden'
            && rect.width > 1 && rect.height > 1;
        try {
            const probe = document.createElement('canvas');
            probe.width = 1;
            probe.height = 1;
            const context = probe.getContext('2d', {willReadFrequently: true});
            context.drawImage(
                canvas,
                Math.floor(canvas.width / 2),
                Math.floor(canvas.height / 2), 1, 1, 0, 0, 1, 1);
            pixel = Array.from(context.getImageData(0, 0, 1, 1).data);
        } catch (error) {
            pixel = null;
        }
    }
    const videos = [...document.querySelectorAll('video')].map((element) => ({
        t: Number(element.currentTime),
        paused: element.paused,
        ended: element.ended,
        ready: Number(element.readyState),
        duration: Number(element.duration),
        src: element.currentSrc || element.src || '',
        ...describe(element),
    }));
    return {
        status: document.querySelector('#status')?.dataset.state || null,
        visibility: document.visibilityState,
        canvasVisible,
        pixel,
        videos,
    };
}"""


def playlist_items(still_id: str, video_id: str) -> list[dict[str, Any]]:
    """A still and a video. The server replaces a known video's dwell with its duration."""
    return [
        {"asset": still_id, "dwell_ms": STILL_DWELL_MS},
        {"asset": video_id, "dwell_ms": 1000},
    ]


def parse_status_rss_kb(text: str) -> int | None:
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    return None


def parse_stat_cpu_ticks(text: str) -> int | None:
    """utime + stime from /proc/<pid>/stat, after the parenthesised comm."""
    fields = text.rsplit(")", 1)[1].split()
    return int(fields[11]) + int(fields[12])


def read_process_resources(pid: int, proc_root: Path = Path("/proc")) -> dict[str, Any]:
    base = proc_root / str(pid)
    try:
        status = (base / "status").read_text()
        stat = (base / "stat").read_text()
        return {
            "alive": True,
            "rss_kb": parse_status_rss_kb(status),
            "cpu_ticks": parse_stat_cpu_ticks(stat),
        }
    except (OSError, ValueError, IndexError):
        return {"alive": False, "rss_kb": None, "cpu_ticks": None}


def sampling_summary(
    offsets: list[float], interval: float, achieved: float,
    deliberate_windows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Sample count, coverage and gaps. A gap is longer than 2.5 intervals."""
    windows = deliberate_windows or []
    ordered = sorted(offsets)
    edges = [0.0, *ordered, achieved]
    threshold = max(interval * 2.5, 1.0)
    gaps = []
    for start, end in zip(edges, edges[1:], strict=False):
        if end - start <= threshold:
            continue
        gap = {"from_s": round(start, 3), "to_s": round(end, 3),
               "seconds": round(end - start, 3)}
        gap["deliberate"] = any(
            start <= window["to_s"] + 0.05 and end >= window["from_s"] - 0.05
            for window in windows
        )
        gaps.append(gap)
    unexplained = [gap for gap in gaps if not gap["deliberate"]]
    covered = achieved - sum(gap["seconds"] for gap in gaps)
    expected = int(achieved / interval) + 1 if interval > 0 else 0
    return {
        "samples": len(ordered),
        "expected_samples": expected,
        "coverage_ratio": round(covered / achieved, 4) if achieved > 0 else 0.0,
        "gap_count": len(gaps),
        "unexplained_gap_count": len(unexplained),
        "max_gap_s": max((gap["seconds"] for gap in gaps), default=0.0),
        "unexplained_max_gap_s": max(
            (gap["seconds"] for gap in unexplained), default=0.0
        ),
        "total_gap_s": round(sum(gap["seconds"] for gap in gaps), 3),
        "gaps": gaps,
    }


def issue_rows(events: list[dict[str, Any]], since: float = 0.0) -> list[dict[str, Any]]:
    """Unexpected page, console, request, HTTP and socket events."""
    rows = []
    for event in events:
        if event["time"] < since:
            continue
        kind = event.get("kind")
        row: dict[str, Any] | None = None
        if kind == "page_error":
            row = {"kind": kind, "text": event.get("text", "")}
        elif kind == "console" and event.get("level") in ("error", "warning"):
            row = {"kind": "console_" + str(event["level"]),
                   "text": event.get("text", "")}
        elif kind == "request_failed":
            row = {"kind": kind, "url": event.get("url", ""),
                   "error": str(event.get("error", ""))}
        elif kind == "http" and int(event.get("status", 0)) >= 400:
            row = {"kind": "http_error", "url": event.get("url", ""),
                   "status": event.get("status")}
        elif kind == "ws_error":
            row = {"kind": kind, "error": str(event.get("error", ""))}
        elif kind == "ws_close" and event.get("code") not in (1000, 1001):
            row = {"kind": kind, "code": event.get("code"),
                   "reason": event.get("reason", "")}
        if row is not None:
            row["time"] = round(event["time"], 3)
            rows.append(row)
    return rows


def is_expected_network_issue(issue: dict[str, Any]) -> bool:
    if issue["kind"] == "page_error":
        return False
    if issue["kind"] == "ws_close":
        return issue.get("code") in (1005, 1006, 4000)
    text = json.dumps(issue).lower()
    return any(marker in text for marker in NETWORK_MARKERS)


def issue_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """A bounded report view; the full rows live in issues.json."""
    by_kind = Counter(row["kind"] for row in rows)
    by_error = Counter(
        str(row.get("error") or row.get("text") or row.get("reason") or "")[:120]
        for row in rows
    )
    return {
        "count": len(rows),
        "by_kind": dict(sorted(by_kind.items())),
        "by_error": dict(by_error.most_common(10)),
        "first": rows[:10],
        "last": rows[-10:] if len(rows) > 10 else [],
    }


def split_expected_issues(
    issues: list[dict[str, Any]], client: str, window: tuple[float, float],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate the controlled offline window's network noise from defects."""
    expected, unexpected = [], []
    for issue in issues:
        in_window = window[0] - 0.5 <= issue["time"] <= window[1]
        if issue.get("client") == client and in_window and is_expected_network_issue(issue):
            expected.append(issue)
        else:
            unexpected.append(issue)
    return expected, unexpected


def build_soak_report(
    *,
    started_at: str,
    finished_at: str,
    checks: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
    artifacts: dict[str, dict[str, Any]],
    cohort: list[str],
    tools: dict[str, Any],
    skipped: list[str],
    unobserved: list[str],
    limitations: list[str],
    repository: dict[str, Any],
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return evidence.build_report(
        tool=TOOL,
        tool_version=TOOL_VERSION,
        gate="soak",
        evidence_kind="software-simulation",
        started_at=started_at,
        finished_at=finished_at,
        checks=checks,
        scenarios=scenarios,
        expected_scenarios=list(SCENARIOS),
        artifacts=artifacts,
        cohort=cohort,
        tools=tools,
        skipped=skipped,
        unobserved=unobserved,
        limitations=limitations,
        repository=repository,
        error=error,
    )


def build_clip(target: Path, seconds: int = VIDEO_SECONDS) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required for the fleet soak video fixture")
    argv = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=30:duration={seconds}",
        "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.0",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(target),
    ]
    done = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    if done.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + done.stderr[-2000:])
    return {"argv": argv, "bytes": target.stat().st_size, "seconds": seconds}


def _pixel_close(seen: Any, wanted: Any, tolerance: int = PIXEL_TOLERANCE) -> bool:
    return bool(seen) and max(abs(a - b) for a, b in zip(seen[:3], wanted[:3], strict=True)) <= tolerance


def _visible_video(state: dict[str, Any]) -> dict[str, Any] | None:
    visible = [video for video in state.get("videos", []) if video.get("visible")]
    if not visible:
        return None
    return max(visible, key=lambda video: (video.get("t", 0), video.get("width", 0)))


async def _member_sample(page: Any) -> dict[str, Any]:
    try:
        return await page.evaluate(MEMBER_SAMPLE_JS)
    except Exception as error:
        return {"error": f"{type(error).__name__}: {error}"}


def _occurrence_key(occurrence: Any) -> str:
    if not isinstance(occurrence, dict):
        return "none"
    return json.dumps(occurrence, sort_keys=True)


def _status_display(status: dict[str, Any]) -> tuple[str, str | None, str | None]:
    """Return (kind, asset, occurrence_key) for what the server says is displayed."""
    live = status.get("live") or {}
    item = live.get("displayed") or live.get("current") or {}
    return (
        str(item.get("kind") or "none"),
        item.get("asset"),
        _occurrence_key(item.get("occurrence")),
    )


async def run(args: argparse.Namespace) -> int:
    from playwright.async_api import async_playwright

    from simulator.browser.run import (
        CUT_COLOURS,
        ClientSpec,
        Rig,
        artifact_directory,
        calibrate_cohort,
        connected,
        descendants,
        open_cohort,
        stop_playback,
        wait_for_centre,
    )

    artifacts = artifact_directory(args.artifacts)
    root = Path(tempfile.mkdtemp(prefix="tw-fleet-", dir="/tmp"))
    for name in ("assets", "media", "tmp"):
        (root / name).mkdir()
    started_at = evidence.iso_now()
    repository = evidence.repository_state(REPO)
    checks: list[dict[str, Any]] = []
    scenario_detail: dict[str, dict[str, Any]] = {
        scenario: {"status": "incomplete", "detail": None} for scenario in SCENARIOS
    }
    skipped: list[str] = []
    unobserved: list[str] = []
    samples: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    deliberate_windows: list[dict[str, Any]] = []
    unexpected_issues: list[dict[str, Any]] = []
    expected_issues: list[dict[str, Any]] = []
    stalls: list[dict[str, Any]] = []
    stale_paints: list[dict[str, Any]] = []
    error: dict[str, Any] | None = None
    recovery_done = False
    stop_done = False
    recovery_short = False
    stop_short = False
    recovery_mono_window: tuple[float, float] | None = None
    tools: dict[str, Any] = {
        "python": platform.python_version(),
        "requested_seconds": args.duration,
        "interval_s": args.interval,
        "clients": args.clients,
        "recovery_offline_seconds": args.recovery_offline_seconds,
        "video_seconds": VIDEO_SECONDS,
        "still_dwell_ms": STILL_DWELL_MS,
    }
    pages: list[tuple[Any, Any]] = []
    http = None
    process = None
    playwright = None
    log = None
    soak_start: float | None = None
    achieved = 0.0
    server_pid: int | None = None
    cohort: list[str] = []

    def check(name: str, ok: bool, **detail: Any) -> bool:
        checks.append(evidence.check_row(name, bool(ok), **detail))
        return bool(ok)

    def event(name: str, **data: Any) -> None:
        elapsed = round(time.monotonic() - soak_start, 3) if soak_start else 0.0
        timeline.append({"elapsed_s": elapsed, "kind": name, **data})

    def set_scenario(name: str, status: str, detail: Any = None) -> None:
        scenario_detail[name] = {"status": status, "detail": detail}

    def read_status() -> tuple[dict[str, Any] | None, str | None]:
        try:
            response = http.get("/api/v3/playback", timeout=10)
            if response.status_code != 200:
                return None, f"status {response.status_code}"
            return response.json(), None
        except Exception as exc:
            return None, f"{type(exc).__name__}: {exc}"

    def artwork_expected(status: dict[str, Any]) -> tuple[str, str | None, tuple[int, int, int] | None]:
        kind, asset, _key = _status_display(status)
        if status.get("state") in ("stopped", "blocked", "failed"):
            return "still", assets.get("idle"), CUT_COLOURS["idle"]
        if kind == "still":
            return kind, asset, colour_by_asset.get(asset)
        return kind, asset, None

    async def picture_ok(page: Any, status: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        kind, _asset, expected = artwork_expected(status)
        sample = await _member_sample(page)
        if "error" in sample:
            return False, sample
        if kind == "video":
            video = _visible_video(sample)
            done = bool(
                video and video["ready"] >= 2 and not video["paused"]
                and video["t"] > 0.02
            )
            return done, sample
        done = bool(sample.get("canvasVisible") and expected
                    and _pixel_close(sample.get("pixel"), expected))
        return done, sample

    try:
        process = _start_server(root, artifacts, http_log_name="server.log")
        log = process.log_handle  # type: ignore[attr-defined]
        server_pid = process.pid
        http = httpx_client(process)
        wait_ready(http, process, args.ready_seconds)
        tools["server_pid"] = server_pid

        specs = [
            (ClientSpec(
                f"fleet-{index + 1}",
                (240, 200, 220, 260)[index % 4],
                (160, 150, 140, 170)[index % 4],
                (1, 1.25, 1.5, 1)[index % 4],
            ), 0 if index % 2 == 0 else 180)
            for index in range(args.clients)
        ]
        playwright = await async_playwright().start()
        browser_env = {**os.environ, "TMPDIR": str(root / "tmp")}
        browser = await playwright.chromium.launch(env=browser_env)
        tools["browser"] = browser.version
        rig = Rig(
            base=process.base_url,  # type: ignore[attr-defined]
            http=http,
            browser=browser,
            playwright=playwright,
            browser_env=browser_env,
            root=root,
            artifacts=artifacts,
            observations=[],
            captured_pages=[],
            resources=[],
            owned=descendants(os.getpid()),
            check=check,
        )
        pages = await open_cohort(rig, tuple(specs), "fleet")
        cohort = [observation.device_id for _, observation in pages]
        check(
            f"{len(pages)} disposable clients opened with distinct identities",
            len(set(cohort)) == len(pages),
            identities=sorted(cohort),
        )
        assets = await calibrate_cohort(
            rig, pages, [mount for _, mount in specs],
            {"idle": CUT_COLOURS["idle"], "red": CUT_COLOURS["red"]}, "fleet",
        )
        colour_by_asset = {
            assets["idle"]: CUT_COLOURS["idle"],
            assets["red"]: CUT_COLOURS["red"],
        }

        clip = root / "fleet.mp4"
        fixture = build_clip(clip)
        fixture_artifact = artifacts / "fixture.mp4"
        shutil.copyfile(clip, fixture_artifact)
        fixture["artifact"] = str(fixture_artifact)
        tools["video_fixture"] = fixture
        upload = http.post(
            "/uploads?name=fleet.mp4", content=clip.read_bytes(),
            headers={"Content-Type": "video/mp4"},
        )
        check("the synthetic video uploads", upload.status_code == 201,
              status=upload.status_code, text=upload.text[-300:])
        if upload.status_code != 201:
            raise RuntimeError("video upload failed")
        video = upload.json()["asset"]

        etag = http.get("/api/v3/playlist").json()["etag"]
        saved = http.put(
            "/api/v3/playlist",
            json={"items": playlist_items(assets["red"], video["id"]), "loop": True},
            headers={"If-Match": etag},
        )
        check("the still and video playlist saves", saved.status_code == 200,
              status=saved.status_code, text=saved.text[-300:])
        if saved.status_code != 200:
            raise RuntimeError("playlist save failed")
        playlist = saved.json()["playlist"]
        tools["playlist"] = playlist

        started = http.post("/api/v3/playback/start")
        check("playback starts", started.status_code == 200,
              status=started.status_code, text=started.text[-300:])
        if started.status_code != 200:
            raise RuntimeError("playback start failed")

        deadline = time.monotonic() + 20
        initial = None
        while time.monotonic() < deadline:
            initial, status_error = read_status()
            if initial and initial.get("state") == "playing" \
                    and initial.get("displayed") == initial.get("current") \
                    and (initial.get("now_ms", 0) or 0) >= (initial.get("current_effective_ms") or 0) + 200:
                break
            await asyncio.sleep(0.1)
        if not initial or initial.get("state") != "playing":
            raise RuntimeError(f"playback never reached playing: {initial}")

        still_painted = []
        for page, observation in pages:
            still_painted.append(await wait_for_centre(page, CUT_COLOURS["red"], 15))
        check("every member painted the first playlist still",
              all(still_painted), members={
                  observation.spec.name: painted
                  for (_, observation), painted in zip(pages, still_painted, strict=True)})

        soak_start = time.monotonic()
        recovery_at = max(8.0, args.duration * 0.3)
        stop_at = max(recovery_at + args.recovery_offline_seconds + 10.0,
                      args.duration * 0.65)
        recovery_short = args.duration < recovery_at + 5
        stop_short = args.duration < stop_at + 5

        last_display: str | None = None
        recovery_armed = False
        boundary_count = 0
        per_member = {
            device_id: {"still_seen": False, "video_seen": False}
            for device_id in cohort
        }
        event_index = {observation.device_id: 0 for _, observation in pages}
        last_video_t: dict[str, float] = {}
        stall_counts: dict[str, int] = {}
        stale_counts: dict[str, int] = {}
        stalled_keys: set[str] = set()
        stale_keys: set[str] = set()
        server_failures = 0
        next_due = soak_start
        resources_missing = 0
        last_status: dict[str, Any] | None = None

        def collect_issues(observation: Any) -> list[dict[str, Any]]:
            rows = issue_rows(observation.events, event_index[observation.device_id])
            event_index[observation.device_id] = len(observation.events)
            for row in rows:
                row["client"] = observation.spec.name
                unexpected_issues.append(row)
            return rows

        async def sample_all(elapsed: float) -> dict[str, Any]:
            nonlocal last_display, boundary_count, server_failures, resources_missing
            nonlocal last_status, last_video_t
            status, status_error = read_status()
            resources = read_process_resources(server_pid) if server_pid else {
                "alive": False, "rss_kb": None, "cpu_ticks": None}
            if not resources["alive"]:
                server_failures += 1
            if resources["rss_kb"] is None or resources["cpu_ticks"] is None:
                resources_missing += 1
            if status is not None:
                last_status = status
            else:
                server_failures += 1
            kind, asset, key = _status_display(status) if status else ("none", None, "none")
            if key != last_display:
                boundary_count += 1
                event("display", kind=kind, asset=asset, occurrence=key)
                last_display = key
            members: dict[str, Any] = {}
            issue_kinds: Counter[str] = Counter()
            current = (status or {}).get("current") or {}
            displayed = (status or {}).get("displayed") or {}
            playing = (status or {}).get("state") == "playing"
            settled = bool(
                playing and displayed and displayed == current
                and ((status or {}).get("now_ms", 0) or 0)
                >= ((status or {}).get("current_effective_ms") or 0) + 1500
            )
            for page, observation in pages:
                device_id = observation.device_id
                raw = await _member_sample(page)
                new_issues = collect_issues(observation)
                issue_kinds.update(row["kind"] for row in new_issues)
                expected_kind, expected_asset, expected_colour = artwork_expected(
                    status or {"state": "stopped"})
                video = _visible_video(raw) if "error" not in raw else None
                advancing: bool | None = None
                if expected_kind == "video":
                    previous = last_video_t.get(device_id)
                    if video is None:
                        advancing = False
                    elif video["paused"] or video["ready"] < 2:
                        advancing = False
                    elif previous is None:
                        advancing = video["t"] > 0.05
                    else:
                        advancing = video["t"] - previous > 0.08
                    if video is not None:
                        last_video_t[device_id] = video["t"]
                if expected_kind == "video" and advancing:
                    per_member[device_id]["video_seen"] = True
                if expected_kind == "still" and expected_colour is not None \
                        and "error" not in raw and _pixel_close(raw.get("pixel"), expected_colour):
                    per_member[device_id]["still_seen"] = True
                    if settled:
                        stale_counts[device_id] = 0
                stale_ok = bool(
                    expected_kind == "still" and expected_colour is not None
                    and "error" not in raw
                    and _pixel_close(raw.get("pixel"), expected_colour)
                )
                if settled and expected_kind == "still" and not stale_ok:
                    stale_counts[device_id] = stale_counts.get(device_id, 0) + 1
                    occurrence = _occurrence_key(displayed.get("occurrence"))
                    record_key = f"{device_id}:{occurrence}"
                    if stale_counts[device_id] >= 3 and record_key not in stale_keys:
                        stale_keys.add(record_key)
                        stale_paints.append({
                            "client": observation.spec.name,
                            "elapsed_s": round(elapsed, 3),
                            "occurrence": occurrence,
                            "pixel": raw.get("pixel"),
                            "expected": list(expected_colour),
                        })
                if settled and expected_kind == "video" and not advancing:
                    stall_counts[device_id] = stall_counts.get(device_id, 0) + 1
                    occurrence = _occurrence_key(displayed.get("occurrence"))
                    record_key = f"{device_id}:{occurrence}"
                    if stall_counts[device_id] >= 3 and record_key not in stalled_keys:
                        stalled_keys.add(record_key)
                        stalls.append({
                            "client": observation.spec.name,
                            "elapsed_s": round(elapsed, 3),
                            "occurrence": occurrence,
                            "video": video,
                        })
                if settled and expected_kind == "video" and advancing:
                    stall_counts[device_id] = 0
                members[device_id] = {
                    "name": observation.spec.name,
                    "expected_kind": expected_kind,
                    "expected_asset": expected_asset,
                    "advancing": advancing,
                    "still_ok": stale_ok,
                    "video": video,
                    "sample": raw,
                }
            return {
                "elapsed_s": round(elapsed, 3),
                "status_error": status_error,
                "resources": resources,
                "status": status,
                "issues": {"new": sum(issue_kinds.values()),
                           "by_kind": dict(issue_kinds)},
                "members": members,
            }

        async def do_recovery() -> None:
            nonlocal unobserved, recovery_mono_window
            _, observation = pages[0]
            page = pages[0][0]
            device_id = observation.device_id
            name = observation.spec.name
            from_start = time.monotonic()
            recovery_mono_window = (from_start, from_start)
            open_before = sum(e["kind"] == "ws_open" for e in observation.events)
            status = read_status()[0]
            kind_now = _status_display(status)[0] if status else "none"
            phase_kind = "still" if kind_now == "still" else "video"
            event("recovery-phase", client=name, kind=phase_kind)
            event("recovery-offline", client=name)
            await page.context.set_offline(True)
            socket_closed = await page.evaluate("""() => {
                const sockets = [...(window.__fleetSockets || [])];
                const open = sockets.reverse().find(s => s.readyState === 1);
                if (!open) return false;
                open.close(4000, 'soak recovery');
                return true;
            }""")
            event("recovery-socket-closed", client=name, closed=socket_closed)
            await asyncio.sleep(args.recovery_offline_seconds)
            restored = time.monotonic()
            await page.context.set_offline(False)
            event("recovery-restored", client=name)
            deadline = restored + 15
            connected_seen = None
            picture_seen = None
            ws_reopens = 0
            identity_preserved = False
            sample: dict[str, Any] = {}
            while time.monotonic() < deadline:
                state = await page.evaluate(
                    "() => document.querySelector('#status')?.dataset.state || null")
                ws_reopens = sum(e["kind"] == "ws_open" for e in observation.events) - open_before
                if state == "connected" and ws_reopens > 0 and connected_seen is None:
                    connected_seen = time.monotonic()
                    event("recovery-connected", client=name,
                          seconds=round(connected_seen - restored, 3))
                    try:
                        identity_preserved = await page.evaluate(
                            "() => localStorage.getItem('tablet-wall-device-id')") == device_id
                    except Exception:
                        identity_preserved = False
                status = read_status()[0]
                if connected_seen is not None and status is not None:
                    ok, sample = await picture_ok(page, status)
                    if ok:
                        picture_seen = time.monotonic()
                        event("recovery-painted", client=name,
                              seconds=round(picture_seen - restored, 3))
                        break
                await asyncio.sleep(0.2)
            connected_seconds = (
                round(connected_seen - restored, 3) if connected_seen else None)
            picture_seconds = (
                round(picture_seen - restored, 3) if picture_seen else None)
            passed = bool(
                connected_seconds is not None and picture_seconds is not None
                and max(connected_seconds, picture_seconds) <= TARGET_RESTORE_SECONDS
                and ws_reopens > 0 and identity_preserved and socket_closed
            )
            status_after = read_status()[0] if connected_seen is not None else None
            detail = {
                "client": name, "device_id": device_id,
                "offline_seconds": args.recovery_offline_seconds,
                "connected_seconds": connected_seconds,
                "picture_seconds": picture_seconds,
                "ws_reopens": ws_reopens,
                "socket_closed": socket_closed,
                "recovery_phase": phase_kind,
                "identity_preserved": identity_preserved,
                "sample": sample,
                "status_after": None if status_after is None else {
                    key: status_after.get(key) for key in (
                        "state", "current", "displayed", "recovery", "blocked_reason")},
                "outcome": passed,
            }
            recovery_end = time.monotonic()
            recovery_mono_window = (from_start, recovery_end)
            window = {"from_s": round(from_start - soak_start, 3),
                      "to_s": round(recovery_end - soak_start, 3),
                      "kind": "controlled recovery"}
            deliberate_windows.append(window)
            unobserved.append(
                f"{name} picture while the controlled offline window was active "
                f"({window['from_s']:.1f}-{window['to_s']:.1f} s)")
            set_scenario("controlled-recovery", "passed" if passed else "failed", detail)
            set_scenario("reconnect", "passed" if (
                connected_seconds is not None and ws_reopens > 0 and identity_preserved
            ) else "failed", detail)
            check("one controlled offline recovery reconnected the same identity",
                  connected_seconds is not None and ws_reopens > 0
                  and identity_preserved and socket_closed,
                  **detail)
            check(f"the controlled recovery repainted within {TARGET_RESTORE_SECONDS:.0f} s",
                  picture_seconds is not None and picture_seconds <= TARGET_RESTORE_SECONDS,
                  **detail)

        async def do_stop_start() -> None:
            started_at = time.monotonic()
            event("playback-stop")
            response = stop_playback(http)
            stopped = False
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                status = read_status()[0]
                if status is not None and status.get("state") == "stopped":
                    stopped = True
                    break
                await asyncio.sleep(0.1)
            idle: dict[str, bool] = {}
            idle_deadline = time.monotonic() + 10
            while time.monotonic() < idle_deadline:
                for page, observation in pages:
                    raw = await _member_sample(page)
                    idle[observation.spec.name] = bool(
                        "error" not in raw
                        and raw.get("canvasVisible")
                        and not any(video.get("visible") for video in raw.get("videos", []))
                        and _pixel_close(raw.get("pixel"), CUT_COLOURS["idle"])
                    )
                if all(idle.values()):
                    break
                await asyncio.sleep(0.1)
            stopped_at = time.monotonic()
            event("playback-stopped", stopped=stopped, idle=idle)
            restart = http.post("/api/v3/playback/start")
            red_painted: dict[str, bool] = {}
            restart_deadline = time.monotonic() + 20
            while time.monotonic() < restart_deadline:
                for page, observation in pages:
                    raw = await _member_sample(page)
                    red_painted[observation.spec.name] = bool(
                        "error" not in raw
                        and raw.get("canvasVisible")
                        and _pixel_close(raw.get("pixel"), CUT_COLOURS["red"])
                    )
                if restart.status_code == 200 and all(red_painted.values()):
                    break
                await asyncio.sleep(0.1)
            restarted_at = time.monotonic()
            event("playback-restarted", status=restart.status_code,
                  repainted=red_painted)
            window = {"from_s": round(started_at - soak_start, 3),
                      "to_s": round(restarted_at - soak_start, 3),
                      "kind": "playback stop/start"}
            deliberate_windows.append(window)
            unobserved.append(
                "playback Stop/Start sampling pause "
                f"({window['from_s']:.1f}-{window['to_s']:.1f} s)")
            passed = bool(
                response is not None and stopped and all(idle.values())
                and restart.status_code == 200 and all(red_painted.values())
            )
            detail = {
                "stop_status": getattr(response, "status_code", None),
                "stopped": stopped,
                "idle": idle,
                "restart_status": restart.status_code,
                "repainted": red_painted,
                "stop_seconds": round(stopped_at - started_at, 3),
                "restart_seconds": round(restarted_at - stopped_at, 3),
                "outcome": passed,
            }
            set_scenario("playback-stop-start", "passed" if passed else "failed", detail)
            check("playback Stop returned every member to the persisted scene",
                  stopped and all(idle.values()), **detail)
            check("playback Start repainted every member", restart.status_code == 200
                  and all(red_painted.values()), **detail)

        while True:
            elapsed = time.monotonic() - soak_start
            if elapsed >= args.duration:
                break
            if not recovery_short and not recovery_done:
                if not recovery_armed and elapsed >= recovery_at:
                    recovery_armed = True
                    event("recovery-armed")
                if recovery_armed:
                    armed_status = last_status or {}
                    armed_kind = _status_display(armed_status)[0]
                    if (armed_kind == "still"
                            and armed_status.get("state") == "playing") \
                            or elapsed >= recovery_at + 12:
                        await do_recovery()
                        recovery_done = True
                        next_due = time.monotonic()
                        continue
            if not stop_short and not stop_done and elapsed >= stop_at:
                await do_stop_start()
                stop_done = True
                next_due = time.monotonic()
                continue
            sample = await sample_all(time.monotonic() - soak_start)
            samples.append(sample)
            next_due += args.interval
            now = time.monotonic()
            if next_due > now:
                await asyncio.sleep(next_due - now)
            else:
                next_due = now

        achieved = time.monotonic() - soak_start
        final_status = read_status()[0]
        final_cohort = set((final_status or {}).get("cohort") or [])
        for page, observation in pages:
            collect_issues(observation)

        stop_playback(http)
        await asyncio.sleep(1.5)
        final_idle: dict[str, bool] = {}
        for page, observation in pages:
            raw = await _member_sample(page)
            final_idle[observation.spec.name] = bool(
                "error" not in raw
                and raw.get("canvasVisible")
                and not any(video.get("visible") for video in raw.get("videos", []))
                and _pixel_close(raw.get("pixel"), CUT_COLOURS["idle"])
            )
        check("the final Stop returned every member to the persisted scene",
              all(final_idle.values()), clients=final_idle)
        for page, observation in pages:
            await page.screenshot(
                path=str(artifacts / f"client-{observation.spec.name}.png"))

        reload_ok = False
        try:
            await pages[0][0].reload()
            await connected(pages[0][0])
            reload_ok = await wait_for_centre(pages[0][0], CUT_COLOURS["idle"], 15)
        except Exception as exc:
            event("reload-error", error=f"{type(exc).__name__}: {exc}")
        check("the persisted scene survives playback and one reload", reload_ok)
        for page, observation in pages:
            collect_issues(observation)

        check("the original cohort stayed complete", set(cohort) == final_cohort,
              cohort=sorted(cohort), final=sorted(final_cohort))
        check("the server stayed alive for the whole run", bool(
            process.poll() is None and server_failures == 0),
              server_failures=server_failures)
        summary = sampling_summary(
            [sample["elapsed_s"] for sample in samples], args.interval,
            achieved, deliberate_windows)
        check("the requested duration was achieved",
              achieved >= args.duration - 1.0,
              requested=args.duration, achieved=round(achieved, 3))
        check("sampling has no unexplained gap above one second",
              summary["unexplained_max_gap_s"] <= 1.0, **summary)
        check("server RSS and CPU were sampled every interval",
              resources_missing == 0 and summary["samples"] > 0,
              missing=resources_missing, samples=summary["samples"])
        rss_values = [sample["resources"]["rss_kb"] for sample in samples
                      if sample["resources"]["rss_kb"] is not None]
        cpu_values = [sample["resources"]["cpu_ticks"] for sample in samples
                      if sample["resources"]["cpu_ticks"] is not None]
        ticks_per_second = os.sysconf("SC_CLK_TCK")
        cpu_seconds = ((cpu_values[-1] - cpu_values[0]) / ticks_per_second
                       if len(cpu_values) > 1 else None)
        tools["resources_summary"] = {
            "samples": len(rss_values),
            "first_rss_kb": rss_values[0] if rss_values else None,
            "last_rss_kb": rss_values[-1] if rss_values else None,
            "max_rss_kb": max(rss_values) if rss_values else None,
            "rss_growth_kb": (rss_values[-1] - rss_values[0]
                              if len(rss_values) > 1 else None),
            "cpu_ticks_total": (cpu_values[-1] - cpu_values[0]
                                if len(cpu_values) > 1 else None),
            "cpu_seconds": round(cpu_seconds, 3) if cpu_seconds is not None else None,
            "cpu_percent_of_one_core": (
                round(cpu_seconds / achieved * 100, 2)
                if cpu_seconds is not None and achieved > 0 else None),
        }
        members_complete = {
            observation.spec.name: per_member[observation.device_id]
            for _, observation in pages
        }
        check("every original member showed a still and an advancing video",
              all(row["still_seen"] and row["video_seen"]
                  for row in members_complete.values()),
              members=members_complete)
        check("no video stall was detected", not stalls, stalls=stalls[:20])
        check("no stale still paint was detected", not stale_paints,
              stale_paints=stale_paints[:20])
        check("boundaries changed at least twice", boundary_count >= 3,
              display_changes=boundary_count)
        set_scenario("boundaries", "passed" if (
            boundary_count >= 3 and all(
                row["still_seen"] and row["video_seen"]
                for row in members_complete.values())
        ) else "failed", {
            "display_changes": boundary_count,
            "members": members_complete,
        })
        set_scenario("sampling-coverage", "passed" if (
            achieved >= args.duration - 1.0
            and summary["unexplained_max_gap_s"] <= 1.0
        ) else "failed", summary)
        set_scenario("resources", "passed" if (
            resources_missing == 0 and process.poll() is None and server_failures == 0
        ) else "failed", {
            "missing_samples": resources_missing,
            "server_failures": server_failures,
        })

        if recovery_mono_window is not None and pages:
            expected_recovery, unexpected_issues = split_expected_issues(
                unexpected_issues,
                pages[0][1].spec.name,
                recovery_mono_window,
            )
            expected_issues.extend(expected_recovery)
        check("no unexpected page, console, request or socket issues",
              not unexpected_issues, issues=unexpected_issues[:40])
        (artifacts / "issues.json").write_text(json.dumps({
            "expected_controlled_recovery": expected_issues,
            "unexpected": unexpected_issues,
        }, indent=2))
        tools["socket_timeline"] = {
            observation.spec.name: [
                {"elapsed_s": round(event["time"] - soak_start, 3), "kind": event["kind"],
                 "code": event.get("code")}
                for event in observation.events
                if event["kind"] in ("ws_open", "ws_close", "ws_error")
            ]
            for _, observation in pages
        }
        tools["expected_recovery_issues"] = issue_summary(expected_issues)
        tools["unexpected_issue_details"] = issue_summary(unexpected_issues)
        tools["unexpected_issue_count"] = len(unexpected_issues)
        tools["sampling"] = summary
        tools["stalls"] = stalls
        tools["stale_paints"] = stale_paints
        tools["boundaries"] = boundary_count
        tools["achieved_seconds"] = round(achieved, 3)
        tools["samples"] = len(samples)
        tools["deliberate_windows"] = deliberate_windows
        tools["final_idle"] = final_idle
        tools["reload_ok"] = reload_ok
        tools["cohort"] = sorted(cohort)
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc),
                 "traceback": traceback.format_exc()}
        traceback.print_exc()
    finally:
        if soak_start is not None and achieved == 0.0:
            achieved = time.monotonic() - soak_start
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

    if not artifacts.exists():
        artifacts.mkdir(parents=True)
    (artifacts / "samples.json").write_text(json.dumps(samples, indent=2))
    (artifacts / "timeline.json").write_text(json.dumps(timeline, indent=2))
    (artifacts / "sockets.json").write_text(json.dumps(tools.get("socket_timeline", {}), indent=2))
    (artifacts / "playlist.json").write_text(json.dumps(tools.get("playlist", {}), indent=2))
    bounded_artifacts = [
        artifacts / name for name in (
            "samples.json", "timeline.json", "sockets.json", "playlist.json",
            "issues.json", "fixture.mp4", "server.log",
        ) if (artifacts / name).exists()
    ] + sorted(artifacts.glob("client-*.png"))
    artifacts_hashed = evidence.artifact_hashes(bounded_artifacts)
    finished_at = evidence.iso_now()

    if recovery_short and not recovery_done:
        set_scenario("controlled-recovery", "skipped", "duration too short")
        set_scenario("reconnect", "skipped", "duration too short")
        skipped.append("controlled recovery and reconnect: duration too short")
    if stop_short and not stop_done:
        set_scenario("playback-stop-start", "skipped", "duration too short")
        skipped.append("playback Stop/Start: duration too short")
    scenario_rows = [
        evidence.scenario_row(name, row["status"], detail=row["detail"])
        for name, row in scenario_detail.items()
    ]
    limitations = [
        "one host runs the server and every Chromium client; CPU, memory, GPU, "
        "display refresh, clocks and the NIC are shared",
        "visible pictures come from canvas pixels and media currentTime on this host, "
        "not from a camera or an optical measurement",
        "network loss is a Playwright offline context, not Wi-Fi, AP, radio or OS behaviour",
        "the sampling loop pauses during the controlled recovery and Stop/Start phases; "
        "those intervals are reported as unobserved",
        "synthetic ffmpeg testsrc2 is not tablet-decoded camera content",
        "this short software run is not the required two-hour physical media soak or "
        "the overnight still soak; both gates remain MISSING",
    ]
    report = build_soak_report(
        started_at=started_at,
        finished_at=finished_at,
        checks=checks,
        scenarios=scenario_rows,
        artifacts=artifacts_hashed,
        cohort=cohort,
        tools=tools,
        skipped=skipped,
        unobserved=unobserved,
        limitations=limitations,
        repository=repository,
        error=error,
    )
    evidence.write_report(artifacts / "report.json", report)
    print(json.dumps({
        "tool": TOOL,
        "completion": report["completion"],
        "checks": f"{report['checks_passed']}/{report['checks_total']}",
        "scenarios": f"{report['scenarios_passed']}/{report['scenarios_total']}",
        "samples": len(samples),
        "achieved_seconds": round(achieved, 3),
        "requested_seconds": args.duration,
        "failures": report["failure_reasons"],
        "artifacts": str(artifacts),
    }, indent=1))
    if report["completion"] != "complete":
        return 2 if error is not None else 1
    return 0


def httpx_client(process: subprocess.Popen):
    import httpx

    base = process.base_url  # type: ignore[attr-defined]
    return httpx.Client(base_url=base, headers={"Origin": base}, timeout=20)


def wait_ready(http: Any, process: subprocess.Popen, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            if http.get("/wall").status_code == 200:
                return
        except Exception:
            pass
        if process.poll() is not None or time.monotonic() >= deadline:
            raise RuntimeError("fleet server did not become ready; see server.log")
        time.sleep(0.1)


def _start_server(root: Path, artifacts: Path, http_log_name: str) -> subprocess.Popen:
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
    log = (artifacts / http_log_name).open("x")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path,
                        help="New directory outside the repository for evidence")
    parser.add_argument("--clients", type=int, default=DEFAULT_CLIENTS)
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION_SECONDS,
                        help="Sampling seconds after playback starts (default 60)")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--recovery-offline-seconds", type=float,
                        default=DEFAULT_RECOVERY_OFFLINE_SECONDS)
    parser.add_argument("--ready-seconds", type=float, default=20.0)
    args = parser.parse_args(argv)
    if not 1 <= args.clients <= 8:
        parser.error("--clients must be 1..8")
    if args.duration < 5:
        parser.error("--duration must be at least 5 seconds")
    if not 0.1 <= args.interval <= 5:
        parser.error("--interval must be 0.1..5 seconds")
    if not 0.5 <= args.recovery_offline_seconds <= 30:
        parser.error("--recovery-offline-seconds must be 0.5..30")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
