import { expect, it } from 'vitest';
import { RulerReview, rulerCheckBodies, rulerScale, rulerUrl, selectedViewport } from './calibration';

it('physical_calibration.test.js', () => {
    const viewport = { width: 600, height: 800, dpr: 2, orientation: 90, mode: "tab" };
    const roster = { tablet: { online: true, viewport }, laptop: { online: true, viewport: { ...viewport, width: 1440, height: 900, dpr: 1 } } };
    expect(selectedViewport(roster, "tablet")).toEqual(viewport);
    expect(selectedViewport(roster, "missing")).toBe(null);
    expect(selectedViewport({ tablet: { online: false, viewport } }, "tablet")).toBe(null);
    expect(selectedViewport({ tablet: { online: true } }, "tablet")).toBe(null);
    for (const key of ["width", "height", "dpr"]) {
        for (const value of [NaN, 0, Infinity, -1]) {
            expect(selectedViewport({ tablet: { online: true, viewport: { ...viewport, [key]: value } } }, "tablet")).toBe(null);
        }
    }
    for (const visual_scale of [0, 1.2, NaN, Infinity, "1"]) {
        expect(selectedViewport({ tablet: { online: true, viewport: { ...viewport, visual_scale } } }, "tablet")).toBe(null);
    }
    expect(selectedViewport({ tablet: { online: true, viewport: { ...viewport, visual_scale: 1 } } }, "tablet")).toEqual(viewport);
    for (const orientation of [0, 90, 180, 270]) {
        expect(selectedViewport({ tablet: { online: true, viewport: { ...viewport, orientation } } }, "tablet")!.orientation).toBe(orientation);
        expect(rulerScale(50, 60, 200, 150), "CSS axes remain ordered before any quarter turn").toEqual([0.25, 0.4]);
    }
    for (const value of [0, NaN, Infinity, "", -1]) expect(() => rulerScale(value, 40, 200, 200)).toThrow();
    expect(rulerUrl(null)).toBe(null);
    for (const origin of ["http://localhost:8080", "http://127.0.0.1", "http://[::1]", "https://x.localhost"]) expect(rulerUrl(origin)).toBe(null);
    expect(rulerUrl("https://tablet.example/path")).toBe("https://tablet.example/client/?calibrate=1");
    const measurements = { x: { mm: "120", px: "600", error: "0.5" }, y: { mm: "200", px: "800", error: "1" } };
    for (const quarter of [0, 1, 2, 3]) {
        const bodies = rulerCheckBodies("tablet", 2, quarter, viewport, measurements);
        expect(bodies.map(body => body.axis)).toEqual(["x", "y"]);
        expect(bodies.map(body => body.span_mm / body.span_px)).toEqual([0.2, 0.25]);
        expect(bodies[0]!.profile_revision, "check the chosen revision rather than the latest profile").toBe(2);
        expect(bodies[0]!.quarter_turn).toBe(quarter);
        expect(bodies[0]!.usable_width_px).toBe(600);
        expect(bodies[1]!.span_error_mm).toBe(1);
    }
    for (const value of ["", -1, NaN, Infinity, "bad"]) {
        expect(() => rulerCheckBodies("tablet", 1, 0, viewport, { ...measurements, x: { ...measurements.x, error: value } })).toThrow();
    }
    expect(() => rulerCheckBodies("tablet", 1, 0, null, measurements)).toThrow();
    expect(() => rulerCheckBodies("tablet", 0, 0, viewport, measurements)).toThrow();
    expect(() => rulerCheckBodies("tablet", 1, 4, viewport, measurements)).toThrow();
    const review = new RulerReview();
    expect(review.canSave("first")).toBe(false);
    review.begin("first");
    expect(review.canSave("first")).toBe(false);
    expect(review.accept("old", []), "late response cannot approve a changed mapping").toBe(false);
    expect(review.accept("first", [{ decision: { required: true } }])).toBe(true);
    expect(review.canSave("first"), "a displayed disagreement still needs a choice").toBe(false);
    review.decide("keep_supplied");
    expect(review.canSave("first"), "Keep supplied never permits a ruler write").toBe(false);
    expect(() => review.decide("use_ruler")).toThrow();
    review.begin("second");
    review.accept("second", []);
    review.decide("use_ruler");
    expect(review.canSave("second")).toBe(true);
    expect(review.canSave("changed-profile-or-viewport")).toBe(false);
    review.invalidate();
    expect(review.canSave("second"), "editing measurements invalidates a prior explicit decision").toBe(false);
    review.begin("third");
    review.invalidate();
    expect(review.accept("third", []), "in-flight results cannot restore invalidated measurements").toBe(false);
    review.begin("fourth");
    review.accept("fourth", []);
    review.decide("remeasure");
    expect(review.canSave("fourth")).toBe(false);
    review.reset();
    expect(review.status).toBe("idle");
    console.log("physical calibration tests passed (viewport, requests, axes, decisions, stale results)");
});
