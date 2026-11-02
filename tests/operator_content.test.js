"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const model = require("../frontend/controller/operator-state.js");
const nodes = new Map();
function node(id) {
    if (!nodes.has(id)) nodes.set(id, { dataset: {}, value: "", hidden: false, disabled: false, textContent: "", attrs: {},
        addEventListener(type, fn) { this[type] = fn; },
        replaceChildren() {}, add() {}, getAttribute(key) { return this.attrs[key]; }, setAttribute(key, value) { this.attrs[key] = value; } });
    return nodes.get(id);
}
const state = { layoutKind: "logical", etag: "current", etagState: "current", configLoaded: true,
    capabilities: { uploads: false }, scene: { content: { type: "color" } },
    draft: { kind: "logical", width: 1000, height: 500, placements: {} } };
const image = { id: "sha256:pattern", name: "black.png", width: 64, height: 64,
    source: "curated", url: "/assets/sha256:pattern", thumbnail_url: "/assets/sha256:pattern", etag: "current" };
const calls = [];
let releaseInventory;
const oldInventory = new Promise(resolve => { releaseInventory = resolve; });
const context = vm.createContext({ window: { OperatorState: model }, document: { getElementById: node }, Option: function () {} });
vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-content.js"), "utf8"), context);
const content = context.window.OperatorContent.create({ state, renderStage() {}, announce() {}, showConflict() {}, isDirty: () => false,
    ingestConfig(config) { state.scene = config.scene; },
    async api(method, path, body) {
        calls.push({ method, path, body });
        if (path === "/api/v3/test-pattern") return image;
        if (path === "/api/v3/images") return oldInventory;
        if (path === "/api/v3/scene") return { scene: { content: body.content } };
        throw new Error("unexpected route " + path);
    } });
(async () => {
    const refresh = content.refresh();
    await node("pattern-black").click();
    assert.deepEqual(calls.map(call => call.path), ["/api/v3/images", "/api/v3/test-pattern", "/api/v3/scene"]);
    assert.equal(calls[2].body.content.asset, image.id, "the generated flat image DTO is shown without fixture-only aliases");
    assert.equal(calls[2].body.content.fit, "contain");
    assert.equal(state.activeImageUnavailableId, null, "the new pattern is inventoried before its scene is shown");
    assert.ok(!node("active-image").textContent.includes("Unavailable"));
    assert.ok(node("active-image").textContent.includes("black.png"));
    releaseInventory({ images: [] });
    await refresh;
    assert.equal(state.activeImageUnavailableId, null, "an older inventory read cannot erase a published pattern");
    assert.ok(node("active-image").textContent.includes("black.png"));
    assert.ok(!node("active-image").textContent.includes("Unavailable"));
    let resolveOutput, waitForResolution = false;
    const next = { ...image, id: "sha256:next", name: "next.png" };
    const racing = context.window.OperatorContent.create({ state, renderStage() {}, announce() {}, showConflict() {},
        resolveOutput() { return waitForResolution ? new Promise(resolve => { resolveOutput = resolve; }) : true; },
        ingestConfig(config) { state.scene = config.scene; },
        async api(method, path, body) {
            if (path === "/api/v3/images") return { images: [image, next] };
            if (path === "/api/v3/scene") return { scene: { content: body.content } };
            throw new Error("unexpected route " + path);
        } });
    await racing.refresh();
    await node("image-select").change({ target: { value: image.id } });
    waitForResolution = true;
    const showing = racing.showSelected();
    racing.previewScene({ name: "Later", content: { type: "image", asset: next.id } }, state.etag);
    resolveOutput(true); await showing;
    assert.equal(state.scene.content.asset, image.id, "Show retains the image captured when the command was requested");
    assert.equal(state.previewContent.asset, next.id, "completion after draft resolution retains a newer image choice");
    assert.equal(racing.dirty(), true);
    const choosing = node("image-select").change({ target: { value: image.id } });
    racing.previewScene({ name: "Later again", content: { type: "image", asset: next.id } }, state.etag);
    resolveOutput(true); await choosing;
    assert.equal(state.previewContent.asset, next.id, "a delayed preview choice cannot replace a newer choice");
    console.log("Generated pattern canonical DTO, publication/read ordering and scene application passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
