# Controller rebuild: build plan

Status: plan for execution. Nothing is built yet.
Date: 2026-11-15. Branch `redesign/direction-b` at `0233914`.
Design input: Direction C plus A's on-canvas editing and B's "Next step" card (`docs/redesign/02-directions.md` §5, §7, and the owner decision in the redesign brief). The final visual spec is `docs/redesign/03-visual-spec.md`, with the mockup at `docs/redesign/mockups/final.html`. When this plan was finished, `final.html` existed (18 states in its `STATES` list) and `03-visual-spec.md` did not. Units marked **needs spec** must not start until both exist. Where this plan and the spec disagree on placement or wording, the spec wins. Where they disagree on behaviour or API use, this plan wins, and the disagreement goes back to the owner.
Contract inventory: `docs/frontend-migration/audit/01-controller-audit.md` (state, drafts) and `02-client-interfaces-compat.md` §2 (every route and frame). I re-checked the route list, the controller's call sites and the session rules against source. The line numbers below are from this commit.

This plan replaces the incremental "islands" path in `docs/frontend-migration/PROPOSAL.md` §3–4 with a full rebuild, as the owner asked. That proposal rejected a full rewrite because it would have to reproduce conflicts, uncertain completion, reconnect, calibration, scaling and every arrangement kind in one cut. This plan answers that risk in four ways. The new app runs beside the old one at a new URL. It ports the old pure logic with differential tests against the old files. Every behaviour gets an end-to-end check in a parity matrix (§8). The old controller is deleted only after every matrix row is green.

## 1. Decisions

| # | Decision | Deciding reason |
|---|---|---|
| 1 | Source in `frontend/controller-app/`. The build goes to `frontend/controller/app/` and is committed. The existing `/controller` static mount serves it at `/controller/app/`. | No backend change (`main.py:653-657` already mounts `frontend/controller` with `html=True`). The old console keeps working at `/controller/physical.html` until switch-over. `make run` needs no npm. |
| 2 | Node `26.13.1` pinned in `.nvmrc`, `engines` and `.npmrc engine-strict=true`. npm with a committed `package-lock.json`. All dependencies are added in U01. | Node 26 is installed here. By Node's usual release schedule it became the active LTS line in October 2026 (inferred, confirm at U01). One unit owns the lockfile, so parallel worktrees never conflict on it. |
| 3 | Data layer: the existing `OperatorSession` + `OperatorSync` is ported to a plain TS class. Its snapshot goes into **one** Zustand vanilla store that also holds every draft. zod parses at the boundary. | The session's write rules (one durable command at a time, uncertain latch, read fence, ETag states) are the riskiest behaviour. A port with differential tests keeps them. A query cache would add retries and refetches that break them (§4.6). |
| 4 | Stage: React-rendered SVG. The `viewBox` is in wall units (logical units or mm). Pointer mapping uses `getScreenCTM()`. Ported pure geometry computes everything. | The old stage (`physical-stage.js:18-140`) reads captured DOM IDs and `window.Operator*` globals, so it cannot be wrapped. The geometry it calls is pure and portable. |
| 5 | Tests: Vitest for ported logic, with differential tests that import the old CommonJS modules. Playwright **TypeScript** e2e (`@playwright/test` 1.57.0) against the real FastAPI build with real tablet pages. axe-core. `toHaveScreenshot` at 390, 820 and 1440 px. | The e2e checks import the app's zod schemas for contract checks, and `toHaveScreenshot` exists only in the TS runner. Version 1.57.0 matches `pyproject.toml` `playwright==1.57.0`, so both runners share `~/.cache/ms-playwright`. |
| 6 | The old Python browser drivers are not retargeted. About 2,000 of their lines use raw `locator(`, `get_by_` or `#id` selectors (grep count over `simulator/browser/*.py`). Only 15 lines in 6 drivers go through the `_workspace_shell.py` helpers. Their obligations are rewritten as TS specs listed in the parity matrix. Drivers that use the controller only incidentally are moved to REST calls before switch-over (U33). | Direction C has no modes, rail tabs or roster chips, so selectors like `data-workspace-mode`, `.roster-pick` and `#tablet-back` have no equivalent. |

## 2. Ground truth the app must honour

### 2.1 Serving rules

- **CSP** (`tabletwall/security_headers.py:43-55`): `script-src 'self'`, `style-src 'self' 'unsafe-inline'`, `img-src 'self' blob:`, `font-src 'self'`, `connect-src 'self'` plus the page's own `ws:` origin. Consequences:
	- There is no inline script. The early theme script is `public/theme.js`, loaded with `<script src>`, as `operator-theme.js` is today. It keeps the `localStorage` key `tablet-wall-theme` and the values `system|light|dark` (`operator-theme.js:5`).
	- There are no `data:` URIs. Set Vite `build.assetsInlineLimit: 0`. Self-host the font, which loads from `/controller/app/assets/`.
	- Nothing loads from another origin. There is no CDN and no Google Fonts.
- **Auth** (`tabletwall/auth.py:113`): when `TABLET_WALL_AUTH_TOKEN` is set, an HTML read without a session redirects to `/auth/login?next=…`. Fetch and the WebSocket use the same-origin cookie. The client never puts a bearer token in JS. `config.capabilities.login_supported` reports the mode (`main.py:1866-1870`).
- **Origin and admission** (audit 02 §2 codes O, U, R, B): writes need the exact operator Origin. Uploads need loopback with no forwarded headers, or the proxy credential. The Vite dev proxy must rewrite `Origin` to the backend origin and must not set `X-Forwarded-*`. Acceptance always runs against the FastAPI-served build, never the dev server.
- **Caching**: everything under `/controller` is sent `Cache-Control: no-cache` (`main.py:632-643`). Hashed asset names plus revalidated HTML are enough. The build has **no code splitting**: one JS and one CSS file. An open page therefore never requests a chunk that a later rebuild deleted.

### 2.2 REST calls the controller makes today

Guard column: **E** is the config ETag sent in `If-Match` (428 if absent, 412 if stale), **P** is the playlist ETag, **V** is the playback version, **U** is upload admission (audit 02 §2), and `—` means no precondition. Shapes are in audit 02 §2 "HTTP inventory". Caller lines are in `frontend/controller/`.

| Area | Method and path | Guard | Request → response | Caller today |
|---|---|---|---|---|
| Authority | GET `/api/v3/config` | — | → Config + `ETag` header | `operator-sync.js:17` |
| | GET `/devices` | — | → `{uuid: Device}`. Fallback only when Config has no `runtime.devices` | `operator-sync.js:20` |
| Content | GET `/api/v3/images` | — | → `{images:[{id,name,width,height,url,thumbnail_url,source}]}` | `operator-content.js:482` |
| | PUT `/api/v3/scene` | E | `{content: color \| calibration \| {type:'image',asset,fit:'cover'\|'contain',background?}}` → Config | `operator-content.js:511` |
| | POST `/uploads?name=` | U | Raw bytes, `Content-Type` set to the file type. XHR for progress → 201 `{state:'ready',asset}` | `operator-content.js:571` |
| | POST `/api/v3/test-pattern` | E | `{pattern:'grid'\|'black'}` → asset entry. Does not select a scene | `operator-content.js:650` |
| | POST `/devices/color`, `/devices/{id}/color` | — | `{color}` → delivery counts | `physical.js:2498` |
| Saved content | GET `/api/v3/scenes`; PUT, DELETE `/api/v3/scenes/{name}[?replace=true]`; POST `…/{name}/recall` | E on writes | Recall returns Config and fails 422 if the image is gone | `operator-content.js:510`, `physical.js:2438-2647` |
| Arrangement | PUT `/api/v3/layout` (physical), PUT `/api/v3/logical-layout` | E | Complete layout → Config + `previous_layout_saved` | `physical.js:5`, `:1163` |
| | POST `/api/v3/layout/clear` | E | `{confirm:true}` → Config | `physical.js:2585` |
| | POST `/api/v3/grid/preview`, POST `/api/v3/grid` | E (+ connection and viewport guards on apply) | GridCommand → `{layout,order,warnings,guards,base_etag,…}` / Config | `operator-grid.js:381`, `:420` |
| Saved arrangements | GET `/api/v3/layouts`, `/api/v3/logical-layouts`; PUT, DELETE `…/{name}`; POST `…/{name}/recall` | E on writes | `{layouts:[{name,etag,kind,valid,layout}]}` | `physical.js:6`, `:2233-2384` |
| Tablets | PATCH `/api/v3/devices/{id}` | E | `{label}` (trimmed, at most 80 characters) → Config | `operator-devices.js:65` |
| | POST `/api/v3/devices/{id}/identify`, `/retry-image`, `/reconnect` | E | → Config | `operator-devices.js:65` |
| | GET `/api/v3/devices/{id}/impact`; DELETE `…/placement`; DELETE `/api/v3/devices/{id}` (forget); POST `…/rebind/preview`, `…/rebind` | E (not on impact) | ImpactPreview, ForgetCommand, RebindCommand (audit 02 §2 "Shared shapes") | `operator-devices.js:65` |
| | PUT `/api/v3/tablet-assignments/{id}` | E | `{mode:'auto'\|'explicit'\|'manual',model_id?}` | `operator-devices.js:25`, `physical.js:2816` |
| Measure | PUT `/api/v3/displays/{id}` | E | Profile body → `{display,etag}`. Appends a revision | `operator-measurements.js:534` |
| | PUT `/api/v3/calibrations/{id}` | E | Calibration body with `viewport_guard` → `{calibration,etag}`. 409 on viewport mismatch | `operator-measurements.js:581` |
| | POST `/api/v3/calibration-check` | — (not durable) | Ruler spans → RulerCheckResult. Writes nothing | `operator-measurements.js:261` |
| Server | GET `/operator-config`, `/api/v3/readiness`, `/api/v3/join-qr` (PNG), `/diagnostics[?verify=1]` | — (read admission R) | Join origin, readiness facts, QR, storage and backup facts | `operator-measurements.js:356`, `operator-readiness.js:3`, `physical.js:10` |
| Playback (opt-in) | GET `/media`; GET, PUT `/api/v3/playlist`; GET `/api/v3/playback`; POST `/api/v3/playback/{start,pause,stop,retry,next,previous}` | P on the playlist PUT; V on every playback POST except start | Audit 02 §2 | `physical.js:7-9` |

These do not exist, so do not invent them:
- **No crop parameters.** Crop follows from `fit` (`cover` = Fill, `contain` = Fit) over the whole-wall bounds. `fitTransform` (`operator-state.js:66-74`) returns `cropX` and `cropY` for display only. The scene input accepts only `type`, `asset`, `fit` and `background` (`main.py:330`, saved-content check at `main.py:600-612`).
- **No backup write.** The controller only shows `backup` and `restore_rehearsal` from `/api/v3/readiness` and `/diagnostics`. Backups run from the CLI.
- **No socket commands.** `/ws/controller` only receives events. Every mutation is HTTP.
- **Legacy routes stay out of the new app**, except the two colour routes and `/uploads`. That covers `/wall*`, `/layouts*`, `/scenes*`, `/scene`, `/devices/{id}/placement` and the legacy rebind. `experimental.html` still uses them.

### 2.3 WebSocket `/ws/controller?protocol=3`

The URL is built from `location`, with `wss:` under HTTPS (`operator-sync.js:35-37`). A physical wall refuses protocol below 3 with close code 4426. Frames are JSON objects with `type`:

| Frame | Payload | Handling today (`operator-sync.js:40-66`) |
|---|---|---|
| `snapshot` | `{devices, wall?, config}` | Authoritative. Ingest the Config, clear the roster error |
| `config_updated` | `{revision, generation, etag}` | Invalidation only. If not busy and the ETag differs, mark it `stale`. If a draft is dirty, raise a conflict notice. Then reconcile with GET config |
| `device_online`, `device_updated` | `{device}` | Merge into the roster. Online, offline and removed also bump `connectionVersions[id]` |
| `device_offline` | `{device_id, last_seen}` | Set `online:false`, keep the placement |
| `device_removed` | `{device_id}` | Delete from the roster |
| `device_status` | — | Accepted for compatibility. The server never sends it |
| `playback_status` | PlaybackStatus | Opt-in observation |
| anything else | — | Ignore |

### 2.4 Command and timing rules to keep exactly

| Rule | Source |
|---|---|
| A write is "durable" when it is not GET, not `…/preview`, and not `/api/v3/calibration-check` | `operator-session.js:43` |
| A durable write is refused locally when the config is unsupported, another durable write is in flight, or the uncertain latch is set | `operator-session.js:44-46` |
| A guarded write is refused locally (412) when its ETag is missing or not `current` | `operator-session.js:48` |
| 10 s timeout. A timeout, network error, 5xx, or unreadable 2xx on a durable write sets the **uncertain latch**. Only `refresh()` that adopts a newer config clears it | `operator-session.js:54-81`, `:106-121` |
| A response that races a newer socket adoption reconciles and returns `commandEtag` | `operator-session.js:83-87` |
| Read fence: a read started before a newer event is discarded | `operator-state.js:208-212` |
| An unsupported config (bad `layout.kind` or `operator_state_version`) blocks writes and shows "Update the console" | `operator-session.js:27-30` |
| The socket reconnects after a **fixed 3 s** (not backoff) and reconciles at once on close | `operator-sync.js:75` |
| Reconcile every 15 s while the page is visible, and also on `visibilitychange` to visible and on `online` | `operator-sync.js:81`, `physical.js:3104-3110` |
| A 1 s tick re-evaluates `tabletState` (render evidence expires after 15 s) and re-renders only when the status signature changes | `physical.js:3115-3121`, `operator-state.js:166-178` |
| Playback polls every 1 s only when opted in and visible | `physical.js:11`, `:3122-3123` |
| Upload: XHR, raw body. A 5xx, status 0, or a 2xx without an asset id makes the upload uncertain. The app never shows an upload automatically | `operator-content.js:562-600` |
| Arrangement history holds 80 entries. A drag is one entry. Esc restores the state from before the drag. The drag threshold is 3 px | `physical.js:12-13`, `physical-stage.js:292` |
| Dirty checks stay separate: layout, tablet forms per device and group, content, grid, playlist | `physical.js:504`, audit 01 §2 "Drafts" |

## 3. Where the app lives and how it ships

```text
frontend/controller-app/          source (new)
	.nvmrc  .npmrc  package.json  package-lock.json
	vite.config.ts  tsconfig.json  components.json  playwright.config.ts  eslint.config.js
	index.html  public/theme.js
	src/  main.tsx  App.tsx
		api/       zod schemas per domain + paths.ts + etag.ts
		session/   session.ts sync.ts readFence.ts outcome.ts
		state/     store.ts reconcile.ts unsaved.ts drafts/*.ts commands/<domain>.ts
		domain/    ported pure logic (layout, status, sizing, stagePanels, calibration, measurements, gridCommand, names, nextStep)
		stage/     WallSvg.tsx TabletShape.tsx useStageGesture.ts
		features/  header preview sources/{images,saved,layouts,tests} onwall board tablet measure server playback nextstep conflict
		ui/        shadcn components, restyled to the spec
		styles/    tokens.css app.css
	e2e/       fixtures.ts + *.spec.ts + __screenshots__/
frontend/controller/app/           build output (committed, generated)
frontend/controller/*              old console, unchanged until U34
```

Vite config essentials: `base: '/controller/app/'`, `build.outDir: '../controller/app'`, `emptyOutDir: true` (the directory holds only build output), `assetsInlineLimit: 0`, `modulePreload: { polyfill: false }`, no `manualChunks` and no dynamic `import()`. Plugins are `@vitejs/plugin-react` and `@tailwindcss/vite`. Vitest includes `src/**/*.test.{ts,tsx}` only, so `make test` (`node tests/*.test.js`) and pytest (`tests/`) never collect app files.

Makefile targets to add (U01):

```make
app:       ## Build the new controller into frontend/controller/app
	@cd "$(ROOT)frontend/controller-app" && npm ci && npm run build
app-check: ## Typecheck, unit tests, and prove the committed build is reproducible
	@cd "$(ROOT)frontend/controller-app" && npm ci && npm run typecheck && npm run test && npm run build \
		&& test -z "$$(git status --porcelain -- ../controller/app)"
app-e2e:   ## Build, then run end-to-end tests against the FastAPI-served build
	@cd "$(ROOT)frontend/controller-app" && npm run build && npm run build:e2e && npx playwright test
```

**Committed build rule.** Feature units never commit `frontend/controller/app/`. They build it locally for e2e and then run `git checkout -- frontend/controller/app`. Whoever merges a unit runs `make app`, commits the output in a separate commit titled `build: controller app`, and runs `make app-check`. Hashed file names would otherwise conflict on every merge.

**Switch-over URL.** The app stays at `/controller/app/`. At switch-over (U34), `index.html` and `physical.html` become small pages whose external `redirect.js` runs `location.replace('app/' + location.search + location.hash)`. That keeps old bookmarks working, keeps query and hash (asserted by `operator_accessibility.py:205-218`), and obeys the CSP. A meta refresh would drop the hash.

## 4. Data layer

### 4.1 Data shapes first

```ts
// api/etag.ts: three concurrency tokens that must never mix
type ConfigEtag = string & { readonly __brand: 'ConfigEtag' };
type PlaylistEtag = string & { readonly __brand: 'PlaylistEtag' };
type PlaybackVersion = string & { readonly __brand: 'PlaybackVersion' };

// api/config.ts (loose objects: unknown fields are kept, see 4.2)
type Bezel = { top: number; right: number; bottom: number; left: number };
type Placement = { x: number; y: number; w: number; h: number; bezel: Bezel };
type Slot = { center_x_mm: number; center_y_mm: number; mount_angle: number; nudge_x_mm: number; nudge_y_mm: number;
	profile_revision: number; calibration_revision: number; participating?: boolean };
type Sizing = { mode: 'fixed' | 'tablets'; padding: number };
type LogicalLayout = { kind: 'logical'; width: number; height: number; placements: Record<DeviceId, Placement>; sizing: Sizing };
type PhysicalLayout = { kind: 'physical'; bounds: Rect; slots: Record<DeviceId, Slot>; sizing: Sizing };
type Layout = LogicalLayout | PhysicalLayout;
type SceneInput = { type: 'color' } | { type: 'calibration' }
	| { type: 'image'; asset: AssetId; fit: 'cover' | 'contain'; background?: HexColor };
type Scene = SceneInput & { url?: string; intrinsicWidth?: number; intrinsicHeight?: number; available?: boolean }; // output only
type Device = { device_id: DeviceId; number?: number; label?: string; online: boolean; protocol: number; caps: string[];
	viewport?: Viewport; mapping?: Mapping; render?: RenderEvidence; identify?: IdentifyState; connection_id?: string };
type Config = { schema: 2; operator_state_version: 1; revision: number; generation: string; etag: ConfigEtag;
	layout: Layout; scene: { content: Scene }; displays; calibrations; referenced_displays; referenced_calibrations;
	tablet_models; tablet_assignments; device_labels: Record<DeviceId, string>; snapshots; capabilities: Capabilities;
	runtime: { devices: Record<DeviceId, Device>; presentation?: { owner: string } } };

// api/frames.ts
type ControllerFrame =
	| { type: 'snapshot'; config: Config; devices?: Device[] }
	| { type: 'config_updated'; revision: number; generation: string; etag: ConfigEtag }
	| { type: 'device_online' | 'device_updated'; device: Device }
	| { type: 'device_offline'; device_id: DeviceId; last_seen: string }
	| { type: 'device_removed'; device_id: DeviceId }
	| { type: 'playback_status' } & PlaybackStatus;

// session/outcome.ts: commands return outcomes instead of throwing
type CommandOutcome<T> =
	| { kind: 'ok'; value: T; commandEtag?: ConfigEtag }
	| { kind: 'conflict' }                                   // 412: draft kept
	| { kind: 'precondition-missing' }                       // 428
	| { kind: 'rejected'; status: number; message: string }  // 4xx: nothing happened
	| { kind: 'refused-locally'; reason: 'busy' | 'uncertain' | 'unsupported' | 'stale-etag' }
	| { kind: 'uncertain'; message: string };                // timeout, network, 5xx, unreadable 2xx

// session/session.ts: published snapshot (same fields as operator-session.js:21-23)
type ServerState = { config: Config | null; etag: ConfigEtag | null; etagState: 'current' | 'stale' | 'missing';
	roster: Record<DeviceId, Device>; connectionVersions: Record<DeviceId, number>; rosterError: string | null;
	rosterUnreachable: boolean; rosterCheckedAt: string | null; transportText: string;
	uncertain: boolean; supported: boolean; busy: boolean; adoption: number };

// state/store.ts: the one store
type WallStore = {
	server: ServerState;                              // written only by Session
	clock: { nowMono: number };                       // 1 s tick (2.4)
	ui: { selected: DeviceId | null; source: 'images' | 'saved' | 'layouts' | 'tests';
		editLayout: boolean; drill: DeviceId | null; measureStep: MeasureStep | null; serverOpen: boolean };
	arrangement: { base: Layout; draft: Layout; baseEtag: ConfigEtag | null; undo: Layout[]; redo: Layout[]; conflict: boolean } | null;
	grid: { command: GridCommand; preview: GridPreview | null; baseEtag: ConfigEtag | null; version: number; dirty: boolean } | null;
	content: { selection: SceneInput | null; savedScene: { name: string; etag: ConfigEtag } | null; baseEtag: ConfigEtag | null; version: number };
	forms: Record<`${DeviceId}:${'name' | 'model' | 'profile' | 'calibration'}`, TabletForm>;
	rulerReview: RulerReview | null;
	playlist: { saved: Playlist | null; draft: Playlist | null; etag: PlaylistEtag | null; dirty: boolean };
	playback: { status: PlaybackStatus | null; version: PlaybackVersion | null; optedIn: boolean; exclusions: DeviceId[] };
};
type TabletForm = { baseline: unknown; values: unknown; baseEtag: ConfigEtag | null; version: number; dirty: boolean; conflict: boolean }; // operator-forms.js:8
```

### 4.2 Parsing at the boundary

- Every HTTP response and every socket frame goes through zod (`zod@4`) in `src/api/`. Use `z.looseObject` for Config, Layout, Slot, Placement, Device and Scene, so fields the app does not know survive a read-modify-write. Default stripping would drop them on the next PUT. A test proves the round trip: `LayoutSchema.parse(x)` deep-equals `x` for every captured fixture.
- Scene writes use `SceneInputSchema`, which is strict and has no derived fields. Echoing `url` or `intrinsicWidth` back returns 422 (`main.py:1921`).
- A failed Config parse puts the session into `supported: false`, as an unsupported config does today (`operator-session.js:27-30`). It never throws into React. A bad frame is dropped, and the session reconciles over HTTP.
- An error body is `{detail: string | ValidationError[] | {code, message, …}}`. One `errorMessage(detail)` handles all three and turns device UUIDs into labels, as `operator-session.js:70-73` does.

### 4.3 Session

`session.ts` is a straight port of `operator-session.js` and `operator-sync.js` with the rules in §2.4. It has no React import. Its interface:

```ts
interface Session {
	start(): void; destroy(): void;
	refresh(): Promise<void>;                          // clears the uncertain latch after a newer adoption
	request<T>(method: Method, path: ApiPath, body?: unknown,
		opts?: { ifMatch?: ConfigEtag | PlaylistEtag | PlaybackVersion; useCurrentEtag?: boolean; fenced?: boolean | 'durable';
			parse: ZodType<T> }): Promise<CommandOutcome<T>>;
}
function createSession(deps: { store: StoreApi<WallStore>; fetch?: typeof fetch; WebSocket?: typeof WebSocket;
	now?: () => number; isDirty: () => boolean; timers?: Timers }): Session;
```

`main.tsx` creates the store and the session once, at module scope, before `createRoot`. StrictMode's double effects then cannot open a second socket (Vercel rule `advanced-init-once`). On a 401, the session sets `transportText` to "Signed out" and the header shows a link to `/auth/login?next=/controller/app/`. Today's controller has no 401 handling (open question 3).

### 4.4 Store and drafts

- One Zustand vanilla store (`createStore`). Components read it with `useStore(store, selector)` and select derived primitives, such as `showingCount` rather than `config` (Vercel `rerender-derived-state`).
- Session writes `server` only. Draft reducers in `state/drafts/*.ts` are pure functions `(draft, event) => draft`, tested without React.
- `reconcile.ts` runs on every adoption (`server.adoption` increments) and is the only code that moves drafts when the server changes:
	- A clean arrangement adopts the new layout. A dirty one keeps `base`, `draft` and `baseEtag`, and sets `conflict = true` when the server ETag differs from `baseEtag`.
	- Clean forms adopt the new baseline. Dirty forms keep their values and set `conflict` (`operator-forms.js`, audit 01 §2).
	- A grid preview whose `base_etag` no longer matches is marked stale. It is never silently re-applied.
	- A content selection keeps its `baseEtag`. A saved-scene preview must be discarded and previewed again. It is never rebased (`operator-content.js:531-533`).
- `unsaved.ts` exposes `hasUnsavedEdits(store)` for `beforeunload`, with the same five inputs as `physical.js:504`.

**On wall versus Preview** (owner default 1): the On wall monitor always draws `server.config.layout` and `server.config.scene`. It never draws `arrangement.base`. Preview draws `grid.preview?.layout ?? arrangement.draft` with `content.selection ?? server scene`. During a conflict, On wall therefore shows the wall as it is now, and Preview shows the operator's kept draft. Today's `stageView` would show `base` (`operator-state.js:34-41`). This is a deliberate change, and it is the reason the arrangement keeps `base` separate from `server`.

### 4.5 Commit flow

```text
operator presses Show on wall
  -> commands/scene.ts show(store, session)
       guard = content.baseEtag ?? server.etag
       outcome = session.request('PUT', '/api/v3/scene', {content}, {ifMatch: guard, parse: ConfigSchema})
       ok          -> ingest is already done by session; clear the selection if version unchanged; announce
       conflict    -> mark content conflict; the banner offers Rebuild preview (new guard) or Discard
       uncertain   -> nothing else; the latch shows "Not confirmed" on On wall with Refresh status
       rejected    -> inline message under the action, focus stays on the trigger
       refused-locally -> disabled reason already explains it
```

Every feature command in `state/commands/<domain>.ts` follows this shape. The meaning of "Keep mine" in the conflict banner depends on the draft kind:
- **Arrangement:** after the operator reviews both monitors, Keep mine sets `baseEtag` to the current ETag and keeps the draft.
- **Tablet forms:** Keep mine is `review()` (`operator-forms.js`).
- **Grid:** Keep mine runs the preview again.
- **Saved-scene previews:** Keep mine is not offered.

"Use theirs" always discards the draft.

### 4.6 Shapes considered

| Shape | Verdict |
|---|---|
| A. Ported Session + one Zustand store + pure draft reducers | **Chosen.** Smallest public surface: components call `commands.*` and select from one store. Write rules stay in one tested class. |
| B. TanStack Query for server state, mutations for writes | Rejected. Query retries, refetch-on-focus and cache invalidation duplicate the session's reconcile and conflict with the uncertain latch and the one-writer rule. Two caches (Query and drafts) would need syncing. |
| C. A state machine per draft (XState) | Rejected. It adds a dependency and a second state model for rules that already exist as small reducers (`operator-forms.js` is 58 lines). |

## 5. Geometry and the stage

### 5.1 Ported pure functions

Each port copies the logic, adds types, and ports the old test file's assertions one for one. It also adds a `*.diff.test.ts` that loads the old file through `createRequire` and asserts equal outputs over the same inputs. Differential tests are deleted at switch-over, and the ported tests stay.

| Old file and exports | New file | Old test (assertion count) | Unit |
|---|---|---|---|
| `physical-sizing.js`: `fitBounds, packSlots, nextPosition, edgeThreshold, LOGICAL_EDGE_THRESHOLD_PX, snapLogical, matchScreenShape, freshViewport, validateLogicalField` (`:331-334`) | `src/domain/physicalSizing.ts` | `tests/physical_sizing.test.js` (20) | U05 |
| `operator-state.js`: `layoutSignature, entries, clone, layoutDraft, bounds, fitTransform, fitLogical, arrangeLogical, rotateLogical, compareIds, sameToken, registrationCounts, shownSubject` | `src/domain/layout.ts` | `tests/operator_state.test.js` (62, shared with the next row) | U06 |
| `operator-state.js`: `observeDevice, observeConfig, tabletState, needsAttention, rosterStatus, aggregate` | `src/domain/status.ts` | (same file) | U06 |
| `operator-stage.js`: `panels, resolution, fit, exceptionLabel, powerReadiness, fleetPower, viewZoom, viewSize, helpText` (`:334`; not `draw`); `operator-stage-viewport.js`: `measureWell` | `src/domain/stagePanels.ts` | `tests/operator_stage_fit.test.js` (38) | U07 |
| `physical-calibration.js`: `selectedViewport, rulerScale, rulerUrl, rulerCheckBodies, RulerReview` (`:65`); `operator-measurements.js`: `buildProfileBody, buildCalibrationBody, requireInteger, requireNonNegative` (`:135`) | `src/domain/calibration.ts`, `src/domain/measurements.ts` | `tests/physical_calibration.test.js` (36), `tests/operator_measurements.test.js` (17) | U08 |
| `operator-grid.js`: `command, membership` (`:468`); `operator-forms.js`: `snapshotName` (`:55`) | `src/domain/gridCommand.ts`, `src/domain/names.ts` | `tests/operator_grid.test.js` (46), `tests/snapshot_names.json` cases | U09 |
| Cross-module checks | — | `tests/operator_geometry.test.js` (83) | U10 |
| `operator-forms.js`: `create` (form drafts) | `src/state/drafts/tabletForms.ts` | `tests/operator_forms.test.js` (40) | U11 |
| `operator-workspace.js:59-66` `setupProgress` | `src/domain/nextStep.ts` | new | U28 |

`tests/operator_state.test.js` already compares `fitTransform` with the tablet's `frontend/client/view.js`. The port keeps that cross-check, so the controller preview and the tablet can never disagree about Fill and Fit.

### 5.2 Stage rendering

- `WallSvg` takes `{layout, content, profileFor, statuses, selected?, interactive}`. The `viewBox` is the layout bounds plus a margin, in wall units: mm for physical, logical units for logical. The aspect is kept with `preserveAspectRatio="xMidYMid meet"`.
- For each panel from `stagePanels.panels()`:
	- The body is drawn as a rect rotated by `mount_angle` around (cx, cy).
	- The active screen is a `clipPath`.
	- The wall image is one `<image>` placed by `fitTransform` over the whole bounds and clipped to each active screen. That is how one picture spans the wall.
	- The overlay shows status (hatch plus "Offline", missing profile, excluded) and a label pill.
- The same component draws both monitors. On wall uses `interactive={false}`.
- The stage box size depends only on the viewport, never on mode, selection or alerts (G1: drift at most 0.02). Use CSS grid tracks with fixed `aspect-ratio`. No content inside the stage box affects its size.

### 5.3 On-canvas editing (A's editing inside C's "Edit layout")

`useStageGesture` implements the `drag` guide from modern-web-guidance:
- It reacts to the primary button only, uses `setPointerCapture`, and clears state on `lostpointercapture`.
- The threshold is 3 px. The tablet body has `touch-action: none`.
- The in-progress transform lives in a ref and a CSS `transform` on the dragged group. The store is not written per frame (Vercel `rerender-use-ref-transient-values`).
- On release it commits once: one draft update and one undo entry. Esc restores the state from before the drag.

| Gesture | Logical | Physical |
|---|---|---|
| Drag | `x, y` with `snapLogical` and `edgeThreshold` | `center_x_mm, center_y_mm` (or the nudge with Alt, as today) |
| Resize handles | `w, h`, checked by `validateLogicalField` | none (size comes from the profile) |
| Rotate | `rotateLogical` (swaps w and h and rotates the bezels) | Rotation handle: free angle, 15° snap unless Shift is held. Buttons for ±90° |
| Bezels | Numeric fields in the drill-in, drawn live | From the profile, read-only |
| Keyboard | Arrows move by the snap step, Shift multiplies by 10. Delete removes the placement after confirmation | Same |

A visually hidden `aria-live="polite"` region announces "Tablet 2 moved". Numeric fields in the drill-in give a way to do every gesture without dragging.

## 6. Testing

| Layer | Tool | What | Where |
|---|---|---|---|
| Pure logic | Vitest (node env) | Ported assertions plus differential tests against the old files | `src/**/*.test.ts` |
| Session and drafts | Vitest with fake fetch, fake WebSocket and fake timers | Ported `operator_session` (16), `operator_sync` (22), `operator_unreachable` (4) and `operator_late_join` (8) assertions; the reconcile matrix | `src/session/*.test.ts`, `src/state/*.test.ts` |
| Components | Vitest (jsdom) + Testing Library | Roles, labels, disabled reasons, focus return. No geometry (jsdom has no layout) | `src/features/**/*.test.tsx` |
| End to end | `@playwright/test` 1.57.0, Chromium (WebKit spot checks in U32) | Real FastAPI build, real `/client/` tablet pages | `e2e/*.spec.ts` |
| Accessibility | `@axe-core/playwright`, tags `wcag2a, wcag2aa, wcag21aa, wcag22aa` | 0 violations per state, width and theme | in each screen spec |
| Visual | `toHaveScreenshot`, `animations: 'disabled'`, fonts awaited | 390×844, 820×1180 and 1440×900, light and dark | `e2e/__screenshots__/` |
| Backend | unchanged `make test`, `make sim` | Protocol and HTTP behaviour | existing |

**e2e harness** (`e2e/fixtures.ts`, U03):
- `server` (worker-scoped): pick a free port and create a temp dir. Set `TABLET_WALL_DB`, `TABLET_WALL_ASSET_DIR`, `TABLET_WALL_MEDIA_DIR` and `TABLET_WALL_BACKUP_DIR` under it. Set `TABLET_WALL_TABLET_ORIGIN` and `TABLET_WALL_OPERATOR_ORIGIN` to `http://127.0.0.1:<port>`, `TABLET_WALL_UPLOAD_MODE=loopback` and `TABLET_WALL_WIFI_NAME=QA`. Clear every inherited `TABLET_WALL_*` and `WALL_*` variable first. This mirrors `simulator/browser/redesign_acceptance.py:273-305` and `deploy/hotspot.py:264-277`. Run `uv run fastapi run main.py --host 127.0.0.1 --port <port>` from the repo root, and wait for `/healthz` to return 200.
- `tablets(n, opts)`: one browser context per tablet with `addInitScript(() => localStorage.setItem('tablet-wall-device-id', ID))`, opened at `/client/`. This is the method in the scratchpad `tour.py`. Fixed UUIDs come from `e2e/fixtures/fleet.ts`.
- `api`: typed REST helpers that reuse `src/api` schemas: `config()`, `placeLogical(grid)`, `placePhysical(slots)`, `upload(file)`, `scene(input)`. Because the server has `TABLET_WALL_OPERATOR_ORIGIN` set, the Origin fence applies to every write. Create the request context with `extraHTTPHeaders: { Origin: 'http://127.0.0.1:<port>' }`, and send `If-Match` with the ETag from a fresh GET config on every guarded write. Without the header every write returns 403.
- `writes(page)`: records every non-GET request the controller page sends to `/api`, `/devices`, `/uploads` or `/media`.
- `tabletPixel(tablet, x, y)`: samples the tablet canvas with `getImageData`, as the existing drivers do (`controller_run.py:165`).
- `guard(page)`: fails the test on any `securitypolicyviolation`, page error, console error, or request to another origin.
- `axe(page)`: runs `AxeBuilder`. If CSP blocks injection, it reopens the same URL in a separate context with `bypassCSP: true` only for axe. CSP and console checks always run in a normal context.
- `stageBox(page)`: `getBoundingClientRect` of `[data-stage="preview"]`.

**Parity gate.** U04b turns every row of §8 into a spec stub `test.fixme('<row id> <behaviour>')`. A feature unit is done when its rows run and pass. Feature parity means all of these hold: `grep -rn "test.fixme" frontend/controller-app/e2e | wc -l` prints `0`, `make app-e2e` passes, `make app-check` passes, `make test` and `make sim` pass, and the owner has approved the screenshots.

**Existing drivers.** Fates, applied by U33 and U34:

| Driver | Fate |
|---|---|
| `simulator/run.py` and `scenarios.py` (no browser) | Kept as is |
| `first_run_acceptance`, `redesign_acceptance` + `_redesign_scenarios` + `_redesign_edge_cases`, `renewal_acceptance`, `composition_gates`, `operator_accessibility` | Rewritten as TS specs (rows in §8). Deleted at switch-over |
| `readiness_acceptance` | Join and readiness obligations rewritten (row S2). Its 15 failures from before this work are not carried over. The `experimental.html` part stays (open question 1) |
| `restoration_acceptance` | Retired. It drives the old five-tab console and is already red at 36/47 (PROPOSAL §6) |
| `controller_run`, `video_run`, `video_transitions_run`, `reconnect_exclusions_run` | Controller-side checks rewritten in U30. Their tablet-side checks are moved to REST playback calls in U33 |
| `field_run`, `group_recovery_run`, `recovery_acceptance_run`, `recovery_run`, `health_run`, `image_efficiency`, `fleet_soak`, `audit_round`, `experience_acceptance`, `decode_probe` | The controller is incidental. U33 replaces their controller-page steps with REST calls through a new `simulator/browser/_api.py` and keeps their tablet and server evidence |
| `run.py` (uses `experimental.html`) | Unchanged |

## 7. Units of work

Every unit runs in its own git worktree from the latest integration branch. "Files" lists every file the unit may create or change. A unit that needs to change any other file stops and reports the need. Run all commands from `frontend/controller-app/` unless a command says otherwise. Tiers: **CH** is Codex 6.1 Sol high, **CM** is Codex medium, and **DS** is DeepSeek.

**Shared wiring files.** Any unit may make small additive changes to `src/main.tsx`, `src/App.tsx` and anything under `src/dev/` to mount and test its work, without that file being on its Files line. List those changes in the commit body. Units U01, U04, U13, U14 and U15 each stopped on this before the rule existed.

**Standard checks**, referred to as `STD` below. Run them in this order. Each must exit 0:
1. `npm run typecheck`
2. `npm run lint`
3. `npm run test`
4. `npm run build && npm run build:e2e`
5. The unit's own e2e commands from its **Accept** line. They run here, after step 4, so they test this unit's code and not the last committed build.
6. `git clean -fdq ../controller/app && git checkout -- ../controller/app`. This is always the last change to the tree (the clean removes newly hashed build files).
7. `git diff --name-only <base>...HEAD` lists only files named in the unit's **Files** line

**Parallel lanes** (no shared files inside a lane step):

```text
L0  U01 ─┬─ U02 ─┐
         ├─ U03 ─┼─ U04b
         ├─ U04 ─┤
         ├─ U05, U06, U07, U08, U09 (DS, parallel) ── U10 (DS)
         └─ U14 (needs spec)
L1  U11 (after U04, U06)
    U12 (after U06, U07) ─┬─ U13 (after U11)
                          └─ U15 (after U04, U11, U14)
L2  after U15, in parallel: [U16 → U17, U18] [U19] [U20] [U21] [U22 (also after U13)] [U23 → U24 → U25] [U26] [U27 → U30] [U23 → U28] [U16 + U22 → U29]
L3  U31 ── U32 PARITY ── U33 ── U34 SWITCH-OVER ── U35
```

The riskiest unknowns come first. U01 proves serving, CSP, fonts, sockets and auth. U03 proves the harness. U04 proves the session. U12 and U13 prove that the SVG stage and its gestures work before any feature depends on them.

---

### U01 · Scaffold and serving spike · CH
- **Depends on:** nothing.
- **Files:** `tests/test_ingress.py` (add `"/controller/app/"` to `read_paths` at line 553, so the tablet listener is proven to deny the new app), `frontend/controller-app/**` (all config files from §3, `index.html`, `public/theme.js`, `src/main.tsx`, `src/App.tsx`, `src/styles/{tokens.css,app.css}`, `e2e/server.ts`, `e2e/smoke.spec.ts`), `frontend/controller/app/**` (first build), `Makefile` (three targets), `.gitignore` (add `node_modules/`, `frontend/controller/app-e2e/`, `frontend/controller-app/test-results/`, `frontend/controller-app/playwright-report/`).
- **Do:**
	- Install every dependency the plan needs, with exact versions (no `^`). Each version must have been published at least two weeks before install.
		- Runtime: `react`, `react-dom` 19.x, `zod` 4.x, `zustand` 5.x, `lucide-react`, `clsx`, `tailwind-merge`, `class-variance-authority`, `@radix-ui/react-{slot,tabs,toggle-group,tooltip,dropdown-menu}`, `@fontsource-variable/atkinson-hyperlegible-next` (if that package is missing, vendor the OFL `woff2` into `src/assets/fonts/`).
		- Dev: `vite`, `@vitejs/plugin-react`, `tailwindcss` 4.x, `@tailwindcss/vite`, `typescript`, `vitest`, `jsdom`, `@testing-library/{react,user-event,jest-dom}`, `@playwright/test@1.57.0`, `@axe-core/playwright`, `eslint`, `typescript-eslint`, `eslint-plugin-react-hooks`, `@types/{react,react-dom,node}`.
	- Write `components.json` for shadcn with Tailwind v4 and the `src/ui` alias.
	- Write `tsconfig` with `strict` and `noUncheckedIndexedAccess`.
	- The page renders "Tablet wall" and the session's `transportText`. U01 uses a 20-line throwaway WebSocket hook, replaced in U04.
	- Placeholder tokens are copied from `docs/redesign/mockups/src/head.html`.
	- `e2e/server.ts` starts an isolated server as described in §6.
	- Add the script `"build:e2e": "vite build --mode e2e --base /controller/app-e2e/ --outDir ../controller/app-e2e"`. In `main.tsx`, when `import.meta.env.MODE === 'e2e'` and `location.hash === '#stage-fixture'`, render `src/dev/StageFixture.tsx` (an empty stub here, filled by U12) instead of the app.
- **Accept:**
	- `STD` passes. Exception: step 4 commits the first build.
	- `npm run build && npm run build && git status --porcelain ../controller/app` prints nothing.
	- `grep -c '<script' ../controller/app/index.html` prints `2`, and both tags have `src` (`theme.js` and the module entry).
	- `npx playwright test e2e/smoke.spec.ts` passes. It asserts that `/controller/app/` returns 200 with a CSP header, there are 0 `securitypolicyviolation` events and 0 console errors, `document.fonts.check('16px "Atkinson Hyperlegible Next"')` is true, a `snapshot` frame arrives, and there are 0 requests to another origin.
	- The same spec, run with `TABLET_WALL_AUTH_TOKEN` set to a 32-byte value, signs in through `POST /auth/login` and then passes the same assertions.
	- From the repo root, `uv run pytest -q tests/test_ingress.py` passes.

### U02 · API schemas and contract fixtures · CH
- **Depends on:** U01.
- **Files:**
	- `src/api/{etag,paths,errors,config,devices,scene,images,layouts,saved,grid,lifecycle,measure,readiness,diagnostics,playback,frames}.ts`
	- `src/api/__fixtures__/*.json`
	- `src/api/*.test.ts`
	- `e2e/contract.spec.ts`
- **Do:**
	- Write the §4.1 types as zod schemas. Export each `type X = z.infer<…>`.
	- Write one `paths.ts` with typed path builders for every §2.2 row.
	- `contract.spec.ts` drives the backend through a scripted session against an isolated server: 4 tablets join, a logical grid, a physical layout, a scene, a saved scene and layout, a grid preview, an impact read, a rebind preview, a ruler check, readiness, diagnostics, playlist and playback status. It parses every response and every observed frame type. Only when `CAPTURE=1` is set does it also write them to `src/api/__fixtures__/`. A normal run parses and asserts, and never writes to the tree. Run `CAPTURE=1 npx playwright test e2e/contract.spec.ts` once in this unit and commit the fixtures.
- **Accept:**
	- `npx playwright test e2e/contract.spec.ts` passes.
	- `npx vitest run src/api` passes, including one round-trip test per layout fixture: `expect(LayoutSchema.parse(f)).toEqual(f)`.
	- A negative test proves that `SceneInputSchema.parse({type:'image',asset,fit:'cover',url:'x'})` fails.
	- `STD` passes.

### U03 · e2e harness · CH
- **Depends on:** U01.
- **Files:** `e2e/fixtures.ts`, `e2e/fixtures/fleet.ts`, `e2e/fixtures/images/*` (copy `assets/EXLENT_Cohort_3_Flyer_Temp.png`, plus a 2-colour 1600×900 PNG for the pixel tests), `e2e/harness.spec.ts`, `playwright.config.ts`.
- **Do:** implement every fixture in §6, including the `Origin` header on the `api` request context. The config uses `workers: 2`, `fullyParallel: false` inside a file, `use.viewport` per project (`phone` 390×844, `tablet` 820×1180, `desktop` 1440×900, and `webkit-desktop` 1440×900 on WebKit, run only by U32). Confirm that `npx playwright test e2e/harness.spec.ts --project=webkit-desktop` launches on this Fedora host. If WebKit cannot launch, remove the project and record that in the commit message and in §9 as a limitation, and `expect.toHaveScreenshot: { animations: 'disabled', maxDiffPixelRatio: 0.002 }`.
- **Accept:** `npx playwright test e2e/harness.spec.ts --workers=2` passes, and it asserts all of these:
	1. 4 tablets show `online: true` in `api.config()` within 10 s.
	2. After `api.placeLogical(2×2)` and `api.scene(image cover)`, every tablet's `runtime.devices[id].render.state` is `displayed` within 10 s.
	3. `tabletPixel` at each screen centre matches the expected colour of the 2-colour image within ±30 per channel.
	4. Two workers use different ports.

### U04 · Session port · CH
- **Depends on:** U01, U03, U02 (schemas). It can start against `unknown` parsing and switch to schemas when U02 merges.
- **Files:** `src/session/{session,sync,readFence,outcome}.ts`, `src/session/*.test.ts`, `src/session/session.diff.test.ts`, `src/main.tsx` (replace the U01 hook), `e2e/session.spec.ts`.
- **Do:** port the §2.4 rules exactly. Port the assertions of the four old test files. The differential test drives the old `operator-session.js` (loaded with `createRequire`, and with `syncFactory` injected) and the new session through the same fake transport script, then compares outcome kinds and published snapshot fields.
- **Accept:**
	- `npx vitest run src/session` passes, with at least as many `expect(` lines as the four old files have assertion lines (`cat src/session/*.test.ts | grep -cE 'expect\('` prints at least `50`). The named cases must include: a timeout makes the next durable write `refused-locally:uncertain`, and `refresh()` clears it; a 5xx is uncertain; an unreadable 2xx is uncertain; a second durable write while one is in flight is `refused-locally:busy`; a 412 keeps the draft; a late read is fenced; `config_updated` marks the ETag stale; a reconnect is scheduled at 3000 ms; reconcile runs at 15000 ms only when visible.
	- `npx playwright test e2e/session.spec.ts` passes. Using `page.routeWebSocket` to close the socket, a new `/ws/controller` connection opens within 3.5 s. With the socket blocked for the whole test, a label change made through `api` appears in the page within 16 s.
	- `STD` passes.

### U04b · Parity spec stubs · DS
- **Depends on:** U03.
- **Files:** `e2e/parity/<ID>.spec.ts`, one file per row in §8 (60 files, `D1.spec.ts` to `X15.spec.ts`). One file per row means parallel units never edit the same spec file.
- **Do:** in each file, write `import { test } from '../fixtures';` and exactly one `test.fixme('<ID> <Behaviour text>', async () => {});`. Copy the ID and the Behaviour cell character for character. Write nothing else.
- **Accept:** `ls e2e/parity/*.spec.ts | wc -l` prints `60`, and `grep -rho "test.fixme('[A-Z][0-9]*" e2e/parity | sort -u | wc -l` prints `60`. `npx playwright test e2e/parity --list` exits 0. `STD` passes.

### U05 · Port physical sizing · DS
- **Depends on:** U01.
- **Files:** `src/domain/physicalSizing.ts`, `src/domain/physicalSizing.test.ts`, `src/domain/physicalSizing.diff.test.ts`.
- **Do:**
	1. Copy every function exported at `frontend/controller/physical-sizing.js:331-334`, and the private helpers they call, into `physicalSizing.ts` as named `export function`s with the same names. Add parameter and return types using `Slot`, `Placement` and `LogicalLayout` from `src/api/config.ts`. Where U02 has not merged yet, use local types with the same field names. Do not change any expression, constant or message string.
	2. In `physicalSizing.test.ts`, copy `tests/physical_sizing.test.js`. Replace `require` with `import * as sizing from './physicalSizing'`. If the old file has no `test(` calls, wrap the whole body in one `it('<file name>', () => { … })`. If it uses `node:test`, turn each `test(name, fn)` into `it(name, fn)`. Replace each assertion on its own line:
		- `assert.deepEqual(a,b)` and `assert.deepStrictEqual(a,b)` become `expect(a).toEqual(b)`
		- `assert.equal(a,b)` and `assert.strictEqual(a,b)` become `expect(a).toBe(b)`
		- `assert.notEqual(a,b)` becomes `expect(a).not.toBe(b)`, and `assert.notDeepEqual(a,b)` becomes `expect(a).not.toEqual(b)`
		- `assert.ok(x)` and `assert(x)` become `expect(x).toBeTruthy()`
		- `assert.match(s,r)` becomes `expect(s).toMatch(r)`
		- `assert.throws(fn, m)` becomes `expect(fn).toThrow(m)`, and `assert.doesNotThrow(fn)` becomes `expect(fn).not.toThrow()`
		- `await assert.rejects(p, m)` becomes `await expect(p).rejects.toThrow(m)`
		Put each `expect(` on its own line, so the line counts below stay comparable.
	3. In `physicalSizing.diff.test.ts`, load the old module with `createRequire(import.meta.url)('../../../controller/physical-sizing.js')`. For every call in the test file, assert `expect(newFn(...args)).toEqual(oldFn(...args))`.
- **Accept:**
	- `npx vitest run src/domain/physicalSizing` prints `Tests  2 passed (2)` (one `it` in each of the two files).
	- `OLD=$(grep -cE 'assert(\.[a-zA-Z]+)?\(' ../../tests/physical_sizing.test.js); NEW=$(grep -cE 'expect\(' src/domain/physicalSizing.test.ts); test "$NEW" -ge "$OLD"` exits 0 (the old file has 20).
	- `STD` passes.

### U06 · Port layout and status logic · DS
- **Depends on:** U01.
- **Files:** `src/domain/layout.ts`, `src/domain/status.ts`, `src/domain/layoutStatus.test.ts`, `src/domain/layoutStatus.diff.test.ts`.
- **Do:** the same three steps as U05.
	- Source: `frontend/controller/operator-state.js`. Put the functions from the first `operator-state.js` row of §5.1 in `layout.ts`, and the second row in `status.ts`. `stageEditable` and `stageView` are not ported. `readFence` belongs to U04.
	- Test source: `tests/operator_state.test.js` (62 assertions). Its comparison with `frontend/client/view.js` loads that file through `createRequire('../../../client/view.js')` and is kept.
- **Accept:**
	- `npx vitest run src/domain/layoutStatus` passes.
	- `OLD=$(grep -cE 'assert(\.[a-zA-Z]+)?\(' ../../tests/operator_state.test.js); NEW=$(grep -cE 'expect\(' src/domain/layoutStatus.test.ts); test "$NEW" -ge "$OLD"` exits 0 (the old file has 62).
	- `STD` passes.

### U07 · Port stage panels · DS
- **Depends on:** U01.
- **Files:** `src/domain/stagePanels.ts`, `src/domain/stagePanels.test.ts`, `src/domain/stagePanels.diff.test.ts`.
- **Do:** the same three steps as U05.
	- Sources: the exports listed at `operator-stage.js:334` except `draw`, plus `measureWell` from `operator-stage-viewport.js:42`.
	- Test source: `tests/operator_stage_fit.test.js` (38 assertions). Skip any assertion that calls `draw` or `create`, and list the skipped line numbers in the commit message.
- **Accept:**
	- `npx vitest run src/domain/stagePanels` passes.
	- `grep -cE 'expect\(' src/domain/stagePanels.test.ts` plus the number of skipped assertions is at least `38`.
	- `STD` passes.

### U08 · Port calibration and measurement bodies · DS
- **Depends on:** U01.
- **Files:** `src/domain/calibration.ts`, `src/domain/measurements.ts`, `src/domain/calibration.test.ts`, `src/domain/measurements.test.ts`, `src/domain/calibration.diff.test.ts`.
- **Do:** the same three steps as U05.
	- Sources: `physical-calibration.js:65` and `operator-measurements.js:135`. Port only the four body builders. The rest of `operator-measurements.js` is DOM code.
	- Tests: `tests/physical_calibration.test.js` (36) and `tests/operator_measurements.test.js` (17). `node:test` `test(name, fn)` becomes `it(name, fn)`.
- **Accept:**
	- `npx vitest run src/domain/calibration src/domain/measurements` passes.
	- `OLD=$(grep -cE 'assert(\.[a-zA-Z]+)?\(' ../../tests/physical_calibration.test.js); NEW=$(grep -cE 'expect\(' src/domain/calibration.test.ts); test "$NEW" -ge "$OLD"` exits 0, and the same check for `../../tests/operator_measurements.test.js` against `src/domain/measurements.test.ts` exits 0 (the old files have 36 and 17).
	- `STD` passes.

### U09 · Port grid command and snapshot names · DS
- **Depends on:** U01.
- **Files:** `src/domain/gridCommand.ts`, `src/domain/names.ts`, `src/domain/gridCommand.test.ts`, `src/domain/names.test.ts`, `src/domain/gridCommand.diff.test.ts`.
- **Do:** the same three steps as U05.
	- Sources: `command` and `membership` from `operator-grid.js:4-68` (nothing from `create`), and `snapshotName` from `operator-forms.js`.
	- `gridCommand.test.ts` ports `tests/operator_grid.test.js` (46 assertions). Skip assertions that call `create`, and list the skipped lines.
	- `names.test.ts` loops over `tests/snapshot_names.json` (imported with `import cases from '../../../../tests/snapshot_names.json'`) and asserts the same accept and reject result as the old `snapshotName`.
- **Accept:**
	- `npx vitest run src/domain/gridCommand src/domain/names` passes.
	- `grep -cE 'expect\(' src/domain/gridCommand.test.ts` plus the number of skipped assertions is at least `46`.
	- `STD` passes.

### U10 · Port cross-module geometry checks · DS
- **Depends on:** U05, U06, U07.
- **Files:** `src/domain/geometry.test.ts`.
- **Do:** port `tests/operator_geometry.test.js` (83 assertions) with the replacements from U05 step 2. Change the imports to the new `layout`, `physicalSizing` and `stagePanels` modules.
- **Accept:**
	- `npx vitest run src/domain/geometry` passes.
	- `OLD=$(grep -cE 'assert(\.[a-zA-Z]+)?\(' ../../tests/operator_geometry.test.js); NEW=$(grep -cE 'expect\(' src/domain/geometry.test.ts); test "$NEW" -ge "$OLD"` exits 0 (the old file has 83).
	- `STD` passes.

### U11 · Store, drafts, reconcile · CH
- **Depends on:** U04, U06.
- **Files:** `src/state/{store,reconcile,unsaved,hooks,commands/run}.ts`, `src/state/drafts/{arrangement,content,tabletForms,grid,playlist}.ts`, tests beside each file.
- **Do:**
	- Write the §4.1 store and the §4.4 rules.
	- Write `commands/run.ts`, which maps a `CommandOutcome` onto draft flags. U16 onward call it.
	- Write the 1 s clock tick. It writes `clock.nowMono` only when the status signature (`status.ts` over all placed ids) changes, which matches `physical.js:3118-3121`.
	- Port the `create` assertions from `tests/operator_forms.test.js`.
- **Accept:**
	- `npx vitest run src/state` passes. Named cases:
		- A remote adoption keeps a dirty arrangement and sets `conflict`.
		- A clean form adopts the new baseline. A dirty form keeps its values.
		- Switching `ui.selected` between two devices keeps both devices' form drafts.
		- Undo stops at 80 entries.
		- A grid preview with a stale `base_etag` is marked stale.
		- A saved-scene preview is dropped on conflict, not rebased.
		- `hasUnsavedEdits` is true for each of the five draft kinds on its own.
		- The tick does not change the store when no status changes.
	- `STD` passes.

### U12 · WallSvg, read-only · CH
- **Depends on:** U03, U06, U07.
- **Files:** `src/stage/{WallSvg,TabletShape}.tsx`, `src/stage/*.test.tsx`, `src/dev/StageFixture.tsx` (fills the U01 stub), `e2e/stage-geometry.spec.ts`, `e2e/fixtures/walls.ts`. Run fixtures with `npm run build:e2e`. Its output is gitignored and served by the same FastAPI mount at `/controller/app-e2e/#stage-fixture`. The production build must not contain the fixture: `grep -c stage-fixture ../controller/app/assets/*.js` prints `0`.
- **Do:** §5.2. Fixture walls, each with **hand-computed** expected screen rectangles in `walls.ts`, not values produced by the production code:
	- logical 3×2 with a trailing hole and asymmetric bezels;
	- logical with a negative placement;
	- physical with mount angles 0, 90, 180 and 270;
	- physical at 37° with a nudge;
	- physical with a negative-origin bounds;
	- a missing profile.
- **Accept:**
	- `npx playwright test e2e/stage-geometry.spec.ts` passes.
	- For each fixture tablet, the `[data-screen=<id>]` client rect matches the expected rect within ±0.5 px at 1440×900.
	- With the 2-colour image, the sampled stage pixel at each screen centre is the expected colour for `cover` and for `contain`.
	- `STD` passes.

### U13 · Stage editing · CH
- **Depends on:** U11, U12.
- **Files:** `src/stage/useStageGesture.ts`, `src/stage/EditOverlay.tsx`, `src/stage/*.test.ts`, `e2e/stage-edit.spec.ts`.
- **Do:** §5.3, tested on the U12 fixture build.
- **Accept:** `npx playwright test e2e/stage-edit.spec.ts` passes and asserts:
	1. Dragging tablet 2 by 100 px changes `center_x_mm` by `100 × mmPerPx` within ±0.5 mm, where `mmPerPx` is computed in the test from the stage rect and the bounds.
	2. The drag sends 0 requests.
	3. Ctrl+Z restores the previous centre exactly. Esc during a drag restores it.
	4. ArrowRight moves the tablet by one snap step, and Shift+ArrowRight by ten.
	5. The rotate handle with Shift gives 37°. Without Shift it snaps to 30° or 45°.
	6. A logical resize below the bezels is refused with the `validateLogicalField` message.
	7. The live region text changes after each move.
	- `STD` passes.

### U14 · Tokens and primitives · CM · needs spec
- **Depends on:** U01 and `docs/redesign/03-visual-spec.md`.
- **Files:** `src/styles/tokens.css`, `src/styles/app.css`, `src/ui/*.tsx` (Button, Tabs, ToggleGroup, Tooltip, DropdownMenu, Input, Label, Field, StatusBadge, Tally, ModalDialog, SideSheet), `src/ui/*.test.tsx`.
- **Do:**
	- Map the spec's tokens to Tailwind v4 `@theme`, in light and dark, with `:root[data-theme]` overrides, matching `public/theme.js`.
	- Restyle the shadcn primitives to the spec. Surfaces are separated by tone, spacing and elevation. Borders appear only on inputs, focus, selection and drop targets. Buttons are filled for primary actions and ghost or quiet for the rest. Do not use the outlined variants.
	- `ModalDialog` and `SideSheet` wrap native `<dialog>` with `showModal()` (modern-web-guidance `dialog` Rule 1): no `role="dialog"`, `aria-modal` or focus trap; `aria-labelledby` points to the heading; `autofocus` on the safe action in destructive confirms; unsaved-change guards live in `cancel`; `dialog:modal { overscroll-behavior: contain }`.
	- `StatusBadge` always shows an icon, a word and a colour.
- **Accept:**
	- `npx vitest run src/ui` passes. The cases cover: a disabled Button exposes its reason through `aria-describedby`; a ModalDialog returns focus to its opener; StatusBadge renders the icon and the word for each status.
	- `STD` passes.

### U15 · App shell (Direction C layout) · CH · needs spec
- **Depends on:** U04, U11, U12, U14.
- **Files:**
	- `src/App.tsx`
	- `src/features/header/**`, `src/features/preview/**`, `src/features/onwall/**`
	- Stub `index.tsx` files for every other `features/*` folder, plus `features/sources/layouts/{SavedLayouts,GridBuilder,EmptyWall}.tsx` and `features/tablet/{Facts,Commands,Lifecycle,MeasureEntry,PlacementFields}.tsx`
	- `src/features/preview/PrimaryAction.tsx`
	- `e2e/shell.spec.ts`
- **Do:**
	- **Header:** status summary button, Server button and theme toggle.
	- **Preview column:** the "Preview" tally, `WallSvg` interactive, the sources tab strip with a fixed height, and `PrimaryAction`.
	- **Right column:** the On wall monitor (`WallSvg` read-only, server truth), the Next step slot, the board slot, and the drill-in slot.
	- **Phone:** Preview pinned at the top, then one "On wall" line that expands to the small view on tap (owner default 3).
	- `PrimaryAction` asks the hooks `usePlaybackAction`, `useArrangementAction` and `useContentAction`, each in its own feature file and stubbed here to return `null`, and shows the first non-null result. Feature units fill in their own hook and never edit `PrimaryAction.tsx`.
- **Accept:** `npx playwright test e2e/shell.spec.ts` passes. At 390, 820 and 1440, across the states main, tablet selected, edit layout on and drill-in open:
	1. The `stageBox` drift is at most 0.02.
	2. At 390, after every scroll container is scrolled to its end, the preview stage rect stays inside the viewport.
	3. axe reports 0 violations in light and in dark.
	4. Screenshot baselines are created.
	- `STD` passes.

### U16 · Images and Show on wall · CH
- **Depends on:** U15.
- **Files:** `src/features/sources/images/**`, `src/features/preview/useContentAction.ts`, `src/state/commands/scene.ts`, `e2e/parity/C{1..5}.spec.ts`, `e2e/parity/C10.spec.ts`.
- **Do:**
	- Library: search uses `startTransition`; thumbnails come from `thumbnail_url`; an empty state says what to upload, or why upload is off.
	- Selecting an image starts a Preview and sends zero writes.
	- Fill and Fit, plus the background colour.
	- Crop text built from `fitTransform.cropX` and `cropY`, and the resolution warning from `stagePanels.resolution`.
	- Show on wall follows §4.5. Focus rules follow `operator-content.js:536-558`.
- **Accept:** rows C1–C5 and C10 pass. `STD` passes.

### U17 · Upload · CM
- **Depends on:** U16.
- **Files:** `src/features/sources/images/Upload.tsx`, `src/state/commands/upload.ts`, `e2e/parity/C6.spec.ts`.
- **Do:** §2.4 upload rule. `final.html` (state `library`) shows a queue of several files. Upload them one at a time, one request per file, because `/uploads` takes one raw body. Show progress per file. Cancel before the transfer completes aborts the XHR, and the file is not added. Cancel after `upload.onload` is not offered, because the server may already be ingesting. The server decides which types it accepts (a 415 shows as a refusal on that row). Disable the control with a reason when `capabilities.uploads` is false. After a success, refresh the library and select the new image if the queue had one file. Never show an upload on the wall.
- **Accept:** row C6 passes. It uses `page.route` to delay, abort, return 500 and return malformed JSON. Each case leaves `writes(page)` with no `/api/v3/scene`. `STD` passes.

### U18 · Saved content · CM
- **Depends on:** U16.
- **Files:** `src/features/sources/saved/**`, `src/state/commands/savedScenes.ts`, `e2e/parity/C7.spec.ts`.
- **Accept:** row C7 passes. `STD` passes.

### U19 · Tests tab · CM
- **Depends on:** U15.
- **Files:** `src/features/sources/tests/**`, `src/state/commands/testPatterns.ts`, `e2e/parity/C8.spec.ts`.
- **Accept:** row C8 passes. `STD` passes.

### U20 · Saved arrangements, return points, Clear wall · CM
- **Depends on:** U15.
- **Files:** `src/features/sources/layouts/{SavedLayouts,EmptyWall}.tsx`, `src/state/commands/savedLayouts.ts`, `e2e/parity/A{5,6}.spec.ts`.
- **Do:**
	- Clicking a saved arrangement draws its stored `layout` in Preview with zero writes.
	- Apply sends POST `…/recall` with `If-Match`. A change of kind needs confirmation in a ModalDialog.
	- Show the `previous_layout_saved` return point.
	- Save, replace and delete, with `names.ts` validation before any request.
	- Clear wall sends POST `/api/v3/layout/clear {confirm:true}` after a ModalDialog confirmation. `final.html` places it in the Server panel (state `data`). Put the component in `EmptyWall.tsx`, and let U15 mount it where the spec says.
- **Accept:** rows A5–A6 pass. `STD` passes.

### U21 · Grid builder · CH
- **Depends on:** U15, U09.
- **Files:** `src/features/sources/layouts/GridBuilder.tsx`, `src/state/commands/grid.ts`, `e2e/parity/A{1,2,8}.spec.ts`.
- **Accept:** rows A1–A2 and A8 pass. `STD` passes.

### U22 · Edit layout and Apply · CH
- **Depends on:** U13, U15.
- **Files:**
	- `src/features/preview/{EditToolbar.tsx,useArrangementAction.ts}`
	- `src/features/tablet/PlacementFields.tsx` (fills the U15 stub)
	- `src/state/commands/layout.ts`
	- `e2e/parity/A{3,4,7}.spec.ts`
- **Do:**
	- Toolbar: undo and redo, snap toggle, fit to tablets, pack, tile, match screen shape, wall bounds, discard.
	- Placement fields for the selected tablet: logical x, y, w, h and bezels; physical centre, nudge, angle and participating.
	- Apply sends one PUT with `arrangement.baseEtag`.
- **Accept:** rows A3–A4 and A7 pass. `STD` passes.

### U23 · Board, header summary, status · CH
- **Depends on:** U15.
- **Files:** `src/features/board/**`, `src/features/header/StatusSummary.tsx`, `e2e/parity/S{1..4}.spec.ts`, `e2e/parity/D{1,2}.spec.ts`.
- **Do:** one row per placed or registered tablet, with icon, word and age. The header summary counts with `aggregate`. Clicking the summary focuses the first problem row.
- **Accept:** rows S1–S4 and D1–D2 pass. `STD` passes.

### U24 · Tablet drill-in: facts, name, model, commands, batch · CM
- **Depends on:** U23.
- **Files:** `src/features/tablet/{index,Facts,Commands}.tsx`, `src/state/commands/devices.ts`, `e2e/parity/T{1,2,3,6}.spec.ts`.
- **Accept:** rows T1–T3 and T6 pass. `STD` passes.

### U25 · Lifecycle: remove, forget, replace · CH
- **Depends on:** U24.
- **Files:** `src/features/tablet/Lifecycle.tsx`, `src/features/board/ReplacementOffer.tsx`, `src/state/commands/lifecycle.ts`, `e2e/parity/T{4,5}.spec.ts`.
- **Accept:** rows T4–T5 pass. `STD` passes.

### U26 · Measure stepper · CH
- **Depends on:** U15, U08.
- **Files:** `src/features/measure/**`, `src/features/tablet/MeasureEntry.tsx`, `src/state/commands/measure.ts`, `e2e/parity/M{1..3}.spec.ts`.
- **Do:** a vertical stepper in the right column (Direction C §5). The steps are:
	1. Model (`tablet-assignments`).
	2. Screen and bezels, with model values pre-filled.
	3. Ruler check (optional). The app shows `rulerUrl` for the tablet, sends POST `calibration-check`, and invalidates `RulerReview` when the device, viewport or inputs change.
	4. Save: PUT `displays`, then PUT `calibrations` with `viewport_guard`.
	Advanced fields sit behind one disclosure in the last step. Preview draws the entered dimensions on that tablet. Moving between steps never saves.
- **Accept:** rows M1–M3 pass. `STD` passes.

### U27 · Server sheet · CM
- **Depends on:** U15.
- **Files:** `src/features/server/**`, `e2e/parity/V{1..3}.spec.ts`.
- **Do:** a SideSheet with three sections. Joining: tablet URL, QR `<img src="/api/v3/join-qr">`, Copy link. Health: `healthz`, `diagnostics`, Verify (`?verify=1`) and Download JSON (Blob plus `<a download>`). Backup: facts only. The experimental opt-in switch also lives here (U30 reads it).
- **Accept:** rows V1–V3 pass. `STD` passes.

### U28 · Next step card and first run · CM
- **Depends on:** U23.
- **Files:** `src/domain/nextStep.ts`, `src/domain/nextStep.test.ts`, `src/features/nextstep/**`, `e2e/parity/D{7,8}.spec.ts`.
- **Do:** `nextStep(store)` returns the first match in this order:
	1. Uncertain command.
	2. Server unreachable.
	3. Draft conflict.
	4. Tablet offline or wrong content.
	5. Replacement offer.
	6. Setup step from `setupProgress` (`operator-workspace.js:59-66`): add a tablet, arrange, show an image.
	7. `null`.
- **Accept:** `npx vitest run src/domain/nextStep` covers each branch. Rows D7–D8 pass. `STD` passes.

### U29 · Conflict, uncertain, unreachable, unsaved · CH
- **Depends on:** U16, U22.
- **Files:** `src/features/conflict/**`, `src/features/onwall/NotConfirmed.tsx`, `src/features/header/SignedOut.tsx`, `src/state/commands/refresh.ts`, `e2e/parity/D{3..6}.spec.ts`, `e2e/parity/C9.spec.ts`, `e2e/parity/X14.spec.ts`.
- **Do:** implement the §4.5 banner semantics and the On wall "Not confirmed" state with Refresh status. When the server is unreachable, every write control is disabled with the reason. Add a `beforeunload` guard.
- **Accept:** rows D3–D6, C9 and X14 pass. `STD` passes.

### U30 · Playlist and playback · CH
- **Depends on:** U15, U27.
- **Files:** `src/features/playback/**`, `src/features/preview/usePlaybackAction.ts`, `src/state/commands/playback.ts`, `src/state/drafts/playlist.ts` (fill in the U11 stub), `e2e/parity/P{1..3}.spec.ts`.
- **Do:**
	- `final.html` puts playback in the Server panel (state `playback`). Mount it where the spec says. It appears only when opted in. It uses `/media` and edits items: dwell shown in seconds and sent as `dwell_ms` from 1000 to 600000, loop, reorder with Move up and Move down buttons, and remove with a single undo.
	- PUT `playlist` sends `If-Match: <PlaylistEtag>`.
	- Transport: Start (with policy and exclusions, confirmed in a ModalDialog), Pause and Resume, Stop, Retry, Next and Previous. Each sends `If-Match: <PlaybackVersion>` except Start.
	- Poll every 1 s when opted in and visible.
- **Accept:** rows P1–P3 pass. `STD` passes.

### U31 · Design rules, accessibility, screenshots · CM · needs spec
- **Depends on:** U16–U30.
- **Files:** `e2e/parity/X{1..6}.spec.ts`, `e2e/parity/X{8..13}.spec.ts`, `e2e/parity/X15.spec.ts`, `e2e/design-rules.spec.ts`, `e2e/__screenshots__/**`.
- **Do:**
	- Port `docs/redesign/mockups/src/audit.py` checks into `design-rules.spec.ts`: rendered font sizes are only the spec's scale; margins, padding and gaps use only the spec's spacing scale; every enabled control shows a focus-visible ring.
	- Port `operator_accessibility.py` `native_keyboard` and `responsive` (200% zoom and enlarged text).
	- Take baselines for every state in the `final.html` `STATES` list except `components`: main, selected, arrange, measure-model, measure-size, measure-ruler, measure-review, firstrun, loading, offline, unreachable, uncertain, conflict, server, data, playback and library. Each at 390, 820 and 1440, light and dark. Compare each against the matching mockup state by eye and record any intended difference in the commit message.
- **Accept:** rows X1–X6, X8–X13 and X15 pass. `npx playwright test e2e/design-rules.spec.ts` passes. The owner approves the screenshot set, recorded in the commit message. `STD` passes.

### U32 · PARITY GATE · CH (review, no feature code)
- **Depends on:** U31.
- **Files:** `docs/redesign/05-parity-report.md`.
- **Do:** run every gate, plus a WebKit pass of `e2e/parity/{C,A}*.spec.ts` (`--project=webkit-desktop`). Record exact counts, durations and tool versions. If the owner's server on port 8012 is running, also open `http://127.0.0.1:8012/controller/app/` with the four saved tablets online (the scratchpad `tour.py` method) and record screenshots, read-only.
- **Accept:**
	- `grep -rn "test.fixme" e2e | wc -l` prints `0`.
	- `make app-check` passes. `make app-e2e` passes.
	- From the repo root, `make test` and `make sim` pass with the same pass and skip counts as before U01.
	- The scenario index is complete. From the repo root, this prints nothing:
		```sh
		{ for f in first_run_acceptance redesign_acceptance _redesign_scenarios _redesign_edge_cases renewal_acceptance operator_accessibility; do grep -oE '^def [a-z][a-z_0-9]*\(rig' simulator/browser/$f.py; done; grep -oE '^def phase_[a-z_]+' simulator/browser/readiness_acceptance.py; } \
			| sed -E 's/^def //; s/\(rig$//' | sort -u | while read -r n; do grep -q "\`$n\`" docs/redesign/04-build-plan.md || echo "UNMAPPED $n"; done
		```
	- G7: `git diff --stat <U01 base commit> -- main.py tabletwall frontend/client` prints nothing.
	- **This is the point of feature parity.** U33 and U34 start only after this.

### U33 · Retarget incidental drivers · CM
- **Depends on:** U32.
- **Files:** `simulator/browser/_api.py` (new), and the ten drivers in the "controller is incidental" row of §6, plus `controller_run.py`, `video_run.py`, `video_transitions_run.py` and `reconnect_exclusions_run.py`.
- **Do:** replace each `goto(… "/controller/physical.html")` flow with `_api.py` calls (`httpx` against the rig's base URL, with the operator `Origin` header and `If-Match` from GET config). Keep every tablet-side and server-side check.
- **Accept:**
	- `grep -ln "physical.html" simulator/browser/{field_run,group_recovery_run,recovery_acceptance_run,recovery_run,health_run,image_efficiency,fleet_soak,audit_round,experience_acceptance,decode_probe,controller_run,video_run,video_transitions_run,reconnect_exclusions_run}.py` prints nothing.
	- Each driver run before and after the change reports the same named checks and results. Store both reports in `docs/redesign/05-parity-report.md`.

### U34 · SWITCH-OVER · CH
- **Depends on:** U33.
- **Files:**
	- Delete the old physical stack: `frontend/controller/{physical.html,physical.js,physical-*.js,operator-*.js,operator-*.css}`. The new `index.html` links no stylesheet. Delete `frontend/controller/fonts/` only if `rg -l SchibstedGrotesk frontend/controller` then prints nothing.
	- Add `frontend/controller/redirect.js`. Rewrite `frontend/controller/index.html` and add a new `physical.html`, both of which load `redirect.js`.
	- Delete every `tests/*.test.js` that `require`s a deleted file. Get the list from `grep -l "frontend/controller/\(operator\|physical\)" tests/*.test.js`. Edit `tests/controller_modules.test.js` to drop only its `physical.js` sections.
	- Edit `tests/test_api.py:58`, `tests/test_ingress.py:553`, `tests/offline_probe.py:25`, `tests/test_hotspot.py:290`, `tests/test_operator_backend.py:33` and `deploy/hotspot.py:187,254,374`. The new URL is `/controller/app/`, and `physical.html` must still return 200 because it is the redirect.
	- Delete the drivers marked "Rewritten" or "Retired" in §6, and their `test_*.py` self-tests.
	- Delete the `src/**/*.diff.test.ts` files.
- **Accept:**
	- `make test`, `make sim`, `make app-check` and `make app-e2e` pass.
	- `rg -l "physical\.js|operator-session|physical-stage" frontend tests deploy simulator` prints nothing.
	- `e2e/parity/X7.spec.ts` passes: `/controller/?a=1#b` and `/controller/physical.html?a=1#b` both end at `/controller/app/?a=1#b`.
	- `uv run --group browser python simulator/browser/readiness_acceptance.py --artifacts <dir>` passes its `experimental.html` part (done: 111/111, see 05-parity-report.md).

### U35 · Docs after switch-over · DS
- **Depends on:** U34.
- **Files:** `README.md`, `docs/field-guide/GUIDE.md`, `deploy/IMAGE-WALL-RUNBOOK.md`.
- **Do:** replace each `/controller/physical.html` with `/controller/app/`. Run `make guide`.
- **Accept:** `rg -n "controller/physical.html" README.md docs/field-guide deploy` prints nothing. `make guide` exits 0.

## 8. Parity matrix

Each row is one Playwright test, written by U04b and filled in by the named unit. Source names the old evidence the row replaces. Each row lives in `e2e/parity/<ID>.spec.ts`. Prefixes: D discovery and realtime, S status, C content, A arrangement, T tablets, M measure, V server, P playback, X shell and quality.

| ID | Behaviour (pass condition) | Source | Unit |
|---|---|---|---|
| D1 | A tablet that opens `/client/` appears on the board within 2 s, and the setup step advances | `first_run_acceptance` S0–S1 | U23 |
| D2 | `device_offline`, `device_online` and `device_removed` update the board. An open draft and the focused field are unchanged | renewal `status_truth`, `operator_regions_updates` | U23 |
| D3 | A second controller's write marks the ETag stale. With a dirty draft, the conflict banner appears. Use theirs discards. Keep mine re-guards, and the next Apply succeeds | edge `second_operator` | U29 |
| D4 | Server restart (new generation): the new snapshot is adopted, drafts are kept, and a conflict is raised if the layout changed | renewal `_restart_server`, `server_stop` | U29 |
| D5 | Server stopped: On wall says "Server unreachable", every write control is disabled with that reason, and the page recovers on restart | `operator_unreachable`, renewal `server_stop` | U29 |
| D6 | A late or out-of-order read never overwrites newer state | edge `stale_reads`, `late_mutation`, `operator_late_join` | U29 |
| D7 | First run: empty wall, then join card with QR and link, then arrange step, then show step, then the card disappears | `first_run_acceptance` S0–S3 | U28 |
| D8 | The Next step card shows the highest-priority problem and its action works | new (Direction B card) | U28 |
| S1 | Board status matches `tabletState` for displayed, stale (evidence older than 15 s), offline, excluded, identifying, unplaced, wrong content and missing tablet | renewal `status_truth`, edge `old_paint`, `missing_live` | U23 |
| S2 | The header summary reads "N of M showing", and it is the only status sentence on the page | renewal `status_truth` (`#wall-health`) | U23 |
| S3 | Status re-evaluates on the 1 s tick without any server event | `physical.js:3115-3121` | U23 |
| S4 | Within 2 s of a tablet going offline, the header names it, its board row says Offline, its stage tile shows an Offline label, and the board order does not change | `composition_gates` G4 | U23 |
| C1 | Selecting an image changes Preview only: 0 writes, On wall unchanged | renewal `guarded_show_focus` | U16 |
| C2 | Show on wall sends exactly 1 PUT `/api/v3/scene` with `If-Match` equal to the ETag at selection, and no layout write. All tablets reach `displayed`, and On wall updates | renewal `guarded_show_focus` | U16 |
| C3 | Show after another controller changed the wall gets a 412. The selection is kept, and Rebuild preview then Show succeeds | edge `stale_scene` | U16 |
| C4 | Fill and Fit, and the background colour, reach the tablets (pixel check). The crop text matches `fitTransform` | renewal `images_workbench` | U16 |
| C5 | Focus after Show stays on the trigger, or moves as `operator-content.js:536-558` does | renewal `guarded_show_focus` | U16 |
| C6 | Upload: progress, a refusal message, and an uncertain state on timeout, 500 or malformed JSON. Inventory order is kept. Upload is never shown automatically. Disabled when uploads are off | edge `upload_timeout`, `upload_ambiguous`, `upload_unreadable`, `inventory_order` | U17 |
| C7 | Saved content: an invalid name sends 0 requests. Save, replace, delete, and recall then Show work | renewal `saved_name_rule` | U18 |
| C8 | Test patterns (grid, black) and colours (all tablets, one tablet) reach the tablets | renewal `pattern_grouping` | U19 |
| C9 | A timeout, 5xx or unreadable response on Show gives "Not confirmed". Further writes are refused until Refresh status | edge `durable_uncertainty`, `batch_uncertain` | U29 |
| C10 | A missing applied image keeps the geometry, shows the image as unavailable on both monitors, and recovers through Add image, Preview and Show | `_redesign_scenarios` `edges` | U16 |
| A1 | Grid preview then apply for 1×3, 2×3, 3×2, 2×2 with a trailing hole, and an explicit order. Preview sends 0 durable writes. Apply sends 1 POST `/api/v3/grid` | renewal `layout_foundation` | U21 |
| A2 | A refused grid (capacity, changed connection or viewport) shows the reason and keeps the inputs | edge `refused_grid` | U21 |
| A3 | Drag, nudge, rotate, resize and snap in Edit layout. Each gesture is one undo entry, history holds 80, and Esc cancels | edge `pointer_drag`, `snap_spacing`, `history_ownership` | U22 |
| A4 | Logical: fixed and fit-to-tablets sizing, pack, tile, custom bounds, rotate (with bezels rotated). Physical: 0/90/180/270 and arbitrary angles, nudge, participation off (bounds unchanged), mixed models | `_redesign_scenarios.py:469-490` (`parity`), edge `mixed_models`, `measured_wall` | U22 |
| A5 | Saved arrangements (logical and physical, invalid entries listed): preview, recall with a kind-change confirmation, return point shown, save, replace, delete | `_redesign_scenarios` `parity` | U20 |
| A6 | Empty wall needs confirmation and sends 1 POST `/api/v3/layout/clear` | `operator_clear_review` | U20 |
| A7 | Apply arrangement sends 1 PUT with the ETag from the first edit, and no scene write. On wall changes only after the response | `_redesign_scenarios` `parity`, `edges` | U22 |
| A8 | Grid membership: an intentional exclusion and a manually entered size survive a tablet reconnect. A tablet that joins after an edit is offered through Include and is never added silently | `_redesign_scenarios` `edges` | U21 |
| T1 | Rename (trimmed, at most 80 characters), model assignment, Identify, Retry image and Reconnect each send 1 request, and their results show | edge `command_variants`, renewal `tablet_facts` | U24 |
| T2 | Form drafts are kept per device when switching tablets and when a remote update arrives | `operator_forms`, `operator_subject_saves` | U24 |
| T3 | Batch commands report completed, untouched, conflict and uncertain correctly | `_redesign_scenarios` `batch`, edge `batch_selection`, `operator_batch` | U24 |
| T4 | Remove placement, and Forget (offline only, impact shown, explicit acknowledgement) | `_redesign_scenarios` `review_forget`, edge `forget_reconnect` | U25 |
| T5 | Replacement: same and different hardware, saved-layout choices, label and number transfer, new-connection and digest guards | edge `replacement_fixture`, `different_hardware`, `replacement_connection`, `replacement_digest` | U25 |
| T6 | Wake-lock reports show per tablet (held or denied) and as a fleet power summary, with the help text from `operator-stage.js:46-48` | renewal `first_wall`, `tablet_facts` | U24 |
| M1 | Saving a profile appends a revision. The active layout's `profile_revision` pins do not change | renewal `measured_blockers` | U26 |
| M2 | The ruler check writes nothing. Its review is invalidated when the viewport or inputs change, and a stale review cannot be saved | `physical_calibration`, renewal `measured_blockers` | U26 |
| M3 | Calibration save with a mismatched viewport gets 409, and the message names the fix | `main.py:2005` | U26 |
| V1 | The Joining section shows the tablet URL, QR and Copy link. Without a tablet origin it says why | `readiness_acceptance` join, `operator_readiness` | U27 |
| V2 | Health shows `healthz` and diagnostics. Verify runs `?verify=1`. Download saves the JSON | `health_run` | U27 |
| V3 | Backup facts show the last manifest and restore rehearsal, or "not recorded" | `operator_readiness` | U27 |
| P1 | Opt-in shows the playlist controls. Editing and saving the playlist sends `If-Match` with the playlist ETag. A stale ETag gives 412 and keeps the edits | `controller_run` F3 | U30 |
| P2 | Start (with policy and exclusions), Pause, Resume, Next, Previous, Retry and Stop each send the playback version. Status updates every 1 s only while visible | `controller_run` F3–F4, `reconnect_exclusions_run` | U30 |
| P3 | Without opt-in: no `/api/v3/playback` polling, and no playlist controls | `physical.js:3122-3123` | U30 |
| X1 | G1 and G1b thresholds from `composition_gates.py:29-33`: at 1366×768 and 1280×800 the preview stage covers at least 45% of the viewport, the wall fills at least 90% of it, and the drawn 3×2 wall covers at least 40%. The stage box drifts at most 0.02 across all states at each width. The phone preview stays pinned | `composition_gates` G1, G1b | U31 |
| X2 | axe reports 0 violations, for every state, at 390, 820 and 1440, in light and dark | `operator_accessibility` | U31 |
| X3 | Every action is reachable by keyboard. Focus is visible on every control. Dialogs return focus | `operator_accessibility` `native_keyboard` | U31 |
| X4 | 200% zoom and enlarged text leave no clipped controls and no horizontal page scroll | `operator_accessibility` `responsive` | U31 |
| X5 | Screenshots match the approved baselines | new | U31 |
| X6 | The page makes 0 CSP violations and 0 requests to another origin, so it loads with no WAN | `offline_probe` | U31 |
| X7 | The old entry URLs redirect to `/controller/app/` and keep the query and hash | `operator_accessibility` `entry_recovery` | U34 |
| X8 | With an image or arrangement draft open, the primary action is fully inside the viewport at all seven `composition_gates.py:26` viewports | `composition_gates` G2 | U31 |
| X9 | At most one primary-styled button is visible per view, with or without a draft | `composition_gates` G3 | U31 |
| X10 | On an empty wall at 1280×800, the join address and Add tablets are inside the first viewport | `composition_gates` G5 | U31 |
| X11 | No horizontal page overflow at the seven viewports. At 390×844, 320×740 and the short sizes 844×390, 667×375, 1024×600 and 1280×600, regions do not overlap and every control can be reached and clicked, at 100% and 200% root text | `composition_gates` G6, G8, `operator_accessibility` `inspect_layout` | U31 |
| X12 | Under `pointer: coarse`, every control is at least 44 px tall, and a touch sweep reaches every required control | renewal `touch_coverage`, coarse pages at `renewal_acceptance.py:1667`, `:2544` | U31 |
| X13 | Long Unicode tablet and image names stay readable at every width. A missing thumbnail shows a fallback | `operator_accessibility` `visual_states` | U31 |
| X14 | Before the first authoritative config arrives, the page shows a loading state and never an empty wall | `operator_accessibility` `loading_workspace` | U29 |
| X15 | Hover, selected and pressed text, and the keyboard focus ring, meet contrast on the real elements. axe does not check these states | `operator_accessibility` `interaction_contrast` | U31 |

### Scenario index

Every scenario in the rewritten drivers maps to rows above. U32 proves the index is complete (see its **Accept** line). Names are function names, except the composition gates.

| Driver | Scenario → rows |
|---|---|
| `first_run_acceptance` | `main` → D7 |
| `redesign_acceptance` | `first_wall` → D7; `disabled` → C6; `image_negatives` → C6, C10; `precise_measurement` → M1, M2; `race_suite` → D3, D6; `recovery` → A5, T4; `corrections` → X3, T1 |
| `_redesign_scenarios` | `review_forget` → T4; `parity` → A4, A5, A7; `edges` → A7, A8, C2, C10, D3, T2, T4, T5; `batch` → T3 |
| `_redesign_edge_cases` | `second_operator` → D3; `pointer_drag`, `snap_spacing`, `history_ownership` → A3; `command_variants` → T1; `batch_uncertain` → C9, T3; `batch_selection` → T3; `mixed_models`, `measured_wall` → A4; `stale_reads`, `late_mutation` → D6; `old_paint`, `missing_live` → S1; `upload_timeout`, `inventory_order`, `upload_ambiguous`, `upload_unreadable` → C6; `stale_scene` → C3; `different_hardware`, `replacement_connection`, `replacement_digest` → T5; `forget_reconnect` → T4; `durable_uncertainty` → C9; `refused_grid` → A2. Helpers with no checks of their own: `ids`, `quick_wall`, `show_supplied`, `replacement_fixture` |
| `renewal_acceptance` | `status_truth` → S1, S2; `guarded_show_focus` → C1, C2, C5; `saved_name_rule` → C7; `pattern_grouping` → C8; `layout_foundation` → A1; `images_workbench` → C4; `first_wall` → D7, T6; `tablet_facts` → T1, T6; `measured_blockers` → M1, M2; `server_stop` → D4, D5; `touch_coverage` → X12 |
| `operator_accessibility` | `native_keyboard` → X3; `entry_recovery` → X7; `visual_states` → X13; `loading_workspace` → X14; `interaction_contrast` → X15; `responsive` → X4; `inspect_layout` → X11. Dropped: `native_capabilities`, because it only records what the headless browser cannot do (native zoom, IME, screen reader) and asserts no app behaviour |
| `composition_gates` | G1, G1b → X1; G2 → X8; G3 → X9; G4 → S4; G5 → X10; G6, G8 → X11; G7 (backend and renderer unchanged) → U32 **Accept** |
| `readiness_acceptance` | `phase_start` → V1; `phase_tablets` → D1; `phase_pinned_health` → S1, T6; `phase_logical_grid` → A1; `phase_physical_grid` → A1, A4; `phase_content` → C2; `phase_fit` → C4; `phase_failure` → S1; `phase_label` → T1; `phase_restart_identify` → D4, T1; `phase_rebind_preview` → T5; `phase_return_point` → A5; `phase_fence` → D3; `phase_uploads` → C6; `phase_playback` → P2; `phase_drill` → T1 |

## 9. Risks and open questions

**Owner decision, 2026-11-17 (X1 / G1b).** On laptop screens (1366×768, 1280×800) the drawn 3×2 wall must cover at least 25% of the viewport, not the old 40%. Measured: about 30–32% at 1366×768 and 26–37% at 1280×800. The preview stage still covers at least 45%. Reason: Direction C keeps the On wall view and tablet list always visible; reaching 40% would mean hiding that column below 1440px. The X1 test title keeps the original row text; its assertion uses 25%.

**Risks**

| Risk | Mitigation |
|---|---|
| The rewrite loses a behaviour that no test pins | Differential tests on every ported pure module. Every scenario in the rewritten drivers maps to §8 rows through the scenario index, and U32 checks that mechanically. The old console stays live until U32 is green. |
| Session semantics drift: double writes, lost uncertain latch, socket per component | The session is created once outside React. Its tests are ported. U04 has a differential test against the old session. The `writes(page)` fixture counts every mutation in e2e. |
| Owner default 1 changes behaviour on purpose (On wall shows server truth during a conflict, not `base`) | Row D3 asserts it. U15 states it in the UI with the tally labels. |
| The build output in git diverges from the source | `make app-check` fails on any diff. Only the merge step commits the output. Node and the lockfile are pinned. |
| Tailwind v4 needs Safari 16.4 or Chrome 111 | Operators use current Chrome and Safari (redesign brief). Tablets never load this app. |
| The spec is not ready when U14 should start | U01–U13 do not need the spec. U14, U15 and U31 are marked **needs spec**. |
| The e2e suite is slow (real tablets, real server) | Worker-scoped servers, 2 workers, and fixtures placed through `api` instead of the UI. The playback rows run in their own project. |
| Direction C splits the screen between Preview and On wall, so the preview may miss G1's 45% area at 1366×768 (the directions doc measured 46% only at 1440×900) | U15 measures it first. If the spec's layout cannot meet it, the owner approves a lower threshold in writing before U31. Never lower it silently. |
| shadcn defaults (outline variants, borders on every container) contradict the owner's feedback | U14 restyles the primitives before any screen uses them. `design-rules.spec.ts` checks the scale. U31 includes owner review. |

**Open questions** (a default is given for each, and the owner may change it)

1. **Is `experimental.html` part of "the old controller"?** It is a separate compatibility editor (`controller.js`, 3,458 lines). `readiness_acceptance.py:812` and `simulator/browser/run.py:1036` drive it, and `tests/test_api.py:59` pins it. Default: keep it untouched, and decide its removal separately.
2. **Is playback in parity scope?** Default: yes, as U30, because the brief says every current feature keeps working. If the owner drops it, delete rows P1–P3 and U30, and leave playback drivers on REST (U33).
3. **401 handling.** Default: a "Signed out" header state with a sign-in link (§4.3). This is new behaviour, small, and covered by the U01 auth smoke.
4. **Reconnect timing.** Default: keep the fixed 3 s for parity. Jittered backoff (0.5 s to 5 s, as the tablet client does) is a one-line change in `sync.ts`. Do it only if the owner asks.
5. **Grid "Keep mine".** Default: run the grid preview again with the same inputs. The other option is to require the operator to re-preview by hand.
6. **Fonts.** Default: Atkinson Hyperlegible Next, as the directions doc proposes. If `03-visual-spec.md` picks another face, U14 follows the spec.
