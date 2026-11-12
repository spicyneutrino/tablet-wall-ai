"use strict";
const assert = require("node:assert/strict");
const test = require("node:test");
const composition = require("../frontend/controller/operator-composition.js");
const forms = require("../frontend/controller/operator-forms.js");
const measurements = require("../frontend/controller/operator-measurements.js");
const flush = () => new Promise(resolve => setImmediate(resolve));

function setup() {
    const nodes = new Map();
    function node(id = "") {
        if (!nodes.has(id)) nodes.set(id, {
            id, value: "", textContent: "", dataset: {}, options: [], children: [], listeners: {},
            classList: { toggle() {} }, matches: () => true,
            addEventListener(name, fn) { this.listeners[name] = fn; },
            append(...items) { this.children.push(...items); },
            replaceChildren(...items) { this.children = items; },
            querySelector: () => null, querySelectorAll: () => [],
            getClientRects: () => [1], add() {}, focus() {}
        });
        return nodes.get(id);
    }
    global.document = { getElementById: node, createElement: node, createTextNode: textContent => ({ textContent }),
        querySelector: () => null, activeElement: null, body: {} };
    global.Option = function (text, value) { this.textContent = text; this.value = value; };
    global.window = { OperatorState: require("../frontend/controller/operator-state.js") };
    let local = composition.reduce(composition.createState(), { type: "select-tablet", id: "a" });
    const state = { formDeviceId: "a", etag: "etag-a", etagState: "current", busy: false,
        roster: { a: { online: true }, b: { online: true } }, base: { kind: "logical", placements: {} },
        draft: { slots: {} }, savedLayouts: [], deviceLabels: {}, tabletModels: {}, tabletAssignments: {} };
    Object.defineProperty(state, "selectedId", { get: () => local.selectedTablet,
        set: id => { local = composition.reduce(local, { type: "select-tablet", id }); } });
    const requests = [], tabletForms = forms.create();
    let release;
    const api = (...args) => { requests.push(args); return new Promise(resolve => { release = resolve; }); };
    return { state, tabletForms, node, api, requests, release: result => release(result) };
}

test("a pending label save stays keyed to A after selection changes to B", async () => {
    const rig = setup(), { state, tabletForms, node } = rig;
    const devices = require("../frontend/controller/operator-devices.js").create({
        state, tabletForms, api: rig.api, labelFor: id => id, announce() {}, profileFor: () => null,
        calibrationFor: () => null, ingestConfig() {}, refreshRoster: async () => {}
    });
    devices.render();
    node("tablet-label").value = "Name for A";
    node("tablet-label").listeners.input();
    await node("tablet-label-form").listeners.submit({ preventDefault() {} });
    assert.equal(rig.requests[0][1], "/api/v3/devices/a");
    assert.deepEqual(rig.requests[0][2], { label: "Name for A" });
    state.selectedId = "b";
    devices.render();
    node("tablet-label").value = "Unsaved name for B";
    node("tablet-label").listeners.input();
    const before = tabletForms.get("b", "name");
    rig.release({ etag: "etag-after-a" });
    await flush();
    assert.equal(rig.requests.length, 1);
    assert.equal(node("tablet-label").value, "Unsaved name for B");
    assert.deepEqual(tabletForms.get("b", "name"), before);
    assert.equal(tabletForms.get("a", "name").dirty, false);
    assert.doesNotMatch(node("tablet-action-message").textContent, /Name saved for a/);
});

for (const group of ["profile", "calibration"]) test("a pending " + group + " save cannot write or populate B", async () => {
    const rig = setup(), { state, tabletForms, node } = rig;
    const values = {
        profileActiveWidth: "200", profileActiveHeight: "120", profileBezelTop: "0", profileBezelRight: "0",
        profileBezelBottom: "0", profileBezelLeft: "0", profilePixelWidth: "", profilePixelHeight: "",
        profileLabel: "A profile", profileProvenance: "manual", calProfileRevision: "1", calViewportWidth: "800",
        calViewportHeight: "600", calDpr: "1", calOrientation: "0", calMode: "tab", calQuarterTurn: "0",
        calAnchorEdge: "top-left", calOffsetX: "0", calOffsetY: "0", calMmCssX: "0.25", calMmCssY: "0.2",
        calUncertainty: "0", calMethod: "manual"
    };
    const elements = Object.fromEntries(Object.entries(values).map(([id, value]) => {
        const field = node(id); field.value = value; return [id, field];
    }));
    for (const id of ["profileForm", "calibrationForm", "profileMsg", "calibrationMsg"]) elements[id] = node(id);
    const fields = Object.entries(elements).filter(([id]) => id.startsWith(group === "profile" ? "profile" : "cal")
        && Object.hasOwn(values, id)).map(([, field]) => field);
    elements[group === "profile" ? "profileForm" : "calibrationForm"].querySelectorAll = () => fields;
    tabletForms.observe("a", group, { ...Object.fromEntries(fields.map(field => [field.id, field.value])), _revision: 1 }, state.etag);
    const feature = measurements.create({
        elements, physicalCalibration: require("../frontend/controller/physical-calibration.js"),
        refresh: async () => {}, state, tabletForms, api: rig.api,
        num: value => value.trim() && Number.isFinite(Number(value)) ? Number(value) : null,
        markInvalid() {}, ValidationError: Error, syncTabDots() {}, clearMsg() {}, clearError() {},
        announce() {}, setMsg: (field, text) => { field.textContent = text; }, errorDetail: error => error.message,
        resolveOutput: async () => true, setBusy: value => { state.busy = value; },
        handleWriteError: error => { throw error; }
    });
    const pending = feature[group === "profile" ? "saveProfile" : "saveCalibration"]({ preventDefault() {} });
    await flush();
    assert.equal(rig.requests.length, 1);
    assert.equal(rig.requests[0][1], "/api/v3/" + (group === "profile" ? "displays" : "calibrations") + "/a");
    assert.deepEqual(rig.requests[0][3], { ifMatch: "etag-a" });
    state.selectedId = "b";
    state.formDeviceId = "b";
    fields.forEach(field => { field.value = "B " + field.id; });
    tabletForms.observe("b", group, { subject: "B" }, "etag-b");
    tabletForms.edit("b", group, { subject: "B draft" }, "etag-b");
    const before = tabletForms.get("b", group);
    rig.release({ etag: "etag-after-a", [group === "profile" ? "display" : "calibration"]: { revision: 2, profile_revision: 1 } });
    await pending;
    assert.equal(rig.requests.length, 1, "completion sends no command for B");
    assert.equal(state.formDeviceId, "b", "completion cannot reset B's mounted form");
    assert.deepEqual(tabletForms.get("b", group), before);
    assert.ok(fields.every(field => field.value === "B " + field.id), "completion cannot populate B with A's fields");
    assert.equal(tabletForms.get("a", group).dirty, false);
    assert.equal(elements[group === "profile" ? "profileMsg" : "calibrationMsg"].textContent, "");
});
