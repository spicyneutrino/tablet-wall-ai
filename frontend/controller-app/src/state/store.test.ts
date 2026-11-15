import { afterEach, expect, it, vi } from 'vitest';
import { ConfigSchema } from '../api/config';
import { ConfigEtagSchema } from '../api/etag';
import { A, B, configFixture, renderFixture } from '../session/testFixtures';
import { createSession } from '../session/session';
import { createWallStore, editArrangement, editContent, editForm, keepMine, observeForm, selectDevice, startClock, useTheirs } from './store';
import { formKey } from './drafts/tabletForms';
import { selectOnWallLayout, selectPreviewLayout } from './hooks';

const etag = ConfigEtagSchema.parse;
function setup() {
  const store = createWallStore(0);
  const session = createSession({ store, now: () => 0, isDirty: () => false });
  session.ingest(configFixture('base'));
  return { store, session };
}
afterEach(() => vi.useRealTimers());
it('a remote adoption keeps a dirty arrangement and sets conflict; On wall follows server truth', () => {
  const { store, session } = setup();
  editArrangement(store, { type: 'edit', layout: { ...configFixture('base').layout, width: 200 } });
  const before = store.getState().arrangement!;
  session.ingest({ ...configFixture('remote'), layout: { ...configFixture('remote').layout, width: 300 } });
  const state = store.getState();
  expect(state.arrangement).toMatchObject({ base: before.base, draft: before.draft, baseEtag: 'base', conflict: true });
  expect(selectPreviewLayout(state)).toBe(before.draft);
  expect(selectOnWallLayout(state)).toBe(state.server.config!.layout);
  expect(keepMine(store, { kind: 'arrangement' }, { version: before.version - 1, etag: etag('remote') })).toBe(false);
  expect(keepMine(store, { kind: 'arrangement' }, { version: before.version, etag: etag('obsolete') })).toBe(false);
  expect(keepMine(store, { kind: 'arrangement' }, { version: before.version, etag: etag('remote') })).toBe(true);
  expect(store.getState().arrangement).toMatchObject({ draft: before.draft, baseEtag: 'remote', conflict: false });
  useTheirs(store, { kind: 'arrangement' });
  expect(store.getState().arrangement).toMatchObject({ base: state.server.config!.layout, draft: state.server.config!.layout, undo: [], redo: [] });
  session.destroy();
});
it('a clean arrangement adopts the new layout', () => {
  const { store, session } = setup();
  session.ingest({ ...configFixture('next'), layout: { ...configFixture('next').layout, width: 500 } });
  expect(store.getState().arrangement).toMatchObject({ baseEtag: 'next', draft: { width: 500 }, conflict: false });
  session.destroy();
});
it('a clean form adopts the new baseline; a dirty form keeps its values and guard', () => {
  const { store, session } = setup();
  observeForm(store, A, 'name'); observeForm(store, B, 'name');
  editForm(store, formKey(B, 'name'), { name: 'My B' });
  session.ingest({ ...configFixture('remote'), device_labels: { [A]: 'Server A', [B]: 'Server B' } });
  expect(store.getState().forms[formKey(A, 'name')]).toMatchObject({ values: { name: 'Server A' }, baseline: { name: 'Server A' }, baseEtag: 'remote', dirty: false });
  expect(store.getState().forms[formKey(B, 'name')]).toMatchObject({ values: { name: 'My B' }, baseline: { name: '' }, baseEtag: 'base', conflict: true });
  const review = { version: store.getState().forms[formKey(B, 'name')]!.version, etag: etag('remote') };
  expect(keepMine(store, { kind: 'form', key: formKey(B, 'name') }, review)).toBe(true);
  expect(store.getState().forms[formKey(B, 'name')]).toMatchObject({ values: { name: 'My B' }, baseline: { name: 'Server B' }, baseEtag: 'remote', conflict: false });
  useTheirs(store, { kind: 'form', key: formKey(B, 'name') });
  expect(store.getState().forms[formKey(B, 'name')]).toMatchObject({ values: { name: 'Server B' }, dirty: false });
  session.destroy();
});
it('switching ui.selected between two devices keeps both devices’ form drafts', () => {
  const { store, session } = setup();
  selectDevice(store, A); observeForm(store, A, 'name'); editForm(store, formKey(A, 'name'), { name: 'My A' });
  selectDevice(store, B); observeForm(store, B, 'name'); editForm(store, formKey(B, 'name'), { name: 'My B' });
  selectDevice(store, A);
  expect(store.getState().forms[formKey(A, 'name')]!.values.name).toBe('My A');
  expect(store.getState().forms[formKey(B, 'name')]!.values.name).toBe('My B');
  session.destroy();
});
it('a saved-scene preview is dropped on conflict, not rebased; ordinary selections retain their guard', () => {
  const { store, session } = setup();
  editContent(store, { type: 'select', selection: { type: 'color' }, etag: etag('base'), savedScene: { name: 'Lobby', etag: etag('base') } });
  session.ingest(configFixture('remote'));
  expect(store.getState().content).toMatchObject({ selection: null, savedScene: null, baseEtag: null });
  editContent(store, { type: 'select', selection: { type: 'calibration' }, etag: etag('remote') });
  session.ingest(configFixture('next'));
  expect(store.getState().content).toMatchObject({ selection: { type: 'calibration' }, baseEtag: 'remote', conflict: true });
  session.destroy();
});
it('the tick does not change the store when no status changes, and expires current paint at 15 seconds', () => {
  vi.useFakeTimers();
  const { store, session } = setup();
  const token = { connection_id: 'c', generation: 'session', revision: 1, render_seq: 1, mapping_revision: 'm', asset: null };
  const config = configFixture('paint');
  config.layout = ConfigSchema.parse({ ...config, layout: { ...config.layout, placements: { [A]: { x: 0, y: 0, w: 50, h: 50, bezel: { top: 0, right: 0, bottom: 0, left: 0 } } } } }).layout;
  config.runtime.devices[A] = { ...config.runtime.devices[A]!, connection_id: 'c',
    mapping: { state: 'ready', revision: 'm', reason: null, viewport: null },
    render: renderFixture('displayed', { current: true, expected_token: token, accepted_token: token, age_ms: 0 }) };
  session.ingest(config);
  const started = Date.now();
  const stop = startClock(store, { now: () => Date.now() - started });
  const before = store.getState(), listener = vi.fn();
  const unsubscribe = store.subscribe(listener);
  vi.advanceTimersByTime(14000);
  expect(store.getState()).toBe(before);
  expect(listener).not.toHaveBeenCalled();
  vi.advanceTimersByTime(1000);
  expect(store.getState().clock.nowMono).toBe(15000);
  expect(listener).toHaveBeenCalledTimes(1);
  const expired = store.getState(); vi.advanceTimersByTime(5000);
  expect(store.getState()).toBe(expired);
  stop(); unsubscribe(); session.destroy(); expect(vi.getTimerCount()).toBe(0);
});
