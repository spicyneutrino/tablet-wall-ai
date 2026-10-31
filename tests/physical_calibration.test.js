"use strict";
const assert = require("node:assert/strict");
const { selectedViewport, rulerScale, rulerUrl } = require("../frontend/controller/physical-calibration.js");
const viewport = { width: 600, height: 800, dpr: 2, orientation: 90, mode: "tab" };
const roster = { tablet: { online: true, viewport }, laptop: { online: true, viewport: { ...viewport, width: 1440, height: 900, dpr: 1 } } };
assert.deepEqual(selectedViewport(roster, "tablet"), viewport);
assert.equal(selectedViewport(roster, "missing"), null);
assert.equal(selectedViewport({ tablet: { online: false, viewport } }, "tablet"), null);
assert.equal(selectedViewport({ tablet: { online: true } }, "tablet"), null);
for (const key of ["width", "height", "dpr"]) {
    for (const value of [NaN, 0, Infinity, -1]) {
        assert.equal(selectedViewport({ tablet: { online: true, viewport: { ...viewport, [key]: value } } }, "tablet"), null);
    }
}
for (const orientation of [0, 90, 180, 270]) {
    assert.equal(selectedViewport({ tablet: { online: true, viewport: { ...viewport, orientation } } }, "tablet").orientation, orientation);
    assert.deepEqual(rulerScale(50, 60, 200, 150), [0.25, 0.4], "CSS axes remain ordered before any quarter turn");
}
for (const value of [0, NaN, Infinity, "", -1]) assert.throws(() => rulerScale(value, 40, 200, 200));
assert.equal(rulerUrl(null), null);
for (const origin of ["http://localhost:8080", "http://127.0.0.1", "http://[::1]", "https://x.localhost"]) assert.equal(rulerUrl(origin), null);
assert.equal(rulerUrl("https://tablet.example/path"), "https://tablet.example/client/?calibrate=1");
console.log("physical calibration tests passed");
