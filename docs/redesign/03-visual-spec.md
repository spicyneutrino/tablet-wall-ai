# Controller visual spec (Direction C, final)

Status: final visual design for the React build. Date: 2026-11-15.

Inputs: `01-critique.md`, `02-directions.md` (foundation and Direction C), and the owner's decision and feedback in the redesign brief. There is no `PRODUCT.md` in the repo, so the visual direction comes from the brief and those two documents, not from a product interview.

| What | Where |
|---|---|
| Mockup, all states (`?state=…&theme=light\|dark`; switcher bottom right; in the Server states press Esc to close the sheet before switching) | `docs/redesign/mockups/final.html` |
| Token file, the single source to port | `docs/redesign/mockups/src/tokens.css` |
| Mockup sources | `mockups/src/final.head.html`, `final.body.html`, `stage-final.js`; built by `build.py final` |
| Checks | `mockups/src/contrast_final.py` (token pairs), `audit_final.py` (axe and a rendered contrast walk), `shots_final.py` (screenshots and stage box) |
| Screenshots | `docs/redesign/shots/final/{state}-{1440\|390}-{light\|dark}.png` (72 files) |
| Contact sheets | `shots/final/contact-desktop-light.png`, `shots/final/contact-phone-dark.png` |
| Before and after | `shots/final/before-after-{main,offline,arrange}-1440-light.png`, `before-after-main-390-light.png` |
| Raw audit output | `shots/final/audit.json`, `shots/final/stage-boxes.json` |

`c.html` was not rebuilt. `head.html` and `stage.js` are unchanged, so a, b and c still build as before.

Run the checks from the repo root:

```sh
python3 docs/redesign/mockups/src/build.py final
python3 docs/redesign/mockups/src/contrast_final.py          # add --md for the table in the appendix
PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright uv run --group browser python docs/redesign/mockups/src/shots_final.py docs/redesign/shots/final
PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright uv run --group browser python docs/redesign/mockups/src/audit_final.py
```

---

## 1. The boxed-feel complaint: before and after

The owner said: "lots of UI elements with outline adds a boxed feel, all UI elements have a border and are just put together. Doesn't give a fluent visual experience."

In `c.html` almost every region and control drew its own 1 px line, so the screen read as tiles glued together. Today's mockup has these lines:

| Element in c.html | Line it drew | Final treatment |
|---|---|---|
| Header | `border-b` under the bar | No line. The header sits on the page tone (`--bg`), and the work area starts below it with space. |
| Right column | `border-l` full height, plus `border-b` between On wall and the board | One raised surface (`--surface`, `--radius-sheet`, `--shadow-raised`) inset 16 px from the window. Sections inside are separated by 24 px of space. |
| Source strip | `.panel` box with a border, plus `border-l` before the Take column | No container. Tabs, thumbnails and the Show on wall button sit directly on the page under the preview. |
| Source type switch | Segmented control with a bordered selected segment | Text tabs. The selected tab gets a 2 px `--primary` bar (7:1). |
| Thumbnails | 1 px border on every thumbnail plus a border on the selected one | No border at rest. The selected thumbnail gets a 2 px `--primary` ring with a 2 px gap. Hover lifts it with `--shadow-float`. |
| Buttons | `border: 1px solid --control` on every non-primary button | Tonal fill (`--tonal`) or ghost. No outlined button exists. |
| Tablet board | Table with `border-top` on every row | A list of rows. Rows are separated by height and padding; hover is a tonal fill. |
| Callouts | Border plus tint | Tint only (`.note-*`). |
| Status pills | Border plus tint (warning, error) | Tint only. |

Before and after, same state, same size (left is `c.html`, right is `final.html`):

- Main: `shots/final/before-after-main-1440-light.png`
- Tablet offline (c's recovery state against the final offline state with the Next step card): `shots/final/before-after-offline-1440-light.png`
- Edit layout: `shots/final/before-after-arrange-1440-light.png`
- Phone main: `shots/final/before-after-main-390-light.png`

Count of resting 1 px borders in the main desktop state: c.html draws borders around the header, the right column, two inner sections, the source panel, the take column, every thumbnail, every non-primary button, the selected segment, the warning pill and every table row. Final draws resting lines only where they carry meaning: the dashed Preview outline and tablet outlines on the stage, the selected thumbnail ring and the selected tab bar, and a 1 px inset `--tonal` edge on dark-content thumbnails (Black, Calibration grid) so a black image does not vanish into a dark page. Text inputs have a border too, but main shows none.

---

## 2. Tokens

All tokens are CSS custom properties in `mockups/src/tokens.css`. Names are stable; U14 ports them as written. Light values sit on `:root`. Dark values sit in two identical blocks: `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) }` and `:root[data-theme="dark"]`. Colour roles never use alpha, so every ratio below is fixed. Only shadows and the scrim use alpha.

### 2.1 Colour

| Token | Light | Dark | Role |
|---|---|---|---|
| `--bg` | `#f1f2f5` | `#0f1115` | Page. The desk under everything. |
| `--surface` | `#ffffff` | `#171a20` | Raised: the side column. |
| `--well` | `#e8ebf0` | `#0b0d10` | Sunken: thumbnail wells, skeletons, meter track. |
| `--field` | `#ffffff` | `#111419` | Text-input fill. |
| `--overlay` | `#ffffff` | `#1f232b` | Floating: canvas toolbar, sheets, dialogs. In dark, overlay is lighter than surface (tonal elevation), because shadows barely show on dark. |
| `--tonal` | `#e3e6ec` | `#262b34` | Secondary button fill, hover fill for ghost buttons, tabs and rows. |
| `--tonal-hover` | `#d6dae2` | `#313744` | Hover on a tonal fill. |
| `--text` | `#14161b` | `#e8ebf1` | Body text. |
| `--text-muted` | `#535a68` | `#a3aab9` | Secondary text, captions. |
| `--on-primary` | `#ffffff` | `#0e1014` | Label on primary and filled danger. |
| `--control` | `#767d90` | `#7c8497` | Text-input border, switch track off, select chevron. |
| `--divider` | `#e1e4ea` | `#242932` | Hairline between rows of a dense list (Server diagnostics only). Decorative; no contrast claim. |
| `--primary` | `#3242c0` | `#93a3ff` | Primary action, selection, links. |
| `--primary-hover` | `#26339c` | `#b3beff` | Primary hover. |
| `--sel-bg` | `#e7e9fb` | `#252c4c` | Selected or pressed fill; info tint. |
| `--sel-text` | `#26339c` | `#c9d0ff` | Text on `--sel-bg`. |
| `--focus` | `#3242c0` | `#93a3ff` | Focus ring. |
| `--tally-preview` | `#3242c0` | `#93a3ff` | Preview monitor label. Same hue as action (owner decision 2). |
| `--tally-live` | `#c4221a` | `#ff6b5f` | On wall monitor label. |
| `--ok` / `--ok-bg` | `#11733b` / `#e2f3e8` | `#52d18d` / `#11301f` | Healthy only: Showing, all checks pass. |
| `--warn` / `--warn-bg` | `#875000` / `#fcefd6` | `#f0b44a` / `#33270e` | Offline tablet, conflict review. |
| `--err` / `--err-bg` | `#b3261e` / `#fbe9e7` | `#ff7b6e` / `#3a1b19` | Server unreachable, not confirmed, failed upload, danger buttons. |
| `--err-hover` | `#8f1d17` | `#ffa196` | Filled danger hover. |
| `--disabled` / `--disabled-bg` | `#5f6676` / `#e3e6ec` | `#8f96a6` / `#20242b` | Disabled label and fill (held to 4.5:1). |

Stage tokens are the same in both themes, because the physical wall is black. Only `--stage` changes (`#0a0b0e` light, `#000000` dark).

| Token | Value | Role |
|---|---|---|
| `--stage` | `#0a0b0e` / `#000000` | Stage well |
| `--stage-body` | `#1b1e25` | Tablet body |
| `--stage-line` | `#6d7588` | Tablet and screen outlines |
| `--stage-text` | `#eef0f4` | Labels, ruler lines, empty-state text on the stage |
| `--stage-pill` | `#08090c` | Label pill fill; text on the edit readout |
| `--stage-screen` | `#0d0f13` | Blanked screen (Measure), dark thumbnails |
| `--stage-hatch` | `#2a2e37` | Offline hatch |
| `--stage-sel` | `#93a3ff` | Selection ring, handles' stroke, smart guide, measure dimensions, Preview outline, edit readout |
| `--stage-handle` | `#ffffff` | Resize and rotate handle fill |
| `--stage-warn` | `#f0b44a` | Offline outline and "Offline" pill |

### 2.2 Elevation, shape, space, type, motion

| Token | Light | Dark |
|---|---|---|
| `--shadow-raised` | `0 1px 2px rgb(16 20 30 / 0.06), 0 2px 8px rgb(16 20 30 / 0.04)` | `0 1px 2px rgb(0 0 0 / 0.4), 0 2px 8px rgb(0 0 0 / 0.24)` |
| `--shadow-float` | `0 2px 6px rgb(16 20 30 / 0.08), 0 10px 28px rgb(16 20 30 / 0.14)` | `0 2px 6px rgb(0 0 0 / 0.4), 0 12px 32px rgb(0 0 0 / 0.5)` |
| `--shadow-modal` | `0 4px 12px rgb(16 20 30 / 0.08), 0 28px 72px rgb(16 20 30 / 0.24)` | `0 4px 12px rgb(0 0 0 / 0.4), 0 32px 80px rgb(0 0 0 / 0.6)` |
| `--scrim` | `rgb(10 12 16 / 0.44)` | `rgb(0 0 0 / 0.6)` |

| Token | Value | Use |
|---|---|---|
| `--radius-sm` | 6px | Tags, playlist and queue thumbnails, skeleton bars |
| `--radius-control` | 8px | Buttons, inputs, thumbnails, rows, tabs |
| `--radius-surface` | 12px | Stage wells, tinted blocks, canvas toolbar |
| `--radius-sheet` | 16px | Side column, sheets |
| `--radius-pill` | 999px | Status chip, number badge, switch, meter |
| `--space-1`, `--space-2`, `--space-3`, `--space-4`, `--space-6`, `--space-8`, `--space-12` | 4, 8, 12, 16, 24, 32, 48 px | Named after the Tailwind step. There is no `--space-5`, `--space-7` or `--space-10`. |
| `--control-h` | 36px (44px under `pointer: coarse`) | Buttons, inputs, tabs |
| `--control-h-lg` | 44px | Show on wall, Apply layout, Start |
| `--side-w` | 400px | Side column at ≥1024 px |
| `--ease-out` | `cubic-bezier(0.2, 0.8, 0.2, 1)` | All state transitions |
| `--dur-fast` / `--dur` | 120ms / 180ms | Colour changes / lifts, switches, disclosures |

Type: one family, Atkinson Hyperlegible Next (self-hosted in the React build; Google Fonts only in the mockup). Weights 400, 600, 700. Tabular numerals everywhere (`font-variant-numeric: tabular-nums`).

| Token set | Size / line | Weight | Use |
|---|---|---|---|
| `--text-title`, `--leading-title`, `--weight-title` | 1.375rem / 1.75rem (22 / 28 px) | 700 | Drill-in titles (Tablet 2, Measure Tablet 2, Library), sheet title |
| `--text-heading`, `--leading-heading`, `--weight-heading` | 1.125rem / 1.5rem (18 / 24 px) | 700 | App name, section headings (Tablets, Diagnostics), large stage message |
| `--text-body`, `--leading-body`, `--weight-body` | **1rem / 1.5rem (16 / 24 px)** | 400 | All running text and input values |
| `--text-label`, `--leading-label`, `--weight-label` | 0.875rem / 1.25rem (14 / 20 px) | 600 | Buttons, tabs, field labels, row names, chips, tallies |
| `--text-caption`, `--leading-caption`, `--weight-caption` | 0.8125rem / 1.125rem (13 / 18 px) | 400, coloured `--text-muted` | Metadata, hints, thumbnail names (set to 600) |

`--text-muted` is a colour, not a size, even though it shares the `--text-` prefix.

`--font-sans` is `"Atkinson Hyperlegible Next", system-ui, sans-serif`.

### 2.3 Port notes for U14 (Tailwind v4 and shadcn/ui)

`frontend/controller-app/src/styles/tokens.css` (read-only check, not edited) still holds the 02 foundation tokens, and `src/styles/app.css` maps `--color-muted: var(--muted)` and `--color-primary`. Replace that file with `mockups/src/tokens.css`. Renames:

| Current name in controller-app | Final name | Note |
|---|---|---|
| `--bg`, `--surface`, `--control`, `--primary`, `--on-primary`, `--primary-hover`, `--sel-bg`, `--sel-text`, `--warn`, `--warn-bg`, `--err`, `--err-bg`, `--disabled`, `--disabled-bg`, `--stage`, `--stage-body`, `--stage-line`, `--stage-text`, `--stage-sel`, `--stage-warn`, `--stage-hatch`, `--shadow-float`, `--radius-control` | same name | New values for several (`--bg`, `--disabled`, `--shadow-float`, `--radius-control` 6 → 8 px, and others); take them from the file. |
| `--muted` | `--text-muted` | `--muted` is a background in shadcn. Change `--color-muted: var(--muted)` to `--color-muted: var(--text-muted)` and the `text-muted` utility keeps working. |
| `--surface-2` | `--tonal` (fills, hover) | Use `--well` for sunken areas. |
| `--border` | `--divider` for hairlines; `--control` for input borders | `--border` remains only as the shadcn alias of `--divider`. |
| `--live` | `--tally-live` | |
| `--draft`, `--draft-bg` | `--tally-preview` (no tint) | Preview is indigo now; green is not used for drafts. |
| `--live-bg` | removed | No On wall tint is drawn. |
| `--stage-draft` | `--stage-sel` | The dashed Preview outline uses the selection indigo. |
| `--stage-live` | removed | Unused. |
| `--radius-panel` | `--radius-surface` (12 px) or `--radius-sheet` (16 px) | |
| (new) | `--well`, `--field`, `--overlay`, `--tonal-hover`, `--focus`, `--ok`, `--ok-bg`, `--err-hover`, `--divider`, `--stage-pill`, `--stage-screen`, `--stage-handle`, `--shadow-raised`, `--shadow-modal`, `--scrim`, `--radius-sm`, `--radius-sheet`, `--radius-pill`, the space, type, size and motion tokens | |

- Copy `tokens.css` as is and reference the roles from `@theme inline` (for example `--color-bg: var(--bg)`, `--color-tonal: var(--tonal)`, `--radius-control: var(--radius-control)`), so the theme switch stays a custom-property swap.
- The end of `tokens.css` aliases the shadcn variable names, so generated components pick up the system: `--background` → `--bg`, `--foreground` → `--text`, `--card` → `--surface`, `--popover` → `--overlay`, `--primary-foreground` → `--on-primary`, `--secondary` → `--tonal`, `--muted` → `--well`, `--muted-foreground` → `--text-muted`, `--accent` → `--tonal`, `--destructive` → `--err`, `--border` → `--divider`, `--input` → `--control`, `--ring` → `--focus`, `--radius` → `--radius-control`. `--primary` keeps its name.
- The muted text token is `--text-muted`, not `--muted`, because shadcn uses `--muted` as a background.
- shadcn's default `Card`, `Separator`, `Tabs` and `Button variant="outline"` draw borders. Remove the border from `Card`, use text tabs with an indicator, and do not use the `outline` button variant. Map `secondary` to tonal and `ghost` to ghost. Only `Input`, `Select` and `Textarea` keep a resting border.

---

## 3. Surfaces and elevation

Four tones, lowest to highest. A region is separated from its neighbour by a tone step, space, or a shadow. Never by a line.

| Level | Token | Shadow | Examples |
|---|---|---|---|
| Sunken | `--well`, `--stage` | none | Stage wells, thumbnail wells, skeletons, meter track |
| Page | `--bg` | none | Header, preview area, sources strip |
| Raised | `--surface` | `--shadow-raised` | The side column (one surface, nothing nested in it but tinted blocks and wells) |
| Floating | `--overlay` | `--shadow-float` | Canvas toolbar, popovers, thumbnail hover |
| Modal | `--overlay` | `--shadow-modal` over `--scrim` | Server sheet (`<dialog>` with `showModal()`) |

Rules:

1. Declare elevation once: a surface gets a tone step or a shadow, never a border as well.
2. Nesting depth is at most two inside the page: side column → tinted block or stage well. No card inside a card.
3. Tinted blocks (`.note-warn`, `.note-err`, `.note-info`, `.note-ok`) have no border and a `--radius-surface` corner. They hold one message and its actions.
4. Groups inside a surface are separated by space: 24 px between sections, 12–16 px between fields, 4–8 px inside a group.
5. In dark, a higher surface is lighter (`--bg` < `--surface` < `--overlay`), because shadows are nearly invisible on dark.

## 4. When a border is allowed

A visible line is used only where it carries information. Each case and its contrast:

| Case | Line | Contrast (light / dark) |
|---|---|---|
| Text input, select | 1 px `--control` | 4.11 / 4.65 on surface, 3.67 / 5.04 on page |
| Focus | 2 px `--focus` outline, 2 px offset (0 on inputs) | 6.69 minimum, both themes |
| Selection | Selected tab: 2 px bar. Selected thumbnail: 2 px ring. Pressed tool: 1.5 px inset ring. Current tablet: filled number badge. Stage: 3 px ring (selected) or 1.5 px frame with handles (editing). | 6.52 minimum |
| Drop target | 1.5 px dashed `--control`; `--primary` while a file is over it | 4.11 / 6.52 |
| Dense list | `--divider` hairline between Server diagnostics rows only | Decorative, no claim |
| Dark-content thumbnail | 1 px inset `--tonal` edge, so a black source stays visible on a dark page | Decorative, no claim |
| Stage geometry | Tablet and screen outlines, dashed offline outline, dashed Preview outline | 3.61 minimum |

Everything else, including buttons, panels, tabs at rest, rows, chips and callouts, has no border. A tonal button's fill against the surface is under 3:1 (about 1.2:1). That is allowed: WCAG 1.4.11 does not require a visible boundary when the label identifies the control, and every button has a visible text label or an accessible name with an icon. The selection and focus cues, which are state information, all meet 3:1.

## 5. Button hierarchy

One filled primary per region. Regions are: the preview area (its primary sits in the Take slot), the side column, and each sheet.

| Variant | Class | Rest | Hover | Use |
|---|---|---|---|---|
| Primary | `.btn-primary` | `--primary` fill, `--on-primary` label, `--shadow-raised` | `--primary-hover` | Show on wall, Apply layout, the Next step action, Next / Save in Measure, Start |
| Tonal | `.btn-tonal` | `--tonal` fill | `--tonal-hover` | Secondary actions: Identify, Save name, Try now, Download report, Edit layout |
| Ghost | `.btn-ghost` | transparent | `--tonal` | Tertiary: Cancel, Back, Discard, All images, icon buttons |
| Danger | `.btn-danger` | `--err-bg` fill, `--err` label | `--err` fill, `--on-primary` label | Clear wall… (opens the confirmation) |
| Danger, confirm | `.btn-danger-solid` | `--err` fill | `--err-hover` | The confirmation step's Clear wall only |

Sizes: default 36 px (44 px on touch), `.btn-lg` 44 px with 24 px padding and 16 px label, `.btn-sm` 32 px, `.btn-icon` square.

States for every variant (see `shots/final/components-1440-light.png`):

- Pressed or toggled (`aria-pressed="true"`): `--sel-bg` fill, `--sel-text` label, 1.5 px inset `--primary` ring.
- Busy: keeps its colour and width, adds a spinning `loader-circle`, label becomes the progressive verb ("Showing…"), `aria-disabled="true"`, cursor `progress`.
- Disabled: `--disabled-bg` fill and `--disabled` label (ghost stays transparent), `not-allowed` cursor, and a reason next to it ("Pick a source to preview it.", "The server can’t be reached.", "Review the change first.").
- Active: a 0.5 px press (`translateY`).

Copy is sentence case. The Vercel guideline asks for Title Case; the product's own copy is sentence case, so this spec keeps it.

---

## 6. Component inventory

| Component | Rest | Hover | Focus-visible | Selected / current | Disabled | Loading |
|---|---|---|---|---|---|---|
| Button (4 variants) | Section 5 | Section 5 | 2 px ring | Pressed ring | Grey, reason nearby | Spinner, verb |
| Tab (`.tab`) | `--text-muted` label | `--tonal` fill, `--text` label | Ring | `--text` label, 2 px `--primary` bar | n/a | Tabs render; panel shows skeletons |
| Source thumbnail (`.src`) | Image in a `--well` (or `--stage-screen`) well, no border | Lifts with `--shadow-float` | Ring around thumbnail and name, 6 px offset | 2 px `--primary` ring, name in `--primary` | `not-allowed` | Skeleton tile |
| Tablet row (`.row`) | Number badge (`--tonal`), name, model, state | `--tonal` fill, badge `--tonal-hover` | Ring | `--sel-bg` fill and badge filled `--primary` | n/a | Skeleton rows |
| Status chip (`.chip`) | Tint fill and matching text, icon, words | Slight saturation | Ring (it is a button that opens the cause) | n/a | n/a | Neutral chip with spinner ("Connecting…") |
| Row state (`.state`) | Icon + word: Showing (ok), Offline 12 min (warn), Unknown (muted) | n/a | n/a | n/a | n/a | n/a |
| Tally | Coloured square + word: Preview (`--tally-preview`), On wall (`--tally-live`) | n/a | n/a | n/a | n/a | n/a |
| Tinted block (`.note-*`) | Tint, title in role colour with icon, body in `--text` | n/a | Contains buttons | n/a | n/a | n/a |
| Text input (`.input`) | `--field` fill, 1 px `--control` | Border `--text-muted` | 2 px `--focus` outline, border `--focus` | n/a | `--disabled-bg`, no visible border | n/a |
| Invalid input | Border `--err`, message below in `--err`, linked by `aria-describedby` | | | | | |
| Select | Native `<select>`, `appearance: none`, chevron | As input | As input | n/a | As input | n/a |
| Switch | 40 × 24, track `--control` off, `--primary` on | n/a | Ring | On | n/a | n/a |
| Radio row | Native radio, row padding | `--tonal` fill | Ring on radio | `--sel-bg` fill (`:has(:checked)`) | n/a | n/a |
| Stepper | Dot `--tonal` / muted label (upcoming) | n/a | n/a | Dot `--primary` (current), `--ok-bg` with check (done) | n/a | n/a |
| Disclosure | Chevron + label | `--tonal` fill | Ring | Chevron turns 90° | n/a | n/a |
| Drop zone | 1.5 px dashed `--control` | n/a | Button inside | File over it: `--primary` dash on `--sel-bg` | Hidden when uploads are off (not drawn) | Queue below with meters |
| Meter | 6 px `--well` track, `--primary` fill, `role="progressbar"` | | | | | |
| Canvas toolbar | `--overlay` with `--shadow-float`, vertical, top-left of the stage | Ghost hover | Ring | Pressed ring (Move, Snap) | n/a | n/a |
| Stage handles | 10 px white squares with `--stage-sel` stroke at corners and edge midpoints; rotate handle on a 22 px stalk; readout tag `x 352  y 130 mm  90°`; dashed smart guide | n/a | Same ring as selection | n/a | n/a | n/a |
| Sheet | `<dialog>` via `showModal()`, right side, 520 px (full screen under 640 px), `--shadow-modal`, `--scrim` backdrop, `overscroll-behavior: contain` | | Focus moves to the first tab; Clear wall confirmation autofocuses Cancel | | | |
| Skeleton | `--well` blocks, 1.6 s opacity pulse; static under reduced motion | | | | | |

Browser surfaces are themed from the palette: `::selection` (`--sel-bg` / `--sel-text`), `accent-color: --primary`, `scrollbar-color: --control`, placeholder `--text-muted`, `color-scheme` per theme, `<meta name="color-scheme" content="light dark">`. `prefers-reduced-motion` removes every transition and animation. `forced-colors` adds `CanvasText` borders to buttons, tabs, rows, chips, blocks and surfaces, and a `Highlight` outline on selected items.

---

## 7. Layout

Desktop (≥1024 px): header 56 px on the page tone; below it a grid `minmax(0,1fr) 400px` with 16 px gaps and 16 px outer inset. Left: Preview label row (36 px), the Preview stage (fills the height), and the sources strip (152 px, fixed in every state) with the Take slot (216 px) on its right. Right: the side column surface, scrolling inside itself, with On wall, the Next step block when one applies, and the board or a drill-in.

Phone (<1024 px): one column that scrolls. The Preview label, the stage (3:2) and the On wall line are pinned at the top (owner decision 3: one On wall line under the preview; View expands it). Sources and the Take button follow, then the side column as a surface with rounded top corners. During Measure the sources strip is hidden on the phone so the stepper sits under the pinned preview.

The Next step block (from Direction B) appears at the top of the side column only when something needs doing: tablet offline, server unreachable, command not confirmed, draft conflict, first run. In the healthy main state there is no block.

The On wall monitor always draws server truth. During a conflict it shows the layout another controller applied; your edit stays in Preview, and the review block explains the difference (owner decision 1).

## 8. States drawn

Every state exists at 1440 × 900 and 390 × 844, light and dark: `shots/final/{state}-{width}-{theme}.png`.

| State | `?state=` | What it shows |
|---|---|---|
| Main | `main` | Healthy wall (4 of 4). Calibration grid picked and previewed with the dashed Preview outline; Show on wall enabled. |
| Tablet selected | `selected` | Ring on Tablet 2 in Preview; drill-in with status, Measure… (primary), Identify, Test colour, rename. |
| Edit layout | `arrange` | Non-grid draft (Tablet 2 turned 90°, Tablet 4 tilted 6°). Handles, rotate handle, readout and smart guide on Tablet 2. Vertical tool rail on the canvas. Inspector with X, Y, Turn, nudge pad and step. Apply layout and Discard in the Take slot. |
| Measure 1–4 | `measure-model`, `measure-size`, `measure-ruler`, `measure-review` | Vertical stepper in the side column. Preview dims the wall and blanks Tablet 2's screen; draws dimensions (steps 1, 2, 4) or the two 200 px ruler lines the tablet shows (step 3). Ruler step: Line A, Line B, ± error, Check result, Keep model / Use ruler (follows `physical.html:1008-1056`). Advanced fields stay behind one disclosure in step 4. |
| First run | `firstrun` | Dashed empty wall with a message on the stage; Next step block with join address, QR and Copy link. |
| Loading | `loading` | "Connecting…" chip, skeleton tablets on the stage, skeleton thumbnails, monitor and rows. |
| Tablet offline | `offline` | Amber chip, hatched Tablet 4, Next step: bring Tablet 4 back (Use the new tablet here, Join code). |
| Server unreachable | `unreachable` | Red chip, "As of 10:52" on the stage, dimmed On wall, Next step: wait for the server, rows "Unknown", Show on wall disabled with reason. |
| Command not confirmed | `uncertain` | Red chip, On wall "Not confirmed" and dimmed, Next step: refresh (primary). |
| Draft conflict review | `conflict` | Your edit in Preview, the newer wall in On wall, review block with Apply my layout / Use the wall's layout; Take slot disabled until reviewed. |
| Server: health | `server` | Modal sheet, Health tab: all checks pass, diagnostics list, Download report, Verify files, Technical details. |
| Server: backup and clear wall | `data` | Backup facts and Download backup; Clear wall with its confirmation expanded. |
| Server: playback | `playback` | Experimental switch, transport (Start primary), playlist with dwell fields, reorder buttons, Add, Loop, Save playlist. |
| Library and upload | `library` | Drill-in: drop zone, upload queue (64% uploading, waiting, a rejected HEIC with the fix), images. |
| Component states | `components` | Every button, tab, thumbnail, row, input, switch, chip and drop-zone state, forced with classes. |

## 9. Verification

All numbers below come from running the scripts on the built `final.html`.

**Token contrast** (`contrast_final.py`, reads `tokens.css` directly): 132 pairs, 0 below minimum. Body text pairs are held to 4.5:1, UI boundaries and large text to 3:1. Lowest text pair: disabled label on disabled fill, 4.60:1 (light). Lowest UI pair: `--control` on `--bg`, 3.67:1 (light). Full table in the appendix.

**Rendered contrast walk** (`audit_final.py`): every visible text node in 72 runs (18 states × 2 widths × 2 themes), composited through its ancestors, plus input borders, switch tracks, selected-tab bars, thumbnail rings, pressed rings, current badges and focus outlines. 113 distinct pairs were actually painted; 0 are below their minimum. Lowest text: 4.60:1 (light disabled label). Lowest UI: 3.67:1 (light input border on the page). SVG stage text is not in the walk; its pairs are the stage rows of the token table.

**axe-core 4.10.2** (tags wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa and best-practice), 72 runs: **0 violations**. 2,606 nodes passed colour contrast. 472 came back incomplete: SVG text on the stage, text over the stage overlays, and rows clipped inside a scrolled column. The rendered walk and the stage token rows cover these. The first run found two problems, both fixed: a dangling `aria-controls` in the loading state, and the walk's reading of the first-run stage message (the walk now resolves overlays on the stage to `--stage`).

**Stage box (G1)**: the Preview stage is 992 × 616 at (16, 104) in all 17 app states at 1440, and 358 × 239 at (16, 108) in all of them at 390, in both themes (`shots/final/stage-boxes.json`). Next step blocks, drill-ins, sheets and the conflict review never move it.

**Phone pinning**: in 12 states at 390 with touch emulation (`pointer: coarse` confirmed true), scrolling to the end keeps the stage fully in view, and no state scrolls horizontally. Two states did on the first run (loading skeletons and a long header chip); both fixed. The disabled Take button's reason was hidden on the phone in the first pass; it now shows under the button at every width.

**Type and spacing** (computed-style walk over the 17 app states at both widths, run on the final build, full output read): rendered sizes are 13, 14, 16, 18 and 22 px only. Every margin, padding and gap is 4, 8, 12, 16, 24, 32 or 48 px, except: 2 px (logo mark gap; switch top alignment), 36 px (step body aligned under the step label: 24 px dot + 12 px gap; select padding that clears the chevron), 44 px (input padding that clears the unit suffix), and `margin-left: auto` resolved to pixels (1, 20, 42, 81 … 1009 px). The walk first found 20 px side-column padding and 20 px sheet header padding; both moved to 24 px.

**Focus**: keyboard Tab reaches the pressed Calibration grid thumbnail in 9 presses; it matches `:focus-visible` with a 2 px solid ring (`#3242c0` light, `#93a3ff` dark). Crops: `shots/final/focus-source-{light,dark}.png`.

**Looked at**: every shot, through the contact sheets and per-state montages. Fixed after looking: the wall framed off-centre on the stage, the phone stage growing to the SVG's height, the side column overflowing during Measure, the canvas toolbar covering the selected tablet's rotate handle, the edit readout overlapping Tablet 4, a duplicate dashed outline next to the smart guide, the dark "Black" thumbnail disappearing into the page, busy buttons rendering as disabled, ruler labels colliding on the phone, the uncertain state previewing the wrong source, and the server tabs wrapping on the phone.

## 10. Deviations, illustrative values, and what is not drawn

Deviations from `02-directions.md`:

- Playback and playlists and Clear wall are in the Server panel, as this task asked. 02 §5 had moved Playback to a Sources tab and Clear wall to Layouts. The build can still add a Playlist sources tab when playback is on.
- Measure keeps C's side-column stepper (not A's modal), so the Preview can draw the values on the tablet being measured.
- Preview is indigo, not green (owner decision 2). Green appears only for healthy status.

Illustrative, not from the backend: the QR code (it does not encode anything), the join address `10.42.0.1:8080`, diagnostics values and times, upload file names and sizes, the backup folder, playlist dwell times, and the bezel values. Panel sizes are from published specs.

Not drawn:

- Motion: dragging on the canvas, handle hover, and transitions are described, not animated. The mockup is static.
- Server → Joining tab (its content is the first-run block), Saved and Tests source tabs, per-tablet test colour, the expanded "Retry, replace or remove" disclosure, the Advanced calibration fields, the expanded phone On wall view, the uploads-off state of the Library, and a playing playlist.
- Keyboard nudge and drag on the canvas are not prototyped; their keyboard and button alternatives are drawn (inspector fields, nudge pad, Turn 90°).
- Contrast of the stage label text was computed from tokens, not measured in the browser (axe cannot read SVG text over shapes).

---

## Appendix: token contrast table

Output of `python3 docs/redesign/mockups/src/contrast_final.py --md`.

| Theme | Pair | Colours | Ratio | Min | Used for | Result |
|---|---|---|---:|---|---|---|
| light | `text` on `bg` | #14161b / #f1f2f5 | 16.17:1 | 4.5 | Body text on the page | pass |
| light | `text` on `surface` | #14161b / #ffffff | 18.10:1 | 4.5 | Body text in the side column and sheets | pass |
| light | `text` on `overlay` | #14161b / #ffffff | 18.10:1 | 4.5 | Text in dialogs, popovers, canvas toolbar | pass |
| light | `text` on `tonal` | #14161b / #e3e6ec | 14.48:1 | 4.5 | Secondary (tonal) button label | pass |
| light | `text` on `tonal-hover` | #14161b / #d6dae2 | 12.92:1 | 4.5 | Tonal button label, hover; row hover | pass |
| light | `text` on `well` | #14161b / #e8ebf0 | 15.14:1 | 4.5 | Text on a sunken well (library tile caption, meter) | pass |
| light | `text` on `field` | #14161b / #ffffff | 18.10:1 | 4.5 | Text-input value | pass |
| light | `text-muted` on `field` | #535a68 / #ffffff | 6.93:1 | 4.5 | Input unit suffix and placeholder | pass |
| light | `control` on `field` | #767d90 / #ffffff | 4.11:1 | 3.0 | Text-input border against its own fill | pass |
| light | `text-muted` on `bg` | #535a68 / #f1f2f5 | 6.19:1 | 4.5 | Muted text on the page | pass |
| light | `text-muted` on `surface` | #535a68 / #ffffff | 6.93:1 | 4.5 | Muted text in the side column | pass |
| light | `text-muted` on `overlay` | #535a68 / #ffffff | 6.93:1 | 4.5 | Muted text in dialogs | pass |
| light | `text-muted` on `tonal` | #535a68 / #e3e6ec | 5.54:1 | 4.5 | Muted text on a hovered row | pass |
| light | `text-muted` on `well` | #535a68 / #e8ebf0 | 5.80:1 | 4.5 | Muted text on a well | pass |
| light | `on-primary` on `primary` | #ffffff / #3242c0 | 7.85:1 | 4.5 | Primary button label | pass |
| light | `on-primary` on `primary-hover` | #ffffff / #26339c | 10.31:1 | 4.5 | Primary button label, hover | pass |
| light | `primary` on `surface` | #3242c0 / #ffffff | 7.85:1 | 4.5 | Link and primary text in the side column | pass |
| light | `primary` on `bg` | #3242c0 / #f1f2f5 | 7.01:1 | 4.5 | Link and primary text on the page | pass |
| light | `primary` on `overlay` | #3242c0 / #ffffff | 7.85:1 | 4.5 | Link text in dialogs | pass |
| light | `sel-text` on `sel-bg` | #26339c / #e7e9fb | 8.57:1 | 4.5 | Selected row / pressed tool label | pass |
| light | `tally-preview` on `bg` | #3242c0 / #f1f2f5 | 7.01:1 | 4.5 | Preview tally label | pass |
| light | `tally-live` on `surface` | #c4221a / #ffffff | 5.85:1 | 4.5 | On wall tally label (side column) | pass |
| light | `tally-live` on `bg` | #c4221a / #f1f2f5 | 5.22:1 | 4.5 | On wall tally label (phone, on the page) | pass |
| light | `ok` on `surface` | #11733b / #ffffff | 5.93:1 | 4.5 | Showing status | pass |
| light | `ok` on `ok-bg` | #11733b / #e2f3e8 | 5.15:1 | 4.5 | Healthy summary chip | pass |
| light | `ok` on `bg` | #11733b / #f1f2f5 | 5.30:1 | 4.5 | Healthy summary chip text on the page header | pass |
| light | `warn` on `warn-bg` | #875000 / #fcefd6 | 5.81:1 | 4.5 | Warning chip and Next step title | pass |
| light | `text` on `warn-bg` | #14161b / #fcefd6 | 15.91:1 | 4.5 | Body text inside the warning Next step block | pass |
| light | `warn` on `surface` | #875000 / #ffffff | 6.61:1 | 4.5 | Warning text in the side column | pass |
| light | `err` on `err-bg` | #b3261e / #fbe9e7 | 5.58:1 | 4.5 | Error chip and block title, danger tonal button | pass |
| light | `text` on `err-bg` | #14161b / #fbe9e7 | 15.44:1 | 4.5 | Body text inside an error block | pass |
| light | `err` on `surface` | #b3261e / #ffffff | 6.54:1 | 4.5 | Error text in the side column | pass |
| light | `err` on `overlay` | #b3261e / #ffffff | 6.54:1 | 4.5 | Danger text in a sheet | pass |
| light | `on-primary` on `err` | #ffffff / #b3261e | 6.54:1 | 4.5 | Filled danger button label (confirmation step) | pass |
| light | `on-primary` on `err-hover` | #ffffff / #8f1d17 | 8.91:1 | 4.5 | Filled danger button label, hover | pass |
| light | `text` on `sel-bg` | #14161b / #e7e9fb | 15.04:1 | 4.5 | Body text inside a selected/info block | pass |
| light | `disabled` on `disabled-bg` | #5f6676 / #e3e6ec | 4.60:1 | 4.5 | Disabled button label | pass |
| light | `disabled` on `surface` | #5f6676 / #ffffff | 5.76:1 | 4.5 | Disabled ghost button label | pass |
| light | `control` on `surface` | #767d90 / #ffffff | 4.11:1 | 3.0 | Text input border, switch track off | pass |
| light | `control` on `overlay` | #767d90 / #ffffff | 4.11:1 | 3.0 | Text input border in dialogs | pass |
| light | `control` on `bg` | #767d90 / #f1f2f5 | 3.67:1 | 3.0 | Text input border on the page | pass |
| light | `focus` on `bg` | #3242c0 / #f1f2f5 | 7.01:1 | 3.0 | Focus ring on the page | pass |
| light | `focus` on `surface` | #3242c0 / #ffffff | 7.85:1 | 3.0 | Focus ring in the side column | pass |
| light | `focus` on `overlay` | #3242c0 / #ffffff | 7.85:1 | 3.0 | Focus ring in dialogs | pass |
| light | `primary` on `bg` | #3242c0 / #f1f2f5 | 7.01:1 | 3.0 | Selected tab indicator, selected thumbnail ring (page) | pass |
| light | `primary` on `surface` | #3242c0 / #ffffff | 7.85:1 | 3.0 | Selected tab indicator, current-row bar (side column) | pass |
| light | `primary` on `well` | #3242c0 / #e8ebf0 | 6.57:1 | 3.0 | Upload progress bar on its track | pass |
| light | `primary` on `tonal` | #3242c0 / #e3e6ec | 6.28:1 | 3.0 | Pressed tool indicator on tonal | pass |
| light | `warn` on `surface` | #875000 / #ffffff | 6.61:1 | 3.0 | Drop-target / warning icon | pass |
| light | `primary` on `sel-bg` | #3242c0 / #e7e9fb | 6.52:1 | 3.0 | Drop zone border while dragging over | pass |
| dark | `text` on `bg` | #e8ebf1 / #0f1115 | 15.82:1 | 4.5 | Body text on the page | pass |
| dark | `text` on `surface` | #e8ebf1 / #171a20 | 14.59:1 | 4.5 | Body text in the side column and sheets | pass |
| dark | `text` on `overlay` | #e8ebf1 / #1f232b | 13.19:1 | 4.5 | Text in dialogs, popovers, canvas toolbar | pass |
| dark | `text` on `tonal` | #e8ebf1 / #262b34 | 11.90:1 | 4.5 | Secondary (tonal) button label | pass |
| dark | `text` on `tonal-hover` | #e8ebf1 / #313744 | 9.99:1 | 4.5 | Tonal button label, hover; row hover | pass |
| dark | `text` on `well` | #e8ebf1 / #0b0d10 | 16.29:1 | 4.5 | Text on a sunken well (library tile caption, meter) | pass |
| dark | `text` on `field` | #e8ebf1 / #111419 | 15.45:1 | 4.5 | Text-input value | pass |
| dark | `text-muted` on `field` | #a3aab9 / #111419 | 7.92:1 | 4.5 | Input unit suffix and placeholder | pass |
| dark | `control` on `field` | #7c8497 / #111419 | 4.93:1 | 3.0 | Text-input border against its own fill | pass |
| dark | `text-muted` on `bg` | #a3aab9 / #0f1115 | 8.11:1 | 4.5 | Muted text on the page | pass |
| dark | `text-muted` on `surface` | #a3aab9 / #171a20 | 7.48:1 | 4.5 | Muted text in the side column | pass |
| dark | `text-muted` on `overlay` | #a3aab9 / #1f232b | 6.75:1 | 4.5 | Muted text in dialogs | pass |
| dark | `text-muted` on `tonal` | #a3aab9 / #262b34 | 6.10:1 | 4.5 | Muted text on a hovered row | pass |
| dark | `text-muted` on `well` | #a3aab9 / #0b0d10 | 8.35:1 | 4.5 | Muted text on a well | pass |
| dark | `on-primary` on `primary` | #0e1014 / #93a3ff | 8.09:1 | 4.5 | Primary button label | pass |
| dark | `on-primary` on `primary-hover` | #0e1014 / #b3beff | 10.63:1 | 4.5 | Primary button label, hover | pass |
| dark | `primary` on `surface` | #93a3ff / #171a20 | 7.41:1 | 4.5 | Link and primary text in the side column | pass |
| dark | `primary` on `bg` | #93a3ff / #0f1115 | 8.03:1 | 4.5 | Link and primary text on the page | pass |
| dark | `primary` on `overlay` | #93a3ff / #1f232b | 6.69:1 | 4.5 | Link text in dialogs | pass |
| dark | `sel-text` on `sel-bg` | #c9d0ff / #252c4c | 9.04:1 | 4.5 | Selected row / pressed tool label | pass |
| dark | `tally-preview` on `bg` | #93a3ff / #0f1115 | 8.03:1 | 4.5 | Preview tally label | pass |
| dark | `tally-live` on `surface` | #ff6b5f / #171a20 | 6.24:1 | 4.5 | On wall tally label (side column) | pass |
| dark | `tally-live` on `bg` | #ff6b5f / #0f1115 | 6.77:1 | 4.5 | On wall tally label (phone, on the page) | pass |
| dark | `ok` on `surface` | #52d18d / #171a20 | 9.02:1 | 4.5 | Showing status | pass |
| dark | `ok` on `ok-bg` | #52d18d / #11301f | 7.41:1 | 4.5 | Healthy summary chip | pass |
| dark | `ok` on `bg` | #52d18d / #0f1115 | 9.78:1 | 4.5 | Healthy summary chip text on the page header | pass |
| dark | `warn` on `warn-bg` | #f0b44a / #33270e | 7.88:1 | 4.5 | Warning chip and Next step title | pass |
| dark | `text` on `warn-bg` | #e8ebf1 / #33270e | 12.23:1 | 4.5 | Body text inside the warning Next step block | pass |
| dark | `warn` on `surface` | #f0b44a / #171a20 | 9.40:1 | 4.5 | Warning text in the side column | pass |
| dark | `err` on `err-bg` | #ff7b6e / #3a1b19 | 6.15:1 | 4.5 | Error chip and block title, danger tonal button | pass |
| dark | `text` on `err-bg` | #e8ebf1 / #3a1b19 | 13.02:1 | 4.5 | Body text inside an error block | pass |
| dark | `err` on `surface` | #ff7b6e / #171a20 | 6.90:1 | 4.5 | Error text in the side column | pass |
| dark | `err` on `overlay` | #ff7b6e / #1f232b | 6.23:1 | 4.5 | Danger text in a sheet | pass |
| dark | `on-primary` on `err` | #0e1014 / #ff7b6e | 7.54:1 | 4.5 | Filled danger button label (confirmation step) | pass |
| dark | `on-primary` on `err-hover` | #0e1014 / #ffa196 | 9.78:1 | 4.5 | Filled danger button label, hover | pass |
| dark | `text` on `sel-bg` | #e8ebf1 / #252c4c | 11.39:1 | 4.5 | Body text inside a selected/info block | pass |
| dark | `disabled` on `disabled-bg` | #8f96a6 / #20242b | 5.25:1 | 4.5 | Disabled button label | pass |
| dark | `disabled` on `surface` | #8f96a6 / #171a20 | 5.88:1 | 4.5 | Disabled ghost button label | pass |
| dark | `control` on `surface` | #7c8497 / #171a20 | 4.65:1 | 3.0 | Text input border, switch track off | pass |
| dark | `control` on `overlay` | #7c8497 / #1f232b | 4.20:1 | 3.0 | Text input border in dialogs | pass |
| dark | `control` on `bg` | #7c8497 / #0f1115 | 5.04:1 | 3.0 | Text input border on the page | pass |
| dark | `focus` on `bg` | #93a3ff / #0f1115 | 8.03:1 | 3.0 | Focus ring on the page | pass |
| dark | `focus` on `surface` | #93a3ff / #171a20 | 7.41:1 | 3.0 | Focus ring in the side column | pass |
| dark | `focus` on `overlay` | #93a3ff / #1f232b | 6.69:1 | 3.0 | Focus ring in dialogs | pass |
| dark | `primary` on `bg` | #93a3ff / #0f1115 | 8.03:1 | 3.0 | Selected tab indicator, selected thumbnail ring (page) | pass |
| dark | `primary` on `surface` | #93a3ff / #171a20 | 7.41:1 | 3.0 | Selected tab indicator, current-row bar (side column) | pass |
| dark | `primary` on `well` | #93a3ff / #0b0d10 | 8.27:1 | 3.0 | Upload progress bar on its track | pass |
| dark | `primary` on `tonal` | #93a3ff / #262b34 | 6.04:1 | 3.0 | Pressed tool indicator on tonal | pass |
| dark | `warn` on `surface` | #f0b44a / #171a20 | 9.40:1 | 3.0 | Drop-target / warning icon | pass |
| dark | `primary` on `sel-bg` | #93a3ff / #252c4c | 5.78:1 | 3.0 | Drop zone border while dragging over | pass |
| stage-light | `stage-text` on `stage` | #eef0f4 / #0a0b0e | 17.25:1 | 4.5 | Tablet label on the stage | pass |
| stage-light | `stage-text` on `stage-pill` | #eef0f4 / #08090c | 17.45:1 | 4.5 | Tablet name in its label pill | pass |
| stage-light | `stage-text` on `stage-body` | #eef0f4 / #1b1e25 | 14.62:1 | 4.5 | Text on a tablet body | pass |
| stage-light | `stage-text` on `stage-hatch` | #eef0f4 / #2a2e37 | 11.92:1 | 4.5 | Text over the offline hatch | pass |
| stage-light | `stage-warn` on `stage-pill` | #f0b44a / #08090c | 10.74:1 | 4.5 | "Offline" in its pill | pass |
| stage-light | `stage-sel` on `stage-screen` | #93a3ff / #0d0f13 | 8.15:1 | 4.5 | Measure dimensions on a blanked screen | pass |
| stage-light | `stage-sel` on `stage` | #93a3ff / #0a0b0e | 8.36:1 | 4.5 | Dimension readout on the stage | pass |
| stage-light | `stage-text` on `stage-screen` | #eef0f4 / #0d0f13 | 16.81:1 | 4.5 | Ruler numbers on a blanked screen | pass |
| stage-light | `stage-pill` on `stage-sel` | #08090c / #93a3ff | 8.46:1 | 4.5 | Edit readout (x, y, turn) on its indigo tag | pass |
| stage-light | `stage-line` on `stage` | #6d7588 / #0a0b0e | 4.26:1 | 3.0 | Tablet outline | pass |
| stage-light | `stage-line` on `stage-body` | #6d7588 / #1b1e25 | 3.61:1 | 3.0 | Screen outline on the body | pass |
| stage-light | `stage-sel` on `stage` | #93a3ff / #0a0b0e | 8.36:1 | 3.0 | Selection ring, handles, preview outline | pass |
| stage-light | `stage-sel` on `stage-body` | #93a3ff / #1b1e25 | 7.09:1 | 3.0 | Selection ring over a body | pass |
| stage-light | `stage-handle` on `stage` | #ffffff / #0a0b0e | 19.68:1 | 3.0 | Resize handle fill on the stage | pass |
| stage-light | `stage-handle` on `stage-sel` | #ffffff / #93a3ff | 2.35:1 | n/a | Handle fill inside its ring (shape cue only) | pass |
| stage-light | `stage-warn` on `stage` | #f0b44a / #0a0b0e | 10.62:1 | 3.0 | Offline outline | pass |
| stage-dark | `stage-text` on `stage` | #eef0f4 / #000000 | 18.41:1 | 4.5 | Tablet label on the stage | pass |
| stage-dark | `stage-text` on `stage-pill` | #eef0f4 / #08090c | 17.45:1 | 4.5 | Tablet name in its label pill | pass |
| stage-dark | `stage-text` on `stage-body` | #eef0f4 / #1b1e25 | 14.62:1 | 4.5 | Text on a tablet body | pass |
| stage-dark | `stage-text` on `stage-hatch` | #eef0f4 / #2a2e37 | 11.92:1 | 4.5 | Text over the offline hatch | pass |
| stage-dark | `stage-warn` on `stage-pill` | #f0b44a / #08090c | 10.74:1 | 4.5 | "Offline" in its pill | pass |
| stage-dark | `stage-sel` on `stage-screen` | #93a3ff / #0d0f13 | 8.15:1 | 4.5 | Measure dimensions on a blanked screen | pass |
| stage-dark | `stage-sel` on `stage` | #93a3ff / #000000 | 8.92:1 | 4.5 | Dimension readout on the stage | pass |
| stage-dark | `stage-text` on `stage-screen` | #eef0f4 / #0d0f13 | 16.81:1 | 4.5 | Ruler numbers on a blanked screen | pass |
| stage-dark | `stage-pill` on `stage-sel` | #08090c / #93a3ff | 8.46:1 | 4.5 | Edit readout (x, y, turn) on its indigo tag | pass |
| stage-dark | `stage-line` on `stage` | #6d7588 / #000000 | 4.55:1 | 3.0 | Tablet outline | pass |
| stage-dark | `stage-line` on `stage-body` | #6d7588 / #1b1e25 | 3.61:1 | 3.0 | Screen outline on the body | pass |
| stage-dark | `stage-sel` on `stage` | #93a3ff / #000000 | 8.92:1 | 3.0 | Selection ring, handles, preview outline | pass |
| stage-dark | `stage-sel` on `stage-body` | #93a3ff / #1b1e25 | 7.09:1 | 3.0 | Selection ring over a body | pass |
| stage-dark | `stage-handle` on `stage` | #ffffff / #000000 | 21.00:1 | 3.0 | Resize handle fill on the stage | pass |
| stage-dark | `stage-handle` on `stage-sel` | #ffffff / #93a3ff | 2.35:1 | n/a | Handle fill inside its ring (shape cue only) | pass |
| stage-dark | `stage-warn` on `stage` | #f0b44a / #000000 | 11.33:1 | 3.0 | Offline outline | pass |

pairs 132  fails 0
