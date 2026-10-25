"""Restore-then-play evidence for a real H.264 upload (software, not optical).

    .venv/bin/python -m simulator.browser.restore_run --artifacts /tmp/tw-restore

Starts a disposable app on temporary paths and a free loopback port, uploads
a real H.264 MP4 and a still through the operator route, saves a playlist,
backs the instance up with ``deploy/backup.py`` while it runs, restores into
brand-new paths, boots the restored copy and opens one real Chromium client.
The closure and byte checks are reported apart from the playback checks.

What this does not prove: optical output, physical decode on a tablet, Caddy
ingress, TLS, or a real host. The report label says so.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from PIL import Image
from playwright.async_api import async_playwright

from simulator.browser.run import (
    REPO,
    ClientSpec,
    child_environment,
    connected,
    wait_for_centre,
    watch_page,
)

VIDEO_SECONDS = 3
VIDEO_SIZE = (640, 360)
SPEC = ClientSpec("restore", 800, 600, 1)
LABEL = "software, not optical or physical"


def free_listener() -> socket.socket:
    """A listening socket on a free loopback port; never port 8000."""
    while True:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        if listener.getsockname()[1] != 8000:
            return listener
        listener.close()


def build_video(target: Path) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required for restore playback evidence")
    width, height = VIDEO_SIZE
    argv = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size={width}x{height}:rate=30:duration={VIDEO_SECONDS}",
        "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.0",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(target),
    ]
    done = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    if done.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + done.stderr[-2000:])
    return {"argv": argv, "bytes": target.stat().st_size}


def jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (48, 32), (20, 120, 200)).save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


class Instance:
    """One uvicorn process bound to disposable paths and a free port."""

    def __init__(self, root: Path, db: Path, assets: Path, media: Path,
                 artifacts: Path, label: str) -> None:
        self.listener = free_listener()
        self.port = self.listener.getsockname()[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.log_path = artifacts / f"{label}-server.log"
        self.env = child_environment(root)
        self.env.update({
            "TABLET_WALL_DB": str(db),
            "TABLET_WALL_ASSET_DIR": str(assets),
            "TABLET_WALL_MEDIA_DIR": str(media),
            "TABLET_WALL_UPLOAD_MODE": "loopback",
            "TABLET_WALL_OPERATOR_ORIGIN": self.base,
        })
        self.process: subprocess.Popen[bytes] | None = None
        self.http: httpx.Client | None = None
        self.log = None

    def start(self, timeout: float = 30.0) -> "Instance":
        self.log = self.log_path.open("w")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--fd",
             str(self.listener.fileno()), "--workers", "1", "--no-access-log"],
            cwd=REPO, env=self.env, pass_fds=(self.listener.fileno(),),
            stdout=self.log, stderr=subprocess.STDOUT,
        )
        self.listener.close()
        self.listener = None
        self.http = httpx.Client(
            base_url=self.base, headers={"Origin": self.base}, timeout=60
        )
        deadline = time.monotonic() + timeout
        last = "no response"
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"the app exited during startup; see {self.log_path}")
            try:
                response = self.http.get("/devices")
                if response.status_code == 200:
                    return self
                last = f"HTTP {response.status_code} {response.text[-300:]}"
            except httpx.HTTPError as error:
                last = f"{type(error).__name__}: {error}"
            time.sleep(.1)
        raise RuntimeError(
            f"the app did not become ready ({last}); see {self.log_path}"
        )

    def stop(self) -> None:
        if self.http is not None:
            self.http.close()
            self.http = None
        process, self.process = self.process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        if self.log is not None:
            self.log.close()
            self.log = None
        if self.listener is not None:
            self.listener.close()
            self.listener = None


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith("TABLET_WALL_")
    }
    return subprocess.run(
        [sys.executable, str(REPO / "deploy" / "backup.py"), *args],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=600,
    )


def must(response: httpx.Response, expected: int, what: str) -> httpx.Response:
    if response.status_code != expected:
        raise RuntimeError(f"{what}: HTTP {response.status_code} {response.text[-800:]}")
    return response


def stop_playback(http: httpx.Client) -> None:
    status = http.get("/api/v3/playback").json()
    if "version" in status:
        http.post(
            "/api/v3/playback/stop",
            headers={"If-Match": str(status["version"])},
        )


def wait_for_viewport(http: httpx.Client, device_id: str, timeout: float = 10.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = http.get("/devices").json().get(device_id)
        viewport = (record or {}).get("viewport")
        if (
            isinstance(viewport, dict)
            and abs(float(viewport.get("width", 0)) - SPEC.width) <= 1
            and abs(float(viewport.get("height", 0)) - SPEC.height) <= 1
        ):
            return record
        time.sleep(.05)
    raise RuntimeError("the client never reported its viewport")


def configure_endpoint(http: httpx.Client, device_id: str) -> None:
    """Give one registered client a display, calibration and physical slot."""
    wait_for_viewport(http, device_id)
    config = must(http.get("/api/v3/config"), 200, "config")
    etag = config.json()["etag"]
    display = must(http.put(
        f"/api/v3/displays/{device_id}",
        json={
            "active_width_mm": SPEC.width * 0.5,
            "active_height_mm": SPEC.height * 0.5,
            "bezels": {"left": 0, "top": 0, "right": 0, "bottom": 0},
            "label": "restore evidence",
            "provenance": "hand-derived",
        },
        headers={"If-Match": etag},
    ), 200, "display")
    calibration = must(http.put(
        f"/api/v3/calibrations/{device_id}",
        json={
            "profile_revision": 1,
            "viewport_width": SPEC.width,
            "viewport_height": SPEC.height,
            "dpr": SPEC.dpr,
            "orientation": 0,
            "mode": "tab",
            "quarter_turn": 0,
            "panel_offset_mm": [0, 0],
            "mm_per_css": [0.5, 0.5],
            "anchor_edge": "top-left",
            "uncertainty_mm": 0,
            "method": "hand-derived",
        },
        headers={"If-Match": display.json()["etag"]},
    ), 200, "calibration")
    must(http.put(
        "/api/v3/layout",
        json={
            "bounds": {"x": 0, "y": 0, "width": 130, "height": 120},
            "slots": {
                device_id: {
                    "center_x_mm": 75,
                    "center_y_mm": 60,
                    "mount_angle": 0,
                    "nudge_x_mm": 0,
                    "nudge_y_mm": 0,
                    "profile_revision": 1,
                    "calibration_revision": 1,
                    "participating": True,
                }
            },
        },
        headers={"If-Match": calibration.json()["etag"]},
    ), 200, "layout")


VIDEO_STATE = """() => [...document.querySelectorAll('video')].map(v => {
    const rect = v.getBoundingClientRect();
    const style = getComputedStyle(v);
    return {
        src: v.currentSrc || v.getAttribute('src') || '',
        visibility: style.visibility,
        paused: v.paused, ended: v.ended, readyState: v.readyState,
        networkState: v.networkState, currentTime: v.currentTime,
        duration: v.duration, videoWidth: v.videoWidth, videoHeight: v.videoHeight,
        error: v.error ? v.error.code : null,
        rect: {width: rect.width, height: rect.height},
    };
})"""


async def video_states(page: Any) -> list[dict[str, Any]]:
    return await page.evaluate(VIDEO_STATE)


def playing_video(states: list[dict[str, Any]]) -> dict[str, Any] | None:
    for state in states:
        if (
            state["visibility"] != "hidden"
            and state["videoWidth"] > 0
            and state["videoHeight"] > 0
            and not state["paused"]
            and not state["ended"]
            and state["currentTime"] > 0.35
        ):
            return state
    return None


async def wait_for_video(page: Any, timeout: float = 25.0) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    last: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        last = await video_states(page)
        if playing_video(last):
            return last
        await asyncio.sleep(.05)
    raise RuntimeError(f"no visible video advanced within {timeout}s: {last}")


async def playback_evidence(page: Any, http: httpx.Client, video: dict[str, Any],
                            device_id: str, check: Any, label: str) -> dict[str, Any]:
    started = http.post("/api/v3/playback/start")
    check("playback", f"{label}: playback starts", started.status_code == 200,
          status=started.status_code, text=started.text[-400:])
    if started.status_code != 200:
        return {}
    session = started.json()
    check("playback", f"{label}: a video playlist starts in strict policy",
          session.get("policy") == "strict" and session.get("cohort") == [device_id],
          policy=session.get("policy"), cohort=session.get("cohort"))

    states = await wait_for_video(page)
    first = playing_video(states)
    check("playback", f"{label}: the client decodes the video at its coded size",
          bool(first) and first["videoWidth"] == VIDEO_SIZE[0]
          and first["videoHeight"] == VIDEO_SIZE[1] and first["error"] is None,
          video=first)
    check("playback", f"{label}: the video element points at the served content id",
          bool(first) and video["url"] in first["src"], src=first and first["src"])

    before = playing_video(await video_states(page))
    await asyncio.sleep(.4)
    after = playing_video(await video_states(page))
    advanced = (
        before is not None and after is not None
        and after["currentTime"] > before["currentTime"] + .15
    )
    check("playback", f"{label}: media time advances", advanced,
          before=before, after=after)

    status = http.get("/api/v3/playback").json()
    check("playback", f"{label}: the server reports the video as the current occurrence",
          status.get("state") == "playing"
          and (status.get("current") or {}).get("item_index") == 0,
          state=status.get("state"), current=status.get("current"))
    return {"states": states, "before": before, "after": after, "session": session}


async def run(artifacts: Path, report: dict[str, Any]) -> None:
    checks = report["checks"]

    def check(group: str, name: str, ok: bool, **detail: Any) -> bool:
        checks[group].append({"name": name, "passed": bool(ok), **detail})
        return bool(ok)

    root = Path(tempfile.mkdtemp(prefix="tablet-wall-restore-", dir="/tmp"))
    source_dir, target_dir = root / "source", root / "restored"
    for path in (source_dir / "assets", source_dir / "media", root / "tmp", target_dir):
        path.mkdir(parents=True)
    source: Instance | None = None
    restored: Instance | None = None
    playwright = None
    browser = None
    contexts: list[Any] = []
    try:
        clip = root / "clip.mp4"
        report["fixture"] = build_video(clip)

        source = Instance(root, source_dir / "wall.db", source_dir / "assets",
                          source_dir / "media", artifacts, "source")
        source.start()
        http = source.http
        assert http is not None
        report["source_origin"] = source.base

        uploaded = must(http.post(
            "/uploads?name=clip.mp4", content=clip.read_bytes(),
            headers={"Content-Type": "video/mp4"},
        ), 201, "video upload")
        video = uploaded.json()["asset"]
        still_upload = must(http.post(
            "/uploads?name=still.jpg", content=jpeg(),
            headers={"Content-Type": "image/jpeg"},
        ), 201, "still upload")
        still = still_upload.json()["asset"]
        report["descriptors"] = {"source_video": video, "source_still": still}
        check("playback", "the operator route publishes a ready H.264 video",
              video.get("kind") == "video" and video.get("mime") == "video/mp4"
              and video.get("intrinsicWidth") == VIDEO_SIZE[0]
              and video.get("intrinsicHeight") == VIDEO_SIZE[1]
              and video.get("faststart") is True and video.get("bytes", 0) > 0,
              descriptor=video)
        check("closure", "the operator route publishes the still", 
              still.get("state") == "ready" and still.get("url", "").startswith("/assets/"),
              descriptor=still)

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            env={**os.environ, "TMPDIR": str(root / "tmp")}
        )
        observations: list[Any] = []
        context = await browser.new_context(
            viewport={"width": SPEC.width, "height": SPEC.height},
            device_scale_factor=SPEC.dpr,
        )
        contexts.append(context)
        page, observation = await watch_page(context, SPEC, observations)
        device_id = str(uuid.uuid4())
        await page.add_init_script(
            f"localStorage.setItem('tablet-wall-device-id', '{device_id}')"
        )
        await page.goto(source.base + "/client/")
        seen = await connected(page)
        check("playback", "a real Chromium client connects to the source", seen == device_id,
              device_id=seen)
        configure_endpoint(http, device_id)
        scene = must(http.put("/scene", json={
            "content": {"type": "image", "asset": still["id"], "fit": "cover"}
        }), 200, "scene")
        painted = await wait_for_centre(page, (20, 120, 200), 15)
        check("playback", "the calibrated client paints the still scene", painted,
              scene=scene.json().get("generation"))

        playlist_etag = http.get("/api/v3/playlist").json()["etag"]
        saved = must(http.put(
            "/api/v3/playlist",
            json={
                "items": [
                    {"asset": video["id"], "dwell_ms": 5000},
                    {"asset": still["id"], "dwell_ms": 5000},
                ],
                "loop": False,
            },
            headers={"If-Match": playlist_etag},
        ), 200, "save playlist")
        document = saved.json()["playlist"]
        report["playlist"] = document
        check("closure", "the playlist names the video and the still",
              [item["asset"] for item in document["items"]] == [video["id"], still["id"]],
              items=document["items"])
        check("closure", "the server takes the video dwell from its metadata",
              document["items"][0]["dwell_ms"] == video.get("durationMs"),
              dwell=document["items"][0]["dwell_ms"], duration=video.get("durationMs"))

        source_play = {}
        try:
            source_play = await playback_evidence(
                page, http, video, device_id, check, "source"
            )
            report["source_playback"] = source_play
        except Exception as error:
            check("playback", "the source client plays the upload before backup", False,
                  error=f"{type(error).__name__}: {error}")
        stop_playback(http)

        snapshot = root / "snapshot"
        done = run_tool(
            "backup", "--db", str(source_dir / "wall.db"),
            "--assets", str(source_dir / "assets"),
            "--media", str(source_dir / "media"), "--dest", str(snapshot),
        )
        check("closure", "deploy/backup.py exits 0 while the app runs", done.returncode == 0,
              stderr=done.stderr[-1200:])
        if done.returncode != 0:
            raise RuntimeError("backup failed")
        verified = run_tool("verify", "--src", str(snapshot))
        check("closure", "the snapshot verifies", verified.returncode == 0,
              stderr=verified.stderr[-1200:])

        manifest = json.loads((snapshot / "manifest.json").read_text())
        report["manifest"] = {
            key: manifest[key]
            for key in ("manifest_version", "schema_version", "references",
                        "media_assets", "media_objects", "omitted_media")
        }
        check("closure", "the snapshot is manifest 3 and carries the video reference",
              manifest["manifest_version"] == 3 and video["id"] in manifest["references"]
              and still["id"] in manifest["references"],
              version=manifest["manifest_version"], references=manifest["references"])
        objects = {entry["object_id"]: entry for entry in manifest["media_objects"]}
        video_object = objects.get(video["id"])
        poster_object = objects.get((video.get("poster") or {}).get("id"))
        still_object = objects.get(still["id"])
        check("closure", "the closure holds the video, its poster and the still",
              video_object is not None and poster_object is not None
              and still_object is not None and manifest["omitted_media"] == [],
              object_ids=sorted(objects), omitted=manifest["omitted_media"])
        if video_object is None or poster_object is None or still_object is None:
            raise RuntimeError("the snapshot closure does not name the uploaded objects")
        check("closure", "the video object's manifest digest and size match its descriptor",
              video_object["mime"] == "video/mp4"
              and video_object["sha256"] == video["id"].split(":", 1)[1]
              and video_object["bytes"] == video["bytes"],
              entry=video_object)

        source.stop()
        source = None

        done = run_tool(
            "restore", "--src", str(snapshot), "--db", str(target_dir / "wall.db"),
            "--assets", str(target_dir / "assets"), "--media", str(target_dir / "media"),
        )
        check("closure", "deploy/backup.py restore exits 0 into fresh targets",
              done.returncode == 0, stderr=done.stderr[-1200:])
        if done.returncode != 0:
            raise RuntimeError("restore failed")
        again = run_tool(
            "restore", "--src", str(snapshot), "--db", str(target_dir / "wall.db"),
            "--assets", str(target_dir / "assets"), "--media", str(target_dir / "media"),
        )
        check("closure", "restore refuses to overwrite its targets", again.returncode == 1,
              stderr=again.stderr[-400:])

        source_bytes = (source_dir / video_object["path"]).read_bytes()
        snapshot_bytes = (snapshot / video_object["path"]).read_bytes()
        restored_bytes = (target_dir / video_object["path"]).read_bytes()
        check("bytes", "source, snapshot and restored video objects are byte-identical",
              source_bytes == snapshot_bytes == restored_bytes,
              bytes=len(restored_bytes))
        check("bytes", "the restored object still hashes to its content id",
              hashlib.sha256(restored_bytes).hexdigest() == video["id"].split(":", 1)[1])
        check("bytes", "the poster bytes survived the round trip",
              (target_dir / poster_object["path"]).read_bytes()
              == (source_dir / poster_object["path"]).read_bytes())
        check("bytes", "the still bytes survived the round trip",
              (target_dir / still_object["path"]).read_bytes()
              == (source_dir / still_object["path"]).read_bytes())

        restored = Instance(root, target_dir / "wall.db", target_dir / "assets",
                            target_dir / "media", artifacts, "restored")
        restored.start()
        report["restored_origin"] = restored.base
        library = must(restored.http.get("/media"), 200, "restored library").json()["assets"]
        entry = next((item for item in library if item.get("id") == video["id"]), None)
        check("playback", "the restored library resolves the video descriptor",
              entry is not None and entry.get("state") == "ready"
              and entry.get("kind") == "video" and entry.get("bytes") == video["bytes"]
              and entry.get("intrinsicWidth") == video["intrinsicWidth"]
              and entry.get("intrinsicHeight") == video["intrinsicHeight"]
              and entry.get("durationMs") == video["durationMs"]
              and entry.get("codec") == video["codec"],
              descriptor=entry)
        report["descriptors"]["restored_video"] = entry

        restored_playlist = restored.http.get("/api/v3/playlist").json()["playlist"]
        check("closure", "the restored playlist is identical",
              restored_playlist.get("items") == document["items"]
              and restored_playlist.get("loop") == document["loop"],
              playlist=restored_playlist)

        whole = restored.http.get(video["url"])
        check("bytes", "the restored app serves the whole video",
              whole.status_code == 200
              and len(whole.content) == video["bytes"]
              and hashlib.sha256(whole.content).hexdigest() == video["id"].split(":", 1)[1],
              status=whole.status_code, bytes=len(whole.content))
        first = restored.http.get(video["url"], headers={"Range": "bytes=0-99"})
        check("bytes", "the restored app serves a byte range from the same bytes",
              first.status_code == 206
              and first.content == restored_bytes[:100]
              and first.headers.get("content-range") == f"bytes 0-99/{video['bytes']}",
              status=first.status_code, content_range=first.headers.get("content-range"))
        tail = restored.http.get(video["url"], headers={"Range": "bytes=-64"})
        check("bytes", "the restored app serves a suffix range",
              tail.status_code == 206 and tail.content == restored_bytes[-64:],
              status=tail.status_code)
        head = restored.http.head(video["url"])
        check("bytes", "the restored app answers HEAD with the full length",
              head.status_code == 200 and head.content == b""
              and head.headers.get("content-length") == str(video["bytes"]),
              status=head.status_code, length=head.headers.get("content-length"))
        poster = restored.http.get((video.get("poster") or {}).get("url", ""))
        check("bytes", "the restored app serves the poster",
              poster.status_code == 200
              and hashlib.sha256(poster.content).hexdigest()
              == poster_object["object_id"].split(":", 1)[1],
              status=poster.status_code)
        still_served = restored.http.get(still["url"])
        check("bytes", "the restored app serves the still",
              still_served.status_code == 200
              and hashlib.sha256(still_served.content).hexdigest()
              == still["id"].split(":", 1)[1],
              status=still_served.status_code)

        context = await browser.new_context(
            viewport={"width": SPEC.width, "height": SPEC.height},
            device_scale_factor=SPEC.dpr,
        )
        contexts.append(context)
        page, observation = await watch_page(
            context, ClientSpec("restore-restored", SPEC.width, SPEC.height, SPEC.dpr),
            observations,
        )
        await page.add_init_script(
            f"localStorage.setItem('tablet-wall-device-id', '{device_id}')"
        )
        await page.goto(restored.base + "/client/")
        seen = await connected(page)
        check("playback", "a fresh Chromium client reconnects to the restored app with the "
                          "restored identity", seen == device_id, device_id=seen)

        try:
            report["restored_playback"] = await playback_evidence(
                page, restored.http, video, device_id, check, "restored"
            )
            await page.screenshot(path=str(artifacts / "restored-video.png"))
        except Exception as error:
            check("playback", "the restored client plays the restored video", False,
                  error=f"{type(error).__name__}: {error}")
        stop_playback(restored.http)

        asset_events = [
            event for event in observation.events
            if event["kind"] == "http" and "/assets/" in event["url"]
        ]
        video_events = [event for event in asset_events if video["id"] in event["url"]]
        failures = [
            event for event in observation.events
            if event["kind"] == "request_failed" and video["id"] in event["url"]
        ]
        report["network"] = {
            "asset_responses": asset_events,
            "video_responses": video_events,
            "video_request_failures": failures,
        }
        check("playback", "the restored client fetched the video from the restored origin",
              any(event["url"].startswith(restored.base + video["url"])
                  for event in video_events),
              urls=[event["url"] for event in video_events])
        check("playback", "the restored video request succeeded and never 404'd",
              any(event["status"] in (200, 206) for event in video_events)
              and all(event["status"] != 404 for event in video_events)
              and not failures,
              statuses=[event["status"] for event in video_events], failures=failures)
        check("playback", "no asset request on the restored client returned 404",
              all(event["status"] != 404 for event in asset_events),
              asset_responses=asset_events)
    finally:
        for context in contexts:
            try:
                await context.close()
            except Exception:
                pass
        if browser is not None:
            await browser.close()
        if playwright is not None:
            await playwright.stop()
        if source is not None:
            source.stop()
        if restored is not None:
            restored.stop()
        shutil.rmtree(root, ignore_errors=True)


def summarize(report: dict[str, Any]) -> None:
    checks = report["checks"]
    total = sum(len(rows) for rows in checks.values())
    passed = sum(1 for rows in checks.values() for row in rows if row["passed"])
    report["summary"] = {
        "checks_passed": passed,
        "checks_total": total,
        "passed": passed == total and not report.get("error"),
    }


async def main(artifacts: Path) -> int:
    artifacts = artifacts.expanduser().resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "label": LABEL,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "artifacts": str(artifacts),
        "checks": {"closure": [], "bytes": [], "playback": []},
        "limitations": [
            "software evidence on one host clock; not optical output",
            "no physical decode, tablet, TLS, Caddy ingress or host restart",
        ],
    }
    try:
        await run(artifacts, report)
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        report["checks"]["playback"].append({
            "name": "the run completed without an exception",
            "passed": False,
            "error": report["error"],
        })
        traceback.print_exc()
    summarize(report)
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    (artifacts / "report.json").write_text(json.dumps(report, indent=2))
    summary = report["summary"]
    print(f"restore-run: {summary['checks_passed']}/{summary['checks_total']} checks passed")
    for group, rows in report["checks"].items():
        for row in rows:
            if not row["passed"]:
                print(f"FAIL {group}: {row['name']} {row.get('error', '')}".rstrip())
    print(f"report: {artifacts / 'report.json'}")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    raise SystemExit(asyncio.run(main(parser.parse_args().artifacts)))
