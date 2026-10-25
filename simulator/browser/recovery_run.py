"""Software connectivity-recovery trials for one real browser client.

    .venv/bin/python -m simulator.browser.recovery_run --artifacts /tmp/...

Each trial drops the browser context offline until the server's 15 s presence
timeout marks the device offline, restores the network, then measures the time
until the page reports connected and paints the persisted still again. This is
network emulation in one Chromium context, not Wi-Fi, radio or OS behavior.
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

from simulator.browser.run import (
    CUT_COLOURS,
    ClientSpec,
    Rig,
    calibrate_cohort,
    child_environment,
    connected,
    descendants,
    open_cohort,
    pixel_close,
    surface_centre,
)

REPO = Path(__file__).resolve().parents[2]
TRIALS = 20
OFFLINE_UNTIL_SERVER_TIMEOUT_S = 17
GATE_S = 10


async def main(artifacts: Path) -> int:
    artifacts.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="tw-recovery-", dir="/tmp"))
    for name in ("assets", "media", "tmp"):
        (root / name).mkdir()
    report: dict[str, Any] = {"trials": [], "gate_seconds": GATE_S,
                              "mode": "one Chromium context network emulation, not Wi-Fi"}
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    base = f"http://127.0.0.1:{listener.getsockname()[1]}"
    env = child_environment(root)
    env.update({"TABLET_WALL_UPLOAD_MODE": "loopback", "TABLET_WALL_OPERATOR_ORIGIN": base})
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
                raise RuntimeError("recovery server did not become ready; see server.log")
            await asyncio.sleep(.1)
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(env={**os.environ, "TMPDIR": str(root / "tmp")})
        spec = ClientSpec("recovery", 240, 160, 1)
        rig = Rig(base=base, http=http, browser=browser, playwright=playwright,
                  browser_env={**os.environ, "TMPDIR": str(root / "tmp")}, root=root,
                  artifacts=artifacts, observations=[], captured_pages=[], resources=[],
                  owned={}, check=lambda *a, **k: True)
        pages = await open_cohort(rig, ((spec, 0),), "recovery")
        page, observation = pages[0]
        assets = await calibrate_cohort(rig, pages, [0], CUT_COLOURS, "recovery")
        red = http.put("/scene", json={
            "content": {"type": "image", "asset": assets["red"], "fit": "cover"},
        }, headers={"Origin": base})
        assert red.status_code == 200, red.text
        red_rgb = CUT_COLOURS["red"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if pixel_close(await surface_centre(page), red_rgb):
                break
            await asyncio.sleep(.1)
        context = page.context
        device_id = observation.device_id
        failures = 0
        for trial in range(1, TRIALS + 1):
            await context.set_offline(True)
            started = time.monotonic()
            while time.monotonic() - started < 25:
                roster = http.get("/devices").json()
                if not roster.get(device_id, {}).get("online", True):
                    break
                await asyncio.sleep(.25)
            offline_seen = not http.get("/devices").json().get(device_id, {}).get("online", True)
            await asyncio.sleep(max(0, OFFLINE_UNTIL_SERVER_TIMEOUT_S - (time.monotonic() - started)))
            await context.set_offline(False)
            restored = time.monotonic()
            connected_ok = False
            painted = False
            while time.monotonic() - restored < 20:
                state = await page.evaluate("document.querySelector('#status')?.dataset.state")
                if state == "connected" and not connected_ok:
                    connected_ok = True
                if connected_ok and pixel_close(await surface_centre(page), red_rgb):
                    painted = True
                    break
                await asyncio.sleep(.1)
            elapsed = round(time.monotonic() - restored, 3)
            ok = offline_seen and connected_ok and painted and elapsed <= GATE_S
            if not ok:
                failures += 1
            report["trials"].append({
                "trial": trial, "offline_seen": offline_seen, "connected": connected_ok,
                "painted": painted, "seconds": elapsed, "passed": ok,
            })
            if not ok:
                await page.screenshot(path=str(artifacts / f"failure-{trial}.png"))
        seconds = sorted(t["seconds"] for t in report["trials"])
        report["summary"] = {
            "trials": TRIALS, "failures": failures,
            "p50_seconds": seconds[len(seconds) // 2],
            "p95_seconds": seconds[min(len(seconds) - 1, int(len(seconds) * .95))],
            "max_seconds": seconds[-1],
            "all_within_gate": failures == 0,
        }
        (artifacts / "report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report["summary"], indent=1))
        return 0 if failures == 0 else 1
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
