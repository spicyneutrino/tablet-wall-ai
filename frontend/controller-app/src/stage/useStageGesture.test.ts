import { describe, expect, it } from 'vitest';
import { DeviceIdSchema } from '../api/devices';
import { LayoutSchema } from '../api/layouts';
import { createWallStore } from '../state/store';
import { canEditStage, changeStageLayout, fitStageLayout, normalizeAngle, positionReadout } from './useStageGesture';

const id = DeviceIdSchema.parse('1eb61a6f-0872-4cb4-9107-6523136723ae');
const other = DeviceIdSchema.parse('4e7c531d-d258-45a5-b787-e4e8ccc5a1c9');
const snap = { step: 10, enabled: true, scale: 2 };
const logical = () => LayoutSchema.parse({ kind: 'logical', width: 600, height: 400,
  sizing: { mode: 'fixed', padding: 0 }, placements: {
    [id]: { x: 60, y: 80, w: 160, h: 120, bezel: { top: 10, right: 20, bottom: 30, left: 40 }, extra: 'keep' },
    [other]: { x: 320, y: 80, w: 120, h: 160, bezel: { top: 0, right: 0, bottom: 0, left: 0 } },
  } });
const physical = () => LayoutSchema.parse({ kind: 'physical', bounds: { x: -50, y: -50, width: 500, height: 400 },
  sizing: { mode: 'fixed', padding: 0 }, slots: {
    [id]: { center_x_mm: 120, center_y_mm: 100, nudge_x_mm: 5, nudge_y_mm: -3, mount_angle: 90,
      profile_revision: 2, calibration_revision: 3, participating: false },
  } });

describe('stage geometry edits', () => {
  it('keeps local draft editing available during uncertainty, while blocking a busy or live stage', () => {
    const store = createWallStore();
    store.setState(state => ({ server: { ...state.server, supported: true, uncertain: true }, ui: { ...state.ui, editLayout: true } }));
    expect(canEditStage(store.getState())).toBe(true);
    store.setState(state => ({ server: { ...state.server, busy: true } }));
    expect(canEditStage(store.getState())).toBe(false);
    store.setState(state => ({ server: { ...state.server, busy: false }, ui: { ...state.ui, editLayout: false } }));
    expect(canEditStage(store.getState())).toBe(false);
  });
  it('moves the physical centre without changing nudges, revisions, participation or bounds', () => {
    const before = physical();
    const result = changeStageLayout(before, id, { type: 'move', dx: 12.345, dy: -6.123 }, snap);
    expect(result.layout).toMatchObject({ bounds: before.kind === 'physical' ? before.bounds : {}, slots: {
      [id]: { center_x_mm: 132.35, center_y_mm: 93.88, nudge_x_mm: 5, nudge_y_mm: -3, mount_angle: 90,
        profile_revision: 2, calibration_revision: 3, participating: false },
    } });
    expect(before).toEqual(physical());
  });
  it('nudges physical placement independently of the declared centre', () => {
    const result = changeStageLayout(physical(), id, { type: 'move', dx: 1, dy: -10, nudge: true }, snap);
    expect(result.layout).toMatchObject({ slots: { [id]: { center_x_mm: 120, center_y_mm: 100, nudge_x_mm: 6, nudge_y_mm: -13 } } });
  });
  it('keeps physical size profile-controlled', () => {
    const before = physical();
    expect(changeStageLayout(before, id, { type: 'resize', dx: 100, dy: 100, handle: 'se' }, snap)).toEqual({ layout: before });
  });
  it('preserves the legacy three-decimal precision when nudging a measured placement', () => {
    const before = physical();
    if (before.kind !== 'physical') throw new Error('Expected physical layout');
    before.slots[id]!.nudge_x_mm = 0.234;
    expect(changeStageLayout(before, id, { type: 'move', dx: 1, dy: 0, nudge: true }, snap).layout)
      .toMatchObject({ slots: { [id]: { nudge_x_mm: 1.234 } } });
  });
  it('normalizes free angles without changing physical position', () => {
    expect(changeStageLayout(physical(), id, { type: 'rotate', angle: -323 }, snap).layout)
      .toMatchObject({ slots: { [id]: { mount_angle: 37, center_x_mm: 120, center_y_mm: 100 } } });
    expect(normalizeAngle(450)).toBe(90);
  });
  it('snaps logical grid movement and pauses snapping for precise movement', () => {
    expect(changeStageLayout(logical(), id, { type: 'move', dx: 16, dy: 17 }, snap).layout)
      .toMatchObject({ placements: { [id]: { x: 80, y: 100 } } });
    expect(changeStageLayout(logical(), id, { type: 'move', dx: 16, dy: 17 }, { ...snap, enabled: false }).layout)
      .toMatchObject({ placements: { [id]: { x: 76, y: 97 } } });
  });
  it('snaps to another body edge using an eight-pixel threshold at the current scale', () => {
    expect(changeStageLayout(logical(), id, { type: 'move', dx: 101, dy: 0 }, snap).layout)
      .toMatchObject({ placements: { [id]: { x: 160, y: 80 } } });
  });
  it('preserves the opposite corner when resizing northwest', () => {
    expect(changeStageLayout(logical(), id, { type: 'resize', dx: -20, dy: -10, handle: 'nw' }, snap).layout)
      .toMatchObject({ placements: { [id]: { x: 40, y: 70, w: 180, h: 130, extra: 'keep' } } });
  });
  it('refuses a resize below the bezels with the ported validation message', () => {
    expect(changeStageLayout(logical(), id, { type: 'resize', dx: -110, dy: 0, handle: 'e' }, snap))
      .toEqual({ error: 'Bezels leave no visible width. Reduce the left or right bezel.' });
  });
  it('refuses dimensions above the fixed wall size and invalid snapped sizes', () => {
    expect(changeStageLayout(logical(), id, { type: 'resize', dx: 500, dy: 0, handle: 'e' }, snap))
      .toEqual({ error: 'Width 660 is larger than the wall width 600 relative units. Use a size that fits the wall.' });
    expect(changeStageLayout(logical(), id, { type: 'resize', dx: 430, dy: 0, handle: 'e' }, { ...snap, step: 1000 }))
      .toEqual({ error: 'Width 1000 is larger than the wall width 600 relative units. Use a size that fits the wall.' });
  });
  it('rotates logical dimensions and asymmetric bezels around the centre', () => {
    expect(changeStageLayout(logical(), id, { type: 'rotate', angle: 90 }, snap).layout)
      .toMatchObject({ placements: { [id]: { x: 80, y: 60, w: 120, h: 160,
        bezel: { top: 40, right: 10, bottom: 20, left: 30 }, extra: 'keep' } } });
    expect(changeStageLayout(logical(), id, { type: 'rotate', angle: -90 }, snap).layout)
      .toMatchObject({ placements: { [id]: { bezel: { top: 20, right: 30, bottom: 40, left: 10 } } } });
  });
  it('reports rendered physical position including nudge', () => {
    expect(positionReadout(physical(), id)).toBe('x 125  y 97 mm  90°');
  });
  it('refits logical bounds once at commit time and preserves per-tablet metadata', () => {
    const before = logical();
    before.sizing = { mode: 'tablets', padding: 10 };
    const fitted = fitStageLayout(before, () => null);
    expect(fitted.layout).toMatchObject({ width: 400, height: 180,
      placements: { [id]: { x: 10, y: 10, extra: 'keep' }, [other]: { x: 270, y: 10 } } });
    expect(before).toMatchObject({ width: 600, height: 400, placements: { [id]: { x: 60 } } });
  });
  it('refits physical bounds with the pinned profile and keeps prior bounds if it is missing', () => {
    const before = physical();
    before.sizing = { mode: 'tablets', padding: 10 };
    const revisions: (number | string | undefined)[] = [];
    const fitted = fitStageLayout(before, (_, revision) => {
      revisions.push(revision);
      return { active_width_mm: 100, active_height_mm: 60 };
    });
    expect(fitted.layout).toMatchObject({ bounds: { x: 85, y: 37, width: 80, height: 120 } });
    expect(revisions).toEqual([2]);
    const missing = fitStageLayout(before, () => null);
    expect(missing.layout).toEqual(before);
    expect(missing.warning).toContain('Exact display profile r2 is missing');
  });
});
