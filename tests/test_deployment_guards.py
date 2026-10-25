"""Small static guards for the portable Phase 3 service and offline frontend.

These are deliberately narrow: they catch accidental regressions in the
reference template and literal external resources, not dynamic network calls
or a real host's firewall/TLS/tablet behaviour.
"""

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


class ResourceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "img", "source"} and "src" in attrs:
            self.urls.append(attrs["src"])
        if tag == "link" and "href" in attrs and attrs.get("rel") in {
            "stylesheet", "icon", "manifest", "preload", "modulepreload"
        }:
            self.urls.append(attrs["href"])


def test_reference_service_is_single_worker_and_loopback_only():
    template = (ROOT / "deploy/tablet-wall.service.example").read_text()
    commands = [line for line in template.splitlines() if line.startswith("ExecStart=")]
    assert len(commands) == 1
    assert "--host 127.0.0.1" in commands[0]
    assert "--workers" not in commands[0]
    assert "0.0.0.0" not in commands[0]
    assert "WorkingDirectory=" in template
    assert "TABLET_WALL_DB=" in template
    assert "TABLET_WALL_ASSET_DIR=" in template
    assert "TABLET_WALL_MEDIA_DIR=" in template
    assert "TABLET_WALL_UPLOAD_MODE=" in template
    assert "TABLET_WALL_OPERATOR_ORIGIN=" in template
    assert "TABLET_WALL_TABLET_ORIGIN=" in template
    assert "Restart=on-failure" in template


def test_tablet_ingress_strips_the_operator_credential():
    """The tablet listener must not forward the internal credential.

    Text inspection only: it catches an accidental Caddyfile edit. Real
    authenticated-ingress behavior is exercised by the Caddy test in
    ``tests/test_ingress.py``.
    """
    caddyfile = (ROOT / "deploy/hotspot.Caddyfile").read_text()
    tablet, operator = caddyfile.split("https://localhost:8444", 1)
    tablet = re.sub(r"#.*", "", tablet)
    assert tablet.count("header_up -X-Tablet-Wall-Operator") == 4
    assert not re.search(r"header_up\s+X-Tablet-Wall-Operator", tablet)
    assert "header_up X-Tablet-Wall-Operator {env.WALL_OPERATOR_CREDENTIAL}" in operator
    for path in ("/uploads", "/media", "/diagnostics", "/rebind"):
        assert path not in tablet
    assert re.search(r"@asset_bytes\s*\{[^}]*method GET HEAD", tablet, re.S), \
        "the exact published-asset route accepts HEAD as well as GET"


def test_frontend_declares_no_external_static_resources():
    for page in (ROOT / "frontend").rglob("*.html"):
        parser = ResourceParser()
        parser.feed(page.read_text())
        for resource in parser.urls:
            parsed = urlsplit(resource)
            assert not parsed.scheme and not parsed.netloc, (page, resource)

    for stylesheet in (ROOT / "frontend").rglob("*.css"):
        css = stylesheet.read_text()
        # Fetchable CSS resources only; a URL in a comment is not a request.
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
        for resource in re.findall(r"url\(\s*['\"]?([^)'\"]+)", css):
            parsed = urlsplit(resource.strip())
            assert not parsed.scheme and not parsed.netloc, (stylesheet, resource)
        assert not re.search(r"@import\b", css, flags=re.IGNORECASE), stylesheet
