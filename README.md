# tablet-wall-ai

Turn a set of tablets into one coordinated display wall.

Each tablet opens the **client** page and registers itself with the server. A
**controller** page watches the roster of connected devices and drives what
they show.

This project began as a copy of `tablet-wall`. New development happens here.

> **Status: R1-R5 software scope implemented and the 2026-10-25 playback and
> controller review repairs merged; all physical and optical validation
> pending.** Tablets self-register, hold a live WebSocket, heartbeat,
> reconnect, and stop fighting over one identity. The operator can upload
> JPEG/PNG stills and H.264 MP4 clips (when an admission mode is configured),
> show stills on the logical wall, measure and calibrate physical panels, place
> bodies with an accessible editor, and run hard-cut still/video playlists with
> a sampled server clock, leased readiness, buffer evidence, pause/resume and
> drift samples. Schema 3 and protocol 3 are live; v1/v2 remain compatible.
> Physical seams, real tablet decode/suspend, optical timing, mixed-model
> calibration and soak are not claimed — see
> [Known limitations](#known-limitations).
>
> The current evidence record, acceptance gaps and review-fix commits are in
> the [review-fix round](docs/planning/tablet-wall-roadmap-2026-10-23/EXECUTION_LOG.md#review-fix-round-2026-10-25)
> and the [durable browser runners](simulator/README.md#durable-browser-acceptance-runners).

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

## Quickstart

```bash
uv sync          # create .venv and install dependencies
make dev         # start the server with auto-reload on http://127.0.0.1:8000
```

Then open:

| Page       | URL                            |
| ---------- | ------------------------------ |
| Client     | http://127.0.0.1:8000/client/     |
| Controller | http://127.0.0.1:8000/controller/ |
| API docs   | http://127.0.0.1:8000/docs        |

`make dev` and `make run` bind to loopback by default; a tablet cannot reach
them via the host's LAN address. For a laptop-hotspot trial with tablets, use
the [two-origin Caddy reference](deploy/README.md) instead: it exposes only
the tablet paths on the hotspot address and keeps the backend on loopback.
Find the host's interface addresses with:

```bash
hostname -I | awk '{print $1}'
```

Read [Known limitations](#known-limitations) before trying this. A deliberately
ungated test on an isolated trusted LAN is possible with
`make run HOST=0.0.0.0`, but that exposes **all** operator routes and is not
Phase 3 security. The client uses `crypto.getRandomValues` when `randomUUID`
is unavailable on a plain-HTTP LAN origin.

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
  controller/               operator dashboard; roster, wall and content control
    index.html  controller.js  controller.css
    physical.html physical.js physical.css
tests/                      pytest contract tests (HTTP + WebSocket)
pyproject.toml              deps, dev deps, pytest config
```

## How it works

1. On load, `frontend/client/client.js` resolves a device UUID and stores it in
   `localStorage`, so a tablet keeps its identity across reloads. It falls back
   to `crypto.getRandomValues` when `crypto.randomUUID` is unavailable — which
   is the normal case over a plain-HTTP LAN origin.
2. The client `POST`s that UUID and its screen size to `/devices/register`. It
   re-registers before *every* connection attempt, because the roster is held in
   memory and does not survive a server restart.
3. It then opens `/ws/device`, sends a heartbeat every 5 s, and applies whatever
   colour the controller assigns.
4. `frontend/controller/controller.js` opens `/ws/controller`, receives the
   roster as a `snapshot`, and is pushed `device_online`, `device_offline`,
   `device_updated`, and `device_removed` events as things change. It polls
   nothing.
5. Colours travel *out* over HTTP (`POST /devices/{device_id}/color`) and are
   pushed *to* the tablet over its socket.

The roster and per-device assigned colours live in memory and are lost on
restart; the active layout and scene persist in SQLite. Tablets notice a
restart, re-register, and reconnect on their own.

The full realtime contract — message shapes, close codes, timing constants — is
in [PROTOCOL.md](PROTOCOL.md).

The controller can save and recall **named layouts** (wall dimensions and all
placements, including reservations) separately from **named scenes** (content
only). Recalling a scene keeps the arrangement currently on the wall. Layout
recall asks for confirmation; saving to a name that already exists requires a
separate explicit replacement confirmation. Saved snapshots live in the same
SQLite database as the active wall, so include it in backups.

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
Keep this directory modest: inventory, scene selection and asset serving
re-scan and decode its candidates, so a large collection or repeated LAN
requests can consume substantial CPU and I/O.

**Do not put sensitive images here yet.** Any client that can reach the server
on the LAN can fetch curated image bytes, and controller authentication is not
implemented yet. An authenticated reverse proxy over TLS or a VPN is planned
for the operator surface in Phase 3; it has not been deployed by this repo.
That operator gate will **not** make device-facing asset reads private: sensitive
assets require a separate tablet/asset access boundary too.

## HTTP API

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

`device_id` must be a version 4 UUID. Width and height are unvalidated ints, so
negative or absurd dimensions are currently accepted.

## Testing

```bash
make test        # or: uv run pytest
```

The Python suite drives the app in-process via Starlette's `TestClient` (backed
by `httpx2`, which is what Starlette now expects). It covers HTTP, sockets,
wall mutations, persistence, and asset validation/serving. For the tablet's
image-loading races and whole-wall transform, also run:

```bash
node tests/client_image.test.js
```

## Known limitations

- **Run one server worker per wall/database.** Active wall state and sockets are
  process-local; two workers would diverge and could overwrite each other's
  revision or recall. The supplied `make run` command uses one process. Do not
  deploy multiple replicas against the same SQLite file.
- **The roster is not persisted.** The active layout, scene, revision and named
  snapshots survive a restart in SQLite; the generation is deliberately
  regenerated so tablets accept restored state even if its revision went
  backwards. But devices, presence, and heartbeat timestamps live in memory:
  after a restart the roster is empty until tablets re-register, which they do
  on their own. A placement whose device has not come back yet is shown as a
  **vacant reservation** and can be released by hand; it is deliberately *not*
  discarded, because a tablet that returns should reclaim the slot it had.
  Authentication and unattended operations are not in yet.
- **Bezel units depend on the mode.** In a logical wall, bezels are abstract
  wall units, not millimetres: panel size, browser chrome, and zoom all make
  millimetres unreliable from a browser. In a physical wall, the controller
  records measured display profiles and calibration in millimetres and places
  panels from those operator measurements; they are not browser-inferred
  physical proof. A well-aligned wall still needs a calibration pass, not a
  spec sheet.
- **Media support is bounded.** Curated JPEG/PNG stills are supported; a
  configured admission mode also accepts JPEG/PNG uploads and H.264 MP4
  clips. Stills render as one centered `cover` image across the whole logical
  wall. Video runs in hard-cut still/video playlists with a sampled server
  clock, leased readiness, buffer evidence, pause/resume and drift samples.
  Browser evidence is desktop Chromium software evidence on one host: it does
  not prove optical onset, physical decode/suspend, iOS Safari, mixed-model
  timing, installed CA trust, real Wi-Fi/OS, kiosk operation or soak. There is
  no arbitrary-media or cross-device optical clock claim. The still/video
  seam and failure/reconnect behaviour have been checked in desktop Chromium;
  physical iPad/Safari and Android/Chrome validation is still pending.
- **The aspect ratio compares against what the tablet reports.** The client
  reports its viewport and re-registers when that changes, and the controller
  warns when a placement's visible rect disagrees. When they do disagree the
  client still renders, covering and cropping rather than distorting — so a
  mismatch degrades the seam instead of breaking it. Pixel-perfect seams are
  not achievable from a browser without kiosk-mode control.
- **No built-in authentication.** Anyone who reaches the backend directly can
  register a device, read the roster, or repaint the wall. The optional
  operator-Origin check is a browser CSRF/WS guard, **not authentication**;
  the [two-origin hotspot reference](deploy/README.md) uses proxy Basic auth
  and a loopback-only backend. This ingress has not been physically validated.
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
- **`device_type` is hardcoded to `"ipad"`.** The client reports the actual
  viewport for aspect-mismatch warnings, but device-type identification is not
  implemented.
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

*Sequencing: the software is currently ahead of the hardware evidence. Do not
start 3c or 3d until the build through 3b has been confirmed on the actual
tablets — the real-device gates are in [deploy/KIOSK.md](deploy/KIOSK.md) and
the manual ingress checks in [deploy/README.md](deploy/README.md).*

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
- [ ] **3c** Operational resilience: structured logs, health/readiness, asset-error states, soak tests — **deferred until the tablet trial confirms 2a–3b**
- [ ] **3d** Engineering gate: ruff, targeted mypy, CI (basic CI starts in 2a) — **deferred for the same reason**

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
