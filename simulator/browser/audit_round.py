"""Repeatable viewport audit against disposable data, with browser error evidence."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile

import httpx
from playwright.async_api import async_playwright

from simulator.browser.run import child_environment, stop_server

REPO = Path(__file__).resolve().parents[2]


async def run(round_number: int, artifacts: Path) -> None:
    artifacts.mkdir(parents=True, exist_ok=False)
    root = Path(tempfile.mkdtemp(prefix="tw-audit-"))
    for name in ("media", "assets", "tmp"):
        (root / name).mkdir()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
    environment = child_environment(root)
    environment["TABLET_WALL_OPERATOR_ORIGIN"] = origin
    environment["TABLET_WALL_UPLOAD_MODE"] = "loopback"
    report = {"round": round_number, "viewports": [], "errors": [], "checks": []}
    process = None
    try:
        with (artifacts / "server.log").open("w") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "main:app", "--fd", str(listener.fileno()), "--workers", "1"],
                cwd=REPO, env=environment, pass_fds=(listener.fileno(),), stdout=log, stderr=log,
            )
            listener.close()
            async with httpx.AsyncClient(base_url=origin, headers={"Origin": origin}) as http:
                for _ in range(200):
                    try:
                        if (await http.get("/wall")).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(.1)
                else:
                    raise RuntimeError("isolated server did not start")
                async with async_playwright() as playwright:
                    browser = await playwright.chromium.launch()
                    try:
                        for label, width, height in (("phone",390,844),("tablet",820,1180),("desktop",1440,1000)):
                            context = await browser.new_context(viewport={"width":width,"height":height}, has_touch=label != "desktop")
                            try:
                                page = await context.new_page()
                                errors = report["errors"]
                                page.on("pageerror", lambda error: errors.append({"kind":"pageerror","message":str(error)}))
                                page.on("console", lambda message: errors.append({"kind":"console","message":message.text}) if message.type == "error" else None)
                                page.on("response", lambda response: errors.append({"kind":"http","status":response.status,"url":response.url}) if response.status >= 400 else None)
                                page.on("requestfailed", lambda request: errors.append({"kind":"network","url":request.url,"failure":request.failure}))
                                if round_number % 2 == 0:
                                    client = await context.new_page()
                                    await client.goto(origin + "/client/")
                                    await client.wait_for_function("document.querySelector('#status').dataset.state === 'connected'")
                                for path in ("/controller/", "/controller/physical.html"):
                                    await page.goto(origin+path, wait_until="networkidle")
                                    await page.wait_for_timeout(300)
                                    for button in await page.locator('[role="tab"], .mobile-nav button').all():
                                        if await button.is_visible():
                                            await button.click()
                                            await page.keyboard.press("Tab")
                                    await page.keyboard.press("Escape")
                                    metrics = await page.evaluate("""() => ({width:innerWidth,scroll:document.documentElement.scrollWidth,
                                        buttons: [...document.querySelectorAll('button')].filter(e=>e.getBoundingClientRect().width>0).length,
                                        headings:[...document.querySelectorAll('h1')].map(e=>e.textContent)})""")
                                    report["viewports"].append({"viewport":label,"path":path,**metrics})
                                    assert metrics["scroll"] <= width, (label,path,metrics)
                                    await page.screenshot(path=str(artifacts / f"{label}-{'physical' if 'physical' in path else 'logical'}.png"), full_page=True)
                                if round_number >= 3:
                                    await context.set_offline(True)
                                    await page.wait_for_timeout(500)
                                    await context.set_offline(False)
                                    await page.reload(wait_until="networkidle")
                                    report["checks"].append(f"{label} recovered after offline and reload")
                            finally:
                                await context.close()
                    finally:
                        await browser.close()
                report["checks"].append("all viewport document widths fit")
                # Reconnect probes intentionally generate transport errors while offline.
                unexpected=[e for e in report["errors"] if not (round_number >= 3 and e["kind"] == "network" and "ERR_INTERNET_DISCONNECTED" in str(e))]
                report["unexpected_errors"] = unexpected
                assert not unexpected, unexpected
    finally:
        listener.close()
        if process is not None:
            stop_server(process)
        shutil.rmtree(root)
        report["cleanup"] = {"server_stopped": process is None or process.poll() is not None,"scratch_removed":not root.exists()}
        (artifacts/"report.json").write_text(json.dumps(report,indent=2)+"\n")


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round",type=int,required=True)
    parser.add_argument("--artifacts",type=Path,required=True)
    args=parser.parse_args()
    asyncio.run(run(args.round,args.artifacts))
