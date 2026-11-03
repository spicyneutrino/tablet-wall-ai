"use strict";
const assert = require("node:assert/strict");
const grid = require("../frontend/controller/operator-grid.js");
class Node {
    constructor() { this.children = []; this.dataset = {}; this.value = ""; this.listeners = {}; }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.children = nodes; }
    setAttribute() {}
    add(option) { this.append(option); }
    addEventListener(type, callback) { this.listeners[type] = callback; }
    querySelectorAll() { return this.children.flatMap(node => [node, ...(node.children || [])]).filter(node => node.dataset && node.dataset.field); }
    closest() { return this; }
    remove() {}
}
const nodes = new Map();
global.document = { getElementById(id) { if (!nodes.has(id)) nodes.set(id, new Node()); return nodes.get(id); }, createElement: () => new Node(), createTextNode: text => ({ textContent: text }) };
global.Option = function (text, value) { this.textContent = text; this.value = value; };
const state = { base: { kind: "logical", placements: {} }, layoutKind: "logical", roster: { first: { number: 1, online: false } } };
const owner = grid.create({ state, api: async () => {}, labelFor: () => "Tablet 1", validPair: () => null, profileFor: () => null, calibrationFor: () => null,
    ingestConfig() {}, renderStage() {}, syncDraftUi() {}, isDirty: () => false, announce() {}, showConflict() {} });
owner.render();
state.roster.first = { number: 1, online: true, viewport: { width: 900, height: 1280 } };
owner.render();
const item = nodes.get("grid-order").children[0];
assert.equal(item.children[0].children[0].checked, true, "#24 registration before socket readiness must become selected without reload");
assert.equal(Number(item.children[1].children[1].children[0].value), 70, "untouched width uses fresh 900 / 1280 viewport");
state.etag = "original";
nodes.get("grid-kind").listeners.change();
state.etag = "unrelated";
owner.modelSetupComplete("own-returned");
nodes.get("grid-preview").listeners.click().then(async () => {
    assert.match(nodes.get("grid-message").textContent, /Rebuild preview explicitly/, "a refreshed unrelated guard cannot authorize the retained grid after model setup");
    nodes.clear();
    const manualState = { base: { kind: "logical", placements: {} }, layoutKind: "logical", roster: {}, etag: "manual-base" };
    let previewRequests = 0;
    const manualOwner = grid.create({ state: manualState, api: async () => { previewRequests += 1; },
        labelFor: id => id, validPair: () => null, profileFor: () => null, calibrationFor: () => null,
        ingestConfig() {}, renderStage() {}, syncDraftUi() {}, isDirty: () => true, announce() {}, showConflict() {} });
    manualOwner.render();
    await nodes.get("grid-preview").listeners.click();
    assert.match(nodes.get("grid-message").textContent, /manual draft/);
    assert.equal(manualOwner.dirty(), false, "refusing a grid preview cannot create a competing grid draft");
    assert.equal(previewRequests, 0, "refusing the ownership transition does not send a preview request");
    console.log("Actual grid row follows late online viewport and retains its conflict guard");
}).catch(error => { console.error(error); process.exitCode = 1; });
