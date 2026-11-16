import { startTransition, useId, useState } from 'react';
import { ChevronRight, Images as ImagesIcon } from 'lucide-react';
import type { Image } from '../../../api/images';
import { HexColorSchema } from '../../../api/scene';
import { selectTestPattern, testPatterns } from '../../../state/commands/testPatterns';
import type { TestPattern } from '../../../state/commands/testPatterns';
import { editContent } from '../../../state/store';
import { useWallStore } from '../../../state/hooks';
import { Button } from '../../../ui/Button';
import { Input } from '../../../ui/Input';
import { SideSheet } from '../../../ui/SideSheet';
import { useShell } from '../../preview/ShellContext';
import { useShellView } from '../../preview/useShellView';
import { useImages } from './ImagesContext';
import { ImageTile } from './ImageTile';
import { Upload, useUploadQueueLength } from './Upload';
import './images.css';

export default function Images() {
  const { store } = useShell();
  const { images, loading: inventoryLoading, error, refresh } = useImages();
  const { loading: wallLoading } = useShellView();
  const loading = wallLoading || inventoryLoading;
  const pattern = useWallStore(store, state => state.ui.testPattern);
  const selection = useWallStore(store, state => state.content.selection);
  const uploads = useWallStore(store, state => state.server.config?.capabilities.uploads);
  const queueLength = useUploadQueueLength();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('');
  const searchId = useId();
  function choose(image: Image) {
    const { server, content } = store.getState();
    if (!server.etag) return;
    const applied = server.config?.scene.content;
    const previous = content.selection?.type === 'image' ? content.selection : applied?.type === 'image' ? applied : null;
    const preview = { type: 'image' as const, asset: image.id, fit: previous?.fit ?? 'cover',
      background: previous?.background ?? HexColorSchema.parse('#0b1120'), name: image.name, url: image.url,
      intrinsicWidth: image.width, intrinsicHeight: image.height, available: true };
    store.setState(state => ({ ui: { ...state.ui, testPattern: null } }));
    editContent(store, { type: 'select', selection: preview, etag: server.etag });
    setOpen(false);
  }
  function choosePattern(value: TestPattern) {
    if (store.getState().content.selection) editContent(store, { type: 'discard' });
    selectTestPattern(store, value);
  }
  const visible = images.filter(image => image.name.toLocaleLowerCase().includes(filter.toLocaleLowerCase()));
  const empty = uploads ? 'Add a JPEG or PNG image to this server, then refresh images.'
    : 'Uploads are off on this server. Add a JPEG or PNG to the server’s image folder, then refresh images.';
  const tiles = (items: Image[]) => items.map(image => <ImageTile key={image.id} image={image}
    selected={selection?.type === 'image' && selection.asset === image.id} onSelect={() => choose(image)} />);
  return <div className="images-source">
    {!loading ? <Button variant="ghost" size="sm" className="all-images" data-all-images aria-label="All images" onClick={() => setOpen(true)}><span className="all-images-label">All images</span><span className="all-images-short">All</span><ChevronRight aria-hidden="true" /></Button> : null}
    <div className="source-strip" role="group" aria-label="Image sources" aria-busy={loading}>
      {loading ? [0, 1, 2].map(index => <div className="source-preview" aria-hidden="true" key={index}>
        <span className="thumb skel" /><span className={`skel h-3 ${['w-20', 'w-16', 'w-12'][index]}`} /></div>) : tiles(images.slice(0, 8))}
      {!loading ? testPatterns.map(entry => <Button variant="ghost" className="source-preview image-tile"
        key={entry.value} aria-pressed={pattern === entry.value} onClick={() => choosePattern(entry.value)}>
        <span className="thumb dark">{entry.value === 'grid' ? <svg viewBox="0 0 120 76" width="120" height="76" aria-hidden="true">
          <path d="M0 19H120M0 38H120M0 57H120M20 0V76M40 0V76M60 0V76M80 0V76M100 0V76" fill="none" stroke="currentColor" />
        </svg> : null}</span>
        <span className="t-caption source-name">{entry.name}</span>
      </Button>) : null}
      {!loading ? <Button variant="ghost" className="source-preview image-tile" onClick={() => setOpen(true)}>
        <span className="thumb"><ImagesIcon aria-hidden="true" /></span><span className="t-caption source-name">Library…</span>
      </Button> : null}
    </div>
    <SideSheet open={open} onOpenChange={setOpen} title="Library">
      <div className="image-library">
        <search className="image-library-tools"><label className="image-search" htmlFor={searchId}>Search images
          <Input id={searchId} type="search" value={query} onChange={event => {
            const value = event.target.value;
            setQuery(value);
            startTransition(() => setFilter(value));
          }} /></label>
          <Button variant="secondary" onClick={refresh} aria-disabled={loading}>{loading ? 'Loading…' : 'Refresh images'}</Button>
        </search>
        <Upload />
        {error ? <p className="t-body" role="alert">{error}</p> : null}
        {!images.length && !loading && !queueLength ? <p className="t-body">{empty}</p> : null}
        {images.length > 0 && !visible.length ? <p className="t-body">No images match “{query}”. Try another name.</p> : null}
        <div className="image-library-grid" role="group" aria-label="Library images">{tiles(visible)}</div>
      </div>
    </SideSheet>
  </div>;
}
