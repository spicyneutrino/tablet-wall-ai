# Build a calibrated local tablet wall, then add timed media

Independent Sol proposal, round 1. Prepared on 2026-10-23 against commit `65a4d5081194c457c74a8c6aae629281a30e634b` in `/var/home/oak/Codes/projects/tablet-wall-ai`.

The durable data is an asset library, display profiles and calibrations, layouts, scenes, and playlists. A running presentation is a separate, versioned playback session. A browser connection is temporary and is never the identity of a physical tablet.

Deliver a useful still-image workflow first. The operator uploads an image, identifies tablets, measures their usable screens, arranges them, previews the crop and physical gaps, and saves the layout. Then add synchronized slideshow cuts. Add prerecorded video through native HTTP playback only after a small real-tablet experiment. Treat live input and screen capture as a later product with different transport and latency requirements.

Keep FastAPI, SQLite, vanilla JavaScript, local assets, the two-origin ingress, and one ASGI worker. There is no reason to introduce a frontend framework, message broker, cloud service, or AI dependency for this roadmap.

## Evidence and limits of this proposal

I inspected source, test implementations, `README.md`, `PROTOCOL.md`, `simulator/`, and `deploy/`. This was a planning pass. I did not run tests, start an application or browser server, install packages, use physical tablets, change network settings, or measure synchronization. Test cases below describe inspected coverage or proposed acceptance work, never a newly observed pass.

I did not read the other planner's proposal or the existing untracked `docs/` and `CODEBASE_EXPLORE_PROMPT.txt`. This file is my only edit. Reciprocal review and final authorship remain with the parent coordinator.

The planning principles have concrete consequences. Model the domain separates physical geometry from content and playback. Sequence work into verifiable units puts a working uploaded still before video infrastructure. Prove it works keeps browser screenshots, transport tests, and optical tablet measurements as distinct evidence. The user's planning-only constraint takes precedence over skill workflows that normally launch prototypes or delegate exploration.

## Establish the actual starting point

The following are current source facts, not feature requests.

- [main.py](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:745), `device_register`, records a UUID4, CSS viewport width and height, and a device type. Registration refreshes presence metadata. `_device_loop` at line 1327 accepts heartbeats; it has no readiness, clock-sync, or rendering-status protocol.
- [client.js](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/client/client.js:218), `resolveDeviceId`, persists one UUID in `localStorage`. `register` at line 269 reports `innerWidth` and `innerHeight`. `DEVICE_TYPE` is still hardcoded to `ipad`. `deviceSocketUrl`, `openSocket`, and `attemptCycle` at lines 1759, 1831, and 1888 negotiate v2, heartbeat, and reconnect.
- [main.py](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:1349), `ws_device`, owns exactly one socket per UUID. A new socket closes the previous one with `4409`. `openSocket` does not branch on the close code, so two active pages sharing storage can repeatedly take over the same device. Separate windows alone do not create independent tablets.
- [state.py](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/state.py:39), `_fresh_wall`, separates layout from scene and carries revision plus generation. `_wall_frame` at line 166 projects a complete per-device presentation. Capability checks downgrade unsupported image or calibration content to color. [protocol.py](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/protocol.py:43) supports major versions 1 and 2. Absent version means v1, and unsupported versions close with `4426`.
- [main.py](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:268), `PlacementCommand`, accepts an integer footprint and bezel in abstract wall units. There is no rotation, physical display profile, PPI measurement, or calibrated browser-to-panel mapping. Negative coordinates are possible. Bezel fields do not have nonnegative constraints. Manual placement does not reject overlapping footprints. `wall_auto` at line 997 creates equal grid cells and rejects collisions with retained offline or vacant reservations.
- [client.js](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/client/client.js:382), `visibleRectOf`, subtracts bezels. `prepareCanvas` at line 432 sizes a canvas using DPR. `drawWallImage` at line 1363 applies one global centered cover of the image, then a per-device centered cover of the visible rect. This preserves the global image transform but crops inconsistently when device and placement aspects differ. DPR currently improves raster resolution; it does not calibrate millimetres.
- [controller.js](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/controller.js:1815), `renderWallMap`, and `buildMapPlacement` at line 1901 draw buttons that focus numeric editors. They are not drag controls. `savePlacement` at line 2615 writes one device at a time. Saved layouts and scenes already have separate save, replace, recall, delete, confirmation, and damaged-record flows. Preserve those semantics.
- [assets.py](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/assets.py:153), `refresh`, inventories top-level regular nonsymlink JPEG and PNG files. `_inspect` at line 332 checks structure and full decode, excludes animation, rejects rotated EXIF, and enforces 10 MiB and 12 megapixels. IDs hash the actual file bytes. `fetch` at line 204 rescans the directory and rehashes the requested bytes. [main.py](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:1273), `get_assets` and `get_asset`, expose inventory and validated bytes. There is no upload route.
- The still-image client has useful race protection. `isCurrentImageAttempt`, `startImageLoad`, and `applyWallFrame` at client lines 1054, 1178, and 1524 scope asynchronous decode to the current asset, generation, revision, and attempt. There is a 15-second whole-attempt deadline, explicit failure UI, object-URL cleanup, and stale-result rejection. There is only one decoded-image cache, no slideshow preloader, and no device-to-controller report that an image reached the renderer.
- [main.py](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:312), `_commit_wall`, persists a proposed state before changing the live state or broadcasting. [persist.py](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/persist.py:70) uses synchronous SQLite transactions, one active-wall row, and named layout/scene tables. Sockets, roster, and presence are process-local. Startup regenerates generation even when revision is restored from disk. This is an important existing recovery rule.
- [hub.py](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/hub.py:93), `_broadcast_wall`, awaits socket sends sequentially. It builds the controller snapshot before the sends, but builds individual device frames later from mutable current state. There is no bounded outbound queue or send deadline. For still scenes this often converges through newer full snapshots. Timed prepare/commit messages need stronger ordering and slow-client isolation.
- The application has an operator Origin guard, not built-in authentication. [deploy/hotspot.Caddyfile](/var/home/oak/Codes/projects/tablet-wall-ai/deploy/hotspot.Caddyfile:9) exposes an exact tablet route allowlist and uses proxy Basic authentication on a loopback operator origin. The backend stays on loopback. Tablet registration, device sockets, and image bytes have no pairing credential. Learnable UUIDs are not access control. Deployment and kiosk artifacts explicitly remain pending physical validation.
- [deploy/backup.py](/var/home/oak/Codes/projects/tablet-wall-ai/deploy/backup.py:386), `_collect_references` and `_read_snapshot`, back up asset references in the active scene and saved scenes. The tool does not currently traverse future playlist, rendition, or library tables. Its asset locator is restricted to current curated image formats and limits. Extending only an upload API would leave recovery incomplete.

Inspected tests corroborate these boundaries. `tests/test_websocket.py::TestControllerSocket.test_second_socket_replaces_the_first` tests replacement, not competing running JavaScript pages. `tests/test_wall.py` tests v1/v2 separation, capability gating, reservations, grid collisions, and revisions. `tests/test_commit_boundary.py` injects disk failure and checks memory, disk, and subscribers. `tests/test_assets.py` covers corrupt, misleading, animated, EXIF-rotated, oversized, replaced, and symlinked inputs. `tests/test_snapshots.py`, `tests/test_persistence.py`, and `tests/test_backup.py` cover saved-state and recovery contracts.

`tests/client_image.test.js` executes the real IIFE in a Node VM with mocked DOM, canvas, fetch, image decode, and sockets. It checks drawing arguments, race handling, and a viewport geometry matrix. It is valuable JavaScript coverage, not a browser rendering test.

[simulator/harness.py](/var/home/oak/Codes/projects/tablet-wall-ai/simulator/harness.py:63) isolates its database and assets. `DeviceSpec`, `VirtualDevice`, `SocketPump`, and `Harness.start` use Starlette TestClient, shared in-process ASGI state, and reader threads. `simulator/scenarios.py` covers registration, content, placements, save/recall, generation, reconnect, replacement, and sweeper behavior. `simulator/geometry.py` independently computes protocol geometry. No client JavaScript, TCP, TLS, hardware decoder, compositor, or pixels run there. Its unbounded test streams cannot prove production backpressure behavior.

`deploy/load-smoke.py::device` does create concurrent network WebSockets through a real ingress, but still runs Python clients on one machine. It proves neither browser rendering nor independent physical radios.

## Address the debt that affects the requested features

Prioritize these findings as engineering work, with regression evidence attached to the relevant tickets.

1. Stop duplicate-page reconnect contention. Respect `4409` as ownership replacement and show a deliberate Take over display action. Reconnecting automatically after ordinary transport loss remains correct.
2. Add validated display measurements. Current registration accepts nonpositive and unreasonable integers, and current bezel inputs permit negative values. New physical models must reject nonfinite values, nonpositive dimensions, negative bezel widths, excessive viewport sizes, and unreasonable payload lengths. Preserve intentional signed placement offsets. Audit legacy saved data before tightening old validation.
3. Give layout edits an atomic operation and a revision precondition. Group drag cannot be a series of independent PUT requests. Concurrent controllers currently have no compare-and-swap contract. Do not silently overwrite another editor's layout.
4. Distinguish connected, capable, loaded, ready, and actually reported rendering states. A successful socket send currently says nothing about image decode or autoplay.
5. Add one ordered, bounded sender per connection before timed playback. Send immutable snapshot values captured at command acceptance. Disconnect a persistently slow client rather than blocking every other client. Coalesce replaceable snapshots deliberately; never accidentally discard a prepare prerequisite or a cancellation. Test welcome-first ordering through the same sender.
6. Remove full-library decode work from normal asset reads as managed uploads arrive. Current reads scale with the whole curated directory and occupy worker threads. Hash and decode a new managed object at ingestion, then address it through an index. Preserve current curated-file swap and byte-identity protections.
7. Keep database writes off the timed scheduling path. Synchronous `_commit_wall` is an intentional safe boundary today. If moving it off the event loop, introduce one serialized command writer and an explicit commit/apply boundary. Merely adding `to_thread(save_state)` between reads and mutations would create lost-update races.
8. Use monotonic time for liveness intervals and playback. Current heartbeat age uses UTC wall time in `state._seconds_since_last_seen`; a host clock adjustment can change the derived age. Keep ISO timestamps for operator display, plus a process-local monotonic last-contact value for expiration.
9. Add durable schema versions and backup reference closure before new persistent types. `load_state` currently parses JSON without the validation used for named recall. An unknown or malformed upgraded document must fail visibly without overwriting the old database with defaults.
10. Extract only the geometry, playback, and transport code that needs shared testing. The approximately 1,900-line client IIFE and 4,100-line controller make new cross-cutting state expensive to reason about. Do not combine this work with a framework rewrite or unrelated cleanup.

## Choose the architecture with the smallest compatibility cost

Keep a single authoritative local server. HTTP remains the operator command transport. WebSockets carry snapshots, clock exchanges, readiness, status, and scheduled presentation control. Media bytes use ordinary HTTP URLs. Server restart creates a fresh epoch and playback session.

The competing options have different costs.

- Pushing image or video bytes in application WebSocket messages would couple large transfers to control latency, require a custom media pipeline, and lose normal caching and seeking. Reject it for the first implementation.
- Independent slideshow intervals or broadcast-immediate video starts would be small to write, but each device would accumulate network, decode, and timer differences. Reject them for timed presentation.
- Native HTTP file playback keeps decoding and buffering in the browser and works without MSE. Choose it for the first prerecorded-video experiment and implementation. It sacrifices exact buffer ownership and seamless adaptive quality switching.
- HLS gives timestamped segments and rendition playlists, with native playback on supported Apple browsers and a tested library route elsewhere. It adds packaging, more requests, and player-dependent buffering. Revisit it if file playback cannot meet measured recovery or delivery needs. Apple documents HLS for live and on-demand delivery. The hls.js project's compatibility section requires MSE or native HLS and warns against assuming that a nonempty `canPlayType` result proves usable playback. [Apple HLS](https://developer.apple.com/streaming/), [hls.js compatibility](https://github.com/video-dev/hls.js#compatibility). Retrieved 2026-10-23.
- A custom MSE player offers append and eviction control but adds quota recovery, timestamp continuity, codec checks, and mobile power behavior. Do not require it for old tablets. WebKit documents that Managed Media Source arrived on iPad before iPhone and has remote-playback prerequisites. That is a compatibility warning, not a reason to exclude every older iPad from native file playback. [WebKit Safari 17.1](https://webkit.org/blog/14735/webkit-features-in-safari-17-1/). Retrieved 2026-10-23.
- WebRTC is a candidate for interactive live capture, with per-receiver jitter buffers, signaling, and potentially significant sender fan-out. It provides no cross-device screen refresh lock. Do not add it to play an uploaded file. An SFU or encoder service is a later decision based on measured local fan-out. [W3C WebRTC](https://www.w3.org/TR/webrtc/). Retrieved 2026-10-23.
- Per-device server-rendered image or video tiles can reduce client decode size but multiply renditions and bind media generation to layout changes. Defer them until full-source decoding proves the bottleneck. Clipping a 4K video to a small tablet slice does not make the decoder process only that slice.

Use a few domain-owned modules as features land. Proposed backend modules are `tabletwall/geometry.py`, `tabletwall/displays.py`, `tabletwall/media.py`, and `tabletwall/playback.py`. Keep route adapters in `main.py` initially. Proposed client modules are `geometry.js`, `clock.js`, and `playback.js`; proposed controller modules are `layout-editor.js` and `media-library.js`. These are planned files, not existing functionality. Continue serving local scripts without introducing a build requirement for the tablet client. Every added client script must be added to the Caddy exact allowlist and deployment checks.

## Define the operator and tablet flows

### Connect, identify, and calibrate

The operator opens the authenticated laptop controller and copies its configured tablet URL. A QR code is useful but remains a local rendering convenience. Each tablet opens the page, shows a large temporary identifier, and exposes an explicit Enable display action for fullscreen and later media activation. The controller assigns a human label such as Left iPad. Identify makes the same label and an edge-orientation marker appear on that tablet for a bounded interval, then restores its current content.

The operator measures active display width and height and bezel edges, chooses the tablet's physical rotation, and runs the ruler and seam pattern. Model specifications can prefill values but are labelled estimates. Keep launch mode, browser build, viewport, DPR, and calibration date visible in details. A changed viewport marks calibration as needing review.

### Arrange and show an uploaded still

The operator selects or drops a JPEG or PNG. Upload and server validation complete before it appears ready in the library. Picking an image changes the controller preview only. Show on wall prepares the image, reports per-device outcomes where supported, and applies it. A missing or failed device remains explicit.

Unplaced devices appear in a tray. Drop or select them onto the wall. A numeric inspector gives the same placement operation. Preview shows active screens, physical bodies, empty gaps, and the global image crop. Save layout names the arrangement independently of Save scene. An absent tablet retains a labelled reservation. Replace tablet explicitly binds a new display identity to a retained slot after the operator identifies it.

This is the initial vertical slice through tickets 1 to 5. It includes upload, a saved physically meaningful layout, calibrated still rendering, and recovery after reload or server restart. It does not need a shared playback clock. Verify on at least one iPad and one Android before calling that slice physically validated.

### Run a slideshow

The operator orders images, sets dwell time, chooses loop behavior, and presses Prepare. The controller reports readiness and failures for the required displays. Start provides a countdown after readiness. Pause, Next, Previous, and Stop all produce server-authored timeline changes. The operator can see that a slow device is holding the next transition and can retry, choose a smaller rendition, or explicitly exclude it.

### Play a file or choose a live source

File playback starts with Upload video, compatibility checking, profile selection, and Prepare. Controls expose start countdown, buffer goal, readiness timeout, and recovery policy. The operator sees buffer coverage, stall reports, clock confidence, and each device's current state. Defaults are muted playback and no automatic restart after server reboot.

Live input is a separate source picker. It names camera, capture device, or screen share, shows that capture is active, and has a persistent Stop sharing action. Starting a playlist of prerecorded files never requests screen-capture permission.

## Specify the domain records before expanding handlers

Use Pydantic discriminated models at HTTP, WebSocket, and persistence boundaries. Keep plain validated objects internally and document equivalent JavaScript records with JSDoc. Avoid adding TypeScript or a shared code generator solely for this change. `PROTOCOL.md` owns wire examples and invariants. Store a schema version in persisted documents independently of transport major version.

- `Asset` has an opaque content ID, media kind, validated MIME, byte size, dimensions, display name, origin, ingest status, and creation time. An uploaded source and a normalized render asset can have different hashes. Never claim the source hash identifies transformed bytes. A `Rendition` references its own asset ID and parent, dimensions, codec details, duration and timebase where relevant. Server file paths never appear in client descriptors.
- `DisplayProfile` has a stable display ID compatible with the current UUID, a label, optional physical-device inventory reference, active-panel dimensions, bezel edges in the native panel orientation, and measurement provenance. A browser storage profile is a registered display endpoint. It is not proof of one unique piece of hardware.
- `ClientSession` has a per-document-load ID, a server-issued connection ID, protocol and capabilities, current viewport report, visibility, activation state, and last contact. A reload keeps the display ID but gets new session and connection IDs. Neither UUID is a credential.
- `Calibration` references a display profile, calibration revision, viewport signature, viewport-to-panel transform, measurement uncertainty, and validation state. The signature includes CSS viewport dimensions, DPR, available orientation report, zoom information where available, and launch mode. Physical screen dimensions are operator input, never inferred from CSS `mm` or DPR.
- `Layout` has a schema version, coordinate-space kind, explicit content bounds, display placements, and optional group metadata. A `Placement` references a display profile and calibration, body pose, and participation flag. Disconnected endpoints remain reservations. Group membership helps editing and does not imply synchronized hardware.
- `Scene` describes content and its fit into content bounds. Variants include color, calibration, still, playlist, and later prerecorded video or live source. Keep layout references compatible with the current active-layout semantics. Scene recall does not recall a layout. A combined preset, if added, is separately named.
- `Playlist` has a stable ID, revision, ordered item IDs, asset or scene references, dwell durations, cut transition, and loop policy. Start with still-image items. Editing an active playlist creates a new revision for the next preparation; it does not mutate a running item's duration in place.
- `PlaybackSession` has generation, random session ID, monotonically increasing version, required display IDs, a frozen scene or playlist revision, an active timeline, at most one pending preparation, buffer policy, and group recovery policy. It is process-local. Persist the selected scene and user settings, but never reuse a prior process's monotonic timestamps after restart.
- `Timeline` has state, server monotonic anchor time, media time at anchor, rate, item or loop occurrence, and any future effective time. States are preparing, armed, playing, paused, rebuffering, stopped, or failed. Compute the current position from the anchor instead of incrementing counters.
- `Preparation` has a unique preparation ID, originating session version, exact asset/rendition and item occurrence, layout and calibration revisions, required participants, deadline, and readiness evidence. Identical assets in successive playlist positions remain different occurrences.
- `DeviceStatus` references the current connection, generation, session, version, and preparation when applicable. It reports fetching, decoding, ready, armed, playing, paused, stalled, blocked, hidden, unsupported, or error. Include bounded detail codes, buffer ranges and sample time, media time, observed drops when available, and clock estimate age. The controller labels client-reported evidence as such. Pixels visible on glass require optical evidence.

Separate desired scene, pending preparation, and active presentation in controller state. Upload complete, command accepted, decoded, and presentation submitted must not share the same success label.

## Keep physical geometry separate from image fit

### Use one explicit physical coordinate system

For a physical layout, use millimetres with finite bounded numeric values. Display millimetres to one decimal place in the editor; keep enough precision internally that repeated transforms do not accumulate rounded placement errors. Set world origin at the top-left of the chosen content bounds, X right and Y down. Permit signed offsets and irregular arrangements. Legacy layouts remain explicitly `logical` until converted.

In the tablet's native reference orientation, record active-panel width and height and four nonnegative bezel widths. The body rectangle includes both the active panel and bezels. A pose places the body's center at `(cxMm, cyMm)` and rotates it clockwise by `rotationDeg`. Derive rotated bounds from the transform, not by changing the measured panel dimensions. Expose 0, 90, 180, and 270 degree controls first. The transform model can support a measured arbitrary angle without a later schema change.

Let `B` map body coordinates to world coordinates. Let `V` map CSS viewport coordinates into body coordinates. `V` includes actual usable panel area, the browser's orientation relative to the native panel, and any viewport origin offset. Browser chrome can reduce the usable panel without changing its physical body. Mount rotation and browser orientation are different inputs.

Let `F` map source content pixels into the wall's explicit content bounds using the scene's fit, focal point, and content rotation. Let `D` map CSS coordinates to the chosen canvas backing resolution. The drawing transform is:

```text
backingPoint = D * inverse(V) * inverse(B) * F * sourcePoint
```

Clip to the calibrated viewport. This composition applies to a calibration pattern, an image, and the positioned native video element. Test both the forward transform and its inverse. Changing cover to contain changes `F`; moving a tablet changes `B`; changing DPR changes `D`. None changes the other's stored values.

CSS pixels, backing pixels, native panel pixels, and millimetres are distinct quantities. If native resolution and active panel dimensions are known, compute native PPI as pixels per inch for information. DPR reports the browser's device-pixel to CSS-pixel scale. Canvas backing scale is an application choice and can be capped for memory or rendering cost. Neither supplies a PPI measurement. A CSS inch is defined relative to CSS pixels and need not match an inch on a screen. [CSS Values and Units, absolute lengths](https://drafts.csswg.org/css-values-3/#absolute-lengths). Retrieved 2026-10-23, editor's draft.

Do not infer a panel's native pixel count from `screen.width * devicePixelRatio`. OS scaling, zoom, viewport restrictions, and reporting differences make that unsuitable for physical calibration. Store known native resolution with its provenance or leave it unknown.

### Calibrate what the page can actually use

1. Identify the tablet and its native top edge. Enter measured active-panel and body dimensions. If the operator enters only diagonal and aspect ratio, derive provisional dimensions and label them unverified.
2. Open the intended launch mode and use fullscreen if available. Otherwise measure the viewport's physical span and offset on the panel. A two-axis ruler with marks at known CSS positions measures millimetres per CSS pixel. Align visible edge marks to measure origin offsets.
3. Render a crosshair, ruler, diagonals, and continuous seam targets in world coordinates. Adjust body position and orientation. Never fix a seam by independently cropping the content on one device without exposing that as a content override.
4. Save calibration with the viewport signature and uncertainty. Capture a photo with a ruler or fiducial across neighboring panels. Compare visible lines against the portion physically hidden by frames and gaps.
5. After rotation, zoom, browser chrome changes, or a different launch mode, compare the signature. Reuse only if compatible. Otherwise mark Needs calibration and exclude the endpoint from timed readiness until verified. Static preview can remain available with a clear warning.

Do not call the current per-device cover fallback a physical calibration. In physical mode, mismatched geometry produces a warning and a correction path. Keep that legacy crop behavior available only in logical layouts or as an explicit operator choice.

### Make seam policies explicit

Default to Preserve physical gaps. The continuous virtual image occupies the measured world. Content behind bezels, body margins, and inter-device air gaps is not visible. Lines on opposite sides remain geometrically consistent. Do not add bezel widths to an active-area offset twice.

Offer Repeat near seams later as a content mapping preset. It deliberately samples an overlapping strip on adjacent screens, so some content appears twice. It does not change a tablet's body or bezel measurements. A zero-overlap compact mapping and an overlap mapping can be presets for regular rows or grids. Irregular arrangements need explicit per-display sampling rectangles and a preview because there is no unique way to collapse every hole in a rotated layout. Do not hide that choice behind negative bezel values.

Start with global cover and contain, a focal point, and an explicit wall background. Keep source fit global. Preview clipped content, missing areas, reservations, and accidental physical overlap. Changing the arrangement must not silently resize fixed content bounds during a show. Offer Fit bounds to arrangement as an explicit edit.

## Evolve the protocol without stranding existing clients

Add protocol major 3 for physical geometry and timed control. v1 and v2 continue their documented logical/color/still behavior. They must never receive a rotated physical placement in a v2-shaped frame. Require v3 geometry support for required members of a physical layout. Offer a clearly identified partial wall only when the operator explicitly excludes unsupported endpoints.

Put new operator commands and typed configuration documents under `/api/v3/`. Keep existing HTTP bodies unchanged for logical static walls. While a physical layout or timed session is active, reject legacy operator mutations with `409` and an Upgrade controller explanation before changing anything. Return an explicit upgrade-required result to a legacy wall reader rather than pretending physical geometry is a logical grid. Legacy tablet registration and sockets still work. An explicitly excluded v2 tablet can receive its existing color fallback with no physical placement, never an invented approximation. Add tests for these mixed-version cases.

Retain `generation` as the server epoch and mint a sufficiently long random value on each start. Retain durable wall revision. Add a separate process-local playback session ID and version so a pause or seek does not depend on changing the durable layout revision.

Use capability names for implemented behavior, such as `geometry.physical.v1`, `image.v1`, `timeline.v1`, and `video.file.v1`. Query-string caps remain a coarse handshake. A v3 client then sends a bounded structured report of its tested APIs, supported candidate codecs, viewport, visibility, and local activation outcome. Never infer decoder support from an OS name or user-agent string alone. Media Capabilities, when present, is advisory evidence about a particular media configuration. Actual sample decode remains necessary. [W3C Media Capabilities](https://www.w3.org/TR/media-capabilities/). Retrieved 2026-10-23, working draft.

Update all version-dependent branches, including `hub._broadcast_wall`, which currently selects exactly v2. Keep welcome as the first frame. Project complete snapshots for each negotiated version from an immutable accepted state.

New operator commands use HTTP and include `expectedGeneration`, `expectedWallRevision` for configuration changes, and `expectedSessionId` plus `expectedVersion` for playback. Add a bounded idempotency key for retryable commands. A duplicate retry returns the original result. A conflicting new command returns `409` with current state. Check the precondition inside the serialized mutation boundary, after slow validation work, rather than before an await.

A layout, calibration, scene, or participant change invalidates preparations that referenced the old configuration. Commit that invalidation with the configuration change and publish a new playback snapshot. During timed playback, default to an explicit pause/re-prepare operation rather than letting geometry change under an old scheduled cut. A draft layout can be edited and previewed without affecting the live session until Apply.

The device channel adds clock request/reply, preparation readiness, command acknowledgement, rendering status, and snapshot request. A versioned playback snapshot contains active timeline plus any pending preparation. Every prepare, commit, pause, seek, cancellation, or stop advances the session version. Commit references the preparation ID whose readiness it uses. Readiness replies include that preparation's originating version, exact content and geometry references, and current connection ID.

Reject a readiness report if the connection was replaced, the generation/session differs, the preparation was canceled, or any referenced revision changed. A delayed decode can populate an asset cache but cannot publish ready for a newer plan or paint over it. Extend the existing image-attempt token discipline rather than replacing it with unscoped promises.

For a new connection, send welcome, full configuration, current playback snapshot, and clock bootstrap. Re-register as today. Invalidate the old connection's readiness. A late joiner derives the current item and position from the timeline, loads that state, and joins at an announced future point or the next cut. It never replays the start of a playlist merely because it reconnected.

The generation is accepted only from the current connection's welcome/snapshot lineage. Once bound, an old asynchronous message from a prior connection cannot switch the client back to an older generation. On server restart, restore configuration, create a new playback session in paused/preparing state, and require explicit Start by default. Do not persist a `performance.now()` or server monotonic anchor and reuse it after reboot.

The status protocol is bounded and rate-limited. Coalesce routine progress, send state transitions immediately, and cap detail strings and buffered-range counts. Readiness has an explicit lease and sample age. Recheck its geometry, asset, activation, clock, and buffer prerequisites before commit, and expire it on disconnect or supersession. Show stale status as unknown instead of retaining a green ready label. Keep render status separate from heartbeat. A socket can be healthy while video is stalled.

## Implement managed image ingestion and recovery together

Keep current curated assets working with their original IDs. Add an owned media directory, configured separately from the read-only curated import directory, and an asset metadata table. Resolve its default relative to the database directory, not an arbitrary import working directory. Tests must explicitly isolate the new directory too.

The first upload endpoint belongs only to the operator origin. Reuse the existing Origin fence and proxy authentication. The tablet ingress continues to deny uploads, inventory, and operator mutations. Uploading from another tablet or phone is a later, scoped uploader credential flow; it must not require exposing the entire controller API on the tablet listener. Asset privacy is a separate decision because existing tablet asset URLs are public to reachable LAN clients.

For the first release, accept one JPEG or PNG file per request. Preserve the current 10 MiB encoded-input limit and 12-megapixel decoded-source limit. Check dimensions before allocating full raster memory. Add maximum edge length, decoded-memory budget, request timeout, queue bound, free-disk reserve, and library quota. Initial defaults of a 60-second request limit, one decoder job, four queued jobs, and a configurable 1 GiB library quota are proposed operating limits, not measured capacity. Return useful `413`, `415`, `422`, `429`, or `507` outcomes. Quota accounting includes staging and generated files.

Stream to an unpredictable exclusive staging file outside static mounts. Enforce the size while reading, including requests with no Content-Length. Do not use the supplied filename as a filesystem path. Validate actual format, structural integrity, full decode, pixel count, and animation. Reject SVG, HTML, HEIC, GIF, archives, remote URLs, and format mismatches initially. Use a bounded worker process for hostile decode and normalization so a timed-out decoder can be terminated. A thread timeout alone cannot stop native decoder CPU work. Keep the ASGI process single-worker; decoder jobs are a separate bounded workload.

Apply EXIF orientation, including mirrored cases, then strip EXIF and private metadata and encode normalized render bytes. Convert a supported embedded color profile into sRGB or reject it with a clear explanation. Define transparency and background behavior consistently. Hash the final stored bytes. The upload response returns the normalized asset ID and dimensions. Preserve an optional original digest as metadata, not as the rendering ID. Curated files retain their current reject-rotated behavior unless deliberately imported through normalization.

Publish only after validation. Write and fsync a complete immutable content-addressed object, atomically rename it into the owned store, then commit its ready metadata row. Never mark a nonexistent partial file ready. If publication succeeds but the database commit fails, a later reconciliation can remove or import the unreferenced object. If a job or request dies, bounded staging cleanup removes only that job's files. Duplicate normalized content reuses one object, with display names kept as metadata. No partial object is listed or served.

For managed still reads, look up the requested object directly and verify its capped bytes against its ID without decoding the entire library. Preserve O_NOFOLLOW, regular-file verification, strict MIME, `nosniff`, and same-origin descriptors. Keep the old curated-file swap tests meaningful. For future large ranged video, use a validated server-owned immutable object and opened-file identity checks instead of reading and hashing the whole video for every range; document that a hostile local writer with the server's privileges is outside that store boundary. Add an integrity verification operation for corruption detection.

Generate small controller thumbnails and optional lower-resolution full-image renditions. Renditions preserve the same source aspect and coordinate mapping. They do not independently crop each tablet. Bound the active and next decoded images on a tablet. Two 12-megapixel RGBA images alone require approximately 96 MB before canvases and browser overhead, so source acceptance is not a promise that every old device should decode that size.

Extend backup in the same milestone. Update reference traversal for active/saved scenes, playlists, rendition parents and children, display/calibration records, and required metadata. Retain manifest versioning, checksums, online SQLite backup, verification before publish, and restore into new targets only. Select the reference set from the captured database, not the later live state. Temporarily protect those objects from deletion while copying. Restore an old backup fixture and a new fixture, then serve their selected assets in an isolated app.

Preserve the current default of backing up referenced content. Clearly show that an uploaded but unused library item is outside that snapshot. Offer a deliberate full-library export later if the operator needs it. Reject deletion of referenced assets by default and report the references. Avoid automatic garbage collection until backup pins and playlist references are tested.

## Build clock estimation and slideshow cuts before video

Use a four-timestamp exchange over the current device WebSocket. With client monotonic send `c0`, server monotonic receive/send `s1` and `s2`, and client receive `c3`, estimate server-minus-client offset and network round trip:

```text
offsetMs = ((s1 - c0) + (s2 - c3)) / 2
roundTripMs = (c3 - c0) - (s2 - s1)
estimatedServerNowMs = clientMonotonicNowMs + offsetMs
```

Take several samples and favor low-round-trip samples. Timestamp a reply at actual send scheduling rather than before a long outbound-queue wait. Track sample age, variation, and drift. Network asymmetry and event-loop delays remain unknown; half the observed round trip is an estimate component, not a guaranteed clock-error bound. Resample initially, periodically, after reconnect, and after visibility or sleep changes. Reject stale confidence. A proposed initial cadence is eight bounded startup samples and a refresh every 15 seconds. Tune from device evidence.

Use a monotonic client clock for deadlines and timeline position. Compare against the server anchor each time a task runs. A delayed callback derives where the presentation should be now instead of advancing one old tick. A coarse timeout can wake ahead of a cut; the visible swap occurs on the next rendering opportunity. A requestAnimationFrame callback is not a hardware synchronization primitive.

For a slideshow, prepare only the next image initially. Keep the current image visible while fetching and decoding the next rendition. Readiness requires a current calibration, visible page, fresh clock estimate, usable rendering surface, and decoded image. Freeze the required participant set for this preparation. Default to every placed display marked required, including offline reservations, until the operator explicitly removes a requirement.

Once all required devices are ready, the server commits a future cut time with a safety lead. If readiness expires before commit, hold the current slide and prepare again. After commit, a device can still disconnect or freeze; acknowledgements cannot make a broadcast atomic across failures. Report degraded presentation if that occurs, then converge through the current snapshot.

Derive playlist position and item occurrence from an anchored timeline. Pause stores a media position. Next and Previous create a new version and preparation. Loop boundaries are server timeline events, not independent native timers. Edits to a running playlist become a new frozen revision. Start with cuts. Crossfades need both images resident and a transition progress derived from shared time; defer them until memory and optical tests justify the cost.

Default recovery is to hold the current still and reschedule the next cut for the group. After two preparation failures, recommend a smaller common rendition or ask the operator to exclude a named device. Never quietly let each tablet advance independently.

## Add prerecorded video with honest buffering controls

### Probe a narrow media profile

First test a short, numbered-frame MP4 on the actual old and new tablets. Use native `<video muted playsinline preload="auto">` with a CSS transform and clipping derived from the same physical model. Prefer native video composition over copying every frame into a canvas. Test that transformed clipping, rotation, and the preparation overlay behave correctly on each actual browser. A canvas path is a measured fallback, not the assumed fast path.

Begin with H.264 video in MP4, 8-bit SDR, 4:2:0, a constant frame rate, and no required audio. Treat a 720p30 rendition near 2 Mbit/s and a 480p fallback as test candidates, not universal decoder guarantees. Validate profile and level against each device. Try a lower frame rate if old hardware requires it, then judge moving seams optically. MP4 is a container; extension or MIME alone does not establish codec compatibility.

Use a bounded local ffprobe process for video metadata and optional offline FFmpeg jobs for known profiles. No shell interpolation, remote playlist fetch, network protocols, or arbitrary source URLs. Bound input bytes, duration, dimensions, frame rate, track count, job time, disk use, and concurrency. Proposed initial file limits are 250 MiB and 10 minutes, configurable after tests. If the supported probe/encoder is unavailable, leave video ingest disabled with an actionable explanation. Do not write a new MP4 parser in application code.

Prepare files for progressive access with the index at the beginning. FFmpeg documents `faststart` for moving the MP4 index. A known keyframe interval also helps seek and recovery experiments. Any packaged encoder needs an explicit binary/dependency and license decision. [FFmpeg formats documentation](https://ffmpeg.org/ffmpeg-formats.html), official indexed documentation excerpt checked 2026-10-23. Full-page retrieval timed out during this pass.

### Serve files through HTTP correctly

Add an allowlisted GET and HEAD media route for ready immutable objects. Support normal `200`, valid single-byte-range `206`, `Content-Range`, `Content-Length`, `Accept-Ranges`, conditional validators, and unsatisfiable-range `416`. Define a bounded policy for multi-range requests rather than accidentally reading the full file into memory. Preserve same-origin media descriptors. Prove actual seek requests through the real proxy; do not assume the existing `Response(content=bytes)` image endpoint provides ranged video.

Use a tested framework file-serving implementation when its pinned version meets the contract, with opened-file validation retained. Do not trust a filename supplied by the requester. Update Caddy to permit exactly the media read methods and paths needed by tablets. Operator uploads stay denied there. [RFC 9110 range requests](https://www.rfc-editor.org/rfc/rfc9110.html#name-range-requests). Retrieved 2026-10-23.

Every tablet normally downloads and decodes a complete source or rendition. At a nominal 2 Mbit/s, 20 independent unicast consumers request about 40 Mbit/s of media payload before protocol overhead and startup bursts. This is arithmetic demand, not a measured hotspot capability. Preloading stills or staggering bulk video preparation can reduce bursts, but browser caching on one tablet does not share bytes with the others. A shared laptop host with virtual clients does not reproduce this radio airtime demand.

### Separate the controls users can actually choose

- Start countdown controls how long after readiness the shared start is scheduled. Propose 2, 5, or 10 seconds, with 2 seconds as an initial default only if the measured control-path margin fits. It is independent of how much video has buffered.
- Buffer goal controls required contiguous media-time coverage ahead of the target position. Propose 2, 5, or 10 seconds, with 5 seconds initially. Near the end, use remaining duration. Show observed coverage and waiting state.
- Preparation timeout defaults provisionally to 30 seconds. Failure holds the group and offers retry, lower quality, or exclusion. Rebuffer goal and low-water warning initially use 5 seconds and 1 second.
- Presentation mode selects Keep wall together, the default, or Continue with available displays, an explicit partial-wall choice. The latter identifies absent devices and cannot be labelled fully synchronized.
- Live delay is a future control relative to a live source's capture timeline. It is not another name for a prerecorded file's start countdown.
- Segment duration belongs to a future segmented transport. It is not an active native-file setting. Candidate HLS packages can compare 2, 4, and 6 second segments with aligned keyframes. Smaller segments trade delay against requests and overhead. They do not directly select cross-tablet synchronization accuracy.

Native `preload` is a hint, and buffered ranges can change or be evicted. `canplaythrough` is a browser estimate, not a readiness guarantee. Require actual range coverage plus usable media state, successful seeks where needed, and tested playback permission. If the browser will not buffer the selected goal, report that limitation instead of waiting forever or claiming the goal was enforced. [HTML media loading and time ranges](https://html.spec.whatwg.org/multipage/media.html#media-elements). Retrieved 2026-10-23.

Native HTTP playback does not expose exact chunk fetch sizes, maximum buffer size, or arbitrary retention of N seconds. Server I/O block size and HTTP transfer chunks are implementation details, not media segments. Do not split a movie into arbitrary byte blobs and replace `video.src` for each one. If exact segment-buffer ownership becomes a requirement, gate an MSE/HLS implementation on the measured supported fleet.

### Schedule, monitor, and recover

Prepare the chosen rendition at the target media time. Wait for metadata, bounded seek completion, adequate contiguous buffering, and a usable first frame. Test local Enable video and delayed `play()` calls with the exact browser and source. A gesture on the controller does not grant activation on remote tablets. Handle the `play()` promise or older API behavior and report blocked state. Use muted inline playback by default. WebKit and Chromium document mute and gesture-dependent autoplay rules; installed apps, preferences, and older builds still require testing. [WebKit video policy](https://webkit.org/blog/6784/new-video-policies-for-ios/), [Chrome autoplay policy](https://developer.chrome.com/blog/autoplay/). Retrieved 2026-10-23.

Commit an anchored future start. Each client estimates expected media time from the shared timeline. Use `requestVideoFrameCallback` metadata for diagnostics when available. Otherwise use `currentTime`, media events, and a rendering loop with a lower-confidence status. The callback API is explicitly best effort and may be late; it is not proof of visible screen timing. [Video frame callback specification](https://wicg.github.io/video-rvfc/). Retrieved 2026-10-23, incubation specification.

Start correction experiments with a dead band of 50 ms, temporary playback rates between 0.98 and 1.02 for moderate error, and a group re-prepare for error beyond 250 ms or a stall. These are provisional tuning values. Test whether the device applies small rate changes smoothly. Avoid rapid seek loops. If the browser ignores or destabilizes correction, disable fine correction and use explicit scheduled group recovery.

Pause, resume, seek, loop, source replacement, and quality changes all create new session versions. A source switch cancels prior callbacks and seeks. A late `seeked`, `playing`, or frame callback carries its owning version. Seek to the authoritative time and re-arm; do not fast-forward an old command sequence. Align renditions to the same duration and timeline before permitting a quality switch. Initially switch quality through a scheduled rebuffer and seek, not an alleged seamless transition.

On low buffer, warn and prepare group recovery before an observed stall where possible. If a tablet actually stalls, it may already have shown a different frame before others hear about it. Report the degraded interval. Schedule a group pause or rebuffer, then resume at a new anchor. After two failed recoveries, offer a tested lower common rendition, a poster or slideshow, or explicit device exclusion. Do not promise that added network delay fixes inadequate decode throughput or an OS that suspends the page.

Audio stays muted on tablets. Later, designate one audio output, such as the operator laptop or one tablet, with explicit local activation. Do not play independent speakers across the wall by default. A single output still needs audio/video offset measurement. Captions and other accessibility content need a readable placement policy rather than tiny text split across bezels.

## Treat live capture as a later branch

A file has an existing seekable timeline. A camera or screen source has capture timestamps, encoder delay, a changing live edge, and a finite delay budget. Keep different `file` and `live` source variants even if both eventually produce an HTTP playlist.

For delayed live video, first compare a local encoder producing HLS with a shared intentionally delayed presentation position. Native HLS players can choose different live positions, so the timeline/readiness model still applies. Measure capture-to-glass delay separately from inter-screen skew. Keep all manifests, segments, dependencies, and optional signaling local.

For interactive mirroring, compare WebRTC on a small actual fleet. Measure per-receiver delay and drift, sender CPU, uplink use, decoder behavior, and whether the required common delay is achievable. Per-browser jitter buffers do not become one shared buffer merely because the sources match. Do not assume every browser exposes a reliable playout-delay control.

Screen capture requires the initiating computer's supported browser, a secure context, a current user action, and an explicit capture choice. Ordinary display-capture permission is not a persistent unattended grant. Keep an immediate local stop control and handle source ending. Older tablets can be receivers without being capture-capable. The current W3C screen-capture document is a working draft; validate the actual producer browser before committing scope. [W3C Screen Capture](https://www.w3.org/TR/screen-capture/). Retrieved 2026-10-23.

Do not choose a live transport before the user decides whether a few seconds of deliberate delay is acceptable or whether interaction latency matters more than moving seams. No target for live latency is promised by this plan.

## Make layout editing usable without fragile gestures

Preserve the existing light console, system fonts, and color tokens in `frontend/controller/controller.css`. Use the wall editor as the main work area. Keep an unplaced-device tray and a selection inspector beside it. Put Library, Playlist, and Playback controls in task-focused sections. A persistent status area distinguishes connected devices, required devices, ready devices, and degraded presentation. Keep protocol numbers and raw revisions in diagnostics rather than the primary operator path.

Use DOM or SVG geometry with native named controls and a synchronized accessible list. Do not require a canvas-only editor. Do not rebuild the entire map DOM during a pointer gesture as current `renderWallMap` does on every render. Hold a local draft and stable selected elements, then adopt an authoritative response.

Pointer behavior must include pointer capture, pan and zoom, constrained drag, multi-select, and cancellation. Begin with select then drag, with a movement threshold to avoid treating a tap as movement. Apply `touch-action` narrowly to the manipulation area. Keep normal page scrolling and browser zoom available outside that area. Use a larger hit target than a small tablet silhouette. A 44 CSS-pixel target is the design preference for inspector controls and handles, subject to rendered verification.

Snap body or active-area edges according to a clearly selected mode. Set the tolerance in screen pixels so it stays usable as the map zoom changes, then convert it into world units. Show the prospective snap line and measured gap. Provide an explicit snapping toggle and a modifier override. Never resize a measured tablet merely to fill a grid cell. Auto-arrange proposes rows using actual body sizes, orientation, and chosen gaps, preserves reservations, previews the result, and applies one atomic layout edit.

The selection inspector offers X and Y position, rotation presets, fine angle if enabled, gap controls, label, calibration, and measured dimensions. Distinguish immutable measured size from placement scale. To change the size, enter calibration mode. Grouping moves or rotates the selection around a stated pivot. Align, distribute, lock, ungroup, and undo are ordinary controls. Drag one local draft, then send one batch command on release. A group change fails atomically on a revision conflict or invalid geometry.

Keyboard behavior must reach every device and control in a predictable list order. Select from the list, use an explicit Move mode with arrow-key nudges, Shift for a larger step, Enter to apply, and Escape to cancel. Shortcuts act only while that editor mode has focus. Provide numeric position fields and tap-based nudge buttons so dragging also has a single-pointer alternative. Keyboard support alone does not meet the requirement for people using a touch pointer who cannot drag. [W3C dragging movements guidance](https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html). Retrieved 2026-10-23.

Announce selection, placement result, conflicts, and upload errors through a restrained live region. Do not announce every pointer move or buffer tick. Show focus and selection independently, and label offline, unknown, and error states with text or shape as well as color. Keep inline labels and form errors. Restore focus after confirmation dialogs and after a selected device disappears. Respect reduced motion in the controller; slideshow transitions are separately operator-controlled presentation content.

On narrow screens, switch the inspector and tray into selectable panels under the wall preview. The same numeric and nudge controls remain usable without a pinch gesture. Test long labels, empty walls, 20 devices, an all-offline layout, stale drafts, missing assets, permission denial, upload failure, and conflict recovery. Do not infer the quality of this redesign from source alone. Its implementation must go through desktop and mobile render, inspect, critique, fix, and verify cycles, including console and network inspection.

## Build separate and reproducible evidence layers

### Keep the fast API and JavaScript checks

Preserve `rtk make test`, which runs Python and Node client tests, and `rtk make sim`, which runs the current simulator plus its self-tests. These are future execution commands; I did not run them in this planning pass. Do not install dependencies implicitly during evidence collection. Use the project's prepared environment or report the missing prerequisite.

Extend API tests for v3 negotiation, old-client projections, strict geometry validation, atomic group edits, stale revision conflicts, idempotent retries, upload publication failures, reference-aware deletion, backup closure, and startup migration refusal. Add playback state-machine tests with an injected monotonic clock. Cover cancel during decode, stale readiness, seek before a scheduled start, a removed required member, session replacement, and restart from a higher old version.

Extend Node tests for physical transforms, inverse mapping, image-slot ownership, preparation cancellation, old callbacks, and deadline calculation. Include asymmetric bezel, negative wall offsets, cardinal rotations, one arbitrary angle, portrait/landscape viewport changes, fractional DPR, and a late previous-session callback. Keep a hand-derived independent geometric oracle. Reusing the production transform as both implementation and expected result would prove little.

Extend the Python simulator for protocol/version and multi-client state behavior, while retaining its explicit no-JavaScript/no-TCP/no-pixels limitation. Do not rename it a device simulator in a way that implies hardware fidelity.

### Add a real-browser multi-client harness

Create a proposed `simulator/browser/` runner that starts a disposable one-worker app process on loopback TCP with temporary database, media, and curated directories. Run a direct-backend mode and a separately configured two-origin proxy mode. Use the real controller page for representative operator flows and actual `/client/` JavaScript for each tablet.

Create one BrowserContext per tablet. Each gets independent localStorage, session storage, cookies, cache, display identity, and its own live WebSocket. Contexts may share one browser process for routine tests. Add a mode using separate browser processes and separate persistent profile directories to test process contention and reload/restart behavior. Reload within a context must preserve its display ID; a new context must get another ID. Never use one shared storage-state file for the fleet. Playwright documents these context isolation guarantees. [Playwright isolation](https://playwright.dev/docs/browser-contexts). Retrieved 2026-10-23.

Keep one deliberate same-context two-page test. It must reproduce duplicate identity and verify the replacement UI stops automatic contention. The normal multi-tablet tests assert N distinct registered identities and N simultaneously live sockets for at least a bounded observation period. Log identities and connection IDs, not just the number of browser windows.

Use fixture profiles such as 1024x768 DPR 1, 768x1024 DPR 2, 1280x800 DPR 1.25, and 800x1280 DPR 1.5. Add a high-DPR profile and browser-chrome viewport changes. Independently assign physical dimensions and bezels so identical CSS viewports can represent different-size panels. Seed irregular gaps, offsets, rotations, reservations, and touch input. These are test profiles, not claims about particular tablet specifications. [Playwright emulation](https://playwright.dev/docs/emulation). Retrieved 2026-10-23.

The runner records browser build, OS, fixture seed, app commit, viewport/DPR, exact identities, per-client socket events, screenshots, console output, failed network requests, status transitions, and cleanup results. Save reports outside the repository unless a test fixture explicitly belongs in source. Stop the app, proxy, contexts, browsers, readers, and impairments in `finally` paths. Never attach the fleet to the operator's current data or everyday browser profile.

Default automation uses the configured Playwright MCP and Chrome DevTools MCP for inspection, through browser-harness where interaction is needed. The reproducible runner uses the pinned Playwright API with equivalent explicit contexts. A separately coordinated implementation task must install or pin tooling if absent; this planning pass does not. Do not assume an MCP new-tab action creates an isolated storage profile. Validate isolation through observed IDs and storage.

Test Chromium, Firefox, and WebKit where available. Playwright's WebKit is patched upstream WebKit, not branded iPad Safari, and codec support depends on the host OS. Linux WebKit emulation is useful coverage but not evidence about an old iPad's decoder or autoplay. [Playwright browser support](https://playwright.dev/docs/browsers). Retrieved 2026-10-23.

### Apply impairments at the layer they describe

Use deterministic seeds and label every impairment report with its layer.

- For application protocol faults, use a test WebSocket relay or Playwright's connection-to-server routing to delay, duplicate, drop, or inject a bounded old message. The real app remains behind the relay. Playwright supports interception of real server-bound WebSockets. A route that does not connect to the server instead mocks communication and must not be reported as an integration pass. [Playwright WebSocketRoute](https://playwright.dev/docs/api/class-websocketroute). Retrieved 2026-10-23.
- Dropping a WebSocket application message is not IP packet loss. WebSockets normally use ordered reliable delivery. Actual loss often appears as retransmission delay, head-of-line blocking, or disconnect. Do not randomly reorder production WebSocket frames and call that realistic Wi-Fi behavior. Deliberate stale-message injection is still useful for validating rejection rules.
- For real TCP delivery and slow bodies, use a user-space test proxy with per-client endpoints and bounded delay/rate/disconnect behavior. It can shape actual bytes to browsers without sudo or host network changes. Record that it models delivery effects rather than physical RF contention. Test range requests, mid-body termination, slow reads, and a device that stops consuming control data.
- For HTTP request failure and latency, use context-scoped routing/offline controls. Delaying `route.fulfill` does not by itself model progressive streaming, so use the proxy for video-body stalls. Chromium CDP network and CPU controls are optional browser-specific probes, not a portable impairment system.
- For clocks, inject the application's clock adapter with a known offset, rate drift, discontinuity, and sleep jump. Do not patch only Date while the player reads performance time and claim drift coverage. Keep a separate unmodified-clock integration case. Do not fake the decoder clock and call it hardware drift.
- For decode and rendering failures, delay the loader adapter, limit CPU in a supported browser, abort real media responses, and provoke unsupported codecs. Synthetic delay validates control logic. Only the actual hardware measures decoder throughput and thermal behavior.
- For backgrounding, exercise actual visibility/lifecycle behavior where supported, then separately test an injected hidden/resume state for deterministic logic. A synthetic event does not prove OS suspension behavior. Browser contexts in a headless process are not equivalent to many foreground tablet screens. Chrome documents throttling of hidden-page timers. [Chrome timer throttling](https://developer.chrome.com/blog/timer-throttling-in-chrome-88/). Retrieved 2026-10-23.

The initial impairment grid includes asymmetric control delay of 20 to 150 ms, jitter of 0 to 100 ms, short disconnects of 1 to 10 seconds, a 60-second outage, body stalls, repeated reload, a stale generation, clock offsets of plus or minus 5 seconds, drift of plus or minus 100 ppm, and 0.5 to 5 second synthetic decode delays. These are deliberately chosen stress inputs, not measurements of the user's network. Include an unimpeded baseline before each class and one combined worst-case scenario. Report bounded failure or safe recovery when the conditions exceed capability; do not require good synchronization during an impossible outage.

### Use real tablets and optical observation for the final claims

Inventory every available tablet with physical label, make/model, OS build, browser build, launch mode, CSS viewport, DPR, known native resolution, measured panel/body size, calibration uncertainty, supported codecs, activation outcome, TLS trust, and power conditions. The minimum useful matrix is the oldest available iPad Safari, a newer iPad Safari, the oldest available Android browser, and a newer Android Chrome. If only two tablets are available, use both, report the absent categories, and keep those gates open. Never invent a model or claim that changing a desktop user agent filled a missing hardware row.

Run one device first, then a mixed pair, then a small mixed group, then the intended 15 to 20 physical clients if available. Repeat tab versus home-screen launch, portrait versus landscape, charging versus battery, local CA trust, sleep/foreground return, radio disconnect/rejoin, server restart, asset miss, and codec failure. A Screen Wake Lock request can be an enhancement on supported secure origins, but visibility changes can release it. The OS power policy and kiosk setup remain part of the real-device gate. [W3C Screen Wake Lock](https://www.w3.org/TR/screen-wake-lock/). Retrieved 2026-10-23, working draft.

All desktop clients on one laptop share its network interface, radio or wired link, OS scheduler, and some CPU/GPU resources. Separate profiles or processes produce independent client sessions and connections. They do not produce 20 independent physical radios, antenna positions, Wi-Fi contention/backoff behavior, roaming paths, or device clocks. Preserve that distinction in reports and dashboards. The existing hotspot AP/client same-channel and DFS context is a trial prerequisite, not app behavior. Do not change networking or use sudo as part of this plan.

For image cuts, display numbered black/white transitions and a common cue on all screens. Record the entire wall with an external high-frame-rate camera. Use a short exposure where possible. Detect the transition in each screen region and compute the maximum-minus-minimum visible time per event. For video, use a known constant-frame-rate test asset with burned-in source time/frame number, moving seam lines, and optional audio ticks. Record frames on all screens simultaneously and compare source frame positions. Repeat enough events to see tail behavior and drift.

Record camera rate and timestamp method, capture-file frame rate, exposure, rolling-shutter limitations, display region row positions, and detection ambiguity. At 240 captured frames per second, one camera-frame interval is approximately 4.17 ms, but that is only sampling resolution. It is not automatically measurement accuracy. Use a common external cue, account for rolling-shutter row offsets, and report an uncertainty interval. If the camera records only short samples during a longer run, report optical skew for those samples and list the unobserved intervals. A full-run optical acceptance claim needs adequate continuous evidence. A photodiode setup is a later option if camera uncertainty matters. Sequential screenshots from several pages cannot measure inter-screen visible timing.

Keep separate metrics for control round trip, estimated clock offset/age, scheduled-handler lateness, client-reported media-time error, preparation duration, stalls, and optical screen skew. For live input, also measure capture-to-glass latency with a filmed source clock or physical event visible beside the wall. A low WebSocket RTT or close `currentTime` values cannot substitute for optical synchronization.

## Adopt provisional acceptance targets and explicit fallback

These numbers are proposed product gates for an explicitly tested foreground, powered, mixed-device cohort on the intended local network. They are not observed results or guarantees for all browsers.

- A new connection appears and receives current configuration within 5 seconds on an otherwise healthy prepared LAN. After connectivity actually returns, recovery targets 10 seconds. Log server and device timing separately. Long offline periods are measured as outages, not hidden in an average.
- A calibrated still wall targets no more than 2 mm of visible line displacement at tested neighboring edges, beyond the intended hidden physical gap. Measure using fiducials and the recorded measurement uncertainty. If the ruler uncertainty already exceeds this target, refine calibration or qualify the result.
- For 100 scheduled still cuts, target optical max-minus-min skew at or below 100 ms for the 95th percentile and no event beyond 250 ms. Record per-event values and worst-device pairs. An unsupported or backgrounded required device makes the cohort unready rather than disappearing from the denominator.
- For a 10-minute constant-frame-rate file run, target steady-state optical skew at or below 100 ms for the 95th percentile and at or below 250 ms outside explicitly logged startup/recovery windows. Report every recovery window, its duration, any stall, and the full-run values too. A run does not pass by excluding most of its duration as recovery.
- The first sustained video gate requires no unplanned stall in the clean-network run and convergence within 5 seconds after a completed group rebuffer, excluding actual network restoration time. Controlled impairment tests may intentionally fail this target; they must instead demonstrate bounded, honest degraded state and recovery without stale playback.
- Software tests demand zero application of a superseded session/version command and no stale decode painting after cancellation. These are deterministic correctness properties, unlike optical timing tolerances.

Targets may need revision after the first hardware experiment. Preserve the initial target and failed observations when making that product decision. Do not quietly widen tolerances and describe the old target as met. Even 100 ms can look wrong for fast motion crossing a seam. If the measured wall looks unacceptable, use stills or slower content, exclude incompatible devices, or choose hardware with coordinated outputs. Browser playback on unrelated displays cannot promise frame-lock or a common scanout phase.

## Execute in phases with evidence at each boundary

### Milestone 0. Capture baseline and available hardware evidence

Depends on no new media functionality. Inspect the prepared runtime and execute the existing Python, Node, simulator, and deployment smoke checks in disposable environments. Build the isolated browser runner. Capture current stills on desktop and on available tablets, and reproduce shared-storage replacement. Also run a minimal native MP4 test fixture on available tablets for decode, muted activation, preload, seek, CSS clipping, and rotation before locking the video-related design in milestone 2. This is a bounded test fixture, not a claim that the current application supports video. Use `deploy/KIOSK.md` and the ingress checklist before claiming the current reference is validated. Record missing hardware and tooling. Do not claim an unattended deployment from the existence of service templates.

Acceptance is a reproducible baseline report, exact tested builds, N distinct browser identities with N sockets in normal fleet mode, a same-storage replacement reproduction, and a documented physical-evidence status. Software work can proceed with missing hardware recorded, but physical and timed-media release gates remain open.

### Milestone 1. Ship upload and a usable calibrated still workflow

Depends on baseline regression checks. Land duplicate ownership handling, managed image ingest/index, reference-aware backup, v3 physical geometry, numeric calibration, and one atomic layout edit. Then add drag, nudge, saved-layout reuse, and content preview. Keep static display status honest. Existing v1/v2 fixtures and curated asset IDs survive unchanged.

Acceptance is an uploaded phone photo with EXIF orientation normalized, one shared image across independently identified clients, asymmetric measured displays with bezels and rotation, a saved layout recalled without changing the scene, a scene recalled without moving tablets, and a new-target restore that serves the selected image. Verify pointer, touch, keyboard, screen-reader smoke, desktop/mobile rendering, console, and network. Physical still quality remains conditional until the mixed tablet trial passes.

### Milestone 2. Ship timed still cuts and operational visibility

Depends on v3 status, ordered outbound transport, and validated still rendering. Add clock estimation, preparation ownership, session/version snapshots, cancellation, and timeline-driven slideshow. Add group participation and slow-device policy. Keep readiness distinct from optical evidence.

Acceptance is deterministic stale-command/reconnect coverage, 100 cuts in isolated real browser clients with captures and status traces, safe behavior under delayed decode and disconnect, and the optical mixed-tablet gate. Default to hard cuts and bounded next-image preloading. Do not proceed to a video synchronization claim using only this milestone's timer tests.

### Milestone 3. Prove prerecorded-video viability, then ship it

Depends on the shared timeline and a physical media-profile probe. Add bounded file ingest/probe, range serving, native video geometry, muted activation flow, observed buffer goals, scheduled playback, seek/pause/loop, and recovery. Validate ingress HEAD/range behavior. Extend backup for large media and renditions before a video upload can be considered recoverable.

Acceptance is the 10-minute optical run on the selected codec/profile, exact tested hardware list, no unplanned clean-run stall, honest degradation under impairments, and complete restore of a selected video and its metadata. If a mixed pair cannot pass, stop increasing fleet size, compare a lower common profile, and document whether video scope is reduced. A prototype failure is a useful decision, not a reason to promise HLS will automatically fix it.

### Milestone 4. Harden the validated fleet

Depends on hardware evidence through the deployed still/video scope. Add the longer soak, structured diagnostics export, readiness/liveness endpoints, storage health and quota display, controller disconnect detection, and startup preflight. Revisit baseline phase-3 work in the existing README with real evidence. Verify WAN-disconnected restart, certificate trust, backup/restore, and intended physical-client count. Keep one ASGI worker. Address an actual deployment's supervision and ownership before calling it unattended.

Acceptance includes a two-hour foreground media soak, an overnight still soak if unattended use is desired, recovery drills, and no leaked processes or stuck jobs. Report thermal and power conditions. A short load-smoke run cannot substitute for this.

### Milestone 5. Choose segmented or live media only from demonstrated need

Depends on a clear latency requirement and measured shortcomings or demand. Compare HLS packaging against native file behavior for prerecorded delivery, or delayed HLS against WebRTC for live sources. Use the same timeline/status/evidence model. Record a decision with browser matrix, packaging cost, real source delay, optical skew, and fallback. Ship only the chosen subset.

## Open the first ten tickets in this order

Each ticket below is a reviewable unit with explicit scope. Implementation owners should attach actual commands, logs, screenshots, and hardware records to acceptance results. Use browser-harness with the configured browser tools for rendered inspection and stop its processes afterwards.

1. **Add isolated browser baseline coverage.** Touch proposed `simulator/browser/`, `simulator/README.md`, and the minimal test-runner configuration. Read `simulator/harness.py` for isolation conventions but keep that API runner separate. Run two real client contexts against disposable loopback TCP, assert separate storage IDs and simultaneously live sockets, reload one, and show one curated still. Add the intentional same-context collision case. Save per-client screenshots, console/network logs, and cleanup receipts. Expand to the 18-profile routine fleet only after the pair works. Dependency: none.
2. **Fix display ownership and validate registration boundaries.** Touch `client.js::openSocket/attemptCycle`, `main.py::DeviceRegistration/ws_device`, `state.py` liveness, `protocol.py`, and protocol tests. Stop automatic retry after `4409`, expose deliberate takeover, preserve stable identity on ordinary reload, and add page-session diagnostics without treating UUIDs as credentials. Bound registration and capability payloads and add monotonic expiry bookkeeping. Acceptance: the duplicate-page browser test stops contention, distinct contexts remain online, normal loss/restart reconnect still works, and v1/v2 handshake fixtures remain valid. Dependency: ticket 1.
3. **Upload managed stills with an index and recoverable storage.** Touch `assets.py`, proposed `media.py`, `persist.py`, operator routes/UI, `deploy/backup.py`, and asset/security/backup tests. Implement staging, bounded worker decode, EXIF normalization, content IDs, quota/error results, thumbnails, and owned-store lookup. Preserve curated IDs. Extend backup and restore before accepting persistent upload success. Acceptance: valid and malicious input matrix, duplicate upload, canceled and crashed ingest, disk-full failure, HTTP serving of published bytes only, UI error recovery, and verified restore. Uploads remain denied on tablet ingress. Dependency: tickets 1 and 2.
4. **Introduce v3 physical layouts and calibration.** Touch proposed `geometry.py` and `displays.py`, `state.py::_wall_frame`, `main.py` layout/calibration models and commands, `persist.py`, client rendering, `PROTOCOL.md`, saved-snapshot validators, and geometry/migration tests. Add explicit physical units, viewport mapping, rotation and offsets, schema versions, atomic batch layout edits, and revision preconditions. Add numeric calibration and current static render status. Acceptance: hand-derived transforms for asymmetric bezels and mixed DPI/rotation; legacy logical fixtures still render as before; conversion asks for a scale or measurements; stale edits are rejected atomically; viewport changes invalidate calibration; mixed-tablet ruler evidence is recorded where available. Dependency: ticket 2. Can overlap upload backend work with strict file ownership agreed by the coordinator.
5. **Make arrangement and preview the primary operator workflow.** Touch proposed `layout-editor.js`, controller HTML/CSS/JS, local preview helpers, and browser flow tests. Add stable selected elements, unplaced tray, pointer drag, snapping, group moves, rotation, numeric/nudge alternatives, undo draft, identify, measured-size auto-arrange preview, and existing named save/recall integration. Acceptance: one batch request per completed gesture, no writes on cancellation, keyboard and single-pointer equivalents, revision-conflict recovery, preserved reservations, global fit/crop preview, and desktop/mobile rendered review. Dependency: tickets 3 and 4 for the complete initial slice.
6. **Add versioned playback control, readiness, and clock diagnostics.** Touch proposed `playback.py`, `clock.js`, client playback module, `hub.py` ordered sender, device message validation, controller status, and `PROTOCOL.md`. Preserve `_commit_wall` durability. Add connection-scoped readiness, immutable snapshots, command versions, prepare/cancel/commit, and clock estimation with uncertainty/age. Acceptance: fake-clock model tests, stale readiness rejected after replace/reload, slow socket cannot delay all peers, first frame remains welcome, and a scheduled numbered-flash experiment reports software and optical metrics separately. Dependency: tickets 1, 2, and 4.
7. **Add synchronized still playlists.** Touch playlist persistence, backup reference traversal, playback and image preload modules, controller playlist editor, Node/API tests, and browser scenarios. Implement frozen playlist revisions, durations, hard cuts, loop, pause/next/previous, and bounded current/next cache. Acceptance: 100 transitions, same item occurrence after late reconnect, no old decode or canceled cut applied, group holds for a slow required display, and physical skew recorded against the provisional gate. Dependency: tickets 3, 5, and 6.
8. **Probe and serve a compatible prerecorded video profile.** Touch proposed video ingest/probe and range-serving code, media schema, exact Caddy read allowlist, backup limits/manifest support, and transport tests. The experiment uses the actual transformed native video route on a mixed pair. Acceptance: a real codec/activation matrix, bounded unsupported-file handling, valid seek/range/HEAD/416 behavior through proxy, large-file restore, and recorded optical behavior for candidate 720p and lower profiles. Dependency: tickets 3, 4, and 6. Decide whether video can proceed before building the full playback UI.
9. **Add buffered scheduled file playback and recovery controls.** Touch client video/timeline module, playback session policies, controller playback controls, capabilities, and media browser tests. Implement observed buffer goals, countdown, versioned play/pause/seek/loop, muted activation and errors, bounded correction, and scheduled group rebuffer. Acceptance: clean 10-minute tested-cohort run, every impairment ends in bounded recovery or an explicit failure state, quality changes re-prepare rather than silently diverge, and all stale events are rejected. Dependency: tickets 7 and 8, with ticket 8's hardware decision passed.
10. **Publish a repeatable tablet and deployment validation record.** Touch simulator/browser impairment fixtures and reports, `deploy/KIOSK.md`, `deploy/OPERATIONS.md`, `deploy/README.md`, and scoped health/diagnostic code. Include a user-space impairment proxy, actual-radio fleet runs, optical analysis procedure, WAN-disconnected operation, sleep/resume, certificate trust, quota behavior, backup restore, and soak results. Acceptance: exact build/device matrix, target results with uncertainty and failed gates visible, leak-free teardown, and deployment status rewritten only to what the evidence supports. Dependency: tickets 5 and 7 for still release, then ticket 9 for video release. No sudo or network mutation in automated tests.

## Migrate without reinterpreting existing walls

Before a schema upgrade, take and verify a snapshot with the old tool. Add ordered, versioned SQLite migrations and migration fixtures from the current schema. Back up to a new destination and keep the prior database and assets for rollback. Unknown future schema versions refuse startup or restore without modifying their inputs.

Existing active/saved layouts become schema-versioned logical layouts. Never assume that one current wall unit equals one millimetre. Conversion takes a chosen scale and actual display measurements, previews old and new geometry, and saves a new physical layout without overwriting the original. Old negative bezel values become conversion warnings requiring a corrected measurement. Old scene asset IDs remain byte-stable. Existing scene recall continues to affect content only.

New physical data and new media descriptors require v3. Cached v1/v2 clients remain usable on logical layouts, receive only supported frames, and are shown as requiring upgrade for physical/timed membership. Keep static revalidation headers and an operator-visible client build ID so cached-client problems can be diagnosed. A connection's advertised capability is not silently promoted when the server upgrades.

Backup manifests need a version that describes new store locations and reference closure. The new verifier reads supported old manifests and restores into new targets. The old verifier must refuse an unknown new format. Do not retrofit large video support by only increasing the existing 10 MiB constant; its format checks, asset locating, reference traversal, and restore verification all need explicit tests.

Each implemented feature keeps one-worker operation. CPU-bound normalization and optional encoding have bounded job queues. They are not extra independent ASGI replicas sharing the same database. If measured storage contention later requires a writer task, migrate all state-changing callers to it together and retain the persist-before-notify property.

## Record the risks and deliberate deferrals

The largest unknown is hardware behavior. No source inspection can establish the decode limit, memory pressure, browser suspension, Wi-Fi capacity, panel refresh phase, or thermal throttling of the user's tablets. The first mixed pair is a decision gate, not a final demonstration after months of video work.

Changing from logical cover to physical mapping can expose existing aspect mismatches. Keep migration explicit and preserve the old layout. A viewport without a valid calibration is unready for a physical timed wall. Do not compensate by stretching known physical size or using negative bezels.

The exact proxy allowlist is easy to break when splitting client scripts or adding HEAD/media paths. Every such change includes positive tablet-route tests and negative operator-route tests, including encoded paths. Keep backend isolation and operator authentication intact. Pairing/revocation and private asset reads are separate scoped work if the LAN is not trusted or media is sensitive.

An all-required readiness policy can let one absent reservation block presentation. Make the participant set visible and exclusion explicit. A best-effort partial wall is a legitimate option, but its label must state what is missing. No distributed prepare/ack exchange can guarantee that a tablet will not suspend immediately after saying ready.

Defer frame-lock claims, arbitrary per-device live latency promises, DRM, multicast, a native kiosk application, automatic camera-based calibration, perspective mapping of noncoplanar walls, arbitrary user URLs, broad third-party media embeds, large adaptive ladders, server-generated tile videos, multiple ASGI workers, public internet exposure, and a service-worker offline playback product. None is necessary for the first uploaded image or synchronized still cuts.

Useful smaller additions earn their place earlier: human device labels, identify mode, replace-device/rebind-slot, content/layout preview, explicit Stop or neutral scene, diagnostics export, storage/quota visibility, and a local setup preflight. Wake lock can be a tested progressive enhancement. Do not claim that it keeps a backgrounded page scheduling normally or replaces OS kiosk configuration.

## Leave product decisions visible, with usable defaults

- Who can upload? Default to the operator laptop through the existing authenticated origin. A tablet or phone uploader needs an explicit scoped sharing flow later.
- Is media private? Default to the existing trusted-LAN public tablet-read model, with an honest label. Sensitive media requires pairing and asset authorization before use.
- What hardware must work? Default to all available tablets for stills and a separately named tested cohort for video. Record exact old/new iPad and Android builds. Missing hardware remains an unresolved gate.
- What counts as synchronized enough? Start with the provisional 100 ms p95 and 250 ms maximum gates above, then evaluate moving seams on actual glass. Keep the original target and results when changing the product requirement.
- Should one slow tablet stop everyone? Default to Keep wall together. Offer named exclusions and a clearly partial mode. Do not quietly remove an offline reservation from required participants.
- How should seams look? Default to measured physical gaps. Repeat-near-seams mapping is an explicit content choice with a preview, initially only for regular arrangements.
- What should play after restart? Restore layout and selected content, then prepare/paused for timed media. Do not auto-start video or audio after recovery.
- Where does audio play? Muted everywhere by default. Later choose one explicit local output and measure its offset.
- Does a backup include every upload? Preserve referenced-content snapshots initially. Show unused items outside the snapshot. A full-library export is a separate option if uploads are an archive.
- Is live delay acceptable? Leave live implementation deferred until the operator chooses delayed coherent presentation or interactive mirroring. That decision changes the transport experiment.
- How large is the final wall? Use 15 to 20 independent browser clients as routine logical-load coverage and grow to the actual available physical fleet for radio and hardware evidence. Do not present the browser count as a supported physical-client capacity.

The next action is ticket 1's reproducible baseline, followed by the uploaded-still and physical-layout slice. The reciprocal review should challenge the identity ownership rule, physical transform and migration, prepare/version invariants, native-video fallback, and whether each acceptance claim has evidence at the layer it describes.
