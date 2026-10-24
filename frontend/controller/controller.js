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
     *   - Wall state is layout + scene + revision + generation: dimensions
     *     are written with PUT /wall, scene content with PUT /scene.
     *   - Still images (PROTOCOL.md "Still images"): GET /assets reads the
     *     curated inventory — on demand plus one read at boot, never
     *     polled. An image only reaches PUT /scene after the operator has
     *     selected an asset and pressed "Show on wall".
     *   - Managed images (R1): GET /media lists the upload library and
     *     POST /uploads streams one file. Neither adds the image to the
     *     wall by itself; selection and "Show on wall" stay the same.
     *
     * There is NO polling. The only timer is a 1 Hz UI tick that redraws
     * relative timestamps and the reconnect countdown; it never touches
     * the network. Wall and placement edits are driven by the operator
     * plus the `wall_updated` broadcast.
     * ------------------------------------------------------------------ */

    const WS_PATH = "/ws/controller";
    const PROTOCOL = 2;

    /* Client page path appended to the configured bare tablet origin. */
    const CLIENT_PATH = "client/";

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
    const RELEASE_CONFIRM_MS = 8000;
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
    const MAP_MAX_H = 420;
    const DEVICE_TYPE_NAMES = { ipad: "iPad", iphone: "iPhone", android: "Android" };
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
        wallGen: document.getElementById("wall-gen"),
        wallNote: document.getElementById("wall-note"),
        wallForm: document.getElementById("wall-form"),
        wallWidth: document.getElementById("wall-width"),
        wallHeight: document.getElementById("wall-height"),
        wallContent: document.getElementById("wall-content"),
        wallContentState: document.getElementById("wall-content-state"),
        contentNow: document.getElementById("content-now"),
        colourBlock: document.getElementById("colour-block"),
        calibrationBlock: document.getElementById("calibration-block"),
        calibrationState: document.getElementById("calibration-state"),
        imagePanel: document.getElementById("image-panel"),
        rosterCount: document.getElementById("roster-count"),
        btnWallSave: document.getElementById("btn-wall-save"),
        autoColumns: document.getElementById("auto-columns"),
        btnAuto: document.getElementById("btn-auto"),
        mapCaption: document.getElementById("map-caption"),
        mapViewport: document.getElementById("map-viewport"),
        mapFrame: document.getElementById("map-frame"),
        mapEmpty: document.getElementById("map-empty"),
        reservations: document.getElementById("reservations"),
        resList: document.getElementById("res-list"),
        alerts: document.getElementById("alerts"),
        alertNoCap: document.getElementById("alert-nocap"),
        alertNoCapTitle: document.getElementById("alert-nocap-title"),
        alertNoCapText: document.getElementById("alert-nocap-text"),
        alertUnverified: document.getElementById("alert-unverified"),
        alertUnverifiedText: document.getElementById("alert-unverified-text"),
        imageActive: document.getElementById("image-active"),
        imageActiveText: document.getElementById("image-active-text"),
        imageMissing: document.getElementById("image-missing"),
        imageMissingTitle: document.getElementById("image-missing-title"),
        imageMissingText: document.getElementById("image-missing-text"),
        btnMissingPick: document.getElementById("btn-missing-pick"),
        btnAssetsRefresh: document.getElementById("btn-assets-refresh"),
        imageCount: document.getElementById("image-count"),
        imageSel: document.getElementById("image-sel"),
        imageNote: document.getElementById("image-note"),
        assetList: document.getElementById("asset-list"),
        imageEmpty: document.getElementById("image-empty"),
        btnImageApply: document.getElementById("btn-image-apply"),
        imagePreview: document.getElementById("image-preview"),
        imagePreviewImg: document.getElementById("image-preview-img"),
        imagePreviewNote: document.getElementById("image-preview-note"),
        uploadBlock: document.getElementById("upload-block"),
        uploadFile: document.getElementById("upload-file"),
        btnUpload: document.getElementById("btn-upload"),
        uploadFileName: document.getElementById("upload-file-name"),
        uploadProgress: document.getElementById("upload-progress"),
        uploadStatus: document.getElementById("upload-status"),
        mediaLibrary: document.getElementById("media-library"),
        mediaList: document.getElementById("media-list"),
        mediaCount: document.getElementById("media-count"),
        mediaNote: document.getElementById("media-note"),
        grid: document.getElementById("grid"),
        empty: document.getElementById("empty"),
        emptyConn: document.getElementById("empty-conn"),
        clientUrl: document.getElementById("client-url"),
        btnCopyUrl: document.getElementById("btn-copy-url"),
        statusStamp: document.getElementById("status-stamp"),
        statusText: document.getElementById("status-text"),
        tileTpl: document.getElementById("tile-tpl")
    };

    /** Per-panel nodes for the saved layouts / scenes panels (Phase 2c).
     *  Kept beside `el` because both panels are driven by the same code with
     *  a `kind` argument — two copies of the same wiring, one namespace. */
    const snapEl = {
        layout: {
            form: document.getElementById("layout-save-form"),
            name: document.getElementById("layout-name"),
            save: document.getElementById("btn-layout-save"),
            msg: document.getElementById("layout-msg"),
            overwrite: document.getElementById("layout-overwrite"),
            overwriteText: document.getElementById("layout-overwrite-text"),
            overwriteYes: document.getElementById("btn-layout-overwrite"),
            overwriteNo: document.getElementById("btn-layout-overwrite-cancel"),
            refresh: document.querySelector('[data-snap-refresh="layout"]'),
            list: document.getElementById("layout-list"),
            empty: document.getElementById("layout-empty")
        },
        scene: {
            form: document.getElementById("scene-save-form"),
            name: document.getElementById("scene-name"),
            save: document.getElementById("btn-scene-save"),
            msg: document.getElementById("scene-msg"),
            overwrite: document.getElementById("scene-overwrite"),
            overwriteText: document.getElementById("scene-overwrite-text"),
            overwriteYes: document.getElementById("btn-scene-overwrite"),
            overwriteNo: document.getElementById("btn-scene-overwrite-cancel"),
            refresh: document.querySelector('[data-snap-refresh="scene"]'),
            list: document.getElementById("scene-list"),
            empty: document.getElementById("scene-empty")
        }
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

    /* Vacant-reservation release: the same two-step confirm as Forget,
     * but keyed to a placement id that has no tile to host the buttons. */
    let confirmingReleaseId = null;
    let confirmReleaseTimer = null;

    /** Full wall state (PROTOCOL.md "Wall state"); null until the snapshot
     *  delivers one. Sparse `placements` live inside it. */
    let wall = null;

    /** True while the wall form holds unsaved dimension edits, so an incoming
     *  `wall_updated` cannot overwrite what the operator is typing. */
    let wallDirty = false;

    /** Scene content chosen in the control but not yet confirmed by the
     *  server's PUT /scene response (or its `wall_updated` echo). */
    let pendingContent = null;

    /* Which content panel is open in the operator's control. This is a view
     * state, not the wall: an operator can browse the image library while the
     * wall still shows colour, and the summary keeps the actual wall state
     * separate. */
    let contentView = null;

    /* Curated asset inventory (GET /assets). Read once at boot and again only
     * when the operator asks — never polled. A failed refresh keeps the last
     * good list (`assetsError` says why it is stale); `assetsLoaded` gates
     * every claim this page makes about what is in the inventory, so "missing"
     * is never asserted from a read that never succeeded. */
    let assets = [];
    let assetsLoaded = false;
    let assetsLoading = false;
    let assetsError = null;
    let assetsStamp = null; // clock stamp of the last successful read

    /** Asset picked in the list but not yet sent. null means no selection,
     *  and no image scene is ever sent without one. */
    let selectedAsset = null;

    /* Managed uploads (GET /media) are a separate store from the curated
     * inventory, so they keep their own list. `mediaState` is "pending" |
     * "ready" | "forbidden" | "error": 403 means uploads are disabled, which
     * hides the upload controls and leaves the curated flow as it was. */
    let mediaAssets = [];
    let mediaState = "pending";
    let mediaError = null;
    let mediaLoading = false;

    /* One upload at a time. `uploadStage` is null | "uploading" |
     * "processing"; progress events drive the first, the upload `load`
     * event the second. */
    let uploadXhr = null;
    let uploadBusy = false;
    let uploadStage = null;

    /* Tablet URL (GET /operator-config, read once at boot). `tabletUrl` is
     * the validated address to show and copy, or null while none is known
     * or the answer could not be trusted. */
    let tabletUrl = null;
    let tabletUrlState = "pending"; // "pending" | "ready" | "unavailable"
    let tabletUrlReason = null;     // why it is unavailable; null otherwise

    /* ------------------------------------------------------------------ *
     * Small helpers
     * ------------------------------------------------------------------ */

    function shortId(id) {
        return String(id).slice(0, 8);
    }

    /** Generation is an opaque lineage token; the first 8 characters are
     *  enough to spot a change on the wall panel. */
    function shortGeneration(generation) {
        if (generation == null || generation === "") return "-";
        return String(generation).slice(0, 8);
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
        if (Number.isNaN(t)) return "-";
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
        return device.online === true ? "Connected now" : relTime(device.last_seen);
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
        return ratio === null ? "-" : ratio.toFixed(3);
    }

    function fmtDelta(delta) {
        return delta === null ? "-" : (delta * 100).toFixed(1) + "%";
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

    /* The content types offered in the segment control. The server answers
     * 422 to anything else, so nothing else is offered there. An image is a
     * different action — an explicit asset selection in the still-image panel
     * below — and is deliberately not a third segment: it cannot be toggled
     * without knowing which asset to send. */
    const SETTABLE_CONTENT = ["color", "calibration"];

    function isSettableContent(type) {
        return typeof type === "string" && SETTABLE_CONTENT.indexOf(type) !== -1;
    }

    /**
     * `scene.content.type` exactly as the server reported it, or null when
     * the payload carries no scene content at all.
     *
     * This must never round an unrecognised value down to `"color"`: the
     * operator sees "color" and would believe the wall is showing colours
     * when a newer server has moved on (PROTOCOL.md reserves `"image"` and
     * may add more). The raw value is what `contentLabel` explains.
     */
    function sceneContentType(raw) {
        const content = raw && raw.scene && raw.scene.content;
        if (!content || typeof content.type !== "string") return null;
        const type = content.type.trim();
        return type === "" ? null : type;
    }

    /**
     * The whole `scene.content` object as the server reported it, or null
     * when the payload carries none.
     *
     * It is kept beside `contentType` because an image scene is more than a
     * type: the asset id, fit and derived intrinsic dimensions are what make
     * a now-missing asset still identifiable (PROTOCOL.md "Still images").
     * The copy is taken as-is — nothing here invents fields the server did
     * not send.
     */
    function sceneContent(raw) {
        const content = raw && raw.scene && raw.scene.content;
        if (!content || typeof content !== "object" || Array.isArray(content)) return null;
        return content;
    }

    /** Short label for the wall-state summary in the content header. */
    function contentSummaryLabel(type) {
        if (type === "color") return "Colour";
        if (type === "calibration") return "Calibration grid";
        if (type === "image") return "Image";
        if (type === null || type === undefined) return "Waiting";
        return "Unsupported type";
    }

    /**
     * Honest, operator-facing name for a scene content type.
     *
     * `"color"` and `"calibration"` read as themselves. `"image"` is named as
     * what it is: it is set from the still-image panel, not from the tabs.
     * Anything else is flagged as unsupported rather than shown as colour.
     */
    function contentLabel(type) {
        if (type === null) return "No content reported";
        if (type === "color") return "Colour (no image)";
        if (type === "calibration") return "Calibration grid (no image)";
        if (type === "image") return "Image";
        return "Unsupported content: " + type;
    }

    /**
     * Amber caption under the segment control — why no segment is pressed.
     * null when there is nothing to explain.
     */
    function contentHint(type) {
        if (type === null || isSettableContent(type)) return null;
        if (type === "image") return null; // the Image block says so itself
        return "The wall shows content this page cannot set (" + type +
            "). Choose solid colour or the calibration grid to replace it.";
    }

    /**
     * Build local wall state from a server payload.
     *
     * The payload shape is the whole wall state — the one `GET /wall`
     * returns and `snapshot` / `wall_updated` / every `PUT` echoes back:
     * layout fields (`width`, `height`, `placements`), `scene`, `revision`
     * and `generation`.
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
            contentType: sceneContentType(raw),
            content: sceneContent(raw),
            generation: typeof raw.generation === "string" ? raw.generation : null,
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
            logStatus("Connected. Waiting for the current state.", "info");
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
            "Lost the connection. Retry " + attempt + " in " + (delay / 1000).toFixed(1) + "s.",
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
        logStatus("Reconnecting…", "info");
        connect();
    }

    function renderConn() {
        el.conn.dataset.state = connState;
        let label;
        if (connState === "open") {
            label = "Live";
        } else if (connState === "connecting") {
            label = "Connecting…";
        } else {
            const secs = retryAt ? Math.max(0, Math.ceil((retryAt - Date.now()) / 1000)) : 0;
            label = attempt > 0 ? "Offline, retrying in " + secs + "s (attempt " + attempt + ")" : "Disconnected";
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
                // revision moved backwards, which is what a server resyncing
                // under a new generation looks like. Clear first so a v1
                // snapshot means "no wall".
                wall = null;
                if (msg.wall) wall = normalizeWall(msg.wall);
                if (awaitingSnapshot) {
                    awaitingSnapshot = false;
                    logStatus(
                        devices.size + (devices.size === 1 ? " tablet" : " tablets") + " known to the server.",
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
                // Its placement is NOT touched here: the server owns it, and a
                // placement outlives the roster as a reservation (PROTOCOL.md
                // "DELETE /devices/{device_id}/placement"). The diagram keeps
                // showing the footprint — now as "vacant · reserved" — until a
                // `wall_updated` says the server really cleared it.
                const id = msg.device_id;
                if (typeof id !== "string") return;
                if (!devices.delete(id)) return;
                syncTiles();
                break;
            }

            case "wall_updated": {
                const next = normalizeWall(msg.wall);
                if (!next) return;
                // Revisions are monotonic only WITHIN a generation, so a
                // frame that is not newer than what we hold is a replay and
                // must not rewind the diagram — unless the generation changed,
                // in which case the server resynchronised (restore, rollback,
                // wiped database) and may legitimately be at a lower revision.
                if (
                    wall &&
                    next.generation === wall.generation &&
                    next.revision <= wall.revision
                ) {
                    return;
                }
                const resynced = !!wall && next.generation !== wall.generation;
                wall = next;
                renderWall();
                if (resynced) {
                    logStatus(
                        "The server restarted or restored a backup. Session " +
                            shortGeneration(wall.generation) + ", revision " +
                            wall.revision + ".",
                        "ok"
                    );
                } else {
                    logStatus(
                        "Wall updated (revision " + wall.revision + "). Showing: " +
                            contentLabel(wall.contentType).toLowerCase() + ".",
                        "info"
                    );
                }
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
        // …and change what the roster can confirm about a placed slot.
        renderCoverage();
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
            capChip: node.querySelector(".meta-cap"),
            capSep: node.querySelector(".meta-cap-sep"),
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
        forget.textContent = "Forget tablet";
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
            ? "Connected. Forgetting it would not stick. Close the tablet first."
            : "Remove this tablet from the roster";
    }

    function updateTile(tile, device) {
        const online = device.online === true;
        tile.el.dataset.state = online ? "online" : "offline";
        tile.badgeLabel.textContent = online ? "Online" : "Offline";

        // Re-applied on every sync so the button tracks presence changes.
        const forget = tile.foot.querySelector('[data-action="forget"]');
        if (forget) applyForgetAvailability(forget, device.device_id);

        const w = Number(device.width);
        const h = Number(device.height);
        tile.res.textContent =
            Number.isFinite(w) && Number.isFinite(h) && device.width != null && device.height != null
                ? w + "×" + h
                : "-";
        tile.type.textContent = typeof device.type === "string" && device.type
            ? (DEVICE_TYPE_NAMES[device.type.toLowerCase()] || device.type) : "-";

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
            tile.curHex.textContent = "Not set";
        }

        tile.seen.textContent = seenLabel(device);
        tile.seen.title = absTime(device.last_seen);

        renderPlacement(tile, device);
        renderCapChip(tile, device);
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
        if (el.rosterCount) {
            el.rosterCount.textContent = devices.size === 0
                ? "None known"
                : devices.size + " known, " + online + " online";
        }
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
            el.emptyConn.textContent = "Connected. Waiting for the first tablet.";
        } else if (connState === "connecting") {
            el.emptyConn.textContent = "Connecting to the server…";
        } else {
            const secs = retryAt ? Math.max(0, Math.ceil((retryAt - Date.now()) / 1000)) : 0;
            el.emptyConn.textContent = "Connection lost. Retrying in " + secs + "s.";
        }
    }

    /* ------------------------------------------------------------------ *
     * Wall panel — size, scene content, revision, generation, arrange
     * ------------------------------------------------------------------ */

    function renderWall() {
        el.wallRev.textContent = wall ? String(wall.revision) : "-";
        if (el.wallGen) {
            el.wallGen.textContent = wall ? shortGeneration(wall.generation) : "-";
        }

        if (wallReady()) {
            el.wallNote.hidden = true;
        } else {
            el.wallNote.hidden = false;
            el.wallNote.textContent = wall
                ? "Set a wall width and height to see the map."
                : "Waiting for the server.";
        }

        // Never stomp on an edit in progress; otherwise follow the server.
        if (wall && !wallDirty) {
            if (document.activeElement !== el.wallWidth) {
                el.wallWidth.value = String(wall.width);
            }
            if (document.activeElement !== el.wallHeight) {
                el.wallHeight.value = String(wall.height);
            }
        }
        // The scene control follows the server too, except while a choice is
        // still in flight (it is sent immediately, not on form submit).
        if (wall && pendingContent === null) {
            renderWallContent(wall.contentType);
        } else if (!wall) {
            renderContentState(null); // nothing reported: claim nothing
        }

        setWallControlsEnabled(wallReady());
        // The snapshot save buttons need the wall state too (there is nothing
        // to snapshot without it); only those two labels are touched here, so
        // a broadcast never rebuilds the snapshot lists under the operator.
        renderSnapshotAvailability();
        renderWallMap();
        renderImagePanel();
        renderCoverage();

        for (const tile of tiles.values()) {
            const device = devices.get(tile.el.dataset.id);
            if (device) {
                renderPlacement(tile, device);
                renderCapChip(tile, device);
            }
        }
    }

    /**
     * Press the segment matching the server's content — and nothing when the
     * content is outside what this control offers (an image is owned by the
     * still-image panel, an unknown type by nobody here), so the control
     * never claims a type it does not have. The state line below it says what
     * the server actually reported in that case.
     */
    function renderWallContent(type) {
        if (contentView === null && (type === "image" || isSettableContent(type))) {
            contentView = type;
        }
        const view = contentView || "color";
        if (el.wallContent) {
            for (const button of el.wallContent.querySelectorAll(".seg-opt")) {
                button.setAttribute(
                    "aria-pressed",
                    String(button.dataset.content === view)
                );
            }
        }
        if (el.colourBlock) el.colourBlock.hidden = view !== "color";
        if (el.imagePanel) el.imagePanel.hidden = view !== "image";
        if (el.calibrationBlock) el.calibrationBlock.hidden = view !== "calibration";
        if (el.calibrationState) {
            el.calibrationState.textContent = type === "calibration"
                ? "Calibration grid is on the wall. Choose Colour or Image to replace it."
                : "Choose Calibration to show the shared grid.";
        }
        if (el.contentNow) el.contentNow.textContent = contentSummaryLabel(type);
        renderContentState(type);
    }

    /** Amber caption under the scene control; silent when there is nothing
     *  to explain (a type the control offers, or no scene reported at all). */
    function renderContentState(type) {
        const node = el.wallContentState;
        if (!node) return;
        let hint = contentHint(type);
        if (hint === null && contentView !== null && type !== null && contentView !== type) {
            hint = "Editing " + contentSummaryLabel(contentView).toLowerCase() +
                ". The wall still shows " + contentSummaryLabel(type).toLowerCase() + ".";
        }
        if (hint === null) {
            node.hidden = true;
            node.textContent = "";
            return;
        }
        node.hidden = false;
        node.textContent = hint;
    }

    function setWallControlsEnabled(on) {
        el.wallWidth.disabled = !on;
        el.wallHeight.disabled = !on;
        el.btnWallSave.disabled = !on;
        el.autoColumns.disabled = !on;
        el.btnAuto.disabled = !on;
        if (!el.wallContent) return;
        for (const button of el.wallContent.querySelectorAll(".seg-opt")) {
            button.disabled = !on;
        }
    }

    /* ------------------------------------------------------------------ *
     * Still image — curated inventory, the image scene, coverage
     *
     * GET /assets is read once at boot and again only when the operator
     * asks; there is no polling, same as everywhere else in this file. An
     * image reaches PUT /scene only through an explicit selection plus
     * "Show on wall", so a page that has merely *seen* an inventory can
     * never put a wall on an asset nobody picked.
     *
     * The coverage alerts read the roster and the stored placements as they
     * stand: a placed, online tablet that never advertised `image` cannot
     * cover the picture (PROTOCOL.md: it falls back to colour), and a placed
     * tablet that is offline — or absent from the roster — is a slot whose
     * capability nobody can confirm until it connects again.
     * ------------------------------------------------------------------ */

    /** The asset id in the active scene, or null when the scene is not an
     *  image. An image reported *without* an id is null too: this page does
     *  not invent one. */
    function activeImageId() {
        if (!wall || wall.contentType !== "image" || !wall.content) return null;
        const asset = wall.content.asset;
        return typeof asset === "string" && asset !== "" ? asset : null;
    }

    function assetById(id) {
        if (typeof id !== "string" || id === "") return null;
        for (const asset of assets) {
            if (asset.id === id) return asset;
        }
        for (const asset of mediaAssets) {
            if (asset.id === id) return asset;
        }
        return null;
    }

    /**
     * Whether the active image is provably absent from the inventory.
     *
     * This needs a successful read to mean anything: an inventory that was
     * never loaded is "unknown", never "missing", so a server without the
     * route cannot make this page claim the wall is broken.
     */
    function activeAssetMissing() {
        const id = activeImageId();
        // A failed refresh leaves a stale list for browsing, not evidence
        // that a currently active asset is missing from the server now.
        if (!id || !assetsLoaded || assetsError) return false;
        if (assetById(id) !== null) return false;
        // With uploads disabled there is no managed list to consult, so the
        // curated inventory is the only evidence this page can use.
        if (mediaState === "forbidden") return true;
        return mediaState === "ready" && !mediaError;
    }

    /** Asset ids are `sha256:<64 hex>` — the prefix is constant, so the
     *  readable part is the digest's first 8 hex digits. */
    function shortAsset(id) {
        const value = String(id);
        const body = value.indexOf("sha256:") === 0 ? value.slice(7) : value;
        return body.slice(0, 8);
    }

    function fmtBytes(n) {
        if (n === null || !Number.isFinite(n) || n < 0) return "-";
        if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + " MiB";
        if (n >= 1024) return (n / 1024).toFixed(1) + " KiB";
        return n + " B";
    }

    /* ------------------------------------------------------------------ *
     * Inventory parsing
     *
     * PROTOCOL.md fixes which fields `GET /assets` lists (id, display name,
     * MIME type, intrinsic dimensions, byte size, same-origin URL) but not
     * the container or the casing, so the reader takes a bare array, an
     * object holding one, or a map keyed by id, and looks each field up
     * under its camelCase and snake_case spellings. An entry with no
     * identifiable id is skipped rather than rendered as a blank row.
     * ------------------------------------------------------------------ */

    function pickString(raw, keys) {
        for (const key of keys) {
            const value = raw[key];
            if (typeof value === "string" && value !== "") return value;
        }
        return null;
    }

    function pickNumber(raw, keys) {
        for (const key of keys) {
            const value = raw[key];
            if (value === null || value === undefined || value === "") continue;
            const n = Number(value);
            if (Number.isFinite(n)) return n;
        }
        return null;
    }

    const ASSET_ID_KEYS = ["id", "asset", "asset_id", "assetId"];

    function normalizeAsset(raw, fallbackId) {
        if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
        let id = pickString(raw, ASSET_ID_KEYS);
        if (!id && typeof fallbackId === "string" && fallbackId !== "") id = fallbackId;
        if (!id) return null;
        // A bare 64-hex digest is the same identity as its prefixed form.
        if (/^[0-9a-fA-F]{64}$/.test(id)) id = "sha256:" + id.toLowerCase();

        const width = pickNumber(raw, ["width", "intrinsicWidth", "intrinsic_width"]);
        const height = pickNumber(raw, ["height", "intrinsicHeight", "intrinsic_height"]);
        const bytes = pickNumber(raw, ["bytes", "byteSize", "byte_size", "size"]);
        const thumbRaw = raw.thumbnail;
        const thumbnail = thumbRaw && typeof thumbRaw === "object" && !Array.isArray(thumbRaw)
            ? pickString(thumbRaw, ["url", "href"])
            : null;

        return {
            id: id,
            name: pickString(raw, ["name", "display_name", "displayName",
                "filename", "file_name"]) || id,
            mime: pickString(raw, ["mime", "mimeType", "mime_type",
                "content_type", "contentType"]) || "",
            width: width !== null && width > 0 ? Math.round(width) : null,
            height: height !== null && height > 0 ? Math.round(height) : null,
            bytes: bytes !== null && bytes >= 0 ? bytes : null,
            url: pickString(raw, ["url", "href"]),
            thumbnail: thumbnail
        };
    }

    /** The inventory as a sorted array, or null when the payload is not one
     *  in any shape this page recognises (the caller reports that honestly
     *  instead of showing an empty list that looks like "no files"). */
    function normalizeAssets(payload) {
        let entries = null; // [raw, fallbackId] pairs
        if (Array.isArray(payload)) {
            entries = payload.map(function (raw) { return [raw, null]; });
        } else if (payload && typeof payload === "object") {
            let container = null;
            for (const key of ["assets", "items", "files"]) {
                if (Array.isArray(payload[key])) {
                    container = payload[key];
                    break;
                }
            }
            if (container) {
                entries = container.map(function (raw) { return [raw, null]; });
            } else {
                const keys = Object.keys(payload);
                const allObjects = keys.length > 0 && keys.every(function (key) {
                    const value = payload[key];
                    return value && typeof value === "object" && !Array.isArray(value);
                });
                if (allObjects) {
                    entries = keys.map(function (key) { return [payload[key], key]; });
                }
            }
        }
        if (!entries) return null;

        const seen = new Set();
        const out = [];
        for (const entry of entries) {
            const asset = normalizeAsset(entry[0], entry[1]);
            if (!asset || seen.has(asset.id)) continue;
            seen.add(asset.id);
            out.push(asset);
        }
        out.sort(function (a, b) {
            const an = a.name.toLowerCase();
            const bn = b.name.toLowerCase();
            if (an !== bn) return an < bn ? -1 : 1;
            return compareIds(a.id, b.id);
        });
        return out;
    }

    /**
     * GET /assets — one read at boot (quietly) and on demand afterwards.
     * A failed refresh keeps the last good list and says why it is stale;
     * the selection is dropped only if the asset it named is really gone.
     */
    async function refreshAssets(quiet) {
        if (assetsLoading) return;
        assetsLoading = true;
        assetsError = null;
        if (el.btnAssetsRefresh) {
            el.btnAssetsRefresh.disabled = true;
            el.btnAssetsRefresh.textContent = "Loading…";
        }
        renderAssetList();

        try {
            const data = await requestJson("GET", "/assets");
            const list = normalizeAssets(data);
            if (list === null) {
                throw new Error("the answer was not an asset inventory");
            }
            assets = list;
            assetsLoaded = true;
            assetsStamp = clockStamp();

            // A refresh can retire the selection: say so once, alongside the
            // inventory result, rather than burying it under the next line.
            let cleared = false;
            if (selectedAsset && !assetById(selectedAsset)) {
                selectedAsset = null;
                cleared = true;
            }
            if (!quiet) {
                logStatus(
                    "Asset inventory: " + assets.length + " file(s), read " +
                        assetsStamp + (cleared
                            ? " · the selected asset is no longer in it, selection cleared"
                            : ""),
                    "ok"
                );
            } else if (cleared) {
                logStatus(
                    "The selected image is no longer in the list, so the selection was cleared.",
                    "info"
                );
            }
        } catch (err) {
            assetsError = err.message;
            logStatus(
                quiet
                    ? "No asset inventory from this server (" + err.message +
                        "). Press Refresh inventory if still images are enabled."
                    : "Asset inventory unavailable: " + err.message,
                quiet ? "info" : "err"
            );
        } finally {
            assetsLoading = false;
            if (el.btnAssetsRefresh) {
                el.btnAssetsRefresh.disabled = false;
                el.btnAssetsRefresh.textContent = "Refresh list";
            }
            renderImagePanel();
        }
    }

    /* ------------------------------------------------------------------ *
     * Managed library (GET /media) and uploads (POST /uploads)
     *
     * Uploads land in the same descriptor shape as the curated inventory,
     * so selection, preview and "Show on wall" are shared. The library is
     * kept apart only so the curated list keeps its own read and wording.
     * ------------------------------------------------------------------ */

    async function refreshMedia(quiet) {
        if (mediaLoading) return false;
        mediaLoading = true;
        mediaError = null;

        let ok = false;
        try {
            const data = await requestJson("GET", "/media");
            const list = normalizeAssets(data);
            if (list === null) {
                throw new Error("the answer was not an image library");
            }
            mediaAssets = list;
            mediaState = "ready";
            ok = true;
            if (selectedAsset && assetById(selectedAsset) === null) {
                selectedAsset = null;
            }
            if (!quiet) {
                logStatus(
                    "Uploaded library: " + list.length +
                        (list.length === 1 ? " image." : " images."),
                    "ok"
                );
            }
        } catch (err) {
            if (err.status === 403) {
                mediaState = "forbidden";
                if (!quiet) logStatus("Uploads are disabled on this server.", "info");
            } else {
                mediaState = "error";
                mediaError = err.message;
                if (!quiet) logStatus("Uploaded library unavailable: " + err.message, "err");
            }
        } finally {
            mediaLoading = false;
            renderImagePanel();
        }
        return ok;
    }

    function renderMediaPanel() {
        renderUploadControls();
        renderMediaLibrary();
    }

    function renderMediaLibrary() {
        const wrap = el.mediaLibrary;
        const list = el.mediaList;
        if (!wrap || !list) return;

        wrap.hidden = mediaState === "forbidden";
        if (mediaState === "forbidden") return;

        if (el.mediaCount) {
            el.mediaCount.textContent = mediaState === "pending"
                ? ""
                : mediaAssets.length + (mediaAssets.length === 1 ? " image" : " images");
        }

        list.textContent = "";
        for (const asset of mediaAssets) {
            list.appendChild(buildMediaRow(asset));
        }
        list.hidden = mediaAssets.length === 0;

        let note = "";
        let kind = "info";
        if (mediaState === "pending") {
            note = "Reading the uploaded library…";
        } else if (mediaState === "error") {
            kind = "err";
            note = "Uploaded library unavailable: " + (mediaError || "unknown error") +
                (mediaAssets.length > 0 ? ". Showing the images read earlier." : "");
        } else if (mediaAssets.length === 0) {
            note = "No uploaded images yet.";
        }
        if (el.mediaNote) {
            el.mediaNote.hidden = note === "";
            el.mediaNote.dataset.kind = kind;
            el.mediaNote.textContent = note;
        }
    }

    function buildMediaRow(asset) {
        const item = document.createElement("li");
        item.className = "media-item";

        const row = document.createElement("button");
        row.type = "button";
        row.className = "media-row";
        row.dataset.media = asset.id;
        row.setAttribute("aria-pressed", String(selectedAsset === asset.id));
        row.title = asset.id + (asset.mime ? " · " + asset.mime : "");

        let thumb;
        if (asset.thumbnail) {
            thumb = document.createElement("img");
            thumb.className = "media-thumb";
            thumb.src = asset.thumbnail;
            thumb.alt = "";
            thumb.loading = "lazy";
        } else {
            thumb = document.createElement("span");
            thumb.className = "media-thumb media-thumb-none";
            thumb.setAttribute("aria-hidden", "true");
        }

        const name = document.createElement("span");
        name.className = "media-name";
        name.textContent = asset.name;

        const size = document.createElement("span");
        size.className = "media-size";
        size.textContent = fmtBytes(asset.bytes);

        row.append(thumb, name, size);
        item.appendChild(row);
        return item;
    }

    function renderUploadControls() {
        if (!el.uploadBlock) return;
        el.uploadBlock.hidden = mediaState === "forbidden";
        if (!el.uploadFile || !el.btnUpload) return;
        el.uploadFile.disabled = uploadBusy;
        el.btnUpload.disabled = uploadBusy || selectedUploadFile() === null;
        el.btnUpload.textContent = !uploadBusy
            ? "Upload"
            : uploadStage === "processing" ? "Processing…" : "Uploading…";
    }

    function selectedUploadFile() {
        if (!el.uploadFile || !el.uploadFile.files) return null;
        return el.uploadFile.files.length > 0 ? el.uploadFile.files[0] : null;
    }

    function setUploadStatus(text, kind) {
        const node = el.uploadStatus;
        if (!node) return;
        node.dataset.kind = kind || "info";
        node.textContent = text || "";
    }

    function setUploadProgress(percent) {
        const node = el.uploadProgress;
        if (!node) return;
        node.hidden = false;
        if (percent === null) {
            node.removeAttribute("value");
            node.setAttribute("aria-valuetext", "Processing");
            return;
        }
        node.max = 100;
        node.value = percent;
        node.setAttribute("aria-valuetext", percent + "%");
    }

    function hideUploadProgress() {
        const node = el.uploadProgress;
        if (!node) return;
        node.hidden = true;
        node.removeAttribute("aria-valuetext");
        node.value = 0;
    }

    function startUpload() {
        if (uploadBusy) return;
        const file = selectedUploadFile();
        if (!file) {
            setUploadStatus("Choose an image file first.", "err");
            return;
        }

        uploadBusy = true;
        uploadStage = "uploading";
        setUploadStatus("Uploading… 0%", "busy");
        setUploadProgress(0);
        renderUploadControls();

        const xhr = new XMLHttpRequest();
        uploadXhr = xhr;
        xhr.open("POST", "/uploads?name=" + encodeURIComponent(file.name));
        xhr.setRequestHeader("Content-Type", file.type);

        xhr.upload.addEventListener("progress", function (event) {
            if (uploadXhr !== xhr || uploadStage !== "uploading") return;
            if (!event.lengthComputable || !(event.total > 0)) {
                setUploadStatus("Uploading…", "busy");
                return;
            }
            const percent = Math.min(100, Math.max(0,
                Math.round((event.loaded / event.total) * 100)));
            setUploadProgress(percent);
            setUploadStatus("Uploading… " + percent + "%", "busy");
        });

        xhr.upload.addEventListener("load", function () {
            if (uploadXhr !== xhr || uploadStage !== "uploading") return;
            uploadStage = "processing";
            setUploadProgress(null);
            setUploadStatus("Processing…", "busy");
            renderUploadControls();
        });

        xhr.addEventListener("load", function () {
            if (uploadXhr !== xhr) return;
            let asset = null;
            let failure = null;
            if (xhr.status === 201) {
                asset = normalizeAsset(uploadAssetPayload(xhr));
                if (!asset) failure = "the server returned no usable image";
            } else {
                failure = uploadFailureText(xhr);
            }
            finishUpload();
            if (failure !== null) {
                setUploadStatus("Upload failed: " + failure, "err");
                logStatus("Upload failed: " + failure, "err");
                return;
            }
            uploadedAsset(asset);
        });

        xhr.addEventListener("error", function () {
            if (uploadXhr !== xhr) return;
            finishUpload();
            setUploadStatus("Upload failed: the server could not be reached.", "err");
            logStatus("Upload failed: the server could not be reached.", "err");
        });

        xhr.addEventListener("abort", function () {
            if (uploadXhr !== xhr) return;
            finishUpload();
            setUploadStatus("Upload cancelled.", "info");
        });

        xhr.send(file);
    }

    function finishUpload() {
        uploadXhr = null;
        uploadBusy = false;
        uploadStage = null;
        hideUploadProgress();
        renderUploadControls();
    }

    function uploadAssetPayload(xhr) {
        try {
            const data = JSON.parse(xhr.responseText);
            return data && typeof data === "object" ? data.asset : null;
        } catch (_err) {
            return null;
        }
    }

    function uploadFailureText(xhr) {
        let detail = "";
        try {
            const data = JSON.parse(xhr.responseText);
            if (data && typeof data.detail === "string") detail = data.detail;
        } catch (_err) {
            /* non-JSON body: fall through to the status line */
        }
        return detail !== "" ? detail : "HTTP " + xhr.status;
    }

    function uploadedAsset(asset) {
        mediaAssets = mediaAssets.filter(function (item) { return item.id !== asset.id; });
        mediaAssets.push(asset);
        mediaState = "ready";
        mediaError = null;
        selectedAsset = asset.id;
        if (el.uploadFile) el.uploadFile.value = "";
        if (el.uploadFileName) el.uploadFileName.textContent = "No file chosen";
        renderImagePanel();
        setUploadStatus("Ready: " + asset.name, "ok");
        logStatus("Uploaded " + asset.name + ". Press Show on wall to display it.", "ok");
        refreshMedia(true);
    }

    function renderImagePanel() {
        if (!el.imagePanel) return;
        renderActiveImage();
        renderAssetList();
        renderMediaPanel();
        renderMissingAsset();
        updateImageControls();
    }

    /** The active scene image, exactly as the server described it — the id,
     *  its name when the inventory knows it, the persisted intrinsic size and
     *  the fit. Nothing is inferred that the payload did not carry. */
    function renderActiveImage() {
        const node = el.imageActive;
        const text = el.imageActiveText;
        if (!node || !text) return;

        if (!wall) {
            node.dataset.state = "none";
            node.title = "";
            text.textContent = "Waiting for the server";
            return;
        }
        if (wall.contentType !== "image") {
            node.dataset.state = "other";
            node.title = "";
            text.textContent = contentLabel(wall.contentType);
            return;
        }

        const content = wall.content || {};
        const id = typeof content.asset === "string" ? content.asset : "";
        if (!id) {
            node.dataset.state = "missing";
            node.title = "";
            text.textContent = "An image with no file named";
            return;
        }

        const asset = assetById(id);
        const bits = [asset && asset.name ? asset.name : "Image " + shortAsset(id)];

        const rawW = content.intrinsicWidth !== undefined
            ? content.intrinsicWidth : (asset ? asset.width : null);
        const rawH = content.intrinsicHeight !== undefined
            ? content.intrinsicHeight : (asset ? asset.height : null);
        const width = Number(rawW);
        const height = Number(rawH);
        if (Number.isFinite(width) && Number.isFinite(height) && width > 0 && height > 0) {
            bits.push(Math.round(width) + "×" + Math.round(height));
        }
        if (typeof content.fit === "string" && content.fit !== "") {
            bits.push(content.fit === "cover" ? "fills the wall" : "fit " + content.fit);
        }

        const missing = activeAssetMissing();
        if (missing) bits.push("not in the image list");
        else if (assetsError || mediaError) bits.push("image list may be out of date");
        else if (!assetsLoaded || mediaState === "pending") bits.push("image list not loaded yet");

        node.dataset.state = missing ? "missing" : "image";
        node.title = id;
        if (el.contentNow) el.contentNow.textContent = bits[0];
        text.textContent = bits.join(", ");
    }

    function renderAssetList() {
        const list = el.assetList;
        if (!list) return;

        // The note carries loading / stale / error; the count carries the
        // last successful read, so a failed refresh never looks like a
        // fresh one and a stale list never looks current.
        if (el.imageNote) {
            let note = "";
            let kind = "info";
            if (assetsLoading) {
                note = "Reading the asset inventory…";
            } else if (assetsError) {
                kind = "err";
                note = "Inventory unavailable: " + assetsError +
                    (assetsLoaded
                        ? ". Showing the list read at " + assetsStamp + "."
                        : ".");
            }
            el.imageNote.hidden = note === "";
            el.imageNote.dataset.kind = kind;
            el.imageNote.textContent = note;
        }

        if (el.imageCount) {
            el.imageCount.textContent = assetsLoaded
                ? assets.length + (assets.length === 1 ? " asset" : " assets") +
                    (assetsStamp ? " · read " + assetsStamp : "")
                : "";
        }

        const activeId = activeImageId();
        list.textContent = "";
        for (const asset of assets) {
            list.appendChild(buildAssetRow(asset, asset.id === activeId));
        }
        list.hidden = assets.length === 0;

        if (el.imageEmpty) {
            let empty = "";
            if (assets.length === 0) {
                if (assetsLoaded) {
                    empty = "No images found. Put JPEG or PNG files in the " +
                        "server's image folder, then press Refresh list.";
                } else if (!assetsLoading && !assetsError) {
                    empty = "The image list has not loaded yet. Press Refresh list.";
                }
            }
            el.imageEmpty.hidden = empty === "";
            el.imageEmpty.textContent = empty;
        }
    }

    function buildAssetRow(asset, isActive) {
        const item = document.createElement("li");
        item.className = "asset-item";

        const row = document.createElement("button");
        row.type = "button";
        row.className = "asset-row";
        row.dataset.asset = asset.id;
        row.setAttribute("aria-pressed", String(selectedAsset === asset.id));
        row.title = asset.id + (asset.mime ? " · " + asset.mime : "");

        const name = document.createElement("span");
        name.className = "asset-name";
        name.textContent = asset.name;

        const dims = document.createElement("span");
        dims.className = "asset-dims mono";
        dims.textContent =
            asset.width !== null && asset.height !== null
                ? asset.width + "×" + asset.height
                : "-";

        const ar = document.createElement("span");
        ar.className = "asset-ar mono";
        ar.textContent =
            asset.width !== null && asset.height !== null
                ? "ar " + fmtAspect(aspectOf(asset.width, asset.height))
                : "ar -";

        const size = document.createElement("span");
        size.className = "asset-bytes mono";
        size.textContent = fmtBytes(asset.bytes);

        const id = document.createElement("span");
        id.className = "asset-id mono";
        id.textContent = shortAsset(asset.id);
        id.title = asset.id;

        const flag = document.createElement("span");
        flag.className = "asset-flag";
        flag.textContent = "On the wall";
        flag.hidden = !isActive;

        row.append(name, dims, ar, size, id, flag);
        item.appendChild(row);
        return item;
    }

    function selectAsset(id) {
        const asset = assetById(id);
        if (!asset) return;
        if (selectedAsset === asset.id) {
            selectedAsset = null;
            logStatus("Asset selection cleared.", "info");
        } else {
            selectedAsset = asset.id;
            logStatus(
                "Selected " + asset.name + ". Press Show on wall to put it on the wall.",
                "info"
            );
        }
        renderAssetList();
        renderMediaLibrary();
        updateImageControls();
    }

    /**
     * The active asset is in the scene but not in the inventory: the wall is
     * rendering an explicit error state (PROTOCOL.md keeps the id until an
     * operator acts), so this block names it and offers the three ways out —
     * a replacement asset, colour, or calibration.
     */
    function renderMissingAsset() {
        const box = el.imageMissing;
        if (!box) return;
        const id = activeImageId();
        if (!id || !activeAssetMissing()) {
            box.hidden = true;
            return;
        }
        box.hidden = false;
        box.dataset.kind = wall && wall.contentType === "image" ? "bad" : "warn";

        if (el.imageMissingTitle) {
            el.imageMissingTitle.textContent =
                "Active image " + shortAsset(id) + " is not in the inventory";
        }
        if (el.imageMissingText) {
            el.imageMissingText.textContent =
                "The file was removed, replaced, or it failed validation, so the wall " +
                "renders an error instead of the picture. The id stays in the scene " +
                "until you act: pick a replacement below, or put the wall back on " +
                "colour or calibration.";
            el.imageMissingText.title = id;
        }
        if (el.btnMissingPick) {
            const hasAssets = assets.length > 0 ||
                (mediaState === "ready" && mediaAssets.length > 0);
            el.btnMissingPick.textContent =
                hasAssets ? "Pick a replacement" : "Refresh the image list";
            el.btnMissingPick.dataset.mode = hasAssets ? "pick" : "refresh";
        }
        for (const button of box.querySelectorAll("button[data-content-action]")) {
            button.disabled = pendingContent !== null;
        }
    }

    function updateImageControls() {
        const active = activeImageId();

        if (el.imageSel) {
            if (!selectedAsset) {
                el.imageSel.textContent = "No image selected";
                el.imageSel.title = "";
            } else {
                const asset = assetById(selectedAsset);
                const bits = [asset ? asset.name : shortAsset(selectedAsset)];
                if (asset && asset.width !== null && asset.height !== null) {
                    bits.push(asset.width + "×" + asset.height);
                }
                if (active && selectedAsset === active) bits.push("already on the wall");
                el.imageSel.textContent = bits.join(", ");
                el.imageSel.title = selectedAsset;
            }
        }

        if (el.btnImageApply) {
            const applying = pendingContent === "image";
            const same = !!selectedAsset && selectedAsset === active;
            const canApply =
                wallReady() && !!selectedAsset && !same && pendingContent === null;
            el.btnImageApply.disabled = !canApply;
            el.btnImageApply.textContent = applying
                ? "Applying…"
                : same ? "Already on the wall" : "Show on wall";
            el.btnImageApply.title = !selectedAsset
                ? "Pick an image first. Nothing is sent without a selection."
                : same
                    ? "This image is already on the wall."
                    : "Show this image across the whole wall";
        }

        // The preview follows the selection only: the wall's own copy of the
        // image is the wall's business, and an asset with no URL in the
        // inventory gets no guessed one.
        if (el.imagePreview && el.imagePreviewImg && el.imagePreviewNote) {
            const asset = selectedAsset ? assetById(selectedAsset) : null;
            const url = asset ? asset.url : null;
            if (asset && url) {
                if (el.imagePreviewImg.getAttribute("src") !== url) {
                    el.imagePreview.dataset.failed = "false";
                    el.imagePreviewImg.src = url;
                    el.imagePreviewImg.alt = "Preview of " + asset.name;
                }
                const failed = el.imagePreview.dataset.failed === "true";
                el.imagePreview.hidden = failed;
                el.imagePreviewNote.hidden = !failed;
                el.imagePreviewNote.textContent = failed
                    ? "The preview did not load. Refresh the list to try again."
                    : "";
            } else {
                if (el.imagePreviewImg.getAttribute("src")) {
                    el.imagePreviewImg.removeAttribute("src");
                    el.imagePreviewImg.alt = "";
                }
                el.imagePreview.hidden = true;
                el.imagePreviewNote.hidden = false;
                el.imagePreviewNote.textContent = asset
                    ? "This image has no preview."
                    : "Pick an image from the list.";
            }
        }
    }

    /**
     * `PUT /scene` with the selected asset — the only place an image scene
     * is written, and it refuses to run without a selection.
     */
    async function applyImageScene() {
        if (!wall) return;
        const asset = selectedAsset;
        if (!asset) {
            logStatus("Pick an image from the list first.", "err");
            return;
        }
        if (asset === activeImageId()) return;
        if (pendingContent !== null) return; // one scene save at a time

        pendingContent = "image";
        renderWallContent("image");
        updateImageControls();

        try {
            const data = await requestJson("PUT", "/scene", {
                content: { type: "image", asset: asset, fit: "cover" }
            });
            const next = normalizeWall(data);
            if (!next || next.width <= 0 || next.height <= 0) {
                logStatus(
                    "Image request returned no usable wall state. Waiting for a wall update to confirm it.",
                    "err"
                );
                return;
            }
            wall = next;
            contentView = "image";
            logStatus(
                "Showing the image on the wall (revision " + wall.revision + ").",
                "ok"
            );
        } catch (err) {
            logStatus("Could not show the image: " + err.message, "err");
        } finally {
            pendingContent = null;
            renderWall();
        }
    }

    /** Recovery from a missing asset: put the inventory under the cursor so
     *  the replacement is one click away. */
    function focusAssetPicker() {
        contentView = "image";
        if (wall) renderWallContent(wall.contentType);
        const hasManaged = mediaState === "ready" && mediaAssets.length > 0;
        if (assets.length === 0 && !hasManaged) {
            refreshAssets(false).then(focusFirstAsset);
            return;
        }
        focusFirstAsset();
        logStatus("Pick an image, then press Show on wall.", "info");
    }

    function focusFirstAsset() {
        const first =
            (el.assetList && el.assetList.querySelector("button[data-asset]")) ||
            (el.mediaList && el.mediaList.querySelector("button[data-media]"));
        if (!first) return;
        if (typeof first.scrollIntoView === "function") {
            first.scrollIntoView({ block: "nearest" });
        }
        first.focus();
    }

    /* ------------------------------------------------------------------ *
     * Image coverage — who can and cannot show a still image
     * ------------------------------------------------------------------ */

    function renderCoverage() {
        if (!el.alerts) return;

        const placedIds = wall ? Object.keys(wall.placements).sort(compareIds) : [];
        const noCap = [];
        const unverified = []; // { id, note }

        for (const id of placedIds) {
            const device = devices.get(id);
            if (!device) {
                unverified.push({ id: id, note: "not in the roster · capability unknown" });
                continue;
            }
            const capsKnown = Array.isArray(device.caps);
            const caps = capsKnown ? device.caps : [];
            const hasImage = device.protocol === 2 && caps.indexOf("image") !== -1;
            const lacksImage = device.protocol === 1 ||
                (device.protocol === 2 && capsKnown && !hasImage);
            if (device.online === true) {
                // A v1 socket receives no wall frame, regardless of caps.
                // Missing protocol/caps is unknown, not proof of fallback.
                if (lacksImage) noCap.push(id);
                else if (!hasImage) {
                    unverified.push({ id: id, note: "online · capability unknown" });
                }
            } else if (hasImage) {
                unverified.push({ id: id, note: "offline · image cap" });
            } else if (device.protocol === 1) {
                unverified.push({ id: id, note: "offline · protocol 1" });
            } else if (lacksImage) {
                unverified.push({ id: id, note: "offline · no image cap" });
            } else {
                unverified.push({ id: id, note: "offline · capability unknown" });
            }
        }

        renderNoCapAlert(noCap);
        renderUnverifiedAlert(unverified);

        // The wrapper only shows when at least one block has something to
        // say; otherwise an empty bordered box would sit above the wall.
        const anyShown =
            (el.alertNoCap && !el.alertNoCap.hidden) ||
            (el.alertUnverified && !el.alertUnverified.hidden);
        el.alerts.hidden = !anyShown;
    }

    function renderNoCapAlert(ids) {
        const box = el.alertNoCap;
        if (!box) return;
        if (ids.length === 0) {
            box.hidden = true;
            return;
        }
        const live = !!wall && wall.contentType === "image";
        box.hidden = false;
        box.dataset.kind = live ? "bad" : "warn";

        if (el.alertNoCapTitle) {
            el.alertNoCapTitle.textContent = live
                ? "The image will not cover the whole wall"
                : "An image would not cover the whole wall";
        }
        if (el.alertNoCapText) {
            el.alertNoCapText.textContent =
                ids.length + (ids.length === 1
                    ? " placed online tablet does"
                    : " placed online tablets do") +
                " not support images: " +
                ids.map(function (id) { return shortId(id); }).join(", ") + ". " +
                (live
                    ? "They show their colour while the rest show the picture, so the image has gaps."
                    : "They would stay on colour if you showed an image.");
            el.alertNoCapText.title = ids.join(", ");
        }
    }

    function renderUnverifiedAlert(entries) {
        const box = el.alertUnverified;
        if (!box) return;
        if (entries.length === 0) {
            box.hidden = true;
            return;
        }
        box.hidden = false;
        if (el.alertUnverifiedText) {
            el.alertUnverifiedText.textContent =
                entries.map(function (entry) {
                    return shortId(entry.id) + " (" + entry.note + ")";
                }).join(", ") +
                ". There is no way to confirm what these show. A " +
                "tablet that comes back takes its own spot again.";
            el.alertUnverifiedText.title = entries.map(function (entry) {
                return entry.id + " (" + entry.note + ")";
            }).join("\n");
        }
    }

    /**
     * The capability chip in a tile's meta row — shown only while the scene
     * is an image, which is when "this tablet cannot render it" means
     * anything. It reports what the tablet advertised, not whether the wall
     * succeeded, and an empty `caps` list is called unknown rather than
     * treated as a refusal.
     */
    function renderCapChip(tile, device) {
        if (!tile.capChip) return;
        const show = !!wall && wall.contentType === "image";
        tile.capChip.hidden = !show;
        if (tile.capSep) tile.capSep.hidden = !show;
        if (!show) return;

        const capsKnown = Array.isArray(device.caps);
        const caps = capsKnown ? device.caps : [];
        const hasImage = device.protocol === 2 && caps.indexOf("image") !== -1;
        const lacksImage = device.protocol === 1 ||
            (device.protocol === 2 && capsKnown && !hasImage);
        const online = device.online === true;

        let kind;
        let text;
        if (online && hasImage) {
            kind = "ok";
            text = "Shows images";
        } else if (online && device.protocol === 1) {
            kind = "warn";
            text = "Old version";
        } else if (online && lacksImage) {
            kind = "warn";
            text = "No image support";
        } else if (online) {
            kind = "dim";
            text = "Image support unknown";
        } else if (hasImage) {
            kind = "dim";
            text = "Shows images";
        } else if (device.protocol === 1) {
            kind = "dim";
            text = "Old version";
        } else if (lacksImage) {
            kind = "dim";
            text = "No image support";
        } else {
            kind = "dim";
            text = "Image support unknown";
        }
        tile.capChip.dataset.kind = kind;
        tile.capChip.textContent = text;
        tile.capChip.title = device.protocol === 1
            ? "Protocol 1 receives no wall frame, regardless of advertised capabilities."
            : capsKnown
                ? "Render capabilities this tablet advertised: " + (caps.join(", ") || "none")
                : "Render capabilities were not reported for this tablet.";
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
        // The reservation list keys off the same roster + wall state, so it
        // is redrawn here: a device leaving the roster turns its footprint
        // into a vacant reservation, which is exactly a roster change.
        renderReservations();

        const frame = el.mapFrame;
        frame.textContent = "";

        if (!wallReady()) {
            frame.hidden = true;
            el.mapCaption.textContent = "";
            el.mapEmpty.hidden = false;
            el.mapEmpty.textContent = wall
                ? "Set a wall width and height to see the map."
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
        let vacant = 0;
        let warns = 0;

        // Every placement is drawn — including ones whose device is absent
        // from the roster. Those are reservations (the tablet that returns
        // reclaims its slot), not stale leftovers, so they are rendered and
        // labelled "vacant · reserved" rather than skipped.
        for (const id of Object.keys(wall.placements)) {
            const device = devices.get(id);
            if (device) {
                placed += 1;
            } else {
                vacant += 1;
            }
            const box = buildMapPlacement(
                id, wall.placements[id], device, wallW, wallH, pxW, pxH
            );
            if (box.dataset.aspect === "mismatch") warns += 1;
            frame.appendChild(box);
        }

        if (placed === 0 && vacant === 0) {
            const note = document.createElement("p");
            note.className = "map-none";
            note.textContent = "No tablets are placed on the wall yet";
            frame.appendChild(note);
        }

        const unplaced = Math.max(0, devices.size - placed);
        const bits = [wallW + " × " + wallH, placed + " placed"];
        if (unplaced > 0) bits.push(unplaced + " not placed");
        if (vacant > 0) bits.push(vacant + (vacant === 1 ? " saved spot" : " saved spots") + " with no tablet");
        if (warns > 0) bits.push(warns + (warns === 1 ? " tablet" : " tablets") + " with a different screen shape");
        el.mapCaption.textContent = bits.join(", ");
    }

    /** True when black text reads better than white on this colour. */
    function isLightColor(hex) {
        const m = /^#?([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$/.exec(hex);
        if (!m) return false;
        const r = parseInt(m[1], 16);
        const g = parseInt(m[2], 16);
        const b = parseInt(m[3], 16);
        return (0.299 * r + 0.587 * g + 0.114 * b) > 160;
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
            ? "vacant" // reserved for a tablet that is not in the roster
            : device.online === true ? "online" : "offline";
        box.dataset.aspect = mismatch ? "mismatch" : "match";

        const pxBoxW = (placement.w / wallW) * pxW;
        const pxBoxH = (placement.h / wallH) * pxH;

        const summary =
            "device " + shortId(id) +
            " · position " + placement.x + "," + placement.y +
            " " + placement.w + "×" + placement.h +
            (device ? "" : " · vacant · reserved. Not in the roster") +
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
        } else {
            // No tile to jump to — hand focus to its Release control instead.
            box.addEventListener("click", function () {
                focusRelease(id);
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

            if (!device) {
                // The mark that keeps a reservation from reading as a device:
                // amber sub-label under the id, matching the outline.
                const sub = document.createElement("span");
                sub.className = "map-sub";
                sub.textContent = "no tablet";
                inset.appendChild(sub);
            }

            if (mismatch && pxBoxW >= 76 && pxBoxH >= 34) {
                const ratios = document.createElement("span");
                ratios.className = "map-ar";
                ratios.textContent = fmtAspect(visAspect) + " ≠ " + fmtAspect(devAspect);
                inset.appendChild(ratios);
            }
        }

        // While the wall shows solid colour, paint each tablet with the colour
        // it was given, so the map reads as the wall itself.
        const shown = device && wall && wall.contentType === "color"
            ? normalizeColor(device.color) : null;
        if (shown) {
            inset.dataset.shown = "true";
            inset.dataset.tone = isLightColor(shown) ? "light" : "dark";
            inset.style.setProperty("--shown", shown);
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
                "Tablet " + shortId(deviceId) + " is not connected, so it has no card.",
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
     * Vacant reservations — placements without a roster device
     *
     * Placements are persisted; the roster is not. After a restart a
     * placement can belong to a device that has not re-registered — a
     * reservation, not a leak (PROTOCOL.md "DELETE /devices/{device_id}/
     * placement"). The tablet that returns reclaims its slot, so the only
     * way to give the space back is this explicit release, offered here
     * behind the same two-step confirm as Forget.
     * ------------------------------------------------------------------ */

    /** Placement ids that hold a slot for a device the roster has forgotten. */
    function vacantIds() {
        if (!wall) return [];
        return Object.keys(wall.placements)
            .filter(function (id) { return !devices.has(id); })
            .sort(compareIds);
    }

    function reservationRow(deviceId) {
        if (!el.resList) return null;
        for (const row of el.resList.children) {
            if (row.dataset.res === deviceId) return row;
        }
        return null;
    }

    function endReleaseConfirm() {
        if (confirmReleaseTimer) clearTimeout(confirmReleaseTimer);
        confirmReleaseTimer = null;
        confirmingReleaseId = null;
    }

    function renderReservations() {
        const wrap = el.reservations;
        const list = el.resList;
        if (!wrap || !list) return;

        const ids = vacantIds();
        // A confirmation whose reservation has vanished (released by another
        // controller, tablet returned) is cancelled rather than rebuilt.
        if (confirmingReleaseId && ids.indexOf(confirmingReleaseId) === -1) {
            endReleaseConfirm();
        }

        list.textContent = "";
        if (ids.length === 0) {
            wrap.hidden = true;
            return;
        }
        wrap.hidden = false;
        for (const id of ids) {
            list.appendChild(buildReservationRow(id, wall.placements[id]));
        }
    }

    function buildReservationRow(id, placement) {
        const row = document.createElement("li");
        row.className = "res-row";
        row.dataset.res = id;

        const info = document.createElement("span");
        info.className = "res-info";
        const devId = document.createElement("span");
        devId.className = "res-id mono";
        devId.textContent = shortId(id);
        devId.title = id;
        const rect = document.createElement("span");
        rect.className = "res-rect mono";
        rect.textContent =
            placement.x + "," + placement.y + " " + placement.w + "×" + placement.h;
        info.append(devId, rect);
        row.appendChild(info);

        if (confirmingReleaseId === id) {
            const question = document.createElement("span");
            question.className = "forget-q";
            question.textContent = "Release this saved spot?";

            const yes = document.createElement("button");
            yes.type = "button";
            yes.className = "btn btn-danger btn-sm";
            yes.dataset.action = "release-confirm";
            yes.textContent = "Release";

            const no = document.createElement("button");
            no.type = "button";
            no.className = "btn btn-ghost btn-sm";
            no.dataset.action = "release-cancel";
            no.textContent = "Cancel";

            row.append(question, yes, no);
        } else {
            const release = document.createElement("button");
            release.type = "button";
            release.className = "btn btn-danger btn-sm";
            release.dataset.action = "release";
            release.textContent = "Release";
            release.title =
                "Give this reserved slot back (DELETE the placement). " +
                "the tablet that returns will have to be placed again";
            row.appendChild(release);
        }
        return row;
    }

    /** Map click on a vacant footprint → its Release control, the way a
     *  roster footprint jumps to its tile. Focus only; the confirm is a
     *  deliberate second step. */
    function focusRelease(deviceId) {
        const row = reservationRow(deviceId);
        const button = row && row.querySelector("button[data-action]");
        if (!button) return;
        button.focus();
    }

    function beginRelease(deviceId) {
        if (!wall || !wall.placements[deviceId] || devices.has(deviceId)) return;
        if (confirmingReleaseId && confirmingReleaseId !== deviceId) {
            cancelRelease(confirmingReleaseId);
        }
        confirmingReleaseId = deviceId;
        renderReservations();
        if (confirmReleaseTimer) clearTimeout(confirmReleaseTimer);
        confirmReleaseTimer = setTimeout(function () {
            cancelRelease(deviceId);
        }, RELEASE_CONFIRM_MS);
        const row = reservationRow(deviceId);
        const yes = row && row.querySelector('[data-action="release-confirm"]');
        if (yes) yes.focus();
    }

    function cancelRelease(deviceId) {
        if (confirmingReleaseId !== deviceId) return;
        endReleaseConfirm();
        renderReservations();
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
        tile.placeState.textContent = saved ? "Placed" : "Not placed";
        tile.placeState.dataset.state = saved ? "placed" : "unplaced";
        tile.placeState.title = saved
            ? "Footprint at " + saved.x + "," + saved.y + " · " +
              saved.w + "×" + saved.h + " wall units"
            : "No placement yet. This tablet draws its id and a note.";
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
            return "the frame leaves no visible area";
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
            ? "Screen " + devW + " × " + devH + " (shape " + fmtAspect(devAspect) + ")"
            : "Screen size not reported";

        const evaluating = tile.placeDirty || !!savedPlacement(device.device_id);
        if (!evaluating) {
            setReadout(tile, "none", "Not on the wall", false, "");
            return;
        }

        const placement = readPlacementInputs(tile);
        if (!placement) {
            setReadout(tile, "edit", "Fill in every field", false, "");
            return;
        }

        const problem = placementProblem(placement);
        if (problem) {
            setReadout(tile, "invalid", "Invalid position", true, problem);
            return;
        }

        const visible = visibleRect(placement);
        const visAspect = aspectOf(visible.w, visible.h);
        const delta = aspectDelta(visAspect, devAspect);
        const row =
            "Visible area " + visible.w + " × " + visible.h +
            " (shape " + fmtAspect(visAspect) +
            ", screen " + fmtAspect(devAspect) +
            ", " + fmtDelta(delta) + " off)";

        if (devAspect === null) {
            setReadout(
                tile, "unknown", row, true,
                "This tablet has not reported its screen size, so the shapes cannot be compared.", "dim"
            );
        } else if (isAspectMismatch(delta)) {
            setReadout(
                tile, "mismatch", row, true,
                "The shape of this area differs from the tablet screen, so the picture will be cropped."
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
            logStatus("That is not a valid colour: " + rawColor, "err");
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
                "Tablet " + shortId(deviceId) + " set to " + applied +
                    (delivered ? "." : ". It will change when the tablet reconnects."),
                delivered ? "ok" : "info"
            );
        } catch (err) {
            logStatus("Could not set the colour on tablet " + shortId(deviceId) + ": " + err.message, "err");
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
                logStatus("No tablets to colour yet.", "info");
            } else {
                logStatus(
                    "Set " + applied + " on " + updated + (updated === 1 ? " tablet" : " tablets") + ", " + delivered + " updated right away.",
                    "ok"
                );
            }
        } catch (err) {
            logStatus("Could not apply the colour: " + err.message, "err");
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
            logStatus("Forgot tablet " + shortId(deviceId) + ".", "ok");
        } catch (err) {
            if (err.status === 404) {
                // Already gone from the server's roster — forget it locally too.
                dropDevice(deviceId);
                logStatus("Tablet " + shortId(deviceId) + " was already gone.", "info");
            } else {
                logStatus("Could not forget tablet " + shortId(deviceId) + ": " + err.message, "err");
                if (tile) tile.el.dataset.busy = "false";
            }
        }
    }

    function dropDevice(deviceId) {
        devices.delete(deviceId);
        // Deliberately does NOT touch wall.placements: the server decides
        // whether a placement survives (a device delete drops its own; a
        // mere roster gap leaves a reservation) and broadcasts `wall_updated`
        // when it changes. Dropping it here would erase a reservation from
        // the diagram before the server has said anything.
        removeTile(deviceId);
        renderTally();
        renderEmpty();
        renderWallMap(); // its footprint now reads as a vacant reservation
        renderCoverage(); // …and its capability is now unknown
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
        // Layout only: scene content goes to PUT /scene (see below), so the
        // two never share a request (PROTOCOL.md "Wall state").
        el.btnWallSave.disabled = true;
        try {
            const data = await requestJson("PUT", "/wall", {
                width: width,
                height: height
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
                    // No scene is known here (the response was not a wall
                    // state), so none is claimed.
                    contentType: wall ? wall.contentType : null,
                    content: wall ? wall.content : null,
                    generation: wall ? wall.generation : null,
                    revision: wall ? wall.revision : 0,
                    placements: wall ? wall.placements : {}
                };
            }
            wallDirty = false;
            renderWall();
            logStatus(
                "Wall size saved: " + wall.width + " × " + wall.height + " (revision " + wall.revision + ").",
                "ok"
            );
        } catch (err) {
            logStatus("Could not save the wall size: " + err.message, "err");
        } finally {
            renderWall();
        }
    }

    /**
     * Scene content — `PUT /scene` with `{content: {type}}`.
     *
     * Sent the moment the operator picks a value rather than on form
     * submit, because it is a different endpoint from the dimensions and
     * deliberately independent of them (PROTOCOL.md "Wall state": layout and
     * scene are kept separate on purpose). The response is the full wall
     * state, so it is adopted directly; a failure rolls the control back to
     * whatever the server last told us and says so in the status bar.
     */
    async function saveSceneContent(type) {
        if (!wall) return;
        contentView = type;
        pendingContent = type;
        renderWallContent(type);
        updateImageControls(); // the image action waits its turn too

        try {
            const data = await requestJson("PUT", "/scene", {
                content: { type: type }
            });
            const next = normalizeWall(data);
            if (next && next.width > 0 && next.height > 0) {
                wall = next;
            }
            logStatus(
                "Wall now shows " + contentLabel(type).replace(" (no image)", "").toLowerCase() + " (revision " + wall.revision + ").",
                "ok"
            );
        } catch (err) {
            logStatus("Could not change what the wall shows: " + err.message, "err");
        } finally {
            pendingContent = null;
            renderWall();
        }
    }

    async function arrangeWall() {
        const body = {};
        const raw = String(el.autoColumns.value).trim();
        if (raw !== "") {
            const columns = Number(raw);
            if (!Number.isInteger(columns) || columns < 1) {
                logStatus("Columns must be a whole number above zero, or empty for automatic.", "err");
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
                logStatus("Arranged the online tablets (revision " + next.revision + ").", "ok");
            } else {
                logStatus("Arrange sent. Waiting for the wall to update.", "info");
            }
        } catch (err) {
            logStatus("Could not arrange the tablets: " + err.message, "err");
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
                "Tablet " + shortId(deviceId) + " needs a number in every position field.",
                "err"
            );
            updatePlacementReadout(tile, device);
            return;
        }
        const problem = placementProblem(placement);
        if (problem) {
            logStatus(
                "Tablet " + shortId(deviceId) + " position rejected: " + problem + ".",
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
            logStatus("Position saved for tablet " + shortId(deviceId) + ".", "ok");
        } catch (err) {
            if (err.status === 404) {
                // Unknown device: the roster lost it while we were editing.
                dropDevice(deviceId);
                logStatus("Tablet " + shortId(deviceId) + " was already gone.", "info");
            } else {
                logStatus(
                    "Could not save the position of tablet " + shortId(deviceId) + ": " + err.message,
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
            logStatus("Tablet " + shortId(deviceId) + " removed from the wall.", "ok");
        } catch (err) {
            if (err.status === 404) {
                dropDevice(deviceId);
                logStatus("Tablet " + shortId(deviceId) + " was already gone.", "info");
            } else {
                logStatus(
                    "Could not remove tablet " + shortId(deviceId) + " from the wall: " + err.message,
                    "err"
                );
            }
        } finally {
            if (tiles.get(deviceId) === tile) tile.el.dataset.busy = "false";
        }
    }

    /**
     * Release a vacant reservation: `DELETE /devices/{id}/placement`.
     *
     * This endpoint answers 200 when a placement exists even though the
     * roster has forgotten the device, which is exactly the case a tile
     * cannot reach. The placement is removed locally only because the
     * server just confirmed it removed the placement; otherwise the server
     * stays authoritative and `wall_updated` is what clears the diagram.
     */
    async function releasePlacement(deviceId) {
        endReleaseConfirm(); // the confirm step is done; the request is in flight

        const row = reservationRow(deviceId);
        if (row) {
            row.dataset.busy = "true";
            for (const button of row.querySelectorAll("button")) button.disabled = true;
        }

        try {
            await requestJson(
                "DELETE",
                "/devices/" + encodeURIComponent(deviceId) + "/placement"
            );
            if (wall && wall.placements[deviceId]) {
                const placements = Object.assign({}, wall.placements);
                delete placements[deviceId];
                wall.placements = placements;
            }
            renderWall();
            logStatus("Released the saved spot of tablet " + shortId(deviceId) + ".", "ok");
        } catch (err) {
            if (err.status === 404) {
                // Neither the device nor a placement exists any more — the
                // server has already forgotten it, so this page may too.
                if (wall && wall.placements[deviceId]) {
                    const placements = Object.assign({}, wall.placements);
                    delete placements[deviceId];
                    wall.placements = placements;
                }
                renderWall();
                logStatus(
                    "The saved spot of tablet " + shortId(deviceId) + " was already gone.",
                    "info"
                );
            } else {
                logStatus(
                    "Could not release the saved spot of tablet " + shortId(deviceId) +
                        ": " + err.message,
                    "err"
                );
                renderReservations(); // rebuild the row with working buttons
            }
        }
    }

    /* ------------------------------------------------------------------ *
     * Saved layouts and scenes — named snapshots (Phase 2c)
     *
     * Two collections with separate name spaces (PROTOCOL.md "Named
     * snapshots"). Each has its own panel, name input and list; neither
     * knows about the other. The server snapshots its OWN active wall, so a
     * save sends no body at all:
     *
     *   GET    /layouts | /scenes              list
     *   PUT    /{base}/{name}                  save; 409 when the name exists
     *   PUT    /{base}/{name}?replace=true     overwrite — only after a
     *                                          visible second click here
     *   POST   /{base}/{name}/recall           apply; answers with the wall
     *   DELETE /{base}/{name}                  drop the snapshot only
     *
     * A recall never mutates local state directly: the server's own wall
     * answer goes through `adoptWallState`, the same "not older than what we
     * hold, within a generation" rule `wall_updated` applies, and the roster
     * socket keeps carrying everything else (including after a reconnect).
     * Names are only ever written as text nodes or path components — never
     * as markup — so a snapshot called "<img onerror=…>" is just a name.
     * ------------------------------------------------------------------ */

    const SNAPSHOT_CONFIRM_MS = 8000;

    /* The server's name rule, checked here so a bad name never costs a round
     * trip: trimmed, 1–64 characters, an ASCII letter or digit first, then
     * letters, digits, spaces, dot, underscore or hyphen. Case-sensitive —
     * nothing here lowercases, folds or otherwise rewrites what was typed. */
    const SNAPSHOT_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$/;

    const SNAPSHOTS = {
        layout: {
            base: "/layouts",
            label: "layout",
            title: "Layout",
            saveVerb: "Save layout",
            items: [],
            loaded: false,
            loading: false,
            operation: null,      // "save" | "overwrite" | "recall" | "delete"
            overwrite: null,      // name waiting for the visible second click
            overwriteTimer: null,
            confirm: null,        // { action: "recall" | "delete", name }
            confirmTimer: null
        },
        scene: {
            base: "/scenes",
            label: "scene",
            title: "Scene",
            saveVerb: "Save scene",
            items: [],
            loaded: false,
            loading: false,
            operation: null,
            overwrite: null,
            overwriteTimer: null,
            confirm: null,
            confirmTimer: null
        }
    };

    function snapRefs(kind) {
        return snapEl[kind];
    }

    function capLabel(snap) {
        return snap.label.charAt(0).toUpperCase() + snap.label.slice(1);
    }

    /**
     * Adopt a wall state that came back from one of our own commands.
     *
     * Same rule as the `wall_updated` handler: within one generation a frame
     * that is older than what we hold is a replay and must not rewind the
     * diagram — the broadcast that carries the authoritative state is on its
     * way. A different generation (the server resynchronised) or nothing held
     * yet adopts unconditionally.
     *
     * Returns true when the state was taken.
     */
    function adoptWallState(next) {
        if (!next) return false;
        if (wall && next.generation === wall.generation && next.revision < wall.revision) {
            return false;
        }
        wall = next;
        return true;
    }

    /** Trimmed, in-range, and the exact spelling the operator typed. */
    function validateSnapshotName(raw) {
        const name = String(raw === null || raw === undefined ? "" : raw).trim();
        if (name === "") {
            return { error: "Give the snapshot a name first." };
        }
        if (name.length > 64) {
            return { error: "Names are at most 64 characters. This one is " + name.length + "." };
        }
        if (!SNAPSHOT_NAME_RE.test(name)) {
            return {
                error: "Names start with a letter or digit and then hold only " +
                    "letters, digits, spaces, dot, underscore or hyphen (1–64 characters)."
            };
        }
        return { name: name };
    }

    /** There is nothing to snapshot until the server has told us what is
     *  active — the same gate the wall form uses. */
    function snapSaveAvailable(kind) {
        if (kind === "layout") return wallReady();
        return !!wall && !!wall.content;
    }

    /** The panel's own status line: validation, in-flight work, why a read is
     *  stale. The markup gives it `role="status"`, so the text is announced
     *  as well as shown — and it is only ever assigned as text. */
    function setSnapMsg(kind, text, msgKind) {
        const node = snapRefs(kind).msg;
        if (!node) return;
        if (!text) {
            node.hidden = true;
            node.textContent = "";
            return;
        }
        node.hidden = false;
        node.dataset.kind = msgKind || "info";
        node.textContent = text;
    }

    /* ------------------------------------------------------------------ *
     * Snapshot list reading + rendering
     * ------------------------------------------------------------------ */

    /** One row's second column: what the server listed, and nothing else. */
    function snapshotItemMeta(kind, entry) {
        if (entry.invalid === true) {
            return "INVALID SAVED DATA · delete or replace this snapshot";
        }
        if (kind === "layout") {
            const layout = entry.layout && typeof entry.layout === "object" ? entry.layout : null;
            if (!layout) return "";
            const width = Number(layout.width);
            const height = Number(layout.height);
            const bits = [];
            if (Number.isFinite(width) && width > 0 && Number.isFinite(height) && height > 0) {
                bits.push(Math.round(width) + " × " + Math.round(height) + " u");
            }
            const placements = layout.placements && typeof layout.placements === "object"
                ? Object.keys(layout.placements).length
                : null;
            if (placements !== null) {
                bits.push(placements + (placements === 1 ? " placement" : " placements"));
            }
            return bits.join(" · ");
        }

        const content = entry.content && typeof entry.content === "object" ? entry.content : null;
        if (!content || typeof content.type !== "string" || content.type === "") {
            return "content not listed";
        }
        // The raw type, never a friendlier one: this page does not claim to
        // render a type it has never heard of.
        const bits = [content.type];
        if (content.type === "image" && typeof content.asset === "string" && content.asset !== "") {
            bits.push(shortAsset(content.asset));
        }
        if (typeof content.fit === "string" && content.fit !== "") bits.push("fit " + content.fit);
        return bits.join(" · ");
    }

    /**
     * The payload as a sorted list, or null when it is not a list in any
     * shape this page recognises — the caller reports that instead of
     * showing an empty list that reads as "you have no saved snapshots".
     */
    function normalizeSnapshotList(payload, kind) {
        const snap = SNAPSHOTS[kind];
        let entries = null;
        if (Array.isArray(payload)) {
            entries = payload;
        } else if (payload && typeof payload === "object") {
            for (const key of [snap.base.slice(1), "items", "list"]) {
                if (Array.isArray(payload[key])) {
                    entries = payload[key];
                    break;
                }
            }
        }
        if (!entries) return null;

        const seen = new Set();
        const out = [];
        for (const raw of entries) {
            if (!raw || typeof raw !== "object" || Array.isArray(raw)) continue;
            const name = typeof raw.name === "string" ? raw.name : "";
            if (name === "" || seen.has(name)) continue;
            seen.add(name);
            out.push({ name: name, meta: snapshotItemMeta(kind, raw) });
        }
        out.sort(function (a, b) {
            const an = a.name.toLowerCase();
            const bn = b.name.toLowerCase();
            if (an !== bn) return an < bn ? -1 : 1;
            return compareIds(a.name, b.name);
        });
        return out;
    }

    function snapshotRow(kind, name) {
        const list = snapRefs(kind).list;
        if (!list) return null;
        for (const row of list.children) {
            if (row.dataset.name === name) return row;
        }
        return null;
    }

    /** Back to the row's ordinary action button, so cancelling a confirm
     *  leaves the keyboard operator where they were. */
    function focusSnapshotAction(kind, name, action) {
        const row = snapshotRow(kind, name);
        if (!row) return false;
        const button = row.querySelector(
            '[data-action="' + (action === "delete" ? "snap-delete" : "snap-recall") + '"]'
        );
        if (!button) return false;
        button.focus();
        return true;
    }

    function restoreSnapshotFocus(kind, name, action, hadFocus) {
        // Don't steal focus if the operator moved elsewhere while a request
        // was in flight. Rebuilt rows remove the old focused button and send
        // focus to <body>; return it to its equivalent, or to the name field
        // after a successful delete removed the row altogether.
        if (!hadFocus || document.activeElement !== document.body) return;
        if (!focusSnapshotAction(kind, name, action)) {
            const input = snapRefs(kind).name;
            if (input) input.focus();
        }
    }

    function buildSnapshotRow(kind, item, busy) {
        const snap = SNAPSHOTS[kind];
        const row = document.createElement("li");
        row.className = "snap-row";
        row.dataset.name = item.name;

        const info = document.createElement("span");
        info.className = "snap-info";
        const name = document.createElement("span");
        name.className = "snap-name";
        name.textContent = item.name;
        const meta = document.createElement("span");
        meta.className = "snap-meta mono";
        meta.textContent = item.meta;
        info.append(name, meta);
        row.appendChild(info);

        const confirming = !!snap.confirm && snap.confirm.name === item.name;
        if (confirming) {
            const question = document.createElement("span");
            question.className = "snap-q";
            question.textContent = snap.confirm.action === "delete"
                ? 'Delete "' + item.name + '" for good? The wall itself is not changed.'
                : "Replace the current layout? Wall size and every tablet position change. " +
                  "What the wall shows stays the same.";

            const yes = document.createElement("button");
            yes.type = "button";
            yes.className = "btn btn-danger btn-sm";
            yes.dataset.action = snap.confirm.action === "delete"
                ? "snap-delete-confirm" : "snap-recall-confirm";
            yes.textContent = snap.confirm.action === "delete" ? "Delete" : "Recall";
            yes.disabled = busy;

            const no = document.createElement("button");
            no.type = "button";
            no.className = "btn btn-ghost btn-sm";
            no.dataset.action = "snap-confirm-cancel";
            no.textContent = "Cancel";
            no.disabled = busy;

            row.append(question, yes, no);
            return row;
        }

        const recall = document.createElement("button");
        recall.type = "button";
        recall.className = "btn btn-sm";
        recall.dataset.action = "snap-recall";
        recall.textContent = "Recall";
        recall.disabled = busy;
        recall.title = kind === "layout"
            ? "Replace the active dimensions and every placement (reservations included). " +
              "The scene content is preserved."
            : "Apply this content to the layout that is active right now. " +
              "Dimensions and placements are untouched.";

        const del = document.createElement("button");
        del.type = "button";
        del.className = "btn btn-ghost btn-sm";
        del.dataset.action = "snap-delete";
        del.textContent = "Delete";
        del.disabled = busy;
        del.title = 'Remove the saved ' + snap.label + ' "' + item.name +
            '. The active wall keeps everything it has.';

        row.append(recall, del);
        return row;
    }

    function renderSnapshotList(kind) {
        const snap = SNAPSHOTS[kind];
        const refs = snapRefs(kind);
        // A list that is mid-read is about to be rebuilt, so nothing on it is
        // actionable — including a confirm that would fire into the read.
        const busy = snap.operation !== null || snap.loading;

        // A confirmation for a name that has left the list (deleted elsewhere,
        // listed by an older read) is dropped rather than rebuilt on a row
        // that is no longer there.
        if (snap.confirm && !snap.items.some(function (item) { return item.name === snap.confirm.name; })) {
            endSnapshotConfirm(kind);
        }

        if (refs.list) {
            refs.list.textContent = "";
            for (const item of snap.items) {
                refs.list.appendChild(buildSnapshotRow(kind, item, busy));
            }
            refs.list.hidden = snap.items.length === 0;
        }

        if (refs.empty) {
            let text = "";
            if (snap.loading) {
                text = "Reading the saved " + snap.label + "s…";
            } else if (!snap.loaded) {
                text = "Saved " + snap.label + "s not read yet. Press Refresh.";
            } else if (snap.items.length === 0) {
                text = "Nothing saved yet. Name the " +
                    (kind === "layout" ? "current arrangement" : "current content") +
                    " above and press " + snap.saveVerb + ".";
            }
            refs.empty.hidden = text === "";
            refs.empty.textContent = text;
        }
    }

    function updateSnapshotSaveButton(kind) {
        const snap = SNAPSHOTS[kind];
        const button = snapRefs(kind).save;
        if (!button) return;
        const available = snapSaveAvailable(kind);
        button.disabled = snap.operation !== null || snap.loading || !available;
        button.textContent = snap.operation === "save" ? "Saving…" : snap.saveVerb;
        button.title = available
            ? "Snapshot the server's current " + snap.label + " under the name you type"
            : kind === "layout"
                ? "No wall state from the server yet. There is nothing to save."
                : "No scene content from the server yet. There is nothing to save.";
    }

    /** Called from `renderWall` on every wall change: it only refreshes the
     *  two save buttons, so a broadcast never steals focus from a list row. */
    function renderSnapshotAvailability() {
        updateSnapshotSaveButton("layout");
        updateSnapshotSaveButton("scene");
    }

    function renderSnapshotPanel(kind) {
        const snap = SNAPSHOTS[kind];
        const refs = snapRefs(kind);
        const busy = snap.operation !== null;

        if (refs.name) refs.name.disabled = busy || snap.loading;
        updateSnapshotSaveButton(kind);

        if (refs.refresh) {
            refs.refresh.disabled = busy || snap.loading;
            refs.refresh.textContent = snap.loading ? "Reading…" : "Refresh";
        }

        if (refs.overwrite) {
            refs.overwrite.hidden = !snap.overwrite;
            if (snap.overwrite && refs.overwriteText) {
                refs.overwriteText.textContent =
                    'A ' + snap.label + ' named "' + snap.overwrite + '" already exists. ' +
                    "replace it? Nothing has been overwritten yet.";
            }
            if (refs.overwriteYes) refs.overwriteYes.disabled = busy;
            if (refs.overwriteNo) refs.overwriteNo.disabled = busy;
        }

        renderSnapshotList(kind);
    }

    /* ------------------------------------------------------------------ *
     * Snapshot commands
     * ------------------------------------------------------------------ */

    /** GET the list. A failure keeps the last good rows and says why they
     *  are stale — the same rule the asset inventory follows. */
    async function refreshSnapshots(kind, quiet) {
        const snap = SNAPSHOTS[kind];
        if (snap.loading || snap.operation !== null) return false;
        snap.loading = true;
        renderSnapshotPanel(kind);

        let succeeded = false;
        try {
            const data = await requestJson("GET", snap.base);
            const items = normalizeSnapshotList(data, kind);
            if (items === null) {
                throw new Error("the answer was not a " + snap.label + " list");
            }
            snap.items = items;
            snap.loaded = true;
            succeeded = true;
            setSnapMsg(kind, null);
            if (!quiet) {
                logStatus(
                    capLabel(snap) + ": " + items.length + " saved " +
                        (items.length === 1 ? snap.label : snap.label + "s") + ".",
                    "ok"
                );
            }
        } catch (err) {
            setSnapMsg(
                kind,
                "Could not read the saved " + snap.label + "s: " + err.message +
                    (snap.loaded ? ". Showing the list read earlier." : ""),
                "err"
            );
            if (!quiet) logStatus("Saved " + snap.label + "s unavailable: " + err.message, "err");
        } finally {
            snap.loading = false;
            renderSnapshotPanel(kind);
        }
        return succeeded;
    }

    /** PUT /{base}/{name} — the server snapshots its own active wall. */
    async function saveSnapshot(kind) {
        const snap = SNAPSHOTS[kind];
        const refs = snapRefs(kind);
        if (snap.operation !== null || snap.loading) return;

        const check = validateSnapshotName(refs.name ? refs.name.value : "");
        if (check.error) {
            setSnapMsg(kind, check.error, "err");
            if (refs.name) refs.name.focus();
            return;
        }
        const name = check.name;

        snap.operation = "save";
        setSnapMsg(kind, 'Saving ' + snap.label + ' "' + name + '"…', "busy");
        renderSnapshotPanel(kind);

        let saved = false;
        let conflict = false;
        try {
            await requestJson("PUT", snap.base + "/" + encodeURIComponent(name));
            saved = true;
        } catch (err) {
            if (err.status === 409) {
                conflict = true;
            } else if (err.status === 422) {
                setSnapMsg(kind, 'The server will not take the name "' + name + '": ' + err.message, "err");
            } else {
                setSnapMsg(kind, "Not saved: " + err.message, "err");
            }
        } finally {
            snap.operation = null;
        }

        if (saved) {
            endSnapshotOverwrite(kind); // this name exists now, nothing pending
            if (refs.name) refs.name.value = "";
            setSnapMsg(kind, null);
            logStatus(snap.title + ' "' + name + '" saved.', "ok");
            renderSnapshotPanel(kind);
            await refreshSnapshots(kind, true); // success refreshes the list
            return;
        }

        renderSnapshotPanel(kind);
        if (conflict) beginSnapshotOverwrite(kind, name);
    }

    /**
     * The server answered 409. Nothing is retried automatically: the operator
     * gets a visible block with its own buttons and focus lands on "Replace
     * it", so the overwrite is a second, deliberate act — and it expires.
     */
    function beginSnapshotOverwrite(kind, name) {
        const snap = SNAPSHOTS[kind];
        endSnapshotOverwrite(kind);
        snap.overwrite = name;
        setSnapMsg(
            kind,
            'A ' + snap.label + ' named "' + name + '" already exists, so nothing was ' +
                "saved. Press Replace it to overwrite it, or Cancel to keep it and " +
                "choose another name.",
            "warn"
        );
        renderSnapshotPanel(kind);

        const yes = snapRefs(kind).overwriteYes;
        if (yes) yes.focus();
        snap.overwriteTimer = setTimeout(function () {
            snap.overwriteTimer = null;
            if (snap.overwrite !== name) return;
            const hadFocus = snapRefs(kind).overwrite.contains(document.activeElement);
            snap.overwrite = null;
            setSnapMsg(kind, 'Not replaced. "' + name + '" is still the saved one. ' +
                "Press Save again and confirm to overwrite it.", "info");
            renderSnapshotPanel(kind);
            if (hadFocus && document.activeElement === document.body) {
                const input = snapRefs(kind).name;
                if (input) input.focus();
            }
        }, SNAPSHOT_CONFIRM_MS);
    }

    function endSnapshotOverwrite(kind) {
        const snap = SNAPSHOTS[kind];
        if (snap.overwriteTimer) clearTimeout(snap.overwriteTimer);
        snap.overwriteTimer = null;
        snap.overwrite = null;
    }

    function cancelSnapshotOverwrite(kind) {
        const snap = SNAPSHOTS[kind];
        if (!snap.overwrite) return;
        const name = snap.overwrite;
        endSnapshotOverwrite(kind);
        setSnapMsg(kind, 'Kept the existing "' + name + '". Nothing was overwritten.', "info");
        renderSnapshotPanel(kind);
        const input = snapRefs(kind).name;
        if (input) input.focus();
    }

    /** The visible second click: PUT ?replace=true, never sent otherwise. */
    async function replaceSnapshot(kind) {
        const snap = SNAPSHOTS[kind];
        const name = snap.overwrite;
        if (!name || snap.operation !== null || snap.loading) return;
        const hadFocus = snapRefs(kind).overwrite.contains(document.activeElement);
        endSnapshotOverwrite(kind);

        snap.operation = "overwrite";
        setSnapMsg(kind, 'Replacing "' + name + '"…', "busy");
        renderSnapshotPanel(kind);

        let ok = false;
        try {
            await requestJson(
                "PUT",
                snap.base + "/" + encodeURIComponent(name) + "?replace=true"
            );
            ok = true;
        } catch (err) {
            setSnapMsg(kind, "Not replaced: " + err.message, "err");
        } finally {
            snap.operation = null;
        }

        if (ok) {
            const refs = snapRefs(kind);
            if (refs.name) refs.name.value = "";
            setSnapMsg(kind, null);
            logStatus(snap.title + ' "' + name + '" replaced.', "ok");
            await refreshSnapshots(kind, true);
        }
        renderSnapshotPanel(kind);
        if (hadFocus && document.activeElement === document.body) {
            const input = snapRefs(kind).name;
            if (input) input.focus();
        }
    }

    function endSnapshotConfirm(kind) {
        const snap = SNAPSHOTS[kind];
        if (snap.confirmTimer) clearTimeout(snap.confirmTimer);
        snap.confirmTimer = null;
        snap.confirm = null;
    }

    /**
     * Recall is two different risks, so it is two different interactions.
     *
     * A layout recall replaces the active dimensions and every placement —
     * reservations included — so it asks first and spells out what goes. A
     * scene recall only sets content on the layout that is active now: there
     * is nothing to throw away, so it is one click (and the server is what
     * guarantees the arrangement is untouched).
     */
    function beginSnapshotRecall(kind, name) {
        const snap = SNAPSHOTS[kind];
        if (snap.operation !== null || snap.loading) return;
        if (kind === "scene") {
            recallSnapshot(kind, name);
            return;
        }
        if (snap.confirm && (snap.confirm.action !== "recall" || snap.confirm.name !== name)) {
            endSnapshotConfirm(kind);
        }
        snap.confirm = { action: "recall", name: name };
        renderSnapshotPanel(kind);
        if (snap.confirmTimer) clearTimeout(snap.confirmTimer);
        snap.confirmTimer = setTimeout(function () {
            cancelSnapshotConfirm(kind);
        }, SNAPSHOT_CONFIRM_MS);

        const row = snapshotRow(kind, name);
        const yes = row && row.querySelector('[data-action="snap-recall-confirm"]');
        if (yes) yes.focus();
    }

    function beginSnapshotDelete(kind, name) {
        const snap = SNAPSHOTS[kind];
        if (snap.operation !== null || snap.loading) return;
        if (snap.confirm && (snap.confirm.action !== "delete" || snap.confirm.name !== name)) {
            endSnapshotConfirm(kind);
        }
        snap.confirm = { action: "delete", name: name };
        renderSnapshotPanel(kind);
        if (snap.confirmTimer) clearTimeout(snap.confirmTimer);
        snap.confirmTimer = setTimeout(function () {
            cancelSnapshotConfirm(kind);
        }, SNAPSHOT_CONFIRM_MS);

        const row = snapshotRow(kind, name);
        const yes = row && row.querySelector('[data-action="snap-delete-confirm"]');
        if (yes) yes.focus();
    }

    function cancelSnapshotConfirm(kind) {
        const snap = SNAPSHOTS[kind];
        if (!snap.confirm) return;
        const { name, action } = snap.confirm;
        const row = snapshotRow(kind, name);
        const hadFocus = !!row && row.contains(document.activeElement);
        endSnapshotConfirm(kind);
        renderSnapshotPanel(kind);
        restoreSnapshotFocus(kind, name, action, hadFocus);
    }

    /** POST /{base}/{name}/recall — adopt the wall the server sends back. */
    async function recallSnapshot(kind, name) {
        const snap = SNAPSHOTS[kind];
        if (snap.operation !== null || snap.loading) return;
        const row = snapshotRow(kind, name);
        const hadFocus = !!row && row.contains(document.activeElement);
        endSnapshotConfirm(kind); // the confirm step (layout) is done

        snap.operation = "recall";
        setSnapMsg(kind, 'Recalling "' + name + '"…', "busy");
        renderSnapshotPanel(kind);

        let failure = null;
        let took = false;
        try {
            const data = await requestJson(
                "POST",
                snap.base + "/" + encodeURIComponent(name) + "/recall"
            );
            took = adoptWallState(normalizeWall(data));
        } catch (err) {
            failure = err;
        } finally {
            snap.operation = null;
        }

        if (failure) {
            if (failure.status === 404) {
                // Someone else removed it while our list still showed it.
                // Re-read first: a successful refresh clears this panel's
                // message line, so the explanation lands after it.
                const refreshed = await refreshSnapshots(kind, true);
                if (refreshed) {
                    setSnapMsg(
                        kind,
                        'The ' + snap.label + ' "' + name + '" is no longer saved. ' +
                            "someone else removed it. The list was refreshed.",
                        "err"
                    );
                }
                renderSnapshotPanel(kind);
                restoreSnapshotFocus(kind, name, "recall", hadFocus);
                logStatus(
                    snap.title + ' "' + name + '" is no longer saved' +
                        (refreshed ? ". The list was refreshed." : "; list refresh failed."),
                    "err"
                );
                return;
            }
            setSnapMsg(
                kind,
                (kind === "layout" ? "Layout not recalled: " : "Scene not recalled: ") +
                    failure.message,
                "err"
            );
            renderSnapshotPanel(kind);
            restoreSnapshotFocus(kind, name, "recall", hadFocus);
            logStatus(snap.title + ' "' + name + '" not recalled: ' + failure.message, "err");
            return;
        }

        if (kind === "layout" && took) {
            // The operator asked for the arrangement to be replaced, so any
            // unsaved dimension edits are exactly what just got overwritten.
            wallDirty = false;
            el.wallWidth.value = String(wall.width);
            el.wallHeight.value = String(wall.height);
        }

        setSnapMsg(kind, null);
        renderSnapshotPanel(kind);

        if (kind === "scene") {
            // The recalled content can name an asset that is no longer in the
            // inventory — that must not block the recall, but it must be seen:
            // re-read the inventory so the missing-asset warning below can tell
            // the truth about what the wall is now showing.
            await refreshAssets(true);
        }

        renderWall();
        restoreSnapshotFocus(kind, name, "recall", hadFocus);
        logStatus(
            took
                ? snap.title + ' "' + name + '" recalled. Revision ' +
                      (wall ? wall.revision : "-") + "."
                : snap.title + ' "' + name + '" recalled. Waiting for the wall update.',
            took ? "ok" : "info"
        );
    }

    /**
     * DELETE /{base}/{name} — the snapshot only. The active wall is not part
     * of this request, so a successful delete never changes what is shown.
     */
    async function deleteSnapshot(kind, name) {
        const snap = SNAPSHOTS[kind];
        if (snap.operation !== null || snap.loading) return;
        const row = snapshotRow(kind, name);
        const hadFocus = !!row && row.contains(document.activeElement);
        endSnapshotConfirm(kind); // the confirm step is done

        snap.operation = "delete";
        setSnapMsg(kind, 'Deleting "' + name + '"…', "busy");
        renderSnapshotPanel(kind);

        let gone = false;
        let failure = null;
        try {
            await requestJson("DELETE", snap.base + "/" + encodeURIComponent(name));
        } catch (err) {
            if (err.status === 404) gone = true;
            else failure = err;
        } finally {
            snap.operation = null;
        }

        if (failure) {
            setSnapMsg(kind, "Not deleted: " + failure.message, "err");
            renderSnapshotPanel(kind);
            restoreSnapshotFocus(kind, name, "delete", hadFocus);
            logStatus(snap.title + ' "' + name + '" not deleted: ' + failure.message, "err");
            return;
        }

        // The server confirmed this row is gone (or was already absent).
        // Remove it locally before the follow-up read: a failed refresh must
        // not leave a clickable row that claims it still exists.
        snap.items = snap.items.filter(function (item) { return item.name !== name; });
        renderSnapshotPanel(kind);
        logStatus(
            snap.title + ' "' + name + '" deleted' +
                (gone ? " (it was already gone)" : "") + ". The wall is unchanged.",
            gone ? "info" : "ok"
        );
        // Re-read before reporting: a successful refresh clears this panel's
        // message line, so "already gone" has to be written after it.
        const refreshed = await refreshSnapshots(kind, true);
        if (refreshed) {
            setSnapMsg(kind, gone ? 'The ' + snap.label + ' "' + name + '" was already gone.' : null, "info");
        }
        renderSnapshotPanel(kind);
        restoreSnapshotFocus(kind, name, "delete", hadFocus);
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
        question.textContent = "Forget this tablet?";

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
        el.globalSel.textContent = color || "None chosen";
        el.globalSel.dataset.set = color ? "true" : "false";
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
                "Select " + preset.name + " " + preset.color + " for all tablets"
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

        /* Scene content: applied immediately via PUT /scene — it is not part
         * of the form submit, which only saves the dimensions. */
        if (el.wallContent) {
            el.wallContent.addEventListener("click", function (event) {
                const button = event.target.closest("button[data-content]");
                if (!button || button.disabled) return;
                const type = button.dataset.content;
                // An image needs a choice of file first, so this option only
                // opens the library; "Show on wall" is what sends it.
                if (type === "image") {
                    contentView = "image";
                    if (wall) renderWallContent(wall.contentType);
                    focusAssetPicker();
                    return;
                }
                if (!isSettableContent(type)) return; // only what the server accepts
                contentView = type;
                if (wall) renderWallContent(wall.contentType);
                if (pendingContent !== null) return; // one save at a time
                if (wall && wall.contentType === type) return; // already there
                saveSceneContent(type);
            });
        }

        /* Still image: inventory refresh, asset selection, and the one
         * explicit scene action. None of these send anything by themselves —
         * the apply button is what reaches PUT /scene, and only with a
         * selection in hand. */
        if (el.btnAssetsRefresh) {
            el.btnAssetsRefresh.addEventListener("click", function () {
                refreshAssets(false);
            });
        }

        if (el.assetList) {
            el.assetList.addEventListener("click", function (event) {
                const row = event.target.closest("button[data-asset]");
                if (!row || row.disabled) return;
                selectAsset(row.dataset.asset);
            });
        }

        if (el.mediaList) {
            el.mediaList.addEventListener("click", function (event) {
                const row = event.target.closest("button[data-media]");
                if (!row || row.disabled) return;
                selectAsset(row.dataset.media);
            });
        }

        if (el.uploadFile) {
            el.uploadFile.addEventListener("change", function () {
                const file = selectedUploadFile();
                if (el.uploadFileName) {
                    el.uploadFileName.textContent = file ? file.name : "No file chosen";
                }
                if (!uploadBusy) setUploadStatus(null);
                renderUploadControls();
            });
        }

        if (el.btnUpload) {
            el.btnUpload.addEventListener("click", startUpload);
        }

        if (el.btnImageApply) {
            el.btnImageApply.addEventListener("click", function () {
                applyImageScene();
            });
        }

        // Recovery from a missing asset: pick a replacement, or fall back to
        // a content type the wall can always render.
        if (el.btnMissingPick) {
            el.btnMissingPick.addEventListener("click", function () {
                if (el.btnMissingPick.dataset.mode === "refresh") refreshAssets(false);
                else focusAssetPicker();
            });
        }

        if (el.imageMissing) {
            el.imageMissing.addEventListener("click", function (event) {
                const button = event.target.closest("button[data-content-action]");
                if (!button || button.disabled) return;
                const type = button.dataset.contentAction;
                if (!isSettableContent(type)) return;
                if (pendingContent !== null) return;
                if (wall && wall.contentType === type) return;
                saveSceneContent(type);
            });
        }

        if (el.imagePreviewImg) {
            el.imagePreviewImg.addEventListener("error", function () {
                if (el.imagePreview) el.imagePreview.dataset.failed = "true";
                updateImageControls();
            });
        }

        // Vacant reservations: Release is a two-step confirm, like Forget.
        if (el.resList) {
            el.resList.addEventListener("click", function (event) {
                const button = event.target.closest("button[data-action]");
                if (!button || button.disabled) return;
                const row = button.closest(".res-row");
                if (!row) return;
                const id = row.dataset.res;

                switch (button.dataset.action) {
                    case "release":
                        beginRelease(id);
                        break;
                    case "release-cancel":
                        cancelRelease(id);
                        break;
                    case "release-confirm":
                        releasePlacement(id);
                        break;
                    default:
                        break;
                }
            });
        }

        el.btnAuto.addEventListener("click", arrangeWall);

        /* Saved layouts and scenes (Phase 2c) — two independent panels.
         * Each keeps its own name input, list, and confirm states; the only
         * thing they share is this wiring. */
        for (const kind of ["layout", "scene"]) {
            (function (kind) {
                const refs = snapRefs(kind);

                if (refs.form) {
                    refs.form.addEventListener("submit", function (event) {
                        event.preventDefault();
                        saveSnapshot(kind);
                    });
                }

                if (refs.refresh) {
                    refs.refresh.addEventListener("click", function () {
                        refreshSnapshots(kind, false);
                    });
                }

                if (refs.list) {
                    refs.list.addEventListener("click", function (event) {
                        const button = event.target.closest("button[data-action]");
                        if (!button || button.disabled) return;
                        const row = button.closest(".snap-row");
                        if (!row) return;
                        const name = row.dataset.name;
                        if (typeof name !== "string" || name === "") return;

                        switch (button.dataset.action) {
                            case "snap-recall":
                                beginSnapshotRecall(kind, name);
                                break;
                            case "snap-recall-confirm":
                                recallSnapshot(kind, name);
                                break;
                            case "snap-delete":
                                beginSnapshotDelete(kind, name);
                                break;
                            case "snap-delete-confirm":
                                deleteSnapshot(kind, name);
                                break;
                            case "snap-confirm-cancel": {
                                // Both a click and an expired confirmation
                                // return focus to the row action if it still
                                // owned focus; neither strands the keyboard
                                // operator on <body>.
                                cancelSnapshotConfirm(kind);
                                break;
                            }
                            default:
                                break;
                        }
                    });
                }

                if (refs.overwriteYes) {
                    refs.overwriteYes.addEventListener("click", function () {
                        replaceSnapshot(kind);
                    });
                }
                if (refs.overwriteNo) {
                    refs.overwriteNo.addEventListener("click", function () {
                        cancelSnapshotOverwrite(kind);
                    });
                }
            })(kind);
        }

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
            // Disabled while no URL is known — guard anyway, so a stale or
            // synthetic click can never put the status text on the clipboard.
            if (tabletUrl === null) return;
            // navigator.clipboard is secure-context only — guard it.
            if (window.isSecureContext && navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(tabletUrl).then(
                    function () { logStatus("Tablet address copied.", "ok"); },
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
        logStatus("Copying is blocked here. Press Ctrl+C or Cmd+C to copy the highlighted address.", "info");
    }

    /* ------------------------------------------------------------------ *
     * Tablet URL — GET /operator-config, one read at boot, never polled
     *
      * The device stage always shows — and copies — the address a tablet should
     * open. That address is NOT always this page's own origin: the
     * operator page and the tablets can be served from two different
     * origins, and the server is the one that knows which. Contract:
     *
      *     { "tablet_origin": "https://<tablet-host>" }
     *     { "tablet_origin": null }   → not configured
     *
     * A configured origin is used verbatim (after validation); `null`
     * falls back to the single-origin dev default, location.origin plus
     * "/client/". Everything else — a failed read, a non-object answer, a
     * missing key, a malformed or unsafe value — leaves the address
     * unavailable and Copy disabled. Guessing `location` in those cases
     * could hand the operator a URL pointing at the wrong host in a
     * two-origin deployment, and a wrong URL is worse than none.
     * ------------------------------------------------------------------ */

    /** The dev default: this page's own origin plus the client path. */
    function devTabletUrl() {
        return location.origin + "/" + CLIENT_PATH;
    }

    /**
     * Validate a configured `tablet_origin` and turn it into the URL a
     * tablet should open. Returns null for anything malformed or unsafe:
     * a non-string, a blank value, embedded whitespace (URL parsing
     * silently strips tabs and newlines, which would change what is
     * opened), an over-long one, something `URL` cannot parse, a scheme
     * other than http(s), a host-less URL, embedded credentials, or a
     * query/fragment that would silently redirect the tablet elsewhere.
     *
      * The backend contract is a bare origin only ("https://<host>"). A
      * path, even "/client/", is a configuration error, never silently
      * transformed into another URL. Nothing bakes in a hostname — the host
      * comes from the server's answer.
     *
     * Whatever comes back reaches the DOM through `textContent` only.
     */
    function tabletUrlFromOrigin(raw) {
        if (typeof raw !== "string") return null;
        const value = raw;
        if (value === "" || value.length > 2048 || /\s/.test(value)) return null;

        let url;
        try {
            url = new URL(value);
        } catch (_err) {
            return null;
        }
        if (url.protocol !== "http:" && url.protocol !== "https:") return null;
        if (url.host === "") return null;
        if (url.username !== "" || url.password !== "") return null;
        if (url.search !== "" || url.hash !== "") return null;
        // URL parsing normalizes case, ports and trailing slashes. Refuse a
        // value it would rewrite, rather than hiding a misconfigured ingress.
        if (url.pathname !== "/" || url.origin !== value) return null;
        return value + "/" + CLIENT_PATH;
    }

    /** One boot-time read of the configured tablet origin. */
    async function fetchOperatorConfig() {
        try {
            const data = await requestJson("GET", "/operator-config");
            if (!data || typeof data !== "object" || Array.isArray(data)) {
                throw new Error("the answer was not an operator config");
            }
            if (!Object.prototype.hasOwnProperty.call(data, "tablet_origin")) {
                throw new Error("the answer carried no tablet_origin");
            }
            if (data.tablet_origin === null) {
                tabletUrl = devTabletUrl(); // not configured: single-origin dev
            } else {
                tabletUrl = tabletUrlFromOrigin(data.tablet_origin);
                if (tabletUrl === null) {
                    throw new Error("tablet_origin is not a usable http(s) URL");
                }
            }
            tabletUrlState = "ready";
            tabletUrlReason = null;
        } catch (err) {
            tabletUrl = null;
            tabletUrlState = "unavailable";
            const detail = err && typeof err.message === "string" ? err.message : "unknown error";
            // Server-supplied text is only ever assigned as text, and kept
            // short so the box stays readable.
            tabletUrlReason = detail.length > 90 ? detail.slice(0, 89) + "…" : detail;
            logStatus("Tablet address unavailable: " + tabletUrlReason + ".", "err");
        }
        renderTabletUrl();
    }

    /**
     * The URL box and its Copy button. Copy is enabled only once a
     * validated URL exists, so neither a click nor the keyboard can put an
     * unverified address — or the message explaining why there is none —
     * on the clipboard. All text goes through `textContent`.
     */
    function renderTabletUrl() {
        const node = el.clientUrl;
        const button = el.btnCopyUrl;
        if (tabletUrl !== null) {
            node.textContent = tabletUrl;
            node.dataset.state = "ready";
            button.disabled = false;
            button.title = "Copy the tablet URL to the clipboard";
            return;
        }
        button.disabled = true;
        node.dataset.state = tabletUrlState;
        if (tabletUrlState === "pending") {
            node.textContent = "Reading the address from the server…";
            button.title = "Waiting for GET /operator-config";
        } else {
            node.textContent = "Address unavailable: " + tabletUrlReason + ".";
            button.title = "The server's operator config could not be read";
        }
    }

    /* ------------------------------------------------------------------ *
     * Boot
     * ------------------------------------------------------------------ */

    /**
     * Seed the wall panel from `GET /wall` so the layout is visible before
     * the roster socket has delivered a snapshot — or while it is down.
     *
     * It is authoritative only while we hold nothing: a snapshot or a
     * `wall_updated` arriving first always wins, and a failure (server down,
     * older server without the route) is not worth reporting — the snapshot
     * will bring the state anyway.
     */
    function fetchWallState() {
        requestJson("GET", "/wall")
            .then(function (data) {
                if (wall) return; // the socket already delivered one
                const next = normalizeWall(data);
                if (!next) return;
                wall = next;
                renderWall();
            })
            .catch(function () {
                /* unreachable or not implemented yet — wait for the snapshot */
            });
    }

    function init() {
        buildGlobalPalette();
        bindEvents();
        // Pending until GET /operator-config answers: no URL is guessed here.
        renderTabletUrl();
        renderConn();
        renderEmpty();
        renderWall(); // wall is null here: disables the panel, notes the wait
        renderSnapshotPanel("layout");
        renderSnapshotPanel("scene");
        logStatus("Connecting to " + wsUrl() + " …", "info");
        fetchWallState();
        // The tablet address comes from the server. It is read alongside the
        // other boot reads; a failure says so in the URL box and leaves Copy
        // disabled rather than falling back to this page's own origin.
        fetchOperatorConfig();
        // Quiet: a server without GET /assets (or with an empty directory) is
        // a fact to note, not a failure to shout about at startup.
        refreshAssets(true);
        // GET /media is the managed library; a 403 means uploads are off, so
        // the upload controls stay hidden and the curated flow is unchanged.
        refreshMedia(true);
        // Same for the named snapshots: a server that has not grown the
        // /layouts and /scenes routes yet says so inside each panel instead
        // of shouting over the connection status at boot.
        refreshSnapshots("layout", true);
        refreshSnapshots("scene", true);
        connect();
        setInterval(tick, 1000);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
