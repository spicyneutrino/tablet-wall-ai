# Calibrate a mixed-tablet wall

Use the wall workspace at `/controller/` to give images the same
physical scale on different tablets. Logical wall units and equal-sized crops
cannot establish millimetres on the screens. Physical mode fits one master image
to the wall, then renders each tablet's measured part. Existing still-image
playlists use this same mapping; pre-splitting each slide is unnecessary.

## Identify and measure each tablet

Open the tablet's existing browser identity at
`http://10.42.0.1:8080/client/?calibrate=1` when using the hotspot launcher.
The ruler page shows its server-assigned `#N` and short ID. Select that same
tablet in **Tablets**, then select **Review measurements**. Opening another
browser or private tab can create another identity.

Record the lit panel width and height, excluding bezels, and all four bezel
widths. Enter a display profile and save it. Profile dimensions describe the
panel's reference orientation; quarter turn maps the browser viewport into that
panel, and the slot's rotation places the tablet on the wall.

## Reuse a measured tablet model

In **Tablets**, select the tablet, then **Review measurements**.
Choose its actual hardware under **Tablet model**. The built-in iPad
Air 2 and Google Pixel C models use the measured portrait dimensions and ruler
scales supplied for this wall, with a provisional 3 mm uncertainty. A unique
screen size, DPR and platform match assigns a model automatically for a new
tablet. This signature is a hint, not proof of the exact hardware. Unknown or
ambiguous signatures remain unknown. Choose a model explicitly to override
detection, or choose manual measurements to stop automatic adaptation.

A model creates a profile and baseline calibration without another ruler
measurement, including for an offline tablet. Fullscreen assumes zero browser
inset. In a tab or standalone mode, the inferred inset is approximate because
browsers do not report toolbar position. Check the result against the real wall.
Turning a tablet updates its browser-to-panel mapping; set the slot rotation
separately to match its physical mounting. Pinch zoom still blocks physical
rendering. Saving a manual profile or calibration switches that tablet to manual.
An existing layout retains the model snapshot associated with its saved
calibration revision. Changing the current model choice does not change that
layout until you apply a draft with the new measurement revisions.

In **Arrange**, choose **Measured** and a grid preset. Open **Tablets and
mounting** to select the tablets, review their measurement pins, and choose
the mounted top edges. Select **Preview arrangement**, review the result,
then select **Apply arrangement**. The current wall stays active during preview.
A change between relative and measured sizing creates a named return point.
Find that record in **Saved** under **Arrangements**.

## Measure the browser scale

1. Put the tablet in its intended orientation and display mode. Use 100% zoom.
   If installing an iPad Home Screen web app, calibrate that identity and mode.
2. Open its ruler page. In **Tablets**, select the matching number, then
   select **Review measurements**.
   **Use tablet viewport** captures that tablet's CSS width, height, DPR,
   orientation and mode. Offline tablets do not supply defaults.
3. Measure between the centres of the endpoint marks on both ruler targets.
   Each is normally 200 CSS pixels; a small viewport may show a shorter labelled
   span. Enter the two measured lengths in millimetres and the labelled spans.
4. Select **Check ruler measurements**. For example, 40 mm measured across
   200 CSS pixels gives `0.2 mm/CSS px`. The horizontal and vertical scales
   describe the browser axes **before** quarter turn. Do not swap them for a
   rotated panel or multiply them by DPR.
5. Review the comparison and select **Use ruler** to prepare the calibration.
   **Keep supplied** writes nothing. **Measure again** returns to the inputs.
   Review quarter turn, panel offsets, and uncertainty. Offsets locate the
   transformed viewport origin on the panel in millimetres. Browser chrome can
   leave part of the panel outside the viewport; zero offsets require checking.
6. Save calibration. Guided saves are refused if the tablet is offline or its
   viewport no longer matches. Preparing measurements alone does not save them.

Saved calibration is a measurement record, not physical verification. The client
fences its physical image on viewport changes and requests a fresh plan. Manual calibrations can require recalibration after changes
to CSS size, DPR, orientation or display mode. Model assignments adapt to the
reported viewport while retaining the measured scale. Pinch
zoom prevents physical playback until the calibrated zoom is restored.

## Place tablets and verify the whole image

Add the measured tablets to the physical draft and position them as mounted,
including bezels and gaps. In **Arrange**, open **Custom bounds**, then
**Wall bounds**. Choose **Fixed wall size** or **Fit wall to tablets**. Packing
places bodies together in a draft. Check the real arrangement before applying it.

Create a test image with exactly the committed wall's aspect ratio. This command
generates 50 mm grid intervals, crossing diagonals and a circle for a sample
600 × 400 mm wall:

```sh
uv run python -m tools.calibration.make_grid \
  --width-mm 600 --height-mm 400 /tmp/wall-grid.png
```

Copy the PNG into the configured curated asset directory, refresh the normal
controller's image inventory, and select it as the wall image. With `make
hotspot`, the default directory is `~/.local/share/tablet-wall-ai/assets/`.
Generate the grid using your actual wall dimensions; otherwise global `cover`
fitting changes its physical spacing. The generator uses whole millimetres at
2 pixels/mm, up to 3,000,000 square millimetres. The existing logical Calibration
scene is not a physical-mode test image.

Measure grid intervals in both directions on each screen and inspect the
diagonals at seams. A 50 mm interval should measure 50 mm on the Air 2 and Pixel C
alike. Gaps intentionally hide the part of the image behind bezels. Adjust
profiles, offsets and placements from measured evidence, then repeat with the
poster and several slideshow cuts. Record ruler uncertainty alongside seam
error. A proposed acceptance target is error plus uncertainty no greater than
2 mm; this requires checking on the actual tablets.

Software tests and simulated viewports do not establish ruler accuracy, Safari
behavior or real-device slideshow timing.
