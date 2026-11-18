import { expect, it, vi } from 'vitest';
import { PlaylistEtagSchema } from '../../api/etag';
import { paths } from '../../api/paths';
import { PlaylistSchema } from '../../api/playback';
import { configFixture } from '../../session/testFixtures';
import { createSession } from '../../session/session';
import { createWallStore, editPlaylist } from '../store';
import {
  applyStatus, loadPlaylist, playbackOutcomeMessage, pollPlayback, savePlaylist, sendTransport, startPlayback,
} from './playback';
import active from '../../api/__fixtures__/playback.json';
import { PlaybackStatusSchema } from '../../api/playback';

const asset = `sha256:${'a'.repeat(64)}` as const;
const playlist = PlaylistSchema.parse({ items: [{ asset, dwell_ms: 5000 }], loop: false, revision: 3 });
const etag = PlaylistEtagSchema.parse('p1');
const status = (version: number) => ({ ...active, version, state: 'playing' });

function setup() {
  const store = createWallStore();
  const transport = vi.fn<typeof fetch>();
  const session = createSession({ store, fetch: transport, isDirty: () => false });
  session.ingest(configFixture('base'));
  return { store, session, transport };
}
type Transport = ReturnType<typeof setup>['transport'];
const respond = (transport: Transport, body: unknown, status = 200) => transport.mockResolvedValueOnce(
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));
const request = (transport: Transport, index: number) => {
  const call = transport.mock.calls[index];
  if (!call) throw new Error(`missing request ${index}`);
  return { path: call[0], method: call[1]?.method, ifMatch: (call[1]?.headers as Record<string, string>)['If-Match'],
    body: call[1]?.body };
};

it('reads the version just before every write and retries one stale version once', async () => {
  const { store, session, transport } = setup();
  respond(transport, status(1));
  respond(transport, { detail: 'playback version is stale' }, 412);
  respond(transport, status(2));
  respond(transport, status(3));
  const outcome = await sendTransport(store, session, 'pause');
  expect(outcome.kind).toBe('ok');
  expect(transport.mock.calls.map((_, index) => request(transport, index)).map(({ method, path, ifMatch }) => [method, path, ifMatch])).toEqual([
    ['GET', paths.playback, undefined], ['POST', paths.playbackCommand('pause'), '1'],
    ['GET', paths.playback, undefined], ['POST', paths.playbackCommand('pause'), '2'],
  ]);
  expect(store.getState().playback).toMatchObject({ version: '3', status: { version: '3' } });
});

it('stops after one retry when the version keeps changing', async () => {
  const { store, session, transport } = setup();
  for (const version of [1, 2]) {
    respond(transport, status(version));
    respond(transport, { detail: 'playback version is stale' }, 412);
  }
  const outcome = await sendTransport(store, session, 'stop');
  expect(outcome.kind).toBe('conflict');
  expect(transport.mock.calls.filter((_, index) => request(transport, index).method === 'POST')).toHaveLength(2);
  expect(playbackOutcomeMessage(outcome)).toBe('Playback changed again while this was sent. Try once more.');
});

it('sends Resume as a Start of the paused session with the version', async () => {
  const { store, session, transport } = setup();
  respond(transport, { ...status(4), state: 'paused' });
  respond(transport, status(5));
  expect((await sendTransport(store, session, 'resume')).kind).toBe('ok');
  expect(request(transport, 1)).toMatchObject({ method: 'POST', path: paths.playbackCommand('start'), ifMatch: '4', body: undefined });
});

it('says to start playback when no session exists, without writing', async () => {
  const { store, session, transport } = setup();
  respond(transport, { state: 'stopped' });
  const outcome = await sendTransport(store, session, 'next');
  expect(outcome).toMatchObject({ kind: 'rejected', status: 409, message: 'Playback is not running. Start it first.' });
  expect(transport).toHaveBeenCalledOnce();
});

it('turns the server refusals into plain words', () => {
  for (const [detail, text] of [
    ['no eligible physical endpoints', 'No wall tablets are online. Open the tablet address on a tablet on the same network, then start again.'],
    ['save a playlist first', 'Save a playlist before starting playback.'],
    ['a physical layout is required', 'Apply a physical layout before starting playback.'],
    ['all participating slots are excluded', 'Every participating tablet is excluded. Include at least one tablet, then start again.'],
    ['playback is already active', 'playback is already active'],
  ] as const) expect(playbackOutcomeMessage({ kind: 'rejected', status: 409, message: detail })).toBe(text);
});

it('starts with the policy and exclusions and no If-Match', async () => {
  const { store, session, transport } = setup();
  respond(transport, status(1));
  const exclusions = ['00000000-0000-4000-8000-000000000002' as never];
  await startPlayback(store, session, { policy: 'strict', exclusions });
  expect(request(transport, 0)).toMatchObject({ method: 'POST', path: paths.playbackCommand('start'), ifMatch: undefined });
  expect(JSON.parse(String(request(transport, 0).body))).toEqual({ exclusions, policy: 'strict' });
  respond(transport, status(2));
  await startPlayback(store, session, { policy: null, exclusions: [] });
  expect(JSON.parse(String(request(transport, 1).body))).toEqual({ exclusions: [] });
});

it('drops a slow poll that a newer command response overtook', async () => {
  const { store, session, transport } = setup();
  let release = () => {};
  transport.mockImplementationOnce(() => new Promise(resolve => {
    release = () => resolve(new Response(JSON.stringify(status(1)), { status: 200, headers: { 'Content-Type': 'application/json' } }));
  }));
  const polling = pollPlayback(store, session);
  applyStatus(store, PlaybackStatusSchema.parse({ state: 'stopped' }));
  release();
  await polling;
  expect(store.getState().playback).toMatchObject({ status: { state: 'stopped' }, version: null });
});

it('saves the playlist with the playlist etag and a body without the revision', async () => {
  const { store, session, transport } = setup();
  editPlaylist(store, { type: 'observe', value: playlist, etag });
  editPlaylist(store, { type: 'edit', value: { ...playlist, loop: true } });
  respond(transport, { playlist: { items: playlist.items, loop: true, revision: 4 }, etag: 'p2' });
  expect((await savePlaylist(store, session)).kind).toBe('ok');
  expect(request(transport, 0)).toMatchObject({ method: 'PUT', path: paths.playlist, ifMatch: 'p1' });
  expect(JSON.parse(String(request(transport, 0).body))).toEqual({ items: [{ asset, dwell_ms: 5000 }], loop: true });
  expect(store.getState().playlist).toMatchObject({ etag: 'p2', dirty: false, draft: { loop: true, revision: 4 } });
});

it('keeps the edits and marks a conflict when the playlist etag is stale', async () => {
  const { store, session, transport } = setup();
  editPlaylist(store, { type: 'observe', value: playlist, etag });
  editPlaylist(store, { type: 'edit', value: { ...playlist, loop: true } });
  respond(transport, { detail: 'playlist changed; reload' }, 412);
  expect((await savePlaylist(store, session)).kind).toBe('conflict');
  expect(store.getState().playlist).toMatchObject({ conflict: true, dirty: true, draft: { loop: true } });
  respond(transport, { playlist, etag: 'p9' });
  await loadPlaylist(store, session, 'keep');
  expect(store.getState().playlist).toMatchObject({ conflict: false, dirty: true, etag: 'p9', draft: { loop: true } });
});

it('refuses to save locally without an etag or an item, sending nothing', async () => {
  const { store, session, transport } = setup();
  editPlaylist(store, { type: 'edit', value: playlist });
  expect(await savePlaylist(store, session)).toEqual({ kind: 'refused-locally', reason: 'stale-etag' });
  editPlaylist(store, { type: 'edit', value: { ...playlist, items: [] } });
  expect(await savePlaylist(store, session)).toMatchObject({ kind: 'rejected', message: 'Add at least one image before saving.' });
  expect(transport).not.toHaveBeenCalled();
});
