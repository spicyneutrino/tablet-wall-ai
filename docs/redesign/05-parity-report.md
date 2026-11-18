# U33 parity report

## U33 driver retargeting

All runs were from the repository root with
`PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright` and `PYTHONPATH=.`, using
`uv run --group browser python simulator/browser/<driver>.py` with the driver's
documented flags. The full before/after captures are in `/tmp/u33-before/` and
`/tmp/u33-after/`. The old-console route is no longer referenced by any of the
14 in-scope drivers; incidental setup goes through `simulator/browser/_api.py`,
which sends the operator `Origin` and takes `If-Match` from a fresh
`GET /api/v3/config`.

Two conditions were already true before this unit and shape several "before"
columns:

1. The deployed CSP is `script-src 'self'`, so Playwright's string-form
   `wait_for_function` (which calls `eval`) fails on controller pages that use
   it. Several drivers aborted before writing a check report.
2. Legacy `/scene` writes are refused with "Upgrade controller: a physical
   layout is active".

`pytest -q` was run twice with the same environment: **1924 passed, 2 skipped**
before and **1924 passed, 2 skipped** after. (An earlier baseline of
1909/3 was taken before the browser dependency group was installed; the 15
newly collected tests are `tests/test_redesign_driver*.py` and
`tests/test_redesign_edge_cases.py`, and their count is unchanged by U33.)

### field_run

- Command: `--artifacts /tmp/u33-…`
- Before: aborted at `physical.html` — CSP blocked the `#rebind-new` option wait; no check report was written.
- After: exit 0, 14/14 checks passed.
- Tablets/server: unchanged — registration, wake-lock, diagnostics shape/admission, origin refusal, rebind placement/number, reconnect and reload checks all passed.
- Retired with the old console: eight checks with no server or tablet evidence — the old console's diagnostics export envelope (its `format`, timestamp and "physical validation pending" label are added by `physical.js`, not the server), the injected integrity-error and failed-refresh messages, mobile overflow, task-tab keyboard navigation, Home/End selection and reload-preserved task. These are covered by the new app's parity specs. The diagnostics verify/refresh and rebind flows now use `Api.diagnostics()` and `Api.rebind()`; the raw verified payload is still saved as `diagnostics.json`.

### group_recovery_run

- Command: `--artifacts /tmp/u33-…`
- Before: 15/20 passed. The five failures were all controller-page checks (CSP-blocked waits and stale UI).
- After: 19/19 passed.
- Changed results (all FAIL → PASS): "the controller sees the live session before the fault", "the controller keeps the recovery record after the commit", "the controller dwell does not exceed the remainder and cut lead", "no unexpected client page, console or request errors".
- Retired: "recorded-cap fixture copy reads as one sentence and offers Retry". It asserted old-console presentation of a locally built fixture response, with no server or tablet evidence; the live blocked transition is checked in `recovery_acceptance_run`.
- Root cause: the remaining checks now assert the same facts through `GET /api/v3/playback` (state, recovery attempts, pending cut time) instead of reading old-console DOM through a CSP-blocked page. Every tablet-side advance, visibility, sample, pixel and cut check is unchanged.

### recovery_acceptance_run

- Command: `--artifacts /tmp/u33-…`
- Before: 81/84 passed; three `*: the scenario completes without an exception` checks failed.
- After: 88 checks; the strict-cap, online-cap and recovery-timeout scenarios now complete, so those three failure-only checks are no longer emitted. The other differences are device UUIDs inside check names (fresh registration each run) and checks reached in later scenarios because the earlier ones no longer abort.
- Controller setup replaced by `Api` playback reads; operator Retry is `POST /api/v3/playback/retry` with a fresh version. All live-video, fault, cap, hold, sample and pixel checks are unchanged.

### recovery_run

- Command: `--artifacts /tmp/u33-…`
- Before: aborted at the legacy `/scene` write ("Upgrade controller: a physical layout is active").
- After: setup now uses `Api.scene()` against `/api/v3/scene`; the 20-trial offline/online loop starts and runs.
- Not runnable here: the full run is a ~12-minute soak (20 trials × ~37 s) and exceeded the 240 s harness limit, so no final report was produced. Verified with `py_compile` and by observing that setup and the first trials ran. No named checks are produced by this driver (trial rows only).

### health_run

- Command: positional artifact directory.
- Before: aborted at `bounding_box()` on `#btn-wall-health` (zero checks).
- After: exit 0; the three named width checks ("390/820/1440px health overview, stale failure feedback, enabled retry, restored fresh state") pass against `GET /devices` and `GET /diagnostics`.
- Root cause: the original assertion depended entirely on old-console DOM. The failure/retry presentation itself is a controller-UI concern and is covered by the new app's parity specs; the tablet connection and server roster checks are unchanged.

### image_efficiency

- Command: `--artifacts … --rounds 5 --idle-seconds 1` (short mode; defaults are 300 s idle).
- Before: exit 0. After: exit 0. Report has no named PASS/FAIL checks; the benchmark fields are unchanged.
- The idle page now opens `/controller/app/` instead of the old console, so the idle network/log measurement targets the console that survives switch-over.

### fleet_soak

- Command: `--artifacts … --duration 5 --interval 0.5` (minimum allowed; real soak is 2 h).
- Before and after: 18 named checks, identical names and results (the short run fails the "boundaries changed at least twice" checks by design). No change to this driver — it has no old-console reference; all setup is already REST. Not runnable here as a real soak.

### audit_round

- Command: `--round 1 --artifacts …`
- Before and after: 1 named check ("all viewport document widths fit"), same result. Both fail on a pre-existing aborted font request (`SchibstedGrotesk-wght.ttf`), unrelated to U33.
- The viewport walk no longer visits `/controller/physical.html`; it visits `/controller/` only. Check names and counts are unchanged.

### experience_acceptance

- Command: `--artifacts … --browser <chromium>`
- Before and after: not runnable here — `ImportError: cannot import name 'TASK_TABS' from '_redesign_edge_cases'` at import time. This is a pre-existing breakage of the driver's helper import. No check report is produced. The driver is entirely old-console UI evidence and its obligations are already rewritten as TS specs; no change was needed to remove a `physical.html` literal from this file.

### decode_probe

- Command: `--artifacts …`
- Before and after: exit 0, 40 named checks, identical names and results (desktop Chromium/WebKit probe page only; no operator console). No change.

### controller_run

- Command: `--artifacts …`
- Before: 4 checks from the browser audit; aborted in a CSP-blocked string wait.
- After: 4 same checks; aborted because the new app has no `#playback-details` element for its controller-side setup.
- Not runnable here as a controller-side check driver: its 90 named checks read old-console DOM (tabbed rail, playlist rows, countdown, dirty dots). Those checks were rewritten in U30; this unit removes the `/controller/physical.html` dependency by targeting `/controller/app/`, but the remaining DOM assertions belong to the new app's specs. Tablet-side playback evidence is carried unchanged by `video_run`, `group_recovery_run`, `recovery_acceptance_run` and `reconnect_exclusions_run`.

### video_run

- Command: `--artifacts …`
- Before: aborted at the Settings tab / CSP-blocked wait; 7 audit checks only.
- After: reaches 21 checks. Playlist save, playback start/pause/resume/stop and the "controller" copy checks are now API-backed through `Api.playlist()`, `Api.playback_start()`/`playback_stop()` and `GET /api/v3/playback`, with the original check names preserved.
- Correction (follow-up): the remaining failure was not an environment or fixture issue. The conversion posted resume to `/api/v3/playback/resume`, which does not exist (the server resumes through `POST /playback/start` while paused), so the clip stayed frozen at the paused time (~1.24 s). It also read the session while still `preparing` and saved the playlist with `loop` off where the old editor defaulted it on. Fixed in the driver; it now exits 0 with 34/34 checks, including the new "resume from the editor leaves paused".

### video_transitions_run

- Command: `--artifacts …`
- Before and after: exit 0, 51 named checks, identical names and results. No change — this driver already sets up through REST.

### reconnect_exclusions_run

- Command: `--artifacts …`
- Before and after: exit 0, 21 named checks, identical names and results. No change — this driver already sets up through REST.

### Summary of differences

- No in-scope driver references `physical.html`.
- Drivers with an unchanged named-check set: `fleet_soak`, `audit_round`, `decode_probe`, `video_transitions_run`, `reconnect_exclusions_run`, `controller_run`.
- `field_run`, `health_run`, `recovery_acceptance_run` and `video_run` previously aborted before emitting their full check lists; after the conversion they reach their tablet/server checks. `group_recovery_run` lost one old-console presentation check. All controller-UI-only assertions without server evidence were retired and are listed above.
- `recovery_run` is a long soak and `experience_acceptance` is broken at import; both were converted/verified without a full run.

## Final gate (2026-11-18)

- `uv run pytest -q`: see commit message for the count (1874 passed after the switch-over removed the old drivers' self-tests).
- Node contract tests: Controller module, wall sizing and URL locality checks passed.
- `make sim`: 23 of 23 scenarios, 1094 of 1094 checks passed; 18 self-tests passed.
- `make app-check`: passed (typecheck, unit tests, reproducible committed build).
- Playwright, Chromium (phone, tablet, desktop): 273 passed, 0 failed, 0 skipped.
- Playwright, WebKit (content and arrangement parity rows): 18 passed, 0 failed.
- `grep -rn "test.fixme" e2e`: 0.
- Backend and tablet client unchanged since the rebuild began (`git diff --stat` on main.py, tabletwall, frontend/client prints nothing).
- Owner decisions: 25% laptop wall coverage (X1), screenshot set approved (X5), wording aligned with the mockup, How to restore added.

## Follow-up fixes (2026-11-18)

Items 1–8 from `followups.md`, merged into `redesign/controller-app`:

- **readiness_acceptance:** it is retargeted off the old console. It keeps 88 checks with their original names, which read tablet pixels, the server API or `experimental.html`. The setup it used to do in the console now goes through `simulator/browser/_api.py`, which has a new `Api.grid()`. 61 checks read only the console; they are retired. Each one maps to its parity row through §6 of the build plan:
  - D1: confirm dialog, model prompt
  - V1: empty-wall header and upload copy
  - S1/T6: provenance cards
  - A1/A4: grid preview copy and confirm
  - C2: console naming, reload and Restore
  - C4: legend, hatch and estimates
  - S1: failure cards and Retry
  - T1/D4: list labels
  - T5: rebind preview labels
  - A5: recall confirms
  - D3: fence cards
  - C6: upload picker
  - P2: experimental playback
  - T1: console paint

  It also drops the two operator-page console and request checks, because there is no operator page any more. `_workspace_shell.py` was used only by this driver and is deleted. Result: `--artifacts <dir>` exits 0 with 111/111 on two runs. `phase_failure` and `phase_label` now prove their evidence only through `wait_until`.
- **video_run:** it exits 0 with 34/34 on four runs. The cause is in the video_run section above.
- **Video playlist e2e:** the new spec `e2e/video-playlist.spec.ts` uses a clip generated by `e2e/fixtures/video.ts`. It found and fixed two app bugs. An uploaded video was auto-selected as an image preview. A newly added video counted 5 s instead of its own `durationMs`.
- **X14 WebKit:** the app already prompts. A probe in WebKit showed a `beforeunload` dialog with a draft and none without one. In Playwright WebKit, a `goto` never settles after its dialog is dismissed, so the test no longer awaits it. The assertions are unchanged. Branded Safari is not tested.
- **P2:** the flake reproduced only under heavy CPU load. The server bumps the playback version at every cut, and the app retries a stale write once. The fix is in the test only: pause and resume are found by path, dwell is 3 s, and Next is clicked just after a cut. Results under load went from 42/45 to 45/45 and from 59/60 to 60/60.
- **Conflict review:** a resized tablet is named with its new size, for example "Tablet 1 now 900 × 450". The X5 `conflict-*-desktop` baselines are updated for this, and only those.
- **Next step:** when a placed tablet is offline and a new tablet has joined, the card adds the candidate and a Review replacement action.
- **Board status:** `shell.css` capped `.state` at 42% of the already narrow report column, so "Not placed" wrapped at 1440. The cap is removed. `e2e/board-status-line.spec.ts` guards it.

Gate on the merged branch:

| Check | Result |
| --- | --- |
| pytest | 1874 passed |
| make sim | 22 scenarios, exit 0 (all ok) |
| make app-check | passed |
| Vitest | 303 passed |
| Playwright, all Chromium projects | 278 passed, 1 failed. The failure was X5 conflict-light desktop, which is the intended copy change; the baseline was updated and X5 then passed 3/3 |
| WebKit, C*, A* and X14 | 20/20 passed |

The full `webkit-desktop` suite has never been part of the gate. It has 9 failures outside that set, listed in `followups.md`.
