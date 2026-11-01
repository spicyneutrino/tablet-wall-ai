# Tablet wall readiness assessment

Independent assessment by GPT 6.1 Terra High, 2026-11-01. Checkout HEAD: `0ff56e30dfd6b2f92995569faa2d6e7fdc90fa8f`. This is a source and focused-test review. I did not read other model reports or inspect a rendered UI.

## Verdict and top five actions

The goal is a dependable wall of tablets showing one continuous image. The project has a credible foundation for a supervised images-only trial, but it is not yet evidenced as dependable unattended operation or physically accurate across mixed devices. The main risk is the gap between saved configuration, what each tablet actually painted, and what an operator can recover without specialist knowledge.

1. Demonstrate the physical-layout image path on the existing iPad Air 2 and Pixel C models in both 2x2 and 1x4 arrangements. Use the supplied measurements; collecting more measurements is not a prerequisite.
2. Add a wall-wide full-image fit and faithful crop preview.
3. Show per-tablet image presentation health and actionable recovery separately from socket presence.
4. Make identity replacement repair saved layouts as well as the active wall.
5. Unify the images-only operator journey and make arrangement switching safe and understandable.

Do not build a framework rewrite, cloud dependency, AI generation, distributed backend, or speculative performance system now. Mirror, independent screens and video are future proposals. Experimental playlists and video should not dominate the image workflow.

## Evidence and existing strengths

**User-reported hardware evidence.** The user reports usable logical images on iPads and Google tablets in 2x2 and 1x4 trials. The saved real wall is a logical four-tablet row, 320 by 60 units, with a cover-rendered 2000 by 745 image. These reports do not establish the physical-layout path, physical seam accuracy, tablet video, optical synchronization, sleep and wake recovery, or sustained operation.

**Source-confirmed.** The backend persists changes before publishing the new wall, with a transactional backup when needed ([main.py:445](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:445)). It has logical and physical sizing, packing, separate layout and scene data, revision-pinned profiles and a calibration guard ([sizing.py:50](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/sizing.py:50), [state.py:371](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/state.py:371)). Built-in measurements have a provisional 3 mm uncertainty and can be overridden. Saved revisions retain their snapshots ([tablet_models.py:8](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/tablet_models.py:8), [PHYSICAL-CALIBRATION.md:22](/var/home/oak/Codes/projects/tablet-wall-ai/docs/PHYSICAL-CALIBRATION.md:22)).

The controller exposes a roster, saved spots and layouts, wall and tablet editing, and content controls ([index.html:32](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/index.html:32)). Physical setup has a draft, apply and cancel, rotation, nudges, model selection, calibration and rebind facilities ([physical.html:49](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical.html:49), [physical.js:146](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical.js:146)). The tablet displays image loading and failure states, with a retry path ([client.js:1558](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/client/client.js:1558)). A tablet listener allowlist and separate operator access already exist ([tablet-routes.caddy:9](/var/home/oak/Codes/projects/tablet-wall-ai/deploy/tablet-routes.caddy:9)).

**Tests run.** The isolated model, calibration guard and roster persistence suites passed 49 tests with one Starlette/AnyIO deprecation warning. Fixtures use temporary database, asset and media paths ([conftest.py:25](/var/home/oak/Codes/projects/tablet-wall-ai/tests/conftest.py:25)). Model tests cover a synthetic ambiguity, rotation, pinned revisions and logical-layout backup ([test_tablet_models.py:11](/var/home/oak/Codes/projects/tablet-wall-ai/tests/test_tablet_models.py:11)). These are software checks, not hardware proof. The earlier full-suite results were supplied by the user and were not rerun here.

## Blockers and risks

1. **The whole image cannot be selected as the fit.** The scene API accepts only cover ([main.py:338](/var/home/oak/Codes/projects/tablet-wall-ai/main.py:338)), the controller sends cover ([controller-inventory.js:875](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/controller-inventory.js:875)), and the client rejects other image fits ([client.js:1051](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/client/client.js:1051)). Image edges can disappear, especially when switching a wide row to a square. Implement consistent wall-wide contain and cover across API, persistence and client render paths. Preview the source, crop, panels and bezel gaps. Explain contain margins. The geometry helper already has a contain calculation, but that alone does not enable the feature ([view.js:138](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/client/view.js:138)).

2. **Replacing a browser identity can break recalled arrangements.** Identity is origin-scoped and rebind changes the active layout while named layouts retain the old ID ([deploy/README.md:242](/var/home/oak/Codes/projects/tablet-wall-ai/deploy/README.md:242)). Physical setup already exposes a rebind form. An operator can repair today's wall and later recall a broken layout. Offer a previewed migration of selected saved layouts and active placement with revision checks, conflict reporting and atomic changes or a safe copy. Cover offline, already-placed and measurement-revision conflicts.

3. **Online does not prove the current image is visible.** Presence uses a socket and heartbeat ([state.py:162](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/state.py:162), [hub.py:172](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/hub.py:172)). The client manages image failure and retry locally ([client.js:1351](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/client/client.js:1351)). This is a design gap, not proof of a failed real device. Add a bounded per-device report for generation, revision, image identity, load/decode/paint outcome, viewport and timestamp. Show unknown or stale honestly and offer retry. A paint acknowledgement still cannot prove a person sees a lit screen.

4. **Physical continuity remains unproven.** Model matching uses screen dimensions, DPR and platform, not a hardware identifier ([tablet_models.py:23](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/tablet_models.py:23)). Browser-chrome offsets are inferred and approximate ([tablet_models.py:117](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/tablet_models.py:117), [PHYSICAL-CALIBRATION.md:32](/var/home/oak/Codes/projects/tablet-wall-ai/docs/PHYSICAL-CALIBRATION.md:32)). A collision between actual devices is a hypothesis, not an observed incident. Confirm the model and operating mode visibly, retain the provisional uncertainty, and demonstrate the physical path before promising scale or seam precision. Browser rotation and mounting angle are distinct inputs. The viewport guard withholds a physical render plan when calibration does not match ([state.py:357](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/state.py:357)).

5. **Recovery and power remain operational dependencies.** Wake lock is best effort, fullscreen needs a gesture and does not survive reload, and socket reconnect cannot guarantee a frozen OS page resumes ([deploy/KIOSK.md:13](/var/home/oak/Codes/projects/tablet-wall-ai/deploy/KIOSK.md:13)). A service restart resets presence and requires tablets to reconnect ([deploy/OPERATIONS.md:75](/var/home/oak/Codes/projects/tablet-wall-ai/deploy/OPERATIONS.md:75)). Provide device-specific kiosk and power instructions, report wake state, and test real restart, network drop, screen lock and foreground recovery. Do not promise remote wake from a web page.

6. **The tablet network is a trust boundary, not device pairing.** Public registration and device sockets do not authenticate individual tablets. A LAN peer knowing a UUID can impersonate one ([deploy/README.md:208](/var/home/oak/Codes/projects/tablet-wall-ai/deploy/README.md:208)). Tablet ingress denies operator routes ([tablet-routes.caddy:9](/var/home/oak/Codes/projects/tablet-wall-ai/deploy/tablet-routes.caddy:9)). Optional shared-secret middleware is bypassed if unset ([auth.py:113](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/auth.py:113)). Isolate the hotspot, restrict backend and operator listeners, verify actual ingress and origin behavior, and state that displayed assets are reachable on the tablet network. Add pairing and revocation when the threat model includes untrusted peers. A UUID or visual label is not a credential.

## Operator journey

1. **Start.** Start the documented single-worker service and tablet ingress. Show the operator the tablet origin, service and storage readiness, backup age and trust instructions. Preserve a stable origin. State the power and network prerequisites.
2. **Join and identify.** Present a QR code and copyable exact tablet URL, with a local-address warning. A new screen displays a large temporary number and short ID. The operator identifies it, assigns a durable human label, confirms or overrides the suggested model, and sees connection and wake status. Pairing is a separate proposed security feature.
3. **Arrange.** Choose a 2x2 or 1x4 draft for selected tablets, preview placements and rotation, then apply once. Use measured body sizes and bezels in physical mode. Label logical layouts as unit-based. Start with the existing model snapshots and packing, allow correction, and preserve a safe return to the prior arrangement. Recall with a preview of missing or changed tablets.
4. **Show.** Choose or upload an image, preview wall and panel coverage, choose contain or cover, then apply. Show current content and image status for every tablet. Show bezel gaps as hidden image regions. Warn when orientation, live viewport or model is uncertain.
5. **Switch.** Recall an arrangement or select an image independently, with a preview of crop and participating devices. Warn about missing devices and unsaved drafts. Keep the existing separate layouts and scenes as the primary concepts.
6. **Recover or remove.** Show the last known state and next step for offline, connected-but-unconfirmed, failed image, calibration mismatch and wake warning. Offer retry and identify actions requiring a gesture on the tablet. Remove from wall keeps the tablet. Forget removes the roster entry and warns about affected reservations and saved layouts. Rebind transfers a known old identity with a preview. Neither forget nor rebind is credential revocation.

## Controller, tablet and mode design

**Proposal.** Make one image-focused controller with Wall, Tablets, Images and Settings tasks. Reuse the physical editor as detailed geometry rather than creating another state model. Show the active layout kind and a single live stage. Put profile, ruler and revision fields behind a details view. Use consistent draft, apply, conflict and undo semantics where feasible. Logical fit-to-tablets currently disables undo because bounds can rebase ([controller-stage.js:573](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/controller-stage.js:573)). Safe whole-draft undo needs design work. The physical page prominently includes experimental playback ([physical.html:95](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical.html:95)); move it behind an experimental area until device support is established.

Keep tablet pages quiet during a healthy show. A tap should expose a large high-contrast identity and useful state, plus fullscreen or retry when supported. Distinguish controller actions from actions requiring a tablet gesture. Keep label, connection, calibration and image presentation as distinct concepts. Do not present a model suggestion as verified hardware.

For mobile and accessibility, make stage operations available without drag, with labelled controls, visible focus, keyboard movement, status text beyond color, readable text and usable touch targets. Existing keyboard nudge controls and labelled stage are useful starting points ([physical.html:69](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical.html:69), [physical.html:241](/var/home/oak/Codes/projects/tablet-wall-ai/frontend/controller/physical.html:241)). This is source evidence, not an accessibility pass. Inspect and exercise desktop and narrow screens, screen readers and zoom before declaring the redesign complete.

**Proposed modes.** Default to one image spanning the wall. A diagnostic identity or grid view is a temporary operator tool that restores the previous image. Mirror and independent content require per-device assignment and recovery semantics; defer them. Playlist and video remain experimental until real-device validation. Distinguish content mode, layout geometry and browser fullscreen in the language.

## Prioritized brainstorm

**Must have.** Full-image fit and crop preview; physical trial using supplied models; actual image presentation health; safe saved-layout rebind; familiar 2x2 and 1x4 draft and recall; startup and recovery instructions; clear remove versus forget; power and trust checks; backup and restore drill.

**Useful next.** QR joining, labels and identify action; image library search and deletion safeguards; duplicate detection and upload failures; bulk orientation and alignment with per-device overrides; before/after layout preview; a consolidated health list; accessible mobile controls. Refine existing upload and library infrastructure before adding another store. Check deletion impact on saved scenes.

**Optional future.** Pairing and revocation for untrusted peers, depending on the threat model; mirror or independent screen modes when a real use case requires them; then tablet video and scheduled playlists after still-image recovery is stable. An offline cache needs an explicit stale-content and trust policy. Battery telemetry, remote OS wake and automatic fullscreen are platform-dependent hypotheses, not assumed browser capabilities.

## Deployment, security, efficiency and architecture

Keep one server process. Multiple workers have separate in-memory sockets and presence and can diverge ([deploy/OPERATIONS.md:75](/var/home/oak/Codes/projects/tablet-wall-ai/deploy/OPERATIONS.md:75)). Retain persist-before-broadcast, ETag conflict guards, pinned calibration, explicit image failure and the narrow tablet route allowlist. Verify access from a separate tablet-network peer, including direct backend and operator ports. Protect operator credentials and the local CA private key. Use HTTPS and actual device trust when required. Rate limits and per-device credentials are threat-model decisions; roster numbers are not authentication.

Backups already include the database and referenced media, and restore targets must be new paths ([deploy/OPERATIONS.md:88](/var/home/oak/Codes/projects/tablet-wall-ai/deploy/OPERATIONS.md:88)). Unused uploads are excluded. Tell the operator before they rely on a backup as a complete library, and add an off-host schedule, verification and periodic isolated restore drill. A snapshot alone does not prove the operator can restore the service.

Wall broadcasts send to device sockets sequentially ([hub.py:126](/var/home/oak/Codes/projects/tablet-wall-ai/tabletwall/hub.py:126)). A slow socket might delay later sends, but the practical effect is unmeasured. Instrument representative connection counts, send failures, image decode and payload sizes before optimizing. Avoid changing concurrency or adding distribution without an observed bottleneck and correctness tests. Retain bounded media processing and content-addressed assets.

## Ranked roadmap

Effort is relative engineering effort, not elapsed time. Acceptance includes software tests and real devices where stated.

| Rank | Work and dependency | Effort | Observable acceptance |
| --- | --- | --- | --- |
| 1 | Physical images-only demonstration using existing models. | S | Both arrangements show one correctly oriented image through the physical path. Record conditions, mismatch and recovery without claiming unmeasured precision. |
| 2 | Fit choice and wall preview, building on existing scene and geometry. | M | Contain shows every image edge and cover shows the predicted crop on every tablet. Preview includes bezels and updates with layout. |
| 3 | Per-tablet still-image health and retry, building on the client and heartbeat. | M | Controller distinguishes offline, waiting, failed and current painted revision. Disconnect, failed asset and retry do not produce false green. |
| 4 | Rebind saved layouts, building on existing rebind and revision checks. | M | Preview lists affected layouts. Migration preserves geometry and pinned profiles or rejects conflicts without partial changes. Recall works after replacement. |
| 5 | Arrangement drafts and safe recall, building on pack and physical draft. | M | Four selected tablets preview and apply 2x2 and 1x4, switch repeatedly and restore the prior layout, with missing devices called out. |
| 6 | Consolidated images-first controller and identity workflow, after items 2 through 5. | L | An operator can join, label, identify, arrange, show, recover and remove in one navigation. Mobile and keyboard tasks work without drag. |
| 7 | Startup, power and recovery runbook and health display, using results of items 1 and 3. | M | A fresh operator starts from power-off, identifies failures, restarts the service and follows kiosk instructions on both models. |
| 8 | Backup scope and restore rehearsal, independent of the controller redesign. | M | An off-host snapshot verifies and restores to isolated paths with referenced image, layout and device records intact. Documentation warns about unused uploads. |
| 9 | Harden isolated deployment and define the pairing threat model. | M | A tablet-network peer cannot access operator or direct backend routes. Asset exposure and residual impersonation risk are documented. |
| 10 | Evaluate optional modes only after still-image gates. | L | A specific need, compatibility matrix and failure criteria justify a small prototype. No video or synchronization claim without real-device evidence. |

## Next images-only demonstration and real-device checklist

Use the existing four devices, supplied measurements and a test image with distinct edge labels, straight lines, a center mark and recognizable features spanning seams. Preserve the current saved wall by using an isolated setup with its own database or an explicitly saved copy. Record model, OS/browser, origin, display mode, orientation, layout kind, image dimensions, fit, active devices and result. No new measurements are required to start.

- Confirm the known logical 1x4 image, then create a physical draft using the supplied models. Confirm each model against the device, viewport and mount orientation. Review the draft and backup before applying.
- Check 1x4 and 2x2. Inspect outer image edges, panel order, rotation, relative scale and continuity across bezel gaps. Record visible mismatches as observations, not millimetre accuracy claims. A photo is not an optical synchronization measurement.
- Compare the intended image with the cover crop. Until contain exists, record which parts are missing.
- Switch arrangements and back, reload one tablet, disconnect and reconnect its Wi-Fi, then restart the server. Record controller and tablet states and manual actions. Test an image failure and retry in an isolated setup.
- Test screen lock, idle timeout, foreground restoration, power and charging on both OS families with the intended kiosk configuration. Record whether and how each returns. Use a defined duration and failure log for any longer supervised soak.
- Rehearse origin change and rebind with disposable identities and copied layouts. Verify named arrangements, backup verification and isolated restore. Check TLS trust and ingress from a separate network peer.

## Checks, limits and cleanup

- Actual checks: `git rev-parse HEAD`, `git status --short`, source and test inspection, and `PYTHONDONTWRITEBYTECODE=1 uv run pytest -q -p no:cacheprovider tests/test_tablet_models.py tests/test_calibration_guard.py tests/test_roster_persistence.py`. Result: 49 passed, one AnyIO deprecation warning. Test fixtures isolate data under temporary paths.
- Earlier full-suite results were user-reported and not rerun here. No browser, server, shared browser session, live wall, real tablet, network or firewall was used. There are no simulated UI observations in this report. UI layout, actual accessibility, physical continuity, sleep and wake, kiosk behavior, deployment ingress and sustained use remain unverified by this review.
- No source edits, commits, services, live database writes or messages were made. The source working tree was clean before and after the review. No server or browser was started, so none required stopping.
- Report path: `/var/home/oak/.local/share/tablet-wall-ai/assessments/2026-11-01/terra-6.1-high.md`.
