import { useEffect, useMemo, useState } from 'react';
import type { DeviceId } from '../../api/devices';
import { playbackOutcomeMessage, startPlayback } from '../../state/commands/playback';
import { useWallStore } from '../../state/hooks';
import { Button } from '../../ui/Button';
import { Field } from '../../ui/Field';
import { Select, Switch } from '../../ui/Input';
import { Label } from '../../ui/Label';
import { ModalDialog } from '../../ui/ModalDialog';
import { useShell } from '../preview/ShellContext';
import { participants } from './model';
import { useTabletName } from './useTabletName';

const EXCLUSIONS_KEY = 'tablet-wall-playback-exclusions-v1';
const POLICIES = {
  '': 'The server picks online, or strict when the playlist has a video.',
  online: 'Waits a moment for tablets, then skips any that miss a cut and keeps going.',
  strict: 'Every tablet in the show must be ready for each cut, or playback blocks.',
} as const;
type Policy = keyof typeof POLICIES;

function storedExclusions(): string[] {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(EXCLUSIONS_KEY) ?? '[]');
    return Array.isArray(value) ? value.filter((id): id is string => typeof id === 'string') : [];
  } catch { return []; }
}

function storeExclusions(ids: readonly string[]) {
  try { sessionStorage.setItem(EXCLUSIONS_KEY, JSON.stringify(ids)); } catch { /* the choice then lasts for this visit only */ }
}

export default function StartDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { store, session } = useShell();
  const layout = useWallStore(store, state => state.server.config?.layout);
  const roster = useWallStore(store, state => state.server.roster);
  const saved = useWallStore(store, state => state.playlist.saved);
  const exclusions = useWallStore(store, state => state.playback.exclusions);
  const nameOf = useTabletName();
  const [policy, setPolicy] = useState<Policy>('');
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const eligible = useMemo(() => participants(layout), [layout]);
  const ordered = [...eligible].sort((left, right) => nameOf(left).localeCompare(nameOf(right), undefined, { numeric: true }));
  const included = eligible.filter(id => !exclusions.includes(id));

  useEffect(() => {
    if (!open) return;
    const keep = storedExclusions().filter((id): id is DeviceId => eligible.some(candidate => candidate === id));
    store.setState(state => ({ playback: { ...state.playback, exclusions: keep } }));
  }, [open, eligible, store]);

  function toggle(id: DeviceId, include: boolean) {
    const next = include ? exclusions.filter(excluded => excluded !== id) : [...exclusions, id];
    storeExclusions(next);
    store.setState(state => ({ playback: { ...state.playback, exclusions: next } }));
  }

  async function confirm() {
    setWorking(true);
    setError('');
    const outcome = await startPlayback(store, session, { policy: policy || null, exclusions: eligible.filter(id => exclusions.includes(id)) });
    setWorking(false);
    if (outcome.kind === 'ok') onOpenChange(false);
    else setError(playbackOutcomeMessage(outcome));
  }

  const count = saved?.items.length ?? 0;
  return <ModalDialog open={open} onOpenChange={onOpenChange} title="Start playback" onClose={event => event.stopPropagation()}>
    <div className="playback-dialog">
      <p className="t-body">Plays {count} {count === 1 ? 'image' : 'images'} in order as hard cuts{saved?.loop ? ', then starts again' : ', then stops on the last one'}.</p>
      <Field label="If a tablet is not ready" hint={POLICIES[policy]}>
        {props => <Select {...props} value={policy} onChange={event => setPolicy(event.target.value as Policy)}>
          <option value="">Server default</option>
          <option value="online">Online: skip tablets that miss a cut</option>
          <option value="strict">Strict: wait for every tablet</option>
        </Select>}
      </Field>
      <fieldset className="playback-tablets">
        <legend className="t-label">Tablets in this show</legend>
        {ordered.map(id => <Label key={id} className="playback-tablet">
          <Switch checked={!exclusions.includes(id)} onChange={event => toggle(id, event.target.checked)} />
          <span className="playback-copy"><span>{nameOf(id)}</span>
            <span className="t-caption">{roster[id]?.online ? 'Online' : 'Offline. Skipped under the online policy.'}</span></span>
        </Label>)}
      </fieldset>
      {error ? <p className="t-body text-err" role="alert">{error}</p> : null}
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="ghost" autoFocus onClick={() => onOpenChange(false)}>Cancel</Button>
        {working ? <Button busy busyLabel="Starting…">Start playback</Button>
          : included.length ? <Button onClick={() => void confirm()}>Start playback</Button>
            : <Button disabled disabledReason="Include at least one tablet.">Start playback</Button>}
      </div>
    </div>
  </ModalDialog>;
}
