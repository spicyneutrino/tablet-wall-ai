"""Real-browser bounded group video recovery on a disposable server.

    .venv/bin/python -m simulator.browser.group_recovery_run --artifacts /tmp/...

One client's active video is frozen and its play promise is replaced with a
never-settling promise. Its bounded local recovery exhausts and sends a
video_fault. The server starts one group recovery at the playhead position,
both clients prepare there, and one common anchor resumes the clip. The live
controller is checked during and after the recovery; its blocked copy is
rendered from a recorded cap status, not a real blocked episode. Software
evidence only; no optical or physical claim.
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
    CUT_COLOURS,
    ClientSpec,
    Rig,
    calibrate_cohort,
    child_environment,
    descendants,
    open_cohort,
)

REPO = Path(__file__).resolve().parents[2]
SECONDS = 6
CLIENTS = (
    (ClientSpec("recover-a", 240, 160, 1), 0),
    (ClientSpec("recover-b", 200, 150, 1.25), 180),
)


def build_clip(target: Path) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required")
    argv = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=30:duration={SECONDS}",
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
        await asyncio.sleep(.1)
    raise RuntimeError(message)


async def main(artifacts: Path) -> int:
    artifacts.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="tw-recovery-", dir="/tmp"))
    for name in ("assets", "media", "tmp"):
        (root / name).mkdir()
    report: dict[str, Any] = {"checks": [], "mode": "software, not optical"}
    checks = report["checks"]

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
    http = None
    playwright = None
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
                raise RuntimeError("recovery server did not become ready")
            await asyncio.sleep(.1)

        clip = root / "clip.mp4"
        build_clip(clip)
        uploaded = http.post("/uploads?name=clip.mp4", content=clip.read_bytes(),
                             headers={"Content-Type": "video/mp4"})
        assert uploaded.status_code == 201, uploaded.text
        video = uploaded.json()["asset"]

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(env={**os.environ, "TMPDIR": str(root / "tmp")})
        rig = Rig(base=base, http=http, browser=browser, playwright=playwright,
                  browser_env={**os.environ, "TMPDIR": str(root / "tmp")}, root=root,
                  artifacts=artifacts, observations=[], captured_pages=[], resources=[],
                  owned={}, check=check)
        pages = await open_cohort(rig, CLIENTS, "recovery")
        names = [obs.spec.name for _, obs in pages]
        assets = await calibrate_cohort(rig, pages, [m for _, m in CLIENTS], CUT_COLOURS, "recovery")
        etag = http.get("/api/v3/playlist").json()["etag"]
        saved = http.put("/api/v3/playlist", json={
            "items": [{"asset": video["id"], "dwell_ms": 1000},
                      {"asset": assets["red"], "dwell_ms": 1000}],
            "loop": False,
        }, headers={"If-Match": etag})
        assert saved.status_code == 200, saved.text
        assert http.post("/api/v3/playback/start").status_code == 200

        async def playing() -> bool:
            for page, _ in pages:
                state = await page.evaluate("""() => [...document.querySelectorAll('video')]
                    .filter(v => v.getClientRects().length)
                    .map(v => ({t: v.currentTime, paused: v.paused, ready: v.readyState}))""")
                if not any(v["t"] > 1.0 and not v["paused"] and v["ready"] >= 2 for v in state):
                    return False
            return True

        await wait_until(playing, 20, "both clients did not reach playing video")
        before = http.get("/api/v3/playback").json()
        report["before"] = before
        await pages[0][0].screenshot(path=str(artifacts / "before-fault.png"))

        controller = await browser.new_page(viewport={"width": 1440, "height": 1000})
        await controller.goto(base + "/controller/physical.html", wait_until="networkidle")
        try:
            await controller.wait_for_function(
                "document.querySelector('#playback-status')?.dataset.state === 'playing'",
                timeout=15000,
            )
            controller_playing = True
        except Exception:
            controller_playing = False
        check("the controller sees the live session before the fault", controller_playing)

        froze = await pages[0][0].evaluate("""() => {
            const v = [...document.querySelectorAll('video')].find(v => v.getClientRects().length);
            if (!v) return false;
            v.__originalPlay = v.play.bind(v);
            v.play = function () { return new Promise(function () {}); };
            v.pause();
            return true;
        }""")
        check("one client's video was frozen with a hanging play promise", froze)

        async def recovered() -> bool:
            status = http.get("/api/v3/playback").json()
            return bool(status.get("recovery"))

        await wait_until(recovered, 30, "the server never started a recovery")
        status = http.get("/api/v3/playback").json()
        recovery = status["recovery"]
        report["recovery_started"] = status
        check("the server starts one recovery from a live playhead",
              recovery["reason"] in ("stalled", "play_failed", "buffer_lost")
              and 0 < recovery["position_ms"] < video["durationMs"],
              recovery=recovery)

        async def resumed() -> bool:
            for page, _ in pages:
                state = await page.evaluate("""() => [...document.querySelectorAll('video')]
                    .filter(v => v.getClientRects().length)
                    .map(v => ({t: v.currentTime, paused: v.paused, ready: v.readyState}))""")
                if not any(v["t"] >= recovery["position_ms"] / 1000 - 0.6
                           and not v["paused"] and v["ready"] >= 2 for v in state):
                    return False
            return True

        await wait_until(resumed, 30, "the group did not resume after recovery")

        async def sampled() -> bool:
            status = http.get("/api/v3/playback").json()
            video = status.get("video") or {}
            if len(video) != len(pages):
                return False
            return all(
                sample.get("age_ms", 99999) < 1500
                and sample.get("media_ms", 0) >= recovery["position_ms"] - 250
                for sample in video.values()
            )

        final = http.get("/api/v3/playback").json()
        report["after"] = final
        check("one recovery record survives the commit",
              final.get("recovery", {}).get("state") == "playing"
              and final.get("recovery", {}).get("attempts") == 1,
              recovery=final.get("recovery"))
        check("the next boundary uses the remaining duration",
              final.get("current_effective_ms") is not None
              and final.get("pending", {}).get("effective_server_ms") is not None
              and abs((final["pending"]["effective_server_ms"] - final["current_effective_ms"])
                      - (video["durationMs"] - recovery["position_ms"])) < 800,
              current=final.get("current_effective_ms"),
              pending=final.get("pending", {}).get("effective_server_ms"),
              remaining=video["durationMs"] - recovery["position_ms"])

        await wait_until(sampled, 10, "the recovered clients did not report samples")
        sampled_status = http.get("/api/v3/playback").json()
        report["after_samples"] = sampled_status.get("video")
        check("both calibrated clients show the recovered picture",
              len(sampled_status.get("video", {})) == len(pages),
              video=sampled_status.get("video"))

        try:
            await controller.wait_for_function(
                "document.querySelector('#playback-status')?.dataset.state === 'playing'",
                timeout=15000,
            )
            await controller.evaluate(
                "document.querySelector('#playback-details').open = true"
            )
            facts = await controller.locator("#playback-facts").inner_text()
        except Exception:
            facts = ""
        report["controller_facts"] = facts
        check("the controller keeps the recovery record after the commit",
              "Recovery" in facts and "attempt 1" in facts, facts=facts[:500])
        dwell = None
        for line in facts.splitlines():
            if line.strip().endswith("left") and "s left" in line:
                try:
                    dwell = float(line.strip().split()[0])
                except ValueError:
                    dwell = None
        remaining_s = (video["durationMs"] - recovery["position_ms"]) / 1000
        # A controller poll can land just before the commit anchor, so the
        # dwell may legitimately include the one-second cut lead.
        check("the controller dwell does not exceed the remainder and cut lead",
              dwell is not None and dwell <= remaining_s + 1.5,
              dwell=dwell, remainder=remaining_s, facts=facts[-300:])
        await controller.screenshot(path=str(artifacts / "controller-recovered.png"))

        blocked = {
            "state": "blocked", "now_ms": final["now_ms"],
            "blocked_reason": "recovery attempt limit reached",
            "current": final["current"], "current_effective_ms": final["current_effective_ms"],
            "pending": None, "cohort": final["cohort"],
            "recovery": {
                **final["recovery"], "state": "blocked", "attempts": 4,
                "missing": [],
            },
        }
        await controller.route(
            "**/api/v3/playback",
            lambda route: asyncio.create_task(route.fulfill(json=blocked)),
        )
        try:
            await controller.wait_for_function(
                "document.querySelector('#playback-status')?.dataset.state"
                " === 'blocked'",
                timeout=8000,
            )
            blocked_text = await controller.locator("#playback-status").inner_text()
            retry_visible = await controller.locator("#btn-playback-retry").is_visible()
        except Exception:
            blocked_text, retry_visible = "", False
        report["controller_blocked"] = blocked_text
        check("the recorded blocked status reads as one sentence and offers Retry",
              "attempt 4" in blocked_text
              and "reached. at" not in blocked_text.lower()
              and retry_visible,
              text=blocked_text, retry=retry_visible)
        await controller.screenshot(path=str(artifacts / "controller-blocked.png"))
        await controller.unroute("**/api/v3/playback")
        await controller.close()
        await pages[0][0].screenshot(path=str(artifacts / "after-recovery.png"))
        http.post("/api/v3/playback/stop",
                  headers={"If-Match": str(http.get("/api/v3/playback").json()["version"])})

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
        if not (artifacts / "report.json").exists():
            report["checks_passed"] = sum(1 for c in checks if c["passed"])
            report["checks_total"] = len(checks)
            report["error"] = "the run ended before its final check"
            (artifacts / "report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.artifacts)))
