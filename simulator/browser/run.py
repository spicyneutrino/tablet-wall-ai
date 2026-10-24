"""Disposable Chromium evidence for the current logical still-image wall."""

from __future__ import annotations

import argparse
import asyncio
import base64
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
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

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


def expected_pixel(name: str, bx: int, by: int) -> tuple[int, int, int]:
    """Hand-derived inverse maps for these fixed placements, sampled at pixel centers.

    The 1600x800 source covers a 1200x800 wall, hiding 200 source columns
    on either side. Landscape crops 175 wall rows above and below its
    600x800 placement. Portrait maps its right-hand placement one to one.
    The third viewport covers the whole wall by its height, 601/800.
    No application or simulator geometry implementation is imported.
    """
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
            response = await request.fetch(path, method=method, data=data)
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

        original, original_obs = pages[0]
        collision_start = time.monotonic()
        duplicate, duplicate_obs = await watch_page(original.context, ClientSpec("duplicate", 800, 600, 1), observations)
        captured_pages.append((duplicate, duplicate_obs))
        await duplicate.goto(base + "/client/")
        duplicate_obs.device_id = await connected(duplicate)
        await asyncio.sleep(3)
        collision_events = [event for obs in (original_obs, duplicate_obs) for event in obs.events if event["time"] >= collision_start]
        closes = [event for event in collision_events if event["kind"] == "ws_close" and event["code"] == 4409]
        welcomes = [event for event in collision_events if event["kind"] == "ws_received" and event["frame"].get("type") == "welcome"]
        contention = duplicate_obs.device_id == original_obs.device_id and len(closes) >= 2 and len(welcomes) >= 3
        report["collision"] = {"status": "BASELINE known issue for T2" if contention else "baseline reproduction FAILED",
                               "shared_id": duplicate_obs.device_id, "close_4409_count": len(closes),
                               "welcome_count": len(welcomes), "duration_seconds": time.monotonic() - collision_start,
                               "expected_future_behavior": "T2 stops automatic ownership contention after 4409"}
        check("duplicate-page T2 baseline reproduced", contention)
        await duplicate.screenshot(path=str(artifacts / "duplicate.png"))

        for observation in observations:
            errors = [event for event in observation.events if event["kind"] in ("page_error", "request_failed", "ws_error")
                      or event["kind"] == "console" and event["level"] in ("warning", "error")
                      or event["kind"] == "http" and event["status"] >= 400
                      or event["kind"] == "ws_close" and event["code"] not in (1000, 1001)
                      and not (event["code"] == 4409 and observation.spec.name in ("landscape", "duplicate")
                               and event["time"] >= collision_start)]
            check(observation.spec.name + " no unexpected browser errors", not errors, errors=errors)
    except BaseException:
        for page, observation in captured_pages:
            try:
                await page.screenshot(path=str(artifacts / f"{observation.spec.name}-failure.png"), timeout=2000)
            except Exception as error:
                observation.event("failure_screenshot_unavailable", error=str(error))
        raise
    finally:
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
    report: dict[str, Any] = {"checks": [], "evidence_gaps": GAPS, "seed": "coded-grid-v1",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "app_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "python": sys.version,
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
