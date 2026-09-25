/*
 * Focused, no-dependency tests for the tablet client's image renderer.
 *
 *     node tests/client_image.test.js
 *
 * client.js is an IIFE that talks straight to the DOM, so this harness runs
 * it inside a `vm` sandbox with a mocked document / window / canvas /
 * fetch / WebSocket, and drives it exactly the way the server does: by
 * handing its device socket a `wall` frame. The canvas mock records every
 * draw call, which is how the tests see the wall-space rectangle, the
 * transform and the panels the client chose.
 *
 * What is covered (PROTOCOL.md "Still images" + the Phase 2b contract):
 *   - the image rectangle is computed from the wall and the image only —
 *     identically on two adjacent tablets, so the seam is continuous;
 *   - nothing is painted before the asset has decoded, and an opaque underlay
 *     is painted before every picture (alpha PNGs);
 *   - an in-flight load that a newer token/generation/revision supersedes, or
 *     whose 15 s deadline expires, is discarded (and its bitmap released)
 *     rather than painted late — and a stale callback never retries;
 *   - the `<img>` fallback decodes the Blob already fetched through an object
 *     URL (ONE network request) and revokes it on replace / drop / timeout,
 *     cancelling the load itself — a late onload or decode() still paints
 *     nothing;
 *   - a retained picture stays up under an unmistakable loading banner;
 *   - a failed load shows IMAGE FAILED + short asset id + a working retry,
 *     an unusable descriptor says to fix it in the controller instead of
 *     promising a tap that cannot help, and releasing a decoded bitmap (scene
 *     change, unplaced, or a failed replacement) closes it rather than
 *     holding up to 12 MP for nothing;
 *   - an unplaced tablet fetches nothing at all until it is placed;
 *   - a missing 2d context is transient: the image stays READY and repaints;
 *   - the `<img>` fallback survives Safari rejecting decode() before onload;
 *   - colour, unknown-type, resize and reconnect behaviour is unchanged.
 */

"use strict";

const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { webcrypto } = require("node:crypto");

const CLIENT_JS = path.join(__dirname, "..", "frontend", "client", "client.js");
const CLIENT_SOURCE = fs.readFileSync(CLIENT_JS, "utf8");

const ORIGIN = "http://wall.test";
const ORIGIN_HREF = ORIGIN + "/client/";
const ZERO_BEZEL = { top: 0, right: 0, bottom: 0, left: 0 };

/* Viewport both tablets use: 800x600 CSS pixels, dpr 1. Their visible rects
 * are 1000x1000 wall units, so the cover scale is max(800/1000, 600/1000). */
const VP = { width: 800, height: 600, dpr: 1 };
const COVER_SCALE = Math.max(VP.width / 1000, VP.height / 1000); // 0.8

/* Mirrors IMAGE_LOAD_TIMEOUT_MS in client.js: the harness fires this timer
 * directly rather than waiting out the real fifteen seconds. */
const IMAGE_LOAD_TIMEOUT_MS = 15000;

/* ------------------------------------------------------------------ */
/* Harness                                                            */
/* ------------------------------------------------------------------ */

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((res, rej) => {
        resolve = res;
        reject = rej;
    });
    return { promise, resolve, reject };
}

function createHarness(opts = {}) {
    const calls = [];
    const docListeners = {};
    const winListeners = {};
    const sockets = [];
    const bitmaps = [];
    const warnings = [];
    const fetchLog = [];

    const RECORDED = [
        "setTransform",
        "save",
        "restore",
        "beginPath",
        "rect",
        "clip",
        "fillRect",
        "strokeRect",
        "drawImage",
        "moveTo",
        "lineTo",
        "stroke",
        "fill",
        "arc",
        "fillText",
    ];

    const ctx = {};
    for (const name of RECORDED) {
        ctx[name] = (...args) => {
            calls.push({ name, args });
        };
    }
    ctx.measureText = (text) => ({ width: String(text).length * 8 });

    /* fillStyle is a property, not a method — track writes so a test can
     * prove what was painted *under* the picture (an alpha PNG must never
     * show the previous frame through it). */
    let fillStyle = "#000000";
    Object.defineProperty(ctx, "fillStyle", {
        get() {
            return fillStyle;
        },
        set(value) {
            fillStyle = value;
            calls.push({ name: "setFillStyle", args: [value] });
        },
        enumerable: true,
        configurable: true,
    });

    /* Simulate a canvas whose 2d context cannot be had (a surface the
     * browser will not give us yet). */
    let contextAvailable = opts.contextAvailable !== false;

    const canvas = {
        width: 0,
        height: 0,
        style: {},
        setAttribute() {},
        getContext(kind) {
            return kind === "2d" && contextAvailable ? ctx : null;
        },
    };

    const documentMock = {
        getElementById(id) {
            return id === "surface" ? canvas : null;
        },
        documentElement: {
            clientWidth: opts.width || VP.width,
            clientHeight: opts.height || VP.height,
            style: { setProperty() {} },
        },
        createElement() {
            return canvas;
        },
        body: { appendChild() {} },
        addEventListener(type, fn) {
            (docListeners[type] = docListeners[type] || []).push(fn);
        },
    };

    const windowMock = {
        innerWidth: opts.width || VP.width,
        innerHeight: opts.height || VP.height,
        devicePixelRatio: opts.dpr !== undefined ? opts.dpr : VP.dpr,
        location: {
            protocol: "http:",
            host: "wall.test",
            href: ORIGIN_HREF,
            origin: ORIGIN,
        },
        addEventListener(type, fn) {
            (winListeners[type] = winListeners[type] || []).push(fn);
        },
    };

    /* Always resolves to a promise: client.js chains `.then` on it. The
     * router defaults to a successful, body-less response (registration). */
    let fetchImpl = () => ({ ok: true, status: 200 });
    function fetchMock(url, options) {
        fetchLog.push({ url, options });
        return Promise.resolve().then(() => fetchImpl(url, options));
    }

    function makeBitmap(blob) {
        const bitmap = {
            width: Number(blob && blob.width),
            height: Number(blob && blob.height),
            tag: (blob && blob.tag) || "",
            closed: false,
            close() {
                this.closed = true;
            },
        };
        bitmaps.push(bitmap);
        return bitmap;
    }
    let bitmapImpl = (blob) => Promise.resolve(makeBitmap(blob));
    let bitmapCalls = 0;
    function createImageBitmapEntry(blob) {
        bitmapCalls++;
        return bitmapImpl(blob);
    }

    /*
     * Timers are recorded as well as run, so a test can fire the client's
     * image-load deadline immediately instead of waiting out the real 15 s.
     */
    const timers = [];
    function sandboxSetTimeout(fn, delay) {
        const entry = {
            delay: Number(delay),
            fn,
            done: false,
            handle: null,
        };
        entry.handle = setTimeout(() => {
            if (entry.done) return;
            entry.done = true;
            fn();
        }, entry.delay);
        timers.push(entry);
        return entry;
    }
    function sandboxClearTimeout(entry) {
        if (!entry || entry.done) return;
        entry.done = true;
        clearTimeout(entry.handle);
    }

    /*
     * The `<img>` fallback path (no createImageBitmap): decode() and the
     * load events are scripted per test, because Safari is known to reject
     * decode() before a later, perfectly good onload.
     */
    const images = [];
    let imageBehaviour = {
        decode: () => Promise.resolve(),
        load: (img) =>
            setImmediate(() => {
                if (img.onload) img.onload();
            }),
    };
    class MockImage {
        constructor() {
            this.naturalWidth = 400;
            this.naturalHeight = 200;
            this.onload = null;
            this.onerror = null;
            this._src = "";
            images.push(this);
        }
        set src(value) {
            this._src = value;
            imageBehaviour.load(this);
        }
        get src() {
            return this._src;
        }
        decode() {
            try {
                return Promise.resolve(imageBehaviour.decode(this));
            } catch (err) {
                return Promise.reject(err);
            }
        }
    }

    class MockWebSocket {
        constructor(url) {
            this.url = url;
            this.readyState = 0;
            this.listeners = {};
            sockets.push(this);
        }
        addEventListener(type, fn) {
            (this.listeners[type] = this.listeners[type] || []).push(fn);
        }
        send() {}
        close() {
            this.readyState = 3;
            this.emit("close");
        }
        emit(type, event) {
            for (const fn of this.listeners[type] || []) fn(event);
        }
    }
    MockWebSocket.CONNECTING = 0;
    MockWebSocket.OPEN = 1;
    MockWebSocket.CLOSED = 3;

    /*
     * URL with object-URL bookkeeping: the client decodes the Blob it
     * already fetched through createObjectURL, and must revoke that URL when
     * the picture is replaced, dropped or timed out. Tests read `objectUrls`
     * to see which Blob was wrapped and whether it was given back.
     */
    const objectUrls = [];
    let objectUrlSeq = 0;
    function URLShim(input, base) {
        return new URL(String(input), base);
    }
    URLShim.createObjectURL = function (blob) {
        const entry = {
            url: "blob:wall.test/" + ++objectUrlSeq,
            blob,
            revoked: false,
        };
        objectUrls.push(entry);
        return entry.url;
    };
    URLShim.revokeObjectURL = function (url) {
        for (const entry of objectUrls) {
            if (entry.url === url) entry.revoked = true;
        }
    };

    const sandbox = {
        console: {
            log() {},
            warn(message, detail) {
                warnings.push({ message, detail });
            },
            error() {},
        },
        setTimeout: sandboxSetTimeout,
        clearTimeout: sandboxClearTimeout,
        setInterval,
        clearInterval,
        URL: URLShim,
        fetch: fetchMock,
        WebSocket: MockWebSocket,
        document: documentMock,
        window: windowMock,
        localStorage: {
            getItem() {
                return null;
            },
            setItem() {},
        },
        crypto: webcrypto,
        Image: MockImage,
        createImageBitmap: createImageBitmapEntry,
    };

    const context = vm.createContext(sandbox);
    vm.runInContext(CLIENT_SOURCE, context, { filename: "client.js" });

    return {
        calls,
        bitmaps,
        warnings,
        fetchLog,
        canvas,
        window: windowMock,
        socket: () => sockets[sockets.length - 1],
        listeners: { document: docListeners, window: winListeners },
        setFetch(fn) {
            fetchImpl = fn;
        },
        setBitmapImpl(fn) {
            bitmapImpl = fn;
        },
        /* Drop createImageBitmap so the client takes its `<img>` path. */
        setCreateImageBitmap(enabled) {
            sandbox.createImageBitmap = enabled
                ? createImageBitmapEntry
                : undefined;
            bitmapCalls = 0;
        },
        bitmapCalls: () => bitmapCalls,
        images,
        objectUrls,
        setImageBehaviour(behaviour) {
            imageBehaviour = Object.assign({}, imageBehaviour, behaviour);
        },
        setContextAvailable(available) {
            contextAvailable = available;
        },
        /*
         * Fire the client's own image-load deadline (IMAGE_LOAD_TIMEOUT_MS)
         * without waiting it out: the deadline is the only timer at that
         * delay while a load is in flight.
         */
        fireImageTimeout() {
            const pending = timers.filter(
                (t) => !t.done && t.delay === IMAGE_LOAD_TIMEOUT_MS
            );
            if (pending.length === 0) {
                throw new Error("no pending image-load deadline to fire");
            }
            for (const timer of pending) {
                timer.done = true;
                clearTimeout(timer.handle);
                timer.fn();
            }
            return pending.length;
        },
        makeBitmap,
        reset() {
            calls.length = 0;
        },
        since(index) {
            return calls.slice(index);
        },
        named(name) {
            return calls.filter((c) => c.name === name);
        },
        texts() {
            return calls
                .filter((c) => c.name === "fillText")
                .map((c) => String(c.args[0]));
        },
        emit(frame) {
            const socket = sockets[sockets.length - 1];
            assert.ok(socket, "client has not opened its device socket yet");
            socket.emit("message", { data: JSON.stringify(frame) });
        },
        click() {
            for (const fn of docListeners.click || []) fn({});
        },
    };
}

/* Let every queued promise job run: registration, fetch, decode, render. */
async function drain() {
    for (let i = 0; i < 6; i++) {
        await new Promise((resolve) => setImmediate(resolve));
    }
}

async function startHarness(opts) {
    const harness = createHarness(opts);
    await drain();
    assert.ok(harness.socket(), "client opened its device socket");
    return harness;
}

/* ------------------------------------------------------------------ */
/* Fixtures                                                           */
/* ------------------------------------------------------------------ */

function imageContent(overrides) {
    return Object.assign(
        {
            type: "image",
            asset: "sha256:" + "a".repeat(64),
            url: "/assets/sha256:" + "a".repeat(64),
            fit: "cover",
            intrinsicWidth: 400,
            intrinsicHeight: 400,
        },
        overrides
    );
}

function wallFrame(fields) {
    return Object.assign(
        {
            type: "wall",
            revision: 1,
            generation: "gen-1",
            wall: { width: 2000, height: 1000 },
            scene: { content: imageContent(), layout: "active" },
            placement: { x: 0, y: 0, w: 1000, h: 1000, bezel: ZERO_BEZEL },
        },
        fields
    );
}

function okResponse(blob) {
    return { ok: true, status: 200, blob: () => Promise.resolve(blob) };
}

function assetBlob(tag, width, height) {
    return { tag, width, height };
}

/* A fetch router: keys are substrings of the requested URL, values are
 * responses or promises of one. Anything else (registration) succeeds. */
function route(map) {
    const queues = {};
    return (url) => {
        for (const key of Object.keys(map)) {
            if (String(url).includes(key)) {
                const value = map[key];
                if (Array.isArray(value)) {
                    queues[key] = queues[key] || value.slice();
                    const next =
                        queues[key].length > 1
                            ? queues[key].shift()
                            : queues[key][0];
                    return Promise.resolve(next);
                }
                return Promise.resolve(value);
            }
        }
        return Promise.resolve({ ok: true, status: 200 });
    };
}

const ASSET_A = "a".repeat(64);
const ASSET_B = "b".repeat(64);

/* The two cover rectangles this suite expects, in wall coordinates:
 *   wall 2000x1000, image 400x400   -> scale 5   -> 0,-500,2000,2000
 *   wall 2000x1000, image 1000x1500 -> scale 2   -> 0,-1000,2000,3000
 * Both are the SAME for every tablet: the cover is a property of the wall,
 * not of the device looking at it. */
const COVER_400 = [0, -500, 2000, 2000];
const COVER_1000x1500 = [0, -1000, 2000, 3000];

/* ------------------------------------------------------------------ */
/* Assertions                                                         */
/* ------------------------------------------------------------------ */

function assertClose(actual, expected, message) {
    assert.ok(
        Math.abs(Number(actual) - Number(expected)) < 1e-9,
        (message || "value") +
            ": expected " +
            expected +
            ", got " +
            actual
    );
}

function assertCloseAll(actual, expected, message) {
    assert.strictEqual(actual.length, expected.length, message + " (length)");
    for (let i = 0; i < expected.length; i++) {
        assertClose(actual[i], expected[i], message + " [" + i + "]");
    }
}

function lastIndexOfNamed(harness, name) {
    for (let i = harness.calls.length - 1; i >= 0; i--) {
        if (harness.calls[i].name === name) return i;
    }
    return -1;
}

function lastDrawImage(harness) {
    const i = lastIndexOfNamed(harness, "drawImage");
    assert.ok(i >= 0, "expected a drawImage call");
    return harness.calls[i].args;
}

/* The wall->viewport transform in force when the picture was drawn. */
function wallTransform(harness) {
    const draw = lastIndexOfNamed(harness, "drawImage");
    assert.ok(draw >= 0, "expected a drawImage call");
    for (let i = draw - 1; i >= 0; i--) {
        if (harness.calls[i].name === "setTransform") {
            return harness.calls[i].args;
        }
    }
    throw new Error("no setTransform preceded the drawImage");
}

/* The clip rect (this device's visible rect, in wall coordinates). */
function clipRect(harness) {
    const draw = lastIndexOfNamed(harness, "drawImage");
    assert.ok(draw >= 0, "expected a drawImage call");
    for (let i = draw - 1; i >= 0; i--) {
        if (harness.calls[i].name === "rect") return harness.calls[i].args;
    }
    throw new Error("no clip rect preceded the drawImage");
}

/* Wall x -> viewport x under a [a,b,c,d,e,f] transform. */
function screenX(transform, wallX) {
    return transform[0] * wallX + transform[4];
}

function paintedRects(harness) {
    return harness
        .named("drawImage")
        .map((c) => c.args.slice(1))
        .map((rect) => rect.map((n) => (n === 0 ? 0 : n))); /* normalise -0 */
}

/* ------------------------------------------------------------------ */
/* Tests                                                              */
/* ------------------------------------------------------------------ */

const tests = [];
function test(name, fn) {
    tests.push({ name, fn });
}

test("seam mapping: both tablets draw one global cover of the wall", async () => {
    /* The left tablet owns x 0..1000 of the wall, the right one x
     * 1000..2000. Both decode the same asset and must land on the same
     * wall-space rectangle; only the clip differs. */
    const fields = {
        scene: {
            content: imageContent({
                asset: "sha256:" + ASSET_A,
                url: "/assets/sha256:" + ASSET_A,
                intrinsicWidth: 1000,
                intrinsicHeight: 1500,
            }),
            layout: "active",
        },
    };

    const decode = deferred(); /* hold the decode so loading shows first */
    const left = await startHarness(VP);
    left.setBitmapImpl(() => decode.promise);
    left.setFetch(route({ [ASSET_A]: okResponse(assetBlob("A", 1000, 1500)) }));
    left.emit(wallFrame(fields));
    await drain();

    assert.strictEqual(
        left.named("drawImage").length,
        0,
        "nothing is painted before the asset has decoded"
    );
    assert.ok(
        left.texts().includes("LOADING IMAGE"),
        "the initial load is a visible diagnostic, not a blank wall"
    );

    decode.resolve(left.makeBitmap(assetBlob("A", 1000, 1500)));
    await drain();

    const right = await startHarness(VP);
    right.setFetch(route({ [ASSET_A]: okResponse(assetBlob("A", 1000, 1500)) }));
    right.emit(
        wallFrame(
            Object.assign({}, fields, {
                placement: {
                    x: 1000,
                    y: 0,
                    w: 1000,
                    h: 1000,
                    bezel: ZERO_BEZEL,
                },
            })
        )
    );
    await drain();

    /* Identical wall-space rectangle: not computed per tablet. */
    assertCloseAll(
        lastDrawImage(left).slice(1),
        COVER_1000x1500,
        "left tablet's cover rectangle"
    );
    assertCloseAll(
        lastDrawImage(right).slice(1),
        COVER_1000x1500,
        "right tablet's cover rectangle"
    );
    assert.deepStrictEqual(
        lastDrawImage(right).slice(1),
        lastDrawImage(left).slice(1),
        "both tablets draw the very same rectangle"
    );

    /* Identical scale, and each clips to its own visible rect. */
    const lt = wallTransform(left);
    const rt = wallTransform(right);
    assertClose(lt[0], COVER_SCALE, "left scale");
    assertClose(rt[0], COVER_SCALE, "right scale");
    assertCloseAll(clipRect(left), [0, 0, 1000, 1000], "left clip");
    assertCloseAll(clipRect(right), [1000, 0, 1000, 1000], "right clip");

    /* The seam: wall x=1000 is the right edge of the left tablet's
     * viewport and the left edge of the right one's — continuous, with no
     * gap and no overlap. */
    assertClose(screenX(lt, 1000), VP.width, "left tablet's seam edge");
    assertClose(screenX(rt, 1000), 0, "right tablet's seam edge");
    /* The wall's own origin and far edge land where they should too. */
    assertClose(screenX(rt, 2000), VP.width, "right tablet's far edge");
});

test("stale load: an older in-flight asset never paints over a newer one", async () => {
    const h = await startHarness(VP);
    const aFetch = deferred();
    const bFetch = deferred();
    h.setFetch(
        route({
            [ASSET_A]: aFetch.promise,
            [ASSET_B]: bFetch.promise,
        })
    );

    h.emit(wallFrame({ revision: 1 }));
    await drain();
    h.emit(
        wallFrame({
            revision: 2,
            scene: {
                content: imageContent({
                    asset: "sha256:" + ASSET_B,
                    url: "/assets/sha256:" + ASSET_B,
                    intrinsicWidth: 1000,
                    intrinsicHeight: 1500,
                }),
                layout: "active",
            },
        })
    );
    await drain();

    /* The newer asset finishes first — as it may well in practice. */
    bFetch.resolve(okResponse(assetBlob("B", 1000, 1500)));
    await drain();
    assertCloseAll(
        lastDrawImage(h).slice(1),
        COVER_1000x1500,
        "the newer picture is on the wall"
    );

    /* Then the superseded one arrives. It must be dropped, released, and
     * must not repaint anything. */
    const paintsBefore = h.named("drawImage").length;
    aFetch.resolve(okResponse(assetBlob("A", 400, 400)));
    await drain();

    const loser = h.bitmaps.find((b) => b.tag === "A");
    assert.ok(loser, "the stale asset was decoded before being judged");
    assert.strictEqual(loser.closed, true, "the stale bitmap is released");
    assert.strictEqual(
        h.named("drawImage").length,
        paintsBefore,
        "a stale result paints nothing"
    );
    assert.ok(
        !paintedRects(h).some((r) => r.join() === COVER_400.join()),
        "the stale picture's rectangle never reaches the canvas"
    );
    assertCloseAll(
        lastDrawImage(h).slice(1),
        COVER_1000x1500,
        "the wall still shows the newer picture"
    );
});

test("generation change restarts the load; the old lineage is discarded", async () => {
    const h = await startHarness(VP);
    const first = deferred();
    const second = deferred();
    h.setFetch(
        route({
            [ASSET_A]: [first.promise, second.promise],
        })
    );

    h.emit(wallFrame({ revision: 5, generation: "gen-1" }));
    await drain();
    assert.strictEqual(
        h.fetchLog.filter((f) => String(f.url).includes(ASSET_A)).length,
        1,
        "one load for the first generation"
    );

    /* A restored server comes back at a LOWER revision under a NEW
     * generation: the frame is accepted, and the load started for the old
     * lineage can no longer be the answer. */
    h.emit(wallFrame({ revision: 2, generation: "gen-2" }));
    await drain();
    assert.strictEqual(
        h.fetchLog.filter((f) => String(f.url).includes(ASSET_A)).length,
        2,
        "the new generation starts its own load"
    );

    second.resolve(okResponse(assetBlob("first", 400, 400)));
    await drain();
    assertCloseAll(
        lastDrawImage(h).slice(1),
        COVER_400,
        "the current generation's asset is painted"
    );

    const paintsBefore = h.named("drawImage").length;
    first.resolve(okResponse(assetBlob("stale", 400, 400)));
    await drain();
    const loser = h.bitmaps.find((b) => b.tag === "stale");
    assert.ok(loser && loser.closed, "the old lineage's bitmap is released");
    assert.strictEqual(
        h.named("drawImage").length,
        paintsBefore,
        "the old lineage paints nothing"
    );
});

test("a retained picture stays up under an unmistakable loading banner", async () => {
    const h = await startHarness(VP);
    h.setFetch(
        route({
            [ASSET_A]: okResponse(assetBlob("A", 400, 400)),
        })
    );
    h.emit(wallFrame({ revision: 1 }));
    await drain();
    assertCloseAll(
        lastDrawImage(h).slice(1),
        COVER_400,
        "the first picture is on the wall"
    );

    const bFetch = deferred();
    h.setFetch(
        route({
            [ASSET_B]: bFetch.promise,
        })
    );
    const mark = h.calls.length;
    h.emit(
        wallFrame({
            revision: 2,
            scene: {
                content: imageContent({
                    asset: "sha256:" + ASSET_B,
                    url: "/assets/sha256:" + ASSET_B,
                    intrinsicWidth: 1000,
                    intrinsicHeight: 1500,
                }),
                layout: "active",
            },
        })
    );
    await drain();

    const retained = h.since(mark).filter((c) => c.name === "drawImage");
    assert.strictEqual(retained.length, 1, "the previous picture is retained");
    assertCloseAll(
        retained[0].args.slice(1),
        COVER_400,
        "and it is still the old picture"
    );
    const textsWhileLoading = h
        .since(mark)
        .filter((c) => c.name === "fillText")
        .map((c) => String(c.args[0]));
    assert.ok(
        textsWhileLoading.includes("LOADING IMAGE \u00b7 " + ASSET_B.slice(0, 8)),
        "with a banner that says which asset is loading: " +
            JSON.stringify(textsWhileLoading)
    );

    bFetch.resolve(okResponse(assetBlob("B", 1000, 1500)));
    await drain();
    const settled = h.since(mark);
    const settledIndex = settled.map((c) => c.name).lastIndexOf("drawImage");
    assert.ok(settledIndex >= 0);
    assertCloseAll(
        settled[settledIndex].args.slice(1),
        COVER_1000x1500,
        "the new picture replaces the old one once decoded"
    );
    assert.ok(
        !settled
            .slice(settledIndex)
            .filter((c) => c.name === "fillText")
            .some((c) => String(c.args[0]).startsWith("LOADING IMAGE")),
        "and the loading banner is gone once it has"
    );
});

test("failure: IMAGE FAILED + short asset id + a retry that works", async () => {
    const h = await startHarness(VP);
    h.setFetch(
        route({
            [ASSET_A]: Promise.resolve({ ok: false, status: 404 }),
        })
    );
    h.emit(wallFrame());
    await drain();

    const texts = h.texts();
    assert.ok(
        texts.includes("IMAGE FAILED"),
        "the failure is stated out loud: " + JSON.stringify(texts)
    );
    assert.ok(
        texts.some((t) => t.includes(ASSET_A.slice(0, 8))),
        "the short asset id names what failed"
    );
    assert.ok(
        texts.some((t) => t.includes("Tap anywhere to retry.")),
        "the panel offers a retry"
    );
    assert.strictEqual(
        h.named("drawImage").length,
        0,
        "no stale surface is presented on failure"
    );
    assert.ok(
        h.warnings.some((w) => String(w.message).includes("image scene failed")),
        "the failure is reported to the console as well"
    );

    /* Retry: the tap the panel promises. */
    h.reset();
    h.setFetch(
        route({
            [ASSET_A]: okResponse(assetBlob("A", 400, 400)),
        })
    );
    h.click();
    await drain();

    assertCloseAll(
        lastDrawImage(h).slice(1),
        COVER_400,
        "the retry loads and paints the asset"
    );
    assert.ok(
        !h.texts().includes("IMAGE FAILED"),
        "the failure panel is gone once it works"
    );
});

test("a replayed wall frame retries the failed asset after a reconnect", async () => {
    const h = await startHarness(VP);
    h.setFetch(
        route({ [ASSET_A]: Promise.resolve({ ok: false, status: 404 }) })
    );
    h.emit(wallFrame({ revision: 7 }));
    await drain();
    assert.ok(
        h.texts().includes("IMAGE FAILED"),
        "a missing asset is reported: " + JSON.stringify(h.texts())
    );

    /* The bytes come back, but an inventory change deliberately does not
     * bump the revision — all the device gets is the replay that follows a
     * reconnect, which must not be a no-op here. */
    h.reset();
    h.setFetch(route({ [ASSET_A]: okResponse(assetBlob("A", 400, 400)) }));
    h.emit(wallFrame({ revision: 7 }));
    await drain();

    assertCloseAll(
        lastDrawImage(h).slice(1),
        COVER_400,
        "the replayed frame recovered the picture"
    );
    assert.ok(
        !h.texts().includes("IMAGE FAILED"),
        "and the failure panel is gone"
    );
});

test("unplaced image content says NO PLACEMENT and paints nothing", async () => {
    const h = await startHarness(VP);
    h.setFetch(route({ [ASSET_A]: okResponse(assetBlob("A", 400, 400)) }));
    h.emit(wallFrame({ placement: null }));
    await drain();

    assert.ok(
        h.texts().includes("NO PLACEMENT"),
        "an unplaced device still reports it: " + JSON.stringify(h.texts())
    );
    assert.strictEqual(
        h.named("drawImage").length,
        0,
        "nothing is painted without a placement"
    );
    assert.strictEqual(
        h.named("clip").length,
        0,
        "and no wall transform is built for it"
    );
});

test("colour, unknown type, resize and reconnect still work", async () => {
    const h = await startHarness(VP);
    h.setFetch(route({}));

    /* Colour content keeps the canvas hidden — today's v1 behaviour. */
    h.emit(
        wallFrame({
            scene: { content: { type: "color" }, layout: "active" },
        })
    );
    await drain();
    assert.strictEqual(h.canvas.style.display, "none", "colour hides the canvas");

    /* An unknown type is still reported, never rendered as colour. */
    h.emit(
        wallFrame({
            revision: 2,
            scene: { content: { type: "hologram" }, layout: "active" },
        })
    );
    await drain();
    assert.ok(
        h.texts().some((t) => t.includes("CANNOT DISPLAY HOLOGRAM")),
        "unknown content is called out: " + JSON.stringify(h.texts())
    );
    assert.strictEqual(h.canvas.style.display, "block");

    /* Calibration still renders its pattern for the visible rect. */
    h.reset();
    h.emit(
        wallFrame({
            revision: 3,
            scene: { content: { type: "calibration" }, layout: "active" },
        })
    );
    await drain();
    assert.ok(
        h.named("stroke").length > 0,
        "the calibration pattern still draws"
    );
    /* Its transform is still the visible-rect -> viewport cover, centred:
     * rect 1000x1000 onto an 800x600 viewport scales by 0.8 and crops
     * (1000 - 600/0.8)/2 = 125 wall units off top and bottom — the rect
     * centre stays at the viewport centre, so the translate is
     * -(0 + 125) * 0.8 = -100 device pixels, not 0. */
    assertCloseAll(
        calibrationTransform(h),
        [COVER_SCALE, 0, 0, COVER_SCALE, -0, -100],
        "calibration still maps its own slice"
    );

    /* Resize re-renders through the same transform. */
    const mark = h.calls.length;
    h.window.innerWidth = 1600;
    h.window.innerHeight = 900;
    for (const fn of h.listeners.window.resize || []) fn({});
    await drain();
    assert.ok(
        h.since(mark).length > 0,
        "a viewport change repaints the wall"
    );
    assert.strictEqual(h.canvas.width, 1600, "the backing store follows");

    /* A reconnect replays the same wall frame: it must be ignored, so the
     * already-decoded picture is not refetched. */
    const fetchesBefore = h.fetchLog.length;
    h.emit(
        wallFrame({
            revision: 3,
            scene: { content: { type: "calibration" }, layout: "active" },
        })
    );
    await drain();
    assert.strictEqual(
        h.fetchLog.length,
        fetchesBefore,
        "a replayed frame changes nothing"
    );
});

/* Calibration's wall->viewport transform, read off its pattern stroke. */
function calibrationTransform(harness) {
    const stroke = lastIndexOfNamed(harness, "stroke");
    assert.ok(stroke >= 0, "expected the calibration pattern to stroke");
    for (let i = stroke - 1; i >= 0; i--) {
        if (harness.calls[i].name === "setTransform") {
            return harness.calls[i].args;
        }
    }
    throw new Error("calibration drew with no transform");
}

test("a stalled asset times out, and its late decode neither paints nor retries", async () => {
    const h = await startHarness(VP);
    const stalled = deferred(); /* headers arrive, body never does */
    h.setFetch(route({ [ASSET_A]: stalled.promise }));
    h.emit(wallFrame());
    await drain();
    assert.ok(
        h.texts().includes("LOADING IMAGE"),
        "the attempt starts on the loading diagnostic"
    );
    assert.strictEqual(h.named("drawImage").length, 0, "nothing painted yet");

    /* Fire IMAGE_LOAD_TIMEOUT_MS directly — the whole attempt (headers,
     * body and decode) is bounded, not just the response headers. */
    h.fireImageTimeout();
    await drain();
    assert.ok(
        h.texts().includes("IMAGE FAILED"),
        "the deadline ends on the failure panel: " + JSON.stringify(h.texts())
    );
    assert.ok(
        h.texts().some((t) => t.includes("image load timed out")),
        "and says why"
    );
    assert.ok(
        h.warnings.some((w) =>
            String(w.message).includes("image scene failed: image load timed out")
        ),
        "and reports it"
    );
    assert.strictEqual(h.named("drawImage").length, 0, "still nothing painted");

    /* The stalled body arrives AFTER the timeout: it must not paint over
     * the failure, must not leak its bitmap, and must not kick off a fresh
     * load on its own — retrying is the operator's tap. */
    const fetchesAtTimeout = h.fetchLog.length;
    stalled.resolve(okResponse(assetBlob("late", 400, 400)));
    await drain();

    const late = h.bitmaps.find((b) => b.tag === "late");
    assert.ok(late, "the late body was decoded before being judged");
    assert.strictEqual(late.closed, true, "…and its bitmap is released");
    assert.strictEqual(
        h.named("drawImage").length,
        0,
        "a post-timeout decode paints nothing"
    );
    assert.strictEqual(
        h.fetchLog.length,
        fetchesAtTimeout,
        "a stale callback does NOT auto-retry the failed attempt"
    );
    assert.ok(h.texts().includes("IMAGE FAILED"), "the failure panel stands");

    /* The tap the panel promises is what retries. */
    h.reset(); /* everything below is the retry's own output */
    h.setFetch(route({ [ASSET_A]: okResponse(assetBlob("A", 400, 400)) }));
    h.click();
    await drain();
    assertCloseAll(
        lastDrawImage(h).slice(1),
        COVER_400,
        "the tap retry loads and paints"
    );
    assert.ok(
        !h.texts().includes("IMAGE FAILED"),
        "…and clears the failure panel"
    );
});

test("a missing 2d context keeps the image READY instead of failing it", async () => {
    const h = await startHarness(VP);
    h.setFetch(route({ [ASSET_A]: okResponse(assetBlob("A", 400, 400)) }));
    h.emit(wallFrame());
    await drain();
    assertCloseAll(
        lastDrawImage(h).slice(1),
        COVER_400,
        "the picture is on the wall"
    );
    const fetchesAfterLoad = h.fetchLog.length;

    /* No surface to paint on: nothing can be drawn, but the picture is
     * perfectly good, so the state must not be touched. */
    h.setContextAvailable(false);
    h.reset();
    for (const fn of h.listeners.window.resize || []) fn({});
    await drain();
    assert.strictEqual(
        h.named("drawImage").length,
        0,
        "nothing can be painted without a context"
    );
    assert.ok(
        !h.texts().includes("IMAGE FAILED"),
        "a transient surface problem is not reported as a broken picture"
    );
    assert.ok(
        !h.warnings.some((w) =>
            String(w.message).includes("image scene failed")
        ),
        "and no failure is recorded"
    );

    /* The surface comes back: the next render repaints the SAME picture
     * from the still-live cache, with no reload. */
    h.setContextAvailable(true);
    for (const fn of h.listeners.window.resize || []) fn({});
    await drain();
    assertCloseAll(
        lastDrawImage(h).slice(1),
        COVER_400,
        "the next render paints the picture again"
    );
    assert.strictEqual(
        h.fetchLog.length,
        fetchesAfterLoad,
        "…with no reload: status stayed ready"
    );
    assert.ok(
        !h.texts().includes("IMAGE FAILED"),
        "and it was never called failed"
    );
});

test("leaving image content releases the decoded bitmap", async () => {
    const h = await startHarness(VP);
    h.setFetch(route({ [ASSET_A]: okResponse(assetBlob("A", 400, 400)) }));
    h.emit(wallFrame({ revision: 1 }));
    await drain();
    const picture = h.bitmaps.find((b) => b.tag === "A");
    assert.ok(picture && !picture.closed, "the picture is decoded and held");
    const fetchesWhileImage = h.fetchLog.length;

    /* colour / calibration / unknown — any non-image scene drops it: up to
     * 12 megapixels is too much to hold for a surface that cannot show it. */
    h.emit(
        wallFrame({
            revision: 2,
            scene: { content: { type: "calibration" }, layout: "active" },
        })
    );
    await drain();
    assert.strictEqual(
        picture.closed,
        true,
        "the decoded bitmap is released when the scene stops being an image"
    );

    /* Coming back must fetch it again rather than resurrect a stale cache. */
    h.emit(wallFrame({ revision: 3 }));
    await drain();
    assert.ok(
        h.fetchLog.length > fetchesWhileImage,
        "the cache really is gone: the picture is fetched again"
    );
    assertCloseAll(
        lastDrawImage(h).slice(1),
        COVER_400,
        "and it paints again"
    );
});

test("a failed replacement releases the picture it replaced", async () => {
    const h = await startHarness(VP);
    h.setFetch(route({ [ASSET_A]: okResponse(assetBlob("A", 400, 400)) }));
    h.emit(wallFrame({ revision: 1 }));
    await drain();
    const previous = h.bitmaps.find((b) => b.tag === "A");
    assert.ok(previous && !previous.closed, "the first picture is held");

    h.setFetch(route({ [ASSET_B]: Promise.resolve({ ok: false, status: 404 }) }));
    h.emit(
        wallFrame({
            revision: 2,
            scene: {
                content: imageContent({
                    asset: "sha256:" + ASSET_B,
                    url: "/assets/sha256:" + ASSET_B,
                }),
                layout: "active",
            },
        })
    );
    await drain();

    assert.ok(
        h.texts().includes("IMAGE FAILED"),
        "the replacement is reported as failed"
    );
    assert.strictEqual(
        previous.closed,
        true,
        "the now-invisible stale bitmap is released, not kept around"
    );
});

test("the <img> fallback survives an early decode() rejection (Safari)", async () => {
    const h = await startHarness(VP);
    h.setCreateImageBitmap(false);
    h.setImageBehaviour({
        /* Safari: decode() rejects before the load event that succeeds. */
        decode: () => Promise.reject(new Error("EncodingError")),
        load: (img) =>
            setImmediate(() => {
                if (img.onload) img.onload();
            }),
    });
    h.setFetch(route({ [ASSET_A]: okResponse(assetBlob("A", 400, 200)) }));
    h.emit(wallFrame());
    await drain();

    assert.strictEqual(
        h.bitmapCalls(),
        0,
        "createImageBitmap was not available, as expected"
    );
    assert.strictEqual(h.images.length, 1, "the <img> path was taken");
    assertCloseAll(
        lastDrawImage(h).slice(1),
        COVER_400,
        "the loaded element is painted"
    );
    assert.ok(
        !h.texts().includes("IMAGE FAILED"),
        "a rejected decode() is not a failure — onload decides: " +
            JSON.stringify(h.texts())
    );
    assert.ok(
        !h.warnings.some((w) =>
            String(w.message).includes("image scene failed")
        ),
        "and nothing is reported"
    );
});

test("an opaque underlay is painted before the picture", async () => {
    const h = await startHarness(VP);
    h.setFetch(route({ [ASSET_A]: okResponse(assetBlob("A", 400, 400)) }));
    h.emit(wallFrame());
    await drain();

    const draw = lastIndexOfNamed(h, "drawImage");
    assert.ok(draw >= 0, "the picture is drawn");

    let styleIndex = -1;
    for (let i = draw - 1; i >= 0; i--) {
        if (h.calls[i].name === "setFillStyle") {
            styleIndex = i;
            break;
        }
    }
    assert.ok(styleIndex >= 0, "a fill style is chosen first");
    const style = h.calls[styleIndex].args[0];
    assert.strictEqual(
        style,
        "#0b1120",
        "the underlay is the opaque background, pinned"
    );
    assert.strictEqual(isOpaque(style), true, "…and fully opaque, so an alpha PNG cannot show the old frame through");

    let rectIndex = -1;
    for (let i = draw - 1; i > styleIndex; i--) {
        if (h.calls[i].name === "fillRect") {
            rectIndex = i;
            break;
        }
    }
    assert.ok(
        rectIndex >= 0,
        "the underlay is filled BEFORE the picture is drawn"
    );
    assertCloseAll(
        h.calls[rectIndex].args,
        [0, 0, 1000, 1000],
        "…over this device's whole visible rect"
    );
});

test("the <img> fallback decodes the Blob it already fetched — one request", async () => {
    const h = await startHarness(VP);
    h.setCreateImageBitmap(false);
    const blob = assetBlob("A", 400, 200);
    h.setFetch(route({ [ASSET_A]: okResponse(blob) }));
    h.emit(wallFrame());
    await drain();

    const gets = h.fetchLog.filter((f) => String(f.url).includes(ASSET_A));
    assert.strictEqual(gets.length, 1, "exactly ONE network request for the asset");
    assert.strictEqual(
        h.objectUrls.length,
        1,
        "the fetched bytes became an object URL"
    );
    assert.strictEqual(
        h.objectUrls[0].blob,
        blob,
        "…from the very Blob that request returned, not from a second GET"
    );
    assert.strictEqual(h.images.length, 1, "one <img> decodes it");
    assert.ok(
        String(h.images[0].src).indexOf("blob:") === 0,
        "its src is the object URL, not the asset URL: " + h.images[0].src
    );
    assertCloseAll(
        lastDrawImage(h).slice(1),
        COVER_400,
        "and the picture is painted"
    );
    assert.ok(
        !h.warnings.some((w) => String(w.message).includes("image scene failed")),
        "no failure reported"
    );
});

test("object URLs are revoked when a picture is replaced or dropped", async () => {
    const h = await startHarness(VP);
    h.setCreateImageBitmap(false);
    const first = assetBlob("A", 400, 400);
    const second = assetBlob("B", 400, 400);
    h.setFetch(route({ [ASSET_A]: okResponse(first) }));
    h.emit(wallFrame({ revision: 1 }));
    await drain();
    assert.strictEqual(
        h.objectUrls.filter((o) => !o.revoked).length,
        1,
        "the first picture holds one live object URL"
    );

    /* Replaced by a different asset. */
    h.setFetch(route({ [ASSET_B]: okResponse(second) }));
    h.emit(
        wallFrame({
            revision: 2,
            scene: {
                content: imageContent({
                    asset: "sha256:" + ASSET_B,
                    url: "/assets/sha256:" + ASSET_B,
                }),
                layout: "active",
            },
        })
    );
    await drain();
    assert.ok(
        h.objectUrls.find((o) => o.blob === first).revoked,
        "the replaced picture's object URL is revoked"
    );
    assert.strictEqual(
        h.images[0].src,
        "",
        "and its <img> was detached"
    );
    assert.strictEqual(
        h.objectUrls.filter((o) => !o.revoked).length,
        1,
        "…leaving exactly the new picture's URL live"
    );

    /* Image content leaves the scene altogether. */
    h.emit(
        wallFrame({
            revision: 3,
            scene: { content: { type: "calibration" }, layout: "active" },
        })
    );
    await drain();
    assert.ok(
        h.objectUrls.find((o) => o.blob === second).revoked,
        "the dropped picture's object URL is revoked too"
    );
    assert.strictEqual(
        h.objectUrls.filter((o) => !o.revoked).length,
        0,
        "nothing is held"
    );
    assert.strictEqual(h.images[1].src, "", "its <img> is detached as well");
});

test("the deadline cancels the <img>: URL revoked, late load paints nothing", async () => {
    const h = await startHarness(VP);
    h.setCreateImageBitmap(false);
    const decodeGate = deferred(); /* decode() never settles by itself */
    h.setImageBehaviour({
        decode: () => decodeGate.promise,
        load: () => {
            /* nothing fires on its own: only a timeout can end this */
        },
    });
    h.setFetch(route({ [ASSET_A]: okResponse(assetBlob("A", 400, 400)) }));
    h.emit(wallFrame());
    await drain();

    assert.strictEqual(h.images.length, 1, "the fallback <img> is loading");
    const img = h.images[0];
    const lateOnload = img.onload; /* the handler that would have painted */
    const entry = h.objectUrls[0];
    assert.ok(entry && !entry.revoked, "the object URL is live while loading");

    h.fireImageTimeout();
    await drain();
    assert.ok(
        h.texts().includes("IMAGE FAILED"),
        "the deadline reports the failure"
    );
    assert.ok(
        h.warnings.some((w) =>
            String(w.message).includes("image scene failed: image load timed out")
        ),
        "…and reports it to the console"
    );
    assert.strictEqual(entry.revoked, true, "the object URL is revoked with it");
    assert.strictEqual(img.onload, null, "handlers cleared");
    assert.strictEqual(img.onerror, null, "handlers cleared");
    assert.strictEqual(img.src, "", "the <img> was detached: no further bytes");
    const fetchesAtTimeout = h.fetchLog.length;
    assert.strictEqual(h.named("drawImage").length, 0, "nothing painted yet");

    /* Whatever could still arrive afterwards must be ignored. */
    assert.strictEqual(
        typeof lateOnload,
        "function",
        "the pre-cancel handler really existed"
    );
    lateOnload.call(img);
    decodeGate.resolve();
    await drain();

    assert.strictEqual(
        h.named("drawImage").length,
        0,
        "a late onload/decode paints nothing"
    );
    assert.strictEqual(
        h.fetchLog.length,
        fetchesAtTimeout,
        "and nothing is refetched"
    );
    assert.strictEqual(
        h.objectUrls.filter((o) => !o.revoked).length,
        0,
        "and the URL stays revoked"
    );
    assert.ok(
        h.texts().includes("IMAGE FAILED"),
        "the failure panel stands"
    );
});

test("a malformed image scene says who must fix it, not 'tap to retry'", async () => {
    const h = await startHarness(VP);
    h.setFetch(route({}));
    h.emit(
        wallFrame({
            scene: {
                content: {
                    type: "image",
                    asset: "sha256:" + ASSET_A,
                    fit: "cover",
                    /* no url: nothing on this device can fetch it */
                },
                layout: "active",
            },
        })
    );
    await drain();

    const texts = h.texts();
    assert.ok(
        texts.includes("IMAGE FAILED"),
        "still an explicit failure: " + JSON.stringify(texts)
    );
    assert.ok(
        texts.some((t) => t.includes("image content has no asset or url")),
        "…with the real reason"
    );
    assert.ok(
        texts.some((t) => t.includes("Set a valid image in the controller.")),
        "…and an instruction that can actually be carried out"
    );
    assert.ok(
        !texts.some((t) => t.includes("Tap anywhere to retry")),
        "no promise of a retry that a tap cannot deliver"
    );

    /* The tap really is inert, so it must not claim to do anything. */
    const fetches = h.fetchLog.length;
    h.click();
    await drain();
    assert.strictEqual(
        h.fetchLog.length,
        fetches,
        "tapping a malformed scene starts no request"
    );
    assert.ok(
        !h.texts().includes("LOADING IMAGE"),
        "…and no load begins"
    );
});

test("an unplaced tablet fetches nothing until it is placed", async () => {
    const h = await startHarness(VP);
    h.setFetch(route({ [ASSET_A]: okResponse(assetBlob("A", 400, 400)) }));

    h.emit(wallFrame({ revision: 1, placement: null }));
    await drain();
    assert.ok(
        h.texts().includes("NO PLACEMENT"),
        "NO PLACEMENT is shown"
    );
    assert.strictEqual(
        h.fetchLog.filter((f) => String(f.url).includes(ASSET_A)).length,
        0,
        "no asset request while unplaced"
    );
    assert.strictEqual(h.objectUrls.length, 0, "no object URL either");
    assert.strictEqual(h.named("drawImage").length, 0, "nothing painted");

    /* The placement arrives: now the picture is worth fetching. */
    h.emit(
        wallFrame({
            revision: 2,
            placement: {
                x: 0,
                y: 0,
                w: 1000,
                h: 1000,
                bezel: ZERO_BEZEL,
            },
        })
    );
    await drain();
    assert.strictEqual(
        h.fetchLog.filter((f) => String(f.url).includes(ASSET_A)).length,
        1,
        "the placement starts the load"
    );
    assertCloseAll(
        lastDrawImage(h).slice(1),
        COVER_400,
        "and the picture paints"
    );

    /* And losing it again gives the decoded picture back. */
    h.reset();
    h.emit(wallFrame({ revision: 3, placement: null }));
    await drain();
    const picture = h.bitmaps.find((b) => b.tag === "A");
    assert.strictEqual(
        picture.closed,
        true,
        "the decoded bitmap is released when the device goes unplaced"
    );
    assert.ok(
        h.texts().includes("NO PLACEMENT"),
        "back to NO PLACEMENT"
    );
    assert.strictEqual(h.named("drawImage").length, 0, "and nothing is drawn");
});

/* "#rrggbb" is opaque; rgba()/hsla() carries its own alpha. */
function isOpaque(style) {
    const value = String(style).trim();
    if (/^#[0-9a-f]{6}$/i.test(value)) return true;
    if (/^#[0-9a-f]{3}$/i.test(value)) return true;
    const rgba = value.match(/rgba?\(([^)]+)\)/i);
    if (!rgba) return false;
    const parts = rgba[1].split(",");
    if (parts.length < 4) return true;
    return Number(parts[3]) >= 1;
}

/* ------------------------------------------------------------------ */
/* Runner                                                             */
/* ------------------------------------------------------------------ */

(async function main() {
    let failed = 0;
    for (const entry of tests) {
        try {
            await entry.fn();
            console.log("ok   - " + entry.name);
        } catch (err) {
            failed++;
            console.error("FAIL - " + entry.name);
            console.error((err && err.stack) || err);
        }
    }
    console.log(
        failed === 0
            ? "\n" + tests.length + " passed"
            : "\n" + failed + " of " + tests.length + " FAILED"
    );
    process.exit(failed === 0 ? 0 : 1);
})();
