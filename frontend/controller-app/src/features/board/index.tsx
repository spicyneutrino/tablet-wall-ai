import { CircleCheck, CircleHelp, TriangleAlert, Plus } from 'lucide-react';
import { useShell } from '../preview/ShellContext';
import { useShellView } from '../preview/useShellView';
import { useWallStore } from '../../state/hooks';
import { Button } from '../../ui/Button';

export default function Board() {
  const { store } = useShell();
  const { tablets, loading, firstRun, unreachable, lastReport, summary } = useShellView();
  const selected = useWallStore(store, state => state.ui.selected);
  return <section className="tablet-section" id="tablet-health" aria-labelledby={firstRun ? undefined : 'tablets-title'}>
    {!firstRun ? <div className="section-heading"><h2 className="t-heading" id="tablets-title">Tablets</h2>
      {!loading ? <span className="t-caption">{unreachable
        ? <>Last report <time data-report-time dateTime={lastReport?.dateTime}>{lastReport?.label ?? 'unavailable'}</time></> : summary}</span> : null}</div> : null}
    <ul className="tablet-list" aria-label="Tablets" aria-busy={loading}>
      {loading ? [0, 1, 2, 3].map(index => <li key={index} className="tablet-loading" aria-hidden="true">
        <span className="skel" /><div><span className="skel" /><span className="skel" /></div><span className="skel w-16" />
      </li>) : tablets.map(tablet => {
        const offline = tablet.status === 'offline';
        const Icon = tablet.showing ? CircleCheck : offline ? TriangleAlert : CircleHelp;
        return <li key={tablet.id}><button className="row" aria-current={selected === tablet.id ? 'true' : undefined}
          onClick={() => store.setState(state => ({ ui: { ...state.ui, selected: tablet.id, drill: tablet.id } }))}>
          <span className="num">{tablet.number ?? '?'}</span>
          <span className="tablet-identity"><span className="row-name">{tablet.name}</span><span className="t-caption">{tablet.model}</span></span>
          <span className={`state state-${tablet.showing ? 'ok' : offline ? 'warn' : 'muted'}`} title={tablet.text}>
            <Icon aria-hidden="true" />{tablet.showing ? 'Showing' : offline ? 'Offline' : tablet.status === 'unknown' ? 'Unknown' : tablet.text}
          </span>
        </button></li>;
      })}
    </ul>
    {firstRun ? <p className="t-caption">Joined tablets appear here and on the preview.</p> : null}
    {!loading && !unreachable && !firstRun ? <Button variant="ghost" className="justify-self-start" onClick={() => store.setState(state => ({ ui: { ...state.ui, serverOpen: true } }))}>
      <Plus aria-hidden="true" />Add a tablet</Button> : null}
  </section>;
}
