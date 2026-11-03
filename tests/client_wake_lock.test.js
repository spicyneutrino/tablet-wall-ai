/*
 * Screen wake lock in the tablet client, against a mocked navigator.wakeLock.
 *
 *     node tests/client_wake_lock.test.js
 *
 * client.js is an IIFE, so it runs in a `vm` sandbox with a minimal document,
 * window, WebSocket and fetch. The tests read what the server would read: the
 * `wake_lock` field of the registration body and of the heartbeat frames.
 *
 *   - no navigator.wakeLock in a secure context        -> unsupported
 *   - an insecure context, with or without the API     -> insecure (checked first)
 *   - request() rejecting                              -> denied, retried later
 *   - hidden page: no request; visible page: request   -> held
 *   - visibility lost: the lock is released, then taken again on return
 *   - a lock the browser drops while visible           -> released, then retaken
 */

"use strict";

const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { webcrypto } = require("node:crypto");

const CLIENT_SOURCE = fs.readFileSync(
    path.join(__dirname, "..", "frontend", "client", "client.js"),
    "utf8"
);
const RETRY_MS = 30000;

function createHarness(opts = {}) {
    const sockets = [];
    const fetchLog = [];
    const docListeners = {};
    const sentinels = [];
    const requests = [];
    let now = 1_000_000;

    class FakeDate extends Date {
        static now() {
            return now;
        }
    }

    const ctx = new Proxy({}, { get: () => () => {}, set: () => true });
    const canvas = { width: 0, height: 0, style: {}, setAttribute() {}, getContext: () => ctx };

    const document = {
        visibilityState: opts.visibility || "visible",
        getElementById: () => null,
        documentElement: { clientWidth: 800, clientHeight: 600, style: { setProperty() {} } },
        createElement: () => canvas,
        body: { appendChild() {} },
        addEventListener(type, fn) {
            (docListeners[type] = docListeners[type] || []).push(fn);
        },
    };

    class MockWebSocket {
        constructor(url) {
            this.url = url;
            this.readyState = 0;
            this.listeners = {};
            this.sent = [];
            sockets.push(this);
        }
        addEventListener(type, fn) {
            (this.listeners[type] = this.listeners[type] || []).push(fn);
        }
        send(data) {
            this.sent.push(JSON.parse(data));
        }
        close() {
            this.readyState = 3;
        }
        emit(type, event) {
            for (const fn of this.listeners[type] || []) fn(event);
        }
    }
    MockWebSocket.OPEN = 1;

    function makeSentinel() {
        const listeners = [];
        const sentinel = {
            released: false,
            addEventListener(type, fn) {
                if (type === "release") listeners.push(fn);
            },
            release() {
                if (sentinel.released) return Promise.resolve();
                sentinel.released = true;
                listeners.forEach((fn) => fn({}));
                return Promise.resolve();
            },
            /* The browser taking the lock back (battery saver, page hidden). */
            revoke() {
                sentinel.release();
            },
        };
        sentinels.push(sentinel);
        return sentinel;
    }

    const allow = () => Promise.resolve(makeSentinel());
    let requestImpl = opts.request || allow;
    const wakeLock = {
        request(kind) {
            requests.push(kind);
            return requestImpl(kind);
        },
    };

    const sandbox = {
        console: { log() {}, warn() {}, error() {} },
        setTimeout,
        clearTimeout,
        setInterval,
        clearInterval,
        Date: FakeDate,
        performance,
        URL,
        fetch(url, options) {
            fetchLog.push({ url, body: options && options.body ? JSON.parse(options.body) : null });
            return Promise.resolve({ ok: true, status: 200 });
        },
        WebSocket: MockWebSocket,
        document,
        window: {
            innerWidth: 800,
            innerHeight: 600,
            devicePixelRatio: 1,
            isSecureContext: opts.secure !== false,
            location: { protocol: "https:", host: "wall.test", href: "https://wall.test/client/" },
            addEventListener() {},
        },
        localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
        crypto: webcrypto,
    };
    if (opts.navigator !== false) {
        sandbox.navigator = opts.api === false ? {} : { wakeLock };
    }
    vm.runInContext(CLIENT_SOURCE, vm.createContext(sandbox), { filename: "client.js" });

    return {
        fetchLog,
        requests,
        sentinels,
        socket: () => sockets[sockets.length - 1],
        allow() {
            requestImpl = allow;
        },
        advance(ms) {
            now += ms;
        },
        setVisibility(state) {
            document.visibilityState = state;
            (docListeners.visibilitychange || []).forEach((fn) => fn({}));
        },
        /* The server's welcome opens the heartbeat loop at a fast cadence. */
        welcome() {
            const socket = sockets[sockets.length - 1];
            socket.readyState = 1;
            socket.emit("message", {
                data: JSON.stringify({
                    type: "welcome",
                    device_id: "x",
                    heartbeat_interval_ms: 15,
                    number: 1,
                }),
            });
        },
        heartbeats: () =>
            sockets.flatMap((socket) => socket.sent).filter((frame) => frame.type === "heartbeat"),
    };
}

async function drain() {
    for (let i = 0; i < 8; i++) await new Promise((resolve) => setImmediate(resolve));
}

async function waitFor(predicate, message) {
    const deadline = Date.now() + 3000;
    while (Date.now() < deadline) {
        if (predicate()) return;
        await new Promise((resolve) => setTimeout(resolve, 5));
    }
    assert.fail(message);
}

async function started(opts) {
    const harness = createHarness(opts);
    await drain();
    assert.ok(harness.socket(), "client opened its device socket");
    return harness;
}

const registered = (harness) => harness.fetchLog[0].body.wake_lock;
const lastHeartbeat = (harness) => {
    const beats = harness.heartbeats();
    return beats[beats.length - 1].wake_lock;
};

const tests = [];
const test = (name, fn) => tests.push({ name, fn });

test("a secure context without navigator.wakeLock reports unsupported", async () => {
    const harness = await started({ api: false });
    assert.strictEqual(registered(harness), "unsupported");
});

test("no navigator at all is unsupported in a secure context", async () => {
    const harness = await started({ navigator: false });
    assert.strictEqual(registered(harness), "unsupported");
});

test("an insecure context reports insecure and never calls the API", async () => {
    const harness = await started({ secure: false });
    assert.strictEqual(registered(harness), "insecure");
    assert.deepStrictEqual(harness.requests, []);
});

test("insecure wins over unsupported: a plain-HTTP tablet has no API at all", async () => {
    const harness = await started({ secure: false, api: false });
    assert.strictEqual(registered(harness), "insecure");
});

test("a visible page takes the lock and reports held in the heartbeat", async () => {
    const harness = await started();
    assert.deepStrictEqual(harness.requests, ["screen"]);
    harness.welcome();
    await waitFor(() => harness.heartbeats().length > 0, "no heartbeat was sent");
    assert.strictEqual(lastHeartbeat(harness), "held");
});

test("a rejected request reports denied, then retries no sooner than 30 s", async () => {
    const harness = await started({
        request: () => Promise.reject(Object.assign(new Error("no"), { name: "NotAllowedError" })),
    });
    assert.strictEqual(harness.requests.length, 1);
    harness.welcome();
    await waitFor(() => harness.heartbeats().length > 2, "no heartbeats");
    assert.strictEqual(lastHeartbeat(harness), "denied");
    assert.strictEqual(harness.requests.length, 1, "no retry inside the 30 s window");

    harness.allow();
    harness.advance(RETRY_MS);
    await waitFor(() => harness.requests.length === 2, "no retry after 30 s");
    await waitFor(() => lastHeartbeat(harness) === "held", "retry did not reach held");
});

test("a hidden page requests nothing until it becomes visible", async () => {
    const harness = await started({ visibility: "hidden" });
    assert.deepStrictEqual(harness.requests, []);
    harness.setVisibility("visible");
    await drain();
    assert.deepStrictEqual(harness.requests, ["screen"]);
    harness.welcome();
    await waitFor(() => harness.heartbeats().length > 0, "no heartbeat was sent");
    assert.strictEqual(lastHeartbeat(harness), "held");
});

test("losing visibility releases the lock; returning reacquires it", async () => {
    const harness = await started();
    harness.welcome();
    await waitFor(() => harness.heartbeats().length > 0, "no heartbeat was sent");
    const first = harness.sentinels[0];
    assert.strictEqual(first.released, false);

    harness.setVisibility("hidden");
    await drain();
    assert.strictEqual(first.released, true);
    await waitFor(() => lastHeartbeat(harness) === "released", "release was not reported");

    harness.setVisibility("visible");
    await drain();
    assert.strictEqual(harness.requests.length, 2, "one new request on return");
    assert.strictEqual(harness.sentinels.length, 2);
    await waitFor(() => lastHeartbeat(harness) === "held", "reacquire was not reported");

    /* Flapping while hidden must not stack requests. */
    harness.setVisibility("hidden");
    harness.setVisibility("hidden");
    harness.setVisibility("visible");
    harness.setVisibility("visible");
    await drain();
    assert.strictEqual(harness.requests.length, 3);
});

test("a lock the browser drops while visible reads released and is retaken", async () => {
    const harness = await started();
    harness.welcome();
    await waitFor(() => harness.heartbeats().length > 0, "no heartbeat was sent");
    harness.sentinels[0].revoke();
    await waitFor(() => lastHeartbeat(harness) === "released", "drop was not reported");
    assert.strictEqual(harness.requests.length, 1);

    harness.advance(RETRY_MS);
    await waitFor(() => harness.requests.length === 2, "no retry after the drop");
    await waitFor(() => lastHeartbeat(harness) === "held", "retry did not reach held");
});

test("a throwing request() is denied rather than fatal", async () => {
    const harness = await started({
        request: () => {
            throw new Error("synchronous failure");
        },
    });
    harness.welcome();
    await waitFor(() => harness.heartbeats().length > 0, "no heartbeat was sent");
    assert.strictEqual(lastHeartbeat(harness), "denied");
});

(async () => {
    let passed = 0;
    for (const { name, fn } of tests) {
        try {
            await fn();
            passed++;
            console.log("ok   - " + name);
        } catch (err) {
            console.log("FAIL - " + name + "\n" + (err && err.stack));
            process.exitCode = 1;
        }
    }
    console.log("\n" + passed + "/" + tests.length + " passed");
    process.exit(process.exitCode || 0);
})();
