# QA baseline — rendered frontend at `0ff56e3`

Initial rendered-app evidence for the image-wall readiness milestone. Baseline
only: it records what the current UI does so later changes can be judged against
observed behaviour, not against memory. It does not accept any roadmap item and
does not establish real-tablet, optical, or soak results.

| Field | Value |
| --- | --- |
| Baseline commit | `0ff56e3` (`feat: add measured tablet setup and adaptive wall sizing`) |
| Frozen source used for the run | `git archive 0ff56e3` → `/tmp/opencode/tw-base-0ff56e3` |
| Branch at run time | `work/tablet-wall-readiness` (integration branch, other agents active) |
| Server URL | `http://127.0.0.1:8766` (loopback only, unused port) |
| Desktop viewport | 1440 × 1000 CSS px, DPR 1 |
| Mobile viewport | 390 × 844 CSS px, DPR 3, Android mobile UA, touch |
| Evidence directory | `/var/home/oak/.local/share/tablet-wall-ai/readiness-program/baseline/` |
| Run record | `0ff56e3-run.json`, `0ff56e3-geometry.json`, `0ff56e3-selection-check.json` in the same directory |
| Run date | 2026-11-01, ~08:44–08:46 UTC |

## 1. Why the run used a frozen tree

The brief pinned `0ff56e3`, but the integration branch advanced while this run
was starting. These landed during the session:

```
5a9cc29 fix(controller): recognize protocol 3 image capabilities
ef99cb8 docs: clarify protocol 3 image capability requirements
abb9c42 fix: respect image capability in physical render frames
```

`18afa5c fix(controller): align capability summaries with negotiated
protocols` landed after the evidence was captured. None of these were made or
reviewed by this task; the baseline stays pinned to `0ff56e3`.

The first attempt served the moving working tree and produced two different
answers for the same check (the "capability unknown" warning appeared at 08:36
and had disappeared by 08:39 because `controller.js` changed underneath the
run). Those screenshots are kept but marked superseded in
`baseline/superseded-drift-abb9c42/` and are **not** used as evidence.

Every finding below comes from the frozen `0ff56e3` export, served on port
8766. Nothing in the checkout was modified by this task: the only file written
is this document.

## 2. Environment and exact commands

```bash
# 1. Freeze the baseline revision outside the checkout (read-only export).
cd /var/home/oak/Codes/projects/tablet-wall-ai
rm -rf /tmp/opencode/tw-base-0ff56e3 && mkdir -p /tmp/opencode/tw-base-0ff56e3
git archive 0ff56e3 | tar -x -C /tmp/opencode/tw-base-0ff56e3

# 2. Disposable data root: database, curated assets, media store, logs, scripts.
ROOT=/tmp/opencode/tw-qa-baseline-0ff56e3
mkdir -p "$ROOT"/data/assets "$ROOT"/data/media/objects "$ROOT"/data/media/staging "$ROOT"/logs
cp assets/EXLENT_Cohort_3_Flyer_Temp.png "$ROOT"/data/assets/sample-flyer.png

# 3. Private loopback server from the frozen tree.
cd /tmp/opencode/tw-base-0ff56e3
TABLET_WALL_DB="$ROOT/data/tablet-wall.db" \
TABLET_WALL_ASSET_DIR="$ROOT/data/assets" \
TABLET_WALL_MEDIA_DIR="$ROOT/data/media" \
setsid nohup rtk /var/home/oak/Codes/projects/tablet-wall-ai/.venv/bin/python \
  -m uvicorn main:app --host 127.0.0.1 --port 8766 --log-level warning \
  > "$ROOT/logs/server.log" 2>&1 &
```

The Playwright driver scripts were written to
`/tmp/opencode/tw-qa-baseline-20261101T023400Z/` and executed with the
repository `.venv` Python:

```bash
cd /tmp/opencode/tw-base-0ff56e3 && \
  rtk /var/home/oak/Codes/projects/tablet-wall-ai/.venv/bin/python \
  /tmp/opencode/tw-qa-baseline-20261101T023400Z/qa_baseline_0ff56e3.py
```

Temporary data paths (all disposable, deleted on VM restart):

- DB: `/tmp/opencode/tw-qa-baseline-0ff56e3/data/tablet-wall.db`
- Assets: `/tmp/opencode/tw-qa-baseline-0ff56e3/data/assets/`
- Media: `/tmp/opencode/tw-qa-baseline-0ff56e3/data/media/`
- Server log: `/tmp/opencode/tw-qa-baseline-0ff56e3/logs/server.log`

Never touched: the live `tablet-wall.db` in the checkout, the live asset
library, hotspot configuration, firewall, or the running installation. The
server was stopped after the run; Playwright closed every browser it opened.

Browser isolation: Playwright's bundled headless Chromium with a fresh
context per device (own storage, DPR, UA, touch, timezone). The
`chrome-devtools-mcp` and `agent-browser` processes already running on the
machine belong to other work and were **not** attached to; no shared user
profile was automated.

## 3. Simulated wall

Four private contexts, deterministic device ids so reruns are comparable. Each
reported its real viewport, screen size, DPR, and platform family on
registration, which let the server match `tabletwall/tablet_models.py`.

| # | Context | Viewport | DPR | Platform | Matched model |
| --- | --- | --- | --- | --- | --- |
| 1 | `pixel-c-1` | 900 × 1280 | 2 | Android | Google Pixel C (147 × 210 mm) |
| 2 | `pixel-c-2` | 900 × 1280 | 2 | Android | Google Pixel C |
| 3 | `ipad-air-2-1` | 768 × 1024 | 2 | iOS (iPad UA) | iPad Air 2 (146.8 × 196 mm) |
| 4 | `ipad-air-2-2` | 768 × 1024 | 2 | iOS (iPad UA) | iPad Air 2 |

All four negotiated protocol 3 with
`caps = calibration,image,physical,video`:

```
ws://127.0.0.1:8766/ws/device?device_id=11111111-…&protocol=3&caps=calibration,image,physical,video&w=900&h=1280&dpr=2&orientation=0&mode=tab
```

Content: one curated asset, `sample-flyer.png` (4000 × 3000 px, 2.79 MB), the
only image in the temporary asset directory. The image scene uses
`fit: "cover"` (`DEFAULT_FIT`); the baseline console exposes no fit control.

## 4. What was exercised

| Area | Exercise | Result |
| --- | --- | --- |
| Tablet registration and content | Four tablets opened `/client/`, registered, connected, painted the wall image | Pass |
| 2×2 image arrangement | Layout pane → Quick arrange → columns `2` → Arrange online | Rendered; see F1 |
| 1×4 image arrangement | Layout pane → Quick arrange → columns `4` → Arrange online | Rendered; see F1 |
| Image spanning | Inspected each tablet screenshot and canvas pixels after both arrangements | Spans; see F2 |
| Wrong-protocol warning | Placed a protocol-1 device on an image wall | Warning shown; see F3 |
| Protocol-3 capability reporting | Read controller coverage alert and the controller WebSocket snapshot | Contradicts painted result; see F4 |
| Content picker | Content tab → Image → list → select → Show on wall, desktop and mobile | Works; see F5 |
| Physical draft flow | `/controller/physical.html`: select tablet → calibration → Add to wall → nudge → Apply | Draft/apply works; see F6 |
| Desktop 1440 × 1000 | Hierarchy, overflow, keyboard focus, console | See F7, F9, F10 |
| Mobile 390 × 844 | Same, plus mobile task nav | See F8, F9, F10 |
| Legacy console after a physical layout | Opened `/controller/` with a physical wall active | Silent stale state; see F6 |

Not exercised (limits, not passes): drag-and-drop placement or drag reorder;
tile preview/apply; saved layout/scene recall; playback and video; uploads with
admission enabled; WebKit/Safari; touch gestures in a real browser; anything
requiring a lit panel, bezel, ruler, or camera.

## 5. Findings

Severity is about the rendered operator experience at this baseline. Items that
the roadmap already targets are cross-referenced; nothing here is a new
requirement.

### F1. 2×2 and 1×4 arrangements render and span (old behaviour works)

Quick arrange writes equal cells across the *fixed* 2000 × 1000 wall:

| Preset | Placements (`x, y, w, h`) |
| --- | --- |
| 2×2 | `[0,0,1000,500]`, `[1000,0,1000,500]`, `[0,500,1000,500]`, `[1000,500,1000,500]` |
| 1×4 | `[0,0,500,1000]`, `[500,0,500,1000]`, `[1000,0,500,1000]`, `[1500,0,500,1000]` |

Screenshots: `0ff56e3-05-desktop-2x2.png`, `0ff56e3-06-desktop-1x4.png` and the
four `0ff56e3-05-tablet-*-2x2.png` / `0ff56e3-06-tablet-*-1x4.png` captures.

Old behaviour worth judging later changes against:

- The grid divides the wall; it does not derive from the tablets' bodies. The
  wall stays "2000 × 1000 units · Fixed size" and the console reports
  **"4 tablets with a different screen shape"** plus the wall warning
  **"4 screen shapes differ."** with a "Review wall checks" action. Each
  mismatched tile carries a faint badge with both aspects (for example
  `0.500 × 0.703`), so the difference is named on the map as well as in the
  summary line.
- Arrange applies immediately. There is no preview step and no Apply gate for
  this path (`controller.js:1264` disables Quick arrange in "Fits tablets" mode
  and points at "Pack placed tablets" instead).
- Resize to "Fits tablets" + Pack columns keeps the same mismatch, verified on
  the frozen tree: saving sizing `tablets` gave a 2000 × 1000 wall, then Pack
  with 2 columns gave a 1000 × 2000 wall with 500 × 1000 cells (aspect 0.5) for
  tablets with aspect ≈ 0.70, so "4 screen shapes differ." persists. Quick
  arrange is disabled while the wall is fitted (`controller.js:1264`), and
  `fit_logical` only encloses existing footprints (`tabletwall/sizing.py:31-45`).
  Evidence: `0ff56e3-22-desktop-fit-pack-2col.png`.

Cross-reference: roadmap §4.1 requires presets derived from measured bodies,
fit-to-tablets sizing, gap 0, preview before Apply, one atomic write.

### F2. The image spans correctly across the four tablets

After 2×2, each tablet painted its own slice. Canvas samples at 2 %/98 % corners
differ per device, and the captures show four different regions of the flyer:
`0ff56e3-05-tablet-pixel-c-1-2x2.png` (bottom-right keynote), etc. After 1×4 the
four slices are a clean left-to-right run
(`0ff56e3-06-tablet-*-1x4.png`).

Because the scene is `cover` on a portrait-ish wall, a 4:3 flyer is cropped and
appears heavily magnified across four panels; that is the current fit rule, not
a spanning failure.

### F3. Protocol-1 device on an image wall → named warning (works)

A registered protocol-1 device placed at `[0,0,600,800]` with the image live
produced:

> **The image will not cover the whole wall** — 1 placed online tablet does not
> support images: 55555555. They show their colour while the rest show the
> picture, so the image has gaps.

`data-kind="bad"`, plus the summary line "1 tablet cannot show the image."
Evidence: `0ff56e3-04-desktop-protocol-1-warning.png`. The warning cleared when
the test device was released and forgotten, so it is state-derived, not sticky.

### F4. Protocol-3 tablets are reported as "capability unknown" while they paint (defect)

All four online tablets advertise protocol 3 and the `image` capability, and
they demonstrably paint the image, yet the legacy console shows:

> **Placed, not confirmed** — `11111111 (online · capability unknown),
> 22222222 (online · capability unknown), 33333333 (online · capability unknown),
> 44444444 (online · capability unknown).` …
> There is no way to confirm what these show.

The same alert is present in the desktop 2×2 and 1×4 captures and on mobile
(`0ff56e3-05-desktop-2x2.png`, `0ff56e3-07-mobile-390x844-wall.png`).

Cause at this revision is a contract mismatch, not a rendering bug:
`frontend/client/client.js:56` advertises `PROTOCOL_VERSION = 3`, while
`frontend/controller/controller.js:1357` and `:1456` accept only
`device.protocol === 2` as image-capable. The controller WebSocket snapshot
confirms the server side is correct:

```json
{"id": "11111111", "protocol": 3,
 "caps": ["calibration", "image", "physical", "video"], "online": true}
```

This is the baseline state that `5a9cc29` addresses; this document does not
accept that fix, it only records the pre-fix rendering. Any later change must
keep the warning honest: capability must never be inferred from a successful
paint, and a real capability gap must still be named.

### F5. Content picker is available and honest about its limits

Desktop and mobile Content → Image show one asset with dimensions, aspect,
size, short id, preview and an enabled "Show on wall". After applying, the wall
line reads "Wall image sample-flyer.png, 4000×3000, fills the wall", the bar
becomes "sample-flyer.png, 4000×3000, already on the wall" with the action
disabled to "Already on the wall", and the wall status reads
`On the wall sample-flyer.png / 4 not placed`.

Uploads are disabled by default (`TABLET_WALL_UPLOAD_MODE` unset → `disabled`):
the "Add a file" block and media library stay hidden, and `/media` answers
`403 {"detail":"uploads are disabled"}`. The UI surfaces no inline explanation
of that 403; only the console shows the failed request. Evidence:
`0ff56e3-02-desktop-content-picker.png`, `0ff56e3-03-desktop-image-selected-on-wall.png`,
`0ff56e3-08-mobile-390x844-content.png`.

### F6. Physical draft flow works, and replaces the logical wall

1. `/controller/physical.html` opens on a logical wall with
   **"Draft not applied"** and the note "The active wall is still logical. This
   draft starts from its dimensions; applying it replaces the logical layout
   with a physical one." Health: `4 online · 0 offline · 4 wake-lock warnings`.
2. Each tablet already had profile r1 and calibration r1 from model matching;
   that is shown per row. Evidence: `0ff56e3-12-physical-initial.png`.
3. Selecting a tablet shows "Add to wall" and the empty-slot note. The
   selected-tablet heading stays "–" until a slot exists, because the inspector
   body is hidden in that state; the device row carries the "Selected" chip.
   Evidence: `0ff56e3-13-physical-tablet-selected.png`.
4. Calibration used the live viewport (768 × 1024, DPR 2) plus 32 mm over a
   200 px span → 0.16 mm per CSS px, saved as revision 2 with mode `tab` and
   orientation `0°`. Evidence: `0ff56e3-14-physical-calibration-saved.png`.
5. "Add to wall" created a draft slot at centre `(1000, 500)` and flipped the
   flag to **"Unapplied changes"** (`data-dirty="true"`) while `/api/v3/config`
   still reported `kind: "logical"`. Nudge X +1 changed only the draft
   (`nudge_x=1`, committed kind still `logical`). Evidence:
   `0ff56e3-15-physical-slot-draft.png`, `0ff56e3-16-physical-draft-dirty.png`.
6. Apply wrote `kind: "physical"`, bounds `2000 × 1000 mm`, one slot, revision 9;
   the flag became "Matches the committed layout". Evidence:
   `0ff56e3-17-physical-applied.png`.

Old behaviour a later change must not silently keep:

- Applying a one-slot draft took the other three tablets **off the wall**:
  health became `4 online · 0 offline · 3 unplaced`, their clients showed
  "Not placed" (`0ff56e3-18-tablet-*-physical-applied.png`), and no
  confirmation was requested before replacing the logical arrangement.
- The physical stage draws a 146.8 × 196 mm body inside a 2000 × 1000 mm wall at
  0.332 stage px/mm; the tablet is ~49 × 65 px, so the slot is hard to target.
  The stage has no zoom control at this revision.
- The legacy console, still open against the new physical wall, kept saying
  **Live**, showed an empty 2000 × 1000 "Fixed size" colour wall, four
  "Not placed" tablets, and no message. Only the browser console showed
  `409 /wall`; the server's detail is "Upgrade controller: a physical layout is
  active" (`main.py:1678-1684`), and it never reaches the screen.
  Evidence: `0ff56e3-19-legacy-controller-on-physical-wall.png`.
- One saved logical layout appeared in the sidebar as
  `Before physical c8c63959da…`, clipped at the panel edge without an ellipsis.

### F7. Desktop 1440 × 1000 layout

- No horizontal overflow (`scrollWidth = clientWidth = 1440`); no element
  crosses the viewport edge.
- Column widths: topbar 54 px, roster 204 px, centre 928 px (wall map
  874 × 437), context 308 px. The three-column shell is stable.
- The tablet-address line truncates with an ellipsis at 1440
  ("Local testing only: http://127.0…"): `#client-url` measures 323 px of
  content in a 224 px box and carries no `title`, so the full address is only
  reachable by copying.
- The right context pane keeps its own scroll; after Arrange online the "Gap"
  and "Order" fields sat clipped at the pane's top edge because the pane had
  been scrolled by the interaction. Content is reachable, but there is no
  sticky heading telling the operator which section is cut off.
- Hierarchy: `H1 Tablet wall` → `H2 Tablets` / `H2 Wall` → `H3` per tablet and
  "Saved layouts". No duplicate ids; no control without an accessible name.

### F8. Mobile 390 × 844 layout

- No horizontal overflow on any of the four task views
  (`scrollWidth = clientWidth = 390`).
- Mobile nav is the only task switcher; the roster column collapses to zero
  width and the context pane becomes a full-width strip below the wall. Task
  switching works and keeps wall state.
- The wall map is 349 × 175 CSS px, i.e. a 2:1 viewport for a 2:1 wall at
  ~5.7 px per wall unit. Tile labels render at 13 px on top of the image, so
  four labels sit over the poster's headline and body copy
  (`0ff56e3-07-mobile-390x844-wall.png`). "2x zoom" exists in the toolbar but
  the default view is the cramped one; below "Review wall checks" the wall view
  leaves a blank band of roughly 180 px above the page footer.
- The "Placed, not confirmed" block (F4) dominates the mobile wall view: it
  fills about 100 px with the same four ids, and "Review wall checks" sits
  directly under it.
- The tablets list gives the short id the largest type in each row, with the
  model, size, platform and "On the wall" stacked around it; rows sit about
  67 CSS px apart and leave a wide empty column on the right
  (`0ff56e3-10-mobile-390x844-tablets.png`).
- The Layout view is a single long column: wall size, tile preview, quick
  arrange, saved setups. Readable at 390, but "Arrange online" is several
  screens below the wall heading (`0ff56e3-09-mobile-390x844-layout.png`).

### F9. Keyboard focus

- Every focused control reported the same visible indicator:
  `outline: solid 2px rgb(35, 104, 79)` (plus the component's own ring where
  applicable). No focused element was offscreen in the walks.
- The skip link is first in order and becomes a solid light box over the brand
  (`0ff56e3-20-desktop-focus-walk.png`); it is legible, but it overlaps the H1
  while focused.
- Mobile order: `Physical setup` link → the four nav tabs → wall actions →
  `Change` → snap checkbox. The nav is reachable before the content, and the
  active tab is `aria-pressed`/selected consistently with the visible state.
- `#snap-toggle` measures 15 × 15 px, but its label ("Snap") is the clickable
  target; treat it as a false positive for tap-size checks. The only genuine
  sub-24 px target found is the in-copy "Physical setup" link in the mobile
  Layout pane (80 × 17 px).

### F10. Console and network

No uncaught page errors on any page. Failed requests: none.

| Page | Response | Meaning |
| --- | --- | --- |
| `/controller/` (desktop, mobile), `/controller/physical.html` | `GET /media` → 403 | uploads disabled by default; picker hides upload UI |
| `/controller/physical.html` | `GET /diagnostics` → 403 | diagnostics are admitted like the library and fail closed while uploads are disabled |
| `/controller/` after physical apply | `GET /wall` → 409 | logical route fenced while the wall is physical; not surfaced in the UI |

Canvas `getImageData` warnings on tablets come from this test harness reading
pixels, not from application code.

## 6. Candidate contract tests for later revisions

Each item is a checkable statement derived from the roadmap plus the baseline
gaps above. "Baseline" records what `0ff56e3` does, not an acceptance result.
Confirm the wording against the roadmap before treating any of these as the
contract.

| # | Check | Baseline |
| --- | --- | --- |
| C1 | With four tablets selected, the 2×2 preset produces four slots with equal body sizes derived from profiles, gap 0, and a wall that encloses them; every tablet paints a distinct quadrant of one image | Fails: cells derive from wall units; "4 screen shapes differ" |
| C2 | The 1×4 preset does the same in one row, in display-number order, with a preview before Apply | Fails: applies immediately, no preview |
| C3 | Switching 2×2 ↔ 1×4 preserves the other arrangement and does not release offline reservations | Not exercised; Quick arrange rewrites all placements |
| C4 | A protocol-1 or capability-less online tablet on an image wall keeps the named "will not cover" warning, including the device id | Passes (F3) |
| C5 | Protocol-3 tablets with `caps` containing `image` are not reported as "capability unknown"; a genuinely unknown capability is still reported as unknown | Fails (F4) |
| C6 | No tablet is reported as confirmed merely because a frame was sent; confirmation requires a render acknowledgement | Not implemented; console has no per-tablet content state |
| C7 | The operator can choose Fill (cover) or Fit whole image for the scene; the choice is remembered per content item and reflected in the coverage text | Fails: fixed `cover`, no control |
| C8 | A physical draft edit changes nothing until Apply; Apply sends bounds and every slot in one write; the committed revision changes once | Passes for a single slot (F6, steps 5–6); not tested with several slots |
| C9 | Applying a physical layout that leaves tablets unplaced names them before or after the change; the operator is not surprised by "3 unplaced" | Fails as UX: no confirmation, only post-hoc health text |
| C10 | The legacy logical console, when a physical wall is active, shows an explicit upgrade/redirect state instead of an empty colour wall with a live connection | Fails (F6) |
| C11 | The content picker states why uploads are unavailable when admission is disabled (not only a 403 in the console), and lists curated assets with dimensions | Partly: list works; reason is silent |
| C12 | 390 × 844 keeps zero horizontal overflow on every task view, and either uses the spare height for the wall map or offers a zoom that does | Overflow passes; map is 349 × 175 with four 13 px labels over the image |
| C13 | Every interactive control keeps a visible focus indicator and has an accessible name; mobile tap targets are ≥ 24 × 24 px | Passes except the 80 × 17 in-copy link |
| C14 | Real screenshots of a 2×2 and 1×4 wall show continuous geometry across bezels | Not achievable here: headless slices only, no hardware |

## 7. Evidence index

In `/var/home/oak/.local/share/tablet-wall-ai/readiness-program/baseline/`:

| File | Shows |
| --- | --- |
| `0ff56e3-01-desktop-1440x1000-initial.png` | Desktop shell, four online tablets, empty wall |
| `0ff56e3-02-desktop-content-picker.png` | Image library with the one curated asset; no upload UI |
| `0ff56e3-03-desktop-image-selected-on-wall.png` | Scene applied; "Already on the wall" |
| `0ff56e3-04-desktop-protocol-1-warning.png` | Named protocol-1 image warning (F3) |
| `0ff56e3-05-desktop-2x2.png` | 2×2 arrangement, capability-unknown alert, shape warning |
| `0ff56e3-05-tablet-<device>-2x2.png` | Per-tablet slice for 2×2 (four files) |
| `0ff56e3-06-desktop-1x4.png` | 1×4 arrangement |
| `0ff56e3-06-tablet-<device>-1x4.png` | Per-tablet slice for 1×4 (four files) |
| `0ff56e3-07-mobile-390x844-wall.png` | Mobile wall, alert, cramped map |
| `0ff56e3-08-mobile-390x844-content.png` | Mobile content picker |
| `0ff56e3-09-mobile-390x844-layout.png` | Mobile layout controls |
| `0ff56e3-10-mobile-390x844-tablets.png` | Mobile roster |
| `0ff56e3-11-mobile-390x844-focus.png` | Mobile focus after tab walk |
| `0ff56e3-12-physical-initial.png` | Physical console, draft not applied |
| `0ff56e3-13-physical-tablet-selected.png` | Device selected, no slot yet |
| `0ff56e3-14-physical-calibration-saved.png` | Calibration r2 saved |
| `0ff56e3-15-physical-slot-draft.png` | Slot added, "Unapplied changes" |
| `0ff56e3-16-physical-draft-dirty.png` | Nudge applied to draft only |
| `0ff56e3-17-physical-applied.png` | Committed physical layout |
| `0ff56e3-18-tablet-<device>-physical-applied.png` | Three tablets now "Not placed" (four files) |
| `0ff56e3-19-legacy-controller-on-physical-wall.png` | Silent stale logical console |
| `0ff56e3-20-desktop-focus-walk.png` | Skip link focus ring |
| `0ff56e3-21-physical-selection-check.png` | Selection chip follows the clicked device |
| `0ff56e3-22-desktop-fit-pack-2col.png` | "Fits tablets" + Pack 2 columns keeps the shape mismatch |
| `0ff56e3-run.json` | Console, response, socket, phase, audit, focus data for the run |
| `0ff56e3-geometry.json` | Measured boxes at 1440 × 1000, 390 × 844, physical |
| `0ff56e3-selection-check.json` | Device/profile/viewport correspondence per row |
| `superseded-drift-abb9c42/` | First attempt against the moving tree; not evidence |

## 8. Limits

- Headless Chromium only; no Safari/WebKit, no real GPU compositor, no browser
  chrome insets, no OS display scaling.
- No real tablet, bezel, ruler, camera, or light sensor. Wake lock reported
  `denied` and the consoles showed four wake-lock warnings; that is headless
  behaviour, not a wall-health finding.
- Uploads were not enabled, so the upload and media-library paths beyond the
  disabled state were not exercised.
- Drag-and-drop, tile preview, saved layout/scene recall, playback, and video
  were not exercised in this baseline. Their absence here is not a pass.
- The server ran on loopback with a temporary database; no restart, reconnection, or concurrent-writer behaviour was tested.
- Screenshots show the tablet identity HUD for the first ~5 s after connect; it
  overlays the top-left of the image in the tablet captures.
