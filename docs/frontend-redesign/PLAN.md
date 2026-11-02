# One wall, one operator workspace

This plan gives a person one application to join and name tablets, arrange a wall, add and show images, save useful states, and recover failures. It is the Sol XHigh synthesis of the independent Opus 5.5 Medium and Sol High reviews. Root proceeds to implementation without another human checkpoint. This commit changes planning documents only.

The application remains plain JavaScript with the existing Python backend. [Architecture](ARCHITECTURE.md) defines ownership and contracts. [Acceptance](ACCEPTANCE.md) defines the evidence required to call the implementation complete.

## Decision and outcome

Use a wall-centred workspace with one contextual task panel. Borrow a short first-run and arrangement guide from the reviews' task-flow alternatives. Keep everyday changes direct. The wall and its problems remain visible while the operator chooses an image, moves a screen, or replaces a browser identity.

Keep two explicit output commands, **Apply arrangement** and **Show image**. The existing server commits layout and content separately. A combined **Make live** would require a new transaction, rollback rules, snapshot schema, and migration work. The user's complete operator workflow does not require that addition. Sequential requests must never masquerade as one atomic change.

Keep **Saved arrangements** for geometry and **Saved scenes** for content. Explain what each saves before the action. Do not turn existing records into bundled walls. Both are available in the same workspace. Cross-kind safety copies remain real arrangement records and preserve the current image.

The finish line is a complete first wall and daily recovery through this workspace on desktop and phone. It includes admitted in-app image addition on a supported launcher profile, logical custom editing parity, the reproduced defects in issues #23 and #24, and actual rendered QA with independent shipped clients.

## Evidence used

Both full reports are identified in [REVIEW-SOURCES.md](REVIEW-SOURCES.md). They reviewed `1288dd1`, whose application matches accepted `29148ec`. Planning starts at `c4577af` on `t3/tablet-wall-design-plan`. Neither report is an acceptance pass.

This synthesis inspected these actual images under `/var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/`:

- `reviews/opus-medium-1288dd1/shots/05-tablets-4-joined-desktop.png` shows four connected tablets with no clear placement path.
- `reviews/opus-medium-1288dd1/shots/19-phone-wall.png` shows truncation and navigation below a large stage.
- `reviews/sol-high-1288dd1/evidence/screenshots/05-measured-preview-desktop.png` shows preview geometry carrying the committed wall's showing labels and a crowded review form.
- `reviews/sol-high-1288dd1/evidence/screenshots/10-disconnected-phone.png` shows the reserved offline position and task controls below the first screen.
- `reviews/sol-high-1288dd1/evidence/screenshots/02-compat-desktop.png` shows useful logical editing capabilities that must migrate.
- `visual-study/joined-fields.png` establishes continuity across separate surfaces, warm material, and quiet alignment. It is original art, not a final UI or a serif-font requirement.

Relevant source was read directly, including `operator-grid.js`, `operator-devices.js`, `operator-content.js`, `operator-sync.js`, `physical-stage.js`, composition and forms in `physical.js`, v3 routes and commit helpers in `main.py`, `tabletwall/operator_state.py`, upload admission, hotspot generation, and existing browser drivers. Source confirms the one-time grid defaults, label reset, dirty calibration reset risk, and incorrect removal route. Existing private review evidence establishes the reproduced failures. This planning task does not claim a new runtime reproduction.

## Information architecture and vocabulary

There is one normal operator entry. `/controller/physical.html` remains the canonical workspace during implementation. After parity passes, `/controller/` enters that workspace through a small styled redirect with a usable link fallback. Do not change bookmark behavior before parity is demonstrated.

The header contains the application title and current arrangement summary, a concise live report such as "3 of 4 tablets report image shown", an Issues action, Saved, and Settings. The task navigation contains **Tablets**, **Arrange**, and **Images**. Saved opens arrangements and scenes in clearly labelled groups. Settings contains Check wall, precise measurement, readiness, diagnostics, and preserved Experimental controls. Joining never requires Settings.

| Visible term | Meaning and action |
| --- | --- |
| Add tablets | Show the configured tablet URL, QR, network facts, and live joined list. It does not install or wake anything. |
| Tablet 1, or a chosen name with its number | Stable identity in ordinary UI. A model is secondary information and never replaces a distinguishing name. |
| Quick arrangement | Relative screen shapes with no measured continuity claim. Advanced fields explicitly use relative units. |
| Match real sizes | Measured screens, bezels, gaps, and pinned browser alignment. A model provides approximate measurements. |
| Mounted rotation | Explicit physical direction. Browser orientation and calibration rotation remain separate in details. |
| Arrangement preview | Local positions or grid proposal. **Apply arrangement** writes geometry only. |
| Image preview | Local image and global Fit or Fill choice on the applied arrangement. **Show image** writes content only. |
| Live wall | Committed geometry and scene, with separate current tablet evidence. Server application is not proof that a tablet painted. |
| Remove from wall | Remove this active position now after review. Keep registration, measurements, and saved reservations. |
| Forget tablet | Review an offline registration's removal. Keep saved reservations and history. The old browser can register again. |
| Replace tablet | Deliberately connect an offline identity to a chosen new registration. Review hardware relationship and exact saved impacts. |
| Saved arrangement | Applied positions, dimensions, pins, and sizing policy. The image is excluded. |
| Saved scene | Applied image or test content and its fit/background. The arrangement is excluded. |
| Return point | An actual server-created safety copy, not a guaranteed undo stack or backup restoration. |

Round display measurements sensibly, usually to one decimal mm, while keeping full precision in data. Use singular/plural grammar. Put UUIDs, ETags, revision pins, generations, and raw warnings in Technical details. Ordinary errors use tablet numbers and names.

## Structural candidates

### Candidate A. Wall workspace with task panels

```text
Desktop, 1440 or 1600 wide
+-----------------------------------------------------------------------+
| Tablet wall       Live: 3 of 4 report image shown    Issues  Saved  Settings |
| [Tablets] [Arrange] [Images]                                            |
+---------------------------------------------+-------------------------+
| Arrangement preview                         | Arrange                 |
| Not yet applied                 [View live] | Tablets > Shape > Review|
|                                             | Row of 4   2 by 2       |
|       [1] [2] [3] [4]                       | Order and mounted edges |
|       One continuous image                  | Sizes and gaps          |
|                                             | Change summary          |
| Unplaced: Tablet 5 [Place]                   +-------------------------+
|                                             | Discard  Apply arrangement |
+---------------------------------------------+-------------------------+

Phone, 390 wide, with 320 reflow
+--------------------------------+
| Wall          3 of 4 report shown |
| Issues          Saved  Settings |
| [Tablets] [Arrange] [Images]     |
| Arrangement preview [View live] |
|       [1] [2] [3] [4]           |
| Arrange                        |
| Shape / Order / Review         |
| Actual fields for this step    |
| Change summary                 |
+--------------------------------+
| Discard      Apply arrangement  |
+--------------------------------+
```

One session owns authority. One arrangement owner handles grids and manual edits. The view displays the selected task and its footer. Spatial continuity supports selection, direct manipulation, and recovery. The risk is a long panel recreating today's rail. Bound the task to short sections, use a larger panel for complex review, and keep the footer beside its summary. The phone preview is compact, not a miniature desktop inspector.

### Candidate B. Task pages with a persistent setup workflow

```text
Desktop
+---------------------------------------------------------------------+
| Wall application                               Connected   Settings |
+----------------+----------------------------------------------------+
| Overview       | Arrange: Tablets > Sizes > Shape > Review            |
| Tablets        | Full-width step form                                |
| Images         |                                  [small live wall] |
| Arrangements   | Back                                 Next / Apply   |
| Recovery       |                                                    |
+----------------+----------------------------------------------------+

Phone
+--------------------------------+
| [Wall] [Tablets] [Images] [Saved] |
| Arrange          Step 2 of 4    |
| Size each tablet               |
| Full-width fields              |
| Small live wall                |
| Back                      Next |
+--------------------------------+
```

A shared session would still be necessary. A flow controller would coordinate page-specific drafts and return paths. This shape gives large forms more room, but splits closely related wall operations across pages. Permanent steps slow small adjustments. Separate arrangement, image, and recovery pages invite duplicate state and repeated navigation guards.

Choose A as the base. Adapt B's short guide for a first arrangement or a substantial grid change. Both reviews independently made this choice. Reject a dashboard of metric cards, an everyday second editor, and a permanent onboarding wizard. [ARCHITECTURE.md](ARCHITECTURE.md) screens both candidates against the architect red flags and compares interface depth.

## Visual direction

Follow [REFERENCE-DESIGN.md](REFERENCE-DESIGN.md). The memorable object is the image crossing accurately drawn tablet boundaries. Surround it with warm ivory, aligned readable controls, and thin meaningful dividers. Do not reproduce a portfolio hero, ornamental illustration, serif heading, gradient, or floating card grid.

| Decision | Starting values and use |
| --- | --- |
| Palette | Background `#f8f3e9`, text `#1e1a15`, muted text `#5e574f`, decorative divider `#dcd7cd`, accent `#9d4616`, stronger control outline `#74695c`. |
| Stage | Charcoal `#1e1a15`, ivory text on solid label backing, precise outlines, restrained bezel hatching. The image remains undimmed in previews. Offline live positions use a clear patterned/dimmed treatment and text. |
| Status | Start with success `#246344`, attention `#795500`, error `#a12a24`. Verify actual adjacent colours. Pair each with a word or icon. Accent marks selection/focus, not every kind of warning. |
| Typography | Schibsted Grotesk with a checked local licensed asset and system sans-serif fallback. Body and controls 1rem/1.5, task headings 1.25 to 1.5rem/1.3 at weight 600, small supporting text no smaller than .875rem/1.45. No required CDN. |
| Spacing | Use .25, .5, .75, 1, 1.5, 2, and 3rem. Default control height at least 2.75rem, 6px corners, 1px control boundary, 2px focus ring with 3px offset. |
| Layout | Shared outer edges, 24 to 32px desktop padding and 16px phone padding. Stage flexes. Task panel starts around 24rem and can reach 30rem when review needs it. Stack when both useful stage width and readable controls no longer fit, initially around 68rem. Text determines the final breakpoint. |
| Motion | Brief action feedback only. Reduced motion removes smooth scrolling, decorative transitions, and stage flashes. Identify uses a static high-contrast number rather than requiring flicker. |

Light mode is the near-term target. A new theme switch is not required. The reference's dark values remain guidance if an existing supported dark mode must be preserved. No token generator, component package, or CSS framework is justified. These values are starting decisions, not a measured contrast pass.

At desktop height, keep the stage and task review useful together. At phone width, navigation precedes task content, the preview is about 10 to 14rem tall when space permits, and the footer stays local to the task with bottom padding. An expanded stage is optional. Do not force stage, long messages, every nav item, and every action into one fixed viewport at 320px or with enlarged text. Reflow and access take priority. Full names remain available in the roster and task heading even when the diagram shows only numbers.

## Exact operator workflows

### Join, identify, name, and set up screens

1. The empty workspace shows **Add tablets**, the configured tablet URL and QR, and "Open this page on each tablet on the same network. Keep it open." Show unknown network facts as unknown.
2. Four independently registering clients appear without reloading the console. Each gets its durable number and a distinct default name. Show connected but unplaced tablets outside the committed wall, with an Arrange action.
3. Identify one tablet, or **Identify selected** for the explicit selection. Results stay attached to the request's tablet IDs. Identify is transient and may obscure the image.
4. Names are optional during first setup. A name field has Save and Discard. Retain unsaved name, profile, calibration, and model form drafts by tablet ID across selection and task changes. Preserve dirty values when telemetry updates. Resolve conflicting remote edits before saving.
5. Arrange begins with the currently placed tablets plus eligible new connected tablets. Before the operator edits membership or reviews a preview, automatically include a newly online, never-touched row and refresh its untouched relative aspect from fresh viewport data. Keep stable number order. Never reselect an intentionally excluded row or overwrite a manually edited size.
6. When membership/order has been edited or a preview reviewed, new arrivals appear as "New tablet available" with **Include**. They do not alter the proposal. Registration can invalidate its ETag and require a fresh review. No reload is needed to continue.
7. Offer **Quick arrangement** or **Match real sizes** with a one-sentence difference. For Match real sizes, show model suggestions as suggestions. Bulk confirmation lists the actual selected names/numbers, chosen model, approximate uncertainty, and a hardware-check declaration. No screen signature auto-confirms hardware. Mixed models can be selected by group; manual measurement remains available.
8. Bulk confirmation uses the existing per-tablet endpoint sequentially. Show progress and exact completed, failed, and untouched tablets. Capture the selection once. Use the ETag returned by the previous successful write, stop on conflict or uncertain completion, and reconcile before asking to retry. Never present the operation as atomic. [Architecture](ARCHITECTURE.md) defines the stricter chain rule.
9. Ask how the top edge is mounted. Offer one explicit common rotation with a diagram and per-tablet overrides. No default declaration is silently submitted. If 90 versus 270 is ambiguous, require the operator's choice. Existing valid pins and stored angles may be preserved visibly. Browser telemetry never resolves physical ambiguity on its own.

The common four-identical-tablet setup needs one group model confirmation and one common mounting declaration. It must not require visiting System four times. The scripted uncomplicated path targets at most 16 deliberate operator actions from opening Add tablets through Apply and showing a supplied image. Client-page visits, optional naming, file-picker internals, and manual calibration are counted separately. Record the actual count rather than claiming a benchmark or a universal usability result.

### Arrange and adjust

Offer Row of N and a suitable two-row grid, plus Custom rows/columns. Show actual selected tablets in stable number order with Identify, earlier/later buttons, and drag reorder as an enhancement. Show holes, excluded active positions, extra gaps, wall padding, and sizing policy when relevant. Removing unselected active reservations needs explicit acknowledgement.

Preview once with exact selected identities, dimension provenance, rotations, release list, and guard. Keep warnings readable beside **Apply arrangement**. When the representation changes, review the real safety-copy consequence. Applying affects geometry only and returns to Live wall with reports pending. Cancelling affects no durable wall state.

Existing walls open directly for manual edits. Preserve pointer drag with threshold/capture and Escape cancellation, numeric position/size, arrow and Shift-arrow nudge, rotation, undo/redo, participation, packing, fit bounds, and fixed bounds. For relative arrangements also preserve resize, bezels, snap spacing, tiling, and custom sizes. Use the same draft owner and Apply action for both representations. No everyday legacy detour is permitted after migration.

Only one output preview is active at a time. Changing between an unfinished arrangement and image task offers **Apply arrangement / Discard / Stay**, or **Show image / Discard / Stay** for an image. Navigating to a tablet for inspection retains the output draft. A conflicting immediate command, including measurement changes, lifecycle writes, or recall, resolves that draft first. No hidden multi-command commit exists.

### Add, choose, preview, and show an image

Images contains **Add image**, thumbnails, names/dimensions, a small local filter for a long inventory, Refresh, selection, Fit/Fill, preview, and **Show image**. Native labelled thumbnail buttons are sufficient. Upload publication and scene application remain separate.

Choose an existing image or add PNG/JPEG. Show transfer progress, then processing, then a successful library item selected locally. Do not show the image automatically. **Fill wall** previews cropped edges. **Show whole image** previews bars. Both use the one wall-wide transform, not per-tablet fits. Crop, bezel, and quality estimates are labelled estimates.

Show image applies to the committed arrangement only. Keep the local selection through refusal or conflict. Report "Image applied. Waiting for tablet reports" before reporting current matching paint. Reload restores the committed image, fit, geometry, and labels. Previous-content restore remains an explicit content command and an in-memory convenience, not a durable undo promise.

A missing/stale asset remains visible by name/identity as unavailable. **Choose replacement image** opens this same panel. Never silently select the first item or relabel broken bytes as loading. A selected item disappearing during preview disables Show until replacement or successful refresh.

### Supported image-addition launch

Add `--operator-uploads` to the existing hotspot launcher. Document the supported command as `rtk make hotspot ARGS='--operator-uploads'`. This is a future launch instruction, not authorization to run or change the live hotspot during this work.

With the flag, launcher-controlled backend environment sets upload mode to `loopback`, binds the backend to `127.0.0.1`, sets the exact operator origin, and prints "Image uploads: this computer only" beside the operator URL. The tablet URL remains a different Caddy listener. The opt-in is per launch, not an invisible persisted security change. With no flag, uploads remain disabled. Refuse inherited non-disabled upload modes and continue refusing an authentication-enabled HTTP trial. The flag alone enables uploads for this profile. Preserve the separate authenticated HTTPS proxy profile.

Upload admission keeps the existing exact single-Origin requirement, local transport-peer requirement, and refusal of forwarded headers. Tablet Caddy keeps denying uploads, inventory, operator controllers/sockets, diagnostics, and wall writes even with spoofed Origin or operator headers. Tests must exercise the generated Caddy configuration, not only a handwritten reference. This is a trusted single-operator computer path; a local process can forge Origin, so it is not local-user authentication.

The UI uses server capability, never a browser security toggle. Enabled mode exposes Add image. Disabled mode says "Adding images is off for this launch" and points to launch help in Settings, including the supported flag. Folder import remains an advanced fallback. Unknown admission or a rejected request has a scoped explanation and Retry after refresh. A permanently disabled button with filesystem instructions does not satisfy acceptance. Remote phone upload is not promised by this loopback profile; phone operators can choose existing images, and upload UI still needs narrow-layout QA on the admitted origin.

### Save and recall

Saved contains two labelled groups. **Save arrangement** captures the applied geometry. **Save scene** captures the applied content. Dirty work must be applied or discarded explicitly before saving or recalling. Each save explains its scope, validates the existing name rules, and asks before replacing an existing name.

Arrangement recall reviews tablet positions, offline/missing reservations, pin availability, image preservation, and any cross-kind safety copy. **Recall arrangement** is the explicit commit. Saved scene recall previews its content on the applied geometry and ends with **Show scene** using the guarded scene-recall route. Unavailable content cannot be presented as ready to show.

Keep existing names and record meanings. Report the actual returned safety-copy name and give it a direct recall action. Existing storage lacks origin/time metadata that reliably separates all automatic copies from user saves. Do not infer provenance from a name prefix, silently rename records, auto-prune them, or promise a complete time-labelled history. A session-local latest-return-point callout is allowed when it comes from an actual response. A durable history/schema expansion is deferred.

### Recover, remove, forget, and replace

Issues opens the exact named tablet and a next action. Connected/presence, mapping readiness, and current render evidence are distinct. Offline positions remain reserved and do not look confirmed. Show image loading only when an image is intended. With no image, say "No image chosen".

For an online fetch/decode failure, offer **Retry image**. **Reconnect** requests a new browser socket while retaining its identity. For offline tablets, instruct the person to check power, network, and the tablet page. For zoom/orientation mismatch, explain restoring the recorded browser mode or reopening screen setup. Link precise measurement and diagnostics when needed. Do not offer remote wake or claim screen power state.

**Remove from wall** names the selected tablet, resolves incompatible drafts, and confirms immediate removal while retaining registration and saves. Call `POST /api/v3/devices/{id}/remove`, including for the final measured tablet. A separate **Clear wall** uses the existing explicit-confirmation endpoint. Do not empty a whole-layout PUT to simulate either command.

**Forget tablet** is offline-only. Review fresh impact, name/number release, preserved histories and saved reservations, and explicit active-position removal if applicable. Cancellation changes nothing. A reconnect before confirmation refuses the plan. Forget is not revocation.

When a new tablet joins and offline reservations exist, offer "New tablet joined. Place it or replace an offline tablet." Require a chosen old identity even if only one exists. Replacement may be opened from either subject. Ask same hardware/new browser versus different hardware. List exact selected saved arrangements and untouched reservations. Preselect only valid snapshots proven to reference the old identity; permit changes. Review transfer of name/number, active position, historical pins, and the connection guard. Different hardware cannot inherit measured calibration. Preview and confirm are the existing guarded lifecycle operation, not a client loop. Invalidate the plan after a connection, snapshot, selection, or authority change.

## States, keyboard, and phone behavior

| State | Required behavior |
| --- | --- |
| First load | Retain the stage frame, say what is loading, and disable unsafe actions. Unknown is not empty. |
| No tablets | Add tablets leads. A readable HTML instruction replaces tiny SVG empty-state text. |
| Tablets but no arrangement | Show unplaced names/numbers and Arrange. No disabled Add dead end. |
| No images | Offer admitted Add image or factual launch help. Keep Arrange usable. |
| Draft/preview | Label the stage Arrangement preview or Image preview. Keep live report wording outside that geometry. Provide View live and the local task footer. |
| Slow/stale connection | Retain useful data and typed values, label status stale with age, and offer scoped retry. Never revive old showing evidence. |
| Conflict | Keep exact local intent and its original guard. Say "The wall changed elsewhere. Your edits are kept." Offer Review latest and Keep editing. Applying remains blocked until explicit review/rebuild. |
| Validation error | Put a specific message beside the field, associate it programmatically, and focus the first invalid field on submit. |
| Pending/failed command | Disable duplicate submission for that task, keep its target visible, and show whether completion is known. Timeout requires reconciliation before retry. |
| Offline/unavailable | Keep the reserved position and current reason. Never substitute fresh pins or another image without consent. |
| Unsupported schema/client | Keep a useful read-only view where possible, show update guidance, and refuse replacement writes. |

Use native buttons, labels, selects, fieldsets, progress, details, and dialogs. Provide skip links and labelled landmarks. Navigation uses standard buttons/links with an explicit current task, not an incomplete custom tab widget. The tablet list is the complete textual and keyboard alternative to stage selection. Native gallery buttons expose selected state. Every stage tile has a name/number and a non-colour selection indicator.

Keep focus on roster selection during a normal selection change and on the current form during runtime updates. An explicit Open task action may focus its heading. After a dialog closes, return focus to its trigger. If a removal destroys that trigger, choose the next useful tablet or Add tablets. Never focus the inspector on every selection/status render. Stable keyed DOM must preserve input caret, selection, and IME composition.

Arrow nudges apply only when the stage edit control is focused, never inside text/number inputs. Reorder has Earlier/Later buttons. Undo/redo shortcuts must not hijack text editing. Escape cancels a drag or closes the active dialog before any outer task. Desktop panels are nonmodal. Phone task content is a full-width inline view with Back, not nested drawers. Dialogs alone contain focus and make background inert.

Use polite scoped completion announcements and actionable alerts. Heartbeats are silent. Verify 4.5:1 normal text, 3:1 large text and essential control/state boundaries. Solid-backed tile labels replace text halos. At small sizes show numbers on the stage and full names in the list. Safe-area padding, scrolling, and virtual keyboard behavior must keep the footer and errors reachable. [Acceptance](ACCEPTANCE.md) sets exact viewport, zoom, text, focus, and recovery checks.

## Review recommendation dispositions

| Source recommendation | Disposition and reason |
| --- | --- |
| Both: wall-centred workspace, contextual tasks, first arrangement guide | Accepted. Candidate A with a short guide and one session. |
| Both: join/model setup, thumbnail library, upload/selection together, plain language | Accepted, including in-app addition on an admitted supported launch. |
| Both: truthful live status, retained conflicts, exact lifecycle semantics and measurement uncertainty | Accepted as release requirements. |
| Opus: one Make live for image and arrangement | Modified to task-local Apply arrangement and Show image. No new atomic transaction is needed for the requested workflows. |
| Opus: Saved walls bundle geometry and content | Deferred. Preserve existing arrangements and scenes without data reinterpretation. |
| Opus: bulk model confirmation and group setup | Accepted with explicit selected identities, hardware declaration, per-write ETag chain, and partial outcomes. No automatic signature-based proof. |
| Opus: replacement prompt and preselected snapshots | Modified. Offer contextual placement/replacement, but require exact old/new subjects and valid proven references. Never infer hardware relationship. |
| Opus: silently create safety copy and call it Undo point | Modified. Preserve the review consequence and actual returned record. No silent pruning or invented history metadata. |
| Opus: move focus to inspector on selection | Rejected as a blanket rule. Only explicit task opening moves focus. Runtime and roster selection retain it. |
| Opus: stage-first phone with global pending bar | Modified. Navigation precedes task content, stage is compact, and the footer belongs to the active task. There is no global combined pending action. |
| Opus: clipped client recovery screen is a proven CSS bug | Trigger remains unverified because its run used a mismatching simulated signature. Required responsive recovery checks cover both orientations; fix reproduced clipping if present. |
| Both: retire compatibility navigation | Accepted only after full listed parity, including logical drag/resize/bezels/snap/custom sizing, saved scenes, per-tablet colour, and unavailable-image replacement. |
| Sol: preserve advanced measurement, diagnostics, test patterns and Experimental | Accepted behind relevant details/Settings, with problem-linked access. Per-tablet show participation remains in Arrange details. |
| Sol: structured upload capability reasons/limits | Deferred unless necessary for truthful launch messaging. Existing boolean plus request outcome suffices. |
| Sol: persistent shared drafts and atomic bundled presets | Deferred. In-session drafts are retained; unload warns. Durable wall restart recovery is required. |
| Sol: asset deletion/rename, model catalogue administration, network editing, remote wake/install, expanded video, backup restoration UI | Deferred. They need separate product/security contracts and are unnecessary to complete this task. Read-only backup facts stay honest. |

## Implementation sequence and ownership

Use at most four workers with the disjoint ownership in [ARCHITECTURE.md](ARCHITECTURE.md). No worker creates an independent editor or writes another owner's files. Root integrates and reviews the contracts between phases.

1. Domain worker defines the single session and keyed draft behavior, then fixes #23 and #24 using focused behavior tests. Shell worker settles markup hooks and the new style entry concurrently. Backend/deploy worker can start the upload flag and negative admission tests once the launch contract above is fixed. Verify fresh late joins, form retention, and last removal before building on those paths.
2. Shell and domain workers connect one coherent Tablets > Arrange > Images journey. Reuse geometry, grid guards, measurement helpers, image admission and current-render predicates. Verify a first wall with four real shipped browser clients and inspect desktop/phone renderings before expanding advanced panels.
3. Domain and shell workers migrate logical/custom editing, saved scenes, colours, and unavailable-image recovery. Verify every parity row in acceptance. Then retire the compatibility entry and remove obsolete primary style imports and dead new-path writers. Keep backend compatibility routes for existing clients.
4. QA worker completes the portable redesign driver, fault injection, keyboard/focus, ingress, and viewport evidence. Root runs the app and performs the render/inspect/critique/fix/verify loop with each owner. Integrate small fixes under the same ownership. Run focused suites and relevant Python lint/type checks, followed by the repository's required integration checks once the code is stable.
5. Root obtains the already requested independent review of the implemented result, resolves proven findings, inspects the final diff, and commits/integrates under the parent task. No implementation worker mutates live data, services, network, browser sessions, or real tablets.

The throughput checkpoint is one complete private first-wall journey, not a number of finished files. If that journey still needs a legacy detour, loses a draft, or cannot add an image, stop adding features and repair it. Completion requires every mandatory acceptance scenario with retained evidence and an explicit list of environmental limits. No full Python or browser acceptance suite was run for this planning commit.
