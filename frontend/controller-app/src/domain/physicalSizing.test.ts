import { expect, it } from 'vitest';
import * as sizing from './physicalSizing';

it('tests/physical_sizing.test.js', () => {
	const profiles: Record<string, { active_width_mm: number; active_height_mm: number; bezels: { left: number; right: number; top: number; bottom: number } }> = {
		"a:1": { active_width_mm: 100, active_height_mm: 60, bezels: { left: 2, right: 4, top: 3, bottom: 5 } },
		"b:2": { active_width_mm: 80, active_height_mm: 40, bezels: { left: 0, right: 0, top: 0, bottom: 0 } }
	};
	const profileFor = (id: string, revision: number | undefined) => profiles[id + ":" + revision] || null;
	const slot = (x: number, y: number, angle: number, nx: number, ny: number, revision = 1) => ({
		center_x_mm: x, center_y_mm: y, mount_angle: angle,
		nudge_x_mm: nx, nudge_y_mm: ny, profile_revision: revision
	});

	const zero = sizing.fitBounds({ a: slot(0, 0, 0, 0, 0) }, profileFor, 0).bounds;
	expect(zero).toEqual({ x: -53, y: -34, width: 106, height: 68 });
	const quarter = sizing.fitBounds({ a: slot(0, 0, 90, 0, 0) }, profileFor, 0).bounds!;
	expect(Math.abs(quarter.width - 68) < 1e-9 && Math.abs(quarter.height - 106) < 1e-9).toBeTruthy();
	const diagonal = sizing.fitBounds({ b: slot(0, 0, 45, 0, 0, 2) }, profileFor, 0).bounds!;
	expect(Math.abs(diagonal.width - Math.sqrt(7200)) < 1e-9).toBeTruthy();
	expect(diagonal.width).toBe(diagonal.height);

	const nudged = sizing.fitBounds({ a: slot(10, -4, 0, 7, -3) }, profileFor, 5).bounds;
	expect(nudged).toEqual({ x: -41, y: -46, width: 116, height: 78 });
	expect(sizing.fitBounds({}, profileFor, 10).bounds).toBe(null);
	const missing = sizing.fitBounds({ a: slot(0, 0, 0, 0, 0, 9) }, profileFor, 0);
	expect(missing.error).toMatch(/Exact display profile r9 is missing/);
	expect(sizing.fitBounds({ a: slot(0, 0, 0, 0, 0) }, profileFor, 1e308).error).toMatch(/finite/);

	const mixed = {
		a: Object.assign(slot(0, 0, 90, 5, 2), { calibration_revision: 4, participating: false }),
		b: Object.assign(slot(0, 0, 45, -2, 1, 2), { calibration_revision: 7 })
	};
	const packed = sizing.packSlots(mixed, profileFor, 1, 12, 8);
	expect(Object.keys(packed.slots!)).toEqual(["a", "b"]);
	expect(packed.slots!.a!.mount_angle).toBe(90);
	expect(packed.slots!.a!.nudge_x_mm).toBe(5);
	expect(packed.slots!.a!.participating).toBe(false);
	expect(packed.slots!.b!.profile_revision).toBe(2);
	const bounds = sizing.fitBounds(packed.slots, profileFor, 8).bounds!;
	expect(bounds.width <= packed.bounds!.width + 1e-9).toBeTruthy();
	expect(bounds.height <= packed.bounds!.height + 1e-9).toBeTruthy();
	const repeated = sizing.packSlots(packed.slots, profileFor, 1, 12, 8);
	expect(repeated).toEqual(packed);

	const adjacent = sizing.packSlots({
		a: slot(0, 0, 0, 5, 2),
		b: slot(0, 0, 0, -2, 1, 2),
		c: slot(0, 0, 90, 0, 0)
	}, (id: string, revision: number | undefined) => profileFor(id === "c" ? "a" : id, revision), 2, 0, 0);
	const aRight = adjacent.slots!.a!.center_x_mm + 5 + 106 / 2;
	const bLeft = adjacent.slots!.b!.center_x_mm - 2 - 80 / 2;
	expect(aRight).toBe(bLeft);
	expect(adjacent.bounds!.width).toBe(186);

	const emptyPack = sizing.packSlots({}, profileFor, 3, 4, 5);
	expect(emptyPack).toEqual({ slots: {}, bounds: null });
	const blockedPack = sizing.packSlots({ a: slot(0, 0, 0, 0, 0, 99) }, profileFor, 1, 0, 0);
	expect(blockedPack.error).toMatch(/Exact display profile r99 is missing/);

	console.log("Physical sizing geometry passed");
});
