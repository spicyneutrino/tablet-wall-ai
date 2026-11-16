import { DeviceIdSchema } from '../../api/devices';
import { entries } from '../../domain/layout';
import { tabletState } from '../../domain/status';
import { useWallStore } from '../../state/hooks';
import { useShell } from './ShellContext';
import type { Scene } from '../../api/scene';

export function contentName(content: Scene | null) {
  if (!content) return 'Nothing yet';
  if (content.type === 'image') return `${content.name || 'Image'}, ${content.fit === 'contain' ? 'Fit' : 'Fill'}`;
  return content.type === 'calibration' ? 'Calibration grid' : 'Tablet colours';
}

export function useShellView() {
  const { store } = useShell();
  const server = useWallStore(store, state => state.server);
  const now = useWallStore(store, state => state.clock.nowMono);
  const config = server.config;
  const loading = !config && !server.rosterError && server.transportText !== 'Signed out';
  const unreachable = server.rosterUnreachable;
  const devices = Object.fromEntries(Object.entries(server.roster).map(([id, device]) => [id, {
    online: device.online, protocol: device.protocol ?? undefined, caps: device.caps,
    connection_id: device.connection_id,
    mapping: device.mapping ? { state: device.mapping.state, reason: device.mapping.reason ?? undefined,
      profile_revision: device.mapping.profile_revision ?? undefined,
      calibration_revision: device.mapping.calibration_revision ?? undefined } : undefined,
    identify: device.identify ?? undefined,
    render: device.render ? { ...device.render, age_ms: device.render.age_ms ?? undefined,
      expected_token: device.render.expected_token ?? undefined, accepted_token: device.render.accepted_token ?? undefined,
      reason: device.render.reason ?? undefined,
      observed_mono: typeof device.render.observed_mono === 'number' ? device.render.observed_mono : undefined } : undefined,
  }]));
  const placed = entries(config?.layout);
  const ids = new Set([...Object.keys(placed), ...Object.keys(server.roster)]);
  const tablets = [...ids].map(key => {
    const id = DeviceIdSchema.parse(key);
    const device = server.roster[id];
    const state = config ? tabletState({ ...config, runtime: { ...config.runtime, devices } }, id, now)
      : { status: 'unknown', text: 'Unknown', showing: false, online: false };
    const assignment = config?.tablet_assignments[id];
    const model = assignment && assignment.model_id !== null ? assignment.model.label : 'Model not set';
    const name = config?.device_labels[id] || device?.label || `Tablet ${device?.number ?? ''}`.trim();
    const text = unreachable ? 'Unknown' : state.showing ? 'Showing'
      : state.status === 'offline' ? 'Offline' : state.status === 'unplaced' ? 'Not placed' : state.text;
    return { id, name, model, number: device?.number, ...state, text,
      showing: !unreachable && state.showing, status: unreachable ? 'unknown' : state.status };
  }).sort((a, b) => (a.number ?? Infinity) - (b.number ?? Infinity) || a.id.localeCompare(b.id));
  const participating = tablets.filter(tablet => {
    const slot = placed[tablet.id];
    return slot && !('participating' in slot && slot.participating === false);
  });
  const showing = participating.filter(tablet => tablet.showing).length;
  const total = participating.length;
  const summary = `${showing} of ${total} showing`;
  const firstRun = !loading && !!config && tablets.length === 0;
  const lastReport = server.rosterCheckedAt ? { dateTime: server.rosterCheckedAt,
    label: new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
      .format(new Date(server.rosterCheckedAt)) } : null;
  const statuses = Object.fromEntries(tablets.map(tablet => [tablet.id,
    { status: tablet.status, text: tablet.text, label: tablet.name, number: tablet.number ?? undefined }]));
  const profileFor = (id: string, revision?: number | string) => {
    const profiles = [...config?.referenced_displays ?? [], ...config?.displays ?? []];
    return profiles.find(profile => profile.device_id === id && (revision === undefined || profile.revision === revision));
  };
  return { server, config, loading, unreachable, firstRun, lastReport, tablets, showing, total, summary, statuses, profileFor };
}
