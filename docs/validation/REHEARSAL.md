# Kit rehearsal record (2026-10-25)

This is the kit acceptance rehearsal. It is **not** hardware acceptance: no
tablet, iPad, camera, AP or installed-trust session was available
(`adb devices` and `idevice_id -l` were empty). All eight gates remain
**MISSING**; every report carries `hardware_gate_status = MISSING` and
`hardware_claim = false`.

## What ran

| Tool | Command / evidence | Result |
| --- | --- | --- |
| Optical analyzer tests | `pytest -q tests/test_optical.py` | **40 passed** |
| Optical synthetic suite | `python -m tools.optical.cli fixtures ...` then `analyze-suite` | **19 cases, 0 errors**; 19 reports `incomplete` because each has fewer than the required 100 real events. The suite includes known offsets, threshold boundaries, subframe/rolling-shutter, exposure/noise, partial/wrong/missing, repeated colours, variable timing, dropped/duplicated frames, truncated capture and early cut. Expected failure cases report their failures rather than being hidden. |
| Device probe | `python -m simulator.browser.decode_probe --artifacts ...`, twice | **40/40 checks**; desktop Chromium and WebKit passed; `ios-safari` **unsupported**. Completion remains `incomplete`; gate MISSING. |
| Trust checker | disposable Caddy, two loopback HTTPS listeners, fresh local CA; `python deploy/trust_check.py ...` | **72/72 checks, 8/8 scenarios**; supplied CA bundle is verifier trust only; backend/tablet route matrix checked; installed tablet trust remains manual. |
| Calibration checker | synthetic worksheet; `python tools/calibration/check_measurements.py ...` | **1/1 checks/scenarios**; pass/fail/inconclusive rule exercised in tests; physical measurements/photos remain manual. |
| Fleet soak harness | `python -m simulator.browser.fleet_soak --duration 60 --clients 4` | **22/22 checks, 6/6 scenarios**; four clients, shared host; not the two-hour media or overnight still run. |
| Network trial harness | `python deploy/network_trials.py --dry --artifacts ...` | **7/7 checks, 20/20 trials**; loopback context offline/online, not Wi-Fi/AP/OS. |
| Kiosk | `docs/validation/KIOSK-CHECK.md` + `deploy/KIOSK.md` | checklist only; no physical device or OS settings. |
| Full Python | `pytest -q` | **995 passed** (3 deprecation warnings). |

Artifacts were written outside the checkout; they are bounded and hash-listed
in each report. The server/browser runners record their own cleanup checks;
the optical and calibration tools have no server or browser to clean up. The
optical synthetic reports are intentionally not `complete`; the analyzer must
not invent the 100-event hardware sample.

## What this proves

- The analyzer accepts explicit timestamps, ROIs, events, camera/exposure and
  rolling-shutter metadata, detects visible onset and reports per-panel
  intervals, conservative bounds, missing/ambiguous events and failures. It
  does not prove a panel.
- The device probe records the fields needed for a physical decode/suspend
  run and runs on desktop Chromium and WebKit. It does not prove iOS Safari,
  a tablet decoder or a physical suspend.
- The trust checker verifies a supplied chain/SAN/fingerprint and the route
  matrix over verified TLS. It does not prove a tablet's installed trust.
- The calibration checker enforces the 2 mm seam rule with uncertainty and
  rejects derived-only methods. It does not replace ruler/photos.
- The fleet/network harnesses run, sample and report; they do not close the
  two-hour/overnight soak or real Wi-Fi gates.
- Every report separates kit completion from the eight hardware gates, which
  stay MISSING.

## Operator prerequisites

Supported mixed tablets and iPad(s), camera/tripod with measured rolling
shutter, ruler/vernier, intended AP/host and charging, portable CA/install
access, second LAN vantage, fleet scope, and time for the 100-event optical
run, ten-minute decode run, 20 network trials, two-hour media soak and any
overnight still run. The frozen targets are in
[ACCEPTANCE.md](ACCEPTANCE.md); the runbooks are linked from
[HARDWARE-VALIDATION.md](HARDWARE-VALIDATION.md).
