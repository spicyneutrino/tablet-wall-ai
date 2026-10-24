"""Disposable Chromium evidence for the current logical still-image wall."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ClientSpec:
    name: str
    width: int
    height: int
    dpr: float
    persistent: bool = False


SPECS = (
    ClientSpec("landscape", 800, 600, 1),
    ClientSpec("portrait", 600, 800, 1.25),
    ClientSpec("process-profile", 801, 601, 1.5, True),
)


@dataclass
class Observation:
    spec: ClientSpec
    device_id: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    renders: list[dict[str, Any]] = field(default_factory=list)

    def event(self, kind: str, **data: Any) -> None:
        self.events.append({"time": time.monotonic(), "kind": kind, **data})


def artifact_directory(path: Path | None) -> Path:
    if path is None:
        path = Path(tempfile.gettempdir()) / ("tablet-wall-browser-" + str(time.time_ns()))
    path = path.expanduser().resolve()
    if path == REPO or REPO in path.parents:
        raise ValueError("artifacts must be outside the repository")
    path.mkdir(parents=True, exist_ok=False)
    return path


def child_environment(root: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("TABLET_WALL_")}
    env.update({
        "TABLET_WALL_DB": str(root / "wall.db"),
        "TABLET_WALL_ASSET_DIR": str(root / "assets"),
        "TABLET_WALL_MEDIA_DIR": str(root / "media"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": str(root / "tmp"),
    })
    return env


def write_fixture(path: Path) -> None:
    image = Image.new("RGB", (1600, 800))
    draw = ImageDraw.Draw(image)
    for row in range(8):
        for col in range(16):
            draw.rectangle((col * 100, row * 100, col * 100 + 99, row * 100 + 99),
                           fill=(15 + col * 13, 20 + row * 27, 25 + col * 5 + row * 11))
    image.save(path)


# P0 video probe: horizontal bands make a quarter turn observable (the bands
# become vertical stripes) and a clip observable (only the top band shows).
PROBE_BANDS = ((255, 0, 0), (0, 255, 0), (0, 0, 255))


def write_probe_source(path: Path) -> None:
    image = Image.new("RGB", (320, 180))
    draw = ImageDraw.Draw(image)
    for index, colour in enumerate(PROBE_BANDS):
        draw.rectangle((0, index * 60, 319, index * 60 + 59), fill=colour)
    image.save(path)


def build_probe_video(source: Path, target: Path) -> dict[str, Any] | None:
    """Encode a two-second H.264 baseline MP4; None when ffmpeg is unavailable.

    The command is fixed, uses no shell, and reads only the generated PNG. A
    capture of the exact argv is returned so the evidence names what ran.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return None
    argv = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-i", str(source),
        "-t", "2", "-r", "30",
        "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.0",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an",
        str(target),
    ]
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"ok": False, "argv": argv, "error": str(error)}
    if completed.returncode != 0:
        return {"ok": False, "argv": argv, "error": completed.stderr.strip()[-2000:]}
    return {
        "ok": True,
        "argv": argv,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "bytes": target.stat().st_size,
    }


def probe_metadata(path: Path) -> dict[str, Any] | None:
    """ffprobe's view of the fixture: codec, profile, size, rate, duration."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None
    completed = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name,profile,width,height,r_frame_rate,pix_fmt",
         "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    if completed.returncode != 0:
        return {"error": completed.stderr.strip()[-2000:]}
    return json.loads(completed.stdout)


def start_probe_server(directory: Path) -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    """Serve the probe page and MP4 from one temporary loopback origin.

    No range support is claimed: this fixture is small and fully buffered, and
    the report records that delivery limitation.
    """
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, *_args: Any) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802 - http.server's spelling
            path = self.translate_path(self.path)
            if not os.path.isfile(path):
                super().do_GET()
                return
            size = os.path.getsize(path)
            value = self.headers.get("Range", "")
            start, end, partial = 0, size - 1, False
            if value.startswith("bytes=") and "-" in value:
                first, last = value.removeprefix("bytes=").split("-", 1)
                try:
                    if first:
                        start = int(first)
                        end = int(last) if last else size - 1
                    else:
                        start = max(0, size - int(last))
                    end = min(end, size - 1)
                except ValueError:
                    start, end = 0, size - 1
                if start > end or start >= size:
                    self.send_error(416)
                    return
                partial = True
            length = end - start + 1
            self.send_response(206 if partial else 200)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if partial:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with open(path, "rb") as handle:
                handle.seek(start)
                self.wfile.write(handle.read(length))

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_address[1]}"


PROBE_PAGE = """<!doctype html>
<meta charset="utf-8">
<style>
  html, body { margin: 0; background: #000; overflow: hidden; }
  #stage { position: relative; width: 240px; height: 240px; background: #000; }
  #vid { position: absolute; left: 0; top: 0; width: 160px; height: 90px; object-fit: fill; }
  #clip { position: absolute; left: 200px; top: 0; width: 80px; height: 45px; overflow: hidden; }
  #clip video { display: block; position: static; width: 160px; height: 90px; }
</style>
<div id="stage">
  <video id="vid" muted playsinline preload="auto" src="/probe.mp4"></video>
  <div id="clip"><video id="clipvid" muted playsinline preload="auto" src="/probe.mp4"></video></div>
</div>
<script>
  window.probe = {
    video: document.getElementById('vid'),
    clipVideo: document.getElementById('clipvid'),
    stage: document.getElementById('stage')
  };
</script>
"""


def expected_pixel(name: str, bx: int, by: int) -> tuple[int, int, int]:
    spec = next(spec for spec in SPECS if spec.name == name)
    x, y = (bx + 0.5) / spec.dpr, (by + 0.5) / spec.dpr
    if name == "landscape":
        sx, sy = 200 + x * 3 / 4, 175 + y * 3 / 4
    elif name == "portrait":
        sx, sy = 800 + x, y
    else:
        sx, sy = 800 + (x - 400.5) * 800 / 601, y * 800 / 601
    col, row = math.floor(sx / 100), math.floor(sy / 100)
    return 15 + col * 13, 20 + row * 27, 25 + col * 5 + row * 11


def process_table() -> dict[int, tuple[int, str]]:
    result = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            result[int(entry.name)] = (int(fields[1]), fields[19])
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return result


def descendants(pid: int) -> dict[int, str]:
    table = process_table()
    owned = {pid}
    while True:
        children = {child for child, (parent, _) in table.items() if parent in owned}
        expanded = owned | children
        if expanded == owned:
            return {child: table[child][1] for child in owned - {pid}}
        owned = expanded


def browser_processes() -> list[int]:
    result = []
    for pid in descendants(os.getpid()):
        try:
            command = Path(f"/proc/{pid}/cmdline").read_bytes()
            if b"--remote-debugging-pipe" in command and b"--type=" not in command:
                result.append(pid)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return result


def stop_server(process: subprocess.Popen | None) -> None:
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


INIT_SCRIPT = """(() => {
    window.__fleetSockets = [];
    window.WebSocket = new Proxy(window.WebSocket, {
        construct(Target, args) {
            const ws = Reflect.construct(Target, args);
            window.__fleetSockets.push(ws);
            ws.addEventListener('close', e => window.__fleetClose({
                url: ws.url, code: e.code, reason: e.reason, clean: e.wasClean
            }));
            return ws;
        }
    });
})();"""


async def watch_page(context: Any, spec: ClientSpec, observations: list[Observation]) -> tuple[Any, Observation]:
    observation = Observation(spec)
    observations.append(observation)
    page = await context.new_page()
    page.set_default_timeout(10_000)
    await page.expose_binding("__fleetClose", lambda source, data: observation.event("ws_close", **data))
    await page.add_init_script(INIT_SCRIPT)
    page.on("console", lambda message: observation.event("console", level=message.type, text=message.text))
    page.on("pageerror", lambda error: observation.event("page_error", text=str(error)))
    page.on("requestfailed", lambda request: observation.event("request_failed", url=request.url, error=request.failure))
    page.on("response", lambda response: observation.event("http", url=response.url, status=response.status))

    def websocket(ws: Any) -> None:
        connection = sum(event["kind"] == "ws_open" for event in observation.events) + 1
        observation.event("ws_open", connection=connection, url=ws.url)

        def frame(direction: str, payload: str | bytes) -> None:
            try:
                data = json.loads(payload)
            except (ValueError, UnicodeError):
                data = str(payload)
            observation.event(direction, connection=connection, frame=data)

        ws.on("framereceived", lambda payload: frame("ws_received", payload))
        ws.on("framesent", lambda payload: frame("ws_sent", payload))
        ws.on("socketerror", lambda error: observation.event("ws_error", connection=connection, error=error))

    page.on("websocket", websocket)
    return page, observation


async def connected(page: Any) -> str:
    await page.wait_for_function("document.querySelector('#status').dataset.state === 'connected'")
    return await page.evaluate("localStorage.getItem('tablet-wall-device-id')")


async def sample_render(page: Any, observation: Observation, artifacts: Path, label: str) -> dict[str, Any]:
    await page.locator("#surface").wait_for(state="visible")
    probe = expected_pixel(observation.spec.name, 20, 20)
    deadline = time.monotonic() + 10
    while True:
        encoded = await page.locator("#surface").evaluate("c => c.toDataURL('image/png')")
        image = Image.open(io.BytesIO(base64.b64decode(encoded.split(",", 1)[1]))).convert("RGBA")
        if image.size[0] > 20 and image.size[1] > 20 and image.getpixel((20, 20))[:3] == probe:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(f"{observation.spec.name}: image pixels did not become ready")
        await asyncio.sleep(.05)
    result = await page.evaluate("""() => {
        const c = document.querySelector('#surface'), r = c.getBoundingClientRect();
        const xs = [2, Math.floor(c.width*.27), Math.floor(c.width*.53), Math.floor(c.width*.73), c.width-3];
        const ys = [2, Math.floor(c.height*.27), Math.floor(c.height*.53), Math.floor(c.height*.73), c.height-3];
        return {
            rect: {x:r.x,y:r.y,width:r.width,height:r.height}, backing:[c.width,c.height],
            viewport:[innerWidth,innerHeight], dpr:devicePixelRatio,
            visualViewport: window.visualViewport ? {width:visualViewport.width,height:visualViewport.height,
                scale:visualViewport.scale,offsetLeft:visualViewport.offsetLeft,offsetTop:visualViewport.offsetTop} : null,
            orientation: screen.orientation ? {type:screen.orientation.type,angle:screen.orientation.angle} : null,
            mode:document.fullscreenElement ? 'fullscreen':'tab',
            samples:ys.flatMap(y=>xs.map(x=>({x,y})))
        };
    }""")
    for sample in result["samples"]:
        sample["rgba"] = image.getpixel((sample["x"], sample["y"]))
        sample["expected"] = expected_pixel(observation.spec.name, sample["x"], sample["y"])
    result["screenshot"] = str(artifacts / f"{observation.spec.name}-{label}.png")
    await page.screenshot(path=result["screenshot"])
    observation.renders.append(result)
    return result


async def exercise(artifacts: Path, report: dict[str, Any], observation_seconds: float,
                   fail_after_server: bool = False) -> None:
    from playwright.async_api import async_playwright

    observations: list[Observation] = []
    report["clients"] = observations
    checks = report["checks"]

    def check(name: str, ok: bool, **details: Any) -> None:
        checks.append({"name": name, "passed": bool(ok), **details})

    initial_processes = descendants(os.getpid())
    root = Path(tempfile.mkdtemp(prefix="tablet-wall-browser-data-"))
    report["temporary_root"] = str(root)
    process = None
    listener = None
    playwright = None
    resources = []
    captured_pages = []
    owned_processes: dict[int, str] = {}
    log = None
    try:
        for name in ("assets", "media", "tmp", "profile"):
            (root / name).mkdir()
        write_fixture(root / "assets" / "coded.png")
        env = child_environment(root)
        report["data_paths"] = {key: value for key, value in env.items() if key.startswith("TABLET_WALL_")}
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        base = f"http://127.0.0.1:{listener.getsockname()[1]}"
        report["origin"] = base
        # Uploads are operator-only. The disposable server runs the explicit
        # direct-local mode: a loopback peer, this exact origin, and no proxy
        # header interpretation. Every state-changing API call below carries
        # the same Origin the browser would send.
        env["TABLET_WALL_UPLOAD_MODE"] = "loopback"
        env["TABLET_WALL_OPERATOR_ORIGIN"] = base
        log = (artifacts / "server.log").open("x")
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--fd", str(listener.fileno()),
             "--workers", "1", "--no-access-log"], cwd=REPO, env=env,
            pass_fds=(listener.fileno(),), stdout=log, stderr=subprocess.STDOUT,
        )
        report["server_pid"] = process.pid
        listener.close()
        listener = None
        if fail_after_server:
            raise RuntimeError("injected partial launch failure after server spawn")
        playwright = await async_playwright().start()
        request = await playwright.request.new_context(base_url=base, timeout=1000)
        resources.append(request)
        deadline = time.monotonic() + 15
        while True:
            try:
                response = await request.get("/wall")
                if response.ok:
                    check("fresh temporary database", (await response.json())["revision"] == 0 and (root / "wall.db").is_file())
                    break
            except Exception:
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("isolated server failed to become ready; see server.log")
            if time.monotonic() >= deadline:
                raise RuntimeError("isolated server readiness deadline exceeded")
            await asyncio.sleep(.1)
        browser_env = {**os.environ, "TMPDIR": str(root / "tmp")}
        browser = await playwright.chromium.launch(env=browser_env)
        resources.append(browser)
        owned_processes.update(descendants(os.getpid()))
        report["browser_version"] = browser.version
        report["browser_build"] = "Playwright 1.57.0 Chromium revision 1200"
        shared_browser_pids = browser_processes()
        report["browser_processes"] = {"independent_contexts": shared_browser_pids}
        pages = []
        for spec in SPECS:
            options = {"viewport": {"width": spec.width, "height": spec.height}, "device_scale_factor": spec.dpr}
            if spec.persistent:
                context = await playwright.chromium.launch_persistent_context(root / "profile", env=browser_env, **options)
                resources.append(context)
                profile_pids = sorted(set(browser_processes()) - set(shared_browser_pids))
                report["browser_processes"]["persistent_profile"] = profile_pids
                check("persistent profile in a separate browser process", len(shared_browser_pids) == 1 and len(profile_pids) == 1)
                # Persistent contexts start with a blank page, not a client.
                for blank in context.pages:
                    await blank.close()
            else:
                context = await browser.new_context(**options)
                resources.append(context)
            owned_processes.update(descendants(os.getpid()))
            page, observation = await watch_page(context, spec, observations)
            captured_pages.append((page, observation))
            await page.goto(base + "/client/")
            observation.device_id = await connected(page)
            pages.append((page, observation))
            check(spec.name + " handshake", all(any(
                event["kind"] == "ws_received" and isinstance(event["frame"], dict) and event["frame"].get("type") == kind
                for event in observation.events) for kind in ("welcome", "wall")))
        check("three independent same-origin identities", len({obs.device_id for _, obs in pages}) == 3)
        controller_context = await browser.new_context(viewport={"width": 1280, "height": 900})
        resources.append(controller_context)
        controller, controller_obs = await watch_page(controller_context, ClientSpec("controller", 1280, 900, 1), observations)
        captured_pages.append((controller, controller_obs))
        await controller.goto(base + "/controller/")

        async def api(method: str, path: str, data: dict[str, Any] | None = None) -> Any:
            response = await request.fetch(
                path, method=method, data=data, headers={"Origin": base}
            )
            check(method + " " + path, response.ok, status=response.status)
            if not response.ok:
                raise RuntimeError(await response.text())
            return await response.json()

        await api("PUT", "/wall", {"width": 1200, "height": 800})
        placements = (
            {"x": 0, "y": 0, "w": 600, "h": 800},
            {"x": 600, "y": 0, "w": 600, "h": 800},
            {"x": 0, "y": 0, "w": 1200, "h": 800},
        )
        for (_, observation), placement in zip(pages, placements, strict=True):
            await api("PUT", f"/devices/{observation.device_id}/placement", placement)
        inventory = await api("GET", "/assets")
        asset = inventory["assets"][0]["id"]
        await api("PUT", "/scene", {"content": {"type": "image", "asset": asset}})
        async with controller.expect_response(lambda response: response.url == base + "/scene" and response.request.method == "PUT") as changed:
            await controller.get_by_role("button", name="Calibration", exact=True).click()
        check("controller calibration response", (await changed.value).ok)
        await controller.wait_for_function("document.querySelector('[data-content=calibration]').getAttribute('aria-pressed') === 'true'")
        await controller.click('#wall-content button[data-content="image"]')
        await controller.locator(f"button[data-asset='{asset}']").click()
        async with controller.expect_response(lambda response: response.url == base + "/scene" and response.request.method == "PUT") as changed:
            await controller.locator("#btn-image-apply").click()
        check("controller image response", (await changed.value).ok)
        await controller.wait_for_function("document.querySelector('[data-content=image]').getAttribute('aria-pressed') === 'true'")
        check("controller selects and shows curated image", (await api("GET", "/wall"))["scene"]["content"]["asset"] == asset)
        await controller.screenshot(path=str(artifacts / "controller.png"), full_page=True)
        report["controller_screenshot"] = str(artifacts / "controller.png")

        for page, observation in pages:
            for label in ("initial", "reload"):
                if label == "reload":
                    before = observation.device_id
                    await page.reload()
                    check(observation.spec.name + " reload retains ID", await connected(page) == before)
                render = await sample_render(page, observation, artifacts, label)
                spec = observation.spec
                check(spec.name + " " + label + " pixels", all(
                    max(abs(actual - expected) for actual, expected in zip(sample["rgba"], (*sample["expected"], 255), strict=True)) <= 2
                    for sample in render["samples"]), samples=render["samples"])
                check(spec.name + " " + label + " rectangle", render["rect"] == {
                    "x": 0, "y": 0, "width": spec.width, "height": spec.height
                } and render["backing"] == [math.floor(spec.width * spec.dpr + .5), math.floor(spec.height * spec.dpr + .5)]
                      and render["viewport"] == [spec.width, spec.height] and render["dpr"] == spec.dpr)

        start = time.monotonic()
        online_samples = []
        close_counts = [sum(event["kind"] == "ws_close" for event in obs.events) for _, obs in pages]
        while time.monotonic() - start < observation_seconds:
            roster = await api("GET", "/devices")
            states = [await page.evaluate("__fleetSockets.filter(s=>s.readyState===WebSocket.OPEN).length") for page, _ in pages]
            online_samples.append({"time": time.monotonic(), "open_sockets": states,
                                   "online": [roster[obs.device_id]["online"] for _, obs in pages]})
            await asyncio.sleep(.25)
        report["liveness"] = {"duration_seconds": time.monotonic() - start, "samples": online_samples}
        check("simultaneously live independent sockets", all(
            row["open_sockets"] == [1, 1, 1] and all(row["online"]) for row in online_samples)
            and close_counts == [sum(event["kind"] == "ws_close" for event in obs.events) for _, obs in pages])
        check("real heartbeats in observation window", all(any(event["kind"] == "ws_sent" and event["time"] >= start
            and event["frame"] == {"type": "heartbeat"} for event in obs.events) for _, obs in pages))

        async def open_sockets(page: Any) -> int:
            return await page.evaluate("__fleetSockets.filter(s=>s.readyState===WebSocket.OPEN).length")

        async def takeover_state(page: Any) -> dict[str, Any]:
            return await page.evaluate("""() => ({
                status: document.querySelector('#status').dataset.state,
                text: document.querySelector('#status .status-text').textContent,
                takeover: !document.querySelector('#takeover').hidden,
            })""")

        def events_since(observation: Observation, since: float) -> list[dict[str, Any]]:
            return [event for event in observation.events if event["time"] >= since]

        def welcomes(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return [event for event in events
                    if event["kind"] == "ws_received" and event["frame"].get("type") == "welcome"]

        def replaced_closes(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return [event for event in events if event["kind"] == "ws_close" and event["code"] == 4409]

        original, original_obs = pages[0]
        collision_start = time.monotonic()
        duplicate, duplicate_obs = await watch_page(original.context, ClientSpec("duplicate", 800, 600, 1), observations)
        captured_pages.append((duplicate, duplicate_obs))
        await duplicate.goto(base + "/client/")
        duplicate_obs.device_id = await connected(duplicate)
        # Longer than the client's 500 ms backoff floor: a page that intends to
        # retry has time to do it, so an observed stop is a real stop.
        await asyncio.sleep(3)

        original_events = events_since(original_obs, collision_start)
        duplicate_events = events_since(duplicate_obs, collision_start)
        loser = await takeover_state(original)
        bounded = (
            duplicate_obs.device_id == original_obs.device_id
            and len(replaced_closes(original_events + duplicate_events)) == 1
            and len(welcomes(duplicate_events)) == 1
            and not [event for event in original_events if event["kind"] == "ws_open"]
            and await open_sockets(original) == 0
            and loser == {"status": "replaced", "text": "Showing on another screen", "takeover": True}
        )
        report["ownership"] = {
            "status": "bounded" if bounded else "FAILED",
            "shared_id": duplicate_obs.device_id,
            "close_4409_count": len(replaced_closes(original_events + duplicate_events)),
            "welcome_count": len(welcomes(duplicate_events)),
            "loser": loser,
            "duration_seconds": time.monotonic() - collision_start,
        }
        check("taken-over page stops retrying and offers an explicit takeover", bounded,
              loser=loser, close_4409_count=len(replaced_closes(original_events + duplicate_events)),
              welcome_count=len(welcomes(duplicate_events)))
        await original.screenshot(path=str(artifacts / "takeover.png"))

        # One deliberate click moves ownership; the previous winner becomes the
        # stopped page. Nothing here is automatic.
        takeover_start = time.monotonic()
        await original.click("#takeover")
        await original.wait_for_function("document.querySelector('#status').dataset.state === 'connected'")
        await duplicate.wait_for_function("document.querySelector('#status').dataset.state === 'replaced'")
        await asyncio.sleep(1)
        original_after = events_since(original_obs, takeover_start)
        duplicate_after = events_since(duplicate_obs, takeover_start)
        duplicate_loser = await takeover_state(duplicate)
        transferred = (
            len(replaced_closes(original_after + duplicate_after)) == 1
            and len(welcomes(original_after)) == 1
            and not [event for event in duplicate_after if event["kind"] == "ws_open"]
            and await open_sockets(original) == 1
            and await open_sockets(duplicate) == 0
            and duplicate_loser == {"status": "replaced", "text": "Showing on another screen", "takeover": True}
        )
        report["ownership"]["takeover"] = {
            "status": "transferred" if transferred else "FAILED",
            "close_4409_count": len(replaced_closes(original_after + duplicate_after)),
            "loser": duplicate_loser,
        }
        check("explicit takeover moves ownership exactly once", transferred, loser=duplicate_loser)
        await duplicate.screenshot(path=str(artifacts / "takeover-loser.png"))

        # ------------------------------------------------------------------
        # P0: rectangle evidence, fullscreen, and the MP4 decode probe
        # ------------------------------------------------------------------

        async def measure_mode(page: Any) -> dict[str, Any]:
            return await page.evaluate("""() => {
                const c = document.querySelector('#surface');
                const r = c.getBoundingClientRect();
                const vv = window.visualViewport;
                return {
                    rect: {x: r.x, y: r.y, width: r.width, height: r.height},
                    backing: [c.width, c.height],
                    viewport: [innerWidth, innerHeight],
                    dpr: devicePixelRatio,
                    visualViewport: vv ? {width: vv.width, height: vv.height, scale: vv.scale,
                                          offsetLeft: vv.offsetLeft, offsetTop: vv.offsetTop} : null,
                    fullscreen: document.fullscreenElement ? document.fullscreenElement.tagName : null,
                    mode: document.fullscreenElement ? 'fullscreen' : 'tab',
                    surfaceDisplay: getComputedStyle(c).display,
                };
            }""")

        mode_page, mode_obs = pages[1]
        mode_spec = mode_obs.spec
        rectangles: dict[str, Any] = {"client": mode_spec.name, "status": "FAIL"}
        try:
            tab = await measure_mode(mode_page)
            rectangles["tab"] = tab
            button_hidden = await mode_page.evaluate(
                "document.getElementById('fs-toggle').hidden"
            )
            if button_hidden:
                rectangles.update({
                    "status": "MISSING",
                    "reason": "the client did not expose a fullscreen control in this engine",
                })
            else:
                # The control hides itself after five seconds and ignores the
                # pointer while hidden. A real click reveals it, and the next
                # click supplies the user activation requestFullscreen needs.
                await mode_page.mouse.click(10, 10)
                await mode_page.wait_for_selector('#fs-toggle[data-visible="true"]', timeout=5000)
                await mode_page.click("#fs-toggle")
                try:
                    await mode_page.wait_for_function(
                        "document.fullscreenElement !== null", timeout=5000
                    )
                except Exception as error:
                    rectangles.update({
                        "status": "MISSING",
                        "reason": f"engine refused fullscreen: {type(error).__name__}",
                    })
                else:
                    await asyncio.sleep(.2)
                    fullscreen = await measure_mode(mode_page)
                    await mode_page.screenshot(path=str(artifacts / "fullscreen.png"))
                    await mode_page.evaluate("document.exitFullscreen()")
                    await mode_page.wait_for_function(
                        "document.fullscreenElement === null", timeout=5000
                    )
                    await asyncio.sleep(.2)
                    restored = await measure_mode(mode_page)
                    rectangles["fullscreen"] = fullscreen
                    rectangles["restored"] = restored
                    exact = (
                        tab["rect"] == restored["rect"]
                        and tab["backing"] == restored["backing"]
                        and tab["viewport"] == restored["viewport"]
                        and fullscreen["mode"] == "fullscreen"
                        and fullscreen["surfaceDisplay"] != "none"
                        and abs(fullscreen["rect"]["width"] - fullscreen["viewport"][0]) <= 2
                        and abs(fullscreen["rect"]["height"] - fullscreen["viewport"][1]) <= 2
                        and fullscreen["backing"] == [
                            math.floor(fullscreen["rect"]["width"] * mode_spec.dpr + .5),
                            math.floor(fullscreen["rect"]["height"] * mode_spec.dpr + .5),
                        ]
                    )
                    rectangles["status"] = "PASS" if exact else "FAIL"
        except Exception as error:
            rectangles.update({
                "status": "FAIL",
                "reason": f"{type(error).__name__}: {error}",
            })
        report["p0"] = {"rectangles": rectangles, "rows": []}
        rows: list[dict[str, Any]] = report["p0"]["rows"]

        def p0_row(ident: str, status: str, expected: str, observed: Any,
                   reason: str = "", **extra: Any) -> None:
            rows.append({
                "id": ident, "status": status, "expected": expected,
                "observed": observed, "reason": reason, **extra,
            })

        probe_dir = root / "probe"
        probe_dir.mkdir()
        probe: dict[str, Any] = {"engine": f"Chromium {browser.version}",
                                 "delivery": "loopback HTTP with single byte-range support"}
        video_build = None
        try:
            write_probe_source(probe_dir / "bands.png")
            video_build = build_probe_video(probe_dir / "bands.png", probe_dir / "probe.mp4")
        except Exception as error:
            video_build = {"ok": False, "error": f"{type(error).__name__}: {error}"}
        probe["fixture"] = {
            "source": "320x180 RGB horizontal bands red/green/blue",
            "build": video_build,
            "ffprobe": probe_metadata(probe_dir / "probe.mp4") if video_build and video_build.get("ok") else None,
        }
        if video_build is None:
            p0_row("mp4_decode_playback", "MISSING", "H.264 decode and muted playback",
                   None, "ffmpeg is not installed; no fixture could be encoded")
            probe["status"] = "MISSING"
        elif not video_build.get("ok"):
            p0_row("mp4_decode_playback", "FAIL", "H.264 fixture encodes",
                   video_build.get("error"), "ffmpeg failed to encode the fixture")
            probe["status"] = "FAIL"
        else:
            (probe_dir / "probe.html").write_text(PROBE_PAGE, encoding="utf-8")
            probe_server, probe_thread, probe_origin = start_probe_server(probe_dir)
            probe_page = None
            try:
                probe_page = await browser.new_page(viewport={"width": 420, "height": 320},
                                                    device_scale_factor=1)
                await probe_page.goto(probe_origin + "/probe.html")
                await probe_page.wait_for_function(
                    "window.probe.video.readyState >= 2 && Number.isFinite(window.probe.video.duration)",
                    timeout=10000,
                )
                metadata = await probe_page.evaluate("""() => {
                    const v = window.probe.video;
                    return {readyState: v.readyState, duration: v.duration,
                            width: v.videoWidth, height: v.videoHeight,
                            canPlay: v.canPlayType('video/mp4; codecs="avc1.42E01E"')};
                }""")
                await probe_page.evaluate("""() => {
                    const v = window.probe.video;
                    window.__frames = 0;
                    if (v.requestVideoFrameCallback) {
                        const count = () => { window.__frames++; v.requestVideoFrameCallback(count); };
                        v.requestVideoFrameCallback(count);
                    }
                    return v.play();
                }""")
                await probe_page.wait_for_function(
                    "window.probe.video.currentTime > 0.4", timeout=10000
                )
                playing = await probe_page.evaluate("""() => {
                    const v = window.probe.video;
                    return {currentTime: v.currentTime, paused: v.paused, ended: v.ended,
                            readyState: v.readyState,
                            buffered: v.buffered.length ? [v.buffered.start(0), v.buffered.end(0)] : null,
                            decodedFrames: v.getVideoPlaybackQuality ? v.getVideoPlaybackQuality().totalVideoFrames : null,
                            callbackFrames: window.__frames};
                }""")
                await probe_page.evaluate("window.probe.video.pause()")
                probe["playback"] = {"metadata": metadata, "playing": playing}
                playback_ok = (
                    playing["currentTime"] > 0.4
                    and not playing["paused"]
                    and (playing["decodedFrames"] or 0) > 0
                    and (playing["callbackFrames"] or 0) > 0
                )
                p0_row("mp4_decode_playback", "PASS" if playback_ok else "FAIL",
                       "metadata, resolved muted play, advancing time, decoded frames",
                       {"metadata": metadata, "playing": playing})

                await probe_page.evaluate("window.probe.video.currentTime = 1.2")
                try:
                    await probe_page.wait_for_function(
                        "Math.abs(window.probe.video.currentTime - 1.2) <= 0.15 "
                        "&& !window.probe.video.seeking",
                        timeout=5000,
                    )
                except Exception:
                    pass
                sought = await probe_page.evaluate(
                    "({time: window.probe.video.currentTime, seeking: window.probe.video.seeking})"
                )
                seek_ok = abs(sought["time"] - 1.2) <= 0.15 and not sought["seeking"]
                probe["seek"] = {"target": 1.2, "observed": sought}
                p0_row("mp4_seek", "PASS" if seek_ok else "FAIL",
                       "seek to 1.2 s completes within 0.15 s", sought)

                async def sample_screenshot(name: str, points: dict[str, tuple[int, int]]) -> dict[str, Any]:
                    path = artifacts / name
                    await probe_page.screenshot(path=str(path))
                    image = Image.open(path).convert("RGB")
                    return {label: image.getpixel(xy) for label, xy in points.items()}

                unrotated = await sample_screenshot("p0-mp4-bands.png", {
                    "red": (80, 15), "green": (80, 45), "blue": (80, 75),
                    "outside": (80, 120), "clipped": (240, 15), "clip-outside": (300, 15),
                })
                near = lambda seen, want: all(abs(a - b) <= 40 for a, b in zip(seen, want))
                clip_ok = (
                    near(unrotated["red"], PROBE_BANDS[0])
                    and near(unrotated["green"], PROBE_BANDS[1])
                    and near(unrotated["blue"], PROBE_BANDS[2])
                    and max(unrotated["outside"]) <= 24
                    and near(unrotated["clipped"], PROBE_BANDS[0])
                    and max(unrotated["clip-outside"]) <= 24
                )
                await probe_page.evaluate("""() => {
                    const v = window.probe.video;
                    v.style.transformOrigin = '0 0';
                    v.style.transform = 'translate(0, 160px) rotate(-90deg)';
                }""")
                await asyncio.sleep(.2)
                rotated = await sample_screenshot("p0-mp4-rotated.png", {
                    "red": (15, 80), "green": (45, 80), "outside": (120, 80),
                })
                rotation_ok = (
                    near(rotated["red"], PROBE_BANDS[0])
                    and near(rotated["green"], PROBE_BANDS[1])
                    and max(rotated["outside"]) <= 24
                )
                probe["compositor"] = {"unrotated": unrotated, "rotated": rotated}
                p0_row("mp4_clip_rotation", "PASS" if clip_ok and rotation_ok else "FAIL",
                       "screenshot pixels prove clip and quarter-turn",
                       {"unrotated": unrotated, "rotated": rotated})

                loop = await probe_page.evaluate("""() => {
                    const v = window.probe.video;
                    v.style.transform = '';
                    v.loop = true;
                    v.currentTime = 1.9;
                    const samples = [];
                    let last = null;
                    let lastNow = performance.now();
                    const started = lastNow;
                    function tick(now) {
                        const t = v.currentTime;
                        samples.push(t);
                        if (last !== null && t + 0.1 < last) {
                            window.__wrap = {from: last, to: t, gapMs: now - lastNow,
                                             samples: samples.length};
                        }
                        last = t; lastNow = now;
                        if (now - started < 3000) requestAnimationFrame(tick);
                    }
                    window.__wrap = null;
                    requestAnimationFrame(tick);
                    return v.play();
                }""")
                await asyncio.sleep(2.6)
                wrap = await probe_page.evaluate("window.__wrap")
                loop_ok = bool(wrap) and wrap["gapMs"] <= 250
                probe["loop"] = {"wrap": wrap, "definition": "rAF sample interval between media-time decrease; software sampling, not optical"}
                p0_row("mp4_loop_gap", "PASS" if loop_ok else "FAIL",
                       "a loop wrap is observed and the sampled restart gap is at most 250 ms",
                       wrap, "not an optical or visible-gap measurement",
                       sampling="requestAnimationFrame, about 16.7 ms")
                probe["status"] = "PASS" if (
                    len([row for row in rows if row["id"].startswith("mp4_")]) == 4
                    and all(row["status"] == "PASS" for row in rows if row["id"].startswith("mp4_"))
                ) else "FAIL"
            except Exception as error:
                probe["status"] = "FAIL"
                probe["error"] = f"{type(error).__name__}: {error}"
                if not any(row["id"].startswith("mp4_") and row["status"] == "PASS" for row in rows):
                    p0_row("mp4_decode_playback", "FAIL", "H.264 decode probe runs",
                           probe["error"], "the probe raised before completing")
            finally:
                if probe_page is not None:
                    await probe_page.close()
                probe_server.shutdown()
                probe_thread.join(5)
        report["p0"]["video"] = probe

        # ------------------------------------------------------------------
        # R1: upload through the real controller and show it on real clients
        # ------------------------------------------------------------------

        upload_path = root / "r1-upload.jpg"
        Image.new("RGB", (640, 360), (200, 30, 160)).save(
            upload_path, format="JPEG", quality=95
        )
        bad_path = root / "not-an-image.txt"
        bad_path.write_text("this is not an image", encoding="utf-8")

        async def canvas_centre(page: Any) -> tuple[int, int, int]:
            encoded = await page.locator("#surface").evaluate("c => c.toDataURL('image/png')")
            image = Image.open(io.BytesIO(base64.b64decode(encoded.split(",", 1)[1]))).convert("RGB")
            return image.getpixel((image.width // 2, image.height // 2))

        async def canvas_pixel(page: Any, x: int, y: int) -> tuple[int, int, int]:
            encoded = await page.locator("#surface").evaluate("c => c.toDataURL('image/png')")
            image = Image.open(io.BytesIO(base64.b64decode(encoded.split(",", 1)[1]))).convert("RGB")
            return image.getpixel((x, y))

        async def wait_for_colour(page: Any, wanted: tuple[int, int, int]) -> tuple[int, int, int]:
            deadline = time.monotonic() + 10
            seen = (0, 0, 0)
            while time.monotonic() < deadline:
                seen = await canvas_centre(page)
                if max(abs(a - b) for a, b in zip(seen, wanted)) <= 25:
                    return seen
                await asyncio.sleep(.1)
            return seen

        r1: dict[str, Any] = {}
        await controller.wait_for_selector("#upload-block:not([hidden])", timeout=10000)
        await controller.set_input_files("#upload-file", str(upload_path))
        await controller.click("#btn-upload")
        await controller.wait_for_function(
            "document.querySelector('#upload-status').textContent.startsWith('Ready:')",
            timeout=30000,
        )
        ready_text = await controller.locator("#upload-status").text_content()
        r1["ready_text"] = ready_text
        check("controller upload reports a ready image", ready_text == "Ready: r1-upload.jpg",
              text=ready_text)

        wall_before = await api("GET", "/wall")
        async with controller.expect_response(
            lambda response: response.url == base + "/scene"
            and response.request.method == "PUT"
        ) as changed:
            await controller.click("#btn-image-apply")
        check("controller upload apply response", (await changed.value).ok)
        wall_after = await api("GET", "/wall")
        uploaded_id = wall_after["scene"]["content"]["asset"]
        r1["asset"] = uploaded_id
        check("uploaded asset replaces the curated scene",
              uploaded_id != wall_before["scene"]["content"].get("asset")
              and uploaded_id.startswith("sha256:"))
        check("controller active image names the upload",
              "r1-upload.jpg" in (await controller.locator("#image-active-text").text_content() or ""))
        library = (await api("GET", "/media"))["assets"]
        check("uploaded library lists exactly the new image",
              [entry["name"] for entry in library] == ["r1-upload.jpg"], library=library)

        colours = {}
        for page, observation in pages:
            colours[observation.spec.name] = await wait_for_colour(page, (200, 30, 160))
        r1["colours"] = colours
        check("every client paints the uploaded image",
              all(max(abs(a - b) for a, b in zip(colour, (200, 30, 160))) <= 25
                  for colour in colours.values()), colours=colours)
        await controller.screenshot(path=str(artifacts / "controller-upload.png"), full_page=True)

        before_bad = (await api("GET", "/wall"))["scene"]["content"]["asset"]
        r1_rejection_start = time.monotonic()
        await controller.set_input_files("#upload-file", str(bad_path))
        await controller.click("#btn-upload")
        await controller.wait_for_function(
            "document.querySelector('#upload-status').textContent.startsWith('Upload failed:')",
            timeout=15000,
        )
        failure_text = await controller.locator("#upload-status").text_content()
        r1["failure_text"] = failure_text
        after_bad = (await api("GET", "/wall"))["scene"]["content"]["asset"]
        check("a rejected upload says why and changes nothing",
              failure_text.startswith("Upload failed:") and before_bad == after_bad,
              text=failure_text)
        # Restore proof: back up this run's data, restore into new targets,
        # start a second disposable server, and paint the restored bytes in a
        # real client. This closes the R1 requirement that a restore is shown,
        # not merely hash-checked.
        backup_dest = root / "r1-backup"
        restored_root = root / "restored"
        restored_root.mkdir()
        (restored_root / "tmp").mkdir()
        backup_run = subprocess.run(
            [sys.executable, str(REPO / "deploy" / "backup.py"), "backup",
             "--db", str(root / "wall.db"), "--assets", str(root / "assets"),
             "--media", str(root / "media"), "--dest", str(backup_dest)],
            cwd=REPO, capture_output=True, text=True, timeout=120,
        )
        check("backup of the live run succeeds", backup_run.returncode == 0,
              stderr=backup_run.stderr[-1000:])
        restore_run = subprocess.run(
            [sys.executable, str(REPO / "deploy" / "backup.py"), "restore",
             "--src", str(backup_dest), "--db", str(restored_root / "wall.db"),
             "--assets", str(restored_root / "assets"),
             "--media", str(restored_root / "media")],
            cwd=REPO, capture_output=True, text=True, timeout=120,
        )
        check("restore into new targets succeeds", restore_run.returncode == 0,
              stderr=restore_run.stderr[-1000:])

        restored_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        restored_listener.bind(("127.0.0.1", 0))
        restored_listener.listen(128)
        restored_base = f"http://127.0.0.1:{restored_listener.getsockname()[1]}"
        restored_env = child_environment(restored_root)
        restored_env["TABLET_WALL_UPLOAD_MODE"] = "disabled"
        restored_env.pop("TABLET_WALL_OPERATOR_ORIGIN", None)
        restored_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--fd",
             str(restored_listener.fileno()), "--workers", "1", "--no-access-log"],
            cwd=REPO, env=restored_env, pass_fds=(restored_listener.fileno(),),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        restored_context = None
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    if httpx.get(restored_base + "/wall", timeout=.5).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError("restored server did not become ready")
                await asyncio.sleep(.1)
            restored_http = httpx.Client(base_url=restored_base, timeout=5)
            try:
                restored_context = await browser.new_context(
                    viewport={"width": 800, "height": 600}, device_scale_factor=1
                )
                restored_id = str(uuid.uuid4())
                registration = restored_http.post("/devices/register", json={
                    "device_id": restored_id, "width": 800, "height": 600,
                    "device_type": "restored",
                })
                placement = restored_http.put(
                    f"/devices/{restored_id}/placement",
                    json={"x": 0, "y": 0, "w": 1200, "h": 800},
                )
                check("restored device registers and is placed",
                      registration.status_code == 200 and placement.status_code == 200,
                      registration=registration.status_code,
                      placement=placement.status_code)
                restored_page, restored_obs = await watch_page(
                    restored_context, ClientSpec("restored", 800, 600, 1), observations
                )
                captured_pages.append((restored_page, restored_obs))
                await restored_page.add_init_script(
                    f"localStorage.setItem('tablet-wall-device-id', '{restored_id}')"
                )
                await restored_page.goto(restored_base + "/client/")
                restored_obs.device_id = await connected(restored_page)
                restored_colour = await wait_for_colour(restored_page, (200, 30, 160))
                served = restored_http.get(f"/assets/{uploaded_id}")
                check(
                    "a restored upload is served and painted by a real client",
                    max(abs(a - b) for a, b in zip(restored_colour, (200, 30, 160))) <= 25
                    and served.status_code == 200
                    and len(served.content) == library[0]["bytes"],
                    colour=restored_colour, status=served.status_code,
                )
                r1["restore"] = {"colour": restored_colour,
                                 "asset": uploaded_id,
                                 "bytes": len(served.content)}
                await restored_page.screenshot(
                    path=str(artifacts / "restored-client.png")
                )
            finally:
                restored_http.close()
        finally:
            if restored_context is not None:
                await restored_context.close()
            restored_process.terminate()
            try:
                restored_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                restored_process.kill()
                restored_process.wait(timeout=5)
            restored_listener.close()

        report["r1"] = r1

        # ------------------------------------------------------------------
        # R2: one calibrated physical client paints the hand-derived matrix
        # ------------------------------------------------------------------

        await controller.close()
        physical_source = root / "physical.png"
        physical = Image.new("RGB", (400, 240), (10, 20, 60))
        physical.paste((220, 20, 20), (80, 120, 120, 160))
        physical.paste((20, 200, 20), (280, 40, 320, 80))
        # Case 2 maps source (200,200) to the panel centre at backing (50,30).
        physical.paste((240, 220, 20), (180, 180, 220, 220))
        physical.save(physical_source)
        physical_http = httpx.Client(base_url=base, headers={"Origin": base}, timeout=10)
        physical_context = None
        try:
            uploaded_physical = physical_http.post(
                "/uploads?name=physical.png", content=physical_source.read_bytes(),
                headers={"Content-Type": "image/png"},
            )
            check("physical fixture uploads", uploaded_physical.status_code == 201,
                  text=uploaded_physical.text[-500:])
            physical_asset = uploaded_physical.json()["asset"]["id"]
            scene = physical_http.put("/scene", json={
                "content": {"type": "image", "asset": physical_asset, "fit": "cover"},
            })
            check("physical fixture scene is set", scene.status_code == 200, text=scene.text)

            physical_context = await browser.new_context(
                viewport={"width": 300, "height": 180}, device_scale_factor=1
            )
            resources.append(physical_context)
            physical_page, physical_obs = await watch_page(
                physical_context, ClientSpec("physical", 300, 180, 1), observations
            )
            captured_pages.append((physical_page, physical_obs))
            await physical_page.goto(base + "/client/")
            physical_obs.device_id = await connected(physical_page)

            config = physical_http.get("/api/v3/config").json()
            display = physical_http.put(
                f"/api/v3/displays/{physical_obs.device_id}",
                json={
                    "active_width_mm": 100, "active_height_mm": 60,
                    "bezels": {"left": 0, "top": 0, "right": 0, "bottom": 0},
                    "label": "physical fixture", "provenance": "hand-derived",
                },
                headers={"If-Match": config["etag"]},
            )
            check("physical display measurement accepted", display.status_code == 200,
                  text=display.text[-500:])
            calibration = physical_http.put(
                f"/api/v3/calibrations/{physical_obs.device_id}",
                json={
                    "profile_revision": 1, "viewport_width": 300,
                    "viewport_height": 180, "dpr": 1, "orientation": 0,
                    "mode": "tab", "quarter_turn": 0,
                    "panel_offset_mm": [0, 0], "mm_per_css": [0.5, 0.5],
                    "anchor_edge": "top-left", "uncertainty_mm": 0,
                    "method": "hand-derived",
                },
                headers={"If-Match": display.json()["etag"]},
            )
            check("physical calibration accepted", calibration.status_code == 200,
                  text=calibration.text[-500:])
            layout = physical_http.put(
                "/api/v3/layout",
                json={
                    "bounds": {"x": 0, "y": 0, "width": 200, "height": 120},
                    "slots": {
                        physical_obs.device_id: {
                            "center_x_mm": 100, "center_y_mm": 100,
                            "mount_angle": 180, "nudge_x_mm": 0, "nudge_y_mm": 0,
                            "profile_revision": 1, "calibration_revision": 1,
                            "participating": True,
                        }
                    },
                },
                headers={"If-Match": calibration.json()["etag"]},
            )
            check("physical layout accepted", layout.status_code == 200,
                  text=layout.text[-500:])

            deadline = time.monotonic() + 10
            yellow = (0, 0, 0)
            while time.monotonic() < deadline:
                yellow = await canvas_pixel(physical_page, 100, 60)
                if max(abs(a - b) for a, b in zip(yellow, (240, 220, 20))) <= 30:
                    break
                await asyncio.sleep(.1)
            check("calibrated physical client paints the source centre", max(
                abs(a - b) for a, b in zip(yellow, (240, 220, 20))
            ) <= 30, colour=yellow)
            outside = await canvas_pixel(physical_page, 250, 150)
            check("physical panel clip leaves the rest of the canvas neutral",
                  max(abs(a - b) for a, b in zip(outside, (11, 17, 32))) <= 12,
                  colour=outside)
            report["r2"] = {
                "client": physical_obs.device_id,
                "asset": physical_asset,
                "panel_centre": yellow,
                "outside_clip": outside,
                "matrix": "[-1,0,0,-1,300,260] source 400x240 -> backing 300x180; panel clip 0..200 x 0..120",
            }
            await physical_page.screenshot(path=str(artifacts / "physical-client.png"))

            # A viewport change that no calibration covers must remove the
            # physical claim instead of repainting a stale plan.
            await physical_page.set_viewport_size({"width": 240, "height": 140})
            await asyncio.sleep(1)
            stale = await canvas_pixel(physical_page, 100, 60)
            report["r2"]["stale_viewport"] = stale
            check("a stale viewport removes the physical claim",
                  max(abs(a - b) for a, b in zip(stale, (240, 220, 20))) > 30,
                  colour=stale)

            editor_context = await browser.new_context(
                viewport={"width": 1280, "height": 900}, device_scale_factor=1
            )
            resources.append(editor_context)
            editor_page, editor_obs = await watch_page(
                editor_context, ClientSpec("editor", 1280, 900, 1), observations
            )
            captured_pages.append((editor_page, editor_obs))
            await editor_page.goto(base + "/controller/physical.html")
            await editor_page.wait_for_selector("#stage-svg [data-device-id]", timeout=10000)
            await editor_page.locator("#stage-svg [data-device-id]").first.click()
            await editor_page.click("#btn-rotate")
            angle_after_rotate = await editor_page.locator("#slot-angle").input_value()
            async with editor_page.expect_response(
                lambda response: response.url == base + "/api/v3/layout"
                and response.request.method == "PUT"
            ) as applied:
                await editor_page.click("#btn-apply")
            check("physical editor rotates and applies a slot",
                  (await applied.value).ok and angle_after_rotate.strip() == "270",
                  angle=angle_after_rotate)
            config_after = physical_http.get("/api/v3/config").json()
            check("applied editor pose is the server pose",
                  config_after["layout"]["slots"][physical_obs.device_id]["mount_angle"] == 270,
                  angle=config_after["layout"]["slots"][physical_obs.device_id]["mount_angle"])
            report["r2"]["editor"] = {"angle": angle_after_rotate}
            await editor_page.screenshot(path=str(artifacts / "physical-editor.png"), full_page=True)

            # ------------------------------------------------------------------
            # R3: two hard cuts on the calibrated still client
            # ------------------------------------------------------------------

            await physical_page.set_viewport_size({"width": 300, "height": 180})
            current = physical_http.get("/api/v3/config").json()
            restored_layout = physical_http.put(
                "/api/v3/layout",
                json={
                    "bounds": {"x": 0, "y": 0, "width": 200, "height": 120},
                    "slots": {
                        physical_obs.device_id: {
                            "center_x_mm": 100, "center_y_mm": 100,
                            "mount_angle": 180, "nudge_x_mm": 0, "nudge_y_mm": 0,
                            "profile_revision": 1, "calibration_revision": 1,
                            "participating": True,
                        }
                    },
                },
                headers={"If-Match": current["etag"]},
            )
            check("playback fixture layout restored",
                  restored_layout.status_code == 200, text=restored_layout.text[-500:])
            deadline = time.monotonic() + 10
            restored_colour = (0, 0, 0)
            while time.monotonic() < deadline:
                restored_colour = await canvas_pixel(physical_page, 100, 60)
                if max(abs(a - b) for a, b in zip(
                    restored_colour, (240, 220, 20)
                )) <= 30:
                    break
                await asyncio.sleep(.1)
            check("physical plan returns after the viewport is restored",
                  max(abs(a - b) for a, b in zip(restored_colour, (240, 220, 20))) <= 30,
                  colour=restored_colour)

            green_source = root / "green.png"
            Image.new("RGB", (400, 240), (20, 200, 60)).save(green_source)
            green_upload = physical_http.post(
                "/uploads?name=green.png", content=green_source.read_bytes(),
                headers={"Content-Type": "image/png"},
            )
            check("playback green fixture uploads", green_upload.status_code == 201,
                  text=green_upload.text[-500:])
            green_asset = green_upload.json()["asset"]["id"]
            playlist_before = physical_http.get("/api/v3/playlist").json()
            saved_playlist = physical_http.put(
                "/api/v3/playlist",
                json={
                    "items": [
                        {"asset": physical_asset, "dwell_ms": 1500},
                        {"asset": green_asset, "dwell_ms": 1500},
                    ],
                    "loop": True,
                },
                headers={"If-Match": playlist_before["etag"]},
            )
            check("hard-cut playlist saves", saved_playlist.status_code == 200,
                  text=saved_playlist.text[-500:])
            await asyncio.sleep(1.5)  # let the clock sampler finish its burst
            started = physical_http.post("/api/v3/playback/start")
            check("playback starts", started.status_code == 200, text=started.text[-500:])

            observed = []
            deadline = time.monotonic() + 20
            last = "yellow"  # the pre-playback still is already on screen
            while time.monotonic() < deadline and len(observed) < 2:
                colour = await canvas_pixel(physical_page, 100, 60)
                label = None
                if max(abs(a - b) for a, b in zip(colour, (20, 200, 60))) <= 30:
                    label = "green"
                elif max(abs(a - b) for a, b in zip(colour, (240, 220, 20))) <= 30:
                    label = "yellow"
                if label is not None and label != last:
                    observed.append({"colour": label, "time": time.monotonic()})
                    last = label
                await asyncio.sleep(.05)
            report["r3"] = {
                "playlist": saved_playlist.json()["playlist"],
                "observed": [entry["colour"] for entry in observed],
                "software_only": True,
                "note": "polled canvas onset; no camera or optical claim",
            }
            check("two hard cuts reach the calibrated client",
                  [entry["colour"] for entry in observed][:2] == ["green", "yellow"],
                  observed=observed)

            await editor_page.click("#btn-playback-refresh")
            await editor_page.wait_for_function(
                "document.querySelector('#playback-status').textContent.includes('playing')",
                timeout=5000,
            )
            await editor_page.click("#btn-playback-pause")
            await editor_page.wait_for_function(
                "document.querySelector('#playback-status').textContent.includes('paused')",
                timeout=5000,
            )
            await editor_page.click("#btn-playback-stop")
            await editor_page.wait_for_function(
                "document.querySelector('#playback-status').textContent.includes('stopped')",
                timeout=5000,
            )
            check("playback pause and stop work from the controller",
                  physical_http.get("/api/v3/playback").json().get("state") == "stopped")
        finally:
            physical_http.close()


        for observation in observations:
            errors = [event for event in observation.events if (
                event["kind"] in ("page_error", "request_failed", "ws_error")
                or (event["kind"] == "console" and event["level"] in ("warning", "error"))
                or (event["kind"] == "http" and event["status"] >= 400)
                or (event["kind"] == "ws_close" and event["code"] not in (1000, 1001))
            ) and not (
                (event["kind"] == "ws_close" and event["code"] == 4409
                 and observation.spec.name in ("landscape", "duplicate")
                 and event["time"] >= collision_start)
                or (event["kind"] == "http"
                    and event["url"].endswith("/uploads?name=not-an-image.txt")
                    and event["status"] == 415)
                or (event["kind"] == "console" and event["time"] >= r1_rejection_start
                    and event["text"].startswith("Failed to load resource")
                    and "415" in event["text"])
            )]
            check(observation.spec.name + " no unexpected browser errors", not errors, errors=errors)

        # ------------------------------------------------------------------
        # P0 evidence matrix: one row per experiment, PASS / FAIL / MISSING
        # ------------------------------------------------------------------

        def named(name: str) -> bool:
            return any(entry["name"] == name and entry["passed"] for entry in checks)

        tab = rectangles.get("tab")
        tab_ok = bool(tab) and (
            abs(tab["rect"]["width"] - mode_spec.width) <= 0.5
            and abs(tab["rect"]["height"] - mode_spec.height) <= 0.5
            and tab["backing"] == [math.floor(mode_spec.width * mode_spec.dpr + .5),
                                   math.floor(mode_spec.height * mode_spec.dpr + .5)]
        )
        p0_row("rectangles_tab", "PASS" if tab_ok else "FAIL",
               "visible canvas rect equals the viewport and backing equals DPR times rect",
               tab)
        if rectangles["status"] == "PASS":
            p0_row("rectangles_fullscreen", "PASS",
                   "fullscreenElement is set and the canvas fills the viewport",
                   rectangles.get("fullscreen"))
        else:
            p0_row("rectangles_fullscreen", rectangles["status"],
                   "fullscreenElement is set and the canvas fills the viewport",
                   rectangles.get("fullscreen"), rectangles.get("reason", ""))
        p0_row("rectangles_standalone", "MISSING",
               "standalone launch rectangle measured", None,
               "no installed standalone launch was tested; fullscreen is not standalone")
        p0_row("tablet_sleep_clock", "MISSING",
               "browser clock behavior across real tablet suspend", None,
               "no physical tablet is available to suspend")
        p0_row("host_suspend_clock", "MISSING",
               "host suspend behavior of the browser and server clocks", None,
               "no host suspend was performed")
        p0_row("physical_ipad", "MISSING", "physical iPad decode, activation and orientation",
               None, "no physical iPad is attached or inventoried")
        p0_row("physical_android", "MISSING", "physical Android decode and activation",
               None, "no physical Android is attached or inventoried")
        p0_row("optical_sync", "MISSING", "wall-wide optical onset and seam measurement",
               None, "no camera or capture hardware is attached")
        p0_row("two_origin_ingress", "MISSING", "requests through both ingress origins",
               None, "this runner uses one disposable direct backend, not an ingress proxy")
        p0_row("software_identity", "PASS" if named("three independent same-origin identities") else "FAIL",
               "three independent contexts hold three identities", 3)
        p0_row("software_reload", "PASS" if all(
            named(observation.spec.name + " reload retains ID") for _, observation in pages
        ) else "FAIL", "reload preserves identity within a context", None)
        p0_row("software_persistent_profile",
               "PASS" if named("persistent profile in a separate browser process") else "FAIL",
               "persistent profile runs in its own browser process", None)
        p0_row("software_still_pixels", "PASS" if all(
            named(observation.spec.name + " initial pixels")
            and named(observation.spec.name + " reload pixels")
            for _, observation in pages
        ) else "FAIL", "canvas pixels match the independent oracle", None)
        p0_row("software_ownership",
               "PASS" if named("taken-over page stops retrying and offers an explicit takeover")
               and named("explicit takeover moves ownership exactly once") else "FAIL",
               "4409 stops the loser and one deliberate click transfers ownership", None)
        p0_row("software_baseline", "PASS" if all(entry["passed"] for entry in checks) else "FAIL",
               "every required software check passes", len(checks))

        required_rows = {
            "rectangles_tab", "rectangles_fullscreen", "rectangles_standalone",
            "mp4_decode_playback", "mp4_seek", "mp4_clip_rotation", "mp4_loop_gap",
            "tablet_sleep_clock", "host_suspend_clock", "physical_ipad",
            "physical_android", "optical_sync", "two_origin_ingress",
            "software_identity", "software_reload", "software_persistent_profile",
            "software_still_pixels", "software_ownership", "software_baseline",
        }
        present = {row["id"] for row in rows}
        missing_required = sorted(required_rows - present)
        check("P0 matrix names every required experiment", not missing_required,
              missing=missing_required)
        failed_rows = [row for row in rows if row["status"] == "FAIL"]
        check("P0 has no failed software experiment", not failed_rows,
              failed=[{"id": row["id"], "reason": row["reason"]} for row in failed_rows])
        unexplained = [row["id"] for row in rows
                       if row["status"] == "MISSING" and not row["reason"].strip()]
        check("P0 missing rows name their prerequisite", not unexplained, unexplained=unexplained)
        report["p0"]["status"] = "FAIL" if failed_rows else (
            "PASS_WITH_MISSING_HARDWARE" if any(row["status"] == "MISSING" for row in rows)
            else "PASS"
        )
    except BaseException:
        for page, observation in captured_pages:
            try:
                await page.screenshot(path=str(artifacts / f"{observation.spec.name}-failure.png"), timeout=2000)
            except Exception as error:
                observation.event("failure_screenshot_unavailable", error=str(error))
        raise
    finally:
        async def cleanup() -> None:
            nonlocal owned_processes

            owned_processes.update(descendants(os.getpid()))
            cleanup_errors = []
            for resource in reversed(resources):
                try:
                    if hasattr(resource, "dispose"):
                        await resource.dispose()
                    else:
                        await resource.close()
                except Exception as error:
                    cleanup_errors.append(str(error))
            if playwright is not None:
                try:
                    await playwright.stop()
                except Exception as error:
                    cleanup_errors.append(str(error))
            try:
                stop_server(process)
            except Exception as error:
                cleanup_errors.append(str(error))
            if listener is not None:
                listener.close()
            if log is not None:
                log.close()
            try:
                shutil.rmtree(root)
            except Exception as error:
                cleanup_errors.append(str(error))
            owned_processes = {pid: birth for pid, birth in owned_processes.items() if pid not in initial_processes}
            table = process_table()
            remaining = {pid: birth for pid, birth in owned_processes.items() if table.get(pid, (None, None))[1] == birth}
            report["cleanup"] = {"server_reaped": process is None or process.returncode is not None,
                                 "server_returncode": process.returncode if process else None,
                                 "owned_processes": owned_processes, "remaining_processes": remaining,
                                 "temporary_root_removed": not root.exists(), "errors": cleanup_errors}
            check("cleanup reaps server and browser processes and removes data", not remaining and not root.exists()
                  and not cleanup_errors and (process is None or process.returncode is not None))

        cleanup_task = asyncio.create_task(cleanup())
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError:
            await cleanup_task
            raise


GAPS = [
    {"experiment": name, "status": "MISSING", "reason": reason}
    for name, reason in (
        ("physical old/new iPad", "No physical iPad attached or inventoried. Chromium is not iOS Safari."),
        ("physical Android", "No physical Android attached or inventoried."),
        ("MP4 decoding", "Current app has no video player. No MP4 decode experiment performed."),
        ("sleep/wake", "No physical foreground, OS sleep, wake-lock or resume experiment performed."),
        ("optical synchronization", "No camera capture or panel timing measurement performed."),
        ("two-origin ingress", "Direct disposable backend only. No isolated ingress proxy in T1."),
    )
]


async def run_with_signals(artifacts: Path, report: dict[str, Any]) -> None:
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()

    def cancel(signum: signal.Signals) -> None:
        if not task.cancelling():
            task.cancel(f"signal {signum.name}")

    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, cancel, signum)
    try:
        await exercise(artifacts, report, 6)
    finally:
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(signum)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, help="new directory outside the repository; default new directory in /tmp")
    args = parser.parse_args()
    try:
        artifacts = artifact_directory(args.artifacts)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    started = time.monotonic()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    try:
        diff = subprocess.check_output(["git", "diff", "HEAD"], cwd=REPO)
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=REPO, text=True
        ).splitlines()
    except subprocess.CalledProcessError:
        diff, status = b"", []
    report: dict[str, Any] = {"checks": [], "evidence_gaps": GAPS, "seed": "coded-grid-v1",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "app_head": head,
        "worktree": {"dirty": bool(diff), "diff_sha256": hashlib.sha256(diff).hexdigest(),
                     "status": status},
        "python": sys.version,
        "platform": sys.platform,
        "shared_resources": ["host scheduler", "GPU", "host clock", "NIC"],
        "mode": "unmodified-clock direct TCP Chromium, tab mode, logical stills"}

    try:
        report["playwright"] = importlib.metadata.version("playwright")
        asyncio.run(run_with_signals(artifacts, report))
    except BaseException as error:
        report["failure"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
    report["duration_seconds"] = time.monotonic() - started
    report["exit_code"] = int("failure" in report or not report["checks"] or any(not check["passed"] for check in report["checks"]))
    report["clients"] = [asdict(observation) for observation in report.get("clients", [])]
    with (artifacts / "report.json").open("x") as output:
        json.dump(report, output, indent=2)
    print(f"browser T1: {sum(check['passed'] for check in report['checks'])}/{len(report['checks'])} checks passed; report {artifacts / 'report.json'}")
    if "failure" in report:
        print(report["failure"]["message"], file=sys.stderr)
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
