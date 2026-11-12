"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function setup() {
    const nodes = new Map();
    const document = { activeElement: null, listeners: {},
        addEventListener(name, handler) { this.listeners[name] = handler; },
        removeEventListener(name) { delete this.listeners[name]; } };
    const element = id => {
        if (!nodes.has(id)) nodes.set(id, { id, textContent: "", listeners: {}, isConnected: true, tabIndex: 0, visibility: "visible",
            getClientRects() { return this.hidden ? [] : [{}]; },
            closest() { return this.collapsed ? {} : null; },
            matches(selector) { return selector === ":modal" ? !!this.open : !!this.disabled; },
            addEventListener(event, handler) { this.listeners[event] = handler; },
            showModal() { this.open = true; },
            close() { this.open = false; if (this.listeners.close) this.listeners.close(); },
            querySelectorAll() { return [element("resolve-commit"), element("resolve-discard"), element("resolve-stay")]; },
            focus() { document.activeElement = this; } });
        return nodes.get(id);
    };
    document.getElementById = element; document.querySelector = () => element("stage"); document.activeElement = element("trigger");
    const window = { getComputedStyle: node => ({ visibility: node.visibility }) };
    vm.runInNewContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8") + "\n" + fs.readFileSync(require.resolve("../frontend/controller/operator-workspace.js"), "utf8"),
        { window, document });
    const draft = { arrangement: true, image: true, applied: [] };
    const workspace = window.OperatorWorkspace.create({ state: {}, arrangementDirty: () => draft.arrangement,
        arrangementPreview: () => draft.arrangement, imageDirty: () => draft.image,
        applyArrangement: async () => { draft.applied.push("arrangement"); draft.arrangement = false; },
        showImage: async () => { draft.applied.push("image"); draft.image = false; },
        discardArrangement: () => { draft.arrangement = false; }, discardImage: () => { draft.image = false; },
        commitTask() {}, renderStage() {}, refreshReadiness() {}, refreshStatus() {}, selectTablet() {}, canCommit: () => true });
    return { workspace, draft, element, document, choose: choice => element("resolve-" + choice).listeners.click() };
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
    const keyboard = setup();
    keyboard.draft.arrangement = false;
    const resolution = keyboard.workspace.resolve("Open Arrange");
    const dialog = keyboard.element("draft-resolution");
    assert.equal(keyboard.document.activeElement, keyboard.element("resolve-stay"), "every opening starts on Stay");
    function tab(from, shiftKey = false) {
        from.focus();
        const event = { key: "Tab", shiftKey, currentTarget: dialog, defaultPrevented: false,
            preventDefault() { this.defaultPrevented = true; } };
        dialog.listeners.keydown?.(event);
        return event.defaultPrevented;
    }
    assert.equal(tab(keyboard.element("resolve-stay")), true, "Tab at the final draft action prevents the native BODY stop");
    assert.equal(keyboard.document.activeElement, keyboard.element("resolve-commit"));
    assert.equal(tab(keyboard.element("resolve-commit"), true), true, "reverse Tab wraps from the first draft action");
    assert.equal(keyboard.document.activeElement, keyboard.element("resolve-stay"));
    const allControls = dialog.querySelectorAll;
    dialog.querySelectorAll = () => [keyboard.element("resolve-commit"), keyboard.element("resolve-discard")];
    for (const shiftKey of [false, true]) {
        keyboard.document.activeElement = keyboard.element("body");
        const event = { key: "Tab", shiftKey, currentTarget: keyboard.document,
            preventDefault() { this.defaultPrevented = true; } };
        keyboard.document.listeners.keydown(event);
        assert.equal(event.defaultPrevented, true, "a removed focused action recovers from BODY");
        assert.equal(keyboard.document.activeElement,
            keyboard.element(shiftKey ? "resolve-discard" : "resolve-commit"),
            "surviving controls receive the correct directional focus");
    }
    dialog.querySelectorAll = allControls;
    keyboard.element("resolve-commit").disabled = true;
    assert.equal(tab(keyboard.element("resolve-stay")), true);
    assert.equal(keyboard.document.activeElement, keyboard.element("resolve-discard"), "disabled commit is skipped at the boundary");
    keyboard.element("resolve-stay").hidden = true;
    assert.equal(tab(keyboard.element("resolve-discard"), true), true);
    assert.equal(keyboard.document.activeElement, keyboard.element("resolve-discard"), "a single rendered action wraps to itself");
    keyboard.element("resolve-stay").hidden = false;
    keyboard.element("resolve-stay").visibility = "hidden";
    assert.equal(tab(keyboard.element("resolve-discard")), true);
    assert.equal(keyboard.document.activeElement, keyboard.element("resolve-discard"), "visibility-hidden actions cannot own focus");
    keyboard.element("resolve-discard").disabled = true;
    keyboard.document.activeElement = keyboard.element("body");
    const bodyTab = { key: "Tab", currentTarget: keyboard.document, preventDefault() { this.defaultPrevented = true; } };
    keyboard.document.listeners.keydown(bodyTab);
    assert.equal(bodyTab.defaultPrevented, true);
    assert.equal(keyboard.document.activeElement, dialog, "focus cleared by unavailable actions is recovered into the native modal");
    keyboard.element("trigger").hidden = true;
    dialog.listeners.cancel({ preventDefault() {} });
    assert.equal(await resolution, false);
    assert.equal(keyboard.document.listeners.keydown, undefined, "closing the modal removes document keyboard handling");
    assert.equal(keyboard.draft.image, true, "Escape retains the image draft");
    assert.deepEqual(keyboard.draft.applied, [], "Escape never writes");
    assert.equal(keyboard.document.activeElement, keyboard.element("compact-task-select"), "an invisible trigger uses a visible fallback");

    const nativeClose = setup();
    const closedResolution = nativeClose.workspace.resolve("Open Images");
    nativeClose.element("draft-resolution").close();
    assert.equal(await closedResolution, false, "native close resolves as Stay instead of leaving the action pending");
    assert.equal(nativeClose.draft.arrangement, true);
    assert.equal(nativeClose.draft.image, true);
    assert.equal(nativeClose.document.activeElement, nativeClose.element("trigger"), "native close restores the exact visible trigger");
    assert.deepEqual(nativeClose.draft.applied, []);
    console.log("Modal draft boundaries skip unavailable actions and close without writing");
    const { workspace, draft, element, choose, document } = setup();
    const result = workspace.resolve("Save tablet name");
    assert.equal(document.activeElement, element("resolve-stay"));
    assert.equal(element("resolve-commit").textContent, "Apply arrangement");
    assert.equal(await workspace.resolve("Another action"), false, "one resolution owns the dialog");
    choose("discard");
    await new Promise(setImmediate);
    assert.equal(element("draft-resolution").open, true, "the remaining image must be reviewed before continuing");
    assert.equal(element("resolve-commit").textContent, "Show image");
    assert.equal(document.activeElement, element("resolve-stay"), "the second combined review also starts on Stay");
    choose("stay");
    assert.equal(await result, false, "Stay on the second draft cancels the original immediate action");
    assert.equal(draft.arrangement, false);
    assert.equal(draft.image, true);
    assert.deepEqual(draft.applied, []);

    const second = setup();
    const committed = second.workspace.resolve("Save tablet name");
    second.choose("commit");
    await new Promise(setImmediate);
    assert.equal(second.document.activeElement, second.element("resolve-stay"), "a successful first commit cannot become the next default");
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

(async () => {
const nodes = new Map();
const document = { activeElement: null, body: { dataset: {} }, getElementById: node, querySelector: selector => node(selector === ".arrange-tools" ? "arrange-tools" : "shared-stage") };
function node(id) {
    if (!nodes.has(id)) nodes.set(id, { dataset: {}, hidden: true, textContent: "", listeners: {}, appends: [], scrollIntoView() {},
        setAttribute(name, value) { (this.attrs ||= {})[name] = value; },
        addEventListener(event, fn) { this.listeners[event] = fn; },
        append(child) { this.appends.push(child); child.parent = this; },
        contains(child) { return child === this || child === node(id + "-summary"); },
        querySelector() { return node(id + "-summary"); }, focus() { document.activeElement = this; } });
    return nodes.get(id);
}
const state = { tabName: "content", roster: { a: { online: true }, b: { online: false } }, configLoaded: true, base: { placements: { a: {} } }, draft: { placements: { a: {} } } };
let dirty = false, applied = "a.png", unavailable = false;
node("stage-mode").hidden = false;
node("image-title").textContent = "a.png";
const context = { window: { OperatorState: require("../frontend/controller/operator-state.js") }, document };
vm.createContext(context);
vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);
vm.runInNewContext(fs.readFileSync(require.resolve("../frontend/controller/operator-workspace.js"), "utf8"), context);
const workspace = context.window.OperatorWorkspace.create({ state, arrangementDirty: () => false, arrangementPreview: () => false,
    imageDirty: () => dirty, canCommit: () => true, stageNames: () => ({ applied, pending: "b.png", unavailable }), commitTask: name => { state.tabName = name; return true; } });

state.base = { placements: {} };
workspace.render();
assert.equal(node("first-wall-steps").hidden, false);
assert.equal(node("first-wall-join-status").textContent, "1 tablet online");
assert.equal(node("first-wall-join").dataset.done, "true");
assert.equal(node("first-wall-arrange-status").textContent, "Not arranged yet");
assert.equal(node("first-wall-arrange").dataset.done, "false");
assert.equal(node("first-wall-image-status").textContent, "No image shown yet");
assert.equal(node("first-wall-image").dataset.done, "false");
node("first-wall-join-action").listeners.click();
assert.equal(document.activeElement, node("tablet-joining-summary"));
await node("first-wall-arrange-action").listeners.click();
assert.equal(state.tabName, "show");
assert.equal(document.activeElement, node("grid-2x2"));
await node("first-wall-image-action").listeners.click();
assert.equal(state.tabName, "content");
assert.equal(document.activeElement, node("image-gallery-summary"));
state.roster = {}; workspace.render();
assert.equal(node("first-wall-join-status").textContent, "No tablets yet");
assert.equal(node("first-wall-arrange-action").disabled, true, "Arrange cannot target hidden controls before tablets join");
node("image-gallery").querySelector = () => null;
await node("first-wall-image-action").listeners.click();
assert.equal(document.activeElement, node("image-search"), "an empty gallery focuses the visible search control");
assert.equal(node("first-wall-join").dataset.done, "false");
state.base = { placements: { a: {} } }; workspace.render();
assert.equal(node("first-wall-steps").hidden, true);
console.log("First-wall visibility, step text, completion attributes and all three destinations passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
