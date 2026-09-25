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
 * When the scene content is `image`, the same visible-rect mapping is reused
 * to clip a centered `cover` of the whole wall: the image rectangle is
 * computed once, in wall coordinates, from the wall size and the image's
 * intrinsic size only — never per tablet — so the seams stay put. The asset
 * is fetched from a same-origin URL and decoded before it is painted, the
 * WHOLE attempt (headers, body and decode) is bounded to 15 seconds, an
 * attempt is discarded when a newer token/generation/revision owns the scene
 * or when its own deadline has passed, and a failed load says so (IMAGE
 * FAILED + short asset id + tap to retry) instead of quietly leaving a stale
 * surface on the wall.
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
     * this client can render, so the server may send calibration and image
     * content (PROTOCOL.md "Still images": a device that has not advertised
     * `image` is never sent image content). */
    var PROTOCOL_VERSION = 2;
    var CAPS = "calibration,image";

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

    /* Image content: how long a same-origin asset may take to arrive and
     * decode before it is reported as failed (PROTOCOL.md "Still images":
     * a missing asset must not present as a blank wall). */
    var IMAGE_LOAD_TIMEOUT_MS = 15000;
    var IMAGE_SHORT_ID_CHARS = 8; /* hex shown on the image panels     */

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
        /* Banner drawn over a retained image while a new one loads: opaque
         * enough to read across a room, without hiding what is underneath. */
        band: "rgba(2, 6, 23, 0.9)",
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
     *   { width, height, contentType, image, imageError, revision, generation,
     *     placement, visible }
     * where `contentType` is `scene.content.type` ("color", "calibration" or
     * "image"), `image` is the normalised image descriptor (see
     * analyzeImageContent) or null when image content arrived unusable, with
     * `imageError` saying why, `visible` is the placement's footprint shrunk
     * by its bezel (or null when this device has no usable placement), and
     * `heldRevision` / `heldGeneration` describe the state we hold: both null
     * until the first accepted frame.
     */
    var wallState = null;
    var heldRevision = null;
    var heldGeneration = null;

    /*
     * The image scene's own state, kept apart from `wallState` because it is
     * reached through asynchronous work that can outlive the frame that
     * asked for it:
     *
     *   imageToken   bumped by every new load attempt and every invalidation;
     *                an attempt whose token is no longer current is stale.
     *   imageAttempt the load currently owning the scene, or null; it carries
     *                the token plus the generation/revision it was started
     *                for, so a completion can prove it is still the answer.
     *   imageStatus  "none" | "loading" | "ready" | "failed".
     *   imageFailure why the scene is failed, for the panel and the console.
     *   imageCache   last successful decode — { key, source, iw, ih, handle }
     *                — so a new load can keep the previous picture on the
     *                wall while clearly saying it is loading, and a replayed
     *                frame needs no refetch. `handle` carries whatever still
     *                has to be released with it (an <img> and its object
     *                URL on the fallback path).
     */
    var imageToken = 0;
    var imageAttempt = null;
    var imageStatus = "none";
    var imageFailure = null;
    var imageCache = null;

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

        if (wallState.contentType === "calibration") {
            showCanvas(true);
            if (!wallState.visible) {
                drawUnplaced();
            } else {
                drawCalibration();
            }
            return;
        }

        /* Image content: the same wall mapping, clipped to this slice,
         * carrying a centered cover of the whole wall. drawImageScene owns
         * every image state — unplaced, loading, ready, failed. */
        if (wallState.contentType === "image") {
            showCanvas(true);
            drawImageScene();
            return;
        }

        /* Absent or colour content is the colour surface. Anything else is
           content this page cannot draw: a type a newer server invented.
           Falling back to the assigned colour would look exactly like a
           healthy wall while showing the wrong thing, so say so on the panel,
           where whoever is standing in front of it can see it. */
        var type = wallState.contentType;
        if (type === null || type === undefined || type === "color") {
            showCanvas(false); /* colour content: today's behaviour, untouched */
            return;
        }

        showCanvas(true);
        drawUnsupported(type);
    }

    /* Content this page cannot render. Saying so beats showing a colour. */
    function drawUnsupported(type) {
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
        ctx.fillText(
            "CANNOT DISPLAY " + String(type).toUpperCase(),
            midX,
            midY + idSize * 0.35
        );

        ctx.fillStyle = PATTERN.unplacedHint;
        ctx.font = hintSize + "px " + FONT_STACK;
        ctx.fillText(
            "This tablet does not render that content type.",
            midX,
            midY + idSize * 0.35 + noteSize
        );
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
         * the rect's CENTRE sits at the viewport's centre: the overflow is
         * cropped equally on all sides, so a viewport whose aspect differs
         * from the rect still shows the middle of its slice (PROTOCOL.md
         * "Aspect and seam caveats"). Anything outside the rect falls
         * outside the canvas and is cropped.
         */
        var scale = Math.max(vp.w / visible.w, vp.h / visible.h);
        if (!Number.isFinite(scale) || scale <= 0) return;
        var k = scale * view.dpr; /* wall unit -> device pixel */
        var ox = (visible.w - vp.w / scale) / 2;
        var oy = (visible.h - vp.h / scale) / 2;
        view.ctx.setTransform(
            k,
            0,
            0,
            k,
            -(visible.x + ox) * k,
            -(visible.y + oy) * k
        );
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

    /* Unplaced under content that needs a placement: name and note, big
     * enough to read. Calibration and image scenes both route here. */
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

    /* ------------------------------------------------------------------ */
    /* Image content                                                      */
    /* ------------------------------------------------------------------ */

    /*
     * Normalise `scene.content` of type "image" into
     *   { key, asset, url, fit, iw, ih }
     * or report why it cannot be addressed at all. `key` identifies the
     * request — asset, url, fit and intrinsic size together — so an in-flight
     * load or a cached decode can be recognised as the answer to exactly the
     * scene on screen now.
     *
     * The descriptor is data only: the server composes the same-origin URL,
     * and `iw`/`ih` are the dimensions it derived from the file (PROTOCOL.md
     * "Still images"). A now-missing asset still arrives with its id and its
     * dimensions so it can be reported as an explicit failure rather than
     * quietly downgraded to colour.
     */
    function analyzeImageContent(content) {
        if (!content || typeof content !== "object") {
            return { desc: null, reason: "malformed image content" };
        }
        var asset = typeof content.asset === "string" ? content.asset : "";
        var url = typeof content.url === "string" ? content.url : "";
        if (asset === "" || url === "") {
            return { desc: null, reason: "image content has no asset or url" };
        }
        var fit =
            content.fit === undefined || content.fit === null
                ? "cover"
                : content.fit;
        if (fit !== "cover") {
            /* Only centered cover exists. Drawing some other fit on one
             * tablet only would break every seam it touches, so refuse it
             * out loud instead. */
            return {
                desc: null,
                reason: "unsupported fit: " + String(fit).slice(0, 32),
            };
        }
        var iw = Number(content.intrinsicWidth);
        var ih = Number(content.intrinsicHeight);
        if (!Number.isFinite(iw) || iw <= 0 || !Number.isFinite(ih) || ih <= 0) {
            /* No usable intrinsic size: the decoded bitmap supplies it. */
            iw = null;
            ih = null;
        }
        return {
            desc: {
                key: [asset, url, fit, iw, ih].join("\u0000"),
                asset: asset,
                url: url,
                fit: fit,
                iw: iw,
                ih: ih,
            },
            reason: null,
        };
    }

    /* Eight digest characters fit the full-screen diagnostic even on a
     * small tablet; the complete ID remains in the scene and inventory. */
    function shortAssetId() {
        var desc = wallState ? wallState.image : null;
        var asset = desc && typeof desc.asset === "string" ? desc.asset : "";
        var colon = asset.indexOf(":");
        var body = (colon >= 0 ? asset.slice(colon + 1) : asset).replace(
            /[^0-9A-Za-z]/g,
            ""
        );
        if (body === "") body = asset.replace(/[^0-9A-Za-z]/g, "");
        if (body === "") return "unknown asset";
        return body.slice(0, IMAGE_SHORT_ID_CHARS);
    }

    /*
     * Same origin only. The wall must not reach outside the LAN server for
     * pixels, and a cross-origin picture would be tainted — undecodable by
     * anything but a plain <img> draw, and unreadable if we ever needed to
     * inspect it.
     */
    function sameOriginUrl(raw) {
        var origin = window.location.origin;
        if (!origin) {
            origin = window.location.protocol + "//" + window.location.host;
        }
        var parsed = new URL(String(raw), window.location.href);
        if (parsed.origin !== origin) {
            throw new Error("image url is not same-origin");
        }
        return parsed.href;
    }

    /*
     * Fetch the bytes, then decode them. Nothing here is ever painted: the
     * caller only ever draws a source that has already decoded.
     *
     * This deliberately does not time itself out — the attempt's own timer
     * (startImageLoad) bounds headers, body AND decode together, so a body
     * or decode that stalls cannot outlive it.
     */
    function fetchImageSource(url, controller, handle) {
        return fetch(url, {
            method: "GET",
            credentials: "same-origin",
            signal: controller ? controller.signal : undefined,
        })
            .then(function (response) {
                if (!response || !response.ok) {
                    var status =
                        response && response.status != null
                            ? response.status
                            : "?";
                    throw new Error("image fetch failed: HTTP " + status);
                }
                if (typeof response.blob !== "function") {
                    throw new Error("image fetch returned no body");
                }
                return response.blob();
            })
            .then(function (blob) {
                return decodeBlob(blob, url, handle);
            });
    }

    /* Decoding before painting is what keeps a slow asset from flashing an
     * empty surface: the wall swaps to the new picture only once it is
     * fully decoded. */
    function decodeBlob(blob, url, handle) {
        if (typeof createImageBitmap === "function") {
            return Promise.resolve(createImageBitmap(blob)).then(function (bitmap) {
                return {
                    source: bitmap,
                    iw: Number(bitmap && bitmap.width),
                    ih: Number(bitmap && bitmap.height),
                    handle: handle,
                };
            });
        }
        /*
         * No createImageBitmap: decode the bytes we ALREADY fetched, by
         * handing the <img> an object URL made from that Blob. Pointing it
         * at the original URL instead would fetch the whole asset a second
         * time — and that request would be nobody's child, so no timeout or
         * scene change could cancel it.
         */
        if (typeof URL.createObjectURL === "function") {
            handle.objectUrl = URL.createObjectURL(blob);
            return decodeWithImage(handle, null);
        }
        /* Nothing can turn the Blob into a picture: fall back to the URL.
         * It costs a second request, but it is the only way to draw. */
        warn("URL.createObjectURL unavailable; loading the image by URL");
        return decodeWithImage(handle, url);
    }

    function decodeWithImage(handle, fallbackUrl) {
        return new Promise(function (resolve, reject) {
            if (typeof Image !== "function") {
                releaseLoad(handle);
                reject(new Error("no image decoder available"));
                return;
            }
            var img = new Image();
            handle.img = img;
            var settled = false;
            function succeed() {
                if (settled) return;
                settled = true;
                img.onload = null;
                img.onerror = null;
                resolve({
                    source: img,
                    iw: Number(img.naturalWidth),
                    ih: Number(img.naturalHeight),
                    handle: handle,
                });
            }
            function fail() {
                if (settled) return;
                settled = true;
                /* The bytes are unusable: let them go right here, rather
                 * than leaving an object URL nobody will ever release. */
                releaseLoad(handle);
                reject(new Error("image decode failed"));
            }
            img.onload = succeed;
            img.onerror = fail;
            img.src = handle.objectUrl || fallbackUrl;
            if (typeof img.decode === "function") {
                /*
                 * A rejection from decode() is NOT a failure: Safari is
                 * known to reject it before a later, perfectly good load
                 * event. The load events are the authority — on resolve we
                 * are done (decoded before painting), on reject we simply
                 * wait for onload/onerror, and if neither ever arrives the
                 * attempt's own timeout settles it.
                 */
                img.decode().then(succeed, function () {
                    /* wait for onload / onerror */
                });
            }
        });
    }

    /* An ImageBitmap holds real memory; the loser of a race and the picture
     * being replaced both get released. */
    function releaseImageSource(source) {
        if (source && typeof source.close === "function") {
            try {
                source.close();
            } catch (err) {
                warn("could not release an image", err);
            }
        }
    }

    /* One attempt's handle on the platform: the <img> still downloading and
     * the object URL its bytes live behind. */
    function newLoadHandle() {
        return { img: null, objectUrl: null };
    }

    /*
     * Abandon a load nobody is waiting for any more: clear its handlers and
     * its src so the <img> stops pulling bytes, then revoke the object URL.
     * Idempotent — every field is nulled as it goes — so a timeout, a scene
     * change and a late settle can all call it without double work.
     */
    function releaseLoad(handle) {
        if (!handle) return;
        var img = handle.img;
        if (img) {
            handle.img = null;
            img.onload = null;
            img.onerror = null;
            try {
                img.src = ""; /* detach: no more network */
            } catch (err) {
                warn("could not cancel the image load", err);
            }
        }
        if (handle.objectUrl) {
            var objectUrl = handle.objectUrl;
            handle.objectUrl = null;
            if (typeof URL.revokeObjectURL === "function") {
                try {
                    URL.revokeObjectURL(objectUrl);
                } catch (err) {
                    warn("could not revoke the image object URL", err);
                }
            }
        }
    }

    /* Give back everything one decoded picture took: the bitmap, the <img>,
     * and its object URL. Works for a resolved load and for a cache entry. */
    function releasePicture(picture) {
        if (!picture) return;
        releaseImageSource(picture.source);
        releaseLoad(picture.handle);
    }

    /*
     * Drop the cached picture for good. Bounded memory matters here: a
     * decoded still is up to 12 megapixels, and once the scene is no longer
     * image — or the failure panel is covering it — nothing will ever draw
     * it again, so keeping it would hold that memory for nothing.
     */
    function releaseImageCache() {
        if (imageCache === null) return;
        var cached = imageCache;
        imageCache = null;
        releasePicture(cached);
    }

    function errorText(err) {
        if (!err) return "unknown error";
        if (typeof err.message === "string" && err.message !== "") {
            return err.message.slice(0, 120);
        }
        return String(err).slice(0, 120);
    }

    /*
     * The stale-result guard. A completion is only allowed to paint when the
     * attempt is still open AND it is still the newest one AND it was
     * started for the generation and revision now held AND the scene it was
     * asked for is the scene on screen. Anything else — a newer frame, a
     * server restart, a different asset, or an attempt that already timed
     * out — is discarded rather than painted over the newer truth.
     */
    function isCurrentImageAttempt(attempt) {
        return (
            !attempt.settled &&
            attempt.token === imageToken &&
            wallState !== null &&
            wallState.contentType === "image" &&
            heldGeneration === attempt.generation &&
            heldRevision === attempt.revision &&
            wallState.image !== null &&
            wallState.image.key === attempt.key
        );
    }

    /* The scene does not need a picture right now — it is not image content
     * any more, or this device has no placement — so cancel any load in
     * flight NOW (stop the <img>, revoke its object URL) and let go of
     * whatever is decoded. */
    function invalidateImageScene() {
        imageToken++;
        if (imageAttempt !== null) {
            /* Abandoned mid-flight: nothing that settles later may paint,
             * and the bytes must stop being pulled on our behalf. */
            imageAttempt.settled = true;
            releaseLoad(imageAttempt.load);
        }
        imageAttempt = null;
        imageStatus = "none";
        imageFailure = null;
        releaseImageCache();
    }

    /*
     * Report the failure out loud — console and panel — never a blank wall
     * and never the previous picture pretending to be this one. Whatever is
     * in flight or cached goes too: the failure panel covers the canvas, so
     * a decoded picture is invisible, and a retry decodes a fresh one
     * anyway.
     */
    function failImageScene(reason) {
        if (imageAttempt !== null) {
            /* A timeout (or a failed load) must stop the <img> and revoke
             * its object URL instead of leaving bytes nobody wants. */
            releaseLoad(imageAttempt.load);
        }
        imageAttempt = null;
        imageStatus = "failed";
        imageFailure = reason;
        releaseImageCache();
        warn("image scene failed: " + reason);
        render();
    }

    /* Reconcile the async image state with the wall state just stored.
     * Returns true when it has already painted the outcome, so the caller
     * does not paint the same frame twice. */
    function syncImageScene() {
        if (!wallState || wallState.contentType !== "image") {
            invalidateImageScene();
            return false;
        }

        if (!wallState.visible) {
            /*
             * NO PLACEMENT: nothing can be shown here, so nothing is
             * fetched. Decoding up to 12 megapixels for a panel that says
             * "not placed" would be waste — the frame that carries the
             * placement starts the load, and a load still running when the
             * placement went away is cancelled by the same call.
             */
            invalidateImageScene();
            return false;
        }

        var desc = wallState.image;
        if (!desc) {
            /* Image content we cannot even address (missing asset/url, an
             * unsupported fit). Saying so beats falling back to colour. */
            failImageScene(wallState.imageError || "malformed image content");
            return true;
        }

        if (imageCache && imageCache.key === desc.key) {
            /* Already decoded this exact picture: a replayed or reconnected
             * frame needs no refetch. */
            imageAttempt = null;
            imageStatus = "ready";
            imageFailure = null;
            return false;
        }

        if (
            imageAttempt !== null &&
            imageAttempt.key === desc.key &&
            imageAttempt.generation === heldGeneration &&
            imageAttempt.revision === heldRevision
        ) {
            imageStatus = "loading"; /* this exact request is already running */
            return false;
        }

        startImageLoad(desc);
        return true;
    }

    /*
     * A replayed wall frame is a no-op except for this: if the scene is the
     * one that failed, try it again — the asset may have been put back, and
     * inventory changes do not bump the revision (PROTOCOL.md "Still
     * images"). One attempt per frame, never a loop.
     */
    function retryFailedImage(image) {
        if (imageStatus !== "failed" || image === null) return;
        if (
            wallState === null ||
            wallState.contentType !== "image" ||
            wallState.image === null ||
            wallState.image.key !== image.key
        ) {
            return;
        }
        startImageLoad(image);
    }

    /* Begin (or restart) the load for one descriptor. */
    function startImageLoad(desc) {
        var attempt = {
            token: ++imageToken,
            key: desc.key,
            generation: heldGeneration,
            revision: heldRevision,
            settled: false,
            load: newLoadHandle(), /* the <img>/object-URL this attempt owns */
        };
        imageAttempt = attempt;
        imageStatus = "loading";
        imageFailure = null;
        render(); /* the diagnostic appears before a byte is fetched */

        var url;
        try {
            url = sameOriginUrl(desc.url);
        } catch (err) {
            attempt.settled = true;
            failImageScene(errorText(err));
            return;
        }

        var controller =
            typeof AbortController === "function" ? new AbortController() : null;

        /*
         * ONE timer bounds the WHOLE attempt — response headers, body and
         * decode together — because a stalled body or a decode that never
         * settles would otherwise leave the wall spinning on "loading" for
         * ever. When it fires the attempt is settled: it reports IMAGE
         * FAILED with a tappable retry, aborts the request where the
         * browser can, and any decode that finishes afterwards is discarded
         * and its bitmap released rather than painted over the failure. A
         * stale callback never restarts the attempt — retrying is the
         * operator's tap.
         */
        var timer = setTimeout(function () {
            timer = null;
            if (controller) {
                try {
                    controller.abort();
                } catch (err) {
                    warn("could not abort the image request", err);
                }
            }
            if (!isCurrentImageAttempt(attempt)) return;
            attempt.settled = true;
            failImageScene("image load timed out");
        }, IMAGE_LOAD_TIMEOUT_MS);

        /* The promise settled, so the attempt's own deadline is spent. */
        function settle() {
            if (timer !== null) {
                clearTimeout(timer);
                timer = null;
            }
        }

        fetchImageSource(url, controller, attempt.load).then(
            function (result) {
                settle();
                if (!isCurrentImageAttempt(attempt)) {
                    /* Superseded or already timed out: paint nothing, leak
                     * nothing (bitmap, <img> and object URL all released),
                     * and retry nothing from here. */
                    releasePicture(result);
                    return;
                }
                attempt.settled = true;
                var iw = desc.iw !== null ? desc.iw : result.iw;
                var ih = desc.ih !== null ? desc.ih : result.ih;
                if (
                    !Number.isFinite(iw) ||
                    iw <= 0 ||
                    !Number.isFinite(ih) ||
                    ih <= 0
                ) {
                    releasePicture(result);
                    failImageScene("image has no usable size");
                    return;
                }
                imageAttempt = null;
                if (imageCache && imageCache.source !== result.source) {
                    releasePicture(imageCache);
                }
                imageCache = {
                    key: desc.key,
                    source: result.source,
                    iw: iw,
                    ih: ih,
                    handle: result.handle,
                };
                imageStatus = "ready";
                imageFailure = null;
                render();
            },
            function (err) {
                settle();
                /* Stale or timed out already: drop it silently — starting a
                 * fresh load from a late rejection would retry an attempt
                 * the operator has not asked to retry. */
                if (!isCurrentImageAttempt(attempt)) return;
                attempt.settled = true;
                failImageScene(errorText(err));
            }
        );
    }

    /* Single entry point for the image scene: unplaced, failed, loading,
     * or a picture with (optionally) a loading banner over it. */
    function drawImageScene() {
        var vp = viewportSize();
        if (!vp) return;
        var desc = wallState.image;

        if (!wallState.visible) {
            drawUnplaced(); /* NO PLACEMENT: nothing to map onto */
            return;
        }
        if (!desc || imageStatus === "failed") {
            drawImageFailure(vp);
            return;
        }

        /* A picture already on the wall may stay while the next one loads —
         * but only under the loading banner, so nobody reads the old frame
         * as the new scene. */
        var entry = null;
        if (imageCache) {
            if (imageStatus === "ready" && imageCache.key === desc.key) {
                entry = imageCache;
            } else if (imageStatus === "loading") {
                entry = imageCache;
            }
        }
        if (!entry) {
            drawImageLoading(vp); /* first load: visible diagnostic */
            return;
        }
        var outcome = drawWallImage(vp, entry);
        if (outcome === "size") {
            /* The decoded picture itself is unusable — a real failure, so
             * say so. (failImageScene also lets go of that bitmap.) */
            if (imageStatus === "ready") {
                failImageScene("image has no usable size");
                return;
            }
            /* A retained picture we cannot draw: the new one is still on
             * its way, so keep saying so. */
            drawImageLoading(vp);
            return;
        }
        if (outcome !== "painted") {
            /*
             * No surface to paint on, or a mapping that makes no sense
             * yet — a canvas we cannot get, a viewport mid-change. That is
             * transient and has nothing to do with the picture, so the
             * state stays as it is (ready stays ready) and a later render
             * (a resize, the next frame) tries again. Calling a perfectly
             * good image broken here would push the operator into a retry
             * loop over a problem that never was one.
             */
            return;
        }
        if (imageStatus === "loading") drawLoadingBanner(vp);
    }

    /*
     * Centered cover of the WHOLE wall, drawn in wall coordinates under the
     * very transform the calibration pattern uses — the visible rect mapped
     * onto this viewport, then clipped to it.
     *
     * The cover rectangle depends only on the wall size and the image's
     * intrinsic size, so every tablet derives the identical rectangle and
     * the seams line up. Covering into each tablet's own visible rect instead
     * would hand every tablet a different scale (PROTOCOL.md "Fit").
     *
     * Returns why it did or did not paint:
     *   "painted" — drawn;
     *   "surface" — no canvas/context, or a nonsensical mapping: transient,
     *               the caller keeps its state and retries on a later
     *               render;
     *   "size"    — the picture's own dimensions are unusable: a failure.
     */
    function drawWallImage(vp, entry) {
        var view = prepareCanvas(vp.w, vp.h);
        if (!view) return "surface";
        var visible = wallState.visible;
        if (!visible) return "surface";

        /* The picture is checked before anything is touched: it is the only
         * of these three that says the asset itself is wrong. */
        var iw = Number(entry.iw);
        var ih = Number(entry.ih);
        if (!Number.isFinite(iw) || iw <= 0 || !Number.isFinite(ih) || ih <= 0) {
            return "size";
        }

        var scale = Math.max(vp.w / visible.w, vp.h / visible.h);
        if (!Number.isFinite(scale) || scale <= 0) return "surface";
        var k = scale * view.dpr; /* wall unit -> device pixel */
        var ctx = view.ctx;
        /* Centred cover of the visible rect onto the viewport, exactly as
         * the calibration mapping: rect centre to viewport centre, overflow
         * cropped equally on all sides. */
        var ox = (visible.w - vp.w / scale) / 2;
        var oy = (visible.h - vp.h / scale) / 2;
        ctx.setTransform(k, 0, 0, k, -(visible.x + ox) * k, -(visible.y + oy) * k);

        var W = wallState.width;
        var H = wallState.height;

        /* max(W/iw, H/ih), centred: the overflow is cropped equally on both
         * sides, and the clip below crops whatever falls outside this
         * device's visible rect. */
        var s = Math.max(W / iw, H / ih);
        var dw = iw * s;
        var dh = ih * s;
        var dx = (W - dw) / 2;
        var dy = (H - dh) / 2;

        ctx.save();
        ctx.beginPath();
        ctx.rect(visible.x, visible.y, visible.w, visible.h);
        ctx.clip();
        /* Opaque underneath: a partially transparent source must never show
         * the previous frame's pixels through it. */
        ctx.fillStyle = PATTERN.background;
        ctx.fillRect(visible.x, visible.y, visible.w, visible.h);
        ctx.drawImage(entry.source, dx, dy, dw, dh);
        ctx.restore();
        return "painted";
    }

    /* Loading over a retained picture: a band that cannot be missed. */
    function drawLoadingBanner(vp) {
        var view = prepareCanvas(vp.w, vp.h);
        if (!view) return;
        var ctx = view.ctx;
        ctx.setTransform(view.dpr, 0, 0, view.dpr, 0, 0);

        var unit = Math.min(vp.w, vp.h);
        var bandH = Math.max(44, unit * 0.18);
        ctx.fillStyle = PATTERN.band;
        ctx.fillRect(0, (vp.h - bandH) / 2, vp.w, bandH);
        ctx.fillStyle = PATTERN.unplacedNote;
        ctx.font = "700 " + Math.max(16, bandH * 0.42) + "px " + FONT_STACK;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(
            "LOADING IMAGE \u00b7 " + shortAssetId(),
            vp.w / 2,
            vp.h / 2
        );
    }

    /* First load: a full panel rather than a blank wall. */
    function drawImageLoading(vp) {
        drawImagePanel(vp, {
            id: shortAssetId(),
            headline: "LOADING IMAGE",
            headlineColor: PATTERN.info,
            hint: "Fetching this wall's picture from the server\u2026",
        });
    }

    /*
     * Failed load or decode: which picture failed, why, and what to do. The
     * canvas is fully painted first, so a stale surface from the previous
     * scene can never show through.
     *
     * The "what to do" is only as true as the state behind it: a scene with
     * no addressable asset (a malformed descriptor) cannot be retried by a
     * tap, because there is no URL to fetch — promising a retry there would
     * be a button that does nothing, so say who has to act instead.
     */
    function drawImageFailure(vp) {
        var retryable = wallState.image !== null;
        drawImagePanel(vp, {
            id: shortAssetId(),
            headline: "IMAGE FAILED",
            headlineColor: PATTERN.unplacedNote,
            hint:
                (imageFailure ? imageFailure + " \u00b7 " : "") +
                (retryable
                    ? "Tap anywhere to retry."
                    : "Set a valid image in the controller."),
        });
    }

    /* Full-viewport panel in the same rhythm as the NO PLACEMENT panel, so
     * the wall always says something out loud. */
    function drawImagePanel(vp, opts) {
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
        ctx.fillText(opts.id, midX, midY - idSize * 0.45);

        ctx.fillStyle = opts.headlineColor;
        ctx.font = "700 " + noteSize + "px " + FONT_STACK;
        ctx.fillText(opts.headline, midX, midY + idSize * 0.35);

        if (opts.hint) {
            ctx.fillStyle = PATTERN.unplacedHint;
            ctx.font = hintSize + "px " + FONT_STACK;
            ctx.fillText(opts.hint, midX, midY + idSize * 0.35 + noteSize);
        }
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

        /* Image content is normalised here, still before anything is
         * stored, so a malformed descriptor reaches the panel as an
         * explainable failure instead of half-rendering. */
        var image = null;
        var imageError = null;
        if (contentType === "image") {
            var analysis = analyzeImageContent(content);
            image = analysis.desc;
            imageError = analysis.reason;
        }

        var placement = frame.placement == null ? null : frame.placement;
        var visible = null;
        if (placement !== null) {
            visible = visibleRectOf(placement);
            if (!visible) {
                warn("placement leaves no visible area; treating as unplaced");
                placement = null;
            }
        }

        /* Revision monotonic only within a generation (see rule 1 above).
         * A rejected frame is otherwise a no-op — with one exception: the
         * wall frame that follows every `welcome` is a replay, and it is the
         * device's chance to try a failed asset again, because an inventory
         * change deliberately does not bump the revision (PROTOCOL.md "Still
         * images": "retry the load on the device (or reconnect)"). */
        if (
            heldRevision !== null &&
            generation === heldGeneration &&
            revision <= heldRevision
        ) {
            retryFailedImage(image);
            return false;
        }

        heldRevision = revision;
        heldGeneration = generation;
        wallState = {
            width: width,
            height: height,
            contentType: contentType,
            image: image,
            imageError: imageError,
            revision: revision,
            generation: generation,
            placement: placement,
            visible: visible,
        };
        /* Image scenes carry asynchronous work: reconcile it with the frame
         * we just accepted — it starts the load, and paints the outcome if
         * there is one — then paint whatever it left for us. */
        if (!syncImageScene()) render();
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

    /*
     * Tap-to-retry, which the failure panel promises. It listens on the
     * document, not the surface, because the surface is
     * `pointer-events: none` (client.css) and the failure has to be
     * recoverable from wherever the operator is standing. Every other
     * content type — and every image scene that is not failed — returns
     * immediately, so a tap never restarts a healthy load.
     */
    function onSurfaceTap() {
        if (!wallState || wallState.contentType !== "image") return;
        if (imageStatus !== "failed" || !wallState.image) return;
        startImageLoad(wallState.image);
    }

    if (typeof document.addEventListener === "function") {
        document.addEventListener("click", onSurfaceTap);
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
