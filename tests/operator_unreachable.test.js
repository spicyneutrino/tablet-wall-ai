"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const model = require("../frontend/controller/operator-state.js");

function harness(failure) {
    const state = { readFence: model.readFence(), roster: {}, busy: false, rosterUnreachable: false };
    const context = vm.createContext({ window: { OperatorState: model, location: { href: "http://127.0.0.1:8080/controller/physical.html" } },
        document: { visibilityState: "visible", getElementById: () => ({}) }, WebSocket: class { static OPEN = 1; }, URL, Date,
        performance: { now: () => 1000 }, setTimeout: () => 1, clearTimeout: () => {}, setInterval: () => 1, clearInterval: () => {} });
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-sync.js"), "utf8"), context);
    const sync = context.window.OperatorSync.create({ state, api: () => Promise.reject(failure),
        ingestConfig: () => {}, renderAll: () => {}, showConflict: () => {}, isDirty: () => false });
    return { state, sync };
}

function apiError(status, message) { return Object.assign(new Error(message), { status }); }

(async () => {
    const network = harness(apiError(0, "Connection lost."));
    await network.sync.reconcile();
    assert.equal(network.state.rosterUnreachable, true, "a transport failure marks the server unreachable");

    const server = harness(apiError(503, "503 unavailable"));
    await server.sync.reconcile();
    assert.equal(server.state.rosterUnreachable, false, "an HTTP error from a reachable server is stale, not unreachable");
    assert.equal(server.state.rosterError, "503 unavailable");

    const reworded = harness(apiError(0, "Le serveur ne répond pas"));
    await reworded.sync.reconcile();
    assert.equal(reworded.state.rosterUnreachable, true, "the decision does not depend on message wording");
    console.log("operator_unreachable: ok");
})().catch(error => { console.error(error); process.exit(1); });
