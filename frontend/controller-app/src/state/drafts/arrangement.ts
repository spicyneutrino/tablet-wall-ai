import type { ConfigEtag } from '../../api/etag';
import type { Layout } from '../../api/layouts';
import { layoutSignature } from '../../domain/layout';

export type ArrangementDraft = {
  base: Layout; draft: Layout; baseEtag: ConfigEtag | null;
  undo: Layout[]; redo: Layout[]; conflict: boolean; version: number;
};
export const arrangementDirty = (value: ArrangementDraft | null) => !!value
  && layoutSignature(value.base) !== layoutSignature(value.draft);
export function createArrangement(layout: Layout, etag: ConfigEtag | null): ArrangementDraft {
  return { base: structuredClone(layout), draft: structuredClone(layout), baseEtag: etag,
    undo: [], redo: [], conflict: false, version: 0 };
}
export type ArrangementEvent =
  | { type: 'edit'; layout: Layout }
  | { type: 'undo' | 'redo' }
  | { type: 'keep'; layout: Layout; etag: ConfigEtag; version: number }
  | { type: 'discard'; layout: Layout; etag: ConfigEtag | null }
  | { type: 'saved'; layout: Layout; etag: ConfigEtag; version: number };
export function arrangementReducer(draft: ArrangementDraft, event: ArrangementEvent): ArrangementDraft {
  switch (event.type) {
    case 'edit':
      if (layoutSignature(draft.draft) === layoutSignature(event.layout)) return draft;
      return { ...draft, draft: structuredClone(event.layout), undo: [...draft.undo, draft.draft].slice(-80),
        redo: [], version: draft.version + 1 };
    case 'undo': {
      const previous = draft.undo.at(-1);
      return previous ? { ...draft, draft: previous, undo: draft.undo.slice(0, -1),
        redo: [...draft.redo, draft.draft].slice(-80), version: draft.version + 1 } : draft;
    }
    case 'redo': {
      const next = draft.redo.at(-1);
      return next ? { ...draft, draft: next, undo: [...draft.undo, draft.draft].slice(-80),
        redo: draft.redo.slice(0, -1), version: draft.version + 1 } : draft;
    }
    case 'keep':
      return event.version === draft.version ? { ...draft, base: structuredClone(event.layout),
        baseEtag: event.etag, conflict: false, version: draft.version + 1 } : draft;
    case 'discard':
      return { ...createArrangement(event.layout, event.etag), version: draft.version + 1 };
    case 'saved':
      return { ...draft, base: structuredClone(event.layout), baseEtag: event.etag, conflict: false,
        ...(draft.version === event.version ? { draft: structuredClone(event.layout), undo: [], redo: [] } : {}) };
  }
}
