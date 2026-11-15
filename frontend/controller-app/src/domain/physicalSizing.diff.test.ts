import { createRequire } from 'node:module';
import { expect, it } from 'vitest';
import * as sizing from './physicalSizing';

const require = createRequire(import.meta.url);
const old = require('../../../controller/physical-sizing.js') as typeof sizing;

it('physicalSizing matches the old module', () => {
	const profiles: Record<string, { active_width_mm: number; active_height_mm: number; bezels: { left: number; right: number; top: number; bottom: number } }> = {
		"a:1": { active_width_mm: 100, active_height_mm: 60, bezels: { left: 2, right: 4, top: 3, bottom: 5 } },
		"b:2": { active_width_mm: 80, active_height_mm: 40, bezels: { left: 0, right: 0, top: 0, bottom: 0 } }
	};
	const profileFor = (id: string, revision: number | undefined) => profiles[id + ":" + revision] || null;
	const slot = (x: number, y: number, angle: number, nx: number, ny: number, revision = 1) => ({
		center_x_mm: x, center_y_mm: y, mount_angle: angle,
		nudge_x_mm: nx, nudge_y_mm: ny, profile_revision: revision
	});

	expect(sizing.fitBounds({ a: slot(0, 0, 0, 0, 0) }, profileFor, 0))
		.toEqual(old.fitBounds({ a: slot(0, 0, 0, 0, 0) }, profileFor, 0));
	expect(sizing.fitBounds({ a: slot(0, 0, 90, 0, 0) }, profileFor, 0))
		.toEqual(old.fitBounds({ a: slot(0, 0, 90, 0, 0) }, profileFor, 0));
	expect(sizing.fitBounds({ b: slot(0, 0, 45, 0, 0, 2) }, profileFor, 0))
		.toEqual(old.fitBounds({ b: slot(0, 0, 45, 0, 0, 2) }, profileFor, 0));
	expect(sizing.fitBounds({ a: slot(10, -4, 0, 7, -3) }, profileFor, 5))
		.toEqual(old.fitBounds({ a: slot(10, -4, 0, 7, -3) }, profileFor, 5));
	expect(sizing.fitBounds({}, profileFor, 10))
		.toEqual(old.fitBounds({}, profileFor, 10));
	expect(sizing.fitBounds({ a: slot(0, 0, 0, 0, 0, 9) }, profileFor, 0))
		.toEqual(old.fitBounds({ a: slot(0, 0, 0, 0, 0, 9) }, profileFor, 0));
	expect(sizing.fitBounds({ a: slot(0, 0, 0, 0, 0) }, profileFor, 1e308))
		.toEqual(old.fitBounds({ a: slot(0, 0, 0, 0, 0) }, profileFor, 1e308));

	const mixed = {
		a: Object.assign(slot(0, 0, 90, 5, 2), { calibration_revision: 4, participating: false }),
		b: Object.assign(slot(0, 0, 45, -2, 1, 2), { calibration_revision: 7 })
	};
	const packed = sizing.packSlots(mixed, profileFor, 1, 12, 8);
	expect(packed).toEqual(old.packSlots(mixed, profileFor, 1, 12, 8));
	expect(sizing.fitBounds(packed.slots, profileFor, 8))
		.toEqual(old.fitBounds(packed.slots, profileFor, 8));
	expect(sizing.packSlots(packed.slots, profileFor, 1, 12, 8))
		.toEqual(old.packSlots(packed.slots, profileFor, 1, 12, 8));

	const adjacentSlots = {
		a: slot(0, 0, 0, 5, 2),
		b: slot(0, 0, 0, -2, 1, 2),
		c: slot(0, 0, 90, 0, 0)
	};
	const adjacentProfileFor = (id: string, revision: number | undefined) => profileFor(id === "c" ? "a" : id, revision);
	expect(sizing.packSlots(adjacentSlots, adjacentProfileFor, 2, 0, 0))
		.toEqual(old.packSlots(adjacentSlots, adjacentProfileFor, 2, 0, 0));

	expect(sizing.packSlots({}, profileFor, 3, 4, 5))
		.toEqual(old.packSlots({}, profileFor, 3, 4, 5));
	expect(sizing.packSlots({ a: slot(0, 0, 0, 0, 0, 99) }, profileFor, 1, 0, 0))
		.toEqual(old.packSlots({ a: slot(0, 0, 0, 0, 0, 99) }, profileFor, 1, 0, 0));
});
