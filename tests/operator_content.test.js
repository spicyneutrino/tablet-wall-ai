"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const model = require("../frontend/controller/operator-state.js");
const nodes = new Map();
function element(tag, ownerDocument) {
    const owner = ownerDocument || document;
    return { tagName: tag, ownerDocument: owner, dataset: {}, value: "", hidden: false, disabled: false, tabIndex: -1,
        textContent: "", attrs: {}, children: [], parentElement: null, rect: null, style: { overflowX: "visible", overflowY: "visible" },
        scrollLeft: 0, scrollTop: 0, clientWidth: 0, clientHeight: 0, scrollWidth: 0, scrollHeight: 0,
        addEventListener(type, fn) { this[type] = fn; },
        append(...items) { for (const item of items) { this.children.push(item); if (item) item.parentElement = this; } },
        replaceChildren(...items) { this.children = []; this.append(...items); },
        remove() { if (this.parentElement) { const index = this.parentElement.children.indexOf(this); if (index >= 0) this.parentElement.children.splice(index, 1); this.parentElement = null; } },
        focus(options) { owner.activeElement = this; this.focusOptions = options || {}; },
        scrollIntoView(options) { this.scrollIntoViewCalls = (this.scrollIntoViewCalls || []).concat([options]); },
        getBoundingClientRect() { return this.rect || { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 }; },
        getClientRects() { return this.rect ? [this.rect] : []; },
        getAttribute(key) { return this.attrs[key]; }, setAttribute(key, value) { this.attrs[key] = value; }, removeAttribute(key) { delete this.attrs[key]; } };
}
function node(id) { if (!nodes.has(id)) nodes.set(id, element()); return nodes.get(id); }
const document = { activeElement: null, getElementById: node, createElement: tag => element(tag) };
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
    assert.equal(calls[2].body.content.background, "#0b1120", "a still-image request carries the renderer's own uncovered-wall default");
    assert.deepEqual(Object.keys(calls[2].body.content).sort(), ["asset", "background", "fit", "type"],
        "controller stage chrome never enters the scene body");
    assert.equal(JSON.stringify(calls[2].body).includes("#22252a"), false);
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
    await galleryNavigation();
    console.log("Generated pattern canonical DTO, publication/read ordering, scene application and row-aware gallery focus passed");
})().catch(error => { console.error(error); process.exitCode = 1; });

async function galleryNavigation() {
    const galleryNodes = new Map();
    const galleryDocument = { activeElement: null };
    galleryDocument.getElementById = id => {
        if (!galleryNodes.has(id)) galleryNodes.set(id, element(id, galleryDocument));
        return galleryNodes.get(id);
    };
    galleryDocument.createElement = tag => element(tag, galleryDocument);
    const galleryNode = id => galleryDocument.getElementById(id);
    const images = Array.from({ length: 9 }, (_, index) => ({
        id: "img-" + index, name: "img-" + index + ".png", width: 100, height: 100,
        url: "/img-" + index, thumbnail_url: "/img-" + index
    }));
    const state = { layoutKind: "logical", etag: "e", etagState: "current", capabilities: { uploads: false },
        scene: { content: { type: "color" } }, draft: {} };
    const calls = [];
    const context = vm.createContext({ window: { OperatorState: model }, document: galleryDocument, Option: function () {} });
    context.window.getComputedStyle = target => target.style || { overflowX: "visible", overflowY: "visible" };
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-content.js"), "utf8"), context);
    const content = context.window.OperatorContent.create({ state, renderStage() {}, announce() {}, showConflict() {},
        ingestConfig(config) { state.scene = config.scene; },
        async api(method, path) {
            calls.push({ method, path });
            if (path === "/api/v3/images") return { images };
            throw new Error("unexpected route " + path);
        } });
    await content.refresh();

    const list = galleryNode("image-gallery");
    const rows = () => list.children;
    const buttons = () => rows().map(row => row.children[0]);
    const visible = () => rows().filter(row => !row.hidden && !row.children[0].disabled).map(row => row.children[0]);
    const tabStops = () => buttons().filter(button => button.tabIndex === 0);
    const assertTabStop = (button, message) => {
        assert.equal(tabStops().length, 1, message + " (one tab entry)");
        assert.equal(tabStops()[0], button, message);
    };
    const focused = () => galleryDocument.activeElement;
    const press = key => {
        const event = { key, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
        list.keydown(event);
        return event;
    };
    const focusButton = index => { buttons()[index].focus(); return buttons()[index]; };
    const layout = (columns, width = 200, height = 100, gap = 8) => buttons().forEach((button, index) => {
        const column = index % columns, row = Math.floor(index / columns);
        const left = column * (width + gap), top = row * (height + gap);
        button.rect = { left, top, right: left + width, bottom: top + height, width, height };
    });
    const oneRow = (width = 124, gap = 8) => buttons().forEach((button, index) => {
        const left = index * (width + gap);
        button.rect = { left, top: 0, right: left + width, bottom: 100, width, height: 100 };
    });

    assertTabStop(buttons()[0], "the first visible choice is the single roving tab entry");
    layout(3);
    focusButton(0);
    let event = press("ArrowRight");
    assert.equal(focused(), buttons()[1], "Right moves to the adjacent visible choice");
    assert.equal(event.defaultPrevented, true);
    event = press("ArrowRight");
    assert.equal(focused(), buttons()[2]);
    event = press("ArrowRight");
    assert.equal(focused(), buttons()[2], "Right never wraps out of its rendered row");
    assert.equal(event.defaultPrevented, false);
    event = press("ArrowLeft");
    assert.equal(focused(), buttons()[1], "Left moves within the rendered row");
    event = press("ArrowDown");
    assert.equal(focused(), buttons()[4], "Down moves to the nearest choice in the next rendered row");
    event = press("ArrowDown");
    assert.equal(focused(), buttons()[7]);
    event = press("ArrowDown");
    assert.equal(focused(), buttons()[7], "Down stops when no rendered row follows");
    assert.equal(event.defaultPrevented, false);
    event = press("ArrowUp");
    assert.equal(focused(), buttons()[4]);
    event = press("ArrowUp");
    assert.equal(focused(), buttons()[1]);
    event = press("ArrowUp");
    assert.equal(focused(), buttons()[1], "Up stops when no rendered row precedes");
    assert.equal(event.defaultPrevented, false);
    event = press("Home");
    assert.equal(focused(), buttons()[0], "Home focuses the first visible choice");
    assert.equal(event.defaultPrevented, true);
    event = press("End");
    assert.equal(focused(), buttons()[8], "End focuses the last visible choice");
    assert.equal(event.defaultPrevented, true);
    assert.equal(buttons()[8].scrollIntoViewCalls.length, 1, "a page-level reveal runs once");
    assert.equal(buttons()[8].scrollIntoViewCalls[0].block, "nearest", "a page-level reveal asks for nearest block scrolling");
    assert.equal(buttons()[8].scrollIntoViewCalls[0].inline, "nearest", "a page-level reveal asks for nearest inline scrolling");
    assertTabStop(buttons()[8], "focus movement is the one roving tab entry");
    assert.equal(content.dirty(), false, "gallery focus never selects content");
    assert.equal(state.previewContent, null, "gallery focus never creates a preview");
    assert.equal(galleryNode("image-title").textContent, "Nothing shown");
    assert.equal(calls.filter(call => call.path === "/api/v3/scene").length, 0, "gallery focus never writes a scene");
    assert.equal(buttons().every(button => button.attrs["aria-pressed"] === "false"), true, "focus never marks a choice as selected");

    layout(2);
    focusButton(0);
    press("ArrowDown");
    assert.equal(focused(), buttons()[2], "row targets follow a two-column layout");
    press("ArrowDown");
    assert.equal(focused(), buttons()[4]);
    layout(1);
    focusButton(0);
    press("ArrowDown");
    assert.equal(focused(), buttons()[1], "row targets follow a one-column layout");
    press("ArrowUp");
    assert.equal(focused(), buttons()[0]);

    oneRow();
    focusButton(0);
    event = press("ArrowDown");
    assert.equal(focused(), buttons()[0], "Down stays native when the rendered gallery has one row");
    assert.equal(event.defaultPrevented, false);
    event = press("ArrowRight");
    assert.equal(focused(), buttons()[1]);
    press("End");
    assert.equal(focused(), buttons()[8]);

    list.style = { overflowX: "auto", overflowY: "visible" };
    list.scrollWidth = 1180; list.clientWidth = 300;
    list.rect = { left: 0, top: 0, right: 300, bottom: 300, width: 300, height: 300 };
    buttons().forEach(button => { delete button.scrollIntoViewCalls; });
    oneRow();
    focusButton(0);
    press("End");
    assert.equal(focused(), buttons()[8]);
    assert.equal(list.scrollLeft, buttons()[8].rect.right - 300, "the horizontal chooser scrolls just enough to expose the focus target");
    assert.equal(buttons()[8].scrollIntoViewCalls, undefined, "inner scrolling never scrolls the outer page");

    list.style = { overflowX: "visible", overflowY: "visible" };
    list.scrollLeft = 0;
    rows().forEach(row => { row.hidden = false; row.children[0].disabled = false; });
    galleryNode("image-search").value = "";
    content.render();
    const firstRow = rows()[0];
    firstRow.dataset.probe = "kept";
    await content.refresh();
    assert.equal(rows()[0], firstRow, "an inventory refresh reuses stable gallery rows");
    assert.equal(firstRow.dataset.probe, "kept");
    layout(3);

    rows()[1].hidden = true;
    buttons()[4].disabled = true;
    focusButton(0);
    press("ArrowRight");
    assert.equal(focused(), buttons()[2], "Right skips hidden choices");
    press("ArrowDown");
    assert.equal(focused(), buttons()[5], "Down skips disabled choices when choosing the nearest target");
    press("ArrowLeft");
    assert.equal(focused(), buttons()[3]);
    event = press("ArrowLeft");
    assert.equal(focused(), buttons()[3], "Left stops at the visible row edge");
    assert.equal(event.defaultPrevented, false);
    assertTabStop(buttons()[3], "a hidden or disabled choice is never the roving tab entry");

    rows()[1].hidden = false;
    buttons()[4].disabled = false;
    content.render();
    galleryNode("image-search").focus();
    galleryNode("image-search").value = "img-4";
    galleryNode("image-search").input();
    assert.equal(focused(), galleryNode("image-search"), "filtering while typing keeps focus in the search field");
    assert.equal(visible().length, 1);
    assert.equal(visible()[0], buttons()[4]);
    assertTabStop(buttons()[4], "one filtered result becomes the single tab entry");
    galleryNode("image-search").value = "no-such-image";
    galleryNode("image-search").input();
    assert.equal(focused(), galleryNode("image-search"), "zero results keep the search field reachable");
    assert.equal(galleryNode("image-search").hidden, false);
    assert.equal(tabStops().length, 0, "zero results never leave a hidden choice as the tab entry");
    galleryNode("image-search").value = "";
    galleryNode("image-search").input();
    assert.equal(focused(), galleryNode("image-search"));
    assert.equal(tabStops().length, 1);

    content.render();
    layout(3);
    focusButton(5);
    galleryNode("image-search").value = "img-6";
    galleryNode("image-search").input();
    assert.equal(focused(), buttons()[6], "hiding the focused choice falls back to the first visible choice");
    assertTabStop(buttons()[6], "the filter fallback becomes the roving entry");
    focusButton(6);
    galleryNode("image-search").value = "no-such-image";
    galleryNode("image-search").input();
    assert.equal(focused(), galleryNode("image-search"), "hiding every choice falls back to the search field");
    assert.equal(tabStops().length, 0);
}
