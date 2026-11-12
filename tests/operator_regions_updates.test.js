"use strict";
const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const vm = require("node:vm");
const dom = require("../frontend/controller/operator-dom.js");

test("injected region references survive relocation and admit late parsed controls", () => {
    const nodes = new Map(), control = { id: "form" };
    let reads = 0;
    const root = { querySelector: selector => { reads += 1; return nodes.get(selector) || null; } };
    const lookup = dom.capture(root);
    assert.equal(lookup("form"), null);
    nodes.set("#form", control);
    assert.equal(lookup("form"), control);
    nodes.delete("#form");
    assert.equal(lookup("form"), control, "a moved form keeps the same reference");
    assert.equal(reads, 2, "rendering does not repeat region lookups for retained controls");
});

test("draft views cannot mutate a feature's nested record", () => {
    const draft = { layout: { placements: { a: { x: 10 } } }, ids: ["a"] };
    const view = dom.readonly(draft);
    assert.throws(() => { view.layout.placements.a.x = 20; }, TypeError);
    assert.throws(() => { view.ids.push("b"); }, TypeError);
    assert.equal(draft.layout.placements.a.x, 10);
    draft.layout.placements.a.x = 30;
    assert.equal(view.layout.placements.a.x, 10, "views are snapshots, never another draft store");
});

test("renderAll observes content and grid before any presentation", () => {
    const calls = [], noop = () => {};
    const feature = name => ({ update: () => calls.push("update " + name), render: () => calls.push("render " + name) });
    const context = { state: {}, operatorContent: feature("content"), operatorGrid: feature("grid"),
        syncMeta: () => calls.push("meta"), syncDraftUi: noop, renderDeviceList: noop, renderStage: noop,
        populateDeviceCard: noop, renderPlayback: noop, operatorDevices: null, operatorReadiness: null,
        workspace: null, renderLogicalEditor: noop, document: { getElementById: () => null } };
    const source = fs.readFileSync(require.resolve("../frontend/controller/physical.js"), "utf8");
    vm.runInNewContext(source.slice(source.indexOf("    function renderAll()"), source.indexOf("    function syncMeta()")), context);
    context.renderAll();
    assert.deepEqual(calls, ["update content", "update grid", "meta", "render content", "render grid"]);
});
