import { ConfigSchema } from '../../api/config';
import type { ConfigEtag } from '../../api/etag';
import { DeviceIdSchema } from '../../api/devices';
import { GridCommandSchema, GridPreviewSchema } from '../../api/grid';
import type { GridCommand } from '../../api/grid';
import { paths } from '../../api/paths';
import { command, membership } from '../../domain/gridCommand';
import type { Member } from '../../domain/gridCommand';
import type { Session } from '../../session/session';
import { createGrid, gridReducer } from '../drafts/grid';
import type { GridDraft } from '../drafts/grid';
import type { WallStoreApi } from '../store';
import { previewGrid } from './run';

export function observeGrid(store: WallStoreApi) {
  const { server, grid } = store.getState();
  const config = server.config;
  if (!config) return;
  let draft = grid;
  if (!draft) {
    const observer = membership();
    observer.observe(Object.fromEntries(Object.entries(server.roster).map(([id, device]) => [id,
      { online: device.online, viewport: device.viewport ?? undefined }])), config.layout);
    const members = observer.view();
    const ids = Object.keys(members).filter(id => members[id]?.included)
      .sort((a, b) => (server.roster[a]?.number ?? Infinity) - (server.roster[b]?.number ?? Infinity) || a.localeCompare(b));
    const columns = Math.max(1, Math.ceil(Math.sqrt(ids.length)));
    draft = { ...createGrid({ kind: config.layout.kind, device_ids: ids.map(id => DeviceIdSchema.parse(id)),
      rows: Math.max(1, Math.ceil(ids.length / columns)), columns, gap: 0, padding: 0,
      sizing: 'tablets', orientation: 'preserve', allow_empty_cells: ids.length !== columns * Math.ceil(ids.length / columns),
      release_unselected: [] }, server.etag), members };
  }
  const observed = gridReducer(draft, { type: 'observe', roster: server.roster, layout: config.layout });
  const members = Object.fromEntries(Object.entries(observed.members).map(([id, member]) =>
    [id, draft.frozen && !draft.members[id] ? { ...member, included: false } : member]));
  const ids = draft.frozen ? draft.command.device_ids : Object.keys(members).filter(id => members[id]?.included)
    .sort((a, b) => (server.roster[a]?.number ?? Infinity) - (server.roster[b]?.number ?? Infinity) || a.localeCompare(b))
    .map(id => DeviceIdSchema.parse(id));
  if (!grid || JSON.stringify(members) !== JSON.stringify(grid.members) || ids.join() !== grid.command.device_ids.join()) {
    store.setState({ grid: { ...observed, members, command: { ...observed.command, device_ids: ids } } });
  }
}

export function changeGrid(store: WallStoreApi, patch: Partial<GridCommand>, members?: Record<string, Member>) {
  const { grid, server } = store.getState();
  if (!grid || !server.etag) return;
  store.setState({ grid: { ...gridReducer(grid, { type: 'edit', command: { ...grid.command, ...patch }, etag: server.etag }),
    members: members ?? grid.members } });
}

export function includeInGrid(store: WallStoreApi, id: string, included: boolean) {
  const grid = store.getState().grid;
  const member = grid?.members[id];
  if (!grid || !member) return;
  const ids = grid.command.device_ids.filter(key => key !== id);
  if (included) ids.push(DeviceIdSchema.parse(id));
  changeGrid(store, { device_ids: ids }, { ...grid.members, [id]: { ...member, included, membershipSource: 'operator' } });
}

export function sizeInGrid(store: WallStoreApi, id: string, dimension: 'w' | 'h', value: number) {
  const grid = store.getState().grid;
  const member = grid?.members[id];
  if (!grid || !member) return;
  changeGrid(store, {}, { ...grid.members, [id]: { ...member, size: { ...member.size, [dimension]: value }, sizeSource: 'operator' } });
}

export function moveInGrid(store: WallStoreApi, id: string, delta: -1 | 1) {
  const grid = store.getState().grid;
  if (!grid) return;
  const ids = [...grid.command.device_ids], index = ids.findIndex(key => key === id), next = index + delta;
  if (index < 0 || next < 0 || next >= ids.length) return;
  [ids[index], ids[next]] = [ids[next]!, ids[index]!];
  changeGrid(store, { device_ids: ids });
}

function gridInput(store: WallStoreApi): GridCommand {
  const { grid, server } = store.getState();
  if (!grid || !server.config) throw new Error('Waiting for the wall.');
  const input = grid.command, config = server.config;
  const selected = new Set<string>(input.device_ids);
  const active = config.layout.kind === 'logical' ? config.layout.placements : config.layout.slots;
  if (Object.keys(active).some(id => !selected.has(id) && !input.release_unselected.includes(DeviceIdSchema.parse(id)))) {
    throw new Error('Acknowledge each tablet released from the active arrangement, including offline reservations.');
  }
  if (input.orientation === 'auto' && input.device_ids.some(id => !server.roster[id]?.online)) {
    throw new Error('Auto orientation needs a fresh online viewport. Choose Preserve for offline reservations.');
  }
  const revisions: Record<string, { profile_revision: number; calibration_revision: number }> = {};
  const angles: Record<string, number | string> = {};
  for (const id of input.device_ids) {
    const slot = config.layout.kind === 'physical' ? config.layout.slots[id] : undefined;
    const profile = config.displays.filter(item => item.device_id === id).sort((a, b) => b.revision - a.revision)[0];
    const calibration = profile && config.calibrations.filter(item => item.device_id === id && item.profile_revision === profile.revision)
      .sort((a, b) => b.revision - a.revision)[0];
    if (slot) revisions[id] = { profile_revision: slot.profile_revision, calibration_revision: slot.calibration_revision };
    else if (profile && calibration) revisions[id] = { profile_revision: profile.revision, calibration_revision: calibration.revision };
    angles[id] = input.kind === 'physical' ? input.mount_angles?.[id] ?? slot?.mount_angle ?? '' : '';
  }
  if (input.kind === 'physical' && input.device_ids.some(id => angles[id] === '')) {
    throw new Error('Declare the mounted top edge for every new measured tablet. Choose a mount angle in Order and sizes.');
  }
  return GridCommandSchema.parse(command({ kind: input.kind, ids: input.device_ids, rows: input.rows, columns: input.columns,
    gap: input.gap, padding: input.padding, sizing: input.sizing, orientation: input.kind === 'physical' ? 'preserve' : input.orientation,
    holes: input.allow_empty_cells, releases: input.release_unselected.filter(id => !selected.has(id)),
    sizes: Object.fromEntries(Object.entries(grid.members).map(([id, member]) => [id, member.size])), revisions, angles }));
}

export async function buildGridPreview(store: WallStoreApi, session: Session, rebuild = false) {
  let input: GridCommand;
  try { input = gridInput(store); } catch (error) {
    return { kind: 'rejected' as const, status: 422, message: error instanceof Error ? error.message : 'Check the grid inputs.' };
  }
  const draft = store.getState().grid!;
  store.setState({ grid: { ...draft, command: input, frozen: true } });
  return previewGrid(store, (body, etag) => session.request('POST', paths.gridPreview, body,
    { ifMatch: etag, parse: GridPreviewSchema }), rebuild);
}

export function gridOutdated(grid: GridDraft, etag: ConfigEtag | null) {
  return grid.stale || grid.baseEtag !== etag;
}

export async function applyGrid(store: WallStoreApi, session: Session) {
  const draft = store.getState().grid;
  if (!draft?.preview || draft.stale || draft.preview.base_etag !== store.getState().server.etag) {
    return { kind: 'rejected' as const, status: 409, message: 'Rebuild preview before applying this grid.' };
  }
  const version = draft.version, base = draft.preview.base_etag;
  const body = GridCommandSchema.parse({ ...draft.command, guards: draft.preview.guards });
  const outcome = await session.request('POST', paths.grid, body, { ifMatch: base, parse: ConfigSchema });
  const current = store.getState();
  if (outcome.kind === 'ok') {
    if (current.grid?.version === version) store.setState({ grid: null });
    return outcome;
  }
  if (outcome.kind !== 'conflict') return outcome;
  const wallChanged = current.server.etag !== base;
  if (wallChanged && current.grid?.version === version) store.setState({ grid: { ...current.grid, stale: true } });
  return { kind: 'rejected' as const, status: 412, message: wallChanged
    ? 'The wall changed since preview. Review these inputs, then rebuild the preview.'
    : "A tablet's connection or viewport changed since preview. Review these inputs, then preview again." };
}
