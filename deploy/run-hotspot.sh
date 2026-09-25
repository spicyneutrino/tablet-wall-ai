#!/usr/bin/env bash
# Validate the hotspot address before Caddy can open a tablet listener.
set -euo pipefail

: "${WALL_HOTSPOT_IP:?Set WALL_HOTSPOT_IP to the hotspot interface IPv4 address}"
: "${WALL_OPERATOR_PASSWORD_HASH:?Set WALL_OPERATOR_PASSWORD_HASH to a Caddy password hash}"

python3 - "$WALL_HOTSPOT_IP" <<'PY'
import ipaddress
import sys

try:
    address = ipaddress.IPv4Address(sys.argv[1])
except ipaddress.AddressValueError as exc:
    raise SystemExit(f"WALL_HOTSPOT_IP must be a valid IPv4 address: {exc}")
if address.is_unspecified or address.is_loopback or address.is_multicast or address.is_link_local:
    raise SystemExit("WALL_HOTSPOT_IP must be a real, non-loopback hotspot address")
PY

if ! ip -o -4 addr show | grep -Fq " inet $WALL_HOTSPOT_IP/"; then
    echo 'WALL_HOTSPOT_IP is not assigned to a local interface' >&2
    exit 1
fi

cd "$(dirname "$0")/.."
CADDY_BIN=${CADDY_BIN:-caddy}
"$CADDY_BIN" validate --config deploy/hotspot.Caddyfile --adapter caddyfile
exec "$CADDY_BIN" run --config deploy/hotspot.Caddyfile --adapter caddyfile
