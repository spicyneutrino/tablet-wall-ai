import { expect, it } from 'vitest';
import { LayoutSchema } from '../../api/layouts';
import { moved, parseSeconds, participants, playlistSummary, secondsText, startReason } from './model';

const slot = { center_x_mm: 0, center_y_mm: 0, mount_angle: 0, nudge_x_mm: 0, nudge_y_mm: 0, profile_revision: 1, calibration_revision: 1 };
const a = '00000000-0000-4000-8000-000000000001', b = '00000000-0000-4000-8000-000000000002';
const physical = LayoutSchema.parse({ kind: 'physical', bounds: { x: 0, y: 0, width: 100, height: 50 },
  sizing: { mode: 'fixed', padding: 0 }, slots: { [a]: slot, [b]: { ...slot, participating: false } } });
const logical = LayoutSchema.parse({ kind: 'logical', width: 100, height: 50, sizing: { mode: 'fixed', padding: 0 }, placements: {} });

it('turns typed seconds into dwell_ms from 1000 to 600000 and says what is wrong otherwise', () => {
  expect(parseSeconds('1')).toEqual({ ok: true, ms: 1000 });
  expect(parseSeconds(' 2.5 ')).toEqual({ ok: true, ms: 2500 });
  expect(parseSeconds('600')).toEqual({ ok: true, ms: 600000 });
  for (const text of ['0', '0.999', '600.001', '601']) expect(parseSeconds(text)).toEqual({ ok: false, error: 'Use 1 to 600 seconds.' });
  for (const text of ['abc', '-3', '1e3', '2,5', '1.2345']) expect(parseSeconds(text)).toMatchObject({ ok: false, error: 'Use a number of seconds, such as 5 or 2.5.' });
  expect(parseSeconds('  ')).toMatchObject({ ok: false, error: 'Enter how many seconds this image stays up.' });
  expect(secondsText(2500)).toBe('2.5');
  expect(secondsText(10000)).toBe('10');
});

it('moves one item and keeps the rest in order', () => {
  expect(moved(['a', 'b', 'c'], 2, 0)).toEqual(['c', 'a', 'b']);
  expect(moved(['a', 'b', 'c'], 0, 1)).toEqual(['b', 'a', 'c']);
});

it('summarises the playlist with its length and loop', () => {
  const item = (dwell_ms: number) => ({ asset: `sha256:${'a'.repeat(64)}` as never, dwell_ms });
  expect(playlistSummary([item(10000), item(5000), item(3000)], true)).toBe('3 items, 18 s loop');
  expect(playlistSummary([item(2500)], false)).toBe('1 item, 2.5 s');
});

it('explains why Start is unavailable, in the order a person can fix it', () => {
  const ok = { layout: physical, saved: true, supported: true, uncertain: false };
  expect(participants(physical)).toEqual([a]);
  expect(participants(logical)).toEqual([]);
  expect(startReason(ok)).toBeNull();
  expect(startReason({ ...ok, supported: false })).toMatch(/Update the console/);
  expect(startReason({ ...ok, uncertain: true })).toMatch(/Refresh status/);
  expect(startReason({ ...ok, layout: logical })).toMatch(/physical layout/);
  expect(startReason({ ...ok, layout: undefined })).toMatch(/physical layout/);
  expect(startReason({ ...ok, saved: false })).toBe('Save the playlist first.');
});
