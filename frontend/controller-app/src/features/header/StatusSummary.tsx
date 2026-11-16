import { StatusBadge } from '../../ui/StatusBadge';
import { useShell } from '../preview/ShellContext';
import { useShellView } from '../preview/useShellView';

export default function StatusSummary() {
  const { store } = useShell();
  const { server, loading, unreachable, firstRun, showing, total } = useShellView();
  const status = loading ? 'connecting' : unreachable ? 'error' : server.uncertain ? 'error'
    : firstRun || !total ? 'unknown' : showing === total ? 'ok' : 'warn';
  const label = loading ? 'Connecting…' : unreachable ? 'Unreachable' : server.uncertain ? 'Not confirmed'
    : firstRun ? 'No tablets yet' : `${showing} of ${total}`;
  function showStatus() {
    if (unreachable || firstRun || !total) store.setState(state => ({ ui: { ...state.ui, serverOpen: true } }));
    else document.getElementById('tablet-health')?.scrollIntoView({ block: 'nearest' });
  }
  if (firstRun) return <button type="button" className="chip chip-neutral" onClick={showStatus}>No tablets yet</button>;
  const fullLabel = unreachable ? 'Server unreachable' : total && !loading && !server.uncertain ? `${label} showing` : label;
  return <>
    <StatusBadge className="status-full" status={status} label={fullLabel} onClick={showStatus} />
    <StatusBadge className="status-compact" status={status} label={label} onClick={showStatus} />
  </>;
}
