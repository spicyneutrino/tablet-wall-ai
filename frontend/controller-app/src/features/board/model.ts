import { DeviceIdSchema } from '../../api/devices';
import { entries } from '../../domain/layout';
import { projectRoster } from '../../domain/roster';
import { aggregate, needsAttention, rosterStatus, tabletState } from '../../domain/status';
import type { ServerState } from '../../session/session';

export function boardView(server: ServerState, nowMono: number) {
  const config = server.config;
  const projected = config ? projectRoster(config, server.roster) : null;
  const unavailable = server.rosterUnreachable || !!server.rosterError;
  const ids = new Set([...Object.keys(entries(config?.layout)), ...Object.keys(server.roster)]);
  const tablets = [...ids].map(key => {
    const id = DeviceIdSchema.parse(key), device = server.roster[id];
    const evidence = projected ? tabletState(projected, id, nowMono)
      : { status: 'unknown', text: 'Unknown', showing: false, online: false };
    const state = unavailable ? { ...evidence, status: 'unknown', text: 'Unknown', showing: false } : evidence;
    const roster = rosterStatus(evidence);
    const word = unavailable ? 'Unknown' : state.showing ? 'Showing'
      : state.status === 'unknown' ? state.text.split(' · ')[0]!
        : roster.key !== 'connected' ? roster.word : state.text.split(' · ')[0]!;
    const tone = unavailable ? 'muted' : state.showing ? 'ok'
      : !needsAttention(state) ? 'muted' : roster.key === 'offline' ? 'warn'
        : roster.tone === 'failure' ? 'err' : 'muted';
    const assignment = config?.tablet_assignments[id];
    return { id, ...state, word, tone, attention: needsAttention(state), number: device?.number,
      name: config?.device_labels[id] || device?.label || `Tablet ${device?.number ?? id.slice(-6)}`,
      model: assignment && assignment.model_id !== null ? assignment.model.label : 'Model not set',
      lastSeen: device?.last_seen ?? null };
  }).sort((a, b) => (a.number ?? Infinity) - (b.number ?? Infinity) || a.id.localeCompare(b.id));
  const counts = projected ? aggregate(projected, nowMono) : { showing: 0, total: 0 };
  const showing = unavailable ? 0 : counts.showing;
  return { tablets, showing, total: counts.total, summary: `${showing} of ${counts.total} showing` };
}

export function reportAge(lastSeen: string | null, now: number) {
  const seen = lastSeen ? Date.parse(lastSeen) : NaN;
  if (!Number.isFinite(seen)) return { label: 'No report', description: 'No last-seen report' };
  const minutes = Math.floor(Math.max(0, now - seen) / 60_000);
  const label = minutes < 1 ? 'just now' : minutes < 60 ? `${minutes} min`
    : minutes < 1440 ? `${Math.floor(minutes / 60)} hr` : `${Math.floor(minutes / 1440)} d`;
  return { label, description: `Last seen ${label}` };
}
