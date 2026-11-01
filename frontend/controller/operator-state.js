"use strict";
(function (root) {
    const clone = value => JSON.parse(JSON.stringify(value));
    const entries = layout => layout && (layout.kind === "physical" ? layout.slots : layout.placements) || {};
    function layoutDraft(layout) {
        if (!layout || !["physical", "logical", undefined].includes(layout.kind)) throw new Error("Unsupported layout. Update the console before editing.");
        const draft = clone(layout);
        draft.kind = draft.kind || "logical";
        draft.sizing = draft.sizing || { mode: "fixed", padding: 0 };
        // Existing physical editing and experimental playback read slots on both kinds.
        if (draft.kind === "logical") draft.slots = {};
        return draft;
    }
    function bounds(layout) {
        return layout.kind === "physical" ? layout.bounds : { x: 0, y: 0, width: layout.width, height: layout.height };
    }
    function fitTransform(layout, content) {
        const b = bounds(layout);
        const width = content.intrinsicWidth, height = content.intrinsicHeight;
        if (![b.width, b.height, width, height].every(n => typeof n === "number" && Number.isFinite(n) && n > 0)) return null;
        const scale = (content.fit === "contain" ? Math.min : Math.max)(b.width / width, b.height / height);
        return { x: b.x + (b.width - width * scale) / 2, y: b.y + (b.height - height * scale) / 2,
            width: width * scale, height: height * scale, scale,
            cropX: Math.max(0, 1 - b.width / (width * scale)),
            cropY: Math.max(0, 1 - b.height / (height * scale)) };
    }
    function compareIds(roster, labels, a, b) {
        const number = id => Number.isInteger(roster[id] && roster[id].number) && roster[id].number > 0 ? roster[id].number : Infinity;
        const label = id => String(labels[id] || roster[id] && roster[id].label || "").trim().toLowerCase();
        return number(a) - number(b) || label(a).localeCompare(label(b)) || a.localeCompare(b);
    }
    function sameToken(a, b) {
        return !!a && !!b && ["connection_id", "generation", "revision", "render_seq", "mapping_revision", "asset"]
            .every(key => a[key] !== undefined && a[key] === b[key]);
    }
    function tabletState(config, id, nowMs) {
        const slot = entries(config.layout)[id];
        const device = config.runtime && config.runtime.devices && config.runtime.devices[id];
        const result = (status, text, showing = false) => ({ status, text, showing, online: !!device && device.online === true });
        if (!slot) return result("unplaced", "Not on the wall");
        if (!device) return result("unknown", "Missing tablet · spot reserved");
        if (slot.participating === false) return result("excluded", "Excluded from show");
        if (!device.online) return result("offline", "Offline · spot reserved");
        const mapping = device.mapping || {};
        if (mapping.status && mapping.status !== "ready") return result(mapping.status, mapping.reason || mapping.status.replaceAll("_", " "));
        if (config.layout.kind === "physical" && ((mapping.profile_revision !== undefined && mapping.profile_revision !== slot.profile_revision)
                || (mapping.calibration_revision !== undefined && mapping.calibration_revision !== slot.calibration_revision))) return result("stale", "Active mapping revisions differ from the pinned slot");
        if (device.identify && !["cleared", "expired"].includes(device.identify.status)) return result("identifying", "Identify overlay · image obscured");
        if (config.runtime.presentation && config.runtime.presentation.owner === "playback") return result("playback", "Experimental playback owns the display");
        const render = device.render || {};
        const status = render.status || "unknown";
        if (device.protocol !== 3 || !(device.caps || []).includes("render_ack")) return result("unknown", "No confirmation · update client or check manually");
        if (status === "displayed") {
            const expected = render.expected_token;
            const accepted = render.token || render.last_token;
            const observed = render.observed_at || config.runtime.observed_at;
            const elapsed = observed ? Math.max(0, nowMs - Date.parse(observed)) : 0;
            const age = typeof render.age_ms === "number" ? render.age_ms + elapsed
                : render.received_at ? nowMs - Date.parse(render.received_at) : Infinity;
            const content = config.scene && config.scene.content || {};
            if (!sameToken(expected, accepted) || !Number.isFinite(age) || age < 0 || age > 15000
                    || expected.generation !== config.generation || expected.revision !== config.revision
                    || expected.asset !== (content.type === "image" ? content.asset : null) || mapping.status !== "ready") {
                return result("stale", "Previous paint · current image unconfirmed");
            }
            return result("displayed", content.type === "image" ? "Showing current image" : "Current scene displayed", content.type === "image");
        }
        const texts = { blocked: "Blocked", loading: "Loading image", failed: "Image failed", hidden: "Page hidden",
            stale: "Confirmation expired", unsupported: "Unsupported client or content", unplaced: "Not on the wall", unknown: "Image unconfirmed" };
        return result(status in texts ? status : "unknown", (texts[status] || texts.unknown) + (render.reason ? " · " + render.reason : ""));
    }
    function aggregate(config, nowMs) {
        const ids = Object.keys(entries(config.layout)).filter(id => entries(config.layout)[id].participating !== false);
        const states = ids.map(id => tabletState(config, id, nowMs));
        return { total: ids.length, showing: states.filter(item => item.showing).length, states };
    }
    function readFence() {
        let epoch = 0, issued = 0, accepted = 0;
        return { event() { epoch += 1; }, start() { return { epoch, sequence: ++issued }; },
            accept(ticket) { if (ticket.epoch !== epoch || ticket.sequence < accepted) return false; accepted = ticket.sequence; return true; } };
    }
    const api = { clone, entries, layoutDraft, bounds, fitTransform, compareIds, sameToken, tabletState, aggregate, readFence };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.OperatorState = api;
}(typeof window !== "undefined" ? window : globalThis));
