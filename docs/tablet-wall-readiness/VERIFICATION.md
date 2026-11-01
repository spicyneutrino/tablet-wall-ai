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
| Static scene takes presentation ownership | `8ef4510` | New test first observed an active session remaining after static selection; operator-image/playback HTTP selection: 47 passed after the fix | Pass. Static selection stops the experimental presentation after the new scene is committed. |

Outstanding evidence includes the consolidated desktop/mobile flows, complete
integration and security checks, and real-tablet calibration, recovery, and soak
acceptance. Experimental video tests are not evidence of usable tablet video.
