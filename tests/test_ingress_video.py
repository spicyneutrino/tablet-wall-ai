"""Real two-listener Caddy evidence for video bytes (not a text check).

The tablet listener admits GET and HEAD on the exact asset route, forwards
ranges and validators, and answers 431 for an oversized Range. Every other
path, method, and a forged operator credential is refused. The authenticated
operator listener uploads the clip and overwrites a client-supplied internal
credential.

Skipped only when Caddy or ffmpeg is missing; the skip reason names the
missing prerequisite instead of faking the evidence.
"""

import base64
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from video_fixtures import _ensure, needs_ffmpeg

CWD = Path(__file__).resolve().parents[1]
CADDY = shutil.which("caddy")
CREDENTIAL = "test-ingress-video-credential-0123456789"
PASSWORD = "operator-test-password"
DEVICE_ID = "0f8fad5b-d9cb-469f-a165-70867728950e"


def free_port() -> int:
    while True:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        if port != 8000:
            return port


def wait_for(url: str, timeout: float = 15.0,
             auth: tuple[str, str] | None = None, status: int = 200) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=.5, auth=auth).status_code == status:
                return
        except httpx.HTTPError:
            pass
        time.sleep(.1)
    raise RuntimeError(f"{url} did not become ready with HTTP {status}")


def stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@pytest.mark.skipif(
    CADDY is None,
    reason="Caddy is not installed; real ingress evidence is SKIPPED, not faked",
)
@needs_ffmpeg
def test_tablet_listener_serves_video_ranges_and_refuses_the_operator_surface(tmp_path):
    app_port, tablet_port, operator_port = free_port(), free_port(), free_port()
    data = tmp_path / "data"
    for name in ("assets", "media"):
        (data / name).mkdir(parents=True)
    operator_origin = f"http://127.0.0.1:{operator_port}"
    tablet_origin = f"http://127.0.0.1:{tablet_port}"

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
\t@asset {{
\t\tmethod GET HEAD
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
\tbasic_auth {{
\t\toperator {password_hash}
\t}}
\treverse_proxy 127.0.0.1:{app_port} {{
\t\theader_up X-Tablet-Wall-Operator "{CREDENTIAL}"
\t\theader_up -Authorization
\t\theader_up -Cookie
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
        wait_for(f"http://127.0.0.1:{app_port}/wall", status=200)
        caddy = subprocess.Popen(
            [CADDY, "run", "--config", str(config), "--adapter", "caddyfile"],
            cwd=tmp_path, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        auth = ("operator", PASSWORD)
        wait_for(f"{operator_origin}/media", auth=auth, status=200)

        clip = _ensure("baseline.mp4", tmp_path).read_bytes()
        uploaded = httpx.post(
            f"{operator_origin}/uploads?name=clip.mp4", content=clip, auth=auth,
            timeout=60,
            headers={
                "Origin": operator_origin,
                "Content-Type": "video/mp4",
                "X-Tablet-Wall-Operator": "forged-by-the-client",
            },
        )
        assert uploaded.status_code == 201, uploaded.text
        video = uploaded.json()["asset"]
        assert video["kind"] == "video" and video["mime"] == "video/mp4"
        digest = video["id"].split(":", 1)[1]
        assert hashlib.sha256(clip).hexdigest() != digest  # remuxed, not the source

        tablet = f"{tablet_origin}{video['url']}"
        full = httpx.get(tablet, timeout=30)
        assert full.status_code == 200
        assert len(full.content) == video["bytes"]
        assert hashlib.sha256(full.content).hexdigest() == digest
        etag = full.headers["etag"]

        head = httpx.head(tablet, timeout=30)
        assert head.status_code == 200 and head.content == b""
        assert head.headers["content-length"] == str(video["bytes"])

        first = httpx.get(tablet, headers={"Range": "bytes=0-99"}, timeout=30)
        assert first.status_code == 206
        assert first.headers["content-range"] == f"bytes 0-99/{video['bytes']}"
        assert first.content == full.content[:100]

        tail = httpx.get(tablet, headers={"Range": "bytes=-64"}, timeout=30)
        assert tail.status_code == 206 and tail.content == full.content[-64:]

        open_ended = httpx.get(
            tablet, headers={"Range": f"bytes={video['bytes'] - 10}-"}, timeout=30
        )
        assert open_ended.status_code == 206 and len(open_ended.content) == 10

        ranged_head = httpx.head(tablet, headers={"Range": "bytes=0-9"}, timeout=30)
        assert ranged_head.status_code == 206
        assert ranged_head.headers["content-range"] == f"bytes 0-9/{video['bytes']}"

        past = httpx.get(
            tablet, headers={"Range": f"bytes={video['bytes']}-"}, timeout=30
        )
        assert past.status_code == 416
        assert past.headers["content-range"] == f"bytes */{video['bytes']}"

        conditional = httpx.get(tablet, headers={"If-None-Match": etag}, timeout=30)
        assert conditional.status_code == 304
        assert conditional.headers["etag"] == etag

        huge = "bytes=" + ",".join(f"{index}-{index}" for index in range(0, 120))
        assert len(huge) > 256
        oversized = httpx.get(tablet, headers={"Range": huge}, timeout=30)
        assert oversized.status_code == 431
        assert oversized.text == "Range header too large"

        # The tablet listener never reaches the operator surface, even with the
        # internal credential or an operator Authorization header attached.
        for path, method in (
            ("/media", "GET"),
            ("/diagnostics", "GET"),
            ("/assets", "GET"),
            ("/rebind", "POST"),
            (f"/devices/{DEVICE_ID}/rebind", "POST"),
        ):
            response = httpx.request(
                method, f"{tablet_origin}{path}", timeout=10,
                headers={"X-Tablet-Wall-Operator": CREDENTIAL},
            )
            assert response.status_code == 403, (path, response.status_code)

        forged_upload = httpx.post(
            f"{tablet_origin}/uploads?name=forged.mp4", content=clip, timeout=30,
            headers={
                "Origin": operator_origin,
                "Content-Type": "video/mp4",
                "X-Tablet-Wall-Operator": CREDENTIAL,
            },
        )
        assert forged_upload.status_code == 403

        basic = base64.b64encode(f"operator:{PASSWORD}".encode()).decode()
        authorized = httpx.get(
            f"{tablet_origin}/media", timeout=10,
            headers={
                "Authorization": f"Basic {basic}",
                "X-Tablet-Wall-Operator": CREDENTIAL,
            },
        )
        assert authorized.status_code == 403

        # The operator listener requires basic auth and injects exactly one
        # credential; the client's forged value never survives the hop.
        assert httpx.get(f"{operator_origin}/media", timeout=10).status_code == 401
        library = httpx.get(f"{operator_origin}/media", auth=auth, timeout=10)
        assert library.status_code == 200, library.text
        assert [entry["id"] for entry in library.json()["assets"]] == [video["id"]]
    finally:
        stop(caddy)
        stop(app)
