/*
 * tablet-wall client page.
 *
 * Runs full-screen on a wall-mounted tablet. Registers a device id with the
 * server, opens a device WebSocket at protocol version 2, heartbeats on the
 * interval the server asks for in its `welcome` frame, and paints the whole
 * viewport with any colour the server sends.
 *
 * As a version-2 client it also stores the `wall` frame's state — the wall's
 * dimensions, this device's placement, and `scene.content.type`. A frame whose
 * revision is not newer than the one already held is ignored, but ONLY while
 * the frame's `generation` is the one held: on a change of generation the
 * frame is accepted and the held revision is reset, because a restored or
 * rolled-back server may legitimately offer a lower revision than this tablet
 * has already seen (PROTOCOL.md "Revision and generation"). When the scene
 * content is `calibration`, it draws this device's slice of a calibration
 * pattern mapped from its visible rect (footprint minus bezel) onto the
 * viewport by covering.
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

    /* Protocol version 2 (wall/placement contract). `caps` advertises what
     * this client can render, so the server may send calibration content. */
    var PROTOCOL_VERSION = 2;
    var CAPS = "calibration";

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

    /* Calibration pattern geometry, in wall units. */
    var PATTERN_BLOCK = 1000; /* alternating tint block              */
    var PATTERN_GRID = 100; /* minor grid spacing                  */
    var PATTERN_GRID_MAJOR = 500; /* major grid and axis-label spacing   */
    var PX_MINOR_LINE = 1.5; /* minor grid weight, in CSS pixels    */
    var PX_MAJOR_LINE = 3.5; /* major grid / crosshair weight       */
    var PX_DIAGONAL = 5; /* diagonals weight                     */
    var PX_OWN_RECT = 6; /* own visible-rect outline weight      */

    /* System font stacks only: nothing may be fetched from a network. */
    var FONT_STACK =
        'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';

    /*
     * Dark, low-chroma palette: it sits next to (and briefly replaces) the
     * wall's own colour mode without clashing with it. Amber marks the
     * diagonals, cyan marks this device's own slice.
     */
    var PATTERN = {
        background: "#0b1120",
        blockTint: "rgba(148, 163, 184, 0.055)",
        gridMinor: "rgba(148, 163, 184, 0.3)",
        gridMajor: "rgba(226, 232, 240, 0.7)",
        axis: "rgba(226, 232, 240, 0.92)",
        diagonal: "#f59e0b",
        crosshair: "#e2e8f0",
        ownRect: "#22d3ee",
        labelBg: "rgba(2, 6, 23, 0.82)",
        info: "#e2e8f0",
        unplacedId: "#f8fafc",
        unplacedNote: "#f59e0b",
        unplacedHint: "#94a3b8",
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
                    // The viewport, not window.screen: this is the area the
                    // wall is actually mapped onto, and the controller compares
                    // it against the placement's visible rect to warn about
                    // cropping. Reporting the screen size makes that comparison
                    // wrong whenever browser chrome or a zoom level is in play.
                    width: window.innerWidth,
                    height: window.innerHeight,
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
    /* Wall state and rendering                                           */
    /* ------------------------------------------------------------------ */

    /*
     * Latest accepted `wall` frame, normalised to
     *   { width, height, contentType, revision, generation, placement,
     *     visible }
     * where `contentType` is `scene.content.type` ("color" or "calibration"),
     * `visible` is the placement's footprint shrunk by its bezel (or null
     * when this device has no usable placement), and `heldRevision` /
     * `heldGeneration` describe the state we hold: both null until the first
     * accepted frame.
     */
    var wallState = null;
    var heldRevision = null;
    var heldGeneration = null;

    var canvasEl = null;
    var canvasResolved = false;

    /* The canvas lives in index.html; create one if the markup is stale. */
    function ensureCanvas() {
        if (canvasResolved) return canvasEl;
        canvasResolved = true;
        canvasEl = document.getElementById("surface");
        if (canvasEl) return canvasEl;
        try {
            canvasEl = document.createElement("canvas");
            canvasEl.id = "surface";
            canvasEl.setAttribute("aria-hidden", "true");
            document.body.appendChild(canvasEl);
        } catch (err) {
            warn("wall surface unavailable", err);
            canvasEl = null;
        }
        if (!canvasEl) warn("wall rendering disabled: no canvas element");
        return canvasEl;
    }

    function showCanvas(show) {
        var el = ensureCanvas();
        if (el) el.style.display = show ? "block" : "none";
    }

    /* "Short id": the first UUID group, e.g. 0f8fad5b. */
    function shortDeviceId() {
        return String(deviceId).slice(0, 8);
    }

    /*
     * The visible rect is the footprint shrunk by the bezel:
     *   visible = { x + bezel.left, y + bezel.top,
     *               w - bezel.left - bezel.right,
     *               h - bezel.top  - bezel.bottom }
     * Returns null when the placement is absent/malformed or the bezel would
     * leave no positive area (the server rejects those with 422; this is the
     * client-side belt and braces).
     */
    function visibleRectOf(placement) {
        if (!placement || typeof placement !== "object") return null;
        var x = Number(placement.x);
        var y = Number(placement.y);
        var w = Number(placement.w);
        var h = Number(placement.h);
        if (
            !Number.isFinite(x) ||
            !Number.isFinite(y) ||
            !Number.isFinite(w) ||
            !Number.isFinite(h)
        ) {
            return null;
        }
        var bezel =
            placement.bezel && typeof placement.bezel === "object"
                ? placement.bezel
                : {};
        var left = Number(bezel.left);
        var right = Number(bezel.right);
        var top = Number(bezel.top);
        var bottom = Number(bezel.bottom);
        if (!Number.isFinite(left)) left = 0;
        if (!Number.isFinite(right)) right = 0;
        if (!Number.isFinite(top)) top = 0;
        if (!Number.isFinite(bottom)) bottom = 0;
        var visible = {
            x: x + left,
            y: y + top,
            w: w - left - right,
            h: h - top - bottom,
        };
        if (!(visible.w > 0) || !(visible.h > 0)) return null;
        return visible;
    }

    function viewportSize() {
        var w = Number(window.innerWidth);
        var h = Number(window.innerHeight);
        if (!(w > 0) || !(h > 0)) {
            var root = document.documentElement || {};
            w = Number(root.clientWidth);
            h = Number(root.clientHeight);
        }
        if (!(w > 0) || !(h > 0)) return null;
        return { w: w, h: h };
    }

    /* Sizes the backing store to CSS pixels x device pixel ratio so lines
     * stay crisp, and returns { ctx, dpr, w, h } or null. */
    function prepareCanvas(cssW, cssH) {
        var el = ensureCanvas();
        if (!el) return null;
        var dpr = Number(window.devicePixelRatio);
        if (!Number.isFinite(dpr) || dpr <= 0) dpr = 1;
        var bw = Math.max(1, Math.round(cssW * dpr));
        var bh = Math.max(1, Math.round(cssH * dpr));
        if (el.width !== bw) el.width = bw;
        if (el.height !== bh) el.height = bh;
        var ctx = null;
        try {
            ctx = el.getContext("2d");
        } catch (err) {
            warn("2d context unavailable", err);
            return null;
        }
        if (!ctx) {
            warn("2d context unavailable");
            return null;
        }
        return { ctx: ctx, dpr: dpr, w: cssW, h: cssH };
    }

    /* Single entry point for every state change that affects the screen. */
    function render() {
        if (!wallState) return; /* no wall frame yet: colour-only surface */
        if (wallState.contentType !== "calibration") {
            showCanvas(false); /* colour content: today's behaviour, untouched */
            return;
        }
        showCanvas(true);
        if (!wallState.visible) {
            drawUnplaced();
        } else {
            drawCalibration();
        }
    }

    function drawCalibration() {
        var vp = viewportSize();
        if (!vp) return;
        var view = prepareCanvas(vp.w, vp.h);
        if (!view) return;
        var visible = wallState.visible;

        /*
         * Cover: scale so the visible rect fills the viewport
         * (scale = max(vw / visible.w, vh / visible.h)), then translate so
         * the rect's top-left sits at the viewport origin. Anything outside
         * the rect falls outside the canvas and is cropped.
         */
        var scale = Math.max(vp.w / visible.w, vp.h / visible.h);
        if (!Number.isFinite(scale) || scale <= 0) return;
        var k = scale * view.dpr; /* wall unit -> device pixel */
        view.ctx.setTransform(k, 0, 0, k, -visible.x * k, -visible.y * k);
        drawPattern(view.ctx, scale, view.dpr, visible);
    }

    /*
     * Draws the WHOLE wall in wall coordinates; the transform above clips it
     * to this device's slice. Readable from a few metres away.
     */
    function drawPattern(ctx, scale, dpr, visible) {
        var W = wallState.width;
        var H = wallState.height;

        /* A screen-pixel width expressed in wall units, so line weights are
         * crisp and constant on screen whatever the mapping scale is. */
        function px(n) {
            return n / (scale * dpr);
        }

        /*
         * Label size derived from the visible rect: it lands between 5% of
         * the viewport width and 200 wall units, so it stays legible across
         * the room and never fills the 500-unit label spacing.
         */
        var font = Math.min(
            Math.max(Math.max(visible.w, visible.h) * 0.05, 20),
            200
        );
        var pad = font * 0.35;

        /* 1. filled background */
        ctx.fillStyle = PATTERN.background;
        ctx.fillRect(0, 0, W, H);

        /* 2. subtle alternating tint for each 1000x1000 block */
        ctx.fillStyle = PATTERN.blockTint;
        for (var bx = 0, ix = 0; bx < W; bx += PATTERN_BLOCK, ix++) {
            for (var by = 0, iy = 0; by < H; by += PATTERN_BLOCK, iy++) {
                if ((ix + iy) % 2 === 0) {
                    ctx.fillRect(
                        bx,
                        by,
                        Math.min(PATTERN_BLOCK, W - bx),
                        Math.min(PATTERN_BLOCK, H - by)
                    );
                }
            }
        }

        /* 3. grid lines every 100 wall units */
        ctx.strokeStyle = PATTERN.gridMinor;
        ctx.lineWidth = px(PX_MINOR_LINE);
        ctx.beginPath();
        for (var x = PATTERN_GRID; x < W; x += PATTERN_GRID) {
            if (x % PATTERN_GRID_MAJOR === 0) continue; /* heavier below */
            ctx.moveTo(x, 0);
            ctx.lineTo(x, H);
        }
        for (var y = PATTERN_GRID; y < H; y += PATTERN_GRID) {
            if (y % PATTERN_GRID_MAJOR === 0) continue;
            ctx.moveTo(0, y);
            ctx.lineTo(W, y);
        }
        ctx.stroke();

        /* 4. heavier lines every 500 units, plus the wall outline */
        ctx.strokeStyle = PATTERN.gridMajor;
        ctx.lineWidth = px(PX_MAJOR_LINE);
        ctx.beginPath();
        for (var mx = 0; mx <= W; mx += PATTERN_GRID_MAJOR) {
            ctx.moveTo(mx, 0);
            ctx.lineTo(mx, H);
        }
        for (var my = 0; my <= H; my += PATTERN_GRID_MAJOR) {
            ctx.moveTo(0, my);
            ctx.lineTo(W, my);
        }
        ctx.stroke();

        /* 5. both diagonals of the whole wall, corner to corner: the seam
         *    test. If the geometry is right these line up across tablets. */
        ctx.strokeStyle = PATTERN.diagonal;
        ctx.lineWidth = px(PX_DIAGONAL);
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(W, H);
        ctx.moveTo(W, 0);
        ctx.lineTo(0, H);
        ctx.stroke();

        /* 6. crosshair at the wall centre */
        var cx = W / 2;
        var cy = H / 2;
        var arm = Math.max(Math.max(visible.w, visible.h) * 0.06, 20);
        ctx.strokeStyle = PATTERN.crosshair;
        ctx.lineWidth = px(PX_MAJOR_LINE);
        ctx.beginPath();
        ctx.moveTo(cx - arm, cy);
        ctx.lineTo(cx + arm, cy);
        ctx.moveTo(cx, cy - arm);
        ctx.lineTo(cx, cy + arm);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(cx, cy, arm * 0.45, 0, Math.PI * 2);
        ctx.stroke();

        /* 7. axis labels along the top and left edges, every 500 units */
        ctx.fillStyle = PATTERN.axis;
        ctx.font = font + "px " + FONT_STACK;
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        for (var lx = 0; lx <= W; lx += PATTERN_GRID_MAJOR) {
            ctx.fillText(String(lx), lx + pad, pad);
        }
        for (var ly = 0; ly <= H; ly += PATTERN_GRID_MAJOR) {
            ctx.fillText(String(ly), pad, ly + pad);
        }

        /* 8. this device's own visible rect, outlined and labelled with its
         *    short id and its x,y,w,h (the rect's own coordinates) */
        var own =
            shortDeviceId() +
            " \u00b7 " +
            visible.x +
            "," +
            visible.y +
            " " +
            visible.w +
            "\u00d7" +
            visible.h;
        var tw = ctx.measureText(own).width;
        ctx.fillStyle = PATTERN.labelBg;
        ctx.fillRect(
            visible.x + pad * 0.5,
            visible.y + pad * 0.5,
            tw + pad,
            font + pad
        );
        ctx.fillStyle = PATTERN.ownRect;
        ctx.fillText(own, visible.x + pad, visible.y + pad);
        ctx.strokeStyle = PATTERN.ownRect;
        ctx.lineWidth = px(PX_OWN_RECT);
        ctx.strokeRect(visible.x, visible.y, visible.w, visible.h);

        /* 9. wall dimensions and current revision, in a corner of the wall */
        var info = W + "\u00d7" + H + " \u00b7 r" + wallState.revision;
        var iw = ctx.measureText(info).width;
        ctx.textAlign = "right";
        ctx.fillStyle = PATTERN.labelBg;
        ctx.fillRect(
            W - pad - iw - pad * 0.5,
            pad * 0.5,
            iw + pad,
            font + pad
        );
        ctx.fillStyle = PATTERN.info;
        ctx.fillText(info, W - pad, pad);
    }

    /* Unplaced in calibration mode: name and note, big enough to read. */
    function drawUnplaced() {
        var vp = viewportSize();
        if (!vp) return;
        var view = prepareCanvas(vp.w, vp.h);
        if (!view) return;
        var ctx = view.ctx;
        ctx.setTransform(view.dpr, 0, 0, view.dpr, 0, 0);

        ctx.fillStyle = PATTERN.background;
        ctx.fillRect(0, 0, vp.w, vp.h);

        var unit = Math.min(vp.w, vp.h);
        var idSize = Math.max(28, unit * 0.16);
        var noteSize = Math.max(16, unit * 0.07);
        var hintSize = Math.max(12, unit * 0.034);
        var midX = vp.w / 2;
        var midY = vp.h / 2;

        ctx.textAlign = "center";
        ctx.textBaseline = "middle";

        ctx.fillStyle = PATTERN.unplacedId;
        ctx.font = "700 " + idSize + "px " + FONT_STACK;
        ctx.fillText(shortDeviceId(), midX, midY - idSize * 0.45);

        ctx.fillStyle = PATTERN.unplacedNote;
        ctx.font = "700 " + noteSize + "px " + FONT_STACK;
        ctx.fillText("NO PLACEMENT", midX, midY + idSize * 0.35);

        ctx.fillStyle = PATTERN.unplacedHint;
        ctx.font = hintSize + "px " + FONT_STACK;
        ctx.fillText(
            "Not placed on this wall yet \u2014 assign a placement in the controller.",
            midX,
            midY + idSize * 0.35 + noteSize
        );
    }

    /*
     * Store a `wall` frame.
     *
     * Two rules, and the second one is the point of `generation`:
     *
     *  1. A frame whose revision is not newer than the one we hold is dropped
     *     untouched, so a replayed frame on reconnect can never roll the wall
     *     back — but ONLY while its `generation` is the generation we hold.
     *     When the generation differs the frame is accepted regardless of its
     *     revision and the held revision is reset to the frame's. A server
     *     restored from a backup, rolled back, or started on a wiped database
     *     can legitimately be at a lower revision than this tablet has seen
     *     (12 → 0), and a client that refused those frames would stay stuck
     *     on stale state forever.
     *  2. The whole frame is validated BEFORE anything is stored, so a
     *     malformed frame can neither render nor reset the held revision.
     *
     * Returns true when it was applied.
     */
    function applyWallFrame(frame) {
        var revision = frame.revision;
        if (!Number.isFinite(revision)) return false;

        /* A frame with no (string) generation is treated as its own,
         * unknown lineage: it never matches a held generation, so it is
         * always accepted rather than wedging the tablet on a comparison it
         * cannot make. */
        var generation =
            typeof frame.generation === "string" ? frame.generation : null;

        var wall = frame.wall;
        if (!wall || typeof wall !== "object") return false;
        var width = Number(wall.width);
        var height = Number(wall.height);
        if (!Number.isFinite(width) || !Number.isFinite(height)) return false;
        if (width <= 0 || height <= 0) return false;

        /* scene.content.type — "color" is the fallback for a frame that
         * omits the scene, which keeps the v1 colour behaviour intact. */
        var scene = frame.scene;
        var content =
            scene && scene.content && typeof scene.content === "object"
                ? scene.content
                : null;
        var contentType =
            content && typeof content.type === "string" && content.type !== ""
                ? content.type
                : "color";

        var placement = frame.placement == null ? null : frame.placement;
        var visible = null;
        if (placement !== null) {
            visible = visibleRectOf(placement);
            if (!visible) {
                warn("placement leaves no visible area; treating as unplaced");
                placement = null;
            }
        }

        /* Revision monotonic only within a generation (see rule 1 above). */
        if (
            heldRevision !== null &&
            generation === heldGeneration &&
            revision <= heldRevision
        ) {
            return false;
        }

        heldRevision = revision;
        heldGeneration = generation;
        wallState = {
            width: width,
            height: height,
            contentType: contentType,
            revision: revision,
            generation: generation,
            placement: placement,
            visible: visible,
        };
        render();
        return true;
    }

    /* The mapping depends on the viewport, so resize re-renders.
     *
     * It also makes the size we registered stale, and that size is what the
     * controller compares a placement against to warn about cropping. So when
     * the viewport genuinely changes -- a rotation, a zoom, an undocked window
     * -- re-register. Debounced, and skipped when the size is unchanged so that
     * browser chrome sliding in and out does not generate traffic. */
    var RESIZE_REREGISTER_MS = 400;
    var resizeTimer = null;
    var reportedSize = window.innerWidth + "x" + window.innerHeight;

    function onViewportChange() {
        render();

        var size = window.innerWidth + "x" + window.innerHeight;
        if (size === reportedSize) return;

        if (resizeTimer !== null) clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function () {
            resizeTimer = null;
            var current = window.innerWidth + "x" + window.innerHeight;
            if (current === reportedSize) return;
            reportedSize = current;
            // Best effort only: a failed re-registration must not tear down a
            // healthy socket. The next connect attempt re-registers anyway.
            register().catch(function () {});
        }, RESIZE_REREGISTER_MS);
    }

    window.addEventListener("resize", onViewportChange);
    window.addEventListener("orientationchange", onViewportChange);

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
            encodeURIComponent(deviceId) +
            "&protocol=" +
            PROTOCOL_VERSION +
            "&caps=" +
            CAPS
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
        } else if (frame.type === "wall") {
            applyWallFrame(frame);
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
