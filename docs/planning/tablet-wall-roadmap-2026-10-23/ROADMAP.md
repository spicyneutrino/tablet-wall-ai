# Tablet wall roadmap

Final synthesis by Sol, gpt-6.1-sol at max reasoning, 2026-10-23. Based on independent Sol and Cursor Opus 5.5 proposals, their reciprocal reviews, source inspection,
parent evidence, and the available Opus task activity. The user authorized Sol final authorship after the Cursor Opus quota failure and Claude Opus rate-limit failure.
Opus contributed the original proposal and cross-review. Opus did not review this final synthesis. See [review decisions](REVIEW_DECISIONS.md) for adjudication and
[transcript notes](OPUS_TRANSCRIPT_NOTES.md) for activity evidence and limits.

## Executive recommendation

Ship upload-and-show on the current logical wall first. Then ship physical calibration and a small drag editor, synchronized slideshow cuts, and native buffered
prerecorded video. Treat segmented delivery and live capture as later decisions driven by an actual source, fleet, and delay requirement. Keep FastAPI, vanilla
JavaScript, SQLite, local HTTP media, and one ASGI worker. Decoder subprocesses are bounded jobs, not additional app workers.

The durable records are media, display measurements, calibration, layouts, scenes, and playlist settings. A running presentation has its own process-local session and
version. Never persist every slide tick or reuse a previous process's monotonic anchor. Preserve existing logical units and cached-client behavior wherever their contract
still applies.

All proposed limits, durations, fleet sizes, tolerances, and thresholds below are provisional. They are choices for experiments or initial operation, not measured
capacity or performance. The parent baseline and inspected current constants are explicitly identified separately. Independent browser sessions are useful software
evidence. Physical synchronization requires simultaneous optical measurement. This plan promises neither frame lock nor matching panel scanout.

## Actual baseline and limits

The source baseline is commit `65a4d5081194c457c74a8c6aae629281a30e634b`. The parent ran the existing simulator and recorded 23 passed scenarios and 1075 passed checks.
That run used in-process TestClient. It exercised protocol and arithmetic, not real client JavaScript, TCP, browser pixels, decoding, or optical synchronization. The
recorded [simulator baseline](BASELINE.md) and [parent observations](parent-observations.md) are the evidence. This synthesis did not rerun that simulator or
any application tests.

The parent observed one online client reporting a 1152 by 720 CSS viewport, one offline client, and one associated hotspot station. Those observations were not correlated
to one physical identity. The hardcoded `ipad` device type does not identify its OS, browser, or hardware. The laptop AP and station interface were both on channel 44.
This is an observation, not a network-capacity result. No browser/pixel inspection or physical optical test was performed in this planning work.

Current features are UUID registration, one socket per identity, v1 color, v2 logical layouts, calibration patterns, curated stills, and separate named layout/scene
recall. Placements have integer abstract units, rectangular bezels, and no physical rotation. The tablet applies global image cover plus a centered per-device cover. The
controller map focuses numeric fields. It has no drag editor. There is no upload, playback clock, readiness protocol, playlist player, or video player. The deployment,
TLS, kiosk, and physical-device gates remain open in [README.md](../../../README.md) and [KIOSK.md](../../../deploy/KIOSK.md).

## Source ownership and implementation boundaries

Existing entry points remain authoritative until a ticket replaces their responsibility.

| Existing file | Relevant ownership |
| --- | --- |
| [main.py](../../../main.py) | Registration, origin guard, HTTP/socket adapters, saved-state validators, `_commit_wall`. |
| [protocol.py](../../../tabletwall/protocol.py) | Version negotiation, close codes, caps, IDs, and legacy fit constants. |
| [state.py](../../../tabletwall/state.py) | Process-local roster, wall state, per-version frame projection, presence. |
| [hub.py](../../../tabletwall/hub.py) | Broadcasts, connection ownership, sweeper, future ordered socket delivery. |
| [persist.py](../../../tabletwall/persist.py) | SQLite state and named snapshots, future schema migrations. |
| [assets.py](../../../tabletwall/assets.py) | Curated-file validation, exact-byte identity, inventory and fetch. |
| [client.js](../../../frontend/client/client.js) | Identity, reconnect, image-attempt fencing, canvas, current renderer. |
| [controller.js](../../../frontend/controller/controller.js) | Existing operator flows, map, numeric edits, save/recall. |
| [backup.py](../../../deploy/backup.py) | Captured-DB reference traversal, checksums, new-target restore. |
| [hotspot.Caddyfile](../../../deploy/hotspot.Caddyfile) | Tablet allowlist and authenticated operator ingress. |
| [simulator/](../../../simulator/README.md) | Fast API/state/geometry evidence with explicit limitations. |

Add these files only as the owning feature lands. Every path in this table is proposed.

| Proposed file or directory | Single responsibility |
| --- | --- |
| `tabletwall/media.py` and `media_worker.py` | Indexed objects, ingest jobs, normalization/probe, publication and quota. |
| `tabletwall/displays.py` and `geometry.py` | Immutable measurements/calibration and canonical committed physical transforms. |
| `tabletwall/playback.py` and `clock.py` | Session state machine, preparations, deadlines, clock epoch and suspend detection. |
| `frontend/client/view.js`, `clock.js`, `playback.js`, `video.js` | Panel-to-viewport application, time adapter, timeline ownership, native video. |
| `frontend/controller/layout-editor.js` and `media-library.js` | Local layout draft and media task UI. Reuse existing visual tokens. |
| `simulator/browser/` | Disposable real-server browser fleet, profiles, impairments, reports and cleanup. |
| `tools/optical/` and `tests/fixtures/geometry/` | Capture analysis and independently derived transform fixtures. |

Retain classic scripts and the existing tablet syntax floor. Avoid a framework, build requirement, or TypeScript migration. Add each new public client script explicitly
to the ingress allowlist and deployment tests. Extract touched responsibilities rather than restructuring the whole client or controller. Preserve `_commit_wall`
durability. Its callback currently runs on the proposed copy and again on live state. Capture IDs/timestamps before that callback. Keep it deterministic and free of timer
creation or other side effects. Do not insert an await into this boundary. A later asynchronous writer requires complete serialization and measured justification.

## Domain records and persistence

Use discriminated validated records at HTTP, socket, worker-result, and persistence boundaries. Keep database schema version, document schema, socket major, durable
revision, and runtime version distinct.

| Record | Required shape and lifetime |
| --- | --- |
| `MediaAsset` | Normalized master object ID, name, kind, pipeline version, dimensions, ready/failed state and rendition relationships. Durable. |
| `MediaObject` | Exact-byte SHA-256 ID, MIME, byte count, immutable location, publication role and dimensions/codec metadata. Durable. |
| `Rendition` | Its own object ID, parent/master ID, role, dimensions and normalized-coordinate mapping. Durable. |
| `DisplayProfileRevision` | UUID endpoint label, native-reference active dimensions, four bezels, optional panel pixels, measurement provenance. Immutable revision. |
| `ClientSession` | Page-load ID, server connection ID, negotiated major/caps, viewport sequence, activation/visibility and monotonic contact age. Ephemeral. |
| `CalibrationRevision` | CSS-to-panel mapping, allowed viewport signatures, uncertainty, method, optical presentation lead and evidence references. Durable. |
| `Layout` | Document schema, `logical` or `physical` kind, fixed content bounds, slots, bindings and frozen measurement/calibration references. Durable. |
| `Slot` | Stable mounting position, body-center pose, orientation, nudge, expected profile and participation setting. Durable. |
| `Scene` | Content variant and global fit/settings. Recall changes content only. Durable. |
| `Playlist` | Versioned saved-scene payload containing ordered still assets, dwell, cut transition and loop setting. Durable. |
| `PlaybackSession` | Generation, clock epoch, session ID/version, frozen selected revision, policy, active timeline and one pending preparation. Ephemeral. |
| `Preparation` | ID, originating version, item occurrence, exact object/geometry refs, frozen participants, deadline and leased readiness. Ephemeral. |
| `RenderPlan` | ID/sequence, source aspect, panel matrix/clip, layout/scene/profile/calibration revisions and allowed local mapping signatures. Derived. |
| `DeviceStatus` | Connection/session/version/preparation lineage, bounded phase/reasons, sample age, clock and media diagnostics. Ephemeral. |

A display ID identifies a browser endpoint. It is neither a hardware fingerprint nor an authorization credential. A slot survives endpoint identity loss or replacement.
Rebinding requires identification and calibration validation. Saved layouts freeze profile revisions. Editing a measurement must not silently change every saved layout.
Saved scenes strip runtime sessions. Saving a scene does not save a layout. Keep the legacy color/calibration/image snapshots readable. A playlist initially needs no
separate reusable playlist table.

Use ordered migrations at startup with `PRAGMA user_version` and a verified pre-migration backup. Schema 0 is today's database. Schema 1 adds the managed media index and
version metadata while retaining legacy document shapes. Schema 2 adds versioned layout/scene envelopes and display/calibration records for v3. Migrate legacy records
into `kind: logical` envelopes transactionally at schema 2. Validate active and saved records before startup can rewrite the generation row. Unknown future schemas or
damaged required records refuse startup without replacing them with defaults. Keep pre-migration database, media and compatible backup tooling for rollback. Old binaries
do not gain this guard retroactively. Starting one on a migrated database is unsupported.

## Physical coordinates and calibration

### Define the spaces and directions

Wall space `W` is millimetres, X right and Y down, viewed from the audience. Content bounds are an explicit wall rectangle. Moving or disconnecting a tablet never changes
those bounds automatically. Body space `B` is centered on the tablet body in its recorded native orientation. Panel space `P` starts at the active panel's top-left in
that same orientation. Viewport space `C` is CSS pixels relative to the actual stable render rectangle. Backing space `D` is canvas pixels chosen by the application.
Source space `N` is normalized upright content, with both axes spanning 0 to 1.

Record active width `Aw`, active height `Ah` and nonnegative native-edge bezels `L,T,R,Btm`. Derive body dimensions `Bw = L + Aw + R` and `Bh = T + Ah + Btm`. The active
top-left in centered body coordinates is `a = [-Bw/2 + L, -Bh/2 + T]`. For active 100 by 60 mm and bezels 13, 13, 7, 17 mm on left, top, right, bottom, the body is 120 by
90 and `a = [-47,-32]`. That is hand-derived fixture arithmetic, not a measurement of a real tablet.

Use column vectors. A named matrix `M_X_to_Y` maps points in X into Y. Multiply rightmost first. Positive rotation is clockwise in this Y-down coordinate system. Canvas
six-number arrays mean `x' = a*x + c*y + e` and `y' = b*x + d*y + f`.

```text
M_B_to_W = translate(centerMm + nudgeMm) * rotateClockwise(mountAngle)
M_P_to_W = M_B_to_W * translate(a)
F_N_to_W = the scene's one global normalized-source-to-wall fit
G_N_to_P = inverse(M_P_to_W) * F_N_to_W
canvasTransform = backingScale * inverse(U_C_to_P) * G_N_to_P
```

The server owns `G_N_to_P`, clipping in panel space, fixed bounds, placement and global fit. The tablet owns only its calibrated live `U_C_to_P` and backing scale. It
does not recompute mount pose, physical gaps or global fit. The controller may compose a local draft preview, but committed server results replace the preview after
Apply. The independent simulator oracle and hand-derived fixtures remain separate implementations.

For a rendition of `Wr` by `Hr` pixels, normalize its pixels with `diag(1/Wr,1/Hr,1)` before applying `G_N_to_P`. Use the rendition's actual dimensions, not the uploaded
source's dimensions. All initial renditions preserve the complete upright image. No implicit per-device crop is allowed. Video uses the same normalized mapping, composed
into CSS element coordinates without canvas backing scale. Set its transform origin explicitly and clip to the usable viewport. For canvas, backingScale uses actual
backing-width/rectangle-width and backing-height/rectangle-height ratios, including integer rounding. For video, normalize the explicitly sized element's local CSS box
before the panel transform. Do not multiply CSS placement by DPR.

For centered cover/contain of upright source dimensions `Iw,Ih` into bounds `w,h`, choose `s=max(w/Iw,h/Ih)` or `min`. Then `F_N_to_W = translate(boundsOrigin +
[(w-s*Iw)/2,(h-s*Ih)/2]) * scale(s*Iw,s*Ih)`. A later focal-point adjustment belongs in this one server fit. It never changes body placement or calibration. Paint an
explicit background for contain/alpha regions.

### Keep mount and browser orientation separate

Mount angle describes the body's pose on the wall. OS/browser orientation describes CSS axes relative to the native panel. Their values can differ under orientation lock.
A 180-degree flip can retain identical viewport dimensions and DPR. Do not infer orientation solely from portrait versus landscape dimensions. Use an operator-confirmed
top-edge arrow and a calibrated mapping of available orientation reports.

An initial `U_C_to_P` is `translate(panelOffsetMm) * Q(q,wMm,hMm) * scale(mmPerCssX,mmPerCssY)`. `Q` rotates the usable viewport and translates its rotated bounding box
back to a positive corner. For q of 0, 1, 2, 3 quarter turns, its point mappings are `(x,y)`, `(h-y,x)`, `(w-x,h-y)`, `(y,w-x)`. The offset locates that oriented bounding
box within the active panel. It does not include bezels a second time. Store which browser edge anchors the calibration. Do not guess toolbar offsets from an aspect
ratio.

Calibrate both physical spans and viewport origin with rulers/edge markers in the intended launch mode. Known model specifications can prefill measurements with
provenance. Unknown model or panel pixels remain unknown. Native PPI can be computed from known panel pixels and measured inches. It is descriptive metadata. DPR and CSS
absolute units do not establish physical size. Backing scale may be capped for memory and differs from native panel density. [CSS
units](https://drafts.csswg.org/css-values-4/#absolute-lengths).

Record canvas rectangle, CSS viewport, visual viewport/scale where available, DPR, orientation including 180 degrees, launch/fullscreen mode and browser build. Use a
viewport sequence and local mapping version independent of durable wall revision. Resize, orientation, zoom, mode changes, identity replacement, or changed calibration
invalidate preparation evidence immediately. Reuse a live mapping only when a calibrated rule covers the new signature. Otherwise report Needs calibration. Hold the last
still with a clear marker or use the neutral scene. Do not silently claim accurate physical placement. Fullscreen/standalone are the initial physical acceptance modes.
Tab mode remains qualified until its usable mapping is measured.

The `100lvh` canvas box versus `innerHeight` drawing basis is an unobserved hypothesis. P0 compares actual rectangles, backing dimensions and screenshots before
prescribing a CSS change. Measure a laid-out stable container or visible surface, since hidden `#surface` has no useful box. If mismatch occurs, use one measured
rectangle consistently and preserve the documented bottom-strip protection. Large viewport units can extend behind expanded browser UI. That supports the experiment, not
a diagnosis. [Viewport specification](https://drafts.csswg.org/css-values-4/#viewport-relative-lengths).

### Preserve physical gaps and existing layouts

Default physical sampling treats bezels and air gaps as hidden parts of one continuous image. Rotate asymmetric bezels with the body. Keep signed placement offsets and
reject negative physical bezels. Do not resize a measured tablet to make a grid fit. Keep compact/no-gap and duplicated seam bands deferred to validated regular groups
with explicit preview. Those modes change content sampling, never measured body dimensions. An irregular rotated wall has no unique hole-collapse mapping.

Legacy conversion asks for an explicit scale and measurements, previews the result, and creates a new physical layout. Do not label current units as millimetres or derive
a physical approximation for a legacy renderer. Flag negative legacy bezels for correction. If native orientation changes, convert their edge interpretation explicitly.
Offer Fit bounds to arrangement as an explicit draft action, not a side effect of presence or binding.

## Protocol, HTTP and upgrade contract

Choose socket major 3 for physical render plans and timed playback, for both device and controller. Keep v1/v2 as legacy logical contracts. R1 uploaded stills use the
existing v2 image descriptor unchanged. Optional fields or diagnostics can be additive, but changed unit/placement/timeline semantics require the chosen v3 contract. Do
not implement a second physical/timed contract inside v2 capabilities. v3 capabilities still state supported rendering/media features; a major version alone does not
prove decode support.

| Peer or artifact | Logical static state | Physical or timed state / downgrade |
| --- | --- | --- |
| Cached v1 device | Existing color contract only. | Color only. Never a synchronized member. |
| Cached v2 device with image cap | Existing logical placements and exact-byte still URLs, including managed uploads. | Color/unplaced fallback with no physical placement or timeline claim. Listed as upgrade needed. |
| New v3 device, new server | Explicit logical mode or physical plan and negotiated capabilities. | Eligible only with the required geometry/timeline/media features and valid preparation evidence. |
| New device, old server | One `4426` can select v2 logical/static compatibility mode for that connection. | Clear v3 capability state and all prepared work. No physical/timed fallback. |
| Cached v1/v2 controller | Existing read/write shapes while the wall is logical/static. | Close its old operator socket with `4426`; legacy affected reads/writes return `409 Upgrade controller`. |
| New controller, old server | One bounded legacy-mode negotiation, visibly limited to old logical controls. | Physical/timed controls disabled. No repeated reload. |
| Legacy saved layout/scene | New reader validates original shape and wraps it as logical/static. | Conversion creates a separate record. Recall never invents missing measurements. |
| Schema 0 database or manifest 1 backup | Supported migration/new-target restore with old-state fixtures. | New runtime session after restore, timed content paused/preparing. |
| Future schema/manifest | Updated reader refuses before modification. | Old binaries on upgraded data are unsupported; restore the matching pre-upgrade set to downgrade. |

When new state is active, fence every legacy mutation affecting configuration, selection, references or device placement. That includes old recall, auto-arrange,
delete-device/placement, color/scene writes and saved-record overwrite/delete paths. Do not fence only `PUT /wall` while leaving another route able to erase v3 state.
Registration and heartbeat remain public endpoint-introduction operations. They confer no operator privilege. Legacy diagnostics can expose roster/build facts, but cannot
fabricate a v2-shaped physical wall. An excluded v2 device receives color with null placement in a fixed neutral logical envelope, never physical millimetres relabelled
as logical dimensions.

| HTTP contract | Chosen behavior |
| --- | --- |
| Existing logical routes | Preserve old bodies and successful behavior for logical/static walls. Optional `If-Match` may protect upgraded callers. |
| R1 `POST /uploads` | Operator-only streamed single-image ingest. Returns job state and exact ready display-object ID. Proposed route. |
| Existing `GET /assets/{id}` | Curated or ready published managed image bytes, same descriptor/ID semantics. |
| `/api/v3/config` and layout/scene/calibration writes | Typed reads and atomic batch writes. Required resource ETag. Proposed routes. |
| `/api/v3/playback` commands | Expected generation, session ID/version and bounded idempotency key. Proposed route family. |
| `GET/HEAD /media/{id}` | Later ready video/object delivery with ranges, same-origin descriptors. Proposed routes. |
| Failed preconditions | `428` if required header is absent, `412` for stale `If-Match`, `409` for semantic/session conflict. |

Use durable revision preconditions for configuration and session-version preconditions for playback. Check them inside the serialized acceptance boundary after awaited
validation, not before. Return the current resource and a conflict explanation. Retrying an idempotency key returns its original result within a bounded retention window.
Do not auto-merge another controller's layout into a local draft.

Static files retain revalidation. Include served build ID and actual loaded build in diagnostics. A newly shipped client may implement an authenticated operator reload
command and bounded build-change reload. An already cached build without that handler cannot be remotely repaired by this feature. Expect one manual refresh/origin
migration. Do not reload blindly on `4426`. Negotiate one supported legacy mode, or stop with an upgrade message. Limit automatic build reload to once per served build
per page session, and stop on repeated incompatibility. Remote reload is a later convenience in the shared v3 transport work, not an R1 upload dependency.

Use one bounded writer per connection. Queue welcome and initial snapshot before publishing the socket to broadcasts. Preserve negotiated initialization: legacy
controller first-frame snapshots and v1 device framing remain unchanged. Capture immutable accepted state and project all versioned frames from that state. Use a single
FIFO with coalescing only for replaceable complete snapshots/status. A complete playback snapshot includes active and pending/committed future action, so coalescing
cannot remove a required prepare. Stamp clock send time when the writer schedules transmission. Initial queue budgets of 64 messages, 1 MiB serialized data and a 5-second
send timeout are provisional. Overflow or sustained slow sending closes that connection and requires snapshot recovery. Cleanup must check ownership so an old writer
cannot drop its replacement.

## Image ingestion, admission and recovery

### Admit an operator explicitly

Default uploads to disabled unless one explicit admission mode is configured. The normal mode uses the existing authenticated operator listener, a loopback-only backend,
and a valid exact operator Origin. Add a private proxy-to-backend operator credential, supplied only after operator authentication. Caddy overwrites any incoming
credential header on that listener and removes it on the tablet listener. The backend verifies the credential independently of Origin. Never log it or expose it in
browser configuration. The tablet listener continues to reject upload/library/operator routes, even with forged Origin or proxy headers. Caddy supports replacing upstream
headers. This is a proposed application configuration, not today's deployed behavior. [Caddy
headers](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#headers).

An explicit local-development mode may instead trust direct loopback clients on a loopback-only listener. In that mode, disable proxy-header interpretation and refuse
forwarded-header requests. Do not share it with a generic public proxy. Require an explicitly configured matching operator Origin in local mode too. A missing Origin is
not a local-mode bypass. Direct hotspot/LAN backend access with the guard unset does not enable upload. If remote operator uploads are needed, add actual authenticated
operator access first. Origin is a browser request-origin check, not authentication.

Pin proxy trust to the actual upstream address, never `*`. Distinguish the transport peer from a forwarded effective client address, and do not use either as a
proxy-authentication substitute. Test missing/duplicate/null Origin, forged Origin, forged X-Forwarded-For, wrong credential, absent configuration and direct LAN access.
Test unauthenticated operator ingress, authenticated ingress, tablet ingress, and a proxy that makes every upstream peer loopback. The last case must still refuse
requests without operator authentication and the internal credential. Published render images retain the stated trusted-LAN read scope. R1 does not require tablet
pairing. Private media or a phone-upload invitation is separate work with scoped credentials.

### Normalize before publication

Accept one JPEG or PNG per streamed raw-body request. Do not accept arbitrary URLs or active document formats. Use an exclusive random staging file outside static mounts,
with hard byte/time/quota checks including missing Content-Length. Display names are bounded metadata, never paths, and the controller renders them as text. Propose
source admission of 32 MiB and 32 MP, one active decoder job and two queued jobs, with a 30-second processing timeout. These limits must be checked against representative
phone images, including 20/24 MP and rejected larger examples, before release. They are separate from tablet rendition budgets. Do not enable 64 MP merely because a
decoder can open it. Use a terminable subprocess with bounded memory, CPU, output dimensions and output byte counts. Set the measured worker memory budget before enabling
ingestion; start experiments at 512 MiB and record peak use and failures.

Validate actual format, dimensions, structure, full decode and non-animation. Apply all EXIF rotations/mirrors, convert supported color profiles to sRGB, and strip
EXIF/GPS/XMP/comments and other private metadata. Define alpha handling and opaque background consistently. Reject unsupported color conversion explicitly rather than
misreporting success. Hash final normalized bytes. An optional source digest is metadata only. Keep no originals by default and publish no metadata-bearing original URL.

Keep a normalized master within the current 12 MP/10 MiB served-image ceiling, with a provisional 4096-pixel long edge. Generate a 2048-pixel default display rendition, a
1024-pixel fallback, and a small thumbnail when useful. Every object has its own hash. R1's v2 descriptor references the selected display object's bytes and actual
dimensions. Do not serve a different rendition under the master's ID. The operator catalog can group those objects by master; backup closure includes the required
master/rendition relationships. Choose later renditions from the slice's physical pixel needs and measured device budget, not user-agent identity. Keep current/next
decoded content bounded. Compressed input size does not bound decoded or canvas memory.

Write and fsync complete object bytes, atomically publish within the owned filesystem, fsync the directory, then commit ready metadata. Only ready published roles can be
read or listed as usable. A failure before ready leaves no public partial object. A file-before-row failure leaves an orphan for reconciliation. Cleanup targets known job
files and unreferenced objects after a grace period. Automatic destructive GC waits for tested pins/reference closure. Quota includes staging, worker outputs and retained
objects. Propose 2 GiB plus a 512 MiB free-space reserve for initial image operation. Return actionable `413/415/422/429/507` outcomes and allow retry after cleanup.

Managed images use indexed lookup rather than rescanning/decoding the entire curated library. Preserve curated symlink, regular-file, changed-file and byte-identity
protections. Use server-owned immutable objects with opened-file identity checks. A hostile writer with server privileges is outside this store boundary. Add an explicit
integrity verification operation. Do not rehash an entire movie for every future range request. Keep media files under a configured directory resolved consistently with
the database, not an accidental working directory.

### Preserve the backup contract

Default backup scope remains referenced content, as approved in [OPERATIONS.md](../../../deploy/OPERATIONS.md). Show that unused uploads are outside this snapshot. A
future explicit full-library export can include all ready uploads. Do not silently redefine Backup as the entire library. Manifest 2 records scope, schema/pipeline
versions, metadata, object checksums, roles and reference closure. Use the captured database to select active/saved scene assets, playlist assets, rendition/master edges
and required display/calibration records. Existing recursive `asset` traversal already handles nested keys. New roots, relationships, formats and managed locations still
need implementation.

Prevent deletion for the capture/copy interval. Initially serialize destructive media operations against backup and defer GC. Use a cross-process store lock: backup holds
a shared lock before database capture through copy/verification; deletion/GC takes the exclusive lock. An in-memory app mutex cannot coordinate the separate backup CLI.
Mutable curated files still require changed-file detection during copying. In an exported referenced-scope database, mark omitted library entries
unavailable/not-in-backup. Never restore a ready row pointing to omitted bytes. Reference-aware deletion also protects active preparation objects and backup pins, not
just saved scenes. Restore only into new targets, verify before publication, and use matching updated tooling. Test manifest 1 restore, manifest 2 restore, corruption,
omitted unused uploads, failure during copy and a concurrent publication/deletion attempt. Then start an isolated restored app and actually fetch/show the selected image.
Video later needs the same real restore proof.

## Playback, readiness and the clock

### Define a session before adding timers

Use preparing, armed, playing, paused, rebuffering, stopped and failed states. Each authoritative action advances a runtime version. Progress/status samples do not. An
occurrence identifies playlist revision, item index and loop count. Repeated use of the same asset is still a different occurrence. A snapshot retains the active
presentation until a future effective time and includes at most one pending preparation/action. Receiving a higher future version must not immediately erase the current
still.

```text
Prepare(v, preparationId, occurrence, exact refs, cohort, deadline)
Ready(connectionId, sessionId, v, preparationId, evidenceSeq, lease)
Commit(v+1, preparedAtVersion=v, preparationId, effectiveServerMs, anchor)
Supersede/Cancel(newVersion) invalidates all different pending work
position(t) = anchorPositionMs + rate * (t - anchorServerMs)
```

A commit transfers only its explicitly referenced preparation into the new version. Every other supersession invalidates old readiness, timers, decodes, seeks and
callbacks. Retain the existing image-attempt token checks as part of this larger lineage. A stale decode may warm an object cache. It cannot paint or claim readiness for
another occurrence.

A ready lease names generation, clock epoch, session/version, preparation, occurrence, current connection and viewport/mapping version. It includes exact object,
layout/calibration/render-plan references, usable render state, visibility, clock freshness and media prerequisites. Propose a 2-second lease renewed every 500 ms while
preparation is active. Disconnect, replacement, hidden/sleep state, changed refs, stale clock, buffer loss or supersession invalidate it. The server rechecks current
ownership, expiry and evidence at commit. No readiness acknowledgement guarantees that a device cannot suspend immediately afterwards. After a committed action fails,
report the degraded interval and issue a new recovery action. Cancellation is not distributed rollback.

### Choose visible membership policies

Static image sharing has no synchronization barrier. For slideshow cuts, default to Online cohort with bounded hold. Freeze all placed online endpoints at preparation,
except explicit show exclusions. Retain a frozen endpoint that proves unsupported or unready. Show offline reservations, exclusions, hidden/unsupported endpoints and missing status before
Start and throughout playback. Do not silently filter to the fastest capable devices.

Prepare the next occurrence immediately after the current cut, using current/next content only. Commit early for the planned cut when leases are valid. If not ready by
planned time minus the lead, hold the current image for at most `min(dwell/2,5 seconds)`. Then commit a future cut for ready participants and record every missed
member/deadline. Late endpoints hold their last still and join the current occurrence when ready. They never independently advance to a future slide. Re-anchor after a
held cut so the following item receives its full dwell.

Offer Strict required slots for stills. It includes offline reservations and holds with Retry, Exclude, or Stop at timeout. Video defaults to that strict policy for start
and actual-stall recovery. Continue with available displays is an explicit partial-video choice with named exclusions and a new session version. Do not add quorum
variants initially. Reports retain planned cohort, observed cohort, misses, exclusions and completion rate. A smaller healthy subset cannot hide a slow device.

Pause effective at `Te` freezes `position(Te)`, not position at command receipt. Next, previous, seek, loop and source/quality replacement create new versions and future
actions. Playlist loop boundaries require committed occurrences. A held cut cannot coexist with a silently advancing modulo timeline. Reconnect sends welcome,
configuration, current playback snapshot and clock bootstrap; it does not replay an old command log. Late join prepares the current occurrence/position or an announced
next boundary. Restart restores static content normally and timed content paused/preparing in a fresh generation/session.

### Estimate offset with explicit validity

Use server monotonic milliseconds through an injected adapter, plus a clock epoch on all timed messages. Keep UTC for logs and durable metadata. On Linux, compare
BOOTTIME minus MONOTONIC to detect laptop suspend. The documented clocks differ in suspend accounting. [Python clock
constants](https://docs.python.org/3.13/library/time.html#time.CLOCK_BOOTTIME). On suspend or unsafe discontinuity, advance clock epoch, invalidate preparations and
pause/re-prepare with a fresh session. Client visibility/pageshow/online, late timers, sleep suspicion and reconnect expire clock confidence and trigger resampling. Test
actual tablet sleep behavior. Do not assume a browser clock advances through sleep from the HR-Time specification. [HR-Time](https://www.w3.org/TR/hr-time-3/).

```text
c0 = client timestamp before send; s1 = server receive timestamp
s2 = writer timestamp before send; c3 = client receive timestamp
offset = ((s1-c0) + (s2-c3)) / 2
rtt = (c3-c0) - (s2-s1)
serverNow = clientNow + offset
```

These are the four-timestamp relations used by NTP, adapted to application messages. [RFC 5905](https://www.rfc-editor.org/rfc/rfc5905.html#section-8). Begin with eight
startup samples and periodic refresh every 5 seconds. Keep only a bounded recent window and prefer its lowest-delay valid sample. Expire estimates after 15 seconds
initially. Reject inconsistent/negative-delay samples outside the timestamp error allowance. Initially require estimated uncertainty at most 25 ms for timed readiness.
Otherwise resample or report unready rather than silently meeting the optical target. Avoid rate fitting and offset slewing initially. A large offset change invalidates
pending work and re-arms it. Schedule timers by relative delay or explicit loop-clock conversion, then recheck the deadline at callback time. Wake before a cut, recheck
ownership/time in requestAnimationFrame, and swap only when the compensated target is due.

For one consistent sample with stable equal clock rates, causal nonnegative one-way delays and exact timestamps, true offset lies in `[s2-c3,s1-c0]`. Its midpoint error
is bounded by half that sample's RTT, even with asymmetric delay. Real use also requires bounded timestamp/queue error, rate error and age. Expand the interval for those
errors. Do not attach half the median RTT to an unrelated median/slewed offset and call it a proof. If those bounds are unknown, report estimated uncertainty and sample
age, not guaranteed future error. Clock uncertainty excludes timer, decoder, compositor, panel and scanout delay. It is not optical screen skew.

Keep network scheduling lead distinct from per-display `presentLeadMs`. Positive presentation lead dispatches earlier: `localDispatch = targetServerMs - offsetMs -
presentLeadMs`. For target 10000, offset 200 and presentation lead 30 ms, dispatch at local 9770 ms. Default presentation lead is zero. Tune only from relative optical
bias with uncertainty, tied to device/browser/mode/refresh configuration. For video apply compensation once to the phase target; do not apply it again to an already
compensated frame diagnostic. Use a provisional 1-second control lead, extending it when delivery/clock evidence cannot fit safely. Do not equate it with video buffer
duration.

## Operator and layout workflow

Keep the current light console, system typography and existing tokens in [controller.css](../../../frontend/controller/controller.css). Make the primary path Select/drop
image, Upload, Preview, Show on wall. Show upload progress, processing, ready, failed, command accepted and reported rendering as different states. Retain the current
scene/layout save separation and an immediate Stop/neutral-scene control. Use local assets and dependencies so the controller and tablet page work without WAN access.
In R1, legacy clients without render telemetry remain unknown after command acceptance. A socket send is not proof that the image appeared.

For setup, show the tablet URL and optional locally rendered QR code. Give each endpoint a human label and bounded Identify action with native-top orientation arrow. Use
an unplaced tray, central SVG wall preview, accessible device list and numeric selection inspector. Draw bodies, active panels, usable viewports, content crop,
reservations and hidden physical gaps distinctly. Selection must remain stable while presence/status updates arrive.

Ship select/drag, cardinal rotation, screen-space snapping, numeric positions, tap nudges, identify, save and recall first. Pointer capture, a movement threshold and
Escape cancel protect touch use. Use a local draft. One atomic batch Apply publishes the completed edit, with revision checks and undo/redo before apply. Group moves
operate on one draft transform and one batch request. Live calibration is a separately entered bounded preview mode, canceled by lease expiry/disconnect and saved only on
Apply. Add marquee/distribute/free-angle handles/model catalogs after the basic workflow is tested.

Keyboard users can select from the list, enter Move mode, nudge, rotate, apply with Enter and cancel with Escape. Provide visible focus, named native controls, persistent
labels, inline errors and restrained status announcements. Tap nudge/numeric/Move-to controls provide a single-pointer alternative to drag. Keyboard support alone is
insufficient. [W3C dragging guidance](https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html). Do not use color alone for offline/error/readiness. Respect
controller reduced motion and preserve zoom/page scrolling outside the manipulation area. Use large touch targets, provisionally 44 CSS pixels for frequent controls, then
inspect rendered results. On narrow viewports, show tray/inspector as selectable panels while preserving the same operations. Test long labels, all-offline/empty walls,
missing media, stale draft, denied activation and failed upload.

Implementation must run the actual route through render, inspect, critique, fix and verify on desktop and mobile. Use browser-harness and the configured browser tools for
relevant inspection, with real Playwright interaction for flows. Inspect console warnings/errors and failed network requests. Include keyboard and assistive-technology
smoke checks. This planning task did not create or visually validate a frontend.

## Prerecorded video and later live input

Start with native `video`, transformed/clipped through the same geometry, served by HTTP ranges. Probe actual H.264/MP4 configurations on the fleet. Provisional
candidates are 720p30 near 2 Mbit/s and a 480p fallback. Record profile/level, pixel format, bitrate, frame rate, duration, audio tracks, decode behavior and transformed
composition. Media Capabilities may inform selection, but an actual sample playback is the release gate. [Media Capabilities
draft](https://www.w3.org/TR/media-capabilities/). A small clipped slice still requires decoding the full rendition. Consider tile renditions only after measuring
quality/decode/bandwidth and layout-change encoding cost.

Use bounded local ffprobe/FFmpeg jobs with fixed arguments, no shell interpolation, no remote input protocols and no arbitrary URLs. Propose a 250 MiB/10-minute initial
file cap, with separate queue/disk budgets. Check the actual codec/container; accept or losslessly remux faststart when supported, and give actionable rejection for other
mismatches. Automatic broad transcoding is deferred. FFmpeg documents moving MP4 metadata to the front for progressive playback. [FFmpeg
MOV/MP4](https://ffmpeg.org/ffmpeg-all.html#mov_002c-mp4_002c-ismv).

Use the pinned framework FileResponse when its tested contract fits. It documents ranged responses. [Starlette responses](https://starlette.dev/responses/#fileresponse).
Verify `GET/HEAD`, `200/206`, suffix/open ranges, `Content-Range/Length`, `Accept-Ranges`, validators and `If-Range` through the real proxy. Return `416` for
unsatisfiable ranges. Use a bounded range count/header size for multirange handling. Do not confuse server read blocks or HTTP transfer chunks with media segments.

Expose Start countdown, Observed buffer goal, Preparation timeout, and Recovery policy separately. Propose 5 seconds of contiguous coverage ahead, 30 seconds preparation
timeout, and a 1-second start lead, tuned from the probe. Near the end require only remaining duration. `preload` is a hint, buffered data may be discarded, and
`canplaythrough` is not a guarantee. [HTML media](https://html.spec.whatwg.org/multipage/media.html#media-elements). Require metadata, bounded seek completion, usable
frame/media evidence, buffer coverage and successful local playback permission. If the browser will not reach the goal, show Blocked/unsupported buffer goal and offer a
lower tested goal/profile.

Muted inline playback is the default. Test the play result on each actual page and provide a local Enable display action if needed. Controller interaction does not
activate a remote tablet. WebKit and Chrome document muted-play policies, but exact old builds and power settings still require trials. [WebKit
policy](https://webkit.org/blog/6784/new-video-policies-for-ios/), [Chrome policy](https://developer.chrome.com/blog/autoplay/). Any future audio uses one locally
activated output with measured offset. Multi-tablet speakers are deferred. Keep captions readable in a designated region rather than splitting essential text across
bezels.

Use `requestVideoFrameCallback` where available for software diagnostics, otherwise currentTime/events with lower confidence. It is best effort and can be late. It does
not observe photons. [Frame callback draft](https://wicg.github.io/video-rvfc/). Define drift as observed media time minus the authoritative compensated target at the
same diagnostic instant. Positive drift slows playback; negative drift speeds it up. Try a 50 ms drift deadband, bounded 0.98 to 1.02 rate correction, then a local seek
for persistent error above 250 ms. Those values and correction stability require device evidence. Avoid rapid repeated seeks. Actual stall under strict mode schedules
group pause/rebuffer and a new common anchor, with the already degraded interval recorded. Bound local recovery attempts; repeated failure offers lower common quality,
Stop, or named exclusion/poster fallback. A poster is an excluded video member, not a synchronized video participant.

Do not use native autonomous loop as the wall contract. Prepare the next loop occurrence and schedule its boundary. Initially allow an explicit hold/seek/re-prepare gap.
Source/quality switches cancel old events and create new versions. Seamless dual-decoder loops are deferred. Full download is an optional small-file experiment before
becoming an operator option. A Blob may consume RAM or backing storage plus copies/decoder memory. It removes network fetch during playback, not every stall cause.
Measure peak resources, storage eviction, object-URL cleanup and replay on actual tablets before enabling a tested cap.

Unicast load is roughly device count times bitrate. Twenty consumers at 2 Mbit/s request 40 Mbit/s before overhead. That is demand arithmetic, not hotspot throughput
evidence. Stagger preparation and measure actual AP/radio behavior. HLS can add deliberate segment duration, packaging and quality ladders, but does not solve a weak
decoder or synchronize displays automatically. Apple documents HLS for live and on-demand delivery. Exact native/library support stays a fleet probe. [Apple
HLS](https://developer.apple.com/streaming/).

Live input has capture time, encoder time, a moving edge and explicit source-to-glass delay. Choose source and acceptable delay before comparing intentionally delayed HLS
with interactive WebRTC. An HLS program-date-time value needs a documented encoder-epoch to server-clock mapping and discontinuity policy. Do not treat wall-clock dates
as server monotonic timestamps. Browser screen capture requires producer permission/activation and an immediate Stop action. Prove the actual producer path. [Screen
Capture draft](https://www.w3.org/TR/screen-capture/). Use a supported secure producer origin, a current local gesture/chooser, source-ended handling and no assumed
persistent unattended capture grant. Unspecified capture chunks are not an implementation-ready ingest design. Do not assume native Chrome HLS, old iOS preload,
WebCodecs, MSE or WAAPI behavior without the relevant probe.

## Independent browser and physical-device evidence

The proposed runner executes the real `/client/` scripts against its own one-worker TCP server. Use a fresh temporary database, curated directory, managed media directory
and unused loopback port. Reject paths outside the temporary root and the live wall's endpoint. Never attach the fleet to the current operator wall. Use the real
controller for representative upload, selection, layout and playback flows. Test a direct backend and an isolated two-origin ingress configuration. Pin
Playwright/library/browser builds. Missing tooling becomes an explicit prerequisite, not an automatic install in this planning task.

Each virtual tablet gets one independent context/profile, its own storage, UUID, page session and socket. Run a same-origin fleet to prove independence rather than
relying on per-client proxy ports. Reload preserves identity within a context. New contexts get distinct identities. Use separate processes with separate persistent
profiles for a subset; never reuse one saved storage state across the fleet. Separate windows do not isolate storage. Ports separate localStorage origins but not all
cookies. [Playwright isolation](https://playwright.dev/docs/browser-contexts), [RFC 6265](https://www.rfc-editor.org/rfc/rfc6265.html#section-8.5). Keep the negative
same-context two-page collision test and assert no reconnect storm after `4409`. Assert N distinct identities and N simultaneously live sockets over an observation
window, not just N windows.

Start with two clients, then grow routine software coverage to 18 heterogeneous fixture endpoints. Vary CSS dimensions, fractional DPR, physical panel size independently
of viewport, asymmetric bezels, mount/OS rotation, offsets and reservations. Include identical CSS sizes with different physical dimensions and a 180-degree
orientation-only change. Use coded calibration pixels at edges/interior, an independent coordinate oracle, rendition selection and empty/loading/error states. Green
readiness is separate from verified pixel output.

| Impairment layer | Evidence it can establish |
| --- | --- |
| Real TCP proxy | Actual byte-stream delay, rate limits, stalls, blackholes and resets for control/media. Not IP packet loss or RF contention. |
| Server-connected WS relay | Application-frame drops, duplicates, stale injection and rejection logic. Not ordinary reordered TCP delivery. |
| HTTP routing/media proxy | Request failures and body stalls. Delayed whole-response fulfillment alone is not progressive buffering. |
| Application clock adapter | Known offset/rate/jumps for deterministic estimator logic. Native decoder/document clocks remain unchanged. |
| Loader/CPU/lifecycle probes | Synthetic decode delay or engine-specific throttling/freeze. Not an old-tablet hardware emulator. |
| Real device trial | Actual browser activation, sleep, decoder, memory, thermal, panel and radio behavior for that exact device. |

Keep an unmodified-clock integration run. Cross-context/process software timing needs an independently calibrated clock mapping and uncertainty. `timeOrigin +
performance.now()` is not unconditional shared-host truth. [HR-Time clock scope](https://www.w3.org/TR/hr-time-3/#time-origin). Probe codecs in each installed engine.
Alternate WebM fixtures test algorithms only; retain an actual production MP4 run. Desktop Playwright WebKit is not iOS Safari, and codecs vary by browser/host.
[Playwright browser limits](https://playwright.dev/docs/browsers#media-codecs). Independent WebSockets do not create independent radios. Separate processes still share
scheduler, GPU, host clock and NIC. Physical tablets share the AP/channel too. Report both the independent endpoints and shared bottlenecks.

Record seed, app/build versions, contexts/processes, IDs/connections, viewports, impairment layer, events, screenshots, console/network and cleanup. Always close test
browsers, contexts, server, proxy, tasks and temporary data in finally paths. No sudo or host network mutation belongs in the runner. Use available physical tablets
early, inventory exact models manually, and record absent old/new iPad/Android categories. Missing hardware blocks claims for those categories, not every implementation
ticket.

## Provisional gates and measurement

Use these gates for an explicitly named foreground powered cohort on its intended LAN. Record failures before changing a target. Preserve original targets and results if
a later product choice revises them.

| Quantity | Initial gate | Stretch goal / method |
| --- | --- | --- |
| Physical seam continuity | At most 2 mm displacement beyond the intended hidden gap. | 1 mm. Ruler/vernier photo at every neighboring edge, with measurement uncertainty. |
| Still cuts | At least 100 cuts; optical wall-wide p95 skew at most 100 ms and max at most 250 ms. | p95 50 ms after measured presentation leads. |
| Video steady state | Ten-minute run; p95 at most 100 ms and max at most 250 ms outside declared startup/recovery windows. | p95 50 ms. Burned-in source frame/time across all screens simultaneously. |
| Clean video run | No unplanned stalls. Report full-run skew and every recovery window too. | Scale fleet only after the mixed pair passes. |
| Recovery after connectivity returns | Correct content within 10 seconds over at least 20 trials. | 5 seconds, recording network restoration separately. |
| Video after completed rebuffer | Converge within 5 seconds or enter an explicit failure state. | Record time from recovery request and total degraded duration as well. |
| Stale work | Zero superseded command effects or stale decode paints. | Deterministic cancellation/replacement tests. |

For cuts measure maximum minus minimum visible onset per event, not pooled pairwise averages. Include original cohort completion/miss counts. A missing transition is a
failed event, not a zero or silently omitted sample. Report healthy-subset diagnostics separately while retaining whole-show failures. For video retain continuous
evidence for a full-run optical claim. Otherwise label sampled windows and all unobserved intervals. Report full-run values, steady-state values, recovery count/duration
and frames with missing participants. Do not remove most of a run as recovery to obtain a pass.

Use numbered flashes and a numbered moving-seam test video. Capture all screens together, preferably at 240 fps or better, with capture timestamps, exposure and region
rows recorded. At 240 fps the sample interval is about 4.17 ms. It is not the complete accuracy. Measure a same-panel noise floor, account for rolling shutter and panel
scanout, and retain detection uncertainty. Raw captures stay outside source control. Keep analysis/settings and sanitized summary evidence reproducible. Photodiodes are a
later option when camera uncertainty limits decisions. Sequential screenshots, RTT, callback times and currentTime agreement cannot establish optical synchronization.
Measure capture-to-glass latency separately if live input is later implemented.

## Phased delivery and acceptance gates

### P0. Bounded baseline and early experiments

Run prepared regression checks in isolation, establish the browser pair and reproduce duplicate identity. Measure actual canvas rectangles in available
tab/fullscreen/standalone modes and record sleep-clock behavior. Probe a short native transformed MP4 on available devices for decode, preload, activation, seek,
clipping, rotation and loop gap. Gate: reproducible software baseline and explicit passed/missing hardware rows. No new physical/media claim. This evidence work proceeds
beside R1. A comprehensive fleet harness is not a prerequisite for the upload backend.

### R1. Upload and show on the current logical wall

Deliver ownership/takeover, bounded registration, schema 1, explicit admission, managed normalization/index, progress/error UI and referenced backup/restore. Keep v2
still descriptors and current logical placements. No clock, geometry editor or crossfade dependency. Gate: phone-image/malicious-input matrix, no public metadata, ingress
refusals, crash-consistent publication and restored bytes shown by real clients. A rendered controller flow and isolated client pair verify software behavior. Physical
upright-photo evidence is recorded when a tablet is available. Release scope must say whether that physical check is still missing.

### R2. Physical numeric calibration and the minimum drag editor

Deliver schema 2/v3, immutable measurements, canonical panel plans, viewport mapping, conversion, batch edits and accessible draft editing. Gate: old/new compatibility
matrix, independent transform/pixel fixtures, stale-viewport rejection, keyboard/tap/pointer flows and saved-state separation. Validate at least two different physical
models against the seam gate before claiming a calibrated mixed wall. Do not call tab-mode accuracy proven from fullscreen results.

### R3. Clock, leased preparation and hard-cut playlists

Deliver ordered senders, status, session/version ownership, clock/suspend rules, visible cohort policies and committed cut occurrences. Gate: deterministic
stale/lease/queue/restart tests, labelled impairment runs and at least 100 optical cuts on the available mixed cohort. Timed physical release also requires the relevant
existing ingress/kiosk/tablet gates. Missing hardware keeps that claim open. Crossfade is optional later, after current/next memory use and optical benefit are measured.
It does not block cuts.

### R4. Native prerecorded video

Use the P0 profile decision, add bounded ingest/ranges, native geometry, observed buffering, activation, correction and authoritative loop/recovery. Gate: production MP4
through actual ingress, strict and partial policy tests, restored large media, and the clean ten-minute optical run. A failed mixed-pair trial first reduces
profile/quality or scope. HLS is not an assumed fix. Enable full download only after its separate resource experiment passes.

### R5. Field readiness for the implemented scope

Complete local-CA trust, origin migration/rebinding, WAN-disconnected restart, quota/storage diagnostics, recovery and backup drills. Test wake-lock release/reacquisition
where supported. It needs secure-context support and does not replace OS kiosk/power setup. [Wake Lock draft](https://www.w3.org/TR/screen-wake-lock/). Gate: exact
device/build matrix, intended physical client count, two-hour media soak and overnight still soak if unattended operation is required. Respect the existing README 3a/3b
physical prerequisites before declaring 3c/3d or unattended operation complete. This roadmap changes feature order; it does not mark those deployment gates passed.

### R6. Conditional segmented delivery or live capture

Start only from a written source/delay requirement or demonstrated file-delivery limitation. Compare one selected HLS packaging/player path or WebRTC experiment against
native-file results, including encoder cost and capture-to-glass delay. Gate: exact producer/receiver matrix, timestamp/discontinuity mapping, chosen delay/skew criteria
and a working Stop/recovery flow. Keep all runtime dependencies local. Public internet access and AI features are outside this roadmap.

## First ten implementation tickets

Each ticket names its owner by responsibility. No app implementation is part of this planning deliverable. Split a ticket further if its diff cannot retain one
independently testable outcome.

### T1. Establish the isolated browser pair and rectangle experiment

- Own proposed `simulator/browser/` and scoped simulator documentation/test configuration.
- Depends on no feature ticket. Pin tooling in the implementation task.
- Run actual client JS with temporary DB/media/port; verify two IDs/two sockets, reload preservation and same-context collision.
- Capture current still pixels, rectangles, console/network and cleanup. Add process/profile subset coverage before timed tests.
- Attach hardware inventory/MP4/sleep experiment results or explicit missing rows. No production-wall writes.

### T2. Stop ownership contention and bound endpoint registration

- Own `client.js::openSocket/attemptCycle`, registration models and process-local liveness bookkeeping.
- Depends on T1's collision reproduction. Do not wait for a full fleet.
- Respect current-socket `4409` with explicit Take over; preserve ordinary reconnect and `4404` registration recovery.
- Validate dimensions/capability lengths and use monotonic expiry with UTC display timestamps.
- Gate: duplicate tabs stop retrying, isolated clients stay online, replacement cleanup and v1/v2 fixtures pass.

### T3. Add schema 1, owned object metadata and fail-closed admission

- Own `persist.py`, proposed media index and upload admission, Caddy operator configuration and security tests.
- Depends on baseline regression evidence, not a clock or physical editor.
- Add startup version checks, pre-migration backup and separate media directory; keep existing documents unchanged.
- Implement authenticated-ingress credential or explicit direct-loopback mode with forwarding rules.
- Gate: old DB survives migration, future/corrupt DB refuses safely, and direct/forged/unauthenticated uploads are denied.

### T4. Normalize uploaded stills and show them through the current contract

- Own proposed media worker, managed image read/index integration and controller upload panel.
- Depends on T2 and T3.
- Stream, validate, strip metadata, publish immutable exact-byte objects and return a v2-compatible display-object descriptor.
- Cover phone images, EXIF mirrors, alpha, malformed files, worker timeout, queue/quota failures and duplicate normalization.
- Gate: rendered upload-preview-show/error-retry flows work on the existing logical wall with no new geometry or timing requirement.

### T5. Make uploaded images recoverable and close R1

- Own backup manifest 2, reference/pin coordination and ingest/crash/restore tests.
- Depends on T3 and T4.
- Preserve referenced scope, mark omitted library rows unavailable and protect copied object closure.
- Restore old/new fixtures into new targets, then start the isolated app and fetch/show the restored image.
- Gate: publication/disk/copy failures never announce missing bytes as ready, and R1 admission/render checks have actual evidence.

### T6. Introduce the one v3 contract and safe socket writer

- Own protocol/state projection, hub writers, HTTP preconditions/idempotency, schema 2 envelopes and migration fixtures.
- Depends on T2, T3 and the R1 compatibility baseline from T5.
- Implement the complete cached-device/controller/HTTP/snapshot/downgrade matrix and bounded update diagnostics.
- Gate: welcome first, immutable snapshots, slow TCP reader isolation, causal coalescing, old-writer cleanup and every legacy mutation fence.
- Keep physical/timed behavior unavailable until its owning capability lands.

### T7. Implement physical panel plans and numeric calibration

- Own proposed displays/geometry modules, client view mapping, conversion and independent geometry fixtures.
- Depends on T6 and T1's rectangle evidence. Change sizing only if evidence requires it.
- Add native-edge bezels, fixed bounds, mount/OS rotation, live mapping version and normalized rendition coordinates.
- Gate: all cardinal rotations including 180-degree-only changes, asymmetric bezels, offsets, fractional DPR and stale plans pass pixel/oracle checks.
- Record mixed-tablet ruler/seam evidence where available; do not substitute emulation for missing hardware.

### T8. Ship the small accessible layout editor

- Own proposed controller editor and scoped HTML/CSS integration.
- Depends on T7; T4 supplies media preview.
- Add tray, stable selection, draft drag/snap/cardinal rotation, group batch move, numeric/tap/keyboard alternatives, Identify and save/recall.
- Gate: cancel writes nothing, Apply is atomic, conflicts preserve the draft, and scene/layout recall remain independent.
- Render and exercise desktop/mobile, touch, keyboard, zoom, long labels and failure states before closing R2.

### T9. Add session ownership, clock confidence and preparation leases

- Own proposed clock/playback core, client time adapter, readiness/status validation and operator diagnostics.
- Depends on T6 and T7. Physical timing uses valid calibration; logical timed mode remains explicitly logical.
- Implement generation/clock epoch/session/version/preparation lineage, suspend expiry, frozen membership and future-effective snapshots.
- Gate: model tests reject every stale lease/callback; real TCP faults and injected clock errors are labelled; no old monotonic anchor survives restart.
- Produce a numbered scheduled-cut experiment with software and optical results separated.

### T10. Ship hard-cut still playlists and the optical acceptance procedure

- Own playlist saved-scene payload, current/next preparation, controller controls, optical tooling and browser scenarios.
- Depends on T4, T5, T8 and T9.
- Implement early commit, bounded online-cohort hold, optional strict slots, explicit misses, full-dwell re-anchoring and loop occurrences.
- Gate: at least 100 cuts, late joins, pause/next/previous/cancel/restart tests, restore closure and honest whole-cohort metrics.
- Close R3 software scope when verified. Physical timing acceptance stays open until the optical cohort and ingress/kiosk gates pass.

After T10, implement R4 as separate ingest/range, native player, recovery and hardware-validation changes. P0 video probing remains early so these later changes follow
evidence rather than a speculative generalized player.

## Defaults, remaining choices and deferrals

Use the operator laptop for upload, trusted-LAN reads for published render assets, physical hidden gaps, cuts and muted video. Restore timed media paused/preparing.
Choose online/bounded stills and strict video visibly per show. Use referenced backups unless the operator explicitly chooses a later full-library export. Keep manual
identity recovery/rebinding before cookies or a hardware identity scheme.

The operator still needs to supply exact tablet inventory, intended fleet count, available camera/capture hardware and desired live source. Useful product feedback can
change backup scope, strictness, audio need, acceptable moving-seam skew and live delay. The defaults above permit implementation without pretending those preferences are
measured facts. An old unsupported browser may remain a still/poster endpoint. Make that exclusion visible.

Defer crossfades, identity cookies, full model catalogs, automatic camera calibration, arbitrary seam warps, per-panel color matching and tile video generation. Revisit
them only after the simpler workflow exposes a concrete need. Also defer cloud access, multicast, DRM, synchronized multi-speaker audio, multiple app workers,
WebCodecs/custom MSE and service-worker offline playback. The largest remaining risks are real decoder limits, browser suspension, memory, Wi-Fi airtime, calibration mode
changes and display delay. No amount of extra buffer repairs sustained inadequate decode throughput or a suspended page.

## Evidence and verification record

The archived [Opus proposal](opus-proposal.md), [Sol proposal](sol-proposal.md), [Opus review](opus-review-sol.md), and [Sol review](sol-review-opus.md) remain unchanged.
All four and the parent evidence were read in full for this synthesis. Both Opus activity timelines were paged, and selected truncated evidence was recovered as recorded
in [transcript notes](OPUS_TRANSCRIPT_NOTES.md). Primary links above were checked on 2026-10-23. W3C/WICG drafts describe work in progress and do not prove implementation
on this fleet. The Starlette legacy docs host failed once; its current official host was retrieved. FFmpeg formats retrieval timed out; official ffmpeg-all documentation
was retrieved instead. Artifact checks cover document existence/length, Markdown fences, local links, existing/proposed repo paths and protected-file hashes. They are
documentation checks. No app, browser, optical, network, codec or performance result was produced by this final-author pass.
