# Runtime worker brief (R3 correctness + R4 video server)

Work in your own worktree. Read the plan at
`/var/home/oak/Codes/projects/tablet-wall-ai/docs/planning/tablet-wall-roadmap-2026-10-23/PLAN-STAGES-3-5.md`
and the contract `docs/design/stages-3-5/CONTRACT.md` in the main checkout.
Do not edit the plan, docs, simulator, client or controller.

## Phase 1: R3 correctness (land and commit first)

Files: `tabletwall/playback.py`, playback/ready/start routes in `main.py`,
`tests/test_playback.py`, `tests/test_playback_strict.py`, plus new focused
tests. Keep the existing external frame shapes except additive fields.

Requirements:
1. `_commit` schedules the next boundary with the committed item's dwell, not
   the next item's. Unequal dwells 5/11/17 must give effective 2/7/18 s.
2. `Session.index` and `loop_count` stay on the active occurrence. The pending
   preparation names the next occurrence. Next from active 0 goes to 1.
3. A non-looping last item reaches a distinct `final` state after its commit;
   it must not be `stopped` before the effective cut.
4. Lease validity uses `now_ms` and the actual accepted cut. A lease expired
   before a held cut cannot commit. Add tests for expiry, renewal, and hold.
5. `accept_ready` enforces mapping revision, fresh clock, decoded, occurrence,
   connection and lineage. Add the parameters needed and update callers.
6. `POST /api/v3/playback/start` on a paused session resumes the current item
   with a new version; on a live session it is still 409. Add model + HTTP
   tests.
7. Strict start includes every required physical slot with
   `participating != false`, including offline ones; online start keeps the
   online cohort. Add a TestClient test with an offline slot that blocks.
8. On stop and on suspend/epoch abort, send the persisted static `wall` frame
   after `playback stopped` to every cohort member. Add a socket test.
9. Recompute clock freshness from `clock_samples` at ready time.

Do not change the playlist dwell rule for stills, the v1/v2 payloads, or the
writer.

Acceptance: `.venv/bin/python -m pytest -q` all pass; new tests fail on the
old code and pass on yours; commit with a conventional message.

## Phase 2: R4 video server (commit separately)

Files: `tabletwall/playback.py`, video hooks in `main.py`,
`tests/test_playback_video.py` (new).

Use `media.video_descriptor` and `media.video_duration_ms`.

- Playlist: a video id's dwell is its duration (1..600000 ms). `PUT playlist`
  and `start` accept video ids. A still keeps the requested dwell.
- Session holds `videos: {asset: duration}`. `_preparation` adds
  `media={kind:"video", duration_ms, buffer_goal_ms:5000,
  start_lead_ms:1000, prepare_timeout_ms:30000}`. Stills have no media.
- `prepare` includes `media`; `commit` includes `start_media_ms: 0` for a
  video; still commits unchanged.
- `ready.video` shape: `{metadata, seeked, buffered_ahead_ms, play_ok, rvfc}`.
  A video lease is ready only with metadata and seek true, play_ok yes, and
  `buffered_ahead_ms >= min(goal, duration)`. A later report that fails
  clears readiness and stores the evidence.
- `video_sample`: accept only the current socket, session, version, occurrence
  and a playing device; finite bounded numbers; at least 1000 ms apart. Keep
  the latest per device for 5 s. Surface in `playback_status.video` as
  `{device_id: {drift_ms, rate, source, media_ms, age_ms}}`.
- Default policy: stills online; a playlist containing a video defaults to
  strict when the request omits `policy`. An explicit policy wins.
- Status includes current item kind/duration, pending media, final state, and
  per-device ready/video evidence so a blocked video explains itself.
- Tests: dwell, prepare media, each ready field, regression, commit anchor,
  sample accept/refuse/age, strict default, single-video final, blocked video.

Commands: `/var/home/oak/Codes/projects/tablet-wall-ai/.venv/bin/python -m pytest -q`.
Never port 8000. Commit on your worktree. Report branch, two SHAs, counts.

## Runner note (parent owns)

The 100-cut check must require zero failed events, not merely complete+failed
= requested. The suspend check must require the persisted static scene after
the abort, not accept the last still. These are parent changes, not runtime.

## Binding round-2 corrections

- `step()` must use the active occurrence (or displayed item before a cut) and
  only mutate index/loop on commit. Pending occurrences carry their own loop.
  Non-looping Next at the last item and Previous at index 0/loop 0 are explicit
  no-ops or 409s. Looping Previous at index 0 decrements the loop when it can.
- Retry rebuilds the blocked pending occurrence, including its loop; do not
  call `step(0)`.
- Pass current connections into start/step/resume/retry.
- Re-anchor every late cut, including a fully ready one: `now >= effective`
  moves the cut to `now + LEAD_MS`, publishes the anchor, allows renewals, and
  preserves the following item's full dwell. Preparation deadline is
  `effective + timeout`; hold cap is `effective + min(dwell/2, 5s)` with no
  deadline clamp.
- Strict includes every required participating slot, including offline and
  protocol-unsupported members.
- Reconnect replaces the pending lease connection and clears readiness,
  evidence seq and clock evidence before resending prepare.
- Readiness checks the exact preparation mapping. Negative evidence, mapping
  change, lost socket, or stale clock clears readiness.
- Track committed-future vs displayed. Pause/Next/Previous before the effective
  time cancels the armed commit and acts from the displayed item. `final`
  still accepts samples and supports Stop/Next/Previous/Pause.
- Start-on-paused restarts the current item at a new anchor; document it.
- Abort/stop sends a v3 `render` frame (new render seq), not only a wall frame.
- Default policy: explicit policy, else strict if any item is video, else
  online. The API must keep "omitted" distinguishable from `"online"`.
