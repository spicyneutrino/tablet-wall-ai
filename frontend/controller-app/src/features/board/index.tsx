import { CircleCheck, CircleHelp, Square, SquareCheck, TriangleAlert, Plus } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { DeviceId } from '../../api/devices';
import { BATCH_WORD, runDeviceBatch } from '../../state/commands/devices';
import type { BatchResult, BatchStatus } from '../../state/commands/devices';
import { useShell } from '../preview/ShellContext';
import { useShellView } from '../preview/useShellView';
import { useWallStore } from '../../state/hooks';
import { Button } from '../../ui/Button';
import ReplacementOffer from './ReplacementOffer';
import { reportAge } from './model';
import './board.css';

type Busy = { busy: true; busyLabel: string } | { busy?: never };
function busyProps(active: boolean, label: string): Busy {
  return active ? { busy: true, busyLabel: label } : {};
}

const TONE: Record<BatchStatus, string> = { completed: 'ok', failed: 'err', conflict: 'err', uncertain: 'warn', untouched: 'muted' };

export default function Board() {
  const { store, session } = useShell();
  const { tablets, loading, firstRun, unreachable, lastReport, server } = useShellView();
  const selected = useWallStore(store, state => state.ui.selected);
  const batchMode = useWallStore(store, state => state.ui.batchMode);
  const batch = useWallStore(store, state => state.ui.batch);
  const [now, setNow] = useState(Date.now);
  const [running, setRunning] = useState<'identify' | 'reconnect' | null>(null);
  const [result, setResult] = useState<BatchResult | null>(null);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const online = tablets.filter(tablet => server.roster[tablet.id]?.online === true);
  const batchBlock = !batch.length ? 'Select at least one tablet.'
    : server.rosterUnreachable ? 'The server is unreachable. Refresh status first.'
      : server.uncertain ? 'The last change was not confirmed. Refresh status first.'
        : server.etagState !== 'current' ? 'Refresh status before sending commands.'
          : server.busy ? 'Another change is being sent. Wait for it to finish.' : '';
  const batchProps = batchBlock ? { 'aria-disabled': true as const, 'aria-describedby': 'tablet-batch-reason' } : {};
  function setBatch(next: DeviceId[]) { store.setState(state => ({ ui: { ...state.ui, batch: next } })); }
  function toggleBatch(id: DeviceId) {
    setBatch(batch.includes(id) ? batch.filter(item => item !== id) : [...batch, id]);
  }
  async function runBatch(action: 'identify' | 'reconnect') {
    if (running || batchBlock) return;
    setRunning(action);
    setResult(null);
    try { setResult(await runDeviceBatch(store, session, action, batch)); }
    finally { setRunning(null); }
  }
  return <section className="tablet-section" id="tablet-health" aria-labelledby="tablets-title" tabIndex={-1}>
    <div className="section-heading"><h2 className="t-heading" id="tablets-title">Tablets</h2>
      <div className="section-tools">
        {!loading ? <Button variant="ghost" size="sm" aria-pressed={batchMode} onClick={() => {
          store.setState(state => ({ ui: { ...state.ui, batchMode: !state.ui.batchMode, batch: [] } }));
          setResult(null);
        }}>{batchMode ? 'Done' : 'Select several'}</Button> : null}
        {!loading ? <span className="t-caption">{unreachable
          ? <>Last report <time data-report-time dateTime={lastReport?.dateTime}>{lastReport?.label ?? 'unavailable'}</time></>
          : `${tablets.length} ${tablets.length === 1 ? 'tablet' : 'tablets'}`}</span> : null}
      </div></div>
    <ul className="tablet-list" role="list" aria-label="Tablets" aria-busy={loading}>
      {loading ? [0, 1, 2, 3].map(index => <li key={index} className="tablet-loading" aria-hidden="true">
        <span className="skel" /><div><span className="skel" /><span className="skel" /></div><span className="skel w-16" />
      </li>) : tablets.map(tablet => {
        const Icon = tablet.showing ? CircleCheck : tablet.tone === 'warn' || tablet.tone === 'err' ? TriangleAlert : CircleHelp;
        const age = reportAge(tablet.lastSeen, now);
        const member = batch.includes(tablet.id);
        return <li key={tablet.id}><Button variant="ghost" className="row tablet-row" id={`tablet-row-${tablet.id}`}
          data-device-id={tablet.id} data-status={tablet.status} data-needs-attention={tablet.attention}
          aria-current={!batchMode && selected === tablet.id ? 'true' : undefined}
          aria-pressed={batchMode ? member : undefined}
          aria-describedby={`tablet-report-${tablet.id}`}
          onClick={() => batchMode ? toggleBatch(tablet.id)
            : store.setState(state => ({ ui: { ...state.ui, selected: tablet.id, drill: tablet.id } }))}>
          {batchMode ? <span className="batch-check" aria-hidden="true">{member ? <SquareCheck /> : <Square />}</span> : null}
          <span className="num">{tablet.number ?? '?'}</span>
          <span className="tablet-identity"><span className="row-name">{tablet.name}</span><span className="t-caption">{tablet.model}</span></span>
          <span className="tablet-report"><span className={`state state-${tablet.tone}`}>
            <Icon aria-hidden="true" /><span>{tablet.word}</span>
          </span><span className="t-caption tablet-age"><span className="sr-only">Last seen </span>{tablet.lastSeen
            ? <time dateTime={tablet.lastSeen}>{age.label}</time> : age.label}</span></span>
        </Button><span id={`tablet-report-${tablet.id}`} className="sr-only">{tablet.text}. {age.description}.</span></li>;
      })}
    </ul>
    <ReplacementOffer />
    {batchMode ? <div className="tablet-batch" role="group" aria-label="Batch tablet commands">
      <div className="flex flex-wrap items-center gap-2">
        <p className="t-caption" aria-live="polite">{batch.length} selected</p>
        <Button variant="ghost" size="sm" onClick={() => setBatch(online.map(tablet => tablet.id))}>Select all</Button>
        <Button variant="ghost" size="sm" onClick={() => setBatch([])}>Clear</Button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" {...batchProps}
          {...busyProps(running === 'identify', 'Identifying…')} onClick={() => void runBatch('identify')}>Identify selected</Button>
        <Button variant="secondary" {...batchProps}
          {...busyProps(running === 'reconnect', 'Reconnecting…')} onClick={() => void runBatch('reconnect')}>Reconnect selected</Button>
      </div>
      {batchBlock ? <p id="tablet-batch-reason" className="t-caption">{batchBlock}</p> : null}
      {result ? <ul className="batch-results" aria-label="Batch results">
        {result.subjects.map(subject => <li key={subject.id} data-device-id={subject.id} data-batch-status={subject.status}>
          <span className="row-name">{tablets.find(tablet => tablet.id === subject.id)?.name ?? 'Tablet'}</span>
          <span className={`state state-${TONE[subject.status]}`}>{BATCH_WORD[subject.status]}</span>
          <span className="t-caption">{subject.message}</span>
        </li>)}
      </ul> : null}
    </div> : null}
    {firstRun ? <p className="t-caption">Joined tablets appear here and on the preview.</p> : null}
    {!loading && !firstRun && !tablets.length ? <p className="t-caption">Tablet status is unavailable. Check that the wall server is running, then refresh status.</p> : null}
    {!loading && !unreachable && !firstRun ? <Button variant="ghost" className="justify-self-start" onClick={() => store.setState(state => ({ ui: { ...state.ui, serverOpen: true } }))}>
      <Plus aria-hidden="true" />Add a tablet</Button> : null}
  </section>;
}
