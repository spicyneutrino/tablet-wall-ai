# Controller v2: design system

## Design read

A local operator console for a wall of physical tablets, used on a laptop in a normal room. The wall is the primary object. The interface should feel like a calm instrument, not a landing page: mineral paper, ink, one deep green signal accent, and a single dark surface for the wall.

## Colour

| Token | Value | Use |
|---|---|---|
| `--surface` | `#f6f8f5` | page and top bar |
| `--rail` | `#edf1ec` | roster and context rail |
| `--field` | `#fcfdfa` | inputs and raised controls |
| `--hover` | `#e4eae3` | hover surface |
| `--ink` | `#25312b` | primary text |
| `--muted` | `#59675d` | metadata and secondary text |
| `--rule` | `#d0d8d0` | hairlines |
| `--control-edge` | `#7a887d` | field and control boundary |
| `--accent` | `#23684f` | selection, primary actions, focus |
| `--accent-hover` | `#19533e` | primary hover |
| `--accent-wash` | `#dfede3` | selected row and active image summary |
| `--wall` | `#232e29` | wall canvas, the only large dark object |
| `--wall-grid` | `#354139` | wall grid |
| `--wall-text` | `#f0f5ed` | wall labels |
| `--wall-muted` | `#c4d0c4` | wall secondary labels |
| `--wall-accent` | `#a5e3bb` | selected footprint and preview cells |
| `--bezel` | `#576057` | footprint hatch |
| `--warning` | `#654d22` | warning text |
| `--warning-wash` | `#f1ead9` | warning surface |
| `--error` | `#893d32` | errors |
| `--error-wash` | `#f5e7e2` | error surface |

Contrast checks: ink on surface 14.2:1; muted on rail 5.1:1; white on accent 5.3:1; wall text on wall 11.2:1. Disabled controls are exempt from the text contrast minimum but are visibly muted.

One accent only. Device colours are data, not interface decoration. Warnings use a tinted full border, never a side stripe.

## Type

Family: `-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Arial, sans-serif`. Coordinates and revision use `ui-monospace, "SFMono-Regular", Consolas, "Liberation Mono", monospace`. No remote fonts.

| Role | Size / line | Weight | Tracking |
|---|---|---|---|
| Product | 16 / 24 | 600 | -0.02em |
| Wall title | 24 / 30 | 600 | -0.025em |
| Selection | 21 / 28 | 600 | -0.025em |
| Section | 13 / 20 | 600 | -0.01em |
| Body | 13 / 20 | 400 | 0 |
| Control | 13 / 20 | 500 | 0 |
| Meta | 12 / 18 | 400 | 0 |
| Coordinate | 11 / 16 | 400 mono | 0 |

Mobile inputs are 16px to avoid automatic zoom.

## Shape and space

- Radius: 3px for tiny labels and swatches, 6px for controls and panels, 10px for dialogs.
- Spacing: 4, 8, 12, 16, 20, 24, 32.
- Control height: 34px desktop, 44px mobile.
- Focus: 2px accent outline, 3px offset. On the dark wall, use wall text or wall accent.
- No drop shadows except the wall's single inset/outline treatment. No glass, no gradient text, no decorative status dots.

## Layout

- Desktop grid: `204px minmax(0,1fr) 308px`, rows `54px minmax(0,1fr) 34px`.
- The left rail scrolls; the centre scrolls; the right context scrolls.
- The wall keeps its true aspect ratio, measured inside a ruler shell. The map frame is capped at 560px high; extreme walls scroll.
- Mobile is one column with a task bar. The wall is first. Content and Layout replace the centre; Tablets shows the roster. The selected inspector sits below the wall on the Wall task.

## Components

- **Roster row:** 38x28 screen thumbnail, short ID, online/offline badge, resolution and type, "On the wall" or "Not placed". Placed rows use the accent border; offline rows use a dashed border. No palette or placement form in the row.
- **Wall footprint:** hatched frame, visible screen inset, short ID label, offline dashed, vacant dotted, shape warning mark. Selected footprint gets a wall-accent outline and four corner handles.
- **Wall image:** one asset mapped through every visible rect; bezel areas stay frame. The map shows the same slice geometry as the clients.
- **Inspector:** selection head with Remove/Place, position and size, shape readout and warning with Match screen shape, Move arrows, bezel disclosure, colour, details, remove/place action. `Remove` and `Place` are always near the top.
- **Content:** Colour / Calibration / Image tabs. Colour and Calibration switch the scene; Image opens the library and applies only from its explicit action. Active image preview follows the selection or the active wall image. Curated and uploaded assets are separate. Missing asset shows Pick replacement / Show colour / Show calibration.
- **Tile tool:** scope, order, columns, rows, gap, shape policy. Numbered cells overlay the wall. Two clicked cells swap. Apply is disabled on blocked capacity or retained-spot conflicts. The write note says each tablet is written one after another.
- **Warnings:** amber tinted full border with a mark, title, and specific text. The wall summary says how many shape and image checks need review.
- **Status bar:** time, live status, Undo, revision and session. Static on mobile so it does not cover controls.
- **Dialogs:** native `<dialog>` for keyboard help; focus returns to the trigger.

## States

- Empty roster: compact invitation and steps on mobile; short message on desktop.
- No wall state: map hidden, "Waiting for the server."
- No image selected: active wall image preview with "This is the image on the wall"; replacement selection is explicit.
- Missing image: error block with three recovery actions.
- Offline placed: dashed footprint, saved spot retained, warning lists unconfirmed IDs.
- Tile preview: existing panels dim, numbered cells show the proposed placement, apply blocked when unsafe.
- Partial tile failure: report the number applied, keep Undo available, do not claim rollback.

## Motion

No decorative motion. Only hover/focus and dialog transitions, all disabled under `prefers-reduced-motion`.
