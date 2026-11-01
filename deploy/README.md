# Run tablets on a laptop hotspot

## Start the HTTP hotspot trial

Enable a NetworkManager Wi-Fi hotspot and connect the tablets to it. Install
Caddy and firewalld, then run `make hotspot` from the repository root. Stop
any earlier app instance on port 8000 first.

The launcher detects the active access-point interface, reads its current
IPv4 address, starts one backend on loopback, and starts a tablet-only Caddy
listener on the hotspot address. It opens the tablet TCP port in that
interface's firewalld zone. Desktop authorization may be required. It does
not change permanent firewall settings or enable a system service.

Wait for **Ready**. Startup checks load the client and its scripts, verify
`/client` redirects to `/client/`, exercise registration payload validation
without creating a test device, verify a device WebSocket upgrade, and
check that operator routes are denied on the tablet listener. Open the
printed tablet URL on each tablet. Open the printed controller URL only on
the laptop. Confirm that each real tablet appears online in the controller;
startup checks cannot drive its browser.

First-launch options are saved for later launches:

```sh
make hotspot ARGS='--interface ap0 --data-dir /absolute/path/to/wall-data'
```

The data directory contains `wall.db`, `assets/`, `media/`, `backend.log`, and
`caddy.log`. Existing files are preserved. To use an existing wall, restore
a [verified backup](OPERATIONS.md#backups) into a new data directory with
those names before starting. The launcher does not copy a checkout database
or migrate another running wall automatically.

The default data directory is `$XDG_DATA_HOME/tablet-wall-ai`, or
`~/.local/share/tablet-wall-ai`. The settings file is
`$XDG_CONFIG_HOME/tablet-wall-ai/hotspot.json`, or
`~/.config/tablet-wall-ai/hotspot.json`. It stores the interface, data
directory, and ports. The IP address is discovered again on every launch.
Use `--backend-port` and `--tablet-port` for different ports, or `--config`
for a separate settings file. The defaults are 8000 and 8080.
Launchers share a per-user tablet-port lock across settings files, so a
second configuration cannot rely on a firewall opening owned by another
running launcher. Lock and firewall recovery records use
`$XDG_RUNTIME_DIR/tablet-wall-ai`, or `~/.cache/tablet-wall-ai` when unset.

Press Ctrl+C to stop both processes. The launcher removes only the runtime
firewall opening it added. An existing opening is left alone. Run
`make hotspot` again after a reboot or hotspot restart; it reapplies the
runtime firewall opening and checks the current address. Missing hotspots,
occupied ports, denied firewall authorization, and failed checks produce an
error instead of a ready message. Logs stay in the data directory.

This HTTP mode serves curated assets on a trusted local hotspot. It requires
application authentication to be unset and managed uploads to be disabled.
Automatic screen wake-lock needs HTTPS, so keep screens awake manually.
The backend and controller remain on loopback. Do not bind the backend to
`0.0.0.0` to work around a connection problem.

## Use the HTTPS reference

The HTTPS reference puts approximately 15–20 tablets on the laptop's
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
| [`validate_service.py`](validate_service.py) | static preflight for a filled system or user service unit, without installing or starting it |
| [`backup.py`](backup.py) (this directory) | verified snapshot of the database plus its referenced curated assets and managed image/video objects, with verify and new-target-only restore — commands and exit codes in [OPERATIONS.md](OPERATIONS.md#backups) |

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
   Also create a separate random internal credential of at least 16 characters
   in private host configuration. Load the same value as
   `TABLET_WALL_OPERATOR_CREDENTIAL` in the backend terminal and
   `WALL_OPERATOR_CREDENTIAL` in the Caddy terminal. Operator image-library and
   diagnostics reads require it even when uploads are disabled. Do not reuse
   the operator password or print the credential in logs.
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

4. In another terminal with `WALL_HOTSPOT_IP`, the hash, and the internal
   `WALL_OPERATOR_CREDENTIAL` exported, run
   `deploy/run-hotspot.sh`. The wrapper rejects a missing, wildcard or
   non-local hotspot IP or missing/short credential, validates the config, then starts Caddy. Do not
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

Managed uploads stay disabled by default. To enable them behind this proxy,
set the backend's `TABLET_WALL_UPLOAD_MODE=proxy` and an absolute
`TABLET_WALL_MEDIA_DIR`. Keep the shared internal credential configured as
described above. Caddy overwrites the internal header only after
authentication and strips it on tablet requests. Missing or mismatched
credentials make operator reads and upload requests fail closed. The simpler
HTTP `make hotspot` profile uses a direct loopback operator connection and does
not need this proxy credential.

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

## Field readiness (R5): operations notes

Everything below is software-side. The steps marked **HUMAN** need an
operator at the laptop or at the tablets; no script in this repository does
them, and none installs a CA, edits a trust store or changes host networking.

### Local-CA trust (HUMAN)

1. With Caddy running once, find its **public** root certificate, usually
   `~/.local/share/caddy/pki/authorities/local/root.crt` on Linux (`caddy
   environ` prints the data directory). Never copy `root.key`.
2. Verify the certificate from the laptop without `-k`:
   `curl --cacert root.crt https://$WALL_HOTSPOT_IP:8443/client/` must return
   the page.
3. Put `root.crt` on each tablet (AirDrop/USB/local download page — not the
   internet) and trust it as in [KIOSK.md](KIOSK.md#certificate-trust-on-an-offline-lan):
   iPadOS needs the profile *and* Certificate Trust Settings; Android varies
   by version and browser.
4. On each tablet open the tablet URL: no warning, the page paints and the
   controller roster shows it online. Only then disconnect the WAN.
5. Tick the matching gate rows in KIOSK.md. A CA that is trusted on the laptop
   but not on a tablet is the most likely first-day failure; `caddy trust`
   changes only the laptop and needs privileges, so it is not part of this.

### Origin migration and rebinding

A tablet's identity (UUID) and display number live in `localStorage`, which
is per origin. Moving from `http://` to `https://`, or to a new host, IP or
port, wipes both: the tablet registers as a brand-new device with the lowest
free number and **no placement**, while the wall keeps its placement as a
vacant reservation under the old id. Keep the origin unchanged when you can;
when you cannot:

1. Before moving, note each tablet's number and position (screenshot the
   controller). Do not delete the old devices or reservations.
2. Move the tablets to the new origin and let them register. Close the old
   pages: the old id must be offline.
3. Find the old id (the vacant reservation in the controller, or the
   `placements` keys of `GET /wall`) and the new id (the unplaced tablet; its
   short id is drawn on its screen).
4. Re-bind, from the operator origin, with exactly one `Origin` header equal
   to the operator origin:

   ```sh
   curl --netrc-file "$WALL_OPERATOR_NETRC" -X POST \
     -H "Origin: https://localhost:8444" -H 'Content-Type: application/json' \
     -d '{"replaces": "<old-id>"}' \
     https://localhost:8444/devices/<new-id>/rebind
   ```

   The new device takes over the old placement (logical) or slot plus its
   display profiles and calibrations (physical), and the old id's display
   number; the old roster record disappears and the tablet reconnects once to
   learn its number. If the server also restarted, the old number is unknown:
   add `"number": N` (the label on the glass; it must be free). Refusals:
   `409` old device online, new device already placed, number in use, or new
   device already holding display records; `404` unknown device.
5. Fix named layouts: rebinding changes the active layout only. A saved
   layout still names the old id, and recalling then saving it again preserves
   that old id. For each saved layout, recall it, then in the draft remove the
   old slot/placement and add the new device at the same position (physical:
   slot center, angle and nudge; logical: same rectangle), apply the draft,
   and save it under the original name with `?replace=true`. Repeat for every
   layout that named the old id. Saved scenes carry content only and need no
   change.
6. Check the wall, numbers and (physical) calibration status in the controller.

Rebinding is not authentication: any operator-origin caller can do it, and
only an offline old id can be replaced.

### Storage and health readout

`GET /diagnostics` (operator listener only: it needs the same admission as
`GET /media`, so it is refused while `TABLET_WALL_UPLOAD_MODE=disabled` and is
not in the tablet allowlist) returns media quota/used/free/reserve bytes,
object and ready-asset counts, `orphans` (object files no database row
lists; a crash between publish and commit leaves them, and nothing deletes
them), the database schema and size, `last_manifest_at` and client counts with
the wake-lock tally. `?verify=1` additionally re-hashes every ready object
(`media.integrity`) and is the call to make after a restore or a disk event.
Point `TABLET_WALL_BACKUP_DIR` at a snapshot (or a directory of snapshots) to
fill `last_manifest_at`; it is read-only.

```sh
curl --netrc-file "$WALL_OPERATOR_NETRC" 'https://localhost:8444/diagnostics?verify=1'
```

### Backup and recovery drill

Automated, on a throwaway instance (free loopback port, temp paths, never the
configured database): `uv run python deploy/drill.py`. It populates a wall
(placements, numbers, a saved layout, curated and uploaded images, saved
scenes, a playlist containing an upload no scene uses), runs `backup.py
backup` while the server is up, verifies, restores into new targets, boots the
restored copy and compares wall, layouts, scenes, playlist, library and the
bytes behind every image. The unused upload is *deliberately* absent after
restore. Display numbers are memory-only, so the drill checks that
re-registering tablets get their remembered numbers back with placements still
attached. `tests/test_deploy_drill.py` runs it in the suite.

The snapshot closure includes the playlist's assets (a playlist-only image
used to be omitted and restored as unavailable). A snapshot taken before that
change whose playlist names such an image fails `verify`; take a fresh one.

Real-host drill (**HUMAN**, record the time): the restore steps in
[OPERATIONS.md](OPERATIONS.md#restore-drill-rehearse-this-before-you-need-it),
then `GET /diagnostics?verify=1`, the rebind recipe above if origins changed,
and the manual checks in KIOSK.md.

### WAN-disconnected restart

`tests/test_offline.py` re-runs a seeded instance twice inside a network
namespace (`unshare -rn`) that has only loopback, after proving it cannot
reach the outside. It checks that startup, the static wall, saved layouts and
scenes, the playlist and media bytes come back, that every served page and
stylesheet references nothing outside its own origin (the SVG namespace string
is the only allowed foreign name), and that the real `client.js` registers,
connects, fetches its image from the loopback origin and paints. It is skipped
where unprivileged namespaces or `node` are unavailable. It cannot prove that
a tablet browser trusts the CA or that Safari/Chrome make no hidden requests.

### What stays MISSING

None of these are shown by software tests, and none is claimed:

- the two-hour media soak and the overnight still soak (needed for unattended
  operation);
- physical kiosk and power setup (Guided Access/pinning, display timeout,
  charging, thermal) and the OS-level behaviour of a held wake lock;
- certificate trust on real iPads and Android tablets, and the full ingress
  checks on a real hotspot;
- the exact device/build matrix, the intended physical client count and any
  real-tablet observation of rebinding, wake lock or reconnect.
