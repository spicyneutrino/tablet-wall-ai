"use strict";
const fs = require("node:fs"), vm = require("node:vm"), assert = require("node:assert/strict");
const source = fs.readFileSync(require.resolve("../frontend/controller/physical.js"), "utf8");
const fragment = source.slice(source.indexOf("        const clearConfirm ="), source.indexOf("        const newModelReview ="));
const nodes = new Map(), writes = [], messages = [];
const state = { etag: "reviewed" };
const document = { getElementById(id) {
    if (!nodes.has(id)) nodes.set(id, { hidden: true, handlers: {}, focus() {}, setAttribute() {}, addEventListener(event, handler) { this.handlers[event] = handler; } });
    return nodes.get(id);
} };
vm.runInNewContext(fragment, { document, state, resolveOutput: async () => true,
    api: async (method, path, body, options) => { writes.push(options); return {}; },
    ingestConfig() {}, announce: text => messages.push(text), handleWriteError(error) { throw error; } });
const click = id => nodes.get(id).handlers.click();
(async () => {
    await click("clear-wall");
    state.etag = "another-operator";
    await click("clear-wall-confirm-yes");
    assert.equal(writes.length, 0);
    assert.match(messages.at(-1), /Review Clear wall again/);
    await click("clear-wall");
    await click("clear-wall-confirm-yes");
    assert.equal(writes.length, 1);
    assert.equal(writes[0].ifMatch, "another-operator");
    await click("clear-wall");
    await click("clear-wall-cancel");
    await click("clear-wall-confirm-yes");
    assert.equal(writes.length, 1);
    console.log("Clear wall rejects stale and cancelled reviews and pins the reviewed revision");
})().catch(error => { console.error(error); process.exitCode = 1; });
