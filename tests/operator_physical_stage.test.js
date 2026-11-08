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

const stageModel = require("../frontend/controller/operator-stage.js");
const wake = (value, options) => stageModel.powerReadiness({ wake_lock: value }, options);
assert.equal(wake("held").label, "Power: held");
assert.equal(wake("held").warning, false);
assert.match(wake("held").guidance, /not proof/);
assert.match(wake("held").guidance, /Auto-Lock/);
assert.equal(wake("denied").warning, true);
assert.match(wake("denied").guidance, /cannot wake/);
assert.equal(wake("released").warning, true);
assert.match(wake("released").guidance, /foreground/);
assert.equal(wake("insecure").warning, true);
assert.match(wake("insecure").guidance, /trusted HTTPS origin/);
assert.equal(wake("unsupported").warning, false);
assert.match(wake("unsupported").guidance, /Auto-Lock/);
assert.equal(wake(undefined).state, "unknown");
assert.equal(wake("bogus").state, "unknown", "an unreported or invalid wake value is unknown, never a guessed state");
const staleWake = wake("held", { stale: true });
assert.equal(staleWake.label, "Last known power held · status stale");
assert.equal(staleWake.stale, true);
assert.match(staleWake.guidance, /last known report/);
assert.match(wake("denied", { stale: true, checkedAt: "2026-11-01T12:00:00Z" }).guidance, /Last checked/);
assert.equal(stageModel.exceptionLabel("displayed", "Reports current image"), "", "healthy paint has no stage exception label");
assert.equal(stageModel.exceptionLabel("failed", "Image failed · source missing"), "Image failed");
assert.equal(stageModel.exceptionLabel("loading", "Loading image"), "Loading");
assert.equal(stageModel.exceptionLabel("blocked", "Blocked"), "Blocked");
assert.equal(stageModel.exceptionLabel("unknown", "Current image unconfirmed"), "Unconfirmed");
assert.equal(stageModel.exceptionLabel("stale", "Previous paint · current image unconfirmed"), "Stale paint");
assert.equal(stageModel.exceptionLabel("stale", "Active mapping revisions differ from the pinned slot"), "Mapping mismatch");
assert.equal(stageModel.exceptionLabel("hidden", "Page hidden"), "Hidden");
assert.equal(stageModel.exceptionLabel("offline", "Offline · spot reserved"), "Offline");
assert.equal(stageModel.exceptionLabel("excluded", "Excluded from show"), "Excluded");
assert.equal(stageModel.exceptionLabel("identifying", "Identify overlay · image obscured"), "Identify");
assert.equal(stageModel.exceptionLabel("playback", "Experimental playback owns the display"), "Playback");
assert.equal(stageModel.exceptionLabel("viewport_mismatch", "Return to the calibrated rotation"), "Blocked");
assert.match(stageModel.helpText(true, "logical"), /Auto-Lock/);
assert.match(stageModel.helpText(true, "logical"), /trusted HTTPS origin/);
assert.match(stageModel.helpText(true, "logical"), /cannot wake a sleeping tablet remotely/);
console.log("Mixed wake states, freshness and concise exception labels passed");

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

function stageSetup(overrides = {}) {
    const nodes = new Map();
    let compact = true;
    const document = { activeElement: null, body: { dataset: {} } };
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
        DRAG_THRESHOLD_PX: 3, afterDraftChange: overrides.afterDraftChange || function () {},
        announce: overrides.announce || function () {}, bodyMetrics: () => null,
        calibrationFor: () => null, beginManual: overrides.beginManual || function () {}, canManualEdit: () => true,
        clearMsg() {}, clone: overrides.clone || (value => value), deviceEntries: () => [], deviceLabel: id => id,
        deviceNumber: () => 1, deviceRows: new Map(), el,
        finiteOr: (value, fallback) => Number.isFinite(value) ? value : fallback,
        formatNumber: value => String(value), isOnline: () => true, latestProfile: () => null,
        mutateDraft: overrides.mutateDraft || (() => true), numberTag: () => "1", numberedLabel: id => id,
        populateDeviceCard() {}, profileFor: () => null, pushUndo: overrides.pushUndo || function () {},
        roundTo: value => value, selectedSlot: () => null,
        selectionChanged() { heading.textContent = state.selectedId || ""; },
        setInputValue() {}, showError() {},
        showTab(name) { showTabCalls.push(name); state.tabName = name; return true; },
        state, syncTabDots() {}, validPair: () => ({})
    });
    return { stage, state, document, window, context, node, heading, sheet: node("device-sheet"), showTabCalls, el,
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

/* Pointer deltas, view transform changes, logical snap and Match shape. */
function viewMatrix(view) {
    return { a: view.scale, b: 0, c: 0, d: view.scale, e: view.offX, f: view.offY,
        inverse() { return this; } };
}

function logicalDraft() {
    return {
        kind: "logical", width: 1000, height: 700, sizing: { mode: "fixed", padding: 0 },
        placements: {
            a: { x: 100, y: 100, w: 100, h: 70, bezel: { top: 3, right: 5, bottom: 7, left: 11 } },
            b: { x: 300, y: 250, w: 80, h: 120, bezel: { top: 0, right: 0, bottom: 0, left: 0 } }
        }
    };
}

function dragSetup(options = {}) {
    const setup = stageSetup(Object.assign({ clone: structuredClone }, options));
    const { el, state, window, document } = setup;
    window.PhysicalSizing = require("../frontend/controller/physical-sizing.js");
    window.OperatorStage = { draw: () => null, helpText: editable => require("../frontend/controller/operator-stage.js").helpText(editable) };
    const view = options.view || { scale: 1, offX: 0, offY: 0 };
    const svg = el.stageSvg;
    svg.style = {};
    svg.setPointerCapture = function () {};
    svg.hasPointerCapture = function () { return false; };
    svg.releasePointerCapture = function () {};
    svg.getScreenCTM = function () { return viewMatrix(view); };
    svg.createSVGPoint = function () {
        return { x: 0, y: 0, matrixTransform(matrix) {
            return { x: (this.x - matrix.e) / matrix.a, y: (this.y - matrix.f) / matrix.d };
        } };
    };
    state.selectedId = "a";
    state.tabName = "show";
    state.busy = false;
    state.gridPreview = false;
    state.viewLive = false;
    state.previewContent = false;
    state.draft = options.draft || logicalDraft();
    state.stage = { scale: 1, offX: 0, offY: 0, width: 720, height: 480 };
    state.roster = options.roster || {
        a: { online: true, viewport: { width: 1600, height: 1000 } },
        b: { online: true, viewport: { width: 1600, height: 1000 } }
    };
    state.rosterError = options.rosterError || null;
    state.undo = [];
    state.redo = [];
    setup.node("logical-snap").value = String(options.step || 1);
    setup.node("logical-snap-enabled").checked = options.enabled !== false;
    return Object.assign(setup, { view: view });
}

function pointerEvent(clientX, clientY, extra = {}) {
    const group = { dataset: { deviceId: "a" }, closest(selector) {
        if (selector === ".slot") return group;
        if (selector === ".logical-resize") return extra.resize ? group : null;
        return null;
    } };
    return { pointerId: 1, clientX: clientX, clientY: clientY, button: 0,
        pointerType: extra.pointerType || "mouse", altKey: !!extra.altKey,
        target: group, preventDefault() {} };
}

function movedTo(deltaX, deltaY, extra = {}) {
    return pointerEvent(100 + deltaX, 100 + deltaY, extra);
}

/* Fit, 2x and scrolled stage keep the same logical displacement. */
for (const condition of [
    { name: "Fit", view: { scale: 1, offX: 0, offY: 0 }, dx: 5, dy: 5, expectX: 105, expectY: 105 },
    { name: "2x", view: { scale: 2, offX: 0, offY: 0 }, dx: 10, dy: 10, expectX: 105, expectY: 105 },
    { name: "scrolled", view: { scale: 1, offX: 37, offY: 21 }, dx: 5, dy: 5, expectX: 105, expectY: 105 }
]) {
    const undo = [];
    const drag = dragSetup({ view: { ...condition.view }, pushUndo: before => undo.push(before) });
    const start = pointerEvent(100, 100);
    drag.stage.onPointerDown(start);
    drag.stage.onPointerMove(movedTo(condition.dx, condition.dy));
    assert.equal(drag.state.draft.placements.a.x, condition.expectX, condition.name + " pointer delta in wall units");
    assert.equal(drag.state.draft.placements.a.y, condition.expectY, condition.name + " pointer delta in wall units");
    drag.stage.onPointerUp(movedTo(condition.dx, condition.dy));
    assert.equal(undo.length, 1, condition.name + " drag pushes the original draft once");
    assert.equal(undo[0].placements.a.x, 100);
    console.log("Stage pointer delta holds at " + condition.name);
}

/* Snap spacing, Alt bypass and the touch checkbox. */
const altSetup = dragSetup({ step: 4 });
altSetup.stage.onPointerDown(pointerEvent(100, 100));
altSetup.stage.onPointerMove(movedTo(5, 5, { altKey: true }));
assert.equal(altSetup.state.draft.placements.a.x, 105, "Alt bypasses grid and edge snap for the current move");
assert.equal(altSetup.state.draft.placements.a.y, 105);
const gridSetup = dragSetup({ step: 4 });
gridSetup.stage.onPointerDown(pointerEvent(100, 100));
gridSetup.stage.onPointerMove(movedTo(5, 5));
assert.equal(gridSetup.state.draft.placements.a.x, 104, "grid spacing still rounds wall coordinates");
assert.equal(gridSetup.state.draft.placements.a.y, 104);
const touchSetup = dragSetup({ step: 4, enabled: false });
touchSetup.stage.onPointerDown(pointerEvent(100, 100, { pointerType: "touch" }));
touchSetup.stage.onPointerMove(movedTo(5, 5, { pointerType: "touch" }));
assert.equal(touchSetup.state.draft.placements.a.x, 105, "touch uses the snap checkbox instead of Alt");
assert.equal(touchSetup.state.draft.placements.a.y, 105);
const outsideSetup = dragSetup();
outsideSetup.stage.onPointerDown(pointerEvent(100, 100));
const outsideMove = movedTo(5, 5);
outsideMove.target = null;
outsideSetup.stage.onPointerMove(outsideMove);
assert.equal(outsideSetup.state.draft.placements.a.x, 105, "pointer capture keeps a drag alive outside the SVG target");

/* Edge snap through body and active edges, and a deterministic tie. */
const edgeSetup = dragSetup();
edgeSetup.stage.onPointerDown(pointerEvent(100, 100));
edgeSetup.stage.onPointerMove(movedTo(97, 77));
assert.equal(edgeSetup.state.draft.placements.a.x, 200, "a tablet body edge aligns inside the 8 px threshold");
assert.equal(edgeSetup.state.draft.placements.a.y, 180);
const activeSetup = dragSetup();
activeSetup.stage.onPointerDown(pointerEvent(100, 100));
activeSetup.stage.onPointerMove(movedTo(188, 0));
assert.equal(activeSetup.state.draft.placements.a.x, 289, "an active edge aligns through the asymmetric left bezel");
const tieDraft = logicalDraft();
tieDraft.placements.c = { x: 10, y: 400, w: 1, h: 10, bezel: {} };
const tieSetup = dragSetup({ draft: tieDraft });
tieSetup.stage.onPointerDown(pointerEvent(100, 100));
tieSetup.stage.onPointerMove(movedTo(-95, 0));
assert.equal(tieSetup.state.draft.placements.a.x, 0, "equal edge distances resolve deterministically");

/* Resize stays on grid spacing and never moves the body. */
const resizeSetup = dragSetup({ step: 4 });
resizeSetup.stage.onPointerDown(pointerEvent(100, 100, { resize: true }));
resizeSetup.stage.onPointerMove(movedTo(10, 10, { resize: true }));
assert.equal(resizeSetup.state.draft.placements.a.w, 112);
assert.equal(resizeSetup.state.draft.placements.a.h, 80);
assert.equal(resizeSetup.state.draft.placements.a.x, 100, "resize anchors the body position");
assert.equal(resizeSetup.state.draft.placements.a.y, 100);

/* Cancel paths restore the pre-drag draft. */
const cancelSetup = dragSetup();
const cancelOriginal = structuredClone(cancelSetup.state.draft);
cancelSetup.stage.onPointerDown(pointerEvent(100, 100));
cancelSetup.stage.onPointerMove(movedTo(40, 40));
cancelSetup.stage.onPointerCancel({ pointerId: 1 });
assert.deepEqual(cancelSetup.state.draft, cancelOriginal, "pointercancel restores the pre-drag geometry");
assert.equal(cancelSetup.state.drag, null);
const escapeSetup = dragSetup();
const escapeOriginal = structuredClone(escapeSetup.state.draft);
escapeSetup.stage.onPointerDown(pointerEvent(100, 100));
escapeSetup.stage.onPointerMove(movedTo(40, 40));
escapeSetup.stage.endDrag(false);
assert.deepEqual(escapeSetup.state.draft, escapeOriginal, "the Escape path restores the pre-drag geometry");
let lastAnnouncement = "";
const viewCancel = dragSetup({ announce: message => { lastAnnouncement = message; } });
const viewCancelOriginal = structuredClone(viewCancel.state.draft);
viewCancel.stage.onPointerDown(pointerEvent(100, 100));
viewCancel.stage.onPointerMove(movedTo(40, 40));
viewCancel.view.scale = 2;
viewCancel.stage.onPointerMove(movedTo(50, 50));
assert.deepEqual(viewCancel.state.draft, viewCancelOriginal, "a mid-drag zoom or resize cancels before recomputing geometry");
assert.equal(viewCancel.state.drag, null);
assert.match(lastAnnouncement, /view changed/, "the operator is told why the drag was cancelled");
const commitCancel = dragSetup({ pushUndo: () => { throw new Error("stale drag committed"); } });
const commitOriginal = structuredClone(commitCancel.state.draft);
commitCancel.stage.onPointerDown(pointerEvent(100, 100));
commitCancel.stage.onPointerMove(movedTo(40, 40));
commitCancel.view.scale = 2;
commitCancel.stage.onPointerUp(movedTo(50, 50));
assert.deepEqual(commitCancel.state.draft, commitOriginal, "a stale capture cannot commit after a transform change");

/* Fit/2x are view-only and cancel a drag on change. */
const zoomSetup = dragSetup({ announce: message => { lastAnnouncement = message; } });
const zoomOriginal = structuredClone(zoomSetup.state.draft);
zoomSetup.stage.setViewZoom("2x");
assert.equal(zoomSetup.document.body.dataset.viewZoom, "2x");
assert.deepEqual(zoomSetup.state.draft, zoomOriginal, "view zoom never changes geometry");
assert.deepEqual(zoomSetup.state.undo, [], "view zoom never changes undo history");
assert.match(lastAnnouncement, /arrangement is unchanged/);
zoomSetup.stage.setViewZoom("fit");
assert.equal(zoomSetup.document.body.dataset.viewZoom, "fit");
zoomSetup.stage.onPointerDown(pointerEvent(100, 100));
zoomSetup.stage.onPointerMove(movedTo(20, 20));
zoomSetup.stage.setViewZoom("2x");
assert.deepEqual(zoomSetup.state.draft, zoomOriginal, "changing zoom during a drag restores the pre-drag draft");
assert.equal(zoomSetup.state.drag, null);

/* Match screen shape uses a fresh online viewport and the draft path. */
const holder = { calls: 0, state: null };
const matchSetup = dragSetup({ mutateDraft(mutator) { mutator(holder.state.draft); holder.calls += 1; return true; } });
holder.state = matchSetup.state;
assert.equal(holder.calls, 0, "drag-only setup has not called the draft mutator");
matchSetup.stage.onPointerDown(pointerEvent(100, 100));
matchSetup.stage.onPointerMove(movedTo(20, 20));
matchSetup.stage.onPointerUp(movedTo(20, 20));
assert.equal(holder.calls, 0, "pointer editing never writes a durable command");
matchSetup.state.draft = logicalDraft();
const match = matchSetup.stage.matchScreenShape();
assert.equal(match.changed, true);
assert.equal(holder.calls, 1, "Match is a draft mutation, not a wire write");
const placement = matchSetup.state.draft.placements.a;
assert.equal(placement.h, 63, "logical height stays an integer");
assert.equal(placement.y, 104, "the active centre is preserved");
assert.equal(placement.w, 100);
assert.equal(placement.x, 100);
assert.deepEqual(placement.bezel, { top: 3, right: 5, bottom: 7, left: 11 });
const matchedAgain = matchSetup.stage.matchScreenShape();
assert.equal(matchedAgain.changed, false, "an already matching shape is not mutated again");
assert.equal(holder.calls, 1);
assert.equal(matchSetup.stage.matchStatus().available, true);
matchSetup.state.draft = { kind: "physical", slots: { a: { center_x_mm: 10 } } };
const measured = matchSetup.stage.matchScreenShape();
assert.equal(measured.changed, false);
assert.equal(measured.measured, true, "measured mode explains pinned measurements without mutation");
matchSetup.state.draft = logicalDraft();
matchSetup.state.roster.a.viewport = null;
const missing = matchSetup.stage.matchScreenShape();
assert.equal(missing.changed, false);
assert.match(missing.reason, /viewport/);
matchSetup.state.roster.a.viewport = { width: 1600, height: 1000 };
matchSetup.state.rosterError = "offline roster";
const stale = matchSetup.stage.matchScreenShape();
assert.equal(stale.changed, false);
assert.match(stale.reason, /stale/);
matchSetup.state.rosterError = null;
matchSetup.state.roster.a.online = false;
const offline = matchSetup.stage.matchScreenShape();
assert.equal(offline.changed, false);
assert.match(offline.reason, /offline/);
assert.match(matchSetup.stage.geometryHelp(), /Shift/);
assert.match(matchSetup.stage.geometryHelp(), /touch/);
console.log("Pointer cancellation, view zoom, logical snap and Match shape passed");

const relayoutView = { scale: 1, offX: 0, offY: 0 };
const relayoutUndo = [];
const relayout = dragSetup({ view: relayoutView, enabled: false, pushUndo: before => relayoutUndo.push(before),
    afterDraftChange() { relayoutView.offY = 2.2; } });
relayout.stage.onPointerDown(pointerEvent(100, 100));
relayout.stage.onPointerMove(movedTo(10, 10));
relayout.stage.onPointerMove(movedTo(20, 20));
relayout.stage.endDrag(true);
assert.equal(relayout.state.draft.placements.a.x, 120, "a draft-induced relayout does not cancel the first drag");
assert.equal(relayoutUndo.length, 1, "the clean-draft drag commits one undo entry");

/* Mixed paint and wake states in the real roster and stage annotation. */
class FakeElement {
    constructor(tagName = "div") {
        this.tagName = tagName; this.attrs = new Map(); this.children = []; this.dataset = {};
        this.textContent = ""; this.style = { setProperty() {} }; this.listeners = {};
        this.hidden = false; this.disabled = false; this.open = false; this.parentElement = null;
        this.classList = { add() {}, remove() {}, contains: name => (this.getAttribute("class") || "").split(/\s+/).includes(name) };
    }
    get attributes() { return [...this.attrs].map(([name, value]) => ({ name, value })); }
    setAttribute(name, value) {
        this.attrs.set(name, String(value));
        if (name.startsWith("data-")) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = String(value);
    }
    getAttribute(name) { const value = this.attrs.get(name); return value === undefined ? null : value; }
    hasAttribute(name) { return this.attrs.has(name); }
    removeAttribute(name) {
        this.attrs.delete(name);
        if (name.startsWith("data-")) delete this.dataset[name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())];
    }
    append(...nodes) { nodes.forEach(node => this.insertBefore(node, null)); }
    insertBefore(node, before) {
        if (node.parentElement) node.remove();
        const index = before ? this.children.indexOf(before) : this.children.length;
        this.children.splice(index, 0, node); node.parentElement = this; return node;
    }
    remove() {
        if (!this.parentElement) return;
        const index = this.parentElement.children.indexOf(this);
        if (index >= 0) this.parentElement.children.splice(index, 1);
        this.parentElement = null;
    }
    addEventListener(type, handler) { (this.listeners[type] = this.listeners[type] || []).push(handler); }
    getClientRects() { return this.hidden ? [] : [{}]; }
    focus() { if (this.ownerDocument) this.ownerDocument.activeElement = this; }
    contains(child) { return child === this; }
    scrollIntoView() {}
    querySelectorAll() { return []; }
    closest() { return null; }
    getScreenCTM() {
        const svg = this.ownerDocument && this.ownerDocument.__svg;
        const scale = svg ? ((parseFloat(svg.style.inlineSize) || 720) / 720) * (svg.__stageScale || 1) : 1;
        return { a: scale, b: 0, c: 0, d: scale, e: 0, f: 0 };
    }
}

function drawSetup() {
    const doc = { activeElement: null, body: { dataset: {} }, getElementById: () => null, querySelector: () => null,
        createElementNS: (_, tag) => { const item = new FakeElement(tag); item.ownerDocument = doc; return item; } };
    const win = { innerHeight: 900, scrollY: 0, matchMedia: () => ({ matches: false }),
        getComputedStyle: node => node.computed || {}, addEventListener() {}, requestAnimationFrame: () => 1,
        ResizeObserver: class { observe() {} disconnect() {} } };
    doc.defaultView = win;
    const field = new FakeElement("div");
    field.style = {};
    field.computed = { borderLeftWidth: "0", borderRightWidth: "0", borderTopWidth: "0", borderBottomWidth: "0" };
    field.getBoundingClientRect = () => ({ top: 0, bottom: 500, width: 900 });
    field.getClientRects = () => [1];
    field.parentElement = new FakeElement("div");
    field.parentElement.clientWidth = 900;
    field.parentElement.computed = { paddingLeft: "0", paddingRight: "0" };
    field.parentElement.getBoundingClientRect = () => ({ bottom: 500 });
    const svg = new FakeElement("svg");
    svg.ownerDocument = doc; svg.style = { setProperty() {} };
    svg.viewBox = { baseVal: { width: 720, height: 480 } };
    svg.closest = selector => selector === ".stage-scroll" ? field : null;
    svg.querySelectorAll = selector => {
        const name = selector.replace(/^\./, ""), found = [];
        const walk = node => node.children.forEach(child => {
            if ((child.getAttribute("class") || "").split(/\s+/).includes(name)) found.push(child);
            walk(child);
        });
        walk(svg); return found;
    };
    doc.__svg = svg;
    return { doc, svg, draw: stageModel.draw };
}

function descendants(node, predicate) {
    return node.children.flatMap(child => (predicate(child) ? [child] : []).concat(descendants(child, predicate)));
}

{
    const { doc, svg, draw } = drawSetup();
    const layout = { kind: "logical", width: 1000, height: 700, placements: {
        healthy: { x: 0, y: 0, w: 200, h: 150, bezel: {} },
        failed: { x: 250, y: 0, w: 200, h: 150, bezel: {} },
        denied: { x: 500, y: 0, w: 200, h: 150, bezel: {} },
        tiny: { x: 0, y: 200, w: 10, h: 10, bezel: {} }
    } };
    const statuses = {
        healthy: { status: "displayed", text: "Reports current image" },
        failed: { status: "failed", text: "Image failed · source missing" },
        denied: { status: "displayed", text: "Reports current image" },
        tiny: { status: "hidden", text: "Page hidden" }
    };
    const powers = { healthy: wake("held"), failed: wake("denied"), denied: wake("denied"), tiny: wake(undefined) };
    global.document = doc;
    const stage = draw({ svg, layout, content: null, profileFor: () => null, labelFor: id => "Tablet " + id,
        statusFor: id => statuses[id], powerFor: id => powers[id], selectedId: null, runtime: { devices: {} } });
    svg.__stageScale = stage.scale;
    const slot = id => descendants(svg, node => node.getAttribute("data-device-id") === id)[0];
    const statusText = id => descendants(slot(id), node => (node.getAttribute("class") || "") === "operator-slot-status");
    const markers = (id, name) => descendants(slot(id), node => (node.getAttribute("class") || "") === name);
    assert.equal(slot("healthy").dataset.powerState, "held");
    assert.equal(slot("healthy").dataset.status, "displayed");
    assert.equal(statusText("healthy").length, 0, "healthy art has no extra stage text");
    assert.equal(markers("healthy", "operator-slot-exception").length, 0);
    assert.equal(markers("healthy", "operator-slot-power").length, 0);
    assert.equal(slot("failed").dataset.powerState, "denied");
    assert.equal(statusText("failed")[0].textContent, "Image failed · Power denied");
    assert.match(slot("failed").getAttribute("aria-label"), /Image failed/);
    assert.match(slot("failed").getAttribute("aria-label"), /Power: denied/);
    assert.equal(markers("failed", "operator-slot-exception").length, 1);
    assert.equal(markers("failed", "operator-slot-power").length, 1);
    assert.equal(slot("denied").dataset.status, "displayed");
    assert.equal(statusText("denied")[0].textContent, "Power denied", "a painted tablet still carries an independent power warning");
    assert.equal(markers("denied", "operator-slot-exception").length, 0);
    assert.equal(markers("denied", "operator-slot-power").length, 1);
    assert.equal(statusText("tiny").length, 0, "a tiny slot leaves its label to the external roster");
    assert.match(slot("tiny").getAttribute("aria-label"), /Page hidden/);
    assert.equal(slot("tiny").dataset.status, "hidden");
    assert.equal(markers("tiny", "operator-slot-power").length, 1, "an unknown power report keeps a shape-only stage marker");
    assert.equal(slot("tiny").dataset.powerState, "unknown");
    delete global.document;
}

function rosterSetup() {
    const nodes = new Map();
    const doc = { activeElement: null, body: { dataset: {} },
        createElement: tag => { const item = new FakeElement(tag); item.ownerDocument = doc; return item; },
        getElementById: id => { if (!nodes.has(id)) nodes.set(id, new FakeElement(id)); return nodes.get(id); } };
    const now = performance.now();
    const token = { connection_id: "socket-1", generation: "g", revision: 8, render_seq: 4, mapping_revision: "mapping", asset: "image" };
    const config = { generation: "g", revision: 8,
        layout: { kind: "physical", bounds: { x: 0, y: 0, width: 1000, height: 500 }, slots: {
            a: { participating: true, profile_revision: 1, calibration_revision: 1 },
            b: { participating: true, profile_revision: 1, calibration_revision: 1 },
            c: { participating: true, profile_revision: 1, calibration_revision: 1 },
            d: { participating: false, profile_revision: 1, calibration_revision: 1 }
        } },
        scene: { content: { type: "image", asset: "image" } },
        runtime: { presentation: { owner: "static" }, devices: {
            a: { online: true, protocol: 3, caps: ["image", "render_ack"], mapping: { state: "ready" }, wake_lock: "denied",
                render: { state: "displayed", current: true, expected_token: { ...token }, accepted_token: { ...token }, age_ms: 0, observed_mono: now } },
            b: { online: true, protocol: 3, caps: ["image", "render_ack"], mapping: { state: "ready" }, wake_lock: "held",
                render: { state: "displayed", current: false, expected_token: { ...token }, accepted_token: { ...token }, age_ms: 0, observed_mono: now } },
            c: { online: false },
            d: { online: true, protocol: 3, caps: ["image", "render_ack"], mapping: { state: "ready" }, wake_lock: "released",
                render: { state: "displayed", current: true, expected_token: { ...token }, accepted_token: { ...token }, age_ms: 0, observed_mono: now } }
        } }
    };
    const state = { operatorConfig: config, roster: config.runtime.devices, rosterError: null,
        rosterCheckedAt: new Date(now).toISOString(), base: config.layout, basePlacements: {},
        deviceLabels: {}, selectedId: null, tabName: "tablet", busy: false, etagState: "current" };
    const el = { deviceList: doc.getElementById("device-list"), wallHealth: doc.getElementById("wall-health"),
        btnWallHealth: doc.getElementById("btn-wall-health"), deviceCount: doc.getElementById("device-count"),
        rosterStatus: doc.getElementById("roster-status") };
    const window = { OperatorState: require("../frontend/controller/operator-state.js"), OperatorStage: stageModel,
        matchMedia: () => ({ matches: false }), addEventListener() {} };
    const context = vm.createContext({ window, document: doc, performance });
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/physical-stage.js"), "utf8"), context);
    const stage = context.window.PhysicalStage.create({
        DRAG_THRESHOLD_PX: 3, afterDraftChange() {}, announce() {}, bodyMetrics: () => null,
        calibrationFor: () => null, beginManual() {}, canManualEdit: () => true, clearMsg() {}, clone: value => value,
        deviceEntries: () => Object.keys(config.layout.slots).map(id => ({ id, label: "Tablet " + id, slot: config.layout.slots[id] })),
        deviceLabel: id => "Tablet " + id, deviceNumber: () => 1, deviceRows: new Map(), el,
        finiteOr: (value, fallback) => Number.isFinite(value) ? value : fallback, formatNumber: String,
        isOnline: id => !!(config.runtime.devices[id] && config.runtime.devices[id].online), latestProfile: () => null,
        mutateDraft: () => true, numberTag: id => id, numberedLabel: id => "Tablet " + id,
        populateDeviceCard() {}, profileFor: () => null, pushUndo() {}, roundTo: value => value,
        selectedSlot: () => null, selectionChanged() {}, setInputValue() {}, showError() {}, showTab() {},
        state, syncTabDots() {}, validPair: () => ({})
    });
    const rowFor = id => el.deviceList.children.find(item => item.dataset.deviceId === id);
    const pickFor = id => rowFor(id).children[0];
    const metaFor = id => pickFor(id).children[1];
    return { stage, state, config, el, rowFor, pickFor, metaFor };
}

{
    const roster = rosterSetup();
    roster.stage.renderDeviceList();
    assert.equal(roster.el.deviceList.children.length, 4, "every wall position has one roster row");
    assert.equal(roster.rowFor("a").dataset.status, "displayed");
    assert.equal(roster.rowFor("a").dataset.powerState, "denied");
    assert.equal(roster.rowFor("a").dataset.powerWarning, "true");
    assert.equal(roster.metaFor("a").textContent, "Power denied");
    assert.match(roster.pickFor("a").getAttribute("aria-label"), /Power: denied/);
    assert.equal(roster.rowFor("b").dataset.status, "stale");
    assert.equal(roster.rowFor("b").dataset.powerState, "held");
    assert.equal(roster.rowFor("b").dataset.powerWarning, "false");
    assert.match(roster.metaFor("b").textContent, /Previous paint/);
    assert.match(roster.metaFor("b").textContent, /Power held/);
    assert.equal(roster.metaFor("b").textContent.includes("showing"), false, "held power never turns stale paint into displayed");
    assert.equal(roster.rowFor("c").dataset.powerState, "unknown");
    assert.equal(roster.metaFor("c").textContent, "Offline · spot reserved · Power unknown");
    assert.equal(roster.rowFor("d").dataset.status, "excluded");
    assert.equal(roster.rowFor("d").dataset.powerState, "released");
    assert.equal(roster.el.wallHealth.textContent, "1 of 3 showing the current image");
    assert.doesNotMatch(roster.el.wallHealth.textContent, /Power|wake-lock/i, "paint count stays separate from power readiness");
    roster.state.rosterError = "503 unavailable";
    roster.stage.renderDeviceList();
    assert.equal(roster.rowFor("a").dataset.status, "stale", "a stale roster cannot claim current paint");
    assert.equal(roster.rowFor("a").dataset.powerStale, "true");
    assert.match(roster.metaFor("a").textContent, /Status stale/);
    assert.match(roster.metaFor("a").textContent, /Last known power denied/);
    assert.match(roster.el.wallHealth.textContent, /Status stale/);
    assert.doesNotMatch(roster.el.wallHealth.textContent, /Power|wake-lock/i);
    console.log("Mixed roster paint, held/denied power, unknown and stale freshness passed");
}
