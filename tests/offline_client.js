/*
 * One real client.js page load against a live server, recording every request.
 *
 *     node tests/offline_client.js <base-url> <device-id> <device-number>
 *
 * Used by tests/test_offline.py inside a network namespace that has loopback
 * and nothing else. client.js runs unmodified in a `vm` sandbox; its fetch and
 * WebSocket are wrapped only to log the absolute URL before forwarding to the
 * real network stack. Prints one JSON line: whether the client connected, which
 * asset it fetched, whether it painted a picture, and every URL it touched.
 */

"use strict";

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { webcrypto } = require("node:crypto");

const [base, deviceId, deviceNumber] = process.argv.slice(2);
const origin = new URL(base);
const source = fs.readFileSync(
    path.join(__dirname, "..", "frontend", "client", "client.js"),
    "utf8"
);

const requests = [];
const draws = { drawImage: 0 };
const ctx = new Proxy(
    {},
    {
        get(_target, name) {
            if (name === "measureText") return (text) => ({ width: String(text).length * 8 });
            return (...args) => {
                if (name === "drawImage") draws.drawImage++;
                return args;
            };
        },
        set: () => true,
    }
);
const canvas = { width: 0, height: 0, style: {}, setAttribute() {}, getContext: () => ctx };
const status = {
    state: "connecting",
    hidden: false,
    setAttribute(name, value) {
        if (name === "data-state") status.state = value;
    },
    querySelector: () => ({ textContent: "" }),
};
const storage = {
    "tablet-wall-device-id": deviceId,
    "tablet-wall-device-number": deviceNumber,
};

class LoggedWebSocket extends WebSocket {
    constructor(url) {
        requests.push({ kind: "websocket", url: new URL(String(url), origin).href });
        super(url);
    }
}

const sandbox = {
    console: { log() {}, warn() {}, error() {} },
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    URL,
    performance,
    crypto: webcrypto,
    fetch(url, options) {
        const absolute = new URL(String(url), origin).href;
        requests.push({ kind: "fetch", url: absolute });
        return fetch(absolute, options);
    },
    WebSocket: LoggedWebSocket,
    createImageBitmap: async (blob) => ({ width: 96, height: 64, size: blob.size, close() {} }),
    document: {
        getElementById: (id) => (id === "surface" ? canvas : id === "status" ? status : null),
        documentElement: { clientWidth: 800, clientHeight: 600, style: { setProperty() {} } },
        createElement: () => canvas,
        body: { appendChild() {} },
        addEventListener() {},
    },
    window: {
        innerWidth: 800,
        innerHeight: 600,
        devicePixelRatio: 1,
        location: {
            protocol: "http:",
            host: origin.host,
            href: origin.href + "client/",
            origin: origin.origin,
        },
        addEventListener() {},
    },
    localStorage: {
        getItem: (key) => (key in storage ? storage[key] : null),
        setItem: (key, value) => (storage[key] = String(value)),
        removeItem: (key) => delete storage[key],
    },
};
vm.runInContext(source, vm.createContext(sandbox), { filename: "client.js" });

const deadline = Date.now() + 8000;
(function poll() {
    const assetRequests = requests.filter((r) => /\/assets\/sha256:/.test(r.url));
    if ((status.state === "connected" && draws.drawImage > 0) || Date.now() > deadline) {
        console.log(
            JSON.stringify({
                connected: status.state === "connected",
                painted: draws.drawImage > 0,
                assets: assetRequests.map((r) => new URL(r.url).pathname),
                requests,
            })
        );
        process.exit(0);
    }
    setTimeout(poll, 50);
})();
