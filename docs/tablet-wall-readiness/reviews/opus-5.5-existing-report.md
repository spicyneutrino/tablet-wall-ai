# Tablet wall readiness assessment and path to dependable use

Repository `tablet-wall-ai` at HEAD `0ff56e3` (feat: add measured tablet setup and adaptive wall sizing). Assessed 2026-10-31 by the requested Opus review subagent. This is assessment and planning only. No tracked file was changed.

**Goal restated.** The user wants a wall of a few browser tablets (iPad Air 2 and Google Pixel C today) that a person can set up, arrange as 2×2 or 1×4, and use to show one large image reliably. The question is what stands between the current code and that outcome, and what to build, cut, or defer.

## Evidence labels

Every claim below carries one of these tags.

- **[S]** means confirmed by reading current source at `0ff56e3`, with a file and line reference.
- **[Sim]** means observed this session in an isolated simulated run. The app ran on loopback `127.0.0.1:18765` with a temporary database. Four headless Chromium "tablets" ran at 1024×768, DPR 1, platform `other`, plus a desktop controller at 1600×1000 and a phone controller at 390×844. These are not iPads or Pixel Cs. They never matched a tablet model, and nothing here shows how Safari or Android Chrome behaves.
- **[U]** means user-reported physical testing, or the prior screenshot taken from a real connected session (`/var/home/oak/.t3/userdata/attachments/0dcb1b86-…-2e60d6ff-….png`).
- **[T]** means automated tests. I re-ran them this session. `uv run pytest` gave **1177 passed in 70.45 s**, and all 9 `tests/*.test.js` Node suites passed. The working tree stayed clean.
- **[P]** means my proposal.
- **[H]** means a hypothesis or outside knowledge not verified here. Verify it before relying on it.

The earlier simulator screenshots directory `/tmp/tablet-wall-commit-review-pd29jwy_/` no longer exists, so I did not use it. My own screenshots are at `/tmp/tw-opus-assess-*.png`. Every server and browser session I started has been stopped, and port 18765 is free.

---

## 1. Readiness verdict

**Verdict: ready for a supervised image demo with the logical controller. Not yet ready for unsupervised or "anyone can set it up" use. The measured mixed-model physical path is implemented and tested, but no hardware has exercised it.**

The core loop works. A tablet opens a URL, registers, gets a number, is placed, and shows its crop of one wall-wide image. That held in the user's own runs [U], in tests [T], and in my simulation [Sim]. What is missing is mostly not rendering. It is trust signals, identity handling, one obvious arrange flow, and a single controller.

The strongest existing capabilities follow.

1. **Correct, defensive state core [S][T].** Writes go through a commit boundary. The database is written first, memory is applied second, and the broadcast goes out last (`main.py` `_commit_wall`, PROTOCOL.md). Revisions, generations, ETag `If-Match` on v3 writes (`main.py:1912`), and per-socket bounded writers that coalesce snapshot frames (`tabletwall/writer.py:1-35`) make concurrent controllers and slow tablets safe. 1177 tests cover this.
2. **A tight tablet-only network surface [S].** The hotspot listener exposes an exact allowlist: client files, `POST /devices/register`, `/ws/device`, and content-addressed `/assets/sha256:…` (`deploy/tablet-routes.caddy`). Everything else answers 403. The operator listener binds loopback only. The launcher proves this at startup, checking that operator routes answer 403 on the tablet port and that the WebSocket upgrade works (`deploy/hotspot.py:148`). Firewall ports it opens are recorded and removed on exit or on the next start (`deploy/hotspot.py:112`).
3. **Durable identity and reservations [S][T].** Tablets keep a UUID and a display number. Placements survive restarts as reservations. Offline tablets reclaim their spot. Rebind moves a lost identity's slot, number, and measurements to a new one (`main.py:1074-1172`).
4. **Measured models as a calibration shortcut [S][T].** Built-in iPad Air 2 and Pixel C models carry the user's hand measurements with 3 mm uncertainty (`tabletwall/tablet_models.py:8-15`). They create a profile and calibration without a ruler session. Viewport adaptation follows rotation and tab, fullscreen, or standalone mode (`tablet_models.py:96-131`). Historical snapshots are pinned per calibration revision.
5. **Wall sizing that matches how people think [S][T].** "Fixed size" and "Fit to tablets" are separate modes, and packing is explicit (`tabletwall/sizing.py`, `docs/WALL-SIZING.md`).
6. **Image delivery is cache-friendly [S].** Asset bytes are content-addressed and served `public, max-age=31536000, immutable` (`tabletwall/routes/assets.py:70`). Switching layouts or re-showing an image does not re-download it.
7. **A reasonable responsive controller [Sim][U].** The logical controller works at desktop and phone widths, with tablets, stage, and inspector panes plus a task bar on mobile (`/tmp/tw-opus-assess-mobile.png`).

What has **not** been validated: precise seams, optical timing, real OS sleep and wake recovery, sustained soak, Safari storage behavior, and anything about video. `docs/validation/ACCEPTANCE.md` correctly lists all eight hardware gates as **MISSING** [S]. Playlist, playback, and video code exists (`tabletwall/playback.py`, `tabletwall/video.py`, `frontend/controller/physical-playback.js`). That code is **experimental and unvalidated on tablets**. Nothing in this report treats video as working.

---

## 2. Key blockers to first dependable real use

Ordered by how directly each one stops a non-author from getting a seamless image on four tablets and keeping it there.

### B1. The main controller always raises a false "not confirmed" alarm [S][Sim]

`frontend/controller/controller.js:1357` and `:1456` treat a tablet as image-capable only when `device.protocol === 2`. Current tablets negotiate protocol 3, with caps `["calibration","image","physical","video"]`, as seen in `GET /devices` during [Sim]. Every placed, online, healthy tablet therefore lands in the "Placed, not confirmed … online · capability unknown … There is no way to confirm what these show" alert. The cap chip also says "Image support unknown". I reproduced this on desktop and on phone width (`/tmp/tw-opus-assess-ctl-image.png`, `/tmp/tw-opus-assess-mobile.png`). An operator learns to ignore warnings, which defeats the health UI. The fix is small: accept `protocol >= 2`, and decide whether v3 reports caps the same way. No test or simulator scenario references `renderCoverage` or this alert text (grep of `tests/` and `simulator/`), so nothing pins the v3 case [S].

### B2. Nobody can know what a tablet actually shows [S]

For still images, tablets send heartbeat, viewport, and playback-only messages (`main.py` around lines 2890-3000). They never acknowledge a render. The client draws a "loading" or "failure" panel locally (`client.js:1560-1600`), but the server never hears about it. A tablet that failed to decode, is stuck on an old revision, or is asleep with its socket half-open looks the same as a healthy one until the heartbeat times out after 15 s (`tabletwall/protocol.py:13-15`). Dependable use needs a one-line truth per tablet, such as "showing revision 12, wall-grid.png, painted 3 s ago" or "image failed: decode".

### B3. Arranging a seamless grid takes three or four tools, and the defaults produce gaps [S][Sim]

- The logical controller has **Tile tablets**, **Arrange online**, **Fit wall to tablets**, and **Pack placed tablets**. The physical console has **Arrange connected tablets** and **Pack tablets**. These are six overlapping concepts.
- The Tile defaults are hard-coded to **3 columns × 2 rows, gap 20** (`frontend/controller/index.html:463-465`), whatever the tablet count. With 4 tablets, the first preview is a 3×2 grid with an empty cell (`/tmp/tw-opus-assess-ctl-tile.png`).
- I applied a 2×2 tiling with gap 0 and "Keep screen shape" on the default fixed 2000×1000 wall. The result was 667×500 footprints with **167-unit dead bands** between columns [Sim]. The image is cover-fitted across the full wall, so a third of the picture falls in those bands. Getting a continuous 2×2 needed Tile, then Fit-to-tablets, then Pack with columns 2 and gap 0.
- Tile apply issues **one `PUT /devices/{id}/placement` per tablet in sequence** (`frontend/controller/controller-stage.js:996-1007`). For 4 tablets the wall revision went from 0 to 4 [Sim], so each tablet repaints up to four times. A mid-way failure leaves a partial layout, and the UI says so ("If one fails, earlier updates stay applied"). The atomic server endpoints `/wall/auto` (`main.py:1353`) and `/wall/pack` (`main.py:1217`) already exist.
- In the physical console, **Arrange connected tablets** (`frontend/controller/physical.js:3095-3115`) sorts tablets by **UUID**, not display number. It always builds **one row**, and it hard-codes `mount_angle: 0`, so every tablet is assumed portrait. Landscape 2×2 iPads need four manual rotations and a re-pack before the result matches the wall.

### B4. Two controllers and two layout models, with hard fences between them [S]

- `/controller/` ("Tablet wall", logical units) and `/controller/physical.html` ("Wall console", millimetres) are separate apps. They differ in look, navigation, and vocabulary: Layout versus System, "Remove" versus "Delete from wall" (screenshots `ctl-*` versus `physical-*`).
- Once a physical layout is applied, every legacy route is fenced with 409 "Upgrade controller" (`main.py:1678-1684`). Applying also closes non-v3 controller sockets (`main.py:2067`). The logical controller has no handling for this state that I could find (no "upgrade" or "physical" text in `controller*.js`).
- **The physical console has no single-image path.** It never calls `PUT /scene` (no `/scene` in `physical*.js`). Its only way to change what the wall shows is the playlist plus **Start**, which is the experimental playback engine (`frontend/controller/physical-playback.js`, top-bar Start/Pause/Stop at `physical.html:22-24`). To show a measured, physically correct still today, you set the image in the logical controller *before* applying the physical layout, or you run the slideshow engine. `docs/PHYSICAL-CALIBRATION.md` tells users to "select it as the wall image" in the normal controller, which is fenced once the layout is physical.
- **No Forget in physical mode.** `DELETE /devices/{id}` calls `_require_logical_wall()` (`main.py:1031`), and the physical console has no forget action (only `rebind` and saved-layout delete in `physical.js`). Stale identities, like the offline "#1 · 1920×1080 · other" in the user's real session [U], cannot be cleared while a physical wall is active.
- **No rebind in the logical controller.** `controller.js` has zero rebind references. Rebind lives only under Physical console → System → Field check (`physical.html:612-643`).
- On first open, the physical console shows **"Draft not applied"** with **Apply layout enabled**. Its draft is seeded from the logical wall's 2000×1000 *units*, reinterpreted as *millimetres*, with no slots (`/tmp/tw-opus-assess-physical-show.png`). `applyLayout` (`physical.js:1297-1318`) has no zero-slot guard or confirm, and the server accepts empty `slots`, so one click would replace a working logical wall with an empty physical one. The server does save a "Before physical …" backup (`main.py:2057`), but this is still a trap.

### B5. Identity loss breaks saved layouts, and identity loss is likely [S][H]

- Rebind moves the live placement or slot, but "Saved layouts keep naming the old id; recall one and save it again" (`main.py:1082`). Fast 2×2↔1×4 switching depends on saved layouts. After any identity loss, recalling them restores reservations for a UUID that will never return.
- Ways to lose identity include clearing site data, opening the client in another browser or a private tab (`docs/PHYSICAL-CALIBRATION.md`), and **any origin change**, such as the HTTP hotspot trial moving to the HTTPS deployment (8080 to 8443). [H] Safari's tracking prevention can also delete script-written storage for sites without user interaction after 7 days of Safari use. Home Screen web apps are treated differently. This needs an iPad test.
- Auto model matching keys on CSS screen size, DPR, and platform only (`tabletwall/tablet_models.py:23-33`). [H] An iPad mini 2, 3, or 4 reports the same 768×1024 at DPR 2 on iOS as an Air 2, but its panel is physically smaller (7.9" versus 9.7"). It would silently receive the Air 2's mm-per-CSS scale. The docs call the match "a hint, not proof", but the UI applies it automatically (`main.py:964-971`).

### B6. The supported deployment disables diagnostics, uploads, and wake lock [S]

- `make hotspot` refuses to start if authentication or uploads are enabled (`deploy/hotspot.py:306`).
- With uploads disabled, `/diagnostics` fails closed, because it is admitted like the media library (`tabletwall/routes/diagnostics.py:87-99`). The physical console's Field check reads "unavailable" [Sim].
- Content arrives only by copying files into `~/.local/share/tablet-wall-ai/assets/` and pressing Refresh. The logical UI still shows an "Add a file: JPEG, PNG, MP4 or MOV" upload block (`index.html:395`).
- Plain HTTP is not a secure context, so the Screen Wake Lock always reports `insecure` (`client.js:2403`). The launcher says "keep tablet screens awake manually" (`hotspot.py:272`). [H] An iPad Air 2 tops out at iPadOS 15.8, and Safari gained Screen Wake Lock only in 16.4, so even HTTPS would not help that model. OS settings and Guided Access are the real mechanism.
- The controller is reachable **only from the laptop** (loopback). The phone layout cannot be used in the supported deployment.

### B7. Only "cover" fitting exists, and cropping is mostly invisible [S][Sim]

`SUPPORTED_FITS = ("cover",)` (`tabletwall/protocol.py:61-62`). A 4:3 poster on a 1×4 wall (roughly 5:1) loses most of its height. The stage shows only the parts that land on tablet faces. Nothing shows the cropped-away source or the areas hidden behind bezels. The image-library thumbnail is the only hint. In the user's real 2×2, a portrait Pixel C (#4, 900×1280) sat in a landscape footprint. The stage drew a dark band and a tiny "1.569 ≠ 0.703" label [U]. In logical mode each tablet cover-crops its own rectangle to its viewport (`client.js:1751-1760`), so a shape mismatch silently breaks continuity at that seam.

---

## 3. Streamlined operator journey [P]

Target data shape: **Tablet** (stable `#N`, label, model, orientation, online, last-painted revision), **Wall** (one millimetre layout, slots keyed by tablet, a size mode, and a fit of cover or contain), **Arrangement** (a named wall layout), and **Content** (one image plus its fit). Everything else is a view of these.

1. **Start.** Run `make hotspot` once. Later, a systemd user unit starts it at login. The terminal and the controller header both show the tablet URL as text and as a **QR code**. The launcher already validates the hotspot, so it can also print "Tablets join SSID X, then open http://10.42.0.1:8080/client/".
2. **Join.** On each tablet, scan the QR or type the URL. The tablet shows a large `#N` and "Waiting for approval" (or "Joined", if approval is off). The controller shows a **"New tablet" card** with the detected model: "Looks like an iPad Air 2. Confirm?" with Confirm, Other model, and Measure manually. **Identify** flashes the number on that tablet, full screen, for 5 s.
3. **Name and place.** Confirmed tablets go into a tray, sorted by number. The operator chooses **Make a grid**, with presets 2×2, 1×4, and 4×1 plus custom rows×columns, and an orientation of auto, portrait, or landscape. One atomic server call places tablets in number order. Footprints are sized from model millimetres, bezels become gaps, mount angle comes from the reported orientation, and the wall fits the tablets. The preview appears on the stage with the image under it. Then **Apply**.
4. **Show content.** Pick an image from the library. The stage shows the **full source image dimmed**, the wall rectangle, the tablet faces bright, and bezel areas hatched. A **Cover/Contain** toggle sits next to it. Show on wall.
5. **Confirm.** Each tablet card turns green only when the tablet acknowledges "painted revision N". A header line reads **"4 of 4 showing wall-grid.png"**.
6. **Switch 2×2 → 1×4.** Save the current arrangement as "2×2". Physically move the tablets. Choose **Make a grid → 1×4**, or recall a saved "1×4", and Apply. If the tablets were rotated, auto orientation picks it up from each tablet's reported viewport, and the stage flags any tablet whose live orientation disagrees with its slot. Undo restores the previous arrangement.
7. **Recover.** A tablet sleeps or loses Wi-Fi, and its card shows "offline 40 s, spot reserved". It reconnects on wake and repaints. The card turns green again without operator action. If it comes back as a new identity, the controller says: "New tablet #7 (iPad Air 2) appeared while #3 (iPad Air 2, placed) is offline. Is this #3?" **Yes** rebinds, rewriting saved arrangements too.
8. **Remove versus forget.** **Remove from wall** frees the slot and keeps the tablet known. **Forget tablet** deletes it from the roster and from saved arrangements after a confirm. Neither action requires a particular layout mode. Offline placed tablets show as "reserved" with a **Release spot** action.

Steps 2, 3, 5, 7, and 8 change today's behavior. Steps 1, 4, and 6 mostly reuse existing parts: the URL display, the image library, and saved layouts.

---

## 4. UI, layout, and mode redesign

### Retain

- The three-pane desktop shape of the logical controller: tablets, stage, inspector. The mobile task bar. Status footer with revision and session. Undo and redo. Keyboard nudging. Aspect-mismatch markers, made larger. All [Sim].
- The physical console's draft, Apply, and Cancel model, with ETag conflict reload. This is the right safety model for multi-tablet changes [S].
- Saved layouts as named arrangements, and the automatic "Before physical …" backup [S].
- The ruler page (`frontend/client/ruler.js`), as an "advanced: measure manually" path [S].
- The device-health summary strip from the physical console ("4 online · 0 offline · 4 needs calibration") [Sim].

### Consolidate [P]

1. **One controller, one stage in millimetres.** Make the physical (mm) layout the only model the UI edits. Model-known tablets get exact footprints. Unknown tablets get an *estimated* footprint from CSS pixels times a default 0.17 mm/px, with an "estimated" badge and a "Measure" action. That keeps the zero-setup feel of logical mode without a second model. Migrate saved logical layouts once, then delete the legacy routes in the same wave. This is the largest item (L). It should follow the smaller fixes, not block them.
2. **One arrange tool** ("Make a grid") replaces Tile, Arrange online, Arrange connected, and Pack. Keep "Fit to tablets" as the default sizing mode and move "Fixed size" under Advanced.
3. **Navigation: Wall · Tablets · Content · Arrangements.** "System" becomes a small Settings and Health drawer holding diagnostics, backup, and an advanced calibration entry. Move playback Start/Pause/Stop **out of the top bar** behind an "Experimental: slideshow" switch until it is validated on hardware.
4. **One stylesheet per page.** `physical.html:10-11` loads both `physical-legacy.css` (3194 lines) and `physical.css` (2400 lines). Delete the legacy one once the views are consolidated.
5. **Hide disabled features in the deployment that disables them.** In hotspot mode, hide the upload block (`index.html:395`) and replace it with "Add images: copy files to <path>, then Refresh". Do not advertise MP4 or MOV while video is experimental.

### Tablet-side UI [P]

- An **Identify overlay**: a full-screen number plus label, shown on an operator command or a 3-finger tap, whatever the content.
- A **state banner** only when something is wrong: "Not on the wall", "Rotate to landscape to match the wall", "Waiting for approval", or "Lost connection, retrying". Today `drawImageFailure` and `drawImageLoading` exist (`client.js:1570-1600`). The new part is sending the state to the server (B2).
- A **"Tap for full screen" first-run prompt** on Android. On iOS, instructions to Add to Home Screen. Fullscreen there is limited, and Home Screen also helps with storage persistence [H].

### Wall modes [P]

All three are proposals, ranked by value per effort.

| Mode | What it does | Benefit | Risk or tradeoff |
| --- | --- | --- | --- |
| **Span** (exists) | One image across the wall | The core use | Cropping and bezel loss, solved by contain and the crop overlay |
| **Mirror** | Every tablet shows the whole image, contain | Trivial setup, no calibration, useful for signage | Client draw branch only, cheap. Must not complicate span geometry |
| **Independent** | Per-tablet image | Menus, labels, mixed content | Needs per-tablet content in the data model, so wait until span is dependable |

---

## 5. Brainstorm, grouped

### Must-have (first dependable use)

| Idea | User benefit | Risk or tradeoff |
| --- | --- | --- |
| Fix the v3 capability check (B1) | Warnings mean something again | None, about 2 lines plus a test |
| Render acknowledgement `{render_seq, revision, asset, status}` from tablet to server, shown per tablet and in a header count (B2) | Operator sees truth, not inference | Small protocol addition. Keep v2 compatible |
| Atomic "Make a grid" endpoint (rows, cols, orientation, gap = bezels, number order, fit wall) (B3) | 2×2 and 1×4 in one action, one repaint | Must handle offline reservations. Reuse `/wall/auto` conflict logic |
| Sensible defaults: grid columns from count (2×2 for 4), gap 0 plus model bezels, fit-to-tablets by default | No dead bands on first try | Changes existing defaults. Pin them with a test |
| Identify button (flash number on tablet) | Match screen to card in seconds | Small server command, mirrors `set_color` (`hub.py:61`) |
| Forget allowed in any layout mode. Remove versus forget clearly separated | Clean roster | Forget must also clean slots and saved layouts, or mark them |
| Rebind in the main UI, with an auto-suggestion when a same-model tablet appears while a placed one is offline | Identity loss becomes a one-tap fix | False suggestions with identical models. Always confirm, never auto |
| Rebind rewrites saved layouts (B5) | Saved 2×2 and 1×4 keep working | Saved layouts become mutable on rebind. Record the change in the response |
| Confirm-on-detect for models instead of silent auto | Wrong-scale iPads are caught | One more click per new tablet |
| A physical-console path to show a single still via `PUT /scene` (B4) | Measured layouts usable without the slideshow engine | Small, until consolidation lands |
| Kiosk and sleep checklist per OS in the controller's help | Screens stay on | Documentation plus OS settings. Cannot be enforced from the web |

### Useful next

| Idea | User benefit | Risk or tradeoff |
| --- | --- | --- |
| Cover/Contain per content, plus letterbox colour | Posters stay readable on 1×4 | Contain leaves bars. Default stays cover |
| Crop and bezel overlay on the stage (dimmed source outside the wall, hatched bezels) | See exactly what is lost before Apply | Rendering only |
| Registration approval ("New tablet waiting") | Doubles as onboarding and as a guard on shared networks | One more step. Make it optional on a trusted hotspot |
| QR for the tablet URL in the controller and terminal | No typing on tablets | Tiny |
| Human labels ("Left top") alongside `#N` | Clear cards and saved layouts | Another field. Numbers stay canonical |
| Orientation-aware slots: the stage warns, or offers to flip, when a tablet's live orientation contradicts its slot | Fixes the real #4 mismatch [U] | Auto-flip could surprise. Warn first |
| Launcher as a systemd user service with a clean stop | Survives reboots and closed terminals | The firewall cleanup path must run on stop. It already handles crash recovery (`hotspot.py:112`) |
| Library hint for oversized images, with an optional single capped rendition (for example a 4096 px long edge) | Faster first paint on 2 GB tablets [H] | Measure first. Pillow already exists in `media_worker.py` |
| Health drawer that works with uploads disabled (split diagnostics admission from upload admission) | Field check in the real deployment | Must stay operator-only |

### Optional future

| Idea | User benefit | Risk or tradeoff |
| --- | --- | --- |
| Phone controller over the hotspot with PIN pairing and a session cookie (reuse `tabletwall/auth.py`) | Operate while standing at the wall | New network exposure. Needs HTTPS or an accepted HTTP risk on a trusted hotspot |
| Mirror and Independent modes | Signage variety | Scope creep before span is reliable |
| Scheduled arrangements and content | Unattended displays | Requires soak validation first |
| Photo-based seam check (phone photo of the grid image) | Faster calibration | Research-grade. The optical tooling exists but is heavy |
| HTTPS by default with a guided CA install | Wake lock on capable tablets, shared-network safety | Origin change resets identities (B5). Decide before calibrating a fleet |

---

## 6. Security, deployment, performance, and architecture

### Security and deployment

What is sound [S]:

- The tablet ingress is a strict allowlist that strips the operator header (`deploy/tablet-routes.caddy`).
- The operator listener is loopback-only, in both the hotspot launcher (`hotspot.py:254`) and the HTTPS reference (`deploy/hotspot.Caddyfile`).
- An Origin guard covers every state-changing request except tablet registration (`main.py:790-820`).
- The launcher verifies the 403 surface at every start (`hotspot.py:148-190`).
- Asset URLs are unguessable content hashes.

What to change, in order [P]:

1. **Keep the trusted-hotspot HTTP model for demos.** It is a sound tradeoff: WPA2 keeps outsiders out, and the operator surface never touches the radio. Say plainly in the UI that this mode has **no wake lock, no uploads, and no diagnostics** (B6), and give the diagnostics their own admission rule.
2. **Registration is open to any hotspot client** (`main.py:899`). Anyone with the Wi-Fi password gets a number and, even unplaced, a wall frame carrying the current image's asset URL (`tabletwall/state.py:338-353`). They cannot change anything. At `MAX_DEVICES = 512` (`protocol.py:28`), a registration flood evicts the least-recently-seen *offline* records (`main.py:907-923`), which could include a sleeping real tablet's record. Its placement survives, but its colour and number lease do not. This is low risk on a private hotspot. Registration approval (Section 5) closes it and helps onboarding.
3. **Shared network (venue Wi-Fi):** do not run the HTTP trial there. Use the HTTPS reference with basic auth, and keep the operator on loopback. Treat registration approval as required there.
4. **Pick the final origin before calibrating.** Moving from HTTP 8080 to HTTPS 8443 changes the origin and wipes every tablet's identity. Rebind recovers live slots but not saved layouts (B5).
5. **Backups:** `deploy/backup.py` exists and the logical-to-physical backup is automatic [S]. Add a one-line "Back up now" to the health drawer before anyone experiments with arrangements.

### Performance and architecture

Measured or observed:

- The tiling apply produced **4 commits and 4 broadcasts for 4 tablets** [Sim]. That is the clearest efficiency problem, and the atomic endpoint fixes it (B3).
- Curated assets go to every tablet at full resolution, and each tablet decodes the whole file (`createImageBitmap(blob)`, `client.js:1163`). The sample library holds a 4000×3000, 2.7 MiB PNG [Sim]. [H] Decode time and memory on an iPad Air 2 (2 GB RAM) may delay first paint. This is unmeasured. Measure "time to painted" per tablet once render acks exist (B2) before building renditions.

Unmeasured and not worth acting on at 4-20 tablets:

- Every broadcast does synchronous SQLite reads in the event loop per v3 device (`hub.py:85-110`, `tablet_models.effective` reading metadata JSON).
- `_config_etag` rebuilds and hashes the full config payload on each v3 write (`main.py:1905-1917`).

Do not optimise these. The writer queue already isolates slow sockets (`writer.py`).

The real cost is **code weight**, not CPU: `main.py` is 3163 lines, `client.js` 4511, `physical.js` 3477, `controller.js` 3429, and the physical page loads about 5.6k lines of CSS. Two controllers double every UI fix. The playback and video stack (`playback.py` 1190, `video.py` 596, `physical-playback.js` 1447, plus heavy simulator and validation tooling) carries most of the remaining complexity for a feature with no demonstrated hardware value yet.

Architecture recommendations [P]:

- Stay on the current stack: FastAPI, SQLite, a vanilla-JS client and controllers, Caddy. No framework rewrite, no distributed backend, no cloud.
- Consolidate controllers (Section 4).
- Freeze playback and video behind an "experimental" flag rather than deleting it. Keep its tests green but stop extending it.

---

## 7. Prioritised roadmap

Effort is relative: S is small, M is medium, L is large compared with the other items. No calendar estimates.

| # | Item | Depends on | Effort | Acceptance criteria |
| --- | --- | --- | --- | --- |
| 1 | **Fix the v3 capability check and the coverage alert** (B1) | None | S | A JS test with four protocol-3, `image`-capable online tablets yields no "Placed, not confirmed" alert and shows "Shows images" chips. Protocol-1 and protocol-2-without-image cases still warn. |
| 2 | **Render acknowledgement and "N of M showing"** (B2) | None | M | The tablet sends `{type:"rendered", render_seq, revision, asset, status}` after paint or failure. The controller card shows "showing rev N" or the failure reason. A test drives a decode failure and sees it in `/devices`. In a simulation, killing one client turns its card offline within 15 s, and reconnecting turns it green with no operator action. |
| 3 | **Atomic "Make a grid" with sane defaults** (B3) | None (merges `/wall/auto` and `/wall/pack`) | M | One request places N tablets in `#N` order as rows×cols, with gap from bezels and fit to tablets, and bumps the revision by exactly 1. Four tablets default to 2×2. The result has no dead bands (sum of widths plus gaps equals the wall width). The 2×2 and 1×4 presets work. A failure changes nothing. |
| 4 | **Identify, Forget in any mode, Rebind in the main UI with suggestion** (B4, B5) | Item 1 (healthy cards) | M | Identify shows the number on the target tablet within 1 s [Sim]. `DELETE /devices/{id}` works while physical is active and removes its slot. A same-model new tablet appearing while a placed one is offline produces a suggestion, and confirming rebinds the slot and number. |
| 5 | **Rebind rewrites saved arrangements** (B5) | Item 4 | S | After a rebind, recalling a saved 2×2 places the new id in the old slot. The response lists the saved layouts that changed. Covered by a test. |
| 6 | **Confirm-on-detect model assignment** (B5) | None | S | A new tablet matching a model shows "Looks like X. Confirm?". Unconfirmed tablets get no physical scale. The existing `test_tablet_models.py` cases are updated. |
| 7 | **Single still path in the physical console, playback behind an "experimental" switch** (B4) | None | S | The physical console can show and change a still image with no playlist session. Start/Pause leave the top bar. The docs' "select it as the wall image" step is true in physical mode. |
| 8 | **Arrange fixes: number order, orientation from viewport, columns choice** (B3) | Item 3 if merged, else standalone | S | Arranging four landscape model-assigned tablets yields mount angle 90° or 270° as reported and number order, and 2 columns gives a 2×2 bounding box. |
| 9 | **Contain fit plus crop and bezel overlay** (B7) | Item 7 | M | `SUPPORTED_FITS` includes `contain`. On a 1×4 wall with a 4:3 image, contain shows the full image with letterbox colour. The stage overlay matches the client crop within 1 wall unit in a geometry test. |
| 10 | **Deployment polish: diagnostics without uploads, hotspot-mode copy, QR, a systemd user unit, a kiosk and sleep checklist** (B6) | None | M | `/diagnostics` answers on loopback in hotspot mode and stays 403 on the tablet port (the `startup_checks` assertion extended). The hotspot UI hides the upload block. After a reboot, the service starts and removes its firewall rule on stop. |
| 11 | **Controller consolidation onto one mm stage** (Section 4) | Items 1-9 | L | One controller page. Logical saved layouts migrate. Legacy routes and `physical-legacy.css` are deleted. The existing test count holds or legacy tests are replaced. The full operator journey in Section 3 passes as a browser test. |
| 12 | **Hardware validation run** (Section 8) | Items 1-3 (needed to observe results) | M (process) | A signed result row in `docs/validation/` for seams, reconnection, and sleep. Video stays MISSING. |

**Top 5 actions, plainly:**

1. Fix the false capability alarm (item 1).
2. Add render acknowledgements so the operator sees what each tablet actually shows (item 2).
3. Replace the four arrange tools with one atomic "Make a grid" that defaults to a seamless 2×2 or 1×4 (items 3 and 8).
4. Make identity robust: Identify, Forget anywhere, and rebind with suggestion that also rewrites saved layouts (items 4 and 5).
5. Run the image-only hardware validation in Section 8 and record it, before any more video or playback work (item 12).

---

## 8. Next demo scope and physical validation checklist

### Demo scope [P]

**Images only.** Four tablets (2× iPad Air 2, 2× Pixel C, as available), on the trusted laptop hotspot with `make hotspot`, controlled from the laptop. Show 2×2, switch to 1×4 by recalling a saved arrangement, and recover from one tablet sleeping and one Wi-Fi drop. No playlist, no video, no uploads.

Run the demo twice:

- **Logical track:** the path proven today, as a baseline.
- **Measured track:** physical console, "Arrange connected tablets" with model assignments confirmed, the image set via the logical controller *before* Apply until item 7 lands.

Compare seams between the two tracks.

### Checklist

Record the date, app SHA, devices with OS and browser versions, launch mode (tab, fullscreen, or Home Screen), and photos.

**Setup**
- [ ] Each tablet: OS auto-lock or sleep set to never, or to the longest setting, while charging. iPad: Guided Access on the client page. Android: the "Stay awake while charging" developer option, or the longest screen timeout. Brightness fixed.
- [ ] Every tablet opens `http://10.42.0.1:8080/client/` and gets a distinct `#N`. Record the time from tap to "Joined".
- [ ] Each tablet's assigned model matches the actual hardware. Record any wrong auto-match.

**Image and seams** (use `tools.calibration.make_grid` at the committed wall's exact mm size)
- [ ] All four tablets show their part within 10 s of "Show on wall". Record the per-tablet time.
- [ ] At every adjacent edge, measure grid-line displacement across the bezel gap with a ruler, in mm. The target from `ACCEPTANCE.md` is ≤ 2 mm beyond the intended hidden gap, plus the 3 mm stated model uncertainty. Photograph each seam.
- [ ] Diagonal lines stay straight across each seam, checked visually and in the photo.
- [ ] A 50 mm grid interval measures 50 mm on both an Air 2 and a Pixel C (scale consistency).
- [ ] Repeat with a real photo or poster. Note any cover-crop surprises.

**Arrangement switching**
- [ ] Save "2×2". Rearrange physically to 1×4, Make or recall "1×4", Apply. Record the operator steps and the time to a correct wall.
- [ ] Recall "2×2" again. All tablets repaint correctly with no re-download (asset cached).
- [ ] Rotate one tablet. Record what the wall shows, whether the controller flags it, and whether rotating back recovers it.

**Recovery** (repeat each at least 5 times; ACCEPTANCE.md's target is 20 trials)
- [ ] Press a tablet's power button to sleep it for 30 s, then wake it. Record the time to correct content and whether the page reloaded or the identity survived.
- [ ] Toggle Wi-Fi off for 30 s, then on. Record the time to correct content.
- [ ] Stop and restart `make hotspot`. Every tablet returns to its slot with no operator action. Record the times.
- [ ] Leave the wall untouched for 2 hours showing one still. Record any sleep, blank screen, or stale content, and battery and temperature notes.
- [ ] Clear one tablet's site data. Rebind it to its old number and confirm the saved arrangements still place it (after item 5).

**Exit:** a filled result row in `docs/validation/HARDWARE-VALIDATION.md` format, with failures retained. Video and optical-timing gates stay **MISSING**.

### What not to build yet

- More playback or video work: sync tuning, rebuffer convergence, video upload ingest. This includes the 100-event optical-capture gate, which applies to slideshow cuts and video, not to a static image.
- Uploads over the hotspot. Copying files to the asset directory is enough for the demo.
- Mirror or independent modes. Phone controller access over the hotspot.
- 15-20-tablet capacity work, a distributed backend, cloud sync, AI generation, or a framework rewrite.
- Server-side per-tablet image renditions, until render-ack timings show decode is a real problem.
- HTTPS migration of the demo fleet, until the origin is final and rebind preserves saved layouts.

---

## Session evidence log

- Isolated server: `uvicorn main:app --host 127.0.0.1 --port 18765` with `TABLET_WALL_DB`, `TABLET_WALL_ASSET_DIR`, and `TABLET_WALL_MEDIA_DIR` under `/tmp/tw-opus-assess-*`. Assets were a generated 600×400 mm grid and a copy of `assets/EXLENT_Cohort_3_Flyer_Temp.png`. Stopped afterwards, and port 18765 confirmed free.
- Screenshots: `/tmp/tw-opus-assess-ctl-initial.png`, `-ctl-tile.png`, `-ctl-image.png`, `-tablet1.png`, `-physical-show.png`, `-physical-system.png`, `-mobile.png`.
- Tests: `uv run pytest -q -p no:cacheprovider` gave 1177 passed. All 9 Node suites passed. `git status --porcelain` is empty before and after.
- Not exercised this session: a real iPad or Pixel C, Safari, model auto-match in the UI (the simulated tablets had platform `other`), the physical Apply flow end to end, HTTPS deployment, sleep and wake, and anything about video.
