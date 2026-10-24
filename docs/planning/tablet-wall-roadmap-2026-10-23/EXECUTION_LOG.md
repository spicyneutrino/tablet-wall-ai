# Execution log: Stages 0-3

Scope: P0, R1, R2 and R3 of [ROADMAP.md](ROADMAP.md). Hardware-only claims
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
