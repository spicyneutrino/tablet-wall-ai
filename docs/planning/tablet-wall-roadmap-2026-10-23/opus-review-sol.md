# Round 2 review: Cursor Opus on Sol's roadmap, and on its own

Written 2026-10-23 against commit `65a4d50`. This reviews `/tmp/tablet-wall-roadmap-20261023-sol.md` (467 lines) and re-checks `/tmp/tablet-wall-roadmap-20261023-opus.md` (1671 lines). "Sol L162" and "Opus L460" are line numbers in those files. `path:line` references point into the checkout.

## Bottom line

- Neither plan should go to implementation as written. Six issues block a coherent final plan, and four of them are partly mine.
- **Compatibility.** Keep the device socket at protocol major 2 with capability gates (Opus), and adopt Sol's rule that a client without physical geometry never gets an approximation. That means I withdraw Opus L460 and L906. Bump only the controller socket, which has no capabilities and always ships with the server.
- **Geometry.** Split ownership at the panel. The server composes world geometry (pose, bezels, seams, fit) into a per-device content-to-panel transform. The tablet composes viewport-to-panel and DPR from live measurements plus persisted calibration. My validity signature misses orientation; Sol's plan names no owner and misses the canvas-box inconsistency.
- **First release.** Upload and show stills through the existing `/assets/sha256:` route and image scene. Include ownership and takeover, remote reload, schema versioning, and backup in the same release. Leave out clocks, geometry changes, and crossfade. Physical layout and timed cuts become separate releases with their own evidence gates.
- **Timing.** Sol's preparation leases, connection fencing, and a playback session kept separate from the wall revision are better than mine. Sol's default that offline reservations are required would halt an unattended wall. Use the online cohort frozen at preparation, a bounded hold, and late join.
- **Security.** Sol's upload rule says nothing about the default case where the Origin guard is off. My plan lets anyone on the LAN fetch originals, GPS metadata included, by hash. Both need fixing.
- **Verified in this round:**
  - Linux `time.monotonic()` excludes suspend.
  - HR-Time does not define what a browser clock does across device sleep.
  - Cookies are not isolated by port, so one of my harness claims is wrong.
- **Still hypotheses (stay early spikes):** the `100lvh` stretch, iOS buffering before `play()`, and native Chrome HLS.

## What I checked, and what I did not

- **Plans and coordination files.** I read both plans in full, plus the parent evidence, the baseline summary, and the decisions log. The baseline is 23 scenarios and 1075 checks run in-process, with no browser, JavaScript, TCP, or pixels.
- **Source.**
  - Python: `main.py`, and `tabletwall/` `protocol.py`, `state.py`, `hub.py`, `persist.py`, `assets.py`.
  - Tablet client: `frontend/client/client.js`, `client.css`, `index.html`, plus parts of `controller.js`.
  - Deployment: `deploy/hotspot.Caddyfile`, `deploy/backup.py`.
  - Also `PROTOCOL.md`, `simulator/geometry.py`, `tests/test_websocket.py`, and the `Makefile`.
- **Local runtime checks (no server started):**
  - The project's Python 3.13.13 reports `time.monotonic()` as `clock_gettime(CLOCK_MONOTONIC)`, and `time.CLOCK_BOOTTIME` exists.
  - Installed uvicorn 0.52.4 defaults to `proxy_headers=True` and reads `FORWARDED_ALLOW_IPS`, which defaults to `127.0.0.1` (`uvicorn/config.py:355-357, 527`). `fastapi_cli` passes no proxy option.
  - The source of Starlette 1.6.0's `FileResponse` handles `Range`, `If-Range`, 416, and `multipart/byteranges`.
- **Web sources (retrieved 2026-10-23):** Linux clock_gettime(2), Python `time` docs, W3C HR-Time, CSS Values 4 §6.1.2.1, and RFC 6265 §8.5. They are listed at the end.
- **Not done.** I ran no tests, servers, browsers, or devices, and changed no files outside this review. No number in this review is a measurement.

Map from the parent's ten decisions to the findings below:

| Decision | Settled in |
| --- | --- |
| 1 compatibility and migration | B1 |
| 2 transform owner | B2 |
| 3 first release | B6 |
| 4 clock, readiness, fencing, queues | B3, B4, I1-I4 |
| 5 geometry semantics | B2, I8 |
| 6 video | I5 |
| 7 browser test layer | I6 |
| 8 security and recovery | B5, I9 |
| 9 unverified claims | I11 |
| 10 targets | I10 |

## Blocking design issues

### B1. One compatibility contract for devices, controllers, HTTP, and persistence

**The two plans.** Sol L162-L164, L170, and L433 add device and HTTP major 3 for physical geometry and timed control. Opus L51 stays on v2. Opus L460 then sends legacy placement derived from the physical layout, and Opus L638 and L906 send a still image to tablets that cannot run playlists.

**Evidence.**
- New fields and frames are already safe on the device socket:
  - The server ignores unknown device frames (`main.py:1327-1345`; PROTOCOL.md L119).
  - The client ignores unknown frame types (`client.js:1808-1828`) and reads only named `wall` fields (`client.js:1524-1608`).
  - `DeviceRegistration` does not forbid extra keys (`main.py:154-158`).
  - `_wall_frame` already downgrades content by capability (`state.py:179-186`). PROTOCOL.md L33-L35 states that as a rule.
- Geometry is not an additive change.
  - Wall units are documented as abstract, not millimetres (PROTOCOL.md L256-L263).
  - The legacy renderer is one centred, uniform cover of the visible rectangle (`client.js:1377-1386`). It cannot express a 180-degree mount, OS rotation that differs from the mount, or a viewport offset under browser chrome.
- The controller socket negotiates only `protocol`, not `caps` (`main.py:1421-1445`; PROTOCOL.md L25).
- Tablets cannot be told to reload. Nothing in `client.js` calls `location.reload`. Opus already has `client_build` detection (Opus L629) but puts it in the sync milestone (Opus L1320). On 4426 it only shows a message (Opus L740). A manual reload does fetch new code, because static files are served `no-cache` (`main.py:421-433`).
- Persistence has no safety net against new shapes.
  - Recall validates exact key sets (`main.py:355-411`), but `load_state` validates nothing (`persist.py:91-109`).
  - `_wall_state` indexes `layout["width"]` directly (`state.py:152-163`).
  - Startup rewrites the row with a new generation (`main.py:118-122`).
- The protocol branches tied to major 2 that a device major 3 must touch are `main.py:1395, 1402, 1451`, `hub.py:103, 115`, and `controller.js:1665-1798`.

**Failure modes.**
- **Opus.** A v2 tablet without the physical capability renders a physical layout through the old cover. That is plausibly right for an upright fullscreen tablet, and silently wrong for 180-degree mounts, rotation-lock mismatches, and tab mode. The legacy still has no defined re-send at each cut, so those tablets freeze on one slide.
- **Sol.** A rolled-back server answers 4426 to every page that negotiated major 3. Neither plan reloads on 4426, so the wall shows an error until someone touches each tablet. Additive frames also get duplicate `/api/v3/` routes they do not need.
- **Both.** An old binary started against a migrated database fails at its first wall read, not at startup, unless the legacy column stays valid.

**Correction: the contract I recommend.**
1. **Device socket stays at major 2.** Clock, status, readiness, commands, playback, and physical geometry become capabilities, gated both ways: `caps` from the client and `server_caps` from the server.
2. **No approximation.**
   - On a physical layout, a device without the geometry capability gets `placement: null`, which today's client already renders as "unplaced". The controller marks it "reload needed".
   - A device without the timeline capability gets today's colour fallback for timed content, with the same label.
   - This adopts Sol L162-L164 in substance and withdraws Opus L460, L638, and L906.
3. **Controller socket moves to major 3**, or gains `caps`. I prefer the bump, because a stale operator tab should fail loudly. While a physical layout is active, the legacy layout writes (`PUT /devices/{id}/placement`, `POST /wall/auto`, `PUT /wall`) return 409 with an "upgrade the controller" message (Sol L164). New typed operator routes can live under any prefix without changing the device major.
4. **Reload support ships in R1.** The welcome carries `client_build`, a capability-gated `reload` command exists, and the new client reloads once (guarded by a sessionStorage counter) on 4426 or a build change. Every tablet must be reloaded by hand once to get that build. After that, upgrades need nobody at the wall.
5. **Persistence.**
   - Use `PRAGMA user_version` plus a `schema` field in each JSON document (Sol L104).
   - Migrations add new tables (displays, calibrations, physical layouts, media) until the physical model is proven.
   - The legacy `wall_state.layout` column always holds a valid legacy document. While a physical layout is active, that is a placeholder with no placements. An old binary then shows every tablet as unplaced instead of failing.
   - True rollback stays "old binary plus pre-migration backup" (Opus L1238, Sol L429).

**Preference.** Major 2 with capabilities for devices. Reserve device major 3 for actually removing legacy fields, which Opus L597 already says.

### B2. Who owns the transform, what invalidates calibration, and which rectangle is the canvas

**The two plans.**
- **Opus.** Opus L47 and L398-L403 compose the whole chain on the server and send `contentToCss`. Its validity record `validFor` (Opus L379, L526) holds viewport size, DPR, fullscreen, and standalone.
- **Sol.** Sol L128-L136 composes `D * inverse(V) * inverse(B) * F` and plans both `geometry.py` and `geometry.js` (Sol L74), but does not say which one is authoritative. Its signature does include orientation (Sol L109).

**Evidence.**
- The client sizes the canvas backing store from `innerWidth` and `innerHeight` (`client.js:418-441`). The canvas element itself is `100lvh` tall (`client.css:36-48`).
  - CSS Values 4 §6.1.2.1 defines large-viewport units as if retractable browser UI were retracted. It says content "might be hidden behind such interfaces" and leaves details largely to the browser.
  - A mismatch is therefore allowed by the spec, but nobody has observed one on these tablets.
- The client re-registers only when `innerWidth x innerHeight` changes (`client.js:1610-1640`). A flip between the two landscape orientations changes neither size nor DPR.
- The simulator checks frames, not pixels, and keeps its own copy of the cover math (`simulator/geometry.py`). It cannot check anything computed in JavaScript.

**Failure modes.**
- **Opus.** A 180-degree OS flip passes `validFor`, so that tablet draws upside down relative to the wall. In tab mode, every toolbar show or hide needs a server round trip before the picture is right again.
- **Sol.** If the tablet also composes pose (B) and fit (F), the seam and fit rules live in both Python (validation, auto-arrange, overlap warnings) and JavaScript (rendering) with no stated winner. The simulator could not catch drift between them.
- **Both.** If the `lvh` hypothesis holds, viewport-to-panel (V) and DPR (D) are both wrong by the ratio of `100lvh` to `innerHeight`. Sol never mentions the mismatch; Sol L28 describes `prepareCanvas` without it.

**Correction: split at the panel.**
- **Server.** It owns body pose B, bezels, seam mapping, and content fit F. `geometry.py` emits one `contentToPanel` transform per device, mapping content coordinates to active-panel millimetres in the panel's native orientation. The simulator checks it against its independent oracle.
- **Tablet.** It owns viewport-to-panel V and DPR scaling D, recomputed on resize, orientation change, and resolution change.
  - V comes from persisted calibration: CSS pixels per millimetre, calibrated orientation, and anchor edge and offset.
  - V also uses live values: the measured canvas rectangle, `screen.orientation.angle` (or `window.orientation`), and `visualViewport.scale` where available.
  - If a live value falls outside the calibrated model (zoom, unknown orientation, pinch zoom), the tablet draws best-effort with an on-screen "uncalibrated" marker, reports that state, and drops out of physical acceptance.
  - Both plans correctly refuse to infer PPI from DPR.
- **Canvas rectangle.** One measured rectangle sets both the canvas CSS box and the backing-store basis. Keep the `lvh` stretch labelled a hypothesis (Opus L187) and measure it in P0. Make the fix anyway, because it is cheap.
- **Controller preview.** It runs B and F in JavaScript for drafts only, and redraws from server output after Apply.
- **Test vectors.** Use two labelled sets.
  - Hand-derived correctness vectors cover asymmetric bezels at all four rotations, negative offsets, fractional DPR, portrait and landscape, a 180-degree OS flip, and a toolbar on each edge. pytest, the Node client tests, and the editor tests all read them.
  - Generated Python-to-JavaScript parity vectors are labelled as parity only.
  - This revises Opus L1084, which regenerated goldens from production code.

### B3. Who is in the readiness cohort, how long readiness lasts, and who may stop the wall

**The two plans.**
- **Sol.**
  - Every placed display is required by default, offline reservations included, and the current slide holds until all of them are ready (Sol L222, L228, L447, L459).
  - Readiness also requires a current calibration (Sol L222). A changed viewport marks calibration for review, and browser-chrome changes exclude the tablet from timed readiness (Sol L82, L148).
- **Opus.** Only "bound, online, capable" devices count, and the wall never holds past `maxWaitMs` (Opus L804, L1047). Readiness is a status phase with no lease (Opus L647-L668).

**Failure modes.**
- **Sol.** Read together, those lines mean one tablet with a dead battery, or one Android URL bar sliding in tab mode, freezes the slideshow on every other tablet until an operator steps in. On an unattended wall, nobody does. If Sol meant "excluded from the cohort" rather than "required but not ready", the plan should say so.
- **Opus.** A tablet that reported ready and was then hidden, replaced, or reloaded still counts, so the wall commits on stale readiness.

**Correction.**
- Freeze the cohort when preparation starts: the placed devices that are online at that moment. Offline reservations are reported prominently as absent, but they do not block.
- Online devices that are not yet ready hold the group for at most `maxHoldMs`. A proposed default is the smaller of half the dwell time and 5 s. After that the server commits anyway. A late device keeps its current still (never black) and cuts as soon as it is ready.
- Sol's "Keep wall together" becomes an explicit per-show option. It is the default only for starting a video.
- Readiness is fenced, as in Sol L174-L184:
  - It carries a preparation ID, session ID and version, and connection ID.
  - It expires on disconnect, a hidden page, or supersession.
  - It is rechecked immediately before commit.
- Tab mode counts as "approximate": it can present but never joins physical acceptance (I8). Toolbar movement therefore never flips readiness.

### B4. The playback version must not share the wall revision (my plan)

**The plan.** Opus L588 puts the playback session inside `scene.content`. Play, pause, next, and the server's own preparing-to-playing step all become `_commit_wall` calls. Opus L719 then uses `"<generation>:<revision>"` as the ETag on every wall route.

**Evidence.**
- `_commit_wall` writes to SQLite synchronously before applying (`main.py:312-336`, `persist.py:70-88`).
- `PUT /scene` awaits the asset lookup before it commits (`main.py:897-918`). A precondition checked before that await can be stale by the time of the commit.

**Failure modes.**
- During a slideshow, every automatic transition bumps the revision, so an operator's unrelated layout edit fails with 412.
- Each transition also pays a synchronous fsync on the same event loop that answers clock pings.
- Persisted schedule anchors invite reuse after a restart.

**Correction (adopts Sol L166 and L172).**
- Keep a process-local playback session: a random ID plus an increasing version, separate from the durable wall revision.
- Scope each precondition to its resource: the wall revision for layout and scene, the session version for playback. Check both inside the synchronous commit, after any awaited validation.
- Persist only the selected playlist revision, the play or pause intent, and a wall-clock resume hint. Never persist monotonic times.
- Opus L1071's "live mode" calibration nudges become a process-local draft sent to the affected tablets, saved only on Apply.

### B5. Who may upload when the guard is off, and keeping originals private

**The two plans.**
- **Sol.** Sol L190 limits uploads to the operator origin by reusing the Origin guard and proxy authentication.
- **Opus, ingress.** Opus L842 allows uploads from a configured, matching operator origin or from a loopback peer.
- **Opus, originals.** The asset ID is the hash of the original (Opus L469). The original is stored as an object (Opus L480), served by hash to any tablet (Opus L709), and backed up by default (Opus L889).

**Evidence.**
- With `TABLET_WALL_OPERATOR_ORIGIN` unset, which is the default and what `make dev` uses, the guard does nothing (`main.py:469-472, 602-610`). The parent found the live app on `http://10.42.0.1:8000`, directly on the hotspot.
- Registration and the device socket require no credential (`main.py:745-772, 1348-1373`). Anything on the LAN can therefore receive wall frames and the asset IDs inside them.
- Behind Caddy, the backend sees the real client address only because uvicorn trusts `X-Forwarded-For` from `127.0.0.1` by default (local check above). The operator listener strips `Cookie` and `Authorization` (`deploy/hotspot.Caddyfile:55-65`).

**Failure modes.**
- **Sol.** In direct or dev mode, any LAN peer can feed files to the decoder and fill the quota.
- **Opus.** `GET /media/<id>` hands the original, GPS EXIF included, to any LAN client that has seen a wall frame.

**Correction.**
- Accept uploads only when one of two conditions holds; otherwise answer 403.
  - The operator origin is configured and matches.
  - The effective peer is loopback, after uvicorn's proxy-header handling.
- Pin both cases with tests, including a forged `X-Forwarded-For` sent from a non-loopback peer.
- The served ID is the hash of the normalized, metadata-stripped bytes (Sol L196). Originals are not kept by default; at most an original digest is stored. Nothing a tablet can reach is addressable by an original's hash.
- Keep Sol's publication order (Sol L194-L200): stage, validate in a bounded worker process, fsync, rename, then commit the metadata row, with reconciliation for crashes in between.

### B6. Both first releases are too big

**The two plans.**
- **Opus.** The first slice is upload plus clock, readiness, crossfade playlists, and an optical 50 ms gate (Opus L55, L245-L265, through milestone 4 at L1210-L1216).
- **Sol.** The first slice is upload plus physical geometry, calibration, and the full drag-and-drop editor (Sol L90, L384-L388, tickets 1-5 at L416-L420). Ticket 3 also waits on the Playwright harness (ticket 1).

**Failure modes.**
- The user's first goal, sharing an uploaded image, waits weeks behind clock work or the editor.
- Crossfade keeps extra decoded layers in memory before anyone has measured the oldest tablet. Opus L903 estimates about 42 MB for three layers on a 10.2-inch iPad.

**Correction: R1 is "upload and show".**
- **Ownership.** Stop retrying after a 4409, offer "Take over", bound registration values, and use monotonic liveness.
- **Updates.** Build ID and remote reload (B1, step 4).
- **Persistence.** Schema versioning.
- **Upload.** Serve managed uploads through the existing `/assets/sha256:<hex>` route and image scene. `assets.find` and `fetch` check the managed index before the curated scan.
  - The ID format (`protocol.py:42`), the stored-content validator (`main.py:392-411`), the backup reference pattern, and the Caddy rule (`deploy/hotspot.Caddyfile:39-45`) all accept such IDs unchanged.
  - R1 therefore changes nothing in the tablet client, the protocol, or the ingress.
- **Library and recovery.** Library UI, reference-aware delete, backup manifest 2, and a restore drill.
- **Out of R1.** No clock, no geometry change, no crossfade.
- **Approximate sizing in R1.** Operators can already type measured millimetres into the abstract units. For fullscreen tablets mounted upright, or whose OS rotation matches the mount, the existing uniform cover is then scale-correct (`client.js:1377-1386`). Document that as "approximate, uncalibrated" and leave PROTOCOL.md's unit definition alone.
- **Harness.** R1 should not wait for Playwright approval. If the harness is not approved yet, record a manual two-tab check instead.

R2 (physical layout and editor) and R3 (timed cuts) follow one shared protocol ticket. They touch different modules, so they can run in parallel.

## Worthwhile improvements

### I1. One ordered sender per connection, with the welcome queued first

- **Use one queue.**
  - Opus L757's three priority lanes break first-in, first-out order across message kinds: a control frame can overtake the snapshot it depends on.
  - Adopt Sol L53's single bounded queue. A newer snapshot replaces a queued snapshot of the same kind. Prepare, commit, and cancel are never dropped.
  - Stamp the server send time at dequeue (Sol L218; Opus L1314). Close the socket when a send deadline passes.
- **Fix a welcome-ordering window.**
  - Today `ws_device` publishes the new socket and its protocol (`main.py:1378-1383`), then awaits `replaced.close()` (`main.py:1385-1387`), and only then sends `welcome` (`main.py:1400`).
  - A concurrent `_broadcast_wall` can therefore, in principle, reach the new socket before `welcome` during a takeover.
  - That is harmless today, because `handleFrame` does not wait for the welcome. It would break Sol L182's binding of the generation to the welcome lineage.
  - Create the sender with `welcome` already queued before publishing the socket.

### I2. Clock jumps and liveness

- **Suspend.**
  - Opus L751's suspend claim is now verified. Here `time.monotonic()` is `CLOCK_MONOTONIC` (local check), which "does not count time that the system is suspended" (clock_gettime(2)). `time.CLOCK_BOOTTIME` includes suspended time (Python docs) and is available.
  - Detect laptop suspend as a change in `CLOCK_BOOTTIME - CLOCK_MONOTONIC`, which grows only by time spent suspended. Opus's wall-clock comparison also fires on NTP steps.
  - On a detected change:
    - bump a `clockEpoch` that travels with every server timestamp;
    - make clients resample their clock offset;
    - re-derive slideshow positions;
    - re-prepare video.
- **Browser clocks across sleep.**
  - HR-Time defines no behavior across device sleep. It only requires that the clock never decreases within one browser session.
  - Keep both plans' client resample triggers: page becomes visible, `pageshow`, `online`, or a timer firing more than 1 s late.
  - Log `performance.now()` against `Date.now()` across a real tablet sleep in P0.
- **Liveness.** Adopt Sol L56. Liveness ages use UTC wall time today (`state.py:73-78`).
  - When the hotspot laptop regains internet, a forward NTP step of more than 15 s expires every socket at once.
  - A backward step keeps dead sockets online.

### I3. State the clock bound precisely, and define the sign of latency compensation

- **The bound.**
  - Sol L218 says half the round trip is "not a guaranteed clock-error bound". For the offset at the moment of the sample, it is one.
  - With non-negative one-way delays u and d, the offset error is (u - d)/2 while the round trip is u + d. The error is therefore at most half the round trip, even with application-level timestamps.
  - Opus L790 and L830 rely on this.
  - What the bound does not cover is drift since the sample, timer lateness, compositor delay, and panel delay. That is why optical evidence stays mandatory.
- **Latency compensation.** Rename Opus's "latency trim" (Opus L377, L814) to `presentLeadMs` and define it:
  - **Scope:** per device, browser build, launch mode, and refresh rate, stored with the calibration.
  - **Sign:** positive means this device lights up later than the cohort median, so it triggers earlier. Local trigger time = toLocal(T) - `presentLeadMs`. During video, the same device runs ahead by `presentLeadMs`.
  - **Source:** optical measurement only, with its uncertainty. Default 0, bounded to about ±100 ms.

### I4. Slideshow cuts: commit early from an anchored plan

- **What each plan gets wrong.**
  - Opus L806 lets tablets cut on their own at known times, so the group can never hold.
  - Sol L222-L228 commits each cut after readiness, but leaves the planned time ambiguous.
- **Combined rule.**
  - An anchored timeline gives the planned cut times.
  - Prepare item k+1 right after cut k.
  - Commit as soon as the cohort is ready, which is normally seconds early. An early commit also survives a brief socket drop.
  - If the cohort is not ready by the planned time minus the safety lead, apply B3's bounded hold, then commit and re-anchor so the next item still gets its full dwell.
  - A device without a commit keeps its current still: it may be late, never early.
- **Cancellation.**
  - Cancel by bumping the version.
  - Discard stale decodes with the existing attempt-token check (`client.js:1054`, `isCurrentImageAttempt`; Sol L178).

### I5. Video details

- **Full download is a spike, not a feature.** Opus L936 offers full download into a Blob as an operator option. Memory equals the file size, and iOS behavior is unverified, so it belongs in the P0 media spike.
- **Scheduled loops by default.** Hold the last frame, seek to 0, and restart at the committed time (Sol L226). Opus L969 uses native `loop` and corrects drift afterwards. Measure each device's native loop gap in the spike.
- **Correct locally first.** Sol L269 re-prepares the whole group above 250 ms, which pauses every tablet for one bad one. Use rate correction, then a per-device seek, and rebuffer the group only when a device stalls under "keep together". All thresholds in both plans stay provisional.
- **Quality experiment.** Every tablet decodes the full frame but shows only its slice, so on an N-tablet wall each tablet upscales roughly 1/N of the source. Both plans defer tile renditions (Opus L991, Sol L72). For walls of more than about four tablets, the probe should compare full-frame and tile renditions and record the re-encode cost per layout change. This is arithmetic, not a measurement.
- **Start bitrates low.** Opus L926 suggests 6-8 Mbit/s per stream, multiplied by N tablets. The parent saw the hotspot and the laptop's Wi-Fi link sharing channel 44. Start from Sol L236's candidates and Opus L988's network self-test.
- **Qualify support claims.** Opus L930 cites MDN's WebCodecs page for `<video>` decoder breadth, and Opus L976 says "broad". Both should read "starting candidate, confirmed per device". Keep native Chrome HLS out of the comparison until there is an HLS decision.

### I6. Harness corrections

- **Isolation.** Opus L1114 says each client gets "its own proxy port, and so its own origin, which also isolates storage". That is wrong for cookies: RFC 6265 §8.5 says cookies do not provide isolation by port. Isolate clients by browser context or profile only.
- **Three impairment layers, each named in reports:**
  - a WebSocket message relay (Playwright `WebSocketRoute` connected to the server; Sol L339) for stale, duplicate, and dropped messages;
  - a user-space TCP proxy (Opus L1110-L1114; Sol L341) for delay, stalls, and resets;
  - context-level request routing for HTTP and media failures.
- **Time injection.** Inject time through an app clock adapter (Sol L343) instead of wrapping `performance.now()` (Opus L1120-L1122). Keep one run with the unmodified clock.
- **Pixel evidence.** Keep the coded-pattern pixel assertions (Opus L1124, L1137) as evidence separate from what tablets report in status frames.
- **Sample size.** A 95th-percentile claim needs at least 100 events (Sol L369). Opus L261's 20 transitions cannot support one.

### I7. Defer the identity cookie

- Opus L52 and L1229-L1230 add an HttpOnly cookie and a `whoami` endpoint. Three facts argue against it:
  - Cookies are not isolated by port.
  - WebKit's storage rules for IP-address hosts and Home Screen apps are unverified.
  - Rebind and "Replace tablet", which both plans have, already fix the visible problem.
- Keep `?display=` as a development aid only. Revisit the cookie if a 7-day device test shows storage loss.

### I8. Calibration modes and the display profile

- **Launch modes.** Physical accuracy claims cover fullscreen and standalone only. Tab mode is "approximate" (Opus L1389).
- **Profile shape.** Store the measured active size and four non-negative bezels in native orientation (Sol L126). Opus L499's body size plus centre offset allows combinations that contradict each other.
- **Legacy conversion.**
  - Legacy bezels are in wall orientation (`client.js:382-416`), so converting a rotated legacy placement must rotate them into native orientation.
  - Negative legacy bezels become conversion warnings (Sol L431).
- **Rotation lock.** Recommend it in the kiosk setup. Tablets lying flat can flip OS orientation unpredictably (inferred, not observed).

### I9. Upload limits and backup scope

- **Input limits.** Sol L192 sets input limits equal to today's served limits (10 MiB, 12 MP). Phones can save larger images; check against the operator's own files.
  - Bound inputs separately. Opus L850's 64 MiB and 64 MP is a starting point.
  - Decode large JPEGs at reduced scale inside the worker.
  - Keep the served master within today's 12 MP and 10 MiB (`tabletwall/assets.py:61-62`), so the existing client budget and backup limits hold.
- **Backup scope.**
  - Today's backup copies referenced files only (`deploy/backup.py:19`), and Sol L206 keeps that. Opus L889 copies all uploads.
  - Curated files have a copy outside the app, but uploads do not. I would default to all ready normalized uploads, with video excludable behind a clear "incomplete" label. This is a product choice.
- **Reference traversal.** `_collect_references` already walks `asset` keys at any depth (`deploy/backup.py:386-411`). Playlists stored as scene content are covered if items keep that key. The file locator still has to learn the managed store.

### I10. Targets as gate and goal, each with a method

All provisional; none are measured.

| Quantity | Gate | Goal | Method and minimum sample |
| --- | --- | --- | --- |
| Seam continuity, fullscreen or standalone | ≤ 2 mm | ≤ 1 mm | Vernier scale plus a photo with a ruler; state the measurement uncertainty; check every seam. |
| Still cut skew, healthy cohort | p95 ≤ 100 ms, max ≤ 250 ms | p95 ≤ 50 ms with optical `presentLeadMs` | Capture at ≥ 240 fps after a noise-floor run on one panel; at least 100 cuts. |
| Video steady-state skew, 10 min | p95 ≤ 100 ms outside logged recovery, with the full run also reported | p95 ≤ 50 ms | Burned-in frame counter; list each recovery window (Sol L370). |
| Correct content after the network returns | ≤ 10 s | ≤ 5 s | Harness plus tablets; at least 20 trials. |
| Stale command applied | 0 | 0 | Deterministic tests. |

### I11. Status of the claims the parent flagged

| Claim | Status | Action |
| --- | --- | --- |
| Linux `time.monotonic()` excludes suspend | Verified (local clock info; clock_gettime(2)) | Apply the I2 epoch rule. |
| `performance.now()` across tablet sleep | Not defined by HR-Time | Log it on devices in P0; resample regardless. |
| `100lvh` box vs `innerHeight` backing store | Source fact; the spec allows a mismatch; not observed | Measure in P0; fix with one measured rectangle. |
| Harness storage isolated by port | False for cookies (RFC 6265 §8.5) | Use contexts or profiles. |
| Starlette serves byte ranges | Source handles Range, If-Range, 416, multipart | Test through Caddy. |
| iOS buffers before `play()` | Unverified | P0 media spike. |
| Native Chrome HLS | Unverified, and not on the critical path | Revisit at an HLS decision. |
| iPad spec values, ID-1 card size | Examples, not load-bearing | Measure the actual devices. |
| WAAPI start time uses the `performance.now()` origin | Unverified (Opus L817) | Defer with crossfade. |

## Strengths to keep

**From Sol:**
- The separation of records (Sol L102-L118), including the line that a browser storage profile is a registered display endpoint, not proof of one piece of hardware.
- Preparation invalidation and fencing (Sol L174-L184).
- Staged, immutable publication, with backup in the same milestone (Sol L194-L204).
- Honest impairment layers (Sol L335-L347), including "dropping a WebSocket application message is not IP packet loss".
- Its uncertainty language for optical evidence: sampling is not accuracy, rolling shutter, unobserved intervals (Sol L355-L361).
- Recovery windows cannot be excluded to pass a target (Sol L370).
- Technical-debt items 5 and 7-9 (Sol L53-L57).
- Keyboard and single-pointer editing (Sol L293-L305).
- Live capture as its own product (Sol L277-L287).

**From Opus:**
- The estimator, sampling cadence, and late-join rules (Opus L768-L827).
- The physical-limits section and the explicit non-goal of frame lock (Opus L1005-L1013).
- Coded-pattern pixel checks (Opus L1124, L1137).
- The optical analyzer with a noise-floor run and no new dependency (Opus L1184-L1189).
- The isolation table (Opus L1149-L1157).
- Picking renditions by slice size (Opus L867), and the browser tiers (Opus L1043-L1047).
- Seams as one "virtual gap" parameter (Opus L433-L437).
- The `lvh` hypothesis with a cheap device check (Opus L187).

## What changes in my own plan

1. **Legacy fallbacks are withdrawn.** No placement derived from a physical layout, and no legacy playlist still (Opus L460, L638, L906). See B1.
2. **4426 handling.** Reload once instead of showing a message, and move build detection into R1 (Opus L629, L740, L1320). See B1.
3. **Transform ownership.** Split at `contentToPanel` instead of a fully server-built `contentToCss`, and add orientation to `validFor` (Opus L379, L398-L403, L526). See B2.
4. **Test vectors.** Hand-derived correctness vectors plus a separate parity set, instead of regenerated goldens (Opus L1084). See B2.
5. **Readiness.** Leases and a bounded hold instead of unleased readiness and "never hold" (Opus L804, L1047). See B3.
6. **Playback state.** A separate session ID and version instead of a session inside the scene with one ETag (Opus L588, L719). See B4.
7. **Asset IDs and originals.** Hash the normalized bytes and keep no originals by default, instead of original-hash IDs with originals served and backed up (Opus L469, L480, L709, L889). See B5.
8. **First release.** R1 has no timing, cuts come before crossfade, and percentile claims need at least 100 events (Opus L55, L245-L265, L261). See B6 and I10.
9. **Send path.** A single ordered queue instead of three lanes (Opus L757). See I1.
10. **Suspend detection.** `CLOCK_BOOTTIME - CLOCK_MONOTONIC` instead of the wall clock (Opus L751). See I2.
11. **Latency compensation.** `presentLeadMs` with a defined sign instead of a "latency trim" (Opus L377, L814). See I3.
12. **Video defaults.** Full download becomes a spike, and loops are scheduled rather than native (Opus L936, L969). See I5.
13. **Harness.** Contexts plus a clock adapter instead of proxy-port isolation and a wrapped `performance.now()` (Opus L1114, L1120). See I6.
14. **Identity cookie.** Deferred out of milestone 0 (Opus L52, L1230). See I7.
15. **Display profile.** Four bezels instead of body size plus centre offset (Opus L499). See I8.
16. **Calibration nudges.** A local draft instead of a commit per nudge (Opus L1071). See B4.

## Where Sol should move

1. **Device protocol.** Use major 2 with capabilities instead of major 3, keeping the no-approximation rule (Sol L162-L164, L433). See B1.
2. **Geometry.** Adopt B2's ownership split and the P0 canvas measurement. Today no owner is named and the mismatch is not mentioned (Sol L28, L128-L136).
3. **Cohort.** Use the online cohort frozen at preparation plus a bounded hold, instead of every reservation being required (Sol L222, L459). See B3.
4. **Upload ingress.** Say what happens when the guard is unset (Sol L190). See B5.
5. **First release.** Ship after ticket 3, through the existing `/assets` route, instead of after ticket 5 (Sol L90). See B6.
6. **Limits and backup.** Separate input limits from served limits, and treat backup scope as a product decision (Sol L192, L206). See I9.
7. **Video correction.** Seek the one drifting tablet locally before re-preparing the whole group at 250 ms (Sol L269). See I5.
8. **Clock bound.** Half the round trip is a bound on the offset at the moment of the sample (Sol L218). See I3.

## Decision table for the final author

| # | Decision | Recommendation | Basis | Still needs |
| --- | --- | --- | --- | --- |
| 1 | Device protocol | Major 2 plus capabilities; no legacy approximation | B1 source evidence | Mixed-version tests |
| 2 | Controller and HTTP | Controller major 3; legacy layout writes return 409 on physical layouts | Controller socket has no caps | Stale-tab test |
| 3 | Cached tablets | `client_build`, remote reload, reload once on 4426, all in R1 | No reload path today | One manual reload per tablet |
| 4 | Persistence | `user_version` plus a document `schema`; additive migrations; valid legacy column; pre-migration backup | `load_state` does not validate | Old binary on a new DB |
| 5 | Geometry owner | Server builds `contentToPanel`; tablet builds V and D live | B2 | P0 canvas-box data |
| 6 | Calibration validity | Scale model, orientation angle, DPR, launch mode; tab mode is approximate | The 180-degree flip | Device modes |
| 7 | Display profile | Active size plus four bezels, native orientation | Fewer invalid states | None |
| 8 | Seams | Physical gaps by default; overlap or no-gap later, for grid groups | Both plans | Photo check |
| 9 | Timeline clock | Server monotonic ms plus `clockEpoch`; detect suspend from BOOTTIME minus MONOTONIC | Man page and Python docs | Tablet sleep log |
| 10 | Latency compensation | `presentLeadMs`, sign defined, optical only | I3 | Optical runs |
| 11 | Playback state | Process-local session ID and version; scoped preconditions checked inside the commit | B4 | Model tests |
| 12 | Cohort | Online at preparation; bounded hold, then proceed; "keep together" as an option | B3 | Product sign-off |
| 13 | Slideshow | Early per-cut commit from an anchored plan; cuts before crossfade | I4 | Optical run of ≥ 100 cuts |
| 14 | Send path | One queue, snapshot coalescing, welcome queued first, send deadline | I1 | Slow-socket scenarios |
| 15 | Upload ingress | Configured matching origin, or loopback after proxy-header handling | B5 | Forged-header tests |
| 16 | Asset IDs | Hash of normalized bytes; existing `/assets` route; no originals kept | B5, B6 | Test fixtures |
| 17 | Upload limits | Inputs bounded separately; master ≤ 12 MP and 10 MiB | I9 | Operator's phone files |
| 18 | Backup | Manifest 2; all ready uploads; video excludable | I9 | Restore drill |
| 19 | Video V1 | Progressive MP4 with ranges, muted, scheduled loop, local correction first | I5 | P0 media spike |
| 20 | Video quality | Compare full-frame and tile renditions for walls of more than four tablets | I5 | Probe |
| 21 | Harness | One context or profile per client; three labelled impairment layers; clock adapter; pixel checks | I6 | Playwright approval |
| 22 | Targets | Gate and goal pairs with methods; at least 100 events | I10 | Hardware |
| 23 | Identity cookie | Defer | I7 | 7-day device test |

## Recommended phase order

1. **P0, spikes and baseline.** These run in parallel and add no product features.
   - The two-context harness, including the same-context collision case (Sol ticket 1).
   - A display report with the measured canvas box from every available tablet, in tab, fullscreen, and standalone modes (Opus T3, as instrumentation only).
   - An MP4 probe on the tablets (Sol milestone 0): decode, muted autoplay, preload, seek, loop gap, transform, and clipping.
   - A sleep log of `performance.now()` against `Date.now()`.
2. **R1, upload and show.**
   - Build in this order:
     1. ownership and takeover, registration bounds, and monotonic liveness;
     2. build ID and reload;
     3. schema versioning;
     4. upload through `/assets`;
     5. backup manifest 2 and a restore drill.
   - The gate:
     - the pytest and Node suites;
     - a malicious-input matrix;
     - a restore into a fresh target that then serves the image;
     - the harness pair drawing a coded test image pixel-correct;
     - one real tablet showing an EXIF-rotated phone photo upright.
3. **Shared protocol ticket.** The per-connection sender, a capability registry, `status` and `identify` frames, and PROTOCOL.md updates.
4. **R2, physical layout, and R3, timed cuts.** These can run in parallel; if they run in sequence, R2 goes first.
   - **R2 scope:** the geometry core and numeric calibration, then the editor.
   - **R2 gate:**
     - the correctness vectors pass;
     - the simulator checks `contentToPanel`;
     - coded-pattern harness runs pass on at least 8 mixed contexts;
     - seam photos come from at least two physical tablet models.
   - **R3 scope:** clock sync, leases, the playback session, playlists, early commit, and the bounded hold.
   - **R3 gate:**
     - model tests pass;
     - impairment runs are labelled by layer;
     - an optical run of at least 100 cuts on two tablets, then on four mixed tablets.
5. **R4, crossfade (optional).** Only after memory measurements on the oldest tablet.
6. **R5, video files.** After the P0 media spike and R3.
7. **R6, field readiness.** HTTPS, kiosk setup, wake lock, and soak tests, alongside the other releases whenever tablets are free.
8. **R7, segmented or live video.** Only after a product decision.

## Product decisions engineering cannot settle, with proposed defaults

1. **A slow or missing tablet.** Default: proceed after a bounded hold for stills; hold strictly when starting a video.
2. **Restart.** Default: slideshows resume at the next item; video waits, paused.
3. **Backup scope.** Default: all ready normalized uploads, with video excludable.
4. **Originals.** Default: not kept; at most a digest.
5. **Who can upload.** Default: the operator laptop only.
6. **Media privacy on the LAN.** Default: trusted LAN, with device pairing later.
7. **Launch modes that count for physical accuracy.** Default: fullscreen and standalone; tab mode is approximate.
8. **When to move to the HTTPS origin.** Default: before the R2 calibration gate, because calibration depends on launch mode. Rebinding keeps the display records.
9. **Target wall size.** This decides whether tile renditions are needed.
10. **Sync tolerances.** Default: the I10 gates, with the goals as stretch targets.
11. **Audio.** Default: muted.
12. **Live video and its delay.** Default: deferred.

## Sources (retrieved 2026-10-23)

- Linux man-pages, clock_gettime(2), on `CLOCK_MONOTONIC` and suspend: https://man7.org/linux/man-pages/man2/clock_gettime.2.html
- Python `time` module, on `CLOCK_BOOTTIME` including suspend: https://docs.python.org/3/library/time.html
- W3C High Resolution Time, editor's draft, which has no sleep or suspend rule: https://w3c.github.io/hr-time/
- CSS Values and Units Level 4, §6.1.2.1, on large, small, and dynamic viewport units: https://drafts.csswg.org/css-values-4/
- RFC 6265 §8.5, "Cookies do not provide isolation by port": https://www.rfc-editor.org/rfc/rfc6265.html#section-8.5
- Local runtime: `time.get_clock_info('monotonic')` on Python 3.13.13; installed uvicorn 0.52.4 `config.py`; Starlette 1.6.0 `FileResponse` source.
