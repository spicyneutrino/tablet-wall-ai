import { createRequire } from 'node:module';
import { expect, it } from 'vitest';
import { RulerReview, rulerCheckBodies, rulerScale, rulerUrl, selectedViewport } from './calibration';

const require = createRequire(import.meta.url);
const old = require('../../../controller/physical-calibration.js') as typeof import('./calibration');

function thrown(run: () => unknown): string | null {
    try { run(); return null; } catch (error) { return (error as Error).message; }
}

it('physical_calibration.diff.test.js', () => {
    const viewport = { width: 600, height: 800, dpr: 2, orientation: 90, mode: "tab" };
    const roster = { tablet: { online: true, viewport }, laptop: { online: true, viewport: { ...viewport, width: 1440, height: 900, dpr: 1 } } };
    for (const id of ["tablet", "laptop", "missing"]) {
        expect(selectedViewport(roster, id)).toEqual(old.selectedViewport(roster, id));
    }
    expect(selectedViewport({ tablet: { online: false, viewport } }, "tablet")).toEqual(old.selectedViewport({ tablet: { online: false, viewport } }, "tablet"));
    expect(selectedViewport({ tablet: { online: true } }, "tablet")).toEqual(old.selectedViewport({ tablet: { online: true } }, "tablet"));
    for (const key of ["width", "height", "dpr"]) {
        for (const value of [NaN, 0, Infinity, -1]) {
            const candidate = { tablet: { online: true, viewport: { ...viewport, [key]: value } } };
            expect(selectedViewport(candidate, "tablet")).toEqual(old.selectedViewport(candidate, "tablet"));
        }
    }
    for (const visual_scale of [0, 1.2, NaN, Infinity, "1", 1]) {
        const candidate = { tablet: { online: true, viewport: { ...viewport, visual_scale } } };
        expect(selectedViewport(candidate, "tablet")).toEqual(old.selectedViewport(candidate, "tablet"));
    }
    for (const orientation of [0, 90, 180, 270]) {
        const candidate = { tablet: { online: true, viewport: { ...viewport, orientation } } };
        expect(selectedViewport(candidate, "tablet")).toEqual(old.selectedViewport(candidate, "tablet"));
    }
    expect(rulerScale(50, 60, 200, 150)).toEqual(old.rulerScale(50, 60, 200, 150));
    for (const value of [0, NaN, Infinity, "", -1]) {
        expect(thrown(() => rulerScale(value, 40, 200, 200))).toBe(thrown(() => old.rulerScale(value, 40, 200, 200)));
    }
    for (const origin of [null, "http://localhost:8080", "http://127.0.0.1", "http://[::1]", "https://x.localhost",
        "https://tablet.example/path", "not a url"]) {
        expect(rulerUrl(origin)).toBe(old.rulerUrl(origin));
    }
    const measurements = { x: { mm: "120", px: "600", error: "0.5" }, y: { mm: "200", px: "800", error: "1" } };
    for (const quarter of [0, 1, 2, 3]) {
        expect(rulerCheckBodies("tablet", 2, quarter, viewport, measurements))
            .toEqual(old.rulerCheckBodies("tablet", 2, quarter, viewport, measurements));
    }
    for (const value of ["", -1, NaN, Infinity, "bad", 0]) {
        const candidate = { ...measurements, x: { ...measurements.x, error: value } };
        expect(thrown(() => rulerCheckBodies("tablet", 1, 0, viewport, candidate)))
            .toBe(thrown(() => old.rulerCheckBodies("tablet", 1, 0, viewport, candidate)));
    }
    expect(thrown(() => rulerCheckBodies("tablet", 1, 0, null, measurements))).toBe(thrown(() => old.rulerCheckBodies("tablet", 1, 0, null, measurements)));
    expect(thrown(() => rulerCheckBodies("tablet", 0, 0, viewport, measurements))).toBe(thrown(() => old.rulerCheckBodies("tablet", 0, 0, viewport, measurements)));
    expect(thrown(() => rulerCheckBodies("tablet", 1, 4, viewport, measurements))).toBe(thrown(() => old.rulerCheckBodies("tablet", 1, 4, viewport, measurements)));

    const steps: [string, ...unknown[]][] = [
        ["canSave", "first"], ["begin", "first"], ["canSave", "first"], ["accept", "old", []],
        ["accept", "first", [{ decision: { required: true } }]], ["canSave", "first"], ["decide", "keep_supplied"],
        ["canSave", "first"], ["decide", "use_ruler"], ["begin", "second"], ["accept", "second", []],
        ["decide", "use_ruler"], ["canSave", "second"], ["canSave", "changed-profile-or-viewport"], ["invalidate"],
        ["canSave", "second"], ["begin", "third"], ["invalidate"], ["accept", "third", []], ["begin", "fourth"],
        ["accept", "fourth", []], ["decide", "remeasure"], ["canSave", "fourth"], ["reset"],
    ];
    const review = new RulerReview();
    const oldReview = new old.RulerReview();
    for (const [method, ...args] of steps) {
        expect(thrown(() => (review[method as keyof RulerReview] as (...values: unknown[]) => unknown)(...args)))
            .toBe(thrown(() => (oldReview[method as keyof RulerReview] as (...values: unknown[]) => unknown)(...args)));
        expect([review.status, review.key, review.results]).toEqual([oldReview.status, oldReview.key, oldReview.results]);
    }
});
