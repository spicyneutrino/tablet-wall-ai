import { describe, it, expect } from 'vitest';
import { command, membership, type GridCommandInput } from './gridCommand';

describe('tests/operator_grid.test.js', () => {
    it('operator_grid', () => {
        const source: GridCommandInput = { kind: "logical", ids: ["four", "one", "two", "three"], rows: 2, columns: 2, gap: 0, padding: 0,
            sizing: "tablets", orientation: "preserve", holes: false, releases: ["offline"],
            sizes: Object.fromEntries(["one", "two", "three", "four"].map(id => [id, { w: 100, h: 60 }])) };
        const logical = command(source);
        expect(logical.device_ids, "submitted order is the sole order of record").toEqual(source.ids);
        expect(logical.release_unselected).toEqual(["offline"]);
        expect(logical.physical_revisions).toBe(undefined);
        expect(logical.mount_angles).toBe(undefined);
        expect(command({ ...source, rows: 1, columns: 4 }).rows).toBe(1);
        expect(() => command({ ...source, ids: [] })).toThrow(/at least one/);
        expect(() => command({ ...source, ids: ["one", "one"] })).toThrow(/duplicate/);
        expect(() => command({ ...source, ids: ["one"] })).toThrow(/exactly 4/);
        expect(command({ ...source, ids: ["one"], holes: true }).allow_empty_cells).toBe(true);
        for (const value of [0, NaN, Infinity, true, 1.5] as number[]) expect(() => command({ ...source, rows: value })).toThrow(/whole numbers/);
        for (const value of [-1, NaN, Infinity, 0.5]) expect(() => command({ ...source, gap: value })).toThrow(/nonnegative/);
        expect(() => command({ ...source, sizes: {} })).toThrow(/logical sizes/);
        const physical = command({ ...source, kind: "physical", ids: ["one"], rows: 1, columns: 1, gap: 0.5,
            revisions: { one: { profile_revision: 1, calibration_revision: 2 } }, angles: { one: "90" } });
        expect(physical.logical_sizes).toBe(undefined);
        expect(physical.mount_angles).toEqual({ one: 90 });
        expect(() => command({ ...source, kind: "physical", revisions: {}, angles: {} })).toThrow(/measurements/);

        const emptyLogical = { kind: "logical", placements: {} };
        const live = membership();
        live.observe({ a: { online: true, viewport: { width: 1600, height: 1000 } } }, emptyLogical);
        const liveView = live.view();
        expect(liveView.a!.size.w, "a live viewport derives an integer relative width").toBe(160);
        expect(liveView.a!.size.h).toBe(100);
        expect(liveView.a!.sizeSource).toBe("viewport");
        live.freeze();
        live.observe({ a: { online: true, viewport: { width: 1000, height: 1000 } } }, emptyLogical);
        expect(live.view().a!.size, "a frozen live join never overwrites explicit geometry").toEqual({ w: 160, h: 100 });
        const explicit = membership();
        explicit.observe({ b: { online: true, viewport: { width: 1600, height: 1000 } } }, emptyLogical);
        explicit.size("b", { w: 123, h: 45 });
        explicit.observe({ b: { online: true, viewport: { width: 1000, height: 1000 } } }, emptyLogical);
        expect(explicit.view().b!.size, "operator size provenance survives later viewport reports").toEqual({ w: 123, h: 45 });
        expect(explicit.view().b!.sizeSource).toBe("operator");
        const saved = membership();
        saved.observe({ c: { online: true, viewport: { width: 2000, height: 1000 } } }, { kind: "logical", placements: { c: { w: 50, h: 40 } } });
        expect(saved.view().c!.size, "saved geometry is never replaced by a live viewport").toEqual({ w: 50, h: 40 });
        expect(saved.view().c!.sizeSource).toBe("saved");
        saved.observe({ c: { online: true, viewport: { width: 2000, height: 1000 } } }, { kind: "logical", placements: { c: { w: 60, h: 40 } } }, { refreshSaved: true });
        expect(saved.view().c!.size, "an explicit saved refresh can adopt the reviewed saved size").toEqual({ w: 60, h: 40 });
        const offline = membership();
        offline.observe({ d: { online: false, viewport: { width: 1600, height: 1000 } } }, emptyLogical);
        expect(offline.view().d!.size, "an offline viewport cannot define a new logical size").toEqual({ w: 100, h: 100 });
        expect(offline.view().d!.sizeSource).toBe("fallback");
        const invalidViewport = membership();
        invalidViewport.observe({ e: { online: true, viewport: { width: Infinity, height: 1000 } } }, emptyLogical);
        expect(invalidViewport.view().e!.size, "a non-finite viewport cannot define an infinite logical size").toEqual({ w: 100, h: 100 });
        expect(invalidViewport.view().e!.sizeSource).toBe("fallback");
        invalidViewport.observe({ f: { online: true, viewport: { width: 1600, height: 900 } } }, emptyLogical);
        expect(invalidViewport.view().f!.size, "a fractional viewport ratio still yields whole logical units").toEqual({ w: 178, h: 100 });
        offline.include("d", true);
        expect(offline.view().d!.membershipSource, "explicit inclusion is recorded separately from live presence").toBe("operator");
        expect(offline.view().d!.included).toBe(true);

        const hugeViewport = membership();
        hugeViewport.observe({ huge: { online: true, viewport: { width: 1e307, height: 1e307 } } }, emptyLogical);
        expect(hugeViewport.view().huge!.size, "large finite square dimensions retain a finite square ratio").toEqual({ w: 100, h: 100 });
        expect(hugeViewport.view().huge!.sizeSource).toBe("viewport");
        hugeViewport.observe({ overflow: { online: true, viewport: { width: 1e307, height: 1 } } }, emptyLogical);
        expect(hugeViewport.view().overflow!.size, "a ratio whose derived width overflows keeps fallback geometry").toEqual({ w: 100, h: 100 });
        expect(hugeViewport.view().overflow!.sizeSource).toBe("fallback");
    });
});
