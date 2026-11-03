# Tablet Wall — final controller design

**Status:** current operator workflow revision. Image previews remain local until Show image; arrangement previews remain local until Apply arrangement.

## Intent

The controller is a viewing instrument for a physical wall. The wall is the first and largest object on Images and Arrange. Everything else is a contextual tool around that object.

One design language: **Bone**. Warm neutral surfaces, charcoal ink, a graphite artwork field, precise geometry, no decorative effects.

The Bone palette study’s blue action/selection roles are **not** adopted. Production keeps its rust accent, green evidence, amber attention and red failure semantics. The Bone neutrals are the target values; the study’s contrast results do not validate this combined system.

## 1. Design system

### Surfaces, ink and state

| Token | Value | Use |
|---|---|---|
| `--bg` | `#EFECE4` | page canvas |
| `--surface` | `#FAF8F2` | working panels, inspector, library cards |
| `--surface-raised` | `#F3F0E8` | quiet bands, non-selected rows |
| `--text` | `#2D2822` | primary ink |
| `--muted` | `#5C564D` | secondary facts |
| `--border` | `#D8D3C7` | group and list separators |
| `--control` | `#67645D` | input and outline-control boundaries |
| `--hover` | `#F0ECE4` | hover fill |
| `--selected` | `#F5E5D7` | selected row or image wash |
| `--disabled-bg` | `#E7E1D5` | disabled controls |
| `--backdrop` | `rgb(30 26 21 / 60%)` | dialog scrim |
| `--stage` | `#22252A` | wall and image field |
| `--stage-text` | `#F2F0EA` | text on the wall field |
| `--stage-line` | `#8A8E95` | panel outlines and hatch |
| `--stage-selected` | `#FFC084` | selected panel on the wall |
| `--accent` | `#8F4014` | links, focus, selected/preview marks, hover edge |
| `--success` | `#246344` | current confirmed evidence |
| `--attention` | `#795500` | attention |
| `--error` | `#A12A24` | failure, removal |

Rust is never the resting fill of a primary/commit button. Primary and commit buttons use an ink fill (`#2D2822`) with cream text (`#EFECE4`) at rest; hover shifts to the rust fill. Rust is for links, focus, selection and preview, not the resting commit fill. Green is only for current confirmed evidence; the gallery's applied marker is neutral ink at weight 600, not green. The logo mark uses a rust border, not an inset shadow.

Working panels (image inspector, library and arrangement tools) use a quiet 1px `--border` edge and 12px corners against the canvas. Their shared inset is 20px on desktop and 16px on phone. Inputs and buttons retain 6px corners so the container and its controls have distinct scales. Use separators between task groups, list rows and control boundaries; do not nest outlined cards or add decorative elevation. No gradients, glass, or new icon system. The one allowed shadow is a true floating layer (native dialog/backdrop); no other shadow.

### Type and space

- One family: Schibsted Grotesk.
- Page title 28px/600 desktop and 26px phone; section 20px/600; body/control 16px; meta and quiet utilities 14px; tabular figures for millimetres and pixels.
- Spacing: 4 / 8 / 12 / 16 / 20 / 24 / 32 / 48.
- Radius: 6px controls, 12px working panels. No uppercase micro-labels, decorative pills, or tracked caps.
- Surfaces use `--surface`; page uses `--bg`; selected rows use the `--selected` wash plus a 3px rust edge.

### Shell

- Header 64px desktop, 56px portrait mobile, 44px short landscape.
- Task navigation 52px desktop. On portrait mobile it becomes a fixed bottom bar, safe-area aware, 56px. Short landscape has no bottom nav and no task title; a 44px tab row remains.
- Content max 1600px, padding 32px desktop / 16px mobile.
- One task heading per panel. The wall heading is a smaller section heading, and the stage state is sentence case. Shape controls use their own labels without an extra heading.

## 2. Wall fit contract

This is the primary rule. The wall **bounds** — not the dark field — must fill at least 80% of the stage’s limiting dimension.

- The stage column measures its available width and the available viewport height after header, navigation, task heading, stage mode row, and a 16px bottom margin. When a preview or commit action bar is visible, subtract its measured height, gaps and safe-area inset before fitting. The height is not a fixed `44vh`, `50vh`, or `68vh`.
- The SVG viewBox uses a 10-unit outer margin, not the current 28-unit margin. The wall bounds keep their configured aspect ratio, device geometry, bezels, gaps, and empty logical regions.
- The dark `.stage-scroll` field shrink-wraps the SVG. Slack goes to the page canvas or the inspector column, never to dark side bands. The field is centered when height-limited.
- The stage fit is recalculated on window resize, tab change, inspector width change, and wall/layout update. A content-driven fallback keeps the stage usable when the viewport is short.
- At 1440/1280/1024, a width-limited wall must occupy at least 80% of the stage column width; a height-limited wall must occupy at least 80% of the available height.
- For wall aspect ratios of 2.6:1 or wider, the stage spans the full workspace width and the inspector/library sit below it. That avoids a large empty left column around a 1×4 wall.
- Above 48rem, Images keeps the stage left and the inspector/library in the same right rail, including 1024px. The rail ranges from 18rem to 22.5rem. At 48rem or narrower, the order is stage, inspector, library; DOM and visual order agree.
- For tall or portrait walls, the dark field is centered on `--bg` within the stage column; the inspector does not consume the stage's horizontal slack. The wall stays at its correct size, not stretched to fill.
- Never stretch or crop the arrangement to fill the field.

The SVG labels use screen-space sizing. They target 11–13 CSS px after both the world scale and the SVG’s CSS scale. If a panel cannot hold a 10px label, labels are omitted and the external identity list is the source. Labels are not drawn as tablet content.

## 3. Layout

### Images — desktop

```
┌───────────────────────────────────────────────┬───────────────┐
│ wall stage                                    │ inspector     │
│ (dominant; dark field shrink-wraps the wall)  │ image status  │
│                                               │ Fit / Show    │
│                                               │ image facts   │
│                                               ├───────────────┤
│                                               │ library 2-up  │
└───────────────────────────────────────────────┴───────────────┘
```

- Grid: `minmax(0, 1fr) clamp(18rem, 31vw, 22.5rem)`, gap 20–32px. The stage starts immediately after the task heading. The 360px inspector has 20px inner padding, reduced to 16px on phone.
- The reviewer’s desktop filmstrip is dropped. The library is a 2-up thumbnail grid in the right column under the inspector; it is sticky while the wall is height-limited. This is what preserves the wall’s height.
- Inspector and Library share the same border, corners and content inset. Panel headings are 18px; disclosures sit behind quiet separators and use 14px muted type. Arrangement-tool disclosures use the same type and aligned disclosure markers. Text utilities keep padded hover targets while aligning their text with the panel content. Empty feedback fields take no space.
- The inspector is one surface: image title/dimensions, selected-image facts, Fit, Show/Restore, preview consequence, command message. It does not repeat applied content. Advanced/alternate/upload controls are disclosures at the bottom.
- Stage mode line is the **only** applied-content home:
  - `Saved wall · Calibration pattern · 2 000 × 1 000`
  - `Saved wall · supplied.png · Fill wall`
  - `Image preview · not on tablets` + a secondary `Applied: Calibration pattern` only when previewing.
  - `Arrangement preview · not applied`.
- Delete `#active-image` from the inspector; its fact moves to the stage mode line. The stage line may wrap on mobile; there is no second applied-content caption.
- Draft dimensions appear in the inspector; applied dimensions appear in the stage mode line. There is no second `.stage-scale`. Applied content appears only in the stage mode area; the inspector never repeats it.

### Arrange — desktop

```
┌───────────────────────────────────────────────┬───────────────┐
│ wall stage, editable                          │ tools         │
│ direct manipulation                           │ presets       │
│                                               │ selected panel│
│                                               │ Apply/Discard │
└───────────────────────────────────────────────┴───────────────┘
```

- Stage left, 360px tools right (same width as Images). Presets are a compact row. Shape, membership, custom numbers, mounting and pins are disclosures in the tools column.
- One Apply/Discard pair. Remove the secondary pair inside “Custom positions and bounds.”
- Panel labels are the stage identity. The selected-panel chip says **Included in show** or **Excluded from show**, never paint.
- The commit bar is attached to the stage bottom; the tools column does not steal the stage’s height.

### Tablets

- Roster left, selected-device inspector right on desktop.
- One status phrase per row: “Offline · spot reserved” once. Accessible names do not repeat “offline” twice.
- The default inspector shows one status line, one recovery sentence/action, and Identify/Reconnect. Naming, measurements, lifecycle, and replacement are behind one Details disclosure.
- Unplaced tablets lead with **Place on wall**, not offline-recovery prose. Recovery is for placed offline devices.
- Placement membership is **Placed** / **No placement**; paint evidence remains in the header/Issues.

### Saved and Settings

- No wall stage. Content max 64rem.
- Saved: arrangements and scenes as two distinct lists with compact rows.
- Settings: readiness first, then facts; revision/generation/schema stay in wall technical details. Utility buttons are label-width, not column-width.

## 4. State model

| Viewed state | Stage mode | Inspector | Primary action |
|---|---|---|---|
| Applied, no draft | `Saved wall · <content> · <fit>` | “Change the image”; no inactive edit form | Adjust saved image / Choose another image |
| Local image preview | `Image preview · not on tablets` | Preview consequence; applied content is named once in the stage mode area | Show image / Discard preview |
| Preview retained, viewing applied | `Saved wall · <content>` | “Preview ready · viewing applied” | View preview / Show / Discard |
| Arrangement preview | `Arrangement preview · not applied` | Geometry consequence, selected screen | Apply arrangement / Discard |
| No image saved | `Saved wall · <content>` | “Change the image” and library guidance | Choose an image |
| Conflict/stale | Mode unchanged | Rebuild/refresh message beside the action | Retry / rebuild |

- **Inspected** means the library image carries the rust outline and is the current local draft. There is no separate “selected but not previewed” state.
- The rust outline marks a retained draft. It remains when the operator uses **View applied**, and disappears after a successful **Show** or **Discard**. After Show, the applied image carries the neutral **Applied** marker but is not “inspected” unless a new draft is made.
- Loading Images does not create a draft. Adjust saved image explicitly creates a guarded preview of the saved image and its current fit. Choose another image focuses the library. The editing controls appear only while a draft exists. Command feedback and Restore remain accessible after the draft is cleared. If no draft exists, the applied image is marked **Applied** but has no rust outline. Clicking any library image, including the applied one, creates a local draft. The inspector shows image facts only for an existing draft.
- **Applied** means server configuration only. It does not mean a tablet painted it. Applied content is named once in the stage mode area; the inspector never repeats it.
- **View applied** while a draft exists changes the stage to the applied configuration; the rust outline stays, and the inspector offers **View preview**. The draft is not lost.
- **Show** succeeds: the draft becomes applied, the rust outline disappears, the neutral Applied marker moves to that image, and the stage mode returns to Saved wall.
- **Discard** removes the draft: the rust outline disappears and the stage returns to the applied configuration.
- **Report current image** is software evidence. The header and Issues own it; `renderShownStatus()` returns brief command feedback only (“Image applied”, “Image applied; status stale”, “Wall changed after this command”), not per-tablet paint outcomes.
- Keep the preview-is-not-tablet-output sentence once, in technical details.
- Command failures, conflict, stale-preview rebuild, unavailable-image recovery, and crop/bar consequences stay beside the action.

## 5. Status wording

- Header separates tablet connections from current display reports. The footer names the controller server connection explicitly. Tablet counts distinguish registered browsers from retained wall positions missing a registration; server checks count the same registered browsers.
- Offline is derived; do not print `4 offline` as a third number.
- Tablet state text: “Reports current image” for a current image render; “Current scene reported” for non-image; “Offline · spot reserved” once.
- Placement: “Placed” / “No placement”; “Included in show” / “Excluded from show” for participation.
- The applied content is one phrase in the stage mode line. No “Currently showing”, no “This image is on the wall”, no gallery check prefix.
- Gallery: one rust outline for the inspected/preview image; one neutral-ink “Applied” text marker for server configuration. Applied text has a reserved lower row and an accessible description. Green is not used for applied configuration.
- Issues is the only paint drill-down.

## 6. Image library

- Desktop: 2-up grid under the inspector. Track width is `(column inner width − gap) / 2`, approximately 160px at the 360px rail; do not use fixed 160/180px tracks. Mobile/landscape: horizontal strip, 132px tracks, scroll-snap.
- Cards: `min-inline-size:0`, `overflow:hidden`, image `max-inline-size:100%; display:block; object-fit:cover; aspect-ratio:4/3`. Filename uses a two-line clamp with ordinary text wrapping and a complete accessible name/title. No forced breaks at underscores. Applied row is reserved so cards do not jump.
- No check prefix. Selected/preview = one 2px rust outline + `--selected` wash. Applied = neutral-ink “Applied” text at weight 600, no border.
- One visible search label and a distinct placeholder; Add image is label-width. Library cards show filename only, no dimensions. Applied dimensions live in the stage mode line; draft dimensions live in the inspector only while a draft exists.
- Thumbnail images stay constrained by the card. Missing thumbnails retain the filename and selection action.

## 7. Mobile

### Portrait

- Header 56px: brand, `0/4` (aria-label “0 of 4 report current image”), Issues. No connected summary.
- Fixed bottom navigation 56px + safe area; content padding-bottom accounts for it.
- Images follows stage, inspector, library. Idle actions provide an explicit way to browse or adjust the saved image. The preview action bar appears only after an explicit selection; Fit / Show / Discard share a row, with view actions below.
- Stage notes and technical text align with the page gutter on phone; only the artwork field is full-bleed.
- The phone wall is full-bleed to the screen edges. Its height respects both the wall aspect and the space needed for image controls; a 1.855:1 wall at 390px width is about 200px tall. Do not crop or rotate the wall to make the phone preview taller.
- The stage height budget is `100dvh − 56px header − 56px bottom nav − safe area − measured action bar − gaps` while a preview exists. When no preview exists, the action bar is absent. Portrait stage fitting reserves the measured idle action area and trailing stage notes, including wrapped lines, so both image-change actions stay within reach. Short screens fall back to scrolling.
- The action bar is fixed above the bottom nav: `position: fixed; inset-inline: 0; inset-block-end: calc(56px + env(safe-area-inset-bottom)); z-index: 35; background: var(--surface); border-block-start: 1px solid var(--border);` with content padding-bottom accounting for it. It contains Fit, Show, Discard, and View preview when a retained draft is viewing applied. The stage aspect ratio is preserved as this budget changes; the wall is never cropped to make the bar fit.
- Arrange: stage first, preset row, one commit bar; advanced controls in a disclosure.
- Tablets: roster first; selecting a row opens a **native `<dialog>` sheet**. `showModal()` gives focus containment, Escape and backdrop. The sheet is bottom-anchored with `margin: auto 0 0`, has a close button, max-height `calc(100dvh - 56px - env(safe-area-inset-top) - env(safe-area-inset-bottom))`, internal scrolling, and returns focus to the row. The 56px is header clearance; it is not the bottom navigation. The sheet may cover the bottom nav because it is in the top layer; do not subtract the nav height from its limit.
- No horizontal overflow; 44px targets; `touch-action:none` only on the editable Arrange stage.

### Short landscape (`max-height: 32rem` and `orientation: landscape`)

- Header 44px, no task title, no bottom nav; keep a 44px tab row.
- Full-width stage capped to the remaining height; a 44px primary action bar stays visible when a preview or draft exists. The wall remains visible without scrolling.
- The 844×390 budget is `390 − 44 header − 44 tabs − 44 action bar − 20 mode − 16 margin = 222px` for the stage while a preview exists. A 1.855:1 wall uses ~412×222 and is centered; this is intended. When no preview exists, the action bar is absent and the stage gains 44px.
- No desktop inspector stack; the library and secondary controls scroll below.

## 8. Acceptance

- 1440×900, 1280×800, 1024×768, 390×844, 844×390: no horizontal overflow; no dark side bands; wall bounds ≥80% of the limiting stage dimension. At 1024 the same side rail is retained.
- Width-limited and height-limited walls, 2×2, 1×4, portrait and unusually wide layouts, all preserve geometry and empty bounds.
- The stage and primary action are visible in the first screen on Images and Arrange in all preview/applied states; the portrait action bar clears the bottom nav and the short-landscape action bar is inside the viewport. One applied-content phrase; one commit pair.
- Selected/preview/applied states are distinguishable with one encoding each.
- Tablet rows have unique names; no duplicate Offline; accessible names do not repeat status.
- Keyboard: tab order follows visual order; stage panels reachable; Enter opens the device sheet; Escape closes; focus returns.
- Tablist inside a navigation landmark; stage labels `aria-hidden` with full group names; applied marker described; 44px targets.
- No shadows, gradients, new icon library, CSS framework, or backend contract change.
- Physical seams, sleep, and unattended operation remain unverified and are never claimed.

## 9. Deliberate non-goals

- No new backend feature, route, or persistence shape.
- No blue action color or blue selection wash.
- No mobile wizard.
- No removal of calibration, conflict, ETag, preview/apply, or honest evidence.
- No claim that a browser screenshot proves physical alignment.

## Implementation notes

- The tablet name input remains visible above the collapsed “Placement and technical details” disclosure. Naming is a first-time task; hiding it cost more than the saved height. The council accepted this deviation.
- The portrait preview bar contains Fit, Show and Discard on one row, with view actions below. It preserves 44px touch targets. Feedback stays in the inspector. At 1024px the controls stay in the right rail instead of becoming a separate fixed bar.
- The short-landscape stage is height-limited to roughly 379×195 by the 44px header, 43px tabs and 45px action bar. It uses the full available height and preserves the wall aspect; the 80% rule is measured against the limiting dimension.

- The phone tablet inspector preserves its open modal and unsaved fields during height-only changes. It reconfigures only when crossing between phone and desktop modes.
- Settings leads with network, live registered-tablet, upload and trust facts. Detailed server, backup and storage evidence remains in native disclosures.
- With enlarged text, the phone header wraps and task navigation can scroll inside its own bounds. Navigation height and action-bar clearance grow with text size.
