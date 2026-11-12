"use strict";
const assert = require("node:assert/strict");
const test = require("node:test");
const composition = require("../frontend/controller/operator-composition.js");
const model = require("../frontend/controller/operator-state.js");

test("composition separates mode, tablet, inspector and draft ownership", () => {
    const initial = composition.createState();
    assert.equal(initial.selectedTablet, null);
    assert.deepEqual(composition.select(initial).inspectorSubject, { kind: "tools", mode: "content" });
    const selected = composition.reduce(initial, { type: "select-tablet", id: "a" });
    assert.equal(selected.mode, initial.mode);
    assert.equal(selected.legacyPanel, initial.legacyPanel);
    assert.deepEqual(composition.select(selected).inspectorSubject, { kind: "tablet", id: "a" });
    let next = composition.reduce(selected, { type: "open-panel", panel: "show" });
    assert.equal(next.mode, "arrange");
    for (const panel of ["tablet", "saved", "system"]) {
        next = composition.reduce(next, { type: "open-panel", panel });
        assert.equal(next.mode, "arrange");
        assert.equal(next.selectedTablet, "a");
        assert.equal(next.legacyPanel, panel);
    }
    next = composition.reduce(next, { type: "set-mode", mode: "test" });
    assert.equal(next.selectedTablet, "a");
    assert.equal(next.legacyPanel, null);
    next = composition.reduce(next, { type: "select-tablet", id: null });
    assert.deepEqual(composition.select(next).inspectorSubject, { kind: "tools", mode: "test" });
    assert.equal(composition.select(next, { image: true }).draftOwner, "image");
    assert.equal(composition.select(next, { arrangement: true }).draftOwner, "arrangement");
    assert.equal(composition.select(next).draftOwner, "none");
    assert.ok(Object.isFrozen(composition.select(next)));
    assert.deepEqual(initial, composition.createState(), "transitions do not mutate earlier state");
});

test("stage ownership keeps current live, image, grid and manual rules", () => {
    for (const panel of ["content", "show", "tablet", "saved", "system"]) {
        for (const gridPreview of [null, { layout: {} }]) {
            for (const viewLive of [false, true]) {
                for (const previewContent of [null, { type: "image" }]) {
                    const state = { tabName: panel, gridPreview, viewLive, previewContent };
                    const expected = panel === "show" && !gridPreview && !viewLive && !previewContent;
                    assert.equal(model.stageView(state).editable, expected);
                    state.composition = composition.select(composition.legacyState(panel, "a"));
                    assert.equal(model.stageView(state).editable, expected);
                }
            }
        }
    }
    const shell = composition.reduce(composition.createState(), { type: "set-mode", mode: "arrange" });
    assert.equal(composition.stageEditable(shell, {}), true, "future shell editing needs no tab name");
});

test("selection navigation keeps legacy reveal policy and rejects a stale reveal", async () => {
    let state = composition.legacyState("content", "a"), release;
    const calls = [];
    const navigate = composition.createSelectionNavigation({
        composition: () => state,
        selectedId: () => state.selectedTablet,
        openPanel: panel => { calls.push(panel); return new Promise(resolve => { release = resolve; }); },
        revealTablet: id => { calls.push("reveal " + id); return true; },
        expandArrange: () => calls.push("expand")
    });
    assert.equal(await navigate("a"), false);
    assert.deepEqual(calls, [], "selection alone never opens a panel or sheet");
    const pending = navigate("a", { reveal: true });
    state = composition.reduce(state, { type: "select-tablet", id: "b" });
    state = composition.reduce(state, { type: "open-panel", panel: "tablet" });
    release(true);
    assert.equal(await pending, false);
    assert.deepEqual(calls, ["tablet"]);
    assert.equal(await navigate("b", { reveal: true, taskOpened: true }), true);
    assert.deepEqual(calls, ["tablet", "reveal b"]);
    state = composition.reduce(state, { type: "open-panel", panel: "show" });
    assert.equal(await navigate("b", { reveal: true, stageActivation: true }), false);
    assert.equal(calls.at(-1), "expand", "an Arrange stage tap keeps the geometry tools");
});
