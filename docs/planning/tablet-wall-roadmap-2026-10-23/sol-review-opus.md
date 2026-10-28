# Sol reciprocal review of the Opus roadmap

Prepared 2026-10-23 for the final Cursor Opus author. This is review round 2, against checkout `65a4d50`. My recommendation is to retain Opus's server-computed transforms, managed media store, native MP4 first approach, and optical measurement procedure. Change the compatibility contract, playback ownership rules, and release sequence before implementation.

`O` refers to `/tmp/tablet-wall-roadmap-20261023-opus.md`, 1671 lines. `S` refers to my `/tmp/tablet-wall-roadmap-20261023-sol.md`, 467 lines. Line references below refer to those unmodified proposals. Source paths are relative to `/var/home/oak/Codes/projects/tablet-wall-ai`.

I read both proposals, the parent evidence, the baseline JSON summary, and relevant source and tests. I ran no app tests, servers, browser sessions, network changes, installs, or delegates. Python clock introspection was read-only. Public primary documents were fetched without a browser. The parent's 23 scenarios and 1075 checks establish the existing in-process protocol/geometry baseline, not rendered output, media performance, or optical synchronization. One online roster endpoint and one associated station do not establish a correlated hardware identity or mixed-tablet result.

Throughput checkpoint: n/a, read-only investigation.

## Blocking design issues

### 1. Use v3 for new physical and timed semantics, while preserving useful additive v2 extensions

Evidence. O §1 L51 and §11.1 L596-598 retain v2. O §9.8 L460 approximates physical layouts for old renderers, and §11.4 L670-701 changes scene/image descriptors. S L162-184 chooses v3, but S L433 overstates the case by requiring v3 for every new media descriptor. `PROTOCOL.md:257-299` defines integer abstract footprints and centered per-device cover. `main.py:363-410` validates exact saved-layout/content keys. `client.js:780-819` expects `asset`, `url`, and `fit: cover`; `client.js:1377-1408` applies legacy cover. The controller has no capability handshake beyond its major version.

Failure. An axis-aligned rounded body rectangle cannot represent a rotated calibrated viewport. A cached v2 client can show a plausible but incorrect crop. A cached controller can overwrite physical state through old placement or scene routes. Adding fields to saved JSON can make recall fail even if a socket peer ignores them. Conversely, requiring v3 for an ordinary uploaded still would delay a feature that can use the existing image contract.

Minimum correction. Adopt this explicit contract:

- v1 remains color-only. v2 remains the documented logical wall and still-image renderer. Preserve old curated IDs and existing fields, units, fit, and recall semantics.
- An uploaded normalized still may use an ordinary v2 image descriptor if its ID names those exact normalized bytes and all existing required fields and same-origin reads remain valid. Optional status or clock diagnostics are independently additive when negotiated. They do not authorize physical or timed membership.
- v3 carries explicitly versioned physical render plans and playback snapshots. Required members must advertise the relevant v3 capabilities. An unsupported endpoint is visibly excluded or blocks preparation. Never invent an approximate physical v2 placement. A deliberately excluded legacy endpoint may receive its existing color/unplaced fallback.
- Version the new physical/playback HTTP commands and reads. Existing logical routes keep their old shape while a logical static wall is active. While new state is active, reject legacy mutations that would alter it, including old recall/auto/delete paths, with `409 Upgrade controller` before mutation. Require preconditions on new writes. Use `412` for failed `If-Match`, `428` when a required header is missing, and `409` for semantic conflicts.
- A new client may fall back from an old server's `4426` to v2 logical stills only. Never retain v3 feature assumptions after fallback. Old already-running pages need an explicit refresh/upgrade path; they cannot execute a newly added auto-reload handler.
- Version SQLite schema and stored documents independently of socket majors. Validate active startup state before `_restore_wall_state` rewrites it at `main.py:118-122`. Preserve legacy snapshots, make physical conversion create a new layout, and reject unknown future schemas without writes. Update exact `== 2` paths in `hub.py:103-117` and `main.py:1395-1405,1451-1454`.

Preference. Choose v3 for the changed contracts, not for every optional frame. Require a compatibility matrix with cached v1/v2 tablets, cached controller, new client/old server, old database, old backup, and logical-to-physical conversion. I revise S's blanket descriptor requirement.

### 2. Keep the server authoritative for committed transforms, and correct the coordinate chain before coding it

Evidence. O §9.3 L388-403 gives server-computed matrices and a JavaScript draft preview. S L128-136 specifies composition but leaves execution ownership too open. O L358 and L499 define an active-center offset, while O L394 describes `o_active` as a corner and still subtracts half the active size. O L400 and L689-692 apply an original-image transform to a selected smaller rendition without specifying rendition-to-source scaling. Current behavior is explicit at `client.js:1377-1408`; the independent oracle is `simulator/geometry.py:17-19,41-104`.

Failure. Using the corner interpretation of `o_active` subtracts half a panel twice. Drawing a 2048-pixel rendition under a transform defined for 6000 source pixels gives the wrong size unless its coordinates are converted. Separate preview, tablet, and simulator compositions can agree on their own assumptions while disagreeing on the wall.

Minimum correction. The server's proposed `geometry.py` owns committed geometry and publishes a render-plan ID, matrices, clipping information, and the exact input revisions/signature. Tablets apply that plan. A small JavaScript implementation may compose draft previews locally, but it is explicitly a second implementation tested against fixed hand-derived fixtures and server results. Keep the simulator's geometric oracle independent. A fixture generator using the production geometry cannot be the only expected-result authority.

Define body coordinates about its center, active size `A`, and active-center offset `o`. The active top-left in body coordinates is `o - A/2`. For example, body 120 by 90 mm, active area 100 by 60 mm, and offset `[3,-2]` produce `[-47,-32]`. Verify that result and its four cardinal rotations. State matrix order, clockwise sign in a Y-down space, corner translation for viewport rotation, and inverse behavior. Each rendition needs an explicit rendition-to-source conversion, or its own server-computed rendition-to-content matrix. CSS video uses CSS coordinates; canvas adds the chosen backing scale once.

Physical body, lit panel, usable browser viewport, mounting rotation, and OS/browser orientation remain separate records. Rotate asymmetric bezels with the body. Keep fixed content bounds and global cover/contain separate from those records. Presence, exclusion, or rebinding must not silently resize bounds, despite O L422's default based on bound slots. Restrict compact/duplicated seams to validated regular groups initially. They alter sampling, never measured bezel widths.

A viewport report needs a sequence/signature. A plan for the old viewport must be rejected immediately after a resize, even before the server responds. Registration currently does not advance wall revision, and `client.js:1581-1587` ignores same-revision frames, so a corrected matrix needs an explicit render-plan revision or equivalent v3 ordering. Revalidate CSS-to-panel calibration after mode/viewport changes. A backing-only scale change can reuse physical geometry after verification; DPR alone never establishes PPI. Reusing calibration on a replacement of the same model, as O L241 suggests, still requires a matching browser configuration and fresh validation.

Preference. Adopt Opus's server authority and revise S's tablet geometry module accordingly. Require corner/pixel tests, asymmetric bezel fixtures, negative offsets, rotation, stale-viewport rejection, and an independently measured ruler trial. Preserve high precision internally and round only displayed millimetres.

### 3. Separate selected durable content from versioned runtime playback, and define readiness as temporary evidence

Evidence. O §10 L562-590 puts a session inside persisted scene content and uses wall revision for control. O §11.6 L731-750 matches status by generation/revision/session but omits preparation and connection ownership. O §12.2 L804 counts only bound, online, capable devices and starts after timeout. O §14 L897-905 advances an autonomous timeline and skips failed items per tablet. S L108-118,172-184,222-228 is stronger, but does not fully specify how holding a cut interacts with its anchored playlist timeline. Existing load ownership at `client.js:1054-1082` and socket ownership at `main.py:1342-1345,1375-1418` must be extended.

Failure. Old readiness can authorize a replacement connection. The same asset appearing twice can be confused with the earlier occurrence. An offline reservation disappears from the default barrier. A late callback can repaint after cancellation. A continuously advancing modulo timeline cannot also hold the current slide for the group without a new anchor. A persisted monotonic anchor has no meaning after restart.

Minimum correction. Keep durable selected scene/playlist/settings in SQLite. Keep a process-local `PlaybackSession` with generation, clock epoch, session ID, version, active timeline, and at most one pending preparation. Commit durable configuration before publishing its runtime consequence. Playback-only changes advance session version without a SQLite write for every progress event or slide boundary. Restore timed content paused/preparing after restart by default. Static images still restore normally.

Specify this state contract before handlers:

1. Prepare freezes the item occurrence, asset/rendition references, geometry/calibration revisions, required slot IDs, and preparation ID. It does not replace the currently visible presentation.
2. Ready names that preparation, its originating version, the current connection ID, and current prerequisite evidence. It has a short lease and sample age. Replaced sockets, disconnect, hidden state, viewport changes, canceled preparations, expired clocks, and insufficient buffers invalidate it.
3. Commit advances the session version, references the preparation, and supplies a future effective time. Retain the active state plus that committed future action in a complete snapshot. A client that missed prepare must load/join or report late; it cannot pretend it was ready.
4. Cancel/supersede invalidates callbacks and timers by generation, clock epoch, session, version, preparation, and connection lineage as applicable. Before commit, hold/retry is safe. After commit, some devices can already have acted. Issue a new authoritative recovery action and report the degraded interval; cancellation is not a distributed rollback.
5. Default required membership includes placed required slots even when offline or unsupported. Freeze membership for a preparation. An operator exclusion is a new version. Timeout leaves an actionable waiting/error state under Keep wall together. Continue with available displays is a separately labelled policy. O's current `all` is actually a deadline policy.
6. For initial still playlists, commit each next occurrence after readiness. If its intended cut is missed, extend the dwell and publish the revised anchor before any later transition is assumed. Do not let a modulo formula advance behind a hold screen. Pause/seek/next/previous and loop occurrences all have explicit future effects. A pause effective at `Te` freezes `position(Te)`, not the earlier command-receipt position.

Preference. Use the stronger S ownership model with these additions. Keep only current/next images initially. Crossfade, multi-item lookahead, and automatic per-device progression are later options. This corrects my own incomplete hold-versus-timeline description as well as O's weaker readiness rules.

### 4. Specify suspend behavior, clock confidence, and latency-compensation sign

Evidence. O §11.6 L751 leaves Linux suspend semantics unverified; §12 L790 calls half median delay uncertainty, and L814 subtracts latency trim. S L218-220 correctly treats RTT as evidence but omits a complete laptop-suspend policy and trim convention. `state.py:73-86` currently expires liveness using UTC. Read-only introspection of `.venv/bin/python`, Python 3.13.13, reports `clock_gettime(CLOCK_MONOTONIC)`. Linux documents that this clock stops in suspend, while BOOTTIME includes suspend. [Kernel timekeeping](https://docs.kernel.org/core-api/timekeeping.html), [Python 3.13 clock constants](https://docs.python.org/3.13/library/time.html#time.CLOCK_BOOTTIME), retrieved 2026-10-23.

Failure. Tablets can continue their clocks while the laptop's timeline stops, then act on stale anchors after resume. A timer scheduled in the wrong clock domain fires incorrectly. A calibration with an undefined sign makes a slow panel later. A low historical RTT does not guarantee a fresh clock estimate after drift, sleep, or estimator slewing.

Minimum correction. Use one injected server clock adapter in generation-scoped monotonic milliseconds for anchors, timestamps, and liveness intervals. Keep UTC for logs and durable metadata. Schedule event-loop timers through an explicit conversion to relative delay or loop-clock time, then recheck deadlines when callbacks run. Do not pass arbitrary server milliseconds directly to `loop.call_at`.

On this Linux host, monitor BOOTTIME-minus-MONOTONIC to detect suspend rather than treating every wall-clock change as sleep. On suspend/resume or an unsafe discontinuity, invalidate preparations and clock confidence, create a new runtime session/clock epoch, and re-prepare. Tablet resume also requires resampling and rechecking readiness. Do not resume optical-sync claims automatically. Behavior on actual tablet sleep remains a device experiment. HR-Time gives monotonic timing within its supported execution scope; it does not create a shared clock across isolated browser executions. [HR-Time](https://www.w3.org/TR/hr-time-3/#dfn-monotonic-clock), working draft, retrieved 2026-10-23.

Define offset as server minus client. Define positive `latencyAdvanceMs` as dispatch earlier. Then `localDispatch = targetServerMs - offsetMs - latencyAdvanceMs`. With offset 200 ms and advance 30 ms, target 10000 ms dispatches at local 9770 ms. Optical relative bias can tune relative alignment; it is not an independent measurement of absolute display-pipeline delay. Keep this value separate from network lead and clock offset. Video diagnostics using expected display time must not apply the compensation twice.

Track RTT, sample age, variation, raw versus applied offset, and drift allowance. Half RTT is an estimate component, not a guaranteed future error bound. Defer rate-skew fitting initially, as Opus proposes, but test known injected rate errors and expire old confidence. This is a concession to O's smaller estimator and a revision to S's missing suspend/trim detail.

### 5. Make bounded sending an actual ordering contract, not only a queue refactor

Evidence. O §11.7 L755-761 has three priority lanes, latest-wall coalescing, and a 5-second timeout, but no queue bounds or cross-lane causal rules. S L53 and L176 asks for bounded ordered sending without choosing those details. `hub.py:101-117` captures the controller snapshot before awaits but projects device frames later from live state. `main.py:1379-1400` installs a replacement socket before awaiting closure of the old socket and sending welcome. This exposes an ordering risk that a new sender must address, not a verified runtime failure in this review.

Failure. Prioritized clock replies or concurrent broadcasts can precede welcome. A coalesced commit can lose its prepare prerequisite. An unbounded control lane still leaks memory. A frame projected later can describe a different accepted revision than the controller saw. An old writer's cleanup can close the replacement connection.

Minimum correction. One writer owns each connection. Reserve welcome and its initial snapshot before allowing ordinary delivery. Capture immutable per-version values at command acceptance. Bound message count and serialized bytes in every lane. Coalesce clock/status traffic deliberately and retain the newest complete playback snapshot, including its active and pending/committed future state. If using discrete prepare/commit messages, preserve their causal order or supply the equivalent full snapshot. Never rely on a dropped prepare having happened. Disconnect on sustained overflow/send timeout and require snapshot recovery. All cleanup checks current connection ownership.

Preference. Keep O's outbox direction, with explicit bounds and causal tests. Test actual TCP slow readers in addition to TestClient because in-process unbounded streams cannot establish real backpressure. Add races for replacement plus broadcast, welcome-first, superseded preparation, full queue, and cleanup of the old writer. Clock stamping at writer send scheduling is useful, but cannot bypass protocol initialization.

### 6. Close the original-file privacy gap and make upload/recovery one shippable feature

Evidence. O L469 uses original-byte hash as uploaded asset ID; L480 retains the original object; L877 serves objects by hash; L259 expects metadata removal. Any tablet seeing that asset ID could reconstruct the original object's read URL unless serving checks publication role. O L842 allows matching Origin or loopback TCP peer. S L190 says reuse the existing fence. Actual `_origin_denial` at `main.py:608-627` is inactive when unset. `tests/test_security.py:83-116` pins that behavior. Caddy provides authentication at `deploy/hotspot.Caddyfile:55-64`; an Origin is not a credential and a proxy's upstream peer is not the end user's trust level.

Failure. Re-encoded display images can coexist with anonymously readable GPS-bearing originals. An unset guard can leave a new upload route public in direct LAN mode. A generic loopback exception can confuse trusted operator requests with proxied requests. A partially published object, deleted backup dependency, or invalid schema can make an apparently successful upload unrecoverable.

Minimum correction. Require an explicit operator upload configuration. The normal release path uses the existing authenticated operator ingress and loopback-only backend, with tablet ingress denying upload regardless of supplied Origin. A separate explicit loopback development mode is reasonable; it must not silently authorize arbitrary LAN clients or every request whose immediate peer is the proxy. If direct LAN upload is desired, define actual operator authentication first. Preserve existing static behavior rather than expanding its trust claim.

Use a normalized master hash as the render asset ID and distinct exact-byte hashes for renditions. Keeping a source hash as metadata is fine. If retaining originals, mark them private to authenticated operator export/backup and exclude them from tablet object publication. Check that role on every read. Strip EXIF including mirrored orientation, GPS, XMP, comments, and other metadata from published image bytes. Sniffing alone is insufficient. Preserve full structural/decode checks, exclusive staging, hard byte/pixel/output limits, and a terminable bounded worker with timeout, resource limits, and bounded output. Keep source-ingest limits separate from tablet rendition limits.

Publish complete immutable objects before committing ready index rows, and expose only ready published objects. Define crash reconciliation for file-before-row failure. Keep curated `O_NOFOLLOW`, regular-file, and byte-ID protections at `assets.py:269-295`; a managed store may use its documented server-owned immutability boundary instead of rehashing a whole movie on each range. Automatic destructive object GC waits until reference closure, in-flight ingest, and backup pinning are proven.

Extend backup, verification, and new-target restore in this same milestone. `backup.py:386-411` already recursively follows nested `asset` keys, so S L35 was too broad about playlist traversal. What it lacks is new-table roots, rendition/original relationships, owned-store lookup, and large-video validation. Its current size cap is at L94. Select references from the captured database and protect those bytes during copying. Preserve the approved referenced snapshot default in `deploy/OPERATIONS.md:78-85`; offer full-library export explicitly. O L889 silently changes that default to all uploads. If full export is selected, private originals still need correct restore metadata and access rules.

Preference. Retain O's bounded process, index, color normalization, and rendition work, with S's publish-before-ready and backup pinning rules. Neither proposal should ship deletion/GC or source-file reads on informal assumptions. Take a verified pre-migration backup and preserve the prior database/assets for rollback. Old manifest readers already reject unknown manifest versions at `backup.py:671-677`; an old binary cannot retroactively learn to reject every new database schema. Document compatible backup tooling after upgrade.

### 7. Keep native file video first, but remove guarantees that its APIs cannot provide

Evidence. O §15.3 L936 says full download means stalls cannot happen and memory equals file size. O L918 accepts Main/High through level 4.2 and 1080p60 by default. O L960 treats seek completion or a frame callback as decoded readiness; O L969 uses native looping. S L236-273 offers narrower candidate profiles and observed buffer goals but also needs an explicit loop/end policy. The current endpoint at `main.py:1297-1319` returns whole bytes, so ranged media is genuinely new work.

Failure. A Blob removes network fetch during playback but can still hit decode, memory, GC, scheduling, or background failures. Its peak memory is not established by encoded file size. Native buffering cannot enforce a maximum or exact N-second target. Independent loop restart gaps accumulate divergence. A desktop WebM run does not validate the production MP4 codec/profile or old-tablet activation. A successful seek event is insufficient by itself to prove the target frame is usable.

Minimum correction. First test the actual transformed native `<video muted playsinline>` route on the available mixed pair. Record codec profile/level, frame rate, pixel format, dimensions, bitrate, first-frame behavior, seek, muted activation, clipping, and rotation. Use 720p30 near 2 Mbit/s and a lower fallback as candidates; do not describe them as universal support. Start with ranged HTTP and observed contiguous buffer coverage at the target position, a finite preparation timeout, media state/frame evidence, and local activation outcomes. Near the end, the required ahead range is the remaining duration. `preload` can be ignored, per the [HTML media standard](https://html.spec.whatwg.org/multipage/media.html#attr-media-preload), retrieved 2026-10-23. Keep countdown, buffer goal, recovery policy, live delay, and future segment duration separate.

Use tested framework Range/HEAD serving through the actual proxy, including suffix/invalid ranges, `If-Range`, and a bounded multirange policy. Full-download mode is optional after a small-file memory experiment, with a tested encoded-size cap and object-URL cleanup. It removes one cause of stalls, not all causes. Native loops must be checked against the authoritative occurrence and timeline. Initial synchronized loops may deliberately re-prepare at a boundary; autonomous native `loop` is not the synchronization contract. Defer dual-decoder seamless looping and audio selection. Audio stays muted; any later audio output requires activation on that actual output page and an offset measurement. A controller gesture is not remote tablet activation.

Keep `requestVideoFrameCallback` as useful software evidence, not light-on-glass proof. Its draft explicitly allows late callbacks. [Video frame callback specification](https://wicg.github.io/video-rvfc/), retrieved 2026-10-23. Correction gains, seek-delay prediction, and seek-only fallback require actual device tests. A poster fallback is a labelled exclusion from video presentation, not a synchronized video participant.

For live work, retain O's delayed HLS option and S's separate interactive WebRTC experiment. Do not preselect either before source/delay requirements. HLS program date-time is an absolute date mapping, not an interchangeable monotonic anchor; define an encoder epoch mapping and discontinuity handling before using O L999-1000. Browser screen capture also needs a proven producer path and packaging/ingest design. Feeding unspecified capture chunks to the server is an experiment, not an implementation-ready fallback. Native Chrome HLS and old iOS preload behavior remain unverified in this review. Remove any universal support claim and test the exact fleet.

### 8. Ship a smaller still release before either proposal's full vertical slice

Evidence. O §7.2 L245-265 requires clocks, outboxes, crossfades, restart continuation, and an optical 50 ms target before the first usable slice, with physical geometry/editor after T10 at L1536-1543. S L384-388 and ticket 5 at L420 put the complete calibrated editor into its first milestone. Current image rendering and named layout/scene behavior already exist. `controller.js:1815-1844` is a numeric-map workflow that can receive incremental improvements.

Failure. O makes a user wait for slideshow infrastructure before uploading one image and postpones the requested arrangement workflow. S can make uploading wait for a substantial editor. Labelling existing numbers millimetres at O L253-255 only works under restrictive measured aspect/mode assumptions and is not a migration or calibration contract.

Minimum correction. Release a recoverable uploaded still on the current logical layout as soon as ownership handling, upload access, normalization/index, UI errors, and backup/restore pass. State clearly that its geometry remains logical. Then ship v3 physical numeric calibration plus a deliberately small accessible drag editor. Do not make either depend on the shared clock, crossfade, comprehensive model catalog, cookie recovery, all outbox work, or live video. Keep the early mixed-device viewport/video spikes as bounded evidence collection, separate from those shipping dependencies.

Preference. Still upload first, physical arrangement second, synchronized cuts third, file video after its hardware gate. Crossfade follows memory/optical evidence. I revise S's milestone 1 into two independently usable releases. This preserves O's useful insight that upload can precede the full physical model, while rejecting a relabelled legacy layout as physically validated.

### 9. Correct the browser-test and synchronization evidence contracts

Evidence. O §16.3 L1036 treats `timeOrigin + performance.now()` as exact shared-host truth, O L1201 calls harness timing lower bounds on real error, and O L1127 mandates VP9/WebM for harness video. S L319-355 gives stronger impairment separation but needs the same warning about clock reference accuracy. `simulator/README.md:191-209` correctly limits its existing evidence. The parent's baseline has no browser pixels, real media bytes, or optical result.

Failure. Separate browser executions or isolated sessions can choose different epoch estimates. Host overload can make desktop timing worse than a physical device, so it is not a mathematical lower bound. A required WebM workaround can silently leave MP4 untested or fail in an engine without that WebM path. New per-client proxy ports can conceal the same-origin storage collision unless isolation is separately asserted.

Minimum correction. Keep the following layers independently reported:

- API simulator and Node VM tests establish protocol/state and arithmetic, with an injected clock for exact estimator/timeline truth.
- Real browser tests use actual client JavaScript, isolated storage contexts, separate sockets, same-origin fleet cases, and additional process/profile runs. Assert identities and simultaneously live sockets, not window count. A distinct proxy port is a distinct origin and must not substitute for this test. Model independent viewport, DPR, physical sizes, orientation, bezels, offsets, reload, and decode/stall state.
- Split control-message fault injection from HTTP/media body shaping. A TCP proxy can delay/rate-limit/reset real streams. It cannot claim actual IP packet loss or RF behavior. A WebSocket relay can deliberately drop/stale-inject application messages, which is a different experiment. CPU throttling and lifecycle control are engine-specific probes, not old-tablet emulation.
- Verify frozen server matrices and rendered coded-pattern edge/interior samples against an independent oracle. Include rendition selection, clipping, rotation, background/empty/error states, and stale-viewport changes. Assert versioned status separately. A green status is not a pixel assertion.
- Keep unmodified-clock browser integration runs. Synthetic drift changes the application clock adapter; it does not move native media clocks or the document animation timeline. Cross-process clock comparison needs a calibrated mapping and uncertainty, not an unqualified epoch addition. HR-Time permits distinct epoch estimates for isolated execution scopes. [HR-Time clock scope](https://www.w3.org/TR/hr-time-3/#dfn-monotonic-clock), retrieved 2026-10-23.
- Probe supported codecs per installed engine. Use alternate clips for algorithm coverage only and label that limitation. Preserve an MP4 run on a real production-capable browser/device. Playwright documents codec differences and that its WebKit is not branded Safari. [Playwright browser documentation](https://playwright.dev/docs/browsers#media-codecs), retrieved 2026-10-23. Desktop WebKit is not iOS Safari.
- Real tablets add independent radios and display pipelines. They still share one AP/channel; they are not independent networks. No desktop context/process arrangement proves airtime contention, panel scanout, hardware decode ceilings, thermal behavior, or tablet sleep.

Use at least 100 still transitions for the provisional p95 gate, and a continuous or explicitly sampled 10-minute video measurement. Prefer wall-wide maximum-minus-minimum onset per event over pooled pairwise values that can conceal one bad endpoint. Report failed/missing devices, max, p95, recovery duration, and excluded intervals. Start with S's provisional 100 ms p95 and 250 ms worst-event still gate, with O's 50 ms as a stretch experiment. Keep 100 ms/250 ms video criteria explicitly cohort-specific and report full-run results as well as steady state. These are product proposals, not measured capability.

Retain O's coded flashes, raw capture retention, rolling-shutter controls, and same-screen noise-floor experiment at L1181-1189. Camera frame interval alone is not accuracy, and the same-screen check still includes panel scanout. Record row position, exposure, capture timestamps, detection uncertainty, and source frame identity. Re-run optical tests after timing/render/media changes. Neither proposal's numerical target can become a reported result without that evidence.

## Worthwhile improvements and claims to qualify

### 10. Keep the viewport and hardware hypotheses as early experiments

O §5 L183 calls D1 and D3 the blockers, but O L187 correctly labels the `100lvh` mismatch inferred. Source proves a possible mismatch between `client.css:44-45` and `client.js:418-452`, not that a visible stretch occurred on the user's tablet. Compare the measured rendering box, visible viewport, backing dimensions, and screenshots in tab/fullscreen/home-screen modes before changing CSS. Preserve the existing reason for the large-height fallback. A hidden `#surface` at `client.css:35` has no useful measured box, so the implementation must measure a stable render container or wait until it is laid out.

O L409's iPad dimensions and CSS viewport, L444's card dimensions, L447's calibration precision, and L1162's automatically recorded model/OS row are not hardware evidence here. Use explicitly hypothetical arithmetic until model specifications are fetched and actual mode/viewport values are measured. A browser report cannot reliably identify the exact iPad model. Use operator inventory and a ruler as the default, with card/profile methods optional. Linux clock suspend semantics are now checked in finding 4; actual tablet sleep, old iOS buffering, transformed video composition, and native HLS remain experiments. I revise S to include this viewport spike earlier and avoid assuming the current render box is already correct.

### 11. Reduce identity and editor scope without losing the requested interaction

Retain close-code-aware ownership and explicit Take over, tested against `tests/test_websocket.py:85-113`. O §M0 L1229-1230 adds a cookie identity authority and `?display=` before demonstrating they are needed. Start with stable local identity, a page/connection ID, durable slot rebinding, and real context isolation. A namespaced URL is a useful manual convenience, not a substitute for isolated browser storage/process tests. Defer cookies until eviction/recovery evidence justifies their cross-origin, namespace, and ingress behavior. Do not interpret display identity as a credential.

Retain O's SVG body/active-panel preview, pointer capture, numeric controls, nudge alternatives, and WCAG single-pointer requirement at L1053-1078. Ship select/drag, cardinal rotation, snapping, identify, numeric/tap/keyboard movement, and save/recall first. Add marquee, distribute, free-angle editing, JSON import/export, and a model catalog later. Use screen-space snapping tolerance, preserve native page scrolling outside the manipulation area, keep focus/selection stable, and avoid live-region announcements for every drag tick. Live calibration writes remain a separately entered mode with serialized preconditioned updates; ordinary dragging edits a local draft and applies one batch.

### 12. Keep persistence and documentation claims exact

O §4.1 L104-111 describes `_commit_wall` as swapping a detached copy. `main.py:329-336` actually calls the mutation twice, first on a copy and then on the live object. Capture IDs, timestamps, and randomized values before that callback and keep it deterministic; do not start timers or generate different session IDs inside it. Preserve disk-failure tests in `tests/test_commit_boundary.py:95-173`. Avoid a speculative asynchronous writer refactor until measured loop blocking warrants it; never insert an await into the present boundary without serialization.

O L1078 says saved layouts contain profile snapshots, but its `PhysicalLayout` type at L513-518 only references profile IDs. S L109-110 also needs exact revision ownership. Freeze the measured geometry used by a saved layout or use immutable profile revisions, so editing a profile does not change every saved layout. Calibration changes invalidate affected preparations explicitly. Saved scene recall still changes content only, as `PROTOCOL.md:327-340` and snapshot tests require.

Retain README's physical-validation and deployment gates at `README.md:289-314`. The requested new roadmap can revise feature ordering, but should explicitly record which older sequencing decisions it supersedes. Do not call reference Caddy/service/kiosk artifacts validated. Security, backup and source inspection are software work; optical and RF acceptance stay open when hardware is missing.

## Strengths to retain and revisions to my proposal

Keep Opus's concrete calibration vocabulary, server matrix delivery, CSS-transformed native video, bounded image worker, rendition/index design, local-only transport, slow-socket isolation direction, and practical optical procedure. Its rejection of frame-lock promises and separation of prerecorded/live media are sound. Its device-specific uncertainty list is useful once hypotheses remain labelled.

I make these concessions and corrections to S:

- Server-computed committed transforms are preferable to maintaining full physical geometry in every tablet. Retain only tested draft-preview composition and an independent oracle.
- A named still playlist can initially be a versioned saved-scene payload. S's separate playlist table is unnecessary unless independent reuse/editing needs it. Freeze its running revision and keep runtime session separate.
- Uploads can ship on logical v2 stills before the entire physical editor. New optional frames do not inherently require a new major. Changed physical/timed semantics do.
- Distinguish ingest-source budgets from tablet decode budgets. S's copied 10 MiB/12 MP cap may reject the very phone photos being requested. Exercise representative 20 MP and rotated inputs, then choose a bounded server limit. Do not raise client decode limits with it. Add memory/timeout evidence before enabling O's 64 MP ceiling by default.
- Keep O's simpler offset estimator initially and defer rate fitting. Add explicit confidence expiry, suspend fencing, and signed presentation compensation that S omitted.
- S's backup criticism needs precision. Recursive nested `asset` references already work; new roots/object relationships and store formats do not. Preserve the approved referenced-snapshot default and add optional full export deliberately.
- S's holding slideshow needs explicit committed occurrence/anchor rules, and native video looping needs versioned boundary recovery. Neither can rely on independent timers.

## Decisions for the final author

| Decision | Recommended choice | Remaining evidence or constraint |
| --- | --- | --- |
| Compatibility | v1/v2 logical contracts; v3 physical/timed contracts; truly additive optional features can stay negotiated | Mixed cached-client/controller and old-state fixtures |
| Uploaded still | Normalize and publish through an existing-compatible still descriptor first | Exact-byte IDs, ingress refusal, restore proof |
| Geometry owner | Server composes committed render plans; tablet applies; editor draft port uses independent fixtures | Rendition coordinates, asymmetric rotation, stale viewport, optical ruler trial |
| First releases | Uploaded still, then physical numeric/drag workflow, then timed cuts | Each release independently reviewable and useful |
| Durable/runtime split | Selected scene/settings durable; playback session and monotonic anchors process-local | Restart restores timed content paused/preparing |
| Barrier | Frozen required slots, including offline reservations; readiness lease tied to connection/preparation | Timeout offers retry/exclude/explicit partial mode |
| Transport | Immutable accepted snapshots, bounded per-connection writer, initialization before ordinary delivery | Slow TCP reader and replacement ordering tests |
| Still transitions | Cuts with current/next cache, crossfade later | Memory and optical trials before fades |
| File video | Native ranged MP4, tested common profile, observed buffer goal, muted | Actual old/new tablet probe; no exact-buffer promise |
| Video loops/quality | Authoritative occurrence/version; initially scheduled re-prepare | Measure gaps, seeks, correction stability |
| Live | Separate later branch; delayed HLS versus interactive WebRTC only after product choice | Producer path, capture-to-glass and inter-screen measurements |
| Backup/privacy | Referenced snapshot remains default; optional full export; originals never public tablet objects | Snapshot closure and pins, crash recovery, new-target restore |
| Sync targets | 100 ms p95 initial still/video cohort target, 50 ms stretch; explicit worst/recovery gates | Provisional until optical distributions exist |

## Recommended phase order

1. Establish the two-client browser baseline and duplicate-ownership fix. Preserve the parent simulator report rather than calling it newly measured. Inventory actual hardware and run viewport/ingress checks. An early bounded video fixture is evidence work, not a dependency on a finished video product.
2. Ship managed still upload on the existing logical layout. Include explicit operator access, bounded normalization, published index lookup, controller progress/error recovery, and backup/restore. No clock or full editor dependency.
3. Add schema-versioned v3 physical geometry, numeric calibration, immutable profile revisions, fixed content bounds, atomic preconditioned layout edits, and the minimum accessible drag/save workflow. Preserve old layouts and scene/layout separation. Verify real mixed-tablet still geometry when available.
4. Add the bounded writer and versioned playback core, clock/suspend rules, status, and a scheduled numbered-cut experiment. Then ship hard-cut still playlists with frozen membership, lease/connection fencing, cancel/reconnect coverage, and the optical gate. Crossfade is a later small milestone if its memory and visible benefit justify it.
5. Pass the real native-video profile/transform/activation experiment before building the complete video UI. Add ranged serving, bounded ingest/probe, observed buffer goals, versioned start/pause/seek/loop, explicit recovery, and large-media restore. Scale from a mixed pair only after its clean run and optical data.
6. Complete deployment/soak/radio-capacity evidence for the implemented scope. Consider segmented VOD or live capture only against a written need. Keep hardware gaps visible and stop all test-owned processes. No sudo or network mutation is part of automated verification.

This yields an initial ticket order of browser baseline, ownership, still ingest/recovery, v3 geometry/batch edits, minimal editor, ordered sender/playback core, cut playlists, video viability/range serving, scheduled file playback, and deployment evidence. Split large tickets further at independently passing boundaries. Do not make the first five depend on video or a generalized media framework.

## Product decisions that evidence cannot settle

| Question | Default for the final roadmap |
| --- | --- |
| Must phones/tablets upload directly? | Operator-laptop upload first. A scoped uploader is separate work. |
| Is content private from LAN participants? | Existing trusted-LAN read model for published render assets, clearly labelled. Private media requires asset/device authorization. Originals remain operator-only regardless. |
| Should a missing tablet stop timed playback? | Keep wall together, with named required slots and visible timeout. Partial presentation requires an explicit choice. Static image sharing does not wait for a synchronization barrier. |
| Resume automatically after restart? | Restore still/layout; timed media paused/preparing. Optional continuity later uses an explicit wall-clock policy, never old monotonic anchors. |
| Which physical setup mode is supported? | Calibrated fullscreen/home-screen mode first where available. Tab mode needs a measured usable viewport and remains qualified until tested. |
| What upload limits? | Separate server-source and client-rendition budgets. Start with 2048-pixel display renditions plus a smaller fallback; exercise ordinary 20 MP phone photos before fixing the source cap. Quotas/timeouts/worker bounds must be explicit and configurable. |
| Does backup mean the whole library? | Existing referenced snapshot by default, with an explicit optional full-library export. |
| How strict is sync? | Provisional 100 ms p95 cohort target and reported worst/recovery windows. Improve toward 50 ms after measurement; do not relabel a target as a result. |
| Is audio needed? | Muted wall initially. Later one explicitly activated output with measured offset. |
| What live source and acceptable delay? | Defer implementation. If requested, compare deliberately delayed coherent playback with interactive mirroring before choosing transport. |

The final roadmap should be one chosen sequence with these contracts, not a union of both proposals' optional features. Missing hardware blocks the relevant validation claim, not useful upload and layout software work.
