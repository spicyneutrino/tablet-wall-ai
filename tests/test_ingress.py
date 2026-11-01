"""Real two-origin Caddy ingress evidence for R1 admission (not a text check).

Starts the actual app on a loopback port and Caddy in front of it with two
listeners: the tablet allowlist (which must never reach /uploads or /media and
must strip the internal credential) and the authenticated operator listener
(which must overwrite any client credential and reach the backend in proxy
mode). Skipped only when Caddy is not installed.
"""

import os
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from video_fixtures import HAVE_FFMPEG, _ensure as build_fixture

CWD = Path(__file__).resolve().parents[1]
CADDY = shutil.which("caddy")
CREDENTIAL = "test-ingress-credential-0123456789"
PASSWORD = "operator-test-password"


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

