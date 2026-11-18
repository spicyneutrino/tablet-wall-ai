import { useCallback, useEffect, useId, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { clsx } from 'clsx';
import { History, MoreHorizontal, Save, TriangleAlert } from 'lucide-react';
import type { Layout } from '../../../api/layouts';
import { bounds } from '../../../domain/layout';
import type { Layout as LayoutDoc } from '../../../domain/layout';
import { panels } from '../../../domain/stagePanels';
import type { PanelProfile } from '../../../domain/stagePanels';
import { snapshotName } from '../../../domain/names';
import { useWallStore } from '../../../state/hooks';
import {
  SNAPSHOT_NAME_RULE, applyArrangement, deleteArrangement, loadSavedArrangements, needsKindConfirmation,
  outcomeMessage, previewArrangement, saveArrangement,
} from '../../../state/commands/savedLayouts';
import type { SavedArrangement } from '../../../state/commands/savedLayouts';
import { Button } from '../../../ui/Button';
import { Field } from '../../../ui/Field';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from '../../../ui/DropdownMenu';
import { Input } from '../../../ui/Input';
import { ModalDialog } from '../../../ui/ModalDialog';
import type { CommandOutcome } from '../../../session/outcome';
import { useShell } from '../../preview/ShellContext';
import { useShellView } from '../../preview/useShellView';

type Message = { tone: 'ok' | 'err'; text: string };
type Confirmation = { kind: 'replace'; name: string } | { kind: 'delete'; entry: SavedArrangement }
  | { kind: 'kind'; entry: SavedArrangement };

const clock = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });

function LayoutThumb({ layout, profileFor }: { layout: Layout; profileFor: (id: string, revision?: number | string) => PanelProfile | null | undefined }) {
  const area = bounds(layout as unknown as LayoutDoc);
  const margin = Math.max(area.width, area.height) * 0.04;
  return <svg viewBox={`${area.x - margin} ${area.y - margin} ${area.width + margin * 2} ${area.height + margin * 2}`}
    width="120" height="76" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
    {panels(layout, profileFor).map(panel => panel.missing ? null : <rect key={panel.id} x={panel.body.x} y={panel.body.y}
      width={panel.body.width} height={panel.body.height} rx={2} fill="var(--stage-body)" stroke="var(--stage-sel)"
      strokeWidth={2} vectorEffect="non-scaling-stroke"
      transform={panel.angle ? `rotate(${panel.angle} ${panel.cx} ${panel.cy})` : undefined} />)}
  </svg>;
}

export default function SavedLayouts() {
  const { store, session } = useShell();
  const { profileFor } = useShellView();
  const config = useWallStore(store, state => state.server.config);
  const etagState = useWallStore(store, state => state.server.etagState);
  const busy = useWallStore(store, state => state.server.busy);
  const uncertain = useWallStore(store, state => state.server.uncertain);
  const supported = useWallStore(store, state => state.server.supported);
  const checkedAt = useWallStore(store, state => state.server.rosterCheckedAt);
  const unreachable = useWallStore(store, state => state.server.rosterUnreachable);
  const previous = useWallStore(store, state => state.server.config?.previous_layout_saved ?? null);
  const [entries, setEntries] = useState<SavedArrangement[] | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [message, setMessage] = useState<Message | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [saveError, setSaveError] = useState<string>();
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const [confirmError, setConfirmError] = useState<string>();
  const [working, setWorking] = useState(false);
  const baseId = useId();
  const stripRef = useRef<HTMLDivElement>(null);
  const loadedRef = useRef(false);
  const loadVersion = useRef(0);

  const publish = useCallback((version: number, outcome: CommandOutcome<SavedArrangement[]>) => {
    if (version !== loadVersion.current) return;
    if (outcome.kind === 'ok') {
      loadedRef.current = true;
      setEntries(outcome.value);
      setStatus('ready');
      return;
    }
    setStatus('error');
    setMessage({ tone: 'err', text: `${loadedRef.current
      ? 'Showing the last known saved arrangements. '
      : 'Saved arrangements could not be read. '}${outcomeMessage(outcome)}` });
  }, []);

  const refresh = useCallback(async () => {
    const version = ++loadVersion.current;
    publish(version, await loadSavedArrangements(session));
  }, [publish, session]);

  const ready = !!config;
  useEffect(() => {
    if (!ready) return;
    const version = ++loadVersion.current;
    void loadSavedArrangements(session).then(outcome => publish(version, outcome));
  }, [ready, publish, session]);

  useEffect(() => {
    if (!selected) return;
    stripRef.current?.querySelector(`[data-arrangement="${selected}"]`)
      ?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }, [selected]);

  const restore = previous && checkedAt ? { name: previous, at: new Date(checkedAt) }
    : previous ? { name: previous, at: new Date() } : null;

  const blocked = !config ? 'Waiting for the wall.' : uncertain ? 'Refresh status first.'
    : !supported ? 'Update the console before editing.' : busy ? 'Another change is in progress.'
      : etagState !== 'current' ? 'Refresh status first.' : null;
  const visible = entries?.filter(entry => entry.name !== restore?.name) ?? [];
  const restoreEntry = restore ? entries?.find(entry => entry.name === restore.name) : undefined;

  function select(entry: SavedArrangement) {
    if (!entry.valid) return;
    if (!previewArrangement(store, entry)) { setMessage({ tone: 'err', text: 'Waiting for the wall.' }); return; }
    setSelected(entry.name);
    setMessage(null);
  }

  function openSave() {
    setSaveName('');
    setSaveError(undefined);
    setSaveOpen(true);
  }

  function openConfirm(next: Confirmation) {
    setConfirmError(undefined);
    setConfirm(next);
  }

  async function persist(name: string, replace: boolean, where: 'save' | 'replace') {
    setWorking(true);
    const outcome = await saveArrangement(store, session, name, replace);
    setWorking(false);
    if (outcome.kind === 'ok') {
      setSaveOpen(false);
      setConfirm(null);
      setSaveName('');
      setMessage({ tone: 'ok', text: `Arrangement “${name}” ${replace ? 'replaced' : 'saved'}.` });
      void refresh();
      return;
    }
    const text = outcomeMessage(outcome);
    if (where === 'save') setSaveError(text); else setConfirmError(text);
  }

  function submitSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = snapshotName(saveName);
    if (name === null) {
      setSaveError(saveName.trim() ? SNAPSHOT_NAME_RULE : `Enter an arrangement name. ${SNAPSHOT_NAME_RULE}`);
      return;
    }
    const existing = entries?.some(entry => entry.name === name);
    if (existing) {
      setSaveOpen(false);
      openConfirm({ kind: 'replace', name });
      return;
    }
    void persist(name, false, 'save');
  }

  async function remove(entry: SavedArrangement) {
    setWorking(true);
    const outcome = await deleteArrangement(store, session, entry);
    setWorking(false);
    if (outcome.kind === 'ok') {
      setConfirm(null);
      setSelected(current => current === entry.name ? null : current);
      setMessage({ tone: 'ok', text: 'Saved arrangement deleted.' });
      void refresh();
      return;
    }
    setConfirmError(outcomeMessage(outcome));
  }

  async function apply(entry: SavedArrangement) {
    setWorking(true);
    const outcome = await applyArrangement(store, session, entry);
    setWorking(false);
    if (outcome.kind === 'ok') {
      setConfirm(null);
      setMessage({ tone: 'ok', text: `Arrangement “${entry.name}” recalled. Image unchanged.` });
      void refresh();
      return;
    }
    setConfirmError(outcomeMessage(outcome));
  }

  function requestApply(entry: SavedArrangement) {
    if (needsKindConfirmation(store, entry)) { openConfirm({ kind: 'kind', entry }); return; }
    void apply(entry);
  }

  function actions(entry: SavedArrangement) {
    return <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="secondary" size="icon" className="absolute right-1 top-1 h-6 w-6"
          aria-label={`Actions for ${entry.name}`} title={`Actions for ${entry.name}`}>
          <MoreHorizontal aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <DropdownMenuLabel>{entry.name}</DropdownMenuLabel>
        <DropdownMenuItem disabled={!!blocked || !entry.valid}
          onSelect={() => requestApply(entry)}>Apply layout</DropdownMenuItem>
        <DropdownMenuItem variant="danger" disabled={!!blocked}
          onSelect={() => openConfirm({ kind: 'delete', entry })}>Delete</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>;
  }

  function tile(entry: SavedArrangement, index: number) {
    const reasonId = `${baseId}-${index}`;
    return <div className="source-preview relative" key={entry.name} data-arrangement={entry.name}>
      <button type="button" className="src" title={entry.name} aria-pressed={selected === entry.name} disabled={!entry.valid}
        aria-describedby={entry.valid ? undefined : reasonId} onClick={() => select(entry)}>
        <span className="thumb dark">{entry.valid ? <LayoutThumb layout={entry.layout} profileFor={profileFor} />
          : <TriangleAlert aria-hidden="true" />}</span>
        <span className="src-name">{entry.name}</span>
      </button>
      {actions(entry)}
      {entry.valid ? null : <span id={reasonId} className="t-caption text-err">Damaged saved data. Delete it.</span>}
    </div>;
  }

  return <>
    <div className="relative h-[114px] min-w-0">
      <div ref={stripRef} className="source-strip absolute inset-0" role="group" aria-label="Saved arrangements" aria-busy={status === 'loading' || undefined}>
        {!config && unreachable ? <p className="t-caption self-center">Saved arrangements are unavailable until the server is back. The console reconnects by itself.</p>
          : status === 'loading' ? [0, 1, 2].map(index => <div className="source-preview" aria-hidden="true" key={index}>
          <span className="thumb skel" /><span className={`skel h-3 ${['w-20', 'w-16', 'w-12'][index]}`} /></div>) : <>
          {restore ? <div className="source-preview relative">
            <button type="button" className="src" title={restore.name} aria-pressed={selected === restore.name}
              disabled={!restoreEntry?.valid} aria-describedby={restoreEntry ? undefined : `${baseId}-restore`}
              onClick={() => restoreEntry && select(restoreEntry)}>
              <span className="thumb dark"><History aria-hidden="true" /></span>
              <span className="src-name">Restore, {clock.format(restore.at)}</span>
            </button>
            {restoreEntry ? actions(restoreEntry) : null}
            {restoreEntry ? null : <span id={`${baseId}-restore`} className="t-caption">Refresh Layouts to find this return point.</span>}
          </div> : null}
          {visible.map(tile)}
          <div className="source-preview">
            <button type="button" className="src" onClick={openSave} aria-haspopup="dialog">
              <span className="thumb add"><Save aria-hidden="true" /></span>
              <span className="src-name">Save current…</span>
            </button>
          </div>
          {status === 'ready' && !visible.length && !restore
            ? <p className="t-caption self-center">No saved arrangements yet. Save this arrangement to reuse it.</p> : null}
        </>}
      </div>
    </div>
    {message ? <p className={clsx('t-caption', message.tone === 'ok' && 'text-ok', message.tone === 'err' && 'text-err')} role="status">
      {message.text}{status === 'error'
        ? <> <Button size="sm" variant="ghost" onClick={() => void refresh()}>Refresh</Button></> : null}
    </p> : null}

    <ModalDialog open={saveOpen} onOpenChange={open => setSaveOpen(open)} title="Save arrangement">
      <form className="grid gap-4" onSubmit={submitSave}>
        <Field id={`${baseId}-name`} label="Name" hint={SNAPSHOT_NAME_RULE} error={saveError}>
          {props => <Input {...props} value={saveName} autoComplete="off"
            onChange={event => { setSaveName(event.target.value); setSaveError(undefined); }} />}
        </Field>
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="ghost" onClick={() => setSaveOpen(false)}>Cancel</Button>
          {working ? <Button type="submit" busy busyLabel="Saving…">Save</Button> : <Button type="submit">Save</Button>}
        </div>
      </form>
    </ModalDialog>

    <ModalDialog open={!!confirm} title={confirm?.kind === 'replace' ? 'Replace saved arrangement'
      : confirm?.kind === 'delete' ? 'Delete saved arrangement' : 'Change the wall kind'}
      onOpenChange={open => { if (!open) { setConfirm(null); setConfirmError(undefined); } }}>
      {confirm ? <>
        <p className="t-body">
          {confirm.kind === 'replace' ? `“${confirm.name}” already exists. Replace it with the arrangement on the wall? The image is not included.`
            : confirm.kind === 'delete' ? `Delete “${confirm.entry.name}”? The wall and its image stay unchanged.`
              : `“${confirm.entry.name}” is a ${confirm.entry.kind} arrangement but the wall is ${config?.layout.kind}. Applying it changes the sizing representation. The server saves a return point for the current arrangement first; the image stays unchanged.`}
        </p>
        {confirmError ? <p className="t-body text-err" role="alert">{confirmError}</p> : null}
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="ghost" autoFocus onClick={() => { setConfirm(null); setConfirmError(undefined); }}>Cancel</Button>
          {confirm.kind === 'delete' ? (working ? <Button variant="danger-solid" busy busyLabel="Deleting…"
            onClick={() => void remove(confirm.entry)}>Delete</Button>
            : <Button variant="danger-solid" onClick={() => void remove(confirm.entry)}>Delete</Button>)
            : confirm.kind === 'kind' ? (working ? <Button busy busyLabel="Applying…"
              onClick={() => void apply(confirm.entry)}>Apply layout</Button>
              : <Button onClick={() => void apply(confirm.entry)}>Apply layout</Button>)
              : (working ? <Button busy busyLabel="Replacing…"
                onClick={() => void persist(confirm.name, true, 'replace')}>Replace</Button>
                : <Button onClick={() => void persist(confirm.name, true, 'replace')}>Replace</Button>)}
        </div>
      </> : null}
    </ModalDialog>
  </>;
}
