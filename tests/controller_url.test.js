"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const context = vm.createContext({ window: {}, URL });
vm.runInContext(
    fs.readFileSync(path.join(__dirname, "../frontend/controller/controller-url.js"), "utf8"),
    context,
    { filename: "controller-url.js" }
);

const isLoopbackOrigin = context.window.ControllerUrl.isLoopbackOrigin;
for (const origin of [
    "http://localhost:8000",
    "http://tablet.localhost:8000",
    "http://127.0.0.1:8000",
    "http://127.42.0.2:8000",
    "http://[::1]:8000",
    "http://2130706433:8000"
]) {
    assert.equal(isLoopbackOrigin(origin), true, origin + " is local to this computer");
}

for (const origin of [
    "http://10.42.0.1:8080",
    "https://192.168.1.10:8443",
    "https://example.test"
]) {
    assert.equal(isLoopbackOrigin(origin), false, origin + " can be reached from another device");
}

assert.equal(isLoopbackOrigin("not an origin"), false);
console.log("Controller URL locality checks passed");
