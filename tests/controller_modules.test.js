"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const context = vm.createContext({ window: {} });
function load(name) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../frontend/controller", name), "utf8"), context, { filename: name });
}
function plain(value) { return JSON.parse(JSON.stringify(value)); }
load("controller-geometry.js");
const geometry = context.window.ControllerGeometry;
assert.deepEqual(plain(geometry.normalizePlacement({ x: "2", y: 3, w: 10, h: 20, bezel: { left: "1" } })), {
    x: 2, y: 3, w: 10, h: 20, bezel: { top: 0, right: 0, bottom: 0, left: 1 }
});
assert.equal(geometry.normalizePlacement({ x: "invalid" }), null);
assert.deepEqual(plain(geometry.visibleRect({ x: 2, y: 3, w: 10, h: 20, bezel: { top: 1, right: 2, bottom: 3, left: 4 } })), { x: 6, y: 4, w: 4, h: 16 });
assert.equal(geometry.aspectOf(1, 0), null);
assert.equal(geometry.isAspectMismatch(null), false);
assert.equal(geometry.isAspectMismatch(0.01), false);
assert.equal(geometry.isAspectMismatch(0.011), true);
assert.equal(geometry.sceneContentType({ scene: { content: { type: " future " } } }), "future");
assert.equal(geometry.isSettableContent("image"), false);
assert.equal(geometry.contentLabel("future"), "Unsupported content: future");
assert.equal(geometry.deviceCaps({}).image, null);
assert.equal(geometry.deviceCaps({ caps: [] }).image, false);
console.log("Controller module contracts passed");
