# Execution log: Stages 0-3

Scope: P0, R1, R2 and R3 of `ROADMAP.md` (an untracked planning artifact,
not part of this checkout). Hardware-only claims
(physical iPad/Android, optical synchronization, real suspend, iOS Safari
decode) stay explicit gaps; the roadmap permits implementing a ticket without
claiming those results.

## Current state

- Stage 0: complete. Browser evidence and explicit missing hardware rows.
- Stage 1: complete. Upload/show, admission, backup and restore-to-render.
- Stage 2: complete for the software scope. Geometry, schema 2, v3 render,
  bounded writers, calibration API and the physical editor are verified.
- Stage 3: software slice complete. Clock sampling, one leased hard-cut
  session, client preparation/commit, controller controls and two rendered
  cuts are verified. The 100-cut and optical gates remain open.

## Stage 0 plan (P0)

Goal: close P0 with a reproducible software baseline plus explicit passed or
missing hardware rows.

1. Rerun the existing checks in isolation: `pytest`, the node client suite,
   `make sim`, and the disposable browser runner. Record exact counts.
2. Rectangle evidence. For every independent client, measure canvas bounding
   rectangle, backing store, viewport, DPR and render mode in tab mode; enter
   fullscreen through the existing `#fs-toggle`, measure again, then exit.
   Record standalone as MISSING with the reason (desktop Chromium has no
   installed web-app display mode).
3. Sleep clock. A real tablet suspend cannot be produced here. Record MISSING
   with the exact required hardware. Do not substitute a frozen-page timer
   experiment for sleep evidence.
4. MP4 probe. Generate a short H.264 baseline MP4 with the installed ffmpeg,
   load it in the installed desktop Chromium, and measure metadata,
   `readyState`, muted play, seek, CSS clip, quarter-turn transform and loop
   restart gap. Label it decode evidence for this engine only; it is not iOS
   Safari and does not prove HTTP range or network preload.
5. Add a `p0` report section with one row per experiment: `PASS`, `FAIL`, or
   `MISSING` with a reason. Update `simulator/README.md` with the same matrix.
6. Run every check again and commit the unit.

Acceptance: all automated checks green; every P0 row is either PASS with
recorded evidence or MISSING with a named prerequisite; the browser run leaves
no temporary data or child process.

Risks: fullscreen may be refused by headless Chromium (record the exact
refusal as MISSING, not a fake pass); a data-URL MP4 does not exercise HTTP
preload or ranges; new browser checks must not make the existing runner flaky.

## Stage 0 (P0): complete

- Runner: 67/67 checks, `p0.status = PASS_WITH_MISSING_HARDWARE`.
- Rectangle evidence: tab and fullscreen recorded for the DPR-1.25 client;
  standalone is MISSING.
- MP4: a generated 2 s H.264 Constrained Baseline fixture served over a
  temporary range-capable loopback origin decoded, played muted, advanced to
  0.41 s, seeked to 1.2 s, passed clip and quarter-turn screenshot checks, and
  wrapped with a 16.6 ms rAF-sampled gap.
- Missing rows: standalone launch, tablet sleep, host suspend, physical iPad,
  physical Android, optical capture, two-origin ingress.
- `make test` 525 passed; node 25 passed; `make sim` 1075 checks; browser
  safety tests 16 passed.
- Commits: `6834949` (T2), `41140db` (P0 runner and README).

## Stage 1 plan (R1: upload and show)

T2 is complete in `6834949`. The remaining units are T3, T4, T5 and R1.1.

### Decisions (revised after advisor review)

- **Schema 1**: every persistence entry point goes through one schema gate. The
  gate coordinates with `BEGIN IMMEDIATE`, re-reads `user_version`, writes a
  durable uniquely named pre-migration backup with SQLite's backup API before
  any DDL, and commits DDL plus the version bump together. A masquerading
  empty file, an existing file missing required tables, a future version or a
  damaged active wall row refuses startup. Damaged saved snapshots stay
  listable/tolerant as today. Tests cover two concurrent initializers, a
  failed backup, a failed DDL, reopen after interruption, and direct calls
  with no lifespan.
- **Media directory**: `TABLET_WALL_MEDIA_DIR`, default `./media`, resolved at
  call time. `objects/<aa>/<sha256>` holds immutable bytes; `staging/` holds
  uncommitted jobs; `.store.lock` is the stable lock inode.
- **Admission**: `TABLET_WALL_UPLOAD_MODE` is `disabled` (default),
  `loopback`, or `proxy`; unknown values deny. `proxy` requires an explicit
  `TABLET_WALL_OPERATOR_CREDENTIAL` and exactly one
  `X-Tablet-Wall-Operator` header, compared with `compare_digest`. Uploads in
  both enabled modes require exactly one non-`null` Origin equal to the
  configured operator origin. `loopback` additionally requires the transport
  peer to be loopback, a loopback bind, proxy-header interpretation disabled,
  and refuses `Forwarded`/`X-Forwarded-*`. The origin guard's "unset means
  allow" result is never sufficient for upload admission.
- **Library reads**: `GET /media` is operator-only. In `proxy` mode the
  credential comes from Caddy on every upstream request, including GET. In
  `loopback` mode a loopback peer may read without Origin (browsers omit it
  on same-origin GET) but uploads still require Origin. Neither path is
  public on the tablet listener.
- **Ingest route**: `POST /uploads` with a single JPEG or PNG raw body,
  streamed to an exclusive staging file. Capacity and quota are reserved
  before the body is consumed; streamed bytes are enforced regardless of
  `Content-Length`; one active worker, two bounded waiters, a receive
  deadline, a 30 s processing deadline, and disconnect cleanup. The
  synchronous `201` returns a ready descriptor; no durable job API. The
  browser's upload progress becomes indeterminate once transmission ends.
- **Worker**: `tabletwall/media_worker.py` validates, applies EXIF transforms,
  normalizes to sRGB/opaque, strips metadata, and writes a master plus
  2048/1024/256 renditions. Both the 4096-long-edge and 12 MP/10 MiB ceilings
  apply. Memory (512 MiB start), CPU, output count/bytes and result size are
  bounded. A subprocess is terminable isolation, not a filesystem sandbox;
  the worker sees only server-owned paths and the report says so.
- **Publication**: fsync each complete object, publish without replacing an
  existing immutable object (`link`/`O_EXCL` or hash-verified reuse), fsync
  the object directory, then insert all ready relationships in one
  transaction. Duplicate normalization reuses matching objects and does not
  double-charge quota. Before commit, a failure creates no ready identity;
  after commit, a retry rediscovers and reuses the same objects. Destructive
  GC is deferred; stale-job cleanup removes only known staging files.
- **Serving and acceptance**: `/assets/{id}` checks managed objects first and
  falls back to curated bytes. `put_scene()` accepts a managed display object
  without scanning the curated library. An explicit integrity-verification
  operation re-hashes ready objects.
- **Controller**: a new upload card with a file picker, upload progress,
  processing/ready/failed states, error text, a media library with
  thumbnails, and a "Show on wall" action that reuses the existing scene PUT.
- **Backup manifest 2**: scene-root references and transitive object closure
  are separate manifest fields. Closure is computed from the captured
  database across curated and managed storage, including master/rendition
  objects and shared hashes. Omitted library rows are marked unavailable in
  every relationship, only inside the captured database and before its final
  digest; retained shared objects stay usable. Manifest 1 keeps its own
  validation and restore path. The store lock inode is identical for backup
  (shared) and future deletion (exclusive); immutable publication does not
  hold it for the whole copy. Restore targets the database, asset dir and
  media dir, refuses live-configured targets, and proves the restored image by
  rendering it through a real client.


### Units

1. **T3a schema 1** (`tabletwall/persist.py`, tests): version check, migration
   backup, additive media tables, damaged/future refusal.
2. **T3b admission** (`main.py`, `tabletwall/media.py`, `deploy/hotspot.Caddyfile`,
   tests): modes, credential, loopback and forwarded-header rules, Caddy
   allowlist/credential rules.
3. **T4a media store and worker** (`tabletwall/media.py`,
   `tabletwall/media_worker.py`, tests): staging, quota, worker limits,
   normalization matrix (EXIF, alpha, CMYK/ICC failure, animation, malformed),
   object publication, indexed fetch, library.
4. **T4b HTTP and controller** (`main.py`, `frontend/controller/*`, tests):
   streamed upload, descriptor, `/assets/{id}` fallback, `GET /media`, upload
   panel and show flow.
5. **T5 backup** (`deploy/backup.py`, tests): manifest 2, media closure, lock,
   omitted marking, restore proof with a real image fetch.
6. **R1.1 evidence**: malicious-input and ingress-refusal matrix, crash
   consistency, and a rendered upload-preview-show flow in the isolated
   browser runner. Record physical upright-photo evidence as MISSING.

### Acceptance

- Old schema-0 fixtures open, migrate once, and keep every document byte
  compatible; a future version and a damaged wall row refuse startup.
- Every upload outcome is explicit; a failed worker leaves no ready row and
  no object readable under a new ID; an interrupted publication leaves at
  most an orphan file that is not listed.
- A phone-style JPEG with EXIF orientation shows upright, with metadata
  stripped, through a real client at the expected pixels.
- Direct, unauthenticated, forged-Origin, forged-forwarding and wrong-credential
  uploads are refused in each mode.
- Backup manifest 1 restores unchanged; manifest 2 restores a referenced
  upload into a new database/media pair, and an isolated app serves exactly
  those bytes.
- `pytest`, node, simulator, browser runner and backup tests pass.

### Risks

- Schema migration must not run implicitly on a read from an old file without
  the backup. All migration goes through `ensure_schema`.
- `media_worker` must not follow paths outside its job directory and must not
  be able to exhaust host memory.
- Backup closure must use the captured database, not live state, and must not
  claim omitted bytes as ready.

## Stage 1 (R1): complete

- T2: commit `6834949`. Contract in `PROTOCOL.md`.
- T3: schema gate `2c99e61`, admission/Caddy `43e2e00`.
- T4: store/worker `a7fe721`, HTTP/controller `43e2e00`/`4b0806f`,
  phone/quota/timeout matrix `183fb6b`.
- T5: manifest 2 `583b405`, restore-to-render `78f6b94`.
- R1.1 evidence:
  - `pytest` 591 passed; node 25 passed; simulator 1075 checks; browser
    84/84 checks with `p0.status = PASS_WITH_MISSING_HARDWARE`.
  - Real Caddy two-origin test: tablet listener refuses `/uploads` and
    `/media` even with a forged internal header; the authenticated operator
    listener overwrites a client credential, requires the exact Origin, and
    the published bytes are readable on the tablet listener.
  - Upload→show: three real clients paint the uploaded colour; a rejected
    text upload changes nothing; a manifest 2 backup restored into new
    targets paints the restored image in a fourth real client.
- Worker memory measurements with `LC_ALL=C` and the 512 MiB limit:
  6000x4000 JPEG peak 225 MiB / 1.7 s; 8000x4000 RGB PNG 245 MiB / 2.1 s;
  8000x4000 RGBA PNG 430 MiB / 2.4 s. All succeed; 32 MP is the admission
  ceiling. The C locale is required (the default locale maps a large archive
  into the worker budget).
- Known limits: physical upright-photo evidence is MISSING (no tablet);
  uploads are disabled by default; destructive GC is deferred; the backup
  CLI's manifest 2 media closure does not include unused uploads by design.

## Stage 2 plan (R2: physical calibration and minimum editor)

### Decisions

- **Protocol 3** is the physical/timed contract; v1 and v2 remain byte
  compatible. v3 device frames are `render`; v3 controller snapshots carry
  the physical wall, display profiles and calibrations. `SERVER_CAPS` for v3
  are `calibration`, `image`, `physical` (clock/playlist join in R3).
- **Schema 2** uses additive tables plus a **read-time legacy adapter**:
  legacy logical documents stay byte-for-byte in place and are projected into
  a runtime envelope; new physical writes use
  `layout:{schema:2,kind:"physical",data:...}` and
  `scene:{schema:2,kind:"static",content:...}`. This deliberately narrows the
  roadmap's eager rewrite: it preserves damaged saved-row bytes and avoids an
  irreversible transformation. The version bump is transactional after a
  verified backup; future versions and damaged required records still refuse.
  Display profiles and calibration revisions are immutable rows. The advisor
  requested this change and the autonomy grant covers it.
- **Physical layout**: bounds in millimetres, a slot per device with
  `center_x_mm`, `center_y_mm`, `mount_angle`, `nudge_x_mm`, `nudge_y_mm`,
  `profile_revision`, `calibration_revision` and `participating`.
  Measurements are native-edge millimetres; bezels are nonnegative; body
  dimensions are derived, never stored as a second source of truth.
- **Transform ownership**: the server sends `G_N_to_P` (normalized source to
  active-panel millimetres) and the active-panel clip. The client owns its
  calibrated `U_C_to_P`, composes `backingScale * inverse(U_C_to_P) *
  G_N_to_P * scale(1/sourceW,1/sourceH)`, and draws the source pixels. The
  target static size remains a single transformed canvas; video (R4) will
  compose the same matrix into CSS.
- **Calibration matching**: a calibration records its viewport signature
  (CSS width/height, DPR, orientation, mode, quarter turn, panel offset,
  mm/CSS, anchor). A device receives a plan only when its reported viewport
  matches a current calibration for its profile revision; otherwise the
  render frame carries `plan: null`, `calibration.status:
  "needs_calibration"` and a neutral still. Resize, rotation or mode change
  invalidates the match immediately.
- **API**: `GET /api/v3/config` (displays, calibrations, active layout),
  `PUT /api/v3/displays/{id}` and `PUT /api/v3/calibrations/{id}` (immutable
  revisions), `PUT /api/v3/layout` (atomic batch, required `If-Match`,
  `428` missing, `412` stale, `409` semantic conflict). While a physical
  layout is active, legacy layout/placement mutations return `409 Upgrade
  controller`; content/scene and colour writes stay available where their
  v2 semantics still apply.
- **Ordered writer**: one bounded FIFO per socket for every protocol version
  (64 frames / 1 MiB / 5 s send timeout), no coalescing in R2. Coalescing
  moves to R3 with playback snapshots.
  The welcome and initial snapshot are queued first and the socket is
  published to broadcasts only after they are enqueued. Queue overflow or a
  sustained slow send closes that connection; cleanup checks writer
  ownership so an old writer cannot drop its replacement.
- **Geometry module**: column-vector matrices, clockwise positive rotation
  in Y-down space, hand-derived fixtures for quarter turns, asymmetric
  bezels, offsets, fractional DPR and 180-degree-only changes. The Python
  module and a new `frontend/client/view.js` are independent
  implementations; a fixture file is shared as data, not code.
- **Editor**: physical layout only, local draft, select/drag with a movement
  threshold and pointer capture, 90-degree rotate, nudge buttons, numeric
  inspector, undo/redo, Escape cancel, and one atomic Apply with the layout
  ETag. A conflict preserves the draft. Curated/uploaded media selection is
  unchanged. Keyboard and single-pointer alternatives are required; drag is
  not the only path. Group moves, snapping, rich crop overlays and elaborate
  Identify are explicitly deferred by this T8 scope amendment.
- **Legacy conversion** is an explicit operator action with a scale and
  measurements, a preview, and a new physical layout. It never relabels
  legacy units as millimetres.

### Units

1. **T6a schema 2** (`tabletwall/persist.py`, tests): envelope migration,
   display/calibration tables, refusal cases, rollback fixtures.
2. **T6b writer** (`tabletwall/writer.py`, `hub.py`, `main.py`, tests):
   bounded queue, coalescing, ownership cleanup, slow-reader isolation.
3. **T6c protocol/state** (`tabletwall/protocol.py`, `state.py`, `main.py`,
   tests): v3 negotiation, render projection, calibration matching,
   legacy fences, controller snapshot.
4. **T7a geometry** (`tabletwall/geometry.py`, `tests/fixtures/geometry/`,
   Python tests): matrices, fit, panel plans, clip, quarter turns.
5. **T7b client view** (`frontend/client/view.js`, `client.js`,
   `tests/client_view.test.js`): compose the same fixtures, draw v3 and leave
   v2 untouched.
6. **T7c calibration API/UI** (`main.py`, controller files): profiles,
   revisions, ETags, numeric panel.
7. **T8 editor** (controller files): draft, drag/rotate/nudge/numeric,
   Apply/Cancel/undo, accessibility and desktop/mobile inspection.
8. **R2.1 evidence**: compatibility matrix, rotation/asymmetric/fractional
   fixtures, stale viewport, editor flows, and a real browser run. Physical
   seam evidence stays MISSING without hardware.

### Acceptance

- v1/v2 frames and tests unchanged; v3 welcome/render ordering deterministic.
- A calibrated device with asymmetric bezels and a 90/180/270 mount receives
  the hand-derived matrix and its canvas paints the expected pixel at the
  expected location; an uncalibrated or stale device gets no physical claim.
- Schema 1 opens, migrates once, keeps logical behaviour, and a future
  version/damaged required record refuses startup.
- Legacy layout mutations are fenced while a physical layout is active.
- Editor: cancel writes nothing, Apply is atomic, a stale ETag preserves the
  draft, and pointer/keyboard/single-pointer paths all work.
- `pytest`, node, simulator, browser and backup suites pass.

## Stage 2 advisor review

Reviewed by Sol. Verdict: revise. Required changes applied above: pinned v3
render contract and lineage, read-time schema adapter, one writer for all
sockets without R2 coalescing, full legacy fence, and a narrower but explicit
editor scope. The advisor's required evidence list is the R2 gate; physical
seam and mixed-model accuracy remain MISSING without hardware.

## Stage 2 progress

- Geometry fixtures and an independent JS implementation: `b03da72`.
- Schema 2, display/calibration revisions, v3 render plans, bounded writers:
  `01a8462`.
- Client physical render path: `54ea5ef`.
- Browser physical plan (mount 180, coded marker, clip, stale viewport):
  `e68e337`, `b8007bc`; 93/93 checks.
- Physical layout save/recall/delete: `c0d9d80`.
- Remaining: the accessible physical editor page and its integration link,
  plus a rendered editor flow. The backend and the render path are verified.

## Stage 3 plan (R3: clock, leased preparation, hard-cut stills)

Goal: deliver the software half of R3 with an explicit optical gap.

1. **Clock** (`tabletwall/clock.py`, `tests/test_clock.py`): monotonic
   milliseconds, epoch, BOOTTIME-minus-MONOTONIC suspend detection, and the
   NTP four-timestamp estimate with RTT/uncertainty validation. The client
   runs the same estimator and reports the chosen sample; the server keeps a
   bounded, fresh record per connection. Suspend or a restart changes the
   epoch and invalidates every preparation.
2. **Playback state** (`tabletwall/playback.py`, tests): one ephemeral
   session per wall with `session_id`, `version`, `generation`, `clock_epoch`,
   state, playlist revision/occurrence, current/next preparation, frozen
   online cohort, anchor, hold flag, missed members and degradation records.
   A preparation names the exact session/version/occurrence/asset/geometry,
   its deadline and lease. Higher versions supersede every different pending
   preparation. A restart has no session and leaves the static wall.
3. **Playlist payload**: one durable active playlist in `schema_meta` as a
   versioned JSON document (max 64 display-object IDs, 1 s to 10 min dwell,
   loop). This is the roadmap's initial "no separate reusable playlist
   table" choice.
4. **Protocol v3**: `clock_bootstrap`, `clock_sample`, `clock_result`,
   `prepare`, `ready`, `commit`, `cancel`, and `playback_status`. A ready
   lease names session/version/preparation/occurrence, connection, viewport
   mapping revision, lease expiry and media readiness. The server rechecks
   current ownership, lease and evidence at commit.
5. **Scheduling**: prepare the next occurrence immediately after a cut;
   freeze the online cohort at start; commit early when leases are valid;
   otherwise hold at most `min(dwell/2, 5 s)` and record every missed member.
   Re-anchor after a hold so the next item gets its full dwell. Pause freezes
   at its effective time; next/previous create a new version.
6. **Client**: clock sampling and offset, preparation without painting,
   ready after decode, commit at the compensated effective time with a
   requestAnimationFrame recheck, hold the last still on a miss, and drop
   every timer/callback from a superseded version.
7. **Controller**: a playback panel over the physical editor page (or an
   existing-controller card): playlist items, dwell, loop, Start, Pause,
   Stop, Next, Previous, and the observed/missed cohort. No optical claim.
8. **Evidence**: deterministic stale/lease/queue/restart tests; a real
   browser run with two calibrated clients and at least 10 hard cuts,
   reporting software onset delta, missed members and degradation windows
   separately from the MISSING optical gate.

### Acceptance

- A stale lease, wrong connection, wrong version, expired clock or changed
  calibration cannot commit.
- A superseded preparation never paints or reports ready.
- Restart/clock epoch advances cancel all pending work and leave the static
  wall; no old monotonic anchor survives.
- Pause/next/previous/stop and loop boundaries are deterministic in model
  tests.
- Two real clients paint the same hard-cut items; the report labels the
  measured skew as software, not optical.
- Existing suites and the R1/R2 browser runs still pass.

### Risks

- The full optical gate (100 cuts, 100/250 ms) needs the named hardware and
  remains MISSING.
- Timer accuracy on a suspended tablet cannot be inferred from desktop
  Chromium; suspend behavior stays a hardware gap.
- Playlist durability in `schema_meta` is intentionally one active list.

## Stage 3 advisor review

Pending.


## Final verification record

- Python: 635 passed.
- Node client: 25 passed.
- Node view: 8 passed.
- Simulator: 23 scenarios, 1075 checks, 18 self-tests.
- Isolated browser: 102/102 checks, including P0, R1 upload/restore, R2
  physical editor and R3 two hard cuts with Pause/Stop from the controller.
- Real Caddy ingress: tablet listener refuses upload/library even with a
  forged credential; the authenticated operator listener overwrites a client
  credential and requires the exact Origin.
- Memory measurements for the 512 MiB worker with `LC_ALL=C`: 6000x4000 JPEG
  225 MiB/1.7 s, 8000x4000 RGB PNG 245 MiB/2.1 s, 8000x4000 RGBA PNG
  430 MiB/2.4 s. All succeed; 32 MP is the admission ceiling.

## Remaining limitations and next actions

- R3's optical gate (100 cuts, p95 <=100 ms / max <=250 ms) is **not**
  measured. The browser run observes two software cuts only; no camera,
  physical suspend, iOS decoder or mixed-model timing was available.
- R2 physical seam continuity and mixed-model calibration are **MISSING**
  without hardware. The four quarter-turn fixtures are checked in Python/JS;
  the browser exercises mount 180 only.
- Strict required-slot playback, coalescing and group editor moves are
  deferred with explicit scope amendments.
- Uploads remain disabled by default. Destructive media GC is deferred.
- A restart restores static content and the saved playlist; no playback
  session, lease or monotonic anchor survives.
- Next implementation steps: a 100-cut software/optical harness, strict slots,
  causal coalescing, suspend injection in a browser, and the physical seam
  procedure.

## Stage 3 closeout (2026-10-24)

Runner: `simulator/browser.run --cuts 100 --suspend`, 129/129 checks.

- 100 of 100 requested cuts committed and painted, three calibrated clients,
  0 failed events, 0 degradation windows, 0 holds.
- Software onset delta (whole show, failed events would be unbounded):
  p50 0.2 ms, p95 1.0 ms, max 1.3 ms. Healthy subset identical.
- Lateness against the planned effective time is about -39.8 ms p50 on all
  three members. That is a browser draw timestamp before the planned instant,
  not optical evidence.
- Suspend injection: the server clock epoch changed, both clients stopped,
  readiness renewals stopped, no cancelled preparation committed or painted,
  and the persisted static scene survived. Control step under the threshold
  changed nothing.
- Optical gate: MISSING. No camera, panel capture, or physical suspend.
- One product gap remains until R4: after a clock-epoch abort the screens keep
  the last committed still until a reload or a new wall frame. The R4 abort
  path sends `stopped` then the persisted wall, and the client restores it.

Field fix committed as `01123e5`: a denied wake lock is reported without a
console warning, and the runner matches a heartbeat frame by type because the
field work added `wake_lock` to it.

## Stage 5 browser verification (2026-10-24)

Temporary server, loopback admission, no operator data. Real Chromium.

- `GET /diagnostics` returned 200 with media quota/used/free/reserve/objects/
  assets/orphans, db schema 3 and size, backup age, clients online/total, and
  the wake-lock state counts.
- A client registered with `wake_lock: "denied"` after reconnecting on a page
  where the permission was refused.
- Rebind with the operator Origin moved the placement and number from an
  offline device to a new registration, removed the old identity, closed the
  new tablet's socket, and the tablet reconnected as `#1` online.
- A write without the operator Origin answered 403.
- Screenshot: `/tmp/opencode/stages35-r5-browser/client-after-rebind.png`.
- Missing: an operator surface for diagnostics/rebind, and every physical
  gate (iPad/Android, real suspend, iOS decode, two-hour soak).

## Stages 3-5 completion (2026-10-24)

### R3 corrections

The Sol review reproduced five model defects in the committed R3 code. All
five are fixed and covered by tests:

- the next cut now uses the committed item's dwell (5/11/17 s gives 2/7/18 s);
- `Session.index` stays on the active occurrence, so Next no longer skips one;
- a non-looping last item reaches `final` after its cut, not `stopped` before it;
- leases are checked against the actual accepted cut and the current time, so
  a lease that expired before a hold cannot commit;
- strict start includes every participating slot, including offline members;
- ready reports must match the preparation occurrence, connection, calibration
  revision and a fresh clock, and a still must be decoded;
- pause resumes the displayed item; stop and abort restore the persisted render.

Evidence: 100/100 software cuts, three calibrated clients, 0 failed events,
0 degradation windows. The isolated run reported p50/p95/max
0.2/0.9/1.1 ms. A later run that overlapped the independent review had p95
1.0 ms with one 11.4 ms event. Check counts vary by one because three
per-device placement checks carry device UUIDs in their names. That is
software draw timing, not optical. Suspend injection cancels the session,
stops renewals, paints no cancelled cut and returns both clients to the
persisted scene. Optical gate: MISSING.

### R4 native video

- Ingest/serving/backup were already merged (schema 3, faststart remux,
  ranges, ETag, backup closure).
- Server: video playlist dwell from metadata, prepare media, ready evidence,
  commit start anchor, bounded 1 s samples, per-device drift status, video
  policy default strict.
- Client: pending/armed/active slots, exact ranged buffer coverage, bounded
  probe and activation promises, rVFC drift with the 50/250 ms rules, pause,
  resume, stop, epoch restore, no native loop.
- Controller: media-library playlist authoring, video badge/duration, live
  status (1 s poll), policy selector, member/buffer/drift evidence, field card
  with diagnostics and rebind, wake-lock roster state.

Browser evidence: a real 4 s H.264 MP4 uploaded through the operator route,
added to the playlist and started from the physical editor, played by two
calibrated Chromium clients. 19/19 checks: descriptor, strict default, editor
authoring with a still and a video, visible video with coded size, advancing
media time, per-device rVFC samples, pause from the editor, resume from the
editor, a looped occurrence, no native loop, stop from the editor and persisted
scene restore. No optical or physical decode claim.

### R5 closeout

- `field_run.py`: 12/12 checks. Diagnostics shape and admission, wake-lock
  state, a real origin/storage loss, rebind through the operator form, number
  and placement moved, old identity removed, new page online and connected.
- `recovery_run.py`: 20/20 trials. Each trial drops one Chromium context until
  the server's 15 s presence timeout, restores it, and measures reconnection
  plus the persisted still. All within the 10 s gate; final p50 0.98 s, max
  1.95 s. Network emulation, not Wi-Fi.
- Diagnostics/rebind/wake-lock are rendered in the physical editor. Local-CA
  trust, real tablet Wi-Fi/OS behavior, kiosk, device matrix and soak remain
  MISSING.

### Verification

- Python: 817 passed.
- Client JS: 43 passed. View JS: 12 passed. Wake lock: 10/10.
- Browser base: 106/106.
- Browser 100 cuts + suspend: 130-131/130-131 (UUID-named checks), p50/p95/max 0.2/0.9-1.0/1.1 ms isolated.
- Video browser: 20/20.
- Field browser: 12/12.
- Recovery browser: 20/20.
- Simulator: 23 scenarios, 1075 checks.
- Deployment guards: 3 passed.
- Controller worker's Playwright run: 38 checks, 0 failures, 1280 and 390 px,
  44 px targets, no horizontal overflow.

Commits: `3611119`, `32272af`, `38a883c`, `a6203c5`, `e24ccad`, `5ab6434`,
`d6b59d7`, `ee5eb80`, `174af4f`, `ac92954`, `bb31ba1`. Worker commits
`0f9bb83` and `2dfaaf8` were integrated by content; their worktrees are clean.

### Explicit deferrals

Group rebuffer with a new common anchor, named partial-video exclusions,
mid-video reconnect recovery and automatic lower-quality fallback are not
implemented. A stalled committed video reports samples but is not group-paused.
These are marked MISSING, not passed. Optical timing, physical suspend, iOS
decode, local-CA device trust and soak remain MISSING.

## Final independent review (Sol xhigh)

Sol reviewed committed HEAD after the first completion and found six further
defects. All are fixed and covered:

1. **P1 short video never ready.** The client floored the buffered end while
   the server published a rounded duration (2066 vs 2067 ms). Coverage now
   rounds up; a fractional-duration fixture passes.
2. **P1 strict commit after a required tablet disconnects.** Closing a device
   socket now revokes its pending lease, so the full cohort check fails and
   strict does not commit to a socket that is gone.
3. **P2 duplicate still commit removed a playing video.** Applied still
   preparations are consumed; a replayed commit is ignored.
4. **P2 status reported expired leases ready.** Status derives readiness from
   the same expiry and clock checks as the commit.
5. **P2 controller timing fields.** The server now publishes `now_ms`; the
   controller reads `current_effective_ms`, so anchors and future commits are
   real. The browser video run checks a timed anchor.
6. **P2 Retry on a failed session.** Retry is enabled only for `blocked`,
   matching the server; failed says Stop and start again.

Two findings were already fixed concurrently: a rejected Previous no longer
cancels the armed cut, and the 412 retry calls the real status refresh.
Final counts: Python 817, client 43, view 12, wake lock 10. Video browser
20/20. Sol's verdict was "not merge-ready" before these fixes; the fixes are
committed (`3c2d5ee`, `3511055`, `7d7143b`, `d53b128`, `a29ac6d`).

Sol verified the replacement-socket fix in `0af196f`: the old lease is revoked
synchronously before the new socket is published, a deterministic reconnect
probe forced a tick during closure and saw no commit, and the replacement
received its preparation and committed with fresh readiness. Verdict:
merge-ready for the software scope. Optical, physical, CA and soak gates
remain MISSING.

## Post-milestone review and cleanup (2026-10-24)

Opus 5.5 reproduced three defects after the milestone:

- one failing writer aborted the commit fan-out, so other tablets never got
  the commit;
- a wall or render frame received mid-show painted over the committed picture;
- a layout or calibration change could commit a cut prepared against the old
  mapping.

Fixed in `24db7ff` and `e52d4bf`:
- each prepare and commit send is isolated; a failed or replaced connection is
  recorded as missed; the commit carries lease connection ids;
- playback owns the glass until stop or epoch, while wall/render frames only
  update the persisted scene;
- display, calibration, active layout and layout recall abort the active
  session.

Tests: a failing writer still reaches the other member, a wall frame during
video does not remove it, and a layout change stops the session. Python 819,
client 44.

Worktree reconciliation:
- `t3/native-video-player-slots` and `t3/controller-video-playlists` are
  recorded as merges after their content was integrated with later fixes.
- `t3/shield-browser-cleanup` and `t3/isolated-browser-runner` were byte-for-
  byte duplicates of changes already on origin/main, so their worktrees and
  branches were removed.
- all merged or superseded Claude/DeepSeek worktrees were removed; two
  uncommitted drafts were preserved first under `recovered/`.
- only the active UX worktrees remain.

## Bounded group recovery and current evidence (2026-10-24)

The feature Sol's fallback plan named next is implemented, merged and proven
at the software boundary. HEAD `64e57d3`.

- `2c9571c` server model: one recovery record per occurrence, fault intake
  from a playing device, three automatic attempts, strict cohort freeze,
  position-aware prepare and commit, remaining-duration next boundary,
  degraded interval, and mapping/layout/epoch aborts.
- `4e9030e` client: fault once per occurrence/position, freeze on a recovery
  prepare, position-aware buffer/probe/commit/samples, and stale callbacks
  cannot paint.
- `917ab79` end-of-clip and operator-retry fixes: stale detection stops
  250 ms before the natural end, a fault at the exact end is refused, and a
  Retry after the automatic cap gets one fresh episode reset to attempt 1.
- `829f5f0` restored-video and real Caddy ingress evidence.
- `c23d37d` controller recovery text/facts and the group recovery browser
  runner.
- `09848f9` controller dwell correction: after a recovery commit the fact is
  the recovered remainder, not the full clip duration.
- `bae3280` the runner checks the live controller before the fault, its
  recovery facts and dwell after the commit, and fresh samples on both
  clients. `b1e7037` keeps a partial report if a check aborts.
- `64e57d3` renders a recorded capped status in the live controller and
  checks the blocked sentence and Retry visibility. This is fixture-rendered
  copy evidence, not a real blocked recovery.

Browser recovery proof (`simulator/browser/group_recovery_run.py`): one
client's active video is frozen with a hanging play promise, its local
retries exhaust, one `video_fault` is accepted, the server starts one
recovery at the live playhead, both calibrated clients prepare there, one
common commit resumes the clip, and the next boundary is the remaining
duration. The live controller shows the same recovery record, a truthful
remaining dwell, and a playing state after the commit. 10/10 checks at
`64e57d3`; the run is software evidence only. The blocked presentation is
checked against a recorded status, not a live cap exhaustion.

Verification at `3f5326d` (docs at `d093647`):
- Python 840 passed (full suite).
- Client 60, view 12, wake lock 10.
- Browser base 105/105; video 20/20; field 12/12; group recovery 10/10;
  restored video 41/41. The base count varies by one conditional API
  evidence line; the earlier run emitted 106/106.
- Caddy + ingress + backup video: 13 passed, including the real Caddy skip
  path.
- Worktrees and branches for the recovery/evidence workers were removed
  after merge; `main` is the only worktree and branch.

### Red-team findings and fixes

The DeepSeek red-team review of the recovery feature found:

- **High, fixed.** A decoder can wedge while `currentTime` and `paused` stay
  healthy. The client watchdog kept renewing the server's sample recency, so
  the stale-sample trigger was masked until drift exceeded 60 s. The client
  now treats 2500 ms without a presented frame as a stall and spends a local
  recovery; after the third it sends the normal fault. Covered by a client VM
  test; not exercised in a real browser, because the browser runner injects a
  pause rather than a frame freeze.
- **High, fixed.** The one-fault-per-occurrence/position guard survived a
  recovery commit, so a second stall at the same position could not report.
  The commit now clears the guard. Client test covers the same-position
  retry.
- **Low, fixed.** A fault before the current commit anchor could start a
  recovery on an armed, not-yet-visible occurrence. The server now ignores
  it; the model test covers both sides of the anchor.
- **Low, documentation.** The stopped/`ended: false` trigger had no distinct
  send path: it is the client `video_fault` with reason `stalled` after local
  recovery is exhausted. Protocol and contract say so.

Accepted or deferred:

- The recovery deadline is the ordinary 30 s preparation window, so one
  dropped tablet can hold the frozen wall for about 31 s before
  blocked/failed. The controller can Stop throughout. This is the approved
  whole-cohort bound, not a new defect.
- An online-policy recovery failure ends the session; the controller offers
  Start again rather than Retry. Retry remains for strict blocked.
- Browser evidence still does not exercise a live timeout, the automatic cap,
  a second device faulting during recovery, or a final-item recovery. The
  blocked copy is rendered from a recorded capped status, not a real cap
  exhaustion.

Claude Opus 5.5 review was retried once on 2026-10-24 at max effort and failed
again with `Claude API rate limit reached`. No Opus findings were produced for
this pass; the independent DeepSeek red-team review above is the substitute.

## Review-fix round (2026-10-25)

The independent review at `96a7862`
(`/tmp/tablet-wall-codex-work-review-2026-10-25/review.md`, outside the
checkout) reproduced two P1 playback defects and two P2 controller defects in
disposable Chromium while the Python, client, video, recovery and restore
suites passed. It also found a browser-evidence gap (F5) and documentation
drift (F6). Software release approval stays closed; every physical,
deployment, iOS, CA, Wi-Fi, kiosk and soak gate remains MISSING.

The committed repair plan is `0ea98b9`
(`work/review-fixes-plan.md`). No separate advisor memo artifact is committed;
the plan records the advisor memo's amendments. The binding amendments kept
recovery identity explicit by `recovery_id`, required one terminal transition
that freezes every reachable cohort member without a fourth prepare, and left
Phase 3's reconnect/exclusion defaults for the operator to confirm rather than
treating advisor review as product acceptance.

### Findings and repairs

| Finding | State | Repair |
| --- | --- | --- |
| F1 preparation identity | Fixed | Server/protocol `8c0c3c3`: an ordinary prepare omits both `recovery_id` and `start_media_ms`; a recovery prepare carries both. Client `8df56f6` detects recovery only from the top-level `recovery_id`, validates a non-empty id and position bounds, and preserves armed/active playback on a routine prepare. |
| F2 terminal hold | Fixed | `8c0c3c3` model and fan-out plus `8df56f6` client handling. The cap advances the session version, clears pending work, builds one hold frame before fan-out, and sends no fourth prepare. Both the socket-fault and stale-sample cap paths use it. The client holds the picture and rejects a stale terminal frame after Retry or a new session. Stop restores the persisted scene; strict Retry resets the fresh episode to attempt 1. |
| F3 pause rendering | Fixed | `925556b`: `remainingDwell` checks `pending` before converting or dereferencing it and uses `paused_at_ms` as the observation time, so the paused countdown stops and the status poll stays healthy. |
| F4 live item identity | Fixed | `925556b`: status publishes `playlist_revision` and `live.current/displayed/pending` from the frozen session. The controller renders live name, kind and duration from that data, hides the editable `Now` marker when revisions differ, and a later Start uses the saved revision. |
| F5 evidence gaps | Partially landed | `video_run.py` now fails on unexpected page/console/request errors and requires visible advancing pictures. `video_transitions_run.py` adds the F1 transitions and the real following cut. `controller_run.py` adds durable pause and live-identity coverage. Recovery timeout, live cap, multi-fault and final-item acceptance remain pending with the recovery acceptance runner. |
| F6 docs/evidence schemas | Partially landed | Current capability, historical scope, evidence kinds and acceptance gaps are reconciled here and in `README.md`, `RECOVERY.md`, `RECOVERY-CONTRACT.md` and `simulator/README.md`. Report-summary normalization (a common runner version, head, dirty, scenario and count schema) and `PROTOCOL.md`'s Retry/Stop wording remain outside this change. |

### Repairs and durable browser evidence

The durable browser additions are `02349b1` (`controller_run.py`), `ae97049`
with merge `2a30ffb` (`video_run.py` v2 and `video_transitions_run.py`), and
`187bde4` (deterministic recovery-time save). Two consecutive green runs each
recorded:

- `controller_run.py`: 54/54 checks, 11/11 scenarios.
- `video_transitions_run.py`: 51/51 checks.
- `video_run.py` v2: 35/35 checks.

Baseline failure proofs:

- `controller_run.py` at `8df56f6`: the run stops at the paused summary; the
  controller never renders `Paused on` (the F3 exception path).
- `video_run.py` at `8df56f6`: 34/35, failing on repeated controller page
  errors `Cannot read properties of null (reading 'occurrence')` from F3.

Targeted verification in the review-fix worktree: Python 851; client 71;
view 12; wake lock 10. `field_run` 12/12 and `restore_run` 41/41 are last
recorded runs from before this round and were not rerun. Do not add counts
across overlapping browser suites.

Still pending:

- Recovery acceptance: timeout, live strict and online caps, operator Retry,
  multi-fault ordering and final-item recovery. No runner count is claimed
  until the recovery acceptance runner lands and passes.
- Phase 3: mid-video reconnect and session-only named exclusions. Both still
  need the operator's product choices; neither is implemented or claimed.
- Report-summary normalization, physical/optical validation, iOS Safari,
  installed CA trust, real Wi-Fi/OS, kiosk and soak.

## Next actions

The remaining product work is hardware and deployment evidence: optical cut
timing, physical decode/suspend, iOS Safari, mixed-model calibration,
installed local-CA trust, real Wi-Fi/OS behavior, kiosk and soak. Software
follow-ups that stay in scope are the recovery acceptance runner (timeout,
live cap, multi-fault and final item), named exclusions, mid-video reconnect
reusing the recovery model, and any credible red-team findings. None of the
hardware gates may be inferred from the software evidence above.
