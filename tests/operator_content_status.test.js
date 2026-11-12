"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const model = require("../frontend/controller/operator-state.js");

function element(tag) {
    return {
        tagName: tag, dataset: {}, attrs: {}, children: [], listeners: {},
        value: "", hidden: false, disabled: false, textContent: "", className: "",
        width: 0, height: 0, src: "",
        addEventListener(type, fn) { this.listeners[type] = fn; this[type] = fn; },
        focus() { document.activeElement = this; },
        replaceChildren(...items) { this.children = items; },
        append(...items) { this.children.push(...items); },
        add(item) { this.children.push(item); },
        remove() { this.removed = true; },
        setAttribute(key, value) { this.attrs[key] = String(value); },
        getAttribute(key) { return Object.prototype.hasOwnProperty.call(this.attrs, key) ? this.attrs[key] : null; },
        removeAttribute(key) { delete this.attrs[key]; }
    };
}

const nodes = new Map();
const document = {
    activeElement: null,
    getElementById(id) {
        if (!nodes.has(id)) nodes.set(id, element(id));
        return nodes.get(id);
    },
    createElement: tag => element(tag)
};
function node(id) { return document.getElementById(id); }
function Option(text, value) { this.text = text; this.value = value; }

const token = { connection_id: "c", generation: "g", revision: 2, render_seq: 1, mapping_revision: "m", asset: "a" };
const config = { generation: "g", revision: 2, layout: { kind: "logical", width: 100, height: 100, placements: { t: {} } },
    scene: { content: { type: "image", asset: "a", fit: "cover" } }, runtime: { devices: { t: { online: true, protocol: 3,
        caps: ["render_ack"], mapping: { state: "ready" }, render: { state: "loading" } } } } };
const state = { layoutKind: "logical", etag: "e", etagState: "current", capabilities: {}, scene: { content: { type: "color" } }, base: config.layout };
const images = ["a", "b"].map(id => ({ id, name: id, width: 100, height: 100, thumbnail_url: "/" + id }));
const requests = [];
let failInventory = false, release;
const context = vm.createContext({ window: { OperatorState: model }, document, Option, performance: { now: () => 100 } });
vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);
vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-content.js"), "utf8"), context);
const content = context.window.OperatorContent.create({ state, renderStage() {}, announce() {}, showConflict() {},
    ingestConfig(result) { state.operatorConfig = result; state.scene = result.scene; },
    async api(method, path, body, options) {
        requests.push({ method, path, body, options });
        if (path === "/api/v3/images") { if (failInventory) throw Error("network"); return { images }; }
        if (path === "/api/v3/scene") return release ? await new Promise(resolve => { release.resolve = resolve; }) : config;
        if (path.startsWith("/api/v3/scenes/")) return config;
        throw Error(path);
    } });
(async () => {
    await content.refresh(); content.render();
    assert.equal(content.dirty(), false, "loading Images must not create a draft");
    assert.equal(node("show-image").disabled, true, "Show needs a draft");
    assert.equal(node("image-preview-controls").hidden, true, "an idle wall does not present an inactive edit form");
    assert.equal(node("edit-current-image").hidden, true, "test colours have no saved image to adjust");
    assert.equal(node("image-fit").disabled, true, "Fit needs a draft");
    assert.equal(node("image-title").textContent, "Tablet colours", "the stage names the test pattern currently on the wall");
    assert.equal(node("image-details").textContent, "", "idle state needs no instructional paragraph");
    state.scene = { content: { type: "image", asset: "sha256:missing" } };
    content.render();
    assert.equal(node("image-title").textContent, "Unavailable image", "a missing applied image has a readable heading instead of an asset digest");
    assert.equal(node("image-source-details").textContent, "sha256:missing", "the exact missing asset identity stays in Image details");
    assert.equal(content.stageNames().unavailable, true, "stage metadata exposes availability independently of its filename");
    state.scene = { content: { type: "color" } };
    content.render();

    node("image-fit").value = "contain";
    node("image-fit").change({ target: node("image-fit") });
    assert.equal(node("image-fit").value, "cover", "changing Fit with no draft restores the control");
    assert.equal(content.dirty(), false);

    const rows = node("image-gallery").children;
    assert.equal(rows.length, 2);
    const cardA = rows.find(row => row.dataset.assetId === "a"), cardB = rows.find(row => row.dataset.assetId === "b");
    const buttonA = cardA.children[0], buttonB = cardB.children[0];
    assert.equal(buttonA.children.find(child => child.className === "image-choice-name").textContent, "a");
    assert.equal(buttonA.children.some(child => child.className === "image-choice-dimensions"), false,
        "library cards show filename only, not dimensions");
    assert.equal(buttonA.attrs["aria-pressed"], "false");
    assert.equal(cardA.dataset.selected, undefined, "selection uses one outline marker, not a duplicate badge");
    assert.equal(content.stageNames().applied, null, "test colours report no applied content name");

    await buttonA.click();
    assert.equal(content.dirty(), true, "clicking a library image creates a draft");
    assert.equal(state.previewContent.fit, "cover", "a genuinely new image starts at the cover default");
    assert.equal(state.previewContent.background, "#0b1120", "a genuinely new image carries the renderer background default");
    assert.equal(node("image-preview-controls").hidden, false);
    assert.equal(buttonA.attrs["aria-pressed"], "true");
    assert.equal(cardA.dataset.selected, undefined);
    assert.equal(node("image-title").textContent, "a");
    assert.equal(node("image-source-details").textContent, "100 × 100 source px");
    assert.equal(node("show-image").disabled, false);
    assert.equal(node("image-fit").disabled, false);
    assert.equal(content.stageNames().pending, "a");

    content.discard();
    assert.equal(content.dirty(), false);
    assert.equal(buttonA.attrs["aria-pressed"], "false");
    assert.equal(node("image-title").textContent, "Tablet colours");
    assert.equal(node("image-details").textContent, "", "idle state needs no instructional paragraph");
    assert.equal(node("show-image").disabled, true);
    assert.equal(node("image-fit").disabled, true);

    assert.equal(node("image-discard").hidden, true); assert.equal(node("restore-image").hidden, true);
    await buttonA.click();
    assert.equal(node("image-discard").hidden, false);
    assert.equal(node("image-rebuild").hidden, true, "a current preview needs no Rebuild");
    state.etag = "changed"; content.render();
    assert.equal(node("image-rebuild").hidden, false, "a stale-base draft exposes Rebuild");
    state.etag = "e";
    node("image-discard").focus();
    await content.showSelected();
    assert.equal(document.activeElement, node("image-search"));
    assert.equal(node("image-discard").hidden, true); assert.equal(node("restore-image").hidden, false);
    assert.equal(content.dirty(), false); assert.equal(state.previewContent, null);
    assert.equal(node("edit-current-image").hidden, false, "a saved image has an explicit adjust action");
    assert.equal(node("image-preview-controls").hidden, true);
    assert.equal(node("show-image").disabled, true); assert.equal(node("image-fit").disabled, true);
    assert.equal(node("image-message").textContent, "", "routine success is silent; the header carries the state");
    assert.equal(buttonA.attrs["aria-pressed"], "false", "a completed Show clears the rust draft outline");
    assert.equal(cardA.dataset.applied, "true", "the applied marker remains when no draft exists");
    const appliedNote = cardA.children.find(child => child.id === buttonA.attrs["aria-describedby"]);
    assert.match(appliedNote.textContent, /Applied configuration/);
    assert.match(appliedNote.textContent, /tablet reports are separate/);
    assert.equal(buttonA.attrs["aria-describedby"], appliedNote.id, "the applied marker has an accessible description");
    assert.equal(content.stageNames().applied, "a");

    const confirm = "";
    const render = config.runtime.devices.t.render;
    Object.assign(render, { state: "displayed", current: true, expected_token: token, accepted_token: { ...token }, age_ms: 0, observed_mono: 100 });
    content.render(); assert.equal(node("image-message").textContent, confirm);
    render.accepted_token = { ...token, revision: 1 }; content.render();
    assert.equal(node("image-message").textContent, confirm, "stale tablet evidence stays in the header and Issues");
    render.state = "failed"; content.render();
    assert.equal(node("image-message").textContent, confirm, "tablet failures are not enumerated in the inspector");
    config.runtime.devices.t.mapping.state = "needs_calibration"; content.render();
    assert.equal(node("image-message").textContent, confirm, "mapping failures are not enumerated in the inspector");
    config.runtime.devices.t.mapping.state = "ready";
    config.runtime.devices.t.online = false; content.render();
    assert.equal(node("image-message").textContent, confirm, "offline tablets are not enumerated in the inspector");
    assert.doesNotMatch(node("image-message").textContent, /offline|failed|failure|cannot confirm|stale/i);
    config.runtime.devices.t.online = true; config.revision = 3; content.render();
    assert.equal(node("image-message").textContent, "", "revision-only drift with unchanged generation, content and arrangement needs no warning");
    const warning = /changed after this command/;
    config.scene.content.asset = "b"; content.render(); assert.match(node("image-message").textContent, warning, "another asset retains the warning");
    config.scene.content.asset = "a"; config.scene.content.fit = "contain"; content.render(); assert.match(node("image-message").textContent, warning, "changed scaling retains the warning");
    config.scene.content.fit = "cover"; config.scene.content.type = "color"; content.render(); assert.match(node("image-message").textContent, warning, "changed content type retains the warning");
    config.scene.content.type = "image";
    config.layout.width = 200; content.render(); assert.match(node("image-message").textContent, warning, "changed arrangement retains the warning even for the same image");
    config.layout.width = 100;
    config.generation = "new"; content.render(); assert.match(node("image-message").textContent, warning, "another server generation cannot inherit the receipt");
    config.generation = "g"; content.render(); assert.equal(node("image-message").textContent, "");
    config.revision = 2; content.render();
    assert.equal(node("image-message").textContent, confirm);
    await content.refresh();
    config.generation = "after-read"; content.render();
    assert.match(node("image-message").textContent, warning, "inventory success preserves the command receipt for later drift detection");
    config.generation = "g"; content.render();
    assert.equal(node("image-message").textContent, confirm);

    state.etagState = "stale"; content.render();
    assert.match(node("image-message").textContent, /^Image applied\. Tablet reports may be stale/);
    state.etagState = "current";
    state.rosterError = "offline"; content.render();
    assert.match(node("image-message").textContent, /stale/);
    state.rosterError = null; content.render();
    assert.equal(node("image-message").textContent, confirm);

    failInventory = true; await content.refresh(); content.render(); assert.match(node("library-status").textContent, /library unavailable/);
    await buttonA.click(); await content.showSelected(); content.render();
    assert.match(node("library-status").textContent, /library unavailable/, "a retained library error survives a later command");
    failInventory = false; await content.refresh();
    await buttonA.click(); release = {};
    const pending = content.showSelected(); await new Promise(resolve => setImmediate(resolve));
    content.previewScene({ name: "new", content: { type: "image", asset: "b" } }, "e");
    release.resolve(config); await pending;
    assert.equal(state.previewContent.asset, "b"); assert.equal(content.dirty(), true); assert.equal(node("image-discard").hidden, false);
    assert.equal(node("image-title").textContent, "b");
    assert.equal(node("image-source-details").textContent, "100 × 100 source px");
    assert.deepEqual({ ...content.stageNames() }, { applied: "a", pending: "b", unavailable: false },
        "the inspector shows draft facts and the stage chip can name applied content");
    assert.equal(buttonA.attrs["aria-pressed"], "false", "Show cleared the draft it submitted");
    assert.equal(buttonB.attrs["aria-pressed"], "true", "a newer draft keeps its own rust outline");
    assert.equal(cardA.dataset.applied, "true", "Show moves the applied marker to the submitted image");
    state.viewLive = true; content.render();
    assert.equal(node("image-title").textContent, "a", "the stage headline names the applied image during comparison");
    assert.equal(node("show-image").textContent, "Show b", "while the applied wall is visible, Show names what it will show");
    state.viewLive = false; content.render();
    node("image-discard").focus(); content.discard(); assert.equal(document.activeElement, node("image-search"));
    assert.equal(content.dirty(), false); assert.equal(state.previewContent, null);
    assert.equal(cardA.dataset.applied, "true", "Discard never removes the applied marker");
    assert.equal(buttonB.attrs["aria-pressed"], "false", "Discard removes the rust outline");
    await node("edit-current-image").click();
    assert.equal(content.dirty(), true, "adjusting a saved image creates a new guarded preview");
    assert.equal(state.previewContent.asset, "a");
    content.discard();
    assert.equal(content.dirty(), false);

    state.scene = { content: { type: "image", asset: "a", fit: "contain" } };
    content.render();
    await buttonA.click();
    assert.equal(state.previewContent.fit, "contain", "reselected applied image retains its applied fit");
    assert.equal(state.previewContent.background, "#0b1120", "an omitted applied background falls back to the renderer default");

    content.discard();
    state.scene = { content: { type: "image", asset: "a", fit: "contain", background: "#123456" } };
    content.render();
    await buttonA.click();
    assert.equal(state.previewContent.background, "#123456", "reselected applied image retains its explicit background");
    node("image-fit").value = "cover";
    node("image-fit").change({ target: node("image-fit") });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(state.previewContent.fit, "cover");
    assert.equal(state.previewContent.background, "#123456", "changing fit keeps the explicit background");

    await buttonB.click();
    assert.equal(state.previewContent.fit, "cover", "a different image keeps the current fit choice");
    assert.equal(state.previewContent.background, "#0b1120", "a different image never inherits another image's background");

    content.discard();
    state.scene = { content: { type: "color" } };
    content.render();
    await buttonA.click();
    assert.equal(state.previewContent.fit, "cover", "a genuinely new image starts at cover");
    node("image-fit").value = "contain";
    node("image-fit").change({ target: node("image-fit") });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(state.previewContent.fit, "contain");
    assert.equal(state.previewContent.background, "#0b1120", "changing fit never invents a background");
    await buttonB.click();
    assert.equal(state.previewContent.fit, "contain", "a deliberate fit choice applies to the next new image");
    assert.equal(state.previewContent.background, "#0b1120", "but its background never carries over");

    content.discard();
    content.previewScene({ name: "Amber", content: { type: "image", asset: "a", fit: "contain", background: "#ABCDEF" } }, "e");
    assert.equal(state.previewContent.background, "#abcdef", "a saved explicit background previews at its normalized value");
    assert.equal(state.previewContent.fit, "contain");
    node("image-fit").value = "cover";
    node("image-fit").change({ target: node("image-fit") });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(state.previewContent.fit, "cover");
    assert.equal(state.previewContent.background, "#abcdef", "changing fit keeps a saved explicit background");

    await buttonB.click();
    assert.equal(state.previewContent.background, "#0b1120", "a new asset after a saved preview uses the new-image default");
    assert.equal(state.previewContent.fit, "cover");

    content.previewScene({ name: "Legacy", content: { type: "image", asset: "a" } }, "e");
    assert.equal(state.previewContent.background, "#0b1120", "a legacy saved scene without a background previews at the client fallback");
    assert.equal(state.previewContent.fit, "cover");
    assert.equal(state.previewContent.asset, "a");
    content.previewScene({ name: "Red", content: { type: "color" } }, "e");
    assert.deepEqual({ ...state.previewContent }, { type: "color" }, "test content carries no image fields");

    content.discard();
    state.scene = { content: { type: "image", asset: "a", fit: "contain", background: "#123456" } };
    content.render();
    content.previewScene({ name: "Amber", content: { type: "image", asset: "a", fit: "contain", background: "#abcdef" } }, "e");
    const savedDraft = JSON.stringify(state.previewContent);
    const beforeRebuild = requests.length;
    state.etag = "saved-entry-replaced"; content.render();
    assert.equal(content.rebuild(), false, "saved previews refuse Rebuild instead of rebasing name recall");
    assert.equal(content.dirty(), true, "refused Rebuild retains the draft");
    assert.equal(JSON.stringify(state.previewContent), savedDraft, "refused Rebuild never substitutes saved content");
    assert.equal(node("show-image").disabled, true);
    assert.match(node("image-message").textContent, /Discard.*Saved.*preview.*again/);
    assert.equal(document.activeElement, node("image-message"), "saved recovery instruction receives focus");
    assert.equal(await content.showSelected(), false);
    assert.equal(requests.length, beforeRebuild, "refused saved Rebuild and Show send no requests");
    content.discard(); state.etag = "e";
    content.previewScene({ name: "Amber", content: { type: "image", asset: "a", fit: "contain", background: "#abcdef" } }, "e");
    assert.equal(await content.showSelected(), true);
    const recalled = requests.at(-1);
    assert.equal(recalled.method, "POST");
    assert.equal(recalled.path, "/api/v3/scenes/Amber/recall");
    assert.equal(recalled.body, undefined, "saved-scene recall never rewrites the scene body");
    assert.equal(recalled.options.ifMatch, "e");
    await node("restore-image").click();
    const restored = requests.at(-1);
    assert.equal(restored.method, "PUT");
    assert.equal(restored.path, "/api/v3/scene");
    assert.equal(restored.body.content.background, "#123456", "restore previous keeps the explicit applied background");
    assert.equal(restored.body.content.fit, "contain");
    assert.deepEqual(Object.keys(restored.body.content).sort(), ["asset", "background", "fit", "type"],
        "restore previous never adds controller chrome to the scene body");
    console.log("Content status, applied/draft ownership, command feedback, error retention and draft races passed");
})().catch(error => { console.error(error); process.exitCode = 1; });

(async () => {
    const nodes = new Map();
    const fitNode = id => { if (!nodes.has(id)) nodes.set(id, element(id)); return nodes.get(id); };
    const bars = element("ul");
    const widthRow = element("li"); widthRow.dataset.axis = "width";
    const heightRow = element("li"); heightRow.dataset.axis = "height";
    bars.children = [widthRow, heightRow];
    nodes.set("crop-bars", bars);
    const fitDocument = { activeElement: null, getElementById: fitNode, createElement: tag => element(tag) };
    const state = { layoutKind: "logical", etag: "e", etagState: "current", configLoaded: true,
        capabilities: {}, scene: { content: { type: "color" } },
        base: { kind: "logical", width: 200, height: 200, placements: {} },
        draft: { kind: "logical", width: 200, height: 200, placements: {} } };
    const assets = {
        wide: { id: "wide", name: "wide.png", width: 1600, height: 1000, url: "/w", thumbnail_url: "/w" },
        tall: { id: "tall", name: "tall.png", width: 1000, height: 1600, url: "/t", thumbnail_url: "/t" },
        square: { id: "square", name: "square.png", width: 1000, height: 1000, url: "/s", thumbnail_url: "/s" },
        missing: { id: "missing", name: "missing.png", url: "/m", thumbnail_url: "/m" }
    };
    const requests = [];
    const context = vm.createContext({ window: { OperatorState: model }, document: fitDocument, Option });
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-content.js"), "utf8"), context);
    const content = context.window.OperatorContent.create({ state, renderStage() {}, announce() {}, showConflict() {},
        ingestConfig(result) { state.scene = result.scene; },
        async api(method, path, body) {
            requests.push({ method, path, body });
            if (path === "/api/v3/images") return { images: Object.values(assets) };
            if (path === "/api/v3/scene") { const asset = assets[body.content.asset];
                return { scene: { content: { ...body.content, intrinsicWidth: asset.width, intrinsicHeight: asset.height } } }; }
            throw Error(path);
        } });
    const text = id => fitNode(id).textContent;
    const choose = id => fitNode("image-gallery").children.find(item => item.dataset.assetId === id).children[0].click();
    const setFit = async value => { fitNode("image-fit").value = value;
        fitNode("image-fit").change({ target: fitNode("image-fit") }); await new Promise(resolve => setImmediate(resolve)); };
    const wall = (width, height) => { state.base.width = width; state.base.height = height;
        state.draft.width = width; state.draft.height = height; content.render(); };
    await content.refresh();
    assert.equal(text("fit-summary"), "Select an image to estimate Fill crop or Fit bands.");
    assert.equal(text("fit-applied"), "Applied: tablet colours · no image fit");
    assert.equal(fitNode("crop-bars").hidden, true);

    await choose("wide");
    assert.equal(text("fit-summary"), "Preview Fill of 1600 × 1000: 37.5% of the source width and 0% of the source height are cropped.");
    assert.equal(text("crop-width"), "37.5% of source width cropped");
    assert.equal(text("crop-height"), "0% of source height cropped");
    assert.equal(widthRow.getAttribute("style"), "--crop:37.5%");
    assert.equal(heightRow.getAttribute("style"), "--crop:0%");
    assert.equal(fitNode("crop-bars").hidden, false);
    assert.equal(text("fit-applied"), "Applied: tablet colours · no image fit", "the proposal never rewrites the applied summary");

    await setFit("contain");
    assert.equal(text("fit-summary"), "Preview Fit of 1600 × 1000: 0% of the wall width and 37.5% of the wall height are uncovered.");
    assert.equal(text("crop-width"), "0% of wall width uncovered");
    assert.equal(text("crop-height"), "37.5% of wall height uncovered");
    assert.equal(widthRow.getAttribute("style"), "--crop:0%");
    assert.equal(heightRow.getAttribute("style"), "--crop:37.5%");

    await setFit("cover");
    await choose("square");
    wall(200, 100);
    assert.equal(text("fit-summary"), "Preview Fill of 1000 × 1000: 0% of the source width and 50% of the source height are cropped.");
    wall(100, 200);
    assert.equal(text("fit-summary"), "Preview Fill of 1000 × 1000: 50% of the source width and 0% of the source height are cropped.");
    await choose("tall");
    wall(200, 200);
    assert.equal(text("fit-summary"), "Preview Fill of 1000 × 1600: 0% of the source width and 37.5% of the source height are cropped.");
    await setFit("contain");
    assert.equal(text("fit-summary"), "Preview Fit of 1000 × 1600: 37.5% of the wall width and 0% of the wall height are uncovered.");

    await choose("missing");
    assert.match(text("fit-summary"), /^Preview crop estimate unavailable: source dimensions are missing\.$/);
    assert.equal(text("crop-width"), "Unavailable");
    assert.equal(text("crop-height"), "Unavailable");
    assert.equal(fitNode("crop-bars").hidden, true, "missing source dimensions never invent zero crop");

    await choose("wide");
    state.base.width = 0;
    content.render();
    assert.match(text("fit-summary"), /^Preview crop estimate unavailable: wall bounds are missing\.$/);
    assert.equal(fitNode("crop-bars").hidden, true);
    wall(200, 200);

    state.scene = { content: { type: "image", asset: "wide", fit: "contain", background: "#123456",
        intrinsicWidth: 1600, intrinsicHeight: 1000 } };
    content.discard();
    assert.equal(text("fit-summary"), "Applied Fit of 1600 × 1000: 0% of the wall width and 37.5% of the wall height are uncovered.");
    assert.equal(text("fit-applied"), "Applied: Fit · background #123456");
    await choose("tall");
    assert.equal(text("fit-applied"), "Applied: Fit · background #123456", "a draft image never changes the applied fit or background");
    assert.match(text("fit-summary"), /^Preview Fit of 1000 × 1600:/);

    content.discard();
    state.scene = { content: { type: "image", asset: "missing" } };
    content.render();
    assert.match(text("fit-summary"), /^Applied crop estimate unavailable: source dimensions are missing\.$/);
    assert.equal(fitNode("crop-bars").hidden, true);

    state.scene = { content: { type: "image", asset: "wide", fit: "cover", background: "#0b1120",
        intrinsicWidth: 1600, intrinsicHeight: 1000 } };
    content.render();
    const summary = fitNode("fit-summary");
    let summaryValue = summary.textContent, summaryWrites = 0;
    Object.defineProperty(summary, "textContent", { get: () => summaryValue,
        set: value => { summaryWrites += 1; summaryValue = value; } });
    for (let index = 0; index < 5; index += 1) content.render();
    assert.equal(summaryWrites, 0, "heartbeats and repeated renders never announce an unchanged fit");
    state.base.width = 400;
    content.render();
    assert.equal(summaryWrites, 1, "a settled wall change updates the authoritative fit summary once");
    assert.match(summaryValue, /^Applied Fill of 1600 × 1000:/);

    state.scene = { content: { type: "color" } };
    state.base.width = 200;
    content.render();
    await content.refresh();
    await choose("wide");
    await setFit("cover");
    assert.equal(requests.some(request => request.method === "PUT"), false, "choosing and fitting a proposal issues no scene PUT");
    assert.equal(await content.showSelected(), true);
    const pushed = requests.at(-1);
    assert.equal(pushed.method, "PUT");
    assert.equal(pushed.path, "/api/v3/scene");
    assert.deepEqual(Object.keys(pushed.body.content).sort(), ["asset", "background", "fit", "type"],
        "fit feedback never adds controller fields to the scene body");
    assert.match(text("fit-summary"), /^Applied Fill of 1600 × 1000:/);
    assert.equal(text("fit-applied"), "Applied: Fill · background #0b1120", "Show settles the committed fit and background");
    console.log("Fit feedback distinguishes source crop from wall bands, keeps applied and draft separate, and updates only on settled changes");
})().catch(error => { console.error(error); process.exitCode = 1; });

{
    const html = fs.readFileSync(require.resolve("../frontend/controller/physical.html"), "utf8");
    for (const id of ["fit-feedback", "fit-feedback-title", "crop-bars", "crop-width", "crop-height", "fit-summary", "fit-applied"]) {
        assert.equal((html.match(new RegExp('id="' + id + '"', "g")) || []).length, 1, "one #" + id);
    }
    assert.ok(html.indexOf('id="fit-feedback"') > html.indexOf('id="show-image"'), "fit feedback follows Show in source order");
    assert.ok(html.indexOf('id="fit-feedback"') > html.indexOf('class="commit-evidence"'), "fit feedback sits in commit evidence");
    assert.match(html, /id="fit-feedback"[^>]*aria-labelledby="fit-feedback-title"/);
    assert.match(html, /id="fit-feedback-title"[^>]*>Image fit and crop</);
    assert.match(html, /id="crop-bars"[^>]*aria-hidden="true"/);
    assert.match(html, /id="fit-summary"[^>]*role="status"[^>]*aria-live="polite"/);
    const bars = html.slice(html.indexOf('id="crop-bars"'), html.indexOf("</ul>", html.indexOf('id="crop-bars"')));
    assert.ok(bars.includes('id="crop-width"') && bars.includes('id="crop-height"'), "crop values belong to the decorative bars");
}
console.log("Fit feedback slots are unique, labelled, decorative and placed after Show");

(async () => {
    const nodes = new Map();
    function localElement(tag, owner) {
        return {
            tagName: tag, dataset: {}, attrs: {}, children: [], listeners: {}, isConnected: true,
            value: "", hidden: false, _disabled: false, textContent: "", className: "", width: 0, height: 0, src: "",
            get disabled() { return this._disabled; },
            set disabled(value) { this._disabled = value; if (value && owner.activeElement === this) owner.activeElement = owner.body; },
            getClientRects() { return this.hidden ? [] : [{ width: 10, height: 10 }]; },
            addEventListener(type, fn) { this.listeners[type] = fn; this[type] = fn; },
            focus() { owner.activeElement = this; owner.focusListener?.({ target: this }); },
            replaceChildren(...items) { this.children = items; },
            append(...items) { this.children.push(...items); },
            remove() { this.removed = true; },
            setAttribute(key, value) { this.attrs[key] = String(value); },
            getAttribute(key) { return Object.prototype.hasOwnProperty.call(this.attrs, key) ? this.attrs[key] : null; },
            removeAttribute(key) { delete this.attrs[key]; }
        };
    }
    const doc = { activeElement: null, getElementById: id => { if (!nodes.has(id)) nodes.set(id, localElement(id, doc)); return nodes.get(id); },
        createElement: tag => localElement(tag, doc) };
    const node = id => doc.getElementById(id);
    doc.body = localElement("body", doc);
    doc.addEventListener = (type, listener) => { if (type === "focusin") doc.focusListener = listener; };
    doc.removeEventListener = (type, listener) => { if (type === "focusin" && doc.focusListener === listener) doc.focusListener = null; };
    const state = { layoutKind: "logical", etag: "e", etagState: "current", capabilities: {}, scene: { content: { type: "color" } },
        base: { kind: "logical", width: 1000, height: 500, placements: {} },
        draft: { kind: "logical", width: 1000, height: 500, placements: {} } };
    const images = ["a", "b"].map(id => ({ id, name: id + ".png", width: 100, height: 100,
        source: "managed", url: "/" + id, thumbnail_url: "/" + id }));
    const calls = [];
    let conflictCount = 0, fail = null, inventoryError = false, inventoryPending = null;
    const context = vm.createContext({ window: { OperatorState: model }, document: doc, Option });
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-content.js"), "utf8"), context);
    const content = context.window.OperatorContent.create({ state, renderStage() {}, announce() {},
        showConflict() { conflictCount += 1; },
        ingestConfig(result) { state.scene = result.scene; },
        async api(method, path, body, options) {
            calls.push({ method, path, body, options });
            if (path === "/api/v3/images") { if (inventoryPending) return inventoryPending.promise; if (inventoryError) throw new Error("Inventory unavailable"); return { images }; }
            if (path === "/api/v3/scene" || path.startsWith("/api/v3/scenes/")) return fail();
            throw new Error("unexpected route " + path);
        } });
    const choose = id => node("image-gallery").children.find(item => item.dataset.assetId === id).children[0].click();
    const exact412 = "Could not show this content. The wall changed after this preview was built, so nothing was shown. Use Refresh status, then Rebuild preview, then Show image.";
    const fail412 = ({ changeEtag = false } = {}) => () => {
        state.etagState = "stale";
        if (changeEtag) state.etag = "changed";
        const error = new Error("Server detail abc123 is not for operators.");
        error.status = 412;
        throw error;
    };
    await content.refresh();

    const deferred = () => {
        const value = {};
        value.promise = new Promise((resolve, reject) => { value.resolve = resolve; value.reject = reject; });
        return value;
    };
    await choose("a");
    const command = deferred();
    fail = () => command.promise;
    const showing = content.showSelected();
    await new Promise(setImmediate);
    inventoryPending = deferred();
    const overlappingRead = content.refresh();
    command.reject(Object.assign(new Error("guard conflict"), { status: 412 }));
    await showing;
    assert.equal(node("image-message").textContent, exact412);
    inventoryPending.resolve({ images });
    await overlappingRead;
    assert.equal(node("image-message").textContent, exact412, "a delayed inventory success cannot clear the 412 command error");
    inventoryPending = null;
    content.discard();
    conflictCount = 0;

    const staleImage = "The wall changed after this preview was built. Show is off until the preview is rebuilt. Use Rebuild preview, then Show image.";
    const staleSaved = "The wall changed after this preview was built. Show is off. Discard this preview, then open Saved and preview the content again.";
    let messageWrites = 0, messageText = node("image-message").textContent;
    Object.defineProperty(node("image-message"), "textContent", {
        get() { return messageText; },
        set(value) { messageText = value; messageWrites += 1; }
    });
    for (const event of ["stale", "412"]) for (const outcome of ["success", "failure"]) {
        content.discard(); state.etag = "e"; state.etagState = "current";
        await choose("a");
        let showing;
        const command = deferred();
        if (event === "412") {
            fail = () => command.promise;
            showing = content.showSelected();
            await new Promise(setImmediate);
        }
        inventoryPending = deferred();
        const reading = content.refresh();
        if (event === "412") {
            command.reject(Object.assign(new Error("guard conflict"), { status: 412 }));
            await showing;
        } else { state.etag = "remote"; content.render(); }
        const expected = event === "412" ? exact412 : staleImage;
        assert.equal(node("image-message").textContent, expected);
        const before = messageWrites;
        const draft = JSON.stringify(state.previewContent);
        const writes = calls.filter(call => call.method !== "GET").length;
        node("image-search").focus();
        if (outcome === "success") inventoryPending.resolve({ images });
        else inventoryPending.reject(new Error("Inventory unavailable"));
        await reading;
        assert.equal(node("image-message").textContent, expected, event + " survives a delayed inventory " + outcome);
        assert.equal(messageWrites, before, "inventory completion adds no command announcement");
        assert.equal(JSON.stringify(state.previewContent), draft);
        assert.equal(doc.activeElement, node("image-search"));
        assert.equal(calls.filter(call => call.method !== "GET").length, writes, "inventory completion sends no write");
        assert.equal(node("library-status").textContent, outcome === "success" ? ""
            : "Image library unavailable. Inventory unavailable. The last known library state is still shown. Use Refresh images to retry.");
        inventoryPending = null;
    }
    content.discard(); state.etag = "e"; state.etagState = "current"; conflictCount = 0;
    await choose("a");
    node("show-image").focus();
    const beforeStale = calls.length;
    state.etagState = "stale";
    content.render();
    assert.equal(doc.activeElement, node("image-rebuild"), "remote invalidation hands focused Show to Rebuild before the new guard arrives");
    assert.equal(node("image-rebuild").hidden, false);
    assert.equal(node("show-image").disabled, true);
    assert.equal(node("image-message").textContent, staleImage);
    assert.equal(node("image-message").dataset.kind, "warn");
    const once = messageWrites;
    state.etag = "remote"; state.etagState = "current";
    content.render(); content.render();
    assert.equal(messageWrites, once, "one stale transition announces only once across invalidation and reconciliation");
    assert.equal(calls.length, beforeStale, "passive recovery sends no request or automatic rebase");
    assert.equal(await content.showSelected(), false);
    content.discard(); state.etag = "e";
    await choose("a");
    node("image-search").focus();
    state.etag = "remote";
    content.render();
    assert.equal(doc.activeElement, node("image-search"), "remote staleness does not touch another control's focus");
    content.discard(); state.etag = "e";
    content.previewScene({ name: "Amber", content: { type: "color" } }, "e");
    node("show-image").focus();
    state.etag = "remote";
    content.render();
    assert.equal(node("image-message").textContent, staleSaved);
    assert.equal(doc.activeElement, node("image-message"), "saved previews focus the safe re-preview instruction");
    content.discard(); state.etag = "e";
    await choose("a");
    inventoryError = true;
    await content.refresh();
    const retainedError = node("library-status").textContent;
    state.etag = "remote";
    content.render();
    assert.equal(node("library-status").textContent, retainedError, "staleness never overwrites a retained inventory error");
    assert.equal(node("image-message").textContent, staleImage, "a library error cannot suppress stale preview guidance");
    inventoryError = false;
    content.discard(); state.etag = "e";
    await content.refresh();

    node("show-image").focus();
    fail = fail412({ changeEtag: true });
    await choose("a");
    const beforeFirst = calls.length;
    assert.equal(await content.showSelected(), false, "a 412 fails the Show");
    assert.equal(calls.length - beforeFirst, 1, "a 412 sends exactly one command and no retry");
    assert.equal(calls.at(-1).method, "PUT");
    assert.equal(conflictCount, 1, "the existing conflict panel call is kept");
    assert.equal(node("image-message").textContent, exact412, "a 412 states the recovery path in plain words");
    assert.equal(node("image-message").textContent.includes("Server detail"), false, "a 412 never prints the server detail");
    assert.equal(doc.activeElement, node("image-rebuild"), "a stale preview focuses the visible Rebuild control first");
    assert.notEqual(doc.activeElement, node("image-search"), "a failed Show never falls back to the search field");
    assert.equal(node("image-rebuild").disabled, false);
    const originalGuard = calls.at(-1).options.ifMatch;
    state.etagState = "current"; content.render();
    assert.equal(node("show-image").disabled, true, "Refresh alone cannot authorize the original preview against a new wall");
    const beforeBlocked = calls.length;
    assert.equal(await content.showSelected(), false, "the public action also refuses a preview requiring rebuild");
    assert.equal(calls.length, beforeBlocked, "Show sends nothing until explicit rebuild");
    assert.equal(originalGuard, "e", "the failed command used the original preview guard");
    assert.equal(content.rebuild(() => false), false, "cancelled image Rebuild never rebases the preview");
    assert.equal(node("show-image").disabled, true);
    assert.equal(node("image-message").textContent, exact412);
    content.rebuild();
    assert.equal(node("image-message").textContent, "", "explicit rebuild clears the obsolete Show failure");
    assert.equal(node("show-image").disabled, false);
    fail = () => ({ scene: { content: { type: "image", asset: "a" } } });
    assert.equal(await content.showSelected(), true);
    assert.equal(calls.at(-1).options.ifMatch, "changed", "only explicit rebuild updates the submitted guard");

    state.etag = "e"; state.etagState = "current"; conflictCount = 0;
    content.discard();
    node("show-image").focus();
    fail = fail412();
    await choose("a");
    await content.showSelected();
    assert.equal(node("image-rebuild").hidden, false, "an invalidated guard exposes explicit recovery before reconciliation returns");
    assert.equal(doc.activeElement, node("image-rebuild"), "an invalidated guard focuses its visible recovery action");
    assert.equal(node("image-message").textContent, exact412, "passive stale guidance never overwrites a real 412 failure");

    state.etag = "e"; state.etagState = "current";
    content.discard();
    node("show-image").focus();
    fail = () => { const error = new Error("Image store failed."); error.status = 500; throw error; };
    await choose("a");
    assert.equal(await content.showSelected(), false, "a non-412 failure still fails the Show");
    assert.equal(node("image-message").textContent, "Could not show this content. Image store failed. Use Refresh images to retry.",
        "a non-412 failure keeps today's text");
    assert.equal(doc.activeElement, node("show-image"), "an enabled trigger keeps focus");

    let rejectShow;
    fail = () => new Promise((resolve, reject) => { rejectShow = reject; });
    node("show-image").focus();
    let pending = content.showSelected();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(doc.activeElement, doc.body, "a pending Show disables the trigger and Chromium drops its focus");
    node("settings-control").focus();
    doc.activeElement = doc.body;
    rejectShow(new Error("Connection lost"));
    await pending;
    assert.equal(doc.activeElement, doc.body, "a user who moved focus while pending keeps ownership even if that control later disappears");

    node("show-image").focus();
    pending = content.showSelected();
    await new Promise(resolve => setImmediate(resolve));
    state.tabName = "system";
    rejectShow(new Error("Connection lost"));
    await pending;
    assert.equal(doc.activeElement, doc.body, "intervening task navigation prevents late Show focus restoration");
    state.tabName = "content";

    state.etag = "e"; state.etagState = "current";
    content.discard();
    content.previewScene({ name: "Amber", content: { type: "image", asset: "a", fit: "contain" } }, "e");
    node("image-message").hidden = true;
    node("image-search").hidden = true;
    node("scene-message").hidden = false;
    node("show-image").focus();
    conflictCount = 0;
    fail = fail412({ changeEtag: true });
    const beforeRecall = calls.length;
    assert.equal(await content.showSelected({ feedback: "scene-message" }), false, "a refused saved-content recall fails");
    assert.equal(calls.length - beforeRecall, 1, "a saved-content recall sends one command and no retry");
    assert.equal(calls.at(-1).method, "POST");
    assert.equal(calls.at(-1).path, "/api/v3/scenes/Amber/recall");
    assert.equal(node("scene-message").textContent,
        "Could not show this content. The wall changed after this preview was built, so nothing was shown. Use Refresh status, discard this preview, then open Saved and preview the content again.",
        "a saved recall failure gives its safe explicit re-preview path");
    assert.equal(doc.activeElement, node("scene-message"), "with Images hidden, focus goes to the visible recall message");
    assert.notEqual(doc.activeElement, node("image-search"), "the hidden Images field is never focused");
    assert.notEqual(doc.activeElement.tagName, "body", "focus never lands on BODY");

    node("scene-message").hidden = true;
    node("show-image").focus();
    state.etag = "e"; state.etagState = "current";
    content.discard();
    content.previewScene({ name: "Amber", content: { type: "image", asset: "a" } }, "e");
    node("image-message").hidden = true; node("image-search").hidden = true;
    fail = fail412({ changeEtag: true });
    await content.showSelected({ feedback: "scene-message" });
    assert.equal(doc.activeElement, doc.body, "with no visible candidate focus is left where disabling the trigger put it");
    assert.notEqual(doc.activeElement, node("image-search"));
    console.log("Failed Show keeps one command, states the D5 message and moves focus only to visible candidates");
})().catch(error => { console.error(error); process.exitCode = 1; });

{
    const html = fs.readFileSync(require.resolve("../frontend/controller/physical.html"), "utf8");
    const status = html.slice(html.indexOf('id="wall-status"'), html.indexOf("</div>", html.indexOf('id="wall-status"')));
    assert.ok(status.includes('id="wall-power-caution"'), "the wall status group exposes a short wake-lock caution");
    const details = html.slice(html.indexOf('id="stage-technical"'));
    assert.ok(details.includes('id="wall-power-summary"'), "the complete fleet evidence is reachable in Details");
    assert.match(html, /id="image-message"[^>]*tabindex="-1"/, "the Images message is programmatically focusable");
    for (const [input, hint, message] of [["layout-name", "layout-name-rule", "layout-msg"],
        ["scene-name", "scene-name-rule", "scene-message"]]) {
        assert.match(html, new RegExp('id="' + input + '"[^>]*aria-describedby="' + hint + " " + message + '"'),
            "the " + input + " rule is described before its message");
        assert.match(html, new RegExp('id="' + hint + '"[^>]*>Use letters, numbers, spaces, dots, underscores or hyphens\\. Start with a letter or number\\. 64 characters at most\\.'),
            "the " + input + " rule sentence is stated once as a hint");
    }
}
console.log("Wave-one HTML adds the power summary, both name-rule hints and a focusable Images message");
