import { createRequire } from 'node:module';
import { describe, it, expect } from 'vitest';
import { command, membership, type GridCommandInput } from './gridCommand';

const old = createRequire(import.meta.url)('../../../controller/operator-grid.js') as {
    command(input: GridCommandInput): unknown;
    membership(): {
        observe(roster: Record<string, unknown>, layout: unknown, options?: { refreshSaved?: boolean }): void;
        commit(layout: unknown): void;
        include(id: string, included: boolean): void;
        size(id: string, size: { w: number; h: number }): void;
        freeze(): void;
        view(): unknown;
    };
};

const same = (next: () => unknown, previous: () => unknown): void => {
    let nextValue, previousValue, nextError, previousError;
    try { nextValue = next(); } catch (error) { nextError = (error as Error).message; }
    try { previousValue = previous(); } catch (error) { previousError = (error as Error).message; }
    expect(nextError).toBe(previousError);
    expect(nextValue).toEqual(previousValue);
};

describe('operator-grid parity', () => {
    it('command matches operator-grid.js', () => {
        const source: GridCommandInput = { kind: "logical", ids: ["four", "one", "two", "three"], rows: 2, columns: 2, gap: 0, padding: 0,
            sizing: "tablets", orientation: "preserve", holes: false, releases: ["offline"],
            sizes: Object.fromEntries(["one", "two", "three", "four"].map(id => [id, { w: 100, h: 60 }])) };
        const variants: GridCommandInput[] = [
            source,
            { ...source, rows: 1, columns: 4 },
            { ...source, ids: [] },
            { ...source, ids: ["one", "one"] },
            { ...source, ids: ["one"] },
            { ...source, ids: ["one"], holes: true },
            { ...source, rows: 0 },
            { ...source, rows: NaN },
            { ...source, rows: Infinity },
            { ...source, rows: true as unknown as number },
            { ...source, rows: 1.5 },
            { ...source, gap: -1 },
            { ...source, gap: NaN },
            { ...source, gap: Infinity },
            { ...source, gap: 0.5 },
            { ...source, sizes: {} },
            { ...source, kind: "physical", ids: ["one"], rows: 1, columns: 1, gap: 0.5,
                revisions: { one: { profile_revision: 1, calibration_revision: 2 } }, angles: { one: "90" } },
            { ...source, kind: "physical", ids: ["one"], rows: 1, columns: 1, gap: 0.5,
                revisions: { one: { profile_revision: 1, calibration_revision: 2 } }, angles: { one: 90 } },
            { ...source, kind: "physical", ids: ["one"], rows: 1, columns: 1, gap: 0.5,
                revisions: { one: { profile_revision: 1, calibration_revision: 2 } }, angles: { one: 45 } },
            { ...source, kind: "physical", ids: ["one"], rows: 1, columns: 1, gap: 0.5,
                revisions: { one: { profile_revision: 1, calibration_revision: 2 } }, angles: { one: "" } },
            { ...source, kind: "physical", ids: ["one"], rows: 1, columns: 1 },
            { ...source, kind: "physical", revisions: {}, angles: {} },
        ];
        for (const variant of variants) same(() => command(variant), () => old.command(variant));
    });

    it('membership matches operator-grid.js', () => {
        const emptyLogical = { kind: "logical", placements: {} };
        const rosterA = { a: { online: true, viewport: { width: 1600, height: 1000 } } };
        const rosterAOff = { a: { online: true, viewport: { width: 1000, height: 1000 } } };
        const savedC = { kind: "logical", placements: { c: { w: 50, h: 40 } } };
        const savedC2 = { kind: "logical", placements: { c: { w: 60, h: 40 } } };
        const steps: Array<(m: ReturnType<typeof membership> | ReturnType<typeof old.membership>) => void> = [
            m => m.observe(rosterA, emptyLogical),
            m => m.freeze(),
            m => m.observe(rosterAOff, emptyLogical),
            m => m.observe({ b: { online: true, viewport: { width: 1600, height: 1000 } } }, emptyLogical),
            m => m.size("b", { w: 123, h: 45 }),
            m => m.observe({ b: { online: true, viewport: { width: 1000, height: 1000 } } }, emptyLogical),
            m => m.observe({ c: { online: true, viewport: { width: 2000, height: 1000 } } }, savedC),
            m => m.observe({ c: { online: true, viewport: { width: 2000, height: 1000 } } }, savedC2, { refreshSaved: true }),
            m => m.observe({ d: { online: false, viewport: { width: 1600, height: 1000 } } }, emptyLogical),
            m => m.include("d", true),
            m => m.observe({ e: { online: true, viewport: { width: Infinity, height: 1000 } } }, emptyLogical),
            m => m.observe({ f: { online: true, viewport: { width: 1600, height: 900 } } }, emptyLogical),
            m => m.observe({ huge: { online: true, viewport: { width: 1e307, height: 1e307 } } }, emptyLogical),
            m => m.observe({ overflow: { online: true, viewport: { width: 1e307, height: 1 } } }, emptyLogical),
            m => m.commit({ kind: "logical", placements: { a: { w: 20, h: 30 } } }),
            m => m.observe({}, { kind: "physical", slots: { a: { center_x_mm: 0 } } }),
            m => m.commit({ kind: "physical", slots: {} }),
        ];
        const next = membership(), previous = old.membership();
        for (const step of steps) {
            step(next);
            step(previous);
            expect(next.view()).toEqual(previous.view());
        }
    });
});
