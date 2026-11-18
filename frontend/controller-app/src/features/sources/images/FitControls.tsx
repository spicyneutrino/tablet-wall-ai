import { useId } from 'react';
import { SceneSchema, HexColorSchema } from '../../../api/scene';
import { bounds, fitTransform } from '../../../domain/layout';
import { panels, resolution } from '../../../domain/stagePanels';
import { editContent } from '../../../state/store';
import { useWallStore, selectPreviewContent, selectPreviewLayout } from '../../../state/hooks';
import { SideSheet } from '../../../ui/SideSheet';
import { ToggleGroup, ToggleGroupItem } from '../../../ui/ToggleGroup';
import { Input } from '../../../ui/Input';
import { useShell } from '../../preview/ShellContext';
import { useShellView } from '../../preview/useShellView';

export function FitControls({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { store } = useShell();
  const content = useWallStore(store, selectPreviewContent);
  const layout = useWallStore(store, selectPreviewLayout);
  const { profileFor, server } = useShellView();
  const colorId = useId();
  if (content?.type !== 'image') return null;
  const image = SceneSchema.parse(content);
  if (image.type !== 'image') return null;
  const transform = layout ? fitTransform(layout, image) : null;
  const frame = layout ? bounds(layout) : null;
  const contain = image.fit === 'contain';
  const cropX = transform && frame ? contain ? Math.max(0, 1 - transform.width / frame.width) : transform.cropX : 0;
  const cropY = transform && frame ? contain ? Math.max(0, 1 - transform.height / frame.height) : transform.cropY : 0;
  const intrinsicWidth = image.intrinsicWidth;
  const warnings = layout && transform && intrinsicWidth
    ? panels(layout, profileFor).flatMap(panel => {
      const result = resolution(panel, transform, { intrinsicWidth }, { viewport: server.roster[panel.id]?.viewport ?? undefined });
      return result?.upscale && result.upscale > 1 ? [`${server.roster[panel.id]?.label || `Tablet ${server.roster[panel.id]?.number ?? ''}`}: ${result.pixels} source pixels for ${result.target} display pixels.`] : [];
    }) : [];
  function update(change: { fit?: 'cover' | 'contain'; background?: ReturnType<typeof HexColorSchema.parse> }) {
    const state = store.getState();
    if (!state.server.etag) return;
    editContent(store, { type: 'select', selection: { ...image, ...change }, etag: state.server.etag });
  }
  return <SideSheet title="Fit and crop" open={open} onOpenChange={onOpenChange}>
    <div className="image-fit-settings">
      <p className="t-body">Changes stay in Preview until you choose Show on wall.</p>
      <ToggleGroup type="single" value={content.fit} aria-label="Image fit" onValueChange={value => {
        if (value === 'cover' || value === 'contain') update({ fit: value });
      }}>
        <ToggleGroupItem value="cover">Fill</ToggleGroupItem><ToggleGroupItem value="contain">Fit</ToggleGroupItem>
      </ToggleGroup>
      <label className="image-background" htmlFor={colorId}>Background
        <Input id={colorId} type="color" value={content.background ?? '#0b1120'} onChange={event => {
          const background = HexColorSchema.safeParse(event.target.value);
          if (background.success) update({ background: background.data });
        }} />
      </label>
      <p className="t-body" data-crop-summary>{transform ?
        `${(cropX * 100).toFixed(1)}% ${contain ? 'of wall width uncovered' : 'of source width cropped'}; ${(cropY * 100).toFixed(1)}% ${contain ? 'of wall height uncovered' : 'of source height cropped'}.`
        : 'Crop estimate unavailable. Refresh images or choose another image.'}</p>
      {warnings.length ? <div className="note note-warn"><p className="t-label">This image may look soft</p>
        {warnings.map(warning => <p className="t-caption" key={warning}>{warning}</p>)}</div> : null}
    </div>
  </SideSheet>;
}
