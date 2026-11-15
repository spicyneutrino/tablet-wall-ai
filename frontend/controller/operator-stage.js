"use strict";
(function (root) {
    const model = typeof module !== "undefined" && module.exports ? require("./operator-state.js") : root.OperatorState;
    const WAKE_STATES = {
        held: { label: "held", warning: false, guidance: "The browser reports the screen wake lock held. This is not proof the operating system will keep the screen on; check Auto-Lock, charging and kiosk settings." },
        released: { label: "released", warning: true, guidance: "The browser reports the screen wake lock released. Bring the tablet page to the foreground and check Auto-Lock, charging and kiosk settings. The operator cannot wake the tablet remotely." },
        denied: { label: "denied", warning: true, guidance: "The browser denied the screen wake lock. Allow it in the browser and check the trusted origin, Auto-Lock, charging and kiosk settings. The operator cannot wake the tablet remotely." },
        insecure: { label: "insecure origin", warning: true, guidance: "This page is not a trusted secure origin, so the screen wake lock is unavailable. Open the wall over its configured trusted HTTPS origin, then check Auto-Lock, charging and kiosk settings. The operator cannot wake the tablet remotely." },
        unsupported: { label: "unsupported", warning: false, guidance: "This browser does not report a screen wake lock. Keep the tablet charging and check Auto-Lock and kiosk settings. The operator cannot wake the tablet remotely." },
        unknown: { label: "unknown", warning: false, guidance: "The tablet has not reported a screen wake-lock state. Check the current tablet page, Auto-Lock, charging and kiosk settings. The operator cannot wake the tablet remotely." }
    };
    const EXCEPTION_LABELS = { loading: "Loading", unknown: "Unconfirmed", excluded: "Excluded", identifying: "Identify", playback: "Playback" };
    function exceptionLabel(status) {
        if (!status || status === "displayed" || status === "preview") return "";
        const roster = model.rosterStatus({ status, online: status !== "offline" });
        if (roster.key !== "connected") return roster.word;
        if (EXCEPTION_LABELS[status]) return EXCEPTION_LABELS[status];
        return "Needs review";
    }
    function powerReadiness(device, options = {}) {
        const state = device && typeof device.wake_lock === "string" && Object.prototype.hasOwnProperty.call(WAKE_STATES, device.wake_lock)
            ? device.wake_lock : "unknown";
        const entry = WAKE_STATES[state];
        const offline = !!device && device.online === false;
        const stale = options.stale === true || offline;
        const checkedAt = offline && device.last_seen || options.checkedAt || null;
        const checked = checkedAt ? Date.parse(checkedAt) : NaN;
        const stamp = stale && Number.isFinite(checked)
            ? " Last checked " + new Date(checked).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) + "." : "";
        const label = stale ? "Last known wake lock " + entry.label + " · status stale" : "Wake lock: " + entry.label;
        const report = state === "denied" ? "Denied by browser" : entry.label[0].toUpperCase() + entry.label.slice(1);
        return { state, stale, warning: entry.warning, label, report: (stale ? "Last known · " : "") + report,
            short: stale ? "Last known wake lock " + entry.label : "Wake lock " + entry.label,
            fact: stale ? "Last known browser wake-lock state: " + entry.label + "." : entry.guidance,
            guidance: stale ? (offline ? "Tablet is offline; this is the last known report." : "Status is stale; this is the last known report.")
                + stamp + " Last known browser wake-lock state: " + entry.label + ". " + powerHelp : entry.guidance,
            checkedAt };
    }
    function fleetPower(entries) {
        const online = entries.filter(entry => entry.online);
        if (online.length < 2) return null;
        const power = online[0].power;
        if (!power || !(power.warning || power.state === "unknown")
                || !online.every(entry => entry.power && entry.power.stale === false && entry.power.state === power.state)) return null;
        return { state: power.state, label: WAKE_STATES[power.state].label, count: online.length };
    }
    const powerHelp = "Screen wake locks are browser reports, not proof the operating system will keep the screen on. "
        + "Check Auto-Lock, charging and kiosk settings. An insecure origin cannot take a wake lock, so open the wall over its trusted HTTPS origin. "
        + "The operator cannot wake a sleeping tablet remotely.";
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
    function viewZoom(svg) {
        const body = svg && svg.ownerDocument && svg.ownerDocument.body;
        return body && body.dataset && body.dataset.viewZoom === "2x" ? "2x" : "fit";
    }
    function viewSize(width, height, zoom) {
        const zoomed = zoom === "2x";
        return { zoom: zoomed ? "2x" : "fit", inlineSize: zoomed ? width * 2 : width,
            blockSize: zoomed ? height * 2 : height, fieldBlockSize: zoomed ? height : null,
            overflow: zoomed ? "auto" : "" };
    }
    function helpText(editable, kind) {
        if (!editable) {
            return "Wall preview. Select a tablet to inspect its identity and status. Numeric position and size fields are available in Arrange when a draft is editable. " + powerHelp;
        }
        if (kind === "physical") {
            return "Wall. Select a tablet and drag it, or use the arrow keys to nudge it by 1 millimetre, or Shift with an arrow for 10 millimetres. "
                + "Escape cancels a drag. Measured positions use decimal millimetres and pinned measurements; numeric centre, nudge, angle and measurement fields are in Arrange. " + powerHelp;
        }
        return "Wall. Select a tablet and drag it, or use the arrow keys to move it by 1 wall unit, or Shift with an arrow for 10 units. "
            + "Escape cancels a drag. Alt pauses snapping while dragging with a mouse or pen; on touch use the snap checkbox. "
            + "Numeric position, size and bezel fields are available in Arrange. Fit and 2x change the view only. " + powerHelp;
    }
    const LABEL_MAX = 16;
    function fitLabels(svg) {
        const labels = [...svg.querySelectorAll(".operator-slot-label")].map(label => {
            const matrix = label.getScreenCTM();
            const scale = matrix ? Math.hypot(matrix.a, matrix.b) : 0;
            if (!scale) return null;
            const width = Number(label.dataset.width) * scale, height = Number(label.dataset.height) * scale;
            const fit = Math.min(LABEL_MAX, height - 8, (width - 12) / (Math.min(4, label.dataset.label.length) * 0.6));
            return { label, scale, width, fit };
        }).filter(Boolean);
        const numberedWall = labels.some(({ label, width }) => label.dataset.label.length * LABEL_MAX * 0.6 > width - 12);
        const wallSize = Math.min(LABEL_MAX, ...labels.map(item => item.fit));
        labels.forEach(({ label, scale }) => {
            const text = label.dataset.label;
            const size = Math.max(1, wallSize);
            const numbered = /^Tablet (\d+)\b/.exec(text);
            label.style.display = "";
            label.textContent = numberedWall && numbered ? numbered[1] : text;
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
        const statusLabels = [...svg.querySelectorAll(".operator-slot-status")].map(label => {
            if (!label.classList || !label.classList.contains("operator-slot-status")) return;
            const matrix = label.getScreenCTM();
            if (!matrix) return;
            const scale = Math.hypot(matrix.a, matrix.b);
            if (!scale) return;
            const width = Number(label.dataset.width) * scale, height = Number(label.dataset.height) * scale;
            let text = label.dataset.label || "";
            const offline = label.dataset.status === "offline";
            if (offline && (width - 12) / (Math.max(1, text.length) * 0.6) < 9) text = "Offline";
            const fit = Math.min(LABEL_MAX, height - 10, (width - 12) / (Math.max(1, text.length) * 0.6));
            return { label, scale, width, height, text, offline, fit };
        }).filter(Boolean);
        const statusSize = Math.min(LABEL_MAX, ...statusLabels.map(item => item.fit).filter(fit => fit >= 9));
        statusLabels.forEach(({ label, scale, width, height, text, offline, fit }) => {
            label.textContent = text;
            const size = Math.min(statusSize, fit);
            const room = Math.max(1, Math.floor((width - 12) / (Math.max(1, size) * 0.6)));
            const fits = offline || size >= 9 && text.length <= room;
            label.style.display = fits ? "" : "none";
            if (!fits) return;
            label.setAttribute("font-size", size / scale);
            label.setAttribute("stroke-width", 2 / scale);
            if (offline) {
                label.setAttribute("text-anchor", "middle");
                label.setAttribute("x", Number(label.dataset.x) + Number(label.dataset.width) / 2);
                label.setAttribute("y", Number(label.dataset.y) + Number(label.dataset.height) / 2 + size / 3 / scale);
                return;
            }
            label.setAttribute("x", Number(label.dataset.x) + 6 / scale);
            label.setAttribute("y", Number(label.dataset.y) + height / scale - 6 / scale);
        });
    }
    function fit(svg, available, { field = svg.closest(".stage-scroll") } = {}) {
        if (svg.classList.contains("is-dragging")) return null;
        const { width, height: availableHeight, borderWidth = 0, borderHeight = 0 } = available;
        const aspect = svg.viewBox.baseVal.width / svg.viewBox.baseVal.height;
        const height = Math.min(availableHeight, width / aspect);
        const fitWidth = Math.min(width, height * aspect);
        const size = viewSize(fitWidth, height, viewZoom(svg));
        field.style.inlineSize = fitWidth + borderWidth + "px";
        field.style.blockSize = size.fieldBlockSize === null ? ""
            : Math.min(size.fieldBlockSize, available.scrollHeight || availableHeight) + borderHeight + "px";
        field.style.overflow = size.overflow;
        svg.style.inlineSize = size.inlineSize + "px";
        svg.style.blockSize = size.blockSize + "px";
        fitLabels(svg);
        return { width: fitWidth, height, availableWidth: available.availableWidth ?? width,
            availableHeight: available.availableHeight ?? availableHeight, zoom: size.zoom };
    }
    function draw({ svg, layout, content, profileFor, labelFor, statusFor, powerFor = null, fleet = null, selectedId, runtime, resolutionNode, preview = false, editable = true, presentation = "context", viewport = null, compareIds = null }) {
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
        svg.setAttribute("aria-label", helpText(editable, layout.kind));
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
        if ((presentation === "arrange" || presentation === "context") && transform && content.url && content.available !== false && content.availability !== "unavailable") world.append(image(0.035));
        const wall = node("g", { "clip-path": "url(#operator-wall-clip)" }); world.append(wall);
        wall.append(rect(b, { fill: "url(#operator-occlusion)" }));
        const visible = node("g", { "clip-path": "url(#operator-panel-clip)" }); wall.append(visible);
        visible.append(rect(b, { fill: content && content.background || "var(--stage)" }));
        if (transform && content.url && content.available !== false && content.availability !== "unavailable") visible.append(image(1));
        const estimates = [], upscaleFactors = [];
        list.sort((a, z) => compareIds ? compareIds(a.id, z.id) : Number(a.id === selectedId) - Number(z.id === selectedId)).forEach(panel => {
            const reported = statusFor(panel.id);
            const status = preview && reported.status !== "offline" ? { status: "preview", text: "Local preview · not tablet output" } : reported;
            const power = powerFor ? powerFor(panel.id) : null;
            const group = node("g", { class: "slot operator-slot", role: "button", tabindex: 0,
                "data-device-id": panel.id, "data-status": status.status, "data-preview": String(preview), "aria-pressed": String(panel.id === selectedId),
                "data-power-state": power ? power.state : "unknown", "data-power-warning": String(!!power && power.warning),
                "data-power-stale": String(!!power && power.stale),
                "aria-label": labelFor(panel.id) + ", " + status.text + (power ? ", " + power.label : "") + (panel.missing ? ", pinned profile missing" : "") });
            const outline = node("g", { transform: rotation(panel) });
            if (!panel.missing) {
                if (panel.id === selectedId) outline.append(rect(panel.body, { class: "operator-selection-halo", fill: "none", stroke: "#000", "stroke-width": 8 / scale }));
                outline.append(rect(panel.body, { class: "operator-body-outline", fill: "transparent", "stroke-width": (panel.id === selectedId ? 3 : 1.5) / scale }));
                outline.append(rect(panel.active, { class: "operator-active-outline", fill: "none", "stroke-width": 0.75 / scale }));
                const estimate = resolution(panel, transform, content, runtime && runtime.devices && runtime.devices[panel.id]);
                if (estimate && estimate.upscale > 1.1) upscaleFactors.push(estimate.upscale);
                if (estimate) estimates.push(labelFor(panel.id) + " ≈" + estimate.pixels + " source px across" + (estimate.target ? " for " + estimate.target + " output px" : " (output resolution unknown)")
                    + (estimate.upscale > 1.1 ? " · " + estimate.upscale.toFixed(1) + "× upscale" : ""));
            } else outline.append(node("circle", { cx: panel.cx, cy: panel.cy, r: 8 / scale, fill: "none", stroke: "var(--stage-selected)", "stroke-width": 2 / scale }));
            if (!preview && status.status === "offline" && !panel.missing) {
                outline.append(rect(panel.body, { class: "offline-reservation", opacity: 0.45 }));
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
            const exception = exceptionLabel(status.status, status.text);
            if (!panel.missing && exception) {
                const size = 7 / scale, right = panel.body.x + panel.body.width, top = panel.body.y;
                outline.append(node("path", { class: "operator-slot-exception", "data-status": status.status,
                    d: "M " + (right - size) + " " + top + " L " + right + " " + top + " L " + right + " " + (top + size) + " Z",
                    fill: status.status === "failed" ? "var(--error-bg)" : "var(--attention-bg)",
                    stroke: status.status === "failed" ? "var(--error)" : "var(--attention)",
                    "stroke-width": 1 / scale, "aria-hidden": "true" }));
            }
            if (!panel.missing && power && (power.warning || power.stale || power.state === "unknown")) {
                const radius = 4 / scale;
                outline.append(node("circle", { class: "operator-slot-power", "data-power-state": power.state,
                    "data-power-stale": String(power.stale), cx: panel.body.x + panel.body.width - 6 / scale,
                    cy: panel.body.y + panel.body.height - 6 / scale, r: radius,
                    fill: "var(--attention-bg)", stroke: "var(--attention)", "stroke-width": 1 / scale,
                    "stroke-dasharray": power.stale || power.state === "unknown" ? 2 / scale + " " + 1 / scale : "none",
                    "aria-hidden": "true" }));
            }
            group.append(outline);
            const fleetCovered = fleet && runtime && runtime.devices && runtime.devices[panel.id]
                && runtime.devices[panel.id].online && power && power.state === fleet.state;
            const exceptionText = status.status === "offline" && exception ? "▲ " + exception : exception;
            const statusText = [exceptionText, power && !fleetCovered && (power.warning || power.stale) ? power.short : ""].filter(Boolean).join(" · ");
            if (!panel.missing && statusText && panel.body.width * scale >= 40 && panel.body.height * scale >= 24) {
                const statusNode = node("text", { x: panel.body.x + 6 / scale, y: panel.body.y + panel.body.height - 6 / scale,
                    class: "operator-slot-status", "font-size": 10 / scale, "stroke-width": 2 / scale,
                    "paint-order": "stroke", fill: "var(--stage-text)", stroke: "var(--stage)",
                    "data-status": status.status, "data-power-state": power ? power.state : "",
                    "data-label": exceptionText, "data-x": panel.body.x, "data-y": panel.body.y,
                    "data-width": panel.body.width, "data-height": panel.body.height, "aria-hidden": "true" }, statusText);
                if (typeof document.createTextNode === "function") {
                    statusNode.textContent = "";
                    if (exceptionText) statusNode.append(node("tspan", {}, exceptionText));
                    const powerLabel = statusText.slice(exceptionText.length);
                    if (powerLabel) statusNode.append(node("tspan", { class: "operator-slot-power-text" }, powerLabel));
                }
                group.append(statusNode);
            }
            if (layout.kind === "logical" && panel.id === selectedId && !panel.missing && editable) {
                group.append(rect({ x: panel.body.x + panel.body.width - 10 / scale, y: panel.body.y + panel.body.height - 10 / scale, width: 10 / scale, height: 10 / scale },
                    { class: "logical-resize", fill: "var(--stage-text)", "aria-hidden": "true" }));
            }
            world.append(group);
        });
        if (presentation === "arrange" || presentation === "context") world.append(rect(b, {
            class: "operator-wall-bounds", fill: "none", stroke: "var(--stage-text)",
            "stroke-width": 1.5 / scale, "stroke-dasharray": 6 / scale + " " + 4 / scale, "pointer-events": "none"
        }));
        syncChildren(svg, view);
        if (resolutionNode) resolutionNode.textContent = estimates.join("; ");
        if (focusedId) {
            const target = Array.from(svg.querySelectorAll(".slot")).find(item => item.dataset.deviceId === focusedId);
            if (target) target.focus({ preventScroll: true });
        }
        return stage;
    }
    const api = { panels, resolution, draw, fit, exceptionLabel, powerReadiness, fleetPower, viewZoom, viewSize, helpText };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.OperatorStage = api;
}(typeof window !== "undefined" ? window : globalThis));
