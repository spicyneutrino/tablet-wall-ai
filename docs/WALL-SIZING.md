# Choose how the wall gets its size

Fixed and tablet-fit sizing serve different starting points. Fixed sizing
starts with a canvas to fill. Tablet-fit sizing starts with an arrangement
of screens and derives the canvas around it.

## Fixed wall

In Wall control, open **Layout**, choose **Fixed wall**, enter the width and
height, and click **Save size**. Dimensions use logical wall units. Changing
the wall size leaves tablet footprints at their existing coordinates.

In Physical setup, open **System → Wall bounds**, choose **Fixed wall size**,
and edit the dimensions in millimetres. X and Y set the rectangle's origin.
Click **Apply layout** to commit the draft.

## Fit the wall around tablets

Choose **Fit to tablets** in Wall control, or **Fit wall to tablets** in
Physical setup. The smallest axis-aligned rectangle enclosing the placed
tablet bodies becomes the wall. Set margin or outer padding to zero for a
tight enclosure, or increase it for space around the arrangement.

This mode follows layout edits, not network presence. An offline tablet or
vacant saved spot still contributes its footprint. Unplaced tablets do not.
With no placements, the previous wall dimensions remain until a tablet is
added. Switching back to fixed keeps the fitted dimensions as an editable
starting point. Modes and padding survive restart and named-layout recall.

Wall control translates the arrangement so its top-left footprint starts at
the chosen margin. Relative positions, footprint dimensions, and bezels stay
the same. Physical setup preserves measured centers, nudges, and mount angles;
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

The basic controller applies packing immediately as one change. Save a named
layout beforehand to retain a return point. Its placement-only Undo and old
cell-tiling tools are disabled while fitting, because a change can translate
every footprint. Physical setup packs its draft, supports Undo, Redo, and
Cancel, and sends the arrangement only when you click **Apply layout**.

## Match actual hardware

Logical footprints use wall units and cannot infer physical dimensions from
browser pixels. Tablets have different pixel densities, borders, and usable
browser areas. For an accurate installation, measure the active panels and
borders in Physical setup, calibrate them, and set each tablet's mount angle.

Physical fitting uses each slot's exact saved measurement revision. A newer
measurement does not silently resize a slot that still references an older
revision. Missing measurements block fitting and packing. At non-cardinal
angles, packing uses the rotated body's enclosing rectangle, so diagonal
edges are not guaranteed to touch.

## Why fitting is a mode

A one-time fit button would become stale after moving, removing, or rotating
a tablet. A saved mode keeps the canvas consistent with the saved arrangement.
Packing remains explicit so ordinary edits do not unexpectedly move neighbors.
