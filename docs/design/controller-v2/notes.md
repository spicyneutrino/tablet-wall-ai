# Controller v2: notes and self-critique

The strongest part is the wall-first layout. The wall is the largest object, the roster and inspector are rails, and the same device selection flows through all three. Placement is a drag, unplacement is one action, and tiling is previewed on the wall before a write.

The weakest part is the long right rail on tablet mode. Position and size, shape, move, bezel, colour, details, and removal cannot all fit at 900px height, so some actions sit below the fold. Remove and Place are pinned near the top to keep the most important reversible action reachable; the rest scrolls.

Three decisions I would still test with an operator:

1. **Tiling shape policy.** Keep screen shape is the default, but for a 3x2 grid of portrait tablets it produces narrow centred screens with large gaps. Fill looks more like a video wall but crops. The preview warns, but the default may still surprise.
2. **Mobile selection scroll.** Tapping a wall footprint scrolls to the inspector. That makes the controls reachable, but it also hides the wall the operator just touched. A split view or a bottom sheet might be better if the wall fits above it.
3. **The roster as the place to place from.** Dragging from the left rail to the wall works, but the drop target is far away on a wide screen. The inspector Place action is the keyboard/mobile fallback; repeated placement may be faster from a compact tray near the wall.

The 390px wall is a fitted overview, not a precision surface. The 2x zoom is contained, and all exact edits are in the inspector. That is the right tradeoff for scrolling, but it means mobile placement is a two-step task: select, then act.

The content tabs are not fully symmetrical: Colour and Calibration apply when selected, while Image selection is a browse state until Show on wall. That asymmetry follows the existing controller and the fact that an image needs a chosen file, but it is worth testing with operators. The physical setup page still uses the previous visual language. It was kept working by separating its stylesheet (`physical-legacy.css`) rather than restyling it in the same pass. That is deliberate scope control, not a claim that the two pages are visually finished together.
