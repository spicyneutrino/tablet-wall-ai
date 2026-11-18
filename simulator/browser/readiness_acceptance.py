"""Bounded tablet and server acceptance evidence for the image-wall roadmap
(TWR-04/05/06/08/09/10/11/13).

The driver boots the checked-out application on private loopback ports with
temporary database, asset, media and backup paths. Four Chromium contexts act
as Android tablets that match the built-in Pixel C signature. Everything else
is the shipped routes, sockets and client code. No backend fixture stands in
for a route.

The operator console is not driven here. Wall setup (model confirmation,
grids, content, labels, saved arrangements, uploads, identify, rebind preview)
goes through the same REST endpoints the console calls, via ``_api.Api``. The
console's own behaviour is proved by the controller app's Playwright parity
specs, ``frontend/controller-app/e2e/parity/<ROW>.spec.ts``.

What this proves:
  * the tablets register, match the Pixel C signature, and map with confirmed
    model profiles pinned into a 1x4 physical wall (TWR-11);
  * grid apply bumps one revision, numbers tablets in order, and names its
    cross-kind return point (TWR-09, TWR-10);
  * content reaches the tablets and Fit and Fill paint the expected pixels
    (TWR-04, TWR-05, TWR-11);
  * an induced image failure, an offline tablet, a backend restart, Identify,
    a viewport fence and a replacement preview behave as the server reports
    (TWR-06, TWR-08, TWR-09, TWR-11);
  * uploads accept PNG and refuse other types (TWR-04);
  * the legacy ``experimental.html`` editor is fenced on a physical wall
    (TWR-04);
  * the stop, backup, verify, restore and boot-restored-copy runbook chain
    keeps scene, layout, labels, numbers and image bytes (TWR-13).

Every run writes its own artifact directory: screenshots, JSON results,
transcript and server logs. Failures are retained, not retried away.

What this does not prove: physical panels, bezels, optical seams, TLS or
proxy composition, OS suspend, battery, or soak. Those remain TWR-17.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

try:
    from _api import Api
except ImportError:  # run as python -m simulator.browser.readiness_acceptance
    from simulator.browser._api import Api

ROOT = Path(__file__).resolve().parents[2]
TABLET_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel C) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
VIEW = {"width": 900, "height": 1280}
BACKGROUND = (11, 17, 32)
MARKED = (2000, 1000)
BORDER = 40
MAGENTA = (255, 0, 255)
GREEN = (40, 140, 90)

checks: list[str] = []
failures: list[str] = []
findings: list[str] = []
notes: list[str] = []
transcript: list[dict] = []

ARTIFACTS = Path(".")
SHOTS = Path(".")
DATA = Path(".")
ASSETS = Path(".")
MEDIA = Path(".")
BACKUPS = Path(".")
PY = sys.executable
APP_SHA = ""
DRIVER_SHA = ""
STARTED = ""


class Instance:
    """One private uvicorn process on loopback with explicit data paths."""

    def __init__(self, db: Path, assets: Path, media: Path, backups: Path, upload: str,
                 port: int | None = None, origin: str | None = None, tag: str = "server"):
        self.db = db
        self.assets = assets
        self.media = media
        self.backups = backups
        self.upload = upload
        self.port = port or free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.origin = origin or self.base
        self.tag = tag
        self.process: subprocess.Popen | None = None
        self.log_path = ARTIFACTS / f"{tag}.log"

    def start(self) -> "Instance":
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("TABLET_WALL", "WALL_"))}
        env.update({
            "TABLET_WALL_DB": str(self.db),
            "TABLET_WALL_ASSET_DIR": str(self.assets),
            "TABLET_WALL_MEDIA_DIR": str(self.media),
            "TABLET_WALL_BACKUP_DIR": str(self.backups),
            "TABLET_WALL_TABLET_ORIGIN": self.origin,
            "TABLET_WALL_OPERATOR_ORIGIN": self.origin,
            "TABLET_WALL_WIFI_NAME": "QA-Wall-Net",
            "TABLET_WALL_UPLOAD_MODE": self.upload,
        })
        command = [PY, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
                   "--port", str(self.port), "--no-access-log"]
        log = open(self.log_path, "a", encoding="utf-8")
        self.process = subprocess.Popen(command, cwd=str(ROOT), env=env,
                                        stdout=log, stderr=subprocess.STDOUT)
        transcript.append({"step": f"start {self.tag}", "command": command,
                           "cwd": str(ROOT), "env": {
                               "TABLET_WALL_DB": str(self.db),
                               "TABLET_WALL_ASSET_DIR": str(self.assets),
                               "TABLET_WALL_MEDIA_DIR": str(self.media),
                               "TABLET_WALL_BACKUP_DIR": str(self.backups),
                               "TABLET_WALL_UPLOAD_MODE": self.upload,
                               "TABLET_WALL_OPERATOR_ORIGIN": self.origin,
                           }, "at": now()})
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"{self.tag} exited during startup; see {self.log_path}")
            try:
                with urllib.request.urlopen(self.base + "/healthz", timeout=1) as response:
                    if response.status == 200:
                        return self
            except Exception:
                time.sleep(0.1)
        self.stop()
        raise RuntimeError(f"{self.tag} did not become healthy")

    def stop(self) -> None:
        process, self.process = self.process, None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        transcript.append({"step": f"stop {self.tag}", "returncode": process.returncode,
                           "at": now()})


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def check(value, message: str) -> None:
    if value:
        checks.append(message)
        print("PASS", message, flush=True)
    else:
        failures.append(message)
        print("FAIL", message, flush=True)


def note(message: str) -> None:
    notes.append(message)
    print("NOTE", message, flush=True)


def persist() -> None:
    payload = {
        "application_sha": APP_SHA,
        "driver_sha256": DRIVER_SHA,
        "driver_path": str(Path(__file__).resolve()),
        "branch": branch(),
        "command": " ".join([sys.executable, *sys.argv]),
        "python": sys.executable,
        "artifacts": str(ARTIFACTS),
        "started_utc": STARTED,
        "updated_utc": now(),
        "base": CURRENT_BASE[0],
        "checks": checks,
        "failures": failures,
        "findings": findings,
        "notes": notes,
        "environment": {
            "playwright_chromium": CHROMIUM_VERSION[0],
            "viewport_css": VIEW,
            "device_scale_factor": 2,
            "platform_family": "android",
        },
        "limits": [
            "Software loopback only. No physical panel, bezel, seam, optical, sleep or soak measurement.",
            "No TLS/proxy composition, host reboot, or installed-service claim.",
            "Identify timing is request-to-overlay on loopback Chromium, not a tablet measurement.",
            "Broadcast count is not re-measured here; the atomic-grid route and one-broadcast result are recorded in docs/tablet-wall-readiness/EFFICIENCY.md.",
            "The operator console is not driven here; its behaviour is covered by the controller app's Playwright parity specs.",
        ],
    }
    (ARTIFACTS / "results.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (ARTIFACTS / "transcript.jsonl").write_text(
        "".join(json.dumps(entry) + "\n" for entry in transcript), encoding="utf-8")


def branch() -> str:
    result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(ROOT),
                            capture_output=True, text=True)
    return result.stdout.strip() or "unknown"


CURRENT_BASE = [""]
CHROMIUM_VERSION = [""]


def http(method: str, path: str, body=None, etag: str | None = None, timeout: int = 30):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Origin": CURRENT_BASE[0]}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if etag:
        headers["If-Match"] = etag
    request = urllib.request.Request(CURRENT_BASE[0] + path, data=data, method=method,
                                     headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            return error.code, json.loads(raw) if raw else None
        except ValueError:
            return error.code, {"raw": raw.decode(errors="replace")}


def config():
    return http("GET", "/api/v3/config")[1]


def device(config_snapshot, device_id):
    return (config_snapshot.get("runtime") or {}).get("devices", {}).get(device_id) or {}


def wait_until(predicate, message: str, timeout: float = 20.0, interval: float = 0.12):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except Exception as error:
            last = error
        time.sleep(interval)
    raise AssertionError(message + (f" (last error: {last})" if last else ""))


def shot(page, name: str, full: bool = False) -> None:
    page.screenshot(path=str(SHOTS / name), full_page=full)
    print("SHOT", name, flush=True)


def make_images() -> None:
    marked = Image.new("RGB", MARKED, GREEN)
    draw = ImageDraw.Draw(marked)
    draw.rectangle((0, 0, MARKED[0] - 1, MARKED[1] - 1), outline=MAGENTA, width=BORDER)
    draw.rectangle((BORDER, BORDER, MARKED[0] - BORDER - 1, MARKED[1] - BORDER - 1),
                   outline=(255, 255, 255), width=6)
    marked.save(ASSETS / "marked.png")

    first = Image.new("RGB", (2000, 1400), (180, 90, 20))
    paint = ImageDraw.Draw(first)
    paint.rectangle((0, 0, 999, 1399), fill=(180, 90, 20))
    paint.rectangle((1000, 0, 1999, 1399), fill=(20, 100, 160))
    paint.ellipse((700, 400, 1300, 1000), fill=(245, 230, 80))
    first.save(ASSETS / "first.png")

    noisy = Image.effect_noise((1200, 800), 64).convert("RGB")
    noisy.save(ASSETS / "upload-ok.png")
    (ARTIFACTS / "upload-bad.txt").write_text("not an image\n", encoding="utf-8")
    Image.new("RGB", (120, 80), (90, 30, 160)).save(ARTIFACTS / "upload-unsupported.webp",
                                                   format="WEBP")


def new_tablet(browser, base: str):
    context = browser.new_context(viewport=VIEW, screen=VIEW, device_scale_factor=2,
                                  user_agent=TABLET_UA)
    context.add_init_script(
        "Object.defineProperty(screen.orientation, 'angle', "
        "{get: () => 270, configurable: true});")
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
    page.goto(base + "/client/", wait_until="load")
    wait_until(lambda: page.locator("#status").get_attribute("data-state") == "connected",
               "tablet did not connect")
    device_id = page.evaluate("localStorage.getItem('tablet-wall-device-id')")
    return {"page": page, "context": context, "id": device_id, "errors": errors}


def painted(asset_id: str, count: int = 4) -> bool:
    snapshot = config()
    devices = (snapshot.get("runtime") or {}).get("devices") or {}
    layout = snapshot.get("layout") or {}
    entries = layout.get("slots") if layout.get("kind") == "physical" else layout.get("placements")
    entries = entries or {}
    matched = 0
    for device_id, item in devices.items():
        if device_id not in entries:
            continue
        matched += 1
        render = item.get("render") or {}
        token = render.get("accepted_token") or {}
        if (render.get("state") != "displayed" or render.get("current") is not True
                or token.get("asset") != asset_id
                or token.get("revision") != snapshot.get("revision")
                or token.get("generation") != snapshot.get("generation")):
            return False
    return matched >= count


def wait_painted(asset_id: str, timeout: float = 30.0, count: int = 4) -> None:
    wait_until(lambda: painted(asset_id, count), f"tablets did not confirm paint of {asset_id}",
               timeout)


def image_id(name: str) -> str:
    images = http("GET", "/api/v3/images")[1]["images"]
    return next(item["id"] for item in images if item["name"] == name)


def sample_colour(path: Path, x: float, y: float, radius: int = 8):
    image = Image.open(path).convert("RGB")
    width, height = image.size
    best = None
    for dy in range(-radius, radius + 1, 2):
        for dx in range(-radius, radius + 1, 2):
            px, py = int(round(x)) + dx, int(round(y)) + dy
            if 0 <= px < width and 0 <= py < height:
                pixel = image.getpixel((px, py))
                if best is None or _distance(pixel, MAGENTA) < _distance(best, MAGENTA):
                    best = pixel
    return best


def _distance(left, right) -> int:
    return sum((a - b) ** 2 for a, b in zip(left, right))


def is_magenta(pixel) -> bool:
    return pixel is not None and pixel[0] >= 190 and pixel[2] >= 190 and pixel[1] <= 100


def magenta_pixels(path: Path) -> int:
    image = Image.open(path).convert("RGB")
    width, height = image.size
    count = 0
    for y in range(0, height, 2):
        for x in range(0, width, 2):
            if is_magenta(image.getpixel((x, y))):
                count += 1
    return count


TRANSFORM_JS = """async (deviceId) => {
  const cfg = await fetch('/api/v3/config').then(r => r.json());
  const slot = cfg.layout.slots[deviceId];
  const profile = cfg.displays.find(p => p.device_id === deviceId && p.revision === slot.profile_revision);
  const calibr = cfg.calibrations.find(c => c.device_id === deviceId && c.revision === slot.calibration_revision);
  const content = cfg.scene.content;
  const V = window.TabletWallView;
  const plan = V.normalizedSourceToPanel({
    active_size: [profile.active_width_mm, profile.active_height_mm],
    bezels: profile.bezels,
    center_mm: [slot.center_x_mm, slot.center_y_mm],
    nudge_mm: [slot.nudge_x_mm || 0, slot.nudge_y_mm || 0],
    mount_angle: slot.mount_angle || 0,
    bounds: [cfg.layout.bounds.x, cfg.layout.bounds.y, cfg.layout.bounds.width, cfg.layout.bounds.height],
    source_size: [content.intrinsicWidth, content.intrinsicHeight],
    fit: content.fit,
  });
  const t = V.canvasTransformComponents({
    backing: [innerWidth, innerHeight],
    rect: [innerWidth, innerHeight],
    calibration: {
      viewport_width: calibr.viewport_width, viewport_height: calibr.viewport_height,
      quarter_turn: calibr.quarter_turn, panel_offset_mm: calibr.panel_offset_mm,
      mm_per_css: calibr.mm_per_css,
      panel_width: plan.active.width, panel_height: plan.active.height,
    },
    panel_from_source: plan.panel_from_source,
    source_size: [content.intrinsicWidth, content.intrinsicHeight],
  });
  const points = {
    left_border: [20, 500], right_border: [1980, 500],
    left_interior: [80, 500], right_interior: [1920, 500],
    top_border: [1000, 20], bottom_border: [1000, 980],
    center: [1000, 500],
  };
  const mapped = {};
  for (const [key, point] of Object.entries(points)) {
    const value = V.apply(t.matrix, point);
    mapped[key] = [value[0], value[1]];
  }
  return { dpr: devicePixelRatio, inner: [innerWidth, innerHeight], clip: t.clip, mapped,
           source: [content.intrinsicWidth, content.intrinsicHeight] };
}"""


def transform(tablet) -> dict:
    return tablet["page"].evaluate(TRANSFORM_JS, tablet["id"])


def inside_view(point, inner) -> bool:
    return 2 <= point[0] <= inner[0] - 2 and 2 <= point[1] <= inner[1] - 2


def record_command(step: str, command: list[str], result: subprocess.CompletedProcess) -> None:
    transcript.append({
        "step": step, "command": command, "cwd": str(ROOT),
        "returncode": result.returncode,
        "stdout_tail": (result.stdout or "")[-4000:],
        "stderr_tail": (result.stderr or "")[-4000:],
        "at": now(),
    })
    print("RUN", step, "exit", result.returncode, flush=True)


def run_tool(*args: str) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("TABLET_WALL", "WALL_"))}
    result = subprocess.run([PY, str(ROOT / "deploy" / "backup.py"), *args],
                            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=300)
    record_command("backup tool " + " ".join(args[:2]), [PY, "deploy/backup.py", *args], result)
    return result


def rest(method: str, *args, **kwargs):
    """One REST call on a fresh client, so a backend restart never leaves a dead pooled connection."""
    with Api(CURRENT_BASE[0]) as client:
        return getattr(client, method)(*args, **kwargs)


def ok(response):
    assert response.is_success, (f"{response.request.method} {response.request.url} "
                                 f"-> {response.status_code} {response.text[:300]}")
    return response


def online_count() -> int:
    devices = (config().get("runtime") or {}).get("devices") or {}
    return sum(1 for item in devices.values() if item.get("online"))


def numbered_ids() -> list[str]:
    snapshot = config()
    return sorted((tablet["id"] for tablet in tablets),
                  key=lambda device_id: device(snapshot, device_id).get("number"))


def saved_layout_names() -> list[str]:
    return [item["name"] for item in http("GET", "/layouts")[1]["layouts"]]


def confirm_model(device_id: str) -> None:
    ok(rest("put", f"/api/v3/tablet-assignments/{device_id}",
            {"mode": "explicit", "model_id": "google-pixel-c"}))
    check(config()["tablet_assignments"].get(device_id, {}).get("mode") == "explicit",
          "TWR-11 A1 " + device_id[:8] + " committed an explicit model assignment before calibration")
    snapshot = config()
    saved = max((item for item in snapshot["calibrations"] if item["device_id"] == device_id),
                key=lambda item: item["revision"])
    live = device(snapshot, device_id)["viewport"]
    ok(rest("put", f"/api/v3/calibrations/{device_id}", {
        "profile_revision": saved["profile_revision"],
        "viewport_width": live["width"], "viewport_height": live["height"], "dpr": live["dpr"],
        "orientation": live["orientation"], "mode": live["mode"],
        "quarter_turn": saved["quarter_turn"], "panel_offset_mm": saved["panel_offset_mm"],
        "mm_per_css": saved["mm_per_css"], "anchor_edge": saved["anchor_edge"],
        "uncertainty_mm": saved["uncertainty_mm"], "method": saved["method"]}))
    wait_until(lambda: any(item.get("device_id") == device_id
                           and item.get("viewport_width") == VIEW["width"]
                           and item["revision"] > saved["revision"]
                           for item in config()["calibrations"]),
               "viewport calibration was not saved")


def grid_command(kind: str, rows: int, columns: int, ids: list[str]) -> dict:
    command = {"kind": kind, "device_ids": ids, "rows": rows, "columns": columns, "gap": 0,
               "padding": 0, "sizing": "tablets", "orientation": "preserve",
               "allow_empty_cells": False, "release_unselected": []}
    if kind == "logical":
        command["logical_sizes"] = {device_id: {"w": VIEW["width"], "h": VIEW["height"]}
                                    for device_id in ids}
        return command
    snapshot = config()
    command["mount_angles"] = {device_id: 0 for device_id in ids}
    command["physical_revisions"] = {
        device_id: {
            "profile_revision": max(item["revision"] for item in snapshot["displays"]
                                    if item["device_id"] == device_id),
            "calibration_revision": max(item["revision"] for item in snapshot["calibrations"]
                                        if item["device_id"] == device_id),
        } for device_id in ids}
    return command


def apply_grid(kind: str, rows: int, columns: int) -> dict:
    _preview, applied = rest("grid", grid_command(kind, rows, columns, numbered_ids()))
    return ok(applied).json()


def show_image(asset_id: str, fit: str) -> None:
    ok(rest("scene", {"type": "image", "asset": asset_id, "fit": fit}))


def upload(path: Path, content_type: str):
    with Api(CURRENT_BASE[0]) as client:
        return client.http.post("/uploads", params={"name": path.name}, content=path.read_bytes(),
                                headers={"Content-Type": content_type})


def phase_start():
    notes.append("Application SHA " + APP_SHA + " on branch " + branch())
    status, health = http("GET", "/healthz")
    check(status == 200 and isinstance(health, dict), "/healthz answers 200 with a JSON body")
    check({"schema", "generation", "revision"}.issubset(health),
          "/healthz reports schema, generation and revision")
    check("counts" in health and "storage_readable" in health,
          "/healthz reports device counts and storage readability")
    serialized = json.dumps(health)
    check(str(ASSETS) not in serialized and str(DATA) not in serialized,
          "/healthz does not leak filesystem paths")


def phase_tablets():
    first = tablets[0]
    snapshot = config()
    record = device(snapshot, first["id"])
    check(record.get("viewport", {}).get("width") == VIEW["width"]
          and record.get("viewport", {}).get("height") == VIEW["height"],
          "tablet " + first["id"][:8] + " registered the simulated 900x1280 viewport")
    check(record.get("model_suggestions") == ["google-pixel-c"],
          "server matched the Pixel C signature for " + first["id"][:8])
    check(snapshot.get("tablet_assignments", {}).get(first["id"], {}).get("mode") == "auto",
          "TWR-11 A1 " + first["id"][:8] + " starts on an unconfirmed automatic assignment")
    check(not [item for item in snapshot.get("displays", []) if item.get("device_id") == first["id"]],
          "TWR-11 A1 " + first["id"][:8] + " has no physical profile before confirmation")
    check(not [item for item in snapshot.get("calibrations", []) if item.get("device_id") == first["id"]],
          "TWR-11 A1 " + first["id"][:8] + " has no physical scale before confirmation")
    confirm_model(first["id"])
    snapshot = config()
    check(any(item.get("provenance") == "tablet-model"
              for item in snapshot.get("displays", []) if item.get("device_id") == first["id"]),
          "TWR-11 A1 " + first["id"][:8] + " received physical scale only after confirmation")

    for _ in range(3):
        tablets.append(new_tablet(browser_ref[0], CURRENT_BASE[0]))
    wait_until(lambda: online_count() == 4, "the server did not see all four tablets join")

    for tablet in tablets[1:]:
        snapshot = config()
        record = device(snapshot, tablet["id"])
        check(record.get("viewport", {}).get("width") == VIEW["width"],
              "tablet " + tablet["id"][:8] + " registered the simulated viewport")
        check(record.get("model_suggestions") == ["google-pixel-c"],
              "server matched the Pixel C signature for " + tablet["id"][:8])
        check(snapshot.get("tablet_assignments", {}).get(tablet["id"], {}).get("mode") == "auto",
              "TWR-11 A1 " + tablet["id"][:8] + " starts on an unconfirmed automatic assignment")
        check(not [item for item in snapshot.get("displays", []) if item.get("device_id") == tablet["id"]],
              "TWR-11 A1 " + tablet["id"][:8] + " has no physical profile before confirmation")
        check(not [item for item in snapshot.get("calibrations", []) if item.get("device_id") == tablet["id"]],
              "TWR-11 A1 " + tablet["id"][:8] + " has no physical scale before confirmation")
        confirm_model(tablet["id"])

    wait_until(lambda: len({item.get("device_id") for item in config().get("displays", [])}) == 4,
               "not every tablet recorded a model profile")
    snapshot = config()
    profiles = snapshot.get("displays", [])
    calibrations = snapshot.get("calibrations", [])
    check(len(profiles) == 4, "four model profiles were recorded after confirmation")
    check(all(item.get("provenance") == "tablet-model" for item in profiles),
          "TWR-11 A2 every profile records the model provenance")
    check(all(item.get("method") == "tablet-model approximate" for item in calibrations),
          "TWR-11 A2 every calibration records the approximate model method")
    check(all(item.get("uncertainty_mm") == 3.0 for item in calibrations),
          "TWR-11 A2 every model calibration records ±3.0 mm uncertainty")


def phase_pinned_health():
    wait_until(lambda: all((item.get("mapping") or {}).get("state") == "ready"
                           for item in config()["runtime"]["devices"].values()),
               "not every pinned slot reached a ready mapping")
    snapshot = config()
    check(all((item.get("mapping") or {}).get("state") == "ready" for item in
              snapshot["runtime"]["devices"].values()),
          "TWR-11 A3 every pinned slot maps with its saved profile and calibration")
    for tablet in tablets:
        record = device(snapshot, tablet["id"])
        health = (record.get("mapping") or {}).get("health") or {}
        check(health.get("ok") is False,
              "TWR-11 A2 " + tablet["id"][:8] + " model health does not claim ok")
        check((health.get("provenance") or {}).get("model") is True
              and (health.get("provenance") or {}).get("approximate") is True
              and (health.get("provenance") or {}).get("confirmed") is True,
              "TWR-11 A2 " + tablet["id"][:8] + " health is approximate, model-derived and confirmed")


def phase_logical_grid():
    before = config()
    apply_grid("logical", 2, 2)
    wait_until(lambda: len(config()["layout"].get("placements", {})) == 4,
               "logical 2x2 was not applied")
    after = config()
    check(after["revision"] == before["revision"] + 1,
          "TWR-10 A1 the logical 2x2 apply incremented the wall revision exactly once "
          f"({before['revision']} -> {after['revision']})")
    placements = after["layout"]["placements"]
    numbers = {key: device(after, key).get("number") for key in placements}
    check(all(number in (1, 2, 3, 4) for number in numbers.values()),
          "TWR-10 A1 all four numbered tablets occupy the 2x2 draft")
    ordered = sorted(placements, key=lambda key: numbers[key])
    expected = [(0, 0), (0, 1), (1, 0), (1, 1)]
    xs = sorted({round(placements[key]["x"]) for key in placements})
    ys = sorted({round(placements[key]["y"]) for key in placements})
    matched = True
    for index, key in enumerate(ordered):
        column = 0 if round(placements[key]["x"]) == xs[0] else 1
        row = 0 if round(placements[key]["y"]) == ys[0] else 1
        matched = matched and (row, column) == expected[index]
    check(matched, "TWR-10 A1 the 2x2 places #1..#4 in row-major number order")
    note("Broadcast count is not re-measured here; docs/tablet-wall-readiness/EFFICIENCY.md records "
         "the atomic-grid route and the one-broadcast result for the 2x2 apply.")


def phase_physical_grid():
    before = config()
    applied = apply_grid("physical", 1, 4)
    wait_until(lambda: config()["layout"].get("kind") == "physical"
               and len(config()["layout"].get("slots", {})) == 4,
               "physical 1x4 was not applied")
    after = config()
    check(after["revision"] == before["revision"] + 1,
          "TWR-10 A1 the physical 1x4 apply incremented the revision exactly once "
          f"({before['revision']} -> {after['revision']})")
    return_name = applied.get("previous_layout_saved") or ""
    check(return_name.startswith("Before physical "),
          "TWR-09 A6 the cross-kind Apply response names the generated return point")
    check(return_name in saved_layout_names(),
          "TWR-09 A6 the generated return point is stored as an automatic saved layout")

    slots = after["layout"]["slots"]
    numbers = {key: device(after, key).get("number") for key in slots}
    ordered = sorted(slots, key=lambda key: numbers[key])
    xs = [slots[key]["center_x_mm"] for key in ordered]
    check(xs == sorted(xs) and len({round(slot["center_x_mm"]) for slot in slots.values()}) == 4,
          "TWR-10 A2 the 1x4 slots advance left to right in #1..#4 order")
    check(len({round(slot["center_y_mm"]) for slot in slots.values()}) == 1,
          "TWR-10 A2 the 1x4 slots share one measured row")
    check(all(slot.get("profile_revision") and slot.get("calibration_revision")
              for slot in slots.values()),
          "TWR-10 A2 every 1x4 slot pins its confirmed profile and calibration")
    phase_pinned_health()
    return return_name


def phase_content(return_name: str):
    first = image_id("first.png")
    marked = image_id("marked.png")
    show_image(first, "cover")
    wait_painted(first)

    show_image(marked, "contain")
    check(config()["scene"]["content"].get("fit") == "contain",
          "TWR-04 A1 image B is committed with the selected fit")
    wait_painted(marked)
    check(True, "TWR-04 A1 all four tablets confirmed image B")

    legacy_context = browser_ref[0].new_context(viewport={"width": 1280, "height": 900})
    legacy = legacy_context.new_page()
    legacy.goto(CURRENT_BASE[0] + "/controller/experimental.html", wait_until="load")
    wait_until(lambda: "read-only" in legacy.locator("#compatibility-guard-text").inner_text()
               or "could not be checked" in legacy.locator("#compatibility-guard-text").inner_text(),
               "legacy compatibility guard did not finish its layout check")
    guard = legacy.locator("#compatibility-guard-text").inner_text()
    check("measured layout" in guard and "read-only" in guard,
          "TWR-04 A5 the legacy editor shows a hard measured-layout banner and read-only wording")
    check(legacy.locator("#app").is_hidden(),
          "TWR-04 A5 the legacy editing workspace is hidden on a physical wall")
    status, body = http("PUT", "/wall", {"width": 1000, "height": 500})
    check(status == 409 and "Upgrade controller" in (body or {}).get("detail", ""),
          "TWR-04 A5 the legacy wall mutation is fenced with 409 on a physical wall")
    shot(legacy, "07-legacy-guard.png", full=True)
    legacy_context.close()

    layout_before = config()["layout"]
    ok(rest("scene", {"type": "color"}))
    check(config()["layout"] == layout_before,
          "TWR-04 A2 Tablet colours change content without changing the arrangement")
    time.sleep(0.5)
    check(tablets[0]["page"].evaluate(
        "getComputedStyle(document.getElementById('surface')).display") == "none",
        "TWR-04 A2 the tablet client switches to its colour surface for Tablet colours")
    show_image(marked, "contain")

    pattern = ok(rest("test_pattern", "black")).json()
    show_image(pattern["id"], "contain")
    black_id = config()["scene"]["content"]["asset"]
    wait_painted(black_id)
    check(config()["layout"] == layout_before,
          "TWR-04 A2 Black wall shows a generated image without changing the layout")
    check(True, "TWR-11 A5 Black wall is generated and painted without a shell copy step")
    show_image(marked, "contain")

    check(return_name in saved_layout_names(),
          "TWR-09 A6 the physical return point survives later content changes")
    return marked


def phase_fit(marked: str):
    show_image(marked, "contain")
    wait_until(lambda: config()["scene"]["content"].get("fit") == "contain",
               "scene did not carry contain")
    wait_painted(marked)

    fit_shots = {}
    for tablet in tablets:
        path = SHOTS / f"09-fit-{tablet['id'][:8]}.png"
        tablet["page"].screenshot(path=str(path))
        fit_shots[tablet["id"]] = path
    mapped = {tablet["id"]: transform(tablet) for tablet in tablets}
    left_visible = inside_view(mapped[tablets[0]["id"]]["mapped"]["left_border"],
                               mapped[tablets[0]["id"]]["inner"])
    right_visible = inside_view(mapped[tablets[3]["id"]]["mapped"]["right_border"],
                                mapped[tablets[3]["id"]]["inner"])
    check(left_visible and right_visible,
          "TWR-05 A1 the client model places the left and right source borders inside the outer 1x4 slices")
    top_hidden = not inside_view(mapped[tablets[0]["id"]]["mapped"]["top_border"],
                                 mapped[tablets[0]["id"]]["inner"])
    bottom_hidden = not inside_view(mapped[tablets[0]["id"]]["mapped"]["bottom_border"],
                                    mapped[tablets[0]["id"]]["inner"])
    check(top_hidden and bottom_hidden,
          "TWR-05 A4 the top and bottom source borders fall behind the measured bezel, not into a crop")

    first_pixel = sample_colour(fit_shots[tablets[0]["id"]],
                               mapped[tablets[0]["id"]]["mapped"]["left_border"][0] * 2,
                               mapped[tablets[0]["id"]]["mapped"]["left_border"][1] * 2)
    check(is_magenta(first_pixel),
          f"TWR-05 A1 the left source border is painted on tablet #1 under Fit (sampled {first_pixel})")
    fourth_pixel = sample_colour(fit_shots[tablets[3]["id"]],
                                mapped[tablets[3]["id"]]["mapped"]["right_border"][0] * 2,
                                mapped[tablets[3]["id"]]["mapped"]["right_border"][1] * 2)
    check(is_magenta(fourth_pixel),
          f"TWR-05 A1 the right source border is painted on tablet #4 under Fit (sampled {fourth_pixel})")
    check(magenta_pixels(fit_shots[tablets[1]["id"]]) == 0
          and magenta_pixels(fit_shots[tablets[2]["id"]]) == 0,
          "TWR-05 A1 interior slices contain no source border under Fit, as the global transform predicts")
    interior_first = sample_colour(fit_shots[tablets[0]["id"]],
                                  mapped[tablets[0]["id"]]["mapped"]["left_interior"][0] * 2,
                                  mapped[tablets[0]["id"]]["mapped"]["left_interior"][1] * 2)
    interior_fourth = sample_colour(fit_shots[tablets[3]["id"]],
                                   mapped[tablets[3]["id"]]["mapped"]["right_interior"][0] * 2,
                                   mapped[tablets[3]["id"]]["mapped"]["right_interior"][1] * 2)
    check(_distance(interior_first, GREEN) < 900 and _distance(interior_fourth, GREEN) < 900,
          "TWR-05 A1 the Fit image interior is painted consistently on the outer slices")
    edge_first = sample_colour(fit_shots[tablets[0]["id"]], 100 * 2, 640 * 2)
    check(_distance(edge_first, BACKGROUND) < 900,
          "TWR-05 A1 tablet #1 shows the Fit letterbox where the source has not started")

    show_image(marked, "cover")
    wait_painted(marked)
    fill_counts = {}
    for tablet in tablets:
        path = SHOTS / f"10-fill-{tablet['id'][:8]}.png"
        tablet["page"].screenshot(path=str(path))
        fill_counts[tablet["id"]] = magenta_pixels(path)
    check(all(count == 0 for count in fill_counts.values()),
          "TWR-05 A1 Fill crops the marked border out of every slice, as the model predicts")
    fill_map = {tablet["id"]: transform(tablet) for tablet in tablets}
    fill_first = sample_colour(SHOTS / f"10-fill-{tablets[0]['id'][:8]}.png",
                              fill_map[tablets[0]["id"]]["mapped"]["left_interior"][0] * 2,
                              fill_map[tablets[0]["id"]]["mapped"]["left_interior"][1] * 2)
    fill_fourth = sample_colour(SHOTS / f"10-fill-{tablets[3]['id'][:8]}.png",
                               fill_map[tablets[3]["id"]]["mapped"]["right_interior"][0] * 2,
                               fill_map[tablets[3]["id"]]["mapped"]["right_interior"][1] * 2)
    check(_distance(fill_first, GREEN) < 900 and _distance(fill_fourth, GREEN) < 900,
          "TWR-05 A1 Fill spans the wall with the source interior on both outer slices")


def phase_failure():
    marked = image_id("marked.png")
    target = tablets[2]
    target["context"].route("**/assets/**", lambda route: route.abort())
    show_image(marked, "contain")

    def one_failed():
        return any(item.get("render", {}).get("state") == "failed"
                   for item in config()["runtime"]["devices"].values())

    wait_until(one_failed, "the aborted image load did not surface as a failed render", timeout=30)
    target["context"].unroute("**/assets/**")
    ok(rest("post", f"/api/v3/devices/{target['id']}/retry-image", guarded=True))
    wait_painted(marked)

    offline = tablets[3]
    offline["page"].close()
    wait_until(lambda: device(config(), offline["id"]).get("online") is False,
               "closed tablet did not report offline")
    offline["page"] = offline["context"].new_page()
    offline["page"].goto(CURRENT_BASE[0] + "/client/", wait_until="load")
    wait_until(lambda: offline["page"].locator("#status").get_attribute("data-state") == "connected",
               "reopened tablet did not reconnect")
    wait_painted(marked)


def phase_label():
    tablet = tablets[1]
    label = "North panel α"
    ok(rest("guarded", "PATCH", f"/api/v3/devices/{tablet['id']}", {"label": label}))
    wait_until(lambda: config()["device_labels"].get(tablet["id"]) == label,
               "label was not saved")
    ok(rest("guarded", "PUT", "/api/v3/layouts/Portrait row"))
    wait_until(lambda: "Portrait row" in saved_layout_names(),
               "physical arrangement was not saved")


def phase_restart_identify():
    tablet = tablets[1]
    label = "North panel α"
    server.stop()
    server.start()
    for item in tablets:
        wait_until(lambda item=item: item["page"].locator("#status").get_attribute("data-state") == "connected",
                   "tablet did not reconnect after the private backend restart", timeout=30)
    wait_until(lambda: online_count() == 4, "server did not see four reconnected tablets", timeout=30)
    check(config()["device_labels"].get(tablet["id"]) == label,
          "TWR-08 A1 the label survived a real backend restart")
    check(tablet["id"] in get_json_layout_slots(),
          "TWR-08 A1 the saved arrangement still references the labelled tablet identity after restart")

    before_revision = config()["revision"]
    started = time.perf_counter()
    ok(rest("identify", tablet["id"]))
    wait_until(lambda: not tablet["page"].evaluate("document.getElementById('identify').hidden"),
               "Identify overlay did not appear", timeout=5)
    elapsed = time.perf_counter() - started
    number = device(config(), tablet["id"]).get("number")
    overlay_number = tablet["page"].locator("#identify-number").inner_text()
    overlay_label = tablet["page"].locator("#identify-label").inner_text()
    check(overlay_number == f"#{number}", "TWR-08 A2 Identify shows the correct tablet number " + overlay_number)
    check(overlay_label == label, "TWR-08 A2 Identify shows the correct tablet name " + overlay_label)
    check(elapsed < 1.0,
          f"TWR-08 A2 Identify was visible within 1 s on loopback ({elapsed:.3f} s, click-to-overlay)")
    note(f"Identify timing method: POST /api/v3/devices/{{id}}/identify request start to visible DOM "
         f"overlay on a loopback Chromium context, measured {elapsed:.3f} s; the check name keeps its "
         f"original 'click-to-overlay' wording, but no console click is involved. This is not a "
         f"hardware timing claim.")
    check(config()["revision"] == before_revision,
          "TWR-08 A2 Identify leaves the wall revision and content unchanged")
    wait_until(lambda: tablet["page"].evaluate("document.getElementById('identify').hidden"),
               "Identify overlay did not expire", timeout=12)
    check(tablet["page"].evaluate("document.getElementById('identify').hidden"),
          "TWR-08 A2 Identify clears on expiry")
    check(config()["revision"] == before_revision,
          "TWR-08 A2 Identify expiry does not bump the wall revision")
    shot(tablet["page"], "13-identify.png", full=False)


def get_json_layout_slots():
    layout = config()["layout"]
    return layout.get("slots") or layout.get("placements") or {}


def phase_rebind_preview():
    old = tablets[3]
    old["page"].close()
    wait_until(lambda: device(config(), old["id"]).get("online") is False,
               "closed tablet did not become offline")
    context = browser_ref[0].new_context(viewport=VIEW, screen=VIEW, device_scale_factor=2,
                                         user_agent=TABLET_UA)
    context.add_init_script("Object.defineProperty(screen.orientation, 'angle', {get: () => 270, configurable: true});")
    replacement = context.new_page()
    replacement.goto(CURRENT_BASE[0] + "/client/", wait_until="load")
    wait_until(lambda: replacement.locator("#status").get_attribute("data-state") == "connected",
               "replacement registration did not connect")
    new_id = replacement.evaluate("localStorage.getItem('tablet-wall-device-id')")
    check(new_id != old["id"], "a replacement browser registered a distinct identity")

    before = config()
    preview = ok(rest("post", f"/api/v3/devices/{new_id}/rebind/preview", {
        "replaces": old["id"], "hardware": "same_hardware", "active": True,
        "saved_layouts": [], "transfer_label": True}, guarded=True)).json()
    technical = json.dumps(preview)
    check("profile_revision_map" in technical and "calibration_revision_map" in technical,
          "TWR-09 A1 the replacement preview reports profile and calibration revision maps")
    after = config()
    check(after["revision"] == before["revision"] and after["layout"] == before["layout"],
          "TWR-09 A1 the replacement preview writes nothing to the wall")
    check(old["id"] in after["runtime"]["devices"] and new_id in after["runtime"]["devices"]
          and old["id"] in get_json_layout_slots(),
          "TWR-09 A1 the replacement preview leaves the roster and active placement untouched")
    note("Rebind apply and recall-after-replacement are retained in the 106-check journey at "
         "readiness-program/final-qa/20261101T120950Z/; this run adds the exact preview revision maps.")
    old["page"] = old["context"].new_page()
    old["page"].goto(CURRENT_BASE[0] + "/client/", wait_until="load")
    wait_until(lambda: old["page"].locator("#status").get_attribute("data-state") == "connected",
               "the original tablet identity did not reconnect after the preview")
    wait_painted(image_id("marked.png"))


def phase_return_point():
    before = config()
    logical_return = apply_grid("logical", 2, 2).get("previous_layout_saved") or ""
    check(logical_return.startswith("Before logical "),
          "TWR-09 A6 the physical-to-logical Apply names its generated return point")
    check(logical_return in saved_layout_names(),
          "TWR-09 A6 the physical-to-logical return point is stored as an automatic layout")

    ok(rest("post", "/api/v3/layouts/Portrait row/recall", guarded=True))
    wait_until(lambda: config()["layout"].get("kind") == "physical",
               "cross-kind recall did not return to the physical arrangement")
    check(any(name.startswith("Before physical ") for name in saved_layout_names()),
          "TWR-09 A6 the logical-to-physical return point is retrievable as a saved layout")
    check(config()["revision"] == before["revision"] + 2,
          "TWR-09 A5 both cross-kind directions each committed exactly one wall revision")


def phase_fence():
    tablet = tablets[0]
    tablet["page"].set_viewport_size({"width": 1200, "height": 1300})
    wait_until(lambda: device(config(), tablet["id"]).get("mapping", {}).get("state") == "viewport_mismatch",
               "a changed viewport did not raise a mapping fence", timeout=20)
    snapshot = config()
    health = device(snapshot, tablet["id"]).get("mapping", {}).get("health") or {}
    warning = health.get("actionable_warning") or {}
    check("exceeds" in warning.get("message", "") and "900" in warning.get("message", "")
          and "1280" in warning.get("message", ""),
          "TWR-11 A4 a real viewport change produces the specific oversized-viewport fence: "
          + warning.get("message", ""))
    check("Clear browser zoom/scale" in warning.get("action", ""),
          "TWR-11 A4 the fence carries a practical recovery action: " + warning.get("action", ""))
    tablet["page"].set_viewport_size(VIEW)
    wait_until(lambda: device(config(), tablet["id"]).get("mapping", {}).get("state") == "ready",
               "restoring the viewport did not clear the fence", timeout=20)
    wait_painted(image_id("marked.png"))
    check(True, "TWR-11 A4 restoring the native viewport clears the fence and repaints")


def phase_uploads():
    capabilities = config().get("capabilities") or {}
    check(capabilities.get("uploads") is True,
          "TWR-04 A3 loopback capabilities advertise uploads")
    limits_source = (ROOT / "tabletwall" / "media_limits.py").read_text(encoding="utf-8")
    check("MAX_SOURCE_BYTES = 32 * 1024 * 1024" in limits_source,
          "TWR-04 A3 the checked-out server source limits a still source to 32 MiB")
    note("Server still-image source limit is 32 MiB (tabletwall/media_limits.py MAX_SOURCE_BYTES).")

    layout_before = config()["layout"]
    assets_before = {item["id"] for item in http("GET", "/api/v3/images")[1]["images"]}
    uploaded = upload(ASSETS / "upload-ok.png", "image/png")
    assert uploaded.status_code == 201, f"valid PNG upload was refused: {uploaded.status_code} {uploaded.text[:300]}"
    assets_after = {item["id"] for item in http("GET", "/api/v3/images")[1]["images"]}
    check(len(assets_after) > len(assets_before),
          "TWR-04 A3 the uploaded PNG joined the still-image inventory")
    check(config()["layout"] == layout_before,
          "TWR-04 A3 a valid upload leaves the wall layout unchanged")

    rejected = upload(ARTIFACTS / "upload-bad.txt", "text/plain")
    rejection = rejected.json().get("detail", "")
    check(rejected.status_code == 415 and "only image/jpeg, image/png" in rejection,
          "TWR-04 A3 a disallowed type produces a readable rejection: " + rejection)
    check(config()["layout"] == layout_before,
          "TWR-04 A3 a rejected upload leaves the wall layout unchanged")

    webp = upload(ARTIFACTS / "upload-unsupported.webp", "image/webp")
    webp_message = webp.json().get("detail", "")
    check(webp.status_code == 415 and "only image/jpeg, image/png" in webp_message,
          "TWR-04 A3 bypassing the picker with unsupported WebP still reports a readable rejection")
    check(config()["layout"] == layout_before,
          "TWR-04 A3 a forced unsupported upload still leaves the layout unchanged")


def phase_drill():
    pattern = ok(rest("test_pattern", "black")).json()
    show_image(pattern["id"], "contain")
    black_id = pattern["id"]
    wait_painted(black_id)
    black_url = pattern["url"]
    with urllib.request.urlopen(CURRENT_BASE[0] + black_url, timeout=30) as response:
        original_bytes = hashlib.sha256(response.read()).hexdigest()

    status, health = http("GET", "/healthz")
    check(status == 200 and "schema" in health and "revision" in health,
          "TWR-13 A4 /healthz reports schema and revision before the runbook stop")
    layout_before = config()["layout"]
    labels_before = config()["device_labels"]
    devices_before = {key: {"number": item.get("number"), "label": item.get("label")}
                      for key, item in config()["runtime"]["devices"].items()}
    server.stop()
    backup_dest = ARTIFACTS / "backup" / "snapshot"
    backup_dest.parent.mkdir(parents=True, exist_ok=True)
    backup = run_tool("backup", "--db", str(DATA / "wall.db"), "--assets", str(ASSETS),
                      "--media", str(MEDIA), "--dest", str(backup_dest))
    check(backup.returncode == 0, "TWR-13 A4 backup exits 0 on the stopped private instance")
    manifest_path = backup_dest / "manifest.json"
    check(manifest_path.exists(), "TWR-13 A4 the backup wrote a manifest")
    manifest = json.loads(manifest_path.read_text())
    check(black_id in manifest.get("references", []),
          "TWR-13 A5 the backup includes the referenced Black wall generated image")
    verify = run_tool("verify", "--src", str(backup_dest))
    check(verify.returncode == 0, "TWR-13 A4 verify exits 0 for the new snapshot")

    restore_root = ARTIFACTS / "restore"
    (restore_root).mkdir(parents=True, exist_ok=True)
    restore = run_tool("restore", "--src", str(backup_dest),
                       "--db", str(restore_root / "wall.db"),
                       "--assets", str(restore_root / "assets"),
                       "--media", str(restore_root / "media"))
    check(restore.returncode == 0, "TWR-13 A4 restore into new paths exits 0")
    check((restore_root / "wall.db").exists() and (restore_root / "assets").is_dir(),
          "TWR-13 A4 restore created the database and assets at new paths")
    note("Restore writes media at the target when the snapshot contains managed media; the restored "
         "server creates an empty media directory on boot when the snapshot has none.")

    restored_backups = ARTIFACTS / "restored-backups"
    restored_backups.mkdir(exist_ok=True)
    restored = Instance(restore_root / "wall.db", restore_root / "assets",
                        restore_root / "media", restored_backups,
                        "disabled", tag="server-restored").start()
    servers.append(restored)
    CURRENT_BASE[0] = restored.base
    try:
        status, _restored_health = http("GET", "/healthz")
        check(status == 200, "TWR-13 A4 the restored copy boots and answers /healthz")
        snapshot = config()
        check(snapshot["scene"]["content"].get("asset") == black_id,
              "TWR-13 A4 the restored copy still has the Black wall scene")
        check(snapshot["layout"] == layout_before,
              "TWR-13 A4 the restored copy preserves the measured arrangement")
        check(snapshot["device_labels"] == labels_before,
              "TWR-13 A4 the restored copy preserves device labels")
        restored_devices = {key: {"number": item.get("number"), "label": item.get("label")}
                            for key, item in http("GET", "/devices")[1].items()}
        check(restored_devices == devices_before,
              "TWR-13 A4 the restored copy preserves durable device numbers and labels")
        with urllib.request.urlopen(restored.base + black_url, timeout=30) as response:
            restored_digest = hashlib.sha256(response.read()).hexdigest()
        check(restored_digest == original_bytes,
              "TWR-13 A4 the restored copy serves byte-identical Black wall content")
        note("Restored instance booted on private loopback origin " + restored.base
             + " from artifacts/restore; no installed service, TLS, or reboot was used.")
    finally:
        restored.stop()
    transcript.append({"step": "runbook chain", "steps": [
        "private start", "healthz", "Black wall", "stop", "backup", "verify",
        "restore to new paths", "boot restored copy"], "at": now()})


def main() -> int:
    global ARTIFACTS, SHOTS, DATA, ASSETS, MEDIA, BACKUPS, PY, APP_SHA, DRIVER_SHA, STARTED
    global server, browser_ref, tablets, servers

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--artifacts", required=True, type=Path,
                        help="fresh directory for screenshots, results and transcript")
    args = parser.parse_args()
    ARTIFACTS = args.artifacts.resolve()
    if ARTIFACTS.exists() and any(ARTIFACTS.iterdir()):
        raise SystemExit(f"artifacts directory is not fresh: {ARTIFACTS}")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    SHOTS = ARTIFACTS / "screenshots"
    SHOTS.mkdir()
    DATA = ARTIFACTS / "data"
    ASSETS = DATA / "assets"
    MEDIA = DATA / "media"
    BACKUPS = DATA / "backups"
    for path in (ASSETS, MEDIA, BACKUPS):
        path.mkdir(parents=True, exist_ok=True)
    PY = sys.executable
    APP_SHA = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                             capture_output=True, text=True).stdout.strip()
    DRIVER_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    STARTED = now()

    make_images()
    server = Instance(DATA / "wall.db", ASSETS, MEDIA, BACKUPS, "disabled", tag="server-main").start()
    CURRENT_BASE[0] = server.base
    servers = [server]
    tablets = []
    browser_ref = [None]

    browser = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser_ref[0] = browser
            CHROMIUM_VERSION[0] = browser.version

            def phase(name: str, function, *arguments):
                print("PHASE", name, flush=True)
                try:
                    return function(*arguments)
                except Exception as error:
                    failures.append(f"{name}: {type(error).__name__}: {error}")
                    print("PHASE FAILED", name, type(error).__name__, error, flush=True)
                    traceback.print_exc()
                    return None
                finally:
                    persist()

            persist()
            phase("start", phase_start)

            tablets.append(new_tablet(browser, server.base))
            wait_until(lambda: online_count() == 1, "the server did not see the first tablet join")

            phase("tablets", phase_tablets)
            phase("logical grid", phase_logical_grid)
            return_name = phase("physical grid", phase_physical_grid) or "Before physical unknown"
            marked = phase("content", phase_content, return_name)
            if not isinstance(marked, str):
                marked = image_id("marked.png")
            phase("fit", phase_fit, marked)
            phase("failure", phase_failure)
            phase("label", phase_label)
            phase("restart and identify", phase_restart_identify)
            phase("rebind preview", phase_rebind_preview)
            phase("return point", phase_return_point)
            phase("fence", phase_fence)

            server.stop()
            server = Instance(DATA / "wall.db", ASSETS, MEDIA, BACKUPS, "loopback",
                              port=server.port, origin=server.origin, tag="server-uploads").start()
            servers.append(server)
            CURRENT_BASE[0] = server.base
            for item in tablets:
                wait_until(lambda item=item: item["page"].locator("#status").get_attribute("data-state") == "connected",
                           "tablet did not reconnect to the upload instance", timeout=30)
            phase("uploads", phase_uploads)
            phase("drill", phase_drill)
            check(not [error for item in tablets for error in item["errors"]],
                  "no tablet page exceptions in the full journey")
    except Exception as error:
        failures.append(f"driver: {type(error).__name__}: {error}")
        traceback.print_exc()
    finally:
        for item in servers:
            try:
                item.stop()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        persist()

    print("CHECKS", len(checks), "FAILURES", len(failures), "FINDINGS", len(findings), flush=True)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())


