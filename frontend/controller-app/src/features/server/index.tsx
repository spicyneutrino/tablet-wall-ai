import { useEffect, useState } from 'react';
import { SideSheet } from '../../ui/SideSheet';
import { Button } from '../../ui/Button';
import { useWallStore } from '../../state/hooks';
import { OperatorConfigSchema } from '../../api/readiness';
import { useShell } from '../preview/ShellContext';
import EmptyWall from '../sources/layouts/EmptyWall';
import Playback from '../playback';

export default function Server() {
  const { store, session } = useShell();
  const open = useWallStore(store, state => state.ui.serverOpen);
  const server = useWallStore(store, state => state.server);
  const [join, setJoin] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState('');
  useEffect(() => {
    if (!open) return;
    let active = true;
    void session.request('GET', '/operator-config', undefined, { parse: OperatorConfigSchema }).then(result => {
      if (active && result.kind === 'ok') setJoin(result.value.tablet_origin);
    });
    return () => { active = false; };
  }, [open, session]);
  return <SideSheet title="Server" open={open} onOpenChange={serverOpen => store.setState(state => ({ ui: { ...state.ui, serverOpen } }))}>
    <div className="server-placeholder">
      <section className="shell-slot"><h3 className="t-heading">Connection</h3><p className="t-body">{server.transportText}</p>
        <Button variant="secondary" className="justify-self-start" onClick={() => {
          setRefreshError('');
          void session.refresh().catch(error => setRefreshError(error instanceof Error ? error.message : 'Status is still unavailable. Try again.'));
        }}>Refresh status</Button>
        {refreshError ? <p className="t-caption" aria-live="polite">{refreshError}</p> : null}</section>
      <section className="shell-slot"><h3 className="t-heading">Joining</h3>
        {join ? <><p className="t-body">Open this address on each tablet.</p><a className="link join-address" href={`${join}/client/`}>{join}/client/</a>
          <img src="/api/v3/join-qr" alt="QR code for joining the tablet wall" width="160" height="160" /></>
          : <p className="t-body">The tablet join address is unavailable. Check the server’s joining configuration.</p>}</section>
      <Playback /><EmptyWall />
    </div>
  </SideSheet>;
}
