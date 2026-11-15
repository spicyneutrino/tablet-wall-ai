import type { WallStore, WallStoreApi } from './store';
import { formsDirty } from './drafts/tabletForms';
import { arrangementDirty } from './drafts/arrangement';
export function hasUnsavedEdits(store: WallStoreApi | WallStore): boolean {
  const state = 'getState' in store ? store.getState() : store;
  return arrangementDirty(state.arrangement) || formsDirty(state.forms)
    || !!state.content.selection || !!state.grid?.dirty || state.playlist.dirty;
}
