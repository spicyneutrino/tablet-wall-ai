import { describe, expect, it } from 'vitest';
import { ConfigSchema } from '../../api/config';
import { LogicalLayoutSchema, PhysicalLayoutSchema } from '../../api/layouts';
import type { Layout } from '../../api/layouts';
import { A, B, configFixture } from '../../session/testFixtures';
import { createArrangement } from '../../state/drafts/arrangement';
import { emptyContent } from '../../state/drafts/content';
import { createForm, formKey } from '../../state/drafts/tabletForms';
import { createWallStore } from '../../state/store';
import type { WallStore } from '../../state/store';
import { conflictItems, describeLayoutChange, describeScene } from './model';

const bezel = { top: 0, right: 0, bottom: 0, left: 0 };
const logical = (placements: Record<string, { x: number; y: number; w?: number; h?: number }>, width = 100): Layout => LogicalLayoutSchema.parse({
  kind: 'logical', width, height: 100, sizing: { mode: 'fixed', padding: 0 },
  placements: Object.fromEntries(Object.entries(placements).map(([id, p]) => [id, { w: 10, h: 10, bezel, ...p }])) });
const slot = (x: number, angle = 0) => ({ center_x_mm: x, center_y_mm: 0, mount_angle: angle, nudge_x_mm: 0, nudge_y_mm: 0,
  profile_revision: 1, calibration_revision: 1 });
const physical = (slots: Record<string, ReturnType<typeof slot>>): Layout => PhysicalLayoutSchema.parse({
  kind: 'physical', bounds: { x: 0, y: 0, width: 100, height: 100 }, sizing: { mode: 'fixed', padding: 0 }, slots });

function wallWith(layout: Layout, overrides: Partial<WallStore> = {}): WallStore {
  const store = createWallStore(0);
  const config = ConfigSchema.parse({ ...configFixture('now'), layout });
  return { ...store.getState(), server: { ...store.getState().server, config, etag: config.etag, etagState: 'current',
    roster: { ...config.runtime.devices } }, ...overrides };
}

describe('describeLayoutChange', () => {
  it('counts what moved, turned, resized, added and removed', () => {
    const from = logical({ [A]: { x: 0, y: 0 }, [B]: { x: 10, y: 0 } });
    expect(describeLayoutChange(from, logical({ [A]: { x: 5, y: 0 }, [B]: { x: 10, y: 0, w: 20 } }))).toBe('1 tablet moved, Tablet now 20 × 10');
    expect(describeLayoutChange(from, logical({ [A]: { x: 0, y: 0 } }))).toBe('1 removed');
    expect(describeLayoutChange(physical({ [A]: slot(0) }), physical({ [A]: slot(40, 90), [B]: slot(80) }))).toBe('1 tablet moved, 1 turned, 1 added');
  });
  it('names a kind switch, a resize and an identical layout', () => {
    const from = logical({ [A]: { x: 0, y: 0 } });
    expect(describeLayoutChange(from, physical({ [A]: slot(0) }))).toBe('Switched to a physical layout');
    expect(describeLayoutChange(from, logical({ [A]: { x: 0, y: 0 } }, 200))).toBe('Wall size changed');
    expect(describeLayoutChange(from, logical({ [A]: { x: 0, y: 0 } }))).toBe('Layout unchanged');
  });
  it('names up to two resized tablets with their new size', () => {
    const third = '00000000-0000-4000-8000-000000000003';
    const from = logical({ [A]: { x: 0, y: 0 }, [B]: { x: 10, y: 0 } });
    const names = { [A]: 'Wall left', [B]: 'Wall right' };
    expect(describeLayoutChange(from, logical({ [A]: { x: 0, y: 0, w: 20 }, [B]: { x: 10, y: 0 } }), names)).toBe('Wall left now 20 × 10');
    expect(describeLayoutChange(from, logical({ [A]: { x: 0, y: 0, w: 20 }, [B]: { x: 10, y: 0, w: 20 } }), names)).toBe('Wall left now 20 × 10, Wall right now 20 × 10');
    const three = logical({ [A]: { x: 0, y: 0 }, [B]: { x: 10, y: 0 }, [third]: { x: 20, y: 0 } });
    expect(describeLayoutChange(three, logical({ [A]: { x: 0, y: 0, w: 20 }, [B]: { x: 10, y: 0, w: 20 }, [third]: { x: 20, y: 0, w: 20 } }), names)).toBe('3 resized');
  });
});

describe('describeScene', () => {
  it('names the content in the wording On wall uses', () => {
    expect(describeScene({ type: 'calibration' })).toBe('Calibration grid');
    expect(describeScene({ type: 'color' })).toBe('Tablet colours');
    expect(describeScene({ type: 'image', asset: `sha256:${'a'.repeat(64)}` as never, fit: 'contain', name: 'Lobby' } as never)).toBe('Lobby, Fit');
    expect(describeScene(null)).toBe('Nothing yet');
  });
});

describe('conflictItems', () => {
  it('is empty without a conflict, and lists each conflicted draft with both sides', () => {
    const base = logical({ [A]: { x: 0, y: 0 } });
    expect(conflictItems(wallWith(base, { arrangement: createArrangement(base, null) }))).toEqual([]);
    const mine = { ...createArrangement(base, null), draft: logical({ [A]: { x: 30, y: 0 } }), conflict: true };
    const items = conflictItems(wallWith(logical({ [A]: { x: 0, y: 0 }, [B]: { x: 10, y: 0 } }), { arrangement: mine,
      content: { ...emptyContent(), conflict: true, selection: { type: 'calibration' } },
      forms: { [formKey(A, 'name')]: { ...createForm(A, 'name', { name: '' }, null), values: { name: 'Lobby' }, dirty: true, conflict: true } } }));
    expect(items.map(item => item.kind)).toEqual(['arrangement', 'content', 'form']);
    expect(items[0]).toMatchObject({ wall: '1 added', mine: '1 tablet moved' });
    expect(items[1]).toMatchObject({ mine: 'Calibration grid', keepable: true });
    expect(items[2]).toMatchObject({ mine: 'Name', wall: 'No fields changed' });
  });
  it('does not offer Keep mine for a saved-scene preview', () => {
    const base = logical({ [A]: { x: 0, y: 0 } });
    const item = conflictItems(wallWith(base, { content: { ...emptyContent(), conflict: true, selection: { type: 'color' },
      savedScene: { name: 'Lobby', etag: 'x' as never } } }))[0];
    expect(item).toMatchObject({ kind: 'content', keepable: false });
  });
});
