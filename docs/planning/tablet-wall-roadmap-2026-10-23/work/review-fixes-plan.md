# Plan: repair the 2026-10-25 review findings

Source: `/tmp/tablet-wall-codex-work-review-2026-10-25/review.md` at
`96a7862`. The review reproduced F1-F4 in disposable Chromium, found F5
evidence gaps and F6 documentation drift. Software release approval stays
closed; all hardware/deployment gates remain MISSING.

Goal: close F1-F4 with narrow repair diffs and regression tests, promote the
review reproductions to durable browser coverage, reconcile docs/evidence,
then add deliberate mid-video reconnect and session-only named exclusions.

## Non-negotiable behaviors

- Ordinary next preparation must never interrupt an armed or active video.
- A recovery is identified by `recovery_id`, never by `start_media_ms` or its
  value. Zero is a valid recovery position.
- A terminal recovery (attempt cap) freezes every reachable cohort member and
  sends no fourth prepare. The transition advances the session version,
  invalidates pending leases and armed callbacks, and captures one immutable
  hold frame before asynchronous fan-out. Both the socket-fault and
  stale-sample cap paths use it. Clients reject a stale terminal frame after
  Retry or a new session. Stop still restores the persisted scene; strict
  Retry still resets attempts to 1.
- The controller renders live item identity from the frozen session, never
  from the editable playlist. Pause must not throw and its dwell is stable.
- A new browser case must fail at `96a7862` before the repair is accepted.
- No push, no history rewrite, no deletion of drafts or review artifacts.

## Phase 1: correctness repairs (three parallel worktrees)

### A. Server and protocol (F1, F2, F4 data, revisions)

Files: `tabletwall/playback.py`, `main.py`, `PROTOCOL.md`,
`tests/test_playback*.py`.

1. Wire identity:
   - `Preparation.as_frame()` adds top-level `recovery_id` only when set; it
     adds `start_media_ms` only for a recovery preparation. Keep the commit's
     `start_media_ms` for video commits.
   - `_send_prepare` emits the same fields; ordinary prepares carry neither
     recovery marker nor start position. Keep the top-level occurrence and
     preparation/version/connection fields authoritative.
   - Keep `Preparation.recovery_id` as the single source of truth. A present
     invalid marker is rejected, not treated as ordinary.
   - Bump the client cache version or document the coordinated reload needed
     before terminal-hold semantics are operational.
2. Terminal hold:
   - Add one model/caller helper for the cap transition
     (`_recovery_failure` and the stale-cap path already converge on
     blocked/failed).
   - In `main.py`, after a cap result from a fault or tick, send
     `{"type":"playback","state":"blocked"|"failed","reason":..., **lineage}`
     to every reachable cohort device with isolated fan-out. No prepare.
   - Preserve strict Retry and online Start-again behavior.
3. Live session metadata:
   - `_playback_status` adds `live: {current, displayed, pending}` and
     `playlist_revision`. Each item carries `{occurrence, asset, kind,
     duration_ms, dwell_ms}` derived from `Session.items`/`Session.videos`.
   - Saved playlist revisions increment only after a successful conditional
     save; `start` captures that revision in the session. Existing documents
     without a revision start at 1; rejected saves do not advance it.
   - `live` entries are nullable and carry asset ID plus frozen kind and
     duration semantics (video duration or still dwell); names resolve from
     the authoritative asset library, not the editable playlist.
4. Tests: serialized ordinary/recovery prepare frames; strict and online cap
   fan-out; no fourth prepare; Retry; status live metadata before and after a
   playlist save; revision monotonicity.

### B. Client (F1, F2)

Files: `frontend/client/client.js`, `tests/client_image.test.js`.

1. Recovery detection uses top-level `frame.recovery_id` only. There is no
   `media.recovery_id` or `start_media_ms` fallback. `start_media_ms` only
   supplies the position after recovery is established. Ordinary prepares
   with `start_media_ms: 0` preserve armed/active playback.
2. `recovery_id` is validated as a non-empty string and the position as
   `0..duration-1` before interrupting; a present invalid marker is rejected
   without freezing. Both serializers and the ordinary zero-start
   compatibility frame are tested.
3. Playback state `blocked`/`failed` holds the active video (clear still
   timers, freeze, release pending/armed, keep playback ownership and the
   picture) instead of `stopPlayback()`; the hold is idempotent and ignores
   stale lineage after Retry/new session. `stopped`, epoch, close and explicit
   Stop still restore the latest persisted scene.
4. Tests: ordinary prepare with zero start and no id; recovery at zero;
   recovery followed by a routine video prepare; video-to-video and
   single-video loop VM shapes; terminal hold preserves the picture and late
   callbacks cannot paint; Stop after hold restores.

### C. Controller (F3, F4 UI)

Files: `frontend/controller/physical.js`, `physical.html/css` only if needed.

1. `remainingDwell` checks `pending` before conversion/dereference. In paused
   state use `paused_at_ms` as the observation time so the countdown stops.
2. Live summary/facts/stage labels use `status.live.*` and the frozen
   `duration_ms`/`kind`; the editable playlist remains authoring. Hide or
   relabel the editable "Now" marker when the session revision differs.
3. Tests: a disposable server plus mocked and real statuses for pause, resume,
   stop, saved/reordered draft during playback and recovery, controller
   reload, no page errors, stable text, focus and accessible names. The
   durable copy is owned by Phase 2D and must be listed there explicitly.

Merge order: A, then B, then C. Run targeted Python/client tests after each
merge, then the full suite. Conflicts are expected only in `main.py`; A owns
all server edits.

## Phase 2: durable evidence and docs (parallel with D/E)

### D. Browser acceptance (F5)

Files: `simulator/browser/group_recovery_run.py`,
`simulator/browser/video_run.py`, a new focused runner if needed,
`simulator/browser/evidence.py` only with E.

- Fail on unexpected controller/client page errors and failed requests;
  classify the intentional hung-play/callback-loss warnings.
- Assert every original cohort member has a visible, advancing picture, not
  only `getClientRects()`.
- Add: consecutive videos, one-video loop, routine preparation while
  armed/active, recovery at zero, recovery followed by an actual video cut,
  live strict/online cap through both fault and stale-sample paths, cohort
  freeze, no fourth prepare, late callbacks, operator Retry/Start again,
  Stop, strict/online timeout, multiple faults in both orders, and final-item
  recovery. Also Pause summary and dwell, Resume, poll health, controller page
  errors, and draft edit/reorder/save during playback and recovery followed by
  a reload and a subsequent Start using the saved revision.
- Preserve partial reports with an explicit incomplete/error state.
- Run each defect reproduction against a `96a7862` worktree first and record
  the failure before accepting its repair. Correct-behavior cases (final-item
  recovery) remain passing regressions, not baseline failures.

### E. Documentation and report accounting (F6)

Files: `README.md`, `PROTOCOL.md`, `docs/design/stages-3-5/*`,
`docs/planning/tablet-wall-roadmap-2026-10-23/RECOVERY.md`, `EXECUTION_LOG.md`,
`simulator/browser/evidence.py`, report summaries.

- Correct current capability statements, scope historical recovery sections
  explicitly, qualify Retry as strict-blocked only, and replace the three
  misleading code comments during the related repair.
- Normalize report summaries: runner version, head SHA, dirty state, scenario
  IDs, pass/fail/skip counts and reasons, error, browser version, evidence
  kind. Never sum overlapping suites. Keep restore's grouped schema via an
  adapter.
- Inventory untracked artifacts; do not delete or commit user drafts in this
  change.

Merge D and E after Phase 1. Rerun the full software acceptance set.

## Phase 3: reconnect and named exclusions

Accepted operator behavior (2026-10-25): automatic reconnect with one normal
attempt; session-only named exclusions at Start with the persisted static
scene; blocked-recovery exclusion deferred to Stop/Start.

- **Mid-video reconnect.** If a session is playing and the returning device
  was required, start one group recovery at the server-authoritative playhead,
  cancel the next item, freeze the reachable cohort, prepare the replacement
  and all required members, then commit a fresh anchor. Coalesce a 2 s storm.
  It consumes one normal recovery attempt. If a recovery is already preparing,
  resend that prepare under the new connection and require fresh clock,
  buffer, mapping and activation evidence. Do not auto-rejoin paused, blocked,
  failed or final sessions; the tablet shows the persisted scene and waits for
  the operator. Never revive an old epoch or monotonic anchor.
- **Named exclusions.** Session-only, chosen at Start from the physical slots.
  Excluded devices are named in the controller, show the persisted static
  scene, are not counted as synchronized participants, and are removed from
  strict readiness; content bounds do not shrink. All-excluded start is
  refused. No live exclusion command and no automatic re-inclusion in this
  increment; diagnostics retain the original required set. Saved layouts are
  unchanged.

Implementation split (accepted): one server worktree for reconnect and the
start-exclusion API, one controller worktree for the session-only exclusion
picker. The server owns `main.py`, `tabletwall/playback.py`, `PROTOCOL.md` and
the playback tests. The controller owns `frontend/controller/physical.*` and
the controller runner. Merge server then controller, then add one browser
runner for reconnect and exclusions.

Start API: `POST /api/v3/playback/start` accepts optional
`exclusions: [uuid]`. Every id must name a participating layout slot; an
all-excluded request is `409`. The session records the original required set,
the excluded set and the effective cohort. Strict readiness and content
bounds use the effective cohort; excluded tablets receive a stopped frame and
show the persisted scene. `GET /api/v3/playback` reports `required`,
`excluded` and `cohort` separately. Resume retains the frozen selection.

Reconnect: after a device socket replacement during an active session, if the
session is `recovering`, resend the existing prepare to the replacement
without a new attempt or deadline. If it is `preparing`/`armed`, resend the
current pending prepare. If a video is `playing`, not final, with at least
250 ms of media left and fewer than three attempts on the occurrence, start
one group recovery at the server playhead with reason `reconnect` and one
normal attempt; this freezes the reachable cohort and commits a fresh common
anchor. A reconnect for the same device within 2 s of that recovery's start
does not start a second attempt. Paused, blocked, failed, final and
near-end/last-video sessions do not auto-rejoin; the tablet shows the
persisted scene until the operator acts. Reconnect never revives an old epoch
or monotonic anchor.

## Verification

Targeted after each merge:
`pytest tests/test_playback*.py`, `node tests/client_image.test.js`,
`node tests/client_view.test.js`, `node tests/client_wake_lock.test.js`.

Full after Phase 2 and Phase 3:
`pytest -q`; the three node suites; browser `run`, `video_run`,
`group_recovery_run`, `field_run`, `restore_run`; simulator safety tests;
`pytest -q -rs tests/test_ingress_video.py tests/test_video_serving.py
tests/test_backup_video.py`.

Every browser artifact directory is new and outside the checkout; servers use
temporary DB/media and free ports, never port 8000.

## Risks and deferred work

- A flapping connection can spend recovery attempts; keep the coalescing
  window and operator Stop.
- Excluding a device is a visible product choice; if the operator rejects
  static-scene appearance, session-only persistence, or the reconnect attempt
  budget, stop before Phase 3 code. The advisor cannot accept these defaults
  on the operator's behalf.
- Hardware gates remain MISSING: optical cut timing, physical decode/suspend,
  iOS Safari, mixed-model calibration, installed CA trust, real Wi-Fi/OS,
  kiosk, soak. Automatic quality fallback stays deferred.
