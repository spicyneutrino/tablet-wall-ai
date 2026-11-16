import { expect, it, vi } from 'vitest';
import { paths } from '../../api/paths';
import { SceneSchema } from '../../api/scene';
import { configFixture } from '../../session/testFixtures';
import { createSession } from '../../session/session';
import { createWallStore } from '../store';
import {
  SAVED_IMAGE_GONE, deleteSavedContent, loadSavedContent, previewSavedContent, recallSavedContent,
  savedContentOutcomeMessage, saveCurrentContent,
} from './savedScenes';
import type { SavedContent } from './savedScenes';
import { SNAPSHOT_NAME_RULE } from './savedLayouts';

const asset = `sha256:${'a'.repeat(64)}` as const;
const image = SceneSchema.parse({ type: 'image', asset, fit: 'cover', background: '#0b1120',
  intrinsicWidth: 1600, intrinsicHeight: 900 });
const savedImage: SavedContent = { name: 'Lobby', etag: 'saved-digest', valid: true, content: image };
const savedPattern: SavedContent = { name: 'Calibration', etag: 'pattern-digest', valid: true,
  content: { type: 'calibration' } };

function setup() {
  const store = createWallStore();
  const transport = vi.fn<typeof fetch>();
  const session = createSession({ store, fetch: transport, isDirty: () => false });
  session.ingest(configFixture('base'));
  return { store, session, transport };
}

function respond(transport: ReturnType<typeof setup>['transport'], body: unknown, status = 200) {
  transport.mockResolvedValueOnce(new Response(JSON.stringify(body), { status,
    headers: { 'Content-Type': 'application/json' } }));
}

function sent(transport: ReturnType<typeof setup>['transport'], index = 0) {
  const call = transport.mock.calls[index];
  if (!call) throw new Error(`missing request ${index}`);
  return { path: call[0], method: call[1]?.method, headers: call[1]?.headers as Record<string, string>,
    body: call[1]?.body };
}

it('lists saved content sorted by name and keeps a damaged entry', async () => {
  const { session, transport } = setup();
  respond(transport, { scenes: [
    { name: 'Zebra', etag: 'z', kind: 'scene', valid: true, content: { type: 'calibration' } },
    { name: 'Broken', etag: 'b', kind: 'scene', valid: false, content: null },
    { name: 'Lobby', etag: 'l', kind: 'scene', valid: true, content: image },
  ] });
  const outcome = await loadSavedContent(session);
  expect(outcome.kind).toBe('ok');
  if (outcome.kind !== 'ok') return;
  expect(outcome.value.map(entry => [entry.name, entry.valid])).toEqual([
    ['Broken', false], ['Lobby', true], ['Zebra', true],
  ]);
  expect(outcome.value[1]).toMatchObject({ valid: true, content: image });
});

it('fills the content draft from a saved scene with no request', () => {
  const { store, transport } = setup();
  store.setState(state => ({ ui: { ...state.ui, testPattern: 'grid' } }));
  const imageInfo = { url: '/media/lobby.png', name: 'lobby.png', width: 1600, height: 900 };
  expect(previewSavedContent(store, savedImage, imageInfo)).toBe(true);
  expect(transport).not.toHaveBeenCalled();
  expect(store.getState().ui.testPattern).toBeNull();
  expect(store.getState().content).toMatchObject({
    selection: { type: 'image', asset, fit: 'cover', background: '#0b1120', url: '/media/lobby.png',
      name: 'lobby.png', intrinsicWidth: 1600, intrinsicHeight: 900, available: true },
    savedScene: { name: 'Lobby', etag: 'saved-digest' },
    baseEtag: 'base', conflict: false,
  });
  const damaged: SavedContent = { name: 'Broken', etag: 'b', valid: false };
  expect(previewSavedContent(store, damaged)).toBe(false);
});

it('previews a deleted image as unavailable and a pattern without image fields', () => {
  const { store } = setup();
  expect(previewSavedContent(store, savedImage, null)).toBe(true);
  expect(store.getState().content.selection).toMatchObject({ available: false });
  expect(previewSavedContent(store, savedPattern)).toBe(true);
  expect(store.getState().content.selection).toEqual({ type: 'calibration' });
});

it('rejects an invalid name with the ported rule before any request', async () => {
  const { store, session, transport } = setup();
  for (const name of ['', '  ', '-leading', 'x'.repeat(65)]) {
    const outcome = await saveCurrentContent(store, session, name);
    expect(outcome.kind).toBe('rejected');
    if (outcome.kind === 'rejected') expect(outcome.message).toContain(SNAPSHOT_NAME_RULE);
  }
  expect(await saveCurrentContent(store, session, ' ')).toEqual({ kind: 'rejected', status: 422,
    message: `Enter a content name. ${SNAPSHOT_NAME_RULE}` });
  expect(transport).not.toHaveBeenCalled();
});

it('saves, replaces and deletes with the current ETag and no body', async () => {
  const { store, session, transport } = setup();
  respond(transport, configFixture('saved'));
  expect((await saveCurrentContent(store, session, '  Lobby  ')).kind).toBe('ok');
  expect(sent(transport)).toMatchObject({ path: '/api/v3/scenes/Lobby', method: 'PUT',
    headers: { 'If-Match': 'base' } });
  expect(sent(transport).body).toBeUndefined();

  respond(transport, configFixture('replaced'));
  expect((await saveCurrentContent(store, session, 'Lobby', true)).kind).toBe('ok');
  expect(sent(transport, 1)).toMatchObject({ path: '/api/v3/scenes/Lobby?replace=true', method: 'PUT',
    headers: { 'If-Match': 'saved' } });

  respond(transport, configFixture('deleted'));
  expect((await deleteSavedContent(store, session, savedImage)).kind).toBe('ok');
  expect(sent(transport, 2)).toMatchObject({ path: '/api/v3/scenes/Lobby', method: 'DELETE',
    headers: { 'If-Match': 'replaced' } });
});

it('recalls a saved scene with the draft guard, then clears the preview', async () => {
  const { store, session, transport } = setup();
  expect(previewSavedContent(store, savedImage, null)).toBe(true);
  const version = store.getState().content.version;
  respond(transport, configFixture('next'));
  const outcome = await recallSavedContent(store, session, savedImage);
  expect(outcome.kind).toBe('ok');
  expect(sent(transport)).toMatchObject({ path: '/api/v3/scenes/Lobby/recall', method: 'POST',
    headers: { 'If-Match': 'base' } });
  expect(sent(transport).body).toBeUndefined();
  expect(store.getState().content.selection).toBeNull();
  expect(store.getState().content.version).toBe(version + 1);
});

it('keeps the preview when recall answers 422 because the image is gone', async () => {
  const { store, session, transport } = setup();
  expect(previewSavedContent(store, savedImage, null)).toBe(true);
  respond(transport, { detail: 'Unknown asset' }, 422);
  const outcome = await recallSavedContent(store, session, savedImage);
  expect(outcome.kind).toBe('rejected');
  if (outcome.kind === 'rejected') expect(outcome.message).toBe(SAVED_IMAGE_GONE);
  expect(store.getState().content.selection).toMatchObject({ type: 'image', asset });
  expect(savedContentOutcomeMessage(outcome)).toBe(SAVED_IMAGE_GONE);
  respond(transport, { detail: 'Saved scene is invalid' }, 422);
  const damaged = await recallSavedContent(store, session, savedImage);
  expect(damaged.kind === 'rejected' && damaged.message).toBe('Saved scene is invalid');
});

it('names an unavailable wall and a damaged entry without sending anything', async () => {
  const store = createWallStore();
  const transport = vi.fn<typeof fetch>();
  const session = createSession({ store, fetch: transport, isDirty: () => false });
  const missing = await saveCurrentContent(store, session, 'Lobby');
  expect(missing).toEqual({ kind: 'rejected', status: 409, message: 'The wall is not ready yet.' });
  const damaged: SavedContent = { name: 'Broken', etag: 'b', valid: false };
  expect(await recallSavedContent(store, session, damaged)).toEqual({ kind: 'rejected', status: 422,
    message: 'This saved content is damaged. Delete it and save the wall again.' });
  expect(transport).not.toHaveBeenCalled();
});

it('maps every non-success outcome to plain guidance', () => {
  expect(savedContentOutcomeMessage({ kind: 'ok', value: null })).toBe('');
  expect(savedContentOutcomeMessage({ kind: 'conflict' })).toMatch(/wall changed/i);
  expect(savedContentOutcomeMessage({ kind: 'uncertain', message: 'Timed out.' })).toMatch(/Not confirmed.*Timed out/);
  expect(savedContentOutcomeMessage({ kind: 'rejected', status: 409, message: 'Name exists' })).toBe('Name exists');
  expect(savedContentOutcomeMessage({ kind: 'refused-locally', reason: 'busy' })).toMatch(/already being sent/);
  expect(savedContentOutcomeMessage({ kind: 'refused-locally', reason: 'stale-etag' })).toMatch(/Refresh status/);
});

it('reports a stale read instead of a partial list', async () => {
  const { session, transport } = setup();
  respond(transport, { detail: 'stale' }, 409);
  expect(await loadSavedContent(session)).toEqual({ kind: 'rejected', status: 409, message: 'stale' });
  expect(paths.scenes).toBe('/api/v3/scenes');
});
