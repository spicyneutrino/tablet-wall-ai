"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { startHarness, drain, wallFrame, imageContent, okResponse, assetBlob, route } = require("./client_image.test.js");
async function connected(t, opts) {
    const h = await startHarness(opts); t.after(() => h.dispose());
    h.socket().readyState = 1;
    h.emit({ type: "welcome", connection_id: "conn-1", protocol: 3, number: 4 });
    h.emit(wallFrame({ scene: { content: { type: "color" } } }));
    return h;
}
function command(h, fields = {}) {
    return { type: "identify", command_id: "identify-1", connection_id: "conn-1", generation: "gen-1",
        server_ms: h.now(), expires_ms: h.now() + 5000, remaining_ms: 5000, duration_ms: 5000,
        number: 4, label: "North <img src=x onerror=alert(1)>", ...fields };
}
const overlay = h => h.document.getElementById("identify");

test("Identify is plain text, acknowledges shown after a frame, and expiry reveals the latest image", async t => {
    const h = await connected(t);
    h.emit(command(h));
    assert.equal(overlay(h).hidden, false);
    assert.equal(h.document.getElementById("identify-number").textContent, "#4");
    assert.equal(h.document.getElementById("identify-label").textContent, "North <img src=x onerror=alert(1)>");
    assert.equal(h.sent("identify_status").length, 0);
    h.runAnimationFrames();
    assert.equal(h.sent("identify_status").at(-1).status, "shown");
    h.setFetch(route({ ["b".repeat(64)]: okResponse(assetBlob("new-scene", 400, 400)) }));
    h.emit(wallFrame({ revision: 2, scene: { content: imageContent({ asset: "sha256:" + "b".repeat(64),
        url: "/assets/sha256:" + "b".repeat(64) }) } }));
    await drain();
    const paints = h.named("drawImage").length;
    assert.ok(paints > 0);
    h.advance(5000); h.fireTimers(timer => timer.delay === 5000);
    assert.equal(overlay(h).hidden, true);
    assert.equal(h.sent("identify_status").at(-1).status, "cleared");
    assert.equal(h.named("drawImage").length, paints);
    assert.equal(h.named("drawImage").at(-1).args[0].tag, "new-scene");
});

test("newer Identify replaces the old command and obsolete animation or expiry callbacks cannot clear it", async t => {
    const h = await connected(t);
    h.emit(command(h, { remaining_ms: 1000, expires_ms: h.now() + 1000 }));
    h.emit(command(h, { command_id: "identify-2", number: 9, label: "South" }));
    h.runAnimationFrames();
    assert.deepEqual(h.sent("identify_status").map(f => [f.command_id, f.status]),
        [["identify-1", "cleared"], ["identify-2", "shown"]]);
    h.fireTimers(timer => timer.delay === 1000);
    assert.equal(overlay(h).hidden, false);
    assert.equal(h.document.getElementById("identify-number").textContent, "#9");
});

test("wrong connection, generation, malformed and expired commands do not show", async t => {
    const h = await connected(t);
    for (const fields of [{ connection_id: "other" }, { generation: "other" }, { remaining_ms: 0 },
        { expires_ms: h.now() - 1 }, { server_ms: "1000" }, { duration_ms: true },
        { number: true }, { label: "bad\nlabel" }, { command_id: "" }]) h.emit(command(h, fields));
    h.runAnimationFrames();
    assert.equal(overlay(h).hidden, true);
    assert.equal(h.sent("identify_status").length, 0);
});

for (const [duration, expected] of [[undefined, 5000], [1, 1000], [50000, 10000]]) {
    test("Identify duration " + duration + " is defaulted or clamped and never extended by a redraw", async t => {
        const h = await connected(t);
        h.emit(command(h, { duration_ms: duration, remaining_ms: 20000, expires_ms: h.now() + 20000 }));
        h.emit(command(h, { duration_ms: duration, remaining_ms: 20000, expires_ms: h.now() + 20000 }));
        h.fireTimers(timer => timer.delay === expected);
        assert.equal(overlay(h).hidden, true);
        assert.equal(h.sent("identify_status").filter(f => f.status === "cleared").length, 1);
    });
}

test("server clock estimate and writer remaining duration both shorten Identify deadlines", async t => {
    const h = await connected(t);
    h.emit({ type: "clock_bootstrap", epoch: "epoch-1" });
    h.fireTimers(timer => timer.delay === 0);
    const sample = h.sent("clock_sample").at(-1);
    h.emit({ type: "clock_sample", id: sample.id, c0: sample.c0, s1: sample.c0 + 2000, s2: sample.c0 + 2000 });
    h.emit(command(h));
    assert.ok(h.fireTimers(timer => timer.delay === 3000) > 0);
    assert.equal(overlay(h).hidden, true);
    h.emit(command(h, { command_id: "identify-2", remaining_ms: 250 }));
    h.fireTimers(timer => timer.delay === 250);
    assert.equal(overlay(h).hidden, true);
});

for (const event of ["disconnect", "pagehide", "takeover", "generation", "resumeexpired"]) {
    test("Identify clears on " + event + " without replaying the command", async t => {
        const h = await connected(t);
        h.emit(command(h)); h.runAnimationFrames();
        if (event === "disconnect" || event === "takeover") h.closeSocket(event === "takeover" ? 4409 : 1006);
        if (event === "pagehide") h.listeners.window.pagehide.forEach(fn => fn());
        if (event === "generation") h.emit(wallFrame({ generation: "gen-2", scene: { content: { type: "color" } } }));
        if (event === "resumeexpired") {
            h.document.visibilityState = "hidden";
            h.listeners.document.visibilitychange.forEach(fn => fn());
            h.advance(5001);
            h.document.visibilityState = "visible";
            h.listeners.window.pageshow.forEach(fn => fn());
        }
        await drain(); h.runAnimationFrames();
        assert.equal(overlay(h).hidden, true);
        assert.equal(h.sent("identify_status").at(-1).status,
            event === "disconnect" || event === "takeover" ? "shown" : "cleared");
    });
}


test("resume expires Identify even when the platform paused its performance clock during sleep", async t => {
    let wallNow = 1000;
    class SleepDate extends Date { static now() { return wallNow; } }
    const h = await connected(t, { Date: SleepDate });
    h.emit(command(h)); h.runAnimationFrames();
    wallNow += 5001;
    h.listeners.window.pageshow.forEach(fn => fn());
    assert.equal(overlay(h).hidden, true);
    assert.equal(h.sent("identify_status").at(-1).status, "cleared");
    await drain();
});
