# Client worker brief (R4 native video player)

Work in your own worktree. Read the plan and contract in the main checkout:
- docs/planning/tablet-wall-roadmap-2026-10-23/PLAN-STAGES-3-5.md
- docs/design/stages-3-5/CONTRACT.md
- docs/planning/tablet-wall-roadmap-2026-10-23/recovered/video-client-block.js
  (reference only, not a patch)

Own `frontend/client/client.js`, `frontend/client/view.js`,
`frontend/client/index.html`, `tests/client_image.test.js`,
`tests/client_view.test.js`.

Requirements:
1. Keep `persistedWall`; `applyWallFrame`/`applyRenderFrame` set it.
2. Add `physicalTransform()` (plan/calibration -> matrix + clip) and use it for
   stills and video, in CSS pixels.
3. Implement the video lifecycle: loading -> metadata -> seek -> buffering ->
   probing -> reseeking -> ready -> armed -> playing -> paused/blocked. Every
   callback checks a generation/epoch/session/version/preparation/occurrence
   token. Bound the play promise with a timeout.
4. Separate `pending` and `armed`. On commit move the slot out of pending
   before the next prepare arrives, so the next prepare cannot release a
   committed-but-not-started video. Release/freeze only by state.
5. Buffer coverage from the range containing the target; near the end require
   only the remainder. No `canplaythrough`, no native loop.
6. Ready evidence every 500 ms; sample every 1000 ms. Drift: 50 ms deadband,
   rate 0.98..1.02 inside 50..250 ms, one seek per 5 s above 250 ms. Report
   `source` rvfc/time.
7. Commit at the compensated effective time, one rAF recheck, start at
   `start_media_ms`.
8. Supersede on new prepare, cancel, pause, stop, close, epoch, visibility;
   pause freezes, stop/epoch restores the persisted wall, resume starts the
   current item again.
9. Activation denial shows one local "Enable display" button and reports
   `needs_gesture`; other failures report `play_ok: no`. Three bounded
   recovery attempts, then blocked.
10. Do not print a warning for an expected activation denial. Keep the still
    path and all existing behavior intact.

Tests: add view tests for `videoCorrection`/deadband/seek budget; add a client
harness test for a commit followed immediately by the next prepare (the armed
slot must survive), and for a superseded generation that never paints.
Commands: `node tests/client_image.test.js`, `node tests/client_view.test.js`,
`node tests/client_wake_lock.test.js`. Commit. Report SHA and counts.

## Binding round-2 corrections

- Three slots: pending, armed, active. A routine next prepare replaces only
  pending. Explicit cancel/pause/stop/epoch/visibility disposes only what the
  action owns.
- Per-slot and per-attempt tokens, not one global latest version. A duplicate
  commit must not start twice.
- A timed-out play probe pauses the element and invalidates the attempt; late
  promise/seek/rAF completions do nothing.
- Buffer coverage must contain the target with no rounded-up gap. Recheck
  coverage and permission after the reseek and before activation.
- The commit carries a new effective anchor if the server re-anchored it;
  schedule from the commit, not from an earlier prepare.
- Include tests for duplicate commit, timeout then late resolution, pause while
  armed, and a next prepare immediately after commit.
