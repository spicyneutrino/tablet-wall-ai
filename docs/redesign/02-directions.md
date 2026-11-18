# Controller redesign: three layout directions

Status: proposal for the owner to compare. Nothing in `frontend/` changed.
Date: 2026-11-15. Branch `redesign/direction-b` at `0233914`.

Inputs: `docs/frontend-migration/PROPOSAL.md`, the four reports in `docs/frontend-migration/audit/`, the critique in `01-critique.md` (S1–S10 below refer to it), and my own captures of the running console at 1440×900 and 390×844 with three of the four tablets online.

Mockups (open in a browser from this folder; each has a state bar at the bottom and accepts `?state=` and `?theme=light|dark`):

| Direction | File | States |
|---|---|---|
| A. Wall editor | `mockups/a.html` | main, selected, measure, arrange, recovery, firstrun |
| B. Guided tasks | `mockups/b.html` | same |
| C. Preview switcher | `mockups/c.html` | same |

Screenshots of every state at 1440×900 and 390×844, light and dark, are in `shots/mockups/` as `{a,b,c}-{state}-{1440|390}-{light|dark}.png`. Side-by-side sheets: `shots/mockups/compare-desktop-main.png`, `shots/mockups/compare-phone.png`.

All mockups use the same data: four tablets in a measured 2 × 2 (Pixel C, iPad Air 2, iPad mini 4, and an offline iPad mini 2), the real library image (`assets/EXLENT_Cohort_3_Flyer_Temp.png`) filled across the wall, and a non-grid "staggered" draft with one tablet turned to portrait and one tilted 6°. Panel sizes come from published specs. Bezels and the join address `10.42.0.1:8080` are illustrative.

---

## 1. What every direction has to fix

From the critique, the problems the structure itself must answer:

| Critique item | Structural answer used by all three |
|---|---|
| S1. Status said four ways, some contradictory | One status summary in the header. It is a button and opens the cause. The stage, list and header use the same colour and words for the same state (offline is always amber with a triangle and the word "Offline"). |
| S2. Selecting a tablet hides the tools | A and C: selection never removes the library or the mode's tools. B replaces the task panel by design (one task at a time); the cost of that is listed under B. |
| S3. Arrange is a 3,400 px form | Arrange shows one method at a time (grid, free placement, saved). Numeric fields live with the selected tablet, not in a list of all tablets. |
| S4. Three navigation systems | One navigation model per direction. The first-run steps disappear once the wall is set up. |
| S5. Draft and commit far apart, colours read backwards | "Preview" and "On wall" are always named in words. The commit action sits next to the preview it commits. Colours follow broadcast tally convention (green = preview, red = on air), always with the label. This is a deliberate choice; see §2.4. |
| S6. Server drawer is a junk drawer | Playback leaves the Server drawer. Clear wall moves to Arrange. Server keeps joining, diagnostics and backup. |
| S7. Measure is a technical form | Measure has one primary action per step, plain questions, and model values pre-filled. Advanced calibration fields stay behind one disclosure in the last step. |
| S8. Small screens squeeze the stage | On a phone the wall stays pinned at the top at full width. Everything else scrolls under it. |
| S9 / S10. Dead ends, inverted disclosure | Disabled controls say why. Recovery actions are buttons, not paragraphs. |

---

## 2. Shared foundation

### 2.1 Data shape

The UI is built on these shapes. They come from the audits and do not change in any direction.

```text
Wall
  applied:  Arrangement + Content          (server authority, ETag-guarded)
  preview:  Arrangement draft | Content selection | none
Arrangement = logical {width,height,placements} | physical {bounds,slots(center,nudge,mount_angle,pinned revisions)}
Content     = image + fit (Fill|Fit) + background, or a test pattern
Tablet      = id, number, name, model, online|offline|unplaced|reserved, last report, wake lock,
              measurement: none | model estimate | profile | ruler-checked calibration
Saved       = content scenes, arrangements (logical|physical), automatic restore points
Server      = joining (URL, QR, checks), diagnostics, backup evidence, experimental playlist/playback
Problems    = uncertain command | draft conflict (412) | server unreachable | tablet offline | replacement offer
```

The UI only ever shows two versions of the wall: **On wall** (applied) and **Preview** (a local draft). Every direction is a way of laying out those two plus the tablets.

### 2.2 The operator's core loop

| When | What the operator does | Frequency (inferred from the brief, not measured) |
|---|---|---|
| Daily | Glance: are all tablets showing? Pick an image or saved content, preview it, show it. Sometimes Identify a tablet or run a test pattern. | Every session |
| Setup | Add tablets (join link or QR), name them, measure each one (model, screen and bezels, optional ruler check), arrange (grid, then adjust), save the arrangement. | Once per wall, again when hardware moves |
| Something breaks | A tablet goes offline (wake it, rejoin, or replace with a new browser identity), a command is uncertain (refresh first), the wall changed underneath a draft (412: review), the server is unreachable (tablets keep their last image), diagnostics for a report. | Occasional, but it must be obvious |

Design priority follows that order: the daily loop must be short and always visible; setup can be deeper; breakage must be impossible to miss and must offer the next action.

### 2.3 Information architecture

- **Objects:** Wall, Tablets, Library (images and test patterns), Saved (content, arrangements, restore points), Server.
- **Verbs:** Show, Arrange, Measure, Test, Recover.
- **Vocabulary changes:** "Content" mode becomes **Show** (it is the verb the operator wants). "Recall geometry" becomes **Use this arrangement**. "Commit" is never shown; the button names the result: **Show on wall**, **Apply arrangement**.
- **Removed from the main surface:** ETags, revisions, mm-per-CSS-pixel, profile revisions. They stay in Server → Diagnostics and in Measure → Advanced.

### 2.4 Design tokens

One token block, identical in all three mockups (`<style>` at the top of each file). The visual world is restrained (Impeccable Operate mode): cool neutral chrome, a near-black stage that matches the physical wall, one indigo for action, selection and focus, and colour otherwise reserved for state.

**Type.** One family, Atkinson Hyperlegible Next (OFL; self-hosted in the build, loaded from Google Fonts only in the mockups). It was chosen because the operator reads tablet numbers and millimetre values, and this face separates 0/O, 1/l/I and 8/B clearly. Tabular numerals everywhere.

| Role | Size / line | Weight | Use |
|---|---|---|---|
| Title | 22 / 28 px | 700 | Panel title, selected tablet name, dialog title |
| Heading | 18 / 24 px | 700 | Section heading |
| Body | **16 / 24 px** | 400 | All running text and field values |
| Label | 14 / 20 px | 600 | Buttons, field labels, list names, tallies |
| Caption | 13 / 18 px | 400, muted | Metadata only (model name, hints) |

Steps between roles: 22→18 = 1.22, 18→16 = 1.13 plus weight, 16→14 = 1.14 plus weight. Hierarchy uses size, weight and placement, never colour alone.

**Spacing.** 4 px base: 4, 8, 12, 16, 24, 32, 48. Tight inside a group (4–8), 12–16 between fields, 24 between sections. Tailwind steps 1, 2, 3, 4, 6, 8, 12 map to it; no other values.

**Radius and size.** Controls 6 px, panels 10 px, status pills 999 px. Control height 36 px (44 px under `pointer: coarse`). Large primary action 44 px.

**Colour roles and measured contrast.** Computed with the WCAG relative-luminance formula by `mockups/src/contrast.py`. No role uses alpha, so the ratios do not depend on what is behind them.

| Pair | Light | Dark | Minimum |
|---|---:|---:|---|
| Text on surface | 18.1:1 | 14.73:1 | ≥4.5 |
| Text on page | 16.45:1 | 15.94:1 | ≥4.5 |
| Text on rail/toolbar | 15.16:1 | 13.51:1 | ≥4.5 |
| Muted on surface | 6.8:1 | 7.46:1 | ≥4.5 |
| Muted on rail | 5.7:1 | 6.84:1 | ≥4.5 |
| Muted on page | 6.18:1 | 8.07:1 | ≥4.5 |
| Primary button label | 7.85:1 | 8.09:1 | ≥4.5 |
| Primary button label, hover | 10.31:1 | 10.63:1 | ≥4.5 |
| Link / primary text | 7.85:1 | 7.47:1 | ≥4.5 |
| Selected row text | 8.48:1 | 8.82:1 | ≥4.5 |
| On wall tally on tint | 5.11:1 | 5.61:1 | ≥4.5 |
| On wall tally on surface | 5.85:1 | 6.3:1 | ≥4.5 |
| Preview tally on tint | 5.21:1 | 7.41:1 | ≥4.5 |
| Preview tally on surface | 5.93:1 | 9.1:1 | ≥4.5 |
| Warning on tint | 6.01:1 | 7.88:1 | ≥4.5 |
| Warning on surface | 6.61:1 | 9.49:1 | ≥4.5 |
| Error on tint | 5.72:1 | 6.15:1 | ≥4.5 |
| Error on surface | 6.54:1 | 6.96:1 | ≥4.5 |
| Disabled label on disabled fill | 4.65:1 | 5.44:1 | ≥4.5 (held to body even though WCAG exempts it) |
| Control border on surface (UI) | 4.11:1 | 4.15:1 | ≥3 |
| Control border on rail (UI) | 3.45:1 | 3.81:1 | ≥3 |
| Focus ring on page (UI) | 7.13:1 | 8.09:1 | ≥3 |

| Stage pair (same in both themes) | Ratio | Minimum |
|---|---:|---|
| Tablet name in label pill | 17.45:1 | ≥4.5 |
| "Offline" in label pill | 10.74:1 | ≥4.5 |
| Text on offline hatch | 11.92:1 | ≥4.5 |
| Measure dimensions on blanked screen | 8.15:1 | ≥4.5 |
| Tablet outline on stage (UI) | 4.31:1 | ≥3 |
| Screen outline on tablet body (UI) | 3.61:1 | ≥3 |
| Selection ring on stage / on body (UI) | 8.46:1 / 7.09:1 | ≥3 |
| Preview outline (UI) | 10.3:1 | ≥3 |

Light values: page `#f3f4f6`, surface `#ffffff`, rail `#e9ebef`, text `#14161b`, muted `#555b69`, control `#767d90`, primary `#3242c0`, On wall `#c4221a`, Preview `#11733b`, warning `#875000`, error `#b3261e`. Dark values and the stage set are in the token block.

**Why green for Preview.** The critique (S5) says green reads as "live/OK". I kept green for Preview because this console is a vision mixer for a wall: in broadcast switchers green is preview and red is on air, and the red/green pair already exists in today's tokens (`--tally-live`, `--draft-text`, `frontend/controller/operator-tokens.css:39-40`, dark `:77-78`). The fix for S5 is that the colour never appears without its word, and amber is no longer used for anything live. If the owner prefers, Preview can move to the indigo action colour; only one token changes. This is a preference call for the owner.

**States.**

| State | Treatment |
|---|---|
| Hover | Fill steps one surface level (`surface` → `rail`). Text colour does not change, so contrast holds. |
| Focus-visible | 2 px indigo outline, 2 px offset, on every control, including pressed and selected ones (fixes the lost ring on Fit/2x in the critique). On the stage: the same indigo ring drawn around the tablet body, distinct from dashed draft and offline strokes. |
| Selected / pressed | Tint fill (`sel-bg`) + indigo border + indigo-dark text. The border carries the 3:1 non-text contrast; the tint alone is not relied on. Segmented controls: white fill with a `control` border (3.45:1 on the track). |
| Disabled | Grey fill, readable label (4.65:1), lighter border, `not-allowed` cursor, and a reason nearby ("Pick a source to preview it."). |
| Busy | Button keeps its width, label changes to the progressive verb ("Showing…"). |
| Status | Always icon + word + colour: Showing (check), Offline (triangle, amber), Not confirmed (question, red), Preview (green square + "Preview"), On wall (red square + "On wall"). |

**Measured against the brief's rules** (computed-style walk over every visible element in all six states at 1440 and 390, `src/audit.py`; raw output `shots/mockups/audit-results.json`). Today's column is from critique §3.

| Rule | Today | Mockups (A, B, C) | Evidence |
|---|---|---|---|
| One type scale | Fail (7 sizes) | Pass | Rendered sizes 13, 14, 16, 18, 22 px only, including SVG stage text |
| 16 px body | Fail (14 px) | Pass | All running text and inputs at 16 px |
| Hierarchy by size, weight, spacing, placement | Fail (1.17 step) | Pass | Steps 1.22 / 1.13 / 1.14 plus weight 700/600/400; the impeccable detector still flags the size steps as below 1.25 (advisory) |
| Body contrast ≥ 4.5:1 | Pass, 1 exception | Pass | Token table above; axe 0 violations |
| Large text / UI ≥ 3:1 | Selected cue fails (1.19–1.58) | Pass | Selected border 3.45:1 on the track; focus ring 7.13:1 |
| Hover, focus-visible, selected, disabled | Partial (ring lost on pressed) | Pass | `shots/mockups/focus-{a,b,c}-{light,dark}.png`: keyboard focus on a selected tab, a checked choice and a pressed source; 2 px solid indigo ring in each |
| One spacing scale | Fail (5.6 px ×68, others) | Pass | Values found: 4, 8, 12, 16, 24, 32, 48 px, plus `ml-auto` (layout, not a spacing step) |

Also: `color-scheme: light dark` on `:root` with a `<meta>`, `accent-color` and `scrollbar-color` from the palette, `::selection` themed, `prefers-reduced-motion` and `forced-colors` handled. Motion is 150 ms ease-out on state changes only.

### 2.5 The wall preview is the primary constraint

- The stage element keeps the same box in every state at a given viewport. Mode, selection, drafts, alerts and dialogs never resize it. Alerts float over the letterbox or sit outside the stage. This is PROPOSAL G1 (drift ≤ 0.02).
- On a phone the stage is pinned to the top at full width (3:2 box) and never scrolls away. Checked by scrolling every scroll container to its end in all six states: the stage stays fully in view in A, B and C.
- The stage draws the real geometry: millimetre layout, the image spread across the whole wall and clipped to each screen, offline tablets hatched with an "Offline" label, the selected tablet ringed, drafts outlined in dashed green.

Measured in the mockups with Playwright (`getBoundingClientRect` of `#stage` in all six states; "wall" is the drawn tablet bounds of the 2 × 2):

| | Stage at 1440×900 | Share | Wall drawn | Stage at 390×844 | Share | Drift across 6 states |
|---|---|---:|---:|---|---:|---:|
| Today's console | 1078 × 554 | 46% | 42% (incl. empty wall area) | 356 × 183 | 20% | not measured per state |
| A. Wall editor | 768 × 700 | 41% | 28% | 358 × 260 | 28% | 0.000 |
| B. Guided tasks | 928 × 776 | 56% | 41% | 358 × 239 | 26% | 0.000 |
| C. Preview switcher | 1008 × 592 (+ 368 × 245 On wall monitor) | 46% (+7%) | 35% | 358 × 239 | 26% | 0.000 |

Light and dark gave identical boxes.

---

## 3. Direction A: Wall editor (canvas first, contextual inspector)

`mockups/a.html` · shots `a-*.png`

The model is a design tool: the wall is a canvas you select things on. A left rail lists what is on the wall, the canvas is in the middle, and a right inspector describes whatever is selected.

```text
┌ Tablet wall  [▲ 3 of 4 showing. Tablet 4 offline]                Server  ◐ ┐
├────────────┬───────────────────────────────────────────┬────────────────────┤
│[Tablets|Lib│ [Show|Arrange|Test]              ↶ ↷  Fit │ Inspector          │
│ |Saved]    │ ┌───────────────────────────────────────┐ │  nothing selected: │
│ 1 Tablet 1 │ │                                       │ │   On the wall      │
│ 2 Tablet 2 │ │              WALL CANVAS              │ │  tablet selected:  │
│ 3 Tablet 3 │ │                                       │ │   Tablet 2 + tools │
│ 4 ▲Offline │ └───────────────────────────────────────┘ │  arrange mode:     │
│ + Add      │ ■On wall Flyer, Fill ← ■Preview …  [Show] │   Arrangement      │
└────────────┴───────────────────────────────────────────┴────────────────────┘
Phone: header / pinned canvas / mode tabs / on-wall bar / tablets list / bottom nav (Wall, Library, Saved, Server); a selected tablet opens a bottom sheet.
```

**Navigation and selection.** Three modes (Show, Arrange, Test) as tabs above the canvas. Click a tablet on the canvas or in the rail to select it; Esc clears. Selecting adds a tablet section to the top of the inspector and collapses the mode panel beneath it; it never replaces the library, which lives in the left rail (answers S2).

| Feature | Where it lives |
|---|---|
| Content | Rail → Library tab; preview on canvas; Show on wall in the bar under the canvas |
| Arrange | Arrange mode: drag on canvas, keyboard nudge; inspector shows one method (grid presets, rows × columns, free placement, wall edges) |
| Measure | Inspector → Measure… → modal dialog (native `<dialog>`), 4 steps with a live diagram of the tablet |
| Test | Test mode: patterns in the inspector; per-tablet colour in the selected tablet section |
| Server | Header → Server: side sheet with Joining, Health (diagnostics), Backup. Experimental opt-in lives here; once enabled, Playlist becomes a rail tab and transport replaces the Show button in the bar |
| Recovery | Header status → selects the problem tablet; inspector shows offline guidance, replacement offer, Remove, Forget. Uncertain command: alert floating over the canvas letterbox. 412 conflict: the bar turns into "The wall changed while you edited" with Review |
| Saved | Rail → Saved tab (content and arrangements); arrangements also listed in the Arrange inspector with restore points |
| Clear wall | Arrange inspector, bottom, behind a confirmation |

**States.** First run: canvas shows a dashed empty wall and a floating "Set up your wall" card (three steps, QR, copy link); on a phone the card sits under the canvas. Empty library: the rail says what formats upload accepts, or why upload is off. Loading: dashed wall outline and "Connecting…" in the header pill. Server unreachable: header pill turns red ("Server unreachable. Tablets keep their last image."), mutating buttons disable with that reason.

**Tradeoffs.** Fastest for setup and arrangement work: direct manipulation with everything in view. Familiar to anyone who has used Figma or Keynote. But it is the most crowded: three columns take 640 px, so the drawn wall is the smallest of the three at 1440 (28% of the screen). The operator must know which mode they are in.

**Risks.** It can drift back into today's console (same skeleton plus a rail). The inspector must stay short or it becomes S3 again. The left rail could collapse to give the wall about 290 px more width; that was not mocked.

**Build cost (relative to the PROPOSAL phases).** Lowest of the three. The skeleton matches today's DOM regions (stage column, inspector rail, commit shelf), so the imperative stage, `OperatorSession` adapter and most driver flows carry over. New: left rail list (replaces the chip strip, which the ≈30 picker locators already need rewritten in phase 0), inspector sections, Measure dialog (Direction B part 1 already ships a native one, `frontend/controller/physical.html:915`). Estimate: baseline 1.0.

---

## 4. Direction B: Guided tasks (task-led, one thing at a time)

`mockups/b.html` · shots `b-*.png`

The model is a calm assistant: the wall on the left at a fixed size, and on the right one task at a time, chosen from a short list of verbs. There is no persistent inspector or mode switch.

```text
┌ Tablet wall  [▲ 3 of 4 showing. Tablet 4 offline]                Server  ◐ ┐
├───────────────────────────────────────────────┬─────────────────────────────┤
│ ┌───────────────────────────────────────────┐ │ ▲ Next: bring Tablet 4 back │
│ │                                           │ │ What do you want to do?     │
│ │                  WALL                     │ │  › Show an image            │
│ │        (same box in every task)           │ │  › Change the arrangement   │
│ │                                           │ │  › Measure a tablet         │
│ └───────────────────────────────────────────┘ │  › Test the wall            │
│ ■On wall  Flyer, Fill, on 3 of 4 tablets      │  › Add a tablet             │
│                                               │ Saved: flyer, 2×2, restore  │
│                                               │ [Back]          [Next ▸]    │
└───────────────────────────────────────────────┴─────────────────────────────┘
Phone: wall pinned on top; the task panel scrolls beneath it.
```

**Navigation and selection.** A stack: Home → task → step, with a breadcrumb and Back. Clicking a tablet on the wall opens that tablet's page (Identify, Measure, Rename, Move or turn, Something wrong?). Each step has one primary button at the bottom right. Home always leads with one "Next" card chosen from current problems or the first unfinished setup step.

| Feature | Where it lives |
|---|---|
| Content | Home → Show an image → pick (library grid) → preview on wall → Show on wall |
| Arrange | Home → Change the arrangement → choose Grid / Free placement / Saved → edit on the wall → Apply to the wall |
| Measure | Home → Measure a tablet (or tablet page → Measure). Inline in the task panel, 5 steps, one question per step; the wall dims and draws the values on the tablet being measured |
| Test | Home → Test the wall; per-tablet colour from the tablet page |
| Server | Header → Server, a task page with Joining, Health, Backup. Playlist appears as a Home task "Run a playlist" once enabled |
| Recovery | The Next card. Offline: "Bring Tablet 4 back" checklist (wake it, rejoin with QR, or use the new tablet in its place). Uncertain command: error card above everything with Refresh. 412: a review step inside the current task |
| Saved | Home → Saved list (content, arrangements, restore points); also the third choice in Change the arrangement |
| Clear wall | Change the arrangement → "Take everything off the wall" |

**States.** First run: Home becomes "Step 1 of 3: Add your first tablet" with the QR and link; later tasks are visible but disabled with the reason ("Available once a tablet joins"). Loading: wall outline and a "Connecting…" Next card. Server unreachable: the Next card explains it, and tasks that write are disabled.

**Tradeoffs.** Biggest wall at 1440 (56% of the screen, 41% drawn wall). Clearest next step and the least to read at once, which answers the owner's "unclear next step" and S4 most directly. Good for an operator who uses it rarely. But every daily action starts with a menu choice and ends with a return to Home, and experts cannot see the tablet list and the library at the same time. Measure inline (not modal) keeps the wall visible while typing millimetres.

**Risks.** Wizard fatigue for frequent use. Deep links and Back behaviour must be exact, or operators get lost in the stack. Free placement still needs the canvas direct-manipulation work of A, so B does not save the hardest part.

**Build cost.** Highest. A navigation stack with focus management and URL state, every feature re-authored as steps with new copy, and the most screens to cover with visual baselines. Most existing browser drivers assume a persistent rail and would need rewriting, not just locator changes. Estimate: about 1.5 × A (inferred from screen count: roughly 25 task steps against A's 6 panels).

---

## 5. Direction C: Preview switcher (status first, preview and on-wall side by side)

`mockups/c.html` · shots `c-*.png`

The model is a broadcast vision mixer. A large **Preview** monitor, a small **On wall** monitor, a strip of sources under the preview, and a tablet health board. Pick a source, it appears in Preview; press Show on wall, it goes to the wall.

```text
┌ Tablet wall  [▲ 3 of 4 showing. Tablet 4 offline]                Server  ◐ ┐
├───────────────────────────────────────────────┬─────────────────────────────┤
│ ■Preview  Same as the wall        [Edit layout]│ ■On wall  Flyer, Fill       │
│ ┌───────────────────────────────────────────┐ │ ┌─────────────────────────┐ │
│ │                                           │ │ │   small applied wall    │ │
│ │              PREVIEW (draft)              │ │ └─────────────────────────┘ │
│ │                                           │ │ Tablets   3 of 4 showing    │
│ └───────────────────────────────────────────┘ │ 1 Tablet 1   ✓ Showing      │
│ [Images|Saved|Layouts|Tests]  ▢ ▢ ▢ ▢ │ [Show  │ 2 Tablet 2   ✓ Showing      │
│                                        │ on wall]│ 4 Tablet 4   ▲ Offline 12m │
└───────────────────────────────────────────────┴─────────────────────────────┘
Phone: Preview pinned on top, sources and Show on wall under it, an "On wall … View" line, then the tablet board.
```

**Navigation and selection.** No modes. What you edit follows from the source you pick: images and saved content change Preview's content; layouts change Preview's arrangement; "Edit layout" turns on dragging in Preview. Click a board row or a tablet in Preview to drill into that tablet in the right column (Back returns to the board). The sources strip and Show button never leave the screen, so selection cannot hide them (S2).

| Feature | Where it lives |
|---|---|
| Content | Sources → Images or Saved → click → Preview → Show on wall (2 clicks) |
| Arrange | Sources → Layouts (saved arrangements, restore points, New grid…) or Edit layout on the Preview; Apply layout replaces Show on wall in the same spot. Preview and On wall show the old and new arrangements side by side |
| Measure | Tablet row → Measure: a vertical stepper in the right column; the Preview draws the values on that tablet. The On wall monitor shrinks to one line during Measure |
| Test | Sources → Tests (patterns, per-tablet colours) |
| Server | Header → Server drawer (Joining, Health, Backup). Playlist becomes a Sources tab when enabled, and its transport takes the Show button's slot while playing |
| Recovery | Board rows carry state; the offline row expands with actions (use the new tablet here, join code, remove). Uncertain command: the On wall monitor shows "Not confirmed" with Refresh, because the operator no longer knows what is on the wall. 412 conflict: Preview keeps your draft, On wall shows the newer wall, and a banner offers Keep mine / Use theirs |
| Saved | Sources → Saved (content) and Layouts (arrangements, restore points) |
| Clear wall | Sources → Layouts → "Empty wall", applied like any layout, with confirmation |

**States.** First run: Preview shows the empty wall with "No tablets on the wall yet"; the board becomes "Add tablets" with QR and link. Loading: both monitors show the dashed outline, board rows as skeletons. Server unreachable: On wall monitor shows "Server unreachable. Tablets keep their last image." and Show on wall disables with that reason.

**Tradeoffs.** Shortest daily loop (2 clicks to change the image, and the result is checked against the On wall monitor without toggling). Health is always visible. The preview/on-wall split answers S1 and S5 head-on, and the strip is the "image strip under the wall" that Direction B part 2 wanted, with a fixed height in every state so it satisfies G1. The cost is a second, small stage, and the preview is shorter than B's (592 px tall at 1440). Setup work (Measure) is less roomy than A's dialog.

**Risks.** Two walls on screen could confuse a first-time user about which one is real; the labels and tally colours must be unmissable. The On wall monitor needs a second read-only stage instance driven by the applied snapshot; the audit notes `stageView()` already chooses `base` for "View applied", but during a draft conflict `base` can be the retained baseline, not the newest server layout (controller audit §2). That must be settled before C is built. On a phone the On wall monitor is one line with a View button, so the side-by-side benefit is desktop only.

**Build cost.** Between A and B, about 1.2 × A (inferred). Reuses the imperative stage twice (one interactive, one read-only), a source strip (a bounded island, like the gallery island in PROPOSAL phase 4a), a board table, and drill-in panels. Drivers change more than A because there are no mode tabs, but the stage, session adapter and commit guards carry over.

---

## 6. Comparison

| | A. Wall editor | B. Guided tasks | C. Preview switcher |
|---|---|---|---|
| Structure | Rail + canvas + inspector, modes | Wall + one task panel, stack | Preview + sources + On wall + board, no modes |
| Stage share at 1440 / 390 | 41% / 28% | **56%** / 26% | 46% (+7% On wall) / 26% |
| Drawn wall share at 1440 | 28% | **41%** | 35% |
| Stage drift across 6 states | 0.000 | 0.000 | 0.000 |
| Controls in view at 1440, main state (today: 33) | 18 | **12** | 17 |
| Tool column overflow at 1440, any state (today: 3,441 px with Arrange expanded) | 0 px | 0 px | 0–10 px |
| Change the image (clicks from main) | 3 (Library tab, image, Show) | 3 (task, image, Show) + back | **2** (image, Show) |
| See tablet health without clicking | Rail list | Only the Next card | **Board, always** |
| Measure a tablet | 2 to open, modal dialog, roomiest | 2 to open, inline, one question per step | 2 to open, stepper in side column |
| Arrange (non-grid) | **Best**: canvas tools + inspector | Method choice, then canvas | Edit layout on Preview; old and new side by side |
| Compare draft with wall | Bar text only | Caption text only | **Two monitors** |
| First-time clarity | Medium | **High** | Medium |
| Breakage visibility | Header pill → inspector | **Next card** | Board row + On wall monitor |
| Critique items answered best | S2, S3 | S4, S7, S9 | S1, S2, S5, S6 |
| Build cost (relative) | **1.0** | ~1.5 | ~1.2 |
| Main risk | Crowding; drifting back to today | Slow for daily use; stack navigation | Two walls confuse; applied-snapshot source during conflicts |

Click counts and control counts are from the mockups (control count = enabled buttons, links, inputs and tabbable rows inside the viewport). Build-cost ratios are estimates, not measurements.

axe-core 4.10.2 (WCAG 2.0/2.1/2.2 A and AA tags), 72 runs (3 directions × 6 states × 2 widths × 2 themes): **0 violations** after fixes. 2,642 text nodes passed colour contrast. 500 nodes came back "incomplete": 492 are SVG stage labels (axe cannot compute contrast for SVG text over SVG shapes) and 8 are text in callouts floating over the stage. Their colour pairs are in the token tables above and all pass. Raw output: `shots/mockups/axe-results.json`. Two violations found on the first run were fixed: `aria-selected` on `role="radio"` buttons, and a scrollable stepper that was not focusable.

---

## 7. Recommendation

**Build C, the Preview switcher, and take two pieces from the others:** A's canvas editing and keyboard nudge inside C's "Edit layout", and B's single "Next" card for first run and breakage, placed at the top of C's board.

Against the owner's own complaints: long scrolling (no tool column scrolls at 1440 in any state; the phone stage stays pinned), too many controls at once (17 in view against today's 33; only B has fewer), unclear next step (one primary action beside the preview; the Next card from B covers setup and problems), weak hierarchy (one scale, measured above). If the board still feels busy, it can collapse to problem rows only when every tablet is fine.

Reasons, in order of weight:

1. **The daily loop is the most frequent thing the operator does, and C makes it shortest and safest.** Two clicks to change the image, with the result checked against a live On wall view. Today's biggest confusion (S1, S5) is about what is on the wall versus what is a draft. C makes that the layout itself, not a label.
2. **Breakage is visible without asking.** The board is always on screen, and an uncertain command shows as "Not confirmed" exactly where the operator looks to see what is on the wall.
3. **The wall stays stable and large.** Zero drift across every state, a 46% preview at 1440 (the same share of the screen as today's stage), plus a second view of the applied wall. B's wall is bigger, but B pays for it with a slower daily loop.
4. **It fits the migration plan.** The sources strip is the Direction B part 2 strip, with its height reserved in every state as G1 requires. The stage stays imperative (controller audit §4). Cost is moderate: about 1.2 × A by my estimate.

Choose **A** instead if most of the owner's time goes into arranging and measuring rather than showing content; it is the cheapest to build. Choose **B** only if the console will be run by occasional, non-technical operators.

Before building C, decide: (1) which snapshot the On wall monitor draws during a 412 conflict (newest server layout, not the retained `base`); (2) whether Preview stays green or moves to indigo; (3) whether the phone needs the On wall monitor as a full toggle rather than one line.

---

## 8. Verification and limits

- Screenshots: every state at 1440×900 and 390×844, light and dark (72 files). I inspected each direction's main, selected, measure, arrange, recovery and first-run shots and fixed what was wrong: states bleeding together (Tailwind `display` beat `[hidden]`), a phone commit bar where two labels overlapped, alerts and the first-run card covering the whole phone stage, a stage that grew in C's phone Arrange state, glyph checkmarks replaced with Lucide icons, disabled text raised from 2.75:1 to 4.65:1, the phone stage in A and C made sticky after a scroll test showed it scrolling away, and off-scale spacing (20, 6, 10, 36, 40 px) and SVG label sizes (9, 11, 12 user units) brought onto the scales.
- `impeccable detect` on the three files: its one real finding (a disabled primary button took the hover fill, 1.7:1 in dark) is fixed. Remaining: `cramped-padding` on `.divider`, `.panel` and the step dots, which are static-scan false positives (the rendered shots show 8–24 px insets from Tailwind classes the scanner does not evaluate), and an advisory `flat-type-hierarchy` (largest step 1.22:1). The tighter ratio is deliberate for an operating tool; weight and placement carry the rest.
- Sources and checks are in `mockups/src/`: `head.html` (the shared token block), `stage.js` (shared data and wall renderer), `{a,b,c}.body.html`, `build.py` (assembles the three self-contained files), `shots.py` (screenshots and stage boxes), `axe.py`, `contrast.py`, `audit.py` (type, spacing, control count, phone scroll), `focus.py`. Run them with `PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright uv run --group browser python docs/redesign/mockups/src/<script>.py` from the repo root (`shots.py` takes `a,b,c <out-dir> [states] [themes]`; `axe.py` takes `a,b,c`).
- Mockups load Tailwind (cdn.tailwindcss.com 3.4.16), Lucide 0.469.0 (unpkg) and the font from Google Fonts. The real build must self-host all of them (PROPOSAL rule 4: offline-safe delivery). The CDN scripts have no SRI hashes; they are throwaway mockups.
- Not drawn, only described: loading, server unreachable, 412 conflict review, the Server sheet, playlist and playback, the library grid and upload, the ruler-check step. Phone sheet behaviour is drawn for A only.
- The mockups are static. Drag, keyboard nudge and focus order were not prototyped.
- Today's stage numbers come from the live console on port 8012 with three tablets online; its "wall drawn" figure includes empty wall area, so it is not directly comparable with the mockups' tablet bounds.
- `audit.py` also counts controls on today's console at port 8012, which needs that server running.
- I inferred the operator's frequency of tasks from the brief and the critique; I did not observe a real operator.
