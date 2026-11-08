"use strict";

(function (root) {
    function footprint(slot, profile) {
        if (!profile || !Number.isFinite(Number(profile.active_width_mm))
                || !Number.isFinite(Number(profile.active_height_mm))
                || Number(profile.active_width_mm) <= 0 || Number(profile.active_height_mm) <= 0) {
            return null;
        }
        const bezels = profile.bezels || {};
        const bodyW = Number(profile.active_width_mm)
            + Math.max(0, Number(bezels.left) || 0) + Math.max(0, Number(bezels.right) || 0);
        const bodyH = Number(profile.active_height_mm)
            + Math.max(0, Number(bezels.top) || 0) + Math.max(0, Number(bezels.bottom) || 0);
        const radians = ((Number(slot.mount_angle) || 0) % 360) * Math.PI / 180;
        const cos = Math.abs(Math.cos(radians));
        const sin = Math.abs(Math.sin(radians));
        return {
            width: cos * bodyW + sin * bodyH,
            height: sin * bodyW + cos * bodyH,
            nudgeX: Number(slot.nudge_x_mm) || 0,
            nudgeY: Number(slot.nudge_y_mm) || 0
        };
    }

    function resolve(slots, profileFor) {
        const ids = Object.keys(slots || {});
        const items = [];
        for (const id of ids) {
            const slot = slots[id];
            const profile = profileFor(id, slot.profile_revision);
            const size = footprint(slot, profile);
            if (!size) return { error: "Exact display profile r" + slot.profile_revision
                + " is missing for tablet " + id + ". Load that profile before fitting or packing." };
            items.push({ id: id, slot: slot, size: size });
        }
        return { items: items };
    }

    function fitBounds(slots, profileFor, padding) {
        const resolved = resolve(slots, profileFor);
        if (resolved.error) return resolved;
        if (!resolved.items.length) return { bounds: null };
        let minX = Infinity;
        let minY = Infinity;
        let maxX = -Infinity;
        let maxY = -Infinity;
        resolved.items.forEach(function (item) {
            const x = (Number(item.slot.center_x_mm) || 0) + item.size.nudgeX;
            const y = (Number(item.slot.center_y_mm) || 0) + item.size.nudgeY;
            minX = Math.min(minX, x - item.size.width / 2);
            minY = Math.min(minY, y - item.size.height / 2);
            maxX = Math.max(maxX, x + item.size.width / 2);
            maxY = Math.max(maxY, y + item.size.height / 2);
        });
        const pad = Math.max(0, Number(padding) || 0);
        const bounds = {
            x: minX - pad, y: minY - pad,
            width: maxX - minX + pad * 2, height: maxY - minY + pad * 2
        };
        if (!Object.values(bounds).every(Number.isFinite) || bounds.width <= 0 || bounds.height <= 0) {
            return { error: "The fitted wall dimensions must be finite and positive." };
        }
        return { bounds: bounds };
    }

    function packSlots(slots, profileFor, columns, gap, padding) {
        const resolved = resolve(slots, profileFor);
        if (resolved.error) return resolved;
        if (!resolved.items.length) return { slots: {}, bounds: null };
        const columnCount = Math.max(1, Math.min(resolved.items.length, Math.floor(Number(columns) || 1)));
        const rowCount = Math.ceil(resolved.items.length / columnCount);
        const rowHeights = Array(rowCount).fill(0);
        const rowWidths = Array(rowCount).fill(0);
        resolved.items.forEach(function (item, index) {
            const row = Math.floor(index / columnCount);
            rowWidths[row] += item.size.width;
            rowHeights[row] = Math.max(rowHeights[row], item.size.height);
        });
        const spacing = Math.max(0, Number(gap) || 0);
        const pad = Math.max(0, Number(padding) || 0);
        const yStarts = [];
        let cursor = pad;
        const totalWidth = Math.max.apply(null, rowWidths.map(function (width, row) {
            const count = Math.min(columnCount, resolved.items.length - row * columnCount);
            return width + (count - 1) * spacing;
        })) + pad * 2;
        rowHeights.forEach(function (height) {
            yStarts.push(cursor);
            cursor += height + spacing;
        });
        const totalHeight = cursor - spacing + pad;
        if (!Number.isFinite(totalWidth) || !Number.isFinite(totalHeight)) {
            return { error: "The packed wall dimensions must be finite and positive." };
        }
        const packed = {};
        let rowX = pad;
        resolved.items.forEach(function (item, index) {
            const column = index % columnCount;
            const row = Math.floor(index / columnCount);
            if (column === 0) rowX = pad;
            const centerX = rowX + item.size.width / 2 - item.size.nudgeX;
            const centerY = yStarts[row] + item.size.height / 2 - item.size.nudgeY;
            rowX += item.size.width + spacing;
            packed[item.id] = Object.assign({}, item.slot, {
                center_x_mm: centerX,
                center_y_mm: centerY
            });
        });
        return { slots: packed, bounds: { x: 0, y: 0, width: totalWidth, height: totalHeight } };
    }

    function nextPosition(slots, profileFor, profile, bounds) {
        const resolved = resolve(slots, profileFor);
        if (resolved.error) return resolved;
        const size = footprint({ mount_angle: 0 }, profile);
        if (!size) return { error: "An exact profile is required before adding a tablet." };
        const occupied = resolved.items.map(item => ({
            x: item.slot.center_x_mm + item.size.nudgeX - item.size.width / 2,
            y: item.slot.center_y_mm + item.size.nudgeY - item.size.height / 2,
            width: item.size.width, height: item.size.height
        }));
        const cellW = Math.max(size.width, ...occupied.map(item => item.width));
        const cellH = Math.max(size.height, ...occupied.map(item => item.height));
        const originX = occupied.length ? Math.min(...occupied.map(item => item.x)) : bounds.x;
        const originY = occupied.length ? Math.min(...occupied.map(item => item.y)) : bounds.y;
        for (let index = 0; index < (occupied.length + 1) * 4; index += 1) {
            const x = originX + (index % 2) * cellW;
            const y = originY + Math.floor(index / 2) * cellH;
            if (occupied.every(item => x + size.width <= item.x + 1e-8 || x >= item.x + item.width - 1e-8
                    || y + size.height <= item.y + 1e-8 || y >= item.y + item.height - 1e-8)) {
                return { x: x + size.width / 2, y: y + size.height / 2 };
            }
        }
        return { error: "No non-overlapping Add position could be suggested. Use a grid preview." };
    }

    const LOGICAL_EDGE_THRESHOLD_PX = 8;

    function linear(value, fallback) {
        const number = Number(value);
        return Number.isFinite(number) ? number : fallback;
    }

    function bezel(slot) {
        return slot && slot.bezel || {};
    }

    function edgeThreshold(thresholdPx, pixelsPerUnit) {
        const threshold = linear(thresholdPx, LOGICAL_EDGE_THRESHOLD_PX);
        const density = linear(pixelsPerUnit, 0);
        return density > 0 ? threshold / density : 0;
    }

    function edgeCandidates(layout, id) {
        const placements = layout && layout.placements || {};
        const selected = placements[id];
        if (!selected) return { x: [], y: [] };
        const box = bezel(selected);
        const offsets = {
            x: [
                { value: 0, priority: 0 },
                { value: linear(selected.w, 0), priority: 0 },
                { value: linear(box.left, 0), priority: 1 },
                { value: linear(selected.w, 0) - linear(box.right, 0), priority: 1 }
            ],
            y: [
                { value: 0, priority: 0 },
                { value: linear(selected.h, 0), priority: 0 },
                { value: linear(box.top, 0), priority: 1 },
                { value: linear(selected.h, 0) - linear(box.bottom, 0), priority: 1 }
            ]
        };
        const targetsX = [];
        const targetsY = [];
        for (const [otherId, other] of Object.entries(placements)) {
            if (otherId === id || !other) continue;
            const otherBox = bezel(other);
            targetsX.push(
                linear(other.x, 0), linear(other.x, 0) + linear(other.w, 0),
                linear(other.x, 0) + linear(otherBox.left, 0),
                linear(other.x, 0) + linear(other.w, 0) - linear(otherBox.right, 0)
            );
            targetsY.push(
                linear(other.y, 0), linear(other.y, 0) + linear(other.h, 0),
                linear(other.y, 0) + linear(otherBox.top, 0),
                linear(other.y, 0) + linear(other.h, 0) - linear(otherBox.bottom, 0)
            );
        }
        const expand = (targets, list) => {
            const values = [];
            for (const target of targets) {
                for (const offset of list) values.push({ value: target - offset.value, priority: offset.priority });
            }
            return values;
        };
        return {
            x: [{ value: 0, priority: 0 }, { value: linear(layout.width, 0) - linear(selected.w, 0), priority: 0 }]
                .concat(expand(targetsX, offsets.x)),
            y: [{ value: 0, priority: 0 }, { value: linear(layout.height, 0) - linear(selected.h, 0), priority: 0 }]
                .concat(expand(targetsY, offsets.y))
        };
    }

    function closestEdge(candidates, raw, threshold) {
        if (!(threshold > 0)) return null;
        let best = null;
        for (const candidate of candidates) {
            const distance = Math.abs(raw - candidate.value);
            if (distance > threshold + 1e-9) continue;
            const closer = !best || distance < best.distance - 1e-9;
            const tieBetter = !!best && Math.abs(distance - best.distance) <= 1e-9
                && (candidate.priority < best.priority
                    || candidate.priority === best.priority && candidate.value < best.value);
            if (closer || tieBetter) {
                best = { value: candidate.value, priority: candidate.priority, distance: distance };
            }
        }
        return best ? Math.round(best.value) : null;
    }

    function snapLogical(slot, layout, options) {
        const settings = options || {};
        if (!slot || !layout || layout.kind !== "logical") return slot ? Object.assign({}, slot) : slot;
        const mode = settings.mode === "resize" ? "resize" : "move";
        const step = Math.max(1, Math.round(linear(settings.step, 1)));
        const enabled = settings.enabled !== false;
        const threshold = linear(settings.threshold, 0);
        const result = Object.assign({}, slot);
        const box = bezel(slot);
        const grid = value => Math.round(value / step) * step;
        if (mode === "resize") {
            const minimumW = linear(box.left, 0) + linear(box.right, 0) + 1;
            const minimumH = linear(box.top, 0) + linear(box.bottom, 0) + 1;
            result.w = Math.max(minimumW, enabled ? grid(linear(slot.w, 0)) : Math.round(linear(slot.w, 0)));
            result.h = Math.max(minimumH, enabled ? grid(linear(slot.h, 0)) : Math.round(linear(slot.h, 0)));
            return result;
        }
        const rawX = linear(slot.x, 0), rawY = linear(slot.y, 0);
        if (!enabled) {
            result.x = Math.round(rawX);
            result.y = Math.round(rawY);
            return result;
        }
        const edges = edgeCandidates(layout, settings.id);
        const edgeX = closestEdge(edges.x, rawX, threshold);
        const edgeY = closestEdge(edges.y, rawY, threshold);
        result.x = edgeX === null ? grid(rawX) : edgeX;
        result.y = edgeY === null ? grid(rawY) : edgeY;
        return result;
    }

    function matchScreenShape(slot, viewport) {
        if (!slot) return { error: "Select a placed tablet before matching its screen shape." };
        const width = linear(viewport && viewport.width, 0);
        const height = linear(viewport && viewport.height, 0);
        if (!(width > 0) || !(height > 0)) return { error: "A current online tablet viewport is required to match the screen shape." };
        const box = bezel(slot);
        const activeWidth = linear(slot.w, 0) - linear(box.left, 0) - linear(box.right, 0);
        if (!(activeWidth > 0)) return { error: "The active screen width is not positive. Review the wall size and bezels first." };
        const activeHeight = activeWidth / (width / height);
        if (!Number.isFinite(activeHeight) || activeHeight <= 0) return { error: "The tablet viewport cannot produce a positive active height." };
        const targetHeight = Math.round(activeHeight + linear(box.top, 0) + linear(box.bottom, 0));
        if (!(targetHeight > linear(box.top, 0) + linear(box.bottom, 0))) {
            return { error: "The bezels leave no positive active height. Review the wall size and bezels first." };
        }
        const targetY = Math.round(linear(slot.y, 0) + (linear(slot.h, 0) - targetHeight) / 2);
        return { placement: Object.assign({}, slot, { y: targetY, h: targetHeight }),
            changed: targetHeight !== slot.h || targetY !== slot.y };
    }

    function freshViewport(device, options) {
        const settings = options || {};
        if (settings.stale) return { available: false, reason: "Tablet status is stale. Refresh status or reconnect before matching the screen shape." };
        if (!device) return { available: false, reason: "Select a tablet before matching the screen shape." };
        if (device.online !== true) return { available: false, reason: "This tablet is offline. Its last viewport cannot define the current screen shape; refresh status or reconnect." };
        const width = linear(device.viewport && device.viewport.width, 0);
        const height = linear(device.viewport && device.viewport.height, 0);
        if (!(width > 0) || !(height > 0)) return { available: false, reason: "No current positive tablet viewport was reported. Refresh status or reconnect." };
        if (settings.expected && (settings.expected.width !== width || settings.expected.height !== height)) {
            return { available: false, reason: "The tablet viewport changed. Refresh status or reconnect before matching the screen shape." };
        }
        return { available: true, viewport: { width: width, height: height } };
    }

    const api = { fitBounds: fitBounds, packSlots: packSlots, nextPosition: nextPosition,
        LOGICAL_EDGE_THRESHOLD_PX: LOGICAL_EDGE_THRESHOLD_PX, edgeThreshold: edgeThreshold,
        snapLogical: snapLogical, matchScreenShape: matchScreenShape, freshViewport: freshViewport };
    root.PhysicalSizing = api;
    if (typeof module !== "undefined" && module.exports) module.exports = api;
}(typeof window !== "undefined" ? window : globalThis));
