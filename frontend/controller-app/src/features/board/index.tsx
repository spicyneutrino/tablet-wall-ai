import { CircleCheck, CircleHelp, TriangleAlert, Plus } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useShell } from '../preview/ShellContext';
import { useShellView } from '../preview/useShellView';
import { useWallStore } from '../../state/hooks';
import { Button } from '../../ui/Button';
import { reportAge } from './model';
import './board.css';

export default function Board() {
  const { store } = useShell();
  const { tablets, loading, firstRun, unreachable, lastReport } = useShellView();
  const selected = useWallStore(store, state => state.ui.selected);
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return <section className="tablet-section" id="tablet-health" aria-labelledby="tablets-title" tabIndex={-1}>
    <div className="section-heading"><h2 className="t-heading" id="tablets-title">Tablets</h2>
      {!loading ? <span className="t-caption">{unreachable
        ? <>Last report <time data-report-time dateTime={lastReport?.dateTime}>{lastReport?.label ?? 'unavailable'}</time></>
        : `${tablets.length} ${tablets.length === 1 ? 'tablet' : 'tablets'}`}</span> : null}</div>
    <ul className="tablet-list" role="list" aria-label="Tablets" aria-busy={loading}>
      {loading ? [0, 1, 2, 3].map(index => <li key={index} className="tablet-loading" aria-hidden="true">
        <span className="skel" /><div><span className="skel" /><span className="skel" /></div><span className="skel w-16" />
      </li>) : tablets.map(tablet => {
        const Icon = tablet.showing ? CircleCheck : tablet.tone === 'warn' || tablet.tone === 'err' ? TriangleAlert : CircleHelp;
        const age = reportAge(tablet.lastSeen, now);
        return <li key={tablet.id}><Button variant="ghost" className="row tablet-row" id={`tablet-row-${tablet.id}`}
          data-device-id={tablet.id} data-status={tablet.status} data-needs-attention={tablet.attention}
          aria-current={selected === tablet.id ? 'true' : undefined} aria-describedby={`tablet-report-${tablet.id}`}
          onClick={() => store.setState(state => ({ ui: { ...state.ui, selected: tablet.id, drill: tablet.id } }))}>
          <span className="num">{tablet.number ?? '?'}</span>
          <span className="tablet-identity"><span className="row-name">{tablet.name}</span><span className="t-caption">{tablet.model}</span></span>
          <span className="tablet-report"><span className={`state state-${tablet.tone}`}>
            <Icon aria-hidden="true" /><span>{tablet.word}</span>
          </span><span className="t-caption tablet-age"><span className="sr-only">Last seen </span>{tablet.lastSeen
            ? <time dateTime={tablet.lastSeen}>{age.label}</time> : age.label}</span></span>
        </Button><span id={`tablet-report-${tablet.id}`} className="sr-only">{tablet.text}. {age.description}.</span></li>;
      })}
    </ul>
    {firstRun ? <p className="t-caption">No tablets yet. Open the join address on a tablet to add it here.</p> : null}
    {!loading && !firstRun && !tablets.length ? <p className="t-caption">Tablet status is unavailable. Check that the wall server is running, then refresh status.</p> : null}
    {!loading && !unreachable && !firstRun ? <Button variant="ghost" className="justify-self-start" onClick={() => store.setState(state => ({ ui: { ...state.ui, serverOpen: true } }))}>
      <Plus aria-hidden="true" />Add a tablet</Button> : null}
  </section>;
}
