import { expect, it, vi } from 'vitest';
import { ConfigSchema } from '../../api/config';
import { LayoutSchema } from '../../api/layouts';
import type { Layout } from '../../api/layouts';
import { paths } from '../../api/paths';
import logicalListing from '../../api/__fixtures__/saved-logical-layouts.json';
import physicalListing from '../../api/__fixtures__/saved-physical-layouts.json';
import { configFixture } from '../../session/testFixtures';
import { createSession } from '../../session/session';
import { createWallStore } from '../store';
import {
  SNAPSHOT_NAME_RULE, applyArrangement, clearWall, deleteArrangement, isRestorePoint,
  loadSavedArrangements, needsKindConfirmation, outcomeMessage, previewArrangement, saveArrangement,
} from './savedLayouts';
import type { SavedArrangement } from './savedLayouts';

const physicalConfig = ConfigSchema.parse({ ...configFixture('physical'),
  layout: { kind: 'physical', bounds: { x: 0, y: 0, width: 340, height: 440 }, slots: {}, sizing: { mode: 'fixed', padding: 0 } } });

function setup(config = configFixture('base')) {
  const store = createWallStore();
  const transport = vi.fn<typeof fetch>();
  const session = createSession({ store, fetch: transport, isDirty: () => false });
  session.ingest(config);
  return { store, session, transport };
}

function respond(transport: ReturnType<typeof setup>['transport'], body: unknown) {
  transport.mockResolvedValueOnce(new Response(JSON.stringify(body), { status: 200,
    headers: { 'Content-Type': 'application/json' } }));
}

function stored(value: unknown): Layout {
  return LayoutSchema.parse(value);
}

function saved(layout: Layout, kind: 'logical' | 'physical', name = 'Studio'): SavedArrangement & { valid: true; layout: Layout } {
  return { name, etag: 'saved-etag', kind, valid: true, layout,
    count: Object.keys(layout.kind === 'physical' ? layout.slots : layout.placements).length };
}

function sent(transport: ReturnType<typeof setup>['transport'], index = 0) {
  const call = transport.mock.calls[index];
  if (!call) throw new Error(`missing request ${index}`);
  return { path: call[0], method: call[1]?.method, headers: call[1]?.headers as Record<string, string>,
    body: call[1]?.body };
}

it('merges both listings by name, tags each kind, sorts, lists a damaged entry once and prefers a valid one', async () => {
  const { session, transport } = setup();
  transport.mockImplementation(async path => new Response(JSON.stringify(path === paths.layouts
    ? { layouts: [...physicalListing.layouts, { name: 'Contract logical', etag: 'stale', kind: 'logical', valid: false, layout: null },
      { name: 'Broken', etag: 'broken', kind: 'logical', valid: false, layout: { width: 0 } }] }
    : { layouts: [...logicalListing.layouts, { name: 'Broken', etag: 'broken', kind: 'logical', valid: false, layout: { width: 0 } }] }),
  { status: 200, headers: { 'Content-Type': 'application/json' } }));
  const outcome = await loadSavedArrangements(session);
  expect(outcome.kind).toBe('ok');
  if (outcome.kind !== 'ok') return;
  expect(outcome.value.map(entry => [entry.name, entry.kind, entry.valid, entry.valid ? entry.count : null])).toEqual([
    ['Broken', outcome.value[0]!.kind, false, null],
    ['Contract logical', 'logical', true, 4],
    ['Contract physical', 'physical', true, 4],
  ]);
  expect(outcome.value.filter(entry => entry.name === 'Contract logical')).toHaveLength(1);
  expect(outcome.value.filter(entry => entry.name === 'Broken')).toHaveLength(1);
  expect(isRestorePoint('Before physical 0123456789ab')).toBe(true);
  expect(isRestorePoint('Before physical xyz')).toBe(false);
});

it('draws a stored layout in the draft with no request, even when its kind differs from the wall', () => {
  const { store, transport } = setup(physicalConfig);
  const logical = saved(stored({ ...logicalListing.layouts[0]!.layout, kind: 'logical' }), 'logical');
  expect(previewArrangement(store, logical)).toBe(true);
  expect(transport).not.toHaveBeenCalled();
  expect(store.getState().arrangement?.draft).toMatchObject({ kind: 'logical', width: 150, height: 200,
    sizing: { mode: 'tablets', padding: 0 } });
  expect(Object.keys(store.getState().arrangement?.draft.placements ?? {})).toHaveLength(4);
  expect(store.getState().arrangement?.base).toEqual(physicalConfig.layout);
  expect(needsKindConfirmation(store, logical)).toBe(true);
  const physical = saved(stored(physicalListing.layouts[0]!.layout), 'physical');
  expect(needsKindConfirmation(store, physical)).toBe(false);
  const damaged: SavedArrangement = { name: 'Broken', etag: 'x', kind: 'logical', valid: false };
  expect(previewArrangement(store, damaged)).toBe(false);
});

it('rejects a bad name with the ported rule before any request', async () => {
  const { store, session, transport } = setup();
  for (const name of ['', '  ', '-leading', 'x'.repeat(65)]) {
    const outcome = await saveArrangement(store, session, name);
    expect(outcome.kind).toBe('rejected');
    if (outcome.kind === 'rejected') expect(outcome.message).toContain(SNAPSHOT_NAME_RULE);
  }
  const blank = await saveArrangement(store, session, ' ');
  expect(blank).toEqual({ kind: 'rejected', status: 422, message: `Enter an arrangement name. ${SNAPSHOT_NAME_RULE}` });
  expect(transport).not.toHaveBeenCalled();
});

it('saves, replaces and deletes with the current ETag and the wall kind in the path', async () => {
  const { store, session, transport } = setup(physicalConfig);
  respond(transport, physicalConfig);
  expect((await saveArrangement(store, session, '  Studio  ')).kind).toBe('ok');
  expect(sent(transport)).toMatchObject({ path: '/api/v3/layouts/Studio', method: 'PUT', headers: { 'If-Match': 'physical' } });
  expect(sent(transport).body).toBeUndefined();

  respond(transport, physicalConfig);
  await saveArrangement(store, session, 'Studio', true);
  expect(sent(transport, 1)).toMatchObject({ path: '/api/v3/layouts/Studio?replace=true', method: 'PUT' });

  respond(transport, physicalConfig);
  const entry = saved(stored(physicalListing.layouts[0]!.layout), 'physical');
  await deleteArrangement(store, session, entry);
  expect(sent(transport, 2)).toMatchObject({ path: '/api/v3/layouts/Studio', method: 'DELETE',
    headers: { 'If-Match': 'physical' } });
});

it('recalls with a POST and the submitted guard, then adopts the recalled layout', async () => {
  const { store, session, transport } = setup(physicalConfig);
  const logical = saved(stored({ ...logicalListing.layouts[0]!.layout, kind: 'logical' }), 'logical');
  const recalled = ConfigSchema.parse({ ...configFixture('next'), layout: logical.layout });
  respond(transport, recalled);
  const outcome = await applyArrangement(store, session, logical);
  expect(outcome.kind).toBe('ok');
  expect(sent(transport)).toMatchObject({ path: '/api/v3/logical-layouts/Studio/recall', method: 'POST',
    headers: { 'If-Match': 'physical' } });
  expect(store.getState().arrangement).toMatchObject({ baseEtag: 'next', conflict: false });
  expect(store.getState().arrangement?.draft.kind).toBe('logical');
});

it('clears the wall with one confirmed POST', async () => {
  const { store, session, transport } = setup();
  respond(transport, configFixture('next'));
  expect((await clearWall(store, session)).kind).toBe('ok');
  expect(sent(transport)).toMatchObject({ path: paths.clearLayout, method: 'POST', headers: { 'If-Match': 'base' },
    body: JSON.stringify({ confirm: true }) });
});

it('maps every non-success outcome to plain guidance', () => {
  expect(outcomeMessage({ kind: 'ok', value: null })).toBe('');
  expect(outcomeMessage({ kind: 'conflict' })).toMatch(/wall changed/i);
  expect(outcomeMessage({ kind: 'uncertain', message: 'Timed out.' })).toMatch(/Not confirmed.*Timed out/);
  expect(outcomeMessage({ kind: 'rejected', status: 409, message: 'Name exists' })).toBe('Name exists');
  expect(outcomeMessage({ kind: 'refused-locally', reason: 'busy' })).toMatch(/already being sent/);
  expect(outcomeMessage({ kind: 'refused-locally', reason: 'stale-etag' })).toMatch(/Refresh status/);
});

it('reports a stale read instead of a partial list', async () => {
  const { session, transport } = setup();
  transport.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'stale' }), { status: 409 }));
  transport.mockResolvedValueOnce(new Response(JSON.stringify({ layouts: [] }), { status: 200 }));
  const outcome = await loadSavedArrangements(session);
  expect(outcome).toEqual({ kind: 'rejected', status: 409, message: 'stale' });
});
