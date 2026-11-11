"use strict";
const assert = require("node:assert/strict");
const grid = require("../frontend/controller/operator-grid.js");
class Node {
    constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.value = ""; this.listeners = {}; }
    get value() { return this.inputValue; }
    set value(value) { this.inputValue = String(value); }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.children = nodes; }
    setAttribute(name, value) { this[name] = value; }
    add(option) { this.append(option); }
    addEventListener(type, callback) { this.listeners[type] = callback; }
    querySelectorAll(tag) { const all = node => (node.children || []).flatMap(child => [child, ...all(child)]); return all(this).filter(node => node.tag === tag); }
    closest() { return this; }
    remove() {}
    focus() { global.document.activeElement = this; }
}
const nodes = new Map();
global.document = { getElementById(id) { if (!nodes.has(id)) nodes.set(id, new Node("div")); return nodes.get(id); },
    createElement: tag => new Node(tag), createTextNode: text => ({ textContent: text }) };
global.Option = function (text, value) { this.textContent = text; this.value = value; };
const state = { base: { kind: "logical", placements: { a: { x: 0, y: 0, w: 100, h: 100 } } }, layoutKind: "logical", etag: "one",
    etagState: "current", roster: { a: { online: true }, b: { online: false } } };
let previewResult;
const requests = [];
const owner = grid.create({ state, api: async (method, path, body) => { requests.push({ method, path, body }); if (previewResult) return previewResult; throw new Error("preview must not be sent"); }, labelFor: id => id, validPair: () => null,
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
nodes.get("grid-preview").listeners.click().then(async () => {
    assert.match(nodes.get("grid-message").textContent, /^Cannot preview arrangement\./, "the acknowledgement satisfies the release guard");
    const twoByTwo = nodes.get("grid-2x2");
    assert.deepEqual([twoByTwo.textContent, twoByTwo["aria-label"]], ["1 × 1", "1 × 1 grid"], "the preset names the grid it will build for one tablet");
    assert.equal(nodes.get("grid-1x4").hidden, true, "equivalent one-tablet presets collapse");
    twoByTwo.listeners.click();
    assert.equal(twoByTwo["aria-pressed"], "true");
    assert.equal(nodes.get("grid-message").textContent, "");
    nodes.get("grid-columns").listeners.change();
    assert.equal(twoByTwo["aria-pressed"], "false", "custom dimensions clear preset selection");
    assert.deepEqual([nodes.get("grid-rows").value, nodes.get("grid-columns").value], ["1", "1"]);
    previewResult = { layout: { kind: "logical", width: 100, height: 100, placements: { a: { x: 0, y: 0, w: 100, h: 100 } } },
        guards: {}, base_etag: "three", order: ["a"], previous_kind: "physical",
        warnings: ["mixed footprint", "mixed footprint.", "uneven edge", "estimated measurement a"] };
    nodes.get("grid-gap").value = nodes.get("grid-padding").value = "0";
    nodes.get("grid-sizing").value = "tablets"; nodes.get("grid-orientation").value = "preserve";
    twoByTwo.listeners.click();
    nodes.get("grid-rows").value = nodes.get("grid-columns").value = "1";
    await nodes.get("grid-preview").listeners.click();
    const message = nodes.get("grid-message"), review = message.children.find(child => child.className === "grid-warnings");
    assert.equal(message.textContent, "1 tablet · 1 × 1 · 100 × 100 logical units");
    assert.equal(review.textContent, "Mixed footprint. Uneven edge. Apply will request a named safety copy of the current arrangement.");
    assert.equal(review.children[1].children[0].textContent, "Estimated measurement a.");
    state.base = { kind: "logical", placements: Object.fromEntries(["a", "b", "c", "d"].map((id, i) => [id, { x: i * 100, y: 0, w: 100, h: 100 }])) };
    state.roster = Object.fromEntries(["a", "b", "c", "d"].map(id => [id, { online: true }]));
    owner.reset();
    const oneRow = nodes.get("grid-1x4");
    const include = (id, checked) => {
        const row = nodes.get("grid-order").children.find(item => item.dataset.deviceId === id);
        const check = row.children[0].children[0];
        check.checked = checked; check.listeners.change();
    };
    oneRow.listeners.click();
    include("d", false);
    assert.equal(oneRow.textContent, "1 × 3");
    assert.equal(oneRow["aria-pressed"], "true");
    assert.deepEqual([nodes.get("grid-rows").value, nodes.get("grid-columns").value, nodes.get("grid-holes").checked], ["1", "3", false], "the selected preset and submitted dimensions agree after removing a tablet");
    requests.length = 0;
    await nodes.get("grid-preview").listeners.click();
    assert.equal(requests.length, 0, "preset synchronization preserves explicit release acknowledgement");
    assert.match(nodes.get("grid-message").textContent, /^Explicitly acknowledge/);
    releases().find(input => input.dataset.release === "d").checked = true;
    previewResult = { layout: { kind: "logical", width: 300, height: 100, placements: Object.fromEntries(["a", "b", "c"].map(id => [id, state.base.placements[id]])) },
        guards: {}, base_etag: state.etag, order: ["a", "b", "c"], previous_kind: "logical", warnings: [] };
    await nodes.get("grid-preview").listeners.click();
    assert.equal(requests.length, 1);
    assert.deepEqual([requests[0].body.device_ids, requests[0].body.rows, requests[0].body.columns, requests[0].body.allow_empty_cells, requests[0].body.release_unselected], [["a", "b", "c"], 1, 3, false, ["d"]]);
    include("d", true);
    assert.deepEqual([oneRow.textContent, nodes.get("grid-columns").value, nodes.get("grid-holes").checked], ["1 × 4", "4", false]);
    twoByTwo.listeners.click();
    include("d", false);
    assert.deepEqual([twoByTwo.textContent, nodes.get("grid-rows").value, nodes.get("grid-columns").value, nodes.get("grid-holes").checked], ["2 × 2", "2", "2", true], "a two-row preset updates its empty-cell policy when membership changes");
    oneRow.listeners.click();
    include("c", false); include("b", false);
    assert.equal(oneRow.hidden, true);
    assert.equal(twoByTwo["aria-pressed"], "true", "the visible equivalent preset carries the selected state for one tablet");
    assert.deepEqual([nodes.get("grid-rows").value, nodes.get("grid-columns").value, nodes.get("grid-holes").checked], ["1", "1", false]);
    nodes.get("grid-columns").value = "5";
    nodes.get("grid-columns").listeners.change();
    include("b", true);
    assert.equal(nodes.get("grid-columns").value, "5", "membership changes preserve custom dimensions after leaving the preset");
    assert.equal(twoByTwo["aria-pressed"], "false");
    assert.equal(oneRow["aria-pressed"], "false");
    for (const [id, typed] of [["grid-rows", "3"], ["grid-columns", "12"]]) {
        owner.reset();
        oneRow.listeners.click();
        const input = nodes.get(id), sent = requests.length;
        document.activeElement = input;
        input.value = typed;
        input.listeners.input?.({ target: input });
        owner.render();
        assert.equal(input.value, typed, "a live render preserves a focused " + id + " edit before blur");
        assert.equal(oneRow["aria-pressed"], "false", "typing custom dimensions leaves the preset immediately");
        assert.equal(twoByTwo["aria-pressed"], "false");
        assert.equal(document.activeElement, input, "runtime rendering preserves the active field");
        assert.equal(requests.length, sent, "typing and rendering do not preview or apply geometry");
        input.listeners.change();
        owner.render();
        assert.equal(input.value, typed, "committing the field does not restore the previous preset");
    }
    console.log("Grid release acknowledgements and preset labels follow authority updates");
    const makeDocument = () => {
        const map = new Map();
        return { map, activeElement: null,
            getElementById(id) { if (!map.has(id)) map.set(id, new Node("div")); return map.get(id); },
            createElement: tag => new Node(tag), createTextNode: text => ({ textContent: text }) };
    };
    let dirty = { value: false }, discarded = { calls: 0 }, measured = [], allowDiscard = false;
    const setup = { doc: makeDocument(), requests: [] };
    global.document = setup.doc;
    const openState = { base: { kind: "physical", slots: {} }, layoutKind: "physical", etag: "one", etagState: "current", busy: false,
        roster: { a: { online: true }, b: { online: true } } };
    const openOwner = grid.create({ state: openState, api: async (...args) => { setup.requests.push(args); throw new Error("blocked previews send no request"); },
        labelFor: id => id, validPair: () => null, profileFor: () => null, calibrationFor: () => null,
        ingestConfig() {}, renderStage() {}, syncDraftUi() {}, isDirty: () => dirty.value, announce() {}, showConflict() {},
        discardDraft: () => { discarded.calls += 1; if (allowDiscard) dirty.value = false; openOwner.render(); },
        openMeasurements: id => measured.push(id) });
    openOwner.render();
    const node = id => setup.doc.getElementById(id);
    assert.equal(node("grid-lock-note").hidden, true, "the place lock note is hidden while no placement draft is open");
    dirty.value = true;
    openOwner.render();
    assert.equal(node("grid-lock-note").hidden, false, "a manual placement draft shows the place lock note");
    assert.equal(node("grid-2x2").disabled, true, "the draft still disables the grid presets");
    assert.equal(node("grid-lock-note").children[0].textContent,
        "Wall shapes are paused while your placement draft is open. Apply it, or discard it to use a wall shape.");
    assert.equal(node("grid-lock-note").children[1].textContent, "Discard");
    assert.equal(node("grid-lock-note").children[1].className, "btn btn-sm");
    const lockDiscard = node("grid-lock-note").children[1];
    lockDiscard.focus(); lockDiscard.listeners.click();
    assert.equal(node("grid-lock-note").hidden, false, "a retained draft keeps the note and its focus owner");
    assert.equal(setup.doc.activeElement, lockDiscard, "a refused discard does not focus a disabled preset");
    allowDiscard = true;
    lockDiscard.listeners.click();
    assert.equal(discarded.calls, 2, "the note's Discard runs the existing arrangement discard");
    assert.equal(node("grid-lock-note").hidden, true, "discarding the draft hides the place lock note");
    assert.equal(node("grid-2x2").disabled, false, "discarding the draft re-enables the grid presets");
    assert.equal(setup.doc.activeElement, node("grid-2x2"), "discarding the lock restores focus to the enabled preset");
    assert.equal(setup.requests.length, 0, "Discard sends no geometry request");

    dirty.value = false;
    node("grid-rows").value = "1"; node("grid-columns").value = "2";
    node("grid-gap").value = "0"; node("grid-padding").value = "0";
    node("grid-sizing").value = "tablets"; node("grid-orientation").value = "preserve";
    openOwner.render();
    assert.equal(node("arrange-membership-summary").textContent, "Order and mounting (2 tablets)");
    const row = id => node("grid-order").children.find(item => item.dataset.deviceId === id);
    await node("grid-preview").listeners.click();
    assert.equal(setup.requests.length, 0, "missing mount angles send no preview request");
    let blockers = node("grid-blockers");
    assert.equal(blockers.hidden, false, "a blocked measured preview lists its blockers");
    assert.deepEqual(blockers.children.map(button => button.textContent), ["a: declare mounted top edge", "b: declare mounted top edge"]);
    assert.deepEqual(blockers.children.map(button => button.className), ["btn btn-sm", "btn btn-sm"]);
    assert.ok(blockers.children.every(button => button.type === "button"));
    blockers.children[0].listeners.click();
    assert.equal(node("arrange-membership").open, true, "the angle blocker opens Order and mounting");
    assert.equal(setup.doc.activeElement, row("a").querySelectorAll("select")[0], "the angle blocker focuses that tablet's angle control");
    for (const id of ["a", "b"]) {
        const angle = row(id).querySelectorAll("select")[0];
        angle.value = "0"; angle.listeners.change();
    }
    await node("grid-preview").listeners.click();
    assert.equal(setup.requests.length, 0, "missing pinned measurements send no preview request");
    assert.match(node("grid-message").textContent, /Cannot preview arrangement\. Confirm a model or save measurements/);
    blockers = node("grid-blockers");
    assert.deepEqual(blockers.children.map(button => button.textContent), ["a: open measurements", "b: open measurements"]);
    blockers.children[1].listeners.click();
    assert.deepEqual(measured, ["b"], "the measurements blocker calls the measurements action for its tablet");
    console.log("Place lock note and measured blocker links passed");
}).catch(error => { console.error(error); process.exitCode = 1; });
