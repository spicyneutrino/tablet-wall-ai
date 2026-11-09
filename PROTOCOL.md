# tablet-wall-ai realtime protocol

The contract between the server, the tablet **client**, and the **controller**.
This is the authoritative interface description; code in `main.py`,
`tabletwall/`, `frontend/client/`, and `frontend/controller/` must match it.

## Transports

| Endpoint                                             | Who connects  | Purpose              |
| ---------------------------------------------------- | ------------- | -------------------- |
| `GET /ws/device?device_id=<uuid4>&protocol=2&caps=…`  | tablet client | liveness + commands  |
| `GET /ws/controller?protocol=2`                       | controller    | roster events        |

Commands travel over **HTTP**. Events travel over **WebSocket**. The controller
never sends anything meaningful up its socket; it listens.

## Protocol versions

The socket carries a major protocol version so the contract can change without
stranding a tablet that is already mounted on a wall.

| Where              | How                                                        |
| ------------------ | ---------------------------------------------------------- |
| Device → server    | `protocol` query param, plus `caps` (comma-separated).      |
| Controller → server| `protocol` query param.                                     |
| Server → v2 device | `protocol` and `server_caps` in the `welcome` frame.        |

- **Absent `protocol` means version 1.** A cached `client.js` that predates the
  version param keeps working exactly as it did.
- Supported majors: **1** and **2**.
- An unsupported major is closed with **4426** *after* the handshake, so the
  client can see the code. A version-1 device is never sent a version-2 frame.
- `caps` advertises what a client can *render* (`calibration` and `image`;
  timed media is future work). The server must not send content a client has
  not advertised. Caps are advisory, so a hostile query is trimmed rather than
  rejected: entries longer than 32 characters are dropped, duplicates are
  removed, and at most 32 are kept. The whole query string is capped at 2048
  characters by the HTTP layer.

Version 1 is the colour-only contract as originally specified. Everything in the
"Wall, placements, and scenes" section below is version 2.


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
is persisted as safe device metadata, but live presence always resets to offline after restart.

## Device record

Every payload that carries a device uses this exact shape:

```json
{
  "device_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
  "width": 1024,
  "height": 768,
  "type": "ipad",
  "color": "#3b82f6",
  "protocol": 2,
  "caps": ["calibration", "image"],
  "number": 1,
  "online": false,
  "last_seen": "2026-09-24T21:38:59.231663+00:00"
}
```

- `type` is the key name — **not** `device_type`. Existing tests depend on this.
- `color` is `#rrggbb` lowercase, or `null` if never set.
- `online` is a boolean.
- `last_seen` is ISO-8601 UTC with an explicit `+00:00` offset.
- `device_id` is a lowercase UUID4 string.
- `number` is the small display number shown in the controller and on the
  calibration screen. It is not identity. The server allocates the lowest free
  positive integer and leases it while the tablet stays in contact. A tablet
  that is offline for 15 minutes releases the number for a replacement.
  A returning client may include its previous `number` in
  `POST /devices/register`; the server honours it only while it is free.
  Numbers are process-local, so a client that does not ask, or asks for a
  taken number, receives the lowest free one.
- `protocol` is the last negotiated major (or `null` before a socket connects);
  `caps` is the list advertised by that socket (empty until then). A version-1
  socket does not receive `wall` frames even if it supplies a `caps` query
  parameter; image support requires protocol 2 or 3 and the `image` cap.

## Messages

All frames are JSON text frames with a discriminating `type` key.

### Server → device

```json
{ "type": "welcome", "device_id": "<uuid>", "heartbeat_interval_ms": 5000, "protocol": 3, "server_caps": [], "number": 1 }
{ "type": "set_color", "color": "#3b82f6" }
```

`welcome` is the first frame after the socket opens. If a color was already
assigned, the server sends `set_color` immediately after `welcome` so a
reconnecting tablet restores its appearance. The `protocol`, `server_caps`,
and `number` keys are present for protocol 2 and 3 only; the protocol-1
welcome is unchanged.

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

A client that receives 4409 stops its reconnect loop and shows a takeover
control instead. Retrying on a timer would take the slot straight back and
produce an endless replacement storm between two pages that share the identity.
The client resumes only on an explicit action, which replaces the other page in
turn.

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

Request body:

```json
{ "device_id": "<uuid4>", "width": 1024, "height": 768, "device_type": "ipad", "number": 3 }
```

`number` is optional. A returning client sends the number it held before a
server restart; the server keeps it only while it is free.

Response is unchanged: `{"registered": true, "device": "<device_id>"}`.

When optional authentication is disabled this is a public write, so every field is bounded before the
record enters memory:

| Field         | Bound                                            | `422` when |
| ------------- | ------------------------------------------------ | ---------- |
| `device_id`   | UUID4                                            | not a UUID4 |
| `width`       | `1 … 16384`                                      | outside that range |
| `height`      | `1 … 16384`                                      | outside that range |
| `device_type` | `1 … 32` characters, printable ASCII (`0x20–0x7e`) | empty, longer, or any other character |
| `number`      | `1 … 512` (optional)                             | outside that range |

The roster holds `512` records. A registration that would exceed it evicts the
least recently contacted **offline** device; placements are stored separately
and survive as reservations. If every record is online the server answers
`429` instead of evicting a live tablet.

Re-registering an existing id updates `width`, `height`, `type`, and
`last_seen`, preserves any assigned `color`, `number`, and an open socket, and
broadcasts `device_updated`.

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

Removes the roster identity and its active placement or slot, preserves saved
layout references, and broadcasts `device_removed`. Playback is aborted.
Requires `If-Match` with the current `GET /api/v3/config` ETag. An invalid or
unknown identity returns `404` before the guard. For a known identity, a
missing guard returns `428`, and a stale guard returns `412` before lifecycle
validation and commit.

- `200` → `{"removed": true, "device_id": "..."}`
- `404` if the device is unknown.

### `POST /devices/{device_id}/rebind`

The path identifies the registered new device. The JSON body is
`{"replaces":"<old UUID4>","number":1}`. `number` is optional and must be
between 1 and the server device limit. The command assumes the same hardware,
transfers the label and active arrangement, and leaves saved layouts unchanged.
It uses the new device's current connection identity internally.

Requires the current config `If-Match`. Framework body validation can return
`422` before the handler. Once the body is valid, a malformed or unknown new
path identity returns `404` before the ETag check. For a known new identity,
missing `If-Match` returns `428`, and a stale value returns `412` before
lifecycle validation. Old-identity and live-connection conflicts are evaluated
after that guard. Do not infer `409` precedence from an old device being live.
The workspace v3 preview supports explicit hardware choice and saved-layout
selection. This legacy request does not have those fields.

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

---

# Version 2 — wall, placements, and scenes

Everything below requires `protocol=2`. Version 1 clients are unaffected.

## Wall coordinate space

The wall is one logical canvas measured in **abstract units**, not pixels.
`wall.width` and `wall.height` are integers in those units; the operator picks
them (a 2×1 wall of landscape panels might be `2000×1000`).

Wall units are deliberately **not** physical millimetres. Panel sizes, browser
chrome, and zoom all make physical measurement unreliable from a browser.
Abstract units keep layouts portable and cheap to change.

A **placement** gives one device a rectangle on that canvas:

```json
{
  "device_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
  "x": 0, "y": 0, "w": 1000, "h": 1000,
  "bezel": { "top": 0, "right": 0, "bottom": 0, "left": 0 }
}
```

`x`/`y`/`w`/`h` are the panel's **full footprint** on the wall, including the
part hidden behind its frame. `bezel` is how much of each edge the frame covers,
in the same units. The **visible rect** is the footprint shrunk by the bezel:

```
visible = { x: x + bezel.left,
            y: y + bezel.top,
            w: w - bezel.left - bezel.right,
            h: h - bezel.top  - bezel.bottom }
```

The client maps its **visible rect** onto its own viewport. Content behind a
bezel is simply not rendered — that is what makes a wall of framed tablets read
as one image. Bezel values must leave a positive visible rect, or the placement
is invalid (`422`).

### Aspect and seam caveats

A client fills its viewport with its visible rect by **covering** — scaling so
the rect covers the viewport and cropping the overflow **equally on all sides**:
the rect's centre is kept at the viewport's centre, so a device whose aspect
differs still shows the middle of its slice and the cropped band is split
across its seams. Seams line up when each placement's visible rect has the same
aspect ratio as that device's reported viewport. When they differ the device
still renders, but the image is cropped inconsistently.

The controller surfaces that mismatch rather than hiding it. Pixel-perfect
seams are **not** achievable from a browser without kiosk/fullscreen control and
a calibration pass; treat this as "good enough to look aligned", not "lab grade".

## Wall state

The wall's state is three things, kept separate on purpose: an **arrangement**,
what is **being shown**, and an **ordering token**. Fusing them would make a
saved layout carry content with it, and make "recall this scene" ambiguous
about which arrangement it meant.

### Layout

| Field        | Type                     | Meaning                                  |
| ------------ | ------------------------ | ---------------------------------------- |
| `width`      | int > 0                  | Wall width in units.                     |
| `height`     | int > 0                  | Wall height in units.                    |
| `placements` | `{device_id: placement}` | Sparse — a device may have no placement. |
| `sizing` | optional `{mode, padding}` | `mode` is `fixed` or `tablets`; omitted means legacy fixed sizing. Padding is a nonnegative whole number of wall units. |

In `tablets` mode, every layout commit fits the wall around all stored
placement footprints, including offline and vacant reservations. Placements
are translated together so their minimum X and Y equal `padding`; sizes,
bezels, and relative distances are preserved. Width and height enclose those
footprints plus padding on both sides. An empty layout retains its last
dimensions. Connections and disconnections do not resize the wall.

### Scene

| Field     | Type           | Meaning                                          |
| --------- | -------------- | ------------------------------------------------ |
| `content` | content object | What tablets are asked to render.                |
| `layout`  | `"active"`     | Reference to the layout in use. Named saved layouts are snapshots, not alternate active-layout references. |

**Recall semantics.** A saved
scene recalls its *content* onto whatever layout is currently **active**. It
never silently replaces the arrangement — recalling a scene must not throw away
placement work the operator did afterwards. Restoring content *and* arrangement
together is a different, separately named action (a preset), not an overload of
"recall scene".

### Named snapshots (Phase 2c)

Layouts and scenes have **separate name spaces**. A saved layout contains
`{ "width", "height", "placements" }`, plus `sizing` when configured (including reservations whose tablets
are absent from the roster), never content. A saved scene contains `content`
only, never placements or a stored URL; its image asset ID, fit and derived
dimensions remain durable even when the curated file is removed. Snapshot
names are trimmed, case-sensitive ASCII strings of 1–64 characters: they must
start with a letter or digit and the rest may contain letters, digits, spaces,
`.`, `_`, or `-`.

Saving and deleting a snapshot do **not** change the active wall, its revision,
or its subscribers. Recall atomically changes one part of the active wall:
layout recall replaces dimensions and all placements but preserves scene;
scene recall replaces only content on the current active layout. Both bump
revision once, persist before the live mutation/broadcast, and retain the
current generation. A missing image asset does **not** block scene recall:
the image scene stays explicit and capable tablets show an error until its
original bytes return or the operator selects other content.

`content` is discriminated by `type`:

| `type`          | Extra fields                                                | Meaning |
| --------------- | ----------------------------------------------------------- | ------- |
| `"color"`       | —                                                            | Version-1 behaviour: each tablet shows its assigned colour. |
| `"calibration"` | —                                                            | Each placed tablet renders its slice of the calibration pattern, which is how the operator checks the geometry. |
| `"image"`       | `asset`, `fit`, `intrinsicWidth`, `intrinsicHeight`          | Curated still image, fitted across the entire wall. The server adds `url` only to the wire descriptor; it is never stored. |

### Revision and generation

| Field        | Type   | Meaning                                              |
| ------------ | ------ | ---------------------------------------------------- |
| `revision`   | int    | Monotonic. Bumped on every accepted change to layout or scene. |
| `generation` | string | Identifies this server's state lineage.              |

`revision` is monotonic **within a generation**. A client that receives a
revision not newer than the one it holds **must ignore it** — that is what
makes reconnect and replay safe.

It must ignore it **only when the generation matches**. Persistence means a
server can come back holding a *lower* revision than a tablet is holding: a
restore from backup, a rollback, a wiped database. If the client kept refusing
those frames, a tablet that had seen revision 12 would reject a freshly
restored server at revision 0 forever.

**The generation is therefore regenerated on every server start**, and the
revision is persisted and continues climbing. That makes the reset
unconditional rather than something the server has to detect: after any
restart — ordinary, restored, or rolled back — a client accepts the first frame
it sees and resets its held revision. (Detecting "did I write this state
myself?" reliably is not possible from inside the database alone, and getting
it wrong means a wall that never resynchronises.)

An unplaced device in `calibration` content renders its device id and a note
that it has no placement. In `color` content it keeps rendering its assigned
colour, as version 1 did — an unplaced tablet is still a tablet, and the
controller's wall map already reports how many are unplaced.

## Messages

### Server → device (v2 additions)

```json
{ "type": "welcome", "device_id": "<uuid>", "heartbeat_interval_ms": 5000,
  "protocol": 2, "server_caps": ["calibration", "image"] }

{ "type": "wall", "revision": 7, "generation": "5c1f9a2e",
  "wall": { "width": 2000, "height": 1000 },
  "scene": { "content": { "type": "calibration" }, "layout": "active" },
  "placement": { "x": 0, "y": 0, "w": 1000, "h": 1000,
                 "bezel": { "top": 0, "right": 0, "bottom": 0, "left": 0 } } }
```

`placement` is `null` when this device is not placed. The frame carries
everything this tablet needs to render — the wall's dimensions, its own
placement, and the content — so it is the *complete presentation* for that
device, not a delta. It is sent after `welcome`, and again on every change,
including on reconnect, so a tablet always restores the current wall without
being told again.

### Server → controller (v2 additions)

```json
{ "type": "snapshot", "devices": [ … ], "wall": { … } }
{ "type": "wall_updated", "wall": { … } }
```

`wall` carries the full state: the layout fields, `scene`, `revision`, and
`generation`.

## HTTP (v2 additions)

### `GET /wall`

The whole state in one read, which is what the controller needs:

```json
{ "width": 2000, "height": 1000,
  "revision": 3, "generation": "5c1f9a2e",
  "placements": { … },
  "scene": { "content": { "type": "color" }, "layout": "active" } }
```

### `PUT /wall`

Layout only. Body may set `width`, `height`, or
`sizing: {"mode":"fixed"|"tablets", "padding":0}`. Padding defaults to zero.
`200` returns the new wall state. `422` if dimensions or sizing are invalid.
Explicit dimensions return `409` while tablet sizing remains selected; send
`sizing.mode: "fixed"` in the same request to resume manual dimensions.
Omitting `sizing` preserves the current mode.
The equal-cell `POST /wall/auto` action also requires fixed sizing (`409`
otherwise); tablet-fit packing preserves the existing footprint sizes.

### `POST /wall/pack`

Body is `{"columns": N, "gap": 0}`. Columns defaults to the number of placed
tablets. Columns must be a positive integer and gap a nonnegative integer.
The route requires tablet sizing mode (`409` otherwise) and at least one
placement (`422` otherwise). It packs all stored footprints in visual order,
top to bottom then left to right, into rows. Footprint sizes and bezels are
preserved. Packing and refitting are one persisted revision and broadcast;
the response is the complete wall state. Unplaced tablets are not added.

### `PUT /scene`

Content only. Body is `{ "content": { "type": … } }`. For an image, send
`{ "content": { "type": "image", "asset": "sha256:<64 lowercase hex digits>",
"fit": "cover" } }`; `fit` accepts `cover` or `contain`; omitted fit defaults to `cover`. The server
looks up the asset and derives its intrinsic dimensions. It persists the ID,
fit and derived dimensions, but not a URL. `200` returns the new wall state;
`422` for an unknown type, invalid/missing asset, unsupported fit, or unknown
fields (including caller-supplied `url` or dimensions).

### Saved layouts and scenes

The server snapshots its **own current active wall**; save requests do not
accept arbitrary layout/content bodies. URL path names must be encoded as a
single path component. All routes use trimmed, case-sensitive names as above;
invalid names return `422`, absent names on recall/delete return `404`.
If a stored snapshot is malformed (for example, a damaged/hand-edited SQLite
row), recall returns `409` **before** changing the active wall. This is
different from an otherwise valid image scene whose asset bytes are missing:
that recall succeeds and the tablet reports the missing image.

| Route | Result |
| ----- | ------ |
| `GET /layouts` | `{ "layouts": [{ "name": "Lobby", "layout": { "width": 2000, "height": 1000, "placements": {} } }] }` |
| `PUT /layouts/{name}` | Save the active layout. `200 { "saved": true, "name": "Lobby" }`; an existing name returns `409` unless `?replace=true` is explicit. |
| `POST /layouts/{name}/recall` | Apply its layout to the active wall; `200` returns full `GET /wall` shape. |
| `DELETE /layouts/{name}` | Remove only this named snapshot; `200 { "deleted": true, "name": "Lobby" }`. |
| `GET /scenes` | `{ "scenes": [{ "name": "Opening", "content": { "type": "color" } }] }` |
| `PUT /scenes/{name}` | Save active scene content. `200 { "saved": true, "name": "Opening" }`; `409` unless `?replace=true` for an existing name. |
| `POST /scenes/{name}/recall` | Apply its content to the active wall without changing placements; `200` returns full `GET /wall` shape. |
| `DELETE /scenes/{name}` | Remove only this named snapshot; `200 { "deleted": true, "name": "Opening" }`. |

Only an **explicit, confirmed** replacement in the controller sends
`?replace=true`. The two snapshot collections are separate SQLite tables
added alongside the existing active-wall row on first open, with no destructive
migration; they survive restarts. A combined layout+scene preset is not part of
this protocol.

If a saved row is damaged, the corresponding list still returns the other
snapshots and includes `{ "name": "…", "layout": null, "invalid": true }`
(or `"content": null` for a scene) for that row. It remains visible so the
operator can delete or explicitly replace it; recalling it returns `409`.

### `PUT /devices/{device_id}/placement`

```json
{ "x": 0, "y": 0, "w": 1000, "h": 1000,
  "bezel": { "top": 0, "right": 0, "bottom": 0, "left": 0 } }
```

`bezel` may be omitted and defaults to zero on every edge. `404` if the device
is unknown; `422` if the rect is degenerate or the bezel leaves no visible area.
The device keeps its placement across a reconnect.

### `DELETE /devices/{device_id}/placement`

Clears the placement and returns the new wall state.

- `200` when a placement was removed.
- `200` when the device is known and had no placement — nothing to do.
- `404` when there is neither a known device nor a placement to remove.

**A placement can outlive the roster.** Placements and safe device metadata are persisted. A placement can still refer to a deleted or absent device. Online presence is not persisted, so after a restart a placement may belong to an offline device that has not yet re-registered. That is a **reservation, not a leak**: a tablet that comes back
reclaims its slot, which is the whole point of persisting placements. It is
removable either by that device returning, or by the operator releasing it
explicitly through this endpoint — which is why a valid id with a placement
must not `404` merely because the roster has forgotten the device.

The controller labels a placement whose device is absent from the roster as
**vacant** and offers a release action, so a stale reservation is visible
rather than silently reserving wall space forever.

`POST /wall/auto` does **not** prune reservations. Auto-arranging must not
silently destroy a slot a tablet is expected to return to; releasing a vacant
slot is an explicit, separate action.

An auto-arrange request that would make an online tablet overlap an offline or
roster-absent reservation must fail with `409` and leave the entire active wall
unchanged. The operator can release or move the conflicting reservations, then
retry. A rejected request never silently overlays saved space.

### Unknown keys

`PUT /wall` and `PUT /scene` reject unknown keys with `422`, including inside
the `content` object. A client still sending the removed `mode` field gets a
`422` rather than having it quietly ignored, which is the point: silently
accepting it would make every such caller believe a change had been applied.

### Shape and precedence notes

- A placement **stored on the wall** (`GET /wall`, `snapshot.wall`,
  `PUT`/`DELETE` responses) carries `device_id`. The copy sent to the device
  itself in the `wall` frame does not — the device already knows its own id.
- `PUT /wall`, `PUT /devices/{id}/placement`, `DELETE /devices/{id}/placement`
  and `POST /wall/auto` all return the **full wall state**, so a caller never
  has to re-read it to know the new revision.
- Deleting a device with `DELETE /devices/{device_id}` also drops that device's
  placement and bumps the revision, so a removed tablet cannot keep reserving a
  hole on the wall.
- On `/ws/device`, an unsupported `protocol` (**4426**) is decided before
  identity (**4400**/**4404**): negotiation is a transport-level concern and
  applies even to a request whose `device_id` is also wrong.

### `POST /wall/auto`

Body: `{ "columns": 2 }` (optional). When `columns` is omitted the server uses
`max(1, round(sqrt(n)))`, where `n` is the number of **online** devices.

Assigns every **online** device a placement in a regular grid, replacing any
existing placements. Devices that are offline keep whatever they had. Returns
the new wall state. If any proposed cell has a positive-area intersection
with a retained offline or vacant reservation, returns `409` with the
conflicting IDs and **does not** change the wall, revision or broadcasts.
Touching at an edge is not a collision; footprints, not bezel-shrunken visible
rects, are compared.

`columns` must be a positive int; anything else is `422`.
An excessively fine grid that rounds any proposed width or height to zero
also returns `422` without changing the wall.

## Client rendering contract

A version-2 client that advertises `calibration` and/or `image` must:

1. Record the wall state and its placement from the latest `wall` frame. The
   frame is the complete presentation for this device, so there is nothing to
   merge and no delta to accumulate.
2. Ignore a frame whose `revision` is not newer than the one it holds — **unless
   the `generation` differs**, in which case accept it and reset the held
   revision. See "Revision and generation".
3. When `scene.content.type` is `"calibration"`, render the calibration pattern
   for its **visible rect**, mapped onto its viewport by centred covering
   (rect centre to viewport centre).
4. When `scene.content.type` is `"color"`, keep rendering the assigned colour.
5. When it advertises `image` and receives `scene.content.type` `"image"`,
   load the server-supplied same-origin URL, decode it, draw one centered-cover
   image over the **whole logical wall**
   and map only this tablet's visible rect to its viewport with the same
   centred covering. While loading or on
   failure, show an unmistakable diagnostic rather than a blank or silently
   stale surface; ignore a late decode for a superseded generation/revision.
   An unplaced tablet reports `NO PLACEMENT` instead of showing an independent
   image preview.
6. Re-render on viewport resize, since the mapping depends on it.

---

## Still images

- **Assets** are curated files in a server-owned directory, **outside** the
  frontend static mounts (`TABLET_WALL_ASSET_DIR`, default `./assets`). Only
  top-level, regular, non-symlink JPEG and PNG files are inventoried; animated,
  corrupt, misleadingly named, oversized (over 10 MiB or 12 megapixels), and
  rotated-by-EXIF files are rejected. The opaque ID is `sha256:` followed by
  the lowercase SHA-256 of the file bytes: a rename preserves identity, while
  replacing bytes creates a new asset; identical bytes have one identity.
  `GET /assets` lists ID, display name, MIME type, intrinsic dimensions, byte
  size and same-origin URL; `GET /assets/{id}` serves only validated bytes,
  read-only, with no upload or arbitrary path/URL endpoint. Inventory refreshes
  on request. Any client able to reach the LAN server may read these images;
  do not curate sensitive assets until an access boundary exists.
- **Inventory response** is `{ "assets": [{ "id": "sha256:…",
  "name": "Poster.png", "mime": "image/png", "intrinsicWidth": 3840,
  "intrinsicHeight": 2160, "bytes": 2481234,
  "url": "/assets/sha256:…" }] }`. Unknown, removed, or changed IDs
  return `404` from `GET /assets/{id}`. Asset bytes carry the validated
  `Content-Type`, `nosniff`, and an immutable cache policy; inventory must not
  be cached (`Cache-Control: no-store`) because it is a refreshable view. A
  directory that does not yet exist has an empty inventory; an existing
  directory that cannot be scanned fails rather than claiming to be empty.
- **Descriptor** on `GET /wall`, controller frames and capable-device `wall`
  frames is `{ "type": "image", "asset": "sha256:…",
  "url": "/assets/sha256:…", "fit": "cover", "intrinsicWidth": 3840,
  "intrinsicHeight": 2160 }`. The server composes the URL; it is not persisted.
  Derived dimensions stay in the persisted scene so a now-missing asset can
  still be identified and rendered as an explicit failure, not silently
  converted to colour. Both `cover` and `contain` are supported.
- **Fit** is centered once onto the **entire wall**, never independently
  onto each tablet. For image `Iw × Ih` and wall `W × H`, `cover` uses
  `max(W/Iw, H/Ih)` and crops overflow; `contain` uses `min(W/Iw, H/Ih)`
  and preserves the whole image with letterboxing. Both center the scaled
  image. Logical tablets apply the same global rectangle then clip to their
  visible rect. Physical plans use the same fit onto the wall bounds before
  mapping to each panel. Every tablet paints the opaque wall background (`#0b1120`) beneath
  the image, including letterboxes and transparent source pixels. The fit is
  persisted and survives scene recall and restart. Unknown fits are rejected.
- A device that has not advertised the `image` capability receives the **same**
  generation, revision and placement but `scene.content` is rewritten to
  `{ "type": "color" }` in its own `wall` frame, without an asset URL. The
  controller still receives the actual image scene and marks online, placed
  devices lacking the capability as a partial-wall warning; offline and
  unknown-capability reservations are reported separately.
- A missing or undecodable asset must not present as a blank wall: show a
  visible error state on the tablet. The controller can identify a missing
  asset by refreshing its inventory; there is no per-device render-status
  message yet, so it cannot assert that pixels were displayed. The asset ID
  remains in the active scene until an operator explicitly switches or
  replaces the content; inventory changes do not bump the wall revision. If
  the original bytes reappear, retry the load on the device (or reconnect);
  the file returning alone does not push a new wall revision.

## Version 3 — physical render plans

Version 3 is the physical/timed contract. Version 1 and version 2 remain
byte-compatible; a v3 device is never sent a v2 frame, and a v2 device on a
physical wall receives the fixed neutral logical envelope described below.

A v3 device reports its viewport on the socket query string:
`w`, `h`, `dpr`, `orientation` (degrees) and `mode` (`tab`, `fullscreen` or
`standalone`). It may repeat the report at any time:

```json
{ "type": "viewport", "viewport": { "width": 600, "height": 800,
  "dpr": 1.25, "orientation": 0, "mode": "fullscreen" } }
```

The `welcome` for protocol 3 adds `"protocol": 3` and
`"server_caps": ["calibration", "image", "physical"]`. The state frame is
`render`:

```json
{
  "type": "render", "mode": "logical" | "physical",
  "render_seq": 4, "revision": 12, "generation": "a1b2c3d4",
  "wall": { "width": 1200, "height": 800 },
  "scene": { "content": { "type": "image", "asset": "sha256:…",
    "fit": "cover", "intrinsicWidth": 2000, "intrinsicHeight": 1000,
    "url": "/assets/sha256:…" } },
  "slot": { "center_x_mm": 300, "center_y_mm": 400, "mount_angle": 90,
    "nudge_x_mm": 5, "nudge_y_mm": -3, "profile_revision": 1,
    "calibration_revision": 1, "participating": true },
  "calibration": { "status": "valid", "revision": 1,
    "viewport_width": 600, "viewport_height": 800, "quarter_turn": 1,
    "panel_offset_mm": [10, 20], "mm_per_css": [0.1666…, 0.1666…],
    "panel_width": 100, "panel_height": 60 },
  "plan": {
    "panel_from_source": [0, -1600, 800, 0, -350, 537],
    "panel_to_wall": [0, 1, -1, 0, 337, 350],
    "body": { "width": 120, "height": 90 },
    "active": { "x": -47, "y": -32, "width": 100, "height": 60 },
    "clip": { "x": 0, "y": 0, "width": 100, "height": 60 },
    "source": { "width": 2000, "height": 1000 }
  }
}
```

`plan` is `null` when the server cannot make a physical claim. The
`calibration.status` is then `needs_calibration` and `reason` names the
missing or stale prerequisite. A v3 device whose wall is still logical
receives `mode: "logical"` with the v2 `wall` fields and may draw with the
legacy renderer.

### Spaces and transform ownership

Wall `W` is millimetres, X right, Y down. Body `B` is centred on the measured
body in native orientation. Panel `P` starts at the active panel's top-left.
`C` is CSS pixels in the stable render rectangle, `D` canvas backing pixels,
and `N` normalized upright source pixels. Matrices are six-number Canvas
arrays with column vectors, `x' = a*x + c*y + e`; multiplication applies the
rightmost first; positive rotation is clockwise.

The server owns `G_N_to_P = inverse(M_P_to_W) * F_N_to_W` and the panel clip.
The client owns `U_C_to_P = translate(panel offset) * Q(q, wMm, hMm) *
scale(mmPerCss)`, where `Q`'s dimensions are the usable viewport already in
millimetres. The client composes:

```text
D = diag(backingW / rectW, backingH / rectH)
  * inverse(U_C_to_P) * G_N_to_P
  * diag(1 / renditionWidth, 1 / renditionHeight)
```

The panel clip is applied under `backingScale * inverse(U_C_to_P)` before the
image is drawn under `D`. A plan is valid only while the reported viewport,
DPR, orientation and mode match the calibration. Resize, quarter-turn or mode
changes invalidate it immediately; the server sends a new `render` (with a new
`render_seq`) or `plan: null`. The wall revision does not change for a
viewport-only update.

### Schema 2

`schema 2` adds `display_profiles` and `calibrations`, both immutable by
`(device_id, revision)`. Existing logical documents are adapted at read time
and are never rewritten by the migration; new physical layouts are stored as
`{"schema":2,"kind":"physical","bounds":…,"slots":…}`, with optional `sizing`.
Physical sizing uses `fixed` or `tablets` and finite nonnegative padding in
millimetres. Tablet mode encloses every slot's rotated body at `center+nudge`,
including bezels and nonparticipating slots, without translating the slots.
An empty layout keeps its bounds. Computed bounds must remain finite and
positive. Sizing is preserved on restart and named-layout recall; a legacy
snapshot without sizing restores fixed behavior. Physical layout writes that
omit sizing preserve an existing physical sizing configuration.

Configuration responses include `referenced_displays` and
`referenced_calibrations` for physical slots. These carry the exact immutable
revisions used by the layout, even when newer measurements also exist.

The database version is
`PRAGMA user_version`; a future version, a missing required table or a damaged
active wall row refuses startup.

### HTTP configuration API

The integrated still-image operator read model, render acknowledgements,
device lifecycle, grids, ruler review, and readiness routes are specified in
[docs/OPERATOR-PROTOCOL.md](docs/OPERATOR-PROTOCOL.md).

| Route | Meaning |
| --- | --- |
| `GET /api/v3/config` | schema, revision, generation, tagged layout, actual projected scene, displays, calibrations, model assignments and an `ETag` |
| `GET /api/v3/images` | operator-admitted merged curated/managed still-image inventory, including with uploads disabled |
| `PUT /api/v3/scene` | change static content with `If-Match`, stop an experimental presentation, return actual config and ETag |
| `PUT /api/v3/displays/{device_id}` | append a display profile revision |
| `PUT /api/v3/calibrations/{device_id}` | append a calibration for an existing profile revision |
| `PUT /api/v3/layout` | atomically replace the active arrangement with a measured physical layout |
| `PUT /api/v3/logical-layout` | atomically replace a complete logical arrangement: width, height, placements and optional sizing |
| `POST /api/v3/layout/clear` | explicitly clear active entries in the current layout kind; requires `{"confirm":true}` and `If-Match` |

The image inventory response is `{"images":[...]}`. Each row has `id`, `name`,
`width`, `height`, `url`, `thumbnail_url`, and `source` (`curated` or `managed`).
Duplicate content IDs appear once, with managed metadata preferred. Videos and
their poster objects are excluded. Reading this operator inventory does not
enable uploads or expose the inventory on the tablet listener.

For v3 scene writes, send only `{"content":{"type":"image","asset":"sha256:...",
"fit":"cover"}}` (or `contain`). The projected config scene contains derived
`url`, `intrinsicWidth`, and `intrinsicHeight`; these are read-only and must be
removed before constructing an input command. Echoing the projected descriptor
is rejected with `422`. Image resolution can yield to other requests, so the
ETag is checked again immediately before commit. Physical scene readback uses
the actual v3 layout and content, never a synthetic logical colour wall.

Every cross-kind v3 Apply or recall saves the previous complete layout in the
same transaction and returns its name as `previous_layout_saved`. A failed
copy or wall write leaves disk, memory, revision and notifications unchanged.
Default empty Apply refuses to erase a populated wall; the explicit clear
command retains its current kind, bounds and content. Named recall is an
explicit replacement and may restore a saved empty arrangement.

Calibration writes may include `viewport_guard: true`. Guided ruler saves use
this flag to require an online device with matching live CSS dimensions, DPR,
orientation and display mode; an offline or changed viewport returns `409`
without creating a revision. The flag is a command option, not persisted
calibration data. Manual/imported calibration writes retain the default `false`.

Every write requires `If-Match` with the current config ETag: `428` when it is
absent, `412` when it is stale, `409` for a semantic conflict. The check runs
after validation and immediately before the synchronous commit. While a
physical layout is active, legacy layout/placement/auto/layout-save/layout-
recall routes return `409 Upgrade controller`; legacy controllers are closed
with `4426`. A cached logical device receives a neutral logical envelope with
no placement, never physical millimetres.

### Writers

Each connection has one bounded FIFO writer (64 frames, 1 MiB of serialized
frames, 5-second send timeout). Welcome and the initial snapshot are queued
before the socket is published to broadcasts. Overflow or a sustained slow
send closes that connection with `4429`; other connections are unaffected.
R2 does not coalesce frames.

### Clock and hard-cut playback (R3/R4)

A v3 device receives `clock_bootstrap` immediately after `welcome`:

```json
{ "type": "clock_bootstrap", "epoch": "a1b2c3d4", "server_ms": 123456.7 }
```

The client then sends bounded samples and returns the receive time:

```json
{ "type": "clock_sample", "id": "c1", "c0": 1234.5 }
{ "type": "clock_sample", "id": "c1", "c0": 1234.5, "s1": 501111.0, "s2": 501111.2 }
{ "type": "clock_result", "id": "c1", "c3": 1235.2 }
```

`c0`/`c3` are the client's `performance.now()`, `s1` is the server receive time
and `s2` is stamped by the writer immediately before the frame leaves. The
server validates the exchange and keeps the lowest-delay fresh sample;
uncertainty above 25 ms or a sample older than 15 s is not sufficient for
timed readiness. A host suspend changes the epoch, cancels every preparation,
sends `{ "type": "playback", "state": "stopped", "reason": "host suspend" }`
and then the persisted `render` frame.

A saved playlist is one ordered list of published display-object IDs with a
dwell and a loop flag:

```json
GET  /api/v3/playlist        -> { "playlist": {...} | null, "etag": "..." }
PUT  /api/v3/playlist        -> requires If-Match; 1..64 items, 1000..600000 ms
```

A video item's dwell is its published duration, not the request value.
Every accepted `PUT` increments the document's `revision` only after its
`If-Match` matched. A legacy document without a revision is treated as
revision 1, so its first successful save writes 2; a rejected save (`422`,
`428` or `412`) never advances it. A Start freezes the saved revision as the
session's `playlist_revision`, and every occurrence names it.
Playback commands are
`POST /api/v3/playback/{start,pause,stop,next,previous,retry}`. `start` needs a
saved playlist and a physical layout. `policy` is optional: an explicit
`"online"` or `"strict"` wins; otherwise the server resolves `"strict"` when
any playlist item is video and `"online"` for stills. A strict start includes
every participating slot, including offline and protocol-unsupported members;
an online start keeps only online v3 endpoints.

`start` also accepts an optional `exclusions` list of physical slot IDs:
`{ "policy": "strict", "exclusions": ["<uuid>"] }`. Every ID must name a
participating slot in the saved layout; an unknown, duplicate or
non-participating ID is `422`. The session freezes three sets: `required` is
every participating slot, `excluded` is the operator's session-only choice,
and `cohort` is the effective participant set. For strict, `cohort` is
`required - excluded`; for online it is the online v3 endpoints in
`required - excluded`. An all-excluded effective cohort is `409`. Excluded
slots are not counted as synchronized participants: they receive no
preparation, and each reachable excluded socket receives one isolated
`playback` stopped frame with reason `"excluded"` so it shows the persisted
scene. Strict readiness
uses `cohort` only; the physical content bounds and each remaining member's
plan are unchanged. `start` on a paused
session resumes the displayed item at a new anchor and keeps the frozen
`required`, `excluded` and `cohort` selection. `pause/stop/next/previous/retry`
require `If-Match` with the current session version (`428` missing, `412`
stale, `404` no session).

A preparation is one occurrence `{playlist_revision, item_index, loop}` with a
preparation ID, its own version, the exact asset and physical plan, a deadline
and a per-device lease. Frames:

```json
{ "type": "prepare", "session_id": "…", "version": 3, "clock_epoch": "…",
  "preparation_id": "…", "occurrence": {...}, "asset": {...},
  "plan": {...}, "calibration": {...},
  "prepare_deadline_ms": 123, "effective_server_ms": 456,
  "connection_id": "…", "cohort": ["<uuid>"], "media": {...} }

{ "type": "ready", "preparation_id": "…", "version": 3,
  "connection_id": "…", "occurrence": {...}, "evidence_seq": 1,
  "mapping_revision": 1, "decoded": true }

{ "type": "commit", "session_id": "…", "version": 4,
  "prepared_at_version": 3, "preparation_id": "…", "occurrence": {...},
  "asset": {...}, "effective_server_ms": 789, "connection_id": "…",
  "missed": ["<uuid>"], "start_media_ms": 0 }

{ "type": "cancel", "session_id": "…", "version": 5, "reason": "superseded" }

{ "type": "playback", "state": "paused"|"stopped", ... }

{ "type": "playback", "state": "blocked"|"failed", "reason": "…",
  "missing": ["<uuid>"], "session_id": "…", "version": 6, "generation": "…",
  "clock_epoch": "…" }
```

A recovery `prepare` adds top-level `recovery_id` and `start_media_ms`; an
ordinary prepare carries neither, so position zero is a valid recovery
position and never an ordinary marker. `start_media_ms` is meaningful only
while a top-level `recovery_id` is present. A `commit` never carries
`recovery_id`; a video commit keeps `start_media_ms` (0 for a fresh occurrence
or the recovery position).

A ready lease is renewed every 500 ms and expires after 2 s. It must cover the
actual accepted cut and the report must match the preparation's occurrence,
connection and calibration revision; a still must report `decoded: true`, and
a stale clock is refused. A full cohort commits early at the cut. A partial
cohort holds for at most `min(dwell/2, 5 s)`, then commits a future cut for the
ready members and records every miss. A lease that expired before that cut is
not used. Every late cut is re-anchored to `now + 1 s`; the server sends a
`reanchor` status action and the next commit carries the new anchor. The
preparation deadline is `effective + timeout`, so a long clip does not block
30 s after it was prepared. A higher version supersedes every different
preparation. A non-looping last item reaches `final` after its commit and
stays sample-capable and controllable. The displayed still is not changed by
preparation. Stop and abort restore the persisted render. Restart leaves no
session and restores static content.

`playback_status` reports the lineage, state, `current` (last committed),
`displayed`, `current_effective_ms`, `pending`, `playlist_revision`, policy,
`required`, `excluded`, the effective `cohort`, ready/missed members, `final`,
the `recovery` record, and per-device `video` samples. `required` and
`excluded` are sorted and independent of the effective cohort. `members`
carries each pending lease's `ready` and video evidence so a blocked clip
names its failed gate.

`live` describes the frozen session, never the editable saved playlist:

```json
"live": {
  "current":   {"occurrence": {...}, "asset": "sha256:…", "kind": "video",
                "duration_ms": 4000, "dwell_ms": 4000},
  "displayed": null,
  "pending":   {"occurrence": {...}, "asset": "sha256:…", "kind": "still",
                "duration_ms": null, "dwell_ms": 5000}
}
```

Each entry is nullable. A video reports its published duration; a still has
`duration_ms: null` and reports only its frozen dwell. Saving or reordering a
playlist changes what the next Start will use; it does not change these
entries while the session runs.

### Prerecorded video (R4)

A ready video library entry adds these fields to the still descriptor:

| field | value |
| --- | --- |
| `kind` | `"video"` |
| `mime` | `"video/mp4"` |
| `durationMs` | `1000..600000` |
| `codec` | RFC 6381, for example `avc1.42C01F` |
| `profile`, `level` | for example `Constrained Baseline`, `3.1` |
| `pixelFormat` | `yuv420p` |
| `frameRate` | number |
| `bitrate` | bits per second |
| `faststart` | always true after ingest |
| `audio` | true when the stored file keeps an AAC or MP3 track (ignored, muted) |
| `poster`, `thumbnail` | a 256-px thumbnail object |

`intrinsicWidth` and `intrinsicHeight` are the displayed size after rotation
metadata. `GET /media` lists stills and videos. Scene `image` content never
accepts a video or poster id (`422`).

`POST /uploads` accepts `video/mp4` and `video/quicktime` under the same
operator admission: H.264 Constrained Baseline/Main/High up to level 4.1,
8-bit `yuv420p`, long edge at most 1920 and short edge at most 1080, at most
60 fps, 250 MiB, 10 minutes and at least 1 second. The server remuxes losslessly
to faststart MP4, strips metadata, and does not transcode. `201` returns the
descriptor; `413` over 250 MiB, `415` another type, `422` an actionable codec
reason, `503` ffmpeg missing, `507` quota.

`GET` and `HEAD /assets/sha256:<hex>` serve a video with
`Accept-Ranges: bytes` and the strong `ETag` `"<hex>"`. A single range returns
`206` with `Content-Range`; an unsatisfiable range returns `416` with
`Content-Range: bytes */size`. `If-Range` and `If-None-Match` (304) are
honoured. At most four ranges are served; more is a full `200`. A malformed
`Range` is ignored; a `Range` header over 256 bytes returns `431`.

A video `prepare` adds
`media: {kind:"video", duration_ms, buffer_goal_ms:5000, start_lead_ms:1000,
prepare_timeout_ms:30000}`. Its `ready.video` evidence is
`{metadata, seeked, buffered_ahead_ms, play_ok: "yes"|"needs_gesture"|"no",
rvfc}`. A video lease is ready only with metadata and seek true, `play_ok` yes,
and contiguous `buffered_ahead_ms >= min(goal, duration - start)`; a later
report that fails clears readiness. `commit.start_media_ms` is 0 for a fresh
occurrence and the recovery `position_ms` for a recovery commit. The client
never sets the native `loop` attribute; every loop is a new server occurrence.
After the commit the client sends
`{ "type": "video_sample", "session_id": "…", "version": 4,
"occurrence": {...}, "media_ms": 1200, "target_ms": 1200,
"drift_ms": 0.4, "rate": 1.0, "source": "rvfc"|"time" }` at most once per
1000 ms. Only the current socket, session, version, occurrence and a playing
device are accepted; values are bounded and the latest sample is kept for 5 s.

### Bounded group video recovery (R4.1)

A playing video occurrence is re-prepared for the whole cohort when one of
these is true:

- the client sends `video_fault` after its own bounded local recovery is
  exhausted or after `play_ok` is `"no"`;
- the server's last accepted `video_sample` for a playing device is older
  than 3000 ms, unless the playhead is within 250 ms of the clip's natural
  end (that sample is not a stall);
- the client reports the committed occurrence stopped with `ended: false`,
  sent as `video_fault` with reason `stalled` after its local recovery is
  exhausted;
- the client presents no video frame for 2500 ms while the element is
  playing (not paused, not seeking, not ended). A frozen decoder can keep
  `currentTime` and `paused` healthy, so sample recency alone cannot see it;
  the client spends its local recoveries and then sends the same
  `video_fault`.

Ordinary drift inside 250 ms stays local and never starts a recovery.

```json
{ "type": "video_fault", "session_id": "…", "version": 4,
  "occurrence": {"playlist_revision": 1, "item_index": 2, "loop": 0},
  "position_ms": 2400, "reason": "stalled"|"play_failed"|"buffer_lost" }
```

The frame is accepted only from the current socket, a device in `playing`,
the current occurrence and the current version; `position_ms` is bounded
`0..duration_ms - 1`, because a position at the exact end has nothing left to
play. A duplicate fault while a recovery is active is ignored.

A replacement device socket rejoins automatically after its welcome and wall
replay. The returning device must be in the effective `cohort`. If the state
is `recovering`, the pending recovery preparation is re-sent under the new
connection with no new attempt and no deadline change. In `preparing` or
`armed`, the current pending preparation is re-sent. A playing still also
re-sends its pending next preparation, because it has no video picture to
recover. In `playing` with a video
occurrence that is not final, more than 250 ms of media remaining and fewer
than three attempts already spent, one group recovery starts at the
server-authoritative playhead with reason `"reconnect"`: it consumes one
normal attempt, freezes the reachable cohort, cancels the routine next
preparation and commits a fresh common anchor. A second reconnect for the same
device within 2 s of that recovery's `started_ms` does not start another
attempt; while the session is still `recovering`, the resend rule applies.
`paused`, `blocked`, `failed` and `final` sessions, a clip within 250 ms of its
end and an occurrence at the attempt cap do not rejoin automatically; the
tablet stays on the persisted scene until the operator acts. A reconnect never
revives an old epoch, version or position anchor. `"reconnect"` is a
server-initiated recovery reason and is never accepted in a client
`video_fault`.

`playback_status.state` becomes `recovering` and `recovery` is one record:

```json
"recovery": {
  "id": "…", "occurrence": {...}, "position_ms": 2400,
  "reason": "stalled"|"play_failed"|"buffer_lost"|"reconnect",
  "device_id": "<uuid>", "attempts": 1,
  "started_ms": 123, "deadline_ms": 456, "degraded_ms": 789,
  "state": "preparing"|"playing"|"blocked"|"failed", "missing": ["<uuid>"]
}
```

`degraded_ms` is the time since the occurrence was first degraded, capped at
the recovery commit anchor once the state is `playing`. `missing` names the
members that were not ready when a recovery blocked.

The pending next occurrence is cancelled, the cohort is frozen and not
shrunk, and the current occurrence is prepared again at a fresh version and
the common anchor `now + LEAD_MS`. The recovery `prepare` carries a top-level
`recovery_id` and `start_media_ms = position_ms`; `ready.video.buffered_ahead_ms`
is measured from that position and the required buffer is
`min(buffer_goal_ms, duration_ms - position_ms)`. The commit carries the same
`start_media_ms`, and the next boundary is `effective_server_ms +
(duration_ms - position_ms)`, not the full duration. A final non-looping
occurrence stays final after the recovery commit.

A recovery commits only with the whole frozen cohort. At the preparation
deadline a strict session becomes `blocked` with
`blocked_reason: "recovery_timeout"` and keeps the recovery for Retry; an
online session becomes `failed` with reason `recovery_failed`. Retry from a
blocked recovery re-prepares the same occurrence and position at a new
version and anchor. At most three automatic recovery attempts are allowed per
occurrence; a fourth fault enters `blocked`/`failed` without another prepare.
That cap transition advances `version` and clears the pending preparation, so
every old lease, prepared commit and late readiness report is stale. An
operator Retry after that cap starts one fresh episode at the same occurrence
and position, at another fresh version, with `attempts` reset to 1; the fresh
episode is bounded by the same three-attempt cap.

Every transition to `blocked`/`failed` is terminal for the session, whether
it is the attempt cap, a recovery timeout or a preparation timeout. The server
builds one `playback` hold frame with the transition's state, `reason`,
`missing` set and lineage, then sends it to every reachable cohort socket with
isolated fan-out. The hold is idempotent, carries no prepare, and clients
ignore stale lineage after Retry or a new session. A recovery timeout
therefore re-sends the same freeze its recovery prepare already established.
Retry is offered for a strict `blocked` session; an online `failed` session
offers Start again instead.

Stop, a mapping/calibration/layout/rebind change and a clock epoch change
cancel the recovery. A replaced device socket revokes the old connection's
recovery lease before the recovery prepare is sent to the replacement socket;
a fault from the superseded socket is refused.

The client owns three slots: preparing, armed (commit received) and active. A
routine next preparation replaces only the preparing slot. On a recovery
trigger the client freezes the active picture, releases pending and armed
work, and prepares the occurrence from the position. It keeps the previous
picture until the recovery commit, then starts at `start_media_ms`; the next
natural boundary is the remaining duration. A recovery that times out shows
the normal blocked/failed state; Retry is available after a strict `blocked`,
while an online `failed` session offers Start again and Stop. Drift
correction uses a 50 ms deadband, a rate within 0.98..1.02 inside 50..250 ms,
and one seek per 5 s above 250 ms. Pause freezes; Start resumes by restarting
the displayed item; Stop restores the persisted render. Named exclusions are a
session-only Start choice; a recovery keeps the frozen effective cohort and
never re-includes an excluded slot automatically. Optical timing, physical
decode/suspend, iOS Safari and soak remain MISSING.

The browser evidence measures software canvas/DOM timing only. No optical
onset, physical sleep or mixed-model claim follows from it.

## Persistence

The active layout, scene, revision, and generation are persisted. Safe device identity, dimensions, type, number, last-seen timestamp, and assigned colour also persist. Sockets, online presence, negotiated capabilities, clock samples, and playback leases stay in memory. Restored metadata starts offline. A commit
happens before notification, so a controller is never told about state that
would not survive a restart.

Run **one server worker per wall/SQLite database**. The active wall and socket
registries are process-local; this version does not coordinate revisions or
broadcasts across multiple workers or replicas. A database-scoped runtime file lock refuses a second live owner before startup writes. See `docs/ROBUSTNESS.md`.

The generation exists because of this: a restored or replaced database can come
back at a lower revision than a connected tablet holds, and the client must
resynchronise rather than reject the server's state as stale.

## Optional authentication

`TABLET_WALL_AUTH_TOKEN` enables shared-secret protection for HTTP routes, static mounts, and both WebSocket endpoints. API clients use `Authorization: Bearer <token>`; browsers POST a token at `/auth/login` and receive a signed, expiring HttpOnly cookie. Cookie writes and WebSocket connections require a same-origin Origin header. Existing operator-Origin checks also apply. Successful authenticated responses use private, no-store caching. See `docs/AUTH.md` for expiry, token rotation, TLS, and proxy setup.
