"""Baseline headers on real pages, without changing what the pages may load.

The app under test mounts the actual client/controller files and the real
``AuthMiddleware`` sign-in page. Enforcement of the policy is a browser
concern; these cases pin the header values, the allowances the existing pages
need, and that a route which already chose a policy keeps it.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from starlette.websockets import WebSocket

from tabletwall.auth import AuthMiddleware
from tabletwall.security_headers import (
    CONTENT_SECURITY_POLICY,
    SecurityHeadersMiddleware,
)

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def directive(policy: str, name: str) -> str:
    for part in policy.split(";"):
        part = part.strip()
        if part.split(" ", 1)[0] == name:
            return part
    raise AssertionError(f"{name} missing from {policy!r}")


def page_app() -> FastAPI:
    application = FastAPI()
    application.add_middleware(SecurityHeadersMiddleware)
    application.mount(
        "/client",
        StaticFiles(directory=FRONTEND / "client", html=True),
        name="client",
    )
    application.mount(
        "/controller",
        StaticFiles(directory=FRONTEND / "controller", html=True),
        name="controller",
    )
    application.get("/json")(lambda: {"ok": True})

    @application.get("/own-policy")
    def own_policy():
        return HTMLResponse(
            "<!doctype html><title>pinned</title>",
            headers={"Content-Security-Policy": "default-src 'none'"},
        )

    @application.websocket("/ws/echo")
    async def echo(websocket: WebSocket):
        await websocket.accept()
        await websocket.send_text("up")
        await websocket.close()

    return application


def test_headers_are_present_on_real_client_and_controller_pages():
    with TestClient(page_app()) as client:
        for path in ("/client/", "/controller/", "/client/client.js", "/json"):
            response = client.get(path)
            assert response.status_code == 200, path
            assert response.headers["X-Content-Type-Options"] == "nosniff", path
            assert response.headers["X-Frame-Options"] == "DENY", path
            assert response.headers["Referrer-Policy"] == "same-origin", path
            assert response.headers["Content-Security-Policy"] == CONTENT_SECURITY_POLICY


def test_policy_allows_local_scripts_styles_blobs_and_same_origin_sockets():
    policy = CONTENT_SECURITY_POLICY
    assert directive(policy, "default-src") == "default-src 'self'"
    assert directive(policy, "script-src") == "script-src 'self'"
    assert "'unsafe-eval'" not in policy
    assert "'unsafe-inline'" not in directive(policy, "script-src")
    assert directive(policy, "style-src") == "style-src 'self' 'unsafe-inline'"
    assert "blob:" in directive(policy, "img-src")
    assert "blob:" in directive(policy, "media-src")
    assert directive(policy, "connect-src") == "connect-src 'self'"
    assert directive(policy, "object-src") == "object-src 'none'"
    assert directive(policy, "frame-ancestors") == "frame-ancestors 'none'"
    assert directive(policy, "base-uri") == "base-uri 'none'"


def test_policy_names_no_external_origin():
    for scheme in ("http://", "https://", "//"):
        assert scheme not in CONTENT_SECURITY_POLICY


def test_a_route_that_already_chose_a_policy_keeps_it():
    with TestClient(page_app()) as client:
        response = client.get("/own-policy")
    assert response.headers["Content-Security-Policy"] == "default-src 'none'"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_login_page_keeps_its_hash_pinned_policy_and_gains_baseline_headers(
    monkeypatch,
):
    monkeypatch.setenv("TABLET_WALL_AUTH_TOKEN", "x" * 32)
    application = FastAPI()

    @application.get("/")
    def root():
        return {"ok": True}

    application.add_middleware(AuthMiddleware)
    application.add_middleware(SecurityHeadersMiddleware)
    with TestClient(application) as client:
        response = client.get("/auth/login")
    assert response.status_code == 200
    assert "Sign in to Tablet wall" in response.text
    policy = response.headers["Content-Security-Policy"]
    assert policy.startswith("default-src 'none'; style-src 'sha256-")
    assert policy != CONTENT_SECURITY_POLICY
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "same-origin"


def test_websocket_scope_passes_through_untouched():
    with TestClient(page_app()) as client:
        with client.websocket_connect("/ws/echo") as socket:
            assert socket.receive_text() == "up"


def test_direct_middleware_call_does_not_touch_a_websocket_scope():
    seen = []

    async def inner(scope, receive, send):
        seen.append(scope["type"])
        await send({"type": "websocket.accept"})

    async def receive():
        return {"type": "websocket.receive"}

    async def send(message):
        seen.append(("sent", message["type"]))

    import anyio

    anyio.run(
        SecurityHeadersMiddleware(inner),
        {"type": "websocket", "path": "/ws/device"},
        receive,
        send,
    )
    assert seen == ["websocket", ("sent", "websocket.accept")]
