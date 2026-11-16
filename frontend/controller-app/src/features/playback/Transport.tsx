import { useId, useState } from 'react';
import type { ReactNode } from 'react';
import { CircleCheck, LoaderCircle, Pause, Play, RotateCcw, SkipBack, SkipForward, Square, TriangleAlert } from 'lucide-react';
import type { DeviceId } from '../../api/devices';
import type { ManagedAsset } from '../../api/images';
import { playbackOutcomeMessage, pollPlayback, sendTransport } from '../../state/commands/playback';
import type { Transport as Action } from '../../state/commands/playback';
import { useWallStore } from '../../state/hooks';
import { Button } from '../../ui/Button';
import { useShell } from '../preview/ShellContext';
import { isActive, participants, position, stateView, startReason } from './model';
import StartDialog from './StartDialog';
import { useTabletName } from './useTabletName';

const ICONS = { ok: CircleCheck, warn: LoaderCircle, err: TriangleAlert, muted: Square } as const;

export default function Transport({ assets, pollError }: { assets: ManagedAsset[]; pollError: string }) {
  const { store, session } = useShell();
  const status = useWallStore(store, state => state.playback.status);
  const server = useWallStore(store, state => state.server);
  const playlist = useWallStore(store, state => state.playlist);
  const nameOf = useTabletName();
  const [working, setWorking] = useState<Action | null>(null);
  const [message, setMessage] = useState('');
  const [starting, setStarting] = useState(false);
  const headingId = useId();
  const captionId = useId();
  const active = isActive(status);
  const view = stateView(status);
  const StateIcon = view.tone === 'muted' && status?.state === 'paused' ? Pause : view.tone === 'ok' && status?.state === 'playing' ? Play : ICONS[view.tone];
  const layout = server.config?.layout;
  const reason = startReason({ layout, saved: !!playlist.saved && !playlist.dirty, supported: server.supported, uncertain: server.uncertain });
  const where = position(status);
  const shown = where && active ? assets.find(asset => asset.id === (status.live.displayed ?? status.live.current)?.asset)?.name : undefined;
  const names = (ids: readonly DeviceId[]) => ids.map(nameOf).join(', ');

  async function send(action: Action) {
    if (working) return;
    setWorking(action);
    setMessage('');
    const outcome = await sendTransport(store, session, action);
    setWorking(null);
    setMessage(playbackOutcomeMessage(outcome));
    if (outcome.kind !== 'ok') void pollPlayback(store, session);
  }
  const wait = !!working;
  function labelled(action: Action, label: string, busyLabel: string, icon: ReactNode, variant: 'primary' | 'secondary', size?: 'lg') {
    return working === action
      ? <Button variant={variant} size={size} busy busyLabel={busyLabel}>{icon}{label}</Button>
      : <Button variant={variant} size={size} aria-disabled={wait || undefined} onClick={() => void send(action)}>{icon}{label}</Button>;
  }
  const step = (action: 'previous' | 'next', label: string, icon: ReactNode) =>
    <Button variant="ghost" size="icon" aria-label={label} aria-disabled={!active || wait || undefined}
      aria-describedby={active ? undefined : captionId} onClick={() => void send(action)}>{icon}</Button>;

  return <section className="playback-block" aria-labelledby={headingId}>
    <div className="playback-head">
      <h3 id={headingId} className="t-heading">Playback</h3>
      <span className={`state state-${view.tone}`} aria-live="polite"><StateIcon className={view.tone === 'warn' ? 'spin' : undefined} aria-hidden="true" />{view.label}</span>
    </div>
    <div className="playback-transport">
      {!active
        ? reason ? <Button size="lg" aria-disabled aria-describedby={captionId}><Play aria-hidden="true" />Start</Button>
          : <Button size="lg" onClick={() => { setMessage(''); setStarting(true); }}><Play aria-hidden="true" />Start</Button>
        : status.state === 'paused' ? labelled('resume', 'Resume', 'Resuming…', <Play aria-hidden="true" />, 'primary', 'lg')
          : labelled('pause', 'Pause', 'Pausing…', <Pause aria-hidden="true" />, 'primary', 'lg')}
      {active ? labelled('stop', 'Stop', 'Stopping…', <Square aria-hidden="true" />, 'secondary') : null}
      {active && status.state === 'blocked' ? labelled('retry', 'Retry', 'Retrying…', <RotateCcw aria-hidden="true" />, 'secondary') : null}
      {step('previous', 'Previous item', <SkipBack aria-hidden="true" />)}
      {step('next', 'Next item', <SkipForward aria-hidden="true" />)}
    </div>
    <p id={captionId} className="t-caption">{reason && !active ? reason : active
      ? `${where ? `Showing item ${where.index + 1}${shown ? `, ${shown}` : ''}${where.loop ? `, loop ${where.loop + 1}` : ''}. ` : ''}Policy ${status.policy}.`
      : `Starts at item 1 with ${participants(layout).length} ${participants(layout).length === 1 ? 'tablet' : 'tablets'} on the wall. Each image is a hard cut.`}</p>
    {active && status.state === 'blocked' ? <div className="note note-err" role="alert">
      <p className="note-title"><TriangleAlert aria-hidden="true" />Playback is blocked</p>
      <p className="t-body">{status.blocked_reason ?? 'A tablet did not get ready.'} Fix the tablet, then choose Retry.</p></div> : null}
    {active && status.state === 'failed' ? <div className="note note-err" role="alert">
      <p className="note-title"><TriangleAlert aria-hidden="true" />Playback failed</p>
      <p className="t-body">Choose Stop, then Start again.</p></div> : null}
    {active && (status.excluded.length || status.missed.length) ? <p className="t-caption">
      {status.excluded.length ? `Left out: ${names(status.excluded)}. ` : ''}{status.missed.length ? `Skipped: ${names(status.missed)}.` : ''}</p> : null}
    {message ? <p className="t-body text-err" role="alert">{message}</p> : null}
    {pollError ? <p className="t-caption" role="status">{pollError}</p> : null}
    <StartDialog open={starting} onOpenChange={setStarting} />
  </section>;
}
