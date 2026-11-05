# Choose how the wall gets its size

Fixed and tablet-fit sizing serve different starting points. Fixed sizing
starts with a canvas to fill. Tablet-fit sizing starts with an arrangement
of screens and derives the canvas around it.

## Fixed wall

Open `/controller/` and select **Arrange**, then **Custom bounds**.
For a measured layout, use **Wall bounds**, choose **Fixed wall size**, and
edit the dimensions in millimetres. X and Y set the rectangle's origin.
For a relative layout, use **Relative arrangement** and choose **Fixed bounds**.
Its width and height use logical wall units.
Select **Apply arrangement** to commit the draft.

The compatibility editor at `/controller/experimental.html` retains the old
**Layout**, **Fixed wall**, and **Save size** controls for logical layouts.
Changing its wall size leaves tablet footprints at their existing coordinates.

## Fit the wall around tablets

For a measured layout, choose **Fit wall to tablets** under **Wall bounds**.
For a relative layout, choose **Fit to tablets** under **Relative arrangement**.
For a grid preset, **Tablets and mounting** offers **Fit wall to tablet bodies**.
The smallest axis-aligned rectangle enclosing the placed tablet bodies becomes
the wall. Set margin or outer padding to zero for a
tight enclosure, or increase it for space around the arrangement.

This mode follows layout edits, not network presence. An offline tablet or
vacant saved spot still contributes its footprint. Unplaced tablets do not.
With no placements, the previous wall dimensions remain until a tablet is
added. Switching back to fixed keeps the fitted dimensions as an editable
starting point. Modes and padding survive restart and named-layout recall.

The compatibility editor translates the arrangement so its top-left footprint
starts at the chosen margin. Relative positions, footprint dimensions, and bezels stay
the same. The workspace preserves measured centers, nudges, and mount angles;
the enclosing rectangle can therefore have a negative X or Y origin.

Fitting changes the canvas used for the global image crop. It does not stretch
the individual tablets to fill newly available space. Irregular arrangements
can leave holes, and diagonal tablets can leave empty corners inside the
enclosing rectangle.

## Bring tablets together

Fitting alone preserves the gaps you arranged. Packing is a separate,
explicit action. In tablet-fit mode, choose the number of columns and the
gap between tablets, then use **Pack placed tablets** or **Pack tablets**.
Each row places bodies next to one another without changing their sizes or
orientations. A zero gap makes cardinally mounted tablet bodies touch.
Rows start below the tallest footprint in the preceding row. Mixed heights
can leave space below shorter tablets; this is predictable row packing, not
a search for the globally smallest possible layout.

The compatibility editor applies packing immediately as one change. Save a named
layout beforehand to retain a return point. Its placement-only Undo and old
cell-tiling tools are disabled while fitting, because a change can translate
every footprint. The workspace packs its draft and offers **Undo**, **Redo**, and
**Discard arrangement**. Packing reaches the wall only after **Apply arrangement**.

## Match actual hardware

Logical footprints use wall units and cannot infer physical dimensions from
browser pixels. Tablets have different pixel densities, borders, and usable
browser areas. For an accurate installation, measure the active panels and
borders through **Tablets**, then **Review measurements**. Calibrate each
tablet and set its mount angle in **Arrange**.

Physical fitting uses each slot's exact saved measurement revision. A newer
measurement does not silently resize a slot that still references an older
revision. Missing measurements block fitting and packing. At non-cardinal
angles, packing uses the rotated body's enclosing rectangle, so diagonal
edges are not guaranteed to touch.

## Why fitting is a mode

A one-time fit button would become stale after moving, removing, or rotating
a tablet. A saved mode keeps the canvas consistent with the saved arrangement.
Packing remains explicit so ordinary edits do not unexpectedly move neighbors.
