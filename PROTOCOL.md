# tablet-wall-ai realtime protocol

The contract between the server, the tablet **client**, and the **controller**.
This is the authoritative interface description; code in `main.py`,
`frontend/client/`, and `frontend/controller/` must match it exactly.

## Transports

| Endpoint                            | Who connects  | Purpose              |
| ----------------------------------- | ------------- | -------------------- |
| `GET /ws/device?device_id=<uuid4>`  | tablet client | liveness + commands  |
| `GET /ws/controller`                | controller    | roster events        |

Commands travel over **HTTP**. Events travel over **WebSocket**. The controller
never sends anything meaningful up its socket; it listens.

## Timing constants

| Name                   | Value | Meaning                                     |
| ---------------------- | ----- | ------------------------------------------- |
| `HEARTBEAT_INTERVAL_MS`| 5000  | The client sends a heartbeat this often.    |
| `HEARTBEAT_TIMEOUT_S`  | 15    | No heartbeat for this long ⇒ device is dead.|
| `SWEEP_INTERVAL_S`     | 2     | How often the server checks for dead devices.|

A device is `online` **iff** it holds an open device socket that has not
exceeded `HEARTBEAT_TIMEOUT_S` since its last heartbeat, connect, or
registration.

## Device lifecycle

```
unknown ──POST /devices/register──▶ registered, offline
registered, offline ──WS open──▶ online
online ──heartbeat──▶ last_seen refreshed
online ──no heartbeat for 15s──▶ socket closed (4408), offline
online ──socket closes (any reason)──▶ offline
any ──DELETE /devices/{device_id}──▶ removed from roster
```

Disconnecting **never** removes a device from the roster — it only flips
`online` to `false`. Only `DELETE` removes it.

The client re-registers before *every* connection attempt, because server state
is in memory and may be lost to a restart.

## Device record

Every payload that carries a device uses this exact shape:

```json
{
  "device_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
  "width": 1024,
  "height": 768,
  "type": "ipad",
  "color": "#3b82f6",
  "online": false,
  "last_seen": "2026-09-24T21:38:59.231663+00:00"
}
```

- `type` is the key name — **not** `device_type`. Existing tests depend on this.
- `color` is `#rrggbb` lowercase, or `null` if never set.
- `online` is a boolean.
- `last_seen` is ISO-8601 UTC with an explicit `+00:00` offset.
- `device_id` is a lowercase UUID4 string.

## Messages

All frames are JSON text frames with a discriminating `type` key.

### Server → device

```json
{ "type": "welcome", "device_id": "<uuid>", "heartbeat_interval_ms": 5000 }
{ "type": "set_color", "color": "#3b82f6" }
```

`welcome` is the first frame after the socket opens. If a color was already
assigned, the server sends `set_color` immediately after `welcome` so a
reconnecting tablet restores its appearance.

### Device → server

```json
{ "type": "heartbeat" }
```

Unrecognised frames are ignored, not fatal.

### Server → controller

```json
{ "type": "snapshot", "devices": [ <device record>, ... ] }
{ "type": "device_online", "device": <device record> }
{ "type": "device_offline", "device_id": "<uuid>", "last_seen": "<iso>" }
{ "type": "device_updated", "device": <device record> }
{ "type": "device_removed", "device_id": "<uuid>" }
```

- `snapshot` is the first frame on connect and is the full roster, as a **list**.
- `device_online` fires when a device socket opens, including when a new socket
  replaces an older one for the same id.
- `device_offline` fires when a device socket closes or times out. It means
  "the socket is gone", not "forget this device" — the roster entry survives.
- `device_updated` fires when metadata changes or `color` changes. Registration
  always broadcasts it, including a first-time registration, since there is no
  separate "device added" event.
- `device_removed` fires when a device is deleted from the roster. It means
  "drop this tile". Controllers that did not issue the `DELETE` rely on it;
  `device_offline` alone would leave them rendering a device that no longer
  exists.

### A note on `last_seen`

`last_seen` is only pushed to controllers when something changes — a device
that is quietly heartbeating does **not** refresh the value the controller
holds. A controller must therefore not render a ticking "last seen" for an
online device: it would drift upwards and eventually claim a live tablet had
been gone for minutes. Report an online device as live, and reserve the
relative `last_seen` for devices that are actually offline.

## WebSocket close codes

| Code | When                                                        |
| ---- | ----------------------------------------------------------- |
| 4400 | `device_id` query param missing or not a valid UUID4.        |
| 4404 | `device_id` is valid but the device has not been registered. |
| 4408 | Server closing the socket after a heartbeat timeout.         |
| 4409 | Replaced: a newer socket opened for the same `device_id`.    |

One socket per device: a second connection for the same id replaces the first,
which is closed with 4409 and does **not** broadcast `device_offline`. The
replacement stays connected and keeps the device online.

**These codes are sent after the handshake completes**, not by rejecting it. A
server that refuses the upgrade gives the browser nothing but a generic `1006`,
so the client could never tell a bad id from a dead server. The server
therefore accepts, then closes with the real code. Verified against a real
WebSocket client: 4400, 4404, and 4409 all arrive as observable close codes.

## HTTP commands

### `GET /devices`

Returns the roster keyed by device id:

```json
{ "<device_id>": <device record>, ... }
```

### `GET /device/{device_id}`

Returns a single device record. `404` if unknown.

### `POST /devices/register`

Unchanged request body:

```json
{ "device_id": "<uuid4>", "width": 1024, "height": 768, "device_type": "ipad" }
```

Response is unchanged: `{"registered": true, "device": "<device_id>"}`.

Re-registering an existing id updates `width`, `height`, `type`, and
`last_seen`, preserves any assigned `color` and an open socket, and broadcasts
`device_updated`.

### `POST /devices/{device_id}/color`

```json
{ "color": "#3b82f6" }
```

- `200` → `{"device_id": "...", "color": "#3b82f6", "delivered": true}`
  where `delivered` reports whether a live device socket received it.
- The color is persisted even when `delivered` is `false`, so it applies when
  the tablet reconnects.
- `404` if the device is unknown.
- `422` if `color` is not `#rrggbb` (6 hex digits, optional `#`, case-insensitive
  on input, normalised to lowercase).

### `POST /devices/color`

Applies one color to every known device.

- `200` → `{"color": "#3b82f6", "updated": 3, "delivered": 2}`
- `422` if `color` is malformed.
- With an empty roster: `{"color": "...", "updated": 0, "delivered": 0}`.

### `DELETE /devices/{device_id}`

Removes a device from the roster and closes its socket with `1000` if open.
Broadcasts `device_offline` (only when a socket was actually closed) followed
by `device_removed`.

- `200` → `{"removed": true, "device_id": "..."}`
- `404` if the device is unknown.

### Ids and status codes

HTTP routes take the id as a plain string and parse it themselves. A malformed
id and an unknown-but-well-formed id are both `404`: neither refers to a device
that exists. `422` is reserved for a well-formed request whose *body* is
invalid, such as a malformed colour.

## Concurrency rules

The server runs on a single asyncio event loop. Requirements:

- Never `await` in the middle of mutating shared state.
- When broadcasting, iterate over a **copy** of the socket collection.
- Wrap each individual send in `try/except`; a send to a closing socket raises,
  and that socket must be dropped without aborting the rest of the broadcast.
- The heartbeat sweeper runs as a background task started on app startup and
  cancelled on shutdown.
