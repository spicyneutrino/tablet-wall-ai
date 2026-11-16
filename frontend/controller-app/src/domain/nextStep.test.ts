import { describe, expect, it } from 'vitest';
import type { Config } from '../api/config';
import { ConfigSchema } from '../api/config';
import { GridCommandSchema } from '../api/grid';
import type { Layout } from '../api/layouts';
import { LogicalLayoutSchema } from '../api/layouts';
import { A, B, C, configFixture, deviceFixture, renderFixture } from '../session/testFixtures';
import { createArrangement } from '../state/drafts/arrangement';
import { emptyContent } from '../state/drafts/content';
import { createGrid } from '../state/drafts/grid';
import { createForm, formKey } from '../state/drafts/tabletForms';
import { createWallStore } from '../state/store';
import type { WallStore } from '../state/store';
import { nextStep } from './nextStep';

const IMAGE = { type: 'image', asset: `sha256:${'a'.repeat(64)}`, fit: 'cover' };
const COLOR = { type: 'color' };

type DeviceMap = WallStore['server']['roster'];

function plot(...ids: string[]): Layout {
  return LogicalLayoutSchema.parse({
    kind: 'logical', width: 100, height: 100, sizing: { mode: 'fixed', padding: 0 },
    placements: Object.fromEntries(ids.map((id, index) => [id,
      { x: index * 10, y: 0, w: 10, h: 10, bezel: { top: 0, right: 0, bottom: 0, left: 0 } }])),
  });
}

function configOf(options: { layout?: Layout; devices?: DeviceMap; scene?: unknown; labels?: Record<string, string> } = {}): Config {
  const base = configFixture('base');
  return ConfigSchema.parse({ ...base,
    ...(options.layout ? { layout: options.layout } : {}),
    ...(options.devices ? { runtime: { ...base.runtime, devices: options.devices } } : {}),
    ...(options.scene ? { scene: { content: options.scene } } : {}),
    ...(options.labels ? { device_labels: options.labels } : {}) });
}

function wall(overrides: Partial<WallStore> = {}): WallStore {
  return { ...createWallStore(0).getState(), ...overrides };
}

function serverOf(overrides: Partial<WallStore['server']>): WallStore['server'] {
  return { ...createWallStore(0).getState().server, ...overrides };
}

function synced(config: Config, overrides: Partial<WallStore['server']> = {}): WallStore['server'] {
  return serverOf({ config, roster: { ...config.runtime.devices }, ...overrides });
}

describe('nextStep', () => {
  it('reports an uncertain command outcome first', () => {
    expect(nextStep(wall({ server: serverOf({ uncertain: true }) }))).toEqual({ kind: 'uncertain' });
  });

  it('reports an unreachable server', () => {
    const state = wall({ server: serverOf({ rosterError: 'Connection lost.', rosterUnreachable: true }) });
    expect(nextStep(state)).toEqual({ kind: 'unreachable' });
  });

  it('reports the first draft in conflict', () => {
    expect(nextStep(wall({ arrangement: { ...createArrangement(plot(A), null), conflict: true } })))
      .toEqual({ kind: 'conflict', draft: 'arrangement' });
    expect(nextStep(wall({ content: { ...emptyContent(), conflict: true } })))
      .toEqual({ kind: 'conflict', draft: 'content' });
    const command = GridCommandSchema.parse({ kind: 'logical', device_ids: [A], rows: 1, columns: 1,
      gap: 0, padding: 0, sizing: 'fixed', orientation: 'preserve', allow_empty_cells: false, release_unselected: [] });
    expect(nextStep(wall({ grid: { ...createGrid(command, null), stale: true } })))
      .toEqual({ kind: 'conflict', draft: 'grid' });
    expect(nextStep(wall({ forms: { [formKey(A, 'name')]:
      { ...createForm(A, 'name', { name: '' }, null), conflict: true } } })))
      .toEqual({ kind: 'conflict', draft: 'form' });
  });

  it('reports a placed tablet that is offline, with its name', () => {
    const state = wall({ server: synced(configOf({ layout: plot(A),
      devices: { [A]: deviceFixture(A, { online: false }) }, scene: IMAGE, labels: { [A]: 'Tablet 4' } })) });
    expect(nextStep(state)).toEqual({ kind: 'tablet-offline', tablet: { deviceId: A, name: 'Tablet 4' } });
  });

  it('reports a placed tablet that shows the wrong content, with its name', () => {
    const state = wall({ server: synced(configOf({ layout: plot(A),
      devices: { [A]: deviceFixture(A, { render: renderFixture('failed') }) }, scene: IMAGE, labels: { [A]: 'Tablet 4' } })) });
    expect(nextStep(state)).toEqual({ kind: 'wrong-content', tablet: { deviceId: A, name: 'Tablet 4' } });
  });

  it('reports a replacement offer for a new tablet and an offline registration', () => {
    const devices: DeviceMap = { [A]: deviceFixture(A), [B]: deviceFixture(B), [C]: deviceFixture(C, { online: false }) };
    const state = wall({ server: synced(configOf({ layout: plot(B), devices, scene: IMAGE,
      labels: { [A]: 'New iPad', [C]: 'Tablet 4' } })) });
    expect(nextStep(state)).toEqual({ kind: 'replacement',
      candidate: { deviceId: A, name: 'New iPad' }, previous: { deviceId: C, name: 'Tablet 4' } });
  });

  it('asks for a tablet when none has joined', () => {
    const state = wall({ server: synced(configOf({ layout: plot(), devices: {}, scene: IMAGE })) });
    expect(nextStep(state)).toEqual({ kind: 'add-tablet' });
  });

  it('asks to arrange once tablets have joined but nothing is placed', () => {
    const state = wall({ server: synced(configOf({ layout: plot(),
      devices: { [A]: deviceFixture(A) }, scene: IMAGE })) });
    expect(nextStep(state)).toEqual({ kind: 'arrange' });
  });

  it('asks to show an image once tablets are arranged without one', () => {
    const state = wall({ server: synced(configOf({ layout: plot(A),
      devices: { [A]: deviceFixture(A) }, scene: COLOR })) });
    expect(nextStep(state)).toEqual({ kind: 'show-image' });
  });

  it('has nothing to ask when the wall is set up', () => {
    const state = wall({ server: synced(configOf({ layout: plot(A),
      devices: { [A]: deviceFixture(A) }, scene: IMAGE })) });
    expect(nextStep(state)).toBeNull();
  });

  it('returns the highest-priority problem when several exist', () => {
    const devices: DeviceMap = { [A]: deviceFixture(A, { online: false }), [B]: deviceFixture(B) };
    let state = wall({
      server: serverOf({ uncertain: true, rosterError: 'Connection lost.', rosterUnreachable: true, roster: devices,
        config: configOf({ layout: plot(A), devices, scene: COLOR, labels: { [A]: 'Tablet 4', [B]: 'Tablet 1' } }) }),
      arrangement: { ...createArrangement(plot(A), null), conflict: true },
    });
    expect(nextStep(state)).toEqual({ kind: 'uncertain' });
    state = { ...state, server: { ...state.server, uncertain: false } };
    expect(nextStep(state)).toEqual({ kind: 'unreachable' });
    state = { ...state, server: { ...state.server, rosterError: null, rosterUnreachable: false } };
    expect(nextStep(state)).toEqual({ kind: 'conflict', draft: 'arrangement' });
    state = { ...state, arrangement: null };
    expect(nextStep(state)).toEqual({ kind: 'tablet-offline', tablet: { deviceId: A, name: 'Tablet 4' } });

    const nextDevices: DeviceMap = { [A]: deviceFixture(A), [B]: deviceFixture(B),
      [C]: deviceFixture(C, { online: false }) };
    state = { ...state, server: { ...state.server, roster: nextDevices,
      config: configOf({ layout: plot(B), devices: nextDevices, scene: COLOR,
        labels: { [A]: 'New iPad', [C]: 'Tablet 4' } }) } };
    expect(nextStep(state)).toEqual({ kind: 'replacement',
      candidate: { deviceId: A, name: 'New iPad' }, previous: { deviceId: C, name: 'Tablet 4' } });

    state = { ...state, server: { ...state.server, roster: { [B]: deviceFixture(B) },
      config: configOf({ layout: plot(), devices: { [B]: deviceFixture(B) }, scene: COLOR }) } };
    expect(nextStep(state)).toEqual({ kind: 'arrange' });
    state = { ...state, server: { ...state.server,
      config: configOf({ layout: plot(B), devices: { [B]: deviceFixture(B) }, scene: COLOR }) } };
    expect(nextStep(state)).toEqual({ kind: 'show-image' });
    state = { ...state, server: { ...state.server,
      config: configOf({ layout: plot(B), devices: { [B]: deviceFixture(B) }, scene: IMAGE }) } };
    expect(nextStep(state)).toBeNull();
  });
});
