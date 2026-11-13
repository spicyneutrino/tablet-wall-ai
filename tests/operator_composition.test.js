"use strict";
const assert = require("node:assert/strict");
const test = require("node:test");
const composition = require("../frontend/controller/operator-composition.js");
const model = require("../frontend/controller/operator-state.js");

test("mode and tablet selection have separate ownership", () => {
    const initial = composition.createState();
    assert.deepEqual(initial, { mode: "content", selectedTablet: null });
    assert.deepEqual(composition.select(initial).inspectorSubject, { kind: "tools", mode: "content" });
    let next = composition.reduce(initial, { type: "select-tablet", id: "a" });
    for (const mode of composition.MODES) {
        next = composition.reduce(next, { type: "set-mode", mode });
        assert.equal(next.mode, mode);
        assert.equal(next.selectedTablet, "a", "selection survives every mode switch");
        assert.deepEqual(composition.select(next).inspectorSubject, { kind: "tablet", id: "a" });
    }
    assert.equal(composition.reduce(next, { type: "set-mode", mode: "saved" }), next, "removed tasks are not modes");
    next = composition.reduce(next, { type: "select-tablet", id: null });
    assert.deepEqual(composition.select(next).inspectorSubject, { kind: "tools", mode: "test" });
    assert.equal(composition.select(next, { image: true }).draftOwner, "image");
    assert.equal(composition.select(next, { arrangement: true }).draftOwner, "arrangement");
    assert.equal(composition.select(next).draftOwner, "none");
    assert.ok(Object.isFrozen(composition.select(next)));
    assert.deepEqual(initial, composition.createState(), "transitions never mutate earlier state");
});

test("only Arrange without live, image or grid preview owns geometry", () => {
    for (const mode of composition.MODES) for (const gridPreview of [null, { layout: {} }]) {
        for (const viewLive of [false, true]) for (const previewContent of [null, { type: "image" }]) {
            const state = { mode, composition: { mode }, gridPreview, viewLive, previewContent };
            assert.equal(model.stageView(state).editable, mode === "arrange" && !gridPreview && !viewLive && !previewContent);
        }
    }
});

test("selection reveals the persistent panel without navigating; obsolete subjects cannot steal focus", async () => {
    let state = composition.reduce(composition.createState(), { type: "select-tablet", id: "a" });
    const calls = [];
    const navigate = composition.createSelectionNavigation({
        composition: () => state, selectedId: () => state.selectedTablet,
        revealTablet: (id, trigger) => { calls.push([id, trigger]); return true; },
        expandArrange: () => calls.push("expand")
    });
    assert.equal(await navigate("a"), false, "passive selection never takes focus");
    assert.deepEqual(calls, []);
    const trigger = {};
    assert.equal(await navigate("a", { reveal: true, trigger }), true);
    assert.deepEqual(calls, [["a", trigger]]);
    state = composition.reduce(state, { type: "select-tablet", id: "b" });
    assert.equal(await navigate("a", { reveal: true }), false, "a stale request never focuses the old subject");
    state = composition.reduce(state, { type: "set-mode", mode: "arrange" });
    assert.equal(await navigate("b", { reveal: true, stageActivation: true }), false, "stage editing keeps keyboard focus on the wall");
    assert.equal(calls.at(-1), "expand");
    assert.equal(state.selectedTablet, "b");
    assert.equal(await navigate("b", { reveal: true }), true, "explicit roster activation reveals the selected panel");
});
