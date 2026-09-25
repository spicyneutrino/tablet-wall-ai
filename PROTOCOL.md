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
  not advertised.

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
  "protocol": 2,
  "caps": ["calibration", "image"],
  "online": false,
  "last_seen": "2026-09-24T21:38:59.231663+00:00"
}
```

- `type` is the key name — **not** `device_type`. Existing tests depend on this.
- `color` is `#rrggbb` lowercase, or `null` if never set.
- `online` is a boolean.
- `last_seen` is ISO-8601 UTC with an explicit `+00:00` offset.
- `device_id` is a lowercase UUID4 string.
- `protocol` is the last negotiated major (or `null` before a socket connects);
  `caps` is the list advertised by that socket (empty until then). A version-1
  socket does not receive `wall` frames even if it supplies a `caps` query
  parameter; image support requires **both** protocol 2 and the `image` cap.

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
the rect covers the viewport and cropping the overflow. Seams line up when each
placement's visible rect has the same aspect ratio as that device's reported
viewport. When they differ the device still renders, but the image is cropped
inconsistently.

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
`{ "width", "height", "placements" }` (including reservations whose tablets
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

Layout only. Body may set `width` and/or `height`. `200` returns the new wall
state. `422` if a dimension is not a positive int.

### `PUT /scene`

Content only. Body is `{ "content": { "type": … } }`. For an image, send
`{ "content": { "type": "image", "asset": "sha256:<64 lowercase hex digits>",
"fit": "cover" } }`; `fit` may be omitted and defaults to `cover`. The server
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

**A placement can outlive the roster.** Placements are persisted and the roster
is not, so after a restart a placement may belong to a device that has not yet
re-registered. That is a **reservation, not a leak**: a tablet that comes back
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
   for its **visible rect**, mapped onto its viewport by covering.
4. When `scene.content.type` is `"color"`, keep rendering the assigned colour.
5. When it advertises `image` and receives `scene.content.type` `"image"`,
   load the server-supplied same-origin URL, decode it, draw one centered-cover
   image over the **whole logical wall**
   and map only this tablet's visible rect to its viewport. While loading or on
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
  converted to colour. Only `cover` is currently supported.
- **Fit** is centered `cover` of the image onto the **entire logical wall**:
  with image `Iw × Ih` and wall `W × H`, scale by `max(W/Iw, H/Ih)` and centre
  the overflow. Every tablet then applies the *same* global transform and clips
  to its own visible rect. Covering the image independently into each tablet's
  visible rect would destroy the seams, because each tablet would choose a
  different scale. For transparent PNG pixels, every tablet first paints the
  same opaque wall background (`#0b1120`), not its individually assigned
  colour, so alpha cannot open a seam.
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

## Persistence

The active layout, the active scene, the revision, and the generation are
persisted; sockets, presence, and heartbeat timestamps stay in memory. A commit
happens before notification, so a controller is never told about state that
would not survive a restart.

Run **one server worker per wall/SQLite database**. The active wall and socket
registries are process-local; this version does not coordinate revisions or
broadcasts across multiple workers or replicas.

The generation exists because of this: a restored or replaced database can come
back at a lower revision than a connected tablet holds, and the client must
resynchronise rather than reject the server's state as stale.
