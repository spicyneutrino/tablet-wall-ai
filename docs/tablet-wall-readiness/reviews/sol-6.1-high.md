# Independent assessment of tablet-wall-ai

Reviewer: GPT 6.1 Sol, High, through Codex. Assessment date: 2026-11-01.
Reviewed commit: 0ff56e30dfd6b2f92995569faa2d6e7fdc90fa8f.

The goal is a dependable wall in which several browser tablets show parts of one coordinated image. This assessment covers the current implementation and the practical work needed to operate it without developer assistance. It makes no source changes and does not incorporate another model's assessment.

## Readiness verdict

**Ready for a supervised, images-only demonstration. Not yet ready to call an unattended tablet wall dependable.** The main gap is integration and operational feedback, followed by device recovery and deployment rehearsal. The project already contains enough geometry, persistence, media validation, and socket infrastructure to improve the current product without a framework rewrite.

The existing logical wall has user-reported hardware evidence in 2x2 and 1x4 arrangements using iPads and Google tablets. That is useful evidence of the basic image-wall idea. It does not establish that the newer physical-layout path renders at the intended scale, that browser insets are modeled correctly, or that the installation recovers from OS sleep.

### Evidence boundaries

- **Source-confirmed** means behavior traced in the reviewed code, with file and line links.
- **Executed software evidence** means checks I ran in this assessment. These include temporary-database API probes, focused pytest tests, and Node tests.
- **User-reported hardware evidence** means the experiments described in the task. I did not repeat them.
- **Hypothesis** means an unmeasured risk or likely consequence requiring an experiment.
- **Proposal** means future behavior, not a current capability.

I performed source and test review only. I did not open a browser, automate a shared browser, inspect rendered desktop/mobile screens, or take new UI screenshots. Node canvas and DOM mocks are software tests, not simulated-browser visual observations. Prior reports of 1,177 Python tests, all Node suites, lint, type checks, and browser/concurrency checks passing are supplied historical software evidence. I did not rerun those complete checks.

The supplied saved wall was a logical 4-tablet row, 320x60 units, showing a cover-rendered 2000x745 image. I did not open or mutate that live database. The reusable Air 2 and Pixel C measurements are accepted inputs for this assessment. More measurements are not a prerequisite to the recommendations.

## The five actions to take first

1. **Make one controller accurately show and change the active image in both layout kinds.** Include the still-image library, current content, layout, and real state in the physical console. Stop returning a synthetic colour wall as the result of an image command.
2. **Show exactly what the image will lose.** Offer Fill and Fit whole image, with a preview of screen areas, bezels, gaps, and global cropping before applying.
3. **Report what each tablet has rendered.** Separate connected, calibrated, loading, image displayed, failed, hidden, and stale. Give the operator a targeted retry.
4. **Finish the tablet lifecycle.** Add durable names, temporary Identify, clear Remove versus Forget behavior, and replacement handling that preserves saved arrangements.
5. **Make 2x2 and 1x4 repeatable saved actions.** Reuse the existing packing, drafts, model records, and snapshots. Add ordering, conflict checks, and a return point instead of another layout engine.

Do not build AI image generation, a cloud service, a new framework, distributed state, a layout optimizer, optical video synchronization, or a native device-management system yet. Mirror and independent-screen modes are future proposals after spanning images meet the acceptance checks below.

## Strong capabilities to retain

The organizing data is already sensible. There is an active layout and a separately saved scene, immutable display-profile and calibration revisions, browser endpoint identities, and process-local connection state.

- **Durable changes precede notifications.** The central commit boundary copies and validates the proposal, saves it, and then updates memory. Roster changes use a shared transaction with rollback of memory. This is a valuable foundation for reliable layout changes. [main.py:445](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:445), [state.py:96](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/state.py:96).
- **Physical geometry is explicit.** Body size, active panel, bezels, mount rotation, CSS-to-panel calibration, and canvas backing pixels have separate transforms. One source-to-wall fit determines all slices. Keep this separation. [geometry.py:1](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/geometry.py:1), [geometry.py:178](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/geometry.py:178).
- **Saved measurement revisions are real records.** Display changes append revisions. Saved layouts reference specific revisions, and model history preserves the matching model snapshot. Changing a current model need not silently rewrite an old layout. [displays.py:1](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/displays.py:1), [tablet_models.py:100](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/tablet_models.py:100).
- **Known hardware does not require starting calibration again.** The measured iPad Air 2 and Pixel C records, signature matching, explicit override, and manual mode already exist. They carry provisional 3 mm uncertainty. [tablet_models.py:8](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/tablet_models.py:8).
- **Physical arrangement edits are drafts.** Apply uses an ETag. A logical-to-physical apply saves a logical return point in the same commit path. Packing and fitting already handle measured bodies and offline reservations. [main.py:1912](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:1912), [main.py:2011](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:2011), [sizing.py:46](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/sizing.py:46), [physical-sizing.js:67](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical-sizing.js:67).
- **Tablet image loading has substantial defensive behavior.** It bounds fetch/decode attempts, discards stale results, releases old bitmaps/object URLs, shows loading/failure states, and supports retry. Reconnection replays current state. The selected Node tests exercised these contracts. [client.js:1326](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/client/client.js:1326), [client.js:1448](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/client/client.js:1448).
- **Slow sockets have bounded writers.** Frame/byte budgets, send deadlines, ordered control frames, and coalescing of complete snapshots constrain backlog. The worker lock also prevents two normal app processes from owning one database. [writer.py:33](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/writer.py:33), [workers.py:13](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/workers.py:13).
- **The content and ingress boundaries are thoughtful.** Images are content-addressed and validated, managed ingest uses a bounded subprocess, and the tablet proxy permits an explicit route/method list. Backups verify referenced bytes before publication. These deserve refinement rather than replacement. [assets.py:1](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/assets.py:1), [media_limits.py:1](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/media_limits.py:1), [tablet-routes.caddy:1](/var/home/oak/Codes/projects/tablet-wall-ai/deploy/tablet-routes.caddy:1), [backup.py:1522](/var/home/oak/Codes/projects/tablet-wall-ai/deploy/backup.py:1522).

## Concrete blockers and what resolves them

These block dependable operation or a stated operator need. They are not all defects in the geometry engine.

### 1. The two controllers do not share an accurate image-wall state

**Source-confirmed and executed, high priority.** GET /wall returns 409 when a physical layout is active. An existing v2 controller is closed when the physical draft is applied. A newly connected v2 controller is nevertheless accepted and receives a synthetic 2000x1000 colour wall with no placements. PUT /scene can successfully set a physical wall's image but returns that same synthetic logical envelope.

The isolated probe reproduced all of those HTTP/snapshot results. The existing logical image handler normalizes that response and announces that it is showing the image. The physical console has playlist controls and sends users to the logical controller to add files. Its configuration response does not include the active scene. Its stage draws bodies, panels, and a grid rather than the image crop.

An operator can change the physical wall while seeing an unrelated logical representation, or confuse a persisted still with a playlist frame. This also makes the claim that the new console covers the old console's tasks premature.

**Fix.** Supply one authoritative operator state containing layout kind, actual scene, content identity, and revision. Move still-image selection/upload and active-image presentation into the physical console. An incompatible logical controller should present an explicit migration/read-only screen. It must not display a plausible substitute wall. Keep logical arrangements available as an advanced compatibility choice.

Evidence: [main.py:1183](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:1183), [main.py:1235](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:1235), [main.py:1867](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:1867), [main.py:2058](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:2058), [main.py:3114](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:3114), [state.py:280](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/state.py:280), [controller-inventory.js:876](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/controller-inventory.js:876), [physical.html:469](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical.html:469), [physical.html:646](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical.html:646), [physical-stage.js:51](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical-stage.js:51).

### 2. Full-image fitting is absent from the product contract

**Source-confirmed and executed, high priority.** The public scene schema accepts only cover. The probe confirmed fit=contain returns 422. The controller always sends cover. The physical geometry helper can calculate contain, but that does not make it an available product feature. Playback plans also hardcode cover.

A poster or photograph with a different aspect ratio loses edges without a useful physical coverage preview. The physical stage cannot tell the operator which parts fall behind bezels or outside the chosen bounds.

**Fix.** Add global Fill and Fit whole image through validation, persistence, static rendering, slideshow plans, and preview together. Add a single wall-level focal position for Fill only after the basic choices work. Show the uncropped source behind a screen-coverage mask. Explain that Fit preserves the source within the wall bounds; bezels and holes still hide pixels. Do not independently fit each tablet, which would destroy continuity.

Evidence: [main.py:338](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:338), [protocol.py:61](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/protocol.py:61), [geometry.py:121](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/geometry.py:121), [main.py:2186](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:2186), [controller-inventory.js:897](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/controller-inventory.js:897).

### 3. Connection health does not establish image health

**Source-confirmed, high priority.** Online means an open device socket with sufficiently recent contact. The physical health summary counts online devices, saved profile/calibration pairs, placement, and wake-lock warnings. It does not establish that the current viewport matches the pinned calibration or that the current image decoded and painted.

The static client failure path updates the local panel and console. The device receive loop has heartbeat, viewport, readiness, and video messages, but no static-image render-result contract. Playlist readiness is not a replacement for static-image status.

**User impact.** An apparently healthy wall can contain a failed image, a calibration fence, or an old visible image without the operator seeing a specific cause. This is a source-based consequence, not a failure observed on real tablets in this assessment.

**Fix.** Add a bounded per-tablet report keyed by connection, generation, content revision, asset, and mapping revision. Report loading, displayed, failed, hidden, and calibration-blocked states, with the last receipt time. Reject stale reports. A displayed acknowledgement proves application rendering intent, not photons or optical synchronization. Add per-tablet Retry image and Refresh connection actions that preserve identity and placement.

Also decouple read-only diagnostics from upload admission. The probe confirmed GET /diagnostics returns 403 when uploads are disabled, the required configuration of the HTTP hotspot launcher.

Evidence: [state.py:162](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/state.py:162), [state.py:371](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/state.py:371), [physical-stage.js:408](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical-stage.js:408), [physical.js:501](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical.js:501), [client.js:1363](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/client/client.js:1363), [main.py:2818](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:2818), [diagnostics.py:85](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/routes/diagnostics.py:85), [media.py:871](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/media.py:871), [hotspot.py:300](/var/home/oak/Codes/projects/tablet-wall-ai/deploy/hotspot.py:300).

### 4. Tablet removal, naming, and replacement remain incomplete

**Source-confirmed and partly executed, high priority.** The physical console can delete a slot through its draft. Forgetting the roster device uses a route fenced to logical layouts; the probe confirmed 409 in physical mode. Physical device lists combine roster identities, profile identities, and layout references, so removing a slot alone need not remove the old tablet from the operator's list.

The model creates a profile label such as iPad Air 2. There is no separate durable operator alias in the registration shape. Small display numbers are leased and can be recycled after an offline interval when another device needs a number. Browser identity lives in origin-scoped localStorage.

Rebind usefully copies measurements/model history and moves the active placement, but its documented behavior leaves saved layouts naming the old browser ID. Recalling 2x2 after replacement can therefore reserve the old identity again.

**Fix.** Separate the UI actions:
- Remove from arrangement leaves the known tablet and saved arrangements.
- Forget browser removes the roster entry and explains reconnection behavior.
- Retire/revoke tablet prevents silent return once pairing exists.
- Replace tablet previews which active and saved arrangements change.

Give each installed tablet an independent name such as Upper left. Keep the browser UUID and display number as secondary diagnostics. Add a temporary remotely triggered Identify overlay with an expiry and automatic return to the image. For rebind, transactionally update explicitly chosen saved layouts or introduce a stable installed-tablet reference. Do not silently rewrite historical measurements. Require the operator to confirm whether replacement means the same hardware at a new origin or different hardware needing its own model.

Evidence: [main.py:227](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:227), [main.py:1029](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:1029), [main.py:1074](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:1074), [state.py:170](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/state.py:170), [physical.js:680](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical.js:680), [physical.html:238](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical.html:238), [client.js:289](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/client/client.js:289).

### 5. Automatically adapted physical calibration is still an estimate

**Source-confirmed approximation, hardware result unverified.** Matching uses screen dimensions, DPR, and platform family. That is a hint, not a hardware credential or unique fingerprint. A real collision with other models is a hypothesis here, not a demonstrated bug.

Model adaptation assumes zero inset in fullscreen and centers the missing viewport area in tab or standalone mode. Browser toolbar placement is not measured by that calculation. Mount angle and reported browser orientation are correctly separate inputs, but an operator must understand both. A saved matching calibration currently receives a favourable status without demonstrating physical seams.

**Fix.** Keep the supplied models and their uncertainty. Display Detected model, Model estimate, Manual calibration, and Physically checked as separate facts. Expose assumed browser inset, current launch mode, zoom fence, and pinned measurement revision. Use the present measurements for the next demonstration. Record physical confidence afterward without pretending an additional calibration form is mandatory before showing an image. Prefer explicit model confirmation during joining and warn when live viewport/mount conditions differ.

Evidence: [tablet_models.py:23](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/tablet_models.py:23), [tablet_models.py:100](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/tablet_models.py:100), [physical.js:1693](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical.js:1693), [client.js:2280](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/client/client.js:2280), [PHYSICAL-CALIBRATION.md:18](/var/home/oak/Codes/projects/tablet-wall-ai/docs/PHYSICAL-CALIBRATION.md:18).

### 6. Deployment and recovery are not yet a complete appliance workflow

**Source-confirmed boundaries; real operation unverified.** The HTTP hotspot launcher has persistent data, startup route checks, child supervision, and owned-firewall cleanup. It deliberately disables uploads and requires manually keeping screens awake. The service template is a placeholder reference, not an installed, validated service.

Wake lock is best effort and secure-context dependent. Fullscreen requires a tablet gesture. There is no app-level ability to power a tablet on or unlock it. The implementation contains reconnection logic; that does not demonstrate recovery of a browser frozen by its OS.

**Fix.** Choose one supported local deployment profile first. Provide a preflight with explicit data paths, intended interface/origins, current security mode, content availability, and actionable startup failures. Rehearse restart, backup, restore, and loss of the network on that profile. Add log rotation and a visible last successful backup. Use OS-side kiosk/power instructions for the actual devices. Treat a black image as blanking, not power control.

Evidence: [hotspot.py:205](/var/home/oak/Codes/projects/tablet-wall-ai/deploy/hotspot.py:205), [tablet-wall.service.example:1](/var/home/oak/Codes/projects/tablet-wall-ai/deploy/tablet-wall.service.example:1), [client.js:2180](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/client/client.js:2180), [client.js:2378](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/client/client.js:2378), [client.js:4470](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/client/client.js:4470), [OPERATIONS.md:1](/var/home/oak/Codes/projects/tablet-wall-ai/deploy/OPERATIONS.md:1).

## A streamlined operator journey

This is a proposal. It refines current capabilities except where explicitly called new.

1. **Start.** Run the supported launcher. The local controller opens an image-wall home screen with the tablet-reachable address, Copy, and a QR code. Show server/data location and a concise status. Put revision, generation, ETag, and raw paths in Details.
2. **Join.** A tablet opens the advertised URL in its intended browser/launch mode. It shows a large short join code and its display number. A pairing window is a new capability. For an initial trusted-hotspot demonstration, retain open join but label it accurately.
3. **Identify and name.** Select the new tablet, trigger Identify, and give it a persistent name. Confirm the detected Air 2 or Pixel C model or choose an explicit override. Unknown hardware can still use a logical arrangement; clearly label that scale is not calibrated.
4. **Arrange.** Select four installed tablets and choose 2x2 or 1x4. The existing packing engine produces a draft. Reorder by dragging or with Move earlier/later buttons. Rotate the mounted body separately from browser orientation. Show active screen, bezel, gap, and current scale. Offline saved spots stay visible.
5. **Show.** Pick a curated or uploaded image, choose Fill or Fit whole image, and inspect the wall preview. Apply once. Show each tablet's progress until all expected screens acknowledge the current content. Keep the prior picture while preparing where possible, with an honest transition state.
6. **Switch.** Save named arrangements such as Four square and Four wide. A recall previews device availability and crop changes. Apply changes layout while preserving content unless the operator explicitly chooses a combined saved presentation. Keep a previous committed return point.
7. **Recover.** Click the affected tablet and see one cause with one next action. Retry image, reconnect, restore zoom, confirm model, or replace identity. Use the existing rebind path for a new browser origin, with saved-layout repair included.
8. **Remove.** Remove a tablet from the current arrangement without erasing its model. Forget or revoke it only through the separate lifecycle action. Show saved-arrangement references before destructive cleanup.

A combined saved presentation is useful later, but layout, content, and playback should remain separate stored concepts. The UI can offer Save arrangement and Save presentation without collapsing their semantics.

## Controller, tablet UI, and mode proposals

### One console with task-based controls

Keep the physical console's stage and selected-tablet inspector as the base. Bring over the logical console's still-image inventory and useful keyboard/touch controls. Use four primary tasks: Wall, Tablets, Content, and System. Arrangement presets belong beside the stage, not among low-level system settings.

Wall should show the current image, current arrangement, pending draft, Show image, Apply arrangement, and a readable health summary. Tablets should offer naming, Identify, rotation, model confidence, recovery, and removal. Content should merge curated and uploaded stills into one browsable library while retaining provenance. System should hold startup, security, diagnostics, backup, and advanced measurement forms.

The first screen should optimize for a still image, with experimental slideshow/video controls behind an explicit switch. Playback Start currently occupies prominent space even though the supported hardware scope is static images. This is a source-based workflow critique, not a rendered-layout judgment. [physical.html:17](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical.html:17), [physical.html:95](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical.html:95).

Consolidate overlapping arrangement verbs. Explain Fit wall to tablets as a canvas sizing policy, Pack as moving bodies, and Fill image as content fitting. They solve different problems. Prefer named presets for the common case and reserve raw coordinates, padding, nudges, and revision selectors for advanced use. The current code already distinguishes fitting from packing. [sizing.py:10](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/sizing.py:10), [WALL-SIZING.md:1](/var/home/oak/Codes/projects/tablet-wall-ai/docs/WALL-SIZING.md:1).

Retire the second editing UI only after parity checks cover still selection, uploads, saved content, empty/error states, joining, and keyboard operation. Do not make deleting files or introducing a framework the first consolidation step.

### Tablet UI

Keep an unobstructed image during normal operation. A tap reveals the existing number/HUD plus the installed name and concise connection/render status. The setup drawer should contain Enter fullscreen, Keep-awake status, Retry image, and a link to ruler mode. Exit setup should be explicit.

Identify should briefly overlay a large number/name without changing the persistent scene. Blank/unblank should be a deliberate display state with a remote return action. Do not label it Sleep or Power off. A failed image must remain an actionable failure, with the controller receiving the same reason.

The current client already has a fading HUD, takeover handling, a fullscreen button, and local image retry. Extend those rather than introducing a tablet dashboard. [client/index.html:13](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/client/index.html:13), [client.js:410](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/client/client.js:410), [client.js:4494](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/client/client.js:4494).

### Modes

Spanning image is the primary content mode. Logical versus physical is a geometry choice within it. Setup/ruler, temporary Identify, blank, and recovery are operational states, not additional content products. This separation avoids one oversized mode selector mixing unrelated choices.

Mirror, in which every tablet shows the complete source, is a useful optional future mode for readable signage or comparison. Independent images per tablet are another future proposal and would require content assignment, saved presentation, and precedence rules. Both should wait until spanning-image switching and recovery are dependable. Video and timed playlists remain experimental regardless of how many software tests pass.

### Mobile and accessibility

I applied the accessibility-inclusive-design skill to these recommendations. Existing markup includes labels, live regions, tab roles, skip links, keyboard nudges, and enlarged stage hit areas. Those are source-confirmed positives, not evidence of full accessibility. [physical.html:14](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical.html:14), [physical-stage.js:139](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical-stage.js:139).

On phones, keep the image preview and main action visible, then use a selected-tablet sheet and task navigation. Avoid shrinking a desktop control rail. Provide numeric and directional alternatives to every drag. Preserve focus after polling, roster changes, and deleting a tablet. Announce meaningful status transitions instead of routine polls. Use text and icons as well as colour for health. Keep controller zoom available; the tablet's physical zoom fence should explain how to return to a valid display state.

Before accepting a redesign, test keyboard-only operation, visible focus, screen-reader names/status, long names, enlarged text, narrow portrait screens, landscape screens, touch target separation, and form-error recovery. Contrast, overflow, focus stability, and actual responsive quality remain unverified in this assessment.

## Brainstorm ranked by practical value

### Must-have for dependable spanning images

- **Accurate single console and content readback.** Removes contradictory state. Costs a careful migration of existing functions and contracts.
- **Fill/Fit with image-and-bezel preview.** Makes cropping intentional. Requires all render paths to agree, including future slideshow use.
- **End-to-end image status and targeted recovery.** Distinguishes an alive browser from a working screen. Adds a small protocol contract and stale-report rules.
- **Names, Identify, Remove/Forget/Replace.** Makes physical installation manageable. Requires lifecycle semantics, not more cosmetic labels.
- **Saved 2x2/1x4 with explicit tablet order.** Makes changes repeatable. Extends packing and snapshots rather than adding optimization.
- **A rehearsed local deployment, backup, and recovery path.** Reduces dependence on developer memory. Adds operational work and real-device evidence rather than many new features.

### Useful next

- **One image library with upload progress, thumbnails, search, and rejection reasons.** Curated folders remain useful for the current upload-disabled hotspot. Managed uploads already normalize source orientation and generate bounded renditions; retain that pipeline.
- **Safe library cleanup.** Add archive/delete with a reference preview for current content, saved scenes, and playlists. Managed quota exists, but no operator media-delete API is present. Never start with automatic destructive garbage collection.
- **Backup scope selection.** Existing backups intentionally copy referenced content, not the entire library. Offer a clear Wall recovery versus Full library choice or document an additional full-directory backup. Otherwise an operator may expect unused uploads to survive a restore when they do not. [OPERATIONS.md:101](/var/home/oak/Codes/projects/tablet-wall-ai/deploy/OPERATIONS.md:101).
- **Built-in physical test image.** Generate a grid matched to committed bounds using the existing tool, then show it like any still image. Label the logical calibration scene separately. This avoids teaching users to copy files just to check continuity.
- **Small operational history.** Record who/which controller changed layout or content, with the revision and reason. A bounded local history is enough; an observability platform is unnecessary.
- **Export/import arrangements and installed-tablet metadata.** Useful for transfer and recovery, but must preserve or explicitly remap identities and measurement references.
- **Strict image cut preparation.** Once static reliability is proven, adapt the existing prepare/commit work for coordinated still changes. Make missed devices explicit. Do not market it as optical synchronization.

### Optional future

- Mirror images, then independent per-tablet images.
- Image-only scheduled shows and slideshow polish after real-device recovery testing.
- Video after a separate compatibility, resource, activation, and optical validation programme.
- A manifest/installed web app only if a specific tested browser needs it for launch behavior. It is not a substitute for OS kiosk configuration.
- More hardware models when actual tablets need them. Do not build a fingerprint catalogue before the installed devices work.
- Focal crop positioning, snap guides, and per-layout content choices after simple Fill/Fit and presets work.

## Security, deployment, efficiency, and architecture

### Security practices

The present tablet route allowlist and loopback operator boundary are worth retaining. Do not expose the raw backend on the tablet network. Origin checking is a browser request fence, not authentication. The optional app shared secret protects all routes when enabled, whereas the reference two-origin proxy authenticates the operator separately. Avoid combining those configurations without an integration test for tablet registration, asset requests, and WebSockets. [auth.py:107](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/auth.py:107), [hotspot.Caddyfile:12](/var/home/oak/Codes/projects/tablet-wall-ai/deploy/hotspot.Caddyfile:12), [main.py:608](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:608).

**Source-confirmed security limit.** A browser UUID is an identity key, not a credential. Device registration and the device socket lack per-tablet proof in the open hotspot profile. A peer with a known UUID can claim that socket. The route allowlist restricts controller access but does not solve tablet impersonation. This is also documented by the repository. [main.py:899](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:899), [main.py:3002](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:3002), [README for deployment:208](/var/home/oak/Codes/projects/tablet-wall-ai/deploy/README.md:208).

**Proposal.** Add short-lived join approval and server-issued per-tablet credentials, with revocation and request/connection limits. Pair once, reconnect without a human, and explicitly reauthorize when storage is lost. Keep credentials out of URLs and logs. Pairing over plain HTTP does not provide confidentiality, so use the tested TLS profile or explicitly accept the trusted-hotspot boundary. Treat served image bytes as accessible to admitted tablets.

Put secrets outside the checkout with restricted permissions. Add routine dependency review and security headers for controller/client pages, including a tested content policy and framing restriction. The login page has a CSP; the controller/client paths do not get an equivalent app policy in the inspected code. Test the policy against local scripts, SVG, blob images, and WebSockets rather than copying a generic header.

### Deployment and backups

Support a deliberate supervised HTTP trial and a separately rehearsed HTTPS/kiosk profile. Keep their capabilities honest. Do not enable uploads merely to make diagnostics work. Do not promise wake lock on the HTTP tablet origin.

Use explicit data directories and one worker. Preserve the launcher startup checks and firewall ownership logic. Reconcile older operations text with the current launcher so operators do not have to choose between historical setup instructions. Add bounded log retention and a health/readiness check that distinguishes a live process from loaded content and storage readiness.

The existing backup tool uses SQLite's backup mechanism, verifies manifests/hashes, and restores into new targets. Retain its refusal to overwrite. Package the real restore drill into the supported operator procedure. Back up runtime configuration and any TLS/secret material separately with appropriate access controls; an image/database snapshot is not a complete host rebuild. Display both backup recency and the date of a successful restore rehearsal.

### Efficiency recommendations without invented performance claims

I measured no latency, throughput, CPU, memory, battery use, or network capacity. There is no basis here for a speedup claim or infrastructure expansion.

Known work in the code provides specific places to inspect if needed:

- Curated inventory reads scan and hash files, although decoded validation facts are cached by content hash. Managed objects use an index. Prefer managed immutable media for a growing library after upload workflow consolidation; keep curated folders for the current trial. Do not weaken byte verification to trust timestamps. [assets.py:161](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/assets.py:161), [routes/assets.py:15](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/routes/assets.py:15).
- The physical controller polls playback each second and periodically reads roster and full configuration. The backend already supports v3 controller snapshots/config notifications. Consider one shared v3 state connection plus a periodic reconciliation read, after fixing correctness. Polling at this scale may already be sufficient; measure before changing it. [physical.js:3438](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical.js:3438), [physical.js:2497](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical.js:2497), [main.py:3114](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:3114).
- Physical render plans perform profile/calibration/history reads per tablet, and configuration assembly performs several database reads. If layout switching becomes slow, profile those paths and consider an immutable, revision-keyed measurement snapshot. Do not introduce another mutable cache before evidence justifies it. [hub.py:87](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/hub.py:87), [main.py:1867](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:1867).
- Retain the ingest subprocess limits and bounded queues. Use the existing thumbnail descriptor for browsing. A tablet must receive sufficient source pixels for its slice; naive per-device resizing can break effective quality or geometry. Measure decode/memory on the actual older tablets before adding adaptive renditions.
- Make unexpected playback-loop exceptions visible. The current catch-all silently continues, which can conceal recurring failures. Add bounded logging and an operator fault state while preserving the loop's isolation. This is source-confirmed and relevant before relying on experimental playback. [main.py:2503](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:2503).

### Architecture direction

Keep FastAPI, SQLite, plain JavaScript, the transform module, content addressing, and the single-owner model. Extract along tested boundaries only when consolidation makes it useful. The immediate architectural improvement is one operator state/command contract and shared content/layout controls. Rewriting the client or moving to distributed state would add failure modes without addressing the demonstrated gaps.

New concepts that earn their cost are installed-tablet names/identity, pairing/revocation, and render-result evidence. Drafts, packing, models, layout recall, uploads, retries, and backups mostly need integration and refinement. Do not introduce a general plugin system or elaborate scene graph for these needs.

## Ranked roadmap

Effort is relative. S means a small bounded change, M means several connected modules/workflows, and L means a new cross-cutting contract or operational programme. These are not calendar estimates.

| Rank | Work | Effort | Dependencies | Observable acceptance |
|---|---|---|---|---|
| 1 | One accurate image console and operator-state response | M | None | With a physical wall active, choose image A then B, reload, and see the actual layout and B everywhere. No synthetic logical wall is shown as current truth. |
| 2 | Global Fill/Fit and physical crop preview | M | 1 | A marked-border image preserves its border under Fit, crops predictably under Fill, and agrees with tablet slices. Preview distinguishes off-wall crop from bezel/gap occlusion. |
| 3 | Static-image render evidence and targeted retry | M | 1 | Force one image request/decode failure. Controller names the tablet and reason. Retry succeeds. Stale acknowledgements cannot make a newer image appear healthy. |
| 4 | Durable names, temporary Identify, and physical Remove/Forget | M | 1, 3 | Identify returns to unchanged content. Names survive restart. A slot can be removed and a browser forgotten while physical mode remains active. Reconnection behavior is explicit. |
| 5 | Saved 2x2/1x4 workflow and replacement-safe recall | M | 1, 4 | Save both arrangements, switch back and forth without changing content, then rebind one browser and recall both without resurrecting the old identity. |
| 6 | Model confidence and live viewport preflight | M | 3, 5 | Air 2/Pixel C reuse needs no new ruler entry. Rotation/zoom/launch-mode changes show the correct valid, estimated, or blocked state. Pinned revisions remain unchanged until Apply. |
| 7 | Approved join, tablet credentials, revocation, and limits | L | 4 | A nonapproved tablet cannot impersonate an installed one. An approved tablet reconnects automatically. Revoked credentials cannot reclaim a slot. |
| 8 | Unified image library and diagnostics independent of upload enablement | M | 1 | Curated images work with uploads disabled and health still loads. Enabled uploads show progress/rejections. Referenced content cannot be silently deleted. |
| 9 | Supported deployment and restore rehearsal | M | 3, 4, 8 | Clean startup yields the correct tablet address. Restart restores content/layout and reconnects tablets. Restore to new targets recovers referenced content. Only the intended listener is exposed. |
| 10 | Mobile, keyboard, and assistive-technology pass on consolidated UI | M | 1 through 6 | Common join/arrange/show/recover flows work on a narrow phone and by keyboard, with preserved focus, readable errors, and no forced drag-only actions. |
| 11 | Images-only real-device acceptance and soak record | M | 1 through 6, 9, 10. Include 7 before claiming an untrusted-network deployment. | Record both arrangements, image changes, one-tablet failure/rejoin, restart, and actual sleep/wake outcomes. State duration, failures, and geometry uncertainty without substituting test counts. |

A supervised physical-image demonstration can proceed before the whole roadmap is implemented. Dependable unattended operation needs the recovery, deployment, and real-device evidence. Security work becomes a release blocker whenever the network is not explicitly trusted.

## The next images-only demonstration

Use the supplied models and the same four tablets. Preserve the present logical wall as a named return point and verified backup before an operator-authorized demonstration. That is a proposed future action; I did not perform it.

1. Start the supported isolated/trial profile and confirm the advertised tablet URL.
2. Reuse the existing browser identities. Confirm each number/name and Air 2/Pixel C assignment.
3. Select a known static image before applying physical layout if the current console split remains. Do not start a playlist. Keep the current limitations visible.
4. Build a 2x2 draft with model-aware bodies, appropriate mount angles, and fit-to-tablets bounds. Apply once.
5. Show an image with labelled corners, diagonals, circles, and fine lines, generated for those committed bounds using the existing calibration-grid tool. Then show a normal photograph/poster.
6. Save that arrangement, form a 1x4 draft with the same devices, and repeat. Keep image changes and arrangement changes separate.
7. Recall 2x2, interrupt one tablet's network connection through an operator-controlled device action, restore it, and inspect recovery. Restart the trial app once and verify the persisted image/arrangement returns.
8. Stop and restore the intended wall state. Record exactly which operations required a tap or manual browser reopen.

At the current HEAD, this demonstrates reuse of measurements and physical image rendering. It cannot honestly demonstrate Fit whole image or a fully consolidated operator journey because those capabilities are not implemented.

### Real-device validation checklist

This is proposed validation, not completed evidence.

- Record the exact model, OS/browser version, origin, tab/fullscreen/standalone mode, orientation, viewport, zoom state, and pinned model/calibration revision.
- Confirm both 2x2 and 1x4 are physically assembled as the saved arrangement describes. A successful logical trial does not satisfy this check.
- Check corner labels, diagonal continuity, circles, and grid spacing on both device types. Record observed mismatch and the provisional uncertainty. Keep geometric continuity, absolute physical scale, and aesthetic acceptability as separate outcomes.
- Confirm browser chrome assumptions in each launch mode. Change orientation and zoom deliberately. Invalid conditions must produce a comprehensible fence and a practical recovery path.
- Test a differently shaped image. At current HEAD record its cover crop. After Fit is added, verify the whole-source bounds and explain unavoidable bezel/gap occlusion.
- Test refresh, same-origin rejoin, duplicate-tab takeover, lost browser storage or changed origin, and replacement. Recall both saved arrangements afterward.
- Cause an image retrieval failure, restore the content, and retry. Check local and controller messages. Confirm an old asset callback cannot repaint the new image.
- Disconnect/reconnect one tablet and then the network. Verify other screens continue appropriately and recovering screens receive current state.
- Restart the server, then perform a separate host reboot rehearsal on the chosen deployment profile. Verify paths, startup supervision, content, and tablet reachability.
- Test actual OS screen sleep, wake, browser background/foreground, and a charging interruption. Record whether a tap, unlock, reload, or app reopen is required. A simulated visibility event is insufficient.
- Run a defined powered soak on the actual devices and network. Record start/end, every failure, resource observations, reconnects, image changes, and interventions. Choose duration for the intended installation. No sustained-operation claim is made here.
- Verify ingress restrictions from a tablet and controller access from the intended operator device. Verify trusted HTTPS without bypassing certificate errors if using TLS.
- Restore a backup to fresh paths and boot it. Confirm referenced images and arrangements, and document what unused library content was intentionally excluded.
- Exercise the controller on a real phone and with keyboard/assistive technology. Check focus, touch, error recovery, and readable status.

No video, optical synchronization, sustained uptime, or millimetre seam-accuracy claim belongs in the demonstration report until separately measured.

## Checks run, limits, and cleanup

All shell commands used the rtk prefix. HEAD and the initial source working tree were checked before reading. The inherited /var/home/oak/AGENTS.md, the supplied session instructions, RTK instructions, and the requested workflow skills were read. No subagents were created and no messages were sent to other people. No other model assessment was read.

**Executed Python checks.** Both commands used the existing virtual environment, PYTHONDONTWRITEBYTECODE=1, and pytest -p no:cacheprovider.

- .venv/bin/pytest -q -p no:cacheprovider tests/test_tablet_models.py tests/test_wall_sizing.py tests/test_calibration_guard.py tests/test_commit_boundary.py tests/test_roster_persistence.py tests/test_writer_coalescing.py tests/test_hotspot.py
  Result: 88 passed. One dependency DeprecationWarning about the AnyIO BlockingPortal alias.
- .venv/bin/pytest -q -p no:cacheprovider tests/test_auth.py tests/test_v3.py tests/test_hub_failures.py tests/test_backup_media.py
  Result: 82 passed. The same dependency warning.

Total for these focused Python selections: 170 passed. No full-suite, ruff, mypy, coverage, benchmark, or full browser/concurrency run was performed.

**Executed JavaScript checks.** Ran node on each of the following files. All processes exited successfully.

- tests/physical_sizing.test.js. Reported Physical sizing geometry passed.
- tests/physical_calibration.test.js. Reported physical calibration tests passed.
- tests/client_image.test.js. Reported 74 passed, including mocked physical transforms and viewport fences. Its video cases remain software-only evidence.
- tests/client_wake_lock.test.js. Reported 10/10 passed using mocked browser capabilities.
- tests/controller_playback_errors.test.js. Reported Controller playback error contracts passed.

**Isolated exploratory check.** An inline Python TestClient probe used a fresh TemporaryDirectory for database, curated image, and managed media. It confirmed contain=422, physical apply=200 with a logical backup, physical GET /wall=409, a new v2 controller's synthetic neutral snapshot, physical Forget=409, diagnostics=403 with uploads disabled, and physical PUT /scene=200 returning colour while the stored scene was an image. Its final assertions passed.

The first exploratory probe stopped at an assertion because I initially expected contain to be accepted. Reading the scene validator established that only cover is supported. I corrected the probe to assert 422 and reran it successfully. I do not report the unreachable static-versus-playlist comparison from that first attempt as an observed defect.

**Other check limits.** A broad search for inherited AGENTS files encountered permission errors in unrelated sibling repositories. The applicable ancestor instructions were read directly. Source inspection included the current backend modules, both controller implementations and supporting modules, tablet image/recovery/wake-lock paths, hotspot ingress, deployment, backups, calibration/sizing documentation, and relevant tests. Existing historical model reports and reviewer summaries were not used.

**Remaining unverified.** Rendered UI layout, contrast, real screen-reader behavior, actual browser performance, physical-model accuracy, browser inset placement, hardware detection collisions, real tablet video, optical synchronization, OS sleep/wake recovery, sustained operation, actual hotspot capacity, real firewall changes, TLS trust on tablets, and installed-service/host recovery remain unverified by this assessment.

**Cleanup.** No browser was launched. TestClient lifespans exited and their temporary directories were removed. The hotspot test itself launched temporary Uvicorn/Caddy instances on unused loopback ports, with firewall operations replaced by test doubles. It ran twice, terminated the launcher normally, and asserted both ports were closed after each run. I left no assessment-owned server running, changed no live database/data, and made no real firewall, network, or service changes. Pytest may retain its normal isolated temporary test artifacts outside the checkout.

**Source status.** git status --porcelain=v1 and git diff --stat were empty after the checks. No source files were edited, no commit was created, and nothing was pushed. The shared checkout remained at the reviewed HEAD at verification.

Absolute report path: /var/home/oak/.local/share/tablet-wall-ai/assessments/2026-11-01/sol-6.1-high.md
