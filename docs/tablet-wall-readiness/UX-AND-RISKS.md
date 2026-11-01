# UX, information architecture, and risk contract — image-first tablet wall

Status: design contract for implementation. Not a claim that any of it is built.
Scope: the still-image wall only. Playback, video, mirror, and independent modes are
out of scope except where they must be demoted or fenced.
Reviewed source: `0ff56e3`. Every "current" statement below cites the file and line in
that checkout. Anything marked **[P]** is a proposal.

Integration decisions on 2026-11-01: the wire states are `displayed` and
`blocked`, as defined in ARCHITECTURE.md; the UI can use "Showing" and "Needs
calibration" where appropriate. The four primary tabs are Wall, Tablets,
Content, and System; layout controls belong inside Wall. Independent operator
diagnostics and exact tablet sign-in routes have since landed. Historical
source findings below describe the assessed baseline.

This document owns one deliverable: the operator experience, the state vocabulary, the
risk guards, and the acceptance evidence. It does not authorize production edits, live
database access, firewall or network changes, or hardware claims.

Evidence labels:

- **[S]** read in current source at the cited location.
- **[A]** arithmetic on source constants, shown in the text.
- **[P]** proposed behavior.
- **[H]** hypothesis that needs a real device or a measured run.

No real iPad, Pixel C, Safari, HTTPS deployment, sleep/wake, or video behaviour was
observed for this document. Do not cite it as hardware validation.

---

## 0. Decisions at a glance

1. **The measured (physical) console is the one operator home.** `/controller/physical.html`
   stays the primary surface. It gains still-image control, per-tablet truth, and
   arrangement presets. The logical console becomes a labelled compatibility editor,
   never a second source of truth.
2. **One authoritative operator state.** The primary console must be able to say which
   layout kind is active, which image and fit are showing, which revision is committed,
   and what each tablet is displaying. Today it cannot: the v3 config has no scene
   (`main.py:1867-1902`), and `PUT /scene` on a physical wall returns a synthetic
   2000×1000 colour wall (`tabletwall/state.py:289-298`).
3. **Transport and content are separate axes.** "Online" is not a health verdict.
   A tablet is `online` or `offline`; its content is `unplaced`, `hidden`, `calblocked`,
   `loading`, `painted`, `failed`, or `unknown`. One badge per tablet derives from both.
4. **A render acknowledgement is the only proof of image health.** It proves the
   application attempted and completed a paint, not that a person sees a lit panel.
5. **Presets are 2×2 and 1×4 only**, in display-number order, edge-to-edge bodies,
   one atomic layout write, preview before Apply, no implicit release of an offline
   reservation.
6. **Fill and Fit whole image are global and explicit.** Fill (cover) stays the default
   for a calibrated wall. Fit whole image adds letterbox bars and is remembered per
   content item. Never fit each tablet independently.
7. **Mount angle is an operator fact, not a browser fact.** Panel orientation, mount
   angle, browser orientation, and launch mode are four different things on screen and
   in the data.
8. **Detection is a hint; confirmation is a decision.** A model match never silently
   becomes a physical scale, and a model-derived plan is never shown as "ok".
9. **Identity actions are separate verbs**: Identify, Rename, Remove from wall, Forget,
   Replace (rebind). Each states exactly what it keeps and what it destroys.
10. **QR carries the join address only.** It does not identify hardware and is not a
    credential. Approval and pairing are optional security layers with their own
    wording; neither is implied by scanning a code.
11. **HTTP hotspot mode is honest.** The supported launcher has no app login, no
    browser wake lock, and no uploads. Operator diagnostics remain available;
    the tablet listener cannot read them. Expected states read calm.
12. **No destructive switch is silent.** A logical↔physical switch always writes a named
    return point in the same commit and names it in the confirmation.

---

## 1. Jobs the console exists to serve

A person stands at the wall with four tablets on a table, a laptop, and one image.

| Job | Success looks like | Today's gap |
| --- | --- | --- |
| Start | The console gives the tablet address, the Wi-Fi name, and readiness in one screen | Address is printed by the launcher; no QR, no readiness block |
| Join | Each tablet shows a number; the operator sees a new row and confirms the model | Open registration; auto-matched model applied silently (`main.py:961-972`) |
| Identify | One tablet flashes its number while the wall content is untouched | No Identify command exists |
| Arrange | 2×2 or 1×4 in number order, seamless, one Apply | Bulk arrange orders by UUID and hard-codes `mount_angle: 0` (`frontend/controller/physical.js:3095-3112`); no presets |
| Show | One image, Fill or Fit whole image, with the crop visible before commit | Physical console has no still-image control; Content tab is playlist-only (`frontend/controller/physical.html:465-523`) |
| Confirm | Every tablet says "showing rev N" or names its failure | No static render ack; online is inferred as healthy |
| Switch | Recall 2×2 / 1×4 without losing the other arrangement | Logical recall from physical writes no backup (`main.py:2079-2091`) |
| Recover | Offline, failed, and calibration-blocked each have one next action | Physical has no Forget; diagnostics fail closed in the supported deployment |
| Stop | Blank the wall, keep state, leave a known recovery path | Blackout exists as colour content; no single "Blank wall" action |

The wall is an output. Do not add editing controls to the tablet. The controller is the
only editing surface, and one person should be able to finish the eight steps above
without reading a document.

---

## 2. Information architecture

### 2.1 One primary console, one compatibility editor

| Surface | Role | Rule |
| --- | --- | --- |
| `/controller/physical.html` — **Wall console** | Primary operator console for every wall | Owns content, status, arrangements, tablets, health |
| `/controller/` — **Logical editor (compatibility)** | Edit legacy unit-based layouts and recall old logical arrangements | Read-only when the active wall is physical, with a banner and a link to the Wall console. Never renders a plausible substitute wall |
| `/client/` | Tablet output | No editing UI; transient identity and recovery only |
| `/client/` ruler mode (`ruler.js`) | Advanced measurement | Reached from the selected tablet, behind a disclosure |

The current split is the root UX defect: the two pages disagree about the active wall,
and each holds a task the other needs. The fix is not a third page. It is one primary
page that can read and write both layout kinds' *content*, plus an explicitly labelled
legacy editor for logical *geometry*.

Current behavior that makes this mandatory **[S]**:

- `GET /wall` is fenced while physical (`main.py:1183-1186`, `main.py:1678-1684`).
- A newly connected legacy controller receives a synthetic 2000×1000 colour wall
  (`tabletwall/state.py:289-298`).
- `PUT /scene` succeeds on a physical wall but returns that synthetic envelope
  (`main.py:1235-1275`).
- The physical console never calls `PUT /scene` (no `/scene` in `physical*.js`).
- Applying a physical layout closes protocol-2 controller sockets
  (`main.py:2061-2069`).

### 2.2 Screen map

The stage is always visible. The rail holds four tasks. Do not add a fifth top-level
tab; the saved arrangements move into the Wall task where they are used.

```
Wall console
├─ Stage (always visible)
│  ├─ active layout chip: "Measured wall (mm)" | "Logical wall (compatibility)"
│  ├─ committed revision · session · ETag (details only)
│  ├─ image underlay: source dimmed, panel areas bright, bezels/gaps hatched
│  ├─ per-slot badges (state model, §3)
│  └─ draft bar: Undo · Redo · "Unapplied changes" · Apply layout · Cancel
├─ Rail: Wall
│  ├─ Show: image picker, Fill / Fit whole image, Show on wall, Restore previous
│  ├─ Arrangements: 2×2 preset, 1×4 preset, ordered tablet list, Preview, Apply
│  ├─ Saved arrangements: save committed, recall, rename, delete, "auto backup" tag
│  └─ Show status: "3 of 4 showing · 1 needs calibration"
├─ Rail: Tablets
│  ├─ roster list (number, label, model trust, transport, content state, wake warning)
│  ├─ selected tablet inspector (mount angle, nudges, rotate, identify, rename)
│  └─ lifecycle: Remove from wall · Forget tablet · Replace tablet
├─ Rail: Content
│  ├─ still images (curated + uploaded, with dimensions and aspect)
│  ├─ warnings: crop, upscale, missing file
│  └─ Experimental (collapsed): playlist and playback, labelled software-only
└─ Rail: System
   ├─ readiness card (§9)
   ├─ wall bounds and advanced sizing (fixed size, fit to tablets, padding)
   ├─ profile/calibration forms, ruler entry, uncertainty
   ├─ diagnostics, backup age, logs
   ├─ security mode and origin
   └─ "Open logical editor (compatibility)" when a logical layout is active
```

Current tabs are Show / Tablet / Content / System (`frontend/controller/physical.html:89-92`).
Renaming "Tablet" to "Tablets" and "Show" to "Wall" is cosmetic; the substantive moves
are: still controls into Wall, arrangements out of System, playback collapsed.

### 2.3 Stage anatomy

The stage must answer four questions without opening a panel:

1. **What will the audience see?** The image, cropped by the current fit, under the
   panel mask — not coloured rectangles alone. Neither controller stage draws image
   content today, so this preview must be built. Reuse the client's wall-rectangle
   derivation (`frontend/client/view.js`, `client.js` `drawWallImage`) so the preview and
   the tablets agree; do not write a third geometry.
2. **Which parts are lost?** Outside-wall source (dimmed), bezel and gap areas
   (hatched), and fit bars (flat letterbox colour). The stage must distinguish "cropped
   away by Fill" from "hidden behind a bezel". They have different fixes.
3. **Which tablet is which?** Each slot carries its number and label. Selected state is
   outline plus a text chip, never colour alone.
4. **Is the draft safe?** A draft flag that says "matches the committed layout" or
   "unapplied changes", and an Apply that is disabled when it would be destructive.

### 2.4 Task contents

**Wall → Show.** One image card: thumbnail, name, intrinsic size, aspect, source pixels
per tablet (computed), fit radio, predicted crop, and a single "Show on wall" button.
After commit: "Showing wall-grid.png · Fill · rev 12" plus "Restore previous".
Content changes are one atomic write and do not create a layout draft.

**Wall → Arrangements.** Preset buttons, ordered tablet list, orientation choice,
gap field (default 0), preview, Apply. Saved arrangements appear here, with the
automatic backups visually separated and labelled `auto`.

**Tablets.** Roster and inspector. The list is sorted by display number, then label,
then id. Each row: `#3 Upper left · iPad Air 2 (confirmed) · Showing rev 12` or
`#4 Right · Pixel C (estimated ±3 mm) · Offline 42 s · reserved`. Actions are verbs, not
icons alone.

**Content.** A still library that works with uploads disabled (curated folder plus a
Refresh action), and with uploads enabled when the deployment supports it. Fit belongs
to the scene, so changing fit is a content action, not an arrangement action.
Experimental playback is a collapsed disclosure with one sentence: "Software evidence
only. Not validated on tablets." No video item is promoted on the primary path.

**System.** Readiness, bounds, measurement, diagnostics, backup, logs, security mode,
and the legacy-editor link. Advanced fields stay behind disclosures; the primary journey
never requires millimetres.

### 2.5 Logical compatibility contract

When `layout.kind === "logical"`:

- The primary console shows a neutral chip: **"Logical wall (compatibility) — unit-based,
  not measured."**
- It may show content and change content (`PUT /scene` is not fenced).
- It may preview the logical placements, but arrangement edits route to the legacy
  editor through one explicit button. Do not silently reinterpret 2000×1000 units as
  millimetres.
- The stage names the conversion risk before any "Convert to measured wall" draft:
  "Logical units are not millimetres. Converting will replace this layout; the previous
  layout will be saved as `Before physical …`."

When `layout.kind === "physical"`:

- The legacy page loads a banner: **"This wall is measured. Open the Wall console."**
  It may show the committed scene read-only and link onward. It must not present an
  editable neutral wall, and it must not accept layout writes (the server already
  fences them).
- A protocol-2 controller socket is closed on apply; the page must handle that close
  with the banner, not a reconnect loop.

### 2.6 What leaves the primary path

- Playback transport (Start/Pause/Stop) from the top bar into Content → Experimental.
- Playlist as the Content tab's main body; it becomes the experimental section.
- Per-tablet legacy "Tile" with 3×2/20-unit defaults
  (`frontend/controller/index.html:463-465`) from the primary flow; it stays in the
  logical editor until that editor is retired.
- Raw UUIDs, ETags, revisions, and profile revision numbers from first-level copy.
  They remain available in Details for support.

### 2.7 Content-first rules

1. The first screen is the stage with the current image, not a form.
2. At most one primary button is visible per task: "Show on wall", "Apply layout",
   "Identify", "Save arrangement".
3. Empty states name the next action: "No image selected. Choose one in Content."
4. Warnings are specific and actionable: name the tablet, the reason, and one next step.
5. No spinner persists without a timeout and an escape action.
6. Normal, expected states are neutral. Offline is not an error; it is a reservation.

---

## 3. Per-tablet state model

### 3.1 Two axes

```
transport : online | offline
content   : unplaced | hidden | calblocked | loading | painted | failed | unknown
modifier  : none | stale
```

One badge is derived from both. The rule is: **transport decides what you can do;
content decides what the audience sees.** A single "online" light must never stand in
for image health.

`orphaned` is a slot condition, not a tablet state: a saved slot names a device that is
no longer in the roster. Show it on the slot, in the arrangement, and in the saved-layout
preview — not in the tablet list, because there is no tablet to list.

Row order chooses the badge, not what the detail line may say. The detail line always
shows both axes, for example "Excluded from show · offline 42 s" or "Not on the wall ·
online". A badge never hides the fact that a tablet is offline.

### 3.2 Derivation order

Evaluate in this order and stop at the first match; later rows apply only when earlier
ones do not.

| # | Condition | State | Badge | Primary action |
| --- | --- | --- | --- | --- |
| 1 | Device id is referenced by a slot but absent from the roster | `orphaned` | "Missing tablet · slot reserved" | Replace tablet, or Remove from wall |
| 2 | No slot/placement in the active layout | `unplaced` | "Not on the wall" | Add to wall / Arrange |
| 3 | In layout, `participating === false` or excluded from the shown set | `hidden` | "Excluded from show" | Include in show |
| 4 | Transport offline | `offline` | "Offline · 42 s" + last content sentence | Wake tablet / Replace tablet / Release spot |
| 5 | Server withheld a physical plan for a reason | `calblocked` | "Needs calibration" + reason | Fix calibration / rotate / return to fullscreen |
| 6 | No acknowledgement mechanism (protocol < 3 or no ack support) | `unknown` | "No confirmation · old client" | Update client / check manually |
| 7 | Render sent, no ack yet, age < 10 s | `loading` | "Sending image…" | Wait; Retry after timeout |
| 8 | Ack is `failed`, or the client reported a load/decode failure | `failed` | "Image failed · decode" | Retry image / choose another image |
| 9 | Ack is `painted`, and its render sequence is the newest sent, but its revision or asset is older than current | `painted` + `stale` | "Showing rev 11 · wall is rev 12" | Wait, or Retry image |
| 10 | Ack is `painted` for the current generation, revision, asset, and mapping | `painted` | "Showing rev 12 · 3 s ago" | None |
| 11 | Render sent, no ack, age ≥ 10 s | `unknown` | "No confirmation · 12 s" | Retry image / Reconnect |

Notes:

- **Joined is an event, not a badge.** "Joined #4" is a one-shot confirmation at
  registration; the durable state is `unplaced` until a slot exists.
- **Asleep is not a state.** A sleeping panel looks `offline` after the 15 s heartbeat
  window (`tabletwall/protocol.py:13-14`). Do not invent an "asleep" claim; the page
  cannot see the screen.
- **Blank/blackout is content.** A black colour scene is `painted` content, not
  `hidden`. Say "Blackout applied", not "Hidden".
- **A stale ack still counts as painted** for what the audience sees, but the header
  must not count it as current.

### 3.3 What `calblocked` means

The server already refuses to guess a physical plan and sends a reason
(`tabletwall/state.py:392-424`). Surface the reason verbatim in operator language:

| Server reason | Operator text | Next action |
| --- | --- | --- |
| `no physical slot` | "Not in this arrangement" | Add to wall |
| `no measured profile or calibration` | "No measurements yet" | Confirm model or measure |
| `calibration does not match the slot profile` | "Measurements changed since this arrangement was saved" | Re-pin or re-measure |
| `viewport does not match the calibration` | "Browser size, rotation, or zoom changed" | Return to the calibrated mode |
| `physical plans currently require image content` | "Measured walls need an image" | Choose an image |
| `image dimensions are unknown` | "Image size not recorded" | Re-select the image |

`calblocked` is not a failure of the tablet. It is the system correctly declining to
claim a physical mapping it cannot justify. Tone: neutral, with a fix.

### 3.4 Header count

One line under the stage:

- `4 of 4 showing · rev 12`
- `3 of 4 showing · 1 needs calibration`
- `2 of 4 showing · 1 sending · 1 offline (reserved)`
- `0 of 4 showing · no image selected`

"Showing" counts only current `painted` acks. Never count `online` as showing. Never
count `unknown` as showing. If no ack mechanism exists at all, write
`4 online · image confirmation unavailable` and say so once in System.

### 3.5 A pure derivation function

Put the table above in one pure function so it can be tested without a DOM:

```
WallState.deriveTabletState({
  device, slot, activeLayout, content, ack, nowMs
}) -> {
  transport, content, modifier, reason,
  confirmedRevision, confirmedAsset, sinceMs
}
```

It must be deterministic and must not read the clock except through `nowMs`. The console
renders the result; it does not re-derive state in three places. This is the smallest
change that makes the vocabulary trustworthy.

---

## 4. Arrangements: 2×2 and 1×4

### 4.1 Preset defaults

| Preset | Rows × columns | Intended bodies | Gap | Sizing | Order |
| --- | --- | --- | --- | --- | --- |
| **2 × 2** | 2 × 2 | Landscape by default | 0 mm between bodies | Fit wall to tablets, padding 0 | Display number, then label, then id |
| **1 × 4** | 1 row × 4 columns | Landscape by default | 0 mm | Fit wall to tablets, padding 0 | Same |

The bezel is part of each body, so "gap 0" means body edges touch; visible panels are
separated by the real bezels. Do not add a synthetic gap to imitate bezels. A gap field
exists only for a deliberate spacer between groups, and its default is 0.

Do not derive the grid from the wall's current aspect. Derive it from the selected
tablets' measured bodies, then set the wall bounds to enclose them. That is what
"Fit wall to tablets" already does (`tabletwall/sizing.py`, `physical-sizing.js`).

### 4.2 Selection and ordering

- Default selection: tablets already in the arrangement, plus online unplaced tablets,
  in number order.
- Offline placed tablets are listed separately as "reserved". They are included by
  default so their spot survives; the preview marks them "offline · reserved".
- Drag to reorder, plus explicit "Move earlier" / "Move later" buttons for keyboard and
  touch. Number order is the default, not a lock.
- If the selected count exceeds the preset capacity, disable the preset and say why:
  "2×2 holds 4 tablets; 5 are selected. Exclude one or release a reserved spot."
  Never drop a tablet silently.

### 4.3 Orientation and mount

The preset asks one question: **"How are the tablet bodies mounted?"** with
`Landscape` (default) and `Portrait`. This sets `mount_angle` per slot, not the browser.
Browser orientation is a separate reported fact used only to warn.

- Landscape: 90° for every selected tablet.
- Portrait: the model's `portrait_angle` (0° for the Air 2, 270° for the Pixel C per
  `tabletwall/tablet_models.py:9-12`), or 0° for an unknown model.
- A per-tablet "Rotate 180°" override handles camera position or an upside-down mount.
  The preset itself is deterministic; it never guesses from the browser.
- Per-tablet mount angle stays editable in the inspector.
- If a tablet's live viewport orientation disagrees with its slot, the stage flags
  "Browser is portrait; slot is landscape" and offers "Match mount to tablet". It never
  flips the slot by itself.

The current bulk arrange hard-codes `mount_angle: 0` and sorts by UUID
(`frontend/controller/physical.js:3099-3106`). Both are wrong for the advertised
quick path. Use the existing `compareDeviceIds` helper (`physical.js:652-668`), which is
already used elsewhere in the same file.

### 4.4 Preview before Apply

The preview must show:

- Every selected body with `#N` and label.
- Panel area bright, bezel hatched, any uncovered wall area cross-hatched.
- The image under the arrangement with the current fit.
- Per-slot state badges from §3, including "offline · reserved".
- A summary: "4 tablets · 2 rows × 2 columns · bodies 238 × 168 mm · wall 476 × 336 mm ·
  gap 0 mm · order #1 #2 / #3 #4" (iPad Air 2 landscape, body includes bezels).
- A warning when any body overlaps another, when a slot has no profile, or when the
  grid leaves a cell empty.

Apply is the only commit. A preset click never writes.

### 4.5 Apply is one write

`PUT /api/v3/layout` already replaces bounds and all slots atomically and requires
`If-Match` (`main.py:1912`, `main.py:2011-2071`). Use exactly that:

- One request, all slots, one revision bump, one broadcast, one repaint cycle.
- `412` → conflict panel. Nothing applied. Reload the config, discard the stale draft,
  re-preview. Never auto-retry.
- `422` → field error. Nothing applied. Keep the draft so the operator can fix it.
- `409`/`422` from a slot-provenance check → name the slot and the missing revision.
- The server also refuses two bodies that overlap in the wall plane, naming both. Physical
  bodies cannot occupy the same space; catching it at Apply is cheaper than diagnosing it
  on glass. Check existing fixtures for intentional overlap before enabling this rule.

Do not use the legacy per-tablet `PUT /devices/{id}/placement` loop
(`frontend/controller/controller-stage.js:996-1007`) for presets. It produced four
commits and four repaints for four tablets, and a mid-loop failure leaves a partial
wall. Keep that code only inside the compatibility editor.

### 4.6 Empty apply is refused

Current source state **[S]**:

- On a logical wall, the physical draft is seeded from logical width/height interpreted
  as millimetres with `slots: {}` (`frontend/controller/physical.js:557-580`).
- `Apply` is enabled when `sizing.mode !== "tablets"` and the draft is not dirty, because
  the disable condition only blocks a clean *physical* layout
  (`frontend/controller/physical.js:1216-1217`).
- The server accepts an empty `slots` object (`main.py:2011-2071` has no zero-slot guard).
- A device with no slot receives `plan: null` and "no physical slot"
  (`tabletwall/state.py:404-406`), so every tablet would show its
  `NEEDS CALIBRATION` panel.

One click on a freshly opened console can therefore replace a working logical image wall
with a measured wall that shows nothing. This is the highest-severity UX defect in the
current tree.

Contract **[P]**:

1. The client disables Apply when the draft has zero slots, with the reason
   "This arrangement has no tablets. Applying would blank every screen."
2. The server rejects `PUT /api/v3/layout` with `422` when `slots` is empty. Clearing a
   wall is a deliberate `DELETE` of each slot, not an apply.
3. Converting a logical wall to measured is an explicit action with its own
   confirmation and its own draft. It is never the default state of the page.
4. The conversion confirmation names the backup it will create.

### 4.7 Switching arrangements

- Switching layout never changes content. Content is a separate scene; keep it.
- Before a cross-kind recall (logical↔physical), write a generated backup of the
  current layout in the same commit, under a visible name such as
  `Before recall 1×4 · 2026-11-01 14:02`. If the backup cannot be written, refuse the
  switch.
- The recall preview lists: tablets missing from the target, tablets whose model or
  calibration revision differs, offline tablets that will be reserved, and the content
  that will remain.
- After recall, the header shows the new arrangement and the same image.
- Offer "Undo switch" while the previous committed layout is still the generated backup.

Today only logical→physical writes a backup (`main.py:2055-2058`); the reverse recall
does not (`main.py:2079-2091`). That is a data-loss path, not a cosmetic gap.

### 4.8 Saved arrangements

Keep saved layouts as snapshots. Do not collapse layout and content into one "show"
object; operators need to change one without the other. Offer a separate
"Save as presentation" only after presets and recall are dependable.

---

## 5. Fit: Fill the wall vs Fit the whole image

### 5.1 Contract

One wall-wide fit, chosen in Content, persisted with the scene:

| Choice | Semantics | Result | When to use |
| --- | --- | --- | --- |
| **Fill the wall** (`cover`, current behavior) | Scale the source so it covers the wall bounds; crop the overflow evenly on two edges | No bars; image edges may be lost | Continuous photographic wall, source aspect close to wall aspect |
| **Fit the whole image** (`contain`) | Scale the source so the entire image fits inside the wall bounds; letterbox the remainder | Every source pixel is inside the wall; bars appear | Posters, text, diagrams, any content with a border |

Rules:

1. The fit is global to the wall. Every tablet derives its slice from the same wall
   rectangle. Never fit per tablet; that breaks continuity.
2. `Fit whole image` does **not** recover pixels hidden behind bezels or gaps. Say so:
   "Fit keeps the whole image inside the wall. Bezels and gaps still cover the seams."
3. The letterbox colour is explicit scene data with a safe default (black). Do not
   inherit the page background; a white page must not produce white bars by accident.
4. Fill remains the default for a calibrated wall. Fit is a deliberate choice and is
   remembered per content item.
5. Fit is persisted and returned in the operator state. Today the API accepts only
   `cover` (`tabletwall/protocol.py:61`, `main.py:343-345`), even though
   `geometry.fit_matrix` already implements both (`tabletwall/geometry.py:131-161`) and
   the physical render plan already forwards the scene's fit
   (`tabletwall/state.py:425-434`). The measured path is therefore closer to contain
   than the API suggests; the logical client still rejects any fit but cover
   (`frontend/client/client.js:1060-1070`).
6. Playback plans must use the same fit or be labelled as ignoring it. Do not let the
   experimental path silently disagree with the still path.

### 5.2 Preview arithmetic

The preview must show the numbers, not just a picture:

```
source aspect  = source_width / source_height
wall aspect    = bounds_width / bounds_height
Fill visible   = min(1, wall_aspect / source_aspect)  horizontally
               = min(1, source_aspect / wall_aspect)  vertically
Fit bar area   = 1 - (visible area with contain)
```

Example **[A]**, using an iPad Air 2 landscape body (238.2 × 167.8 mm including
bezels; active area 196 × 146.75 mm):

- 2×2 wall: 476.4 × 335.6 mm → aspect 1.42. A 4:3 image (1.33) under Fill keeps
  `1.333 / 1.42 = 94%` of its height; about 6% is cropped.
- 1×4 wall: 952.8 × 167.8 mm → aspect 5.68. The same 4:3 image under Fill keeps
  `1.333 / 5.68 = 23%` of its height; **about 76% is cropped**.
  The 2000×745 image in the reported saved wall is a different case (aspect 2.68), but it
  still loses roughly half its height at that wall aspect.
- The same 4:3 poster under Fit is drawn 223.7 × 167.8 mm: **about 24% of the wall
  width**, with bars on both sides. It is smaller, but complete.

Warnings:

- Fill: "Fill hides 76% of this image's height on this wall." Show it whenever the
  visible fraction is below 0.85.
- Fit: "Fit adds bars. The image will be 24% of the wall width." Show the drawn size.
- Upscale: "Each tablet gets about 500 source pixels across for a 2048-pixel panel
  (≈4× upscale)." Compute it; do not guess.

### 5.3 Copy

- Radio: **Fill the wall (crops)** / **Fit the whole image (adds bars)**.
- Status: "Showing poster.png · Fit whole image · rev 12".
- Do not call Fit "letterbox" in the primary UI; call it what it does.

### 5.4 Edge cases

- Source larger than needed: still one global scale; no per-device downscale.
- Source smaller than the wall: warn about upscale; do not silently blur.
- Alpha PNG: paint an opaque underlay first (the client already does for Fill).
- Image removed or hash mismatch: `failed` with "Image missing on the server", not a
  blank wall.
- Changing fit while tablets are offline: commit once; offline tablets repaint on
  reconnect and their ack must carry the current revision.

---

## 6. Panel, mount, browser, launch mode

These are four independent facts. Conflating them produces the kind of mismatch the
operator reported in a real 2×2, where a portrait Pixel C sat in a landscape footprint
(user-reported; not re-observed here).

| Fact | Source | Changes when | Used for |
| --- | --- | --- | --- |
| **Panel orientation** | Model record (`portrait_angle`, active width/height) | Hardware is different | Which side is "up" in the body |
| **Mount angle** | Operator, in the arrangement | Someone physically re-hangs the tablet | Slot geometry: where the body sits and which way it faces |
| **Browser orientation** | Tablet viewport report (`orientation` 0/90/180/270) | OS rotation, browser UI, tab change | Calibration match check only |
| **Launch mode** | Viewport report (`tab`/`fullscreen`/`standalone`) | User enters/leaves fullscreen, adds to Home Screen | Browser inset assumption and calibration validity |

Rules:

1. The preset sets mount angle from the operator's `Landscape`/`Portrait` choice.
2. The browser never rotates a slot. If the reported viewport disagrees, the slot is
   `calblocked` with "Browser is portrait; slot is landscape" and an explicit
   "Match mount to tablet" action.
3. Fullscreen is a gesture, not a server command. The controller can ask; the tablet
   must accept. Never claim remote fullscreen.
4. Launch mode is part of the calibration signature. A model-derived plan in `tab` mode
   assumes a centred inset (`tabletwall/tablet_models.py:117-131`); that is an
   approximation, not a measurement. Label it.
5. Rotating a tablet is an operator action with a preview: "This rotates the body. The
   image stays in place." Do not rotate content to compensate.
6. The inspector shows all four facts in one block, so an operator can see which one is
   wrong.

Pinch zoom:

- The client detects `visualViewport.scale !== 1` and already treats a changed viewport
  as a mapping change (`frontend/client/client.js:2286`, `:2300`). In a physical wall that
  becomes `calblocked` with "Browser zoom changed".
- In a logical wall, zoom changes the CSS pixel size and therefore the apparent scale
  without a fence. Surface "Browser is zoomed (1.3×)" in the tablet's state and on the
  client banner. Do not disable pinch zoom on the controller — it is an accessibility
  feature. On the tablet, a fence plus "reload to reset" is enough; do not fight the
  user's browser.
- Double-tap zoom on the tablet should be prevented by the kiosk configuration, not by
  removing user scaling. Record it as an OS/kiosk instruction, not a software claim.

---

## 7. Model provenance and uncertainty

A match is a hint about screen geometry. It is not an identity, a credential, or proof
of the physical panel.

Current behavior **[S]**:

- `match()` compares CSS screen size, DPR, and platform (`tabletwall/tablet_models.py:23-32`).
- Registration auto-assigns a unique match (`main.py:961-972`).
- Built-ins contain one iOS model, so "unique among built-ins" is not unique among
  iPads (`tabletwall/tablet_models.py:8-15`). Several iPad models share 768×1024 at DPR 2.
- The profile records `provenance="tablet-model"` and the calibration records an
  uncertainty, but the console shows only `calib rN saved` with an `ok` tone
  (`frontend/controller/physical.js:501-514`).

Target vocabulary, shown as a badge beside the tablet name:

| Provenance | Meaning | Badge | Tone |
| --- | --- | --- | --- |
| `detected` | Signature suggestion, not accepted | "iPad Air 2 · suggested" | info |
| `confirmed` | Operator accepted the model for this tablet | "iPad Air 2 · confirmed" | neutral |
| `approximate` | Scale derived from the model, ± uncertainty | "Model estimate · ±3 mm" | warn |
| `measured` | Ruler measurement on this viewport | "Ruler measured · ±0.7 mm" | ok |
| `physically-checked` | A seam check was recorded for this arrangement | "Checked · 2 mm target" | ok |

Rules:

1. No physical plan before confirmation. An unconfirmed tablet may join, be identified,
   and appear in a logical wall; it cannot be given a measured slot.
2. "Detected" never says "this is an iPad Air 2". It says "Looks like an iPad Air 2.
   Confirm?"
3. Model-derived plans show their uncertainty everywhere the plan matters: inspector,
   arrangement summary, seam report. Do not print `ok` for an estimate.
4. Changing the model is an explicit apply with a preview of affected slots and saved
   arrangements. It never rewrites a saved revision.
5. Rebind may copy model history, but it must not silently promote an estimate to
   measured.
6. Do not grow the built-in model list to avoid confirmation. More models do not make a
   signature an identity.

---

## 8. Identity lifecycle

### 8.1 Verbs and consequences

| Action | What it does | What it keeps | Confirmation | Danger |
| --- | --- | --- | --- | --- |
| **Identify** | Shows a large `#N` and label on one tablet for 10 s, then restores the scene | Everything | None | Fails visibly if the tablet is offline or asleep |
| **Rename** | Sets a durable operator label ("Upper left") | Number, id, history | None | Labels are not unique keys |
| **Approve join** *(optional)* | Admits a newly registered tablet | Device record | "Allow #5 to join?" | Open registration remains the default on a trusted hotspot |
| **Pair** *(optional)* | Issues a revocable per-tablet credential | Device record and credential | "Pair this tablet?" | Requires TLS or an explicitly accepted local boundary |
| **Remove from wall** | Deletes the slot/placement | Device, number, measurements, saved arrangements | "Remove #3 from this arrangement?" | Audience sees one fewer screen until rearranged |
| **Forget** | Deletes the roster entry and device history, and optionally its slot | Saved arrangements (named as affected) | Type the number or name | The tablet returns as new; a kept slot becomes orphaned |
| **Replace (rebind)** | Hands an old offline id's slot, number, and history to a new id | Saved arrangements only if healed | Preview of moved slot, number, and affected arrangements | Refuses if the old id is online or the new id is placed |

Semantics that must hold:

- **Remove ≠ Forget.** Remove is an arrangement edit. Forget is roster cleanup. Never
  label both "Delete".
- **Forget works in any layout kind.** Today `DELETE /devices/{id}` is fenced to logical
  (`main.py:1029-1031`, `main.py:1678-1684`) and the physical console has no Forget
  action. That is a lifecycle hole, not a preference.
- **Forget refuses while the tablet is online**, then offers "Remove from wall first" or
  "Disconnect the tablet".
- **Forget lists what it will break**: "Saved arrangement `2×2 lobby` references this
  tablet. It will recall with a reserved empty spot."
- **Forget offers to remove the current slot**, default on, so cleanup does not leave an
  orphaned hole. Saved arrangements are still named separately; forgetting does not
  silently rewrite them.
- **Identify is not a scene change.** It must not bump the wall revision, change the
  scene, or leave a stale overlay.

### 8.2 Replace (rebind) contract

Current behavior is useful and should be kept: the old id must be offline, the new id
must not be placed, and the display number must be free (`main.py:1074-1096`). The
transaction moves the slot, number, and display records (`main.py:1101-1146`).

Current limitation: "Saved layouts keep naming the old id; recall one and save it again"
(`main.py:1078-1081`). That makes the promised 2×2↔1×4 switch fragile after any origin
change or cleared site data.

Target **[P]**:

1. The Replace form requires an explicit choice: **"Same hardware, new browser
   identity"** or **"Different hardware"**. The first copies measurements; the second
   starts a new model confirmation.
2. A preview lists: the slot that moves, the number, the measurements copied, the saved
   arrangements that reference the old id, and any that cannot be updated.
3. On confirm, heal saved arrangements in the same operation, or report exactly which
   ones need manual repair. Never leave a silent broken snapshot.
4. The response lists changed arrangements by name; the console shows them.
5. Conflicts are refused, never partially applied: old online, new placed, number in
   use, missing slot, model mismatch requiring a decision.

### 8.3 Saved-layout conflict matrix

| Condition | Result | Operator text |
| --- | --- | --- |
| Old id online | `409` | "That tablet is still connected. Disconnect it before replacing." |
| New id already in a slot | `409` | "The new tablet is already on the wall. Remove it first." |
| Number already used | `409` | "Display number 3 is used by another tablet." |
| Saved layout references old id | heal or report | "Updated 2 arrangements; `Lobby` needs a manual repair." |
| Saved layout pins a profile revision | keep revision; copy with offset | "Measurements preserved at revision 4." |
| Old profile missing | proceed with no copy; warn | "No measurements to copy. The new tablet needs a model confirmation." |
| Rebind during playback | abort playback | "Playback stopped because a mapping changed." |

### 8.4 QR and join

- The QR encodes the tablet URL, for example `http://10.42.0.1:8080/client/`.
- The card also prints the URL as text and the SSID; a QR is a convenience, not the only
  path.
- Copy: **"Tablet address — open this on each tablet."** Under it: "Same Wi-Fi as this
  laptop. Not a login."
- A QR must not contain a device id, a session token, or a secret that is displayed in
  the room. If a one-time join code is added later, the code is short-lived, single-use,
  and exchanged over the server, not trusted because it was scanned.
- Never write "Scan to pair" unless a credential exchange actually happens. Scanning a
  URL proves nothing about the hardware or the person.

---

## 9. Readiness, calm HTTP, and OS-managed wake

### 9.1 Readiness card

One card at the top of System, also summarized in the header when not ready:

| Field | Values | Meaning |
| --- | --- | --- |
| Server | Ready / Starting / Failed | Process and database |
| Database | Writable / Read-only / Error | Can the wall persist a change? |
| Layout | Measured / Logical (compatibility) / None | Active geometry kind |
| Content | Image name + fit / Colour / None | What the wall should show |
| Tablets | `4 known · 3 online · 2 showing` | Roster and content truth |
| Confirmation | Available / Unavailable (old client) | Whether acks are possible |
| Backup | 2 days ago / Never / Unknown | Last verified backup |
| Origin | `http://10.42.0.1:8080` | Exact tablet origin |
| Security | Open hotspot / Auth on / Pairing on | What is actually enforced |
| Diagnostics | Available / Disabled in this mode | Why Field check is missing |

Three readiness levels, derived, never guessed:

- **Ready** — database writable, content present, every participating tablet `painted`
  for the current revision, backup within the policy window (default 7 days).
- **Degraded** — content present, but at least one tablet is `offline`, `loading`,
  `failed`, `unknown`, or `calblocked`; or the backup is stale; or all scales are
  model-derived.
- **Not ready** — no content, no placed tablets, a physical layout with zero slots, or a
  database that cannot be written.

The word "Ready" must not appear while any participating tablet has no confirmation.
Use "Degraded — 3 of 4 confirmed" instead.

### 9.2 Calm HTTP

The supported hotspot profile is unauthenticated HTTP with uploads disabled and the
operator bound to loopback. Say that plainly, once, where an operator will see it:

> **Local hotspot mode.** Tablets join this Wi-Fi and open the address above. There is no
> login in this mode, no browser wake lock, and no uploads. Diagnostics and the
> operator page are available only on this laptop. Use a private, trusted Wi-Fi
> network for this profile.

Rules:

- Do not show alarm-red for expected conditions: an offline reservation or an
  unsupported wake lock on HTTP.
- Do not advertise uploads, video, or remote access in this mode.
- The card says "Diagnostics available" for an admitted operator. Never enable
  uploads to make diagnostics work.
- The security mode is visible before the first destructive action, not buried in
  Settings.
- If authentication is enabled, the tablet origin must be able to serve the sign-in page
  or use a device credential. Today the tablet allowlist omits `/auth/login`
  (`deploy/tablet-routes.caddy:13-55`) while auth redirects there (`tabletwall/auth.py:139`).
  Until that composes, auth-on is not a supported tablet profile. Say so in the mode card.

### 9.3 Optional approval and pairing

- **Approval** (recommended for shared or semi-public hotspots): a new tablet waits as
  "Waiting for approval" and the console shows "New tablet #5 · iPad Air 2 suggested ·
  Allow / Deny". This is onboarding plus a guard, not authentication.
- **Pairing** (only when the threat model includes untrusted peers): server-issued,
  revocable per-tablet credential; reconnects silently; re-authorize after storage loss.
  Over plain HTTP, pairing does not provide confidentiality. Do not claim it does.
- Neither approval nor pairing proves which physical panel is which. Identify does that,
  with a human looking at the screen.
- The local operator boundary stays: tablet routes are an allowlist, the operator
  listener is loopback, and the proxy strips the operator header
  (`deploy/tablet-routes.caddy:9-55`). Do not expose the backend to the tablet network to
  make a feature easier.

### 9.4 OS-managed wake

The page cannot wake, unlock, or power a tablet. Sleep is an OS setting. Put the
instructions beside the join step and in the kiosk checklist, and never present wake as
a software feature.

| Platform | Operator setting | What the console must not claim |
| --- | --- | --- |
| iPad | Auto-Lock: Never, set while the tablet is on power; Guided Access on the client; Add to Home Screen for launch consistency; fixed brightness | "The wall wakes itself" |
| Android (Pixel C) | Stay awake while charging (developer option) or longest screen timeout; screen pinning/kiosk; disable battery optimisation for the browser; fixed brightness | "Remote wake" or "remote fullscreen" |
| Both | Keep on power; a smart plug is an OS-level power decision, not an app action | "The server can power the tablet" |

OS menus and policy controls change between versions, and managed devices may not expose
them. These are instructions to verify on the installed OS, not validated steps.

Honest state copy:

- `Offline · 42 s · spot reserved` — expected after sleep; not an error.
- `Identify unavailable while the tablet is offline` — disable the button.
- `Wake lock unavailable on this origin` — a warning with the reason, not a failure.
- `The page reloaded after wake` — if observed, record it as a finding. Do not assume it.

---

## 10. Security boundary and non-claims

Keep:

- Loopback-only operator listener; tablet route allowlist; exact-origin guard; bounded
  registration fields; one process per database; content-addressed asset bytes.
- Registration approval as an option, not a replacement for authentication.
- Backups that verify referenced bytes, and restore into new paths.

Do not claim:

- That a QR code identifies a tablet or a person.
- That a model signature is a hardware fingerprint.
- That a painted acknowledgement proves a lit screen or optical sync.
- That an HTTP hotspot is authenticated or safe on a shared network.
- That wake lock, fullscreen, or recovery after OS freeze is guaranteed by the page.
- That any video, optical, or millimetre-seam gate has passed.

Residual risks to state in the UI or docs:

- Any hotspot client can register; at `MAX_DEVICES = 512` an offline record can be
  evicted (`tabletwall/protocol.py:28`, `main.py:907-923`). On a private hotspot this is
  low; approval closes it.
- A peer that knows a device UUID can claim its socket. Pairing is the fix; a UUID is an
  identity key, not a credential.
- Display numbers are leased and can be recycled; a label plus number is the operator's
  stable handle, not a security principal.

---

## 11. Adversarial review: hazards and required guards

Severity is about audience-visible failure on a working wall, not code style.

### H1 — Empty physical apply blanks a working wall (critical)

**Trigger.** Open the Wall console while the wall is logical; press Apply
(`frontend/controller/physical.js:1216-1217`, `:557-580`). No slot is required by the
server (`main.py:2011-2071`).
**Worst outcome.** Every tablet loses its placement and shows `NEEDS CALIBRATION`; the
operator believes the image broke.
**Guard.** Client disables Apply at zero slots; server rejects empty `slots`; conversion
is a separate confirmed action.
**Test.** `test_v3.py`: empty physical layout returns 422 and the revision is unchanged;
node test: Apply disabled for a zero-slot draft seeded from a logical wall.

### H2 — A wrong model signature silently sets the physical scale (high)

**Trigger.** Another iPad reports 768×1024 at DPR 2; the only iOS built-in matches and is
auto-assigned (`tabletwall/tablet_models.py:8-32`, `main.py:961-972`).
**Worst outcome.** Every seam is scaled by the wrong panel size; the plan is presented as
valid.
**Guard.** Detect ≠ confirm; no physical slot before confirmation; model-derived plans
show ± uncertainty and never use the `ok` tone.
**Test.** `test_tablet_models.py`: a matching signature creates an `auto` assignment but
no physical slot is accepted until a confirmation flag exists; console state test maps
`provenance="tablet-model"` to "Model estimate", not "ok".

### H3 — Pinch zoom changes the mapping without an obvious cause (high)

**Trigger.** A person pinches the tablet page (or the browser restores a zoom level).
**Worst outcome.** Physical: `calblocked` with a reason the operator does not connect to
zoom. Logical: the image rescales and seams drift, with no fence.
**Guard.** Report zoom as its own reason; show "Browser zoom 1.3× · reload to reset" on
the tablet and in the roster; never disable controller zoom.
**Test.** `client_image.test.js`: a zoomed viewport reports the zoom reason; a logical
frame with a changed CSS viewport still derives the wall rectangle from wall coordinates,
and the console test maps it to a visible warning.

### H4 — Auth expiry strands an always-on wall (high)

**Trigger.** Auth is enabled; the 12-hour session cookie (`tabletwall/auth.py:20`) expires;
the tablet tries `POST /devices/register` and fails; the client retries forever.
**Worst outcome.** "Offline · retrying" forever with no sign-in action; the wall stays on
a stale image.
**Guard.** A tablet must not depend on an operator session: use a device credential, or
serve the login route on the tablet origin. On `401`, show "Sign in again" and stop silent
retry.
**Test.** `test_auth.py`: an expired cookie on register produces a distinct client-visible
status, not an endless retry; ingress test: `/auth/login` is either allowed on the tablet
listener or the deployment mode is refused as unsupported.

### H5 — Concurrent config writes overwrite each other (high)

**Trigger.** Two console tabs, or a preset apply racing a manual edit.
**Worst outcome.** The last writer silently replaces the other arrangement or content.
**Guard.** `If-Match` on every v3 write (already `main.py:1912`); never auto-retry a 412;
one Apply in flight; the conflict panel offers reload only. Do not mix ETag-less legacy
writes into the primary flow.
**Test.** `test_v3.py::test_config_writes_require_a_current_etag` extended: a stale ETag
on layout, display, calibration, and assignment leaves revision and slots unchanged; node
test: the preset button is disabled while busy.

### H6 — Rebind leaves saved arrangements pointing at a ghost (high)

**Trigger.** Browser storage cleared or origin changed; operator rebinds; later recalls
2×2.
**Worst outcome.** The arrangement reserves an id that will never return; a slot is empty
and the wall has a hole.
**Guard.** Preview affected arrangements; heal them in the same operation or list them as
needing repair; refuse conflicts; never partially apply.
**Test.** `test_tablet_models.py` / `test_v3.py`: after rebind, recalling a saved layout
places the new id; the response names the updated arrangements; a conflict leaves both the
active slot and the saved layouts unchanged.

### H7 — Offline reservations are silently released or silently collide (high)

**Trigger.** Preset apply while one placed tablet is offline; or `/wall/auto` with a
reservation in the grid area.
**Worst outcome.** The offline tablet wakes to no slot, or the new layout overlaps a
reserved rectangle.
**Guard.** Include offline placed tablets by default and mark them reserved; if capacity
is exceeded, disable the preset and require an explicit release; reuse the reservation
overlap refusal already implemented for `/wall/auto` (`main.py:1420-1446`).
**Test.** `test_offline.py` / `test_v3.py`: a preset that would drop an offline slot is
refused without a release; an overlapping physical layout is refused with 422 and no
revision change.

### H8 — A partial grid commit leaves half a wall (high)

**Trigger.** Legacy Tile applies one `PUT /devices/{id}/placement` per tablet
(`frontend/controller/controller-stage.js:996-1007`); the third fails.
**Worst outcome.** Some tablets moved, others not, several revisions, no single undo.
**Guard.** Presets use one `PUT /api/v3/layout`; failure changes nothing; the previous
committed layout is the undo target.
**Test.** `test_v3.py`: a failing slot validation leaves all slots and the revision
unchanged; a successful four-tablet apply bumps the revision exactly once.

### H9 — A stale acknowledgement paints a false green (high)

**Trigger.** A slow tablet acks revision 11 after revision 12 was broadcast.
**Worst outcome.** The console says "showing" for content the audience is not seeing.
**Guard.** Ack keyed by connection, generation, render sequence, revision, asset, and
mapping revision; accept only the current socket and a render sequence at or above the
last sent; everything else is recorded as ignored, never displayed as current.
**Test.** `test_v3.py`: a stale ack after a newer render is ignored; `client_image.test.js`:
a superseded load never paints and never reports success.

### H10 — Unknown status is shown as healthy (high)

**Trigger.** A protocol-2 client, a client without ack support, or an ack timeout.
**Worst outcome.** The operator trusts a wall that has no confirmation.
**Guard.** `unknown` is a first-class neutral state; the header counts only current acks;
old clients get "image confirmation unavailable" once, with the reason.
**Test.** Node state-derivation test: protocol < 3 yields `unknown`, never `painted`;
`test_v3.py`: a v2 device receives a neutral frame and no ack is expected.

### H11 — A layout switch destroys a tuned arrangement (high)

**Trigger.** Recall a logical layout while a physical wall is active
(`main.py:2079-2091`), or apply a preset over an unsaved draft.
**Worst outcome.** A calibrated 2×2 is gone; only a generic "Before physical" backup
exists for the other direction.
**Guard.** Every cross-kind switch writes a named backup in the same commit; the
confirmation says which name; refuse if the backup fails; show the previous arrangement
as an undo target.
**Test.** `test_v3.py`: logical recall from physical creates a restorable generated
backup; a failed backup write leaves the active layout unchanged.

### Additional credible failures

| Hazard | Guard |
| --- | --- |
| Two tabs with different drafts | One draft per tab, but conflict on apply; reload discards stale draft |
| Identify while the tablet is asleep | Disable with "offline"; never queue indefinitely |
| Image deleted or hash mismatch | `failed` with "Image missing", not a blank surface |
| Model change while a slot pins an old revision | Draft must re-pin or show a blocked slot; never silently rewrite |
| Content change while layout is being applied | Separate revisions; both writes use ETag; last conflict surfaces |
| Wrong mount angle (operator error) | Preview shows body outline; seam check records it; do not auto-correct |
| Very long labels | Truncate in the list, full text in the inspector; label is not a key |
| Phone controller on a narrow screen | Presets and Apply reachable without drag; inspector as a sheet |

---

## 12. Design contract (testable invariants)

These are the acceptance conditions for the UX work. Each is falsifiable.

**C1. One truth.** The primary console's rendered state is derived from the v3 config
plus render acks. No view fabricates a wall. A logical wall is shown as logical; a
physical wall is shown as physical.

**C2. No silent blank.** A layout write with zero slots is refused client-side and
server-side, except an explicit clear operation.

**C3. One commit per arrangement.** A preset apply produces exactly one revision bump,
one broadcast, one write, and no overlapping bodies. A failure produces zero changes.

**C4. Stable order.** Presets place tablets by display number, then label, then id; the
operator can see and change the order before Apply.

**C5. Mount is explicit.** Every slot has an operator-chosen mount angle. No code path
sets it from a browser report without the operator seeing it.

**C6. Fit is explicit and global.** The scene records `cover` (shown as Fill) or
`contain` (shown as Fit whole image); all tablets derive from the same wall rectangle;
the preview states the cropped fraction and bar size.

**C7. Transport is not health.** No green "showing" state exists without a current
acknowledgement. `unknown` is neutral and visible.

**C8. Stale is impossible to mistake.** An ack for an old generation/revision/asset/
mapping is never presented as current.

**C9. Detection is not confirmation.** A model match creates a suggestion, not a
physical scale; model-derived calibration is labelled approximate with its uncertainty.

**C10. Verbs are distinct.** Remove from wall, Forget, and Replace have different
consequences, different confirmations, and work in both layout kinds.

**C11. Rebind does not orphan snapshots.** After a replace, affected saved arrangements
are updated or explicitly listed as needing repair in the same response.

**C12. Switching is reversible.** Any cross-kind recall or apply writes a named backup
in the same commit and offers it as the undo target.

**C13. Expected states are calm.** Offline, disabled diagnostics, unsupported wake lock,
and old clients read as expected conditions with a next step, not as alarms.

**C14. No credential theatre.** QR carries an address; approval admits a join; pairing
issues a revocable credential. None is described as hardware identification.

**C15. Isolated evidence.** Every UX check runs against a temporary database and asset
directory; no live wall, firewall, or network is touched. Screenshots are labelled
"simulated Chromium", never "iPad".

---

## 13. Focused tests (source-based)

Run from the repository root. Use `rtk` for output filtering; keep the underlying
command exact so the evidence is reproducible.

Isolation for any manual console check (never the repository database):

```
QA_ROOT=/tmp/opencode/tw-ux-qa
mkdir -p "$QA_ROOT/assets" "$QA_ROOT/media"
export TABLET_WALL_DB="$QA_ROOT/wall.db"
export TABLET_WALL_ASSET_DIR="$QA_ROOT/assets"
export TABLET_WALL_MEDIA_DIR="$QA_ROOT/media"
```

Then start a loopback-only instance on a free port (18765 was used by earlier reviews)
and confirm no other listener is touched. No firewall rule, hotspot, or live network is
part of UX QA.

```
rtk test uv run pytest -q -p no:cacheprovider tests/test_v3.py tests/test_wall_sizing.py
rtk test uv run pytest -q -p no:cacheprovider tests/test_tablet_models.py tests/test_offline.py
rtk test uv run pytest -q -p no:cacheprovider tests/test_auth.py tests/test_ingress.py tests/test_security.py
rtk test node tests/controller_modules.test.js
rtk test node tests/client_image.test.js
rtk test node tests/physical_sizing.test.js
```

Full gates before hand-off:

```
rtk test uv run pytest -q -p no:cacheprovider
rtk test bash -c 'for t in tests/*.test.js; do node "$t" || exit 1; done'
rtk err uv run ruff check main.py tabletwall deploy
rtk err uv run mypy
```

New or extended tests, by contract:

| Contract | Test location | Assertion |
| --- | --- | --- |
| C1 | `tests/test_v3.py` | `GET /api/v3/config` includes `scene` (`content`, `fit`, asset name) and the active layout kind; a physical wall reports the same content the tablets receive |
| C1 | `tests/controller_modules.test.js` | The logical compatibility banner derives from `layout.kind`, not from a missing field |
| C2 | `tests/test_v3.py::test_an_empty_physical_layout_is_refused` | `PUT /api/v3/layout` with `slots: {}` returns 422; revision, generation, and existing slots unchanged |
| C2 | new node state test | A draft seeded from a logical wall with zero slots has Apply disabled and a reason |
| C3 | `tests/test_v3.py::test_a_preset_applies_as_one_commit` | Four slots, one request, revision +1, one broadcast; a 422 leaves everything unchanged |
| C4 | `tests/controller_modules.test.js` | Ordered selection uses number, then label, then id; equal numbers do not reorder unpredictably |
| C5 | `tests/physical_sizing.test.js` | Landscape and portrait presets produce the expected body rectangle and mount angle; a 90° body swaps dimensions once |
| C6 | `tests/client_image.test.js` | A `contain` scene paints the full source inside the wall with bars; two adjacent tablets derive the same wall rectangle; no per-tablet fit |
| C6 | `tests/test_api.py` / `tests/test_v3.py` | `fit: "contain"` is accepted, persisted, and returned; unknown fits are 422 |
| C7 | new node derivation test | `online + no ack` is `unknown`, not `painted`; `offline + last painted` preserves the last content sentence and does not count as showing |
| C7 | `tests/test_v3.py` | A protocol-2 device gets a neutral frame and is reported as confirmation-unavailable |
| C8 | `tests/test_v3.py` | A stale ack (older render sequence, revision, or asset) is ignored and cannot overwrite the current confirmed revision |
| C9 | `tests/test_tablet_models.py` | Auto match records `mode: "auto"`; a model change does not rewrite a pinned slot revision; the console mapping shows "model estimate" |
| C10 | `tests/test_v3.py` | Forget works while physical; Remove deletes only the slot; each leaves the other's data intact |
| C11 | `tests/test_v3.py` | Rebind updates named saved layouts and returns the list; a conflict changes neither |
| C12 | `tests/test_v3.py` | Cross-kind recall writes a backup; if the backup cannot be written, the switch is refused |
| C13 | `tests/controller_modules.test.js` | Expected states map to neutral tones; `unknown` and `offline` are not error-red |
| C14 | `tests/test_security.py` | A QR payload contains the origin and client path only; no device id, token, or secret |
| C15 | `tests/conftest.py` | Every test keeps `TABLET_WALL_DB`, `TABLET_WALL_ASSET_DIR`, and `TABLET_WALL_MEDIA_DIR` under `tmp_path` |

Implementation notes for the test author:

- Do not assert exact paragraph copy unless it is a contract string in §3/§5; assert the
  derived state and the action availability instead.
- For the empty-apply server guard, add the test before the guard and watch it fail for
  the right reason (200 with an empty wall, not a fixture error).
- For contain, reuse the existing geometry fixtures rather than hand-computing expected
  matrices in the test.
- Keep the existing Python and Node suites green. The reviews report 1,177 Python tests
  and 9 Node files at this commit; rerun and record your own counts. If a current test
  asserts the old cover-only or empty-apply behavior, update it with a comment naming
  this contract.

---

## 14. Desktop and mobile flows

### 14.1 Desktop (operator at a laptop, ~1600×1000)

1. Open the console. Stage shows the active wall, content, and revision. Readiness says
   either "Ready" or the specific degraded reason.
2. Copy the tablet address or show the QR card. The SSID and "Not a login" note are
   visible without scrolling.
3. Join four tablets. Each appears as `#N · suggested model`; confirm each. No physical
   slot exists before confirmation.
4. Select the new tablet, press Identify, watch the number on the physical screen, then
   rename it "Upper left". Identify restores the image on its own.
5. Wall → Arrangements → 2×2. The preview shows four bodies in number order, edge to
   edge, offline reservations marked. Apply once. Status counts progress.
6. Wall → Show → choose a 4:3 poster → Fill reports "about 6% of the height hidden" in
   2×2 → choose Fit whole image → Show. Every tablet reports "Showing rev 12".
7. Save arrangement as "2×2 lobby". Switch to 1×4 via the preset, Apply, save as
   "1×4 row". Fill now reports "76% of the height hidden" for the same poster; choose Fit
   again to compare. Recall 2×2: content stays, arrangement returns, the previous
   arrangement is offered as undo.
8. Pull one tablet's Wi-Fi. Its row reads "Offline · reserved"; the header counts it.
   Restore; it repaints and returns to green without operator action.
9. Force an image failure (isolated asset). The row names the reason; Retry recovers.
10. Reload the page mid-draft. The console says "Config changed; reload" or restores the
    committed state; it never applies a stale draft.

### 14.2 Mobile (operator at the wall, ~390×844)

1. The stage remains the first thing visible, with the primary action for the current
   task pinned below it.
2. Tasks are a bottom bar or a segmented control, not a shrunken desktop rail.
3. Tablet selection opens a sheet with number, label, state, Identify, and the one next
   action. No drag is required to select or reorder; "Move earlier/later" buttons work.
4. Presets show the same preview, scrollable, with Apply at thumb height. The Apply
   button is never below an unbounded list.
5. Errors and conflicts appear in the same viewport as the action; no toast-only failure.
6. Keyboard and screen-reader behavior on desktop: every drag has a numeric or button
   alternative; focus returns to the selected tablet after a re-render; status changes
   are announced once, not on every poll.
7. Test at 200% text zoom and in landscape. A dense calibration form may scroll; the join,
   arrange, show, and recover actions may not require it.

### 14.3 Flow acceptance

| Flow | Pass condition |
| --- | --- |
| First run | From an empty database to four tablets showing one image, using only the primary console, no shell command after launch |
| 2×2 → 1×4 → 2×2 | Three applies, content unchanged, no arrangement lost, no re-download of asset bytes |
| One tablet offline | Reservation preserved; header honest; recovery needs no operator action beyond waking the tablet |
| One tablet failed | Named reason; Retry works; other tablets unaffected |
| Replace a tablet | New id in the old slot; saved arrangements updated or listed; number preserved |
| Reload / second tab | No stale apply; conflict is visible and recoverable |
| Phone | Join, identify, preset, apply, and retry reachable with one thumb |

---

## 15. QA matrix

Expected values are the target contract. Current behavior may differ; §11 names the
known gaps. Run every row against a temporary database and asset directory.

### A. State derivation

| # | Transport | Slot | Ack / condition | Expected badge | Expected action |
| --- | --- | --- | --- | --- | --- |
| A1 | online | none | — | Not on the wall | Arrange |
| A2 | online | participating false | — | Excluded from show | Include |
| A3 | offline | present | last painted rev 11 | Offline · 42 s · reserved | Wake / Release spot |
| A4 | online | present | no profile | Needs calibration · no measurements | Confirm model / Measure |
| A5 | online | present | profile + viewport mismatch | Needs calibration · browser changed | Return to calibrated mode |
| A6 | online | present | render sent, 2 s ago, no ack | Sending image… | Wait |
| A7 | online | present | render sent, 12 s ago, no ack | No confirmation · 12 s | Retry / Reconnect |
| A8 | online | present | ack failed decode | Image failed · decode | Retry |
| A9 | online | present | ack painted rev 11, wall rev 12 | Showing rev 11 · stale | Wait / Retry |
| A10 | online | present | ack painted current | Showing rev 12 · 3 s ago | None |
| A11 | online | present | protocol 2 | No confirmation · old client | Update |
| A12 | — | slot names a missing device | slot exists, device gone | Missing tablet · slot reserved | Replace / Remove |
| A13 | online | present | colour blackout | Blackout applied | Show image |
| A14 | online | present | ack for an older connection | Ignore ack; keep current state | — |

### B. Arrangement and fit

| # | Given | Action | Expected |
| --- | --- | --- | --- |
| B1 | 4 online, numbered 1-4, landscape | 2×2 preview | Order #1 #2 / #3 #4; bodies edge to edge; gap 0 |
| B2 | 4 online, one offline placed | 2×2 | Preset includes the offline slot as reserved; preview marks it; Apply preserves it |
| B3 | 5 selected | 2×2 | Preset disabled: "holds 4; 5 selected" |
| B4 | 3 selected | 2×2 | Preview names the empty cell; Apply requires "Apply with one empty cell" |
| B5 | Two slots overlap in the draft | Apply | Refused with the overlapping pair named; no revision change |
| B6 | Logical wall, fresh console | Apply | Disabled: "no tablets in this arrangement" |
| B7 | Physical draft, second tab applies first | Apply | 412 conflict panel; no partial write |
| B8 | 4:3 poster on 1×4 | Choose Fill | "Fill hides 76% of the height"; stage shows cropped source |
| B9 | Same poster | Choose Fit whole image | Whole image visible; bars shown; status says Fit |
| B10 | Image smaller than wall | Show | Upscale warning with source pixels per tablet |
| B11 | Switch 2×2 → 1×4 | Recall | Backup name shown; content unchanged; previous arrangement undoable |
| B12 | Apply four slots | Observe revision | Exactly one bump; one broadcast; one repaint cycle |

### C. Identity and switching

| # | Given | Action | Expected |
| --- | --- | --- | --- |
| C1 | Online tablet | Identify | Number flashes ≤1 s; scene unchanged; revision unchanged |
| C2 | Offline tablet | Identify | Disabled with "offline"; no queued overlay |
| C3 | New tablet | Join | Appears as suggested model; no physical slot until confirm |
| C4 | Confirmed model | Change model | Preview of affected slots; pinned revisions unchanged until Apply |
| C5 | Placed tablet | Remove from wall | Slot removed; device, number, saved arrangements kept |
| C6 | Offline tablet, physical wall | Forget | Roster entry and history removed; affected arrangements listed |
| C7 | Online tablet | Forget | Refused; offer disconnect/remove first |
| C8 | Old offline id, new id | Replace | Slot and number move; affected arrangements updated or listed |
| C9 | Old id online | Replace | 409; nothing moved |
| C10 | Number in use | Replace | 409; nothing moved |
| C11 | After replace | Recall 2×2 | New id lands in the old slot |
| C12 | Saved layout with a missing tablet | Recall | Preview names the hole; no silent drop |

### D. Resilience, security, and evidence

| # | Scenario | Expected | Evidence |
| --- | --- | --- | --- |
| D1 | Server restart, tablets open | All re-register; content and layout restored; no manual reload if the client reconnects | Test log + simulated run |
| D2 | Tablet offline 30 s (Wi-Fi off), then restored | Offline, then repaint; no duplicate roster row | Simulated run |
| D3 | Stale ack after newer render | Ignored; console stays on current revision | Unit test |
| D4 | Two tabs write | One applies; the other gets 412 and reloads | API test |
| D5 | Auth enabled, session expired | Visible sign-in or device credential; no infinite retry | Auth test; mode card says unsupported until fixed |
| D6 | Hotspot mode | No uploads or browser wake lock advertised; diagnostics on the operator path; operator loopback only; tablet 403 surface intact | Ingress test |
| D7 | QR displayed | Contains origin + `/client/` only | Security test |
| D8 | Device id in a QR or log | Absent | Review of the payload |
| D9 | Screenshot evidence | Label says "simulated Chromium 1600×1000 / 390×844", never "iPad" | Artifact path + caption |
| D10 | Full suite | Baseline holds; new contract tests fail before the guard and pass after | Command output |

---

## 16. Top acceptance blockers

Ordered by how directly each stops a non-author from getting a dependable image wall.

1. **The primary console cannot state or change the active content truthfully.**
   The v3 config has no scene; `PUT /scene` on a physical wall returns a synthetic
   envelope. Until this is fixed, no other screen can be trusted. Closes when the
   console names the image, fit, revision, and layout kind after a reload, and a
   tablet's slice matches the preview.
2. **One click can blank the wall.** Zero-slot physical apply is enabled and accepted.
   Closes when the client disables it and the server refuses it, with a test proving the
   revision does not move.
3. **"Online" is the only health signal.** There is no static render acknowledgement, so
   a failed or stale tablet looks healthy. Closes when each tablet reports a current
   `painted`/`failed` state keyed by revision and asset, and stale reports are ignored.
4. **2×2 and 1×4 are not repeatable.** UUID ordering, a hard-coded mount angle, no
   presets, and per-tablet writes make the advertised quick path unreliable. Closes when
   a preset is one atomic write in number order with a preview.
5. **Fit is cover-only, and the loss is invisible.** A 4:3 poster on 1×4 loses about 76%
   of its height. Closes when Fit whole image is persisted and previewed, with the
   cropped fraction stated before Apply.
6. **Identity survives neither origin change nor cleanup.** Rebind leaves snapshots
   stale; physical cannot forget; there is no label or Identify. Closes when the
   lifecycle actions are distinct, rebind heals or reports saved arrangements, and
   Identify is available online.
7. **A layout switch can destroy a tuned arrangement.** Logical recall from physical
   writes no backup. Closes when every cross-kind switch writes and names a return point.
8. **Recovery and deployment are unproven on hardware.** Sleep, wake, restart, auth
   composition, diagnostics in hotspot mode, and seam accuracy have no real-device
   evidence. Closes only with recorded runs, not more software tests.

---

## 17. Non-goals and open decisions

Not in this scope:

- Video, playlist polish, optical synchronization, audio.
- Mirror or independent per-tablet content.
- Cloud, multi-user roles, remote internet access.
- A framework rewrite, a second database, distributed state.
- Per-device image renditions before decode timings exist.
- More built-in tablet models as a substitute for confirmation.
- Remote power, remote unlock, or guaranteed recovery from OS freeze.

Open decisions that need an owner, not a guess:

1. **Stable installed-slot identity now, or heal snapshots on rebind?** Healing is
   smaller and closes the immediate hole; a stable slot identity is the durable fix.
2. **Approval on by default?** Recommended off on a private hotspot, on for shared Wi-Fi.
3. **Final origin (HTTP 8080 vs HTTPS 8443) before calibrating a fleet.** Changing origin
   resets browser identity; decide before measurement, not after.
4. **Letterbox colour** default and whether it is per scene or per wall.
5. **Ack timeout.** 10 s is proposed; it must be longer than a slow decode on a 2 GB
   tablet and shorter than an operator's patience. Measure before fixing it.
6. **Whether `physically-checked` becomes a stored record** or stays a note in the
   validation document.

---

## 18. Suggested build order

1. Truth: scene in the operator state, still controls in the primary console, logical
   compatibility banner.
2. Safety: zero-slot refusal, empty-apply guard, cross-kind backup, single-write presets.
3. Truth per tablet: ack contract, state derivation, header count, retry.
4. Presets: ordering, mount choice, preview, offline reservations.
5. Fit: contain in API, persistence, client render, preview arithmetic.
6. Identity: labels, Identify, Forget in physical, rebind healing.
7. Calm operation: readiness card, QR, mode copy, OS wake checklist.
8. Real-device evidence: seams, switching, reconnect, sleep, 2-hour soak. Record failures.

Each step ends with a runnable check. Do not start step 3 before step 1; a truthful ack
for an unknown scene is still an unknown scene.

---

## 19. Evidence to attach when this contract is claimed as met

- Commit SHA and the exact commands run.
- `pytest` summary with counts and the Node per-file results.
- Isolated server log showing temporary `TABLET_WALL_DB`, asset, and media paths.
- Desktop screenshot at 1600×1000 and phone screenshot at 390×844, captioned
  "simulated Chromium", with the tested revision visible.
- API traces for: empty apply 422, preset apply (one revision bump), 412 conflict,
  stale ack ignored, rebind updating saved layouts, cross-kind backup.
- A physical run record only if it actually happened: devices, OS/browser, launch mode,
  orientation, origin, image, fit, observed seams, failures, and manual interventions.
  Otherwise write "not performed" and keep the hardware gate open.

A software pass is not a hardware gate. A screenshot is not a seam measurement. A model
match is not an identification. Say which one the evidence is.
