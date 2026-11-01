"use strict";
const assert = require("node:assert/strict");
const { selectedViewport, rulerScale, rulerUrl, rulerCheckBodies, RulerReview } = require("../frontend/controller/physical-calibration.js");
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
for (const visual_scale of [0, 1.2, NaN, Infinity, "1"]) {
    assert.equal(selectedViewport({ tablet: { online: true, viewport: { ...viewport, visual_scale } } }, "tablet"), null);
}
assert.deepEqual(selectedViewport({ tablet: { online: true, viewport: { ...viewport, visual_scale: 1 } } }, "tablet"), viewport);
for (const orientation of [0, 90, 180, 270]) {
    assert.equal(selectedViewport({ tablet: { online: true, viewport: { ...viewport, orientation } } }, "tablet").orientation, orientation);
    assert.deepEqual(rulerScale(50, 60, 200, 150), [0.25, 0.4], "CSS axes remain ordered before any quarter turn");
}
for (const value of [0, NaN, Infinity, "", -1]) assert.throws(() => rulerScale(value, 40, 200, 200));
assert.equal(rulerUrl(null), null);
for (const origin of ["http://localhost:8080", "http://127.0.0.1", "http://[::1]", "https://x.localhost"]) assert.equal(rulerUrl(origin), null);
assert.equal(rulerUrl("https://tablet.example/path"), "https://tablet.example/client/?calibrate=1");
const measurements = { x: { mm: "120", px: "600", error: "0.5" }, y: { mm: "200", px: "800", error: "1" } };
for (const quarter of [0, 1, 2, 3]) {
    const bodies = rulerCheckBodies("tablet", 2, quarter, viewport, measurements);
    assert.deepEqual(bodies.map(body => body.axis), ["x", "y"]);
    assert.deepEqual(bodies.map(body => body.span_mm / body.span_px), [0.2, 0.25]);
    assert.equal(bodies[0].profile_revision, 2, "check the chosen revision rather than the latest profile");
    assert.equal(bodies[0].quarter_turn, quarter);
    assert.equal(bodies[0].usable_width_px, 600);
    assert.equal(bodies[1].span_error_mm, 1);
}
for (const value of ["", -1, NaN, Infinity, "bad"]) {
    assert.throws(() => rulerCheckBodies("tablet", 1, 0, viewport, { ...measurements, x: { ...measurements.x, error: value } }));
}
assert.throws(() => rulerCheckBodies("tablet", 1, 0, null, measurements));
assert.throws(() => rulerCheckBodies("tablet", 0, 0, viewport, measurements));
assert.throws(() => rulerCheckBodies("tablet", 1, 4, viewport, measurements));
const review = new RulerReview();
assert.equal(review.canSave("first"), false);
review.begin("first");
assert.equal(review.canSave("first"), false);
assert.equal(review.accept("old", []), false, "late response cannot approve a changed mapping");
assert.equal(review.accept("first", [{ decision: { required: true } }]), true);
assert.equal(review.canSave("first"), false, "a displayed disagreement still needs a choice");
review.decide("keep_supplied");
assert.equal(review.canSave("first"), false, "Keep supplied never permits a ruler write");
assert.throws(() => review.decide("use_ruler"));
review.begin("second");
review.accept("second", []);
review.decide("use_ruler");
assert.equal(review.canSave("second"), true);
assert.equal(review.canSave("changed-profile-or-viewport"), false);
review.invalidate();
assert.equal(review.canSave("second"), false, "editing measurements invalidates a prior explicit decision");
review.begin("third");
review.invalidate();
assert.equal(review.accept("third", []), false, "in-flight results cannot restore invalidated measurements");
review.begin("fourth");
review.accept("fourth", []);
review.decide("remeasure");
assert.equal(review.canSave("fourth"), false);
review.reset();
assert.equal(review.status, "idle");
console.log("physical calibration tests passed (viewport, requests, axes, decisions, stale results)");
