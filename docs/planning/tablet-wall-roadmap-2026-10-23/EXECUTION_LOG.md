# Execution log: Stages 0-3

Scope: P0, R1, R2 and R3 of [ROADMAP.md](ROADMAP.md). Hardware-only claims
(physical iPad/Android, optical synchronization, real suspend, iOS Safari
decode) stay explicit gaps; the roadmap permits implementing a ticket without
claiming those results.

## Current state

- Stage 0: planning.
- Stage 1: T2 (ownership and bounded registration) implemented and verified,
  uncommitted at the start of this run.
- Stage 2: not started.
- Stage 3: not started.

## Stage 0 plan (P0)

Goal: close P0 with a reproducible software baseline plus explicit passed or
missing hardware rows.

1. Rerun the existing checks in isolation: `pytest`, the node client suite,
   `make sim`, and the disposable browser runner. Record exact counts.
2. Rectangle evidence. For every independent client, measure canvas bounding
   rectangle, backing store, viewport, DPR and render mode in tab mode; enter
   fullscreen through the existing `#fs-toggle`, measure again, then exit.
   Record standalone as MISSING with the reason (desktop Chromium has no
   installed web-app display mode).
3. Sleep clock. A real tablet suspend cannot be produced here. Record MISSING
   with the exact required hardware. Do not substitute a frozen-page timer
   experiment for sleep evidence.
4. MP4 probe. Generate a short H.264 baseline MP4 with the installed ffmpeg,
   load it in the installed desktop Chromium, and measure metadata,
   `readyState`, muted play, seek, CSS clip, quarter-turn transform and loop
   restart gap. Label it decode evidence for this engine only; it is not iOS
   Safari and does not prove HTTP range or network preload.
5. Add a `p0` report section with one row per experiment: `PASS`, `FAIL`, or
   `MISSING` with a reason. Update `simulator/README.md` with the same matrix.
6. Run every check again and commit the unit.

Acceptance: all automated checks green; every P0 row is either PASS with
recorded evidence or MISSING with a named prerequisite; the browser run leaves
no temporary data or child process.

Risks: fullscreen may be refused by headless Chromium (record the exact
refusal as MISSING, not a fake pass); a data-URL MP4 does not exercise HTTP
preload or ranges; new browser checks must not make the existing runner flaky.

## Stage 0 advisor review

Pending.

## Decisions

- 2026-10-23: keep the roadmap's hardware gaps explicit instead of emulating
  physical evidence. A software analogue is recorded under its own label.
