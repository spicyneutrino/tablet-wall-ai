# Hardware and deployment validation

Status: **all eight gates are MISSING.** This page is the gate matrix and
operator runbook. The repository contains a validation kit that can be run on
a workstation; a kit pass proves the tool, not the hardware. A gate changes
from MISSING only when the operator records the required physical evidence and
signs the row.

The acceptance numbers are frozen in [ACCEPTANCE.md](ACCEPTANCE.md), copied
from the published targets in
`../planning/tablet-wall-roadmap-2026-10-23/ROADMAP.md:500-522`. This page does
not revise them. The approved recovery window remains the ordinary ~31 s
preparation deadline; no run may trim it out of a full-run result.

## Evidence contract

Every kit report uses `tools/validation/evidence.py` and the schema in
[EVIDENCE-SCHEMA.md](EVIDENCE-SCHEMA.md). It records:

- evidence kind, application SHA, tool/settings versions and original cohort;
- expected scenario ids, every check and scenario, failure reasons, skipped
  and unobserved intervals;
- artifact paths, sizes and SHA-256, plus an explicit completion state.

The report always carries `hardware_gate_status = MISSING` and
`hardware_claim = false`. Kit success and hardware acceptance are separate
columns. Synthetic, desktop Chromium, WebKit, loopback Caddy and simulated
fleet runs cannot close a gate.

## Gate matrix

| Gate | Published acceptance | Kit | Hardware evidence | Status |
| --- | --- | --- | --- | --- |
| Optical still cuts | At least 100 events; wall-wide visible onset p95 ≤ 100 ms, max ≤ 250 ms; missing transitions fail their events; report uncertainty and all intervals | `tools/optical/` analyzer + synthetic fixtures | High-speed camera/tripod, simultaneous panels, numbered flash, raw capture, ROI/event files | **MISSING** |
| Physical video decode, suspend and recovery | 10-minute clean run with no unplanned stalls; optical p95 ≤ 100 ms and max ≤ 250 ms outside declared startup/recovery windows; recovery convergence within 5 s; zero stale paints | `tools/device_probe/` + `simulator/browser/decode_probe.py` | Real mixed tablets, production H.264, independent recording, power/temperature records | **MISSING** |
| iOS Safari | Page/register/socket/media, muted inline play or an actionable activation request, geometry, pause/resume, recovery and background/return on supported iPads; same optical/connectivity targets | Device probe page; desktop WebKit smoke only | Physical iPad models, intended iPadOS/Safari, trusted origin, tab and Home Screen | **MISSING** |
| Mixed-model calibration | Adjacent-edge seam displacement ≤ 2 mm beyond intended hidden gaps; uncertainty and photos at every edge; no DPR-derived physical claim | `tools/calibration/check_measurements.py` + worksheet | Ruler/vernier, camera, measured lit panels/bezels, asymmetric and rotated units | **MISSING** |
| Installed CA trust and origin migration | Each real browser opens the intended origin with no warning and works with WAN absent; backend unreachable from the LAN; operator auth and tablet allowlist hold; rebind preserves slot/number | `deploy/trust_check.py` + disposable Caddy negative matrix | Disposable first deployment, Caddy public root, real tablet trust settings, second LAN client, backup/restore | **MISSING** |
| Real Wi-Fi and OS behavior | Content correct within 10 s of connectivity restoration over at least 20 trials; all trials and failures retained; intended fleet capacity remains a trial target | `deploy/network_trials.py` + offline/online control | Actual AP/hotspot, intended tablets/radios, power/sleep settings, network logs | **MISSING** |
| Kiosk operation | Devices stay on or return to the intended page; measured viewport/calibration remains valid; operator can enter and exit safely; recovery meets the same connectivity targets | `docs/validation/KIOSK-CHECK.md` checklist + `deploy/KIOSK.md` | Real devices, OS management/pinning, charging, Auto-Lock/Guided Access settings, operator exit procedure | **MISSING** |
| Sustained soak | At least 2-hour media soak; overnight still soak if unattended; no unplanned stalls, lost members, stale paints or unexplained restarts; resource/temperature envelope agreed before the run | `simulator/browser/fleet_soak.py` (harness only) | Intended physical fleet, trusted ingress, charging, temperature/resource monitoring, continuous or sampled recording | **MISSING** |

The executed kit rehearsal and its counts are in [REHEARSAL.md](REHEARSAL.md).

## Kit dry-run status

This table proves the tools run; it is not hardware acceptance.

| Workstream | Latest dry run | Gate |
| --- | --- | --- |
| Device probe | 40/40 checks; desktop Chromium and WebKit passed; iOS scenario unsupported as intended | physical decode/suspend and iOS Safari remain **MISSING** |
| Trust and origin | 72/72 checks, 8/8 scenarios against disposable Caddy with a fresh local CA; supplied-bundle verifier trust only | installed CA trust remains **MISSING** |
| Calibration | synthetic worksheet pass/fail/inconclusive cases; 1/1 dry scenario | mixed-model calibration remains **MISSING** |
| Fleet soak harness | 4 clients, 60 s; 22/22 checks, 6/6 scenarios; shared-host limitations recorded | the two-hour media and overnight still runs remain **MISSING** |
| Network trial harness | dry loopback 20 trials; 7/7 checks, 20/20 scenarios; not Wi-Fi | real Wi-Fi/OS remains **MISSING** |
| Kiosk | browser/OS checklist; no physical device | kiosk remains **MISSING** |
| Optical analyzer | 40 analyzer tests; 19 synthetic cases, 0 errors, including threshold, rolling-shutter, noise, partial/wrong/missing, dropped/duplicated and truncated captures. Reports stay incomplete until 100 real events; synthetic only. | optical cut timing remains **MISSING** |

## Operator prerequisites

Supply and record:

- exact tablet models, OS/browser versions, display numbers and UUID mapping;
- viewport/display mode, calibration and profile revisions;
- application SHA, playlist and media SHA-256, ingress configuration;
- camera model, lens, frame rate, exposure, resolution, rolling-shutter
  readout/direction and clock mapping;
- AP/host configuration, WAN state, power/charging and temperature logging;
- raw captures and logs outside the repository; bounded samples may be
  committed only with operator authorization;
- a signed result row for every gate, including failures, uncertainty and
  missing/unobserved intervals.

## What can run without the hardware

- Optical analyzer on synthetic 240 fps fixtures, including known offsets,
  threshold boundaries, rolling shutter, noise, partial/wrong/missing
  transitions and truncated captures. This validates the analyzer only.
- Device probe in desktop Chromium and WebKit (if installed). This validates
  the probe and desktop media plumbing, not a tablet or iOS.
- Trust checker against a disposable loopback Caddy with a generated local CA;
  route/TLS/certificate checks only. Installed tablet trust is manual.
- Calibration checker on synthetic measurement rows. Real ruler/photos are
  manual.
- Short simulated fleet soak. It validates the harness/resource sampling, not
  the required two-hour media or overnight still run.
- Network-trial harness against a loopback origin with network emulation. It
  does not prove Wi-Fi, radio or OS behavior.

## Per-gate runbooks

- [Optical capture](OPTICAL-CAPTURE.md)
- [Device probe](DEVICE-PROBE.md)
- [Trust and origin](TRUST-AND-ORIGIN.md)
- [Calibration sheet](CALIBRATION-SHEET.md)
- [Soak and network](SOAK-AND-NETWORK.md)
- [Kiosk check](KIOSK-CHECK.md)
- [Kiosk platform notes](../deploy/KIOSK.md)
- [Hotspot/TLS operations](../deploy/OPERATIONS.md)

## Sign-off

A gate row may be updated only with: gate, date/time, application SHA,
equipment inventory, scenario ids, full-run and steady-state results,
failures and unobserved intervals, artifact hashes, operator name and an
explicit signed verdict. Until then the row remains **MISSING**.
