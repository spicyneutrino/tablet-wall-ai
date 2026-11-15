import type { DeviceStatus } from '../../api/devices';
import type { ConfigEtag } from '../../api/etag';
import type { GridCommand, GridPreview } from '../../api/grid';
import type { Member } from '../../domain/gridCommand';
import { membership } from '../../domain/gridCommand';
import type { LayoutLike, RosterDevice } from '../../domain/gridCommand';

export type GridDraft = { command: GridCommand; preview: GridPreview | null; baseEtag: ConfigEtag | null;
  version: number; dirty: boolean; stale: boolean; members: Record<string, Member>; frozen: boolean };
export function createGrid(command: GridCommand, etag: ConfigEtag | null): GridDraft {
  return { command: structuredClone(command), preview: null, baseEtag: etag, version: 0,
    dirty: false, stale: false, members: {}, frozen: false };
}
export type GridEvent =
  | { type: 'observe'; roster: Record<string, RosterDevice | DeviceStatus>; layout: LayoutLike }
  | { type: 'edit'; command: GridCommand; etag: ConfigEtag }
  | { type: 'preview'; preview: GridPreview; version: number; etag: ConfigEtag }
  | { type: 'model-saved'; commandEtag: ConfigEtag; currentEtag: ConfigEtag };
export function gridReducer(draft: GridDraft, event: GridEvent): GridDraft {
  switch (event.type) {
    case 'observe': {
      const observer = membership();
      observer.observe(Object.fromEntries(Object.entries(event.roster).map(([id, device]) => [id,
        { online: device.online, viewport: device.viewport ?? undefined }])), event.layout);
      const automatic = observer.view();
      const members = { ...draft.members };
      for (const [id, fresh] of Object.entries(automatic)) {
        const old = members[id];
        members[id] = !old ? fresh : draft.frozen ? old : { ...old,
          ...(old.membershipSource === 'automatic' && event.roster[id]?.online ? { included: true } : {}),
          ...(['fallback', 'viewport'].includes(old.sizeSource) && fresh.sizeSource === 'viewport'
            ? { size: fresh.size, sizeSource: fresh.sizeSource } : {}) };
      }
      return JSON.stringify(members) === JSON.stringify(draft.members) ? draft : { ...draft, members };
    }
    case 'edit': return { ...draft, command: structuredClone(event.command), preview: null, frozen: true,
      baseEtag: draft.dirty ? draft.baseEtag : event.etag, dirty: true, stale: false, version: draft.version + 1 };
    case 'preview': return event.version !== draft.version ? draft : { ...draft, preview: structuredClone(event.preview),
      dirty: true, frozen: true, baseEtag: event.preview.base_etag, stale: event.preview.base_etag !== event.etag };
    case 'model-saved': return event.commandEtag === event.currentEtag
      ? { ...draft, baseEtag: event.commandEtag, preview: null, stale: false, version: draft.version + 1 }
      : { ...draft, stale: true };
  }
}
