"""Desktop smoke for the standalone device decode/suspend probe.

Builds a 10 s H.264 fixture with a burned-in frame counter and time, serves the
probe page from an isolated loopback static server, and drives it in desktop
Chromium and WebKit (when Playwright can launch WebKit). The run captures the
probe JSON, browser versions, console/page errors and the clip hash, then writes
a report through ``tools.validation.evidence``.

This proves the probe page works in desktop engines. It does not prove physical
tablet decode, suspend, decoder freeze, low-memory termination or iOS Safari.
"""

from __future__ import annotations

import argparse
import asyncio
import colorsys
import importlib.metadata
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from simulator.browser.run import artifact_directory  # noqa: E402
from tools.validation import evidence  # noqa: E402

PROBE_DIR = REPO / "tools" / "device_probe"
PROBE_INDEX = PROBE_DIR / "index.html"
PROBE_JS = PROBE_DIR / "probe.js"

RUNNER = "decode-probe/1"
TOOL_VERSION = "1"
CLIP_SECONDS = 10
CLIP_FPS = 30
CLIP_WIDTH = 640
CLIP_HEIGHT = 360
CLIP_FRAMES = CLIP_SECONDS * CLIP_FPS
H264_CODEC = "mp4_h264_baseline"
ENGINE_ORDER = ("chromium", "webkit")
IOS_SCENARIO = "ios-safari"
IOS_DETAIL = "iOS Safari requires operator hardware; desktop WebKit is not iOS Safari."
VIEWPORT = {"width": 1280, "height": 720}
DEVICE_SCALE_FACTOR = 1

READY_JS = "() => window.__deviceProbeReady === true && !!window.__deviceProbe"
PLAYING_JS = (
    "() => { const s = window.__deviceProbe && window.__deviceProbe.state();"
    " return !!(s && s.playing && s.frames >= 5 && s.playOutcome === 'resolved'); }"
)
RUNNING_JS = (
    "() => { const s = window.__deviceProbe && window.__deviceProbe.state();"
    " return !!(s && s.playing && s.frames >= 5); }"
)

LIMITATIONS = [
    "Desktop engines only. This run does not prove physical tablet decode, "
    "suspend, loop or recovery behaviour.",
    "Not iOS Safari. Playwright WebKit on Linux is desktop WebKit, not an iOS "
    "device, Safari build or iOS media stack.",
    "No decoder-freeze induction, low-memory termination, app switch, "
    "lock/unlock or independent camera recording. Those are operator steps.",
    "Headless wake-lock and fullscreen state do not represent tablet kiosk "
    "behaviour and are recorded, not exercised as acceptance.",
    "The fixture is synthetic and burned-in. It validates the probe, not a "
    "panel, decoder, compositor or camera.",
]

UNOBSERVED = [
    "app switch / home-screen round trip",
    "device lock and unlock",
    "low-memory termination and operator reload",
    "decoder-freeze induction",
    "independent camera recording",
    "iOS Safari",
    "physical tablet decode, suspend and wake lock",
]


class UnsupportedEngine(RuntimeError):
    """The optional desktop engine cannot run here; it is not a probe failure."""


@lru_cache(maxsize=1)
def probe_contract() -> dict[str, Any]:
    """Read the page contract embedded in index.html (single source of truth)."""
    text = PROBE_INDEX.read_text()
    match = re.search(
        r'<script type="application/json" id="probe-contract">(.*?)</script>',
        text,
        re.DOTALL,
    )
    if not match:
        raise RuntimeError("probe contract block is missing from index.html")
    return json.loads(match.group(1))


def field_value(payload: dict[str, Any], path: str) -> tuple[Any, bool]:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None, False
        current = current[part]
    return current, True


def payload_problems(
    payload: dict[str, Any], contract: dict[str, Any] | None = None,
) -> list[str]:
    """Contract gaps that make the captured page log unusable."""
    contract = contract or probe_contract()
    problems: list[str] = []
    for path in contract["required_payload_fields"]:
        _, present = field_value(payload, path)
        if not present:
            problems.append(f"missing payload field: {path}")

    events = payload.get("media_events")
    names = {
        row.get("name")
        for row in events or []
        if isinstance(row, dict)
    } if isinstance(events, list) else set()
    for name in contract["core_media_events"]:
        if name not in names:
            problems.append(f"core media event not observed: {name}")

    frames = payload.get("frame_callbacks") or {}
    if frames.get("supported"):
        if not frames.get("count"):
            problems.append("requestVideoFrameCallback supported but no callbacks recorded")
        rows = frames.get("rows") or []
        if rows and isinstance(rows[0], dict):
            metadata = rows[0].get("metadata")
            if not isinstance(metadata, dict):
                problems.append("frame callback metadata object is missing")
                metadata = rows[0]
            for key in contract["required_frame_metadata"]:
                if key not in metadata:
                    problems.append(f"frame callback metadata field missing: {key}")
                elif metadata.get(key) is None:
                    problems.append(f"frame callback metadata field is null: {key}")
    return problems


def source_problems(payload: dict[str, Any], clip: dict[str, Any]) -> list[str]:
    source = payload.get("source") or {}
    problems: list[str] = []
    if source.get("sha256") != clip["sha256"]:
        problems.append("source sha256 does not match the generated clip")
    if source.get("size") != clip["bytes"]:
        problems.append("source size does not match the generated clip")
    if source.get("name") != clip["name"]:
        problems.append("source name does not match the generated clip")
    if not source.get("media"):
        problems.append("source media metadata was not reported")
    return problems


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # older Pillow: bitmap default font
        return ImageFont.load_default()


def _clip_frame(
    index: int,
    big: ImageFont.ImageFont,
    mid: ImageFont.ImageFont,
    small: ImageFont.ImageFont,
) -> Image.Image:
    image = Image.new("RGB", (CLIP_WIDTH, CLIP_HEIGHT), (12, 17, 23))
    draw = ImageDraw.Draw(image)
    phase = index / max(1, CLIP_FRAMES - 1)
    hue = (index % 120) / 120.0
    red, green, blue = colorsys.hsv_to_rgb(hue, 0.55, 0.40)
    tint = (int(red * 255), int(green * 255), int(blue * 255))

    draw.rectangle((0, 0, int(CLIP_WIDTH * phase), 8), fill=(98, 211, 164))
    draw.rectangle((24, 22, 330, 150), fill=(0, 0, 0))
    draw.text((40, 30), f"FRAME {index:04d}", font=big, fill=(255, 255, 255))
    draw.text((40, 112), f"{index / CLIP_FPS:07.3f} s", font=mid, fill=(255, 214, 102))

    draw.text(
        (CLIP_WIDTH // 2, CLIP_HEIGHT // 2),
        f"{index:04d}",
        font=big,
        anchor="mm",
        fill=tint,
    )

    draw.rectangle((0, CLIP_HEIGHT - 58, CLIP_WIDTH, CLIP_HEIGHT), fill=(22, 30, 40))
    draw.text(
        (24, CLIP_HEIGHT - 47),
        "tablet-wall decode probe  |  10 s  |  30 fps  |  H.264",
        font=small,
        fill=(188, 203, 217),
    )
    draw.rectangle(
        (0, CLIP_HEIGHT - 6, int(CLIP_WIDTH * phase), CLIP_HEIGHT),
        fill=(98, 211, 164),
    )
    return image


def _ffprobe(path: Path) -> dict[str, Any]:
    done = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries",
            "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames",
            "-show_entries", "format=duration",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, timeout=60,
    )
    if done.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {done.stderr.strip()[-800:]}")
    data = json.loads(done.stdout)
    streams = data.get("streams") or []
    if not streams:
        raise RuntimeError("ffprobe reported no video stream")
    stream = streams[0]
    rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1"
    numerator, _, denominator = rate.partition("/")
    fps = float(numerator) / float(denominator) if denominator and float(denominator) else None
    frames_value = str(stream.get("nb_frames") or "")
    return {
        "codec": stream.get("codec_name"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "fps": round(fps, 3) if fps else None,
        "frames": int(frames_value) if frames_value.isdigit() else None,
        "duration": round(float((data.get("format") or {}).get("duration") or 0), 3),
    }


def build_clip(path: Path) -> dict[str, Any]:
    """Generate the burned-in H.264 fixture and return its identity."""
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{CLIP_WIDTH}x{CLIP_HEIGHT}", "-r", str(CLIP_FPS), "-i", "-",
        "-frames:v", str(CLIP_FRAMES),
        "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.1",
        "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "23",
        "-g", "30", "-keyint_min", "30", "-sc_threshold", "0",
        "-movflags", "+faststart", "-y", str(path),
    ]
    big, mid, small = _font(58), _font(34), _font(22)
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        assert process.stdin is not None
        for index in range(CLIP_FRAMES):
            process.stdin.write(_clip_frame(index, big, mid, small).tobytes())
        process.stdin.close()
        stderr = process.stderr.read().decode(errors="replace") if process.stderr else ""
        code = process.wait(timeout=180)
    except Exception:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        raise
    if code != 0:
        raise RuntimeError(f"ffmpeg failed ({code}): {stderr.strip()[-1200:]}")

    metadata = _ffprobe(path)
    digest = evidence.file_sha256(path)
    return {
        "name": path.name,
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": digest,
        **metadata,
    }


def parse_range(header: str, size: int) -> tuple[int, int]:
    if not header.startswith("bytes="):
        raise ValueError("unsupported range unit")
    spec = header[6:].split(",", 1)[0].strip()
    first, separator, last = spec.partition("-")
    if not separator:
        raise ValueError("malformed range")
    if first == "":
        length = int(last)
        start = max(0, size - length)
        end = size - 1
    else:
        start = int(first)
        end = int(last) if last else size - 1
    if start < 0 or start >= size or start > end:
        raise ValueError("range outside the file")
    return start, min(end, size - 1)


def start_server(
    routes: dict[str, Path],
) -> tuple[ThreadingHTTPServer, threading.Thread, int]:
    """Serve only the whitelisted probe files, with single-range support."""
    content_types = {
        ".html": "text/html; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".mp4": "video/mp4",
    }

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def do_HEAD(self) -> None:  # noqa: N802
            self._serve(head=True)

        def do_GET(self) -> None:  # noqa: N802
            self._serve(head=False)

        def _serve(self, head: bool) -> None:
            target = routes.get(urlparse(self.path).path)
            if target is None:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            try:
                size = target.stat().st_size
            except OSError:
                self.send_response(500)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            start, end = 0, size - 1
            partial = False
            range_header = self.headers.get("Range")
            if range_header:
                try:
                    start, end = parse_range(range_header, size)
                    partial = True
                except ValueError:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return

            self.send_response(206 if partial else 200)
            if partial:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Type", content_types.get(target.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if head:
                return
            remaining = end - start + 1
            try:
                with target.open("rb") as handle:
                    handle.seek(start)
                    while remaining > 0:
                        chunk = handle.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, int(server.server_address[1])


def stop_server(server: ThreadingHTTPServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _command_version(command: list[str]) -> str | None:
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    first = (done.stdout or done.stderr).splitlines()
    return first[0].strip() if first else None


def _playwright_version() -> str | None:
    try:
        return importlib.metadata.version("playwright")
    except importlib.metadata.PackageNotFoundError:
        return None


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _snapshot(page: Any) -> dict[str, Any]:
    return page.evaluate("window.__deviceProbe.snapshot()")


def _check(
    result: dict[str, Any], engine: str, name: str, passed: bool, **detail: Any,
) -> bool:
    result["checks"].append(
        evidence.check_row(f"{engine}: {name}", passed, **detail),
    )
    return passed


async def run_engine(
    playwright: Any,
    engine: str,
    base_url: str,
    artifacts: Path,
    clip: dict[str, Any],
    contract: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "engine": engine,
        "status": "failed",
        "version": None,
        "detail": None,
        "checks": [],
        "console": [],
        "page_errors": [],
        "request_failures": [],
        "payload": None,
    }
    browser = None
    context = None
    page = None
    try:
        try:
            browser = await getattr(playwright, engine).launch()
        except Exception as exc:  # noqa: BLE001 - launch failures are evidence
            result["status"] = "unsupported" if engine == "webkit" else "failed"
            result["detail"] = f"{type(exc).__name__}: {exc}"
            return result

        result["version"] = browser.version
        context = await browser.new_context(
            viewport=VIEWPORT, device_scale_factor=DEVICE_SCALE_FACTOR,
        )
        page = await context.new_page()
        page.set_default_timeout(15000)

        console: list[dict[str, Any]] = result["console"]
        page_errors: list[dict[str, Any]] = result["page_errors"]
        request_failures: list[dict[str, Any]] = result["request_failures"]

        page.on("console", lambda message: console.append({
            "type": message.type,
            "text": message.text[:1200],
            "location": message.location,
        }) if len(console) < 200 else None)
        page.on("pageerror", lambda error: page_errors.append({
            "name": type(error).__name__,
            "message": str(error)[:1200],
        }) if len(page_errors) < 40 else None)
        page.on("requestfailed", lambda request: request_failures.append({
            "url": request.url[:1000],
            "method": request.method,
            "failure": str(request.failure)[:400] if request.failure else None,
        }) if len(request_failures) < 80 else None)

        query = urlencode({
            "src": "/clip.mp4",
            "source_name": clip["name"],
            "source_size": clip["bytes"],
            "source_sha256": clip["sha256"],
            "run": run_id,
            "autoplay": "1",
            "loop": "0",
        })
        url = f"{base_url}/?{query}"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_function(READY_JS, timeout=15000)
        await page.wait_for_function(PLAYING_JS, timeout=20000)

        initial = await _snapshot(page)
        result["payload"] = initial
        problems = payload_problems(initial, contract)
        _check(result, engine, "payload contract", not problems, problems=problems[:25])
        identity = source_problems(initial, clip)
        _check(result, engine, "source identity", not identity, problems=identity)

        codec = (
            initial.get("environment", {})
            .get("codec_support", {})
            .get(H264_CODEC, {})
            .get("can_play_type", "")
        )
        if not codec:
            if engine == "webkit":
                raise UnsupportedEngine("desktop WebKit reports no H.264 canPlayType support")
            raise RuntimeError("desktop Chromium reports no H.264 canPlayType support")
        _check(result, engine, "h264 canPlayType", codec in ("probably", "maybe"), answer=codec)
        _check(
            result, engine, "fresh play and frame callbacks",
            initial["play"]["last_outcome"] == "resolved"
            and initial["counters"]["frame_callbacks"] >= 5,
            play_outcome=initial["play"]["last_outcome"],
            frame_callbacks=initial["counters"]["frame_callbacks"],
        )

        await page.evaluate("window.__deviceProbe.pause()")
        await page.wait_for_function(
            "() => window.__deviceProbe.state().paused === true", timeout=5000,
        )
        paused = await page.evaluate("window.__deviceProbe.state()")
        _check(result, engine, "pause control", paused["paused"] is True, state=paused)

        await page.evaluate("window.__deviceProbe.seek(5.0)")
        await page.wait_for_function(
            "() => { const s = window.__deviceProbe.state();"
            " return s.currentTime >= 4.5 && s.currentTime <= 7.5; }",
            timeout=5000,
        )
        seeked = await page.evaluate("window.__deviceProbe.state()")
        seek_time = seeked["currentTime"]
        _check(
            result, engine, "seek control",
            seek_time is not None and 4.5 <= seek_time <= 7.5,
            state=seeked,
        )

        await page.evaluate("window.__deviceProbe.start('resume')")
        # WebKit can leave the resume play promise pending while playback
        # visibly advances; that outcome is evidence, not a failed resume.
        await page.wait_for_function(RUNNING_JS, timeout=10000)
        resumed = await page.evaluate("window.__deviceProbe.state()")
        _check(
            result, engine, "resume playback",
            resumed["playing"] is True and resumed["frames"] >= 5,
            play_outcome=resumed["playOutcome"],
            state=resumed,
        )

        duration = seeked["duration"] or CLIP_SECONDS
        await page.evaluate("window.__deviceProbe.setLoop(true)")
        await page.evaluate(f"window.__deviceProbe.seek({max(0.0, duration - 0.8)})")
        await page.evaluate("window.__deviceProbe.start('loop-check')")
        await page.wait_for_function(
            "() => { const s = window.__deviceProbe.state();"
            " return s.loop === true && s.playing && s.currentTime < 3; }",
            timeout=8000,
        )
        looped = await page.evaluate("window.__deviceProbe.state()")
        loop_time = looped["currentTime"]
        _check(
            result, engine, "loop control",
            looped["loop"] is True and looped["playing"] is True
            and loop_time is not None and loop_time < 3,
            state=looped,
        )
        await page.evaluate("window.__deviceProbe.setLoop(false)")

        await page.evaluate("window.__deviceProbe.setMuted(false)")
        await page.wait_for_function(
            "() => window.__deviceProbe.state().muted === false", timeout=5000,
        )
        await page.evaluate("window.__deviceProbe.setMuted(true)")
        muted = await page.evaluate("window.__deviceProbe.state()")
        _check(result, engine, "mute control", muted["muted"] is True, state=muted)

        marker = await page.evaluate(
            "window.__deviceProbe.mark('smoke-marker')",
        )
        _check(
            result, engine, "operator marker",
            isinstance(marker, dict) and marker.get("label") == "smoke-marker",
            marker=marker,
        )

        before = await _snapshot(page)
        result["payload"] = before
        _write_json(artifacts / f"probe-desktop-{engine}-actions.json", before)
        event_names = {
            row.get("name") for row in before.get("media_events", [])
            if isinstance(row, dict)
        }
        _check(
            result, engine, "pause/seek media events",
            {"pause", "seeking", "seeked"}.issubset(event_names),
            observed=sorted(name for name in event_names if name),
        )
        _check(
            result, engine, "volumechange event", "volumechange" in event_names,
        )

        await page.reload(wait_until="domcontentloaded")
        await page.wait_for_function(READY_JS, timeout=15000)
        await page.wait_for_function(RUNNING_JS, timeout=20000)
        await page.wait_for_timeout(250)
        after = await _snapshot(page)
        result["payload"] = after

        lineage = after.get("lineage") or {}
        gaps = lineage.get("unexplained_gaps") or []
        lineage_ok = (
            after["page"]["sequence"] == before["page"]["sequence"] + 1
            and after["page"]["previous_instance_id"] == before["page"]["instance_id"]
            and len(lineage.get("sessions") or []) >= 2
            and bool(lineage.get("previous_summary"))
            and after["page"]["navigation"].get("session_storage_present") is True
            and len(gaps) >= 1
        )
        _check(
            result, engine, "reload lineage",
            lineage_ok,
            before_sequence=before["page"]["sequence"],
            after_sequence=after["page"]["sequence"],
            previous_instance_id=after["page"].get("previous_instance_id"),
            sessions=len(lineage.get("sessions") or []),
            previous_summary=bool(lineage.get("previous_summary")),
            gaps=gaps[:2],
        )

        persistence = after.get("persistence") or {}
        persistence_ok = (
            persistence.get("session_storage", {}).get("writes", 0) > 0
            and persistence.get("local_storage", {}).get("writes", 0) > 0
            and isinstance(persistence.get("trimmed"), dict)
            and persistence.get("limits") == contract["limits"]
        )
        _check(
            result, engine, "bounded persistence", persistence_ok,
            session_writes=persistence.get("session_storage", {}).get("writes"),
            local_writes=persistence.get("local_storage", {}).get("writes"),
            trimmed=persistence.get("trimmed"),
        )

        wake = after.get("environment", {}).get("wake_lock") or {}
        fullscreen = after.get("environment", {}).get("fullscreen") or {}
        _check(
            result, engine, "wake lock state recorded",
            isinstance(wake, dict) and isinstance(wake.get("state"), str),
            state=wake,
        )
        _check(
            result, engine, "fullscreen state recorded",
            isinstance(fullscreen, dict) and isinstance(fullscreen.get("state"), str),
            state=fullscreen,
        )
        _check(
            result, engine, "explicit unavailable APIs",
            isinstance(after.get("unavailable"), list),
            unavailable=after.get("unavailable"),
        )

        final_problems = payload_problems(after, contract)
        _check(
            result, engine, "post-reload payload contract",
            not final_problems, problems=final_problems[:25],
        )
        _check(
            result, engine, "no page errors", not page_errors,
            count=len(page_errors), errors=page_errors[:5],
        )
        console_errors = [row for row in console if row.get("type") == "error"]
        _check(
            result, engine, "no console errors", not console_errors,
            count=len(console_errors), errors=console_errors[:5],
        )

        try:
            await page.screenshot(path=str(artifacts / f"probe-desktop-{engine}.png"))
        except Exception as exc:  # noqa: BLE001 - screenshot is supporting evidence
            result["detail"] = f"screenshot failed: {type(exc).__name__}: {exc}"
    except UnsupportedEngine as exc:
        result["status"] = "unsupported"
        result["detail"] = str(exc)
    except Exception as exc:  # noqa: BLE001 - run failures are evidence
        result["status"] = "failed"
        result["detail"] = f"{type(exc).__name__}: {exc}"
        result["checks"].append(evidence.check_row(
            f"{engine}: runner action error", False,
            error={"type": type(exc).__name__, "message": str(exc)[:1200]},
        ))
        if page is not None:
            try:
                result["payload"] = await _snapshot(page)
            except Exception:  # noqa: BLE001 - page may be gone
                pass
    finally:
        if result["status"] not in ("unsupported",) and result["checks"]:
            result["status"] = (
                "failed" if any(not row["passed"] for row in result["checks"])
                else "passed"
            )
        if result.get("payload") is not None:
            _write_json(
                artifacts / f"probe-desktop-{engine}.json",
                result["payload"],
            )
        _write_json(artifacts / f"console-desktop-{engine}.json", {
            "engine": engine,
            "version": result["version"],
            "console": result["console"],
            "page_errors": result["page_errors"],
            "request_failures": result["request_failures"],
            "status": result["status"],
            "detail": result["detail"],
        })
        if context is not None:
            try:
                await context.close()
            except Exception:  # noqa: BLE001 - cleanup failure is not scenario evidence
                pass
        if browser is not None:
            try:
                await browser.close()
            except Exception:  # noqa: BLE001
                pass
    return result


async def run_engines(
    base_url: str,
    artifacts: Path,
    clip: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed; run with the browser dependency group"
        ) from exc

    results: dict[str, dict[str, Any]] = {}
    async with async_playwright() as playwright:
        for engine in ENGINE_ORDER:
            run_id = f"decode-probe-{engine}-{time.time_ns()}"
            results[engine] = await run_engine(
                playwright, engine, base_url, artifacts, clip, contract, run_id,
            )
    return results


def assemble_report(
    *,
    started_at: str,
    engines: dict[str, dict[str, Any]],
    artifacts: dict[str, dict[str, Any]],
    tools: dict[str, Any] | None = None,
    repository: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure report assembly; no browser, network or filesystem dependence."""
    checks: list[dict[str, Any]] = []
    scenarios: list[dict[str, Any]] = []
    for engine in ENGINE_ORDER:
        scenario_id = f"desktop-{engine}"
        result = engines.get(engine)
        if result is None:
            scenarios.append(evidence.scenario_row(
                scenario_id, "incomplete", detail="engine did not run",
            ))
            continue
        status = result.get("status")
        if status != "unsupported":
            checks.extend(result.get("checks") or [])
        if status == "unsupported":
            scenarios.append(evidence.scenario_row(
                scenario_id, "unsupported", detail=result.get("detail"),
            ))
        elif status == "failed":
            scenarios.append(evidence.scenario_row(
                scenario_id, "failed", detail=result.get("detail"),
            ))
        elif status == "passed":
            scenarios.append(evidence.scenario_row(
                scenario_id, "passed", detail=result.get("detail"),
            ))
        else:
            scenarios.append(evidence.scenario_row(
                scenario_id, "incomplete", detail=result.get("detail"),
            ))

    scenarios.append(evidence.scenario_row(
        IOS_SCENARIO, "unsupported", detail=IOS_DETAIL,
    ))
    return evidence.build_report(
        tool="device-probe-smoke",
        tool_version=TOOL_VERSION,
        gate="physical-decode-suspend",
        evidence_kind="desktop-browser",
        started_at=started_at,
        checks=checks,
        scenarios=scenarios,
        expected_scenarios=[f"desktop-{engine}" for engine in ENGINE_ORDER] + [IOS_SCENARIO],
        cohort=[f"desktop-{engine}" for engine in ENGINE_ORDER],
        artifacts=artifacts,
        tools=tools or {},
        repository=repository or {},
        skipped=[],
        unobserved=UNOBSERVED,
        limitations=LIMITATIONS,
        error=error,
    )


def _artifact_paths(artifacts: Path) -> list[Path]:
    return sorted(
        path for path in artifacts.rglob("*")
        if path.is_file() and path.name != "report.json"
    )


def _temp_parent() -> str:
    candidate = Path("/tmp/opencode")
    return str(candidate) if candidate.is_dir() else tempfile.gettempdir()


async def run_smoke(artifacts: Path) -> dict[str, Any]:
    started_at = evidence.iso_now()
    root = Path(tempfile.mkdtemp(prefix="tw-decode-probe-", dir=_temp_parent()))
    clip_path = root / "decode-probe-10s.mp4"
    server: ThreadingHTTPServer | None = None
    thread: threading.Thread | None = None
    try:
        clip = build_clip(clip_path)
        retained_clip = artifacts / clip_path.name
        shutil.copy2(clip_path, retained_clip)
        clip["path"] = str(retained_clip)

        contract = probe_contract()
        server, thread, port = start_server({
            "/": PROBE_INDEX,
            "/index.html": PROBE_INDEX,
            "/probe.js": PROBE_JS,
            "/clip.mp4": clip_path,
        })
        base_url = f"http://127.0.0.1:{port}"
        engines = await run_engines(base_url, artifacts, clip, contract)
        tools = {
            "runner": RUNNER,
            "playwright": _playwright_version(),
            "ffmpeg": _command_version(["ffmpeg", "-version"]),
            "ffprobe": _command_version(["ffprobe", "-version"]),
            "browsers": {
                engine: engines.get(engine, {}).get("version")
                for engine in ENGINE_ORDER
            },
            "clip": {
                "name": clip["name"],
                "bytes": clip["bytes"],
                "sha256": clip["sha256"],
                "codec": clip["codec"],
                "duration": clip["duration"],
                "fps": clip["fps"],
                "frames": clip["frames"],
            },
            "viewport": {**VIEWPORT, "device_scale_factor": DEVICE_SCALE_FACTOR},
            "server": "127.0.0.1 free port (loopback static, range requests)",
        }
        report = assemble_report(
            started_at=started_at,
            engines=engines,
            artifacts=evidence.artifact_hashes(_artifact_paths(artifacts)),
            tools=tools,
            repository=evidence.repository_state(REPO),
        )
        evidence.write_report(artifacts / "report.json", report)
        return report
    finally:
        if server is not None and thread is not None:
            stop_server(server, thread)
        shutil.rmtree(root, ignore_errors=True)


def _abort_report(artifacts: Path, started_at: str, exc: Exception) -> dict[str, Any]:
    report = assemble_report(
        started_at=started_at,
        engines={},
        artifacts=evidence.artifact_hashes(_artifact_paths(artifacts)),
        repository=evidence.repository_state(REPO),
        error={
            "type": type(exc).__name__,
            "message": str(exc)[:2000],
            "traceback": traceback.format_exc()[-4000:],
        },
    )
    evidence.write_report(artifacts / "report.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Desktop Chromium/WebKit smoke for the device probe page.",
    )
    parser.add_argument(
        "--artifacts", type=Path, default=None,
        help="new directory outside the repository for probe JSON and the report",
    )
    args = parser.parse_args(argv)
    started_at = evidence.iso_now()
    artifacts = artifact_directory(args.artifacts)
    try:
        report = asyncio.run(run_smoke(artifacts))
    except Exception as exc:  # noqa: BLE001 - always leave an incomplete report
        report = _abort_report(artifacts, started_at, exc)

    chromium = next(
        (row for row in report["scenarios"] if row["id"] == "desktop-chromium"),
        None,
    )
    ok = (
        chromium is not None and chromium["status"] == "passed"
        and not report["failure_reasons"]
    )
    print(json.dumps({
        "artifacts": str(artifacts),
        "report": str(artifacts / "report.json"),
        "completion": report["completion"],
        "checks": f"{report['checks_passed']}/{report['checks_total']}",
        "scenarios": {row["id"]: row["status"] for row in report["scenarios"]},
        "failure_reasons": report["failure_reasons"],
        "webkit": next(
            (row for row in report["scenarios"] if row["id"] == "desktop-webkit"),
            None,
        ),
    }, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
