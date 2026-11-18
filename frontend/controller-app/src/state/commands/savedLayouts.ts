import { ConfigSchema } from '../../api/config';
import type { Config } from '../../api/config';
import { LayoutSchema } from '../../api/layouts';
import type { ClearLayoutCommand, Layout, StoredLayout } from '../../api/layouts';
import { paths } from '../../api/paths';
import { SavedLayoutsSchema } from '../../api/saved';
import type { SavedLayout } from '../../api/saved';
import { entries, layoutDraft } from '../../domain/layout';
import type { Layout as LayoutDoc } from '../../domain/layout';
import { snapshotName } from '../../domain/names';
import type { CommandOutcome } from '../../session/outcome';
import type { Session } from '../../session/session';
import { arrangementReducer, createArrangement } from '../drafts/arrangement';
import type { WallStoreApi } from '../store';
import { run } from './run';

// Behaviour ported from the old operator console, removed in the switch-over.
export const SNAPSHOT_NAME_RULE = 'Use letters, numbers, spaces, dots, underscores or hyphens. Start with a letter or number. 64 characters at most.';
export const RESTORE_POINT_NAME = /^Before (physical|logical) [a-f0-9]{12}$/;

export type ArrangementKind = 'logical' | 'physical';
export type SavedArrangement = { name: string; etag: string; kind: ArrangementKind; valid: false }
  | { name: string; etag: string; kind: ArrangementKind; valid: true; layout: Layout; count: number };

export const isRestorePoint = (name: string) => RESTORE_POINT_NAME.test(name);

function canonical(stored: StoredLayout): Layout | null {
  try {
    return LayoutSchema.parse(layoutDraft(stored as unknown as LayoutDoc));
  } catch {
    return null;
  }
}

function toArrangement(kind: ArrangementKind, entry: SavedLayout): SavedArrangement {
  if (!entry.valid) return { name: entry.name, etag: entry.etag, kind, valid: false };
  const layout = canonical(entry.layout);
  if (!layout) return { name: entry.name, etag: entry.etag, kind, valid: false };
  return { name: entry.name, etag: entry.etag, kind, valid: true, layout, count: Object.keys(entries(layout as unknown as LayoutDoc)).length };
}

function read(session: Session, path: typeof paths.layouts | typeof paths.logicalLayouts) {
  return session.request('GET', path, undefined, { fenced: 'durable', parse: SavedLayoutsSchema });
}

/** Both listings merged by name. An invalid entry appears in both, so it is listed once. */
export async function loadSavedArrangements(session: Session): Promise<CommandOutcome<SavedArrangement[]>> {
  const [physical, logical] = await Promise.all([read(session, paths.layouts), read(session, paths.logicalLayouts)]);
  if (physical.kind !== 'ok') return physical;
  if (logical.kind !== 'ok') return logical;
  const merged = new Map<string, SavedArrangement>();
  for (const [kind, listing] of [['physical', physical.value], ['logical', logical.value]] as const) {
    for (const entry of listing.layouts) {
      const next = toArrangement(kind, entry);
      const current = merged.get(next.name);
      if (!current || next.valid && !current.valid) merged.set(next.name, next);
    }
  }
  return { kind: 'ok', value: [...merged.values()].sort((left, right) => left.name.localeCompare(right.name)) };
}

/** Draw a saved arrangement in Preview. No request is sent. */
export function previewArrangement(store: WallStoreApi, saved: SavedArrangement): boolean {
  if (!saved.valid) return false;
  const state = store.getState(), config = state.server.config;
  if (!config) return false;
  const base = state.arrangement ?? createArrangement(config.layout, state.server.etag);
  store.setState({ grid: null, arrangement: arrangementReducer(base, { type: 'edit', layout: saved.layout }) });
  return true;
}

export function needsKindConfirmation(store: WallStoreApi, saved: SavedArrangement): boolean {
  const kind = store.getState().server.config?.layout.kind;
  return !!kind && saved.valid && kind !== saved.kind;
}

export function applyArrangement(store: WallStoreApi, session: Session, saved: SavedArrangement) {
  return run(store, { kind: 'arrangement' }, guard => session.request('POST', paths.recallLayout(saved.kind, saved.name),
    undefined, { ifMatch: guard ?? undefined, parse: ConfigSchema }));
}

export async function saveArrangement(store: WallStoreApi, session: Session, rawName: string,
  replace = false): Promise<CommandOutcome<Config>> {
  const name = snapshotName(rawName);
  if (name === null) return { kind: 'rejected', status: 422,
    message: rawName.trim() ? SNAPSHOT_NAME_RULE : `Enter an arrangement name. ${SNAPSHOT_NAME_RULE}` };
  const config = store.getState().server.config;
  if (!config) return { kind: 'rejected', status: 409, message: 'The wall is not ready yet.' };
  return session.request('PUT', paths.savedLayout(config.layout.kind, name, replace), undefined,
    { useCurrentEtag: true, parse: ConfigSchema });
}

export async function deleteArrangement(store: WallStoreApi, session: Session,
  saved: SavedArrangement): Promise<CommandOutcome<Config>> {
  if (!store.getState().server.config) return { kind: 'rejected', status: 409, message: 'The wall is not ready yet.' };
  return session.request('DELETE', paths.savedLayout(saved.kind, saved.name), undefined,
    { useCurrentEtag: true, parse: ConfigSchema });
}

export function clearWall(store: WallStoreApi, session: Session) {
  const body: ClearLayoutCommand = { confirm: true };
  return run(store, { kind: 'arrangement' }, guard => session.request('POST', paths.clearLayout, body,
    { ifMatch: guard ?? undefined, parse: ConfigSchema }));
}

export function outcomeMessage(outcome: CommandOutcome<unknown>): string {
  switch (outcome.kind) {
    case 'ok': return '';
    case 'conflict': return 'The wall changed. Refresh Layouts and review it again.';
    case 'precondition-missing': return 'Refresh status, then try again.';
    case 'rejected': return outcome.message;
    case 'uncertain': return `Not confirmed. ${outcome.message}`;
    case 'refused-locally':
      return outcome.reason === 'busy' ? 'Another change is already being sent. Wait for it to finish.'
        : outcome.reason === 'uncertain' ? 'The last change was not confirmed. Refresh status first.'
          : outcome.reason === 'unsupported' ? 'Update the console before editing.'
            : 'The wall may have changed. Refresh status first.';
  }
}
