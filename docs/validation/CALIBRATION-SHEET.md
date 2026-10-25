# Calibration and seam measurement sheet

Gate: **mixed-model-calibration** — status **MISSING**. The checker validates
what the operator measured; it does not install tablets, place a ruler or see
the wall. A green report is a green *worksheet*, not a green hardware gate.

The frozen acceptance record is [ACCEPTANCE.md](ACCEPTANCE.md): adjacent-edge
seam displacement at most **2 mm** beyond the intended hidden gap, with
uncertainty and a photo at every adjacent edge, from independently measured
active dimensions. The 1 mm value is a stretch goal, not the gate. Neither
number is revised here.

## What "seam displacement" means in this sheet

Each row describes one adjacent edge between two panels. The two panels lie
side by side (`axis=horizontal`, the default) or one above the other
(`axis=vertical`). `left_panel_id` is the left/top panel; `right_panel_id` is
the right/bottom panel.

- `intended_gap_mm` is the gap between the two **bodies**, set by the mount,
  spacer or jig. It is not read off the lit seam and it is not the gap you
  wish you had.
- The expected **visible gap** is computed from the operator's independent
  measurements:

  ```text
  expected_visible_gap = primary seam-facing bezel
                       + intended_gap
                       + secondary seam-facing bezel
  ```

  "Seam-facing" means the right bezel of the left panel and the left bezel of
  the right panel for a horizontal edge; the bottom bezel of the top panel and
  the top bezel of the bottom panel for a vertical edge. Rotation is applied
  first (see below).
- `measured_seam_displacement_mm` is the signed difference between the
  measured active-edge separation and that expected visible gap:

  ```text
  displacement = measured_active_edge_separation - expected_visible_gap
  ```

  Positive means the seam is wider than intended; negative means tighter or
  overlapping. It is a physical reading (ruler/vernier/caliper/feeler/tape),
  not a browser measurement. The optional `measured_visible_gap_mm` column
  lets the checker cross-check the arithmetic; when both are present they
  must agree within the stated uncertainty (or 0.5 mm, whichever is larger).

Do not use device pixel ratio, a CSS viewport, a screenshot or a model to
derive a panel size. The active area and bezels are physical; DPR is not a
length standard. A row whose `method` names DPR, a viewport, a screenshot or a
derived calculation is rejected as insufficient even if its numbers pass.

## Equipment

- Steel rule with 0.5 mm graduations, or a vernier caliper (0.02–0.05 mm), for
  active dimensions, bezels and seam spacing.
- Feeler gauges or a taper gauge for the intended body gap where a spacer is
  inaccessible.
- A straight-edge long enough to span two panels, for checking that the
  measurement line is parallel to the seam and the panel edges.
- A camera on a tripod, perpendicular to the seam, with the ruler in the same
  frame and at the same distance as the seam. A hand-held oblique photo is not
  a measurement.
- Diffuse light and a plain background. Screen content used as a boundary must
  be a full-screen white or flat field with the active area clearly lit.
- A mount jig or reference stops if the intended gap is set mechanically.

Record the instrument identifier, resolution and calibration date. A borrowed
ruler with unknown graduations is not traceable evidence.

## Procedure

1. **Freeze the revisions first.** Read `/api/v3/config` and record the app
   SHA, each panel's active `profile_revision` and `calibration_revision`, the
   view/render revision, viewport, DPR, mode and quarter turn. Freeze changes
   for the duration of the measurement. Any later change invalidates the row
   until it is rechecked.
2. **Measure the active area, not the glass or the frame.** Display a flat
   lit field. Measure the active width at the top, middle and bottom of the
   panel and the active height at the left, middle and right; record the
   median for each. If the active boundary is rounded or obscured, record the
   usable measurement line and the uncertainty it adds.
3. **Measure all four bezels per panel.** From the active edge to the body or
   frame edge on that side: `left`, `top`, `right`, `bottom`. Do not assume
   symmetry; a chin, a camera bump or a rotated mount is normal.
4. **Measure the intended body gap independently.** Use the spacer, jig,
   reference stops or feeler gauge. If the mount cannot be measured directly,
   stop and record the limitation; do not infer it from the observed seam.
5. **Measure the active-edge separation at the seam** with the rule or
   vernier, three times, at positions that avoid local frame curvature. Take
   the median. Compute the signed displacement with the formula above, or
   enter the measured gap in `measured_visible_gap_mm` for the cross-check and
   the displacement you computed. Record the uncertainty.
6. **Take a photo at every adjacent edge.** Perpendicular, ruler visible,
   both active edges and the seam in frame, frame filling most of the image,
   no zoom or digital crop that removes the scale. Name the file after the
   edge id. Raw photos stay outside the repository.
7. **Enter the row.** All revisions are exact strings, not "latest". The
   photo path is relative to the sheet (or to `--photo-root`).
8. **Run the checker.** A failed or inconclusive row is re-measured, not
   edited to fit. Record the re-measurement as a new row/revision; keep the
   old failure. Do not average an edge out of the sheet.
9. **Recheck after any change** to active profile, calibration, view/render
   revision, viewport, orientation, display mode, zoom, mount or origin/rebind
   path. A new view revision means new rows or an explicit "not rechecked"
   gap.

### Uncertainty budget

State one `uncertainty_mm` per row; it is the operator's honest bound, not a
default. Build it from:

- instrument resolution and reading error;
- parallax/eye alignment and ruler contact;
- active-edge blur, frame shadow or rounded corners;
- repeatability across the three readings (max deviation is a useful floor);
- camera perspective if the photo is the primary record (prefer the direct
  instrument reading).

Combine by root-sum-square or take the conservative maximum and say which.
Do not report a smaller number because the row would then pass. The checker
adds and subtracts the stated value; it does not second-guess it.

### Rotation and orientation

Panels are measured in their native orientation (`active_width_mm`,
`active_height_mm`, and the four native bezels). A mount rotated clockwise
relative to native swaps and remaps the wall-facing values:

| `rotation_deg` | Wall active size | Wall left bezel | Wall top bezel | Wall right bezel | Wall bottom bezel |
| --- | --- | --- | --- | --- | --- |
| 0 | native W × H | native left | native top | native right | native bottom |
| 90 | native H × W | native bottom | native left | native top | native right |
| 180 | native W × H | native right | native bottom | native left | native top |
| 270 | native H × W | native top | native right | native bottom | native left |

Only multiples of 90° are accepted. A rotation that is not a quarter turn is a
mount defect to record in the notes, not a number to round. The checker flags
`rotated-mount` and uses the remapped seam bezel; a checker that reads native
left/right blindly would be wrong for a rotated panel.

## CSV columns

Header names are exact. Extra columns are ignored; missing required columns
abort the run with exit 2.

| Column | Unit | Required | Meaning |
| --- | --- | --- | --- |
| `edge_id` | id | yes | Stable id for one adjacent edge, unique in the sheet |
| `left_panel_id` | id | yes | Left (horizontal) or top (vertical) panel |
| `right_panel_id` | id | yes | Right (horizontal) or bottom (vertical) panel |
| `left_active_width_mm` | mm | yes | Native active width, median of three |
| `left_active_height_mm` | mm | yes | Native active height, median of three |
| `left_bezel_left_mm` | mm | yes | Native left bezel |
| `left_bezel_top_mm` | mm | yes | Native top bezel |
| `left_bezel_right_mm` | mm | yes | Native right bezel |
| `left_bezel_bottom_mm` | mm | yes | Native bottom bezel |
| `right_active_width_mm` | mm | yes | Native active width, median of three |
| `right_active_height_mm` | mm | yes | Native active height, median of three |
| `right_bezel_left_mm` | mm | yes | Native left bezel |
| `right_bezel_top_mm` | mm | yes | Native top bezel |
| `right_bezel_right_mm` | mm | yes | Native right bezel |
| `right_bezel_bottom_mm` | mm | yes | Native bottom bezel |
| `intended_gap_mm` | mm | yes | Intended body gap from the mount/jig |
| `measured_seam_displacement_mm` | mm | yes | Signed active-separation minus expected gap |
| `uncertainty_mm` | mm | yes | Stated bound for this row |
| `left_profile_revision` | text | yes | Exact active profile revision |
| `left_calibration_revision` | text | yes | Exact calibration revision |
| `right_profile_revision` | text | yes | Exact active profile revision |
| `right_calibration_revision` | text | yes | Exact calibration revision |
| `view_revision` | text | yes | Exact view/render revision used for the check |
| `photo_path` | path | yes | Photo at this edge; relative to sheet or `--photo-root` |
| `method` | text | yes | Must name a physical instrument (see policy) |
| `axis` | text | no | `horizontal` (default) or `vertical` |
| `left_rotation_deg` | deg | no | Clockwise quarter turns, default 0 |
| `right_rotation_deg` | deg | no | Clockwise quarter turns, default 0 |
| `measured_visible_gap_mm` | mm | no | Independent active-edge separation for the cross-check |

Ranges enforced by the checker: active 20–1500 mm, bezel 0–250 mm, intended
gap 0–100 mm, uncertainty 0–20 mm, displacement −200–200 mm. A value outside a
range is a failed row, not a warning.

### Method policy

The `method` must contain at least one of: `ruler`, `vernier`, `caliper`,
`micrometer`, `feeler`, `tape`, `straightedge`, `straight-edge`, `steel-rule`,
`steel rule`. It must not contain: `dpr`, `device-pixel`, `devicepixel`,
`pixel-ratio`, `viewport`, `screenshot`, `screen-shot`, `derived`, `computed`,
`calculated`, `estimated`, `estimate`, `css-pixel`, `browser`.

Examples that pass: `steel ruler, tripod photo`, `vernier caliper, three
readings`, `feeler gauge for intended gap; ruler for active edge`.
Examples that fail: `DPR-derived`, `viewport math`, `screenshot estimate`,
`looks straight`.

## Running the checker

```bash
python tools/calibration/check_measurements.py \
  --csv /secure/tablet-wall/calibration/mixed-pair.csv \
  --json-out /secure/tablet-wall/evidence/calibration-$(date -u +%Y%m%dT%H%M%SZ).json \
  --markdown-out /secure/tablet-wall/evidence/calibration-summary.md \
  --evidence-kind operator-hardware \
  --expect-profile-revision 3 \
  --expect-calibration-revision 7 \
  --expect-view-revision view-12 \
  --expect-edges e1,e2,e3,e4
```

- `--expect-edges` makes a missing row explicit; without it the checker can
  only judge the rows present and records that the grid's completeness was not
  checked.
- `--expect-*revision` makes stale rows fail. Without them, the checker still
  rejects inconsistent revisions for the same panel across edges and mixed
  view revisions across the sheet, but it cannot know the intended revision.
- `--evidence-kind synthetic` is for fixture tests; `operator-hardware` is for
  a real sheet. The tool cannot verify the label, so an operator must not
  mislabel a fixture.
- `--photo-root` is needed when relative photo paths are not relative to the
  CSV's directory.

Exit status is 0 only when every row passed and every expected edge is
present; 1 for any failed/inconclusive row or worksheet defect; 2 for a
missing file or header.

The JSON report records every row, the expected gap computed from the panel
measurements, the signed displacement, the uncertainty bounds, the method and
photo presence, exact revisions, artifact hashes and the explicit gate status
`MISSING`. The Markdown summary is written beside the JSON by default.

### Verdict rule

| Worst-case bound | Verdict |
| --- | --- |
| `abs(displacement) + uncertainty <= 2 mm` | `passed` |
| `abs(displacement) - uncertainty > 2 mm` | `failed` |
| otherwise | `inconclusive` (reported as a failed scenario, never a pass) |

Uncertainty that crosses the threshold is a re-measure, not a rounded pass. A
row with a missing photo, a derived method, a stale revision or a
missing/duplicate edge fails regardless of its displacement.

An **inconclusive** row appears in the report with `outcome: inconclusive` and
`completion: incomplete`. Do not sum the passing rows into a physical pass and
do not drop the failed edge when computing an average. Each adjacent edge is
reported; the gate applies to every one.

## Synthetic worksheet example

This row is a **fixture**, not a measurement. It exists so the schema can be
seen without implying a panel was touched.

```csv
edge_id,left_panel_id,right_panel_id,left_active_width_mm,left_active_height_mm,left_bezel_left_mm,left_bezel_top_mm,left_bezel_right_mm,left_bezel_bottom_mm,right_active_width_mm,right_active_height_mm,right_bezel_left_mm,right_bezel_top_mm,right_bezel_right_mm,right_bezel_bottom_mm,intended_gap_mm,measured_seam_displacement_mm,uncertainty_mm,left_profile_revision,left_calibration_revision,right_profile_revision,right_calibration_revision,view_revision,photo_path,method,axis
e1,ipad-a,ipad-b,196.0,261.0,6,6,6,6,196.0,261.0,6,6,6,6,3,0.8,0.3,3,7,3,7,view-12,photos/e1.jpg,steel ruler with tripod photo,horizontal
```

Expected visible gap for this row: `6 + 3 + 6 = 15 mm`. Worst case:
`0.8 + 0.3 = 1.1 mm`, so a synthetic run reports `passed`. That says the
checker works; it says nothing about a wall.

## Photos and raw data

- One photo per edge, taken perpendicular to the seam with the scale visible.
- File name: `<edge_id>-<device-a>-<device-b>-<UTC timestamp>.jpg`.
- Include the sheet revision in the photo or the filename; a photo whose
  revision cannot be matched to a row is not evidence for that row.
- Record camera model, lens, distance, exposure and whether the image is
  cropped. A perspective photo needs a scale in the same plane as the seam.
- Hashes of referenced photos go in the report. The images themselves stay
  outside the checkout unless the operator authorizes a bounded sample; do
  not commit a full measurement set to the repository.

## Sign-off

Fill one row per edge and one summary row per device pair.

| Field | Value |
| --- | --- |
| Gate | mixed-model-calibration |
| Date/time (UTC) | |
| App SHA | |
| Exact tablet models / OS / browser | |
| Panel UUIDs and display numbers | |
| Active profile revisions | |
| Calibration revisions | |
| View/render revision | |
| Intended gap and mount method | |
| Instrument, resolution, calibration date | |
| Every edge id, displacement and uncertainty | |
| Photos and hashes | |
| Checker report path/hash | |
| Failures and inconclusive rows | |
| Rechecked edges after any change | |
| Operator | |
| Verdict | PASS / FAIL / MISSING |

The gate remains **MISSING** until that row is signed. A checker run with
`completion: complete` does not change it.

## Rechecks after rebind or an origin change

An origin change or cleared storage gives the tablet a new device UUID. The
rebind copies the saved profile/calibration revisions, but the client's
viewport, DPR, mode, orientation and zoom can still differ. Recheck:

- the exact profile/calibration/view revisions in `/api/v3/config`;
- the active dimensions and bezels in the new browser profile;
- the seam row(s) for that panel, with a fresh photo;
- saved layouts recalled and saved under the new id.

A panel that is physically untouched still needs a new row if its measured
active area, bezel interpretation, viewport mapping or view revision changed.
"Do not infer physical sizes from DPR" applies after rebind too.

## Limits

- The checker validates a worksheet, not the wall. Installation, ruler
  placement, lighting, camera framing and the visual seam remain manual.
- Photo existence is checked; the image content is not machine-inspected.
- Camera perspective and lens distortion are not modelled; direct instrument
  readings are preferred, and a photo-only measurement must state the
  perspective uncertainty.
- The uncertainty is the operator's value, not an independent statistical
  estimate.
- Mixed panel sizes are legitimate; a cross-axis size difference is flagged
  for review, not failed by itself.
- The 2 mm gate and 1 mm stretch goal are frozen by
  [ACCEPTANCE.md](ACCEPTANCE.md) and are not revised by a passing run.
