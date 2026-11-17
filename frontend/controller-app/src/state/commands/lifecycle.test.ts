import { describe, expect, it } from 'vitest';
import { ConfigSchema } from '../../api/config';
import { ImpactPreviewSchema, RebindPreviewSchema } from '../../api/lifecycle';
import { LogicalLayoutSchema } from '../../api/layouts';
import { A, B, C, configFixture, deviceFixture } from '../../session/testFixtures';
import type { ServerState } from '../../session/session';
import { createWallStore } from '../store';
import {
  CHANGED, conflictText, finishLifecycle, newTablets, numberProblem, rebindCommand, replacementPair, staleReason, unsavedBlock,
} from './lifecycle';
import type { ReplaceChoices } from './lifecycle';

const roster = (online: Record<string, boolean>, numbers: Record<string, number> = {}) => Object.fromEntries(
  Object.entries(online).map(([id, on]) => [id, deviceFixture(id as typeof A, { online: on, number: numbers[id] })]));
const placeOnly = (...ids: string[]) => ConfigSchema.parse({ ...configFixture('base'), layout: LogicalLayoutSchema.parse({
  kind: 'logical', width: 100, height: 100, sizing: { mode: 'fixed', padding: 0 },
  placements: Object.fromEntries(ids.map((id, index) => [id, { x: index * 10, y: 0, w: 10, h: 10, bezel: { top: 0, right: 0, bottom: 0, left: 0 } }])) }) });
const name = (id: string) => id.slice(-1);

describe('replacement offer', () => {
  it('pairs the newest online unplaced tablet with the first other tablet that is offline', () => {
    const devices = roster({ [A]: false, [B]: true, [C]: true }, { [A]: 1, [B]: 2, [C]: 3 });
    expect(newTablets(placeOnly(A), devices)).toEqual([B, C]);
    expect(replacementPair(placeOnly(A), devices)).toEqual({ newId: C, oldId: A });
  });
  it('offers nothing without an unplaced online tablet or without an offline one', () => {
    expect(replacementPair(placeOnly(A, B), roster({ [A]: false, [B]: true }))).toBeNull();
    expect(replacementPair(placeOnly(A), roster({ [A]: true, [B]: true }))).toBeNull();
    expect(replacementPair(null, roster({ [A]: false, [B]: true }))).toBeNull();
  });
});

describe('replace command', () => {
  const choices = (extra: Partial<ReplaceChoices> = {}): ReplaceChoices =>
    ({ hardware: 'same_hardware', active: true, transferLabel: true, number: '', saved: {}, ...extra });
  const saved = [{ name: 'Wall A', etag: 'a', kind: 'logical', valid: true }, { name: 'Wall B', etag: 'b', kind: 'physical', valid: true }];
  it('needs an explicit hardware answer', () => {
    expect(rebindCommand(A, choices({ hardware: '' }), saved)).toBeNull();
  });
  it('sends the chosen layouts with their etags, and the number only when typed', () => {
    expect(rebindCommand(A, choices({ saved: { 'Wall B': true } }), saved)).toEqual({ replaces: A, hardware: 'same_hardware', active: true,
      saved_layouts: [{ name: 'Wall B', etag: 'b' }], transfer_label: true });
    expect(rebindCommand(A, choices({ number: ' 7 ', hardware: 'different_hardware', transferLabel: false }), saved)).toMatchObject({
      hardware: 'different_hardware', number: 7, transfer_label: false, saved_layouts: [] });
  });
  it('rejects numbers the server would', () => {
    for (const text of ['0', '-1', '1.5', 'x']) expect(numberProblem(text)).not.toBeNull();
    expect(numberProblem('')).toBeNull();
    expect(rebindCommand(A, choices({ number: '0' }), saved)).toBeNull();
  });
  it('words each server conflict', () => {
    const names = { old: 'Tablet 4', new: 'Tablet 5' };
    expect(conflictText({ code: 'old_connected', message: 'raw' }, names)).toContain('Only an offline tablet');
    expect(conflictText({ code: 'physical_rebuild_required', message: 'raw' }, names)).toContain('Edit layout');
    expect(conflictText({ code: 'unknown', message: 'raw words' }, names)).toBe('raw words');
  });
});

describe('a review goes stale', () => {
  const server = (extra: Partial<ServerState> = {}): ServerState => ({ ...createWallStore(0).getState().server, etag: 'e' as never,
    etagState: 'current', roster: roster({ [A]: false, [B]: true }), connectionVersions: { [B]: 2 }, ...extra });
  const impact = ImpactPreviewSchema.parse({ etag: 'e', online: false, active_entry: null, saved_layouts: [], has_measurement_history: false });
  const preview = RebindPreviewSchema.parse({ base_etag: 'e', old_id: A, new_id: B, affected_active: false, affected_saved: [], untouched_saved: [],
    conflicts: [], profile_revision_map: {}, calibration_revision_map: {}, label_after: null, number_after: null, old_offline: true, new_connection_id: 'c' });
  const replace = { kind: 'replace', oldId: A, newId: B, preview, connection: 2 } as const;
  it('while the wall, the tablets and their connections still match, it does not', () => {
    expect(staleReason(replace, server(), name)).toBeNull();
    expect(staleReason({ kind: 'forget', id: A, impact }, server(), name)).toBeNull();
  });
  it.each([
    ['the wall changed', { etag: 'f' as never }, CHANGED],
    ['status is stale', { etagState: 'stale' as const }, 'Refresh status, then review again.'],
    ['the old tablet came back', { roster: roster({ [A]: true, [B]: true }) }, '1 came back online. Review again.'],
    ['the new tablet went offline', { roster: roster({ [A]: false, [B]: false }) }, '2 went offline. Review again.'],
    ['the new tablet reconnected', { connectionVersions: { [B]: 3 } }, '2 reconnected. Review again.'],
  ])('when %s', (_, extra, text) => {
    expect(staleReason(replace, server(extra), name)).toBe(text);
  });
  it('for Forget when the tablet is back online', () => {
    expect(staleReason({ kind: 'forget', id: A, impact }, server({ roster: roster({ [A]: true }) }), name)).toContain('Forget works only on an offline tablet');
  });
});

it('blocks a lifecycle change while a name or model draft is unsaved', () => {
  expect(unsavedBlock({}, [A])).toBe('');
  expect(unsavedBlock({ [`${A}:name`]: { dirty: true } } as never, [A])).toContain('unsaved');
});

it('finishing a change keeps the notice, picks a tablet that exists and drops the gone ones from a batch', () => {
  const store = createWallStore(0);
  store.setState(state => ({ ui: { ...state.ui, selected: A, drill: A, batch: [A, B] } }));
  finishLifecycle(store, { notice: 'Done.', select: B, gone: [A] });
  expect(store.getState().ui).toMatchObject({ lifecycleNotice: 'Done.', selected: B, drill: B, batch: [B] });
  finishLifecycle(store, { notice: 'Gone.', select: null, gone: [B] });
  expect(store.getState().ui).toMatchObject({ selected: null, drill: null, batch: [] });
});
