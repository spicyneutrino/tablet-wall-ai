"use strict";
(function (root) {
    function selectedViewport(roster, id) {
        const record = roster[id];
        const v = record && record.online === true && record.viewport;
        if (!v || ![v.width, v.height, v.dpr].every(n => typeof n === "number" && Number.isFinite(n) && n > 0)
            || ![0, 90, 180, 270].includes(v.orientation)
            || !["tab", "fullscreen", "standalone"].includes(v.mode)) return null;
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
    const api = { selectedViewport, rulerScale, rulerUrl };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.PhysicalCalibration = api;
}(typeof window !== "undefined" ? window : globalThis));
