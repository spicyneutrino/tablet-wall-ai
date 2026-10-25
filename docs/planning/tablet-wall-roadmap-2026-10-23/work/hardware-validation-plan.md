# Plan: hardware and deployment validation kit

Status: the eight remaining gates need physical devices, a camera, a real
access point/host, installed tablet trust and operator time. This plan builds
and dry-runs the **tooling and procedures**; it does not close a gate. Every
gate stays MISSING until an operator records the required physical evidence.
No desktop Chromium, WebKit, loopback Caddy, model test or synthetic fixture
may be promoted to a hardware result.

Source: the 2026-10-25 independent review's physical plan
(`/tmp/tablet-wall-codex-work-review-2026-10-25/review.md`, section "Physical
and deployment validation plan"), `ROADMAP.md:500-522`, `deploy/KIOSK.md`,
`deploy/OPERATIONS.md`, `deploy/hotspot.Caddyfile` and `deploy/smoke.sh`.

## Phase 1: build the kit (parallel worktrees)

### A. Optical cut analyzer + capture kit

Files: `tools/optical/` (new), `tests/test_optical.py`, `docs/validation/OPTICAL-CAPTURE.md`.

- Ingest a high-speed capture as numbered frames or a video decoded with
  ffmpeg, an ROI JSON (one polygon/box per panel), an event CSV (event id,
  expected wall time or flash frame, target asset/colour) and camera metadata
  (fps, exposure, rolling-shutter direction).
- Per event and ROI, detect the first transition after the reference, report
  the onset timestamp, wall-wide max-min skew, missing/ambiguous transitions,
  per-event uncertainty and full-run vs steady-state p50/p95/max. Enforce the
  100/250 ms gate only when at least 100 complete events exist.
- Generate synthetic 240 fps captures with known panel offsets (including
  offsets above the gate and one missing transition) and prove the analyzer
  recovers them within one frame. Label synthetic fixtures as such.
- Capture document: camera/tripod/exposure, numbered flash, simultaneous
  panels, ROI rules, raw storage outside the repo, 100-event minimum,
  uncertainty reporting, failure rows and sign-off.

### B. Device decode/suspend probe

Files: `tools/device_probe/` (new), `simulator/browser/decode_probe.py`,
`docs/validation/DEVICE-PROBE.md`.

- A standalone probe page plays a burned-in frame/time MP4 and logs
  `requestVideoFrameCallback`, `currentTime`, `readyState`, dropped-frame
  counts, visibility, wake-lock state, UA and viewport; exports JSON for the
  operator. It covers fresh play, loop, seek, app switch, lock/unlock, low
  memory and reload.
- A Playwright Chromium/WebKit smoke runner loads the probe with a generated
  fixture and saves the log. It proves the probe works on desktop engines
  only; iOS Safari and physical decode remain MISSING.
- Extract the existing host-suspend simulation result into the device
  procedure as a software control, not a physical suspend.

### C. Trust, origin and calibration kit

Files: `deploy/trust_check.py`, `tools/calibration/check_measurements.py`,
`docs/validation/TRUST-AND-ORIGIN.md`, `docs/validation/CALIBRATION-SHEET.md`,
tests.

- `trust_check.py`: inspect a supplied chain/SAN/fingerprint, verify the
  tablet origin with the installed public root (never `-k` as proof), run the
  existing negative route checks against tablet and operator origins, and
  record whether the backend is reachable from the tablet namespace. A real
  tablet visit with no warning remains manual evidence.
- Calibration checker: ingest the worksheet CSV (panel active dimensions,
  bezels, mount angle, measured seam displacement, uncertainty, viewport/
  calibration revisions), validate ranges and compute adjacent-edge seam
  displacement; synthetic asymmetric/rotated cases and one failing row.
- Worksheets capture exact device/OS/browser, UUID/number, calibration
  revision, ruler/camera method and photos at every edge.

### D. Fleet soak, network and kiosk harness

Files: `simulator/browser/fleet_soak.py`, `deploy/network_trials.py`,
`docs/validation/SOAK-AND-NETWORK.md`, `docs/validation/KIOSK-CHECK.md`.

- Fleet soak: N disposable clients on one server, repeated still/video/recovery
  cycles, configurable duration; sample server RSS/CPU, socket/page errors,
  visible-picture completeness, recovery windows, and write a report. A short
  software dry run (for example 5 minutes) validates the harness. The required
  two-hour media and overnight still runs on real tablets remain MISSING.
- Network trials: 20-trial harness against an operator-supplied origin/device
  with timestamps and failure rows; the existing offline `recovery_run.py`
  remains a network-emulation control, not Wi-Fi evidence.
- Kiosk check: browser probe for wake lock, fullscreen, visibility and return;
  `deploy/KIOSK.md` remains the OS/device procedure. Guided Access, Auto-Lock
  and managed kiosk settings are operator steps.

## Evidence rules (advisor amendments)

Every tool writes through `tools/validation/evidence.py` and
`docs/validation/EVIDENCE-SCHEMA.md`. It records evidence kind, application
SHA, tool/settings versions, original cohort, expected scenarios, artifact
hashes, every failure, skipped and unobserved intervals, and completion.
Kit execution success is separate from hardware acceptance; every report keeps
`hardware_gate_status = MISSING`. A single missing transition, wrong target or
failed row blocks that event and is reported. Optical uncertainty that crosses
a threshold is inconclusive. A supplied CA bundle proves verifier trust only
and must name the trust store actually tested. The acceptance record
`docs/planning/tablet-wall-roadmap-2026-10-23/ROADMAP.md` (targets at lines
500-522) is frozen before measurements; this work does not revise it.

## Phase 2: dry runs and evidence discipline

- Run the optical synthetic suite and the analyzer on its fixtures.
- Run the device probe in desktop Chromium and WebKit; record the engine
  versions and explicitly not iOS.
- Run the trust checker against the disposable loopback Caddy setup with a
  generated local CA; record the negative-route matrix. Do not claim tablet
  trust.
- Run the calibration checker on synthetic measurements and one deliberately
  failing row.
- Run a short fleet soak (for example 5 minutes) with simulated clients and
  record memory/CPU/errors. Do not label it a hardware soak.
- Write `docs/validation/HARDWARE-VALIDATION.md` as the single gate matrix with
  status, equipment, procedure, acceptance and evidence path for each of the
  eight MISSING gates. Link it from README and the execution log.
- Record every artifact outside the checkout; keep raw camera/tablet data out
  of the repository unless the operator authorizes a bounded sample.

## Phase 3: operator hardware execution (blocked until equipment)

The operator supplies the mixed tablet pair/fleet, camera, power, AP/host,
portable CA/install access and time. Execute the procedures in order:

1. Trust/origin install and negative probes on one tablet.
2. Calibration and seam measurement on the mixed pair.
3. Still-cut optical capture, at least 100 events.
4. Video decode/suspend/loop/recovery procedure, including app switch,
   lock/unlock and low-memory reload.
5. Wi-Fi/AP loss and restore trials, 20 trials.
6. Kiosk/OS setup and return checks.
7. Two-hour media soak and, if unattended overnight use is required, the
   overnight still soak.

Only the operator's recorded evidence can change a gate from MISSING.

## Kit acceptance rehearsal

The kit is accepted only when a disposable end-to-end rehearsal runs all four
tools, reproduces known failures, distinguishes aborted/unsupported runs,
verifies cleanup and leaves all eight gates MISSING. It must show the failed
row and the skipped/unobserved intervals, not only green paths. The operator
still supplies supported mixed tablets, camera/tripod, measuring tools, AP and
host, charging, trust/settings access, fleet scope and execution time.

## Boundaries

- No synthetic capture, desktop browser, loopback Caddy, WebKit or model
  result closes a hardware gate.
- No evidence is summed across overlapping suites.
- The 100/250 ms optical gate, 2 mm seam gate, 10 s connectivity target and
  soak durations are not revised by this work.
- The 31-second recovery window and the accepted session-only exclusion /
  one-attempt reconnect behavior are unchanged.
