"""Deterministic restoration acceptance driver for the supported operator routes.

This driver never changes application behavior. It starts the selected source
tree as a private app server with explicit data roots, drives the shipped
controller and client pages, and records source, fixture, viewport, request,
console, assertion and cleanup evidence.

Every registry scenario has a durable body. A feature that has not landed yet
is gated by an explicit missing-hook failure that names the owning task; it is
never a skipped or synthetic pass. Baseline scenarios may intentionally fail
their predicted assertion on clean HEAD; that failure is reported with the
observed value.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[2]
TASK_ID = "M0-02"
APPLICATION_PATHS = ("main.py", "frontend", "tabletwall", "deploy")
DRIVER_PATHS = (
    "simulator/browser/restoration_acceptance.py",
    "simulator/browser/run.py",
    "simulator/browser/evidence.py",
)
TEST_PATH = "tests/test_restoration_driver.py"

# Registry order is part of the frozen CLI. Implemented entries exist now;
# later entries stay explicitly incomplete until their owning milestone.
SCENARIO_ENTRIES = (
    {
        "name": "gallery-focus",
        "status": "implemented",
        "owner": "M0-02",
        "reason": None,
        "known_baseline_failure": "Observed HEAD treats every arrow as one step and "
        "uses preventScroll, so a focused target can leave the inner scroll viewport.",
    },
    {
        "name": "recovery-sheet",
        "status": "implemented",
        "owner": "M0-02",
        "reason": None,
        "known_baseline_failure": "Observed HEAD's issue action selects and opens the "
        "Tablets task without opening the compact device sheet.",
    },
    {
        "name": "library-composer",
        "status": "implemented",
        "owner": "M0-02",
        "reason": None,
        "known_baseline_failure": "Observed HEAD has no bounded desktop library or "
        "phone wall-first chooser layout, so long libraries can displace action context.",
    },
    {
        "name": "scene-paint",
        "status": "implemented",
        "owner": "M0-02",
        "reason": None,
        "known_baseline_failure": "Observed HEAD's client acknowledges displayed paint "
        "only for image content, so colour and logical calibration stay unconfirmed.",
    },
    {
        "name": "fit-feedback",
        "status": "implemented",
        "owner": "M6-00",
        "reason": None,
        "known_baseline_failure": "The M5-03 fit-feedback slots are absent until that candidate is "
        "integrated. The scenario fails explicitly with a missing-hook diagnostic.",
    },
    {
        "name": "geometry-tools",
        "status": "implemented",
        "owner": "M6-00",
        "reason": None,
        "known_baseline_failure": None,
    },
    {
        "name": "fleet-power",
        "status": "implemented",
        "owner": "M6-00",
        "reason": None,
        "known_baseline_failure": "The M6-02 power readiness hook is absent until that candidate is "
        "integrated. The scenario fails explicitly with a missing-hook diagnostic.",
    },
    {
        "name": "historical-forms",
        "status": "implemented",
        "owner": "M6-00",
        "reason": None,
        "known_baseline_failure": None,
    },
    {
        "name": "historical-membership",
        "status": "implemented",
        "owner": "M6-00",
        "reason": None,
        "known_baseline_failure": None,
    },
    {
        "name": "historical-uncertainty",
        "status": "implemented",
        "owner": "M6-00",
        "reason": None,
        "known_baseline_failure": None,
    },
)
SCENARIOS = {entry["name"]: entry for entry in SCENARIO_ENTRIES}
IMPLEMENTED = tuple(
    entry["name"] for entry in SCENARIO_ENTRIES if entry["status"] == "implemented"
)
INCOMPLETE = tuple(
    entry["name"] for entry in SCENARIO_ENTRIES if entry["status"] == "incomplete"
)
FIXTURE_COUNTS = (0, 1, 8, 24)
FIXTURE_ASPECTS = ((1600, 1000), (1000, 1600), (2400, 1000))
SCENARIO_FIXTURES = {
    "gallery-focus": 24,
    "recovery-sheet": 1,
    "library-composer": 24,
    "scene-paint": 1,
    "fit-feedback": 8,
    "geometry-tools": 8,
    "fleet-power": 1,
    "historical-forms": 1,
    "historical-membership": 0,
    "historical-uncertainty": 1,
}
# These are the additive DOM hooks owned by tasks that may land after this
# authoring task. A missing hook is an explicit failure with the owning task
# named, never a skipped or synthetic pass.
SCENARIO_HOOKS = {
    "fit-feedback": {
        "owner": "M5-03",
        "selectors": ("#fit-feedback", "#fit-summary", "#fit-applied", "#crop-bars"),
    },
    "fleet-power": {
        "owner": "M6-02",
        "expressions": (
            "() => typeof window.OperatorStage?.powerReadiness === 'function'",
            "() => !!document.getElementById('tablet-evidence')",
        ),
    },
}
CLIENT_SPECS = (
    # Unequal viewports and DPRs. Orientation is overridden in the page so the
    # physical calibration can pin a real, distinct signature per client.
    {"name": "landscape-a", "width": 1280, "height": 800, "dpr": 1.0, "orientation": 0, "mobile": False},
    {"name": "portrait-b", "width": 800, "height": 1280, "dpr": 1.25, "orientation": 0, "mobile": True},
    {"name": "wide-c", "width": 1024, "height": 640, "dpr": 1.5, "orientation": 90, "mobile": False},
    {"name": "compact-d", "width": 390, "height": 844, "dpr": 2.0, "orientation": 0, "mobile": True},
)
CLIENT_COLOURS = ("#7c2d12", "#14532d", "#1e3a8a", "#4c1d95")
TASK_VALUES = {"Images": "content", "Tablets": "tablet", "Arrange": "show", "Settings": "system"}
FIXTURE_COVERAGE_NOTE = (
    "Scenario servers now serve 0 (historical-membership), 1 (recovery-sheet, "
    "scene-paint, fleet-power, historical-forms, historical-uncertainty), 8 "
    "(fit-feedback, geometry-tools) and 24 (gallery-focus, library-composer) "
    "deterministic assets. Asset aspect and fit coverage is exercised at 8; a "
    "different library count is not a new visual claim."
)
LIMITATIONS = [
    "Software browser evidence only. No physical tablet, optical seam, sleep/wake, "
    "native screen reader, native browser zoom, network ingress or hardware certification.",
    "The client pages are real shipped pages. Protocol-only, synthetic-pointer or "
    "mutated state copies are labelled state_rule_probe or simulation and are never "
    "counted as physical or painted acceptance evidence.",
    "A missing feature hook fails explicitly with its owning task named. It is never "
    "a skipped or synthetic pass.",
    "Final assembled execution remains M6-04/M7-04. These durable bodies replace "
    "the former incomplete stubs; they do not accept an unrun journey.",
    FIXTURE_COVERAGE_NOTE,
]


# ---------------------------------------------------------------------------
# CLI and source identity
# ---------------------------------------------------------------------------


def resolve_source_root(value: Path | str | None) -> Path:
    """Resolve the read-only source tree served by the private app server."""
    root = Path(value).expanduser().resolve() if value is not None else REPO.resolve()
    if not (root / "main.py").is_file():
        raise ValueError(f"--source-root must contain main.py: {root}")
    return root


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def new_artifacts(
    path: Path | str,
    source_root: Path,
    driver_root: Path = REPO,
    *,
    create: bool = True,
) -> Path:
    """Validate a new artifacts directory outside both repositories.

    With ``create=False`` the destination must still not exist, but the caller
    owns creation (a single scenario creates its own target in run_scenario).
    """
    destination = Path(path).expanduser().resolve()
    for root in (source_root.resolve(), driver_root.resolve()):
        if _inside(destination, root):
            raise ValueError("artifacts must be outside the repository and source root")
    if create:
        destination.mkdir(parents=True, exist_ok=False)
    elif destination.exists():
        raise FileExistsError(f"artifacts directory already exists: {destination}")
    return destination


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


def _git(root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _tree_hashes(root: Path, names: tuple[str, ...]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name in names:
        candidate = root / name
        if candidate.is_file():
            hashes[name] = digest(candidate)
            continue
        if not candidate.is_dir():
            continue
        for child in sorted(candidate.rglob("*")):
            if not child.is_file():
                continue
            if "__pycache__" in child.parts or child.suffix in (".pyc", ".pyo"):
                continue
            relative = child.relative_to(root).as_posix()
            hashes[relative] = digest(child)
    return hashes


def _identity(hashes: dict[str, str]) -> str:
    return _sha256_bytes(
        json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
    )


def application_identity(source_root: Path) -> dict[str, Any]:
    """Hash only the application source selected by --source-root."""
    root = source_root.resolve()
    hashes = _tree_hashes(root, APPLICATION_PATHS)
    app_hashes = {
        name: value
        for name, value in hashes.items()
        if name == "main.py"
        or name.startswith(("frontend/", "tabletwall/", "deploy/"))
    }
    head = _git(root, "rev-parse", "HEAD")
    return {
        "source_root": str(root),
        "head": head,
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
        "dirty_status": _git(root, "status", "--porcelain=v1"),
        "git_repository": head is not None,
        "file_count": len(app_hashes),
        "application_sha256": _identity(app_hashes),
        "application_hashes": app_hashes,
    }


def driver_identity(driver_root: Path = REPO) -> dict[str, Any]:
    """Hash the accepted driver, never the selected application source."""
    root = driver_root.resolve()
    hashes = {
        name: digest(root / name)
        for name in DRIVER_PATHS
        if (root / name).is_file()
    }
    test_hash = digest(root / TEST_PATH) if (root / TEST_PATH).is_file() else None
    return {
        "driver_root": str(root),
        "head": _git(root, "rev-parse", "HEAD"),
        "dirty_status": _git(root, "status", "--porcelain=v1"),
        "driver_sha256": _identity(hashes),
        "driver_hashes": hashes,
        "test_sha256": test_hash,
    }


# ---------------------------------------------------------------------------
# Deterministic fixtures
# ---------------------------------------------------------------------------


def _fixture_name(group: int, index: int, seed: str, suffix: str) -> str:
    region = "north-gallery" if index % 3 == 0 else "south-gallery"
    return (
        f"{group:02d}-{index:02d}-{region}-east-wall-loading-bay-panorama-"
        f"approved-survey-2026-11-07-{seed[:12]}{suffix}"
    )


def _write_fixture(path: Path, width: int, height: int, seed: str) -> tuple[int, int, int]:
    seed_bytes = bytes.fromhex(seed)
    palette = [
        tuple(32 + value % 192 for value in seed_bytes[offset : offset + 3])
        for offset in (0, 3, 6, 9)
    ]
    image = Image.new("RGB", (width, height), palette[0])
    draw = ImageDraw.Draw(image)
    columns = 10
    rows = max(4, round(height / max(1, width / columns)))
    cell_w = max(1, width // columns)
    cell_h = max(1, height // rows)
    for row in range(rows):
        for column in range(columns):
            value = hashlib.sha256(f"{seed}:{row}:{column}".encode()).digest()
            colour = tuple(24 + byte % 200 for byte in value[:3])
            x0, y0 = column * cell_w, row * cell_h
            draw.rectangle(
                (x0, y0, min(width - 1, x0 + cell_w - 1), min(height - 1, y0 + cell_h - 1)),
                fill=colour,
            )
    centre = (width // 2, height // 2)
    radius = max(8, min(width, height) // 10)
    draw.rectangle(
        (centre[0] - radius, centre[1] - radius, centre[0] + radius, centre[1] + radius),
        fill=palette[1],
    )
    if path.suffix.lower() in (".jpg", ".jpeg"):
        image.save(path, format="JPEG", quality=92)
    else:
        image.save(path, format="PNG")
    return palette[1]


def generate_fixtures(directory: Path) -> list[dict[str, Any]]:
    """Write deterministic 0/1/8/24 libraries and return their hashes."""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    groups: list[dict[str, Any]] = []
    for group in FIXTURE_COUNTS:
        group_dir = root / f"library-{group}"
        group_dir.mkdir(parents=True, exist_ok=True)
        files: list[dict[str, Any]] = []
        for index in range(group):
            seed = hashlib.sha256(
                f"tablet-wall-restoration/{TASK_ID}/{group}/{index}".encode()
            ).hexdigest()
            width, height = FIXTURE_ASPECTS[index % len(FIXTURE_ASPECTS)]
            suffix = ".jpg" if index % 4 == 3 else ".png"
            name = _fixture_name(group, index, seed, suffix)
            path = group_dir / name
            center = _write_fixture(path, width, height, seed)
            files.append(
                {
                    "name": name,
                    "path": str(path),
                    "relative_path": path.relative_to(root).as_posix(),
                    "sha256": digest(path),
                    "bytes": path.stat().st_size,
                    "width": width,
                    "height": height,
                    "format": "jpeg" if suffix == ".jpg" else "png",
                    "center_rgb": list(center),
                }
            )
        groups.append({"count": group, "directory": str(group_dir), "files": files})
    return groups


def prepare_assets(fixtures_root: Path, assets_root: Path, count: int) -> list[dict[str, Any]]:
    """Copy one deterministic fixture group into the private asset root."""
    source = Path(fixtures_root) / f"library-{count}"
    target = Path(assets_root)
    target.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    for path in sorted(source.glob("*")):
        if not path.is_file():
            continue
        destination = target / path.name
        shutil.copyfile(path, destination)
        with Image.open(destination) as image:
            width, height = image.size
        copied.append(
            {
                "name": destination.name,
                "path": str(destination),
                "sha256": digest(destination),
                "width": width,
                "height": height,
            }
        )
    return copied


# ---------------------------------------------------------------------------
# Private environment and server launch
# ---------------------------------------------------------------------------


def restoration_environment(data_root: Path, port: int, uploads: bool = True) -> dict[str, str]:
    """Build a complete private environment without mutating os.environ."""
    root = Path(data_root)
    for name in ("assets", "media", "backups", "tmp"):
        (root / name).mkdir(parents=True, exist_ok=True)
    xdg_root = root / "xdg"
    private_home = xdg_root / "home"
    private_home.mkdir(parents=True, exist_ok=True, mode=0o700)
    xdg_paths: dict[str, str] = {"HOME": str(private_home)}
    for key, name in (
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_RUNTIME_DIR", "run"),
    ):
        directory = xdg_root / name
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        xdg_paths[key] = str(directory)
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("TABLET_WALL_", "WALL_"))
        and key not in {"TABLET_ORIGIN", "AUTH_TOKEN", "OPERATOR_CREDENTIAL"}
    }
    base = f"http://127.0.0.1:{port}"
    environment.update(
        {
            "TABLET_WALL_DB": str(root / "wall.db"),
            "TABLET_WALL_ASSET_DIR": str(root / "assets"),
            "TABLET_WALL_MEDIA_DIR": str(root / "media"),
            "TABLET_WALL_BACKUP_DIR": str(root / "backups"),
            "TABLET_WALL_UPLOAD_MODE": "loopback" if uploads else "disabled",
            "TABLET_WALL_OPERATOR_ORIGIN": base,
            "TABLET_WALL_TABLET_ORIGIN": base,
            "TMPDIR": str(root / "tmp"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    environment.update(xdg_paths)
    return environment


def launch_server(
    source_root: Path,
    environment: dict[str, str],
    log_path: Path,
    listener: socket.socket,
) -> tuple[subprocess.Popen[bytes], Any, list[str]]:
    """Launch the selected source tree with an explicit cwd and bound socket."""
    argv = [
        sys.executable,
        "-m",
        "uvicorn",
        "main:app",
        "--fd",
        str(listener.fileno()),
        "--workers",
        "1",
        "--no-access-log",
    ]
    log = Path(log_path).open("x")
    process = subprocess.Popen(
        argv,
        cwd=str(Path(source_root).resolve()),
        env=environment,
        pass_fds=(listener.fileno(),),
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return process, log, argv


def _tail(path: Path, limit: int = 2000) -> str:
    try:
        return Path(path).read_text(errors="replace")[-limit:]
    except OSError:
        return ""


def wait_ready(base: str, process: subprocess.Popen[bytes], log_path: Path, timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while True:
        if process.poll() is not None:
            raise RuntimeError(
                f"private server exited before readiness; see {log_path}\n{_tail(log_path)}"
            )
        try:
            with urllib.request.urlopen(base + "/healthz", timeout=0.5) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError(f"private server readiness deadline exceeded; see {log_path}")
        time.sleep(0.1)


def process_cwd(pid: int | None) -> str | None:
    if pid is None:
        return None
    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        return None


def stop_owned_server(process: subprocess.Popen[bytes] | None) -> dict[str, Any]:
    if process is None:
        return {"pid": None, "exit": None, "alive": False}
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
    return {"pid": process.pid, "exit": process.returncode, "alive": process.poll() is None}


def wait_until(
    page: Any,
    expression: str,
    timeout: float = 10,
    arg: Any = None,
    interval: float = 0.1,
) -> bool:
    """CSP-safe bounded polling.

    ``page.evaluate`` runs through the debugger and is allowed under the
    application's ``script-src 'self'``; string ``page.wait_for_function``
    polling uses ``eval`` and is blocked.
    """
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while True:
        try:
            if page.evaluate(expression, arg):
                return True
        except Exception as error:
            last_error = error
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"bounded wait expired after {timeout}s: {expression} ({last_error!r})"
            )
        page.wait_for_timeout(interval * 1000)


def launch_browser(playwright: Any, environment: dict[str, str]) -> Any:
    """Use Playwright's tested default headless browser, not a forced executable."""
    return playwright.chromium.launch(headless=True, env=environment)


# ---------------------------------------------------------------------------
# API and report helpers
# ---------------------------------------------------------------------------


def cleanup_ok(cleanup: dict[str, Any]) -> bool:
    if cleanup.get("errors"):
        return False
    server = cleanup.get("server") or {}
    if server.get("pid") is not None and (server.get("alive") or server.get("exit") is None):
        return False
    return (
        cleanup.get("browser_disconnected") is True
        and cleanup.get("port_closed") is True
        and cleanup.get("private_data_removed") is True
    )


def scenario_pass(
    checks: list[dict[str, Any]], cleanup: dict[str, Any], interrupted: bool = False
) -> bool:
    """A scenario passes only with assertions, no failures and complete cleanup."""
    return (
        bool(checks)
        and not interrupted
        and all(row.get("pass") is True for row in checks)
        and cleanup_ok(cleanup)
    )


def incomplete_report(name: str) -> dict[str, Any]:
    entry = SCENARIOS[name]
    return {
        "scenario": name,
        "status": "incomplete",
        "pass": False,
        "checks": 0,
        "failures": [
            {
                "name": "scenario is explicitly incomplete",
                "pass": False,
                "classification": "explicitly_incomplete",
                "reason": entry["reason"],
                "owner": entry["owner"],
            }
        ],
        "owner": entry["owner"],
        "reason": entry["reason"],
        "artifacts": None,
    }


class Api:
    def __init__(self, base: str) -> None:
        self.base = base
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        if_match: str | None = None,
    ) -> tuple[int, Any]:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Origin": self.base}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if if_match:
            headers["If-Match"] = if_match
        request = urllib.request.Request(
            self.base + path, data=data, headers=headers, method=method
        )
        status = 0
        payload: Any = None
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                status = response.status
                raw = response.read()
        except urllib.error.HTTPError as error:
            status = error.code
            raw = error.read()
        except OSError as error:
            self.calls.append({"method": method, "path": path, "status": None, "error": str(error)})
            raise
        try:
            payload = json.loads(raw) if raw else None
        except ValueError:
            payload = raw.decode(errors="replace")
        self.calls.append(
            {
                "method": method,
                "path": path,
                "status": status,
                "if_match": if_match,
                "body": body,
            }
        )
        return status, payload


def _write_json(path: Path, value: Any) -> None:
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n")


# ---------------------------------------------------------------------------
# Rig
# ---------------------------------------------------------------------------


class Rig:
    def __init__(self, out: Path, scenario: str, source_root: Path, identity: dict[str, Any]) -> None:
        self.out = Path(out)
        self.scenario = scenario
        self.source_root = Path(source_root)
        self.identity = identity
        self.results: list[dict[str, Any]] = []
        self.requests: list[dict[str, Any]] = []
        self.console: list[dict[str, Any]] = []
        self.network: list[dict[str, Any]] = []
        self.page_errors: list[dict[str, Any]] = []
        self.clients: list[dict[str, Any]] = []
        self.contexts: list[Any] = []
        self.pages: dict[str, Any] = {}
        self.server = None
        self.server_log = None
        self.listener = None
        self.browser = None
        self.page = None
        self.private = None
        self.port = None
        self.base = None
        self.env: dict[str, str] = {}
        self.argv: list[str] = []
        self.api_client: Api | None = None
        self.api_calls: list[dict[str, Any]] = []
        self.server_cwd: str | None = None
        self.fixtures: list[dict[str, Any]] = []
        self.assets: list[dict[str, Any]] = []
        self.browser_version: str | None = None
        self.interrupted = False

    # -- environment -------------------------------------------------------

    def setup(self, playwright: Any) -> None:
        self.private = Path(
            tempfile.mkdtemp(prefix=f"tablet-wall-restoration-{self.scenario}-")
        )
        data = self.private / "data"
        self.fixtures = generate_fixtures(self.private / "fixtures")
        count = SCENARIO_FIXTURES[self.scenario]
        self.assets = prepare_assets(self.private / "fixtures", data / "assets", count)
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(128)
        self.port = self.listener.getsockname()[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.env = restoration_environment(data, self.port, uploads=True)
        self.server, self.server_log, self.argv = launch_server(
            self.source_root, self.env, self.out / "server.log", self.listener
        )
        self.listener.close()
        self.listener = None
        wait_ready(self.base, self.server, self.out / "server.log")
        self.server_cwd = process_cwd(self.server.pid)
        self.api_client = Api(self.base)
        self.api_calls = self.api_client.calls
        self.browser = launch_browser(playwright, self.env)
        self.browser_version = getattr(self.browser, "version", None)
        context = self.browser.new_context(
            viewport={"width": 1440, "height": 900}, reduced_motion="reduce"
        )
        self.contexts.append(context)
        self.page = context.new_page()
        self.page.set_default_timeout(10_000)
        self.pages["controller"] = self.page
        self.observe(self.page, "controller")
        self.page.goto(self.base + "/controller/physical.html")
        self.page.locator("#tablet-url").wait_for(state="visible")

    def observe(self, page: Any, label: str) -> None:
        page.on("pageerror", lambda error: self.page_errors.append({"page": label, "error": str(error)}))
        page.on(
            "console",
            lambda message: self.console.append(
                {"page": label, "type": message.type, "text": message.text}
            )
            if message.type in ("warning", "error")
            else None,
        )
        page.on(
            "request",
            lambda request: self.requests.append(
                {
                    "page": label,
                    "method": request.method,
                    "url": request.url,
                    "if_match": request.headers.get("if-match"),
                }
            )
            if request.method not in ("GET", "HEAD")
            else None,
        )
        page.on(
            "response",
            lambda response: self.network.append(
                {"page": label, "url": response.url, "status": response.status}
            )
            if response.status >= 400
            else None,
        )

    def new_client(
        self,
        spec: dict[str, Any],
        index: int,
        init_script: str | None = None,
    ) -> tuple[Any, str]:
        options = {
            "viewport": {"width": spec["width"], "height": spec["height"]},
            "screen": {"width": spec["width"], "height": spec["height"]},
            "device_scale_factor": spec["dpr"],
            "is_mobile": spec["mobile"],
            "has_touch": spec["mobile"],
        }
        context = self.browser.new_context(**options)
        self.contexts.append(context)
        context.add_init_script(
            "Object.defineProperty(screen.orientation,'angle',"
            f"{{get:()=>{spec['orientation']},configurable:true}})"
        )
        if init_script:
            context.add_init_script(init_script)
        page = context.new_page()
        page.set_default_timeout(10_000)
        label = f"tablet-{index + 1}"
        self.observe(page, label)
        page.goto(self.base + "/client/")
        wait_until(page, "() => document.querySelector('#status')?.dataset.state === 'connected'")
        device_id = page.evaluate("localStorage.getItem('tablet-wall-device-id')")
        self.clients.append(
            {
                "label": label,
                "device_id": device_id,
                "viewport": {"width": spec["width"], "height": spec["height"]},
                "dpr": spec["dpr"],
                "orientation": spec["orientation"],
                "mobile": spec["mobile"],
            }
        )
        self.pages[label] = page
        return page, device_id

    # -- API --------------------------------------------------------------

    def place_logical_clients(self, count: int = 2) -> list[str]:
        screens = [
            self.new_client(spec, index)
            for index, spec in enumerate(CLIENT_SPECS[:count])
        ]
        ids = [device_id for _, device_id in screens]
        status, _ = self.request("PUT", "/wall", {"width": 1200, "height": 800})
        if status != 200:
            raise RuntimeError(f"logical wall write failed: {status}")
        for index, device_id in enumerate(ids):
            status, _ = self.request(
                "PUT",
                f"/devices/{device_id}/placement",
                {"x": index * 600, "y": 0, "w": 600, "h": 800},
            )
            if status != 200:
                raise RuntimeError(f"placement write failed: {status}")
        self.wait_config(
            lambda config: all(device_id in config["layout"]["placements"] for device_id in ids)
        )
        return ids

    def api(self) -> Api:
        if self.api_client is None:
            self.api_client = Api(self.base)
            self.api_calls = self.api_client.calls
        return self.api_client

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        if_match: str | None = None,
    ) -> tuple[int, Any]:
        return self.api().request(method, path, body, if_match)

    def config(self) -> dict[str, Any]:
        status, payload = self.request("GET", "/api/v3/config")
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError(f"config read failed: {status} {payload}")
        return payload

    def put_scene(self, content: dict[str, Any]) -> tuple[int, Any]:
        config = self.config()
        return self.request("PUT", "/api/v3/scene", {"content": content}, config["etag"])

    def wait_config(self, predicate: Any, timeout: float = 15) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            config = self.config()
            if predicate(config):
                return config
            if time.monotonic() >= deadline:
                raise RuntimeError("config predicate deadline exceeded")
            time.sleep(0.1)

    # -- UI ---------------------------------------------------------------

    def task(self, name: str) -> None:
        selector = self.page.locator("#compact-task-select")
        if selector.is_visible():
            selector.select_option(value=TASK_VALUES[name])
            return
        self.page.get_by_role(
            "tab", name=re.compile(rf"^{re.escape(name)}(?:, unsaved changes)?$")
        ).click()

    def open_disclosures(self, locator: Any) -> None:
        for detail in locator.locator("xpath=ancestor::details").all():
            if detail.get_attribute("open") is None:
                detail.locator(":scope > summary").click()

    def click(self, selector: str) -> None:
        locator = self.page.locator(selector)
        self.open_disclosures(locator)
        locator.click()

    def focus_press(self, selector: str, key: str = "Enter") -> None:
        locator = self.page.locator(selector)
        self.open_disclosures(locator)
        locator.focus()
        locator.press(key)

    def search(self, text: str) -> int:
        self.page.fill("#image-search", text)
        self.page.wait_for_timeout(60)
        return self.visible_gallery_count()

    def visible_gallery_count(self) -> int:
        return self.page.evaluate(
            "() => [...document.querySelectorAll('#image-gallery > li')].filter(li => !li.hidden).length"
        )

    def asset_names(self) -> list[str]:
        return [asset["name"] for asset in self.assets]

    def shot(self, name: str) -> str:
        clean = re.sub(r"[^\w.-]+", "-", name)
        path = self.out / f"{clean}.png"
        self.page.screenshot(path=str(path))
        return str(path)

    # -- assertions -------------------------------------------------------

    def check(
        self,
        name: str,
        ok: bool,
        actual: Any = None,
        expected: Any = True,
        *,
        fatal: bool = True,
        classification: str | None = None,
        known_baseline_failure: str | None = None,
    ) -> bool:
        artifact = None
        if not ok:
            try:
                artifact = self.shot(f"failure-{len(self.results) + 1:03d}")
            except Exception as error:  # capture failure must not mask the assertion
                artifact = f"capture failed: {error!r}"
        row = {
            "name": name,
            "pass": bool(ok),
            "expected": expected,
            "actual": actual,
            "artifact": artifact,
            "classification": classification
            or ("software_completed" if ok else "baseline_assertion_failed_needs_triage"),
            "known_baseline_failure": known_baseline_failure,
            "time": time.time(),
        }
        self.results.append(row)
        print(("PASS " if ok else "FAIL ") + self.scenario + " " + name, flush=True)
        if not ok and fatal:
            raise AssertionError(name)
        return bool(ok)

    # -- cleanup ----------------------------------------------------------

    def close(self) -> dict[str, Any]:
        cleanup: dict[str, Any] = {"errors": []}
        if self.page is not None:
            try:
                self.shot("final")
            except Exception as error:
                cleanup["errors"].append(f"final screenshot: {error!r}")
        fixtures_out = self.out / "fixtures"
        fixtures_out.mkdir(exist_ok=True)
        for asset in self.assets:
            source = Path(asset["path"])
            if source.is_file():
                target = fixtures_out / source.name
                shutil.copyfile(source, target)
                asset["artifact"] = str(target)
        for context in reversed(self.contexts):
            try:
                context.close()
            except Exception as error:
                cleanup["errors"].append(f"context close: {error!r}")
        cleanup["browser_disconnected"] = True
        if self.browser is not None:
            try:
                self.browser.close()
                cleanup["browser_disconnected"] = not self.browser.is_connected()
            except Exception as error:
                cleanup["errors"].append(f"browser close: {error!r}")
        cleanup["server"] = stop_owned_server(self.server)
        if self.server_log is not None:
            try:
                self.server_log.close()
            except Exception:
                pass
        if self.listener is not None:
            self.listener.close()
        if self.port is not None:
            with socket.socket() as probe:
                cleanup["port_closed"] = probe.connect_ex(("127.0.0.1", self.port)) != 0
        if self.private is not None:
            shutil.rmtree(self.private, ignore_errors=True)
            cleanup["private_data_removed"] = not self.private.exists()
        _write_json(self.out / "cleanup.json", cleanup)
        _write_json(
            self.out / "identity.json",
            {
                "task": TASK_ID,
                "scenario": self.scenario,
                "source": self.identity,
                "cwd": str(Path(self.source_root).resolve()),
                "command": [sys.executable, *sys.argv],
                "origin": self.base,
                "port": self.port,
                "server_argv": self.argv,
                "server_pid": None if self.server is None else self.server.pid,
                "server_cwd": self.server_cwd,
                "api_calls": self.api_calls,
                "private_paths": {
                    key: value
                    for key, value in self.env.items()
                    if key.startswith(("TABLET_WALL_", "XDG_"))
                    or key in {"TMPDIR", "HOME"}
                },
                "browser": {
                    "engine": "chromium",
                    "launch": "playwright-default-headless",
                    "version": self.browser_version,
                },
                "fixtures": self.fixtures,
                "assets": self.assets,
                "clients": self.clients,
            },
        )
        _write_json(self.out / "requests.json", self.requests)
        _write_json(
            self.out / "console.json",
            {"pageerrors": self.page_errors, "messages": self.console, "failed_responses": self.network},
        )
        return cleanup


# ---------------------------------------------------------------------------
# Scenario bodies
# ---------------------------------------------------------------------------


def _gallery_rows(page: Any) -> list[list[dict[str, Any]]]:
    return page.evaluate(
        """() => {
            const buttons = [...document.querySelectorAll('#image-gallery > li')]
                .filter(li => !li.hidden)
                .map(li => li.querySelector('button'))
                .filter(button => button && !button.disabled);
            const rows = [];
            for (const button of buttons) {
                const rect = button.getBoundingClientRect();
                let row = rows.find(item => Math.abs(item.top - rect.top) < 4);
                if (!row) { row = { top: rect.top, items: [] }; rows.push(row); }
                row.items.push({ name: button.textContent.trim(), left: rect.left });
            }
            rows.sort((a, b) => a.top - b.top);
            return rows.map(row => row.items.sort((a, b) => a.left - b.left));
        }"""
    )


def _active_target(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """() => {
            const element = document.activeElement;
            if (!element) return null;
            const rect = element.getBoundingClientRect();
            let parent = element.parentElement;
            while (parent) {
                const style = getComputedStyle(parent);
                const scrolls = /(auto|scroll)/.test(style.overflowY + style.overflowX);
                if (scrolls && (parent.scrollHeight > parent.clientHeight || parent.scrollWidth > parent.clientWidth)) break;
                parent = parent.parentElement;
            }
            const container = parent ? parent.getBoundingClientRect() : {top: 0, left: 0, right: innerWidth, bottom: innerHeight};
            const inside = rect.top >= container.top - 1 && rect.bottom <= container.bottom + 1
                && rect.left >= container.left - 1 && rect.right <= container.right + 1
                && rect.top >= -1 && rect.bottom <= innerHeight + 1;
            return {
                name: element.textContent.trim(),
                tag: element.tagName,
                rect: {top: rect.top, left: rect.left, right: rect.right, bottom: rect.bottom},
                container: parent ? (parent.id || parent.className || parent.tagName) : 'viewport',
                container_rect: {top: container.top, left: container.left, right: container.right, bottom: container.bottom},
                inside_scroll_viewport: inside,
            };
        }"""
    )


def _canvas_samples(page: Any) -> list[list[int]]:
    encoded = page.locator("#surface").evaluate("canvas => canvas.toDataURL('image/png')")
    image = Image.open(io.BytesIO(base64.b64decode(encoded.split(",", 1)[1]))).convert("RGB")
    xs = [2, image.width // 4, image.width // 2, image.width * 3 // 4, image.width - 3]
    ys = [2, image.height // 4, image.height // 2, image.height * 3 // 4, image.height - 3]
    return [list(image.getpixel((x, y))) for y in ys for x in xs]


def _wait_canvas(page: Any, timeout: float = 5) -> tuple[bool, list[list[int]]]:
    deadline = time.monotonic() + timeout
    visible = False
    samples: list[list[int]] = []
    while True:
        visible = page.evaluate(
            "() => { const canvas = document.getElementById('surface'); return !canvas.hidden && getComputedStyle(canvas).display !== 'none' && canvas.width > 0; }"
        )
        samples = _canvas_samples(page) if visible else []
        if visible and len({tuple(sample) for sample in samples}) >= 3:
            return visible, samples
        if time.monotonic() >= deadline:
            return visible, samples
        page.wait_for_timeout(100)


def _screenshot_pixel(page: Any, x: int | None = None, y: int | None = None) -> list[int]:
    image = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
    return list(image.getpixel((image.width // 2 if x is None else x, image.height // 2 if y is None else y)))


def _aggregate(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """async () => {
            const config = await (await fetch('/api/v3/config', {cache: 'no-store'})).json();
            const now = performance.now();
            const observed = window.OperatorState.observeConfig(config, now);
            return {config, aggregate: window.OperatorState.aggregate(observed, now)};
        }"""
    )


def _state_probes(page: Any, negatives: bool = True) -> dict[str, Any]:
    """State-rule probes over the current real token; never painted evidence.

    The config is projected with OperatorState.observeConfig exactly as
    operator-session does before tabletState/aggregate read the page clock.
    """
    return page.evaluate(
        """negatives => {
            const raw = window.__restorationConfig;
            const now = performance.now();
            const id = Object.keys(raw.runtime.devices)[0];
            const observed = () => window.OperatorState.observeConfig(
                JSON.parse(JSON.stringify(raw)), now);
            const state = config => window.OperatorState.tabletState(config, id, now);
            const result = { current: state(observed()) };
            if (!negatives) return result;
            let config = observed();
            config.runtime.devices[id].connection_id = 'foreign-connection';
            result.connection = state(config);
            config = observed();
            config.generation = 'foreign-generation';
            result.generation = state(config);
            config = observed();
            config.revision = Number(config.revision) + 1;
            result.revision = state(config);
            config = observed();
            config.runtime.devices[id].render.expected_token.mapping_revision = 'foreign-mapping';
            result.mapping = state(config);
            config = observed();
            config.runtime.devices[id].render.expected_token.asset = 'sha256:' + '0'.repeat(64);
            result.asset = state(config);
            config = observed();
            config.runtime.devices[id].render.expected_token.render_seq += 1;
            result.render_seq = state(config);
            config = observed();
            config.runtime.devices[id].render.age_ms = 15000;
            config.runtime.devices[id].render.observed_mono = now;
            result.age = state(config);
            config = observed();
            config.runtime.devices[id].render.state = 'hidden';
            result.hidden = state(config);
            config = observed();
            config.runtime.devices[id].render.state = 'blocked';
            config.runtime.devices[id].render.reason = 'zoom';
            result.zoomed = state(config);
            config = observed();
            delete config.layout.placements[id];
            result.unplaced = state(config);
            config = observed();
            config.runtime.presentation.owner = 'playback';
            result.playback = state(config);
            return result;
        }""",
        negatives,
    )


def require_hooks(rig: Rig, scenario: str) -> bool:
    """Fail explicitly when an owning task's additive DOM/JS hook is absent."""
    hooks = SCENARIO_HOOKS.get(scenario)
    if not hooks:
        return True
    missing: list[dict[str, str]] = []
    for selector in hooks.get("selectors", ()):
        try:
            present = rig.page.locator(selector).count() > 0
        except Exception as error:
            missing.append({"selector": selector, "error": repr(error)})
            continue
        if not present:
            missing.append({"selector": selector, "error": "not present"})
    for expression in hooks.get("expressions", ()):
        try:
            present = rig.page.evaluate(expression) is True
        except Exception as error:
            missing.append({"expression": expression, "error": repr(error)})
            continue
        if not present:
            missing.append({"expression": expression, "error": "not true"})
    if not missing:
        return True
    rig.check(
        f"{scenario} required hook is present (owner {hooks['owner']})",
        False,
        {"missing": missing},
        "all registered hooks present",
        fatal=False,
        classification="missing_required_hook",
    )
    return False


def delete_device_with_current_guard(rig: Rig, device_id: str) -> tuple[int, Any]:
    """Send the current If-Match guard, never an unguarded stale delete."""
    etag = rig.config().get("etag")
    if not etag:
        raise RuntimeError("current config etag is unavailable; refusing an unguarded DELETE")
    return rig.request("DELETE", f"/devices/{device_id}", if_match=etag)


def show_pattern(rig: Rig, selector: str) -> None:
    """Pattern controls live in Images after the authorized workbench move."""
    rig.task("Images")
    rig.click(selector)


def slot_rect(page: Any, device_id: str) -> dict[str, float] | None:
    return page.evaluate(
        """id => {
            const slot = document.querySelector('#stage-svg .slot[data-device-id="' + id + '"]');
            if (!slot) return null;
            const body = slot.querySelector('.operator-body-outline') || slot;
            const rect = body.getBoundingClientRect();
            return {x: rect.x, y: rect.y, w: rect.width, h: rect.height};
        }""",
        device_id,
    )


def draft_placement(page: Any, device_id: str) -> dict[str, float] | None:
    return page.evaluate(
        """id => {
            const body = document.querySelector('#stage-svg .slot[data-device-id="' + id + '"] .operator-body-outline');
            if (!body) return null;
            return {x: Number(body.getAttribute('x')), y: Number(body.getAttribute('y')),
                w: Number(body.getAttribute('width')), h: Number(body.getAttribute('height'))};
        }""",
        device_id,
    )


def select_stage_slot(rig: Rig, device_id: str) -> bool:
    rect = slot_rect(rig.page, device_id)
    if not rect:
        return False
    rig.page.mouse.click(rect["x"] + rect["w"] / 2, rect["y"] + rect["h"] / 2)
    try:
        wait_until(
            rig.page,
            "(id) => document.querySelector('#stage-svg .slot[aria-pressed=\"true\"]')?.dataset.deviceId === id",
            timeout=5,
            arg=device_id,
        )
    except TimeoutError:
        return False
    return True


def drag_slot(
    rig: Rig,
    device_id: str,
    dx: float,
    dy: float,
    *,
    steps: int = 12,
    alt: bool = False,
    escape: bool = False,
    viewport_resize: tuple[int, int] | None = None,
) -> None:
    """Drag a real rendered slot; deltas are draft logical units (or mm)."""
    page = rig.page
    page.evaluate("() => window.scrollTo(0, 0)")
    rect = slot_rect(page, device_id)
    placement = draft_placement(page, device_id)
    if not rect or not placement:
        raise RuntimeError(f"missing rendered slot {device_id}")
    combined = rect["w"] / max(1.0, placement["w"])
    point = page.evaluate(
        """id => {
            const slot = document.querySelector('#stage-svg .slot[data-device-id="' + id + '"]');
            const body = slot?.querySelector('.operator-body-outline');
            if (!body) return null;
            const rect = body.getBoundingClientRect();
            let left = Math.max(0, rect.left), top = Math.max(0, rect.top);
            let right = Math.min(innerWidth, rect.right), bottom = Math.min(innerHeight, rect.bottom);
            for (let node = body.parentElement; node; node = node.parentElement) {
                const style = getComputedStyle(node), box = node.getBoundingClientRect();
                if (/auto|scroll|hidden|clip/.test(style.overflowX)) {
                    left = Math.max(left, box.left + node.clientLeft);
                    right = Math.min(right, box.left + node.clientLeft + node.clientWidth);
                }
                if (/auto|scroll|hidden|clip/.test(style.overflowY)) {
                    top = Math.max(top, box.top + node.clientTop);
                    bottom = Math.min(bottom, box.top + node.clientTop + node.clientHeight);
                }
            }
            if (right - left < 8 || bottom - top < 8) return null;
            for (const fy of [0.5, 0.25, 0.75]) for (const fx of [0.5, 0.25, 0.75]) {
                const x = left + (right - left) * fx, y = top + (bottom - top) * fy;
                const hit = document.elementFromPoint(x, y);
                if (hit?.closest('.slot') === slot && !hit.closest('.logical-resize')) return {x, y};
            }
            return null;
        }""",
        device_id,
    )
    if point is None:
        raise RuntimeError(f"no visible, hit-tested drag point for slot {device_id}")
    start_x, start_y = point["x"], point["y"]
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    if alt:
        page.keyboard.down("Alt")
    page.mouse.move(start_x + dx * combined / 2, start_y + dy * combined / 2, steps=max(2, steps // 2))
    if viewport_resize is not None:
        page.set_viewport_size({"width": viewport_resize[0], "height": viewport_resize[1]})
    elif escape:
        page.keyboard.press("Escape")
    page.mouse.move(start_x + dx * combined, start_y + dy * combined, steps=max(2, steps))
    page.mouse.up()
    if alt:
        page.keyboard.up("Alt")
    page.wait_for_timeout(150)


def open_measurement_details(rig: Rig) -> None:
    rig.task("Settings")
    wait_until(rig.page, "() => !document.getElementById('panel-system').hidden")
    details = rig.page.locator("#measurement-details")
    if details.get_attribute("open") is None:
        details.locator(":scope > summary").click()
    rig.page.locator("#profile-form").wait_for(state="visible")


def set_logical_snap(rig: Rig, enabled: bool, step: int = 1) -> None:
    page = rig.page
    page.fill("#logical-snap", str(step))
    page.dispatch_event("#logical-snap", "change")
    if page.is_checked("#logical-snap-enabled") != enabled:
        if enabled:
            page.check("#logical-snap-enabled")
        else:
            page.uncheck("#logical-snap-enabled")
    page.wait_for_timeout(60)


def gallery_focus(rig: Rig) -> None:
    page = rig.page
    rig.place_logical_clients(2)
    rig.task("Images")
    wait_until(page, "() => document.querySelectorAll('#image-gallery > li').length === 24")
    names = page.evaluate(
        "() => [...document.querySelectorAll('#image-gallery .image-choice-name')].map(node => node.textContent)"
    )
    rig.check(
        "24-image library renders one button per deterministic asset",
        len(names) == 24 and len(set(names)) == 24,
        {"count": len(names), "unique": len(set(names))},
        24,
    )
    rig.check(
        "Fixture labels include long operator-style names",
        max(len(name) for name in names) >= 80,
        max(len(name) for name in names),
        ">=80 characters",
    )

    north = rig.search("north-gallery")
    rig.check("Filter reduces the 24-image library to the 8 north fixtures", north == 8, north, 8)
    single = rig.search(rig.asset_names()[0])
    rig.check("Filter isolates exactly one long-named asset", single == 1, single, 1)
    empty = rig.search("no-such-image-token")
    rig.check(
        "Zero results keep search usable and show distinct empty text",
        empty == 0 and page.locator("#image-search").is_enabled() and page.locator("#image-search-empty").is_visible(),
        {"visible": empty, "search_enabled": page.locator("#image-search").is_enabled()},
        {"visible": 0, "search_enabled": True},
    )
    rig.search("")

    before = rig.config()
    page.locator("#image-gallery li:not([hidden]) .image-choice-button").first.focus()
    page.keyboard.press("End")
    end = _active_target(page)
    rig.check(
        "End focuses the last visible gallery button inside its scroll viewport",
        bool(end and end["inside_scroll_viewport"] and end["name"] == names[-1]),
        end,
        {"name": names[-1], "inside_scroll_viewport": True},
        fatal=False,
        known_baseline_failure=SCENARIOS["gallery-focus"]["known_baseline_failure"],
    )
    page.keyboard.press("Home")
    home = _active_target(page)
    rig.check(
        "Home focuses the first visible gallery button inside its scroll viewport",
        bool(home and home["inside_scroll_viewport"] and home["name"] == names[0]),
        home,
        {"name": names[0], "inside_scroll_viewport": True},
        fatal=False,
        known_baseline_failure=SCENARIOS["gallery-focus"]["known_baseline_failure"],
    )

    rows = _gallery_rows(page)
    expected_down = None
    if len(rows) > 1 and rows[0]:
        first_left = rows[0][0]["left"]
        expected_down = min(rows[1], key=lambda item: abs(item["left"] - first_left))["name"]
    page.locator("#image-gallery li:not([hidden]) .image-choice-button").first.focus()
    page.keyboard.press("ArrowDown")
    down = _active_target(page)
    rig.check(
        "ArrowDown moves to the nearest button in the next rendered row",
        bool(expected_down and down and down["name"] == expected_down),
        {"active": None if down is None else down["name"], "rows": rows},
        {"expected": expected_down},
        fatal=False,
        known_baseline_failure=SCENARIOS["gallery-focus"]["known_baseline_failure"],
    )
    after = rig.config()
    scene_writes = [
        row for row in rig.requests if row["method"] == "PUT" and row["url"].endswith("/api/v3/scene")
    ]
    rig.check(
        "Gallery focus and filter never write scene content",
        not scene_writes and after["revision"] == before["revision"],
        {"scene_writes": scene_writes, "before": before["revision"], "after": after["revision"]},
        {"scene_writes": [], "revision": before["revision"]},
    )
    rig.check(
        "Focused gallery navigation retains the wall and Show context",
        page.locator("#stage-svg").is_visible() and page.locator("#show-image").count() == 1,
        {"stage_visible": page.locator("#stage-svg").is_visible(), "show_controls": page.locator("#show-image").count()},
        True,
    )

    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(120)
    rig.search("")
    page.locator("#image-gallery li:not([hidden]) .image-choice-button").first.focus()
    page.keyboard.press("End")
    phone = _active_target(page)
    rig.check(
        "Phone End exposes the last gallery target inside the horizontal chooser",
        bool(phone and phone["inside_scroll_viewport"] and phone["name"] == names[-1]),
        phone,
        {"name": names[-1], "inside_scroll_viewport": True},
        fatal=False,
        known_baseline_failure=SCENARIOS["gallery-focus"]["known_baseline_failure"],
    )
    rig.check(
        "Phone gallery does not create document horizontal overflow",
        page.evaluate("() => document.documentElement.scrollWidth <= innerWidth + 1"),
        page.evaluate("() => ({width: document.documentElement.scrollWidth, viewport: innerWidth})"),
        {"scrollWidth": "<= innerWidth + 1"},
        fatal=False,
    )


def library_composer(rig: Rig) -> None:
    page = rig.page
    rig.place_logical_clients(2)
    rig.task("Images")
    wait_until(page, "() => document.querySelectorAll('#image-gallery > li').length === 24")
    names = rig.asset_names()

    counts = {
        "24": rig.search(""),
        "8": rig.search("north-gallery"),
        "1": rig.search(names[0]),
        "0": rig.search("no-such-image-token"),
    }
    rig.check(
        "Library filters expose 24, 8, 1 and 0 asset states",
        counts == {"24": 24, "8": 8, "1": 1, "0": 0},
        counts,
        {"24": 24, "8": 8, "1": 1, "0": 0},
    )
    rig.search("")
    before = rig.config()
    gallery_names = page.evaluate(
        "() => [...document.querySelectorAll('#image-gallery > li:not([hidden]) .image-choice-name')].map(node => node.textContent)"
    )
    last = page.locator("#image-gallery li:not([hidden]) .image-choice-button").last
    last_name = gallery_names[-1]
    last.scroll_into_view_if_needed()
    last.click()
    wait_until(
        page,
        "(name) => document.querySelector('#image-title')?.textContent === name",
        arg=last_name,
    )
    after = rig.config()
    scene_writes = [
        row for row in rig.requests if row["method"] == "PUT" and row["url"].endswith("/api/v3/scene")
    ]
    rig.check(
        "Choosing image 24 is proposal-only and preserves durable scene and revision",
        not scene_writes
        and after["revision"] == before["revision"]
        and after["scene"] == before["scene"],
        {"scene_writes": scene_writes, "before": before["revision"], "after": after["revision"]},
        {"scene_writes": [], "scene": "unchanged"},
    )
    rig.check(
        "Image 24 exposes a reachable Show action and matching composer title",
        page.locator("#image-preview-controls").is_visible()
        and page.locator("#show-image").is_enabled()
        and page.locator("#image-title").inner_text() == last_name,
        {
            "preview_visible": page.locator("#image-preview-controls").is_visible(),
            "show_enabled": page.locator("#show-image").is_enabled(),
            "title": page.locator("#image-title").inner_text(),
        },
        {"show_enabled": True, "title": last_name},
        fatal=False,
    )
    stage_box = page.locator("#wall-context-content").bounding_box()
    composer_box = page.locator("#selected-image-controls").bounding_box()
    rig.check(
        "Desktop image 24 retains visible wall and composer boxes",
        bool(
            stage_box
            and composer_box
            and stage_box["y"] < 900
            and composer_box["y"] < 900
        ),
        {"stage": stage_box, "composer": composer_box},
        "both start inside the 1440x900 viewport",
        fatal=False,
    )

    rig.click("#add-image")
    rig.check(
        "Upload admission remains reachable from the long library",
        page.locator("#image-addition").get_attribute("open") is not None
        and (
            page.locator("#upload-form").is_visible()
            or page.locator("#upload-instruction").is_visible()
        ),
        {
            "open": page.locator("#image-addition").get_attribute("open"),
            "form_visible": page.locator("#upload-form").is_visible(),
            "instruction_visible": page.locator("#upload-instruction").is_visible(),
        },
        "details open with an admission form or instruction",
    )

    # Stable DOM and focus are the observable part of "retained browse position".
    page.evaluate(
        "() => { const item = document.querySelector('#image-gallery > li'); item.dataset.restorationProbe = 'kept'; }"
    )
    page.locator("#image-search").focus()
    rig.search("north-gallery")
    rig.search("")
    kept = page.evaluate(
        "() => document.querySelector('#image-gallery > li')?.dataset.restorationProbe === 'kept'"
    )
    focus_in_search = page.evaluate(
        "() => document.activeElement === document.getElementById('image-search')"
    )
    roving = page.evaluate(
        "() => document.querySelectorAll('#image-gallery .image-choice-button[tabindex=\"0\"]').length"
    )
    rig.check(
        "Filtering keeps focus in the search field and preserves stable library DOM",
        kept and focus_in_search and roving == 1,
        {"stable_dom": kept, "focus_in_search": focus_in_search, "roving_tab_stops": roving},
        {"stable_dom": True, "focus_in_search": True, "roving_tab_stops": 1},
        fatal=False,
    )

    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(120)
    wall_box = page.locator("#wall-context-content").bounding_box()
    library_box = page.locator("#panel-content .image-library").bounding_box()
    rig.check(
        "Phone wall and action context precede the long chooser",
        bool(wall_box and library_box and wall_box["y"] <= library_box["y"]),
        {"wall": wall_box, "library": library_box},
        "wall top <= library top",
        fatal=False,
        known_baseline_failure=SCENARIOS["library-composer"]["known_baseline_failure"],
    )
    rig.check(
        "Phone long library does not create document horizontal overflow",
        page.evaluate("() => document.documentElement.scrollWidth <= innerWidth + 1"),
        page.evaluate("() => ({width: document.documentElement.scrollWidth, viewport: innerWidth})"),
        {"scrollWidth": "<= innerWidth + 1"},
    )


def recovery_sheet(rig: Rig) -> None:
    page = rig.page
    ids = rig.place_logical_clients(2)
    offline_context = rig.contexts[2]
    rig.contexts.remove(offline_context)
    offline_context.close()
    rig.wait_config(
        lambda config: config["runtime"]["devices"][ids[1]]["online"] is False, timeout=20
    )
    rig.task("Tablets")
    issue = page.locator(f'#wall-issues .issue-row[data-device-id="{ids[1]}"] .issue-action')
    if page.locator("#wall-issues-panel").get_attribute("open") is None:
        page.locator("#issues-title").click()
    issue.wait_for(state="visible")
    rig.check("Offline reservation appears as a wall issue", issue.is_visible(), True, True)

    # Desktop keyboard action: the sheet is a static inspector here.
    issue.focus()
    issue.press("Enter")
    wait_until(
        page,
        "(id) => [...document.querySelectorAll('#device-list .dev-row')]"
        ".some(row => row.dataset.selected === 'true' && row.dataset.deviceId === id)",
        arg=ids[1],
    )
    heading = page.locator("#tablet-action-name").inner_text()
    recovery_text = page.locator("#tablet-recovery")
    rig.check(
        "Desktop keyboard issue action selects the reserved tablet and reveals recovery guidance",
        heading != "Select a tablet."
        and recovery_text.is_visible()
        and "power" in recovery_text.inner_text().lower(),
        {"heading": heading, "recovery": recovery_text.inner_text() if recovery_text.is_visible() else None},
        {"heading": "selected tablet", "recovery": "power/network guidance"},
        fatal=False,
        known_baseline_failure=SCENARIOS["recovery-sheet"]["known_baseline_failure"],
    )

    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(150)
    issue = page.locator(f'#wall-issues .issue-row[data-device-id="{ids[1]}"] .issue-action')
    rig.check(
        "Removed compact sheet is closed before the phone issue action",
        not page.evaluate("document.getElementById('device-sheet').open"),
        page.evaluate("document.getElementById('device-sheet').open"),
        False,
    )
    rig.open_disclosures(issue)
    issue.scroll_into_view_if_needed()
    issue.click()
    opened = False
    try:
        wait_until(
            page,
            "() => { const sheet = document.getElementById('device-sheet'); "
            "return !!sheet && sheet.open && sheet.dataset.modal === 'true'; }",
            timeout=3,
        )
        opened = True
    except Exception:
        opened = False
    rig.check(
        "Phone touch issue action opens the compact recovery sheet",
        opened,
        {"sheet_open": page.evaluate("document.getElementById('device-sheet').open")},
        True,
        fatal=False,
        known_baseline_failure=SCENARIOS["recovery-sheet"]["known_baseline_failure"],
    )
    if opened:
        rig.check(
            "Phone recovery sheet names the reserved tablet",
            page.locator("#tablet-action-name").inner_text() != "Select a tablet.",
            page.locator("#tablet-action-name").inner_text(),
            "selected tablet",
        )
        page.keyboard.press("Escape")
        wait_until(page, "() => !document.getElementById('device-sheet').open")
        rig.check(
            "Escape closes the recovery sheet and returns focus to a visible control",
            page.evaluate(
                "() => { const element = document.activeElement; return !!element && element.isConnected && !element.hidden && element.getClientRects().length > 0; }"
            ),
            page.evaluate("() => document.activeElement?.id || document.activeElement?.className"),
            "visible connected control",
        )

    # Same-device roster pick is a separate supported reveal path.
    pick = page.locator(f'#device-list .dev-pick[data-device-id="{ids[0]}"]')
    if pick.count():
        pick.scroll_into_view_if_needed()
        pick.click()
        try:
            wait_until(
                page,
                "() => { const sheet = document.getElementById('device-sheet'); "
                "return !!sheet && sheet.open && sheet.dataset.modal === 'true'; }",
                timeout=3,
            )
            rig.check(
                "Same online device opens through the roster reveal path",
                page.locator("#tablet-action-name").inner_text() != "Select a tablet.",
                page.locator("#tablet-action-name").inner_text(),
                "selected online tablet",
            )
            page.keyboard.press("Escape")
            wait_until(page, "() => !document.getElementById('device-sheet').open")
            rig.check(
                "Escape returns focus to the visible roster trigger",
                page.evaluate("() => document.activeElement?.classList.contains('dev-pick') === true"),
                page.evaluate("() => document.activeElement?.className"),
                "dev-pick",
                fatal=False,
            )
        except Exception as error:
            rig.check(
                "Same online device opens through the roster reveal path",
                False,
                repr(error),
                "sheet opens",
                fatal=False,
            )

    status, payload = delete_device_with_current_guard(rig, ids[1])
    rig.check(
        "Offline reservation can be removed deliberately with the current If-Match guard",
        status == 200,
        {"status": status, "if_match": rig.api_calls[-1].get("if_match")},
        200,
    )
    try:
        wait_until(
            page,
            "(id) => ![...document.querySelectorAll('#wall-issues .issue-row')]"
            ".some(row => row.dataset.deviceId === id)",
            arg=ids[1],
            timeout=5,
        )
        removed = True
    except Exception:
        removed = False
    rig.check(
        "Removed device leaves no stale issue action",
        removed,
        {"issue_row_present": page.locator(f'#wall-issues .issue-row[data-device-id="{ids[1]}"]').count()},
        {"issue_row_present": 0},
        fatal=False,
    )


def scene_paint(rig: Rig) -> None:
    page = rig.page
    clients = [rig.new_client(spec, index) for index, spec in enumerate(CLIENT_SPECS)]
    ids = [device_id for _, device_id in clients]
    status, _ = rig.request("PUT", "/wall", {"width": 1600, "height": 1000})
    rig.check("Logical wall accepts the four unequal clients", status == 200, status, 200)
    for index, device_id in enumerate(ids):
        status, _ = rig.request(
            "PUT",
            f"/devices/{device_id}/placement",
            {
                "x": (index % 2) * 800,
                "y": (index // 2) * 500,
                "w": 800,
                "h": 500,
            },
        )
        rig.check(f"Client {index + 1} placement accepted", status == 200, status, 200)
    rig.wait_config(lambda config: all(device_id in config["layout"]["placements"] for device_id in ids))

    for device_id, colour in zip(ids, CLIENT_COLOURS, strict=True):
        status, _ = rig.request("POST", f"/devices/{device_id}/color", {"color": colour})
        rig.check(f"Test colour accepted for {device_id[-6:]}", status == 200, status, 200)

    rig.check(
        "Presentation pattern controls are in the Images workbench",
        page.locator("#panel-content #presentation-checks").count() == 1,
        page.locator("#panel-content #presentation-checks").count(),
        1,
        fatal=False,
    )
    show_pattern(rig, "#show-colours")
    page.wait_for_timeout(300)
    for index, (client_page, device_id) in enumerate(clients):
        colour = CLIENT_COLOURS[index]
        try:
            wait_until(
                client_page,
                "(colour) => getComputedStyle(document.documentElement)"
                ".getPropertyValue('--surface-color').trim().toLowerCase() === colour",
                arg=colour,
                timeout=5,
            )
            applied = True
        except Exception:
            applied = False
        pixel = _screenshot_pixel(client_page)
        expected = tuple(int(colour[offset : offset + 2], 16) for offset in (1, 3, 5))
        rig.check(
            f"Real client {index + 1} paints its colour background",
            applied and max(abs(a - b) for a, b in zip(pixel, expected, strict=True)) <= 4,
            {"applied": applied, "pixel": pixel, "expected": list(expected)},
            {"applied": True, "pixel": list(expected)},
            fatal=False,
        )

    colour_aggregate = _aggregate(page)
    rig.check(
        "Colour paint is confirmed as displayed on all four real clients",
        colour_aggregate["aggregate"]["showing"] == 4,
        {
            "total": colour_aggregate["aggregate"]["total"],
            "showing": colour_aggregate["aggregate"]["showing"],
            "states": [row["status"] for row in colour_aggregate["aggregate"]["states"]],
        },
        4,
        fatal=False,
        classification="baseline_assertion_failed_needs_triage",
        known_baseline_failure=SCENARIOS["scene-paint"]["known_baseline_failure"],
    )

    rig.click("#show-calibration")
    for index, (client_page, _) in enumerate(clients):
        visible, samples = _wait_canvas(client_page)
        unique = {tuple(sample) for sample in samples}
        rig.check(
            f"Real client {index + 1} paints a varied logical calibration canvas",
            visible and len(unique) >= 3,
            {"visible": visible, "unique_colours": len(unique)},
            {"visible": True, "unique_colours": ">=3"},
            fatal=False,
        )

    calibration_aggregate = _aggregate(page)
    rig.check(
        "Logical calibration paint is confirmed as displayed on all four real clients",
        calibration_aggregate["aggregate"]["showing"] == 4,
        {
            "total": calibration_aggregate["aggregate"]["total"],
            "showing": calibration_aggregate["aggregate"]["showing"],
            "states": [row["status"] for row in calibration_aggregate["aggregate"]["states"]],
        },
        4,
        fatal=False,
        classification="baseline_assertion_failed_needs_triage",
        known_baseline_failure=SCENARIOS["scene-paint"]["known_baseline_failure"],
    )

    asset = rig.assets[0]
    asset_id = "sha256:" + asset["sha256"]
    status, payload = rig.put_scene({"type": "image", "asset": asset_id, "fit": "cover"})
    rig.check("Fixture image scene accepted", status == 200, status, 200)
    try:
        rig.wait_config(
            lambda config: all(
                config["runtime"]["devices"][device_id]["render"].get("state") == "displayed"
                for device_id in ids
            ),
            timeout=20,
        )
        image_painted = True
    except Exception:
        image_painted = False
    rig.check(
        "Real clients report the current image as displayed",
        image_painted,
        rig.config()["runtime"]["devices"],
        "all four displayed",
        fatal=False,
    )
    if image_painted:
        for index, (client_page, _) in enumerate(clients):
            visible, samples = _wait_canvas(client_page)
            unique = {tuple(sample) for sample in samples}
            rig.check(
                f"Real client {index + 1} image canvas is not blank",
                visible and len(unique) >= 3,
                {"visible": visible, "unique_colours": len(unique)},
                {"visible": True, "unique_colours": ">=3"},
                fatal=False,
            )

    # State-rule probes use the real current token but are explicitly not
    # client paint evidence. Without a displayed image token there is nothing
    # honest to mutate.
    if image_painted:
        page.evaluate("config => { window.__restorationConfig = config; }", rig.config())
        current = _state_probes(page, negatives=False)["current"]
        positive = rig.check(
            "Current real token is displayed before negative probes",
            current["status"] == "displayed" and current["showing"] is True,
            current,
            "displayed",
            fatal=False,
            classification="state_rule_probe",
        )
        if positive:
            probes = _state_probes(page)
            for name, label in (
                ("connection", "foreign connection"),
                ("generation", "foreign generation"),
                ("revision", "foreign revision"),
                ("mapping", "foreign mapping revision"),
                ("asset", "foreign asset"),
                ("render_seq", "foreign render sequence"),
                ("age", "age 15000 ms"),
                ("hidden", "hidden report"),
                ("zoomed", "zoomed/blocked report"),
                ("unplaced", "unplaced slot"),
                ("playback", "playback presentation"),
            ):
                rig.check(
                    f"Negative token/state probe rejects {label}",
                    probes[name]["showing"] is False,
                    probes[name],
                    {"showing": False},
                    fatal=False,
                    classification="state_rule_probe",
                )
        else:
            rig.check(
                "Negative token/state probes are not driven without a fresh displayed real token",
                False,
                current,
                "fresh displayed token",
                fatal=False,
                classification="not_driven_after_previous_failure",
            )
    else:
        rig.check(
            "Negative token/state probes are not driven without a displayed real token",
            False,
            {"image_painted": False},
            "real displayed token",
            fatal=False,
            classification="not_driven_after_previous_failure",
        )


def fit_feedback(rig: Rig) -> None:
    page = rig.page
    if not require_hooks(rig, "fit-feedback"):
        return
    clients = [rig.new_client(spec, index) for index, spec in enumerate(CLIENT_SPECS[:2])]
    ids = [device_id for _, device_id in clients]
    status, _ = rig.request("PUT", "/wall", {"width": 200, "height": 200})
    rig.check("Fit feedback wall accepts 200 x 200 relative bounds", status == 200, status, 200)
    for index, device_id in enumerate(ids):
        status, _ = rig.request(
            "PUT",
            f"/devices/{device_id}/placement",
            {"x": index * 100, "y": 0, "w": 100, "h": 100},
        )
        rig.check(f"Fit feedback client {index + 1} placement accepted", status == 200, status, 200)
    rig.wait_config(lambda config: all(device_id in config["layout"]["placements"] for device_id in ids))
    rig.task("Images")
    wait_until(page, "() => document.querySelectorAll('#image-gallery > li').length === 8")

    page.locator("#image-gallery > li .image-choice-button").first.click()
    wait_until(page, "() => document.getElementById('image-preview-controls')?.hidden === false")
    page.select_option("#image-fit", "cover")
    page.wait_for_timeout(120)
    summary = page.locator("#fit-summary").inner_text()
    width_text = page.locator("#crop-width").inner_text()
    height_text = page.locator("#crop-height").inner_text()
    rig.check(
        "Fill preview reports source-width crop on a square logical wall",
        "37.5% of the source width" in summary and "0% of the source height" in summary,
        {"summary": summary, "width": width_text, "height": height_text},
        {"source_width": "37.5%", "source_height": "0%"},
    )
    rig.check(
        "Crop bars use the same percentages and denominator",
        width_text == "37.5% of source width cropped" and height_text == "0% of source height cropped",
        {"width": width_text, "height": height_text},
        {"width": "37.5% of source width cropped", "height": "0% of source height cropped"},
    )
    rig.check(
        "Proposal preview does not claim applied fit",
        "no image fit" in page.locator("#fit-applied").inner_text(),
        page.locator("#fit-applied").inner_text(),
        "no image fit",
    )
    before = rig.config()
    scene_writes = [
        row for row in rig.requests if row["method"] == "PUT" and row["url"].endswith("/api/v3/scene")
    ]
    rig.check(
        "Choosing and changing fit sends no durable scene write",
        not scene_writes and rig.config()["revision"] == before["revision"],
        {"writes": scene_writes, "before": before["revision"], "after": rig.config()["revision"]},
        {"writes": [], "revision": before["revision"]},
    )

    page.select_option("#image-fit", "contain")
    page.wait_for_timeout(120)
    contain_summary = page.locator("#fit-summary").inner_text()
    rig.check(
        "Fit preview reports wall-height bands without mixing denominators",
        "0% of the wall width" in contain_summary
        and "37.5% of the wall height" in contain_summary,
        contain_summary,
        {"wall_width": "0%", "wall_height": "37.5%"},
    )

    page.click("#show-image")
    rig.wait_config(
        lambda config: config["scene"]["content"].get("type") == "image"
        and config["scene"]["content"].get("fit") == "contain"
    )
    rig.check(
        "Settled image names the applied Fit and explicit background",
        "Applied: Fit" in page.locator("#fit-applied").inner_text()
        and "#0b1120" in page.locator("#fit-applied").inner_text(),
        page.locator("#fit-applied").inner_text(),
        {"fit": "Fit", "background": "#0b1120"},
    )
    applied_summary = page.locator("#fit-summary").inner_text()
    rig.check(
        "Applied feedback reports the committed fit after Show",
        applied_summary.startswith("Applied Fit of 1600 × 1000:")
        and "37.5% of the wall height" in applied_summary,
        applied_summary,
        "Applied Fit of 1600 × 1000 with 37.5% wall height uncovered",
    )

    applied_line = page.locator("#fit-applied").inner_text()
    page.locator("#image-gallery > li .image-choice-button").nth(1).click()
    page.wait_for_timeout(120)
    rig.check(
        "A later draft selection never rewrites the settled applied line",
        page.locator("#fit-applied").inner_text() == applied_line,
        page.locator("#fit-applied").inner_text(),
        applied_line,
    )
    rig.check(
        "Tall draft exposes its own proposed crop estimate",
        "1000 × 1600" in page.locator("#fit-summary").inner_text(),
        page.locator("#fit-summary").inner_text(),
        "1000 × 1600 preview",
    )


def geometry_tools(rig: Rig) -> None:
    page = rig.page
    ids = rig.place_logical_clients(2)
    rig.task("Arrange")
    wait_until(page, "() => document.querySelectorAll('#stage-svg .slot').length >= 2")
    rig.check(
        "Geometry controls are enabled from the reviewed stage module",
        page.locator("#view-zoom-2x").is_enabled()
        and page.locator("#view-zoom-fit").is_enabled()
        and page.locator("#logical-snap-enabled").is_enabled()
        and page.locator("#btn-match-shape").count() == 1,
        {
            "2x": page.locator("#view-zoom-2x").is_enabled(),
            "snap": page.locator("#logical-snap-enabled").is_enabled(),
            "match_present": page.locator("#btn-match-shape").count(),
        },
        {"2x": True, "snap": True, "match_present": 1},
    )
    rig.open_disclosures(page.locator("#geometry-help-text"))
    help_text = page.locator("#geometry-help-text").inner_text()
    rig.check(
        "Geometry help names the real keyboard and view alternatives",
        "Alt" in help_text and "2x" in help_text and "unit" in help_text.lower(),
        help_text,
        "Alt, 2x and unit alternatives",
    )
    rig.check(
        "Initial wall view is Fit",
        page.evaluate("() => (document.body.dataset.viewZoom || 'fit') === 'fit'")
        and page.get_attribute("#view-zoom-fit", "aria-pressed") == "true",
        page.evaluate("() => document.body.dataset.viewZoom || 'fit'"),
        "fit",
    )

    before = rig.config()
    view_requests_before = len(rig.requests)
    page.click("#view-zoom-2x")
    wait_until(page, "() => document.body.dataset.viewZoom === '2x'")
    rig.check(
        "2x changes only the view state and pressed control",
        page.get_attribute("#view-zoom-2x", "aria-pressed") == "true"
        and rig.config()["revision"] == before["revision"]
        and rig.config()["layout"] == before["layout"]
        and page.evaluate("() => document.body.dataset.outputDirty === 'false'"),
        {"zoom": page.evaluate("() => document.body.dataset.viewZoom"),
         "revision": rig.config()["revision"], "dirty": page.evaluate("() => document.body.dataset.outputDirty")},
        {"zoom": "2x", "revision": before["revision"], "dirty": "false"},
    )
    rig.check(
        "2x is view-only and writes no network command",
        not [row for row in rig.requests[view_requests_before:] if row["page"] == "controller"],
        [row for row in rig.requests[view_requests_before:] if row["page"] == "controller"],
        [],
    )
    page.click("#view-zoom-fit")
    wait_until(page, "() => (document.body.dataset.viewZoom || 'fit') === 'fit'")

    rig.check("First stage slot can be selected for direct editing", select_stage_slot(rig, ids[0]))
    set_logical_snap(rig, False, 1)
    original = rig.config()["layout"]["placements"][ids[0]]
    drag_slot(rig, ids[0], 12, 8)
    moved = draft_placement(page, ids[0])
    rig.check(
        "Fit pointer drag commits the requested relative displacement in the draft",
        bool(moved and moved["x"] == original["x"] + 12 and moved["y"] == original["y"] + 8),
        {"before": original, "after": moved},
        {"x": original["x"] + 12, "y": original["y"] + 8},
    )
    rig.check(
        "A draft drag writes no durable layout before Apply",
        rig.config()["layout"]["placements"][ids[0]] == original,
        rig.config()["layout"]["placements"][ids[0]],
        original,
    )
    page.click("#btn-undo")
    wait_until(
        page,
        "(expected) => { const slot = document.querySelector('#stage-svg .slot[data-device-id=\"' + expected.id + '\"] .operator-body-outline'); "
        "return slot && Number(slot.getAttribute('x')) === expected.x; }",
        arg={"id": ids[0], "x": original["x"]},
    )
    rig.check(
        "One undo restores the exact pre-drag geometry",
        draft_placement(page, ids[0])["x"] == original["x"],
        draft_placement(page, ids[0]),
        original,
    )

    page.click("#view-zoom-2x")
    wait_until(page, "() => document.body.dataset.viewZoom === '2x'")
    drag_slot(rig, ids[0], 8, 0)
    scaled = draft_placement(page, ids[0])
    rig.check(
        "2x pointer delta maps to the same logical units without double transform",
        bool(scaled and scaled["x"] == original["x"] + 8),
        scaled,
        {"x": original["x"] + 8},
    )
    page.click("#view-zoom-fit")
    wait_until(page, "() => (document.body.dataset.viewZoom || 'fit') === 'fit'")

    pre_escape = draft_placement(page, ids[0])
    drag_slot(rig, ids[0], 20, 0, escape=True)
    rig.check(
        "Escape mid-drag cancels and restores the pre-draft geometry",
        draft_placement(page, ids[0]) == pre_escape,
        draft_placement(page, ids[0]),
        pre_escape,
    )
    pre_resize = draft_placement(page, ids[0])
    drag_slot(rig, ids[0], 20, 0, viewport_resize=(1280, 800))
    page.set_viewport_size({"width": 1440, "height": 900})
    page.wait_for_timeout(160)
    rig.check(
        "A view resize mid-drag cancels and restores the pre-draft geometry",
        draft_placement(page, ids[0]) == pre_resize,
        draft_placement(page, ids[0]),
        pre_resize,
    )
    page.click("#btn-cancel")
    wait_until(page, "() => document.body.dataset.outputDirty === 'false'")

    set_logical_snap(rig, True, 20)
    before_snap = rig.config()["layout"]["placements"][ids[0]]
    drag_slot(rig, ids[0], 12, 0)
    snapped = draft_placement(page, ids[0])
    rig.check(
        "Enabled grid snap rounds a relative drag to the declared step",
        bool(snapped and snapped["x"] % 20 == 0 and snapped["x"] != before_snap["x"] + 12),
        snapped,
        {"multiple_of": 20, "not_raw": before_snap["x"] + 12},
    )
    page.click("#btn-cancel")
    wait_until(page, "() => document.body.dataset.outputDirty === 'false'")
    set_logical_snap(rig, True, 20)
    drag_slot(rig, ids[0], 12, 0, alt=True)
    bypass = draft_placement(page, ids[0])
    rig.check(
        "Alt bypasses grid snap and keeps the raw whole-unit delta",
        bool(bypass and bypass["x"] == before_snap["x"] + 12),
        bypass,
        {"x": before_snap["x"] + 12},
    )
    page.click("#btn-cancel")
    wait_until(page, "() => document.body.dataset.outputDirty === 'false'")

    tie = page.evaluate(
        """() => window.PhysicalSizing.snapLogical(
            {x: 17, y: 40, w: 60, h: 40, bezel: {top: 0, right: 0, bottom: 0, left: 2}},
            {kind: 'logical', width: 200, height: 100, placements: {
                a: {x: 17, y: 40, w: 60, h: 40, bezel: {top: 0, right: 0, bottom: 0, left: 2}},
                b: {x: 16, y: 0, w: 20, h: 20, bezel: {top: 0, right: 0, bottom: 0, left: 2}}}},
            {id: 'a', mode: 'move', step: 20, enabled: true, threshold: 2})"""
    )
    rig.check(
        "Edge decision runs before grid spacing at an exact tie",
        tie["x"] == 16,
        tie,
        {"x": 16},
    )

    # Match is a draft-only, current-viewport operation.
    set_logical_snap(rig, False, 1)
    select_stage_slot(rig, ids[0])
    match_before = rig.config()["layout"]["placements"][ids[0]]
    requests_before = len(rig.requests)
    page.click("#btn-match-shape")
    page.wait_for_timeout(180)
    matched = draft_placement(page, ids[0])
    rig.check(
        "Match uses the current online viewport shape and mutates only the draft",
        bool(matched and matched["h"] == 375 and matched["x"] == match_before["x"]),
        matched,
        {"h": 375, "x": match_before["x"]},
    )
    rig.check(
        "Match sends no durable write before Apply",
        not [row for row in rig.requests[requests_before:] if row["method"] != "GET"]
        and rig.config()["layout"]["placements"][ids[0]] == match_before,
        {"writes": [row for row in rig.requests[requests_before:] if row["method"] != "GET"]},
        {"writes": []},
    )
    page.click("#btn-apply")
    rig.wait_config(
        lambda config: config["layout"]["placements"][ids[0]]["h"] == 375,
        timeout=15,
    )
    put_rows = [row for row in rig.requests if row["method"] == "PUT" and row["url"].endswith("/api/v3/logical-layout")]
    rig.check(
        "Apply sends one guarded logical-layout command with integer geometry",
        len(put_rows) == 1 and put_rows[0].get("if_match")
        and rig.config()["layout"]["placements"][ids[0]]["h"] == 375,
        {"puts": put_rows, "applied": rig.config()["layout"]["placements"][ids[0]]},
        {"puts": 1, "if_match": True, "h": 375},
    )

    # Measured mode keeps pinned profile/calibration revisions and shows the
    # measured path instead of logical-only controls.
    config = rig.config()
    status, profile = rig.request(
        "PUT",
        f"/api/v3/displays/{ids[0]}",
        {
            "active_width_mm": 240,
            "active_height_mm": 150,
            "bezels": {"left": 5, "top": 5, "right": 5, "bottom": 5},
            "panel_pixels": None,
            "label": "Fixture tablet",
            "provenance": "datasheet",
        },
        if_match=config["etag"],
    )
    rig.check("Measured fixture profile accepted", status == 200, status, 200)
    config = rig.config()
    status, calibration = rig.request(
        "PUT",
        f"/api/v3/calibrations/{ids[0]}",
        {
            "profile_revision": profile["display"]["revision"],
            "viewport_width": 1280,
            "viewport_height": 800,
            "dpr": 1.0,
            "orientation": 0,
            "mode": "tab",
            "quarter_turn": 0,
            "panel_offset_mm": [0, 0],
            "mm_per_css": [0.1875, 0.1875],
            "anchor_edge": "top-left",
            "uncertainty_mm": 3,
            "method": "datasheet",
        },
        if_match=config["etag"],
    )
    rig.check("Measured fixture calibration accepted", status == 200, status, 200)
    config = rig.config()
    status, _ = rig.request(
        "PUT",
        "/api/v3/layout",
        {
            "bounds": {"x": 0, "y": 0, "width": 480, "height": 300},
            "slots": {
                ids[0]: {
                    "center_x_mm": 130,
                    "center_y_mm": 85,
                    "mount_angle": 0,
                    "nudge_x_mm": 0,
                    "nudge_y_mm": 0,
                    "profile_revision": profile["display"]["revision"],
                    "calibration_revision": calibration["calibration"]["revision"],
                    "participating": True,
                }
            },
            "sizing": {"mode": "fixed", "padding": 0},
        },
        if_match=config["etag"],
    )
    rig.check("Measured fixture layout accepted", status == 200, status, 200)
    rig.wait_config(lambda config: config["layout"].get("kind") == "physical")
    rig.task("Arrange")
    wait_until(page, "() => document.body.dataset.stageMode !== 'live' || document.querySelector('#stage-svg .slot')")
    select_stage_slot(rig, ids[0])
    page.wait_for_timeout(150)
    rig.check(
        "Measured mode hides logical-only controls and explains pinned measurements",
        page.locator("#logical-editor").is_hidden()
        and page.locator("#btn-match-shape").is_disabled()
        and "measured" in page.locator("#match-shape-note").inner_text().lower(),
        {
            "logical_hidden": page.locator("#logical-editor").is_hidden(),
            "match_disabled": page.locator("#btn-match-shape").is_disabled(),
            "note": page.locator("#match-shape-note").inner_text(),
        },
        {"logical_hidden": True, "match_disabled": True, "note": "measured path"},
    )
    measured_before = rig.config()["layout"]["slots"][ids[0]]
    drag_slot(rig, ids[0], 5, 0)
    measured_after = rig.config()["layout"]["slots"][ids[0]]
    rig.check(
        "Measured drag changes decimal millimetres only in the draft",
        measured_after == measured_before,
        {"before": measured_before, "durable_after": measured_after},
    )
    measured_draft = page.evaluate(
        "() => ({x: document.getElementById('slot-center-x')?.value, "
        "provenance: document.getElementById('tablet-provenance')?.textContent || ''})"
    )
    rig.check(
        "Measured draft exposes the edited millimetre centre and pinned provenance",
        measured_draft["x"] not in (None, "")
        and f"{measured_before['profile_revision']}" in measured_draft["provenance"],
        measured_draft,
        {"x": "number", "provenance": "pinned revision"},
    )
    page.click("#btn-apply")
    rig.wait_config(
        lambda config: config["layout"]["slots"][ids[0]]["center_x_mm"]
        != measured_before["center_x_mm"],
        timeout=15,
    )
    applied_measured = rig.config()["layout"]["slots"][ids[0]]
    rig.check(
        "Measured Apply preserves pinned profile and calibration revisions",
        applied_measured["profile_revision"] == measured_before["profile_revision"]
        and applied_measured["calibration_revision"] == measured_before["calibration_revision"],
        applied_measured,
        {"profile_revision": measured_before["profile_revision"],
         "calibration_revision": measured_before["calibration_revision"]},
    )


WAKE_LOCK_HELD = """
Object.defineProperty(navigator, 'wakeLock', {configurable: true, value: {
  request: async () => ({addEventListener() {}, release: async () => {}})
}});
"""
WAKE_LOCK_DENIED = """
Object.defineProperty(navigator, 'wakeLock', {configurable: true, value: {
  request: async () => { throw Object.assign(new Error('denied'), {name: 'NotAllowedError'}); }
}});
"""
WAKE_LOCK_UNSUPPORTED = """
Object.defineProperty(navigator, 'wakeLock', {configurable: true, value: undefined});
"""


def fleet_power(rig: Rig) -> None:
    page = rig.page
    if not require_hooks(rig, "fleet-power"):
        return
    clients = [
        rig.new_client(CLIENT_SPECS[0], 0, WAKE_LOCK_HELD),
        rig.new_client(CLIENT_SPECS[1], 1, WAKE_LOCK_DENIED),
        rig.new_client(CLIENT_SPECS[2], 2, WAKE_LOCK_UNSUPPORTED),
    ]
    ids = [device_id for _, device_id in clients]
    status, _ = rig.request("PUT", "/wall", {"width": 1200, "height": 800})
    rig.check("Fleet wall accepts three unequal clients", status == 200, status, 200)
    for index, device_id in enumerate(ids):
        status, _ = rig.request(
            "PUT",
            f"/devices/{device_id}/placement",
            {"x": (index % 2) * 600, "y": (index // 2) * 400, "w": 600, "h": 400},
        )
        rig.check(f"Fleet client {index + 1} placement accepted", status == 200, status, 200)
    rig.wait_config(
        lambda config: [config["runtime"]["devices"][device_id].get("wake_lock") for device_id in ids]
        == ["held", "denied", "unsupported"],
        timeout=20,
    )
    asset = rig.assets[0]
    status, _ = rig.put_scene({"type": "image", "asset": "sha256:" + asset["sha256"], "fit": "cover"})
    rig.check("Fleet fixture image scene accepted", status == 200, status, 200)
    rig.wait_config(
        lambda config: all(
            config["runtime"]["devices"][device_id]["render"].get("state") == "displayed"
            for device_id in ids
        ),
        timeout=20,
    )
    aggregate = _aggregate(page)
    rig.check(
        "Mixed power states do not change the confirmed paint count",
        aggregate["aggregate"]["showing"] == 3,
        aggregate["aggregate"],
        3,
    )

    rig.task("Tablets")
    wait_until(page, "(ids) => ids.every(id => document.querySelector('#device-list .dev-row[data-device-id=\"' + id + '\"]'))", arg=ids)
    wait_until(
        page,
        "(id) => [...document.querySelectorAll('#device-list .dev-row')].some(row => row.dataset.deviceId === id && row.dataset.status === 'displayed')",
        arg=ids[1],
    )
    denied_row = page.locator(f'#device-list .dev-row[data-device-id="{ids[1]}"]')
    held_row = page.locator(f'#device-list .dev-row[data-device-id="{ids[0]}"]')
    unsupported_row = page.locator(f'#device-list .dev-row[data-device-id="{ids[2]}"]')
    rig.check(
        "Roster keeps paint and wake readiness on separate facts",
        denied_row.get_attribute("data-status") == "displayed"
        and denied_row.get_attribute("data-power-state") == "denied"
        and denied_row.get_attribute("data-power-warning") == "true"
        and held_row.get_attribute("data-power-warning") == "false"
        and unsupported_row.get_attribute("data-power-state") == "unsupported",
        {
            "denied": denied_row.get_attribute("data-status"),
            "denied_power": denied_row.get_attribute("data-power-state"),
            "held_warning": held_row.get_attribute("data-power-warning"),
            "unsupported": unsupported_row.get_attribute("data-power-state"),
        },
        {"denied": "displayed", "denied_power": "denied", "held_warning": "false", "unsupported": "unsupported"},
    )
    denied_row.locator(".dev-pick").click()
    wait_until(page, "() => document.getElementById('device-sheet')?.open === true")
    rig.check(
        "Painted but denied power still renders an independent warning",
        "Power: denied" in page.locator("#tablet-evidence").inner_text()
        and page.locator("#tablet-evidence").get_attribute("data-power-warning") == "true"
        and page.locator("#tablet-recovery").is_visible()
        and "denied" in page.locator("#tablet-recovery").inner_text().lower()
        and "cannot wake" in page.locator("#tablet-recovery").inner_text().lower(),
        {
            "evidence": page.locator("#tablet-evidence").inner_text(),
            "warning": page.locator("#tablet-evidence").get_attribute("data-power-warning"),
            "recovery": page.locator("#tablet-recovery").inner_text(),
        },
        {"evidence": "Power: denied", "warning": "true", "recovery": "cannot wake"},
    )
    retry_title = page.locator("#tablet-retry-image").get_attribute("title")
    reconnect_title = page.locator("#tablet-reconnect").get_attribute("title")
    rig.check(
        "Retry image and Reconnect stay distinct and do not promise remote wake",
        retry_title != reconnect_title and "does not wake" in retry_title and "does not wake" in reconnect_title,
        {"retry": retry_title, "reconnect": reconnect_title},
        {"distinct": True, "remote_wake": False},
    )
    denied_slot = page.locator(f'#stage-svg .slot[data-device-id="{ids[1]}"]')
    rig.check(
        "Stage annotates the denied paint position without turning it into a paint failure",
        denied_slot.get_attribute("data-power-state") == "denied"
        and denied_slot.get_attribute("data-power-warning") == "true"
        and denied_slot.get_attribute("data-status") == "displayed",
        {
            "power": denied_slot.get_attribute("data-power-state"),
            "warning": denied_slot.get_attribute("data-power-warning"),
            "paint": denied_slot.get_attribute("data-status"),
        },
        {"power": "denied", "warning": "true", "paint": "displayed"},
    )

    requests_before = len(rig.requests)
    rig.open_disclosures(page.locator("#tablet-retry-image"))
    page.click("#tablet-retry-image")
    wait_until(page, "() => /Image retry requested/.test(document.getElementById('tablet-action-message').textContent)")
    page.click("#tablet-reconnect")
    wait_until(page, "() => /Reconnect requested/.test(document.getElementById('tablet-action-message').textContent)")
    posts = [row for row in rig.requests[requests_before:] if row["method"] == "POST"]
    rig.check(
        "Retry image and Reconnect call different endpoints with distinct receipts",
        {row["url"].rsplit("/", 1)[-1] for row in posts} == {"retry-image", "reconnect"},
        posts,
        {"endpoints": {"retry-image", "reconnect"}},
    )

    # A held browser report is not paint evidence. Close the held client and
    # verify both the real count and the state rule stay honest.
    held_context = clients[0][0].context
    rig.contexts.remove(held_context)
    held_context.close()
    rig.wait_config(lambda config: config["runtime"]["devices"][ids[0]]["online"] is False, timeout=20)
    page.wait_for_timeout(300)
    rig.task("Tablets")
    held_row = page.locator(f'#device-list .dev-row[data-device-id="{ids[0]}"]')
    rig.check(
        "An offline held report remains last known power and never a current paint claim",
        held_row.get_attribute("data-status") != "displayed"
        and held_row.get_attribute("data-power-state") == "held"
        and _aggregate(page)["aggregate"]["showing"] == 2,
        {
            "status": held_row.get_attribute("data-status"),
            "power": held_row.get_attribute("data-power-state"),
            "showing": _aggregate(page)["aggregate"]["showing"],
        },
        {"status": "offline/stale", "power": "held", "showing": 2},
    )
    page.evaluate("config => { window.__restorationConfig = config; }", rig.config())
    state_probe = page.evaluate(
        """id => {
            const config = JSON.parse(JSON.stringify(window.__restorationConfig));
            const now = performance.now();
            config.runtime.devices[id].wake_lock = 'held';
            config.runtime.devices[id].render.state = 'stale';
            config.runtime.devices[id].render.observed_mono = now - 20000;
            config.runtime.devices[id].render.age_ms = 20000;
            const observed = window.OperatorState.observeConfig(config, now);
            return window.OperatorState.tabletState(observed, id, now);
        }""",
        ids[0],
    )
    rig.check(
        "Held wake lock with stale paint is still not displayed",
        state_probe["showing"] is False,
        state_probe,
        {"showing": False},
        classification="state_rule_probe",
    )


def historical_forms(rig: Rig) -> None:
    page = rig.page
    ids = rig.place_logical_clients(2)
    rig.task("Tablets")
    page.locator(f'#device-list .dev-pick[data-device-id="{ids[0]}"]').click()
    wait_until(page, "() => document.getElementById('device-sheet')?.open === true")
    open_measurement_details(rig)

    page.fill("#profile-label", "Lobby left checked")
    page.fill("#profile-active-width", "123.4")
    page.fill("#profile-active-height", "80")
    page.fill("#profile-provenance", "datasheet")
    page.fill("#cal-method", "ruler across the active edge")
    page.select_option("#tablet-model", "manual")
    page.wait_for_timeout(80)
    rig.check(
        "Measurement edits mark their keyed forms dirty without a write",
        page.locator("#tablet-label-form").get_attribute("data-dirty") == "false"
        and page.locator("#profile-label").get_attribute("data-dirty") == "true"
        and not [row for row in rig.requests if row["method"] == "PUT"],
        {
            "profile_dirty": page.locator("#profile-label").get_attribute("data-dirty"),
            "writes": [row for row in rig.requests if row["method"] == "PUT"],
        },
        {"profile_dirty": "true", "writes": []},
    )

    page.click("#refresh-status")
    page.wait_for_timeout(250)
    for task in ("Images", "Settings"):
        rig.task(task)
    rig.check(
        "Dirty profile, calibration and model fields survive task changes and heartbeat refresh",
        page.input_value("#profile-label") == "Lobby left checked"
        and page.input_value("#profile-active-width") == "123.4"
        and page.input_value("#cal-method") == "ruler across the active edge"
        and page.input_value("#tablet-model") == "manual",
        {
            "label": page.input_value("#profile-label"),
            "active_width": page.input_value("#profile-active-width"),
            "cal_method": page.input_value("#cal-method"),
            "model": page.input_value("#tablet-model"),
        },
        {"label": "Lobby left checked", "active_width": "123.4",
         "cal_method": "ruler across the active edge", "model": "manual"},
    )

    rig.task("Tablets")
    page.locator(f'#device-list .dev-pick[data-device-id="{ids[1]}"]').click()
    wait_until(page, "() => document.getElementById('device-sheet')?.open === true")
    open_measurement_details(rig)
    wait_until(page, "() => document.getElementById('device-card-name')?.textContent !== '–'")
    rig.task("Tablets")
    page.locator(f'#device-list .dev-pick[data-device-id="{ids[0]}"]').click()
    wait_until(page, "() => document.getElementById('device-sheet')?.open === true")
    open_measurement_details(rig)
    page.wait_for_timeout(150)
    rig.check(
        "Selection changes retain each tablet's own dirty values",
        page.input_value("#profile-label") == "Lobby left checked"
        and page.input_value("#profile-active-width") == "123.4",
        {"label": page.input_value("#profile-label"), "active_width": page.input_value("#profile-active-width")},
        {"label": "Lobby left checked", "active_width": "123.4"},
    )

    writes_before = len([row for row in rig.requests if row["method"] == "PUT"])
    page.fill("#profile-label", "")
    page.locator("#btn-profile-save").focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    rig.check(
        "Keyboard submitting an empty name announces a named error and focuses the editable field",
        page.locator("#profile-msg").is_visible()
        and "Label" in page.locator("#profile-msg").inner_text()
        and page.evaluate("() => document.activeElement?.id") == "profile-label"
        and page.get_attribute("#profile-label", "aria-invalid") == "true"
        and len([row for row in rig.requests if row["method"] == "PUT"]) == writes_before,
        {
            "message": page.locator("#profile-msg").inner_text() if page.locator("#profile-msg").is_visible() else None,
            "focus": page.evaluate("() => document.activeElement?.id"),
            "invalid": page.get_attribute("#profile-label", "aria-invalid"),
        },
        {"message": "Label must be 1 to 80 characters.", "focus": "profile-label", "invalid": "true"},
    )

    page.click("#discard-profile")
    page.wait_for_timeout(120)
    rig.check(
        "Discarding one dirty group leaves the other retained model choice",
        page.locator("#profile-label").get_attribute("data-dirty") == "false"
        and page.input_value("#tablet-model") == "manual"
        and page.input_value("#profile-label") != "",
        {
            "profile_dirty": page.locator("#profile-label").get_attribute("data-dirty"),
            "model": page.input_value("#tablet-model"),
            "label": page.input_value("#profile-label"),
        },
        {"profile_dirty": "false", "model": "manual", "label": "restored"},
    )

    page.set_viewport_size({"width": 390, "height": 844})
    trigger = page.locator(f'#device-list .dev-pick[data-device-id="{ids[0]}"]')
    rig.task("Tablets")
    trigger.click()
    wait_until(page, "() => document.getElementById('device-sheet')?.open === true")
    page.keyboard.press("Escape")
    wait_until(page, "() => document.getElementById('device-sheet')?.open !== true")
    rig.check(
        "The native tablet dialog stays usable and Escape restores a visible trigger",
        page.evaluate(
            "() => { const e = document.activeElement; return !!e && e.isConnected && !e.hidden && e.getClientRects().length > 0; }"
        ),
        page.evaluate("() => document.activeElement?.className"),
        "visible connected trigger",
    )


def historical_membership(rig: Rig) -> None:
    page = rig.page
    rig.task("Arrange")
    page.locator("#grid-order").wait_for(state="attached")
    rig.check(
        "Arrangement starts with no forced reservation before the first live join",
        not page.locator("#grid-order [data-device-id]").count(),
        page.locator("#grid-order [data-device-id]").count(),
        0,
    )
    first_page, first_id = rig.new_client(CLIENT_SPECS[0], 0)
    rig.wait_config(lambda config: first_id in config["runtime"]["devices"])
    wait_until(
        page,
        "(id) => !!document.querySelector('#grid-order [data-device-id=\"' + id + '\"]')",
        arg=first_id,
    )
    rig.open_disclosures(page.locator("#grid-order"))
    row = page.locator(f'#grid-order [data-device-id="{first_id}"]')
    rig.check(
        "A first live join becomes included before any user freeze with a fresh viewport aspect",
        row.locator('input[type="checkbox"]').is_checked()
        and row.get_attribute("data-size-source") == "viewport"
        and row.get_attribute("data-membership-source") == "automatic"
        and row.locator('input[data-field="w"]').input_value() == "160",
        {
            "included": row.locator('input[type="checkbox"]').is_checked(),
            "size_source": row.get_attribute("data-size-source"),
            "membership": row.get_attribute("data-membership-source"),
            "width": row.locator('input[data-field="w"]').input_value(),
        },
        {"included": True, "size_source": "viewport", "membership": "automatic", "width": "160"},
    )
    row.locator('input[type="checkbox"]').uncheck()
    page.wait_for_timeout(80)
    rig.check(
        "An explicit exclusion is remembered as an operator choice",
        not row.locator('input[type="checkbox"]').is_checked()
        and row.get_attribute("data-membership-source") == "operator",
        row.get_attribute("data-membership-source"),
        "operator",
    )
    first_page.reload()
    wait_until(first_page, "() => document.querySelector('#status')?.dataset.state === 'connected'")
    rig.wait_config(lambda config: config["runtime"]["devices"][first_id]["online"] is True)
    page.wait_for_timeout(200)
    row = page.locator(f'#grid-order [data-device-id="{first_id}"]')
    rig.check(
        "A reconnect does not overwrite the intentional exclusion",
        not row.locator('input[type="checkbox"]').is_checked()
        and row.get_attribute("data-membership-source") == "operator",
        {
            "included": row.locator('input[type="checkbox"]').is_checked(),
            "membership": row.get_attribute("data-membership-source"),
        },
        {"included": False, "membership": "operator"},
    )

    second_page, second_id = rig.new_client(CLIENT_SPECS[1], 1)
    rig.wait_config(lambda config: second_id in config["runtime"]["devices"])
    wait_until(
        page,
        "(id) => !!document.querySelector('#grid-order [data-device-id=\"' + id + '\"]')",
        arg=second_id,
    )
    second_row = page.locator(f'#grid-order [data-device-id="{second_id}"]')
    rig.check(
        "A join after membership editing requires an explicit Include",
        not second_row.locator('input[type="checkbox"]').is_checked()
        and second_row.get_attribute("data-available") == "true"
        and second_row.get_by_role("button", name=re.compile("^Include ")).is_visible(),
        {
            "included": second_row.locator('input[type="checkbox"]').is_checked(),
            "available": second_row.get_attribute("data-available"),
            "include_visible": second_row.get_by_role("button", name=re.compile("^Include ")).is_visible(),
        },
        {"included": False, "available": "true", "include_visible": True},
    )
    second_row.get_by_role("button", name=re.compile("^Include ")).click()
    row.locator('input[type="checkbox"]').check()
    page.wait_for_timeout(80)
    page.click("#grid-2x2")
    page.wait_for_timeout(80)
    page.check("#grid-holes")
    page.click("#grid-preview")
    wait_until(page, "() => /Rebuild preview explicitly/.test(document.getElementById('grid-message').textContent)")
    rig.check(
        "A later join requires an explicit rebase before preview",
        page.locator("#grid-rebuild").is_visible(),
        page.locator("#grid-message").inner_text(),
        "Rebuild preview explicitly",
    )
    page.once("dialog", lambda dialog: dialog.accept())
    page.click("#grid-rebuild")
    wait_until(page, "() => /tablets ·/.test(document.getElementById('grid-message').textContent)")
    page.click("#btn-apply")
    rig.wait_config(
        lambda config: all(device_id in config["layout"]["placements"] for device_id in (first_id, second_id)),
        timeout=15,
    )
    rig.check(
        "The reviewed membership applies one arrangement with both live tablets",
        all(device_id in rig.config()["layout"]["placements"] for device_id in (first_id, second_id)),
        rig.config()["layout"]["placements"],
        "both placements",
    )

    # Offline reservations stay until deliberately removed; removing the last
    # active tablet does not erase the registration or a reserved position.
    second_context = second_page.context
    rig.contexts.remove(second_context)
    second_context.close()
    rig.wait_config(lambda config: config["runtime"]["devices"][second_id]["online"] is False, timeout=20)
    rig.task("Tablets")
    page.locator(f'#device-list .dev-pick[data-device-id="{second_id}"]').click()
    wait_until(page, "() => document.getElementById('device-sheet')?.open === true")
    page.on("dialog", lambda dialog: dialog.accept())
    rig.open_disclosures(page.locator("#tablet-remove"))
    page.click("#tablet-remove")
    rig.wait_config(
        lambda config: second_id not in config["layout"]["placements"]
        and first_id in config["layout"]["placements"],
        timeout=15,
    )
    rig.check(
        "Removing one active tablet retains the other reserved position and both registrations",
        rig.config()["layout"]["placements"].get(first_id) is not None
        and second_id not in rig.config()["layout"]["placements"]
        and second_id in rig.config()["runtime"]["devices"],
        {
            "placements": rig.config()["layout"]["placements"],
            "registered": second_id in rig.config()["runtime"]["devices"],
        },
        {"first_reserved": True, "second_removed": True, "second_registered": True},
    )
    page.locator(f'#device-list .dev-pick[data-device-id="{first_id}"]').click()
    wait_until(page, "() => document.getElementById('device-sheet')?.open === true")
    rig.open_disclosures(page.locator("#tablet-remove"))
    page.click("#tablet-remove")
    rig.wait_config(lambda config: not config["layout"]["placements"], timeout=15)
    rig.check(
        "A deliberate last-tablet removal succeeds, keeps registration and clears stale focus",
        not rig.config()["layout"]["placements"]
        and first_id in rig.config()["runtime"]["devices"]
        and page.evaluate(
            "() => { const e = document.activeElement; return !!e && e.isConnected && !e.hidden && e.getClientRects().length > 0; }"
        ),
        {
            "placements": rig.config()["layout"]["placements"],
            "registered": first_id in rig.config()["runtime"]["devices"],
            "focus": page.evaluate("() => document.activeElement?.id || document.activeElement?.className"),
        },
        {"placements": {}, "registered": True, "focus": "visible"},
    )


def historical_uncertainty(rig: Rig) -> None:
    page = rig.page
    ids = rig.place_logical_clients(2)
    rig.task("Arrange")
    page.locator("#arrange-membership-summary").wait_for(state="visible")
    rig.open_disclosures(page.locator("#grid-rows"))
    page.fill("#grid-rows", "1")
    page.fill("#grid-columns", "1")
    page.dispatch_event("#grid-columns", "change")
    page.click("#grid-preview")
    wait_until(page, "() => document.getElementById('grid-message').textContent.length > 0")
    rig.check(
        "A refused grid retains the typed rows and columns and explains the refusal",
        "exactly 1" in page.locator("#grid-message").inner_text().lower()
        and "empty trailing cells" in page.locator("#grid-message").inner_text().lower()
        and page.input_value("#grid-rows") == "1"
        and page.input_value("#grid-columns") == "1",
        {
            "message": page.locator("#grid-message").inner_text(),
            "rows": page.input_value("#grid-rows"),
            "columns": page.input_value("#grid-columns"),
        },
        {"message": "capacity or empty cells", "rows": "1", "columns": "1"},
    )
    page.fill("#grid-columns", "2")
    page.dispatch_event("#grid-columns", "change")
    page.click("#grid-preview")
    wait_until(page, "() => /2 tablets ·/.test(document.getElementById('grid-message').textContent)")
    rig.check(
        "A valid manual grid previews without rewriting the typed fields",
        page.input_value("#grid-rows") == "1" and page.input_value("#grid-columns") == "2",
        {"rows": page.input_value("#grid-rows"), "columns": page.input_value("#grid-columns")},
        {"rows": "1", "columns": "2"},
    )
    page.click("#btn-cancel")
    wait_until(page, "() => document.body.dataset.outputDirty === 'false'")

    rig.task("Images")
    wait_until(page, "() => document.querySelectorAll('#image-gallery > li').length === 1")
    asset_id = page.locator("#image-gallery > li").first.get_attribute("data-asset-id")
    before_scene = rig.config()
    lost_scene: list[bool] = []

    def lose_scene(route: Any) -> None:
        if lost_scene:
            route.continue_()
            return
        lost_scene.append(True)
        route.fetch()
        route.abort()

    page.route("**/api/v3/scene", lose_scene)
    page.locator("#image-gallery > li .image-choice-button").first.click()
    wait_until(page, "() => !document.getElementById('show-image').disabled")
    page.click("#show-image")
    wait_until(page, "() => !document.getElementById('command-uncertainty').hidden", timeout=10)
    committed = rig.config()
    rig.check(
        "A lost response is reported as uncertain while the durable commit is visible",
        "may have completed" in page.locator("#command-uncertainty").inner_text().lower()
        and committed["scene"]["content"].get("asset") == asset_id
        and committed["revision"] > before_scene["revision"],
        {
            "banner": page.locator("#command-uncertainty").inner_text(),
            "asset": committed["scene"]["content"].get("asset"),
            "revision": [before_scene["revision"], committed["revision"]],
        },
        {"banner": "may have completed", "asset": asset_id, "revision": "increased"},
    )
    page.click("#refresh-command-status")
    wait_until(page, "() => document.getElementById('command-uncertainty').hidden")
    rig.check(
        "Refresh status reconciles the actual durable result and clears the uncertainty latch",
        page.locator("#command-uncertainty").is_hidden()
        and rig.config()["scene"]["content"].get("asset") == asset_id,
        {"hidden": page.locator("#command-uncertainty").is_hidden(),
         "asset": rig.config()["scene"]["content"].get("asset")},
        {"hidden": True, "asset": asset_id},
    )
    page.unroute("**/api/v3/scene", lose_scene)

    # Upload ambiguity uses the real controller XHR and a lost response after
    # the server published the asset.
    page.click("#add-image")
    page.locator("#upload-form").wait_for(state="visible")
    lost_upload: list[bool] = []

    def lose_upload(route: Any) -> None:
        if lost_upload:
            route.continue_()
            return
        lost_upload.append(True)
        response = route.fetch(post_data=Path(upload_source).read_bytes())
        rig.check(
            "The intercepted upload publishes its selected bytes before losing the response",
            response.status == 201,
            {"status": response.status},
            {"status": 201},
            classification="transport_fault_setup",
        )
        route.abort()

    upload_source = next(
        group["files"][0]["path"] for group in rig.fixtures if group["count"] == 8
    )
    page.route("**/uploads*", lose_upload)
    page.set_input_files("#upload-file", upload_source)
    upload_before = rig.config()
    page.click("#upload-submit")
    wait_until(
        page,
        "() => /uncertain/i.test(document.getElementById('upload-message').textContent)",
        timeout=15,
    )
    rig.check(
        "A lost upload response requires a real inventory refresh before retry",
        "Refresh images" in page.locator("#upload-message").inner_text()
        and page.locator("#upload-submit").is_disabled()
        and rig.config()["scene"] == upload_before["scene"],
        {
            "message": page.locator("#upload-message").inner_text(),
            "submit_disabled": page.locator("#upload-submit").is_disabled(),
            "scene_unchanged": rig.config()["scene"] == upload_before["scene"],
        },
        {"message": "Refresh images", "submit_disabled": True, "scene_unchanged": True},
    )
    page.unroute("**/uploads*", lose_upload)
    page.click("#refresh-images")
    wait_until(page, "() => document.querySelectorAll('#image-gallery > li').length === 2")
    rig.check(
        "Inventory refresh reveals the published upload, re-enables retry and shows nothing automatically",
        page.locator("#upload-submit").is_enabled()
        and rig.config()["scene"] == upload_before["scene"]
        and page.locator("#image-gallery > li").count() == 2,
        {
            "submit_enabled": page.locator("#upload-submit").is_enabled(),
            "scene_unchanged": rig.config()["scene"] == upload_before["scene"],
            "gallery": page.locator("#image-gallery > li").count(),
        },
        {"submit_enabled": True, "scene_unchanged": True, "gallery": 2},
    )

    # Redo is an output command: a competing image proposal must be resolved
    # before redo can restore the arrangement.
    rig.task("Arrange")
    wait_until(page, "() => document.getElementById('draft-resolution')?.open === true")
    page.click("#resolve-discard")
    wait_until(page, "() => document.body.dataset.task === 'arrange'")
    select_stage_slot(rig, ids[0])
    set_logical_snap(rig, False, 1)
    original = rig.config()["layout"]["placements"][ids[0]]
    drag_slot(rig, ids[0], 10, 0)
    page.click("#btn-undo")
    wait_until(
        page,
        "(expected) => { const slot = document.querySelector('#stage-svg .slot[data-device-id=\"' + expected.id + '\"] .operator-body-outline'); "
        "return slot && Number(slot.getAttribute('x')) === expected.x; }",
        arg={"id": ids[0], "x": original["x"]},
    )
    rig.task("Images")
    page.locator("#image-gallery > li .image-choice-button").nth(1).click()
    wait_until(page, "() => document.body.dataset.outputDirty === 'true'")
    wait_until(page, "() => !document.getElementById('show-image').disabled")
    rig.task("Arrange")
    wait_until(page, "() => document.getElementById('draft-resolution')?.open === true")
    rig.check(
        "A task switch with a competing image proposal opens current-owner resolution",
        "image preview has not been shown" in page.locator("#draft-resolution-text").inner_text().lower(),
        page.locator("#draft-resolution-text").inner_text(),
        "image preview has not been shown",
    )
    page.click("#resolve-stay")
    wait_until(page, "() => document.getElementById('draft-resolution')?.open !== true")
    rig.check(
        "Stay preserves both the image preview and the arrangement history",
        page.locator("#image-preview-controls").is_visible()
        and page.evaluate("() => document.body.dataset.outputDirty === 'true'")
        and page.evaluate("() => document.body.dataset.task === 'images'"),
        {
            "preview": page.locator("#image-preview-controls").is_visible(),
            "dirty": page.evaluate("() => document.body.dataset.outputDirty"),
            "task": page.evaluate("() => document.body.dataset.task"),
        },
        {"preview": True, "dirty": "true", "task": "images"},
    )
    rig.task("Arrange")
    wait_until(page, "() => document.getElementById('draft-resolution')?.open === true")
    page.click("#resolve-discard")
    wait_until(page, "() => document.body.dataset.task === 'arrange'")
    rig.check(
        "Discard scopes to the image proposal and leaves the arrangement history intact",
        page.evaluate("() => document.body.dataset.outputDirty === 'false'")
        and draft_placement(page, ids[0])["x"] == original["x"]
        and not page.locator("#btn-redo").is_hidden(),
        {
            "dirty": page.evaluate("() => document.body.dataset.outputDirty"),
            "x": draft_placement(page, ids[0])["x"],
            "redo_hidden": page.locator("#btn-redo").is_hidden(),
        },
        {"dirty": "false", "x": original["x"], "redo_hidden": False},
    )
    page.click("#btn-redo")
    wait_until(
        page,
        "(expected) => { const slot = document.querySelector('#stage-svg .slot[data-device-id=\"' + expected.id + '\"] .operator-body-outline'); "
        "return slot && Number(slot.getAttribute('x')) === expected.x; }",
        arg={"id": ids[0], "x": original["x"] + 10},
    )
    rig.check(
        "After the competing proposal is discarded, redo restores the current owner's arrangement",
        draft_placement(page, ids[0])["x"] == original["x"] + 10,
        draft_placement(page, ids[0]),
        {"x": original["x"] + 10},
    )
    page.click("#btn-cancel")
    wait_until(page, "() => document.body.dataset.outputDirty === 'false'")


SCENARIO_BODIES = {
    "gallery-focus": gallery_focus,
    "recovery-sheet": recovery_sheet,
    "library-composer": library_composer,
    "scene-paint": scene_paint,
    "fit-feedback": fit_feedback,
    "geometry-tools": geometry_tools,
    "fleet-power": fleet_power,
    "historical-forms": historical_forms,
    "historical-membership": historical_membership,
    "historical-uncertainty": historical_uncertainty,
}


# ---------------------------------------------------------------------------
# Scenario execution
# ---------------------------------------------------------------------------


def run_scenario(
    out: Path,
    name: str,
    source_root: Path,
    identity: dict[str, Any],
) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=False)
    rig = Rig(out, name, source_root, identity)
    interrupted = False
    failure = None
    with sync_playwright() as playwright:
        try:
            rig.setup(playwright)
            rig.check(
                "Private server originated from the selected source root",
                rig.server_cwd == str(Path(source_root).resolve()),
                {"server_cwd": rig.server_cwd, "manifest_source_root": rig.identity["application"]["source_root"]},
                str(Path(source_root).resolve()),
                fatal=False,
            )
            SCENARIO_BODIES[name](rig)
            rig.check("No JavaScript page exceptions", not rig.page_errors, rig.page_errors, [], fatal=False)
        except Exception as error:
            interrupted = True
            failure = {
                "name": "scenario interrupted",
                "pass": False,
                "expected": "journey reaches all assertions",
                "actual": repr(error),
                "traceback": traceback.format_exc(),
                "classification": "driver_or_product_interruption_unresolved",
            }
            rig.results.append(failure)
            _write_json(out / "failure.json", failure)
            print(f"FAIL {name} {error}", flush=True)
        finally:
            cleanup = rig.close()
    passed = scenario_pass(rig.results, cleanup, interrupted)
    report = {
        "scenario": name,
        "status": "pass" if passed else "fail",
        "pass": passed,
        "checks": len(rig.results),
        "failures": [row for row in rig.results if not row["pass"]],
        "assertions": rig.results,
        "interrupted": interrupted,
        "artifacts": str(out),
        "source_root": str(Path(source_root).resolve()),
        "fixtures": rig.fixtures,
        "clients": rig.clients,
        "browser": {
            "engine": "chromium",
            "launch": "playwright-default-headless",
            "version": rig.browser_version,
        },
        "cleanup": cleanup,
        "limitations": LIMITATIONS,
    }
    _write_json(out / "scenario.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Implemented: "
        + ", ".join(IMPLEMENTED)
        + ". Explicitly incomplete: "
        + ", ".join(INCOMPLETE),
    )
    parser.add_argument("--artifacts", required=True, type=Path, help="new directory outside the repository")
    parser.add_argument(
        "--scenario",
        choices=("all", *SCENARIOS),
        default="all",
        help="one registry scenario or all of them",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=None,
        help="read-only application source to serve; defaults to this checkout",
    )
    args = parser.parse_args(argv)
    selected = tuple(SCENARIOS) if args.scenario == "all" else (args.scenario,)
    single_implemented = len(selected) == 1 and SCENARIOS[selected[0]]["status"] == "implemented"
    try:
        source_root = resolve_source_root(args.source_root)
        artifacts = new_artifacts(
            args.artifacts, source_root, create=not single_implemented
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))

    application_before = application_identity(source_root)
    driver = driver_identity()
    reports: list[dict[str, Any]] = []
    for name in selected:
        entry = SCENARIOS[name]
        if entry["status"] != "implemented":
            reports.append(incomplete_report(name))
            continue
        target = artifacts / name if args.scenario == "all" else artifacts
        reports.append(
            run_scenario(
                target,
                name,
                source_root,
                {"application": application_before, "driver": driver},
            )
        )

    application_after = application_identity(source_root)
    source_unchanged = (
        application_before["application_sha256"] == application_after["application_sha256"]
    )
    incomplete = [report for report in reports if report["status"] == "incomplete"]
    passed = (
        source_unchanged
        and not incomplete
        and all(report["pass"] for report in reports)
    )
    result = {
        "task": TASK_ID,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scenario": args.scenario,
        "command": [sys.executable, *sys.argv],
        "cwd": os.getcwd(),
        "source_root": str(source_root),
        "source": {
            "application_before": application_before,
            "application_after": application_after,
            "application_unchanged": source_unchanged,
            "driver": driver,
        },
        "registry": [
            {
                "name": entry["name"],
                "status": entry["status"],
                "owner": entry["owner"],
                "reason": entry["reason"],
                "known_baseline_failure": entry["known_baseline_failure"],
            }
            for entry in SCENARIO_ENTRIES
        ],
        "fixtures": reports[0].get("fixtures", []) if reports and reports[0].get("fixtures") else [],
        "fixture_coverage": {
            "generated_groups": list(FIXTURE_COUNTS),
            "served_by_scenario": dict(SCENARIO_FIXTURES),
            "note": FIXTURE_COVERAGE_NOTE,
        },
        "reports": reports,
        "pass": passed,
        "acceptance_complete": False,
        "software_complete": passed and not incomplete,
        "incomplete": incomplete,
        "limitations": LIMITATIONS,
    }
    _write_json(artifacts / "results.json", result)
    passed_checks = sum(report.get("checks", 0) for report in reports if report["status"] != "incomplete")
    failed_checks = sum(len(report.get("failures", [])) for report in reports)
    print(
        f"restoration {args.scenario}: {passed_checks} checks, "
        f"{failed_checks} failures, {len(incomplete)} incomplete; "
        f"report {artifacts / 'results.json'}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
