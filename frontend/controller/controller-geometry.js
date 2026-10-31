"use strict";

/* Wall geometry and scene-content rules. No DOM or live controller state. */
window.ControllerGeometry = (function () {
    const ASPECT_TOLERANCE = 0.01;

    function numOr(value, fallback) {
        const n = Number(value);
        return Number.isFinite(n) ? n : fallback;
    }

    function normalizeSizing(raw) {
        const sizing = raw && typeof raw === "object" ? raw : {};
        return {
            mode: sizing.mode === "tablets" ? "tablets" : "fixed",
            padding: Math.max(0, Math.round(numOr(sizing.padding, 0)))
        };
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

    /** Advertised render capabilities, with "not reported" kept distinct from
     *  "reported and unsupported". */
    function deviceCaps(device) {
        const known = !!device && Array.isArray(device.caps);
        const caps = known ? device.caps : [];
        return {
            known: known,
            caps: caps,
            image: known ? caps.indexOf("image") !== -1 : null
        };
    }

    function placementShapeMismatch(placement, device) {
        if (!placement || !device) return false;
        const visible = visibleRect(placement);
        const delta = aspectDelta(aspectOf(visible.w, visible.h), viewportAspect(device));
        return isAspectMismatch(delta);
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

    return { numOr, normalizeSizing, visibleRect, aspectOf, aspectDelta, isAspectMismatch, fmtAspect, fmtDelta, viewportAspect, deviceCaps, placementShapeMismatch, normalizePlacement, isSettableContent, sceneContentType, sceneContent, contentSummaryLabel, contentLabel, contentHint };
})();
