"""Rendered R5 field checks on a disposable loopback server.

    .venv/bin/python -m simulator.browser.field_run --artifacts /tmp/...

Checks the operator diagnostics admission and shape, the wake-lock state in
the roster, and a real rebind after an origin/storage loss: a fresh browser
profile registers a new id, the operator hands it the old placement and
number, and the new page reconnects. No physical device, CA trust, Wi-Fi or
soak claim.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
from playwright.async_api import async_playwright

REPO = Path(__file__).resolve().parents[2]
WAKE_STATES = {"held", "released", "unsupported", "insecure", "denied"}


async def wait_until(predicate, timeout: float, message: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await predicate():
            return
        await asyncio.sleep(.05)
    raise RuntimeError(message)


async def main(artifacts: Path) -> int:
    artifacts.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="tw-field-", dir="/tmp"))
    for name in ("assets", "media", "tmp"):
        (root / name).mkdir()
    report: dict[str, Any] = {"checks": [], "artifacts": str(artifacts), "root": str(root)}
    checks: list[dict[str, Any]] = report["checks"]

    def check(name: str, ok: bool, **detail: Any) -> bool:
        checks.append({"name": name, "passed": bool(ok), **detail})
        return bool(ok)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    base = f"http://127.0.0.1:{listener.getsockname()[1]}"
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("TABLET_WALL_")
    }
    env.update({
        "TABLET_WALL_DB": str(root / "wall.db"),
        "TABLET_WALL_ASSET_DIR": str(root / "assets"),
        "TABLET_WALL_MEDIA_DIR": str(root / "media"),
        "TABLET_WALL_UPLOAD_MODE": "loopback",
        "TABLET_WALL_OPERATOR_ORIGIN": base,
        "TMPDIR": str(root / "tmp"),
    })
    log = (artifacts / "server.log").open("x")
    process = None
    http = None
    playwright = None
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--fd", str(listener.fileno()),
             "--workers", "1", "--no-access-log"],
            cwd=REPO, env=env, pass_fds=(listener.fileno(),),
            stdout=log, stderr=subprocess.STDOUT,
        )
        listener.close()
        listener = None
        http = httpx.Client(base_url=base, headers={"Origin": base}, timeout=20)
        deadline = time.monotonic() + 20
        while True:
            try:
                if http.get("/wall").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("field server did not become ready; see server.log")
            await asyncio.sleep(.1)
        report["origin"] = base

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(env={**os.environ, "TMPDIR": str(root / "tmp")})
        old_context = await browser.new_context(viewport={"width": 800, "height": 600})
        old_page = await old_context.new_page()
        await old_page.goto(base + "/client/", wait_until="networkidle")
        await old_page.wait_for_function("document.querySelector('#status').dataset.state === 'connected'")
        old_id = await old_page.evaluate("localStorage.getItem('tablet-wall-device-id')")
        async def old_registered() -> bool:
            return http.get("/devices").json().get(old_id) is not None

        await wait_until(old_registered, 10, "old device never registered")
        devices = http.get("/devices").json()
        old_number = devices[old_id]["number"]
        old_wake = devices[old_id].get("wake_lock")
        report["old"] = {"id": old_id, "number": old_number, "wake_lock": old_wake}
        check("the client registered a display number", isinstance(old_number, int) and old_number > 0,
              old=report["old"])
        check("the roster carries a valid wake-lock state", old_wake in WAKE_STATES, wake_lock=old_wake)

        placed = http.put(f"/devices/{old_id}/placement", json={
            "x": 0, "y": 0, "w": 2000, "h": 1000,
            "bezel": {"top": 0, "right": 0, "bottom": 0, "left": 0},
        })
        check("the old client gets a placement", placed.status_code == 200, text=placed.text[-400:])

        diagnostics = http.get("/diagnostics")
        report["diagnostics"] = diagnostics.json() if diagnostics.status_code == 200 else diagnostics.text
        check("diagnostics is admitted on the loopback operator origin", diagnostics.status_code == 200)
        body = report["diagnostics"]
        check("diagnostics reports media, db, backup and clients",
              isinstance(body, dict) and {"media", "db", "backup", "clients"} <= set(body)
              and {"quota_bytes", "used_bytes", "free_bytes", "reserve_bytes", "objects", "assets", "orphans"} <= set(body["media"])
              and body["db"]["schema"] >= 1 and isinstance(body["db"]["bytes"], int)
              and "last_manifest_at" in body["backup"]
              and body["clients"]["total"] >= 1 and body["clients"]["online"] >= 1
              and set(body["clients"]["wake_lock"]) == WAKE_STATES,
              body=body)
        check("diagnostics counts the reported wake-lock state",
              sum(body["clients"]["wake_lock"].values()) == body["clients"]["total"],
              counts=body["clients"]["wake_lock"])

        bad_write = httpx.post(base + f"/devices/{old_id}/placement", json={
            "x": 0, "y": 0, "w": 1, "h": 1,
            "bezel": {"top": 0, "right": 0, "bottom": 0, "left": 0},
        }, timeout=10)
        check("a write without the operator Origin is refused", bad_write.status_code == 403,
              status=bad_write.status_code)

        await old_page.close()
        await old_context.close()
        new_context = await browser.new_context(viewport={"width": 800, "height": 600})
        new_page = await new_context.new_page()
        await new_page.goto(base + "/client/", wait_until="networkidle")
        await new_page.wait_for_function("document.querySelector('#status').dataset.state === 'connected'")
        new_id = await new_page.evaluate("localStorage.getItem('tablet-wall-device-id')")
        async def new_registered() -> bool:
            return http.get("/devices").json().get(new_id) is not None

        await wait_until(new_registered, 10, "new device never registered")
        report["new"] = {"id": new_id, "number": http.get("/devices").json()[new_id]["number"]}
        check("the replacement is a different, unplaced identity", new_id != old_id)

        editor = await browser.new_page(viewport={"width": 1440, "height": 1000})
        await editor.goto(base + "/controller/physical.html", wait_until="networkidle")
        await editor.wait_for_function(
            "document.querySelectorAll('#rebind-new option').length > 1"
            " && document.querySelectorAll('#rebind-replaces option').length > 1",
            timeout=15000,
        )
        await editor.click("#tab-system")
        await editor.wait_for_function(
            "() => document.querySelector('#panel-system')?.hidden === false",
            timeout=5000,
        )
        await editor.wait_for_function("!document.querySelector('#btn-diag-download').disabled")
        await editor.click("#btn-diag-verify")
        await editor.wait_for_function("document.querySelector('#diag-msg').textContent.includes('passed')")
        check("clean integrity has a success message",
              await editor.locator("#diag-msg").get_attribute("data-kind") == "ok")
        async with editor.expect_download() as pending_download:
            await editor.click("#btn-diag-download")
        download = await pending_download.value
        await download.save_as(str(artifacts / "diagnostics.json"))
        exported = json.loads((artifacts / "diagnostics.json").read_text())
        check("diagnostics download contains the captured report and software evidence label",
              exported["format"] == "tablet-wall-diagnostics-v1"
              and exported["captured_at"].endswith("Z")
              and exported["diagnostics"]["media"]["integrity"]["ok"] is True
              and "Physical tablet validation is pending" in exported["evidence"])
        await editor.click("#btn-diag-refresh")
        await editor.wait_for_function("!document.querySelector('#btn-diag-download').disabled")
        check("refresh clears the old integrity result",
              await editor.locator("#diag-integrity").is_hidden())

        async def damaged_diagnostics(route):
            response = await route.fetch()
            data = await response.json()
            data["media"]["integrity"] = {"ok": False, "problems": ["missing fixture object"]}
            await route.fulfill(response=response, json=data)

        await editor.route("**/diagnostics?verify=1", damaged_diagnostics)
        await editor.click("#btn-diag-verify")
        await editor.wait_for_function("document.querySelector('#diag-msg').textContent.includes('found problems')")
        check("failed integrity is an error with a visible problem",
              await editor.locator("#diag-msg").get_attribute("data-kind") == "err"
              and "missing fixture object" in await editor.locator("#diag-problems").inner_text())
        await editor.screenshot(path=str(artifacts / "diagnostics-error-desktop.png"), full_page=True)
        await editor.unroute("**/diagnostics?verify=1", damaged_diagnostics)

        async def unavailable_diagnostics(route):
            await route.fulfill(status=503, json={"detail": "fixture outage"})

        await editor.route("**/diagnostics", unavailable_diagnostics)
        await editor.click("#btn-diag-refresh")
        await editor.wait_for_function("document.querySelector('#diag-state').textContent === 'error'")
        check("failed refresh blocks stale exports and hides integrity",
              await editor.locator("#btn-diag-download").is_disabled()
              and await editor.locator("#diag-integrity").is_hidden())
        await editor.unroute("**/diagnostics", unavailable_diagnostics)
        await editor.click("#btn-diag-refresh")
        await editor.wait_for_function("!document.querySelector('#btn-diag-download').disabled")
        await editor.set_viewport_size({"width": 390, "height": 844})
        await editor.click("#tab-system")
        check("mobile diagnostics has no horizontal overflow",
              await editor.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        check("mobile task tabs expose diagnostics and support keyboard navigation",
              await editor.locator("#btn-diag-download").is_visible()
              and await editor.locator("#tab-system").get_attribute("aria-selected") == "true")
        await editor.locator("#tab-system").focus()
        await editor.keyboard.press("Home")
        check("mobile Home selects Show", await editor.locator("#panel-show").is_visible())
        await editor.keyboard.press("End")
        check("mobile End returns to System", await editor.locator("#panel-system").is_visible())
        await editor.reload(wait_until="networkidle")
        check("mobile reload preserves the selected task",
              await editor.locator("#panel-system").is_visible())
        await editor.locator("#btn-diag-download").scroll_into_view_if_needed()
        await editor.screenshot(path=str(artifacts / "diagnostics-mobile.png"))
        await editor.set_viewport_size({"width": 1440, "height": 1000})
        await editor.select_option("#rebind-new", new_id)
        await editor.select_option("#rebind-replaces", old_id)
        await editor.fill("#rebind-number", str(old_number))
        editor.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))
        await editor.click("#btn-rebind")
        await editor.wait_for_function(
            "document.querySelector('#rebind-msg')?.textContent.includes('Rebound')",
            timeout=10000,
        )
        rebound = http.get("/wall")
        roster = http.get("/devices").json()
        report["rebind"] = {"message": await editor.locator("#rebind-msg").inner_text(),
                            "placements": list(rebound.json()["placements"]),
                            "number": roster.get(new_id, {}).get("number")}
        check("the operator rebind form moves the placement and number",
              report["rebind"]["number"] == old_number
              and new_id in report["rebind"]["placements"],
              response=report["rebind"])
        await editor.screenshot(path=str(artifacts / "operator-rebind.png"), full_page=True)
        wall = http.get("/wall").json()
        check("the old identity is gone and the new one holds its place",
              new_id in wall["placements"] and old_id not in wall["placements"],
              placements=list(wall["placements"]))
        check("the old roster record disappears", old_id not in http.get("/devices").json())

        async def reconnected() -> bool:
            devices = http.get("/devices").json()
            return bool(devices.get(new_id, {}).get("online"))

        await wait_until(reconnected, 15, "the rebound tablet never reconnected")
        await new_page.wait_for_function("document.querySelector('#status').dataset.state === 'connected'")
        await new_page.reload(wait_until="networkidle")
        await new_page.wait_for_function("document.querySelector('#status').dataset.state === 'connected'")
        await new_page.screenshot(path=str(artifacts / "client-after-rebind.png"))
        report["after"] = {
            "devices": {key[:8]: {"number": value["number"], "online": value["online"],
                                  "wake_lock": value.get("wake_lock")}
                        for key, value in http.get("/devices").json().items()},
            "status": await new_page.evaluate("document.querySelector('#status').dataset.state"),
        }
        check("the rebound tablet reloads and reconnects under the new number",
              report["after"]["status"] == "connected"
              and http.get("/devices").json()[new_id]["number"] == old_number,
              after=report["after"])

        report["checks_passed"] = sum(1 for c in checks if c["passed"])
        report["checks_total"] = len(checks)
        (artifacts / "report.json").write_text(json.dumps(report, indent=2))
        return 0 if report["checks_passed"] == report["checks_total"] else 1
    finally:
        if http is not None:
            http.close()
        if playwright is not None:
            await playwright.stop()
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        log.close()
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.artifacts)))
