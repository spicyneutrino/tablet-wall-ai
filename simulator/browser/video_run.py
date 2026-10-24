"""Real-browser R4 video evidence on a disposable server.

    .venv/bin/python -m simulator.browser.video_run --artifacts /tmp/...

This is software evidence on one host clock. It does not claim optical
synchronization, physical decode, suspend, or ingress delivery. The report
records every check and the exact argv used to build the fixture.
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
from pathlib import Path
from typing import Any

import httpx
from playwright.async_api import async_playwright

from simulator.browser.run import (
    CUT_CLIENTS,
    CUT_COLOURS,
    ClientSpec,
    Rig,
    Observation,
    calibrate_cohort,
    child_environment,
    descendants,
    open_cohort,
)

REPO = Path(__file__).resolve().parents[2]
VIDEO_SECONDS = 4
VIDEO_CLIENTS = (
    (ClientSpec("video-a", 240, 160, 1), 0),
    (ClientSpec("video-b", 200, 150, 1.25), 180),
)


def build_video(target: Path) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required for video evidence")
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


async def wait_until(predicate, timeout: float, message: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await predicate():
            return
        await asyncio.sleep(.05)
    raise RuntimeError(message)


async def video_state(page: Any) -> dict[str, Any]:
    return await page.evaluate("""() => {
        const videos = [...document.querySelectorAll('video')].map(v => {
            const rect = v.getBoundingClientRect();
            const style = getComputedStyle(v);
            return {
                visible: style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0,
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


async def main(artifacts: Path) -> int:
    artifacts.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="tw-video-", dir="/tmp"))
    for name in ("assets", "media", "tmp"):
        (root / name).mkdir()
    report: dict[str, Any] = {"checks": [], "artifacts": str(artifacts), "root": str(root)}
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
        owned.update(descendants(os.getpid()))
        rig = Rig(base=base, http=http, browser=browser, playwright=playwright,
                  browser_env={**os.environ, "TMPDIR": str(root / "tmp")}, root=root,
                  artifacts=artifacts, observations=observations, captured_pages=[],
                  resources=resources, owned=owned, check=check)
        pages = await open_cohort(rig, VIDEO_CLIENTS, "video")
        names = [obs.spec.name for _, obs in pages]
        assets = await calibrate_cohort(rig, pages, [mount for _, mount in VIDEO_CLIENTS],
                                        CUT_COLOURS, "video")

        etag = http.get("/api/v3/playlist").json()["etag"]
        saved = http.put("/api/v3/playlist", json={
            "items": [
                {"asset": descriptor["id"], "dwell_ms": 1000},
                {"asset": assets["red"], "dwell_ms": 1000},
            ],
            "loop": True,
        }, headers={"If-Match": etag})
        check("a video playlist saves", saved.status_code == 200, text=saved.text[-500:])
        playlist = saved.json()["playlist"]
        report["playlist"] = playlist
        check("the server sets the video dwell to its duration",
              playlist["items"][0]["dwell_ms"] == descriptor["durationMs"],
              dwell=playlist["items"][0]["dwell_ms"], duration=descriptor["durationMs"])

        started = http.post("/api/v3/playback/start")
        check("playback starts", started.status_code == 200, text=started.text[-500:])
        session = started.json()
        report["session"] = session
        check("a video playlist defaults to strict policy", session.get("policy") == "strict",
              policy=session.get("policy"))

        async def first_video_visible() -> bool:
            for page, _ in pages:
                state = await video_state(page)
                if any(v["visible"] and v["videoWidth"] > 0 for v in state["videos"]):
                    return True
            return False

        await wait_until(first_video_visible, 20, "no client ever showed a video element")
        states = {name: await video_state(page) for (page, _), name in zip(pages, names, strict=True)}
        report["initial_video"] = states
        visible = [v for s in states.values() for v in s["videos"] if v["visible"]]
        check("the video element advertises the coded size",
              all(v["videoWidth"] == 640 and v["videoHeight"] == 360 for v in visible), states=states)
        check("the element never sets the native loop attribute",
              all(v["loop"] is False for v in visible), states=states)

        async def advances() -> bool:
            for page, _ in pages:
                state = await video_state(page)
                if not any(v["visible"] and v["currentTime"] > .5 and not v["paused"] for v in state["videos"]):
                    return False
            return True

        await wait_until(advances, 20, "media time did not advance on both clients")
        report["playing"] = {name: await video_state(page) for (page, _), name in zip(pages, names, strict=True)}
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

        version = status["version"]
        paused = http.post("/api/v3/playback/pause", headers={"If-Match": str(version)})
        check("pause is accepted", paused.status_code == 200, text=paused.text[-500:])
        await asyncio.sleep(1.2)
        paused_state = {name: await video_state(page) for (page, _), name in zip(pages, names, strict=True)}
        report["paused"] = paused_state
        check("pause freezes the video elements",
              all(v["paused"] for s in paused_state.values() for v in s["videos"] if v["visible"]), states=paused_state)

        resumed = http.post("/api/v3/playback/start")
        check("start resumes a paused session", resumed.status_code == 200, text=resumed.text[-500:])
        await wait_until(advances, 20, "video did not advance after resume")
        report["resumed"] = {name: await video_state(page) for (page, _), name in zip(pages, names, strict=True)}

        async def looped() -> bool:
            current = http.get("/api/v3/playback").json().get("current")
            return bool(current and current.get("loop", 0) >= 1)

        await wait_until(looped, 20, "the video occurrence never looped")
        report["looped_status"] = http.get("/api/v3/playback").json()
        check("a loop is a new server occurrence, not native loop",
              report["looped_status"]["current"]["loop"] >= 1
              and all(v["loop"] is False for s in report["resumed"].values() for v in s["videos"]))

        stopped = http.post("/api/v3/playback/stop",
                            headers={"If-Match": str(http.get("/api/v3/playback").json()["version"])})
        check("stop is accepted", stopped.status_code == 200, text=stopped.text[-500:])
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

        editor = await browser.new_page(viewport={"width": 1440, "height": 1000})
        await editor.goto(base + "/controller/physical.html", wait_until="networkidle")
        await editor.wait_for_timeout(800)
        report["editor_text"] = (await editor.locator("body").inner_text())[:4000]
        check("the physical editor renders the playback panel",
              "playback" in report["editor_text"].lower())
        await editor.screenshot(path=str(artifacts / "controller-physical.png"), full_page=True)

        report["checks_passed"] = sum(1 for c in checks if c["passed"])
        report["checks_total"] = len(checks)
        (artifacts / "report.json").write_text(json.dumps(report, indent=2))
        return 0 if report["checks_passed"] == report["checks_total"] else 1
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.artifacts)))
