"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const nodes = new Map();
const document = { activeElement: null, body: { dataset: {} }, getElementById: node, querySelector: () => node("shared-stage") };
function node(id) {
    if (!nodes.has(id)) nodes.set(id, { dataset: {}, hidden: true, textContent: "", listeners: {}, appends: [],
        addEventListener(event, fn) { this.listeners[event] = fn; },
        append(child) { this.appends.push(child); child.parent = this; },
        contains(child) { return child === this || child === node(id + "-summary"); },
        querySelector() { return node(id + "-summary"); }, focus() { document.activeElement = this; } });
    return nodes.get(id);
}
const state = { tabName: "content", roster: { a: { online: true }, b: { online: false } }, configLoaded: true, base: { placements: { a: {} } } };
let dirty = false;
const context = { window: { OperatorState: require("../frontend/controller/operator-state.js") }, document };
vm.runInNewContext(fs.readFileSync(require.resolve("../frontend/controller/operator-workspace.js"), "utf8"), context);
const workspace = context.window.OperatorWorkspace.create({ state, arrangementDirty: () => false, arrangementPreview: () => false,
    imageDirty: () => dirty, canCommit: () => true });
workspace.render();
assert.equal(node("shared-stage").parent, node("wall-context-content"));
assert.equal(node("connected-summary").textContent, "1 connected");
assert.equal(node("stage-mode-label").textContent, "Applied configuration");
node("edited-field").focus();
workspace.render(); workspace.render();
assert.equal(node("wall-context-content").appends.length, 1, "runtime updates do not detach the stage or SVG focus");
assert.equal(document.activeElement, node("edited-field"));
state.tabName = "tablet"; dirty = true; workspace.render();
assert.equal(node("shared-stage").parent, node("wall-context-tablet"));
assert.equal(node("stage-mode-label").textContent, "Image preview · not shown");
state.rosterError = true; workspace.render();
assert.equal(node("connected-summary").textContent, "Connections stale");
node("add-image").listeners.click();
assert.equal(node("image-addition").open, true);
assert.equal(document.activeElement, node("image-addition-summary"), "disabled upload leads to availability explanation");
node("upload-form").hidden = false; node("add-image").listeners.click();
assert.equal(document.activeElement, node("upload-file"), "admitted upload leads to the native file control");
node("add-tablets").listeners.click();
assert.equal(node("tablet-joining").open, true);
assert.equal(document.activeElement, node("tablet-joining-summary"));
state.roster = {}; workspace.render();
assert.equal(node("tablet-joining").open, true, "empty roster leads with joining help");
node("edited-field").focus(); state.roster = { a: { online: true } }; workspace.render();
assert.equal(node("tablet-joining").open, false, "automatic joining help closes when the roster populates without stealing a field");
console.log("Workspace relocates one stage only on task changes and preserves keyed field focus and admitted entry points");

const controller = fs.readFileSync(require.resolve("../frontend/controller/physical.js"), "utf8");
const taskSource = controller.slice(controller.indexOf("    function commitTask("), controller.indexOf("    function onTabKeyDown("));
const sequence = [];
const taskState = { tabName: "tablet", tabScroll: {} };
const tasks = ["tablet", "content", "show"].map(name => ({ name,
    tab: { setAttribute() {} }, panel: { hidden: true, querySelector() { return null; } } }));
const taskContext = { state: taskState, el: {}, tabEntries: () => tasks,
    workspace: { render() { sequence.push("move:" + taskState.tabName); } },
    renderStage() { sequence.push("draw:" + taskState.tabName); } };
vm.createContext(taskContext); vm.runInContext(taskSource, taskContext);
assert.equal(taskContext.commitTask("content"), true);
assert.deepEqual(sequence, ["move:content", "draw:content"], "task change draws immediately after state and host change");
sequence.length = 0;
taskContext.commitTask("content");
assert.deepEqual(sequence, ["move:content"], "re-entering the active task needs no extra draw");
console.log("Task commit draws the new task immediately after moving the original stage");
