# Frontend migration regression safety net

Audit of committed checkout `bcc3d48ee2fee78015a4ae7f3a814e02cde14588`. This report proposes tests only. No application or test source was edited. The supplied AGENTS instructions apply; there is no AGENTS.md in this checkout root. COMMON.md was read in full. Evidence below is inspected source unless explicitly labelled execution or proposal.

## Executive assessment

Preserve behavioral assertions, replace fragile loaders before moving their owning feature. Most migration risk is source extraction and VM globals, not the assertions themselves. Keeping every DOM ID cannot save a test that extracts a named function from an IIFE after bundling.

`make test` runs pytest first and then every `tests/*.test.js` in a separate Node process (Makefile:36). Pytest only discovers `tests/`, not simulator self-tests (pyproject.toml:34). Browser acceptance is not a default test gate. Pure arithmetic or fake canvas assertions do not establish rendered-browser or physical seam correctness.

Known baseline supplied by the owner, not rerun here: renewal_acceptance had **5 failures / 285 checks on main**, all **“Exact fractional CSS width ... unproven”**; composition_gates passed. The driver explicitly records fractional-width limitations (simulator/browser/renewal_acceptance.py:212, :1616, :1643). Preserve these exact five limitations in baseline comparison, never waive all layout-foundation failures. G7 in composition_gates is a separate diff check, not browser evidence (simulator/browser/composition_gates.py:9).

## Executed baseline

`rtk proxy make test` exited **0** in this checkout. Pytest reported **1909 passed, 3 skipped, 3 warnings in 94.40s**. All **42 JS files** then completed successfully, including their custom assertion runners and node:test subtests. No single aggregate JavaScript case count is claimed because runners have different reporting formats. Warnings were Starlette's deprecated anyio BlockingPortal alias and two Pillow getdata deprecations. The browser drivers and `make sim` were not run. Test setup created the ignored .venv and normal test caches; tracked git status remained clean. No long-lived server was launched by this audit.

## Classification method and counts

One category per JS file, assigned by its most migration-sensitive harness. (a) means behavior-level with imports whose paths may need adapting; CommonJS is still a mechanical loader change. (b) means direct module imports plus hand-built DOM and structure contracts. (c) means raw source evaluation, function slicing or inherited VM harness. The categories describe current tests, not permanent constraints on the migrated app. Mixed files retain all their assertions when the loader changes.

**42 JavaScript files: (a) 11, (b) 5, (c) 26.** Counts are files, not assertions or parameterized cases. Detailed entries follow. Python and browser inventories use separate counts because neither equals JS file coverage.

Worst offenders are controller_modules (mixed module checks plus physical.js slicing), controller_image_capability (function boundary inferred from indentation), operator_forms, operator_clear_review, operator_regions_updates, operator_saved_actions, operator_wall_status and operator_workspace_composition (source substring boundaries). client_image is the largest shared harness, 5,558 lines, and its VM/fake DOM is inherited by client_identify and client_render_status. Replacing its loader without preserving clock, decode, socket and animation scheduling would lose valuable race coverage (tests/client_image.test.js:689).

## Complete JavaScript file inventory

Each entry lists inspected loader lines, fake-DOM technique, and explicit selector/string assertion evidence. Quoted pins are representative; the evidence list includes the exact assertion lines for that file's structural contracts. These are not real browser DOMs, layout engines, or accessibility trees.

### client_identify.test.js · (c)

Imports startHarness from client_image.test.js, inheriting whole client VM, fake canvas, timers, sockets, image/bitmap and DOM.

Behavior evidence: Identify is plain text, acknowledges shown after a frame, and expiry reveals the latest image; newer Identify replaces the old command and obsolete animation or expiry callbacks cannot clear it; wrong connection, generation, malformed and expired commands do not show; Identify duration ; server clock estimate and writer remaining duration both shorten Identify deadlines; Identify clears on ; resume expires Identify even when the platform paused its performance clock during sleep

Loader evidence:

- `tests/client_identify.test.js:4` `const { startHarness, drain, wallFrame, imageContent, okResponse, assetBlob, route } = require("./client_image.test.js");`

DOM/copy pins:

- `tests/client_identify.test.js:17` `const overlay = h => h.document.getElementById("identify");`
- `tests/client_identify.test.js:23` `assert.equal(h.document.getElementById("identify-number").textContent, "#4");`
- `tests/client_identify.test.js:24` `assert.equal(h.document.getElementById("identify-label").textContent, "North <img src=x onerror=alert(1)>");`
- `tests/client_identify.test.js:50` `assert.equal(h.document.getElementById("identify-number").textContent, "#9");`

### client_image.test.js · (c)

Whole client.js in VM; fake document/canvas draw log, WebSocket, fetch/blob/image decode, storage, timers and animation frames; real view.js math.

Behavior evidence: contain fits once across ${W}x${H}, source ${iw}x${ih}; seam mapping: both tablets draw one global cover of the wall; stale load: an older in-flight asset never paints over a newer one; generation change restarts the load; the old lineage is discarded; a retained picture stays up under an unmistakable loading banner; failure: IMAGE FAILED + short asset id + a retry that works; a replayed wall frame retries the failed asset after a reconnect

Loader evidence:

- `tests/client_image.test.js:66` `const CLIENT_SOURCE = fs.readFileSync(CLIENT_JS, "utf8");`
- `tests/client_image.test.js:69` `const view = require("../frontend/client/view.js");`
- `tests/client_image.test.js:689` `vm.runInContext(CLIENT_SOURCE, context, { filename: "client.js" });`
- `tests/client_image.test.js:5391` `const html = fs.readFileSync(CLIENT_HTML, "utf8");`
- `tests/client_image.test.js:5392` `const css = fs.readFileSync(CLIENT_CSS, "utf8");`

DOM/copy pins:

- `tests/client_image.test.js:1593` `assert.ok(h.texts().includes("NO PLACEMENT"), "the unplaced panel is drawn");`
- `tests/client_image.test.js:1711` `assert.ok(h.texts().includes("IMAGE FAILED"), "the failure panel stands");`
- `tests/client_image.test.js:5493` `assert.equal(recovery.hidden, false, "the mapping refusal has a readable DOM recovery panel");`
- `tests/client_image.test.js:5523` `assert.equal(h.elements.find(el => el.attributes.id === "calibration-recovery").hidden, false);`
- `tests/client_image.test.js:5529` `assert.equal(h.elements.find(el => el.attributes.id === "calibration-recovery").hidden, true,`

### client_render_status.test.js · (c)

Imports startHarness from client_image.test.js, inheriting whole client VM, fake canvas, timers, sockets, image/bitmap and DOM.

Behavior evidence: a successful draw needs a following animation frame; heartbeat refreshes strictly ordered evidence; new tokens at the same revision repaint cached pixels and obsolete animation callbacks cannot report; logical wall-mode handoff and tokenless protocol2 wall frames remain compatible without invented evidence; malformed, wrong connection, mismatched duplicated fields and wrong assets cannot replace evidence; stale decodes, failures and animation callbacks cannot cross token, generation, socket or viewport ownership; hidden invalidates displayed evidence and resume requires a new paint and animation frame; physical image confirms only after drawing; unplaced, calibration, viewport, zoom and unsupported stay explicit

Loader evidence:

- `tests/client_render_status.test.js:5` `assetBlob, route, VIDEO_CALIBRATION, VIDEO_PLAN } = require("./client_image.test.js");`

DOM/copy pins:

- `tests/client_render_status.test.js:109` `assert.equal(last(h).status, "hidden");`
- `tests/client_render_status.test.js:112` `assert.equal(last(h).status, "hidden");`
- `tests/client_render_status.test.js:170` `assert.equal(h.texts().includes("NEEDS CALIBRATION"), false);`
- `tests/client_render_status.test.js:192` `assert.equal(displayed(h).length, 0, "a hidden page cannot claim a painted scene");`
- `tests/client_render_status.test.js:193` `assert.equal(last(h).status, "hidden");`
- `tests/client_render_status.test.js:268` `const action = h.document.getElementById("auth-login");`
- `tests/client_render_status.test.js:507` `assert.equal(h.fetchLog.filter(f => String(f.url).includes("/assets/")).length, fetches + 1,`

### client_view.test.js · (a)

No DOM; pure records, injected API/session doubles.

Behavior evidence: fixture: ; every panel_from_source inverts and round-trips three points; negative or missing bezels and quarter turn 4 are refused; other invalid input is refused; cover and contain share the centre but not the extent; video drift is observed minus target, in both directions; video correction: 50 ms deadband keeps rate 1 and never seeks

Loader evidence:

- `tests/client_view.test.js:16` `const view = require("../frontend/client/view.js");`
- `tests/client_view.test.js:24` `const CASES = JSON.parse(fs.readFileSync(FIXTURES, "utf8")).cases;`

DOM/copy pins:

- No literal DOM/copy pin found in the inspected assertion patterns. Data values and exported API names remain contracts.

### client_wake_lock.test.js · (c)

Whole client.js in VM with null DOM lookups, navigator wakeLock, fake visibility/timers/socket/storage.

Behavior evidence: a secure context without navigator.wakeLock reports unsupported; no navigator at all is unsupported in a secure context; an insecure context reports insecure and never calls the API; insecure wins over unsupported: a plain-HTTP tablet has no API at all; a visible page takes the lock and reports held in the heartbeat; a rejected request reports denied, then retries no sooner than 30 s; a hidden page requests nothing until it becomes visible

Loader evidence:

- `tests/client_wake_lock.test.js:26` `const CLIENT_SOURCE = fs.readFileSync(`
- `tests/client_wake_lock.test.js:143` `vm.runInContext(CLIENT_SOURCE, vm.createContext(sandbox), { filename: "client.js" });`

DOM/copy pins:

- No literal DOM/copy pin found in the inspected assertion patterns. Data values and exported API names remain contracts.

### controller_image_capability.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.ok(start >= 0, name + " exists");; assert.equal(el.alertNoCap.hidden, !(online && lacks), label);; assert.equal(el.alertUnverified.hidden, online && (capable // lacks), label);; assert.equal(el.alerts.hidden, online && capable, label);

Loader evidence:

- `tests/controller_image_capability.test.js:7` `const source = fs.readFileSync(path.join(__dirname, "../frontend/controller/controller.js"), "utf8");`
- `tests/controller_image_capability.test.js:20` `vm.runInContext(source.slice(start, end), context, { filename: "controller.js" });`

DOM/copy pins:

- `tests/controller_image_capability.test.js:39` `assert.equal(tile.capChip.textContent, protocol === 1 ? "Old version"`
- `tests/controller_image_capability.test.js:46` `assert.ok(el.alertUnverifiedText.textContent.includes("offline · " + note), label);`
- `tests/controller_image_capability.test.js:56` `assert.ok(el.alertUnverifiedText.textContent.includes("not in the roster · capability unknown"));`

### controller_modules.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.deepEqual(plain(geometry.normalizePlacement({ x: "2", y: 3, w: 10, h: 20, bezel: { left: "1" } })), {; assert.equal(geometry.normalizePlacement({ x: "invalid" }), null);; assert.deepEqual(plain(geometry.visibleRect({ x: 2, y: 3, w: 10, h: 20, bezel: { top: 1, right: 2, bottom: 3, left: 4 } })), { x: 6, y: 4, w: 4, h: 16 });; assert.equal(geometry.aspectOf(1, 0), null);

Loader evidence:

- `tests/controller_modules.test.js:8` `vm.runInContext(fs.readFileSync(path.join(__dirname, "../frontend/controller", name), "utf8"), context, { filename: name });`
- `tests/controller_modules.test.js:101` `const html = fs.readFileSync(path.join(__dirname, "../frontend/controller", page), "utf8");`
- `tests/controller_modules.test.js:121` `vm.runInContext(fs.readFileSync(path.join(__dirname, "../frontend/controller", match[1]), "utf8"), boot, { filename: match[1] });`
- `tests/controller_modules.test.js:258` `const source = fs.readFileSync(path.join(__dirname, "../frontend/controller/physical.js"), "utf8");`
- `tests/controller_modules.test.js:259` `const html = fs.readFileSync(path.join(__dirname, "../frontend/controller/physical.html"), "utf8");`
- `tests/controller_modules.test.js:260` `const sizing = require("../frontend/controller/physical-sizing.js");`
- `tests/controller_modules.test.js:281` `const reconcile = source.slice(source.indexOf("    function reconcileLogicalErrors("),`
- `tests/controller_modules.test.js:283` `const bind = source.slice(source.indexOf("    let logicalResetPending ="),`
- `tests/controller_modules.test.js:285` `vm.runInContext(reconcile + bind + "\nbindLogicalEditor();", sandbox);`
- `tests/controller_modules.test.js:288` `vm.runInContext("reconcileLogicalErrors(state.draft)", sandbox);`

DOM/copy pins:

- `tests/controller_modules.test.js:103` `assert.ok(html.includes('id="' + id + '"'), "boot fixture geometry control exists in the real page: " + id);`
- `tests/controller_modules.test.js:106` `assert.match(html, /<body class="physical" data-view-zoom="fit" data-mode="content">/,`
- `tests/controller_modules.test.js:109` `assert.ok(shape.includes('id="grid-rows"') && shape.includes('id="grid-columns"'),`
- `tests/controller_modules.test.js:113` `assert.ok(shape.includes('id="arrange-grid-heading"') && shape.includes('id="arrange-bounds-heading"'),`
- `tests/controller_modules.test.js:117` `assert.ok(html.includes('id="arrange-model"') && html.includes('id="arrange-membership"'),`
- `tests/controller_modules.test.js:226` `assert.equal(healthNodes.wallHealth.textContent, "1 online · 1 offline · 1 needs calibration · 1 unplaced");`
- `tests/controller_modules.test.js:228` `assert.ok(!healthNodes.wallHealth.textContent.includes("wake-lock"), "unsupported wake lock is normal on HTTP");`
- `tests/controller_modules.test.js:231` `assert.ok(healthNodes.wallHealth.textContent.includes("1 wake-lock warning"));`
- `tests/controller_modules.test.js:234` `assert.equal(healthNodes.deviceCount.textContent, "1 of 2 last known online");`
- `tests/controller_modules.test.js:235` `assert.ok(healthNodes.wallHealth.textContent.startsWith("Last known:"));`
- `tests/controller_modules.test.js:236` `assert.ok(healthNodes.rosterStatus.textContent.includes("Showing last known status"));`
- `tests/controller_modules.test.js:239` `assert.equal(healthNodes.deviceCount.textContent, "Status unknown");`
- `tests/controller_modules.test.js:240` `assert.equal(healthNodes.wallHealth.textContent, "Tablet status unavailable");`
- `tests/controller_modules.test.js:306` `assert.equal(errors, 3, "disabled reset controls do not bypass validation");`

### controller_playback_errors.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.equal(writes, 2, "a version conflict retries the command once");; assert.deepEqual(versions, ["1", "3"], "retry reads a fresh version immediately before writing");; assert.deepEqual(retry.messages, []);; assert.equal(retry.state.playbackBusy, false);

Loader evidence:

- `tests/controller_playback_errors.test.js:7` `vm.runInContext(fs.readFileSync(path.join(__dirname, "../frontend/controller/physical-playback.js"), "utf8"), context);`

DOM/copy pins:

- No literal DOM/copy pin found in the inspected assertion patterns. Data values and exported API names remain contracts.

### controller_sizing.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.deepEqual(plain(geometry.normalizeSizing(undefined)), { mode: "fixed", padding: 0 });; assert.deepEqual(plain(geometry.normalizeSizing({ mode: "tablets", padding: "12.6" })), { mode: "tablets", padding: 13 });; assert.deepEqual(plain(geometry.normalizeSizing({ mode: "unknown", padding: -3 })), { mode: "fixed", padding: 0 });; assert.equal(editor.pendingNudge.placement.x, 100, "fit mode lets movement expand the derived wall");

Loader evidence:

- `tests/controller_sizing.test.js:9` `vm.runInContext(fs.readFileSync(path.join(__dirname, "../frontend/controller", name), "utf8"), context, { filename: name });`

DOM/copy pins:

- `tests/controller_sizing.test.js:41` `assert.equal(nodes.btnUndoStage.disabled, true, "placement undo is disabled in fit mode");`
- `tests/controller_sizing.test.js:42` `assert.equal(nodes.btnRedoStage.disabled, true, "placement redo is disabled in fit mode");`
- `tests/controller_sizing.test.js:43` `assert.equal(nodes.tileSection.hidden, true, "sequential tiling is hidden in fit mode");`
- `tests/controller_sizing.test.js:51` `assert.equal(nodes.tileSection.hidden, false, "sequential tiling remains available for fixed walls");`

### controller_url.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.equal(isLoopbackOrigin(origin), true, origin + " is local to this computer");; assert.equal(isLoopbackOrigin(origin), false, origin + " can be reached from another device");; assert.equal(isLoopbackOrigin("not an origin"), false);

Loader evidence:

- `tests/controller_url.test.js:9` `vm.runInContext(`
- `tests/controller_url.test.js:10` `fs.readFileSync(path.join(__dirname, "../frontend/controller/controller-url.js"), "utf8"),`

DOM/copy pins:

- No literal DOM/copy pin found in the inspected assertion patterns. Data values and exported API names remain contracts.

### operator_batch.test.js · (a)

No DOM; pure records, injected API/session doubles.

Behavior evidence: assert.equal(options.ifMatch, etag);; assert.deepEqual(body, { mode: "explicit", model_id: "actual-model" });; assert.deepEqual(result.completed, ["one", "two", "three", "four"], "original captured order survives external selection edits");; assert.deepEqual(guards, ["start", "returned-1", "returned-2", "returned-3"]);

Loader evidence:

- `tests/operator_batch.test.js:3` `const { confirmModels } = require("../frontend/controller/operator-devices.js");`

DOM/copy pins:

- `tests/operator_batch.test.js:37` `assert.ok(!guards.includes("unrelated-get"), "a fresh unrelated GET never authorizes the next write");`

### operator_clear_review.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.equal(writes.length, 0);; assert.match(messages.at(-1), /Review Clear wall again/);; assert.equal(writes.length, 1);; assert.equal(writes[0].ifMatch, "another-operator");

Loader evidence:

- `tests/operator_clear_review.test.js:3` `const source = fs.readFileSync(require.resolve("../frontend/controller/physical.js"), "utf8");`
- `tests/operator_clear_review.test.js:4` `const fragment = source.slice(source.indexOf("        const clearConfirm ="), source.indexOf("        const newModelReview ="));`
- `tests/operator_clear_review.test.js:11` `vm.runInNewContext(fragment, { document, state, resolveOutput: async () => true,`

DOM/copy pins:

- No literal DOM/copy pin found in the inspected assertion patterns. Data values and exported API names remain contracts.

### operator_composition.test.js · (a)

No DOM; pure records, injected API/session doubles.

Behavior evidence: mode and tablet selection have separate ownership; only Arrange without live, image or grid preview owns geometry; selection reveals the persistent panel without navigating; obsolete subjects cannot steal focus

Loader evidence:

- `tests/operator_composition.test.js:4` `const composition = require("../frontend/controller/operator-composition.js");`
- `tests/operator_composition.test.js:5` `const model = require("../frontend/controller/operator-state.js");`

DOM/copy pins:

- No literal DOM/copy pin found in the inspected assertion patterns. Data values and exported API names remain contracts.

### operator_content.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.equal(node("library-status").textContent, "", "pattern publication invalidates obsolete inventory loading text");; assert.equal(node("refresh-images").disabled, false, "a pattern invalidation releases inventory busy state");; assert.deepEqual(calls.map(call => call.path), ["/api/v3/images", "/api/v3/test-pattern", "/api/v3/scene"]);; assert.equal(calls[2].body.content.asset, image.id, "the generated flat image DTO is shown without fixture-only aliases");

Loader evidence:

- `tests/operator_content.test.js:6` `const model = require("../frontend/controller/operator-state.js");`
- `tests/operator_content.test.js:52` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);`
- `tests/operator_content.test.js:53` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-content.js"), "utf8"), context);`
- `tests/operator_content.test.js:140` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);`
- `tests/operator_content.test.js:141` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-content.js"), "utf8"), context);`
- `tests/operator_content.test.js:344` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);`
- `tests/operator_content.test.js:345` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-content.js"), "utf8"), context);`
- `tests/operator_content.test.js:485` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);`
- `tests/operator_content.test.js:486` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-content.js"), "utf8"), context);`
- `tests/operator_content.test.js:534` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);`
- `tests/operator_content.test.js:535` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-content.js"), "utf8"), context);`
- `tests/operator_content.test.js:608` `for (const file of ["operator-dom.js", "operator-content.js"]) vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/" + file), "utf8"), context);`

DOM/copy pins:

- `tests/operator_content.test.js:66` `assert.equal(node("library-status").textContent, "", "pattern publication invalidates obsolete inventory loading text");`
- `tests/operator_content.test.js:67` `assert.equal(node("refresh-images").disabled, false, "a pattern invalidation releases inventory busy state");`
- `tests/operator_content.test.js:74` `assert.equal(JSON.stringify(calls[2].body).includes("#22252a"), false);`
- `tests/operator_content.test.js:77` `assert.equal(tile.children.find(child => child.className === "image-size").textContent, "64 × 64");`
- `tests/operator_content.test.js:79` `assert.equal(preview.attrs["aria-label"], "Preview black.png");`
- `tests/operator_content.test.js:85` `assert.equal(node("image-title").textContent, "black.png", "the composer names the applied image");`
- `tests/operator_content.test.js:86` `assert.equal(node("pattern-message").textContent, "", "routine pattern success is silent");`
- `tests/operator_content.test.js:157` `assert.equal(tabStops().length, 1, message + " (one tab entry)");`
- `tests/operator_content.test.js:218` `assert.equal(galleryNode("image-title").textContent, "Tablet colours");`
- `tests/operator_content.test.js:220` `assert.equal(buttons().every(button => button.attrs["aria-pressed"] === "false"), true, "focus never marks a choice as selected");`
- `tests/operator_content.test.js:273` `assert.equal(focused(), buttons()[2], "Right skips hidden choices");`
- `tests/operator_content.test.js:275` `assert.equal(focused(), buttons()[5], "Down skips disabled choices when choosing the nearest target");`
- `tests/operator_content.test.js:296` `assert.equal(galleryNode("image-search").hidden, false);`
- `tests/operator_content.test.js:297` `assert.equal(tabStops().length, 0, "zero results never leave a hidden choice as the tab entry");`
- `tests/operator_content.test.js:366` `assert.equal(node("refresh-images").disabled, true, "a pending inventory read disables its trigger");`
- `tests/operator_content.test.js:368` `assert.match(node("library-status").textContent, /Refreshing the image library/);`
- `tests/operator_content.test.js:369` `assert.match(node("library-status").textContent, /last known library state/);`
- `tests/operator_content.test.js:372` `assert.equal(doc.activeElement, node("refresh-images"), "the settled refresh restores its invoking focus");`
- `tests/operator_content.test.js:373` `assert.equal(node("refresh-images").disabled, false);`
- `tests/operator_content.test.js:376` `assert.equal(node("library-status").textContent, "", "routine inventory success clears the refreshing label");`
- `tests/operator_content.test.js:382` `assert.equal(doc.activeElement, node("refresh-images"), "a failed refresh also restores its invoking focus");`
- `tests/operator_content.test.js:384` `assert.match(node("library-status").textContent, /library unavailable/);`
- `tests/operator_content.test.js:385` `assert.match(node("library-status").textContent, /last known library state is still shown/);`
- `tests/operator_content.test.js:386` `assert.equal(node("refresh-images").disabled, false);`
- `tests/operator_content.test.js:407` `assert.equal(node("library-status").textContent, refreshing, "an older failure cannot change the newer request's status");`
- `tests/operator_content.test.js:408` `assert.equal(node("refresh-images").disabled, true, "an older finalizer cannot clear the newer request's busy state");`
- `tests/operator_content.test.js:409` `assert.equal(doc.activeElement, node("image-search"), "an older finalizer cannot take focus");`
- `tests/operator_content.test.js:413` `assert.equal(node("library-status").textContent, "");`
- `tests/operator_content.test.js:414` `assert.equal(node("refresh-images").disabled, false);`
- `tests/operator_content.test.js:424` `assert.equal(empty.hidden, true, "a real empty inventory is announced only by the library status");`
- `tests/operator_content.test.js:425` `assert.equal(node("library-status").textContent, "No images available.");`
- `tests/operator_content.test.js:426` `assert.equal(node("image-message").textContent, "", "empty inventory does not announce in command feedback");`
- `tests/operator_content.test.js:429` `assert.equal(node("library-status").textContent, "No images available.", "a search cannot turn a real empty inventory into a filter miss");`
- `tests/operator_content.test.js:430` `assert.equal(empty.hidden, true, "search remains silent for empty inventory");`
- `tests/operator_content.test.js:437` `assert.equal(empty.textContent, "No images match your search.");`
- `tests/operator_content.test.js:445` `assert.equal(thumbnail.hidden, true, "a missing thumbnail is not rendered as a broken image");`
- `tests/operator_content.test.js:446` `assert.match(buttonA.attrs["aria-label"], /thumbnail unavailable/);`
- `tests/operator_content.test.js:447` `assert.match(buttonA.attrs["aria-describedby"], /image-thumbnail-note/);`
- `tests/operator_content.test.js:451` `assert.doesNotMatch(buttonA.attrs["aria-label"] || "", /thumbnail unavailable/);`
- `tests/operator_content.test.js:460` `assert.equal(node("image-title").textContent, "Unavailable image");`
- `tests/operator_content.test.js:461` `assert.equal(node("image-details").textContent, "Selected image unavailable. Refresh images or choose a replacement.");`
- `tests/operator_content.test.js:462` `assert.equal(node("show-image").disabled, true, "an unavailable selected proposal cannot be shown");`
- `tests/operator_content.test.js:479` `const list = doc.getElementById("image-gallery");`
- `tests/operator_content.test.js:499` `doc.getElementById("image-search").value = "keep";`
- `tests/operator_content.test.js:500` `doc.getElementById("image-search").input();`
- `tests/operator_content.test.js:544` `const list = doc.getElementById("image-gallery");`
- `tests/operator_content.test.js:548` `const tag = id => button(id).children.find(child => child.className === "image-choice-tag");`
- `tests/operator_content.test.js:553` `assert.equal(tag(patternA.id).textContent, "Test pattern");`
- `tests/operator_content.test.js:554` `assert.equal(tag(patternA.id).hidden, false, "a pattern shows its visible tag");`
- `tests/operator_content.test.js:556` `assert.equal(tag(managed.id).hidden, true, "a managed upload shaped like a pattern is not labelled");`
- `tests/operator_content.test.js:557` `assert.equal(tag(managed.id).textContent, "", "ordinary gallery tiles retain their plain text contract");`
- `tests/operator_content.test.js:558` `assert.equal(tag(wrongId.id).hidden, true, "a curated file whose name does not match its own id is not labelled");`
- `tests/operator_content.test.js:560` `assert.equal(button(patternA.id).attrs["aria-label"], "Preview " + patternA.name + ", test pattern",`
- `tests/operator_content.test.js:562` `assert.equal(button(patternB.id).attrs["aria-label"], "Preview " + patternB.name + ", test pattern");`
- `tests/operator_content.test.js:563` `assert.equal(button(managed.id).attrs["aria-label"], "Preview " + managed.name,`
- `tests/operator_content.test.js:565` `assert.equal(button(wrongId.id).attrs["aria-label"], "Preview " + wrongId.name);`
- `tests/operator_content.test.js:566` `assert.equal(button(plain.id).attrs["aria-label"], "Preview " + plain.name);`
- `tests/operator_content.test.js:576` `assert.equal(button(patternA.id).attrs["aria-pressed"], "true");`
- `tests/operator_content.test.js:629` `assert.equal(node("library-status").textContent, "", "upload uncertainty clears obsolete inventory loading");`
- `tests/operator_content.test.js:630` `assert.equal(node("refresh-images").disabled, false);`
- `tests/operator_content.test.js:631` `} else assert.equal(node("refresh-images").disabled, true, "the existing upload follow-up owns busy state");`
- `tests/operator_content.test.js:633` `assert.equal(node("upload-message").textContent, feedback, "the invalidated read cannot resolve upload outcome");`
- `tests/operator_content.test.js:634` `assert.equal(node("upload-submit").disabled, outcome === "uncertain");`
- `tests/operator_content.test.js:636` `assert.equal(node("refresh-images").disabled, true, "obsolete finalization cannot finish the upload follow-up");`
- `tests/operator_content.test.js:639` `assert.equal(node("library-status").textContent, "");`
- `tests/operator_content.test.js:643` `assert.equal(node("upload-message").textContent, "Could not check image-addition availability. connection unavailable. Use Check image-addition connection to retry.");`
- `tests/operator_content.test.js:644` `assert.equal(node("image-message").textContent, "", "capability feedback stays out of command feedback");`

### operator_content_status.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.equal(content.dirty(), false, "loading Images must not create a draft");; assert.equal(node("show-image").disabled, true, "Show needs a draft");; assert.equal(node("image-preview-controls").hidden, true, "an idle wall does not present an inactive edit form");; assert.equal(node("edit-current-image").hidden, true, "test colours have no saved image to adjust");

Loader evidence:

- `tests/operator_content_status.test.js:6` `const model = require("../frontend/controller/operator-state.js");`
- `tests/operator_content_status.test.js:46` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);`
- `tests/operator_content_status.test.js:47` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-content.js"), "utf8"), context);`
- `tests/operator_content_status.test.js:330` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);`
- `tests/operator_content_status.test.js:331` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-content.js"), "utf8"), context);`
- `tests/operator_content_status.test.js:441` `const html = fs.readFileSync(require.resolve("../frontend/controller/physical.html"), "utf8");`
- `tests/operator_content_status.test.js:489` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);`
- `tests/operator_content_status.test.js:490` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-content.js"), "utf8"), context);`
- `tests/operator_content_status.test.js:723` `const html = fs.readFileSync(require.resolve("../frontend/controller/physical.html"), "utf8");`

DOM/copy pins:

- `tests/operator_content_status.test.js:60` `assert.equal(node("show-image").disabled, true, "Show needs a draft");`
- `tests/operator_content_status.test.js:61` `assert.equal(node("image-preview-controls").hidden, true, "an idle wall does not present an inactive edit form");`
- `tests/operator_content_status.test.js:62` `assert.equal(node("edit-current-image").hidden, true, "test colours have no saved image to adjust");`
- `tests/operator_content_status.test.js:63` `assert.equal(node("image-fit").disabled, true, "Fit needs a draft");`
- `tests/operator_content_status.test.js:64` `assert.equal(node("image-title").textContent, "Tablet colours", "the stage names the test pattern currently on the wall");`
- `tests/operator_content_status.test.js:65` `assert.equal(node("image-details").textContent, "", "idle state needs no instructional paragraph");`
- `tests/operator_content_status.test.js:72` `assert.equal(node("image-title").textContent, "Unavailable image", "a missing applied image has a readable heading instead of an asset digest");`
- `tests/operator_content_status.test.js:73` `assert.equal(node("image-source-details").textContent, "sha256:missing", "the exact missing asset identity stays in Image details");`
- `tests/operator_content_status.test.js:80` `assert.equal(node("image-fit").value, "cover", "changing Fit with no draft restores the control");`
- `tests/operator_content_status.test.js:87` `assert.equal(buttonA.children.find(child => child.className === "image-choice-name").textContent, "a");`
- `tests/operator_content_status.test.js:88` `assert.equal(buttonA.children.some(child => child.className === "image-choice-dimensions"), false,`
- `tests/operator_content_status.test.js:90` `assert.equal(buttonA.attrs["aria-pressed"], "false");`
- `tests/operator_content_status.test.js:98` `assert.equal(node("image-preview-controls").hidden, false);`
- `tests/operator_content_status.test.js:99` `assert.equal(buttonA.attrs["aria-pressed"], "true");`
- `tests/operator_content_status.test.js:101` `assert.equal(node("image-title").textContent, "a");`
- `tests/operator_content_status.test.js:102` `assert.equal(node("image-source-details").textContent, "100 × 100 source px");`
- `tests/operator_content_status.test.js:103` `assert.equal(node("show-image").disabled, false);`
- `tests/operator_content_status.test.js:104` `assert.equal(node("image-fit").disabled, false);`
- `tests/operator_content_status.test.js:109` `assert.equal(buttonA.attrs["aria-pressed"], "false");`
- `tests/operator_content_status.test.js:110` `assert.equal(node("image-title").textContent, "Tablet colours");`
- `tests/operator_content_status.test.js:111` `assert.equal(node("image-details").textContent, "", "idle state needs no instructional paragraph");`
- `tests/operator_content_status.test.js:112` `assert.equal(node("show-image").disabled, true);`
- `tests/operator_content_status.test.js:113` `assert.equal(node("image-fit").disabled, true);`
- `tests/operator_content_status.test.js:115` `assert.equal(node("image-discard").hidden, true); assert.equal(node("restore-image").hidden, true);`
- `tests/operator_content_status.test.js:117` `assert.equal(node("image-discard").hidden, false);`
- `tests/operator_content_status.test.js:118` `assert.equal(node("image-rebuild").hidden, true, "a current preview needs no Rebuild");`
- `tests/operator_content_status.test.js:120` `assert.equal(node("image-rebuild").hidden, false, "a stale-base draft exposes Rebuild");`
- `tests/operator_content_status.test.js:124` `assert.equal(document.activeElement, node("image-search"));`
- `tests/operator_content_status.test.js:125` `assert.equal(node("image-discard").hidden, true); assert.equal(node("restore-image").hidden, false);`
- `tests/operator_content_status.test.js:127` `assert.equal(node("edit-current-image").hidden, false, "a saved image has an explicit adjust action");`
- `tests/operator_content_status.test.js:128` `assert.equal(node("image-preview-controls").hidden, false, "idle image scaling remains available in the commit bar");`
- `tests/operator_content_status.test.js:129` `assert.equal(node("show-image").disabled, true); assert.equal(node("image-fit").disabled, false);`
- `tests/operator_content_status.test.js:130` `assert.equal(node("image-message").textContent, "", "routine success is silent; the header carries the state");`
- `tests/operator_content_status.test.js:131` `assert.equal(buttonA.attrs["aria-pressed"], "false", "a completed Show clears the rust draft outline");`
- `tests/operator_content_status.test.js:133` `const appliedNote = cardA.children.find(child => child.id === buttonA.attrs["aria-describedby"]);`
- `tests/operator_content_status.test.js:136` `assert.equal(buttonA.attrs["aria-describedby"], appliedNote.id, "the applied marker has an accessible description");`
- `tests/operator_content_status.test.js:144` `renderContent(content); assert.equal(node("image-message").textContent, confirm);`
- `tests/operator_content_status.test.js:146` `assert.equal(node("image-message").textContent, confirm, "stale tablet evidence stays in the header and Issues");`
- `tests/operator_content_status.test.js:148` `assert.equal(node("image-message").textContent, confirm, "tablet failures are not enumerated in the inspector");`
- `tests/operator_content_status.test.js:150` `assert.equal(node("image-message").textContent, confirm, "mapping failures are not enumerated in the inspector");`
- `tests/operator_content_status.test.js:153` `assert.equal(node("image-message").textContent, confirm, "offline tablets are not enumerated in the inspector");`
- `tests/operator_content_status.test.js:156` `assert.equal(node("image-message").textContent, "", "revision-only drift with unchanged generation, content and arrangement needs no warning");`
- `tests/operator_content_status.test.js:158` `config.scene.content.asset = "b"; renderContent(content); assert.match(node("image-message").textContent, warning, "another asset retains the warning");`
- `tests/operator_content_status.test.js:159` `config.scene.content.asset = "a"; config.scene.content.fit = "contain"; renderContent(content); assert.match(node("image-message").textContent, warning, "changed scaling retains the warning");`
- `tests/operator_content_status.test.js:160` `config.scene.content.fit = "cover"; config.scene.content.type = "color"; renderContent(content); assert.match(node("image-message").textContent, warning, "changed content type retains the warning");`
- `tests/operator_content_status.test.js:162` `config.layout.width = 200; renderContent(content); assert.match(node("image-message").textContent, warning, "changed arrangement retains the warning even for the same image");`
- `tests/operator_content_status.test.js:164` `config.generation = "new"; renderContent(content); assert.match(node("image-message").textContent, warning, "another server generation cannot inherit the receipt");`
- `tests/operator_content_status.test.js:165` `config.generation = "g"; renderContent(content); assert.equal(node("image-message").textContent, "");`
- `tests/operator_content_status.test.js:167` `assert.equal(node("image-message").textContent, confirm);`
- `tests/operator_content_status.test.js:170` `assert.match(node("image-message").textContent, warning, "inventory success preserves the command receipt for later drift detection");`
- `tests/operator_content_status.test.js:172` `assert.equal(node("image-message").textContent, confirm);`
- `tests/operator_content_status.test.js:175` `assert.match(node("image-message").textContent, /^Image applied\. Tablet reports may be stale/);`
- `tests/operator_content_status.test.js:178` `assert.match(node("image-message").textContent, /stale/);`
- `tests/operator_content_status.test.js:180` `assert.equal(node("image-message").textContent, confirm);`
- `tests/operator_content_status.test.js:182` `failInventory = true; await content.refresh(); renderContent(content); assert.match(node("library-status").textContent, /library unavailable/);`
- `tests/operator_content_status.test.js:184` `assert.match(node("library-status").textContent, /library unavailable/, "a retained library error survives a later command");`
- `tests/operator_content_status.test.js:190` `assert.equal(state.previewContent.asset, "b"); assert.equal(content.dirty(), true); assert.equal(node("image-discard").hidden, false);`
- `tests/operator_content_status.test.js:191` `assert.equal(node("image-title").textContent, "b");`
- `tests/operator_content_status.test.js:192` `assert.equal(node("image-source-details").textContent, "100 × 100 source px");`
- `tests/operator_content_status.test.js:195` `assert.equal(buttonA.attrs["aria-pressed"], "false", "Show cleared the draft it submitted");`
- `tests/operator_content_status.test.js:196` `assert.equal(buttonB.attrs["aria-pressed"], "true", "a newer draft keeps its own rust outline");`
- `tests/operator_content_status.test.js:199` `assert.equal(node("image-title").textContent, "a", "the stage headline names the applied image during comparison");`
- `tests/operator_content_status.test.js:200` `assert.equal(node("show-image").textContent, "Show b", "while the applied wall is visible, Show names what it will show");`
- `tests/operator_content_status.test.js:202` `node("image-discard").focus(); content.discard(); assert.equal(document.activeElement, node("image-search"));`
- `tests/operator_content_status.test.js:205` `assert.equal(buttonB.attrs["aria-pressed"], "false", "Discard removes the rust outline");`
- `tests/operator_content_status.test.js:214` `assert.equal(node("image-fit").value, "contain");`
- `tests/operator_content_status.test.js:217` `assert.equal(node("image-fit").value, "cover", "discard restores applied Scaling");`
- `tests/operator_content_status.test.js:285` `assert.equal(node("show-image").disabled, true);`
- `tests/operator_content_status.test.js:286` `assert.match(node("image-message").textContent, /Discard.*Saved.*preview.*again/);`
- `tests/operator_content_status.test.js:287` `assert.equal(document.activeElement, node("image-message"), "saved recovery instruction receives focus");`
- `tests/operator_content_status.test.js:350` `assert.equal(fitNode("crop-bars").hidden, true);`
- `tests/operator_content_status.test.js:358` `assert.equal(fitNode("crop-bars").hidden, false);`
- `tests/operator_content_status.test.js:384` `assert.equal(fitNode("crop-bars").hidden, true, "missing source dimensions never invent zero crop");`
- `tests/operator_content_status.test.js:390` `assert.equal(fitNode("crop-bars").hidden, true);`
- `tests/operator_content_status.test.js:406` `assert.equal(fitNode("crop-bars").hidden, true);`
- `tests/operator_content_status.test.js:447` `assert.match(html, /id="fit-feedback"[^>]*aria-labelledby="fit-feedback-title"/);`
- `tests/operator_content_status.test.js:449` `assert.match(html, /id="crop-bars"[^>]*aria-hidden="true"/);`
- `tests/operator_content_status.test.js:450` `assert.match(html, /id="fit-summary"[^>]*role="status"[^>]*aria-live="polite"/);`
- `tests/operator_content_status.test.js:452` `assert.ok(bars.includes('id="crop-width"') && bars.includes('id="crop-height"'), "crop values belong to the decorative bars");`
- `tests/operator_content_status.test.js:525` `assert.equal(node("image-message").textContent, exact412);`
- `tests/operator_content_status.test.js:528` `assert.equal(node("image-message").textContent, exact412, "a delayed inventory success cannot clear the 412 command error");`
- `tests/operator_content_status.test.js:557` `assert.equal(node("image-message").textContent, expected);`
- `tests/operator_content_status.test.js:565` `assert.equal(node("image-message").textContent, expected, event + " survives a delayed inventory " + outcome);`
- `tests/operator_content_status.test.js:566` `assert.equal(messageWrites, before, "inventory completion adds no command announcement");`
- `tests/operator_content_status.test.js:568` `assert.equal(doc.activeElement, node("image-search"));`
- `tests/operator_content_status.test.js:570` `assert.equal(node("library-status").textContent, outcome === "success" ? ""`
- `tests/operator_content_status.test.js:580` `assert.equal(doc.activeElement, node("image-rebuild"), "remote invalidation hands focused Show to Rebuild before the new guard arrives");`
- `tests/operator_content_status.test.js:581` `assert.equal(node("image-rebuild").hidden, false);`
- `tests/operator_content_status.test.js:582` `assert.equal(node("show-image").disabled, true);`
- `tests/operator_content_status.test.js:583` `assert.equal(node("image-message").textContent, staleImage);`
- `tests/operator_content_status.test.js:584` `assert.equal(node("image-message").dataset.kind, "warn");`
- `tests/operator_content_status.test.js:588` `assert.equal(messageWrites, once, "one stale transition announces only once across invalidation and reconciliation");`
- `tests/operator_content_status.test.js:596` `assert.equal(doc.activeElement, node("image-search"), "remote staleness does not touch another control's focus");`
- `tests/operator_content_status.test.js:602` `assert.equal(node("image-message").textContent, staleSaved);`
- `tests/operator_content_status.test.js:603` `assert.equal(doc.activeElement, node("image-message"), "saved previews focus the safe re-preview instruction");`
- `tests/operator_content_status.test.js:611` `assert.equal(node("library-status").textContent, retainedError, "staleness never overwrites a retained inventory error");`
- `tests/operator_content_status.test.js:612` `assert.equal(node("image-message").textContent, staleImage, "a library error cannot suppress stale preview guidance");`
- `tests/operator_content_status.test.js:625` `assert.equal(node("image-message").textContent, exact412, "a 412 states the recovery path in plain words");`
- `tests/operator_content_status.test.js:626` `assert.equal(node("image-message").textContent.includes("Server detail"), false, "a 412 never prints the server detail");`
- `tests/operator_content_status.test.js:627` `assert.equal(doc.activeElement, node("image-rebuild"), "a stale preview focuses the visible Rebuild control first");`
- `tests/operator_content_status.test.js:629` `assert.equal(node("image-rebuild").disabled, false);`
- `tests/operator_content_status.test.js:632` `assert.equal(node("show-image").disabled, true, "Refresh alone cannot authorize the original preview against a new wall");`
- `tests/operator_content_status.test.js:638` `assert.equal(node("show-image").disabled, true);`
- `tests/operator_content_status.test.js:639` `assert.equal(node("image-message").textContent, exact412);`
- `tests/operator_content_status.test.js:641` `assert.equal(node("image-message").textContent, "", "explicit rebuild clears the obsolete Show failure");`
- `tests/operator_content_status.test.js:642` `assert.equal(node("show-image").disabled, false);`
- `tests/operator_content_status.test.js:653` `assert.equal(node("image-rebuild").hidden, false, "an invalidated guard exposes explicit recovery before reconciliation returns");`
- `tests/operator_content_status.test.js:654` `assert.equal(doc.activeElement, node("image-rebuild"), "an invalidated guard focuses its visible recovery action");`
- `tests/operator_content_status.test.js:655` `assert.equal(node("image-message").textContent, exact412, "passive stale guidance never overwrites a real 412 failure");`
- `tests/operator_content_status.test.js:663` `assert.equal(node("image-message").textContent, "Could not show this content. Image store failed. Use Refresh images to retry.",`
- `tests/operator_content_status.test.js:665` `assert.equal(doc.activeElement, node("show-image"), "an enabled trigger keeps focus");`
- `tests/operator_content_status.test.js:698` `assert.equal(await content.showSelected({ feedback: "scene-message" }), false, "a refused saved-content recall fails");`
- `tests/operator_content_status.test.js:702` `assert.equal(node("scene-message").textContent,`
- `tests/operator_content_status.test.js:705` `assert.equal(doc.activeElement, node("scene-message"), "with Images hidden, focus goes to the visible recall message");`
- `tests/operator_content_status.test.js:725` `assert.ok(!status.includes('id="wall-power-caution"'), "wall status does not infer whether tablet screens may sleep");`
- `tests/operator_content_status.test.js:727` `assert.ok(!details.includes('id="wall-power-summary"'), "wake-lock reports stay in the Tablet panel");`
- `tests/operator_content_status.test.js:728` `assert.match(html, /id="image-message"[^>]*tabindex="-1"/, "the Images message is programmatically focusable");`
- `tests/operator_content_status.test.js:731` `assert.match(html, new RegExp('id="' + input + '"[^>]*aria-describedby="' + hint + " " + message + '"'),`

### operator_devices.test.js · (b)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.equal(node("tablet-recovery-actions").open, true, "stale authority keeps recovery visible");; assert.equal(node("tablet-identify").disabled, true, authority + " authority disables the inspector command");; assert.equal(devices.canIdentify("a"), false, authority + " authority disables other command entries");; assert.equal(requests.length, 0, "unavailable Identify sends no request");

Loader evidence:

- `tests/operator_devices.test.js:3` `const { create } = require("../frontend/controller/operator-devices.js");`
- `tests/operator_devices.test.js:33` `rosterStatus: require("../frontend/controller/operator-state.js").rosterStatus, entries: layout => layout.placements || layout.slots,`
- `tests/operator_devices.test.js:42` `const forms = require("../frontend/controller/operator-forms.js").create();`
- `tests/operator_devices.test.js:144` `evidence = require("../frontend/controller/operator-state.js").tabletState({`
- `tests/operator_devices.test.js:316` `const power = require("../frontend/controller/operator-stage.js").powerReadiness(state.roster.a, { stale, checkedAt: state.rosterCheckedAt });`

DOM/copy pins:

- `tests/operator_devices.test.js:55` `assert.equal(node("tablet-recovery-actions").open, true, "stale authority keeps recovery visible");`
- `tests/operator_devices.test.js:56` `assert.equal(node("tablet-identify").disabled, true, authority + " authority disables the inspector command");`
- `tests/operator_devices.test.js:60` `assert.match(node("tablet-action-message").textContent, /Refresh status/, "activation-time refusal explains recovery");`
- `tests/operator_devices.test.js:64` `assert.equal((node("tablet-label-save").dataset.ready === "true"), false, "clean names have no primary emphasis");`
- `tests/operator_devices.test.js:67` `assert.equal((node("tablet-label-save").dataset.ready === "true"), true, "a dirty valid name is ready for emphasis");`
- `tests/operator_devices.test.js:70` `assert.equal((node("tablet-label-save").dataset.ready === "true"), false, "invalid names are not ready for emphasis");`
- `tests/operator_devices.test.js:71` `assert.equal(node("tablet-label-save").disabled, false, "emphasis does not change existing availability");`
- `tests/operator_devices.test.js:74` `assert.equal((node("tablet-label-save").dataset.ready === "true"), true, "poll rendering preserves dirty valid emphasis");`
- `tests/operator_devices.test.js:76` `assert.equal((node("tablet-label-save").dataset.ready === "true"), false, "discard restores the clean treatment");`
- `tests/operator_devices.test.js:77` `assert.equal(node("tablet-identify").disabled, false);`
- `tests/operator_devices.test.js:78` `assert.equal(node("tablet-recovery-actions").open, false, "healthy current reports collapse recovery");`
- `tests/operator_devices.test.js:79` `assert.equal(node("tablet-recovery-title").textContent, "Details");`
- `tests/operator_devices.test.js:81` `assert.equal(node("tablet-recovery-actions").open, true, "polls preserve operator disclosure choice");`
- `tests/operator_devices.test.js:84` `assert.equal(node("tablet-recovery-actions").hidden, true, "offline recovery does not offer an empty disclosure");`
- `tests/operator_devices.test.js:85` `assert.equal(node("tablet-evidence").hidden, true, "offline facts are not repeated above guidance");`
- `tests/operator_devices.test.js:86` `assert.equal(node("tablet-recovery").hidden, false, "offline physical recovery guidance remains visible");`
- `tests/operator_devices.test.js:87` `assert.match(node("tablet-recovery").textContent, /check power/);`
- `tests/operator_devices.test.js:90` `assert.equal(node("tablet-recovery-actions").hidden, false, "online failures retain actionable recovery");`
- `tests/operator_devices.test.js:91` `assert.equal(node("tablet-recovery-actions").open, true, "failed images show recovery immediately");`
- `tests/operator_devices.test.js:104` `assert.match(node("tablet-action-message").textContent, /Identify requested for Tablet a/);`
- `tests/operator_devices.test.js:105` `assert.equal(announcements.some(text => text.includes("Delivery is unconfirmed")), true);`
- `tests/operator_devices.test.js:117` `assert.equal(node("tablet-evidence").textContent, "Wake lock: denied");`
- `tests/operator_devices.test.js:120` `assert.equal(node("tablet-evidence").dataset.powerWarning, "true");`
- `tests/operator_devices.test.js:121` `assert.equal(node("tablet-recovery").hidden, false, "a painted tablet still warns denied power");`
- `tests/operator_devices.test.js:122` `assert.equal(node("tablet-recovery").children.length, 3, "recovery guidance is three readable parts");`
- `tests/operator_devices.test.js:124` `assert.equal(node("tablet-recovery").textContent, DENIED_RECOVERY, "the split keeps the exact pre-change words in order");`
- `tests/operator_devices.test.js:125` `assert.match(node("tablet-recovery").textContent, /denied/);`
- `tests/operator_devices.test.js:126` `assert.match(node("tablet-recovery").textContent, /cannot wake/);`
- `tests/operator_devices.test.js:127` `assert.match(node("tablet-provenance").textContent, /Wake lock readiness: denied/);`
- `tests/operator_devices.test.js:128` `assert.match(node("tablet-retry-image").title, /does not wake/);`
- `tests/operator_devices.test.js:129` `assert.match(node("tablet-reconnect").title, /does not wake/);`
- `tests/operator_devices.test.js:137` `assert.match(node("tablet-evidence").textContent, /Previous paint/);`
- `tests/operator_devices.test.js:138` `assert.match(node("tablet-evidence").textContent, /Wake lock: held/);`
- `tests/operator_devices.test.js:139` `assert.equal(node("tablet-evidence").dataset.status, "stale");`
- `tests/operator_devices.test.js:140` `assert.equal(node("tablet-evidence").dataset.powerWarning, "false");`
- `tests/operator_devices.test.js:141` `assert.match(node("tablet-recovery").textContent, /does not confirm paint/);`
- `tests/operator_devices.test.js:142` `assert.match(node("tablet-recovery").textContent, /not proof/);`
- `tests/operator_devices.test.js:149` `assert.match(node("tablet-recovery").textContent, /measurements/);`
- `tests/operator_devices.test.js:151` `assert.equal(node("open-tablet-measurements").hidden, false, "mapping revision staleness exposes measurements recovery");`
- `tests/operator_devices.test.js:157` `assert.match(node("tablet-evidence").textContent, /Last known wake lock held/);`
- `tests/operator_devices.test.js:158` `assert.equal(node("tablet-evidence").dataset.powerStale, "true");`
- `tests/operator_devices.test.js:159` `assert.match(node("tablet-recovery").textContent, /Tablet is offline.*last known report/);`
- `tests/operator_devices.test.js:161` `assert.equal(node("tablet-recovery").children.length, 3, "offline recovery also has three readable parts");`
- `tests/operator_devices.test.js:172` `assert.equal(node("tablet-recovery").children[2].children.length, 4, "server limits keep three short sentences under their heading");`
- `tests/operator_devices.test.js:173` `assert.match(node("tablet-recovery").children[2].textContent, /cannot wake.*denied/,`
- `tests/operator_devices.test.js:182` `assert.equal(node("tablet-evidence").textContent, "Wake lock: unknown");`
- `tests/operator_devices.test.js:183` `assert.equal(node("tablet-recovery").hidden, true, "unknown power alone does not fabricate a warning");`
- `tests/operator_devices.test.js:187` `assert.match(node("tablet-evidence").textContent, /Last known wake lock unknown/);`
- `tests/operator_devices.test.js:188` `assert.match(node("tablet-evidence").textContent, /status stale/);`
- `tests/operator_devices.test.js:189` `assert.equal(node("tablet-evidence").dataset.powerStale, "true");`
- `tests/operator_devices.test.js:194` `assert.equal(node("tablet-evidence").textContent, "Wake lock: unsupported");`
- `tests/operator_devices.test.js:195` `assert.equal(node("tablet-recovery").hidden, true, "unsupported is reported without a false power warning");`
- `tests/operator_devices.test.js:198` `assert.equal(node("tablet-evidence").textContent, "Wake lock: insecure origin");`
- `tests/operator_devices.test.js:199` `assert.equal(node("tablet-recovery").hidden, false);`
- `tests/operator_devices.test.js:200` `assert.match(node("tablet-recovery").textContent, /trusted HTTPS origin/);`
- `tests/operator_devices.test.js:203` `assert.equal(node("tablet-recovery").hidden, false);`
- `tests/operator_devices.test.js:204` `assert.match(node("tablet-recovery").textContent, /foreground/);`
- `tests/operator_devices.test.js:217` `assert.match(node("tablet-action-message").textContent, /Image retry requested/);`
- `tests/operator_devices.test.js:218` `assert.match(node("tablet-action-message").textContent, /does not wake/);`
- `tests/operator_devices.test.js:223` `assert.match(node("tablet-action-message").textContent, /Reconnect requested/);`
- `tests/operator_devices.test.js:224` `assert.match(node("tablet-action-message").textContent, /does not wake/);`
- `tests/operator_devices.test.js:241` `assert.equal(document.activeElement, node("tablet-identify"), "a failed command restores focus to its invoking control");`
- `tests/operator_devices.test.js:250` `assert.equal(node("tablet-label").value, "Draft name");`
- `tests/operator_devices.test.js:262` `assert.equal(pointer.hidden, false, "an offline selected tablet with online unplaced tablets offers the pointer");`
- `tests/operator_devices.test.js:263` `assert.equal(pointer.children[0].textContent, "Review replacement with a new tablet");`
- `tests/operator_devices.test.js:264` `assert.equal(pointer.children[0].className, "btn");`
- `tests/operator_devices.test.js:267` `assert.equal(document.activeElement, node("replacement-old"), "the replacement offer's first control receives focus");`
- `tests/operator_devices.test.js:273` `assert.equal(node("tablet-replacement-pointer").hidden, true, "no online unplaced tablet hides the pointer");`
- `tests/operator_devices.test.js:277` `assert.equal(node("tablet-replacement-pointer").hidden, true, "an online tablet that is placed hides the pointer");`
- `tests/operator_devices.test.js:281` `assert.equal(node("tablet-replacement-pointer").hidden, true, "an online selected tablet does not offer the pointer");`
- `tests/operator_devices.test.js:290` `assert.equal(node("open-tablet-measurements").hidden, true, "a logical wall hides measurements for a healthy selected tablet");`
- `tests/operator_devices.test.js:293` `assert.equal(node("open-tablet-measurements").hidden, false, "an applied measured layout keeps measurements reachable");`
- `tests/operator_devices.test.js:297` `assert.equal(node("open-tablet-measurements").hidden, false, "an applied physical layout keeps measurements reachable");`
- `tests/operator_devices.test.js:301` `assert.equal(node("open-tablet-measurements").hidden, false, "a physical grid kind keeps measurements reachable");`
- `tests/operator_devices.test.js:305` `assert.equal(node("open-tablet-measurements").hidden, false, "a blocked mapping keeps measurements reachable");`
- `tests/operator_devices.test.js:327` `assert.match(node("tablet-action-message").textContent, /Identify requested for Tablet a/);`
- `tests/operator_devices.test.js:329` `assert.equal(node("tablet-action-message").textContent, "", "a receipt does not outlive the selection that earned it");`
- `tests/operator_devices.test.js:332` `assert.equal(node("open-tablet-measurements").hidden, true, "no selected tablet hides measurements");`

### operator_entry.test.js · (c)

Whole entry script in VM; window.location/history doubles, no rendered DOM.

Behavior evidence: assert.equal(destination, undefined, "navigation waits for the fallback content");; assert.equal(nodes["entry-link"].href, expected, "fallback stays on the same origin and preserves local state");; if (blocked) assert.match(nodes["entry-status"].textContent, /blocked.*Open wall workspace/);; else assert.equal(destination, expected);

Loader evidence:

- `tests/operator_entry.test.js:5` `const source = fs.readFileSync(require.resolve("../frontend/controller/operator-entry.js"), "utf8");`
- `tests/operator_entry.test.js:12` `vm.runInNewContext(source, { URL, window: { location }, document: { readyState: "loading",`

DOM/copy pins:

- `tests/operator_entry.test.js:18` `if (blocked) assert.match(nodes["entry-status"].textContent, /blocked.*Open wall workspace/);`

### operator_forms.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.equal(forms.observe("A", "name", { name: "Tablet 1" }, "heartbeat").values.name, "Lobby left");; assert.equal(forms.get("A", "name").dirty, true, "late A save cannot clear a newer A edit");; assert.equal(forms.get("B", "name").values.name, "Keep B edit", "A result cannot change selected B");; assert.equal(forms.observe("A", group, { field: "baseline" }, "runtime").values.field, "exact unsaved value");

Loader evidence:

- `tests/operator_forms.test.js:5` `const forms = require("../frontend/controller/operator-forms.js").create();`
- `tests/operator_forms.test.js:31` `const grouped = require("../frontend/controller/operator-forms.js").create();`
- `tests/operator_forms.test.js:40` `const rule = require("../frontend/controller/operator-forms.js").snapshotName;`
- `tests/operator_forms.test.js:56` `const controllerSource = fs.readFileSync(require.resolve("../frontend/controller/physical.js"), "utf8");`
- `tests/operator_forms.test.js:79` `vm.runInContext("const SNAPSHOT_NAME_RULE = " + ruleLiteral + ";\n" + controllerSource.slice(start, end), context);`
- `tests/operator_forms.test.js:111` `vm.runInContext("const SNAPSHOT_NAME_RULE = " + ruleLiteral + "; let savedScenes = [];\n" + controllerSource.slice(start, end), context);`

DOM/copy pins:

- `tests/operator_forms.test.js:83` `assert.equal(message.textContent, ruleText, "a refused arrangement name shows the rule");`
- `tests/operator_forms.test.js:93` `assert.equal(message.textContent, "Enter an arrangement name. " + ruleText, "an empty arrangement keeps its original prompt and the rule");`
- `tests/operator_forms.test.js:109` `const start = controllerSource.indexOf('document.getElementById("scene-save-form").addEventListener("submit"');`
- `tests/operator_forms.test.js:115` `assert.equal(message.textContent, ruleText, "a refused content name shows the rule");`
- `tests/operator_forms.test.js:122` `assert.equal(message.textContent, "Enter a content name. " + ruleText, "an empty content name keeps its original prompt and the rule");`

### operator_geometry.test.js · (a)

No DOM; pure records, injected API/session doubles.

Behavior evidence: assert.equal(layout.width, 258); assert.equal(layout.height, 128);; assert.equal(layout.placements.a.x, 4); assert.equal(layout.placements.b.y, 4);; assert.equal(layout.placements.b.x - layout.placements.a.x, b.x - a.x, "fit preserves relative positions");; assert.deepEqual(layout.placements.a.bezel, a.bezel);

Loader evidence:

- `tests/operator_geometry.test.js:3` `const { fitLogical, arrangeLogical, rotateLogical } = require("../frontend/controller/operator-state.js");`
- `tests/operator_geometry.test.js:35` `const sizing = require("../frontend/controller/physical-sizing.js");`
- `tests/operator_geometry.test.js:36` `const stageModel = require("../frontend/controller/operator-stage.js");`

DOM/copy pins:

- `tests/operator_geometry.test.js:80` `assert.equal(sizing.matchScreenShape(baseSlot, { width: 0, height: 1000 }).error.includes("viewport"), true);`
- `tests/operator_geometry.test.js:81` `assert.equal(sizing.matchScreenShape({ ...baseSlot, w: 12 }, { width: 1600, height: 1000 }).error.includes("active screen width"), true);`
- `tests/operator_geometry.test.js:87` `assert.equal(sizing.freshViewport({ online: true, viewport: { width: 1600, height: 1000 } }, { stale: true }).reason.includes("stale"), true);`
- `tests/operator_geometry.test.js:92` `assert.match(sizing.validateLogicalField("w", "0", fixedDraft, baseSlot).message, /at least 1/);`
- `tests/operator_geometry.test.js:94` `assert.match(sizing.validateLogicalField("w", "999999", fixedDraft, baseSlot).message, /wall width 3600/);`
- `tests/operator_geometry.test.js:96` `assert.match(sizing.validateLogicalField("h", "999999", fixedDraft, baseSlot).message, /wall height 2400/);`
- `tests/operator_geometry.test.js:98` `assert.match(sizing.validateLogicalField("w", "1.5", fixedDraft, baseSlot).message, /whole number/);`
- `tests/operator_geometry.test.js:104` `assert.match(sizing.validateLogicalField("bezel-left", "-1", fixedDraft, baseSlot).message, /negative/);`
- `tests/operator_geometry.test.js:105` `assert.match(sizing.validateLogicalField("bezel-left", "100", fixedDraft, baseSlot).message, /no visible width/);`
- `tests/operator_geometry.test.js:121` `for (const phrase of ["Shift", "Escape", "Alt", "touch", "Numeric", "Fit and 2x"]) assert.ok(help.includes(phrase), "help names " + phrase);`
- `tests/operator_geometry.test.js:122` `assert.ok(stageModel.helpText(false).includes("Numeric"));`
- `tests/operator_geometry.test.js:123` `assert.ok(stageModel.helpText(true, "physical").includes("millimetre"), "measured help names millimetres");`
- `tests/operator_geometry.test.js:124` `assert.equal(stageModel.helpText(true, "physical").includes("snap checkbox"), false, "measured help does not claim logical snap");`

### operator_grid.test.js · (a)

No DOM; pure records, injected API/session doubles.

Behavior evidence: assert.deepEqual(logical.device_ids, source.ids, "submitted order is the sole order of record");; assert.deepEqual(logical.release_unselected, ["offline"]);; assert.equal(logical.physical_revisions, undefined);; assert.equal(logical.mount_angles, undefined);

Loader evidence:

- `tests/operator_grid.test.js:3` `const { command } = require("../frontend/controller/operator-grid.js");`
- `tests/operator_grid.test.js:4` `const sizing = require("../frontend/controller/physical-sizing.js");`
- `tests/operator_grid.test.js:5` `const stage = require("../frontend/controller/operator-stage.js");`
- `tests/operator_grid.test.js:50` `const { membership } = require("../frontend/controller/operator-grid.js");`

DOM/copy pins:

- No literal DOM/copy pin found in the inspected assertion patterns. Data values and exported API names remain contracts.

### operator_grid_releases.test.js · (b)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.deepEqual(owner.selectedIds(), ["a"]);; assert.equal(nodes.get("grid-releases").children.length, 0);; assert.deepEqual(releases().map(input => input.dataset.release), ["b"], "another operator's placement for a known unselected tablet needs an acknowledgement control");; assert.equal(releases()[0].checked, true, "a later authority render keeps the acknowledgement");

Loader evidence:

- `tests/operator_grid_releases.test.js:4` `const grid = require("../frontend/controller/operator-grid.js");`

DOM/copy pins:

- `tests/operator_grid_releases.test.js:20` `global.document = { getElementById(id) { if (!nodes.has(id)) nodes.set(id, new Node("div")); return nodes.get(id); },`
- `tests/operator_grid_releases.test.js:34` `const releases = () => nodes.get("grid-releases").querySelectorAll("input");`
- `tests/operator_grid_releases.test.js:41` `assert.match(nodes.get("grid-message").textContent, /^Cannot preview arrangement\./, "the acknowledgement satisfies the release guard");`
- `tests/operator_grid_releases.test.js:44` `assert.equal(nodes.get("grid-1x4").hidden, true, "equivalent one-tablet presets collapse");`
- `tests/operator_grid_releases.test.js:46` `assert.equal(twoByTwo["aria-pressed"], "true");`
- `tests/operator_grid_releases.test.js:47` `assert.equal(nodes.get("grid-message").textContent, "");`
- `tests/operator_grid_releases.test.js:49` `assert.equal(twoByTwo["aria-pressed"], "false", "custom dimensions clear preset selection");`
- `tests/operator_grid_releases.test.js:59` `const message = nodes.get("grid-message"), review = message.children.find(child => child.className === "grid-warnings");`
- `tests/operator_grid_releases.test.js:60` `assert.equal(message.textContent, "1 tablet · 1 × 1 · 100 × 100 logical units");`
- `tests/operator_grid_releases.test.js:61` `assert.equal(review.textContent, "Mixed footprint. Uneven edge. Apply will request a named safety copy of the current arrangement.");`
- `tests/operator_grid_releases.test.js:62` `assert.equal(review.children[1].children[0].textContent, "Estimated measurement a.");`
- `tests/operator_grid_releases.test.js:65` `assert.equal(nodes.get("grid-summary").hidden, false);`
- `tests/operator_grid_releases.test.js:66` `assert.equal(nodes.get("grid-summary-warning").hidden, false);`
- `tests/operator_grid_releases.test.js:67` `assert.equal(nodes.get("grid-summary-warning-title").textContent, "Uneven edge", "the uneven-edge warning is its own callout");`
- `tests/operator_grid_releases.test.js:68` `assert.match(nodes.get("grid-summary-warning-text").textContent, /^Mixed footprint\. Uneven edge\./);`
- `tests/operator_grid_releases.test.js:69` `assert.match(nodes.get("grid-summary-note").textContent, /named safety copy/);`
- `tests/operator_grid_releases.test.js:81` `assert.equal(oneRow.textContent, "1 × 3");`
- `tests/operator_grid_releases.test.js:82` `assert.equal(oneRow["aria-pressed"], "true");`
- `tests/operator_grid_releases.test.js:87` `assert.match(nodes.get("grid-message").textContent, /^Explicitly acknowledge/);`
- `tests/operator_grid_releases.test.js:102` `assert.equal(twoByTwo["aria-pressed"], "true", "the visible equivalent preset carries the selected state for one tablet");`
- `tests/operator_grid_releases.test.js:108` `assert.equal(twoByTwo["aria-pressed"], "false");`
- `tests/operator_grid_releases.test.js:109` `assert.equal(oneRow["aria-pressed"], "false");`
- `tests/operator_grid_releases.test.js:119` `assert.equal(oneRow["aria-pressed"], "false", "typing custom dimensions leaves the preset immediately");`
- `tests/operator_grid_releases.test.js:120` `assert.equal(twoByTwo["aria-pressed"], "false");`
- `tests/operator_grid_releases.test.js:131` `getElementById(id) { if (!map.has(id)) map.set(id, new Node("div")); return map.get(id); },`
- `tests/operator_grid_releases.test.js:146` `assert.equal(node("grid-lock-note").hidden, true, "the place lock note is hidden while no placement draft is open");`
- `tests/operator_grid_releases.test.js:149` `assert.equal(node("grid-lock-note").hidden, false, "a manual placement draft shows the place lock note");`
- `tests/operator_grid_releases.test.js:150` `assert.equal(node("grid-2x2").disabled, true, "the draft still disables the grid presets");`
- `tests/operator_grid_releases.test.js:151` `assert.equal(node("grid-lock-note").children[0].textContent,`
- `tests/operator_grid_releases.test.js:153` `assert.equal(node("grid-lock-note").children[1].textContent, "Discard");`
- `tests/operator_grid_releases.test.js:154` `assert.equal(node("grid-lock-note").children[1].className, "btn btn-sm");`
- `tests/operator_grid_releases.test.js:157` `assert.equal(node("grid-lock-note").hidden, false, "a retained draft keeps the note and its focus owner");`
- `tests/operator_grid_releases.test.js:158` `assert.equal(setup.doc.activeElement, lockDiscard, "a refused discard does not focus a disabled preset");`
- `tests/operator_grid_releases.test.js:162` `assert.equal(node("grid-lock-note").hidden, true, "discarding the draft hides the place lock note");`
- `tests/operator_grid_releases.test.js:163` `assert.equal(node("grid-2x2").disabled, false, "discarding the draft re-enables the grid presets");`
- `tests/operator_grid_releases.test.js:164` `assert.equal(setup.doc.activeElement, node("grid-2x2"), "discarding the lock restores focus to the enabled preset");`
- `tests/operator_grid_releases.test.js:172` `assert.equal(node("arrange-membership-summary").textContent, "Order and mounting (2 tablets)");`
- `tests/operator_grid_releases.test.js:177` `assert.equal(blockers.hidden, false, "a blocked measured preview lists its blockers");`
- `tests/operator_grid_releases.test.js:182` `assert.equal(node("arrange-membership").open, true, "the angle blocker opens Order and mounting");`
- `tests/operator_grid_releases.test.js:183` `assert.equal(setup.doc.activeElement, row("a").querySelectorAll("select")[0], "the angle blocker focuses that tablet's angle control");`
- `tests/operator_grid_releases.test.js:185` `const angle = row(id).querySelectorAll("select")[0];`
- `tests/operator_grid_releases.test.js:190` `assert.match(node("grid-message").textContent, /Cannot preview arrangement\. Confirm a model or save measurements/);`

### operator_late_join.test.js · (b)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.deepEqual(owner.view(), beforeObservation, "presentation cannot observe membership, change selected IDs or input versions");; assert.deepEqual(owner.selectedIds(), [], "the late tablet is admitted only by the explicit update step");; assert.equal(item.children[0].children[0].checked, true, "#24 registration before socket readiness must become selected without reload");; assert.equal(Number(item.children[1].children[1].children[0].value), 70, "untouched width uses fresh 900 / 1280 viewport");

Loader evidence:

- `tests/operator_late_join.test.js:4` `const grid = require("../frontend/controller/operator-grid.js");`

DOM/copy pins:

- `tests/operator_late_join.test.js:37` `assert.match(nodes.get("grid-message").textContent, /Rebuild preview explicitly/, "a refreshed unrelated guard cannot authorize the retained grid after model setup");`
- `tests/operator_late_join.test.js:46` `assert.match(nodes.get("grid-message").textContent, /manual draft/);`

### operator_measurements.test.js · (a)

No DOM; pure records, injected API/session doubles.

Behavior evidence: measurement field state builds profile payloads without a DOM; profile pixel validation retains field marking and first-error order; calibration payload retains independent axes, offsets and ruler guard; identical live viewport text is written once per distinct viewport; calibration validation rejects invalid form state with the existing messages

Loader evidence:

- `tests/operator_measurements.test.js:4` `const { createPayloads, liveViewportText, updateLiveViewport } = require("../frontend/controller/operator-measurements.js");`

DOM/copy pins:

- `tests/operator_measurements.test.js:70` `assert.equal(node.textContent, "Selected tablet: 800 × 600 CSS px · DPR 2 · 90° · tab");`

### operator_membership.test.js · (a)

No DOM; pure records, injected API/session doubles.

Behavior evidence: assert.equal(setup.view().first.included, true, "#24 registration before online must become selected without reload");; assert.deepEqual(setup.view().first.size, { w: 70, h: 100 }, "fresh viewport replaces the untouched square fallback");; assert.equal(setup.view().first.included, false, "intentional exclusion survives reconnect");; assert.equal(setup.view().second.included, false, "joins after membership edit require explicit Include");

Loader evidence:

- `tests/operator_membership.test.js:3` `const { membership } = require("../frontend/controller/operator-grid.js");`

DOM/copy pins:

- No literal DOM/copy pin found in the inspected assertion patterns. Data values and exported API names remain contracts.

### operator_physical_stage.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.equal(rosterSummary(mixed, false), "0 online · 4 retained wall positions");; assert.equal(rosterSummary(mixed, true), "Status stale · Last known: 0 online · 4 retained wall positions");; assert.equal(rosterSummary(allRegistered, false), "1 online");; assert.equal(rosterSummary({ layout: { kind: "logical", placements: {} } }, false), "Tablet status unknown");

Loader evidence:

- `tests/operator_physical_stage.test.js:6` `const context = vm.createContext({ window: { OperatorState: require("../frontend/controller/operator-state.js") } });`
- `tests/operator_physical_stage.test.js:7` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/physical-stage.js"), "utf8"), context);`
- `tests/operator_physical_stage.test.js:24` `const stageModel = require("../frontend/controller/operator-stage.js");`
- `tests/operator_physical_stage.test.js:129` `OperatorState: Object.assign({}, require("../frontend/controller/operator-state.js"), { stageView: () => ({}) }),`
- `tests/operator_physical_stage.test.js:150` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-workspace.js"), "utf8"), context);`
- `tests/operator_physical_stage.test.js:151` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/physical-stage.js"), "utf8"), context);`
- `tests/operator_physical_stage.test.js:171` `const composition = require("../frontend/controller/operator-composition.js");`
- `tests/operator_physical_stage.test.js:232` `window.PhysicalSizing = require("../frontend/controller/physical-sizing.js");`
- `tests/operator_physical_stage.test.js:233` `window.OperatorStage = { draw: () => null, helpText: editable => require("../frontend/controller/operator-stage.js").helpText(editable) };`
- `tests/operator_physical_stage.test.js:661` `const window = { OperatorState: require("../frontend/controller/operator-state.js"), OperatorStage: stageModel,`
- `tests/operator_physical_stage.test.js:664` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-workspace.js"), "utf8"), context);`
- `tests/operator_physical_stage.test.js:665` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/physical-stage.js"), "utf8"), context);`
- `tests/operator_physical_stage.test.js:768` `const context = vm.createContext({ window: { OperatorState: require("../frontend/controller/operator-state.js"), addEventListener() {},`
- `tests/operator_physical_stage.test.js:770` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-workspace.js"), "utf8"), context);`
- `tests/operator_physical_stage.test.js:771` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/physical-stage.js"), "utf8"), context);`

DOM/copy pins:

- `tests/operator_physical_stage.test.js:69` `assert.equal(stageModel.exceptionLabel("hidden", "Page hidden"), "Wrong content");`
- `tests/operator_physical_stage.test.js:193` `assert.equal(same.heading.textContent, "b");`
- `tests/operator_physical_stage.test.js:196` `assert.equal(same.document.activeElement, same.node("issue-b"), "clearing the panel returns focus to its exact invoking control");`
- `tests/operator_physical_stage.test.js:202` `assert.equal(gone.document.activeElement, gone.node("issues-title"), "a removed origin uses the surviving fallback");`
- `tests/operator_physical_stage.test.js:584` `assert.equal(statusText("failed")[0].textContent, "Wrong content · Wake lock denied");`
- `tests/operator_physical_stage.test.js:585` `assert.match(slot("failed").getAttribute("aria-label"), /Image failed/);`
- `tests/operator_physical_stage.test.js:586` `assert.match(slot("failed").getAttribute("aria-label"), /Wake lock: denied/);`
- `tests/operator_physical_stage.test.js:590` `assert.equal(statusText("denied")[0].textContent, "Wake lock denied", "a painted tablet still carries an independent power warning");`
- `tests/operator_physical_stage.test.js:594` `assert.match(slot("tiny").getAttribute("aria-label"), /Page hidden/);`
- `tests/operator_physical_stage.test.js:595` `assert.equal(slot("tiny").dataset.status, "hidden");`
- `tests/operator_physical_stage.test.js:619` `assert.equal(slot(id).getAttribute("aria-label"), id + ", Reports current image, Wake lock: denied");`
- `tests/operator_physical_stage.test.js:621` `assert.equal(descendants(slot("offline"), node => node.getAttribute("class") === "operator-slot-status")[0].textContent,`
- `tests/operator_physical_stage.test.js:658` `const el = { deviceList: doc.getElementById("device-list"), wallHealth: doc.getElementById("wall-health"),`
- `tests/operator_physical_stage.test.js:659` `btnWallHealth: doc.getElementById("btn-wall-health"), deviceCount: doc.getElementById("device-count"),`
- `tests/operator_physical_stage.test.js:660` `rosterStatus: doc.getElementById("roster-status") };`
- `tests/operator_physical_stage.test.js:693` `assert.equal(roster.factFor("a", "connection").textContent, "Connected");`
- `tests/operator_physical_stage.test.js:694` `assert.equal(roster.factFor("a", "image").textContent, "Connected");`
- `tests/operator_physical_stage.test.js:695` `assert.equal(roster.factFor("a", "power").textContent, "Wake lock denied");`
- `tests/operator_physical_stage.test.js:696` `assert.equal(roster.pickFor("a").getAttribute("aria-label"), "Tablet a, Connected, Reports current image. Wake lock: denied");`
- `tests/operator_physical_stage.test.js:700` `assert.equal(roster.factFor("b", "connection").textContent, "Connected");`
- `tests/operator_physical_stage.test.js:701` `assert.equal(roster.factFor("b", "image").textContent, "Stale");`
- `tests/operator_physical_stage.test.js:702` `assert.equal(roster.factFor("b", "power").textContent, "Wake lock held");`
- `tests/operator_physical_stage.test.js:703` `assert.equal(roster.factFor("b", "image").textContent.includes("showing"), false, "held power never turns stale paint into displayed");`
- `tests/operator_physical_stage.test.js:705` `assert.equal(roster.factFor("c", "connection").textContent, lastSeen);`
- `tests/operator_physical_stage.test.js:706` `assert.equal(roster.factFor("c", "image").textContent, "Offline");`
- `tests/operator_physical_stage.test.js:708` `assert.equal(roster.factFor("c", "power").textContent, "Last known wake lock unknown");`
- `tests/operator_physical_stage.test.js:711` `assert.equal(roster.factFor("d", "connection").textContent, "Connected");`
- `tests/operator_physical_stage.test.js:712` `assert.equal(roster.factFor("d", "image").textContent, "Connected");`
- `tests/operator_physical_stage.test.js:713` `assert.equal(roster.factFor("d", "power").textContent, "Wake lock released");`
- `tests/operator_physical_stage.test.js:715` `assert.equal(roster.factFor("unplaced", "connection").textContent, "Connected");`
- `tests/operator_physical_stage.test.js:716` `assert.equal(roster.factFor("unplaced", "image").textContent, "Not placed");`
- `tests/operator_physical_stage.test.js:717` `assert.equal(roster.factFor("unplaced", "power").textContent, "Wake lock held");`
- `tests/operator_physical_stage.test.js:718` `assert.equal(roster.pickFor("unplaced").getAttribute("aria-label"), "Tablet unplaced, Connected, No placement. Wake lock: held");`
- `tests/operator_physical_stage.test.js:720` `assert.equal(roster.metaFor("a").children.map(child => child.textContent).join(""), "Connected · Connected · Wake lock denied");`
- `tests/operator_physical_stage.test.js:721` `assert.equal(roster.el.wallHealth.textContent, "1 of 3 showing the current image");`
- `tests/operator_physical_stage.test.js:725` `assert.equal(roster.factFor("c", "connection").textContent, "Offline", "an offline tablet without a timestamp states only the connection fact");`
- `tests/operator_physical_stage.test.js:730` `assert.equal(roster.factFor("a", "connection").textContent, "Status stale");`
- `tests/operator_physical_stage.test.js:731` `assert.equal(roster.factFor("a", "image").textContent, "Stale");`
- `tests/operator_physical_stage.test.js:732` `assert.equal(roster.factFor("a", "power").textContent, "Last known wake lock denied");`
- `tests/operator_physical_stage.test.js:745` `querySelector(selector) { if (selector === "ul") this.ul ||= make("ul"); return this.ul; },`
- `tests/operator_physical_stage.test.js:779` `const el = { stageSvg: { querySelectorAll: () => [], style: {} }, stageScale: doc.getElementById("stage-scale") };`

### operator_readiness.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.equal(known.url.href, "http://192.168.50.1:8080/client/");; assert.equal(known.url.copyable, true);; assert.equal(known.qr.state, "ready");; assert.equal(known.qr.href, "/api/v3/join-qr");

Loader evidence:

- `tests/operator_readiness.test.js:42` `const context = vm.createContext({ window: { OperatorState: require("../frontend/controller/operator-state.js"), location: { origin: "http://127.0.0.1:8000" } }, document: document, URL: URL, Date: Date, JSON: JSON });`
- `tests/operator_readiness.test.js:43` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);`
- `tests/operator_readiness.test.js:44` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-readiness.js"), "utf8"), context);`

DOM/copy pins:

- `tests/operator_readiness.test.js:101` `assert.ok(joined.includes(expected), "missing " + expected);`
- `tests/operator_readiness.test.js:103` `assert.ok(!joined.includes("revision 7") && !joined.includes("generation gen-7") && !joined.includes("schema 3"),`
- `tests/operator_readiness.test.js:125` `assert.ok(!JSON.stringify(malformed).includes("Old-Net"), "guessed aliases must be ignored");`
- `tests/operator_readiness.test.js:126` `assert.ok(!JSON.stringify(malformed).includes("2026-01-01"), "guessed aliases must be ignored");`
- `tests/operator_readiness.test.js:139` `assert.ok(unrecordedText.includes("No backup snapshot is recorded"));`
- `tests/operator_readiness.test.js:140` `assert.ok(unrecordedText.includes("No restore rehearsal recorded. A backup is not proven restorable."));`
- `tests/operator_readiness.test.js:141` `assert.ok(unrecordedText.includes("Not verified. A manifest is a record on disk, not proof that the wall restores."));`
- `tests/operator_readiness.test.js:166` `assert.equal(page.nodes["btn-readiness-refresh"].attrs["aria-label"], "Refresh server checks");`
- `tests/operator_readiness.test.js:170` `assert.equal(page.nodes["btn-readiness-refresh"].disabled, true);`
- `tests/operator_readiness.test.js:171` `assert.equal(page.nodes["btn-readiness-refresh"].attrs["aria-label"], "Refreshing server checks…");`
- `tests/operator_readiness.test.js:177` `assert.equal(page.nodes["tablet-url"].textContent, "http://192.168.50.1:8080/client/");`
- `tests/operator_readiness.test.js:178` `assert.equal(page.nodes["tablet-join-line"].hidden, false);`
- `tests/operator_readiness.test.js:179` `assert.equal(page.nodes["tablet-qr-figure"].hidden, false);`
- `tests/operator_readiness.test.js:181` `assert.equal(page.nodes["readiness-errors"].hidden, true);`
- `tests/operator_readiness.test.js:183` `assert.equal(page.nodes["readiness-refreshed"].hidden, true, "a healthy read has one timestamp");`
- `tests/operator_readiness.test.js:184` `assert.ok(factsText(page.nodes).includes("Wall-Net"));`
- `tests/operator_readiness.test.js:185` `assert.ok(!factsText(page.nodes).includes("Backup proof"), "routine server checks lead with connection facts");`
- `tests/operator_readiness.test.js:186` `assert.ok(page.nodes["operator-readiness-backup"].children.some(node => node.textContent === "Backup proof"),`
- `tests/operator_readiness.test.js:188` `assert.ok(page.nodes["operator-readiness-backup"].children.some(node => node.textContent === "Restore rehearsal"));`
- `tests/operator_readiness.test.js:189` `assert.ok(!page.nodes["operator-readiness-details"].children.some(node => node.textContent === "Backup proof"),`
- `tests/operator_readiness.test.js:199` `assert.ok(!factsText(page.nodes).includes("Live tablet status"), "live display evidence belongs to the header");`
- `tests/operator_readiness.test.js:200` `assert.ok(page.nodes["operator-readiness-details"].children.some(node => node.textContent === "Connected tablets"),`
- `tests/operator_readiness.test.js:204` `assert.ok(!factsText(page.nodes).includes("Last known"), "roster failure does not rewrite independent server evidence");`
- `tests/operator_readiness.test.js:214` `assert.ok(factsText(page.nodes).includes("Wall-Net"), "config snapshots cannot erase fetched readiness");`
- `tests/operator_readiness.test.js:219` `assert.equal(page.nodes["tablet-qr-error"].hidden, false);`
- `tests/operator_readiness.test.js:221` `assert.equal(page.nodes["tablet-qr-error"].hidden, true);`
- `tests/operator_readiness.test.js:234` `assert.equal(page.nodes["tablet-qr"].hidden, true, "the old bitmap is hidden until the new image loads");`
- `tests/operator_readiness.test.js:238` `assert.equal(page.nodes["tablet-qr"].hidden, true, "an obsolete load cannot reveal the previous QR");`
- `tests/operator_readiness.test.js:241` `assert.equal(page.nodes["tablet-qr"].hidden, false);`
- `tests/operator_readiness.test.js:249` `assert.match(failed.nodes["readiness-status"].textContent, /403 forbidden/);`
- `tests/operator_readiness.test.js:250` `assert.match(failed.nodes["readiness-status"].textContent, /Refresh to try again/);`
- `tests/operator_readiness.test.js:251` `assert.equal(failed.nodes["btn-readiness-refresh"].attrs["aria-label"], "Retry server checks");`
- `tests/operator_readiness.test.js:252` `assert.equal(failed.nodes["btn-readiness-refresh"].attrs["aria-label"], "Retry server checks", "the accessible name keeps the visible verb and names its region");`
- `tests/operator_readiness.test.js:253` `assert.equal(failed.nodes["btn-readiness-refresh"].disabled, false);`
- `tests/operator_readiness.test.js:254` `assert.equal(failed.nodes["tablet-join-line"].hidden, true, "no address means no line and no Copy");`
- `tests/operator_readiness.test.js:260` `assert.equal(failed.nodes["btn-readiness-refresh"].attrs["aria-label"], "Refresh server checks");`
- `tests/operator_readiness.test.js:268` `assert.match(wrong.nodes["readiness-status"].textContent, /did not include the expected fields/);`
- `tests/operator_readiness.test.js:276` `assert.equal(issues.nodes["readiness-errors"].hidden, false);`
- `tests/operator_readiness.test.js:277` `assert.match(issues.nodes["readiness-errors"].textContent, /TABLET_WALL_TABLET_ORIGIN is not configured/);`
- `tests/operator_readiness.test.js:279` `assert.match(issues.nodes["readiness-status"].textContent, /with 1 issue below/);`
- `tests/operator_readiness.test.js:285` `assert.equal(failed.nodes["readiness-message"].textContent, "Tablet address copied.");`

### operator_regions_updates.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: injected region references survive relocation and admit late parsed controls; draft views cannot mutate a feature's nested record; renderAll observes content and grid before any presentation

Loader evidence:

- `tests/operator_regions_updates.test.js:6` `const dom = require("../frontend/controller/operator-dom.js");`
- `tests/operator_regions_updates.test.js:38` `const source = fs.readFileSync(require.resolve("../frontend/controller/physical.js"), "utf8");`
- `tests/operator_regions_updates.test.js:39` `vm.runInNewContext(source.slice(source.indexOf("    function renderAll()"), source.indexOf("    function syncDiagnosticColours()")), context);`

DOM/copy pins:

- No literal DOM/copy pin found in the inspected assertion patterns. Data values and exported API names remain contracts.

### operator_saved_actions.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.ok(offset >= 0 && source.indexOf(end, offset) > offset);; assert.equal(preview().disabled, false);; assert.equal(damaged().disabled, true);; assert.equal(deletion().disabled, false, "damaged content remains deletable");

Loader evidence:

- `tests/operator_saved_actions.test.js:6` `const source = fs.readFileSync(require.resolve("../frontend/controller/physical.js"), "utf8");`
- `tests/operator_saved_actions.test.js:10` `return source.slice(offset, source.indexOf(end, offset));`
- `tests/operator_saved_actions.test.js:52` `vm.runInContext(extract("    let compositionBusy = false;", "    const profileCache")`
- `tests/operator_saved_actions.test.js:62` `const render = () => vm.runInContext("savedScenes = entries; renderSavedScenes();", ctx);`

DOM/copy pins:

- `tests/operator_saved_actions.test.js:26` `return this.children.flatMap(child => [child, ...child.querySelectorAll()]).filter(child => child.type === "button");`
- `tests/operator_saved_actions.test.js:63` `const button = name => node("saved-scenes").querySelectorAll().find(item => item.attrs["aria-label"] === name);`
- `tests/operator_saved_actions.test.js:77` `assert.equal(deletion().disabled, false, "damaged content remains deletable");`
- `tests/operator_saved_actions.test.js:80` `assert.equal(preview().disabled, true, "busy entry disables an already-rendered saved Preview");`
- `tests/operator_saved_actions.test.js:81` `assert.equal(deletion().disabled, true, "busy entry also disables saved Delete");`
- `tests/operator_saved_actions.test.js:86` `assert.equal(damaged().disabled, true, "busy exit retains the damaged-preview restriction");`
- `tests/operator_saved_actions.test.js:89` `assert.equal(preview().disabled, false, "content rendered during a command becomes available when it ends");`
- `tests/operator_saved_actions.test.js:91` `assert.equal(preview().disabled, true, "session commands use the same availability projection");`
- `tests/operator_saved_actions.test.js:93` `assert.equal(preview().disabled, true, "composition completion cannot unlock a busy session");`
- `tests/operator_saved_actions.test.js:100` `assert.equal(preview().disabled, true, "a recall receipt does not unlock Preview before its saved-list read completes");`
- `tests/operator_saved_actions.test.js:124` `assert.equal(failure.button("Preview content “Landscape”").disabled, false, "failed follow-up read also releases command availability");`

### operator_session.test.js · (a)

No DOM; pure records, injected API/session doubles.

Behavior evidence: assert.equal(session.state, undefined, "session does not expose mutable authority");; assert.throws(() => { session.view().config.runtime.devices.a.online = false; }, TypeError);; await assert.rejects(() => session.request("POST", "/api/v3/layout/clear", { confirm: true }, { etag: true }), /progress/);; assert.equal((await old).runtime.devices.a.render.state, "displayed", "late command response cannot regress newer runtime with the same durable ETag");

Loader evidence:

- `tests/operator_session.test.js:3` `const { create } = require("../frontend/controller/operator-session.js");`

DOM/copy pins:

- No literal DOM/copy pin found in the inspected assertion patterns. Data values and exported API names remain contracts.

### operator_stage_fit.test.js · (b)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.equal(result.width, 966, "well padding and field borders are excluded");; assert.equal(parseFloat(field.style.inlineSize), 968);; assert.equal(result.width / result.height, 720 / 370);; assert.equal(observers[0].node, well, "the persistent well owns observation");

Loader evidence:

- `tests/operator_stage_fit.test.js:3` `const { fit: fitMeasured, draw } = require("../frontend/controller/operator-stage.js");`
- `tests/operator_stage_fit.test.js:4` `const stageModel = require("../frontend/controller/operator-state.js");`
- `tests/operator_stage_fit.test.js:61` `const { create, measureWell } = require("../frontend/controller/operator-stage-viewport.js");`
- `tests/operator_stage_fit.test.js:175` `compareIds: (a, b) => require("../frontend/controller/operator-state.js").compareIds(roster, {}, a, b) };`

DOM/copy pins:

- `tests/operator_stage_fit.test.js:90` `assert.equal(label.textContent, "2", "small labels preserve the distinguishing number");`
- `tests/operator_stage_fit.test.js:98` `assert.equal(fit(), null, "a hidden well cannot supply a fitting rectangle");`

### operator_state.test.js · (a)

No DOM; pure records, injected API/session doubles.

Behavior evidence: assert.equal(draft.kind, "logical");; assert.equal(draft.width, 320);; assert.equal(draft.bounds, undefined, "logical dimensions must never seed millimetre bounds");; assert.equal(logical.placements.one.w, 80, "draft must not mutate committed geometry");

Loader evidence:

- `tests/operator_state.test.js:3` `const model = require("../frontend/controller/operator-state.js");`
- `tests/operator_state.test.js:4` `const tabletView = require("../frontend/client/view.js");`

DOM/copy pins:

- No literal DOM/copy pin found in the inspected assertion patterns. Data values and exported API names remain contracts.

### operator_subject_saves.test.js · (b)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: a pending label save stays keyed to A after selection changes to B; a pending 

Loader evidence:

- `tests/operator_subject_saves.test.js:4` `const composition = require("../frontend/controller/operator-composition.js");`
- `tests/operator_subject_saves.test.js:5` `const forms = require("../frontend/controller/operator-forms.js");`
- `tests/operator_subject_saves.test.js:6` `const measurements = require("../frontend/controller/operator-measurements.js");`
- `tests/operator_subject_saves.test.js:26` `global.window = { OperatorState: require("../frontend/controller/operator-state.js") };`
- `tests/operator_subject_saves.test.js:41` `const devices = require("../frontend/controller/operator-devices.js").create({`
- `tests/operator_subject_saves.test.js:84` `elements, physicalCalibration: require("../frontend/controller/physical-calibration.js"),`

DOM/copy pins:

- `tests/operator_subject_saves.test.js:59` `assert.equal(node("tablet-label").value, "Unsaved name for B");`
- `tests/operator_subject_saves.test.js:110` `assert.equal(elements[group === "profile" ? "profileMsg" : "calibrationMsg"].textContent, "");`

### operator_sync.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.equal(requests.length, 1, "slow reconciliation starts after socket subscription");; assert.deepEqual(received.map(item => item.config.revision), [8], "slower HTTP read cannot overwrite socket snapshot");; assert.equal(received[0].options.preserveDraft, true);; assert.equal(state.etagState, "stale", "writes wait for the new authoritative configuration");

Loader evidence:

- `tests/operator_sync.test.js:5` `const model = require("../frontend/controller/operator-state.js");`
- `tests/operator_sync.test.js:16` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-sync.js"), "utf8"), context);`

DOM/copy pins:

- No literal DOM/copy pin found in the inspected assertion patterns. Data values and exported API names remain contracts.

### operator_unreachable.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.equal(network.state.rosterUnreachable, true, "a transport failure marks the server unreachable");; assert.equal(server.state.rosterUnreachable, false, "an HTTP error from a reachable server is stale, not unreachable");; assert.equal(server.state.rosterError, "503 unavailable");; assert.equal(reworded.state.rosterUnreachable, true, "the decision does not depend on message wording");

Loader evidence:

- `tests/operator_unreachable.test.js:5` `const model = require("../frontend/controller/operator-state.js");`
- `tests/operator_unreachable.test.js:12` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-sync.js"), "utf8"), context);`

DOM/copy pins:

- `tests/operator_unreachable.test.js:32` `assert.equal(reworded.state.rosterUnreachable, true, "the decision does not depend on message wording");`

### operator_upload.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.match(f.node("upload-message").textContent, /completion is uncertain/);; assert.equal(f.node("upload-submit").disabled, true);; f.submit(); assert.equal(f.requests.length, 1, "ambiguous completion blocks another transport send");; assert.equal(f.node("upload-submit").disabled, true, "a read begun before uncertainty cannot reconcile it");

Loader evidence:

- `tests/operator_upload.test.js:6` `const model = require("../frontend/controller/operator-state.js");`
- `tests/operator_upload.test.js:29` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);`
- `tests/operator_upload.test.js:30` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-content.js"), "utf8"), context);`

DOM/copy pins:

- `tests/operator_upload.test.js:54` `assert.match(f.node("upload-message").textContent, /completion is uncertain/);`
- `tests/operator_upload.test.js:55` `assert.equal(f.node("upload-submit").disabled, true);`
- `tests/operator_upload.test.js:58` `assert.equal(f.node("upload-submit").disabled, true, "a read begun before uncertainty cannot reconcile it");`
- `tests/operator_upload.test.js:59` `assert.equal(f.node("refresh-images").disabled, false);`
- `tests/operator_upload.test.js:62` `assert.equal(f.node("upload-submit").disabled, true, "failed inventory refresh keeps the lock");`
- `tests/operator_upload.test.js:65` `assert.equal(f.node("upload-submit").disabled, false);`
- `tests/operator_upload.test.js:71` `assert.match(f.node("upload-message").textContent, /Image addition refused/);`
- `tests/operator_upload.test.js:72` `assert.equal(f.node("upload-submit").disabled, false);`
- `tests/operator_upload.test.js:78` `assert.equal(f.node("upload-form").hidden, true, "refused admission hides the upload form");`
- `tests/operator_upload.test.js:83` `assert.equal(f.node("upload-form").hidden, true, "unknown admission hides the upload form");`
- `tests/operator_upload.test.js:95` `assert.match(f.node("upload-message").textContent, /Image added and selected/);`
- `tests/operator_upload.test.js:102` `assert.match(f.node("upload-message").textContent, /Image added to the library/);`
- `tests/operator_upload.test.js:112` `assert.match(f.node("upload-message").textContent, /Image added to the library/);`
- `tests/operator_upload.test.js:128` `assert.match(f.node("upload-message").textContent, /Image added to the library/);`
- `tests/operator_upload.test.js:151` `assert.match(f.node("upload-message").textContent, /completion is uncertain/);`
- `tests/operator_upload.test.js:152` `assert.equal(f.node("upload-submit").disabled, true);`
- `tests/operator_upload.test.js:161` `assert.equal(f.node("upload-submit").disabled, false);`
- `tests/operator_upload.test.js:172` `assert.match(f.node("upload-message").textContent, /completion is uncertain/);`
- `tests/operator_upload.test.js:173` `assert.equal(f.node("upload-submit").disabled, true);`
- `tests/operator_upload.test.js:187` `assert.match(f.node("fit-summary").textContent, /^Preview Fill/);`
- `tests/operator_upload.test.js:192` `assert.match(f.node("fit-summary").textContent, /^Preview Fit/);`
- `tests/operator_upload.test.js:193` `assert.equal(f.node("crop-width").textContent, "50% of wall width uncovered");`

### operator_wall_status.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.deepEqual(stage.fleetPower(denied), { state: "denied", label: "denied", count: 2 });; assert.deepEqual(stage.fleetPower([...denied, entry("c", "held", false)]), { state: "denied", label: "denied", count: 2 });; assert.equal(stage.fleetPower([entry("a"), entry("b", "released")]), null);; assert.equal(stage.fleetPower([]), null);

Loader evidence:

- `tests/operator_wall_status.test.js:5` `const model = require("../frontend/controller/operator-state.js");`
- `tests/operator_wall_status.test.js:6` `const stage = require("../frontend/controller/operator-stage.js");`
- `tests/operator_wall_status.test.js:52` `const source = fs.readFileSync(require.resolve("../frontend/controller/operator-workspace.js"), "utf8");`
- `tests/operator_wall_status.test.js:54` `vm.runInContext(source.slice(source.indexOf("        function renderProblems("), source.indexOf("        const powerFor =", source.indexOf("        function renderProblems("))), context);`

DOM/copy pins:

- `tests/operator_wall_status.test.js:61` `assert.equal($("wall-status-summary").textContent, "Content report issues: 2");`
- `tests/operator_wall_status.test.js:62` `assert.equal($("wall-power-summary").textContent, "", "wake-lock reports belong only in the selected Tablet panel");`
- `tests/operator_wall_status.test.js:64` `assert.equal(button.textContent, "▲ Tablet 2 wrong content");`
- `tests/operator_wall_status.test.js:65` `assert.match(button.attrs["aria-label"], /Image failed.*Review recovery/);`
- `tests/operator_wall_status.test.js:71` `assert.equal($("wall-power-summary").textContent, "", "mixed wake states cannot produce a fleet claim");`
- `tests/operator_wall_status.test.js:72` `assert.equal($("wall-power-summary").textContent, "");`
- `tests/operator_wall_status.test.js:74` `assert.equal($("wall-power-summary").textContent, "", "stale evidence cannot produce a fleet claim");`
- `tests/operator_wall_status.test.js:80` `render(); assert.equal($("wall-status-summary").textContent, "Content report issues: 1");`
- `tests/operator_wall_status.test.js:82` `render(); assert.equal($("wall-status-summary").textContent, "Content report issues: 0");`
- `tests/operator_wall_status.test.js:87` `assert.equal(rows.get("+more").button.textContent, "+2");`
- `tests/operator_wall_status.test.js:88` `assert.match(rows.get("+more").button.attrs["aria-label"], /Open Tablets to review all/);`
- `tests/operator_wall_status.test.js:102` `assert.equal(rows.get("+more").button.textContent, "+1");`

### operator_workspace.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.equal(keyboard.document.activeElement, keyboard.element("resolve-stay"), "every opening starts on Stay");; assert.equal(tab(keyboard.element("resolve-stay")), true, "Tab at the final draft action prevents the native BODY stop");; assert.equal(keyboard.document.activeElement, keyboard.element("resolve-commit"));; assert.equal(tab(keyboard.element("resolve-commit"), true), true, "reverse Tab wraps from the first draft action");

Loader evidence:

- `tests/operator_workspace.test.js:25` `vm.runInNewContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8") + "\n" + fs.readFileSync(require.resolve("../frontend/controller/operator-workspace.js"), "utf8"),`
- `tests/operator_workspace.test.js:53` `vm.runInNewContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8") + "\n" + fs.readFileSync(require.resolve("../frontend/controller/operator-workspace.js"), "utf8"),`

DOM/copy pins:

- `tests/operator_workspace.test.js:19` `querySelectorAll() { return [element("resolve-commit"), element("resolve-discard"), element("resolve-stay")]; },`
- `tests/operator_workspace.test.js:74` `assert.equal(keyboard.document.activeElement, keyboard.element("resolve-stay"), "every opening starts on Stay");`
- `tests/operator_workspace.test.js:82` `assert.equal(tab(keyboard.element("resolve-stay")), true, "Tab at the final draft action prevents the native BODY stop");`
- `tests/operator_workspace.test.js:83` `assert.equal(keyboard.document.activeElement, keyboard.element("resolve-commit"));`
- `tests/operator_workspace.test.js:84` `assert.equal(tab(keyboard.element("resolve-commit"), true), true, "reverse Tab wraps from the first draft action");`
- `tests/operator_workspace.test.js:85` `assert.equal(keyboard.document.activeElement, keyboard.element("resolve-stay"));`
- `tests/operator_workspace.test.js:100` `assert.equal(tab(keyboard.element("resolve-stay")), true);`
- `tests/operator_workspace.test.js:101` `assert.equal(keyboard.document.activeElement, keyboard.element("resolve-discard"), "disabled commit is skipped at the boundary");`
- `tests/operator_workspace.test.js:103` `assert.equal(tab(keyboard.element("resolve-discard"), true), true);`
- `tests/operator_workspace.test.js:104` `assert.equal(keyboard.document.activeElement, keyboard.element("resolve-discard"), "a single rendered action wraps to itself");`
- `tests/operator_workspace.test.js:107` `assert.equal(tab(keyboard.element("resolve-discard")), true);`
- `tests/operator_workspace.test.js:108` `assert.equal(keyboard.document.activeElement, keyboard.element("resolve-discard"), "visibility-hidden actions cannot own focus");`
- `tests/operator_workspace.test.js:121` `assert.equal(keyboard.document.activeElement, keyboard.element("tab-content"), "an invisible trigger uses a visible fallback");`
- `tests/operator_workspace.test.js:129` `assert.equal(nativeClose.document.activeElement, nativeClose.element("trigger"), "native close restores the exact visible trigger");`
- `tests/operator_workspace.test.js:134` `assert.equal(document.activeElement, element("resolve-stay"));`
- `tests/operator_workspace.test.js:135` `assert.equal(element("resolve-commit").textContent, "Apply arrangement");`
- `tests/operator_workspace.test.js:139` `assert.equal(element("draft-resolution").open, true, "the remaining image must be reviewed before continuing");`
- `tests/operator_workspace.test.js:140` `assert.equal(element("resolve-commit").textContent, "Show image");`
- `tests/operator_workspace.test.js:141` `assert.equal(document.activeElement, element("resolve-stay"), "the second combined review also starts on Stay");`
- `tests/operator_workspace.test.js:152` `assert.equal(second.document.activeElement, second.element("resolve-stay"), "a successful first commit cannot become the next default");`

### operator_workspace_composition.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.equal(node("commit-applied-name").textContent, "On wall: a.png");; assert.equal(node("setup-strip").hidden, true);; assert.equal(node("commit-bar").dataset.commit, "idle", "the commit bar is present even without a draft");; assert.equal(node("stage-mode-label").textContent, "Showing");

Loader evidence:

- `tests/operator_workspace_composition.test.js:19` `const composition = require("../frontend/controller/operator-composition.js");`
- `tests/operator_workspace_composition.test.js:24` `const context = { window: { OperatorState: require("../frontend/controller/operator-state.js") }, document };`
- `tests/operator_workspace_composition.test.js:26` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);`
- `tests/operator_workspace_composition.test.js:27` `vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-workspace.js"), "utf8"), context);`
- `tests/operator_workspace_composition.test.js:109` `const controller = fs.readFileSync(require.resolve("../frontend/controller/physical.js"), "utf8");`
- `tests/operator_workspace_composition.test.js:111` `const forms = require("../frontend/controller/operator-forms.js").create();`
- `tests/operator_workspace_composition.test.js:120` `vm.runInContext(controller.slice(controller.indexOf("    function syncTabDots("), controller.indexOf("    function syncTopbarTransport(")), ctx);`
- `tests/operator_workspace_composition.test.js:134` `const html = fs.readFileSync(require.resolve("../frontend/controller/physical.html"), "utf8");`
- `tests/operator_workspace_composition.test.js:164` `const source = fs.readFileSync(require.resolve("../frontend/controller/physical.js"), "utf8");`
- `tests/operator_workspace_composition.test.js:165` `const extract = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));`
- `tests/operator_workspace_composition.test.js:173` `} }, window: { OperatorState: require("../frontend/controller/operator-state.js") },`
- `tests/operator_workspace_composition.test.js:182` `vm.runInContext("let layoutsVersion = 0, scenesVersion = 0, savedScenes = [], layoutsLoaded = false, scenesLoaded = false; let operatorDevices = null;"`
- `tests/operator_workspace_composition.test.js:194` `assert.equal(vm.runInContext("layoutsLoaded && scenesLoaded", ctx), true);`

DOM/copy pins:

- `tests/operator_workspace_composition.test.js:16` `querySelector() { return node(id + "-summary"); }, focus() { document.activeElement = this; } });`
- `tests/operator_workspace_composition.test.js:33` `assert.equal(node("commit-applied-name").textContent, "On wall: a.png");`
- `tests/operator_workspace_composition.test.js:34` `assert.equal(node("setup-strip").hidden, true);`
- `tests/operator_workspace_composition.test.js:35` `assert.equal(node("commit-bar").dataset.commit, "idle", "the commit bar is present even without a draft");`
- `tests/operator_workspace_composition.test.js:36` `assert.equal(node("stage-mode-label").textContent, "Showing");`
- `tests/operator_workspace_composition.test.js:40` `assert.equal(document.activeElement, node("edited-field"), "rendering never takes keyed field focus");`
- `tests/operator_workspace_composition.test.js:45` `assert.equal(node("stage-mode-label").textContent, "Unavailable image", "unavailable content is never described as showing");`
- `tests/operator_workspace_composition.test.js:49` `assert.equal(node("stage-mode-description").textContent, "Image preview, not shown");`
- `tests/operator_workspace_composition.test.js:50` `assert.equal(node("commit-bar").dataset.commit, "image");`
- `tests/operator_workspace_composition.test.js:51` `assert.match(node("draft-state").textContent, /b.png.*not on wall/);`
- `tests/operator_workspace_composition.test.js:52` `assert.equal(node("show-image").classList.values.has("btn-primary"), true);`
- `tests/operator_workspace_composition.test.js:53` `assert.equal(node("tablet-arrange").classList.values.has("btn-primary"), false, "draft commit takes priority over tablet actions");`
- `tests/operator_workspace_composition.test.js:57` `assert.equal(node("image-addition").open, true);`
- `tests/operator_workspace_composition.test.js:58` `assert.equal(document.activeElement, node("image-addition-summary"), "unadmitted uploads focus the explanation");`
- `tests/operator_workspace_composition.test.js:60` `assert.equal(document.activeElement, node("upload-file"));`
- `tests/operator_workspace_composition.test.js:62` `assert.equal(node("stage-mode-label").textContent, "Showing tablet colours");`
- `tests/operator_workspace_composition.test.js:63` `assert.equal(node("commit-bar").dataset.commit, "idle");`
- `tests/operator_workspace_composition.test.js:65` `assert.equal(node("draft-state").textContent, "No image yet · tablet colours");`
- `tests/operator_workspace_composition.test.js:66` `assert.equal(node("first-wall-image-action").classList.values.has("btn-primary"), true);`
- `tests/operator_workspace_composition.test.js:68` `assert.equal(node("stage-mode-label").textContent, "Showing calibration pattern");`
- `tests/operator_workspace_composition.test.js:69` `assert.equal(node("restore-image").classList.values.has("btn-primary"), true, "test restore precedes the selected tablet");`
- `tests/operator_workspace_composition.test.js:71` `assert.equal(node("stage-mode-label").textContent, "Nothing shown", "a scene without wall positions cannot claim to be showing");`
- `tests/operator_workspace_composition.test.js:72` `assert.equal(node("join-strip").hidden, true, "joined tablets replace the join card");`
- `tests/operator_workspace_composition.test.js:73` `assert.equal(node("setup-strip").hidden, false);`
- `tests/operator_workspace_composition.test.js:74` `assert.equal(node("first-wall-join").dataset.done, "true");`
- `tests/operator_workspace_composition.test.js:76` `assert.equal(node("first-wall-arrange-action").classList.values.has("btn-primary"), true, "only the current step's action is the filled primary");`
- `tests/operator_workspace_composition.test.js:77` `assert.equal(node("first-wall-image-action").classList.values.has("btn-primary"), false);`
- `tests/operator_workspace_composition.test.js:81` `assert.equal(node("grid-preview").classList.values.has("btn-primary"), true);`
- `tests/operator_workspace_composition.test.js:82` `assert.equal(node("first-wall-arrange-action").classList.values.has("btn-primary"), false);`
- `tests/operator_workspace_composition.test.js:83` `assert.equal(document.activeElement, node("grid-preview"));`
- `tests/operator_workspace_composition.test.js:87` `assert.equal(document.activeElement, node("copy-tablet-url"));`
- `tests/operator_workspace_composition.test.js:89` `assert.equal(node("first-wall-arrange-action").disabled, true);`
- `tests/operator_workspace_composition.test.js:90` `assert.equal(node("tablet-joining").open, true);`
- `tests/operator_workspace_composition.test.js:92` `assert.equal(node("tablet-joining").open, false);`
- `tests/operator_workspace_composition.test.js:94` `assert.equal(node("tablet-joining").open, true, "runtime updates preserve disclosure state");`
- `tests/operator_workspace_composition.test.js:96` `assert.equal(node("setup-strip").hidden, false, "a placed wall with no image still has a step to finish");`
- `tests/operator_workspace_composition.test.js:98` `assert.equal(node("first-wall-image-action").classList.values.has("btn-primary"), true);`
- `tests/operator_workspace_composition.test.js:100` `assert.equal(node("setup-strip").hidden, true, "the strip disappears once tablets are placed and an image is shown");`
- `tests/operator_workspace_composition.test.js:123` `assert.equal(entries[0].tab.attrs["aria-label"], "Content, unsaved changes");`
- `tests/operator_workspace_composition.test.js:127` `ctx.syncTabDots(); assert.equal(node("device-sheet").dataset.dirty, "true", "tablet field drafts belong to the Tablet panel");`
- `tests/operator_workspace_composition.test.js:130` `ctx.syncTabDots(); assert.equal(node("device-sheet").dataset.dirty, "false");`
- `tests/operator_workspace_composition.test.js:144` `assert.ok(content.includes('id="saved-scenes"'));`
- `tests/operator_workspace_composition.test.js:145` `for (const id of ["saved-layouts", "return-point"]) assert.ok(arrange.includes('id="' + id + '"'));`
- `tests/operator_workspace_composition.test.js:146` `assert.ok(test.includes('id="presentation-checks"'));`
- `tests/operator_workspace_composition.test.js:148` `for (const id of ["tablet-label-form", "measurement-details", "profile-form", "calibration-form", "cal-live-viewport"]) assert.ok(tablet.includes('id="' + id + '"'), "Tablet panel retains " + id);`
- `tests/operator_workspace_composition.test.js:150` `assert.ok(server.includes('id="' + id + '"'), "Server drawer owns " + id);`
- `tests/operator_workspace_composition.test.js:153` `assert.equal(count(id), 1); assert.ok(html.includes('data-form="' + id + '"'), "keyed form contract retained");`
- `tests/operator_workspace_composition.test.js:170` `const ctx = { state: startupState, API_LAYOUTS: "/api/v3/layouts", document: { activeElement: null, getElementById(id) {`

### physical_calibration.test.js · (a)

No DOM; pure records, injected API/session doubles.

Behavior evidence: assert.deepEqual(selectedViewport(roster, "tablet"), viewport);; assert.equal(selectedViewport(roster, "missing"), null);; assert.equal(selectedViewport({ tablet: { online: false, viewport } }, "tablet"), null);; assert.equal(selectedViewport({ tablet: { online: true } }, "tablet"), null);

Loader evidence:

- `tests/physical_calibration.test.js:3` `const { selectedViewport, rulerScale, rulerUrl, rulerCheckBodies, RulerReview } = require("../frontend/controller/physical-calibration.js");`

DOM/copy pins:

- No literal DOM/copy pin found in the inspected assertion patterns. Data values and exported API names remain contracts.

### physical_sizing.test.js · (a)

No DOM; pure records, injected API/session doubles.

Behavior evidence: assert.deepEqual(zero, { x: -53, y: -34, width: 106, height: 68 }, "0° includes body bezels");; assert.ok(Math.abs(quarter.width - 68) < 1e-9 && Math.abs(quarter.height - 106) < 1e-9,; assert.ok(Math.abs(diagonal.width - Math.sqrt(7200)) < 1e-9);; assert.equal(diagonal.width, diagonal.height, "45° uses the rotated axis-aligned footprint");

Loader evidence:

- `tests/physical_sizing.test.js:4` `const sizing = require("../frontend/controller/physical-sizing.js");`

DOM/copy pins:

- No literal DOM/copy pin found in the inspected assertion patterns. Data values and exported API names remain contracts.

### ruler.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: long ruler fits both endpoint targets within usable ; short-span retains a labelled 200 CSS px option and fits smaller viewports; zoom hides the targets, fullscreen redraws actual lengths and close removes handlers and overlay; a late welcome identity resizes both spans when the header grows

Loader evidence:

- `tests/ruler.test.js:6` `const source = fs.readFileSync(require.resolve("../frontend/client/ruler.js"), "utf8");`
- `tests/ruler.test.js:30` `vm.runInNewContext(source, { window, document: { body, createElement: node,`

DOM/copy pins:

- `tests/ruler.test.js:44` `assert.equal(h.ids["ruler-horizontal-label"].textContent, `Horizontal: 0 to ${w} CSS px`);`
- `tests/ruler.test.js:45` `assert.equal(h.ids["ruler-vertical-label"].textContent, `Vertical: 0 to ${v} CSS px`);`
- `tests/ruler.test.js:64` `assert.equal(h.ids["ruler-horizontal"].hidden, true);`
- `tests/ruler.test.js:65` `assert.equal(h.ids["ruler-vertical"].hidden, true);`
- `tests/ruler.test.js:66` `assert.match(h.ids["ruler-zoom"].textContent, /100%/);`
- `tests/ruler.test.js:69` `assert.equal(h.ids["ruler-vertical"].hidden, false);`

### stage_preview_editing.test.js · (c)

Hand-built nodes, document lookup, class/attribute/event or SVG stubs; inspect the pins below.

Behavior evidence: assert.equal(state.draft.placements.a.x, 2, guard + " prevents edits");; assert.equal(state.draft.placements.a.x, 2, tab + " keeps geometry unchanged");; assert.equal(state.draft.placements.a.y, 3, tab + " keeps geometry unchanged");; assert.equal(state.draft.placements.a.x, 3);

Loader evidence:

- `tests/stage_preview_editing.test.js:5` `const context = { window: { OperatorState: require("../frontend/controller/operator-state.js") } };`
- `tests/stage_preview_editing.test.js:6` `vm.runInNewContext(fs.readFileSync("frontend/controller/physical-stage.js", "utf8"), context);`

DOM/copy pins:

- No literal DOM/copy pin found in the inspected assertion patterns. Data values and exported API names remain contracts.

## Python tests touching frontend assets and contracts

All Python tests use pytest; HTTP tests generally use isolated FastAPI TestClient plus temporary storage (tests/conftest.py:1). They survive controller framework choice unless routes, resource paths, response shapes or admission change. Backend internals monkeypatches remain implementation coupling to Python, not React. The following automatic inventory includes every test_*.py with literal frontend/page references, plus the explicitly requested asset-cache suite. Each entry lists test functions and the actual asset references. Driver-unit tests validate harness logic, not shipped UI.

### test_api.py

`tests/test_api.py:16` test_root_returns_greeting; `tests/test_api.py:33` test_frontend_files_must_be_revalidated; `tests/test_api.py:46` test_unchanged_frontend_file_revalidates_to_304; `tests/test_api.py:62` test_app_pages_are_served; `tests/test_api.py:85` test_frontend_assets_are_reachable; `tests/test_api.py:91` test_unknown_route_returns_404; `tests/test_api.py:96` test_register_device_reports_success; `tests/test_api.py:105` test_registered_device_appears_in_roster; `tests/test_api.py:115` test_registration_records_utc_last_seen; `tests/test_api.py:124` test_re_registration_updates_without_duplicating; `tests/test_api.py:136` test_empty_roster_returns_empty_object; `tests/test_api.py:139` test_get_register_endpoint_explains_post; `tests/test_api.py:156` test_register_rejects_bad_device_id; `tests/test_api.py:164` test_register_rejects_missing_fields; `tests/test_api.py:169` test_register_rejects_non_numeric_dimensions; `tests/test_api.py:174` test_rejected_registration_leaves_roster_untouched

- `tests/test_api.py:25` `"/client/",`
- `tests/test_api.py:26` `"/client/client.js",`
- `tests/test_api.py:27` `"/client/client.css",`
- `tests/test_api.py:28` `"/controller/",`
- `tests/test_api.py:29` `"/controller/controller.js",`
- `tests/test_api.py:30` `"/controller/controller.css",`
- `tests/test_api.py:36` `Without ``Cache-Control`` a browser may reuse ``client.js`` for hours`
- `tests/test_api.py:47` `etag = client.get("/client/client.js").headers["etag"]`
- `tests/test_api.py:49` `again = client.get("/client/client.js", headers={"if-none-match": etag})`
- `tests/test_api.py:56` `("/client/", ["client.css", "client.js"]),`
- `tests/test_api.py:57` `("/controller/", ["operator-workspace.css", "operator-entry.js"]),`
- `tests/test_api.py:58` `("/controller/physical.html", ["operator-workspace.css", "physical.js"]),`
- `tests/test_api.py:59` `("/controller/experimental.html", ["controller.css", "controller.js"]),`
- `tests/test_api.py:79` `"/client/client.js",`
- `tests/test_api.py:80` `"/client/client.css",`
- `tests/test_api.py:81` `"/controller/controller.js",`
- `tests/test_api.py:82` `"/controller/controller.css",`

### test_asset_cache.py

`tests/test_asset_cache.py:36` test_repeated_reads_hash_current_bytes_but_decode_only_once; `tests/test_asset_cache.py:57` test_stat_preserving_malicious_swap_is_not_a_cache_hit; `tests/test_asset_cache.py:70` test_cached_fifo_replacement_does_not_block_readiness; `tests/test_asset_cache.py:89` test_failed_scan_does_not_delay_recovery; `tests/test_asset_cache.py:103` test_cached_content_is_rechecked_for_extension_and_symlinks; `tests/test_asset_cache.py:117` test_cached_validation_does_not_survive_stricter_pixel_limits; `tests/test_asset_cache.py:124` test_decode_cache_is_bounded_and_does_not_keep_image_bytes; `tests/test_asset_cache.py:134` test_deletion_and_directory_change_do_not_reuse_cached_inventory; `tests/test_asset_cache.py:146` test_a_healthy_probe_enumerates_nothing; `tests/test_asset_cache.py:163` test_repeated_misses_scan_at_most_once_per_cooldown; `tests/test_asset_cache.py:179` test_a_rename_keeps_identity_without_waiting_for_a_refresh; `tests/test_asset_cache.py:193` test_deletion_then_restoration_recovers_after_the_cooldown; `tests/test_asset_cache.py:211` test_an_explicit_refresh_renews_the_discovery_opportunity; `tests/test_asset_cache.py:226` test_uncached_bytes_are_found_inside_the_bound; `tests/test_asset_cache.py:242` test_replaced_bytes_never_satisfy_the_old_identity; `tests/test_asset_cache.py:274` test_a_stat_preserving_swap_is_not_available; `tests/test_asset_cache.py:289` test_a_matching_extension_is_required_for_a_healthy_candidate; `tests/test_asset_cache.py:302` test_directory_scoping_does_not_reuse_another_directory; `tests/test_asset_cache.py:332` test_malformed_ids_do_not_scan


### test_auth.py

`tests/test_auth.py:37` test_all_http_routes_require_authentication; `tests/test_auth.py:44` test_unauthorized_writes_cannot_change_state; `tests/test_auth.py:53` test_wrong_bearer_is_refused; `tests/test_auth.py:59` test_bearer_scheme_is_case_insensitive; `tests/test_auth.py:63` test_duplicate_authorization_is_refused; `tests/test_auth.py:69` test_bearer_can_read_static_files_and_write; `tests/test_auth.py:78` test_protected_image_bytes_cannot_enter_shared_caches; `tests/test_auth.py:96` test_protected_video_get_head_and_ranges_cannot_enter_shared_caches; `tests/test_auth.py:109` test_html_navigation_redirects_to_login_without_secret; `tests/test_auth.py:122` test_browser_login_sets_cookie_and_allows_normal_browser_routes; `tests/test_auth.py:138` test_https_cookie_is_secure; `tests/test_auth.py:147` test_cookie_writes_require_exact_same_origin; `tests/test_auth.py:156` test_sockets_require_auth_before_upgrade; `tests/test_auth.py:165` test_socket_denial_without_http_extension; `tests/test_auth.py:186` test_cookie_socket_requires_same_origin; `tests/test_auth.py:195` test_bearer_socket_and_existing_operator_guard; `tests/test_auth.py:210` test_browser_cookie_does_not_bypass_operator_guard; `tests/test_auth.py:217` test_login_requires_same_origin; `tests/test_auth.py:224` test_duplicate_origins_are_refused; `tests/test_auth.py:231` test_failed_login_never_reflects_token; `tests/test_auth.py:239` test_login_redirect_stays_local; `tests/test_auth.py:243` test_login_rejects_invalid_and_oversized_forms; `tests/test_auth.py:250` test_tampered_expired_and_rotated_sessions_are_refused; `tests/test_auth.py:264` test_logout_clears_browser_session; `tests/test_auth.py:272` test_short_configured_secret_fails_closed; `tests/test_auth.py:278` test_empty_auth_setting_preserves_default_behavior

- `tests/test_auth.py:35` `"/client/", "/client/client.js", "/controller/", "/nonexistent",`
- `tests/test_auth.py:70` `assert secured.get("/controller/", headers=BEARER).status_code == 200`
- `tests/test_auth.py:71` `assert secured.get("/client/client.js", headers=BEARER).status_code == 200`
- `tests/test_auth.py:110` `response = secured.get("/client/?token=do-not-copy", headers={"Accept": "text/html"}, follow_redirects=False)`
- `tests/test_auth.py:123` `response = login(secured, next="/client/")`
- `tests/test_auth.py:125` `assert response.headers["location"] == "/client/"`
- `tests/test_auth.py:130` `assert secured.get("/client/").status_code == 200`
- `tests/test_auth.py:240` `assert login(secured, next=destination).headers["location"] == "/controller/"`
- `tests/test_auth.py:281` `assert client.get("/client/").status_code == 200`

### test_deployment_hosts.py

`tests/test_deployment_hosts.py:18` test_configured_origins_and_loopback_hosts_are_admitted; `tests/test_deployment_hosts.py:25` test_foreign_host_cannot_read_a_configured_loopback_backend; `tests/test_deployment_hosts.py:38` test_malformed_or_ambiguous_host_is_refused; `tests/test_deployment_hosts.py:46` test_foreign_host_is_refused_before_device_socket_accept; `tests/test_deployment_hosts.py:54` test_unconfigured_development_keeps_existing_host_behavior

- `tests/test_deployment_hosts.py:24` `"/wall", "/client/"])`

### test_health.py

`tests/test_health.py:70` test_healthz_reports_ready_state_without_paths_or_secrets; `tests/test_health.py:86` test_healthz_is_503_when_storage_or_schema_is_not_ready; `tests/test_health.py:94` test_healthz_answers_503_without_leaking_the_state_error; `tests/test_health.py:105` test_all_three_routes_are_operator_admitted; `tests/test_health.py:114` test_proxy_credential_admits_the_operator_routes; `tests/test_health.py:124` test_readiness_has_the_exact_tablet_url_and_join_qr_route; `tests/test_health.py:140` test_readiness_stays_answerable_when_live_state_fails; `tests/test_health.py:154` test_join_qr_is_a_png_of_exactly_the_join_url; `tests/test_health.py:171` test_join_qr_is_503_with_an_actionable_error_when_unconfigured; `tests/test_health.py:178` test_join_qr_does_not_use_the_operator_origin_or_a_query; `tests/test_health.py:186` test_healthz_and_readiness_are_cheap_enough_to_avoid_asset_resolution

- `tests/test_health.py:129` `assert body["tablet_url"] == f"{TABLET}/client/"`
- `tests/test_health.py:151` `assert body["tablet_url"] == f"{TABLET}/client/"`
- `tests/test_health.py:167` `assert decoded.text == f"{TABLET}/client/"`
- `tests/test_health.py:183` `assert decoded.text == "http://10.42.0.9:9090/client/"`

### test_hotspot.py

`tests/test_hotspot.py:17` test_failed_log_writer_is_reported_before_a_live_child_can_be_left_blocked; `tests/test_hotspot.py:42` test_startup_reports_a_log_failure_before_trying_http; `tests/test_hotspot.py:62` test_discovery_uses_access_point_instead_of_uplink_or_vpn; `tests/test_hotspot.py:80` test_missing_hotspot_is_actionable; `tests/test_hotspot.py:86` test_saved_settings_rediscover_address_on_next_launch; `tests/test_hotspot.py:102` test_invalid_saved_ports_are_refused; `tests/test_hotspot.py:111` test_firewall_preserves_existing_rule_ownership; `tests/test_hotspot.py:131` test_interrupted_firewall_change_is_recovered_before_reuse; `tests/test_hotspot.py:143` test_occupied_port_does_not_touch_data_or_existing_server; `tests/test_hotspot.py:154` test_different_configs_cannot_share_firewall_port; `tests/test_hotspot.py:168` test_occupied_port_does_not_remove_a_firewall_rule; `tests/test_hotspot.py:179` test_recently_closed_port_can_restart; `tests/test_hotspot.py:209` test_real_launcher_checks_persists_restarts_and_cleans_up; `tests/test_hotspot.py:265` test_hotspot_name_reads_the_active_access_point_ssid; `tests/test_hotspot.py:277` test_hotspot_name_is_unknown_instead_of_failing_startup; `tests/test_hotspot.py:285` test_preflight_prints_the_actual_settings; `tests/test_hotspot.py:297` test_preflight_says_unknown_when_the_ssid_was_not_discovered; `tests/test_hotspot.py:303` test_preflight_names_local_only_upload_opt_in; `tests/test_hotspot.py:311` test_inherited_upload_modes_are_refused_even_with_flag; `tests/test_hotspot.py:323` test_authentication_is_still_refused_before_discovery; `tests/test_hotspot.py:335` test_main_passes_only_the_launch_flag_and_never_saved_authorization; `tests/test_hotspot.py:352` test_backend_environment_sets_only_the_selected_upload_profile; `tests/test_hotspot.py:362` test_rotating_log_keeps_a_hard_retention_ceiling; `tests/test_hotspot.py:381` test_rotating_log_bounds_a_single_unterminated_line; `tests/test_hotspot.py:393` test_rotating_log_archives_an_oversized_existing_file_at_startup; `tests/test_hotspot.py:406` test_log_pump_follows_a_child_to_eof_and_joins_its_reader; `tests/test_hotspot.py:423` test_spawn_logged_captures_the_real_child; `tests/test_hotspot.py:434` test_readiness_summary_reads_the_mounted_projection; `tests/test_hotspot.py:443` test_readiness_summary_is_unknown_before_the_route_is_mounted

- `tests/test_hotspot.py:244` `assert redirect.headers["location"] == "/client/"`
- `tests/test_hotspot.py:246` `assert httpx.get(tablet + "/client/?calibrate=1").status_code == 200`
- `tests/test_hotspot.py:247` `assert httpx.get(tablet + "/client/ruler.js").status_code == 200`
- `tests/test_hotspot.py:248` `assert httpx.get(tablet + "/controller/").status_code == 403`
- `tests/test_hotspot.py:289` `assert "http://10.42.0.1:18080/client/" in output`
- `tests/test_hotspot.py:290` `assert "http://127.0.0.1:18000/controller/physical.html" in output`

### test_ingress.py

`tests/test_ingress.py:69` test_two_origin_ingress_admits_only_the_authenticated_operator; `tests/test_ingress.py:326` test_tablet_ingress_allows_only_the_exact_app_auth_entry_points; `tests/test_ingress.py:394` test_uploads_disabled_diagnostics_needs_operator_proof; `tests/test_ingress.py:480` test_generated_hotspot_ingress_keeps_loopback_uploads_operator_only

- `tests/test_ingress.py:336` `with start_processes(config, env, app_port, f"{tablet}/client/") as (app, caddy):`
- `tests/test_ingress.py:347` `assert 'name="next" value="/client/"' in bare.text`
- `tests/test_ingress.py:370` `client_surface = browser.get("/client/")`
- `tests/test_ingress.py:389` `for path in ("/diagnostics", "/media", "/uploads", "/wall", "/controller/"):`
- `tests/test_ingress.py:517` `with start_processes(config, env, app_port, f"{tablet}/client/") as (app, caddy), \`
- `tests/test_ingress.py:553` `"/controller/", "/controller/physical.html", "/controller/physical.js",`
- `tests/test_ingress.py:597` `for path in ("/client/", "/client/client.js", "/client/client.css", "/client/view.js", "/client/favicon.svg"):`
- `tests/test_ingress.py:599` `icon = recorded(public, "HEAD", "/client/favicon.svg")`
- `tests/test_ingress.py:601` `for method, path in (("POST", "/client/favicon.svg"), ("HEAD", "/client/favicon.svg/extra"),`
- `tests/test_ingress.py:602` `("HEAD", "/client/client.js")):`
- `tests/test_ingress.py:605` `assert redirect.status_code == 308 and redirect.headers["location"] == "/client/"`

### test_network_trials.py

`tests/test_network_trials.py:11` test_is_instant_accepts_iso_offsets_naive_utc_and_epochs; `tests/test_network_trials.py:20` test_a_restore_marker_carries_the_exact_time_and_optional_labels; `tests/test_network_trials.py:29` test_a_trial_within_the_target_passes_only_with_timing_and_outage_evidence; `tests/test_network_trials.py:56` test_summary_keeps_failures_and_reports_nearest_rank_distribution; `tests/test_network_trials.py:79` test_live_trial_uses_the_slower_of_origin_and_tablet_and_records_skew; `tests/test_network_trials.py:99` test_a_live_trial_without_an_observed_outage_fails; `tests/test_network_trials.py:108` test_a_complete_report_has_twenty_scenarios_and_never_a_hardware_claim; `tests/test_network_trials.py:137` test_a_missing_trial_becomes_incomplete_and_a_failed_trial_blocks; `tests/test_network_trials.py:168` test_marker_source_ignores_history_and_reads_the_next_appended_line; `tests/test_network_trials.py:180` test_origin_validation_rejects_paths_and_normalizes_a_trailing_slash; `tests/test_network_trials.py:188` test_dry_mode_rejects_a_live_base_url; `tests/test_network_trials.py:193` test_live_mode_needs_a_base_url_tablet_and_metadata; `tests/test_network_trials.py:203` test_restored_at_needs_exactly_twenty_values

- `tests/test_network_trials.py:183` `network_trials._origin("https://192.168.1.2:8443/client/")`

### test_offline.py

`tests/test_offline.py:72` test_the_namespace_really_blocks_the_outside; `tests/test_offline.py:78` test_startup_restores_wall_playlist_and_media_offline; `tests/test_offline.py:94` test_served_pages_reference_nothing_outside_the_origin; `tests/test_offline.py:110` test_a_real_client_page_load_touches_only_its_own_origin

- `tests/test_offline.py:6` `loads every served page and runs the real ``client.js`` against it. Skipped`
- `tests/test_offline.py:99` `assert pages["fetched"]["/client/"] == "ok"`
- `tests/test_offline.py:100` `assert pages["fetched"]["/controller/"] == "ok"`
- `tests/test_offline.py:102` `assert any(path.endswith("client.js") for path in pages["fetched"])`

### test_operability.py

`tests/test_operability.py:68` test_configured_environment_is_projected_without_guessing; `tests/test_operability.py:81` test_missing_tablet_origin_is_an_actionable_error_not_a_guess; `tests/test_operability.py:99` test_invalid_tablet_origin_is_reported_and_not_used; `tests/test_operability.py:106` test_unknown_wifi_and_backup_stay_unknown; `tests/test_operability.py:117` test_non_printable_wifi_name_is_not_reported; `tests/test_operability.py:122` test_wifi_name_is_not_queried_from_networkmanager; `tests/test_operability.py:132` test_plain_http_warns_that_wake_lock_is_unavailable; `tests/test_operability.py:140` test_https_context_calls_wake_lock_best_effort; `tests/test_operability.py:147` test_shared_secret_is_not_described_as_authenticated_device_identity; `tests/test_operability.py:164` test_content_readiness_describes_what_is_actually_selected; `tests/test_operability.py:178` test_newest_backup_manifest_is_read_without_verifying_or_writing; `tests/test_operability.py:194` test_broken_backup_manifest_does_not_become_a_recency_claim; `tests/test_operability.py:201` test_restore_rehearsal_is_reported_only_when_recorded; `tests/test_operability.py:211` test_restore_rehearsal_without_a_timestamp_is_unknown; `tests/test_operability.py:218` test_health_reports_schema_and_counts_without_private_paths; `tests/test_operability.py:235` test_health_is_not_ready_without_storage_or_matching_schema; `tests/test_operability.py:241` test_live_snapshot_uses_the_process_state_and_store; `tests/test_operability.py:250` test_live_snapshot_reports_unreadable_storage; `tests/test_operability.py:257` test_missing_database_does_not_get_created_by_readiness; `tests/test_operability.py:265` test_readiness_never_copies_an_asset_path_from_a_failure; `tests/test_operability.py:276` test_operator_data_paths_are_reported_only_for_the_operator_projection; `tests/test_operability.py:285` test_managed_asset_requires_its_object_file; `tests/test_operability.py:296` test_curated_asset_availability_recovers_after_restore_within_the_bound; `tests/test_operability.py:323` test_curated_availability_rejects_a_malformed_id_without_scanning

- `tests/test_operability.py:92` `"http://10.0.0.1:8080/client/",`

### test_operator_backend.py

`tests/test_operator_backend.py:20` test_mounted_readiness_health_and_qr_use_live_wall; `tests/test_operator_backend.py:43` test_new_registration_notifies_durable_config_change_after_commit; `tests/test_operator_backend.py:59` test_new_legacy_controller_cannot_observe_a_fake_physical_wall; `tests/test_operator_backend.py:70` test_mounted_ruler_review_is_admitted_origin_guarded_and_nonmutating; `tests/test_operator_backend.py:93` test_number_release_broadcast_cannot_overwrite_a_new_socket_owner; `tests/test_operator_backend.py:235` test_runtime_does_not_change_durable_etag_or_issue_instructions; `tests/test_operator_backend.py:262` test_stale_or_inexact_tokens_cannot_confirm; `tests/test_operator_backend.py:275` test_retry_sequence_visibility_and_raw_report_bounds; `tests/test_operator_backend.py:300` test_takeover_and_zoom_fences; `tests/test_operator_backend.py:321` test_contain_requires_capability_and_cached_logical_v3_still_works; `tests/test_operator_backend.py:341` test_physical_colour_and_pinned_calibration_health; `tests/test_operator_backend.py:362` test_identify_expires_over_new_scene_with_fresh_token; `tests/test_operator_backend.py:394` test_grid_one_revision_order_and_viewport_guards; `tests/test_operator_backend.py:428` test_labels_snapshots_durable_etags_and_restart; `tests/test_operator_backend.py:453` test_model_match_is_suggestion_until_confirmed_and_preserves_decisions; `tests/test_operator_backend.py:469` test_remove_and_offline_only_forget_preserve_saved_reservations; `tests/test_operator_backend.py:512` test_rebind_keeps_model_source_after_capturing_a_new_viewport; `tests/test_operator_backend.py:555` test_model_tagged_save_cannot_create_an_untraceable_model_scale; `tests/test_operator_backend.py:570` test_model_health_dpr_fence_also_blocks_the_render_plan; `tests/test_operator_backend.py:594` test_rebind_all_histories_saved_recall_and_final_write_rollback; `tests/test_operator_backend.py:641` test_different_hardware_rebind_refuses_physical_scale; `tests/test_operator_backend.py:652` test_generated_patterns_are_ordinary_curated_assets; `tests/test_operator_backend.py:674` test_invalid_snapshots_remain_visible_and_change_etag; `tests/test_operator_backend.py:688` test_viewport_rejects_invalid_visual_scale; `tests/test_operator_backend.py:699` test_physical_grid_uses_every_selected_revision_and_commits_once; `tests/test_operator_backend.py:722` test_inherited_model_estimate_is_not_overwritten_or_verified; `tests/test_operator_backend.py:736` test_model_history_changes_etag_without_wall_revision; `tests/test_operator_backend.py:748` test_missing_asset_availability_does_not_invalidate_durable_etag; `tests/test_operator_backend.py:758` test_generated_pattern_rechecks_etag_after_generation; `tests/test_operator_backend.py:771` test_scene_snapshot_recall_validates_availability_and_fit; `tests/test_operator_backend.py:785` test_rebind_saved_digest_and_connection_guards; `tests/test_operator_backend.py:805` test_identify_status_is_connection_and_command_owned; `tests/test_operator_backend.py:827` test_v3_status_notifications_preserve_device_fields; `tests/test_operator_backend.py:842` test_failed_experimental_presentation_still_fences_static_evidence; `tests/test_operator_backend.py:857` test_heartbeat_age_expires_render_evidence_without_changing_config; `tests/test_operator_backend.py:871` test_old_socket_cannot_report_for_or_clear_its_replacement; `tests/test_operator_backend.py:893` test_logical_background_is_image_only_and_new_mutations_are_cas_guarded; `tests/test_operator_backend.py:911` test_grid_auto_orientation_uses_selected_historical_model_after_google_and_manual_assignment

- `tests/test_operator_backend.py:30` `assert readiness.json()["tablet_url"] == "http://10.42.0.1:8080/client/"`
- `tests/test_operator_backend.py:33` `for response in (health, readiness, qr, client.get("/controller/physical.html")):`

### test_redesign_driver.py

`tests/test_redesign_driver.py:17` test_existing_artifacts_refused_before_any_launch; `tests/test_redesign_driver.py:41` test_no_arbitrary_server_option; `tests/test_redesign_driver.py:62` test_launch_profile_is_private_and_does_not_inherit_admission; `tests/test_redesign_driver.py:89` test_identity_changes_for_dirty_bytes_without_new_commit; `tests/test_redesign_driver.py:123` test_bounded_wait_does_not_turn_timeout_into_success; `tests/test_redesign_driver.py:128` test_injected_failure_scope_does_not_hide_unrelated_http; `tests/test_redesign_driver.py:146` test_real_failure_captured_before_actual_cleanup; `tests/test_redesign_driver.py:189` test_real_race_records_both_authorities_and_retained_intent

- `tests/test_redesign_driver.py:138` `"http://127.0.0.1/controller/physical.js", status=404`

### test_redesign_edge_cases.py

`tests/test_redesign_edge_cases.py:18` test_partial_or_failed_runs_cannot_close_mandatory_groups; `tests/test_redesign_edge_cases.py:35` test_external_proof_rejects_changed_source_or_allowlist; `tests/test_redesign_edge_cases.py:56` test_external_proof_parser_accepts_expanded_denial_matrix; `tests/test_redesign_edge_cases.py:93` test_native_tab_helper_uses_real_tab_and_bounds_an_unreachable_target; `tests/test_redesign_edge_cases.py:115` test_two_held_real_responses_release_independently; `tests/test_redesign_edge_cases.py:165` test_real_transport_race_retains_old_payload_and_actual_new_authority; `tests/test_redesign_edge_cases.py:198` test_held_response_release_keeps_followup_requests_routable

- `tests/test_redesign_edge_cases.py:72` `("POST", "/client/favicon.svg"),`
- `tests/test_redesign_edge_cases.py:73` `("HEAD", "/client/favicon.svg/extra"),`
- `tests/test_redesign_edge_cases.py:74` `("HEAD", "/client/client.js"),`
- `tests/test_redesign_edge_cases.py:81` `"path": "/client/favicon.svg",`

### test_restoration_driver.py

`tests/test_restoration_driver.py:37` test_registry_and_bodies_cover_all_ten_durable_scenarios; `tests/test_restoration_driver.py:105` test_missing_feature_hook_fails_explicitly_with_the_owner_named; `tests/test_restoration_driver.py:122` test_present_feature_hook_adds_no_failure_and_missing_js_hook_is_named; `tests/test_restoration_driver.py:155` test_fit_feedback_missing_hook_does_not_fake_a_pass_or_touch_the_server; `tests/test_restoration_driver.py:164` test_current_guard_delete_sends_the_exact_config_if_match; `tests/test_restoration_driver.py:180` test_current_guard_delete_refuses_an_unguarded_request; `tests/test_restoration_driver.py:192` test_pattern_controls_navigate_to_images_after_the_authorized_move; `tests/test_restoration_driver.py:206` test_artifacts_must_be_new_and_outside_both_repositories; `tests/test_restoration_driver.py:218` test_new_artifacts_can_defer_creation_to_the_scenario; `tests/test_restoration_driver.py:229` test_wait_until_polls_evaluate_and_never_uses_wait_for_function; `tests/test_restoration_driver.py:253` test_launch_browser_uses_playwright_default_headless_browser; `tests/test_restoration_driver.py:276` test_environment_is_private_complete_and_does_not_mutate_ambient; `tests/test_restoration_driver.py:330` test_fixture_groups_are_unique_deterministic_and_cover_required_shapes; `tests/test_restoration_driver.py:367` test_source_identity_separates_application_from_driver; `tests/test_restoration_driver.py:393` test_source_root_must_be_an_application_tree; `tests/test_restoration_driver.py:400` test_server_launch_uses_the_selected_source_root_as_cwd; `tests/test_restoration_driver.py:436` test_an_incomplete_registry_entry_still_writes_explicit_failure_without_a_server; `tests/test_restoration_driver.py:495` test_single_implemented_scenario_creates_its_own_artifacts_target; `tests/test_restoration_driver.py:530` test_all_scenario_uses_new_child_artifact_directories; `tests/test_restoration_driver.py:574` test_task_values_include_the_settings_panel; `tests/test_restoration_driver.py:579` test_unknown_or_missing_scenario_is_a_usage_error; `tests/test_restoration_driver.py:598` test_scenario_pass_requires_assertions_and_complete_cleanup; `tests/test_restoration_driver.py:617` test_help_lists_the_frozen_scenario_interface; `tests/test_restoration_driver.py:633` test_socket_evidence_is_bounded_and_excludes_config_snapshots

- `tests/test_restoration_driver.py:21` `(root / "frontend/app.js").write_text("window.app = 1;\n")`
- `tests/test_restoration_driver.py:377` `(source / "frontend/app.js").write_text("window.app = 2;\n")`

### test_runtime_ownership.py

`tests/test_runtime_ownership.py:15` test_second_app_lifespan_is_refused_until_first_stops; `tests/test_runtime_ownership.py:25` test_runtime_lock_excludes_another_process_and_releases_after_crash; `tests/test_runtime_ownership.py:48` test_startup_failure_releases_runtime_ownership; `tests/test_runtime_ownership.py:61` test_static_mounts_work_when_imported_outside_repository

- `tests/test_runtime_ownership.py:68` `" assert client.get('/client/').status_code == 200\n"`
- `tests/test_runtime_ownership.py:69` `" assert client.get('/controller/').status_code == 200\n"`

### test_security.py

`tests/test_security.py:87` test_writes_need_no_origin; `tests/test_security.py:96` test_writes_succeed_and_move_the_revision; `tests/test_security.py:104` test_controller_socket_needs_no_origin; `tests/test_security.py:110` test_an_empty_variable_is_the_same_as_unset; `tests/test_security.py:127` test_json_body_put; `tests/test_security.py:136` test_bodyless_auto_post; `tests/test_security.py:148` test_bodyless_recall_post; `tests/test_security.py:157` test_delete; `tests/test_security.py:178` test_guard_only_adds_403s; `tests/test_security.py:205` test_missing_origin_is_403; `tests/test_security.py:231` test_non_matching_origin_is_403; `tests/test_security.py:247` test_duplicate_or_combined_origin_headers_are_403; `tests/test_security.py:255` test_denied_delete_leaves_the_device_registered; `tests/test_security.py:262` test_registration_exception_is_exact_path_only; `tests/test_security.py:269` test_bad_tablet_link_config_does_not_disable_operator_fence; `tests/test_security.py:279` test_denial_precedes_body_validation; `tests/test_security.py:302` test_reads_are_not_guarded; `tests/test_security.py:311` test_registration_is_always_reachable; `tests/test_security.py:318` test_the_exemption_is_the_exact_post_path_only; `tests/test_security.py:334` test_missing_origin_is_rejected_with_403; `tests/test_security.py:345` test_non_matching_origin_is_rejected_with_403; `tests/test_security.py:354` test_rejected_handshake_registers_nothing; `tests/test_security.py:364` test_matching_origin_is_accepted_and_gets_the_snapshot; `tests/test_security.py:373` test_device_socket_is_not_guarded; `tests/test_security.py:423` test_malformed_operator_origin_denies_every_write; `tests/test_security.py:451` test_malformed_operator_origin_denies_the_controller_socket; `tests/test_security.py:478` test_a_valid_value_is_compared_exactly; `tests/test_security.py:491` test_unset_returns_null; `tests/test_security.py:497` test_empty_returns_null; `tests/test_security.py:510` test_configured_origin_is_returned_verbatim; `tests/test_security.py:531` test_malformed_value_is_refused_rather_than_echoed; `tests/test_security.py:552` test_the_read_is_not_guarded_by_the_operator_origin

- `tests/test_security.py:272` `monkeypatch.setenv(main.TABLET_ORIGIN_ENV, "https://tablets.wall.test/client/")`
- `tests/test_security.py:398` `"https://operator.wall.test/client/",`
- `tests/test_security.py:522` `"https://tablets.wall.test/client/",`

### test_security_headers.py

`tests/test_security_headers.py:79` test_headers_are_present_on_real_client_and_controller_pages; `tests/test_security_headers.py:91` test_policy_allows_local_scripts_styles_blobs_and_same_origin_sockets; `tests/test_security_headers.py:122` test_only_one_valid_host_adds_the_exact_socket_source; `tests/test_security_headers.py:129` test_policy_names_no_external_origin; `tests/test_security_headers.py:134` test_a_route_that_already_chose_a_policy_keeps_it; `tests/test_security_headers.py:141` test_login_page_keeps_its_hash_pinned_policy_and_gains_baseline_headers; `tests/test_security_headers.py:165` test_websocket_scope_passes_through_untouched; `tests/test_security_headers.py:171` test_direct_middleware_call_does_not_touch_a_websocket_scope

- `tests/test_security_headers.py:81` `for path in ("/client/", "/controller/", "/client/client.js", "/json"):`

### test_trust_check.py

`tests/test_trust_check.py:219` test_origins_are_parsed_into_one_unambiguous_https_form; `tests/test_trust_check.py:244` test_ambiguous_or_insecure_origins_are_rejected; `tests/test_trust_check.py:249` test_fingerprint_normalization_strips_common_separators; `tests/test_trust_check.py:262` test_the_parser_offers_no_insecure_or_bypass_switch; `tests/test_trust_check.py:274` test_trust_store_identity_names_the_store_actually_loaded; `tests/test_trust_check.py:293` test_certificate_parsing_records_chain_subjects_issuers_sans_and_validity; `tests/test_trust_check.py:319` test_a_verified_disposable_ingress_run_is_complete_but_never_tablet_trust; `tests/test_trust_check.py:379` test_an_untrusted_server_fails_closed_and_never_borrows_the_route_matrix; `tests/test_trust_check.py:407` test_a_wrong_pinned_fingerprint_fails_while_tls_remains_verified; `tests/test_trust_check.py:427` test_a_leaky_tablet_ingress_fails_the_denied_routes; `tests/test_trust_check.py:441` test_an_unauthenticated_operator_listener_fails_the_auth_matrix; `tests/test_trust_check.py:453` test_hostname_mismatch_is_reported_as_its_own_failure; `tests/test_trust_check.py:470` test_a_supplied_second_vantage_runs_its_own_matrix; `tests/test_trust_check.py:497` test_an_ipv4_argument_cannot_masquerade_as_the_ipv6_vantage; `tests/test_trust_check.py:514` test_a_trust_store_that_cannot_be_loaded_fails_with_an_explicit_error; `tests/test_trust_check.py:529` test_the_same_origin_for_both_roles_is_rejected_before_probing

- `tests/test_trust_check.py:231` `"https://192.168.137.1:8443/client/",`
- `tests/test_trust_check.py:356` `assert any("tablet GET /client/ -> 200" in name for name in names)`
- `tests/test_trust_check.py:399` `assert not any("tablet GET /client/ -> 200" == check["name"]`

### test_wall.py

`tests/test_wall.py:64` test_absent_protocol_means_version_1; `tests/test_wall.py:78` test_version_1_welcome_has_no_extra_keys; `tests/test_wall.py:91` test_protocol_2_welcome_carries_version_and_server_caps; `tests/test_wall.py:106` test_unsupported_device_protocol_closes_with_4426; `tests/test_wall.py:119` test_unsupported_controller_protocol_closes_with_4426; `tests/test_wall.py:126` test_device_record_starts_with_no_protocol; `tests/test_wall.py:134` test_v1_socket_records_protocol_1_and_empty_caps; `tests/test_wall.py:144` test_v2_socket_records_protocol_and_caps; `tests/test_wall.py:157` test_empty_caps_stay_empty; `tests/test_wall.py:167` test_reregistration_preserves_negotiated_protocol; `tests/test_wall.py:186` test_v1_device_never_receives_wall; `tests/test_wall.py:205` test_v2_device_receives_wall_after_welcome; `tests/test_wall.py:222` test_wall_frame_carries_the_placement; `tests/test_wall.py:244` test_wall_replays_on_reconnect; `tests/test_wall.py:277` test_wall_change_is_pushed_to_a_connected_v2_device; `tests/test_wall.py:303` test_content_downgrades_without_the_calibration_cap; `tests/test_wall.py:324` test_calibration_cap_keeps_calibration_content; `tests/test_wall.py:338` test_v1_snapshot_has_no_wall_key; `tests/test_wall.py:349` test_v1_controller_never_gets_wall_updated; `tests/test_wall.py:362` test_v2_snapshot_carries_the_wall; `tests/test_wall.py:379` test_snapshot_shape_differs_between_v1_and_v2; `tests/test_wall.py:394` test_wall_updated_is_broadcast_on_every_change; `tests/test_wall.py:432` test_default_wall_state; `tests/test_wall.py:452` test_put_wall_accepts_any_subset; `tests/test_wall.py:497` test_put_wall_rejects_bad_values_with_422; `tests/test_wall.py:509` test_put_scene_replaces_the_content_and_bumps_the_revision; `tests/test_wall.py:532` test_put_scene_leaves_the_layout_alone; `tests/test_wall.py:579` test_put_scene_rejects_bad_bodies_with_422; `tests/test_wall.py:589` test_placement_defaults_bezel_to_zero; `tests/test_wall.py:612` test_placement_records_a_full_bezel; `tests/test_wall.py:636` test_partial_bezel_defaults_the_other_edges_to_zero; `tests/test_wall.py:665` test_bad_placement_is_422; `tests/test_wall.py:673` test_placement_for_unknown_device_is_404; `tests/test_wall.py:681` test_placement_for_malformed_id_is_404; `tests/test_wall.py:689` test_delete_without_a_placement_is_200; `tests/test_wall.py:697` test_delete_clears_the_placement; `tests/test_wall.py:710` test_delete_of_an_absent_device_with_a_placement_is_200; `tests/test_wall.py:738` test_a_reservation_survives_a_restart_and_can_be_released; `tests/test_wall.py:771` test_delete_placement_of_unknown_or_malformed_id_is_404; `tests/test_wall.py:778` test_a_zero_width_cell_is_rejected_before_reservation_checks; `tests/test_wall.py:798` test_a_zero_height_cell_is_rejected; `tests/test_wall.py:813` test_default_columns_grid_for_three_online_devices; `tests/test_wall.py:858` test_explicit_columns_tile_the_wall_exactly; `tests/test_wall.py:885` test_auto_replaces_online_and_leaves_offline_untouched; `tests/test_wall.py:924` test_auto_rejects_a_grid_that_would_cover_a_vacant_reservation; `tests/test_wall.py:952` test_auto_rejects_a_grid_that_would_cover_an_offline_reservation; `tests/test_wall.py:975` test_auto_accepts_a_grid_that_only_touches_a_reservation; `tests/test_wall.py:1016` test_auto_judges_overlap_by_footprint_not_by_visible_area; `tests/test_wall.py:1042` test_an_existing_online_placement_is_not_a_reservation; `tests/test_wall.py:1067` test_a_rejected_auto_changes_nothing_anywhere; `tests/test_wall.py:1103` test_auto_with_an_empty_roster; `tests/test_wall.py:1110` test_auto_rejects_bad_columns_with_422; `tests/test_wall.py:1115` test_every_mutation_strictly_bumps_the_revision; `tests/test_wall.py:1149` test_delete_drops_its_placement; `tests/test_wall.py:1165` test_delete_without_a_placement_leaves_the_revision_alone

- `tests/test_wall.py:65` `"""A cached client.js that predates the version param keeps working."""`

Key distinctions:

- test_asset_cache.py checks image inventory/hash/decode freshness, malicious byte swaps, symlinks, directory changes, negative lookup cooldown and bounded cache. This is **not** the HTML `?v=` script cache-token test (tests/test_asset_cache.py:36, :57, :163).
- test_api.py checks served static routes, no-cache and validators; test_security_headers.py and test_auth.py check CSP, auth and redirects. Vite hashed chunks must remain same-origin, load behind existing admission, and support the controller entry path. Add manifest/chunk walking rather than preserving obsolete bundle filenames forever.
- test_ingress.py uses real subprocess app/Caddy plus HTTP, not a browser. It proves operator/tablet listener allowlists, auth/upload/diagnostic separation and static client reachability (tests/test_ingress.py:69, :326, :480, :553, :597). Do not move controller chunks into a path publicly admitted as tablet content.
- test_operator_backend.py provides HTTP + owned-device-socket contracts for registration notifications, ETags, evidence tokens, ruler admission, grid atomicity, model revisions, identification, rebind and restoration. Its static page read only checks headers (tests/test_operator_backend.py:20, :394, :699). This is category (a) at the frontend boundary.
- test_renewal_heading_roles.py tests acceptance-driver heading arithmetic, not semantic headings in a real rendered page (tests/test_renewal_heading_roles.py:19). test_redesign_driver*, test_restoration_driver and test_redesign_edge_cases similarly test evidence and driver behavior.
- test_offline.py has stronger offline execution via a network namespace and Node driver, but is environment-dependent (tests/test_offline.py:6, :94, :110). Its static asset crawl must follow a bundler's module graph, CSS imports and fonts.
- Supporting behavioral backend suites include test_websocket, test_device_lifecycle, test_render_status, test_v3, test_grid, test_layout_transitions, test_wall_sizing, test_image_fit, test_geometry, test_calibration*, test_displays, test_tablet_models, test_snapshots, test_operator_images and test_playback*. They protect wire/domain behavior, not the operator's ability to find and invoke it.

## Simulator and browser inventory

Measured wall-clock runtimes are **unknown** because browser drivers were read, not executed. Durations below are source defaults or explicit minimum waits; they are not benchmark results. Most browser drivers launch private app storage and Chromium, and may generate media via ffmpeg. They are materially heavier than Node tests. Browser support conclusions cannot be generalized from desktop Chromium to iPadOS 15.

The in-process simulator has 18 virtual tablets and 22 registered scenarios (simulator/scenarios.py:308–1828). They cover isolation, registration and invalid bodies, controller snapshots, handshake rejection, online presence, colors, wall updates, placement validation/release, scene capability downgrade, images/hash freshness, snapshots, tiling, matched/mismatched seams, revisions/generations, reconnect, socket takeover, restart and heartbeat sweeper. It selects devices by UUID in HTTP/socket frames, not DOM. It executes no frontend code, uses a model renderer and accelerated sweeper constants (simulator/run.py:40). `make sim` also runs simulator/test_simulator_selftest.py. Runtime not measured here.

Every browser Python file is inventoried below. Helpers and driver self-tests are explicitly distinguished from executable acceptance drivers. DOM locators are category (b); injected globals, instrumentation and source-based driver unit tests are additionally category (c). HTTP/socket/pixel checks are behavior-level (a).

### _redesign_edge_cases.py

Bounded transport races and native-input acceptance on disposable shipped clients.

- `simulator/browser/_redesign_edge_cases.py:27` `page.locator("#refresh-status").click()`
- `simulator/browser/_redesign_edge_cases.py:28` `expect(page.locator("body")).to_have_attribute("data-connection", "current")`
- `simulator/browser/_redesign_edge_cases.py:36` `page.set_default_timeout(7000)`
- `simulator/browser/_redesign_edge_cases.py:38` `expect(page.locator(":is(.dev-pick,.roster-pick):visible")).to_have_count(len(ids(rig)))`
- `simulator/browser/_redesign_edge_cases.py:45` `page.locator("#tablet-label").fill(name)`
- `simulator/browser/_redesign_edge_cases.py:46` `page.locator("#tablet-label-save").click()`
- `simulator/browser/_redesign_edge_cases.py:47` `expect(page.locator("#tablet-action-message")).to_contain_text("Name saved")`
- `simulator/browser/_redesign_edge_cases.py:98` `p.locator("#grid-1x4").click()`
- `simulator/browser/_redesign_edge_cases.py:99` `p.locator("#grid-preview").click()`
- `simulator/browser/_redesign_edge_cases.py:100` `expect(p.locator("body")).to_have_attribute("data-stage-mode", "arrangement-preview")`

### _redesign_scenarios.py

Actual UI journeys, ported from the source-matched functional handoff.

- `simulator/browser/_redesign_scenarios.py:15` `subject = page.locator("#tablet-label-form").get_attribute("data-device-id")`
- `simulator/browser/_redesign_scenarios.py:17` `rig.open_disclosures(page.locator("#tablet-forget-preview"))`
- `simulator/browser/_redesign_scenarios.py:18` `page.locator("#tablet-forget-preview").click()`
- `simulator/browser/_redesign_scenarios.py:22` `if page.locator("#tablet-forget-impact").is_visible():`
- `simulator/browser/_redesign_scenarios.py:25` `sheet = page.locator("#device-sheet")`
- `simulator/browser/_redesign_scenarios.py:28` `page.locator("#device-sheet-close").click()`
- `simulator/browser/_redesign_scenarios.py:30` `page.locator("#refresh-status").click()`
- `simulator/browser/_redesign_scenarios.py:34` `select_tablet(page.locator(f':is(.dev-pick,.roster-pick):visible[data-device-id="{subject}"]'))`
- `simulator/browser/_redesign_scenarios.py:35` `expect(page.locator("#tablet-forget-impact")).to_be_visible()`
- `simulator/browser/_redesign_scenarios.py:55` `if page.locator("#device-sheet").get_attribute("data-modal") == "true":`

### _workspace_shell.py

Drive the persistent wall through visible controls without bypassing draft guards.

- `simulator/browser/_workspace_shell.py:8` `return page.locator(f'[data-workspace-mode="{mode}"]:visible').first`
- `simulator/browser/_workspace_shell.py:13` `return page.locator(f':is(.roster-pick,.dev-pick){identity}:visible')`
- `simulator/browser/_workspace_shell.py:17` `back = page.locator("#tablet-back")`
- `simulator/browser/_workspace_shell.py:23` `drawer = page.locator("#server-drawer")`
- `simulator/browser/_workspace_shell.py:26` `page.locator("#btn-server").click()`
- `simulator/browser/_workspace_shell.py:31` `page.locator("#server-close").click()`
- `simulator/browser/_workspace_shell.py:34` `expect(page.locator("#device-sheet")).to_be_visible()`
- `simulator/browser/_workspace_shell.py:37` `nav = page.locator("#nav-tablets")`
- `simulator/browser/_workspace_shell.py:40` `if page.locator("body").get_attribute("data-view") != "tablets":`
- `simulator/browser/_workspace_shell.py:47` `if name == "Arrange tablet" and page.locator("body").get_attribute("data-mode") == mode:`

### audit_round.py

Repeatable viewport audit against disposable data, with browser error evidence.

- `simulator/browser/audit_round.py:104` `await page.get_by_label("Access token").fill(`
- `simulator/browser/audit_round.py:107` `await page.get_by_role(`
- `simulator/browser/audit_round.py:187` `for button in await page.locator(`

### clock_app.py

Test-only ASGI entry for the disposable suspend experiment.


### composition_gates.py

Measure the workspace-wall composition gates G1-G6 and G8 against a live operator console.

- `simulator/browser/composition_gates.py:124` `new = page.locator(f"[data-workspace-mode='{name}']:visible")`
- `simulator/browser/composition_gates.py:128` `compact = page.locator("#compact-task-select")`
- `simulator/browser/composition_gates.py:132` `page.locator(OLD_TAB[name]).click()`
- `simulator/browser/composition_gates.py:363` `page.locator("#show-image").click()`
- `simulator/browser/composition_gates.py:456` `page.locator("#image-discard").click()`
- `simulator/browser/composition_gates.py:461` `page.locator("#grid-preview").click()`
- `simulator/browser/composition_gates.py:497` `discard = page.locator("button:visible", has_text="Discard").first`
- `simulator/browser/composition_gates.py:550` `header_height = page.locator("header.topbar").bounding_box()["height"]`
- `simulator/browser/composition_gates.py:551` `chip_tops = page.locator("#exception-strip > li").evaluate_all("rows => rows.map(e => e.getBoundingClientRect().top)")`
- `simulator/browser/composition_gates.py:552` `page.locator("#exception-strip [data-status=more] button").click()`

### controller_run.py

Durable controller acceptance for F3 (pause), F4 (live identity) and the tabbed console shell.

Scenario/check entry points: `scenario_statuses`

- `simulator/browser/controller_run.py:383` `return await controller.locator("#playback-status").inner_text()`
- `simulator/browser/controller_run.py:386` `return await controller.locator("#playback-countdown").inner_text()`
- `simulator/browser/controller_run.py:389` `return await controller.locator("#playback-facts").inner_text()`
- `simulator/browser/controller_run.py:392` `return await controller.locator("#playback-poll-note").inner_text()`
- `simulator/browser/controller_run.py:395` `return await controller.locator(".playlist-name").all_inner_texts()`
- `simulator/browser/controller_run.py:398` `return await controller.locator('.playlist-item[data-current="true"]').count()`
- `simulator/browser/controller_run.py:541` `return await controller.locator("#playback-stale").is_hidden()`
- `simulator/browser/controller_run.py:614` `await controller.locator(f"#tab-{current}").focus()`
- `simulator/browser/controller_run.py:643` `await controller.locator("#panel-system .legacy-card").screenshot(`
- `simulator/browser/controller_run.py:873` `await controller.locator("#btn-playback-pause").inner_text() == "Resume"`

### decode_probe.py

Desktop smoke for the standalone device decode/suspend probe.

Scenario/check entry points: `run_engine`, `run_engines`, `run_smoke`

- `simulator/browser/decode_probe.py:472` `page.set_default_timeout(15000)`

### evidence.py

Pure analysis of hard-cut software evidence. Software onset, not optical.


### experience_acceptance.py

Separate experience evidence supplement; behavioral acceptance remains authoritative.

- `simulator/browser/experience_acceptance.py:66` `selected_task = p.locator("#compact-task-select").input_value()`
- `simulator/browser/experience_acceptance.py:96` `rig.click(p.locator("#device-list .dev-pick").first)`
- `simulator/browser/experience_acceptance.py:98` `expect(rig.tablets[0].locator("#identify")).to_be_visible()`
- `simulator/browser/experience_acceptance.py:105` `expect(p.locator("#refresh-images")).to_be_enabled()`
- `simulator/browser/experience_acceptance.py:110` `expect(p.locator("body")).to_have_attribute("data-stage-mode", "arrangement-preview")`

### field_run.py

Rendered R5 field checks on a disposable loopback server.

- `simulator/browser/field_run.py:174` `await editor.locator("#diag-msg").get_attribute("data-kind") == "ok")`
- `simulator/browser/field_run.py:188` `await editor.locator("#diag-integrity").is_hidden())`
- `simulator/browser/field_run.py:200` `await editor.locator("#diag-msg").get_attribute("data-kind") == "err"`
- `simulator/browser/field_run.py:201` `and "missing fixture object" in await editor.locator("#diag-problems").inner_text())`
- `simulator/browser/field_run.py:212` `await editor.locator("#btn-diag-download").is_disabled()`
- `simulator/browser/field_run.py:213` `and await editor.locator("#diag-integrity").is_hidden())`
- `simulator/browser/field_run.py:222` `await editor.locator("#btn-diag-download").is_visible()`
- `simulator/browser/field_run.py:223` `and await editor.locator("#tab-system").get_attribute("aria-selected") == "true")`
- `simulator/browser/field_run.py:224` `await editor.locator("#tab-system").focus()`
- `simulator/browser/field_run.py:226` `check("mobile Home selects Show", await editor.locator("#panel-show").is_visible())`

### first_run_acceptance.py

Drive setup using its filled actions and record the four honest wall states.

- `simulator/browser/first_run_acceptance.py:25` `buttons = rig.page.locator(".btn-primary:visible")`
- `simulator/browser/first_run_acceptance.py:37` `expect(page.locator(".btn-primary:visible")).to_have_count(0 if state == "S3" else 1)`
- `simulator/browser/first_run_acceptance.py:39` `expect(page.locator(".btn-primary:visible")).to_have_attribute("id", expected)`
- `simulator/browser/first_run_acceptance.py:40` `assert page.locator("body").get_attribute("data-test-live") == "false"`
- `simulator/browser/first_run_acceptance.py:42` `"primary": expected, "tally": page.locator(".stage-tally").inner_text(),`
- `simulator/browser/first_run_acceptance.py:43` `"commit": page.locator("#draft-state").inner_text()})`
- `simulator/browser/first_run_acceptance.py:53` `expect(page.locator("#copy-tablet-url")).to_be_focused()`
- `simulator/browser/first_run_acceptance.py:55` `expect(page.locator("#empty-title")).to_have_text("6 tablets waiting to be arranged")`
- `simulator/browser/first_run_acceptance.py:56` `expect(page.locator("#join-strip")).to_be_hidden()`
- `simulator/browser/first_run_acceptance.py:59` `expect(page.locator("#grid-preview")).to_be_focused()`

### fleet_soak.py

Fleet soak harness for N disposable Chromium clients on one server.

- `simulator/browser/fleet_soak.py:1197` `parser.add_argument("--duration", type=float, default=DEFAULT_DURATION_SECONDS,`
- `simulator/browser/fleet_soak.py:1207` `parser.error("--duration must be at least 5 seconds")`

### group_recovery_run.py

Real-browser bounded group video recovery on a disposable server.

- `simulator/browser/group_recovery_run.py:535` `facts = await controller.locator("#playback-facts").inner_text()`
- `simulator/browser/group_recovery_run.py:637` `blocked_text = await controller.locator("#playback-status").inner_text()`
- `simulator/browser/group_recovery_run.py:638` `retry_visible = await controller.locator("#btn-playback-retry").is_visible()`

### health_run.py

Rendered health failure/retry checks. Pass a new artifact directory as the argument.

- `simulator/browser/health_run.py:62` `assert page.locator("#btn-wall-health").bounding_box()["height"] >= 44`
- `simulator/browser/health_run.py:63` `page.locator("#btn-wall-health").click()`
- `simulator/browser/health_run.py:72` `page.locator("#btn-roster-refresh").click()`
- `simulator/browser/health_run.py:76` `assert "Last known:" in page.locator("#wall-health").inner_text()`
- `simulator/browser/health_run.py:77` `assert page.locator("#btn-roster-refresh").is_enabled()`
- `simulator/browser/health_run.py:80` `page.locator("#btn-roster-refresh").click()`
- `simulator/browser/health_run.py:84` `assert "1 of 1 online" in page.locator("#device-count").inner_text()`

### image_efficiency.py

Measured image-wall efficiency baseline (TWR-16).

Scenario/check entry points: `run_profile`, `run_wall_rounds`

- `simulator/browser/image_efficiency.py:671` `page.set_default_timeout(30_000)`
- `simulator/browser/image_efficiency.py:993` `page.set_default_timeout(30_000)`

### operator_accessibility.py

Native-markup keyboard and rendered-layout probes on isolated shipped clients.

- `simulator/browser/operator_accessibility.py:46` `names = page.get_by_role("tab").all_text_contents()`
- `simulator/browser/operator_accessibility.py:49` `page.locator("[role=tab][aria-selected=true]").inner_text().strip()`
- `simulator/browser/operator_accessibility.py:62` `expect(p.locator("body")).to_have_attribute("data-connection", "current")`
- `simulator/browser/operator_accessibility.py:117` `expect(p.locator("#layout-msg")).to_contain_text("Enter an arrangement name")`
- `simulator/browser/operator_accessibility.py:127` `expect(p.locator("#scene-message")).to_contain_text("Enter a content name")`
- `simulator/browser/operator_accessibility.py:135` `rows = p.locator("#grid-order li[data-device-id]")`
- `simulator/browser/operator_accessibility.py:166` `expect(p.locator("body")).to_have_attribute("data-stage-mode", "arrangement-preview")`
- `simulator/browser/operator_accessibility.py:169` `dialog = p.locator("#draft-resolution")`
- `simulator/browser/operator_accessibility.py:171` `trigger_id = p.locator("[role=tab][aria-selected=true]").get_attribute("id")`
- `simulator/browser/operator_accessibility.py:196` `p.locator("#btn-cancel").click()`

### readiness_acceptance.py

Bounded acceptance evidence for the image-wall roadmap (TWR-04/05/06/08/09/10/11/13).

Scenario/check entry points: `run_tool`

- `simulator/browser/readiness_acceptance.py:276` `if name == "Settings" and page.locator("#device-sheet").is_visible() and not page.locator("#server-drawer").is_visible():`
- `simulator/browser/readiness_acceptance.py:322` `wait_until(lambda: "online" in page.locator("#device-count").inner_text(),`
- `simulator/browser/readiness_acceptance.py:337` `wait_until(lambda: page.locator("#status").get_attribute("data-state") == "connected",`
- `simulator/browser/readiness_acceptance.py:346` `page.locator("#measurement-details").evaluate("node => node.open = true")`
- `simulator/browser/readiness_acceptance.py:347` `page.locator("#tablet-model").select_option("google-pixel-c")`
- `simulator/browser/readiness_acceptance.py:349` `page.locator("#apply-tablet-model").click()`
- `simulator/browser/readiness_acceptance.py:357` `page.locator("#cal-use-viewport").click()`
- `simulator/browser/readiness_acceptance.py:358` `page.locator("#btn-calibration-save").click()`
- `simulator/browser/readiness_acceptance.py:398` `page.locator(f'#image-gallery [data-asset-id="{asset_id}"] button').click()`
- `simulator/browser/readiness_acceptance.py:399` `page.locator("#image-fit").select_option(fit)`

### reconnect_exclusions_run.py

Live browser acceptance for session exclusions and mid-video reconnect.

Scenario/check entry points: `scenario`


### recovery_acceptance_run.py

Live browser acceptance for terminal recovery holds and recovery boundaries.

Scenario/check entry points: `scenario_markers`, `scenario_violations`, `run_scenario`


### recovery_run.py

Software connectivity-recovery trials for one real browser client.


### redesign_acceptance.py

Isolated shipped-client acceptance. --artifacts must name a new directory.

Scenario/check entry points: `run_scenario`

- `simulator/browser/redesign_acceptance.py:449` `(self.out / (stem + "-ax.yml")).write_text(page.locator("body").aria_snapshot())`
- `simulator/browser/redesign_acceptance.py:485` `locator = self.page.locator(selector) if isinstance(selector, str) else selector`
- `simulator/browser/redesign_acceptance.py:487` `for detail in locator.locator("xpath=ancestor::details").all():`
- `simulator/browser/redesign_acceptance.py:489` `summary = detail.locator(":scope > summary")`
- `simulator/browser/redesign_acceptance.py:498` `locator = self.page.locator(selector) if isinstance(selector, str) else selector`
- `simulator/browser/redesign_acceptance.py:519` `locator = self.page.locator(selector)`
- `simulator/browser/redesign_acceptance.py:524` `options = locator.locator("option").evaluate_all("es=>es.map(e=>e.value)")`
- `simulator/browser/redesign_acceptance.py:539` `expect(self.page.locator(selector)).to_be_visible()`
- `simulator/browser/redesign_acceptance.py:540` `self.page.locator(selector).focus()`
- `simulator/browser/redesign_acceptance.py:543` `self.page.locator(selector).check()`

### renewal_acceptance.py

Renewal acceptance driver for the operator-console renewal contracts.

Scenario/check entry points: `run_scenario`

- `simulator/browser/renewal_acceptance.py:374` `self.page.set_default_timeout(10_000)`
- `simulator/browser/renewal_acceptance.py:680` `select_tablet(page.locator(f':is(.dev-pick,.roster-pick):visible[data-device-id="{device_id}"]').first)`
- `simulator/browser/renewal_acceptance.py:682` `reports[device_id] = page.locator("#tablet-facts").evaluate("""e => {`
- `simulator/browser/renewal_acceptance.py:686` `page.locator("#tablet-back").click()`
- `simulator/browser/renewal_acceptance.py:696` `locator = page.locator(selector)`
- `simulator/browser/renewal_acceptance.py:730` `len(shown) == 1 and page.locator("#wall-health").text_content().count("showing ") == 1`
- `simulator/browser/renewal_acceptance.py:731` `and page.locator("#wall-health-short").text_content() == "5/6",`
- `simulator/browser/renewal_acceptance.py:732` `{"visible": shown, "accessible": page.locator("#wall-health").text_content()},`
- `simulator/browser/renewal_acceptance.py:741` `health_text == "5 of 6 showing " + page.locator("#image-title").inner_text()`
- `simulator/browser/renewal_acceptance.py:749` `page.locator("#stage-technical").evaluate("e=>e.open=true")`

### report.py

Normalize one browser evidence report into a common summary.


### restoration_acceptance.py

Deterministic restoration acceptance driver for the supported operator routes.

Scenario/check entry points: `scenario_pass`, `run_scenario`

- `simulator/browser/restoration_acceptance.py:777` `self.page.set_default_timeout(10_000)`
- `simulator/browser/restoration_acceptance.py:781` `self.page.locator("#tablet-url").wait_for(state="visible")`
- `simulator/browser/restoration_acceptance.py:862` `page.set_default_timeout(10_000)`
- `simulator/browser/restoration_acceptance.py:948` `selector = self.page.locator("#compact-task-select")`
- `simulator/browser/restoration_acceptance.py:952` `self.page.get_by_role(`
- `simulator/browser/restoration_acceptance.py:957` `for detail in locator.locator("xpath=ancestor::details").all():`
- `simulator/browser/restoration_acceptance.py:959` `detail.locator(":scope > summary").click()`
- `simulator/browser/restoration_acceptance.py:962` `locator = self.page.locator(selector)`
- `simulator/browser/restoration_acceptance.py:967` `locator = self.page.locator(selector)`
- `simulator/browser/restoration_acceptance.py:1164` `encoded = page.locator("#surface").evaluate("canvas => canvas.toDataURL('image/png')")`

### restore_run.py

Restore-then-play evidence for a real H.264 upload (software, not optical).

Scenario/check entry points: `run_tool`


### run.py

Disposable Chromium evidence for the current logical still-image wall.

Scenario/check entry points: `run_cuts`, `run_suspend`, `run_with_signals`

- `simulator/browser/run.py:331` `page.set_default_timeout(10_000)`
- `simulator/browser/run.py:367` `await page.locator("#surface").wait_for(state="visible")`
- `simulator/browser/run.py:371` `encoded = await page.locator("#surface").evaluate("c => c.toDataURL('image/png')")`
- `simulator/browser/run.py:619` `encoded = await page.locator("#surface").evaluate("c => c.toDataURL('image/png')")`
- `simulator/browser/run.py:1061` `await controller.get_by_role("button", name="Calibration", exact=True).click()`
- `simulator/browser/run.py:1066` `await controller.locator('.map-vis[data-calibration="true"]').count() >= 1)`
- `simulator/browser/run.py:1068` `await controller.locator(".map-number").count() >= 1)`
- `simulator/browser/run.py:1070` `await controller.locator(f"button[data-asset='{asset}']").click()`
- `simulator/browser/run.py:1072` `await controller.locator("#btn-image-apply").click()`
- `simulator/browser/run.py:1501` `encoded = await page.locator("#surface").evaluate("c => c.toDataURL('image/png')")`

### test_browser.py

Driver self-tests; no standalone browser acceptance claim.

Scenario/check entry points: `test_signal_cancellation_keeps_event_reader_alive_during_cleanup`, `test_first_cancellation_during_cleanup_after_launch_failure`, `test_first_sigterm_during_dispose_saves_failure_report_and_cleans_server`, `test_browser_process_detection_handles_rewritten_chromium_argv`, `test_artifacts_reject_repository_and_existing_directory`, `test_child_environment_fences_operator_data`, `test_hand_derived_pixel_anchors`, `test_coded_png_anchors`, `test_stop_server_reaps_even_when_called_twice`, `test_partial_server_launch_cleanup`, `test_missing_browser_saves_failure_report_and_cleans_server`, `test_cuts_argument_is_validated_before_anything_is_created`, `test_clock_adapter_step_changes_the_epoch_only_past_the_suspend_threshold`, `test_csp_safe_predicate_polling_is_bounded_and_preserves_arguments`, `test_video_audit_requires_completed_superseding_static_render`, `test_watch_page_records_fetch_lifecycle_for_video_audit`, `scenario`

- `simulator/browser/test_browser.py:252` `[sys.executable, str(REPO / "simulator/browser/run.py"), "--artifacts", str(destination), "--cuts", "1"],`
- `simulator/browser/test_browser.py:256` `assert "--cuts" in result.stderr`
- `simulator/browser/test_browser.py:349` `def set_default_timeout(self, value):`

### test_composition_gates.py

Gate arithmetic for composition_gates.py (pure functions, no browser).

Scenario/check entry points: `test_area_fraction`, `test_box_drift_uses_size_and_position`, `test_fill_is_limiting_dimension`, `test_aspect_error`, `test_fully_inside_edges`, `test_verdict_shape`, `test_region_overlaps_checks_both_axes_and_containment`


### test_evidence.py

Hand-checked cases for the hard-cut analysis. No browser needed.

Scenario/check entry points: `scenario`, `test_nearest_rank_percentiles`, `test_delta_is_per_event_max_minus_min_not_pooled`, `test_missing_paint_is_a_failed_event_and_makes_the_whole_show_unbounded`, `test_two_failures_push_the_whole_show_p95_to_unbounded`, `test_a_member_without_a_commit_fails_the_event_and_server_misses_are_named`, `test_event_with_no_commit_for_any_member_is_not_omitted`, `test_wrong_pixel_is_not_a_completed_cut`, `test_a_late_paint_for_a_repeated_asset_is_not_borrowed_from_the_next_occurrence`, `test_degradation_windows_merge_consecutive_events_and_report_the_reanchor`, `test_lateness_uses_the_server_to_page_clock_mapping`, `test_small_samples_do_not_crash`


### test_experience_acceptance.py

Cheap checks for entry-evidence classification, independent of browser startup.

Scenario/check entry points: `test_visible_content_is_not_tied_to_fixture_count`, `test_absent_and_occluded_targets_are_reported`, `test_below_fold_target_fails_entry`


### test_image_efficiency.py

Focused checks for the TWR-16 evidence arithmetic and byte matching.

Scenario/check entry points: `test_nearest_rank_uses_the_ranked_sample_not_interpolation`, `test_summary_reports_count_p50_p95_range_and_handles_empty`, `test_summaries_keep_errors_out_of_latency_samples`, `test_asset_bytes_are_attributed_across_resets_and_both_id_forms`


### test_report.py

Cases for the browser report adapter. No browser or /tmp dependency.

Scenario/check entry points: `scenario_report`, `test_top_level_report_is_normalized`, `test_restore_grouped_checks_use_summary_counts_without_runner_identity`, `test_scenario_rows_and_counts_are_not_summed_into_checks`, `test_partial_report_keeps_its_state_and_does_not_gain_counts`, `test_controller_scenario_results_keep_their_ids_and_counts`, `test_legacy_metadata_and_failure_are_read_without_inventing_a_state`, `test_inconsistent_reports_are_flagged`, `test_cli_prints_one_object_per_report_and_exits_one_on_inconsistency`, `test_cli_exits_zero_when_every_report_is_consistent`


### video_run.py

Real-browser R4 video evidence on a disposable server.

Scenario/check entry points: `check_advancing`, `check_no_horizontal_clipping`

- `simulator/browser/video_run.py:488` `await editor.get_by_role("tab", name="Settings", exact=True).click()`
- `simulator/browser/video_run.py:498` `list_text = await editor.locator("#playlist-items").inner_text()`
- `simulator/browser/video_run.py:527` `report["editor_text_playing"] = (await editor.locator("body").inner_text())[:4000]`
- `simulator/browser/video_run.py:531` `await editor.locator("#playback-more > summary").click()`
- `simulator/browser/video_run.py:533` `facts = await editor.locator("#playback-facts").inner_text()`
- `simulator/browser/video_run.py:537` `summary = await editor.locator("#playback-status").inner_text()`
- `simulator/browser/video_run.py:668` `report["editor_text"] = (await editor.locator("body").inner_text())[:4000]`

### video_transitions_run.py

Real-browser video transition evidence on a disposable server.


## Coverage gaps against the preservation brief

“End-to-end” below means shipped software through a browser, real HTTP and sockets. Source presence establishes that a scenario exists, not that it passed on this revision. This audit only executed make test.

| Behavior | Existing software evidence | Remaining gap before migration |
| --- | --- | --- |
| Device discovery and joining | Simulator registration/handshake/presence; first_run_acceptance joins six browser clients and verifies setup S0–S3; readiness and join QR backend tests | Add new client joining during a dirty inspector edit; persistent UUID across reload, failed registration and old-browser UUID fallback in real client page |
| WebSocket updates | operator_sync VM tests, backend sockets, readiness/renewal browser clients and live status transitions | React island mount/unmount must not create duplicate connections, listeners or replayed mutations |
| Controller polling reconciliation | operator_sync rejects slower reads and queues refresh; operator_unreachable covers transport failure | Explicit browser test that blocks only /ws/controller, allows HTTP, mutates another controller and observes correct state without draft/focus loss; do not infer fallback coverage from healthy-WS tests |
| Physical scaling and crop/fit | client_view fixture matrices, client_image canvas math and physical transforms; readiness browser calibrations and still rendering | Cross-product of asymmetric bezels, all quarter turns, anisotropic axes, fractional CSS size, DPR and contain/cover; physical mm and optical seams remain unproved |
| Profiles, ruler, calibration, mapping | physical_calibration and ruler unit tests; backend calibration suites; redesign measured UI journeys and renewal measured blockers | Add one browser journey from ruler review through saved profile/calibration to wall paint, including stale review rejection; physical ruler reading remains a human hardware gate |
| Reconnection and recovery | client render-status/image race tests, simulator reconnect/takeover/restart, recovery_run, field_run, video recovery/exclusions drivers | Controller remount while recovery is pending; server generation change while modal has unsaved data; real OS suspend/Wi-Fi are missing |
| Relative layout | operator_geometry fit/arrange/rotate; simulator logical wall; redesign custom relative browser journey | Run same behavior in legacy and island paths, preserving bounds, current scene and selected device |
| Physical layout | operator_grid/stage/physical sizing, backend physical grids, redesign measured position/rotation/nudge | Mixed profile revisions and all mounting orientations in one deterministic browser matrix |
| Packed layouts | operator_geometry and controller_sizing; redesign journey explicitly exercises pack | Add standalone named packed case with expected per-device DTO and pixel anchors, so a broad journey cannot silently stop exercising it |
| Tiled layouts | simulator auto tiling and seam cases; operator_geometry fixed tile; redesign UI tile and fixed bounds | Explicit custom row/column and holes cases at mobile width, plus legacy experimental route when it remains supported |
| Custom bounds and rotation | tests/operator_geometry.test.js:3, :115; tests/operator_grid.test.js:23; simulator/browser/_redesign_scenarios.py:190, :244, :469, :490 | Freeze negative origins, asymmetric bezel rotation and 0/90/180/270 outputs separately, not only “layout saved” assertions |
| Physical old-tablet compatibility | README and validation docs explicitly leave hardware gates missing | No automated suite here proves Safari on iPadOS 15, old Android WebView, optical scaling, Wi-Fi or overnight soak |

The arrangement coverage statement is substantive: the existing redesign journey names custom logical size, bezel, undo/redo, pack, tile and fixed bounds, then recalls the relative layout after a measured layout (simulator/browser/_redesign_scenarios.py:469–490). Do not replace it with only 2×2 and 1×4 smoke tests. No claim is made that every arrangement/rotation/profile combination has end-to-end coverage.

Runtime facts relevant to CI scheduling: recovery_run has 20 trials and a 17-second offline period per trial, so offline time alone is at least 340 seconds (simulator/browser/recovery_run.py:43–44, :108–117). recovery_acceptance_run deliberately waits for a roughly 31-second timeout. fleet_soak defaults to 60 seconds of sampling, plus setup/recovery/stop-start overhead (simulator/browser/fleet_soak.py:1197–1198). controller_run builds a 20-second video, decode_probe a 10-second clip. Those clip lengths are not full-suite timings. Renewal, composition, accessibility, redesign and first-run elapsed runtimes must be collected from the first CI baseline run rather than guessed.

## Tests to land before migration

### Phase 0: freeze behavior on the current frontend

1. Add a versioned fixture manifest derived from simulator's existing 18-tablet cohort. Use stable UUIDs and numbers, mixed viewport sizes/DPR, two absent reservations, one unsupported/old-protocol device, asymmetric bezels, historical model/profile/calibration revisions and explicit layout order. Use fresh isolated DB/media/asset roots and a private free port per worker. Reuse the same domain fixtures in Python, JS math and browser setup; preserve independent hand-derived pixel anchors so tests do not merely recompute expectations with production geometry.
2. Freeze named arrangements for relative fixed/custom, relative fitted, packed, tiled with custom rows/columns, empty trailing cells, measured grid, manual physical bounds and all four mounting angles. Freeze scene images with portrait, landscape and square aspect ratios, transparency/background, missing bytes and changed bytes. Record expected v3 layout/scene DTOs, revision changes, render plans and sampled pixel positions. Include current scene preserved on layout recall and current layout preserved on scene recall.
3. Add browser characterization for join → preview arrangement → apply → select image → Show → all clients acknowledge; preview and upload must never mutate the live scene. Exercise failure/retry, offline/hidden/unplaced/mapping-blocked evidence, stale request ordering, CAS conflict, ambiguous write timeout and late result after selection switches from A to B. Preserve the existing subject-save tests' exact data ownership guarantees.
4. Add polling-only, controller socket reconnect, device takeover, server restart/generation, asset cancellation, hidden/resume and identity persistence browser scenarios. Assert visible output AND server state AND exact mutation count. Wait for evidence tokens/conditions rather than fixed sleeps.
5. Record visual baselines at **390×844, 820×1180, 1440×900** for empty/joining, full live wall, selected tablet, image preview, arrangement preview, Measure steps, dirty-navigation confirmation, saved recall, loading, failure and permission denial. Pin Chromium/OS/fonts/DPR, wait for fonts and settled render acknowledgements, disable animation, freeze only nondeterministic clocks. Keep status text unmasked when it is the behavior being tested. Keep geometry thresholds and semantic assertions alongside image diffs. Add 320/768/1024 spot checks to satisfy frontend-ui-engineering's breakpoint rule. Fractional viewport checks remain an explicit limitation until the runner measures the requested width.
6. Freeze accessibility behavior: keyboard tabs/roving arrows; labelled inputs/errors; one meaningful status summary; one inspector bound to selection; Measure modal step order, safe cancellation, focus containment and return; no hidden/inert control receives focus; gallery selection retains focus/scroll. Add axe checks where supported and a short manual VoiceOver/TalkBack checklist. Scores alone are insufficient.

Do not approve snapshots blindly. Direction B is the target layout, so separate behavior characterization from the deliberate later visual change. Before an island lands, establish and review Direction B snapshots on its accepted baseline, then require migration parity with that baseline.

### Replace fragile locators safely

Python Playwright uses `get_by_role`; the TypeScript equivalent is `getByRole`. Prefer named roles within a semantic region or dialog, plus `getByLabel` for fields. For example, `page.getByRole('button', {name: 'Show image', exact: true})` replaces `#show-image`; scope duplicate Apply actions to the named inspector or arrangement dialog. Replace `#image-fit` with its associated field label, and saved action selectors with the record's named row/region then `getByRole('button', {name: 'Recall', exact: true})`. Verify the actual accessible name before converting.

Keep `#surface` or a dedicated test identifier for canvas pixel sampling, SVG geometric anchors, and application integration IDs consumed by legacy code. Role selectors do not describe a crop matrix. Keep explicit uniqueness assertions for primary actions and nonduplicated statuses. Do not weaken a selector with `.first()` to hide duplicate controls. Replace selectors one scenario at a time on the current app and prove they still fail for the original regression. Generated component IDs may change; label/control relationships must remain valid.

Convert source-sliced tests into imported pure-domain tests or public behavioral tests **before** bundling the feature they guard. For renderAll order, test that an inventory/status update cannot erase a draft or present stale state, rather than asserting internal call order. For saved-name handling, keep snapshot_names.json as cross-language input and assert field errors plus no network request for invalid names. Preserve late-response, uncertainty and exact-write-count cases as browser or session tests. Do not retain a permanent test-only window export just to make old VM tests pass.

### API and realtime contracts

Use FastAPI `app.openapi()` or isolated `/openapi.json` to capture a reviewed normalized schema baseline. Generate the controller TypeScript DTO/client types from it. Assert required request/response schemas and HTTP methods for registration, v3 config/runtime, images, scene/layout/grid, profiles/calibration-check, identify/recovery, snapshots and readiness. Exercise valid and invalid requests against TestClient and validate actual JSON responses, headers, ETags and error bodies against the reviewed contract. Schema generation alone cannot prove behavior, and routes returning untyped dictionaries may need an explicit JSON Schema fixture.

OpenAPI does not describe WebSocket frames. Keep a separately versioned fixture schema from PROTOCOL.md for welcome/config/runtime/render_ack/identify, generation/revision/connection tokens, close codes and ownership. Replay out-of-order, duplicate, missing-capability and stale-generation frames through both legacy and island adapters. Test 401/403/409/412, operator origin admission, CSP, and abort vs ambiguous write outcomes. Do not silently update schemas to make a failing migration pass.

### React island verification

Start with one presentation island inside an explicit owned root. Legacy code owns its surrounding DOM; React owns its children. Feed immutable DTOs into the island and return explicit events to the existing serialized session. Keep one authoritative transport and command owner during coexistence.

Add **Vitest + Testing Library** only when the first React feature is introduced, not as a prerequisite dependency for auditing today's app. Component tests use `screen.getByRole`, `getByLabelText` and user-event to cover rendering, keyboard interactions, selected subject, busy/error/empty states, validation and focus. Test reducer/session behavior separately with the shared fixtures. StrictMode mount/unmount tests must prove cleanup of listeners/subscriptions and no duplicate requests or writes. jsdom cannot prove real dialog top layer, scrolling, SVG sizing or canvas output.

Playwright integration must run legacy controller + real React island + FastAPI + shipped tablet pages. Verify one subscription, one write per action, selection changes during saves, pending draft navigation and island disposal/reentry. Run production Vite build as well as development smoke. Walk all referenced chunks/fonts/CSS behind the real controller entry and proxy; assert correct MIME, CSP, no external-origin dependencies and working cache invalidation. Keep client resources isolated from React/Tailwind output. Tablet bundle compatibility is its own contract.

## Proposed CI gates by migration phase

| Phase | Required PR gates | Extended gates / promotion |
| --- | --- | --- |
| 0, characterization | Existing make test, make sim, new DTO/wire fixtures, new browser smoke, accessibility checks and reviewed 390/820/1440 baselines | Run full renewal/composition/readiness/redesign/restoration once; record elapsed times, tool versions, exact skips and known fractional limitations |
| 1, build tooling only | Same gates plus production asset graph/CSP/cache/offline/ingress checks; application source behavior unchanged | Verify controller entry, experimental compatibility route and unmodified tablet resources; fail unknown warning/request errors |
| 2, first island | Same plus tsc, Vitest/Testing Library, island integration and relevant visual states on Chromium/WebKit | Full legacy + island journeys; hardware smoke before enabling by default |
| 3, feature slices | All prior relevant gates; arrangement matrix for geometry slices; modal/focus/a11y tests for Measure; transport and CAS matrix for state slices | Nightly video/recovery/exclusions/restoration, 18-device simulator and longer fleet runs; no failing slice promoted |
| 4, remove legacy owner | Full suites, production integration, API/wire diff review, no duplicate ownership, no dead legacy asset references | Real iPadOS 15 and older Android validation plus documented rollback rehearsal; hardware gates stay separate from CI green |

Gate principle: no new failures, no lost scenario/check counts, no new unexplained skips, no unexpected page/console/network errors. Compare exact named obligations and states; never sum overlapping suite check totals into a fake coverage score. Reuse simulator/browser/report.py's explicit incomplete/contradiction handling. Keep flaky or unsupported evidence visible. The five supplied fractional-width baseline limitations are a narrow named exception requiring unchanged observations, not a blanket “allow failures” setting. G7's “no renderer/backend edits” rule applies to controller-only phases; a deliberately scoped later change needs a revised reviewed gate, not a concealed bypass.

## Applied skill rules and limits

- frontend-ui-engineering's “Verify With What the Project Has” shaped this audit: run make test now; propose Vitest only with a React island. Its verification list shaped keyboard, responsive, console, state and accessibility gates, and its separation of fetching/presentation shaped the island boundary.
- impeccable's Operate mode and “verify by looking at the rendered result at the sizes it ships at” shaped the proposed wall-first visual states and batch screenshot review. This is planning only; no UI edit or rendered inspection was performed here.
- frontend-design's “brief wins” and responsive/focus/reduced-motion quality floor keep Direction B authoritative. Visual parity should preserve the accepted design rather than freeze the rejected rail layout.
- vercel-react-best-practices rules `client-event-listeners`, `client-swr-dedup`, `rerender-derived-state` and `bundle-conditional` motivate cleanup/deduplication, immutable inputs and controller-only asset assertions. RSC/Next.js-specific advice is not applicable to a Vite island.
- web-design-guidelines was loaded as requested. This report is a regression plan, not a claimed compliance audit against its remotely fetched current checklist.
- Modern Web Guidance was searched for accessible dialogs and its accessibility/dialog guides read. The accessibility rule “Don't rely purely on scores” shaped the manual assistive-technology gate. Dialog guidance says to keep the unsaved-change guard in a cancel handler where closedby is unsupported. Tests must exercise dismissal and draft protection on the supported browsers, not merely inspect an attribute. Its current-browser examples do not override the brief's iPadOS 15 support requirement. No recommendation here depends on Popover, Invoker Commands, closedby or Tailwind v4 working on legacy clients.

Unknowns: real tablet browser execution, optical seams, physical measurements, long soak, the runtime cost of most browser drivers and an executed baseline for those drivers on this checkout. These are explicit evidence gaps, not passes.
