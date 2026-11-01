"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const model = require("../frontend/controller/operator-state.js");
const sockets = [], requests = [], received = [], connection = {};
class Socket {
    static OPEN = 1;
    constructor() { this.readyState = 1; sockets.push(this); }
    close() { this.readyState = 3; }
}
const state = { readFence: model.readFence(), roster: {}, busy: false };
const context = vm.createContext({ window: { OperatorState: model, location: { href: "http://127.0.0.1:8080/controller/physical.html" } },
    document: { visibilityState: "visible", getElementById: () => connection }, WebSocket: Socket, URL, Date, performance: { now: () => 1000 },
    setTimeout: () => 1, clearTimeout: () => {}, setInterval: () => 1, clearInterval: () => {} });
vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-sync.js"), "utf8"), context);
const sync = context.window.OperatorSync.create({ state,
    api: () => new Promise(resolve => requests.push(resolve)),
    ingestConfig: (config, options) => { received.push({ config, options }); state.operatorConfig = config; },
    renderAll: () => {}, showConflict: () => {}, isDirty: () => false });
const config = revision => ({ revision, etag: String(revision), runtime: { devices: {} } });
const flush = () => new Promise(resolve => setImmediate(resolve));
(async () => {
    sync.start();
    assert.equal(requests.length, 1, "slow reconciliation starts after socket subscription");
    sockets[0].onmessage({ data: JSON.stringify({ type: "snapshot", config: config(8) }) });
    requests.shift()(config(1)); await flush();
    assert.deepEqual(received.map(item => item.config.revision), [8], "slower HTTP read cannot overwrite socket snapshot");
    assert.equal(received[0].options.preserveDraft, true);
    const pending = sync.reconcile();
    sockets[0].onmessage({ data: JSON.stringify({ type: "config_updated", etag: "9" }) });
    requests.shift()(config(7)); await pending; await flush();
    assert.equal(requests.length, 1, "update during fetch queues a fresh read after discarding the old response");
    requests.shift()(config(9)); await flush();
    assert.deepEqual(received.map(item => item.config.revision), [8, 9]);
    state.roster.other = { render: { state: "displayed", age_ms: 100, observed_mono: 10 } };
    sockets[0].onmessage({ data: JSON.stringify({ type: "device_updated", device: { device_id: "tablet", online: true, render: { state: "loading" } } }) });
    assert.equal(state.roster.tablet.render.state, "loading");
    assert.equal(state.operatorConfig.runtime.devices.tablet.render.state, "loading", "runtime evidence updates authoritative status without a layout write");
    assert.equal(state.roster.tablet.render.observed_mono, 1000);
    assert.equal(state.roster.other.render.observed_mono, 10, "one tablet's report cannot refresh another tablet's stale evidence");
    sockets[0].onmessage({ data: JSON.stringify({ type: "device_offline", device_id: "tablet" }) });
    assert.equal(state.roster.tablet.online, false);
    sockets[0].onmessage({ data: JSON.stringify({ type: "device_removed", device_id: "tablet" }) });
    assert.equal(state.roster.tablet, undefined);
    sync.destroy(); assert.equal(sockets[0].readyState, 3);
    console.log("Operator socket subscription, slower-read rejection, queued reconciliation and runtime events passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
