# Dependable image wall architecture

This is the implementation contract for one operator workflow that can arrange, show, inspect, and recover a spanning still image. It preserves logical wall units and measured physical millimetres. It does not convert a working logical layout into guessed millimetres.

Status on 2026-11-01: proposed contracts, grounded in current source. This document alone does not implement them. Only this file belongs to the design author. The other agents retain their files and branches. No nested agents, live data changes, firewall changes, network configuration changes, commits, pushes, or pull requests are part of this design task.

## Evidence and present structure

All four assessments were read in full. Their observations are historical evidence at `0ff56e30dfd6b2f92995569faa2d6e7fdc90fa8f`:

- [Opus existing report](reviews/opus-5.5-existing-report.md) supplies the simulated operator journey, sequential tiling problem, false capability alarm, and proposed consolidation.
- [Terra report](reviews/terra-6.1-high.md) stresses dimension preservation, presentation evidence, selected saved-layout migration, and hardware limits.
- [Sol report](reviews/sol-6.1-high.md) establishes the misleading physical scene readback, connection/mapping evidence requirements, and lifecycle boundaries.
- [DeepSeek report](reviews/deepseek-v4.1-flash.md) identifies the missing reverse safety copy, UUID arrangement order, physical Forget fence, auth composition, and upload-dependent diagnostics.

The shared checkout is moving while implementation agents work. HEAD observed during this design was `ef99cb814149c64d582403098533e91f23773cd4`. For example, the current logical controller already accepts protocols 2 and 3 in its image-capability checks. Do not recreate that report finding as an unfixed task. Capability support still does not prove presentation.

The existing data flow is request validation, detached wall proposal, SQLite commit, live dictionary replacement, and socket notification. Device roster mutations can join the wall transaction through `device_changes()`. The hub chooses logical frames or physical render plans. Physical plans load the profile and calibration revisions pinned by each slot, then adapt model calibration to the live viewport. The tablet performs the final CSS/backing-pixel transform and asynchronous image decode.

The current source boundaries constrain the design:

| Source | Existing responsibility and consequence |
| --- | --- |
| [main.py](../../main.py), `_commit_wall`, `_config_payload`, `_require_config_etag` | Keep one durable commit boundary and the existing v3 concurrency mechanism. Config currently omits the scene. |
| [state.py](../../tabletwall/state.py), `_project_scene`, `_wall_state`, `_render_frame`, `device_changes` | Layout, scene, generation, and revision already have separate meanings. `_wall_state` currently synthesizes a neutral logical wall for physical mode. `_render_frame` can change on viewport updates without a wall revision. |
| [persist.py](../../tabletwall/persist.py), `transaction`, `_runtime_layout`, `save_layout`, `_DEVICE_FIELDS` | Reuse SQLite transactions and existing saved layouts. Missing logical `kind` is a legacy representation, not a unit conversion. Roster persistence is explicitly whitelisted. |
| [hub.py](../../tabletwall/hub.py), `_send_wall_to_device`, `_broadcast_wall` | Reuse bounded writers and v3 config notifications. Keep per-device delivery separate from controller state projection. |
| [displays.py](../../tabletwall/displays.py), `copy_records` | Existing revision offsets can append copied profile/calibration histories without editing source records. |
| [tablet_models.py](../../tabletwall/tablet_models.py), `effective`, `copy_assignment` | Model snapshots are pinned by revision. Orientation and browser insets affect the effective mapping. Model-derived scale remains approximate. |
| [geometry.py](../../tabletwall/geometry.py), `fit_matrix`, `normalized_source_to_panel` | Global contain arithmetic exists. The product contract and callers still restrict or hardcode cover. |
| [client.js](../../frontend/client/client.js), `analyzeImageContent`, `drawWallImage`, `drawPhysicalImage`, `applyRenderFrame` | Reuse stale-load cancellation and explicit failures. Add evidence after actual canvas drawing. Fix logical v3 construction where `**logical_frame` currently overwrites `type: render` with `type: wall`. |
| [physical.js](../../frontend/controller/physical.js), `physicalFromConfig`, `ingestConfig`, `applyLayout` | Reuse drafts and conflicts. `physicalFromConfig` currently copies logical dimensions into empty mm bounds. Remove that implicit conversion from the primary workflow. |
| [physical-sizing.js](../../frontend/controller/physical-sizing.js), `packSlots` | Existing row packing is the geometric precedent. Python owns the accepted grid result; the browser consumes its preview. |
| [routes](../../tabletwall/routes), `assets.py`, `devices.py`, `diagnostics.py` | APIRouter modules already exist. Extract only routes/helpers needed for this work. Do not reorganize all of `main.py`. |
| [auth.py](../../tabletwall/auth.py), [media.py](../../tabletwall/media.py), [tablet-routes.caddy](../../deploy/tablet-routes.caddy) | Preserve middleware, exact origins, proxy credentials, and the tablet allowlist. Diagnostics admission must stop depending on upload enablement. |

## Two viable structures and the decision

### A. Extend the existing v3 state and add bounded command helpers

Keep the live `wall` and `devices` dictionaries, SQLite, pinned display records, and logical/physical layout union. Extend `GET /api/v3/config` into the complete operator read model. Add small pure modules for grid construction, scene normalization, render evidence, and identity migration. Extract the new operator routes into APIRouters with explicit callbacks to the existing commit boundary.

The unified console owns one committed config, one draft of its tagged layout, and a separately edited scene. A logical stage adapter uses units. A physical adapter uses millimetres and pinned measurements. Both use shared image selection, fit, lifecycle actions, errors, and status. `/controller/physical.html` is the primary Wall console for either kind. `/controller/` remains a labelled logical compatibility editor until parity checks justify redirecting its entry. Existing logical rendering stays usable during this change.

This requires no new database tables, no guessed scale, and no new installation identity. It leaves two geometry adapters to maintain. Rebind must explicitly repair selected saved layouts because browser UUIDs remain their keys.

### B. Introduce an installed-tablet registry and an application service

Add a durable `installed_tablet_id`, human label, and current browser binding. Layout entries reference installed tablets. Browser UUIDs become endpoints beneath that registry. A `WallApplication` service owns state reads, transactions, mapping versions, and all logical/physical commands. Routes are thin adapters. The console consumes the same state union as A.

Replacement changes one binding rather than rewriting every saved layout. Both existing layout kinds remain dimensioned until an explicit conversion with operator-supplied scale or complete measured replacement is approved. This structure is viable, but requires schema migration, backup support, roster/history migration, and migration of legacy callers before it earns its simpler replacement behavior.

| Decision criterion | A | B |
| --- | --- | --- |
| Preserve the demonstrated logical wall | Directly | Requires endpoint and identity migration |
| Reuse existing commit/roster tests | Mostly unchanged | Many contracts move into the service |
| Saved-layout repair | Explicit transactional rewrite | Stable installation binding |
| Independent implementation now | Small helpers with one integration owner | Core service and migration must land first |
| Risk for the first dependable image wall | Smaller | Broader |

Choose A. The Model the Domain principle gives the layout and evidence discriminated shapes below. Karpathy's surgical-change rule keeps the existing durable model and commit path. B is a future option if repeated identity migration makes the explicit repair costly. The Opus suggestion to make every layout mm-based is not accepted for this delivery. A default `0.17 mm/px` cannot recover a real scale from a `320 x 60` logical arrangement.

## Authoritative state and scene

`GET /api/v3/config` is the authoritative operator response for both kinds. Keep the existing `schema: 2` storage/config marker and add `operator_state_version: 1` for this additive contract. Protocol major 3, database schema version 3, and operator-state version are distinct values. An unsupported operator-state version produces an explicit upgrade state in the UI.

The response has these named types. They are signatures and data contracts, not production stubs:

```text
Layout = LogicalLayout | PhysicalLayout
LogicalLayout = {
  kind: "logical", width: PositiveInt, height: PositiveInt,
  placements: Map<UUID4, LogicalPlacement>, sizing: Sizing
}
LogicalPlacement = {
  device_id: UUID4, x: Int, y: Int, w: PositiveInt, h: PositiveInt,
  bezel: {left: NonnegativeInt, right: NonnegativeInt,
          top: NonnegativeInt, bottom: NonnegativeInt}
}
PhysicalLayout = {
  kind: "physical", bounds: {x: Finite, y: Finite,
                            width: PositiveFinite, height: PositiveFinite},
  slots: Map<UUID4, PhysicalSlot>, sizing: Sizing
}
PhysicalSlot = {
  center_x_mm: Finite, center_y_mm: Finite, mount_angle: FiniteDegrees,
  nudge_x_mm: Finite, nudge_y_mm: Finite,
  profile_revision: PositiveInt, calibration_revision: PositiveInt,
  participating: Bool
}
Sizing = {mode: "fixed" | "tablets", padding: NonnegativeFinite}
Scene = {layout: "active", content: SceneContent}
SceneContent = {type: "color"} | {type: "calibration"} | ImageContent
ImageContent = {
  type: "image", asset: AssetID, fit: "cover" | "contain",
  background: HexRGB, intrinsicWidth: PositiveInt, intrinsicHeight: PositiveInt
}
SceneInput = {content: {type: "color"} | {type: "calibration"} |
  {type: "image", asset: AssetID, fit?: "cover" | "contain", background?: HexRGB}}
OperatorConfig = {
  schema: 2, operator_state_version: 1, generation: String, revision: Int,
  etag: String, layout: Layout, scene: ProjectedScene,
  displays: Profile[], calibrations: Calibration[],
  referenced_displays: Profile[], referenced_calibrations: Calibration[],
  tablet_models: ModelMap, tablet_assignments: AssignmentMap,
  device_labels: Map<UUID4, String | null>,
  snapshots: {layouts: SnapshotSummary[], scenes: SnapshotSummary[]},
  capabilities: OperatorCapabilities, runtime: OperatorRuntime
}
SnapshotSummary = {name: String, kind: String, valid: Bool, etag: String}
OperatorRuntime = {
  observed_at: ISO8601, devices: Map<UUID4, DeviceStatus>,
  presentation: {owner: "static" | "playback", state: String}
}
DeviceStatus = {
  online: Bool, last_seen: ISO8601, protocol: Int | null, caps: String[],
  number: PositiveInt | null, label: String | null,
  viewport: Viewport | null, wake_lock: String | null,
  mapping: MappingStatus, render: RenderStatus, identify: IdentifyStatus | null
}
```

`Sizing.padding` must be integral for logical layouts. Bezel sums must leave a positive active logical rectangle. Every numeric field rejects booleans, NaN, and infinity. Generic physical editing retains existing finite mount-angle support. Grid presets use quarter turns only.

Legacy logical documents without `kind` project as `kind: logical`. Missing sizing projects as `{mode: fixed, padding: 0}`. Missing image fit means cover. Missing image background means `#0b1120`, the current renderer's `PATTERN.background` colour. Preserve that appearance. `ProjectedScene` adds only server-derived same-origin `url` and optional library name/availability. Never accept client-supplied URL, intrinsic size, projection name, revision, or generation as scene input. Missing bytes retain their ID and dimensions and project an unavailable state. They never become a colour scene.

The content schema remains the existing image/calibration/colour vocabulary. Do not add a separate persistent mode for Identify, setup, blanking, or future video. A physical calibration test image is an ordinary generated image asset with the committed bounds. The existing logical calibration pattern remains a logical-only diagnostic. Explicitly report unsupported content rather than treating it as bad measurements. Physical colour mode must draw the assigned device colour without requiring an image plan, so returning to the default scene does not falsely say calibration is missing.

`MappingStatus` comes from the same pinned profile, calibration, effective viewport mapping, and capability decision used to build the tablet frame. It is one of `ready`, `unplaced`, `needs_calibration`, `viewport_mismatch`, `zoom_changed`, `unsupported_content`, or `unsupported_client`, with a reason. It includes pinned revisions, method, uncertainty, model-confirmation state, and inset assumptions. It must not substitute the latest profile for the active slot's profile. A geometrically valid model plan is still labelled approximate. Existing inferred model assignments stay visible as unconfirmed estimates. New automatic matches are suggestions; only explicit confirmation assigns their scale. Known Air 2/Pixel C models require no new ruler measurements to try the physical path.

### Durable ETag and live state

Keep the existing bare hash in the JSON `etag` field and accept the existing quoted or bare `If-Match` form. The HTTP ETag identifies the durable configuration projection, not a byte hash of the full response with its live status. The endpoint remains `Cache-Control: no-store` and does not implement conditional GET caching.

The durable ETag covers generation, wall revision, normalized layout/scene, profile/calibration records, model assignments/history that affect mapping, device labels, and saved layout/scene digests. Snapshot save/delete and label changes must invalidate it even when the wall revision stays unchanged. Hash snapshot contents, not only names. Library inventory names, current time, heartbeats, number leases, sockets, evidence, and diagnostics do not invalidate it. Uploaded/curated asset validation remains content-addressed and independent.

Do not call `_render_frame` while building a config GET. Today that function increments `render_seq`. Readback must have no command or render side effects. Read cached expected render metadata or call a pure mapping helper.

V3 controller sockets retain `snapshot.config`, `config_updated`, and device lifecycle frames. Initial `snapshot.config` is the same projection as GET config. Durable changes emit `config_updated`; the console refetches config. Evidence/viewport changes emit a device status update. Preserve existing `device_updated.device` fields and add the new status rather than sending v3 data to v1 controllers. Subscribe first, apply the initial snapshot, and discard a slower HTTP read if a newer event arrived while it was pending. Keep a slow reconciliation read for stale/offline state. Reconnection fetches a fresh full snapshot. A dirty draft stays visible with its old ETag and a conflict message.

## Endpoints and commit rules

New operator mutations use `If-Match` and return the authoritative config plus operation metadata. GET config remains the common readback; new code must not normalize `_wall_state()` after changing a physical wall. Use existing asset inventory/upload endpoints for content selection. No parallel content store is introduced.

| Endpoint | Contract |
| --- | --- |
| `GET /api/v3/config` | Full config, scene, current state, capabilities, and durable ETag. |
| `GET /api/v3/images` | Operator-admitted merged view of curated and ready managed still images, including when uploads are disabled. Returns `images` rows with `id`, `name`, `width`, `height`, `url`, `thumbnail_url`, and `source`. Reuses existing stores; creates no second content store. |
| `PUT /api/v3/scene` | `SceneInput`. Normalize/validate asset, commit content once, stop an experimental presentation if active, then broadcast static state. Return config. |
| `PUT /api/v3/layout` | Keep the current physical body `{bounds, slots, sizing?}`. Validate and commit through the common replacement function. |
| `PUT /api/v3/logical-layout` | `{width, height, placements, sizing}`. Atomic whole logical draft. Layout kind stays explicit in the response. |
| `POST /api/v3/grid/preview` | `GridCommand`, below. Pure preview with layout, warnings, resolved order, input guards, and base ETag. No writes or sends. |
| `POST /api/v3/grid` | The same command plus its returned input guards. Revalidate, construct, and commit all entries once. |
| `POST /api/v3/layouts/{name}/recall` | Existing physical recall, using the common safety-copy path. |
| `POST /api/v3/logical-layouts/{name}/recall` | Existing logical recall, using the same safety-copy path. |
| `PUT`, `DELETE /api/v3/layouts/{name}` | Existing physical snapshot endpoints, ETag guard, update snapshot digest. |
| `GET /api/v3/logical-layouts` | Include logical entries and invalid entries with validity flags rather than hiding damaged records. |
| `PUT`, `DELETE /api/v3/logical-layouts/{name}` | Logical snapshot parity with physical mode. Same namespace; reject kind/name collisions without explicit replace. |
| `GET /api/v3/scenes`, `PUT`, `DELETE /api/v3/scenes/{name}` | V3 wrappers for existing scene snapshots with ETag guards and digest readback. |
| `POST /api/v3/scenes/{name}/recall` | Validate saved image availability and fit, then use the same static-scene commit function. |
| `PATCH /api/v3/devices/{id}` | `{label: String | null}`. Durable metadata, no layout or content changes. |
| `GET /api/v3/devices/{id}/impact` | `{etag, online, active_entry, saved_layouts, has_measurement_history}`. Read-only impact preview for Forget. |
| `POST /api/v3/devices/{id}/identify` | `{duration_ms?: Int}`. Transient command, capability and connection check. |
| `POST /api/v3/devices/{id}/retry-image` | Resend current static state to this connection, issuing a new render token. No wall revision. |
| `POST /api/v3/devices/{id}/reconnect` | Close the owned socket normally. The existing client reconnects with its current identity. No credential or roster reset. |
| `POST /api/v3/devices/{id}/rebind/preview` | `RebindCommand`, below. Read-only impact/conflict preview. |
| `POST /api/v3/devices/{id}/rebind` | Exact previewed selection and guards. One transaction for roster, histories, active layout, and selected saved layouts. |
| `DELETE /api/v3/devices/{id}` | Body `{remove_active: Bool, saved_layouts: "keep"}`, guarded by the impact ETag. Refuse a present active entry unless removal is acknowledged. Offline-only Forget never deletes measurement history or saved layouts implicitly. |
| `GET /diagnostics`, `GET /healthz` | Operator-admitted reads independent of upload mode. Healthz returns only readiness, schema, generation/revision, and counts. |

All newly introduced request models forbid unknown keys. Missing ETag is 428; stale ETag or preview guards are 412; invalid fields/assets/revision references are 422; absent entities are 404; valid requests with live conflicts are 409. Errors retain FastAPI's `detail` key. Structured conflicts use `detail: {code, message, conflicts}`. The client handles existing string details too. A failed durable write is a 5xx, with no successful notification or partial memory update.

Asset scans/decode metadata can await before mutation. Recheck the ETag and all live guards after that await, immediately before the synchronous transaction. No await occurs between the last checks, transaction, and memory publication. Build proposals first; persist every participating row; let the outer transaction commit; then apply live dictionaries; then abort playback/close sockets/broadcast. A notification failure cannot undo an already committed operation. Reconnection reads the committed state.

`device_changes()` currently restores memory on outer transaction failure. Preserve this guarantee during extraction. Do not publish a new render expectation, close the old identity's socket, or notify a controller while a combined transaction can still fail.

Required service signatures are deliberately small:

```text
MutationResult = OperatorConfig & {previous_layout_saved: String | null}
operator_config_payload() -> OperatorConfig
durable_config_etag(config: OperatorConfig) -> String
async resolve_scene(input: SceneInput) -> Scene
replace_layout(layout: Layout, expected_etag: String) -> MutationResult
build_grid(command: GridCommand, inputs: GridInputs) -> GridPreview
plan_rebind(command: RebindCommand, inputs: RebindInputs) -> RebindPlan
apply_rebind(plan: RebindPlan, expected_etag: String) -> MutationResult
render_mapping(device_id: UUID4) -> MappingResult
accept_render_ack(device_id: UUID4, socket: WebSocket, ack: RenderAck) -> Bool
operator_device_status(device_id: UUID4, now_mono: Finite) -> DeviceStatus
```

No helper imports `main`. The composition root injects the existing commit and post-commit notification callbacks into route factories. Helpers use the existing `state`, `persist`, `displays`, and geometry modules without copying live globals. Keep `main` re-exports used by current tests; do not create a second state object to make extraction convenient. `render_status.py` depends on protocol/data types and passed connection/mapping inputs, not on `state.py`, because state projection also reads render status.

Route-module exports have these signatures. Callback aliases have the corresponding service signatures above; `notify` is the existing async notification adapter. The lifecycle transaction callback belongs to the backend integration owner.

```text
routes.wall.create_router(*, config_payload: ConfigReader,
  require_etag: ETagGuard, commit_scene: SceneCommit,
  replace_layout: LayoutCommit, notify: AsyncNotify) -> APIRouter
routes.grid.create_router(*, get_inputs: GridInputReader,
  require_etag: ETagGuard, replace_layout: LayoutCommit,
  config_payload: ConfigReader, notify: AsyncNotify) -> APIRouter
routes.device_actions.create_router(*, get_inputs: LifecycleInputReader,
  require_etag: ETagGuard, commit_lifecycle: LifecycleCommit,
  config_payload: ConfigReader, send_command: DeviceCommandSender,
  notify: AsyncNotify) -> APIRouter
```

## Render acknowledgement and operator truth

Negotiate additive caps `render_ack`, `identify`, and `image_contain` on protocol 3. Keep `image` as the basic image capability. V1/v2 and cached v3 clients without the new caps remain compatible but render status is `unknown` or `unsupported`, never confirmed by socket presence. Existing playback readiness and its integer `mapping_revision` remain a separate contract.

For every static device instruction, include and retain this token:

```text
RenderToken = {
  connection_id: String, generation: String, revision: NonnegativeInt,
  render_seq: PositiveInt, mapping_revision: String, asset: AssetID | null
}
Viewport = {
  width: PositiveFinite, height: PositiveFinite, dpr: PositiveFinite,
  orientation: 0 | 90 | 180 | 270, mode: "tab" | "fullscreen" | "standalone",
  visual_scale: PositiveFinite
}
RenderAck = {
  type: "render_ack", token: RenderToken, report_seq: PositiveInt,
  status: "loading" | "displayed" | "failed" | "hidden" | "blocked" |
          "unplaced" | "unsupported",
  reason: null | "fetch" | "decode" | "size" | "surface" | "transform" |
          "calibration" | "viewport" | "zoom" | "no_slot" | "capability" |
          "auth" | "playback",
  viewport: Viewport, visible: Bool
}
```

`connection_id` is the server's existing per-socket UUID and must appear in the v3 welcome. It is an identity fence, not a secret or device credential. Device render frames carry `token: RenderToken` alongside their existing top-level generation/revision/render-sequence fields. Those duplicate fields must agree. `mapping_revision` is an opaque static-mapping digest of the layout kind, placement/slot and bounds, pinned measurement revisions, effective calibration values, validated viewport, and supported content interpretation. It changes when the effective viewport changes even if wall revision and pinned calibration number do not. `render_seq` advances for every issued static instruction and retry, including logical v3 instructions. Preserve `type: render` for those instructions. Legacy v2 receives its existing `wall` shape.

Keep expected token, latest accepted report, report sequence, and receipt monotonic time in a bounded process-local map keyed by device. Clear it on startup, disconnect, replacement, Forget, and rebind. Never persist it in roster metadata. A writer enqueue establishes the latest expectation and invalidates previous evidence. If the writer coalesces or drops intermediate plans, their acknowledgements cannot confirm the latest plan. A failed send closes/removes the owned connection through the current hub behavior.

Acceptance requires all of the following:

1. The sending socket still owns `device_sockets[id]`, and its connection ID matches the token.
2. The full token matches the latest expected token, including the exact asset or null. The generation and wall revision must still be current.
3. `report_seq` is strictly increasing for the connection. Reject booleans, nonfinite values, oversized strings, and unknown enums. Bound the serialized report to 4096 bytes before parsing its fields.
4. A displayed image has a ready mapping, image capability, positive canvas surface, matching validated viewport, `visible: true`, and no active experimental presentation. Client-only zoom/visibility guards can make a report less healthy. They cannot override a server mapping fence.

The client reports loading when it accepts an instruction, failure on exhausted fetch/decode or drawing failure, and displayed only after `drawImage` completes and a subsequent animation-frame callback still owns that token. A decoded cache entry alone is not displayed. Capture the token in every async callback and discard it if the socket, generation, mapping, scene, or render sequence changed. On reconnection, accept and repaint the new token even at the same wall revision. Cached pixels can be reused; old evidence cannot.

Send a report on status transitions and refresh the latest report at the existing five-second heartbeat cadence. `report_seq` increases on each refresh. Hidden pages report hidden when possible and require a fresh paint after becoming visible. A page that freezes without a final report expires by server receipt time. Receipt age uses monotonic time; optional client timestamps never decide freshness. No evidence older than `HEARTBEAT_TIMEOUT_S`, currently 15 seconds, counts as current. This is a bounded report of application activity, not proof that the OS screen is lit.

`RenderStatus` includes expected token, last accepted status/token, `received_at`, computed `age_ms`, and a derived status. The UI distinguishes offline, unsupported, unplaced, blocked, loading, failed, hidden, stale, unknown, identifying, and current displayed. The aggregate denominator includes expected participating placed devices, including offline reservations. Only current matching image acknowledgements contribute to "N of M showing". An active Identify overlay or playback presentation suppresses that contribution. Zero participants means "No tablets on the wall". An unsupported image-capability chip can never become an image-presented chip.

Retry image issues a fresh token and clears the latest expectation's green state while retaining its prior pixels as historical content during loading. It retries the same content-addressed URL without changing scene or layout. Reconnect keeps UUID/label/number. Registration 401 stops the silent backoff path and offers the supported sign-in route. Resume handling on `visibilitychange`, `pageshow`, and `online` probes registration/socket ownership and resends viewport. Preserve 4409 takeover behavior so an obsolete tab cannot steal the identity back in a loop.

## Atomic grid command and orientation

The four-device default is rows 2, columns 2. "1 x 4" always means one row and four columns. "4 x 1" means four rows and one column. The primary presets are 2 x 2 and 1 x 4. Custom dimensions use the same explicit row/column semantics.

```text
GridCommand = {
  kind: "logical" | "physical", device_ids: UUID4[],
  rows: PositiveInt, columns: PositiveInt,
  gap: NonnegativeFinite, padding: NonnegativeFinite,
  sizing: "tablets" | "fixed",
  orientation: "preserve" | "auto" | "portrait" | "landscape",
  mount_angles?: Map<UUID4, 0 | 90 | 180 | 270>,
  logical_sizes?: Map<UUID4, {w: PositiveInt, h: PositiveInt}>,
  physical_revisions?: Map<UUID4, {profile_revision: PositiveInt,
                                calibration_revision: PositiveInt}>,
  allow_empty_cells: Bool, release_unselected: UUID4[],
  guards?: Map<UUID4, {connection_id: String | null,
                      viewport: Viewport | null}>
}
GridPreview = {
  layout: Layout, order: UUID4[], warnings: String[],
  guards: Map<UUID4, ConnectionViewportGuard>, base_etag: String,
  reservations_removed: UUID4[], previous_kind: "logical" | "physical"
}
```

The submitted array is the sole order of record, laid out left-to-right and top-to-bottom. Reject duplicate/unknown IDs, empty selection, excess capacity, nonintegral logical sizes/gap/padding, and insufficient rows/columns. Require exactly `rows * columns` devices unless `allow_empty_cells` explicitly acknowledges trailing holes. The UI initially sorts by valid display number, then normalized human label, then UUID. It exposes Move earlier/later controls. The server must not resort the submitted selection by UUID or by a number lease that changed after preview.

Logical commands reject `physical_revisions` and `mount_angles`. Physical commands reject `logical_sizes`. Entry maps may only name selected devices. Preview returns complete guards; Apply requires those guards even if the preview request omitted them. A guard mismatch is 412, never an instruction to recompute silently from newer telemetry.

This command replaces the active arrangement. IDs in the current arrangement but absent from `device_ids` must appear exactly in `release_unselected`; otherwise return 409 with the reservations that would be lost. Include selected offline reservations with explicit stored sizes/revisions and preserved orientation. Auto-orientation of an offline tablet is refused. Preview explains every excluded tablet. An empty physical draft cannot replace a populated logical wall through an accidental default Apply. Clear wall is a separate explicitly confirmed empty-layout operation.

For logical mode, preserve an existing footprint where available. New sizes come from the explicit `logical_sizes` in the draft, initially suggested by live viewport aspect in logical units. The UI shows those sizes before Apply. No CSS-to-mm factor enters this path. Bezel edges retain their logical units. Logical placement has no mount rotation, so orientation presets choose an aspect/size; a real browser orientation mismatch remains visible and requires the operator to rotate the device or choose a new size.

For physical mode, require explicit pinned profile/calibration revisions from the preview. Dimensions use measured bodies, including bezels. Pack bodies with `gap` as extra space between bodies. Gap zero already includes both adjacent bezels between active panels; never add those bezels again. Preserve nudges and compute centers so the effective nudged body is packed correctly, matching `PhysicalSizing.packSlots`. New slots use zero nudges. Participation is retained for existing slots and defaults true for new slots.

Keep browser orientation, calibration quarter turn, and wall mount angle distinct. For `preserve`, retain the existing mount or use an explicit per-device angle for a new slot. For `auto`, require a fresh viewport and a confirmed model or explicit mounting information. For the existing model convention, compute `quarter = ((portrait_angle - viewport.orientation) / 90) mod 4`, then the upright native-panel mount is `(360 - 90 * quarter) mod 360`. Confirm this against the four-corner fixtures for both model portrait angles; raw browser angle alone is insufficient. Manual calibrations do not imply a measured wall mount. Require their angle explicitly. Portrait/landscape chooses the requested body aspect, retains the current angle if already compatible, otherwise uses the compatible upright auto angle or requires a 90/270 choice. Per-device `mount_angles` overrides that choice and stays visible in preview.

Use the existing row-packing rule, not fixed wall cells. For each row, accumulate item widths plus gap; use the maximum body height for that row; place rows consecutively. Fit bounds to those bodies plus padding when `sizing: tablets`. For fixed sizing, use the active same-kind bounds and warn about clipped/outside areas. Do not borrow logical bounds for a new physical layout. Mixed body sizes can leave holes and uneven edges, even with zero extra gap. Preview those holes honestly. Only equal aspect-matched bodies in a complete grid can promise full rectangular coverage.

The preview and commit call the same Python `build_grid` helper. The client draws the returned layout. Commit rechecks durable ETag and the preview's connection/viewport guards, then writes one layout with one revision increment and one broadcast. No per-tablet placement loop. Scene, assets, histories, and labels remain unchanged. Cancelled preview changes nothing. A failure at any input or persistence step leaves the entire old arrangement intact.

## Labels, Identify, Remove, and Forget

Persist optional `label` on the durable roster record, independently of model profile `label` and leased display number. Normalize outer whitespace, cap at 80 Unicode characters, and reject control characters. Empty input clears the label to null. Duplicate names are allowed. Render through text nodes, including the tablet overlay. Older roster documents may omit `label`; both the loader and required-field validator must treat it as optional. Registration preserves a name and cannot overwrite it. Restart/reconnect preserves it. The existing display-number lease policy remains unchanged; do not market `#N` as a permanent installation ID.

Identify is a transient socket command, never a saved scene. Use a distinct DOM overlay above the existing canvas/HUD. The command carries `command_id`, target `connection_id`, server send time, deadline, duration, label, and current number. Default duration is 5000 ms, bounded between 1000 and 10000 ms. The ordered writer stamps remaining duration from a server monotonic expiry. The client uses the existing server clock/bootstrap estimate where available to discard an expired delayed command, caps its local monotonic timer by the remaining duration, and never extends expiry on redraw. Identify does not require optical clock quality.

```text
IdentifyFrame = {
  type: "identify", command_id: String, connection_id: String, generation: String,
  server_ms: Finite, expires_ms: Finite, duration_ms: PositiveInt,
  remaining_ms: NonnegativeFinite, label: String | null, number: PositiveInt | null
}
IdentifyStatusFrame = {
  type: "identify_status", command_id: String, connection_id: String,
  status: "shown" | "cleared"
}
```

`server_ms` and `expires_ms` use the existing server clock epoch, not the tablet wall clock. Reject mismatched connection/generation and expired commands. Late status from an obsolete command cannot replace the status of the newer command.

A newer Identify replaces the older overlay. A new scene updates behind it. Dismiss on expiry, disconnect, pagehide, takeover, or changed connection. Reconnect never replays it. On resume, clear an expired overlay before drawing. Expiry reveals the latest scene, not the scene captured when Identify started. A client may acknowledge `identify_status` with command/connection IDs and shown/cleared status; queued/delivered alone is not shown. The operator sees identifying or unknown delivery rather than inferring the base image is unobstructed. The base scene revision and active image never change.

Remove from wall changes only the active tagged arrangement. Saved layouts and roster remain. Offline placements are reservations, so they have the same Remove action. Forget removes the offline roster entry, releases its number/label, and removes its active entry in the same transaction if explicitly confirmed by the impact preview. Return the saved-layout names that still reference the old UUID. Keep those snapshots and measurement history intact as visible reservations; hiding them would make Forget appear to erase history while recall resurrects it. The impact confirmation explicitly says that saved reservations remain and that reopening the old browser can register again. Forget is not revocation. Do not silently delete profiles/calibrations because old snapshots pin them.

Forget requires the owned socket to be absent, not merely an old heartbeat. The normal sweeper can close a stale socket before the operator retries. The tablet roster view uses durable roster entries and explicitly labelled active/saved reservations. Historical measurement records alone must not recreate a forgotten tablet card, as the current `physical.js` union of profile IDs can do. Measurement history stays reachable in advanced details.

The current `DELETE /devices/{id}` actually closes an online socket; contrary to a recommendation in the DeepSeek report, there is no current offline-only protection to "keep". The new v3 Forget contract deliberately adds that protection. The compatibility wrapper must adopt it explicitly, with updated tests, rather than accidentally retaining two lifecycle meanings.

## Rebind and saved-layout migration

Keep browser UUID keys for this delivery. A replacement request declares whether this is the same hardware with a new browser identity. Do not copy measurements from a different physical tablet on a model-name guess.

```text
RebindCommand = {
  replaces: UUID4, hardware: "same_hardware" | "different_hardware",
  active: Bool, saved_layouts: {name: String, etag: String}[],
  number?: PositiveInt, transfer_label: Bool
}
RebindPreview = {
  base_etag: String, old_id: UUID4, new_id: UUID4,
  affected_active: Bool, affected_saved: SnapshotSummary[],
  untouched_saved: SnapshotSummary[], conflicts: Conflict[],
  profile_revision_map: Map<Int, Int>, calibration_revision_map: Map<Int, Int>,
  label_after: String | null, number_after: PositiveInt | null,
  old_offline: Bool, new_connection_id: String | null
}
RebindApply = RebindCommand & {new_connection_id: String | null}
```

The UI selects all valid saved arrangements that reference the old UUID by default, displays the exact list, and lets the operator choose. No server-side implicit "all" that can gain more snapshots between preview and apply. The global ETag plus each selected snapshot digest guards saved contents. Apply sends `RebindApply` with the preview's target connection ID, which must still match, including null for offline. Recheck the old socket is absent, the new identity exists, the requested number is free, and the target is not already present in the active or any selected saved arrangement. A stale open old socket counts as a conflict until it is closed; a heartbeat timeout alone must not let it revive halfway through handover.

For `same_hardware`, gather every referenced profile/calibration pair from the active and selected saved physical layouts, not only the current assignment. Verify the references exist and agree. Use `displays.copy_records` with explicit append offsets only when the target's existing records are the known automatically created model records. Otherwise report target-history conflict and require an explicit separate measurement decision. Return exact old-to-new revision maps and use them for every rewritten slot. Copy the associated model-history snapshots with `tablet_models.copy_assignment`; never substitute today's built-in model for a historical snapshot. Original measurement records remain unchanged.

For `different_hardware`, preserve logical placements if explicitly selected. A physical active or selected saved layout requires a separate draft with the new tablet's own profile, calibration, body fit, and mount. The immediate rebind endpoint returns 409 with those physical arrangements listed. This is a deliberate supported refusal, not partial migration. The operator can omit them and rebuild physical drafts separately. No copied scale can claim to validate replacement hardware.

Rewriting a logical entry changes its map key and embedded `device_id` only. Rewriting a physical slot changes its key and mapped revision references only. Preserve bounds, sizing, positions, nudges, angle, participation, and scene bytes. Reject a selected damaged snapshot or missing revision before writing. Leave unselected snapshots untouched and report their remaining reservations.

Use one `persist.transaction()` for copied histories/model metadata, selected `save_layout(..., replace=True)` writes, roster transfer, and active wall state if changed. Build detached proposals before the transaction and publish memory only after the outer commit. A failure on the last saved layout or roster write must roll back the first copied profile too. Increment the wall revision once if the active arrangement changed; otherwise change the durable ETag through labels/snapshot/history digests without inventing a visual revision. Notify once and clear old/new render evidence after success. Close/reconnect the new socket only after commit if its number/welcome metadata changed.

The legacy `/devices/{id}/rebind` can delegate to this engine with its documented active-only selection and report outstanding saved references. New UI uses only the v3 preview/apply pair. It must not silently claim saved layouts were healed after calling the legacy endpoint.

## Safe switching and backup atomicity

Every active layout replacement passes through one helper, including direct Apply, grid, both recall directions, and old recall wrappers. If the layout kind changes, save the complete previous normalized layout under a unique `Before logical <hex>` or `Before physical <hex>` name before replacing it. Use the existing 64-character snapshot-name rules and collision refusal. The saved name describes the target switch. Return `previous_layout_saved` with the actual name. Preserve the previous layout's units, sizing, reservations, and pinned revisions.

The safety copy and new wall row commit in one SQLite transaction. A backup name collision, snapshot write failure, or wall write failure leaves old disk state, live state, revision, and notifications untouched. Retrying with an old If-Match returns 412 rather than creating another switch. A crash after commit but before notification recovers the new layout and safety copy on restart. Both physical Apply and physical recall over logical require this copy; both logical Apply and logical recall over physical require it too.

A same-kind Apply retains ordinary draft undo behavior. A same-kind recall can offer saving the current arrangement, but must not pretend browser-local undo survives restart. For cross-kind recall the automatic return point is mandatory even if a similarly named saved layout already exists. Scene selection and layout recall remain independent; switches do not start a playlist or replace the image.

This SQLite safety copy is not an off-host backup. Retain [deploy/backup.py](../../deploy/backup.py)'s verified content closure, staged publication, and refusal to overwrite restore targets. Verify that label metadata, normalized scene defaults, contain/background, model histories, and rewritten snapshots survive backup/verify/restore to fresh temporary paths. Unreferenced library files remain outside its recovery scope. No daemon, backup schedule, live restore, or network deployment is introduced by these contracts.

## One contain/cover contract

User-facing Fill maps to `cover`; Fit whole image maps to `contain`. Defaults stay cover. Fit is global to the wall, independent of tablet count. For source `(Iw, Ih)` and wall bounds `(x, y, W, H)`, use these definitions in static clients, plans, and preview:

```text
scale = max(W / Iw, H / Ih) for cover
scale = min(W / Iw, H / Ih) for contain
draw_width = Iw * scale
draw_height = Ih * scale
draw_x = x + (W - draw_width) / 2
draw_y = y + (H - draw_height) / 2
```

Background is an opaque normalized `#rrggbb`. Fill the current output surface before drawing, including alpha and contain margins, so old pixels cannot leak through. Preserve source orientation normalization and the server-derived upright dimensions. Never stretch or fit the source independently inside each tablet.

The implementation must change all relevant callers together:

- Scene validation, normalized persistence, projected scene, saved-scene recall, and `SUPPORTED_FITS` accept both values. Non-image variants reject fit/background/asset fields.
- Logical static drawing uses the chosen global scale. Retain the existing mapping of a logical active rectangle to its viewport for compatibility, but flag aspect mismatch. Under mismatch, that legacy per-viewport clipping means the preview cannot promise every source edge appears on glass. Grid generation should choose matching footprints instead of concealing the issue.
- Physical static plans pass fit into `normalized_source_to_panel`, use the scene background, and clip to the calibrated active panel. The existing transform functions remain authoritative.
- `_physical_plan_for` takes explicit fit instead of hardcoding cover. `_send_prepare` carries the matching fit and background in the prepared image descriptor. Existing playlist image items retain explicit cover and `#0b1120` defaults. `preparedContent` reads those descriptor values and must not replace a supplied contain value with cover. A playlist item must not inherit whichever static scene happens to be active. Adding playlist fit controls is deferred; if image-item fit/background are later accepted, validation, persistence, preparation, and still-commit decoding must pass them unchanged. Video items keep their existing cover behavior. No playback timing or video feature expansion belongs here.
- The stage uses the same wall transform and exact pinned panel/body geometry. Logical preview shows the logical active rectangle after its bezels. Physical preview shows active panels and the assumed viewport inset. Dim the source outside bounds; distinguish off-wall crop, contain margins, bezels, holes, and draft changes. Preview never invents physical accuracy for units.

Add `image_contain` capability so a cached client that only implements cover cannot silently misrender contain. For an unsupported placed device, withhold the incompatible image instruction, show an explicit upgrade/unsupported reason, and exclude it from confirmed coverage. Preserve the existing safe v2 fallback envelope for physical tablets. Never send that envelope as operator truth. A newly connected legacy controller on a physical wall receives an explicit upgrade refusal/4426; it cannot reconnect indefinitely to a plausible neutral wall. Legacy `PUT /scene` stays a logical response contract only while logical mode is active and returns the existing upgrade conflict in physical mode. The new console uses `PUT /api/v3/scene` everywhere.

For a 400 x 100 wall and a 100 x 100 source, contain places a 100 x 100 image at x=150; cover places a 400 x 400 image at y=-150. These are deterministic geometry test cases. A physical panel behind a bezel can still hide source pixels under contain. "Whole image inside wall bounds" does not mean "every pixel visible through panels". Source-pixel/upscale estimates are arithmetic warnings, not measured sharpness claims.

## Auth, diagnostics, and deployment compatibility

The supported HTTP hotspot remains a trusted-network supervised trial, with uploads disabled and operator access on direct loopback. No shared-token cookie is required there. New state/device/grid/scene endpoints stay off the tablet allowlist. Asset bytes, registration, and device sockets retain their current narrow access. New client scripts require exact allowlist entries if extracted; do not replace the list with a directory wildcard.

Keep shared-secret auth, same-origin cookie checks, and the independent operator-origin guard. New routes must not bypass either. Operator config reports whether uploads are enabled, which fits/commands the clients can negotiate, and whether a login path is supported. It returns no token, proxy credential, private key, or local secret path.

Diagnostics use `admit_operator_read(request)` independently of `upload_mode()`. Reuse the current library admission proofs. Direct mode requires a real loopback transport peer and no forwarded headers. If the configured operator proxy credential is present in deployment, require exactly one constant-time-matched credential header, with no fallback to "proxy is loopback". Reject duplicate or invalid headers. Keep app auth outside this helper. The hotspot direct backend therefore admits diagnostics while uploads remain disabled. The tablet Caddy listener continues to deny diagnostics, healthz, config, and all operator commands even with a forged credential. Heavy integrity verification remains an explicit operator action.

If app auth is enabled, the tablet ingress must serve the exact `GET` and `POST /auth/login` path needed for a same-origin login, with existing origin checks and bounded form handling. This makes expired sessions actionable. It does not make a 12-hour shared operator cookie a durable tablet credential. The two-origin reference proxy strips cookies/Authorization on its operator upstream; do not claim that configuration composes with app shared-secret auth without a complete integration test. A supported authenticated profile must declare the tested single-origin or explicitly tested two-origin combination. The HTTP launcher keeps refusing auth rather than weakening its contract.

Durable per-device credentials, approval, and revocation are a separate security workstream. They must not be approximated by treating labels, UUIDs, render connection IDs, or a longer shared cookie as authorization. Until that work is explicitly implemented and tested, the UI and runbook retain trusted-hotspot/session-expiry limits. A 401 shows authentication required and a supported sign-in action; a forbidden login route shows an operator deployment error instead of an endless retry.

No API powers on, unlocks, wakes, or forces fullscreen on a tablet. Keep existing best-effort wake lock, manual fullscreen gestures, and OS kiosk instructions. Preserve one server process, current worker ownership, immutable assets, media bounds, and queue limits. Video and playlists stay experimental in the consolidated console.

## File ownership and implementation dependencies

This is a proposed allocation for the coordinator's existing workers, not permission to spawn more agents. Use only the user-requested DeepSeek and Sol models. Each implementer works in its assigned isolated checkout and must not revert another worker's edits. If an existing assignment already owns a listed file, that owner keeps it; coordinate a handoff before applying this allocation.

Only the backend integration owner edits `main.py`. It also owns changes to the shared state, persistence whitelist, protocol caps, socket dispatch, and the existing Python test files that monkeypatch `main`. Other backend workers return helpers and route factories; they do not paste handlers into `main.py`. Each new helper and test below has exactly one writer.

| Owner | Exclusive files and responsibility | Dependency |
| --- | --- | --- |
| Backend integration | `main.py`, `tabletwall/state.py`, `tabletwall/hub.py`, `tabletwall/persist.py`, `tabletwall/protocol.py`, `tabletwall/displays.py`, `tabletwall/tablet_models.py`; new `tabletwall/operator_state.py`, `tabletwall/scene.py`, `tabletwall/routes/wall.py`; existing `tests/test_v3.py`, `tests/test_wall.py`, `tests/test_snapshots.py`, `tests/test_field.py`, `tests/test_roster_persistence.py`, `tests/test_commit_boundary.py`, `tests/test_tablet_models.py`, `tests/test_geometry.py`, `tests/test_wall_sizing.py`, `tests/test_displays.py`; new `tests/test_operator_state.py`. Own accurate projection, durable ETag, scene normalization, common replacement/transaction boundary, compatibility wrappers, final route wiring and socket hooks. | Starts first. Publish helper signatures and the existing test re-export hooks before others integrate. |
| Grid backend | New `tabletwall/grid.py`, `tabletwall/routes/grid.py`, `tests/test_grid.py`. Own pure ordered logical/physical construction, preview guards, and route factory. Use existing sizing/geometry reads. No edits to `main.py`, `sizing.py`, or frontend files. | Depends on common layout/commit and config contracts. Can build pure helper/tests from this document immediately. |
| Identity backend | New `tabletwall/device_lifecycle.py`, `tabletwall/routes/device_actions.py`, `tests/test_device_lifecycle.py`. Own impact previews, selected snapshot migration plans, labels/Forget/rebind/Identify route factory. Core owner applies any needed whitelist/history helper adjustments in shared modules. | Depends on durable ETag and transaction adapter. Can build pure migration/conflict tests immediately. |
| Evidence backend | New `tabletwall/render_status.py`, `tests/test_render_status.py`. Own bounded expected-token and acknowledgement validation, status derivation, and reset operations. Core owner wires `state.py`, `hub.py`, and `main.py`. | Token and mapping contract precedes client hook integration. Can test acceptance and stale/replaced sockets independently. |
| Tablet client | `frontend/client/client.js`, `frontend/client/view.js`, `frontend/client/index.html`, `frontend/client/client.css`; `tests/client_image.test.js`, `tests/client_view.test.js`, `tests/client_wake_lock.test.js`; new `tests/client_render_status.test.js`, `tests/client_identify.test.js`. Own fit/background, current-token draw evidence, Identify overlay, resume/auth recovery, and additive caps. | Can use synthetic protocol fixtures now. Needs server token/command wiring for end-to-end verification. |
| Unified operator UI | `frontend/controller/physical.js`, `frontend/controller/physical.html`, `frontend/controller/physical-stage.js`, `frontend/controller/physical.css`, `frontend/controller/physical-sizing.js`, `frontend/controller/controller.js`, `frontend/controller/index.html`, `frontend/controller/controller-inventory.js`, `frontend/controller/controller-stage.js`, `frontend/controller/controller-geometry.js`; new `frontend/controller/operator-state.js`, `frontend/controller/operator-content.js`, `frontend/controller/operator-grid.js`; new `tests/operator_state.test.js`, `tests/operator_grid.test.js`. Own one console, tagged stage adapters, still-image library, draft conflicts, status, lifecycle forms, and legacy entry guard. Do not rewrite the stylesheet system or experimental playback engine. | API fixture contract first. Wait for any already-owned capability fix in `controller.js` before taking the legacy entry changes. |
| Access and operations | `tabletwall/auth.py`, `tabletwall/media.py`, `tabletwall/routes/diagnostics.py`; new `tabletwall/operator_access.py`; `deploy/tablet-routes.caddy`, `deploy/hotspot.py`, `deploy/backup.py`; existing `tests/test_auth.py`, `tests/test_ingress.py`, `tests/test_hotspot.py`, `tests/test_backup_media.py`; new `tests/test_operator_access.py`. Own independent read admission, login compatibility, client allowlist changes, backup round-trip verification. No live deployment execution. | Diagnostics/admission checks are independent. Return required changes to old diagnostic cases in `test_field.py` to its backend integration owner. |

Do not create a generic dependency-injection framework. Route factories accept narrow callbacks such as `config_payload`, `require_etag`, `replace_layout`, and post-commit notification. Identity receives one synchronous transaction adapter rather than inventing its own wall copy. Existing FastAPI decorators are removed from `main.py` only when their replacements are wired, preserving endpoint paths and app/test ownership.

The integration sequence has verifiable units:

1. Land accurate state/scene projection, ETag rules, and compatibility fences. Verify physical image A/B readback and logical readback with isolated TestClient.
2. Integrate grid, lifecycle, and evidence helpers in parallel by their file owners. Verify one revision per layout operation, stale/refused commands, and rollback after late writes fail.
3. Connect tablet caps, fit/background, and evidence hooks. Verify actual draw/failure/resume events against current tokens in isolated browser clients.
4. Connect the shared operator UI and tagged stage adapters. Verify 2x2/1x4 drafts, image changes, Identify expiry, replacement-safe recall, and current status at desktop and narrow mobile widths.
5. Integrate access/diagnostics and backup compatibility. Verify denied tablet paths, uploads-disabled operator diagnostics, actionable 401, and restore into new paths.
6. Run the focused integration matrix below. Record browser artifacts and failures. Real-tablet and unattended-operation acceptance remain separate open gates.

The throughput checkpoint is a working physical still-image read/change/status path after steps 1 and 3. If helpers grow into a new backend service or layout migration before that path works, reduce the scope back to A. No framework rewrite or additional mode should delay this checkpoint.

The companion UX document currently uses `painted`/`calblocked` for UI states and says hotspot diagnostics are unavailable. At integration, map those display labels to the `displayed`/`blocked` wire enums here and update the hotspot copy after independent diagnostics admission passes. This document does not edit that owner's file. Mount inference in the grid is a visible draft suggestion requiring operator review, not a claim that browser orientation measured the installed mount.

## Verification and evidence

The supplied 1177-test baseline is historical and was not rerun for this document. Existing tests are useful evidence of the foundations; they do not test the proposed endpoints or prove hardware behavior.

The design author executed this focused baseline with the repository fixtures that set temporary database, asset, and media paths:

```bash
rtk proxy env PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q -p no:cacheprovider tests/test_v3.py tests/test_geometry.py tests/test_displays.py tests/test_wall_sizing.py tests/test_roster_persistence.py tests/test_commit_boundary.py --junitxml=/tmp/tablet-wall-architecture-20261101-contract-baseline.xml
rtk proxy node tests/client_view.test.js
rtk proxy node tests/client_image.test.js
rtk proxy node tests/physical_sizing.test.js
```

Observed results were 74 Python tests passed with one existing AnyIO/Starlette deprecation warning; 12 client-view cases passed; 74 client-image cases passed; and "Physical sizing geometry passed". The Python artifact is [contract-baseline.xml](/tmp/tablet-wall-architecture-20261101-contract-baseline.xml). The Node image suite includes existing mocked video cases; passing those adds no hardware/video evidence. No server, browser, live wall, hotspot, or firewall was started by the design author.

Document checks resolve every source/report/artifact link, check balanced code fences, check the required contract sections, and inspect whitespace in the complete new file. Their machine-readable result is [document-check.json](/tmp/tablet-wall-architecture-20261101-document-check.json). The no-index whitespace command returns 1 for a newly added file even when it has no whitespace diagnostics; the check records diagnostics separately from that expected difference status.

The implementation owners must add and execute these behavioral checks. New filenames below are planned tests, not tests claimed as already present or passing:

| Check | Exact target and required artifact |
| --- | --- |
| State truth | `tests/test_operator_state.py`: physical image A then B, scene/config/socket agreement, logical union, no synthetic operator wall, missing asset remains an image, runtime cannot alter durable ETag, label/snapshot changes do alter it. JUnit output. |
| Atomic grids | `tests/test_grid.py`: 2x2 and 1x4 ordered arrays, logical/physical units, mixed sizes/holes, Pixel C and Air 2 quarter-turn fixtures, stale viewport, offline reservation and explicit release, invalid empty/default apply, one revision/broadcast, failure leaves everything unchanged. JUnit output and returned preview JSON. |
| Evidence | `tests/test_render_status.py`, `tests/client_render_status.test.js`: load/decode/draw transitions, stale callback, old socket, wrong generation/revision/asset/mapping/render sequence, hidden/zoom state, same-revision reconnect, out-of-order report, expired evidence, writer coalescing, and retry after failure. JUnit/Node output plus captured WS frames from isolated integration. |
| Lifecycle | `tests/test_device_lifecycle.py`, `tests/client_identify.test.js`: label persistence/escaping, offline-only Forget in both kinds, all selected snapshots repaired, target collision, model offsets/history, different-hardware refusal, unselected reservations, failure on final write rolls back all earlier writes, Identify expires over a newer scene and does not replay. JUnit/Node output. |
| Safe return | Extend `tests/test_commit_boundary.py` and lifecycle tests for all four cross-kind Apply/recall directions. Force backup insertion and final state save failures. Assert no partial backup, revision, memory, or broadcast. Restore copied database into fresh test paths. JUnit output and backup manifest. |
| Fit agreement | `tests/test_geometry.py`, `tests/client_view.test.js`, `tests/client_image.test.js`: global contain and cover corner fixtures, alpha/background, nonzero/negative physical bounds, asymmetric bezels, rotated panels, logical aspect mismatch, static and prepared still agreement. Store expected transform/corner JSON with the test fixture. |
| Access compatibility | `tests/test_operator_access.py`, `tests/test_auth.py`, `tests/test_ingress.py`: uploads-disabled direct diagnostics, forwarded/remote/forged/duplicate credential rejection, exact login methods, cookie expiry, negative tablet route matrix, and unchanged content-byte authentication. JUnit output. Test proxy behavior only with isolated processes and firewall doubles. |
| Rendered operator journey | Use the project dev command with fresh temporary DB/assets/media and a private browser. Exercise both kinds, image A/B, fit, 2x2/1x4, Identify, fail/retry, stale draft conflict, rebind/recall, and legacy entry at desktop and about 390 px mobile. Save screenshots, console/network failures, protocol traces, exact command/environment, and cleanup result. Inspect keyboard/focus, overflow, long names, and error states. Source inspection alone cannot accept this UI. |

No software check closes physical seam accuracy, real Safari/Android behavior, actual screen sleep/wake, sustained soak, optical timing, or video gates. The real-device checklist in the combined reviews remains proposed validation using the supplied measurements. Report any remaining hardware or authenticated-deployment limitation before calling the wall dependable unattended.
