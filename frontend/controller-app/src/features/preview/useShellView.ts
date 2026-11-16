import { boardView } from '../board/model';
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
  const { tablets, showing, total, summary } = boardView(server, now);
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
