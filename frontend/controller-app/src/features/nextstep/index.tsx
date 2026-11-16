import { CloudOff, CircleHelp, TriangleAlert, TabletSmartphone, Copy } from 'lucide-react';
import { useEffect, useState } from 'react';
import { ReadinessSchema } from '../../api/readiness';
import type { Readiness } from '../../api/readiness';
import { Button } from '../../ui/Button';
import { useShell } from '../preview/ShellContext';
import { useShellView } from '../preview/useShellView';

export default function NextStep() {
  const { store, session } = useShell();
  const { server, firstRun, unreachable, tablets } = useShellView();
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [copyStatus, setCopyStatus] = useState('');
  const [refreshError, setRefreshError] = useState('');
  useEffect(() => {
    if (!firstRun) return;
    let active = true;
    void session.request('GET', '/api/v3/readiness', undefined, { parse: ReadinessSchema }).then(result => {
      if (active && result.kind === 'ok') setReadiness(result.value);
    });
    return () => { active = false; };
  }, [firstRun, session]);
  const offline = tablets.find(tablet => tablet.status === 'offline');
  const next = unreachable ? { tone: 'err', Icon: CloudOff, title: 'Next step: wait for the server',
    body: 'The tablets keep showing their last image. The console reconnects by itself. If this lasts, check that the server is running on the wall’s computer.' }
    : server.uncertain ? { tone: 'err', Icon: CircleHelp, title: 'Next step: refresh', body: 'The last command was not confirmed. Refresh status before trying again.' }
    : firstRun ? { tone: 'info', Icon: TabletSmartphone, title: 'Next step: add your first tablet', body: 'On each tablet, open this address in the browser or scan the code.' }
    : offline ? { tone: 'warn', Icon: TriangleAlert, title: `Next step: bring ${offline.name} back`, body: 'Wake the tablet and it reconnects by itself. Its place on the wall is reserved.' } : null;
  if (!next) return null;
  const { Icon } = next;
  return <section className={`note note-${next.tone}`} aria-labelledby="next-step-title">
    <h2 className="note-title" id="next-step-title"><Icon aria-hidden="true" />{next.title}</h2>
    <p className="t-body">{next.body}</p>
    {firstRun && readiness?.tablet_url ? <div className="join-code">
      {readiness.join_qr_url ? <img src={readiness.join_qr_url} alt="QR code for joining the tablet wall" width="96" height="96" /> : null}
      <div className="shell-slot"><a className="t-heading join-address" href={readiness.tablet_url}>{new URL(readiness.tablet_url).host}</a>
        <Button onClick={() => {
          if (!navigator.clipboard) { setCopyStatus('Select and copy the join address above.'); return; }
          void navigator.clipboard.writeText(readiness.tablet_url ?? '').then(() => setCopyStatus('Link copied.'),
            () => setCopyStatus('Select and copy the join address above.'));
        }}><Copy aria-hidden="true" />Copy link</Button><span className="t-caption" aria-live="polite">{copyStatus}</span></div>
    </div> : null}
    {firstRun ? <p className="t-caption">Then measure each tablet and pick an image. Tablets keep their place if they restart.</p> : null}
    <div className="shell-actions">{unreachable || server.uncertain ? <Button variant={server.uncertain ? 'primary' : 'secondary'}
      onClick={() => {
        setRefreshError('');
        void session.refresh().catch(error => setRefreshError(error instanceof Error ? error.message : 'Status is still unavailable. Try again.'));
      }}>{server.uncertain ? 'Refresh status' : 'Try now'}</Button>
      : !firstRun || !readiness?.tablet_url ? <Button variant={firstRun ? 'primary' : 'ghost'} onClick={() => store.setState(state => ({ ui: { ...state.ui, serverOpen: true } }))}>
        {firstRun ? 'Join address and code' : 'Join code'}</Button> : null}</div>
    {refreshError ? <p className="t-caption" aria-live="polite">{refreshError}</p> : null}
  </section>;
}
