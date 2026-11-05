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
