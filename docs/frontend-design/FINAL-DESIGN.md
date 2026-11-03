# Tablet Wall — final controller design

**Status:** revised after four-member design gate. Target: every member ≥ 9/10 before implementation.

## Intent

The controller is a viewing instrument for a physical wall. The wall is the first and largest object on Images and Arrange. Everything else is a contextual tool around that object.

One design language: **Bone**. Warm neutral surfaces, warm charcoal ink, a deep warm artwork field, precise geometry, no decorative effects.

The Bone palette study’s blue action/selection roles are **not** adopted. Production keeps its rust accent, green evidence, amber attention and red failure semantics. The Bone neutrals are the target values; the study’s contrast results do not validate this combined system.

## 1. Design system

### Surfaces, ink and state

| Token | Value | Use |
|---|---|---|
| `--bg` | `#F5F0E7` | page canvas |
| `--surface` | `#FDFBF6` | working panels, inspector, library cards |
| `--surface-raised` | `#F9F5EE` | quiet bands, non-selected rows |
| `--text` | `#2D2822` | primary ink |
| `--muted` | `#5C564D` | secondary facts |
| `--border` | `#DED8CC` | group and list separators |
| `--control` | `#6F685C` | input and outline-control boundaries |
| `--hover` | `#F6F2EA` | hover fill |
| `--selected` | `#F5E5D7` | selected row or image wash |
| `--disabled-bg` | `#EEE8DE` | disabled controls |
| `--backdrop` | `rgb(30 26 21 / 60%)` | dialog scrim |
| `--stage` | `#262119` | wall and image field |
| `--stage-text` | `#F5F0E7` | text on the wall field |
| `--stage-line` | `#8F897E` | panel outlines and hatch |
| `--stage-selected` | `#FFC084` | selected panel on the wall |
| `--accent` | `#9D4616` | links, focus, selected/preview marks, hover edge |
| `--success` | `#246344` | current confirmed evidence |
| `--attention` | `#795500` | attention |
| `--error` | `#A12A24` | failure, removal |

Rust is never the resting fill of a primary/commit button. Primary and commit buttons use an ink fill (`#2D2822`) with cream text (`#F5F0E7`) at rest; hover shifts to the rust fill. Rust is for links, focus, selection and preview, not the resting commit fill. Green is only for current confirmed evidence; the gallery's applied marker is neutral ink at weight 600, not green. The logo mark uses a rust border, not an inset shadow.

Surfaces are separated by tone and spacing. Keep separators only between task groups, list rows, and control boundaries. Remove nested card borders and any decorative elevation. No gradients, glass, or new icon system. The one allowed shadow is a true floating layer (native dialog/backdrop); no other shadow.

### Type and space

- One family: Schibsted Grotesk.
- Page title 28px/600; section 20px/600; body/control 16px; meta 14px; tabular figures for millimetres and pixels.
- Spacing: 4 / 8 / 12 / 16 / 24 / 32 / 48.
- Radius: 6px. No uppercase micro-labels, decorative pills, or tracked caps.
- Surfaces use `--surface`; page uses `--bg`; selected rows use the `--selected` wash plus a 3px rust edge.

### Shell

- Header 64px desktop, 56px portrait mobile, 44px short landscape.
- Task navigation 52px desktop. On portrait mobile it becomes a fixed bottom bar, safe-area aware, 56px. Short landscape has no bottom nav and no task title; a 44px tab row remains.
- Content max 1600px, padding 32px desktop / 16px mobile.
- One task heading per panel, 28px, except Images and Arrange where the task title is visually hidden (screen-reader only) and the active tab plus the stage heading carry the task. No repeated “Shape” heading when the control labels already name the group.

## 2. Wall fit contract

This is the primary rule. The wall **bounds** — not the dark field — must fill at least 80% of the stage’s limiting dimension.

- The stage column measures its available width and the available viewport height after header, navigation, task heading, stage mode row, and a 16px bottom margin. When a preview or commit action bar is visible, subtract its measured height, gaps and safe-area inset before fitting. The height is not a fixed `44vh`, `50vh`, or `68vh`.
- The SVG viewBox uses a 10-unit outer margin, not the current 28-unit margin. The wall bounds keep their configured aspect ratio, device geometry, bezels, gaps, and empty logical regions.
- The dark `.stage-scroll` field shrink-wraps the SVG. Slack goes to the page canvas or the inspector column, never to dark side bands. The field is centered when height-limited.
- The stage fit is recalculated on window resize, tab change, inspector width change, and wall/layout update. A content-driven fallback keeps the stage usable when the viewport is short.
- At 1440/1280/1024, a width-limited wall must occupy at least 80% of the stage column width; a height-limited wall must occupy at least 80% of the available height.
- For wall aspect ratios of 2.6:1 or wider, the stage spans the full workspace width and the inspector/library sit below it. That avoids a large empty left column around a 1×4 wall.
- At viewports of 1100px or narrower, the stage always spans the full workspace width and the inspector/library sit below it. The side rail is not allowed to shrink the wall at 1024; a 1024 acceptance checks wall area/height, not only column width.
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

- Grid: `minmax(0, 1fr) 360px`, gap 24–32px. The stage starts immediately after the task heading. The 360px inspector has 16px inner padding.
- The reviewer’s desktop filmstrip is dropped. The library is a 2-up thumbnail grid in the right column under the inspector; it is sticky while the wall is height-limited. This is what preserves the wall’s height.
- The inspector is one surface: image title/dimensions, selected-image facts, Fit, Show/Restore, preview consequence, command message. It does not repeat applied content. Advanced/alternate/upload controls are disclosures at the bottom.
- Stage mode line is the **only** applied-content home:
  - `Applied configuration · Calibration pattern · 2 000 × 1 000`
  - `Applied configuration · supplied.png · Fill wall`
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
| Applied, no draft | `Applied configuration · <content> · <fit>` | “Choose an image”; no draft outline | Show disabled until a draft is created |
| Local image preview | `Image preview · not on tablets` | Preview consequence; applied content is named once in the stage mode area | Show image / Discard preview |
| Preview retained, viewing applied | `Applied configuration · <content>` | “Preview ready · viewing applied” | View preview / Show / Discard |
| Arrangement preview | `Arrangement preview · not applied` | Geometry consequence, selected screen | Apply arrangement / Discard |
| No selection | `Applied configuration · <content>` | “Choose an image” prompt, library | Show disabled |
| Conflict/stale | Mode unchanged | Rebuild/refresh message beside the action | Retry / rebuild |

- **Inspected** means the library image carries the rust outline and is the current local draft. There is no separate “selected but not previewed” state.
- The rust outline marks a retained draft. It remains when the operator uses **View applied**, and disappears after a successful **Show** or **Discard**. After Show, the applied image carries the neutral **Applied** marker but is not “inspected” unless a new draft is made.
- Loading Images does not create a draft. If no draft exists, the applied image is marked **Applied** but has no rust outline. Clicking any library image, including the applied one, creates a local draft. The inspector shows image facts only for an existing draft.
- **Applied** means server configuration only. It does not mean a tablet painted it. Applied content is named once in the stage mode area; the inspector never repeats it.
- **View applied** while a draft exists changes the stage to the applied configuration; the rust outline stays, and the inspector offers **View preview**. The draft is not lost.
- **Show** succeeds: the draft becomes applied, the rust outline disappears, the neutral Applied marker moves to that image, and the stage mode returns to Applied configuration.
- **Discard** removes the draft: the rust outline disappears and the stage returns to the applied configuration.
- **Report current image** is software evidence. The header and Issues own it; `renderShownStatus()` returns brief command feedback only (“Image applied”, “Image applied; status stale”, “Wall changed after this command”), not per-tablet paint outcomes.
- Keep the preview-is-not-tablet-output sentence once, in technical details.
- Command failures, conflict, stale-preview rebuild, unavailable-image recovery, and crop/bar consequences stay beside the action.

## 5. Status wording

- Header: `0 connected · 0/4 report current image` (transport + evidence). Mobile: `0/4`.
- Offline is derived; do not print `4 offline` as a third number.
- Tablet state text: “Reports current image” for a current image render; “Current scene reported” for non-image; “Offline · spot reserved” once.
- Placement: “Placed” / “No placement”; “Included in show” / “Excluded from show” for participation.
- The applied content is one phrase in the stage mode line. No “Currently showing”, no “This image is on the wall”, no gallery check prefix.
- Gallery: one rust outline for the inspected/preview image; one neutral-ink “Applied” text marker for server configuration. Applied text has a reserved lower row and an accessible description. Green is not used for applied configuration.
- Issues is the only paint drill-down.

## 6. Image library

- Desktop: 2-up grid under the inspector. Track width is `(column inner width − gap) / 2`, approximately 160px at the 360px rail; do not use fixed 160/180px tracks. Mobile/landscape: horizontal strip, 132px tracks, scroll-snap.
- Cards: `min-inline-size:0`, `overflow:hidden`, image `max-inline-size:100%; display:block; object-fit:cover; aspect-ratio:4/3`. Filename wraps at spaces, underscores, or arbitrary characters if necessary. Applied row is reserved so cards do not jump.
- No check prefix. Selected/preview = one 2px rust outline + `--selected` wash. Applied = neutral-ink “Applied” text at weight 600, no border.
- One visible search label and a distinct placeholder; Add image is label-width. Library cards show filename only, no dimensions. Applied dimensions live in the stage mode line; draft dimensions live in the inspector only while a draft exists.
- Thumbnail bug: the current image overflows its card; constrain both the button and its children.

## 7. Mobile

### Portrait

- Header 56px: brand, `0/4` (aria-label “0 of 4 report current image”), Issues. No connected summary.
- Fixed bottom navigation 56px + safe area; content padding-bottom accounts for it.
- Images: stage first, then a pinned action bar (Fit / Show / Discard) that appears only while a preview or draft exists, then the horizontal library strip, then details. Do not interrupt this sequence with diagnostics.
- The phone wall is full-bleed to the screen edges. Its height is the aspect-correct maximum for the wall ratio; a 1.855:1 wall at 390px width is about 200px tall. Do not crop or rotate the wall to make the phone preview taller.
- The stage height budget is `100dvh − 56px header − 56px bottom nav − safe area − 56px action bar − gaps` while a preview exists. When no preview exists, the action bar is absent and the stage may use its height.
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

- 1440×900, 1280×800, 1024×768, 390×844, 844×390: no horizontal overflow; no dark side bands; wall bounds ≥80% of the limiting stage dimension. At 1024 the full-width layout applies and the wall is checked by rendered area/height, not only column width.
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

## Implementation notes (council-accepted deviations)

- The tablet name input remains visible above the collapsed “Placement and technical details” disclosure. Naming is a first-time task; hiding it cost more than the saved height. The council accepted this deviation.
- The portrait preview action bar renders at roughly 105px, carrying Fit, Show, Discard, one feedback line and View applied above the 56px bottom navigation. It keeps 44px touch targets. The council accepted this deviation; the 1024px bar is 57px and the short-landscape bar is 45px.
- The short-landscape stage is height-limited to roughly 379×195 by the 44px header, 43px tabs and 45px action bar. It uses the full available height and preserves the wall aspect; the 80% rule is measured against the limiting dimension.
