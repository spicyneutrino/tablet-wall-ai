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
assert.equal(geometry.deviceCaps({ caps: [] }).image, null);
assert.equal(geometry.deviceCaps({ protocol: 1, caps: ["image"] }).image, false);
assert.equal(geometry.deviceCaps({ protocol: 1 }).known, true);
for (const protocol of [2, 3]) {
    assert.equal(geometry.deviceCaps({ protocol, caps: ["image"] }).image, true);
    assert.equal(geometry.deviceCaps({ protocol, caps: [] }).image, false);
    assert.equal(geometry.deviceCaps({ protocol }).known, false);
}
assert.equal(geometry.deviceCaps({ protocol: 4, caps: ["image"] }).known, false);
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
for (const page of ["experimental.html"]) {
    const boot = vm.createContext({ window: {}, document: {
        readyState: "loading", getElementById: () => null,
        querySelector: () => null, querySelectorAll: () => [], addEventListener: () => {}
    } });
    const html = fs.readFileSync(path.join(__dirname, "../frontend/controller", page), "utf8");
    for (const match of html.matchAll(/<script src="([^"?]+)(?:\?[^\"]*)?"><\/script>/g)) {
        vm.runInContext(fs.readFileSync(path.join(__dirname, "../frontend/controller", match[1]), "utf8"), boot, { filename: match[1] });
    }
}
load("controller-inventory.js");
const inventoryState = {
    assets: [{ id: "still", name: "Still", kind: "still" }], mediaAssets: [],
    selectedAsset: "still", assetsLoaded: true, mediaState: "ready"
};
const inventoryRuntime = { wall: { revision: 1 }, pendingContent: null, contentView: null };
let imageRequest = null;
const inventoryController = context.window.ControllerInventory.create({
    inventory: inventoryState, runtime: inventoryRuntime, el: {},
    aspectOf: geometry.aspectOf, compareIds: (a, b) => a < b ? -1 : a > b ? 1 : 0,
    requestJson: async (method, route, body) => { imageRequest = { method, route, body }; return { revision: 2 }; },
    normalizeWall: value => value, renderWall: () => {}, renderWallContent: () => {}, logStatus: () => {}, wallReady: () => true
});
const normalizedAssets = inventoryController.model.normalizeAssets({ assets: [
    { id: "A".repeat(64), name: "Zulu", mime: "image/png", width: "20", height: 10 },
    { id: "sha256:" + "a".repeat(64), name: "Duplicate" },
    { id: "clip", name: "Alpha", mime: "video/mp4", duration_ms: "1234" }
] });
assert.equal(normalizedAssets.length, 2, "bare and prefixed digests are one asset");
assert.equal(normalizedAssets[0].id, "clip");
assert.equal(normalizedAssets[0].durationMs, 1234);
assert.equal(normalizedAssets[1].width, 20);
assert.equal(inventoryController.model.normalizeAssets({}), null);
(async () => {
    await inventoryController.applyImageScene();
    assert.equal(imageRequest.method, "PUT");
    assert.equal(imageRequest.route, "/scene");
    assert.equal(imageRequest.body.content.asset, "still");
    assert.equal(inventoryRuntime.wall.revision, 2);
    assert.equal(inventoryRuntime.contentView, "image");
    assert.equal(inventoryRuntime.pendingContent, null);
})().catch(error => { console.error(error); process.exitCode = 1; });
