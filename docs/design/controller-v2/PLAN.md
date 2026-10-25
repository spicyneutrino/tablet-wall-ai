# Single operator console: frontend stage 6

Source: Claude Sonnet 5.5 High, 2026-10-25. Planning only; this file records
the approved direction for implementation.

## What the plan found

- `physical.html`/`physical.js` and `index.html`/`controller.js` are two
  different state models, not two skins. The logical page uses the WebSocket,
  `PUT /wall`, `PUT /scene` and `/assets`; the physical page uses
  `/api/v3/config`, layout, playlist and playback. Uploads exist only in
  `controller.js`.
- Playlist items carry asset and dwell only. Per-item fit/transition is not in
  the playlist API, so Content v1 covers library, upload, order, dwell and
  loop; fit and transitions need a backend change.
- `#playback-status` already has a second live region; `announce()` writes
  state changes to `#page-status`.
- Readiness rows say `waiting` during healthy playback because they describe
  the next cut, and are sorted lexicographically, so `#2` can precede `#1`.

## Target

One page, `physical.html`, retitled **Wall console**. Keep the filename because
runners and tests hard-code it. The stage is always visible. A sticky right
rail has four tabs:

| Tab | Contents |
| --- | --- |
| Show | transport, one-line cohort, exclusions when present, next-cut readiness, Details |
| Tablet | tablet list, selected inspector, profile and calibration |
| Content | library, upload (later), playlist order, dwell, loop, Save playlist |
| System | wall bounds, saved layouts, diagnostics, rebind |

Default tab is Show when idle/playing/paused and blocked/failed/recovering.
A stage selection opens Tablet and focuses the inspector. Tabs are view-only
state and never dirty the draft. A compact transport strip stays in the
topbar so Stop is always reachable. `index.html` stays a linked logical mode
until the operator confirms it can be retired.

## Phases

1. **Low-risk fixes on the current page.** Live-region split, one-line cohort,
   transport order, `waiting` -> `preparing next`, display-number sort,
   keyboard stage scroll, local Apply/Cancel, selection/warning color split,
   no side stripes, type floor and measure, mobile playback cap and retitle.
2. **Single-console rail.** Add the four tabs, topbar transport, local Apply
   footer, selection-opens-Tablet, mobile compact view.
3. **Content and legacy.** Port upload from `controller.js`, promote library,
   playlist and slideshow; link or later redirect the logical mode. Defer the
   authenticated controller tablet and backend fit/transition controls.

## Phase 1 first PR

Files: `physical.html`, `physical.css`, `physical.js`,
`simulator/browser/controller_run.py`, cache-bust query strings.

1. Remove `role="status"` and `aria-live` from `#playback-status`. Add
   `#playback-countdown` with `aria-hidden="true"`. Move the remaining-time
   text out of the state sentence. Keep `#page-status` as the state
   announcement.
2. Put transport actions directly below the status line in an active session.
   Make the cohort a one-line summary. Move the long exclusion explanation
   into a collapsed disclosure.
3. Rename "Readiness" to "Next cut". Show `preparing next` instead of
   `waiting` while the current picture is healthy. Sort rows by display
   number.
4. Add `id="stage-scroll"`, `tabindex="0"`, `role="region"` and a label. At
   ≤719 px scale the SVG to fit and remove the horizontal scroll.
5. Add `#btn-apply-local` and `#btn-cancel-local` to a sticky footer in the
   Selected tablet card. They proxy `#btn-apply`/`#btn-cancel` and share their
   disabled state. Selecting a slot scrolls the inspector into view and focuses
   `#selected-title` (add `tabindex="-1"`), but not during a pointer drag.
6. Use ink for selection, keep orange for primary/focus/warning, remove
   side-stripe borders, raise utility type to 13 px, cap prose at 62ch, and
   retitle to "Wall console".
7. At ≤719 px cap the sticky playback card at about 190 px: state, countdown,
   transport and a More disclosure. Hide the rest until More expands.
8. Update `controller_run.py` countdown assertions and add checks for the
   live region, readiness order/text, one-line cohort, and mobile stage fit.

## File ownership

| Owner | Files |
| --- | --- |
| A | `physical.html` only |
| B | `physical.css`, `physical-legacy.css`, cache query in HTML agreed with A |
| C | `physical.js` only |
| D | `simulator/browser/controller_run.py`, new console runner if needed |

A and C agree on IDs first. B reads CSS class names from A. D updates
assertions after C lands. Do not touch `controller.js`, `controller.css`, or
other runners in Phase 1.

## Acceptance

- Existing `controller_run.py` scenarios still pass.
- New checks: no live-region countdown updates; `#page-status` one mutation
  per state change; readiness says `preparing next` and sorts by display
  number; cohort one line; local Apply visible after selection; 390 px no page
  overflow and stage fits; axe no serious/critical issues at 1440 and 390.
- No horizontal page overflow at 1440, 1280, 1024, 390. No console errors.
- Preserve IDs used by runners: playback status/buttons/details/facts,
  playlist library/add/save/items, rebind controls, stage SVG, Apply/Cancel,
  page status.
