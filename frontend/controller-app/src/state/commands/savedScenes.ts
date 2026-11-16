import { ConfigSchema } from '../../api/config';
import type { Config } from '../../api/config';
import { ConfigEtagSchema } from '../../api/etag';
import { paths } from '../../api/paths';
import { SavedScenesSchema } from '../../api/saved';
import type { SavedScene } from '../../api/saved';
import type { Scene } from '../../api/scene';
import { snapshotName } from '../../domain/names';
import type { CommandOutcome } from '../../session/outcome';
import type { Session } from '../../session/session';
import { contentReducer } from '../drafts/content';
import type { WallStoreApi } from '../store';
import { SNAPSHOT_NAME_RULE } from './savedLayouts';
import { run } from './run';

export const SAVED_IMAGE_GONE = 'The image for this saved content was deleted.';

export type SavedContent = { name: string; etag: string; valid: false }
  | { name: string; etag: string; valid: true; content: Scene };
export type SavedImage = { url: string; name: string; width: number; height: number };

function toSaved(entry: SavedScene): SavedContent {
  return entry.valid
    ? { name: entry.name, etag: entry.etag, valid: true, content: entry.content }
    : { name: entry.name, etag: entry.etag, valid: false };
}

export async function loadSavedContent(session: Session): Promise<CommandOutcome<SavedContent[]>> {
  const outcome = await session.request('GET', paths.scenes, undefined,
    { fenced: 'durable', parse: SavedScenesSchema });
  if (outcome.kind !== 'ok') return outcome;
  return { kind: 'ok', value: outcome.value.scenes.map(toSaved)
    .sort((left, right) => left.name.localeCompare(right.name)) };
}

/** Fill the content draft from a saved scene. No request is sent. */
export function previewSavedContent(store: WallStoreApi, saved: SavedContent, image?: SavedImage | null): boolean {
  if (!saved.valid) return false;
  const state = store.getState();
  const etag = state.server.etag;
  if (!etag) return false;
  const stored = saved.content;
  const selection = stored.type === 'image'
    ? { type: 'image' as const, asset: stored.asset, fit: stored.fit, background: stored.background,
      ...(image ? { url: image.url, name: image.name, intrinsicWidth: image.width, intrinsicHeight: image.height,
        available: true } : { available: false }) }
    : { type: stored.type };
  const base = { ...state.content, selection: null, baseEtag: null };
  store.setState(state => ({ ui: { ...state.ui, testPattern: null },
    content: contentReducer(base, { type: 'select', selection, etag,
      savedScene: { name: saved.name, etag: ConfigEtagSchema.parse(saved.etag) } }) }));
  return true;
}

export async function recallSavedContent(store: WallStoreApi, session: Session,
  saved: SavedContent): Promise<CommandOutcome<Config>> {
  if (!saved.valid) return { kind: 'rejected', status: 422,
    message: 'This saved content is damaged. Delete it and save the wall again.' };
  const outcome = await run(store, { kind: 'content' }, guard => session.request('POST',
    paths.recallScene(saved.name), undefined, { ifMatch: guard ?? undefined, parse: ConfigSchema }));
  return outcome.kind === 'rejected' && outcome.status === 422 && /unknown asset/i.test(outcome.message)
    ? { ...outcome, message: SAVED_IMAGE_GONE } : outcome;
}

export async function saveCurrentContent(store: WallStoreApi, session: Session, rawName: string,
  replace = false): Promise<CommandOutcome<Config>> {
  const name = snapshotName(rawName);
  if (name === null) return { kind: 'rejected', status: 422,
    message: rawName.trim() ? SNAPSHOT_NAME_RULE : `Enter a content name. ${SNAPSHOT_NAME_RULE}` };
  if (!store.getState().server.config) return { kind: 'rejected', status: 409, message: 'The wall is not ready yet.' };
  return session.request('PUT', paths.savedScene(name, replace), undefined,
    { useCurrentEtag: true, parse: ConfigSchema });
}

export async function deleteSavedContent(store: WallStoreApi, session: Session,
  saved: SavedContent): Promise<CommandOutcome<Config>> {
  if (!store.getState().server.config) return { kind: 'rejected', status: 409, message: 'The wall is not ready yet.' };
  return session.request('DELETE', paths.savedScene(saved.name), undefined,
    { useCurrentEtag: true, parse: ConfigSchema });
}

export function savedContentOutcomeMessage(outcome: CommandOutcome<unknown>): string {
  switch (outcome.kind) {
    case 'ok': return '';
    case 'conflict': return 'The wall changed. Refresh Saved and review it again.';
    case 'precondition-missing': return 'Refresh status, then try again.';
    case 'rejected': return outcome.message;
    case 'uncertain': return `Not confirmed. ${outcome.message}`;
    case 'refused-locally':
      return outcome.reason === 'busy' ? 'Another change is already being sent. Wait for it to finish.'
        : outcome.reason === 'uncertain' ? 'The last change was not confirmed. Refresh status first.'
          : outcome.reason === 'unsupported' ? 'Update the console before editing.'
            : 'The wall may have changed. Refresh status first.';
  }
}
