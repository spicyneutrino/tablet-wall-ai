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
    function fitLabels(svg) {
        svg.querySelectorAll(".operator-slot-label").forEach(label => {
            const matrix = label.getScreenCTM();
            if (!matrix) return;
            const scale = Math.hypot(matrix.a, matrix.b);
            if (!scale) return;
            const width = Number(label.dataset.width) * scale, height = Number(label.dataset.height) * scale;
            const text = label.dataset.label;
            const size = Math.min(12, height - 8, (width - 12) / (Math.min(4, text.length) * 0.6));
            label.style.display = size < 10 ? "none" : "";
            if (size < 10) return;
            const room = Math.max(1, Math.floor((width - 12) / (size * 0.6)));
            const numbered = /^Tablet (\d+)\b/.exec(text);
            label.textContent = text.length > room && numbered && room <= numbered[0].length ? numbered[1]
                : text.length > room ? text.slice(0, Math.max(1, room - 1)) + "…" : text;
            label.setAttribute("font-size", size / scale);
            label.setAttribute("stroke-width", 0);
            label.setAttribute("x", Number(label.dataset.x) + 6 / scale);
            label.setAttribute("y", Number(label.dataset.y) + (size + 4) / scale);
            const bg = label.previousElementSibling;
            if (bg && bg.classList && bg.classList.contains("operator-slot-label-bg")) {
                const textWidth = typeof label.getComputedTextLength === "function" ? label.getComputedTextLength() : label.textContent.length * size * 0.6 / scale;
                bg.setAttribute("x", Number(label.dataset.x) + 3 / scale);
                bg.setAttribute("y", Number(label.dataset.y) + 1.5 / scale);
                bg.setAttribute("width", textWidth + 6 / scale);
                bg.setAttribute("height", (size + 5) / scale);
                bg.setAttribute("rx", 2 / scale);
            }
        });
    }
    const fits = new WeakMap();
    // Call OperatorStage.fit(el.stageSvg) after renderStage and stage relocation.
    // Optional { actionBar, navigation } elements override the workspace defaults.
    function fit(svg, options = {}) {
        if (svg.classList.contains("is-dragging")) return null;
        const field = svg.closest(".stage-scroll");
        if (!field || !field.parentElement || !svg.viewBox.baseVal.width) return null;
        const win = svg.ownerDocument.defaultView, doc = svg.ownerDocument;
        let state = fits.get(svg);
        if (!state) {
            state = { options, parent: null };
            const schedule = () => {
                if (state.frame) return;
                state.frame = win.requestAnimationFrame(() => { state.frame = 0; fit(svg, state.options); });
            };
            state.observer = new win.ResizeObserver(schedule);
            win.addEventListener("resize", schedule);
            fits.set(svg, state);
        }
        state.options = options;
        if (state.parent !== field.parentElement) {
            state.observer.disconnect();
            state.parent = field.parentElement;
            state.observer.observe(state.parent);
        }
        const parentStyle = win.getComputedStyle(state.parent), fieldStyle = win.getComputedStyle(field);
        const availableWidth = state.parent.clientWidth - parseFloat(parentStyle.paddingLeft) - parseFloat(parentStyle.paddingRight);
        if (availableWidth <= 0 || !field.getClientRects().length) return null;
        const compact = win.matchMedia("(max-width: 48rem), (max-height: 32rem) and (orientation: landscape)").matches;
        const fieldRect = field.getBoundingClientRect();
        const zoom = fieldRect.width / parseFloat(fieldStyle.width) || 1;
        const fieldTop = (fieldRect.top + win.scrollY) / zoom;
        let bottom = win.innerHeight / zoom;
        const navigation = options.navigation || doc.querySelector(".workspace-nav-landmark");
        const actionBar = options.actionBar || doc.querySelector(doc.body.dataset.task === "arrange" ? "#arrange-footer-actions" : ".image-actions");
        for (const bar of [navigation, doc.body.dataset.outputDirty === "true" && actionBar]) {
            if (!bar || !bar.getClientRects().length) continue;
            const rect = bar.getBoundingClientRect();
            if (bar === actionBar) {
                const inline = compact && bottom - fieldTop - rect.height / zoom - 16 < 120 / zoom;
                doc.body.dataset[doc.body.dataset.task === "arrange" ? "arrangeActionsInline" : "imageActionsInline"] = String(inline);
                if (inline) continue;
            }
            const style = win.getComputedStyle(bar);
            if (style.position === "fixed" && rect.bottom / zoom > bottom / 2) bottom = Math.min(bottom, rect.top / zoom - (parseFloat(style.marginTop) || 0));
        }
        const borderWidth = parseFloat(fieldStyle.borderLeftWidth) + parseFloat(fieldStyle.borderRightWidth);
        const borderHeight = parseFloat(fieldStyle.borderTopWidth) + parseFloat(fieldStyle.borderBottomWidth);
        const aspect = svg.viewBox.baseVal.width / svg.viewBox.baseVal.height;
        const width = Math.max(0, availableWidth - borderWidth);
        const commit = doc.body.dataset.task === "arrange" ? doc.querySelector(".arrange-result .arrange-commit") : null;
        const stageTail = Math.max(0, (state.parent.getBoundingClientRect().bottom - fieldRect.bottom) / zoom);
        const reserved = !compact && commit && commit.getClientRects().length ? commit.offsetHeight + stageTail + 16 : 0;
        const availableHeight = bottom - fieldTop - 16 - borderHeight - reserved;
        // A short viewport keeps a usable field and falls back to page scrolling.
        const taskSelector = doc.getElementById("compact-task-select");
        const reflow = taskSelector && taskSelector.getClientRects().length;
        const topInset = navigation && win.getComputedStyle(navigation).position === "sticky" ? navigation.getBoundingClientRect().height / zoom : 0;
        const imagePortrait = compact && doc.body.dataset.task === "images" && win.matchMedia("(orientation: portrait)").matches;
        const height = imagePortrait ? width / aspect : reflow ? Math.min(width / aspect, Math.max(120 / zoom, bottom - topInset - 16))
            : Math.min(width / aspect, Math.max(120 / zoom, availableHeight));
        field.style.inlineSize = Math.min(width, height * aspect) + borderWidth + "px";
        svg.style.inlineSize = Math.min(width, height * aspect) + "px";
        svg.style.blockSize = height + "px";
        fitLabels(svg);
        return { width: Math.min(width, height * aspect), height, availableWidth, availableHeight };
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
        const height = viewport ? viewport.height : 20 + 700 * b.height / b.width;
        const scale = viewport ? viewport.scale : 700 / b.width;
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
        hatch.append(node("path", { d: "M-2 2L2-2 M0 9L9 0 M7 11L11 7", stroke: "var(--stage-line)", "stroke-width": 1, "stroke-opacity": 0.4 }));
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
        world.append(rect(b, { fill: content && content.background || "var(--stage)", stroke: "var(--stage-line)", "stroke-width": 1 / scale }));
        if ((presentation === "arrange" || presentation === "context") && transform && content.url && content.available !== false && content.availability !== "unavailable") world.append(image(0.22));
        const wall = node("g", { "clip-path": "url(#operator-wall-clip)" }); world.append(wall);
        wall.append(rect(b, { fill: "url(#operator-occlusion)" }));
        const visible = node("g", { "clip-path": "url(#operator-panel-clip)" }); wall.append(visible);
        visible.append(rect(b, { fill: content && content.background || "var(--stage)" }));
        if (transform && content.url && content.available !== false && content.availability !== "unavailable") visible.append(image(1));
        const estimates = [], upscaleFactors = [];
        list.sort((a, z) => Number(a.id === selectedId) - Number(z.id === selectedId)).forEach(panel => {
            const status = preview ? { status: "preview", text: "Local preview · not tablet output" } : statusFor(panel.id);
            const group = node("g", { class: "slot operator-slot", role: "button", tabindex: 0,
                "data-device-id": panel.id, "data-status": status.status, "data-preview": String(preview), "aria-pressed": String(panel.id === selectedId),
                "aria-label": labelFor(panel.id) + ", " + status.text + (panel.missing ? ", pinned profile missing" : "") });
            const outline = node("g", { transform: rotation(panel) });
            if (!panel.missing) {
                outline.append(rect(panel.body, { class: "operator-body-outline", fill: "transparent", "stroke-width": (panel.id === selectedId ? 3 : 1.5) / scale }));
                outline.append(rect(panel.active, { class: "operator-active-outline", fill: "none", "stroke-width": 0.75 / scale }));
                const estimate = resolution(panel, transform, content, runtime && runtime.devices && runtime.devices[panel.id]);
                if (estimate && estimate.upscale > 1.1) upscaleFactors.push(estimate.upscale);
                if (estimate) estimates.push(labelFor(panel.id) + " ≈" + estimate.pixels + " source px across" + (estimate.target ? " for " + estimate.target + " output px" : " (output resolution unknown)")
                    + (estimate.upscale > 1.1 ? " · " + estimate.upscale.toFixed(1) + "× upscale" : ""));
            } else outline.append(node("circle", { cx: panel.cx, cy: panel.cy, r: 8 / scale, fill: "none", stroke: "var(--stage-selected)", "stroke-width": 2 / scale }));
            if (!preview && status.status === "offline" && !panel.missing) {
                outline.append(rect(panel.body, { class: "offline-reservation", opacity: 0.18 }));
                outline.append(rect(panel.body, { fill: "url(#operator-occlusion)", opacity: 0.28 }));
            }
            if (!panel.missing) {
                const label = labelFor ? labelFor(panel.id) : "";
                if (label) {
                    outline.append(node("rect", { class: "operator-slot-label-bg", fill: "var(--stage)", opacity: 0.82 }));
                    outline.append(node("text", { x: panel.active.x + 6 / scale, y: panel.active.y + 15 / scale,
                        class: "operator-slot-label", "font-size": 11 / scale, "stroke-width": 0,
                        "data-label": label, "data-x": panel.active.x, "data-y": panel.active.y,
                        "data-width": panel.active.width, "data-height": panel.active.height,
                        "aria-hidden": "true" }, label));
                }
            }
            group.append(outline);
            if (layout.kind === "logical" && panel.id === selectedId && !panel.missing && editable) {
                group.append(rect({ x: panel.body.x + panel.body.width - 10 / scale, y: panel.body.y + panel.body.height - 10 / scale, width: 10 / scale, height: 10 / scale },
                    { class: "logical-resize", fill: "var(--stage-text)", "aria-hidden": "true" }));
            }
            world.append(group);
        });
        syncChildren(svg, view);
        fit(svg, fits.get(svg) && fits.get(svg).options);
        if (resolutionNode) resolutionNode.textContent = estimates.length ? "Estimated sampling. " + estimates.join("; ") + ". Rotation, clipping and gaps may reduce visible detail." : "Resolution estimate needs an image and panel dimensions. Preview does not confirm tablet output.";
        if (focusedId) {
            const target = Array.from(svg.querySelectorAll(".slot")).find(item => item.dataset.deviceId === focusedId);
            if (target) target.focus({ preventScroll: true });
        }
        return stage;
    }
    const api = { panels, resolution, draw, fit };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.OperatorStage = api;
}(typeof window !== "undefined" ? window : globalThis));
