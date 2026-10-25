# Trust, origin and rebinding check

Gate: **installed-ca-trust** — status **MISSING**. Nothing in this document
closes it. `deploy/trust_check.py` proves what a *verifier on this host* can
prove with a named trust store; it cannot prove that a tablet installed the
root, that the browser showed no warning, or that the LAN has no path to the
backend. Those are the operator steps below.

The frozen acceptance record is
[ACCEPTANCE.md](ACCEPTANCE.md). The route matrix and the original `-k` caveat
are in [`deploy/smoke.sh`](../../deploy/smoke.sh) and
[`deploy/hotspot.Caddyfile`](../../deploy/hotspot.Caddyfile).

## What the tool proves, and what it does not

`deploy/trust_check.py`:

- builds a verifying context with `ssl.create_default_context(cafile=...)`;
  with no `--ca-file` it uses the host default store. It never offers `-k`, an
  "insecure" switch or a "proceed anyway" option;
- records the store it actually loaded: a supplied bundle's path and SHA-256
  with `system_roots_loaded: false`, or the host store's `cafile`/`capath`
  and certificate counts;
- records the negotiated TLS version and cipher, the leaf SHA-256, subject,
  issuer, SANs, validity window, chain subjects/issuers and the hostname
  verification result;
- replays the `deploy/smoke.sh` route matrix over verified TLS, not `curl -k`:
  the five client documents and the WebSocket upgrade must be allowed; an
  unknown content-addressed asset must return 404 (the route reached the app);
  an invalid registration must return 422 (the route reached the app without
  creating an identity); `/uploads`, `/media`, `/diagnostics`, `/assets`,
  `/rebind`, `/devices/<id>/rebind`, every operator route and the encoded
  traversal variants must return 403;
- checks that the operator listener refuses unauthenticated reads, writes and
  the controller WebSocket upgrade with 401;
- writes one `tablet-wall-validation-evidence/1` report with
  `gate: installed-ca-trust`, `hardware_gate_status: MISSING` and every failed
  request as a named check.

It does not prove:

| Not proven | Why | Where it is recorded |
| --- | --- | --- |
| A tablet's browser/OS trusts the root | A supplied CA is verifier trust only | Report limitation; manual section below |
| The origin opens with no warning, WAN absent | The tool has no browser UI and no per-device store | Manual section below |
| A second physical LAN vantage | The route matrix runs on this host | `--second-vantage-tablet-origin` or manual |
| IPv6 unless supplied | `--ipv6-tablet-origin` is optional | `tools.vantages`, `unobserved` |
| The backend port is unreachable from the LAN | Firewall/binding is not an ingress path | Manual section below |
| Another deployment's ingress | Only the tested listener configuration was exercised | Report limitation |

A run may be `completion: complete` while the hardware gate stays `MISSING`.
Those are different claims.

## Arguments and exit codes

```text
--tablet-origin             required, bare https://host[:port]
--operator-origin           required, bare https://host[:port]
--ca-file                   optional PEM bundle; omitted = host default store
--expect-fingerprint        optional leaf SHA-256 (colons/spaces accepted)
--json-out                  required evidence report path
--timeout                   per-connection seconds (default 8)
--evidence-kind             disposable-ingress (default) or operator-hardware
--ipv6-tablet-origin        optional IPv6 literal vantage
--second-vantage-tablet-origin  optional second LAN vantage
```

Origins must be bare HTTPS origins: a path, query, fragment, embedded
credential or `http://` scheme is rejected before a socket is opened. Exit
status is 0 only when every check and scenario passed, 1 when the report is
incomplete, and 2 for an argument error.

`--expect-fingerprint` pins the **leaf** certificate presented by the tablet
origin, not the CA root. A certificate renewal changes it; record both the
root fingerprint (below) and the observed leaf in the run notes.

`deploy/smoke.sh` remains the credentialed route control and still uses
`-k` for its Caddy local CA. Its output is route evidence only; never cite a
`-k` request as trust evidence. `trust_check.py` is the separate verified-TLS
implementation of the same matrix.

## Disposable dry run

Use a generated CA and loopback listeners first. This proves the tool, not a
tablet.

```bash
python deploy/trust_check.py \
  --tablet-origin https://127.0.0.1:8443 \
  --operator-origin https://127.0.0.1:8444 \
  --ca-file /secure/lab/root.crt \
  --json-out /secure/lab/evidence/trust-dry-run.json
```

The tests in `tests/test_trust_check.py` generate their own CA, leaf and
loopback ingress and prove four failure modes: an untrusted certificate fails
closed without grading the route matrix, a wrong fingerprint fails while TLS
stays verified, a leaky `/media` or `/diagnostics` route fails, and an
unauthenticated operator listener fails.

## Public root export and custody

The CA **private key stays on the host**. Tablets receive the public root
certificate and nothing else.

Caddy's local authority normally lives under its data directory. On Linux the
default is:

```bash
ls "$XDG_DATA_HOME/caddy/pki/authorities/local/" 2>/dev/null \
  || ls "$HOME/.local/share/caddy/pki/authorities/local/"
```

`root.crt` is the public certificate; `root.key` and `intermediate.key` must
never leave the host, a backup, or a secrets store with a narrower audience
than the host itself. macOS and Windows use their own Caddy data directories;
locate `pki/authorities/local/root.crt` under the Caddy data directory rather
than copying a path from this page.

Before distributing the root:

```bash
openssl x509 -in root.crt -noout -subject -issuer -dates -fingerprint -sha256
sha256sum root.crt
```

Record the subject, validity, SHA-256 fingerprint, export date, host name and
the person who exported it. The filename alone is not identity. Compare the
fingerprint with what each device's trust settings show where the OS displays
it.

Export over removable media or a direct transfer that does not require WAN.
Never install an intermediate or private key as a device root. Never lower
verification (for example `NODE_TLS_REJECT_UNAUTHORIZED=0`, a browser flag, or
`curl -k`) to make a visit "work".

### Rotation and retirement

1. Create or select the replacement root and export only its public
   certificate.
2. Install it on every tablet, then verify trust (below) on every tablet.
3. Keep the old root installed until every tablet passes; removing it early
   makes an offline device unrecoverable without a cable and a re-install.
4. Retire the old root from devices, the host trust store and backups only
   after the signed inventory says no device depends on it.
5. Record who held both private keys, where, and for how long.

## Per-device installation (manual)

Exact menus change by OS version. Record what the device actually showed
instead of assuming a path.

### iPadOS / Safari

1. Transfer `root.crt` to the iPad (AirDrop, a local file server, or a
   managed-device profile). Avoid making the transfer depend on the origin
   whose trust is not yet installed.
2. Install the downloaded profile: Settings → General → VPN & Device
   Management → install the downloaded profile. The device asks for the
   passcode.
3. Enable full trust: Settings → General → About → Certificate Trust
   Settings → enable the root. Apple documents the distinction between
   installing a profile and trusting it:
   [Trust manually installed certificate profiles](https://support.apple.com/en-us/102390).
4. Open the exact tablet origin in Safari. A warning, an interstitial or a
   "visit anyway" link means the step failed; do not continue.

### Android / Chrome

1. Transfer `root.crt` and install it under Settings → Security →
   Encryption & credentials → Install a certificate → CA certificate. The
   exact path and the warning screens differ by manufacturer and version.
2. Confirm the certificate appears in the user credentials list.
3. Open the exact origin in the intended browser. Some Android versions or
   browsers do not accept user-installed roots for all traffic; if a warning
   appears, record it as a failed installation for that device/browser pair
   rather than disabling verification.

### What every installation row records

| Field | Example |
| --- | --- |
| Device | iPad model, exact model identifier if available |
| OS / browser | iPadOS 18.x / Safari 18.x, or Android 15 / Chrome 13x |
| Root subject and SHA-256 | output of `openssl x509 … -fingerprint -sha256` |
| Install path and profile name | what the OS displayed |
| Full-trust step | enabled / not applicable / failed |
| Installer and date | person, UTC timestamp |
| No-warning visit | screenshot of the URL bar and padlock |
| WAN state | Wi-Fi WAN uplink off, hotspot/LAN still up |

A tablet that never saw the origin before the WAN was removed, or that rejects
the CA with the WAN gone, has no in-band recovery path. Install and verify
before taking the LAN offline.

## No-warning visit with WAN absent

The gate text is "each real browser opens the intended origin with no warning
at all". Do this per tablet, with the WAN uplink disabled and the LAN still
serving:

1. Confirm the host has no default route (or the WAN interface is down) and
   the tablet is on the hotspot/LAN. Record the commands and output.
2. Confirm the tablet clock is correct; an expired or not-yet-valid
   certificate fails even with the right root.
3. Open the exact `https://<tablet-origin>` URL, not a shortcut that rewrites
   it, not a cached page, and not the operator origin.
4. Confirm: no certificate warning; the page loads; the device registers; the
   WebSocket shows a welcome; the assigned number/colour/pattern appears; a
   curated asset renders. Record the device UUID, number, viewport and
   calibration revision.
5. Reload once, then background and foreground the browser. Confirm the page
   reconnects without a warning. A real sleep/suspend test belongs to the
   device-probe and kiosk gates, not this one.
6. Screenshot the URL bar, the padlock/certificate details and the rendered
   content. Screenshots of the trust settings and the certificate fingerprint
   belong with the installation row.

The precise browser UI differs by version; the operator records what was
shown, not a generic "looks fine".

## Registration, WebSocket and content

A trusted TLS connection alone is not the gate. With WAN absent, confirm:

- the client page's assets all come from the same LAN origin (no CDN, font or
  analytics request in the network panel);
- `POST /devices/register` creates the device and the response is accepted;
- the `/ws/device` upgrade succeeds and `welcome` carries the expected number;
- the tablet receives a colour/pattern and reconnects after a forced socket
  close;
- a curated image renders at the intended crop/fit;
- reload does not produce a certificate interstitial.

Record the device UUID, display number, app SHA, view revision, calibration
revision and the exact origin in the evidence note.

## Second LAN vantage and IPv6

The verification host is one vantage. A genuinely second physical client is a
separate run **on that client** with the same tablet/operator origins and the
same CA file; its report is separate evidence and cannot inherit the primary
result. Certificates and hosts reachable only from that client must be
recorded with it.

`--second-vantage-tablet-origin` is not a simulation of a remote client. It is
for a second **address of the same ingress** that this host can reach, for
example another interface or port, and it runs the same matrix with the same
trust store:

```bash
python deploy/trust_check.py \
  --tablet-origin https://192.168.137.1:8443 \
  --operator-origin https://localhost:8444 \
  --ca-file /secure/lab/root.crt \
  --second-vantage-tablet-origin https://192.168.137.1:9443 \
  --json-out /secure/lab/evidence/trust-second-address.json
```

A second address must present a certificate valid for that address (an IP SAN,
not only a DNS name). Its result is recorded separately and cannot inherit the
primary result.

IPv6 is optional and often disabled on the hotspot. If it is enabled, the
listener must bind the IPv6 address, the certificate must carry an IPv6 SAN
(for example `IP:fd00::1`), and the firewall must apply the same rules. Run:

```bash
python deploy/trust_check.py \
  --tablet-origin https://192.168.137.1:8443 \
  --operator-origin https://localhost:8444 \
  --ca-file /secure/lab/root.crt \
  --ipv6-tablet-origin https://[fd00::1]:8443 \
  --json-out /secure/lab/evidence/trust-ipv6.json
```

The report lists every vantage in `tools.vantages` and whether it was
attempted (`tested`). An IPv4 address passed as `--ipv6-tablet-origin` is a
failed check, not a silent downgrade.

Direct backend reachability is a separate check. From the second vantage,
attempt the backend port (normally 8000) and any alternate interface address
with `curl`, `nc` or the platform equivalent; connection refused/timeout is
the expected result. Record the commands and outputs. The route matrix proves
the ingress denies backend paths, not that a firewall blocks the port.

## Origin or storage loss: rebind

An origin change (HTTP to HTTPS, a new host name/IP) or clearing site data
gives the tablet a new empty `localStorage` and therefore a new device UUID.
The server still remembers the old identity. Rebind transfers the placement,
slot, display records and number:

```http
POST /devices/<new-device-id>/rebind
Content-Type: application/json

{"replaces": "<old-device-id>", "number": <n>}
```

Rules from the implementation:

- the new identity must already have registered;
- the old identity must be **offline** (409 while it is live);
- `replaces` must differ from the new id;
- the new identity must not already be placed;
- the new identity must not already have display records of its own; the copy
  refuses to merge two histories;
- the number is taken from the old record unless supplied, and a number used
  by another device is refused;
- the active placement/slot, display profile and calibration revisions are
  copied; saved layouts are **not** rewritten;
- the old identity is removed from the roster after the hand-over.

Procedure:

1. Let the tablet register at the new origin. Record the new UUID, number (if
   any) and the exact origin.
2. Stop the old page/device so the old id is offline. Do not delete the old
   device first.
3. Rebind with `replaces` set to the old id and the display number on the
   glass. If the number is lost, read it from the old record or the physical
   label and supply it explicitly.
4. Compare before/after: active slot/placement, display number, profile
   revision, calibration revision, viewport/DPR and quarter turn.
5. Recall each saved layout that named the old id. Saved layouts keep the old
   id, so recall and save again under the new id. Do not silently edit the
   JSON; use the controller.
6. Recheck the seam and calibration after any viewport or orientation change.
   A pure origin change does not change the panel, but a new browser profile
   can change viewport chrome, so recheck rather than assume.
7. Retire the old identity: confirm it is absent from `/devices` and
   `/api/v3/config`, confirm no live socket remains, and decide explicitly
   whether old saved layouts are retained for history or deleted.

| Rebind check | Evidence |
| --- | --- |
| New UUID registered at the exact new origin | `/devices` and config snapshot |
| Old id offline before rebind | 409 avoided; timestamp |
| Slot/placement preserved | config before/after |
| Display number preserved | welcome/roster and glass label |
| Profile/calibration revisions copied | config `revisions`, calibration rows |
| Saved layout recall and re-save | screenshot plus new saved name/id |
| Seam still within 2 mm | [CALIBRATION-SHEET.md](CALIBRATION-SHEET.md) row |
| Old identity retired | roster/config and socket list |
| New origin trusted with no warning | per-device installation row |

## Saved layouts, content and calibration rechecks

- A saved layout records arrangement, not content and not the device trust
  store. Rebinding does not make an old layout point at the new id.
- Recall every layout used by the wall, confirm the intended arrangement and
  content, then save it under the new identity. Record the old and new names.
- Calibration is keyed by device id. The rebind copies the saved revisions,
  but the tablet still has its own viewport, DPR, mode and orientation; after
  a browser/origin change, confirm the client reports the expected values and
  that the seam still passes. Re-measure if the viewport, zoom, orientation or
  display mode changed.
- A view-revision change invalidates a calibration claim. Re-run the
  calibration checker with the new view revision and retain both reports.
- If the origin name changes again, repeat trust installation and verification
  before rebinding; a bind succeeds on TLS but still leaves a browser warning.

## Evidence capture

For a real host run, keep the report and the manual rows together:

```bash
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p /secure/tablet-wall/evidence
openssl x509 -in /secure/lab/root.crt -noout \
  -subject -issuer -dates -fingerprint -sha256 \
  > "/secure/tablet-wall/evidence/root-$STAMP.txt"
sha256sum /secure/lab/root.crt >> "/secure/tablet-wall/evidence/root-$STAMP.txt"
python deploy/trust_check.py \
  --tablet-origin https://192.168.137.1:8443 \
  --operator-origin https://localhost:8444 \
  --ca-file /secure/lab/root.crt \
  --json-out "/secure/tablet-wall/evidence/trust-$STAMP.json"
```

Add:

- tablet inventory: exact model, OS, browser, UUID, display number;
- installation rows and screenshots, including Certificate Trust Settings;
- the no-warning visit screenshot with WAN state and host routing output;
- the second-vantage and IPv6 outputs, or an explicit "not tested" for each;
- direct backend-port attempts and their output;
- the config snapshot (`/api/v3/config`), profile/calibration revisions and
  saved-layout names before and after rebinding;
- the calibration report and photos for the post-rebind seam;
- operator name, UTC timestamps and a signed verdict.

Raw screenshots and host logs stay outside the repository unless the operator
authorizes a bounded sample. The JSON report contains paths and hashes, not
the certificate private key or operator credentials.

Sign-off row:

`gate | date/time | app SHA | root SHA-256 | devices | origin | trust-store
kind | route result | WAN state | second/IPv6 vantage | rebind result |
failures | unobserved | artifacts | operator | verdict`

Until that row exists, **installed-ca-trust is MISSING**.

## Failure handling

- Any failed trust, route or operator-auth check blocks kit completion. Do not
  add an exemption for "just the media route" or "only IPv4".
- 403 means the tablet default-deny branch was reached. A 404 on a denied
  path is a different result: record it as a failure until the ingress is
  understood.
- A reachable TLS listener with an untrusted certificate is a failed run, not
  a reason to retry with `-k`. The report keeps the unverified certificate as
  a labelled diagnostic only.
- If the operator origin cannot be reached at all, the operator scenarios are
  skipped and the run is incomplete. Do not substitute direct backend access
  for the operator origin.
- A certificate that verifies but has the wrong host or an expired window is a
  failure; the chain result is recorded separately from the hostname result.
