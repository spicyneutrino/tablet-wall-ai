import { useEffect, useState } from 'react';
import type { Media } from '../../api/images';
import { loadMedia, loadPlaylist, pollPlayback } from '../../state/commands/playback';
import { Button } from '../../ui/Button';
import { useShell } from '../preview/ShellContext';
import { readFailure } from '../server/model';
import type { Load } from '../server/model';
import PlaylistEditor from './PlaylistEditor';
import Transport from './Transport';
import './playback.css';

const loading = { kind: 'loading' } as const;

/** Mounted by the Server panel only while the opt-in switch is on, so the poll below stops with it. */
export default function Playback() {
  const { store, session } = useShell();
  const [media, setMedia] = useState<Load<Media>>(loading);
  const [playlist, setPlaylist] = useState<Load<null>>(loading);
  const [attempt, setAttempt] = useState(0);
  const [pollError, setPollError] = useState('');

  useEffect(() => {
    let active = true;
    void Promise.all([loadMedia(session), loadPlaylist(store, session)]).then(([images, saved]) => {
      if (!active) return;
      setMedia(images.kind === 'ok' ? { kind: 'ready', value: images.value } : { kind: 'error', message: readFailure(images, 'The image list') });
      setPlaylist(saved.kind === 'ok' ? { kind: 'ready', value: null } : { kind: 'error', message: readFailure(saved, 'The playlist') });
    });
    return () => { active = false; };
  }, [store, session, attempt]);

  useEffect(() => {
    let inflight = false;
    async function tick() {
      if (document.visibilityState !== 'visible' || inflight) return;
      inflight = true;
      try {
        const outcome = await pollPlayback(store, session);
        setPollError(outcome.kind === 'ok' ? '' : 'Playback status is unavailable. This page keeps trying every second.');
      } finally { inflight = false; }
    }
    void tick();
    const timer = window.setInterval(() => void tick(), 1000);
    document.addEventListener('visibilitychange', tick);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', tick); };
  }, [store, session]);

  function reload() {
    setMedia(loading);
    setPlaylist(loading);
    setAttempt(value => value + 1);
  }

  const failed = media.kind === 'error' ? media.message : playlist.kind === 'error' ? playlist.message : '';
  return <div className="playback">
    <Transport assets={media.kind === 'ready' ? media.value.assets : []} pollError={pollError} />
    {failed ? <section className="playback-block" aria-label="Playlist">
      <p className="t-body">{failed}</p>
      <Button variant="ghost" className="justify-self-start" onClick={reload}>Try again</Button>
    </section> : <PlaylistEditor media={media} ready={playlist.kind === 'ready'} />}
  </div>;
}
