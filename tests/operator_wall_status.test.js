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

const document = { activeElement: null, createElement: () => node() };
const focusCalls = [];
function node() {
    return { children: [], dataset: {}, attrs: {}, textContent: "", hidden: false, isConnected: true,
        append(...children) { for (const child of children) { this.children.push(child); child.parent = this; } },
        contains(child) { return !!child && (child === this || this.children.some(item => item.contains(child))); },
        setAttribute(key, value) { this.attrs[key] = value; }, addEventListener() {},
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
    problemRows: new Map(), labelFor: id => "Tablet " + state.roster[id].number, revealRow() {},
    powerFor: id => stage.powerReadiness(state.roster[id], { stale: !!state.rosterError }) };
const source = fs.readFileSync(require.resolve("../frontend/controller/operator-workspace.js"), "utf8");
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf("        function renderProblems("), source.indexOf("        const powerFor =", source.indexOf("        function renderProblems("))), context);
const evidence = new Map([["a", { status: "displayed", showing: true, text: "Reports current image" }],
    ["b", { status: "failed", showing: false, text: "Image failed" }], ["c", { status: "offline", showing: false, text: "Offline" }]]);
const render = () => context.renderProblems(["a", "b", "c"], evidence);
const order = () => $("exception-strip").children.map(row => row.button.dataset.problemDevice);
render();
assert.deepEqual(order(), ["b", "c"], "header chips name failures only");
assert.equal($("wall-status-summary").textContent, "Content report issues: 2");
assert.equal($("wall-power-summary").textContent, "Screen wake lock: all 2 online tablets report denied. Browser report, not proof the screen is lit.");
assert.equal($("wall-power-summary").hidden, false);
const rows = context.problemRows, button = rows.get("b").button;
assert.equal(button.textContent, "▲ Tablet 2 wrong content");
assert.match(button.attrs["aria-label"], /Image failed.*Review recovery/);
document.activeElement = button;
render(); render();
assert.equal(document.activeElement, button, "polling keeps the exact issue button and its focus");
assert.equal(focusCalls.length, 0, "polling does not take keyboard ownership");
state.roster.b.wake_lock = "held"; render();
assert.equal($("wall-power-summary").hidden, true, "mixed wake states cannot produce a fleet claim");
assert.equal($("wall-power-summary").textContent, "");
state.rosterError = true; render();
assert.equal($("wall-power-summary").hidden, true, "stale evidence cannot produce a fleet claim");
assert.deepEqual(order(), [], "unreachable server is a separate status, not six offline tablets");
state.rosterError = false;
evidence.set("b", { showing: false, status: "unplaced", online: true, text: "Not placed" });
render(); assert.deepEqual(order(), ["c"], "Not placed is setup progress, not a failure chip");
evidence.set("c", { showing: false, status: "excluded", text: "Excluded" });
render(); assert.equal($("wall-status-summary").textContent, "Content report issues: 1");
evidence.set("b", { showing: true, status: "displayed", text: "Reports current image" });
render(); assert.equal($("wall-status-summary").textContent, "Content report issues: 0");
console.log("Failure-only header chips, retained focus and honest fleet summaries passed");
