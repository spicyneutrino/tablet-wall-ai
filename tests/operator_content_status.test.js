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
let failInventory = false, release;
const context = vm.createContext({ window: { OperatorState: model }, document, Option, performance: { now: () => 100 } });
vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);
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
    assert.equal(content.dirty(), false, "loading Images must not create a draft");
    assert.equal(node("show-image").disabled, true, "Show needs a draft");
    assert.equal(node("image-preview-controls").hidden, true, "an idle wall does not present an inactive edit form");
    assert.equal(node("edit-current-image").hidden, true, "test colours have no saved image to adjust");
    assert.equal(node("image-fit").disabled, true, "Fit needs a draft");
    assert.equal(node("image-title").textContent, "Nothing shown", "diagnostic colours are never named as content");
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
    assert.equal(node("image-title").textContent, "Nothing shown");
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
    const appliedNote = cardA.children[1];
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

    state.etagState = "stale"; content.render();
    assert.match(node("image-message").textContent, /^Image applied\. Tablet reports may be stale/);
    state.etagState = "current";
    state.rosterError = "offline"; content.render();
    assert.match(node("image-message").textContent, /stale/);
    state.rosterError = null; content.render();
    assert.equal(node("image-message").textContent, confirm);

    failInventory = true; await content.refresh(); content.render(); assert.match(node("image-message").textContent, /library unavailable/);
    await buttonA.click(); await content.showSelected(); content.render();
    assert.match(node("image-message").textContent, /library unavailable/, "a retained library error survives a later command");
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
    assert.equal(node("image-title").textContent, "b", "comparison keeps the pending filename in the inspector");
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
    console.log("Content status, applied/draft ownership, command feedback, error retention and draft races passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
