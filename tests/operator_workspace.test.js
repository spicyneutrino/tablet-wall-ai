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
    const workspace = window.OperatorWorkspace.create({ state: { mode: "content" }, arrangementDirty: () => draft.arrangement,
        arrangementPreview: () => draft.arrangement, imageDirty: () => draft.image,
        applyArrangement: async () => { draft.applied.push("arrangement"); draft.arrangement = false; },
        showImage: async () => { draft.applied.push("image"); draft.image = false; },
        discardArrangement: () => { draft.arrangement = false; }, discardImage: () => { draft.image = false; },
        commitMode() {}, renderStage() {}, refreshReadiness() {}, refreshStatus() {}, selectTablet() {}, canCommit: () => true });
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
        { window, document: { addEventListener() {}, getElementById: element, querySelector: () => element("stage"), activeElement: element("trigger") } });
    const calls = [];
    const workspace = window.OperatorWorkspace.create({ state, arrangementDirty: () => false,
        arrangementPreview: () => false, imageDirty: () => false,
        applyArrangement: async () => {}, showImage: async () => {}, discardArrangement() {}, discardImage() {},
        commitMode(name, taskOptions) {
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
    assert.equal(keyboard.document.activeElement, keyboard.element("tab-content"), "an invisible trigger uses a visible fallback");

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
    assert.equal(await issue.workspace.revealIssue("a", rowA, triggerA), true);
    assert.deepEqual(issue.calls.map(call => [call.kind, call.id]), [["select", "a"]], "recovery selection leaves the current mode in place");
    assert.deepEqual([issue.calls[0].options.reveal, issue.calls[0].options.trigger], [true, triggerA]);
    const removed = setupIssue();
    removed.state.operatorConfig.layout.slots = { b: {} };
    assert.equal(await removed.workspace.revealIssue("a", rowA, triggerA), false, "removed tablets cannot reveal stale recovery");
    assert.deepEqual(removed.calls, []);
    const detached = setupIssue();
    assert.equal(await detached.workspace.revealIssue("a", { isConnected: false }, triggerA), false);
    assert.deepEqual(detached.calls, []);
})().catch(error => { console.error(error); process.exitCode = 1; });

