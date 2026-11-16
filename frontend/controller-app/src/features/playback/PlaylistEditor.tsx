import { useEffect, useId, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, ImageOff, Plus, X } from 'lucide-react';
import type { ManagedAsset, Media } from '../../api/images';
import type { Playlist, PlaylistItem } from '../../api/playback';
import { loadPlaylist, playlistOutcomeMessage, savePlaylist } from '../../state/commands/playback';
import { useWallStore } from '../../state/hooks';
import { editPlaylist } from '../../state/store';
import { Button } from '../../ui/Button';
import { Input, Select, Switch } from '../../ui/Input';
import { Label } from '../../ui/Label';
import { useShell } from '../preview/ShellContext';
import type { Load } from '../server/model';
import { DEFAULT_DWELL_MS, MAX_ITEMS, isVideo, moved, parseSeconds, playlistSummary, secondsText } from './model';

type Removed = { item: PlaylistItem; index: number; name: string };
type Focus = { row: number; action: 'up' | 'down' | 'remove'; n: number };

export default function PlaylistEditor({ media, ready }: { media: Load<Media>; ready: boolean }) {
  const { store, session } = useShell();
  const playlist = useWallStore(store, state => state.playlist);
  const [pending, setPending] = useState<(string | undefined)[]>([]);
  const [removed, setRemoved] = useState<Removed | null>(null);
  const [announce, setAnnounce] = useState('');
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [adding, setAdding] = useState('');
  const [focus, setFocus] = useState<Focus | null>(null);
  const list = useRef<HTMLOListElement>(null);
  const headingId = useId();

  const assets = media.kind === 'ready' ? media.value.assets : [];
  const items = playlist.draft?.items ?? [];
  const loop = playlist.draft?.loop ?? false;
  const lookup = (id: string): ManagedAsset | undefined => assets.find(asset => asset.id === id);
  const nameOf = (item: PlaylistItem) => lookup(item.asset)?.name ?? 'Image no longer available';
  const errors = items.map((_, index) => {
    const text = pending[index];
    if (text === undefined) return '';
    const parsed = parseSeconds(text);
    return parsed.ok ? '' : parsed.error;
  });
  const invalid = errors.some(Boolean);

  const [seen, setSeen] = useState(playlist.saved);
  if (seen !== playlist.saved) { setSeen(playlist.saved); setPending([]); }
  useEffect(() => {
    if (focus) list.current?.querySelector<HTMLElement>(`[data-row="${focus.row}"][data-action="${focus.action}"]`)?.focus();
  }, [focus]);

  function commit(next: PlaylistItem[], nextLoop = loop) {
    const value: Playlist | null = !next.length && !playlist.saved ? null : { ...playlist.draft, items: next, loop: nextLoop };
    editPlaylist(store, { type: 'edit', value });
  }
  function edited(text: string, undo = false) {
    if (!undo) setRemoved(null);
    setMessage('');
    setAnnounce(text);
  }
  function setDwell(index: number, text: string) {
    setPending(current => Object.assign([...current], { [index]: text }));
    const parsed = parseSeconds(text);
    if (parsed.ok) { edited(''); commit(items.map((item, at) => at === index ? { ...item, dwell_ms: parsed.ms } : item)); }
  }
  function settle(index: number) {
    if (pending[index] !== undefined && parseSeconds(pending[index]).ok) setPending(current => Object.assign([...current], { [index]: undefined }));
  }
  function move(index: number, to: number, action: 'up' | 'down') {
    edited(`Moved ${nameOf(items[index]!)} to position ${to + 1} of ${items.length}.`);
    setPending(current => moved(items.map((_, at) => current[at]), index, to));
    commit(moved(items, index, to));
    setFocus({ row: to, action: to === 0 ? 'down' : to === items.length - 1 ? 'up' : action, n: Date.now() });
  }
  function remove(index: number) {
    const item = items[index]!;
    edited(`Removed ${nameOf(item)}.`);
    setRemoved({ item, index, name: nameOf(item) });
    setPending(current => items.map((_, at) => current[at]).filter((_, at) => at !== index));
    commit(items.filter((_, at) => at !== index));
    setFocus(items.length > 1 ? { row: Math.min(index, items.length - 2), action: 'remove', n: Date.now() } : null);
  }
  function undo() {
    if (!removed) return;
    const next = [...items];
    next.splice(removed.index, 0, removed.item);
    edited(`Restored ${removed.name}.`, true);
    setRemoved(null);
    setPending(current => { const restored = [...current]; restored.splice(removed.index, 0, undefined); return restored; });
    commit(next);
    setFocus({ row: removed.index, action: 'remove', n: Date.now() });
  }
  function add() {
    const id = adding || assets[0]?.id;
    const asset = assets.find(candidate => candidate.id === id);
    if (!asset) return;
    edited(`Added ${asset.name} as item ${items.length + 1}.`);
    commit([...items, { asset: asset.id as PlaylistItem['asset'], dwell_ms: DEFAULT_DWELL_MS }]);
  }
  async function save() {
    setSaving(true);
    setMessage('');
    setRemoved(null);
    const outcome = await savePlaylist(store, session);
    setSaving(false);
    setMessage(outcome.kind === 'ok' ? 'Playlist saved.' : playlistOutcomeMessage(outcome));
  }
  async function reload(mode: 'keep' | 'discard') {
    setRemoved(null);
    const outcome = await loadPlaylist(store, session, mode);
    setMessage(outcome.kind === 'ok' ? '' : playlistOutcomeMessage(outcome));
  }

  const saveReason = playlist.conflict ? 'Choose Keep my edits or Use the saved playlist first.'
    : invalid ? 'Fix the seconds shown in red first.' : !items.length ? 'Add at least one image first.'
    : !playlist.dirty ? 'No changes to save.' : !playlist.etag ? 'Reload the playlist first.' : null;
  const addReason = media.kind === 'loading' ? 'Reading the image list…' : !assets.length ? 'Upload an image first.'
    : items.length >= MAX_ITEMS ? `A playlist holds up to ${MAX_ITEMS} items.` : null;

  return <section className="playback-block" aria-labelledby={headingId}>
    <div className="playback-head">
      <h3 id={headingId} className="t-heading">Playlist</h3>
      <span className="t-caption">{playlistSummary(items, loop)}</span>
    </div>
    {!ready ? <p className="t-body">Reading the playlist…</p> : null}
    {playlist.conflict ? <div className="note note-warn" role="alert">
      <p className="note-title">The saved playlist changed</p>
      <p className="t-body">Someone saved a different playlist while you were editing. Your edits are kept below.</p>
      <div className="playback-actions">
        <Button variant="secondary" onClick={() => void reload('keep')}>Keep my edits</Button>
        <Button variant="ghost" onClick={() => void reload('discard')}>Use the saved playlist</Button>
      </div></div> : null}
    {ready && !items.length ? <p className="t-body">No images yet. Pick one below and choose Add.</p> : null}
    <ol className="playlist-rows" aria-label="Playlist order" ref={list}>
      {items.map((item, index) => {
        const asset = lookup(item.asset);
        const name = nameOf(item);
        const text = pending[index] ?? secondsText(item.dwell_ms);
        const errorId = `${headingId}-dwell-${index}`;
        return <li className="playlist-row" key={index}>
          <span className="playlist-thumb">{asset
            ? <img src={asset.thumbnail?.url ?? asset.url} alt="" width={48} height={32} loading="lazy" />
            : <ImageOff aria-hidden="true" />}</span>
          <span className="t-body playlist-name">{name}</span>
          <div className="playlist-controls">
            <div className="unit playlist-dwell">
              <Input aria-label={`${name}: seconds on screen`} value={isVideo(asset) ? 'Full clip' : text} inputMode="decimal" autoComplete="off"
                disabled={isVideo(asset)} aria-invalid={errors[index] ? true : undefined} aria-describedby={errors[index] ? errorId : undefined}
                onChange={event => setDwell(index, event.target.value)} onBlur={() => settle(index)} />
              {isVideo(asset) ? null : <span>s</span>}
            </div>
            <div className="playlist-actions">
              {index > 0 ? <Button variant="ghost" size="icon" aria-label={`Move ${name} up`} data-row={index} data-action="up"
                onClick={() => move(index, index - 1, 'up')}><ArrowUp aria-hidden="true" /></Button> : null}
              {index < items.length - 1 ? <Button variant="ghost" size="icon" aria-label={`Move ${name} down`} data-row={index} data-action="down"
                onClick={() => move(index, index + 1, 'down')}><ArrowDown aria-hidden="true" /></Button> : null}
              <Button variant="ghost" size="icon" aria-label={`Remove ${name}`} data-row={index} data-action="remove"
                onClick={() => remove(index)}><X aria-hidden="true" /></Button>
            </div>
          </div>
          {errors[index] ? <span id={errorId} className="t-caption field-error playlist-error" role="alert">{errors[index]}</span> : null}
        </li>;
      })}
    </ol>
    {removed ? <p className="t-body playlist-undo">Removed {removed.name}. <Button variant="ghost" size="sm" onClick={undo}>Undo</Button></p> : null}
    <p className="sr-only" role="status">{announce}</p>
    <div className="playback-add">
      <Select aria-label="Image to add" value={adding || assets[0]?.id || ''} disabled={!assets.length} onChange={event => setAdding(event.target.value)}>
        {assets.length ? assets.map(asset => <option key={asset.id} value={asset.id}>{asset.name}</option>) : <option value="">No images yet</option>}
      </Select>
      {addReason ? <Button variant="secondary" disabled disabledReason={addReason}><Plus aria-hidden="true" />Add</Button>
        : <Button variant="secondary" onClick={add}><Plus aria-hidden="true" />Add</Button>}
    </div>
    <div className="playback-footer">
      <Label className="playback-loop"><Switch checked={loop} disabled={!items.length}
        onChange={event => { edited(''); commit(items, event.target.checked); }} />Loop</Label>
      <div className="playback-actions">
        {playlist.dirty ? <Button variant="ghost" onClick={() => void reload('discard')}>Discard changes</Button> : null}
        {saving ? <Button variant="secondary" busy busyLabel="Saving…">Save playlist</Button>
          : saveReason ? <Button variant="secondary" disabled disabledReason={saveReason}>Save playlist</Button>
            : <Button variant="secondary" onClick={() => void save()}>Save playlist</Button>}
      </div>
    </div>
    {message ? <p className="t-body" role="status">{message}</p> : null}
  </section>;
}
