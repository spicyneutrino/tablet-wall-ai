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

    /* Placement inputs per tile: the footprint first, then the bezel. */
    const PLACE_FIELDS = [
        "x", "y", "w", "h",
        "bezel-top", "bezel-right", "bezel-bottom", "bezel-left"
    ];

    /* Preview map frame, in CSS pixels. The wall rectangle keeps its aspect
     * ratio inside these bounds; extreme walls scroll in the viewport. */
    const MAP_MAX_H = 560;
    const DEVICE_TYPE_NAMES = { ipad: "iPad", iphone: "iPhone", android: "Android" };
    const MAP_MIN_H = 120;
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
        btnWallSizeSettings: document.getElementById("btn-wall-size-settings"),
        btnFitWallTablets: document.getElementById("btn-fit-wall-tablets"),
        wallForm: document.getElementById("wall-form"),
        wallWidth: document.getElementById("wall-width"),
        wallHeight: document.getElementById("wall-height"),
        wallSizingMode: document.getElementById("wall-sizing-mode"),
        wallPadding: document.getElementById("wall-padding"),
        wallSizingHelp: document.getElementById("wall-sizing-help"),
        packColumns: document.getElementById("pack-columns"),
        packGap: document.getElementById("pack-gap"),
        packControls: document.getElementById("pack-controls"),
        btnPack: document.getElementById("btn-pack"),
        packStatus: document.getElementById("pack-status"),
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
        clientUrlLabel: document.getElementById("client-url-label"),
        btnCopyUrl: document.getElementById("btn-copy-url"),
        statusStamp: document.getElementById("status-stamp"),
        statusText: document.getElementById("status-text"),
        tileTpl: document.getElementById("tile-tpl")
    };

    /* Stage controls: the wall-first editor around the existing data layer. */
    const stage = {
        app: document.getElementById("app"),
        context: document.getElementById("context"),
        paneTablet: document.getElementById("pane-tablet"),
        paneContent: document.getElementById("pane-content"),
        paneLayout: document.getElementById("pane-layout"),
        contextTabs: Array.from(document.querySelectorAll("[data-context-tab]")),
        mobileTabs: Array.from(document.querySelectorAll(".mobile-nav [data-task]")),
        inspectorEmpty: document.getElementById("inspector-empty"),
        inspector: document.getElementById("inspector"),
        inspId: document.getElementById("insp-id"),
        inspEyebrow: document.getElementById("insp-eyebrow"),
        inspMeta: document.getElementById("insp-meta"),
        inspStateOnline: document.getElementById("insp-state-online"),
        inspStatePlacement: document.getElementById("insp-state-placement"),
        inspRemove: document.getElementById("insp-remove"),
        inspRemoveBottom: document.getElementById("insp-remove-bottom"),
        inspPlace: document.getElementById("insp-place"),
        inspX: document.getElementById("insp-x"),
        inspY: document.getElementById("insp-y"),
        inspW: document.getElementById("insp-w"),
        inspH: document.getElementById("insp-h"),
        inspLock: document.getElementById("insp-lock"),
        inspSave: document.getElementById("insp-save"),
        inspError: document.getElementById("insp-error"),
        inspShape: document.getElementById("insp-shape"),
        inspWarning: document.getElementById("insp-warning"),
        inspWarningText: document.getElementById("insp-warning-text"),
        inspMatch: document.getElementById("insp-match"),
        inspStep: document.getElementById("insp-step"),
        inspStepDesktop: document.getElementById("insp-step-desktop"),
        inspBezelTop: document.getElementById("insp-bezel-top"),
        inspBezelRight: document.getElementById("insp-bezel-right"),
        inspBezelBottom: document.getElementById("insp-bezel-bottom"),
        inspBezelLeft: document.getElementById("insp-bezel-left"),
        inspBezelSummary: document.getElementById("insp-bezel-summary"),
        inspPalette: document.getElementById("insp-palette"),
        inspColor: document.getElementById("insp-color"),
        inspColorText: document.getElementById("insp-color-text"),
        inspColourSummary: document.getElementById("insp-colour-summary"),
        inspDetailId: document.getElementById("insp-detail-id"),
        inspDetailType: document.getElementById("insp-detail-type"),
        inspDetailScreen: document.getElementById("insp-detail-screen"),
        inspDetailImage: document.getElementById("insp-detail-image"),
        inspDetailSeen: document.getElementById("insp-detail-seen"),
        inspDetailPlacement: document.getElementById("insp-detail-placement"),
        inspForget: document.getElementById("insp-forget"),
        inspForgetHint: document.getElementById("insp-forget-hint"),
        inspRemoveArea: document.getElementById("insp-remove-area"),
        wallDimensions: document.getElementById("wall-dimensions"),
        actualCoverage: document.getElementById("actual-coverage"),
        wallWarnings: document.getElementById("wall-warnings"),
        wallWarningText: document.getElementById("wall-warning-text"),
        btnReviewChecks: document.getElementById("btn-review-checks"),
        stageReadout: document.getElementById("stage-readout"),
        rulerX: document.getElementById("ruler-x"),
        rulerY: document.getElementById("ruler-y"),
        wallScroll: document.getElementById("wall-scroll"),
        wallShell: document.getElementById("wall-shell"),
        mapViewport: document.getElementById("map-viewport"),
        mapFrame: document.getElementById("map-frame"),
        tileLayer: document.getElementById("tile-layer"),
        snapToggle: document.getElementById("snap-toggle"),
        snapStep: document.getElementById("snap-step"),
        btnUndoStage: document.getElementById("btn-undo-stage"),
        btnRedoStage: document.getElementById("btn-redo-stage"),
        btnZoomWall: document.getElementById("btn-zoom-wall"),
        btnKeys: document.getElementById("btn-keys"),
        keysDialog: document.getElementById("keys-dialog"),
        keysClose: document.getElementById("keys-close"),
        btnTile: document.getElementById("btn-tile"),
        tileSection: document.getElementById("tile-section"),
        tileScope: document.getElementById("tile-scope"),
        tileColumns: document.getElementById("tile-columns"),
        tileRows: document.getElementById("tile-rows"),
        tileGap: document.getElementById("tile-gap"),
        tileOrder: document.getElementById("tile-order"),
        tileShape: document.getElementById("tile-shape"),
        tileHelp: document.getElementById("tile-help"),
        tileResult: document.getElementById("tile-result"),
        tilePreviewBtn: document.getElementById("tile-preview-btn"),
        tileApply: document.getElementById("tile-apply"),
        tileWriteNote: document.getElementById("tile-write-note"),
        tileCancel: document.getElementById("tile-cancel"),
        btnChangeContent: document.getElementById("btn-change-content"),
        btnManageLayouts: document.getElementById("btn-manage-layouts"),
        layoutShortcuts: document.getElementById("layout-shortcuts"),
        statusUndo: document.getElementById("status-undo")
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
    let wallBusy = false;
    let packBusy = false;
    let packDefaultsMode = null;

    /** Scene content chosen in the control but not yet confirmed by the
     *  server's PUT /scene response (or its `wall_updated` echo). */
    let pendingContent = null;

    /* Which content panel is open in the operator's control. This is a view
     * state, not the wall: an operator can browse the image library while the
     * wall still shows colour, and the summary keeps the actual wall state
     * separate. */
    let contentView = null;

    /* Stage state: one selected device, one local placement history, and the
     * tiling preview. These are view/editor state, never a second source of
     * truth for the wall. */
    const editor = {
        selectedId: null,
        contextMode: "tablet",
        mobileTask: "wall",
        stageUndo: [],
        stageRedo: [],
        stageDrag: null,
        stageNudgeTimer: null,
        pendingNudge: null,
        stageJustDragged: false,
        stageHistoryGeneration: null,
        inspForgetPending: false,
        inspForgetTimer: null,
        tilePreviewPlan: null,
        tilePreviewSelected: [],
        tileApplying: false,
    };


    /* Curated asset inventory (GET /assets). Read once at boot and again only
     * when the operator asks — never polled. A failed refresh keeps the last
     * good list (`assetsError` says why it is stale); `assetsLoaded` gates
     * every claim this page makes about what is in the inventory, so "missing"
     * is never asserted from a read that never succeeded. */
    const inventory = {
        assets: [],
        assetsLoaded: false,
        assetsLoading: false,
        assetsError: null,
        assetsStamp: null, // clock stamp of the last successful read

    /** Asset picked in the list but not yet sent. null means no selection,
     *  and no image scene is ever sent without one. */
        selectedAsset: null,

    /* Managed uploads (GET /media) are a separate store from the curated
     * inventory, so they keep their own list. `mediaState` is "pending" |
     * "ready" | "forbidden" | "error": 403 means uploads are disabled, which
     * hides the upload controls and leaves the curated flow as it was. */
        mediaAssets: [],
        mediaState: "pending",
        mediaError: null,
        mediaLoading: false,

    /* One upload at a time. `uploadStage` is null | "uploading" |
     * "processing"; progress events drive the first, the upload `load`
     * event the second. */
        uploadXhr: null,
        uploadBusy: false,
        uploadStage: null,

    };

    /* Tablet URL (GET /operator-config, read once at boot). `tabletUrl` is
     * the validated address to show and copy, or null while none is known
     * or the answer could not be trusted. */
    let tabletUrl = null;
    let tabletUrlState = "pending"; // "pending" | "ready" | "local" | "unavailable"
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

    const { numOr, visibleRect, aspectOf, aspectDelta, isAspectMismatch, fmtAspect, fmtDelta, viewportAspect, deviceCaps, placementShapeMismatch, normalizePlacement, isSettableContent, sceneContentType, sceneContent, contentSummaryLabel, contentLabel, contentHint } = window.ControllerGeometry;

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
            sizing: window.ControllerGeometry.normalizeSizing(raw.sizing),
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

        socket.addEventListener("close", async function () {
            if (ws !== socket) return;
            ws = null;
            if (await compatibilityAllowed()) scheduleReconnect();
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

    function deviceHandle(device) {
        const number = Number(device && device.number);
        return Number.isInteger(number) && number > 0
            ? "Tablet #" + number
            : "Tablet " + shortId(device && device.device_id);
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
                if (msg.type === "device_online" && (!previous || previous.online !== true)) {
                    logStatus(deviceHandle(device) + " connected.", "ok");
                } else if (msg.type === "device_updated" && previous &&
                        Number(previous.number) !== Number(device.number)) {
                    logStatus(deviceHandle(device) + " is now " +
                        (Number(device.number) > 0 ? "#" + Number(device.number) : "un-numbered") +
                        ".", "info");
                }
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
                logStatus(deviceHandle(previous) + " disconnected.", "info");
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
                const removed = devices.get(id);
                if (!devices.delete(id)) return;
                logStatus(deviceHandle(removed) + " removed from the roster.", "info");
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
        renderSelection();
        renderWallSummary();
        renderLayoutShortcuts();
        renderStageHistory();
    }

    function createTile(id) {
        const node = el.tileTpl.content.firstElementChild.cloneNode(true);
        node.dataset.id = id;

        const tile = {
            el: node,
            number: node.querySelector(".tile-number"),
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
            location: node.querySelector(".tile-location"),
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

        node.draggable = true;
        node.addEventListener("click", function (event) {
            if (event.target.closest("button, input, summary, details, a")) return;
            selectDevice(id, { focusTile: false });
        });
        node.addEventListener("keydown", function (event) {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                selectDevice(id, { focusTile: false });
                return;
            }
            if (event.key === "Delete" || event.key === "Backspace") {
                if (!savedPlacement(id)) return;
                event.preventDefault();
                removeSelected();
            }
        });
        node.addEventListener("dragstart", function (event) {
            if (!event.dataTransfer) return;
            event.dataTransfer.effectAllowed = "move";
            event.dataTransfer.setData("text/plain", id);
            node.dataset.dragging = "true";
        });
        node.addEventListener("dragend", function () {
            node.dataset.dragging = "false";
            if (stage.mapFrame) stage.mapFrame.classList.remove("drop-ready");
        });

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
        if (tile.number) {
            const number = Number(device.number);
            const hasNumber = Number.isInteger(number) && number > 0;
            tile.number.hidden = !hasNumber;
            tile.number.textContent = hasNumber ? "#" + number : "";
            tile.number.title = hasNumber ? "Tablet number " + number : "";
        }

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
        paintTileScreen(tile, device);
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
        if (wall && editor.stageHistoryGeneration !== null &&
                wall.generation !== editor.stageHistoryGeneration) {
            editor.stageUndo = [];
            editor.stageRedo = [];
            editor.stageHistoryGeneration = null;
            renderStageHistory();
        }

        if (stage.wallDimensions) {
            stage.wallDimensions.textContent = wall
                ? wall.width + " × " + wall.height + " units · " +
                    (wall.sizing.mode === "tablets" ? "Fits tablets" : "Fixed size")
                : "Waiting for the server";
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
            if (el.wallSizingMode) el.wallSizingMode.value = wall.sizing.mode;
            if (el.wallPadding) el.wallPadding.value = String(wall.sizing.padding);
        }
        renderWallSizingControls();
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
                paintTileScreen(tile, device);
            }
        }

        renderSelection();
        renderWallSummary();
        renderLayoutShortcuts();
        renderStageHistory();
    }

    /** Counts that explain the wall without repeating every alert. */
    function renderWallSummary() {
        if (!stage.actualCoverage) return;
        if (!wallReady()) {
            stage.actualCoverage.textContent = wall
                ? "Set a wall width and height to arrange tablets."
                : "Waiting for the wall state.";
            if (stage.wallWarnings) stage.wallWarnings.hidden = true;
            return;
        }

        let placed = 0;
        let offline = 0;
        let imageUnknown = 0;
        let imageUnsupported = 0;
        let shapeMismatch = 0;
        for (const id of Object.keys(wall.placements)) {
            const placement = wall.placements[id];
            const device = devices.get(id);
            if (!device) continue;
            placed += 1;
            if (device.online !== true) offline += 1;
            const caps = deviceCaps(device);
            if (caps.image === false) imageUnsupported += 1;
            else if (caps.image !== true) imageUnknown += 1;
            if (placementShapeMismatch(placement, device)) shapeMismatch += 1;
        }
        const unplaced = Math.max(0, devices.size - placed);
        const vacant = vacantIds().length;

        const bits = [];
        if (placed > 0) bits.push(placed + " placed");
        if (unplaced > 0) bits.push(unplaced + " not placed");
        if (offline > 0) bits.push(offline + " offline");
        if (vacant > 0) bits.push(vacant + (vacant === 1 ? " saved spot" : " saved spots"));
        stage.actualCoverage.textContent = bits.length
            ? bits.join(" · ")
            : "No tablets are placed yet.";

        const warnBits = [];
        if (shapeMismatch > 0) {
            warnBits.push(shapeMismatch + (shapeMismatch === 1 ? " screen shape differs" : " screen shapes differ"));
        }
        if (imageUnsupported > 0 && wall.contentType === "image") {
            warnBits.push(imageUnsupported + (imageUnsupported === 1
                ? " tablet cannot show the image" : " tablets cannot show the image"));
        }
        if (imageUnknown > 0 && wall.contentType === "image") {
            warnBits.push(imageUnknown + (imageUnknown === 1
                ? " tablet cannot confirm the image" : " tablets cannot confirm the image"));
        }
        if (vacant > 0) {
            warnBits.push(vacant + (vacant === 1 ? " saved spot is retained" : " saved spots are retained"));
        }
        if (warnBits.length && stage.wallWarnings && stage.wallWarningText) {
            stage.wallWarnings.hidden = false;
            stage.wallWarningText.textContent = warnBits.join(". ") + ".";
            const hasAlerts = !!(el.alerts &&
                el.alerts.querySelector(".alert:not([hidden])"));
            if (stage.btnReviewChecks) stage.btnReviewChecks.hidden = !hasAlerts;
        } else if (stage.wallWarnings) {
            stage.wallWarnings.hidden = true;
            if (stage.btnReviewChecks) stage.btnReviewChecks.hidden = true;
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
                ? "Calibration grid is on the wall. Each tablet shows its number; the roster and map use the same number."
                : "Choose Calibration to show the shared grid and each tablet number.";
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
        const fitted = wall && wall.sizing.mode === "tablets";
        el.wallWidth.disabled = !on;
        el.wallHeight.disabled = !on;
        el.wallSizingMode.disabled = !on || wallBusy;
        el.wallPadding.disabled = !on || wallBusy;
        el.btnWallSave.disabled = !on || wallBusy;
        el.autoColumns.disabled = !on || fitted;
        el.btnAuto.disabled = !on || fitted;
        el.btnAuto.title = fitted ? "Use Pack placed tablets while fitting the wall." : "";
        if (!el.wallContent) return;
        for (const button of el.wallContent.querySelectorAll(".seg-opt")) {
            button.disabled = !on;
        }
    }

    function renderWallSizingControls() {
        if (!el.wallSizingMode || !wall) return;
        const tabletsMode = el.wallSizingMode.value === "tablets";
        el.wallWidth.readOnly = tabletsMode;
        el.wallHeight.readOnly = tabletsMode;
        el.btnWallSave.textContent = tabletsMode ? "Save sizing" : "Save size";
        el.btnWallSave.disabled = wallBusy || !wallReady();
        if (el.btnFitWallTablets) {
            const alreadyFitted = wall.sizing.mode === "tablets" && wall.sizing.padding === 0;
            el.btnFitWallTablets.disabled = wallBusy || !wallReady() || alreadyFitted;
        }
        const placedCount = Object.keys(wall.placements || {}).length;
        if (el.wallPadding && el.wallPadding.closest) {
            const field = el.wallPadding.closest("label");
            if (field) field.hidden = !tabletsMode;
        }
        if (el.packControls) el.packControls.hidden = !tabletsMode;
        if (el.wallSizingHelp) {
            el.wallSizingHelp.textContent = tabletsMode
                ? "The wall follows every placed footprint, including offline reservations. Dimensions update when placements change."
                : "Size changes keep each footprint at its current coordinates.";
        }
        if (tabletsMode && packDefaultsMode !== "tablets" && el.packColumns) {
            el.packColumns.value = String(Math.max(1, Math.ceil(Math.sqrt(placedCount || 1))));
        }
        packDefaultsMode = tabletsMode ? "tablets" : "fixed";
        if (el.btnPack) {
            el.btnPack.disabled = !tabletsMode || wall.sizing.mode !== "tablets"
                || wallDirty || !placedCount || packBusy || wallBusy;
        }
        if (el.packStatus && tabletsMode && wallDirty) {
            el.packStatus.textContent = "Save sizing before packing.";
        } else if (el.packStatus && el.packStatus.textContent === "Save sizing before packing.") {
            el.packStatus.textContent = "";
        }
        if (el.packColumns) el.packColumns.disabled = !tabletsMode || !placedCount || packBusy || wallBusy;
        if (el.packGap) el.packGap.disabled = !tabletsMode || !placedCount || packBusy || wallBusy;
        renderStageHistory();
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
    const {
        activeImageId, applyImageScene, assetById, focusAssetPicker, refreshAssets, refreshMedia, renderImagePanel, renderUploadControls, selectAsset, selectedUploadFile, setUploadStatus, shortAsset, startUpload, updateImageControls
    } = window.ControllerInventory.create({
        PROTOCOL, aspectOf, clockStamp, compareIds, contentLabel, el, fmtAspect, inventory, logStatus, normalizeWall, renderWall, renderWallContent, renderWallMap, requestJson, wallReady,
        runtime: {
            get wall() { return wall; }, set wall(value) { wall = value; },
            get pendingContent() { return pendingContent; }, set pendingContent(value) { pendingContent = value; },
            get contentView() { return contentView; }, set contentView(value) { contentView = value; },
        }
    });

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
            const hasImage = (device.protocol === 2 || device.protocol === 3) && caps.indexOf("image") !== -1;
            const lacksImage = device.protocol === 1 ||
                ((device.protocol === 2 || device.protocol === 3) && capsKnown && !hasImage);
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
     * succeeded. Missing `caps` remain unknown; a reported list without
     * `image` means no image support.
     */
    function renderCapChip(tile, device) {
        if (!tile.capChip) return;
        const show = !!wall && wall.contentType === "image";
        tile.capChip.hidden = !show;
        if (tile.capSep) tile.capSep.hidden = !show;
        if (!show) return;

        const capsKnown = Array.isArray(device.caps);
        const caps = capsKnown ? device.caps : [];
        const hasImage = (device.protocol === 2 || device.protocol === 3) && caps.indexOf("image") !== -1;
        const lacksImage = device.protocol === 1 ||
            ((device.protocol === 2 || device.protocol === 3) && capsKnown && !hasImage);
        const online = device.online === true;

        let kind;
        let text;
        if (online && hasImage) {
            kind = "ok";
            text = "Image capable";
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
            text = "Image capable";
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
        const focusedId = document.activeElement &&
            document.activeElement.classList &&
            document.activeElement.classList.contains("map-pl")
            ? document.activeElement.dataset.id : null;
        for (const node of Array.from(frame.querySelectorAll(".map-pl, .map-none"))) {
            node.remove();
        }

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

        renderRulers(wallW, wallH);
        updateStageReadout();

        if (focusedId) {
            const again = frame.querySelector('.map-pl[data-id="' + cssEscape(focusedId) + '"]');
            if (again) again.focus({ preventScroll: true });
        }
        if (editor.tilePreviewPlan) renderTilePreviewOnWall();
        for (const tile of tiles.values()) {
            const device = devices.get(tile.el.dataset.id);
            if (device) paintTileScreen(tile, device);
        }
    }

    function cssEscape(value) {
        if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(value);
        return String(value).replace(/["\\]/g, "\\$&");
    }

    function renderRulers(wallW, wallH) {
        if (!stage.rulerX || !stage.rulerY) return;
        stage.rulerX.textContent = "";
        stage.rulerY.textContent = "";
        for (let i = 0; i <= 4; i += 1) {
            const x = document.createElement("span");
            x.textContent = String(Math.round(wallW * i / 4));
            stage.rulerX.appendChild(x);
            const y = document.createElement("span");
            y.textContent = String(Math.round(wallH * i / 4));
            stage.rulerY.appendChild(y);
        }
    }

    function updateStageReadout() {
        if (!stage.stageReadout) return;
        if (!wallReady()) {
            stage.stageReadout.textContent = "Waiting for the wall state.";
            return;
        }
        if (!editor.selectedId || !wall.placements[editor.selectedId]) {
            stage.stageReadout.textContent = editor.selectedId
                ? shortId(editor.selectedId) + " is not on the wall."
                : "Select a tablet to see its footprint.";
            return;
        }
        const p = wall.placements[editor.selectedId];
        stage.stageReadout.textContent =
            shortId(editor.selectedId) + "  X " + fmtNumber(p.x) + "  Y " + fmtNumber(p.y) +
            "  W " + fmtNumber(p.w) + "  H " + fmtNumber(p.h);
    }

    function fmtNumber(n) {
        return Number.isFinite(Number(n)) ? String(Math.round(Number(n) * 100) / 100) : "-";
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
        const calibration = !!(device && wall && wall.contentType === "calibration");
        const number = device ? Number(device.number) : NaN;
        const hasNumber = Number.isInteger(number) && number > 0;

        const box = document.createElement("button");
        box.type = "button";
        box.className = "map-pl";
        box.dataset.id = id;
        box.dataset.selected = editor.selectedId === id ? "true" : "false";
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
                if (editor.stageJustDragged) {
                    editor.stageJustDragged = false;
                    return;
                }
                selectDevice(id, { focusTile: true });
            });
            box.addEventListener("pointerdown", function (event) {
                startStageDrag(event, id, box, "move");
            });
            box.addEventListener("keydown", function (event) {
                if (event.key === "Delete" || event.key === "Backspace") {
                    event.preventDefault();
                    event.stopPropagation();
                    selectDevice(id, { focusTile: false });
                    removeSelected();
                    return;
                }
                if (event.key === "Escape" && editor.stageDrag) {
                    event.preventDefault();
                    event.stopPropagation();
                    cancelStageDrag();
                    return;
                }
                if (event.key === "ArrowLeft" || event.key === "ArrowRight" ||
                        event.key === "ArrowUp" || event.key === "ArrowDown") {
                    event.preventDefault();
                    event.stopPropagation();
                    const step = event.shiftKey ? 10 : 1;
                    const dx = event.key === "ArrowLeft" ? -step :
                        event.key === "ArrowRight" ? step : 0;
                    const dy = event.key === "ArrowUp" ? -step :
                        event.key === "ArrowDown" ? step : 0;
                    nudgeSelected(dx, dy);
                }
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
            label.textContent = hasNumber
                ? "#" + number + " " + shortId(id)
                : shortId(id);
            if (calibration) label.hidden = true;
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
            } else if (calibration) {
                const sub = document.createElement("span");
                sub.className = "map-sub";
                sub.textContent = shortId(id);
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
        } else if (device && wall && wall.contentType === "image") {
            paintMapSlice(inset, visible, wallW, wallH, pxW, pxH);
        } else if (calibration) {
            paintCalibrationSlice(inset, visible, wallW, wallH, pxW, pxH);
            if (hasNumber) {
                const badge = document.createElement("span");
                badge.className = "map-number";
                badge.textContent = "#" + number;
                badge.style.setProperty(
                    "--number-fs",
                    Math.max(14, Math.min(42, Math.round(room / 3))) + "px"
                );
                inset.appendChild(badge);
            }
        }

        box.appendChild(inset);

        if (device && editor.selectedId === id) {
            for (const corner of ["nw", "ne", "sw", "se"]) {
                const handle = document.createElement("span");
                handle.className = "map-handle";
                handle.dataset.handle = corner;
                handle.setAttribute("aria-hidden", "true");
                handle.addEventListener("pointerdown", function (event) {
                    event.stopPropagation();
                    startStageDrag(event, id, box, "resize", corner);
                });
                box.appendChild(handle);
            }
        }
        return box;
    }

    /** Paint the logical wall image through one visible rectangle. */
    function paintMapSlice(inset, visible, wallW, wallH, pxW, pxH) {
        const id = activeImageId();
        const asset = id ? assetById(id) : null;
        if (!asset || !asset.url) return;
        const imgW = Number(asset.width);
        const imgH = Number(asset.height);
        if (!(imgW > 0) || !(imgH > 0)) return;
        /* The image covers the whole wall, centered. Its top-left in the map
         * frame is (offX, offY); the inset begins at the visible rect. */
        const scale = Math.max(pxW / imgW, pxH / imgH);
        const drawW = imgW * scale;
        const drawH = imgH * scale;
        const offX = (pxW - drawW) / 2;
        const offY = (pxH - drawH) / 2;
        inset.style.backgroundImage = 'url("' + asset.url.replace(/"/g, '\\"') + '")';
        inset.style.backgroundRepeat = "no-repeat";
        inset.style.backgroundSize = drawW + "px " + drawH + "px";
        inset.style.backgroundPosition =
            (offX - (visible.x / wallW) * pxW) + "px " +
            (offY - (visible.y / wallH) * pxH) + "px";
    }

    /**
     * Paint the shared calibration grid through one visible rect. The grid
     * is in wall units, so adjacent footprints line up exactly as the
     * tablets do. The number is a separate screen-space badge on the tablet;
     * on the map it is a large centred mark.
     */
    function paintCalibrationSlice(inset, visible, wallW, wallH, pxW, pxH) {
        const gx = (100 / wallW) * pxW;
        const gy = (100 / wallH) * pxH;
        const mx = (500 / wallW) * pxW;
        const my = (500 / wallH) * pxH;
        const posX = -(visible.x / wallW) * pxW;
        const posY = -(visible.y / wallH) * pxH;
        inset.style.backgroundColor = "#0b1120";
        inset.style.backgroundImage = [
            "linear-gradient(to right, rgba(148, 163, 184, 0.3) 1px, transparent 1px)",
            "linear-gradient(to bottom, rgba(148, 163, 184, 0.3) 1px, transparent 1px)",
            "linear-gradient(to right, rgba(226, 232, 240, 0.7) 1px, transparent 1px)",
            "linear-gradient(to bottom, rgba(226, 232, 240, 0.7) 1px, transparent 1px)"
        ].join(", ");
        inset.style.backgroundSize = [
            gx + "px " + gy + "px",
            gx + "px " + gy + "px",
            mx + "px " + my + "px",
            mx + "px " + my + "px"
        ].join(", ");
        inset.style.backgroundPosition = [
            posX + "px " + posY + "px",
            posX + "px " + posY + "px",
            posX + "px " + posY + "px",
            posX + "px " + posY + "px"
        ].join(", ");
        inset.style.backgroundRepeat = "repeat";
        inset.dataset.calibration = "true";
    }

    /** Paint a roster thumbnail from the same wall image and placement. */
    function paintTileScreen(tile, device) {
        if (!tile || !tile.screenFill) return;
        tile.screenFill.style.backgroundImage = "";
        tile.screenFill.style.backgroundRepeat = "";
        tile.screenFill.style.backgroundSize = "";
        tile.screenFill.style.backgroundPosition = "";
        if (!wall || wall.contentType !== "image") return;
        const id = activeImageId();
        const asset = id ? assetById(id) : null;
        const placement = savedPlacement(device.device_id);
        if (!asset || !asset.url || !placement) return;
        const imgW = Number(asset.width);
        const imgH = Number(asset.height);
        const visible = visibleRect(placement);
        const box = tile.screenFill.parentElement;
        const boxW = box && box.clientWidth > 0 ? box.clientWidth : 32;
        const boxH = box && box.clientHeight > 0 ? box.clientHeight : 22;
        if (!(imgW > 0) || !(imgH > 0) || !(wall.width > 0) || !(wall.height > 0)) return;
        /* First cover the visible rect into the thumbnail, then cover the
         * image to that virtual wall. The two stages match the tablet's
         * viewport crop rather than a shrunken copy of the whole wall. */
        const s = Math.max(boxW / visible.w, boxH / visible.h);
        const wallPxW = wall.width * s;
        const wallPxH = wall.height * s;
        const c = Math.max(wallPxW / imgW, wallPxH / imgH);
        const drawW = imgW * c;
        const drawH = imgH * c;
        const offX = (wallPxW - drawW) / 2;
        const offY = (wallPxH - drawH) / 2;
        const centerX = (boxW - visible.w * s) / 2;
        const centerY = (boxH - visible.h * s) / 2;
        tile.screenFill.style.background = "transparent";
        tile.screenFill.style.backgroundImage = 'url("' + asset.url.replace(/"/g, '\\"') + '")';
        tile.screenFill.style.backgroundRepeat = "no-repeat";
        tile.screenFill.style.backgroundSize = drawW + "px " + drawH + "px";
        tile.screenFill.style.backgroundPosition =
            (offX - visible.x * s + centerX) + "px " +
            (offY - visible.y * s + centerY) + "px";
        tile.screenNote.hidden = true;
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
        tile.el.dataset.placement = saved ? "placed" : "unplaced";
        if (tile.location) tile.location.textContent = saved ? "On the wall" : "Not placed";
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

    async function requestJson(method, path, body, ifMatch) {
        const options = { method: method, headers: {} };
        if (ifMatch) options.headers["If-Match"] = ifMatch;
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
        if (wallBusy) return;
        const mode = el.wallSizingMode.value === "tablets" ? "tablets" : "fixed";
        const padding = Number(el.wallPadding.value);
        const width = Number(el.wallWidth.value);
        const height = Number(el.wallHeight.value);
        if (!Number.isInteger(padding) || padding < 0) {
            logStatus("Wall margin must be a non-negative whole number.", "err");
            return;
        }
        if (mode === "fixed" && (!Number.isInteger(width) || width < 1 || !Number.isInteger(height) || height < 1)) {
            logStatus("Wall width and height must be positive whole numbers.", "err");
            return;
        }
        // Layout only: scene content goes to PUT /scene (see below), so the
        // two never share a request (PROTOCOL.md "Wall state").
        wallBusy = true;
        renderWallSizingControls();
        try {
            const body = { sizing: { mode: mode, padding: padding } };
            if (mode === "fixed") {
                body.width = width;
                body.height = height;
            }
            const previousWall = wall;
            const data = await requestJson("PUT", "/wall", body);
            const next = normalizeWall(data);
            if (next && next.width > 0 && next.height > 0) {
                adoptWallState(next);
            } else if (wall === previousWall) {
                // Something other than a wall state came back; keep the
                // operator's values and let `wall_updated` reconcile.
                wall = {
                    width: width,
                    height: height,
                    sizing: { mode: mode, padding: padding },
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
                (mode === "tablets" ? "Tablet-fit sizing saved: " : "Wall size saved: ") +
                    wall.width + " × " + wall.height + " (revision " + wall.revision + ").",
                "ok"
            );
        } catch (err) {
            logStatus("Could not save the wall size: " + err.message, "err");
        } finally {
            wallBusy = false;
            renderWall();
        }
    }

    function fitWallToTablets() {
        if (wallBusy || !wallReady()) return;
        el.wallSizingMode.value = "tablets";
        el.wallPadding.value = "0";
        wallDirty = false;
        renderWallSizingControls();
        saveWall();
    }

    function openWallSizeSettings() {
        const mobile = typeof window.matchMedia === "function" &&
            window.matchMedia("(max-width: 900px)").matches;
        const tab = mobile
            ? stage.mobileTabs.find(function (item) { return item.dataset.task === "saved"; })
            : stage.contextTabs.find(function (item) { return item.dataset.contextTab === "layout"; });
        if (tab) tab.click();
        if (el.wallSizingMode) el.wallSizingMode.focus();
    }

    async function packPlacedTablets() {
        if (packBusy || wallBusy || wallDirty || !wall || wall.sizing.mode !== "tablets" ||
                !Object.keys(wall.placements || {}).length) return;
        const columns = Number(el.packColumns.value);
        const gap = Number(el.packGap.value);
        if (!Number.isInteger(columns) || columns < 1 || !Number.isInteger(gap) || gap < 0) {
            logStatus("Pack columns must be positive and gap must be a non-negative whole number.", "err");
            return;
        }
        packBusy = true;
        if (el.packStatus) el.packStatus.textContent = "Packing placed tablets…";
        renderWallSizingControls();
        try {
            const next = normalizeWall(await requestJson("POST", "/wall/pack", { columns: columns, gap: gap }));
            if (!next || !next.width || !next.height) throw new Error("The server did not return a wall layout.");
            adoptWallState(next);
            wallDirty = false;
            if (el.packStatus) el.packStatus.textContent = "Placed tablets packed into " + columns + " columns.";
            renderWall();
            logStatus("Packed " + Object.keys(wall.placements).length + " placed tablets.", "ok");
        } catch (err) {
            if (el.packStatus) el.packStatus.textContent = "Pack failed: " + err.message;
            logStatus("Could not pack placed tablets: " + err.message, "err");
        } finally {
            packBusy = false;
            renderWallSizingControls();
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
            const data = await requestJson(
                "PUT",
                "/devices/" + encodeURIComponent(deviceId) + "/placement",
                placement
            );
            const next = normalizeWall(data);
            if (next && next.width > 0 && next.height > 0) {
                adoptWallState(next);
            } else if (wall) {
                // Older servers return an empty success; mirror the submitted
                // placement and let `wall_updated` supply any derived layout.
                const placements = Object.assign({}, wall.placements);
                placements[deviceId] = placement;
                wall.placements = placements;
            }
            tile.placeDirty = false;
            renderWall();
            logStatus("Position saved for tablet " + shortId(deviceId) + ".", "ok");
            return true;
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
            return false;
        } finally {
            if (tiles.get(deviceId) === tile) tile.el.dataset.busy = "false";
        }
    }

    async function clearPlacement(deviceId) {
        const tile = tiles.get(deviceId);
        if (!tile) return;

        tile.el.dataset.busy = "true";
        try {
            const data = await requestJson(
                "DELETE",
                "/devices/" + encodeURIComponent(deviceId) + "/placement"
            );
            const next = normalizeWall(data);
            if (next && next.width > 0 && next.height > 0) {
                adoptWallState(next);
            } else if (wall) {
                const placements = Object.assign({}, wall.placements);
                delete placements[deviceId];
                wall.placements = placements;
            }
            tile.placeDirty = false;
            renderWall();
            logStatus("Tablet " + shortId(deviceId) + " removed from the wall.", "ok");
            return true;
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
            return false;
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

    const {
        SNAPSHOTS, snapRefs, renderSnapshotAvailability, renderSnapshotPanel, refreshSnapshots, saveSnapshot, cancelSnapshotOverwrite, replaceSnapshot, beginSnapshotRecall, beginSnapshotDelete, cancelSnapshotConfirm, recallSnapshot, deleteSnapshot
    } = window.ControllerSnapshots.create({
        snapEl, wallReady, getWall: function () { return wall; }, shortAsset, requestJson, logStatus, adoptWallState, normalizeWall, refreshAssets, renderWall, renderLayoutShortcuts: function () { return renderLayoutShortcuts(); }, compareIds,
        syncRecalledLayout: function () {
            wallDirty = false;
            el.wallWidth.value = String(wall.width);
            el.wallHeight.value = String(wall.height);
        }
    });

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
        if (el.btnFitWallTablets) el.btnFitWallTablets.addEventListener("click", fitWallToTablets);
        if (el.btnWallSizeSettings) el.btnWallSizeSettings.addEventListener("click", openWallSizeSettings);

        const markWallDirty = function () {
            wallDirty = true;
            renderWallSizingControls();
        };
        el.wallWidth.addEventListener("input", markWallDirty);
        el.wallHeight.addEventListener("input", markWallDirty);
        el.wallSizingMode.addEventListener("change", function () {
            wallDirty = true;
            renderWallSizingControls();
        });
        el.wallPadding.addEventListener("input", function () {
            wallDirty = true;
            renderWallSizingControls();
        });
        el.btnPack.addEventListener("click", packPlacedTablets);

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
                if (!inventory.uploadBusy) setUploadStatus(null);
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
            if (tabletUrl === null || tabletUrlState !== "ready") return;
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
            tabletUrlState = window.ControllerUrl.isLoopbackOrigin(tabletUrl) ? "local" : "ready";
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
        if (tabletUrl !== null && tabletUrlState === "ready") {
            el.clientUrlLabel.textContent = "Tablet address";
            node.textContent = tabletUrl;
            node.dataset.state = "ready";
            button.disabled = false;
            button.title = "Copy the tablet URL to the clipboard";
            return;
        }
        button.disabled = true;
        node.dataset.state = tabletUrlState;
        if (tabletUrlState === "local") {
            el.clientUrlLabel.textContent = "This computer only";
            node.textContent = "Local testing only: " + tabletUrl;
            button.title = "This address only works on this computer. Start hotspot setup to get a tablet address.";
            return;
        }
        el.clientUrlLabel.textContent = "Tablet address";
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

    /* ------------------------------------------------------------------ *
     * Stage: selection, direct placement, tiling, undo, mobile tasks
     *
     * This layer extends the existing controller rather than replacing its
     * data path. The tile template stays the hidden source of exact fields,
     * so savePlacement() and the protocol handling keep working unchanged.
     * ------------------------------------------------------------------ */

    const {
        cancelStageDrag, initStage, nudgeSelected, removeSelected, renderLayoutShortcuts, renderSelection, renderStageHistory, renderTilePreviewOnWall, selectDevice, startStageDrag
    } = window.ControllerStage.create({
        DEVICE_TYPE_NAMES, PRESETS, SNAPSHOTS, aspectDelta, aspectOf, beginSnapshotRecall, clearPlacement, compareIds, cssEscape, deviceCaps, devices, editor, el, fmtAspect, fmtDelta, fmtNumber, focusTile, forgetDevice, isAspectMismatch, logStatus, normalizeColor, paintTileScreen, pct, placementProblem, placementShapeMismatch, renderWall, renderWallMap, requestJson, savePlacement, savedPlacement, seenLabel, setDeviceColor, shortId, stage, tiles, updateStageReadout, viewportAspect, visibleRect, wallReady,
        runtime: { get wall() { return wall; }, get tileOrder() { return tileOrder; } }
    });

    async function compatibilityAllowed() {
        const guard = document.getElementById("compatibility-guard");
        const app = document.getElementById("app");
        try {
            const config = await requestJson("GET", "/api/v3/config");
            if (config.layout && ["logical", undefined].includes(config.layout.kind)
                    && (config.operator_state_version === undefined || config.operator_state_version === 1)) { guard.hidden = true; app.hidden = false; return true; }
            document.getElementById("compatibility-guard-text").textContent = "This wall uses a measured layout. This compatibility editor is read-only. Open the Wall console to see the real arrangement and active content.";
        } catch (error) {
            document.getElementById("compatibility-guard-text").textContent = "The active layout could not be checked. " + error.message + ". Reload to retry, or open the Wall console. Editing is blocked until the layout kind is known.";
        }
        wall = null;
        app.hidden = true; guard.hidden = false;
        if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
        return false;
    }

    async function init() {
        if (!await compatibilityAllowed()) return;
        buildGlobalPalette();
        bindEvents();
        initStage();
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
