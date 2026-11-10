"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
(async () => {
const nodes = new Map();
const document = { activeElement: null, body: { dataset: {} }, getElementById: node, querySelector: selector => node(selector === ".arrange-tools" ? "arrange-tools" : "shared-stage") };
function node(id) {
    if (!nodes.has(id)) nodes.set(id, { dataset: {}, hidden: true, textContent: "", listeners: {}, appends: [],
        setAttribute(name, value) { (this.attrs ||= {})[name] = value; },
        addEventListener(event, fn) { this.listeners[event] = fn; },
        append(child) { this.appends.push(child); child.parent = this; },
        contains(child) { return child === this || child === node(id + "-summary"); },
        querySelector() { return node(id + "-summary"); }, focus() { document.activeElement = this; } });
    return nodes.get(id);
}
const state = { tabName: "content", roster: { a: { online: true }, b: { online: false } }, configLoaded: true, base: { placements: { a: {} } }, draft: { placements: { a: {} } } };
let dirty = false, applied = "a.png", unavailable = false;
node("stage-mode").hidden = false;
node("image-title").textContent = "a.png";
const context = { window: { OperatorState: require("../frontend/controller/operator-state.js") }, document };
vm.createContext(context);
vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);
vm.runInNewContext(fs.readFileSync(require.resolve("../frontend/controller/operator-workspace.js"), "utf8"), context);
const workspace = context.window.OperatorWorkspace.create({ state, arrangementDirty: () => false, arrangementPreview: () => false,
    imageDirty: () => dirty, canCommit: () => true, stageNames: () => ({ applied, pending: "b.png", unavailable }), commitTask: name => { state.tabName = name; } });
workspace.render();
assert.equal(node("commit-applied-name").textContent, "On wall: a.png");
assert.equal(node("first-wall-steps").hidden, true);
assert.equal(node("shared-stage").parent, node("wall-context-content"));
assert.equal(node("stage-mode-label").textContent, "Showing");
state.tabName = "show"; workspace.render();
assert.equal(node("stage-mode-label").textContent, "Showing a.png", "other tasks retain the applied filename");
state.tabName = "content"; workspace.render();
unavailable = true; node("image-title").textContent = "Unavailable image"; workspace.render();
assert.equal(node("stage-mode-label").textContent, "Unavailable image", "unavailable content is never described as showing");
assert.equal(node("stage-mode").hidden, true, "Images does not repeat its unavailable heading in a second status");
state.tabName = "show"; workspace.render();
assert.equal(node("stage-mode").hidden, false, "other tasks keep the missing-image signal visible");
assert.equal(node("stage-mode-label").textContent, "Unavailable image");
state.tabName = "content"; unavailable = false; node("image-title").textContent = "a.png"; workspace.render();
assert.equal(node("stage-mode").hidden, false);
assert.equal(node("stage-mode-description").textContent, "");
node("edited-field").focus();
const attached = node("wall-context-content").appends.length;
workspace.render(); workspace.render();
assert.equal(node("wall-context-content").appends.length, attached, "runtime updates do not detach the stage or SVG focus");
assert.equal(document.activeElement, node("edited-field"));
assert.equal(node("stage-applied-chip").textContent, "Applied: a.png", "the workbench stage names the applied content");
assert.equal(node("stage-draft-chip").hidden, true, "no draft chip without a pending image");
state.tabName = "tablet"; dirty = true; state.previewContent = { type: "image" }; workspace.render();
assert.equal(node("shared-stage").parent, node("wall-context-tablet"));
assert.equal(node("stage-mode-label").textContent, "Preview · b.png");
assert.equal(node("stage-mode-description").textContent, "Image preview, not shown");
assert.equal(document.body.dataset.stageMode, "image-preview");
assert.equal(node("stage-draft-chip").textContent, "Draft: b.png", "the workbench stage names the pending image");
assert.equal(node("draft-state").textContent, "Draft · not on wall", "the shelf names the draft state");
state.rosterError = true; workspace.render();
assert.equal(document.body.dataset.connection, "stale");
node("add-image").listeners.click();
assert.equal(node("image-addition").open, true);
assert.equal(document.activeElement, node("image-addition-summary"), "disabled upload leads to availability explanation");
node("upload-form").hidden = false; node("add-image").listeners.click();
assert.equal(document.activeElement, node("upload-file"), "admitted upload leads to the native file control");
dirty = false; state.previewContent = null; applied = null;
state.scene = { content: { type: "color" } }; workspace.render();
assert.equal(node("stage-mode-label").textContent, "Showing tablet colours", "test colours on the wall are not reported as nothing");
state.scene = { content: { type: "calibration" } }; workspace.render();
assert.equal(node("stage-mode-label").textContent, "Showing calibration pattern");
state.base = { placements: {} }; workspace.render();
assert.equal(node("stage-mode-label").textContent, "Nothing shown", "a scene with no tablets on the wall shows nothing");
state.base = { placements: { a: {} } }; state.scene = null; workspace.render();
assert.equal(node("stage-mode-label").textContent, "Nothing shown");
const tabletOnly = ["image-details-disclosure", "stage-technical", "arrange-tools"];
state.roster = {}; workspace.render();
assert.equal(node("tablet-joining").open, true);
assert.deepEqual(tabletOnly.map(id => node(id).hidden), [true, true, true], "with no tablets, Images and Arrange offer only Add tablets");
state.roster = { a: { online: true } }; workspace.render();
assert.equal(node("tablet-joining").open, false);
node("tablet-joining").open = true; workspace.render();
assert.equal(node("tablet-joining").open, true, "polls preserve an opened joining disclosure");
assert.deepEqual(tabletOnly.map(id => node(id).hidden), [false, false, false], "details and arrange tools return once a tablet joins");
state.rosterError = false; state.base = { placements: {} }; state.tabName = "content"; state.roster = { a: { online: true } }; workspace.render();
node("image-title").textContent = "Nothing shown"; workspace.render();
assert.equal(node("stage-mode").hidden, true, "empty Images announces Nothing shown only once");
assert.equal(node("wall-empty").hidden, false);
assert.equal(node("empty-add-tablets").textContent, "Arrange tablets", "online tablets lead the empty Images card to Arrange");
await node("empty-add-tablets").listeners.click();
assert.equal(state.tabName, "show", "the empty Images action opens Arrange");
for (const task of ["show", "tablet"]) { state.tabName = task; workspace.render(); assert.equal(node("wall-empty").hidden, true, "no empty card on " + task); }
state.tabName = "content"; state.roster = { a: { online: false } }; workspace.render();
assert.equal(node("empty-add-tablets").textContent, "Add tablets");
await node("empty-add-tablets").listeners.click();
assert.equal(state.tabName, "tablet", "without online tablets the action opens Tablets");
console.log("Workspace relocates one stage only on task changes and preserves keyed field focus and admitted entry points");

const controller = fs.readFileSync(require.resolve("../frontend/controller/physical.js"), "utf8");
const taskSource = controller.slice(controller.indexOf("    function commitTask("), controller.indexOf("    function onTabKeyDown("));
const sequence = [];
const taskState = { tabName: "tablet", tabScroll: {} };
const tasks = ["tablet", "content", "show"].map(name => ({ name,
    tab: { setAttribute() {} }, panel: { hidden: true, querySelector() { return null; } } }));
const taskContext = { document, state: taskState, el: {}, tabEntries: () => tasks,
    workspace: { render() { sequence.push("move:" + taskState.tabName); } },
    renderStage() { sequence.push("draw:" + taskState.tabName); } };
vm.createContext(taskContext); vm.runInContext(taskSource, taskContext);
assert.equal(taskContext.commitTask("content"), true);
assert.deepEqual(sequence, ["move:content", "draw:content"], "task change draws immediately after state and host change");
sequence.length = 0;
taskContext.commitTask("content");
assert.deepEqual(sequence, ["move:content"], "re-entering the active task needs no extra draw");
console.log("Task commit draws the new task immediately after moving the original stage");

{
    const forms = require("../frontend/controller/operator-forms.js").create();
    let layoutDirty = false, imageDirty = false;
    const labels = { content: "Images", tablet: "Tablets", show: "Arrange", saved: "Saved", system: "Settings" };
    const entries = Object.entries(labels).map(([name, label]) => ({ name, tab: {
        textContent: label, dot: name === "saved" ? null : { hidden: true }, attrs: {},
        querySelector() { return this.dot; },
        setAttribute(key, value) { this.attrs[key] = value; }, getAttribute(key) { return this.attrs[key]; }
    } }));
    const selector = { options: entries.map(e => ({ value: e.name, textContent: labels[e.name], setAttribute() {} })),
        parentElement: { dataset: {} }, setAttribute() {} };
    const note = { textContent: "" };
    const ctx = { state: { playlistDirty: false }, tabletForms: forms, tabEntries: () => entries,
        isDirty: () => layoutDirty, operatorGrid: { dirty: () => false }, operatorContent: { dirty: () => imageDirty },
        document: { getElementById: id => id === "compact-task-select" ? selector : note } };
    vm.createContext(ctx);
    vm.runInContext(controller.slice(controller.indexOf("    function syncTabDots("), controller.indexOf("    function syncTopbarTransport(")), ctx);
    const tab = name => entries.find(e => e.name === name).tab;
    layoutDirty = true; ctx.syncTabDots();
    assert.equal(tab("show").dot.hidden, false, "geometry drafts belong to Arrange");
    assert.equal(tab("tablet").dot.hidden, true, "geometry drafts do not mark Tablets");
    assert.equal(note.textContent, "Draft: Arrange", "closed navigation names the draft owner");
    layoutDirty = false; imageDirty = true; ctx.syncTabDots();
    assert.equal(tab("content").attrs["aria-label"], "Images, unsaved changes", "image previews are not announced as playlist drafts");
    assert.equal(note.textContent, "Draft: Images");
    imageDirty = false;
    forms.observe("A", "profile", { width: 100 }, "base"); forms.edit("A", "profile", { width: 101 }, "base"); ctx.syncTabDots();
    assert.equal(note.textContent, "Draft: Settings", "profile edits retain their Settings owner across tablet selection");
    forms.discard("A", "profile");
    forms.observe("B", "model", { model: "" }, "base"); forms.edit("B", "model", { model: "manual" }, "base"); ctx.syncTabDots();
    assert.equal(note.textContent, "Draft: Settings", "unconfirmed model choices retain their Settings owner");
    assert.equal(tab("system").attrs["aria-label"], "Settings, unsaved changes");
    forms.discard("B", "model");
    forms.observe("A", "name", { name: "A" }, "base"); forms.edit("A", "name", { name: "Lobby" }, "base"); ctx.syncTabDots();
    assert.equal(note.textContent, "Draft: Tablets", "tablet naming has its own owner");
    forms.discard("A", "name"); ctx.syncTabDots();
    assert.equal(note.textContent, "", "discard clears the named draft hint");
    assert.ok(entries.every(e => !e.tab.dot || e.tab.dot.hidden));
}

{
    const html = fs.readFileSync(require.resolve("../frontend/controller/physical.html"), "utf8");
    const count = id => (html.match(new RegExp('id="' + id + '"', "g")) || []).length;
    for (const id of ["workbench-stage", "commit-shelf", "wall-status", "exception-rail", "exception-strip", "exception-roster", "device-list", "show-image", "presentation-checks", "stage-svg", "image-gallery", "draft-resolution", "device-sheet"]) {
        assert.equal(count(id), 1, "the shell owns exactly one #" + id);
    }
    const images = html.slice(html.indexOf('id="panel-content"'), html.indexOf('id="panel-system"'));
    for (const id of ["workbench-stage", "commit-shelf", "commit-bar", "commit-draft-name", "commit-applied-name", "jump-to-library", "wall-status", "exception-rail", "exception-strip", "exception-roster", "wall-context-content"]) {
        assert.ok(images.includes('id="' + id + '"'), "Images contains #" + id);
    }
    assert.equal(images.includes('id="device-list"'), false, "the Images rail never duplicates the Tablets roster");
    const tablets = html.slice(html.indexOf('id="panel-tablet"'), html.indexOf('id="panel-content"'));
    assert.ok(tablets.includes('id="device-list"'), "Tablets keeps the real device roster");
    assert.ok(!tablets.includes('id="exception-roster"'), "the exception roster is not the Tablets roster");
    assert.equal((html.match(/id="wall-context-content"/g) || []).length, 1, "one Images stage host");

    const saved = html.slice(html.indexOf('id="panel-saved"'), html.indexOf('id="wall-context-park"'));
    for (const id of ["saved-layouts", "saved-scenes", "saved-empty", "saved-scenes-empty", "layouts-status", "scenes-status", "layouts-count", "scenes-count", "return-point"]) {
        assert.equal(count(id), 1, "Saved owns exactly one #" + id);
    }
    assert.equal((saved.match(/class="saved-list"/g) || []).length, 2, "Saved keeps one arrangement list and one content list");
    assert.ok(saved.includes("Automatic restore point saved"), "the automatic return point is labelled");
    assert.ok(saved.includes("Recall geometry from return point"), "the return point names geometry, not content");

    const settings = html.slice(html.indexOf('id="panel-system"'), html.indexOf('id="panel-saved"'));
    for (const id of ["settings-evidence", "settings-diagnostics", "backup-restore", "settings-experimental", "diag-last-known", "operator-readiness-backup", "readiness-status", "btn-readiness-refresh", "btn-diag-refresh", "btn-diag-verify", "cal-live-viewport"]) {
        assert.equal(count(id), 1, "Settings owns exactly one #" + id);
    }
    for (const heading of ["Joining and launch admission", "Diagnostics and current evidence", "Backup and restore", "Measurements and calibration", "Experimental"]) {
        assert.ok(settings.includes(heading), "Settings groups " + heading);
    }
    assert.equal((settings.match(/id="readiness-message"/g) || []).length, 0, "Copy feedback stays with the joining surface");
    assert.equal(count("readiness-message"), 1, "there is one Copy-only readiness message");
    const joining = html.slice(html.indexOf('id="tablet-joining"'), html.indexOf('id="device-sheet"'));
    assert.ok(joining.includes('id="readiness-message"'), "readiness-message belongs to Add tablets");
    assert.equal((settings.match(/id="presentation-checks"/g) || []).length, 0, "check actions are not duplicated in Settings");

    const source = fs.readFileSync(require.resolve("../frontend/controller/physical.js"), "utf8");
    assert.match(source, /"Recall geometry"/, "arrangements expose geometry recall");
    assert.match(source, /"Preview content"/, "content exposes preview only");
    assert.match(source, /Automatic restore point/, "restore points are labelled in saved rows");
    assert.match(source, /not current evidence for the wall/, "a failed diagnostics read is labelled last known, not current");
    assert.match(source, /Showing last known saved arrangements/, "saved arrangement failures retain an explicit last-known label");
    assert.match(source, /Showing last known saved content/, "saved content failures retain an explicit last-known label");
    console.log("The shared shell owns one stage, one commit surface and the exact workbench slots");
}


{
    const source = fs.readFileSync(require.resolve("../frontend/controller/physical.js"), "utf8");
    const extract = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
    const calls = [];
    const startupState = { configLoaded: false, roster: {}, displays: [], calibrations: [], savedLayouts: [] };
    const statusNodes = new Map();
    const noop = () => {};
    const ctx = { state: startupState, API_LAYOUTS: "/api/v3/layouts", document: { activeElement: null, getElementById(id) {
        if (!statusNodes.has(id)) statusNodes.set(id, { hidden: true, textContent: "" });
        return statusNodes.get(id);
    } }, window: { OperatorState: require("../frontend/controller/operator-state.js") },
        el: {}, clone: structuredClone, isDirty: () => false, operatorContent: { dirty: () => false },
        api: async (method, path, body, options) => { calls.push({ method, path, options }); return { layouts: [], scenes: [] }; },
        setMsg: noop, clearMsg: noop, renderSavedLayouts: noop, renderSavedScenes: noop,
        rememberProfile: noop, rememberCalibration: noop, restorePlaybackExclusions: noop,
        ensureSelection: noop, showConflict: noop, hideConflict: noop, renderAll: noop,
        maybeChooseInitialTab: noop, announce: noop
    };
    vm.createContext(ctx);
    vm.runInContext("let layoutsVersion = 0, scenesVersion = 0, savedScenes = [], layoutsLoaded = false, scenesLoaded = false; let operatorDevices = null;"
        + extract("    async function loadLayouts()", "    const restorePointName")
        + extract("    async function loadScenes()", "    function bindDiagnosticColours()")
        + extract("    function observeSession(", "    function ensureSelection()"), ctx);
    await ctx.loadLayouts(); await ctx.loadScenes();
    assert.equal(calls.length, 0, "Saved reads wait for initial config adoption instead of racing the durable read fence");
    startupState.configLoaded = true;
    const config = { etag: "current", layout: { kind: "logical", width: 100, height: 100, placements: {} } };
    ctx.observeSession({ config, uncertain: false });
    await new Promise(setImmediate);
    assert.equal(calls.length, 3, "first config starts both saved lists exactly once");
    assert.ok(calls.every(call => call.options.fenced === "durable"), "startup keeps the durable read fence");
    assert.equal(vm.runInContext("layoutsLoaded && scenesLoaded", ctx), true);
    ctx.observeSession({ config, uncertain: false }, { runtime: true });
    await new Promise(setImmediate);
    assert.equal(calls.length, 3, "heartbeat updates do not restart saved-list reads");
}

})().catch(error => { console.error(error); process.exitCode = 1; });
