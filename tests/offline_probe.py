"""Runs inside a network namespace that has loopback and no other route.

Started by ``tests/test_offline.py`` through ``unshare -rn``. Boots the app on
previously seeded data twice (a cold start and a restart), loads the served
pages and one real client page, and prints a single JSON document. It never
decides pass or fail: the parent test does.
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deploy import drill  # noqa: E402

PAGES = ("/client/", "/controller/", "/controller/physical.html")
URL_ATTRIBUTES = {"src", "href", "action", "data", "poster", "srcset", "formaction"}
SCHEME_URL = re.compile(r"\b(?:https?|wss?)://([A-Za-z0-9][A-Za-z0-9.-]*)(?::\d+)?")
CSS_URL = re.compile(r"url\(\s*['\"]?([^)'\"]+)|@import\s+['\"]([^'\"]+)", re.IGNORECASE)
# An XML namespace identifier is a name, never fetched.
NAMESPACES = {"www.w3.org"}


class References(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in URL_ATTRIBUTES and value:
                self.urls.extend(part.split()[0] for part in value.split(",") if part.strip())


def wan_reachable() -> list[str]:
    reached = []
    for host, port in (("1.1.1.1", 443), ("8.8.8.8", 53), ("192.0.2.1", 80)):
        with socket.socket() as sock:
            sock.settimeout(2)
            try:
                sock.connect((host, port))
                reached.append(f"{host}:{port}")
            except OSError:
                pass
    return reached


def crawl(instance: drill.Instance) -> dict:
    """Fetch every page and the same-origin files they reference; list foreign URLs."""
    own_host = urlsplit(instance.base).hostname
    seen: dict[str, str] = {}
    foreign: list[str] = []
    queue = list(PAGES)

    def external(url: str, where: str) -> None:
        parts = urlsplit(urljoin(instance.base + "/", url))
        if parts.scheme in ("http", "https", "ws", "wss") and parts.hostname != own_host:
            foreign.append(f"{where}: {url}")

    while queue:
        path = queue.pop()
        if path in seen:
            continue
        status, body = instance.request("GET", path)
        if status != 200:
            seen[path] = f"HTTP {status}"
            continue
        text = body.decode("utf-8", "replace") if isinstance(body, bytes) else json.dumps(body)
        seen[path] = "ok"
        references: list[str] = []
        if path.endswith((".html", "/")):
            parser = References()
            parser.feed(text)
            references = parser.urls
        elif path.endswith(".css"):
            references = [a or b for a, b in CSS_URL.findall(text)]
        executable_text = path.endswith(("/", ".html", ".js", ".css", ".svg"))
        for host in SCHEME_URL.findall(text) if executable_text else []:
            if host not in NAMESPACES and host != own_host:
                foreign.append(f"{path}: {host}")
        for reference in references:
            parts = urlsplit(reference)
            if parts.scheme or parts.netloc:
                external(reference, path)
            elif parts.path and not reference.startswith(("#", "data:")):
                queue.append(urljoin(path, parts.path))
    return {"fetched": seen, "foreign": foreign}


def main() -> None:
    config = json.loads(sys.argv[1])
    out: dict = {"wan_reachable": wan_reachable()}
    instance = drill.Instance(Path(config["db"]), Path(config["assets"]), Path(config["media"]))
    try:
        for label in ("cold_start", "restart"):
            instance.start()
            out[label] = {
                "observed": drill.observe(instance),
                "asset_sha": drill.served_sha(instance, config["asset"]),
            }
            if label == "cold_start":
                out["pages"] = crawl(instance)
                client = subprocess.run(
                    ["node", str(ROOT / "tests" / "offline_client.js"), instance.base,
                     config["device"], str(config["number"])],
                    capture_output=True, text=True, timeout=60,
                )
                out["client"] = (
                    json.loads(client.stdout.splitlines()[-1]) if client.stdout.strip()
                    else {"error": client.stderr[-500:]}
                )
            instance.stop()
    finally:
        instance.stop()
    print(json.dumps(out))


main()
