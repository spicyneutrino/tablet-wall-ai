"use strict";
const assert = require("node:assert/strict");
const { create } = require("../frontend/controller/operator-devices.js");
const nodes = new Map();
function node(id) {
    if (!nodes.has(id)) nodes.set(id, {
        dataset: {}, value: "", textContent: "", options: [], listeners: {},
        addEventListener(event, handler) { this.listeners[event] = handler; },
        replaceChildren() {}, append() {}, add(value) { this.options.push(value); },
        getClientRects() { return [1]; }, focus() { document.activeElement = this; }
    });
    return nodes.get(id);
}
global.document = { getElementById: node, createElement: node, activeElement: null, body: {} };
global.Option = function (text, value) { this.textContent = text; this.value = value; };
global.window = { OperatorState: {
    entries: layout => layout.slots,
    tabletState: () => evidence,
    compareIds: (roster, labels, a, b) => a.localeCompare(b)
} };
let evidence = { status: "displayed", text: "Reports current image", showing: true };
const state = { selectedId: "a", roster: { a: { online: true, caps: ["identify"] }, b: { online: true, caps: ["identify"] } },
    base: { slots: {} }, draft: { slots: {} }, layoutKind: "logical", etagState: "current", savedLayouts: [] };
let release;
const requests = [], announcements = [];
const devices = create({ state, tabletForms: require("../frontend/controller/operator-forms.js").create(),
    labelFor: id => "Tablet " + id, announce: text => announcements.push(text),
    api: (...args) => { requests.push(args); return new Promise(resolve => { release = resolve; }); },
    refreshRoster: async () => {}, profileFor: () => null, calibrationFor: () => null });
async function run() {
    for (const authority of ["stale", "missing"]) {
        state.etagState = authority;
        devices.render();
        assert.equal(node("tablet-recovery-actions").open, true, "stale authority keeps recovery visible");
        assert.equal(node("tablet-identify").disabled, true, authority + " authority disables the inspector command");
        assert.equal(devices.canIdentify("a"), false, authority + " authority disables other command entries");
        await devices.identify("a");
        assert.equal(requests.length, 0, "unavailable Identify sends no request");
        assert.match(node("tablet-action-message").textContent, /Refresh status/, "activation-time refusal explains recovery");
    }
    state.etagState = "current";
    devices.render();
    assert.equal(node("tablet-identify").disabled, false);
    assert.equal(node("tablet-recovery-actions").open, false, "healthy current reports collapse recovery");
    node("tablet-recovery-actions").open = true; devices.render();
    assert.equal(node("tablet-recovery-actions").open, true, "polls preserve operator disclosure choice");
    evidence = { status: "failed", text: "Failed image", showing: false }; devices.render();
    assert.equal(node("tablet-recovery-actions").open, true, "failed images show recovery immediately");
    evidence = { status: "displayed", text: "Reports current image", showing: true }; devices.render();
    const pending = devices.identify("a");
    assert.equal(requests.length, 1);
    assert.equal(requests[0][1], "/api/v3/devices/a/identify");
    assert.equal(devices.canIdentify("b"), false, "a running command blocks another Identify");
    state.selectedId = "b";
    devices.render();
    release({});
    await pending;
    assert.doesNotMatch(node("tablet-action-message").textContent, /Identify requested for Tablet a/, "completion does not overwrite another subject receipt");
    state.selectedId = "a";
    devices.render();
    assert.match(node("tablet-action-message").textContent, /Identify requested for Tablet a/);
    assert.equal(announcements.some(text => text.includes("Delivery is unconfirmed")), true);
    assert.equal(requests.length, 1, "selection changes and completion do not repeat a command");
    console.log("Identify authority, availability, refusal and captured-subject receipts passed");
}
run().catch(error => { console.error(error); process.exitCode = 1; });
