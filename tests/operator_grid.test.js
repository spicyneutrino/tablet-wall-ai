"use strict";
const assert = require("node:assert/strict");
const { command } = require("../frontend/controller/operator-grid.js");
const sizing = require("../frontend/controller/physical-sizing.js");
const stage = require("../frontend/controller/operator-stage.js");
const source = { kind: "logical", ids: ["four", "one", "two", "three"], rows: 2, columns: 2, gap: 0, padding: 0,
    sizing: "tablets", orientation: "preserve", holes: false, releases: ["offline"],
    sizes: Object.fromEntries(["one", "two", "three", "four"].map(id => [id, { w: 100, h: 60 }])) };
const logical = command(source);
assert.deepEqual(logical.device_ids, source.ids, "submitted order is the sole order of record");
assert.deepEqual(logical.release_unselected, ["offline"]);
assert.equal(logical.physical_revisions, undefined);
assert.equal(logical.mount_angles, undefined);
assert.deepEqual(command({ ...source, rows: 1, columns: 4 }).rows, 1);
assert.throws(() => command({ ...source, ids: [] }), /at least one/);
assert.throws(() => command({ ...source, ids: ["one", "one"] }), /duplicate/);
assert.throws(() => command({ ...source, ids: ["one"] }), /exactly 4/);
assert.equal(command({ ...source, ids: ["one"], holes: true }).allow_empty_cells, true);
for (const value of [0, NaN, Infinity, true, 1.5]) assert.throws(() => command({ ...source, rows: value }), /whole numbers/);
for (const value of [-1, NaN, Infinity, 0.5]) assert.throws(() => command({ ...source, gap: value }), /nonnegative/);
assert.throws(() => command({ ...source, sizes: {} }), /logical sizes/);
const physical = command({ ...source, kind: "physical", ids: ["one"], rows: 1, columns: 1, gap: 0.5,
    revisions: { one: { profile_revision: 1, calibration_revision: 2 } }, angles: { one: "90" } });
assert.equal(physical.logical_sizes, undefined);
assert.deepEqual(physical.mount_angles, { one: 90 });
assert.throws(() => command({ ...source, kind: "physical", revisions: {}, angles: {} }), /measurements/);
const profile = { active_width_mm: 100, active_height_mm: 60, bezels: { top: 5, right: 9, bottom: 11, left: 7 }, panel_pixels_width: 2048 };
const slots = {};
for (const id of ["one", "two", "three", "four"]) {
    const next = sizing.nextPosition(slots, () => profile, profile, { x: -10, y: -20, width: 100, height: 60 });
    assert.ok(!next.error);
    slots[id] = { center_x_mm: next.x, center_y_mm: next.y, profile_revision: 1, calibration_revision: 2, mount_angle: 0, nudge_x_mm: 0, nudge_y_mm: 0 };
}
const panels = stage.panels({ kind: "physical", slots }, () => profile);
for (let i = 0; i < panels.length; i += 1) for (let j = i + 1; j < panels.length; j += 1) {
    const a = panels[i].body, b = panels[j].body;
    assert.ok(a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y, "manual adds must not overlap");
}
assert.equal(panels[0].body.y, panels[1].body.y);
assert.equal(panels[2].body.y, panels[3].body.y);
assert.equal(panels[0].body.x, panels[2].body.x, "four manual adds suggest a 2 by 2");
assert.equal(panels[0].active.x - panels[0].body.x, 7, "asymmetric left bezel moves the active clip");
assert.equal(panels[0].body.width, 116, "body includes bezels exactly once");
const crop = stage.panels({ kind: "logical", placements: { one: { x: 20, y: 30, w: 100, h: 70, bezel: { top: 3, right: 5, bottom: 7, left: 11 } } } }, () => null)[0];
assert.deepEqual(crop.active, { x: 31, y: 33, width: 84, height: 60 });
assert.equal(stage.panels({ kind: "physical", slots }, () => null)[0].missing, true, "missing pinned records cannot borrow the latest profile");
assert.deepEqual(stage.resolution(panels[0], { scale: 0.2 }, { intrinsicWidth: 2000 }, null), { pixels: 500, target: 2048, upscale: 4.096 });
console.log("Operator atomic-grid inputs, manual Add and panel clipping contracts passed");

const { membership } = require("../frontend/controller/operator-grid.js");
const emptyLogical = { kind: "logical", placements: {} };
const live = membership();
live.observe({ a: { online: true, viewport: { width: 1600, height: 1000 } } }, emptyLogical);
let liveView = live.view();
assert.equal(liveView.a.size.w, 160, "a live viewport derives an integer relative width");
assert.equal(liveView.a.size.h, 100);
assert.equal(liveView.a.sizeSource, "viewport");
live.freeze();
live.observe({ a: { online: true, viewport: { width: 1000, height: 1000 } } }, emptyLogical);
assert.deepEqual(live.view().a.size, { w: 160, h: 100 }, "a frozen live join never overwrites explicit geometry");
const explicit = membership();
explicit.observe({ b: { online: true, viewport: { width: 1600, height: 1000 } } }, emptyLogical);
explicit.size("b", { w: 123, h: 45 });
explicit.observe({ b: { online: true, viewport: { width: 1000, height: 1000 } } }, emptyLogical);
assert.deepEqual(explicit.view().b.size, { w: 123, h: 45 }, "operator size provenance survives later viewport reports");
assert.equal(explicit.view().b.sizeSource, "operator");
const saved = membership();
saved.observe({ c: { online: true, viewport: { width: 2000, height: 1000 } } }, { kind: "logical", placements: { c: { w: 50, h: 40 } } });
assert.deepEqual(saved.view().c.size, { w: 50, h: 40 }, "saved geometry is never replaced by a live viewport");
assert.equal(saved.view().c.sizeSource, "saved");
saved.observe({ c: { online: true, viewport: { width: 2000, height: 1000 } } }, { kind: "logical", placements: { c: { w: 60, h: 40 } } }, { refreshSaved: true });
assert.deepEqual(saved.view().c.size, { w: 60, h: 40 }, "an explicit saved refresh can adopt the reviewed saved size");
const offline = membership();
offline.observe({ d: { online: false, viewport: { width: 1600, height: 1000 } } }, emptyLogical);
assert.deepEqual(offline.view().d.size, { w: 100, h: 100 }, "an offline viewport cannot define a new logical size");
assert.equal(offline.view().d.sizeSource, "fallback");
const invalidViewport = membership();
invalidViewport.observe({ e: { online: true, viewport: { width: Infinity, height: 1000 } } }, emptyLogical);
assert.deepEqual(invalidViewport.view().e.size, { w: 100, h: 100 }, "a non-finite viewport cannot define an infinite logical size");
assert.equal(invalidViewport.view().e.sizeSource, "fallback");
invalidViewport.observe({ f: { online: true, viewport: { width: 1600, height: 900 } } }, emptyLogical);
assert.deepEqual(invalidViewport.view().f.size, { w: 178, h: 100 }, "a fractional viewport ratio still yields whole logical units");
offline.include("d", true);
assert.equal(offline.view().d.membershipSource, "operator", "explicit inclusion is recorded separately from live presence");
assert.equal(offline.view().d.included, true);
const matched = sizing.matchScreenShape({ x: 0, y: 0, w: 100, h: 70, bezel: { top: 3, right: 5, bottom: 7, left: 11 } }, { width: 1600, height: 1000 });
assert.equal(Number.isInteger(matched.placement.h), true, "Match keeps logical grid sizes integral");
console.log("Operator membership provenance, frozen sizes and integer Match geometry passed");

const hugeViewport = membership();
hugeViewport.observe({ huge: { online: true, viewport: { width: 1e307, height: 1e307 } } }, emptyLogical);
assert.deepEqual(hugeViewport.view().huge.size, { w: 100, h: 100 }, "large finite square dimensions retain a finite square ratio");
assert.equal(hugeViewport.view().huge.sizeSource, "viewport");
hugeViewport.observe({ overflow: { online: true, viewport: { width: 1e307, height: 1 } } }, emptyLogical);
assert.deepEqual(hugeViewport.view().overflow.size, { w: 100, h: 100 }, "a ratio whose derived width overflows keeps fallback geometry");
assert.equal(hugeViewport.view().overflow.sizeSource, "fallback");
