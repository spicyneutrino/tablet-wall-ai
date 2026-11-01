# Verification record

This record describes checks performed during implementation. It does not replace
the roadmap acceptance criteria or establish real-tablet results.

| Unit | Revision | Executable evidence | Result and limits |
| --- | --- | --- | --- |
| Python baseline | `0ff56e3` Python sources | `.venv/bin/python -m pytest -q` | 1,177 passed, three deprecation warnings, 109.30 s. Temporary test data; no tablet evidence. |
| Protocol 3 capability warning | `5a9cc29` | `node tests/controller_image_capability.test.js`; all ten `tests/*.test.js` suites | Pass. Fifty roster combinations, missing devices, and colour scenes. Independent reviewer also ran the new test against baseline and observed the intended failure. Rendered acceptance remains open. |
| Protocol capability documentation | `ef99cb8` | Source and protocol comparison | Protocol 2 or 3 plus the image capability is required. Capability does not establish successful rendering. |
| Physical image capability fence | `abb9c42` | Three new cases failed before the change with `type: image` instead of `type: color`; `tests/test_v3.py` (12 passed), `tests/test_wall.py` and `tests/test_hub_failures.py` (99 passed); Ruff | Pass. No image descriptor or plan is sent without advertised image support. No physical screen was observed. |
| Operator diagnostics and tablet sign-in admission | `15e21f6`, whitespace cleanup `981b2db` | Root field/deployment/ingress/auth selection: 99 passed. Independent Sol High review: 109 focused tests, 161 raw-path/method denial probes, 100 admission cases, duplicate credential stripping and Origin/session/redirect checks against temporary Caddy/backend processes | Pass for local HTTP behavior. Uploads can remain disabled while an operator reads diagnostics. Tablet routes admit exact login/logout methods and continue to deny operator paths. Deployed TLS and real hardware were not tested. |
| Capability summaries and prepared-image delivery | `18afa5c`, `3f9beee` | Controller module/capability/sizing checks passed. Prepared-image denial cases failed `True is False` before the new guard. V3, model, and playback HTTP selection: 52 passed afterward | Pass. The rotation fixture now represents an image-capable client and retains its geometry/history assertions. Experimental playback tests do not establish usable tablet playback. |
| Actual scene and merged image inventory | `7a73cbe` | Root operator-image/v3/model selection: 56 passed; worker's broader selection: 145 passed, Ruff and mypy passed | API foundation passes. Complete runtime read model, compatibility guard, and rendered UI remain open. |
| V3 static scene takes presentation ownership | `8ef4510` | New test first observed an active session remaining after static selection; operator-image/playback HTTP selection: 47 passed after the fix | API foundation passes. `PUT /api/v3/scene` stops the experimental presentation after commit; the operator UI migration remains open. |
| Image-state foundation regression | `6b5f8fd` | Complete Python suite: 1,213 passed, three dependency deprecation warnings, 93.94 s | Pass at this checkpoint, before later fit/layout/helper/client integration. |
| Global whole-image fit | `90cc8d6`, existing background preserved in `955179f` | Root: 78 client cases and 102 asset/fit/operator-image cases passed. Worker: 194 relevant Python cases passed, Ruff and mypy passed | Fit foundation passes; preview agreement and client capability integration remain open. |
| Cross-kind return points and empty-Apply guard | `805ce16` | New checks first exposed eight failures, including a late write persisting on disk. Fourteen transition cases pass; v3/model/transition selection: 45 passed; earlier adjacent selection: 268 passed; Ruff and mypy pass | Software boundary passes. Explicit clear is separate; real-device arrangement recall remains open. |
| Proxy operator-read configuration | `7dbf04b` | Three launcher cases failed before the guard; deployment/ingress/field selection: 41 passed afterward; shell syntax valid | Reference TLS proxy now requires its shared internal credential before launch. Trusted HTTP direct-loopback profile does not need it. No live deployment changed. |
| Render, arrangement and lifecycle planning helpers | `7610ff3`, `9f2fc09`, `2662242` | Root repeated 144 grid/render and 95 lifecycle cases successfully | Helpers pass focused checks; actual route/socket/transaction wiring remains open and is under independent review. |
| Tablet reporting, Identify, recovery and rulers | `15d36d4` | All current Node suites passed at root. Worker reports 148 client cases and private desktop/tablet/mobile browser checks; protocol extensions used explicit WebSocket fixtures | Actual private-backend logical contain rendering passed. New server transport and integrated operator flow remain open. Browser artifacts are outside the checkout in readiness-program/client/. |
| Calibration trust and diagnostic image helpers | `7c2b3d0` | Root repeated 82 calibration/pattern cases; worker Ruff/mypy passed and inspected a generated grid | Helpers pass focused checks; publication, route wiring, and physical accuracy remain open. |
| Complete foundation/helper/client checkpoint | `7c2b3d0` | Complete Python suite: 1,562 passed, three dependency deprecations, 78.80 s; JUnit `/tmp/tablet-wall-foundation-7c2b3d0.xml`. All Node suites passed; Ruff passed; mypy passed for 40 source files | Green software checkpoint before backend composition and unified-console integration. This does not close end-to-end acceptance. |

## Integrated software checkpoint

These checks supersede the earlier statements that route/socket composition
was pending. They do not close the full-journey or hardware gates.

| Unit | Revision | Executable evidence | Result and limits |
| --- | --- | --- | --- |
| Unified operator console and canonical evidence | `5b7c729`, `16ee0cd`, `50cc0b8` | All JavaScript suites; canonical state/token, independent monotonic age, cleared Identify, and offline VM fixture checks | Pass. Original worker browser evidence used fixtures for routes that were absent on its base. Those fixture checks are not integrated acceptance. |
| Composed operator routes and sockets | `b791dfe` | 278 worker-focused tests, including 45 composition cases. Root later repeated 384 helper/composition tests | Pass. Layout, labels, Identify/retry/reconnect, grid, snapshots, rebind, test patterns, historical pins, and transaction rollback are wired. |
| Operations and page protections | `705dbb3` through `ef06e87` | Root 52 readiness/health/CSP/offline checks. Worker backup drill, QR independently decoded, log retention/long-line/EOF checks | Pass for temporary HTTP loopback checks. Actual mounted routes are exercised in the operator composition tests. Readiness UI acceptance and deployed TLS remain separate. |
| Independent helper review corrections | `8c3356a` | Regression checks failed before fixes; 384 focused cases afterward. Common layout validation replaces duplicated lifecycle geometry checks while retaining snapshot extensions | Model CSS scale cannot become measured through panel provenance; model hints cannot bypass manual fences; malformed reports and unrepresentable grid/ruler/pattern arithmetic are refused. Offline telemetry cannot size a new reservation. |
| Complete integrated Python checkpoint | `8c3356a` | `.venv/bin/python -m pytest -q --junitxml=/tmp/tablet-wall-integrated-8c3356a.xml` | **1,684 passed**, three dependency deprecations, 85.21 s. All current Node suites, production Ruff, and mypy for 46 source files passed. |
| Fresh server review corrections | `9d91591` | New managed-file availability and socket/legacy regressions failed before fixes; 232 server/image/render/recovery/protocol tests passed afterward | Metadata is assigned before handshake awaits; late legacy controllers cannot observe a fake physical wall; missing managed bytes report unavailable without changing durable ETags. Experimental loop failures now become a visible failed state with bounded logging; this does not establish working video. |
| Actual browser image confirmation | `9d91591` | Private Uvicorn, temporary data, actual `client.js`, real WebSocket acknowledgements, desktop 1600×1000 and 390×844 / 800×600 views | Pass after fixing two remaining wall-clock callers. Header, stage, and roster agree on current display; no page errors or horizontal overflow. Artifacts at `/var/home/oak/.local/share/tablet-wall-ai/readiness-program/root-browser/`. Only one logical tablet was exercised here. |
| Explicit ruler decisions and pinned trust details | `7a2c6cc`, `2ee4659` | Root 171 route/calibration/composition checks, all 16 Node suites, production Ruff and mypy for 47 files. Repeated actual mounted-app browser journey passed 30 assertions at 1600×1000 and 390×844 | Keep supplied is nonmutating; Use ruler prepares a new calibration revision; input/viewport changes invalidate the decision; old profile and layout pins survive. Canonical pinned health, inset assumption, and both sides of the scale discrepancy appear in the tablet card. Artifacts `/tmp/twr12-operator-io4xhxq4/`; only deliberate invalid-span 422s appeared. Physical accuracy remains unverified. |
| Complete calibration-integrated checkpoint | `2ee4659` Python sources | `.venv/bin/python -m pytest -q --junitxml=/tmp/tablet-wall-calibration-integrated.xml` | **1,739 passed**, three dependency deprecations, 86.13 s. All 16 JavaScript suites, production Ruff, and mypy for 47 source files passed. Fresh review and remaining four-tablet/readiness/efficiency acceptance are still open. |
| Efficiency baseline | measured application `8c3356a`, harness `d4473c7` | [Method, measurements, raw artifacts and dispositions](EFFICIENCY.md). Root repeated four harness checks plus the atomic-grid route regression; scoped harness Ruff passes | Five interleaved rounds for one/four actual browser clients, accepted paint acknowledgements, 300-second console request/log window, and separate profiling run. The 2×2 apply produced one revision and broadcast. No optimisation or hardware/capacity claim. Current code has later review fixes; recorded timings describe the pinned measured application, not a fresh measurement of every later commit. |
| Security and operations red-team corrections | `4dace75` | New configured-Host matrix, injected ENOSPC with a live child, startup log-failure checks, production Ruff, and mypy for 47 files. Complete Python run `/tmp/tablet-wall-host-guard-final.xml`: **1,763 passed**, three dependency deprecations, 84.72 s | Configured foreign/ambiguous hosts are refused before HTTP/WS routing; unconfigured development is unchanged. Test fixtures use admitted loopback URLs rather than a production `testserver` exception. Logging failure stops supervision with an actionable error. Private actual Uvicorn/browser check rejects foreign Host with 400 and retains valid paint/consistent desktop/mobile status. |
| Fresh-shell operator recovery dry run | `4dace75` | Private actual wall stopped; all `TABLET_WALL_*` variables removed from the backup-tool subprocess environment; explicit source paths; backup, verify, and restore to new targets each returned 0 | Runbook now supplies source paths and creates backup/restore parent directories. The first restore attempt exposed the missing parent-directory step; the corrected dry run passed. Referenced curated bytes and revision were preserved. No live restore, service cutover, host reboot, or tablet rejoin was performed. Evidence in readiness-program/root-browser/checks.json. |
| Fresh calibration review corrections | `bbbbb0d` | Thirteen offset/revision regressions failed before the fix. Then 244 calibration/grid/composition cases and 184 focused cases passed; production Ruff and mypy for 47 files passed | Manual nonzero offsets remain in the health projection and prevent full-panel agreement; oversized profile revisions return 422 before SQLite lookup. A private actual tablet browser entered fullscreen, saved a translated manual calibration, and the operator card showed the retained 10 mm offset and coverage warning with `full_panel: false`, `ok: false`. Evidence in readiness-program/root-browser/explicit-offset-health.png and checks.json. |

`ruff check .` was also tried and found 46 existing issues in simulator,
test-fixture, and optical-tool files outside the production lint target. The
repository's required `ruff check main.py tabletwall deploy` passes. Those
unrelated files were not changed to make this feature's checks green.

## Final operator integration checkpoint

The following results supersede earlier pending statements about the integrated
operator journey. Independent re-review of the final corrections is still open.

- Integrated `bb48ce1` as `2bb6499`. The readiness card reads the mounted API,
  preserves unknown/error states, and separates a recorded manifest from a
  verified restore. Worker evidence had 77 checks but used a selection refresh
  workaround and left rebind blocked. Those two flows were not accepted then.
- `68c955c` preserves model-source history for same-hardware rebind using only
  unambiguous historical profile/scale snapshots. It refuses missing or
  conflicting source metadata and respects the model DPR fence. Focused checks
  passed. Its first full run retained an offline-origin scan failure caused by
  a dummy QR validation URL; the final correction uses the actual operator origin.
- Fresh independent review at `68c955c` passed 670 Python cases, all 17 Node
  suites, production Ruff and mypy for 47 files, and the adapted Host/logging
  security and recovery probes. It nevertheless **failed** on wrong-device
  actions in logical/compact views and an obsolete displayed QR after changing
  the tablet origin. Report `/tmp/tablet-review-68c955c-lm1qjl9p/REVIEW.md`.
- Root corrected those findings and the registration/reconciliation race.
  The selection notification runs independently of inspector visibility; label
  responses cannot replace another selection's edit baseline. New registration
  publishes a durable-config update after commit. A runtime event interrupting
  a read queues a new read. Own in-flight writes retain their response handling.
  The QR image source changes with the encoded tablet URL; old pixels stay
  hidden until the current image loads. Retry also requests a new image.
- `.venv/bin/python -m pytest -q
  --junitxml=/tmp/tablet-wall-final-software.xml` passed **1,782 tests**, three
  dependency deprecations, 85.43 s. All **17** `tests/*.test.js` suites passed.
  `.venv/bin/python -m ruff check main.py tabletwall deploy` passed.
  `.venv/bin/python -m mypy` passed for **47** source files.
- Actual private Uvicorn and four Chromium tablet contexts at 1024×768 CSS px,
  DPR 2, passed **106 checks**. Operator views were 1600×1000, 390×844, and 200%
  CSS zoom. The driver used the real routes, sockets and shipped client rather
  than backend fixtures. Logical and physical 2×2/1×4, global Fill/Fit including
  sampled letterbox pixels, current acknowledgements, induced image failure and
  retry, Identify/expiry, labels, Remove, Forget, re-registration, cross-kind
  saves/recalls, replacement, and recall of both saved kinds after replacement
  passed. List, keyboard and stage selection changed only the intended label in
  both layout kinds and both viewport sizes. No Refresh status workaround or
  model reconfirmation workaround was used. No unexpected page exceptions or
  failed network requests remained; the deliberately aborted image is excluded.
- Journey artifacts and rerunnable driver are at
  `/var/home/oak/.local/share/tablet-wall-ai/readiness-program/final-qa/20261101T120950Z/`.
  `results.json` contains checks and empty failure lists; `screenshots/` and
  `videos/` retain the actual run. Earlier failed runs are retained in sibling
  timestamped directories. Their failures include a real own-write ETag race,
  and two driver errors (assuming a model label contained a short ID and using
  CSP-disallowed string evaluation), both corrected before the passing run.
- `.venv/bin/python /tmp/tablet-wall-qr-refresh-check.py` started a private
  backend, decoded the displayed QR with independent `zxing-cpp`, restarted the
  backend at the same operator origin with a changed tablet origin, clicked
  Refresh readiness and decoded the new displayed pixels. Both addresses
  matched their corresponding text. Evidence `/tmp/tablet-wall-qr-refresh-wj8xo99d/`.

All owned servers and browsers were stopped. These are software browser checks,
not measurements of panels, bezels, physical seams, sleep, battery, or optical
synchronisation. Hardware, installed TLS/auth composition, host reboot, and
real-device soak remain unverified. Experimental video tests are not evidence
of usable tablet video.

### Additional phone-width and content checks

The same 106-check four-tablet journey was repeated with the operator initially
at 390×844 and restored to that width after the explicit selection matrix. It
passed with no page exceptions, unexpected failed requests, or remaining
workarounds. Artifacts are in
`/var/home/oak/.local/share/tablet-wall-ai/readiness-program/final-qa/20261101T135445Z-mobile/`.
The embedded selection matrix deliberately also visits desktop width; this is
not a claim that every assertion was executed only at phone width.

A further actual-app check found that generated Black wall / Wall-sized grid
controls expected fixture-only nested metadata while the mounted route returns
a flat image DTO. The handler now consumes the canonical result and adds the
published metadata to its local library before selecting the scene. This avoids
requiring another refresh or briefly marking the new pattern unavailable. The
new `node tests/operator_content.test.js` fails against the old handler and
passes after the correction. Before-fix failure is retained at
`/tmp/tablet-wall-pattern-regression-before.log`. All 18 JavaScript suites pass.

The launcher now prints `/controller/physical.html`, the primary operator
surface, in both preflight and Ready output. The README and image-wall runbook
now name the actual tabs and controls, the two layout kinds, Fill/Fit, QR card,
and recovery scope. `.venv/bin/python -m pytest -q tests/test_hotspot.py` passed
29 cases. Production Ruff and mypy for 47 source files pass. No network settings,
service, or live installation was changed.

The added private-backend content/recovery run passed 17 behavioral checks plus
one recorded recovery-time observation. It exercised Tablet colours, Black wall,
Restore previous content, long Unicode labels with reduced motion, keyboard
tabs and Preview/Cancel, targeted Reconnect, hidden-state exclusion, and
hidden/offline recovery after a server restart without reloading the client.
It also generated and painted the measured wall grid from the actual **Wall**
tab, checked that logical calibration is disabled in measured mode, inspected
visible control names and a keyboard focus outline, and exercised an actual
401/sign-in form round trip after enabling auth on a restarted private backend.
The client retained its identity. This tests loopback auth behavior, not the
installed TLS/proxy deployment. Evidence and the rerunnable driver are in
`/var/home/oak/.local/share/tablet-wall-ai/readiness-program/final-qa/20261101T140548Z-recovery/`.
No operator page exceptions remained. Earlier driver errors are retained in
sibling runs; they included wrong tab/DTO assumptions and an unaccepted native
confirmation, not additional accepted product results. Owned servers and
browsers were stopped after every run.

The content/recovery driver was repeated with stronger paint predicates requiring
`current: true` and the accepted token's generation, revision and asset to match
the current config, in addition to `state: displayed`. All 17 behaviors plus the
recorded timing observation passed again. Evidence is in
`/var/home/oak/.local/share/tablet-wall-ai/readiness-program/final-qa/20261101T140721Z-recovery-current-token/`.
This supersedes the weaker displayed-state-only recovery predicate above.

Fresh independent review **passed `0529eaa`**. It repeated the full 106-check
journey and 168 focused Python cases, all 17 then-current Node suites, 24 extra
actual-browser race assertions, and 15 sync event-order cases. Delayed label
responses preserved both untouched and edited selection fields; interrupted
config reads refreshed without a workaround; delayed/failed QR image responses
kept old pixels hidden and Retry fetched current independently decoded pixels.
The exact-source report is `/tmp/tablet-review-0529eaa-pxDG5e/REVIEW.md`.
Later generated-pattern/entry-point changes are under a separate bounded review.

A further keyboard-only four-client check reproduced focus returning to `body`
when Move earlier/later disabled the control at the ordering boundary. The
handler now focuses the other enabled direction at that boundary. The same
actual-browser check passes at both first and last positions. Sampled computed
text colours for the active task tab, topbar note and grid heading exceed
4.5:1 contrast. This is a sample, not a WCAG conformance claim. Before-fix
artifacts are in `final-qa/20261101T141043Z-keyboard/`; passing results and
screenshot are in `final-qa/20261101T141121Z-keyboard/` under the same
readiness-program directory. No backend or library state from the live wall was
used. All owned processes were stopped.
