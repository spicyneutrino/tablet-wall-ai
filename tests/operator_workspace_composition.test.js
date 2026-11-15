"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
(async () => {
const nodes = new Map();
const document = { activeElement: null, body: { dataset: {} }, addEventListener() {}, querySelectorAll: () => [],
    getElementById: node, querySelector: () => node("arrange-tools") };
function node(id) {
    if (!nodes.has(id)) nodes.set(id, { id, dataset: {}, hidden: false, textContent: "", listeners: {}, children: [], appends: [], isConnected: true,
        classList: { values: new Set(), toggle(name, yes) { if (yes) this.values.add(name); else this.values.delete(name); } },
        setAttribute(name, value) { (this.attrs ||= {})[name] = value; },
        addEventListener(event, fn) { this.listeners[event] = fn; },
        append(child) { this.appends.push(child); child.parent = this; },
        contains(child) { return child === this; }, scrollIntoView() {}, getClientRects() { return this.hidden ? [] : [1]; },
        querySelector() { return node(id + "-summary"); }, focus() { document.activeElement = this; } });
    return nodes.get(id);
}
const composition = require("../frontend/controller/operator-composition.js");
const state = { get composition() { return { mode: this.mode, selectedTablet: this.selectedId }; },
    mode: "content", roster: { a: { online: true }, b: { online: false } }, configLoaded: true,
    base: { placements: { a: {} } }, draft: { placements: { a: {} } }, scene: { content: { type: "image" } } };
let dirty = false, arrangement = false, applied = "a.png", unavailable = false;
const context = { window: { OperatorState: require("../frontend/controller/operator-state.js") }, document };
vm.createContext(context);
vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);
vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-workspace.js"), "utf8"), context);
const workspace = context.window.OperatorWorkspace.create({ state, arrangementDirty: () => arrangement, arrangementPreview: () => arrangement,
    imageDirty: () => dirty, canCommit: () => true, stageNames: () => ({ applied, pending: "b.png", unavailable }),
    clearSelection: () => { state.selectedId = null; },
    commitMode: name => { state.mode = name; return true; } });
workspace.render();
assert.equal(node("commit-applied-name").textContent, "On wall: a.png");
assert.equal(node("setup-strip").hidden, true);
assert.equal(node("commit-bar").dataset.commit, "idle", "the commit bar is present even without a draft");
assert.equal(node("stage-mode-label").textContent, "Showing");
node("edited-field").focus();
for (const mode of composition.MODES) {
    state.mode = mode; workspace.render();
    assert.equal(document.activeElement, node("edited-field"), "rendering never takes keyed field focus");
    assert.equal([...nodes.values()].reduce((sum, item) => sum + item.appends.length, 0), 0, "the stage and forms are never detached by a mode render");
}
state.mode = "content";
unavailable = true; workspace.render();
assert.equal(node("stage-mode-label").textContent, "Unavailable image", "unavailable content is never described as showing");
unavailable = false; dirty = true; state.previewContent = { type: "image" }; state.selectedId = "a"; workspace.render();
assert.equal(document.body.dataset.subject, "tablet");
assert.equal(document.body.dataset.stageMode, "image-preview");
assert.equal(node("stage-mode-description").textContent, "Image preview, not shown");
assert.equal(node("commit-bar").dataset.commit, "image");
assert.match(node("draft-state").textContent, /b.png.*not on wall/);
assert.equal(node("show-image").classList.values.has("btn-primary"), true);
assert.equal(node("tablet-arrange").classList.values.has("btn-primary"), false, "draft commit takes priority over tablet actions");
state.rosterError = true; workspace.render();
assert.equal(document.body.dataset.connection, "stale");
node("upload-form").hidden = true; node("add-image").listeners.click();
assert.equal(node("image-addition").open, true);
assert.equal(document.activeElement, node("image-addition-summary"), "unadmitted uploads focus the explanation");
node("upload-form").hidden = false; node("add-image").listeners.click();
assert.equal(document.activeElement, node("upload-file"));
dirty = false; state.rosterError = false; state.previewContent = null; applied = null; state.scene = { content: { type: "color" } }; workspace.render();
assert.equal(node("stage-mode-label").textContent, "Showing tablet colours");
assert.equal(node("commit-bar").dataset.commit, "idle");
assert.equal(document.body.dataset.noImage, "true");
assert.equal(node("draft-state").textContent, "No image yet · tablet colours");
assert.equal(node("first-wall-image-action").classList.values.has("btn-primary"), true);
state.scene = { content: { type: "calibration" } }; workspace.render();
assert.equal(node("stage-mode-label").textContent, "Showing calibration pattern");
assert.equal(node("restore-image").classList.values.has("btn-primary"), true, "test restore precedes the selected tablet");
state.base = { placements: {} }; state.rosterError = false; workspace.render();
assert.equal(node("stage-mode-label").textContent, "Nothing shown", "a scene without wall positions cannot claim to be showing");
assert.equal(node("join-strip").hidden, true, "joined tablets replace the join card");
assert.equal(node("setup-strip").hidden, false);
assert.equal(node("first-wall-join").dataset.done, "true");
assert.deepEqual(["first-wall-join", "first-wall-arrange", "first-wall-image"].map(id => node(id).dataset.state), ["done", "current", "blocked"]);
assert.equal(node("first-wall-arrange-action").classList.values.has("btn-primary"), true, "only the current step's action is the filled primary");
assert.equal(node("first-wall-image-action").classList.values.has("btn-primary"), false);
await node("first-wall-arrange-action").listeners.click();
assert.equal(state.mode, "arrange");
workspace.render();
assert.equal(node("grid-preview").classList.values.has("btn-primary"), true);
assert.equal(node("first-wall-arrange-action").classList.values.has("btn-primary"), false);
assert.equal(document.activeElement, node("grid-preview"));
await node("first-wall-image-action").listeners.click();
assert.equal(state.mode, "content");
node("first-wall-join-action").listeners.click();
assert.equal(document.activeElement, node("copy-tablet-url"));
state.roster = {}; workspace.render();
assert.equal(node("first-wall-arrange-action").disabled, true);
assert.equal(node("tablet-joining").open, true);
state.roster = { a: { online: true } }; workspace.render();
assert.equal(node("tablet-joining").open, false);
node("tablet-joining").open = true; workspace.render();
assert.equal(node("tablet-joining").open, true, "runtime updates preserve disclosure state");
state.mode = "arrange"; state.base = { placements: { a: {} } }; state.scene = {}; workspace.render();
assert.equal(node("setup-strip").hidden, false, "a placed wall with no image still has a step to finish");
assert.deepEqual(["first-wall-join", "first-wall-arrange", "first-wall-image"].map(id => node(id).dataset.state), ["done", "done", "current"]);
assert.equal(node("first-wall-image-action").classList.values.has("btn-primary"), true);
state.scene = { content: { type: "image" } }; workspace.render();
assert.equal(node("setup-strip").hidden, true, "the strip disappears once tablets are placed and an image is shown");
state.selectedId = null; state.mode = "content"; state.base = { placements: {} }; state.scene = {}; workspace.render();
assert.equal(await workspace.land(), true, "an unarranged wall with tablets lands on Arrange");
assert.equal(state.mode, "arrange");
state.mode = "content"; state.base = { placements: { a: {} } }; workspace.render();
assert.equal(await workspace.land(), false, "an arranged wall lands in Content");
assert.equal(state.mode, "content");
console.log("Persistent wall, draft identity, precedence and retained form focus passed");

const controller = fs.readFileSync(require.resolve("../frontend/controller/physical.js"), "utf8");
{
    const forms = require("../frontend/controller/operator-forms.js").create();
    let layoutDirty = false, imageDirty = false;
    const entries = [["content", "Content"], ["arrange", "Arrange"], ["test", "Test"]].map(([name, label]) => ({ name, tab: {
        textContent: label, dot: { hidden: true }, attrs: {}, querySelector() { return this.dot; },
        setAttribute(key, value) { this.attrs[key] = value; }
    } }));
    const ctx = { state: { playlistDirty: false }, tabletForms: forms, modeEntries: () => entries,
        isDirty: () => layoutDirty, operatorGrid: { dirty: () => false }, operatorContent: { dirty: () => imageDirty }, document };
    vm.createContext(ctx);
    vm.runInContext(controller.slice(controller.indexOf("    function syncTabDots("), controller.indexOf("    function syncTopbarTransport(")), ctx);
    layoutDirty = true; ctx.syncTabDots(); assert.equal(entries[1].tab.dot.hidden, false);
    layoutDirty = false; imageDirty = true; ctx.syncTabDots();
    assert.equal(entries[0].tab.attrs["aria-label"], "Content, unsaved changes");
    imageDirty = false;
    for (const group of ["profile", "model", "name", "calibration"]) {
        forms.observe("A", group, { value: "base" }, "etag"); forms.edit("A", group, { value: "draft" }, "etag");
        ctx.syncTabDots(); assert.equal(node("device-sheet").dataset.dirty, "true", "tablet field drafts belong to the Tablet panel");
        forms.discard("A", group);
    }
    ctx.syncTabDots(); assert.equal(node("device-sheet").dataset.dirty, "false");
    assert.ok(entries.every(entry => entry.tab.dot.hidden));
}
{
    const html = fs.readFileSync(require.resolve("../frontend/controller/physical.html"), "utf8");
    const count = id => (html.match(new RegExp('id="' + id + '"', "g")) || []).length;
    const unique = ["stage-well", "stage-svg", "commit-shelf", "commit-bar", "roster", "device-list", "show-image", "btn-apply", "setup-strip", "server-drawer", "device-sheet", "measurement-details", "saved-layouts", "saved-scenes", "return-point", "readiness-message"];
    for (const id of unique) assert.equal(count(id), 1, "one instance of #" + id);
    assert.doesNotMatch(html, /wall-context-|id="tab-(tablet|saved|system)"|compact-task-select/);
    const content = html.slice(html.indexOf('id="panel-content"'), html.indexOf('id="panel-show"'));
    const arrange = html.slice(html.indexOf('id="panel-show"'), html.indexOf('id="panel-test"'));
    const test = html.slice(html.indexOf('id="panel-test"'), html.indexOf('id="panel-tablets"'));
    const tablet = html.slice(html.indexOf('id="device-sheet"'), html.indexOf('</main>'));
    const server = html.slice(html.indexOf('id="server-drawer"'), html.indexOf('</dialog>', html.indexOf('id="server-drawer"')));
    assert.ok(content.includes('id="saved-scenes"'));
    for (const id of ["saved-layouts", "return-point"]) assert.ok(arrange.includes('id="' + id + '"'));
    assert.ok(test.includes('id="presentation-checks"'));
    assert.equal(count("diagnostic-colours"), 1, "Test colour controls are shared with the selected Tablet inspector");
    for (const id of ["tablet-label-form", "open-tablet-measurements"]) assert.ok(tablet.includes('id="' + id + '"'), "Tablet panel retains " + id);
    const measure = html.slice(html.indexOf('<dialog class="measure-dialog" id="measurement-details"'), html.indexOf('</dialog>', html.indexOf('id="measure-title"')));
    for (const id of ["profile-form", "calibration-form", "cal-live-viewport", "tablet-model"]) assert.ok(measure.includes('id="' + id + '"'), "Measure dialog owns " + id);
    for (const step of ["model", "profile", "ruler", "advanced"]) assert.ok(measure.includes('data-measure-step="' + step + '"') && measure.includes('data-step-panel="' + step), "Measure dialog has a " + step + " step and panel");
    for (const id of ["settings-evidence", "settings-diagnostics", "backup-restore", "settings-experimental", "diag-last-known", "operator-readiness-backup", "readiness-status", "btn-readiness-refresh", "btn-diag-refresh", "btn-diag-verify", "clear-wall-confirm"]) {
        assert.ok(server.includes('id="' + id + '"'), "Server drawer owns " + id);
    }
    for (const id of ["tablet-label-form", "profile-form", "calibration-form", "scene-save-form", "layout-save-form", "upload-form"]) {
        assert.equal(count(id), 1); assert.ok(html.includes('data-form="' + id + '"'), "keyed form contract retained");
    }
    assert.match(controller, /"Recall geometry"/);
    assert.match(controller, /"Preview content"/);
    assert.match(controller, /Automatic restore point/);
    assert.match(controller, /not current evidence for the wall/);
    assert.match(controller, /Showing last known saved arrangements/);
    assert.match(controller, /Showing last known saved content/);
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
