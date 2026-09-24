"use strict";

(function () {
    /* ------------------------------------------------------------------ *
     * tablet-wall-ai — controller
     *
     * Transport (PROTOCOL.md):
     *   - One WebSocket to /ws/controller. The controller only listens;
     *     it never sends anything meaningful up the socket.
     *   - All commands are plain HTTP POST/DELETE.
     *
     * There is NO polling. The only timer is a 1 Hz UI tick that redraws
     * relative timestamps and the reconnect countdown; it never touches
     * the network.
     * ------------------------------------------------------------------ */

    const WS_PATH = "/ws/controller";

    /* Tasteful preset palette — solid colours, no gradients. */
    const PRESETS = [
        { color: "#ef4444", name: "red" },
        { color: "#f97316", name: "orange" },
        { color: "#eab308", name: "amber" },
        { color: "#22c55e", name: "green" },
        { color: "#14b8a6", name: "teal" },
        { color: "#3b82f6", name: "blue" },
        { color: "#6366f1", name: "indigo" },
        { color: "#a855f7", name: "violet" },
        { color: "#ec4899", name: "pink" },
        { color: "#64748b", name: "slate" },
        { color: "#000000", name: "black" },
        { color: "#ffffff", name: "white" }
    ];

    /* Reconnect backoff: 0.5s, 1s, 2s, ... capped at 15s, ±20% jitter. */
    const BACKOFF_BASE_MS = 500;
    const BACKOFF_MAX_MS = 15000;
    const BACKOFF_FACTOR = 2;
    const BACKOFF_JITTER = 0.2;

    const REQUEST_TIMEOUT_MS = 10000;
    const FORGET_CONFIRM_MS = 8000;
    const HEX_RE = /^#?[0-9a-fA-F]{6}$/;

    /* ------------------------------------------------------------------ *
     * DOM
     * ------------------------------------------------------------------ */

    const el = {
        conn: document.getElementById("conn"),
        connLabel: document.getElementById("conn-label"),
        btnReconnect: document.getElementById("btn-reconnect"),
        tallyOnline: document.getElementById("tally-online"),
        tallyTotal: document.getElementById("tally-total"),
        globalPalette: document.getElementById("global-palette"),
        globalColor: document.getElementById("global-color"),
        globalSel: document.getElementById("global-sel"),
        btnApplyAll: document.getElementById("btn-apply-all"),
        grid: document.getElementById("grid"),
        empty: document.getElementById("empty"),
        emptyConn: document.getElementById("empty-conn"),
        clientUrl: document.getElementById("client-url"),
        btnCopyUrl: document.getElementById("btn-copy-url"),
        statusStamp: document.getElementById("status-stamp"),
        statusText: document.getElementById("status-text"),
        tileTpl: document.getElementById("tile-tpl")
    };

    /* ------------------------------------------------------------------ *
     * State
     * ------------------------------------------------------------------ */

    /** device_id -> device record (PROTOCOL.md "device record" shape). */
    const devices = new Map();

    /** device_id -> { el, ...element refs } */
    const tiles = new Map();

    /** Last rendered tile order; used so we only touch the DOM order when
     *  membership actually changes (moving nodes would blur focus). */
    let tileOrder = [];

    let ws = null;
    let connState = "connecting"; // "connecting" | "open" | "down"
    let attempt = 0;              // consecutive failed connection attempts
    let reconnectTimer = null;
    let retryAt = 0;              // epoch ms of the next scheduled attempt
    let awaitingSnapshot = false; // true between socket-open and first snapshot

    let globalColor = null;
    let confirmingId = null;
    let confirmTimer = null;

    /* ------------------------------------------------------------------ *
     * Small helpers
     * ------------------------------------------------------------------ */

    function shortId(id) {
        return String(id).slice(0, 8);
    }

    /** "#3B82F6" / "3b82f6" -> "#3b82f6"; anything else -> null. */
    function normalizeColor(value) {
        if (typeof value !== "string") return null;
        const trimmed = value.trim();
        if (!HEX_RE.test(trimmed)) return null;
        return "#" + trimmed.replace(/^#/, "").toLowerCase();
    }

    /** "3s ago" / "4m ago" ... — DOM-only, no network. */
    function relTime(iso) {
        const t = Date.parse(iso);
        if (Number.isNaN(t)) return "—";
        const seconds = Math.max(0, (Date.now() - t) / 1000);
        if (seconds < 5) return "just now";
        if (seconds < 60) return Math.floor(seconds) + "s ago";
        if (seconds < 3600) return Math.floor(seconds / 60) + "m ago";
        if (seconds < 86400) return Math.floor(seconds / 3600) + "h ago";
        return Math.floor(seconds / 86400) + "d ago";
    }

    function absTime(iso) {
        const t = Date.parse(iso);
        if (Number.isNaN(t)) return "";
        return new Date(t).toLocaleString();
    }

    /**
     * What the "last seen" row should read.
     *
     * The server only pushes a fresh `last_seen` when something actually
     * changes, so a device that is happily heartbeating does NOT refresh the
     * value cached here. Ticking a relative time upwards for a tablet that is
     * demonstrably present would claim it is drifting away, so an online
     * device reads as live and only an offline one reports how long it has
     * been gone.
     */
    function seenLabel(device) {
        return device.online === true ? "live" : relTime(device.last_seen);
    }

    function pad2(n) {
        return n < 10 ? "0" + n : String(n);
    }

    function clockStamp() {
        const d = new Date();
        return pad2(d.getHours()) + ":" + pad2(d.getMinutes()) + ":" + pad2(d.getSeconds());
    }

    function logStatus(text, kind) {
        el.statusStamp.textContent = clockStamp();
        el.statusText.textContent = text;
        el.statusText.dataset.kind = kind || "info";
    }

    function compareIds(a, b) {
        return a < b ? -1 : a > b ? 1 : 0;
    }

    /* ------------------------------------------------------------------ *
     * Transport — WebSocket with reconnect + backoff
     * ------------------------------------------------------------------ */

    function wsUrl() {
        const scheme = location.protocol === "https:" ? "wss:" : "ws:";
        return scheme + "//" + location.host + WS_PATH;
    }

    function connect() {
        if (reconnectTimer) {
            clearTimeout(reconnectTimer);
            reconnectTimer = null;
        }
        if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
            return;
        }
        if (typeof WebSocket === "undefined") {
            connState = "down";
            renderConn();
            logStatus("This browser has no WebSocket support.", "err");
            return;
        }

        retryAt = 0;
        connState = "connecting";
        renderConn();

        let socket;
        try {
            socket = new WebSocket(wsUrl());
        } catch (_err) {
            ws = null;
            scheduleReconnect();
            return;
        }
        ws = socket;

        socket.addEventListener("open", function () {
            if (ws !== socket) return;
            attempt = 0;
            retryAt = 0;
            awaitingSnapshot = true; // snapshot is the first frame on connect
            connState = "open";
            renderConn();
            logStatus("Roster socket open — waiting for the snapshot.", "info");
        });

        socket.addEventListener("message", function (event) {
            if (ws !== socket) return;
            handleMessage(event.data);
        });

        socket.addEventListener("error", function () {
            /* "close" always follows; let that drive the retry. */
        });

        socket.addEventListener("close", function () {
            if (ws !== socket) return;
            ws = null;
            scheduleReconnect();
        });
    }

    function scheduleReconnect() {
        const exp = Math.min(BACKOFF_MAX_MS, BACKOFF_BASE_MS * Math.pow(BACKOFF_FACTOR, attempt));
        const jitter = 1 + (Math.random() * 2 - 1) * BACKOFF_JITTER;
        const delay = Math.max(250, Math.round(exp * jitter));

        attempt += 1;
        retryAt = Date.now() + delay;
        connState = "down";
        renderConn();
        logStatus(
            "Lost the roster socket — retry " + attempt + " in " + (delay / 1000).toFixed(1) + "s.",
            "err"
        );

        if (reconnectTimer) return;
        reconnectTimer = setTimeout(function () {
            reconnectTimer = null;
            connect();
        }, delay);
    }

    function reconnectNow() {
        if (reconnectTimer) {
            clearTimeout(reconnectTimer);
            reconnectTimer = null;
        }
        attempt = 0;
        retryAt = 0;
        const old = ws;
        ws = null;
        if (old) {
            try {
                old.close();
            } catch (_err) {
                /* already gone */
            }
        }
        logStatus("Reconnecting now…", "info");
        connect();
    }

    function renderConn() {
        el.conn.dataset.state = connState;
        let label;
        if (connState === "open") {
            label = "socket open";
        } else if (connState === "connecting") {
            label = "connecting…";
        } else {
            const secs = retryAt ? Math.max(0, Math.ceil((retryAt - Date.now()) / 1000)) : 0;
            label = attempt > 0 ? "retry in " + secs + "s · attempt " + attempt : "disconnected";
        }
        el.connLabel.textContent = label;
        el.conn.title = wsUrl();
        el.btnReconnect.hidden = connState === "open";
        renderEmptyConn();
    }

    /* ------------------------------------------------------------------ *
     * Incoming messages (server → controller)
     * ------------------------------------------------------------------ */

    function handleMessage(raw) {
        let msg;
        try {
            msg = JSON.parse(raw);
        } catch (_err) {
            return; // malformed frames are ignored, not fatal
        }
        if (!msg || typeof msg.type !== "string") return;

        switch (msg.type) {
            case "snapshot": {
                if (!Array.isArray(msg.devices)) return;
                devices.clear();
                for (const device of msg.devices) {
                    if (device && typeof device.device_id === "string") {
                        devices.set(device.device_id, device);
                    }
                }
                if (awaitingSnapshot) {
                    awaitingSnapshot = false;
                    logStatus(
                        "Snapshot received — " + devices.size + " device(s) on the wall.",
                        "info"
                    );
                }
                syncTiles();
                break;
            }

            case "device_online":
            case "device_updated": {
                const device = msg.device;
                if (!device || typeof device.device_id !== "string") return;
                const previous = devices.get(device.device_id);
                devices.set(device.device_id, previous ? Object.assign({}, previous, device) : device);
                syncTiles();
                break;
            }

            case "device_offline": {
                const id = msg.device_id;
                if (typeof id !== "string") return;
                const previous = devices.get(id);
                if (!previous) return; // unknown device: nothing to dim
                devices.set(id, Object.assign({}, previous, {
                    online: false,
                    last_seen: typeof msg.last_seen === "string" ? msg.last_seen : previous.last_seen
                }));
                syncTiles();
                break;
            }

            case "device_removed": {
                // Another controller issued the DELETE, or this one did and the
                // echo arrived after the local removal. Either way the device is
                // gone from the roster, so drop any tile still showing it.
                const id = msg.device_id;
                if (typeof id !== "string") return;
                if (!devices.delete(id)) return; // already gone locally
                syncTiles();
                break;
            }

            default:
                return; // unrecognised frames are ignored
        }
    }

    /* ------------------------------------------------------------------ *
     * Rendering
     * ------------------------------------------------------------------ */

    function syncTiles() {
        const ids = Array.from(devices.keys()).sort(compareIds);

        for (const id of Array.from(tiles.keys())) {
            if (!devices.has(id)) removeTile(id);
        }

        for (const id of ids) {
            let tile = tiles.get(id);
            if (!tile) {
                tile = createTile(id);
                tiles.set(id, tile);
            }
            updateTile(tile, devices.get(id));
        }

        const changed =
            ids.length !== tileOrder.length ||
            ids.some(function (id, i) { return tileOrder[i] !== id; });
        if (changed) {
            for (const id of ids) {
                el.grid.appendChild(tiles.get(id).el);
            }
            tileOrder = ids;
        }

        renderTally();
        renderEmpty();
    }

    function createTile(id) {
        const node = el.tileTpl.content.firstElementChild.cloneNode(true);
        node.dataset.id = id;

        const tile = {
            el: node,
            devId: node.querySelector(".dev-id"),
            badgeLabel: node.querySelector(".badge-label"),
            screenFill: node.querySelector(".screen-fill"),
            screenNote: node.querySelector(".screen-note"),
            res: node.querySelector(".meta-res"),
            type: node.querySelector(".meta-type"),
            seen: node.querySelector(".fact-seen"),
            curSwatch: node.querySelector(".cur-swatch"),
            curHex: node.querySelector(".cur-hex"),
            palette: node.querySelector(".palette-sm"),
            colourInput: node.querySelector(".tile-colour-input"),
            foot: node.querySelector(".tile-foot")
        };

        tile.devId.textContent = shortId(id);
        tile.devId.title = id;

        for (const preset of PRESETS) {
            tile.palette.appendChild(makeSwatch(preset, "set-color"));
        }

        buildTileFoot(tile, id);
        return tile;
    }

    function makeSwatch(preset, action) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "swatch";
        button.dataset.action = action;
        button.dataset.color = preset.color;
        button.style.background = preset.color;
        button.title = preset.name + " " + preset.color;
        button.setAttribute("aria-label", preset.name + " " + preset.color);
        if (action === "global-color") {
            button.setAttribute("aria-pressed", "false");
        }
        return button;
    }

    function buildTileFoot(tile, deviceId) {
        tile.foot.textContent = "";
        // The colour picker lives in the footer but survives footer rebuilds
        // (forget-confirmation swaps the buttons out from under it).
        tile.foot.appendChild(tile.colourInput);

        const forget = document.createElement("button");
        forget.type = "button";
        forget.className = "btn btn-danger btn-sm";
        forget.dataset.action = "forget";
        forget.textContent = "Forget";
        applyForgetAvailability(forget, deviceId);
        tile.foot.appendChild(forget);
    }

    /**
     * Whether a device can be forgotten at all.
     *
     * A connected tablet re-registers the instant its socket closes, so
     * forgetting a live one would not stick: the tile would vanish and then
     * reappear a moment later, which reads as a broken button. Forget is
     * therefore offered only for tablets that are genuinely gone.
     */
    function applyForgetAvailability(button, deviceId) {
        const device = devices.get(deviceId);
        const online = !!device && device.online === true;
        button.disabled = online;
        button.title = online
            ? "Connected — forgetting it would not stick. Close the tablet first."
            : "Remove this tablet from the roster";
    }

    function updateTile(tile, device) {
        const online = device.online === true;
        tile.el.dataset.state = online ? "online" : "offline";
        tile.badgeLabel.textContent = online ? "ONLINE" : "OFFLINE";

        // Re-applied on every sync so the button tracks presence changes.
        const forget = tile.foot.querySelector('[data-action="forget"]');
        if (forget) applyForgetAvailability(forget, device.device_id);

        const w = Number(device.width);
        const h = Number(device.height);
        tile.res.textContent =
            Number.isFinite(w) && Number.isFinite(h) && device.width != null && device.height != null
                ? w + "×" + h
                : "—";
        tile.type.textContent = typeof device.type === "string" && device.type ? device.type : "—";

        const color = normalizeColor(device.color);
        if (color) {
            tile.screenFill.style.background = color;
            tile.screenNote.hidden = true;
            tile.curSwatch.style.background = color;
            tile.curSwatch.dataset.empty = "false";
            tile.curHex.textContent = color;
            if (normalizeColor(tile.colourInput.value) !== color) {
                tile.colourInput.value = color;
            }
        } else {
            tile.screenFill.style.background = "";
            tile.screenNote.hidden = false;
            tile.curSwatch.style.background = "";
            tile.curSwatch.dataset.empty = "true";
            tile.curHex.textContent = "unset";
        }

        tile.seen.textContent = seenLabel(device);
        tile.seen.title = absTime(device.last_seen);
    }

    function removeTile(id) {
        const tile = tiles.get(id);
        if (!tile) return;
        if (confirmingId === id) {
            if (confirmTimer) clearTimeout(confirmTimer);
            confirmTimer = null;
            confirmingId = null;
        }
        tile.el.remove();
        tiles.delete(id);
    }

    function renderTally() {
        let online = 0;
        for (const device of devices.values()) {
            if (device.online === true) online += 1;
        }
        el.tallyOnline.textContent = String(online);
        el.tallyTotal.textContent = String(devices.size);
    }

    /* Empty state: shown only when no device has registered (yet). */
    function renderEmpty() {
        el.empty.hidden = devices.size > 0;
        el.grid.hidden = devices.size === 0;
        renderEmptyConn();
    }

    function renderEmptyConn() {
        if (el.empty.hidden) return;
        if (connState === "open") {
            el.emptyConn.textContent = "socket open · waiting for the first tablet";
        } else if (connState === "connecting") {
            el.emptyConn.textContent = "connecting to " + wsUrl();
        } else {
            const secs = retryAt ? Math.max(0, Math.ceil((retryAt - Date.now()) / 1000)) : 0;
            el.emptyConn.textContent = "connection lost · retrying in " + secs + "s";
        }
    }

    /* ------------------------------------------------------------------ *
     * 1 Hz UI tick — redraws relative timestamps only. No network.
     * ------------------------------------------------------------------ */

    function tick() {
        for (const id of tiles.keys()) {
            const device = devices.get(id);
            const tile = tiles.get(id);
            if (device && tile) tile.seen.textContent = seenLabel(device);
        }
        if (connState !== "open") renderConn();
    }

    /* ------------------------------------------------------------------ *
     * HTTP commands
     * ------------------------------------------------------------------ */

    async function requestJson(method, path, body) {
        const options = { method: method, headers: {} };
        if (body !== undefined) {
            options.headers["Content-Type"] = "application/json";
            options.body = JSON.stringify(body);
        }

        let response;
        if (typeof AbortController === "function") {
            const controller = new AbortController();
            options.signal = controller.signal;
            const timer = setTimeout(function () { controller.abort(); }, REQUEST_TIMEOUT_MS);
            try {
                response = await fetch(path, options);
            } catch (err) {
                throw new Error(err && err.name === "AbortError" ? "request timed out" : "server unreachable");
            } finally {
                clearTimeout(timer);
            }
        } else {
            try {
                response = await fetch(path, options);
            } catch (_err) {
                throw new Error("server unreachable");
            }
        }

        let data = null;
        try {
            data = await response.json();
        } catch (_err) {
            /* non-JSON body: fall through to status handling */
        }
        if (!response.ok) {
            const detail = data && typeof data.detail === "string" ? data.detail : "HTTP " + response.status;
            const error = new Error(detail);
            // Carry the status explicitly: callers branch on it, and the
            // server's detail text is not guaranteed to mention the code.
            error.status = response.status;
            throw error;
        }
        return data;
    }

    async function setDeviceColor(deviceId, rawColor) {
        const color = normalizeColor(rawColor);
        const tile = tiles.get(deviceId);
        if (!color) {
            logStatus("Not a #rrggbb colour: " + rawColor, "err");
            return;
        }
        if (tile) tile.el.dataset.busy = "true";

        try {
            const data = await requestJson(
                "POST",
                "/devices/" + encodeURIComponent(deviceId) + "/color",
                { color: color }
            );
            const applied = (data && normalizeColor(data.color)) || color;
            const delivered = Boolean(data && data.delivered === true);

            const device = devices.get(deviceId);
            if (device) {
                const next = Object.assign({}, device, { color: applied });
                devices.set(deviceId, next);
                if (tile && tiles.get(deviceId) === tile) updateTile(tile, next);
            }

            logStatus(
                "#" + shortId(deviceId) + " → " + applied +
                    (delivered ? " · delivered" : " · stored, applies when the tablet reconnects"),
                delivered ? "ok" : "info"
            );
        } catch (err) {
            logStatus("Colour not applied to #" + shortId(deviceId) + ": " + err.message, "err");
        } finally {
            if (tile) tile.el.dataset.busy = "false";
        }
    }

    async function applyToAll(rawColor) {
        const color = normalizeColor(rawColor);
        if (!color) return;

        el.btnApplyAll.disabled = true;
        try {
            const data = await requestJson("POST", "/devices/color", { color: color });
            const applied = (data && normalizeColor(data.color)) || color;
            const updated = data && typeof data.updated === "number" ? data.updated : 0;
            const delivered = data && typeof data.delivered === "number" ? data.delivered : 0;

            for (const [id, device] of devices) {
                devices.set(id, Object.assign({}, device, { color: applied }));
            }
            syncTiles();

            if (updated === 0) {
                logStatus("Applied " + applied + " to 0 devices — the roster is empty.", "info");
            } else {
                logStatus(
                    "Applied " + applied + " to " + updated + " device(s) · delivered to " + delivered,
                    "ok"
                );
            }
        } catch (err) {
            logStatus("Apply-to-all failed: " + err.message, "err");
        } finally {
            el.btnApplyAll.disabled = !globalColor;
        }
    }

    async function forgetDevice(deviceId) {
        const tile = tiles.get(deviceId);
        if (tile) tile.el.dataset.busy = "true";

        try {
            await requestJson("DELETE", "/devices/" + encodeURIComponent(deviceId));
            dropDevice(deviceId);
            logStatus("Forgot device #" + shortId(deviceId) + ".", "ok");
        } catch (err) {
            if (err.status === 404) {
                // Already gone from the server's roster — forget it locally too.
                dropDevice(deviceId);
                logStatus("Device #" + shortId(deviceId) + " was already gone.", "info");
            } else {
                logStatus("Could not forget #" + shortId(deviceId) + ": " + err.message, "err");
                if (tile) tile.el.dataset.busy = "false";
            }
        }
    }

    function dropDevice(deviceId) {
        devices.delete(deviceId);
        removeTile(deviceId);
        renderTally();
        renderEmpty();
    }

    /* ------------------------------------------------------------------ *
     * Forget — two-step confirmation
     * ------------------------------------------------------------------ */

    function beginForget(deviceId) {
        if (confirmingId) cancelForget(confirmingId);
        const tile = tiles.get(deviceId);
        if (!tile) return;

        confirmingId = deviceId;
        tile.foot.textContent = "";

        const question = document.createElement("span");
        question.className = "forget-q";
        question.textContent = "Forget this device?";

        const yes = document.createElement("button");
        yes.type = "button";
        yes.className = "btn btn-danger btn-sm";
        yes.dataset.action = "forget-confirm";
        yes.textContent = "Forget";

        const no = document.createElement("button");
        no.type = "button";
        no.className = "btn btn-ghost btn-sm";
        no.dataset.action = "forget-cancel";
        no.textContent = "Cancel";

        tile.foot.append(question, yes, no);
        yes.focus();

        confirmTimer = setTimeout(function () {
            cancelForget(deviceId);
        }, FORGET_CONFIRM_MS);
    }

    function cancelForget(deviceId) {
        if (confirmingId !== deviceId) return;
        if (confirmTimer) clearTimeout(confirmTimer);
        confirmTimer = null;
        confirmingId = null;
        const tile = tiles.get(deviceId);
        if (tile) buildTileFoot(tile, deviceId);
    }

    /* ------------------------------------------------------------------ *
     * Global colour selection (no network until "Apply to all")
     * ------------------------------------------------------------------ */

    function selectGlobalColor(rawColor) {
        const color = normalizeColor(rawColor);
        globalColor = color;
        el.globalSel.textContent = color || "—";
        el.btnApplyAll.disabled = !color;
        el.btnApplyAll.textContent = color ? "Apply " + color + " to all" : "Apply to all";
        if (color) el.globalColor.value = color;

        for (const button of el.globalPalette.querySelectorAll(".swatch")) {
            button.setAttribute("aria-pressed", String(button.dataset.color === color));
        }
    }

    function buildGlobalPalette() {
        for (const preset of PRESETS) {
            const button = makeSwatch(preset, "global-color");
            button.setAttribute(
                "aria-label",
                "Select " + preset.name + " " + preset.color + " for all devices"
            );
            el.globalPalette.appendChild(button);
        }
    }

    /* ------------------------------------------------------------------ *
     * Events
     * ------------------------------------------------------------------ */

    function bindEvents() {
        el.btnReconnect.addEventListener("click", reconnectNow);

        el.globalPalette.addEventListener("click", function (event) {
            const button = event.target.closest("button[data-color]");
            if (button) selectGlobalColor(button.dataset.color);
        });

        el.globalColor.addEventListener("input", function () {
            selectGlobalColor(el.globalColor.value);
        });

        el.btnApplyAll.addEventListener("click", function () {
            applyToAll(globalColor);
        });

        // Per-tile buttons (presets, forget, confirm/cancel).
        el.grid.addEventListener("click", function (event) {
            const button = event.target.closest("button[data-action]");
            if (!button) return;
            const tileEl = button.closest(".tile");
            if (!tileEl) return;
            const id = tileEl.dataset.id;

            switch (button.dataset.action) {
                case "set-color":
                    setDeviceColor(id, button.dataset.color);
                    break;
                case "forget":
                    beginForget(id);
                    break;
                case "forget-cancel":
                    cancelForget(id);
                    break;
                case "forget-confirm":
                    forgetDevice(id);
                    break;
                default:
                    break;
            }
        });

        // Per-tile native colour picker — fires once, when the operator commits.
        el.grid.addEventListener("change", function (event) {
            const input = event.target;
            if (!input.matches || !input.matches('input[type="color"]')) return;
            const tileEl = input.closest(".tile");
            if (!tileEl) return;
            setDeviceColor(tileEl.dataset.id, input.value);
        });

        el.btnCopyUrl.addEventListener("click", function () {
            const text = el.clientUrl.textContent;
            // navigator.clipboard is secure-context only — guard it.
            if (window.isSecureContext && navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(
                    function () { logStatus("Client URL copied.", "ok"); },
                    function () { selectClientUrl(); }
                );
            } else {
                selectClientUrl();
            }
        });
    }

    function selectClientUrl() {
        try {
            const range = document.createRange();
            range.selectNodeContents(el.clientUrl);
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
        } catch (_err) {
            /* selection unavailable — the URL is still visible on screen */
        }
        logStatus("Clipboard unavailable — press Ctrl/Cmd+C to copy the highlighted URL.", "info");
    }

    /* ------------------------------------------------------------------ *
     * Boot
     * ------------------------------------------------------------------ */

    function init() {
        buildGlobalPalette();
        bindEvents();
        el.clientUrl.textContent = location.origin + "/client/";
        renderConn();
        renderEmpty();
        logStatus("Connecting to " + wsUrl() + " …", "info");
        connect();
        setInterval(tick, 1000);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
