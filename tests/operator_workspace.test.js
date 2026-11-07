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
    vm.runInNewContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8") + "\n" + fs.readFileSync(require.resolve("../frontend/controller/operator-workspace.js"), "utf8"),
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

function setupIssue(options = {}) {
    const nodes = new Map();
    const element = id => {
        if (!nodes.has(id)) nodes.set(id, { id, textContent: "", listeners: {}, isConnected: true, hidden: false,
            addEventListener(event, handler) { this.listeners[event] = handler; },
            showModal() { this.open = true; }, close() { this.open = false; }, focus() {} });
        return nodes.get(id);
    };
    const window = { OperatorState: {
        entries: layout => layout.slots || layout.placements || {},
        tabletState: () => ({ showing: false, status: "hidden", text: "Hidden" })
    } };
    const state = {
        operatorConfig: { layout: { kind: "physical", slots: { a: {}, b: {} } } },
        roster: { a: { online: true }, b: { online: true } }, tabName: "tablet", deviceLabels: {}
    };
    vm.runInNewContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8") + "\n" + fs.readFileSync(require.resolve("../frontend/controller/operator-workspace.js"), "utf8"),
        { window, document: { getElementById: element, querySelector: () => element("stage"), activeElement: element("trigger") } });
    const calls = [];
    const workspace = window.OperatorWorkspace.create({ state, arrangementDirty: () => false,
        arrangementPreview: () => false, imageDirty: () => false,
        applyArrangement: async () => {}, showImage: async () => {}, discardArrangement() {}, discardImage() {},
        commitTask(name, taskOptions) {
            calls.push({ kind: "commit", name, options: taskOptions });
            return options.commit ? options.commit(name, taskOptions) : true;
        },
        renderStage() {}, stageNames: () => ({}),
        selectTablet(id, selectOptions) { calls.push({ kind: "select", id, options: selectOptions }); },
        canCommit: () => true, labelFor: id => "Tablet " + id });
    return { workspace, state, calls };
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

    const issue = setupIssue();
    const triggerA = element("issue-a");
    const rowA = { isConnected: true, firstElementChild: triggerA };
    assert.equal(await issue.workspace.revealIssue("a", rowA, triggerA), true, "an issue action opens Tablets first");
    assert.deepEqual(issue.calls.map(call => [call.kind, call.id || call.name]), [["commit", "tablet"], ["select", "a"]],
        "task transition completes once before the selected device sheet is revealed");
    assert.deepEqual([issue.calls[1].options.reveal, issue.calls[1].options.taskOpened, issue.calls[1].options.trigger],
        [true, true, triggerA], "the invoking issue control is preserved and the reveal reuses the completed task transition");
    assert.equal(issue.calls.some(call => call.kind === "select" && !call.options.reveal), false, "selection never precedes the task transition");

    const other = setupIssue();
    other.state.selectedId = "a";
    const triggerB = element("issue-b");
    await other.workspace.revealIssue("b", { isConnected: true, firstElementChild: triggerB }, triggerB);
    assert.deepEqual(other.calls.map(call => [call.kind, call.id || call.name]), [["commit", "tablet"], ["select", "b"]],
        "a different device reveals after the same single transition");

    const refused = setupIssue({ commit: () => false });
    assert.equal(await refused.workspace.revealIssue("a", { isConnected: true }, element("issue-a")), false,
        "a refused task transition leaves recovery hidden");
    assert.deepEqual(refused.calls.map(call => call.kind), ["commit"], "refused navigation never selects or reveals");

    const removed = setupIssue();
    removed.state.operatorConfig.layout.slots = { b: {} };
    assert.equal(await removed.workspace.revealIssue("a", { isConnected: true }, element("issue-a")), false,
        "a device removed during the transition does not reveal stale recovery");
    assert.deepEqual(removed.calls.map(call => call.kind), ["commit"], "removed device never reaches selection");

    const detached = setupIssue();
    assert.equal(await detached.workspace.revealIssue("a", { isConnected: false }, element("issue-a")), false,
        "a detached issue row does not reveal");
    assert.deepEqual(detached.calls.map(call => call.kind), ["commit"]);

    let releaseFirst;
    let commitCount = 0;
    const raced = setupIssue({ commit: () => {
        commitCount += 1;
        return commitCount === 1 ? new Promise(resolve => { releaseFirst = resolve; }) : true;
    } });
    const firstReveal = raced.workspace.revealIssue("a", { isConnected: true }, element("issue-a"));
    const latestReveal = raced.workspace.revealIssue("b", { isConnected: true }, element("issue-b"));
    assert.equal(await latestReveal, true);
    releaseFirst(true);
    assert.equal(await firstReveal, false, "a superseded reveal cannot select or open stale recovery");
    assert.deepEqual(raced.calls.filter(call => call.kind === "select").map(call => call.id), ["b"],
        "only the newest issue request reveals");
})().catch(error => { console.error(error); process.exitCode = 1; });
