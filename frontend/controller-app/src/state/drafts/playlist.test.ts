import { expect, it } from 'vitest';
import { PlaylistEtagSchema } from '../../api/etag';
import { PlaylistSchema } from '../../api/playback';
import { emptyPlaylist, playlistReducer } from './playlist';
const playlist = PlaylistSchema.parse({ items: [{ asset: 'sha256:' + 'a'.repeat(64), dwell_ms: 1000 }], loop: false });
it('playlist observation keeps dirty values and late saves preserve newer input', () => {
  const first = playlistReducer(emptyPlaylist(), { type: 'observe', value: playlist, etag: PlaylistEtagSchema.parse('p1') });
  const dirty = playlistReducer(first, { type: 'edit', value: { ...playlist, loop: true } });
  const remote = playlistReducer(dirty, { type: 'observe', value: playlist, etag: PlaylistEtagSchema.parse('p2') });
  expect(remote).toMatchObject({ draft: { loop: true }, dirty: true, conflict: true, etag: 'p1' });
  const newer = playlistReducer(remote, { type: 'edit', value: { ...playlist, items: [...playlist.items, ...playlist.items] } });
  const saved = playlistReducer(newer, { type: 'saved', value: dirty.draft, etag: PlaylistEtagSchema.parse('p3'), version: dirty.version });
  expect(saved.draft!.items).toHaveLength(2); expect(saved.dirty).toBe(true);
  const discarded = playlistReducer(saved, { type: 'discard', value: playlist, etag: PlaylistEtagSchema.parse('p3') });
  expect(discarded).toMatchObject({ draft: playlist, dirty: false, conflict: false });
});
