# Next actions after the Stages 3-5 milestone (Sol xhigh, 2026-10-24)

Claude Opus 5.5 was requested but hit its API rate limit twice. It reproduced
three defects before failing: commit fan-out stopped on one closed writer, a
wall frame painted over playback, and a mapping change could commit old
geometry. All three are fixed (`24db7ff`, `e52d4bf`). Sol produced this plan
as the fallback advisor.

## Order

Software-completable:
1. Integrate the controller UX worker. Verify saved-versus-draft playback,
   strict defaults, rebind, keyboard scope, stale polling and desktop/mobile
   states against the merged HUD.
2. Close the active-session rebind risk. Rebinding moves a physical slot and
   closes a socket without aborting playback; apply the mapping-change abort
   and test it. Done in `eb4bc12`.
3. Complete missing evidence: play restored video in a browser; exercise
   HEAD, ranges, validators and admission through a disposable real Caddy.
4. Implement bounded group recovery with a fresh common anchor, then reuse it
   for mid-video reconnect. Add named exclusions after.
5. Defer automatic quality fallback until a device trial identifies a useful
   common lower profile. Ingest remuxes; transcoding is separate scope.

Hardware-blocked: optical cut timing, real decode/suspend, iOS Safari, mixed-
model calibration, installed local-CA trust, deployed Wi-Fi/OS, kiosk, soak.
Start with a mixed-device pair before fleet expansion.

## Next feature: bounded group video recovery

One authoritative recovery record: occurrence, recovery position, version,
reason/member, deadline, attempts, degraded interval.

Acceptance:
- A confirmed stall, playback failure or exhausted local recovery triggers one
  versioned group recovery. Ordinary drift stays local.
- Recovery cancels the prepared next item and freezes the group. Old timers,
  callbacks, commits and readiness cannot advance it.
- All required members prepare the same occurrence and position. Readiness
  checks buffer ahead of that position, including the remainder near the end.
- Fresh leases permit one future common anchor. The following boundary uses
  the remaining duration.
- Timeout or exhausted attempts produces a named blocked/failure state with
  Retry and Stop. Strict never silently shrinks the cohort.
- Status retains reason, missing members, attempts and degraded interval.
  Repeated reports cannot create a recovery storm.
- Stop, mapping changes, epoch changes and socket replacement supersede safely.

## Parallel split

- Server: `tabletwall/playback.py`, `main.py`, `PROTOCOL.md`, playback tests.
- Client: `frontend/client/client.js`, client tests.
- Evidence: `simulator/browser/video_run.py`, a recovery runner,
  `tests/test_backup_video.py`, ingress smoke.
- Controller: `physical.*` remains with its current UX owner; recovery
  presentation is a dependent follow-up.

## Design memo decisions

Take now with the controller worker: compact idle transport, reachable
selection/calibration, saved-playlist preflight, numbered roster/readiness,
guided rebind, actionable failure copy, quieter technical details, stale
indicators, contrast, scoped arrow keys, touch targets. Keep the stage model.
Verify the HUD/pill/failure notice rather than rebuilding.

Defer: playlist-remove undo, exact breakpoint tuning beyond observed problems,
an extra tablet rebind acknowledgment, quality-selection UI.

Correct:
- "Save and start" must wait for a successful conditional save; a conflict
  must block Start. Resume keeps the frozen session.
- Offline/unsupported strict members stay visible in preflight.
- Rebind must disclose saved layouts keep the old id; copied calibration is not
  proof a replacement is physically calibrated.
- Plain HTTP reports `insecure`; do not relabel it unsupported.
- Remove routine Refresh but keep recovery after poll failures.
- Stop restores the persisted scene, not "leaves it on screen".
- Details must preserve missing-member reasons, focus order and one transport
  announcement.

Do not: reopen R3/R4/R5, add crossfades/audio/live streaming, build quorum
variants, add per-tablet automatic quality, mask stalls with indefinite
retries, or count posters as synchronized video participants.
