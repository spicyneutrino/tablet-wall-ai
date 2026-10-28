"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const context = vm.createContext({ window: {} });
function load(name) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../frontend/controller", name), "utf8"), context, { filename: name });
}
function plain(value) { return JSON.parse(JSON.stringify(value)); }
load("controller-geometry.js");
const geometry = context.window.ControllerGeometry;
assert.deepEqual(plain(geometry.normalizePlacement({ x: "2", y: 3, w: 10, h: 20, bezel: { left: "1" } })), {
    x: 2, y: 3, w: 10, h: 20, bezel: { top: 0, right: 0, bottom: 0, left: 1 }
});
assert.equal(geometry.normalizePlacement({ x: "invalid" }), null);
assert.deepEqual(plain(geometry.visibleRect({ x: 2, y: 3, w: 10, h: 20, bezel: { top: 1, right: 2, bottom: 3, left: 4 } })), { x: 6, y: 4, w: 4, h: 16 });
assert.equal(geometry.aspectOf(1, 0), null);
assert.equal(geometry.isAspectMismatch(null), false);
assert.equal(geometry.isAspectMismatch(0.01), false);
assert.equal(geometry.isAspectMismatch(0.011), true);
assert.equal(geometry.sceneContentType({ scene: { content: { type: " future " } } }), "future");
assert.equal(geometry.isSettableContent("image"), false);
assert.equal(geometry.contentLabel("future"), "Unsupported content: future");
assert.equal(geometry.deviceCaps({}).image, null);
assert.equal(geometry.deviceCaps({ caps: [] }).image, false);
console.log("Controller module contracts passed");
load("controller-snapshots.js");
let savedWall = null;
const snapshotMessages = { hidden: true, dataset: {}, textContent: "" };
const snapshots = context.window.ControllerSnapshots.create({
    snapEl: { layout: { msg: snapshotMessages }, scene: {} },
    wallReady: () => !!savedWall, getWall: () => savedWall,
    shortAsset: id => id.slice(0, 8), compareIds: (a, b) => a < b ? -1 : a > b ? 1 : 0
});
assert.equal(snapshots.snapSaveAvailable("layout"), false);
savedWall = { content: { type: "color" } };
assert.equal(snapshots.snapSaveAvailable("scene"), true);
assert.deepEqual(plain(snapshots.validateSnapshotName("  Main wall  ")), { name: "Main wall" });
assert.ok(snapshots.validateSnapshotName("../wall").error);
assert.ok(snapshots.validateSnapshotName("x".repeat(65)).error);
assert.deepEqual(plain(snapshots.normalizeSnapshotList({ layouts: [
    { name: "Zulu", layout: { width: 10, height: 20, placements: {} } },
    { name: "Alpha", invalid: true }, { name: "Zulu" }
] }, "layout")), [
    { name: "Alpha", meta: "INVALID SAVED DATA · delete or replace this snapshot" },
    { name: "Zulu", meta: "10 × 20 u · 0 placements" }
]);
assert.equal(snapshots.normalizeSnapshotList({}, "scene"), null);
snapshots.setSnapMsg("layout", "Reading failed", "err");
assert.equal(snapshotMessages.hidden, false);
assert.equal(snapshotMessages.dataset.kind, "err");
snapshots.setSnapMsg("layout", null);
assert.equal(snapshotMessages.hidden, true);
load("controller-stage.js");
context.setTimeout = () => 1;
context.clearTimeout = () => {};
const editor = { selectedId: "tablet", pendingNudge: null, stageNudgeTimer: null, stageUndo: [], stageRedo: [] };
let currentWall = { width: 100, height: 100, placements: { tablet: { x: 60, y: 10, w: 30, h: 20, bezel: { top: 0, right: 0, bottom: 0, left: 0 } } } };
const stageNodes = {
    inspX: {}, inspY: {}, inspW: {}, inspH: {}, inspShape: {}, inspWarning: {},
    inspStep: { value: "20" }, btnUndoStage: {}, btnRedoStage: {}, statusUndo: {}
};
const stageController = context.window.ControllerStage.create({
    editor, stage: stageNodes, devices: new Map(),
    fmtNumber: String, shortId: String, updateStageReadout: () => {},
    runtime: { get wall() { return currentWall; } }
});
stageController.nudgeSelected(1, 0);
assert.equal(editor.pendingNudge.placement.x, 70, "nudge clamps to the wall edge");
assert.equal(currentWall.placements.tablet.x, 60, "preview must not write server state");
stageController.nudgeSelected(-1, 0);
assert.equal(editor.pendingNudge.placement.x, 50, "successive nudges use the pending preview");
editor.pendingNudge = null;
currentWall = { ...currentWall, placements: { tablet: { ...currentWall.placements.tablet, x: 0 } } };
stageController.nudgeSelected(1, 0);
assert.equal(editor.pendingNudge.placement.x, 20, "replacement wall state is read at call time");
stageController.renderStageHistory();
assert.equal(stageNodes.btnUndoStage.disabled, true);
editor.stageUndo.push({});
stageController.renderStageHistory();
assert.equal(stageNodes.btnUndoStage.disabled, false);
assert.equal(stageNodes.statusUndo.hidden, false);

// Execute each page's classic scripts in markup order before DOMContentLoaded.
// This catches missing dependencies and initialization cycles in the VM path.
for (const page of ["index.html", "physical.html"]) {
    const boot = vm.createContext({ window: {}, document: {
        readyState: "loading", getElementById: () => null,
        querySelector: () => null, querySelectorAll: () => [], addEventListener: () => {}
    } });
    const html = fs.readFileSync(path.join(__dirname, "../frontend/controller", page), "utf8");
    for (const match of html.matchAll(/<script src="([^"?]+)(?:\?[^\"]*)?"><\/script>/g)) {
        vm.runInContext(fs.readFileSync(path.join(__dirname, "../frontend/controller", match[1]), "utf8"), boot, { filename: match[1] });
    }
}
load("physical-playback.js");
const playback = context.window.PhysicalPlayback.create({}).model;
const occurrence = { playlist_revision: 3, item_index: 0, loop: 0 };
const status = {
    state: "playing", now_ms: 11000, current_effective_ms: 10000,
    live: { current: { occurrence, asset: "frozen-video", kind: "video", duration_ms: 2500 } }
};
assert.equal(playback.liveSlotEntry(status, "current").asset, "frozen-video");
assert.equal(playback.remainingDwell(status), 1500);
assert.equal(playback.remainingDwell({ ...status, state: "paused", paused_at_ms: 10500, now_ms: 90000 }), 2000,
    "paused dwell uses the pause instant rather than the current server clock");
assert.equal(playback.remainingDwell({ ...status, state: "paused" }), null,
    "an absent pause instant must not invent a countdown");
assert.equal(playback.remainingDwell({ ...status, pending: {
    occurrence: { ...occurrence, item_index: 1 }, effective_server_ms: 12000
} }), 1000);
assert.equal(playback.liveSlotEntry({ state: "armed", live: { current: status.live.current } }, "displayed"), null);
assert.equal(playback.liveSlotEntry({ state: "playing", current: {
    occurrence, asset_id: "legacy", media: { kind: "video", duration_ms: 3000 }
} }, "current").duration_ms, 3000);
const members = playback.memberState({
    required: ["b", "a"], ready: ["a"], missing: [{ device_id: "b", reason: "offline" }],
    excluded: ["c"], pending: { leases: { a: { ready: true } } }
});
assert.deepEqual([...members.required], ["b", "a"]);
assert.equal(members.missing.get("b"), "offline");
assert.equal(members.excluded.has("c"), true);
assert.equal(members.ready.has("a"), true);
