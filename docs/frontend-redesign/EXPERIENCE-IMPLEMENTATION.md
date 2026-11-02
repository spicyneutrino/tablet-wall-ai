# Workspace composition implementation

Prepared from `2b2fa48a58b6be45b2337a792155ebdd3d936bc0` on 2026-11-02. This package implements selected B in the existing vanilla owners. Root integrates the independently delivered stage package serially. This report is scoped software evidence, not final combined experience approval.

## Delivered behavior

Images leads with one keyed, searchable gallery. Desktop has two gallery columns and a selected-image column. Phone puts the same gallery before the selected name, Fit/Fill and Show. The four-image fixture exposes Show fully at y795.6–839.6 on 390×844. A real thirteen-image inventory was searched and selected without a permanent four-item cap. The Selected image controls link focuses the sole commit region. Alternate filename selection remains in a labelled disclosure. Add opens the existing admitted upload form or its capability explanation. Upload still requires launch admission and never shows automatically.

Tablets leads with the populated roster and per-row Identify buttons. Their accessible names include the actual tablet identity. Each command captures that row's ID and uses the existing guarded command owner. Selection and per-identity name drafts stay keyed. Compare/Discard appear for name drafts; Discard restores useful field focus. Add opens native joining help. Empty rosters open it automatically; population closes automatically opened help unless it contains focus. Explicitly opened help stays open. Placement/measurement and lifecycle details remain native disclosures; unresolved Forget/replacement reviews expand. Remove, Forget, replacement declarations, exact saved references, connection guards and reservations retain their original handlers.

Arrange keeps sizing, shape and the named membership summary before the original stage, then the actual proposal and Apply review. Missing models, changed pins, undeclared mounts, unresolved model batches and release decisions expand membership review. Completed membership can collapse. Valid unchanged previews omit another enabled Preview. Rebuild appears only for stale-base grid/image drafts; Discard remains available for actual local work. Successful Preview focuses its review without scrolling the page unexpectedly. Custom positions, bounds, packing and relative editing follow ordinary review. Selecting a stage tablet in Arrange opens its custom editor.

Saved records precede their save forms. Arrangement thumbnails are passive SVGs generated from actual saved geometry and available pinned profiles through the existing `OperatorStage.panels` helper. They contain no fabricated saved image. Names, subjects, representation and available exact pins are shown. Scene thumbnails and filenames come from the current image inventory when that asset exists. Existing guarded Recall/Preview/Delete/save meanings remain intact. A scene remains content; an arrangement remains geometry.

Settings leads with existing readiness and check owners. Clear wall is inside Destructive wall actions. The header derives connection count and showing evidence from existing state and retains a pending-intent indicator. Initial connection guidance now distinguishes an operating wall from an empty first-run wall.

Global errors, conflicts and uncertain-command status are outside every task/stage disclosure. Uncertainty reads the session's published `uncertain` field directly and is not a second state store. Its explicit Refresh status uses the existing session reconciliation and write fence. Browser checks verified that the notice remains visible on all five tasks after a real committed write followed by an induced HTTP500.

The existing Schibsted Grotesk, palette and semantic tokens are retained. Normal metadata uses at least `.875rem`; controls use at least `2.75rem`. Task title, toolbar, object choices and selected controls follow DOM order. No CSS order, positive tabindex, second mobile tree, framework or backend change was introduced. Commits stay in document flow. Arrow-key navigation now follows the Images, Tablets, Arrange, Saved, Settings order. Clicking a tab focuses its task heading; arrow navigation retains the tablist focus behavior.

## Shared stage integration contract

There is one original `.wall-stage` and one `#stage-svg`. `OperatorWorkspace.render` relocates that same section only when `state.tabName` changes. It uses `#wall-context-content`, `#wall-context-tablet` and `#wall-context-show`, with a hidden parking host for Saved/Settings. Runtime refresh does not detach the section or keyed fields. A browser MutationObserver verified one relocation for a task transition and none during two explicit status refreshes.

`commitTask` updates tab state, calls `workspace.render` to move the host, then immediately calls `renderStage()` when the task changed. The new Node test executes that actual function and asserts move-before-draw ordering. The private navigation driver has a 250 ms `#stage-svg[data-presentation]` assertion for `images`, `tablets` and `arrange` when Terra's attribute is present. This isolated baseline lacks that attribute; the combined root trial must execute those assertions after integration.

All existing stage IDs are preserved, including scroll, scale, title, quality, resolution, live/preview controls and provenance IDs. Technical revision/session/ETag, generic sizing guidance and coverage prose are in the original stage's details. Actionable stage quality/uncertainty remains outside those details. Manual conflict comparison opens Arrange before focusing the actual comparison, so it cannot be stranded in collapsed secondary context.

Root reported stage commit `2d485704c6250c7b13b07b59ea3278e973dc87c6`, independent QA `985bcef`, and the Arrange-only editing guard `361ec04`. This package does not modify `operator-stage.js`, `physical-stage.js`, `operator-stage.css`, `tests/operator_geometry.test.js`, or `tests/controller_modules.test.js`. Terra's dynamically created `#stage-identities` remains part of the same relocated section. No new stage shell API is required.

The old first-wall assertion for four central 14px labels is obsolete after the stage merge. The new measured journey instead checks four accessible tablet buttons with actual identity/status, explicit mounts/pins and exact current paint tokens. It does not remove any CAS, response-order, uncertainty or lifecycle assertion. The original acceptance drivers remain unchanged.

## Verification and source identity

All 74 Node checks passed. The focused Python command passed 177 tests with the existing Starlette/AnyIO deprecation warning. Node output is [node-final.log](/var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/node-final.log); Python output is [python-final.log](/var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/python-final.log).

The private browser suite reused the shipped `redesign_acceptance.Rig`, `experience_acceptance` measurements, existing held-response/guard scenarios, and actual shipped clients. Eleven scenarios passed, with 174 recorded assertions including repeated fixture checks. Each passed without unexpected console warnings/errors, page exceptions or failed requests. Deliberately induced HTTP failures remain labelled in their network/console records.

| Scenario | Recorded checks | Behavior exercised |
| --- | ---: | --- |
| composition | 78 | Four-image gallery, all tasks/viewports, select/fit/Show, logical2×2/1×4, upload without auto-Show, thirteen-image search, exact row Identify, keyed name, pending/error/conflict, 200% text and sampled contrast |
| measured | 18 | Explicit group hardware and mount, measured2×2/1×4, Preview without a write, geometry-only Apply, exact pins and current paint tokens |
| navigation | 9 | Gallery-first tab arrows, native modal containment/Escape, heading and invalid-field focus |
| history | 14 | Output resolver, manual redo ownership, image preview through Tablets/Settings and history shortcuts |
| lifecycle | 11 | Cancelled Remove/Forget/replacement, offline reservation, reconnect invalidation and exact saved references |
| uncertainty-global | 11 | Real postcommit500, visible notice on every task, explicit reconciliation |
| durable-uncertainty | 7 | A second write stays fenced despite automatic reconciliation until explicit refresh and renewed review |
| late-mutation | 5 | Held mutation success preserves newer authority and another identity's dirty field |
| refused-grid | 7 | Refused grid ownership leaves manual editing and Apply usable |
| stale-reads | 7 | Old roster and diagnostic reads cannot revive stale evidence or overwrite a field |
| old-paint | 7 | Released old paint cannot confirm a new scene/connection; fresh exact paint restores showing |

The final selected composition/navigation captures are in [candidate](/var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/candidate). Those runs include the last enlarged-text flex and automatic joining-disclosure corrections. The preceding [final](/var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/final) directory contains the complete eleven-scenario run. [final-visual/measured](/var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/final-visual/measured) adds an actual phone measured2×2 Preview/Apply and desktop measured1×4. Earlier guard runs used the same domain behavior; the subsequent changes only concern text wrapping and joining-help disclosure presentation.

The exact file hashes, per-run source/application hashes, copied driver hashes and final cleanup audit are in [handoff-evidence.json](/var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/handoff-evidence.json). The owned application-file hash map, serialized with sorted JSON keys, hashes to `dada425cbb79e6c6709ae312eba5abc9ac646ce0c8e7808b73deff20450fbad4`. The external workspace driver hashes to `38f0706097f6fbb68bf058426dfdd992bad8e5ae939fe610c4369a8f08dda4d4`. The latest candidate's full application hash is `868eee869ebfab53af043fcc688223182c8cc5bbd8e3d82ab0e490ac87204963` and source hash is `4b8af60b8f8065274964d5fc88b11ea82ba8aa02201efd1384c22c1bc532827d`. Each Rig copied the drivers it actually loaded. Do not substitute these hashes for the combined root candidate's identity.

Key commands ran from this isolated worktree:

```sh
rtk proxy node --test tests/*.test.js
rtk proxy env PYTHONDONTWRITEBYTECODE=1 /var/home/oak/Codes/projects/tablet-wall-ai/.venv/bin/python -m pytest -q tests/test_grid.py tests/test_commit_boundary.py tests/test_device_lifecycle.py tests/test_redesign_edge_cases.py tests/test_redesign_driver_actions.py simulator/browser/test_experience_acceptance.py
rtk proxy env PYTHONDONTWRITEBYTECODE=1 PLAYWRIGHT_BROWSERS_PATH=/var/home/oak/.cache/ms-playwright /var/home/oak/Codes/projects/tablet-wall-ai/.venv/bin/python /var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/verify_workspace.py --out /var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/final --jobs composition measured navigation history lifecycle uncertainty-global durable-uncertainty late-mutation refused-grid stale-reads old-paint
rtk proxy env PYTHONDONTWRITEBYTECODE=1 PLAYWRIGHT_BROWSERS_PATH=/var/home/oak/.cache/ms-playwright /var/home/oak/Codes/projects/tablet-wall-ai/.venv/bin/python /var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/verify_workspace.py --out /var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/final-visual --jobs composition measured
rtk proxy env PYTHONDONTWRITEBYTECODE=1 PLAYWRIGHT_BROWSERS_PATH=/var/home/oak/.cache/ms-playwright /var/home/oak/Codes/projects/tablet-wall-ai/.venv/bin/python /var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/verify_workspace.py --out /var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/candidate --jobs composition navigation
rtk proxy git diff --check
```

Every browser rerun needs a new output directory. The script is an external, rerunnable evidence artifact, not an edited acceptance driver.

## Visual evidence and mismatch ledger

The latest candidate covers 1440×900, 390×844, 320×844 and 820×1180, plus 200% CSS root text enlargement at390. Viewport/full-page PNGs, DOM, accessibility snapshots, config, traces and request/response evidence remain with each screenshot. Direct PNG inspection covered the selected-reference desktop/phone concepts, rendered task views, pending/error/conflict, offline, measured phone preview and enlarged text. Live assertions also exercised empty and required model setup. Source/metric checks do not replace the recorded screenshot judgment.

- [Images desktop](/var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/candidate/composition/composition-live-Images-1440x900-r4-logical-334323151d-viewport.png).
- [Images phone](/var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/candidate/composition/composition-live-Images-390x844-r4-logical-334323151d-viewport.png).
- [Tablets desktop](/var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/candidate/composition/composition-live-Tablets-1440x900-r4-logical-334323151d-viewport.png).
- [Tablets phone](/var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/candidate/composition/composition-live-Tablets-390x844-r4-logical-334323151d-viewport.png).
- [Saved phone](/var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/candidate/composition/composition-live-Saved-390x844-r4-logical-334323151d-viewport.png).
- [Settings phone](/var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/candidate/composition/composition-live-Settings-390x844-r4-logical-334323151d-viewport.png).
- [Enlarged-text Images](/var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/candidate/composition/composition-text-200-percent-Images-390x844-r5-logical-334323151d-viewport.png).

| Reference or finding | Actual result and disposition |
| --- | --- |
| Recognizable gallery before fit/Show | Four actual supplied-art windows lead at303.8px on phone. Show is fully visible at795.6–839.6px. Search and a selected-controls link support larger inventories. |
| Roster with direct Identify | Four row Identify actions occupy402–446,521–565,640–684 and759–803px on390. Selection and name stay in their actual owner. |
| Short prototype header | Production retains the real44px Issues action and current evidence. It takes more height than prototype-only text; it does not duplicate diagnostic cards. |
| Selected-image reference column | Desktop retains a passive whole-source thumbnail as well as the shared wall below controls. Phone omits that redundant passive thumbnail. There is still only one writable image selection owner. |
| Plain saved records | Actual geometry thumbnails deliberately exclude art because arrangements do not store images. Scene thumbnails use available inventory data. Missing data is not filled from prototype fields. |
| Enlarged text | The first inspection found broken Issues wrapping and a squeezed search field despite no page overflow. Fixed flex behavior; final screenshots show an intact Issues label and full-width search. |
| Arrange result/Apply proximity | The source composition now places the same stage before Apply and custom forms after it. This isolated checkout still has the baseline3:2 canvas and central labels. Final stage appearance and phone Apply placement require Terra integration; this report does not claim a combined visual pass. |

The documented historical baseline in EXPERIENCE-ACCEPTANCE.md used application `beca736` and one supplied image. Its phone task panel began at768px. The current four-image candidate begins the active panel at156px, gallery at303.8px and Show at795.6px. Both are software fixtures with the supplied artwork; the library inventories differ. These are entry-position observations, not task-time savings or a controlled usability study.

## Browser isolation, cleanup and remaining limits

[Browser preflight](/var/home/oak/.local/share/tablet-wall-ai/frontend-redesign/2026-11-02/workspace-2b2fa48/browser-preflight.txt) records T3 preview unavailable, Chrome DevTools' absent `/opt/google/chrome/chrome`, Playwright MCP's absent `chromium-1252`, and harness doctor with no daemon/active connection. The explicit authorization permitted cached `chromium-1200` through read-only parent `.venv` Python. No browser install, display change, user-browser attach or external browser service was used.

All owned contexts closed and browsers disconnected. Each private server process group exited; every recorded loopback port was checked closed; temporary DB/assets/media/server/browser XDG data was removed. The final audit found no recorded browser/server PIDs remaining. Earlier failed driver iterations also ran Rig cleanup. One initial old-paint cleanup sampled two Chromium PIDs before reap; both were gone on the subsequent audit. No live DB, assets, tablet, hotspot, firewall, service, network admission, user browser, push or PR was changed.

Only the seven owned app files, three owned/focused test files and this new handoff document belong to the commit. Existing Node tests were adapted only for visible focus recovery and the stage node lookup. New tests verify one-node relocation, field focus, native entry points, joining disclosure transitions and immediate task redraw ordering. No nested agent was used.

Model the Domain kept all authoritative records in the existing session/content/grid/device owners and limited new state to keyed DOM presentation. Karpathy's surgical-change rule kept stage/backend/deployment/acceptance sources out of this patch. The design-system and accessibility skills retained tokens, native semantics, real metadata size, target size and DOM order. Deslop/unslop/technical-writing guided the final diff and handoff.

The full38-scenario suite was not run. Native zoom, virtual keyboard, IME, assistive technology, Safari/Firefox, real tablet/optical accuracy, sleep, TLS/ingress and soak remain unverified. The tablet signature and physical model declarations are explicit simulation fixtures. Ruler uncertainty and mixed heterogeneous pinned dimensions are not newly established by this package. Root owns the heterogeneous-size combined trial, stage-specific failure matrix, independent final review and complete experience verdict after integrating the stage. The navigation job should then assert immediate `data-presentation`; the central-label acceptance assertion must be updated to accessible external identities without changing guard intent.
