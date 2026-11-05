"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const model = require("../frontend/controller/operator-state.js");

function fixture() {
    const nodes = new Map(), requests = [], reads = [];
    function node(id) {
        if (!nodes.has(id)) nodes.set(id, { dataset: {}, value: "", hidden: false, disabled: false, textContent: "", attrs: {},
            files: [{ name: "sample.jpg", type: "image/jpeg" }],
            addEventListener(type, fn) { this[type] = fn; }, replaceChildren() {}, add() {},
            getAttribute(key) { return this.attrs[key]; }, removeAttribute(key) { delete this.attrs[key]; } });
        return nodes.get(id);
    }
    class Request {
        constructor() { this.upload = {}; requests.push(this); }
        open() {} setRequestHeader() {} send() {}
        async reply(status, body) {
            this.status = status; this.responseText = body;
            const finished = this.onload(); this.onloadend(); await finished;
        }
    }
    const state = { layoutKind: "logical", etag: "current", etagState: "current", capabilities: { uploads: true },
        scene: { content: { type: "color" } } };
    const context = vm.createContext({ window: { OperatorState: model }, document: { getElementById: node },
        Option: function () {}, XMLHttpRequest: Request });
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-dom.js"), "utf8"), context);
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/controller/operator-content.js"), "utf8"), context);
    const content = context.window.OperatorContent.create({ state, renderStage() {}, announce() {}, showConflict() {},
        api(method, path) {
            assert.equal(method, "GET"); assert.equal(path, "/api/v3/images");
            return new Promise((resolve, reject) => reads.push({ resolve, reject }));
        } });
    const submit = () => node("upload-form").submit({ preventDefault() {} });
    return { node, requests, reads, content, submit, state };
}

(async () => {
    for (const [status, body] of [[500, "{}"], [502, "upstream unavailable"], [503, '{"detail":"late failure"}'],
        [201, "invalid json"], [201, "null"], [201, "{}"], [201, '{"asset":{}}']]) {
        const f = fixture();
        const oldRead = f.content.refresh();
        f.submit(); await f.requests[0].reply(status, body);
        assert.match(f.node("upload-message").textContent, /completion is uncertain/);
        assert.equal(f.node("upload-submit").disabled, true);
        f.submit(); assert.equal(f.requests.length, 1, "ambiguous completion blocks another transport send");
        f.reads[0].resolve({ images: [] }); await oldRead;
        assert.equal(f.node("upload-submit").disabled, true, "a read begun before uncertainty cannot reconcile it");
        assert.equal(f.node("refresh-images").disabled, false);
        const failedRead = f.content.refresh();
        f.reads[1].reject(new Error("offline")); await failedRead;
        assert.equal(f.node("upload-submit").disabled, true, "failed inventory refresh keeps the lock");
        const reconciled = f.content.refresh();
        f.reads[2].resolve({ images: [] }); await reconciled;
        assert.equal(f.node("upload-submit").disabled, false);
        f.submit(); assert.equal(f.requests.length, 2, "successful explicit inventory refresh permits reviewed retry");
        assert.equal(f.state.scene.content.type, "color", "uploads never change the wall");
    }
    for (const status of [400, 403, 413, 415, 422, 429]) {
        const f = fixture(); f.submit(); await f.requests[0].reply(status, '{"detail":"Known refusal"}');
        assert.match(f.node("upload-message").textContent, /Image addition refused/);
        assert.equal(f.node("upload-submit").disabled, false);
    }
    console.log("Upload ambiguity, stale inventory, reconciliation and known refusals passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
