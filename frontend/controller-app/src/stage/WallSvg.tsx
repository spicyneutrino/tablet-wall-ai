import { useEffect, useId, useRef, useState } from 'react';
import type { Scene } from '../api/scene';
import { bounds, fitTransform } from '../domain/layout';
import { panels } from '../domain/stagePanels';
import type { Layout, PanelRect } from '../domain/stagePanels';
import type { TabletState } from '../domain/status';
import { TabletShape } from './TabletShape';

export type WallLayout = Extract<Layout, { kind: 'logical' }> |
  (Extract<Layout, { kind: 'physical' }> & { bounds: PanelRect });
export type WallStatus = Pick<TabletState, 'status' | 'text'> & { label?: string; number?: number };
export type WallSvgProps = {
  layout: WallLayout;
  content: Scene | null;
  profileFor: Parameters<typeof panels>[1];
  statuses: Readonly<Record<string, WallStatus>>;
  selected?: string;
  interactive: boolean;
};

export function WallSvg({ layout, content, profileFor, statuses, selected, interactive }: WallSvgProps) {
  const id = useId();
  const svg = useRef<SVGSVGElement>(null);
  const frame = layout.kind === 'physical' ? { kind: layout.kind, bounds: layout.bounds } :
    { kind: layout.kind, width: layout.width, height: layout.height };
  const wall = bounds(frame);
  const margin = wall.width / 70;
  const viewWidth = wall.width + 2 * margin, viewHeight = wall.height + 2 * margin;
  const [scale, setScale] = useState(700 / wall.width);
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => {
      if (entry && entry.contentRect.width > 0 && entry.contentRect.height > 0) {
        setScale(Math.min(entry.contentRect.width / viewWidth, entry.contentRect.height / viewHeight));
      }
    });
    if (svg.current) observer.observe(svg.current);
    return () => observer.disconnect();
  }, [viewWidth, viewHeight]);
  const image = content?.type === 'image' && content.available !== false
    ? fitTransform(frame, content) : null;
  const list = panels(layout, profileFor).sort((a, b) =>
    (statuses[a.id]?.number ?? Infinity) - (statuses[b.id]?.number ?? Infinity) || a.id.localeCompare(b.id));
  const labelSize = Math.max(1, Math.min(16, ...list.flatMap((panel) => panel.missing ? [] : [
    (panel.active.height * scale - 8) / 1.6,
    (panel.active.width * scale - 12) / (Math.max(3, String(statuses[panel.id]?.number ?? statuses[panel.id]?.label ?? panel.id).length) * 0.65),
  ]))) / scale;

  return (
    <svg ref={svg} role="group" aria-label="Wall preview" data-interactive={interactive}
      viewBox={`${wall.x - margin} ${wall.y - margin} ${viewWidth} ${viewHeight}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ display: 'block', inlineSize: '100%', blockSize: '100%', minInlineSize: 0, minBlockSize: 0,
        background: 'var(--stage)', color: 'var(--stage-text)' }}>
      <defs>
        <clipPath id={`${id}-wall`} clipPathUnits="userSpaceOnUse"><rect {...wall} /></clipPath>
        <pattern id={`${id}-hatch`} width={wall.width / 80} height={wall.width / 80} patternUnits="userSpaceOnUse">
          <path d={`M0 ${wall.width / 80} L${wall.width / 80} 0`} stroke="var(--stage-line)"
            strokeWidth={wall.width / 700} strokeOpacity="0.45" />
        </pattern>
        {image && content?.type === 'image' && content.url ? (
          <image id={`${id}-image`} href={content.url} x={image.x} y={image.y}
            width={image.width} height={image.height} preserveAspectRatio="none" />
        ) : null}
      </defs>
      <rect {...wall} fill="var(--stage)" />
      {list.length === 0 ? (
        <text x={wall.x + wall.width / 2} y={wall.y + wall.height / 2} textAnchor="middle"
          fill="currentColor" fontSize={wall.width / 30}>No tablets placed</text>
      ) : null}
      {list.map((panel, index) => (
        <TabletShape key={panel.id} panel={panel} id={`${id}-panel-${index}`}
          status={statuses[panel.id] ?? { status: 'unknown', text: 'Unconfirmed' }}
          selected={selected === panel.id} wallClip={`${id}-wall`} hatch={`${id}-hatch`}
          image={image && content?.type === 'image' && content.url ? `${id}-image` : null}
          background={content?.type === 'image' ? content.background : undefined}
          labelSize={labelSize} markerSize={wall.width / 70} />
      ))}
    </svg>
  );
}
