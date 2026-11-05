"""Optional shared-secret authentication for HTTP and WebSocket requests."""

import base64
import hashlib
import hmac
import html
import os
import secrets
import time
from urllib.parse import parse_qs, quote

from starlette.datastructures import MutableHeaders
from starlette.requests import HTTPConnection, Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from starlette.websockets import WebSocket

TOKEN_ENV = "TABLET_WALL_AUTH_TOKEN"
COOKIE_NAME = "tablet_wall_session"
SESSION_SECONDS = 12 * 60 * 60
LOGIN_BODY_LIMIT = 8192
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
LOGIN_STYLE = """
* { box-sizing: border-box; }
body { margin: 0; padding: 64px 32px; color: #2d2822; background: #efece4;
    font: 16px/1.5 -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; }
main { width: 100%; max-width: 28rem; margin: 0 auto; }
h1 { margin: 0 0 32px; font-size: 28px; line-height: 1.25; letter-spacing: -.025em; }
label { display: block; font-weight: 600; }
input[type=password] { display: block; width: 100%; min-height: 48px; margin: 8px 0 24px;
    padding: 10px 12px; border: 1px solid #67645d; border-radius: 6px;
    color: #2d2822; background: #faf8f2; font: inherit; }
button { min-height: 48px; padding: 10px 24px; border: 0; border-radius: 6px;
    background: #2d2822; color: #efece4; font: inherit; font-weight: 600; cursor: pointer; }
button:hover { background: #8f4014; }
input:focus-visible, button:focus-visible { outline: 2px solid #8f4014; outline-offset: 3px; }
[role=alert] { padding: 12px; margin: 0 0 24px; border: 1px solid currentColor;
    border-radius: 6px; background: #faf8f2; color: #a12a24; }
@media (max-width: 480px) { body { padding: 40px 16px; } button { width: 100%; } }
"""


def _matches(candidate: str, expected: str) -> bool:
    return hmac.compare_digest(
        hashlib.sha256(candidate.encode()).digest(),
        hashlib.sha256(expected.encode()).digest(),
    )


def _same_origin(connection: HTTPConnection) -> bool:
    origins = connection.headers.getlist("origin")
    url = connection.url
    scheme = {"ws": "http", "wss": "https"}.get(url.scheme, url.scheme)
    return origins == [f"{scheme}://{url.netloc}"]


def _session(secret: str) -> str:
    payload = f"{int(time.time()) + SESSION_SECONDS}.{secrets.token_hex(16)}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def _valid_session(value: str, secret: str) -> bool:
    parts = value.split(".")
    if len(parts) != 3:
        return False
    expires, nonce, signature = parts
    payload = f"{expires}.{nonce}"
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not _matches(signature, expected):
        return False
    try:
        return int(expires) > time.time()
    except ValueError:
        return False


def _destination(value: str) -> str:
    if not value.startswith("/") or value.startswith("//"):
        return "/controller/"
    if "\\" in value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return "/controller/"
    return value


def _login_page(destination: str, *, failed: bool = False) -> HTMLResponse:
    message = "<p role=\"alert\">The access token was not accepted.</p>" if failed else ""
    response = HTMLResponse(
        "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>Tablet wall sign in</title><style>{LOGIN_STYLE}</style><body><main>"
        "<h1>Sign in to Tablet wall</h1>"
        f"{message}<form method=\"post\" action=\"/auth/login\">"
        "<label>Access token <input name=\"token\" type=\"password\" required "
        "autocomplete=\"current-password\"></label>"
        f"<input type=\"hidden\" name=\"next\" value=\"{html.escape(destination, quote=True)}\">"
        "<button type=\"submit\">Sign in</button></form></main></body></html>",
        status_code=401 if failed else 200,
    )
    style_hash = base64.b64encode(hashlib.sha256(LOGIN_STYLE.encode()).digest()).decode()
    response.headers["Content-Security-Policy"] = (
        f"default-src 'none'; style-src 'sha256-{style_hash}'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    )
    return response


class AuthMiddleware:
    """Protect all routes and mounts, with a public credential-entry form."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        secret = os.environ.get(TOKEN_ENV, "")
        if scope["type"] not in {"http", "websocket"} or not secret:
            await self.app(scope, receive, send)
            return
        connection = HTTPConnection(scope)
        response: Response
        if len(secret.encode()) < 32:
            response = JSONResponse(
                {"detail": f"{TOKEN_ENV} must contain at least 32 bytes"}, status_code=503
            )
        elif scope["type"] == "http" and scope["path"] == "/auth/login":
            response = await self._login(Request(scope, receive), secret)
        else:
            authorization = connection.headers.getlist("authorization")
            bearer = (
                len(authorization) == 1
                and authorization[0][:7].lower() == "bearer "
                and _matches(authorization[0][7:], secret)
            )
            cookie = _valid_session(connection.cookies.get(COOKIE_NAME, ""), secret)
            if bearer or cookie:
                requires_origin = scope["type"] == "websocket" or scope["method"] not in SAFE_METHODS
                if not bearer and requires_origin and not _same_origin(connection):
                    response = JSONResponse({"detail": "A same-origin Origin header is required"}, status_code=403)
                elif scope["type"] == "http" and scope["path"] == "/auth/logout" and scope["method"] == "POST":
                    response = RedirectResponse("/auth/login", status_code=303)
                    response.delete_cookie(COOKIE_NAME, path="/")
                else:
                    async def private_send(message: Message) -> None:
                        if message["type"] == "http.response.start":
                            headers = MutableHeaders(raw=message.setdefault("headers", []))
                            headers["Cache-Control"] = "private, no-store"
                        await send(message)

                    await self.app(scope, receive, private_send)
                    return
            elif scope["type"] == "http" and scope["method"] in {"GET", "HEAD"} and "text/html" in connection.headers.get("accept", ""):
                destination = quote(_destination(scope["path"]), safe="")
                response = RedirectResponse(f"/auth/login?next={destination}", status_code=303)
            else:
                response = JSONResponse(
                    {"detail": "Authentication required"}, status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
        response.headers["Cache-Control"] = "no-store"
        # no-referrer makes browsers send Origin: null on login form POSTs.
        response.headers["Referrer-Policy"] = "same-origin"
        if scope["type"] == "websocket":
            websocket = WebSocket(scope, receive, send)
            if "websocket.http.response" in scope.get("extensions", {}):
                await websocket.send_denial_response(response)
            else:
                await websocket.close(code=1008)
        else:
            await response(scope, receive, send)

    async def _login(self, request: Request, secret: str) -> Response:
        if request.method == "GET":
            return _login_page(_destination(request.query_params.get("next", "/controller/")))
        if request.method != "POST":
            return Response(status_code=405, headers={"Allow": "GET, POST"})
        if not _same_origin(request):
            return JSONResponse({"detail": "A same-origin Origin header is required"}, status_code=403)
        if request.headers.get("content-type", "").split(";", 1)[0] != "application/x-www-form-urlencoded":
            return JSONResponse({"detail": "Use a URL-encoded login form"}, status_code=415)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > LOGIN_BODY_LIMIT:
                return JSONResponse({"detail": "Login form is too large"}, status_code=413)
        try:
            fields = parse_qs(body.decode("utf-8"), max_num_fields=4)
        except (ValueError, UnicodeDecodeError):
            return JSONResponse({"detail": "Invalid login form"}, status_code=400)
        destination = _destination(fields.get("next", ["/controller/"])[0])
        tokens = fields.get("token", [])
        if len(tokens) != 1 or not _matches(tokens[0], secret):
            return _login_page(destination, failed=True)
        response = RedirectResponse(destination, status_code=303)
        response.set_cookie(
            COOKIE_NAME, _session(secret), max_age=SESSION_SECONDS, httponly=True,
            secure=request.url.scheme == "https", samesite="strict", path="/",
        )
        return response
