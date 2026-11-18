# Controller critique and accessibility audit (current console)

Input to the from-scratch controller redesign. Read-only review of `frontend/controller/physical.html` on branch `redesign/direction-b` (commit `0233914`), 2026-11-15.

## Method

- Server: a private copy of the scratchpad `inspect.db` on port 8013, with four headless tablet clients online. A second run used `TABLET_WALL_TABLET_ORIGIN` so the join QR rendered. A fresh, empty DB on port 8014 was used for first run. The shared 8012 server was not touched.
- Browser: Chromium through `agent-browser` at 1440×900, 820×1180 and 390×844, light and dark. Screenshots are in `shots/current/` (`d` = desktop, `t` = 820 tablet width, `p` = 390 phone).
- axe-core: the embedded engine in `agent-browser a11y`, run on 9 states: Content, tablet selected, Arrange, Test, Server drawer, Measure dialog, tablet offline, first run, and dark theme.
- Computed styles: a script walked every visible element and collected font sizes and weights, margin, padding and gap values, and text contrast against the composited background. Token contrast was computed from `operator-tokens.css`.
- Keyboard focus: tabbed through the page on the shared 8012 server (read-only) and read the computed outline of each focused control (d31).
- Also ran `impeccable detect --json frontend/controller/physical.html`.
- Not covered: a real upload, because uploads are disabled unless the server is launched with `--operator-uploads` (d29). Physical (measured) arrangement editing on a saved measured profile (the slot editor with nudge and mount angle, `physical.html:540-600`). The return point after a recall. The loading state, which lasts less than one frame on localhost.
- The impeccable critique normally runs two isolated sub-agents. This was a single-context run because I was already running as a delegated agent.

## 1. Task inventory

"Clicks" means clicks from the default Content view with nothing selected, at 1440×900. "Scroll" means the control is below the fold of the 856px rail.

| Task / control group | Where it lives today | Clicks / scroll | Shot |
|---|---|---|---|
| **Discovery: add a tablet (join URL, QR, copy)** | `+` chip in toolbar → popover; QR is inside a collapsed "Joining details" disclosure. On first run, the same card is centred on the stage. Server drawer → Add a tablet (duplicate). | 2 (`+`, Joining details) | d22, d24 |
| First wall setup | Steps strip: Add tablets → **Arrange wall** → Preview → **Apply arrangement** → Choose image → thumbnail → **Show image** | 6 | d25–d27 |
| Select a tablet | Roster chip in toolbar, or click it on the stage. **Replaces the right-rail tools** with the tablet sheet ("‹ Library" back link). | 1 | d02 |
| Rename tablet | Tablet sheet → Tablet name → Save name | 3 | d02 |
| Identify tablet | Tablet sheet; also per row in Arrange → Order and mounting | 2 | d02 |
| Retry image / Reconnect | Tablet sheet → "Retry or reconnect" disclosure | 3 | d03 |
| Remove from wall / forget / replace (rebind) | Tablet sheet → "Remove or replace" disclosure; replacement offer appears separately (`physical.html:495`, `:638`) | 3+ | d14 bg |
| **Move** | Arrange tab, drag on stage, then Apply in commit shelf. Numeric: select → X/Y fields (`physical.html` tablet sheet) | 3 | d07 |
| Nudge (keyboard / 1 mm buttons, physical) | Arrow keys on stage; `btn-nudge-*` buttons in physical slot editor (`physical.html:573-579`) | 2+ | — |
| **Resize** | 12 px handle at tablet corner (d06), or W/H fields in tablet sheet, or W/H in Order and mounting rows | 2–3 | d06 |
| **Rotate** | Tablet sheet → Rotate 90°, at y≈872 of 900 (bottom edge). Physical: arbitrary mount angle in slot editor | 2 + scroll | d06 |
| **Bezels** | Logical: 4 fields in tablet sheet. Physical: Measure → Size and bezels (mm). The same concept appears in two places with two units. | 2–4 | d06, d14-profile |
| Grid presets / rows × columns | Arrange → Wall shape (2×2, 1×4, rows, cols) → Preview → Apply | 3–4 | d04 |
| Relative vs Measured sizing | Arrange → Sizing select (`physical.html:286`) | 2 | d04 |
| Order, participation, mounting | Arrange → "Order and mounting" disclosure → per-tablet checkbox, W/H, Move earlier/later | 3 + scroll | d05 |
| Orientation, wall bounds, gap, padding, trailing holes | Arrange → Advanced → Grid bounds | 3 + scroll | d05 |
| Fixed/custom bounds, snap, pack, tile | Arrange → Advanced → Wall bounds and packing / Tile or pack tablets | 4 + scroll | d05 |
| Undo / redo arrangement | Toolbar arrows (disabled until a draft exists) | 1 | d07 |
| **Saved arrangements** (save, recall, delete) | Bottom of the Arrange pane, under three disclosures. Recall is labelled "Recall geometry". | 3 | d28 |
| Return point (cross-kind) | `#return-point`, appears only after a recall (`physical.html:444`) | — | not reached |
| **Content: library, search, choose image** | Content tab rail → thumbnail → preview on stage → Show image | 2 | d08 |
| **Cropping** | Scaling select (Fill/Fit) in commit shelf; "33.3% cropped" readout. No pan/position crop exists; crop bars in Wall details (`physical.html:216`). | 2 | d08 |
| Upload | Add → "Upload" disclosure; disabled by launch flag, but the Add button stays active (dead end) | 2 | d29 |
| Saved content (save/recall) | Content rail bottom → Name → Save content | 2 | d01 |
| Wall details (revision, ETag, crop bars, identities) | Content rail → "Wall details" disclosure | 2 | d01 |
| **Test patterns** (tablet colours, calibration grid, wall grid, black) | Test tab → button | 2 | d12 |
| Per-tablet test colour / read colour | Test tab → select tablet → colour → Apply to tablet. Selecting a tablet replaces the Test pane with the tablet sheet (d14 background shows "‹ Test patterns"), so the colour control and the selection are not visible together (inferred from the back-link; not exercised end to end). | 4+ | d12 |
| **Measure: model** | Select → Measure… → Model step → Confirm model choice | 4 | d14-1 |
| Measure: profile / bezels (mm) | Measure → Size and bezels → Save profile | 5 | d14-profile |
| **Ruler calibration** | Measure → Ruler check → Use tablet viewport → enter mm/spans → Save calibration | 6+ + scroll | d14-ruler |
| Advanced calibration (quarter turn, anchor, offsets, mm/px) | Measure → Advanced | 5 + scroll | d14-advanced |
| **Recovery when a tablet goes offline** | Header exception chip "Tablet 2 offline" → tablet sheet with guidance; roster chip turns red; stage tile shows "▲ Offline" | 1 | d16, d17 |
| **Reconnection (tablet)** | Automatic. Offline was shown within 3 s of the client closing (d15). Chip and header were back to normal within 5 s of it reopening (d18). | 0 | d15, d18 |
| Server unreachable | Header turns red "Server unreachable · tablets keep their last image"; all chips "Stale". Recovery is automatic. | 0 | d20, d21 |
| Server: joining checks, diagnostics, verify files, download report | Server drawer (2550 px tall when expanded) | 2–3 + scroll | d09, d10 |
| Backup and restore evidence | Server drawer → Backup and restore disclosure | 3 + scroll | d10 |
| **Playlist and playback** (start/pause/stop/next/prev, loop, dwell, exclusions, policy) | Server drawer → scroll → **Enable playlist and playback** checkbox → scroll to Playlist and Playback cards. Start stays disabled until a saved *physical* layout exists; the reason is shown as red error text (d11). | 4+ + 2 scrolls | d10, d11 |
| Clear wall (destructive) | Bottom of Server drawer, under the experimental playback block | 3 + scroll | d10 |
| Theme | Toolbar icon toggle (system → light → dark) | 1 | d30 |
| Zoom (Fit / 2x) | Toolbar | 1 | — |
| Tablets list and wall issues | Phone bottom-nav "Tablets" only (`physical.html:667`). No desktop entry point was found. | 1 (phone) | p02 |
| Logical compatibility editor | Separate page `experimental.html`, linked from playlist help text | — | — |

Cross-check against `docs/frontend-migration/audit/01-controller-audit.md` §1 and PROPOSAL §2: every arrangement operation listed there has a UI home above, with one exception. The legacy `/wall/auto` and `/wall/pack` are called only by the older logical editor (`controller.js:2535`, `:2602`), so they are reachable from `experimental.html`, not from this console. Session exclusions live in the playback block. Reservations show as offline chips. Two items were not exercised in the browser: rebind and the return point.

## 2. Structural UX problems (ranked)

### S1. Status surfaces contradict each other (feedback, critical)
- The header calls whatever is on the wall "the current image", including the calibration pattern. It shows "● 4 of 4 showing the current image" in green. On the same screen, the stage says "Test pattern", the commit shelf says "Test pattern on the wall", and step 3 says "No image shown yet" (d01).
- With the server's joining check failing ("Tablet joining is unavailable…"), the header stays green (d09).
- The header status is a `<p id="btn-wall-health">` (`physical.html:22`). It looks like a status pill but you cannot click it to see why. The real issue control is a separate chip that appears only for some issues (d16).
- The roster shows an offline tablet as a red chip, while the stage shows it as an amber "▲ Offline" (d16). The same state has two colours.
- The commit-shelf region's accessible name follows the content type, not its purpose. It is "Calibration grid" or "Tablet colours" even while it holds an arrangement draft (`operator-content.js:441`; axe snapshot during d27).

### S2. One rail, three jobs: selection hijacks the tools (selection model, critical)
- The right rail holds the mode tools (Library / Wall shape / Test patterns). Selecting any tablet replaces them with the tablet sheet. The way back is a back-link named after the hidden pane: "‹ Library", "‹ Wall shape", "‹ Test patterns" (d02, d06, d14).
- In Content mode, selecting a tablet hides the library. In Test mode, "Apply to tablet" needs a selection, but making the selection hides that control (d12 → d14 background).
- Selection on the stage is a faint 2 px inner highlight (d02). The roster chip ring is the only strong selection cue, and it is far from the stage.
- At 820 and 390 widths, the tablet sheet opens below the fold of a fixed stage, so a selection changes content the operator cannot see (t02, p03).

### S3. Arrange is a 3,400 px settings form (density and progressive disclosure, high)
- In its default state the Arrange pane shows Wall shape plus four collapsed disclosures. Fully expanded it is **3,441 px tall with 64 controls and 11 disclosures**, nested three deep (Advanced → Grid bounds / Wall bounds and packing / Tile or pack) (d05).
- Tablet size can be edited in **three places in two units**: the Order-and-mounting rows (relative W/H), the tablet sheet (X/Y/W/H/bezels), and Measure → Size and bezels (mm) (d05, d06, d14-profile).
- Saved arrangements sit at the bottom of this pane, under the disclosures (d04, d28). Recall is labelled "Recall geometry", and every row repeats "Relative geometry · 4 tablets · Recall restores geometry only".
- Rotate 90° sits at the bottom edge of the rail at 900 px (d06). The resize handle is a 12 px square (d06).
- Dragging lets tablets overlap with no warning (d07).

### S4. Three overlapping navigation and progress systems (navigation model, high)
- Mode tabs (Content / Arrange / Test), the first-wall steps strip (Add tablets / Arrange / Show), and the commit shelf all describe "what to do next". The steps strip never goes away. After setup it still takes about 57 px and keeps a permanent "Choose image" call to action (d01, d28).
- The steps' "Arrange wall" switches the tab but does not preview. The operator still needs Preview, then Apply in the shelf, which is in a different region (d26 → d27).
- Phone adds a fourth nav item, "Tablets", that has no desktop equivalent (p02 vs d01).

### S5. Draft and commit are split across the screen and colour-coded backwards (feedback, high)
- Draft controls live in the right rail. Apply/Discard live in the bottom shelf, about 1,000 px away diagonally (d07).
- A draft gets a **green** border and green "preview · not applied" text. The live test pattern gets an **amber** border (d07, d01). Green usually means live or OK. Here it means "not yet sent".
- The "On wall" toggle in the stage corner is the only way to compare the draft with the applied state, and it has no label explaining what it does (d07).

### S6. The Server drawer is a junk drawer (information architecture, high)
- It holds joining, diagnostics (about 30 key/value rows), backup evidence, the experimental playlist and playback, and Clear wall. Expanded, it is 2,550 px (d10).
- Playback is an operating task, not a setting. It is reached through a settings checkbox and two scrolls. The destructive Clear wall sits below it.
- "Add a tablet" appears both here and in the toolbar popover.

### S7. Measure is a technical form wearing a wizard (progressive disclosure, medium)
- 4 steps and **54 controls**. Each step has three equal-weight buttons, for example Confirm model choice / Compare current saved model / Discard model choice, with no primary action (d14-1, d14-profile).
- The Ruler step opens with four paragraphs of instructions (d14-ruler). Advanced exposes internals such as Profile revision, mm per CSS pixel and Anchor edge (d14-advanced).
- On the phone, the step labels collapse to bare numbers 1–4 (p04).
- The close control is a plain letter "X".

### S8. Small viewports squeeze the work area to a slot (responsive layout, medium)
- At 820×1180 the stage, steps and shelf are fixed and take about 765 px. The tool rail gets about 410 px, and the selected tablet's position fields are off-screen (t03).
- At 390×844 the rail gets about 290 px above the bottom nav (p05). Phone touch targets are fine: 61 of 65 targets are at least 44 px.
- The Library thumbnail stretches to 388 px wide with black letterbox bars at 820 (t01).

### S9. Dead ends and missing state (feedback, medium)
- With uploads disabled, Add stays an active button and opens a paragraph telling you to relaunch the server (d29).
- With the server unreachable, Search, Add and Save content look enabled in the screenshot (d20). This is a visual check; the `disabled` attribute was not read.
- The Add-tablet popover shows the same "No tablet address is configured" sentence twice, once in amber and once in body text (d13).
- Test patterns has no pressed or selected state for the pattern currently on the wall (d12).
- Offline reservations render as "— - Offline Original" and "— - Offline": a dash glyph, a dash, a status, then the name (d01).

### S10. Disclosure priorities are inverted (medium)
- The tablet sheet hides Retry and Reconnect behind a disclosure, but repeats the wake-lock paragraph twice, under Details and under Placement and measurements (d03).
- Recovery guidance for an offline tablet is good (d17): what the server knew, what to do at the tablet, and what the server cannot do. But it is muted 13 px prose, and the actions sit below it.

Strengths worth keeping: the stage-first layout, automatic reconnection with honest stale labels (d20, d21), the first-run join card (d24), the clear offline guidance copy (d17), real undo/redo, and the dark stage, which matches the physical wall.

## 3. Measured visual system

### Rules table: pass/fail

| Rule | Result | Evidence |
|---|---|---|
| One type scale | **Fail** | 7 rendered sizes (10, 12, 13, 14, 16, 17, 17.6), plus `1.125rem` in source |
| 16px body | **Fail** | Body renders at 14px; one visible element is 16px |
| Hierarchy by size, weight, spacing, placement | **Fail** | Section headings are 14px/600, the same size as body; the detector reports a flat hierarchy (1.17:1 largest step) |
| Body contrast ≥ 4.5:1 | **Pass, one exception** | text 17.77, muted 5.27; `#stage-key` 3.25; muted on hover 4.42 |
| Large text ≥ 3:1 | n/a | No text at ≥ 24px or ≥ 18.66px bold, except the stage labels at 17.05 |
| Hover / focus-visible / selected / disabled | **Partial** | Focus is lost on pressed Fit/2x; the selected cue is under 3:1; Test patterns have no selected state |
| One spacing scale | **Fail** | 5.6px is used 68×, plus 2, 3, 4.16, 4.8, 8.8, 9.6 and 12.8px |

### Type (computed, visible elements with own text)

| Size | Content view | Arrange expanded | Source |
|---|---:|---:|---|
| 10px | 6 | 6 | `.625rem` roster glyph (`operator-workspace.css:98`) |
| 12px | 22 | 11 | `--text-sm` |
| 13px | 20 | 50 | `--text-label` |
| 14px | 31 | 54 | `--text-md` (the de facto body) |
| 16px | 1 | 1 | `--text-lg` |
| 17px / 17.6px | 3 | 3 | ad hoc `1.0625rem` brand, `1.1rem` undo/redo (`operator-workspace.css:37,114`) |
| 18px | — | — | ad hoc `1.125rem` tablet name (`:360`) |

- Body text is 14px, not 16px. Only one visible element renders at 16px. Section headings ("Library", "Wall shape") are 14px/600, the same size as body text, so hierarchy rests on weight alone. The h1 is 17px. Sizes 12 and 13 are 1px apart.
- Weights in use: 400, 500, 600, 700. Line heights are fractional (`--lead: 1.428571`, giving 18.57 and 22.86px).

### Spacing (computed margin, padding and gap)
- Token scale: 4 / 8 / 12 / 16 / 24 / 32 (`operator-tokens.css`). Values in use outside it: 2, 3, 4.16, 4.8, **5.6 (68 uses in Arrange)**, 6, 8.8, 9.6 and 12.8px. They come from rem literals such as `.35rem`, `.26rem`, `.3rem`, `.55rem`, `.6rem` and `.8rem` in `operator-workspace.css`, which uses about 30 off-token literals.
- The rule "one token scale, no arbitrary margins" fails.

### Contrast (WCAG 2.2; token pairs and computed elements)

| Pair | Light | Dark | Use |
|---|---:|---:|---|
| text on surface | 17.77 | 14.71 | body |
| muted on surface | 5.27 | 6.91 | captions, hints, summaries, labels |
| muted on bg (#f5f5f3) | 4.83 | 7.46 | toolbar and segmented control |
| muted on hover | **4.42** ✗ | 5.59 | hovered muted text |
| muted on disabled-bg | **4.22** ✗ | 5.59 | disabled buttons (exempt, but hard to read) |
| stage-line #84909e on surface | **3.25** ✗ | 5.26 | `#stage-key` "4 tablets cover 46% of the wall" (12px) |
| attention on surface | 5.86 | 9.12 | warnings |
| error on surface | 6.57 | 6.71 | errors |
| draft-text on surface | 5.60 | 8.61 | draft labels |
| selected tab / pressed zoom: ring `#cecaca` on track `#ebebe8` | 1.32 | — | the selected cue is a white fill on `#ebebe8` (1.19:1) plus this ring; both are under 3:1 |

Body, label and caption text pass 4.5:1 at rest. One measured text failure: `#stage-key` at 3.25:1. Muted text on hover falls below 4.5:1.

### State styling gaps
- **Selected:** mode tabs and Fit/2x use a white-on-grey fill (1.19:1) with a 1px ring (1.58:1). This is weak and does not meet the 3:1 non-text contrast rule (WCAG 1.4.11). Stage selection is a thin inner stroke. Test patterns have no selected state.
- **Focus-visible** (d31, computed on the focused element):
  - Mode tab, roster chip and summary: 2px `#17181a` outline. Visible.
  - Stage tile: a dashed `#edeef0` stroke (3/2) replaces the outline. It is visible on black, but it looks like the dashed draft and offline strokes.
  - **Fit/2x pressed button: the focus ring is lost.** `.stage-view-zoom .btn[aria-pressed="true"] { outline: 1px solid var(--border-strong) }` (`operator-workspace.css:112`) overrides the global `:focus-visible` rule (`:13`). The focused button shows a 1px `#cecaca` line, which is 1.32:1 against the track.
  - Focus order: 31 stops per loop. Six roster chips and four stage tiles come before the rail. Only the selected mode tab is in the order (roving).
- **Hover:** about 10 rules. Hover on summaries changes only colour (`:252`).
- **Disabled:** grey fill with muted text, 4.22:1. Server-down does not disable mutating controls (S9).
- **Status colour:** offline is red in the roster and amber on the stage. Draft is green. Live test pattern is amber (S1, S5).

### Impeccable detector (`physical.html`, static scan)
- `flat-type-hierarchy` ×1: body 12px, h3 14px, h2 16px. The largest adjacent step is 1.17:1, below the 1.25:1 target. This matches the measured scale.
- `cramped-padding` ×3: `rail-tabs`, `setup-strip` and the Clear-wall `destructive-area` have children flush against their border or background.
- `broken-image` ×2: `<img>` without a `src`. This is a false positive; the thumbnail placeholders get their `src` from JS.

### axe-core results

| State | Violations (rule × nodes) | Incomplete |
|---|---|---|
| Content | heading-order ×1, landmark-unique ×1, region ×1 | color-contrast 11, aria-prohibited-attr 2, aria-valid-attr-value 1 |
| Tablet selected | same 3 | same |
| Arrange | same 3 | color-contrast 10, … |
| Test | same 3 | same |
| Tablet offline | same 3 | — |
| Dark theme | same 3 | — |
| First run (fresh DB) | heading-order ×1, region ×1 | — |
| Server drawer open | 0 | 0 |
| Measure dialog | 0 | color-contrast 3 |

All violations are moderate:
- `heading-order`: `#first-wall-title` is an `h3` directly under the `h1` (`physical.html:87`).
- `landmark-unique`: two regions are both named "Wall": `.stage-column` (`physical.html:63`) and the stage section.
- `region`: `<div class="sr-only" aria-label="Status">` sits outside any landmark (`physical.html:906`).

The incomplete items include `aria-label` on a `<p>` and a `<div>` with no role (`#btn-wall-health`, the Status div), and `aria-controls="server-drawer"` on a closed `<dialog>`. axe could not resolve the contrast of SVG stage labels or of glyph-only marks. My own computed check covers those: stage labels are 17.05:1.

## Screenshots

All are in `docs/redesign/shots/current/`:
- **Desktop:** d31 focus states (composite), d01 home, d02/d03 selection, d04–d07 Arrange, d08 content preview, d09–d11 Server/playback, d12 Test, d13/d22 add tablet, d14-* Measure, d15–d18 offline and reconnect, d19–d21 server down and back, d24–d27 first run, d28 saved arrangements, d29 upload disabled, d30 dark.
- **820 width:** t01–t03.
- **390 width:** p01–p05.
