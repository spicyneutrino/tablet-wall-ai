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

    const api = { fitBounds: fitBounds, packSlots: packSlots };
    root.PhysicalSizing = api;
    if (typeof module !== "undefined" && module.exports) module.exports = api;
}(typeof window !== "undefined" ? window : globalThis));
