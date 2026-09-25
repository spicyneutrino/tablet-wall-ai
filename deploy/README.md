# Phase 3a hotspot reference (not a production deployment)

The intended first trial puts approximately 15–20 tablets on the laptop's
hotspot. `hotspot.Caddyfile` uses **two HTTPS origins without DNS**:

| Origin | Access | Proxy policy |
| --- | --- | --- |
| `https://<hotspot-ip>:8443` | Tablets on the hotspot | Only the tablet page, registration POST, device WebSocket and curated image bytes |
| `https://localhost:8444` | Operator **on the laptop** | HTTP Basic auth before the controller, all operator APIs and controller WebSocket |

Both origins proxy to **one** backend process on `127.0.0.1:8000`. The Caddy
listeners bind only the hotspot IP and loopback respectively. These are
different origins by host and port; no DNS service or WAN connection is needed
after installing Caddy. The sample uses Caddy's local certificate authority
(`tls internal`), not a public certificate. **Each tablet must trust that CA**;
`curl -k` on the laptop is not evidence of tablet TLS trust. Export and install
only the CA *public certificate*, never its signing key, and validate iPad
Safari and Android Chrome separately. If certificates cannot be trusted on
physical tablets, stop and choose a suitable name/certificate solution rather
than silently exposing the operator API over HTTP.

## Status and related reference artifacts

**Phase 3b status: reference artifacts pending validation.** The documents and
template below are written down but not yet exercised end to end on a real
host with real tablets. The repository installs, enables and starts none of
them, and none of it makes this deployment unattended.

| Artifact | What it is |
| --- | --- |
| [`README.md`](README.md) (this file) | the two-origin hotspot ingress reference |
| [OPERATIONS.md](OPERATIONS.md) | placeholders, service lifecycle, backup/verify/restore drill, rollback, open decisions |
| [KIOSK.md](KIOSK.md) | OS-side display behaviour (screen sleep, fullscreen, launch surface) and real-device gates |
| [tablet-wall.service.example](tablet-wall.service.example) | placeholder-only systemd unit template; you choose and install the unit yourself |
| [`backup.py`](backup.py) (this directory) | verified snapshot of the database plus only its referenced assets, with verify and new-target-only restore — commands and exit codes in [OPERATIONS.md](OPERATIONS.md#backups) |

Cross-links: the parent [../README.md](../README.md) describes what the
software does; this directory describes how traffic reaches it.

## Set up a temporary laptop trial

1. Install Caddy (v2.8+ with `basic_auth`) before disconnecting WAN. Determine
   the **laptop's hotspot interface IPv4 address** reachable by the tablets;
   do not use `0.0.0.0`, the VPN/tailnet address or an assumed default such as
   `192.168.1.1`. Export `WALL_HOTSPOT_IP=<that IP>`. If the hotspot changes
   IP, update the URL and restart Caddy/backend with the new origins.
2. Generate a password hash interactively with `caddy hash-password`; choose a
   strong operator password, save its resulting hash in the environment as
   `WALL_OPERATOR_PASSWORD_HASH` (quote the `$` characters). Never put the
   plaintext password, hash, private CA key, or browser session in the repo.
3. Start **one** backend process from the repository root with absolute data
   paths, for example (adjust your storage directory):

   ```sh
   mkdir -p "$HOME/tablet-wall-data/assets"
   export TABLET_WALL_DB="$HOME/tablet-wall-data/wall.db"
   export TABLET_WALL_ASSET_DIR="$HOME/tablet-wall-data/assets"
   export TABLET_WALL_OPERATOR_ORIGIN='https://localhost:8444'
   export TABLET_WALL_TABLET_ORIGIN="https://$WALL_HOTSPOT_IP:8443"
   make run                         # defaults to HOST=127.0.0.1
   ```

4. In another terminal with `WALL_HOTSPOT_IP` and the hash exported, run
   `deploy/run-hotspot.sh`. The wrapper rejects a missing, wildcard or
   non-local hotspot IP, validates the config, then starts Caddy. Do not
   bypass it with a raw `caddy run` on a shared machine.
   Follow Caddy's [local HTTPS instructions](https://caddyserver.com/docs/automatic-https#local-https)
   for locating/trusting its CA root on the laptop and tablets. Verify the
   actual iPad/Android browser opens the tablet URL **without** a certificate
   warning before declaring TLS ready. Retain the CA key safely; anyone with
   that key can forge certificates for trusted devices.
5. Open `https://localhost:8444/controller/` on the laptop, authenticate, and
   copy the displayed tablet URL to the tablets. Run `deploy/smoke.sh` against
   both origins **with operator credentials** as described below. Keep the
   asset directory curated: its bytes are intentionally
   accessible to every device on the hotspot.

**Do not expose `:8000` to the hotspot.** `make run` now binds loopback by
default; `make run HOST=0.0.0.0` bypasses the proxy and is insecure for this
deployment. Confirm from a second LAN device that the laptop's `:8000` port
cannot be reached. Local users/processes on the laptop can still bypass the
proxy; control laptop access accordingly. Test port reachability over IPv4
and IPv6 if both are enabled. For a server later, adapt the bindings, TLS and
operator-auth system deliberately and repeat the full ingress checks; this
sample is **not** an unattended service, backup, or identity design.

## Boundary and verification

The tablet ingress is a **default-deny** route/method allowlist. `/client/`
and its current three static files are listed individually; if client assets
are added later, extend the list deliberately and rerun the encoded-path
checks. In
particular `GET /assets` (inventory), `GET /devices`, `GET /wall`, snapshots,
`/controller/`, `/ws/controller`, `/docs`, and every operator write are denied
on the tablet origin. The operator origin requires proxy auth for **all**
requests, not just `/controller/`. Caddy forwards WebSocket upgrades. The
backend's configured operator Origin check blocks cross-origin or origin-less
state-changing requests and controller WebSocket handshakes, including simple
form POSTs to scene/layout recall and auto-arrange; it is **not** a replacement
for proxy authentication or backend isolation. Normal browser-initiated
same-origin requests include the Origin header. Non-browser automation needs
an explicit exact operator Origin **and** valid proxy credentials.

With the two exports below, run the included negative-route smoke test:

```sh
export TABLET_ORIGIN="https://$WALL_HOTSPOT_IP:8443"
export OPERATOR_ORIGIN='https://localhost:8444'
export WALL_OPERATOR_NETRC=/path/to/private-netrc
deploy/smoke.sh
```

The netrc file must contain `machine localhost login operator password <your
operator password>` and be `chmod 600`; keep it outside the repo. Without
credentials the script cannot verify that the proxy passes same-origin
requests but rejects CSRF and hostile controller WebSockets, so it exits
incomplete rather than reporting a security pass. The local Caddy root trust
is verified separately (for example, curl's `--cacert` using Caddy's **public**
`root.crt`, with certificate verification enabled).

The script intentionally uses `-k` for the **temporary local CA** on the
laptop. It must not be used to claim browser certificate trust or production
TLS. Supplement it with an actual unauthenticated LAN-host probe against
`:8000`, a real tablet's page/registration/socket/image render, an
authenticated controller HTTP/WS flow, a foreign-origin form POST and WS
attempt, and a WAN-disconnected restart/recall check. Block or firewall the
operator port for hotspot clients even if the operator listener is intended
to bind loopback.

To rehearse **20 mixed-size connections** through the actual tablet ingress,
run `uv run python deploy/load-smoke.py --tablet-origin "$TABLET_ORIGIN"
--ca-cert /path/to/caddy/root.crt --devices 20 --asset-id sha256:<curated-id>`.
This checks concurrent registration, WebSocket welcome/wall frames, and
optional image delivery using a verified CA; it does **not** test whether the
hotspot accepts 20 physical clients, image seams, display sleep, sustained
uptime, or reconnect after a radio outage. Those require the real tablets.

The residual risk is explicit: public registration and `/ws/device` have no
device pairing or per-tablet identity yet. A LAN peer that learns/guesses a
device UUID can replace its socket and spoof presence; rate limiting and
pairing/revocation belong to subsequent security work. Curated asset bytes are
public on the tablet origin, not private operator content. The SQLite DB plus
its referenced image bytes both require backups; SQLite should be backed up
using its online backup API, not a raw file copy during writes. The snapshot,
verify and restore drill — including stopping the service first and restoring only
into new paths — is in [OPERATIONS.md](OPERATIONS.md#backups).
