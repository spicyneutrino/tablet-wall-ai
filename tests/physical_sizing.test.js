"use strict";

const assert = require("node:assert/strict");
const sizing = require("../frontend/controller/physical-sizing.js");

const profiles = {
    "a:1": { active_width_mm: 100, active_height_mm: 60, bezels: { left: 2, right: 4, top: 3, bottom: 5 } },
    "b:2": { active_width_mm: 80, active_height_mm: 40, bezels: { left: 0, right: 0, top: 0, bottom: 0 } }
};
const profileFor = (id, revision) => profiles[id + ":" + revision] || null;
const slot = (x, y, angle, nx, ny, revision = 1) => ({
    center_x_mm: x, center_y_mm: y, mount_angle: angle,
    nudge_x_mm: nx, nudge_y_mm: ny, profile_revision: revision
});

const zero = sizing.fitBounds({ a: slot(0, 0, 0, 0, 0) }, profileFor, 0).bounds;
assert.deepEqual(zero, { x: -53, y: -34, width: 106, height: 68 }, "0° includes body bezels");
const quarter = sizing.fitBounds({ a: slot(0, 0, 90, 0, 0) }, profileFor, 0).bounds;
assert.ok(Math.abs(quarter.width - 68) < 1e-9 && Math.abs(quarter.height - 106) < 1e-9,
    "90° swaps the complete bezel-inclusive body axes");
const diagonal = sizing.fitBounds({ b: slot(0, 0, 45, 0, 0, 2) }, profileFor, 0).bounds;
assert.ok(Math.abs(diagonal.width - Math.sqrt(7200)) < 1e-9);
assert.equal(diagonal.width, diagonal.height, "45° uses the rotated axis-aligned footprint");

const nudged = sizing.fitBounds({ a: slot(10, -4, 0, 7, -3) }, profileFor, 5).bounds;
assert.deepEqual(nudged, { x: -41, y: -46, width: 116, height: 78 }, "fit centers include slot nudges and outer padding");
assert.equal(sizing.fitBounds({}, profileFor, 10).bounds, null, "empty fit has no derived bounds");
const missing = sizing.fitBounds({ a: slot(0, 0, 0, 0, 0, 9) }, profileFor, 0);
assert.match(missing.error, /Exact display profile r9 is missing/);
assert.match(sizing.fitBounds({ a: slot(0, 0, 0, 0, 0) }, profileFor, 1e308).error, /finite/);

const mixed = {
    a: Object.assign(slot(0, 0, 90, 5, 2), { calibration_revision: 4, participating: false }),
    b: Object.assign(slot(0, 0, 45, -2, 1, 2), { calibration_revision: 7 })
};
const packed = sizing.packSlots(mixed, profileFor, 1, 12, 8);
assert.deepEqual(Object.keys(packed.slots), ["a", "b"]);
assert.equal(packed.slots.a.mount_angle, 90);
assert.equal(packed.slots.a.nudge_x_mm, 5);
assert.equal(packed.slots.a.participating, false);
assert.equal(packed.slots.b.profile_revision, 2);
const bounds = sizing.fitBounds(packed.slots, profileFor, 8).bounds;
assert.ok(bounds.width <= packed.bounds.width + 1e-9);
assert.ok(bounds.height <= packed.bounds.height + 1e-9);
const repeated = sizing.packSlots(packed.slots, profileFor, 1, 12, 8);
assert.deepEqual(repeated, packed, "packing is independent of existing centers and repeatable");

const adjacent = sizing.packSlots({
    a: slot(0, 0, 0, 5, 2),
    b: slot(0, 0, 0, -2, 1, 2),
    c: slot(0, 0, 90, 0, 0)
}, (id, revision) => profileFor(id === "c" ? "a" : id, revision), 2, 0, 0);
const aRight = adjacent.slots.a.center_x_mm + 5 + 106 / 2;
const bLeft = adjacent.slots.b.center_x_mm - 2 - 80 / 2;
assert.equal(aRight, bLeft, "zero-gap mixed tablet bodies touch rather than occupy padded grid cells");
assert.equal(adjacent.bounds.width, 186, "the wall encloses the widest packed row");

const emptyPack = sizing.packSlots({}, profileFor, 3, 4, 5);
assert.deepEqual(emptyPack, { slots: {}, bounds: null });
const blockedPack = sizing.packSlots({ a: slot(0, 0, 0, 0, 0, 99) }, profileFor, 1, 0, 0);
assert.match(blockedPack.error, /Exact display profile r99 is missing/);

console.log("Physical sizing geometry passed");
