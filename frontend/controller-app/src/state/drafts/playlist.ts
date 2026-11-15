import type { PlaylistEtag } from '../../api/etag';
import type { Playlist } from '../../api/playback';
export type PlaylistDraft = { saved: Playlist | null; draft: Playlist | null; etag: PlaylistEtag | null;
  dirty: boolean; conflict: boolean; version: number };
export const emptyPlaylist = (): PlaylistDraft => ({ saved: null, draft: null, etag: null, dirty: false, conflict: false, version: 0 });
export type PlaylistEvent =
  | { type: 'edit'; value: Playlist | null }
  | { type: 'observe' | 'discard'; value: Playlist | null; etag: PlaylistEtag }
  | { type: 'saved'; value: Playlist | null; etag: PlaylistEtag; version: number };
export function playlistReducer(draft: PlaylistDraft, event: PlaylistEvent): PlaylistDraft {
  if (event.type === 'edit') return { ...draft, draft: structuredClone(event.value), version: draft.version + 1,
    dirty: JSON.stringify(draft.saved) !== JSON.stringify(event.value) };
  if (event.type === 'observe' && draft.dirty) return { ...draft, conflict: draft.etag !== event.etag };
  const keep = event.type === 'saved' && event.version !== draft.version;
  const value = keep ? draft.draft : structuredClone(event.value);
  return { ...draft, saved: structuredClone(event.value), draft: value, etag: event.etag, conflict: false,
    dirty: JSON.stringify(value) !== JSON.stringify(event.value), version: draft.version + (event.type === 'discard' ? 1 : 0) };
}
