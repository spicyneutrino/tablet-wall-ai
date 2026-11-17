import { ChevronRight, CircleMinus, Replace, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import type { DeviceId } from '../../api/devices';
import type { ImpactPreview, RebindCommand, RebindPreview } from '../../api/lifecycle';
import { entries } from '../../domain/layout';
import {
  applyReplacement, disabledWhen, finishLifecycle, forgetTablet, lifecycleMessage, newTablets, numberProblem, offlineTablets,
  playbackNote, previewReplacement, readImpact, rebindCommand, removePlacement, replacementPair, staleReason, conflictText,
  unsavedBlock, wallBlock,
} from '../../state/commands/lifecycle';
import type { Hardware, Pair, ReplaceChoices } from '../../state/commands/lifecycle';
import { useWallStore } from '../../state/hooks';
import { Button } from '../../ui/Button';
import { Field } from '../../ui/Field';
import { Input, Select, Switch } from '../../ui/Input';
import { Label } from '../../ui/Label';
import { ModalDialog } from '../../ui/ModalDialog';
import { useTabletName } from '../playback/useTabletName';
import { useShell } from '../preview/ShellContext';
import { useShellView } from '../preview/useShellView';

type ImpactState = { id: DeviceId } & ({ status: 'loading' } | { status: 'failed'; message: string } | { status: 'ready'; impact: ImpactPreview });

function failure(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

/** Reads what a change would touch before anything is written. The result belongs to one tablet id. */
function useImpact(id: DeviceId) {
  const { session } = useShell();
  const [state, setState] = useState<ImpactState>({ id, status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let current = true;
    readImpact(session, id).then(outcome => {
      if (current) setState(outcome.kind === 'ok' ? { id, status: 'ready', impact: outcome.value }
        : { id, status: 'failed', message: lifecycleMessage(outcome) });
    }, (error: unknown) => {
      if (current) setState({ id, status: 'failed', message: failure(error, 'Could not read what this changes.') });
    });
    return () => { current = false; };
  }, [session, id, attempt]);
  return {
    state: state.id === id ? state : { id, status: 'loading' } as const,
    again: () => { setState({ id, status: 'loading' }); setAttempt(count => count + 1); },
  };
}

type Confirm = { busy: true; busyLabel: string } | { disabled: true; disabledReason: string } | Record<string, never>;
function confirmProps(working: boolean, workingLabel: string, block: string): Confirm {
  return working ? { busy: true, busyLabel: workingLabel } : block ? { disabled: true, disabledReason: block } : {};
}

function Names({ items }: { items: readonly { name: string }[] }) {
  return <>{items.map(item => item.name).join(', ')}</>;
}

function Stale({ reason, again }: { reason: string; again: () => void }) {
  return <div className="note note-warn" role="alert">
    <p className="t-body">{reason}</p>
    <Button variant="secondary" className="justify-self-start" onClick={again}>Review again</Button>
  </div>;
}

function Loading({ state, again }: { state: ImpactState; again: () => void }) {
  if (state.status === 'loading') return <p className="t-body" role="status">Reading what this changes…</p>;
  if (state.status !== 'failed') return null;
  return <div className="lifecycle-dialog">
    <p className="t-body text-err" role="alert">{state.message}</p>
    <Button variant="secondary" className="justify-self-start" onClick={again}>Try again</Button>
  </div>;
}

type DialogProps = { open: boolean; onOpenChange: (open: boolean) => void };

function LifecycleDialog({ open, onOpenChange, title, working, children }: DialogProps & { title: string; working: boolean; children: ReactNode }) {
  return <ModalDialog open={open} onOpenChange={onOpenChange} title={title}
    onCancel={event => { if (working) event.preventDefault(); }} onClose={event => event.stopPropagation()}>
    {open ? <div className="lifecycle-dialog">{children}</div> : null}
  </ModalDialog>;
}

function Actions({ working, onCancel, children }: { working: boolean; onCancel: () => void; children: ReactNode }) {
  return <div className="lifecycle-buttons">
    <Button variant="ghost" autoFocus aria-disabled={working || undefined} onClick={onCancel}>Cancel</Button>
    {children}
  </div>;
}

function RemoveDialog({ id, open, onOpenChange }: DialogProps & { id: DeviceId }) {
  const [working, setWorking] = useState(false);
  return <LifecycleDialog open={open} onOpenChange={onOpenChange} working={working}
    title={`Remove ${useTabletName()(id)} from the wall?`}>
    <RemoveBody id={id} onOpenChange={onOpenChange} working={working} setWorking={setWorking} />
  </LifecycleDialog>;
}

type BodyProps = { onOpenChange: (open: boolean) => void; working: boolean; setWorking: (working: boolean) => void };

function RemoveBody({ id, onOpenChange, working, setWorking }: BodyProps & { id: DeviceId }) {
  const { store, session } = useShell();
  const nameOf = useTabletName(), name = nameOf(id);
  const server = useWallStore(store, state => state.server);
  const config = useWallStore(store, state => state.server.config);
  const { state, again } = useImpact(id);
  const [error, setError] = useState('');
  const impact = state.status === 'ready' ? state.impact : null;
  const stale = impact ? staleReason({ kind: 'remove', id, impact }, server, nameOf) : null;
  const block = !impact ? 'Reading what this changes…' : !impact.active_entry ? `${name} is not on the wall.`
    : stale ? 'Review again first.' : wallBlock(server);
  const stops = playbackNote(config);
  async function confirm() {
    if (!impact || block || working) return;
    setWorking(true);
    setError('');
    try {
      const outcome = await removePlacement(session, id, impact.etag);
      if (outcome.kind === 'ok') {
        finishLifecycle(store, { notice: `${name} is off the wall. It is still registered, and saved layouts keep its place.`, select: id, gone: [] });
        onOpenChange(false);
      } else setError(lifecycleMessage(outcome));
    } catch (problem) { setError(failure(problem, 'The change may not have been made. Refresh status.')); } finally { setWorking(false); }
  }
  return <>
    <Loading state={state} again={again} />
    {impact ? <>
      <p className="t-body">{name} leaves the wall. It stays registered, and its name, number and measurements are kept. You can place it again in Edit layout.</p>
      {impact.saved_layouts.length ? <p className="t-body">Saved layouts that include it keep its place: <Names items={impact.saved_layouts} />.</p> : null}
      {stops ? <p className="t-body">{stops}</p> : null}
      {stale ? <Stale reason={stale} again={again} /> : null}
    </> : null}
    {error ? <p className="t-body text-err" role="alert">{error}</p> : null}
    <Actions working={working} onCancel={() => onOpenChange(false)}>
      <Button variant="danger-solid" {...confirmProps(working, 'Removing…', block)} onClick={() => void confirm()}>Remove from wall</Button>
    </Actions>
  </>;
}

function ForgetDialog({ id, open, onOpenChange }: DialogProps & { id: DeviceId }) {
  const [working, setWorking] = useState(false);
  return <LifecycleDialog open={open} onOpenChange={onOpenChange} working={working}
    title={`Forget ${useTabletName()(id)}?`}>
    <ForgetBody id={id} onOpenChange={onOpenChange} working={working} setWorking={setWorking} />
  </LifecycleDialog>;
}

function ForgetBody({ id, onOpenChange, working, setWorking }: BodyProps & { id: DeviceId }) {
  const { store, session } = useShell();
  const nameOf = useTabletName(), name = nameOf(id);
  const server = useWallStore(store, state => state.server);
  const config = useWallStore(store, state => state.server.config);
  const { state, again } = useImpact(id);
  const [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState('');
  const impact = state.status === 'ready' ? state.impact : null;
  const stale = impact ? staleReason({ kind: 'forget', id, impact }, server, nameOf) : null;
  const onWall = !!impact?.active_entry;
  const block = !impact ? 'Reading what this changes…' : stale ? 'Review again first.'
    : onWall && !acknowledged ? 'Switch on “Also remove it from the wall” to continue.' : wallBlock(server);
  const stops = playbackNote(config);
  async function confirm() {
    if (!impact || block || working) return;
    setWorking(true);
    setError('');
    try {
      const outcome = await forgetTablet(session, id, impact.etag, onWall);
      if (outcome.kind === 'ok') {
        finishLifecycle(store, { notice: `${name} was forgotten. Saved layouts and measurement history were kept.`, select: null, gone: [id] });
        onOpenChange(false);
      } else setError(lifecycleMessage(outcome));
    } catch (problem) { setError(failure(problem, 'The change may not have been made. Refresh status.')); } finally { setWorking(false); }
  }
  return <>
    <Loading state={state} again={again} />
    {impact ? <>
      <p className="t-body"><strong>This cannot be undone.</strong> Forgetting {name} deletes its registration. Its name and number are released.</p>
      <p className="t-body">If its page is opened on the tablet again, it joins as a new tablet.</p>
      {onWall ? <Label className="lifecycle-switch">
        <Switch checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} />
        <span className="lifecycle-copy"><span>Also remove it from the wall</span>
          <span className="t-caption t-muted">{name} is placed on the wall now. Forgetting it takes that place away.</span></span>
      </Label> : <p className="t-body">It is not on the wall.</p>}
      <p className="t-body">{impact.saved_layouts.length
        ? <>Saved layouts that include it keep its reserved place: <Names items={impact.saved_layouts} />.</>
        : 'No saved layout includes it.'}{impact.has_measurement_history ? ' Its measurement history is kept.' : ''}</p>
      {stops ? <p className="t-body">{stops}</p> : null}
      {stale ? <Stale reason={stale} again={again} /> : null}
    </> : null}
    {error ? <p className="t-body text-err" role="alert">{error}</p> : null}
    <Actions working={working} onCancel={() => onOpenChange(false)}>
      <Button variant="danger-solid" {...confirmProps(working, 'Forgetting…', block)} onClick={() => void confirm()}>Forget tablet</Button>
    </Actions>
  </>;
}

type Preview = { command: RebindCommand; preview: RebindPreview; connection: number };

export function ReplaceDialog({ newId, oldId, open, onOpenChange }: DialogProps & { newId: DeviceId; oldId: DeviceId }) {
  const [working, setWorking] = useState(false);
  const nameOf = useTabletName();
  return <LifecycleDialog open={open} onOpenChange={onOpenChange} working={working}
    title={`Put ${nameOf(newId)} in an offline tablet’s place?`}>
    <ReplaceBody newId={newId} initialOld={oldId} onOpenChange={onOpenChange} working={working} setWorking={setWorking} />
  </LifecycleDialog>;
}

const HARDWARE = {
  same_hardware: 'Same tablet, new browser. Its measurements are copied over.',
  different_hardware: 'A different tablet. It will need its own measurements.',
} as const;

function ReplaceBody({ newId, initialOld, onOpenChange, working, setWorking }: BodyProps & { newId: DeviceId; initialOld: DeviceId }) {
  const { store, session } = useShell();
  const nameOf = useTabletName();
  const server = useWallStore(store, state => state.server);
  const config = useWallStore(store, state => state.server.config);
  const [oldId, setOldId] = useState(initialOld);
  const { state, again } = useImpact(oldId);
  const [choices, setChoices] = useState<ReplaceChoices>({ hardware: '', active: true, transferLabel: true, number: '', saved: {} });
  const [preview, setPreview] = useState<Preview | null>(null);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState('');
  const impact = state.status === 'ready' ? state.impact : null;
  const oldName = nameOf(oldId), newName = nameOf(newId);
  const onWall = !!impact?.active_entry;
  const offline = offlineTablets(server.roster, newId);
  const resolved: ReplaceChoices = { ...choices, active: onWall && choices.active,
    saved: Object.fromEntries((impact?.saved_layouts ?? []).map(item => [item.name, item.valid && (choices.saved[item.name] ?? true)])) };
  const command = impact ? rebindCommand(oldId, resolved, impact.saved_layouts) : null;
  const problem = numberProblem(choices.number);
  const stale = preview ? staleReason({ kind: 'replace', oldId, newId, preview: preview.preview, connection: preview.connection }, server, nameOf) : null;
  const conflicts = preview?.preview.conflicts.map(conflict => conflictText(conflict, { old: oldName, new: newName })) ?? [];
  const stops = playbackNote(config);

  function change(next: Partial<ReplaceChoices>) {
    setChoices(current => ({ ...current, ...next }));
    setPreview(null);
    setError('');
  }
  async function review() {
    if (!command || !server.etag || reading) return;
    setReading(true);
    setError('');
    const connection = server.connectionVersions[newId] ?? 0;
    try {
      const outcome = await previewReplacement(session, newId, command, server.etag);
      if (outcome.kind === 'ok') setPreview({ command, preview: outcome.value, connection });
      else setError(lifecycleMessage(outcome));
    } catch (failed) { setError(failure(failed, 'Could not review the replacement. Refresh status.')); } finally { setReading(false); }
  }
  async function confirm() {
    if (!preview || stale || conflicts.length || working) return;
    setWorking(true);
    setError('');
    try {
      const outcome = await applyReplacement(session, newId, preview.command, preview.preview);
      if (outcome.kind === 'ok') {
        const label = preview.preview.label_after || (preview.preview.number_after ? `Tablet ${preview.preview.number_after}` : newName);
        finishLifecycle(store, { notice: `${label} replaced ${oldName}${preview.preview.affected_active ? ' and took its place on the wall' : ''}.`,
          select: newId, gone: [oldId] });
        onOpenChange(false);
      } else setError(lifecycleMessage(outcome));
    } catch (failed) { setError(failure(failed, 'The change may not have been made. Refresh status.')); } finally { setWorking(false); }
  }

  if (preview) {
    const { preview: result } = preview;
    return <>
      <p className="t-body">Review what changes. Nothing is saved until you confirm.</p>
      <ul className="lifecycle-list">
        <li>{result.affected_active ? `${newName} takes ${oldName}’s place on the wall.` : 'The wall’s layout is not changed.'}</li>
        <li>{result.affected_saved.length ? <>Saved layouts updated to use it: <Names items={result.affected_saved} />.</> : 'No saved layout is updated.'}</li>
        {result.untouched_saved.length ? <li>Saved layouts left as they are, still pointing at {oldName}: <Names items={result.untouched_saved} />.</li> : null}
        <li>Name afterwards: {result.label_after ?? 'the generated name'}. Number afterwards: {result.number_after ?? 'none'}.</li>
        <li>{preview.command.hardware === 'same_hardware'
          ? Object.keys(result.profile_revision_map).length ? `${oldName}’s measurements are copied to ${newName}.` : 'There are no measurements to copy.'
          : `${newName} will need its own measurements.`}</li>
        <li>{oldName} is removed from the tablet list. {newName} reconnects once to take its place.</li>
        {stops ? <li>{stops}</li> : null}
      </ul>
      {conflicts.length ? <div className="note note-err" role="alert">
        <p className="t-body">This replacement cannot go ahead.</p>
        <ul className="lifecycle-list">{conflicts.map(text => <li key={text}>{text}</li>)}</ul>
      </div> : null}
      {stale ? <Stale reason={stale} again={() => setPreview(null)} /> : null}
      {error ? <p className="t-body text-err" role="alert">{error}</p> : null}
      <ReviewActions working={working} onCancel={() => onOpenChange(false)} onBack={() => setPreview(null)}>
        <Button {...confirmProps(working, 'Replacing…', conflicts.length ? 'Fix the problems above first.' : stale ? 'Review again first.' : wallBlock(server))}
          onClick={() => void confirm()}>Replace {oldName}</Button>
      </ReviewActions>
    </>;
  }

  const hint = !impact ? 'Reading what this changes…' : !choices.hardware ? 'Say whether it is the same tablet.' : problem ?? wallBlock(server);
  return <>
    <p className="t-body">{newName} is online and not on the wall. Only an offline tablet can be replaced.</p>
    <Field label="Replace">
      {props => <Select {...props} value={oldId} onChange={event => { setOldId(event.target.value as DeviceId); setChoices(current => ({ ...current, saved: {} })); setPreview(null); }}>
        {offline.map(id => <option key={id} value={id}>{nameOf(id)}</option>)}
      </Select>}
    </Field>
    <Field label="Is it the same tablet?" hint={choices.hardware ? HARDWARE[choices.hardware] : undefined}>
      {props => <Select {...props} value={choices.hardware} onChange={event => change({ hardware: event.target.value as Hardware | '' })}>
        <option value="">Choose one</option>
        <option value="same_hardware">Same tablet, new browser</option>
        <option value="different_hardware">A different tablet</option>
      </Select>}
    </Field>
    <Loading state={state} again={again} />
    {impact ? <>
      <div className="lifecycle-switches">
        {onWall ? <Label className="lifecycle-switch"><Switch checked={choices.active} onChange={event => change({ active: event.target.checked })} />
          <span className="lifecycle-copy"><span>Take its place on the wall</span><span className="t-caption t-muted">{oldName} is on the wall now.</span></span></Label> : null}
        <Label className="lifecycle-switch"><Switch checked={choices.transferLabel} onChange={event => change({ transferLabel: event.target.checked })} />
          <span className="lifecycle-copy"><span>Keep {oldName}’s name</span></span></Label>
        {impact.saved_layouts.map(item => <Label key={item.name} className="lifecycle-switch">
          <Switch checked={item.valid && (choices.saved[item.name] ?? true)} disabled={!item.valid}
            onChange={event => change({ saved: { ...choices.saved, [item.name]: event.target.checked } })} />
          <span className="lifecycle-copy"><span>Update saved layout “{item.name}”</span>
            <span className="t-caption t-muted">{item.valid ? 'It includes this tablet.' : 'It is damaged, so it cannot be updated.'}</span></span>
        </Label>)}
      </div>
      <Field label="Number (optional)" hint="Leave empty to keep the old number." error={problem ?? undefined}>
        {props => <Input {...props} inputMode="numeric" autoComplete="off" value={choices.number}
          onChange={event => change({ number: event.target.value })} />}
      </Field>
    </> : null}
    {error ? <p className="t-body text-err" role="alert">{error}</p> : null}
    <Actions working={working} onCancel={() => onOpenChange(false)}>
      <Button variant="secondary" {...(reading ? { busy: true as const, busyLabel: 'Reviewing…' } : !command || wallBlock(server) || !offline.length
        ? { disabled: true as const, disabledReason: hint || 'Review is not available yet.' } : {})} onClick={() => void review()}>Review replacement</Button>
    </Actions>
  </>;
}

function ReviewActions({ working, onCancel, onBack, children }: { working: boolean; onCancel: () => void; onBack: () => void; children: ReactNode }) {
  return <div className="lifecycle-buttons">
    <Button key="cancel" variant="ghost" autoFocus aria-disabled={working || undefined} onClick={onCancel}>Cancel</Button>
    <Button key="back" variant="ghost" aria-disabled={working || undefined} onClick={onBack}>Back</Button>
    {children}
  </div>;
}

type Which = 'remove' | 'forget' | 'replace';

export default function Lifecycle() {
  const { store } = useShell();
  const { tablets, server, config } = useShellView();
  const id = useWallStore(store, state => state.ui.drill ?? state.ui.selected);
  const forms = useWallStore(store, state => state.forms);
  const nameOf = useTabletName();
  const [which, setWhich] = useState<Which | null>(null);
  const [target, setTarget] = useState<Pair | null>(null);
  const tablet = tablets.find(item => item.id === id);
  if (!id || !tablet || !config) return null;
  const online = server.roster[id]?.online === true;
  const placed = id in entries(config.layout);
  const name = nameOf(id);
  const wall = wallBlock(server);
  const offer = replacementPair(config, server.roster);
  const fresh = newTablets(config, server.roster);
  const pair = online
    ? !placed ? { newId: id, oldId: offer?.newId === id ? offer.oldId : offlineTablets(server.roster, id)[0] } : null
    : fresh.length ? { newId: fresh.at(-1)!, oldId: id } : null;
  const replaceReason = !online ? pair ? '' : 'No new tablet has joined. Open the wall address on the new tablet first.'
    : placed ? 'Only an offline tablet can be replaced.'
      : pair?.oldId ? '' : 'No tablet is offline, so there is nothing to replace.';
  const unsaved = unsavedBlock(forms, [id, ...pair ? [pair.newId] : [], ...pair?.oldId ? [pair.oldId] : []]);
  const removeReason = !placed ? `${name} is not on the wall.` : wall;
  const forgetReason = online ? 'Forget needs the tablet offline. Remove from wall keeps its registration.' : wall || unsaved;
  const replaceBlock = replaceReason || wall || unsaved;
  return <>
    <details className="tablet-lifecycle" key={id} open={!!pair?.oldId}>
      <summary><ChevronRight className="chev" aria-hidden="true" />Replace or remove</summary>
      <div className="lifecycle-actions">
        <Button variant="secondary" {...disabledWhen(removeReason)} onClick={() => setWhich('remove')}>
          <CircleMinus aria-hidden="true" />Remove from wall</Button>
        <Button variant="secondary" {...disabledWhen(replaceBlock)} onClick={() => { if (pair?.oldId) setTarget({ newId: pair.newId, oldId: pair.oldId }); setWhich('replace'); }}>
          <Replace aria-hidden="true" />{online ? 'Use this tablet as a replacement' : 'Replace with a new tablet'}</Button>
        <Button variant="danger" {...disabledWhen(forgetReason)} onClick={() => setWhich('forget')}>
          <Trash2 aria-hidden="true" />Forget tablet</Button>
      </div>
    </details>
    <RemoveDialog id={id} open={which === 'remove'} onOpenChange={open => setWhich(open ? 'remove' : null)} />
    <ForgetDialog id={id} open={which === 'forget'} onOpenChange={open => setWhich(open ? 'forget' : null)} />
    {target ? <ReplaceDialog newId={target.newId} oldId={target.oldId} open={which === 'replace'}
      onOpenChange={open => setWhich(open ? 'replace' : null)} /> : null}
  </>;
}
