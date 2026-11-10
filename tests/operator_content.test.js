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
        get firstElementChild() { return this.children[0] || null; },
        get nextElementSibling() {
            const siblings = this.parentElement && this.parentElement.children;
            const index = siblings ? siblings.indexOf(this) : -1;
            return index >= 0 ? siblings[index + 1] || null : null;
        },
        insertBefore(child, reference) {
            const previous = child.parentElement;
            if (previous && previous.children) {
                const at = previous.children.indexOf(child);
                if (at >= 0) previous.children.splice(at, 1);
            }
            const index = reference ? this.children.indexOf(reference) : -1;
            if (index < 0) this.children.push(child); else this.children.splice(index, 0, child);
            child.parentElement = this;
            return child;
        },
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
    await inventoryState();
    await closestFocus();
    await patternGrouping();
    console.log("Generated pattern canonical DTO, publication/read ordering, scene application, row-aware gallery focus, inventory state and closest fallback passed");
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
    assert.equal(event.defaultPrevented, true);
    event = press("ArrowLeft");
    assert.equal(focused(), buttons()[1], "Left moves within the rendered row");
    event = press("ArrowDown");
    assert.equal(focused(), buttons()[4], "Down moves to the nearest choice in the next rendered row");
    event = press("ArrowDown");
    assert.equal(focused(), buttons()[7]);
    event = press("ArrowDown");
    assert.equal(focused(), buttons()[7], "Down stops when no rendered row follows");
    assert.equal(event.defaultPrevented, true);
    event = press("ArrowUp");
    assert.equal(focused(), buttons()[4]);
    event = press("ArrowUp");
    assert.equal(focused(), buttons()[1]);
    event = press("ArrowUp");
    assert.equal(focused(), buttons()[1], "Up stops when no rendered row precedes");
    assert.equal(event.defaultPrevented, true);
    event = press("Home");
    assert.equal(focused(), buttons()[0], "Home focuses the first visible choice");
    assert.equal(event.defaultPrevented, true);
    assert.equal(press("Home").defaultPrevented, true, "Home at the first choice prevents native scrolling");
    event = press("End");
    assert.equal(focused(), buttons()[8], "End focuses the last visible choice");
    assert.equal(event.defaultPrevented, true);
    assert.equal(press("End").defaultPrevented, true, "End at the last choice prevents native scrolling");
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
    assert.equal(buttons()[8].scrollIntoViewCalls.length, 1, "nested scrolling delegates one reveal to the browser");
    assert.equal(buttons()[8].scrollIntoViewCalls[0].block, "nearest");
    assert.equal(buttons()[8].scrollIntoViewCalls[0].inline, "nearest");

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
    assert.equal(event.defaultPrevented, true);
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

async function inventoryState() {
    const nodes = new Map();
    const doc = { activeElement: null, getElementById: null, createElement: tag => focusedElement(tag, doc) };
    function focusedElement(tag, owner) {
        const node = element(tag, owner);
        let disabled = false;
        Object.defineProperty(node, "disabled", {
            get() { return disabled; },
            set(value) {
                disabled = Boolean(value);
                if (disabled && owner.activeElement === node) owner.activeElement = owner.body || null;
            }
        });
        return node;
    }
    doc.body = focusedElement("body", doc);
    doc.getElementById = id => {
        if (!nodes.has(id)) nodes.set(id, focusedElement(id, doc));
        return nodes.get(id);
    };
    const node = id => doc.getElementById(id);
    const state = { layoutKind: "logical", etag: "e", etagState: "current", capabilities: { uploads: false },
        scene: { content: { type: "color" } }, draft: {} };
    const asset = id => ({ id, name: id + ".png", width: 100, height: 100, url: "/" + id, thumbnail_url: "/" + id + ".thumb" });
    const a = asset("a"), b = asset("b"), c = asset("c"), d = asset("d");
    const pending = [];
    const context = vm.createContext({ window: { OperatorState: model }, document: doc, Option: function () {} });
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-content.js"), "utf8"), context);
    const content = context.window.OperatorContent.create({ state, renderStage() {}, announce() {}, showConflict() {},
        ingestConfig(config) { state.scene = config.scene; },
        api(method, path) {
            if (path !== "/api/v3/images") throw new Error("unexpected route " + path);
            return new Promise((resolve, reject) => pending.push({ resolve, reject }));
        } });
    const refreshWith = async images => {
        const read = content.refresh();
        pending.shift().resolve({ images });
        await read;
    };
    const click = async id => node("image-gallery").children.find(row => row.dataset.assetId === id).children[0].click();
    const rows = () => node("image-gallery").children;

    await refreshWith([a, b, c]);
    node("image-search").value = ""; node("image-search").input();
    const before = new Map(rows().map(row => [row.dataset.assetId, row]));
    node("refresh-images").focus();
    const read = content.refresh();
    const request = pending.shift();
    assert.equal(node("refresh-images").disabled, true, "a pending inventory read disables its trigger");
    assert.equal(doc.activeElement, doc.body, "disabling the focused refresh control moves focus to BODY in the browser model");
    assert.match(node("image-message").textContent, /Refreshing the image library/);
    assert.match(node("image-message").textContent, /last known library state/);
    request.resolve({ images: [a, b, c, d] });
    await read;
    assert.equal(doc.activeElement, node("refresh-images"), "the settled refresh restores its invoking focus");
    assert.equal(node("refresh-images").disabled, false);
    assert.equal(rows().length, 4, "new inventory rows appear after the read settles");
    assert.equal(rows().find(row => row.dataset.assetId === "a"), before.get("a"), "an inventory refresh reuses existing row nodes");
    assert.equal(node("image-message").textContent, "", "routine inventory success clears the refreshing label");

    node("refresh-images").focus();
    const failed = content.refresh();
    pending.shift().reject(new Error("offline"));
    await failed;
    assert.equal(doc.activeElement, node("refresh-images"), "a failed refresh also restores its invoking focus");
    assert.equal(rows().length, 4, "a failed refresh keeps the last known inventory");
    assert.match(node("image-message").textContent, /library unavailable/);
    assert.match(node("image-message").textContent, /last known library state is still shown/);
    assert.equal(node("refresh-images").disabled, false);

    const slow = content.refresh();
    const slowRequest = pending.shift();
    const fast = content.refresh();
    const fastRequest = pending.shift();
    fastRequest.resolve({ images: [a] });
    await fast;
    slowRequest.resolve({ images: [a, b, c, d] });
    await slow;
    assert.equal(rows().length, 1, "a stale inventory read cannot replace a newer result");
    assert.equal(rows()[0].dataset.assetId, "a");

    await refreshWith("abcdefgh".split("").map(asset));
    rows().find(row => row.dataset.assetId === "e").children[0].focus();
    await refreshWith([asset("d"), asset("g")]);
    assert.equal(doc.activeElement.parentElement.dataset.assetId, "d", "inventory removal finds the nearest survivor in the previous row order");
    node("image-search").focus();
    node("image-search").value = ""; node("image-search").input();
    await refreshWith([]);
    const empty = node("image-search-empty");
    assert.equal(empty.hidden, false, "a real empty inventory shows a message inside the library");
    assert.equal(empty.textContent, "No images available.");
    assert.equal(node("image-message").textContent, "No images available.");
    assert.equal(rows().length, 0);
    node("image-search").value = "anything"; node("image-search").input();
    assert.equal(empty.textContent, "No images available.", "a search cannot turn a real empty inventory into a filter miss");

    node("image-search").value = ""; node("image-search").input();
    await refreshWith([a, b]);
    assert.equal(empty.hidden, true);
    node("image-search").value = "zzz"; node("image-search").input();
    assert.equal(empty.hidden, false);
    assert.equal(empty.textContent, "No images match your search.");
    node("image-search").value = ""; node("image-search").input();

    const rowA = rows().find(row => row.dataset.assetId === "a");
    const buttonA = rowA.children[0];
    const thumbnail = buttonA.children[0];
    thumbnail.error();
    assert.equal(rowA.dataset.thumbnail, "unavailable");
    assert.equal(thumbnail.hidden, true, "a missing thumbnail is not rendered as a broken image");
    assert.match(buttonA.attrs["aria-label"], /thumbnail unavailable/);
    assert.match(buttonA.attrs["aria-describedby"], /image-thumbnail-note/);
    thumbnail.load();
    assert.equal(rowA.dataset.thumbnail, undefined);
    assert.equal(thumbnail.hidden, false);
    assert.doesNotMatch(buttonA.attrs["aria-label"] || "", /thumbnail unavailable/);

    await click("a");
    assert.equal(content.dirty(), true);
    assert.equal(state.previewContent.asset, "a");
    await refreshWith([b]);
    assert.equal(content.dirty(), true, "an inventory drop keeps the selected proposal explicit");
    assert.equal(state.previewContent.asset, "a");
    assert.equal(state.previewContent.available, false);
    assert.equal(node("image-title").textContent, "Unavailable image");
    assert.equal(node("image-details").textContent, "Selected image unavailable. Refresh images or choose a replacement.");
    assert.equal(node("show-image").disabled, true, "an unavailable selected proposal cannot be shown");
    assert.equal(rows().length, 1, "the missing selection never silently switches to a surviving image");
    assert.equal(rows()[0].dataset.assetId, "b");
    await click("b");
    assert.equal(state.previewContent.asset, "b", "an explicit replacement selection wins");
    assert.equal(state.previewContent.available, undefined);

    console.log("Inventory refresh focus, last-known failure, stale read, empty/filter/missing-thumbnail and unavailable proposal states passed");
}

async function closestFocus() {
    const nodes = new Map();
    const doc = { activeElement: null, getElementById: null, createElement: tag => element(tag, doc) };
    doc.getElementById = id => {
        if (!nodes.has(id)) nodes.set(id, element(id, doc));
        return nodes.get(id);
    };
    const list = doc.getElementById("image-gallery");
    const images = ["keep-0", "drop-1", "keep-2", "drop-3", "keep-4", "drop-5", "keep-6", "drop-7", "keep-8"]
        .map((name, index) => ({ id: "img-" + index, name, width: 100, height: 100, url: "/" + index, thumbnail_url: "/" + index }));
    const state = { layoutKind: "logical", etag: "e", etagState: "current", capabilities: { uploads: false },
        scene: { content: { type: "color" } }, draft: {} };
    const context = vm.createContext({ window: { OperatorState: model }, document: doc, Option: function () {} });
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-content.js"), "utf8"), context);
    const content = context.window.OperatorContent.create({ state, renderStage() {}, announce() {}, showConflict() {},
        ingestConfig(config) { state.scene = config.scene; },
        async api(method, path) { if (path === "/api/v3/images") return { images }; throw new Error("unexpected route " + path); } });
    await content.refresh();
    const rows = () => list.children;
    const buttons = () => rows().map(row => row.children[0]);
    buttons().forEach((button, index) => {
        const column = index % 3, row = Math.floor(index / 3);
        const left = column * 108, top = row * 108;
        button.rect = { left, top, right: left + 100, bottom: top + 100, width: 100, height: 100 };
    });
    buttons()[3].focus();
    doc.getElementById("image-search").value = "keep";
    doc.getElementById("image-search").input();
    assert.equal(doc.activeElement, buttons()[2], "hiding the focused choice focuses the closest visible choice, not the first");
    assert.equal(buttons()[2].tabIndex, 0, "the closest fallback is the one roving tab entry");
    const kept = rows()[2];
    list.scrollTop = 120;
    await content.refresh();
    assert.equal(rows()[2], kept, "a filtered refresh keeps the same row node");
    assert.equal(doc.activeElement, buttons()[2], "a filtered inventory refresh keeps gallery focus");
    assert.equal(list.scrollTop, 120, "an inventory refresh does not reset gallery scroll");
    console.log("Closest visible gallery fallback, filtered row identity, focus and scroll passed");
}

async function patternGrouping() {
    const nodes = new Map();
    const doc = { activeElement: null, getElementById: null, createElement: tag => element(tag, doc) };
    doc.getElementById = id => {
        if (!nodes.has(id)) nodes.set(id, element(id, doc));
        return nodes.get(id);
    };
    const state = { layoutKind: "logical", etag: "e", etagState: "current", capabilities: { uploads: false },
        scene: { content: { type: "color" } },
        base: { kind: "logical", width: 1000, height: 500, placements: {} },
        draft: { kind: "logical", width: 1000, height: 500, placements: {} } };
    const hashA = "a".repeat(64), hashB = "b".repeat(64), hashC = "c".repeat(64), hashD = "d".repeat(64), hashE = "e".repeat(64);
    const asset = (hash, name, source) => ({ id: "sha256:" + hash, name, width: 100, height: 100,
        source, url: "/" + hash, thumbnail_url: "/" + hash });
    const patternB = asset(hashB, "wall-pattern-" + hashB + ".png", "curated");
    const managed = asset(hashD, "wall-pattern-" + hashD + ".png", "managed");
    const wrongId = asset(hashC, "wall-pattern-" + hashB + ".png", "curated");
    const plain = asset(hashE, "zebra.png", "curated");
    const patternA = asset(hashA, "wall-pattern-" + hashA + ".png", "curated");
    const images = [patternB, managed, wrongId, plain, patternA];
    const calls = [];
    const context = vm.createContext({ window: { OperatorState: model }, document: doc, Option: function () {} });
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-content.js"), "utf8"), context);
    const content = context.window.OperatorContent.create({ state, renderStage() {}, announce() {}, showConflict() {},
        ingestConfig(config) { state.scene = config.scene; },
        async api(method, path, body) {
            calls.push({ method, path, body });
            if (path === "/api/v3/images") return { images };
            throw new Error("unexpected route " + path);
        } });
    await content.refresh();
    const list = doc.getElementById("image-gallery");
    const rows = () => list.children;
    const row = id => rows().find(item => item.dataset.assetId === id);
    const button = id => row(id).children[0];
    const tag = id => button(id).children.find(child => child.className === "image-choice-tag");
    const order = () => rows().map(item => item.dataset.assetId);

    assert.deepEqual(order(), [managed.id, wrongId.id, plain.id, patternB.id, patternA.id],
        "curated hash-named files sort after other images and keep their own order");
    assert.equal(tag(patternA.id).textContent, "Test pattern");
    assert.equal(tag(patternA.id).hidden, false, "a pattern shows its visible tag");
    assert.equal(tag(patternB.id).hidden, false);
    assert.equal(tag(managed.id).hidden, true, "a managed upload shaped like a pattern is not labelled");
    assert.equal(tag(managed.id).textContent, "", "ordinary gallery tiles retain their plain text contract");
    assert.equal(tag(wrongId.id).hidden, true, "a curated file whose name does not match its own id is not labelled");
    assert.equal(tag(plain.id).hidden, true);
    assert.equal(button(patternA.id).attrs["aria-label"], "Preview " + patternA.name + ", test pattern",
        "a pattern tile says so in its accessible name");
    assert.equal(button(patternB.id).attrs["aria-label"], "Preview " + patternB.name + ", test pattern");
    assert.equal(button(managed.id).attrs["aria-label"], "Preview " + managed.name,
        "a managed file with the same shape keeps the ordinary accessible name");
    assert.equal(button(wrongId.id).attrs["aria-label"], "Preview " + wrongId.name);
    assert.equal(button(plain.id).attrs["aria-label"], "Preview " + plain.name);
    assert.equal(rows().filter(item => item.tagName === "li").length, rows().length, "there is one gallery list");
    assert.equal(rows().filter(item => item.children[0].tabIndex === 0).length, 1, "the gallery keeps one Tab stop");

    button(patternA.id).focus();
    button(patternA.id).click();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(content.dirty(), true, "a pattern stays selectable");
    assert.equal(state.previewContent.asset, patternA.id, "selecting a pattern previews it");
    assert.equal(doc.activeElement, button(patternA.id), "selecting a pattern keeps gallery focus");
    assert.equal(button(patternA.id).attrs["aria-pressed"], "true");
    assert.deepEqual(calls.map(call => call.path), ["/api/v3/images"], "selection writes no scene");
    const insert = list.insertBefore;
    list.insertBefore = function (item, reference) {
        if (item.children.includes(doc.activeElement)) doc.activeElement = null;
        return insert.call(this, item, reference);
    };
    list.scrollTop = 120;
    patternA.name = "aaa.png";
    images.unshift(images.pop());
    await content.refresh();
    assert.equal(doc.activeElement === button(patternA.id), true, "refresh restores the same focused choice after moving its row");
    assert.equal(button(patternA.id).focusOptions.preventScroll, true);
    assert.equal(list.scrollTop, 120, "restoring reorder focus preserves gallery scroll");
    assert.equal(rows().filter(item => item.children[0].tabIndex === 0).length, 1);
    console.log("Exact curated test patterns sort last, carry a visible tag and keep the single gallery tab stop");
}
