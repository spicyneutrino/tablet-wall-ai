"""Rendered health failure/retry checks. Pass a new artifact directory as the argument."""

import json, os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

repo = Path(__file__).resolve().parents[2]
out = Path(sys.argv[1])
out.mkdir()
with tempfile.TemporaryDirectory(prefix="tw-health-") as scratch:
    root = Path(scratch)
    for name in ("media", "assets"):
        (root / name).mkdir()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    base = f"http://127.0.0.1:{listener.getsockname()[1]}"
    env = {k: v for k, v in os.environ.items() if not k.startswith("TABLET_WALL_")}
    env.update(
        TABLET_WALL_DB=str(root / "wall.db"),
        TABLET_WALL_MEDIA_DIR=str(root / "media"),
        TABLET_WALL_ASSET_DIR=str(root / "assets"),
        TABLET_WALL_OPERATOR_ORIGIN=base,
        TABLET_WALL_UPLOAD_MODE="loopback",
    )
    log = (out / "server.log").open("w")
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--fd", str(listener.fileno())],
        cwd=repo,
        env=env,
        pass_fds=(listener.fileno(),),
        stdout=log,
        stderr=log,
    )
    listener.close()
    report = {"checks": [], "errors": []}
    try:
        import urllib.request

        for _ in range(200):
            try:
                urllib.request.urlopen(base + "/wall")
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            client = browser.new_page()
            client.goto(base + "/client/")
            client.wait_for_function(
                "document.querySelector('#status').dataset.state === 'connected'"
            )
            for width in (390, 820, 1440):
                page = browser.new_page(
                    viewport={"width": width, "height": 844}, has_touch=width < 1000
                )
                page.on("pageerror", lambda e: report["errors"].append(str(e)))
                page.goto(base + "/controller/physical.html", wait_until="networkidle")
                page.wait_for_function(
                    "document.querySelector('#wall-health').textContent.includes('1 online')"
                )
                assert page.locator("#btn-wall-health").bounding_box()["height"] >= 44
                page.locator("#btn-wall-health").click()
                page.route(
                    "**/devices",
                    lambda route: route.fulfill(
                        status=503,
                        content_type="application/json",
                        body='{"detail":"injected unavailable"}',
                    ),
                )
                page.locator("#btn-roster-refresh").click()
                page.wait_for_function(
                    "document.querySelector('#roster-status').textContent.includes('last known')"
                )
                assert "Last known:" in page.locator("#wall-health").inner_text()
                assert page.locator("#btn-roster-refresh").is_enabled()
                page.screenshot(path=str(out / f"stale-{width}.png"), full_page=True)
                page.unroute("**/devices")
                page.locator("#btn-roster-refresh").click()
                page.wait_for_function(
                    "!document.querySelector('#device-count').textContent.includes('last known')"
                )
                assert "1 of 1 online" in page.locator("#device-count").inner_text()
                report["checks"].append(
                    f"{width}px health overview, stale failure feedback, enabled retry, restored fresh state"
                )
                page.close()
            browser.close()
        assert not report["errors"], report["errors"]
        report["status"] = "passed"
    finally:
        process.terminate()
        process.wait(timeout=10)
        log.close()
        (out / "report.json").write_text(json.dumps(report, indent=2))
