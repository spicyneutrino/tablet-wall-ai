# Stages 3-5 implementation plan (Sol review round 2)

Status: implemented and verified in the software scope. Final evidence is in
`EXECUTION_LOG.md`; recovery facts in `RECOVERY.md`. Optical, physical decode,
suspend, CA trust and soak remain MISSING.


## Round 2 verification corrections (binding)

Sol approved R3 and R5 with corrections and rejected R4 as written. These
rules override the text below where they conflict.

### R3 transitions

- `step()` changes with `_commit()`. Only an accepted transition updates the
  active index/loop. A pending occurrence carries its own loop number.
  Next at a non-looping last item and Previous at index 0 with loop 0 are
  explicit no-ops or 409s; define and test them. Looping Previous at index 0
  decrements the loop only when it can.
- Retry copies the blocked pending occurrence, including its loop; it must not
  call `step(0)`.
- Every preparation receives current connection ids. Main supplies them for
  start, step, retry, and resume.
- Re-anchor every late cut, including a fully ready one: if
  `now >= pending.effective_ms`, move the cut to `now + LEAD_MS`, publish the
  new anchor, allow renewals against it, and keep the following item's full
  dwell. Preparation deadline is `effective_ms + timeout`, so a long clip does
  not hold-block 30 s after it was prepared. The hold cap is
  `effective + min(dwell/2, 5s)` with no deadline clamp.
- Strict cohort includes every required participating slot, including offline
  and protocol-unsupported members. Online keeps the online cohort.
- Reconnect replaces the pending lease's connection id and clears its
  readiness, evidence sequence and clock evidence, then resends prepare.
- Readiness is validated against the exact mapping used by the preparation.
  Negative evidence, a changed mapping, lost socket ownership, or a stale
  clock invalidates previously accepted readiness. A mapping/layout change
  aborts an active session or forces a new preparation; it cannot commit.
- Distinguish committed-future from displayed. `current` is the last committed
  occurrence; keep the previous occurrence and its effective time so status
  can say displayed vs waiting. Pause/Next/Previous before the effective time
  cancel the armed commit and act from the displayed item. Pause after it
  freezes the current item. `final` remains sample-capable and controllable.
- Start-on-paused resumes by restarting the current item at a new anchor; it
  does not claim to resume a frozen media position. Document that.
- Include the client restoration change in R3: `render` frames carry a new
  sequence for v3, so a persisted render paints even when the wall revision is
  unchanged. Do not rely on a `wall` frame at an equal revision.

### R4 lifecycle ownership

- Three slots: `pending` (preparing), `armed` (commit received, waiting for
  effective), `active` (playing/frozen). A routine next prepare replaces only
  `pending`. Explicit cancel/pause/stop/epoch/visibility disposes the slots
  that the action owns.
- Each slot and each start attempt has its own token. Callbacks check
  generation, epoch, session, version, preparation, occurrence, connection,
  and attempt, not one global latest version.
- Commit and start are idempotent. A duplicate commit cannot start twice. A
  timed-out play probe pauses the element and invalidates the attempt; late
  promise/seek/rAF completions do nothing.
- Buffer coverage must contain the requested target with no rounded-up gap.
  Recheck coverage and play permission after the reseek and immediately
  before activation.
- Default policy rule: explicit valid policy, else `strict` when any playlist
  item is video, else `online`. Resolve server-side at Start. The controller
  omits policy unless the operator chooses. Resume keeps policy and cohort.
- Video duration is `1000..600000 ms` (ingest rejects under 1 s).
- Narrow acceptance: upload, prepare, commit, decode, advancing media time,
  geometry/pixels, fresh samples, pause/resume, stop, loop occurrence, and
  restored-media playback are required. Group rebuffer/new anchor, named
  exclusions, automatic partial-video recovery, and mid-video reconnect
  recovery are explicitly MISSING, not claimed. A stalled committed video has
  an authoritative failure transition and reported degraded interval.

### R5 additions

- Origin change with fresh storage, then rebind and reconnect, on logical and
  physical layouts, plus a restart with an explicit number.
- Wake-lock release/reacquisition and live roster updates, including denied
  and unsupported.
- Diagnostics loading/error/absent-backup/damaged-object states.
- WAN-disconnected cold start and restart where the harness can run offline;
  otherwise MISSING with the reason.
- Twenty recovery trials measured from connectivity restoration to correct
  rendered content, retaining failures and final/long-item cases.
- Executable saved-layout migration: recall-and-save preserves the old id;
  the operator must rebind or correct the draft. Test that path.
- Local-CA device trust, physical Wi-Fi/OS, device/build matrix, unattended
  operation, and soak remain MISSING.

## Review corrections that change the work

Sol reproduced these in the committed model and the recovered server draft.
They are R3 correctness defects, not R4 polish.

1. The next cut is scheduled with the next item's dwell. With dwells 5/11/17 s
   the second cut is planned at 13 s instead of 7 s. The current item's dwell
   must set the next boundary.
2. After a commit, `Session.index` is advanced to the pending item, so Next
   skips one occurrence. Keep `index` on the active occurrence; the pending
   preparation carries the next index.
3. A single non-looping item sets `state = "stopped"` inside the commit, before
   its first effective cut. The last item needs a distinct final state.
4. `_valid_leases()` ignores `now_ms` and accepts a lease that expired before a
   re-anchored cut. A hold committed with a lease that expired 4.5 s earlier.
   Validate leases against the actual accepted cut and the current time.
5. Strict membership is "strict within the online cohort". Offline required
   slots and `participating` are not considered. Strict must include every
   required slot and block on the missing ones.
6. Ready evidence checks are incomplete: mapping revision is stored without
   comparison, `clock_ok` is cached without age, and `decoded`, occurrence and
   connection are not all enforced at the socket adapter.
7. Reconnect does not restore the active occurrence or the pending action.
8. Pause has no resume path, and the controller's Start answers 409 after
   Pause with no explanation.
9. Abort/epoch leaves the last still on screen. The R4 abort path sends the
   persisted wall and the client restores it.
10. Recovered drafts must not be applied wholesale. The 930-line client block
    kills a committed-but-not-yet-started video when the next prepare arrives;
    it has no awaited play timeout, no visibility/clock confidence, and no
    group recovery. The recovered server keeps defects 1-6 and stops a
    single-video session before samples can arrive.
11. Contract conflicts: video should default strict (roadmap); the contract
    says online. Samples are 900 ms in the draft, 1 s in the contract. Ingest
    rejects clips under 1 s. `PATTERN.background` already exists. Playback UI
    lives in `physical.js`, not `controller.js`.

## R3 correctness fixes (must land before R4)

Files: `tabletwall/playback.py`, `tabletwall/clock.py` if needed,
playback routes in `main.py`, `tests/test_playback*.py`,
`tests/test_v3.py`, `tests/test_playback_http.py` if present.

### Model

- Keep `Session.index` and `loop_count` on the active occurrence. At start,
  `current is None` and `index = 0`; pending names item 0.
- `_commit`: set current and index from the committed occurrence; compute
  `next_index()` from that; schedule the pending cut at
  `effective_ms + current_item.dwell_ms`; do not move `index` to the pending
  item.
- Add `final: bool` (or `state="final"`) for a non-looping last item. The
  session stays alive until Stop; status says final.
- `_valid_leases(session, now_ms, cut_ms)` requires `ready`, fresh
  `clock_ok`, `lease_expires_ms >= cut_ms`, and `lease_expires_ms > now_ms`.
  The hold path computes the accepted cut (`now + LEAD_MS`) and revalidates.
- `accept_ready` rejects a report after the effective time; it records
  mapping revision and clock age evidence for the adapter.
- Strict membership is supplied by the caller; the model treats every cohort
  member as required.
- Add `resume(session, now_ms, connections)` that leaves `paused`, bumps the
  version, prepares the current index with `now + LEAD_MS`, and keeps the
  frozen cohort. `Start` on a paused session resumes; `Start` on a live
  session is still 409.
- `pause` records `paused_at_ms` and the active occurrence; `resume` clears it.
- `stop` leaves the session in `stopped`; the caller sends the persisted wall.

### Socket adapter

- Recheck the current socket and `connection_id`.
- Recompute clock freshness from the last accepted sample (15 s), not a cached
  boolean.
- Compare the reported mapping revision against the device's current
  calibration revision used for the prepare.
- Require `decoded is True` for a still and the video evidence gate for a
  video.
- Match occurrence and preparation lineage.
- On connect during a session, send the pending prepare again with its
  current effective time. If the client reconnects after the cut, send a
  `playback` state frame with the active occurrence and let the next commit
  restore; document the residual one-item gap for stills.
- On abort (clock epoch, restart), send `playback stopped` then the persisted
  static `wall` frame to every cohort member. Stop does the same.

### Tests

- Unequal dwells 5/11/17: boundaries at 2, 7, 18 s.
- Next from active 0 with pending 1 targets 1; Previous targets the last
  active. Next/Previous around an armed boundary invalidates the prepared
  lease.
- One non-looping item: commit at its effective time, state final, no stopped
  before the cut.
- Lease expiring before a held cut cannot commit; renewals allow it.
- Strict with an offline required member blocks at the deadline.
- Pause then Start resumes at a new version and the same occurrence.
- Abort sends stopped plus a wall frame; stale prepare/ready after it cannot
  paint.
- HTTP/socket test for stale mapping, stale clock, wrong occurrence,
  `decoded: false`.

## R4 implementation

### Contract and defaults

- Video playlists default to `strict`; stills keep `online`. An explicit
  `policy` overrides both. The controller shows the effective policy.
- Video item dwell is `duration_ms` from published metadata (1000..600000 ms).
- `prepare.media = {kind:"video", duration_ms, buffer_goal_ms:5000,
  start_lead_ms:1000, prepare_timeout_ms:30000}`.
- `ready.video = {metadata, seeked, buffered_ahead_ms, play_ok, rvfc}`; ready
  only with metadata, seek, play_ok yes, and contiguous coverage of
  `min(goal, duration - start)`.
- `commit.start_media_ms` is 0 for a fresh occurrence.
- `video_sample` at most once per 1000 ms, from the active connection and
  occurrence; keep the latest sample per device for 5 s.
- No native loop attribute. Each loop is a server occurrence.

### Server

Files: `tabletwall/playback.py` (only video additions after R3),
`main.py` video hooks, tests.

- Build media in `_preparation` from `session.videos`.
- `validate_playlist(videos=...)` sets video dwell.
- `_asset_descriptor` returns the video descriptor.
- `_prepare_playback` includes `media`.
- `_send_commit` includes `start_media_ms`.
- `accept_ready(video=...)` stores evidence and drops readiness when evidence
  regresses.
- `_commit` sets `current_media`, `playing`, clears samples, and includes the
  start anchor.
- `video_sample` validation: session/version/occurrence, playing device,
  current socket, finite bounded values, 1 s floor. Broadcast status at most
  1/s.
- `playback_status.video` per device with drift, rate, source, media_ms, age;
  also expose the current item kind and required/ready evidence so a blocked
  video explains itself.
- Default strict when the playlist has a video.

Tests: video dwell, prepare media, ready gate each field, regression drops
readiness, commit start_media, sample acceptance/refusal, status freshness,
strict block/retry, single-video final, and a TestClient run with a real
uploaded fixture.

### Client

Files: `frontend/client/client.js`, `view.js`, `index.html`, client tests.

Use the recovered block as reference, not as a patch. State machine:

`loading -> metadata -> seeking -> buffering -> probing -> reseeking -> ready
-> armed -> playing -> paused/rebuffering -> blocked | disposed`

- Every timer, promise, seek, listener and rVFC handle carries
  `{generation, epoch, session, version, preparation, occurrence,
  connection}` and checks it before acting.
- Keep committed slots separate from `pending`: on commit, move the slot to
  `armed` and clear `pending`, so the next prepare cannot release it before
  its effective time.
- Buffer coverage from the range containing the target; near the end require
  only the remainder. Do not use `canplaythrough` or a near-end allowance.
- Activation probe: muted play/pause; `NotAllowedError` shows one local
  Enable display button and reports `needs_gesture`; other failure is `no`.
  Bound the play promise with a timeout.
- Geometry: reuse the still's `physicalTransform` in CSS, no backing scale.
  Compare the clip rect and a sampled pixel in the browser check.
- Commit at the compensated effective time with one rAF recheck; start at
  `start_media_ms`; never loop natively.
- Drift: rVFC or timeupdate; deadband 50 ms, rate 0.98..1.02 inside
  50..250 ms, one seek per 5 s above 250 ms; report 1/s with source.
- Supersede: any new preparation, cancel, pause, stop, socket close, epoch
  change, or visibility loss cancels timers/rVFC/listeners and prevents stale
  paints. Pause freezes; resume prepares the current item; stop and epoch
  restore `persistedWall`.
- Recovery: three bounded reloads/seek-and-play attempts, then `play_ok: no`
  and stop network work. A stalled active video keeps sending samples so the
  server and operator see the drift. Group rebuffer/new anchor is deferred
  and reported; strict blocks on the missing evidence instead of pretending
  synchronization.
- Keep the still path and cache versions compatible.

Tests: view correction math; a native-media harness for promise/seek/buffer
ordering if feasible; supersede-after-commit followed immediately by the next
prepare; no stale play/seek after replacement.

### Controller

Files: `frontend/controller/physical.html`, `physical.js`, `physical.css`,
small `controller.js` library changes, `index.html` cache versions.

- Playlist authoring from the media library: poster, name, kind, duration;
  add/remove/up/down. Stills edit dwell; video shows clip length.
- Upload accepts `video/mp4,video/quicktime`; the library keeps `kind` and
  `durationMs`; a video cannot be applied as a still scene.
- Playback panel: effective policy (strict by default with video), Retry,
  Stop, Pause/Resume, current/pending occurrence, required vs ready members,
  activation failures, buffer goal, deadline, remaining dwell, per-tablet
  drift and sample age.
- Live status through the v3 controller socket; the page currently fetches
  once. Reconnect recovery keeps the last status and refreshes.
- R5: a compact field card with diagnostics (quota, db, backup age, clients,
  wake-lock counts), wake-lock state in the roster, and a rebind form
  (new device id, replaces id, optional number).
- Accessibility: labels, 44 px targets, focus, no horizontal scroll at 390 px.
  Announce state changes, not every sample.

### Protocol and deployment docs

`PROTOCOL.md`: descriptor, ingest limits/errors, ranges, playlist dwell,
prepare media, ready video evidence, commit anchor, sample, status, policy
defaults, pause/resume, final/loop, abort/static restore, reconnect limits.
`deploy/README.md`: fix rebind layout migration (active layout only; saved
layouts need explicit rebind or draft correction). Reconcile manifest 2/3 and
backup text. `README.md`: R4 software scope and missing hardware.

### Browser evidence

Extend `simulator/browser/run.py` with a video scenario on a fresh temp DB:

1. Generate a 6 s H.264 clip with a visible frame counter and a still.
2. Upload both through the operator route; confirm the descriptor.
3. Calibrate two clients, save [video, still], start with default policy.
4. Assert: prepare media, ready evidence, commit start_media, video visible in
   the clip rect, media time advances, at least one sample with source and
   fresh age, status shows it, pause freezes, Start resumes, Stop restores the
   static wall, the next loop occurrence prepares the video again, no native
   loop.
5. Failure paths: activation denied -> Enable display; buffer below goal ->
   strict blocks; stale sample after version change is ignored.
6. Reject an unsupported codec upload.
7. Restore a real decodable MP4 into new targets, boot the restored app, and
   play it through `/client/`; keep the byte checks separate.
8. Label timings software, not optical. Save screenshots and JSON.

## R5 closeout

- Rendered diagnostics: operator page loads quota, db, backup age, clients,
  wake-lock counts; non-operator denied; `?verify=1` integrity.
- Rendered rebind: new registration replaces an offline old id; placement or
  slot, display records and number move; the tablet reconnects with the new
  number; old identity is gone.
- Roster shows `wake_lock` per device.
- Secure-origin evidence: HTTP tests cannot prove local-CA trust. Document the
  exact CA/host steps and keep TLS-trust MISSING without a device.
- Disconnect/recovery: at least 20 trials on the browser cohort, correct
  content within 10 s; physical Wi-Fi and OS sleep stay MISSING.
- Fix `deploy/README.md` rebind migration text; reconcile backup docs.
- Two-hour media and overnight soak stay MISSING with reasons.

## Verification matrix

| Layer | Command | Gate |
| --- | --- | --- |
| Python | `.venv/bin/python -m pytest -q` | all pass |
| Client | node image/view/wake-lock suites | all pass |
| Simulator | `.venv/bin/python simulator/run.py` | 23 scenarios, 0 failed |
| Browser base | `.venv/bin/python -m simulator.browser.run` | all checks pass, zero failed events required |
| R3 cuts | `--cuts 100 --suspend` | 100 complete, 0 failed, p95/max recorded, optical MISSING, suspend restores the static wall |
| R4 video | new video scenario | real playback, sample, pause/resume, stop, loop, restore |
| Ingress | ingress tests | upload/inventory denied on tablet, HEAD on asset only |
| Drill | deploy drill | restore renders |

## Parallel ownership

| Worker | Owns | Depends on |
| --- | --- | --- |
| runtime | `tabletwall/playback.py`, playback routes in `main.py`, backend tests | none |
| client | `frontend/client/**`, client/view tests | contract, runtime frames |
| controller | `frontend/controller/**`, library/playback/field UI | contract |
| parent | contract/docs, simulator/browser, ingress/deploy, integration, evidence | all |

Runtime lands first. Client and controller run in parallel against the
contract. The parent writes the browser video scenario after the server frames
exist and integrates.

## Explicit deferrals and risks

- Group rebuffer with a new common anchor and named exclusions: the client
  reports stalls and strict blocks; automatic group recovery is deferred with
  a visible failure state, not silently claimed.
- Reconnect mid-video resumes at the next occurrence or a fresh prepare; it
  does not reconstruct an exact mid-clip position. Documented and tested.
- Physical optical, suspend, iOS decode, local-CA trust on devices, and soak
  gates remain MISSING.
- A 930-line client insert is the main review risk. Keep video in one
  delimited section and add only needed helpers.
- The browser timing is software evidence on one host clock.
