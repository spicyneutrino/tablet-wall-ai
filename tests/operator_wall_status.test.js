"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const model = require("../frontend/controller/operator-state.js");
const stage = require("../frontend/controller/operator-stage.js");
const entry = (id, wake_lock = "denied", online = true, stale = false) => ({ id, online,
    power: stage.powerReadiness({ online, wake_lock }, { stale }) });
const denied = [entry("a"), entry("b")];
assert.deepEqual(stage.fleetPower(denied), { state: "denied", label: "denied", count: 2 });
assert.deepEqual(stage.fleetPower([...denied, entry("c", "held", false)]), { state: "denied", label: "denied", count: 2 });
assert.equal(stage.fleetPower([entry("a"), entry("b", "released")]), null);
assert.equal(stage.fleetPower([]), null);
assert.equal(stage.fleetPower([entry("a")]), null);
assert.equal(stage.fleetPower([entry("a", "held"), entry("b", "held")]), null);
assert.deepEqual(stage.fleetPower([entry("a", "unknown"), entry("b", "unknown")]), { state: "unknown", label: "unknown", count: 2 });
assert.equal(stage.fleetPower([entry("a"), entry("b", "denied", true, true)]), null);
assert.equal(stage.fleetPower([entry("a", "unsupported"), entry("b", "unsupported")]), null);
for (const status of ["offline", "stale", "failed", "unplaced"]) assert.equal(model.needsAttention({ status, showing: false }), true);
assert.equal(model.needsAttention({ status: "displayed", showing: true }), false);
assert.equal(model.needsAttention({ status: "excluded", showing: false }), false);

const document = { activeElement: null, body: { dataset: { view: "tools" } }, createElement: () => node() };
const focusCalls = [];
function node() {
    return { children: [], dataset: {}, attrs: {}, listeners: {}, textContent: "", hidden: false, isConnected: true,
        append(...children) { for (const child of children) { this.children.push(child); child.parent = this; } },
        contains(child) { return !!child && (child === this || this.children.some(item => item.contains(child))); },
        setAttribute(key, value) { this.attrs[key] = value; },
        addEventListener(event, listener) { this.listeners[event] = listener; },
        click() { if (this.listeners.click) this.listeners.click(); },
        insertBefore(child, before) {
            if (child.parent) {
                if (child.contains(document.activeElement)) document.activeElement = null;
                child.parent.children.splice(child.parent.children.indexOf(child), 1);
            }
            const index = before ? this.children.indexOf(before) : this.children.length;
            this.children.splice(index, 0, child); child.parent = this;
        },
        remove() { this.parent.children.splice(this.parent.children.indexOf(this), 1); this.isConnected = false; },
        focus(options) { focusCalls.push({ button: this, options }); document.activeElement = this; }
    };
}
const nodes = new Map();
const $ = id => { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); };
$("wall-health").textContent = "1 of 3 showing the current image";
const state = { operatorConfig: { layout: { placements: { a: {}, b: {}, c: {} } } }, roster: { a: { number: 1, online: true, wake_lock: "denied" },
    b: { number: 2, online: true, wake_lock: "denied" }, c: { number: 3, online: false, wake_lock: "released" } }, deviceLabels: {} };
const context = { document, state, window: { OperatorState: model, OperatorStage: stage }, $, setTextIfChanged: (node, text) => { node.textContent = text; },
    phone: { matches: false }, problemRows: new Map(), labelFor: id => "Tablet " + state.roster[id].number, revealRow() {},
    powerFor: id => stage.powerReadiness(state.roster[id], { stale: !!state.rosterError }) };
const source = fs.readFileSync(require.resolve("../frontend/controller/operator-workspace.js"), "utf8");
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf("        function renderProblems("), source.indexOf("        const powerFor =", source.indexOf("        function renderProblems("))), context);
const evidence = new Map([["a", { status: "displayed", showing: true, text: "Reports current image" }],
    ["b", { status: "failed", showing: false, text: "Image failed" }], ["c", { status: "offline", showing: false, text: "Offline" }]]);
const render = () => context.renderProblems(["a", "b", "c"], evidence);
const order = () => $("exception-strip").children.map(row => row.button.dataset.problemDevice);
const kinds = () => $("exception-strip").children.map(row => row.dataset.status);
render();
assert.deepEqual(kinds(), ["more"], "several failures collapse into one header summary");
assert.deepEqual(order(), ["b"], "the summary reveals the first failing tablet");
assert.equal($("wall-status-summary").textContent, "Content report issues: 2");
assert.equal($("wall-power-summary").textContent, "", "wake-lock reports belong only in the selected Tablet panel");
const rows = context.problemRows, button = rows.get("summary").button;
assert.equal(button.textContent, "▲ 2 tablets need attention");
assert.match(button.attrs["aria-label"], /^2 tablets need attention\. Review the first\.$/);
document.activeElement = button;
render(); render();
assert.equal(document.activeElement, button, "polling keeps the exact summary button and its focus");
assert.equal(focusCalls.length, 0, "polling does not take keyboard ownership");
state.roster.b.wake_lock = "held"; render();
assert.equal($("wall-power-summary").textContent, "", "mixed wake states cannot produce a fleet claim");
state.rosterError = true; render();
assert.equal($("wall-power-summary").textContent, "", "stale evidence cannot produce a fleet claim");
assert.deepEqual(order(), [], "unreachable server is a separate status, not six offline tablets");
state.rosterError = false;
evidence.set("b", { showing: false, status: "unplaced", online: true, text: "Not placed" });
render(); assert.deepEqual(order(), ["c"], "Not placed is setup progress, not a failure chip");
const single = rows.get("summary").button;
assert.equal(single.textContent, "▲ Tablet 3 offline", "a single failure is named on the summary row");
assert.match(single.attrs["aria-label"], /Offline.*Review recovery/);
single.focus();
evidence.set("b", { status: "failed", showing: false, text: "Image failed" }); render();
assert.equal(rows.get("summary").button, single, "rising from one to two failures reuses the same button");
assert.equal(single.textContent, "▲ 2 tablets need attention");
evidence.set("b", { showing: false, status: "unplaced", online: true, text: "Not placed" }); render();
assert.equal(single.textContent, "▲ Tablet 3 offline");
assert.equal(document.activeElement, single, "focus survives the one, two, one transitions");
evidence.set("c", { showing: false, status: "excluded", text: "Excluded" });
render(); assert.equal($("wall-status-summary").textContent, "Content report issues: 1");
evidence.set("b", { showing: true, status: "displayed", text: "Reports current image" });
render(); assert.equal($("wall-status-summary").textContent, "Content report issues: 0");
for (const id of ["a", "b", "c"]) evidence.set(id, { status: "offline", showing: false, text: "Offline" });
context.phone.matches = true;
render();
assert.deepEqual(kinds(), ["more"], "phone shows the same single summary");
const again = rows.get("summary").button;
assert.equal(again.textContent, "▲ 3 tablets need attention");
assert.match(again.attrs["aria-label"], /Open Tablets to review all/);
let tabletNavigations = 0;
$("nav-tablets").addEventListener("click", () => { tabletNavigations++; document.body.dataset.view = "tablets"; });
again.click(); again.click();
assert.equal(document.body.dataset.view, "tablets", "every failing tablet remains reachable from the count");
assert.equal(tabletNavigations, 1, "repeated count activation keeps Tablets open");
const summary = again;
summary.focus();
const focusCount = focusCalls.length;
context.phone.matches = false; render(); render();
assert.equal(document.activeElement, summary, "responsive changes keep the summary button and its focus");
assert.equal(focusCalls.length, focusCount, "polling does not move focus");
console.log("Failure-only header chips, phone failure counts, retained focus and Tablet-panel-only wake reports passed");
