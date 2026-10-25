"""Real-browser bounded group video recovery on a disposable server.

    .venv/bin/python -m simulator.browser.group_recovery_run --artifacts /tmp/...

One client's active video is frozen and its play promise is replaced with a
never-settling promise. Its bounded local recovery exhausts and sends a
video_fault. The server starts one group recovery at the playhead position,
both clients prepare there, and one common anchor resumes the clip. The
runner then waits for the real following cut and verifies both members show
the still, not only that a scheduled timestamp passed.

Every original cohort member must have a computed-visible picture that
advances (computed visibility, opacity, size, readyState and two samples).
Unexpected page errors, console errors, warnings and failed requests fail the
run; only the warnings produced by the deliberate hung play are classified as
intentional. The controller's blocked copy is rendered from a recorded cap
status; it is labelled fixture-rendered and is never counted as a live
transition. Software evidence only; no optical or physical claim.
"""

from __future__ import annotations

import argparse
import asyncio
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
    open_cohort,
)

REPO = Path(__file__).resolve().parents[2]
RUNNER = "group-recovery/2"
EVIDENCE_KIND = "software-browser"
SECONDS = 6
CLIENTS = (
    (ClientSpec("recover-a", 240, 160, 1), 0),
    (ClientSpec("recover-b", 200, 150, 1.25), 180),
)

# Only the warnings our deliberate hung play produces are tolerated. Any
# other warning is unexpected and fails the run, like an error.
HUNG_PLAY_WARNING = re.compile(
    r"\[tablet-wall\] video (?:recovery \d+|blocked after \d+ recoveries"
    r"|fault [a-z_]+ at \d+ ms)"
)

VIDEO_STATE_JS = """() => {
    const describe = (element) => {
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        const opacity = Number(style.opacity);
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
    const videos = [...document.querySelectorAll('video')].map((v) => ({
        src: v.currentSrc || v.src || '',
        t: Number(v.currentTime),
        paused: v.paused,
        ended: v.ended,
        ready: Number(v.readyState),
        error: v.error ? v.error.code : null,
        ...describe(v),
    }));
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
            /* Read back through a one-pixel probe created with
             * willReadFrequently so the measurement does not add a
             * Canvas2D console warning of its own. */
            const probe = document.createElement('canvas');
            probe.width = 1;
            probe.height = 1;
            const probeContext = probe.getContext(
                '2d', {willReadFrequently: true});
            probeContext.drawImage(
                canvas,
                Math.floor(canvas.width / 2),
                Math.floor(canvas.height / 2), 1, 1, 0, 0, 1, 1);
            pixel = Array.from(probeContext.getImageData(0, 0, 1, 1).data);
        } catch (error) {
            pixel = null;
        }
    }
    return {videos, canvasVisible, pixel};
}"""


def repository_state() -> dict[str, Any]:
    """Head, branch and dirty state for the report, without fetching."""
    def run(*args: str) -> str:
        done = subprocess.run(
            ["git", "-C", str(REPO), *args],
            capture_output=True, text=True, timeout=15,
        )
        return done.stdout.strip()

    return {
        "head": run("rev-parse", "HEAD"),
        "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(run("status", "--porcelain")),
    }


def build_clip(target: Path, seconds: int = SECONDS) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required")
    argv = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=30:duration={seconds}",
        "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.0",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(target),
    ]
    done = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    if done.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + done.stderr[-2000:])
    return {"argv": argv, "bytes": target.stat().st_size}


async def wait_until(predicate, timeout: float, message: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if asyncio.iscoroutine(result):
            result = await result
        if result:
            return
        await asyncio.sleep(.1)
    raise RuntimeError(message)


async def video_state(page: Any) -> dict[str, Any]:
    return await page.evaluate(VIDEO_STATE_JS)


def visible_videos(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [video for video in state.get("videos", []) if video.get("visible")]


def primary_video(state: dict[str, Any]) -> dict[str, Any] | None:
    visible = visible_videos(state)
    if not visible:
        return None
    return max(visible, key=lambda video: (video.get("t", 0), video.get("width", 0)))


def console_violations(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Unexpected page errors, console errors/warnings and request failures."""
    violations = []
    for event in events:
        kind = event.get("kind")
        if kind == "page_error":
            violations.append({"kind": kind, "text": event.get("text", "")})
        elif kind == "request_failed":
            violation = {
                "kind": kind,
                "url": event.get("url", ""),
                "error": event.get("error", ""),
            }
            violations.append(violation)
        elif kind == "console":
            level = event.get("level")
            text = str(event.get("text", ""))
            if level == "error":
                violations.append({"kind": kind, "level": level, "text": text})
            elif level in ("warning", "warn") and not HUNG_PLAY_WARNING.search(text):
                violations.append({"kind": kind, "level": level, "text": text})
    return violations


def prepare_frames(observation: Any) -> list[dict[str, Any]]:
    """Every prepare frame this client actually received, in wire order."""
    return [
        event["frame"] for event in observation.events
        if event.get("kind") == "ws_received"
        and isinstance(event.get("frame"), dict)
        and event["frame"].get("type") == "prepare"
    ]


def displayed_index(status: dict[str, Any]) -> int | None:
    displayed = status.get("displayed") or status.get("current")
    return displayed.get("item_index") if isinstance(displayed, dict) else None


async def main(artifacts: Path) -> int:
    artifacts = artifact_directory(artifacts)
    root = Path(tempfile.mkdtemp(prefix="tw-recovery-", dir="/tmp"))
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
        "fixture_checks": [],
    }
    checks = report["checks"]
    started = time.monotonic()

    def check(name: str, ok: bool, evidence: str = "live", **detail: Any) -> bool:
        entry = {"name": name, "passed": bool(ok), "evidence": evidence, **detail}
        checks.append(entry)
        if evidence != "live":
            report["fixture_checks"].append(entry)
        return bool(ok)

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
    pages: list[tuple[Any, Any]] = []

    def write_report() -> None:
        live = [item for item in checks if item["evidence"] == "live"]
        fixture = [item for item in checks if item["evidence"] != "live"]
        report["checks_passed"] = sum(1 for item in live if item["passed"])
        report["checks_total"] = len(live)
        report["fixture_checks_passed"] = sum(1 for item in fixture if item["passed"])
        report["fixture_checks_total"] = len(fixture)
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
        report["clip"] = build_clip(clip)
        uploaded = http.post("/uploads?name=clip.mp4", content=clip.read_bytes(),
                             headers={"Content-Type": "video/mp4"})
        assert uploaded.status_code == 201, uploaded.text
        video = uploaded.json()["asset"]

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            env={**os.environ, "TMPDIR": str(root / "tmp")}
        )
        report["browser_version"] = browser.version
        rig = Rig(base=base, http=http, browser=browser, playwright=playwright,
                  browser_env={**os.environ, "TMPDIR": str(root / "tmp")},
                  root=root, artifacts=artifacts, observations=[],
                  captured_pages=[], resources=[], owned={}, check=check)
        pages = await open_cohort(rig, CLIENTS, "recovery")
        assets = await calibrate_cohort(
            rig, pages, [mount for _, mount in CLIENTS], CUT_COLOURS, "recovery"
        )
        etag = http.get("/api/v3/playlist").json()["etag"]
        saved = http.put("/api/v3/playlist", json={
            "items": [{"asset": video["id"], "dwell_ms": 1000},
                      {"asset": assets["red"], "dwell_ms": 1000}],
            "loop": False,
        }, headers={"If-Match": etag})
        assert saved.status_code == 200, saved.text
        assert http.post("/api/v3/playback/start").status_code == 200

        async def both_playing(minimum: float = .2) -> bool:
            for page, _ in pages:
                state = await video_state(page)
                visible = visible_videos(state)
                if not any(
                    video["t"] >= minimum
                    and not video["paused"]
                    and video["ready"] >= 2
                    for video in visible
                ):
                    return False
            return True

        await wait_until(both_playing, 20, "both clients did not reach playing video")

        async def advancing(interval: float = .7) -> list[dict[str, Any]]:
            first = [primary_video(await video_state(page)) for page, _ in pages]
            await asyncio.sleep(interval)
            second = [primary_video(await video_state(page)) for page, _ in pages]
            rows = []
            for (page, observation), before, after in zip(pages, first, second):
                row = {
                    "device": observation.device_id,
                    "before": before,
                    "after": after,
                    "delta_s": (
                        round(after["t"] - before["t"], 3)
                        if before and after else None
                    ),
                }
                rows.append(row)
            return rows

        rows = await advancing()
        report["before_advance"] = rows
        check(
            "every original cohort member shows a visible advancing video before the fault",
            all(
                row["before"] and row["after"]
                and row["before"]["visible"] and row["after"]["visible"]
                and row["before"]["opacity"] > .05
                and row["before"]["width"] > 1 and row["before"]["height"] > 1
                and not row["after"]["paused"] and row["after"]["ready"] >= 2
                and (row["delta_s"] or 0) >= .15
                for row in rows
            ),
            rows=rows,
        )
        before = http.get("/api/v3/playback").json()
        report["before"] = before
        check("the session reports every cohort member playing",
              before.get("state") == "playing"
              and len(before.get("video", {})) == len(pages),
              state=before.get("state"), video=before.get("video"))
        await pages[0][0].screenshot(path=str(artifacts / "before-fault.png"))

        controller = await browser.new_page(viewport={"width": 1440, "height": 1000})
        controller_events: list[dict[str, Any]] = []
        controller.on("pageerror", lambda error: controller_events.append(
            {"kind": "page_error", "text": str(error)}))
        controller.on("console", lambda message: controller_events.append(
            {"kind": "console", "level": message.type, "text": message.text}))
        controller.on("requestfailed", lambda request: controller_events.append(
            {"kind": "request_failed", "url": request.url,
             "error": request.failure}))
        await controller.goto(base + "/controller/physical.html",
                              wait_until="networkidle")
        await controller.click("#tab-show")
        await controller.wait_for_function(
            "() => document.querySelector('#panel-show')?.hidden === false",
            timeout=5000,
        )
        try:
            await controller.wait_for_function(
                "document.querySelector('#playback-status')?.dataset.state"
                " === 'playing'", timeout=15000,
            )
            controller_playing = True
        except Exception:
            controller_playing = False
        check("the controller sees the live session before the fault",
              controller_playing)

        froze = await pages[0][0].evaluate("""() => {
            const v = [...document.querySelectorAll('video')]
                .find(v => getComputedStyle(v).visibility !== 'hidden'
                    && v.getBoundingClientRect().width > 1);
            if (!v) return false;
            v.__originalPlay = v.play.bind(v);
            v.play = function () { return new Promise(function () {}); };
            v.pause();
            return true;
        }""")
        check("one client's video was frozen with a hanging play promise", froze)

        async def recovered() -> bool:
            return bool(http.get("/api/v3/playback").json().get("recovery"))

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
                state = await video_state(page)
                if not any(
                    video["t"] >= recovery["position_ms"] / 1000 - .6
                    and not video["paused"] and video["ready"] >= 2
                    for video in visible_videos(state)
                ):
                    return False
            return True

        await wait_until(resumed, 30, "the group did not resume after recovery")
        rows = await advancing()
        report["after_advance"] = rows
        check(
            "both clients visibly advance after one common recovery anchor",
            all(
                row["before"] and row["after"]
                and row["before"]["visible"] and row["after"]["visible"]
                and not row["after"]["paused"] and row["after"]["ready"] >= 2
                and (row["delta_s"] or 0) >= .15
                for row in rows
            ),
            rows=rows,
        )
        for (page, observation), row in zip(pages, rows):
            check(
                f"{observation.spec.name}: the recovered picture is visible at "
                "computed visibility, opacity and size",
                bool(row["before"])
                and row["before"]["visibility"] == "visible"
                and row["before"]["display"] != "none"
                and row["before"]["opacity"] > .05
                and row["before"]["width"] > 1 and row["before"]["height"] > 1,
                row=row,
            )

        async def sampled() -> bool:
            state = http.get("/api/v3/playback").json().get("video") or {}
            if len(state) != len(pages):
                return False
            return all(
                sample.get("age_ms", 99999) < 1500
                and sample.get("media_ms", 0) >= recovery["position_ms"] - 250
                for sample in state.values()
            )

        await wait_until(sampled, 10, "the recovered clients did not report samples")
        sampled_status = http.get("/api/v3/playback").json()
        report["after_samples"] = sampled_status.get("video")
        check("both calibrated clients report fresh samples after recovery",
              len(sampled_status.get("video", {})) == len(pages),
              video=sampled_status.get("video"))

        final = http.get("/api/v3/playback").json()
        report["after"] = final
        recovery_id = final.get("recovery", {}).get("id")
        check("one recovery record survives the commit",
              final.get("recovery", {}).get("state") == "playing"
              and final.get("recovery", {}).get("attempts") == 1,
              recovery=final.get("recovery"))
        check("the recorded recovery id is the wire recovery id",
              bool(recovery_id)
              and all(
                  sum(1 for frame in prepare_frames(observation)
                      if frame.get("recovery_id") == recovery_id) >= 1
                  for _, observation in pages
              ),
              recovery_id=recovery_id,
              prepares=[
                  {
                      "device": observation.device_id,
                      "recovery_frames": [
                          frame.get("recovery_id")
                          for frame in prepare_frames(observation)
                          if frame.get("recovery_id")
                      ],
                  }
                  for _, observation in pages
              ])
        check("the next boundary uses the remaining duration",
              final.get("current_effective_ms") is not None
              and final.get("pending", {}).get("effective_server_ms") is not None
              and abs(
                  (final["pending"]["effective_server_ms"]
                   - final["current_effective_ms"])
                  - (video["durationMs"] - recovery["position_ms"])
              ) < 800,
              current=final.get("current_effective_ms"),
              pending=final.get("pending", {}).get("effective_server_ms"),
              remaining=video["durationMs"] - recovery["position_ms"])

        try:
            await controller.wait_for_function(
                "document.querySelector('#playback-status')?.dataset.state"
                " === 'playing'", timeout=15000,
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

        # Wait for the *actual* following cut, not its scheduled timestamp.
        scheduled_cut = (http.get("/api/v3/playback").json()
                         .get("pending") or {}).get("effective_server_ms")

        async def following_cut() -> bool:
            return _following_cut_due(http)

        await wait_until(
            following_cut,
            max(5.0, ((scheduled_cut or 0) - final["now_ms"]) / 1000 + 8),
            "the following cut never reached the glass",
        )
        cut_status = http.get("/api/v3/playback").json()
        report["following_cut"] = cut_status
        cut_latency = (None if scheduled_cut is None
                       else cut_status["now_ms"] - scheduled_cut)
        check("the following cut is the second playlist item on the glass",
              displayed_index(cut_status) == 1
              and cut_status["now_ms"] >= cut_status["current_effective_ms"],
              displayed=cut_status.get("displayed"),
              current=cut_status.get("current"),
              now_ms=cut_status.get("now_ms"),
              effective=cut_status.get("current_effective_ms"))
        check("the actual cut lands inside the tolerated commit window",
              cut_latency is not None and -500 <= cut_latency <= 4000,
              scheduled_ms=scheduled_cut, observed_ms=cut_status.get("now_ms"),
              latency_ms=cut_latency)

        async def still_visible() -> bool:
            for page, _ in pages:
                state = await video_state(page)
                if visible_videos(state):
                    return False
                if not state.get("canvasVisible"):
                    return False
                pixel = state.get("pixel") or []
                if len(pixel) < 3 or pixel[0] < 140 or pixel[1] > 100 or pixel[2] > 100:
                    return False
            return True

        await wait_until(still_visible, 8,
                         "both clients did not show the red still after the cut")
        cut_states = [await video_state(page) for page, _ in pages]
        cut_pixels = [
            {"device": observation.device_id,
             "pixel": state.get("pixel"),
             "videos": state.get("videos")}
            for (page, observation), state in zip(pages, cut_states)
        ]
        report["cut_pixels"] = cut_pixels
        check("both clients show the red still with no visible video",
              all(not item["videos"] or not visible_videos(item["videos"])
                  for item in cut_pixels)
              and all((item["pixel"] or [0])[0] > 140 for item in cut_pixels),
              pixels=cut_pixels)
        await pages[0][0].screenshot(path=str(artifacts / "after-cut.png"))
        await pages[1][0].screenshot(path=str(artifacts / "after-cut-b.png"))

        # Fixture-rendered copy of the cap presentation. This is deliberately
        # not evidence of a live blocked transition; the live cap lives in
        # recovery_acceptance_run.
        blocked = {
            "state": "blocked", "now_ms": cut_status["now_ms"],
            "blocked_reason": "recovery attempt limit reached",
            "current": final["current"],
            "current_effective_ms": final["current_effective_ms"],
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
                " === 'blocked'", timeout=8000,
            )
            blocked_text = await controller.locator("#playback-status").inner_text()
            retry_visible = await controller.locator("#btn-playback-retry").is_visible()
        except Exception:
            blocked_text, retry_visible = "", False
        report["controller_blocked"] = blocked_text
        check("recorded-cap fixture copy reads as one sentence and offers Retry",
              "attempt 4" in blocked_text
              and "reached. at" not in blocked_text.lower()
              and retry_visible,
              evidence="fixture-rendered",
              text=blocked_text, retry=retry_visible)
        await controller.screenshot(path=str(artifacts / "controller-blocked-fixture.png"))
        await controller.unroute("**/api/v3/playback")

        # Unexpected client console/page/request errors; only the deliberate
        # hung play warnings are classified as intentional.
        events = [
            event for _, observation in pages for event in observation.events
        ] + controller_events
        violations = console_violations(events)
        report["console_violations"] = violations
        check("no unexpected client page, console or request errors",
              not violations, violations=violations)

        http.post("/api/v3/playback/stop",
                  headers={"If-Match": str(http.get("/api/v3/playback").json()["version"])})
        report["state"] = (
            "complete"
            if all(item["passed"] for item in checks)
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


def _following_cut_due(http: httpx.Client) -> bool:
    """Committed and promoted second occurrence, past its real commit time."""
    status = http.get("/api/v3/playback").json()
    if displayed_index(status) != 1:
        return False
    effective = status.get("current_effective_ms")
    return (
        status.get("now_ms") is not None
        and effective is not None
        and status["now_ms"] >= effective + 200
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.artifacts)))
