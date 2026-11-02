# Architecture for one operator workspace

This is the documentation-only sketch and rationale for [PLAN.md](PLAN.md). The caller experience is the contract. Signatures below describe plain JavaScript responsibilities, not a TypeScript migration or executable stubs. Acceptance is in [ACCEPTANCE.md](ACCEPTANCE.md).

## Problem

The operator needs one complete wall application. Today `physical.js` composes a shared mutable object, multiple task modules, protocol fences, DOM controls, and form state. A second controller owns logical editing and scenes. Replacing the appearance alone would leave duplicate writers, lost forms, and misleading preview status. A framework rewrite would risk working geometry, lifecycle, rendering, and admission behavior without improving the requested outcome.

The backend's committed layout and scene, measurement histories, snapshot digests, admission, and current render tokens are strong existing contracts. Preserve those boundaries. Concentrate browser authority adoption and guarded commands in one session. Keep arrangement, tablet forms/lifecycle, and image selection as domain owners. The workspace controls presentation and focus, not persistence.

## Usage

A person opens Add tablets and watches clients appear. Arrange proposes a shape using the actual selected screens. Apply arrangement commits geometry. Images selects or uploads content and previews Fit/Fill. Show image commits content. The live summary then waits for current reports. An offline screen opens targeted recovery. Saved arrangements and scenes remain different choices in the same application.

The view code consumes a small set of owners. It does not fetch configuration or choose an ETag:

```text
session = OperatorSession.create({ transport, clock })
arrangement = ArrangementEditor.create({ session })
tablets = TabletTask.create({ session })
images = ImagesTask.create({ session })
workspace = Workspace.create({ session, arrangement, tablets, images })
workspace.open('tablets')
session.start()

arrangement.beginGrid()
arrangement.setShape({ rows: 1, columns: 4 })
arrangement.setCommonMount(0)  // Only after explicit operator choice.
review = await arrangement.preview()
result = await arrangement.apply(review.id)
// result is applied, conflict, refused, failed, or uncertain.
// Applied means persisted. Current image reports can still be pending.

workspace.open('images')
await images.upload(file)     // Publishes/selects. Does not show.
images.select({ assetId, fit: 'contain' })
result = await images.showSelected()

workspace.openTablet(oldId, { focus: 'preserve' })
plan = await tablets.previewReplacement({ oldId, newId,
    hardware: 'same_hardware', active: true, savedRefs, transferLabel: true })
result = await tablets.confirmReplacement(plan.id)
```

The root composition creates each owner once and destroys it once. A task switch does not create another socket, mutable authority object, or copy of the roster. The view receives readonly snapshots and emits domain intent. Only the explicit task-open path requests focus movement.

## Existing system and rationale constraints

### How output reaches a tablet

`GET /api/v3/config` combines durable layout, scene, pins, labels and snapshot facts with runtime registration, mapping and paint evidence. `tabletwall/operator_state.py:durable_etag` excludes runtime and asset URL/name/availability fields. Heartbeats do not advance durable authority. Registration, measurement history, and snapshots can change the ETag without moving a screen.

An image choice lives locally in `OperatorContent`. Show sends asset identity and fit to `PUT /api/v3/scene`. The route checks the ETag before and after asynchronous asset resolution. `_commit_wall` builds and persists a detached proposal before replacing shared memory and broadcasting. Geometry commands use their own guarded routes. Clients receive current connection/generation/revision/render/mapping/asset tokens, decode and paint, and report against that exact instruction. Server ownership and sequence checks reject old evidence. `OperatorState.tabletState` determines current report status with monotonic freshness.

`OperatorSync` currently fences old GETs around WS events and slow reconciliation. Preserve that policy when moving ownership. Do not let a task response overwrite a newer config, clear a newer form edit, or revive a superseded paint acknowledgement.

### Why existing boundaries survive

`DECISIONS.md` records preservation of classic script order and extraction around explicit factories. `PROTOCOL.md` and the current v3 routes separate layout from scene deliberately. `docs/tablet-wall-readiness/VERIFICATION.md` records cross-kind safety copies, empty replacement refusal, pinned-history validation, and late-write/transaction tests. These are constraints, not redesign opportunities. Source confirms that Remove has a separate lifecycle route and Clear wall has a distinct explicit-confirmation route.

This synthesis uses local source, durable project documents, and both independent reports for rationale. It performs the how/why investigation sequentially under the explicit no-nested-agent rule. It does not claim new issue-tracker, chat, observability, or analytics evidence. Root owns external integration. No inference about hardware or deployment readiness follows from this plan.

## Shape

### Data first

Keep wire schemas private to the session and task adapters. Use ordinary objects with JSDoc discriminants where useful. Preserve the two geometry representations exactly:

```text
Geometry =
    { kind: 'logical', width, height,
      placements: Record<DeviceId, { x, y, w, h, bezel }>, sizing }
  | { kind: 'physical', bounds,
      slots: Record<DeviceId, { center_x_mm, center_y_mm, mount_angle,
        nudge_x_mm, nudge_y_mm, profile_revision,
        calibration_revision, participating }>, sizing }

Authority = { config, etag, revision, generation, supported }
Runtime = { devices, transportState, observedAt, freshness }
SceneIntent = { type: 'image', asset: AssetId,
                fit: 'cover' | 'contain', background? }

ArrangementDraft =
    { kind: 'idle' }
  | { kind: 'manual', baseEtag, baseGeometry, geometry, undo, redo, version }
  | { kind: 'grid', baseEtag, intent, membership, inputVersion,
      preview: null | { id, command, layout, guards, baseEtag, inputVersion } }
  | { kind: 'conflict', retainedDraft, latestAuthority, reason }

GridMember = { id, included, membershipSource: 'automatic' | 'operator',
               size, sizeSource: 'saved' | 'viewport' | 'fallback' | 'operator',
               explicitMount: null | 0 | 90 | 180 | 270 }

TabletForms = Map<DeviceId, {
    name: { baseline, value, editVersion, baseEtag, dirty },
    profile: { baseline, value, editVersion, baseEtag, dirty },
    calibration: { baseline, value, editVersion, baseEtag, dirty },
    modelChoice, conflict, pendingCommands, lastResult
}>

ImageTask = { inventoryState, items, selectedIntent, baseEtag,
              selectionVersion, dirty,
              upload: idle | transferring | processing | succeeded |
                      rejected | failed | uncertain }

View = { task, selectedId, stageMode: 'live' | 'arrangement-preview' |
         'image-preview', returnFocus, taskScroll }

Outcome =
    Applied { authority, reports: 'pending', subject }
  | Conflict { latestAuthority, retainedIntent, subject }
  | Refused { reason, fieldErrors, retainedIntent, subject }
  | Failed { reason, retryable, retainedIntent, subject }
  | Uncertain { reason, reconcileRequired: true, retainedIntent, subject }
```

Geometry records remain JSON-compatible keyed objects, not ES Map instances. The actual existing payload field names remain authoritative. This sketch omits unrelated playback fields rather than replacing their schemas. Scene/test content is an existing discriminated union, not always an image. Never reinterpret relative units as mm or flatten calibration, mounted rotation, and browser orientation into one angle.

Per Model the Domain, discriminated drafts replace independent booleans that permit two conflicting arrangement previews. Tablet form values live by identity rather than in whichever input is currently visible. Per Prove It Works, applied state and current client proof remain separate observable results.

### Ownership map

All frontend paths below are under `frontend/controller/`.

| Owner and file | Owns | Does not own |
| --- | --- | --- |
| `operator-session.js`, new, with `operator-sync.js` as its transport helper | Config/runtime adoption, API error parsing, ETag/read fence, one socket/reconcile loop, command serialization, target/result identity, subscriptions and teardown. | DOM, input values, geometric editing decisions, thumbnail selection. |
| `operator-state.js` | Existing pure geometry, evidence, order and fence functions. | A second mutable store or transport. |
| `operator-grid.js`, `physical-stage.js`, `physical-sizing.js` under one arrangement owner | Manual/grid draft, original guard, membership/default provenance, preview command, undo/redo, physical and migrated logical edit policy. | Direct authority assignment or independent HTTP ownership. |
| `operator-devices.js` and retained measurement behavior/helpers | Keyed tablet forms, immutable action subjects, model batches, impact/rebind review, capture of exact pins/guards. | Global selected ID as an async action target, writable session state. |
| `operator-content.js` | Inventory, image intent, global fit, upload progress, previous-content convenience and saved-scene intent. | Automatic showing on upload, geometry authority, render proof. |
| `physical.js` | Thin composition, owner creation, event wiring and preserved advanced task integration. | New duplicate fetching, inline copies of task policy, a second authoritative config. |
| `operator-workspace.js`, new, `physical.html`, `operator-stage.js` | Open task/selection, stable DOM projection, focus/scroll, stage rendering, form hooks and action feedback. | Network calls, persistence, ETag updates, `showing = true` state. |
| Server `main.py`, `tabletwall/*` | Durable commit/admission, lifecycle/geometry validation, pins, snapshots, current render token acceptance. | Browser draft or presentation convenience state. |

`operator-sync.js` must call the session's ingest methods rather than independently mutate a state bag shared with views. The session can retain a private mutable object for compatibility with proven helpers during the first slice. Do not expose it as `session.state`. Remove migrated direct assignments from `physical.js` in that slice. One module privately owning mutable state is simpler than a generic event bus or a second store with adapters in both directions.

The existing classic IIFE/factory style can remain. Add scripts in explicit dependency order, with the composition loaded last. No bundler or import-system rewrite is required. Reuse `controller-geometry.js` calculations if they are pure. Do not import `controller.js`, its inventory runtime, or its independent socket into the primary workspace.

### Public contracts

```text
OperatorSession.create(dependencies)
    start() / destroy()
    subscribe(listener) -> unsubscribe
    view() -> immutable authority/runtime projection
    refresh(reason) -> current | stale | failed
    applyArrangement({ geometry, baseEtag }) -> Outcome
    applyGrid({ command, previewGuard, baseEtag }) -> Outcome
    showScene({ content, baseEtag }) -> Outcome
    saveName({ id, value, baseEtag }) -> Outcome
    setModel({ id, modelId, baseEtag }) -> Outcome
    removeFromWall({ id, baseEtag }) -> Outcome
    clearWall({ confirm: true, baseEtag }) -> Outcome
    lifecycle and snapshot methods with their existing domain payloads
    identify/retry/reconnect with explicit id and current guard

ArrangementEditor
    view() / beginGrid() / beginManual()
    setShape(shape) / include(id, bool) / moveEarlier(id) / setMount(id, angle)
    edit(change) / undo() / redo()
    preview() -> review | refused | conflict
    apply(reviewId?) -> Outcome
    discard()
    observeSession(view) -> retain draft, or update untouched setup defaults

TabletTask
    fields(id) / editFields(id, group, patch)
    saveFields({ id, group, editVersion }) -> Outcome
    confirmModels({ ids, modelId, hardwareDeclared }) -> BatchOutcome
    previewForget(id) / confirmForget(planId, removeActive)
    previewReplacement(intent) / confirmReplacement(planId)
    identify(id) / retryImage(id) / reconnect(id)

ImagesTask
    view() / refresh() / select(intent) / discard()
    upload(file) -> selected | rejected | failed | uncertain
    showSelected() / previewSavedScene(name) / showSavedScene(reviewId)

Workspace
    open(task, { focus: 'heading' | 'preserve' })
    openTablet(id, { focus })
    render(view) / destroy()
```

These are domain operations, not a requirement for one trivial wrapper file per endpoint. Keep related snapshot methods with existing snapshot task code if that is smaller. The important contract is that no view coordinates GET/ETag mutation/write/roster refresh itself. Upload XHR remains in ImagesTask because it owns progress and cancellation; it uses the existing server-admitted endpoint and never adopts config from an upload response.

### Authority, conflicts, and command adoption

1. A draft captures its original ETag. Editing retains that base until discard, successful commit, or an explicit rebuild after comparison. A stale preview is never refreshed by replacing its If-Match silently.
2. The session serializes local durable commands. Busy state is task-scoped in the view. Runtime observation remains live during a command, but cannot destroy field values or change its subject. Backend CAS still protects other operators.
3. Every async request captures the target ID, payload, form editVersion, request ticket, and expected guard before awaiting. The result updates that subject. Mark a form clean only if its current editVersion/value still matches the submitted version. A selection change cannot redirect the result.
4. WS events invalidate older read tickets. GET config, fallback roster GET, inventory refresh, model-history fetch, snapshot fetch, and lifecycle-preview responses each have ownership/version fences. A delayed result cannot overwrite newer authority or a later task input. Do not compare ETag strings as ordered revision numbers.
5. Command responses can be older than a WS/config update. Use existing compare/adoption rules and reconcile when ordering is uncertain. A late response can complete its named action without regressing authority. Snapshot-only changes and registration must not be missed because wall revision stayed equal.
6. Runtime-only evidence changes do not conflict with a draft. A durable ETag change from another operator marks it conflicted, retains the exact proposal and prevents apply. Review latest can show current authority alongside the retained values. Keep editing is allowed locally but does not enable apply. Explicit Rebuild preview or Discard starts from current authority.
7. Transport timeout means uncertain completion, not guaranteed refusal. Reconcile and inspect authoritative subject/config before enabling retry. Do not repeat lifecycle/recall/upload commands blindly.
8. Successful application adopts committed intent then waits for fresh matching paint. It must not carry old `showing` labels onto preview geometry or count an old acknowledgement for a new scene, mapping, socket, generation, or revision.

Only one output draft is active. Switching Arrange/Images resolves the old output intent with its own apply/show, discard, or stay decision. Inspecting tablets can retain it. Any immediate durable task command that would invalidate that intent resolves it first. Per-device field drafts may coexist and survive selection; a remote change marks their bases stale rather than clearing them. Browser unload warns about dirty intent. Persisted cross-restart local draft recovery is out of scope. On reopen, committed server state is restored and the UI does not claim an unsaved draft survived.

### First-join defaults and immutable reviews

Today `OperatorGrid.render` sets inclusion and aspect only when it creates a row. Registration can create that row before the online/viewport event. Fix the first incorrect transition rather than repeatedly ticking all online tablets.

Track inclusion and sizing provenance per ID. Before the operator edits membership/order or reviews a preview, an online transition can include an untouched unplaced member, and fresh viewport can replace its untouched fallback size. Use the existing aspect formula with positive whole relative dimensions, for example height 100 and width rounded from viewport ratio. Preserve saved dimensions and manually edited sizes. Sort newly eligible automatic members by stable display number.

After the selection/order is touched or any preview is reviewed, freeze membership/order and reviewed input. A new arrival is available but excluded until explicit Include. If ETag changes, retain the preview and require rebuilding it. A viewport transition must never mutate an already reviewed command, even if its previous fallback was poor. Surface the stale/default issue for review instead. Excluding a screen stays excluded through disconnect/reconnect. The same rule applies to a fifth registration during a label or arrangement edit.

### Bulk model confirmation without false atomicity

Use the existing explicit per-device assignment route. No new bulk transaction is justified for four tablets. The batch captures ordered IDs, names/numbers, chosen model, original guard, and an explicit hardware declaration. The confirmation must show the actual selected list. Matching telemetry is only a suggestion. Existing model scale remains approximate and must pass current mapping readiness before measured use.

```text
confirmModels(batch):
    reject if hardwareDeclared is false, selection is empty, or a draft conflicts
    expected = batch.reviewedEtag
    completed = []; remaining = batch.ids
    for id in batch.ids:
        obtain current fenced authority
        if current.etag != expected:
            stop with conflict(completed, remaining)
        send explicit assignment(id, modelId, If-Match=expected)
        if response is timeout or network-uncertain:
            stop with uncertain(completed, id, untouchedRest)
        if response is refused/conflict:
            stop with partial(completed, id, untouchedRest)
        require response.etag
        expected = response.etag
        completed.append(id)
    reconcile configuration and pins
    return completed with measured-readiness results for every selected tablet
```

A fresh GET is a check against the expected chain, not permission to use whatever ETag it returns. External durable edits between GET and PUT yield 412. A duplicate ID, disconnected client, unsupported model, changed mapping, or mismatching signature remains visible. Do not call the entire group ready merely because assignments saved. A retry reviews only unresolved subjects with fresh pins and guard, never rewrites completed tablets silently.

Common mounted rotation is an explicit operator declaration captured once with the selected list. It can set all four to 0, 90, 180, or 270, with overrides. A labelled initial prompt remains unanswered until chosen. Preserve a valid existing stored angle when reopening an arrangement. Do not infer 90/270 from a landscape viewport.

### Lifecycle, snapshots, and compatibility migration

Remove calls `POST /api/v3/devices/{id}/remove`. Last and middle removal use the same lifecycle plan, leaving registration/history/saves intact. Clear calls `POST /api/v3/layout/clear` with `confirm:true`. Forget uses a current impact ETag and explicit active removal. Replacement captures old/new IDs, hardware declaration, connection ID, exact selected saved digests, transfers and revision mappings. Its preview/apply outcome remains backend-atomic under the existing lifecycle implementation.

Saved arrangements retain logical/physical routes and full pinned geometry. Scenes retain the existing named content records. To preview a scene, ImagesTask reads the saved content, checks availability, captures name/content/digest/base ETag, then **Show scene** calls guarded recall. A changed snapshot changes the guard and refuses recall until reviewed. Do not reconstruct a bundle from two writes.

| Compatibility capability | Primary destination and completion proof |
| --- | --- |
| Logical drag/resize, bezel, snap, custom wall/screen size | Arrange > Custom. Same local draft/Apply, numeric and keyboard alternatives, server remains unchanged until Apply. |
| Tile, Quick arrange, Pack, fit-to-tablets/fixed bounds | Arrange shape/tools. Reuse pure algorithms and send one guarded proposal. No direct v2 geometry writer. |
| Saved scenes | Saved > Scenes, with preview and Show scene. Save scope and replace/delete confirmation survive. |
| Per-tablet colour and all-tablet colours | Settings > Check wall, with named targets, explicit colour application and separate Show test colours command. Preserve existing colour endpoints as the narrow diagnostic exception described below. |
| Unavailable image replacement | Images > Choose replacement image. Same library, fit preview and Show, never implicit substitution. |

Migrate those callers before retiring `/controller/`. Keep the legacy entry functional during intermediate work, then replace its HTML/script entry with a styled forwarding page after parity passes. Remove obsolete primary imports and primary-only forwarding links in the same retirement slice. Backend v2 compatibility routes remain for clients outside this UI. Delete old controller scripts/styles only if no remaining HTML, tests, or supported diagnostic consumer uses them; otherwise leave them explicitly unreachable from normal navigation. Do not delete unrelated dead code.

Per-tablet colour currently uses `/devices/{id}/color` and `/devices/color`, without configuration CAS and outside the v3 config's colour projection. Reuse that existing diagnostic behavior through a named session method with immutable targets and explicit results. Read current colour from `/devices` for the diagnostic form only, behind a read fence. Do not merge this legacy roster read over v3 authority/runtime. Label it a test-colour setting, not a guarded arrangement edit or image paint proof. Serializing the browser command does not make it atomic across operators. A new v3 colour schema/guard is deferred; root must record this existing exception rather than claim every mutation has CAS.

### Ordinary endpoint reuse and new work

| Operation | Contract |
| --- | --- |
| Session/config/updates | Existing `GET /api/v3/config`, controller WS protocol 3, readiness GET. Retain slow reconciliation. |
| Grid/manual geometry | Existing grid preview/apply and logical/physical layout PUT, original guards and pins. |
| Model and measurement | Existing tablet-assignment, display, calibration routes and ruler helpers. Sequential batch is a new UI workflow, not a new endpoint. |
| Images | Existing admitted `GET /api/v3/images`, upload POST, scene PUT, current bytes and diagnostics. No automatic scene mutation from upload. |
| Remove/clear/forget/rebind | Existing lifecycle endpoints. Correct caller selection fixes final removal. |
| Arrangement/scene save, recall, delete | Existing kind-specific arrangement and scene endpoints. No record migration or bundle schema. |
| Colour tests | Existing colour routes only for diagnostic setting, with the explicit guard limitation above. |
| New backend HTTP schema | None required by this plan. Preserve the existing capability boolean. Request errors remain authoritative. |
| New deployment behavior | `--operator-uploads` opt-in, controlled backend env, factual preflight/help, generated-ingress tests. No live deployment change. |

### Upload launcher and admission boundary

The launcher currently rejects any enabled upload mode and reports disabled uploads. Add a per-launch CLI boolean. Default remains disabled. Permit the flag only in the existing direct-loopback trusted HTTP profile. The launcher owns the computed operator Origin, upload mode, tablet Origin and backend binding. Refuse inherited non-disabled modes rather than treating environment input as the opt-in. Existing auth-enabled HTTP rejection stays. No browser toggle changes admission and no new operator path is added to tablet Caddy.

Thread the flag explicitly through preflight/run settings without silently persisting it to the user's hotspot config. Backend env is `TABLET_WALL_UPLOAD_MODE=loopback` only for the flagged launch, otherwise `disabled`, and `TABLET_WALL_OPERATOR_ORIGIN=http://127.0.0.1:<backend_port>`. Keep `--host 127.0.0.1`. Preserve exact single Origin, peer, forwarded-header, file bounds, decode worker, immutable publication and storage checks. An unprivileged generated-Caddy test binds disposable loopback ports without invoking real hotspot discovery/firewall/service code.

`capabilities.uploads` indicates configured support, not a guarantee every current request is admitted. Add image remains hidden/unavailable when false, unknown gets Check connection, and a 403/503 explains request denial without suggesting a browser-side bypass. The flagged profile must pass a real operator upload to meet the product goal. A phone on the tablet network cannot access operator controls under this profile. Responsive upload testing can use a phone viewport on the admitted local origin.

## Visual implementation and deletion plan

Use three small style files rather than another override tail. `operator-tokens.css` owns the compact values in PLAN. `operator-workspace.css` owns page/task/control layout. `operator-stage.css` owns stage/labels/selection/bezels. The shell worker owns all three. Use low-specificity purpose classes and semantic attributes. No token generator or separate component library is needed.

Five recurring patterns suffice: task region/footer, labelled field/validation, named tablet row/status, image choice, and review/confirmation. Their behavior is specified in PLAN and acceptance. Avoid one component per visual variant or a universal form/schema engine. Put markup in the shell, behavior in the domain owner, and pass stable action/form hooks between them.

During migration, remove injected shell markup from task factories as their views move into `physical.html` or `operator-workspace.js`. The shell owns generated rows and form nodes; domain modules receive input values and emit view data through the agreed adapters. Do not alternate ownership of a node between two renderers. Critical hooks are task identity, device ID, action, field, and review ID. Use stable IDs for existing automated flows when sensible. QA prefers accessible names; hooks supplement ambiguous identities.

Replace the primary page's `physical-legacy.css` and `physical.css` imports once all retained primary panels, including advanced and Experimental, have styles. Do not globally restyle `controller.css` while the compatibility editor is still usable. Inspect the actual primary route after each style slice. Remove old primary style files only after reference checks. Keep one primary stylesheet set at the finish line. A local licensed font is an implementation asset with its licence, not a network dependency.

## Synthesis decision

Candidate A in PLAN is the base. It concentrates the complexity of one live wall behind a session and small task owners. Callers choose an outcome rather than coordinating load/validate/save phases. It hides protocol ordering while exposing real task boundaries, approximate dimensions, and separate commits.

Candidate B hides setup sequence well, but exposes page navigation and repeated draft coordination during normal adjustments. Borrow its short arrangement guide, not its permanent page workflow. Borrow Opus's contextual joining, group setup, thumbnail library and recovery prompts. Borrow Sol's task-local commit semantics, field identity, exact guards and conservative data meaning. Reject the combined pending commit, bundled record reinterpretation, and unconditional focus movement.

The existing reviews supplied four independently produced structural sketches across two reports. This synthesis compares their two distinct whole-application shapes without a new arena or nested agent. It is not a measured usability contest.

### Red-flag screening

| Architect red flag | Candidate A resolution | Candidate B assessment |
| --- | --- | --- |
| Shallow module/pass-through | Session hides fencing, ordering, errors and adoption. Task owners complete domain actions. Do not split one method per file or add a generic forwarding bus. | A page-only module hides little unless the same domain owners exist beneath it. Extra flow wrappers add another level. |
| Information leakage | Wire shapes and ETags stay behind session/task boundaries. Views receive formatted task state and explicit outcomes. | Every page would otherwise learn guard/navigation rules. A shared session mitigates this but does not remove page coordination. |
| Temporal decomposition | Owners are session, arrangement, tablet forms/lifecycle, images and view. No load/validate/save module chain. | A step controller can spread one arrangement invariant across pages. The borrowed short guide keeps one owner. |
| Split ownership | One authority writer, one arrangement draft, keyed tablet forms, one image choice. Runtime read projections never become another durable store. | Route-scoped stores are rejected. Shared owners make B viable, but its UI still has more transitions. |
| Two ways to do one task | Migrate parity then retire normal compatibility entry. One image library and one arrangement Apply. | Separate dashboard shortcuts plus full task pages risk duplicate paths; no reason to pay that cost here. |
| Importable internals | Private IIFE/factory state, no exported mutable bag. Public snapshots are readonly by convention/freezing in tests. | Same restriction is needed across every page. |
| Hand-synced list | Use server model/capability/snapshot data once. Derive names, status, gallery and nav from one owned task/config definition. | Multiple pages must not copy roster, inventory, or capability enumerations. |

## Tradeoffs accepted

- We accept two output verbs in exchange for truthful commits and reuse of tested backend transactions.
- We accept a sequential, visibly partial four-tablet model batch in exchange for no new bulk persistence contract.
- We accept an explicit common mount declaration in exchange for avoiding an unsupported 90/270 guess.
- We accept local-only upload in the opted-in hotspot profile in exchange for preserving tablet ingress isolation.
- We accept in-memory drafts with unload protection in exchange for avoiding a new shared persistent draft product.
- We accept preserving existing snapshot names in exchange for avoiding invented provenance and destructive history migration.
- We accept a narrow legacy diagnostic colour command without CAS in exchange for full capability parity without expanding the config schema. It cannot be described as a guarded image/arrangement transaction.

## Alternatives considered

A real atomic combined wall command could transactionally validate layout and asset, save a prior wall, commit once and broadcast one render intent. That is technically viable, but requires a new durable bundled record and migration semantics. It adds no necessary capability for this task, so it loses to task-local commits.

Keeping the current composition state and restyling all panels is cheaper initially. It leaves selection-driven field loss and competing state writers as conventions rather than ownership rules. Extract only the session and actual conflicting domain ownership, not every helper.

A framework/store migration could enforce readonly state more strongly, but adds build/dependency risk and a large rewrite. Existing factories and pure helpers can encode the required boundaries. A future rewrite needs evidence beyond aesthetic preference.

## Responsibility and file ownership

The initial shell handoff has a concrete projection. Domain owners provide `stage = { mode, geometry, content, selectedId, tabletNames, liveEvidence }`, where `liveEvidence` is omitted from preview tile rendering. A separate `liveSummary = { text, currentCount, participatingCount, stale, issues }` always describes committed state. Tablet field projections carry subject ID, value, dirty/error/busy state, and editVersion. Task footers carry their exact action label, enabled state, and review summary. Technical details are inert display data, not a write guard chosen by the view.

Worker B binds named callbacks such as `selectTablet(id)`, `openTask(task)`, `editTabletFields(id, group, patch)`, `previewArrangement()`, `applyArrangement(reviewId)`, and `showSelectedImage()`. Worker A owns their implementation. At binding time each async action captures its subject/review ID. This local callback contract does not introduce a global event bus. Agree these projections and hooks before parallel editing, then change them only with root reconciliation.

Use four workers at most. They are not alone in the codebase and must not revert one another. Root owns integration, app-level reconciliation and acceptance verdict. Assign each touched path to one writer before work starts.

| Worker | Exclusive writable responsibility | Integration contract |
| --- | --- | --- |
| A. Functional workspace and domain/session | All primary controller HTML/JS, compatibility entry forwarding after parity, reused logical helpers, related `tests/*.test.js`. Includes the domain/session paths above, `physical.html`, `operator-workspace.js` and `operator-stage.js`. No CSS or font files. | One writer owns DOM structure and its behavior, eliminating a temporary split between injected forms and the new renderer. Publishes stable task/state/control classes for B after a working vertical slice. Owns primary commands/drafts and parity. |
| B. Visual system and responsive styling | Three new controller CSS files, obsolete primary CSS removal, local fonts/licence and client recovery CSS only if reproduced. No HTML or JS edits; request markup changes through root/A. | Starts from A's integrated working markup and task classes. Creates the warm technical visual treatment and verifies the real route at desktop/phone/zoom. Root/A changes stylesheet imports after B publishes the assets. |
| C. Operator upload/deploy | `deploy/hotspot.py`, relevant launcher script/Makefile help if necessary, `deploy/IMAGE-WALL-RUNBOOK.md`, `tests/test_hotspot.py`, `tests/test_ingress.py`, admission-focused tests. Any necessary `main.py`/`tabletwall/*` change belongs exclusively here. | Default disabled, per-launch loopback flag, exact configured origin, generated tablet ingress still denied. No new HTTP schema planned. Notify root if that contract cannot be met. Only main.py writer if one is needed. |
| D. Portable browser QA | New `simulator/browser/redesign_acceptance.py`, `simulator/browser/operator_accessibility.py` updates, focused fixture helpers and driver tests. No application edits. | Uses semantic UI actions and four independent shipped clients. Distinguishes UI proof from fixture injection. Produces screenshots, traces, console/network, identities, failures and cleanup. |

Worker A's scope is intentionally sequential across domain tasks. Do not split it into several workers who all edit `physical.js`. Worker B can prepare the shell and visual baseline while A establishes the contract. Worker C can run in parallel immediately because its boundary is fixed. Worker D starts fixture/driver work against the agreed names and completes after integrated flows exist. Root reassigns ownership explicitly before moving work; no two workers write the same file concurrently.

## Implementation reconciliation

Root accepted the synthesis before implementation. On 2026-11-02, root reassigned
HTML, task markup and stage rendering from B to A, while B owns styles/fonts only.
The reason is concrete: existing domain factories inject the very form nodes being
migrated. One vertical-slice owner can remove those competing writers together,
then a styling owner can work against stable actual markup. C starts in parallel
with A; B and D start after A's working contract is integrated. No public state or
backend behavior contract changes. This replaces the original simultaneous A/B
DOM handoff and avoids asking separate writers to coordinate transient selectors.

No application implementation exists in this planning commit. The synthesized contracts are accepted for root's next step under the default architect agreement. No runtime acceptance or independent implementation review is claimed.

Before closing each implementation unit, root records any accepted deviation here, with the accepting owner/review and updated affected signatures, outcomes and ownership. Do not update the plan merely to excuse an implementation that violated it. Local naming changes do not need a new architecture. Repeated workarounds across unrelated tasks, duplicated draft writers, or two incompatible command outcomes require re-grounding the shape before proceeding.

## Open questions and risks

Can the launcher-generated Caddy test prove operator isolation without touching the host network? The required test uses unprivileged disposable loopback listeners. If Caddy is unavailable, admission unit tests alone do not close that acceptance item.

Do profile/calibration forms lose values in additional navigation paths? The reviewed source clears their dirty flags. Worker A must investigate and cover actual values/version behavior, not only the known label case.

Does the client recovery screen clip at both target orientations with a valid simulation? The review trigger used a nonmatching signature. Treat it as unverified until rendered, while retaining the responsive acceptance requirement.

Can all preserved Experimental controls use the new markup contract without expanding domain extraction? Preserve them through an adapter owned by A if needed. Do not promote them or silently drop them to meet a screenshot target.

These are implementation checks, not requests for another human checkpoint. Environmental blockers and accepted deviations stay explicit.

## Next implementation step

Implement the private session boundary and keyed tablet/grid state, then prove late four-client joins, retained form edits and final-tablet lifecycle removal before completing the new shell.
