"""Real two-origin Caddy ingress evidence for R1 admission (not a text check).

Starts the actual app on a loopback port and Caddy in front of it with two
listeners: the tablet allowlist (which must never reach /uploads or /media and
must strip the internal credential) and the authenticated operator listener
(which must overwrite any client credential and reach the backend in proxy
mode). Skipped only when Caddy is not installed.
"""

import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from websockets.sync.client import connect

from deploy import hotspot

from video_fixtures import HAVE_FFMPEG, _ensure as build_fixture

CWD = Path(__file__).resolve().parents[1]
CADDY = shutil.which("caddy")
CREDENTIAL = "test-ingress-credential-0123456789"
PASSWORD = "operator-test-password"


@pytest.fixture(autouse=True)
def private_caddy_directories(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "caddy-config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "caddy-data"))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for(url: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(url, timeout=.5)
            return
        except httpx.HTTPError:
            time.sleep(.1)
    raise RuntimeError(f"{url} did not become ready")


def jpeg() -> bytes:
    from io import BytesIO
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (48, 32), (10, 90, 170)).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.mark.skipif(CADDY is None, reason="Caddy is not installed")
def test_two_origin_ingress_admits_only_the_authenticated_operator(tmp_path):
    app_port, tablet_port, operator_port = free_port(), free_port(), free_port()
    data = tmp_path / "data"
    for name in ("assets", "media"):
        (data / name).mkdir(parents=True)
    operator_origin = f"http://127.0.0.1:{operator_port}"

    hash_result = subprocess.run(
        [CADDY, "hash-password", "--plaintext", PASSWORD],
        capture_output=True, text=True, check=True,
    )
    password_hash = hash_result.stdout.strip()

    config = tmp_path / "Caddyfile"
    config.write_text(f'''{{
\tadmin off
\tauto_https off
}}
http://127.0.0.1:{tablet_port} {{
\t@uploads path /uploads*
\thandle @uploads {{
\t\trespond "Forbidden" 403
\t}}
\t@media path /media* /diagnostics*
\thandle @media {{
\t\trespond "Forbidden" 403
\t}}
\t@asset {{
\t\tmethod GET
\t\tpath_regexp asset ^/assets/sha256:[0-9a-f]{{64}}$
\t}}
\thandle @asset {{
\t\treverse_proxy 127.0.0.1:{app_port} {{
\t\t\theader_up -X-Tablet-Wall-Operator
\t\t}}
\t}}
\thandle {{
\t\trespond "Forbidden" 403
\t}}
}}
http://127.0.0.1:{operator_port} {{
\t@surface path /uploads* /media* /diagnostics*
\thandle @surface {{
\t\tbasic_auth {{
\t\t\toperator {password_hash}
\t\t}}
\t\treverse_proxy 127.0.0.1:{app_port} {{
\t\t\theader_up X-Tablet-Wall-Operator "{CREDENTIAL}"
\t\t\theader_up -Authorization
\t\t\theader_up -Cookie
\t\t}}
\t}}
\thandle {{
\t\trespond "Not found" 404
\t}}
}}
''')

    env = {
        **os.environ,
        "TABLET_WALL_DB": str(data / "wall.db"),
        "TABLET_WALL_ASSET_DIR": str(data / "assets"),
        "TABLET_WALL_MEDIA_DIR": str(data / "media"),
        "TABLET_WALL_UPLOAD_MODE": "proxy",
        "TABLET_WALL_OPERATOR_ORIGIN": operator_origin,
        "TABLET_WALL_OPERATOR_CREDENTIAL": CREDENTIAL,
    }
    app = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
         "--port", str(app_port), "--no-access-log"],
        cwd=CWD, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    caddy = None
    try:
        wait_for(f"http://127.0.0.1:{app_port}/wall")
        caddy = subprocess.Popen(
            [CADDY, "run", "--config", str(config), "--adapter", "caddyfile"],
            cwd=tmp_path, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        wait_for(f"http://127.0.0.1:{operator_port}/media", timeout=20)

        tablet = f"http://127.0.0.1:{tablet_port}"
        operator = f"http://127.0.0.1:{operator_port}"
        auth = ("operator", PASSWORD)

        # Tablet listener: never reaches upload/library, and a forged internal
        # credential cannot change that.
        assert httpx.get(f"{tablet}/media", headers={"X-Tablet-Wall-Operator": CREDENTIAL}).status_code == 403
        assert httpx.get(f"{tablet}/diagnostics", headers={"X-Tablet-Wall-Operator": CREDENTIAL}).status_code == 403
        assert httpx.post(f"{tablet}/uploads", content=jpeg(),
                          headers={"X-Tablet-Wall-Operator": CREDENTIAL,
                                   "Origin": operator_origin}).status_code == 403

        # Operator listener: no auth is refused by Caddy, not the app.
        assert httpx.get(f"{operator}/media").status_code == 401

        # Diagnostics are operator reads: refused without operator proof,
        # served with the authenticated proxy credential, and never reachable
        # on the tablet listener.
        assert httpx.get(f"{operator}/diagnostics").status_code == 401
        diagnostics = httpx.get(f"{operator}/diagnostics", auth=auth)
        assert diagnostics.status_code == 200, diagnostics.text
        assert diagnostics.json()["media"]["assets"] == 0

        # Auth + library read: Caddy supplied the credential on a GET.
        library = httpx.get(f"{operator}/media", auth=auth)
        assert library.status_code == 200, library.text
        assert library.json()["assets"] == []

        # The client's forged credential is overwritten by Caddy; the exact
        # Origin is still required by the backend.
        uploaded = httpx.post(
            f"{operator}/uploads?name=ingress.jpg", content=jpeg(), auth=auth,
            headers={"Origin": operator_origin,
                     "Content-Type": "image/jpeg",
                     "X-Tablet-Wall-Operator": "forged-by-the-client"},
        )
        assert uploaded.status_code == 201, uploaded.text
        descriptor = uploaded.json()["asset"]

        wrong_origin = httpx.post(
            f"{operator}/uploads?name=wrong.jpg", content=jpeg(), auth=auth,
            headers={"Origin": "http://127.0.0.1:1", "Content-Type": "image/jpeg"},
        )
        assert wrong_origin.status_code == 403

        # Published bytes are readable on the tablet listener, without the
        # internal credential ever being forwarded by that listener.
        served = httpx.get(f"{tablet}{descriptor['url']}")
        assert served.status_code == 200
        assert len(served.content) == descriptor["bytes"]

        if HAVE_FFMPEG:
            clip = build_fixture("baseline.mp4", tmp_path).read_bytes()
            sent = httpx.post(
                f"{operator}/uploads?name=clip.mp4", content=clip, auth=auth, timeout=60,
                headers={"Origin": operator_origin, "Content-Type": "video/mp4",
                         "X-Tablet-Wall-Operator": "forged-by-the-client"},
            )
            assert sent.status_code == 201, sent.text
            video = sent.json()["asset"]

            # The tablet listener still cannot upload or list, whatever the type.
            assert httpx.post(
                f"{tablet}/uploads", content=clip,
                headers={"X-Tablet-Wall-Operator": CREDENTIAL, "Origin": operator_origin,
                         "Content-Type": "video/mp4"},
            ).status_code == 403
            assert httpx.get(f"{tablet}/media").status_code == 403

            # ... but it reads the published object, with ranges, through the proxy.
            first = httpx.get(f"{tablet}{video['url']}", headers={"Range": "bytes=0-99"})
            assert first.status_code == 206
            assert first.headers["content-range"] == f"bytes 0-99/{video['bytes']}"
            assert len(first.content) == 100
            tail = httpx.get(f"{tablet}{video['url']}", headers={"Range": "bytes=-50"})
            assert tail.status_code == 206 and len(tail.content) == 50
            open_ended = httpx.get(
                f"{tablet}{video['url']}", headers={"Range": f"bytes={video['bytes'] - 10}-"}
            )
            assert open_ended.status_code == 206 and len(open_ended.content) == 10
            past = httpx.get(
                f"{tablet}{video['url']}", headers={"Range": f"bytes={video['bytes']}-"}
            )
            assert past.status_code == 416
            assert past.headers["content-range"] == f"bytes */{video['bytes']}"
            etag = first.headers["etag"]
            assert httpx.get(
                f"{tablet}{video['url']}", headers={"Range": "bytes=0-9", "If-Range": etag}
            ).status_code == 206
            assert httpx.get(
                f"{tablet}{video['url']}", headers={"If-None-Match": etag}
            ).status_code == 304
            assert httpx.get(f"{tablet}{video['poster']['url']}").status_code == 200

            # HEAD and a ranged HEAD under the real server (the proxy's tablet
            # allowlist is GET-only, so these go to the backend directly).
            backend = f"http://127.0.0.1:{app_port}{video['url']}"
            head = httpx.head(backend)
            assert head.status_code == 200 and head.content == b""
            assert head.headers["content-length"] == str(video["bytes"])
            ranged_head = httpx.head(backend, headers={"Range": "bytes=0-9"})
            assert ranged_head.status_code == 206
            assert ranged_head.headers["content-range"] == f"bytes 0-9/{video['bytes']}"
    finally:
        for process in (caddy, app):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


# ---------------------------------------------------------------------------
# The deployed tablet allowlist itself, imported rather than re-written
# ---------------------------------------------------------------------------

AUTH_TOKEN = "test-tablet-ingress-token-at-least-32-bytes"


def app_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    """A clean backend environment: no deployment variable leaks in from a shell."""
    data = tmp_path / "data"
    for name in ("assets", "media"):
        (data / name).mkdir(parents=True, exist_ok=True)
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith("TABLET_WALL_") and key != "WALL_BACKEND_PORT"
    }
    return {
        **env,
        "TABLET_WALL_DB": str(data / "wall.db"),
        "TABLET_WALL_ASSET_DIR": str(data / "assets"),
        "TABLET_WALL_MEDIA_DIR": str(data / "media"),
        **extra,
    }


def tablet_site(port: int) -> str:
    return f'''http://127.0.0.1:{port} {{
\timport {(CWD / "deploy/tablet-routes.caddy").as_posix()}
}}
'''


@contextmanager
def start_processes(config: Path, env: dict[str, str], app_port: int, wait_url: str):
    app = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
         "--port", str(app_port), "--no-access-log"],
        cwd=CWD, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    caddy = None
    try:
        wait_for(f"http://127.0.0.1:{app_port}/wall")
        caddy = subprocess.Popen(
            [CADDY, "run", "--config", str(config), "--adapter", "caddyfile"],
            cwd=config.parent, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        wait_for(wait_url, timeout=20)
        yield app, caddy
    finally:
        for process in (caddy, app):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


@pytest.mark.skipif(CADDY is None, reason="Caddy is not installed")
def test_tablet_ingress_allows_only_the_exact_app_auth_entry_points(tmp_path):
    app_port, tablet_port = free_port(), free_port()
    env = app_env(tmp_path, TABLET_WALL_AUTH_TOKEN=AUTH_TOKEN,
                  WALL_BACKEND_PORT=str(app_port))
    config = tmp_path / "Caddyfile"
    config.write_text(
        "{\n\tadmin off\n\tauto_https off\n}\n" + tablet_site(tablet_port)
    )
    tablet = f"http://127.0.0.1:{tablet_port}"

    with start_processes(config, env, app_port, f"{tablet}/client/") as (app, caddy):
        assert app.poll() is None and caddy.poll() is None

        page = httpx.get(f"{tablet}/auth/login?next=%2Fclient")
        assert page.status_code == 200, page.text
        assert 'type="password"' in page.text
        assert 'name="next" value="/client"' in page.text

        # A direct visit still returns to the tablet client, not the operator UI.
        bare = httpx.get(f"{tablet}/auth/login")
        assert bare.status_code == 200, bare.text
        assert 'name="next" value="/client/"' in bare.text

        # Existing app middleware rejects foreign Origin and malformed forms.
        foreign = httpx.post(
            f"{tablet}/auth/login", data={"token": AUTH_TOKEN, "next": "/client"},
            headers={"Origin": "https://attacker.invalid"},
        )
        assert foreign.status_code == 403
        malformed = httpx.post(
            f"{tablet}/auth/login", json={"token": AUTH_TOKEN},
            headers={"Origin": tablet},
        )
        assert malformed.status_code == 415

        with httpx.Client(base_url=tablet, follow_redirects=False) as browser:
            signed = browser.post(
                "/auth/login", data={"token": AUTH_TOKEN, "next": "/client"},
                headers={"Origin": tablet},
            )
            assert signed.status_code == 303
            assert signed.headers["location"] == "/client"
            assert browser.cookies.get("tablet_wall_session")

            client_surface = browser.get("/client/")
            assert client_surface.status_code == 200, client_surface.text
            assert client_surface.headers["cache-control"] == "private, no-store"

            signed_out = browser.post("/auth/logout", headers={"Origin": tablet})
            assert signed_out.status_code == 303
            assert signed_out.headers["location"] == "/auth/login"

        # Exact method/path only: the login page is not a wildcard surface.
        for method, path in (
            ("GET", "/auth/logout"),
            ("GET", "/auth/login/"),
            ("PUT", "/auth/login"),
            ("DELETE", "/auth/login"),
            ("GET", "/auth/logout/"),
        ):
            assert httpx.request(method, f"{tablet}{path}").status_code == 403, (method, path)

        # Operator paths stay denied on the tablet listener.
        for path in ("/diagnostics", "/media", "/uploads", "/wall", "/controller/"):
            assert httpx.get(f"{tablet}{path}").status_code == 403, path


@pytest.mark.skipif(CADDY is None, reason="Caddy is not installed")
def test_uploads_disabled_diagnostics_needs_operator_proof(tmp_path):
    app_port, tablet_port, operator_port = free_port(), free_port(), free_port()
    operator_origin = f"http://127.0.0.1:{operator_port}"
    hash_result = subprocess.run(
        [CADDY, "hash-password", "--plaintext", PASSWORD],
        capture_output=True, text=True, check=True,
    )
    password_hash = hash_result.stdout.strip()
    env = app_env(
        tmp_path,
        TABLET_WALL_UPLOAD_MODE="disabled",
        TABLET_WALL_OPERATOR_ORIGIN=operator_origin,
        TABLET_WALL_OPERATOR_CREDENTIAL=CREDENTIAL,
        WALL_BACKEND_PORT=str(app_port),
    )
    config = tmp_path / "Caddyfile"
    config.write_text(
        "{\n\tadmin off\n\tauto_https off\n}\n"
        + tablet_site(tablet_port)
        + f'''http://127.0.0.1:{operator_port} {{
\t@surface path /uploads* /media* /diagnostics*
\thandle @surface {{
\t\tbasic_auth {{
\t\t\toperator {password_hash}
\t\t}}
\t\treverse_proxy 127.0.0.1:{app_port} {{
\t\t\theader_up X-Tablet-Wall-Operator "{CREDENTIAL}"
\t\t\theader_up -Authorization
\t\t\theader_up -Cookie
\t\t}}
\t}}
\thandle {{
\t\trespond "Not found" 404
\t}}
}}
'''
    )
    tablet = f"http://127.0.0.1:{tablet_port}"
    operator = f"http://127.0.0.1:{operator_port}"
    auth = ("operator", PASSWORD)

    with start_processes(config, env, app_port, f"{operator}/diagnostics") as (app, caddy):
        assert app.poll() is None and caddy.poll() is None

        # The tablet listener never reaches diagnostics, even with a forged
        # internal credential, and an unauthenticated proxy is refused too.
        assert httpx.get(
            f"{tablet}/diagnostics", headers={"X-Tablet-Wall-Operator": CREDENTIAL}
        ).status_code == 403
        assert httpx.get(
            f"http://127.0.0.1:{app_port}/diagnostics",
            headers={"X-Forwarded-For": "192.168.137.2"},
        ).status_code == 403

        # Caddy, not the app, refuses an unauthenticated operator request.
        assert httpx.get(f"{operator}/diagnostics").status_code == 401
        assert httpx.get(f"{operator}/diagnostics", auth=("operator", "wrong")).status_code == 401

        # Uploads are disabled, but the authenticated operator can read and
        # verify storage. A direct loopback caller is the local operator.
        report = httpx.get(f"{operator}/diagnostics", auth=auth)
        assert report.status_code == 200, report.text
        assert report.json()["media"]["assets"] == 0
        assert "integrity" not in report.json()["media"]
        assert report.headers["cache-control"] == "no-store"
        verified = httpx.get(f"{operator}/diagnostics?verify=1", auth=auth)
        assert verified.status_code == 200, verified.text
        assert verified.json()["media"]["integrity"] == {"ok": True, "problems": []}
        local = httpx.get(f"http://127.0.0.1:{app_port}/diagnostics")
        assert local.status_code == 200, local.text


def stored_state(data):
    with sqlite3.connect(f"file:{data / 'wall.db'}?mode=ro", uri=True) as db:
        dump = "\n".join(db.iterdump()).encode()
    return {
        "database_sha256": hashlib.sha256(dump).hexdigest(),
        "media_files": {
            str(path.relative_to(data)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((data / "media").rglob("*")) if path.is_file()
        },
    }


@pytest.mark.skipif(CADDY is None, reason="Caddy is not installed; composed ingress remains unverified")
@pytest.mark.timeout(60)
def test_generated_hotspot_ingress_keeps_loopback_uploads_operator_only(tmp_path):
    app_port, tablet_port = free_port(), free_port()
    data = tmp_path / "data"
    settings = hotspot.Settings("unused-test-interface", str(data), app_port, tablet_port)
    env = app_env(tmp_path)
    env.update(hotspot.backend_environment(settings, "127.0.0.1", data, None, True))
    env.update({"XDG_CONFIG_HOME": str(tmp_path / "caddy-config"),
                "XDG_DATA_HOME": str(tmp_path / "caddy-data")})
    operator = f"http://127.0.0.1:{app_port}"
    tablet = f"http://127.0.0.1:{tablet_port}"
    config = tmp_path / "generated.Caddyfile"
    config.write_text(hotspot.proxy_config("127.0.0.1", tablet_port))
    manifest = {
        "caddy_version": subprocess.check_output([CADDY, "version"], text=True).strip(),
        "config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
        "allowlist_sha256": hashlib.sha256((CWD / "deploy/tablet-routes.caddy").read_bytes()).hexdigest(),
        "backend_port": app_port, "tablet_port": tablet_port,
        "operator_origin": operator, "upload_mode": env["TABLET_WALL_UPLOAD_MODE"],
        "backend_bind": "127.0.0.1", "requests": [],
        "source_sha256": {
            path: hashlib.sha256((CWD / path).read_bytes()).hexdigest()
            for path in ("main.py", "tabletwall/media.py", "deploy/hotspot.py", "tests/test_ingress.py")
        },
    }

    def recorded(client, method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        manifest["requests"].append({
            "origin": str(client.base_url).rstrip("/"), "method": method, "path": path,
            "headers": list(kwargs.get("headers", {}).items())
                if isinstance(kwargs.get("headers", {}), dict) else kwargs["headers"],
            "status": response.status_code,
        })
        return response

    processes = ()
    try:
        with start_processes(config, env, app_port, f"{tablet}/client/") as (app, caddy), \
                httpx.Client(base_url=operator, timeout=15) as local, \
                httpx.Client(base_url=tablet, timeout=15) as public:
            processes = (app, caddy)
            assert app.poll() is None and caddy.poll() is None
            before = recorded(local, "GET", "/api/v3/config").json()
            assert before["capabilities"]["uploads"] is True
            body = jpeg()
            upload_headers = {"Origin": operator, "Content-Type": "image/jpeg"}
            uploaded = recorded(local, "POST", "/uploads?name=operator.jpg",
                                content=body, headers=upload_headers)
            assert uploaded.status_code == 201, uploaded.text
            descriptor = uploaded.json()["asset"]
            manifest["published_asset"] = descriptor
            after = recorded(local, "GET", "/api/v3/config").json()
            assert (after["etag"], after["scene"], after["layout"]) == (
                before["etag"], before["scene"], before["layout"])
            baseline = stored_state(data)
            manifest["state_before_denials"] = baseline

            bad_origins = [[], [("Origin", "http://wrong.invalid")], [("Origin", "null")],
                           [("Origin", operator), ("Origin", operator)],
                           [("Origin", f"{operator}, {operator}")]]
            for origins in bad_origins:
                refused = recorded(local, "POST", "/uploads?name=refused.jpg", content=body,
                                   headers=[("Content-Type", "image/jpeg"), *origins])
                assert refused.status_code == 403, refused.text
            for header in ("Forwarded", "X-Forwarded-For", "X-Forwarded-Host",
                           "X-Forwarded-Proto", "X-Forwarded-Port", "X-Forwarded-Anything"):
                refused = recorded(local, "POST", "/uploads?name=forwarded.jpg", content=body,
                                   headers={**upload_headers, header: "127.0.0.1",
                                            "X-Tablet-Wall-Operator": CREDENTIAL})
                assert refused.status_code == 403, refused.text

            device_id = "00000000-0000-4000-8000-000000000001"
            read_paths = ["/uploads", "/media", "/api/v3/images", "/assets", "/devices",
                          "/controller/", "/controller/physical.html", "/controller/physical.js",
                          "/ws/controller", "/diagnostics", "/healthz", "/operator-config",
                          "/api/v3/config", "/api/v3/readiness", "/api/v3/join-qr",
                          f"/api/v3/devices/{device_id}/impact", "/wall", "/scene", "/docs"]
            mutations = [("POST", "/uploads"), ("POST", "/media/verify"),
                         ("PUT", "/wall"), ("PUT", "/scene"), ("POST", "/wall/pack"),
                         ("POST", "/wall/auto"), ("PUT", "/api/v3/scene"),
                         ("PUT", "/api/v3/layout"), ("PUT", "/api/v3/logical-layout"),
                         ("POST", "/api/v3/layout/clear"), ("POST", "/api/v3/grid"),
                         ("POST", "/api/v3/grid/preview"), ("PUT", "/api/v3/config"),
                         ("PATCH", "/api/v3/config"), ("DELETE", "/api/v3/config"),
                         ("DELETE", f"/devices/{device_id}"),
                         ("POST", f"/devices/{device_id}/rebind"),
                         ("POST", f"/api/v3/devices/{device_id}/remove"),
                         ("DELETE", f"/api/v3/devices/{device_id}"),
                         ("POST", f"/api/v3/devices/{device_id}/rebind/preview"),
                         ("POST", f"/api/v3/devices/{device_id}/rebind"),
                         ("PUT", "/api/v3/scenes/denied"),
                         ("PUT", "/api/v3/logical-layouts/denied")]
            for forged in ({}, {"Origin": operator, "X-Tablet-Wall-Operator": CREDENTIAL,
                                "Forwarded": "for=127.0.0.1;proto=http",
                                "X-Forwarded-For": "127.0.0.1",
                                "X-Forwarded-Host": f"127.0.0.1:{app_port}",
                                "X-Forwarded-Proto": "http"}):
                for method, path in [(method, path) for path in read_paths
                                     for method in ("GET", "HEAD")] + mutations:
                    if path == "/uploads" and method == "POST":
                        kwargs = {"content": body, "headers": {**upload_headers, **forged}}
                    else:
                        kwargs = {"headers": {"Origin": operator, "If-Match": before["etag"], **forged}}
                        if method not in ("GET", "HEAD"):
                            kwargs["json"] = {"confirm": True, "width": 900, "height": 700}
                    refused = recorded(public, method, path, **kwargs)
                    assert refused.status_code == 403, (method, path, refused.text)
                refused = recorded(public, "GET", "/ws/controller?protocol=3", headers={
                    **forged, "Origin": operator, "Connection": "Upgrade", "Upgrade": "websocket",
                    "Sec-WebSocket-Version": "13", "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="})
                assert refused.status_code == 403

            final = stored_state(data)
            manifest["state_after_denials"] = final
            assert final == baseline
            assert recorded(local, "GET", "/api/v3/config").json()["etag"] == before["etag"]
            assert len(recorded(local, "GET", "/media").json()["assets"]) == 1
            for path in ("/client/", "/client/client.js", "/client/client.css", "/client/view.js"):
                assert recorded(public, "GET", path).status_code == 200
            redirect = recorded(public, "GET", "/client")
            assert redirect.status_code == 308 and redirect.headers["location"] == "/client/"
            published = recorded(public, "GET", descriptor["url"])
            assert published.status_code == 200
            assert "immutable" in published.headers["cache-control"]
            assert "sha256:" + hashlib.sha256(published.content).hexdigest() == descriptor["id"]
            assert published.content == recorded(local, "GET", descriptor["url"]).content
            head = recorded(public, "HEAD", descriptor["url"])
            assert head.status_code == 200 and head.content == b""
            assert int(head.headers["content-length"]) == len(published.content)
            registered = recorded(public, "POST", "/devices/register", json={
                "device_id": device_id, "width": 1024, "height": 768, "device_type": "test"},
                headers={"Origin": tablet, "X-Tablet-Wall-Operator": CREDENTIAL})
            assert registered.status_code == 200, registered.text
            with connect(f"ws://127.0.0.1:{tablet_port}/ws/device?device_id={device_id}&protocol=3",
                         origin=tablet, open_timeout=5, close_timeout=2) as ws:
                welcome = json.loads(ws.recv(timeout=5))
                assert welcome["type"] == "welcome" and welcome["device_id"] == device_id
                assert welcome["protocol"] == 3
                manifest["device_websocket"] = {"status": 101, "welcome": welcome}
            manifest["passed"] = True
    finally:
        manifest["cleanup"] = {}
        for name, port in (("backend", app_port), ("tablet", tablet_port)):
            with socket.socket() as probe:
                manifest["cleanup"][f"{name}_port_closed"] = probe.connect_ex(("127.0.0.1", port)) != 0
        manifest["process_exit_codes"] = {
            name: process.poll() for name, process in zip(("backend", "caddy"), processes)
        }
        (tmp_path / "ingress-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    assert all(manifest["cleanup"].values())
