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
    rosterRows: new Map(), stripRows: new Map(), labelFor: id => id, revealRow() {},
    orderedIds: ids => ids.slice().sort((a, b) => model.compareIds(state.roster, {}, a, b)),
    positionTag: id => "#" + state.roster[id].number, shortEvidence: item => item.text,
    powerFor: id => stage.powerReadiness(state.roster[id], { stale: !!state.rosterError }),
    powerText: power => power.warning || power.stale || power.state === "unknown" ? power.label : "" };
const source = fs.readFileSync(require.resolve("../frontend/controller/operator-workspace.js"), "utf8");
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf("        function renderExceptionRail("), source.indexOf("        async function resolve(")), context);
const evidence = new Map([["a", { status: "displayed", showing: true, text: "Reports current image" }],
    ["b", { status: "failed", showing: false, text: "Image failed" }], ["c", { status: "offline", showing: false, text: "Offline" }]]);
const render = () => context.renderExceptionRail(["c", "a", "b"], evidence);
const order = () => $("exception-roster").children.map(row => row.dataset.deviceId);
render();
assert.deepEqual(order(), ["b", "c", "a"]);
assert.equal($("wall-status-summary").textContent, "Content report issues: 2");
assert.equal($("wall-status-summary").textContent.includes("showing the current"), false);
assert.equal($("wall-power-summary").textContent, "Screen wake lock: all 2 online tablets report denied. Browser report, not proof the screen is lit.");
assert.equal($("wall-power-summary").hidden, false);
const rows = context.rosterRows;
assert.equal(rows.get("a").power.hidden, true);
assert.equal(rows.get("c").power.hidden, false);
assert.equal(rows.get("a").dataset.powerState, "denied");
assert.equal(rows.get("a").button.attrs["aria-label"], "a, Reports current image, Wake lock: denied. Review recovery.");
const healthyButton = rows.get("a").button;
document.activeElement = healthyButton;
evidence.set("a", { status: "failed", showing: false, text: "Image failed" });
render();
assert.deepEqual(order(), ["a", "b", "c"]);
assert.equal(document.activeElement, healthyButton);
assert.equal(focusCalls.length, 1);
assert.equal(focusCalls[0].button, healthyButton);
assert.equal(focusCalls[0].options.preventScroll, true);
render(); assert.equal(focusCalls.length, 1);
state.roster.b.wake_lock = "held"; render();
assert.equal(rows.get("a").power.hidden, false);
assert.equal($("wall-power-summary").hidden, true);
assert.equal($("wall-power-summary").textContent, "");
state.roster.b.wake_lock = "denied"; state.rosterError = true; render();
assert.equal($("wall-power-summary").hidden, true);
assert.equal(rows.get("a").power.hidden, false);
evidence.set("a", { showing: true, status: "displayed", text: "Reports current image" });
evidence.set("b", { showing: true, status: "displayed", text: "Reports current image" });
render(); assert.equal($("wall-status-summary").textContent, "Content report issues: 1");
evidence.set("c", { showing: false, status: "excluded", text: "Excluded" });
render(); assert.equal($("wall-status-summary").textContent, "Content report issues: 0");
console.log("Wall status fleet power, attention order, retained focus and single summary pass");
