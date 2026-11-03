# Validation evidence schema

Every hardware-validation tool writes one report through
`tools/validation/evidence.py`. The schema is `tablet-wall-validation-evidence/1`.
The report proves what the **kit** did. It never changes a hardware gate:
`hardware_gate_status` is always `MISSING` and `hardware_claim` is always
`false` unless an operator records separate physical evidence.

The aggregate TWR-17 image-wall operator trial uses a separate
[trial record contract](../tablet-wall-readiness/HARDWARE-ACCEPTANCE.md#trial-record-contract)
and [JSON template](../tablet-wall-readiness/TWR-17-TRIAL-RECORD.template.json).
It records signed observations and reasoned not-run rows across several gates.
This kit schema continues to describe individual tool executions; its `completion`
field is not the aggregate trial's verdict. Do not add an invented kit gate or
silently map an operator's not-run result to a passed scenario.

## Required fields

| Field | Meaning |
| --- | --- |
| `schema` | Contract identifier. |
| `tool`, `tool_version` | Kit executable and its own version. |
| `gate` | One of `optical-cut-timing`, `physical-decode-suspend`, `ios-safari`, `mixed-model-calibration`, `installed-ca-trust`, `real-wifi-os`, `kiosk`, `soak`. |
| `evidence_kind` | `synthetic`, `desktop-browser`, `software-simulation`, `disposable-ingress` or `operator-hardware`. |
| `repository` | Head, branch and dirty state of the checkout that produced the tool run. |
| `started_at`, `finished_at` | UTC timestamps. |
| `cohort` | Original participants expected for the run, by stable id. |
| `expected_scenarios` | Every planned scenario id; absent rows become `incomplete`, never silently dropped. |
| `scenarios` | `passed`, `failed`, `skipped`, `incomplete` or `unsupported`, with optional detail. |
| `checks` | Named pass/fail checks with bounded detail. |
| `checks_passed`, `checks_total`, `scenarios_passed`, `scenarios_total` | Counts. Never sum overlapping suites. |
| `failure_reasons` | Every failed check and failed scenario. A single failure blocks completion. |
| `skipped`, `unobserved` | Named skipped work and intervals with no observation. |
| `tools` | Relevant versions/settings (browser, ffmpeg, camera, OpenSSL, OS). |
| `artifacts` | Path, existence, bytes and SHA-256 for every bounded artifact. |
| `limitations` | What the run cannot prove. |
| `completion` | `complete` only when no failure, skip, unsupported scenario or error remains. |
| `error` | Type/message/traceback when the run aborted. |

## Rules

- A missing transition or wrong target fails its event. Do not compute a gate
  from only the complete events while hiding failures.
- A supplied CA bundle proves verifier trust only. Identify whose trust store
  was exercised; installed browser/tablet trust remains an operator step.
- Optical uncertainty that crosses a published threshold yields
  `inconclusive`, not a pass. Preserve full-run, declared steady-state,
  recovery and unobserved intervals separately.
- Synthetic fixtures validate the analyzer, not a panel. Desktop Chromium or
  WebKit validates the probe, not iOS Safari or physical decode.
- A loopback Caddy run validates ingress rules, not installed tablet trust.
- A short simulated fleet soak validates the harness, not the two-hour
  physical media soak or the overnight still soak.
- Raw camera, tablet and network captures stay outside the repository unless
  the operator authorizes a bounded sample.
