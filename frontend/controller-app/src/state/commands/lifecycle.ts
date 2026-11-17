import { ConfigSchema } from '../../api/config';
import type { Config } from '../../api/config';
import type { DeviceId, DeviceStatus } from '../../api/devices';
import { ForgetCommandSchema, ImpactPreviewSchema, RebindApplySchema, RebindCommandSchema, RebindPreviewSchema } from '../../api/lifecycle';
import type { ImpactPreview, RebindCommand, RebindPreview } from '../../api/lifecycle';
import { paths } from '../../api/paths';
import type { SnapshotSummary } from '../../api/saved';
import { entries } from '../../domain/layout';
import type { CommandOutcome } from '../../session/outcome';
import type { ServerState, Session } from '../../session/session';
import type { WallStore, WallStoreApi } from '../store';
import { deviceMessage } from './devices';

export const CHANGED = 'Something changed since you looked. Review it again.';

export function lifecycleMessage(outcome: CommandOutcome<unknown>): string {
  return outcome.kind === 'conflict' ? CHANGED : deviceMessage(outcome);
}

export const readImpact = (session: Session, id: DeviceId) =>
  session.request('GET', paths.impact(id), undefined, { fenced: 'durable', parse: ImpactPreviewSchema });

export const removePlacement = (session: Session, id: DeviceId, etag: string) =>
  session.request('DELETE', paths.placement(id), undefined, { ifMatch: etag, parse: ConfigSchema });

export const forgetTablet = (session: Session, id: DeviceId, etag: string, removeActive: boolean) =>
  session.request('DELETE', paths.device(id), ForgetCommandSchema.parse({ remove_active: removeActive, saved_layouts: 'keep' }),
    { ifMatch: etag, parse: ConfigSchema });

export const previewReplacement = (session: Session, newId: DeviceId, command: RebindCommand, etag: string) =>
  session.request('POST', paths.rebindPreview(newId), command, { ifMatch: etag, parse: RebindPreviewSchema });

export const applyReplacement = (session: Session, newId: DeviceId, command: RebindCommand, preview: RebindPreview) =>
  session.request('POST', paths.rebind(newId), RebindApplySchema.parse({ ...command, new_connection_id: preview.new_connection_id }),
    { ifMatch: preview.base_etag, parse: ConfigSchema });

export type Review =
  | { kind: 'remove' | 'forget'; id: DeviceId; impact: ImpactPreview }
  | { kind: 'replace'; oldId: DeviceId; newId: DeviceId; preview: RebindPreview; connection: number };

/** Why a reviewed change can no longer be confirmed, or null while the review still describes the wall. */
export function staleReason(review: Review, server: ServerState, name: (id: DeviceId) => string): string | null {
  if (server.etagState !== 'current') return 'Refresh status, then review again.';
  if (review.kind !== 'replace') {
    if (server.etag !== review.impact.etag) return CHANGED;
    return review.kind === 'forget' && server.roster[review.id]?.online
      ? `${name(review.id)} came back online. Forget works only on an offline tablet.` : null;
  }
  if (server.etag !== review.preview.base_etag) return CHANGED;
  if (server.rosterError) return 'Status is out of date. Refresh status, then review again.';
  if (server.roster[review.oldId]?.online) return `${name(review.oldId)} came back online. Review again.`;
  if (!server.roster[review.newId]?.online) return `${name(review.newId)} went offline. Review again.`;
  return (server.connectionVersions[review.newId] ?? 0) === review.connection ? null
    : `${name(review.newId)} reconnected. Review again.`;
}

export type Pair = { newId: DeviceId; oldId: DeviceId };

/** Tablets that are online and not in the active layout, newest number last. */
export function newTablets(config: Config, roster: Record<string, DeviceStatus>): DeviceId[] {
  const placed = new Set(Object.keys(entries(config.layout)));
  return (Object.keys(roster) as DeviceId[]).filter(id => roster[id]?.online === true && !placed.has(id))
    .sort((a, b) => (roster[a]?.number ?? Infinity) - (roster[b]?.number ?? Infinity) || a.localeCompare(b));
}

export function offlineTablets(roster: Record<string, DeviceStatus>, except?: DeviceId): DeviceId[] {
  return (Object.keys(roster) as DeviceId[]).filter(id => id !== except && roster[id]?.online !== true)
    .sort((a, b) => (roster[a]?.number ?? Infinity) - (roster[b]?.number ?? Infinity) || a.localeCompare(b));
}

/** The offer the Next step card names: the newest unplaced tablet and the first other tablet that is offline. */
export function replacementPair(config: Config | null, roster: Record<string, DeviceStatus>): Pair | null {
  if (!config) return null;
  const newId = newTablets(config, roster).at(-1);
  if (!newId) return null;
  const oldId = (Object.keys(roster) as DeviceId[]).find(id => id !== newId && roster[id]?.online !== true);
  return oldId ? { newId, oldId } : null;
}

export type Hardware = 'same_hardware' | 'different_hardware';
export type ReplaceChoices = {
  hardware: Hardware | ''; active: boolean; transferLabel: boolean; number: string; saved: Record<string, boolean>;
};

export function numberProblem(raw: string): string | null {
  const text = raw.trim();
  if (!text) return null;
  return /^[1-9]\d{0,5}$/.test(text) ? null : 'Use a whole number from 1 up, or leave it empty to keep the old number.';
}

/** Null until the operator has said whether the new tablet is the same hardware. */
export function rebindCommand(oldId: DeviceId, choices: ReplaceChoices, saved: readonly SnapshotSummary[]): RebindCommand | null {
  if (!choices.hardware || numberProblem(choices.number)) return null;
  const number = choices.number.trim();
  return RebindCommandSchema.parse({ replaces: oldId, hardware: choices.hardware, active: choices.active,
    saved_layouts: saved.filter(item => choices.saved[item.name]).map(item => ({ name: item.name, etag: item.etag })),
    transfer_label: choices.transferLabel, ...(number ? { number: Number(number) } : {}) });
}

/** The server's conflict codes, in the words an operator can act on. */
export function conflictText(conflict: { code: string; message: string }, names: { old: string; new: string }): string {
  switch (conflict.code) {
    case 'old_connected': return `${names.old} is online. Only an offline tablet can be replaced.`;
    case 'target_already_present': return `${names.new} is already in a layout you chose. Clear that choice, or remove it from the layout first.`;
    case 'physical_rebuild_required': return 'A different tablet has different measurements. Measure it, then place it in Edit layout instead of replacing.';
    case 'target_history_conflict': return `${names.new} already has measurements of its own, so ${names.old}’s cannot be copied onto it.`;
    case 'number_in_use': return `That number belongs to another tablet. Choose a different number, or leave it empty.`;
    default: return conflict.message;
  }
}

/** The server stops a running playlist on every lifecycle change, so say so before it happens. */
export function playbackNote(config: Config | null): string | null {
  return config?.runtime.presentation.owner === 'playback' ? 'The playlist is running and will stop.' : null;
}

export function unsavedBlock(forms: WallStore['forms'], ids: readonly DeviceId[]): string {
  return ids.some(id => forms[`${id}:name`]?.dirty || forms[`${id}:model`]?.dirty)
    ? 'Save or discard the unsaved name or model first.' : '';
}

export function wallBlock(server: ServerState): string {
  return server.etagState !== 'current' ? 'Refresh status before changing the wall.'
    : server.uncertain ? 'The last change was not confirmed. Refresh status first.'
      : server.busy ? 'Another change is being sent. Wait for it to finish.' : '';
}

/** Leaves the store pointing at a tablet that still exists and records what happened where it stays mounted. */
export function finishLifecycle(store: WallStoreApi, result: { notice: string; select: DeviceId | null; gone: DeviceId[] }) {
  store.setState(state => ({ ui: { ...state.ui, lifecycleNotice: result.notice,
    selected: result.select, drill: result.select && state.ui.drill ? result.select : null,
    batch: state.ui.batch.filter(id => !result.gone.includes(id)) } }));
}

type Disabled = { disabled: true; disabledReason: string } | { disabled?: never; disabledReason?: never };
export function disabledWhen(reason: string): Disabled {
  return reason ? { disabled: true, disabledReason: reason } : {};
}
