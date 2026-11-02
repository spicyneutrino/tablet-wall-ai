# tablet-wall-ai

Turn a set of tablets into one coordinated display wall.

Each tablet opens the **client** page and registers itself with the server. A
**controller** page watches the roster of connected devices and drives what
they show.

This project began as a copy of `tablet-wall`. New development happens here.

> **Status: working image-wall prototype.** Tablets connect through their
> browsers, show portions of one shared image, and can be arranged through the
> controller. The operator reports physical trials in 2×2 and 1×4 arrangements.
> Measured profiles, ruler calibration, rotation mapping, and saved layouts
> are implemented. Precise mixed-model alignment and sustained physical
> operation still need recorded validation.
>
> Experimental still/video playlist code and automated playback tests also
> exist. They do not establish working video playback on the intended tablets.
> The currently demonstrated hardware scope is image display. Physical seams,
> tablet video decode/suspend, optical timing, and soak are not claimed. See
> [Known limitations](#known-limitations).
>
> The current combined plan and evidence are in the
> [readiness roadmap](docs/tablet-wall-readiness/ROADMAP.md) and
> [verification record](docs/tablet-wall-readiness/VERIFICATION.md). The
> [image-wall runbook](deploy/IMAGE-WALL-RUNBOOK.md) covers startup and recovery.

> New to the codebase? Read the [field guide](docs/field-guide/index.html)
> (open it in a browser) or its [Markdown source](docs/field-guide/GUIDE.md).
> It explains the architecture, the playback model, the geometry, the media
> pipeline, the security boundary, and the current roadmap.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

## Run on this laptop

```bash
uv sync          # create .venv and install dependencies
make dev         # start the server with auto-reload on http://127.0.0.1:8000
```

These addresses work only on the computer running the server:

| Page       | URL                            |
| ---------- | ------------------------------ |
| Local client test | http://127.0.0.1:8000/client/ |
| Wall console | http://127.0.0.1:8000/controller/physical.html |
| Logical compatibility editor | http://127.0.0.1:8000/controller/ |
| API docs   | http://127.0.0.1:8000/docs        |

## Connect tablets to the laptop hotspot

On Linux with NetworkManager, firewalld, and Caddy installed, enable the
laptop's Wi-Fi hotspot, connect the tablets to it, then run:

```bash
make hotspot
```

Stop any earlier `make dev` or `make run` process first. The launcher refuses
occupied ports rather than replacing another server.

After its startup checks pass, open the printed **Tablets** URL on each
tablet. For a hotspot at `10.42.0.1`, it is
`http://10.42.0.1:8080/client/`. Use the URL printed for your current hotspot;
its address can change. Both `/client` and `/client/` work. A tablet must never
use `127.0.0.1` or `localhost` to reach the laptop.

The Wall console stays at
`http://127.0.0.1:8000/controller/physical.html` on the laptop. Its **System**
tab shows the exact tablet address, Copy button, join QR, and readiness facts.
A loopback address carries a warning that it only opens on this computer.
The QR is an address shortcut; it does not authenticate or approve a tablet.

The launcher saves settings in `~/.config/tablet-wall-ai/hotspot.json` and
wall data in `~/.local/share/tablet-wall-ai/`, respecting the corresponding
XDG directories. Next time, run `make hotspot` again. This does not load or
overwrite a database in the checkout. See [hotspot options and existing
data](deploy/README.md#start-the-http-hotspot-trial) to choose another directory.

This is an HTTP trial for a trusted hotspot. Keep tablet screens awake
manually; automatic wake-lock requires HTTPS. Only tablet routes are exposed
on the hotspot. Press Ctrl+C to stop both servers and remove the firewall
opening if the launcher added it. For TLS and certificate trust, use the
[HTTPS reference](deploy/README.md#use-the-https-reference).

## Project layout

```
main.py                     FastAPI app: HTTP, v3 API and WebSocket routes
tabletwall/                 state, persistence, hub, media, displays, geometry,
                            clock, playback, writer and the image worker
assets/                     optional server-local curated images (create it)
media/                      managed upload objects and staging (created at run)
PROTOCOL.md                 the realtime contract between server and pages
deploy/                     hotspot proxy reference, service unit template,
                            operations + kiosk notes, backup/restore tool
frontend/
  client/                   runs on each tablet; paints its wall slice
    index.html  client.js  client.css  view.js
  controller/               one operator workspace for tablets, arrangement,
                            images, saved records and settings
    physical.html physical.js operator-*.js
    operator-tokens.css operator-workspace.css operator-stage.css fonts/
    index.html operator-entry.js (forwards to the workspace)
    experimental.html controller*.js controller.css (opt-in compatibility tools)
tests/                      pytest contract tests (HTTP + WebSocket)
pyproject.toml              deps, dev deps, pytest config
```

## How it works

1. On load, `frontend/client/client.js` resolves a device UUID and stores it in
   `localStorage`, so a tablet keeps its identity across reloads. It falls back
   to `crypto.getRandomValues` when `crypto.randomUUID` is unavailable — which
   is the normal case over a plain-HTTP LAN origin.
2. The client `POST`s that UUID and its screen size to `/devices/register`. It
   re-registers before every connection attempt to refresh its dimensions and establish live presence.
3. It opens `/ws/device`, sends a heartbeat every 5 s, and applies the current
   scene and its assigned slice. Static images use one wall-wide Fill (`cover`)
   or Fit whole image (`contain`) transform.
4. The Wall console reads `/api/v3/config` and subscribes to protocol-3
   `/ws/controller` updates. It also reconciles every 15 s while visible.
5. Tablets report image attempts and painted frames using connection/revision
   tokens. The console distinguishes current reports, loading, failed, stale,
   hidden, offline, and mapping-blocked states. A paint report is software
   evidence, not proof of optical alignment.

Device identity, dimensions, type, display number, last seen, and assigned colours survive restart in SQLite. Restored devices start offline. Sockets, capabilities, clocks, and playback leases are never restored. Tablets re-register and reconnect on their own.

The full realtime contract — message shapes, close codes, timing constants — is
in [PROTOCOL.md](PROTOCOL.md).

The controller can save and recall **named layouts** (wall dimensions and all
placements, including reservations) separately from **named scenes** (content
only). Recalling a scene keeps the arrangement currently on the wall. Layout
recall asks for confirmation; saving to a name that already exists requires a
separate explicit replacement confirmation. Saved snapshots live in the same
SQLite database as the active wall, so include it in backups.

### Operator diagnostics

The Wall console keeps Wall, Tablets, Content and System tabs available
on desktop and phone screens. Under System, Field check can refresh storage,
backup and client health or verify stored object bytes. Download report saves
the last successful response as timestamped JSON, including integrity results
when verification was requested. Failed refreshes disable download until a
successful retry. Diagnostics use operator-read admission independently of upload
mode. Reports contain operational metadata; review them before sharing.
Desktop browser evidence does not replace physical tablet validation.

### Curating still images

There are two sources. **Curated files**: create an `assets/` directory at the
repository root (or set `TABLET_WALL_ASSET_DIR` to another server-local
directory) and copy JPEG or PNG files into it. **Managed uploads**: set
`TABLET_WALL_MEDIA_DIR` (default `./media`), choose
`TABLET_WALL_UPLOAD_MODE=loopback` for direct local use or `proxy` with
`TABLET_WALL_OPERATOR_CREDENTIAL` behind the authenticated operator listener,
and use the controller's upload panel. Uploads are disabled by default; the
normalized master and renditions are exact-byte objects behind `/assets/{id}`.
Use the controller's asset
refresh control to discover newly copied files without restarting the server.
Only top-level, non-symlink, non-animated files are inventoried; the initial
limits are 10 MiB and 12 megapixels per image. Normalize EXIF rotation before
copying an image. The controller selects an opaque SHA-256 asset ID rather than
a path, so a rename preserves a scene but changing the bytes gives the image a
new identity and requires re-selection. Back up **both** the SQLite database
and the referenced curated image bytes: the database contains references,
not image bytes. Unreferenced files are not in this snapshot; preserve them
separately if needed. The snapshot/restore drill is in
[deploy/OPERATIONS.md](deploy/OPERATIONS.md#backups).
Keep this directory modest. Every lookup reads and hashes current files; full image decoding is cached by content hash. See the [measured cache behavior](docs/ROBUSTNESS.md#repeatable-inventory-measurement).

When authentication is disabled, every client that reaches the backend can read curated and managed assets. Built-in token authentication protects asset reads as well as operator routes. A proxy protecting only the operator listener does not protect tablet-facing asset URLs. Keep the backend on loopback and use TLS for token or cookie transport on shared networks.

## Change the wall size

Open the [Wall console](http://127.0.0.1:8000/controller/physical.html), then
**Wall → Layout & size**. Choose **Logical units** or **Measured millimetres**,
select **2 × 2** or **1 × 4**, review the participating tablet order and body
orientation, then **Preview arrangement → Apply layout**. The 1 × 4 preset
means one horizontal row. Gap defaults to zero; Fit wall to tablet bodies
makes the bounds follow the packed footprints. Preview and Cancel do not
change the tablets.

Measured layouts use pinned screen, bezel and calibration records. Confirm the
actual model or save measurements before using that mode. Model profiles remain
approximate; they do not establish seam accuracy. Advanced bounds and
measurements are under **System**; selected-tablet mount angles and nudges are
under **Tablets**. Missing referenced measurements
block fitting rather than guessing a size.

The [logical compatibility editor](http://127.0.0.1:8000/controller/) retains
custom logical Width/Height and packing controls under **Layout**. It is blocked
while a measured layout is active. Use the Wall console for normal image and
arrangement changes. See [wall sizing behavior](docs/WALL-SIZING.md) and
[physical calibration](docs/PHYSICAL-CALIBRATION.md).

## HTTP API

The primary console uses the authoritative v3 routes described in
[the operator protocol](docs/OPERATOR-PROTOCOL.md). The compatibility endpoints
below retain logical editing. `/wall` and `/scene` refuse a measured wall with
an upgrade conflict; use v3 to read or change its actual layout and scene.

| Method   | Path                          | Purpose                               |
| -------- | ----------------------------- | ------------------------------------- |
| `GET`    | `/`                           | Liveness greeting                     |
| `GET`    | `/devices`                    | Full roster, keyed by device id       |
| `GET`    | `/device/{device_id}`         | One device record; `404` if unknown   |
| `GET`    | `/devices/register`           | Hint that registration is a `POST`    |
| `POST`   | `/devices/register`           | Register or refresh a device          |
| `POST`   | `/devices/{device_id}/color`  | Set one device's colour               |
| `POST`   | `/devices/color`              | Set every device's colour             |
| `DELETE` | `/devices/{device_id}`        | Remove a device from the roster       |
| `GET`    | `/wall`                       | Active layout, scene, revision        |
| `PUT`    | `/wall`                       | Change logical wall dimensions        |
| `PUT`    | `/scene`                      | Select colour, calibration or image   |
| `GET`    | `/assets`                     | Refresh curated image inventory       |
| `GET`    | `/assets/{id}`                | Read validated same-origin image      |
| `GET`    | `/layouts`, `/scenes`         | List named arrangement/content snapshots |
| `PUT`    | `/layouts/{name}`, `/scenes/{name}` | Save current layout/content (409 if name exists; `?replace=true` overwrites) |
| `POST`   | `/layouts/{name}/recall`, `/scenes/{name}/recall` | Restore arrangement/content separately |
| `DELETE` | `/layouts/{name}`, `/scenes/{name}` | Remove a saved snapshot |
| `GET`    | `/ws/device?device_id=…`      | Device socket: liveness + commands    |
| `GET`    | `/ws/controller`              | Controller socket: roster events      |
| `GET`    | `/docs`                       | Interactive OpenAPI docs              |

Registration body:

```json
{
  "device_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
  "width": 1024,
  "height": 768,
  "device_type": "ipad"
}
```

`device_id` must be a version 4 UUID. Width and height must be positive
integers no greater than 16384.

## Testing

```bash
make test        # Python and all client JavaScript tests
```

The Python suite drives the app in-process via Starlette's `TestClient` (backed
by `httpx2`, which is what Starlette now expects). It covers HTTP, sockets,
wall mutations, persistence, and asset validation/serving. For the tablet's
image-loading races and whole-wall transform, also run:

```bash
node tests/client_image.test.js
```

## Hardware validation kit

The eight physical and deployment gates remain **MISSING**. The repository
contains a kit that builds the evidence and procedures but never promotes a
synthetic, desktop-browser, loopback or simulated run to a hardware result:

- gate matrix and operator runbook: [docs/validation/HARDWARE-VALIDATION.md](docs/validation/HARDWARE-VALIDATION.md);
- frozen targets: [docs/validation/ACCEPTANCE.md](docs/validation/ACCEPTANCE.md);
- evidence contract: [docs/validation/EVIDENCE-SCHEMA.md](docs/validation/EVIDENCE-SCHEMA.md);
- optical capture, device probe, trust/origin, calibration, soak/network and
  kiosk runbooks live under `docs/validation/`.

A gate changes only with the operator's signed physical evidence.

## Known limitations

- **Run one server worker per wall/database.** Active wall state and sockets are
  process-local; two workers would diverge and could overwrite each other's
  revision or recall. A database-scoped runtime lock now refuses a second process. The supplied `make run` command uses one process. Do not
  deploy multiple replicas against the same SQLite file.
- **Presence is live.** Safe device metadata and colours persist, but a restart marks every device offline until it reconnects. Layouts and scenes retain their revision; the server mints a new generation. Missing placements remain available as saved spots. See [restart and ownership behavior](docs/ROBUSTNESS.md).
- **Bezel units depend on the mode.** In a logical wall, bezels are abstract
  wall units, not millimetres: panel size, browser chrome, and zoom all make
  millimetres unreliable from a browser. In a physical wall, the controller
  records measured display profiles and calibration in millimetres and places
  panels from those operator measurements; they are not browser-inferred
  physical proof. A well-aligned wall still needs a calibration pass, not a
  spec sheet.
  See [mixed-tablet physical calibration](docs/PHYSICAL-CALIBRATION.md) for the
  tablet ruler, measured viewport setup, and whole-wall grid check.
- **Media support is bounded.** Curated JPEG/PNG stills are supported; a
  configured admission mode also accepts JPEG/PNG uploads and H.264 MP4
  clips. Stills render with one centered wall-wide Fill (`cover`) or
  Fit whole image (`contain`) transform in either layout kind. Experimental
  video code uses hard-cut still/video playlists with a sampled server
  clock, leased readiness, buffer evidence, pause/resume and drift samples.
  Browser evidence is desktop Chromium software evidence on one host: it does
  not prove optical onset, physical decode/suspend, iOS Safari, mixed-model
  timing, installed CA trust, real Wi-Fi/OS, kiosk operation or soak. There is
  no arbitrary-media or cross-device optical clock claim. The still/video
  seam and failure/reconnect behaviour have been checked in desktop Chromium;
  physical iPad/Safari and Android/Chrome validation is still pending.
- **Logical and measured mapping differ.** A logical placement with a different
  visible aspect is covered and cropped rather than distorted, which can leave
  a seam mismatch. A measured plan checks pinned calibration against the live
  viewport, orientation, zoom and launch mode; a mismatch blocks the plan with
  a recovery reason. Physical alignment still needs a recorded device trial.
- **Authentication is opt-in.** Set `TABLET_WALL_AUTH_TOKEN` to a random secret of at least 32 bytes to protect all HTTP and WebSocket routes. Browsers sign in at `/auth/login`; API clients use a Bearer token. Unset or empty preserves open local operation. See [authentication setup](docs/AUTH.md). The operator-Origin guard and proxy isolation remain separate checks. Use TLS on shared networks.
- **A device must register before it can open a socket.** A socket for an
  unregistered id is closed with `4404` rather than registering on the fly, so
  registration stays the single source of device metadata.
- **`last_seen` is not pushed while a device is healthy.** It only reaches
  controllers when something changes, so a controller must render an online
  device as live rather than counting up a stale timestamp. See
  [PROTOCOL.md](PROTOCOL.md).
- **Frontend files are always revalidated.** The static mounts send
  `Cache-Control: no-cache`, so a browser asks the server (ETag, usually a 304)
  before reusing `client.js` or `controller.js`. A tablet that loaded the page
  *before* this header existed may still need one hard refresh.
  `fastapi dev` reloads the server, not the browser.
- **The app must run from the repository root.** The static mounts use relative
  paths (`StaticFiles(directory="frontend/client")`), so importing `main` from
  any other directory raises `RuntimeError: Directory 'frontend/client' does not
  exist`. The `make` targets handle this for you.
- **One socket per device, none for controllers.** A second socket for the same
  device id silently replaces the first, so two browser tabs on one origin share
  a single identity. Controller sockets have no heartbeat, so one that vanishes
  without a clean close is only reaped when a later broadcast to it fails.
- **Model detection is approximate.** The client reports its platform and
  screen signature. Built-in iPad Air 2 and Pixel C matches reuse measured
  profiles; a signature is not proof of the exact hardware. Unknown models
  need manual measurements.
- **Screen sleep is still an OS decision.** In a secure context (HTTPS) the
  page asks for a Screen Wake Lock while it is visible, retakes it when the
  page returns, and reports `held`/`released`/`unsupported`/`insecure`/`denied`
  per tablet in the roster. On a plain-HTTP origin the API does not exist, and
  a held lock never replaces kiosk, Auto-Lock or power settings. Its only
  fullscreen request is the on-screen "Full screen" button (shown for 5 s
  after a touch) — see [deploy/KIOSK.md](deploy/KIOSK.md).

## Roadmap

**Phase 0 — hygiene** ✅ *done*

- [x] Commit the app and frontend (previously untracked)
- [x] Add this README
- [x] Add a dev script (`Makefile`)
- [x] Add pytest scaffolding and contract tests

**Phase 1 — close the core loop** ✅ *done*

- [x] Fix the secure-context `crypto.randomUUID()` failure (`getRandomValues` fallback)
- [x] Replace polling with a WebSocket channel for clients and controller
- [x] Build the controller UI: device tiles with status and last-seen
- [x] Implement `POST /devices/{device_id}/color` end to end
- [x] Add heartbeats, expiry, and deregistration so `last_seen` is honest
- [x] Add reconnect with backoff to `client.js`

**Phase 2 — a coherent wall of still images** ✅ *software done*

*Definition of done: a curated still image displays as one coherent wall, and
the operator can save and recover its arrangement and presentation.*

- [x] Protocol v2: version negotiation and capability advertisement
- [x] Wall coordinate space, placements, and bezel insets
- [x] Controller: wall panel, placement editing, wall map, auto-arrange
- [x] Client: calibration rendering with a verified seam
- [x] Separate layout from scene; add the generation reset rule
- [x] Persist the active layout and scene (SQLite)
- [x] **2a** Integrity: removable vacant reservations, persist-before-apply, honest controller content states
- [x] **2b** Curated assets and the still-image wall (desktop Chromium verified;
  physical tablet validation remains)
- [x] **2c** Named layout/scene save and recall — closes the Phase 2 software
  milestone (physical iPad/Android verification remains)

Clock sync and video are **not** Phase 2. A still image needs no shared playback
clock, and clock sync without a timed medium is cost with no visible capability.

**Phase 3 — safe, unattended operation**

*Software checks are ahead of the hardware evidence. They do not establish
unattended operation. Real-device gates remain in [deploy/KIOSK.md](deploy/KIOSK.md)
and the manual ingress checks in [deploy/README.md](deploy/README.md). The
[current readiness programme](docs/tablet-wall-readiness/ROADMAP.md) supersedes
the earlier software sequencing below.*

- [ ] **3a** Trust boundary: a two-origin laptop-hotspot proxy reference and
  configurable same-origin operator guards are in progress. Physical ingress
  checks and certificate trust on real tablets are required before calling it
  secure. Device identity, pairing and revocation remain separate decisions.
- [ ] **3b** HTTPS, deployment service, kiosk guidance, backups — **reference
  artifacts pending validation**: [service unit
  template](deploy/tablet-wall.service.example), [operations
  notes](deploy/OPERATIONS.md), [kiosk/tablet
  notes](deploy/KIOSK.md) and the backup/restore tool
  ([deploy/backup.py](deploy/backup.py)) are written and covered by automated
  tests, including a full backup/verify/restore drill; none of it has been
  exercised in a real deployment. Not complete, and not an unattended
  deployment.
- [ ] **3c** Operational resilience: health/readiness, bounded logs and image-error recovery are implemented and software-tested in the [readiness programme](docs/tablet-wall-readiness/ROADMAP.md); real-tablet soak remains open
- [ ] **3d** Engineering gate: production Ruff and mypy run with the tests; the current [verification record](docs/tablet-wall-readiness/VERIFICATION.md) lists results. Hardware acceptance remains separate

**Phase 4 — timed media, software slice**

- [x] Clock estimation, scheduled starts, leased readiness, hard-cut stills
- [x] Native H.264 MP4 ingest, ranged serving, buffered preparation, drift
  samples, pause/resume and loop occurrences in a real browser
- [ ] Physical tablet decode/suspend, optical onset, mixed-model timing and a
  ten-minute optical run. The browser evidence is software timing on one host
  clock, not a wall-synchronization claim.

---

**There is no AI capability, and none is planned.** The project name is
`tablet-wall-ai` for historical reasons; nothing in it uses a model, and no
schema or roadmap space is reserved on the assumption that something will.

## Developer checks

Run `uv sync --all-groups` before the checks. `make test` runs Python tests and all JavaScript suites. `make lint` runs Ruff syntax, undefined-name, unused-import, and common-defect checks on production Python. `make typecheck` checks annotated production code with strict optional handling; unannotated function bodies are not yet enforced.

`make coverage` measures Python lines and branches, including worker subprocesses, writes `coverage.xml`, and enforces an 80% combined floor. Current image-wall browser acceptance uses `uv run --group browser python -m simulator.browser.readiness_acceptance --artifacts /tmp/new-readiness-run` and `uv run --group browser python -m simulator.browser.operator_accessibility --artifacts /tmp/new-accessibility-run`. Use a fresh artifact directory each time. The older `controller_run` covers experimental playback; it is not the image-wall acceptance gate. See the [browser runner guide](simulator/README.md#current-image-wall-acceptance).

For repeatable viewport and reconnect checks, run `uv run --group browser python -m simulator.browser.audit_round --round 6 --artifacts /tmp/new-viewport-audit`. The browser runners always use temporary database, media, and asset paths. For any manual app launch, set those paths to a disposable scratch copy before startup; startup creates directories, writes SQLite, and cleans staging.

Before installing a filled service template, run `uv run python deploy/validate_service.py /path/to/tablet-wall.service --scope user` or `--scope system`. The shipped template intentionally fails until its placeholders are filled. See [operations](deploy/OPERATIONS.md).

The earlier generated guides and planning documents in `docs/docs_model*/` and `docs/planning/` are historical design evidence. Use this README, PROTOCOL.md, and the current deployment guides for runtime behavior.
