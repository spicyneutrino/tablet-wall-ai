# Frontend migration: architecture proposal and plan

Status: proposal for approval. Nothing in this document is implemented yet.
Date: 2026-11-15. Baseline: `main` at `bcc3d48`. Direction B part 1 is in progress on `redesign/direction-b` (uncommitted).

Evidence comes from four read-only audits run against a clean checkout of `bcc3d48`, plus my own baseline runs. The audits are in `audit/` next to this file:

| Report | Scope | Model |
|---|---|---|
| `audit/01-controller-audit.md` | Controller modules, state, DOM contract (478 IDs), tokens, candidate islands | Codex-Personal 6.1 Sol, high |
| `audit/02-client-interfaces-compat.md` | Tablet client, 80 HTTP routes, WebSocket protocol 3, arrangements, iPadOS 15 / old WebView, device validation | Codex-Work 6.1 Sol, high |
| `audit/03-test-safety-net.md` | 42 JS test files, Python tests, browser drivers, gaps, CI gates | Codex-Personal 6.1 Sol, medium |
| `audit/04-options-tooling.md` | Full vs partial vs vanilla, Vite/FastAPI delivery, Tailwind, shadcn, phases | Codex-Work 6.1 Sol, medium |

## 1. Recommendation

**Partial, incremental migration of the controller. Keep the tablet client in plain JavaScript and plain CSS.**

| Option | Verdict | Why |
|---|---|---|
| A. Full React rewrite of the controller | Reject | It would have to reproduce draft conflicts, uncertain-completion fencing, reconnect logic, calibration, physical scaling and every arrangement kind in one cut. 26 of 42 JS test files load source text or slice functions and would all break at once. |
| B. Strangler: types, then Vite, then React islands | **Adopt** | Each step ships on its own and can stop. Direction B's regions (Measure, inspector, image strip, selection surface) become natural component boundaries. |
| C. Stay vanilla, add `checkJs` and modules | Adopt as phase 1 only | It is the safest runtime and could deliver Direction B, but stepped forms and responsive inspectors keep getting more expensive to synchronise by hand. It is also the fallback if phase 3 shows the islands cost more than they return. |

Sequencing (the owner left this open): **ship Direction B part 1 in vanilla now, then migrate**, and do the rest of Direction B *in* the new stack. Reasons:

- Part 1 (stepped Measure dialog, single status summary, first-run fix) is done and passes every suite at baseline. Holding it for a framework would delay the fix the owner asked for.
- Part 2 of Direction B (image strip under the wall, one selection surface instead of chips plus tiles) was tried and backed out. It conflicts with the stage-area gate (G1/G1b) and with roughly 30 browser locators that assume one visible picker per tablet. Those locators get rewritten to role-based selectors in phase 0 anyway, so part 2 is cheaper after that.
- Building a new-framework branch that also changes the UX would be a rewrite in disguise, which the brief rules out.

## 2. What exists today

### Controller (`frontend/controller`)

- **Pages.** `physical.html` is the live console. `index.html` redirects. `experimental.html` plus `controller.js` is an older compatibility editor with its own tests.
- **Code.** 27 JS files and 4 CSS files, loaded as ordered classic scripts with per-file `?v=` cache tokens. Modules publish `window.Operator*` / `window.Physical*` factories. `physical.js` (≈3,200 lines) wires everything and builds an `el` map of captured nodes at load time.
- **State.** `OperatorSession` is the server authority. It holds frozen snapshots behind `view()` and `subscribe()`, serialises commands, applies ETag `If-Match`, fences late reads, and treats timeouts and 5xx on writes as *uncertain*, blocking retry until a refresh. Drafts sit beside it with different owners: the arrangement draft (with 80-step undo), the content selection, grid preview guards, and `tabletForms` keyed by device and group (name, model, profile, calibration). `physical.js` exposes session fields to the old mutable `state` through non-enumerable getters, so spreading or serialising `state` silently drops data.
- **DOM contract.** 478 page IDs are used by JS, and 330 of them are also pinned by tests or drivers. Body attributes (`data-mode`, `data-subject`, `data-stage-mode`, `data-connection`, …) drive CSS. Moving the same node is safe; replacing it with a new node of the same ID leaves stale captured references.
- **Stage.** An SVG wall with keyed diffing, pinned-revision geometry, clip paths, `getScreenCTM` pointer mapping, drag transactions, nudge, rotation and label fitting. This is the hardest part to port and stays imperative until a geometry test matrix exists.
- **Design system.** `operator-tokens.css` holds semantic colours, type, spacing, radii and control heights, with light and dark themes and an early theme script. Recurring patterns: buttons, chips, fact lists, two-column field grids, disclosures, native dialogs (draft resolution, server drawer, and now Measure), gallery, saved-item lists, commit bar.

### Tablet client (`frontend/client`)

- **Files.** One independent classic-script page: `client.js` (identity, registration, WebSocket protocol 3, heartbeat and reconnect, image fetch and decode lifetimes, render acknowledgements, Identify, wake lock, fullscreen, viewport reporting), `view.js` (pure affine math for crop, physical mapping and quarter turns), `ruler.js` (`?calibrate=1` measurement overlay) and `client.css`.
- **Connection behaviour.** Reconnect backs off from 0.5 s to a 5 s cap with jitter. Close code 4409 means another page took over this tablet's identity, so the client stops retrying and shows Take over.
- **Offline.** No service worker. Everything is served from the LAN origin.
- **Hotspot allowlist.** `deploy/tablet-routes.caddy` admits exact client filenames. Any new client file needs an allowlist change and its security tests.

### Backend interfaces

- **Surface.** 80 HTTP routes. The controller uses mainly `/api/v3/*` (config, images, scene, layouts, grid preview and apply, profiles, calibration, lifecycle, readiness, diagnostics). It also uses a few legacy routes for colour and upload.
- **WebSockets.** `/ws/controller?protocol=3` and `/ws/device?protocol=3`.
- **Concurrency.** Config ETag, playlist ETag and playback version are three separate concurrency tokens and must stay separate types.
- **Types.** OpenAPI from FastAPI covers HTTP, but some routes return untyped dicts and need hand-written schemas. WebSocket frames have no schema at all, so they need a fixture schema derived from `PROTOCOL.md`.

### Arrangements that must survive

- **Two persisted kinds.** Logical (relative) and physical (measured).
- **Operations over those kinds.** Grids of any rows and columns with order and allowed trailing holes, preserved-size pack, equal-cell tile, the legacy `/wall/auto` and `/wall/pack` variants (whose rounding differs), fixed and custom bounds including negative origins, fit to tablets or bodies, logical rotate, quarter turns, arbitrary physical mount angles, nudge, participation and session exclusions, reservations, rebind, and saved arrangements with cross-kind return points.
- **Not limited to presets.** 2×2 and 1×4 are only presets.

### Also preserved: playback and playlists

`physical-playback.js` (≈1,400 lines, in the Server drawer) drives playlists and still or video playback. Playback has its own playlist ETag and playback version, plus session exclusions and cohorts. It stays legacy-owned until an island explicitly takes it. Its regression gate is the existing playback unit tests plus `controller_run`, `video_run`, `video_transitions_run` and `reconnect_exclusions_run`, all run at every phase that touches the Server drawer or session.

## 3. Target architecture

```
frontend/
  controller-src/          new: package.json, lockfile, tsconfig, vite.config.ts, src/
    src/session/           typed wrapper over OperatorSession (one socket, one command queue)
    src/api/               types generated from OpenAPI + hand schemas for WS frames
    src/islands/<name>/    React islands, one root per owned region
    src/ui/                shadcn-derived primitives, adapted to existing tokens
  controller/              still what FastAPI serves
    *.js, *.css            legacy files, shrinking over time
    assets/                generated by Vite, content-hashed, committed
  client/                  unchanged runtime; JSDoc + tsc --noEmit only
```

Rules:

1. **One authority.** React reads `OperatorSession` through `useSyncExternalStore(session.subscribe, session.view)`. No second socket, polling loop, React Query cache or automatic retry. A small UI-state adapter publishes immutable snapshots for selection and drafts at real mutation points, including from vanilla handlers.
2. **One owner per region.** `createRoot(host)` only after that region's legacy render and listener code is removed in the same change. Host IDs stay. Pinned child IDs and roles are re-rendered by React, never duplicated. No hidden copies kept just to satisfy tests.
3. **Drafts are not controlled from snapshots.** Inputs keep the current rule: a server update never overwrites a dirty field. Captured guards (`draftBaseEtag`, form baselines, grid preview guard) stay attached to the work they protect.
4. **Delivery stays offline-safe.** Built assets are committed, and CI fails if a rebuild differs. `make run` and `make hotspot` never call npm. No CDN or font fetches. Use Vite `base: '/controller/'` with hashed filenames, keep `?v=` tokens only for the legacy files, and keep HTML on `no-cache`. Keep the previous release's chunks so a page that is already open can still load lazy imports. The dev server proxies HTTP and `/ws` to FastAPI, and acceptance always runs against the built output too.
5. **Styling.**
   - **Tailwind 3.4 on the controller during coexistence.** `preflight` is off, utilities use a `tw-` prefix, and a shared `.operator-react` scope covers every island and portal container.
   - **Theme from `operator-tokens.css`.** Map the existing values directly (`var(--bg)`, not `hsl(var(...))`) so dark mode and the theme script keep working for both worlds.
   - **Tailwind v4 later, controller only.** Only after the operator browser floor (Safari 16.4 / Chrome 111) is confirmed.
6. **Primitives.**
   - **Native first.** Native `<dialog>` with `showModal()` for blocking flows such as Measure, and native `<select>`.
   - **shadcn/Radix where needed.** Only where native behaviour is not enough: a Sheet for the phone inspector, Tabs for real tab panels, Tooltip for supplementary hints.
   - **Lucide icons.** Named imports, replaced only as their region migrates. Application graphics (stage, QR) stay custom.
7. **Tablet client.**
   - **No changes to its stack.** No React, no Tailwind, no shared CSS bundle.
   - **If it is ever built,** use a separate esbuild script that emits the same filenames as a classic IIFE, with an ES2019 syntax ceiling and targets `safari14, chrome87`. No `@vitejs/plugin-legacy` unless a real device needs it.
   - **No Tailwind v4 there.** v4 requires Safari 16.4, Chrome 111 and Firefox 128.

## 4. Phased plan

Each phase ends with working, deployable output and can stop there. Sizes are relative (S, M, L), not calendar estimates.

| Phase | Size | Work | Exit criteria |
|---|---|---|---|
| **B1. Ship Direction B part 1 (vanilla)** | S | Already built: stepped Measure dialog, one header status summary, first-run step fix, Measure trigger near the top of the tablet card. | Suites at baseline (see §6). Owner review, then merge. |
| **0. Safety net** | M | Record the real device inventory (below). Shared 18-tablet fixture manifest. Freeze arrangement DTOs and pixel anchors for every arrangement kind, including all four mount angles, asymmetric bezels, negative origins and holes. Browser characterisation: join → preview → apply → show; polling-only reconciliation; socket reconnect; server generation change; takeover. Visual baselines at 390×844, 820×1180 and 1440×900 for loading, empty, error, selected, preview and Measure steps. Convert the ≈30 picker locators and the ID selectors in the shared driver helper to `getByRole`/`getByLabel`. OpenAPI schema snapshot plus WS frame fixtures. | New tests fail on the regressions they target (proved by reverting). Baseline recorded with the 5 known fractional-width exceptions named, nothing else waived. |
| **1. Types and module boundaries** | M | `package.json`, lockfile, pinned Node. `allowJs` + `checkJs` + `tsc --noEmit` over controller and client. Types for session snapshots, config, drafts and DTOs. Turn source-sliced tests into imports of pure functions before their feature moves. | Typecheck clean. All existing tests green. No runtime bytes changed. |
| **2. Vite delivery, no UI change** | M | Staged build into `frontend/controller/assets/`, never `emptyOutDir` on the mixed folder. Dev proxy. CI reproducibility check. Tests that every built reference resolves locally, with the correct MIME types and caching. | FastAPI-served build passes all suites. Offline hotspot rehearsal passes with WAN disconnected. Tablet assets byte-identical. |
| **3. First island: Saved content list** | S/M | Mount in `#saved-scenes`, owning only its rows. Proves the session hook, guarded commands (`previewScene` with a captured ETag), focus recovery, scoped Tailwind and tokens, light and dark themes, and teardown. Vitest + Testing Library introduced here. | No duplicate IDs, listeners or sockets. Browser suites green. Phone and desktop screenshots reviewed. **Checkpoint:** if adapter, CSS and test work cost more than the UX it bought, stop and keep the remaining regions vanilla on the phase 1–2 foundation. |
| **4. Direction B part 2 as islands** | L, as several M changes | One region per change: (a) image gallery as a strip under the wall. G1 requires the stage to keep the same size in every mode (drift ≤ 0.02), not just ≥45% area and ≥40% drawn wall. A strip that appears only in Content, or collapses, fails G1 at any height. The strip must therefore reserve its height in all modes or sit inside the well's letterbox area; (b) tablet inspector, starting with facts and the name form; (c) one selection surface replacing the chip strip, now possible with role-based tests; (d) Measure steps as React-owned forms reusing `tabletForms` and its guards, with no profile save or layout repin on step navigation; (e) phone inspector as a sheet. | Per region: dirty-dismissal, stale status, loading and error states, phone keyboard and viewport, built-asset run, and real-tablet smoke on both device families. |
| **5. Consolidate** | M | Remove migrated globals, adapters and dead CSS. Decide on the stage only if the geometry matrix fully covers it. Reassess Tailwind v4 for the controller. | One owner per region. No unreferenced assets. Full suites plus a signed real-device matrix. |
| **Client track (parallel, small)** | S each | (1) **Compatibility fix found by the audit:** `client.css` uses `:has()` for the waiting backdrop, which iPadOS 15.0–15.3 and WebView < 105 ignore. Replace it with a root attribute set by existing placement state. Add a `:focus` baseline where `:focus-visible` is missing. (2) JSDoc types and `tsc --noEmit`. No framework. | Before and after captures on real iPadOS 15 and the oldest WebView. Client unit tests green. |

Staffing: one engineer owns session and delivery, a second the current UI region. With one engineer, run the phases in order. Never change `physical.js` ownership boundaries in two places at once.

## 5. Testing and real-device validation

- **Test gates.**
  - **Every phase:** no new failures, no lost checks, no new unexplained skips, no new console or network errors.
  - **Images:** visual diffs sit alongside semantic and geometry assertions, never replace them.
  - **Selectors:** never weaken a selector with `.first()` to hide a duplicate control.
- **Island tests.**
  - **Vitest + Testing Library:** role and label queries, user-event, and StrictMode mount/unmount proving there are no duplicate subscriptions or writes.
  - **Playwright:** legacy page plus island plus FastAPI plus real tablet pages, on the production build.
- **Real devices, every phase that touches output.**
  - **Setup:** a trial install on unused ports with a backup.
  - **Remote inspection:** Safari Web Inspector over USB from a Mac for iPadOS; `chrome://inspect` for Android. A kiosk WebView needs `setWebContentsDebuggingEnabled(true)`.
  - **What to run:** cold join with WAN disconnected; reload and 4409 takeover; logical and measured layouts beyond 2×2 and 1×4 (1×3, 2×3, 3×2, holes, mixed models, 90/180/270 and an arbitrary angle); ruler measurement with a physical ruler (≤2 mm seam target); a second controller forcing a 412; Wi-Fi drop and OS sleep across 20 trials.
  - **Records:** console, network and socket logs, screenshots, photos.
  - Hardware gates stay separate from CI green, and all eight existing hardware gates are still MISSING.

## 6. Current baseline (measured this session)

| Suite | `main` | Direction B part 1 |
|---|---|---|
| pytest | 1,924 passed, 2 skipped | 1,924 passed, 2 skipped |
| Node `tests/*.test.js` | all pass | all pass (3 tests updated to the new contract) |
| renewal_acceptance | 280/285 (5 known fractional-width) | 280/285 (same 5) |
| composition_gates G1–G8 | pass | pass (G2 updated: one summary chip) |
| redesign_acceptance | all scenarios pass | all pass after two driver fixes (parity + precise-measurement rerun: 84/84) |
| readiness_acceptance | 15 failures | the same 15 failures (they predate B; includes a `simulator` import error when run as a script) |
| restoration_acceptance | 36/47, 11 failures | the same 36/47 (it still drives the old five-tab console) |
| operator_accessibility | not run on main | pass |
| first_run_acceptance | not run on main | pass (8/8) |

Driver changes made for B: the shared `_workspace_shell` helper now opens Measure and its step for a field and closes the dialog before switching tasks. Eight `details.open = true` hacks became `open_measure()` calls. One redesign assertion now expects Measure to be modal and to return focus to its trigger. G2 expects one summary chip. The full renewal and gates runs predate the last two helper tweaks (closing order inside `task()`, the discard loop). The scenarios those tweaks touch were rerun and pass.

Readiness and restoration are already red on `main`. Phase 0 should repair or retire them so they can serve as gates.

The test audit's fresh worktree counted 1,909 passed and 3 skipped. The difference from my 1,924/2 is probably environment-dependent skips and collection. It is not resolved, so phase 0 should pin the environment and record exact counts.

## 7. Decisions needed from the owner

Answered 2026-11-15:

- **Fleet:** Pixel C, iPad and iPad mini from about 2014–2015. Tablets keep plain HTML, CSS and JS with no build step. iPad Air 2 and iPad mini 4 stop at iPadOS 15; iPad Air (2013) and iPad mini 2 and 3 stop at iOS 12.5. Until the exact models are confirmed (Settings → General → About), the client floor is Safari 12 on iOS 12.5, not iPadOS 15: no optional chaining, nullish coalescing, `:has()`, `gap` on flexbox, or `aspect-ratio`. The client-compatibility track must audit against that floor.
- **Operator browsers:** Chrome and Safari on a laptop or the server. The controller is not limited by the tablet floor.
- **Built assets:** commit the built controller files.

Still open:

1. **Node in CI and on dev machines.** Node is already needed for `make test`. Confirm a pinned version is acceptable.
2. **Direction B part 1.** Approve and merge before phase 0?
