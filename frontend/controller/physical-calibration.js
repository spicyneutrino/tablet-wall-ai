"use strict";
(function (root) {
    function selectedViewport(roster, id) {
        const record = roster[id];
        const v = record && record.online === true && record.viewport;
        if (!v || ![v.width, v.height, v.dpr].every(n => typeof n === "number" && Number.isFinite(n) && n > 0)
            || ![0, 90, 180, 270].includes(v.orientation)
            || !["tab", "fullscreen", "standalone"].includes(v.mode)
            || (v.visual_scale !== undefined && (typeof v.visual_scale !== "number"
                || !Number.isFinite(v.visual_scale) || Math.abs(v.visual_scale - 1) > 0.01))) return null;
        return { width: v.width, height: v.height, dpr: v.dpr, orientation: v.orientation, mode: v.mode };
    }
    function rulerScale(measuredX, measuredY, spanX, spanY) {
        const values = [measuredX, measuredY, spanX, spanY].map(Number);
        if (!values.every(n => Number.isFinite(n) && n > 0)) throw new Error("Enter positive measured lengths and CSS spans for both lines.");
        const scale = [values[0] / values[2], values[1] / values[3]];
        if (!scale.every(n => Number.isFinite(n) && n > 0)) throw new Error("Ruler scale must be finite and positive.");
        return scale;
    }
    function rulerUrl(origin) {
        try {
            const url = new URL(origin);
            const host = url.hostname.toLowerCase().replace(/\.+$/, "");
            if (!["http:", "https:"].includes(url.protocol) || url.username || url.password
                || host === "localhost" || host.endsWith(".localhost") || host === "[::1]"
                || /^127\./.test(host)) return null;
            return new URL("/client/?calibrate=1", url.origin).href;
        } catch (_) { return null; }
    }
    function rulerCheckBodies(deviceId, profileRevision, quarterTurn, viewport, measurements) {
        if (!viewport) throw new Error("Capture the selected tablet's online viewport first.");
        if (!Number.isInteger(profileRevision) || profileRevision < 1) throw new Error("Choose an existing profile revision.");
        if (![0, 1, 2, 3].includes(quarterTurn)) throw new Error("Choose the native-panel quarter turn first.");
        rulerScale(measurements.x.mm, measurements.y.mm, measurements.x.px, measurements.y.px);
        return ["x", "y"].map(axis => {
            const error = measurements[axis].error;
            if (error === "" || !Number.isFinite(Number(error)) || Number(error) < 0) {
                throw new Error("Enter an estimated ruler error in mm for each axis, including zero if appropriate.");
            }
            return {
                device_id: deviceId, profile_revision: profileRevision, quarter_turn: quarterTurn,
                axis, span_px: Number(measurements[axis].px), span_mm: Number(measurements[axis].mm),
                span_error_mm: Number(error), usable_width_px: viewport.width, usable_height_px: viewport.height
            };
        });
    }
    class RulerReview {
        constructor() { this.reset(); }
        reset() { this.status = "idle"; this.key = null; this.results = null; }
        begin(key) { this.key = key; this.results = null; this.status = "checking"; }
        accept(key, results) {
            if (this.status !== "checking" || this.key !== key) return false;
            this.results = results;
            this.status = "review";
            return true;
        }
        decide(choice) {
            if (this.status !== "review") throw new Error("Check the current ruler measurements before choosing.");
            if (!["keep_supplied", "use_ruler", "remeasure"].includes(choice)) throw new Error("Choose a ruler decision.");
            this.status = { keep_supplied: "kept", use_ruler: "prepared", remeasure: "stale" }[choice];
        }
        invalidate() { if (this.status !== "idle") this.status = "stale"; }
        canSave(key) { return this.status === "prepared" && this.key === key; }
    }
    const api = { selectedViewport, rulerScale, rulerUrl, rulerCheckBodies, RulerReview };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.PhysicalCalibration = api;
}(typeof window !== "undefined" ? window : globalThis));
