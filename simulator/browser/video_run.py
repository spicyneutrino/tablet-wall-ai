"""Real-browser R4 video evidence on a disposable server.

    .venv/bin/python -m simulator.browser.video_run --artifacts /tmp/...

This is software evidence on one host clock. It does not claim optical
synchronization, physical decode, suspend, or ingress delivery. The report
records every check and the exact argv used to build the fixture. A page
error, an unexpected console warning/error, a failed request or an HTTP
status at or above 400 fails the run. This runner deliberately injects no
hung play or lost callback, so it classifies no injected warning.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
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

from simulator.browser.run import (
    CUT_COLOURS,
    ClientSpec,
    Observation,
    Rig,
    calibrate_cohort,
    child_environment,
    descendants,
    open_cohort,
    watch_page,
    wait_for_predicate,
)

REPO = Path(__file__).resolve().parents[2]
RUNNER = "video_run"
RUNNER_VERSION = 2
EVIDENCE_KIND = "software browser; not optical or physical"
VIDEO_SECONDS = 4
VIDEO_CLIENTS = (
    (ClientSpec("video-a", 240, 160, 1), 0),
    (ClientSpec("video-b", 200, 150, 1.25), 180),
)
# This runner creates no intentional browser warning. Anything in this list
# must name the exact page, kind and text of an injection this runner made.
INJECTED_WARNINGS: tuple[dict[str, Any], ...] = ()


def repo_metadata() -> dict[str, Any]:
    def run(*argv: str) -> str:
        return subprocess.run(
            argv, cwd=REPO, capture_output=True, text=True, timeout=10
        ).stdout.strip()

    return {
        "head_sha": run("git", "rev-parse", "HEAD") or None,
        "branch": run("git", "rev-parse", "--abbrev-ref", "HEAD") or None,
        "dirty": bool(run("git", "status", "--porcelain")),
    }


def build_clip(target: Path, seconds: int, source: str = "testsrc2") -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required for video evidence")
    argv = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"{source}=size=640x360:rate=30:duration={seconds}",
        "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.0",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(target),
    ]
    done = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    if done.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + done.stderr[-2000:])
    return {"argv": argv, "bytes": target.stat().st_size, "seconds": seconds,
            "source": source}


def build_video(target: Path) -> dict[str, Any]:
    return build_clip(target, VIDEO_SECONDS)


async def wait_until(predicate, timeout: float, message: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await predicate():
            return
        await asyncio.sleep(.05)
    raise RuntimeError(message)


async def canvas_centre(page: Any) -> list[int]:
    return await page.evaluate("""() => {
        const c = document.querySelector('#surface');
        const probe = document.createElement('canvas'); probe.width = probe.height = 1;
        const ctx = probe.getContext('2d', {willReadFrequently: true});
        ctx.drawImage(c, Math.floor(c.width/2), Math.floor(c.height/2), 1, 1, 0, 0, 1, 1);
        return [...ctx.getImageData(0, 0, 1, 1).data];
    }""")


def close_enough(pixel: list[int], rgb: tuple[int, int, int], tolerance: int = 30) -> bool:
    return len(pixel) >= 3 and max(abs(a - b) for a, b in zip(pixel[:3], rgb)) <= tolerance


async def video_state(page: Any) -> dict[str, Any]:
    return await page.evaluate("""() => {
        const videos = [...document.querySelectorAll('video')].map((v, index) => {
            const rect = v.getBoundingClientRect();
            const style = getComputedStyle(v);
            const opacity = Number.parseFloat(style.opacity);
            return {
                index: index,
                visible: style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && Number.isFinite(opacity) && opacity > 0
                    && rect.width > 0 && rect.height > 0,
                display: style.display, visibility: style.visibility, opacity: style.opacity,
                paused: v.paused, ended: v.ended, readyState: v.readyState,
                currentTime: v.currentTime, duration: v.duration,
                videoWidth: v.videoWidth, videoHeight: v.videoHeight,
                playbackRate: v.playbackRate,
                rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                transform: style.transform, loop: v.loop,
            };
        });
        return {videos, surface: !!document.querySelector('#surface')};
    }""")


def visible_videos(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [video for video in state["videos"] if video["visible"]]


def probe_details(probe: dict[str, Any]) -> dict[str, Any]:
    """Probe fields safe to pass as check detail; the verdict stays separate."""
    return {key: value for key, value in probe.items() if key != "ok"}


async def probe_advancing_video(
    page: Any,
    *,
    interval: float = 0.5,
    minimum_after: float = 0.0,
    expected_duration: float | None = None,
) -> dict[str, Any]:
    """Sample one visible video twice; it must be ready, playing and advancing."""
    before_state = await video_state(page)
    before_visible = visible_videos(before_state)
    if len(before_visible) != 1:
        return {"ok": False, "reason": "expected exactly one visible video before sampling",
                "visible_before": len(before_visible), "before": before_state}
    before = before_visible[0]
    await asyncio.sleep(interval)
    after_state = await video_state(page)
    after_visible = visible_videos(after_state)
    if len(after_visible) != 1:
        return {"ok": False, "reason": "expected exactly one visible video after sampling",
                "visible_after": len(after_visible), "after": after_state}
    after = after_visible[0]
    delta = after["currentTime"] - before["currentTime"]
    reasons: list[str] = []
    if before["paused"] or after["paused"]:
        reasons.append("paused")
    if before["ended"] or after["ended"]:
        reasons.append("ended")
    if before["readyState"] < 2 or after["readyState"] < 2:
        reasons.append("readyState below HAVE_CURRENT_DATA")
    if delta < 0.15:
        reasons.append("currentTime did not advance")
    if after["currentTime"] < minimum_after:
        reasons.append("currentTime is below the required floor")
    if expected_duration is not None and abs(after["duration"] - expected_duration) > 0.5:
        reasons.append("visible element has the wrong clip duration")
    if before["index"] != after["index"] and abs(before["duration"] - after["duration"]) > 0.5:
        reasons.append("the sampled element changed")
    return {
        "ok": not reasons,
        "reason": "; ".join(reasons) if reasons else None,
        "interval_s": interval,
        "delta_s": round(delta, 3),
        "before": before,
        "after": after,
    }


async def wait_advancing(
    page: Any,
    *,
    timeout: float = 20,
    interval: float = 0.5,
    minimum_after: float = 0.0,
    expected_duration: float | None = None,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last = await probe_advancing_video(
            page, interval=interval, minimum_after=minimum_after,
            expected_duration=expected_duration,
        )
        if last["ok"]:
            return last
        await asyncio.sleep(.05)
    raise RuntimeError("no visible advancing video: " + json.dumps(last)[-1200:])


async def wait_advancing_under(page: Any, maximum: float, timeout: float = 15) -> dict[str, Any]:
    """Wait for an advancing video whose currentTime proves a restart."""
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        try:
            probe = await wait_advancing(
                page, timeout=min(3, max(0.2, deadline - time.monotonic())),
                minimum_after=0.2,
            )
        except RuntimeError as exc:
            last = {"ok": False, "reason": str(exc)}
            continue
        last = probe
        if probe["after"]["currentTime"] < maximum:
            return probe
        await asyncio.sleep(.1)
    raise RuntimeError("no restarted advancing video: " + json.dumps(last)[-1200:])


async def check_advancing(
    record, page: Any, label: str, *, timeout: float = 10, **kwargs: Any
) -> dict[str, Any]:
    last: dict[str, Any] | None = None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        last = await probe_advancing_video(page, **kwargs)
        if last["ok"]:
            record(label, True, **probe_details(last))
            return last
        await asyncio.sleep(.05)
    record(label, False, **(probe_details(last) if last else {"reason": "no sample"}))
    return last or {"ok": False}


def unexpected_browser_issues(
    observation: Observation, allowed: tuple[dict[str, Any], ...] = INJECTED_WARNINGS
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for event in observation.events:
        kind = event["kind"]
        record: dict[str, Any] | None = None
        if kind == "page_error":
            record = {"kind": "page_error", "text": event["text"]}
        elif kind == "console" and event["level"] in ("error", "warning"):
            record = {"kind": "console_" + event["level"], "text": event["text"]}
        elif kind == "request_failed":
            record = {"kind": "request_failed", "url": event["url"], "error": event["error"]}
        elif kind == "http" and event["status"] >= 400:
            record = {"kind": "http_error", "url": event["url"], "status": event["status"]}
        elif kind == "ws_error":
            record = {"kind": "ws_error", "error": event["error"]}
        elif kind == "ws_close" and event["code"] not in (1000, 1001):
            record = {"kind": "ws_close", "code": event["code"], "reason": event["reason"]}
        if record is None:
            continue
        injected = next((
            entry["why"] for entry in allowed
            if entry.get("name") == observation.spec.name
            and entry.get("kind") == record["kind"]
            and entry.get("contains", "") in json.dumps(record)
        ), None)
        if injected is not None:
            record["injected"] = injected
        else:
            issues.append(record)
    return issues


def audit_browser_issues(check, observations: list[Observation]) -> None:
    for observation in observations:
        issues = unexpected_browser_issues(observation)
        check(
            observation.spec.name + ": no unexpected page errors, console errors, "
            "failed requests or HTTP errors",
            not issues, issues=issues,
        )


async def horizontal_overflow(page: Any) -> dict[str, Any]:
    return await page.evaluate("""() => {
        const root = document.documentElement;
        const body = document.body;
        return {
            innerWidth: window.innerWidth,
            documentWidth: root.scrollWidth,
            bodyWidth: body ? body.scrollWidth : null,
            scrollX: window.scrollX,
        };
    }""")


async def check_no_horizontal_clipping(record, page: Any, label: str) -> None:
    overflow = await horizontal_overflow(page)
    widths = [overflow["documentWidth"]]
    if overflow["bodyWidth"] is not None:
        widths.append(overflow["bodyWidth"])
    record(label, max(widths) <= overflow["innerWidth"] + 1, **overflow)


def read_status(http: httpx.Client) -> dict[str, Any]:
    return http.get("/api/v3/playback").json()


def cohort_complete(status: dict[str, Any], pages: list[tuple[Any, Observation]]) -> bool:
    expected = {observation.device_id for _, observation in pages}
    cohort = set(status.get("cohort") or [])
    return cohort == expected and len(cohort) == len(pages)


async def main(artifacts: Path) -> int:
    artifacts.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="tw-video-", dir="/tmp"))
    for name in ("assets", "media", "tmp"):
        (root / name).mkdir()
    report: dict[str, Any] = {
        "runner": RUNNER,
        "runner_version": RUNNER_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "state": "incomplete",
        "checks": [],
        "artifacts": str(artifacts),
        "root": str(root),
        **repo_metadata(),
    }
    checks: list[dict[str, Any]] = report["checks"]

    def check(name: str, ok: bool, **detail: Any) -> bool:
        checks.append({"name": name, "passed": bool(ok), **detail})
        return bool(ok)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    base = f"http://127.0.0.1:{listener.getsockname()[1]}"
    env = child_environment(root)
    env.update({"TABLET_WALL_UPLOAD_MODE": "loopback", "TABLET_WALL_OPERATOR_ORIGIN": base})
    log = (artifacts / "server.log").open("x")
    process = None
    resources: list[Any] = []
    owned: dict[int, str] = {}
    observations: list[Observation] = []
    playwright = None
    http = None
    error: str | None = None
    finalized = False

    def finalize() -> None:
        nonlocal finalized
        if finalized:
            return
        finalized = True
        audit_browser_issues(check, observations)
        report["checks_passed"] = sum(1 for entry in checks if entry["passed"])
        report["checks_total"] = len(checks)
        report["checks_failed"] = report["checks_total"] - report["checks_passed"]
        report["error"] = error
        report["state"] = "incomplete" if error else (
            "passed" if report["checks_passed"] == report["checks_total"] else "failed"
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
        http = httpx.Client(base_url=base, headers={"Origin": base}, timeout=30)
        deadline = time.monotonic() + 20
        while True:
            try:
                if http.get("/wall").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("video server did not become ready; see server.log")
            await asyncio.sleep(.1)
        report["origin"] = base

        clip = root / "clip.mp4"
        report["fixture"] = build_video(clip)
        upload = http.post("/uploads?name=clip.mp4", content=clip.read_bytes(),
                           headers={"Content-Type": "video/mp4"})
        check("video upload returns a ready descriptor", upload.status_code == 201,
              status=upload.status_code, text=upload.text[-500:])
        descriptor = upload.json()["asset"]
        report["descriptor"] = descriptor
        check("descriptor is a faststart H.264 yuv420p clip",
              descriptor["kind"] == "video" and descriptor["mime"] == "video/mp4"
              and descriptor["pixelFormat"] == "yuv420p" and descriptor["faststart"] is True
              and descriptor["intrinsicWidth"] == 640 and descriptor["intrinsicHeight"] == 360)

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(env={**os.environ, "TMPDIR": str(root / "tmp")})
        resources.append(browser)
        report["browser_version"] = browser.version
        owned.update(descendants(os.getpid()))
        rig = Rig(base=base, http=http, browser=browser, playwright=playwright,
                  browser_env={**os.environ, "TMPDIR": str(root / "tmp")}, root=root,
                  artifacts=artifacts, observations=observations, captured_pages=[],
                  resources=resources, owned=owned, check=check)
        pages = await open_cohort(rig, VIDEO_CLIENTS, "video")
        names = [obs.spec.name for _, obs in pages]
        assets = await calibrate_cohort(rig, pages, [mount for _, mount in VIDEO_CLIENTS],
                                        CUT_COLOURS, "video")
        cohort = {observation.device_id for _, observation in pages}
        check("the original cohort is complete before video", len(cohort) == len(pages),
              cohort=sorted(cohort), clients=len(pages))

        controller_context = await browser.new_context(viewport={"width": 1440, "height": 1000})
        resources.append(controller_context)
        editor, editor_observation = await watch_page(
            controller_context, ClientSpec("controller", 1440, 1000, 1), observations
        )
        rig.captured_pages.append((editor, editor_observation))
        await editor.goto(base + "/controller/physical.html", wait_until="networkidle")
        await editor.get_by_role("tab", name="Settings", exact=True).click()
        await editor.check("#experimental-opt-in")
        await wait_for_predicate(editor,
            "document.querySelectorAll('#playlist-library option').length > 1",
            timeout=15000,
        )
        await editor.select_option("#playlist-library", descriptor["id"])
        await editor.click("#btn-playlist-add")
        await editor.select_option("#playlist-library", assets["red"])
        await editor.click("#btn-playlist-add")
        list_text = await editor.locator("#playlist-items").inner_text()
        check("the editor adds a video and a still from the library",
              "video" in list_text.lower() and "still" in list_text.lower(), text=list_text)
        await editor.click("#btn-playlist-save")
        await wait_for_predicate(editor,
            "document.querySelector('#playlist-msg')?.textContent.toLowerCase().includes('save')",
            timeout=10000,
        )
        playlist = http.get("/api/v3/playlist").json()["playlist"]
        report["playlist"] = playlist
        check("the server sets the video dwell to its duration",
              playlist["items"][0]["dwell_ms"] == descriptor["durationMs"]
              and playlist["items"][1]["asset"] == assets["red"],
              dwell=playlist["items"][0]["dwell_ms"], duration=descriptor["durationMs"])

        await wait_for_predicate(editor,
            "!document.querySelector('#btn-playback-start').disabled", timeout=10000
        )
        editor.once("dialog", lambda dialog: dialog.accept())
        await editor.click("#btn-playback-start")
        await wait_for_predicate(editor,
            "document.querySelector('#playback-status').dataset.state === 'playing'",
            timeout=10000,
        )
        check("start from the editor reaches playing", True)
        session = http.get("/api/v3/playback").json()
        report["session"] = session
        check("a video playlist defaults to strict policy", session.get("policy") == "strict",
              policy=session.get("policy"))
        report["editor_text_playing"] = (await editor.locator("body").inner_text())[:4000]
        check("the editor shows the live video session and members",
              "playing" in report["editor_text_playing"].lower()
              and "video" in report["editor_text_playing"].lower())
        await editor.evaluate("document.querySelector('#playback-details').open = true")
        facts = await editor.locator("#playback-facts").inner_text()
        report["editor_facts_playing"] = facts
        check("the editor shows a timed anchor from the server clock",
              "anchor" in facts.lower(), facts=facts)
        summary = await editor.locator("#playback-status").inner_text()
        report["editor_summary_playing"] = summary
        live_current = (session.get("live") or {}).get("current") or {}
        check("the controller summary names the live current video",
              summary.startswith("Playing: item 1")
              and descriptor["name"] in summary
              and live_current.get("occurrence") == session.get("current")
              and live_current.get("kind") == "video",
              summary=summary, live=live_current, current=session.get("current"))
        await editor.screenshot(path=str(artifacts / "controller-playing.png"), full_page=True)

        await wait_until(
            lambda: _any_ready_video(pages),
            20, "no client ever showed a visible, ready video element",
        )
        active: dict[str, dict[str, Any]] = {}
        for (page, _), name in zip(pages, names, strict=True):
            probe = await wait_advancing(page, timeout=20, minimum_after=0.5)
            active[name] = probe
            check(name + " shows a visible advancing video", probe["ok"], **probe_details(probe))
        report["initial_active"] = active
        states = {name: await video_state(page) for (page, _), name in zip(pages, names, strict=True)}
        report["initial_video"] = states
        visible = [v for s in states.values() for v in s["videos"] if v["visible"]]
        check("the video element advertises the coded size",
              all(v["videoWidth"] == 640 and v["videoHeight"] == 360 for v in visible), states=states)
        check("the element never sets the native loop attribute",
              all(v["loop"] is False for v in visible), states=states)
        check("the controller cohort contains every original client",
              cohort_complete(http.get("/api/v3/playback").json(), pages),
              cohort=http.get("/api/v3/playback").json().get("cohort"),
              expected=sorted(cohort))
        await pages[0][0].screenshot(path=str(artifacts / "client-video.png"))

        async def sampled() -> bool:
            status = http.get("/api/v3/playback").json()
            video = status.get("video") or {}
            return len(video) >= 2 and all(entry.get("age_ms", 99999) < 3000 for entry in video.values())

        await wait_until(sampled, 15, "no fresh per-device video samples reached status")
        status = http.get("/api/v3/playback").json()
        report["status_playing"] = status
        check("status reports per-device drift with a source",
              all(entry.get("source") in ("rvfc", "time") and abs(entry.get("drift_ms", 0)) < 60000
                  for entry in status["video"].values()), video=status["video"])

        await editor.click("#btn-playback-pause")
        await wait_for_predicate(editor,
            "document.querySelector('#playback-status').dataset.state === 'paused'",
            timeout=10000,
        )
        check("pause from the editor reaches paused", True)
        await asyncio.sleep(1.2)
        paused_state = {name: await video_state(page) for (page, _), name in zip(pages, names, strict=True)}
        report["paused"] = paused_state
        check("pause freezes the video elements",
              all(v["paused"] for s in paused_state.values() for v in s["videos"] if v["visible"]), states=paused_state)

        await editor.click("#btn-playback-pause")  # the button now says Resume
        await wait_for_predicate(editor,
            "document.querySelector('#playback-status').dataset.state !== 'paused'",
            timeout=10000,
        )
        resumed: dict[str, dict[str, Any]] = {}
        for (page, _), name in zip(pages, names, strict=True):
            probe = await wait_advancing(page, timeout=20)
            resumed[name] = probe
            check(name + " advances visibly after resume", probe["ok"], **probe_details(probe))
        report["resumed"] = resumed
        check("resume from the editor advances the video",
              all(probe["ok"] for probe in resumed.values()), clients=resumed)

        async def looped() -> bool:
            current = http.get("/api/v3/playback").json().get("current")
            return bool(current and current.get("loop", 0) >= 1)

        await wait_until(looped, 20, "the video occurrence never looped")

        async def loop_displayed() -> dict[str, Any] | None:
            status = http.get("/api/v3/playback").json()
            current = status.get("current") or {}
            if (
                current.get("loop", 0) >= 1
                and status.get("displayed") == current
                and status.get("current_effective_ms") is not None
                and status.get("now_ms", 0) >= status["current_effective_ms"] + 200
            ):
                return status
            return None

        loop_wait_deadline = time.monotonic() + 20
        loop_status = None
        while time.monotonic() < loop_wait_deadline:
            loop_status = await loop_displayed()
            if loop_status is not None:
                break
            await asyncio.sleep(.05)
        if loop_status is None:
            raise RuntimeError("the looped occurrence never reached the displayed state")
        loop_active: dict[str, dict[str, Any]] = {}
        for (page, _), name in zip(pages, names, strict=True):
            probe = await wait_advancing_under(page, 2.0, timeout=15)
            loop_active[name] = probe
            check(name + " shows a visible advancing picture after the loop commit",
                  probe["ok"], **probe_details(probe))
        report["loop_active"] = loop_active
        report["looped_status"] = loop_status
        check("a loop is a new server occurrence, not native loop",
              loop_status["current"]["loop"] >= 1
              and all(probe["after"]["loop"] is False for probe in loop_active.values()),
              current=loop_status.get("current"), clients={
                  name: {"loop": probe["after"]["loop"]} for name, probe in loop_active.items()
              })

        await editor.click("#btn-playback-stop")
        await wait_for_predicate(editor,
            "document.querySelector('#playback-status').dataset.state === 'stopped'",
            timeout=10000,
        )
        check("stop from the editor reaches stopped", True)
        await asyncio.sleep(1.2)
        final = {name: await video_state(page) for (page, _), name in zip(pages, names, strict=True)}
        report["stopped"] = final
        check("stop removes the video layers",
              all(not any(v["visible"] for v in state["videos"]) for state in final.values()), states=final)
        idle = {name: await canvas_centre(page) for (page, _), name in zip(pages, names, strict=True)}
        report["idle_pixels"] = idle
        check("stop restores the persisted static scene",
              all(close_enough(pixel, CUT_COLOURS["idle"]) for pixel in idle.values()), pixels=idle)
        await pages[0][0].screenshot(path=str(artifacts / "client-after-stop.png"))

        report["editor_text"] = (await editor.locator("body").inner_text())[:4000]
        check("the physical editor renders the playback panel",
              "playback" in report["editor_text"].lower())
        await editor.screenshot(path=str(artifacts / "controller-physical.png"), full_page=True)

        for (page, observation) in rig.captured_pages:
            label = observation.spec.name + " has no horizontal clipping"
            await check_no_horizontal_clipping(check, page, label)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    finally:
        with contextlib.suppress(Exception):
            if http is not None:
                http.close()
        with contextlib.suppress(Exception):
            if playwright is not None:
                await playwright.stop()
        with contextlib.suppress(Exception):
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
        with contextlib.suppress(Exception):
            if listener is not None:
                listener.close()
        with contextlib.suppress(Exception):
            log.close()
        shutil.rmtree(root, ignore_errors=True)
        finalize()

    if report["state"] == "incomplete":
        return 2
    return 0 if report["checks_passed"] == report["checks_total"] else 1


async def _any_ready_video(pages: list[tuple[Any, Observation]]) -> bool:
    for page, _ in pages:
        state = await video_state(page)
        if any(
            video["visible"] and video["videoWidth"] > 0
            and video["readyState"] >= 2 and not video["paused"]
            for video in state["videos"]
        ):
            return True
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.artifacts)))
