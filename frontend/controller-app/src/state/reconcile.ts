import type { WallStore } from './store';
import { arrangementDirty, createArrangement } from './drafts/arrangement';
import { contentReducer } from './drafts/content';
import { formBaseline, formKey, tabletFormReducer } from './drafts/tabletForms';

export function reconcile(state: WallStore): Partial<WallStore> {
  const { config, etag } = state.server;
  if (!config) return {};
  const arrangement = arrangementDirty(state.arrangement) && state.arrangement
    ? { ...state.arrangement, conflict: etag !== state.arrangement.baseEtag }
    : { ...createArrangement(config.layout, etag), version: state.arrangement?.version ?? 0 };
  const forms = { ...state.forms };
  for (const form of Object.values(state.forms)) {
    if (form) forms[formKey(form.id, form.group)] = tabletFormReducer(form,
      { type: 'observe', values: formBaseline(config, form.id, form.group), etag });
  }
  const grid = state.grid ? { ...state.grid,
    stale: state.grid.preview ? state.grid.preview.base_etag !== etag : state.grid.dirty && state.grid.baseEtag !== etag } : null;
  let content = state.content;
  if (content.selection && content.baseEtag !== etag) {
    content = content.savedScene ? contentReducer(content, { type: 'discard' }) : { ...content, conflict: true };
  }
  return { arrangement, forms, grid, content };
}
