"use strict";
const assert = require("node:assert/strict");
const { create } = require("../frontend/controller/operator-devices.js");
const nodes = new Map();
function node(id) {
    if (!nodes.has(id)) nodes.set(id, {
        dataset: {}, value: "", textContent: "", options: [], listeners: {}, hidden: false, isConnected: true,
        addEventListener(event, handler) { this.listeners[event] = handler; },
        replaceChildren() {}, append() {}, add(value) { this.options.push(value); },
        getClientRects() { return [1]; }, focus() { document.activeElement = this; }
    });
    return nodes.get(id);
}
global.document = { getElementById: node, createElement: node, querySelector: () => null, activeElement: null, body: {} };
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
const forms = require("../frontend/controller/operator-forms.js").create();
const devices = create({ state, tabletForms: forms,
    labelFor: id => "Tablet " + id, announce: text => announcements.push(text),
    api: (...args) => { requests.push(args); return new Promise(resolve => { release = resolve; }); },
    refreshRoster: async () => {}, profileFor: () => null, calibrationFor: () => null });
const flush = () => new Promise(resolve => setImmediate(resolve));
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
    state.roster.a.online = false;
    evidence = { status: "offline", text: "Offline", showing: false }; devices.render();
    assert.equal(node("tablet-recovery-actions").hidden, true, "offline recovery does not offer an empty disclosure");
    assert.equal(node("tablet-recovery").hidden, false, "offline physical recovery guidance remains visible");
    assert.match(node("tablet-recovery").textContent, /check power/);
    state.roster.a.online = true;
    evidence = { status: "failed", text: "Failed image", showing: false }; devices.render();
    assert.equal(node("tablet-recovery-actions").hidden, false, "online failures retain actionable recovery");
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

    /* Per-device power is a separate, independently fresh fact. */
    state.etagState = "current";
    state.selectedId = "a";
    state.roster.a.online = true;
    state.roster.a.wake_lock = "denied";
    state.rosterError = null;
    evidence = { status: "displayed", text: "Reports current image", showing: true };
    const beforeAnnouncements = announcements.length;
    devices.render();
    assert.equal(node("tablet-evidence").textContent, "Power: denied");
    assert.equal(node("tablet-evidence").dataset.powerWarning, "true");
    assert.equal(node("tablet-recovery").hidden, false, "a painted tablet still warns denied power");
    assert.match(node("tablet-recovery").textContent, /denied/);
    assert.match(node("tablet-recovery").textContent, /cannot wake/);
    assert.match(node("tablet-provenance").textContent, /Power readiness: Power: denied/);
    assert.match(node("tablet-retry-image").title, /does not wake/);
    assert.match(node("tablet-reconnect").title, /does not wake/);
    assert.notEqual(node("tablet-retry-image").title, node("tablet-reconnect").title, "Retry image and Reconnect describe different actions");
    devices.render();
    assert.equal(announcements.length, beforeAnnouncements, "a heartbeat re-render does not announce");

    state.roster.a.wake_lock = "held";
    evidence = { status: "stale", text: "Previous paint · current image unconfirmed", showing: false };
    devices.render();
    assert.match(node("tablet-evidence").textContent, /Previous paint/);
    assert.match(node("tablet-evidence").textContent, /Power: held/);
    assert.equal(node("tablet-evidence").dataset.status, "stale");
    assert.equal(node("tablet-evidence").dataset.powerWarning, "false");
    assert.match(node("tablet-recovery").textContent, /does not confirm paint/);
    assert.match(node("tablet-recovery").textContent, /not proof/);

    delete state.roster.a.wake_lock;
    evidence = { status: "displayed", text: "Reports current image", showing: true };
    devices.render();
    assert.equal(node("tablet-evidence").textContent, "Power: unknown");
    assert.equal(node("tablet-recovery").hidden, true, "unknown power alone does not fabricate a warning");

    state.rosterError = "503 unavailable";
    devices.render();
    assert.match(node("tablet-evidence").textContent, /Last known power unknown/);
    assert.match(node("tablet-evidence").textContent, /status stale/);
    assert.equal(node("tablet-evidence").dataset.powerStale, "true");

    state.rosterError = null;
    state.roster.a.wake_lock = "unsupported";
    devices.render();
    assert.equal(node("tablet-evidence").textContent, "Power: unsupported");
    assert.equal(node("tablet-recovery").hidden, true, "unsupported is reported without a false power warning");
    state.roster.a.wake_lock = "insecure";
    devices.render();
    assert.equal(node("tablet-evidence").textContent, "Power: insecure origin");
    assert.equal(node("tablet-recovery").hidden, false);
    assert.match(node("tablet-recovery").textContent, /trusted HTTPS origin/);
    state.roster.a.wake_lock = "released";
    devices.render();
    assert.equal(node("tablet-recovery").hidden, false);
    assert.match(node("tablet-recovery").textContent, /foreground/);

    /* Retry image and Reconnect stay separate commands with separate consequences. */
    state.roster.a.wake_lock = "held";
    state.roster.a.online = true;
    state.etagState = "current";
    evidence = { status: "displayed", text: "Reports current image", showing: true };
    devices.render();
    const beforeRequests = requests.length;
    node("tablet-retry-image").listeners.click();
    assert.equal(requests.length, beforeRequests + 1);
    assert.equal(requests[beforeRequests][1], "/api/v3/devices/a/retry-image");
    release({}); await flush(); await flush();
    assert.match(node("tablet-action-message").textContent, /Image retry requested/);
    assert.match(node("tablet-action-message").textContent, /does not wake/);
    node("tablet-reconnect").listeners.click();
    assert.equal(requests.length, beforeRequests + 2);
    assert.equal(requests[beforeRequests + 1][1], "/api/v3/devices/a/reconnect");
    release({}); await flush(); await flush();
    assert.match(node("tablet-action-message").textContent, /Reconnect requested/);
    assert.match(node("tablet-action-message").textContent, /does not wake/);

    /* A failed command restores the invoking control, and a removed device keeps its draft. */
    state.roster.a.online = true;
    state.roster.a.caps = ["identify"];
    state.roster.a.wake_lock = "held";
    state.etagState = "current";
    evidence = { status: "displayed", text: "Reports current image", showing: true };
    devices.render();
    node("tablet-identify").disabled = false;
    node("tablet-identify").focus();
    const focusBefore = requests.length;
    const identifyPending = devices.identify("a");
    assert.equal(requests.length, focusBefore + 1);
    document.activeElement = document.body;
    release(Promise.reject(new Error("network failed")));
    await identifyPending;
    assert.equal(document.activeElement, node("tablet-identify"), "a failed command restores focus to its invoking control");

    devices.render();
    forms.edit("a", "name", { name: "Draft name" }, state.etag);
    node("tablet-label").value = "Draft name";
    delete state.roster.a;
    devices.render();
    assert.equal(forms.get("a", "name").dirty, true, "a removed device keeps its unsaved draft");
    assert.equal(forms.get("a", "name").values.name, "Draft name");
    assert.equal(node("tablet-label").value, "Draft name");
    console.log("Mixed sheet power, freshness, distinct recovery actions and draft focus passed");
}
run().catch(error => { console.error(error); process.exitCode = 1; });
