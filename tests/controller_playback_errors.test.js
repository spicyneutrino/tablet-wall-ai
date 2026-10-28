"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const context = vm.createContext({ window: {} });
vm.runInContext(fs.readFileSync(path.join(__dirname, "../frontend/controller/physical-playback.js"), "utf8"), context);
class ApiError extends Error {
    constructor(status, detail) { super(detail); this.status = status; }
}
function setup(api) {
    const state = { playbackBusy: false, playlist: { items: [] }, playbackExclusions: [], configLoaded: false };
    const messages = [];
    const controller = context.window.PhysicalPlayback.create({
        ApiError, state, el: {}, API_PLAYBACK: "/api/v3/playback", api,
        clearMsg() {}, syncTopbarTransport() {}, errorDetail: error => error.message,
        isOnline: () => false, announce() {}, setMsg: (_node, text) => messages.push(text),
        maybeChooseInitialTab() {}, syncPlaylistCurrent() {}
    });
    return { state, messages, controller };
}
(async () => {
    let writes = 0;
    let reads = 0;
    const versions = [];
    const retry = setup(async (method, _route, _body, options) => {
        if (method === "GET") { reads += 1; return { state: "stopped", version: reads }; }
        writes += 1;
        versions.push(options.ifMatch);
        if (writes === 1) throw new ApiError(412, "version changed");
        return { state: "stopped", version: 4 };
    });
    await retry.controller.playbackAction("pause");
    assert.equal(writes, 2, "a version conflict retries the command once");
    assert.deepEqual(versions, ["1", "3"], "retry reads a fresh version immediately before writing");
    assert.deepEqual(retry.messages, []);
    assert.equal(retry.state.playbackBusy, false);

    const conflict = setup(async method => {
        if (method === "GET") return { state: "stopped", version: 1 };
        throw new ApiError(409, "physical layout is required");
    });
    await conflict.controller.playbackAction("resume");
    assert.deepEqual(conflict.messages, ["Apply a physical layout before starting playback."]);
    assert.equal(conflict.state.playbackBusy, false);

    let rejectedWrites = 0;
    const repeated = setup(async method => {
        if (method === "GET") return { state: "stopped", version: 1 };
        rejectedWrites += 1;
        throw new ApiError(412, "still changing");
    });
    await repeated.controller.playbackAction("stop");
    assert.equal(rejectedWrites, 2, "a repeated conflict must not loop forever");
    assert.deepEqual(repeated.messages, ["still changing"]);
    console.log("Controller playback error contracts passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
