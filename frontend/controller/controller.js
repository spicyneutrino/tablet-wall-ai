"use strict";

(function () {
    /* ------------------------------------------------------------------ *
     * tablet-wall-ai — controller
     *
     * Transport (PROTOCOL.md):
     *   - One WebSocket to /ws/controller?protocol=2. The controller only
     *     listens; it never sends anything meaningful up the socket.
     *   - All commands are plain HTTP POST/PUT/DELETE.
     *   - v2 frames: `snapshot` also carries the wall, and `wall_updated`
     *     replaces it (see "Server → controller (v2 additions)").
     *
     * There is NO polling. The only timer is a 1 Hz UI tick that redraws
     * relative timestamps and the reconnect countdown; it never touches
     * the network. Wall and placement edits are driven by the operator
     * plus the `wall_updated` broadcast.
     * ------------------------------------------------------------------ */

    const WS_PATH = "/ws/controller";
    const PROTOCOL = 2;

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

    /* Wall units are abstract integers. A placement matches the device's
     * reported viewport when the two aspect ratios agree to within this
     * relative tolerance — exact equality is not reachable with integers. */
    const ASPECT_TOLERANCE = 0.01;

    /* Placement inputs per tile: the footprint first, then the bezel. */
    const PLACE_FIELDS = [
        "x", "y", "w", "h",
        "bezel-top", "bezel-right", "bezel-bottom", "bezel-left"
    ];

    /* Preview map frame, in CSS pixels. The wall rectangle keeps its aspect
     * ratio inside these bounds; extreme walls scroll in the viewport. */
    const MAP_MAX_H = 300;
    const MAP_MIN_H = 92;
    const FOCUS_FLASH_MS = 1600;

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
        wallRev: document.getElementById("wall-rev"),
        wallNote: document.getElementById("wall-note"),
        wallForm: document.getElementById("wall-form"),
        wallWidth: document.getElementById("wall-width"),
        wallHeight: document.getElementById("wall-height"),
        wallMode: document.getElementById("wall-mode"),
        btnWallSave: document.getElementById("btn-wall-save"),
        autoColumns: document.getElementById("auto-columns"),
        btnAuto: document.getElementById("btn-auto"),
        mapCaption: document.getElementById("map-caption"),
        mapViewport: document.getElementById("map-viewport"),
        mapFrame: document.getElementById("map-frame"),
        mapEmpty: document.getElementById("map-empty"),
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

    /** Full wall state (PROTOCOL.md "Wall state"); null until the snapshot
     *  delivers one. Sparse `placements` live inside it. */
    let wall = null;

    /** True while the wall form holds unsaved edits, so an incoming
     *  `wall_updated` cannot overwrite what the operator is typing. */
    let wallDirty = false;

    /** Mode chosen in the wall form but not yet saved. */
    let pendingMode = null;

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
     * Wall + geometry helpers (PROTOCOL.md "Wall coordinate space")
     * ------------------------------------------------------------------ */

    function numOr(value, fallback) {
        const n = Number(value);
        return Number.isFinite(n) ? n : fallback;
    }

    /** The footprint shrunk by the bezel — the rect a tablet actually shows. */
    function visibleRect(placement) {
        return {
            x: placement.x + placement.bezel.left,
            y: placement.y + placement.bezel.top,
            w: placement.w - placement.bezel.left - placement.bezel.right,
            h: placement.h - placement.bezel.top - placement.bezel.bottom
        };
    }

    /** width ÷ height of a rect, or null when it cannot be a ratio. */
    function aspectOf(w, h) {
        const ratio = Number(w) / Number(h);
        return Number.isFinite(ratio) && ratio > 0 ? ratio : null;
    }

    /** Relative distance between two aspect ratios; null when unknown. */
    function aspectDelta(visible, viewport) {
        if (visible === null || viewport === null) return null;
        return Math.abs(visible - viewport) / viewport;
    }

    function isAspectMismatch(delta) {
        return delta !== null && delta > ASPECT_TOLERANCE;
    }

    function fmtAspect(ratio) {
        return ratio === null ? "—" : ratio.toFixed(3);
    }

    function fmtDelta(delta) {
        return delta === null ? "—" : (delta * 100).toFixed(1) + "%";
    }

    /** The device's reported viewport as a ratio, or null if not reported. */
    function viewportAspect(device) {
        if (!device || device.width == null || device.height == null) return null;
        return aspectOf(device.width, device.height);
    }

    function normalizePlacement(raw) {
        if (!raw || typeof raw !== "object") return null;
        const x = Number(raw.x);
        const y = Number(raw.y);
        const w = Number(raw.w);
        const h = Number(raw.h);
        if (![x, y, w, h].every(Number.isFinite)) return null;
        const bezel = raw.bezel && typeof raw.bezel === "object" ? raw.bezel : {};
        return {
            x: x,
            y: y,
            w: w,
            h: h,
            bezel: {
                top: numOr(bezel.top, 0),
                right: numOr(bezel.right, 0),
                bottom: numOr(bezel.bottom, 0),
                left: numOr(bezel.left, 0)
            }
        };
    }

    /**
     * Build local wall state from a server payload.
     *
     * A payload that omits `placements` entirely keeps the placements we
     * already hold (`{}` is a real value and is honoured); only a payload
     * that never had them starts empty. `snapshot` clears `wall` first, so
     * a snapshot without a wall genuinely resets to "no wall state".
     */
    function normalizeWall(raw) {
        if (!raw || typeof raw !== "object") return null;
        const placements = {};
        if (raw.placements && typeof raw.placements === "object") {
            for (const id of Object.keys(raw.placements)) {
                const placement = normalizePlacement(raw.placements[id]);
                if (placement) placements[id] = placement;
            }
        } else if (wall) {
            Object.assign(placements, wall.placements);
        }
        return {
            width: Math.max(0, Math.round(numOr(raw.width, 0))),
            height: Math.max(0, Math.round(numOr(raw.height, 0))),
            mode: raw.mode === "calibration" ? "calibration" : "color",
            revision: Math.max(0, Math.round(numOr(raw.revision, 0))),
            placements: placements
        };
    }

    function wallReady() {
        return !!wall && wall.width > 0 && wall.height > 0;
    }

    function savedPlacement(deviceId) {
        return wall && wall.placements ? wall.placements[deviceId] || null : null;
    }

    /**
     * Forget the footprint that belonged to a device that left the roster.
     *
     * PROTOCOL.md specifies that deleting a device also drops its placement,
     * and the server broadcasts the new wall, so this is belt-and-braces: it
     * keeps the diagram correct even if the `device_removed` event arrives
     * before the matching `wall_updated`, or arrives without one.
     */
    function dropPlacement(deviceId) {
        if (!wall || !wall.placements[deviceId]) return false;
        const placements = Object.assign({}, wall.placements);
        delete placements[deviceId];
        wall.placements = placements;
        return true;
    }

    /** "%" position inside the wall or a footprint. */
    function pct(value, total) {
        return total > 0 ? (value / total) * 100 + "%" : "0%";
    }

    /* ------------------------------------------------------------------ *
     * Transport — WebSocket with reconnect + backoff
     * ------------------------------------------------------------------ */

    function wsUrl() {
        const scheme = location.protocol === "https:" ? "wss:" : "ws:";
        return scheme + "//" + location.host + WS_PATH + "?protocol=" + PROTOCOL;
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
                // The snapshot is authoritative: adopt its wall even when the
                // revision moved backwards, which is what a restarted server
                // looks like. Clear first so a v1 snapshot means "no wall".
                wall = null;
                if (msg.wall) wall = normalizeWall(msg.wall);
                if (!wallDirty && wall) pendingMode = wall.mode;
                if (awaitingSnapshot) {
                    awaitingSnapshot = false;
                    logStatus(
                        "Snapshot received — " + devices.size + " device(s) on the wall.",
                        "info"
                    );
                }
                syncTiles();
                renderWall();
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
                const known = devices.delete(id);
                const hadPlacement = dropPlacement(id);
                if (!known && !hadPlacement) return;
                syncTiles();
                break;
            }

            case "wall_updated": {
                const next = normalizeWall(msg.wall);
                if (!next) return;
                // Revisions are monotonic; anything not newer than what we
                // hold is a replay and must not rewind the diagram.
                if (wall && next.revision <= wall.revision) return;
                wall = next;
                if (!wallDirty) pendingMode = wall.mode;
                renderWall();
                logStatus(
                    "Wall updated — revision " + wall.revision + " · " + wall.mode + ".",
                    "info"
                );
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
        // Presence flips recolour the diagram, so redraw it with the tiles.
        renderWallMap();
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
            foot: node.querySelector(".tile-foot"),
            // Placement editor (v2).
            placeState: node.querySelector(".place-state"),
            placeReadout: node.querySelector(".place-readout"),
            placeVp: node.querySelector(".ro-vp"),
            placeVis: node.querySelector(".ro-vis"),
            placeFlag: node.querySelector(".ro-flag"),
            placeFlagText: node.querySelector(".ro-flag-text"),
            placeClear: node.querySelector('[data-action="place-clear"]'),
            placeInputs: {},
            placeDirty: false,
            flashTimer: null
        };

        tile.devId.textContent = shortId(id);
        tile.devId.title = id;

        for (const field of PLACE_FIELDS) {
            tile.placeInputs[field] = node.querySelector('[data-field="' + field + '"]');
        }

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

        renderPlacement(tile, device);
    }

    function removeTile(id) {
        const tile = tiles.get(id);
        if (!tile) return;
        if (confirmingId === id) {
            if (confirmTimer) clearTimeout(confirmTimer);
            confirmTimer = null;
            confirmingId = null;
        }
        if (tile.flashTimer) {
            clearTimeout(tile.flashTimer);
            tile.flashTimer = null;
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
     * Wall panel — size, mode, revision, arrange
     * ------------------------------------------------------------------ */

    function renderWall() {
        el.wallRev.textContent = wall ? String(wall.revision) : "—";

        if (wallReady()) {
            el.wallNote.hidden = true;
        } else {
            el.wallNote.hidden = false;
            el.wallNote.textContent = wall
                ? "wall width/height not set"
                : "no wall state from the server";
        }

        // Never stomp on an edit in progress; otherwise follow the server.
        if (wall && !wallDirty) {
            if (document.activeElement !== el.wallWidth) {
                el.wallWidth.value = String(wall.width);
            }
            if (document.activeElement !== el.wallHeight) {
                el.wallHeight.value = String(wall.height);
            }
            pendingMode = wall.mode;
            renderWallMode(pendingMode);
        }

        setWallControlsEnabled(wallReady());
        renderWallMap();

        for (const tile of tiles.values()) {
            const device = devices.get(tile.el.dataset.id);
            if (device) renderPlacement(tile, device);
        }
    }

    function renderWallMode(mode) {
        for (const button of el.wallMode.querySelectorAll(".seg-opt")) {
            button.setAttribute("aria-pressed", String(button.dataset.mode === mode));
        }
    }

    function setWallControlsEnabled(on) {
        el.wallWidth.disabled = !on;
        el.wallHeight.disabled = !on;
        el.btnWallSave.disabled = !on;
        el.autoColumns.disabled = !on;
        el.btnAuto.disabled = !on;
        for (const button of el.wallMode.querySelectorAll(".seg-opt")) {
            button.disabled = !on;
        }
    }

    /* ------------------------------------------------------------------ *
     * Wall preview map
     *
     * A scaled technical diagram: the wall rectangle, every placement at
     * its footprint, the bezel hatched, the visible rect drawn inside it,
     * labelled with the device's short id. Click a footprint to jump to
     * that device's tile. Positions are percentages, so the geometry is
     * exact at any size; only the frame is measured in pixels.
     * ------------------------------------------------------------------ */

    function renderWallMap() {
        const frame = el.mapFrame;
        frame.textContent = "";

        if (!wallReady()) {
            frame.hidden = true;
            el.mapCaption.textContent = "";
            el.mapEmpty.hidden = false;
            el.mapEmpty.textContent = wall
                ? "Wall width and height are not set — the diagram needs both."
                : "Waiting for the wall state from the server.";
            return;
        }
        el.mapEmpty.hidden = true;
        frame.hidden = false;

        const wallW = wall.width;
        const wallH = wall.height;
        const measured = el.mapViewport.clientWidth;
        const avail = measured > 80 ? measured : 640;

        let pxW = avail;
        let pxH = pxW * wallH / wallW;
        if (pxH > MAP_MAX_H) {
            pxH = MAP_MAX_H;
            pxW = pxH * wallW / wallH;
        }
        if (pxH < MAP_MIN_H) {
            pxH = MAP_MIN_H;
            pxW = pxH * wallW / wallH;
        }
        frame.style.width = Math.round(pxW) + "px";
        frame.style.height = Math.round(pxH) + "px";

        let placed = 0;
        let orphans = 0;
        let warns = 0;

        for (const id of Object.keys(wall.placements)) {
            const device = devices.get(id);
            if (device) {
                placed += 1;
            } else {
                orphans += 1; // placement left behind by a removed device
            }
            const box = buildMapPlacement(
                id, wall.placements[id], device, wallW, wallH, pxW, pxH
            );
            if (box.dataset.aspect === "mismatch") warns += 1;
            frame.appendChild(box);
        }

        if (placed === 0 && orphans === 0) {
            const note = document.createElement("p");
            note.className = "map-none";
            note.textContent = "no placements yet";
            frame.appendChild(note);
        }

        const unplaced = Math.max(0, devices.size - placed);
        const bits = [wallW + " × " + wallH + " u", placed + " placed"];
        if (unplaced > 0) bits.push(unplaced + " unplaced");
        if (orphans > 0) bits.push(orphans + " orphaned");
        if (warns > 0) bits.push(warns + " aspect mismatch");
        el.mapCaption.textContent = bits.join(" · ");
    }

    function buildMapPlacement(id, placement, device, wallW, wallH, pxW, pxH) {
        const visible = visibleRect(placement);
        const visAspect = aspectOf(visible.w, visible.h);
        const devAspect = viewportAspect(device);
        const delta = aspectDelta(visAspect, devAspect);
        const mismatch = isAspectMismatch(delta);

        const box = document.createElement("button");
        box.type = "button";
        box.className = "map-pl";
        box.style.left = pct(placement.x, wallW);
        box.style.top = pct(placement.y, wallH);
        box.style.width = pct(placement.w, wallW);
        box.style.height = pct(placement.h, wallH);
        box.dataset.state = !device
            ? "missing"
            : device.online === true ? "online" : "offline";
        box.dataset.aspect = mismatch ? "mismatch" : "match";

        const pxBoxW = (placement.w / wallW) * pxW;
        const pxBoxH = (placement.h / wallH) * pxH;

        const summary =
            "device " + shortId(id) +
            " · footprint " + placement.x + "," + placement.y +
            " " + placement.w + "×" + placement.h +
            (device ? "" : " · no longer in the roster") +
            (mismatch
                ? " · aspect mismatch: visible " + fmtAspect(visAspect) +
                  " vs viewport " + fmtAspect(devAspect) +
                  " (Δ " + fmtDelta(delta) + ")"
                : "");
        box.title = summary;
        box.setAttribute("aria-label", summary);

        if (device) {
            box.addEventListener("click", function () {
                focusTile(id);
            });
        }

        // Visible rect: the footprint inset by the bezel on each edge.
        const inset = document.createElement("span");
        inset.className = "map-vis";
        inset.style.top = pct(placement.bezel.top, placement.h);
        inset.style.right = pct(placement.bezel.right, placement.w);
        inset.style.bottom = pct(placement.bezel.bottom, placement.h);
        inset.style.left = pct(placement.bezel.left, placement.w);

        const room = Math.min(pxBoxW, pxBoxH);
        if (room >= 16) {
            const label = document.createElement("span");
            label.className = "map-label";
            label.textContent = shortId(id);
            inset.style.setProperty(
                "--label-fs",
                Math.max(6, Math.min(11, Math.round(room / 6))) + "px"
            );
            inset.appendChild(label);

            if (mismatch && pxBoxW >= 76 && pxBoxH >= 34) {
                const ratios = document.createElement("span");
                ratios.className = "map-ar";
                ratios.textContent = fmtAspect(visAspect) + " ≠ " + fmtAspect(devAspect);
                inset.appendChild(ratios);
            }
        }

        box.appendChild(inset);
        return box;
    }

    /**
     * Map click → scroll the matching tile into view and outline it for a
     * moment. scrollIntoView is safe everywhere; only the smooth behaviour
     * is negotiable with reduced-motion.
     */
    function focusTile(deviceId) {
        const tile = tiles.get(deviceId);
        if (!tile) {
            logStatus(
                "Device #" + shortId(deviceId) + " has no tile — it is not in the roster.",
                "err"
            );
            return;
        }
        if (typeof tile.el.scrollIntoView === "function") {
            const reduced =
                typeof window.matchMedia === "function" &&
                window.matchMedia("(prefers-reduced-motion: reduce)").matches;
            tile.el.scrollIntoView({
                block: "center",
                behavior: reduced ? "auto" : "smooth"
            });
        }
        tile.el.dataset.flash = "true";
        if (tile.flashTimer) clearTimeout(tile.flashTimer);
        tile.flashTimer = setTimeout(function () {
            tile.flashTimer = null;
            if (tiles.get(deviceId) === tile) tile.el.dataset.flash = "false";
        }, FOCUS_FLASH_MS);
    }

    /* ------------------------------------------------------------------ *
     * Per-device placement editing
     * ------------------------------------------------------------------ */

    function renderPlacement(tile, device) {
        // Guards the whole editor: a cached page shell without the v2
        // markup simply leaves the section inert instead of throwing.
        if (!tile.placeState || !tile.placeVp || !tile.placeInputs.x) return;

        const saved = savedPlacement(device.device_id);
        if (!tile.placeDirty) syncPlacementInputs(tile, saved);

        // "Unplaced" is a state, not a fault — dashed and quiet, never red.
        tile.placeState.textContent = saved ? "PLACED" : "UNPLACED";
        tile.placeState.dataset.state = saved ? "placed" : "unplaced";
        tile.placeState.title = saved
            ? "Footprint at " + saved.x + "," + saved.y + " · " +
              saved.w + "×" + saved.h + " wall units"
            : "No placement yet — this tablet draws its id and a note.";
        if (tile.placeClear) tile.placeClear.disabled = !saved;

        updatePlacementReadout(tile, device);
    }

    /** Push saved geometry (or sensible wall-sized defaults) into the
     *  inputs. Never while the operator is mid-edit. */
    function syncPlacementInputs(tile, saved) {
        const values = saved || (wallReady()
            ? {
                x: 0,
                y: 0,
                w: wall.width,
                h: wall.height,
                bezel: { top: 0, right: 0, bottom: 0, left: 0 }
            }
            : null);
        if (!values) return;

        setPlaceField(tile, "x", values.x);
        setPlaceField(tile, "y", values.y);
        setPlaceField(tile, "w", values.w);
        setPlaceField(tile, "h", values.h);
        setPlaceField(tile, "bezel-top", values.bezel.top);
        setPlaceField(tile, "bezel-right", values.bezel.right);
        setPlaceField(tile, "bezel-bottom", values.bezel.bottom);
        setPlaceField(tile, "bezel-left", values.bezel.left);
    }

    function setPlaceField(tile, field, value) {
        const input = tile.placeInputs[field];
        if (!input) return;
        const next = String(value);
        if (input.value !== next) input.value = next;
    }

    /** Current form values as a placement, or null if any field is blank
     *  or not a number (mid-edit states are not errors, just incomplete). */
    function readPlacementInputs(tile) {
        const values = {};
        for (const field of PLACE_FIELDS) {
            const input = tile.placeInputs[field];
            if (!input) return null;
            const text = String(input.value).trim();
            if (text === "") return null;
            const n = Number(text);
            if (!Number.isFinite(n)) return null;
            values[field] = n;
        }
        return {
            x: values.x,
            y: values.y,
            w: values.w,
            h: values.h,
            bezel: {
                top: values["bezel-top"],
                right: values["bezel-right"],
                bottom: values["bezel-bottom"],
                left: values["bezel-left"]
            }
        };
    }

    /** Why the server would answer 422, checked before we send it.
     *
     * PROTOCOL.md specifies exactly two invalid cases — a degenerate rect
     * and a bezel that leaves no visible area — so those are the only two
     * this refuses. Anything else is the server's call. */
    function placementProblem(placement) {
        if (!(placement.w > 0) || !(placement.h > 0)) {
            return "the footprint must be bigger than zero";
        }
        const visible = visibleRect(placement);
        if (!(visible.w > 0) || !(visible.h > 0)) {
            return "the bezel leaves no visible area";
        }
        return null;
    }

    /**
     * Viewport versus visible rect, live as the operator types.
     *
     * A placement renders cleanly when its visible rect shares the device's
     * reported aspect ratio. A mismatch is surfaced, never hidden — it is
     * the geometry foot-gun of the whole feature — but a device with no
     * placement reads as neutral, not as a fault.
     */
    function updatePlacementReadout(tile, device) {
        if (!tile.placeVp || !tile.placeVis) return;

        const devW = Number(device.width);
        const devH = Number(device.height);
        const hasViewport =
            device.width != null && device.height != null &&
            Number.isFinite(devW) && Number.isFinite(devH) &&
            devW > 0 && devH > 0;
        const devAspect = hasViewport ? devW / devH : null;
        tile.placeVp.textContent = hasViewport
            ? "viewport " + devW + " × " + devH + " · ar " + fmtAspect(devAspect)
            : "viewport not reported";

        const evaluating = tile.placeDirty || !!savedPlacement(device.device_id);
        if (!evaluating) {
            setReadout(tile, "none", "visible — · not placed", false, "");
            return;
        }

        const placement = readPlacementInputs(tile);
        if (!placement) {
            setReadout(tile, "edit", "visible — · fill in every field", false, "");
            return;
        }

        const problem = placementProblem(placement);
        if (problem) {
            setReadout(tile, "invalid", "visible — · invalid", true, problem);
            return;
        }

        const visible = visibleRect(placement);
        const visAspect = aspectOf(visible.w, visible.h);
        const delta = aspectDelta(visAspect, devAspect);
        const row =
            "visible " + visible.w + " × " + visible.h +
            " · ar " + fmtAspect(visAspect) +
            " vs " + fmtAspect(devAspect) +
            " · Δ " + fmtDelta(delta);

        if (devAspect === null) {
            setReadout(
                tile, "unknown", row, true,
                "no viewport reported — aspect cannot be compared", "dim"
            );
        } else if (isAspectMismatch(delta)) {
            setReadout(
                tile, "mismatch", row, true,
                "aspect mismatch — this slice crops differently from the rest"
            );
        } else {
            setReadout(tile, "ok", row, false, "");
        }
    }

    function setReadout(tile, state, row, showFlag, flagText, flagKind) {
        tile.placeReadout.dataset.state = state;
        tile.placeVis.textContent = row;
        tile.placeFlag.hidden = !showFlag;
        tile.placeFlag.dataset.kind = flagKind || "warn";
        if (showFlag) tile.placeFlagText.textContent = flagText;
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
        dropPlacement(deviceId);
        removeTile(deviceId);
        renderTally();
        renderEmpty();
        renderWallMap(); // the diagram may still be showing its placement
    }

    /* ------------------------------------------------------------------ *
     * Wall + placement commands
     * ------------------------------------------------------------------ */

    async function saveWall() {
        const width = Number(el.wallWidth.value);
        const height = Number(el.wallHeight.value);
        if (!Number.isInteger(width) || width < 1 || !Number.isInteger(height) || height < 1) {
            logStatus("Wall width and height must be positive whole numbers.", "err");
            return;
        }
        const mode = pendingMode || (wall ? wall.mode : "color");

        el.btnWallSave.disabled = true;
        try {
            const data = await requestJson("PUT", "/wall", {
                width: width,
                height: height,
                mode: mode
            });
            const next = normalizeWall(data);
            if (next && next.width > 0 && next.height > 0) {
                wall = next;
            } else {
                // Something other than a wall state came back; keep the
                // operator's values and let `wall_updated` reconcile.
                wall = {
                    width: width,
                    height: height,
                    mode: mode,
                    revision: wall ? wall.revision : 0,
                    placements: wall ? wall.placements : {}
                };
            }
            wallDirty = false;
            pendingMode = wall.mode;
            renderWall();
            logStatus(
                "Wall saved — revision " + wall.revision + " · " +
                    wall.width + "×" + wall.height + " " + wall.mode + ".",
                "ok"
            );
        } catch (err) {
            logStatus("Wall not saved: " + err.message, "err");
        } finally {
            renderWall();
        }
    }

    async function arrangeWall() {
        const body = {};
        const raw = String(el.autoColumns.value).trim();
        if (raw !== "") {
            const columns = Number(raw);
            if (!Number.isInteger(columns) || columns < 1) {
                logStatus("Columns must be a positive whole number — or blank for auto.", "err");
                return;
            }
            body.columns = columns;
        }

        el.btnAuto.disabled = true;
        try {
            const data = await requestJson("POST", "/wall/auto", body);
            const next = normalizeWall(data);
            if (next && next.width > 0 && next.height > 0) {
                wall = next;
                renderWall();
                logStatus("Arranged online devices — revision " + next.revision + ".", "ok");
            } else {
                logStatus("Arrange sent — waiting for the wall update.", "info");
            }
        } catch (err) {
            logStatus("Arrange failed: " + err.message, "err");
        } finally {
            renderWall();
        }
    }

    async function savePlacement(deviceId) {
        const tile = tiles.get(deviceId);
        if (!tile) return;
        const device = devices.get(deviceId);
        if (!device) return;

        const placement = readPlacementInputs(tile);
        if (!placement) {
            logStatus(
                "Placement for #" + shortId(deviceId) + " needs a number in every field.",
                "err"
            );
            updatePlacementReadout(tile, device);
            return;
        }
        const problem = placementProblem(placement);
        if (problem) {
            logStatus(
                "Placement for #" + shortId(deviceId) + " rejected: " + problem + ".",
                "err"
            );
            updatePlacementReadout(tile, device);
            return;
        }

        tile.el.dataset.busy = "true";
        try {
            await requestJson(
                "PUT",
                "/devices/" + encodeURIComponent(deviceId) + "/placement",
                placement
            );
            // PROTOCOL.md only promises a 200 for this call, so mirror what
            // we sent; the authoritative revision arrives with `wall_updated`.
            if (wall) {
                const placements = Object.assign({}, wall.placements);
                placements[deviceId] = placement;
                wall.placements = placements;
            }
            tile.placeDirty = false;
            renderWall();
            logStatus("Placement saved for #" + shortId(deviceId) + ".", "ok");
        } catch (err) {
            if (err.status === 404) {
                // Unknown device: the roster lost it while we were editing.
                dropDevice(deviceId);
                logStatus("Device #" + shortId(deviceId) + " was already gone.", "info");
            } else {
                logStatus(
                    "Placement not saved for #" + shortId(deviceId) + ": " + err.message,
                    "err"
                );
            }
        } finally {
            if (tiles.get(deviceId) === tile) tile.el.dataset.busy = "false";
        }
    }

    async function clearPlacement(deviceId) {
        const tile = tiles.get(deviceId);
        if (!tile) return;

        tile.el.dataset.busy = "true";
        try {
            await requestJson(
                "DELETE",
                "/devices/" + encodeURIComponent(deviceId) + "/placement"
            );
            if (wall) {
                const placements = Object.assign({}, wall.placements);
                delete placements[deviceId];
                wall.placements = placements;
            }
            tile.placeDirty = false;
            renderWall();
            logStatus("Placement cleared for #" + shortId(deviceId) + ".", "ok");
        } catch (err) {
            if (err.status === 404) {
                dropDevice(deviceId);
                logStatus("Device #" + shortId(deviceId) + " was already gone.", "info");
            } else {
                logStatus(
                    "Could not clear the placement of #" + shortId(deviceId) + ": " + err.message,
                    "err"
                );
            }
        } finally {
            if (tiles.get(deviceId) === tile) tile.el.dataset.busy = "false";
        }
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

        /* Wall panel: form commits on submit, everything else just marks
         * the form dirty so incoming updates stop touching the inputs. */
        el.wallForm.addEventListener("submit", function (event) {
            event.preventDefault();
            saveWall();
        });

        const markWallDirty = function () {
            wallDirty = true;
        };
        el.wallWidth.addEventListener("input", markWallDirty);
        el.wallHeight.addEventListener("input", markWallDirty);

        el.wallMode.addEventListener("click", function (event) {
            const button = event.target.closest("button[data-mode]");
            if (!button || button.disabled) return;
            pendingMode = button.dataset.mode;
            wallDirty = true;
            renderWallMode(pendingMode);
        });

        el.btnAuto.addEventListener("click", arrangeWall);

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
                case "place-save":
                    savePlacement(id);
                    break;
                case "place-clear":
                    clearPlacement(id);
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

        // Placement fields: recompute the aspect readout as the operator
        // types. Nothing touches the network until "Save" is pressed.
        el.grid.addEventListener("input", function (event) {
            const input = event.target;
            if (!input.matches || !input.matches("input[data-field]")) return;
            const tileEl = input.closest(".tile");
            if (!tileEl) return;
            const tile = tiles.get(tileEl.dataset.id);
            const device = devices.get(tileEl.dataset.id);
            if (!tile || !device) return;
            tile.placeDirty = true;
            updatePlacementReadout(tile, device);
        });

        /* The diagram measures its container; re-measure on resize. */
        let resizeTimer = null;
        window.addEventListener("resize", function () {
            if (resizeTimer) clearTimeout(resizeTimer);
            resizeTimer = setTimeout(function () {
                resizeTimer = null;
                renderWallMap();
            }, 120);
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
        renderWall(); // wall is null here: disables the panel, notes the wait
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
