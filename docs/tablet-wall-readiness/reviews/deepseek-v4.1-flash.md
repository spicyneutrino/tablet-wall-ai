# Independent readiness assessment — DeepSeek V4.1 Flash

**Repository:** `/var/home/oak/Codes/projects/tablet-wall-ai`  
**HEAD assessed:** `0ff56e30dfd6b2f92995569faa2d6e7fdc90fa8f` (`feat: add measured tablet setup and adaptive wall sizing`)  
**Assessment date:** 2026-11-01  
**Method:** independent source and focused-test review. No browser UI session, no server process, no live database access, no edits. I did not read the other model reports before writing this.

**Evidence legend**

- **[Source]** confirmed in current code at the cited lines.
- **[Test]** actually run by me in this checkout, with the result stated.
- **[Probe]** confirmed by a throwaway in-process `TestClient` probe using a temporary database, assets directory and media directory under `/tmp/opencode`; no live data touched.
- **[User-reported]** the operator's physical 2×2 and 1×4 trials and the current saved wall; accepted as reported, not re-verified by me.
- **[Hypothesis]** plausible but not established by source or a real-device test.
- **[Proposal]** a recommendation, not current behaviour.

The parent's 1177-Python-test, all-Node, ruff, mypy and isolated desktop/mobile/concurrency results are prior software evidence. I did not rerun the full suite; the focused results in §11 are mine.

---

## 1. Verdict and strong existing capabilities

**Verdict: a well-engineered images-only wall prototype, not yet a dependable unattended tablet wall.**

It is ready for a supervised still-image demonstration on known hardware in the **logical** wall mode that the operator has physically exercised. It is **not** ready to be the primary operator path for a mixed-model **physical** wall, and it is not ready for unattended restart/sleep/recovery operation. The code quality, persistence discipline and geometry separation are stronger than the product integration around them.

What is genuinely strong, and should not be rebuilt:

- **Commit and recovery discipline.** Wall changes are written to SQLite from a detached proposal before memory is updated and before controllers are notified (`main._commit_wall`, `main.py:445-479`). A failed save leaves memory, disk and subscribers agreeing. The runtime lock refuses a second worker on one database (`tabletwall/workers.py:12-28`). A new generation on every start forces clients to resynchronise rather than reject restored state (`main._restore_wall_state`, `main.py:150-165`). This is the right shape for a single-process wall.
- **Separated wall concepts.** Layout, scene, revision and generation are distinct (`tabletwall/state.py:7-10`); layouts and scenes save and recall independently. Physical slots pin profile and calibration revisions, so editing a measurement does not silently rewrite an old layout (`tabletwall/displays.py:1-6`).
- **A clean geometry model.** Wall/body/panel/CSS/backing/normalized spaces, six-number matrices, server-owned `G_N_to_P`, client-owned calibrated `U_C_to_P` (`tabletwall/geometry.py:1-18`). The math is independently fixture-tested (`tests/test_geometry.py:31-71`, `tests/client_view.test.js`).
- **Measured models and snapshots.** iPad Air 2 and Pixel C profiles with a recorded 3 mm provisional uncertainty, revision-pinned model snapshots, explicit/manual override, and model-aware rebind (`tabletwall/tablet_models.py:8-131`). This is a sensible foundation; the problem is that its trust level is not visible to the operator.
- **Asset integrity.** Content-addressed asset IDs, hash verification on read, explicit client failure panels instead of a silent blank wall, immutable caching for bytes (`tabletwall/routes/assets.py:35-68`; `frontend/client/client.js:1811-1843`).
- **A real trust boundary.** Optional shared-secret auth, exact-origin CSRF fencing, a tablet-only Caddy route allowlist, uploads disabled by default, bounded registration fields, and a one-process runtime lock. The hotspot launcher verifies redirect, registration, WebSocket upgrade and operator-route denial at boot (`deploy/hotspot.py:132-190`).
- **Operational artifacts with honest caveats.** Verified online backup/verify/restore (`deploy/backup.py`), a service-unit template, kiosk guidance, and hardware gate documents that explicitly say they are **MISSING**. The documentation is unusually honest about what is not proven.
- **Frontend care.** Bounded per-socket writers with coalescing and overflow close (`tabletwall/writer.py`), generation-aware image loads, explicit `NEEDS CALIBRATION` / `IMAGE FAILED` states, wake-lock reporting, reconnect backoff, and accessible controller markup.

The gap is not "the code is bad." The gap is that **the product's main demonstrated capability (one image across tablets) is split across two consoles, the physical path is not operationally complete, and the physical evidence is still missing.**

---

## 2. Concrete blockers

### B1. A physical wall has no first-class still-image control, and the legacy console silently misreports it

**User impact.** On a physical wall, the "Wall console" (`/controller/physical.html`) has Show, Tablet, Content and System tabs, but its Content tab is only a playlist builder (`frontend/controller/physical.html:465-523`). There is no image picker, no colour picker, and no indication of the active still scene. A one-item still playlist is not the same thing: it runs through the experimental playback session's prepare/lease/readiness path, not the static scene the physical renderer uses. To put a still image on a physical wall the operator must open the legacy `/controller/` page and use its Content tab. That page is a protocol-2 client (`frontend/controller/controller.js:30`) and receives a **neutral** wall for a physical layout: `_wall_state()` returns a hard-coded 2000×1000 wall with no placements and `{"type":"color"}` (`tabletwall/state.py:289-298`). A `PUT /scene` issued from that page succeeds — the tablets do show the image — but the response still says colour, because `PUT /scene` returns `_wall_state()` (`main.py:1235-1275`). The v3 config has no `scene` at all (`main._config_payload`, `main.py:1867-1902`), so the physical console cannot know what is showing.

**[Probe]** with a temporary database, a saved image scene and a physical layout: `GET /api/v3/config` had no `scene` key; `GET /wall` returned 409; `PUT /scene` returned 200 but its returned scene was `{"content":{"type":"color"},"layout":"active"}` while the live wall scene was the image. This is not a cosmetic mismatch: the only page that can select the image reports that it did not.

**What fixes it.** Add the projected scene (content, asset name, fit, intrinsic dimensions) to the v3 config payload, and add still-image / colour controls and an active-content status card to the physical console. Make the legacy page detect `layout.kind === "physical"` and either redirect to the physical console or show a hard banner explaining that it is not the layout editor. Do not leave two pages that disagree about what is on the wall.

### B2. Switching from a physical arrangement to a logical layout can silently discard the physical arrangement

**User impact.** Applying a physical layout over a logical one auto-saves the old logical layout under a generated `Before physical …` name (`main.py:2055-2058`). The reverse is not true: recalling a logical layout from the physical console calls `/api/v3/logical-layouts/{name}/recall`, which commits the logical layout with no backup of the active physical layout (`main.py:2079-2091`). The physical console's recall confirmation only mentions an unapplied draft (`frontend/controller/physical.js:2893-2920`), not "your current physical arrangement is not saved." One click can lose a tuned 2×2 mount.

**[Source]** is conclusive; this is a data-loss path, not a theory. **[Probe]** confirmed a physical layout can be applied and the logical backup is created, while the reverse recall has no generated backup in the code path.

**What fixes it.** Before any cross-kind recall or apply, snapshot the current layout under a generated name in the same transaction, exactly as the logical→physical path does. The confirmation should say whether the current layout is already saved and which generated name will hold it. If a generated backup cannot be written, refuse the switch rather than proceed.

### B3. Physical mode cannot forget a device

**User impact.** `DELETE /devices/{device_id}` is fenced by `_require_logical_wall` (`main.py:1029-1031`, `main.py:1678-1684`). The physical console has no Forget action; its legacy card only links back to the logical page (`physical.html:646-652`), which is the wrong page for a physical wall and whose own layout view is neutral. "Delete from wall" removes a slot from the draft, not the roster record. A replaced, lost or test tablet therefore stays in the roster and in the measurement history. At 512 devices the roster evicts the least-recently-contacted offline record, but that is not an operator-controlled cleanup.

This is a functional hole in the requested join → identify → remove/forget → rebind journey. Rebind can move an identity, but it cannot simply retire one.

**What fixes it.** Split roster deletion from layout mutation: allow forgetting an offline device while physical, and remove its physical slot only through the normal draft/apply path (or explicitly ask). Add a two-step Forget action to the physical Tablets tab. Keep the current "cannot forget an online device" protection.

---

### B4. Rapid 2×2 / 1×4 arrangement is not deterministic, and the logical tiling default can create uncovered image bands

**User impact.** Three separate issues compound in the exact workflow the operator uses:

1. **Physical bulk arrange orders by UUID, not by display number.** `arrange-tablets` iterates `Object.keys(state.tabletAssignments).sort()` (`frontend/controller/physical.js:3099-3106`). A `compareDeviceIds` helper that sorts by `#number`, then label, then id already exists (`physical.js:652-668`) and is used elsewhere; bulk arrange does not use it. Four tablets packed in one row therefore get their wall slices in lexical-UUID order. If the tablets are physically sitting left-to-right as #1–#4, the image is scrambled until the operator manually drags every tile to the matching physical position. The stage labels help, but the "rapid" path is not rapid.
2. **Manual Add overlaps the first two tablets.** `addSelectedDevice` computes `column = count % 3`, `columnOffset = count === 0 ? 0 : column - 1` (`physical-stage.js:737-751`). At `count = 0` and `count = 1` the offset is 0 both times, so the second tablet is placed exactly on the first. The third goes right and the fourth left. The operator has to separate the first two by hand, and the overlap may be mistaken for a rendering bug.
3. **Logical Tile defaults to "Keep screen shape" in a fixed wall.** The tile template's first/default option is `keep` (`index.html:473-479`), and `fitPlacementInCell` fits a 4:3 footprint inside a wider cell (`controller-stage.js:723-753`). For a 2×2 of 4:3 landscape tablets in the default 2000×1000 (2:1) wall, each cell is 1000×500, so the placement is about 666×500 with a 333-unit horizontal gap between columns. The global image is continuous in wall coordinates, but no tablet covers that gap: the image is genuinely missing between the physical screens. The controller may warn about shape mismatch, but the default action is the wrong one for a seamless wall. Separately, logical tile application writes placements one at a time (`controller-stage.js:1001-1018`), so a failure halfway leaves a partially tiled wall.

**What fixes it.** Use number/label order in bulk arrange and let the operator reorder before applying. Add explicit 2×2 and 1×4 presets that choose the correct wall aspect and zero gap. Fix the add-placement grid so cell 0 and cell 1 differ. Default the logical tiling to a mode that actually covers the wall (or require "Fit wall to tablets" + Pack for a seamless wall, with a plain-language warning). Make a logical tiling apply atomic, or route it through the same all-slots-in-one-write path the physical console already has.

### B5. Model auto-detection can silently apply the iPad Air 2 scale to a different iPad, and the uncertainty is invisible

**User impact.** `tablet_models.match()` returns `ipad-air-2` for any telemetry with CSS screen `768×1024`, DPR 2 and `platform_family == "ios"` (`tablet_models.py:23-32`), and registration auto-assigns the unique match (`main.py:961-971`). The built-in list contains exactly one iOS model (`tablet_models.py:8-15`), so "unique among built-ins" is not "unique among iPads." **[Hypothesis, externally checkable]** several other iPad models share the 768×1024 @2 CSS signature; if the operator ever attaches one, it receives the Air 2's measured profile and ruler scale without confirmation. A wrong model is worse than "unknown," because the physical plan is then treated as valid.

Even on the correct hardware, the 3 mm `uncertainty_mm` is stored but not shown as a trust state: the calibration is marked `valid` (`tabletwall/state.py:425-452`) and the console displays only `calib rN saved` with an `ok` tone (`frontend/controller/physical.js:501-511`). The calibration's `method` field (`tablet-model approximate`) is editable in the form but does not appear in the roster or wall-health summary. An operator cannot tell a model-derived approximate plan from a ruler-measured one by looking at the console.

The model's non-fullscreen inset is also a guess: `dx = 0 if fullscreen else (sw - width) / 2` and `dy` similarly (`tablet_models.py:123-126`). **[Source]** the formula centres the remaining panel around the viewport. **[Hypothesis]** browser chrome is not centred — Safari's toolbar is at one edge — so a tab-mode model plan can carry a systematic offset of roughly half the chrome height rather than a random ±3 mm. The docs say "approximate"; the console does not.

**What fixes it.** Default a new unknown-signature tablet to unassigned/unknown and require one explicit "this is an iPad Air 2" confirmation before creating a model plan. Show the provenance and uncertainty beside every device: "Model (Air 2), ±3 mm, approximate" vs "Ruler, ±0.7 mm, measured" vs "Unknown." Refuse or clearly warn on model-derived plans in `tab`/`standalone` mode until the inset has been checked on that exact device. Do not expand the built-in model list as a substitute for confirmation.

### B6. Auth and the secure tablet ingress do not currently compose, and the 12-hour session is hostile to an always-on wall

**User impact.** This is not a hotspot-trial blocker (the launcher refuses auth and uploads on purpose, `deploy/hotspot.py:306-309`), but it blocks the next security step.

- Auth issues a 12-hour signed cookie (`tabletwall/auth.py:20`, `auth.py:194`). The running tablet's WebSocket may stay up for days, but the first reconnect after 12 hours hits `POST /devices/register` with an expired cookie; `register()` sees a non-OK response and throws (`frontend/client/client.js:467-498`), and `attemptCycle` retries forever (`client.js:4468-4503`). The wall stays on its last image with "Offline · retrying" and no sign-in action. A wall that needs a manual login after every network blip is not dependable.
- The tablet-only Caddy allowlist contains `/client/`, the client scripts, `/devices/register`, `/ws/device` and asset bytes; it does **not** contain `/auth/login` (`deploy/tablet-routes.caddy:13-51`). A browser navigating to `/client/` with no cookie is redirected to `/auth/login`, which the tablet listener answers 403. `docs/AUTH.md:13` tells the operator to sign in separately on the tablet origin, but the shipped tablet allowlist cannot serve that page. The backend auth and the proxy allowlist are individually sensible; together they are incomplete.

**What fixes it.** Give the wall a durable device credential separate from the operator session (per-device token stored in the client, or a long-lived device cookie with rotation), and handle 401 in the client with a visible "Sign in again" action or navigation rather than silent retry. Add `/auth/login` (and whatever it needs) to the tablet allowlist, or document a single-origin/auth deployment as the only supported combination. Re-test the full negative matrix; the existing trust checker only covers the proxy path, not app auth plus the tablet allowlist.

---

## 3. Important risks and validation gaps (not all blockers)

**R1. The physical path has no real-device evidence.** The geometry is fixture-tested, but the user's 2×2 and 1×4 trials were logical. The server's physical plan, the client's `U_C_to_P`, the Pixel C `portrait_angle = 270` rotation, the 90° mount mapping and the 3 mm model scale have not been observed on glass. The repo itself says all eight hardware gates are MISSING (`docs/validation/HARDWARE-VALIDATION.md:3-41`). This is the first thing a demonstration must change; do not claim "physical spanning works" from software tests.

**R2. The ruler method may not reach the 2 mm seam target.** The ruler overlay caps each line at 200 CSS px (`frontend/client/ruler.js:33-34`). On a 768 px-wide iPad, a 200 px span extrapolates 3.84× to the panel; a 1 mm measuring error becomes ~3.8 mm. The controller defaults the span to 200 (`physical.html:352-355`). The 3 mm model uncertainty is explicitly provisional. This is honest, but the current method plus the acceptance target need a longer-span or multi-span measurement on the real devices. This is a validation/measurement risk, not a reason to delay the assessment or the demo.

**[Proposal]** allow the ruler to span the usable width/height (or several spans) and show the derived mm/CSS and the estimated panel error before saving. Do not make new measurements a prerequisite for reading this report; the existing measurements are sufficient for a first physical trial.

**R3. OS sleep/wake and reconnect are source-plausible but unproven, and the client has no watchdog.** The client connects once and reconnects only when the WebSocket close event fires (`client.js:4426-4438`); the heartbeat checks `readyState` and warns on send failure but does not force a reconnect (`client.js:2352-2369`). The only `visibilitychange` handlers release/retake the wake lock and interrupt playback (`client.js:2439-2450`, `client.js:4311-4317`); they do not re-register or probe the socket on resume. **[Hypothesis]** a suspended iPad/Android page that resumes with a half-dead socket can sit on a stale image until a reload. The docs correctly say this is unverified (`deploy/KIOSK.md:13-41`). Add a visibility/pageshow/online reconnect trigger and a missed-heartbeat or stale-socket watchdog, then test real sleep/wake.

**R4. Source resolution and crop are invisible in the console.** The saved wall reported by the operator is 4 tablets in one row, 320×60 wall units, showing a 2000×745 image with `cover`. **[Arithmetic on user-reported data]** the wall aspect is 5.33 and the image aspect is 2.68, so `cover` shows only about 50% of the image height; each tablet gets about 500 source pixels across. If those are iPad Air 2s (2048 native px wide), that is roughly a 4× upscale. The image may look fine at a distance, but the console does not warn about either the crop or the pixel shortfall. `drawWallImage` always covers and ignores the scene's `fit` field (`client.js:1737-1786`); the API only accepts `cover` (`main.py:338-345`, `tabletwall/protocol.py:76-77`), even though `geometry.fit_matrix` already supports `contain` (`geometry.py:131-161`). Managed uploads serve a 2048-edge display rendition (`media_limits.py:14-19`; `media.py:526-571`), and curated files cap at 12 MP (`assets.py:62-64`), so a four-tablet row of 2048–2560 px panels cannot be pixel-perfect from one global image. This is a quality/visibility gap, not a correctness failure. Add a controller crop preview, a source-pixels-per-tablet estimate, and a `contain` option with an explicit letterbox colour. Measure perceived quality; do not assume the 4× upscale is unacceptable.

**R5. The "wall health" summary can be wrong for a pinned layout.** `validPair` checks the *latest* profile and its latest calibration, not the revisions the active slot names (`physical.js:501-519`). A device whose slot is still valid on an older pinned profile can be counted as "needs calibration" after someone saves a newer profile; a device whose pinned profile is missing but whose latest pair is fine can be counted as healthy. The render plan itself is correctly pinned; the summary is not. This undermines the health signal the operator is supposed to trust. Health should reflect the active slot and the server's actual plan status per device, not only the latest records.

**R6. Operational readiness is reference-grade, not wall-grade.** The hotspot launcher appends `backend.log` and `caddy.log` with no rotation (`deploy/hotspot.py:252`); the service unit is a placeholder-only template; there is no `/healthz` route and no autostart for the combined hotspot+proxy; diagnostics are admitted through `media.admit_library` (`tabletwall/routes/diagnostics.py:84-96`), which fails closed when uploads are disabled (`tabletwall/media.py:871-874`) — exactly the supported hotspot configuration. The physical console still shows a Field check card, but it cannot succeed there. Backups are a CLI tool with schedule/retention explicitly left open (`deploy/OPERATIONS.md:203`). For a demo, fine; for "dependable," not yet.

**R7. Avoidable polling in the physical console.** The physical page polls `/api/v3/playback` every second (`physical.js:13`, `physical.js:3440-3452`) and re-reads `/devices` plus `/api/v3/config` every five seconds (`physical.js:2491-2520`). It does not use the existing v3 controller WebSocket that already pushes `config_updated` and `playback_status`. For 4 tablets this is harmless; for a console left open all day it is unnecessary load and latency, and it contradicts the README's "controller polls nothing" statement (which describes the legacy page). Use the socket for config/roster/playback; keep a slow fallback.

---

## 4. Streamlined start → join → arrange → show → switch → recover/remove journey

The current journey requires knowing which of two consoles to use, and some steps are only possible on one of them. The target is one console, one place for each task, and no silent loss.

| Step | Today | Target |
| --- | --- | --- |
| **Start** | Enable hotspot manually, `make hotspot`, open `/controller/`; the physical console is a separate link. Logs grow, no autostart. | One supervised start (or documented boot service). The console shows server health, data paths, last backup, tablet URL/QR and the active layout/scene immediately. |
| **Join** | Type the printed URL on each tablet; copy button only. Device appears with `#N`; no QR, no name. | Scan a QR from the console; tablet registers; console offers "New tablet #N — confirm model or measure." Name it once. |
| **Identify** | Show the calibration scene (logical only), or tap the tablet to show its 5 s HUD. Physical valid walls have no badge. | "Identify" button sends a transient name/number overlay to one tablet (or all), without replacing the image. |
| **Arrange** | Logical: drag/tile/auto, or Fit+Pack. Physical: bulk arrange in UUID order or add one at a time (first two overlap). | Choose 2×2 or 1×4; order by number or drag to reorder; bodies packed edge-to-edge; fit wall if needed; preview; Apply is atomic and auto-saves the previous layout. |
| **Show** | Logical Content tab selects the image. Physical console cannot; its legacy substitute reports colour. | One Content tab with Image / Colour / Test pattern; full-wall crop preview; per-tablet slice; resolution warning; Show. |
| **Switch** | Save/recall exists but cross-kind recall can discard the physical layout; names share one namespace. | Save named layout/scene; any cross-kind switch auto-backs up; a "Recent changes" undo; names labelled logical/physical. |
| **Recover** | Physical rebind exists; no Forget; diagnostics fail closed; reconnect after sleep is unproven. | Health reflects the active plan; identify/rebind/forget in one place; client reconnects on resume; 401 shows a sign-in action; server restart restores and clients resync. |
| **Stop** | Ctrl+C; backup is a separate CLI; no blackout shortcut (black colour exists). | "Blackout" and "Stop server" from the console; verified backup reminder; logs rotated; known exit path from kiosk. |

The single most important product change is not a new feature: it is **collapsing the logical/physical split into one workflow**, with the physical measurement details shown as properties of the wall rather than as a second application.

---

## 5. UX, information architecture, controller consolidation, tablet UI and modes

### 5.1 One console, five jobs

**Proposal.** Retire the two-console split. Use the physical console's v3 API and ETag discipline as the base, because it is the more correct data path, and fold the legacy page's working still-image library into it. The target information architecture:

1. **Wall** — the stage. Image/colour/test-pattern preview, per-tablet status, drag/rotate/nudge, zoom, undo, Apply. The stage should show the selected image clipped per placement, not just coloured rectangles.
2. **Tablets** — identity and lifecycle. Name, model/measurement trust, online/wake-lock, identify, rebind, forget, add/remove from wall. This is where the missing Forget belongs.
3. **Content** — Image, Colour, Test pattern, and an **Experimental** playlist section behind an explicit flag. The current physical Content tab is playlist-only; that is backwards for the demonstrated images-only scope.
4. **Layout & size** — wall mode (units vs mm), 2×2/1×4 presets, fit/pack, gap, saved layouts, previous-layout backups. A single unit label and a single "Apply" boundary.
5. **System** — health, storage, last backup, logs, auth state, server/version, and the existing diagnostics independent of uploads.

Keep the current mobile navigation pattern (task buttons at ≤900 px) and the accessible tab/skip-link structure; the physical page already has good ARIA and reduced-motion handling (`physical.css:1997`, mobile breakpoints at `physical.css:898-914`). Do not redesign the visual language; consolidate the tasks.

### 5.2 Remove or demote

- **Remove the legacy controller from the primary path** once the unified console reaches parity (still image, colour, calibration, layout, saved scenes, rebind). Until then, make it show a hard "This is not the physical layout editor — open Wall console" banner rather than a neutral wall. Do not delete it before parity; the current physical page cannot select a still image.
- **Demote the playlist/video UI** to an Experimental section or a separate page. It is the largest block of content UI in the physical console (`physical.html:465-523`) yet the demonstrated hardware scope is images only. Keeping it prominent makes the product look like a video wall that cannot be trusted.
- **Remove the 1 Hz/5 s polling** in the physical console in favour of the existing controller socket. Keep a slow roster fallback for a dead socket.
- **Remove the logical Tile default "Keep screen shape"** or make it a secondary choice. For a seamless wall the primary action should be Fit wall to tablets + Pack with zero gap.
- **Remove the generated "Before physical <hex>" from the ordinary saved list?** No — keep it, but label it as an automatic safety copy and offer cleanup. It is doing the right thing; it is just hidden among user layouts.

### 5.3 Tablet UI and modes

The client is a canvas with a status chip and a transient HUD; that is the right minimal surface. Add, in order:

- **Transient Identify overlay.** A server command (not a scene change) draws a large name/number for ~10 s over the current image. This is how an operator matches a physical tablet to a console row without breaking the wall.
- **Install mode.** A `?setup=1` or console-triggered overlay with the device number/name, current viewport, DPR, orientation, display mode, wake-lock state and a "measure" link. Keep the existing ruler overlay (`ruler.js`) as its measuring tool, but allow a longer span.
- **Test pattern mode.** Server-generated grid at the current wall bounds, with 50 mm intervals, diagonals and a circle, so a physical wall can be checked without the shell `tools/calibration/make_grid.py` + copy + refresh dance. The built-in logical Calibration scene cannot render on a physical wall (`state._render_frame` requires image content, `state.py:416-419`), so this is a real gap, not a duplicate.
- **Image mode** (default), **Colour/Blackout** (diagnostic / end-of-day), **Experimental playlist**. Do not add a persistent mode state machine; content types plus transient commands are enough.
- **Connection/quality HUD on touch**: the existing HUD shows identity; add the last accepted revision/time and whether the plan is model or ruler based. This is the only way a person at the wall can tell whether it is stale.

**Do not** put editing controls on the wall tablet itself. The wall is an output; Guided Access/kiosk is the protection. A hidden exit gesture is an operational decision, not a UI feature.

**Mobile and accessibility.** Keep the consolidated console's phone task navigation and skip links, and test it at ~390 px width as well as desktop. The physical console's dense measurement forms are the hard part; hide advanced calibration fields behind a disclosure (the current page already does some of this) and keep the primary join/arrange/show path reachable with one thumb. The wall client's correct accessibility surface is its status/HUD text; the canvas is intentionally `aria-hidden` (`frontend/client/index.html:12-20`). Do not add an editing UI on the wall to satisfy an accessibility checklist.

---

## 6. Brainstorm: must-have, useful next, optional future

### Must-have for a dependable images-only wall (core spanning reliability)

1. **Single-console still-image control + active-scene truth** (B1). Without it the physical path cannot be operated honestly. Benefit: one place to show and verify; tradeoff: none beyond UI work. This is a refinement of an existing capability, not a new concept.
2. **Non-destructive layout switching and physical Forget** (B2, B3). Benefit: no lost arrangements, clean roster; tradeoff: an extra generated backup and one confirmation.
3. **Deterministic, edge-to-edge 2×2/1×4 arrangement** (B4). Benefit: the advertised quick path actually works; tradeoff: presets must know the wall aspect and tablet orientation. Refinement.
4. **Measurement trust visible + a built-in physical test pattern** (B5, R2). Benefit: the operator knows whether a seam is limited by a model guess or a ruler; tradeoff: more status text. Mostly refinement; the test-pattern endpoint is a small new concept.
5. **Crop/resolution preview** (R4). Benefit: catches the current 2000×745-on-four-tablets crop/upscale before the audience sees it; tradeoff: one more preview computation. Refinement.
6. **Client recovery hardening** (R3, B6). Benefit: the wall returns after sleep/network/auth expiry; tradeoff: a watchdog and a durable device credential. Refinement plus one security concept.

**New concepts vs refinements.** The genuinely new concepts are: a stable slot identity separate from the device UUID (for saved layouts that survive rebind), a durable per-device credential for an always-on wall, a transient Identify command (not a scene change), a server-generated wall-aspect test pattern, and human device names. Everything else above is a refinement of an existing capability. Resist adding new state models or a second content pipeline until these are settled.

### Useful next

- **Device names/aliases and stable labels.** Persist a human name ("Left top") separate from the leased `#N`. Benefit: identify/rebind without memorising UUIDs; tradeoff: one metadata field and a rename UI. The current number is a 15-minute lease, not a stable label (`state.py:32-35`).
- **Content library completion.** Today there is no delete/rename endpoint for managed uploads, and uploads are disabled in the supported hotspot; curated files are copied by hand. Add used-by checks, safe delete/rename, and a local operator-only upload path. Benefit: the operator can maintain the library without a shell; tradeoff: reference integrity and backup closure must be updated together. This is a refinement of the existing asset store, not a new media service.
- **QR join.** Generate the tablet URL as a QR in the console. Benefit: typing a URL on a tablet is the slowest part of join; tradeoff: a local QR library or a tiny server-side PNG. No cloud.
- **Full-image `contain` fit + explicit letterbox colour.** `geometry.fit_matrix` already supports it; expose it in the API and both renderers. Benefit: a poster can be shown whole; tradeoff: black bars and a scene background field.
- **Per-tablet "include/participate" toggle.** The physical slot already has `participating` (`physical.js:552`, `physical-stage.js:652-654`) but no UI to set it. Benefit: park a broken tablet without losing its slot; tradeoff: one checkbox and a playback exclusion interaction to clarify.
- **Atomic logical tiling.** Use one all-slots write rather than sequential `PUT /devices/{id}/placement` (`controller-stage.js:1001-1018`). Benefit: no half-tiled wall; tradeoff: a small API addition.
- **Health endpoint and log rotation.** A local `/healthz` and rotating hotspot logs. Benefit: supervision and disk safety; tradeoff: small.
- **Scheduled verified backup.** A systemd timer or `cron` wrapper around `deploy/backup.py`, with the last manifest shown in System. Benefit: recoverability; tradeoff: retention policy and disk budget.

### Optional future (only after the images-only physical path is demonstrated)

- **Mirror mode** (every tablet shows the same full image) and **independent mode** (each tablet shows a different image). Both are legitimate, but they are separate products from a continuous spanning image. Do not let them complicate the core geometry or the content model yet. They would need a per-device content assignment concept; that is a new concept, not a refinement.
- **Video/playlist on real tablets.** The code exists and is tested in desktop Chromium, but decode/suspend, iOS Safari, optical onset and mixed-model timing are unproven (`README.md:283-293`). Keep it experimental. A video feature that stutters is worse than no video for a dependable wall.
- **Optical synchronisation / clock claims.** Only after a real timed medium is demonstrated; a still image needs no shared clock.
- **Per-device slice renditions / pre-slicing.** Could improve sharpness and bandwidth on large walls, but it adds a content pipeline and invalidation surface. Measure the current global-image quality first.
- **A PWA manifest / install prompt.** Might improve Android Home Screen launch and kiosk behaviour; small, but test it on the actual browsers before claiming anything. A native app is not justified by the current evidence.

### Do not build

Multi-user accounts/RBAC, cloud sync, remote internet access, AI image generation or auto-layout guessing, a distributed/multi-worker backend, a general transcoder/DRM, a second database, or speculative canvas/WebGL optimization. None is needed for a 4–20 tablet still-image wall, and each adds a failure mode the operator cannot debug.

---

## 7. Security, deployment, performance and architecture recommendations

### Security

- **Keep the hotspot trust model explicit.** The supported trial is an unauthenticated HTTP hotspot with uploads disabled, an operator bound to loopback and a tablet route allowlist. That is acceptable for a physically controlled demo. Do not describe it as authenticated or safe on a shared network.
- **Fix the auth/tablet-ingress composition before using auth** (B6). Add `/auth/login` to the tablet allowlist or document a single-origin deployment; replace the 12-hour operator cookie with a durable device credential for wall tablets; handle 401 visibly. Re-run the negative trust matrix with app auth enabled.
- **Keep the exact-origin guard and proxy credential.** They are correctly described as CSRF/proxy isolation, not authentication (`main.py:608-634`). Do not weaken them to make a UI simpler.
- **Add conservative response headers** to the app pages: `Content-Security-Policy` with `default-src 'self'`, `frame-ancestors 'none'`, `X-Content-Type-Options: nosniff` (assets already set it), and a referrer policy. The login page already has a CSP; the app pages do not. Low risk on a LAN, cheap to add.
- **Rate-limit login and registration at the proxy** if the server is ever reachable beyond the trusted hotspot. The app bounds bodies and the roster, but does not rate-limit (`docs/AUTH.md:33`). Do not add a home-grown limiter first.
- **Per-device pairing/revocation is the right future concept for an untrusted LAN**, not a shared operator token. The current last-socket-wins model means any client that knows a UUID can take over that tablet (`main.py:3034-3059`). On a trusted hotspot this is acceptable; do not pretend it is device authentication.
- **Backups contain the database and referenced images.** Protect the destination; do not put it on a world-readable share. The backup manifest records hashes, not paths (`deploy/backup.py:22-24`).

### Deployment and operations

- **Make the supported shape start on boot.** A user systemd unit for `deploy/hotspot.py` (or a documented split for hotspot + backend + Caddy) plus NetworkManager autoconnect. The current launcher is a foreground process; a laptop reboot means a manual `make hotspot`. Add a real readiness check, not `Restart=on-failure` alone (`deploy/tablet-wall.service.example:84-85`).
- **Add `/healthz`** returning database readability, schema version, current revision, connected device count and last successful save/broadcast. Keep `/diagnostics` for storage/integrity. This is not a cloud health service.
- **Uncouple diagnostics from uploads.** `admit_library` fails closed on `uploads are disabled` (`media.py:871-874`), which makes Field check dead in the hotspot. Give diagnostics its own operator admission (loopback or the operator credential) and keep upload admission separate.
- **Rotate the hotspot logs.** `backend.log` and `caddy.log` are opened with `"a"` (`hotspot.py:252`) and never rotated. A 24/7 wall will fill the data disk. Use journald (service) or a size-capped rotating handler/logrotate.
- **Schedule and verify backups.** The backup tool is good; the schedule/retention is an open decision (`deploy/OPERATIONS.md:203`). A weekly (or daily) verified snapshot to a separate disk, with the last manifest time in System, is enough for this scale. Rehearse restore into new paths.
- **Keep the service single-process.** The runtime lock and the README are right; do not add workers or replicas against one SQLite file. If scaling beyond one host is ever needed, that is an architecture change, not a config change.

### Performance and architecture

- **Do not optimize before measuring the intended 4–20 tablet wall.** There are no performance numbers in this report. The current per-device frame fan-out, bounded writer queues and SQLite single-writer model are appropriate for this scale.
- **Use the existing v3 WebSocket in the physical console** instead of the 1 s/5 s polling (R7). This is the clearest efficiency win with no new infrastructure.
- **Consider SQLite WAL and a busy timeout** only if a real workload shows `database is locked`; the current synchronous writes from one event loop are simple and correct. Do not add a database server.
- **Serve image bytes at the resolution the wall needs.** Managed uploads cap the display rendition at 2048 (`media_limits.py:19`); curated files cap at 12 MP (`assets.py:63-64`). For a 4-tablet row of iPad Air 2 / Pixel C panels, the global image is the limiting factor. Measure perceived sharpness and consider serving the master or a larger rendition, or a per-slice pipeline, only if it matters. Do not pre-slice by default: it multiplies storage and complicates content invalidation.
- **Keep the two state shapes only as long as necessary.** The logical/physical split (`kind: logical` vs `kind: physical`) causes much of the UI and API duplication. Consolidating the operator surface does not require a framework rewrite; it requires one console and one content model. A later data-model simplification (stable slot identity separate from device UUID) is a larger change; defer it until rebind pain is measured.

---

## 8. Ranked roadmap (12 items)

Effort is relative only: **S** small, **M** medium, **L** large. No calendar promises. Dependencies are real ordering constraints.

| # | Item | Depends on | Effort | Observable acceptance criteria |
| --- | --- | --- | --- | --- |
| 1 | **Single-console still-image parity** — add scene to v3 config; Image/Colour controls, active-content status and crop preview in the physical console; legacy page detects physical and redirects/banners | — | M | On a physical wall, choose an image in one console; the console names the active asset and shows its crop; tablets update; the legacy page cannot silently show a different scene. |
| 2 | **Non-destructive switching + physical Forget** — auto-backup the current layout before any logical↔physical switch; split roster delete from placement removal; two-step Forget in physical | 1 (for the UI home) | S | Recall logical from physical and back; the previous arrangement is recoverable under a generated name. An offline device can be forgotten from the physical console without removing another device's slot. |
| 3 | **Deterministic 2×2/1×4 arrangement** — order by display number/label; 2×2 and 1×4 presets; edge-to-edge fit/pack; fix first-two-add overlap; warn on uncovered bands | 1 | M | Four connected tablets arrange in number order; a 2×2 or 1×4 with gap 0 has no uncovered wall band and no shape-mismatch warning; two manual adds never overlap. |
| 4 | **Measurement trust + physical test pattern + resolution warning** — confirm model inference; show model/ruler/unknown and ±uncertainty per tablet; generate a wall-aspect grid; show source px per tablet | 1, 3 | M | A model-derived plan is clearly labelled approximate with its uncertainty; a ruler plan is labelled measured; the test pattern appears without a shell command; the current 2000 px / four-tablet case produces a visible resolution warning. |
| 5 | **Client and auth recovery hardening** — visibility/pageshow/online reconnect; heartbeat/stale-socket watchdog; 401 shows a sign-in action; durable device credential; add login route to the tablet allowlist or document the single-origin choice | — | M | Hide a tablet, drop its socket/server, restore connectivity: it re-registers and shows the correct slice within 10 s. An expired auth session produces a visible sign-in path, not an indefinite "Offline · retrying". |
| 6 | **Health and diagnostics** — `/healthz`; independent diagnostics admission; active-plan status per device; log rotation | — | S/M | With uploads disabled, Field check works and reports DB/storage/backup. `/healthz` reports DB readability, revision and device counts. Hotspot logs rotate. The health summary reflects the active pinned slot, not only the latest profile. |
| 7 | **Supervised startup + scheduled backup** — boot service for hotspot + backend/Caddy; NetworkManager autoconnect; verified backup timer; last manifest in System | 6 | M | Reboot the host; the wall returns without a manual command. The nightly/weekly backup verifies and its timestamp is visible. |
| 8 | **Wall preview + `contain` fit** — render the selected image over the placement map; per-device crop badge; expose `contain` with a letterbox colour | 1 | M | The controller preview matches the tablets' slices; `contain` shows the whole image with a chosen background; the crop badge matches the arithmetic. |
| 9 | **Content library completion** — used-by/reference checks, safe delete/rename; a local operator-only upload path; keep backup closure correct | 1 | M | A referenced image cannot be deleted without warning; an unreferenced one can; uploads work only on the operator path; backup/verify still passes after a library change. |
| 10 | **Identity: names, stable labels, Identify, QR** — persist a human name; Identify overlay; QR for the tablet URL; stable number for installed slots | 2 | S/M | Rename a tablet and see it after restart; Identify flashes the right physical screen; QR opens the client; an installed tablet keeps its label through a server restart and a normal reconnect. |
| 11 | **Saved-layout healing / stable slot identity** — rewrite saved snapshots on rebind, or separate slot identity from device UUID | 10 | M/L | After rebind, recall an old saved layout and the tablet lands in the intended slot (or an explicit Heal action does it with a preview). |
| 12 | **Images-only real-device validation + 2 h soak** — execute §9, record signed evidence | 1–6 | M | The checklist in §9 passes on the actual tablets; failures and uncertainty are recorded; no video/optical claim is made. |

**Sequencing.** Items 1–5 are the real "dependable images-only wall" block. Items 6–7 make it operable unattended. Items 8–11 are quality/lifecycle refinements. Video, mirror/independent modes and optical work stay after 12.

---

## 9. Images-only next demonstration and real-device validation checklist

**Goal:** prove the physical spanning path, not the experimental video path. Use the actual 2 iPads + 2 Pixel C (or the real set), in 2×2, with the existing measured models. Preserve the current saved logical 4×1 wall; do not overwrite it.

**Preparation (before touching the live wall):**

1. Take a verified backup of the current database, curated assets and media (`deploy/backup.py backup` then `verify`). Record the application SHA.
2. Save the current logical 4×1 arrangement under a named layout (do not rely only on the automatic "Before physical" copy).
3. Confirm each tablet's model in the physical console. If the model is auto-detected, explicitly confirm it; if the device is not the measured model, stop and measure it. Do not proceed on an unconfirmed model.
4. Use a known image with the wall's aspect, or accept the documented crop. For a 2×2 of four 4:3 tablets, the wall should be fitted to the bodies, not forced into a 2:1 wall.
5. If possible, measure one tablet with a full-span ruler (or several spans) and record mm/CSS and uncertainty. If not possible, run the model-approximate trial and label the result approximate; do not claim 2 mm.

**Run:**

6. Start the hotspot/console fresh. Verify the tablet URL/QR and that the operator is loopback-only.
7. Join all four tablets; record `#N`, full id, model, OS/browser, viewport, DPR, orientation, display mode and wake-lock state for each.
8. Identify each tablet with the Identify action (or the calibration scene if Identify is not built yet); map physical position left-to-right/top-to-bottom.
9. Arrange 2×2: order by number, place bodies edge-to-edge, gap 0, fit wall to tablets. Apply. Confirm the previous layout was auto-saved.
10. Show the generated test pattern for the resulting bounds. Photograph every seam; measure a 50 mm horizontal and vertical interval on each screen; record the ruler error and the estimate's uncertainty.
11. Replace the test pattern with a real poster/image. Check the crop at top/bottom and the source-pixel shortfall. Record whether the image is soft at the intended viewing distance.
12. Restart the server while all tablets stay open. Measure how long until every tablet shows the correct slice; record any tablet that needs a reload.
13. Toggle Wi-Fi/airplane mode on one tablet for 10 s, then restore. Measure recovery; repeat at least 5 times (the formal gate asks for 20 network trials).
14. Lock/sleep one tablet (OS Auto-Lock or the lock button), wake it, and check whether the image and socket recover without a reload. If they do not, record the failure; it is a finding, not a demo failure.
15. Use Identify, Remove from wall, Forget and Rebind in that order. Confirm a rebind preserves the slot, measurements and number, and that saved layouts are understood to be snapshots.
16. Recall the saved logical 4×1 and then the physical 2×2. Confirm the switch is reversible and no arrangement is lost.
17. Run a 2-hour still-image soak with all four tablets. Record CPU, memory, temperature, disk, log growth, disconnects and any stale frame. Do not run video.

**Pass criteria (images only):**

- All four tablets show the correct quadrant of one continuous image; no uncovered band, no upside-down or swapped slice.
- Seam displacement plus measurement uncertainty is at or below 2 mm, or the actual value is recorded and the 2 mm target is marked not met.
- Server restart: every tablet recovers within 10 s without a manual reload (or the failure is recorded).
- Network restore: content is correct within 10 s; 20/20 trials recorded for the formal gate.
- Sleep/wake: the page either recovers or the failure mode and required manual action are documented.
- Two-hour soak: no unplanned stalls, lost members, stale paints or unexplained restarts.
- No claim of video, optical sync, physical millimetre accuracy beyond the measured uncertainty, or unattended readiness.

**Do not** use the physical demonstration to promote the eight MISSING hardware gates. Record the evidence per `docs/validation/EVIDENCE-SCHEMA.md`; a software pass is not a hardware gate.

---

## 10. Top five actions, plainly

1. **Make the physical console able to show and verify a still image.** Put the scene in the v3 config, add the image/colour/test-pattern controls and an active-content card, and stop the legacy page from silently showing a different wall.
2. **Make switching safe and finish the device lifecycle.** Auto-save the current layout before any logical↔physical switch; allow Forget in physical; keep the "cannot forget an online device" rule.
3. **Make 2×2/1×4 deterministic and edge-to-edge.** Order by number/label, add presets, use Fit+Pack with zero gap for a seamless wall, fix the first-two-add overlap, and warn when the tiling leaves uncovered image bands.
4. **Make measurement trust and crop/resolution visible.** Confirm model detection, show model vs ruler and ±uncertainty, add a wall-aspect test pattern, and show the source-pixels-per-tablet/crop before the audience sees it.
5. **Harden recovery and operations, then run the real-device images-only checklist.** Reconnect on resume, visible 401 handling/durable device credential, `/healthz`, independent diagnostics, log rotation, supervised boot and scheduled verified backup.

**What not to build yet:** video/playlist expansion or optical sync; mirror/independent modes; cloud/remote access, multi-user roles or RBAC; distributed/multi-worker state; AI generation or automatic layout guessing; a general transcoder/DRM; per-slice rendering or a framework rewrite; more built-in tablet models as a substitute for confirmation. None of these fixes the fact that the physical console cannot yet select and verify a static image on its own.

---

## 11. Checks run, what remains unverified, cleanup

### Checks actually run by me

- `uv run pytest -q tests/test_v3.py tests/test_tablet_models.py tests/test_wall_sizing.py tests/test_geometry.py tests/test_displays.py` → **52 passed**, 1 deprecation warning, 0.64 s. This covers the v3 physical negotiation/plan, models, sizing, geometry fixtures and display revisions. It does not cover the UI or hardware.
- `node tests/physical_sizing.test.js` → passed.
- `node --test tests/*.test.js` → exit 0; all **9 Node test files** reported passed (`client_image`, `client_view`, `client_wake_lock`, `controller_modules`, `controller_playback_errors`, `controller_sizing`, `controller_url`, `physical_calibration`, `physical_sizing`).
- **[Probe]** throwaway in-process `TestClient` with a temporary DB/assets/media under `/tmp/opencode`: confirmed `GET /api/v3/config` has no `scene`; `GET /wall` is 409 in physical mode; `PUT /scene` returns a colour scene while the live scene is an image; `DELETE /devices/{id}` is 409 in physical mode; a logical→physical apply creates a `Before physical …` backup. This is the strongest direct evidence for B1–B3.
- `git status --porcelain` at the start and end: empty. No source edits, no commits, no live database access.

I did **not** rerun the parent's full 1177-test suite, launch a server, start a browser, or perform a UI observation. This report is source/test/probe review only. The parent's counts are prior evidence, not mine.

### What remains unverified

- Physical seam accuracy, the 3 mm model uncertainty, the 2 mm acceptance target, and the Pixel C rotation mapping on glass.
- Whether other iPad models share the 768×1024 @2 signature and would be misassigned (B5); needs a device inventory check.
- Safari/Chrome tab/standalone inset behaviour and the model centring guess (B5).
- Real OS sleep/wake and reconnect after freeze; the client has no resume probe (R3).
- Auth expiry and the tablet login path on real browsers; the allowlist/login mismatch is source-confirmed, but the user-visible failure is not observed on hardware.
- Perceived image sharpness for a 2000×745 image across four tablets (iPad/Pixel C mix); the pixel arithmetic is certain, the visual judgment is not.
- 15–20 tablet hotspot capacity, sustained CPU/temperature, log growth, and any performance claim.
- Video, optical onset, audio, mixed-model decode — not assessed as working.

### Cleanup status

- No servers, browsers or background processes were started.
- No live app data, database, services, firewall or network settings were changed.
- The throwaway probe and its temporary files are under `/tmp/opencode/deepseek-review` and were removed after the run.
- The source working tree is **clean** at `0ff56e3`; no files in the checkout were modified.
- Other model report files were not read or overwritten.

### Report path

`/var/home/oak/.local/share/tablet-wall-ai/assessments/2026-11-01/deepseek-v4.1-flash.md`

