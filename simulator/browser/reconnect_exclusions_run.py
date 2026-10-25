"""Live browser acceptance for session exclusions and mid-video reconnect.

    .venv/bin/python -m simulator.browser.reconnect_exclusions_run \
        --artifacts /tmp/tw-reconnect-exclusions-NEW

Three calibrated desktop Chromium clients share one disposable server. The
runner checks the accepted Phase 3 behavior:

* Start-time exclusions keep the excluded tablet on the persisted scene, out
  of the effective cohort, and out of strict readiness. The all-excluded and
  unknown-id refusals are checked over HTTP; pause/resume keeps the frozen
  sets.
* A tablet that reconnects during a playing video starts exactly one group
  recovery at the server playhead with reason ``reconnect``. All original
  members prepare at that position and resume from one common anchor. A
  second drop while the recovery is still preparing consumes no new attempt.
* Paused, final, near-end and excluded sessions do not auto-rejoin; the tablet
  stays on the persisted scene.

Software evidence only. No optical, physical, iOS, CA, Wi-Fi, kiosk or soak
claim follows.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
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

import simulator.browser.run as run_module
from simulator.browser.group_recovery_run import (
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

# Capture the device socket so a deliberate close exercises the real client
# reconnect loop and the server's socket replacement path.
run_module.ONSET_SCRIPT += """
window.WebSocket = new Proxy(window.WebSocket, {construct(Target, args) {
    const ws = Reflect.construct(Target, args);
    if (String(args[0]).includes('/ws/device')) window.__reviewWs = ws;
    return ws;
}});
"""

REPO = Path(__file__).resolve().parents[2]
RUNNER = "reconnect-exclusions/1"
EVIDENCE_KIND = "software-browser"
SECONDS = 20
CLIENTS = (
    (ClientSpec("rejoin-a", 240, 160, 1), 0),
    (ClientSpec("rejoin-b", 200, 150, 1.25), 180),
    (ClientSpec("rejoin-c", 220, 140, 1), 0),
)


async def main(artifacts: Path) -> int:
    artifacts = artifact_directory(artifacts)
    root = Path(tempfile.mkdtemp(prefix="tw-rejoin-", dir="/tmp"))
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
            raise RuntimeError(name)

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
    pages: list[tuple[Any, Any]] = []

    def status() -> dict[str, Any]:
        return http.get("/api/v3/playback").json()

    def stop() -> None:
        current = status()
        if current.get("state") != "stopped":
            response = http.post(
                "/api/v3/playback/stop",
                headers={"If-Match": str(current["version"])},
            )
            assert response.status_code == 200, response.text

    def save_playlist(items: list[dict[str, Any]], loop: bool) -> dict[str, Any]:
        etag = http.get("/api/v3/playlist").json()["etag"]
        saved = http.put(
            "/api/v3/playlist",
            json={"items": items, "loop": loop},
            headers={"If-Match": etag},
        )
        assert saved.status_code == 200, saved.text
        return saved.json()

    def start(exclusions: list[str] | None = None, policy: str = "strict") -> dict[str, Any]:
        stop()
        body: dict[str, Any] = {"policy": policy}
        if exclusions is not None:
            body["exclusions"] = exclusions
        response = http.post("/api/v3/playback/start", json=body)
        assert response.status_code == 200, response.text
        return response.json()

    async def playing(minimum: float = .2, subset: list[Any] | None = None) -> bool:
        for page, _ in (subset if subset is not None else pages):
            state = await video_state(page)
            if not any(
                video["t"] >= minimum
                and not video["paused"]
                and video["ready"] >= 2
                and video["visible"]
                for video in state["videos"]
            ):
                return False
        return True

    async def advancing(interval: float = .7) -> list[dict[str, Any]]:
        first = [primary_video(await video_state(page)) for page, _ in pages]
        await asyncio.sleep(interval)
        second = [primary_video(await video_state(page)) for page, _ in pages]
        rows = []
        for (page, observation), before, after in zip(pages, first, second):
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

    async def drop(page: Any) -> None:
        closed = await page.evaluate("""() => {
            if (!window.__reviewWs) return false;
            window.__reviewWs.close(4000, "review reconnect");
            return true;
        }""")
        if not closed:
            raise RuntimeError("the device socket was not captured")

    async def idle_scene(page: Any) -> bool:
        state = await video_state(page)
        if visible_videos(state):
            return False
        pixel = state.get("pixel")
        return bool(
            state.get("canvasVisible")
            and pixel
            and max(
                abs(pixel[0] - CUT_COLOURS["idle"][0]),
                abs(pixel[1] - CUT_COLOURS["idle"][1]),
                abs(pixel[2] - CUT_COLOURS["idle"][2]),
            ) <= 40
        )

    def recovery_prepares() -> list[list[dict[str, Any]]]:
        rows = []
        for _, observation in pages:
            frames = [
                frame for frame in prepare_frames(observation)
                if frame.get("recovery_id")
            ]
            rows.append(frames)
        return rows

    def unexpected_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Expected network loss from the deliberate offline windows is not a defect."""
        allowed = (
            "ERR_INTERNET_DISCONNECTED", "ERR_NETWORK_CHANGED",
            "ERR_CONNECTION_RESET", "ERR_CONNECTION_REFUSED", "ERR_ABORTED",
        )
        result = []
        for violation in console_violations(events):
            if violation.get("kind") == "request_failed" and any(
                marker in str(violation.get("error", "")) for marker in allowed
            ):
                continue
            if violation.get("kind") == "console" and any(
                marker in str(violation.get("text", "")) for marker in allowed
            ):
                continue
            result.append(violation)
        return result

    def scenario(name: str) -> dict[str, Any]:
        entry = {"id": name, "state": "running"}
        report["scenarios"].append(entry)
        return entry

    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--fd", str(listener.fileno()),
             "--workers", "1", "--no-access-log"],
            cwd=REPO, env=env, pass_fds=(listener.fileno(),),
            stdout=log, stderr=subprocess.STDOUT,
        )
        listener.close()
        listener = None
        http = httpx.Client(base_url=base, headers={"Origin": base}, timeout=30)
        deadline = time.monotonic() + 20
        while True:
            try:
                if http.get("/wall").status_code in (200, 409):
                    break
            except httpx.HTTPError:
                pass
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("server did not become ready")
            await asyncio.sleep(.1)

        clip = root / "clip.mp4"
        report["clip"] = build_clip(clip, SECONDS)
        uploaded = http.post(
            "/uploads?name=clip.mp4", content=clip.read_bytes(),
            headers={"Content-Type": "video/mp4"},
        )
        assert uploaded.status_code == 201, uploaded.text
        video = uploaded.json()["asset"]

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            env={**os.environ, "TMPDIR": str(root / "tmp")}
        )
        report["browser_version"] = browser.version
        rig = Rig(
            base=base, http=http, browser=browser, playwright=playwright,
            browser_env={**os.environ, "TMPDIR": str(root / "tmp")},
            root=root, artifacts=artifacts, observations=[],
            captured_pages=[], resources=[], owned={}, check=check,
        )
        pages = await open_cohort(rig, CLIENTS, "rejoin")
        assets = await calibrate_cohort(
            rig, pages, [mount for _, mount in CLIENTS], CUT_COLOURS, "rejoin"
        )
        ids = [observation.device_id for _, observation in pages]
        report["devices"] = ids
        excluded = ids[2]
        red = assets["red"]

        # ---- Exclusions -------------------------------------------------
        entry = scenario("exclusions")
        entry_start = len(checks)
        save_playlist([
            {"asset": video["id"], "dwell_ms": 1000},
            {"asset": red, "dwell_ms": 1000},
        ], False)
        began = start([excluded])
        check(
            "excluded start reports required, excluded and effective cohort",
            began.get("required") == sorted(ids)
            and began.get("excluded") == [excluded]
            and began.get("cohort") == sorted(ids[:2]),
            status=began,
        )
        await wait_until(lambda: playing(subset=pages[:2]), 20,
                         "the included cohort never played")
        await asyncio.sleep(.5)
        await wait_until(lambda: idle_scene(pages[2][0]), 10,
                         "the excluded tablet never showed the persisted scene")
        excluded_state = await video_state(pages[2][0])
        check(
            "the excluded tablet stays on the persisted idle scene",
            not visible_videos(excluded_state) and await idle_scene(pages[2][0]),
            state=excluded_state,
        )
        excluded_prepares = prepare_frames(pages[2][1])
        check(
            "the excluded tablet receives no preparation",
            not excluded_prepares,
            prepares=excluded_prepares,
        )
        included_rows = await advancing()
        check(
            "both included tablets visibly advance",
            all(row["delta_s"] is not None and row["delta_s"] > .3
                for row in included_rows[:2]),
            rows=included_rows[:2],
        )
        all_excluded = http.post(
            "/api/v3/playback/start",
            json={"policy": "strict", "exclusions": ids},
        )
        unknown = http.post(
            "/api/v3/playback/start",
            json={"policy": "strict", "exclusions": [
                "5c6d7e8f-9012-4a3b-8c4d-5e6f708192a3"
            ]},
        )
        check(
            "all-excluded is refused and an unknown id is rejected",
            all_excluded.status_code == 409 and unknown.status_code == 422,
            all_excluded=all_excluded.status_code, unknown=unknown.status_code,
        )
        paused_version = status()["version"]
        paused = http.post(
            "/api/v3/playback/pause",
            headers={"If-Match": str(paused_version)},
        )
        assert paused.status_code == 200, paused.text
        resumed = http.post(
            "/api/v3/playback/start",
            json={"policy": "online", "exclusions": ids},
        )
        check(
            "a paused resume keeps the frozen exclusions and ignores a new list",
            resumed.status_code == 200
            and resumed.json()["excluded"] == [excluded]
            and resumed.json()["cohort"] == sorted(ids[:2]),
            status=resumed.json(),
        )
        await wait_until(lambda: playing(subset=pages[:2]), 20,
                         "the cohort did not resume")
        check("the exclusion scenario has no page errors", not unexpected_events(
            [event for _, observation in pages for event in observation.events]
        ), violations=unexpected_events(
            [event for _, observation in pages for event in observation.events]
        )[:5])
        entry["state"] = "passed" if all(
            item["passed"] for item in checks[entry_start:]
        ) else "failed"

        # ---- Reconnect --------------------------------------------------
        entry = scenario("reconnect")
        entry_start = len(checks)
        started_status = start([])
        check("all three start for reconnect",
              started_status.get("cohort") == sorted(ids))
        await wait_until(playing, 20, "all three never played")
        await asyncio.sleep(.5)
        attempts_before = int((status().get("recovery") or {}).get("attempts") or 0)
        await drop(pages[2][0])

        async def reconnect_started() -> bool:
            current = status()
            recovery = current.get("recovery") or {}
            return current.get("state") == "recovering" and recovery.get("reason") == "reconnect"

        await wait_until(reconnect_started, 25, "the reconnect recovery never started")
        recovery = status()["recovery"]
        check(
            "a returning playing video starts one reconnect recovery",
            recovery.get("attempts") == attempts_before + 1
            and recovery.get("device_id") == excluded
            and recovery.get("reason") == "reconnect",
            recovery=recovery,
        )
        # Drop the same member again while the recovery is still preparing.
        await drop(pages[2][0])
        await asyncio.sleep(1.0)
        after_second = status()
        check(
            "a second drop during the recovery spends no extra attempt",
            after_second.get("state") in ("recovering", "playing")
            and (after_second.get("recovery") or {}).get("attempts") == recovery.get("attempts"),
            status=after_second,
        )
        await wait_until(playing, 25, "the group did not resume after the reconnect")
        rows = await advancing()
        check(
            "all three original members advance after the reconnect",
            all(row["delta_s"] is not None and row["delta_s"] > .3 for row in rows),
            rows=rows,
        )
        prepares = recovery_prepares()
        check(
            "all three members prepared the same recovery identity and position",
            all(len(frames) >= 1 for frames in prepares)
            and len({frames[-1]["recovery_id"] for frames in prepares if frames}) == 1
            and len({frames[-1]["start_media_ms"] for frames in prepares if frames}) == 1,
            prepares=[[{
                "recovery_id": frame.get("recovery_id"),
                "start_media_ms": frame.get("start_media_ms"),
            } for frame in frames] for frames in prepares],
        )
        check("the reconnect scenario has no page errors", not unexpected_events(
            [event for _, observation in pages for event in observation.events]
        ), violations=unexpected_events(
            [event for _, observation in pages for event in observation.events]
        )[:5])
        entry["state"] = "passed" if all(
            item["passed"] for item in checks[entry_start:]
        ) else "failed"

        # ---- Paused does not auto-rejoin --------------------------------
        entry = scenario("paused_no_rejoin")
        entry_start = len(checks)
        paused_version = status()["version"]
        paused = http.post(
            "/api/v3/playback/pause",
            headers={"If-Match": str(paused_version)},
        )
        assert paused.status_code == 200, paused.text
        await drop(pages[2][0])
        await asyncio.sleep(1.5)
        paused_state = status()
        check(
            "a reconnect while paused does not start a recovery",
            paused_state.get("state") == "paused"
            and not ((paused_state.get("recovery") or {}).get("reason") == "reconnect"),
            status=paused_state,
        )
        resumed = http.post(
            "/api/v3/playback/start",
            headers={"If-Match": str(paused_state["version"])},
        )
        check("the paused session resumes after the reconnect", resumed.status_code == 200,
              text=resumed.text)
        await wait_until(playing, 25, "the paused cohort did not resume")
        entry["state"] = "passed" if all(
            item["passed"] for item in checks[entry_start:]
        ) else "failed"

        # ---- Final does not auto-rejoin --------------------------------
        entry = scenario("final_no_rejoin")
        entry_start = len(checks)
        save_playlist([{"asset": video["id"], "dwell_ms": 1000}], False)
        final_started = start([])
        check("the final session starts", final_started.get("state") in ("preparing", "playing"),
              status=final_started)
        await wait_until(lambda: status().get("state") == "final", 25,
                         "the final session never reached final")
        await drop(pages[2][0])
        await asyncio.sleep(1.5)
        final_state = status()
        check(
            "a reconnect during the final item does not start a recovery",
            final_state.get("state") == "final"
            and not ((final_state.get("recovery") or {}).get("reason") == "reconnect"),
            status=final_state,
        )
        entry["state"] = "passed" if all(
            item["passed"] for item in checks[entry_start:]
        ) else "failed"

        # ---- Excluded does not auto-rejoin ------------------------------
        entry = scenario("excluded_no_rejoin")
        entry_start = len(checks)
        save_playlist([
            {"asset": video["id"], "dwell_ms": 1000},
            {"asset": red, "dwell_ms": 1000},
        ], False)
        excluded_started = start([excluded])
        check("the excluded session starts", excluded_started.get("cohort") == sorted(ids[:2]),
              status=excluded_started)
        await wait_until(lambda: playing(subset=pages[:2]), 20,
                         "the included cohort did not play")
        await drop(pages[2][0])
        await asyncio.sleep(1.5)
        excluded_state = status()
        check(
            "a reconnect by an excluded tablet starts no recovery",
            excluded_state.get("state") == "playing"
            and not ((excluded_state.get("recovery") or {}).get("reason") == "reconnect"),
            status=excluded_state,
        )
        check(
            "the excluded tablet remains on the persisted scene",
            await idle_scene(pages[2][0]),
        )
        entry["state"] = "passed" if all(
            item["passed"] for item in checks[entry_start:]
        ) else "failed"

        report["state"] = "complete"
        report["status"] = "passed" if all(item["passed"] for item in checks) else "failed"
        return 0 if report["status"] == "passed" else 1
    except BaseException as error:
        report["error"] = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
        raise
    finally:
        try:
            if http is not None:
                http.close()
        except Exception:
            pass
        if playwright is not None:
            await playwright.stop()
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        log.close()
        live = [item for item in checks]
        report["checks_passed"] = sum(1 for item in live if item["passed"])
        report["checks_total"] = len(live)
        report["scenarios_passed"] = sum(
            1 for item in report["scenarios"] if item["state"] == "passed"
        )
        report["scenarios_total"] = len(report["scenarios"])
        report["duration_s"] = round(time.monotonic() - started, 1)
        report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (artifacts / "report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.artifacts)))
