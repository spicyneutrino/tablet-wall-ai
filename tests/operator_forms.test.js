"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const forms = require("../frontend/controller/operator-forms.js").create();
forms.observe("A", "name", { name: "Tablet 1" }, "original");
forms.edit("A", "name", { name: "Lobby left" }, "original");
forms.observe("B", "name", { name: "Tablet 2" }, "original");
assert.equal(forms.observe("A", "name", { name: "Tablet 1" }, "heartbeat").values.name, "Lobby left");
const submitted = forms.get("A", "name");
forms.edit("A", "name", { name: "Lobby left newer" }, "original");
forms.edit("B", "name", { name: "Keep B edit" }, "original");
forms.saved("A", "name", submitted.version, submitted.values, "returned");
assert.equal(forms.get("A", "name").dirty, true, "late A save cannot clear a newer A edit");
assert.equal(forms.get("B", "name").values.name, "Keep B edit", "A result cannot change selected B");
for (const group of ["profile", "calibration", "model"]) {
    forms.observe("A", group, { field: "baseline" }, "original");
    forms.edit("A", group, { field: "exact unsaved value" }, "original");
    assert.equal(forms.observe("A", group, { field: "baseline" }, "runtime").values.field, "exact unsaved value");
    assert.equal(forms.observe("A", group, { field: "remote changed" }, "changed").conflict, true);
    assert.equal(forms.get("A", group).baseEtag, "original");
}
console.log("Keyed names, measurements, model choices, conflicts and edit-version saves passed");

const beforeReview = forms.get("A", "profile");
assert.equal(forms.review("A", "profile", beforeReview.version - 1, { field: "remote" }, "fresh"), false, "an old comparison cannot authorize newer input");
assert.equal(forms.review("A", "profile", beforeReview.version, { field: "remote" }, "reviewed"), true);
assert.equal(forms.get("A", "profile").values.field, "exact unsaved value");
assert.equal(forms.get("A", "profile").baseEtag, "reviewed");

const grouped = require("../frontend/controller/operator-forms.js").create();
grouped.observe("A", "name", { name: "A" }, "base");
grouped.observe("A", "profile", { width: 100 }, "base");
grouped.edit("A", "profile", { width: 101 }, "base");
assert.equal(grouped.dirty(undefined, "profile"), true, "Settings can find measurement edits across tablets");
assert.equal(grouped.dirty(undefined, "name"), false, "measurement edits do not mark tablet naming dirty");
assert.equal(grouped.dirty("A"), true, "existing all-group guards still cover the tablet");

const sharedNames = require("./snapshot_names.json");
const rule = require("../frontend/controller/operator-forms.js").snapshotName;
const ruleText = "Use letters, numbers, spaces, dots, underscores or hyphens. Start with a letter or number. 64 characters at most.";
assert.equal(sharedNames.length >= 16, true, "the shared table has at least 16 cases");
for (const { raw, sent, expect } of sharedNames) {
    assert.equal(raw.trim(), sent, "Node trim produces the shared sent value for " + JSON.stringify(raw));
    assert.equal(rule(raw), expect, "the client accepts exactly the shared expect value for " + JSON.stringify(raw));
    assert.equal(forms.snapshotName(raw), expect, "the instance and module rules agree for " + JSON.stringify(raw));
    if (expect !== null) assert.equal(expect, sent, "an accepted name is sent unchanged");
}
assert.equal(rule(" Lobby "), "Lobby", "surrounding whitespace is trimmed before matching");
assert.equal(rule("Harbour dawn, fit"), null, "a comma is refused before any request");
assert.equal(rule("é"), null, "the rule is ASCII only");
assert.equal(rule("a".repeat(64)), "a".repeat(64), "64 characters is accepted");
assert.equal(rule("a".repeat(65)), null, "65 characters is refused");
console.log("The shared saved-name table agrees with Node and keeps the client acceptance rule on sent");

const controllerSource = fs.readFileSync(require.resolve("../frontend/controller/physical.js"), "utf8");
const ruleLiteral = /const SNAPSHOT_NAME_RULE = ("[^"]+");/.exec(controllerSource)[1];
assert.equal(JSON.parse(ruleLiteral), ruleText, "physical.js states the same rule sentence");

function formNode(value) {
    return { value, hidden: true, dataset: {}, textContent: "", focus() { this.focused = true; },
        addEventListener(type, handler) { this.listener = { type, handler }; } };
}
function show(label, text, detail) { label.textContent = text; label.dataset.kind = detail; label.hidden = !text; }

(async () => {
    {
        const input = formNode("Harbour dawn, fit"), message = formNode("");
        const requests = [];
        const context = vm.createContext({
            el: { layoutName: input, layoutMsg: message }, tabletForms: forms,
            state: { busy: false, savedLayouts: [], etag: "e", layoutKind: "logical" }, setMsg: show,
            resolveOutput: async () => true, setBusy() {}, ingestConfig() {}, loadLayouts: async () => {},
            handleWriteError() {}, API_LAYOUTS: "/api/v3/layouts",
            api: async (...args) => { requests.push(args); return { name: "saved" }; }
        });
        const start = controllerSource.indexOf("    async function saveLayout(event) {");
        const end = controllerSource.indexOf("    async function recallLayout(entry) {", start);
        vm.runInContext("const SNAPSHOT_NAME_RULE = " + ruleLiteral + ";\n" + controllerSource.slice(start, end), context);
        await context.saveLayout({ preventDefault() {} });
        assert.equal(requests.length, 0, "a refused arrangement name sends no request");
        assert.equal(input.focused, true, "a refused arrangement name keeps focus in its field");
        assert.equal(message.textContent, ruleText, "a refused arrangement name shows the rule");
        input.value = "Harbour dawn, fit"; input.focused = false;
        await context.saveLayout({ preventDefault() {} });
        assert.equal(requests.length, 0, "a second refused name is still not sent");
        input.value = " Lobby ";
        await context.saveLayout({ preventDefault() {} });
        assert.equal(requests.length, 1, "a valid arrangement name sends exactly one request");
        assert.equal(requests[0][1], "/api/v3/logical-layouts/Lobby", "the arrangement is sent with its trimmed name");
        input.value = "";
        await context.saveLayout({ preventDefault() {} });
        assert.equal(message.textContent, "Enter an arrangement name. " + ruleText, "an empty arrangement keeps its original prompt and the rule");
        assert.equal(requests.length, 1, "an empty arrangement sends nothing");
        console.log("Layout save validates the shared rule before sending and refocuses its field");
    }

    {
        const input = formNode("Harbour dawn, fit"), message = formNode("");
        let handler = null;
        const nodes = { "scene-save-form": { addEventListener(type, fn) { assert.equal(type, "submit"); handler = fn; } },
            "scene-name": input, "scene-message": message };
        const requests = [];
        const context = vm.createContext({
            document: { getElementById: id => nodes[id] || null }, tabletForms: forms, window: { confirm: () => true },
            setMsg: show, resolveOutput: async () => true, ingestConfig() {}, loadScenes: async () => {},
            api: async (...args) => { requests.push(args); return {}; }
        });
        const start = controllerSource.indexOf('document.getElementById("scene-save-form").addEventListener("submit"');
        const end = controllerSource.indexOf("\n        });", start) + 12;
        vm.runInContext("const SNAPSHOT_NAME_RULE = " + ruleLiteral + "; let savedScenes = [];\n" + controllerSource.slice(start, end), context);
        await handler({ preventDefault() {} });
        assert.equal(requests.length, 0, "a refused content name sends no request");
        assert.equal(input.focused, true, "a refused content name keeps focus in its field");
        assert.equal(message.textContent, ruleText, "a refused content name shows the rule");
        input.value = " Lobby ";
        await handler({ preventDefault() {} });
        assert.equal(requests.length, 1, "a valid content name sends exactly one request");
        assert.equal(requests[0][1], "/api/v3/scenes/Lobby", "the content is sent with its trimmed name");
        input.value = "";
        await handler({ preventDefault() {} });
        assert.equal(message.textContent, "Enter a content name. " + ruleText, "an empty content name keeps its original prompt and the rule");
        assert.equal(requests.length, 1, "an empty content name sends nothing");
        console.log("Scene save validates the shared rule before sending and refocuses its field");
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
