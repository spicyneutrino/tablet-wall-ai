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
    function syncChildren(parent, next) {
        const remaining = Array.from(parent.children);
        const key = item => item.tagName + ":" + (item.getAttribute("data-device-id") || item.id || item.getAttribute("class") || "");
        for (const [index, proposed] of Array.from(next.children).entries()) {
            const current = remaining.find(item => key(item) === key(proposed));
            if (!current) { parent.insertBefore(proposed, parent.children[index] || null); continue; }
            remaining.splice(remaining.indexOf(current), 1);
            for (const attr of Array.from(current.attributes)) if (!proposed.hasAttribute(attr.name)) current.removeAttribute(attr.name);
            for (const attr of proposed.attributes) if (current.getAttribute(attr.name) !== attr.value) current.setAttribute(attr.name, attr.value);
            if (proposed.children.length || current.children.length) syncChildren(current, proposed);
            else if (current.textContent !== proposed.textContent) current.textContent = proposed.textContent;
            if (parent.children[index] !== current) parent.insertBefore(current, parent.children[index] || null);
        }
        remaining.forEach(item => item.remove());
    }
    function draw({ svg, layout, content, profileFor, labelFor, statusFor, selectedId, runtime, resolutionNode, preview = false, editable = true, presentation = "context", viewport = null }) {
        const ns = "http://www.w3.org/2000/svg";
        const node = (tag, attrs, text) => {
            const item = document.createElementNS(ns, tag);
            Object.entries(attrs || {}).forEach(([key, value]) => item.setAttribute(key, String(value)));
            if (text) item.textContent = text;
            return item;
        };
        const b = model.bounds(layout);
        const width = 720;
        const height = viewport ? viewport.height : Math.max(160, Math.min(720, 56 + 664 * b.height / b.width));
        const scale = viewport ? viewport.scale : Math.min(664 / b.width, (height - 56) / b.height);
        const offX = viewport ? viewport.offX : width / 2 - (b.x + b.width / 2) * scale;
        const offY = viewport ? viewport.offY : height / 2 - (b.y + b.height / 2) * scale;
        const stage = { scale, offX, offY, width, height, step: 50 };
        svg.setAttribute("viewBox", "0 0 " + width + " " + height);
        svg.style.setProperty("--stage-aspect", width / height);
        svg.dataset.presentation = presentation;
        svg.setAttribute("aria-label", editable
            ? "Wall. Select a tablet and drag it, or use the arrow keys to nudge the selected tablet."
            : "Wall preview. Select a tablet to inspect its identity and status.");
        const focused = document.activeElement;
        const focusedId = focused && focused.closest && focused.closest(".slot") && focused.closest(".slot").dataset.deviceId;
        const view = node("svg");
        const defs = node("defs");
        const wallClip = node("clipPath", { id: "operator-wall-clip", clipPathUnits: "userSpaceOnUse" });
        wallClip.append(node("rect", b)); defs.append(wallClip);
        const panelClip = node("clipPath", { id: "operator-panel-clip", clipPathUnits: "userSpaceOnUse" });
        const hatch = node("pattern", { id: "operator-occlusion", width: 9, height: 9, patternUnits: "userSpaceOnUse" });
        hatch.append(node("path", { d: "M-2 2L2-2 M0 9L9 0 M7 11L11 7", stroke: "#75828d", "stroke-width": 1 }));
        defs.append(hatch, panelClip); view.append(defs);
        const world = node("g", { transform: "translate(" + offX + " " + offY + ") scale(" + scale + ")" });
        view.append(world);
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
        if ((presentation === "arrange" || presentation === "context") && transform && content.url && content.available !== false && content.availability !== "unavailable") world.append(image(0.22));
        const wall = node("g", { "clip-path": "url(#operator-wall-clip)" }); world.append(wall);
        wall.append(rect(b, { fill: "url(#operator-occlusion)" }));
        const visible = node("g", { "clip-path": "url(#operator-panel-clip)" }); wall.append(visible);
        visible.append(rect(b, { fill: content && content.background || "#0b1120" }));
        if (transform && content.url && content.available !== false && content.availability !== "unavailable") visible.append(image(1));
        const estimates = [], upscaleFactors = [];
        list.sort((a, z) => Number(a.id === selectedId) - Number(z.id === selectedId)).forEach(panel => {
            const status = preview ? { status: "preview", text: "Local preview · not tablet output" } : statusFor(panel.id);
            const group = node("g", { class: "slot operator-slot", role: "button", tabindex: 0,
                "data-device-id": panel.id, "data-status": status.status, "data-preview": String(preview), "aria-pressed": String(panel.id === selectedId),
                "aria-label": labelFor(panel.id) + ", " + status.text + (panel.missing ? ", pinned profile missing" : "") });
            const outline = node("g", { transform: rotation(panel) });
            if (!panel.missing) {
                outline.append(rect(panel.body, { class: "operator-body-outline", fill: "transparent", stroke: panel.id === selectedId ? "#f4b942" : "#e5edf2", "stroke-width": (panel.id === selectedId ? 3 : 1.5) / scale }));
                outline.append(rect(panel.active, { class: "operator-active-outline", fill: "none", stroke: "#a8bcc6", "stroke-width": 0.75 / scale }));
                const estimate = resolution(panel, transform, content, runtime && runtime.devices && runtime.devices[panel.id]);
                if (estimate && estimate.upscale > 1.1) upscaleFactors.push(estimate.upscale);
                if (estimate) estimates.push(labelFor(panel.id) + " ≈" + estimate.pixels + " source px across" + (estimate.target ? " for " + estimate.target + " output px" : " (output resolution unknown)")
                    + (estimate.upscale > 1.1 ? " · " + estimate.upscale.toFixed(1) + "× upscale" : ""));
            } else outline.append(node("circle", { cx: panel.cx, cy: panel.cy, r: 8 / scale, fill: "none", stroke: "#f4b942", "stroke-width": 2 / scale }));
            if (!preview && status.status === "offline" && !panel.missing) {
                outline.append(rect(panel.body, { class: "offline-reservation", fill: "#171b20", opacity: 0.78 }));
                outline.append(rect(panel.body, { fill: "url(#operator-occlusion)", opacity: 0.7 }));
            }
            group.append(outline);
            if (layout.kind === "logical" && panel.id === selectedId && !panel.missing && editable) {
                group.append(rect({ x: panel.body.x + panel.body.width - 10 / scale, y: panel.body.y + panel.body.height - 10 / scale, width: 10 / scale, height: 10 / scale },
                    { class: "logical-resize", fill: "#e5edf2", "aria-hidden": "true" }));
            }
            world.append(group);
        });
        syncChildren(svg, view);
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
