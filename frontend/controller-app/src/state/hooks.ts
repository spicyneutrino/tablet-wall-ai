import { useStore } from 'zustand';
import type { WallStore, WallStoreApi } from './store';
import { arrangementDirty } from './drafts/arrangement';

export function useWallStore<T>(store: WallStoreApi, selector: (state: WallStore) => T): T {
  return useStore(store, selector);
}
export const selectStageEditable = (state: WallStore) => state.ui.editLayout && !state.grid?.preview && !state.content.selection;
export const selectStageMode = (state: WallStore) => state.grid?.preview || arrangementDirty(state.arrangement)
  ? 'arrangement-preview' : state.content.selection ? 'image-preview' : 'live';
export const selectPreviewLayout = (state: WallStore) => state.grid?.preview?.layout ?? state.arrangement?.draft ?? state.server.config?.layout ?? null;
export const selectOnWallLayout = (state: WallStore) => state.server.config?.layout ?? null;
export const selectOnWallContent = (state: WallStore) => state.server.config?.scene.content ?? null;
export const selectPreviewContent = (state: WallStore) => state.content.selection ?? selectOnWallContent(state);
export const selectPreviewUnavailable = (state: WallStore) => {
  const content = selectPreviewContent(state);
  return content?.type === 'image' && content.asset === state.ui.activeImageUnavailableId;
};
export const selectSelectedNameDirty = (state: WallStore) => state.ui.selected
  ? state.forms[`${state.ui.selected}:name`]?.dirty ?? false : false;

export const selectOnWallMode = () => 'live' as const;
export const selectOnWallEditable = () => false;
