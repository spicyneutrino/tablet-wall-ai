import { ConfigSchema } from '../../api/config';
import type { SceneInput } from '../../api/scene';
import type { Session } from '../../session/session';
import type { WallStoreApi } from '../store';
import { run } from './run';

export function show(store: WallStoreApi, session: Session) {
  const selection = store.getState().content.selection;
  if (!selection) return Promise.resolve({ kind: 'rejected' as const, status: 409, message: 'Pick a source to preview it.' });
  const content: SceneInput = selection.type === 'image'
    ? { type: 'image', asset: selection.asset, fit: selection.fit, background: selection.background }
    : { type: selection.type };
  return run(store, { kind: 'content' }, guard => session.request('PUT', '/api/v3/scene', { content },
    { ifMatch: guard ?? '', parse: ConfigSchema }));
}
