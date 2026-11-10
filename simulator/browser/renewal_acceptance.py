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

The private runtime directory is chosen with TABLET_WALL_RENEWAL_RUNTIME when
set, so a caller can keep DB, assets, media, backups, HOME, XDG and TMPDIR under
its evidence directory outside the repository. It is removed after each run.
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
import traceback
from datetime import datetime, timezone
from typing import Any

REPO = Path(__file__).resolve().parents[2]
RENEWAL_TASK_ID = "renewal-1"
DRIVER_PATHS = (
    "simulator/browser/renewal_acceptance.py",
    "simulator/browser/restoration_acceptance.py",
)
PORTS = tuple(range(43300, 43320))

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

LIMITATIONS = [
    "Software browser evidence only. No physical tablet, optical seam, sleep/wake, "
    "native screen reader, native browser zoom, network ingress or hardware certification.",
    "The operator page is the real shipped page. Generated fixture images are labelled "
    "GENERATED FIXTURE and are never counted as operator content.",
    "CSS text at 200% is applied as an injected html{font-size:200%} style and is labelled "
    "as an emulation, not a user's browser setting.",
    "Fractional CSS viewport widths are not accepted by Playwright or by Chromium's "
    "device-metrics protocol. Each requested fractional width is measured at the integer "
    "CSS width the engine resolves for it; both values are recorded. Chromium resolves "
    "719.5 to 720 and 768.5 to 769.",
    "A gallery tile's accessible name is read from its aria-label, which is the name "
    "Chromium computes for a button without aria-labelledby.",
]


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
    """The restoration Rig, bound to 43300-43319 and a caller-owned runtime root."""

    def setup(self, playwright: Any) -> None:
        runtime_root = Path(os.environ.get("TABLET_WALL_RENEWAL_RUNTIME") or tempfile.gettempdir())
        runtime_root.mkdir(parents=True, exist_ok=True)
        self.private = Path(tempfile.mkdtemp(prefix=f"renewal-{self.scenario}-", dir=runtime_root))
        data = self.private / "data"
        self.fixtures = generate_fixtures(self.private / "fixtures")
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
        self.results[-1]["obligation"] = obligation
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
    if (!panel) return {panel: null, controls: 0, short: []};
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
    const short = controls.map(el => {
        const rect = el.getBoundingClientRect();
        return {
            tag: el.tagName,
            id: el.id,
            cls: String(el.className).slice(0, 40),
            label: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 40),
            height: Math.round(rect.height * 100) / 100,
        };
    }).filter(row => row.height < 44);
    return {panel: panel.id, controls: controls.length, short};
}"""



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


# ---------------------------------------------------------------------------
# guarded-show-focus (D5, C-GUARD)
# ---------------------------------------------------------------------------


def guarded_show_focus(rig: RenewalRig) -> None:
    page = rig.page
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

    asset = rig.assets[1]
    status, payload = rig.put_scene({"type": "image", "asset": "sha256:" + asset["sha256"], "fit": "contain"})
    rig.check(
        "A second guarded scene write is accepted before Show",
        status == 200,
        status,
        200,
        obligation="C-GUARD",
        fatal=True,
    )
    new_etag = payload.get("etag") if isinstance(payload, dict) else None
    if not new_etag:
        new_etag = rig.config()["etag"]
    wait_until(
        page,
        "(etag) => document.getElementById('etag-value')?.title === etag"
        " && document.getElementById('etag-state')?.textContent === 'current'",
        arg=new_etag,
        timeout=20,
    )
    wait_until(page, "() => !document.getElementById('show-image').disabled", timeout=20)

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
        after - before == 1,
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

    for requested in FRACTIONAL_WIDTHS:
        width = resolved_width(requested)
        try:
            page.set_viewport_size({"width": requested, "height": 900})  # type: ignore[arg-type]
            measured_label = f"{requested}px"
        except Exception:
            width = resolved_width(requested)
            measured_label = f"{requested}px (engine width {width})"
        measure_viewport(measured_label, width, 900)

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
            rig.check(
                f"Coarse pointer 390x844 {task}: every visible enabled control is at least 44px tall",
                sweep["panel"] is not None and sweep["short"] == [],
                {"panel": sweep["panel"], "controls": sweep["controls"], "short": sweep["short"]},
                {"panel": "visible", "short": []},
                obligation="C-TOUCH",
            )
    finally:
        rig.page = page

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


SCENARIO_BODIES = {
    "status-truth": status_truth,
    "guarded-show-focus": guarded_show_focus,
    "saved-name-rule": saved_name_rule,
    "pattern-grouping": pattern_grouping,
    "layout-foundation": layout_foundation,
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
            "note": "Generated fixture libraries only; every image is labelled GENERATED FIXTURE.",
        },
        "reports": reports,
        "pass": passed,
        "acceptance_complete": False,
        "software_complete": passed,
        "incomplete": [],
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
