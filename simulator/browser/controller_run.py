"""Durable controller acceptance for F3 (pause), F4 (live identity) and the
tabbed console shell.

    .venv/bin/python -m simulator.browser.controller_run --artifacts /tmp/...

Starts a disposable real server on a free port with temporary storage, two
calibrated Chromium clients and a 20 s video plus a still. It then drives the
physical controller UI rather than only reading ``data-state``:

* The console opens on Show with four tabs and exactly one visible panel. Arrow
  keys move the roving tabindex without dirtying a draft or writing a layout,
  a reload restores the last manual tab, and 390x844 keeps all task tabs reachable while
  keeping Show selected initially. The topbar transport mirrors the rail and starts
  playback; the legacy index.html link lives only in System.
* Pause must render ``Paused`` with the live item name, the paused countdown must
  not age, the status poll must stay healthy, Resume must advance the clients
  and Stop must restore the persisted scene.
* Remaining time lives in ``#playback-countdown`` only. ``#playback-status`` is
  not a live region, its playing text is stable, and a state change announces
  once on ``#page-status``.
* Active readiness sorts by display number, says ``preparing next``, and the
  cohort summary is one line. A session with no exclusions hides the exclusion
  controls; one exclusion shows them.
* Selecting a tablet shows the local Apply/Cancel footer, a nudge enables both
  copies of Apply, and local Cancel clears the draft without writing.
* While the frozen video session keeps playing, a different playlist is edited,
  reordered and saved from the controller. A reload must keep the live name,
  kind, duration and dwell from the frozen session, show the new still in the
  editable rows and hide the editable ``Now`` marker because the revisions
  differ. The same save is repeated while paused and while a real recovery is
  in progress.
* A new Start after Stop must use the newly saved still.
* 390x844 must have no horizontal overflow, a compact paused playback card, a
  visible More control and a stage that fits without horizontal scrolling.
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
    "S5": "390x844 pause summary is readable with a compact card and fitted stage",
    "S6": "a saved draft during playback keeps the frozen live identity",
    "S7": "a saved draft while paused keeps the live name and the frozen dwell",
    "S8": "a saved draft during recovery keeps the frozen live identity",
    "S9": "Stop restores the persisted scene",
    "S10": "a new Start uses the newly saved still",
    "S11": "no unexpected page errors, console errors or failed requests",
    "S12": "local Apply/Cancel mirror the draft without writing a layout",
    "S13": "one session exclusion shows the cohort and hides the excluded tablet",
    "S14": "the tabbed console switches, persists and keeps its drafts",
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

        async def countdown() -> str:
            return await controller.locator("#playback-countdown").inner_text()

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
            await open_tab("content")
            await controller.select_option("#playlist-library", asset_id)
            await controller.wait_for_function(
                "() => !document.querySelector('#btn-playlist-add').disabled", timeout=5000)
            await controller.click("#btn-playlist-add")

        async def move_up(index: int) -> None:
            await open_tab("content")
            await controller.click(
                f'.playlist-item[data-index="{index}"] [data-action="up"]')

        async def remove_row(index: int) -> None:
            await open_tab("content")
            await controller.click(
                f'.playlist-item[data-index="{index}"] [data-action="remove"]')

        async def save_playlist(expected_revision: int) -> None:
            await open_tab("content")
            await controller.click("#btn-playlist-save")
            await wait_until(
                lambda: saved_playlist().get("revision") == expected_revision, 10,
                f"the saved playlist never advanced to revision {expected_revision}")
            await controller.wait_for_function(
                "() => (document.querySelector('#playlist-msg')?.textContent || '')"
                ".startsWith('Playlist saved')", timeout=10000)

        async def reload_controller(tab: str = "show") -> None:
            await controller.reload(wait_until="networkidle")
            await open_tab(tab)
            await controller.evaluate("document.querySelector('#playback-details').open = true")
            await controller.wait_for_function(
                "() => !document.querySelector('#btn-playback-start').disabled"
                " || !document.querySelector('#btn-playback-stop').hidden",
                timeout=15000)
            await controller.wait_for_function(
                "() => (document.querySelector('#playlist-hint')?.textContent || '')"
                " === 'Saved on the server.'", timeout=15000)

        async def shell_state() -> dict[str, Any]:
            return await controller.evaluate("""() => {
                const tabs = [...document.querySelectorAll('#rail-tabs [role="tab"]')];
                const panels = [...document.querySelectorAll(
                    '#rail-panels [role="tabpanel"]')];
                const transport = document.querySelector('#topbar-transport');
                const legacy = document.querySelector(
                    '#panel-system a[href="index.html"]');
                return {
                    tabs: tabs.map(node => ({
                        id: node.id,
                        selected: node.getAttribute('aria-selected'),
                        tabindex: node.getAttribute('tabindex'),
                        controls: node.getAttribute('aria-controls'),
                    })),
                    panels: panels.map(node => ({
                        id: node.id,
                        hidden: node.hidden,
                        visible: !node.hidden && node.getClientRects().length > 0,
                        labelledby: node.getAttribute('aria-labelledby'),
                    })),
                    selected: (tabs.find(
                        node => node.getAttribute('aria-selected') === 'true')
                        || {}).id || null,
                    visiblePanels: panels.filter(
                        node => !node.hidden && node.getClientRects().length > 0)
                        .map(node => node.id),
                    focused: document.activeElement ? document.activeElement.id : null,
                    stored: (() => {
                        try {
                            return window.sessionStorage.getItem(
                                'tablet-wall-console-tab-v1');
                        } catch (error) {
                            return null;
                        }
                    })(),
                    stageVisible: (() => {
                        const stage = document.querySelector('#stage-svg');
                        return !!stage && stage.getClientRects().length > 0
                            && stage.getBoundingClientRect().width > 0;
                    })(),
                    topbarIndexLinks: document.querySelectorAll(
                        '.topbar a[href="index.html"]').length,
                    topbarTransportVisible: !!transport
                        && transport.getClientRects().length > 0,
                    legacyLink: legacy ? legacy.textContent.trim() : null,
                };
            }""")

        def valid_tab_shell(snapshot: dict[str, Any], expected: str) -> bool:
            panels = {panel["id"]: panel for panel in snapshot["panels"]}
            selected = [tab["id"] for tab in snapshot["tabs"]
                        if tab["selected"] == "true"]
            return (
                snapshot["selected"] == f"tab-{expected}"
                and selected == [f"tab-{expected}"]
                and snapshot["visiblePanels"] == [f"panel-{expected}"]
                and all(tab["controls"] in panels for tab in snapshot["tabs"])
                and all(panels[tab["controls"]]["labelledby"] == tab["id"]
                        for tab in snapshot["tabs"])
                and all(panels[tab["controls"]]["visible"]
                        == (tab["selected"] == "true")
                        for tab in snapshot["tabs"])
                and [tab["tabindex"] for tab in snapshot["tabs"]
                     if tab["selected"] == "true"] == ["0"]
                and all(tab["tabindex"] == "-1" for tab in snapshot["tabs"]
                        if tab["selected"] != "true"))

        async def open_tab(name: str) -> None:
            await controller.click(f"#tab-{name}")
            await controller.wait_for_function("""(name) => {
                const tab = document.querySelector('#tab-' + name);
                const panel = document.querySelector('#panel-' + name);
                const visible = [...document.querySelectorAll(
                    '#rail-panels [role="tabpanel"]')].filter(
                    node => !node.hidden && node.getClientRects().length > 0);
                return !!tab && !!panel
                    && tab.getAttribute('aria-selected') === 'true'
                    && tab.getAttribute('tabindex') === '0'
                    && !panel.hidden && panel.getClientRects().length > 0
                    && visible.length === 1 && visible[0] === panel;
            }""", arg=name, timeout=5000)

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

        initial_shell = await shell_state()
        check("S1", "the tabbed console opens on Show with four tabs, one panel and the stage",
              valid_tab_shell(initial_shell, "show")
              and [tab["id"] for tab in initial_shell["tabs"]]
              == ["tab-show", "tab-tablet", "tab-content", "tab-system"]
              and [panel["id"] for panel in initial_shell["panels"]]
              == ["panel-show", "panel-tablet", "panel-content", "panel-system"]
              and initial_shell["stageVisible"]
              and initial_shell["stored"] is None,
              tabs=[tab["id"] for tab in initial_shell["tabs"]],
              panels=initial_shell["visiblePanels"],
              stage=initial_shell["stageVisible"], stored=initial_shell["stored"])

        phase["id"] = "S14"
        check("S14", "the topbar has no legacy link and the System panel holds the legacy view",
              initial_shell["topbarIndexLinks"] == 0
              and initial_shell["legacyLink"] == "Logical wall (legacy)",
              topbar_links=initial_shell["topbarIndexLinks"],
              legacy=initial_shell["legacyLink"])
        draft_before = await controller.evaluate("""() => ({
            tabletDot: !document.querySelector('#tab-tablet-dot').hidden,
            contentDot: !document.querySelector('#tab-content-dot').hidden,
            playlistHint: document.querySelector('#playlist-hint').textContent,
        })""")
        layout_before_switch = http.get("/api/v3/config").json().get("revision")
        await open_tab("show")
        transitions = (
            ("ArrowRight", "tablet",
             "ArrowRight moves Show to Tablet with a roving tabindex"),
            ("ArrowRight", "content",
             "ArrowRight moves Tablet to Content with a roving tabindex"),
            ("ArrowLeft", "tablet",
             "ArrowLeft moves Content back to Tablet with a roving tabindex"),
            ("Home", "show", "Home selects Show with a roving tabindex"),
            ("End", "system", "End selects System with a roving tabindex"),
            ("ArrowRight", "show",
             "ArrowRight wraps System back to Show with a roving tabindex"),
        )
        tab_transitions = []
        current = "show"
        for key, expected, name in transitions:
            await controller.locator(f"#tab-{current}").focus()
            await controller.keyboard.press(key)
            snapshot = await shell_state()
            tab_transitions.append({
                "key": key, "expected": expected, "selected": snapshot["selected"],
                "visible": snapshot["visiblePanels"], "focused": snapshot["focused"],
                "tabindex": {tab["id"]: tab["tabindex"] for tab in snapshot["tabs"]},
            })
            check("S14", name,
                  valid_tab_shell(snapshot, expected)
                  and snapshot["focused"] == f"tab-{expected}",
                  selected=snapshot["selected"], visible=snapshot["visiblePanels"],
                  focused=snapshot["focused"])
            current = expected
        report["tab_transitions"] = tab_transitions
        draft_after = await controller.evaluate("""() => ({
            tabletDot: !document.querySelector('#tab-tablet-dot').hidden,
            contentDot: !document.querySelector('#tab-content-dot').hidden,
            playlistHint: document.querySelector('#playlist-hint').textContent,
        })""")
        layout_after_switch = http.get("/api/v3/config").json().get("revision")
        check("S14", "switching tabs neither dirties a draft nor writes the layout",
              draft_after == draft_before
              and layout_after_switch == layout_before_switch,
              draft_before=draft_before, draft_after=draft_after,
              layout_before=layout_before_switch, layout_after=layout_after_switch)
        await open_tab("system")
        await controller.screenshot(
            path=str(artifacts / "tabs-system-desktop.png"), full_page=True)
        await controller.locator("#panel-system .legacy-card").screenshot(
            path=str(artifacts / "system-legacy-desktop.png"))
        await open_tab("content")
        content_shell = await shell_state()
        check("S14", "the topbar transport stays visible outside the Show panel",
              content_shell["topbarTransportVisible"]
              and content_shell["selected"] == "tab-content"
              and content_shell["stored"] == "content",
              visible=content_shell["topbarTransportVisible"],
              selected=content_shell["selected"], stored=content_shell["stored"])
        await controller.screenshot(
            path=str(artifacts / "tabs-content-desktop.png"), full_page=True)
        await controller.reload(wait_until="networkidle")
        await controller.wait_for_function(
            "() => document.querySelector('#tab-content')?.getAttribute('aria-selected')"
            " === 'true' && !document.querySelector('#panel-content')?.hidden",
            timeout=15000)
        restored_shell = await shell_state()
        check("S14", "a reload restores the last manually chosen tab",
              valid_tab_shell(restored_shell, "content")
              and restored_shell["stored"] == "content",
              selected=restored_shell["selected"],
              visible=restored_shell["visiblePanels"],
              stored=restored_shell["stored"])
        report["tab_shell"] = {"initial": initial_shell, "restored": restored_shell}

        phase["id"] = "S1"
        await open_tab("show")
        await open_details()
        await controller.wait_for_function(
            "() => !document.querySelector('#btn-topbar-start').disabled", timeout=15000)
        await controller.click("#btn-topbar-start")
        await wait_until(lambda: status().get("state") in ("playing", "preparing"), 15,
                         "the Start never began a session")
        await wait_until(lambda: status().get("state") == "playing", 25,
                         "the session never reached playing")
        await wait_until(clients_advancing, 25, "the clients never advanced the video")
        report["session"] = status()
        check("S1", "Start from the controller begins a playing session on both clients", True)
        await controller.wait_for_function(
            "() => document.querySelector('#topbar-playback-state')?.dataset.state"
            " === 'playing'", timeout=15000)
        transport = await controller.evaluate("""() => {
            const pairs = ['start', 'pause', 'stop'].map(name => {
                const rail = document.querySelector('#btn-playback-' + name);
                const top = document.querySelector('#btn-topbar-' + name);
                return {
                    name: name,
                    railHidden: rail.hidden, topHidden: top.hidden,
                    railDisabled: rail.disabled, topDisabled: top.disabled,
                    railText: rail.textContent.trim(), topText: top.textContent.trim(),
                };
            });
            const word = document.querySelector('#playback-state-word');
            const topbar = document.querySelector('#topbar-playback-state');
            return {
                railState: word.textContent.trim(), railData: word.dataset.state,
                topbarState: topbar.textContent.trim(), topbarData: topbar.dataset.state,
                pairs: pairs,
            };
        }""")
        report["topbar_transport"] = transport
        check("S1", "the topbar transport mirrors the rail state and its Start began playback",
              status().get("state") == "playing"
              and transport["railState"] == transport["topbarState"] == "playing"
              and transport["railData"] == transport["topbarData"] == "playing"
              and all(pair["railHidden"] == pair["topHidden"]
                      and pair["railDisabled"] == pair["topDisabled"]
                      and pair["railText"] == pair["topText"]
                      for pair in transport["pairs"])
              and transport["pairs"][0]["topHidden"]
              and not transport["pairs"][1]["topHidden"]
              and not transport["pairs"][2]["topHidden"]
              and transport["pairs"][1]["topText"] == "Pause",
              rail=transport["railState"], topbar=transport["topbarState"],
              buttons=transport["pairs"])

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
        playing_countdown = await countdown()
        playing_facts = await facts()
        live_region = await controller.evaluate("""() => {
            const status = document.querySelector('#playback-status');
            const countdown = document.querySelector('#playback-countdown');
            return {
                role: status.getAttribute('role'),
                ariaLive: status.getAttribute('aria-live'),
                countdownAriaHidden: countdown.getAttribute('aria-hidden'),
            };
        }""")
        report["controller_playing"] = {
            "summary": playing_summary, "countdown": playing_countdown,
            "facts": playing_facts, "live_region": live_region,
        }
        check("S2", "the controller summary names the playing video without its remaining time",
              playing_summary.startswith("Playing:") and "f3-session.mp4" in playing_summary
              and DWELL_RE.search(playing_summary) is None,
              summary=playing_summary)
        check("S2", "the countdown carries the playing remaining time and is hidden from assistive tech",
              DWELL_RE.search(playing_countdown) is not None
              and live_region["countdownAriaHidden"] == "true",
              countdown=playing_countdown, aria_hidden=live_region["countdownAriaHidden"])
        check("S2", "the playback summary is not a live region",
              live_region["role"] is None and live_region["ariaLive"] is None,
              role=live_region["role"], aria_live=live_region["ariaLive"])
        check("S2", "the controller facts show the frozen 20 s video kind and duration",
              "Current media" in playing_facts and "video \u00b7 20 s clip" in playing_facts,
              facts=playing_facts)

        stable_summary = await summary()
        stable_countdown = await countdown()
        await asyncio.sleep(3.1)
        later_summary = await summary()
        later_countdown = await countdown()
        report["playing_stability"] = {
            "summary_before": stable_summary, "summary_after": later_summary,
            "countdown_before": stable_countdown, "countdown_after": later_countdown,
            "state": status().get("state"),
        }
        check("S2", "the playing summary stays stable for three seconds while the countdown advances",
              report["playing_stability"]["state"] == "playing"
              and stable_summary == later_summary
              and DWELL_RE.search(stable_countdown) is not None
              and later_countdown != stable_countdown,
              summary_before=stable_summary, summary_after=later_summary,
              countdown_before=stable_countdown, countdown_after=later_countdown)

        await controller.wait_for_function(
            "() => document.querySelectorAll('.playback-member').length === 2", timeout=10000)
        readiness = await controller.evaluate("""() => ({
            names: [...document.querySelectorAll('.playback-member-name')]
                .map(node => node.textContent),
            chips: [...document.querySelectorAll('.playback-member .chip')]
                .map(node => node.textContent),
            waiting: document.querySelectorAll(
                '.playback-member[data-state="waiting"]').length,
        })""")
        report["readiness"] = readiness
        check("S2", "active readiness rows are ordered by display number and say preparing next",
              len(readiness["names"]) == 2
              and readiness["names"][0].startswith("#1")
              and readiness["names"][1].startswith("#2")
              and readiness["waiting"] >= 1
              and "preparing next" in readiness["chips"]
              and "waiting" not in readiness["chips"],
              names=readiness["names"], chips=readiness["chips"],
              waiting=readiness["waiting"])

        cohort = await controller.evaluate("""() => {
            const line = document.querySelector('#playback-cohort-line');
            const style = getComputedStyle(line);
            const rect = line.getBoundingClientRect();
            return {
                hidden: line.hidden, text: line.textContent,
                whiteSpace: style.whiteSpace, height: rect.height,
                fontSize: parseFloat(style.fontSize),
                exclusionsHidden: document.querySelector('#playback-exclusions').hidden,
            };
        }""")
        report["cohort_line"] = cohort
        check("S2", "zero exclusions keep the cohort summary one line and hide the exclusion controls",
              not cohort["hidden"]
              and "2 required" in cohort["text"]
              and "0 excluded" in cohort["text"]
              and "2 in this show" in cohort["text"]
              and cohort["whiteSpace"] == "nowrap"
              and cohort["height"] <= cohort["fontSize"] * 2
              and cohort["exclusionsHidden"] is True,
              text=cohort["text"], white_space=cohort["whiteSpace"],
              height=cohort["height"], font=cohort["fontSize"],
              exclusions_hidden=cohort["exclusionsHidden"])
        await controller.screenshot(path=str(artifacts / "controller-playing.png"), full_page=True)

        phase["id"] = "S3"
        await open_tab("show")
        await video_window()
        mark = len(events)
        # Start the pause just after a completed poll, so an in-flight status
        # read cannot add a second announcement to the transition.
        poll_before_pause = await poll_note()
        await controller.wait_for_function(
            "(before) => (document.querySelector('#playback-poll-note')?.textContent || '')"
            " !== before", arg=poll_before_pause, timeout=3000)
        await controller.evaluate("""() => {
            window.__pageStatusChanges = [];
            const node = document.querySelector('#page-status');
            new MutationObserver(() => {
                window.__pageStatusChanges.push(node.textContent);
            }).observe(node, {childList: true, characterData: true, subtree: true});
        }""")
        await controller.click("#btn-playback-pause")
        await wait_until(lambda: status().get("state") == "paused", 10, "pause did not stick")
        await wait_summary("Paused on")
        await asyncio.sleep(.4)
        paused_one = await summary()
        paused_countdown_one = await countdown()
        paused_facts_one = await facts()
        poll_one = await poll_note()
        paused_status = status()
        page_status_changes = await controller.evaluate("() => window.__pageStatusChanges")
        report["pause"] = {
            "status": paused_status, "summary": paused_one,
            "countdown": paused_countdown_one, "facts": paused_facts_one,
            "poll": poll_one, "page_status_changes": page_status_changes,
        }
        paused_dwell_before = DWELL_RE.search(paused_countdown_one)
        check("S3", "the pause summary says Paused with the live video name",
              paused_one.startswith("Paused on") and "f3-session.mp4" in paused_one,
              summary=paused_one)
        check("S3", "the paused countdown carries the remaining time and the summary does not",
              paused_dwell_before is not None
              and DWELL_RE.search(paused_one) is None,
              summary=paused_one, countdown=paused_countdown_one)
        check("S3", "the paused transition announces once on the page status",
              page_status_changes == ["Playback paused."],
              changes=page_status_changes)
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
            const card = document.querySelector('#playback-card');
            const more = document.querySelector('#btn-playback-more');
            const extra = document.querySelector('#playback-extra');
            const stage = document.querySelector('#stage-scroll');
            const svg = document.querySelector('#stage-svg');
            const tabs = [...document.querySelectorAll('#rail-tabs [role="tab"]')];
            const panels = [...document.querySelectorAll(
                '#rail-panels [role="tabpanel"]')];
            const railTabs = document.querySelector('#rail-tabs');
            return {
                innerWidth: window.innerWidth,
                documentScrollWidth: document.documentElement.scrollWidth,
                documentClientWidth: document.documentElement.clientWidth,
                summary: summary.textContent,
                summaryLeft: rect.left, summaryRight: rect.right, summaryWidth: rect.width,
                summaryOverflow: summary.scrollWidth - summary.clientWidth,
                fontSize: parseFloat(style.fontSize),
                countdown: document.querySelector('#playback-countdown').textContent,
                pauseText: pause.textContent,
                pauseVisible: !!pause.getClientRects().length,
                cardHeight: card.getBoundingClientRect().height,
                moreVisible: !!more.getClientRects().length,
                moreExpanded: String(more.parentElement.open),
                extraVisible: !!extra.getClientRects().length,
                stageTabIndex: stage.getAttribute('tabindex'),
                stageRole: stage.getAttribute('role'),
                stageScrollWidth: stage.scrollWidth,
                stageClientWidth: stage.clientWidth,
                svgWidth: svg.getBoundingClientRect().width,
                railTabsDisplay: getComputedStyle(railTabs).display,
                railTabsVisible: !!railTabs.getClientRects().length,
                tabs: tabs.map(node => ({
                    id: node.id,
                    selected: node.getAttribute('aria-selected'),
                    tabindex: node.getAttribute('tabindex'),
                    controls: node.getAttribute('aria-controls'),
                })),
                panels: panels.map(node => ({
                    id: node.id, hidden: node.hidden,
                    visible: !node.hidden && node.getClientRects().length > 0,
                })),
                selectedTab: (tabs.find(
                    node => node.getAttribute('aria-selected') === 'true')
                    || {}).id || null,
                visiblePanels: panels.filter(
                    node => !node.hidden && node.getClientRects().length > 0)
                    .map(node => node.id),
            };
        }""")
        report["mobile"] = mobile_state
        check("S5", "the 390x844 controller has no horizontal page overflow",
              mobile_state["documentScrollWidth"] - mobile_state["documentClientWidth"] <= 1,
              width=mobile_state["documentScrollWidth"],
              viewport=mobile_state["documentClientWidth"])
        mobile_panels = {panel["id"]: panel for panel in mobile_state["panels"]}
        mobile_tabs_consistent = (
            mobile_state["selectedTab"] == "tab-show"
            and mobile_state["visiblePanels"] == ["panel-show"]
            and all(mobile_panels[tab["controls"]]["visible"]
                    == (tab["selected"] == "true")
                    for tab in mobile_state["tabs"]))
        check("S5", "390x844 exposes the tab strip and keeps Show as the initial panel",
              mobile_state["railTabsDisplay"] != "none"
              and mobile_state["railTabsVisible"]
              and mobile_tabs_consistent
              and [tab["tabindex"] for tab in mobile_state["tabs"]
                   if tab["selected"] == "true"] == ["0"]
              and all(tab["tabindex"] == "-1" for tab in mobile_state["tabs"]
                      if tab["selected"] != "true"),
              display=mobile_state["railTabsDisplay"],
              tabs_visible=mobile_state["railTabsVisible"],
              selected=mobile_state["selectedTab"],
              panels=mobile_state["visiblePanels"])
        check("S5", "the mobile paused summary fits, stays readable and names the video",
              mobile_state["summaryLeft"] >= 0
              and mobile_state["summaryRight"] <= mobile_state["innerWidth"] + 1
              and mobile_state["summaryOverflow"] <= 1
              and mobile_state["fontSize"] >= 12
              and "Paused on" in mobile_state["summary"]
              and "f3-session.mp4" in mobile_state["summary"]
              and DWELL_RE.search(mobile_state["summary"]) is None,
              summary=mobile_state["summary"], font=mobile_state["fontSize"],
              right=mobile_state["summaryRight"], overflow=mobile_state["summaryOverflow"])
        check("S5", "the mobile paused countdown carries the remaining time",
              DWELL_RE.search(mobile_state["countdown"]) is not None,
              countdown=mobile_state["countdown"])
        check("S5", "the mobile collapsed playback card is compact with More and a hidden extra block",
              mobile_state["cardHeight"] <= 200
              and mobile_state["moreVisible"]
              and mobile_state["moreExpanded"] == "false"
              and not mobile_state["extraVisible"],
              height=mobile_state["cardHeight"], more=mobile_state["moreVisible"],
              expanded=mobile_state["moreExpanded"], extra=mobile_state["extraVisible"])
        check("S5", "the mobile stage is a fitted, focusable region",
              mobile_state["stageTabIndex"] == "0"
              and mobile_state["stageRole"] == "region"
              and mobile_state["stageScrollWidth"] <= mobile_state["stageClientWidth"] + 1
              and mobile_state["svgWidth"] <= mobile_state["stageClientWidth"] + 1,
              tabindex=mobile_state["stageTabIndex"], role=mobile_state["stageRole"],
              scroll_width=mobile_state["stageScrollWidth"],
              client_width=mobile_state["stageClientWidth"],
              svg_width=mobile_state["svgWidth"])
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
        paused_countdown_two = await countdown()
        paused_facts_two = await facts()
        poll_two = await poll_note()
        page_status_changes_after = await controller.evaluate("() => window.__pageStatusChanges")
        report["pause"]["summary_after_2s"] = paused_two
        report["pause"]["countdown_after_2s"] = paused_countdown_two
        report["pause"]["facts_after_2s"] = paused_facts_two
        report["pause"]["poll_after_2s"] = poll_two
        report["pause"]["page_status_changes_after_2s"] = page_status_changes_after
        check("S3", "the pause summary is identical after 2.4 s",
              paused_one == paused_two, before=paused_one, after=paused_two)
        paused_dwell_after = DWELL_RE.search(paused_countdown_two)
        check("S3", "the paused countdown is identical after 2.4 s",
              paused_countdown_one == paused_countdown_two,
              before=paused_countdown_one, after=paused_countdown_two)
        check("S3", "the paused countdown does not age",
              paused_dwell_before is not None and paused_dwell_after is not None
              and paused_dwell_before.group(0) == paused_dwell_after.group(0),
              before=paused_countdown_one, after=paused_countdown_two)
        check("S3", "the paused transition did not announce again during the wait",
              page_status_changes_after == ["Playback paused."],
              changes=page_status_changes_after)
        facts_dwell_one = [line for line in paused_facts_one.splitlines()
                           if DWELL_RE.search(line)]
        facts_dwell_two = [line for line in paused_facts_two.splitlines()
                           if DWELL_RE.search(line)]
        check("S3", "the paused facts dwell is identical after 2.4 s",
              facts_dwell_one == facts_dwell_two and facts_dwell_one != [],
              before=facts_dwell_one, after=facts_dwell_two)
        check("S3", "the poll stays healthy while paused", await poll_is_healthy(), poll=poll_two)

        phase["id"] = "S4"
        await open_tab("show")
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
        await controller.wait_for_function(
            "() => document.querySelector('#tab-content-dot').hidden === false", timeout=5000)
        content_dot_dirty = await controller.locator("#tab-content-dot").is_visible()
        await move_up(2)
        await move_up(1)
        await remove_row(1)
        await remove_row(1)
        await wait_rows(1)
        preview_rows = await rows()
        check("S6", "the draft can be edited and reordered down to the new green still",
              preview_rows == ["controller-green.png"], rows=preview_rows)
        await save_playlist(2)
        await controller.wait_for_function(
            "() => document.querySelector('#tab-content-dot').hidden === true", timeout=5000)
        content_dot_after = await controller.locator("#tab-content-dot").is_visible()
        saved_two = saved_playlist()
        check("S6", "the saved playlist advanced to revision 2 with only the new still",
              saved_two.get("revision") == 2
              and [item["asset"] for item in saved_two["items"]] == [assets["green"]],
              saved=saved_two)
        check("S6", "the Content tab marks an unsaved playlist and clears after save",
              content_dot_dirty and not content_dot_after,
              dirty=content_dot_dirty, clean=not content_dot_after)
        content_layout = await controller.evaluate("""() => {
            const item = document.querySelector('.playlist-item');
            const body = item && item.querySelector('.playlist-item-body');
            const picker = document.querySelector('#playlist-library');
            const controls = item && item.querySelector('.playlist-controls');
            const width = (node) => node ? node.getBoundingClientRect().width : 0;
            return {
                itemWidth: width(item), bodyWidth: width(body),
                pickerWidth: width(picker),
                controlsHeight: controls ? controls.getBoundingClientRect().height : 0,
            };
        }""")
        report["content_layout"] = content_layout
        check("S6", "the playlist rows and library picker fit the 392 px rail",
              content_layout["bodyWidth"] >= 200
              and content_layout["pickerWidth"] >= 300
              and content_layout["controlsHeight"] <= 46,
              **content_layout)
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
        live_countdown = await countdown()
        live_facts = await facts()
        live_rows = await rows()
        markers = await now_markers()
        live_status = status()
        report["playing_draft"] = {
            "summary": live_summary, "countdown": live_countdown, "facts": live_facts,
            "rows": live_rows, "markers": markers, "status": live_status, "saved": saved_two,
        }
        check("S6", "the reloaded summary still names the frozen video, not the new still",
              live_summary.startswith("Playing:")
              and "f3-session.mp4" in live_summary
              and "controller-green.png" not in live_summary
              and DWELL_RE.search(live_summary) is None,
              summary=live_summary)
        check("S6", "the reloaded countdown keeps the frozen video's remaining dwell",
              DWELL_RE.search(live_countdown) is not None,
              countdown=live_countdown)
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
        await open_tab("show")
        await video_window(max_elapsed_ms=10000)
        await controller.click("#btn-playback-pause")
        await wait_until(lambda: status().get("state") == "paused", 10,
                         "the second pause did not stick")
        await wait_summary("Paused on")
        await open_details()
        await asyncio.sleep(.4)
        paused_before_save = await summary()
        paused_countdown_before_save = await countdown()
        paused_facts_before_save = await facts()
        check("S7", "the second pause again names the frozen video with a paused countdown",
              paused_before_save.startswith("Paused on")
              and "f3-session.mp4" in paused_before_save
              and DWELL_RE.search(paused_before_save) is None
              and DWELL_RE.search(paused_countdown_before_save) is not None,
              summary=paused_before_save, countdown=paused_countdown_before_save)
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
        paused_countdown_after_save = await countdown()
        paused_facts_after_save = await facts()
        paused_rows_after = await rows()
        paused_markers = await now_markers()
        paused_status_after = status()
        report["paused_draft"] = {
            "summary_before": paused_before_save, "summary_after": paused_after_save,
            "countdown_before": paused_countdown_before_save,
            "countdown_after": paused_countdown_after_save,
            "facts_before": paused_facts_before_save, "facts_after": paused_facts_after_save,
            "rows": paused_rows_after, "markers": paused_markers,
            "saved": saved_three, "status": paused_status_after,
        }
        check("S7", "the paused summary is unchanged by saving another playlist",
              paused_after_save == paused_before_save,
              before=paused_before_save, after=paused_after_save)
        check("S7", "the paused countdown is unchanged by saving another playlist",
              paused_countdown_after_save == paused_countdown_before_save,
              before=paused_countdown_before_save, after=paused_countdown_after_save)
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
        await open_tab("show")
        await controller.click("#btn-playback-pause")
        await wait_until(lambda: status().get("state") == "playing", 25,
                         "the second Resume never reached playing")
        await wait_summary("Playing")
        await wait_until(clients_advancing, 20, "the clients did not advance after the second Resume")
        phase["id"] = "S8"

        await video_window(max_elapsed_ms=10000)
        # Keep the second member's recovery preparation from becoming ready
        # so the recovery stays observable while the save is performed. The
        # prototype is restored before the cohort is allowed to resume.
        await pages[1][0].evaluate("""() => {
            window.__reviewPlay = HTMLMediaElement.prototype.play;
            HTMLMediaElement.prototype.play = function () {
                return new Promise(function () {});
            };
        }""")
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
        await pages[1][0].evaluate("""() => {
            if (window.__reviewPlay) HTMLMediaElement.prototype.play = window.__reviewPlay;
            delete window.__reviewPlay;
        }""")
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
        await open_tab("show")
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
        await open_tab("show")
        await controller.wait_for_function(
            "() => !document.querySelector('#btn-playback-start').disabled", timeout=10000)
        await controller.click("#btn-playback-start")
        await wait_until(lambda: status().get("state") == "playing", 25,
                         "the new Start never played")
        await wait_until(lambda: clients_show_still(CUT_COLOURS["green"]), 20,
                         "the clients never showed the newly saved green still")
        # The controller polls once a second; wait for it to render the new
        # playing session and mark the live row before reading the marker.
        await wait_summary("Playing:", 10)

        async def marked_now() -> bool:
            return await now_markers() == 1

        await wait_until(marked_now, 10, "the live row was never marked Now")
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
        await wait_until(lambda: status().get("state") == "stopped", 10,
                         "the final Stop did not stick")
        await controller.wait_for_function(
            "() => (document.querySelector('#playback-status')?.textContent || '')"
            " === 'Playback is stopped.'", timeout=15000)

        phase["id"] = "S12"
        layout_document = http.get("/api/v3/config").json()
        layout_revision_before = layout_document.get("revision")
        selected_id = pages[0][1].device_id
        await controller.wait_for_selector(
            f'#stage-svg .slot[data-device-id="{selected_id}"]', timeout=10000)
        await controller.click(f'#stage-svg .slot[data-device-id="{selected_id}"]')
        await controller.wait_for_function(
            "() => !document.querySelector('#inspector-body').hidden"
            " && document.querySelector('#selected-title').textContent !== '–'",
            timeout=10000)
        tablet_shell = await shell_state()
        check("S12", "selecting a stage slot opens the Tablet panel",
              valid_tab_shell(tablet_shell, "tablet"),
              selected=tablet_shell["selected"], visible=tablet_shell["visiblePanels"])
        await open_tab("tablet")
        local_before = await controller.evaluate("""() => ({
            localVisible: !!document.querySelector('#btn-apply-local').getClientRects().length,
            localCancelVisible: !!document.querySelector('#btn-cancel-local').getClientRects().length,
            localDisabled: document.querySelector('#btn-apply-local').disabled,
            localCancelDisabled: document.querySelector('#btn-cancel-local').disabled,
            globalDisabled: document.querySelector('#btn-apply').disabled,
            globalCancelDisabled: document.querySelector('#btn-cancel').disabled,
            selected: document.querySelector('#selected-title').textContent,
        })""")
        check("S12", "selecting a tablet shows the local Apply and Cancel controls",
              local_before["localVisible"] and local_before["localCancelVisible"]
              and local_before["selected"] != "–",
              selected=local_before["selected"])
        check("S12", "the local controls mirror the disabled global draft controls",
              local_before["localDisabled"] is True
              and local_before["globalDisabled"] is True
              and local_before["localCancelDisabled"] is True
              and local_before["globalCancelDisabled"] is True,
              local=local_before["localDisabled"],
              global_disabled=local_before["globalDisabled"])

        await controller.click("#btn-nudge-x-plus")
        await controller.wait_for_function(
            "() => !document.querySelector('#btn-apply-local').disabled"
            " && !document.querySelector('#btn-apply').disabled", timeout=5000)
        await controller.wait_for_function(
            "() => document.querySelector('#tab-tablet-dot').hidden === false", timeout=5000)
        tablet_dot_dirty = await controller.locator("#tab-tablet-dot").is_visible()
        nudged = await controller.evaluate("""() => ({
            localDisabled: document.querySelector('#btn-apply-local').disabled,
            globalDisabled: document.querySelector('#btn-apply').disabled,
            localCancelDisabled: document.querySelector('#btn-cancel-local').disabled,
            globalCancelDisabled: document.querySelector('#btn-cancel').disabled,
            nudgeX: document.querySelector('#slot-nudge-x').value,
        })""")
        check("S12", "a nudge enables both Apply controls and both Cancel controls",
              nudged["localDisabled"] is False and nudged["globalDisabled"] is False
              and nudged["localCancelDisabled"] is False
              and nudged["globalCancelDisabled"] is False
              and nudged["nudgeX"] == "1",
              local=nudged["localDisabled"], global_disabled=nudged["globalDisabled"],
              nudge_x=nudged["nudgeX"])

        await controller.click("#btn-cancel-local")
        await controller.wait_for_function(
            "() => document.querySelector('#btn-apply-local').disabled"
            " && document.querySelector('#btn-apply').disabled", timeout=5000)
        await controller.wait_for_function(
            "() => document.querySelector('#tab-tablet-dot').hidden === true", timeout=5000)
        tablet_dot_after = await controller.locator("#tab-tablet-dot").is_visible()
        cancelled = await controller.evaluate("""() => ({
            localDisabled: document.querySelector('#btn-apply-local').disabled,
            globalDisabled: document.querySelector('#btn-apply').disabled,
            nudgeX: document.querySelector('#slot-nudge-x').value,
        })""")
        layout_revision_after = http.get("/api/v3/config").json().get("revision")
        report["local_apply"] = {
            "before": local_before, "nudged": nudged, "cancelled": cancelled,
            "layout_revision_before": layout_revision_before,
            "layout_revision_after": layout_revision_after,
        }
        check("S12", "local Cancel clears the draft and disables both Apply controls",
              cancelled["localDisabled"] is True and cancelled["globalDisabled"] is True
              and cancelled["nudgeX"] == "0",
              nudge_x=cancelled["nudgeX"])
        check("S12", "local Cancel and the nudge did not write the layout",
              layout_revision_after == layout_revision_before,
              before=layout_revision_before, after=layout_revision_after)
        check("S12", "the Tablet tab marks the layout draft and clears after local Cancel",
              tablet_dot_dirty and not tablet_dot_after,
              dirty=tablet_dot_dirty, clean=not tablet_dot_after)
        await controller.screenshot(
            path=str(artifacts / "local-apply-cancel-desktop.png"), full_page=True)

        phase["id"] = "S13"
        await open_tab("show")
        excluded_id = pages[1][1].device_id
        await controller.wait_for_function(
            "() => !document.querySelector('#playback-exclusions').hidden"
            " && !!document.querySelector('#playback-exclusion-list input')",
            timeout=10000)
        show_shell = await shell_state()
        check("S13", "the exclusion controls sit in the visible Show panel",
              valid_tab_shell(show_shell, "show")
              and await controller.locator("#playback-exclusions").is_visible(),
              selected=show_shell["selected"], visible=show_shell["visiblePanels"])
        await controller.check(
            f'#playback-exclusion-list input[data-device-id="{excluded_id}"]')
        await controller.wait_for_function(
            "() => (document.querySelector('#playback-exclusion-summary')?.textContent || '')"
            ".includes('1 excluded')", timeout=5000)
        exclusion_summary_before = await controller.locator(
            "#playback-exclusion-summary").inner_text()
        check("S13", "one chosen exclusion is visible before Start",
              "2 required" in exclusion_summary_before
              and "1 excluded" in exclusion_summary_before
              and "1 in this show" in exclusion_summary_before,
              summary=exclusion_summary_before)
        await controller.click("#btn-playback-start")
        await wait_until(lambda: status().get("state") == "playing", 25,
                         "the excluded-cohort Start never played")
        await wait_summary("Playing", 15000)
        excluded_state = await controller.evaluate("""() => {
            const block = document.querySelector('#playback-exclusions');
            const line = document.querySelector('#playback-cohort-line');
            return {
                exclusionsHidden: block.hidden,
                exclusionsVisible: !!block.getClientRects().length,
                title: document.querySelector('#playback-exclusions-title').textContent,
                summary: document.querySelector('#playback-exclusion-summary').textContent,
                listHidden: document.querySelector('#playback-exclusion-list').hidden,
                cohortHidden: line.hidden,
                cohortText: line.textContent,
            };
        }""")
        started_with_exclusion = status()
        report["excluded_session"] = {
            "status": started_with_exclusion,
            "summary": await summary(),
            "cohort": excluded_state,
            "exclusion_summary_before": exclusion_summary_before,
        }
        check("S13", "an active session with one exclusion shows the frozen exclusion block",
              not excluded_state["exclusionsHidden"]
              and excluded_state["exclusionsVisible"]
              and excluded_state["title"] == "This show's cohort"
              and "1 excluded" in excluded_state["summary"]
              and "1 in this show" in excluded_state["summary"]
              and excluded_state["listHidden"] is True,
              title=excluded_state["title"], summary=excluded_state["summary"])
        check("S13", "the excluded session keeps a one-line cohort summary",
              not excluded_state["cohortHidden"]
              and "2 required" in excluded_state["cohortText"]
              and "1 excluded" in excluded_state["cohortText"]
              and "1 in this show" in excluded_state["cohortText"],
              cohort=excluded_state["cohortText"])
        check("S13", "the server froze one excluded member for the show",
              started_with_exclusion.get("state") == "playing"
              and len(started_with_exclusion.get("excluded") or []) == 1
              and started_with_exclusion.get("excluded") == [excluded_id],
              state=started_with_exclusion.get("state"),
              excluded=started_with_exclusion.get("excluded"))
        await controller.screenshot(
            path=str(artifacts / "excluded-session-desktop.png"), full_page=True)
        await controller.click("#btn-playback-stop")
        await wait_until(lambda: status().get("state") == "stopped", 10,
                         "the excluded-session Stop did not stick")
        await controller.wait_for_function(
            "() => (document.querySelector('#playback-status')?.textContent || '')"
            " === 'Playback is stopped.'", timeout=15000)

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
