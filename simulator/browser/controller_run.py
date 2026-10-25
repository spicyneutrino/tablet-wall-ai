"""Durable controller acceptance for F3 (pause) and F4 (live identity).

    .venv/bin/python -m simulator.browser.controller_run --artifacts /tmp/...

Starts a disposable real server on a free port with temporary storage, two
calibrated Chromium clients and a 20 s video plus a still. It then drives the
physical controller UI rather than only reading ``data-state``:

* Pause must render ``Paused`` with the live item name, the paused dwell must
  not age, the status poll must stay healthy, Resume must advance the clients
  and Stop must restore the persisted scene.
* While the frozen video session keeps playing, a different playlist is edited,
  reordered and saved from the controller. A reload must keep the live name,
  kind, duration and dwell from the frozen session, show the new still in the
  editable rows and hide the editable ``Now`` marker because the revisions
  differ. The same save is repeated while paused and while a real recovery is
  in progress.
* A new Start after Stop must use the newly saved still.
* 390x844 must have no horizontal overflow and a readable pause summary.
* Unexpected controller/client page errors, console errors and failed
  requests fail the run.

Software browser evidence only: one host clock, no optical or physical claim.
Every artifact directory is new and outside the checkout.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

import httpx
from playwright.async_api import async_playwright

from simulator.browser.run import (
    CUT_COLOURS,
    ClientSpec,
    Rig,
    artifact_directory,
    calibrate_cohort,
    child_environment,
    descendants,
    open_cohort,
    stop_server,
)

REPO = Path(__file__).resolve().parents[2]
VIDEO_SECONDS = 20
CLIENTS = (
    (ClientSpec("controller-a", 240, 160, 1), 0),
    (ClientSpec("controller-b", 200, 150, 1.25), 180),
)
SCENARIOS = {
    "S1": "disposable server, 20 s video plus still, two calibrated clients",
    "S2": "the controller renders the live playing video",
    "S3": "Pause renders the frozen live name and a stable dwell with healthy polls",
    "S4": "Resume returns to playing and the clients advance",
    "S5": "390x844 pause summary is readable without horizontal overflow",
    "S6": "a saved draft during playback keeps the frozen live identity",
    "S7": "a saved draft while paused keeps the live name and the frozen dwell",
    "S8": "a saved draft during recovery keeps the frozen live identity",
    "S9": "Stop restores the persisted scene",
    "S10": "a new Start uses the newly saved still",
    "S11": "no unexpected page errors, console errors or failed requests",
}
DWELL_RE = re.compile(r"\b\d+(?:\.\d+)? s left")
EXPECTED_EVENT_REASONS = {
    "net::ERR_ABORTED": (
        "the browser cancelled an in-flight request when a page navigated or a media "
        "element was torn down; never an application failure"
    ),
}


async def wait_until(predicate, timeout: float, message: str, interval: float = .05) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if inspect.isawaitable(value):
            value = await value
        if value:
            return value
        await asyncio.sleep(interval)
    raise RuntimeError(message)


def build_video(target: Path) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required for the controller video fixture")
    argv = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=30:duration={VIDEO_SECONDS}",
        "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.0",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(target),
    ]
    done = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    if done.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + done.stderr[-2000:])
    return {"argv": argv, "bytes": target.stat().st_size}


def git(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=REPO, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


async def video_state(page: Any) -> list[dict[str, Any]]:
    return await page.evaluate("""() => [...document.querySelectorAll('video')].map(v => {
        const rect = v.getBoundingClientRect();
        const style = getComputedStyle(v);
        return {
            visible: style.visibility !== 'hidden' && style.display !== 'none'
                && rect.width > 0 && rect.height > 0,
            paused: v.paused, ended: v.ended, readyState: v.readyState,
            currentTime: v.currentTime, duration: v.duration,
            videoWidth: v.videoWidth, videoHeight: v.videoHeight,
        };
    })""")


async def canvas_centre(page: Any) -> list[int]:
    return await page.evaluate("""() => {
        const canvas = document.querySelector('#surface');
        const probe = document.createElement('canvas');
        probe.width = probe.height = 1;
        const context = probe.getContext('2d', {willReadFrequently: true});
        context.drawImage(canvas, Math.floor(canvas.width / 2),
                          Math.floor(canvas.height / 2), 1, 1, 0, 0, 1, 1);
        return [...context.getImageData(0, 0, 1, 1).data];
    }""")


def close_enough(pixel: list[int], rgb: tuple[int, int, int], tolerance: int = 30) -> bool:
    return len(pixel) >= 3 and max(abs(a - b) for a, b in zip(pixel[:3], rgb)) <= tolerance


async def main(artifacts_arg: Path) -> int:
    artifacts = artifact_directory(artifacts_arg)
    root = Path(tempfile.mkdtemp(prefix="tw-controller-", dir="/tmp"))
    for name in ("assets", "media", "tmp"):
        (root / name).mkdir()
    report: dict[str, Any] = {
        "runner": "controller_run",
        "runner_version": 1,
        "mode": "software browser evidence, not optical or physical",
        "head": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "artifacts": str(artifacts),
        "temporary_root": str(root),
        "scenarios_expected": SCENARIOS,
        "checks": [],
        "page_events": [],
    }
    checks: list[dict[str, Any]] = report["checks"]
    events: list[dict[str, Any]] = report["page_events"]
    phase = {"id": "S1"}
    state: dict[str, Any] = {"browser_version": None}

    def check(scenario: str, name: str, ok: bool, **detail: Any) -> bool:
        checks.append({"scenario": scenario, "name": name, "passed": bool(ok), **detail})
        return bool(ok)

    def record(page_label: str, kind: str, **detail: Any) -> None:
        events.append({
            "page": page_label, "kind": kind, "phase": phase["id"],
            "at_ms": round(time.time() * 1000), **detail,
        })

    def watch(page: Any, label: str) -> None:
        page.on("pageerror", lambda error: record(label, "pageerror", message=str(error)))
        def console(message: Any) -> None:
            if message.type in ("error", "warning"):
                record(label, f"console.{message.type}", message=message.text)
        page.on("console", console)
        page.on("requestfailed", lambda request: record(
            label, "requestfailed", url=request.url, failure=request.failure or ""))
        page.on("response", lambda response: record(
            label, "response", status=response.status, url=response.url)
            if response.status >= 400 else None)

    def scenario_statuses(status: str) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in checks:
            grouped.setdefault(item["scenario"], []).append(item)
        rows = []
        for scenario, name in SCENARIOS.items():
            seen = grouped.get(scenario, [])
            if seen and all(item["passed"] for item in seen):
                result = "passed"
            elif seen:
                result = "failed"
            else:
                result = "incomplete" if status != "passed" else "failed"
            rows.append({
                "id": scenario, "name": name, "status": result,
                "checks": len(seen),
                "failed": sum(1 for item in seen if not item["passed"]),
            })
        return rows

    def write_report(status: str, cleanup: dict[str, Any] | None = None) -> None:
        report["status"] = status
        report["checks_passed"] = sum(1 for item in checks if item["passed"])
        report["checks_total"] = len(checks)
        report["scenario_results"] = scenario_statuses(status)
        report["scenarios_passed"] = sum(
            1 for item in report["scenario_results"] if item["status"] == "passed")
        report["scenarios_total"] = len(report["scenario_results"])
        report["browser_version"] = state["browser_version"]
        if cleanup is not None:
            report["cleanup"] = cleanup
        (artifacts / "report.json").write_text(json.dumps(report, indent=2))
        lines = [
            "# Controller acceptance report",
            "",
            f"- Runner: `controller_run` v1 ({report['mode']})",
            f"- Head: `{report['head']}` on `{report['branch']}` (dirty={report['dirty']})",
            f"- Status: **{status}**",
            f"- Checks: {report['checks_passed']}/{report['checks_total']} passed",
            f"- Scenarios: {report['scenarios_passed']}/{report['scenarios_total']} passed",
            f"- Browser: {report['browser_version']}",
            f"- Artifacts: `{report['artifacts']}`",
            "",
            "| Scenario | Status | Checks | Failed |",
            "| --- | --- | --- | --- |",
        ]
        for row in report["scenario_results"]:
            lines.append(
                f"| {row['id']} {row['name']} | {row['status']} | {row['checks']} | {row['failed']} |")
        if report.get("error"):
            lines += ["", "## Error", "", f"`{report['error']['type']}: {report['error']['message']}`"]
        if cleanup is not None:
            lines += ["", "## Cleanup", "", f"`{json.dumps(cleanup)}`"]
        (artifacts / "report.md").write_text("\n".join(lines) + "\n")

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    base = f"http://127.0.0.1:{listener.getsockname()[1]}"
    env = child_environment(root)
    env.update({"TABLET_WALL_UPLOAD_MODE": "loopback", "TABLET_WALL_OPERATOR_ORIGIN": base})
    log = (artifacts / "server.log").open("x")
    process = None
    http = None
    playwright = None
    browser = None
    controller = None
    mobile = None
    final = {"status": "incomplete"}

    def status() -> dict[str, Any]:
        response = http.get("/api/v3/playback")
        response.raise_for_status()
        return response.json()

    def saved_playlist() -> dict[str, Any]:
        return http.get("/api/v3/playlist").json()["playlist"]

    def put_playlist(items: list[dict[str, Any]], loop: bool = True) -> dict[str, Any]:
        etag = http.get("/api/v3/playlist").json()["etag"]
        response = http.put("/api/v3/playlist", json={"items": items, "loop": loop},
                            headers={"If-Match": etag})
        if response.status_code != 200:
            raise RuntimeError(f"playlist setup failed: {response.status_code} {response.text[-400:]}")
        return response.json()["playlist"]

    try:
        report["origin"] = base
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--fd", str(listener.fileno()),
             "--workers", "1", "--no-access-log"],
            cwd=REPO, env=env, pass_fds=(listener.fileno(),),
            stdout=log, stderr=subprocess.STDOUT,
        )
        listener.close()
        listener = None
        http = httpx.Client(base_url=base, headers={"Origin": base}, timeout=30)

        async def server_ready() -> bool:
            try:
                return http.get("/wall").status_code in (200, 409)
            except httpx.HTTPError:
                return False

        await wait_until(server_ready, 25, "the controller server never became ready")
        report["server_pid"] = process.pid

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            env={**os.environ, "TMPDIR": str(root / "tmp")})
        state["browser_version"] = browser.version

        def rig_check(name: str, ok: bool, **detail: Any) -> bool:
            return check("S1", name, ok, **detail)

        rig = Rig(base=base, http=http, browser=browser, playwright=playwright,
                  browser_env={**os.environ, "TMPDIR": str(root / "tmp")}, root=root,
                  artifacts=artifacts, observations=[], captured_pages=[],
                  resources=[], owned={}, check=rig_check)
        pages = await open_cohort(rig, CLIENTS, "controller")
        for page, observation in pages:
            watch(page, observation.spec.name)
        assets = await calibrate_cohort(
            rig, pages, [mount for _, mount in CLIENTS], CUT_COLOURS, "controller")
        check("S1", "two independent clients calibrated, placed and shown the idle still",
              len(pages) == 2, clients=[observation.spec.name for _, observation in pages])

        clip = root / "f3-session.mp4"
        report["fixture"] = build_video(clip)
        uploaded = http.post("/uploads?name=f3-session.mp4", content=clip.read_bytes(),
                             headers={"Content-Type": "video/mp4"})
        if uploaded.status_code != 201:
            raise RuntimeError(f"video upload failed: {uploaded.status_code} {uploaded.text[-400:]}")
        video = uploaded.json()["asset"]
        report["video"] = video
        check("S1", "the fixture video is a 20 s H.264 yuv420p clip",
              video.get("kind") == "video" and video.get("durationMs") == VIDEO_SECONDS * 1000
              and video.get("pixelFormat") == "yuv420p",
              duration_ms=video.get("durationMs"), kind=video.get("kind"))
        original = [
            {"asset": video["id"], "dwell_ms": 1000},
            {"asset": assets["red"], "dwell_ms": 1000},
        ]
        saved = put_playlist(original, loop=True)
        report["original_playlist"] = saved
        check("S1", "the initial saved playlist is the 20 s video and a red still",
              saved["revision"] == 1
              and [item["asset"] for item in saved["items"]] == [video["id"], assets["red"]]
              and saved["items"][0]["dwell_ms"] == VIDEO_SECONDS * 1000,
              playlist=saved)

        controller = await browser.new_page(viewport={"width": 1440, "height": 1000})
        watch(controller, "controller-desktop")
        await controller.goto(base + "/controller/physical.html", wait_until="networkidle")
        await controller.evaluate("document.querySelector('#playback-details').open = true")
        await controller.wait_for_function(
            "() => document.querySelectorAll('#playlist-library option').length > 1",
            timeout=15000)
        await controller.wait_for_function(
            "() => document.querySelectorAll('.playlist-item').length === 2", timeout=15000)
        await controller.wait_for_function(
            "() => !document.querySelector('#btn-playback-start').disabled", timeout=15000)

        async def summary() -> str:
            return await controller.locator("#playback-status").inner_text()

        async def facts() -> str:
            return await controller.locator("#playback-facts").inner_text()

        async def poll_note() -> str:
            return await controller.locator("#playback-poll-note").inner_text()

        async def rows() -> list[str]:
            return await controller.locator(".playlist-name").all_inner_texts()

        async def now_markers() -> int:
            return await controller.locator('.playlist-item[data-current="true"]').count()

        async def open_details() -> None:
            await controller.evaluate("document.querySelector('#playback-details').open = true")

        async def wait_rows(count: int, timeout: float = 15000) -> None:
            await controller.wait_for_function(
                "(count) => document.querySelectorAll('.playlist-item').length === count",
                arg=count, timeout=timeout)

        async def wait_summary(prefix: str, timeout: float = 15000) -> None:
            await controller.wait_for_function(
                "(prefix) => (document.querySelector('#playback-status')?.textContent || '')"
                ".startsWith(prefix)", arg=prefix, timeout=timeout)

        async def add_asset(asset_id: str) -> None:
            await controller.select_option("#playlist-library", asset_id)
            await controller.wait_for_function(
                "() => !document.querySelector('#btn-playlist-add').disabled", timeout=5000)
            await controller.click("#btn-playlist-add")

        async def move_up(index: int) -> None:
            await controller.click(
                f'.playlist-item[data-index="{index}"] [data-action="up"]')

        async def remove_row(index: int) -> None:
            await controller.click(
                f'.playlist-item[data-index="{index}"] [data-action="remove"]')

        async def save_playlist(expected_revision: int) -> None:
            await controller.click("#btn-playlist-save")
            await wait_until(
                lambda: saved_playlist().get("revision") == expected_revision, 10,
                f"the saved playlist never advanced to revision {expected_revision}")
            await controller.wait_for_function(
                "() => (document.querySelector('#playlist-msg')?.textContent || '')"
                ".startsWith('Playlist saved')", timeout=10000)

        async def reload_controller() -> None:
            await controller.reload(wait_until="networkidle")
            await controller.evaluate("document.querySelector('#playback-details').open = true")
            await controller.wait_for_function(
                "() => !document.querySelector('#btn-playback-start').disabled"
                " || !document.querySelector('#btn-playback-stop').hidden",
                timeout=15000)
            await controller.wait_for_function(
                "() => (document.querySelector('#playlist-hint')?.textContent || '')"
                " === 'Saved on the server.'", timeout=15000)

        def healthy_poll(text: str) -> bool:
            return "Live status, read at" in text and "Status unavailable" not in text

        async def poll_is_healthy() -> bool:
            if not healthy_poll(await poll_note()):
                return False
            return await controller.locator("#playback-stale").is_hidden()

        async def video_window(timeout: float = 30, max_elapsed_ms: int = 9000) -> dict[str, Any]:
            async def ready() -> Any:
                current = status()
                live = (current.get("live") or {}).get("current") or {}
                effective = current.get("current_effective_ms")
                now = current.get("now_ms")
                if (current.get("state") == "playing" and live.get("asset") == video["id"]
                        and effective is not None and now is not None
                        and 250 <= now - effective <= max_elapsed_ms):
                    return current
                return None
            return await wait_until(ready, timeout, "the session never entered a fresh video window")

        async def clients_advancing(minimum: float = .3) -> bool:
            for page, _ in pages:
                videos = await video_state(page)
                if not any(v["visible"] and not v["paused"] and v["currentTime"] > minimum
                           for v in videos):
                    return False
            return True

        async def clients_show_still(rgb: tuple[int, int, int]) -> bool:
            for page, _ in pages:
                videos = await video_state(page)
                if any(v["visible"] for v in videos):
                    return False
                if not close_enough(await canvas_centre(page), rgb):
                    return False
            return True

        phase["id"] = "S1"
        await controller.click("#btn-playback-start")
        await wait_until(lambda: status().get("state") in ("playing", "preparing"), 15,
                         "the Start never began a session")
        await wait_until(lambda: status().get("state") == "playing", 25,
                         "the session never reached playing")
        await wait_until(clients_advancing, 25, "the clients never advanced the video")
        report["session"] = status()
        check("S1", "Start from the controller begins a playing session on both clients", True)

        phase["id"] = "S2"
        await wait_summary("Playing")
        playing = status()
        report["status_playing"] = playing
        live = (playing.get("live") or {}).get("current") or {}
        check("S2", "the server reports the frozen video identity for the live session",
              live.get("asset") == video["id"] and live.get("kind") == "video"
              and live.get("duration_ms") == VIDEO_SECONDS * 1000
              and playing.get("playlist_revision") == 1,
              live=live, playlist_revision=playing.get("playlist_revision"))
        playing_summary = await summary()
        playing_facts = await facts()
        report["controller_playing"] = {"summary": playing_summary, "facts": playing_facts}
        check("S2", "the controller summary names the playing video",
              playing_summary.startswith("Playing:") and "f3-session.mp4" in playing_summary
              and DWELL_RE.search(playing_summary) is not None,
              summary=playing_summary)
        check("S2", "the controller facts show the frozen 20 s video kind and duration",
              "Current media" in playing_facts and "video \u00b7 20 s clip" in playing_facts,
              facts=playing_facts)
        await controller.screenshot(path=str(artifacts / "controller-playing.png"), full_page=True)

        phase["id"] = "S3"
        await video_window()
        mark = len(events)
        await controller.click("#btn-playback-pause")
        await wait_until(lambda: status().get("state") == "paused", 10, "pause did not stick")
        await wait_summary("Paused on")
        await asyncio.sleep(.4)
        paused_one = await summary()
        paused_facts_one = await facts()
        poll_one = await poll_note()
        paused_status = status()
        report["pause"] = {
            "status": paused_status, "summary": paused_one, "facts": paused_facts_one,
            "poll": poll_one,
        }
        paused_dwell_before = DWELL_RE.search(paused_one)
        check("S3", "the pause summary says Paused with the live video name",
              paused_one.startswith("Paused on") and "f3-session.mp4" in paused_one
              and paused_dwell_before is not None,
              summary=paused_one)
        check("S3", "the paused facts keep the frozen 20 s video kind and duration",
              "Current media" in paused_facts_one
              and "video \u00b7 20 s clip" in paused_facts_one,
              facts=paused_facts_one)
        check("S3", "the pause control offers Resume and Stop stays available",
              await controller.locator("#btn-playback-pause").inner_text() == "Resume"
              and await controller.locator("#btn-playback-stop").is_visible())
        check("S3", "the poll is healthy at the pause", await poll_is_healthy(), poll=poll_one)
        await controller.screenshot(path=str(artifacts / "controller-paused.png"), full_page=True)

        phase["id"] = "S5"
        mobile = await browser.new_page(viewport={"width": 390, "height": 844})
        watch(mobile, "controller-mobile")
        await mobile.goto(base + "/controller/physical.html", wait_until="networkidle")
        await mobile.wait_for_function(
            "() => (document.querySelector('#playback-status')?.textContent || '')"
            ".startsWith('Paused on')", timeout=15000)
        await asyncio.sleep(.5)
        mobile_state = await mobile.evaluate("""() => {
            const summary = document.querySelector('#playback-status');
            const style = getComputedStyle(summary);
            const rect = summary.getBoundingClientRect();
            const pause = document.querySelector('#btn-playback-pause');
            return {
                innerWidth: window.innerWidth,
                documentScrollWidth: document.documentElement.scrollWidth,
                documentClientWidth: document.documentElement.clientWidth,
                summary: summary.textContent,
                summaryLeft: rect.left, summaryRight: rect.right, summaryWidth: rect.width,
                summaryOverflow: summary.scrollWidth - summary.clientWidth,
                fontSize: parseFloat(style.fontSize),
                pauseText: pause.textContent,
                pauseVisible: !!pause.getClientRects().length,
            };
        }""")
        report["mobile"] = mobile_state
        check("S5", "the 390x844 controller has no horizontal page overflow",
              mobile_state["documentScrollWidth"] - mobile_state["documentClientWidth"] <= 1,
              width=mobile_state["documentScrollWidth"],
              viewport=mobile_state["documentClientWidth"])
        check("S5", "the mobile pause summary fits, stays readable and names the video",
              mobile_state["summaryLeft"] >= 0
              and mobile_state["summaryRight"] <= mobile_state["innerWidth"] + 1
              and mobile_state["summaryOverflow"] <= 1
              and mobile_state["fontSize"] >= 12
              and "Paused on" in mobile_state["summary"]
              and "f3-session.mp4" in mobile_state["summary"]
              and DWELL_RE.search(mobile_state["summary"]) is not None,
              summary=mobile_state["summary"], font=mobile_state["fontSize"],
              right=mobile_state["summaryRight"], overflow=mobile_state["summaryOverflow"])
        check("S5", "the mobile pause control offers Resume",
              mobile_state["pauseText"] == "Resume" and mobile_state["pauseVisible"],
              button=mobile_state["pauseText"])
        await mobile.screenshot(path=str(artifacts / "mobile-paused.png"), full_page=True)
        mobile_bad = [event for event in events if event["page"] == "controller-mobile"
                      and event["kind"] in ("pageerror", "console.error")]
        check("S5", "the mobile controller page raised no errors", not mobile_bad,
              events=mobile_bad[:5])
        await mobile.close()
        mobile = None

        phase["id"] = "S3"
        await asyncio.sleep(2.4)
        paused_two = await summary()
        paused_facts_two = await facts()
        poll_two = await poll_note()
        report["pause"]["summary_after_2s"] = paused_two
        report["pause"]["facts_after_2s"] = paused_facts_two
        report["pause"]["poll_after_2s"] = poll_two
        check("S3", "the pause summary is identical after 2.4 s",
              paused_one == paused_two, before=paused_one, after=paused_two)
        paused_dwell_after = DWELL_RE.search(paused_two)
        check("S3", "the paused dwell text does not age",
              paused_dwell_before is not None and paused_dwell_after is not None
              and paused_dwell_before.group(0) == paused_dwell_after.group(0),
              before=paused_one, after=paused_two)
        facts_dwell_one = [line for line in paused_facts_one.splitlines()
                           if DWELL_RE.search(line)]
        facts_dwell_two = [line for line in paused_facts_two.splitlines()
                           if DWELL_RE.search(line)]
        check("S3", "the paused facts dwell is identical after 2.4 s",
              facts_dwell_one == facts_dwell_two and facts_dwell_one != [],
              before=facts_dwell_one, after=facts_dwell_two)
        check("S3", "the poll stays healthy while paused", await poll_is_healthy(), poll=poll_two)

        phase["id"] = "S4"
        await controller.click("#btn-playback-pause")
        await wait_until(lambda: status().get("state") in ("preparing", "playing"), 15,
                         "Resume did not leave paused")
        await wait_until(lambda: status().get("state") == "playing", 25,
                         "Resume never reached playing")
        await wait_summary("Playing")
        await wait_until(clients_advancing, 20, "the clients did not advance after Resume")
        resumed_summary = await summary()
        check("S4", "Resume returns to playing and both clients advance",
              resumed_summary.startswith("Playing:"), summary=resumed_summary)
        pause_events = events[mark:]
        pause_bad = [event for event in pause_events
                     if event["kind"] in ("pageerror", "console.error", "requestfailed", "response")]
        check("S3", "Pause and Resume raised no page errors, console errors or failed requests",
              not pause_bad, events=pause_bad[:5])
        report["resume"] = {
            "status": status(),
            "clients": [await video_state(page) for page, _ in pages],
        }

        phase["id"] = "S6"
        await video_window()
        session_revision = status()["playlist_revision"]
        await add_asset(assets["green"])
        await wait_rows(3)
        await move_up(2)
        await move_up(1)
        await remove_row(1)
        await remove_row(1)
        await wait_rows(1)
        preview_rows = await rows()
        check("S6", "the draft can be edited and reordered down to the new green still",
              preview_rows == ["controller-green.png"], rows=preview_rows)
        await save_playlist(2)
        saved_two = saved_playlist()
        check("S6", "the saved playlist advanced to revision 2 with only the new still",
              saved_two.get("revision") == 2
              and [item["asset"] for item in saved_two["items"]] == [assets["green"]],
              saved=saved_two)
        await reload_controller()
        await wait_summary("Playing")
        async def live_video_current() -> bool:
            current = status()
            return (current.get("state") == "playing"
                    and (current.get("live") or {}).get("current", {}).get("asset")
                    == video["id"])
        await wait_until(live_video_current, 15,
                         "the frozen video was not current after the reload")
        live_summary = await summary()
        live_facts = await facts()
        live_rows = await rows()
        markers = await now_markers()
        live_status = status()
        report["playing_draft"] = {
            "summary": live_summary, "facts": live_facts, "rows": live_rows,
            "markers": markers, "status": live_status, "saved": saved_two,
        }
        live_dwell = DWELL_RE.search(live_summary)
        check("S6", "the reloaded summary still names the frozen video, not the new still",
              live_summary.startswith("Playing:")
              and "f3-session.mp4" in live_summary
              and "controller-green.png" not in live_summary
              and live_dwell is not None,
              summary=live_summary)
        check("S6", "the reloaded facts keep the frozen 20 s video and its remaining dwell",
              "Current media" in live_facts and "video \u00b7 20 s clip" in live_facts
              and "Remaining dwell" in live_facts
              and any(DWELL_RE.search(line) for line in live_facts.splitlines()),
              facts=live_facts)
        check("S6", "the editable rows show the newly saved still",
              live_rows == ["controller-green.png"], rows=live_rows)
        check("S6", "no editable row carries the Now marker when the revisions differ",
              markers == 0 and live_status.get("playlist_revision") == session_revision
              and saved_two.get("revision") != session_revision,
              markers=markers, session_revision=live_status.get("playlist_revision"),
              saved_revision=saved_two.get("revision"))
        await controller.screenshot(
            path=str(artifacts / "live-vs-editable-desktop.png"), full_page=True)

        phase["id"] = "S7"
        await video_window(max_elapsed_ms=10000)
        await controller.click("#btn-playback-pause")
        await wait_until(lambda: status().get("state") == "paused", 10,
                         "the second pause did not stick")
        await wait_summary("Paused on")
        await open_details()
        await asyncio.sleep(.4)
        paused_before_save = await summary()
        paused_facts_before_save = await facts()
        check("S7", "the second pause again names the frozen video with a paused dwell",
              paused_before_save.startswith("Paused on")
              and "f3-session.mp4" in paused_before_save
              and DWELL_RE.search(paused_before_save) is not None,
              summary=paused_before_save)
        await add_asset(assets["yellow"])
        await wait_rows(2)
        await move_up(1)
        await wait_rows(2)
        reordered_rows = await rows()
        check("S7", "the draft reorder is visible before the save",
              reordered_rows == ["controller-yellow.png", "controller-green.png"],
              rows=reordered_rows)
        await save_playlist(3)
        saved_three = saved_playlist()
        await reload_controller()
        await wait_summary("Paused on")
        await wait_rows(2)
        await asyncio.sleep(.5)
        paused_after_save = await summary()
        paused_facts_after_save = await facts()
        paused_rows_after = await rows()
        paused_markers = await now_markers()
        paused_status_after = status()
        report["paused_draft"] = {
            "summary_before": paused_before_save, "summary_after": paused_after_save,
            "facts_before": paused_facts_before_save, "facts_after": paused_facts_after_save,
            "rows": paused_rows_after, "markers": paused_markers,
            "saved": saved_three, "status": paused_status_after,
        }
        check("S7", "the paused summary is unchanged by saving another playlist",
              paused_after_save == paused_before_save,
              before=paused_before_save, after=paused_after_save)
        check("S7", "the paused facts keep the frozen video and the same dwell",
              "Current media" in paused_facts_after_save
              and "video \u00b7 20 s clip" in paused_facts_after_save
              and [line for line in paused_facts_before_save.splitlines()
                   if DWELL_RE.search(line)]
              == [line for line in paused_facts_after_save.splitlines()
                  if DWELL_RE.search(line)],
              facts=paused_facts_after_save)
        check("S7", "the editable rows show the reordered saved stills",
              paused_rows_after == ["controller-yellow.png",
                                    "controller-green.png"],
              rows=paused_rows_after)
        check("S7", "the paused editable rows carry no Now marker",
              paused_markers == 0 and paused_status_after.get("state") == "paused",
              markers=paused_markers)
        await controller.screenshot(
            path=str(artifacts / "paused-after-save-desktop.png"), full_page=True)
        phase["id"] = "S7"
        await controller.click("#btn-playback-pause")
        await wait_until(lambda: status().get("state") == "playing", 25,
                         "the second Resume never reached playing")
        await wait_summary("Playing")
        await wait_until(clients_advancing, 20, "the clients did not advance after the second Resume")
        phase["id"] = "S8"

        await video_window(max_elapsed_ms=10000)
        froze = await pages[0][0].evaluate("""() => {
            const video = [...document.querySelectorAll('video')].find((node) => {
                const style = getComputedStyle(node);
                const rect = node.getBoundingClientRect();
                return style.visibility !== 'hidden' && style.display !== 'none'
                    && rect.width > 0 && rect.height > 0;
            });
            if (!video) return null;
            video.__originalPlay = video.play.bind(video);
            video.play = function () { return new Promise(function () {}); };
            video.pause();
            return {src: video.currentSrc || video.src, time: video.currentTime};
        }""")
        check("S8", "one client's visible video is frozen with a hanging play promise",
              bool(froze) and froze.get("time", 0) > 0, froze=froze)
        await wait_until(lambda: status().get("state") == "recovering", 30,
                         "the server never started a recovery")
        recovering = status()
        report["recovery_started"] = recovering
        # The recovery anchor is about one second out. Force the poll the way a
        # real focus/visibility return would, so the transient state is visible,
        # then edit and save through the same controls in one synchronous UI
        # turn before the anchor.
        try:
            await controller.evaluate(
                "() => document.dispatchEvent(new Event('visibilitychange'))")
            await controller.wait_for_function(
                "() => (document.querySelector('#playback-status')?.textContent || '')"
                ".startsWith('Recovering')", timeout=800)
            recovery_visible = await summary()
        except Exception:
            recovery_visible = ""
        report["recovery_visible"] = recovery_visible
        check("S8", "when the controller caught the live recovery it named the frozen video",
              not recovery_visible
              or (recovery_visible.startswith("Recovering")
                  and "f3-session.mp4" in recovery_visible),
              summary=recovery_visible)
        recovery_at_save = status()
        edited_rows = await controller.evaluate("""(assetId) => {
            const select = document.querySelector('#playlist-library');
            select.value = assetId;
            select.dispatchEvent(new Event('change', {bubbles: true}));
            document.querySelector('#btn-playlist-add').click();
            const upTwo = document.querySelector(
                '.playlist-item[data-index="2"] [data-action="up"]');
            if (upTwo) upTwo.click();
            const upOne = document.querySelector(
                '.playlist-item[data-index="1"] [data-action="up"]');
            if (upOne) upOne.click();
            document.querySelector('#btn-playlist-save').click();
            return [...document.querySelectorAll('.playlist-name')]
                .map(node => node.textContent);
        }""", assets["red"])
        await wait_until(lambda: saved_playlist().get("revision") == 4, 10,
                         "the recovery-time save never advanced to revision 4")
        saved_four = saved_playlist()
        recovery_after_save = status()
        report["recovery_draft"] = {
            "state_at_save": recovery_at_save.get("state"),
            "state_after_save": recovery_after_save.get("state"),
            "edited_rows": edited_rows,
            "saved": saved_four,
            "recovery": recovery_after_save.get("recovery"),
        }
        check("S8", "the playlist save and reorder happened while the server was recovering",
              recovery_at_save.get("state") == "recovering"
              and saved_four.get("revision") == 4,
              state=recovery_at_save.get("state"), saved=saved_four)
        await reload_controller()
        await controller.wait_for_function(
            "() => ['Recovering', 'Playing'].some(prefix =>"
            " (document.querySelector('#playback-status')?.textContent || '')"
            ".startsWith(prefix))", timeout=15000)
        await wait_rows(3)
        recovery_summary = await summary()
        recovery_facts = await facts()
        recovery_rows = await rows()
        recovery_markers = await now_markers()
        recovery_status = status()
        report["recovery_draft"].update({
            "summary": recovery_summary, "facts": recovery_facts,
            "rows": recovery_rows, "markers": recovery_markers,
            "status_after_reload": recovery_status,
        })
        check("S8", "the reloaded live summary still names the frozen video",
              ("Recovering" in recovery_summary or recovery_summary.startswith("Playing"))
              and "f3-session.mp4" in recovery_summary
              and (recovery_status.get("live") or {}).get("current", {}).get("asset")
              == video["id"],
              summary=recovery_summary,
              live=(recovery_status.get("live") or {}).get("current"))
        check("S8", "the reloaded facts keep the frozen video kind and duration",
              "Current media" in recovery_facts and "video \u00b7 20 s clip" in recovery_facts,
              facts=recovery_facts)
        check("S8", "the editable rows show the reordered draft saved during recovery",
              recovery_rows == ["controller-red.png",
                                "controller-yellow.png",
                                "controller-green.png"],
              rows=recovery_rows)
        check("S8", "the session revision stayed frozen while the saved revision advanced",
              recovery_status.get("playlist_revision") == 1
              and saved_four.get("revision") == 4 and recovery_markers == 0,
              session_revision=recovery_status.get("playlist_revision"),
              saved_revision=saved_four.get("revision"), markers=recovery_markers)
        await controller.screenshot(
            path=str(artifacts / "recovery-draft-desktop.png"), full_page=True)
        await wait_until(lambda: status().get("state") == "playing", 30,
                         "the cohort never resumed after the recovery")
        await wait_until(clients_advancing, 25, "the clients never advanced after the recovery")
        recovered = status()
        report["recovery_completed"] = recovered
        check("S8", "the recovery completed once, and the frozen identity survived the save",
              (recovered.get("recovery") or {}).get("attempts") == 1
              and (recovered.get("live") or {}).get("current", {}).get("asset") == video["id"],
              recovery=recovered.get("recovery"),
              live=(recovered.get("live") or {}).get("current"))

        phase["id"] = "S9"
        await controller.click("#btn-playback-stop")
        await wait_until(lambda: status().get("state") == "stopped", 10, "Stop did not stick")
        await controller.wait_for_function(
            "() => (document.querySelector('#playback-status')?.textContent || '')"
            " === 'Playback is stopped.'", timeout=10000)
        check("S9", "Stop restores the stopped summary",
              await summary() == "Playback is stopped.")
        await wait_until(
            lambda: clients_show_still(CUT_COLOURS["idle"]), 20,
            "the clients did not restore the persisted idle scene")
        check("S9", "Stop restores the persisted scene on both clients", True)
        check("S9", "Start is offered again after Stop",
              await controller.locator("#btn-playback-start").is_visible())
        await pages[0][0].screenshot(path=str(artifacts / "client-after-stop.png"))
        await controller.screenshot(path=str(artifacts / "controller-stopped.png"), full_page=True)

        phase["id"] = "S10"
        await wait_rows(3)
        await remove_row(0)
        await remove_row(0)
        await wait_rows(1)
        final_rows = await rows()
        check("S10", "the final draft is the new green still only",
              final_rows == ["controller-green.png"], rows=final_rows)
        await save_playlist(5)
        saved_five = saved_playlist()
        await controller.wait_for_function(
            "() => !document.querySelector('#btn-playback-start').disabled", timeout=10000)
        await controller.click("#btn-playback-start")
        await wait_until(lambda: status().get("state") == "playing", 25,
                         "the new Start never played")
        await wait_until(lambda: clients_show_still(CUT_COLOURS["green"]), 20,
                         "the clients never showed the newly saved green still")
        started = status()
        start_summary = await summary()
        start_markers = await now_markers()
        report["new_start"] = {
            "status": started, "summary": start_summary,
            "rows": await rows(), "markers": start_markers, "saved": saved_five,
        }
        live_start = (started.get("live") or {}).get("current") or {}
        check("S10", "the new Start uses the newly saved still revision",
              live_start.get("asset") == assets["green"] and live_start.get("kind") == "still"
              and started.get("playlist_revision") == saved_five.get("revision") == 5,
              live=live_start, playlist_revision=started.get("playlist_revision"))
        check("S10", "the controller names the newly started still",
              "controller-green.png" in start_summary, summary=start_summary)
        check("S10", "the matching revision marks the live row Now",
              start_markers == 1, markers=start_markers)
        await pages[0][0].screenshot(path=str(artifacts / "client-green-start.png"))
        await controller.screenshot(path=str(artifacts / "controller-new-start.png"),
                                    full_page=True)
        http.post("/api/v3/playback/stop",
                  headers={"If-Match": str(status().get("version"))})

        phase["id"] = "S11"
        warnings = [event for event in events if event["kind"] == "console.warning"]
        unexpected: list[dict[str, Any]] = []
        expected: list[dict[str, Any]] = []
        for event in events:
            if event["kind"] == "console.warning":
                continue
            if event["kind"] == "requestfailed" and event.get("failure") in EXPECTED_EVENT_REASONS:
                expected.append({**event, "reason": EXPECTED_EVENT_REASONS[event["failure"]]})
            else:
                unexpected.append(event)
        report["expected_events"] = expected
        report["console_warnings"] = warnings
        page_errors = [event for event in unexpected if event["kind"] == "pageerror"]
        console_errors = [event for event in unexpected if event["kind"] == "console.error"]
        failed = [event for event in unexpected
                  if event["kind"] in ("requestfailed", "response")]
        report["unexpected_events"] = unexpected
        check("S11", "no unexpected page errors on any controller or client page",
              not page_errors, events=page_errors[:5])
        check("S11", "no unexpected console errors on any controller or client page",
              not console_errors, events=console_errors[:5])
        check("S11", "no unexpected failed requests or HTTP responses at or above 400",
              not failed, events=failed[:5])
        check("S11", "the injected client fault was classified as an expected warning",
              any("video fault" in event.get("message", "") for event in warnings),
              warnings=warnings[:5])

        final["status"] = ("passed" if all(item["passed"] for item in checks) else "failed")
    except BaseException as error:
        report["error"] = {
            "type": type(error).__name__, "message": str(error),
            "traceback": traceback.format_exc(),
        }
        raise
    finally:
        cleanup: dict[str, Any] = {"errors": []}
        for page, name in ((mobile, "mobile"), (controller, "controller")):
            if page is not None:
                try:
                    await page.close()
                except Exception as error:  # noqa: BLE001 - evidence, never fatal
                    cleanup["errors"].append(f"closing the {name} page: {error}")
        if browser is not None:
            try:
                await browser.close()
                cleanup["browser_closed"] = True
            except Exception as error:  # noqa: BLE001
                cleanup["browser_closed"] = False
                cleanup["errors"].append(f"closing the browser: {error}")
        if playwright is not None:
            try:
                await playwright.stop()
            except Exception as error:  # noqa: BLE001
                cleanup["errors"].append(f"stopping Playwright: {error}")
        if http is not None:
            http.close()
        if process is not None:
            stop_server(process)
            cleanup["server_reaped"] = process.poll() is not None
            cleanup["server_pid"] = process.pid
        if listener is not None:
            listener.close()
        log.close()
        try:
            shutil.rmtree(root)
            cleanup["temporary_root_removed"] = not root.exists()
        except OSError as error:  # noqa: BLE001
            cleanup["temporary_root_removed"] = False
            cleanup["errors"].append(f"removing the temporary root: {error}")
        cleanup["remaining_descendants"] = descendants(os.getpid())
        if final["status"] == "passed":
            cleanup_check_name = "the server, browser and temporary root are gone"
            check("S11", cleanup_check_name,
                  cleanup.get("server_reaped") is True
                  and cleanup.get("browser_closed") is True
                  and cleanup.get("temporary_root_removed") is True
                  and not cleanup["remaining_descendants"]
                  and not cleanup["errors"],
                  cleanup=cleanup)
            final["status"] = "passed" if all(item["passed"] for item in checks) else "failed"
        write_report(final["status"], cleanup)
    return 0 if final["status"] == "passed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.artifacts)))
