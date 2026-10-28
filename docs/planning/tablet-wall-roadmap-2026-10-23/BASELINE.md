# Simulator baseline

Observed on 2026-10-23 at commit `65a4d5081194c457c74a8c6aae629281a30e634b`.
The coordinating agent ran the existing simulator before the roadmap reviews.

```bash
.venv/bin/python simulator/run.py --quiet --report /tmp/tablet-wall-roadmap-20261023-baseline.json
```

The command exited with code 0:

```text
scenarios: 23 passed, 0 failed, 0 errored of 23
checks:    1075 passed, 0 failed of 1075
note:      no browser/canvas execution — see the limitations in the report
```

This run checked protocol behavior and geometry through the in-process harness.
It did not run tablet JavaScript, use real TCP, render browser pixels, decode
video, or measure physical display synchronization. The planners read these
results; they did not rerun the simulator.

The raw JSON report remains a temporary artifact. It is excluded from this
commit following the [simulator's report instructions](../../../simulator/README.md#report).
Use a new output path under `/tmp` to record a fresh run.
