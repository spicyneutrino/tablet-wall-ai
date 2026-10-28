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
