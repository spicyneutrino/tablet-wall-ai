# Optical cut capture and analysis

Status: the analyzer and its synthetic fixtures are software. They do **not**
close the `optical-cut-timing` hardware gate. Every report built by this kit
keeps `hardware_gate_status = MISSING` and `hardware_claim = false` through
`tools/validation/evidence.py`. Only an operator's recorded physical capture,
reviewed against the frozen acceptance record, can change the gate.

Synthetic fixtures validate the analyzer only. They are not panel, camera,
installation or wall evidence. Do not paste a synthetic result into a hardware
acceptance record.

## 1. What this kit measures

The kit measures **visible onset** in a high-speed capture: the first frame in
which the expected target colour is confirmed across a configured fraction of
sampled points in each panel ROI. It reports, per panel:

- a conservative onset interval from the last baseline frame and the first
  confirmed frame, including exposure and rolling-shutter row offsets;
- a best-estimate onset point inside that interval;
- confidence, target fraction, changed fraction, and the same-panel noise
  floor;
- `observed`, `missing`, `wrong-target`, `partial`, `ambiguous` or
  `unobserved` status.

Per event it reports the wall-wide point skew (maximum minus minimum onset
point) and the conservative bound `max(upper) - min(lower)`. Across events it
reports expected/observed/missing/ambiguous counts, p50/p95/max point skew,
failure rows, and separate full-run and declared steady-state windows. A single
missing, wrong, partial or ambiguous event remains in the output and blocks a
gate-evaluable observation.

The published gate is unchanged: at least 100 complete cuts, wall-wide p95
skew at most 100 ms and max at most 250 ms. This kit never reports a pass. With
fewer than 100 complete events, or with any failure, the observation is
`not-evaluable`. If the conservative uncertainty crosses 100 ms or 250 ms, the
observation is `inconclusive`.

## 2. Equipment

Capture the whole wall in one frame, not one tablet at a time.

- Camera with a genuine high-speed mode at 240 fps or better, manual exposure,
  manual gain, manual white balance and a fixed lens. A phone slow-motion clip
  is not enough unless it records actual per-frame timestamps and exposure.
- Sturdy tripod or rigid mount. Nothing may move between events.
- A visible numbered flash or LED counter board in frame, updated once per
  event. It is the reference marker; do not infer it from the nominal frame
  rate.
- A diffused light source with stable colour temperature and no flicker.
  Disable automatic exposure, automatic white balance, noise reduction and
  frame interpolation.
- Lenses/framing that cover every active panel plus the flash board. Avoid
  extreme perspective; a straight-on or gently elevated view is easier to
  sample.
- Storage sized for the full run. Raw captures stay outside this repository.
- A measurement sheet or field log for event ids, wall time, source frame,
  camera settings, operator, and every deviation.
- Optional: an LED strip or fast photodiode for measuring the camera's
  rolling-shutter readout. A manufacturer specification is a fallback, not a
  measurement; mark `measured: false` when it is not measured.

## 3. Camera and capture setup

Record the camera model, lens, resolution, orientation, exposure, gain, white
balance, and the measured rolling-shutter readout and direction in the capture
manifest. The manifest schema is `tablet-wall-optical-capture/1`.

```json
{
  "schema": "tablet-wall-optical-capture/1",
  "capture_id": "wall-a-2026-11-02-run-01",
  "evidence_kind": "operator-hardware",
  "camera": {
    "model": "camera and lens",
    "exposure_us": 500,
    "gain": "manual, fixed",
    "white_balance": "manual 5600 K",
    "orientation_deg": 0,
    "resolution": {"width": 1920, "height": 1080},
    "rolling_shutter": {
      "readout_us": 8200,
      "direction": "top-to-bottom",
      "measured": true,
      "method": "LED strip sweep at 1 kHz; 12 repeats"
    },
    "nominal_fps": 240
  },
  "timestamp_basis": "exposure_start",
  "clock": {
    "source": "camera monotonic time",
    "mapping": "reference_frame is a manifest frame; wall-clock offset recorded in the field log"
  },
  "frames": [
    {"index": 0, "path": "frames/000000.png", "timestamp_s": 0.0},
    {"index": 1, "path": "frames/000001.png", "timestamp_s": 0.004167}
  ],
  "dropped_frames": [],
  "duplicated_frames": [],
  "panel_scanout": "operator note: left panel top-to-bottom refresh, right panel model B",
  "notes": "raw frames live outside the repository"
}
```

Rules:

- `frames[]` lists **actual** decoded frames with actual timestamps. A nominal
  fps field may be recorded as metadata, but it is never used for timing.
  Never synthesize timestamps from a nominal rate.
- `timestamps` are on one camera clock. `timestamp_basis` says what the stamp
  means: `exposure_start` (default), `exposure_centre` or `exposure_end`.
  Choose one convention and use it for the whole run.
- `orientation_deg`, `gain` and `white_balance` are required. `orientation_deg`
  is the clockwise rotation from sensor to delivered frame. ROIs are normally
  in delivered-frame pixel coordinates; the analyzer maps them back to the
  sensor for readout order. A missing orientation is rejected rather than
  assumed to be landscape.
- `rolling_shutter.readout_us` is the measured full-frame readout duration.
  `direction` is the sensor readout direction, one of `top-to-bottom`,
  `bottom-to-top`, `left-to-right` or `right-to-left`. Mark `measured: false`
  if you used an estimate; the report will list that limitation and the run
  will **not** be gate-evaluable, because row-offset uncertainty cannot support
  the 100/250 ms decision.
- `dropped_frames` and `duplicated_frames` list frame indices known from the
  capture tool. The analyzer also reports timestamp gaps and duplicate
  timestamps as unobserved intervals. Do not hide a drop; keep the frame
  indices so the onset interval widens honestly.
- `panel_scanout` is an optional operator note. It is not a measurement made
  by this tool.
- `clock` documents how the reference frame maps to the wall event log. See
  section 6.

Video input: if the capture is a video, the analyzer decodes every frame with
`ffmpeg` and takes per-frame presentation timestamps from `ffprobe`. It fails
when the extracted frame count and ffprobe timestamp count disagree. A nominal
`avg_frame_rate` is not a timestamp source. Use `--decode-video` to force the
video path even if extracted frames also exist, and `--frames-dir` to choose a
bounded decoded-frame directory. Only files named `NNNNNN.png` (six digits) in
that directory are replaced; unrelated files are left alone. Extraction is
staged, so a failed or mismatched decode leaves the previous frame set in place.
A directory that already holds a partial extraction is safest replaced with a
fresh directory.

## 4. Numbered flash and reference frames

Put a numbered flash or LED counter board in the same frame as the wall and
record its value for every event. Prefer a board whose number is unambiguous at
the capture resolution. The event record names a `reference_frame` (preferred)
or a `reference_time_s`:

```json
{
  "event_id": "cut-0001",
  "reference_frame": 240,
  "search_window": {"before_ms": 50, "after_ms": 400},
  "expected_panels": ["left", "right"],
  "target": {"rgb": [0, 200, 0], "tolerance": 30},
  "min_target_fraction": 0.60,
  "steady_state": true,
  "source_frame": 1234,
  "notes": "wall event log row 1"
}
```

- `reference_frame` is an actual manifest frame index. This avoids mixing
  camera and wall clocks.
- `reference_time_s` is allowed when the event log is already mapped to the
  camera clock. Record the mapping method and uncertainty in the field log.
- `search_window.before_ms` makes early cuts observable. If a panel can switch
  before the reference marker, declare a non-zero before-window. A window that
  starts after the cut cannot recover it.
- `expected_panels` must name at least two distinct panels that should change.
  A single-panel event cannot measure wall-wide skew and is rejected.
- `target` is the expected post-cut colour. `rgb` is the direct form; a
  `patch` path is averaged over the whole patch image. Keep tolerance tight
  enough that a different colour cannot pass, and document any gain/WB shift.
- `steady_state: false` marks startup, recovery or otherwise excluded events.
  They stay in the full-run output and are listed as recovery intervals; they
  are excluded from the steady-state window only. Never delete them.
- `source_frame` is the expected burned-in source frame for video alignment.
  It is checked only when a burned-in ROI is configured **and** OCR is enabled.
  Every event that declares a source frame must have a readable check; declared
  values must be strictly increasing and unique, and so must the observed
  values. Otherwise `source_frame_tracking` is false and video sync is not
  claimed. A cut detector alone is not video synchronization.

Reference frames are not inferred from the number of frames since boot. If a
reference frame is missing from the capture, the event is `unobserved`; the
analyzer does not silently pick a neighbour unless an explicit
`reference_time_s` is supplied.

## 5. ROIs

One ROI file per capture. The schema is `tablet-wall-optical-rois/1`.

```json
{
  "schema": "tablet-wall-optical-rois/1",
  "coordinate_space": "delivered",
  "source_frame_roi": [20, 20, 180, 50],
  "source_frame_digits": 6,
  "panels": [
    {
      "panel_id": "left",
      "polygon": [[120, 180], [520, 180], [520, 700], [120, 700]],
      "sample_rows": [0.2, 0.5, 0.8],
      "sample_columns": [0.15, 0.38, 0.62, 0.85],
      "sample_radius": 2,
      "noise_reference": {
        "polygon": [[140, 660], [220, 660], [220, 700], [140, 700]],
        "sample_rows": [0.3, 0.7],
        "sample_columns": [0.25, 0.75],
        "sample_radius": 1
      }
    }
  ]
}
```

Rules:

- `coordinate_space` is `delivered` (default) for polygons drawn on the decoded
  frame, or `sensor` for polygons in raw sensor pixels. Sensor-space ROIs need
  the manifest camera metadata and are rotated into the delivered frame before
  sampling. Map polygons against a representative full-resolution frame, never
  against a resized preview with different geometry.
- Keep the polygon inside the active panel area. Exclude bezels, borders,
  reflections, status bars, logos and bright room reflections.
- Use several rows and columns. The default grid is five columns by four rows;
  explicit `sample_points` is allowed, but the points must span at least two
  rows and two columns. A 12–20 point grid is a better default than the
  three-point hard minimum. `sample_rows` and `sample_columns` are fractions
  strictly between 0 and 1 of the polygon's bounding box.
- The analyzer confirms an onset only when the configured fraction of probe
  points match the expected target **and** changed from baseline. A small local
  change is not an onset.
- `sample_radius` is the half-size of the square mean patch. A larger patch
  suppresses sensor noise but smears a fine transition; record the choice.
- `noise_reference` is required and must be on the **same panel**, with its
  polygon and probe points inside the panel polygon. It estimates that panel's
  baseline temporal and spatial noise. A global background patch is not a
  substitute. Keep it inside the panel and out of changing content where
  possible.
- Reuse the same ROIs for every event in a run. If the camera moved, the run is
  invalid; recapture rather than redrawing ROIs mid-run.
- `source_frame_roi` is optional. It must contain only the burned-in frame
  number; `source_frame_digits` is the number of digits to read. OCR requires
  `tesseract` and the `--ocr` flag. Without both, the report sets
  `source_frame_tracking = false` and does not claim video sync.

## 6. Clock mapping

The camera clock is the timing source. The wall event log is a separate clock.
Record the mapping explicitly:

- camera model and time source;
- whether timestamps are exposure start, centre or end;
- reference frame index and its camera timestamp;
- wall-clock time of the reference marker and the measured offset between the
  wall event log and the camera clock;
- how the offset was measured (numbered flash, visible event marker, clap,
  hardware trigger) and its uncertainty;
- whether frame timestamps came from the manifest or from `ffprobe`.

Do not convert a wall-clock time to a frame index by multiplying by a nominal
fps. If the event log only has wall time, map it with the recorded offset and
report the mapping uncertainty. The analyzer does not fetch or correct clocks.

For video alignment, the burned-in source frame is the independent reference.
A cut detector alone cannot prove video synchronization: a matching cut in two
streams can still come from different decoded frames. Keep the OCR checks and
the source-frame rows; if they are absent or unreadable, state that video sync
was not evaluated.

## 7. Procedure

1. Freeze the acceptance record and note its path and revision. Do not edit the
   thresholds during the run.
2. Mount the camera rigidly. Frame every active panel and the numbered flash.
3. Set manual exposure, gain, white balance, focus and a fixed frame rate. Turn
   off auto-focus, auto-exposure, auto-white-balance and interpolation.
4. Measure the rolling-shutter readout and direction. Record the method and
   repeats. Mark `measured: false` if it is only a specification.
5. Capture a short pilot with a deliberate all-panel cut. Verify frame paths,
   actual timestamps, ROI coverage, same-panel noise and the flash number
   before committing operator time to the full run.
6. Run at least 100 complete cuts. Keep the original cohort and every failure.
   Do not stop at 100 successful events and drop earlier failures.
7. For each event, record the event id, reference frame/time, expected panels,
   target colour/patch, search window, steady-state flag and source frame.
8. Copy the raw capture to storage outside the repository. Record its location,
   size, hash and access restrictions. Keep only bounded analysis artifacts and
   sanitized summaries in the repository, and only with operator authorization.
9. Run the analyzer. Review the CSV/JSON/Markdown failure rows, unobserved and
   recovery intervals, and the conservative bounds. Do not accept a report that
   hides a failure or claims a pass.
10. Photograph the setup, the flash board, every panel edge/ROI overlay, and the
    final capture screen. Attach the field log and sign-off.

## 8. Running the analyzer

```sh
python -m tools.optical.cli analyze \
  --manifest /path/outside/repo/manifest.json \
  --rois /path/outside/repo/rois.json \
  --events /path/outside/repo/events.json \
  --out /path/outside/repo/analysis \
  --repo-root .
```

Useful options:

- `--decode-video` forces ffmpeg/ffprobe frame extraction and timestamps.
- `--frames-dir DIR` chooses the decoded-frame directory.
- `--ocr` reads a configured burned-in source-frame ROI with tesseract.
- `--baseline-frames`, `--min-baseline-frames`, `--confirm-frames` tune the
  detector. They do not change the published 100/250 ms thresholds.

Outputs in `--out`:

| File | Contents |
| --- | --- |
| `analysis.json` | Full capture, ROI, event, panel, metric, interval and limitation data. |
| `events.csv` | One row per event, including failures and conservative bounds. |
| `panels.csv` | One row per event/panel, including intervals, confidence and reasons. |
| `summary.md` | Human-readable summary with failure, unobserved and recovery rows. |
| `report.json` | The evidence report built with `tools.validation.evidence`. |

`report.json` always has `gate = optical-cut-timing`,
`hardware_gate_status = MISSING`, `hardware_claim = false`, artifact hashes,
failure reasons and limitations. `completion` describes the kit run, not the
hardware gate; a complete synthetic run is still synthetic.

To reproduce the analyzer fixtures:

```sh
python -m tools.optical.cli fixtures --out /tmp/optical-fixtures
python -m tools.optical.cli analyze-suite --suite /tmp/optical-fixtures --out /tmp/optical-fixtures-out --repo-root .
```

The fixture suite covers 240 fps captures, 0/30/80 ms offsets, a sub-frame
phase, a 100 ms boundary, a 300 ms overshoot, rolling-shutter row offsets,
exposure blur, noise, partial transitions, wrong targets, repeated colours
(including a baseline that already matches the target and then drifts inside
tolerance), missing participants, variable timing, dropped/duplicated frames
and a duplicate timestamp, a truncated capture, an early cut before the
reference and a declared startup event. These cases validate the detector and
the reporting logic. They do not validate a panel.

## 9. Failure rows and intervals

Every one of these is retained in the outputs:

- `missing` — no visible change towards the target inside the window;
- `wrong-target` — a visible change, but not the expected colour;
- `partial` — some probe points changed but fewer than the configured fraction;
- `ambiguous` — the target was already present at baseline, the baseline noise
  is too high, or the onset bounds are inconsistent/too wide;
- `unobserved` — a missing reference, insufficient baseline, no search frames,
  or a search window truncated by the end of the capture.

A single failed event blocks a gate-evaluable observation even when 100 other
events are complete. The full-run metrics keep the failure row; the
healthy-subset diagnostic is not substituted for the whole cohort.

Unobserved intervals include missing/dropped frame gaps, duplicate timestamps,
search windows before the first frame or past the last frame, and absent
baseline coverage. Declared non-steady events are listed as recovery/startup
intervals, retained in the full run, and excluded only from the steady-state
window. Never remove most of a run as "recovery" to obtain a better number.

## 10. Uncertainty

The interval accounts for:

- the actual frame interval (not a nominal fps);
- the camera exposure, including a blended exposure at the transition;
- the sample row's position in the rolling-shutter readout;
- the camera orientation mapping;
- the difference between the last baseline frame and the first confirmed frame;
- the sampling fraction, patch mean and same-panel noise floor.

The point estimate is a best estimate inside the interval, not a sub-frame
measurement. The conservative wall bound is `max(upper) - min(lower)`, not a
pairwise average. If the conservative bound crosses 100 ms (p95) or 250 ms
(max), the observation is `inconclusive`, not a pass. If the point estimate
crosses either limit, the observation is `exceeded` and the report fails the
event threshold checks. Neither condition can promote the gate.

## 11. Photos and sign-off

Attach or reference, outside the repository unless authorized:

- wide photo of the whole wall and camera on the tripod;
- close photo of the numbered flash/counter board;
- photo of the camera settings screen (exposure, gain, WB, resolution, fps);
- ROI overlay screenshot for every panel;
- photo of the field log page with event ids and wall times;
- at least one raw frame showing all panels and the reference marker.

Sign-off:

| Field | Value |
| --- | --- |
| Capture id | |
| Operator | |
| Date/time and timezone | |
| Camera, lens, resolution | |
| Exposure / gain / white balance | |
| Measured readout and direction | |
| Orientation | |
| Reference method and clock offset | |
| Event count attempted / complete | |
| Raw storage location and hash | |
| Analyzer SHA and settings | |
| Failures / unobserved / recovery count | |
| Conservative p95 / max | |
| Threshold observation (`within-threshold-observation-only`, `inconclusive`, `exceeded` or `not-evaluable`) | |
| Operator signature | |
| Reviewer signature | |
| Gate status (must remain `MISSING` until separately accepted) | MISSING |

## 12. Limitations

- The analyzer infers visible onset in captured frames. It does not measure
  panel photon emission, capture-to-glass latency, or the tablet's internal
  presentation pipeline.
- Camera-clock mapping, flash timing and rolling-shutter readout are supplied
  metadata. The tool records them; it does not independently verify them.
- A nominal fps is never timing evidence. If actual timestamps are absent, the
  analyzer refuses the capture.
- A cut detector is not video synchronization. Burned-in source-frame tracking
  is optional and is reported as unavailable when absent.
- Synthetic fixtures validate the analyzer only.
- The 100/250 ms gate and the 100-event minimum are not revised here.
- Raw captures are expected outside the repository. Artifact hashes bind the
  bounded analysis inputs and outputs, not every raw frame.
- The report may be `complete` as a kit run while `hardware_gate_status` is
  still `MISSING`; those are different claims.
