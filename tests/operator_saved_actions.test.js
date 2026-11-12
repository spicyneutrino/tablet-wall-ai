"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync(require.resolve("../frontend/controller/physical.js"), "utf8");
function extract(start, end) {
    const offset = source.indexOf(start);
    assert.ok(offset >= 0 && source.indexOf(end, offset) > offset);
    return source.slice(offset, source.indexOf(end, offset));
}

function setup() {
    const nodes = new Map();
    const document = { activeElement: null, body: {}, getElementById: node, createElement: () => node() };
    function node(id) {
        if (id && nodes.has(id)) return nodes.get(id);
        const item = { dataset: {}, children: [], attrs: {}, listeners: {}, disabled: false,
            classList: { add() {} },
            setAttribute(name, value) { this.attrs[name] = value; },
            addEventListener(name, handler) { this.listeners[name] = handler; },
            append(...children) { this.children.push(...children); children.forEach(child => { child.parent = this; }); },
            replaceChildren() { this.children = []; },
            closest() { return this.parent?.parent; },
            querySelectorAll() {
                return this.children.flatMap(child => [child, ...child.querySelectorAll()]).filter(child => child.type === "button");
            },
            focus() { document.activeElement = this; } };
        if (id) nodes.set(id, item);
        return item;
    }
    const entry = { name: "Landscape", etag: "original-content", content: { type: "color" } };
    const damaged = { name: "Damaged", etag: "damaged-content", valid: false, content: {} };
    const arrangement = { name: "Relative custom", etag: "original-arrangement", logical: true };
    const state = { etag: "original-wall", etagState: "current", layoutKind: "logical", draft: null,
        snapshots: { scenes: [entry, damaged], layouts: [arrangement] } };
    const writes = [], previews = [], tasks = [];
    let sessionBusy = false, release, failRead = false;
    const el = Object.fromEntries(["savedLayouts", "btnApply", "btnCancel", "btnUndo", "btnRedo", "boundsMode",
        "boundsPadding", "btnPackTablets", "layoutMsg"].map(id => [id, node(id)]));
    const ctx = vm.createContext({ state, el, document, API_LAYOUTS: "/api/v3/layouts",
        session: { view: () => ({ busy: sessionBusy }) }, window: { confirm: () => true },
        syncGeometryControls() {}, renderCalibrationHelper() {}, syncInspector() {}, syncTabDots() {},
        resolveOutput: async () => true,
        setMsg: (target, text) => { target.textContent = text; },
        showReturnPoint() {}, handleWriteError() {},
        ingestConfig: result => { state.etag = result.etag; },
        loadLayouts: () => new Promise((resolve, reject) => { release = () => failRead ? reject(new Error("read failed")) : resolve(); }),
        api: async (method, path, body, options) => { writes.push({ method, path, options }); return { etag: "recalled-wall" }; },
        operatorContent: { imageFor: () => null, previewScene: (item, guard) => previews.push({ item, guard }) },
        showTab: async name => { tasks.push(name); } });
    vm.runInContext(extract("    let compositionBusy = false;", "    const profileCache")
        + extract("    function syncDraftUi()", "    function pushUndo(")
        + extract("    function setBusy(", "    /*")
        + extract("    function snapshotMatches(", "    async function loadLayouts()")
        + extract("    function savedTag(", "    function renderSavedLayouts()")
        + extract("    function updateSavedButtons()", "    function showReturnPoint(")
        + extract("    async function recallLayout(", "    async function deleteLayout(")
        + "let savedScenes = [], scenesLoaded = true;\n"
        + extract("    function sceneMeta(", "    async function loadScenes()"), ctx);
    ctx.entries = [entry, damaged];
    const render = () => vm.runInContext("savedScenes = entries; renderSavedScenes();", ctx);
    const button = name => node("saved-scenes").querySelectorAll().find(item => item.attrs["aria-label"] === name);
    render();
    return { ctx, state, entry, arrangement, el, document, render, button, writes, previews, tasks,
        release: () => release(), sessionBusy: value => { sessionBusy = value; ctx.syncDraftUi(); },
        failRead: () => { failRead = true; } };
}

(async () => {
    const h = setup();
    const preview = () => h.button("Preview content “Landscape”");
    const damaged = () => h.button("Preview content “Damaged”");
    const deletion = () => h.button("Delete content “Damaged”");
    assert.equal(preview().disabled, false);
    assert.equal(damaged().disabled, true);
    assert.equal(deletion().disabled, false, "damaged content remains deletable");
    const focused = preview(); focused.focus();
    h.ctx.setBusy(true);
    assert.equal(preview().disabled, true, "busy entry disables an already-rendered saved Preview");
    assert.equal(deletion().disabled, true, "busy entry also disables saved Delete");
    assert.equal(preview(), focused, "availability updates preserve the original node");
    assert.equal(h.document.activeElement, focused, "availability updates do not move focus");
    h.ctx.setBusy(false);
    assert.equal(preview().disabled, false);
    assert.equal(damaged().disabled, true, "busy exit retains the damaged-preview restriction");
    assert.equal(deletion().disabled, false);
    h.ctx.setBusy(true); h.render(); h.ctx.setBusy(false);
    assert.equal(preview().disabled, false, "content rendered during a command becomes available when it ends");
    h.sessionBusy(true);
    assert.equal(preview().disabled, true, "session commands use the same availability projection");
    h.ctx.setBusy(false);
    assert.equal(preview().disabled, true, "composition completion cannot unlock a busy session");
    h.sessionBusy(false);
    assert.equal(preview().disabled, false);

    const recalling = h.ctx.recallLayout(h.arrangement);
    await new Promise(setImmediate);
    assert.match(h.el.layoutMsg.textContent, /recalled/);
    assert.equal(preview().disabled, true, "a recall receipt does not unlock Preview before its saved-list read completes");
    await h.ctx.recallLayout(h.arrangement);
    await preview().listeners.click();
    await deletion().listeners.click();
    assert.equal(h.writes.length, 1, "pending recall and saved actions cannot issue a second write");
    assert.deepEqual(JSON.parse(JSON.stringify(h.writes[0])), { method: "POST", path: "/api/v3/logical-layouts/Relative%20custom/recall", options: { ifMatch: "original-wall" } });
    assert.equal(h.previews.length, 0);
    h.release(); await recalling;
    assert.equal(preview().disabled, false);
    assert.deepEqual(h.tasks, [], "busy exit never queues a preview or a task switch");
    await preview().listeners.click();
    assert.equal(h.previews.length, 1);
    assert.equal(h.previews[0].item, h.entry, "explicit Preview keeps the original saved entry");
    assert.equal(h.previews[0].guard, "recalled-wall");
    assert.deepEqual(h.tasks, ["content"]);
    assert.equal(h.writes.length, 1, "Preview adds no write");
    h.state.snapshots.scenes = [{ ...h.entry, etag: "replacement-content" }];
    await preview().listeners.click();
    assert.equal(h.previews.length, 1, "same-name replacement cannot substitute content under the original entry");
    assert.equal(h.writes.length, 1);

    const failure = setup(); failure.failRead();
    const failedRecall = failure.ctx.recallLayout(failure.arrangement);
    await new Promise(setImmediate); failure.release(); await failedRecall;
    assert.equal(failure.button("Preview content “Landscape”").disabled, false, "failed follow-up read also releases command availability");
    console.log("Saved actions track composition and session busy state, recover after recall, and retain snapshot guards without duplicate writes");
})().catch(error => { console.error(error); process.exitCode = 1; });
