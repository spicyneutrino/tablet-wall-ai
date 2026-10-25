# Validation tools

These tools build and dry-run hardware/deployment evidence. They do not close
a gate. Every report uses `tools/validation/evidence.py`
(`docs/validation/EVIDENCE-SCHEMA.md`) and keeps `hardware_gate_status` at
`MISSING`.

| Tool | Gate | Runbook |
| --- | --- | --- |
| `tools/optical/` | optical cut timing | `docs/validation/OPTICAL-CAPTURE.md` |
| `tools/device_probe/` and `simulator/browser/decode_probe.py` | physical decode/suspend, iOS Safari | `docs/validation/DEVICE-PROBE.md` |
| `deploy/trust_check.py` | installed CA trust and origin | `docs/validation/TRUST-AND-ORIGIN.md` |
| `tools/calibration/` | mixed-model calibration | `docs/validation/CALIBRATION-SHEET.md` |
| `simulator/browser/fleet_soak.py` | soak harness, not the physical soak | `docs/validation/SOAK-AND-NETWORK.md` |
| `deploy/network_trials.py` | real Wi-Fi/OS harness | `docs/validation/SOAK-AND-NETWORK.md` |
| `deploy/kiosk_check.py` or the kiosk checklist | kiosk API probe, OS settings manual | `docs/validation/KIOSK-CHECK.md` |

The shared contract test is `tests/test_validation_evidence.py`. The kit
rehearsal and the gate matrix are in
`docs/validation/HARDWARE-VALIDATION.md`; targets are frozen in
`docs/validation/ACCEPTANCE.md`.

Rules:

- A synthetic fixture validates the analyzer, not a panel.
- Desktop Chromium/WebKit validates the probe, not iOS Safari.
- A supplied CA bundle proves verifier trust only; it is not tablet trust.
- A short simulated fleet soak validates the harness, not the two-hour media
  or overnight still run.
- Keep raw captures and logs outside the repository unless the operator
  authorizes a bounded sample.
