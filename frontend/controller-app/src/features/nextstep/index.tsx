import { useEffect, useState } from 'react';
import {
  CircleHelp, CloudOff, Copy, GitCompareArrows, Images as ImagesIcon, LayoutGrid, MonitorSmartphone, RefreshCw, Replace,
  TabletSmartphone, TriangleAlert,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { DeviceId } from '../../api/devices';
import { paths } from '../../api/paths';
import { ReadinessSchema } from '../../api/readiness';
import { nextStep } from '../../domain/nextStep';
import type { NextStep as Step } from '../../domain/nextStep';
import type { WallStoreApi } from '../../state/store';
import { useWallStore } from '../../state/hooks';
import { Button } from '../../ui/Button';
import { useShell } from '../preview/ShellContext';
import './nextstep.css';

type Card = { tone: 'warn' | 'err' | 'info'; Icon: LucideIcon; title: string; body: string; alert: boolean };

function cardFor(step: Step): Card {
  switch (step.kind) {
    case 'uncertain': return { tone: 'err', Icon: CircleHelp, title: 'Next step: refresh', alert: true,
      body: 'The last command was not confirmed. Refresh status before you try again.' };
    case 'unreachable': return { tone: 'err', Icon: CloudOff, title: 'Next step: wait for the server', alert: true,
      body: 'The tablets keep showing their last image. The console reconnects by itself. If this lasts, check that the server is running on the wall’s computer.' };
    case 'conflict': return { tone: 'warn', Icon: GitCompareArrows, title: 'Next step: review your change', alert: true,
      body: 'The wall changed while you edited. Your edit is kept in Preview until you decide.' };
    case 'tablet-offline': return { tone: 'warn', Icon: TriangleAlert, title: `Next step: bring ${step.tablet.name} back`, alert: true,
      body: 'Wake the tablet and it reconnects by itself. Its place on the wall is reserved.' };
    case 'wrong-content': return { tone: 'err', Icon: TriangleAlert, title: `Next step: get ${step.tablet.name} showing again`, alert: true,
      body: 'It is not showing the wall image. Open it to try again, or measure it again if its screen changed.' };
    case 'replacement': return { tone: 'warn', Icon: Replace, title: `Next step: replace ${step.previous.name}`, alert: true,
      body: `${step.candidate.name} joined and can take ${step.previous.name}’s place on the wall.` };
    case 'add-tablet': return { tone: 'info', Icon: TabletSmartphone, title: 'Next step: add your first tablet', alert: false,
      body: 'On each tablet, open this address in the browser or scan the code.' };
    case 'arrange': return { tone: 'info', Icon: LayoutGrid, title: 'Next step: arrange the tablets', alert: false,
      body: 'Tablets have joined. Place each one on the wall so it knows where it belongs.' };
    case 'show-image': return { tone: 'info', Icon: ImagesIcon, title: 'Next step: show an image', alert: false,
      body: 'The wall is arranged. Pick an image and show it on the tablets.' };
  }
}

function showTablet(store: WallStoreApi, id: DeviceId) {
  store.setState(state => ({ ui: { ...state.ui, selected: id, drill: null } }));
  document.getElementById(`tablet-row-${id}`)?.focus();
}

function reviewChanges() {
  const target = document.getElementById('conflict') ?? document.getElementById('preview');
  target?.focus();
}

function joinAddress(url: string) {
  try { return { url, host: new URL(url).host }; } catch { return { url, host: url }; }
}

export default function NextStep() {
  const { store, session } = useShell();
  const state = useWallStore(store, value => value);
  const step = nextStep(state);
  const addTablet = step?.kind === 'add-tablet';
  const [join, setJoin] = useState<{ url: string; host: string } | null>(null);
  const [copyStatus, setCopyStatus] = useState('');
  const [refreshError, setRefreshError] = useState('');

  useEffect(() => {
    if (!addTablet) return;
    let active = true;
    void session.request('GET', paths.readiness, undefined, { parse: ReadinessSchema }).then(result => {
      if (!active || result.kind !== 'ok') return;
      const url = result.value.tablet_url;
      if (url) setJoin(joinAddress(url));
    });
    return () => { active = false; };
  }, [addTablet, session]);

  if (!step) return null;
  const card = cardFor(step);
  const { Icon } = card;
  function refresh() {
    setRefreshError('');
    void session.refresh().catch(error => setRefreshError(
      error instanceof Error ? error.message : 'Status is still unavailable. Try again.'));
  }
  async function copy() {
    if (!join) return;
    if (!navigator.clipboard) { setCopyStatus('Select and copy the join address above.'); return; }
    try {
      await navigator.clipboard.writeText(join.url);
      setCopyStatus('Link copied.');
    } catch {
      setCopyStatus('Select and copy the join address above.');
    }
  }
  return <section className={`note note-${card.tone}`} aria-labelledby="next-step-title"
    role={card.alert ? 'alert' : undefined}>
    <h2 className="note-title" id="next-step-title"><Icon aria-hidden="true" />{card.title}</h2>
    <p className="t-body">{card.body}</p>
    {step.kind === 'add-tablet' ? <>
      <div className="join-code nextstep-join">
        <span className="nextstep-qr"><img src={paths.joinQr} alt="QR code for the tablet address" width={96} height={96} /></span>
        <div className="nextstep-join-copy">
          {join ? <>
            <a className="t-heading join-address" href={join.url} translate="no">{join.host}</a>
            <Button className="justify-self-start" onClick={() => void copy()}><Copy aria-hidden="true" />Copy link</Button>
            <p className="t-caption" aria-live="polite">{copyStatus}</p>
          </> : <p className="t-caption">Reading the tablet address…</p>}
        </div>
      </div>
      <p className="t-caption">Then measure each tablet and pick an image. Tablets keep their place if they restart.</p>
    </> : null}
    {step.kind !== 'add-tablet' ? <div className="nextstep-actions">
      {step.kind === 'uncertain' ? <Button onClick={refresh}><RefreshCw aria-hidden="true" />Refresh status</Button> : null}
      {step.kind === 'unreachable' ? <Button variant="secondary" onClick={refresh}><RefreshCw aria-hidden="true" />Try now</Button> : null}
      {step.kind === 'conflict' ? <Button onClick={reviewChanges}>Review changes</Button> : null}
      {step.kind === 'tablet-offline' || step.kind === 'wrong-content' ? <Button onClick={() => showTablet(store, step.tablet.deviceId)}>
        <MonitorSmartphone aria-hidden="true" />Show tablet</Button> : null}
      {step.kind === 'replacement' ? <Button onClick={() => showTablet(store, step.candidate.deviceId)}>
        <Replace aria-hidden="true" />Review replacement</Button> : null}
      {step.kind === 'arrange'
        ? <Button onClick={() => store.setState(value => ({ ui: { ...value.ui, source: 'layouts' } }))}>
          <LayoutGrid aria-hidden="true" />Arrange tablets</Button> : null}
      {step.kind === 'show-image'
        ? <Button onClick={() => store.setState(value => ({ ui: { ...value.ui, source: 'images' } }))}>
          <ImagesIcon aria-hidden="true" />Choose an image</Button> : null}
    </div> : null}
    {refreshError ? <p className="t-caption" aria-live="polite">{refreshError}</p> : null}
  </section>;
}
