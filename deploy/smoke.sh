#!/usr/bin/env bash
# Negative-route checks against the ACTUAL two-origin hotspot proxy. The -k
# switch is only for the local Caddy CA; it does not establish tablet trust.
set -euo pipefail

: "${TABLET_ORIGIN:?Set TABLET_ORIGIN, e.g. https://192.168.137.1:8443}"
: "${OPERATOR_ORIGIN:?Set OPERATOR_ORIGIN, e.g. https://localhost:8444}"

status() {
    local code
    code=$(curl --noproxy '*' -ksS --path-as-is --max-time 5 \
        --output /dev/null --write-out '%{http_code}' "$@")
    printf '%s' "$code"
}

expect() {
    local wanted="$1" actual
    shift
    actual=$(status "$@")
    if [[ "$actual" != "$wanted" ]]; then
        printf 'FAIL expected %s, got %s: %s\n' "$wanted" "$actual" "$*" >&2
        exit 1
    fi
    printf 'OK %s %s\n' "$wanted" "$*"
}

ws_status() {
    local code
    # Once upgraded, curl can time out waiting for frames; the HTTP status is
    # still useful. A fixed key is fine for a non-secret handshake probe.
    code=$(curl --noproxy '*' -ksS --http1.1 --path-as-is --max-time 2 \
        --output /dev/null --write-out '%{http_code}' \
        -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
        -H 'Sec-WebSocket-Version: 13' \
        -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' "$@") || :
    printf '%s' "$code"
}

expect_ws() {
    local wanted="$1" actual
    shift
    actual=$(ws_status "$@")
    if [[ "$actual" != "$wanted" ]]; then
        printf 'FAIL expected WS status %s, got %s: %s\n' "$wanted" "$actual" "$*" >&2
        exit 1
    fi
    printf 'OK WS %s %s\n' "$wanted" "$*"
}

# Allowed tablet routes (invalid registration payload proves it reached the
# app without actually creating/overwriting a tablet identity).
expect 308 "$TABLET_ORIGIN/client"
expect 200 -L "$TABLET_ORIGIN/client"
expect 200 "$TABLET_ORIGIN/client/"
expect 422 -X POST -H 'Content-Type: application/json' --data '{}' \
    "$TABLET_ORIGIN/devices/register"
expect 404 "$TABLET_ORIGIN/assets/sha256:$(printf '0%.0s' {1..64})"
expect_ws 101 "$TABLET_ORIGIN/ws/device?device_id=00000000-0000-4000-8000-000000000001&protocol=2"

# Everything operator-only (including GET reads, docs, and alternate paths)
# must hit the tablet origin's default-deny branch before it reaches FastAPI.
for route in / /controller/ /ws/controller /wall /devices /assets \
    /layouts /scenes /docs /openapi.json /operator-config /diagnostics /media \
    /auth/logout /auth/logout/ /auth/login/ \
    '/%77all' '/./wall' '/x/../wall' '//wall' '/client/%2e%2e/controller/' \
    '/client/..%2fwall' '/client/%2e%2e%2fwall' \
    '/client/%252e%252e/wall' '/client/..%5cwall' \
    '/assets/%2e%2e%2fwall' \
    "/assets/sha256:$(printf '0%.0s' {1..64})/../wall"; do
    expect 403 "$TABLET_ORIGIN$route"
done
# Only GET/POST /auth/login and POST /auth/logout are allowed. Wrong methods
# and near-miss paths must hit the default-deny branch.
expect 403 -X PUT -H 'Content-Type: application/x-www-form-urlencoded' \
    --data 'token=x' "$TABLET_ORIGIN/auth/login"
expect 403 -X DELETE "$TABLET_ORIGIN/auth/login"
expect 403 -X PUT -H 'Content-Type: application/json' --data '{"width":5}' \
    "$TABLET_ORIGIN/wall"
expect 403 -X POST "$TABLET_ORIGIN/wall/auto"
expect 403 -X POST "$TABLET_ORIGIN/layouts/probe/recall"
expect 403 -X DELETE "$TABLET_ORIGIN/devices/00000000-0000-4000-8000-000000000001"
expect 403 -X POST "$TABLET_ORIGIN/devices/color"
expect 403 -X POST "$TABLET_ORIGIN/devices/00000000-0000-4000-8000-000000000001/rebind"
expect 403 -X POST "$TABLET_ORIGIN/devices/00000000-0000-4000-8000-000000000001/color"
expect 403 -X PUT "$TABLET_ORIGIN/scene"
expect 403 -X PUT "$TABLET_ORIGIN/devices/00000000-0000-4000-8000-000000000001/placement"
expect 403 -X DELETE "$TABLET_ORIGIN/devices/00000000-0000-4000-8000-000000000001/placement"
expect 403 -X PUT "$TABLET_ORIGIN/layouts/Probe"
expect 403 -X DELETE "$TABLET_ORIGIN/layouts/Probe"
expect 403 -X PUT "$TABLET_ORIGIN/scenes/Probe"
expect 403 -X POST "$TABLET_ORIGIN/scenes/Probe/recall"
expect 403 -X DELETE "$TABLET_ORIGIN/scenes/Probe"
expect 403 -X GET "$TABLET_ORIGIN/devices/register"
expect 403 -X POST "$TABLET_ORIGIN/client/"
expect 403 -X POST "$TABLET_ORIGIN/client"
expect_ws 403 "$TABLET_ORIGIN/ws/controller?protocol=2"

# The operator listener must authenticate reads, writes AND websocket upgrade.
expect 401 "$OPERATOR_ORIGIN/controller/"
expect 401 "$OPERATOR_ORIGIN/wall"
expect 401 "$OPERATOR_ORIGIN/operator-config"
expect 401 "$OPERATOR_ORIGIN/diagnostics"
expect 401 -X POST "$OPERATOR_ORIGIN/wall/auto"
expect_ws 401 "$OPERATOR_ORIGIN/ws/controller?protocol=2"

# Credentialed checks are REQUIRED for a complete security result. A netrc
# file avoids putting the password in the script, shell history or process
# arguments. It must have mode 0600.
: "${WALL_OPERATOR_NETRC:?Set WALL_OPERATOR_NETRC to a mode-0600 netrc file for complete proxy/Origin verification}"
[[ "$(stat -c '%a' "$WALL_OPERATOR_NETRC")" == "600" ]] || {
    echo 'WALL_OPERATOR_NETRC must be mode 0600' >&2
    exit 1
}
auth=(--netrc-file "$WALL_OPERATOR_NETRC" --basic)
expect 200 "${auth[@]}" "$OPERATOR_ORIGIN/wall"
# No mutation can occur: a name starting with '-' is invalid (422) after a
# valid-origin request reaches the route. A simple form request is the
# cross-site, no-preflight threat we reject before route dispatch.
expect 403 "${auth[@]}" -X POST \
    -H 'Content-Type: application/x-www-form-urlencoded' --data 'name=x' \
    "$OPERATOR_ORIGIN/layouts/-invalid/recall"
expect 403 "${auth[@]}" -X POST -H 'Origin: https://attacker.invalid' \
    -H 'Content-Type: application/x-www-form-urlencoded' --data 'name=x' \
    "$OPERATOR_ORIGIN/layouts/-invalid/recall"
expect 422 "${auth[@]}" -X POST -H "Origin: $OPERATOR_ORIGIN" \
    -H 'Content-Type: application/x-www-form-urlencoded' --data 'name=x' \
    "$OPERATOR_ORIGIN/layouts/-invalid/recall"
expect_ws 403 "${auth[@]}" -H 'Origin: https://attacker.invalid' \
    "$OPERATOR_ORIGIN/ws/controller?protocol=2"
expect_ws 101 "${auth[@]}" -H "Origin: $OPERATOR_ORIGIN" \
    "$OPERATOR_ORIGIN/ws/controller?protocol=2"

echo 'Proxy route smoke passed. Still verify backend isolation and real tablets.'
