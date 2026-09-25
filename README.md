# tablet-wall-ai

Turn a set of tablets into one coordinated display wall.

Each tablet opens the **client** page and registers itself with the server. A
**controller** page watches the roster of connected devices and, eventually,
drives what they show.

This project began as a copy of `tablet-wall`. New development happens here.

> **Status: Phase 2 in progress.** Tablets self-register, hold a live
> WebSocket, heartbeat, and reconnect on their own. The controller is an
> operator dashboard that shows the wall live, places tablets on a shared wall
> canvas, and drives a calibration pattern to check the geometry. The active
> layout and scene persist across restarts. Still images are not implemented
> yet, and there is no authentication — see
> [Known limitations](#known-limitations) and [Roadmap](#roadmap).

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

To open the client from a tablet, use the host machine's LAN address instead of
localhost, e.g. `http://192.168.1.50:8000/client/`. Find it with:

```bash
hostname -I | awk '{print $1}'
```

Read [Known limitations](#known-limitations) before trying this — the client
currently fails on a plain-HTTP LAN origin.

## Project layout

```
main.py                     FastAPI app: HTTP routes, WebSocket hub, presence
PROTOCOL.md                 the realtime contract between server and pages
frontend/
  client/                   runs on each tablet; registers, listens, shows colour
    index.html  client.js  client.css
  controller/               operator dashboard; live roster + colour control
    index.html  controller.js  controller.css
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

Server state lives in dicts in `main.py`, so the roster and every assigned
colour are lost on restart. Tablets notice, re-register, and reconnect on their
own.

The full realtime contract — message shapes, close codes, timing constants — is
in [PROTOCOL.md](PROTOCOL.md).

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

The suite drives the app in-process via Starlette's `TestClient` (backed by
`httpx2`, which is what Starlette now expects). `tests/test_api.py` covers the
HTTP surface; `tests/test_websocket.py` drives real sockets through
`TestClient.websocket_connect`, including presence transitions, colour replay,
and every documented close code.

## Known limitations

- **The roster is not persisted.** The active layout, scene, revision, and
  generation survive a restart in SQLite, so a wall you arranged stays arranged
  and a restart resynchronises tablets rather than blanking them. But devices,
  presence, and heartbeat timestamps live in memory: after a restart the roster
  is empty until tablets re-register, which they do on their own. A placement
  whose device has not come back yet is shown as a **vacant reservation** and
  can be released by hand; it is deliberately *not* discarded, because a tablet
  that returns should reclaim the slot it had. Nothing else about Phase 3 —
  authentication, roster persistence, ops — is in yet.
- **Bezels are abstract units, not millimetres.** Wall units are a layout
  convenience, deliberately not physical measurement: panel sizes, browser
  chrome, and zoom all make millimetres unreliable from a browser. A
  well-aligned wall needs a calibration pass, not a spec sheet.
- **Content is colour and calibration only.** There is no image or video
  rendering yet, so the wall can prove its geometry but cannot yet show
  anything you would want to look at.
- **The aspect ratio compares against what the tablet reports.** The client
  reports its viewport and re-registers when that changes, and the controller
  warns when a placement's visible rect disagrees. When they do disagree the
  client still renders, covering and cropping rather than distorting — so a
  mismatch degrades the seam instead of breaking it. Pixel-perfect seams are
  not achievable from a browser without kiosk-mode control.
- **No authentication.** Anyone who can reach the server can register a device,
  read the roster, or repaint the wall.
- **A device must register before it can open a socket.** A socket for an
  unregistered id is closed with `4404` rather than registering on the fly, so
  registration stays the single source of device metadata.
- **`last_seen` is not pushed while a device is healthy.** It only reaches
  controllers when something changes, so a controller must render an online
  device as live rather than counting up a stale timestamp. See
  [PROTOCOL.md](PROTOCOL.md).
- **Frontend changes may need a hard refresh.** The static mounts send no
  `Cache-Control`, so browsers heuristically cache `client.js` and
  `controller.js`. `fastapi dev` reloads the server, not the browser.
- **The app must run from the repository root.** The static mounts use relative
  paths (`StaticFiles(directory="frontend/client")`), so importing `main` from
  any other directory raises `RuntimeError: Directory 'frontend/client' does not
  exist`. The `make` targets handle this for you.
- **One socket per device, none for controllers.** A second socket for the same
  device id silently replaces the first, so two browser tabs on one origin share
  a single identity. Controller sockets have no heartbeat, so one that vanishes
  without a clean close is only reaped when a later broadcast to it fails.
- **`device_type` is hardcoded to `"ipad"`, and `window.screen.width/height`
  reports screen CSS pixels rather than the viewport.** Wall geometry is
  Phase 2 work.
- **The server has no wake-lock story.** A tablet's screen will still sleep;
  that needs either kiosk software or HTTPS plus the Screen Wake Lock API.

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

**Phase 2 — a coherent wall of still images**

*Definition of done: a curated still image displays as one coherent wall, and
the operator can save and recover its arrangement and presentation.*

- [x] Protocol v2: version negotiation and capability advertisement
- [x] Wall coordinate space, placements, and bezel insets
- [x] Controller: wall panel, placement editing, wall map, auto-arrange
- [x] Client: calibration rendering with a verified seam
- [x] Separate layout from scene; add the generation reset rule
- [x] Persist the active layout and scene (SQLite)
- [ ] **2a** Integrity: removable vacant reservations, persist-before-apply, honest controller content states
- [ ] **2b** Curated assets and the still-image wall
- [ ] **2c** Named save/recall — closes Phase 2

Clock sync and video are **not** Phase 2. A still image needs no shared playback
clock, and clock sync without a timed medium is cost with no visible capability.

**Phase 3 — safe, unattended operation**

- [ ] **3a** Trust boundary: authenticate controller mutations and the controller socket; device identity and pairing
- [ ] **3b** HTTPS, deployment service, kiosk/fullscreen guidance, backups
- [ ] **3c** Operational resilience: structured logs, health/readiness, asset-error states, soak tests
- [ ] **3d** Engineering gate: ruff, targeted mypy, CI (basic CI starts in 2a)

**Phase 4 — timed media, only if validated**

- [ ] Prototype real-tablet video decoding and synchronisation, then design clock estimation, scheduled starts, drift correction, and buffering fallback. Proceed only if that prototype shows acceptable seams.

---

**There is no AI capability, and none is planned.** The project name is
`tablet-wall-ai` for historical reasons; nothing in it uses a model, and no
schema or roadmap space is reserved on the assumption that something will.
