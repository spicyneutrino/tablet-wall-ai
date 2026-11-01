"""Measured image-wall efficiency baseline (TWR-16).

Runs a bounded, disposable loopback server with an imported-app wrapper that
records the server's render-instruction hand-off and every accepted render
acknowledgement on one monotonic clock. Four real Chromium client pages paint
curated PNGs through the shipped ``client.js`` canvas path; this script only
drives and measures them.

The report is evidence, not an acceptance claim. It says nothing about
physical tablets, battery, memory, or a capacity envelope. Raw files are
written outside the checkout; the committed report cites them.

Typical invocation (all paths outside the checkout)::

    .venv/bin/python -m simulator.browser.image_efficiency \\
        --artifacts /var/home/oak/.local/share/tablet-wall-ai/readiness-program/efficiency/run-...

``--profile`` runs a separate single-process CPU profile (no browser) after
the wall measurements. Profiler overhead is real; those numbers are used only
to name a limiter, never as wall latency.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import math
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

import httpx
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
DEFAULT_ASSET_SOURCE = Path("/var/home/oak/.local/share/tablet-wall-ai/assets")
DEVICE_IDS = (
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
    "33333333-3333-4333-8333-333333333333",
    "44444444-4444-4444-8444-444444444444",
)
VIEWPORT = {"width": 600, "height": 800}
COLOR_SCENE = {"type": "color"}
TARGET_DEVICE_COUNT = 4
PRIMARY_ROUNDS = 5
IDLE_SECONDS = 300
DEFAULT_ROTATION_BYTES = 1_000_000
DEFAULT_ROTATION_BACKUPS = 2


# ---------------------------------------------------------------------------
# server wrapper
# ---------------------------------------------------------------------------

WRAPPER = r'''"""Runtime-only instrumentation around the unmodified application."""

import asyncio
import json
import os
import time

import main as app_main
import tabletwall.render_status as render_status
import starlette.websockets as starlette_ws


_LEDGER = os.environ["TABLET_WALL_EFFICIENCY_LEDGER"]
_fd = os.open(_LEDGER, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
_TOKEN_KEYS = ("connection_id", "generation", "revision", "render_seq",
               "mapping_revision", "asset")


def _emit(kind, **data):
    record = {"kind": kind, "mono_ns": time.monotonic_ns(),
              "wall_ns": time.time_ns()}
    record.update(data)
    os.write(_fd, (json.dumps(record, separators=(",", ":"), sort_keys=True)
                   + "\n").encode("utf-8"))


def _token(raw):
    if not isinstance(raw, dict):
        return None
    if not all(key in raw for key in _TOKEN_KEYS):
        return None
    return {key: raw.get(key) for key in _TOKEN_KEYS}


def _frame_token(frame):
    return _token(frame.get("token")) if isinstance(frame, dict) else None


_original_expect = render_status.expect


def _expect(device_id, token, *, now_mono=None):
    _emit("instruction_enqueued", device_id=device_id,
          token={key: getattr(token, key) for key in _TOKEN_KEYS})
    return _original_expect(device_id, token, now_mono=now_mono)


render_status.expect = _expect

_original_send_json = starlette_ws.WebSocket.send_json


async def _send_json(self, data, mode="text"):
    if isinstance(data, dict) and data.get("type") == "render":
        token = _frame_token(data)
        if token is not None:
            size = len(json.dumps(data, separators=(",", ":")).encode("utf-8"))
            _emit("instruction_sent", token=token, frame_bytes=size)
    return await _original_send_json(self, data, mode)


starlette_ws.WebSocket.send_json = _send_json

_original_receive = starlette_ws.WebSocket.receive


async def _receive(self):
    message = await _original_receive(self)
    if isinstance(message, dict):
        text = message.get("text")
        if text and "render_ack" in text:
            try:
                payload = json.loads(text)
            except ValueError:
                payload = None
            if isinstance(payload, dict) and payload.get("type") == "render_ack":
                _emit("ack_received", token=_token(payload.get("token")),
                      status=payload.get("status"),
                      report_seq=payload.get("report_seq"),
                      raw_bytes=len(text.encode("utf-8")))
    return message


starlette_ws.WebSocket.receive = _receive

_original_accept = render_status.accept


def _accept(device_id, **kwargs):
    report = kwargs.get("report")
    try:
        payload = json.loads(report) if isinstance(report, (str, bytes)) else report
    except ValueError:
        payload = None
    accepted = _original_accept(device_id, **kwargs)
    _emit("ack_accepted", device_id=device_id, accepted=bool(accepted),
          status=payload.get("status") if isinstance(payload, dict) else None,
          report_seq=payload.get("report_seq") if isinstance(payload, dict) else None,
          token=_token(payload.get("token")) if isinstance(payload, dict) else None)
    return accepted


render_status.accept = _accept

_original_broadcast_wall = app_main._broadcast_wall


async def _broadcast_wall():
    _emit("broadcast_wall", revision=app_main.wall.get("revision"))
    return await _original_broadcast_wall()


app_main._broadcast_wall = _broadcast_wall

app = app_main.app
'''


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def nearest_rank(values: list[float], percentile: float) -> float | None:
    """Nearest-rank percentile, matching the skill's evidence convention."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, min(len(ordered), math.ceil(percentile / 100.0 * len(ordered))))
    return ordered[rank - 1]


def summary(values: list[float]) -> dict[str, Any]:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return {"n": 0, "p50_ms": None, "p95_ms": None, "min_ms": None,
                "max_ms": None, "mean_ms": None, "range_ms": None}
    return {
        "n": len(clean),
        "p50_ms": round(nearest_rank(clean, 50), 3),
        "p95_ms": round(nearest_rank(clean, 95), 3),
        "min_ms": round(min(clean), 3),
        "max_ms": round(max(clean), 3),
        "mean_ms": round(sum(clean) / len(clean), 3),
        "range_ms": round(max(clean) - min(clean), 3),
    }


def read_json_lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    return records


class Ledger:
    """Incremental reader for the wrapper's append-only JSONL ledger."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.offset = 0
        self.records: list[dict[str, Any]] = []

    def poll(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return self.records
        with self.path.open("rb") as handle:
            handle.seek(self.offset)
            chunk = handle.read()
            self.offset = handle.tell()
        for line in chunk.splitlines():
            if not line.strip():
                continue
            try:
                self.records.append(json.loads(line))
            except ValueError:
                continue
        return self.records

    async def wait_until(
        self, predicate: Callable[[dict[str, Any]], bool], timeout: float,
        description: str,
    ) -> list[dict[str, Any]]:
        deadline = time.monotonic() + timeout
        while True:
            self.poll()
            hits = [record for record in self.records if predicate(record)]
            if hits:
                return hits
            if time.monotonic() >= deadline:
                raise TimeoutError(description)
            await asyncio.sleep(0.02)


class PageMeter:
    """Per-page HTTP and WebSocket byte counters for one measurement window."""

    def __init__(self, page: Any) -> None:
        self.page = page
        self.reset()
        page.on("response", self._response)
        page.on("websocket", self._websocket)

    def reset(self) -> None:
        self.http_requests = 0
        self.http_bytes = 0
        self.asset_requests = 0
        self.asset_bytes = 0
        self.ws_frames = 0
        self.ws_bytes = 0
        if not hasattr(self, "_asset_ids"):
            self._asset_ids: set[str] = set()

    def watch_asset(self, asset_id: str) -> None:
        self._asset_ids.add(asset_id)
        self._asset_ids.add(asset_id.split(":", 1)[-1])

    def _response(self, response: Any) -> None:
        try:
            headers = response.headers
            length = int(headers.get("content-length") or 0)
        except Exception:
            length = 0
        self.http_requests += 1
        self.http_bytes += length
        if any(asset_id in response.url for asset_id in self._asset_ids):
            self.asset_requests += 1
            self.asset_bytes += length

    def _websocket(self, websocket: Any) -> None:
        def received(payload: str | bytes) -> None:
            data = payload.encode("utf-8") if isinstance(payload, str) else payload
            self.ws_frames += 1
            self.ws_bytes += len(data)

        websocket.on("framereceived", received)

    def snapshot(self) -> dict[str, int]:
        return {
            "http_requests": self.http_requests,
            "http_bytes": self.http_bytes,
            "asset_requests": self.asset_requests,
            "asset_bytes": self.asset_bytes,
            "ws_frames": self.ws_frames,
            "ws_bytes": self.ws_bytes,
        }


class ConsoleMeter:
    """Records every console request and WebSocket frame with a local clock."""

    def __init__(self, page: Any) -> None:
        self.page = page
        self.requests: list[dict[str, Any]] = []
        self.frames: list[dict[str, Any]] = []
        page.on("request", self._request)
        page.on("websocket", self._websocket)

    def _request(self, request: Any) -> None:
        self.requests.append({
            "mono_ns": time.monotonic_ns(),
            "method": request.method,
            "url": request.url,
            "resource_type": request.resource_type,
        })

    def _websocket(self, websocket: Any) -> None:
        def frame(direction: str, payload: str | bytes) -> None:
            data = payload.encode("utf-8") if isinstance(payload, str) else payload
            self.frames.append({
                "mono_ns": time.monotonic_ns(),
                "direction": direction,
                "bytes": len(data),
            })

        websocket.on("framereceived", lambda payload: frame("received", payload))
        websocket.on("framesent", lambda payload: frame("sent", payload))


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True,
            timeout=15, check=False,
        ).stdout.strip()
    except OSError:
        return ""


def environment_snapshot() -> dict[str, Any]:
    try:
        load = list(os.getloadavg())
    except OSError:
        load = [None, None, None]
    return {
        "application_sha": git("rev-parse", "HEAD"),
        "application_dirty": bool(git("status", "--porcelain")),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "nproc": os.cpu_count(),
        "load_average_1_5_15": load,
        "load_average_at_init": load,
        "playwright": importlib.metadata.version("playwright"),
        "utc_started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "data_boundary": "private loopback server, temporary DB/assets/media/log",
    }


def artifact_directory(path: Path) -> Path:
    path = path.expanduser().resolve()
    if path == REPO or REPO in path.parents:
        raise ValueError("artifacts must be outside the repository")
    path.mkdir(parents=True, exist_ok=False)
    return path


def copy_assets(source: Path, destination: Path) -> list[dict[str, Any]]:
    if not source.is_dir():
        raise RuntimeError(f"asset source is not a directory: {source}")
    manifest = []
    for path in sorted(source.iterdir()):
        if not path.is_file() or path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            continue
        try:
            with Image.open(path) as image:
                image.load()
                width, height = image.size
                image_format = image.format
        except Exception as error:
            manifest.append({"name": path.name, "skipped": str(error)})
            continue
        if image_format not in ("PNG", "JPEG"):
            manifest.append({"name": path.name, "skipped": "unsupported format"})
            continue
        if width * height > 12_000_000 or path.stat().st_size > 10 * 1024 * 1024:
            manifest.append({
                "name": path.name, "skipped": "outside asset limits",
                "width": width, "height": height, "bytes": path.stat().st_size,
            })
            continue
        target = destination / path.name
        shutil.copy2(path, target)
        digest = hashlib_sha256(target)
        manifest.append({
            "name": path.name, "width": width, "height": height,
            "bytes": target.stat().st_size, "format": image_format,
            "sha256": digest, "id": "sha256:" + digest,
        })
    valid = [entry for entry in manifest if "skipped" not in entry]
    if not valid:
        raise RuntimeError(f"no usable curated assets in {source}")
    return manifest


def hashlib_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def largest_asset(manifest: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        (entry for entry in manifest if "skipped" not in entry),
        key=lambda entry: (entry["width"] * entry["height"], entry["bytes"]),
    )


# ---------------------------------------------------------------------------
# benchmark
# ---------------------------------------------------------------------------


class Benchmark:
    def __init__(self, artifacts: Path, asset_source: Path, rounds: int,
                 idle_seconds: int) -> None:
        self.artifacts = artifacts
        self.asset_source = asset_source
        self.rounds = rounds
        self.idle_seconds = idle_seconds
        self.root = Path(tempfile.mkdtemp(prefix="tw-efficiency-", dir="/tmp/opencode"))
        for name in ("assets", "media", "tmp"):
            (self.root / name).mkdir()
        self.ledger = Ledger(self.root / "ledger.jsonl")
        self.report: dict[str, Any] = {
            "format": "tablet-wall-efficiency-baseline/1",
            "environment": environment_snapshot(),
            "artifacts": str(artifacts),
            "temporary_root": str(self.root),
            "conditions": {
                "cold": "fresh page reload after a browser HTTP cache clear, scene colour: first asset fetch and decode",
                "warm": "same page, immediately after the cold paint: the decoded picture is still retained, so this is the draw/report path with no asset fetch and no decode",
            },
            "limitations": [
                "Desktop headless Chromium on loopback only; no physical tablet, battery, memory or thermal claim.",
                "The server runs uvicorn with its access log enabled, matching deploy/hotspot.py; the idle log figure includes access lines, not only application warnings.",
                "Times are server-observed: render instruction sent (Starlette send_json call) to the client's displayed render_ack receipt.",
                "An accepted displayed ack means the client claimed a completed draw; this run does not inspect the painted pixels.",
                "The console idle sample is five minutes, not a day. The daily log figure is labelled a projection.",
                "The CPU profile runs separately under cProfile; it names a limiter and is not comparable to wall latency.",
            ],
        }
        self.http: httpx.AsyncClient | None = None
        self.base: str | None = None
        self.process: subprocess.Popen | None = None
        self.listener: socket.socket | None = None
        self.playwright = None
        self.browser = None
        self.contexts: list[Any] = []
        self.pages: list[Any] = []
        self.meters: list[PageMeter] = []
        self.device_ids = list(DEVICE_IDS)
        self.asset_manifest = copy_assets(asset_source, self.root / "assets")
        valid = [entry for entry in self.asset_manifest if "skipped" not in entry]
        self.primary_asset = largest_asset(valid)
        # A second image is inventory ballast and an alternative payload; the
        # timed runs keep one asset so cache state is comparable.
        self.secondary_asset = next(
            (entry for entry in valid if entry["name"] != self.primary_asset["name"]),
            self.primary_asset,
        )
        self.report["assets"] = {
            "source": str(asset_source),
            "primary": self.primary_asset,
            "secondary": self.secondary_asset,
            "manifest": valid,
            "all": self.asset_manifest,
        }

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        self.report["environment"]["load_average_at_start"] = list(os.getloadavg())
        env = {
            key: value for key, value in os.environ.items()
            if not key.startswith("TABLET_WALL_")
        }
        env.update({
            "TABLET_WALL_DB": str(self.root / "wall.db"),
            "TABLET_WALL_ASSET_DIR": str(self.root / "assets"),
            "TABLET_WALL_MEDIA_DIR": str(self.root / "media"),
            "TABLET_WALL_UPLOAD_MODE": "loopback",
            "TABLET_WALL_EFFICIENCY_LEDGER": str(self.root / "ledger.jsonl"),
            "PYTHONPATH": os.pathsep.join([str(self.root), str(REPO)]),
            "PYTHONDONTWRITEBYTECODE": "1",
            "TMPDIR": str(self.root / "tmp"),
        })
        (self.root / "efficiency_app.py").write_text(WRAPPER, encoding="utf-8")
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(128)
        self.base = f"http://127.0.0.1:{self.listener.getsockname()[1]}"
        env["TABLET_WALL_OPERATOR_ORIGIN"] = self.base
        self.report["origin"] = self.base
        log = (self.artifacts / "server.log").open("x", encoding="utf-8")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "efficiency_app:app",
             "--fd", str(self.listener.fileno()), "--workers", "1",
             "--access-log"],
            cwd=REPO, env=env, pass_fds=(self.listener.fileno(),),
            stdout=log, stderr=subprocess.STDOUT,
        )
        self.report["server_pid"] = self.process.pid
        self.listener.close()
        self.listener = None
        self.http = httpx.AsyncClient(
            base_url=self.base, headers={"Origin": self.base}, timeout=30,
        )
        deadline = time.monotonic() + 30
        while True:
            try:
                response = await self.http.get("/wall")
                if response.status_code == 200:
                    payload = response.json()
                    self.report["initial_revision"] = payload.get("revision")
                    break
            except httpx.HTTPError:
                pass
            if self.process.poll() is not None:
                raise RuntimeError("isolated server exited; see server.log")
            if time.monotonic() >= deadline:
                raise RuntimeError("isolated server did not become ready")
            await asyncio.sleep(0.1)

        from playwright.async_api import async_playwright

        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            env={**os.environ, "TMPDIR": str(self.root / "tmp")},
            args=[
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
            ],
        )
        self.report["browser"] = {
            "name": "Playwright Chromium",
            "version": self.browser.version,
            "executable": self.browser.browser_type.executable_path,
        }

    async def stop(self) -> None:
        for context in reversed(self.contexts):
            try:
                await context.close()
            except Exception:
                pass
        if self.browser is not None:
            try:
                await self.browser.close()
            except Exception:
                pass
        if self.playwright is not None:
            try:
                await self.playwright.stop()
            except Exception:
                pass
        if self.http is not None:
            try:
                await self.http.aclose()
            except Exception:
                pass
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                await asyncio.to_thread(self.process.wait, 10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                await asyncio.to_thread(self.process.wait, 5)
        if self.listener is not None:
            try:
                self.listener.close()
            except Exception:
                pass

    # -- HTTP --------------------------------------------------------------

    async def config(self) -> dict[str, Any]:
        assert self.http is not None
        response = await self.http.get("/api/v3/config")
        response.raise_for_status()
        return response.json()

    async def put(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        assert self.http is not None
        for _ in range(6):
            config = await self.config()
            response = await self.http.put(
                path, json=body, headers={"If-Match": config["etag"]},
            )
            if response.status_code == 412:
                await asyncio.sleep(0.05)
                continue
            response.raise_for_status()
            return response.json()
        raise RuntimeError(f"etag conflict persisted for {path}")

    async def set_layout(self, tablets: int) -> dict[str, Any]:
        placements = {}
        for index, device_id in enumerate(self.device_ids[:tablets]):
            placements[device_id] = {
                "device_id": device_id,
                "x": index * VIEWPORT["width"], "y": 0,
                "w": VIEWPORT["width"], "h": VIEWPORT["height"],
                "bezel": {"top": 0, "right": 0, "bottom": 0, "left": 0},
            }
        return await self.put("/api/v3/logical-layout", {
            "width": VIEWPORT["width"] * tablets,
            "height": VIEWPORT["height"],
            "placements": placements,
            "sizing": {"mode": "fixed", "padding": 0},
        })

    async def set_scene(self, content: dict[str, Any]) -> dict[str, Any]:
        return await self.put("/api/v3/scene", {"content": content})

    async def set_color(self) -> dict[str, Any]:
        return await self.set_scene(COLOR_SCENE)

    async def set_image(self) -> dict[str, Any]:
        return await self.set_scene({"type": "image", "asset": self.primary_asset["id"]})

    # -- clients -----------------------------------------------------------

    async def connect_clients(self) -> None:
        assert self.browser is not None
        for device_id in self.device_ids:
            context = await self.browser.new_context(
                viewport=VIEWPORT, device_scale_factor=1,
            )
            await context.add_init_script(
                "try { localStorage.setItem('tablet-wall-device-id', %s); }"
                " catch (error) {}" % json.dumps(device_id)
            )
            page = await context.new_page()
            page.set_default_timeout(30_000)
            self.contexts.append(context)
            self.pages.append(page)
            self.meters.append(PageMeter(page))
            await page.goto(self.base + "/client/", wait_until="domcontentloaded")
            await page.wait_for_selector(
                "#status[data-state='connected']", state="attached", timeout=30_000)
            observed = await page.evaluate(
                "localStorage.getItem('tablet-wall-device-id')")
            if observed != device_id:
                raise RuntimeError(f"client identity mismatch: {observed} != {device_id}")

    async def clear_cache(self, pages: list[Any]) -> None:
        for page in pages:
            session = await page.context.new_cdp_session(page)
            try:
                await session.send("Network.enable")
                await session.send("Network.clearBrowserCache")
            finally:
                await session.detach()

    async def reload(self, pages: list[Any]) -> None:
        await asyncio.gather(
            *(page.reload(wait_until="domcontentloaded") for page in pages),
            return_exceptions=False,
        )
        await asyncio.gather(
            *(page.wait_for_selector(
                "#status[data-state='connected']", state="attached", timeout=30_000)
              for page in pages),
            return_exceptions=False,
        )

    # -- ledger waits ------------------------------------------------------

    async def wait_accepted(
        self, device_ids: set[str], revision: int, asset: str | None,
        mark_ns: int, status: str, timeout: float = 45,
    ) -> dict[str, dict[str, Any]]:
        deadline = time.monotonic() + timeout
        last: dict[str, str | None] = {}
        while True:
            self.ledger.poll()
            accepted: dict[str, dict[str, Any]] = {}
            for record in self.ledger.records:
                if record.get("kind") != "ack_accepted":
                    continue
                token = record.get("token") or {}
                if (record.get("accepted") and record.get("status") == status
                        and record.get("device_id") in device_ids
                        and record.get("mono_ns", 0) >= mark_ns
                        and token.get("revision") == revision
                        and token.get("asset") == asset):
                    accepted[record["device_id"]] = record
                elif (record.get("device_id") in device_ids
                      and record.get("mono_ns", 0) >= mark_ns
                      and (record.get("token") or {}).get("revision") == revision):
                    last[record["device_id"]] = record.get("status")
            if device_ids <= set(accepted):
                return accepted
            if time.monotonic() >= deadline:
                missing = device_ids - set(accepted)
                raise TimeoutError(
                    f"no accepted {status} ack for revision {revision}, "
                    f"asset {asset}: missing={sorted(missing)} last={last}")
            await asyncio.sleep(0.02)

    # -- measurements ------------------------------------------------------

    async def settle_color(self, device_ids: set[str]) -> int:
        mark = time.monotonic_ns()
        scene = await self.set_color()
        revision = scene["revision"]
        # The shipped client reports ``loading`` for a colour and never a
        # displayed paint (only image content takes the displayed path), so
        # this waits for the accepted instruction receipt, not a paint.
        await self.wait_accepted(device_ids, revision, None, mark, "loading")
        return revision

    async def measure_image(
        self, round_number: int, tablets: int, condition: str,
    ) -> dict[str, Any]:
        target_ids = set(self.device_ids[:tablets])
        target_meters = self.meters[:tablets]
        for meter in target_meters:
            meter.watch_asset(self.primary_asset["id"])
            meter.reset()
        mark = time.monotonic_ns()
        try:
            scene = await self.set_image()
            revision = scene["revision"]
            accepted = await self.wait_accepted(
                target_ids, revision, self.primary_asset["id"], mark, "displayed")
        except Exception as error:
            self.ledger.poll()
            failed = [
                record for record in self.ledger.records
                if record.get("mono_ns", 0) >= mark
                and record.get("device_id") in target_ids
                and (record.get("token") or {}).get("revision") is not None
            ]
            return {
                "round": round_number, "tablets": tablets,
                "condition": condition, "error": f"{type(error).__name__}: {error}",
                "records": failed[-20:],
            }

        await asyncio.sleep(0.15)
        self.ledger.poll()
        records = [
            record for record in self.ledger.records
            if record.get("mono_ns", 0) >= mark
            and (record.get("token") or {}).get("revision") == revision
        ]
        sent: dict[tuple[Any, Any], dict[str, Any]] = {}
        enqueued: dict[tuple[Any, Any], dict[str, Any]] = {}
        received: dict[tuple[Any, Any], dict[str, Any]] = {}
        for record in records:
            token = record.get("token") or {}
            key = (token.get("connection_id"), token.get("render_seq"))
            if record.get("kind") == "instruction_sent":
                sent[key] = record
            elif record.get("kind") == "instruction_enqueued":
                enqueued[key] = record
            elif record.get("kind") == "ack_received" and record.get("status") == "displayed":
                received[key] = record

        samples = []
        meter_by_device = dict(zip(self.device_ids[:tablets], target_meters))
        for device_id, ack in accepted.items():
            token = ack["token"]
            key = (token.get("connection_id"), token.get("render_seq"))
            sent_record = sent.get(key)
            received_record = received.get(key)
            if sent_record is None or received_record is None:
                samples.append({
                    "device_id": device_id,
                    "error": "missing instruction_sent or ack_received for token",
                })
                continue
            meter = meter_by_device[device_id].snapshot()
            samples.append({
                "device_id": device_id,
                "sent_to_ack_ms": round(
                    (received_record["mono_ns"] - sent_record["mono_ns"]) / 1e6, 3),
                "enqueued_to_ack_ms": round(
                    (received_record["mono_ns"] - enqueued[key]["mono_ns"]) / 1e6, 3)
                if key in enqueued else None,
                "accept_delay_ms": round(
                    (ack["mono_ns"] - received_record["mono_ns"]) / 1e6, 3),
                "frame_bytes": sent_record.get("frame_bytes"),
                "ack_bytes": received_record.get("raw_bytes"),
                **meter,
            })
        rejected = [
            record for record in records
            if record.get("kind") == "ack_accepted"
            and record.get("device_id") in target_ids
            and not record.get("accepted")
            and record.get("status") == "displayed"
        ]
        latencies = [sample["sent_to_ack_ms"] for sample in samples
                     if "sent_to_ack_ms" in sample]
        sent_times = [sent[(ack["token"]["connection_id"],
                            ack["token"]["render_seq"])]["mono_ns"]
                      for ack in accepted.values()
                      if (ack["token"]["connection_id"],
                          ack["token"]["render_seq"]) in sent]
        snapshot = await self.http.get("/api/v3/config")
        snapshot.raise_for_status()
        snapshot_payload = snapshot.json()
        current_after = {
            device_id: bool(
                snapshot_payload.get("runtime", {})
                .get("devices", {})
                .get(device_id, {})
                .get("render", {})
                .get("current"))
            for device_id in sorted(target_ids)
        }
        return {
            "round": round_number,
            "tablets": tablets,
            "condition": condition,
            "revision": revision,
            "asset": self.primary_asset["id"],
            "samples": samples,
            "sample_count": len(samples),
            "accepted_displayed": len(accepted),
            "rejected_displayed_acks": len(rejected),
            "fleet_from_first_send_ms": round(
                (max(record["mono_ns"] for record in received.values())
                 - min(sent_times)) / 1e6, 3)
            if received and sent_times else None,
            "latency_summary": summary(latencies),
            "current_after_check": current_after,
            "payload": {
                "render_frame_bytes_per_device": [
                    sample.get("frame_bytes") for sample in samples],
                "render_frame_bytes_total": sum(
                    sample.get("frame_bytes") or 0 for sample in samples),
                "asset_http_bytes_total": sum(
                    sample.get("asset_bytes") or 0 for sample in samples),
                "asset_requests_total": sum(
                    sample.get("asset_requests") or 0 for sample in samples),
                "ws_bytes_received_total": sum(
                    sample.get("ws_bytes") or 0 for sample in samples),
                "config_snapshot_bytes": len(snapshot.content),
            },
            "records": records[-80:],
        }

    async def run_wall_rounds(self) -> None:
        measurements = []
        self.report["wall"] = measurements
        for round_number in range(1, self.rounds + 1):
            sizes = [1, TARGET_DEVICE_COUNT] if round_number % 2 else [
                TARGET_DEVICE_COUNT, 1]
            for tablets in sizes:
                device_ids = set(self.device_ids[:tablets])
                pages = self.pages[:tablets]
                await self.set_layout(tablets)
                # Cold: colour, settle, clear caches and reload, settle on colour.
                await self.settle_color(device_ids)
                await self.clear_cache(pages)
                cold_mark = time.monotonic_ns()
                await self.reload(pages)
                cold_revision = (await self.config())["revision"]
                await self.wait_accepted(
                    device_ids, cold_revision, None, cold_mark, "loading")
                measurements.append(await self.measure_image(
                    round_number, tablets, "cold"))
                # Warm: republish the same image without leaving image content,
                # so the client still holds the decoded picture and only draws.
                measurements.append(await self.measure_image(
                    round_number, tablets, "warm"))
                self.report["progress"] = {
                    "round": round_number, "tablets": tablets,
                    "completed": len(measurements),
                }

    async def measure_2x2(self) -> dict[str, Any]:
        device_ids = self.device_ids[:4]
        await self.set_layout(4)
        await self.settle_color(set(device_ids))
        config = await self.config()
        before_revision = config["revision"]
        command = {
            "kind": "logical",
            "device_ids": device_ids,
            "rows": 2,
            "columns": 2,
            "gap": 0,
            "padding": 0,
            "sizing": "tablets",
            "orientation": "preserve",
            "logical_sizes": {
                device_id: {"w": VIEWPORT["width"], "h": VIEWPORT["height"]}
                for device_id in device_ids
            },
            "allow_empty_cells": False,
            "release_unselected": [],
        }
        assert self.http is not None
        preview = await self.http.post(
            "/api/v3/grid/preview", json=command,
            headers={"If-Match": config["etag"]},
        )
        preview.raise_for_status()
        command["guards"] = preview.json()["guards"]
        mark = time.monotonic_ns()
        response = await self.http.post(
            "/api/v3/grid", json=command,
            headers={"If-Match": config["etag"]},
        )
        response.raise_for_status()
        applied = response.json()
        await asyncio.sleep(0.3)
        self.ledger.poll()
        broadcasts = [
            record for record in self.ledger.records
            if record.get("kind") == "broadcast_wall"
            and record.get("mono_ns", 0) >= mark
        ]
        return {
            "before_revision": before_revision,
            "after_revision": applied["revision"],
            "revision_delta": applied["revision"] - before_revision,
            "broadcasts": len(broadcasts),
            "placements": len(applied.get("layout", {}).get("placements", {})),
            "preview_placements": len(
                preview.json().get("layout", {}).get("placements", {})),
            "command": command,
        }

    async def measure_asset_inventory(self) -> dict[str, Any]:
        """Time the real ``GET /assets`` scan/hash path over this library."""
        assert self.http is not None
        samples = []
        last = None
        for _ in range(20):
            start = time.perf_counter_ns()
            response = await self.http.get("/assets")
            response.raise_for_status()
            samples.append((time.perf_counter_ns() - start) / 1e6)
            last = response
        payload = last.json() if last is not None else {"assets": []}
        return {
            "count": len(samples),
            "library_assets": len(payload.get("assets", [])),
            "library_bytes": sum(asset["bytes"] for asset in payload.get("assets", [])),
            "server_endpoint_ms": summary(samples),
            "note": "Loopback HTTP includes client and serialization; the profile run isolates the server function.",
        }

    async def measure_idle(self) -> dict[str, Any]:
        assert self.browser is not None
        name, path = "physical", "/controller/physical.html"
        context = await self.browser.new_context(
            viewport={"width": 1440, "height": 1000},
        )
        page = await context.new_page()
        page.set_default_timeout(30_000)
        self.contexts.append(context)
        meter = ConsoleMeter(page)
        await page.goto(self.base + path, wait_until="load")
        await page.wait_for_load_state("load", timeout=30_000)
        await page.bring_to_front()
        await asyncio.sleep(2.0)
        visibility_start = await page.evaluate(
            "() => ({state: document.visibilityState, focus: document.hasFocus()})")

        # The primary operator console is up and foregrounded; the four
        # tablets stay connected and idle for the whole window.
        start = time.monotonic_ns()
        log_path = self.artifacts / "server.log"
        log_start = log_path.stat().st_size
        boot_requests = len(meter.requests)
        await asyncio.sleep(self.idle_seconds)
        end = time.monotonic_ns()
        log_end = log_path.stat().st_size
        visibility_end = await page.evaluate(
            "() => ({state: document.visibilityState, focus: document.hasFocus()})")
        result: dict[str, Any] = {
            "duration_s": round((end - start) / 1e9, 3),
            "window_start_mono_ns": start,
            "log": {
                "path": str(log_path),
                "bytes_start": log_start,
                "bytes_end": log_end,
                "bytes_growth": log_end - log_start,
                "idle_projection_bytes_per_day_labeled": round(
                    (log_end - log_start) / (end - start) * 1e9 * 86400, 1),
                "rotation_active_cap_bytes": DEFAULT_ROTATION_BYTES,
                "rotation_backups": DEFAULT_ROTATION_BACKUPS,
                "rotation_retained_bytes": (
                    DEFAULT_ROTATION_BYTES * (DEFAULT_ROTATION_BACKUPS + 1)),
            },
            "consoles": {},
        }
        requests = [
            request for request in meter.requests
            if request["mono_ns"] >= start
        ]
        frames = [
            frame for frame in meter.frames
            if frame["mono_ns"] >= start
        ]
        result["consoles"][name] = {
            "url": page.url,
            "visibility_start": visibility_start,
            "visibility_end": visibility_end,
            "boot_requests": boot_requests,
            "idle_http_requests": len(requests),
            "idle_http_get": sum(1 for item in requests if item["method"] == "GET"),
            "idle_http_paths": _count_paths(requests),
            "idle_ws_frames": len(frames),
            "idle_ws_received": sum(
                1 for item in frames if item["direction"] == "received"),
            "idle_ws_sent": sum(
                1 for item in frames if item["direction"] == "sent"),
            "idle_ws_bytes": sum(item["bytes"] for item in frames),
            "requests": requests,
            "frames": frames,
        }
        await page.close()
        (self.artifacts / "console-idle.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result

    # -- orchestration -----------------------------------------------------

    async def run(self) -> dict[str, Any]:
        try:
            await self.start()
            await self.connect_clients()
            await self.set_layout(TARGET_DEVICE_COUNT)
            await self.settle_color(set(self.device_ids))
            await self.run_wall_rounds()
            self.report["grid_2x2"] = await self.measure_2x2()
            self.report["asset_inventory"] = await self.measure_asset_inventory()
            self.report["idle"] = await self.measure_idle()
            self.report["environment"]["load_average_at_finish"] = list(os.getloadavg())
            self.report["environment"]["load_average_1_5_15"] = list(os.getloadavg())
            self.report["environment"]["utc_finished"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        finally:
            await self.stop()
        self.report["summaries"] = summaries(self.report.get("wall", []))
        return self.report


def _count_paths(requests: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for request in requests:
        path = request["url"].split("?", 1)[0]
        if request["url"].startswith("http://") or request["url"].startswith("https://"):
            path = "/" + path.split("/", 3)[-1]
        counts[path] = counts.get(path, 0) + 1
    return dict(sorted(counts.items()))


def summaries(measurements: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for measurement in measurements:
        key = f"{measurement.get('tablets')}t-{measurement.get('condition')}"
        grouped.setdefault(key, []).append(measurement)
    result: dict[str, Any] = {}
    for key, rows in sorted(grouped.items()):
        latencies = []
        fleet = []
        errors = []
        samples = 0
        for row in rows:
            if row.get("error"):
                errors.append(row["error"])
                continue
            samples += row.get("sample_count", 0)
            for sample in row.get("samples", []):
                if "sent_to_ack_ms" in sample:
                    latencies.append(sample["sent_to_ack_ms"])
            if row.get("fleet_from_first_send_ms") is not None:
                fleet.append(row["fleet_from_first_send_ms"])
        result[key] = {
            "samples": samples,
            "rounds": len(rows),
            "errors": errors,
            "time_to_painted": summary(latencies),
            "fleet_from_first_send": summary(fleet),
        }
    return result


# ---------------------------------------------------------------------------
# separate CPU profile (no browser)
# ---------------------------------------------------------------------------


def profile_worker(root: str, out: str) -> int:
    """Single-process profile of config, asset scan, SQLite and one broadcast."""
    import cProfile
    import io
    import pstats

    base_root = Path(root)
    for name in ("assets", "media"):
        base_root.joinpath(name).mkdir(parents=True, exist_ok=True)
    os.environ.update({
        "TABLET_WALL_DB": str(base_root / "wall.db"),
        "TABLET_WALL_ASSET_DIR": str(base_root / "assets"),
        "TABLET_WALL_MEDIA_DIR": str(base_root / "media"),
        "TABLET_WALL_OPERATOR_ORIGIN": "http://testserver",
    })
    sys.path.insert(0, str(REPO))
    import main  # noqa: WPS433 - deliberate import after the temporary env
    from fastapi.testclient import TestClient
    from tabletwall import assets as asset_module

    with TestClient(main.app) as client:
        device_ids = list(DEVICE_IDS[:4])
        for index, device_id in enumerate(device_ids):
            client.post("/devices/register", json={
                "device_id": device_id, "width": 600, "height": 800,
                "device_type": "test",
            }).raise_for_status()
        config = client.get("/api/v3/config").json()
        placements = {
            device_id: {
                "device_id": device_id, "x": index * 600, "y": 0,
                "w": 600, "h": 800,
                "bezel": {"top": 0, "right": 0, "bottom": 0, "left": 0},
            }
            for index, device_id in enumerate(device_ids)
        }
        origin = {"Origin": "http://testserver"}
        client.put("/api/v3/logical-layout",
                   headers={**origin, "If-Match": config["etag"]},
                   json={"width": 2400, "height": 800, "placements": placements,
                         "sizing": {"mode": "fixed", "padding": 0}}).raise_for_status()
        inventory = client.get("/assets").json()["assets"]
        client.put("/api/v3/scene",
                   headers={**origin,
                            "If-Match": client.get("/api/v3/config").json()["etag"]},
                   json={"content": {"type": "image",
                                     "asset": inventory[0]["id"]}}).raise_for_status()

        def timed(label: str, function: Callable[[], Any], count: int = 30) -> dict[str, Any]:
            samples = []
            for _ in range(count):
                start = time.perf_counter_ns()
                function()
                samples.append((time.perf_counter_ns() - start) / 1e6)
            return {"label": label, "count": count, **summary(samples)}

        # Setup fake device sockets so one broadcast executes the real frame
        # projection and JSON sizing path without a network client.
        from tabletwall import hub, state, writer

        class FakeSocket:
            async def send_json(self, frame, mode="text"):
                FakeSocket.last = len(json.dumps(frame))

        class FakeWriter:
            def __init__(self):
                self.frames = []

            async def send(self, frame, stamp=None):
                self.frames.append(frame)

        for device_id in device_ids:
            socket = FakeSocket()
            state.device_sockets[device_id] = socket
            writer._writers[socket] = FakeWriter()

        operations = {
            "config_payload": lambda: main._config_payload(),
            "config_etag": lambda: main._config_etag(),
            "assets_list_assets": lambda: asset_module.list_assets(),
            "sqlite_load_layouts": main.persist.load_layouts,
            "sqlite_load_scenes": main.persist.load_scenes,
        }
        results = {name: timed(name, function) for name, function in operations.items()}

        async def one_broadcast():
            await hub._broadcast_wall()

        broadcast_samples = []
        for _ in range(30):
            start = time.perf_counter_ns()
            asyncio.run(one_broadcast())
            broadcast_samples.append((time.perf_counter_ns() - start) / 1e6)
        results["broadcast_4_devices_fake_writer"] = {
            "label": "broadcast_4_devices_fake_writer",
            "count": 30, **summary(broadcast_samples),
        }

        profiler = cProfile.Profile()
        profiler.enable()
        for _ in range(30):
            main._config_payload()
            main._config_etag()
            asset_module.list_assets()
            asyncio.run(one_broadcast())
        profiler.disable()
        stream = io.StringIO()
        pstats.Stats(profiler, stream=stream).sort_stats("cumulative").print_stats(20)
        profile_text = stream.getvalue()

    Path(out).write_text(json.dumps({
        "format": "tablet-wall-efficiency-profile/1",
        "note": "Separate in-process profile. cProfile inflates CPU; use only to name a limiter, not as wall latency.",
        "operations": results,
        "top_cumulative": profile_text,
    }, indent=2) + "\n", encoding="utf-8")
    return 0


def run_profile(artifacts: Path, asset_source: Path) -> dict[str, Any]:
    root = Path(tempfile.mkdtemp(prefix="tw-efficiency-profile-", dir="/tmp/opencode"))
    for name in ("assets", "media"):
        (root / name).mkdir()
    copy_assets(asset_source, root / "assets")
    out = artifacts / "profile.json"
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--profile-worker",
         str(root), str(out)],
        cwd=REPO, capture_output=True, text=True, timeout=180,
        env={k: v for k, v in os.environ.items() if not k.startswith("TABLET_WALL_")},
    )
    if completed.returncode != 0:
        (artifacts / "profile-stderr.txt").write_text(
            completed.stdout + "\n" + completed.stderr, encoding="utf-8")
        raise RuntimeError("profile worker failed; see profile-stderr.txt")
    return json.loads(out.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=False)
    parser.add_argument("--asset-source", type=Path, default=DEFAULT_ASSET_SOURCE)
    parser.add_argument("--rounds", type=int, default=PRIMARY_ROUNDS)
    parser.add_argument("--idle-seconds", type=int, default=IDLE_SECONDS)
    parser.add_argument("--profile", action="store_true",
                        help="also run the separate CPU profile")
    parser.add_argument("--profile-only", action="store_true")
    parser.add_argument("--profile-worker", nargs=2, metavar=("ROOT", "OUT"))
    args = parser.parse_args(argv)

    if args.profile_worker:
        return profile_worker(args.profile_worker[0], args.profile_worker[1])
    if args.artifacts is None:
        parser.error("--artifacts is required")
    artifacts = artifact_directory(args.artifacts)
    if args.rounds < 5:
        parser.error("--rounds must be at least 5 for an interleaved baseline")
    if args.idle_seconds < 1:
        parser.error("--idle-seconds must be positive")

    if args.profile_only:
        result = run_profile(artifacts, args.asset_source)
        (artifacts / "report.json").write_text(
            json.dumps({"profile": result}, indent=2) + "\n", encoding="utf-8")
        print(artifacts)
        return 0

    benchmark = Benchmark(artifacts, args.asset_source, args.rounds,
                          args.idle_seconds)
    report = asyncio.run(benchmark.run())
    if args.profile:
        try:
            report["profile"] = run_profile(artifacts, args.asset_source)
        except Exception as error:
            report["profile"] = {"error": f"{type(error).__name__}: {error}"}
    (artifacts / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (artifacts / "summary.json").write_text(
        json.dumps({
            "environment": report["environment"],
            "browser": report.get("browser"),
            "assets": report["assets"]["manifest"],
            "summaries": report.get("summaries"),
            "grid_2x2": report.get("grid_2x2"),
            "asset_inventory": report.get("asset_inventory"),
            "idle": {
                name: {
                    key: value for key, value in console.items()
                    if key not in ("requests", "frames")
                }
                for name, console in report.get("idle", {}).get("consoles", {}).items()
            },
            "profile": report.get("profile"),
        }, indent=2) + "\n", encoding="utf-8")
    print(artifacts)
    if any(row.get("error") for row in report.get("wall", [])):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
