# Acceptance for the operator workspace redesign

This is the implementation finish line for [PLAN.md](PLAN.md) and [ARCHITECTURE.md](ARCHITECTURE.md). The portable scenarios below are implemented. See [VERIFICATION.md](VERIFICATION.md) for the executed candidate, retained failures, software results and native/hardware limits.

Every mandatory scenario must pass or remain explicitly blocked with its evidence and effect on completion. Root runs the rendered application, inspects screenshots, and fixes relevant problems before handoff. A build, mocked DOM test, or successful API call alone cannot establish a complete operator flow.

## Safe and reproducible environment

Use only new private directories, databases, image stores, backups, unused loopback ports, and disposable browser contexts. Never load the live wall database, private library, real tablet profiles, or a user browser session. Do not invoke the live hotspot launcher, NetworkManager, firewall, system service, or real deployment. Do not merge or deploy.

The repository dev commands are `rtk make dev PORT=<unused-port>` and `rtk make run HOST=127.0.0.1 PORT=<unused-port>`. Both need explicit private environment paths for any manual QA. The portable driver must set those paths itself and invoke the checked-out application using the repository virtualenv or `uv run`, without shell command interpolation from labels or file names.

Add `simulator/browser/redesign_acceptance.py`. Retain reusable setup from `readiness_acceptance.py` where useful, but do not reuse its page reload before gridding or execute its full historical suite just to set up this journey. Update `operator_accessibility.py` for the new markup and focus behavior. Add focused driver tests only for safety, report identity, waits/failure recording, and race injection that materially affect evidence trust.

Define this command interface in the new driver:

```bash
rtk proxy .venv/bin/python simulator/browser/redesign_acceptance.py --artifacts /tmp/tablet-wall-redesign-NEW --scenario all
rtk proxy .venv/bin/python simulator/browser/redesign_acceptance.py --artifacts /tmp/tablet-wall-first-NEW --scenario first-wall
rtk proxy .venv/bin/python simulator/browser/redesign_acceptance.py --artifacts /tmp/tablet-wall-races-NEW --scenario races
rtk proxy .venv/bin/python simulator/browser/redesign_acceptance.py --artifacts /tmp/tablet-wall-recovery-NEW --scenario recovery
rtk proxy .venv/bin/python simulator/browser/redesign_acceptance.py --artifacts /tmp/tablet-wall-parity-NEW --scenario parity
rtk proxy .venv/bin/python simulator/browser/redesign_acceptance.py --artifacts /tmp/tablet-wall-layout-NEW --scenario responsive
```

The driver refuses an existing artifact directory and cannot target an arbitrary already-running server. `--ingress-proof <manifest.json>` can attach read-only generated-ingress evidence only when its source hashes match. A full run returns nonzero while native/hardware gates remain open; inspect `pass`, `software_complete`, `acceptance_complete` and `mandatory_uncovered` separately.

For manual inspection, apply browser-harness and frontend-testing-debugging. Follow the current host routing constraints. Do not use `preview_*` to verify edits. For any permitted baseline/shared browser work, use preview status first as required by T3. For edited-app verification use the configured Chrome DevTools/Playwright tools when available and an isolated context. Record exact unavailable tool errors and browser-harness doctor results before a permitted fallback. Existing standing instructions permit repository Python Playwright fallback with cached Chromium. Inspect the actual display/session and installed browser paths before changing any display assumptions. Do not modify DISPLAY, install browsers globally, attach the user's profile, or weaken CSP to make a test pass.

### Required artifacts and identity

Each run writes an identity manifest, results JSON, action transcript, viewport and full-page screenshots, DOM/accessibility snapshots for key states, browser trace where available, server logs, console warnings/errors, failed requests, unexpected HTTP errors, and cleanup results. Store these outside application source.

The manifest records git HEAD, dirty status and exact changed-source hashes, driver hash, command/arguments, timestamp, browser version/executable, CSS viewport/DPR, reduced-motion/text/zoom settings, private data paths, server PID/port, client IDs with independent storage contexts, synthetic image hashes, and evidence classification. A HEAD alone is insufficient when the checkout is dirty. Screenshot filenames include scenario, task state, viewport, and image/arrangement identity where relevant. Retain the matching config revision/ETag and per-client current tokens in JSON; do not print all tokens in product UI.

Every assertion has pass/fail, expected behavior, actual values, and an artifact link. Capture failures before cleanup. Label fixture mistakes as fixture failures and keep them visible. Do not turn a partial run into success by omitting failed steps or restarting against accumulated registrations. Re-runs get new directories and new data.

Stop all owned clients/contexts, private browsers, servers, Caddy processes, and temporary listeners in `finally`, including after an assertion. Record exit statuses and inspect actual process liveness. Never kill a process owned by someone else. No development server or browser remains running at handoff.

### What counts as actual UI proof

Use four separate contexts running the shipped `/client/`, registering through the real route and maintaining independent sockets/storage. One proposed profile is 900 by 1280 CSS pixels, DPR 2, Pixel C UA and browser angle 270, as in the corrected reviews. Record the override as synthetic input. It is not hardware verification and never substitutes for the operator's model declaration.

Use semantic actions in the actual operator route for joining instructions, selection, naming, model declaration, arranging, upload, fit, Show, saving, recall, remove, Forget and replacement. The harness must not set internal `window` state, call application factories, or seed durable geometry to bypass those flows. Read-only API/config observations can verify results. Fault cases may use a private fixture endpoint/mock transport, interrupted network, or targeted private file corruption to create an otherwise inaccessible state. Classify those steps as fixture injection and then verify the recovery through the real UI. Actual production endpoints remain unchanged.

## 1. Empty console, then four actual clients

1. Open the empty operator page first, before any client registration. Capture the first viewport and Add tablets. Confirm URL/QR/network facts are readable, real, and not buried in Settings.
2. Start four independent shipped clients one by one. Observe registration before socket/viewport readiness for at least one client, using a bounded private delay. Do not reload the operator page at any point before first Apply.
3. Confirm each number/default name is distinct. Confirm connected-but-unplaced status. An offline initial row becoming online is automatically eligible while setup remains untouched.
4. Open Arrange. All four eligible untouched rows are selected and ordered by stable number. Untouched relative size defaults use fresh viewport aspect, not 100 by 100 squares. For 900 by 1280 the example default is width 70, height 100. Saved/custom sizes remain their original values.
5. Exclude tablet 2 deliberately, then disconnect/reconnect it. It stays excluded. Restore it explicitly. Change one default size manually; later telemetry must not overwrite it.
6. Choose Row of 4. Preview and inspect the actual shape. A fresh Quick arrangement uses no measured-continuity language. Discard does not change server geometry/revision.
7. Choose Match real sizes. Open group model setup and inspect the exact four identities/model/approximation statement. Confirm the operator declaration. No explicit model confirmation or measured profile is created before this action. The existing auto-mode registration record may exist without a confirmed model. A matching screen signature alone never marks the group confirmed.
8. Declare the common mounted rotation explicitly. Verify per-tablet overrides. Test 90 and 270 as distinct choices. A new ambiguous landscape setup cannot proceed by guessing. Existing valid stored angles can be preserved visibly.
9. Preview, inspect actual order/shape/gaps/uncertainties, and Apply arrangement. There is one reviewed grid commit. Reload-free status changes from preview to committed. It does not say image shown when no image is selected.

Capture desktop 1440 by 900 and 1600 by 1000 at empty, joined, review and applied states. Record the action count of the uncomplicated default journey. The target is at most 16 deliberate console actions from opening Add tablets through Apply and showing a supplied existing image, with optional naming/manual calibration excluded explicitly. Count selections, confirmation acceptance and task opens. Do not combine several hidden script actions into one count. The goal is removal of the repeated per-tablet System ritual, not a measured human-performance claim.

## 2. Bulk model partial outcomes

Run a successful four-tablet group with the real assignment endpoints and inspect successive If-Match values. Each successful response supplies the next expected ETag. A reconciliation GET must match that chain; it must not silently adopt an unrelated fresh ETag as authorization.

Inject a 412 on the third assignment by making a second operator's real durable change. Tablets 1 and 2 remain confirmed, tablet 3 is reported conflicted, and tablet 4 remains untouched. The UI lists all three outcome classes by actual names/numbers and stops. It does not roll back successful writes or say the batch was atomic. An external change between GET and PUT must also fail safely.

Inject timeout/connection loss during a batch write. Report completion as uncertain, reconcile current assignments, and require review before retrying unresolved targets. Do not resend completed targets automatically. Change selection during a delayed batch; the original captured IDs remain the subjects. An incompatible or mixed model selection is not auto-confirmed as a homogeneous group. Confirmed assignment and measured mapping readiness remain separate statuses.

## 3. Add, choose, Fit/Fill, Show, and reload

Use the supported opted-in loopback profile with the same computed origin as the launcher contract. Open Images and add a synthetic PNG, then JPEG, through the real file input. Observe transfer, processing and completion. The new library entry is locally selected. Server scene/layout remain unchanged after upload and selection.

Select Fill wall and Show whole image in turn. Inspect the stage's one global transform, cropped edges/bars, bezel gaps, and estimate language. Both are labelled Image preview. The live count continues referring only to committed state. Preview tiles cannot carry Showing badges that imply the proposed fit is already shown.

Click Show image. Verify exactly one intended scene write with asset identity/fit and the reviewed ETag, while geometry remains unchanged. Verify the applied config and wait for four current matching reports from shipped clients. Capture the operator and at least one real client slice. Read generation/revision/connection/mapping/asset tokens in artifacts. Old reports never confirm this scene.

Reload the console and restart its disposable browser context while keeping/reopening private storage as appropriate. Applied geometry, labels, image and fit persist. Unsaved selection does not become live. Saved scenes retain their original content-only meaning. Previous-content restore is explicit and is not advertised as restart-persistent history.

Phone viewport upload is tested on the admitted local origin. Do not claim the tablet-network listener permits a remote phone to upload. Supported profile addition succeeds on the operator computer; phone selection/show workflows still work whenever the operator origin is legitimately reachable.

## 4. Image failure and stale inventory

| Injected state | Required production behavior |
| --- | --- |
| Invalid image decode, such as non-image bytes named `.png` | Actionable rejection, current wall unchanged, no published ready item, file input/retry usable. UI waits for the actual result rather than matching the file name. |
| Admission or validation 4xx | Factual refusal beside Add image. No security toggle, forwarded-header trick, or auto-fallback to tablet ingress. Current wall remains intact. |
| HTTP 5xx or unreadable successful receipt | Completion is uncertain, including configuration/storage errors that may arrive after publication. Require a later successful inventory refresh before retry; older reads and failed refreshes cannot unlock it. No automatic Show. |
| Known capacity/queue refusal | Report the specific refusal. Retry controls follow known 4xx refusal versus ambiguous 5xx completion. No half-published item is offered as ready. |
| Network failure or timeout after request body was sent | Mark uncertain completion, Refresh inventory before retry, no automatic Show, and no duplicate live action. |
| Inventory refresh races with an earlier refresh | The older result cannot remove a later uploaded selection or newer item. The latest selection remains attached to its asset identity. |
| Selected image disappears before Show | Mark unavailable, disable unsafe Show or present the server refusal, retain selection/reason, and offer Choose replacement image. Never choose another file silently. |
| Live image bytes disappear or become unavailable | Current scene identity remains visible, reports reflect failure/staleness, and Choose replacement image leads through the same preview/Show path. |
| Saved scene refers to stale/missing image | Show scene refuses with recovery guidance. Geometry remains unchanged and no unrelated asset is substituted. |

The driver must inspect console/network and classify injected failures separately from unexpected failures. It must not declare the page healthy by ignoring all 4xx/5xx responses.

## 5. Draft retention, action subjects, and focus

Reproduce issue #23 first against the baseline evidence or a focused failing behavior test. In the implementation, enter an unsaved name for A, select B, then return to A. Exact value, dirty marker, and caret where feasible remain. B's values never inherit A's input. Save A and confirm durable label/reload. Discard affects A only.

Investigate profile, calibration and model forms by entering real changed values, moving between A/B and tasks, and receiving runtime updates. Preserve values and their baselines. Do not merely assert that dirty flags stay true. A changed remote form subject creates an explicit conflict. Unload warns about dirty work; a subsequent reopen restores server-committed state without claiming unsaved drafts were saved.

Start a delayed save/Identify/retry for A, then select B and edit B. The request/result stay attached to A and cannot clear B's dirty value, move focus to A, or show A's stale status as B's action result. If A is edited again while its save is pending, the late success does not mark the newer edit clean.

While the name input is focused, trigger heartbeat, reconciliation, device status, and a fifth join. Focus, selection range, input value and IME composition remain stable. Roster selection does not unconditionally focus the inspector. Explicit task opening may focus its heading. A completed dialog returns focus to its trigger or a defined useful fallback if removed.

Switch from an arrangement preview to Images and exercise each Apply/Discard/Stay branch. Each branch resolves only its named output intent. No hidden scene write accompanies Apply arrangement. Viewing Tablets during a preview retains it. A lifecycle/model/recall command that conflicts with a draft requires explicit resolution first.

## 6. Old reads, WS events, and independent operators

Use bounded deterministic interception, not lucky sleeps. Artifact JSON identifies each delayed request, event, response, guard and final authority.

| Race | Required result |
| --- | --- |
| Hold old GET config, deliver newer WS config/event and reconcile, release old GET | Authority and runtime do not regress. Dirty forms and selected ID stay intact. |
| Hold fallback roster GET or diagnostic `/devices` read, deliver newer v3 runtime, then release | The old roster cannot overwrite current online/render truth. Colour-only diagnostic data stays separate. |
| Hold an old mutation response after a newer config update | Complete the named action if justified, but do not adopt an older config over newer authority. Reconcile uncertain ordering. |
| Release old paint acknowledgement after a new scene, reconnect, rebind, or server generation | It cannot revive image-shown status. Fresh exact tokens are required. |
| Second operator changes geometry during local manual/grid preview | Keep exact preview and original guard. Commit is blocked/refused with 412 until explicit review/rebuild. No automatic retry with new ETag. |
| Second operator changes a label, measurement or snapshot without moving the wall | Durable conflict is detected even when wall revision is unchanged. Local field/grid/rebind review is retained but cannot apply stale intent. |
| Fifth client joins during reviewed geometry/order edit | New client is available separately. It is not included or resized into the reviewed preview. If registration changes ETag, retain the old preview and require a rebuild. |
| Untouched first setup receives later online/viewport data | Inclusion/aspect update once by provenance. An intentional exclusion/manual size is preserved. |
| Heartbeats alone during a draft | No false durable conflict and no form reset. |

Use a second real operator context for conflicting writes wherever possible. Use private interception only for ordering that normal UI cannot reliably generate. Both are software evidence; neither proves a physical network race on hardware.

## 7. Remove, Clear, Forget, replacement, and saved recall

1. Build and save a measured four-screen arrangement. Remove a middle screen through the actual named panel. Inspect `POST /api/v3/devices/{id}/remove`, not a whole-layout replacement. Registration, label/number, measurements and saved references remain.
2. Remove the remaining screens, including the final one. The last removal succeeds and leaves an empty active arrangement without 409 or an unavailable Clear wall instruction. Rejoining/placing remains possible. Repeat the final removal in a relative arrangement.
3. Rebuild, invoke Clear wall, and cancel once. Nothing changes. Confirm Clear wall using the explicit endpoint/body. All active positions clear while registrations/saves remain.
4. Close A's client. Its position is reserved and reads Offline with no false paint proof. Online commands are disabled. Forget is not offered for an online tablet.
5. Review offline Forget, including actual active position, saved references, name/number release and retained measurement history. Confirm explicit active removal when needed. Cancel leaves everything. If A reconnects after review, confirmation refuses rather than forgetting a live socket. A forgotten browser can register again and is not described as revoked.
6. Join B as a new actual client. Replacement asks which offline registration it replaces, even when a suggestion exists. Declare same hardware/new browser. Inspect old/new subjects, selected exact saved digests, active impact, transfer choices and connection guard. Cancel once, then preview and confirm. Active and precisely selected saved reservations rebind. Recall those saves through the UI and verify correct pins/labels/number behavior.
7. Repeat different-hardware declaration. It must not inherit A's measured calibration. Require fresh setup where needed. Unsupported measured combinations are refused with guidance, not silently converted.
8. Between replacement preview and confirm, change B's connection, one selected snapshot, or the current ETag. Apply refuses without partial changes. Report the plan stale and require a new review. Do not silently update its digest list.
9. Save an applied arrangement and scene separately. Verify respective scope, duplicate-name confirmation, allowed name validation and delete cancellation. Recall each with an active draft and exercise explicit resolution. The arrangement recall preserves content. The scene recall preserves geometry.
10. Recall across representations. A real server safety copy exists and the returned name is shown. Recall it again to recover the prior geometry and exact pins. Missing pinned records, damaged saves and offline reservations are explicit. Never substitute latest measurement for missing history or promise data restoration from a read-only backup badge.

Future tests must not assume selected IDs after async navigation. Every lifecycle assertion names exact targets and unchanged non-targets.

## 8. Compatibility parity before retirement

| Capability exercised through the primary workspace | Required proof |
| --- | --- |
| Logical drag, resize, x/y/width/height and custom wall bounds | Correct preview and numeric values, no server mutation before Apply, one guarded commit after Apply, reload retains geometry. |
| Logical bezel, snap step, Tile/Quick arrange/Pack | Actual expected arrangement/visible panel, same draft owner, cancellation/undo, preserved fixed/fit bounds. No v2 geometry bypass. |
| Physical drag/nudge/rotation, body/fixed sizing and participation | Pointer and keyboard alternatives agree. Pins remain exact. Excluded slots do not falsely contribute to the participating live count. |
| Saved scene preview/save/show/recall/delete | Content-only semantics, current asset validation, explicit overwrite/delete and retained geometry. |
| Per-tablet and all-tablet diagnostic colours | Exact colour targets change only after an explicit action. Show test colours is separate from colour selection. Restore previous content remains explicit. No optical or current-image proof is inferred from a colour POST result. |
| Missing-image replacement | Same Images panel with preview, Fit/Fill and Show. No legacy detour or silent substitution. |
| Precise ruler/profile/calibration, diagnostics/readiness, experimental controls | Reachable from Settings or problem-specific entry. Existing guards/uncertainty remain. Experimental status remains explicit. |

After every row passes, `/controller/` enters the one workspace with a styled link fallback and meaningful error/loading state. No normal navigation links to a second editor. Primary entry has one stylesheet set and one session/socket. Raw compatibility backend routes are not removed by frontend retirement. Test both entry URLs at desktop and phone. Do not retire the editor to make screenshots shorter before parity exists.

## 9. Client failure, retry, reconnect, and restart

After Show, delay/fail bytes for one client. The operator reports three current successes and the named client's loading/failure, not four shown. Retry image targets only that connected client. Unblock bytes and require fresh paint proof. During Identify, the overlay is acknowledged separately and the obscured image is not counted as unobstructed current proof when the existing status predicate excludes it.

Disconnect one client. Preserve its position and last-known identity but invalidate fresh proof. Reopen with the same context storage. The same identity/number reconnects and only fresh tokens restore success. Reconnect control preserves identity and resets evidence appropriately. Offline recovery cannot claim to wake a tablet.

Restart the private server using the same private DB/assets. Durable layout, pins, labels, saved arrangements/scenes, image and fit survive. Generation/evidence renew. The console labels stale/reconnecting until authoritative data returns. A browser restart alone does not turn old tokens into current proof. Reopen the operator and client contexts, recover through the normal UI, and capture the resulting reports.

At 900 by 1280 and 1280 by 900, deliberately create a valid viewport/mapping mismatch and render the shipped client's recovery text. Check long reason strings, heading/body/actions, orientation, text enlargement and safe wrapping. No clipping or unreachable instructions. The earlier nonmatching-emulator observation is a reason to check, not proof of a particular CSS cause.

## 10. Responsive, keyboard, contrast, and content inspection

Inspect actual rendered routes at 1440 by 900, 1600 by 1000, 390 by 844, and 320 by 640. Also inspect widths just above and below the chosen panel breakpoint, and tablet recovery at both orientations. Capture empty, four joined, arrangement review, image preview/shown, offline, conflict, upload failure and confirmation states. Inspect full-page shots as well as first viewports; full-page sticky-header artifacts must not be mistaken for in-page defects.

At 390 and 320, task navigation is before long task content. Controls, full task names, summary, errors, Back and the local action remain reachable without a long return scroll. The compact preview does not shrink instructions or essential text inside SVG. Long tablet names can simplify to numbers in the diagram, with full names in the adjacent list. There is no document horizontal overflow or keyboard scroll trap. Intentional stage pan/zoom stays contained and has alternatives.

Use actual browser 200% zoom where supported and record the effective layout viewport. Test separately with a 200% user/default text setting and long Unicode labels including combining marks, CJK, emoji and mixed RTL text. If automation can only emulate CSS zoom, label that as emulation and retain an explicit native-browser zoom check as unrun. Do not claim native zoom from changing viewport alone. At a 320 CSS-pixel effective width, all tasks and confirmations remain usable. A 400% desktop zoom spot-check is desirable and must be labelled separately if unrun.

Complete the first-wall, image, save, removal and recovery flows keyboard-only. Verify native names/roles/states, label associations, skip links, heading order, current task/selection, disabled reasons, progress, invalid fields and announcements. Run a screen-reader smoke check where available; otherwise report that limitation without a conformance claim.

Tab order follows source order. Focus is always visible and not covered by a sticky footer or virtual keyboard. Stage nudges work only in the stage edit context. Text-input arrows/undo remain native. Earlier/Later reorder buttons retain a useful focus target at boundaries. Escape cancels the nearest operation. Confirmation dialogs contain focus and return it. Desktop asides do not trap it. Runtime updates and roster changes do not steal focus or replace the focused input. New errors on submit focus the correct field, not an unrelated global status bar.

Measure actual composited colours for normal text, muted text, primary/secondary actions, selected/hover/focus, field boundaries, disabled explanations, status, solid tile labels and errors. Require 4.5:1 normal text, 3:1 large text and essential non-text boundaries/states. Decorative divider contrast alone is not the control boundary. Colour is never the sole state cue. Unsupported contrast samples must be inspected, not counted as passing.

Enable reduced motion and confirm no decorative animation, smooth-scroll requirement or rapid Identify flash. Check font failure/offline mode uses the local/system fallback without broken layout. Check missing thumbnails and long filenames. Record console warning/error and network health throughout navigation, forms, dialogs, upload, failure and recovery.

Maintain a small mismatch ledger with reference/design decision, actual screenshot, defect or intentional deviation, fix, and verification. Compare hierarchy, spacing, alignment, typography, image continuity, status association, overflow, and action reachability. Do not add decorative components to fill empty space. Visual quality requires the render/inspect/critique/fix/verify loop, not source review alone.

## 11. Negative upload and generated-ingress acceptance

The backend/deploy worker extends `tests/test_hotspot.py`, `tests/test_ingress.py`, and admission/upload tests. Preserve the separate authenticated proxy tests. These are additional focused checks, not authorization to run a live hotspot.

| Setup/request | Exact expected behavior |
| --- | --- |
| Launcher default without flag | Backend mode explicitly disabled, capability false, no usable file input, preflight/help describes uploads off. |
| Launcher with `--operator-uploads` | Backend mode loopback, computed exact operator Origin, backend bound to 127.0.0.1, factual local-only preflight, successful actual operator UI upload. Flag is not silently persisted. |
| Inherited proxy/loopback/unknown non-disabled mode | Launcher refuses instead of inheriting upload authorization. Flag is the only opt-in for the trusted HTTP profile. |
| Auth token supplied to trusted HTTP launch | Existing refusal remains. The flag does not relax authentication or HTTPS profile constraints. |
| Direct local POST with one exact configured Origin and valid PNG/JPEG | Upload admitted under opted-in loopback mode, bounded worker/publication succeeds, no scene auto-show. |
| Missing, wrong, `null`, duplicate or comma-joined Origin | Refused. Test raw HTTP header multiplicity, not a client dictionary that merges duplicate values. No publication. |
| Non-loopback peer with exact Origin | Refused by admission. A unit transport fixture may prove this condition; do not expose a real LAN backend to manufacture it. |
| Loopback peer with Forwarded or any X-Forwarded-* header | Refused even with exact Origin. A forged operator credential does not bypass loopback checks. |
| Invalid/disabled backend mode or absent operator Origin | Fail closed with factual 403/503 as applicable. Never advertise a working upload workflow based solely on a browser switch. |

Generate the tablet Caddy configuration using `deploy.hotspot.proxy_config`, load it in a private Caddy instance on unused loopback ports, and run actual requests with upload mode loopback upstream. The test must use the generated output, not only the reference `hotspot.Caddyfile` or a copied allowlist. Its manifest records Caddy version, config hash, ports, requests/statuses, and upstream reachability.

Assert tablet listener 403 for `/uploads`, `/media`, `/api/v3/images`, controller HTML/JS, `/ws/controller`, diagnostics, lifecycle/rebind routes and wall/config-write routes. Exercise the methods that could otherwise mutate state, plus operator paths under GET/HEAD where relevant. Repeat upload and operator requests with exact spoofed operator Origin, `X-Tablet-Wall-Operator`, and forwarded headers. Verify no asset publication or durable mutation and no operator WS upgrade. Tablet `/client/`, actual registration/socket and permitted immutable asset bytes remain functional. A tablet upload rejection caused only by a malformed payload does not prove ingress denial; use an otherwise valid upload.

Direct backend admission tests and generated-Caddy denial are both mandatory. A Caddy unavailable skip leaves the composed-ingress item unrun. Do not claim TLS or live hotspot isolation from these HTTP loopback tests. No firewall/service/network state changes are necessary or permitted.

## Required focused checks and closure

Worker A adds meaningful behavior coverage for keyed form values/action subjects, late registration defaults/provenance, stale preview guards and correct lifecycle removal. Reuse `tests/operator_grid.test.js`, `tests/operator_state.test.js`, `tests/operator_sync.test.js`, `tests/operator_content.test.js`, and the existing sizing/calibration tests. New session/device tests are justified when no existing target covers the observable behavior. Avoid tests that only mirror private object fields or restyle selectors.

Run affected Node tests and focused Python lifecycle/grid/snapshot/model/scene/upload/deploy/ingress selections as changes land. If Python production code changes, run repository lint and type checks. Once integrated behavior stabilizes, root runs the repository-required broader checks. Repeating the full 1,782-test Python or 183-check browser suites during planning is unnecessary and was not done.

Completion requires the new first-wall journey, both upload modes with a successful supported addition, lifecycle and parity cases, deterministic race cases, responsive/keyboard visual evidence, generated-ingress negatives, clean unexpected console/network results, and verified cleanup. Root's final report states exact app/driver identity, pass/fail/block counts, accepted deviations, inspected artifacts and independent review result. It must distinguish software simulation, injected fixtures and actual UI interaction.

Real hardware, optical alignment, physical bezel accuracy, panel power/sleep, TLS deployment, video, prolonged soak and live-system behavior remain outside this software acceptance. Do not label them passed. No application, browser, server or deployment was started by the documentation-only synthesis task.
