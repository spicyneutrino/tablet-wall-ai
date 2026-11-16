import type { DeviceId } from '../../api/devices';
import { useWallStore } from '../../state/hooks';
import { useShell } from '../preview/ShellContext';

export function useTabletName() {
  const { store } = useShell();
  const config = useWallStore(store, state => state.server.config);
  const roster = useWallStore(store, state => state.server.roster);
  return (id: DeviceId) => config?.device_labels[id] || roster[id]?.label || `Tablet ${roster[id]?.number ?? id.slice(0, 8)}`;
}
