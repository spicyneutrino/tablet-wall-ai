"""Live browser acceptance for terminal recovery holds and recovery boundaries.

    .venv/bin/python -m simulator.browser.recovery_acceptance_run \
        --artifacts /tmp/tw-recovery-acceptance-NEW

Every scenario uses the real server, real device sockets and real Chromium
players on a disposable database and media directory. Nothing here is a
fixture or a scheduled-timestamp check:

* strict attempt cap: three committed recoveries, then the fourth valid fault
  from a client whose local recovery is exhausted. The session is blocked,
  attempts are 4, no fourth prepare is sent, and both clients hold a visible
  paused picture. The live controller shows the blocked state and Retry;
  clicking Retry resets attempts to 1 and both clients visibly advance.
* online cap: the same episode under ``online`` ends ``failed``, holds both
  clients, and the controller offers Start again rather than Retry.
* recovery timeout: one member's readiness reports are dropped, so the real
  deadline expires (about 31 seconds). The session is blocked, the missing
  member is named, both reachable clients hold, and Stop restores the
  persisted scene.
* multi-fault: an old-version fault and the other member's current-version
  fault are injected in both orders during one recovery. One recovery id and
  one attempt survive and no second prepare appears.
* final item: one video, no loop. A forced recovery returns to the final
  state with no pending next item; both clients advance and the natural end
  is not a fault.

A partial or aborted run always writes report.json with an explicit
``incomplete``/``error`` state and every completed check. Software evidence
only; no optical or physical claim.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
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

from simulator.browser.group_recovery_run import (
    HUNG_PLAY_WARNING,
    build_clip,
    console_violations,
    prepare_frames,
    primary_video,
    repository_state,
    video_state,
    visible_videos,
    wait_until,
)
from simulator.browser.run import (
    CUT_COLOURS,
    ClientSpec,
    Rig,
    artifact_directory,
    calibrate_cohort,
    child_environment,
    open_cohort,
)

REPO = Path(__file__).resolve().parents[2]
RUNNER = "recovery-acceptance/1"
EVIDENCE_KIND = "software-browser"
MAIN_SECONDS = 30
FINAL_SECONDS = 10
RECOVERY_WAIT = 20
CLIENTS = (
    (ClientSpec("accept-a", 240, 160, 1), 0),
    (ClientSpec("accept-b", 200, 150, 1.25), 180),
)


class Abort(RuntimeError):
    """A required acceptance check failed; the scenario cannot continue."""


async def main(artifacts: Path) -> int:
    artifacts = artifact_directory(artifacts)
    root = Path(tempfile.mkdtemp(prefix="tw-accept-recovery-", dir="/tmp"))
    for name in ("assets", "media", "tmp"):
        (root / name).mkdir()
    report: dict[str, Any] = {
        "runner": RUNNER,
        "evidence_kind": EVIDENCE_KIND,
        "repository": repository_state(),
        "mode": "software, not optical",
        "state": "incomplete",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": [],
        "scenarios": [],
    }
    checks = report["checks"]
    started = time.monotonic()

    def check(name: str, ok: bool, **detail: Any) -> bool:
        checks.append({"name": name, "passed": bool(ok), **detail})
        return bool(ok)

    def require(name: str, ok: bool, **detail: Any) -> None:
        if not check(name, ok, **detail):
            raise Abort(name)

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
    process = None
    http = None
    playwright = None
    browser = None
    controller = None
    controller_events: list[dict[str, Any]] = []
    pages: list[tuple[Any, Any]] = []

    def write_report() -> None:
        report["checks_passed"] = sum(1 for item in checks if item["passed"])
        report["checks_total"] = len(checks)
        report["scenarios_passed"] = sum(
            1 for item in report["scenarios"] if item["state"] == "passed"
        )
        report["scenarios_total"] = len(report["scenarios"])
        report["duration_s"] = round(time.monotonic() - started, 1)
        report["finished_at"] = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
        )
        (artifacts / "report.json").write_text(json.dumps(report, indent=2))

    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--fd", str(listener.fileno()),
             "--workers", "1", "--no-access-log"],
            cwd=REPO, env=env, pass_fds=(listener.fileno(),),
            stdout=log, stderr=subprocess.STDOUT,
        )
        listener.close()
        listener = None
        http = httpx.Client(base_url=base, headers={"Origin": base}, timeout=60)
        deadline = time.monotonic() + 20
        while True:
            try:
                if http.get("/wall").status_code in (200, 409):
                    break
            except httpx.HTTPError:
                pass
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("recovery acceptance server did not become ready")
            await asyncio.sleep(.1)

        main_clip = root / "clip-30s.mp4"
        final_clip = root / "clip-10s.mp4"
        report["clips"] = {
            "main": build_clip(main_clip, MAIN_SECONDS),
            "final": build_clip(final_clip, FINAL_SECONDS),
        }
        videos: dict[str, dict[str, Any]] = {}
        for label, path in (("main", main_clip), ("final", final_clip)):
            uploaded = http.post(
                f"/uploads?name={path.name}", content=path.read_bytes(),
                headers={"Content-Type": "video/mp4"},
            )
            require(f"upload of the {label} live clip succeeds",
                    uploaded.status_code == 201, response=uploaded.text[-300:])
            videos[label] = uploaded.json()["asset"]
        main = videos["main"]
        final = videos["final"]

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            env={**os.environ, "TMPDIR": str(root / "tmp")}
        )
        report["browser_version"] = browser.version
        rig = Rig(base=base, http=http, browser=browser, playwright=playwright,
                  browser_env={**os.environ, "TMPDIR": str(root / "tmp")},
                  root=root, artifacts=artifacts, observations=[],
                  captured_pages=[], resources=[], owned={}, check=check)
        pages = await open_cohort(rig, CLIENTS, "acceptance")
        device_ids = [observation.device_id for _, observation in pages]
        assets = await calibrate_cohort(
            rig, pages, [mount for _, mount in CLIENTS], CUT_COLOURS, "acceptance"
        )
        report["cohort"] = device_ids

        controller = await browser.new_page(viewport={"width": 1440, "height": 1000})
        controller.on("pageerror", lambda error: controller_events.append(
            {"kind": "page_error", "text": str(error)}))
        controller.on("console", lambda message: controller_events.append(
            {"kind": "console", "level": message.type, "text": message.text}))
        controller.on("requestfailed", lambda request: controller_events.append(
            {"kind": "request_failed", "url": request.url,
             "error": request.failure}))
        await controller.goto(base + "/controller/physical.html",
                              wait_until="networkidle")
        await controller.evaluate(
            "document.querySelector('#playback-details').open = true"
        )

        def status() -> dict[str, Any]:
            return http.get("/api/v3/playback").json()

        async def stop_session() -> None:
            current = status()
            if current.get("state") in (None, "stopped"):
                return
            version = current.get("version")
            if version is None:
                return
            for _ in range(3):
                response = http.post(
                    "/api/v3/playback/stop", headers={"If-Match": str(version)})
                if response.status_code == 200:
                    break
                if response.status_code != 412:
                    break
                version = status().get("version")
            await wait_until(
                lambda: status().get("state") in (None, "stopped"),
                5, "the session did not stop",
            )
            await asyncio.sleep(.4)

        async def save_and_start(items: list[str], policy: str,
                                 loop: bool = False) -> None:
            await stop_session()
            etag = http.get("/api/v3/playlist").json()["etag"]
            saved = http.put("/api/v3/playlist", json={
                "items": [{"asset": asset, "dwell_ms": 1000} for asset in items],
                "loop": loop,
            }, headers={"If-Match": etag})
            require("the scenario playlist is saved",
                    saved.status_code == 200, response=saved.text[-300:])
            started_session = http.post(
                "/api/v3/playback/start", json={"policy": policy})
            require(f"the {policy} session starts",
                    started_session.status_code == 200,
                    response=started_session.text[-300:])

        async def both_playing(minimum: float = .2) -> bool:
            for page, _ in pages:
                state = await video_state(page)
                if not any(
                    video["t"] >= minimum
                    and not video["paused"]
                    and video["ready"] >= 2
                    for video in visible_videos(state)
                ):
                    return False
            return True

        async def wait_playing(minimum: float = .2,
                               timeout: float = 20) -> None:
            async def ready() -> bool:
                return await both_playing(minimum)

            await wait_until(ready, timeout, "both clients did not play")

        async def advance_rows(interval: float = .7) -> list[dict[str, Any]]:
            first = [primary_video(await video_state(page)) for page, _ in pages]
            await asyncio.sleep(interval)
            second = [primary_video(await video_state(page)) for page, _ in pages]
            rows = []
            for (_, observation), before, after in zip(pages, first, second):
                rows.append({
                    "device": observation.device_id,
                    "before": before,
                    "after": after,
                    "delta_s": (
                        round(after["t"] - before["t"], 3)
                        if before and after else None
                    ),
                })
            return rows

        async def require_advancing(label: str, interval: float = .7) -> None:
            rows = await advance_rows(interval)
            report.setdefault("advance", {})[label] = rows
            require(
                f"{label}: both clients visibly advance",
                all(
                    row["before"] and row["after"]
                    and row["before"]["visible"] and row["after"]["visible"]
                    and row["before"]["opacity"] > .05
                    and row["before"]["width"] > 1
                    and row["before"]["height"] > 1
                    and not row["after"]["paused"]
                    and row["after"]["ready"] >= 2
                    and (row["delta_s"] or 0) >= .15
                    for row in rows
                ),
                rows=rows,
            )

        async def hold_rows(seconds: float = 1.3) -> list[dict[str, Any]]:
            first = [primary_video(await video_state(page)) for page, _ in pages]
            await asyncio.sleep(seconds)
            second = [primary_video(await video_state(page)) for page, _ in pages]
            rows = []
            for (_, observation), before, after in zip(pages, first, second):
                rows.append({
                    "device": observation.device_id,
                    "before": before,
                    "after": after,
                    "delta_s": (
                        round(after["t"] - before["t"], 3)
                        if before and after else None
                    ),
                })
            return rows

        async def require_hold(label: str, seconds: float = 1.3) -> None:
            async def holding() -> bool:
                for page, _ in pages:
                    video = primary_video(await video_state(page))
                    if not video or not video["paused"]:
                        return False
                return True

            await wait_until(holding, 6, f"{label}: clients did not hold")
            rows = await hold_rows(seconds)
            report.setdefault("holds", {})[label] = rows
            require(
                f"{label}: both clients hold a visible paused picture",
                all(
                    row["before"] and row["after"]
                    and row["before"]["visible"] and row["after"]["visible"]
                    and row["before"]["opacity"] > .05
                    and row["before"]["width"] > 1
                    and row["before"]["height"] > 1
                    and row["after"]["ready"] >= 2
                    and row["after"]["paused"]
                    and abs(row["delta_s"] or 0) <= .05
                    for row in rows
                ),
                rows=rows,
            )

        async def send_frame(index: int, payload: dict[str, Any]) -> bool:
            return bool(await pages[index][0].evaluate("""(frame) => {
                const sockets = (window.__fleetSockets || [])
                    .filter((socket) => socket.readyState === 1);
                if (!sockets.length) return false;
                sockets[sockets.length - 1].send(JSON.stringify(frame));
                return true;
            }""", payload))

        def fault_position(index: int) -> int:
            current = status()
            sample = (current.get("video") or {}).get(device_ids[index]) or {}
            asset = current.get("live", {}).get("current") or {}
            duration = asset.get("duration_ms") or 0
            if sample.get("age_ms", 9999) < 1500 and duration:
                return max(0, min(int(sample["media_ms"]) + 100, duration - 1))
            return 1000

        def fault_payload(index: int, position_ms: int | None = None,
                          version: int | None = None,
                          occurrence: Any = None) -> dict[str, Any]:
            current = status()
            return {
                "type": "video_fault",
                "session_id": current["session_id"],
                "version": current["version"] if version is None else version,
                "occurrence": (current["current"] if occurrence is None
                               else occurrence),
                "position_ms": (fault_position(index)
                                if position_ms is None else position_ms),
                "reason": "stalled",
            }

        async def send_fault(index: int, position_ms: int | None = None,
                             version: int | None = None,
                             occurrence: Any = None) -> dict[str, Any]:
            payload = fault_payload(index, position_ms, version, occurrence)
            require(f"a valid video_fault is sent from {device_ids[index]}",
                    await send_frame(index, payload), payload=payload)
            return payload

        async def wait_recovery_started(previous_id: str | None,
                                        attempts: int) -> str:
            async def accepted() -> bool:
                recovery = status().get("recovery") or {}
                return (
                    recovery.get("id") != previous_id
                    and recovery.get("attempts") == attempts
                )

            await wait_until(accepted, 8, "the recovery fault was not accepted")
            return status()["recovery"]["id"]

        async def wait_recovery_playing(recovery_id: str,
                                        timeout: float = RECOVERY_WAIT) -> None:
            async def playing() -> bool:
                current = status()
                recovery = current.get("recovery") or {}
                if (recovery.get("id") != recovery_id
                        or recovery.get("state") != "playing"):
                    return False
                effective = current.get("current_effective_ms")
                if (effective is None
                        or current.get("now_ms", 0) < effective):
                    return False
                position = recovery.get("position_ms", 0)
                return await both_playing(max(0, position / 1000 - .6))

            await wait_until(playing, timeout,
                             "the recovery did not commit and resume")

        async def fault_and_recover(index: int, attempts: int,
                                    label: str) -> str:
            previous = (status().get("recovery") or {}).get("id")
            position = fault_position(index)
            await send_fault(index, position)
            recovery_id = await wait_recovery_started(previous, attempts)
            await wait_recovery_playing(recovery_id)
            await require_advancing(label)
            frames = [
                sum(1 for frame in prepare_frames(observation)
                    if frame.get("recovery_id") == recovery_id)
                for _, observation in pages
            ]
            require(
                f"{label}: each client received exactly one recovery prepare "
                "under the wire recovery id",
                frames == [1] * len(pages),
                recovery_id=recovery_id, frames=frames,
            )
            return recovery_id

        def prepare_window() -> dict[str, int]:
            return {observation.device_id: len(observation.events)
                    for _, observation in pages}

        def recovery_prepares_since(window: dict[str, int]) -> list[dict[str, Any]]:
            entries = []
            for _, observation in pages:
                for event in observation.events[window[observation.device_id]:]:
                    frame = event.get("frame")
                    if (event.get("kind") == "ws_received"
                            and isinstance(frame, dict)
                            and frame.get("type") == "prepare"
                            and frame.get("recovery_id")):
                        entries.append({
                            "device": observation.device_id,
                            "recovery_id": frame["recovery_id"],
                            "position_ms": frame.get("start_media_ms"),
                        })
            return entries

        def sends_since(window: dict[str, int]) -> list[dict[str, Any]]:
            entries = []
            for _, observation in pages:
                for event in observation.events[window[observation.device_id]:]:
                    frame = event.get("frame")
                    if (event.get("kind") == "ws_sent"
                            and isinstance(frame, dict)):
                        entries.append({
                            "device": observation.device_id,
                            "frame": frame,
                        })
            return entries

        async def controller_ui() -> dict[str, Any]:
            return await controller.evaluate("""() => {
                const status = document.querySelector('#playback-status');
                const retry = document.querySelector('#btn-playback-retry');
                const start = document.querySelector('#btn-playback-start');
                const stop = document.querySelector('#btn-playback-stop');
                return {
                    state: status ? status.dataset.state : null,
                    text: status ? status.innerText : '',
                    retryHidden: retry ? retry.hidden : null,
                    retryDisabled: retry ? retry.disabled : null,
                    startHidden: start ? start.hidden : null,
                    startText: start ? start.textContent.trim() : null,
                    stopHidden: stop ? stop.hidden : null,
                    facts: document.querySelector('#playback-facts')?.innerText || '',
                };
            }""")

        async def wait_controller(state_name: str, timeout: float = 12) -> None:
            await controller.wait_for_function(
                "(want) => document.querySelector('#playback-status')?.dataset.state"
                " === want", arg=state_name, timeout=int(timeout * 1000),
            )

        def scenario_markers() -> tuple[dict[str, int], int]:
            return (
                {observation.device_id: len(observation.events)
                 for _, observation in pages},
                len(controller_events),
            )

        def scenario_violations(window: dict[str, int],
                                controller_index: int) -> list[dict[str, Any]]:
            events = [
                event for _, observation in pages
                for event in observation.events[window[observation.device_id]:]
            ]
            return console_violations(events + controller_events[controller_index:])

        async def run_scenario(name: str, body: Any) -> None:
            window, controller_index = scenario_markers()
            entry: dict[str, Any] = {
                "name": name,
                "state": "running",
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            report["scenarios"].append(entry)
            began = time.monotonic()
            try:
                await body()
            except Abort as error:
                entry["state"] = "failed"
                entry["error"] = f"required check failed: {error}"
            except Exception as error:
                entry["state"] = "failed"
                entry["error"] = f"{type(error).__name__}: {error}"
                entry["traceback"] = traceback.format_exc()[-3000:]
                check(f"{name}: the scenario completes without an exception",
                      False, error=entry["error"])
            else:
                entry["state"] = "passed"
            finally:
                violations = scenario_violations(window, controller_index)
                report.setdefault("violations", {})[name] = violations
                if not check(
                    f"{name}: no unexpected page errors, console errors or "
                    "failed requests",
                    not violations, violations=violations,
                    allowed_warning=HUNG_PLAY_WARNING.pattern,
                ):
                    entry["state"] = "failed"
                entry["duration_s"] = round(time.monotonic() - began, 1)
                try:
                    await stop_session()
                except Exception:
                    pass

        # --- strict cap, operator Retry ----------------------------------
        async def strict_cap() -> None:
            await save_and_start([main["id"], assets["red"]], "strict")
            await wait_playing(.2)
            for attempt in (1, 2, 3):
                await wait_until(
                    lambda: _past_anchor(http), 12, "not past the recovery anchor")
                await fault_and_recover(
                    0, attempt, f"strict cap automatic recovery {attempt}")

            window = prepare_window()
            report["strict_cap_before_fault"] = status()
            fault_window = len(pages[0][1].events)
            froze = await pages[0][0].evaluate("""() => {
                const v = [...document.querySelectorAll('video')]
                    .find(v => getComputedStyle(v).visibility !== 'hidden'
                        && v.getBoundingClientRect().width > 1);
                if (!v) return false;
                v.play = function () { return new Promise(function () {}); };
                v.pause();
                return true;
            }""")
            require("the fourth fault client is frozen with a hung play", froze)
            await wait_until(
                lambda: status().get("state") in ("blocked", "failed"),
                25, "the fourth fault did not reach the cap",
            )
            blocked_at = time.monotonic()
            blocked = status()
            report["strict_cap"] = blocked
            client_faults = [
                event for event in pages[0][1].events[fault_window:]
                if event.get("kind") == "ws_sent"
                and isinstance(event.get("frame"), dict)
                and event["frame"].get("type") == "video_fault"
            ]
            report["strict_cap_client_faults"] = client_faults
            require(
                "the strict cap is the frozen client's own fourth valid fault",
                any(event["time"] <= blocked_at + .5 for event in client_faults),
                faults=client_faults, blocked_at=blocked_at,
            )
            require("the strict cap names the frozen client's fault",
                    (blocked.get("recovery") or {}).get("device_id")
                    == device_ids[0],
                    recovery=blocked.get("recovery"),
                    expected=device_ids[0])
            require("strict cap reports blocked", blocked.get("state") == "blocked",
                    state=blocked.get("state"))
            require("strict cap retains attempt 4",
                    (blocked.get("recovery") or {}).get("attempts") == 4,
                    recovery=blocked.get("recovery"))
            require("strict cap clears the next preparation",
                    blocked.get("pending") is None, pending=blocked.get("pending"))
            await asyncio.sleep(.8)
            entries = recovery_prepares_since(window)
            require("the strict cap sends no fourth recovery prepare",
                    entries == [], prepares=entries)
            await require_hold("strict cap holds both clients")

            await wait_controller("blocked")
            ui = await controller_ui()
            report["strict_controller"] = ui
            require("the live controller renders the real blocked state",
                    ui["state"] == "blocked"
                    and "Blocked" in ui["text"]
                    and "attempt 4" in ui["text"],
                    ui=ui)
            require("the live blocked controller offers Retry and Stop",
                    ui["retryHidden"] is False and ui["stopHidden"] is False,
                    ui=ui)

            await controller.click("#btn-playback-retry")
            await wait_until(
                lambda: (status().get("recovery") or {}).get("attempts") == 1,
                12, "Retry did not reset attempts to 1",
            )
            retry_id = status()["recovery"]["id"]
            await wait_recovery_playing(retry_id)
            await require_advancing("operator Retry resumes both clients")
            await controller.wait_for_function(
                "() => ['blocked', 'failed'].indexOf("
                "document.querySelector('#playback-status')?.dataset.state) === -1",
                timeout=10000,
            )
            ui = await controller_ui()
            report["strict_retry_controller"] = ui
            require("the live controller leaves the terminal state after Retry",
                    ui["state"] not in ("blocked", "failed"), ui=ui)

        # --- online cap ---------------------------------------------------
        async def online_cap() -> None:
            await save_and_start([main["id"], assets["red"]], "online")
            await wait_playing(.2)
            for attempt in (1, 2, 3):
                await wait_until(
                    lambda: _past_anchor(http), 12, "not past the recovery anchor")
                await fault_and_recover(
                    0, attempt, f"online cap automatic recovery {attempt}")

            window = prepare_window()
            await send_fault(0)
            await wait_until(
                lambda: status().get("state") == "failed", 12,
                "the fourth online fault did not fail the session",
            )
            failed = status()
            report["online_cap"] = failed
            require("online cap reports failed", failed.get("state") == "failed",
                    state=failed.get("state"))
            require("online cap retains attempt 4",
                    (failed.get("recovery") or {}).get("attempts") == 4,
                    recovery=failed.get("recovery"))
            require("online cap clears the next preparation",
                    failed.get("pending") is None, pending=failed.get("pending"))
            await asyncio.sleep(.8)
            entries = recovery_prepares_since(window)
            require("the online cap sends no fourth recovery prepare",
                    entries == [], prepares=entries)
            await require_hold("online cap holds both clients")

            await wait_controller("failed")
            ui = await controller_ui()
            report["online_controller"] = ui
            require("the live failed controller offers Start again, not Retry",
                    ui["state"] == "failed"
                    and ui["startHidden"] is False
                    and ui["startText"] == "Start again"
                    and ui["retryHidden"] is True,
                    ui=ui)

        # --- recovery timeout --------------------------------------------
        async def recovery_timeout() -> None:
            await save_and_start([main["id"], assets["red"]], "strict")
            await wait_playing(.2)
            dropped = await pages[1][0].evaluate("""() => {
                if (!window.__originalSend) {
                    window.__originalSend = WebSocket.prototype.send;
                }
                window.__droppedReady = 0;
                WebSocket.prototype.send = function (data) {
                    try {
                        const frame = JSON.parse(data);
                        if (frame && frame.type === 'ready') {
                            window.__droppedReady += 1;
                            return;
                        }
                    } catch (error) { /* not JSON: send it */ }
                    return window.__originalSend.call(this, data);
                };
                return true;
            }""")
            require("one member's readiness reports can be dropped", dropped)
            try:
                previous = (status().get("recovery") or {}).get("id")
                await send_fault(0)
                recovery_id = await wait_recovery_started(previous, 1)
                began = time.monotonic()
                await wait_until(
                    lambda: status().get("state") in ("blocked", "failed"),
                    45, "the recovery deadline never expired",
                )
                elapsed = time.monotonic() - began
                timed_out = status()
                report["timeout"] = timed_out
                report["timeout_elapsed_s"] = round(elapsed, 1)
                require(
                    "the recovery timeout takes about the documented 31 seconds",
                    29 <= elapsed <= 45, elapsed_s=round(elapsed, 1),
                    recovery_id=recovery_id,
                    deadline_ms=(timed_out.get("recovery") or {}).get("deadline_ms"),
                )
                require("a strict timeout reports blocked",
                        timed_out.get("state") == "blocked",
                        state=timed_out.get("state"))
                recovery = timed_out.get("recovery") or {}
                require("the timeout names the member that never became ready",
                        device_ids[1] in (recovery.get("missing") or []),
                        missing=recovery.get("missing"), expected=device_ids[1])
                require(
                    "the timeout also names the missing member in session.missed",
                    device_ids[1] in (timed_out.get("missed") or []),
                    missed=timed_out.get("missed"),
                )
                await require_hold(
                    "the recovery timeout holds both reachable clients")

                await wait_controller("blocked")
                ui = await controller_ui()
                report["timeout_controller"] = ui
                require("the live timeout controller names the missing member",
                        "Missing members" in ui["facts"]
                        and "missing 1" in ui["facts"]
                        and CLIENTS[1][0].name in ui["facts"],
                        facts=ui["facts"][-600:])

                await stop_session()
                require("Stop clears the timed-out session",
                        status().get("state") == "stopped", status=status())
                await wait_until(lambda: restored_idle(pages), 10,
                                 "Stop did not restore the persisted scene")
            finally:
                with_restore = pages[1][0].evaluate("""() => {
                    if (window.__originalSend) {
                        WebSocket.prototype.send = window.__originalSend;
                        delete window.__originalSend;
                    }
                    return true;
                }""")
                try:
                    await with_restore
                except Exception:
                    pass

        # --- multi-fault, both orders ------------------------------------
        async def multi_fault() -> None:
            await save_and_start([main["id"], assets["red"]], "strict")
            await wait_playing(.2)

            async def one_order(name: str, first_device: int,
                                second_device: int, order: str,
                                expected_attempts: int) -> str:
                await wait_until(
                    lambda: _past_anchor(http), 12, "not past the recovery anchor")
                window = prepare_window()
                before = status()
                old_version = before["version"]
                occurrence = before["current"]
                await send_fault(first_device, position_ms=900,
                                 version=old_version, occurrence=occurrence)
                recovery_id = await wait_recovery_started(
                    (before.get("recovery") or {}).get("id"), expected_attempts)
                current = status()
                stale = {
                    "type": "video_fault",
                    "session_id": current["session_id"],
                    "version": old_version,
                    "occurrence": occurrence,
                    "position_ms": 950,
                    "reason": "stalled",
                }
                fresh = {
                    "type": "video_fault",
                    "session_id": current["session_id"],
                    "version": current["version"],
                    "occurrence": current["current"],
                    "position_ms": 960,
                    "reason": "stalled",
                }
                if order == "stale_first":
                    require(f"{name}: the stale fault is sent to the server",
                            await send_frame(first_device, stale))
                    require(f"{name}: the second member's current fault is sent",
                            await send_frame(second_device, fresh))
                else:
                    require(f"{name}: the second member's current fault is sent",
                            await send_frame(second_device, fresh))
                    require(f"{name}: the stale fault is sent to the server",
                            await send_frame(first_device, stale))
                await asyncio.sleep(.5)
                after = status()
                require(f"{name}: one recovery id survives both extra faults",
                        (after.get("recovery") or {}).get("id") == recovery_id,
                        recovery_id=recovery_id, recovery=after.get("recovery"))
                require(f"{name}: one attempt survives both extra faults",
                        (after.get("recovery") or {}).get("attempts")
                        == expected_attempts,
                        recovery=after.get("recovery"))
                entries = recovery_prepares_since(window)
                require(
                    f"{name}: no second prepare appears for either extra fault",
                    {entry["recovery_id"] for entry in entries} == {recovery_id}
                    and len(entries) == len(pages),
                    recovery_id=recovery_id, prepares=entries,
                )
                await wait_recovery_playing(recovery_id)
                await require_advancing(f"{name} resumes both clients")
                return recovery_id

            order_a = await one_order(
                "multi-fault stale then current", 0, 1, "stale_first", 1)
            order_b = await one_order(
                "multi-fault current then stale", 1, 0, "current_first", 2)
            report["multi_fault"] = {
                "first_recovery_id": order_a,
                "second_recovery_id": order_b,
            }

        # --- final item ---------------------------------------------------
        async def final_item() -> None:
            await save_and_start([final["id"]], "strict")
            saved = (http.get("/api/v3/playlist").json().get("playlist") or {})
            require("the final case is one video with no loop",
                    len(saved.get("items", [])) == 1
                    and saved.get("loop") is False
                    and saved["items"][0].get("asset") == final["id"],
                    playlist=saved)
            await wait_playing(.2)
            window = prepare_window()
            await wait_until(lambda: _past_anchor(http), 12,
                             "not past the final-item anchor")
            await send_fault(0, position_ms=1000)
            recovery_id = await wait_recovery_started(None, 1)
            await wait_recovery_playing(recovery_id)
            committed = status()
            report["final_committed"] = committed
            recovery = committed.get("recovery") or {}
            require("final item recovery commits into the final state",
                    committed.get("state") == "final"
                    and committed.get("final") is True
                    and recovery.get("state") == "playing",
                    state=committed.get("state"), recovery=recovery)
            require("the final recovery has no pending next item",
                    committed.get("pending") is None,
                    pending=committed.get("pending"))
            await require_advancing("final item recovery resumes both clients")

            sent_window = {observation.device_id: len(observation.events)
                           for _, observation in pages}
            await wait_until(
                lambda: _final_ended(pages, final["durationMs"]),
                20, "the final video did not reach its natural end",
            )
            ended = status()
            report["final_ended"] = ended
            require("the natural end is not a fault",
                    (ended.get("recovery") or {}).get("id") == recovery_id
                    and (ended.get("recovery") or {}).get("attempts") == 1,
                    recovery=ended.get("recovery"))
            require("the session stays final at the natural end",
                    ended.get("state") == "final", state=ended.get("state"))
            faults = [
                entry for entry in sends_since(sent_window)
                if entry["frame"].get("type") == "video_fault"
            ]
            require("no client reports a fault at the natural end",
                    faults == [], faults=faults)
            prepares = [
                {"device": observation.device_id, "frame": event["frame"]}
                for _, observation in pages
                for event in observation.events[window[observation.device_id]:]
                if event.get("kind") == "ws_received"
                and isinstance(event.get("frame"), dict)
                and event["frame"].get("type") == "prepare"
            ]
            require(
                "the final item sends only its recovery prepares and no next "
                "preparation",
                len(prepares) == len(pages)
                and all(item["frame"].get("recovery_id") == recovery_id
                        for item in prepares),
                recovery_id=recovery_id, prepares=prepares,
            )

        await run_scenario("strict_cap_and_retry", strict_cap)
        await run_scenario("online_cap", online_cap)
        await run_scenario("recovery_timeout", recovery_timeout)
        await run_scenario("multi_fault_both_orders", multi_fault)
        await run_scenario("final_item", final_item)
        check(
            "all five planned live scenarios ran",
            [item["name"] for item in report["scenarios"]] == [
                "strict_cap_and_retry", "online_cap", "recovery_timeout",
                "multi_fault_both_orders", "final_item",
            ],
            scenarios=[item["name"] for item in report["scenarios"]],
        )

        await stop_session()
        report["state"] = (
            "complete"
            if all(item["passed"] for item in checks)
            and all(item["state"] == "passed" for item in report["scenarios"])
            else "failed"
        )
        return 0 if report["state"] == "complete" else 1
    except Exception as error:
        report["state"] = "incomplete"
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()[-4000:]
        return 1
    finally:
        if http is not None:
            http.close()
        if playwright is not None:
            await playwright.stop()
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        log.close()
        shutil.rmtree(root, ignore_errors=True)
        write_report()


def _past_anchor(http: httpx.Client) -> bool:
    current = http.get("/api/v3/playback").json()
    effective = current.get("current_effective_ms")
    return (
        current.get("state") in ("playing", "final")
        and effective is not None
        and current.get("now_ms", 0) > effective + 300
    )


async def restored_idle(pages: list[tuple[Any, Any]]) -> bool:
    for page, _ in pages:
        state = await video_state(page)
        if visible_videos(state):
            return False
        if not state.get("canvasVisible"):
            return False
        pixel = state.get("pixel") or []
        if len(pixel) < 3 or pixel[0] < 100 or pixel[1] > 100 or pixel[2] < 100:
            return False
    return True


async def _final_ended(pages: list[tuple[Any, Any]], duration_ms: int) -> bool:
    for page, _ in pages:
        state = await video_state(page)
        visible = visible_videos(state)
        if not visible:
            return False
        video = max(visible, key=lambda item: item["t"])
        if not video["ended"] and video["t"] < duration_ms / 1000 - .25:
            return False
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.artifacts)))
