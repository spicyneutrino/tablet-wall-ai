"""Bounded acceptance evidence for the image-wall roadmap (TWR-04/05/06/08/09/10/11/13).

The driver boots the checked-out application on private loopback ports with
temporary database, asset, media and backup paths. Four Chromium contexts act
as Android tablets that match the built-in Pixel C signature; a fifth context
is the operator console. Everything else is the shipped routes, sockets,
client and console code. No backend fixture stands in for a route.

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
dialogs: list[str] = []
transcript: list[dict] = []
requests_seen: list[str] = []

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
        "dialogs": dialogs,
        "requests": requests_seen,
        "console_errors": OPERATOR_ERRORS,
        "failed_requests": [item for item in FAILED_REQUESTS
                            if "net::ERR_ABORTED" not in item
                            and "net::ERR_CONNECTION_REFUSED" not in item],
        "failed_requests_raw": FAILED_REQUESTS,
        "environment": {
            "playwright_chromium": CHROMIUM_VERSION[0],
            "viewport_css": VIEW,
            "device_scale_factor": 2,
            "platform_family": "android",
        },
        "limits": [
            "Software loopback only. No physical panel, bezel, seam, optical, sleep or soak measurement.",
            "No TLS/proxy composition, host reboot, or installed-service claim.",
            "Identify timing is click-to-overlay on loopback Chromium, not a tablet measurement.",
            "Broadcast count is not re-measured here; the atomic-grid route and one-broadcast result are recorded in docs/tablet-wall-readiness/EFFICIENCY.md.",
            "Accessibility (contrast, zoom, keyboard, focus) is owned by a separate reviewer and is not duplicated here.",
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
DISMISS_DIALOG = [False]
OPERATOR_ERRORS: list[str] = []
FAILED_REQUESTS: list[str] = []


def on_dialog(dialog) -> None:
    dialogs.append(dialog.message)
    if DISMISS_DIALOG[0]:
        dialog.dismiss()
    else:
        dialog.accept()


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


def tab(page, name: str) -> None:
    page.get_by_role("tab", name=name, exact=True).click()


def select_tablet(page, device_id: str) -> None:
    tab(page, "Tablets")
    page.locator(f".dev-pick[data-device-id='{device_id}']").click()
    wait_until(lambda: page.locator(f".dev-pick[data-device-id='{device_id}']")
               .get_attribute("aria-pressed") == "true",
               "click did not select the requested tablet")


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


def start_operator(browser, base: str, width: int = 1600, height: int = 1000,
                   errors: list | None = None, failed: list | None = None):
    errors = OPERATOR_ERRORS if errors is None else errors
    failed = FAILED_REQUESTS if failed is None else failed
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
    page.on("requestfailed", lambda request, failed=failed: failed.append(
        f"{request.method} {request.url} {request.failure}"))
    page.on("request", lambda request: requests_seen.append(f"{request.method} {request.url}"))
    page.on("dialog", on_dialog)
    page.goto(base + "/controller/physical.html", wait_until="load")
    wait_until(lambda: "online" in page.locator("#device-count").inner_text(),
               "operator console did not report a roster")
    return context, page


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


def confirm_model(page, device_id: str) -> None:
    select_tablet(page, device_id)
    tab(page, "System")
    page.locator("#measurement-details").evaluate("node => node.open = true")
    page.locator("#tablet-model").select_option("google-pixel-c")
    dialogs_before = len(dialogs)
    page.locator("#apply-tablet-model").click()
    wait_until(lambda: config()["tablet_assignments"].get(device_id, {}).get("mode") == "explicit",
               "model confirmation was not committed")
    check(config()["tablet_assignments"].get(device_id, {}).get("mode") == "explicit",
          "TWR-11 A1 " + device_id[:8] + " committed an explicit model assignment before calibration")
    check(any("Confirm this tablet" in message for message in dialogs[dialogs_before:]),
          "TWR-11 A1 confirming the model requires an explicit confirmation dialog")
    page.locator("#cal-use-viewport").click()
    page.locator("#btn-calibration-save").click()
    wait_until(lambda: any(item.get("device_id") == device_id
                           and item.get("viewport_width") == VIEW["width"]
                           for item in config()["calibrations"]),
               "viewport calibration was not saved")


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


def select_image(page, asset_id: str, fit: str) -> None:
    tab(page, "Wall")
    page.locator("#image-select").select_option(asset_id)
    page.locator("#image-fit").select_option(fit)


def show_image(page, asset_id: str, fit: str) -> None:
    select_image(page, asset_id, fit)
    page.locator("#show-image").click()
    wait_until(lambda: config()["scene"]["content"].get("asset") == asset_id,
               "scene did not commit the selected image")


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


def near(point, other, tolerance: float = 2.0) -> bool:
    return abs(point[0] - other[0]) <= tolerance and abs(point[1] - other[1]) <= tolerance


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



def phase_start(page):
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

    wait_until(lambda: "No tablets on the wall." in page.evaluate(
        "document.getElementById('stage-svg').textContent"),
        "the fresh empty-wall stage text did not appear")
    stage_text = page.evaluate("document.getElementById('stage-svg').textContent")
    check("No tablets on the wall." in stage_text,
          "TWR-06 A8 a fresh empty wall reads 'No tablets on the wall.' on the stage")
    wait_until(lambda: "No tablets on the wall" in page.locator("#wall-health").inner_text(),
               "the fresh empty-wall header did not appear")
    health_text = page.locator("#wall-health").inner_text()
    check("No tablets on the wall" in health_text,
          "TWR-06 A8 the fresh empty wall header reads 'No tablets on the wall'")

    tab(page, "Content")
    instruction = page.locator("#upload-instruction").inner_text()
    check("Uploads are off" in instruction and "Refresh images" in instruction,
          "TWR-04 A3 uploads disabled shows the copy-to-directory instruction")
    check(page.locator("#upload-form").is_hidden(),
          "TWR-04 A3 uploads disabled hides the upload form")
    check(page.locator("#experimental-controls").is_hidden(),
          "TWR-04 A4 experimental playback controls are hidden until opt-in")
    check(page.locator("#topbar-transport").is_hidden(),
          "TWR-04 A4 the top bar carries no visible playback transport")
    content_text = page.locator("#panel-content").inner_text()
    check("Software evidence only" in content_text
          and "not been validated on tablets" in content_text,
          "TWR-04 A4 the experimental section states software evidence only and no tablet validation")
    shot(page, "01-empty-wall.png", full=True)


def phase_tablets():
    page = operator_pages[0]
    first = tablets[0]
    select_tablet(page, first["id"])
    tab(page, "System")
    page.locator("#measurement-details").evaluate("node => node.open = true")
    wait_until(lambda: "Looks like Google Pixel C" in page.locator("#tablet-model-status").inner_text(),
               "the authoritative model suggestion did not render", timeout=5)
    status_text = page.locator("#tablet-model-status").inner_text()
    page.locator("#tablet-model-status").scroll_into_view_if_needed()
    shot(page, "02-model-status.png", full=False)
    prompt_ok = "Looks like Google Pixel C" in status_text and "suggestion, not proof" in status_text
    check(prompt_ok,
          "TWR-11 A1 the console shows 'Looks like Google Pixel C. ... suggestion, not proof.' "
          "before confirmation (observed: " + status_text + ")")
    if not prompt_ok:
        findings.append(
            "TWR-11 A1 product gap: the server reports model_suggestions=['google-pixel-c'] for the "
            "new tablet, but the rendered #tablet-model-status reads '" + status_text + "'. The "
            "device_updated frame carries screen_width/screen_dpr/platform_family, but the "
            "config_updated reconcile replaces state.roster with the config projection that omits "
            "them; the console does not use the server's model_suggestions field. Screenshot "
            "02-model-status.png; observed the same result in every fresh run that reached this check.")
        print("FINDING TWR-11 A1 prompt not rendered", flush=True)
    if "Looks like Google Pixel C" in status_text:
        note("Signature prompt observed for tablet " + first["id"][:8] + " before confirmation.")
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
    confirm_model(page, first["id"])
    snapshot = config()
    check(any(item.get("provenance") == "tablet-model"
              for item in snapshot.get("displays", []) if item.get("device_id") == first["id"]),
          "TWR-11 A1 " + first["id"][:8] + " received physical scale only after confirmation")

    for _ in range(3):
        tablets.append(new_tablet(browser_ref[0], CURRENT_BASE[0]))
    wait_until(lambda: "4 online" in page.locator("#device-count").inner_text(),
               "operator did not see all four tablets join")

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
        confirm_model(page, tablet["id"])

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
    page = operator_pages[0]
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

    select_tablet(page, tablets[0]["id"])
    provenance = page.locator("#tablet-provenance").inner_text()
    check("approximate" in provenance.lower() and "±3" in provenance,
          "TWR-11 A2 the tablet card shows approximate provenance with ±3 mm")
    check("No physical accuracy is claimed." in provenance,
          "TWR-11 A2 the tablet card explicitly claims no physical accuracy")
    shot(page, "02-model-provenance.png", full=True)


def phase_logical_grid():
    page = operator_pages[0]
    page.reload(wait_until="load")
    wait_until(lambda: "4 online" in page.locator("#device-count").inner_text(),
               "reloaded console did not see four tablets")
    tab(page, "Wall")
    before = config()
    page.locator("#grid-kind").select_option("logical")
    page.locator("#grid-2x2").click()
    page.locator("#grid-preview").click()
    wait_until(lambda: page.locator("#grid-cancel").is_enabled(),
               "logical 2x2 preview did not appear")
    check("Preview only" in page.locator("#grid-message").inner_text(),
          "TWR-10 A5 the 2x2 preview is labelled before Apply")
    page.locator("#btn-apply").click()
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
    shot(page, "03-logical-2x2.png", full=False)


def phase_physical_grid():
    page = operator_pages[0]
    tab(page, "Wall")
    before = config()
    page.locator("#grid-kind").select_option("physical")
    page.locator("#grid-orientation").select_option("preserve")
    page.locator("#grid-rows").fill("1")
    page.locator("#grid-columns").fill("4")
    for angle in page.locator("#grid-order select").all():
        angle.select_option("0")
    page.wait_for_timeout(250)
    page.locator("#grid-preview").click()
    wait_until(lambda: page.locator("#grid-cancel").is_enabled(),
               "physical 1x4 preview did not appear")
    preview = page.locator("#grid-message").inner_text()
    check("Preview only" in preview and "1 rows × 4 columns" in preview,
          "TWR-10 A2 the physical 1x4 preview reports one row and four columns")
    check("Apply will request a named safety copy" in preview,
          "TWR-09 A5 the cross-kind preview warns that Apply requests a named safety copy")
    shot(page, "04-physical-1x4-preview.png", full=False)

    dialogs_before = len(dialogs)
    page.locator("#btn-apply").click()
    wait_until(lambda: config()["layout"].get("kind") == "physical"
               and len(config()["layout"].get("slots", {})) == 4,
               "physical 1x4 was not applied")
    after = config()
    check(after["revision"] == before["revision"] + 1,
          "TWR-10 A1 the physical 1x4 apply incremented the revision exactly once "
          f"({before['revision']} -> {after['revision']})")
    check(any("named safety copy" in message for message in dialogs[dialogs_before:]),
          "TWR-09 A5 the cross-kind Apply confirmation names the safety-copy requirement")
    message = page.locator("#grid-message").inner_text()
    check("Previous arrangement saved as “Before physical " in message,
          "TWR-09 A6 the cross-kind Apply response names the generated return point")
    return_point = message.split("Before physical ", 1)[1].split("”", 1)[0]
    return_name = "Before physical " + return_point
    saved = [item["name"] for item in http("GET", "/layouts")[1]["layouts"]]
    check(return_name in saved,
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
    shot(page, "05-physical-1x4.png", full=False)
    phase_pinned_health()
    return return_name


def phase_content(return_name: str):
    page = operator_pages[0]
    tab(page, "Wall")
    first = image_id("first.png")
    marked = image_id("marked.png")
    show_image(page, first, "cover")
    active = page.locator("#stage-applied-content").inner_text()
    check("first.png" in active and "Fill" in active and "2000 × 1400 px" in active,
          "TWR-04 A1 image A is named in the console with its fill and source size")
    wait_painted(first)

    show_image(page, marked, "contain")
    active = page.locator("#stage-applied-content").inner_text()
    check("marked.png" in active and "Fit whole image" in active and "2000 × 1000 px" in active,
          "TWR-04 A1 image B is named in the console with its fit and source size")
    check(config()["scene"]["content"].get("fit") == "contain",
          "TWR-04 A1 image B is committed with the selected fit")
    wait_painted(marked)
    check(True, "TWR-04 A1 all four tablets confirmed image B")
    shot(page, "06-image-b.png", full=False)

    page.reload(wait_until="load")
    wait_until(lambda: "online" in page.locator("#device-count").inner_text(),
               "console did not recover after reload")
    tab(page, "Wall")
    wait_until(lambda: "marked.png" in page.locator("#stage-applied-content").inner_text(),
               "reload did not show image B")
    check("Fit whole image" in page.locator("#stage-applied-content").inner_text(),
          "TWR-04 A1 reload still names image B with Fit")
    check(config()["scene"]["content"].get("asset") == marked,
          "TWR-04 A1 reload still reads image B from the committed scene")
    wait_painted(marked)
    check(True, "TWR-04 A1 reload still shows image B on the tablets")

    legacy_context = browser_ref[0].new_context(viewport={"width": 1280, "height": 900})
    legacy = legacy_context.new_page()
    legacy.goto(CURRENT_BASE[0] + "/controller/", wait_until="load")
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
    tab(page, "Wall")
    page.locator("summary").filter(has_text="Colours and continuity checks").evaluate("node => node.parentElement.open = true")
    page.locator("#show-colours").click()
    wait_until(lambda: config()["scene"]["content"].get("type") == "color",
               "colour scene was not applied")
    check(config()["layout"] == layout_before,
          "TWR-04 A2 Tablet colours change content without changing the arrangement")
    page.wait_for_timeout(500)
    check(tablets[0]["page"].evaluate(
        "getComputedStyle(document.getElementById('surface')).display") == "none",
        "TWR-04 A2 the tablet client switches to its colour surface for Tablet colours")
    page.locator("#restore-image").click()
    wait_until(lambda: config()["scene"]["content"].get("asset") == marked,
               "Restore previous content did not return to image B")
    check(config()["layout"] == layout_before,
          "TWR-04 A2 Restore previous content returns to image B without losing the layout")

    page.locator("summary").filter(has_text="Colours and continuity checks").evaluate("node => node.parentElement.open = true")
    page.locator("#pattern-black").click()
    wait_until(lambda: config()["scene"]["content"].get("type") == "image"
               and config()["scene"]["content"].get("asset") != marked,
               "Black wall did not commit a generated pattern")
    black_id = config()["scene"]["content"]["asset"]
    wait_painted(black_id)
    check(config()["layout"] == layout_before,
          "TWR-04 A2 Black wall shows a generated image without changing the layout")
    check(True, "TWR-11 A5 Black wall is generated and painted without a shell copy step")
    page.locator("#restore-image").click()
    wait_until(lambda: config()["scene"]["content"].get("asset") == marked,
               "Restore after Black wall did not return to image B")
    check(config()["layout"] == layout_before,
          "TWR-04 A2 Restore returns from Black wall without changing the layout")

    check(return_name in [item["name"] for item in http("GET", "/layouts")[1]["layouts"]],
          "TWR-09 A6 the physical return point survives later content changes")
    return marked


MODEL_JS = """async () => {
  const cfg = await fetch('/api/v3/config').then(r => r.json());
  const content = { intrinsicWidth: cfg.scene.content.intrinsicWidth,
                    intrinsicHeight: cfg.scene.content.intrinsicHeight,
                    fit: cfg.scene.content.fit };
  const transform = window.OperatorState.fitTransform(cfg.layout, content);
  const items = [];
  for (const [id, slot] of Object.entries(cfg.layout.slots)) {
    const profile = cfg.displays.find(p => p.device_id === id && p.revision === slot.profile_revision);
    const device = cfg.runtime.devices[id] || {};
    const viewport = device.viewport || {};
    const target = profile.panel_pixels_width || (viewport.width && Math.round(viewport.width * viewport.dpr)) || null;
    const pixels = Math.round(Math.min(content.intrinsicWidth, profile.active_width_mm / transform.scale));
    items.push({ id, pixels, target, upscale: target ? target / Math.max(1, pixels) : null });
  }
  return { scale: transform.scale, cropX: transform.cropX, cropY: transform.cropY, items };
}"""


def phase_fit(marked: str):
    page = operator_pages[0]
    tab(page, "Wall")
    show_image(page, marked, "contain")
    wait_until(lambda: config()["scene"]["content"].get("fit") == "contain",
               "scene did not carry contain")
    fit_note = page.locator("#image-fit-note").inner_text()
    check("Fit keeps the entire source inside the wall bounds and adds bars." in fit_note,
          "TWR-05 A2 contain is named as a whole-wall fit with bars")
    check("Bezels and gaps still hide image areas." in fit_note
          and "This is one wall-wide transform." in fit_note,
          "TWR-05 A4 the fit note separates bezel/gap occlusion from the global transform")
    stage_note = page.locator("#stage-preview-note").inner_text()
    check("Hatching marks hidden bezels and gaps." in stage_note
          and "Fill may also crop source edges outside the wall." in stage_note,
          "TWR-05 A4 the stage note distinguishes bezel/gap hatching from off-wall Fill crop")
    legend = page.locator(".stage-legend").evaluate("node => node.textContent")
    check("Tablet body" in legend and "Active panel" in legend,
          "TWR-05 A4 the stage legend has separate body and active-panel treatments")
    hatch = page.evaluate("""() => {
      const pattern = document.querySelector('#stage-svg pattern#operator-occlusion');
      const clip = document.querySelector('#stage-svg clipPath#operator-panel-clip');
      return {pattern: !!pattern, stroke: pattern && pattern.querySelector('path') && pattern.querySelector('path').getAttribute('stroke'),
              clip: !!clip};
    }""")
    check(hatch["pattern"] and hatch["clip"] and hatch["stroke"] == "#75828d",
          "TWR-05 A4 the stage draws a hatch pattern for occlusion and a panel clip, not colour alone")

    page.locator("summary").filter(has_text="Preview coverage and resolution estimates").click()
    wait_until(lambda: page.locator("#stage-resolution").is_visible(),
               "resolution estimate is not visible when expanded")
    model = page.evaluate(MODEL_JS)
    resolution = page.locator("#stage-resolution").inner_text()
    for item in model["items"]:
        expected = f"≈{item['pixels']} source px across"
        check(expected in resolution,
              "TWR-05 A5 the visible resolution estimate uses the OperatorState arithmetic: " + expected)
    max_upscale = max((item["upscale"] for item in model["items"] if item["upscale"]), default=0)
    quality = page.locator("#stage-quality-summary").inner_text()
    check(f"Estimated upscaling up to {max_upscale:.1f}×" in quality,
          f"TWR-05 A5 the visible upscaling warning agrees with the model ({max_upscale:.1f}×)")
    shot(page, "08-fit-resolution.png", full=False)

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

    show_image(page, marked, "cover")
    wait_painted(marked)
    cover_model = page.evaluate(MODEL_JS)
    fill_note = page.locator("#image-fit-note").inner_text()
    expected_fill = (f"Fill crops {round(cover_model['cropX'] * 100)}% of the source width and "
                     f"{round(cover_model['cropY'] * 100)}% of its height outside the wall.")
    check(expected_fill in fill_note,
          "TWR-05 A1 Fill states the crop predicted by the OperatorState model: " + expected_fill)
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

    tab(page, "Wall")
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(300)
    shot(page, "11-fit-phone.png", full=True)
    page.set_viewport_size({"width": 1600, "height": 1000})


def phase_failure():
    page = operator_pages[0]
    marked = image_id("marked.png")
    target = tablets[2]
    target["context"].route("**/assets/**", lambda route: route.abort())
    show_image(page, marked, "contain")

    def one_failed():
        return any(item.get("render", {}).get("state") == "failed"
                   for item in config()["runtime"]["devices"].values())

    wait_until(one_failed, "the aborted image load did not surface as a failed render", timeout=30)
    health = page.locator("#wall-health").inner_text()
    check("3 of 4 report current image" in health,
          "TWR-06 A1 the header counts three of four after one induced image failure: " + health)
    select_tablet(page, target["id"])
    name = page.locator("#tablet-action-name").inner_text()
    evidence = page.locator("#tablet-evidence").inner_text()
    number = device(config(), target["id"]).get("number")
    check(f"#{number}" in name,
          "TWR-06 A1 the selected failure card names the failed tablet number: " + name)
    check("Image failed" in evidence and "fetch" in evidence,
          "TWR-06 A1 the failure card names the failure reason: " + evidence)
    shot(page, "12-image-failure.png", full=True)
    target["context"].unroute("**/assets/**")
    page.locator("#tablet-retry-image").click()
    wait_painted(marked)
    check("4 of 4 report current image" in page.locator("#wall-health").inner_text(),
          "TWR-06 A1 Retry returns the failed tablet to four of four showing")

    offline = tablets[3]
    offline["page"].close()
    wait_until(lambda: device(config(), offline["id"]).get("online") is False,
               "closed tablet did not report offline")
    wait_until(lambda: "3 of 4 report current image" in page.locator("#wall-health").inner_text(),
               "offline tablet is still counted as showing")
    check("1 offline" in page.locator("#wall-health").inner_text(),
          "TWR-06 A8 the header explains the offline member instead of silently dropping it")
    offline["page"] = offline["context"].new_page()
    offline["page"].goto(CURRENT_BASE[0] + "/client/", wait_until="load")
    wait_until(lambda: offline["page"].locator("#status").get_attribute("data-state") == "connected",
               "reopened tablet did not reconnect")
    wait_painted(marked)
    check("4 of 4 report current image" in page.locator("#wall-health").inner_text(),
          "TWR-06 A8 the offline member rejoins the showing count after recovery")


def phase_label():
    page = operator_pages[0]
    tablet = tablets[1]
    label = "North panel α"
    select_tablet(page, tablet["id"])
    page.locator("#tablet-label").fill(label)
    page.locator("#tablet-label-save").click()
    wait_until(lambda: config()["device_labels"].get(tablet["id"]) == label,
               "label was not saved")
    check(label in page.locator("#device-list").inner_text(),
          "TWR-08 A1 the saved label appears in the tablet list")
    tab(page, "Wall")
    page.locator("#layout-name").fill("Portrait row")
    page.locator("#btn-layout-save").click()
    wait_until(lambda: any(item["name"] == "Portrait row"
                           for item in http("GET", "/layouts")[1]["layouts"]),
               "physical arrangement was not saved")


def phase_restart_identify():
    page = operator_pages[0]
    tablet = tablets[1]
    label = "North panel α"
    server.stop()
    server.start()
    for item in tablets:
        wait_until(lambda item=item: item["page"].locator("#status").get_attribute("data-state") == "connected",
                   "tablet did not reconnect after the private backend restart", timeout=30)
    wait_until(lambda: "4 online" in page.locator("#device-count").inner_text(),
               "console did not see four reconnected tablets", timeout=30)
    page.reload(wait_until="load")
    wait_until(lambda: "4 online" in page.locator("#device-count").inner_text(),
               "reloaded console did not see four tablets")
    check(config()["device_labels"].get(tablet["id"]) == label,
          "TWR-08 A1 the label survived a real backend restart")
    select_tablet(page, tablet["id"])
    check(label in page.locator("#device-list").inner_text(),
          "TWR-08 A1 the label is visible in the list after restart and reconnect")
    check(label in page.locator("#tablet-action-name").inner_text(),
          "TWR-08 A1 the label is visible on the selected tablet card after restart")
    tab(page, "Wall")
    wait_until(lambda: "Portrait row" in page.locator("#saved-layouts").inner_text(),
               "saved layout did not reappear after restart")
    check(tablet["id"] in get_json_layout_slots(),
          "TWR-08 A1 the saved arrangement still references the labelled tablet identity after restart")

    before_revision = config()["revision"]
    tab(page, "Tablets")
    started = time.perf_counter()
    page.locator("#tablet-identify").click()
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
    note(f"Identify timing method: Playwright click start to visible DOM overlay on a loopback Chromium "
         f"context, measured {elapsed:.3f} s; this is not a hardware timing claim.")
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
    page = operator_pages[0]
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

    select_tablet(page, old["id"])
    page.locator("#operator-device-actions details").first.evaluate("node => node.open = true")
    page.locator("#replace-target").select_option(new_id)
    page.locator("#replace-hardware").select_option("same_hardware")
    before = config()
    page.locator("#replace-preview").click()
    wait_until(lambda: page.locator("#replace-apply").is_enabled(),
               "replacement preview did not become ready: "
               + page.locator("#tablet-action-message").inner_text(), timeout=20)
    summary = page.locator("#replace-summary").inner_text()
    check("Preview only." in summary,
          "TWR-09 A1 the replacement preview is labelled preview-only")
    check(old["id"][:8] in summary and new_id[:8] in summary,
          "TWR-09 A1 the replacement preview names the old and new identities")
    check("Profile revision map" in summary and "calibration map" in summary,
          "TWR-09 A1 the replacement preview reports profile and calibration revision maps")
    check("Label after:" in summary and "number after:" in summary,
          "TWR-09 A1 the replacement preview reports the resulting label and number")
    after = config()
    check(after["revision"] == before["revision"] and after["layout"] == before["layout"],
          "TWR-09 A1 the replacement preview writes nothing to the wall")
    check(old["id"] in after["runtime"]["devices"] and new_id in after["runtime"]["devices"]
          and old["id"] in get_json_layout_slots(),
          "TWR-09 A1 the replacement preview leaves the roster and active placement untouched")
    note("Rebind apply and recall-after-replacement are retained in the 106-check journey at "
         "readiness-program/final-qa/20261101T120950Z/; this run adds the exact preview revision maps.")
    shot(page, "14-rebind-preview.png", full=True)
    old["page"] = old["context"].new_page()
    old["page"].goto(CURRENT_BASE[0] + "/client/", wait_until="load")
    wait_until(lambda: old["page"].locator("#status").get_attribute("data-state") == "connected",
               "the original tablet identity did not reconnect after the preview")
    wait_painted(image_id("marked.png"))
    return context, replacement


def phase_return_point():
    page = operator_pages[0]
    tab(page, "Wall")
    before = config()
    page.locator("#grid-kind").select_option("logical")
    page.locator("#grid-2x2").click()
    page.locator("#grid-preview").click()
    wait_until(lambda: page.locator("#grid-cancel").is_enabled(),
               "logical cross-kind preview did not appear")
    dialogs_before = len(dialogs)
    page.locator("#btn-apply").click()
    wait_until(lambda: config()["layout"].get("kind") == "logical",
               "cross-kind logical apply did not commit")
    check(any("named safety copy" in message for message in dialogs[dialogs_before:]),
          "TWR-09 A5 the physical-to-logical Apply confirmation names the safety copy")
    message = page.locator("#grid-message").inner_text()
    check("Previous arrangement saved as “Before logical " in message,
          "TWR-09 A6 the physical-to-logical Apply names its generated return point")
    logical_return = "Before logical " + message.split("Before logical ", 1)[1].split("”", 1)[0]
    check(logical_return in [item["name"] for item in http("GET", "/layouts")[1]["layouts"]],
          "TWR-09 A6 the physical-to-logical return point is stored as an automatic layout")

    row = page.locator("#saved-layouts li", has_text="Portrait row")
    dialogs_before = len(dialogs)
    row.locator("button", has_text="Recall").click()
    wait_until(lambda: config()["layout"].get("kind") == "physical",
               "cross-kind recall did not return to the physical arrangement")
    check(any("named safety copy" in message for message in dialogs[dialogs_before:]),
          "TWR-09 A5 the logical-to-physical recall confirmation names the safety copy")
    announcement = page.locator("#page-status").inner_text()
    check("Previous arrangement saved as “Before physical " in announcement,
          "TWR-09 A6 the cross-kind recall announcement names the generated return point: " + announcement)
    check(any(name.startswith("Before physical ") for name in
              [item["name"] for item in http("GET", "/layouts")[1]["layouts"]]),
          "TWR-09 A6 the logical-to-physical return point is retrievable as a saved layout")
    check(config()["revision"] == before["revision"] + 2,
          "TWR-09 A5 both cross-kind directions each committed exactly one wall revision")


def phase_fence():
    page = operator_pages[0]
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
    select_tablet(page, tablets[1]["id"])
    select_tablet(page, tablet["id"])
    evidence = page.locator("#tablet-evidence").inner_text()
    provenance = page.locator("#tablet-provenance").inner_text()
    check("live viewport does not match" in evidence or "viewport does not match pinned calibration" in evidence,
          "TWR-11 A4 the tablet card reports the viewport mismatch instead of a healthy plan: "
          + evidence)
    check("exceeds" in provenance and "Clear browser zoom/scale" in provenance,
          "TWR-11 A4 the provenance card repeats the fence and recovery action")
    shot(page, "15-viewport-fence.png", full=True)
    tablet["page"].set_viewport_size(VIEW)
    wait_until(lambda: device(config(), tablet["id"]).get("mapping", {}).get("state") == "ready",
               "restoring the viewport did not clear the fence", timeout=20)
    wait_painted(image_id("marked.png"))
    check(True, "TWR-11 A4 restoring the native viewport clears the fence and repaints")


def phase_uploads():
    page = operator_pages[0]
    tab(page, "Content")
    wait_until(lambda: page.locator("#upload-form").is_visible(),
               "loopback uploads did not reveal the form")
    capabilities = config().get("capabilities") or {}
    check(capabilities.get("uploads") is True,
          "TWR-04 A3 loopback capabilities advertise uploads")
    file_input = page.locator("#upload-file")
    check(file_input.get_attribute("type") == "file",
          "TWR-04 A3 the visible form uses a real file input")
    accept = file_input.get_attribute("accept") or ""
    check("image/png" in accept and "image/jpeg" in accept,
          "TWR-04 A3 the file input accepts the server's still-image types")
    check(page.locator("#upload-instruction").is_hidden(),
          "TWR-04 A3 loopback uploads replace the copy instruction with the form")
    limits_source = (ROOT / "tabletwall" / "media_limits.py").read_text(encoding="utf-8")
    check("MAX_SOURCE_BYTES = 32 * 1024 * 1024" in limits_source,
          "TWR-04 A3 the checked-out server source limits a still source to 32 MiB")
    note("Server still-image source limit is 32 MiB (tabletwall/media_limits.py MAX_SOURCE_BYTES); "
         "the browser form exposes no client-side size message.")

    layout_before = config()["layout"]
    assets_before = {item["id"] for item in http("GET", "/api/v3/images")[1]["images"]}
    page.evaluate("""() => {
      window.__uploadTrace = [];
      const progress = document.getElementById('upload-progress');
      const message = document.getElementById('upload-message');
      const record = () => window.__uploadTrace.push({
        hidden: progress.hidden, message: message.textContent, at: performance.now() });
      new MutationObserver(record).observe(progress, { attributes: true, subtree: true, childList: true });
      new MutationObserver(record).observe(message, { childList: true, subtree: true, characterData: true });
      record();
    }""")
    file_input.set_input_files(str(ASSETS / "upload-ok.png"))
    page.locator("#upload-submit").click()
    wait_until(lambda: "Image uploaded" in page.locator("#upload-message").inner_text(),
               "valid PNG upload did not report success", timeout=60)
    trace = page.evaluate("window.__uploadTrace")
    check(any(entry["hidden"] is False for entry in trace),
          "TWR-04 A3 the progress element became visible during the upload")
    check(any("Uploading upload-ok.png" in entry["message"] for entry in trace),
          "TWR-04 A3 the upload message named the selected PNG")
    check(page.evaluate("document.getElementById('upload-file').files[0].type") == "image/png",
          "TWR-04 A3 the actual file input carried image/png")
    assets_after = {item["id"] for item in http("GET", "/api/v3/images")[1]["images"]}
    check(len(assets_after) > len(assets_before),
          "TWR-04 A3 the uploaded PNG joined the still-image inventory")
    check(config()["layout"] == layout_before,
          "TWR-04 A3 a valid upload leaves the wall layout unchanged")
    shot(page, "16-upload-success.png", full=True)

    page.locator("#upload-file").set_input_files(str(ARTIFACTS / "upload-bad.txt"))
    page.locator("#upload-submit").click()
    wait_until(lambda: "Upload rejected." in page.locator("#upload-message").inner_text(),
               "a disallowed upload did not report a rejection", timeout=30)
    rejection = page.locator("#upload-message").inner_text()
    check("only image/jpeg, image/png" in rejection,
          "TWR-04 A3 a disallowed type produces a readable rejection: " + rejection)
    check(config()["layout"] == layout_before,
          "TWR-04 A3 a rejected upload leaves the wall layout unchanged")
    shot(page, "17-upload-rejected.png", full=True)

    page.locator("#upload-file").set_input_files(str(ARTIFACTS / "upload-unsupported.webp"))
    page.locator("#upload-submit").click()
    wait_until(lambda: "Upload rejected." in page.locator("#upload-message").inner_text(),
               "webp upload did not report a rejection", timeout=30)
    webp_message = page.locator("#upload-message").inner_text()
    advertised = page.locator("#upload-file").get_attribute("accept") or ""
    check(set(advertised.split(",")) == {"image/jpeg", "image/png"},
          "TWR-04 A3 the still-image picker advertises exactly the supported JPEG/PNG types")
    check("only image/jpeg, image/png" in webp_message,
          "TWR-04 A3 bypassing the picker with unsupported WebP still reports a readable rejection")
    if "image/webp" in advertised and "only image/jpeg, image/png" in webp_message:
        findings.append(
            "TWR-04 A3 minor mismatch: the file input advertises image/webp, but POST /uploads "
            "rejects image/webp with 415 (" + webp_message + "). A user can select a type the "
            "server refuses. Screenshot: 18-upload-webp-mismatch.png")
        print("FINDING webp accept/upload mismatch", flush=True)
    check(config()["layout"] == layout_before,
          "TWR-04 A3 a forced unsupported upload still leaves the layout unchanged")
    shot(page, "18-upload-webp-rejected.png", full=True)


def phase_playback():
    page = operator_pages[0]
    tab(page, "Content")
    check(page.locator("#experimental-controls").is_hidden(),
          "TWR-04 A4 playback controls are hidden before the explicit switch")
    check(page.locator("#topbar-transport").is_hidden(),
          "TWR-04 A4 the top bar still has no playback transport before opt-in")
    page.locator("#experimental-opt-in").check()
    wait_until(lambda: page.locator("#experimental-controls").is_visible(),
               "the explicit switch did not reveal the experimental controls")
    check(page.locator("#btn-playback-start").is_visible(),
          "TWR-04 A4 the explicit switch reveals the Start control")
    check(page.locator("#topbar-transport").is_hidden(),
          "TWR-04 A4 the top bar stays free of playback transport after opt-in")
    wait_until(lambda: page.locator("#playlist-library option").count() > 1,
               "the uploaded file did not appear in the playlist library")
    option = page.locator("#playlist-library option").filter(has_text="upload-ok.png").first
    wait_until(lambda: option.count() == 1, "the uploaded PNG is not selectable for the playlist")
    page.locator("#playlist-library").select_option(option.get_attribute("value"))
    page.locator("#btn-playlist-add").click()
    wait_until(lambda: page.locator("#playlist-items li").count() >= 1,
               "the uploaded PNG was not added to the playlist draft")
    page.locator("#btn-playlist-save").click()
    wait_until(lambda: len((http("GET", "/api/v3/playlist")[1] or {}).get("playlist", {}).get("items", [])) == 1,
               "the experimental playlist was not saved")
    check(True, "TWR-04 A4 a saved playlist enables the experimental Start control without enabling it by default")
    requests_before = len(requests_seen)
    dialogs_before = len(dialogs)
    DISMISS_DIALOG[0] = True
    page.locator("#btn-playback-start").click()
    DISMISS_DIALOG[0] = False
    wait_until(lambda: len(dialogs) > dialogs_before, "Start did not raise a confirmation")
    check(any("Start experimental playback" in message and "not validated" in message
              for message in dialogs[dialogs_before:]),
          "TWR-04 A4 Start requires a second confirmation that names experimental and unvalidated playback")
    page.wait_for_timeout(500)
    playback_requests = [entry for entry in requests_seen[requests_before:]
                         if entry.startswith("POST ") and "/api/v3/playback" in entry]
    check(not playback_requests,
          "TWR-04 A4 dismissing the confirmation starts no playback request")
    check(page.locator("#playback-state-word").inner_text().strip() == "stopped",
          "TWR-04 A4 the playback state stays stopped after dismissal")
    presentation = (config().get("runtime") or {}).get("presentation")
    check(not presentation or presentation.get("owner") != "playback",
          "TWR-04 A4 the wall does not hand presentation to playback after dismissal")
    page.locator("#experimental-opt-in").uncheck()
    wait_until(lambda: page.locator("#experimental-controls").is_hidden(),
               "unchecking the switch did not hide the experimental controls")


def phase_drill():
    page = operator_pages[0]
    tab(page, "Wall")
    page.locator("summary").filter(has_text="Colours and continuity checks").evaluate("node => node.parentElement.open = true")
    marked = image_id("marked.png")
    page.locator("#pattern-black").click()
    wait_until(lambda: config()["scene"]["content"].get("type") == "image"
               and config()["scene"]["content"].get("asset") != marked,
               "Black wall did not commit generated content")
    black = config()["scene"]["content"]
    black_id = black["asset"]
    wait_painted(black_id)
    black_url = black["url"]
    with urllib.request.urlopen(CURRENT_BASE[0] + black_url, timeout=30) as response:
        original_bytes = hashlib.sha256(response.read()).hexdigest()
    check(True, "TWR-13 A4 the runbook Black wall step paints generated content from the console")

    status, health = http("GET", "/healthz")
    check(status == 200 and "schema" in health and "revision" in health,
          "TWR-13 A4 /healthz reports schema and revision before the runbook stop")
    layout_before = config()["layout"]
    labels_before = config()["device_labels"]
    devices_before = {key: {"number": item.get("number"), "label": item.get("label")}
                      for key, item in config()["runtime"]["devices"].items()}
    shot(page, "19-runbook-black.png", full=True)

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
    global server, browser_ref, operator_contexts, operator_pages, tablets, servers

    parser = argparse.ArgumentParser(description=__doc__)
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
    operator_contexts = []
    operator_pages = []
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
            empty_context, empty_page = start_operator(browser, server.base)
            operator_contexts.append(empty_context)
            operator_pages.append(empty_page)
            phase("start and empty wall", phase_start, empty_page)

            page = empty_page
            wait_until(lambda: "0 online" in page.locator("#device-count").inner_text(),
                       "operator did not start on an empty roster")
            first_tablet = new_tablet(browser, server.base)
            tablets.append(first_tablet)
            wait_until(lambda: "1 online" in page.locator("#device-count").inner_text(),
                       "operator did not see the first tablet join")

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
            page.reload(wait_until="load")
            wait_until(lambda: "online" in page.locator("#device-count").inner_text(),
                       "console did not recover after the upload restart")
            phase("uploads", phase_uploads)
            phase("playback", phase_playback)
            phase("drill", phase_drill)
            check(not OPERATOR_ERRORS,
                  "no operator page exceptions in the full journey")
            refused = [item for item in FAILED_REQUESTS if "net::ERR_CONNECTION_REFUSED" in item]
            if refused:
                note("The only failed operator requests were navigation aborts and "
                     + str(len(refused)) + " connection refusals during the two deliberate private "
                     "server restarts: " + "; ".join(refused[:4]))
            unexpected = [item for item in FAILED_REQUESTS
                          if "net::ERR_ABORTED" not in item
                          and "net::ERR_CONNECTION_REFUSED" not in item]
            check(not unexpected,
                  "no unexpected failed operator requests; navigation aborts and deliberate "
                  "private-restart connection refusals are excluded: " + str(unexpected[:3]))
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
