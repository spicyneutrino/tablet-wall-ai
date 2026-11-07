"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { startHarness, createHarness, drain, deferred, wallFrame, imageContent, okResponse,
    assetBlob, route, VIDEO_CALIBRATION, VIDEO_PLAN } = require("./client_image.test.js");

function instruction(seq = 1, fields = {}) {
    const frame = wallFrame(Object.assign({ type: "render", mode: "logical", render_seq: seq }, fields));
    frame.token = { connection_id: "conn-1", generation: frame.generation, revision: frame.revision,
        render_seq: seq, mapping_revision: "mapping-" + seq,
        asset: frame.scene.content.type === "image" ? frame.scene.content.asset : null };
    return frame;
}
async function connected(t, opts = {}) {
    const h = await startHarness(opts);
    t.after(() => h.dispose());
    h.socket().readyState = 1;
    h.emit({ type: "welcome", connection_id: "conn-1", protocol: 3, number: 4, heartbeat_interval_ms: 5000 });
    h.setFetch(route({ ["a".repeat(64)]: okResponse(assetBlob("A", 400, 400)) }));
    return h;
}
const last = h => h.sent("render_ack").at(-1);
const displayed = h => h.sent("render_ack").filter(f => f.status === "displayed");

test("a successful draw needs a following animation frame; heartbeat refreshes strictly ordered evidence", async t => {
    const h = await connected(t);
    h.emit(instruction());
    await drain();
    assert.equal(h.named("drawImage").length, 1);
    assert.equal(displayed(h).length, 0);
    assert.equal(last(h).status, "loading");
    h.runAnimationFrames();
    assert.equal(last(h).status, "displayed");
    assert.deepEqual(Object.keys(last(h)).sort(), ["type", "token", "report_seq", "status", "reason", "viewport", "visible"].sort());
    assert.equal(last(h).viewport.visual_scale, 1);
    h.fireIntervals(5000);
    assert.equal(last(h).status, "displayed");
    const acks = h.sent("render_ack");
    for (let i = 1; i < acks.length; i++) assert.ok(acks[i].report_seq > acks[i - 1].report_seq);
    assert.match(h.socket().url, /render_ack,identify,image_contain/);
});

test("new tokens at the same revision repaint cached pixels and obsolete animation callbacks cannot report", async t => {
    const h = await connected(t);
    h.emit(instruction()); await drain();
    h.emit(instruction(2)); await drain();
    assert.equal(h.bitmapCalls(), 1);
    assert.equal(last(h).status, "loading");
    h.runAnimationFrames();
    assert.deepEqual(displayed(h).map(f => f.token.render_seq), [2]);
    h.emit(instruction(1));
    assert.equal(last(h).token.render_seq, 2);
});

test("logical wall-mode handoff and tokenless protocol2 wall frames remain compatible without invented evidence", async t => {
    const h = await connected(t);
    h.emit(instruction(1, { type: "wall" })); await drain(); h.runAnimationFrames();
    assert.equal(last(h).status, "displayed");
    const count = h.sent("render_ack").length;
    h.emit(wallFrame({ revision: 2 })); await drain(); h.runAnimationFrames(); h.fireIntervals(5000);
    assert.equal(h.sent("render_ack").length, count);
    assert.ok(h.named("drawImage").length >= 2);
});

test("malformed, wrong connection, mismatched duplicated fields and wrong assets cannot replace evidence", async t => {
    const h = await connected(t);
    h.emit(instruction()); await drain(); h.runAnimationFrames();
    const count = h.sent("render_ack").length;
    for (const patch of [{ connection_id: "other" }, { generation: "other" }, { revision: true },
        { render_seq: 3 }, { mapping_revision: "" }, { asset: null }, { extra: 1 }]) {
        const frame = instruction(2); Object.assign(frame.token, patch); h.emit(frame);
    }
    await drain(); h.runAnimationFrames();
    assert.equal(h.sent("render_ack").length, count);
});

test("stale decodes, failures and animation callbacks cannot cross token, generation, socket or viewport ownership", async t => {
    const h = await connected(t);
    const pending = deferred();
    let calls = 0;
    h.setBitmapImpl(blob => ++calls === 1 ? pending.promise : Promise.resolve(h.makeBitmap(blob)));
    h.emit(instruction()); await drain();
    h.emit(instruction(2, { generation: "gen-2", revision: 0 })); await drain();
    const bitmap = h.makeBitmap(assetBlob("old", 400, 400));
    pending.resolve(bitmap); await drain();
    assert.equal(bitmap.closed, true);
    h.runAnimationFrames();
    assert.deepEqual(displayed(h).map(f => f.token.generation), ["gen-2"]);
    const oldSocket = h.socket();
    h.closeSocket(1006); await drain();
    h.fireTimers(timer => timer.delay >= 500 && timer.delay <= 625); await drain();
    assert.equal(h.socketCount(), 2);
    h.socket().readyState = 1;
    h.emit({ type: "welcome", connection_id: "conn-2", number: 4 });
    oldSocket.emit("message", { data: JSON.stringify(instruction(9)) });
    const fresh = instruction(1, { generation: "gen-2", revision: 0 });
    fresh.token.connection_id = "conn-2";
    h.emit(fresh); await drain();
    h.window.innerWidth = 600;
    h.runAnimationFrames();
    assert.equal(displayed(h).length, 0);
});

test("hidden invalidates displayed evidence and resume requires a new paint and animation frame", async t => {
    const h = await connected(t);
    h.emit(instruction()); await drain(); h.runAnimationFrames();
    h.document.visibilityState = "hidden";
    h.listeners.document.visibilitychange.forEach(fn => fn());
    assert.equal(last(h).status, "hidden");
    assert.equal(last(h).visible, false);
    h.fireIntervals(5000);
    assert.equal(last(h).status, "hidden");
    const paints = h.named("drawImage").length;
    h.document.visibilityState = "visible";
    h.listeners.document.visibilitychange.forEach(fn => fn());
    assert.ok(h.named("drawImage").length > paints);
    assert.equal(last(h).status, "loading");
    h.runAnimationFrames();
    assert.equal(last(h).status, "displayed");
    await drain();
    assert.ok(h.sent("viewport").length > 0);
    assert.ok(h.fetchLog.filter(f => f.url === "/devices/register").length >= 2);
});

for (const [name, setup, reason] of [
    ["fetch", h => h.setFetch(() => ({ ok: false, status: 404 })), "fetch"],
    ["decode", h => h.setBitmapImpl(() => Promise.reject(new Error("invalid bytes"))), "decode"],
    ["size", h => h.setFetch(route({ ["a".repeat(64)]: okResponse(assetBlob("A", 0, 0)) })), "size"],
    ["surface", h => h.setContextAvailable(false), "surface"],
    ["drawImage", h => { h.ctx.drawImage = () => { throw new Error("lost surface"); }; }, "surface"],
    ["auth", h => h.setFetch(() => ({ ok: false, status: 401 })), "auth"],
]) test(name + " failures never display and report the specific reason", async t => {
    const h = await connected(t); setup(h);
    const frame = instruction();
    if (name === "size") { delete frame.scene.content.intrinsicWidth; delete frame.scene.content.intrinsicHeight; }
    h.emit(frame); await drain(); h.runAnimationFrames();
    assert.equal(displayed(h).length, 0);
    assert.equal(last(h).status, "failed");
    assert.equal(last(h).reason, reason);
});

test("physical image confirms only after drawing; unplaced, calibration, viewport, zoom and unsupported stay explicit", async t => {
    const h = await connected(t);
    const physical = { mode: "physical", calibration: VIDEO_CALIBRATION, plan: VIDEO_PLAN,
        slot: { center_x_mm: 0, center_y_mm: 0, mount_angle: 0 } };
    h.emit(instruction(1, physical)); await drain();
    assert.equal(displayed(h).length, 0);
    h.runAnimationFrames(); assert.equal(last(h).status, "displayed");
    h.emit(instruction(2, { ...physical, plan: null })); await drain();
    assert.equal(last(h).status, "blocked"); assert.equal(last(h).reason, "calibration");
    h.emit(instruction(3, { ...physical, plan: null, slot: null }));
    assert.equal(last(h).status, "unplaced");
    h.emit(instruction(4, { scene: { content: { type: "future" } } }));
    assert.equal(last(h).status, "unsupported");
    h.emit(instruction(5)); await drain();
    h.window.innerWidth = 600;
    h.listeners.window.resize.forEach(fn => fn());
    assert.equal(last(h).reason, "viewport");
    h.window.visualViewport = { scale: 2, width: 300, height: 300 };
    h.emit(instruction(6)); await drain();
    assert.equal(last(h).reason, "zoom");
});

test("physical color uses assigned CSS color with no image plan and keeps unplaced status explicit", async t => {
    const h = await connected(t);
    h.emit({ type: "set_color", color: "#e04040" });
    h.emit(instruction(1, { mode: "physical", plan: null, calibration: { status: "invalid" }, slot: null,
        scene: { content: { type: "color" } } }));
    assert.equal(h.canvas.style.display, "none");
    assert.equal(h.texts().includes("NEEDS CALIBRATION"), false);
    assert.equal(last(h).status, "unplaced");
    assert.equal(h.bitmapCalls(), 0);
});

test("a colour scene reports displayed after one animation frame", async t => {
    const h = await connected(t);
    h.emit(instruction(1, { scene: { content: { type: "color" } } }));
    await drain();
    assert.equal(displayed(h).length, 0, "evidence waits for a painted frame");
    assert.equal(last(h).status, "loading");
    h.runAnimationFrames();
    assert.equal(last(h).status, "displayed");
    assert.equal(last(h).token.asset, null);
    assert.deepEqual(Object.keys(last(h)).sort(), ["type", "token", "report_seq", "status", "reason", "viewport", "visible"].sort());
});

test("a colour scene stays silent when hidden, zoomed or unplaced", async t => {
    const h = await connected(t);
    h.document.visibilityState = "hidden";
    h.emit(instruction(1, { scene: { content: { type: "color" } } }));
    await drain(); h.runAnimationFrames();
    assert.equal(displayed(h).length, 0, "a hidden page cannot claim a painted scene");
    assert.equal(last(h).status, "hidden");
    h.document.visibilityState = "visible";
    h.window.visualViewport = { scale: 2, width: 300, height: 300 };
    h.emit(instruction(2, { scene: { content: { type: "color" } } }));
    await drain(); h.runAnimationFrames();
    assert.equal(displayed(h).length, 0, "a zoomed page cannot claim a painted scene");
    assert.equal(last(h).status, "blocked");
    h.window.visualViewport = undefined;
    h.emit(instruction(3, { scene: { content: { type: "color" } }, placement: null }));
    await drain(); h.runAnimationFrames();
    assert.equal(displayed(h).length, 0, "an unplaced tablet cannot claim a painted scene");
    assert.equal(last(h).status, "unplaced");
});

test("a logical calibration scene reports a surface failure without drawing and recovers after paint", async t => {
    const h = await connected(t);
    h.setContextAvailable(false);
    h.emit(instruction(1, { scene: { content: { type: "calibration" } } }));
    await drain();
    assert.equal(displayed(h).length, 0);
    assert.equal(h.named("drawImage").length, 0, "calibration draws the pattern, not the asset");
    h.runAnimationFrames();
    assert.equal(last(h).status, "failed");
    assert.equal(last(h).reason, "surface");

    h.setContextAvailable(true);
    h.emit(instruction(2, { scene: { content: { type: "calibration" } } }));
    await drain();
    assert.ok(h.named("stroke").length > 0, "a valid context draws the calibration pattern");
    assert.equal(displayed(h).length, 0, "the next animation frame still fences success");
    h.runAnimationFrames();
    assert.equal(last(h).status, "displayed");
    assert.deepEqual(displayed(h).map(f => f.token.render_seq), [2]);
    assert.equal(last(h).token.asset, null);
});

test("an unresponsive socket is retired even without close event, and reconnect preserves identity and number", async t => {
    const h = await connected(t);
    const original = JSON.parse(h.fetchLog[0].options.body).device_id;
    h.socket().close = () => {};
    h.advance(15001); h.fireIntervals(5000); await drain();
    h.fireTimers(timer => timer.delay >= 500 && timer.delay <= 625); await drain();
    assert.equal(h.socketCount(), 2);
    const registration = JSON.parse(h.fetchLog.filter(f => f.url === "/devices/register").at(-1).options.body);
    assert.equal(registration.device_id, original);
    assert.equal(registration.number, 4);
});

test("a stalled welcome is bounded and ordinary reconnect retains the client id", async t => {
    const h = await startHarness(); t.after(() => h.dispose());
    h.socket().close = () => {};
    h.fireTimers(timer => timer.delay === 10000); await drain();
    h.fireTimers(timer => timer.delay >= 500 && timer.delay <= 625); await drain();
    assert.equal(h.socketCount(), 2);
});

test("online and pageshow probe the live owner, but never retry after 4409 takeover", async t => {
    const h = await connected(t);
    for (const event of ["online", "pageshow"]) {
        h.listeners.window[event].forEach(fn => fn()); await drain();
    }
    assert.ok(h.sent("viewport").length >= 2);
    h.closeSocket(4409); await drain();
    const registrations = h.fetchLog.length;
    for (const event of ["online", "pageshow", "resize"]) h.listeners.window[event].forEach(fn => fn());
    h.fireIntervals(); h.fireTimers(timer => timer.delay < 1000); await drain();
    assert.equal(h.socketCount(), 1);
    assert.equal(h.fetchLog.length, registrations);
    assert.equal(h.status().state, "replaced");
});

for (const loginStatus of [200, 403, 404, 405]) test("401 pauses retry and exposes a same-origin action or deployment error for login " + loginStatus, async t => {
    const h = createHarness({ fetch: url => String(url).startsWith("/auth/login")
        ? { ok: loginStatus === 200, status: loginStatus } : { ok: false, status: 401 } });
    t.after(() => h.dispose()); await drain();
    const action = h.document.getElementById("auth-login");
    assert.equal(action.href, "/auth/login?next=%2Fclient%2F");
    assert.equal(action.hidden, loginStatus !== 200);
    assert.equal(h.status().state, loginStatus === 200 ? "auth" : "deployment");
    h.fireTimers(timer => timer.delay < 1000); h.fireIntervals(); await drain();
    assert.equal(h.fetchLog.filter(f => f.url === "/devices/register").length, 1);
    assert.equal(h.socketCount(), 0);
});


test("an old socket decode and queued close cannot paint or stop its replacement heartbeat", async t => {
    const h = await connected(t);
    const pending = deferred();
    h.setBitmapImpl(() => pending.promise);
    h.emit(instruction()); await drain();
    const old = h.socket(); h.closeSocket(1006); await drain();
    h.fireTimers(timer => timer.delay >= 500 && timer.delay <= 625); await drain();
    h.socket().readyState = 1;
    h.emit({ type: "welcome", connection_id: "conn-2", number: 4, heartbeat_interval_ms: 5000 });
    const bitmap = h.makeBitmap(assetBlob("old socket", 400, 400));
    pending.resolve(bitmap); await drain(); h.runAnimationFrames();
    assert.equal(bitmap.closed, true);
    assert.equal(h.named("drawImage").length, 0);
    old.emit("close", { code: 4409 });
    h.fireIntervals(5000);
    assert.equal(h.sent("heartbeat").length, 1);
    assert.equal(h.status().state, "connected");
});

test("viewport changes discard a pending decode and never paint it over a changed scene", async t => {
    const h = await connected(t);
    const pending = deferred();
    h.setBitmapImpl(() => pending.promise);
    h.emit(instruction()); await drain();
    h.window.innerWidth = 600;
    h.emit(instruction(2, { scene: { content: { type: "color" } } }));
    const bitmap = h.makeBitmap(assetBlob("old viewport", 400, 400));
    pending.resolve(bitmap); await drain(); h.runAnimationFrames();
    assert.equal(bitmap.closed, true);
    assert.equal(h.named("drawImage").length, 0);
    assert.deepEqual(displayed(h).map(f => f.token.render_seq), [2], "only the colour scene may report; the stale decode cannot");
});

test("surface recovery repaints before displayed and restores canvas clipping after a failed draw", async t => {
    const h = await connected(t);
    const draw = h.ctx.drawImage;
    h.ctx.drawImage = () => { throw new Error("surface lost"); };
    h.emit(instruction()); await drain();
    assert.equal(last(h).reason, "surface");
    assert.equal(h.named("save").length, h.named("restore").length);
    h.ctx.drawImage = draw;
    h.emit(instruction(2)); await drain();
    assert.equal(last(h).status, "loading");
    h.runAnimationFrames();
    assert.equal(last(h).status, "displayed");
});

test("normalized scene background overrides the opaque default and invalid colors retain #0b1120", async t => {
    const h = await connected(t);
    for (const [background, expected, seq] of [["#ABCDEF", "#abcdef", 1], ["transparent", "#0b1120", 2]]) {
        h.reset();
        h.emit(instruction(seq, { scene: { content: imageContent({ background }) } })); await drain();
        const draw = h.calls.map(c => c.name).lastIndexOf("drawImage");
        assert.equal(h.calls.slice(0, draw).filter(c => c.name === "setFillStyle").at(-1).args[0], expected);
    }
});

for (const [fit, expected] of [[undefined, [0, -1000, 2000, 3000]], ["contain", [2000 / 3, 0, 2000 / 3, 1000]]]) {
    test("prepared still " + fit + " uses its own fit and background over a static contain image", async t => {
        const h = await connected(t);
        h.emit(instruction(1, { scene: { content: imageContent({ fit: "contain" }) } })); await drain();
        h.emit({ type: "prepare", session_id: "session", version: 1, preparation_id: "prep",
            occurrence: { playlist_revision: 1, item_index: 0, loop: 0 }, connection_id: "conn-1",
            asset: { id: "sha256:" + "b".repeat(64), url: "/assets/still", intrinsicWidth: 1000, intrinsicHeight: 1500,
                fit, background: "#112233" } }); await drain();
        h.emit({ type: "commit", session_id: "session", version: 2, prepared_at_version: 1, preparation_id: "prep",
            occurrence: { playlist_revision: 1, item_index: 0, loop: 0 }, connection_id: "conn-1", effective_server_ms: h.now() + 100 });
        h.advance(100); h.fireTimers(timer => timer.delay === 60); h.runAnimationFrames(); await drain();
        const actual = h.named("drawImage").at(-1).args.slice(1);
        expected.forEach((value, i) => assert.ok(Math.abs(actual[i] - value) < 1e-8, actual));
        const drawIndex = h.calls.map(c => c.name).lastIndexOf("drawImage");
        assert.equal(h.calls.slice(0, drawIndex).filter(c => c.name === "setFillStyle").at(-1).args[0], "#112233");
        assert.equal(last(h).reason, "playback");
    });
}


test("a cache hit settles and releases a different picture still decoding", async t => {
    const h = await connected(t);
    h.setCreateImageBitmap(false);
    const other = "sha256:" + "b".repeat(64);
    h.setFetch(route({
        ["a".repeat(64)]: okResponse(assetBlob("A", 400, 400)),
        ["b".repeat(64)]: okResponse(assetBlob("B", 400, 400)),
    }));
    h.emit(instruction(1)); await drain(); h.runAnimationFrames();
    assert.equal(last(h).status, "displayed", "the first picture is cached and on the wall");
    assert.equal(h.objectUrls.filter(entry => !entry.revoked).length, 1);
    const abandoned = deferred();
    h.setImageBehaviour({ decode: () => abandoned.promise, load: () => {} });
    h.emit(instruction(2, { scene: { content: imageContent({ asset: other, url: "/assets/" + other }) } }));
    await drain();
    assert.equal(h.objectUrls.length, 2, "the second picture reached its object URL");
    assert.equal(h.objectUrls[1].revoked, false);
    assert.notEqual(h.images[1].src, "");
    h.emit(instruction(3)); await drain();
    assert.equal(h.objectUrls[1].revoked, true, "the abandoned decode must give back its object URL");
    assert.equal(h.images[1].src, "", "the abandoned <img> must stop pulling bytes");
    assert.equal(h.objectUrls[0].revoked, false, "the cached picture stays available");
    assert.equal(h.named("drawImage").at(-1).args[0], h.images[0]);
    abandoned.resolve(); await drain(); h.runAnimationFrames();
    assert.equal(h.named("drawImage").at(-1).args[0], h.images[0], "a late decode never paints over the cached picture");
    assert.equal(displayed(h).filter(f => f.token.render_seq === 2).length, 0, "the superseded picture never reports displayed");
    assert.equal(last(h).token.render_seq, 3);
    assert.equal(h.objectUrls[0].revoked, false);
});

test("superseding an image aborts its in-flight fetch immediately", async t => {
    class Controller {
        constructor() {
            const listeners = [];
            this.signal = { aborted: false, addEventListener: (_type, listener) => listeners.push(listener) };
            this.abort = () => { this.signal.aborted = true; listeners.forEach(listener => listener()); };
        }
    }
    const h = await connected(t, { AbortController: Controller });
    let signal;
    let firstAsset = true;
    h.setFetch((url, options) => {
        if (String(url).includes("/assets/") && firstAsset) {
            firstAsset = false;
            signal = options.signal;
            return new Promise((_resolve, reject) => signal.addEventListener("abort", () => {
                reject(Object.assign(new Error("request aborted"), { name: "AbortError" }));
            }));
        }
        if (String(url).includes("/assets/")) return okResponse(assetBlob("B", 400, 400));
        return { ok: true, status: 200 };
    });
    h.emit(instruction(1)); await drain();
    assert.equal(signal.aborted, false);
    h.emit(instruction(2, { scene: { content: { type: "color" } } })); await drain();
    assert.equal(signal.aborted, true, "obsolete network work should stop when the scene changes");
    await drain();
    assert.equal(h.sent("render_ack").some(frame => frame.status === "failed"), false,
        "the aborted obsolete fetch must not report a scene failure");
    h.emit(instruction(3)); await drain(); h.runAnimationFrames();
    assert.equal(last(h).status, "displayed", "the current image can still fetch, decode, and display");
    assert.equal(last(h).token.render_seq, 3);
});

for (const phase of ["headers", "body"]) test("a superseded image never decodes late " + phase + " without AbortController", async t => {
    const h = await connected(t);
    h.setCreateImageBitmap(false);
    h.setImageBehaviour({ decode: () => new Promise(() => {}), load: () => {} });
    const response = deferred(), body = deferred();
    h.setFetch(() => phase === "headers" ? response.promise : Promise.resolve({
        ok: true, status: 200, blob: () => body.promise,
    }));
    h.emit(instruction(1)); await drain();
    h.emit(instruction(2, { scene: { content: { type: "color" } } }));
    await drain(); h.runAnimationFrames();
    response.resolve(okResponse(assetBlob("late", 400, 400)));
    body.resolve(assetBlob("late", 400, 400));
    await drain();
    assert.equal(h.objectUrls.length, 0, "released work cannot allocate another object URL");
    assert.equal(h.images.length, 0, "released work cannot start another decoder");
    assert.equal(last(h).status, "displayed");
    assert.equal(last(h).token.render_seq, 2);
});

test("registration timeout stays bounded without AbortController and a late response cannot start a socket", async t => {
    const pending = deferred();
    const h = createHarness({ fetch: () => pending.promise }); t.after(() => h.dispose());
    await drain();
    h.fireTimers(timer => timer.delay === 10000); await drain();
    assert.equal(h.status().state, "offline");
    pending.resolve({ ok: true, status: 200 }); await drain();
    assert.equal(h.socketCount(), 0);
});

test("resume repaints even while an earlier registration probe is still pending", async t => {
    const h = await connected(t);
    h.emit(instruction()); await drain(); h.runAnimationFrames();
    const pending = deferred(); h.setFetch(() => pending.promise);
    h.listeners.window.online.forEach(fn => fn()); await drain();
    h.document.visibilityState = "hidden"; h.listeners.document.visibilitychange.forEach(fn => fn());
    h.document.visibilityState = "visible"; h.listeners.document.visibilitychange.forEach(fn => fn());
    assert.equal(last(h).status, "loading");
    h.runAnimationFrames(); assert.equal(last(h).status, "displayed");
    pending.resolve({ ok: true, status: 200 }); await drain();
});
