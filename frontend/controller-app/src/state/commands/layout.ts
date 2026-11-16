import { ConfigSchema } from '../../api/config';
import { paths } from '../../api/paths';
import { LogicalLayoutCommandSchema, PhysicalLayoutCommandSchema } from '../../api/layouts';
import type { Session } from '../../session/session';
import type { WallStoreApi } from '../store';
import { arrangementDirty } from '../drafts/arrangement';
import { run } from './run';

export function applyArrangement(store: WallStoreApi, session: Session) {
  const arrangement = store.getState().arrangement;
  if (!arrangement || !arrangementDirty(arrangement) || !arrangement.baseEtag || arrangement.conflict) {
    return Promise.resolve({ kind: 'rejected' as const, status: 409, message: 'Review the layout before applying it.' });
  }
  const layout = arrangement.draft;
  if (layout.kind === 'physical' && !Object.keys(layout.slots).length) {
    return Promise.resolve({ kind: 'rejected' as const, status: 409, message: 'An empty measured layout cannot be applied. Use Clear wall instead.' });
  }
  const body = layout.kind === 'logical'
    ? LogicalLayoutCommandSchema.parse({ width: layout.width, height: layout.height, placements: layout.placements, sizing: layout.sizing })
    : PhysicalLayoutCommandSchema.parse({ bounds: layout.bounds, slots: layout.slots, sizing: layout.sizing });
  return run(store, { kind: 'arrangement' }, guard => session.request('PUT',
    layout.kind === 'logical' ? paths.logicalLayout : paths.layout, body,
    { ifMatch: guard ?? '', parse: ConfigSchema }));
}
