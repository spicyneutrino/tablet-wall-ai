"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../frontend/controller/controller.js"), "utf8");
const el = Object.fromEntries([
    "alerts", "alertNoCap", "alertNoCapTitle", "alertNoCapText", "alertUnverified", "alertUnverifiedText"
].map(name => [name, { hidden: true, dataset: {} }]));
const devices = new Map();
const context = vm.createContext({
    el, devices, wall: { contentType: "image", placements: { tablet: {} } },
    compareIds: (a, b) => a.localeCompare(b), shortId: id => id
});
for (const name of ["renderCoverage", "renderNoCapAlert", "renderUnverifiedAlert", "renderCapChip"]) {
    const start = source.indexOf("    function " + name + "(");
    assert.ok(start >= 0, name + " exists");
    const end = source.indexOf("\n    }", start) + "\n    }".length;
    vm.runInContext(source.slice(start, end), context, { filename: "controller.js" });
}
let cases = 0;
for (const protocol of [3, 2, 1, undefined, 4]) {
    for (const caps of [["image", "physical"], ["physical"], [], undefined, null]) {
        for (const online of [true, false]) {
            const device = { protocol, caps, online };
            const label = JSON.stringify(device);
            devices.set("tablet", device);
            context.renderCoverage();
            const tile = { capChip: { dataset: {} }, capSep: {} };
            context.renderCapChip(tile, device);
            const supported = protocol === 2 || protocol === 3;
            const capable = supported && Array.isArray(caps) && caps.includes("image");
            const lacks = protocol === 1 || (supported && Array.isArray(caps) && !capable);
            assert.equal(el.alertNoCap.hidden, !(online && lacks), label);
            assert.equal(el.alertUnverified.hidden, online && (capable || lacks), label);
            assert.equal(el.alerts.hidden, online && capable, label);
            assert.equal(tile.capChip.hidden, false, label);
            assert.equal(tile.capChip.textContent, protocol === 1 ? "Old version"
                : capable ? "Image capable" : lacks ? "No image support" : "Image support unknown", label);
            assert.equal(tile.capChip.dataset.kind, online && capable ? "ok"
                : online && lacks ? "warn" : "dim", label);
            if (!online) {
                const note = capable ? "image cap" : protocol === 1 ? "protocol 1"
                    : lacks ? "no image cap" : "capability unknown";
                assert.ok(el.alertUnverifiedText.textContent.includes("offline · " + note), label);
            }
            cases += 1;
        }
    }
}
devices.clear();
context.renderCoverage();
assert.equal(el.alertNoCap.hidden, true);
assert.equal(el.alertUnverified.hidden, false);
assert.ok(el.alertUnverifiedText.textContent.includes("not in the roster · capability unknown"));
context.wall.contentType = "color";
const tile = { capChip: { dataset: {} }, capSep: {} };
context.renderCapChip(tile, { protocol: 3, caps: ["image"], online: true });
assert.equal(tile.capChip.hidden, true);
assert.equal(tile.capSep.hidden, true);
console.log("Controller image capability contracts passed (" + cases + " roster cases, missing device, non-image scene)");
