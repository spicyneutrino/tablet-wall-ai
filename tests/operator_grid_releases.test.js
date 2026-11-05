"use strict";
const assert = require("node:assert/strict");
const grid = require("../frontend/controller/operator-grid.js");
class Node {
    constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.value = ""; this.listeners = {}; }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.children = nodes; }
    setAttribute(name, value) { this[name] = value; }
    add(option) { this.append(option); }
    addEventListener(type, callback) { this.listeners[type] = callback; }
    querySelectorAll(tag) { const all = node => (node.children || []).flatMap(child => [child, ...all(child)]); return all(this).filter(node => node.tag === tag); }
    closest() { return this; }
    remove() {}
}
const nodes = new Map();
global.document = { getElementById(id) { if (!nodes.has(id)) nodes.set(id, new Node("div")); return nodes.get(id); },
    createElement: tag => new Node(tag), createTextNode: text => ({ textContent: text }) };
global.Option = function (text, value) { this.textContent = text; this.value = value; };
const state = { base: { kind: "logical", placements: { a: { x: 0, y: 0, w: 100, h: 100 } } }, layoutKind: "logical", etag: "one",
    etagState: "current", roster: { a: { online: true }, b: { online: false } } };
const owner = grid.create({ state, api: async () => { throw new Error("preview must not be sent"); }, labelFor: id => id, validPair: () => null,
    profileFor: () => null, calibrationFor: () => null, ingestConfig() {}, renderStage() {}, syncDraftUi() {}, isDirty: () => false, announce() {}, showConflict() {} });
owner.render();
assert.deepEqual(owner.selectedIds(), ["a"]);
assert.equal(nodes.get("grid-releases").children.length, 0);
state.base = { kind: "logical", placements: { a: { x: 0, y: 0, w: 100, h: 100 }, b: { x: 100, y: 0, w: 100, h: 100 } } }; state.etag = "two";
owner.render();
const releases = () => nodes.get("grid-releases").querySelectorAll("input");
assert.deepEqual(releases().map(input => input.dataset.release), ["b"], "another operator's placement for a known unselected tablet needs an acknowledgement control");
releases()[0].checked = true;
state.etag = "three";
owner.render();
assert.equal(releases()[0].checked, true, "a later authority render keeps the acknowledgement");
nodes.get("grid-preview").listeners.click().then(() => {
    assert.match(nodes.get("grid-message").textContent, /^Cannot preview arrangement\./, "the acknowledgement satisfies the release guard");
    const twoByTwo = nodes.get("grid-2x2");
    assert.deepEqual([twoByTwo.textContent, twoByTwo["aria-label"]], ["1 × 1", "1 × 1 grid"], "the preset names the grid it will build for one tablet");
    assert.equal(nodes.get("grid-1x4").hidden, true, "equivalent one-tablet presets collapse");
    twoByTwo.listeners.click();
    assert.equal(twoByTwo["aria-pressed"], "true");
    assert.equal(nodes.get("grid-message").textContent, "");
    nodes.get("grid-columns").listeners.change();
    assert.equal(twoByTwo["aria-pressed"], "false", "custom dimensions clear preset selection");
    assert.deepEqual([nodes.get("grid-rows").value, nodes.get("grid-columns").value], [1, 1]);
    console.log("Grid release acknowledgements and preset labels follow authority updates");
}).catch(error => { console.error(error); process.exitCode = 1; });
