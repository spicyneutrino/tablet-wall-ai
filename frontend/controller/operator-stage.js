"use strict";
(function (root) {
    const model = typeof module !== "undefined" && module.exports ? require("./operator-state.js") : root.OperatorState;
    function panels(layout, profileFor) {
        return Object.entries(model.entries(layout)).map(([id, slot]) => {
            if (layout.kind !== "physical") {
                const bezel = slot.bezel || {};
                return { id, slot, body: { x: slot.x, y: slot.y, width: slot.w, height: slot.h },
                    active: { x: slot.x + (bezel.left || 0), y: slot.y + (bezel.top || 0),
                        width: slot.w - (bezel.left || 0) - (bezel.right || 0), height: slot.h - (bezel.top || 0) - (bezel.bottom || 0) }, angle: 0 };
            }
            const profile = profileFor(id, slot.profile_revision);
            const cx = slot.center_x_mm + (slot.nudge_x_mm || 0), cy = slot.center_y_mm + (slot.nudge_y_mm || 0);
            if (!profile) return { id, slot, missing: true, cx, cy };
            const bezel = profile.bezels || {};
            const width = profile.active_width_mm + (bezel.left || 0) + (bezel.right || 0);
            const height = profile.active_height_mm + (bezel.top || 0) + (bezel.bottom || 0);
            return { id, slot, profile, cx, cy, angle: slot.mount_angle || 0,
                body: { x: cx - width / 2, y: cy - height / 2, width, height },
                active: { x: cx - width / 2 + (bezel.left || 0), y: cy - height / 2 + (bezel.top || 0),
                    width: profile.active_width_mm, height: profile.active_height_mm } };
        });
    }
    function resolution(panel, transform, content, device) {
        if (!transform || panel.missing) return null;
        const pixels = Math.round(Math.min(content.intrinsicWidth, panel.active.width / transform.scale));
        const target = panel.profile && panel.profile.panel_pixels_width
            || device && device.viewport && Math.round(device.viewport.width * device.viewport.dpr);
        return { pixels, target: target || null, upscale: target ? target / Math.max(1, pixels) : null };
    }
    function draw({ svg, layout, content, profileFor, labelFor, statusFor, selectedId, runtime, resolutionNode }) {
        const ns = "http://www.w3.org/2000/svg";
        const node = (tag, attrs, text) => {
            const item = document.createElementNS(ns, tag);
            Object.entries(attrs || {}).forEach(([key, value]) => item.setAttribute(key, String(value)));
            if (text) item.textContent = text;
            return item;
        };
        const b = model.bounds(layout);
        const scale = Math.min(664 / b.width, 424 / b.height);
        const offX = 360 - (b.x + b.width / 2) * scale, offY = 240 - (b.y + b.height / 2) * scale;
        const stage = { scale, offX, offY, step: 50 };
        const focused = document.activeElement;
        const focusedId = focused && focused.closest && focused.closest(".slot") && focused.closest(".slot").dataset.deviceId;
        svg.replaceChildren();
        const defs = node("defs");
        const wallClip = node("clipPath", { id: "operator-wall-clip", clipPathUnits: "userSpaceOnUse" });
        wallClip.append(node("rect", b)); defs.append(wallClip);
        const panelClip = node("clipPath", { id: "operator-panel-clip", clipPathUnits: "userSpaceOnUse" });
        const hatch = node("pattern", { id: "operator-occlusion", width: 9, height: 9, patternUnits: "userSpaceOnUse" });
        hatch.append(node("path", { d: "M-2 2L2-2 M0 9L9 0 M7 11L11 7", stroke: "#75828d", "stroke-width": 1 }));
        defs.append(hatch, panelClip); svg.append(defs);
        const world = node("g", { transform: "translate(" + offX + " " + offY + ") scale(" + scale + ")" });
        svg.append(world);
        const list = panels(layout, profileFor);
        const rect = (shape, attributes) => node("rect", Object.assign({}, shape, attributes));
        const rotation = panel => panel.angle ? "rotate(" + panel.angle + " " + panel.cx + " " + panel.cy + ")" : "rotate(0)";
        list.filter(panel => !panel.missing && panel.slot.participating !== false).forEach(panel => {
            panelClip.append(rect(panel.active, { transform: rotation(panel) }));
        });
        const transform = content && content.type === "image" && model.fitTransform(layout, content);
        const image = opacity => node("image", { href: content.url, x: transform.x, y: transform.y,
            width: transform.width, height: transform.height, preserveAspectRatio: "none", opacity });
        world.append(rect(b, { fill: content && content.background || "#0b1120", stroke: "#778793", "stroke-width": 1 / scale }));
        if (transform && content.url && content.available !== false && content.availability !== "unavailable") world.append(image(0.22));
        const wall = node("g", { "clip-path": "url(#operator-wall-clip)" }); world.append(wall);
        wall.append(rect(b, { fill: "url(#operator-occlusion)" }));
        const visible = node("g", { "clip-path": "url(#operator-panel-clip)" }); wall.append(visible);
        visible.append(rect(b, { fill: content && content.background || "#0b1120" }));
        if (transform && content.url && content.available !== false && content.availability !== "unavailable") visible.append(image(1));
        const estimates = [], upscaleFactors = [];
        const cssRatio = 720 / (svg.getBoundingClientRect().width || 720);
        list.sort((a, z) => Number(a.id === selectedId) - Number(z.id === selectedId)).forEach(panel => {
            const status = statusFor(panel.id);
            const group = node("g", { class: "slot operator-slot", role: "button", tabindex: 0,
                "data-device-id": panel.id, "aria-pressed": String(panel.id === selectedId),
                "aria-label": labelFor(panel.id) + ", " + status.text + (panel.missing ? ", pinned profile missing" : "") });
            const outline = node("g", { transform: rotation(panel) });
            if (!panel.missing) {
                outline.append(rect(panel.body, { fill: "transparent", stroke: panel.id === selectedId ? "#f4b942" : "#e5edf2", "stroke-width": (panel.id === selectedId ? 3 : 1.5) / scale }));
                outline.append(rect(panel.active, { fill: "none", stroke: "#a8bcc6", "stroke-width": 0.75 / scale }));
                const estimate = resolution(panel, transform, content, runtime && runtime.devices && runtime.devices[panel.id]);
                if (estimate && estimate.upscale > 1.1) upscaleFactors.push(estimate.upscale);
                if (estimate) estimates.push(labelFor(panel.id) + " ≈" + estimate.pixels + " source px across" + (estimate.target ? " for " + estimate.target + " output px" : " (output resolution unknown)")
                    + (estimate.upscale > 1.1 ? " · " + estimate.upscale.toFixed(1) + "× upscale" : ""));
            } else outline.append(node("circle", { cx: panel.cx, cy: panel.cy, r: 8 / scale, fill: "none", stroke: "#f4b942", "stroke-width": 2 / scale }));
            group.append(outline);
            const center = panel.missing ? { x: panel.cx, y: panel.cy } : { x: panel.body.x + panel.body.width / 2, y: panel.body.y + panel.body.height / 2 };
            const text = node("text", { x: center.x, y: center.y, class: "operator-slot-label", "font-size": 12 * cssRatio / scale, "text-anchor": "middle", "pointer-events": "none" });
            const labelLimit = panel.missing ? 20 : Math.max(8, Math.min(36, Math.floor(panel.body.width * scale / cssRatio / 7)));
            const label = labelFor(panel.id);
            text.append(node("tspan", { x: center.x, dy: 0 }, label.length > labelLimit ? label.slice(0, labelLimit - 1) + "…" : label));
            const statusLabels = { displayed: "Showing", loading: "Loading", offline: "Offline reserved", unknown: "Unconfirmed", identifying: "Identifying", failed: "Image failed", excluded: "Excluded" };
            text.append(node("tspan", { x: center.x, dy: 16 * cssRatio / scale, "font-size": 11 * cssRatio / scale }, statusLabels[status.status] || status.status.replaceAll("_", " ")));
            group.append(text); world.append(group);
        });
        if (!list.length) svg.append(node("text", { x: 360, y: 240, "text-anchor": "middle", class: "stage-note" }, "No tablets on the wall. Choose tablets in Layout & size."));
        if (resolutionNode) resolutionNode.textContent = estimates.length ? "Estimated sampling. " + estimates.join("; ") + ". Rotation, clipping and gaps may reduce visible detail." : "Resolution estimate needs an image and panel dimensions. Preview does not confirm tablet output.";
        const quality = document.getElementById("stage-quality-summary");
        if (quality) quality.textContent = upscaleFactors.length ? "Estimated upscaling up to " + Math.max(...upscaleFactors).toFixed(1) + "×. Check resolution estimates." : "";
        if (focusedId) {
            const target = Array.from(svg.querySelectorAll(".slot")).find(item => item.dataset.deviceId === focusedId);
            if (target) target.focus({ preventScroll: true });
        }
        return stage;
    }
    const api = { panels, resolution, draw };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.OperatorStage = api;
}(typeof window !== "undefined" ? window : globalThis));
