# Audit rounds

Each completed round includes both operator pages at 390x844, 820x1180, and 1440x1000 with console, page, response, and failed-request capture. Evidence lives outside the repository, with summaries committed here.

## Round 1, baseline, empty state, architecture

- Python 3.13.13. `make test` passed 996 Python tests and 93 JavaScript checks.
- Controller browser suite passed 95 checks. Field suite passed 22 checks.
- Viewport audit `/tmp/tw-round1/report.json` passed all six rendered page/viewport combinations with no errors and no document overflow.
- Reviewed screenshot `/tmp/tw-round1/phone-physical.png`, tab controls, empty-state next actions, and touch layout.
- Findings B01 through B13 seeded from the seven requested lenses. Work remains open.

## Round 2, connected tablet, persistence and typed failure paths

- Viewport audit `/tmp/tw-round2/report.json` passed all six page/viewport combinations with a live simulated client, no console/network errors, and no document overflow.
- Code audit found existing typed paths conflate clock pending evidence and playback preparation and fail optional-value checks. Tracked B14.
- Backup code already snapshots database, referenced media/video, curated images, and playlist closure. Docs still describe older shapes. Tracked B15.
- Existing physical layout editor includes Undo/Redo; logical console has all-device colors; system tab offers diagnostics download. Verify and improve these paths instead of duplicating them.

## Round 3, offline recovery and actual browser authentication

- `/tmp/tw-round3/report.json` initially failed because deliberate offline errors were classified as unexpected. The harness now records the deliberate probe interval and only recognizes its explicit transport errors as expected.
- `/tmp/tw-round3-retry/report.json` passed all six combinations; each viewport returned to a current configuration after offline/reload, with no unexpected errors.
- Authentication browser testing found a real Chromium form failure with Referrer-Policy no-referrer. Tracked B16; fix and repeat live cookie/WebSocket verification required.
- Python state boundary fixes passed all 996 Python tests and all JS suites before diagnostics extraction.

## Round 4, security, shared caches, transaction failure, and corruption

- `/tmp/tw-round4/report.json` passed all six rendered page/viewport combinations with a connected tablet and offline recovery. No unexpected browser errors.
- Independent review reproduced protected assets advertising public caching, partial delete/rebind persistence, stale heartbeat contact times after restart, and present-null roster corruption. Tracked B17 through B20.
- Authenticated responses now use private, no-store. Auth regression batch passed 288 tests; real Chromium login and live HTTP/WebSockets passed at 375, 768, and 1440 pixels.
- Diagnostics extraction first failed 15 tests after an import removal; restoring shutil fixed the full suite. All three route extractions were verified separately before commit.
- Tooling baseline counts subprocesses and passes an 80% combined coverage floor. Nine targeted hub error/reconnect tests raise hub coverage from about 74% to 97.16% combined.

## Round 5, authenticated operator flows and stale health feedback

- `/tmp/tw-round5-retry/report.json` passed all six rendered page/viewport combinations with real form login, HttpOnly Strict cookies, API/static anonymous denials, and offline recovery.
- Initial run caught navigation cancellation in the test harness immediately after login; waiting for network-idle before the next navigation removed this instrumentation error without suppressing failures.
- Integrated authentication/tooling suite passed 1087 Python tests and 93 JavaScript checks. Production lint and strict optional typecheck pass.
- Frontend audit found failed roster refresh silently retains old online counts, tracked B21. Health overview and explicit stale/retry feedback are in progress.
- Ranked feature audit confirms existing bulk colors, physical undo/redo, diagnostics download, and complete backup/restore flow. New work targets visible health and freshness feedback.

## Round 6, keyboard, rejected writes, and module failure paths

- `/tmp/tw-round6/report.json` passed all six authenticated rendered combinations, keyboard focus checks, live simulated clients, and offline recovery.
- Invalid dimension requests returned 422 and preserved the complete wall. A foreign Origin returned 403 despite a valid bearer token. Anonymous API and static reads returned 401.
- Independent review reproduced a missing ApiError constructor dependency in extracted playback error handling. Tracked B22 before frontend integration; happy-path browser/unit checks had not covered that branch.
- Backup/restore rendered drill `/tmp/tw-restore-integrated/report.json` passed 41 of 41 checks, including database/media closure, byte identity, and restored playback.
- Backend integration review passed 109 targeted tests, confirmed no awaits in shared transaction bodies, and found no remaining auth/roster/cache/worker blocker.

## Round 7, integrated restart boundaries and authenticated empty states

- `/tmp/tw-round7/report.json` passed all six authenticated rendered combinations, keyboard focus, invalid-write immutability, foreign-Origin denial, and offline/reload recovery.
- Fresh audit followed closure of B01-B05. Backend review confirmed safe offline restoration, corrupt-null startup refusal, atomic delete/rebind failure handling, and one runtime owner.
- `make test` passed 1125 Python tests plus 93 JS checks after robustness integration. `make lint` and `make typecheck` passed.
- No new broken, confusing, or missing findings. Previously identified frontend B21/B22 remain open pending integration.

## Round 8, landscape and wide-screen responsiveness

- `/tmp/tw-round8/report.json` passed both operator pages at phone landscape 844x390, tablet landscape 1180x820, and desktop 1920x1080.
- Real authentication, live tablet connections, keyboard focus, invalid-write immutability, foreign-Origin denial, anonymous denial, and offline recovery passed. No document overflow or unexpected console/network errors.
- No new broken, confusing, or missing findings. This round followed closure of five tooling/extraction/document-review findings.
- Six controller extractions each passed the full baseline suite before their individual commits. Playback error correction passed the full suite and dedicated 412/409/repeated-conflict tests.

## Round 9, fully integrated frontend and repeatable tooling

- `/tmp/tw-round9/report.json` passed all six portrait page/viewport combinations after frontend integration, with authentication, keyboard focus, invalid writes, CSRF rejection, and reconnect recovery.
- Final controller acceptance passed 95 checks; field acceptance passed 22 checks. Health fault injection at 390, 820, and 1440 pixels passed visible stale state, retry availability, and successful recovery with no page errors (`/tmp/tw-health-final/report.json`).
- Running the actual benchmark after route extraction exposed a StopIteration in its endpoint discovery, tracked B23. The tool now binds the real extracted route and clears inherited TABLET_WALL settings.
- Repeated benchmark `/tmp/tw-final-benchmark.json` completed five alternating rounds, 15 valid responses and 60 current-file reads per side, 60 versus zero decodes, and zero errors.
- Integrated coverage passed 1125 tests at 82.04% combined, including subprocesses. No coverage claim relies on the discarded measurement that omitted subprocess work.

## Round 10, final landscape flow and data safety

- `/tmp/tw-round10/report.json` passed both pages at landscape phone/tablet and wide desktop sizes, including real authentication, live clients, keyboard focus, rejected writes, Origin denial, and offline recovery.
- No new broken, confusing, or missing findings. All previously tracked local issues have verified fixes.
- Final `make test` passed 1125 Python tests, all 93 original JS assertions, and the two new module/playback contract suites. `make lint`, `make typecheck`, and `node --check` on all 10 frontend scripts passed.
- Read-only SQL dumps of the real database and SHA-256 of every real media file still match the initial external backup.
- Reviewed final landscape tablet screenshot; layout, health summary, tab controls, and system diagnostics remain readable without document overflow.

## Round 11, extracted script delivery and final portrait recovery

- `/tmp/tw-round11/report.json` passed both operator pages at phone, tablet, and desktop portrait sizes with real authentication and offline recovery.
- Every frontend script matched its on-disk bytes over authenticated HTTP. Every script ETag revalidated to 304 and retained private,no-store caching. Anonymous requests remained denied.
- Keyboard focus, invalid dimension immutability, and foreign-Origin rejection passed. No unexpected page, console, response, or failed-request errors.
- No new broken, confusing, or missing findings. Rounds 10 and 11 are the final consecutive clean rounds after all application fixes.
- Durable copies of all eleven successful round reports, final controller/field/restore results, and health error/retry checks are in `docs/audit/`. Earlier failed verifier attempts remain described above rather than counted as successful rounds.
- Four optional polish items remain. Physical tablets, Safari, optical timing, real-network behavior, TLS trust, and host service installation are pending manual validation.
