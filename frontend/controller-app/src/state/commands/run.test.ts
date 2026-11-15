import { expect, it, vi } from 'vitest';
import { ConfigSchema } from '../../api/config';
import { ConfigEtagSchema, PlaylistEtagSchema } from '../../api/etag';
import { A, B, configFixture } from '../../session/testFixtures';
import { createSession } from '../../session/session';
import type { CommandOutcome } from '../../session/outcome';
import { createWallStore, editArrangement, editContent, editForm, editPlaylist, observeForm, selectDevice } from '../store';
import { formKey } from '../drafts/tabletForms';
import { PlaylistSchema } from '../../api/playback';
import { run } from './run';

function deferred<T>() {
  let resolve!: (value: T) => void;
  return { promise: new Promise<T>(done => { resolve = done; }), resolve: (value: T) => resolve(value) };
}
function setup() {
  const store = createWallStore();
  const session = createSession({ store, isDirty: () => false }); session.ingest(configFixture('base'));
  editContent(store, { type: 'select', selection: { type: 'calibration' }, etag: ConfigEtagSchema.parse('base') });
  return { store, session };
}
it.each<CommandOutcome<unknown>>([
  { kind: 'conflict' }, { kind: 'precondition-missing' }, { kind: 'rejected', status: 422, message: 'invalid' },
  { kind: 'uncertain', message: 'not confirmed' },
  { kind: 'refused-locally', reason: 'busy' }, { kind: 'refused-locally', reason: 'uncertain' },
  { kind: 'refused-locally', reason: 'unsupported' }, { kind: 'refused-locally', reason: 'stale-etag' },
])('maps $kind without clearing the submitted draft or retrying', async outcome => {
  const { store, session } = setup(), before = store.getState().content;
  const execute = vi.fn(async () => outcome);
  expect(await run(store, { kind: 'content' }, execute)).toEqual(outcome);
  expect(execute).toHaveBeenCalledExactlyOnceWith('base');
  expect(store.getState().content).toEqual({ ...before, conflict: outcome.kind === 'conflict' });
  session.destroy();
});
it('uses the submitted draft guard, and a late content success cannot clear newer input', async () => {
  const { store, session } = setup();
  session.ingest(configFixture('remote'));
  const pending = deferred<CommandOutcome<unknown>>(), execute = vi.fn(() => pending.promise);
  const promise = run(store, { kind: 'content' }, execute);
  editContent(store, { type: 'select', selection: { type: 'color' }, etag: ConfigEtagSchema.parse('remote') });
  session.ingest(configFixture('saved'));
  pending.resolve({ kind: 'ok', value: configFixture('saved') }); await promise;
  expect(execute).toHaveBeenCalledExactlyOnceWith('base');
  expect(store.getState().content.selection).toEqual({ type: 'color' });
  session.destroy();
});
it('an unchanged content success clears the selection after Session has adopted the result', async () => {
  const { store, session } = setup();
  await run(store, { kind: 'content' }, async () => { session.ingest(configFixture('saved')); return { kind: 'ok', value: configFixture('saved') }; });
  expect(store.getState().content.selection).toBeNull(); session.destroy();
});
it('a raced commandEtag never clears a draft against newer remote authority', async () => {
  const { store, session } = setup();
  await run(store, { kind: 'content' }, async () => {
    session.ingest(configFixture('remote')); return { kind: 'ok', value: configFixture('remote'), commandEtag: ConfigEtagSchema.parse('own-command') };
  });
  expect(store.getState().content).toMatchObject({ selection: { type: 'calibration' }, baseEtag: 'base', conflict: true });
  session.destroy();
});
it('an arrangement success retains edits made while the command was pending', async () => {
  const { store, session } = setup();
  const config = configFixture('base');
  editArrangement(store, { type: 'edit', layout: { ...config.layout, width: 200 } });
  const pending = deferred<CommandOutcome<unknown>>();
  const saving = run(store, { kind: 'arrangement' }, () => pending.promise);
  editArrangement(store, { type: 'edit', layout: { ...config.layout, width: 300 } });
  const saved = ConfigSchema.parse({ ...configFixture('saved'), layout: { ...config.layout, width: 200 } });
  session.ingest(saved); pending.resolve({ kind: 'ok', value: saved }); await saving;
  expect(store.getState().arrangement).toMatchObject({ base: { width: 200 }, draft: { width: 300 }, conflict: false, baseEtag: 'saved' });
  session.destroy();
});
it('late A saves cannot clear newer A input or change selected B; form receipts retain their own ETag', async () => {
  const { store, session } = setup();
  observeForm(store, A, 'name'); observeForm(store, B, 'name');
  editForm(store, formKey(A, 'name'), { name: 'Sent A' });
  const pending = deferred<CommandOutcome<unknown>>();
  const saving = run(store, { kind: 'form', key: formKey(A, 'name') }, () => pending.promise);
  editForm(store, formKey(A, 'name'), { name: 'New A' });
  selectDevice(store, B); editForm(store, formKey(B, 'name'), { name: 'Keep B' });
  pending.resolve({ kind: 'ok', value: { etag: 'receipt' } }); await saving;
  expect(store.getState().forms[formKey(A, 'name')]).toMatchObject({ baseline: { name: 'Sent A' }, values: { name: 'New A' }, dirty: true, baseEtag: 'receipt' });
  expect(store.getState().forms[formKey(B, 'name')]!.values.name).toBe('Keep B');
  expect(store.getState().ui.selected).toBe(B); session.destroy();
});
it('a real session 412 retains the keyed form; only a reviewed current ETag can be used next', async () => {
  const store = createWallStore();
  const transport = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ detail: 'stale' }), { status: 412 }));
  const session = createSession({ store, fetch: transport, isDirty: () => false }); session.ingest(configFixture('base'));
  observeForm(store, A, 'name'); editForm(store, formKey(A, 'name'), { name: 'Mine' });
  await run(store, { kind: 'form', key: formKey(A, 'name') }, guard => session.request('PATCH', `/api/v3/devices/${A}`,
    { label: 'Mine' }, { ifMatch: guard ?? undefined, parse: ConfigSchema }));
  expect(store.getState().forms[formKey(A, 'name')]).toMatchObject({ values: { name: 'Mine' }, conflict: true, baseEtag: 'base' });
  expect(transport.mock.calls[0]?.[1]?.headers).toMatchObject({ 'If-Match': 'base' }); session.destroy();
});
it('playlist commits use their separate token and preserve newer playlist edits', async () => {
  const { store, session } = setup();
  const playlist = PlaylistSchema.parse({ items: [{ asset: 'sha256:' + 'a'.repeat(64), dwell_ms: 1000 }], loop: false });
  editPlaylist(store, { type: 'observe', value: playlist, etag: PlaylistEtagSchema.parse('playlist-base') });
  editPlaylist(store, { type: 'edit', value: { ...playlist, loop: true } });
  const pending = deferred<CommandOutcome<{ playlist: typeof playlist; etag: ReturnType<typeof PlaylistEtagSchema.parse> }>>();
  const execute = vi.fn(() => pending.promise);
  const saving = run(store, { kind: 'playlist' }, execute, value => value);
  expect(execute).toHaveBeenCalledExactlyOnceWith('playlist-base');
  editPlaylist(store, { type: 'edit', value: { ...playlist, loop: true, items: [...playlist.items, ...playlist.items] } });
  pending.resolve({ kind: 'ok', value: { playlist, etag: PlaylistEtagSchema.parse('playlist-only') } }); await saving;
  expect(store.getState().playlist).toMatchObject({ saved: playlist, draft: { loop: true }, etag: 'playlist-only', dirty: true });
  expect(store.getState().server.etag).toBe('base'); session.destroy();
});
