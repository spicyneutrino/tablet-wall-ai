# Controller v2: final plan

## What this is

A redesign of the tablet-wall controller from a stack of cards into a wall-first editor. The wall is the document. The left rail is the roster, the centre is the wall, and the right rail is one context panel for the selected tablet, the wall content, or the layout. The design is restrained, mineral, and green-accented rather than a generic dashboard.

This plan is the synthesis of four independent design rounds and two cross-reviews. The design round hit account limits, so the final plan was completed from the artifacts and transcripts, not from a fresh Opus run. The process is recorded in `REVIEWS.md`.

## Design rounds and what survived

| Lead | Artifact | What survived |
|---|---|---|
| Sonnet | Mockups complete, docs rate-limited | Wall-as-document, direct placement, the tiled-grid overlay with numbered cells and click-to-swap, the honest request count, the physical bezel treatment |
| Opus | Desktop mockup complete, mobile/docs quota-limited | Continuous single image across the wall, the right context rail with Tablet/Content/Layout, the shelf of tablets, the exact shape-mismatch explanation and Match screen shape |
| Sol | Complete design, mockups, 22 interaction checks, final synthesis mockups produced before a quota stop | Three-region frame, selection sync, exact geometry inspector, move-first mobile inspector, undo model, honest tile write model, capability map |
| Astra | Mockups complete, docs quota-limited | Mineral sage/cream palette, type hierarchy, stable roster, layout thumbnails, browse-then-apply content flow |

The cross-review rejected a permanent bottom dock plus a left rail, a fixed mobile status bar, and a number-only device name system. It kept the left roster, the wall-first centre, one context rail, and a real mobile task bar.

## Final layout

Desktop at 1440:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Tablet wall   Live  3/4 online        Tablet address  Copy   Physical setup  │ 54
├──────────────┬──────────────────────────────────────────┬────────────────────┤
│ Tablets   4  │ Wall   1800 × 800 units        Tile      │ Tablet Content     │
│ 3 placed     │ On the wall  image.png  Change           │ Layout             │
│ 1 unplaced   │ Snap  Grid 20     Undo Redo 2x Keys      │                    │
│              │                                          │ selected ID        │
│  [rows]      │        wall canvas with rulers           │ position / size    │
│              │        physical bezels, handles          │ shape + match      │
│  Saved       │                                          │ move / bezel       │
│  layouts     │ legend · coordinates · warnings          │ colour / details   │
│              │                                          │ remove / place     │
├──────────────┴──────────────────────────────────────────┴────────────────────┤
│ 10:35:12  status message                         Revision 71  Session 8617f74a│ 34
└──────────────────────────────────────────────────────────────────────────────┘
```

- Left rail: 204px. Tablets, placed/unplaced groups, saved spots, saved layouts.
- Centre: flexible. Wall size, actual content, snap/grid, undo/redo, zoom, keys, canvas, legend, warnings.
- Right rail: 308px. Tablet, Content, Layout.
- At 901-1200px: 190px / flexible / 292px.
- At 900px and below: task bar Wall, Tablets, Content, Layout; one task at a time; fitted wall plus a contained 2x zoom; selected inspector below the wall.

## Interaction decisions

- **One selection.** Wall footprint and roster row select the same device. The inspector follows. Focus stays visible after a re-render.
- **Move.** Pointer drag on the wall; snap to grid, wall edges, and other footprints; Alt disables snap; Escape cancels; live coordinates.
- **Resize.** Four corner handles; exact W/H; visible-aspect lock; Match screen shape sets the height that matches the screen.
- **Place.** Drag an unplaced row onto the wall, or press Place. The keyboard/mobile fallback is the inspector's Place action, which finds the first free footprint.
- **Remove.** One action in the inspector header or via drag back to the roster. Undo, not a confirmation dialog. Delete also works.
- **Tile.** Scope, order, columns, rows, gap, shape policy. The wall shows numbered preview cells. Click two cells to swap. Apply is blocked on capacity or a retained-spot conflict. Custom tiling writes placements one after another and reports partial failure; it never claims atomicity.
- **Undo.** Local placement history for move, resize, place, remove, and tile. Undo is a persistent button, not only a toast. History clears on a session/generation change.
- **Content.** Colour and Calibration are direct mode switches. Image selection is separate from applying, because an image needs a file first. The header always reports the actual wall. The image preview shows the active image even before a replacement is selected.
- **Mobile.** Wall first. Task tabs. Tap selects and reveals the inspector. The inspector puts 44px move arrows before numeric fields. No page-level horizontal scroll.

## Implementation

The existing data layer is kept. The tile template stays in the DOM as the hidden exact-field source so `savePlacement()`, protocol handling, and the browser evidence runner keep working. The new stage layer adds selection, drag, resize, tiling, undo, and mobile task state around it.

`physical.html` keeps the previous shared styles under `physical-legacy.css`, so the controller redesign does not break the physical editor.

## Calibration and identity

Every tablet gets a small display number, lowest free over the in-memory roster. The controller shows it in the roster, the wall label, and the inspector. The calibration scene draws the same number large on the tablet and previews each tablet's grid and number on the controller map, so a person can match a physical screen to a row without decoding a UUID.

The number is leased for 15 minutes after the tablet goes offline. A replacement can take an expired number; the old record loses it and the controller is told. The number is process-local, but a returning browser remembers it in localStorage and asks for it on registration; after a server restart it reclaims its previous number while it is free. That is documented in PROTOCOL.md.

The image preview in the controller now uses the same centered cover geometry as the client. The map and the roster thumbnail both use the image origin, not its negative offset.

## Verification

- Browser evidence: 106/106 checks passed, `/tmp/opencode/tablet-wall-final-reclaim/report.json`.
- Python: 647 passed.
- Client JS: 28 passed.
- View JS: 8 passed.
- Deployment guards: 3 passed.
- Manual: 1440, 1280, and 390 layouts; no horizontal overflow; selection, drag move, corner resize, place, remove, undo/redo, tile apply, tile undo, content switching, and mobile tasks exercised.
- Manual feature test: four simulated tablets kept #1–#4 across a server restart, reconnected within one second, and the controller logged each connect and disconnect. A tablet taken offline for 18 seconds showed Reconnecting, released its socket, and returned as #1.

## Known limits

- Custom tiling is sequential by design. A mid-run failure can leave earlier writes applied; the UI reports the count and offers undo.
- Undo replays placements through the existing per-device API. It is not atomic and can be beaten by another controller.
- The wall map is a diagram. It maps the active image and bezels, not an optical measurement.
- The physical setup page keeps its existing visual language; only its shared stylesheet dependency was separated.
- Mobile does not support pointer-dragging a mounted tablet; it uses tap, Place, and stepping. This avoids scroll conflicts.
