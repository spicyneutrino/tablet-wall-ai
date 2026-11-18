import { expect, it, vi } from 'vitest';
import { GridCommandSchema, GridPreviewSchema } from '../../api/grid';
import { ConfigEtagSchema } from '../../api/etag';
import { A, configFixture, deviceFixture } from '../../session/testFixtures';
import { createSession } from '../../session/session';
import { createWallStore, editArrangement, editGrid } from '../store';
import { previewGrid, rebuildGrid } from '../commands/run';
import { createGrid } from './grid';

const etag = ConfigEtagSchema.parse;
function setup() {
  const config = configFixture('base'), store = createWallStore();
  const session = createSession({ store, isDirty: () => false }); session.ingest(config);
  const command = GridCommandSchema.parse({ kind: 'logical', device_ids: [A], rows: 1, columns: 1,
    gap: 0, padding: 0, sizing: 'fixed', orientation: 'preserve', allow_empty_cells: false, release_unselected: [] });
  store.setState({ grid: createGrid(command, config.etag) });
  const preview = GridPreviewSchema.parse({ layout: config.layout, order: [A], warnings: [], guards: {},
    base_etag: 'base', reservations_removed: [], previous_kind: 'logical' });
  return { store, session, command, config, preview };
}
it('a grid preview with a stale base_etag is marked stale and is never silently re-applied', () => {
  const { store, session, preview } = setup();
  editGrid(store, { type: 'preview', preview, version: 0, etag: etag('base') });
  session.ingest(configFixture('remote'));
  expect(store.getState().grid).toMatchObject({ preview, baseEtag: 'base', stale: true });
  session.destroy();
});
it('ports late-join lines 26, 27, 30, 31: reads do not observe membership; explicit observation admits fresh viewport', () => {
  const { store, session, config } = setup();
  editGrid(store, { type: 'observe', roster: { [A]: { online: false } }, layout: config.layout });
  const before = store.getState().grid;
  session.ingest({ ...config, runtime: { ...config.runtime, devices: { [A]: deviceFixture(A,
    { viewport: { width: 900, height: 1280, dpr: 1, visual_scale: 1, orientation: 0, mode: 'tab' } }) } } });
  const view = () => store.getState().grid;
  view(); view();
  expect(view()?.members).toEqual(before?.members);
  expect(Object.keys(view()!.members).filter(id => view()!.members[id]?.included)).toEqual([]);
  editGrid(store, { type: 'observe', roster: store.getState().server.roster, layout: config.layout });
  expect(view()!.members[A]?.included).toBe(true);
  expect(view()!.members[A]?.size.w).toBe(70);
  editGrid(store, { type: 'observe', roster: { [A]: { online: false } }, layout: config.layout });
  expect(view()!.members[A]).toMatchObject({ included: true, size: { w: 70, h: 100 }, sizeSource: 'viewport' });
  session.destroy();
});
it('ports late-join line 37: a model response cannot authorize a retained grid against unrelated authority', async () => {
  const { store, session, command } = setup();
  editGrid(store, { type: 'edit', command, etag: etag('base') });
  session.ingest(configFixture('unrelated'));
  editGrid(store, { type: 'model-saved', commandEtag: etag('own-returned'), currentEtag: etag('unrelated') });
  const transport = vi.fn();
  const outcome = await previewGrid(store, transport);
  expect(outcome.kind === 'rejected' && outcome.message).toMatch(/Rebuild preview explicitly/);
  expect(transport).not.toHaveBeenCalled(); expect(store.getState().grid!.baseEtag).toBe('base');
  session.destroy();
});
it('ports late-join lines 46, 47, 48: refusing manual draft ownership sends nothing and does not create a competing grid draft', async () => {
  const { store, session, config } = setup();
  editArrangement(store, { type: 'edit', layout: { ...config.layout, width: 999 } });
  const transport = vi.fn();
  const result = await previewGrid(store, transport);
  expect(result.kind === 'rejected' && result.message).toMatch(/manual draft/);
  expect(store.getState().grid!.dirty).toBe(false);
  expect(transport).not.toHaveBeenCalled(); session.destroy();
});
it('Keep mine reruns a grid preview with a fresh guard; late previews stay stale and newer edits survive', async () => {
  const { store, session, command, preview } = setup();
  editGrid(store, { type: 'edit', command, etag: etag('base') });
  session.ingest(configFixture('remote'));
  const transport = vi.fn(async (_command, guard) => ({ kind: 'ok' as const, value: { ...preview, base_etag: guard } }));
  await rebuildGrid(store, transport);
  expect(transport).toHaveBeenCalledWith(command, etag('remote'));
  expect(store.getState().grid).toMatchObject({ stale: false, baseEtag: 'remote' });
  const oldVersion = store.getState().grid!.version;
  editGrid(store, { type: 'edit', command: { ...command, padding: 3 }, etag: etag('remote') });
  editGrid(store, { type: 'preview', preview, version: oldVersion, etag: etag('remote') });
  expect(store.getState().grid!.preview).toBeNull();
  editGrid(store, { type: 'preview', preview, version: store.getState().grid!.version, etag: etag('remote') });
  expect(store.getState().grid!.stale).toBe(true);
  session.destroy();
});
