# tablet-wall-ai

Turn a set of tablets into one coordinated display wall.

Each tablet opens the **client** page and registers itself with the server. A
**controller** page watches the roster of connected devices and, eventually,
drives what they show.

This project began as a copy of `tablet-wall`. New development happens here.

> **Status: early skeleton.** Device registration works end to end. The
> controller has no UI yet and no content can be pushed to a tablet. See
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
main.py                     FastAPI app: API routes + static mounts
frontend/
  client/                   runs on each tablet; self-registers
    index.html  client.js  client.css
  controller/               operator page; currently console-only
    index.html  controller.js  controller.css
tests/                      pytest contract tests for the HTTP API
pyproject.toml              deps, dev deps, pytest config
```

## How it works

1. On load, `frontend/client/client.js` reads a device UUID from
   `localStorage`, generating and storing one on first visit. The UUID is the
   tablet's stable identity across reloads.
2. The client `POST`s that UUID plus `window.screen.width/height` and a
   hardcoded `device_type` to `/devices/register`.
3. The server stores the device in an in-memory dict, stamped with a UTC
   `last_seen`.
4. `frontend/controller/controller.js` polls `GET /devices` once a second and
   logs the roster to the browser console.

The server keeps all state in the `devices` dict in `main.py`, so the roster is
lost on restart and is per-process.

## HTTP API

| Method | Path                        | Purpose                                     |
| ------ | --------------------------- | ------------------------------------------- |
| `GET`  | `/`                         | Liveness greeting                           |
| `GET`  | `/devices`                  | Full device roster                          |
| `GET`  | `/devices/register`         | Hint that registration is a `POST`          |
| `POST` | `/devices/register`         | Register/refresh a device                   |
| `GET`  | `/device/{device_id}`       | **Stub** — echoes the id, does not look up  |
| `POST` | `/devices/{device_id}/color`| **Stub** — no-op, returns `null`            |
| `GET`  | `/docs`                     | Interactive OpenAPI docs                    |

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
`httpx2`, which is what Starlette now expects) and covers the root route, both
static mounts, and the registration contract including validation failures.

The two placeholder endpoints are deliberately left untested — pinning their
current output would enshrine placeholder behaviour.

## Known limitations

**The client cannot register from a tablet on a plain-HTTP LAN origin.**
`client.js` calls `crypto.randomUUID()`, which browsers expose only in a
[secure context](https://developer.mozilla.org/en-US/docs/Web/API/Crypto/randomUUID)
— HTTPS or localhost. On `http://192.168.1.50:8000/client/` the call throws
`crypto.randomUUID is not a function` inside an async IIFE, so it surfaces only
as an unhandled rejection in the console and the tablet silently never
registers. Fixing this (a `getRandomValues` fallback, or serving HTTPS) is the
first thing to do before real hardware.

Other gaps:

- **`last_seen` is written once and never updated.** There is no heartbeat,
  expiry, or deregistration, so a dead tablet stays in the roster forever and
  the field really means "first seen". The controller cannot distinguish a live
  wall from a stale one.
- **The app must run from the repository root.** The static mounts use
  relative paths (`StaticFiles(directory="frontend/client")`), so importing
  `main` from any other directory raises `RuntimeError: Directory
  'frontend/client' does not exist`. The `make` targets handle this for you.
- **The controller has no UI.** It logs to the console; both stylesheets are
  empty.
- **No authentication.** Anyone who can reach the server can register or read
  the roster.
- **No persistence.** Restarting the server forgets every device.
- **No realtime channel.** The controller polls at 1 Hz, so pushing a command
  to a tablet is not possible yet.
- **No reconnect handling.** If the server is briefly unavailable the client
  throws and never retries.
- `device_type` is hardcoded to `"ipad"`, and `window.screen.width/height`
  reports screen CSS pixels rather than the viewport.

## Roadmap

**Phase 0 — hygiene** ✅ *done*

- [x] Commit the app and frontend (previously untracked)
- [x] Add this README
- [x] Add a dev script (`Makefile`)
- [x] Add pytest scaffolding and contract tests

**Phase 1 — close the core loop**

- [ ] Fix the secure-context `crypto.randomUUID()` failure (or serve HTTPS)
- [ ] Replace polling with a WebSocket channel for clients and controller
- [ ] Build the controller UI: device tiles with status and last-seen
- [ ] Implement `POST /devices/{device_id}/color` end to end
- [ ] Add heartbeats, expiry, and deregistration so `last_seen` is honest
- [ ] Add reconnect with backoff to `client.js`

**Phase 2 — make it a wall**

- [ ] Assign each tablet a grid position from the controller
- [ ] Sync shared content across tablets (the actual video-wall effect)
- [ ] Server-time clock sync so playback lines up
- [ ] Bezel compensation for physical gaps
- [ ] Save and recall layouts/scenes

**Phase 3 — ops**

- [ ] Persist the roster (SQLite)
- [ ] Controller auth token
- [ ] HTTPS, systemd unit, structured logging
- [ ] Kiosk-mode setup docs (Guided Access / Fully Kiosk Browser)
- [ ] ruff + mypy + CI
