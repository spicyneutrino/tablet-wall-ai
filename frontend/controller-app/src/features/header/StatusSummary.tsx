import { StatusBadge } from '../../ui/StatusBadge';
import { useShellView } from '../preview/useShellView';

export default function StatusSummary() {
  const { server, loading, unreachable, firstRun, showing, total, tablets } = useShellView();
  const problem = tablets.find(tablet => tablet.attention);
  const status = loading ? 'connecting' : unreachable ? 'error' : server.uncertain ? 'error'
    : server.rosterError || firstRun || !total ? 'unknown' : showing === total && !problem ? 'ok' : 'warn';
  const label = loading ? 'Connecting…' : unreachable ? 'Unreachable' : server.uncertain ? 'Not confirmed'
    : server.rosterError ? 'Status unavailable' : firstRun ? 'No tablets yet' : `${showing} of ${total}`;
  function showStatus() {
    const target = document.getElementById(problem ? `tablet-row-${problem.id}` : 'tablet-health');
    target?.scrollIntoView({ block: 'nearest' });
    target?.focus({ preventScroll: true });
  }
  const fullLabel = unreachable ? 'Server unreachable' : !firstRun && !loading && !server.uncertain && !server.rosterError ? `${label} showing` : label;
  const cause = problem ? `${problem.name}: ${problem.word}.` : firstRun ? 'Open the join address on a tablet.' : 'Review the tablet board.';
  return <div className="wall-summary" aria-live="polite" aria-atomic="true">
    <StatusBadge className="status-full" status={status} label={fullLabel} onClick={showStatus} aria-describedby="wall-status-cause" />
    <StatusBadge className="status-compact" status={status} label={label} onClick={showStatus} aria-describedby="wall-status-cause" />
    <span id="wall-status-cause" className="sr-only">{cause}</span>
  </div>;
}
