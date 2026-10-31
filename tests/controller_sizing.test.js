"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const context = vm.createContext({ window: {} });
function load(name) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../frontend/controller", name), "utf8"), context, { filename: name });
}
load("controller-geometry.js");
const geometry = context.window.ControllerGeometry;
const plain = value => JSON.parse(JSON.stringify(value));

assert.deepEqual(plain(geometry.normalizeSizing(undefined)), { mode: "fixed", padding: 0 });
assert.deepEqual(plain(geometry.normalizeSizing({ mode: "tablets", padding: "12.6" })), { mode: "tablets", padding: 13 });
assert.deepEqual(plain(geometry.normalizeSizing({ mode: "unknown", padding: -3 })), { mode: "fixed", padding: 0 });

load("controller-stage.js");
context.setTimeout = () => 1;
context.clearTimeout = () => {};
const editor = { selectedId: "tablet", pendingNudge: null, stageNudgeTimer: null, stageUndo: [{}], stageRedo: [{}] };
const nodes = {
    inspX: {}, inspY: {}, inspW: {}, inspH: {}, inspShape: {}, inspWarning: {}, inspStep: { value: "20" },
    btnUndoStage: {}, btnRedoStage: {}, statusUndo: {}, tileSection: {}, btnTile: {}
};
let wall = {
    width: 100, height: 100, sizing: { mode: "tablets", padding: 0 },
    placements: { tablet: { x: 60, y: 10, w: 30, h: 20, bezel: { top: 0, right: 0, bottom: 0, left: 0 } } }
};
const stage = context.window.ControllerStage.create({
    editor, stage: nodes, devices: new Map(), fmtNumber: String, shortId: String, updateStageReadout: () => {},
    runtime: { get wall() { return wall; } }
});

stage.nudgeSelected(1, 0);
stage.nudgeSelected(1, 0);
assert.equal(editor.pendingNudge.placement.x, 100, "fit mode lets movement expand the derived wall");
assert.equal(wall.placements.tablet.x, 60, "nudge remains a local preview until saved");
stage.renderStageHistory();
assert.equal(nodes.btnUndoStage.disabled, true, "placement undo is disabled in fit mode");
assert.equal(nodes.btnRedoStage.disabled, true, "placement redo is disabled in fit mode");
assert.equal(nodes.tileSection.hidden, true, "sequential tiling is hidden in fit mode");

wall = { ...wall, sizing: { mode: "fixed", padding: 0 } };
editor.pendingNudge = null;
stage.nudgeSelected(1, 0);
stage.nudgeSelected(1, 0);
assert.equal(editor.pendingNudge.placement.x, 70, "fixed mode keeps the existing wall edge clamp");
stage.renderStageHistory();
assert.equal(nodes.tileSection.hidden, false, "sequential tiling remains available for fixed walls");

console.log("Controller wall sizing contracts passed");
