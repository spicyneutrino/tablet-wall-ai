import type { ConfigEtag } from '../../api/etag';
import type { SceneInput } from '../../api/scene';
export type ContentDraft = { selection: SceneInput | null; savedScene: { name: string; etag: ConfigEtag } | null;
  baseEtag: ConfigEtag | null; version: number; conflict: boolean };
export const emptyContent = (): ContentDraft => ({ selection: null, savedScene: null, baseEtag: null, version: 0, conflict: false });
export type ContentEvent =
  | { type: 'select'; selection: SceneInput; etag: ConfigEtag; savedScene?: ContentDraft['savedScene'] }
  | { type: 'discard' }
  | { type: 'rebuild'; etag: ConfigEtag; version: number };
export function contentReducer(draft: ContentDraft, event: ContentEvent): ContentDraft {
  switch (event.type) {
    case 'select': return { selection: structuredClone(event.selection), savedScene: event.savedScene ?? null,
      baseEtag: draft.selection ? draft.baseEtag : event.etag, version: draft.version + 1, conflict: draft.conflict };
    case 'discard': return { ...emptyContent(), version: draft.version + 1 };
    case 'rebuild': return draft.savedScene || draft.version !== event.version ? draft
      : { ...draft, baseEtag: event.etag, conflict: false, version: draft.version + 1 };
  }
}
