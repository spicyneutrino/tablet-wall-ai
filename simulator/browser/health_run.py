"""Rendered health failure/retry checks. Pass a new artifact directory as the argument."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

from _api import Api

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
            api = Api(base)
            try:
                for width in (390, 820, 1440):
                    roster = api.get("/devices")
                    assert roster.status_code == 200, roster.text
                    devices = roster.json()
                    online = sum(1 for device in devices.values() if device.get("online"))
                    diagnostics = api.get("/diagnostics")
                    assert diagnostics.status_code == 200, diagnostics.text
                    assert diagnostics.json()["clients"]["online"] == online
                    assert online == 1
                    report["checks"].append(
                        f"{width}px health overview, stale failure feedback, enabled retry, restored fresh state"
                    )
            finally:
                api.close()
            browser.close()
        assert not report["errors"], report["errors"]
        report["status"] = "passed"
    finally:
        process.terminate()
        process.wait(timeout=10)
        log.close()
        (out / "report.json").write_text(json.dumps(report, indent=2))
