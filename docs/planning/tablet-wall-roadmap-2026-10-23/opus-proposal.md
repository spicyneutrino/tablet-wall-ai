# Tablet wall forward plan, round 1 (Opus)

Written 2026-10-23 against `/var/home/oak/Codes/projects/tablet-wall-ai` at commit `65a4d50` ("feat(controller): redesign the operator console"). This is a proposal. Nothing in it is implemented, and every timing number in it is a design target, not a measurement.

The plan covers sharing images and slideshows across tablets, prerecorded and live video, physical geometry and calibration, synchronized presentation on mixed old and new Android and iPad browsers, drag-and-drop layout, and how to test each of these honestly. Local or hotspot operation is the default throughout.

Four things are treated as fixed constraints:

- the existing security boundary (the operator Origin guard and the two-origin Caddy reference in `deploy/`),
- protocol negotiation by major version and capabilities, including the post-handshake close codes,
- one server worker holding live state in memory,
- SQLite persistence through the commit-before-apply boundary (`_commit_wall`).

Contents

1. Decisions in brief
2. Terms
3. Evidence base
4. What exists today
5. Correctness and architecture debt
6. What only real devices can settle
7. Operator flows and the first vertical slice
8. Architecture options and choices
9. Physical coordinate model and calibration
10. Domain types
11. Protocol evolution
12. Clock sync and scheduled presentation
13. Images: upload, processing, storage and backup
14. Slideshows
15. Video
16. Sync targets, measurement and slow devices
17. Layout editor
18. Test layers
19. Milestones
20. First ten tickets
21. Open product questions and defaults
22. Non-goals and deliberate deferrals
23. Sources

---

## 1. Decisions in brief

1. Keep the monolith: FastAPI in one worker, vanilla JavaScript, SQLite, no build step. New server code lands as small modules beside `tabletwall/`. New tablet code lands as extra classic scripts in the ES2017 dialect the client already uses. No media server, framework rewrite or peer-to-peer layer.
2. Put a shared clock under everything that moves. The server's monotonic clock is the timebase. Tablets estimate their offset from it with NTP-style ping and pong frames on the existing device WebSocket, and they present changes at scheduled server times instead of when a message happens to arrive.
3. Separate preparing content from showing it. A content change becomes a prepare phase with readiness reports, followed by a scheduled start under an explicit policy: wait for all tablets, wait for a quorum, or start at a fixed deadline. A late or reconnecting tablet joins the timeline where it is now.
4. Model physical walls in millimetres. A layout holds slots with physical poses, device profiles give active area and bezels, and per-device calibration gives CSS pixels per millimetre, viewport offset, viewport rotation and a latency trim. The server composes each tablet's transform and sends it as a matrix, so tablets stop carrying their own copy of the geometry rules. Content fit is decided once for the whole wall. Abstract-unit layouts keep today's renderer.
5. Seams are a policy with one parameter, the virtual gap: physical gaps (the default), no gaps (grid groups only), or an overlap band where content near a seam is duplicated on both sides.
6. Uploads go into a content-addressed media store through a processing pipeline in a subprocess: strict type sniffing, decode limits, EXIF orientation applied, conversion to sRGB, metadata stripped, renditions generated. Only the operator origin or a loopback client can upload. Tablets get read-only, hash-named URLs.
7. Video V1 is prerecorded H.264/AAC MP4 with the index at the front of the file, served with HTTP byte ranges, muted on tablets, started on a schedule, and kept aligned with small `playbackRate` changes and rare seeks. Segmented HLS comes second. Live input is a separate later track that starts with delayed HLS. WebRTC and WebCodecs stay out until a measured need appears.
8. The protocol stays at major version 2. New behaviour is additive and gated by capabilities (`clock`, `status`, `view`, `playlist`, `video`, `command`, plus a `liveness` server capability). Operator writes get optimistic concurrency through `ETag` and `If-Match`.
9. Fix identity first. The tablet reads close codes, a `?display=<name>` parameter gives distinct identities inside one browser profile, a server-set HttpOnly cookie recovers an identity that local storage lost, and the controller can bind a new device to an existing slot.
10. Test in five layers: unit tests with shared geometry fixtures, the existing in-process simulator, a real-browser harness with isolated contexts and a userspace network impairment proxy, a physical tablet matrix, and optical measurement with a high-speed camera. Only the last two can say anything about real synchronization.
11. Targets are provisional. For example, the plan aims for a 95th percentile slide-change onset difference of 50 ms or less between healthy tablets, measured optically. Every target has a fallback for slow devices.
12. The first usable slice is: upload images, run a synchronized crossfade slideshow on the current layout model with placements entered in millimetres, see per-tablet readiness and clock health in the controller, and survive reconnects and a server restart. Physical calibration, the drag-and-drop editor and video follow it.

## 2. Terms

- Offset: the estimated difference between a tablet's clock and the server's clock.
- Uncertainty: the error bound a tablet reports for its offset. It is half the round-trip time of the samples the estimate used.
- Onset difference: the time between two tablets starting the same visible change, measured as light leaving the screens.
- Software-observed onset: the time a tablet's script believes it started showing a change, from its frame callback timestamp. It excludes the display's own delay.
- Drift: how far a playing video's position is from where the shared timeline says it should be.
- Lead: how far in the future a change is scheduled so every tablet receives the command in time.
- Late join: a tablet that arrives after a scheduled start computes where the timeline is now and enters there.
- Slot: a mounting position in a physical layout. A binding connects a slot to a device identity.

## 3. Evidence base

Read in full: `README.md`, `PROTOCOL.md`, `main.py`, `tabletwall/protocol.py`, `tabletwall/state.py`, `tabletwall/hub.py`, `tabletwall/persist.py`, `tabletwall/assets.py`, `frontend/client/client.js`, `frontend/client/client.css`, `frontend/client/index.html`, `deploy/hotspot.Caddyfile`, `deploy/README.md`, `deploy/KIOSK.md`, `deploy/OPERATIONS.md`, `simulator/README.md` and the simulator modules.

Read in part: `frontend/controller/controller.js` (structure, wall map, placement inputs, write paths), `deploy/backup.py`, `deploy/load-smoke.py`, the test suites (names and selected bodies), and three tables in the user's `docs/CODEBASE_GUIDE.md` (concurrency, state ownership, complexity hotspots) to cross-check my debt list. I did not modify anything under `docs/` or `CODEBASE_EXPLORE_PROMPT.txt`.

Parent observations, not re-run by me (from `/tmp/tablet-wall-roadmap-20261023-parent-evidence.md`):

- The simulator passed 23 scenarios and 1075 checks.
- The laptop's Wi-Fi client and its hotspot both used channel 44, with one associated station.
- The live server at `http://10.42.0.1:8000` had one online client reporting a 1152x720 CSS viewport and one offline client.

That live server is reachable over plain HTTP on the hotspot address without the Caddy ingress in front of it, so direct LAN exposure is in real use. Whether the operator Origin guard was configured is unknown, because read-only GETs pass either way. That matters for the upload rule in section 13.

Local facts I checked in this session:

- Starlette 1.6.0 `FileResponse` serves single and multiple byte ranges, honours `If-Range`, and answers 416 for unsatisfiable ranges.
- Pillow 12.3.0 ships `MAX_IMAGE_PIXELS = 89,478,485`. It warns above that and raises `DecompressionBombError` above twice that. The app's own 12 MP pre-check is the real limit today.
- `ffmpeg` and `ffprobe` 8.1.3 are installed with `libx264`, `libvpx-vp9`, `libopus`, `aac`, and the `drawtext` and `testsrc2` filters.
- Playwright browser builds exist in `~/.cache/ms-playwright`, but the Playwright library is not in the project environment.
- There is no branded Chrome outside Flatpak, and there is GNOME Web (`epiphany`, WebKitGTK).

Not done: I ran no tests and started no servers or browsers. I changed no files except this one. Browser and media claims are cited in section 23 with the retrieval date. Claims I could not confirm from a primary source are marked "unverified".

Labels used below:

- "verified in source": I read the code.
- "documented": a primary source is cited.
- "inferred": reasoned but not observed.
- "needs device": only physical hardware can settle it.

## 4. What exists today

### 4.1 Server

- `main.py` holds all routes. Live state is module-level in `tabletwall/state.py` (`devices`, `device_sockets`, `controller_sockets`, `wall`).
- Every wall change goes through `_commit_wall` (`main.py:312`):
  1. deep-copy the wall,
  2. apply the change,
  3. bump the revision,
  4. `persist.save_state`,
  5. swap the live state and broadcast.

  Nothing awaits between mutation and swap.
- Clients order frames by generation then revision. The generation is a fresh 8-hex string on every start (`state._new_generation`), which makes every client accept the next frame after a restart.
- Protocol majors 1 and 2 are negotiated with the `protocol` query parameter, and capabilities with `caps`. The server's `server_caps` is `["calibration", "image"]`. Close codes 4400, 4404, 4408, 4409 and 4426 are sent after accepting the socket so browsers can read them (`ws_device`, `main.py:1348`).
- The device loop (`_device_loop`, `main.py:1327`) ignores every frame type except `heartbeat`. It refreshes `last_seen` only if the socket still owns the device's slot. Heartbeat interval 5 s, timeout 15 s, sweep every 2 s.
- Content types are `color`, `calibration` and `image`. The only fit is `cover` (`SceneContent`).
- A layout is a wall rectangle in abstract integer units (default 2000 x 1000) plus per-device placements `{x, y, w, h, bezel}`. Placements of offline devices stay as vacant reservations. Named layouts and named scenes are snapshots in their own tables.
- When `TABLET_WALL_OPERATOR_ORIGIN` is set, unsafe methods and the controller socket need a matching `Origin`. `POST /devices/register` is exempt. `/operator-config` tells the controller the tablet origin.
- The README marks Phase 2 software as done and physical validation as pending. Its roadmap lists Phase 3 (trust boundary, HTTPS and service setup, resilience, CI) and says timed media comes only after validation.

### 4.2 Tablet client (`frontend/client/client.js`, 1919 lines)

- Identity is a UUID4 in `localStorage` under `tablet-wall-device-id` (`client.js:218`). `DEVICE_TYPE` is hardcoded to `"ipad"` (`client.js:46`).
- `register()` posts `innerWidth` and `innerHeight` before every connect, and again after a debounced resize or orientation change.
- There is one WebSocket with `protocol=2&caps=calibration,image`. `openSocket` (`client.js:1831`) handles every close the same way, and `run()` reconnects with jittered backoff from 0.5 s to 15 s. Close codes are never read.
- Wall frames apply by the generation and revision rule (`applyWallFrame`, `client.js:1524`).
- Rendering uses one canvas. `prepareCanvas` (`client.js:432`) sizes the backing store from `viewportSize()`, which reads `innerWidth` and `innerHeight`. Meanwhile `client.css:44-45` sizes the element to `100vh`, then `100lvh`.
- Mapping happens in two stages. Each tablet covers its viewport with its placement's visible rect (scale is the larger of the two axis ratios, centred), and the image covers the whole wall. Aspect mismatches therefore crop per tablet.
- Image loads go fetch, blob, then `createImageBitmap`, with an `<img>` fallback, a 15 s timeout, and stale-load guards by token, generation and revision.
- There are calibration, unplaced and unsupported-content screens, a status pill, and a fullscreen button that shows for 5 s.
- The client has no time sync, sends no status upstream, ignores `visibilitychange`, has no server liveness check and no wake lock.
- It uses ES2017 features (async functions, `padStart`). I did not audit it for later syntax.

### 4.3 Controller (`frontend/controller/controller.js`, 4109 lines)

- One large closure with sections for what is on the wall, wall size and layout, a wall map, tablet cards and saved setups.
- Placements are edited with numeric fields per tablet. The wall map is a set of buttons that focus a tablet card. A grep for `pointerdown`, `setPointerCapture`, `dragstart` and `keydown` finds nothing, so there is no drag or keyboard movement today.
- Writes carry no revision precondition. No automated test covers this file.

### 4.4 Persistence and assets

- The database comes from `TABLET_WALL_DB` (default `tablet-wall.db`). Tables are `wall_state` (one row), `saved_layouts` and `saved_scenes`. Each call opens a connection and re-runs `CREATE TABLE IF NOT EXISTS`. There is no schema version.
- Curated assets come from `TABLET_WALL_ASSET_DIR` (default `./assets`).
  - Rules: JPEG and PNG only, 10 MiB, 12 MP, extension must match the format, no animation, and EXIF orientation must be 1 or absent.
  - IDs are `sha256:` of the bytes.
  - `assets.refresh()` (`assets.py:153`) rescans, rehashes and decodes every file. It runs on every list, every scene write (`find`) and every fetch.
- `GET /assets/{id}` (`main.py:1297`) reads the whole file into memory, re-hashes it, and returns it with immutable caching and `nosniff`. It has no Range support.

### 4.5 Deployment and security boundary

- `deploy/hotspot.Caddyfile` defines two origins.
  - Tablet origin `https://{$WALL_HOTSPOT_IP}:8443` with `tls internal` and an exact allowlist: four client file paths, `POST /devices/register`, `GET /ws/device`, and `GET /assets/sha256:<64 hex>`. Everything else gets 403.
  - Operator origin `https://localhost:8444`, bound to loopback, with Basic auth. It strips `Authorization` and `Cookie` before proxying.
- `deploy/backup.py` copies the database with SQLite's online backup API plus referenced curated assets (manifest version 1). It restores only into new targets.
- `deploy/load-smoke.py` opens 20 connections through the ingress.
- `deploy/KIOSK.md` has a table of real-device gates that are not yet checked off.

### 4.6 Tests and simulator

- Python suites: `test_api`, `test_assets`, `test_backup`, `test_commit_boundary`, `test_deployment_guards`, `test_persistence`, `test_security`, `test_snapshots`, `test_wall`, `test_websocket`, plus simulator self-tests. That is about 300 test functions by grep count.
- `tests/client_image.test.js` runs `client.js` in a Node `vm` with a fake DOM and canvas (23 cases).
- `simulator/` drives the real app in-process through Starlette's `TestClient`, with 18 simulated devices, 23 scenarios and a geometry oracle. Its README says it cannot see JavaScript, pixels, TCP behaviour or real time. That is accurate, and it stays true after this plan.

## 5. Correctness and architecture debt

| ID | Problem | Evidence | Fixed in |
| --- | --- | --- | --- |
| D1 | Windows in one browser profile fight over one identity | one storage key per origin (`client.js:218`), 4409 replacement in `ws_device`, close code ignored in `openSocket` | M0 |
| D2 | Identity can be lost | identity only in `localStorage`; WebKit deletes script-writable storage after 7 days of Safari use without interaction (documented); a new origin means a new identity | M0, M5 |
| D3 | Canvas element box and backing store can disagree | backing store from `innerHeight`, element height `100lvh` (`client.css:44-45`) | M0 |
| D4 | Asset reads scale with library size | `assets.refresh()` hashes and decodes every file on each list, scene write and fetch | M2 |
| D5 | Whole-file responses without byte ranges | `get_asset` returns `Response(content=data)` | M2 |
| D6 | Fan-out waits on the slowest socket | `hub._broadcast_wall` awaits each send in turn | M0 |
| D7 | Last write wins between operator windows | no precondition on write routes | M0 |
| D8 | Tablets cannot tell the server is gone | client only notices when TCP does | M0 |
| D9 | Loose input validation | `Bezel` allows negative edges; `Bezel` and `PlacementCommand` accept unknown keys; registration sizes are unbounded | M0 |
| D10 | Geometry rules exist in five copies | `PlacementCommand.validate_rect`, `_valid_saved_layout`, `client.visibleRectOf`, controller `placementProblem`, `simulator/geometry.py` | M0, M5 |
| D11 | No schema versioning | `persist._MIGRATION` only creates tables; `_valid_saved_layout` checks exact key sets | M0 |
| D12 | Event-loop work adds timing noise | SQLite on the loop, image validation in threads | M2, M3 |
| D13 | Controller has no tests | one 4109-line closure | M5, M6 |
| D14 | Ingress allowlist names exact files | Caddyfile lists `/client/client.js` and the other files one by one | M0 |
| D15 | Needed browser features require HTTPS | Wake Lock, Cache Storage and WebCodecs are secure-context only (documented) | M8 |

The two that block the rest are D1 and D3.

D1 makes any multi-window manual test and any naive browser harness unreliable. Two pages sharing storage replace each other every reconnect cycle.

D3 is inferred from the code and not yet observed. Suppose a browser shows a toolbar, so the large viewport (`lvh`) is taller than `innerHeight`. The browser then stretches the backing store vertically by the ratio of the two. Desktop Chromium has no retractable toolbar, which is why existing desktop checks would not show it. The first device check is cheap: on a real tablet in a normal browser tab, display the canvas's `getBoundingClientRect().height` next to `innerHeight`. If D3 is real, every physical calibration made in tab mode would be wrong, so it is fixed before calibration work starts.

D2 changes the order of work. Moving tablets from the current plain-HTTP origin to the HTTPS Caddy origin gives every tablet a new identity, and the WebKit storage cap can do the same after a week. Calibration data keyed by device identity would be orphaned. M0 therefore adds cheap rebinding, and the origin decision (question 3 in section 21) comes before anyone records calibration data.

D6 matters for timing. A scheduled start needs a lead longer than the worst fan-out time. With sequential awaited sends, one slow tablet stretches that for every tablet after it in the loop.

## 6. What only real devices can settle

- Viewport behaviour per browser and mode:
  - `innerWidth` and `innerHeight` against `lvh`, `screen.width` and `visualViewport`,
  - toolbar retraction and orientation reporting,
  - Home Screen and fullscreen modes.

  This settles D3 and the calibration method.
- CSS pixels per millimetre for each model and each OS zoom setting (iPadOS Display Zoom, Android display size).
- Fullscreen API availability per device. Safari 16.4 supports it unprefixed on iPadOS (documented); older iPadOS and each Android browser need checking.
- Image decode time and the memory ceiling on the oldest tablet, which set the largest safe rendition.
- Display pipeline delay per model, from a frame callback to light leaving the panel. JavaScript cannot read it, and it differs between models. The per-device latency trim exists to correct it.
- Refresh rate (60 Hz, 120 Hz, or reduced in power-saving modes) and whether frame callbacks follow it. Whether iOS Low Power Mode caps frame callbacks at 30 per second is unverified. Tablets will report their measured frame rate.
- Video behaviour:
  - which resolutions and bitrates decode smoothly,
  - whether `playbackRate` changes of 1 to 5% stutter,
  - seek latency and the gap when a video loops,
  - muted autoplay,
  - whether iOS buffers before `play()` is called (unverified).
- Wi-Fi:
  - the round-trip distribution and power-save delays,
  - recovery after screen sleep,
  - the aggregate throughput of this laptop hotspot, whose single radio serves both the access point and the laptop's own Wi-Fi connection.
- Storage persistence beyond 7 days, in Safari tabs versus Home Screen apps.
- Clock behaviour across tablet sleep, long runs and thermal throttling.
- Wake lock, auto-lock and kiosk features (Guided Access, Android screen pinning).

## 7. Operator flows and the first vertical slice

### 7.1 Flows

F1, join. The controller shows the tablet URL and a QR code. A new tablet opens it, registers, and shows a large label and colour in setup mode. The operator names it.

F2, arrange. The operator picks a device model for each tablet (or "custom") and drags shapes on a millimetre canvas. Shapes snap to neighbours with a chosen gap and rotate in 90 degree steps, and an inspector shows numeric values. "Identify" flashes the real tablet. Tapping a tablet in setup mode highlights its shape in the editor.

F3, calibrate.

1. Each tablet goes fullscreen or runs as a Home Screen app.
2. Scale comes from the model profile, from matching a bank card on screen, or from a ruler.
3. The wall shows an alignment pattern across all tablets. With live mode on, the operator nudges tablets until lines are continuous, reading vernier scales at the seams.
4. The operator saves the result as a named layout.

F4, upload and show. The operator drags files into the media panel. Each shows progress, then a thumbnail with dimensions and any warnings. The operator picks one and presses Show. The controller shows each tablet go from preparing to ready to showing, and the wall changes together.

F5, slideshow. The operator drags images into a playlist and sets duration and transition (default 10 s with an 800 ms crossfade). Controls are play, pause, next and previous. The controller shows the current slide, the time to the next one, and any late or failed tablets.

F6, video. The operator uploads an MP4. The server checks codec, profile, frame rate and file layout, and fixes the layout losslessly if that is the only problem. The operator chooses full download or buffer-ahead. Playback starts when the start policy is met. The controller shows buffer, drift and stalls per tablet.

F7, recover. A tablet that reloads, sleeps or loses Wi-Fi returns to the right content at the right point. A replacement tablet shows a pairing code, and the operator binds it to the old slot, keeping position and, for the same model, calibration. After a server restart the wall resumes where the timeline says it should be.

### 7.2 Slice 1

Goal: the smallest release that is useful on a real wall and exercises the risky parts (time sync over real Wi-Fi, readiness, uploads, identity), without waiting for the physical model or the editor.

Scope:

- From M0: close codes and identity, the render box fix and display report, `If-Match`, per-socket send queues, the liveness watchdog, schema versioning.
- From M2: image upload with renditions.
- From M3: status, clock sync, and prepare-then-show.
- From M4: playlists with crossfade.
- The layout stays the current model, and the operator enters placements in millimetres. Units are plain numbers today, so "1 unit = 1 mm" is a convention the controller can label.

  With a tablet in fullscreen and a visible rect equal to its active area, today's centred cover mapping already gives the correct physical scale, because both axis ratios are the same. Rotation and toolbar offsets wait for M5.

Acceptance. All targets here are provisional, and the measured distributions are recorded whether or not a target is met.

1. Upload three phone photos from the controller: one rotated by EXIF, one carrying GPS metadata, and one PNG with transparency. Each appears upright and without metadata within 10 s on the laptop.
2. A three-item playlist with 8 s slides and a 1 s crossfade plays on at least two physical tablets plus 10 harness clients. The controller shows each tablet's clock uncertainty and phase.
3. An optical check with a phone at 240 frames per second over 20 transitions shows a 95th percentile onset difference between physical tablets of 50 ms or less.
4. Turning one tablet's Wi-Fi off for 20 s: it shows the correct slide within 5 s of reconnecting.
5. Restarting the server mid-slideshow: tablets show the slide the timeline expects within 10 s.
6. Two controller windows: the stale one gets a 412 and a clear message, and nothing is overwritten.
7. Harness: 12 isolated browser contexts get 12 distinct identities. Two pages sharing one context produce one conflict screen and no reconnect storm.

## 8. Architecture options and choices

### 8.1 System shape

Options:

- (a) extend the monolith,
- (b) add a media sidecar (Caddy `file_server`, nginx, or a media server),
- (c) rewrite on a framework with a build step,
- (d) peer-to-peer distribution between tablets.

Choice: (a), with Caddy `file_server` as a later optimisation for large static media if measurements call for it.

- The server's hard parts (the commit boundary, ordering, socket slot ownership) are already in this code and well tested.
- The fleet is tens of devices.
- A single process keeps the clock master, the state and the fan-out together, which is what synchronization needs.
- (b) is worth it only if Python-served video saturates the CPU at real bitrates. M7 measures that.
- (c) costs a rewrite and solves none of the listed problems.
- (d) needs WebRTC in a browser and gains nothing on one hotspot radio, where every byte still crosses the same air.

### 8.2 Time base

Options:

- (a) a server-anchored schedule with NTP-style offset estimation over the device WebSocket,
- (b) trust each tablet's `Date.now()`,
- (c) run an NTP server on the laptop and point tablets at it,
- (d) keep showing changes on arrival.

Choice: (a).

- (b) fails offline: tablets on a hotspot without internet may never sync their clocks, and wall-clock time can jump. The HR-Time specification advises against sending wall-clock time representations between computers (documented).
- (c) needs per-tablet OS settings that iPadOS does not expose.
- (d) is today's behaviour. It is fine for a static image, but its skew equals delivery jitter. On Wi-Fi with power saving, that can plausibly reach hundreds of milliseconds (inferred; M3 measures it).

### 8.3 Tablet rendering

For images, the plan uses canvas layers. Each prepared item is drawn once into a viewport-sized canvas holding only this tablet's slice, then shown by changing that layer's opacity.

- `<img>` elements with CSS transforms are simpler, but the browser keeps each item's whole decoded image, which old tablets may not afford.
- WebGL adds capability that isn't needed and adds compatibility risk.
- Canvas layers keep memory bounded by the number of layers, not by image size.

For video, the plan uses a `<video>` element positioned with a CSS matrix so each tablet shows its slice. Copying every video frame into a canvas costs a full-frame copy per frame on old hardware. Whether very large transformed video elements composite well on the oldest iPads needs a device check.

### 8.4 Video delivery

Compared in section 15.6. Choice: progressive MP4 first, segmented HLS second, live input as delayed HLS. WebRTC and WebCodecs are deferred.

### 8.5 Geometry representation

Options:

- (a) keep abstract units and add a per-device scale,
- (b) millimetres for everything physical,
- (c) the pixels of one reference device.

Choice: (b).

- Millimetres can be checked with a ruler, device specifications are published in them, and they make the PPI question explicit.
- (a) is (b) with unexplained numbers.
- (c) breaks as soon as models differ.

### 8.6 Browser test driver

Options: Playwright, Selenium/WebDriver, Puppeteer, or hand-opened windows.

Choice: Playwright with its Python bindings, to match the repo.

- It creates browser contexts with their own storage, cookies and sockets (documented).
- It drives Chromium, Firefox and WebKit builds.
- It exposes the Chrome DevTools Protocol for CPU throttling and page freezing in Chromium.
- Selenium is worth adding only if a Mac becomes available: `safaridriver` can drive Safari on an iOS or iPadOS device connected to a Mac (documented in the Safari 13 notes).
- Hand-opened windows share storage and hit D1.

## 9. Physical coordinate model and calibration

### 9.1 Spaces and units

- Wall space is in millimetres, with the origin at the top-left of the wall frame as a viewer sees it, x to the right and y down. Values are floats stored to 0.1 mm.
- A tablet's body frame is its outer shell, in the profile's reference orientation.
- The active area is the lit part of the panel inside the body.
- The viewport is what the browser gives the page, in CSS pixels, with the page's own "up".
- Device pixels are CSS pixels times `devicePixelRatio`. They are used only to size backing stores and choose renditions.

### 9.2 Profiles, slots and calibration

A device profile describes a model. It holds:

- active area size in mm, in the reference orientation,
- body size in mm,
- the active area's centre offset from the body centre (non-zero when one bezel is wider, as on tablets with a home button),
- native panel pixels and PPI, for reference,
- where those numbers came from (a specification page or a measurement) and when.

A slot describes a mounting position in a layout. It holds:

- body centre in wall millimetres,
- rotation in quarter turns,
- optional fine rotation in degrees, for small tilt corrections,
- optional nudge in millimetres,
- a label, the expected profile, and an optional grid group.

A binding maps a slot to a device identity. Because slots and bindings are separate, a replaced or re-identified tablet is rebound, not re-placed.

Calibration belongs to a device in one browser configuration. It holds:

- `k`, CSS pixels per millimetre (isotropic, assuming square pixels),
- the viewport offset in mm from the active area's top-left (non-zero when a toolbar uses part of the screen),
- the viewport rotation in quarter turns relative to the active area, for when the OS draws the page rotated against the profile's reference orientation,
- the latency trim in milliseconds,
- the method used (profile, card, ruler or manual),
- the configuration it is valid for: viewport CSS size, DPR, fullscreen, standalone.

If a later registration reports a different configuration, the controller marks the calibration stale.

### 9.3 Transform chain

For a viewport point in CSS pixels, the wall position in millimetres is given by one affine matrix:

```
M_wall<-css = T(c_slot + n) · R(theta) · T(o_active - s_active / 2) · T(o_view) · Q(q_view, V / k) · S(1 / k)
```

- `S(1 / k)` converts CSS pixels to millimetres.
- `Q(q_view, V / k)` rotates the viewport rectangle (size `V / k` in mm) by `q_view` quarter turns about its corner and translates it so its top-left is at the origin again.
- `T(o_view)` places the viewport inside the active area.
- `T(o_active - s_active / 2)` moves from active-area corner coordinates to body-centred coordinates (`o_active` is the active area's corner relative to the body centre, `s_active` its size).
- `R(theta)` rotates the body into the wall, with `theta` = 90 degrees times the slot's quarter turns, plus the fine rotation.
- `T(c_slot + n)` moves to the slot centre in wall space, plus the nudge.

The seam policy (9.6) then maps wall space to content space, which is a per-group translation. The server sends each tablet the inverse, `contentToCss`, as six numbers in canvas `setTransform` order.

- Images: the tablet sets `ctx.setTransform` to `dpr` times `contentToCss` times the item's `imageToContent` matrix, then draws the bitmap at the origin.
- Video: the same product without `dpr` becomes a CSS `matrix()` on the video element, with `transform-origin: 0 0`.

The server is the only place that composes the chain (`tabletwall/geometry.py`). The controller's preview composes it in JavaScript for live dragging, checked against the same golden vectors (section 18.1). Tablets in physical mode only apply matrices, which removes their copy of the geometry rules.

### 9.4 PPI, CSS pixels and DPR: a worked example

The physical size of a CSS pixel differs by model.

- Apple's published specification for the 10.2-inch iPad is 2160 x 1620 pixels at 264 ppi (not re-fetched in this session; check the exact model). Its active area is 2160 / 264 = 8.18 in = 207.8 mm wide. In fullscreen landscape, Safari gives a 1080 x 810 CSS viewport at DPR 2, so k = 1080 / 207.8 = 5.20 CSS px per mm.
- A hypothetical 10-inch Android tablet with a 1280 x 800 CSS viewport across a 217 mm active area has k = 5.90.
- If both draw one image at the same CSS pixel scale, the image is about 13% larger on the iPad, and the jump shows at the seam.
- A desktop monitor at 96 dpi has k = 3.78 and says nothing about either tablet.

Rules that follow:

- Never derive physical size from the user agent. After user-agent reduction, Chrome on Android reports the model as "K" and the Android version as "10". Safari on iPad usually sends a macOS user agent (both documented). The operator picks the model.
- `devicePixelRatio` only sizes backing stores and chooses renditions. It is not a physical measure.
- OS zoom settings change k. Recalibrate when the reported viewport or DPR changes.

### 9.5 Content fit is separate from geometry

A scene has a content rectangle in content space (default: the bounding box of all bound slots' active areas after the seam policy) and a content transform: `fit` (`cover` or `contain`), a focal point for cover crops, and optional zoom and pan.

- A layout never changes when content changes.
- A content transform never depends on any single tablet.

In physical mode this replaces today's two-stage cover (per-device cover of the visible rect, then a global cover). There is one fit, applied once, so no tablet crops differently from its neighbours.

### 9.6 Seam policies

A seam policy says what happens to content in the space between active areas. It is set per grid group (tablets aligned in rows and columns). Irregular arrangements always use physical gaps.

- Physical gaps (default): the wall acts as a window onto the content. Lines stay straight across seams, and content behind bezels and gaps is not shown.
- No gaps: the group is packed edge to edge in a virtual wall. Every content pixel appears once, but a line crossing a seam jogs by the gap width.
- Overlap band: adjacent content windows overlap by a chosen width, so the band beside each seam appears on both tablets. This helps when text or faces must not be cut by a bezel.

All three are one parameter per seam, the virtual gap: equal to the physical gap, zero, or negative. The server applies it when it computes each tablet's content window. Tablets never need to know which policy is active.

### 9.7 Calibration procedure and expected accuracy

1. Mode check. The tablet asks for fullscreen or Home Screen mode, and the controller flags any tablet that is in neither.
2. Scale. Choose one of three methods:
   - Profile: k = viewport width / active width. Valid only when the viewport fills the active area.
   - Card: the tablet shows a rectangle with handles. The operator lays an ID-1 bank card (85.60 x 53.98 mm; check the card with calipers) on the glass and drags until the edges match. k = rectangle width in CSS px / 85.60.
   - Ruler: two lines a known CSS distance apart, and the operator types the measured millimetres.

   A correct profile is usually the most accurate. The card is good to roughly 0.5%, about 1 mm across a 200 mm panel (inferred from one CSS pixel of handle precision plus edge alignment).
3. Rotation and offset. The tablet shows an arrow and "this way up", and the operator confirms the slot rotation. In tab mode the operator says which edge the toolbar is on, and the tablet reports how much of the screen its viewport uses.
4. Alignment. The wall shows a physical-mode pattern: diagonals, circles and a 10 mm grid. In live mode, nudges apply immediately at a few updates per second, so the operator can watch the lines meet.
5. Verification. Vernier scales at each seam, with ticks every 1.0 mm on one side and every 0.9 mm on the other, so misalignment can be read by eye to about 0.2 mm (limited by CSS pixel size).
6. Latency trim, later, from optical measurement: a per-device offset in milliseconds that cancels that model's display pipeline delay.

Provisional target after calibration: line continuity across seams within 1 mm for fullscreen tablets, checked with the vernier pattern and a photo.

### 9.8 Legacy layouts and migration

- Existing layouts keep abstract units and the current renderer. Nothing changes for them.
- "Convert to millimetres" asks for each tablet's model. It proposes one scale factor (mm per unit) by least squares over tablets with known profiles, converts positions, and opens the result in the editor. It creates a new layout and leaves the old one alone.
- Saved snapshots validate against the content version that wrote them (the D11 fix), so old snapshots still recall.
- Tablets without the `view` capability receive legacy placement fields derived from the physical layout (body rect rounded to integer millimetres), and the controller labels them as using the legacy renderer.

## 10. Domain types

Notation is TypeScript-like for readability only. Implementation is Pydantic models on the server and plain objects in the tablet scripts.

```ts
// ---------- media ----------
type ObjectId = string;            // "sha256:<64 hex>" of any stored file
type AssetId = ObjectId;           // for uploads: hash of the original bytes; for curated files: hash of the file

interface MediaAsset {
  id: AssetId;
  kind: "image" | "video";
  origin: "upload" | "curated";
  name: string;                    // sanitised display name, never used as a path
  status: "processing" | "ready" | "failed";
  error?: string;                  // operator-facing reason when failed
  pipelineVersion: number;         // renditions can be rebuilt from the original
  createdAt: string;               // ISO 8601, wall clock
  original: { object: ObjectId; bytes: number; mime: string };
  width: number;                   // after orientation is applied
  height: number;
  renditions: Rendition[];         // largest first; for curated files, the file itself
  poster?: ObjectId;               // still image for video fallbacks and thumbnails
  video?: { durationMs: number; fps: number; codec: string; profile: string; level: number;
            hasAudio: boolean; keyframeIntervalMs: number };
}

interface Rendition {
  object: ObjectId; mime: string; width: number; height: number; bytes: number;
  role: "display" | "thumbnail"; bitrateKbps?: number;
}

// ---------- geometry ----------
interface DeviceProfile {
  id: string; label: string;
  activeMm: [number, number];             // reference orientation
  bodyMm: [number, number];
  activeCentreOffsetMm: [number, number];
  panelPx?: [number, number]; ppi?: number;
  source: { kind: "spec" | "measured"; ref?: string; date: string };
}

interface Slot {
  id: string; label: string;
  centreMm: [number, number];
  quarterTurns: 0 | 1 | 2 | 3; fineDeg: number; nudgeMm: [number, number];
  profileId?: string; group?: string;     // grid group, for seam policies
}

type SeamPolicy = { kind: "physical" } | { kind: "none" } | { kind: "overlap"; widthMm: number };

interface PhysicalLayout {
  version: 1; units: "mm";
  slots: Slot[];
  bindings: Record<string, string>;      // slot id -> device id
  seams: Record<string, SeamPolicy>;     // grid group -> policy
}

interface Calibration {
  cssPxPerMm: number;
  viewportOffsetMm: [number, number];
  viewportQuarterTurns: 0 | 1 | 2 | 3;
  latencyTrimMs: number;
  method: "profile" | "card" | "ruler" | "manual";
  validFor: { viewportCss: [number, number]; dpr: number; fullscreen: boolean; standalone: boolean };
  measuredAt: string;
}

interface Display {                      // persisted per device identity
  deviceId: string; label: string; profileId?: string;
  calibration?: Calibration;
  lastReport?: DisplayReport;
}

interface DisplayReport {                // sent at registration; untrusted input
  viewportCss: [number, number];         // measured box of the render surface
  screenCss: [number, number]; dpr: number;
  orientation?: { type: string; angle: number };
  fullscreen: boolean; standalone: boolean;
  features: string[];                    // detected features, informational only
  userAgent: string;
}

// ---------- content and playback ----------
type Fit = "cover" | "contain";
interface ContentTransform { fit: Fit; focal?: [number, number]; zoom?: number; panMm?: [number, number] }
type Transition = { kind: "cut" } | { kind: "crossfade"; durationMs: number };
type BufferPolicy = { kind: "full" } | { kind: "ahead"; minAheadMs: number };

interface PlaylistItem { asset: AssetId; durationMs: number; transition: Transition; transform?: ContentTransform }

type Content =
  | { type: "color" }
  | { type: "calibration"; pattern?: "grid" | "alignment" | "vernier" | "sync-flash" | "identify" }
  | { type: "image"; asset: AssetId; transform: ContentTransform; session?: PlaybackSession }
  | { type: "playlist"; items: PlaylistItem[]; loop: boolean; session: PlaybackSession }
  | { type: "video"; asset: AssetId; transform: ContentTransform; loop: boolean;
      audio: { kind: "none" } | { kind: "device"; deviceId: string };
      buffer: BufferPolicy; session: PlaybackSession };

interface PlaybackSession {
  id: string;                            // same id means the prepared media can be kept
  state: "preparing" | "playing" | "paused";
  anchor?: { serverMs: number; positionMs: number };   // absent while preparing
  start: { policy: "all" | "quorum" | "deadline"; quorum?: number; maxWaitMs: number; leadMs: number };
  drift?: { softMs: number; hardMs: number; maxRateDelta: number };  // video only
}

// ---------- status (memory only, never persisted) ----------
interface DeviceStatus {
  seq: number; generation: string; revision: number; sessionId?: string;
  phase: "idle" | "preparing" | "ready" | "presenting" | "late" | "degraded" | "failed";
  item?: number; positionMs?: number;
  presentedAtServerMs?: number;          // software-observed onset of the last change
  clock?: { offsetMs: number; uncertaintyMs: number; rttMinMs: number; samples: number };
  media?: { bufferedAheadMs: number; driftMs: number; rate: number;
            droppedFrames: number; stalls: number; seeks: number };
  display: { visible: boolean; fullscreen: boolean; rafHz?: number;
             wakeLock: "held" | "released" | "unsupported" | "denied" };
  deliveryMs?: number;                   // last wall frame, send to receipt, on the shared clock
  errors?: string[];
}
```

Where things live:

- The session lives inside `scene.content`. Starting, pausing or skipping is one committed wall change, so the existing revision rule orders control actions and persistence is atomic.
- Saved scenes strip the session and keep items and settings. A named playlist is a saved scene, so no separate playlist table is needed.
- New tables: `media_objects`, `media_assets`, `displays` and `device_profiles`. Physical layouts are versioned JSON documents in the existing `saved_layouts` table and the `wall_state` row.

## 11. Protocol evolution

### 11.1 Rules

- Stay on major version 2. Add fields and frames only behind capabilities. Tablets ignore unknown fields, and the server's device loop already ignores unknown frame types (`main.py:1327`).
- A breaking change, such as removing the legacy placement fields, needs major version 3. The existing 4426 path already handles that.
- Gate every new behaviour in both directions. The tablet advertises a capability in `caps`, and uses a server feature only when `server_caps` lists it. For example, a new tablet must not start its liveness watchdog against an old server that never answers.
- Every scheduled time on the wire is in server monotonic milliseconds for the current generation, and its name ends in `ServerMs`. Wall-clock time appears only in persistence and logs.
- Every string a tablet sends (display reports, status, errors) is untrusted. The server bounds sizes and rates, and the controller renders such strings with `textContent`, never as HTML.

### 11.2 Registration and welcome

The registration body gains two optional objects. `DeviceRegistration` ignores unknown fields today, so old servers accept the new body unchanged.

```jsonc
{
  "device_id": "0f8d6c1e-3b0a-4c47-9d0e-2f6b1d1c9a55",
  "width": 1080, "height": 810,          // kept for v1/v2 compatibility
  "device_type": "ipad",                 // kept; display only
  "display": {
    "viewportCss": [1080, 810], "screenCss": [1080, 810], "dpr": 2,
    "orientation": {"type": "landscape-primary", "angle": 90},
    "fullscreen": true, "standalone": false,
    "features": ["createImageBitmap", "waapi", "rvfc", "wakeLock", "mse"]
  },
  "client": {"userAgent": "Mozilla/5.0 (Macintosh; ...)", "build": "3f9a1c2e"}
}
```

The server validates `width` and `height` between 1 and 16384 and rejects anything else with 422. It bounds every other number and caps every string's length.

The welcome gains three fields:

- `server_ms`, for a first rough offset,
- `clock.pingIntervalMs`,
- `client_build`, a hash of the client files the server serves.

A tablet keeps the `client_build` from its first welcome after page load. When a later welcome carries a different value, the server is now serving newer code. The tablet reloads at a safe moment, such as an item boundary, at most once per 10 minutes.

### 11.3 Capabilities and downgrade

| Capability | Meaning | Server behaviour when a tablet lacks it |
| --- | --- | --- |
| `clock` | answers clock sync, honours `...ServerMs` times | content applies on arrival, no transitions |
| `status` | sends status frames | controller shows "no status" |
| `view` | applies server matrices | legacy placement fields |
| `playlist` | runs a playlist timeline | the item current at send time, as a still image |
| `video` | runs video sessions | the video's poster image, else colour |
| `command` | accepts identify, reload, setup | commands are refused for that tablet |

The server adds `clock`, `status`, `liveness`, `playlist`, `video`, `command` and `view` to `server_caps` as each one ships.

### 11.4 New frames

```jsonc
// tablet -> server
{"type": "time_ping", "id": 17, "t0": 53211.84}
{"type": "status", "seq": 88, "generation": "5c1f9a2e", "revision": 57, "sessionId": "s-7f3a",
 "phase": "presenting", "item": 2, "presentedAtServerMs": 831000.4,
 "clock": {"offsetMs": 759128.4, "uncertaintyMs": 3.1, "rttMinMs": 6.2, "samples": 24},
 "display": {"visible": true, "fullscreen": true, "wakeLock": "held", "rafHz": 60},
 "deliveryMs": 14.2}
{"type": "command_ack", "id": "c-91", "result": "done"}

// server -> tablet
{"type": "time_pong", "id": 17, "t0": 53211.84, "t1": 812340.12, "t2": 812340.31}
{"type": "command", "id": "c-91", "name": "identify", "args": {"seconds": 5}, "expiresServerMs": 832000}

// server -> controllers (coalesced to at most 2 per second per device)
{"type": "device_status", "device_id": "0f8d6c1e-...", "status": {"...": "latest status"}}
```

Notes on these frames:

- `t1` is stamped when the server reads the ping. `t2` is stamped by the socket writer just before sending.
- A tablet sends `status` when its phase changes, and otherwise at most every 5 s.
- The server drops status frames that arrive faster than 10 per second.

The wall frame gains `sentServerMs`, a `view` object for tablets with `view`, sessions inside `scene.content`, and renditions in image descriptors. Shape for one tablet in a physical layout:

```jsonc
{
  "type": "wall", "generation": "5c1f9a2e", "revision": 57, "sentServerMs": 812345.2,
  "wall": {"width": 1240, "height": 520, "units": "mm"},
  "placement": { /* legacy fields, still sent for older clients */ },
  "view": {
    "v": 1,
    "contentToCss": [5.197, 0, 0, 5.197, -77.96, -62.36],
    "contentWindowMm": [15.0, 12.0, 207.8, 155.9],
    "validFor": {"viewportCss": [1080, 810], "dpr": 2, "fullscreen": true},
    "latencyTrimMs": 0
  },
  "scene": {"content": {
    "type": "playlist", "loop": true,
    "items": [{
      "asset": "sha256:<hex>", "durationMs": 8000,
      "transition": {"kind": "crossfade", "durationMs": 1000},
      "image": {"intrinsic": [6000, 4000],
                "imageToContent": [0.20667, 0, 0, 0.20667, 0, -153.33],
                "renditions": [{"url": "/media/sha256:<hex>", "width": 4096, "height": 2731},
                               {"url": "/media/sha256:<hex>", "width": 2048, "height": 1365}]}
    }],
    "session": {"id": "s-7f3a", "state": "playing",
                "anchor": {"serverMs": 815000.0, "positionMs": 0},
                "start": {"policy": "all", "maxWaitMs": 3000, "leadMs": 300}}
  }}
}
```

A single image carries a session too, used only for its start time. Old clients ignore the session and show the image on arrival, as today.

### 11.5 HTTP additions

| Route | Allowed from | Purpose |
| --- | --- | --- |
| `POST /media?name=` | operator origin or loopback | upload, raw body |
| `GET /media` | operator | library list with status |
| `GET /media/sha256:<hex>` | tablet and operator | object bytes, byte ranges, immutable caching |
| `DELETE /media/{asset}` | operator | delete if unreferenced; 409 lists the references |
| `GET /devices/whoami?display=` | tablet | recover identity from the cookie |
| `POST /devices/{id}/commands` | operator | identify, reload, setup mode |
| `GET`, `PUT /displays/{id}` | operator | label, profile, calibration |
| `GET`, `PUT /device-profiles/{id}` | operator | model data |
| `PUT /wall/layout` | operator | replace the physical layout atomically |
| `POST /wall/session/{action}` | operator | play, pause, next, previous, seek |
| `POST /wall/bind` | operator | bind a slot or reservation to a device |

Every route that changes the wall returns `ETag: "<generation>:<revision>"`. When a request carries a stale `If-Match`, the server answers 412 with the current wall in the body. Requests without the header keep today's behaviour, so scripts and tests keep working. The controller always sends it.

The tablet allowlist in the Caddyfile adds:

- `GET` on `^/media/sha256:[0-9a-f]{64}$`,
- `GET /devices/whoami`,
- a pattern `^/client/[a-z0-9-]+\.(js|css)$` instead of naming each file, with a test that every file under `frontend/client/` matches it and nothing else is exposed.

Upload, library and session routes stay operator-only. Whether any target browser sends `HEAD` for media is unverified. Allow it on media paths only if a device needs it.

### 11.6 Ordering, stale commands and reconnect

1. Wall frames keep today's rule: a new generation resets, and within a generation a revision at or below the one held is ignored.
2. Session control actions are wall commits, so the revision rule orders them. The session id tells a tablet whether its prepared media is still valid.
3. A scheduled time already in the past when a frame arrives triggers late-join rules (section 12.4). Executing immediately as though the time were still ahead is wrong.
4. Commands carry an id and an expiry. Tablets ignore expired commands and ids they have already seen. Commands are not replayed on reconnect; only wall state is.
5. Operator writes carry `If-Match`. Live dragging serializes writes per controller: at most one request in flight, and pending moves collapse into the latest one.
6. Status frames name the generation, revision and session they describe. Readiness for the current start counts only matching reports.
7. A tablet acts on close codes only for its current socket:
   - 4409: show a conflict screen with "Take over", and stop reconnecting.
   - 4404: register again, then reconnect.
   - 4426: show "this page and the server disagree on the protocol version".
   - 4400: log it and back off.
   - 4408 and other codes: reconnect with backoff.
8. Reconnect sequence:
   1. register (with the display report),
   2. open the socket,
   3. welcome,
   4. receive the full wall frame,
   5. send a burst of eight clock pings while preparing content,
   6. present: static content immediately, timed content once uncertainty is below threshold or the scheduled time arrives,
   7. send status.
9. If the laptop sleeps, Linux's `CLOCK_MONOTONIC` (behind `time.monotonic()`) stops counting. This is known clock_gettime(2) behaviour that I did not re-check in this session. The server compares monotonic and wall-clock deltas every few seconds. After a jump of more than 1 s, it re-anchors sessions and tells tablets to resync.

### 11.7 Send path

Each socket gets an outbox and one writer task, in `tabletwall/hub.py`.

- The outbox has three lanes: clock replies first, then small control frames in order, then the latest wall frame.
- Wall frames are full state. A newer wall frame replaces an unsent older one in place, so a tablet that falls behind skips stale states instead of queuing them.
- A send that takes longer than 5 s closes the socket. The existing drop, close and offline-broadcast path then runs.
- `_broadcast_wall` only enqueues, so fan-out time no longer depends on the slowest tablet (D6).
- Ordering guarantees are unchanged: welcome before the replayed wall frame, and so on.

This touches load-bearing slot-ownership code, so the existing simulator scenarios must stay green, and new slow-socket scenarios are added.

## 12. Clock sync and scheduled presentation

### 12.1 Estimator

Each sample gives an offset and a delay from four times:

```
offset = ((t1 - t0) + (t2 - t3)) / 2
delay  = (t3 - t0) - (t2 - t1)
```

Here `t0` and `t3` are the tablet's `performance.now()` at send and receipt, and `t1` and `t2` are server monotonic milliseconds at receipt and send.

Cadence:

- a burst of 8 pings 60 ms apart after each welcome,
- then one every 2 s for 30 s,
- then one every 10 s,
- a fresh burst after `visibilitychange` to visible, `pageshow`, `online`, or a detected time jump (a timer that fires more than 1 s late).

Estimate and uncertainty:

- Keep the last 32 samples younger than 120 s.
- Select samples whose delay is within 2 ms of the window minimum.
- Take the median of their offsets.
- Uncertainty is half the median delay of the selected samples.

Applying the estimate:

- Changes under 20 ms are slewed at no more than 1 ms per 100 ms, so animations don't jump.
- Larger changes, typically after sleep, are stepped, and the tablet re-renders from the timeline.

The plan does not estimate rate skew. Crystal clocks differ by tens of parts per million, and at 50 ppm a 10 s resync interval accumulates 0.5 ms. Rate estimation is deferred until a measurement shows a need.

This is a pure module (`frontend/client/clock.js`), tested in Node with synthetic delay traces.

### 12.2 Scheduling and start policies

- `deadline`: the first commit fixes the start time at now plus a budget (3 s for images, 8 s for video). There is no second commit and no server timer. Tablets that are not ready by then join late.
- `all` (default for single images and video): the first commit sets the state to `preparing`. The server counts matching `ready` reports. When all bound, online, capable tablets are ready, or when `maxWaitMs` runs out, it commits `playing` with the anchor at now plus the lead.
- `quorum`: the same, with a fraction of tablets.
- Slideshow items need no start message. The timeline is known in advance, and tablets prefetch.

The lead starts at 300 ms (provisional). It adapts to the slowest recent 95th percentile delivery time, which tablets report as `deliveryMs` from `sentServerMs` and their clock estimate, plus a margin. Only human-rate control actions pay the lead.

Server-side timers use `loop.call_at` on the same event loop. They follow the commit-boundary rules: compute, commit, then broadcast, with nothing awaited mid-mutation.

### 12.3 Presenting at a time

The local target is the server time, minus the offset, minus the tablet's latency trim.

- Cut: switch layers in the frame callback whose timestamp is at least `target - period / 2`. That picks the frame closest to the target. The same rule on every tablet cancels the shared part of the delay.
- Crossfade with the Web Animations API, where available: create an opacity animation on the incoming layer and set its `startTime` to the target on the document timeline. Opacity animations can run on the compositor, which shields the fade from main-thread pauses. That the document timeline and `performance.now()` share a time origin is expected from the specifications, but this session did not verify it in each engine. The harness compares this path against the fallback.
- Crossfade fallback: set opacity in each frame callback from the shared clock, as a function of time, not frame count.
- Quiet window: tablets avoid starting decodes or other heavy work in the 500 ms before a scheduled change, finish preparing at least 2 s early when they can, and reuse layer canvases so a transition allocates nothing.
- When the page becomes visible again, the tablet computes the current item from the timeline and shows it without a transition.

### 12.4 Late join and recovery

- Slideshow: compute the position, the current item and any transition in progress. Prepare the current item first, show it with a cut, then resume prefetching.
- Video: seek to the expected position plus a learned seek delay, then let drift control settle it.
- A tablet that misses a slide's time keeps showing the previous slide (never black), reports `late`, and cuts to the current slide when ready if it is still within that slide's time.

### 12.5 Limits

- Delay asymmetry cannot be seen from round trips. If the uplink takes 5 ms and the downlink 60 ms, the offset is biased by 27.5 ms. The reported uncertainty (half the delay, 32.5 ms) still covers it. Choosing minimum-delay samples makes symmetric samples more likely, but this bias is the floor of NTP-style sync. Optical measurement finds residual per-device bias, and the latency trim can absorb a stable one.
- Browsers may coarsen `performance.now()` (documented in HR-Time). At the coarsening currently used this is negligible, but the estimator must not assume microseconds.
- Tablets' displays are not locked to one another. Vsync phase alone makes two 60 Hz panels differ by up to one frame. Section 16.1 works out the numbers.

## 13. Images: upload, processing, storage and backup

### 13.1 Trust model

The operator is trusted to choose content, but files are not trusted to be well formed. Phone photos carry location metadata, crafted files can target decoders, and any LAN peer can reach the server in the direct LAN mode the parent observed in use.

Rules:

- Uploads require either a configured operator origin with a matching `Origin`, or a loopback TCP peer. Without a configured operator origin, a request from another LAN address gets 403 with "uploads need the operator console on this computer".
- Tablets can never upload. The tablet ingress has no route for it.
- The server never accepts or serves SVG, HTML, PDF or any active format.

### 13.2 Upload route and limits

- `POST /media?name=<display name>` with a raw body and `Content-Type: image/jpeg | image/png | video/mp4`. There is no multipart parsing.
- The body streams to `media/incoming/<random>.part`, hashing as it goes and enforcing the cap byte by byte. If `Content-Length` is present and too large, the server refuses with 413 before reading.
- Default caps: 64 MiB for images, 4 GiB for video, library quota 20 GiB (all open question 7). If the upload would leave less than 2 GiB of free disk, the answer is 507.
- One upload in flight per client and at most four queued processing jobs. Beyond that the answer is 429 with `Retry-After`.
- Caddy's operator origin sets `request_body max_size` on `/media` as a second limit (413 from Caddy, documented).
- If the original's hash already exists, the server returns the existing asset and does not reprocess.

### 13.3 Processing pipeline

Processing runs in a subprocess (`python -m tabletwall.media_worker`) with resource limits (CPU seconds, address space) and a wall-clock timeout. That contains decoder crashes and keeps the event loop's clock replies accurate.

1. Sniff the magic bytes and require them to match the declared type: JPEG `FF D8 FF`, PNG `89 50 4E 47 0D 0A 1A 0A`, MP4 `ftyp` at offset 4.
2. Set `Image.MAX_IMAGE_PIXELS` to the app limit (64 MP default) and turn `DecompressionBombWarning` into an error. Check `size` before `load()`. Reject animated images, as today.
3. Apply `ImageOps.exif_transpose`, then drop all metadata (EXIF including GPS, XMP, IPTC, comments) by re-encoding without passing metadata through.
4. Convert colour to sRGB with `ImageCms` when an ICC profile is present, and assume sRGB when it is absent. Convert CMYK to RGB, 16-bit to 8-bit, and palette images to RGB or RGBA. Fixtures cover each case.
5. Downscale the master to at most 8192 px on the long edge. Renditions are 4096, 2048 and 1024 px plus a 320 px thumbnail, only those smaller than the master.
6. Encode baseline JPEG at quality 90 for opaque images (progressive JPEG can decode slower on old devices; unverified) and PNG when there is alpha.
7. Record `pipelineVersion` so renditions can be rebuilt from originals after a pipeline change.

Tablets choose the smallest rendition that still gives at least one image pixel per device pixel for their slice, because the slice size is known from the matrices. They draw the slice into a layer and release the decoded bitmap (`ImageBitmap.close()`), so memory holds layers, not images.

### 13.4 Store layout and serving

```
$TABLET_WALL_MEDIA_DIR/            default ./media, separate from the curated ./assets
  incoming/<random>.part           in-progress uploads, removed at startup
  objects/sha256/ab/cd/<64 hex>    every stored file, named by its own hash, mode 0444
```

- `GET /media/sha256:<hex>` looks the object up in an in-memory index loaded from `media_objects`, then returns `FileResponse` with `Cache-Control: public, max-age=31536000, immutable`, `X-Content-Type-Options: nosniff` and `Content-Security-Policy: sandbox`. Byte ranges come from Starlette.
- Store files are written by the app and verified at write time, so serving does not re-hash. An operator command can re-verify the store.
- The curated directory keeps today's rules and its stronger re-hash-on-serve guarantee, because the operator edits it by hand. Its inventory is cached by name, size, inode and modification time, so only changed files are re-hashed and re-decoded (D4).

### 13.5 Lifecycle, quotas and deletion

- `DELETE /media/{asset}` answers 409 with a list of the referencing scenes when the active scene or any saved scene uses the asset. Otherwise it removes the record and every object no other asset uses.
- Startup removes leftover `.part` files and objects no record references.

### 13.6 Backup and restore

- `deploy/backup.py` moves to manifest version 2 and adds the new tables to its expected-table list.
- Uploads have no other copy, so by default the backup includes every upload original and master, whether referenced or not. Renditions are optional because they can be rebuilt. Curated files keep today's referenced-only rule.
- A flag skips video originals for quick backups and warns that the backup is then incomplete.
- Restore verifies every hash. Version 1 backups still restore into a new target, and migrations run on the first start.
- Schema migrations take an automatic online backup of the database before the first pending migration and keep the last three (D11).

## 14. Slideshows

- Content: an ordered item list, a loop flag and defaults. Named playlists are saved scenes. Starting one makes a new session.
- Timeline: item start offsets are running sums of durations, and the total is D. The position at server time t is `anchor.positionMs + (t - anchor.serverMs)` while playing, modulo D when looping. The current item is the last one whose start is at or before the position. A crossfade into item j occupies the first T_j milliseconds of j.
- Controls are commits with `If-Match`, anchored at now plus the lead:
  - pause: anchor at the current position with rate 0,
  - play: the same position with rate 1,
  - next and previous: an anchor that puts the position at an item start.
- Edits to a playing playlist take effect at the next item boundary through a new session anchored there, so nobody sees a jump.
- Prefetch: each tablet keeps the current item and the next two prepared as viewport-sized layers. On the 10.2-inch iPad example that is 3 x 2160 x 1620 x 4 bytes, about 42 MB. Prepare times go into status.
- A missing or failed item follows the late-join hold rule. A failed asset is skipped on that tablet and reported, and the rest of the wall keeps the schedule.
- After a server restart, the persisted anchor also stores Unix time, so the timeline continues by elapsed wall-clock time. A wall-clock jump while the server was down shifts the resume point. That is acceptable.
- Tablets without `playlist` get the item current at send time as a still image, and the controller badges them.

## 15. Video

### 15.1 Prerecorded files and live input are different products

Prerecorded files have a known duration, can be fetched ahead, and can be seeked. Synchronization then only needs a shared timeline. Live input has a moving edge, needs an encoder and a segmenter running all the time, and trades delay against robustness. The plan ships prerecorded playback first and treats live input as a separate track (15.8) with its own decision point.

### 15.2 V1: progressive file playback

Accepted file shape, checked with `ffprobe`:

- MP4 container, H.264 (High or Main profile, level 4.2 or lower), 8-bit 4:2:0, constant frame rate up to 60 fps, up to 1920 x 1080 by default,
- AAC audio or no audio,
- the `moov` index before the media data ("faststart").

`ffprobe` runs in a subprocess with a timeout, a forced MP4 demuxer and `-protocol_whitelist file`, so a crafted file can't make it open other inputs. When only faststart is missing, the server remuxes losslessly (`ffmpeg -c copy -movflags +faststart`). Other mismatches are rejected with a suggested command. A starting point to validate on devices:

```
ffmpeg -i input.mov -c:v libx264 -profile:v high -level 4.1 -pix_fmt yuv420p -r 30 \
  -g 60 -keyint_min 60 -sc_threshold 0 -b:v 6M -maxrate 8M -bufsize 12M \
  -c:a aac -b:a 128k -ar 48000 -movflags +faststart output.mp4
```

The 2 s keyframe interval makes seeks during drift recovery cheap. H.264 is chosen because it has the widest decoder support (documented on MDN). Automatic transcoding on the server is open question 8. The default is off.

Serving uses `GET /media/sha256:<hex>` with byte ranges. iOS requires byte-range support from media servers (documented).

### 15.3 Buffering, chunking and delay options

- Full download (`buffer.kind = "full"`): the tablet fetches the whole file into a Blob and plays from an object URL. No network is used during playback, so stalls cannot happen. Memory equals file size, which limits it on old tablets; the safe size needs a device test.
- Buffer ahead (`buffer.kind = "ahead"`, default 10 s): the tablet uses the HTTP URL and reports ready once the buffered range ahead of the start position reaches `minAheadMs`. The browser chooses its own Range chunk sizes, and the app cannot control them.
- Deliberate chunking: segmented HLS in M9. The server cuts fixed 2 s segments, which bounds memory and allows bitrate switching.
- Start delay: the start policy's `maxWaitMs` and lead.
- For live input there is an explicit presentation delay (15.8).

### 15.4 Sync control

The expected position at server time t is `anchor.positionMs + (t - anchor.serverMs)`, modulo the duration when looping.

Measurement:

- With `requestVideoFrameCallback` (Baseline 2024, documented), each callback gives `mediaTime` and `expectedDisplayTime`. Map the display time to server time and compare with the expected position for that moment. The callback can run a frame late (documented), so use a median of 5.
- Without it, sample `currentTime` in frame callbacks and average over 1 s.

Control, starting values to tune on devices:

- Absolute error at or below the soft threshold (30 ms): rate 1, as a deadband against oscillation.
- Between soft and hard (1000 ms): `playbackRate = 1 - clamp(error / 2 s, -0.05, +0.05)`, updated at most every 500 ms. At this gain a 100 ms lead runs at 0.95 for about 2 s.
- Above the hard threshold, or after a stall: seek to the expected position plus the learned seek delay, then resume.
- Tablets where rate changes cause dropped frames (measured right after each change) switch to seek-only mode with a 60 ms deadband and report it.

Start:

1. Prepare: set the source, load, seek to the start position, wait for buffer or a full download, and confirm a decoded frame with `seeked` or a frame callback.
2. iOS may not buffer until `play()` is called (unverified). The prepare step can call `play()` muted and pause on the first frame. Muted `play()` needs no gesture on iOS (documented).
3. Report ready.
4. Call `play()` at the target minus a learned start delay (the time from `play()` to the first presented frame). Drift control takes over from there.

### 15.5 Audio, autoplay, loops and seeking

- Tablets play muted with `playsinline`. Muted autoplay is allowed in Chrome and on iOS, and unmuting without a gesture pauses playback on iOS (both documented). Chrome kiosks can also allow sound with enterprise autoplay policies (documented).
- Audio, when wanted, comes from one device: a chosen tablet that the operator taps once per page load to enable sound, or the controller's browser on the laptop, which already has a user gesture. That device follows the same timeline. Multi-tablet audio is a non-goal, because tens of milliseconds of offset between speakers is audible as echo.
- Loops: native `loop` with drift control fixing the restart gap. On Tier A tablets that can afford two decoders, an optional double-buffered loop preloads a second element at position 0 and starts it at the scheduled loop time. Each device's loop gap needs a test.
- Seeking from the controller is a session commit with a new anchor. Tablets seek to the anchor plus their learned seek delay.

### 15.6 Delivery options compared

| Option | Chunk and buffer control | Sync control | Support on target devices | Effort | Role |
| --- | --- | --- | --- | --- | --- |
| Progressive MP4 with byte ranges | browser decides; app can force full download | `currentTime`, `playbackRate`, seek, frame callbacks | broad; iOS needs byte ranges (documented) | low | V1 |
| HLS, native or hls.js | server segments, bounded memory, bitrate switching | same element controls | native in Safari and iPadOS; Chrome desktop 142 and later per caniuse, not confirmed by Chrome's release notes (unverified); Android needs a device check; hls.js needs MSE (iPadOS 13 and later) or Managed Media Source (Safari 17 and later) | medium | M9, and the base for live |
| Custom MSE or Managed Media Source pipeline | app fetches and appends chunks, full buffer control | full | MSE on iPadOS since Safari 13; Managed Media Source since Safari 17.0 on iPad and 17.1 on iPhone, which requires disabling remote playback or offering AirPlay (documented) | high | only if HLS control proves inadequate |
| WebCodecs into canvas | per-frame | frame-accurate within one device | secure contexts only, limited availability, no demuxer included (documented) | very high | deferred |
| WebRTC with a media server | network-driven jitter buffer | weak across receivers | broad for playback; needs signalling and a media server for many receivers | high | deferred; sub-second live only |

### 15.7 Bandwidth

Browsers cannot receive multicast, so every tablet downloads its own copy. Aggregate load is the number of tablets times the bitrate: 12 tablets at 6 Mbps is 72 Mbps sustained through one hotspot radio. That radio also carries the laptop's own Wi-Fi connection on the same channel, and its real capacity is unmeasured.

The plan answers this four ways:

- a network self-test command, where each tablet downloads a 10 MB object and reports throughput and round trips,
- full-download mode before a show,
- lower-bitrate renditions,
- later, per-tablet cropped renditions, so each tablet downloads only its slice at its own resolution. These are tied to a layout hash and rebuilt when the layout changes.

### 15.8 Live input (deferred, M9)

Decisions needed first: the source (laptop screen, HDMI capture card, network camera), the acceptable delay (default 3 s), and whether audio is needed.

The first approach:

- `ffmpeg` encodes and writes fMP4 HLS segments of 1 to 2 s, with `EXT-X-PROGRAM-DATE-TIME` taken from the server clock.
- Each tablet plays media time m at server time `PDT(m) + D`, where D is the fixed presentation delay set by the operator. The V1 drift control is reused.
- A larger D gives more robustness.
- Capturing the laptop screen on this Fedora Wayland desktop with `ffmpeg` is unverified. The fallback source is screen capture in the operator's browser (`getDisplayMedia` works on localhost as a secure context) feeding chunks to the server.
- WebRTC is reconsidered only if the product needs sub-second delay and accepts weaker cross-tablet alignment.

## 16. Sync targets, measurement and slow devices

### 16.1 What the physics allows

- Vsync phase: two independent 60 Hz panels show a scheduled change at their next refresh. With uniform random phases, the absolute difference d over a frame period F = 16.7 ms has `P(d <= x) = 1 - (1 - x/F)^2`. The mean is F/3 = 5.6 ms, and the 95th percentile is 0.776 F = 12.9 ms, before any other error.
- Display pipeline depth differs between models by an unknown number of frames. One to three frames (17 to 50 ms) is plausible (inferred), and measuring it is the point of section 18.5. The latency trim exists for this.
- A 30 fps video frame lasts 33 ms. Two tablets one frame apart differ by that much, however good the clock is.
- Clock error has the asymmetry floor from 12.5.
- The plan does not promise frame lock (genlock). Browsers expose no way to align refresh cycles across devices, and a page cannot know when its pixels actually changed.

### 16.2 Provisional targets

| Quantity | Provisional target | Measured by | If missed |
| --- | --- | --- | --- |
| Clock uncertainty, healthy tablet | p95 at most 5 ms | status reports | longer bursts before changes; flag the tablet |
| Estimator error against truth, harness, symmetric jitter up to 50 ms | p95 at most 2 ms | harness ground truth | fix the estimator |
| Software-observed onset spread, 12 harness contexts | p95 at most 10 ms | frame timestamps on the host clock | fix the scheduler |
| Slide change onset difference, healthy tablets | p95 at most 50 ms, stretch 33 ms | optical | latency trims; animation path; less work near changes |
| Video steady-state offset between tablets, 10 min | p95 at most 50 ms, median at most 20 ms | optical with flash test clip, plus drift reports | tune gains; lower rendition; tier fallback |
| Video start alignment | all within 100 ms by 3 s after start | optical | longer prepare; learned start delay |
| Seam continuity after calibration, fullscreen | at most 1 mm | vernier pattern and photo | recalibrate; check the profile |
| Correct content after Wi-Fi returns | within 5 s | harness and tablets | watchdog tuning |
| Prefetch finished before slide time | at least 2 s early for 95% of slides | status | smaller rendition; tier fallback |
| Upload to ready, 20 MP JPEG on the laptop | at most 10 s | server timing | worker tuning |
| Clock reply service delay during processing | p99 at most 20 ms | server metric | move more work out of process |

These targets get revised after the first optical data. Reports always say whether a number is a target or a measurement.

### 16.3 Measurement methods

- Software-observed onsets are frame callback timestamps converted to server time. They are cheap and work on every tablet and in the harness. They are blind to display delay, so they track regressions and do not prove synchronization.
- Harness ground truth: every context shares the host clock, and so does the server. `performance.timeOrigin + performance.now()` in each context maps to host epoch milliseconds, which gives true software onsets and true estimator error without trusting the estimator (18.3).
- Optical measurement (18.5) is the only measure of what a viewer sees.

### 16.4 Slow devices

Tiers are assigned from features and adjusted from measurements:

- Tier A has frame callbacks for video, `createImageBitmap`, the Web Animations API and fullscreen. It gets everything.
- Tier B is older but meets the ES2017 floor. It gets images and slideshows with frame-callback crossfades or cuts, video with `currentTime` sampling, and smaller renditions.
- Tier C covers tablets that are repeatedly late, drop many frames or get killed for memory. They get cuts only, 1024 px renditions and a longer lead, and video becomes the poster image. They are flagged in the controller.

A tablet is demoted after three late prepares or a stall pattern within 10 minutes. The operator can override the tier. One slow tablet never holds the wall past `maxWaitMs`.

## 17. Layout editor

### 17.1 Model and rendering

- The editor is SVG in millimetres with a `viewBox`, zoom and pan. Each slot is a group with body, active area, label, an orientation arrow and status colour.
- New controller code is written as ES modules, because the controller runs in the operator's modern browser. The tablet client stays on classic ES2017 scripts.
- Editor state is a reducer over commands (move, rotate, bind, group, align), which gives undo and redo, and Node tests import it directly (D13).
- The existing `controller.js` exposes a small interface (`getState`, `subscribe`, `request`) for the new modules instead of being rewritten.

### 17.2 Interaction

- Pointer drag uses `setPointerCapture` and `touch-action: none` on the canvas. A 4 px threshold separates a tap from a drag. Moves are throttled to frame callbacks. Escape cancels a drag and restores the start pose.
- Snapping goes to other bodies' edges with a gap preset (0 mm, the measured gap, or custom), to centre and edge alignment guides, and to a 1, 5 or 10 mm grid. Holding Alt disables it. Live gap readouts show millimetres to each neighbour.
- Multi-select by Shift-click or marquee. Group drag, align and distribute, and a grid generator (rows, columns, model, gap).
- Rotation is in 90 degree steps with a button or the R key. Fine rotation is only in the inspector.
- Keyboard: Tab moves between slots with a roving tabindex. Arrow keys move 1 mm, with Shift 10 mm and Alt 0.1 mm. R rotates, Enter opens the inspector, Delete unbinds after confirmation, and Ctrl+Z and Ctrl+Shift+Z undo and redo. A live region announces results, for example "Tablet A3 moved to x 412 mm, y 120 mm, 9.5 mm from A2".
- WCAG 2.2 success criterion 2.5.7 requires a single-pointer way to do anything that dragging does, and says keyboard support alone does not satisfy it (documented). The editor therefore has on-screen nudge buttons for the selection, numeric inspector fields, and a "move to" mode where the operator taps a slot and then taps the destination.

### 17.3 Identification, preview and apply

- "Identify" flashes the tablet with its label. "Locate" puts tablets in setup mode, where a tap highlights the matching shape. "Show labels" labels every tablet at once.
- Preview draws the current content behind the slots at wall scale, with opaque bezels, so the operator sees each tablet's crop and the seam policy's effect before applying.
- Drafts are local until Apply, which sends one `PUT /wall/layout` with `If-Match`. Live mode, intended for calibration, applies each move at a few updates per second with serialized writes, so the operator can watch the real wall.
- Warnings, not blocks:
  - overlapping bodies (physically impossible, so usually a measurement error),
  - slots outside the wall,
  - unbound slots,
  - uncalibrated or stale-calibrated tablets,
  - tablets not in fullscreen.
- Saved layouts hold slots, bindings, profile snapshots, seam policies and the content rectangle. Recall rebinds by device identity. An unbound slot offers "Bind" with a list of unplaced online tablets and pairing-code confirmation. JSON export and import support sharing between walls.

## 18. Test layers

### 18.1 L0: unit tests and golden vectors

- `tests/fixtures/geometry/*.json` hold inputs (layout, profile, calibration, viewport, content, seam policy) and expected outputs (matrices, content windows, coordinates at viewport corners). The same files are consumed by pytest (server geometry and the simulator oracle), by the tablet tests (legacy mapping today, matrix application later) and by the editor's tests. A script regenerates them, and the diff gets reviewed. This contains D10.
- Pure tablet modules (clock estimator, timeline math, drift controller, rendition choice) get Node tests with synthetic traces.
- A syntax guard keeps tablet scripts at ES2017. Use a parser pinned to ES2017 if a small dev dependency is approved, and otherwise a scanner for common later syntax (`?.`, `??`, `catch {`, class fields, numeric separators).
- Media fixtures:
  - images: EXIF-rotated, GPS-tagged, CMYK, 16-bit PNG, palette with transparency, animated PNG, truncated, bomb dimensions, a polyglot (valid JPEG header with trailing HTML), a wrong extension, oversized,
  - videos: no faststart, VFR, HEVC, 4K, audio-only.

### 18.2 L1: the existing API simulator

It stays as the fast, deterministic protocol and geometry layer. New scenarios:

- identity replacement storms (two sockets alternating) and the new conflict behaviour,
- `If-Match` and 412 on every write route,
- outbox ordering, coalescing and slow-socket isolation,
- readiness counting and deadline timers,
- playlist timeline math on the server, and restart re-anchoring,
- capability downgrades for each new content type,
- upload API errors.

Its README limitations stay, unchanged in substance.

### 18.3 L2: real-browser harness

Layout: a new top-level `browser_harness/`, mirroring `simulator/`.

- `server.py` starts `uvicorn main:app` as a subprocess on `127.0.0.1` and a random free port. It sets `TABLET_WALL_DB`, `TABLET_WALL_ASSET_DIR` and `TABLET_WALL_MEDIA_DIR` to a fresh temporary directory. It refuses to run if any of them points outside that directory, or if the port is 8000 or already in use. It kills the server on exit. It never touches the operator's wall.
- `proxy.py` is a per-client asyncio TCP proxy. Each direction gets its own delay distribution, jitter, bandwidth cap, periodic holds that roughly model Wi-Fi power save, blackhole windows (traffic stops, sockets stay open) and resets.

  A userspace TCP proxy cannot drop packets. TCP turns loss into delay, so loss is modelled as delay spikes and stalls. Real packet loss would need kernel tools such as `tc netem`, which need root, and this plan does not use root.

  Each client gets its own proxy port, and so its own origin, which also isolates storage.
- `fleet.py` describes each client:
  - engine: Playwright Chromium, Firefox or WebKit,
  - isolation: a context in a shared browser, or a separate browser process with its own profile directory,
  - viewport, `deviceScaleFactor`, mobile and touch flags (Chromium), portrait or landscape, and a label,
  - impairment profile and clock skew.
- `probes.js` is an init script. It enables the tablet's `?debug=1` event log hook, and it can wrap `performance.now()` and frame callback timestamps with an injected offset and rate.

  That wrapper does not move `document.timeline` or media clocks, so skew tests use the frame-callback animation path. This limitation is recorded in every report.
- Chromium-only hooks through the DevTools Protocol: CPU throttling for slow-decode tests, and page lifecycle freeze and resume for background tests. Visibility changes come from bringing another tab to the front in headed mode. All of these need verifying in the harness ticket.
- Screenshots of a coded calibration pattern, which encodes wall millimetre coordinates in coloured blocks, let the harness check what each viewport shows at its edges.
- The JSON report goes outside the repo and always includes a limitations section.

Video in the harness: Playwright's bundled Chromium lacks some codecs that branded Chrome includes, and Playwright's WebKit on Linux differs from Safari for media (both documented). Harness video tests therefore use VP9/Opus WebM versions of the test clips, which exercise the sync logic. H.264 behaviour is a device test. A Flatpak Chrome could be reached through `connect_over_cdp` as an optional extra.

Headed windows that overlap can have their frame callbacks throttled. Run headless, or use Chromium switches that disable occlusion and background throttling, and verify those switches in the chosen version.

Starting scenarios:

1. Identity isolation: 12 contexts in one browser plus 4 separate browser processes give 16 identities, 16 sockets and 16 roster entries.
2. Collision, the negative case: two pages in one context without `?display=`. One shows the conflict screen, and there are no more than two connection attempts in 30 s.
3. `?display=a` and `?display=b` in one context give two identities.
4. Clearing local storage and reloading recovers the same identity from the cookie.
5. Heterogeneous geometry: 1024x768 at DPR 2, 1180x820 at 2, 1280x800 at 1.5, 800x1280 at 2 (portrait), 1920x1200 at 1. Coded-pattern screenshots must match the expected wall coordinates within one CSS pixel at every edge.
6. Toolbar resize: shrinking the viewport height by 60 px without a reload keeps the canvas box and backing store consistent (D3).
7. A proxy reset reconnects, and a 30 s blackhole triggers the watchdog. Both return to correct content.
8. A server restart (new generation) resumes content.
9. Latency, jitter and asymmetric delay: estimator error and reported uncertainty against ground truth.
10. Clock offset of plus or minus 5 s and drift of plus or minus 200 ppm.
11. A 20 s freeze and resume brings a resync and a catch-up without a transition.
12. One context at 6x CPU throttle with 4096 px renditions: the deadline policy proceeds, and that context joins late.
13. A reload during a slideshow rejoins the current item.
14. Uploading a 60 MP image while 12 clients run a slideshow leaves clock reply service delay unaffected.
15. Later, video stall: a bandwidth cap below the bitrate on one context, then recovery.

Isolation, stated plainly:

| Setup | Own storage and identity | Own socket | Own process | Own clock | Own radio and RF path | Own display pipeline |
| --- | --- | --- | --- | --- | --- | --- |
| Windows in one browser profile | no | yes, but they replace each other | no | no | no | no |
| Playwright contexts in one browser | yes | yes | partly | no | no | no |
| Separate browser processes | yes | yes | yes | no | no | no |
| Phones and tablets on the hotspot | yes | yes | yes | yes | yes | yes |

Distinct sessions and connections are what the harness provides. Independent radios, clocks, decoders and displays exist only on physical devices. Injected skew emulates a separate clock but does not create one.

### 18.4 L3: physical tablet matrix

Rows are devices: model, OS version, browser and version, recorded automatically from the first display report. Columns are modes (browser tab, fullscreen, Home Screen app) crossed with tests:

- viewport report against a measured box,
- calibration accuracy,
- decode time per rendition size,
- slideshow software-observed and optical onsets,
- 1080p30 H.264 at 4 and 8 Mbps,
- rate-change smoothness, seek delay and loop gap,
- sleep and wake, Wi-Fi off and on, reload, server restart,
- wake lock, and a 2-hour soak.

Results:

- Reports go to a dated directory outside the repo. Sanitized display reports become fixtures under `tests/fixtures/devices/`.
- Phones add cheap extra independent radios.
- Android Chrome can be driven over USB debugging. iPads can be driven with `safaridriver` only through a Mac.

### 18.5 L4: optical measurement

- A `sync-flash` calibration pattern: black, with a white flash of 100 ms at scheduled times every 2 s. A block code in one corner shows the flash index, so flashes can be matched across tablets.
- A matching test clip, generated with `ffmpeg`'s `testsrc2`, `drawtext` frame numbers and a white frame every 2 s, in H.264 for devices and VP9 for the harness.
- Capture with a phone at 240 frames per second (4.17 ms per frame) with all tablets in view, for at least 30 flashes.
- `tools/optical/analyze.py` crops a region per tablet with `ffmpeg`. It reads per-frame mean luminance from the `signalstats` filter, finds each onset at the 50% crossing with interpolation between frames, matches flashes by index, and writes per-pair distributions plus per-device mean bias, which suggests latency trims. It needs no new Python dependency.
- Error sources to control:
  - rolling shutter: keep tablets in one horizontal row of the camera image, or rotate the camera so its scan runs along the row,
  - panel response time: use the 50% crossing,
  - the phone's real capture rate: verify it.
- Measure the method's noise floor first: one tablet shows the flash in two halves of its own screen at the same refresh, so the expected offset is zero.
- Photodiodes on a microcontroller sampling above 2 kHz would remove rolling shutter. They are optional hardware, and deferred.

### 18.6 What a desktop cannot prove

- Any end-to-end synchronization number for real tablets. Display delay, panel response and refresh phase belong to the device.
- Real Wi-Fi behaviour: contention for airtime, power-save buffering, interference, and the hotspot's single-radio channel constraint. The proxy only adds the delays it is told to add.
- Real decoders: hardware decode limits, memory kills, thermal throttling. Headless Chromium may decode in software.
- iPadOS Safari policies: autoplay, storage caps, background suspension.
- Physical millimetres, bezels and viewing angles.
- Clock behaviour across real tablet sleep.

The harness proves logic, isolation, recovery and regressions. Its timing numbers are lower bounds on real error.

### 18.7 Continuous integration

- L0 and L1 run on every change, part of README Phase 3d.
- L2 runs Chromium headless with loose timing bounds, nightly or on demand. Firefox and WebKit runs start local-only.
- L3 and L4 run before a release and after any change to timing, rendering or media code. Results are kept with dates and labelled as measurements.

## 19. Milestones

The suggested order follows. The slice is complete after M4. M5 and M6 can swap with M7 if video matters more (open question 12).

```
M0 foundations ----+--> M2 media ------+--> M4 slideshow (slice 1) --> M5 physical --> M6 editor
M1 harness --------+--> M3 timing -----+                               |
                                                                       +--> M7 video --> M9 segmented and live
M8 field readiness runs alongside, gated by HTTPS on real tablets
```

### M0. Foundations

Goal: trustworthy identities, sizes, writes and fan-out before timed media.

Depends on: nothing.

Tasks:

1. Tablet close-code handling as in 11.6, acting only on the current socket.
2. `?display=<name>` namespaces the storage key and the default label.
3. A server-set identity cookie (`HttpOnly`, `SameSite=Strict`, and `Secure` on HTTPS) and `GET /devices/whoami`. The cookie only recovers an identity when local storage is empty. It never overrides a stored identity and is never used for authorization.
4. A controller action that binds a vacant reservation to an unplaced online tablet, confirmed by a 4-character code the tablet shows in setup mode.
5. Size the canvas backing store and mapping from the element's measured box, report that box as the viewport, and listen to `visualViewport` resizes where available.
6. The display report at registration. Bounds checks on registration sizes. `device_type` becomes display-only.
7. Reject negative bezels and unknown keys on new placement writes. Keep accepting legacy snapshots as written.
8. `ETag`, `If-Match` and 412 on wall routes, with controller handling.
9. Per-socket outboxes (11.7) for tablets and controllers.
10. A `liveness` server capability: the server answers pings, and the tablet watchdog reconnects after three missed replies. Handle `visibilitychange`, `pageshow` and `online`.
11. Schema versioning with `PRAGMA user_version`, ordered migrations run once at startup, and a pre-migration backup. Stop re-running DDL on every connection.
12. Golden geometry vectors for today's mapping, plus a first controller test file.
13. The ES2017 guard, and the client path pattern in the Caddyfile with its test.

Modules: `frontend/client/client.js` and `client.css`; `main.py` (`DeviceRegistration`, `Bezel`, `PlacementCommand`, `device_register`, `ws_device`, `_device_loop`, write routes); `tabletwall/hub.py`; `tabletwall/persist.py`; `frontend/controller/controller.js`; `deploy/hotspot.Caddyfile`; `deploy/load-smoke.py`; `PROTOCOL.md`; tests; simulator scenarios.

Acceptance:

- Existing tests and simulator scenarios pass unchanged.
- New tests cover each close code, cookie recovery, 412 on each route, outbox ordering and coalescing, and slow-socket isolation (a stalled socket delays no other socket's frame by more than 50 ms in the simulator).
- Harness scenarios 1 to 8 pass once M1 lands.
- One physical tablet shows the D3 check values in tab mode and in fullscreen.

Risks:

- The send path is load-bearing. Mitigation: keep slot ownership checks exactly as they are, and add scenarios.
- The cookie adds a second identity source. Mitigation: it only fills an empty slot, and mismatches are logged.

Migration: the database is stamped `user_version = 1` with no content change. Old tablets on the new server and new tablets on an old server both keep working, because every new behaviour is capability-gated.

Deferred: coordinating same-identity tabs with `BroadcastChannel`.

### M1. Real-browser harness

Goal: a fleet of isolated real browser clients against a throwaway server, with impairments, before timing work starts.

Depends on: M0 task 1, and approval to add Playwright for Python as a dev dependency. Its version must match the cached browsers, or browsers must be installed while online.

Tasks: section 18.3, starting with scenarios 1 to 8 and the minimal proxy (delay, blackhole, reset). Jitter, asymmetry and skew come in M3.

Modules: new `browser_harness/` with its README; a small `?debug=1` hook in `client.js`; a dev dependency group in `pyproject.toml`.

Acceptance: as in 18.3 scenarios 1 to 8; a run takes under 5 minutes; a test asserts the temporary paths and the port.

Risks: flaky timing assertions (keep bounds loose and leave tight bounds to L4); occlusion throttling; browser version drift.

Deferred: Firefox and WebKit in CI.

### M2. Media library and image uploads

Depends on: M0 schema versioning.

Tasks:

- the store and its tables, the upload route, the processing worker, renditions,
- listing, serving and deletion with reference checks, startup cleanup, quota,
- renditions in image descriptors and rendition choice on tablets,
- the controller media panel (drop zone, progress, errors, thumbnails),
- the curated inventory cache,
- Caddy allowlist and body limit,
- backup manifest version 2,
- `PROTOCOL.md`.

Modules: new `tabletwall/media.py` and `tabletwall/media_worker.py`; `main.py` routes; `tabletwall/assets.py`; `tabletwall/persist.py`; `client.js`; `controller.js`; `deploy/hotspot.Caddyfile`; `deploy/backup.py`; new `tests/test_media.py` and fixtures.

Acceptance:

- Every fixture is accepted and normalized, or rejected with its specific reason.
- With no operator origin configured, an upload from a non-loopback LAN address is refused.
- A 1 GB body is cut off at the limit with 413, with no memory growth.
- Twenty harness clients fetching one rendition cause zero rescans (a counter shows it), and range requests return 206.
- Backup and restore into a new path reproduces the library with every hash verified.

Risks: decoders on hostile input (subprocess, limits, timeouts); disk exhaustion (quota and free-space check); colour conversion edge cases (fixtures).

Migration: the migration adds tables. Curated assets keep their IDs and routes, and existing scenes are untouched.

Deferred: WebP, AVIF and HEIC input; per-tablet cropped renditions; serving media through Caddy `file_server`.

### M3. Timing core: status, clock, prepare and show

Depends on: M0 (outbox, liveness), and M1 for testing.

Tasks:

- status frames, a server status table (memory only), and the controller health panel with an event log,
- clock ping and pong, with stamping in the outbox writer,
- the estimator module, the server time base, and laptop sleep detection,
- `clock`, `status` and `command` capabilities,
- scheduled presentation for image changes with start policies, server timers and adaptive lead,
- presentation at a time with the animation path and the fallback,
- late join and delivery latency measurement,
- identify, reload and setup commands with acknowledgements, plus client build detection,
- the `sync-flash` pattern and `tools/optical/analyze.py`.

Modules: new `tabletwall/clock.py` and `tabletwall/sessions.py`; `main.py`; `tabletwall/hub.py`; new `frontend/client/clock.js` and `frontend/client/stage.js`; controller panels; `tools/optical/`; tests; simulator and harness scenarios.

Acceptance:

- Harness estimator error and software onset targets from 16.2 are met.
- Uncertainty covers bias under asymmetric delay.
- A throttled context does not delay the others under the deadline policy.
- Two physical tablets have a recorded optical sync-flash distribution, judged against the provisional 50 ms target.

Risks:

- Event-loop pauses skewing server stamps. Mitigation: the subprocess worker and a service-delay metric.
- Power-save delay. Mitigation: bursts before scheduled changes.
- Engine differences in animation timing. Mitigation: compare both paths in the harness and on devices.

Migration: none for data. Old tablets keep showing changes on arrival.

Deferred: rate-skew estimation.

### M4. Slideshows (completes slice 1)

Depends on: M2, M3.

Tasks:

- the playlist content type and validation, and named playlists as saved scenes,
- session controls as commits,
- shared timeline math with golden vectors,
- tablet prefetch and layered rendering, cut and crossfade, the missing-item rule,
- restart re-anchoring, and edits applied at item boundaries,
- the controller playlist editor, with reorder by drag and by buttons,
- live progress, and the fallback for tablets without `playlist`.

Modules: `main.py` scene validation; `tabletwall/sessions.py`; `tabletwall/persist.py` content versioning; new `frontend/client/timeline.js`; controller playlist UI; tests; simulator and harness scenarios.

Acceptance: section 7.2.

Risks: memory on old tablets (bounded layers, rendition choice); janky fades on Tier B (cut fallback).

Deferred: time-of-day schedules, pan-and-zoom effects, and transition types beyond cut and crossfade.

### M5. Physical geometry and calibration

Depends on: M0 (identity, binding), M3 (commands), and M1 (screenshots). It should come after the HTTPS origin decision, so calibration is recorded against the final origin.

Tasks:

- `device_profiles` and `displays` tables and routes,
- `PhysicalLayout` with slots and bindings,
- `tabletwall/geometry.py` for matrices, content windows and seam policies,
- the `view` capability on tablets for images, patterns and slideshows,
- calibration flows on the tablet (profile, card, ruler) and in the controller,
- alignment and vernier patterns, live nudge mode, and the latency trim field,
- conversion from abstract layouts,
- the simulator oracle in millimetres, and golden vectors.

Modules: new `tabletwall/geometry.py`; `main.py`; `tabletwall/persist.py`; new `frontend/client/view.js`; controller calibration panels; `simulator/geometry.py`; tests.

Acceptance:

- Harness coded-pattern checks pass within one CSS pixel for 8 mixed contexts, including portrait and rotated slots.
- At least two tablets of different models in fullscreen show lines continuous across seams within 1 mm after calibration (photo plus vernier).
- A replaced tablet rebinds to its slot without re-placement.

Risks:

- Tab-mode offsets differ per browser. Mitigation: support fullscreen and Home Screen first, and label tab mode "approximate".
- Wrong profile data. Mitigation: show the source, and let a measurement override it.

Migration: abstract layouts are untouched. Conversion creates new layouts.

Deferred: camera-based automatic calibration, and per-device colour and brightness trims.

### M6. Layout editor

Depends on: M5, and M0 (`If-Match`).

Tasks: section 17, with Node tests for the editor state model and harness UI tests driving pointer, keyboard and tap-only input.

Modules: new `frontend/controller/editor/*.js` (ES modules); a small interface in `controller.js`; `PUT /wall/layout`; tests.

Acceptance:

- A hallway test (provisional): an operator arranges 6 tablets of 2 models into a 3 x 2 grid with 10 mm gaps in under 3 minutes three times, once each with touch only, keyboard only and taps only.
- Every action works without dragging.
- A concurrent edit from another window produces a 412 and a reload prompt, never silent loss.

Risks: scope creep in UX details; editing 30 or more slots (SVG is fine at that scale).

Deferred: freeform rotation handles, and irregular content masks.

### M7. Prerecorded video V1

Depends on: M2, M3, and preferably M5.

Tasks:

- `ffprobe` validation with lossless faststart remux, poster extraction and rejection guidance,
- the `video` content type and session,
- the tablet video module (15.2 to 15.5),
- audio designation and media fields in status,
- the network self-test command,
- the test clip generator (H.264 and VP9) and optical analysis for video,
- a CPU measurement of Python serving at real bitrates.

Modules: `tabletwall/media.py` and the worker; `tabletwall/sessions.py`; new `frontend/client/video.js`; the controller video panel; `tools/media/make-test-clips.sh`; `tools/optical/`; tests.

Acceptance:

- Harness (WebM): 8 contexts stay within 50 ms software-observed drift at the 95th percentile through jitter and a 5 s stall on one context.
- Devices: at least two tablets play a 10-minute 1080p30 H.264 clip within the 16.2 video targets, and recover to within 100 ms in under 5 s after a 10 s Wi-Fi loss.
- Tier C tablets fall back to the poster image without holding the others.

Risks:

- Rate changes stutter on some devices. Mitigation: seek-only mode.
- iOS preload behaviour. Mitigation: muted play-and-pause priming.
- Hotspot bandwidth. Mitigation: the self-test, full download, lower bitrate.
- Python serving cost. Mitigation: measure, then consider Caddy `file_server`.

Deferred: HLS, per-tablet cropped renditions, multi-tablet audio.

### M8. Field readiness

Depends on: README Phase 3a and 3b, and real tablets. Any milestone can reach tablets earlier in plain HTTP mode, with reduced features.

Tasks:

- HTTPS trust for each tablet model (local CA), then the origin switch with rebinding,
- Screen Wake Lock, reacquired on visibility change (documented requirements: secure context, released when hidden),
- a Home Screen web app manifest and guidance,
- kiosk guidance: Guided Access, Android screen pinning, Auto-Lock set to never on the tablets,
- an 8-hour slideshow soak and a 1-hour video soak,
- a backup and restore drill, and a load smoke with media,
- `Content-Security-Policy` headers for both pages,
- the operations documentation, and every `deploy/KIOSK.md` gate with dated evidence per device.

Acceptance: every gate has a dated result per device; the soak completes without manual intervention; the restore drill completes.

Deferred: a service worker offline cache, which also requires HTTPS (documented for Cache Storage).

### M9. Segmented video and live input (conditional)

Depends on: M7 results, and a product decision on sources and acceptable delay.

Tasks:

- HLS VOD packaging with fMP4 segments of 2 s,
- a tablet HLS path: native where the device check passes, otherwise a vendored and pinned `hls.js` over MSE or Managed Media Source,
- live capture and segmenting with `EXT-X-PROGRAM-DATE-TIME` from the server clock,
- an operator setting for presentation delay,
- reuse of the V1 drift control.

Acceptance (provisional): live delay equals the configured value within 0.5 s, and inter-tablet offset matches the V1 video targets.

Deferred: WebRTC and WebCodecs.

## 20. First ten tickets

Each ticket is meant to fit one reviewable change. Sizes are rough: S is about a day, M a few days, L about a week.

T1. Tablet close codes and identity hygiene (M0, size S to M).

- Scope: close-code handling for the current socket only, the conflict screen with "Take over", `?display=`, the identity cookie and `GET /devices/whoami`, and the Caddy allowlist entry.
- Touches: `client.js` (`resolveDeviceId`, `openSocket`, `run`), `main.py` (`device_register`, new route), `deploy/hotspot.Caddyfile`, `tests/client_*.test.js`, `tests/test_websocket.py`, `tests/test_security.py`, `PROTOCOL.md`.
- Done when: tests cover every close code and cookie recovery, and a manual two-tab check shows one conflict screen and no loop.

T2. Browser harness skeleton with a minimal proxy (M1, size M).

- Needs: Playwright dev dependency approval.
- Scope: the safe launcher, the fleet of contexts and separate processes, the proxy with delay, blackhole and reset, the debug hook, screenshots, the report.
- Done when: scenarios 1 to 4 pass with 16 clients, and the safety assertions hold.

T3. Measured render box and display report (M0, size S).

- Scope: canvas sizing from the element box, the `display` and `client` objects at registration, server bounds, the `visualViewport` listener, the debug overlay values, harness scenario 6.
- Done when: scenario 6 passes, and one physical tablet's tab-mode and fullscreen values are recorded.

T4. Write preconditions, outboxes and liveness (M0, size M to L).

- Scope: `ETag`, `If-Match` and 412; controller conflict handling; per-socket outboxes; the `liveness` capability and tablet watchdog; visibility, `pageshow` and `online` handling; slow-socket simulator scenarios; harness scenario 7.
- Done when: the M0 acceptance for these items is met, with all existing tests green.

T5. Schema versioning and media store foundation (M0 and M2, size M).

- Scope: migrations with pre-migration backup; the `media_objects` and `media_assets` tables; the store and startup cleanup; `GET /media/sha256:<hex>` through `FileResponse`; the curated inventory cache; the tablet allowlist; `backup.py` manifest version 2.
- Done when: migrations from saved version-0 databases preserve content; tests cover single, suffix and unsatisfiable ranges; 20 harness clients cause zero rescans; backup and restore round-trips.

T6. Image upload pipeline and media panel (M2, size L).

- Scope: the streaming upload with limits and sniffing, the worker subprocess, renditions, deletion with reference checks, quota, the controller drop zone and list, fixtures.
- Done when: the M2 acceptance is met.

T7. Status channel and health panel (M3, size M).

- Scope: `status` frames and capability, the server status table, coalesced `device_status`, the controller health panel and event log, the identify command with acknowledgement.
- Done when: 12 harness contexts show live phases, identify flashes the right page, and steady-state status traffic is under one frame per second per tablet.

T8. Clock sync (M3, size M).

- Scope: `tabletwall/clock.py` with sleep detection, ping and pong stamped in the outbox, `frontend/client/clock.js` with Node trace tests, bursts and resync triggers, clock fields in status, proxy jitter and asymmetry, skew injection, harness ground truth.
- Done when: the estimator targets in 16.2 are met in the harness, and a 10-minute offset and uncertainty log from one physical tablet is recorded.

T9. Scheduled image changes and optical measurement kit (M3, size L).

- Scope: prepare and show with start policies and server timers, presentation at a time with both animation paths, late join, latency trim plumbing (default 0), the `sync-flash` pattern, `tools/optical/analyze.py`.
- Done when: the software onset target is met in the harness, and a first optical distribution from two tablets is recorded with the raw video kept outside the repo.

T10. Slideshow sessions (M4, size L).

- Scope: M4.
- Done when: the slice 1 acceptance in section 7.2 is met.

After T10, in order:

1. physical geometry core (`geometry.py`, profiles, displays, the `view` capability),
2. calibration flows and patterns,
3. slots, bindings and layout conversion,
4. the layout editor,
5. video V1,
6. field readiness.

## 21. Open product questions and defaults

1. Which tablets exactly: models, OS and browser versions, how many? Default: assume at least one iPad running iOS 12 to 15 and one older Android Chrome, keep the ES2017 floor, and record every tablet's report on first connect.
2. Browser tab, fullscreen or Home Screen? Default: physical alignment targets apply only to fullscreen and Home Screen modes. Tab mode is supported and labelled approximate.
3. Move tablets to HTTPS? Default: yes, before calibration data is recorded (D2), using the existing Caddy reference. Plain HTTP stays for development.
4. Audio? Default: a silent wall, with one optional audio device in M7.
5. Default seam policy? Default: physical gaps.
6. Does "share an image" include phones or tablets in the room sending pictures? Default: the operator laptop only for now. A guarded "share from phone" page on the operator origin with authentication could come later.
7. Upload limits? Default: images up to 64 MiB and 64 MP, stored master up to 8192 px on the long edge; video up to 4 GiB, 1920 x 1080 and 60 fps, H.264 High at level 4.2 or lower; library quota 20 GiB.
8. Transcode video on the server? Default: no automatic transcoding in V1, only the lossless faststart fix and a suggested command. An optional background transcode can come later.
9. What happens when a tablet isn't ready at a slide change? Default: the wall proceeds at the deadline, the late tablet holds the previous slide, then cuts when ready.
10. Resume after a server restart? Default: continue the timeline by elapsed wall-clock time.
11. Is live video needed, from what source and at what delay? Default: deferred. Decide the source and accept a 3 s delay before M9 starts.
12. Editor before video? Default: editor first; swap if video matters more.
13. Several operators at once? Default: allowed. Conflicts get 412 and a reload prompt.
14. New dev dependencies? Default: Playwright for Python, yes. No new Node packages unless a small ES2017 parser is approved for the syntax guard.
15. Tablet naming? Default: row letter plus column number (A1, A2), editable.

## 22. Non-goals and deliberate deferrals

Non-goals:

- frame lock or genlock between tablets, and any guarantee of identical photon timing,
- cloud services or internet dependence,
- AI features (the README states the project has none),
- multiple server workers,
- peer-to-peer distribution,
- DRM,
- synchronized audio from many tablets,
- remote access from outside the hotspot.

Deferred, each with a trigger for reconsidering it:

- Rate-skew estimation: when measurements show drift between resyncs.
- Photodiode rig: when camera precision limits decisions.
- Camera-based automatic calibration: when walls grow beyond about 20 tablets.
- Per-tablet cropped video renditions: when the self-test shows bandwidth limits.
- Caddy `file_server` for media: when Python serving shows CPU limits.
- HLS: after V1 device results.
- WebRTC: when sub-second live delay becomes a requirement.
- WebCodecs: when element-level control proves insufficient and every target device supports it.
- A service worker offline cache: after HTTPS.
- WebP, AVIF and HEIC input: on operator demand.
- Time-of-day schedules: after slideshows ship.
- Per-device colour trims: after mixed-panel walls are in use.

## 23. Sources

All web sources were retrieved on 2026-10-23.

- W3C, High Resolution Time: https://w3c.github.io/hr-time/
  - The monotonic clock never decreases and is not affected by system clock adjustments.
  - It exists only within one execution of the user agent.
  - Timer throttling should not affect its accuracy.
  - Sub-millisecond resolution is optional.
  - Avoid sending wall-clock time representations between computers.
- WebKit, New `<video>` Policies for iOS: https://webkit.org/blog/6784/new-video-policies-for-ios/
  - Muted or silent video can autoplay and `play()` without a gesture.
  - `playsinline` is needed for inline playback on iPhone.
  - Unmuting without a gesture pauses playback.
- Chrome for Developers, Autoplay policy in Chrome: https://developer.chrome.com/blog/autoplay
  - Muted autoplay is always allowed.
  - Enterprise policies can allow autoplay with sound.
- Apple, Safari Web Content Guide, Creating Video: https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/SafariWebContent/CreatingVideoforSafarioniPhone/CreatingVideoforSafarioniPhone.html
  - Servers delivering media to iOS must support byte-range requests.
- WebKit, WebKit Features in Safari 17.1: https://webkit.org/blog/14735/webkit-features-in-safari-17-1/
  - Managed Media Source shipped in Safari 17.0 on iPad and Mac and in 17.1 on iPhone.
  - It requires an AirPlay alternative or disabled remote playback.
- WebKit, New WebKit Features in Safari 13: https://webkit.org/blog/9674/new-webkit-features-in-safari-13/
  - Media Source Extensions on iPadOS.
  - iPad Safari sends a macOS user agent except on iPad mini.
  - Pointer Events and Media Capabilities `decodingInfo()`.
  - WebDriver for iOS through a Mac.
- WebKit, WebKit Features in Safari 16.4: https://webkit.org/blog/13966/webkit-features-in-safari-16-4/
  - Unprefixed Fullscreen API on macOS and iPadOS.
  - Preliminary Screen Orientation API, with locking still experimental.
  - Screen Wake Lock API.
- WebKit, Full Third-Party Cookie Blocking and More: https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/
  - Script-writable storage is deleted after 7 days of Safari use without interaction.
  - Home Screen web apps have their own counter.
  - The post recommends server-set cookies for persistence.
- MDN, `HTMLVideoElement.requestVideoFrameCallback()`: https://developer.mozilla.org/en-US/docs/Web/API/HTMLVideoElement/requestVideoFrameCallback
  - Baseline 2024.
  - Provides `mediaTime`, `expectedDisplayTime` and `presentedFrames`.
  - A callback can run one refresh late.
- MDN, Screen Wake Lock API: https://developer.mozilla.org/en-US/docs/Web/API/Screen_Wake_Lock_API
  - Secure context only.
  - Released when the page is hidden.
  - Reacquire on visibility change.
- MDN, CacheStorage: https://developer.mozilla.org/en-US/docs/Web/API/CacheStorage
  - Secure context only.
- MDN, VideoDecoder: https://developer.mozilla.org/en-US/docs/Web/API/VideoDecoder
  - Secure context only, limited availability.
- MDN, WebCodecs API: https://developer.mozilla.org/en-US/docs/Web/API/WebCodecs_API
  - H.264 is the most widely supported codec.
  - Demuxing needs a separate library.
- Chromium, User-Agent Reduction: https://www.chromium.org/updates/ua-reduction/
  - The reduced Android user agent reports the model as "K" and the Android version as "10".
- Playwright, Isolation: https://playwright.dev/docs/browser-contexts
  - Contexts have their own local storage, session storage and cookies.
- Playwright, Emulation: https://playwright.dev/docs/emulation
  - Viewport, device scale factor, mobile and touch flags.
  - Offline emulation affects fetch, XHR and WebSockets.
- Playwright, Browsers: https://playwright.dev/docs/browsers
  - Bundled Chromium lacks some codecs that branded Chrome includes.
  - WebKit on Linux differs from Safari for media.
- W3C WAI, Understanding Success Criterion 2.5.7 Dragging Movements: https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html
  - Dragging needs a single-pointer alternative.
  - Keyboard support alone does not satisfy the criterion.
- Caddy, `request_body` directive: https://caddyserver.com/docs/caddyfile/directives/request_body
  - `max_size` makes oversized bodies fail with 413.
- Can I use, HTTP Live Streaming: https://caniuse.com/http-live-streaming
  - Community-maintained, not a primary source.
  - Lists Chrome 142 and later as supporting HLS.
- Chrome 142 release notes: https://developer.chrome.com/release-notes/142
  - Fetched and searched. No HLS entry was found.
  - Native HLS in Chrome is treated as unverified.
- Local evidence from this session:
  - Starlette 1.6.0 `FileResponse` range handling.
  - Pillow 12.3.0 `_decompression_bomb_check` and `MAX_IMAGE_PIXELS`.
  - The `ffmpeg` 8.1.3 encoder and filter list.
  - The Playwright browser cache listing.
  - The source files cited by line above.
- Not fetched in this session, and marked where used:
  - Apple's iPad 10.2-inch display specification.
  - The ISO/IEC 7810 ID-1 card size.
  - The Linux `clock_gettime(2)` suspend behaviour.
