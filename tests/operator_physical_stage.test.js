"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const context = vm.createContext({ window: { OperatorState: require("../frontend/controller/operator-state.js") } });
vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/physical-stage.js"), "utf8"), context);
const { rosterSummary, configureDeviceSheet } = context.window.PhysicalStage;

const mixed = {
    layout: { kind: "physical", slots: { a: {}, b: {}, c: {}, d: {}, e: {}, f: {} } },
    runtime: { devices: { a: { online: false }, b: { online: false } } }
};
assert.equal(rosterSummary(mixed, false), "0 online · 4 retained wall positions");
assert.equal(rosterSummary(mixed, true), "Status stale · Last known: 0 online · 4 retained wall positions");

const allRegistered = {
    layout: { kind: "logical", placements: { a: {}, b: {} } },
    runtime: { devices: { a: { online: true }, b: { online: false } } }
};
assert.equal(rosterSummary(allRegistered, false), "1 online");
assert.equal(rosterSummary({ layout: { kind: "logical", placements: {} } }, false), "Tablet status unknown");

const sheet = {
    open: true,
    dataset: { modal: "true" },
    closed: 0,
    attrs: { open: "" },
    close() { this.closed += 1; this.open = false; },
    removeAttribute(name) { delete this.attrs[name]; },
    setAttribute(name, value) { this.attrs[name] = value; this.open = true; }
};
assert.equal(configureDeviceSheet(sheet, true, true), true);
assert.equal(sheet.closed, 0, "same-mode height changes leave an open device sheet alone");
assert.equal(sheet.open, true);
assert.equal(configureDeviceSheet(sheet, false, true), false);
assert.equal(sheet.closed, 1, "switching to desktop closes a modal sheet");
assert.equal(sheet.open, true, "desktop mode keeps the sheet available as an open panel");
assert.equal(sheet.attrs.open, "");

console.log("Physical stage roster counts and device-sheet mode transitions passed");

function stageSetup() {
    const nodes = new Map();
    let compact = true;
    const document = { activeElement: null };
    function node(id) {
        if (!nodes.has(id)) {
            const item = {
                id, dataset: {}, hidden: false, isConnected: true, disabled: false, open: false, modal: false,
                textContent: "", attrs: {}, listeners: {}, modalCount: 0, focusCount: 0, scrolled: false,
                addEventListener(event, handler) { this.listeners[event] = handler; },
                setAttribute(name, value) { this.attrs[name] = value; if (name === "open") this.open = true; },
                removeAttribute(name) { delete this.attrs[name]; if (name === "open") this.open = false; },
                focus() { this.focusCount += 1; document.activeElement = this; },
                showModal() { this.open = true; this.modal = true; this.modalCount += 1; },
                close() { this.open = false; this.modal = false; if (this.listeners.close) this.listeners.close(); },
                getClientRects() { return this.hidden ? [] : [{}]; },
                contains(child) { return child === this; },
                scrollIntoView() { this.scrolled = true; }
            };
            nodes.set(id, item);
        }
        return nodes.get(id);
    }
    document.getElementById = node;
    document.querySelector = () => node("stage");
    const resizeListeners = [];
    const window = {
        OperatorState: Object.assign({}, require("../frontend/controller/operator-state.js"), { stageView: () => ({}) }),
        matchMedia: () => ({ matches: compact }),
        addEventListener(event, handler) { if (event === "resize") resizeListeners.push(handler); }
    };
    const state = { selectedId: null, tabName: "tablet", roster: { a: { online: true }, b: { online: true } },
        deviceLabels: {}, base: { slots: { a: {}, b: {} } } };
    const showTabCalls = [];
    const el = {
        stageSvg: { querySelectorAll: () => [], classList: { add() {}, remove() {} } },
        stageScale: node("stage-scale"), profileMsg: node("profile-msg"), calibrationMsg: node("calibration-msg"),
        inspectorEmpty: node("inspector-empty"), inspectorBody: node("inspector-body"), inspectorMissing: node("inspector-missing"),
        btnCopySelectedId: node("copy-selected-id"), btnAddSlot: node("add-slot"), slotMissingText: node("slot-missing-text"),
        selectedTitle: node("selected-title"), selectedId: node("selected-id"), selectedState: node("selected-state"),
        selectedNote: node("selected-note"), btnRotate: node("rotate"), btnDeleteSlot: node("delete-slot"),
        btnNudgeXMinus: node("nudge-x-minus"), btnNudgeXPlus: node("nudge-x-plus"),
        btnNudgeYMinus: node("nudge-y-minus"), btnNudgeYPlus: node("nudge-y-plus"),
        wallHealth: node("wall-health"), btnWallHealth: node("btn-wall-health"), deviceCount: node("device-count"),
        rosterStatus: node("roster-status"), deviceList: node("device-list")
    };
    const context = vm.createContext({ window, document });
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/physical-stage.js"), "utf8"), context);
    const heading = node("tablet-action-name");
    const stage = context.window.PhysicalStage.create({
        DRAG_THRESHOLD_PX: 3, afterDraftChange() {}, announce() {}, bodyMetrics: () => null,
        calibrationFor: () => null, beginManual() {}, canManualEdit: () => true, clearMsg() {},
        clone: value => value, deviceEntries: () => [], deviceLabel: id => id, deviceNumber: () => 1,
        deviceRows: new Map(), el, finiteOr: (value, fallback) => Number.isFinite(value) ? value : fallback,
        formatNumber: value => String(value), isOnline: () => true, latestProfile: () => null,
        mutateDraft: () => true, numberTag: () => "1", numberedLabel: id => id, populateDeviceCard() {},
        profileFor: () => null, pushUndo() {}, roundTo: value => value, selectedSlot: () => null,
        selectionChanged() { heading.textContent = state.selectedId || ""; },
        setInputValue() {}, showError() {},
        showTab(name) { showTabCalls.push(name); state.tabName = name; return true; },
        state, syncTabDots() {}, validPair: () => ({})
    });
    return { stage, state, document, node, heading, sheet: node("device-sheet"), showTabCalls,
        resize() { resizeListeners.forEach(listener => listener()); },
        setCompact(value) { compact = value; } };
}

(async () => {
    const same = stageSetup();
    const trigger = same.node("issue-a");
    same.state.selectedId = "a";
    same.stage.selectDevice("a", { reveal: true, taskOpened: true, trigger });
    await new Promise(setImmediate);
    assert.equal(same.sheet.modalCount, 1, "the selected device sheet opens once");
    assert.equal(same.sheet.dataset.modal, "true");
    assert.equal(same.heading.focusCount, 1, "the recovery heading receives focus after showModal");
    assert.equal(same.state.sheetTrigger, trigger, "the invoking issue control is kept for close return");
    assert.deepEqual(same.showTabCalls, [], "a completed task transition is not re-entered");
    same.stage.selectDevice("a", { reveal: true, taskOpened: true, trigger: same.node("issue-a-again") });
    await new Promise(setImmediate);
    assert.equal(same.sheet.modalCount, 1, "selecting the same tablet again reuses the open sheet");
    assert.equal(same.state.sheetTrigger, same.node("issue-a-again"), "the newest invoking control owns close return");

    const other = stageSetup();
    other.state.selectedId = "a";
    const triggerB = other.node("issue-b");
    other.stage.selectDevice("b", { reveal: true, taskOpened: true, trigger: triggerB });
    await new Promise(setImmediate);
    assert.equal(other.state.selectedId, "b", "a different device becomes the selected tablet");
    assert.equal(other.heading.textContent, "b", "the recovery heading names the selected device");
    assert.equal(other.sheet.modalCount, 1, "a different device reveals through the same single sheet");
    other.sheet.close();
    assert.equal(triggerB.focusCount, 1, "close restores the invoking issue control");
    assert.equal(other.state.sheetTrigger, null);

    const gone = stageSetup();
    const staleTrigger = gone.node("issue-gone");
    staleTrigger.isConnected = false;
    gone.state.selectedId = "a";
    gone.stage.selectDevice("a", { reveal: true, taskOpened: true, trigger: staleTrigger });
    await new Promise(setImmediate);
    gone.sheet.close();
    assert.equal(gone.node("issues-title").focusCount, 1, "a removed invoking control falls back to the task heading");

    const race = stageSetup();
    race.state.selectedId = "a";
    race.state.tabName = "content";
    race.stage.selectDevice("b", { reveal: true, trigger: race.node("issue-b") });
    race.state.selectedId = "c";
    await new Promise(setImmediate);
    assert.equal(race.state.tabName, "tablet", "the pending transition completed before the stale reveal was rejected");
    assert.equal(race.state.selectedId, "c");
    assert.equal(race.sheet.modalCount, 0, "a newer selection wins over a pending transition");
    assert.deepEqual(race.showTabCalls, ["tablet"], "the pending reveal used the existing task transition once");

    const resize = stageSetup();
    const resizeTrigger = resize.node("issue-a");
    resize.state.selectedId = "a";
    resize.stage.selectDevice("a", { reveal: true, taskOpened: true, trigger: resizeTrigger });
    await new Promise(setImmediate);
    assert.equal(resize.sheet.modal, true);
    resize.setCompact(false);
    resize.resize();
    assert.equal(resize.sheet.open, true, "phone to desktop keeps the sheet available as an inline panel");
    assert.equal(resize.sheet.dataset.modal, "", "desktop mode no longer claims a modal");
    assert.equal(resize.sheet.attrs.open, "", "desktop mode opens the inline panel");
    assert.equal(resizeTrigger.focusCount, 1, "closing the modal on resize restores the invoking control");
    resize.setCompact(true);
    resize.resize();
    assert.equal(resize.sheet.open, false, "desktop to phone closes the inline sheet instead of leaving an invisible modal");
    assert.equal(resize.sheet.attrs.open, undefined);
    console.log("Recovery reveals once after task completion, guards stale selections and restores focus across close and resize");
})().catch(error => { console.error(error); process.exitCode = 1; });
