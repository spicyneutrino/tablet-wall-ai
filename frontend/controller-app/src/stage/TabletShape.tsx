import { exceptionLabel } from '../domain/stagePanels';
import type { Panel } from '../domain/stagePanels';
import type { WallStatus } from './WallSvg';

type TabletShapeProps = {
  panel: Panel;
  id: string;
  status: WallStatus;
  selected: boolean;
  wallClip: string;
  hatch: string;
  image: string | null;
  background?: string;
  markerSize: number;
  labelSize: number;
};

export function TabletShape({ panel, id, status, selected, wallClip, hatch, image, background, markerSize, labelSize }: TabletShapeProps) {
  const label = status.label ?? (status.number ? `Tablet ${status.number}` : panel.id);
  const exception = panel.missing ? 'Missing profile' : panel.slot.participating === false ? 'Excluded' : exceptionLabel(status.status);
  const description = [label, status.text, exception !== status.text ? exception : '', selected ? 'selected' : ''].filter(Boolean).join(', ');
  if (panel.missing) {
    return (
      <g role="img" aria-label={description} data-device-id={panel.id} data-status="missing-profile">
        <circle cx={panel.cx} cy={panel.cy} r={markerSize} fill="var(--stage-warn)" />
        <text x={panel.cx} y={panel.cy + markerSize * 3} textAnchor="middle"
          fontSize={labelSize} fill="var(--stage-text)">{label} · Missing profile</text>
      </g>
    );
  }
  const rotation = `rotate(${panel.angle} ${panel.cx ?? 0} ${panel.cy ?? 0})`;
  const cx = panel.active.x + panel.active.width / 2;
  const cy = panel.active.y + panel.active.height / 2;
  const angle = panel.angle * Math.PI / 180;
  const pivotX = panel.cx ?? cx, pivotY = panel.cy ?? cy;
  const labelX = pivotX + (cx - pivotX) * Math.cos(angle) - (cy - pivotY) * Math.sin(angle);
  const labelY = pivotY + (cx - pivotX) * Math.sin(angle) + (cy - pivotY) * Math.cos(angle);
  const shortLabel = /^Tablet (\d+)\b/.exec(label)?.[1] ?? label;
  const size = labelSize;
  const labelOffset = Math.min(panel.active.width, panel.active.height) / 3;
  const pillWidth = Math.min(panel.active.width * 0.85, Math.max(3, shortLabel.length + 2) * size * 0.65);
  return (
    <g role="img" aria-label={description} data-device-id={panel.id} data-status={status.status} data-selected={selected}>
      <defs>
        <clipPath id={`${id}-screen`} clipPathUnits="userSpaceOnUse"><rect {...panel.active} transform={rotation} /></clipPath>
      </defs>
      <rect {...panel.body} data-body={panel.id} transform={rotation} fill="var(--stage-body)" />
      <rect {...panel.active} data-screen={panel.id} transform={rotation} fill="var(--stage)" />
      {panel.slot.participating !== false ? (
        <g clipPath={`url(#${id}-screen)`}>
          <g clipPath={`url(#${wallClip})`}>
            <rect {...panel.active} transform={rotation} fill={background ?? 'var(--stage)'} />
            {image ? <use href={`#${image}`} /> : null}
          </g>
        </g>
      ) : null}
      {exception ? <rect {...panel.active} transform={rotation} fill={`url(#${hatch})`} /> : null}
      {selected ? <rect {...panel.body} transform={rotation} fill="none" stroke="var(--stage-sel)"
        strokeWidth="3" vectorEffect="non-scaling-stroke" /> : null}
      <g aria-hidden="true" fill="var(--stage-text)">
        <rect x={labelX - pillWidth / 2} y={labelY - labelOffset - size}
          width={pillWidth} height={size * 1.6} rx={size / 3} fill="var(--stage)" />
        <text data-tablet-label={panel.id} x={labelX} y={labelY - labelOffset + size / 5} textAnchor="middle"
          fontSize={size}>{shortLabel}</text>
        {exception ? <text x={labelX} y={labelY + labelOffset} textAnchor="middle"
          fontSize={Math.min(size, panel.active.width / (exception.length * 0.65))}
          paintOrder="stroke" stroke="var(--stage)" strokeWidth={size / 3}>{exception}</text> : null}
      </g>
    </g>
  );
}
