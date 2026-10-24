# Controller v2: implementation map

## Files

- `frontend/controller/index.html`: new three-region shell, inspector, content and layout panes, tile tool, mobile task bar. Keeps every existing controller ID that `controller.js` and the browser evidence runner use.
- `frontend/controller/controller.css`: the new console stylesheet. `physical.html` no longer loads it.
- `frontend/controller/physical-legacy.css`: the previous shared stylesheet, kept so the physical editor is unchanged.
- `frontend/controller/physical.html`: loads `physical-legacy.css` and `physical.css`.
- `frontend/controller/controller.js`: existing data/transport layer plus the new stage layer.
- `simulator/browser/run.py`: opens the Content context tab before driving the calibration, image, and upload controls.

## Preserved contract

The existing element IDs are still present. The browser runner and the controller logic depend on these groups:

- Connection: `conn`, `conn-label`, `btn-reconnect`, `tally-online`, `tally-total`, `client-url`, `btn-copy-url`.
- Wall: `wall-form`, `wall-width`, `wall-height`, `btn-wall-save`, `auto-columns`, `btn-auto`, `wall-note`, `wall-rev`, `wall-gen`, `map-viewport`, `map-frame`, `map-empty`, `map-caption`, `alerts`, `alert-nocap`, `alert-nocap-title`, `alert-nocap-text`, `alert-unverified`, `alert-unverified-text`.
- Roster: `grid`, `empty`, `empty-conn`, `tile-tpl`, `reservations`, `res-list`.
- Content: `show`, `show-title`, `wall-content`, `wall-content-state`, `content-now`, `colour-block`, `calibration-block`, `calibration-state`, `image-panel`, `global-palette`, `global-color`, `global-sel`, `btn-apply-all`, `image-active`, `image-active-text`, `image-missing`, `image-missing-title`, `image-missing-text`, `btn-missing-pick`, `btn-assets-refresh`, `image-count`, `image-sel`, `image-note`, `asset-list`, `image-empty`, `btn-image-apply`, `image-preview`, `image-preview-img`, `image-preview-note`, `upload-block`, `upload-file`, `btn-upload`, `upload-file-name`, `upload-progress`, `upload-status`, `media-library`, `media-list`, `media-count`, `media-note`.
- Snapshots: `layout-save-form`, `layout-name`, `btn-layout-save`, `layout-msg`, `layout-overwrite`, `layout-overwrite-text`, `btn-layout-overwrite`, `btn-layout-overwrite-cancel`, `layout-list`, `layout-empty`, and the matching scene IDs.
- Status: `status-stamp`, `status-text`.

The tile template still carries the exact placement inputs, palette, colour input, forget action, and readout. They are hidden by CSS but remain the source that `savePlacement()` reads.

## New stage state

- `selectedId`, `contextMode`, `mobileTask`.
- `stageUndo` / `stageRedo` entries: `{before, after, label}` placement maps.
- `stageDrag`: move or resize gesture, pointer capture, start placement, live placement.
- `pendingNudge` and a 320ms flush timer.
- `tilePreviewPlan`, `tilePreviewSelected`, `tileApplying`.
- `inspForgetPending` and its timer.

## New functions

### Selection and panes

- `selectDevice(id, options)`: one selection for wall and roster; syncs tile selection, map outline, inspector, and optional tile scroll.
- `renderSelection()`: fills the inspector from `devices` and `wall.placements`; skips field writes while an inspector input is focused; updates state, shape, colour, details, and action labels.
- `setContextMode(mode)` / `setMobileTask(task)` / `applyPaneVisibility()`: desktop Tablet/Content/Layout panes and mobile Wall/Tablets/Content/Layout tasks.
- `renderWallSummary()`: placed, unplaced, offline, saved-spot, shape, and image counts.

### Direct placement

- `startStageDrag(event, id, box, mode, corner)`: pointer capture, move or resize, Escape cancel, Alt disables snapping.
- `snapPlacement()`: grid, wall edges, other footprint edges; whole-unit rounding.
- `startStageDrag` / `endStageDrag` / `cancelStageDrag` / `resize` handles added to the selected `.map-pl`.
- `dropDeviceOnWall()`: native drag from the roster to the wall.
- `firstFreePlacement()` / `placeSelectedFirstFree()`.
- `dropDeviceOnWall()` and drag-to-roster removal.

### Exact geometry

- `readInspectorPlacement()` validates fields and bezels, then rounds at the API boundary.
- `commitPlacement()` writes through the existing `savePlacement()` and records history.
- `nudgeSelected()` / `flushNudge()`.
- `matchHeightFor()` / `matchSelectedShape()`.
- `onInspectorDimensionInput()` keeps the visible aspect when the lock is on.

### Undo and redo

- `pushStageHistory()`, `renderStageHistory()`.
- `undoStage()` / `redoStage()`.
- `applyPlacementMap()` replays a placement map through existing PUT/DELETE endpoints. It is sequential and not atomic; failures are reported.

### Tiling

- `buildTilePlan()` / `finishTilePlan()`: scope, order, columns, rows, gap, keep-shape or fill.
- `fitPlacementInCell()`: solves the visible rect to the device aspect inside a cell.
- `startTilePreview()` / `renderTilePreviewOnWall()` / `toggleTileCell()`: numbered overlay, two-cell swap, blocked apply.
- `applyTilePreview()`: sequential `PUT /devices/{id}/placement`; records the applied subset for undo; reports a partial failure honestly.
- `roundPlacement()`: the wire model uses integers, so fractions from fitting are rounded once at the boundary.

### Wall and roster rendering

- `renderWall()` now also updates dimensions, summary, selection, layout shortcuts, and history.
- `renderTiles()` syncs selection/summary/history.
- `createTile()` adds selection, keyboard, and drag behavior; the row is a compact list option.
- `updateTile()` / `renderPlacement()` set `data-placement` and the row location.
- `buildMapPlacement()` adds `data-id`, `data-selected`, drag/pointer handlers, resize handles, and image slices.
- `paintMapSlice()` / `paintTileScreen()` map the active image through each visible rect.
- `renderWallMap()` preserves the tile layer, updates rulers/selection, and repaints the image after assets load.
- `renderRulers()`, `updateStageReadout()`, `renderLayoutShortcuts()`.

### Assets and snapshots

- `refreshAssets()` / `refreshMedia()` repaint the wall after the library loads.
- `updateImageControls()` previews the active wall image when no replacement is selected; it does not change selection.
- `renderSnapshotPanel()` refreshes the left-rail layout shortcuts.

### Mapping, calibration, and display numbers

- `paintMapSlice()` uses the image's top-left in the map frame. The position is `offX - visible.x/wall.width*pxW`, and the same for Y. The previous negative-offset form shifted a letterboxed image down or right.
- `paintTileScreen()` uses the two-stage cover: visible rect to thumbnail, then the wall image to that virtual wall. A simple wall-cover shrank the crop.
- `paintCalibrationSlice()` paints a wall-aligned minor and major grid inside each visible rect.
- `buildMapPlacement()` hides the normal label in calibration, adds a centred number badge and the short id, and adds the large number only when the scene is calibration.
- `tabletwall/state.py`: `_recycle_device_numbers()` releases numbers for devices without an open socket and older than `DEVICE_NUMBER_LEASE_S`; `_ensure_device_number()` assigns the lowest free number. Both run synchronously before an await.
- `main.py`: registration preserves `number`, allocates it, and broadcasts `device_updated` for any released holder. The device socket ensures a number after reconnect and includes it in the v2/v3 welcome. The v1 welcome is unchanged.
- `frontend/client/client.js`: stores the welcome number outside the revision-gated wall state, repaints on a changed welcome, and draws one screen-space badge on calibration and diagnostic screens.
- The number lease is in-memory. A server restart renumbers in reconnect order, noted in PROTOCOL.md.

## API notes

- No backend changes. Placements still use `{x, y, w, h, bezel}` and must be integers.
- Tiling gap is computed; it is not persisted.
- Custom tiling is a sequence of existing placement PUTs. The UI does not claim atomicity and offers undo for completed writes.
- Image content remains one asset across the whole wall; each tablet is a window into the same mapping.
- Undo replays existing PUT/DELETE calls.

## Test plan and results

- Browser evidence: `106/106` checks passed, `/tmp/opencode/tablet-wall-calibration-final/report.json`.
- Python: `645 passed`.
- Client JS: `27 passed`.
- View JS: `8 passed`.
- Deployment guards: `3 passed`.
- Manual: 1440, 1280, and 390 layouts; no page horizontal overflow; selected inspector, drag move, corner resize, place, remove, undo/redo, tile preview/apply/undo, content switching, and mobile tasks.

## Known risks

- The custom tiling apply is sequential; a partial failure leaves earlier writes in place and only reports/undoes them.
- Undo is best-effort against a second controller; there is no compare-and-swap API.
- The wall map is a diagram, not an optical measurement.
- Mobile uses tap/select/step rather than pointer-dragging mounted tablets, to keep page scrolling usable.
- The physical page retains its previous visual language; only its stylesheet dependency changed.
