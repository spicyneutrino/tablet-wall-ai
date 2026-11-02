"use strict";
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const context = { window: {} };
vm.runInNewContext(fs.readFileSync("frontend/controller/physical-stage.js", "utf8"), context);
const state = { draft: { kind: "logical", placements: { a: { x: 2, y: 3 } } }, selectedId: "a" };
const stage = context.window.PhysicalStage.create({ state, mutateDraft: change => change(state.draft) });
for (const guard of ["viewLive", "previewContent", "gridPreview", "busy"]) {
    state[guard] = true;
    stage.nudgeSelected(1, 1);
    assert.equal(state.draft.placements.a.x, 2, guard + " prevents edits");
    state[guard] = false;
}
stage.nudgeSelected(1, -1);
assert.equal(state.draft.placements.a.x, 3);
assert.equal(state.draft.placements.a.y, 2);
console.log("Stage keyboard nudge respects live and preview modes");
