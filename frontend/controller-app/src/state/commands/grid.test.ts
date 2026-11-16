import { expect, it, vi } from 'vitest';
import { ConfigEtagSchema } from '../../api/etag';
import { GridCommandSchema, GridPreviewSchema } from '../../api/grid';
import type { GridPreview } from '../../api/grid';
import { A } from '../../session/testFixtures';
import type { Session } from '../../session/session';
import { createGrid } from '../drafts/grid';
import { createWallStore } from '../store';
import type { WallStoreApi } from '../store';
import { applyGrid, gridOutdated } from './grid';

const base = ConfigEtagSchema.parse('base');
const next = ConfigEtagSchema.parse('next');
const command = GridCommandSchema.parse({ kind: 'logical', device_ids: [A], rows: 1, columns: 1, gap: 0, padding: 0,
  sizing: 'tablets', orientation: 'preserve', allow_empty_cells: false, release_unselected: [],
  logical_sizes: { [A]: { w: 100, h: 100 } } });
const preview = GridPreviewSchema.parse({ layout: { kind: 'logical', width: 100, height: 100, sizing: { mode: 'tablets', padding: 0 },
  placements: { [A]: { device_id: A, x: 0, y: 0, w: 100, h: 100, bezel: { top: 0, right: 0, bottom: 0, left: 0 } } } },
  order: [A], warnings: [], guards: { [A]: { connection_id: 'connection-1', viewport: null } }, base_etag: 'base',
  reservations_removed: [], previous_kind: 'logical' });

function setup(etag = base) {
  const store = createWallStore() as WallStoreApi;
  store.setState(state => ({ server: { ...state.server, etag, etagState: 'current' },
    grid: { ...createGrid(command, etag), preview: preview as GridPreview, dirty: true, frozen: true } }));
  return store;
}
function session(outcome: Awaited<ReturnType<Session['request']>>) {
  return { request: vi.fn(async () => outcome) } as unknown as Session;
}

it('gridOutdated follows the wall ETag, not only the stored flag', () => {
  const store = setup(), grid = store.getState().grid!;
  expect(gridOutdated(grid, base)).toBe(false);
  expect(gridOutdated(grid, next)).toBe(true);
  expect(gridOutdated({ ...grid, stale: true }, base)).toBe(true);
});

it('apply sends the preview guards and base ETag, then clears the draft it applied', async () => {
  const store = setup(), send = session({ kind: 'ok', value: { etag: 'next' } as never });
  const outcome = await applyGrid(store, send);
  expect(outcome).toMatchObject({ kind: 'ok' });
  expect(send.request).toHaveBeenCalledExactlyOnceWith('POST', '/api/v3/grid',
    expect.objectContaining({ guards: preview.guards, device_ids: [A] }), expect.objectContaining({ ifMatch: 'base' }));
  expect(store.getState().grid).toBeNull();
});

it('a guard refusal keeps the preview and inputs, and names the connection or viewport change', async () => {
  const store = setup(), before = store.getState().grid, send = session({ kind: 'conflict' });
  const outcome = await applyGrid(store, send);
  expect(outcome).toMatchObject({ kind: 'rejected', status: 412, message: expect.stringMatching(/connection or viewport/i) });
  expect(store.getState().grid).toEqual(before);
});

it('a wall change observed while the command is in flight marks the kept preview stale', async () => {
  const store = setup();
  const send = { request: vi.fn(async () => {
    store.setState(state => ({ server: { ...state.server, etag: next } }));
    return { kind: 'conflict' } as const;
  }) } as unknown as Session;
  const outcome = await applyGrid(store, send);
  expect(outcome).toMatchObject({ kind: 'rejected', status: 412, message: expect.stringMatching(/wall changed/i) });
  expect(store.getState().grid).toMatchObject({ stale: true, preview, command });
});

it('never posts a preview that no longer matches the wall', async () => {
  const store = setup(next), send = session({ kind: 'conflict' });
  expect(await applyGrid(store, send)).toMatchObject({ kind: 'rejected', status: 409 });
  expect(send.request).not.toHaveBeenCalled();
});
