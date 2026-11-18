import { useState } from 'react';
import { ImageOff } from 'lucide-react';
import { Button } from '../../../ui/Button';
import type { Image } from '../../../api/images';

export function ImageTile({ image, selected, onSelect }: { image: Image; selected: boolean; onSelect: () => void }) {
  const [failed, setFailed] = useState(false);
  return <Button variant="ghost" className="source-preview image-tile" aria-pressed={selected} onClick={onSelect}>
    <span className="thumb">{failed ? <ImageOff aria-hidden="true" />
      : <img src={image.thumbnail_url} alt="" width="120" height="76" loading="lazy" onError={() => setFailed(true)} />}</span>
    <span className="t-caption source-name">{image.name}</span>
  </Button>;
}
