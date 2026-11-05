"""Isolated shipped-client acceptance. --artifacts must name a new directory."""

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
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
import urllib.request

from PIL import Image, ImageDraw
from playwright.sync_api import expect, sync_playwright

from _redesign_edge_cases import TASK_TABS, HeldResponse, save_name, second_operator, task_tab

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from deploy.hotspot import Settings, backend_environment  # noqa: E402

SCENARIOS = ("first-wall", "races", "recovery", "parity", "responsive", "corrections", "edge-cases")
APPLICATION_BASE = "295cb61220677a3a42dbcc7812c3a267c810864b"
MANDATORY_OPEN = [
    "Physical pointer drag, explicit snap-step behavior, Clear cancellation, and complete offline/reconnect command variants.",
    "Batch uncertain completion, selection changes during delayed batch, and incompatible/mixed model groups.",
    "Stale fallback roster/diagnostic GET, old mutation response after newer authority, and old paint acknowledgement injection.",
    "Upload 120-second timeout, inventory refresh ordering, stale saved-scene refusal, and missing live asset client failure.",
    "Different-hardware replacement, exact changed-snapshot/connection guard refusal, and reconnect-after-Forget-review refusal.",
    "Native Tab-order/dialog containment, invalid-submit field focus and reorder-boundary focus in the automated browser.",
    "Named desktop/phone visual states, sampled hover/focus/SVG/non-text contrast, missing thumbnails and labelled text/CSS zoom emulation.",
    "Generated Caddy/direct admission proof is owned by C/root; this driver composes environment only and does not repeat that proof.",
    "Controller query/hash forwarding, readable DOM recovery, and immediate first-preview labels.",
    "Integrated durable500, image/history ownership, all incompatible resolver intents, and refused-grid manual editing regressions.",
]
SOFTWARE_GROUPS = (
    ("physical-pointer", "snap-spacing", "command-variants", "parity"),
    ("batch-uncertain", "batch-selection", "mixed-models", "model-batch"),
    ("races", "stale-reads", "late-mutation", "old-paint"),
    (
        "upload-timeout",
        "inventory-order",
        "stale-scene",
        "missing-live",
        "image-negatives",
        "upload-postpublication",
        "upload-unreadable",
    ),
    (
        "different-hardware",
        "replacement-digest",
        "replacement-connection",
        "forget-reconnect",
        "conflict-lifecycle",
    ),
    ("native-keyboard", "responsive"),
    ("visual-states", "loading-workspace", "interaction-contrast", "responsive"),
    (),
    ("entry-recovery", "first-wall"),
    ("durable-uncertainty", "history-ownership", "refused-grid"),
)
ENVIRONMENT_OPEN = [
    "Native operating-system IME and screen-reader smoke were not driven.",
    "Native 200%/400% browser zoom was not demonstrated; CSS zoom/text enlargement is separately labelled emulation.",
    "Real hardware, optical alignment/bezel accuracy, sleep, TLS/live ingress, video and prolonged soak remain unverified.",
]
BROWSER_LIMIT = {
    "chrome_devtools": "Could not find Google Chrome executable for channel stable at /opt/google/chrome/chrome.",
    "playwright_mcp": "Browser chrome-for-testing is not installed; expected /var/home/oak/.cache/ms-playwright/chromium-1252/chrome-linux64/chrome.",
    "browser_harness_doctor": "daemon alive FAIL; active browser connections 0; Chrome running",
    "inspected_session": "DISPLAY=:0; WAYLAND_DISPLAY=wayland-0; XDG_SESSION_TYPE=wayland; unchanged",
    "fallback": "Authorized isolated project Python Playwright, cached Chromium; never CDP attach",
    "observed_at": "2026-11-02",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


DRIVER_BYTES = {
    str(path.relative_to(ROOT)): path.read_bytes()
    for path in [
        *Path(__file__).parent.glob("*redesign*.py"),
        Path(__file__).with_name("operator_accessibility.py"),
        *ROOT.glob("tests/test_redesign*.py"),
    ]
}


def request_body(request):
    data = request.post_data_buffer
    if data is None:
        return None
    if "json" in request.headers.get("content-type", ""):
        return data.decode("utf-8")
    return {
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "content_type": request.headers.get("content-type"),
    }


def git(*args, root=ROOT):
    return subprocess.check_output(
        ["rtk", "proxy", "git", *args], cwd=root, text=True
    ).strip()


def source_identity(root=ROOT):
    files = (
        subprocess.check_output(
            [
                "rtk",
                "proxy",
                "git",
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            cwd=root,
        )
        .decode()
        .split("\0")
    )
    hashes = {
        name: digest(root / name)
        for name in sorted(set(files))
        if name and (root / name).is_file()
    }
    combined = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    app_hashes = {
        name: value
        for name, value in hashes.items()
        if name.startswith(("frontend/", "tabletwall/", "deploy/")) or name == "main.py"
    }
    return {
        "head": git("rev-parse", "HEAD", root=root),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD", root=root),
        "dirty_status": git("status", "--porcelain=v1", root=root),
        "source_sha256": combined,
        "source_hashes": hashes,
        "application_hashes": app_hashes,
        "application_sha256": hashlib.sha256(
            json.dumps(app_hashes, sort_keys=True).encode()
        ).hexdigest(),
        "driver_hashes": {
            str(p.relative_to(ROOT)): digest(p)
            for p in [
                *Path(__file__).parent.glob("*redesign*.py"),
                Path(__file__).with_name("operator_accessibility.py"),
            ]
        },
    }


def external_ingress_proof(path=None):
    path = Path(
        path or "/tmp/tablet-wall-favicon-ingress-tys6crky/ingress-manifest.json"
    )
    result = {
        "classification": "external_root_evidence",
        "path": str(path),
        "verified": False,
    }
    try:
        manifest = json.loads(path.read_text())
        matching = {
            name: (ROOT / name).is_file() and digest(ROOT / name) == value
            for name, value in manifest["source_sha256"].items()
        }
        allowlist = (
            digest(ROOT / "deploy/tablet-routes.caddy") == manifest["allowlist_sha256"]
        )
        requests = manifest["requests"]
        tablet_origin = f"http://127.0.0.1:{manifest['tablet_port']}"
        denials = sum(
            row["origin"] == tablet_origin and row["status"] == 403 for row in requests
        )
        favicon = [
            row
            for row in requests
            if row["path"].endswith("favicon.svg") and row["status"] == 200
        ]
        favicon_head = [row for row in favicon if row["method"] == "HEAD"]
        uploads = [
            row
            for row in requests
            if row["path"].startswith("/uploads") and row["status"] == 201
        ]
        result.update(
            manifest_sha256=digest(path),
            source_matches=matching,
            allowlist_matches=allowlist,
            tablet_denials=denials,
            favicon_200=favicon,
            favicon_head_200=favicon_head,
            exact_favicon_head_proven=bool(favicon_head),
            upload_201=uploads,
            cleanup=manifest["cleanup"],
            caddy_version=manifest["caddy_version"],
        )
        result["verified"] = (
            bool(matching)
            and all(matching.values())
            and allowlist
            and manifest.get("passed") is True
            and denials >= 124
            and bool(favicon)
            and bool(uploads)
            and all(manifest["cleanup"].values())
            and manifest["state_before_denials"] == manifest["state_after_denials"]
        )
    except (OSError, KeyError, ValueError) as error:
        result["error"] = repr(error)
    return result


def coverage_report(reports, ingress):
    by_name = {row["scenario"]: row for row in reports}
    groups = []
    for description, required in zip(MANDATORY_OPEN, SOFTWARE_GROUPS):
        unrun = [name for name in required if name not in by_name]
        issues = [
            name for name in required if name in by_name and not by_name[name]["pass"]
        ]
        passed = (
            not unrun
            and not issues
            and (
                bool(required)
                or ingress["verified"]
                and ingress.get("exact_favicon_head_proven", False)
            )
        )
        groups.append(
            {
                "requirement": description,
                "required_scenarios": required,
                "status": "PASS" if passed else "ISSUES" if issues else "BLOCKED",
                "unrun": unrun,
                "issues": issues,
                "evidence": {
                    name: by_name[name]["artifacts"]
                    for name in required
                    if name in by_name
                },
                **({"external_evidence": ingress} if not required else {}),
            }
        )
    return groups


def new_artifacts(path):
    path = Path(path).absolute()
    path.mkdir(parents=True, exist_ok=False)
    return path.resolve()


def child_environment(private, port, uploads):
    settings = Settings(
        interface="private-fixture-unused",
        data_dir=str(private),
        backend_port=port,
        tablet_port=port,
    )
    inherited = {
        k: v for k, v in os.environ.items() if k.startswith(("TABLET_WALL", "WALL_"))
    }
    try:
        for key in inherited:
            del os.environ[key]
        env = backend_environment(
            settings,
            "127.0.0.1",
            private,
            "Synthetic QA network",
            operator_uploads=uploads,
        )
    finally:
        os.environ.update(inherited)
    env["TABLET_WALL_BACKUP_DIR"] = str(private / "backups")
    for key, name in (
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_RUNTIME_DIR", "run"),
    ):
        directory = private / "xdg" / name
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        env[key] = str(directory)
    return env


def process_group_members(group):
    result = {}
    for path in Path("/proc").glob("[0-9]*/stat"):
        try:
            fields = path.read_text().rsplit(") ", 1)[1].split()
            if int(fields[2]) == group and fields[0] != "Z":
                result[int(path.parent.name)] = (
                    (path.parent / "cmdline")
                    .read_bytes()
                    .replace(b"\0", b" ")
                    .decode(errors="replace")
                )
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return result


def wait_until(predicate, pump, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        pump(50)
    raise AssertionError(f"bounded wait expired after {timeout}s")


def owned_browser_processes():
    rows = {}
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            status = (proc / "status").read_text()
            parent = int(re.search(r"^PPid:\s+(\d+)", status, re.M)[1])
            rows[int(proc.name)] = (
                parent,
                (proc / "cmdline")
                .read_bytes()
                .replace(b"\0", b" ")
                .decode(errors="replace"),
            )
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    owned = {os.getpid()}
    while True:
        new = {pid for pid, (parent, _) in rows.items() if parent in owned} - owned
        if not new:
            break
        owned.update(new)
    return {
        pid: cmd
        for pid, (_, cmd) in rows.items()
        if pid in owned and re.search(r"/(chrome|chromium)[^/ ]*/|/chrome(?: |$)", cmd)
    }


class Rig:
    def __init__(self, out, scenario, uploads=True, keyboard=False):
        self.out, self.scenario, self.uploads, self.keyboard = (
            out,
            scenario,
            uploads,
            keyboard,
        )
        self.results, self.errors, self.console, self.network = [], [], [], []
        self.requests, self.responses, self.contexts, self.tablets, self.events = (
            [],
            [],
            [],
            [],
            [],
        )
        self.server = self.browser = self.page = None
        self.induced = []
        self.dialog_accept = True
        self.manifest = {
            **source_identity(),
            "baseline_application_commit": APPLICATION_BASE,
            "application_matches_baseline": not git(
                "diff",
                APPLICATION_BASE,
                "--",
                "frontend",
                "tabletwall",
                "deploy",
                "main.py",
            ),
            "command": [sys.executable, *sys.argv],
            "cwd": str(ROOT),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scenario": scenario,
            "evidence": "Software simulation with actual shipped UI/clients and labelled fault injection",
            "browser_tool_limitations": BROWSER_LIMIT,
            "operator_actions": [],
            "clients": [],
            "render_modes": [],
            "limits": [],
            "loaded_driver_hashes": {
                name: hashlib.sha256(value).hexdigest()
                for name, value in DRIVER_BYTES.items()
            },
        }
        driver_copy = self.out / "driver"
        driver_copy.mkdir(exist_ok=True)
        for name, value in DRIVER_BYTES.items():
            target = driver_copy / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)

    def write(self, name, value):
        (self.out / name).write_text(
            json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n"
        )

    def config(self):
        with urllib.request.urlopen(
            self.base + "/api/v3/config", timeout=3
        ) as response:
            result = json.load(response)
            return result

    def shot(self, page, name):
        name = re.sub(r"[^\w.-]+", "-", name)
        viewport = page.viewport_size
        state = self.config()
        asset = str(state["scene"]["content"].get("asset", "no-image"))[-10:]
        stem = f"{self.scenario}-{name}-{viewport['width']}x{viewport['height']}-r{state['revision']}-{state['layout']['kind']}-{asset}"
        self.manifest["render_modes"].append(
            {
                "artifact": stem,
                "url": page.url,
                "viewport": viewport,
                **page.evaluate("""()=>({DPR:devicePixelRatio,root_font:getComputedStyle(document.documentElement).fontSize,
            css_zoom:getComputedStyle(document.documentElement).zoom,visual_scale:visualViewport?.scale,
            reduced_motion:matchMedia('(prefers-reduced-motion: reduce)').matches,task:document.body.dataset.task})"""),
            }
        )
        page.screenshot(path=str(self.out / (stem + "-viewport.png")))
        page.screenshot(path=str(self.out / (stem + "-full.png")), full_page=True, timeout=30000)
        (self.out / (stem + ".html")).write_text(page.content())
        (self.out / (stem + "-ax.yml")).write_text(page.locator("body").aria_snapshot())
        self.write(stem + "-config.json", state)
        return stem + "-viewport.png"

    def viewport_shots(self, name):
        previous = self.page.viewport_size
        for width, height in ((1440, 900), (1600, 1000), (390, 844), (320, 640)):
            self.page.set_viewport_size({"width": width, "height": height})
            self.shot(self.page, name)
        self.page.set_viewport_size(previous)

    def check(self, ok, name, actual=None, expected=True, fatal=True):
        artifact = (
            self.shot(self.page, f"check-{len(self.results) + 1:03}")
            if not ok
            else "evidence.json"
        )
        state = self.config()
        self.events.append({"check": name, "config": state, "etag": state.get("etag")})
        self.results.append(
            {
                "name": name,
                "pass": bool(ok),
                "expected": expected,
                "actual": bool(ok) if actual is None else deepcopy(actual),
                "artifact": artifact,
                "classification": "software_completed"
                if ok
                else "acceptance_assertion_failed_needs_triage",
            }
        )
        print(("PASS " if ok else "FAIL ") + self.scenario + " " + name, flush=True)
        if not ok and fatal:
            raise AssertionError(name)

    def open_disclosures(self, selector):
        locator = self.page.locator(selector) if isinstance(selector, str) else selector
        for detail in locator.locator("xpath=ancestor::details").all():
            if detail.get_attribute("open") is None:
                summary = detail.locator(":scope > summary")
                self.manifest["operator_actions"].append("Open " + summary.inner_text())
                if self.keyboard:
                    summary.focus()
                    summary.press("Enter")
                else:
                    summary.click()

    def click(self, selector, label=None):
        locator = self.page.locator(selector) if isinstance(selector, str) else selector
        self.open_disclosures(locator)
        self.manifest["operator_actions"].append(label or str(selector))
        if self.keyboard:
            expect(locator).to_be_visible()
            expect(locator).to_be_enabled()
            locator.focus()
            locator.press("Enter")
        else:
            locator.click()

    def task(self, name):
        selector = self.page.locator("#compact-task-select")
        if selector.is_visible():
            selector.select_option(value=TASK_TABS[name])
            return
        self.click(task_tab(self.page, name), "Open " + name)

    def select(self, selector, value):
        self.open_disclosures(selector)
        self.manifest["operator_actions"].append(f"Choose {selector}={value}")
        locator = self.page.locator(selector)
        if self.keyboard:
            expect(locator).to_be_visible()
            expect(locator).to_be_enabled()
            locator.focus()
            options = locator.locator("option").evaluate_all("es=>es.map(e=>e.value)")
            current = options.index(locator.input_value())
            target = options.index(value)
            for _ in range(abs(target - current)):
                locator.press("ArrowDown" if target > current else "ArrowUp")
            locator.press("Enter")
            locator.press("Tab")
            expect(locator).to_have_value(value)
        else:
            locator.select_option(value)

    def toggle(self, selector):
        self.open_disclosures(selector)
        self.manifest["operator_actions"].append("Declare " + selector)
        if self.keyboard:
            expect(self.page.locator(selector)).to_be_visible()
            self.page.locator(selector).focus()
            self.page.keyboard.press("Space")
        else:
            self.page.locator(selector).check()

    def observe(self, context, label):
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        context.expose_binding(
            "recordAcceptanceAction",
            lambda source, event: self.events.append(
                {"page": label, "action": event, "time": time.time()}
            ),
        )
        context.add_init_script("""document.addEventListener('click',e=>{
          const n=e.target.closest('button,a,input,select,summary,[role=button]');
          if(n) window.recordAcceptanceAction({type:'click',id:n.id,text:n.innerText?.slice(0,100),trusted:e.isTrusted});
        },true);document.addEventListener('change',e=>window.recordAcceptanceAction({type:'change',id:e.target.id,value:e.target.type==='file'?'synthetic file':e.target.value}),true);""")
        context.add_init_script("""document.addEventListener('keydown',e=>{
          if(e.key==='Tab') window.recordAcceptanceAction({type:'native-tab',shift:e.shiftKey,trusted:e.isTrusted});
        },true);""")
        context.on("page", lambda page: self.observe_page(page, label))

    def observe_page(self, page, label):
        page.on(
            "pageerror",
            lambda error: self.errors.append({"page": label, "error": str(error)}),
        )
        page.on(
            "console",
            lambda msg: (
                self.console.append(
                    {
                        "page": label,
                        "type": msg.type,
                        "text": msg.text,
                        "location": msg.location,
                        "induced": self.expected_failures(
                            msg.location.get("url", ""), message=msg.text
                        ),
                    }
                )
                if msg.type in ("warning", "error")
                else None
            ),
        )
        page.on(
            "requestfailed",
            lambda req: self.network.append(
                {
                    "page": label,
                    "url": req.url,
                    "failure": req.failure,
                    "induced": self.expected_failures(req.url, failure=req.failure),
                }
            ),
        )
        page.on("response", lambda response: self.response(response, label))
        page.on(
            "request",
            lambda req: (
                self.requests.append(
                    {
                        "page": label,
                        "url": req.url,
                        "method": req.method,
                        "body": request_body(req),
                        "if_match": req.headers.get("if-match"),
                        "induced": list(self.induced),
                    }
                )
                if req.method not in ("GET", "HEAD")
                else None
            ),
        )
        page.on("dialog", self.dialog)
        page.on("websocket", lambda socket: self.observe_socket(socket, label))

    def observe_socket(self, socket, label):
        def frame(direction, payload):
            try:
                value = json.loads(payload)
            except (ValueError, UnicodeDecodeError):
                value = str(payload)
            self.events.append(
                {
                    "page": label,
                    "socket": socket.url,
                    "direction": direction,
                    "payload": value,
                    "time": time.time(),
                }
            )

        socket.on("framesent", lambda payload: frame("sent", payload))
        socket.on("framereceived", lambda payload: frame("received", payload))

    def dialog(self, dialog):
        self.events.append(
            {
                "dialog": dialog.type,
                "message": dialog.message,
                "accepted": self.dialog_accept,
            }
        )
        if dialog.type == "beforeunload" or not self.dialog_accept:
            dialog.dismiss()
        else:
            self.manifest["operator_actions"].append(
                "Accept explicit confirmation: " + dialog.message
            )
            dialog.accept()

    def response(self, response, label):
        if response.status >= 400:
            self.network.append(
                {
                    "page": label,
                    "url": response.url,
                    "status": response.status,
                    "induced": self.expected_failures(
                        response.url, status=response.status
                    ),
                }
            )
        if "/tablet-assignments/" in response.url and response.request.method == "PUT":
            self.responses.append(
                {
                    "url": response.url,
                    "status": response.status,
                    "returned_etag": response.json().get("etag"),
                    "if_match": response.request.headers.get("if-match"),
                }
            )

    @contextmanager
    def fault(self, name, failures=(), console_messages=()):
        item = {
            "name": name,
            "failures": failures,
            "console_messages": console_messages,
        }
        self.induced.append(item)
        self.events.append({"fixture_injection": name, "phase": "start"})
        try:
            yield
        finally:
            self.events.append({"fixture_injection": name, "phase": "end"})
            self.induced.remove(item)

    def expected_failures(self, url, status=None, failure=None, message=None):
        labels = []
        for item in self.induced:
            if message is not None and any(
                re.search(path, url) and re.fullmatch(text, message)
                for path, text in item["console_messages"]
            ):
                labels.append(item["name"])
            for pattern, statuses in item["failures"]:
                if re.search(pattern, url) and (
                    status in statuses
                    or failure is not None
                    and failure in statuses
                    or (failure is not None and "network" in statuses)
                    or (
                        message is not None
                        and any(str(code) in message for code in statuses)
                    )
                    or (
                        message is not None
                        and "network" in statuses
                        and "net::ERR_" in message
                    )
                ):
                    labels.append(item["name"])
        return labels

    def start_server(self):
        listener = socket.socket()
        self.listener = listener
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", self.port))
        listener.listen()
        self.port = listener.getsockname()[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.log = (
            self.out / f"server-{len(self.manifest.get('servers', []))}.log"
        ).open("w")
        command = [
            "rtk",
            "proxy",
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--fd",
            str(listener.fileno()),
            "--no-access-log",
        ]
        self.server = subprocess.Popen(
            command,
            cwd=ROOT,
            env=self.env,
            stdout=self.log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            pass_fds=(listener.fileno(),),
        )
        self.manifest.setdefault("servers", []).append(
            {"pid": self.server.pid, "port": self.port, "command": command}
        )

        def healthy():
            if self.server.poll() is not None:
                raise RuntimeError("Private server exited before health check")
            try:
                with urllib.request.urlopen(
                    self.base + "/healthz", timeout=0.3
                ) as response:
                    return response.status == 200
            except OSError:
                return False

        try:
            wait_until(healthy, lambda ms: time.sleep(ms / 1000))
        finally:
            listener.close()

    def stop_server(self):
        if self.server is None:
            return
        entry = self.manifest["servers"][-1]
        entry["owned_process_group_before_stop"] = process_group_members(
            self.server.pid
        )
        os.killpg(self.server.pid, signal.SIGTERM)
        try:
            self.server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(self.server.pid, signal.SIGKILL)
            self.server.wait(timeout=5)
        deadline = time.monotonic() + 5
        while process_group_members(self.server.pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        if process_group_members(self.server.pid):
            os.killpg(self.server.pid, signal.SIGKILL)
            time.sleep(0.05)
        entry["remaining_owned_process_group"] = process_group_members(self.server.pid)
        entry.update(exit=self.server.returncode, alive=self.server.poll() is None)
        self.log.close()
        self.server = None

    def setup(self, playwright):
        self.temp = tempfile.TemporaryDirectory(prefix="tablet-wall-redesign-")
        self.private = Path(self.temp.name)
        for name in ("assets", "media", "backups"):
            (self.private / name).mkdir()
        image = Image.new("RGB", (1200, 600))
        draw = ImageDraw.Draw(image)
        for i, color in enumerate(
            ((190, 70, 45), (215, 160, 40), (45, 145, 110), (40, 100, 180))
        ):
            draw.rectangle((i * 300, 0, (i + 1) * 300 - 1, 599), fill=color)
            draw.line((i * 300, 0, 1199 - i * 300, 599), fill="white", width=7)
        image.save(self.private / "assets/supplied.png")
        self.manifest["initial_synthetic_image"] = {
            "name": "supplied.png",
            "sha256": digest(self.private / "assets/supplied.png"),
        }
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.env = child_environment(self.private, self.port, self.uploads)
        self.manifest.update(
            private_paths={
                k: v for k, v in self.env.items() if k.startswith("TABLET_WALL")
            },
            base=self.base,
            port=self.port,
            launch_profile="deploy.hotspot.backend_environment composition only; no ingress/hotspot run",
        )
        self.start_server()
        self.browser = playwright.chromium.launch(
            headless=True,
            executable_path=playwright.chromium.executable_path,
            env=self.env,
        )
        self.manifest.update(
            browser_version=self.browser.version,
            browser_executable=playwright.chromium.executable_path,
        )
        context = self.browser.new_context(
            viewport={"width": 1440, "height": 900}, reduced_motion="reduce"
        )
        self.contexts.append(context)
        self.observe(context, "operator")
        self.page = context.new_page()
        self.page.set_default_timeout(7000)
        self.page.goto(self.base + "/controller/physical.html")
        expect(self.page.locator("#tablet-url")).to_be_visible()
        self.check(
            not self.config()["runtime"]["devices"],
            "Console opens before any tablet registers",
        )
        self.viewport_shots("empty")
        self.click("#empty-add-tablets", "Open Add tablets")
        for i in range(4):
            self.new_tablet(i, delay=i == 0)
        expect(self.page.locator("#device-count")).to_contain_text("4")
        self.task("Arrange")
        expect(
            self.page.locator("#grid-order input[type=checkbox]:checked")
        ).to_have_count(4)
        widths = self.page.locator("#grid-order input[data-field=w]").evaluate_all(
            "es=>es.map(e=>e.value)"
        )
        self.check(
            widths == ["70"] * 4,
            "Four late joins selected at fresh aspect without console reload",
            widths,
            ["70"] * 4,
        )
        rows = self.config()["runtime"]["devices"]
        expected_ids = sorted(rows, key=lambda id: rows[id]["number"])
        order = self.page.locator("#grid-order li[data-device-id]").evaluate_all(
            "es=>es.map(e=>e.dataset.deviceId)"
        )
        self.check(
            len({row["number"] for row in rows.values()}) == 4
            and order == expected_ids,
            "Joined tablet numbers are distinct and setup order follows stable numbers",
            order,
            expected_ids,
        )
        self.viewport_shots("four-joined")

    def new_tablet(self, number, delay=False, landscape=False):
        viewport = (
            {"width": 1280, "height": 900}
            if landscape
            else {"width": 900, "height": 1280}
        )
        context = self.browser.new_context(
            viewport=viewport,
            screen=viewport,
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
            user_agent="Mozilla/5.0 (Linux; Android 13; Pixel C) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        self.contexts.append(context)
        self.observe(context, f"tablet-{number + 1}")
        context.add_init_script(
            "Object.defineProperty(screen.orientation,'angle',{get:()=>270,configurable:true})"
        )
        if delay:
            context.add_init_script("""(()=>{const original=window.fetch;let delayed=false;window.fetch=async(...args)=>{
              const response=await original(...args);if(!delayed&&String(args[0]).includes('/devices/register')){
              delayed=true;await new Promise(resolve=>setTimeout(resolve,1800));}return response;};})();""")
        page = context.new_page()
        if delay:
            with page.expect_response("**/devices/register"):
                page.goto(self.base + "/client/")
            self.click(
                "#btn-roster-refresh",
                "Fixture-only refresh to observe registration delay",
            )
            expect(self.page.locator("#device-list .dev-pick")).to_have_count(1)
            rows = self.config()["runtime"]["devices"]
            self.check(
                len(rows) == 1 and next(iter(rows.values()))["online"] is False,
                "Registered-before-online response delay observed",
                rows,
                "one offline registration",
            )
        else:
            page.goto(self.base + "/client/")
        expect(self.page.locator("#device-list .dev-pick")).to_have_count(number + 1)
        wait_until(
            lambda: page.evaluate("localStorage.getItem('tablet-wall-device-id')"),
            page.wait_for_timeout,
        )
        device_id = page.evaluate("localStorage.getItem('tablet-wall-device-id')")
        self.manifest["clients"].append(
            {
                "id": device_id,
                "context": number + 1,
                "viewport": viewport,
                "DPR": 2,
                "orientation_override": 270,
                "synthetic_signature": True,
            }
        )
        wait_until(
            lambda: self.config()["runtime"]["devices"][device_id]["online"],
            self.page.wait_for_timeout,
        )
        self.tablets.append(page)
        return page

    def close(self):
        cleanup = self.manifest.setdefault("cleanup", {"contexts": [], "errors": []})
        owned = owned_browser_processes()
        cleanup["owned_browser_pids_before_close"] = owned
        try:
            if self.server and self.server.poll() is None:
                self.write("final-config.json", self.config())
            if self.page and not self.page.is_closed():
                self.shot(self.page, "final")
            fixtures = self.out / "fixtures"
            fixtures.mkdir(exist_ok=True)
            self.manifest["synthetic_images"] = []
            for path in self.private.rglob("*"):
                if path.suffix.lower() in (".png", ".jpg", ".jpeg"):
                    target = fixtures / (
                        str(path.relative_to(self.private)).replace("/", "-")
                    )
                    shutil.copyfile(path, target)
                    self.manifest["synthetic_images"].append(
                        {
                            "path": str(path),
                            "artifact": str(target),
                            "sha256": digest(path),
                        }
                    )
        except Exception as error:
            cleanup["errors"].append(repr(error))
        finally:
            for i, context in enumerate(self.contexts):
                try:
                    context.tracing.stop(path=str(self.out / f"trace-{i}.zip"))
                    context.close()
                    cleanup["contexts"].append({"index": i, "closed": True})
                except Exception as error:
                    cleanup["errors"].append(repr(error))
            try:
                if self.browser:
                    self.browser.close()
                    cleanup["browser_disconnected"] = not self.browser.is_connected()
                    cleanup["remaining_owned_browser_pids"] = [
                        pid for pid in owned if Path(f"/proc/{pid}").exists()
                    ]
            finally:
                self.stop_server()
                if hasattr(self, "listener"):
                    self.listener.close()
                if hasattr(self, "temp"):
                    self.temp.cleanup()
                    cleanup["private_data_removed"] = not self.private.exists()
                if hasattr(self, "port"):
                    with socket.socket() as probe:
                        cleanup["port_closed"] = (
                            probe.connect_ex(("127.0.0.1", self.port)) != 0
                        )
        self.write("identity.json", self.manifest)
        self.write("evidence.json", self.events)
        self.write("network.json", self.network)
        self.write(
            "console.json", {"pageerrors": self.errors, "messages": self.console}
        )
        self.write("requests.json", self.requests)
        self.write("model-responses.json", self.responses)
        self.write(
            "results.json",
            {
                "checks": self.results,
                "cleanup": cleanup,
                "limits": self.manifest["limits"],
            },
        )


def first_wall(rig):
    p = rig.page
    rig.select("#grid-kind", "physical")
    rig.select("#group-model", "google-pixel-c")
    subjects = p.locator("#group-subjects").inner_text()
    rig.check(
        all(f"Tablet {i}" in subjects for i in range(1, 5)),
        "Group confirmation names exact four subjects",
        subjects,
    )
    rig.check(
        not any(
            a.get("mode") == "explicit"
            for a in rig.config()["tablet_assignments"].values()
        ),
        "Synthetic screen signature does not confirm hardware",
    )
    rig.toggle("#group-hardware")
    rig.click("#group-confirm", "Confirm hardware group")
    expect(p.locator("#group-result")).to_contain_text(
        "Untouched · none", timeout=15000
    )
    rig.select("#grid-common-mount", "0")
    rig.click("#grid-1x4", "Choose Row of 4")
    before = rig.config()
    rig.click("#grid-preview", "Preview arrangement")
    expect(p.locator("body")).to_have_attribute("data-stage-mode", "arrangement-preview")
    labels = p.locator("#stage-identities li").evaluate_all(
        "es=>es.map(e=>({text:e.textContent,pixels:parseFloat(getComputedStyle(e).fontSize)}))"
    )
    names = p.locator('#stage-svg [role="button"]').evaluate_all(
        "es=>es.map(e=>e.getAttribute('aria-label'))"
    )
    rig.check(
        len(labels) == len(names) == 4
        and all(row["pixels"] >= 14 for row in labels)
        and all(
            any(f"Tablet {i}" in row["text"] for row in labels)
            and any(f"Tablet {i}" in name for name in names)
            for i in range(1, 5)
        ),
        "Immediate first preview retains exact accessible identities and readable external labels",
        {"labels": labels, "names": names},
        "4 named SVG buttons and matching external identity labels at least 14 CSS pixels",
    )
    rig.check(
        rig.config()["layout"] == before["layout"],
        "Arrangement preview makes no early durable write",
    )
    rig.viewport_shots("measured-review")
    rig.click("#btn-apply", "Apply arrangement")
    expect(p.locator("body")).to_have_attribute("data-stage-mode", "live", timeout=15000)
    slots = rig.config()["layout"]["slots"]
    rig.check(
        len(slots) == 4
        and all(
            s["mount_angle"] == 0
            and s["profile_revision"] >= 1
            and s["calibration_revision"] >= 1
            for s in slots.values()
        ),
        "Applied arrangement retains declared mount and exact measurement pins",
        slots,
    )
    rig.task("Images")
    rig.click(
        p.get_by_role("button", name="Preview supplied.png", exact=True),
        "Select supplied image",
    )
    rig.click("#show-image", "Show image")
    expect(p.locator("#wall-health")).to_contain_text("4 of 4 showing the current image", timeout=15000)
    current = rig.config()
    renders = {id: row["render"] for id, row in current["runtime"]["devices"].items()}
    rig.check(
        len(renders) == 4
        and all(
            row["current"]
            and row["expected_token"] == row["accepted_token"]
            and row["accepted_token"]["generation"] == current["generation"]
            and row["accepted_token"]["revision"] == current["revision"]
            for row in renders.values()
        ),
        "Four actual clients report exact current generation, revision, mapping, asset and connection tokens",
        renders,
    )
    rig.manifest["script_fixture_action_count"] = len(rig.manifest["operator_actions"])
    rig.manifest["first_wall_actions"] = deepcopy(rig.manifest["operator_actions"])
    rig.check(
        len(rig.manifest["operator_actions"]) <= 16,
        "Scripted first journey at most 16 deliberate console actions including fixture refresh",
        rig.manifest["operator_actions"],
        "<=16; client visits and file picker excluded; not a human benchmark",
    )
    rig.shot(p, "image-shown")
    rig.shot(rig.tablets[0], "real-client-slice")
    for width, height in ((1600, 1000), (1440, 900)):
        p.set_viewport_size({"width": width, "height": height})
        rig.shot(p, "applied-image-shown")
    rig.task("Arrange")
    before = rig.config()
    rig.click("#grid-2x2")
    rig.click("#grid-preview")
    expect(p.locator("body")).to_have_attribute("data-stage-mode", "arrangement-preview")
    rig.check(
        rig.config()["layout"] == before["layout"]
        and rig.config()["revision"] == before["revision"],
        "Additional 2 by 2 preview preserves original durable arrangement and revision",
    )
    rig.viewport_shots("two-by-two-review")
    rig.click("#btn-apply")
    expect(p.locator("body")).to_have_attribute("data-stage-mode", "live", timeout=15000)
    expect(p.locator("#wall-health")).to_contain_text("4 of 4 showing the current image", timeout=15000)
    rig.check(
        rig.config()["scene"] == before["scene"],
        "Additional 2 by 2 Apply changes only arrangement",
    )
    rig.task("Images")
    rig.manifest["limits"].append(
        "First-wall scenario covers the bounded default journey; other scenarios contain mandatory variants."
    )


def run_scenario(out, name, body, uploads=True, keyboard=False):
    out.mkdir(exist_ok=False)
    rig = Rig(out, name, uploads=uploads, keyboard=keyboard)
    with sync_playwright() as playwright:
        try:
            rig.setup(playwright)
            body(rig)
            unexpected = [row for row in rig.network if not row.get("induced")]
            unexpected_console = [row for row in rig.console if not row.get("induced")]
            rig.check(not rig.errors, "No JavaScript page exceptions", rig.errors)
            rig.check(
                not unexpected,
                "No unexpected failed requests or HTTP errors",
                unexpected,
                [],
                fatal=False,
            )
            rig.check(
                not unexpected_console,
                "No unexpected console warnings or errors",
                unexpected_console,
                [],
                fatal=False,
            )
        except Exception as error:
            failure = {
                "name": "scenario interrupted",
                "pass": False,
                "expected": "journey reaches all assertions",
                "actual": repr(error),
                "traceback": traceback.format_exc(),
                "artifact": "failure.json",
                "classification": "driver_or_product_interruption_unresolved",
            }
            rig.results.append(failure)
            rig.write("failure.json", failure)
            print(f"FAIL {name} {error}", flush=True)
            if rig.page and not rig.page.is_closed():
                try:
                    rig.shot(rig.page, "failure")
                except Exception as capture_error:
                    rig.write("capture-error.json", {"error": repr(capture_error)})
        finally:
            rig.close()
    return {
        "scenario": name,
        "pass": all(r["pass"] for r in rig.results)
        and not rig.manifest["cleanup"]["errors"]
        and not rig.manifest["cleanup"].get("remaining_owned_browser_pids", [])
        and rig.manifest["cleanup"].get("port_closed", False)
        and all(
            not row.get("remaining_owned_process_group")
            for row in rig.manifest.get("servers", [])
        ),
        "checks": len(rig.results),
        "failures": [r for r in rig.results if not r["pass"]],
        "artifacts": str(out),
    }


def disabled(rig):
    rig.task("Images")
    rig.click("#add-image")
    rig.check(
        not rig.page.locator("#upload-file").is_visible()
        and "--operator-uploads"
        in rig.page.locator("#upload-instruction").inner_text(),
        "Default-off launch hides file input and gives factual opt-in help",
    )


def image_negatives(rig):
    first_wall(rig)
    p = rig.page
    original = rig.config()
    source = (rig.private / "assets/supplied.png").read_bytes()
    for label, name, mime, data in [
        (
            "invalid extension and MIME",
            "invalid.txt",
            "text/plain",
            b"invalid synthetic input",
        ),
        ("valid PNG bytes with rejected MIME", "wrong-mime.png", "text/plain", source),
        ("invalid PNG bytes", "bad-decode.png", "image/png", b"not a decodable image"),
    ]:
        with rig.fault(label, [(r"/uploads", [415, 422])]):
            rig.open_disclosures(p.locator("#upload-file"))
            p.locator("#upload-file").set_input_files(
                {"name": name, "mimeType": mime, "buffer": data}
            )
            rig.click("#upload-submit")
            expect(p.locator("#upload-message")).to_contain_text(
                "refused", timeout=15000
            )
            expect(p.locator("#upload-submit")).to_be_enabled()
            rig.check(
                rig.config()["scene"] == original["scene"]
                and rig.config()["layout"] == original["layout"],
                label + " is actionable and preserves current wall",
                p.locator("#upload-message").inner_text(),
            )
    for status in [403, 503, 429, 507]:
        with rig.fault(
            f"synthetic admission/storage refusal HTTP {status}",
            [(r"/uploads", [status])],
        ):
            p.route(
                "**/uploads?*",
                lambda route: route.fulfill(
                    status=status, json={"detail": f"Synthetic QA refusal {status}"}
                ),
                times=1,
            )
            rig.open_disclosures(p.locator("#upload-file"))
            p.locator("#upload-file").set_input_files(
                {"name": "refused.png", "mimeType": "image/png", "buffer": source}
            )
            rig.click("#upload-submit")
            if status >= 500:
                expect(p.locator("#upload-progress")).to_be_hidden()
                rig.check(
                    "uncertain" in p.locator("#upload-message").inner_text()
                    and p.locator("#upload-submit").is_disabled(),
                    f"Ambiguous upload HTTP {status} requires explicit inventory reconciliation before retry",
                    {
                        "message": p.locator("#upload-message").inner_text(),
                        "retry_disabled": p.locator("#upload-submit").is_disabled(),
                    },
                    fatal=False,
                )
                rig.click("#refresh-images")
                expect(p.locator("#upload-submit")).to_be_enabled()
            else:
                expect(p.locator("#upload-message")).to_contain_text(
                    f"Synthetic QA refusal {status}"
                )
                expect(p.locator("#upload-submit")).to_be_enabled()
            rig.check(
                rig.config()["scene"] == original["scene"],
                f"UI explains induced {status} and preserves live scene",
            )
    with rig.fault(
        "upload network abort after real request creation", [(r"/uploads", ["network"])]
    ):
        p.route("**/uploads?*", lambda route: route.abort("connectionreset"), times=1)
        rig.open_disclosures(p.locator("#upload-file"))
        p.locator("#upload-file").set_input_files(
            {"name": "uncertain.png", "mimeType": "image/png", "buffer": source}
        )
        rig.click("#upload-submit")
        expect(p.locator("#upload-message")).to_contain_text("uncertain")
        expect(p.locator("#upload-submit")).to_be_disabled()
        rig.check(
            rig.config()["scene"] == original["scene"],
            "Uncertain upload never automatically shows or retries",
        )
        rig.click("#refresh-images")
        expect(p.locator("#upload-submit")).to_be_enabled()
    Image.new("RGB", (811, 407), (160, 23, 180)).save(rig.private / "retry-fresh.png")
    rig.open_disclosures(p.locator("#upload-file"))
    p.locator("#upload-file").set_input_files(str(rig.private / "retry-fresh.png"))
    rig.click("#upload-submit")
    expect(p.locator("#upload-message")).to_contain_text(
        "Image added and selected", timeout=15000
    )
    rig.check(
        rig.config()["scene"] == original["scene"],
        "Explicit upload retry selects without showing",
    )
    before = rig.config()
    client = rig.tablets[0]
    with rig.fault(
        "one shipped client immutable image bytes fail",
        [(r"/(assets|media)/", ["network"])],
        [
            (
                r"/client/client\.js",
                r"\[tablet-wall\] image scene failed: Failed to fetch",
            )
        ],
    ):
        client.route("**/assets/**", lambda route: route.abort("connectionreset"))
        client.route("**/media/**", lambda route: route.abort("connectionreset"))
        rig.click("#show-image")
        expect(p.locator("#wall-health")).to_contain_text(
            "3 of 4 showing the current image", timeout=15000
        )
        failed = rig.config()
        rig.check(
            sum(r["render"]["current"] for r in failed["runtime"]["devices"].values())
            == 3,
            "One byte failure prevents false four-client current proof",
            failed["runtime"],
        )
        rig.shot(client, "actual-client-byte-failure")
        client.unroute("**/assets/**")
        client.unroute("**/media/**")
        rig.task("Tablets")
        rig.click(f'.dev-pick[data-device-id="{rig.manifest["clients"][0]["id"]}"]')
        rig.click("#tablet-retry-image")
        expect(p.locator("#wall-health")).to_contain_text(
            "4 of 4 showing the current image", timeout=15000
        )
        after = rig.config()
        rig.check(
            after["layout"] == before["layout"]
            and all(
                r["render"]["current"] for r in after["runtime"]["devices"].values()
            ),
            "Targeted retry requires fresh actual client paint and keeps geometry",
        )
    rig.manifest["limits"].append(
        "This scenario covers network-abort uncertainty; native deadline and inventory ordering run in separate private edge cases."
    )


def precise_measurement(rig):
    first_wall(rig)
    p = rig.page
    id = rig.manifest["clients"][0]["id"]
    rig.task("Tablets")
    rig.click(f'.dev-pick[data-device-id="{id}"]')
    rig.task("Settings")
    p.locator("#measurement-details").evaluate("e=>e.open=true")
    p.locator("#cal-use-ruler").scroll_into_view_if_needed()
    before = rig.config()
    for axis in ["x", "y"]:
        p.locator(f"#cal-ruler-mm-{axis}").fill("32.39")
        p.locator(f"#cal-ruler-span-{axis}").fill("200")
        p.locator(f"#cal-ruler-error-{axis}").fill("0.5")
    rig.click("#cal-use-ruler")
    expect(p.locator("#cal-ruler-decision")).to_be_visible(timeout=15000)
    rig.shot(p, "precise-ruler-decision")
    rig.check(
        rig.config()["calibrations"] == before["calibrations"],
        "Actual ruler check only reviews uncertainty, never saves early",
    )
    rig.click("#cal-keep-supplied")
    expect(p.locator("#calibration-msg")).to_contain_text("Nothing was written")
    rig.check(
        rig.config()["calibrations"] == before["calibrations"],
        "Keep supplied decision preserves history and pins",
    )
    rig.click("#btn-diag-refresh")
    expect(p.locator("#btn-diag-download")).to_be_enabled(timeout=15000)
    with p.expect_download() as download:
        rig.click("#btn-diag-download")
    download.value.save_as(str(rig.out / "diagnostics-download.json"))
    rig.check(
        (rig.out / "diagnostics-download.json").stat().st_size > 100,
        "Actual diagnostics report downloads from Settings",
    )


def batch_faults(body):
    def run(rig):
        with rig.fault(
            "second real operator changes a name before third assignment, inducing 412",
            [(r"/api/v3/tablet-assignments/", [412])],
        ):
            body(rig)

    return run


def edge_faults(body):
    def run(rig):
        with rig.fault(
            "delayed mutation response and real second-operator conflicts, missing synthetic asset, explicit Forget refusal",
            [(r"/(assets|media)/", [404]), (r"/api/v3/devices/.*/forget", [409, 422])],
        ):
            body(rig)

    return run


def race_suite(rig):
    p = rig.page
    ids = [row["id"] for row in rig.manifest["clients"]]
    other_context = rig.browser.new_context(viewport={"width": 1440, "height": 900})
    rig.contexts.append(other_context)
    rig.observe(other_context, "second-operator")
    other = other_context.new_page()
    other.goto(rig.base + "/controller/physical.html")
    task_tab(other, "Tablets").click()
    other.locator(f'.dev-pick[data-device-id="{ids[0]}"]').click()
    old = rig.config()

    def held(route):
        response = route.fetch()
        other.locator("#tablet-label").fill("New authority after held GET")
        other.locator("#tablet-label-save").click()
        expect(other.locator("#tablet-action-message")).to_contain_text("Name saved")
        expect(p.locator("#device-list")).to_contain_text(
            "New authority after held GET"
        )
        rig.events.append(
            {
                "race": "old config GET held across real newer WS update",
                "old": old,
                "new": rig.config(),
            }
        )
        route.fulfill(response=response)

    p.route("**/api/v3/config", held, times=1)
    rig.task("Tablets")
    rig.click(f'.dev-pick[data-device-id="{ids[1]}"]')
    p.locator("#tablet-label").fill("Retained exact draft B")
    rig.click("#btn-roster-refresh")
    expect(p.locator("#tablet-label")).to_have_value("Retained exact draft B")
    expect(p.locator("#device-list")).to_contain_text("New authority after held GET")
    rig.check(
        True, "Old GET cannot regress newer WS name or keyed dirty form", rig.events[-1]
    )
    rig.manifest["limits"].extend(
        [
            "Stale roster/diagnostics, old paint and uncertain batch writes run in separate private edge cases.",
            "Batch conflict and retained preview/action-subject races run in separate fresh private rigs.",
        ]
    )


def recovery(rig):
    first_wall(rig)
    p = rig.page
    ids = [row["id"] for row in rig.manifest["clients"]]
    rig.task("Saved")
    p.locator("#layout-name").fill("Durable recovery arrangement")
    rig.click("#btn-layout-save")
    expect(p.locator("#layout-msg")).to_contain_text("saved")
    p.locator("#scene-name").fill("Durable recovery scene")
    rig.click("#scene-save")
    expect(p.locator("#scene-message")).to_contain_text("Content saved")
    durable = rig.config()
    client = rig.tablets[0]
    rig.task("Tablets")
    rig.click(f'.dev-pick[data-device-id="{ids[0]}"]')
    rig.click("#tablet-identify")
    expect(client.locator("#identify")).to_be_visible()
    expect(client.locator("#identify")).to_be_hidden(timeout=10000)
    expect(p.locator("#wall-health")).to_contain_text("4 of 4 showing the current image", timeout=15000)
    rig.check(
        True,
        "Identify overlay expires independently and fresh unobscured reports return",
    )
    client.close()
    wait_until(
        lambda: not rig.config()["runtime"]["devices"][ids[0]]["online"],
        p.wait_for_timeout,
    )
    expect(p.locator("#tablet-forget-preview")).to_be_enabled(timeout=20000)
    rig.check(
        not p.locator("#tablet-forget-preview").is_disabled(),
        "Offline registration exposes reviewed recovery",
    )
    rig.click("#tablet-forget-preview")
    expect(p.locator("#tablet-forget-impact")).to_be_visible()
    rig.click("#tablet-forget-cancel")
    rig.check(
        p.locator("#tablet-forget-preview").evaluate("e=>e===document.activeElement"),
        "Forget cancellation returns useful focus",
    )
    reopened = client.context.new_page()
    reopened.goto(rig.base + "/client/")
    rig.tablets[0] = reopened
    expect(p.locator("#wall-health")).to_contain_text("4 of 4 showing the current image", timeout=15000)
    rig.check(
        reopened.evaluate("localStorage.getItem('tablet-wall-device-id')") == ids[0],
        "Independent context storage preserves reconnect identity",
    )
    for viewport in ({"width": 930, "height": 1280}, {"width": 1280, "height": 930}):
        reopened.set_viewport_size(viewport)
        expect(p.locator("#tablet-recovery")).to_contain_text(
            "calibrated", timeout=15000
        )
        rig.shot(reopened, "valid-signature-viewport-mismatch")
        metrics = reopened.evaluate(
            "({overflow:document.documentElement.scrollWidth>innerWidth+1,text:document.body.innerText})"
        )
        rig.check(
            not metrics["overflow"] and len(metrics["text"]) > 30,
            "Valid synthetic signature recovery wraps in both orientations",
            metrics,
            fatal=False,
        )
    reopened.set_viewport_size({"width": 900, "height": 1280})
    expect(p.locator("#wall-health")).to_contain_text("4 of 4 showing the current image", timeout=15000)
    with rig.fault(
        "owned private backend restart; transient socket/network failures expected",
        [(r"127\.0\.0\.1", ["network"])],
    ):
        rig.stop_server()
        rig.start_server()
        expect(p.locator("#wall-health")).to_contain_text(
            "4 of 4 showing the current image", timeout=25000
        )
    fresh = rig.config()
    rig.check(
        fresh["layout"] == durable["layout"] and fresh["scene"] == durable["scene"],
        "Private restart preserves durable arrangement and scene",
        fresh,
    )
    rig.check(
        fresh.get("generation") != durable.get("generation"),
        "Private restart renews server generation",
        [durable.get("generation"), fresh.get("generation")],
    )
    rig.manifest["limits"].append(
        "Byte failure and lifecycle guard variants run in separate private edge cases; this scenario covers offline storage and private restart."
    )


def corrections(rig):
    """Corrective keyboard, fit, Identify, recovery and feedback checks.

    Run with:
      .venv/bin/python simulator/browser/redesign_acceptance.py \
          --artifacts /tmp/tablet-wall-corrections-NEW --scenario corrections
    """
    p = rig.page
    first_wall(rig)
    for name in ("Images", "Tablets", "Arrange", "Saved", "Settings"):
        tab = task_tab(p, name)
        tab.focus()
        tab.press("Enter")
        expect(tab).to_be_focused()
        style = tab.evaluate(
            "e=>({outline:getComputedStyle(e).outlineStyle,rect:e.getBoundingClientRect().toJSON()})"
        )
        rig.check(
            style["outline"] != "none" and style["rect"]["width"] > 1,
            name + " retains visible keyboard tab focus",
            style,
        )

    rig.task("Images")
    gallery = p.locator("#image-gallery .image-choice-button")
    count = gallery.count()
    stops = [gallery.nth(index).evaluate("e=>e.tabIndex") for index in range(count)]
    rig.check(
        count > 0 and sum(1 for stop in stops if stop == 0) == 1
        and all(stop in (0, -1) for stop in stops),
        "Image gallery exposes one tab stop",
        stops,
    )
    if count > 1:
        gallery.nth(0).focus()
        p.keyboard.press("ArrowRight")
        expect(gallery.nth(1)).to_be_focused()
        rig.check(
            gallery.nth(1).evaluate("e=>e.tabIndex") == 0,
            "Gallery tab stop follows arrow focus",
        )
        p.keyboard.press("Home")
        expect(gallery.nth(0)).to_be_focused()

    p.locator("#edit-current-image").click()
    expect(p.locator("#stage-mode-description")).to_have_text("Image preview, not shown")
    tree = p.locator("body").aria_snapshot()
    rig.check(
        "Image preview, not shown" in tree,
        "Actual accessibility tree exposes the image preview boundary",
    )
    (rig.out / "image-preview-ax.yml").write_text(tree)

    toggle = p.locator("#view-toggle")
    expect(toggle).to_have_text("View applied")
    toggle.focus()
    toggle.press("Enter")
    expect(toggle).to_be_focused()
    expect(toggle).to_have_text("View preview")
    rig.check(True, "View applied keeps focus and relabels the toggle View preview")
    toggle.press("Enter")
    expect(toggle).to_be_focused()
    expect(toggle).to_have_text("View applied")
    rig.check(True, "View preview keeps focus and relabels the toggle View applied")

    for width, height in ((320, 844), (390, 844), (667, 375), (844, 390)):
        for scale in (1, 2):
            p.set_viewport_size({"width": width, "height": height})
            tag = p.add_style_tag(content=f"html{{font-size:{100 * scale}%}}")
            for fit in ("cover", "contain"):
                p.locator("#image-fit").select_option(fit)
                p.locator("#image-fit").scroll_into_view_if_needed()
                p.evaluate(
                    "()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))"
                )
                metrics = p.locator("#image-fit").evaluate(
                    """e=>{
                        const s=getComputedStyle(e), c=document.createElement('canvas').getContext('2d');c.font=s.font;
                        return {text:e.selectedOptions[0].textContent,required:c.measureText(e.selectedOptions[0].textContent).width,
                            available:e.clientWidth-parseFloat(s.paddingLeft)-parseFloat(s.paddingRight)-24,
                            labelFont:getComputedStyle(e.parentElement).fontSize};
                    }"""
                )
                rig.check(
                    metrics["required"] <= metrics["available"] + 1
                    and float(metrics["labelFont"].replace("px", "")) >= 14,
                    f"Scaling label and selected {fit} stay readable at {width} and {scale}x text",
                    metrics,
                )
            rig.shot(p, f"{width}-text{scale}-fit")
            tag.evaluate("e=>e.remove()")

    p.locator("#image-discard").click()
    p.set_viewport_size({"width": 1440, "height": 900})
    p.locator("#edit-current-image").click()
    expect(p.locator("#show-image")).to_be_enabled()
    p.locator("#show-image").focus()
    p.locator("#show-image").press("Enter")
    expect(p.locator("#show-image")).to_be_disabled(timeout=15000)
    expect(p.locator("#image-search")).to_be_focused()
    rig.check(True, "Show image hands focus to the visible library after the command disables it")

    rig.task("Arrange")
    p.locator("#grid-1x4").click()
    p.locator("#grid-preview").click()
    expect(p.locator("#stage-mode-description")).to_have_text("Arrangement preview, not applied")
    tree = p.locator("body").aria_snapshot()
    rig.check(
        "Arrangement preview, not applied" in tree,
        "Actual accessibility tree exposes the geometry preview boundary",
    )
    (rig.out / "arrangement-preview-ax.yml").write_text(tree)
    p.locator("#btn-apply").focus()
    p.locator("#btn-apply").press("Enter")
    expect(p.locator("#grid-preview")).to_be_focused(timeout=15000)
    rig.check(True, "Apply arrangement hands focus to the visible Preview control")

    p.locator("#grid-1x4").click()
    p.locator("#grid-preview").click()
    expect(p.locator("#btn-cancel")).to_be_enabled(timeout=15000)
    p.locator("#btn-cancel").focus()
    p.locator("#btn-cancel").press("Enter")
    expect(p.locator("#grid-preview")).to_be_focused()
    rig.check(p.locator("#grid-preview").is_visible(), "Discard returns focus to the visible Preview control")
    rig.open_disclosures("#grid-order")
    identify = p.locator("#grid-order [data-device-id]").first.get_by_role("button", name="Identify", exact=False)
    with p.expect_request("**/identify") as request:
        identify.click()
    subject = p.locator("#grid-order [data-device-id]").first.get_attribute("data-device-id")
    rig.check(
        request.value.url.endswith("/" + subject + "/identify"),
        "Arrange Identify uses its captured row subject",
        request.value.url,
    )
    rig.shot(p, "ordering-identify")

    rig.task("Tablets")
    p.locator(".dev-pick").first.click()
    other = second_operator(rig)
    held = HeldResponse(rig, p, "**/api/v3/config", "Identify stale-authority read")
    save_name(other, subject, "Review tablet")
    held.wait()
    expect(p.locator("#tablet-identify")).to_be_disabled()
    expect(p.locator(".roster-identify").first).to_be_disabled()
    rig.check(True, "Both visible Identify entries disable while authority is stale")
    held.release()
    expect(p.locator("#tablet-identify")).to_be_enabled()
    expect(p.locator(".roster-identify").first).to_be_enabled()
    rig.check(True, "Both Identify entries recover after authoritative reconciliation")

    p.set_viewport_size({"width": 390, "height": 844})
    p.locator(".dev-pick").first.click()
    rig.tablets[0].set_viewport_size({"width": 930, "height": 1280})
    expect(p.locator("#open-tablet-measurements")).to_be_visible()
    p.locator("#open-tablet-measurements").click()
    expect(p.locator("#panel-system")).to_be_visible()
    expect(p.locator("#tablet-model")).to_be_focused()
    expect(p.locator("dialog:modal")).to_have_count(0)
    p.locator("#tablet-model").click()
    p.locator("#tablet-model").press("Escape")
    rig.check(True, "Phone measurement recovery closes its modal and focuses an interactive destination")
    rig.shot(p, "measurement-destination")

    rig.tablets[0].set_viewport_size({"width": 900, "height": 1280})
    rig.task("Tablets")
    rig.new_tablet(4)
    p.locator(".dev-pick").last.click()
    expect(p.locator("#tablet-arrange")).to_be_visible()
    p.locator("#tablet-arrange").click()
    expect(p.locator("#panel-show")).to_be_visible()
    expect(p.locator("dialog:modal")).to_have_count(0)
    p.locator("#grid-1x4").click()
    p.locator("#btn-cancel").click()
    rig.check(True, "Phone Place in Arrange closes its modal and leaves the destination interactive")
    rig.shot(p, "arrange-destination")

    rig.task("Saved")
    p.locator("#layout-name").fill("")
    p.locator("#btn-layout-save").click()
    expect(p.locator("#layout-msg")).to_contain_text("name")
    msg = p.locator("#layout-msg").bounding_box()
    button = p.locator("#btn-layout-save").bounding_box()
    rig.check(
        0 <= msg["y"] - button["y"] - button["height"] < 32,
        "Saved validation is adjacent to the form",
        {"message": msg, "button": button},
    )
    expect(p.locator("#layout-name")).to_be_focused()
    rig.shot(p, "saved-local-feedback")
    rig.check(
        p.locator("#btn-layouts-refresh").inner_text() == "Refresh"
        and p.locator("#scenes-refresh").count() == 0,
        "One task-level Refresh saved names both object inventories",
    )
    rig.shot(p, "corrective-final")


def main(argv=None):
    from _redesign_edge_cases import EDGE_CASES

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument(
        "--ingress-proof",
        type=Path,
        help="Read-only external generated-ingress manifest; source hashes must match",
    )
    parser.add_argument(
        "--scenario", choices=("all", *SCENARIOS, *EDGE_CASES), default="all"
    )
    args = parser.parse_args(argv)
    out = new_artifacts(args.artifacts)
    from _redesign_scenarios import parity, edges, batch
    from operator_accessibility import responsive

    jobs = {
        "first-wall": first_wall,
        "races": race_suite,
        "recovery": recovery,
        "parity": parity,
        "responsive": responsive,
        "corrections": corrections,
        **EDGE_CASES,
    }
    reports = []
    for name in SCENARIOS if args.scenario == "all" else (args.scenario,):
        if name == "edge-cases":
            for edge_name, body in EDGE_CASES.items():
                reports.append(run_scenario(out / edge_name, edge_name, body))
            continue
        reports.append(
            run_scenario(out / name, name, jobs[name], keyboard=name == "responsive")
        )
        if name == "races":
            reports.append(
                run_scenario(out / "model-batch", "model-batch", batch_faults(batch))
            )
            reports.append(
                run_scenario(
                    out / "conflict-lifecycle", "conflict-lifecycle", edge_faults(edges)
                )
            )
        if name == "recovery":
            reports.append(
                run_scenario(
                    out / "image-negatives", "image-negatives", image_negatives
                )
            )
        if name == "parity":
            reports.append(
                run_scenario(
                    out / "precise-measurement",
                    "precise-measurement",
                    precise_measurement,
                )
            )
    if args.scenario == "all":
        reports.append(
            run_scenario(
                out / "uploads-disabled", "uploads-disabled", disabled, uploads=False
            )
        )
    ingress = external_ingress_proof(args.ingress_proof)
    coverage = coverage_report(reports, ingress)
    result = {
        "source": source_identity(),
        "runs": reports,
        "pass": all(r["pass"] for r in reports),
        "acceptance_complete": False,
        "software_complete": all(row["status"] == "PASS" for row in coverage),
        "coverage": coverage,
        "external_ingress": ingress,
        "mandatory_uncovered": [
            row["requirement"] for row in coverage if row["status"] != "PASS"
        ]
        + ENVIRONMENT_OPEN,
        "limits": ENVIRONMENT_OPEN,
    }
    (out / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    return 0 if result["pass"] and args.scenario != "all" else 1


if __name__ == "__main__":
    sys.exit(main())
