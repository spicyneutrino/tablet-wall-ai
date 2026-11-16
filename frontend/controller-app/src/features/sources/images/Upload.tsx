import { useId, useRef, useState } from 'react';
import { FileX, ImageUp, Upload as UploadIcon, X } from 'lucide-react';
import type { ManagedAsset } from '../../../api/images';
import { HexColorSchema } from '../../../api/scene';
import { formatBytes, UPLOAD_FAILED, UPLOAD_REFUSED, UPLOADS_OFF, uploadFile } from '../../../state/commands/upload';
import type { UploadHandle } from '../../../state/commands/upload';
import { useWallStore } from '../../../state/hooks';
import { editContent } from '../../../state/store';
import type { WallStoreApi } from '../../../state/store';
import { Button } from '../../../ui/Button';
import { useShell } from '../../preview/ShellContext';
import { useImages } from './ImagesContext';

type Status = 'queued' | 'uploading' | 'cancelled' | 'refused' | 'failed';
type QueueItem = { id: number; file: File; status: Status; progress: number; transferComplete: boolean; batch: number };

function selectUploaded(store: WallStoreApi, asset: ManagedAsset) {
  const { server, content } = store.getState();
  if (!server.etag) return;
  const applied = server.config?.scene.content;
  const previous = content.selection?.type === 'image' ? content.selection
    : applied?.type === 'image' ? applied : null;
  const preview = { type: 'image' as const, asset: asset.id, fit: previous?.fit ?? 'cover',
    background: previous?.background ?? HexColorSchema.parse('#0b1120'), name: asset.name, url: asset.url,
    intrinsicWidth: asset.intrinsicWidth, intrinsicHeight: asset.intrinsicHeight, available: true };
  store.setState(state => ({ ui: { ...state.ui, testPattern: null } }));
  editContent(store, { type: 'select', selection: preview, etag: server.etag });
}

export function Upload() {
  const { store } = useShell();
  const { refresh } = useImages();
  const uploads = useWallStore(store, state => state.server.config?.capabilities.uploads);
  const enabled = uploads === true;
  const [items, setItems] = useState<QueueItem[]>([]);
  const [over, setOver] = useState(false);
  const [total, setTotal] = useState(0);
  const [finished, setFinished] = useState(0);
  const itemsRef = useRef<QueueItem[]>([]);
  const active = useRef<UploadHandle | null>(null);
  const running = useRef(false);
  const nextId = useRef(1);
  const input = useRef<HTMLInputElement>(null);
  const titleId = useId();

  function commit(next: QueueItem[]) {
    itemsRef.current = next;
    setItems(next);
  }
  function patch(id: number, changes: Partial<QueueItem>) {
    commit(itemsRef.current.map(item => item.id === id ? { ...item, ...changes } : item));
  }
  function remove(id: number) {
    const item = itemsRef.current.find(candidate => candidate.id === id);
    if (item?.status === 'queued') setTotal(value => value - 1);
    commit(itemsRef.current.filter(candidate => candidate.id !== id));
  }
  function finish(item: QueueItem, changes: Partial<QueueItem>) {
    patch(item.id, changes);
    setFinished(value => value + 1);
  }
  function drop(item: QueueItem, changes: Partial<QueueItem>) {
    patch(item.id, changes);
    setTotal(value => value - 1);
  }
  async function uploadItem(item: QueueItem) {
    patch(item.id, { status: 'uploading', progress: 0, transferComplete: false });
    const handle = uploadFile(item.file, {
      onProgress: percent => patch(item.id, { progress: percent }),
      onTransferComplete: () => patch(item.id, { transferComplete: true, progress: 100 }),
    });
    active.current = handle;
    const result = await handle.done;
    active.current = null;
    if (result.kind === 'cancelled') return drop(item, { status: 'cancelled', progress: 0 });
    if (result.kind === 'refused') return drop(item, { status: 'refused' });
    if (result.kind === 'failed') return finish(item, { status: 'failed' });
    setFinished(value => value + 1);
    refresh();
    if (item.batch === 1) selectUploaded(store, result.asset);
    remove(item.id);
  }
  async function start() {
    if (running.current) return;
    running.current = true;
    try {
      for (;;) {
        const next = itemsRef.current.find(item => item.status === 'queued');
        if (!next) break;
        await uploadItem(next);
      }
    } finally {
      running.current = false;
    }
  }
  function addFiles(files: FileList | null) {
    if (!files || !enabled) return;
    const list = Array.from(files).filter(file => file.size > 0);
    if (!list.length) return;
    const additions = list.map(file => ({ id: nextId.current++, file, status: 'queued' as const,
      progress: 0, transferComplete: false, batch: list.length }));
    setTotal(value => value + additions.length);
    commit([...itemsRef.current, ...additions]);
    void start();
  }
  function cancel(id: number) {
    const item = itemsRef.current.find(candidate => candidate.id === id);
    if (!item || item.status !== 'uploading' || item.transferComplete) return;
    active.current?.cancel();
  }
  function retry(id: number) {
    patch(id, { status: 'queued', progress: 0, transferComplete: false });
    setFinished(value => value - 1);
    void start();
  }

  const inFlight = items.some(item => item.status === 'queued' || item.status === 'uploading');
  const reason = uploads === false ? UPLOADS_OFF : 'Checking upload availability…';
  const heading = uploads === false ? UPLOADS_OFF : uploads === true ? 'Drop images here, or' : 'Checking upload availability…';
  return <>
    <p className="t-caption">PNG or JPEG. Uploads run one at a time.</p>
    <div className={over ? 'drop is-over' : 'drop'} role="group" aria-label="Upload images"
      onDragOver={event => { if (!enabled) return; event.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={event => { event.preventDefault(); setOver(false); addFiles(event.dataTransfer.files); }}>
      <ImageUp className="i-lg t-muted" aria-hidden="true" />
      <p className="t-body">{heading}</p>
      <input ref={input} type="file" accept="image/png,image/jpeg" multiple hidden aria-label="Choose image files"
        onChange={event => { addFiles(event.target.files); event.target.value = ''; }} />
      <Button variant="secondary" {...(enabled ? { disabled: false as const } : { disabled: true as const, disabledReason: reason })}
        onClick={() => input.current?.click()}><UploadIcon aria-hidden="true" />Choose files…</Button>
    </div>
    {items.length ? <section aria-labelledby={titleId} className="grid gap-3">
      <h3 id={titleId} className="t-label">{inFlight ? `Uploading ${Math.min(finished + 1, total)} of ${total}` : 'Upload queue'}</h3>
      <ul className="grid gap-4">
        {items.map(item => {
          const percent = Math.round(item.progress);
          const label = item.status === 'queued' ? 'Waiting'
            : item.status === 'uploading' ? item.transferComplete ? 'Processing…' : `${percent}% · ${formatBytes(item.file.size)}`
              : item.status === 'cancelled' ? 'Cancelled' : formatBytes(item.file.size);
          return <li key={item.id} className="flex items-center gap-3">
            <span className="w-12 h-8 rounded-sm bg-well grid place-items-center flex-none" aria-hidden="true">
              {item.status === 'refused' || item.status === 'failed'
                ? <FileX className="i-sm text-err" aria-hidden="true" /> : null}
            </span>
            <div className="flex-1 min-w-0 grid gap-1">
              <div className="flex justify-between gap-2">
                <span className="t-label truncate">{item.file.name}</span>
                <span className="t-caption">{label}</span>
              </div>
              {item.status === 'uploading' ? <div className="meter" role="progressbar" aria-label={item.file.name}
                aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${percent}%` }} /></div>
                : <span className="t-caption">{formatBytes(item.file.size)}</span>}
              {item.status === 'refused' ? <span className="t-caption text-err">{UPLOAD_REFUSED}</span> : null}
              {item.status === 'failed' ? <span className="t-caption text-err">{UPLOAD_FAILED}</span> : null}
            </div>
            {item.status === 'uploading' && !item.transferComplete
              ? <Button variant="ghost" size="icon" aria-label={`Cancel upload of ${item.file.name}`}
                onClick={() => cancel(item.id)}><X aria-hidden="true" /></Button> : null}
            {item.status === 'failed' ? <Button variant="ghost" size="sm" onClick={() => retry(item.id)}>Retry</Button> : null}
            {item.status !== 'uploading' ? <Button variant="ghost" size="icon"
              aria-label={item.status === 'queued' ? `Remove ${item.file.name} from the queue` : `Dismiss ${item.file.name}`}
              onClick={() => remove(item.id)}><X aria-hidden="true" /></Button> : null}
          </li>;
        })}
      </ul>
    </section> : null}
  </>;
}
