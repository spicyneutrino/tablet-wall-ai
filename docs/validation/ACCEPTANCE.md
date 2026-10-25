# Frozen validation acceptance record

Frozen 2026-10-25 before hardware measurements. This record fixes the target
numbers used by the validation kit. It does not record a pass. All eight gates
remain **MISSING** until the operator signs a result row.

## Sources

| Source | SHA-256 | Note |
| --- | --- | --- |
| `../planning/tablet-wall-roadmap-2026-10-23/ROADMAP.md` (untracked planning artifact) | `d8aebc2d89785e122eb604374a45d98719c45f9392b655f615c69222cbc0ff16` | Targets at lines 500-522; retain the artifact. |
| `/tmp/tablet-wall-codex-work-review-2026-10-25/review.md` (review outside the checkout) | `101b6ff332668e307c8bd1d644a59f4171cc31f44b93f0127d1b24e75efe26e9` | Physical/deployment validation plan. |

## Frozen targets

- **Optical still cuts:** at least 100 events. Per-event wall-wide visible
  onset max-minus-min p95 ≤ 100 ms and max ≤ 250 ms. Missing transitions fail
  their events. Report camera/exposure/rolling-shutter uncertainty, same-panel
  noise, full-run and declared steady-state values, every unobserved and
  recovery interval. Raw capture and analysis stay outside the repository.
- **Physical video decode/suspend/recovery:** ten-minute clean run with no
  unplanned stalls. Outside declared startup/recovery windows, optical p95 ≤
  100 ms and max ≤ 250 ms. After a completed rebuffer, converge within 5 s or
  fail explicitly. Zero superseded paints. Exact device/build/power matrix
  recorded.
- **iOS Safari:** supported physical iPad models and intended iPadOS/Safari,
  trusted actual origin, tab and Home Screen launch. Page/register/socket/
  media, muted inline play or an actionable activation request, geometry,
  pause/resume, recovery and background/return must work. Same optical and
  connectivity targets. Desktop WebKit does not close this gate.
- **Mixed-model calibration:** adjacent-edge seam displacement ≤ 2 mm beyond
  the intended hidden gap, with uncertainty and photos at every adjacent edge.
  Independently measured active dimensions; no DPR-derived physical claim.
- **Installed CA trust and origin migration:** each real browser opens the
  intended tablet origin with no warning and works with WAN absent; the
  backend is unreachable from the LAN; tablet routes and operator admission
  hold; rebind after origin/storage loss preserves slot/number and records
  saved-layout/calibration consequences.
- **Real Wi-Fi/OS:** correct content within 10 s of connectivity restoration
  over at least 20 trials; retain all trials, failures and the distribution.
  Intended 15-20-tablet capacity remains a trial target until the operator
  specifies the release cohort.
- **Kiosk:** devices stay on or return to the intended page under the agreed
  OS procedure; measured viewport/calibration stays valid; operator can enter
  and exit safely; recovery meets the same connectivity targets.
- **Soak:** at least a two-hour media soak; overnight still soak if unattended
  operation is required. The overnight duration and acceptable
  resource/temperature envelope must be agreed before the run. No unplanned
  stalls, lost members, stale paints or unexplained restarts; optical targets
  apply to any claimed interval.

## Accepted policy, not a gate

- The recovery window is the ordinary ~31 s preparation deadline. Retry is
  offered for strict blocked; online failed offers Start again.
- Session-only exclusions and one-attempt automatic reconnect are accepted
  behavior; they do not relax any hardware target.

## Sign-off template

`gate | date/time | app SHA | equipment | scenarios | full-run/steady-state |
failures | unobserved | artifact hashes | operator | verdict`

Until a signed row exists, the gate is **MISSING**.
