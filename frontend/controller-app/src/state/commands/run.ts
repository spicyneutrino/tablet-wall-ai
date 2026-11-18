import { ConfigEtagSchema } from '../../api/etag';
import { isRecord } from '../../session/outcome';
import type { ConfigEtag, PlaylistEtag } from '../../api/etag';
import type { GridCommand, GridPreview } from '../../api/grid';
import type { PlaylistResponse } from '../../api/playback';
import type { CommandOutcome } from '../../session/outcome';
import type { DraftTarget, WallStoreApi } from '../store';
import { arrangementDirty, arrangementReducer } from '../drafts/arrangement';
import { contentReducer } from '../drafts/content';
import { gridReducer } from '../drafts/grid';
import { tabletFormReducer } from '../drafts/tabletForms';
import { playlistReducer } from '../drafts/playlist';

export type CommitTarget = DraftTarget | { kind: 'playlist' };
export type CommitResult<T> = CommandOutcome<T>;
export async function run<T>(store: WallStoreApi, target: CommitTarget,
  execute: (guard: ConfigEtag | PlaylistEtag | null) => Promise<CommitResult<T>>,
  playlistReceipt?: (value: T) => PlaylistResponse): Promise<CommitResult<T>> {
  const before = store.getState();
  const draft = target.kind === 'form' ? before.forms[target.key] : before[target.kind];
  if (!draft) return { kind: 'rejected', status: 409, message: 'This draft is no longer available.' };
  const version = draft.version;
  const guard = target.kind === 'playlist' ? before.playlist.etag : 'baseEtag' in draft ? draft.baseEtag ?? before.server.etag : before.server.etag;
  const outcome = await execute(guard);
  const state = store.getState();
  if (outcome.kind === 'conflict') {
    const current = target.kind === 'form' ? state.forms[target.key] : state[target.kind];
    const currentGuard = target.kind === 'playlist' ? state.playlist.etag : current && 'baseEtag' in current ? current.baseEtag : null;
    if (!current || currentGuard !== guard || target.kind === 'content' && !state.content.selection) return outcome;
    switch (target.kind) {
      case 'arrangement':
        if (state.arrangement) store.setState({ arrangement: { ...state.arrangement, conflict: true } });
        break;
      case 'content': store.setState({ content: state.content.savedScene
        ? contentReducer(state.content, { type: 'discard' }) : { ...state.content, conflict: true } }); break;
      case 'grid': if (state.grid) store.setState({ grid: { ...state.grid, stale: true } }); break;
      case 'playlist': store.setState({ playlist: { ...state.playlist, conflict: true } }); break;
      case 'form': {
        const form = state.forms[target.key];
        if (form) store.setState({ forms: { ...state.forms, [target.key]: { ...form, conflict: true } } });
      }
    }
    return outcome;
  }
  if (outcome.kind !== 'ok') return outcome;
  if (target.kind === 'playlist') {
    if (playlistReceipt) {
      const receipt = playlistReceipt(outcome.value);
      store.setState({ playlist: playlistReducer(state.playlist,
        { type: 'saved', value: receipt.playlist, etag: receipt.etag, version }) });
    }
    return outcome;
  }
  const etag = outcome.commandEtag ?? ConfigEtagSchema.safeParse(isRecord(outcome.value) ? outcome.value.etag : null).data;
  if (!etag || state.server.etag !== guard && state.server.etag !== etag) return outcome;
  switch (target.kind) {
    case 'arrangement':
      if (state.arrangement && state.server.config) store.setState({ arrangement: arrangementReducer(state.arrangement,
        { type: 'saved', layout: state.server.config.layout, etag, version }) });
      break;
    case 'content':
      if (state.content.version === version) store.setState({ content: contentReducer(state.content, { type: 'discard' }) });
      break;
    case 'grid':
      if (state.grid?.version === version) store.setState({ grid: null });
      break;
    case 'form': {
      const form = state.forms[target.key];
      if (form && 'values' in draft) store.setState({ forms: { ...state.forms, [target.key]: tabletFormReducer(form,
        { type: 'saved', values: draft.values, etag, version }) } });
    }
  }
  return outcome;
}

export async function previewGrid(store: WallStoreApi,
  preview: (command: GridCommand, etag: ConfigEtag) => Promise<CommitResult<GridPreview>>,
  rebuild = false,
): Promise<CommitResult<GridPreview>> {
  const state = store.getState();
  if (arrangementDirty(state.arrangement)) return { kind: 'rejected', status: 409,
    message: 'Save or discard the manual draft before building a grid preview.' };
  if (!state.grid || !state.server.etag || state.server.etagState !== 'current') {
    return { kind: 'refused-locally', reason: 'stale-etag' };
  }
  if (!rebuild && (state.grid.stale || state.grid.baseEtag !== state.server.etag)) {
    return { kind: 'rejected', status: 409, message: 'Rebuild preview explicitly after reviewing the current wall.' };
  }
  const version = state.grid.version, command = structuredClone(state.grid.command), etag = state.server.etag;
  const outcome = await preview(command, etag);
  const current = store.getState();
  if (outcome.kind === 'ok' && current.grid && current.server.etag) {
    store.setState({ grid: gridReducer(current.grid, { type: 'preview', preview: outcome.value,
      version, etag: current.server.etag }) });
  }
  return outcome;
}

export function rebuildGrid(store: WallStoreApi, preview: Parameters<typeof previewGrid>[1]) {
  return previewGrid(store, preview, true);
}
