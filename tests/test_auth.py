"""Authentication applies before every HTTP route, static mount, and socket."""

import asyncio
import hashlib

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from starlette.testclient import WebSocketDenialResponse
from video_fixtures import fabricate_video

import main
from tabletwall import auth

TOKEN = "test-only-shared-token-with-at-least-32-bytes"
ORIGIN = "http://testserver"
BEARER = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def secured(client, monkeypatch):
    monkeypatch.setenv(auth.TOKEN_ENV, TOKEN)
    return client


def login(client, **kwargs):
    return client.post(
        "/auth/login", data={"token": TOKEN, **kwargs},
        headers={"Origin": ORIGIN}, follow_redirects=False,
    )


@pytest.mark.parametrize("path", [
    "/wall", "/docs", "/openapi.json", "/operator-config", "/assets",
    "/client/", "/client/client.js", "/controller/", "/nonexistent",
])
def test_all_http_routes_require_authentication(secured, path):
    response = secured.get(path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["cache-control"] == "no-store"


def test_unauthorized_writes_cannot_change_state(secured, device_payload):
    before = main.wall.copy()
    assert secured.put("/wall", json={"width": 4001}).status_code == 401
    assert secured.post("/devices/register", json=device_payload).status_code == 401
    assert main.wall == before
    assert main.devices == {}


@pytest.mark.parametrize("credential", ["", "wrong", TOKEN + "suffix"])
def test_wrong_bearer_is_refused(secured, credential):
    response = secured.get("/wall", headers={"Authorization": f"Bearer {credential}"})
    assert response.status_code == 401


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "bEaReR"])
def test_bearer_scheme_is_case_insensitive(secured, scheme):
    assert secured.get("/wall", headers={"Authorization": f"{scheme} {TOKEN}"}).status_code == 200


def test_duplicate_authorization_is_refused(secured):
    assert secured.get("/wall", headers=[
        ("Authorization", f"Bearer {TOKEN}"), ("Authorization", f"Bearer {TOKEN}"),
    ]).status_code == 401


def test_bearer_can_read_static_files_and_write(secured):
    assert secured.get("/controller/", headers=BEARER).status_code == 200
    assert secured.get("/client/client.js", headers=BEARER).status_code == 200
    assert secured.put("/wall", json={"width": 4001}, headers=BEARER).status_code == 200
    assert secured.get("/wall", headers=BEARER).json()["width"] == 4001


@pytest.mark.parametrize("credential", ["bearer", "cookie"])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_protected_image_bytes_cannot_enter_shared_caches(secured, asset_dir, credential, method):
    image = asset_dir / "private.png"
    Image.new("RGB", (8, 8), "red").save(image)
    asset_id = "sha256:" + hashlib.sha256(image.read_bytes()).hexdigest()
    if credential == "cookie":
        login(secured)
    headers = BEARER if credential == "bearer" else {}
    response = secured.request(method, f"/assets/{asset_id}", headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.content == (image.read_bytes() if method == "GET" else b"")


@pytest.mark.parametrize("credential", ["bearer", "cookie"])
@pytest.mark.parametrize(("method", "extra_headers", "status"), [
    ("GET", {}, 200), ("HEAD", {}, 200),
    ("GET", {"Range": "bytes=0-15"}, 206), ("HEAD", {"Range": "bytes=0-15"}, 206),
])
def test_protected_video_get_head_and_ranges_cannot_enter_shared_caches(secured, credential, method, extra_headers, status):
    descriptor = fabricate_video(1024)
    if credential == "cookie":
        login(secured)
    headers = {**(BEARER if credential == "bearer" else {}), **extra_headers}
    response = secured.request(method, descriptor["url"], headers=headers)
    assert response.status_code == status
    assert response.headers["cache-control"] == "private, no-store"
    assert len(response.content) == (0 if method == "HEAD" else 16 if status == 206 else 1024)
    secured.cookies.clear()
    assert secured.get(descriptor["url"], headers=extra_headers).status_code == 401


def test_html_navigation_redirects_to_login_without_secret(secured):
    response = secured.get("/client/?token=do-not-copy", headers={"Accept": "text/html"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login?next=%2Fclient%2F"
    page = secured.get(response.headers["location"])
    assert page.status_code == 200
    assert 'type="password"' in page.text
    assert "do-not-copy" not in page.text
    assert TOKEN not in page.text
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert page.headers["referrer-policy"] == "same-origin"


def test_browser_login_sets_cookie_and_allows_normal_browser_routes(secured, device_payload):
    response = login(secured, next="/client/")
    assert response.status_code == 303
    assert response.headers["location"] == "/client/"
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/" in cookie
    assert f"Max-Age={auth.SESSION_SECONDS}" in cookie
    assert TOKEN not in cookie
    assert secured.get("/client/").status_code == 200
    assert secured.post("/devices/register", json=device_payload, headers={"Origin": ORIGIN}).status_code == 200
    with secured.websocket_connect("/ws/device?device_id=" + device_payload["device_id"], headers={"Origin": ORIGIN}) as socket:
        assert socket.receive_json()["type"] == "welcome"
    with secured.websocket_connect("/ws/controller", headers={"Origin": ORIGIN}) as socket:
        assert socket.receive_json()["type"] == "snapshot"


def test_https_cookie_is_secure(monkeypatch):
    monkeypatch.setenv(auth.TOKEN_ENV, TOKEN)
    with TestClient(main.app, base_url="https://testserver") as client:
        response = client.post("/auth/login", data={"token": TOKEN}, headers={"Origin": "https://testserver"}, follow_redirects=False)
        assert "Secure" in response.headers["set-cookie"]
        assert client.get("/wall").status_code == 200


@pytest.mark.parametrize("origin", [None, "https://attacker.invalid", "null", "http://testserver:80"])
def test_cookie_writes_require_exact_same_origin(secured, origin):
    assert login(secured).status_code == 303
    before = secured.get("/wall").json()
    headers = {} if origin is None else {"Origin": origin}
    assert secured.put("/wall", json={"width": 4001}, headers=headers).status_code == 403
    assert secured.get("/wall").json() == before


@pytest.mark.parametrize("path", ["/ws/device", "/ws/controller", "/ws/unknown"])
def test_sockets_require_auth_before_upgrade(secured, path):
    with pytest.raises(WebSocketDenialResponse) as denied:
        with secured.websocket_connect(path):
            pass
    assert denied.value.status_code == 401
    assert main.device_sockets == {}
    assert main.controller_sockets == set()


def test_socket_denial_without_http_extension(monkeypatch):
    monkeypatch.setenv(auth.TOKEN_ENV, TOKEN)
    messages = []

    async def downstream(scope, receive, send):
        pytest.fail("An unauthorized socket reached the application")

    async def receive():
        return {"type": "websocket.connect"}

    async def send(message):
        messages.append(message)

    asyncio.run(auth.AuthMiddleware(downstream)(
        {"type": "websocket", "path": "/ws/controller", "headers": []}, receive, send,
    ))
    assert messages == [{"type": "websocket.close", "code": 1008, "reason": ""}]


@pytest.mark.parametrize("origin", [None, "https://attacker.invalid"])
@pytest.mark.parametrize("path", ["/ws/device", "/ws/controller"])
def test_cookie_socket_requires_same_origin(secured, origin, path):
    login(secured)
    headers = {} if origin is None else {"Origin": origin}
    with pytest.raises(WebSocketDenialResponse) as denied:
        with secured.websocket_connect(path, headers=headers):
            pass
    assert denied.value.status_code == 403


def test_bearer_socket_and_existing_operator_guard(secured, monkeypatch):
    with secured.websocket_connect("/ws/controller", headers=BEARER) as socket:
        assert socket.receive_json()["type"] == "snapshot"
    monkeypatch.setenv(main.OPERATOR_ORIGIN_ENV, "https://operator.wall.test")
    assert secured.put("/wall", json={"width": 4001}, headers=BEARER).status_code == 403
    with pytest.raises(WebSocketDenialResponse) as denied:
        with secured.websocket_connect("/ws/controller", headers=BEARER):
            pass
    assert denied.value.status_code == 403
    headers = {**BEARER, "Origin": "https://operator.wall.test"}
    assert secured.put("/wall", json={"width": 4001}, headers=headers).status_code == 200
    with secured.websocket_connect("/ws/controller", headers=headers) as socket:
        assert socket.receive_json()["type"] == "snapshot"


def test_browser_cookie_does_not_bypass_operator_guard(secured, monkeypatch):
    login(secured)
    monkeypatch.setenv(main.OPERATOR_ORIGIN_ENV, "https://operator.wall.test")
    assert secured.put("/wall", json={"width": 4001}, headers={"Origin": ORIGIN}).status_code == 403


@pytest.mark.parametrize("origin", [None, "https://attacker.invalid", "null"])
def test_login_requires_same_origin(secured, origin):
    headers = {} if origin is None else {"Origin": origin}
    response = secured.post("/auth/login", data={"token": TOKEN}, headers=headers)
    assert response.status_code == 403
    assert auth.COOKIE_NAME not in secured.cookies


def test_duplicate_origins_are_refused(secured):
    headers = [("Origin", ORIGIN), ("Origin", ORIGIN)]
    assert secured.post("/auth/login", data={"token": TOKEN}, headers=headers).status_code == 403
    login(secured)
    assert secured.put("/wall", json={"width": 4001}, headers=headers).status_code == 403


def test_failed_login_never_reflects_token(secured):
    response = secured.post("/auth/login", data={"token": "wrong-sensitive-value"}, headers={"Origin": ORIGIN})
    assert response.status_code == 401
    assert "wrong-sensitive-value" not in response.text
    assert auth.COOKIE_NAME not in secured.cookies


@pytest.mark.parametrize("destination", ["//attacker.invalid", "https://attacker.invalid", "/\\attacker.invalid", "/\r\nLocation: https://attacker.invalid"])
def test_login_redirect_stays_local(secured, destination):
    assert login(secured, next=destination).headers["location"] == "/controller/"


def test_login_rejects_invalid_and_oversized_forms(secured):
    assert secured.post("/auth/login", json={"token": TOKEN}, headers={"Origin": ORIGIN}).status_code == 415
    headers = {"Origin": ORIGIN, "Content-Type": "application/x-www-form-urlencoded"}
    assert secured.post("/auth/login", content=b"\xff", headers=headers).status_code == 400
    assert secured.post("/auth/login", content=b"x" * (auth.LOGIN_BODY_LIMIT + 1), headers=headers).status_code == 413


def test_tampered_expired_and_rotated_sessions_are_refused(secured, monkeypatch):
    login(secured)
    session = secured.cookies[auth.COOKIE_NAME]
    secured.cookies.set(auth.COOKIE_NAME, session + "tampered")
    assert secured.get("/wall").status_code == 401
    secured.cookies.clear()
    secured.cookies.set(auth.COOKIE_NAME, session)
    with monkeypatch.context() as clock:
        clock.setattr(auth.time, "time", lambda: 10**12)
        assert secured.get("/wall").status_code == 401
    monkeypatch.setenv(auth.TOKEN_ENV, TOKEN + "rotated")
    assert secured.get("/wall").status_code == 401


def test_logout_clears_browser_session(secured):
    login(secured)
    assert secured.post("/auth/logout").status_code == 403
    response = secured.post("/auth/logout", headers={"Origin": ORIGIN}, follow_redirects=False)
    assert response.status_code == 303
    assert secured.get("/wall").status_code == 401


def test_short_configured_secret_fails_closed(client, monkeypatch):
    monkeypatch.setenv(auth.TOKEN_ENV, "short")
    assert client.get("/wall").status_code == 503
    assert client.get("/auth/login").status_code == 503


def test_empty_auth_setting_preserves_default_behavior(client, monkeypatch):
    monkeypatch.setenv(auth.TOKEN_ENV, "")
    assert client.get("/wall").status_code == 200
    assert client.get("/client/").status_code == 200
    with client.websocket_connect("/ws/controller") as socket:
        assert socket.receive_json()["type"] == "snapshot"
