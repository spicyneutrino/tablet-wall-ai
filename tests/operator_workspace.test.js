"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function setup() {
    const nodes = new Map();
    const element = id => {
        if (!nodes.has(id)) nodes.set(id, { textContent: "", listeners: {}, isConnected: true,
            addEventListener(event, handler) { this.listeners[event] = handler; },
            showModal() { this.open = true; }, close() { this.open = false; }, focus() {} });
        return nodes.get(id);
    };
    const window = {};
    vm.runInNewContext(fs.readFileSync(require.resolve("../frontend/controller/operator-workspace.js"), "utf8"),
        { window, document: { getElementById: element, querySelector: () => element("stage"), activeElement: element("trigger") } });
    const draft = { arrangement: true, image: true, applied: [] };
    const workspace = window.OperatorWorkspace.create({ state: {}, arrangementDirty: () => draft.arrangement,
        arrangementPreview: () => draft.arrangement, imageDirty: () => draft.image,
        applyArrangement: async () => { draft.applied.push("arrangement"); draft.arrangement = false; },
        showImage: async () => { draft.applied.push("image"); draft.image = false; },
        discardArrangement: () => { draft.arrangement = false; }, discardImage: () => { draft.image = false; },
        commitTask() {}, renderStage() {}, refreshReadiness() {}, refreshStatus() {}, selectTablet() {}, canCommit: () => true });
    return { workspace, draft, element, choose: choice => element("resolve-" + choice).listeners.click() };
}

(async () => {
    const { workspace, draft, element, choose } = setup();
    const result = workspace.resolve("Save tablet name");
    assert.equal(element("resolve-commit").textContent, "Apply arrangement");
    assert.equal(await workspace.resolve("Another action"), false, "one resolution owns the dialog");
    choose("discard");
    await new Promise(setImmediate);
    assert.equal(element("draft-resolution").open, true, "the remaining image must be reviewed before continuing");
    assert.equal(element("resolve-commit").textContent, "Show image");
    choose("stay");
    assert.equal(await result, false, "Stay on the second draft cancels the original immediate action");
    assert.equal(draft.arrangement, false);
    assert.equal(draft.image, true);
    assert.deepEqual(draft.applied, []);

    const second = setup();
    const committed = second.workspace.resolve("Save tablet name");
    second.choose("commit");
    await new Promise(setImmediate);
    assert.deepEqual(second.draft.applied, ["arrangement"], "committing geometry does not commit content");
    second.choose("commit");
    assert.equal(await committed, true);
    assert.deepEqual(second.draft.applied, ["arrangement", "image"]);

    const except = setup();
    const ownImageCommand = except.workspace.resolve("Show selected image", "image");
    except.choose("discard");
    assert.equal(await ownImageCommand, true, "an image command resolves only incompatible geometry");
    assert.equal(except.draft.image, true);
    console.log("Output resolution reviews every incompatible draft before continuing");
})().catch(error => { console.error(error); process.exitCode = 1; });
