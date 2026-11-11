"""Renewal acceptance driver for the operator-console renewal contracts.

This driver never changes application behavior. It serves the selected source
tree as a private app server with explicit data roots, drives the shipped
operator page, and records source, fixture, viewport, request, assertion and
cleanup evidence.

Every check names the plan obligation it proves (a C- or D- id) and records an
actual value against an expected value. A scenario with no checks, an unknown
scenario name, or any failed check is a failure.

Scenario bodies are written from `feature-preservation.md` and `decisions.md`,
not from the parallel T1 and T2 implementations. The five P0 scenarios are:

    status-truth          D1, D2, D3, C-STATUS, C-POWER, C-FOCUS-ROSTER
    guarded-show-focus    D5, C-GUARD
    saved-name-rule       D6, C-NAME
    pattern-grouping      D7, C-PATTERN, C-GALLERY
    layout-foundation     C-LAYOUT, C-TOUCH

The five wave-2 scenarios are:

    images-workbench      D9, D10, C-WORKBENCH, C-FOCUS-ROSTER
    first-wall            D11, D12, C-GUARD, C-STATUS, C-GEOMETRY
    tablet-facts          D13, C-RECOVERY, C-POWER, C-STATUS
    measured-blockers     D12, C-GEOMETRY
    server-stop           C-OFFLINE

The private runtime directory is chosen with TABLET_WALL_RENEWAL_RUNTIME when
set, so a caller can keep DB, assets, media, backups, HOME, XDG and TMPDIR under
its evidence directory outside the repository. It is removed after each run.
The private port range defaults to 43300-43319 and is overridable per worker
with TABLET_WALL_RENEWAL_PORT_RANGE=START-END, so parallel workers never share
a port.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[2]
RENEWAL_TASK_ID = "renewal-1"
DRIVER_PATHS = (
    "simulator/browser/renewal_acceptance.py",
    "simulator/browser/restoration_acceptance.py",
)


def _port_range() -> tuple[int, int]:
    """Return the assigned private port range as an inclusive pair."""
    raw = os.environ.get("TABLET_WALL_RENEWAL_PORT_RANGE", "").strip()
    if not raw:
        return 43300, 43319
    start_text, _, end_text = raw.partition("-")
    try:
        start = int(start_text)
        end = int(end_text) if end_text else start
    except ValueError as error:
        raise ValueError(
            f"TABLET_WALL_RENEWAL_PORT_RANGE must be START-END, got {raw!r}"
        ) from error
    if not (0 < start <= end < 65536):
        raise ValueError(f"TABLET_WALL_RENEWAL_PORT_RANGE is out of range: {raw!r}")
    return start, end


PORT_START, PORT_END = _port_range()
PORTS = tuple(range(PORT_START, PORT_END + 1))

sys.path.insert(0, str(Path(__file__).resolve().parent))

from restoration_acceptance import (  # noqa: E402
    CLIENT_SPECS,
    WAKE_LOCK_DENIED,
    WAKE_LOCK_HELD,
    application_identity,
    generate_fixtures,
    launch_browser,
    launch_server,
    new_artifacts,
    prepare_assets,
    process_cwd,
    resolve_source_root,
    restoration_environment,
    scenario_pass,
    stop_owned_server,
    wait_ready,
    wait_until,
    Rig,
    _write_json,
)

SCENARIO_ENTRIES = (
    {
        "name": "status-truth",
        "owner": "T1",
        "fixtures": 1,
        "obligations": ("D1", "D2", "D3", "C-STATUS", "C-POWER", "C-FOCUS-ROSTER"),
    },
    {
        "name": "guarded-show-focus",
        "owner": "T2",
        "fixtures": 8,
        "obligations": ("D5", "C-GUARD"),
    },
    {
        "name": "saved-name-rule",
        "owner": "T2",
        "fixtures": 1,
        "obligations": ("D6", "C-NAME"),
    },
    {
        "name": "pattern-grouping",
        "owner": "T2",
        "fixtures": 8,
        "obligations": ("D7", "C-PATTERN", "C-GALLERY"),
    },
    {
        "name": "layout-foundation",
        "owner": "T3",
        "fixtures": 0,
        "obligations": ("C-LAYOUT", "C-TOUCH"),
    },
    {
        "name": "images-workbench",
        "owner": "T4",
        "fixtures": 10,
        "obligations": (
            "D9", "D10", "C-WORKBENCH", "C-FOCUS-ROSTER", "C-GALLERY",
            "C-LAYOUT", "C-TOUCH", "C-NAV",
        ),
    },
    {
        "name": "first-wall",
        "owner": "T4",
        "fixtures": 8,
        "obligations": ("D11", "D12", "C-GUARD", "C-STATUS", "C-GEOMETRY", "C-POWER"),
    },
    {
        "name": "tablet-facts",
        "owner": "T5",
        "fixtures": 8,
        "obligations": ("D13", "C-RECOVERY", "C-POWER"),
    },
    {
        "name": "measured-blockers",
        "owner": "T5",
        "fixtures": 0,
        "obligations": ("D12", "C-GEOMETRY"),
    },
    {
        "name": "server-stop",
        "owner": "T6",
        "fixtures": 8,
        "obligations": ("C-OFFLINE",),
    },
)
SCENARIOS = {entry["name"]: entry for entry in SCENARIO_ENTRIES}
SCENARIO_FIXTURES = {entry["name"]: entry["fixtures"] for entry in SCENARIO_ENTRIES}

TASK_NAMES = ("Images", "Arrange", "Tablets", "Saved", "Settings")
TASK_PANELS = {
    "Images": "panel-content",
    "Arrange": "panel-show",
    "Tablets": "panel-tablet",
    "Saved": "panel-saved",
    "Settings": "panel-system",
}
VIEWPORTS = ((1440, 900), (1280, 800), (390, 844), (320, 740), (844, 390))
FRACTIONAL_WIDTHS = (719.5, 767.5, 768.5, 1100.5, 1360.5)
# Control ids that must be visible in each task before a height sweep means
# anything. Tablets rows carry no ids, so their pick button is matched by class.
TOUCH_EXPECTED = {
    "Images": {
        "ids": (
            "view-zoom-fit", "view-zoom-2x", "image-search", "add-image",
            "refresh-images", "image-chooser-summary", "show-colours",
            "show-calibration", "pattern-grid", "pattern-black",
        ),
        "classes": (),
    },
    "Tablets": {
        "ids": ("btn-roster-refresh", "issues-title"),
        "classes": ("dev-pick",),
    },
}

LIMITATIONS = [
    "Software browser evidence only. No physical tablet, optical seam, sleep/wake, "
    "native screen reader, native browser zoom, network ingress or hardware certification.",
    "The operator page is the real shipped page. Generated fixture images are labelled "
    "GENERATED FIXTURE and are never counted as operator content.",
    "CSS text at 200% is applied as an injected html{font-size:200%} style and is labelled "
    "as an emulation, not a user's browser setting.",
    "Fractional CSS viewport widths are not accepted by Playwright or by Chromium's "
    "device-metrics protocol. Exact fractional coverage of C-LAYOUT is therefore "
    "unproven and reported incomplete: each requested fractional width is measured at "
    "the integer CSS width the engine resolves for it, and those integer measurements "
    "are additional coverage only. Chromium resolves 719.5 to 720 and 768.5 to 769. "
    "The shipped page sends 'frame-ancestors \\'none\\'' and X-Frame-Options DENY, so a "
    "same-origin fractional iframe cannot prove it without weakening that policy.",
    "A gallery tile's accessible name is read from its aria-label, which is the name "
    "Chromium computes for a button without aria-labelledby.",
    "images-workbench serves a purpose-built ten-image library (4000x600, 900x2400 and "
    "3200x1000 among them) labelled GENERATED FIXTURE; it is not the shipped library.",
]

# The ten generated workbench images. Three exercise extreme whole-image shapes.
WORKBENCH_IMAGES = (
    ("01-4000x600", 4000, 600),
    ("02-900x2400", 900, 2400),
    ("03-3200x1000", 3200, 1000),
    ("04-1600x1000", 1600, 1000),
    ("05-1000x1600", 1000, 1600),
    ("06-2400x1000", 2400, 1000),
    ("07-1280x720", 1280, 720),
    ("08-720x1280", 720, 1280),
    ("09-2048x1152", 2048, 1152),
    ("10-1024x1024", 1024, 1024),
)
WORKBENCH_SHAPES = (
    ("GENERATED-FIXTURE-01-4000x600.png", 4000, 600),
    ("GENERATED-FIXTURE-02-900x2400.png", 900, 2400),
    ("GENERATED-FIXTURE-03-3200x1000.png", 3200, 1000),
)


def prepare_workbench_assets(assets_root: Path) -> list[dict[str, Any]]:
    """Write the ten reviewed GENERATED FIXTURE images and return their hashes."""
    target = Path(assets_root)
    target.mkdir(parents=True, exist_ok=True)
    prepared: list[dict[str, Any]] = []
    for label, width, height in WORKBENCH_IMAGES:
        name = f"GENERATED-FIXTURE-{label}.png"
        path = target / name
        image = Image.new("RGB", (width, height), (28, 36, 48))
        draw = ImageDraw.Draw(image)
        columns, rows = 8, 6
        cell_w, cell_h = max(1, width // columns), max(1, height // rows)
        for row in range(rows):
            for column in range(columns):
                value = hashlib.sha256(f"{label}:{row}:{column}".encode()).digest()
                draw.rectangle(
                    (
                        column * cell_w,
                        row * cell_h,
                        min(width - 1, (column + 1) * cell_w - 1),
                        min(height - 1, (row + 1) * cell_h - 1),
                    ),
                    fill=tuple(24 + byte % 200 for byte in value[:3]),
                )
        draw.rectangle(
            (max(0, width // 2 - 20), max(0, height // 2 - 20),
             min(width - 1, width // 2 + 20), min(height - 1, height // 2 + 20)),
            fill=(240, 240, 240),
        )
        image.save(path, format="PNG")
        prepared.append(
            {
                "name": name,
                "path": str(path),
                "sha256": _sha256_bytes(path.read_bytes()),
                "bytes": path.stat().st_size,
                "width": width,
                "height": height,
                "format": "png",
                "generated_fixture": True,
            }
        )
    return prepared


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def driver_identity() -> dict[str, Any]:
    hashes = {
        name: _sha256_bytes((REPO / name).read_bytes())
        for name in DRIVER_PATHS
        if (REPO / name).is_file()
    }
    head = None
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, timeout=20, check=False
        )
        head = completed.stdout.strip() if completed.returncode == 0 else None
    except Exception:  # pragma: no cover - environment dependent
        head = None
    return {"driver_root": str(REPO), "head": head, "driver_hashes": hashes,
            "driver_sha256": _sha256_bytes(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode())}


def resolved_width(requested: float) -> int:
    """The integer CSS width Chromium resolves for a fractional request."""
    return int(math.floor(requested + 0.5))


# ---------------------------------------------------------------------------
# Rig
# ---------------------------------------------------------------------------


class RenewalRig(Rig):
    """The restoration Rig, bound to the assigned private port range."""

    def setup(self, playwright: Any) -> None:
        runtime_root = Path(os.environ.get("TABLET_WALL_RENEWAL_RUNTIME") or tempfile.gettempdir())
        runtime_root.mkdir(parents=True, exist_ok=True)
        self.private = Path(tempfile.mkdtemp(prefix=f"renewal-{self.scenario}-", dir=runtime_root))
        data = self.private / "data"
        self.fixtures = generate_fixtures(self.private / "fixtures")
        if self.scenario == "images-workbench":
            self.assets = prepare_workbench_assets(data / "assets")
        else:
            count = SCENARIO_FIXTURES[self.scenario]
            self.assets = prepare_assets(self.private / "fixtures", data / "assets", count)
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        bound = None
        for port in PORTS:
            try:
                self.listener.bind(("127.0.0.1", port))
                bound = port
                break
            except OSError:
                continue
        if bound is None:
            self.listener.close()
            self.listener = None
            raise RuntimeError(f"no free port in the assigned range {PORTS[0]}-{PORTS[-1]}")
        self.listener.listen(128)
        self.port = bound
        self.base = f"http://127.0.0.1:{self.port}"
        self.env = restoration_environment(data, self.port, uploads=True)
        self.server, self.server_log, self.argv = launch_server(
            self.source_root, self.env, self.out / "server.log", self.listener
        )
        self.listener.close()
        self.listener = None
        wait_ready(self.base, self.server, self.out / "server.log")
        self.server_cwd = process_cwd(self.server.pid)
        self.api_client = None
        self.api_calls = []
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
        wait_until(
            self.page,
            "() => document.getElementById('wall-health')?.textContent !== 'Checking tablet status…'",
        )

    def check(  # type: ignore[override]
        self,
        name: str,
        ok: bool,
        actual: Any = None,
        expected: Any = True,
        *,
        obligation: str,
        fatal: bool = False,
        classification: str | None = None,
        known_baseline_failure: str | None = None,
        incomplete_reason: str | None = None,
    ) -> bool:
        super().check(
            name,
            ok,
            actual,
            expected,
            fatal=False,
            classification=classification,
            known_baseline_failure=known_baseline_failure,
        )
        row = self.results[-1]
        row["obligation"] = obligation
        if incomplete_reason:
            row["incomplete"] = incomplete_reason
            if not ok:
                row["classification"] = classification or "unproven_known_platform_limitation"
        if not ok and fatal:
            raise AssertionError(name)
        return bool(ok)

    def close(self) -> dict[str, Any]:  # type: ignore[override]
        cleanup = super().close()
        identity_path = self.out / "identity.json"
        if identity_path.is_file():
            identity = json.loads(identity_path.read_text())
            identity["task"] = RENEWAL_TASK_ID
            identity["driver"] = "simulator/browser/renewal_acceptance.py"
            _write_json(identity_path, identity)
        return cleanup


# ---------------------------------------------------------------------------
# Shared measurement snippets
# ---------------------------------------------------------------------------


VISIBLE_PANEL = "() => document.querySelector('.task-panel:not([hidden])')"

LAYOUT_MEASURE = """() => {
    const visible = el => {
        if (!el || !el.isConnected || el.closest('.sr-only')) return false;
        if (typeof el.checkVisibility === 'function'
                && !el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0.5 && rect.height > 0.5;
    };
    const panels = [...document.querySelectorAll('.task-panel')].filter(visible);
    const panel = panels[0] || null;
    const result = {
        innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        panel: panel ? panel.id : null,
        paddings: panels.map(item => [item.id, parseFloat(getComputedStyle(item).paddingInlineStart)]),
        headings: {},
        textOffenders: [],
        textCount: 0,
    };
    if (!panel) return result;
    for (const level of ['h2', 'h3']) {
        const sizes = new Map();
        panel.querySelectorAll(level).forEach(heading => {
            if (heading.closest('.sr-only') || !visible(heading)) return;
            const size = getComputedStyle(heading).fontSize;
            if (!sizes.has(size)) sizes.set(size, heading.id || heading.textContent.trim().slice(0, 24));
        });
        result.headings[level] = [...sizes.entries()].map(([size, sample]) => ({size, sample}));
    }
    const walker = document.createTreeWalker(panel, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
        if (!node.nodeValue.trim()) continue;
        const parent = node.parentElement;
        if (!parent || !visible(parent)) continue;
        const range = document.createRange();
        range.selectNodeContents(node);
        for (const rect of range.getClientRects()) {
            if (rect.width < 1 || rect.height < 1) continue;
            result.textCount += 1;
            if (rect.left < 12 - 0.01 || rect.right > innerWidth - 12 + 0.01) {
                result.textOffenders.push({
                    left: Math.round(rect.left * 100) / 100,
                    right: Math.round(rect.right * 100) / 100,
                    text: node.nodeValue.trim().slice(0, 60),
                    tag: parent.tagName,
                    cls: String(parent.className).slice(0, 40),
                });
            }
        }
    }
    return result;
}"""

CONTROL_SWEEP = """() => {
    const panel = document.querySelector('.task-panel:not([hidden])');
    if (!panel) return {panel: null, controls: [], count: 0, short: [], coarse: false};
    const selector = 'button, select, textarea, summary, .check-label, .check,'
        + ' input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"])';
    const controls = [...panel.querySelectorAll(selector)].filter(el => {
        if (el.disabled) return false;
        if (el.getAttribute('aria-disabled') === 'true') return false;
        if (el.closest('details:not([open])') && !el.matches('summary')) return false;
        if (typeof el.checkVisibility === 'function'
                && !el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) return false;
        return el.getClientRects().length > 0;
    });
    const rows = controls.map(el => {
        const rect = el.getBoundingClientRect();
        return {
            tag: el.tagName,
            id: el.id,
            cls: String(el.className).slice(0, 40),
            label: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 40),
            height: Math.round(rect.height * 100) / 100,
        };
    });
    return {
        panel: panel.id,
        controls: rows,
        count: rows.length,
        short: rows.filter(row => row.height < 44),
        coarse: matchMedia('(pointer: coarse)').matches,
    };
}"""


def touch_coverage(sweep: dict[str, Any], task: str) -> dict[str, Any]:
    """Which required controls the sweep actually saw, independent of counts."""
    rows = sweep["controls"]
    ids = {row["id"] for row in rows if row["id"]}
    classes = {token for row in rows for token in row["cls"].split()}
    expected = TOUCH_EXPECTED[task]
    missing_ids = [item for item in expected["ids"] if item not in ids]
    missing_classes = [item for item in expected["classes"] if item not in classes]
    return {
        "ok": bool(rows) and not missing_ids and not missing_classes,
        "controls": len(rows),
        "ids": sorted(ids),
        "missing_ids": missing_ids,
        "missing_classes": missing_classes,
    }


def _device_rows(page: Any) -> list[dict[str, Any]]:
    return page.evaluate(
        """() => [...document.querySelectorAll('#stage-svg .slot, #device-list .dev-row')].map(node => ({
            kind: node.classList.contains('slot') ? 'slot' : 'row',
            id: node.dataset.deviceId,
            status: node.dataset.status,
            powerState: node.dataset.powerState,
            powerWarning: node.dataset.powerWarning,
            powerStale: node.dataset.powerStale,
        }))"""
    )


def _roster_rows(page: Any) -> list[dict[str, Any]]:
    return page.evaluate(
        """() => [...document.querySelectorAll('#exception-roster > li')].map(row => ({
            id: row.dataset.deviceId,
            status: row.dataset.status,
            powerState: row.dataset.powerState,
        }))"""
    )


def _visible_text_matches(page: Any, pattern: str) -> list[dict[str, Any]]:
    return page.evaluate(
        """source => {
            const matcher = new RegExp(source, 'i');
            const scope = [document.querySelector('header.topbar'), document.getElementById('panel-content')];
            const seen = [];
            for (const root of scope) {
                if (!root) continue;
                const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
                let node;
                while ((node = walker.nextNode())) {
                    if (!matcher.test(node.nodeValue)) continue;
                    const parent = node.parentElement;
                    if (!parent) continue;
                    if (typeof parent.checkVisibility === 'function'
                            && !parent.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) continue;
                    seen.push({text: node.nodeValue.trim().slice(0, 90),
                        id: (parent.closest('[id]') || {}).id || ''});
                }
            }
            return seen;
        }""",
        pattern,
    )


def _wait_task_panel(rig: RenewalRig, name: str) -> None:
    panel = TASK_PANELS[name]
    wait_until(
        rig.page,
        "(id) => { const node = document.getElementById(id); return !!node && !node.hidden"
        " && node.getClientRects().length > 0; }",
        arg=panel,
    )


TASK_VALUES = {"Images": "content", "Arrange": "show", "Tablets": "tablet", "Saved": "saved", "Settings": "system"}


def _soft_wait(page: Any, expression: str, arg: Any = None, timeout: float = 15.0) -> bool:
    try:
        wait_until(page, expression, arg=arg, timeout=timeout)
        return True
    except TimeoutError:
        return False


def _task(rig: RenewalRig, name: str) -> None:
    page = rig.page
    compact = page.locator("#compact-task-select")
    if compact.is_visible():
        compact.select_option(value=TASK_VALUES[name])
    else:
        page.get_by_role(
            "tab", name=re.compile(rf"^{re.escape(name)}(?:, unsaved changes)?$")
        ).click()
    _wait_task_panel(rig, name)
    page.wait_for_timeout(60)


def _port_and_place(rig: RenewalRig, count: int, held: int | None = None) -> list[tuple[Any, str]]:
    """Join `count` clients with a denied wake lock and place them on a 4x2 wall."""
    clients = []
    for index in range(count):
        spec = CLIENT_SPECS[index % len(CLIENT_SPECS)]
        script = WAKE_LOCK_HELD if held == index else WAKE_LOCK_DENIED
        clients.append(rig.new_client(spec, index, script))
    ids = [device_id for _, device_id in clients]
    status, _ = rig.request("PUT", "/wall", {"width": 1600, "height": 800})
    if status != 200:
        raise RuntimeError(f"logical wall write failed: {status}")
    for index, device_id in enumerate(ids):
        status, _ = rig.request(
            "PUT",
            f"/devices/{device_id}/placement",
            {"x": (index % 4) * 400, "y": (index // 4) * 400, "w": 400, "h": 400},
        )
        if status != 200:
            raise RuntimeError(f"placement write failed for {index}: {status}")
    rig.wait_config(
        lambda config: all(device_id in config["layout"]["placements"] for device_id in ids),
        timeout=20,
    )
    return clients


def _place_extra(rig: RenewalRig, spec_index: int, cell: int, script: str) -> tuple[Any, str]:
    page, device_id = rig.new_client(CLIENT_SPECS[spec_index % len(CLIENT_SPECS)], spec_index, script)
    status, _ = rig.request(
        "PUT",
        f"/devices/{device_id}/placement",
        {"x": (cell % 4) * 400, "y": (cell // 4) * 400, "w": 400, "h": 400},
    )
    if status != 200:
        raise RuntimeError(f"extra placement write failed: {status}")
    rig.wait_config(lambda config: device_id in config["layout"]["placements"], timeout=20)
    return page, device_id


def _close_client(rig: RenewalRig, page: Any, device_id: str) -> None:
    context = page.context
    if context in rig.contexts:
        rig.contexts.remove(context)
    context.close()
    rig.wait_config(
        lambda config: config["runtime"]["devices"].get(device_id, {}).get("online") is False,
        timeout=20,
    )


def _scene_scene_puts(rig: RenewalRig) -> int:
    return len([row for row in rig.requests
                if row["method"] == "PUT" and row["url"].split("?")[0].endswith("/api/v3/scene")])


def _inner_text(page: Any, selector: str) -> str:
    locator = page.locator(selector)
    return locator.inner_text() if locator.count() else ""


# ---------------------------------------------------------------------------
# status-truth (D1, D2, D3, C-STATUS, C-POWER, C-FOCUS-ROSTER)
# ---------------------------------------------------------------------------


def status_truth(rig: RenewalRig) -> None:
    page = rig.page
    clients = _port_and_place(rig, 6)
    ids = [device_id for _, device_id in clients]
    rig.wait_config(
        lambda config: all(config["runtime"]["devices"][device_id].get("wake_lock") == "denied" for device_id in ids),
        timeout=20,
    )
    asset = rig.assets[0]
    status, _ = rig.put_scene({"type": "image", "asset": "sha256:" + asset["sha256"], "fit": "cover"})
    if status != 200:
        raise RuntimeError(f"scene write failed: {status}")
    rig.wait_config(
        lambda config: all(config["runtime"]["devices"][device_id]["render"].get("state") == "displayed"
                           for device_id in ids),
        timeout=30,
    )
    offline_id = ids[-1]
    _close_client(rig, clients[-1][0], offline_id)
    _task(rig, "Images")
    wait_until(page, "() => /showing the current/.test(document.getElementById('wall-health').textContent)")

    shown = _visible_text_matches(page, "showing the current")
    rig.check(
        "The wall sentence appears once across the top bar and Images panel",
        len(shown) == 1,
        shown,
        {"count": 1},
        obligation="D3",
    )

    health_text = _inner_text(page, "#wall-health")
    health_label = page.get_attribute("#btn-wall-health", "aria-label")
    rig.check(
        "The wall health line keeps its exact count and Issues label",
        health_text == "5 of 6 showing the current image"
        and health_label == "5 of 6 tablets showing the current image. Issues.",
        {"text": health_text, "label": health_label},
        {"text": "5 of 6 showing the current image",
         "label": "5 of 6 tablets showing the current image. Issues."},
        obligation="C-STATUS",
    )

    power_mentions = page.evaluate(
        """() => {
            const root = document.getElementById('panel-content');
            const out = [];
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walker.nextNode())) {
                if (!/power/i.test(node.nodeValue)) continue;
                const parent = node.parentElement;
                if (!parent) continue;
                if (typeof parent.checkVisibility === 'function'
                        && !parent.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) continue;
                out.push({text: node.nodeValue.trim().slice(0, 80), cls: String(parent.className).slice(0, 40)});
            }
            return out;
        }"""
    )
    rig.check(
        "Uniform wake-lock warnings leave at most three visible power mentions in Images",
        len(power_mentions) <= 3,
        power_mentions,
        {"max": 3},
        obligation="D2",
    )

    roster = _roster_rows(page)
    rig.check(
        "The first Exceptions roster row is the offline tablet",
        len(roster) == 6 and roster[0]["id"] == offline_id,
        {"rows": roster, "offline": offline_id},
        {"first": offline_id, "count": 6},
        obligation="D1",
    )

    attention = _inner_text(page, "#attention-heading")
    rig.check(
        "The attention heading counts the one offline position",
        attention == "Needs attention (1)",
        attention,
        "Needs attention (1)",
        obligation="D1",
    )

    summary = page.locator("#wall-power-summary")
    summary_visible = summary.count() == 1 and summary.is_visible()
    summary_text = summary.inner_text() if summary.count() else ""
    rig.check(
        "The fleet power line is visible and names the five online reports",
        summary_visible and "5" in summary_text and "denied" in summary_text.lower(),
        {"count": summary.count(), "visible": summary_visible, "text": summary_text},
        {"count": 1, "visible": True, "names": "5 ... denied"},
        obligation="D2",
    )

    _task(rig, "Tablets")
    wait_until(
        page,
        "(ids) => ids.every(id => document.querySelector('#device-list .dev-row[data-device-id=\"' + id + '\"]'))",
        arg=ids,
        timeout=20,
    )
    wait_until(
        page,
        """(ids) => ids.every(id => {
            const row = document.querySelector('#device-list .dev-row[data-device-id="' + id + '"]');
            return row && row.dataset.status;
        })""",
        arg=ids,
        timeout=20,
    )
    rows = _device_rows(page)
    by_key = {(row["kind"], row["id"]): row for row in rows}
    mismatches = []
    for index, device_id in enumerate(ids):
        for kind in ("slot", "row"):
            actual = by_key.get((kind, device_id))
            if actual is None:
                mismatches.append({"kind": kind, "id": device_id, "missing": True})
                continue
            offline = index == len(ids) - 1
            expected = {
                "kind": kind,
                "id": device_id,
                "status": actual["status"],
                "powerState": "denied",
                "powerWarning": "true",
                "powerStale": "true" if offline else "false",
            }
            if offline and actual["status"] == "displayed":
                mismatches.append({"kind": kind, "id": device_id, "displayed": True})
            elif not offline and actual["status"] != "displayed":
                mismatches.append({"kind": kind, "id": device_id, "status": actual["status"]})
            elif actual != expected:
                mismatches.append({"kind": kind, "id": device_id, "actual": actual})
    rig.check(
        "Every stage slot and Tablets row keeps the per-device power attributes",
        len(rows) == 12 and not mismatches,
        {"rows": rows, "mismatches": mismatches},
        {"rows": 12, "mismatches": []},
        obligation="C-POWER",
    )

    _task(rig, "Images")
    _, held_id = _place_extra(rig, 6, 2, WAKE_LOCK_HELD)
    rig.wait_config(
        lambda config: config["runtime"]["devices"][held_id].get("wake_lock") == "held"
        and held_id in config["layout"]["placements"],
        timeout=20,
    )
    wait_until(
        page,
        "(id) => !!document.querySelector('#stage-svg .slot[data-device-id=\"' + id + '\"]')",
        arg=held_id,
        timeout=20,
    )
    warnings = page.evaluate(
        """() => {
            const slots = [...document.querySelectorAll('#stage-svg .slot')]
                .filter(slot => slot.dataset.powerWarning === 'true');
            return {
                count: slots.length,
                missing: slots.filter(slot => !/denied/i.test(slot.textContent))
                    .map(slot => slot.dataset.deviceId),
            };
        }"""
    )
    rig.check(
        "Mixed wake-lock states keep every warning tile's power text",
        warnings["count"] >= 6 and warnings["missing"] == [],
        warnings,
        {"count": ">= 6", "missing": []},
        obligation="D2",
    )
    mixed_summary = page.locator("#wall-power-summary")
    rig.check(
        "Mixed wake-lock states hide the fleet line instead of summarising one state",
        mixed_summary.count() == 1 and not mixed_summary.is_visible(),
        {"count": mixed_summary.count(),
         "visible": mixed_summary.is_visible() if mixed_summary.count() else None},
        {"count": 1, "visible": False},
        obligation="D2",
    )

    focus_id = ids[0]
    target = page.locator(f'#exception-roster li[data-device-id="{focus_id}"] .exception-review')
    wait_until(page, "(id) => { const row = document.querySelector('#exception-roster li[data-device-id=\"' + id + '\"]'); return !!row && row.dataset.status === 'displayed'; }", arg=focus_id)
    target.focus()
    focused_before = page.evaluate("() => document.activeElement?.dataset?.deviceId || null")
    focus_offline = ids[1]
    _close_client(rig, clients[1][0], focus_offline)
    reordered = _soft_wait(
        page,
        "(id) => { const first = document.querySelector('#exception-roster > li'); return !!first && first.dataset.deviceId === id; }",
        arg=focus_offline,
        timeout=20,
    )
    focused = page.evaluate(
        """() => {
            const element = document.activeElement;
            return {tag: element ? element.tagName : null,
                id: element && element.dataset ? element.dataset.deviceId || null : null,
                body: element === document.body};
        }"""
    )
    rig.check(
        "A reordering render keeps focus on the same roster button",
        reordered and focused_before == focus_id and focused["id"] == focus_id and not focused["body"],
        {"before": focused_before, "after": focused, "reordered": reordered},
        {"before": focus_id, "after": focus_id, "body": False, "reordered": True},
        obligation="C-FOCUS-ROSTER",
    )

    # Stale roster is a different state from an offline client. One client is
    # already offline above while the roster itself is still current; stopping
    # the server makes the controller's roster read fail with no injected JS.
    current_before = page.evaluate(
        """() => {
            const summary = document.getElementById('wall-power-summary');
            return {
                connection: document.body.dataset.connection,
                health: document.getElementById('wall-health').textContent,
                offlineRows: [...new Set([...document.querySelectorAll(
                    '#device-list .dev-row[data-status="offline"], #stage-svg .slot[data-status="offline"]'
                )])].map(row => row.dataset.deviceId),
                fleet: summary
                    ? {present: true, visible: summary.getClientRects().length > 0, hidden: summary.hidden}
                    : {present: false},
            };
        }"""
    )
    stopped = stop_owned_server(rig.server)
    _write_json(
        rig.out / "server_stop.json",
        {
            "reason": "drive a stale controller roster independently of offline paint",
            "restarted": False,
            "restart_note": "The scenario ends after this assertion set; rig cleanup records the "
                            "deliberate stop instead of pretending the server is alive.",
            "server": stopped,
        },
    )
    became_stale = _soft_wait(
        page, "() => document.body.dataset.connection === 'stale'", timeout=15
    )
    stale = page.evaluate(
        """() => {
            const health = document.getElementById('wall-health');
            const summary = document.getElementById('wall-power-summary');
            const roster = document.getElementById('roster-status');
            return {
                connection: document.body.dataset.connection,
                health: health.textContent,
                healthLabel: document.getElementById('btn-wall-health').getAttribute('aria-label'),
                counting: /\\d+ of \\d+ showing the current/.test(health.textContent),
                fleet: summary
                    ? {present: true, visible: summary.getClientRects().length > 0,
                        hidden: summary.hidden, text: summary.textContent}
                    : {present: false},
                roster: roster
                    ? {present: true, hidden: roster.hidden, text: roster.textContent}
                    : {present: false},
                rowStatuses: [...document.querySelectorAll('#device-list .dev-row')]
                    .map(row => row.dataset.status),
            };
        }"""
    )
    rig.check(
        "A stopped server makes the connection stale instead of reusing offline paint",
        became_stale
        and current_before["connection"] == "current"
        and bool(current_before["offlineRows"])
        and stale["connection"] == "stale",
        {"before": current_before, "after": stale["connection"], "server_stop": stopped},
        {"before": {"connection": "current", "offlineRows": ">= 1"},
         "after": {"connection": "stale"}},
        obligation="C-POWER",
    )
    rig.check(
        "A stale roster reports that current image evidence is unavailable",
        became_stale
        and "Status stale" in stale["health"]
        and "Current image evidence unavailable" in stale["health"]
        and not stale["counting"]
        and (stale["healthLabel"] or "").startswith("Status stale."),
        {"health": stale["health"], "label": stale["healthLabel"],
         "counting": stale["counting"]},
        {"health": "Status stale · Current image evidence unavailable",
         "counting": False, "label": "starts with Status stale."},
        obligation="C-POWER",
    )
    rig.check(
        "A stale roster marks every Tablets row stale instead of offline",
        became_stale
        and bool(stale["rowStatuses"])
        and all(status == "stale" for status in stale["rowStatuses"])
        and stale["roster"]["present"]
        and not stale["roster"]["hidden"]
        and "Status stale" in stale["roster"]["text"],
        {"statuses": stale["rowStatuses"], "roster": stale["roster"],
         "offline_before_stop": current_before["offlineRows"]},
        {"statuses": ["stale", "…"], "roster": {"hidden": False, "text": "Status stale. …"}},
        obligation="D2",
    )
    rig.check(
        "A stale roster hides the fleet power line",
        became_stale
        and stale["fleet"]["present"]
        and stale["fleet"]["hidden"]
        and not stale["fleet"]["visible"],
        stale["fleet"],
        {"present": True, "hidden": True, "visible": False},
        obligation="D2",
    )


# ---------------------------------------------------------------------------
# guarded-show-focus (D5, C-GUARD)
# ---------------------------------------------------------------------------


def guarded_show_focus(rig: RenewalRig) -> None:
    page = rig.page
    clients = [rig.new_client(CLIENT_SPECS[i % 4], i) for i in range(6)]
    _place_grid(rig, clients, 1800, 1000, 3)
    for width, height in ((1440, 900), (1280, 800), (390, 844)):
        page.set_viewport_size({"width": width, "height": height})
        for kind in ("image", "unfocused", "saved"):
            _task(rig, "Images")
            if kind == "saved":
                status, _ = rig.request("PUT", "/api/v3/scenes/Renewal%20focus?replace=true",
                                        if_match=rig.config()["etag"])
                if status != 200:
                    raise RuntimeError(f"saved focus fixture failed: {status}")
                wait_until(page, "etag => document.getElementById('etag-value').title === etag"
                           " && document.getElementById('etag-state').textContent === 'current'",
                           arg=rig.config()["etag"])
                _task(rig, "Saved")
                wait_until(page, "() => document.getElementById('scenes-status').textContent === ''")
                page.get_by_role("button", name="Preview content “Renewal focus”", exact=True).click()
            else:
                page.locator("#image-gallery > li .image-choice-button").first.click()
            wait_until(page, "() => !document.getElementById('show-image').disabled")
            page.keyboard.press("Tab")
            page.locator("#image-search" if kind == "unfocused" else "#show-image").focus()
            page.evaluate("""() => {
                window.renewalFocusCalls = [];
                window.renewalFocus = HTMLElement.prototype.focus;
                window.renewalScroll = Element.prototype.scrollIntoView;
                HTMLElement.prototype.focus = function(...args) {
                    window.renewalFocusCalls.push(['focus', this.id]);
                    return window.renewalFocus.apply(this, args);
                };
                Element.prototype.scrollIntoView = function(...args) {
                    window.renewalFocusCalls.push(['scroll', this.id]);
                    return window.renewalScroll.apply(this, args);
                };
            }""")
            start = len(rig.requests)
            asset = rig.assets[1]
            status, _ = rig.put_scene({"type": "image", "asset": "sha256:" + asset["sha256"],
                                       "fit": "contain", "background": f"#{width + len(rig.requests):06x}"})
            if status != 200:
                raise RuntimeError(f"remote focus fixture write failed: {status}")
            wait_until(page, "etag => document.getElementById('etag-value').title === etag"
                       " && document.getElementById('etag-state').textContent === 'current'",
                       arg=rig.config()["etag"])
            page.wait_for_timeout(200)
            actual = page.evaluate("""() => {
                const active = document.activeElement, a = active.getBoundingClientRect();
                const message = document.getElementById('image-message'), m = message.getBoundingClientRect();
                const hit = document.elementFromPoint(a.left + a.width / 2, a.top + a.height / 2);
                const inside = r => r.width > 0 && r.height > 0 && r.top >= 0 && r.left >= 0
                    && r.bottom <= innerHeight && r.right <= innerWidth;
                const result = {focus: active.id, inside: inside(a), hit: hit === active || active.contains(hit),
                    ring: active.matches(':focus-visible'), message: message.textContent,
                    messageInside: inside(m), role: message.getAttribute('role'),
                    disabled: document.getElementById('show-image').disabled,
                    dirty: document.body.dataset.outputDirty, calls: window.renewalFocusCalls};
                HTMLElement.prototype.focus = window.renewalFocus;
                Element.prototype.scrollIntoView = window.renewalScroll;
                return result;
            }""")
            expected_message = (
                "The wall changed after this preview was built. Show is off. Discard this preview, then open Saved and preview the content again."
                if kind == "saved" else
                "The wall changed after this preview was built. Show is off until the preview is rebuilt. Use Rebuild preview, then Show image."
            )
            expected_focus = "image-search" if kind == "unfocused" else (
                "image-message" if kind == "saved" else "image-rebuild")
            rig.check(
                f"Remote {kind} preview change at {width}x{height} explains disabled Show and preserves visible focus ownership without writes",
                actual["focus"] == expected_focus and actual["inside"] and actual["hit"]
                and actual["ring"] and actual["message"] == expected_message
                and actual["role"] == "status" and actual["disabled"] and actual["dirty"] == "true"
                and (kind != "unfocused" or not actual["calls"])
                and (kind == "unfocused" or width == 390 or actual["messageInside"])
                and not _controller_write_rows(rig, start),
                {**actual, "writes": _controller_write_rows(rig, start)},
                {"focus": expected_focus, "message": expected_message, "writes": []},
                obligation="D5",
            )
            rig.shot(f"remote-stale-{kind}-{width}")
            page.locator("#image-discard").click()
    page.set_viewport_size({"width": 1440, "height": 900})
    _task(rig, "Images")
    wait_until(page, "() => document.querySelectorAll('#image-gallery > li').length >= 8", timeout=20)
    page.locator("#image-gallery > li .image-choice-button").first.click()
    wait_until(page, "() => !document.getElementById('show-image').disabled")
    rig.check(
        "Selecting a library image starts a draft that can be shown",
        page.evaluate("() => document.body.dataset.outputDirty === 'true'"),
        page.evaluate("() => document.body.dataset.outputDirty"),
        "true",
        obligation="C-GUARD",
        fatal=True,
    )

    original_guard = rig.config()["etag"]

    def competing_write(route: Any) -> None:
        asset = rig.assets[1]
        status, _ = rig.put_scene({"type": "image", "asset": "sha256:" + asset["sha256"], "fit": "contain"})
        rig.check(
            "A second guarded scene write is accepted before Show",
            status == 200,
            status,
            200,
            obligation="C-GUARD",
            fatal=True,
        )
        route.continue_()

    page.route("**/api/v3/scene", competing_write, times=1)
    before = _scene_scene_puts(rig)
    page.click("#show-image")
    wait_until(
        page,
        "() => /Could not show/.test(document.getElementById('image-message').textContent)",
        timeout=20,
    )
    page.wait_for_timeout(200)
    after = _scene_scene_puts(rig)
    rig.check(
        "A stale guard sends exactly one scene PUT and never retries",
        after - before == 1 and _scene_write_rows(rig, 0)[-1]["if_match"] == original_guard,
        {"before": before, "after": after, "sends": rig.requests[-4:]},
        {"delta": 1},
        obligation="C-GUARD",
    )

    message = _inner_text(page, "#image-message")
    rig.check(
        "The guarded failure message is plain and drops the server detail",
        "Could not show" in message and "configuration changed" not in message.lower(),
        message,
        {"contains": "Could not show", "excludes": "configuration changed"},
        obligation="D5",
    )
    conflict = page.locator("#conflict-panel")
    rig.check(
        "The global conflict panel remains visible after a guarded failure",
        conflict.count() == 1 and conflict.is_visible(),
        {"count": conflict.count(), "visible": conflict.is_visible() if conflict.count() else None},
        {"count": 1, "visible": True},
        obligation="C-GUARD",
    )
    draft = page.locator("#stage-draft-chip")
    rig.check(
        "The draft chip survives the guarded failure",
        draft.count() == 1 and draft.is_visible() and draft.inner_text().startswith("Draft:"),
        {"count": draft.count(), "visible": draft.is_visible() if draft.count() else None,
         "text": draft.inner_text() if draft.count() else ""},
        {"visible": True, "text": "Draft: …"},
        obligation="C-GUARD",
    )
    rebuild = page.locator("#image-rebuild")
    focus = page.evaluate("() => document.activeElement ? (document.activeElement.id || document.activeElement.tagName) : null")
    expected_focus = "image-rebuild" if rebuild.count() and rebuild.is_visible() else "image-message"
    rig.check(
        "A failed Show moves focus to the rebuild control, else the message, never search",
        focus == expected_focus,
        {"focus": focus, "rebuild_visible": rebuild.count() == 1 and rebuild.is_visible()},
        {"focus": expected_focus},
        obligation="D5",
    )

    before_recovery = _scene_scene_puts(rig)
    page.locator("#refresh-status").focus()
    page.keyboard.press("Enter")
    wait_until(page, "() => document.getElementById('etag-state').textContent === 'current'")
    page.wait_for_timeout(200)
    rig.check(
        "Refresh status leaves Show disabled until manual Rebuild preview and sends no scene PUT",
        page.locator("#show-image").is_disabled()
        and page.locator("#image-rebuild").is_visible()
        and _scene_scene_puts(rig) == before_recovery,
        {"showDisabled": page.locator("#show-image").is_disabled(),
         "puts": _scene_scene_puts(rig) - before_recovery},
        {"showDisabled": True, "puts": 0},
        obligation="C-GUARD",
    )
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("#image-rebuild").focus()
    page.keyboard.press("Enter")
    wait_until(page, "() => !document.getElementById('show-image').disabled")
    rig.check(
        "Explicit rebuild clears the obsolete failure without writing content",
        not _inner_text(page, "#image-message")
        and _scene_scene_puts(rig) == before_recovery,
        {"message": _inner_text(page, "#image-message"),
         "puts": _scene_scene_puts(rig) - before_recovery},
        {"message": "", "puts": 0},
        obligation="C-GUARD",
    )
    page.locator("#show-image").focus()
    rebuilt_guard = rig.config()["etag"]
    with page.expect_response(lambda response: response.request.method == "PUT"
                              and _url_path({"url": response.url}).endswith("/api/v3/scene")) as response:
        page.keyboard.press("Enter")
    rig.check(
        "Show after explicit rebuild uses the new guard and succeeds once",
        response.value.status == 200 and _scene_scene_puts(rig) == before_recovery + 1
        and _scene_write_rows(rig, 0)[-1]["if_match"] == rebuilt_guard
        and rebuilt_guard != original_guard,
        {"status": response.value.status, "puts": _scene_scene_puts(rig) - before_recovery},
        {"status": 200, "puts": 1},
        obligation="C-GUARD",
    )


# ---------------------------------------------------------------------------
# saved-name-rule (D6, C-NAME)
# ---------------------------------------------------------------------------


def _layout_writes(rig: RenewalRig, start: int) -> list[dict[str, Any]]:
    return [row for row in rig.requests[start:]
            if row["method"] == "PUT" and ("/layouts" in row["url"] or "/logical-layouts" in row["url"])]


def _scene_writes(rig: RenewalRig, start: int) -> list[dict[str, Any]]:
    return [row for row in rig.requests[start:]
            if row["method"] == "PUT" and "/api/v3/scenes/" in row["url"]]


def saved_name_rule(rig: RenewalRig) -> None:
    page = rig.page
    _task(rig, "Saved")
    rule = "Use letters, numbers, spaces, dots, underscores or hyphens."
    before_any_submit = page.evaluate(
        """() => {
            const read = id => {
                const node = document.getElementById(id);
                return node ? {present: true, visible: node.getClientRects().length > 0,
                    text: node.textContent} : {present: false};
            };
            return {layout: read('layout-name-rule'), scene: read('scene-name-rule')};
        }"""
    )
    hints_ok = all(
        item["present"] and item["visible"]
        and "Use letters, numbers, spaces, dots, underscores or hyphens." in item["text"]
        and "64 characters at most." in item["text"]
        for item in (before_any_submit["layout"], before_any_submit["scene"])
    )
    rig.check(
        "Both name fields state the rule before any submit",
        hints_ok,
        before_any_submit,
        {"layout-name-rule": rule + " … 64 characters at most.",
         "scene-name-rule": rule + " … 64 characters at most."},
        obligation="C-NAME",
    )

    described = page.evaluate(
        """() => ({
            layout: (document.getElementById('layout-name') || {}).getAttribute
                ? document.getElementById('layout-name').getAttribute('aria-describedby') : null,
            scene: (document.getElementById('scene-name') || {}).getAttribute
                ? document.getElementById('scene-name').getAttribute('aria-describedby') : null,
        })"""
    )
    def described_before(tokens: str | None, rule_id: str, message_id: str) -> bool:
        parts = (tokens or "").split()
        return rule_id in parts and message_id in parts and parts.index(rule_id) < parts.index(message_id)

    described_ok = (
        described_before(described["layout"], "layout-name-rule", "layout-msg")
        and described_before(described["scene"], "scene-name-rule", "scene-message")
    )
    rig.check(
        "Both name fields describe themselves with the rule before their message",
        described_ok,
        described,
        {"layout-name": "layout-name-rule layout-msg", "scene-name": "scene-name-rule scene-message"},
        obligation="D6",
    )

    start = len(rig.requests)
    page.fill("#layout-name", "Harbour dawn, fit")
    page.locator("#btn-layout-save").click()
    page.wait_for_timeout(400)
    layout_writes = _layout_writes(rig, start)
    rig.check(
        "A rejected arrangement name sends no layout write",
        not layout_writes,
        layout_writes,
        [],
        obligation="C-NAME",
    )
    rig.check(
        "A rejected arrangement name keeps focus in its field",
        page.evaluate("() => document.activeElement?.id") == "layout-name",
        page.evaluate("() => document.activeElement?.id"),
        "layout-name",
        obligation="C-NAME",
    )
    rule_message = _inner_text(page, "#layout-msg")
    rig.check(
        "A rejected arrangement name shows the rule text",
        "Use letters, numbers, spaces, dots, underscores or hyphens." in rule_message,
        rule_message,
        rule,
        obligation="C-NAME",
    )

    start = len(rig.requests)
    page.fill("#layout-name", "Harbour dawn fit")
    page.locator("#btn-layout-save").click()
    wait_until(page, "() => /saved/i.test(document.getElementById('layout-msg').textContent)", timeout=20)
    saved_layouts = _layout_writes(rig, start)
    rig.check(
        "An accepted arrangement name still saves with one guarded write",
        len(saved_layouts) == 1 and "Harbour%20dawn%20fit" in saved_layouts[0]["url"]
        and bool(saved_layouts[0]["if_match"]),
        saved_layouts,
        {"writes": 1, "name": "Harbour%20dawn%20fit", "if_match": True},
        obligation="C-NAME",
    )

    asset = rig.assets[0]
    status, _ = rig.put_scene({"type": "image", "asset": "sha256:" + asset["sha256"], "fit": "cover"})
    rig.check(
        "An applied image exists before the content name checks",
        status == 200,
        status,
        200,
        obligation="C-NAME",
        fatal=True,
    )
    wait_until(
        page,
        "() => { const value = document.getElementById('etag-value'); const state = document.getElementById('etag-state');"
        " return value && state && state.textContent === 'current'; }",
        timeout=20,
    )
    _task(rig, "Saved")

    start = len(rig.requests)
    page.fill("#scene-name", "Harbour dawn, fit")
    page.locator("#scene-save").click()
    page.wait_for_timeout(400)
    scene_writes = _scene_writes(rig, start)
    rig.check(
        "A rejected content name sends no scene write",
        not scene_writes,
        scene_writes,
        [],
        obligation="C-NAME",
    )
    rig.check(
        "A rejected content name keeps focus in its field",
        page.evaluate("() => document.activeElement?.id") == "scene-name",
        page.evaluate("() => document.activeElement?.id"),
        "scene-name",
        obligation="C-NAME",
    )
    scene_message = _inner_text(page, "#scene-message")
    rig.check(
        "A rejected content name shows the rule text",
        "Use letters, numbers, spaces, dots, underscores or hyphens." in scene_message,
        scene_message,
        rule,
        obligation="C-NAME",
    )

    start = len(rig.requests)
    page.fill("#scene-name", "Harbour dawn fit")
    page.locator("#scene-save").click()
    wait_until(page, "() => /Content saved/.test(document.getElementById('scene-message').textContent)", timeout=20)
    saved_scenes = _scene_writes(rig, start)
    rig.check(
        "An accepted content name still saves with one guarded write",
        len(saved_scenes) == 1 and "Harbour%20dawn%20fit" in saved_scenes[0]["url"]
        and bool(saved_scenes[0]["if_match"]),
        saved_scenes,
        {"writes": 1, "name": "Harbour%20dawn%20fit", "if_match": True},
        obligation="C-NAME",
    )


# ---------------------------------------------------------------------------
# pattern-grouping (D7, C-PATTERN, C-GALLERY)
# ---------------------------------------------------------------------------


def pattern_grouping(rig: RenewalRig) -> None:
    page = rig.page
    _port_and_place(rig, 1)
    _task(rig, "Images")
    wait_until(page, "() => document.querySelectorAll('#image-gallery > li').length >= 8", timeout=20)
    rig.click("#pattern-black")
    wait_until(page, "() => document.querySelectorAll('#image-gallery > li').length >= 9", timeout=20)
    rig.click("#refresh-images")
    wait_until(
        page,
        "() => !document.getElementById('refresh-images').disabled"
        " && document.querySelectorAll('#image-gallery > li').length >= 9",
        timeout=20,
    )
    page.wait_for_timeout(200)
    last = page.evaluate(
        """() => {
            const items = [...document.querySelectorAll('#image-gallery > li')];
            const item = items[items.length - 1];
            if (!item) return null;
            const button = item.querySelector('button');
            const name = item.querySelector('.image-choice-name');
            const tag = [...item.querySelectorAll('*')]
                .find(node => node.children.length === 0 && node.textContent.trim() === 'Test pattern');
            return {
                assetId: item.dataset.assetId || '',
                name: name ? name.textContent : '',
                text: item.textContent,
                tag: tag ? {present: true, visible: tag.getClientRects().length > 0} : {present: false},
                ariaLabel: button ? button.getAttribute('aria-label') : null,
                buttons: items.length,
                tabStops: [...document.querySelectorAll('#image-gallery [tabindex="0"]')].length,
            };
        }"""
    )
    if last is None:
        raise RuntimeError("image gallery is empty after Black wall and Refresh images")
    expected_name = "wall-pattern-" + last["assetId"][len("sha256:"):] + ".png"
    rig.check(
        "The generated pattern sorts last and keeps its exact published name",
        last["assetId"].startswith("sha256:") and last["name"] == expected_name,
        {"assetId": last["assetId"], "name": last["name"], "position": last["buttons"]},
        {"assetId": "sha256:…", "name": expected_name, "last": True},
        obligation="D7",
    )
    rig.check(
        "The pattern tile shows a visible Test pattern tag",
        last["tag"]["present"] and last["tag"]["visible"],
        last["tag"],
        {"tag": "Test pattern", "visible": True},
        obligation="C-PATTERN",
    )
    rig.check(
        "The pattern tile accessible name ends with the test-pattern suffix",
        bool(last["ariaLabel"]) and last["ariaLabel"].endswith(", test pattern"),
        last["ariaLabel"],
        {"endsWith": ", test pattern"},
        obligation="C-PATTERN",
    )
    rig.check(
        "The gallery keeps exactly one Tab stop",
        last["tabStops"] == 1,
        {"tabStops": last["tabStops"]},
        {"tabStops": 1},
        obligation="C-GALLERY",
    )

    page.locator("#image-gallery > li").last.locator("button").click()
    wait_until(page, "() => document.body.dataset.outputDirty === 'true'", timeout=20)
    rig.check(
        "Selecting the pattern still starts a draft",
        page.evaluate("() => document.body.dataset.outputDirty === 'true'")
        and page.evaluate("() => !document.getElementById('show-image').disabled"),
        {"dirty": page.evaluate("() => document.body.dataset.outputDirty"),
         "show": page.evaluate("() => !document.getElementById('show-image').disabled")},
        {"dirty": "true", "show": True},
        obligation="C-GALLERY",
    )


# ---------------------------------------------------------------------------
# layout-foundation (C-LAYOUT, C-TOUCH)
# ---------------------------------------------------------------------------


def _layout_check(rig: RenewalRig, task: str, label: str, measured: dict[str, Any]) -> None:
    paddings = measured["paddings"]
    gutter_ok = bool(paddings) and all(value >= 12 for _, value in paddings)
    headings_ok = all(len(measured["headings"].get(level, [])) <= 1 for level in ("h2", "h3"))
    heading_levels = {level: measured["headings"].get(level, []) for level in ("h2", "h3")}
    text_checked = task in ("Saved", "Settings", "Tablets")
    text_ok = (not text_checked) or (
        measured["textCount"] > 0 and not measured["textOffenders"]
    )
    ok = (measured["panel"] is not None
          and measured["scrollWidth"] <= measured["innerWidth"]
          and gutter_ok and headings_ok and text_ok)
    scope = ", text inside the gutter" if text_checked else ""
    rig.check(
        f"{label} {task}: no horizontal overflow, 12px gutter, one heading size{scope}",
        ok,
        {
            "panel": measured["panel"],
            "scrollWidth": measured["scrollWidth"],
            "innerWidth": measured["innerWidth"],
            "paddings": paddings,
            "headings": heading_levels,
            "textCount": measured["textCount"],
            "textOffenders": measured["textOffenders"][:6],
        },
        {
            "panel": "visible",
            "scrollWidth": "<= innerWidth",
            "paddingInlineStart": ">= 12",
            "headingSizesPerLevel": "<= 1",
            "text": "left >= 12 and right <= innerWidth - 12" if text_checked else "not checked for this task",
        },
        obligation="C-LAYOUT",
    )


def layout_foundation(rig: RenewalRig) -> None:
    page = rig.page
    _port_and_place(rig, 1)

    def measure_viewport(label: str, width: int, height: int) -> None:
        page.set_viewport_size({"width": width, "height": height})
        page.wait_for_timeout(120)
        for task in TASK_NAMES:
            _task(rig, task)
            measured = page.evaluate(LAYOUT_MEASURE)
            _layout_check(rig, task, label, measured)

    for width, height in VIEWPORTS:
        measure_viewport(f"{width}x{height}", width, height)

    for width, height in ((1440, 900), (1280, 800)):
        page.set_viewport_size({"width": width, "height": height})
        page.wait_for_timeout(120)
        for task, rail_selector, wall_selector in (
            ("Images", "#exception-rail", "#wall-context-content"),
            ("Arrange", ".arrange-tools", ".arrange-result"),
        ):
            _task(rig, task)
            placed = page.evaluate(
                """selectors => {
                    const rail = document.querySelector(selectors.rail);
                    const wall = document.querySelector(selectors.wall);
                    const rect = node => node ? node.getBoundingClientRect() : null;
                    const railRect = rect(rail), wallRect = rect(wall);
                    return {
                        rail: railRect && {left: railRect.left, right: railRect.right,
                            width: railRect.width, height: railRect.height},
                        wall: wallRect && {left: wallRect.left, right: wallRect.right,
                            width: wallRect.width, height: wallRect.height},
                        inside: !!railRect && !!wallRect
                            && railRect.right <= innerWidth + 0.5 && wallRect.right <= innerWidth + 0.5
                            && railRect.left >= -0.5 && wallRect.left >= -0.5,
                        separate: !!railRect && !!wallRect
                            && (wallRect.right <= railRect.left + 0.5 || railRect.right <= wallRect.left + 0.5),
                    };
                }""",
                {"rail": rail_selector, "wall": wall_selector},
            )
            rig.check(
                f"{width}x{height} {task}: the rail and the wall are both visible and do not overlap",
                placed["inside"] and placed["separate"]
                and placed["rail"]["width"] > 0 and placed["wall"]["width"] > 0,
                placed,
                {"inside": True, "separate": True, "rail": "> 0 wide", "wall": "> 0 wide"},
                obligation="C-NAV",
            )

    # Exact fractional coverage is attempted first, then reported unproven if
    # the engine refuses. Integer measurements are additional coverage only.
    for requested in FRACTIONAL_WIDTHS:
        width = resolved_width(requested)
        attempt: dict[str, Any] = {"requested": requested, "resolved_width": width}
        exact = False
        try:
            page.set_viewport_size({"width": requested, "height": 900})  # type: ignore[arg-type]
            page.wait_for_timeout(120)
            measured_visual = page.evaluate(
                "() => window.visualViewport ? window.visualViewport.width : innerWidth"
            )
            attempt["measured_visual_width"] = measured_visual
            exact = measured_visual == requested
        except Exception as error:
            attempt["error"] = repr(error)
        if exact:
            for task in TASK_NAMES:
                _task(rig, task)
                _layout_check(rig, task, f"{requested}px", page.evaluate(LAYOUT_MEASURE))
            continue
        measure_viewport(
            f"additional coverage at engine width {width}px for requested {requested}px",
            width,
            900,
        )
        rig.check(
            f"Exact fractional CSS width {requested}px is unproven "
            f"(Chromium measured {width}px instead)",
            False,
            attempt,
            {"requested": requested, "measured_visual_width": requested},
            obligation="C-LAYOUT",
            incomplete_reason=(
                f"C-LAYOUT exact fractional width {requested}px was not measured. "
                f"Chromium device metrics accept only integer CSS widths, so the "
                f"{width}px layout is additional coverage, not proof of {requested}px."
            ),
        )

    coarse = rig.browser.new_context(
        viewport={"width": 390, "height": 844},
        has_touch=True,
        is_mobile=True,
        reduced_motion="reduce",
    )
    rig.contexts.append(coarse)
    coarse_page = coarse.new_page()
    coarse_page.set_default_timeout(10_000)
    rig.observe(coarse_page, "coarse-controller")
    coarse_page.goto(rig.base + "/controller/physical.html")
    wait_until(
        coarse_page,
        "() => document.getElementById('wall-health')?.textContent !== 'Checking tablet status…'",
    )
    rig.page = coarse_page
    try:
        for task in ("Images", "Tablets"):
            _task(rig, task)
            sweep = coarse_page.evaluate(CONTROL_SWEEP)
            coverage = touch_coverage(sweep, task)
            rig.check(
                f"Coarse pointer 390x844 {task}: the expected visible controls exist before sizing",
                coverage["ok"],
                coverage,
                {"ids": list(TOUCH_EXPECTED[task]["ids"]),
                 "classes": list(TOUCH_EXPECTED[task]["classes"]),
                 "controls": ">= 1"},
                obligation="C-TOUCH",
            )
            rig.check(
                f"Coarse pointer 390x844 {task}: every visible enabled control is at least 44px tall",
                sweep["coarse"] and sweep["count"] > 0 and sweep["short"] == [],
                {"coarse": sweep["coarse"], "count": sweep["count"],
                 "short": sweep["short"]},
                {"coarse": True, "count": "> 0", "short": []},
                obligation="C-TOUCH",
            )
    finally:
        rig.page = page

    empty_context = rig.browser.new_context(
        viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True
    )
    rig.contexts.append(empty_context)
    empty_page = empty_context.new_page()
    empty_page.set_content(
        "<!doctype html><section class='task-panel' id='panel-content'></section>"
    )
    empty_sweep = empty_page.evaluate(CONTROL_SWEEP)
    empty_verdict = touch_coverage(empty_sweep, "Images")
    rig.check(
        "The coarse-pointer predicate rejects a deliberately empty task panel",
        empty_sweep["panel"] == "panel-content"
        and empty_sweep["count"] == 0
        and not empty_verdict["ok"]
        and empty_verdict["missing_ids"] == list(TOUCH_EXPECTED["Images"]["ids"]),
        {"panel": empty_sweep["panel"], "count": empty_sweep["count"],
         "short": empty_sweep["short"], "verdict": empty_verdict},
        {"panel": "panel-content", "count": 0, "verdict": {"ok": False}},
        obligation="C-TOUCH",
    )

    for width, height, label in ((1280, 800, "1280x800"), (390, 844, "390x844")):
        page.set_viewport_size({"width": width, "height": height})
        page.wait_for_timeout(120)
        page.evaluate(
            "() => { const style = document.createElement('style'); style.id = 'renewal-text-200';"
            " style.textContent = 'html{font-size:200%}'; document.head.append(style); }"
        )
        try:
            for task in TASK_NAMES:
                _task(rig, task)
                overflow = page.evaluate(
                    "() => ({scrollWidth: document.documentElement.scrollWidth, innerWidth})"
                )
                rig.check(
                    f"CSS text 200% (emulation) {label} {task}: no horizontal overflow",
                    overflow["scrollWidth"] <= overflow["innerWidth"],
                    overflow,
                    {"scrollWidth": "<= innerWidth"},
                    obligation="C-LAYOUT",
                )
        finally:
            page.evaluate("() => document.getElementById('renewal-text-200')?.remove()")

    page.set_viewport_size({"width": 1440, "height": 900})


# ---------------------------------------------------------------------------
# Wave-2 shared helpers
# ---------------------------------------------------------------------------


def _url_path(row: dict[str, Any]) -> str:
    """The path of an absolute or relative request URL, without query or fragment."""
    raw = str(row.get("url") or "")
    return urlsplit(raw).path or raw.split("?", 1)[0]


def _layout_write_path(path: str) -> bool:
    """Whether a URL path is a durable v3 arrangement write, not a preview."""
    clean = path.rstrip("/") or "/"
    if clean == "/api/v3/grid":
        return True
    if clean.startswith("/api/v3/grid/"):
        return clean != "/api/v3/grid/preview"
    if clean == "/api/v3/layout" or clean.startswith("/api/v3/layout/"):
        return True
    if clean == "/api/v3/logical-layout" or clean.startswith("/api/v3/logical-layout/"):
        return True
    return (
        clean == "/api/v3/layouts"
        or clean.startswith("/api/v3/layouts/")
        or clean == "/api/v3/logical-layouts"
        or clean.startswith("/api/v3/logical-layouts/")
    )


def _controller_write_rows(
    rig: RenewalRig, start: int, end: int | None = None
) -> list[dict[str, Any]]:
    """Non-GET requests issued by the operator page in ``[start, end)``."""
    return [
        row
        for row in rig.requests[start:end]
        if row.get("page") == "controller" and row.get("method") not in ("GET", "HEAD")
    ]


def _restart_interval_writes(
    rig: RenewalRig,
    *,
    post_show: int,
    before_restart: int,
    after_restart: int,
) -> dict[str, list[dict[str, Any]]]:
    """Automatic writes in the contiguous interval from after the failed Show to readiness."""
    return {
        "after_show_before_restart": _controller_write_rows(rig, post_show, before_restart),
        "during_restart_startup": _controller_write_rows(rig, before_restart, after_restart),
    }


def _layout_write_rows(rig: RenewalRig, start: int) -> list[dict[str, Any]]:
    """Durable arrangement writes since ``start``; previews are not writes."""
    rows = []
    for row in rig.requests[start:]:
        if row.get("page") != "controller" or row.get("method") not in ("PUT", "POST", "DELETE"):
            continue
        if _layout_write_path(_url_path(row)):
            rows.append(row)
    return rows


def _scene_write_rows(rig: RenewalRig, start: int) -> list[dict[str, Any]]:
    return [
        row
        for row in rig.requests[start:]
        if row.get("page") == "controller"
        and row.get("method") == "PUT"
        and _url_path(row).endswith("/api/v3/scene")
    ]


def _place_grid(
    rig: RenewalRig, clients: list[tuple[Any, str]], width: int, height: int, columns: int
) -> list[str]:
    """Place the joined clients on a logical wall with ``columns`` per row."""
    ids = [device_id for _, device_id in clients]
    status, _ = rig.request("PUT", "/wall", {"width": width, "height": height})
    if status != 200:
        raise RuntimeError(f"logical wall write failed: {status}")
    rows = max(1, math.ceil(len(ids) / columns))
    cell_width = max(1, width // columns)
    cell_height = max(1, height // rows)
    for index, device_id in enumerate(ids):
        status, _ = rig.request(
            "PUT",
            f"/devices/{device_id}/placement",
            {
                "x": (index % columns) * cell_width,
                "y": (index // columns) * cell_height,
                "w": cell_width,
                "h": cell_height,
            },
        )
        if status != 200:
            raise RuntimeError(f"placement write failed for {index}: {status}")
    rig.wait_config(
        lambda config: all(device_id in config["layout"]["placements"] for device_id in ids),
        timeout=20,
    )
    return ids


def _gallery_metrics(page: Any, *, reset_scroll: bool = True) -> dict[str, Any]:
    return page.evaluate(
        """reset => {
            const gallery = document.getElementById('image-gallery');
            if (!gallery) return {present: false};
            if (reset) gallery.scrollTop = 0;
            const g = gallery.getBoundingClientRect();
            const tiles = [...gallery.children].filter(li => !li.hidden).map(li => {
                const button = li.querySelector('button');
                const name = li.querySelector('.image-choice-name');
                const size = li.querySelector('.image-size');
                const img = li.querySelector('img');
                const rect = li.getBoundingClientRect();
                const imageRect = img ? img.getBoundingClientRect() : null;
                return {
                    assetId: li.dataset.assetId || '',
                    name: name ? name.textContent : null,
                    buttonText: button ? button.textContent.trim() : null,
                    ariaLabel: button ? button.getAttribute('aria-label') : null,
                    imageSize: size ? size.textContent.trim() : null,
                    rect: {top: rect.top, bottom: rect.bottom, left: rect.left, right: rect.right},
                    img: imageRect ? {
                        width: imageRect.width,
                        height: imageRect.height,
                        objectFit: getComputedStyle(img).objectFit,
                        hidden: img.hidden,
                        complete: img.complete,
                        naturalWidth: img.naturalWidth,
                        naturalHeight: img.naturalHeight,
                        currentSrc: img.currentSrc,
                    } : null,
                    insideGallery: rect.top >= g.top - 1 && rect.bottom <= g.bottom + 1
                        && rect.left >= g.left - 1 && rect.right <= g.right + 1,
                    insideViewport: rect.top >= -1 && rect.bottom <= innerHeight + 1
                        && rect.left >= -1 && rect.right <= innerWidth + 1,
                };
            });
            return {
                present: true,
                gallery: {
                    top: g.top, bottom: g.bottom, left: g.left, right: g.right,
                    clientHeight: gallery.clientHeight,
                    scrollHeight: gallery.scrollHeight,
                    overflowY: getComputedStyle(gallery).overflowY,
                    scrollTop: gallery.scrollTop,
                },
                tiles,
                innerWidth,
                innerHeight,
                scrollY: window.scrollY,
            };
        }""",
        reset_scroll,
    )


def _whole_image_ok(
    tile: dict[str, Any] | None, expected_width: int, expected_height: int
) -> bool:
    """Whole-image proof: decoded expected pixels, contain fit, and aspect target."""
    if not tile or not tile.get("img"):
        return False
    img = tile["img"]
    if img.get("complete") is not True:
        return False
    if img.get("naturalWidth") != expected_width or img.get("naturalHeight") != expected_height:
        return False
    if img.get("hidden") or img.get("objectFit") != "contain":
        return False
    if not img.get("width") or not img.get("height"):
        return False
    aspect = img["width"] / img["height"]
    expected = expected_width / expected_height
    return abs(aspect / expected - 1) <= 0.02


def _drawing_metrics(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """() => {
            const host = document.getElementById('wall-context-content');
            const svg = document.getElementById('stage-svg');
            if (!host || !svg) return {present: false};
            const style = getComputedStyle(host);
            const innerWidth = host.clientWidth
                - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
            const innerHeight = host.clientHeight
                - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
            const rect = svg.getBoundingClientRect();
            const viewBox = svg.viewBox.baseVal;
            if (!viewBox.width || !viewBox.height) return {present: false};
            const widthBudget = innerWidth / viewBox.width;
            const heightBudget = innerHeight / viewBox.height;
            const limiting = widthBudget <= heightBudget ? 'width' : 'height';
            const fill = limiting === 'width' ? rect.width / innerWidth : rect.height / innerHeight;
            return {
                present: true,
                innerWidth, innerHeight,
                drawing: {width: rect.width, height: rect.height, left: rect.left, top: rect.top},
                viewBox: {width: viewBox.width, height: viewBox.height},
                limiting,
                fill,
            };
        }"""
    )


def _commit_positions(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """() => {
            const bar = document.getElementById('commit-bar');
            const evidence = document.querySelector('.commit-evidence');
            return {
                bar: bar ? getComputedStyle(bar).position : null,
                evidence: evidence ? getComputedStyle(evidence).position : null,
            };
        }"""
    )


def _select_gallery_image(rig: RenewalRig, index: int = 0) -> bool:
    page = rig.page
    tiles = page.locator("#image-gallery > li:not([hidden]) .image-choice-button")
    if tiles.count() <= index:
        return False
    tiles.nth(index).click()
    page.wait_for_timeout(120)
    return _soft_wait(
        page, "() => document.getElementById('show-image')?.disabled === false", timeout=15
    )


def _box_in_viewport(page: Any, selector: str) -> dict[str, Any]:
    locator = page.locator(selector)
    if not locator.count():
        return {"present": False, "inside": False}
    box = locator.first.bounding_box()
    viewport = page.evaluate("() => ({width: innerWidth, height: innerHeight})")
    if not box:
        return {"present": True, "inside": False, "visible": False, "viewport": viewport}
    inside = (
        box["x"] >= -0.5
        and box["y"] >= -0.5
        and box["x"] + box["width"] <= viewport["width"] + 0.5
        and box["y"] + box["height"] <= viewport["height"] + 0.5
    )
    return {"present": True, "inside": inside, "box": box, "viewport": viewport}


def _navigation_modes(page: Any) -> dict[str, bool]:
    return page.evaluate(
        """() => {
            const shown = node => {
                if (!node) return false;
                const style = getComputedStyle(node);
                return style.display !== 'none' && style.visibility !== 'hidden'
                    && node.getClientRects().length > 0;
            };
            return {
                tabs: shown(document.getElementById('rail-tabs')),
                compact: shown(document.getElementById('compact-task-select')),
            };
        }"""
    )


def _overflow(page: Any) -> dict[str, Any]:
    return page.evaluate(
        "() => ({scrollWidth: document.documentElement.scrollWidth, innerWidth})"
    )


def _roster_focus_metrics(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """() => {
            const active = document.activeElement;
            const roster = document.getElementById('exception-roster');
            if (!active || !roster || !roster.contains(active)) return {focusInside: false};
            let container = null, node = active.parentElement;
            while (node && node !== document.body) {
                const style = getComputedStyle(node);
                if (/(auto|scroll)/.test(style.overflowY + style.overflowX)) { container = node; break; }
                node = node.parentElement;
            }
            container = container || roster;
            const bounds = container.getBoundingClientRect();
            const rect = active.getBoundingClientRect();
            return {
                focusInside: true,
                inside: rect.top >= bounds.top - 1 && rect.bottom <= bounds.bottom + 1
                    && rect.left >= bounds.left - 1 && rect.right <= bounds.right + 1
                    && rect.top >= -1 && rect.bottom <= innerHeight + 1,
                container: container.id || String(container.className),
                activeId: active.closest('li') ? active.closest('li').dataset.deviceId : null,
                rect: {top: rect.top, bottom: rect.bottom, left: rect.left, right: rect.right},
                containerRect: {top: bounds.top, bottom: bounds.bottom, left: bounds.left, right: bounds.right},
                scrollY: window.scrollY,
            };
        }"""
    )


def _roster_focus_ok(
    reordered: bool,
    before: dict[str, Any],
    after: dict[str, Any],
    focused_id: str,
    scroll_before: float,
) -> bool:
    """The originally focused roster row keeps its identity, visible bounds and page scroll."""
    if not reordered or not before.get("focusInside") or not after.get("focusInside"):
        return False
    if not after.get("inside") or after.get("activeId") != focused_id:
        return False
    if after.get("scrollY") != scroll_before:
        return False
    return True


def _tablet_rows(page: Any) -> list[dict[str, Any]]:
    return page.evaluate(
        """() => [...document.querySelectorAll('#device-list .dev-row')].map(row => {
            const pick = row.querySelector('.dev-pick');
            return {
                id: row.dataset.deviceId,
                status: row.dataset.status,
                powerState: row.dataset.powerState,
                powerWarning: row.dataset.powerWarning,
                powerStale: row.dataset.powerStale,
                pickLabel: pick ? pick.getAttribute('aria-label') : null,
                facts: [...row.querySelectorAll('.dev-fact')].map(node => ({
                    fact: node.dataset.fact,
                    text: (node.textContent || '').trim(),
                })),
            };
        })"""
    )


def _fact(row: dict[str, Any], name: str) -> str | None:
    for fact in row["facts"]:
        if fact["fact"] == name:
            return fact["text"]
    return None


def _show_refusal_ok(
    *,
    present: bool,
    visible: bool,
    disabled: bool | None,
    attempted: bool,
    message_ok: bool,
    message_changed: bool,
    intended_writes: list[dict[str, Any]],
    success: bool,
) -> bool:
    """C-OFFLINE: an attempted Show is refused or uncertain; a disabled one writes nothing."""
    if success or not present or not visible:
        return False
    if attempted:
        return message_ok and message_changed
    if disabled is True:
        return not intended_writes
    return False


def _restart_server(rig: RenewalRig, suffix: str = "") -> dict[str, Any]:
    """Restart the private server on the same port and data roots."""
    listener = None
    for _ in range(50):
        candidate = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        candidate.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            candidate.bind(("127.0.0.1", rig.port))
            candidate.listen(128)
            listener = candidate
            break
        except OSError:
            candidate.close()
            time.sleep(0.2)
    if listener is None:
        raise RuntimeError(f"could not rebind private port {rig.port} for the restart")
    if rig.server_log is not None:
        try:
            rig.server_log.close()
        except OSError:
            pass
    log_path = rig.out / ("server-restart" + suffix + ".log")
    server, log, argv = launch_server(rig.source_root, rig.env, log_path, listener)
    listener.close()
    wait_ready(rig.base, server, log_path)
    rig.server = server
    rig.server_log = log
    rig.argv = argv
    return {"pid": server.pid, "log": str(log_path), "argv": argv}


# ---------------------------------------------------------------------------
# images-workbench (D9, D10, C-WORKBENCH, C-FOCUS-ROSTER)
# ---------------------------------------------------------------------------


def images_workbench(rig: RenewalRig) -> None:
    page = rig.page
    clients = [
        rig.new_client(CLIENT_SPECS[index % len(CLIENT_SPECS)], index)
        for index in range(6)
    ]
    ids = _place_grid(rig, clients, 1800, 1000, 3)
    _task(rig, "Images")
    wait_until(
        page, "() => document.querySelectorAll('#image-gallery > li').length === 10", timeout=40
    )
    wait_until(page, "() => document.querySelectorAll('#stage-svg .slot').length === 6", timeout=30)

    payload = rig.request("GET", "/api/v3/images")[1]
    images = payload.get("images", []) if isinstance(payload, dict) else []
    inventory = {item["name"]: item for item in images}
    rig.check(
        "The workbench serves the ten GENERATED FIXTURE images, including the three extreme shapes",
        len(images) == 10 and all(name in inventory for name, _, _ in WORKBENCH_SHAPES),
        {"count": len(images), "names": sorted(inventory)},
        {"count": 10, "shapes": [name for name, _, _ in WORKBENCH_SHAPES]},
        obligation="C-WORKBENCH",
    )

    def viewport(width: int, height: int) -> None:
        page.set_viewport_size({"width": width, "height": height})
        page.wait_for_timeout(180)
        page.evaluate("() => window.scrollTo(0, 0)")
        _task(rig, "Images")
        wait_until(
            page, "() => document.querySelectorAll('#stage-svg .slot').length === 6", timeout=20
        )

    # 1440x900: drawing width, gallery whole thumbnails, sticky bar, phone gate.
    viewport(1440, 900)
    shape_names = [name for name, _, _ in WORKBENCH_SHAPES]
    _soft_wait(
        page,
        "(names) => names.every(name => {"
        " const li = [...document.querySelectorAll('#image-gallery > li')]"
        "   .find(item => item.querySelector('.image-choice-name')?.textContent === name);"
        " const img = li?.querySelector('img');"
        " return !!img && img.complete && img.naturalWidth > 0 && img.naturalHeight > 0; })",
        arg=shape_names,
        timeout=20,
    )
    gallery = _gallery_metrics(page)
    whole = [
        tile for tile in gallery["tiles"] if tile["insideGallery"] and tile["insideViewport"]
    ]
    rig.check(
        "1440x900: at least six whole thumbnails lie inside the gallery's visible box at page scroll 0",
        gallery["scrollY"] == 0 and len(whole) >= 6,
        {"count": len(whole), "scrollY": gallery["scrollY"], "gallery": gallery["gallery"],
         "whole": [tile["name"] for tile in whole]},
        {"count": ">= 6", "scrollY": 0},
        obligation="C-WORKBENCH",
    )
    drawing = _drawing_metrics(page)
    rig.check(
        "1440x900: the six-tablet wall drawing is at least 900 px wide",
        drawing["present"] and drawing["drawing"]["width"] >= 900 - 0.5,
        drawing,
        {"drawing.width": ">= 900"},
        obligation="D9",
    )
    rig.check(
        "1440x900: the drawing fills at least 90% of the stage box in its limiting dimension",
        drawing["present"] and drawing["fill"] >= 0.9,
        {"fill": drawing.get("fill"), "limiting": drawing.get("limiting"),
         "drawing": drawing.get("drawing"),
         "inner": [drawing.get("innerWidth"), drawing.get("innerHeight")]},
        {"fill": ">= 0.9"},
        obligation="C-WORKBENCH",
    )
    for name, width, height in WORKBENCH_SHAPES:
        tile = next((item for item in gallery["tiles"] if item["name"] == name), None)
        aspect = (
            tile["img"]["width"] / tile["img"]["height"]
            if tile and tile["img"] and tile["img"]["height"]
            else None
        )
        expected = width / height
        ok = _whole_image_ok(tile, width, height)
        rig.check(
            f"1440x900: {name} is shown whole with decoded expected pixels, "
            "object-fit contain and its own aspect",
            ok,
            {"tile": tile, "expectedIntrinsic": [width, height],
             "expectedAspect": expected, "actualAspect": aspect},
            {"decoded": True, "intrinsic": [width, height],
             "objectFit": "contain", "aspectWithin": "2%"},
            obligation="C-WORKBENCH",
        )
    rig.check(
        "Gallery tile buttons keep the plain image name so gallery-focus still reads it",
        bool(gallery["tiles"])
        and all(tile["name"] and tile["buttonText"] == tile["name"] for tile in gallery["tiles"]),
        [{"name": tile["name"], "buttonText": tile["buttonText"]} for tile in gallery["tiles"]],
        {"buttonText": "equals the image name"},
        obligation="C-GALLERY",
    )
    sized = [tile for tile in gallery["tiles"] if tile["imageSize"]]
    sizes_ok = len(sized) == len(gallery["tiles"]) and all(
        tile["name"] in inventory
        and str(inventory[tile["name"]]["width"]) in tile["imageSize"]
        and str(inventory[tile["name"]]["height"]) in tile["imageSize"]
        for tile in sized
    )
    rig.check(
        "Each gallery tile states its pixel size under the name",
        sizes_ok,
        [{"name": tile["name"], "size": tile["imageSize"]} for tile in gallery["tiles"]],
        {"size": "width and height shown for every tile"},
        obligation="C-WORKBENCH",
    )
    commits = _commit_positions(page)
    rig.check(
        "1440x900: the commit bar is sticky and commit evidence stays in flow",
        commits["bar"] == "sticky" and commits["evidence"] not in ("sticky", "fixed"),
        commits,
        {"bar": "sticky", "evidence": "not sticky"},
        obligation="D10",
    )
    jump_display = page.evaluate(
        "() => { const node = document.getElementById('jump-to-library');"
        " return node ? getComputedStyle(node).display : null; }"
    )
    rig.check(
        "1440x900: the phone Choose an image button is not displayed",
        jump_display == "none",
        jump_display,
        "none",
        obligation="C-WORKBENCH",
    )
    selected = _select_gallery_image(rig, 0)
    show_box = _box_in_viewport(page, "#show-image")
    rig.check(
        "1440x900: Show image is fully inside the viewport after selecting",
        selected and show_box["inside"],
        {"selected": selected, "show": show_box},
        {"inside": True},
        obligation="C-WORKBENCH",
    )
    page.locator("#image-discard").click()
    page.wait_for_timeout(120)

    # Status-driven reorder: focus a row that stays, then take another tablet offline.
    roster_row = page.locator(f'#exception-roster li[data-device-id="{ids[0]}"] .exception-review')
    if roster_row.count():
        roster_row.focus()
    focus_before = _roster_focus_metrics(page)
    scroll_before = focus_before.get("scrollY")
    if scroll_before is None:
        scroll_before = page.evaluate("() => window.scrollY")
    _close_client(rig, clients[-1][0], ids[-1])
    reordered = _soft_wait(
        page,
        "(id) => document.querySelector('#exception-roster > li')?.dataset.deviceId === id",
        arg=ids[-1],
        timeout=20,
    )
    focus = _roster_focus_metrics(page)
    rig.check(
        "After a status-driven reorder the originally focused roster row keeps focus inside "
        "the roster box and the page does not scroll",
        _roster_focus_ok(reordered, focus_before, focus, ids[0], scroll_before),
        {"reordered": reordered, "focusBefore": focus_before, "focus": focus,
         "scrollBefore": scroll_before, "expectedFocusedId": ids[0]},
        {"reordered": True, "focusInside": True, "inside": True,
         "activeId": ids[0], "scrollY": scroll_before},
        obligation="C-FOCUS-ROSTER",
    )

    # 1280x800: drawing fill, four whole thumbnails, Show in viewport.
    viewport(1280, 800)
    drawing = _drawing_metrics(page)
    rig.check(
        "1280x800: the drawing fills at least 90% of the stage box in its limiting dimension",
        drawing["present"] and drawing["fill"] >= 0.9,
        {"fill": drawing.get("fill"), "limiting": drawing.get("limiting"),
         "drawing": drawing.get("drawing")},
        {"fill": ">= 0.9"},
        obligation="C-WORKBENCH",
    )
    gallery = _gallery_metrics(page)
    whole = [
        tile for tile in gallery["tiles"] if tile["insideGallery"] and tile["insideViewport"]
    ]
    rig.check(
        "1280x800: at least four whole thumbnails lie inside the gallery's visible box",
        len(whole) >= 4,
        {"count": len(whole), "whole": [tile["name"] for tile in whole]},
        {"count": ">= 4"},
        obligation="C-WORKBENCH",
    )
    selected = _select_gallery_image(rig, 0)
    show_box = _box_in_viewport(page, "#show-image")
    rig.check(
        "1280x800: Show image is fully inside the viewport after selecting",
        selected and show_box["inside"],
        {"selected": selected, "show": show_box},
        {"inside": True},
        obligation="C-WORKBENCH",
    )
    overflow = _overflow(page)
    rig.check(
        "1280x800: Images has no horizontal overflow",
        overflow["scrollWidth"] <= overflow["innerWidth"],
        overflow,
        {"scrollWidth": "<= innerWidth"},
        obligation="C-LAYOUT",
    )
    page.locator("#image-discard").click()
    page.wait_for_timeout(120)

    # 1280x800 with labelled CSS 200% text.
    page.set_viewport_size({"width": 1280, "height": 800})
    page.wait_for_timeout(120)
    page.evaluate(
        "() => { const style = document.createElement('style'); style.id = 'renewal-text-200';"
        " style.textContent = 'html{font-size:200%}'; document.head.append(style); }"
    )
    try:
        _task(rig, "Images")
        selected = _select_gallery_image(rig, 0)
        show_box = _box_in_viewport(page, "#show-image")
        overflow = _overflow(page)
        rig.check(
            "CSS text 200% (emulation) 1280x800: Show image is inside the viewport and "
            "there is no horizontal overflow",
            selected and show_box["inside"] and overflow["scrollWidth"] <= overflow["innerWidth"],
            {"selected": selected, "show": show_box, "overflow": overflow},
            {"inside": True, "scrollWidth": "<= innerWidth"},
            obligation="C-WORKBENCH",
        )
    finally:
        page.evaluate("() => document.getElementById('renewal-text-200')?.remove()")
        try:
            page.locator("#image-discard").click(timeout=2000)
        except Exception:
            pass

    # 390x844 phone reach.
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(180)
    page.evaluate("() => window.scrollTo(0, 0)")
    _task(rig, "Images")
    jump = page.locator("#jump-to-library")
    jump_visible = jump.count() == 1 and jump.is_visible()
    jump_box = jump.first.bounding_box() if jump.count() else None
    rig.check(
        "390x844: Choose an image is visible at the top of the page",
        jump_visible and jump_box is not None and jump_box["y"] <= 844,
        {"visible": jump_visible, "box": jump_box},
        {"visible": True, "top": "<= 844"},
        obligation="C-WORKBENCH",
    )
    focused_gallery = False
    if jump_visible:
        jump.first.click()
        focused_gallery = _soft_wait(
            page,
            "() => document.getElementById('image-gallery')?.contains(document.activeElement)",
            timeout=10,
        )
    rig.check(
        "390x844: one activation of Choose an image puts focus in the gallery",
        focused_gallery,
        page.evaluate(
            "() => ({tag: document.activeElement?.tagName, id: document.activeElement?.id,"
            " inGallery: !!document.getElementById('image-gallery')?.contains(document.activeElement)})"
        ),
        {"inGallery": True},
        obligation="C-WORKBENCH",
    )
    gallery = _gallery_metrics(page, reset_scroll=False)
    in_view = [tile for tile in gallery["tiles"] if tile["insideViewport"]]
    rig.check(
        "390x844: after one activation at least two whole thumbnails are in the viewport",
        len(in_view) >= 2,
        {"count": len(in_view), "inView": [tile["name"] for tile in in_view]},
        {"count": ">= 2"},
        obligation="C-WORKBENCH",
    )
    selected = _select_gallery_image(rig, 0)
    show_box = _box_in_viewport(page, "#show-image")
    overflow = _overflow(page)
    rig.check(
        "390x844: Show image is inside the viewport after selecting and there is no overflow",
        selected and show_box["inside"] and overflow["scrollWidth"] <= overflow["innerWidth"],
        {"selected": selected, "show": show_box, "overflow": overflow},
        {"inside": True, "scrollWidth": "<= innerWidth"},
        obligation="C-WORKBENCH",
    )
    commits = _commit_positions(page)
    rig.check(
        "390x844: the commit bar is sticky at phone height and commit evidence stays in flow",
        commits["bar"] == "sticky" and commits["evidence"] not in ("sticky", "fixed"),
        commits,
        {"bar": "sticky", "evidence": "not sticky"},
        obligation="D10",
    )
    page.locator("#image-discard").click()
    page.wait_for_timeout(120)

    # 320x740: no overflow, Show reachable by scrolling.
    page.set_viewport_size({"width": 320, "height": 740})
    page.wait_for_timeout(180)
    _task(rig, "Images")
    overflow = _overflow(page)
    rig.check(
        "320x740: Images has no horizontal overflow",
        overflow["scrollWidth"] <= overflow["innerWidth"],
        overflow,
        {"scrollWidth": "<= innerWidth"},
        obligation="C-LAYOUT",
    )
    selected = _select_gallery_image(rig, 0)
    page.locator("#show-image").scroll_into_view_if_needed()
    show_box = _box_in_viewport(page, "#show-image")
    rig.check(
        "320x740: Show image is reachable by scrolling",
        selected and show_box["inside"],
        {"selected": selected, "show": show_box},
        {"inside": True},
        obligation="C-WORKBENCH",
    )
    page.locator("#image-discard").click()
    page.wait_for_timeout(120)

    coarse = rig.browser.new_context(
        viewport={"width": 320, "height": 740},
        has_touch=True,
        is_mobile=True,
        reduced_motion="reduce",
    )
    rig.contexts.append(coarse)
    coarse_page = coarse.new_page()
    coarse_page.set_default_timeout(10_000)
    rig.observe(coarse_page, "coarse-controller")
    coarse_page.goto(rig.base + "/controller/physical.html")
    wait_until(
        coarse_page,
        "() => document.getElementById('wall-health')?.textContent !== 'Checking tablet status…'",
    )
    rig.page = coarse_page
    try:
        _task(rig, "Images")
        sweep = coarse_page.evaluate(CONTROL_SWEEP)
        coverage = touch_coverage(sweep, "Images")
        rig.check(
            "Coarse pointer 320x740 Images: the expected visible controls exist before sizing",
            coverage["ok"],
            coverage,
            {"ids": list(TOUCH_EXPECTED["Images"]["ids"]), "controls": ">= 1"},
            obligation="C-TOUCH",
        )
        rig.check(
            "Coarse pointer 320x740 Images: every visible enabled control is at least 44px tall",
            sweep["coarse"] and sweep["count"] > 0 and sweep["short"] == [],
            {"coarse": sweep["coarse"], "count": sweep["count"], "short": sweep["short"]},
            {"coarse": True, "count": "> 0", "short": []},
            obligation="C-TOUCH",
        )
    finally:
        rig.page = page

    # 844x390: the commit bar is not sticky at landscape phone height.
    page.set_viewport_size({"width": 844, "height": 390})
    page.wait_for_timeout(180)
    _task(rig, "Images")
    commits = _commit_positions(page)
    rig.check(
        "844x390: the commit bar exists and is not sticky, and commit evidence stays in flow",
        commits["bar"] not in (None, "sticky")
        and commits["evidence"] not in ("sticky", "fixed"),
        commits,
        {"bar": "present and not sticky", "evidence": "not sticky"},
        obligation="D10",
    )

    # Fractional widths: integer additional coverage only; exact fractions stay unproven.
    for requested in FRACTIONAL_WIDTHS:
        width = resolved_width(requested)
        page.set_viewport_size({"width": width, "height": 900})
        page.wait_for_timeout(150)
        _task(rig, "Images")
        overflow = _overflow(page)
        modes = _navigation_modes(page)
        rig.check(
            f"Additional coverage at engine width {width}px for requested {requested}px: "
            "Images has no horizontal overflow",
            overflow["scrollWidth"] <= overflow["innerWidth"],
            overflow,
            {"scrollWidth": "<= innerWidth"},
            obligation="C-LAYOUT",
        )
        rig.check(
            f"Additional coverage at engine width {width}px for requested {requested}px: "
            "exactly one of the tabs or the compact select is visible",
            modes["tabs"] != modes["compact"],
            modes,
            {"tabs": "xor compact"},
            obligation="C-NAV",
        )

    page.set_viewport_size({"width": 1440, "height": 900})
    _task(rig, "Images")
    if page.locator("#image-discard").is_visible():
        page.locator("#image-discard").click()
    config = rig.config()
    layout = config["layout"]
    for placement in layout["placements"].values():
        placement["bezel"] = {edge: 1 for edge in ("left", "right", "top", "bottom")}
    status, payload = rig.request("PUT", "/api/v3/logical-layout",
                                  {key: layout[key] for key in ("width", "height", "placements")},
                                  if_match=config["etag"])
    if status != 200:
        raise RuntimeError(f"coverage fixture write failed: {status} {payload}")
    wait_until(page, "() => !document.getElementById('stage-key').hidden")
    for count in (6, 4):
        if count == 4:
            config = rig.config()
            placements = {
                device_id: {**config["layout"]["placements"][device_id],
                            "x": 160 if index % 2 else 0, "y": 100 if index >= 2 else 0,
                            "w": (160, 63, 160, 46)[index], "h": 100}
                for index, device_id in enumerate(ids[:4])
            }
            status, payload = rig.request("PUT", "/api/v3/logical-layout",
                                    {"width": 223, "height": 200, "placements": placements},
                                    if_match=config["etag"])
            if status != 200:
                raise RuntimeError(f"near-square fixture write failed: {status} {payload}")
            wait_until(page, "() => document.querySelectorAll('#stage-svg .slot').length === 4")
        for width, height in ((1440, 900), (1280, 800)):
            page.set_viewport_size({"width": width, "height": height})
            for draft in (False, True):
                if draft:
                    _select_gallery_image(rig, 0)
                page.locator("#view-zoom-fit").click()
                page.evaluate("() => window.scrollTo(0, 0)")
                page.wait_for_timeout(250)
                fit = page.evaluate("""() => {
                    const box = document.getElementById('wall-context-content');
                    const rect = box.getBoundingClientRect();
                    const inside = node => { const r = node.getBoundingClientRect();
                        return r.width > 0 && r.height > 0 && r.top >= rect.top - .5
                            && r.bottom <= rect.bottom + .5 && r.left >= rect.left - .5
                            && r.right <= rect.right + .5; };
                    const slots = [...document.querySelectorAll('#stage-svg .slot')];
                    const drawn = slots.map(node => node.getBoundingClientRect());
                    return {range: box.scrollHeight - box.clientHeight,
                        slots: slots.map(inside),
                        drawingWidth: Math.max(...drawn.map(r => r.right)) - Math.min(...drawn.map(r => r.left)),
                        coverage: inside(document.getElementById('stage-key')),
                        details: inside(document.querySelector('#stage-technical > summary')),
                        horizontalOverflow: document.documentElement.scrollWidth - innerWidth};
                }""")
                rig.check(
                    f"Fit {count} tablets {width}x{height} draft={draft}: tiles, coverage and Stage details fit without inner scrolling",
                    fit["range"] == 0 and len(fit["slots"]) == count and all(fit["slots"])
                    and fit["coverage"] and fit["details"] and fit["horizontalOverflow"] == 0,
                    fit,
                    {"range": 0, "slots": [True] * count, "coverage": True,
                     "details": True, "horizontalOverflow": 0},
                    obligation="C-WORKBENCH",
                )
                if count == 6 and width == 1440:
                    drawing = _drawing_metrics(page)
                    rig.check(
                        f"Fit six tablets draft={draft}: drawing remains at least 900px wide",
                        drawing["drawing"]["width"] >= 899.5 and fit["drawingWidth"] >= 899.5,
                        {"svg": drawing, "tilesWidth": fit["drawingWidth"]},
                        {"drawing.width": ">= 900"},
                        obligation="D9",
                    )
                if draft:
                    show = _box_in_viewport(page, "#show-image")
                    rig.check(f"Fit {count} tablets {width}px: Show stays visible with a draft",
                              show["inside"], show, {"inside": True}, obligation="D10")
                rig.shot(f"fit-{count}-{width}-draft-{draft}")
                if draft:
                    page.locator("#image-discard").click()
    page.locator("#view-zoom-2x").click()
    pan = page.evaluate("() => {const n=document.getElementById('stage-scroll');"
                        "return {x:n.scrollWidth-n.clientWidth,y:n.scrollHeight-n.clientHeight};}")
    rig.check("2x retains intentional stage scrolling", pan["x"] > 0 or pan["y"] > 0,
              pan, {"x or y": "> 0"}, obligation="C-WORKBENCH")
    page.locator("#view-zoom-fit").click()
    page.set_viewport_size({"width": 390, "height": 844})
    page.add_style_tag(content="html {font-size:200%}")
    _task(rig, "Settings")
    page.locator("#backup-restore > summary").click()
    paths = page.evaluate("""() => ({
        open: document.getElementById('backup-restore').open,
        width: innerWidth, documentWidth: document.documentElement.scrollWidth,
        rows: [...document.querySelectorAll('#operator-readiness-paths dd')]
            .map(node => ({width: node.clientWidth, content: node.scrollWidth}))
    })""")
    rig.check("Open Data paths at 390px CSS200 wraps every value without horizontal overflow",
              paths["open"] and paths["documentWidth"] <= paths["width"]
              and len(paths["rows"]) >= 4
              and all(row["content"] <= row["width"] for row in paths["rows"]),
              paths, {"open": True, "documentWidth": "<= width", "rows": "all fit"},
              obligation="C-LAYOUT")
    page.locator("#readiness-paths").scroll_into_view_if_needed()
    rig.shot("open-data-paths-390-css200")


# ---------------------------------------------------------------------------
# first-wall (D11, D12, C-GUARD, C-STATUS, C-GEOMETRY)
# ---------------------------------------------------------------------------


def _first_wall_step_texts(page: Any) -> list[str]:
    steps = page.locator("#first-wall-steps")
    if not steps.count():
        return []
    return steps.locator("li").all_inner_texts()


def first_wall(rig: RenewalRig) -> None:
    page = rig.page
    wake_scripts = (WAKE_LOCK_DENIED, WAKE_LOCK_HELD, WAKE_LOCK_DENIED, WAKE_LOCK_HELD)
    clients = [
        rig.new_client(CLIENT_SPECS[index], index, wake_scripts[index])
        for index in range(4)
    ]
    ids = [device_id for _, device_id in clients]
    expected_wake = {
        ids[index]: "held" if wake_scripts[index] == WAKE_LOCK_HELD else "denied"
        for index in range(4)
    }
    rig.wait_config(
        lambda config: all(
            config["runtime"]["devices"][device_id].get("wake_lock") == state
            for device_id, state in expected_wake.items()
        ),
        timeout=25,
    )
    _task(rig, "Tablets")
    wait_until(
        page,
        "(ids) => ids.every(id => {"
        " const row = document.querySelector('#device-list .dev-row[data-device-id=\"' + id + '\"]');"
        " return !!row && !!row.dataset.status && row.dataset.status !== 'offline'; })",
        arg=ids,
        timeout=25,
    )

    steps = page.locator("#first-wall-steps")
    steps_present = steps.count() == 1
    steps_visible = steps_present and steps.is_visible()
    rig.check(
        "First-wall steps are visible on Tablets before any wall exists",
        steps_visible,
        {"present": steps_present, "visible": steps_visible},
        {"present": True, "visible": True},
        obligation="D11",
    )
    texts = _first_wall_step_texts(page)
    joined = " ".join(texts)
    arranged_step = bool(re.search(r"not arranged yet|wall arranged", joined, re.IGNORECASE))
    image_step = bool(re.search(r"no image shown yet|image shown", joined, re.IGNORECASE))
    rig.check(
        "The first-wall steps name the joined tablets and the two unstarted steps",
        len(texts) == 3 and "4" in texts[0] and "tablet" in texts[0].lower()
        and arranged_step and image_step,
        {"texts": texts},
        {"count": 3, "step1": "4 tablets online",
         "step2": "Not arranged yet / Wall arranged", "step3": "No image shown yet / Image shown"},
        obligation="D11",
    )
    focused_preset = False
    if steps_visible:
        step_two = steps.locator("li").nth(1).locator("button").first
        if step_two.count():
            step_two.click()
            _wait_task_panel(rig, "Arrange")
            focused_preset = _soft_wait(
                page, "() => document.activeElement?.id === 'grid-2x2'", timeout=10
            )
    rig.check(
        "Step 2 opens Arrange and lands focus on the 2 by 2 preset",
        focused_preset,
        page.evaluate(
            "() => ({active: document.activeElement?.id, panel: document.querySelector('.task-panel:not([hidden])')?.id})"
        ),
        {"active": "grid-2x2"},
        obligation="D11",
    )

    # Place one tablet from a Tablets row, using the visible Place action only.
    _task(rig, "Tablets")
    wait_until(
        page,
        "(id) => !!document.querySelector('#device-list .dev-row[data-device-id=\"' + id + '\"] .dev-action')",
        arg=ids[0],
        timeout=20,
    )
    place_start = len(rig.requests)
    page.locator(
        f'#device-list .dev-row[data-device-id="{ids[0]}"] .dev-action'
    ).click()
    _wait_task_panel(rig, "Arrange")
    disabled_by_draft = _soft_wait(
        page, "() => document.getElementById('grid-2x2')?.disabled === true", timeout=15
    )
    shape_text = page.locator("#panel-show").inner_text()
    note_visible = (
        "Wall shapes are paused while your placement draft is open" in shape_text
    )
    rig.check(
        "Place from a Tablets row locks wall shapes and shows the pause note",
        disabled_by_draft and note_visible,
        {"grid2x2Disabled": disabled_by_draft, "noteVisible": note_visible,
         "shapeText": shape_text[:400]},
        {"grid2x2Disabled": True, "noteVisible": True},
        obligation="D12",
    )
    discards = page.evaluate(
        """() => [...document.querySelectorAll('#panel-show button')].map((button, index) => ({
            index,
            id: button.id,
            text: (button.textContent || '').trim(),
            aria: button.getAttribute('aria-label') || '',
            visible: button.getClientRects().length > 0,
            disabled: button.disabled,
        })).filter(item => item.visible && !item.disabled && item.id !== 'btn-cancel'
            && /discard/i.test(item.text + ' ' + item.aria))"""
    )
    discard_index = discards[0]["index"] if discards else None
    if discard_index is not None:
        page.locator("#panel-show button").nth(discard_index).focus()
        page.keyboard.press("Enter")
    else:
        page.locator("#btn-cancel").click()
    reenabled = _soft_wait(
        page, "() => document.getElementById('grid-2x2')?.disabled === false", timeout=15
    )
    rig.check(
        "The pause note's Discard re-enables wall shapes",
        note_visible and discard_index is not None and reenabled,
        {"noteVisible": note_visible, "discard": discards, "reenabled": reenabled},
        {"discard": "visible in the note", "reenabled": True},
        obligation="D12",
    )
    focus = page.evaluate("() => document.activeElement.id || document.activeElement.tagName")
    rig.check(
        "Keyboard Discard on the placement lock restores focus to a visible enabled grid action",
        focus in ("grid-2x2", "grid-preview")
        and page.locator("#" + focus).is_visible()
        and not page.locator("#" + focus).is_disabled(),
        focus,
        ["grid-2x2", "grid-preview"],
        obligation="D12",
    )
    rig.shot("place-lock-keyboard-discard-focus")
    place_writes = _layout_write_rows(rig, place_start)
    rig.check(
        "Placing and discarding a draft tablet sends no layout write",
        not place_writes,
        place_writes,
        [],
        obligation="C-GEOMETRY",
    )

    # Preview then Apply through the visible Arrange controls.
    _task(rig, "Arrange")
    wait_until(
        page,
        "() => document.querySelectorAll('#grid-order .tablet-order-row').length === 4",
        timeout=20,
    )
    if page.locator("#grid-kind").input_value() != "logical":
        page.select_option("#grid-kind", "logical")
        page.wait_for_timeout(150)
    page.fill("#grid-rows", "2")
    page.fill("#grid-columns", "2")
    if page.locator("#grid-holes").is_checked():
        page.uncheck("#grid-holes")
    page.wait_for_timeout(120)
    page.click("#grid-preview")
    preview_ready = _soft_wait(
        page, "() => document.getElementById('btn-apply')?.disabled === false", timeout=25
    )
    rig.check(
        "The four-tablet wall previews through the visible Arrange controls",
        preview_ready,
        page.evaluate(
            "() => ({applyDisabled: document.getElementById('btn-apply')?.disabled,"
            " message: document.getElementById('grid-message')?.textContent})"
        ),
        {"applyDisabled": False},
        obligation="C-GEOMETRY",
    )
    if preview_ready:
        page.click("#btn-apply")
    applied = _soft_wait(
        page, "() => document.body.dataset.stageMode === 'live'", timeout=25
    )
    rig.check(
        "Applying the first wall reaches the live stage",
        applied,
        page.evaluate(
            "() => ({stageMode: document.body.dataset.stageMode,"
            " message: document.getElementById('grid-message')?.textContent})"
        ),
        {"stageMode": "live"},
        obligation="C-GEOMETRY",
    )

    _task(rig, "Tablets")
    wait_until(
        page,
        "() => document.querySelectorAll('#device-list .dev-row').length >= 4",
        timeout=20,
    )
    hidden_after = steps.count() == 1 and not steps.is_visible()
    rig.check(
        "Applying the first wall hides the first-wall steps",
        hidden_after,
        {"present": steps.count(), "hidden": hidden_after},
        {"present": 1, "hidden": True},
        obligation="D11",
    )

    # Show the chosen image and prove exactly one guarded write and current paint.
    _task(rig, "Images")
    wait_until(
        page, "() => document.querySelectorAll('#image-gallery > li').length >= 8", timeout=30
    )
    selected = _select_gallery_image(rig, 0)
    show_start = len(rig.requests)
    if selected:
        page.click("#show-image")
    health = _soft_wait(
        page,
        "() => /4 of 4 showing the current image/.test("
        "document.getElementById('wall-health').textContent)",
        timeout=35,
    )
    puts = _scene_write_rows(rig, show_start)
    rig.check(
        "Show sends exactly one guarded PUT /api/v3/scene",
        selected and len(puts) == 1 and bool(puts[0].get("if_match")),
        {"selected": selected, "puts": puts},
        {"puts": 1, "if_match": True},
        obligation="C-GUARD",
    )
    config = None
    if health:
        config = rig.wait_config(
            lambda value: all(
                value["runtime"]["devices"][device_id]["render"].get("current") is True
                for device_id in ids
            ),
            timeout=30,
        )
    renders = (
        {device_id: config["runtime"]["devices"][device_id].get("render") for device_id in ids}
        if config
        else {}
    )
    current_paint = bool(renders) and all(
        render
        and render.get("current") is True
        and render.get("expected_token") == render.get("accepted_token")
        and render["accepted_token"].get("generation") == config["generation"]
        and render["accepted_token"].get("revision") == config["revision"]
        for render in renders.values()
    )
    rig.check(
        "All four clients report the current image paint",
        current_paint,
        renders,
        {"clients": 4, "current": True},
        obligation="C-STATUS",
    )
    health_text = _inner_text(page, "#wall-health")
    health_label = page.get_attribute("#btn-wall-health", "aria-label")
    rig.check(
        "The wall health line says 4 of 4 showing the current image",
        health_text == "4 of 4 showing the current image"
        and health_label == "4 of 4 tablets showing the current image. Issues.",
        {"text": health_text, "label": health_label},
        {"text": "4 of 4 showing the current image",
         "label": "4 of 4 tablets showing the current image. Issues."},
        obligation="C-STATUS",
    )

    # Arrange with a mixed wake-lock fleet: the shared stage must keep each
    # tablet's own power fact instead of depending on the Images fleet line.
    _task(rig, "Arrange")
    wait_until(
        page, "() => document.querySelectorAll('#stage-svg .slot').length === 4", timeout=20
    )
    slots = page.evaluate(
        """() => [...document.querySelectorAll('#stage-svg .slot')].map(slot => ({
            id: slot.dataset.deviceId,
            status: slot.dataset.status,
            powerState: slot.dataset.powerState,
            powerStale: slot.dataset.powerStale,
            text: (slot.textContent || '').trim(),
            label: slot.getAttribute('aria-label') || '',
        }))"""
    )
    expected_power = expected_wake
    by_id = {slot["id"]: slot for slot in slots}
    mixed_ok = len(slots) == 4 and all(
        by_id.get(device_id)
        and by_id[device_id]["powerState"] == state
        and state in by_id[device_id]["label"].lower()
        and (state != "denied" or state in by_id[device_id]["text"].lower())
        for device_id, state in expected_power.items()
    )
    rig.check(
        "Arrange (mixed wake locks): every stage slot keeps its own per-tablet power text",
        mixed_ok,
        {"slots": slots, "expected": expected_power},
        {"powerState": expected_power, "denied": "visible text on Arrange"},
        obligation="C-POWER",
    )


# ---------------------------------------------------------------------------
# tablet-facts (D13, C-RECOVERY, C-POWER, C-STATUS)
# ---------------------------------------------------------------------------


def tablet_facts(rig: RenewalRig) -> None:
    page = rig.page
    clients = [
        rig.new_client(CLIENT_SPECS[index], index, WAKE_LOCK_DENIED)
        for index in range(4)
    ]
    ids = [device_id for _, device_id in clients]
    placed = [clients[0], clients[1], clients[3]]
    _place_grid(rig, placed, 1200, 400, 3)
    rig.wait_config(
        lambda config: all(
            config["runtime"]["devices"][device_id].get("wake_lock") == "denied"
            for device_id in ids
        ),
        timeout=25,
    )
    asset = rig.assets[0]
    status, _ = rig.put_scene(
        {"type": "image", "asset": "sha256:" + asset["sha256"], "fit": "cover"}
    )
    if status != 200:
        raise RuntimeError(f"scene write failed: {status}")
    rig.wait_config(
        lambda config: all(
            config["runtime"]["devices"][device_id]["render"].get("state") == "displayed"
            for device_id in [ids[0], ids[1], ids[3]]
        ),
        timeout=30,
    )
    _close_client(rig, clients[3][0], ids[3])
    _task(rig, "Tablets")
    wait_until(
        page,
        "(ids) => ids.every(id => !!document.querySelector("
        "'#device-list .dev-row[data-device-id=\"' + id + '\"]'))",
        arg=ids,
        timeout=20,
    )
    wait_until(
        page,
        "(id) => document.querySelector('#device-list .dev-row[data-device-id=\"' + id + '\"]')"
        "?.dataset.status === 'offline'",
        arg=ids[3],
        timeout=20,
    )
    wait_until(
        page,
        "(id) => document.querySelector('#device-list .dev-row[data-device-id=\"' + id + '\"]')"
        "?.dataset.status === 'unplaced'",
        arg=ids[2],
        timeout=20,
    )

    rows = {row["id"]: row for row in _tablet_rows(page)}
    expected = {
        ids[0]: {"status": "displayed", "connection": "Connected",
                 "image": "Reports current image", "power": "Power denied"},
        ids[1]: {"status": "displayed", "connection": "Connected",
                 "image": "Reports current image", "power": "Power denied"},
        ids[2]: {"status": "unplaced", "connection": "Connected",
                 "image": None, "power": "Power denied"},
        ids[3]: {"status": "offline", "connection": None,
                 "image": None, "power": "Last known power denied"},
    }
    for device_id, want in expected.items():
        row = rows.get(device_id)
        facts = {fact["fact"]: fact["text"] for fact in (row or {}).get("facts", [])}
        connection = facts.get("connection")
        image = facts.get("image")
        power = facts.get("power")
        connection_ok = (
            connection == want["connection"]
            if want["connection"]
            else bool(connection and connection.startswith("Offline · last seen"))
        )
        image_ok = (
            image == want["image"]
            if want["image"]
            else (
                bool(image and "Offline" in image)
                if want["status"] == "offline"
                else bool(image and re.search(r"No placement|Not on the wall", image))
            )
        )
        rig.check(
            f"Tablet {device_id} shows three labelled facts with the expected connection, "
            "image and power text",
            row is not None
            and len(row["facts"]) == 3
            and set(facts) == {"connection", "image", "power"}
            and connection_ok
            and image_ok
            and power == want["power"]
            and row["status"] == want["status"],
            {"row": row, "facts": facts},
            {"facts": ["connection", "image", "power"], "status": want["status"]},
            obligation="D13",
        )

    power_expectations = {
        ids[0]: ("denied", "true", "false"),
        ids[1]: ("denied", "true", "false"),
        ids[2]: ("denied", "true", "false"),
        ids[3]: ("denied", "true", "true"),
    }
    power_ok = all(
        rows.get(device_id)
        and rows[device_id]["powerState"] == state
        and rows[device_id]["powerWarning"] == warning
        and rows[device_id]["powerStale"] == stale
        for device_id, (state, warning, stale) in power_expectations.items()
    )
    rig.check(
        "Every row keeps its per-device data-power attributes exactly",
        power_ok,
        {
            device_id: {
                "powerState": (rows.get(device_id) or {}).get("powerState"),
                "powerWarning": (rows.get(device_id) or {}).get("powerWarning"),
                "powerStale": (rows.get(device_id) or {}).get("powerStale"),
            }
            for device_id in power_expectations
        },
        {"state": "denied", "warning": "true", "stale": "false/true for offline"},
        obligation="C-POWER",
    )

    # Arrange with a uniform denied fleet: the shared stage must still show the
    # per-tablet power text instead of relying on the Images-only fleet line.
    _task(rig, "Arrange")
    wait_until(
        page, "() => document.querySelectorAll('#stage-svg .slot').length === 3", timeout=20
    )
    arrange_slots = page.evaluate(
        """() => [...document.querySelectorAll('#stage-svg .slot')].map(slot => ({
            id: slot.dataset.deviceId,
            status: slot.dataset.status,
            powerState: slot.dataset.powerState,
            powerStale: slot.dataset.powerStale,
            text: (slot.textContent || '').trim(),
            label: slot.getAttribute('aria-label') || '',
        }))"""
    )
    uniform_ok = len(arrange_slots) == 3 and all(
        slot["powerState"] == "denied"
        and "denied" in slot["label"].lower()
        and "denied" in slot["text"].lower()
        for slot in arrange_slots
    )
    rig.check(
        "Arrange (uniform denied): every stage slot keeps its per-tablet power text",
        uniform_ok,
        arrange_slots,
        {"powerState": "denied", "denied": "visible text on Arrange"},
        obligation="C-POWER",
    )
    _task(rig, "Tablets")
    wait_until(
        page,
        "(ids) => ids.every(id => !!document.querySelector("
        "'#device-list .dev-row[data-device-id=\"' + id + '\"]'))",
        arg=ids,
        timeout=20,
    )

    page.locator(f'#device-list .dev-pick[data-device-id="{ids[3]}"]').click()
    wait_until(page, "() => document.getElementById('device-sheet')?.open === true")
    pointer = page.get_by_role(
        "button", name="Review replacement with a new tablet", exact=True
    )
    pointer_visible = pointer.count() >= 1 and pointer.first.is_visible()
    rig.check(
        "An offline selected tablet offers the new-tablet replacement pointer",
        pointer_visible,
        {"count": pointer.count(),
         "visible": pointer.first.is_visible() if pointer.count() else None},
        {"visible": True},
        obligation="C-RECOVERY",
    )
    pointer_start = len(rig.requests)
    focused_offer = False
    if pointer_visible:
        pointer.first.click()
        focused_offer = _soft_wait(
            page,
            "() => document.getElementById('replacement-offer')?.contains(document.activeElement)",
            timeout=10,
        )
    rig.check(
        "Activating the replacement pointer focuses inside the replacement offer",
        focused_offer,
        page.evaluate(
            "() => ({active: document.activeElement?.id, tag: document.activeElement?.tagName,"
            " offerVisible: !document.getElementById('replacement-offer')?.hidden,"
            " inside: !!document.getElementById('replacement-offer')?.contains(document.activeElement)})"
        ),
        {"inside": True},
        obligation="D13",
    )
    rebinds = [row for row in rig.requests[pointer_start:] if "rebind" in row["url"]]
    rig.check(
        "The replacement pointer sends no rebind request before Confirm",
        not rebinds,
        rebinds,
        [],
        obligation="C-RECOVERY",
    )

    page.locator(f'#device-list .dev-pick[data-device-id="{ids[3]}"]').click()
    wait_until(
        page,
        "(id) => document.querySelector('#device-list .dev-row[data-device-id=\"' + id + '\"]')"
        "?.dataset.selected === 'true'",
        arg=ids[3],
    )
    recovery = page.evaluate(
        """() => {
            const node = document.getElementById('tablet-recovery');
            if (!node) return {present: false};
            return {
                present: true,
                hidden: node.hidden,
                paragraphs: node.querySelectorAll('p').length,
                text: node.textContent,
            };
        }"""
    )
    recovery_text = (recovery.get("text") or "").lower()
    rig.check(
        "The offline recovery guidance is three paragraphs that still say power, denied and cannot wake",
        recovery["present"]
        and not recovery["hidden"]
        and recovery["paragraphs"] == 3
        and "power" in recovery_text
        and "denied" in recovery_text
        and "cannot wake" in recovery_text,
        recovery,
        {"paragraphs": 3, "words": ["power", "denied", "cannot wake"]},
        obligation="C-RECOVERY",
    )

    stopped = stop_owned_server(rig.server)
    _write_json(
        rig.out / "server_stop.json",
        {
            "reason": "make the Tablets roster stale after the live fact checks",
            "restarted": False,
            "server": stopped,
        },
    )
    became_stale = _soft_wait(
        page, "() => document.body.dataset.connection === 'stale'", timeout=15
    )
    wait_until(
        page,
        "() => [...document.querySelectorAll('#device-list .dev-row')]"
        ".every(row => row.dataset.status === 'stale')",
        timeout=20,
    )
    stale_rows = _tablet_rows(page)
    stale_ok = became_stale and bool(stale_rows) and all(
        len(row["facts"]) == 3
        and set(fact["fact"] for fact in row["facts"]) == {"connection", "image", "power"}
        and _fact(row, "connection") == "Status stale"
        for row in stale_rows
    )
    rig.check(
        "A stale roster makes every Tablets row's connection fact read Status stale",
        stale_ok,
        {"connection": became_stale, "rows": stale_rows},
        {"connection": "stale", "fact": "Status stale"},
        obligation="D13",
    )


# ---------------------------------------------------------------------------
# measured-blockers (D12, C-GEOMETRY)
# ---------------------------------------------------------------------------


def measured_blockers(rig: RenewalRig) -> None:
    page = rig.page
    for index in range(3):
        rig.new_client(CLIENT_SPECS[index], index)
    _task(rig, "Arrange")
    wait_until(
        page,
        "() => document.querySelectorAll('#grid-order .tablet-order-row').length === 3",
        timeout=20,
    )
    page.select_option("#grid-kind", "physical")
    page.fill("#grid-rows", "1")
    page.fill("#grid-columns", "3")
    page.wait_for_timeout(250)
    labels = page.evaluate(
        """() => [...document.querySelectorAll('#grid-order .tablet-order-row')].map(row => {
            const select = row.querySelector('select[aria-label^="Mount angle for "]');
            return select ? select.getAttribute('aria-label').replace('Mount angle for ', '') : null;
        }).filter(Boolean)"""
    )
    preview_start = len(rig.requests)
    page.click("#grid-preview")
    messaged = _soft_wait(
        page,
        "() => /Declare the mounted top edge/.test("
        "document.getElementById('grid-message').textContent)",
        timeout=15,
    )
    buttons = page.evaluate(
        """() => [...document.querySelectorAll('#panel-show button')]
            .filter(button => {
                const name = (button.getAttribute('aria-label') || button.textContent || '').trim();
                return /: declare mounted top edge$/.test(name)
                    && button.getClientRects().length > 0 && !button.disabled;
            })
            .map(button => (button.getAttribute('aria-label') || button.textContent || '').trim())"""
    )
    expected_names = sorted(f"{label}: declare mounted top edge" for label in labels)
    rig.check(
        "A blocked measured preview names every blocking tablet with one button each",
        messaged and len(labels) == 3 and sorted(buttons) == expected_names,
        {"labels": labels, "buttons": buttons, "messaged": messaged},
        {"buttons": expected_names},
        obligation="D12",
    )
    summary = _inner_text(page, "#arrange-membership-summary")
    rig.check(
        "The order and mounting summary counts the blocking tablets",
        f"({len(labels)} tablets)" in summary,
        summary,
        f"contains ({len(labels)} tablets)",
        obligation="D12",
    )
    for label in labels:
        blocker = page.get_by_role(
            "button", name=f"{label}: declare mounted top edge", exact=True
        )
        present = blocker.count() >= 1 and blocker.first.is_visible()
        focused = False
        active = None
        if present:
            blocker.first.click()
            focused = _soft_wait(
                page,
                "(label) => { const node = document.activeElement;"
                " return !!node && node.getAttribute('aria-label') === 'Mount angle for ' + label"
                " && node.getClientRects().length > 0 && !node.disabled; }",
                arg=label,
                timeout=10,
            )
            active = page.evaluate(
                "() => { const node = document.activeElement; return node ? {"
                " tag: node.tagName, id: node.id, aria: node.getAttribute('aria-label'),"
                " visible: node.getClientRects().length > 0, disabled: !!node.disabled } : null; }"
            )
        rig.check(
            f"The blocker for {label} focuses that tablet's visible mount control",
            present and focused,
            {"present": present, "focused": focused, "active": active},
            {"present": True, "aria": f"Mount angle for {label}"},
            obligation="D12",
        )
    writes = _layout_write_rows(rig, preview_start)
    rig.check(
        "A blocked measured preview sends no layout write",
        not writes,
        writes,
        [],
        obligation="C-GEOMETRY",
    )

    # After valid mounting declarations, a second preview must expose the
    # missing pinned measurements and their per-tablet Settings action.
    device_rows = page.evaluate(
        """() => [...document.querySelectorAll('#grid-order .tablet-order-row')].map(row => {
            const select = row.querySelector('select[aria-label^="Mount angle for "]');
            return {
                id: row.dataset.deviceId,
                label: select ? select.getAttribute('aria-label').replace('Mount angle for ', '') : null,
            };
        }).filter(row => row.id && row.label)"""
    )
    for row in device_rows:
        page.select_option(
            f'#grid-order .tablet-order-row[data-device-id="{row["id"]}"] select', "0"
        )
    declared_angles = page.evaluate(
        """() => [...document.querySelectorAll('#grid-order .tablet-order-row')]
            .map(row => row.querySelector('select[aria-label^="Mount angle for "]')?.value ?? null)"""
    )
    rig.check(
        "Every selected measured tablet has a declared mount angle before the measurements preview",
        bool(device_rows) and len(declared_angles) == len(device_rows)
        and all(value not in (None, "") for value in declared_angles),
        {"angles": declared_angles, "rows": device_rows},
        {"count": len(device_rows), "angles": "all declared"},
        obligation="D12",
    )

    measurements_start = len(rig.requests)
    page.click("#grid-preview")
    measurements_messaged = _soft_wait(
        page,
        "() => /Confirm a model or save measurements|Pinned physical measurements are unavailable|"
        "missing measurement/i.test(document.getElementById('grid-message').textContent)",
        timeout=15,
    )
    measurements_buttons = page.evaluate(
        """() => [...document.querySelectorAll('#panel-show button')]
            .filter(button => {
                const name = (button.getAttribute('aria-label') || button.textContent || '').trim();
                return /: open measurements$/.test(name)
                    && button.getClientRects().length > 0 && !button.disabled;
            })
            .map(button => (button.getAttribute('aria-label') || button.textContent || '').trim())"""
    )
    expected_measurements = sorted(
        f"{row['label']}: open measurements" for row in device_rows
    )
    rig.check(
        "A measured preview with declared mounting but missing pinned measurements names every "
        "tablet with one visible enabled measurements button",
        measurements_messaged and bool(device_rows)
        and sorted(measurements_buttons) == expected_measurements,
        {"message": _inner_text(page, "#grid-message"), "buttons": measurements_buttons,
         "rows": device_rows, "messaged": measurements_messaged},
        {"buttons": expected_measurements},
        obligation="D12",
    )
    for index, row in enumerate(device_rows):
        if index:
            _task(rig, "Arrange")
        target = f"{row['label']}: open measurements"
        action = page.get_by_role("button", name=target, exact=True)
        if index and not (
            action.count() >= 1 and action.first.is_visible() and not action.first.is_disabled()
        ):
            preview_button = page.locator("#grid-preview")
            if (
                preview_button.count()
                and preview_button.is_visible()
                and preview_button.is_enabled()
            ):
                preview_button.click()
                _soft_wait(
                    page,
                    "() => /Confirm a model or save measurements|"
                    "Pinned physical measurements are unavailable|missing measurement/i.test("
                    "document.getElementById('grid-message').textContent)",
                    timeout=15,
                )
            action = page.get_by_role("button", name=target, exact=True)
        present = (
            action.count() >= 1
            and action.first.is_visible()
            and not action.first.is_disabled()
        )
        clicked = False
        opened = False
        if present:
            action.first.click()
            clicked = True
            opened = _soft_wait(
                page,
                "({id}) => { const panel = document.getElementById('panel-system');"
                " const details = document.getElementById('measurement-details');"
                " const selected = document.querySelector('#device-list .dev-pick[aria-pressed=true]');"
                " const active = document.activeElement;"
                " return !!panel && !panel.hidden && !!details && details.open"
                " && !!selected && selected.dataset.deviceId === id"
                " && !!active && (active.id === 'tablet-model' || details.contains(active)); }",
                arg={"id": row["id"]},
                timeout=10,
            )
        action_state = page.evaluate(
            "() => ({panels: [...document.querySelectorAll('.task-panel')]"
            ".filter(panel => !panel.hidden && panel.getClientRects().length > 0)"
            ".map(panel => panel.id),"
            " detailsOpen: !!document.getElementById('measurement-details')?.open,"
            " selected: document.querySelector('#device-list .dev-pick[aria-pressed=true]')?.dataset.deviceId,"
            " active: document.activeElement ? {id: document.activeElement.id,"
            " tag: document.activeElement.tagName} : null})"
        )
        rig.check(
            f"The measurements blocker for {row['label']} selects that exact tablet and "
            "opens its measurement settings",
            present and clicked and opened,
            {"present": present, "clicked": clicked, "opened": opened,
             "state": action_state, "expectedSelected": row["id"]},
            {"present": True, "selected": row["id"], "detailsOpen": True,
             "focus": "measurement control"},
            obligation="D12",
        )
    _task(rig, "Tablets")
    selected_id = device_rows[0]["id"]
    page.locator(f'#device-list .dev-pick[data-device-id="{selected_id}"]').click()
    standalone = page.locator("#open-tablet-measurements")
    available = standalone.count() == 1 and standalone.is_visible() and standalone.is_enabled()
    opened = False
    if available:
        standalone.click()
        opened = _soft_wait(
            page,
            "(id) => { const details = document.getElementById('measurement-details');"
            " const active = document.activeElement; const panel = document.getElementById('panel-system');"
            " return !!panel && !panel.hidden && !!details && details.open"
            " && document.querySelector('#device-list .dev-pick[aria-pressed=true]')?.dataset.deviceId === id"
            " && !!active && !active.disabled && active.getClientRects().length > 0"
            " && (active.id === 'tablet-model' || details.contains(active)); }",
            arg=selected_id,
            timeout=10,
        )
    rig.check(
        "The selected measured tablet standalone measurements action opens its own visible settings",
        available and opened,
        {"available": available, "opened": opened, "selected": selected_id},
        {"available": True, "opened": True, "selected": selected_id},
        obligation="D12",
    )
    measurement_writes = _layout_write_rows(rig, measurements_start)
    rig.check(
        "The missing-measurements preview and its settings actions send no layout write",
        not measurement_writes,
        measurement_writes,
        [],
        obligation="C-GEOMETRY",
    )


# ---------------------------------------------------------------------------
# server-stop (C-OFFLINE)
# ---------------------------------------------------------------------------


def _dom_snapshot(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """() => {
            const text = id => { const node = document.getElementById(id); return node ? node.textContent : null; };
            const roster = document.getElementById('exception-roster');
            const pattern = document.getElementById('pattern-black');
            const patternGrid = document.getElementById('pattern-grid');
            const colours = document.getElementById('show-colours');
            return {
                connection: document.body.dataset.connection,
                connectionText: (document.getElementById('page-status') || {}).textContent || null,
                operatorConnection: (document.getElementById('operator-connection') || {}).textContent || null,
                health: text('wall-health'),
                healthLabel: document.getElementById('btn-wall-health')?.getAttribute('aria-label') || null,
                checked: text('wall-checked'),
                wallSummary: text('wall-status-summary'),
                exceptionCount: text('exception-count'),
                attention: text('attention-heading'),
                positions: text('position-count'),
                exceptionStrip: text('exception-strip'),
                rosterStatus: (() => { const node = document.getElementById('roster-status');
                    return node ? {hidden: node.hidden, text: node.textContent} : null; })(),
                roster: roster ? [...roster.querySelectorAll('li')].map(row => ({
                    id: row.dataset.deviceId,
                    status: row.dataset.status,
                    text: row.textContent.trim().slice(0, 200),
                })) : [],
                imageMessage: text('image-message'),
                pageStatus: text('page-status'),
                patternBlack: pattern ? {present: true, disabled: pattern.disabled,
                    visible: pattern.getClientRects().length > 0} : {present: false},
                patternGrid: patternGrid ? {present: true, disabled: patternGrid.disabled,
                    visible: patternGrid.getClientRects().length > 0} : {present: false},
                colours: colours ? {present: true, disabled: colours.disabled,
                    visible: colours.getClientRects().length > 0} : {present: false},
                etagState: text('etag-state'),
            };
        }"""
    )


def server_stop(rig: RenewalRig) -> None:
    clients = [rig.new_client(CLIENT_SPECS[index % len(CLIENT_SPECS)], index) for index in range(6)]
    for width, height in ((1440, 900), (1280, 800)):
        rig.page.set_viewport_size({"width": width, "height": height})
        if rig.page.locator("#image-discard").is_visible():
            rig.page.locator("#image-discard").click()
        _server_stop_at_viewport(rig, clients, width, height)


def _server_stop_at_viewport(rig: RenewalRig, clients: list, width: int, height: int) -> None:
    page = rig.page
    suffix = f"-{width}x{height}"
    _place_grid(rig, clients, 1800, 1000, 3)
    asset = rig.assets[0]
    status, _ = rig.put_scene(
        {"type": "image", "asset": "sha256:" + asset["sha256"], "fit": "cover"}
    )
    if status != 200:
        raise RuntimeError(f"scene write failed: {status}")
    current = _soft_wait(
        page,
        "() => /6 of 6 showing the current image/.test("
        "document.getElementById('wall-health').textContent)",
        timeout=35,
    )
    _task(rig, "Images")
    wait_until(
        page, "() => document.querySelectorAll('#image-gallery > li').length >= 8", timeout=30
    )
    selected = _select_gallery_image(rig, 1)
    before = page.evaluate(
        "() => ({connection: document.body.dataset.connection,"
        " dirty: document.body.dataset.outputDirty,"
        " showDisabled: document.getElementById('show-image')?.disabled})"
    )
    rig.check(
        "The controller loads with current status, a shown image and a draft ready to show",
        current and selected and before["connection"] == "current" and before["dirty"] == "true"
        and before["showDisabled"] is False,
        {"current": current, "selected": selected, "before": before},
        {"connection": "current", "dirty": "true", "showDisabled": False},
        obligation="C-OFFLINE",
    )

    stop_index = len(rig.requests)
    stopped = stop_owned_server(rig.server)
    _write_json(
        rig.out / ("server_stop" + suffix + ".json"),
        {"reason": "real server stop for C-OFFLINE", "server": stopped,
         "stop_request_index": stop_index},
    )
    became_stale = _soft_wait(
        page, "() => document.body.dataset.connection !== 'current'", timeout=10
    )
    after_stop = _dom_snapshot(page)
    rig.check(
        "A real server stop makes the operator connection non-current within 10 s",
        became_stale and after_stop["connection"] != "current",
        {"after": after_stop["connection"], "connectionText": after_stop["connectionText"],
         "operatorConnection": after_stop["operatorConnection"], "health": after_stop["health"]},
        {"connection": "!= current"},
        obligation="C-OFFLINE",
    )
    _write_json(rig.out / ("server_stop_observations" + suffix + ".json"), {"after_stop": after_stop})

    if page.locator("#refresh-status").count():
        page.click("#refresh-status")
    stale_health = _soft_wait(
        page,
        "() => /Status stale|evidence unavailable|stale/i.test("
        "document.getElementById('wall-health').textContent)",
        timeout=15,
    )
    refreshed = _dom_snapshot(page)
    health_text = (refreshed["health"] or "")
    health_label = (refreshed["healthLabel"] or "")
    counting_current = bool(re.search(r"\d+ of \d+ showing the current", health_text))
    rig.check(
        "Refresh status cannot present current wall evidence while the server is stopped",
        stale_health
        and (health_text.startswith("Status stale") or "evidence unavailable" in health_text.lower())
        and not counting_current
        and health_label.startswith("Status stale"),
        {"health": health_text, "label": health_label, "counting": counting_current,
         "connection": refreshed["connection"], "etagState": refreshed["etagState"]},
        {"health": "Status stale · Current image evidence unavailable",
         "counting": False, "label": "starts with Status stale."},
        obligation="C-OFFLINE",
    )
    after_refresh_index = len(rig.requests)
    pre_show_index = len(rig.requests)
    pre_show_writes = _controller_write_rows(rig, stop_index, pre_show_index)
    rig.check(
        "No automatic operator write happens between the stop and the first operator command",
        not pre_show_writes,
        pre_show_writes,
        [],
        obligation="C-OFFLINE",
    )

    message_before = page.evaluate(
        "() => (document.getElementById('image-message') || {}).textContent || ''"
    )
    show_control = page.locator("#show-image")
    show_present = show_control.count() == 1
    show_visible = show_present and show_control.is_visible()
    show_disabled = show_control.is_disabled() if show_present else None
    show_attempted = False
    message_set = False
    if show_present and show_visible and not show_disabled:
        show_control.focus()
        page.evaluate("() => scrollTo(0, 0)")
        page.keyboard.press("Enter")
        show_attempted = True
        message_set = _soft_wait(
            page,
            "() => { const node = document.getElementById('image-message');"
            " return !!node && /uncertain|may have completed|Could not show|Connection lost|Refresh status/i"
            ".test(node.textContent); }",
            timeout=20,
        )
    else:
        page.wait_for_timeout(100)
    if show_attempted:
        page.wait_for_timeout(150)
        focus = page.evaluate("""() => {
            const e = document.activeElement, r = e.getBoundingClientRect();
            const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
            return {id: e.id || e.tagName, visible: !!e.getClientRects().length,
                ring: getComputedStyle(e).outlineWidth, focusVisible: e.matches(':focus-visible'),
                viewport: [innerWidth, innerHeight], rect: {top:r.top,bottom:r.bottom,left:r.left,right:r.right},
                inside: r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth,
                unobscured: !!hit && (e === hit || e.contains(hit)),
                uncertainty: !!document.getElementById('refresh-command-status').getClientRects().length};
        }""")
        expected_focus = "show-image" if not show_control.is_disabled() else (
            "image-rebuild" if page.locator("#image-rebuild").is_visible() else "image-message")
        rig.check(
            f"A real connection-lost keyboard Show retains visible focus on its enabled trigger or recovery at {width}x{height}",
            focus["id"] == expected_focus and focus["visible"] and focus["ring"] != "0px"
            and focus["focusVisible"] and focus["inside"] and focus["unobscured"] and focus["uncertainty"],
            focus,
            {"id": expected_focus, "visible": True, "ring": "> 0px", "inside": True,
             "unobscured": True, "uncertainty": True, "viewport": [width, height]},
            obligation="C-GUARD",
        )
        rig.shot("connection-lost-show-focus" + suffix)
    post_show_index = len(rig.requests)
    intended_show_writes = _controller_write_rows(rig, pre_show_index, post_show_index)
    show = _dom_snapshot(page)
    message_now = show["imageMessage"] or ""
    message_ok = bool(
        re.search(
            r"uncertain|may have completed|Could not show|Connection lost|Refresh status",
            message_now,
            re.IGNORECASE,
        )
    )
    success = "Content applied" in message_now \
        or "Content applied" in (show["pageStatus"] or "")
    show_branch = (
        "disabled"
        if show_present and show_visible and show_disabled is True and not show_attempted
        else "attempted"
        if show_attempted
        else "missing_or_hidden"
    )
    rig.check(
        "The Show control is present and visible as an enabled attempt or an honest disabled control",
        show_present and show_visible and show_disabled is not None,
        {"present": show_present, "visible": show_visible, "disabled": show_disabled,
         "attempted": show_attempted},
        {"present": True, "visible": True, "disabled": "boolean"},
        obligation="C-OFFLINE",
    )
    rig.check(
        "Show on a draft is disabled without a write or refused/uncertain, and never claims success",
        _show_refusal_ok(
            present=show_present,
            visible=show_visible,
            disabled=show_disabled,
            attempted=show_attempted,
            message_ok=message_ok,
            message_changed=message_now != message_before,
            intended_writes=intended_show_writes,
            success=success,
        ),
        {"branch": show_branch, "message": message_now, "messageBefore": message_before,
         "messageSet": message_set, "pageStatus": show["pageStatus"], "success": success,
         "intendedWrites": intended_show_writes},
        {"branch": "disabled with zero attempted writes, or attempted with refusal/uncertainty",
         "success": False},
        obligation="C-OFFLINE",
    )
    show_writes = _controller_write_rows(rig, stop_index, post_show_index)
    _write_json(
        rig.out / ("server_stop_observations" + suffix + ".json"),
        {
            "after_stop": after_stop,
            "after_refresh": refreshed,
            "after_show": show,
            "show_branch": show_branch,
            "intended_show_writes": intended_show_writes,
            "writes_since_stop": show_writes,
        },
    )

    reports_current = [
        row["text"] for row in refreshed["roster"]
        if "Reports current image" in row["text"]
    ]
    rig.check(
        "The stale Exceptions surface marks the status stale and does not keep reporting "
        "current image evidence",
        bool(refreshed["roster"])
        and all(row["status"] == "stale" for row in refreshed["roster"])
        and not reports_current,
        {"count": refreshed["exceptionCount"], "attention": refreshed["attention"],
         "positions": refreshed["positions"], "strip": refreshed["exceptionStrip"],
         "rosterStatus": refreshed["rosterStatus"], "rows": refreshed["roster"],
         "reportsCurrent": reports_current,
         "patternBlack": refreshed["patternBlack"],
         "patternGrid": refreshed["patternGrid"], "colours": refreshed["colours"]},
        {"rows": "all stale", "reportsCurrent": []},
        obligation="C-OFFLINE",
    )

    pre_restart_index = len(rig.requests)
    restart = _restart_server(rig, suffix)
    restart_index = len(rig.requests)
    restart_writes = _restart_interval_writes(
        rig,
        post_show=post_show_index,
        before_restart=pre_restart_index,
        after_restart=restart_index,
    )
    rig.check(
        "No automatic write is issued after the failed Show before the restart",
        not restart_writes["after_show_before_restart"],
        {"writes": restart_writes["after_show_before_restart"],
         "intendedShowWrites": intended_show_writes},
        [],
        obligation="C-OFFLINE",
    )
    rig.check(
        "No automatic write is issued during the restart and readiness interval",
        not restart_writes["during_restart_startup"],
        restart_writes["during_restart_startup"],
        [],
        obligation="C-OFFLINE",
    )
    if page.locator("#refresh-status").count():
        page.click("#refresh-status")
    restored = _soft_wait(
        page,
        "() => document.body.dataset.connection === 'current'"
        " && /showing the current/.test(document.getElementById('wall-health').textContent)",
        timeout=25,
    )
    recovered = _dom_snapshot(page)
    rig.check(
        "After a restart on the same port and data, Refresh status restores current status",
        restored and recovered["connection"] == "current"
        and "Status stale" not in (recovered["health"] or "")
        and bool(re.search(r"\d+ of \d+ showing the current", recovered["health"] or "")),
        {"restart": restart, "after": recovered["connection"],
         "health": recovered["health"], "etagState": recovered["etagState"]},
        {"connection": "current", "health": "not Status stale; N of M showing the current"},
        obligation="C-OFFLINE",
    )
    post_restart_writes = _controller_write_rows(rig, restart_index)
    rig.check(
        "The page writes nothing automatically after the restart before the operator command",
        not post_restart_writes,
        post_restart_writes,
        [],
        obligation="C-OFFLINE",
    )
    _write_json(
        rig.out / ("server_stop_observations" + suffix + ".json"),
        {
            "after_stop": after_stop,
            "after_refresh": refreshed,
            "after_show": show,
            "show_branch": show_branch,
            "intended_show_writes": intended_show_writes,
            "writes_since_stop": show_writes,
            "request_boundaries": {
                "stop": stop_index,
                "after_refresh": after_refresh_index,
                "pre_show": pre_show_index,
                "after_show": post_show_index,
                "before_restart": pre_restart_index,
                "after_restart_ready": restart_index,
            },
            "pre_operator_command_writes": pre_show_writes,
            "post_show_before_restart_writes": restart_writes["after_show_before_restart"],
            "restart_startup_writes": restart_writes["during_restart_startup"],
            "restart": restart,
            "after_restart_refresh": recovered,
            "post_restart_pre_command_writes": post_restart_writes,
        },
    )


SCENARIO_BODIES = {
    "status-truth": status_truth,
    "guarded-show-focus": guarded_show_focus,
    "saved-name-rule": saved_name_rule,
    "pattern-grouping": pattern_grouping,
    "layout-foundation": layout_foundation,
    "images-workbench": images_workbench,
    "first-wall": first_wall,
    "tablet-facts": tablet_facts,
    "measured-blockers": measured_blockers,
    "server-stop": server_stop,
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
    rig = RenewalRig(out, name, source_root, identity)
    interrupted = False
    with sync_playwright() as playwright:
        try:
            rig.setup(playwright)
            rig.check(
                "Private server originated from the selected source root",
                rig.server_cwd == str(Path(source_root).resolve()),
                {"server_cwd": rig.server_cwd,
                 "manifest_source_root": rig.identity["application"]["source_root"]},
                str(Path(source_root).resolve()),
                obligation="C-PRESERVE",
            )
            SCENARIO_BODIES[name](rig)
            covered = {row.get("obligation") for row in rig.results}
            missing = [item for item in SCENARIOS[name]["obligations"] if item not in covered]
            if missing:
                rig.check(
                    "The scenario proves every registered obligation",
                    False,
                    {"missing": missing},
                    [],
                    obligation=missing[0],
                )
            rig.check(
                "No JavaScript page exceptions",
                not rig.page_errors,
                rig.page_errors,
                [],
                obligation="C-PRESERVE",
            )
        except Exception as error:
            interrupted = True
            failure = {
                "name": "scenario interrupted",
                "pass": False,
                "obligation": "scenario",
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
    incomplete = [row["incomplete"] for row in rig.results if row.get("incomplete")]
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
        "obligations": list(SCENARIOS[name]["obligations"]),
        "owner": SCENARIOS[name]["owner"],
        "incomplete": incomplete,
        "software_complete": passed and not incomplete,
        "limitations": LIMITATIONS,
    }
    _write_json(out / "scenario.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Scenarios: " + ", ".join(SCENARIOS),
    )
    parser.add_argument("--artifacts", required=True, type=Path, help="new directory outside the repository")
    parser.add_argument(
        "--scenario",
        choices=("all", *SCENARIOS),
        default="all",
        help="one renewal scenario or all of them: " + ", ".join(SCENARIOS),
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=None,
        help="read-only application source to serve; defaults to this checkout",
    )
    args = parser.parse_args(argv)
    selected = tuple(SCENARIOS) if args.scenario == "all" else (args.scenario,)
    try:
        source_root = resolve_source_root(args.source_root)
        artifacts = new_artifacts(args.artifacts, source_root, create=args.scenario == "all")
    except (OSError, ValueError) as error:
        parser.error(str(error))

    application_before = application_identity(source_root)
    driver = driver_identity()
    reports: list[dict[str, Any]] = []
    for name in selected:
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
    passed = source_unchanged and bool(reports) and all(report["pass"] for report in reports)
    incomplete = [item for report in reports for item in report.get("incomplete", [])]
    result = {
        "task": RENEWAL_TASK_ID,
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
            {"name": entry["name"], "owner": entry["owner"], "fixtures": entry["fixtures"],
             "obligations": list(entry["obligations"])}
            for entry in SCENARIO_ENTRIES
        ],
        "fixtures": reports[0].get("fixtures", []) if reports else [],
        "fixture_coverage": {
            "generated_groups": [0, 1, 8, 24],
            "served_by_scenario": dict(SCENARIO_FIXTURES),
            "workbench_library": [name for name, _, _ in WORKBENCH_SHAPES],
            "note": "Generated fixture libraries only; every image is labelled GENERATED FIXTURE. "
                    "images-workbench serves its own ten-image GENERATED FIXTURE library.",
        },
        "reports": reports,
        "pass": passed,
        "acceptance_complete": False,
        "software_complete": passed and not incomplete,
        "incomplete": incomplete,
        "limitations": LIMITATIONS,
    }
    _write_json(artifacts / "results.json", result)
    passed_checks = sum(report.get("checks", 0) for report in reports)
    failed_checks = sum(len(report.get("failures", [])) for report in reports)
    print(
        f"renewal {args.scenario}: {passed_checks} checks, "
        f"{failed_checks} failures; report {artifacts / 'results.json'}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
