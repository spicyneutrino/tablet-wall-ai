# Migration options, tooling and delivery mechanics

Recommendation: **B, incremental TypeScript and Vite, followed by bounded React islands**. Start with C's checking discipline. Preserve the existing transport, session and geometry code. Do not rewrite the controller or migrate the tablet runtime to React. Direction B is a UX decision that can ship in vanilla first; it must not wait for framework conversion.

## Evidence and limits

Verified from this checkout:

- `main.py:632–656` mounts `frontend/client` and `frontend/controller` through `RevalidatedStaticFiles`. Every static response gets `Cache-Control: no-cache`; ETags permit revalidation. There is no frontend build integration in these mounts.
- `frontend/controller/physical.html:10–13,1145–1163` explicitly orders three stylesheets and classic scripts, with per-file `?v=` tokens. The theme script runs early. Preserve early theme application to prevent a light flash.
- `Makefile:19–40` starts Python directly through uv; Node is required for tests, not startup. `pyproject.toml:1–28` declares Python, browser and documentation dependencies. A repository search found no package.json outside node_modules.
- `deploy/hotspot.py:285,359` starts processes rooted at the checkout and launches uvicorn. `deploy/tablet-wall.service.example:40,81` describes checkout-root operation and uv sync. These are runtime launchers, not an existing Node artifact pipeline.
- `deploy/tablet-routes.caddy:9–20` admits exact client filenames. `/controller` and the operator socket are intentionally outside the tablet listener. A new tablet chunk URL will fail unless explicitly added to the allowlist.
- `tests/test_asset_cache.py:1–8` and its tests cover uploaded/curated image validation, content identity and filesystem freshness. **They do not test frontend version tokens.** Keep those security/freshness tests unchanged. Static HTTP assertions live in `tests/test_api.py:22–51`; page-to-asset wiring assertions begin at `tests/test_api.py:53`. Tablet token assertions exist in `tests/client_image.test.js:5394–5395`.
- `frontend/controller/operator-session.js:14–40,97–124` already provides a frozen cached snapshot, subscriptions with unsubscribe, guarded requests, reconciliation and lifecycle. `physical.js:246–292` bridges this session into the older mutable UI state. UI drafts, selection and viewport remain local (`physical.js:192–220`); `renderAll` imperatively updates many regions (`physical.js:934–950`).
- VM tests depend on globals and source paths, for example `tests/operator_workspace.test.js:25` and `tests/operator_physical_stage.test.js:4–7`. `tests/operator_wall_status.test.js:54` even slices function source. Bundling everything at once would cause avoidable test churn.
- Shared tokens already cover semantic colors, type, spacing and sizes (`operator-tokens.css:10–71`) and dark mode through media queries and `data-theme` (`operator-tokens.css:74–130`).

This is a source-grounded proposal, not an implementation or rendered UX verification. No app server, browser session, test suite or physical tablet validation was run. Root AGENTS.md is absent in this checkout; the supplied session instructions and COMMON.md were read. Impeccable context reported no PRODUCT.md or DESIGN.md. The explicit shared brief and existing tokens supply product context for this scoped report; no project documents were created. Actual operator browser versions and oldest Android WebView are unknown.

## 1. Options for this codebase

Scores are qualitative engineering judgments, **5 is best on every axis**. For risk, test churn and complexity, 5 means least risk/churn/complexity. They are not measured benchmark results.

| Criterion | A. Full controller rewrite | B. Incremental modules and islands | C. Improve vanilla |
|---|---:|---:|---:|
| Safety of existing behavior | 1 | 4 | 5 |
| Low test churn | 1 | 4 | 4 |
| UX payoff, Direction B and later | 5 | 5 | 3 |
| Low bundle/runtime cost | 2 | 3 | 5 |
| One or two engineers' sustained velocity | 2 | 4 | 4 |
| Simple deployment | 2 | 3 | 5 |
| Offline hotspot reliability | 3 | 4 | 5 |

**A. Full React rewrite.** Clean component ownership and consistent forms could eventually simplify large inspectors and stepped measurement flows. But the rewrite must reproduce draft conflicts, uncertain completion, reconnect fences, calibration, all arrangement variants and physical scaling together. Tests based on VM-loaded scripts would change across the controller at once. React does not fix hierarchy by itself. A parallel implementation also doubles behavior maintenance. Runtime packages are manageable on operator phones, but this incurs build and packaging work immediately. An offline bundle is possible, but every omitted chunk becomes a field failure. Reject A both on cost and because COMMON.md explicitly excludes rewrites.

**B. Strangler.** Introduce build tooling without changing transport or geometry. Convert pure modules and replace one independently owned DOM region at a time. Direction B's Measure flow, inspector and image strip become useful component boundaries. Browser acceptance stays authoritative while VM tests migrate only with their owning region. Costs include temporary CSS coexistence, adapters and dual mental models; budget removal of each replaced renderer in the same phase. Early total bytes can increase because React and legacy code coexist. One React runtime across roots, selective dependencies and lazy optional tools limit that cost. No claim of a size or performance improvement is justified before measurement.

**C. Vanilla improvement.** JSDoc, `// @ts-check`, `allowJs/checkJs` plus `tsc --noEmit`, ES modules, event cleanup and a tiny DOM helper can preserve the simplest runtime and delivery. It can implement Direction B fully. However, as stepped forms and responsive inspectors expand, repeated imperative DOM synchronization remains costly. Keep helpers limited to repeated element creation/binding; do not build a private virtual DOM. C is the right stopping point if the team cannot own Node build artifacts or expects little subsequent UI work. Given the owner's preferred stack and continued UI work, use C as preparation for B rather than a permanent commitment.

## 2. Recommended delivery mechanics

### Files and reproducible artifacts

Proposed layout:

- `frontend/controller-src/` owns package.json, a lockfile, tsconfig, Vite config, canonical HTML entries, modules, React islands and styles.
- `frontend/controller/` remains FastAPI's served directory. During transition it contains untouched legacy files plus a generated `assets/` subdirectory and generated HTML entries.
- Build in a temporary staging directory, copy only enumerated legacy assets into the release tree, then publish the complete output. **Never set Vite emptyOutDir against the mixed source/served directory** while legacy files remain there.
- Canonical `physical.html` moves to the source tree only when the build becomes authoritative. Vite processes its module entry and CSS; legacy classic scripts remain explicitly copied and ordered until migrated. Keep `/controller/`, its redirect entry, `/controller/physical.html` and experimental tools functional. No SPA fallback is required.

For this checkout-based application, initially **commit generated controller output** along with source and lockfile. CI runs a pinned Node version and `npm ci`, typecheck and build, then fails if generated output differs. Review source separately from generated changes. Document a single build command and add Make targets for frontend check/build/dev. Ordinary `make run` and `make hotspot` continue to consume ready static files without invoking npm or reaching a registry. This is deliberate generated-file churn in exchange for preserving today's launch contract. Later, release archives can contain CI-built artifacts without committing them, but only after all deployment paths consume archives and reject missing output. Do not silently require npm on an offline field laptop.

A release includes HTML, all imported chunks, styles, local font/license and icons. Never fetch CDN scripts, web fonts or CSS in the hotspot flow. Validate a prepared checkout with network disabled; dependency preparation is a separate online installation step. Existing uv/Python installation requirements do not disappear.

### URLs and caching

Use Vite `base: '/controller/'` and content-hashed generated filenames, such as `/controller/assets/operator-<hash>.js`. The current `?v=` scheme remains only for unconverted classic assets. Do not add manual tokens to hashed assets. Preserve `no-cache` on HTML and stable legacy filenames. Initially retaining `no-cache` for generated assets too is correct and minimizes backend change; hashing already prevents version ambiguity.

Optional later optimization: only content-addressed generated paths receive `public, max-age=31536000, immutable`, with corresponding static-route tests. Never apply that policy to HTML, stable names, API responses or image validation routes. Change `tests/test_api.py` wiring expectations as individual entries move; add tests that all built HTML references resolve, including CSS imports and lazy chunks, and that HTML revalidates. Leave `test_asset_cache.py`'s media contract intact. Keep tablet token assertions until the tablet itself changes.

Publish assets before new HTML; retain prior release chunks across at least the supported open-session window, or deploy versioned release directories with an atomic switch and retained assets. Otherwise an already open controller may request a deleted lazy chunk. Test upgrade with an old page open and keep the prior complete release for rollback. Avoid a service worker in this migration; HTTP revalidation already solves the present stale-code problem.

### Development and proxy boundary

Run FastAPI on loopback and Vite on a separate loopback dev port. Open Vite's `/controller/physical.html` for HMR. Proxy `/api`, `/devices`, `/device`, `/assets`, `/layouts`, `/scenes`, and whichever readiness/auth/media routes the existing controller actually calls to FastAPI. Proxy `/ws` with `ws: true`, including `/ws/controller`; verify the socket builder uses the page origin so it reaches that proxy. Reserve `/controller/assets` for generated code and `/assets` for image objects.

Preserve Host/Origin/cookie semantics unless a documented backend origin policy requires an explicit development allowance; do not disable admission checks or inject production operator credentials to make HMR work. Check login redirects, protocol selection and cookie behavior separately. Keep Vite unavailable on the tablet listener. Browser acceptance and hotspot rehearsals must also run against the built FastAPI-served output, not just HMR. Vite's [server proxy documentation](https://vite.dev/config/server-options#server-proxy) defines the HTTP and WebSocket options.

### State and DOM ownership

Use the existing **OperatorSession as authoritative server store**, rather than a new event bus or duplicate React fetch layer. Pass its instance and existing command functions explicitly into island mounts. A React hook can use `useSyncExternalStore(session.subscribe, session.view)`. Both functions are stable and `view()` returns the same frozen snapshot until publish (`operator-session.js:19–24,101–103`). These properties meet React's [external store contract](https://react.dev/reference/react/useSyncExternalStore). Do not clone inside getSnapshot or return the mutable legacy state object. Avoid a second socket, polling timer, React Query cache or automatic command retry.

Selection and drafts are a different data shape. Expose a small UI adapter with cached immutable snapshots and explicit commands for selected tablet, pending image, arrangement draft and active inspector. Publish it at actual mutation boundaries, including vanilla handlers; publishing only on server events misses local edits. Do not proxy the whole mutable object or deep-copy geometry every pointer move. Keep drag/viewport transient state in its current owner until the stage migration. Local React state holds uncommitted step fields; durable commands retain session busy, ETag and uncertain-completion guards.

Mount with `createRoot(existingHost).render(<Inspector ... />)` only after removing legacy descendant rendering and listeners for that region. The host ID survives; its children now have one owner. If a pinned role/ID belongs to a child, render that same ID/role/label inside React and remove the original child so duplicates never exist. Do not leave two hidden copies to satisfy tests. `physical.js` currently captures many elements before startup, so cut over that region's capture/binding/render paths before React replaces children. Gate legacy `renderAll` calls for the migrated owner, not arbitrary individual DOM writes.

Keep trigger and status IDs stable when behavior is unchanged. Move VM tests that exercise the replaced renderer to component/browser interaction tests; retain pure model and session tests. Test readiness after asynchronous root render rather than assuming synchronous DOM creation. Unmount on teardown; unsubscribe and remove listeners on pagehide/HMR. Expose a temporary narrow `window.Operator*` compatibility facade only for remaining callers and remove it when its last caller migrates.

## 3. Tailwind, primitives and icons

### Support floor and CSS coexistence

The [official Tailwind v4 compatibility page](https://tailwindcss.com/docs/compatibility) confirms **Chrome 111+, Safari 16.4+, Firefox 128+**. Operator desktops and phones can plausibly meet this, but that is a proposed support policy, not verified fleet evidence. A controller served to an iPadOS 15 operator would not meet it. [Tailwind v3 documentation](https://v3.tailwindcss.com/docs/browser-support) promises current stable browsers rather than a precise historical floor; v3 is not a blanket guarantee for every old browser utility.

Choose **Tailwind 3.4 during coexistence**. It offers straightforward selector scoping and avoids raising the controller floor before inventory. Upgrade the controller alone to v4 only after confirming the above minimum browsers, auditing generated components/CSS and passing rendered tests. Modern controller hardware makes v4 a valid eventual choice, not a reason to combine a CSS engine migration with the first island.

Disable preflight (`corePlugins.preflight: false`) and namespace utilities with a prefix such as `tw-`. `important: '#react-root'` scopes v3 utilities and raises specificity but **does not scope preflight**, component-authored global CSS or Radix portals. A single root selector also fails for multiple separate islands. Prefer a shared `.operator-react` scope applied to every island wrapper and portal container, or explicit generated selectors per host. Keep overlay portal containers within that scope and outside clipping/transform ancestors; test z-index and top-layer interaction. Add a tiny scoped box-sizing/control baseline required by adopted components. Audit existing `operator-workspace.css` element and ID selectors because utility prefixing does not stop legacy rules entering islands.

Use `operator-tokens.css` as the single authority. Map theme colors to full values such as `background: 'var(--bg)'`, `foreground: 'var(--text)'`, `border: 'var(--border)'`, `ring: 'var(--focus)'`; map spacing, font and radii to the corresponding variables. These existing values are full CSS colors, so **do not wrap them with hsl(var(...))** as some shadcn examples do. Adapt copied component aliases and avoid opacity modifiers unless channel tokens are deliberately introduced. Keep the existing early `data-theme` script and system preference rules; token values switch both worlds together. Add a matching dark selector only where a component truly needs a structural dark variant. Do not install a second theme provider.

### Choose primitives by behavior

| Surface | Suitable shadcn/Radix option | Preferred decision here |
|---|---|---|
| Stepped Measure form | Dialog | Native `<dialog>` wrapper with `showModal()` first. Reuse form commands and validation. Radix Dialog is an alternative if a demonstrated requirement exceeds native behavior; never stack native and Radix focus traps. |
| Phone inspector | Sheet, based on Dialog | A modal Sheet fits a deliberately blocking phone inspector. Desktop inspector stays an ordinary aside. Keep draft ownership outside responsive wrappers so resizing does not erase work. |
| Real mutually exclusive panels | Tabs | Radix Tabs when tab semantics and arrow navigation fit. Navigation or actions remain links/buttons, not decorative tabs. Measurement steps are a stepper, not freely selectable tabs by default. |
| Short lists of choices | Select | Native select first for browser keyboard and phone picker behavior. Radix Select only for needed rich content; preserve visible labels and disabled states. |
| Supplemental hints | Tooltip | Radix Tooltip if needed during transition; never hide essential status or instructions behind hover. Accessible names remain on controls. Native popover is an option only with support detection/fallback. |

The retrieved modern-web-guidance `dialog` guide says “Use the native `<dialog>` element” and “DO use `dialog.showModal()` when opening from script.” Apply its native semantics, accessible heading, safe initial focus, explicit close and dirty-form cancel guard. Do not use `open={true}` as a substitute for modal opening. Do not manually add focus trapping to native modal dialogs. The guide treats `closedby` as enhancement and requires fallbacks for popover/invoker features outside the supported browser floor. Under the proposed conservative floor, use script opening rather than requiring new declarative invoker commands. Native popover cannot replace a blocking Measure modal. Bundle any needed fallback locally; no CDN runtime dependencies.

Adopt only the needed shadcn component source and Radix packages. The [shadcn v4 migration guide](https://ui.shadcn.com/docs/tailwind-v4) must not be interpreted as permission to copy v4-only output into v3. Pin compatible recipes, adapt classes/tokens and review generated CSS rather than blindly running the latest generator over the existing page.

Use named Lucide React imports in migrated components, preserve current icon sizes/stroke consistency and accessible button labels. Decorative SVGs get aria-hidden. Do not dynamically import an entire icon-name registry or replace application-specific geometry/QR/status graphics. Replace old inline icons only as their owning region migrates. Lucide still emits inline SVG, so this is consistency and maintenance work, not an assumed bandwidth reduction.

Applied skill rules: Impeccable's **Operate** mode favors precision and familiar patterns; the wall remains dominant and framework adoption adds no decorative chrome. frontend-design's brief-first restraint preserves the incumbent visual language. frontend-ui-engineering's composition and separation of data/presentation lead to small islands backed by the existing session. Its APG, keyboard and responsive rules require focus, labels and phone tests. web-design-guidelines favors semantic controls and accessible icon names. vercel-react-best-practices rules `client-event-listeners`, `rerender-derived-state`, `rerender-use-ref-transient-values`, `bundle-conditional` and `bundle-barrel-imports` favor one subscription authority, bounded subscriptions, imperative drag state and selective/lazy imports. No Next.js, SSR, router or server-component infrastructure is needed.

## 4. Tablet client

Keep `frontend/client` vanilla and separate from controller dependencies, CSS and build configuration. First choice is JSDoc/checkJs with `tsc --noEmit`, which changes no runtime bytes. If TypeScript becomes useful, compile to stable existing `client.js`, `view.js` and `ruler.js` paths. Prefer a small esbuild script with explicit `target: ['safari14', 'chrome87']`, browser platform and an IIFE for a single entry if bundling. Vite can use the same explicit build.target, but its default is too new and HTML/module output needs more deployment coordination. Current [Vite build documentation](https://vite.dev/config/build-options#build-target) has a Baseline default and uses Oxc; do not assume every Vite release uses esbuild internally.

Safari 14 syntax is conservative for iPadOS 15; Chrome 87 is a **proposed tested floor**, not evidence of compatibility with every old Android tablet. Record actual WebView versions before promising support. Android OS version alone does not identify its WebView engine. Neither syntax transpilation nor a legacy plugin adds missing DOM APIs, CSS behavior, codecs, wake locks or dependable suspension/reconnection. Keep existing capability checks and verify any newly introduced APIs independently. Preserve HTTP-LAN operation, UUID fallback and polling/recovery behavior.

No @vitejs/plugin-legacy by default for Safari 14/Chrome 87 targets. Both can consume modern module-era code, and stable IIFE output avoids module loader needs. Add legacy output/polyfills only for a documented older engine that fails the actual runtime; extra loaders and polyfills bring bytes and more public asset paths. Do not ship Tailwind v4 to the tablet, and do not share controller CSS bundles with it. Keep client CSS simple and test it on real iPadOS 15 and the oldest supported Android WebView. If chunks become necessary, explicitly update `deploy/tablet-routes.caddy` and its security tests; never broaden it to all frontend files merely to make a bundler work.

## 5. Phased plan for one or two engineers

Sizes are relative scope, not calendar commitments. S is a focused change, M several coordinated changes, L a multi-flow tranche. Hardware scheduling is external to coding estimates. Each phase ends with working deployed output and can stop without requiring the next phase.

| Phase | Size | Entry | Work and exit criteria |
|---|---|---|---|
| 0. Safety net and inventory | M | Current main plus Direction B ownership identified | Record operator and tablet browser floors. Run make test and existing renewal/composition/accessibility/first-run drivers against main and Direction B separately. Inventory pinned IDs, classic globals, asset references and all arrangement modes. Add missing observable coverage for relative/physical/packed/tiled/custom bounds/rotation, image fit/crop, discovery/join, WS/poll fallback, calibration and recovery. Exit with recorded baseline, explicit existing failures and a rollback artifact. |
| 1. Checking and module boundary | M | Baseline available | Add frontend package/lockfile, pinned Node, allowJs/checkJs noEmit and explicit session/config/draft types. Convert pure model modules incrementally without changing algorithms. Preserve VM adapters only while actual callers need them. Exit with typecheck and existing tests passing, unchanged API behavior and no new tablet runtime. |
| 2. Vite delivery without UI replacement | M | Typed boundary agreed | Build staged controller output, commit artifacts, CI reproducibility check and dev HTTP/WS proxy. Preserve classic ordering and URLs. Exit with FastAPI-built-page smoke tests, all referenced chunks local, static caching assertions and offline hotspot rehearsal passing. |
| 3. First bounded island | S/M | Artifact and session adapter stable | Migrate a small read-only inspector subsection or image-details region, not geometry or the whole Measure form. Establish scope/tokens, createRoot lifecycle and useSyncExternalStore. Remove that region's legacy renderer/listeners. Exit with selection/live updates, keyboard labels, light/dark and phone/desktop rendering verified, no duplicate IDs/listeners/sockets. |
| 4. Direction B regions | L, split into M changes | First island proves ownership model; coordinate with existing Direction B branch | Move Measure steps, inspector and image strip one at a time. Reuse session commands, draft/conflict guards and current geometry. Avoid a simultaneous UX and geometry rewrite. Exit per region with acceptance/browser checks for dirty dismissal, stale status, loading/errors, phone keyboard/viewport and actual built assets. Run physical calibration/image trials before promoting hardware claims. |
| 5. Consolidate only demonstrated value | M | Several independently accepted regions | Remove migrated globals/adapters/legacy CSS selectors; retain still-used experimental and tablet files. Consider larger stage ownership only if justified, with all arrangement/scaling regression gates. Reassess v4 after fleet confirmation. Exit with one owner per region, reproducible offline artifact and no unreferenced generated assets. |

One engineer owns session/delivery and the other owns the current UI region; with one engineer, execute serially. Do not have both change `physical.js` ownership boundaries concurrently. Throughput checkpoint after phase 3: if adapter/CSS/test work costs more than the next UX improvement, keep remaining regions vanilla and deliver Direction B with the established checking/build foundation. React coverage percentage is not an exit criterion.

For each UI phase, run the app and inspect the actual built route with the configured browser tools under browser-harness. Inspect desktop and phone hierarchy, overflow, focus, loading/empty/error states, console warnings and failed requests. Exercise interactions with Playwright and close processes afterward. Existing desktop software evidence cannot replace real tablet calibration, suspend/reconnect and hotspot validation. This report itself does not claim those checks passed.
