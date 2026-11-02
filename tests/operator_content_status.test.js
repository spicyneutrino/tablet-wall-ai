"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const model = require("../frontend/controller/operator-state.js");
const nodes = new Map();
const document = { activeElement: null, getElementById: node };
function node(id) {
    if (!nodes.has(id)) nodes.set(id, { dataset: {}, value: "", hidden: false, disabled: false, textContent: "", attrs: {},
        addEventListener(type, fn) { this[type] = fn; }, focus() { document.activeElement = this; },
        replaceChildren() {}, add() {}, getAttribute(key) { return this.attrs[key]; } });
    return nodes.get(id);
}
const token = { connection_id: "c", generation: "g", revision: 2, render_seq: 1, mapping_revision: "m", asset: "a" };
const config = { generation: "g", revision: 2, layout: { kind: "logical", width: 100, height: 100, placements: { t: {} } },
    scene: { content: { type: "image", asset: "a", fit: "cover" } }, runtime: { devices: { t: { online: true, protocol: 3,
        caps: ["render_ack"], mapping: { state: "ready" }, render: { state: "loading" } } } } };
const state = { layoutKind: "logical", etag: "e", etagState: "current", capabilities: {}, scene: { content: { type: "color" } }, base: config.layout };
const images = ["a", "b"].map(id => ({ id, name: id, width: 100, height: 100, thumbnail_url: "/" + id }));
let failInventory = false, release;
const context = vm.createContext({ window: { OperatorState: model }, document, Option: function () {}, performance: { now: () => 100 } });
vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-content.js"), "utf8"), context);
const content = context.window.OperatorContent.create({ state, renderStage() {}, announce() {}, showConflict() {},
    ingestConfig(result) { state.operatorConfig = result; state.scene = result.scene; },
    async api(method, path) {
        if (path === "/api/v3/images") { if (failInventory) throw Error("network"); return { images }; }
        if (path === "/api/v3/scene") return release ? await new Promise(resolve => { release.resolve = resolve; }) : config;
        throw Error(path);
    } });
(async () => {
    await content.refresh(); content.render();
    assert.equal(node("image-discard").hidden, true); assert.equal(node("restore-image").hidden, true);
    await node("image-select").change({ target: { value: "a" } });
    assert.equal(node("image-discard").hidden, false);
    node("image-discard").focus();
    await content.showSelected();
    assert.equal(document.activeElement, node("image-select"));
    assert.equal(node("image-discard").hidden, true); assert.equal(node("restore-image").hidden, false);
    assert.match(node("image-message").textContent, /Waiting for current/);
    const render = config.runtime.devices.t.render;
    Object.assign(render, { state: "displayed", current: true, expected_token: token, accepted_token: { ...token }, age_ms: 0, observed_mono: 100 });
    content.render(); assert.match(node("image-message").textContent, /confirm display/);
    render.accepted_token = { ...token, revision: 1 }; content.render(); assert.match(node("image-message").textContent, /stale/);
    render.state = "failed"; content.render(); assert.match(node("image-message").textContent, /failure/);
    config.runtime.devices.t.online = false; content.render(); assert.match(node("image-message").textContent, /offline/);
    config.runtime.devices.t.online = true; config.revision = 3; content.render(); assert.match(node("image-message").textContent, /changed after/);
    config.revision = 2;
    failInventory = true; await content.refresh(); content.render(); assert.match(node("image-message").textContent, /library unavailable/);
    await node("image-select").change({ target: { value: "a" } }); await content.showSelected(); content.render();
    assert.match(node("image-message").textContent, /library unavailable/);
    failInventory = false; await content.refresh();
    await node("image-select").change({ target: { value: "a" } }); release = {};
    const pending = content.showSelected(); await new Promise(resolve => setImmediate(resolve));
    content.previewScene({ name: "new", content: { type: "image", asset: "b" } }, "e");
    release.resolve(config); await pending;
    assert.equal(state.previewContent.asset, "b"); assert.equal(content.dirty(), true); assert.equal(node("image-discard").hidden, false);
    node("image-discard").focus(); content.discard(); assert.equal(document.activeElement, node("image-select"));
    console.log("Content status, error ownership, draft races and contextual actions passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
