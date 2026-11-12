"""Measure the workspace-wall composition gates G1-G6 against a live operator console.

Works on the five-tab console and on the workspace shell (see the DOM contract in the
redesign spec). Every gate records the measured value next to its threshold. Run with the
Playwright interpreter, for example:

    python -m simulator.browser.composition_gates --out /new/dir --port-range 43900-43919

G7 (nothing under the backend or renderer changed) is a ``git diff`` check, not a browser one.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]

VIEWPORTS = [(1920, 1080), (1440, 900), (1366, 768), (1280, 800), (1024, 768), (768, 1024), (390, 844)]
MODES = ("content", "arrange", "test")
AREA_SIZES = [(1366, 768), (1280, 800)]
STAGE_AREA_MIN = 0.45
WELL_DRIFT_MAX = 0.02
FILL_MIN = 0.90
ASPECT_TOLERANCE = 0.01
OFFLINE_SECONDS = 2.0

# Old-UI fallbacks, used only when the data-* contract is absent.
OLD_TAB = {"content": "#tab-content", "arrange": "#tab-show", "test": "#tab-system"}
OLD_TASK_VALUE = {"content": "content", "arrange": "show", "test": "system"}


# --- pure gate arithmetic -------------------------------------------------------------------


def box_area(box: dict | None) -> float:
    return 0.0 if not box else max(0.0, box["width"]) * max(0.0, box["height"])


def area_fraction(box: dict | None, viewport: tuple[int, int]) -> float:
    return box_area(box) / (viewport[0] * viewport[1])


def box_drift(a: dict, b: dict, viewport: tuple[int, int]) -> float:
    """Largest relative difference of size (vs the box) and position (vs the viewport)."""
    return max(
        abs(a["width"] - b["width"]) / max(a["width"], 1e-9),
        abs(a["height"] - b["height"]) / max(a["height"], 1e-9),
        abs(a["x"] - b["x"]) / viewport[0],
        abs(a["y"] - b["y"]) / viewport[1],
    )


def fill_fraction(drawn: dict | None, well: dict | None) -> float:
    """How much of the well the drawn wall covers in its limiting dimension."""
    if not drawn or not well or well["width"] <= 0 or well["height"] <= 0:
        return 0.0
    return max(drawn["width"] / well["width"], drawn["height"] / well["height"])


def aspect_error(drawn: dict | None, view_box: tuple[float, float] | None) -> float:
    """Relative error between the drawn aspect and the SVG view box aspect."""
    if not drawn or not view_box or drawn["height"] <= 0 or view_box[1] <= 0:
        return 1.0
    want = view_box[0] / view_box[1]
    return abs(drawn["width"] / drawn["height"] - want) / want


def fully_inside(box: dict | None, viewport: tuple[int, int], slack: float = 0.5) -> bool:
    return bool(
        box
        and box["width"] > 0
        and box["height"] > 0
        and box["x"] >= -slack
        and box["y"] >= -slack
        and box["x"] + box["width"] <= viewport[0] + slack
        and box["y"] + box["height"] <= viewport[1] + slack
    )


def verdict(passed: bool, value: Any, threshold: str, detail: Any = None) -> dict:
    out = {"pass": bool(passed), "value": value, "threshold": threshold}
    if detail is not None:
        out["detail"] = detail
    return out


# --- page helpers ---------------------------------------------------------------------------

VISIBLE_JS = """
const closed = e => { for (let n = e.parentElement; n; n = n.parentElement)
  if (n.tagName === 'DETAILS' && !n.open && !(e.tagName === 'SUMMARY' && e.parentElement === n)
      && !([...n.children].find(c => c.tagName === 'SUMMARY') || {contains: () => false}).contains(e)) return true;
  return false; };
const vis = e => { if (!e) return false; const s = getComputedStyle(e);
  return s.display !== 'none' && s.visibility !== 'hidden' && e.getClientRects().length > 0
    && e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().height > 0
    && !closed(e) && (!e.checkVisibility || e.checkVisibility({contentVisibilityAuto: true})); };
const rect = e => { if (!e) return null; const r = e.getBoundingClientRect();
  return {x: r.x, y: r.y, width: r.width, height: r.height}; };
"""

WELL_SELECTOR = "[data-stage-well], #stage-scroll"


def open_mode(page: Any, name: str) -> None:
    new = page.locator(f"[data-workspace-mode='{name}']:visible")
    if new.count():
        new.first.click()
    else:
        compact = page.locator("#compact-task-select")
        if compact.is_visible():
            compact.select_option(value=OLD_TASK_VALUE[name])
        else:
            page.locator(OLD_TAB[name]).click()
    page.wait_for_timeout(250)
    page.evaluate("window.scrollTo(0, 0)")


def set_viewport(page: Any, size: tuple[int, int]) -> None:
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.evaluate("() => document.fonts.ready")
    page.wait_for_timeout(250)


def measure_view(page: Any) -> dict:
    """One measurement pass: well, wall, primaries, overflow and first inspector control."""
    return page.evaluate(
        "(WELL) => {" + VISIBLE_JS + """
        const well = document.querySelector(WELL.split(',')[0]) || document.querySelector('#stage-scroll');
        const svg = document.querySelector('#stage-svg');
        const vb = svg && svg.viewBox && svg.viewBox.baseVal;
        const primaries = [...document.querySelectorAll('.btn-primary')].filter(vis)
          .map(e => ({id: e.id, text: e.textContent.trim().slice(0, 40)}));
        const inspector = document.querySelector('[data-inspector], #inspector')
          || [...document.querySelectorAll('.task-panel')].find(vis);
        const control = inspector && [...inspector.querySelectorAll(
          'button, input:not([type=hidden]), select, textarea, a[href], summary')]
          .filter(e => vis(e) && !(well && well.contains(e)))[0];
        return {
          viewport: {width: innerWidth, height: innerHeight},
          wellVisible: vis(well), well: vis(well) ? rect(well) : null,
          svgVisible: vis(svg), drawn: vis(svg) ? rect(svg) : null,
          viewBox: vb && vb.width ? [vb.width, vb.height] : null,
          primaries,
          scrollWidth: document.documentElement.scrollWidth, innerWidth,
          firstControl: control ? {id: control.id, text: (control.textContent || '').trim().slice(0, 40), box: rect(control)} : null,
          inspectorFound: !!inspector,
        };
        }""",
        WELL_SELECTOR,
    )


def roster_rows(page: Any) -> list[dict]:
    return page.evaluate(
        "() => {" + VISIBLE_JS + """
        let rows = [...document.querySelectorAll('#roster [data-device-id]')];
        if (!rows.length) rows = [...document.querySelectorAll('.tablet-row')];
        return rows.map(e => ({id: e.dataset.deviceId, status: e.dataset.status || '',
          text: e.innerText.replace(/\\s+/g, ' ').trim(), visible: vis(e),
          label: (e.querySelector('.dev-label') || {}).textContent || '',
          number: (e.querySelector('.dev-number') || {}).textContent || ''}));
        }"""
    )


def header_problem(page: Any) -> dict:
    return page.evaluate(
        "() => {" + VISIBLE_JS + """
        const chips = [...document.querySelectorAll('[data-problem-device]')].filter(vis);
        if (chips.length || document.querySelector('[data-problem-device]'))
          return {source: 'data-problem-device', text: chips.map(e => e.innerText).join(' | '), count: chips.length};
        const b = document.querySelector('#btn-wall-health');
        return {source: '#btn-wall-health', text: b && vis(b) ? b.innerText.replace(/\\s+/g, ' ').trim() : '',
          srOnly: (document.querySelector('#issues-description') || {}).textContent || '', count: b ? 1 : 0};
        }"""
    )


def slot_label(page: Any, device_id: str) -> dict:
    return page.evaluate(
        "(id) => {" + VISIBLE_JS + """
        const slot = document.querySelector(`#stage-svg .slot[data-device-id="${id}"]`);
        if (!slot) return {present: false, labels: []};
        const labels = [...slot.querySelectorAll('text')].filter(vis).map(t => t.textContent.trim()).filter(Boolean);
        return {present: true, slotVisible: vis(slot), labels};
        }""",
        device_id,
    )


def find_join_and_add(page: Any) -> dict:
    return page.evaluate(
        "() => {" + VISIBLE_JS + """
        const vp = {w: innerWidth, h: innerHeight};
        const inside = e => { const r = e.getBoundingClientRect();
          return r.left >= 0 && r.top >= 0 && r.right <= vp.w && r.bottom <= vp.h; };
        const addr = /(\\d{1,3}\\.){3}\\d{1,3}:\\d+|localhost:\\d+|https?:\\/\\/\\S+:\\d+/;
        const join = [...document.querySelectorAll('body *')].filter(e => vis(e)
          && (addr.test(e.value || '') || ([...e.childNodes].some(n => n.nodeType === 3 && addr.test(n.textContent)))));
        const add = [...document.querySelectorAll('button, a')].filter(e => vis(e) && /add tablet/i.test(e.textContent));
        const pack = list => list.map(e => ({text: (e.value || e.textContent).trim().slice(0, 60), inside: inside(e),
          box: rect(e)}));
        return {join: pack(join), add: pack(add)};
        }"""
    )


def open_all_details(page: Any) -> int:
    return page.evaluate(
        "() => { const d = [...document.querySelectorAll('details')]; d.forEach(e => e.open = true); return d.length; }"
    )


def commit_primary(page: Any, ids: tuple[str, ...]) -> dict:
    """Box of the visible draft primary, preferring one inside #commit-bar."""
    return page.evaluate(
        "(ids) => {" + VISIBLE_JS + """
        const scope = document.querySelector('#commit-bar') || document;
        for (const id of ids) {
          const e = scope.querySelector('#' + id) || document.querySelector('#' + id);
          if (e && vis(e)) return {id, box: rect(e), enabled: !e.disabled, inBar: !!document.querySelector('#commit-bar #' + id)};
        }
        return {id: null, box: null, enabled: false, inBar: false};
        }""",
        list(ids),
    )


# --- the run --------------------------------------------------------------------------------


def run(out: Path, port_range: str) -> dict:
    for key, rel in {"HOME": "home", "XDG_CONFIG_HOME": "xdg-config", "XDG_CACHE_HOME": "xdg-cache",
                     "XDG_DATA_HOME": "xdg-data", "TMPDIR": "tmp"}.items():
        (out / rel).mkdir(exist_ok=True)
        os.environ[key] = str(out / rel)
    os.environ["TABLET_WALL_RENEWAL_RUNTIME"] = str(out / "runtime")
    os.environ["TABLET_WALL_RENEWAL_PORT_RANGE"] = port_range
    sys.path.insert(0, str(REPO))
    from playwright.sync_api import sync_playwright

    from simulator.browser import renewal_acceptance as ra

    shots: list[dict] = []

    def shot(page: Any, name: str, **meta: Any) -> None:
        path = out / f"{name}.png"
        page.screenshot(path=str(path))
        shots.append({"file": path.name, **meta})

    gates: dict[str, dict] = {}
    result: dict[str, Any] = {"source": ra.application_identity(REPO), "gates": gates, "screenshots": shots,
                              "measurements": {}}
    rig = ra.RenewalRig(out / "demo", "images-workbench", REPO,
                        {"application": result["source"], "driver": ra.driver_identity()})
    rig.out.mkdir()
    page: Any = None
    with sync_playwright() as pw:
        try:
            rig.setup(pw)
            page = rig.page
            page.emulate_media(color_scheme="light")

            # G5: the empty wall, before any tablet joins.
            set_viewport(page, (1280, 800))
            found = find_join_and_add(page)
            join_ok = any(item["inside"] for item in found["join"])
            add_ok = any(item["inside"] for item in found["add"])
            gates["G5"] = verdict(join_ok and add_ok,
                                  {"join_address_inside": join_ok, "add_tablets_inside": add_ok},
                                  "join address and Add tablets inside first viewport at 1280x800", found)
            shot(page, "g5-empty-wall-1280x800", state="empty wall")

            # Fixture: 6 tablets, 3x2, one image shown.
            clients = [rig.new_client(ra.CLIENT_SPECS[i % len(ra.CLIENT_SPECS)], i) for i in range(6)]
            ra._place_grid(rig, clients, 1800, 1000, 3)
            set_viewport(page, (1440, 900))
            open_mode(page, "content")
            if not ra._select_gallery_image(rig, 0):
                raise RuntimeError("no gallery image to show")
            page.locator("#show-image").click()
            page.wait_for_function(
                "() => document.body.dataset.outputDirty !== 'true'"
                " && document.querySelector('#wall-health').textContent.includes('6 of 6')", timeout=20000)

            # G1, G3 (no draft) and G6 across modes x viewports.
            grid: dict[str, dict] = {}
            for size in VIEWPORTS:
                for mode in MODES:
                    set_viewport(page, size)
                    open_mode(page, mode)
                    grid[f"{size[0]}x{size[1]}/{mode}"] = measure_view(page)
                    shot(page, f"{mode}-{size[0]}x{size[1]}-light", viewport=list(size), mode=mode, scheme="light")
            set_viewport(page, (1440, 900))
            page.emulate_media(color_scheme="dark")
            for mode in MODES:
                open_mode(page, mode)
                shot(page, f"{mode}-1440x900-dark", viewport=[1440, 900], mode=mode, scheme="dark")
            page.emulate_media(color_scheme="light")
            result["measurements"]["grid"] = grid

            g1: dict[str, Any] = {}
            ok1 = True
            for size in AREA_SIZES:
                wells = {}
                for mode in MODES:
                    m = grid[f"{size[0]}x{size[1]}/{mode}"]
                    frac = area_fraction(m["well"], size)
                    fill = fill_fraction(m["drawn"], m["well"])
                    asp = aspect_error(m["drawn"], m["viewBox"])
                    wells[mode] = m["well"]
                    mode_ok = m["wellVisible"] and frac >= STAGE_AREA_MIN and fill >= FILL_MIN and asp <= ASPECT_TOLERANCE
                    ok1 &= mode_ok
                    g1[f"{size[0]}x{size[1]}/{mode}"] = {
                        "well_visible": m["wellVisible"], "area_fraction": round(frac, 4),
                        "fill": round(fill, 4), "aspect_error": round(asp, 4), "pass": bool(mode_ok)}
                drift = None
                if all(wells.values()):
                    drift = max(box_drift(wells[a], wells[b], size) for a in MODES for b in MODES)
                drift_ok = drift is not None and drift <= WELL_DRIFT_MAX
                ok1 &= drift_ok
                g1[f"{size[0]}x{size[1]}/drift"] = {"max_drift": None if drift is None else round(drift, 4),
                                                    "pass": drift_ok}
            gates["G1"] = verdict(ok1, g1, f"area>={STAGE_AREA_MIN}, drift<={WELL_DRIFT_MAX}, fill>={FILL_MIN} "
                                  "at 1366x768 and 1280x800 in every mode")

            g6: dict[str, Any] = {}
            narrow = {mode: grid[f"390x844/{mode}"] for mode in MODES}
            ok6 = True
            for mode, m in narrow.items():
                ctrl = m["firstControl"]
                top_ok = bool(m["wellVisible"] and ctrl and m["well"]["y"] < ctrl["box"]["y"])
                ok6 &= top_ok
                g6[f"390x844/{mode}/stage_above_first_control"] = {
                    "stage_top": m["well"] and round(m["well"]["y"], 1),
                    "first_control_top": ctrl and round(ctrl["box"]["y"], 1),
                    "first_control": ctrl and (ctrl["id"] or ctrl["text"]), "pass": top_ok}
            overflow = {k: m["scrollWidth"] - m["innerWidth"] for k, m in grid.items()}
            worst = max(overflow.values())
            ok6 &= worst <= 0
            g6["max_overflow_px"] = {"value": worst, "worst_cases": {k: v for k, v in overflow.items() if v > 0},
                                     "pass": worst <= 0}
            gates["G6"] = verdict(ok6, g6, "stage top above first inspector control at 390x844; "
                                  "scrollWidth<=innerWidth at all 7 viewports x 3 modes")

            # G2 (with every disclosure open) and G3 (with a draft open).
            g2: dict[str, Any] = {}
            draft_primaries: dict[str, list] = {}
            set_viewport(page, (1440, 900))
            open_mode(page, "content")
            if not ra._select_gallery_image(rig, 1):
                raise RuntimeError("no second gallery image for a draft")
            for size in VIEWPORTS:
                set_viewport(page, size)
                open_mode(page, "content")
                opened = open_all_details(page)
                page.wait_for_timeout(150)
                page.evaluate("window.scrollTo(0, 0)")
                cp = commit_primary(page, ("show-image",))
                inside = fully_inside(cp["box"], size)
                g2[f"image/{size[0]}x{size[1]}"] = {"details_opened": opened, "box": cp["box"], "in_commit_bar": cp["inBar"],
                                                      "pass": inside}
                draft_primaries[f"image/{size[0]}x{size[1]}"] = measure_view(page)["primaries"]
                shot(page, f"g2-image-draft-{size[0]}x{size[1]}", viewport=list(size), state="image draft, disclosures open")
            set_viewport(page, (1440, 900))
            page.locator("#image-discard").click()
            page.wait_for_timeout(200)
            open_mode(page, "arrange")
            page.fill("#grid-rows", "3")
            page.fill("#grid-columns", "2")
            page.locator("#grid-preview").click()
            page.wait_for_function("() => document.getElementById('btn-apply')?.disabled === false", timeout=25000)
            for size in VIEWPORTS:
                set_viewport(page, size)
                open_mode(page, "arrange")
                opened = open_all_details(page)
                page.wait_for_timeout(150)
                page.evaluate("window.scrollTo(0, 0)")
                cp = commit_primary(page, ("btn-apply",))
                inside = fully_inside(cp["box"], size)
                g2[f"arrangement/{size[0]}x{size[1]}"] = {"details_opened": opened, "box": cp["box"],
                                                           "in_commit_bar": cp["inBar"], "pass": inside}
                draft_primaries[f"arrangement/{size[0]}x{size[1]}"] = measure_view(page)["primaries"]
                shot(page, f"g2-arrangement-draft-{size[0]}x{size[1]}", viewport=list(size),
                     state="arrangement draft, disclosures open")
            gates["G2"] = verdict(all(v["pass"] for v in g2.values()), g2,
                                  "commit primary fully inside viewport, 7 viewports x (image, arrangement) draft, "
                                  "all inspector disclosures open")
            primaries_grid = {k: m["primaries"] for k, m in grid.items()}
            counts = {k: len(v) for k, v in {**primaries_grid, **draft_primaries}.items()}
            worst3 = max(counts.values())
            gates["G3"] = verdict(worst3 <= 1, {"max_visible_primaries": worst3,
                                                "views_over": {k: v for k, v in counts.items() if v > 1}},
                                  "<=1 visible .btn-primary per view (no-draft and draft states)",
                                  {k: v for k, v in {**primaries_grid, **draft_primaries}.items() if len(v) > 1})
            # Leave the arrangement draft.
            set_viewport(page, (1440, 900))
            discard = page.locator("button:visible", has_text="Discard").first
            if discard.count():
                discard.click()
                page.wait_for_timeout(200)

            # G4: one tablet offline.
            set_viewport(page, (1440, 900))
            open_mode(page, "content")
            before = [r["id"] for r in roster_rows(page)]
            victim_page, victim_id = clients[-1]
            victim = next(r for r in roster_rows(page) if r["id"] == victim_id)
            ra._close_client(rig, victim_page, victim_id)
            started = time.monotonic()
            seen: dict[str, Any] = {}
            elapsed = None
            while time.monotonic() - started < 6.0:
                rows = roster_rows(page)
                row = next((r for r in rows if r["id"] == victim_id), None)
                head = header_problem(page)
                label = slot_label(page, victim_id)
                names = [n for n in (victim["label"].strip(), "Tablet " + victim["number"].strip().lstrip("#")) if n.strip()]
                seen = {
                    "header_names_tablet": any(n.lower() in head["text"].lower() for n in names),
                    "roster_row_offline_visible": bool(row and row["visible"] and "offline" in row["text"].lower()),
                    "tile_text_label": any("offline" in t.lower() for t in label["labels"]),
                    "header": head, "row": row, "tile": label, "names_tried": names}
                if seen["header_names_tablet"] and seen["roster_row_offline_visible"] and seen["tile_text_label"]:
                    elapsed = time.monotonic() - started
                    break
                page.wait_for_timeout(50)
            after = [r["id"] for r in roster_rows(page)]
            order_ok = before == after
            g4_ok = elapsed is not None and elapsed <= OFFLINE_SECONDS and order_ok
            shot(page, "g4-offline-1440x900", state="one tablet offline", mode="content")
            open_mode(page, "arrange")
            shot(page, "g4-offline-1440x900-arrange", state="one tablet offline", mode="arrange")
            # Where the roster does live (old UI: Tablets tab) is recorded for context only.
            gates["G4"] = verdict(g4_ok, {"seconds_to_all_three": elapsed, "roster_order_unchanged": order_ok,
                                          **{k: seen.get(k) for k in ("header_names_tablet", "roster_row_offline_visible",
                                                                      "tile_text_label")}},
                                  f"header names it, roster text 'Offline', tile text label, within {OFFLINE_SECONDS}s, "
                                  "order unchanged", {"last_sample": seen, "order_before": before, "order_after": after})
            result["console"] = rig.console
            result["page_errors"] = rig.page_errors
        except Exception:
            result["error"] = traceback.format_exc()
            raise
        finally:
            result["cleanup"] = rig.close()
            result["pass"] = len(gates) == 6 and all(g["pass"] for g in gates.values()) and "error" not in result
            result["gate_summary"] = {k: gates[k]["pass"] for k in sorted(gates)}
            (out / "gates.json").write_text(json.dumps(result, indent=2, default=str))
    for name in ("home", "xdg-config", "xdg-cache", "xdg-data", "tmp", "runtime"):
        shutil.rmtree(out / name, ignore_errors=True)
    return result


def table(result: dict) -> str:
    lines = ["| Gate | Result | Threshold | Measured |", "|---|---|---|---|"]
    for name in sorted(result["gates"]):
        gate = result["gates"][name]
        value = json.dumps(gate["value"], default=str)
        lines.append(f"| {name} | {'PASS' if gate['pass'] else 'FAIL'} | {gate['threshold']} | {value[:140]} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, type=Path, help="new output directory")
    parser.add_argument("--port-range", default="43900-43919", help="inclusive START-END private ports")
    args = parser.parse_args(argv)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = run(out, args.port_range)
    print(table(result))
    print("composition gates:", "PASS" if result["pass"] else "FAIL", "out", out)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
