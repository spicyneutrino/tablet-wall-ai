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
for (const page of ["index.html", "physical.html", "experimental.html"]) {
    const geometryControls = new Set(["btn-match-shape", "view-zoom-fit", "view-zoom-2x", "logical-snap-enabled"]);
    const boot = vm.createContext({ window: {}, document: {
        readyState: "loading", getElementById: id => geometryControls.has(id) ? { addEventListener() {} } : null,
        querySelector: () => null, querySelectorAll: () => [], addEventListener: () => {}
    } });
    const html = fs.readFileSync(path.join(__dirname, "../frontend/controller", page), "utf8");
    if (page === "physical.html") for (const id of geometryControls) {
        assert.ok(html.includes('id="' + id + '"'), "boot fixture geometry control exists in the real page: " + id);
    }
    if (page === "physical.html") {
        assert.match(html, /<body class="physical" data-view-zoom="fit">/,
            "the initial view zoom state is the truthful Fit default");
        const shape = html.slice(html.indexOf('id="arrange-shape"'), html.indexOf('id="arrange-custom"'));
        assert.ok(shape.includes('id="grid-rows"') && shape.includes('id="grid-columns"'),
            "custom grid rows and columns sit in the wall-shape group, not behind the order disclosure");
        assert.ok(shape.indexOf('id="grid-rows"') < shape.indexOf('id="grid-2x2"'),
            "custom rows and columns are adjacent to the presets they feed");
        assert.ok(shape.includes('id="arrange-grid-heading"') && shape.includes('id="arrange-bounds-heading"'),
            "the wall-shape group labels grid controls apart from bounds controls");
        assert.match(html, /<details id="arrange-custom"[^>]*\bopen\b/,
            "selected geometry and relative arrangement controls are expanded instead of behind a collapsed disclosure");
        assert.ok(html.includes('id="arrange-model"') && html.includes('id="arrange-membership"'),
            "order and mounting and model and measurements have separate groups");
    }
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
load("physical-stage.js");
const physicalEditor = {
    busy: false, tabName: "show", selectedId: "tablet", draft: { slots: { tablet: {
        center_x_mm: 10, center_y_mm: 20, nudge_x_mm: 0, nudge_y_mm: 0, mount_angle: 270
    } } }
};
const physicalHistory = [];
const physicalStage = context.window.PhysicalStage.create({
    canManualEdit: () => true, beginManual: () => {},
    mutateDraft: change => { physicalHistory.push(plain(physicalEditor.draft)); change(physicalEditor.draft); return true; },
    state: physicalEditor, selectedSlot: () => physicalEditor.draft.slots.tablet,
    clone: plain, finiteOr: (value, fallback) => Number.isFinite(Number(value)) ? Number(value) : fallback,
    roundTo: (value, digits) => Math.round(value * 10 ** digits) / 10 ** digits,
    formatNumber: String, pushUndo: before => physicalHistory.push(before),
    afterDraftChange: () => {}, announce: () => {},
    el: { stageSvg: { classList: { remove: () => {} }, hasPointerCapture: () => false } }
});
physicalStage.nudgeSelected(0.1, -0.2);
assert.equal(physicalEditor.draft.slots.tablet.nudge_x_mm, 0.1);
assert.equal(physicalHistory[0].slots.tablet.nudge_x_mm, 0, "history holds the draft before the nudge");
physicalStage.rotateSelected();
assert.equal(physicalEditor.draft.slots.tablet.mount_angle, 0);
const preDrag = plain(physicalEditor.draft);
physicalEditor.draft.slots.tablet.center_x_mm = 99;
physicalEditor.drag = { id: "tablet", pointerId: 3, moved: true, preDraft: preDrag };
physicalStage.onPointerCancel({ pointerId: 2 });
assert.equal(physicalEditor.draft.slots.tablet.center_x_mm, 99, "a different pointer cannot cancel a drag");
physicalStage.onPointerCancel({ pointerId: 3 });
assert.equal(physicalEditor.draft.slots.tablet.center_x_mm, 10);
assert.equal(physicalHistory.length, 2, "a cancelled drag adds no history entry");
const healthState = {
    roster: { a: { wake_lock: "unsupported" }, b: {} }, rosterCheckedAt: "2026-10-28T12:00:00Z",
    rosterError: null, base: { slots: { a: {} } }, basePlacements: {}
};
const healthNodes = { deviceCount: {}, wallHealth: {}, btnWallHealth: { dataset: {} }, rosterStatus: { dataset: {} } };
const health = context.window.PhysicalStage.create({
    state: healthState, el: healthNodes, deviceRows: new Map([["a", {}], ["b", {}]]),
    isOnline: id => id === "a", validPair: id => id === "a" ? {} : null
});
health.renderDeviceHealth();
assert.equal(healthNodes.wallHealth.textContent, "1 online · 1 offline · 1 needs calibration · 1 unplaced");
assert.equal(healthNodes.btnWallHealth.dataset.kind, "warn");
assert.ok(!healthNodes.wallHealth.textContent.includes("wake-lock"), "unsupported wake lock is normal on HTTP");
healthState.roster.a.wake_lock = "denied";
health.renderDeviceHealth();
assert.ok(healthNodes.wallHealth.textContent.includes("1 wake-lock warning"));
healthState.rosterError = "503 unavailable";
health.renderDeviceHealth();
assert.equal(healthNodes.deviceCount.textContent, "1 of 2 last known online");
assert.ok(healthNodes.wallHealth.textContent.startsWith("Last known:"));
assert.ok(healthNodes.rosterStatus.textContent.includes("Showing last known status"));
healthState.rosterCheckedAt = null;
health.renderDeviceHealth();
assert.equal(healthNodes.deviceCount.textContent, "Status unknown");
assert.equal(healthNodes.wallHealth.textContent, "Tablet status unavailable");

for (const kind of ["logical", "physical"]) {
    for (const compact of [false, true]) {
        for (const reveal of [false, true]) {
            const selected = { selectedId: "Beta", busy: false, draft: { kind, placements: {}, slots: {} }, basePlacements: {}, roster: {} };
            const selectionNodes = { inspectorEmpty: {}, inspectorBody: { hidden: true }, inspectorMissing: {}, btnAddSlot: {}, slotMissingText: {}, deviceCount: {}, wallHealth: {}, btnWallHealth: { dataset: {} }, rosterStatus: { dataset: {} } };
            const notified = [];
            const selectionStage = context.window.PhysicalStage.create({ state: selected, el: selectionNodes, deviceRows: new Map(),
                latestProfile: () => null, deviceLabel: id => id, selectedSlot: () => null, validPair: () => null,
                compactView: () => compact, showTab: () => {}, selectionChanged: () => notified.push(selected.selectedId) });
            selectionStage.selectDevice("Beta", { reveal });
            assert.deepEqual(notified, ["Beta"], "selection actions refresh independently of inspector kind, viewport and reveal");
        }
    }
}
