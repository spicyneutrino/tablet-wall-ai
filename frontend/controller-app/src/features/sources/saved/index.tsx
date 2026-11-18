import { useCallback, useEffect, useId, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { clsx } from 'clsx';
import { ImageOff, MoreHorizontal, Palette, Save, TriangleAlert } from 'lucide-react';
import { SNAPSHOT_NAME_RULE } from '../../../state/commands/savedLayouts';
import {
  deleteSavedContent, loadSavedContent, previewSavedContent, recallSavedContent,
  savedContentOutcomeMessage, saveCurrentContent,
} from '../../../state/commands/savedScenes';
import type { SavedContent, SavedImage } from '../../../state/commands/savedScenes';
import { snapshotName } from '../../../domain/names';
import { useWallStore } from '../../../state/hooks';
import { Button } from '../../../ui/Button';
import { Field } from '../../../ui/Field';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from '../../../ui/DropdownMenu';
import { Input } from '../../../ui/Input';
import { ModalDialog } from '../../../ui/ModalDialog';
import type { CommandOutcome } from '../../../session/outcome';
import type { Image } from '../../../api/images';
import type { Scene } from '../../../api/scene';
import { useShell } from '../../preview/ShellContext';
import { useImages } from '../images/ImagesContext';
import './saved.css';

type Message = { tone: 'ok' | 'err'; text: string };
type Confirmation = { kind: 'replace'; name: string } | { kind: 'delete'; entry: SavedContent };

function fitLabel(content: Scene): string {
  if (content.type !== 'image') return content.type === 'calibration' ? 'Pattern' : 'Colour';
  return content.fit === 'contain' ? 'Fit' : 'Fill';
}

function imageFor(content: Scene, images: Image[]): SavedImage | null {
  if (content.type !== 'image') return null;
  const image = images.find(entry => entry.id === content.asset);
  return image ? { url: image.url, name: image.name, width: image.width, height: image.height } : null;
}

function SceneThumb({ content, image }: { content: Scene; image: Image | undefined }) {
  const [failed, setFailed] = useState(false);
  if (content.type === 'calibration') {
    return <svg viewBox="0 0 120 76" width="120" height="76" aria-hidden="true">
      <path d="M0 19H120M0 38H120M0 57H120M20 0V76M40 0V76M60 0V76M80 0V76M100 0V76" fill="none" stroke="currentColor" />
    </svg>;
  }
  if (content.type === 'color') return <Palette aria-hidden="true" />;
  if (!image || failed) return <ImageOff aria-hidden="true" />;
  return <img src={image.thumbnail_url} alt="" width="120" height="76" loading="lazy" onError={() => setFailed(true)} />;
}

export default function Saved() {
  const { store, session } = useShell();
  const { images } = useImages();
  const config = useWallStore(store, state => state.server.config);
  const etagState = useWallStore(store, state => state.server.etagState);
  const busy = useWallStore(store, state => state.server.busy);
  const uncertain = useWallStore(store, state => state.server.uncertain);
  const supported = useWallStore(store, state => state.server.supported);
  const unreachable = useWallStore(store, state => state.server.rosterUnreachable);
  const [entries, setEntries] = useState<SavedContent[] | null>(null);
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

  const publish = useCallback((version: number, outcome: CommandOutcome<SavedContent[]>) => {
    if (version !== loadVersion.current) return;
    if (outcome.kind === 'ok') {
      loadedRef.current = true;
      setEntries(outcome.value);
      setStatus('ready');
      return;
    }
    setStatus('error');
    setMessage({ tone: 'err', text: `${loadedRef.current
      ? 'Showing the last known saved content. '
      : 'Saved content could not be read. '}${savedContentOutcomeMessage(outcome)}` });
  }, []);

  const refresh = useCallback(async () => {
    const version = ++loadVersion.current;
    publish(version, await loadSavedContent(session));
  }, [publish, session]);

  const ready = !!config;
  useEffect(() => {
    if (!ready) return;
    const version = ++loadVersion.current;
    void loadSavedContent(session).then(outcome => publish(version, outcome));
  }, [ready, publish, session]);

  useEffect(() => {
    if (!selected) return;
    stripRef.current?.querySelector(`[data-saved-content="${selected}"]`)
      ?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }, [selected]);

  const blocked = !config ? 'Waiting for the wall.' : uncertain ? 'Refresh status first.'
    : !supported ? 'Update the console before editing.' : busy ? 'Another change is in progress.'
      : etagState !== 'current' ? 'Refresh status first.' : null;

  function select(entry: SavedContent) {
    if (!entry.valid) return;
    if (!previewSavedContent(store, entry, imageFor(entry.content, images))) {
      setMessage({ tone: 'err', text: 'Waiting for the wall.' });
      return;
    }
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
    const outcome = await saveCurrentContent(store, session, name, replace);
    setWorking(false);
    if (outcome.kind === 'ok') {
      setSaveOpen(false);
      setConfirm(null);
      setSaveName('');
      setMessage({ tone: 'ok', text: `Content “${name}” ${replace ? 'replaced' : 'saved'}.` });
      void refresh();
      return;
    }
    const text = savedContentOutcomeMessage(outcome);
    if (where === 'save') setSaveError(text); else setConfirmError(text);
  }

  function submitSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = snapshotName(saveName);
    if (name === null) {
      setSaveError(saveName.trim() ? SNAPSHOT_NAME_RULE : `Enter a content name. ${SNAPSHOT_NAME_RULE}`);
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

  async function remove(entry: SavedContent) {
    setWorking(true);
    const outcome = await deleteSavedContent(store, session, entry);
    setWorking(false);
    if (outcome.kind === 'ok') {
      setConfirm(null);
      setSelected(current => current === entry.name ? null : current);
      setMessage({ tone: 'ok', text: 'Saved content deleted.' });
      void refresh();
      return;
    }
    setConfirmError(savedContentOutcomeMessage(outcome));
  }

  async function show(entry: SavedContent) {
    setWorking(true);
    const outcome = await recallSavedContent(store, session, entry);
    setWorking(false);
    if (outcome.kind === 'ok') {
      setSelected(null);
      setMessage({ tone: 'ok', text: `Content “${entry.name}” is on the wall.` });
      return;
    }
    setMessage({ tone: 'err', text: savedContentOutcomeMessage(outcome) });
  }

  function actions(entry: SavedContent) {
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
          onSelect={() => { void show(entry); }}>Show on wall</DropdownMenuItem>
        <DropdownMenuItem variant="danger" disabled={!!blocked}
          onSelect={() => openConfirm({ kind: 'delete', entry })}>Delete</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>;
  }

  function tile(entry: SavedContent, index: number) {
    const reasonId = `${baseId}-${index}`;
    const image = entry.valid && entry.content.type === 'image'
      ? images.find(item => item.id === entry.content.asset) : undefined;
    return <div className="source-preview relative" key={entry.name} data-saved-content={entry.name}>
      <button type="button" className="src" title={entry.valid ? `${entry.name} · ${fitLabel(entry.content)}` : entry.name}
        aria-pressed={selected === entry.name} disabled={!entry.valid}
        aria-describedby={entry.valid ? undefined : reasonId} onClick={() => select(entry)}>
        <span className="thumb dark saved-thumb">
          {entry.valid ? <SceneThumb content={entry.content} image={image} />
            : <TriangleAlert aria-hidden="true" />}
          {entry.valid ? <span className="tag saved-fit" aria-hidden="true">{fitLabel(entry.content)}</span> : null}
        </span>
        <span className="src-name">{entry.name}</span>
      </button>
      {actions(entry)}
      {entry.valid ? null : <span id={reasonId} className="t-caption text-err">Damaged saved data. Delete it.</span>}
    </div>;
  }

  return <>
    <div className="relative h-[114px] min-w-0">
      <div ref={stripRef} className="source-strip absolute inset-0" role="group"
        aria-label="Saved content" aria-busy={status === 'loading' || undefined}>
        {!config && unreachable ? <p className="t-caption self-center">Saved content is unavailable until the server is back. The console reconnects by itself.</p>
          : status === 'loading' ? [0, 1, 2].map(index => <div className="source-preview" aria-hidden="true" key={index}>
            <span className="thumb skel" /><span className={`skel h-3 ${['w-20', 'w-16', 'w-12'][index]}`} /></div>) : <>
            {(entries ?? []).map(tile)}
            <div className="source-preview">
              <button type="button" className="src" onClick={openSave} aria-haspopup="dialog">
                <span className="thumb add"><Save aria-hidden="true" /></span>
                <span className="src-name">Save current…</span>
              </button>
            </div>
            {status === 'ready' && !entries?.length
              ? <p className="t-caption self-center">Nothing saved yet. Save what is on the wall to reuse it.</p> : null}
          </>}
      </div>
    </div>
    {message ? <p className={clsx('t-caption', message.tone === 'ok' && 'text-ok', message.tone === 'err' && 'text-err')} role="status">
      {message.text}{status === 'error'
        ? <> <Button size="sm" variant="ghost" onClick={() => void refresh()}>Refresh</Button></> : null}
    </p> : null}

    <ModalDialog open={saveOpen} onOpenChange={open => setSaveOpen(open)} title="Save content">
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

    <ModalDialog open={!!confirm} title={confirm?.kind === 'replace' ? 'Replace saved content' : 'Delete saved content'}
      onOpenChange={open => { if (!open) { setConfirm(null); setConfirmError(undefined); } }}>
      {confirm ? <>
        <p className="t-body">
          {confirm.kind === 'replace' ? `“${confirm.name}” already exists. Replace it with the content on the wall? The arrangement is not included.`
            : `Delete “${confirm.entry.name}”? The wall stays unchanged.`}
        </p>
        {confirmError ? <p className="t-body text-err" role="alert">{confirmError}</p> : null}
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="ghost" autoFocus onClick={() => { setConfirm(null); setConfirmError(undefined); }}>Cancel</Button>
          {confirm.kind === 'delete' ? (working ? <Button variant="danger-solid" busy busyLabel="Deleting…"
            onClick={() => void remove(confirm.entry)}>Delete</Button>
            : <Button variant="danger-solid" onClick={() => void remove(confirm.entry)}>Delete</Button>)
            : (working ? <Button busy busyLabel="Replacing…"
              onClick={() => void persist(confirm.name, true, 'replace')}>Replace</Button>
              : <Button onClick={() => void persist(confirm.name, true, 'replace')}>Replace</Button>)}
        </div>
      </> : null}
    </ModalDialog>
  </>;
}
