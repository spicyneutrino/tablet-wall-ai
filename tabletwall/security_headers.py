"""Baseline browser security headers for every HTTP response.

One ASGI wrapper, applied outside application authentication so the sign-in
page gets the same protections as the controller and tablet pages. It is a
plain ``send`` interceptor: WebSocket scopes pass through untouched, and a
response that already carries a policy (the sign-in page's hash-pinned CSP)
keeps it.

The policy is written for the pages this project actually serves:

* ``script-src 'self'``: every page script is a same-origin classic script.
  There is no inline script, no bundled third-party script, and no need for
  ``'unsafe-eval'`` or ``'unsafe-inline'``.
* ``style-src 'self' 'unsafe-inline'``: ``ruler.js`` builds the measuring
  overlay with inline ``style`` attributes, and the controller positions
  elements through the CSSOM. Inline *styles* are allowed; inline scripts are
  not.
* ``img-src 'self' blob:``: the tablet decodes an already-fetched image from a
  ``Blob`` object URL so a scene change can cancel a decode.
* ``media-src 'self' blob:``: the experimental video path serves bytes from
  this origin and may play a staged blob.
* ``connect-src 'self'``: same-origin ``fetch`` and the same-origin
  ``/ws/device`` and ``/ws/controller`` WebSockets. CSP3 treats ``'self'`` as
  matching ``ws:``/``wss:`` on the page's own host and port.
* ``frame-ancestors 'none'`` plus ``object-src 'none'``: no embedding and no
  plugin content. ``base-uri`` and ``form-action`` stay on this origin.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "base-uri 'none'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' blob:; "
    "media-src 'self' blob:; "
    "font-src 'self'; "
    "connect-src 'self'"
)

STATIC_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}


class ConfiguredHostMiddleware:
    """Fence configured deployment hosts without changing unconfigured development."""

    def __init__(self, app: ASGIApp, allowed_hosts: Callable[[], set[str] | None]):
        self.app = app
        self.allowed_hosts = allowed_hosts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        allowed = self.allowed_hosts() if scope["type"] in ("http", "websocket") else None
        if allowed is not None:
            hosts = Headers(scope=scope).getlist("host")
            valid = False
            if len(hosts) == 1:
                raw = hosts[0]
                try:
                    parsed = urlsplit("//" + raw)
                    valid = (
                        raw == raw.strip() and not any(ord(char) <= 32 for char in raw)
                        and parsed.hostname is not None
                        and parsed.hostname.lower().rstrip(".") in allowed
                        and parsed.username is None and parsed.password is None
                        and not parsed.path and not parsed.query and not parsed.fragment
                        and (parsed.port is None or 0 < parsed.port <= 65535)
                    )
                except ValueError:
                    pass
            if not valid:
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    await JSONResponse(status_code=400, content={"detail": "Host is not admitted for this deployment"},
                                       headers={"Cache-Control": "no-store"})(scope, receive, send)
                return
        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    """Add the baseline headers unless a route already chose its own value."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw = message.setdefault("headers", [])
                present = {key.lower() for key, _value in raw}
                for name, value in STATIC_HEADERS.items():
                    encoded = name.lower().encode("latin-1")
                    if encoded not in present:
                        raw.append((encoded, value.encode("latin-1")))
            await send(message)

        await self.app(scope, receive, send_with_headers)
