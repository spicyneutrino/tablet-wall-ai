/*
 * tablet-wall client page.
 *
 * Runs full-screen on a wall-mounted tablet. Registers a device id with the
 * server, opens a device WebSocket, heartbeats on the interval the server
 * asks for in its `welcome` frame, and paints the whole viewport with any
 * colour the server sends.
 *
 * Must work on a plain-HTTP LAN origin with no internet access, so:
 *   - no external resources of any kind,
 *   - no secure-context-only API is ever called unguarded.
 *
 * See PROTOCOL.md for the message contract.
 */
(function () {
    "use strict";

    /* ------------------------------------------------------------------ */
    /* Constants                                                          */
    /* ------------------------------------------------------------------ */

    var STORAGE_KEY = "tablet-wall-device-id";
    var REGISTER_URL = "/devices/register";
    var DEVICE_TYPE = "ipad"; // device geometry is a later phase

    var BACKOFF_MIN_MS = 500;
    var BACKOFF_MAX_MS = 15000;
    var REGISTER_TIMEOUT_MS = 10000;
    var DEFAULT_HEARTBEAT_MS = 5000; // only used if welcome omits the value

    var UUID_V4_RE =
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

    var STATUS_TEXT = {
        connecting: "Connecting\u2026",
        reconnecting: "Reconnecting\u2026",
        offline: "Offline \u00b7 retrying",
        connected: "",
    };

    /* ------------------------------------------------------------------ */
    /* Status indicator                                                   */
    /* ------------------------------------------------------------------ */

    var statusEl = document.getElementById("status");
    var statusTextEl = statusEl
        ? statusEl.querySelector(".status-text")
        : null;

    function setStatus(state) {
        if (!statusEl || !statusTextEl) return;
        statusEl.setAttribute("data-state", state);
        statusTextEl.textContent = STATUS_TEXT[state] || "";
    }

    function warn(message, err) {
        var detail =
            err && err.message ? err.message : err != null ? String(err) : "";
        if (detail) {
            console.warn("[tablet-wall] " + message + ":", detail);
        } else {
            console.warn("[tablet-wall] " + message);
        }
    }

    /* ------------------------------------------------------------------ */
    /* Device identity                                                    */
    /* ------------------------------------------------------------------ */

    /* byteHex is an array of 16 two-character hex strings. */
    function formatUuid(byteHex) {
        return [
            byteHex.slice(0, 4).join(""),
            byteHex.slice(4, 6).join(""),
            byteHex.slice(6, 8).join(""),
            byteHex.slice(8, 10).join(""),
            byteHex.slice(10, 16).join(""),
        ].join("-");
    }

    function bytesToHex(bytes) {
        var hex = [];
        for (var i = 0; i < bytes.length; i++) {
            hex.push(bytes[i].toString(16).padStart(2, "0"));
        }
        return hex;
    }

    /* RFC 4122 version 4 UUID built from crypto.getRandomValues(). */
    function uuidV4FromGetRandomValues() {
        var bytes = new Uint8Array(16);
        crypto.getRandomValues(bytes);
        bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
        bytes[8] = (bytes[8] & 0x3f) | 0x80; // RFC 4122 variant 10xx
        return formatUuid(bytesToHex(bytes));
    }

    /*
     * Last resort: a non-cryptographic id (Math.random), shaped like a UUID4
     * so the server's UUID4 validation still accepts it. Clearly labelled
     * here and in the console warning below. This path only runs when crypto
     * is entirely absent, which never happens on a real tablet browser.
     */
    function uuidV4FromMathRandom() {
        var nibbles = [];
        for (var i = 0; i < 32; i++) {
            nibbles.push(Math.floor(Math.random() * 16));
        }
        nibbles[12] = 4; // version 4 (high nibble of byte 6)
        nibbles[16] = (nibbles[16] & 0x3) | 0x8; // RFC 4122 variant
        var bytes = [];
        for (var j = 0; j < 16; j++) {
            bytes.push(nibbles[j * 2] * 16 + nibbles[j * 2 + 1]);
        }
        return formatUuid(bytesToHex(bytes));
    }

    function newDeviceId() {
        var webCrypto = typeof crypto !== "undefined" ? crypto : null;

        // 1. crypto.randomUUID() is secure-context-only — guard the lookup
        //    and the call, and fall through if either misbehaves.
        try {
            if (webCrypto && typeof webCrypto.randomUUID === "function") {
                return webCrypto.randomUUID();
            }
        } catch (err) {
            warn("crypto.randomUUID unavailable", err);
        }

        // 2. crypto.getRandomValues() is exposed outside secure contexts, so
        //    this is the path a plain-HTTP LAN tablet takes.
        try {
            if (webCrypto && typeof webCrypto.getRandomValues === "function") {
                return uuidV4FromGetRandomValues();
            }
        } catch (err) {
            warn("crypto.getRandomValues unavailable", err);
        }

        // 3. No crypto at all — usable but NOT cryptographically random.
        warn("crypto unavailable; using a NON-CRYPTOGRAPHIC device id");
        return uuidV4FromMathRandom();
    }

    function resolveDeviceId() {
        try {
            var stored = localStorage.getItem(STORAGE_KEY);
            if (stored && UUID_V4_RE.test(stored)) {
                return stored;
            }
            if (stored) {
                warn("stored device id is not a UUID4; generating a new one");
            }
        } catch (err) {
            warn("localStorage unavailable", err);
        }

        var id = newDeviceId();
        try {
            localStorage.setItem(STORAGE_KEY, id);
        } catch (err) {
            warn("could not persist device id", err);
        }
        return id;
    }

    var deviceId = resolveDeviceId();

    /* ------------------------------------------------------------------ */
    /* HTTP                                                               */
    /* ------------------------------------------------------------------ */

    function fetchWithTimeout(url, options, timeoutMs) {
        if (typeof AbortController !== "function") {
            return fetch(url, options);
        }
        var controller = new AbortController();
        var timer = setTimeout(function () {
            controller.abort();
        }, timeoutMs);
        return fetch(url, Object.assign({}, options, { signal: controller.signal })).then(
            function (response) {
                clearTimeout(timer);
                return response;
            },
            function (err) {
                clearTimeout(timer);
                throw err;
            }
        );
    }

    /* Re-register before EVERY connection attempt: server state is in memory
     * and may have been lost to a restart. Throws on failure; the caller
     * backs off and retries instead of dying. */
    function register() {
        return fetchWithTimeout(
            REGISTER_URL,
            {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    device_id: deviceId,
                    width: window.screen.width,
                    height: window.screen.height,
                    device_type: DEVICE_TYPE,
                }),
            },
            REGISTER_TIMEOUT_MS
        ).then(function (response) {
            if (!response.ok) {
                throw new Error("registration failed: HTTP " + response.status);
            }
            return response;
        });
    }

    /* ------------------------------------------------------------------ */
    /* WebSocket                                                          */
    /* ------------------------------------------------------------------ */

    function deviceSocketUrl() {
        var scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
        return (
            scheme +
            "//" +
            window.location.host +
            "/ws/device?device_id=" +
            encodeURIComponent(deviceId)
        );
    }

    var heartbeatTimer = null;
    var welcomedOnce = false;

    function stopHeartbeat() {
        if (heartbeatTimer !== null) {
            clearInterval(heartbeatTimer);
            heartbeatTimer = null;
        }
    }

    /* Interval comes from the welcome frame; the constant is only a fallback
     * for a malformed frame. */
    function startHeartbeat(socket, intervalMs) {
        stopHeartbeat();
        var ms = Number(intervalMs);
        if (!Number.isFinite(ms) || ms <= 0) {
            ms = DEFAULT_HEARTBEAT_MS;
        }
        heartbeatTimer = setInterval(function () {
            try {
                if (socket.readyState === WebSocket.OPEN) {
                    socket.send(JSON.stringify({ type: "heartbeat" }));
                }
            } catch (err) {
                warn("heartbeat send failed", err);
            }
        }, ms);
    }

    function applyColor(color) {
        if (typeof color !== "string" || color.length === 0) return;
        document.documentElement.style.setProperty("--surface-color", color);
    }

    function handleFrame(socket, raw, onWelcome) {
        var frame;
        try {
            frame = JSON.parse(raw);
        } catch (err) {
            return; // unrecognised frames are ignored, not fatal
        }
        if (!frame || typeof frame !== "object") return;

        if (frame.type === "welcome") {
            welcomedOnce = true;
            resetBackoff();
            startHeartbeat(socket, frame.heartbeat_interval_ms);
            setStatus("connected");
            onWelcome();
        } else if (frame.type === "set_color") {
            applyColor(frame.color);
        }
    }

    /* Resolves when the socket closes, with `true` if a `welcome` arrived. */
    function openSocket() {
        return new Promise(function (resolve) {
            var socket;
            try {
                socket = new WebSocket(deviceSocketUrl());
            } catch (err) {
                warn("could not open websocket", err);
                resolve(false);
                return;
            }

            var welcomed = false;

            socket.addEventListener("message", function (event) {
                if (typeof event.data !== "string") return;
                handleFrame(socket, event.data, function () {
                    welcomed = true;
                });
            });

            socket.addEventListener("error", function () {
                // A close event always follows; nothing to do here.
            });

            socket.addEventListener("close", function () {
                stopHeartbeat();
                resolve(welcomed);
            });
        });
    }

    /* ------------------------------------------------------------------ */
    /* Reconnect loop                                                     */
    /* ------------------------------------------------------------------ */

    var backoffMs = BACKOFF_MIN_MS;

    function resetBackoff() {
        backoffMs = BACKOFF_MIN_MS;
    }

    /* Exponential backoff with equal jitter: base doubles every attempt from
     * ~500 ms up to ~15 s, plus up to 25% random jitter. */
    function nextDelay() {
        var base = backoffMs;
        backoffMs = Math.min(base * 2, BACKOFF_MAX_MS);
        var jitter = Math.floor(Math.random() * base * 0.25);
        return Math.min(base + jitter, BACKOFF_MAX_MS);
    }

    function sleep(ms) {
        return new Promise(function (resolve) {
            setTimeout(resolve, ms);
        });
    }

    /* One register + connect cycle. Never throws. */
    function attemptCycle() {
        setStatus(welcomedOnce ? "reconnecting" : "connecting");
        return register()
            .then(function () {
                return openSocket(); // resolves only when the socket closes
            })
            .catch(function (err) {
                warn("connection attempt failed", err);
            })
            .then(function () {
                setStatus(welcomedOnce ? "reconnecting" : "offline");
            });
    }

    async function run() {
        for (;;) {
            try {
                await attemptCycle();
            } catch (err) {
                warn("connection cycle failed", err);
                setStatus(welcomedOnce ? "reconnecting" : "offline");
            }
            await sleep(nextDelay());
        }
    }

    /* Never let a rejection escape to the console unhandled. */
    run().catch(function (err) {
        warn("client stopped unexpectedly", err);
        setStatus("offline");
    });
})();
