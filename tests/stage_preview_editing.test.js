"use strict";
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const context = { window: { OperatorState: require("../frontend/controller/operator-state.js") } };
vm.runInNewContext(fs.readFileSync("frontend/controller/physical-stage.js", "utf8"), context);
const state = { get composition() { return { mode: this.mode }; }, draft: { kind: "logical", placements: { a: { x: 2, y: 3 } } }, selectedId: "a", mode: "arrange" };
const stage = context.window.PhysicalStage.create({ state, mutateDraft: change => change(state.draft) });
for (const guard of ["viewLive", "previewContent", "gridPreview", "busy"]) {
    state[guard] = true;
    stage.nudgeSelected(1, 1);
    assert.equal(state.draft.placements.a.x, 2, guard + " prevents edits");
    state[guard] = false;
}
for (const tab of ["content", "test"]) {
    state.mode = tab;
    stage.nudgeSelected(1, 1);
    assert.equal(state.draft.placements.a.x, 2, tab + " keeps geometry unchanged");
    assert.equal(state.draft.placements.a.y, 3, tab + " keeps geometry unchanged");
}
state.mode = "arrange";
stage.nudgeSelected(1, -1);
assert.equal(state.draft.placements.a.x, 3);
assert.equal(state.draft.placements.a.y, 2);
console.log("Stage keyboard nudge respects live and preview modes");
