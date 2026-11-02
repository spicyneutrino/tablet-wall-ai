"use strict";
const assert = require("node:assert/strict");
const { create } = require("../frontend/controller/operator-session.js");
const config = (etag, paint = "loading") => ({ etag, revision: 1, generation: "session", layout: { kind: "logical", width: 100, height: 100, placements: {} }, runtime: { devices: { a: { online: true, render: { state: paint } } } } });
(async () => {
    let pending, latest = config("first"), fail = false;
    const session = create({ clock: () => 100, syncFactory: { create({ ingestConfig }) { return { start() {}, destroy() {}, async reconcile() { ingestConfig(latest, { remote: true, preserveDraft: true }); } }; } },
        transport: async () => { if (fail) throw new Error("network"); return new Promise(resolve => { pending = payload => resolve({ ok: true, json: async () => payload }); }); } });
    session.ingest(latest);
    assert.equal(session.state, undefined, "session does not expose mutable authority");
    assert.throws(() => { session.view().config.runtime.devices.a.online = false; }, TypeError);
    const old = session.request("PUT", "/api/v3/scene", { content: { type: "color" } }, { etag: true });
    await assert.rejects(() => session.request("POST", "/api/v3/layout/clear", { confirm: true }, { etag: true }), /progress/);
    latest = config("returned", "displayed"); session.ingest(latest, { remote: true });
    pending(config("returned", "loading"));
    assert.equal((await old).runtime.devices.a.render.state, "displayed", "late command response cannot regress newer runtime with the same durable ETag");
    const changed = session.request("PUT", "/api/v3/scene", {}, { etag: true });
    latest = config("another-operator", "displayed"); session.ingest(latest, { remote: true });
    pending(config("own-command", "loading"));
    const receipt = await changed;
    assert.equal(receipt.etag, "another-operator", "a late receipt cannot replace newer authority");
    assert.equal(receipt.commandEtag, "own-command", "the command guard remains the actual returned guard, separate from newer authority");
    fail = true;
    await assert.rejects(() => session.request("PATCH", "/api/v3/devices/a", { label: "A" }, { etag: true }), /uncertain/);
    assert.equal(session.view().uncertain, true);
    await assert.rejects(() => session.request("PATCH", "/api/v3/devices/a", { label: "A" }, { etag: true }), /may have completed/);
    await session.refresh(); assert.equal(session.view().uncertain, false, "explicit refresh clears uncertainty only after reconciliation");
    session.destroy();
    for (const status of [500, 502, 503]) {
        let writes = 0;
        const failing = create({ syncFactory: { create({ ingestConfig }) { return {
            start() {}, destroy() {}, async reconcile() { ingestConfig(config("after-reconciliation")); }
        }; } }, transport: async (_path, options) => {
            if (options.method === "GET") return { ok: true, json: async () => config("read") };
            writes += 1;
            return { ok: false, status, json: async () => ({ detail: "Server failed after processing the command" }) };
        } });
        failing.ingest(config("before-command"));
        await assert.rejects(() => failing.request("PATCH", "/api/v3/devices/a", { label: "Saved name" }, { etag: true }),
            error => error.status === status && error.uncertain && /uncertain/i.test(error.message));
        assert.equal(failing.view().uncertain, true, "server errors cannot establish that a command did not commit");
        await assert.rejects(() => failing.request("PATCH", "/api/v3/devices/a", { label: "Retry" }, { etag: true }), /may have completed/);
        assert.equal(writes, 1, "another write is refused before transport until the operator reconciles");
        await failing.request("GET", "/api/v3/config");
        failing.ingest(config("socket-update"));
        assert.equal(failing.view().uncertain, true, "an incidental snapshot does not acknowledge an uncertain command");
        await failing.refresh();
        assert.equal(failing.view().uncertain, false);
        failing.destroy();
    }
    console.log("Readonly session, command serialization, late response adoption and uncertainty fences passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
