"use strict";
const assert = require("node:assert/strict");
const { create } = require("../frontend/controller/operator-devices.js");
const nodes = new Map();
function makeNode(tagName = "div") {
    const classes = new Set();
    const item = {
        tagName: String(tagName).toUpperCase(), dataset: {}, value: "", options: [], listeners: {}, hidden: false,
        isConnected: true, parentElement: null, children: [], text: "",
        classList: { toggle(name, enabled) { if (enabled) classes.add(name); else classes.delete(name); }, contains(name) { return classes.has(name); } },
        matches(selector) { return selector === ":valid" && this.valid !== false; },
        addEventListener(event, handler) { this.listeners[event] = handler; },
        append(...items) { items.forEach(child => { child.parentElement = this; this.children.push(child); }); },
        replaceChildren(...items) { this.children = []; items.forEach(child => this.append(child)); },
        add(value) { this.options.push(value); },
        getClientRects() { return [1]; },
        focus() { global.document.activeElement = this; }
    };
    Object.defineProperty(item, "textContent", {
        get() { return this.children.length ? this.children.map(child => child.textContent).join(" ") : this.text; },
        set(value) { this.text = String(value); this.children = []; }
    });
    return item;
}
function node(id) {
    if (!nodes.has(id)) nodes.set(id, makeNode(id));
    return nodes.get(id);
}
global.document = { getElementById: node, createElement: makeNode, createTextNode: text => ({ textContent: text }),
    querySelector: () => null, activeElement: null, body: {} };
global.Option = function (text, value) { this.textContent = text; this.value = value; };
global.window = { OperatorState: {
    entries: layout => layout.placements || layout.slots,
    tabletState: () => evidence,
    compareIds: (roster, labels, a, b) => a.localeCompare(b)
} };
let evidence = { status: "displayed", text: "Reports current image", showing: true };
const state = { selectedId: "a", roster: { a: { online: true, caps: ["identify"] }, b: { online: true, caps: ["identify"] } },
    base: { kind: "logical", slots: {} }, draft: { slots: {} }, layoutKind: "logical", etagState: "current", savedLayouts: [] };
let release;
const requests = [], announcements = [], selections = [];
const forms = require("../frontend/controller/operator-forms.js").create();
const devices = create({ state, tabletForms: forms,
    labelFor: id => "Tablet " + id, announce: text => announcements.push(text),
    api: (...args) => { requests.push(args); return new Promise(resolve => { release = resolve; }); },
    refreshRoster: async () => {}, profileFor: () => null, calibrationFor: () => null,
    selectTablet: id => { selections.push(id); state.selectedId = id; devices.render(); } });
const flush = () => new Promise(resolve => setImmediate(resolve));
const DENIED_RECOVERY = "The browser denied the screen wake lock. Allow it in the browser and check the trusted origin, Auto-Lock, charging and kiosk settings. The operator cannot wake the tablet remotely.";
const sentences = text => (String(text).match(/[^.!?]+[.!?]+/g) || []).map(value => value.trim()).sort();
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
    assert.equal(node("tablet-label-save").classList.contains("btn-primary"), false, "clean names have no primary emphasis");
    node("tablet-label").value = "Desk tablet";
    node("tablet-label").listeners.input();
    assert.equal(node("tablet-label-save").classList.contains("btn-primary"), true, "a dirty valid name is primary");
    node("tablet-label-form").valid = false;
    node("tablet-label").listeners.input();
    assert.equal(node("tablet-label-save").classList.contains("btn-primary"), false, "invalid names are not primary");
    assert.equal(node("tablet-label-save").disabled, false, "emphasis does not change existing availability");
    node("tablet-label-form").valid = true;
    devices.render();
    assert.equal(node("tablet-label-save").classList.contains("btn-primary"), true, "poll rendering preserves dirty valid emphasis");
    node("tablet-label-discard").listeners.click();
    assert.equal(node("tablet-label-save").classList.contains("btn-primary"), false, "discard restores the clean treatment");
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
    assert.equal(node("tablet-evidence").textContent, "Wake lock: denied");
    assert.equal(node("tablet-evidence").dataset.powerWarning, "true");
    assert.equal(node("tablet-recovery").hidden, false, "a painted tablet still warns denied power");
    assert.equal(node("tablet-recovery").children.length, 3, "recovery guidance is three readable parts");
    assert.deepEqual(node("tablet-recovery").children.map(part => part.tagName), ["P", "P", "P"]);
    assert.equal(node("tablet-recovery").textContent, DENIED_RECOVERY, "the split keeps the exact pre-change words in order");
    assert.match(node("tablet-recovery").textContent, /denied/);
    assert.match(node("tablet-recovery").textContent, /cannot wake/);
    assert.match(node("tablet-provenance").textContent, /Wake lock readiness: denied/);
    assert.match(node("tablet-retry-image").title, /does not wake/);
    assert.match(node("tablet-reconnect").title, /does not wake/);
    assert.notEqual(node("tablet-retry-image").title, node("tablet-reconnect").title, "Retry image and Reconnect describe different actions");
    devices.render();
    assert.equal(announcements.length, beforeAnnouncements, "a heartbeat re-render does not announce");

    state.roster.a.wake_lock = "held";
    evidence = { status: "stale", text: "Previous paint · current image unconfirmed", showing: false };
    devices.render();
    assert.match(node("tablet-evidence").textContent, /Previous paint/);
    assert.match(node("tablet-evidence").textContent, /Wake lock: held/);
    assert.equal(node("tablet-evidence").dataset.status, "stale");
    assert.equal(node("tablet-evidence").dataset.powerWarning, "false");
    assert.match(node("tablet-recovery").textContent, /does not confirm paint/);
    assert.match(node("tablet-recovery").textContent, /not proof/);

    evidence = require("../frontend/controller/operator-state.js").tabletState({
        layout: { kind: "physical", slots: { a: { profile_revision: 1, calibration_revision: 1 } } },
        runtime: { devices: { a: { online: true, mapping: { state: "ready", profile_revision: 2, calibration_revision: 1 } } } }
    }, "a", performance.now());
    devices.render();
    assert.match(node("tablet-recovery").textContent, /measurements/);
    assert.doesNotMatch(node("tablet-recovery").textContent, /retry the image/);
    assert.equal(node("open-tablet-measurements").hidden, false, "mapping revision staleness exposes measurements recovery");

    state.roster.a.online = false;
    state.roster.a.last_seen = "2026-11-01T12:00:00Z";
    evidence = { status: "offline", text: "Offline · spot reserved", showing: false };
    devices.render();
    assert.match(node("tablet-evidence").textContent, /Last known wake lock held/);
    assert.equal(node("tablet-evidence").dataset.powerStale, "true");
    assert.match(node("tablet-recovery").textContent, /Tablet is offline.*last known report/);
    assert.doesNotMatch(node("tablet-recovery").textContent, /browser reports the screen wake lock held/);
    assert.equal(node("tablet-recovery").children.length, 3, "offline recovery also has three readable parts");
    const stamp = "Last checked " + new Date("2026-11-01T12:00:00Z").toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) + ".";
    const offlineSentences = [
        "On the tablet, check power, keep its screen awake, join the wall network and reopen the tablet page in its existing browser.",
        "The server cannot wake a powered-off or sleeping tablet.",
        "Tablet is offline; this is the last known report.",
        stamp,
        "Last known browser wake-lock state: held.",
        "Screen wake locks are browser reports, not proof the operating system will keep the screen on.",
        "Check Auto-Lock, charging and kiosk settings; an insecure origin cannot take a wake lock, so open the wall over its trusted HTTPS origin.",
        "The operator cannot wake a sleeping tablet remotely."
    ];
    assert.deepEqual(sentences(node("tablet-recovery").textContent), offlineSentences.slice().sort(),
        "splitting the stale offline guidance loses no sentence and rewords none");
    state.roster.a.online = true;

    delete state.roster.a.wake_lock;
    evidence = { status: "displayed", text: "Reports current image", showing: true };
    devices.render();
    assert.equal(node("tablet-evidence").textContent, "Wake lock: unknown");
    assert.equal(node("tablet-recovery").hidden, true, "unknown power alone does not fabricate a warning");

    state.rosterError = "503 unavailable";
    devices.render();
    assert.match(node("tablet-evidence").textContent, /Last known wake lock unknown/);
    assert.match(node("tablet-evidence").textContent, /status stale/);
    assert.equal(node("tablet-evidence").dataset.powerStale, "true");

    state.rosterError = null;
    state.roster.a.wake_lock = "unsupported";
    devices.render();
    assert.equal(node("tablet-evidence").textContent, "Wake lock: unsupported");
    assert.equal(node("tablet-recovery").hidden, true, "unsupported is reported without a false power warning");
    state.roster.a.wake_lock = "insecure";
    devices.render();
    assert.equal(node("tablet-evidence").textContent, "Wake lock: insecure origin");
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

    /* The offline tablet points at the replacement review without sending a request. */
    state.etagState = "current";
    state.selectedId = "a";
    state.base = { kind: "logical", slots: {} };
    state.roster = { a: { online: false }, b: { online: true }, c: { online: true } };
    evidence = { status: "offline", text: "Offline", showing: false };
    state.rosterError = null;
    const beforePointerRequests = requests.length, beforeSelections = selections.length;
    devices.render();
    const pointer = node("tablet-replacement-pointer");
    assert.equal(pointer.hidden, false, "an offline selected tablet with online unplaced tablets offers the pointer");
    assert.equal(pointer.children[0].textContent, "Review replacement with a new tablet");
    assert.equal(pointer.children[0].className, "btn");
    pointer.children[0].listeners.click();
    assert.deepEqual(selections.slice(beforeSelections), ["c"], "the newest online unplaced tablet is selected");
    assert.equal(document.activeElement, node("replacement-old"), "the replacement offer's first control receives focus");
    assert.equal(requests.length, beforePointerRequests, "the pointer sends no request");
    state.roster.b.online = false;
    state.roster.c.online = false;
    state.selectedId = "a";
    devices.render();
    assert.equal(node("tablet-replacement-pointer").hidden, true, "no online unplaced tablet hides the pointer");
    state.roster = { a: { online: false }, b: { online: true } };
    state.base = { kind: "logical", slots: { b: {} } };
    devices.render();
    assert.equal(node("tablet-replacement-pointer").hidden, true, "an online tablet that is placed hides the pointer");
    state.base = { kind: "logical", slots: {} };
    state.selectedId = "b";
    devices.render();
    assert.equal(node("tablet-replacement-pointer").hidden, true, "an online selected tablet does not offer the pointer");

    /* Measurements stay reachable whenever the wall is measured. */
    state.selectedId = "a";
    state.layoutKind = "logical";
    state.base = { kind: "logical", slots: {} };
    node("grid-kind").value = "logical";
    evidence = { status: "displayed", text: "Reports current image", showing: true };
    devices.render();
    assert.equal(node("open-tablet-measurements").hidden, true, "a logical wall hides measurements for a healthy selected tablet");
    state.layoutKind = "physical";
    devices.render();
    assert.equal(node("open-tablet-measurements").hidden, false, "an applied measured layout keeps measurements reachable");
    state.layoutKind = "logical";
    state.base = { kind: "physical", slots: {} };
    devices.render();
    assert.equal(node("open-tablet-measurements").hidden, false, "an applied physical layout keeps measurements reachable");
    state.base = { kind: "logical", slots: {} };
    node("grid-kind").value = "physical";
    devices.render();
    assert.equal(node("open-tablet-measurements").hidden, false, "a physical grid kind keeps measurements reachable");
    node("grid-kind").value = "logical";
    evidence = { status: "viewport_mismatch", text: "Return to the calibrated rotation", showing: false };
    devices.render();
    assert.equal(node("open-tablet-measurements").hidden, false, "a blocked mapping keeps measurements reachable");
    evidence = { status: "displayed", text: "Reports current image", showing: true };
    state.selectedId = "a";
    state.roster.a.online = true;
    state.rosterCheckedAt = "2026-11-01T12:00:00Z";
    for (const [wake, label] of Object.entries({ held: "held", released: "released", denied: "denied", insecure: "insecure origin", unsupported: "unsupported", unknown: "unknown" })) {
        state.roster.a.wake_lock = wake;
        for (const stale of [false, true]) {
            state.rosterError = stale ? "offline" : null;
            devices.render();
            const provenance = node("tablet-provenance").textContent;
            const power = require("../frontend/controller/operator-stage.js").powerReadiness(state.roster.a, { stale, checkedAt: state.rosterCheckedAt });
            assert.equal(provenance.slice(provenance.indexOf("Wake lock readiness:")),
                "Wake lock readiness: " + (stale ? "last known " : "") + label + (stale ? " · status stale" : "") + ". " + power.guidance);
            assert.equal(provenance.match(/Wake lock readiness:/g).length, 1);
        }
    }
    state.rosterError = null;
    state.selectedId = null;
    devices.render();
    assert.equal(node("open-tablet-measurements").hidden, true, "no selected tablet hides measurements");
    console.log("Mixed sheet power, freshness, distinct recovery actions and draft focus passed");
}
run().catch(error => { console.error(error); process.exitCode = 1; });
