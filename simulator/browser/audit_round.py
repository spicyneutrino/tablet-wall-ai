"""Repeatable viewport audit against disposable data, with browser error evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
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
    auth_token = secrets.token_urlsafe(40) if round_number >= 5 else None
    headers = {"Origin": origin}
    if auth_token:
        environment["TABLET_WALL_AUTH_TOKEN"] = auth_token
        headers["Authorization"] = f"Bearer {auth_token}"
    report = {
        "round": round_number,
        "status": "running",
        "viewports": [],
        "errors": [],
        "checks": [],
    }
    process = None
    try:
        with (artifacts / "server.log").open("w") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "main:app",
                    "--fd",
                    str(listener.fileno()),
                    "--workers",
                    "1",
                ],
                cwd=REPO,
                env=environment,
                pass_fds=(listener.fileno(),),
                stdout=log,
                stderr=log,
            )
            listener.close()
            async with httpx.AsyncClient(base_url=origin, headers=headers) as http:
                for _ in range(200):
                    try:
                        if (await http.get("/wall")).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.1)
                else:
                    raise RuntimeError("isolated server did not start")
                async with async_playwright() as playwright:
                    browser = await playwright.chromium.launch()
                    try:
                        sizes = (
                            (
                                ("phone", 844, 390),
                                ("tablet", 1180, 820),
                                ("desktop", 1920, 1080),
                            )
                            if round_number >= 8 and round_number % 2 == 0
                            else (
                                ("phone", 390, 844),
                                ("tablet", 820, 1180),
                                ("desktop", 1440, 1000),
                            )
                        )
                        for label, width, height in sizes:
                            context = await browser.new_context(
                                viewport={"width": width, "height": height},
                                has_touch=label != "desktop",
                            )
                            try:
                                page = await context.new_page()
                                if auth_token:
                                    await page.goto(origin + "/controller/")
                                    await page.get_by_label("Access token").fill(
                                        auth_token
                                    )
                                    await page.get_by_role(
                                        "button", name="Sign in", exact=True
                                    ).click()
                                    await page.wait_for_url(origin + "/controller/")
                                    await page.wait_for_load_state("networkidle")
                                    cookies = await context.cookies()
                                    assert any(
                                        cookie["httpOnly"]
                                        and cookie["sameSite"] == "Strict"
                                        for cookie in cookies
                                    )
                                    report["checks"].append(
                                        f"{label} browser login and HttpOnly cookie"
                                    )
                                errors = report["errors"]
                                probe = {"offline": False}
                                page.on(
                                    "pageerror",
                                    lambda error: errors.append(
                                        {
                                            "kind": "pageerror",
                                            "message": str(error),
                                            "probe": probe["offline"],
                                        }
                                    ),
                                )
                                page.on(
                                    "console",
                                    lambda message: (
                                        errors.append(
                                            {
                                                "kind": "console",
                                                "message": message.text,
                                                "probe": probe["offline"],
                                            }
                                        )
                                        if message.type == "error"
                                        else None
                                    ),
                                )
                                page.on(
                                    "response",
                                    lambda response: (
                                        errors.append(
                                            {
                                                "kind": "http",
                                                "status": response.status,
                                                "url": response.url,
                                                "probe": probe["offline"],
                                            }
                                        )
                                        if response.status >= 400
                                        else None
                                    ),
                                )
                                page.on(
                                    "requestfailed",
                                    lambda request: errors.append(
                                        {
                                            "kind": "network",
                                            "url": request.url,
                                            "failure": request.failure,
                                            "probe": probe["offline"],
                                        }
                                    ),
                                )
                                if round_number % 2 == 0:
                                    client = await context.new_page()
                                    await client.goto(origin + "/client/")
                                    await client.wait_for_function(
                                        "document.querySelector('#status').dataset.state === 'connected'"
                                    )
                                for path in (
                                    "/controller/",
                                    "/controller/physical.html",
                                ):
                                    await page.goto(
                                        origin + path, wait_until="networkidle"
                                    )
                                    await page.wait_for_timeout(300)
                                    for button in await page.locator(
                                        '[role="tab"], .mobile-nav button'
                                    ).all():
                                        if await button.is_visible():
                                            await button.click()
                                            await page.keyboard.press("Tab")
                                    await page.keyboard.press("Escape")
                                    if round_number >= 6:
                                        await page.keyboard.press("Tab")
                                        focused = await page.evaluate(
                                            "document.activeElement.tagName"
                                        )
                                        assert focused not in {"BODY", "HTML"}, focused
                                    metrics = await page.evaluate("""() => ({width:innerWidth,scroll:document.documentElement.scrollWidth,
                                        buttons: [...document.querySelectorAll('button')].filter(e=>e.getBoundingClientRect().width>0).length,
                                        headings:[...document.querySelectorAll('h1')].map(e=>e.textContent)})""")
                                    report["viewports"].append(
                                        {"viewport": label, "path": path, **metrics}
                                    )
                                    assert metrics["scroll"] <= width, (
                                        label,
                                        path,
                                        metrics,
                                    )
                                    await page.screenshot(
                                        path=str(
                                            artifacts
                                            / f"{label}-{'physical' if 'physical' in path else 'logical'}.png"
                                        ),
                                        full_page=True,
                                    )
                                if round_number >= 3:
                                    probe["offline"] = True
                                    await context.set_offline(True)
                                    await page.wait_for_timeout(500)
                                    await context.set_offline(False)
                                    await page.reload(wait_until="networkidle")
                                    await page.wait_for_function(
                                        "document.querySelector('#etag-state').textContent === 'current'"
                                    )
                                    probe["offline"] = False
                                    report["checks"].append(
                                        f"{label} recovered after offline and reload"
                                    )
                            finally:
                                await context.close()
                    finally:
                        await browser.close()
                if round_number >= 6:
                    before = (await http.get("/wall")).json()
                    for payload in ({"width": -1}, {"width": "bad"}, {"height": 0}):
                        rejected = await http.put("/wall", json=payload)
                        assert rejected.status_code == 422, rejected.text
                    assert (await http.get("/wall")).json() == before
                    report["checks"].append(
                        "invalid dimensions leave the wall unchanged"
                    )
                    rejected = await http.post(
                        "/devices/color",
                        json={"color": "#ffffff"},
                        headers={"Origin": "https://foreign.invalid"},
                    )
                    assert rejected.status_code == 403, rejected.text
                    report["checks"].append(
                        "foreign origin remains rejected with valid bearer auth"
                    )
                if round_number >= 11:
                    for source in (REPO / "frontend").rglob("*.js"):
                        path = "/" + str(source.relative_to(REPO / "frontend"))
                        response = await http.get(path)
                        assert (
                            response.status_code == 200
                            and response.content == source.read_bytes()
                        ), path
                        assert (
                            response.headers["cache-control"] == "private, no-store"
                        ), path
                        etag = response.headers["etag"]
                        cached = await http.get(path, headers={"If-None-Match": etag})
                        assert cached.status_code == 304, (path, cached.status_code)
                        assert cached.headers["cache-control"] == "private, no-store", (
                            path
                        )
                    report["checks"].append(
                        "all extracted scripts match disk bytes and revalidate under private authentication caching"
                    )
                if auth_token:
                    async with httpx.AsyncClient(base_url=origin) as anonymous:
                        for path in (
                            "/wall",
                            "/client/client.js",
                            "/controller/controller.js",
                            "/diagnostics",
                        ):
                            assert (await anonymous.get(path)).status_code == 401
                    report["checks"].append(
                        "anonymous API and static requests remain blocked"
                    )
                report["checks"].append("all viewport document widths fit")
                # Reconnect probes intentionally generate transport errors while offline.
                unexpected = [
                    e
                    for e in report["errors"]
                    if not (
                        e.get("probe")
                        and e["kind"] in {"network", "console"}
                        and any(
                            message in str(e)
                            for message in ("ERR_INTERNET_DISCONNECTED", "ERR_ABORTED")
                        )
                    )
                ]
                report["unexpected_errors"] = unexpected
                assert not unexpected, unexpected
                report["status"] = "passed"
    except BaseException as error:
        report["status"] = "failed"
        report["failure"] = str(error)
        raise
    finally:
        listener.close()
        if process is not None:
            stop_server(process)
        shutil.rmtree(root)
        report["cleanup"] = {
            "server_stopped": process is None or process.poll() is not None,
            "scratch_removed": not root.exists(),
        }
        (artifacts / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.round, args.artifacts))
