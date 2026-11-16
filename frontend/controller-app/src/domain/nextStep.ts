import type { Config } from '../api/config';
import type { DeviceId, DeviceStatus } from '../api/devices';
import type { WallStore } from '../state/store';
import { entries } from './layout';
import { rosterStatus, tabletState } from './status';
import { projectRoster } from './roster';

export type TabletName = { deviceId: DeviceId; name: string };
export type DraftKind = 'arrangement' | 'content' | 'grid' | 'form';

export type NextStep =
  | { kind: 'uncertain' }
  | { kind: 'unreachable' }
  | { kind: 'conflict'; draft: DraftKind }
  | { kind: 'tablet-offline'; tablet: TabletName }
  | { kind: 'wrong-content'; tablet: TabletName }
  | { kind: 'replacement'; candidate: TabletName; previous: TabletName }
  | { kind: 'add-tablet' }
  | { kind: 'arrange' }
  | { kind: 'show-image' };

type ReplacementStep = Extract<NextStep, { kind: 'replacement' }>;

function tabletName(config: Config, roster: Record<string, DeviceStatus>, id: string): TabletName {
  const deviceId = id as DeviceId;
  const device = roster[deviceId];
  const name = config.device_labels[deviceId] || device?.label
    || (device?.number ? `Tablet ${device.number}` : 'Unregistered tablet');
  return { deviceId, name };
}

function conflictDraft(state: WallStore): DraftKind | null {
  if (state.arrangement?.conflict) return 'arrangement';
  if (state.content.conflict) return 'content';
  if (state.grid?.stale) return 'grid';
  if (Object.values(state.forms).some((form) => form?.conflict)) return 'form';
  return null;
}

function replacementOffer(config: Config, roster: Record<string, DeviceStatus>, placed: string[]): ReplacementStep | null {
  const placedIds = new Set(placed);
  const order = (id: string) => roster[id]?.number ?? Infinity;
  const candidate = Object.keys(roster)
    .filter((id) => roster[id]?.online === true && !placedIds.has(id))
    .sort((a, b) => order(a) - order(b) || a.localeCompare(b))
    .at(-1);
  if (!candidate) return null;
  const previous = Object.keys(roster).find((id) => id !== candidate && roster[id]?.online !== true);
  if (!previous) return null;
  return { kind: 'replacement',
    candidate: tabletName(config, roster, candidate), previous: tabletName(config, roster, previous) };
}

export function nextStep(state: WallStore): NextStep | null {
  const { server, clock } = state;
  if (server.uncertain) return { kind: 'uncertain' };
  if (server.rosterUnreachable) return { kind: 'unreachable' };
  const conflict = conflictDraft(state);
  if (conflict) return { kind: 'conflict', draft: conflict };

  const config = server.config;
  if (!config || server.rosterError) return null;
  const roster = server.roster;
  const placed = Object.keys(entries(config.layout));
  const view = projectRoster(config, roster);
  const stateOf = (id: string) => rosterStatus(tabletState(view, id, clock.nowMono));

  const offline = placed.find((id) => stateOf(id).key === 'offline');
  if (offline) return { kind: 'tablet-offline', tablet: tabletName(config, roster, offline) };
  const wrong = placed.find((id) => stateOf(id).key === 'wrong-content');
  if (wrong) return { kind: 'wrong-content', tablet: tabletName(config, roster, wrong) };

  const replacement = replacementOffer(config, roster, placed);
  if (replacement) return replacement;

  if (!Object.keys(roster).length) return { kind: 'add-tablet' };
  if (!placed.length) return { kind: 'arrange' };
  if (config.scene.content.type !== 'image') return { kind: 'show-image' };
  return null;
}
