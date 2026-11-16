import { useWallStore } from '../../state/hooks';
import { useShell } from '../preview/ShellContext';
import { useShellView } from '../preview/useShellView';
export default function Facts() {
  const { store } = useShell();
  const { tablets } = useShellView();
  const id = useWallStore(store, state => state.ui.drill ?? state.ui.selected);
  const tablet = tablets.find(tablet => tablet.id === id);
  return tablet ? <dl><dt className="t-muted">State</dt><dd>{tablet.text}</dd>
    <dt className="t-muted">Connection</dt><dd>{tablet.online ? 'Online' : 'Offline'}</dd></dl> : null;
}
