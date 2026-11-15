import { expect, it } from 'vitest';
import { GridCommandSchema } from '../api/grid';
import { PlaylistSchema } from '../api/playback';
import { A, configFixture } from '../session/testFixtures';
import { createSession } from '../session/session';
import { createWallStore, editArrangement, editContent, editForm, editGrid, editPlaylist, observeForm } from './store';
import type { WallStoreApi } from './store';
import { formKey } from './drafts/tabletForms';
import { createGrid } from './drafts/grid';
import { hasUnsavedEdits } from './unsaved';
const config = configFixture('base');
const changes: Record<string, (store: WallStoreApi) => void> = {
  arrangement: store => editArrangement(store, { type: 'edit', layout: { ...config.layout, width: 200 } }),
  forms: store => { observeForm(store, A, 'profile'); editForm(store, formKey(A, 'profile'), { width: '200' }); },
  content: store => editContent(store, { type: 'select', selection: { type: 'color' }, etag: config.etag }),
  grid: store => {
    const command = GridCommandSchema.parse({ kind: 'logical', device_ids: [A], rows: 1, columns: 1, gap: 0, padding: 0,
      sizing: 'fixed', orientation: 'preserve', allow_empty_cells: false, release_unselected: [] });
    store.setState({ grid: createGrid(command, config.etag) }); editGrid(store, { type: 'edit', command, etag: config.etag });
  },
  playlist: store => editPlaylist(store, { type: 'edit', value: PlaylistSchema.parse({ items: [{ asset: 'sha256:' + 'a'.repeat(64), dwell_ms: 1000 }], loop: false }) }),
};
it.each(Object.entries(changes))('hasUnsavedEdits is true for %s alone', (_name, change) => {
  const store = createWallStore(), session = createSession({ store, isDirty: () => false }); session.ingest(config);
  expect(hasUnsavedEdits(store)).toBe(false); change(store); expect(hasUnsavedEdits(store)).toBe(true);
  session.destroy();
});
