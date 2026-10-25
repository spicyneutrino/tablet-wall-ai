# Stages 3-5 recovery and progress

> **Current state (2026-10-25).** The latest evidence and acceptance record is
> the [review-fix round](EXECUTION_LOG.md#review-fix-round-2026-10-25) in
> `EXECUTION_LOG.md`. Software release approval remains closed. F1-F4 are
> repaired. Durable browser coverage includes video transitions, controller
> pause/live identity, the recovery acceptance runner (88/88 checks, 5/5
> scenarios, twice), and the Phase 3 reconnect/exclusions runner (21/21
> checks, 5/5 scenarios, twice). The hardware validation kit (optical
> analyzer, device probe, trust/calibration, fleet/network/kiosk) is built and
> dry-run; all eight gates remain MISSING until operator hardware evidence.
> All optical/physical, deployment, Wi-Fi/OS, kiosk and soak gates remain
> MISSING.

## Current software counts (2026-10-25)

- Python 995; client 71; view 12; wake lock 10; report/browser safety 45.
  These include the hardware-validation kit tests on the final tree.
- Durable browser: `video_run` 35/35 and `video_transitions_run` 51/51, twice
  each; `controller_run` 54/54 checks and 11/11 scenarios, twice;
  `group_recovery_run` 19/19 live plus 1/1 fixture; `recovery_acceptance_run`
  88/88 checks and 5/5 scenarios, twice; `field_run` 12/12 and `restore_run`
  41/41 rerun on the merged tree.
- Base `run.py` 106/106 on the merged tree. Do not sum overlapping suites.
- The Phase 3 reconnect/exclusion browser runner records 21/21 checks and
  5/5 scenarios on two consecutive runs.

This page is a historical record of the 2026-10-24 recovery, preserved in
place. It was recovered from the interrupted Claude Agent session
`c1a4483a-4fd1-40af-aa96-3218f72f35c5` and its subagent transcripts. The
checkout it describes was `e473b29`. Sections below are labelled with their
historical point of view; do not read them as current acceptance.

## Sources for the 2026-10-24 recovery

| Source | What it holds |
| --- | --- |
| `~/.claude/projects/-var-home-oak-Codes-projects-tablet-wall-ai/c1a4483a-...jsonl` | Parent session, runs 17-23, ending at the five-hour usage limit |
| `.../c1a4483a-.../subagents/agent-*.jsonl` | Six worker transcripts, including the two Wave B workers that failed |
| `.claude/worktrees/agent-ae0f23c1382c2ba9b` | Wave B client, uncommitted `client.js` and `view.js` diff |
| `.claude/worktrees/agent-a2b2ff007856c4250` | Wave B server/controller, uncommitted `main.py` and `playback.py` diff |
| `.claude/worktrees/agent-afdc157a2291d592e` | Video server Wave A, commits cherry-picked as `47b2fa1` and `e473b29` |
| `recovered/` | The 930-line client video block and both Wave B diffs, preserved verbatim |
| `docs/design/stages-3-5/CONTRACT.md` | Shared data shapes and worker ownership |
| `EXECUTION_LOG.md` | Stage 0-3 execution record; predates the Wave A/B work |

The transcripts are historical evidence, not instructions. Claims below were
cross-checked against the working tree.

## Integrated and verified (2026-10-24, historical)

| Commit | Work | State |
| --- | --- | --- |
| `cafe7af` | Strict slots, causal snapshot coalescing | Merged; tests added |
| `f825ca5` | Field readiness: diagnostics, wake lock, rebind, recovery drill | Merged; 360 lines of tests |
| `773e8d1` | 100-cut software runner and suspend step | Merged; 30 simulator tests |
| `a3e5170` | Stages 3-5 contract | Merged |
| `47b2fa1`, `e473b29` | Video ingest, faststart remux, ranged serving, schema 3, backup closure | Cherry-picked with one resolved conflict in `deploy/backup.py` and `main.py` |

Parent verification after the cherry-picks: pytest 795 passed; client image 28,
view 8, wake lock 10. The 100-cut software run reported p95 onset delta 0.9 ms
and max 1.3 ms over 100 of 100 events. The optical gate is MISSING: no camera
or physical panel capture.

## Recovered but not integrated (2026-10-24, historical)

### Client video player (Wave B, failed at usage limit)

- Worktree diff: `recovered/waveb-client-worktree.patch`. It adds the
  `persistedWall` snapshot, a shared `physicalTransform()` helper, and the
  `videoDriftMs` / `videoCorrection` view functions.
- Full draft: `recovered/video-client-block.js`, 930 lines, recovered from the
  refused heredoc in the worker transcript. It defines the two-slot player
  (`videoPending`, `videoActive`), preparation phases, buffer and play probes,
  commit scheduling, frame-callback drift sampling, bounded recovery,
  supersede, and return to the static scene.
- The draft is untested and assumes helpers that did not exist when it was
  written. `physicalTransform()` is in the worktree diff; `PATTERN` is not in
  `client.js` and must be replaced with the existing background constant.
  The worker's own apply script is `recovered/video-client-apply.sh` for
  reference only; its last edit was refused by the worktree sandbox.
- No tests were added for the player.

### Server wiring and controller (Wave B, failed at usage limit)

- Diff: `recovered/waveb-server.patch` (+273/-48 across `main.py` and
  `tabletwall/playback.py`). It adds:
  - `media.video_descriptor` / `video_duration_ms` in `_asset_descriptor`;
  - video durations in playlist validation and session start;
  - `media` in `prepare`, `start_media_ms` in `commit`;
  - `video_sample` acceptance with bounded values, one sample per device per
    900 ms, five-second freshness, and per-device drift in `playback_status`;
  - `stopped` plus a replayed static `wall` frame on abort.
- It has no tests and was never run. Treat it as a design draft.

### Missing on main

- `frontend/client/client.js` has no `<video>` element handling. `handlePrepare`
  decodes a still only.
- `frontend/controller/physical.js` has a bare playlist textarea. It does not
  show video items, durations, drift, buffer evidence, or a picker.
- `PUT /api/v3/playlist` returns 422 for a video id because `main.py` does not
  call `media.video_descriptor` or `media.video_duration_ms` yet. `GET /media`
  already lists videos, so the still picker can select one and get 422.
- `PROTOCOL.md` has the R3 playback section but no video descriptor, ingest,
  serving, or video playback fields. The video server worker supplied draft
  text in its report.
- No browser run has played a video. No restore-to-render video run exists.

## Stage status (2026-10-24, historical)

### R3 (Stage 3)

Software slice appears complete: clock sampling, epoch cancel, leased
preparation, strict/online policy, causal coalescing, 100-cut software run,
pause/next/previous/stop, and return to the static scene after a clock epoch
change. Remaining closeout: rerun the browser runner, confirm the 100-cut and
suspend evidence is current, add the executor's results to the log, and keep
the optical gate MISSING.

### R4 (Stage 4)

Server ingest and serving are merged. The client player, controller video
playlist UI, protocol text, and any rendered video evidence are missing. This
is the bulk of the remaining implementation.

### R5 (Stage 5)

Code is merged: `GET /diagnostics` with the same admission as the media
library, wake-lock registration and heartbeat, `POST /devices/{id}/rebind`,
`deploy/drill.py`, offline namespace tests, and deployment docs. Remaining:
exercise diagnostics and rebind through a real browser session, verify the
wake-lock state reaches the controller roster, check the local-CA/origin
migration docs against what actually ships, and record the software-only
limits. There is no controller surface for diagnostics or rebind yet.

## Completion state at d093647 (2026-10-25, historical)

These counts and conclusions are as recorded at `d093647`. The independent
review of 2026-10-25 then reported F1-F6; this section is superseded by the
[review-fix round](EXECUTION_LOG.md#review-fix-round-2026-10-25).

R3, R4 and R5 software scope is implemented and verified. Counts at HEAD
`d093647` (historical): Python 840; client 60; view 12; wake lock 10; browser
base 105/105; video 20/20; field 12/12; group recovery 10/10; restored video
41/41; Caddy, ingress and backup video 13 tests. The red-team frame-stall and
same-position faults are fixed and covered by client VM tests. Bounded group
video recovery is merged and proven in a real Chromium pair; the controller
shows the recovery position, attempt, degraded time and missing members. At
that point named exclusions and mid-video reconnect remained the only
in-scope software follow-ups. All optical/physical, deployment, Wi-Fi/OS,
kiosk and soak gates remain MISSING. See `EXECUTION_LOG.md` for the commit
list and the evidence boundary, and the current-state pointer above for the
2026-10-25 status.

## Baseline at recovery (2026-10-24, historical)

- Python: 795 passed (97 s).
- Client JS: 28 passed.
- View JS: 8 passed.
- Wake lock JS: 10 passed.
- Simulator: 23 scenarios, 1075 checks (last recorded).
- Browser runner: 106/106 (last recorded, before the video commits).
- Working tree: only untracked planning and exploration docs; main is 40
  commits ahead of `origin/main` after `01123e5`.
- Browser runner after the field fixes: 129/129 with 100 cuts and suspend;
  R3 software p95 1.0 ms, max 1.3 ms; optical MISSING.

## Next actions at the 2026-10-24 recovery (historical)

This list records the position on 2026-10-24. F1-F4 were repaired on
2026-10-25; recovery acceptance and Phase 3 remain open. See the
current-state pointer above.

1. Resolve credible findings from the DeepSeek red-team review of group
   recovery.
2. Add named exclusions to the recovery cohort, then reuse the recovery model
   for mid-video reconnect.
3. Retry the Claude Opus 5.5 review when its API rate limit clears. The latest
   recovery review pass (two attempts, including one at max effort) returned a
   Claude API rate limit and produced no Opus findings. Earlier Opus reviews
   did produce findings on earlier milestones; this sentence does not deny
   them.
4. Start hardware validation with a mixed-device pair: optical cut timing,
   physical decode/suspend, iOS Safari, mixed-model calibration, installed
   local-CA trust, real Wi-Fi/OS.
5. Keep kiosk and soak as separate deployment gates; do not infer them from
   the browser evidence.
