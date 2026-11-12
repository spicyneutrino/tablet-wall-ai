"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const model = require("../frontend/controller/operator-state.js");

function fixture(file = { name: "sample.jpg", type: "image/jpeg" }) {
    const nodes = new Map(), requests = [], reads = [], writes = [], conflicts = [];
    function node(id) {
        if (!nodes.has(id)) nodes.set(id, { dataset: {}, value: "", hidden: false, disabled: false, textContent: "", attrs: {},
            files: [file],
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
    const controls = { writeReply: () => Promise.resolve({ generation: "g", revision: 1 }) };
    const content = context.window.OperatorContent.create({ state, renderStage() {}, announce() {},
        showConflict(reason) { conflicts.push(reason); }, ingestConfig() {},
        api(method, path, body, options) {
            if (method === "GET" && path === "/api/v3/images") {
                return new Promise((resolve, reject) => reads.push({ resolve, reject }));
            }
            if (method === "PUT" && path === "/api/v3/scene") {
                writes.push({ body, options });
                return controls.writeReply({ body, options });
            }
            return Promise.reject(new Error("unexpected request " + method + " " + path));
        } });
    const submit = () => node("upload-form").submit({ preventDefault() {} });
    return { node, requests, reads, writes, conflicts, content, submit, state, controls };
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
    {
        const f = fixture();
        f.state.capabilities.uploads = false;
        f.content.render();
        assert.equal(f.node("upload-form").hidden, true, "refused admission hides the upload form");
        f.submit();
        assert.equal(f.requests.length, 0, "refused admission never sends a transport");
        f.state.capabilities = {};
        f.content.render();
        assert.equal(f.node("upload-form").hidden, true, "unknown admission hides the upload form");
        f.submit();
        assert.equal(f.requests.length, 0, "unknown admission never sends a transport");
    }
    const uploaded = { id: "sha256:new", name: "new.png", width: 10, height: 10, url: "/new", thumbnail_url: "/new" };
    const body = JSON.stringify({ asset: uploaded });
    {
        const f = fixture();
        f.submit();
        const finished = f.requests[0].reply(201, body);
        await new Promise(resolve => setImmediate(resolve));
        assert.equal(f.reads.length, 1, "a successful upload reads the library after admission");
        assert.match(f.node("upload-message").textContent, /Image added and selected/);
        assert.equal(f.state.previewContent.asset, "sha256:new", "an unchanged selection may adopt the uploaded asset");
        f.reads[0].resolve({ images: [uploaded] });
        await finished;
        assert.equal(f.state.previewContent.asset, "sha256:new");
        assert.equal(f.state.scene.content.type, "color", "upload selection never shows the wall");
        f.content.previewScene({ name: "After settled upload", content: { type: "image", asset: "sha256:later" } }, "e");
        assert.match(f.node("upload-message").textContent, /Image added to the library/);
        assert.doesNotMatch(f.node("upload-message").textContent, /added and selected/);
    }
    {
        const f = fixture();
        f.submit();
        f.content.previewScene({ name: "Operator choice", content: { type: "image", asset: "sha256:operator" } }, "e");
        const finished = f.requests[0].reply(201, body);
        await new Promise(resolve => setImmediate(resolve));
        assert.equal(f.reads.length, 1);
        assert.match(f.node("upload-message").textContent, /Image added to the library/);
        assert.equal(f.state.previewContent.asset, "sha256:operator", "a later operator selection wins over the upload");
        f.reads[0].resolve({ images: [uploaded] });
        await finished;
        assert.equal(f.state.previewContent.asset, "sha256:operator", "the upload never replaces a newer selection");
        assert.equal(f.state.scene.content.type, "color");
    }
    {
        const f = fixture();
        f.submit();
        const finished = f.requests[0].reply(201, body);
        await new Promise(resolve => setImmediate(resolve));
        f.content.previewScene({ name: "Later choice", content: { type: "image", asset: "sha256:operator" } }, "e");
        f.reads[0].resolve({ images: [uploaded] });
        await finished;
        assert.equal(f.state.previewContent.asset, "sha256:operator");
        assert.match(f.node("upload-message").textContent, /Image added to the library/);
        assert.doesNotMatch(f.node("upload-message").textContent, /added and selected/);
    }
    for (const [label, file, expected] of [
        ["a still image", { name: "sample.jpg", type: "image/jpeg" }, 120000],
        ["an MP4 video", { name: "clip.mp4", type: "video/mp4" }, 750000],
        ["a QuickTime video", { name: "phone.mov", type: "video/quicktime" }, 750000],
        ["an MP4 suffix with an opaque type", { name: "CLIP.MP4", type: "application/octet-stream" }, 750000],
        ["a MOV suffix with no type", { name: "phone.mov", type: "" }, 750000],
        ["an unknown kind", { name: "notes.bin", type: "text/plain" }, 120000],
    ]) {
        const f = fixture(file);
        f.submit();
        assert.equal(f.requests.length, 1, label + " sends one transport");
        assert.equal(f.requests[0].timeout, expected, label + " selects that kind's browser deadline");
        f.requests[0].onloadend();
    }
    {
        const f = fixture({ name: "clip.mp4", type: "video/mp4" });
        f.submit();
        const request = f.requests[0];
        request.status = 0;
        request.ontimeout(); request.onloadend();
        assert.match(f.node("upload-message").textContent, /completion is uncertain/);
        assert.equal(f.node("upload-submit").disabled, true);
        assert.equal(f.state.scene.content.type, "color", "a lost video response never changes the wall");
        const sent = f.requests.length;
        f.submit();
        assert.equal(f.requests.length, sent, "an uncertain receipt blocks another transport before review");
        const reconciled = f.content.refresh();
        assert.equal(f.reads.length, 1, "the operator must read the library before retrying");
        f.reads[0].resolve({ images: [uploaded] });
        await reconciled;
        assert.equal(f.node("upload-submit").disabled, false);
        assert.equal(f.state.previewContent, null, "reconciling a published asset never auto-shows it");
        assert.equal(f.state.scene.content.type, "color");
        f.submit();
        assert.equal(f.requests.length, sent + 1, "a reviewed library permits the retry");
    }
    {
        const f = fixture({ name: "clip.mp4", type: "video/mp4" });
        f.submit();
        f.requests[0].status = 0;
        f.requests[0].onerror(); f.requests[0].onloadend();
        assert.match(f.node("upload-message").textContent, /completion is uncertain/);
        assert.equal(f.node("upload-submit").disabled, true);
        assert.equal(f.state.scene.content.type, "color", "a transport abort before publication never changes the wall");
    }
    {
        const f = fixture();
        f.state.base = { kind: "logical", width: 1000, height: 500, sizing: { mode: "tablets", padding: 0 }, placements: {} };
        f.submit();
        const finished = f.requests[0].reply(201, body);
        await new Promise(resolve => setImmediate(resolve));
        f.reads[0].resolve({ images: [uploaded] });
        await finished;
        assert.equal(f.state.previewContent.asset, uploaded.id);
        assert.equal(f.state.previewContent.fit, "cover", "a new image keeps the default fit");
        assert.equal(f.state.previewContent.background, "#0b1120", "a new image keeps the canonical background");
        assert.match(f.node("fit-summary").textContent, /^Preview Fill/);
        f.node("image-fit").change({ target: { value: "contain" } });
        await new Promise(resolve => setImmediate(resolve));
        assert.equal(f.state.previewContent.fit, "contain");
        assert.equal(f.state.previewContent.background, "#0b1120", "changing fit retains the background");
        assert.match(f.node("fit-summary").textContent, /^Preview Fit/);
        assert.equal(f.node("crop-width").textContent, "50% of wall width uncovered");
        f.controls.writeReply = () => Promise.reject(Object.assign(new Error("wall changed"), { status: 412 }));
        assert.equal(await f.content.showSelected(), false);
        assert.equal(f.content.dirty(), true, "412 retains the preview");
        assert.equal(f.state.previewContent.asset, uploaded.id);
        assert.equal(f.state.previewContent.fit, "contain");
        assert.equal(f.state.scene.content.type, "color", "412 never mutates the wall");
        assert.equal(f.writes.length, 1);
        assert.equal(f.writes[0].options.ifMatch, "current", "the original ETag guard is retained");
        assert.equal(f.conflicts.length, 1, "412 shows the retained-proposal conflict");
        f.content.previewScene({ name: "Custom background", content: { type: "image", asset: uploaded.id,
            fit: "contain", background: "#ABCDEF" } }, "custom");
        assert.equal(f.state.previewContent.background, "#abcdef", "a custom saved background is normalized and retained");
        assert.equal(f.state.previewContent.fit, "contain");
    }
    console.log("Upload deadlines, lost-publication recovery, ambiguity, stale inventory, refusals, ETag retention and selection-version admission passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
