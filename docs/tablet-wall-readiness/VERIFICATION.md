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

`ruff check .` was also tried and found 46 existing issues in simulator,
test-fixture, and optical-tool files outside the production lint target. The
repository's required `ruff check main.py tabletwall deploy` passes. Those
unrelated files were not changed to make this feature's checks green.

Outstanding evidence includes the consolidated desktop/mobile flows, complete
integration and security checks, and real-tablet calibration, recovery, and soak
acceptance. Experimental video tests are not evidence of usable tablet video.
