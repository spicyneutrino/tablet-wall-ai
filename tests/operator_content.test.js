"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const model = require("../frontend/controller/operator-state.js");
const nodes = new Map();
function element() {
    return { dataset: {}, value: "", hidden: false, disabled: false, textContent: "", attrs: {}, children: [],
        addEventListener(type, fn) { this[type] = fn; }, append(...items) { this.children.push(...items); },
        replaceChildren(...items) { this.children = items; }, remove() {}, focus() {},
        getAttribute(key) { return this.attrs[key]; }, setAttribute(key, value) { this.attrs[key] = value; }, removeAttribute(key) { delete this.attrs[key]; } };
}
function node(id) { if (!nodes.has(id)) nodes.set(id, element()); return nodes.get(id); }
const document = { getElementById: node, createElement: element };
const choose = id => node("image-gallery").children.filter(row => row.dataset.assetId === id).at(-1).children[0].click();
const state = { layoutKind: "logical", etag: "current", etagState: "current", configLoaded: true,
    capabilities: { uploads: false }, scene: { content: { type: "color" } },
    draft: { kind: "logical", width: 1000, height: 500, placements: {} } };
const image = { id: "sha256:pattern", name: "black.png", width: 64, height: 64,
    source: "curated", url: "/assets/sha256:pattern", thumbnail_url: "/assets/sha256:pattern", etag: "current" };
const calls = [];
let releaseInventory;
const oldInventory = new Promise(resolve => { releaseInventory = resolve; });
const context = vm.createContext({ window: { OperatorState: model }, document, Option: function () {} });
vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);
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
    assert.equal(content.stageNames().applied, "black.png");
    assert.equal(node("image-title").textContent, "black.png", "the composer names the applied image");
    assert.equal(node("pattern-message").textContent, "", "routine pattern success is silent");
    assert.doesNotMatch(node("image-message").textContent, /Image updated/, "pattern success never writes routine Images feedback");
    releaseInventory({ images: [] });
    await refresh;
    assert.equal(state.activeImageUnavailableId, null, "an older inventory read cannot erase a published pattern");
    assert.equal(content.stageNames().applied, "black.png");
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
    await choose(image.id);
    waitForResolution = true;
    const showing = racing.showSelected();
    racing.previewScene({ name: "Later", content: { type: "image", asset: next.id } }, state.etag);
    resolveOutput(true); await showing;
    assert.equal(state.scene.content.asset, image.id, "Show retains the image captured when the command was requested");
    assert.equal(state.previewContent.asset, next.id, "completion after draft resolution retains a newer image choice");
    assert.equal(racing.dirty(), true);
    const choosing = choose(image.id);
    racing.previewScene({ name: "Later again", content: { type: "image", asset: next.id } }, state.etag);
    resolveOutput(true); await choosing;
    assert.equal(state.previewContent.asset, next.id, "a delayed preview choice cannot replace a newer choice");
    console.log("Generated pattern canonical DTO, publication/read ordering and scene application passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
