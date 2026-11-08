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
