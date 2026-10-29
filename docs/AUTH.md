# Enable shared-secret authentication

Set `TABLET_WALL_AUTH_TOKEN` to a random secret with at least 32 bytes before starting the server. Generate one with `python -c 'import secrets; print(secrets.token_urlsafe(32))'`. Store the value in your service's environment or secret manager, then restart the server.

An unset or empty value preserves the existing unauthenticated behavior. A nonempty value shorter than 32 bytes fails closed with HTTP 503. Authentication covers every HTTP route, static file, and WebSocket endpoint. Only the credential-entry page and its login submission at `/auth/login` are public.

## Sign in from a browser

Open `/controller/` or `/client/` on each browser that needs access. The server redirects page navigation to `/auth/login`. Enter the access token and select **Sign in**. The token travels in the POST body, never in a URL. The login page requires a same-origin `Origin` header, which browsers send on form submissions.

The server issues a signed cookie that expires after 12 hours. The cookie has `HttpOnly`, `SameSite=Strict`, and `Path=/`. HTTPS connections also receive `Secure`. Use HTTPS when other machines can observe the network. With a TLS reverse proxy, preserve the original host and configure trusted proxy headers so the application sees the public HTTPS scheme.

Sign in separately on the tablet and operator origins when you use a two-origin deployment. A cookie grants the same application access as the shared secret. The application does not define separate tablet and operator roles. Keep the existing reverse-proxy route restrictions when you need those roles.

Cookie-authenticated writes and WebSocket handshakes require exactly one `Origin` header that matches the request's scheme and host, including its port. A missing, duplicate, `null`, or foreign origin fails with HTTP 403. Browser pages use this rule without JavaScript changes. A proxy must preserve the public host and scheme for this comparison.

To sign out, submit a same-origin `POST /auth/logout`, or clear the site's cookies. Signing out clears that browser's cookie. To revoke all issued cookies and API credentials, replace `TABLET_WALL_AUTH_TOKEN` and restart the server. Stateless cookies cannot revoke one copied session individually.

## Authenticate a script

Send `Authorization: Bearer <token>` on each HTTP request and WebSocket handshake. For example, after setting the token in your shell, run:

```sh
curl --fail --header "Authorization: Bearer $TABLET_WALL_AUTH_TOKEN" http://localhost:8000/wall
```

Never put the token in a query string. Query tokens and WebSocket subprotocol tokens are not accepted. A missing or incorrect credential returns HTTP 401 with `WWW-Authenticate: Bearer`. WebSockets are refused before upgrade. ASGI servers without HTTP handshake-denial support close the handshake instead.

The existing `TABLET_WALL_OPERATOR_ORIGIN` guard still applies to bearer-authenticated writes and `/ws/controller`. If you configure that guard, scripts must also send its exact `Origin` value. Browser sessions must satisfy both the configured operator origin and the request's own origin. `POST /devices/register` keeps its existing operator-origin exemption, but it still requires authentication and cookie CSRF checks.

## Operate the server

Use a strong random secret. The application bounds login request bodies but does not rate-limit attempts. Apply rate limits at your reverse proxy when the server is exposed beyond a trusted network. Avoid logging authorization headers, login request bodies, or cookies. Keep transport encryption and any existing proxy authentication enabled.

Health checks, backup scripts, deployment probes, and other automation also need bearer credentials when authentication is enabled. Public documentation endpoints and static assets have no authentication exemption.

Authenticated HTTP responses use `Cache-Control: private, no-store`, including image bytes, video ranges, and static files. Authentication overrides the normal public immutable asset cache policy so shared caches cannot serve protected bytes to another caller.
