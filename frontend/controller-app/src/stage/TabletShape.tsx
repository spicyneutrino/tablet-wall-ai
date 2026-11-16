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
  const number = status.number ?? /^Tablet (\d+)\b/.exec(label)?.[1];
  const size = labelSize;
  const bodyWidth = Math.abs(panel.body.width * Math.cos(angle)) + Math.abs(panel.body.height * Math.sin(angle));
  const bodyHeight = Math.abs(panel.body.width * Math.sin(angle)) + Math.abs(panel.body.height * Math.cos(angle));
  const chipX = pivotX - bodyWidth / 2 + size * 8 / 13;
  const chipY = pivotY - bodyHeight / 2 + size * 8 / 13;
  const compact = bodyWidth < size * 12;
  const chipLabel = number && compact ? String(number) : number ? `${number}  ${label}` : label;
  const pillWidth = Math.min(bodyWidth - size, (chipLabel.length * 0.56 + 1.7) * size);
  const offline = status.status === 'offline';
  return (
    <g role="img" aria-label={description} data-device-id={panel.id} data-status={status.status} data-selected={selected}>
      <defs>
        <clipPath id={`${id}-screen`} clipPathUnits="userSpaceOnUse"><rect {...panel.active} transform={rotation} /></clipPath>
      </defs>
      <rect {...panel.body} data-body={panel.id} transform={rotation} fill="var(--stage-body)" />
      <rect {...panel.active} data-screen={panel.id} transform={rotation} fill="var(--stage)" />
      {panel.slot.participating !== false && !offline ? (
        <g clipPath={`url(#${id}-screen)`}>
          <g clipPath={`url(#${wallClip})`}>
            <rect {...panel.active} transform={rotation} fill={background ?? 'var(--stage)'} />
            {image ? <use href={`#${image}`} /> : null}
          </g>
        </g>
      ) : null}
      {offline ? <rect {...panel.active} transform={rotation} fill="var(--stage-body)" /> : null}
      {offline ? <rect {...panel.active} transform={rotation} fill={`url(#${hatch})`}
        stroke={offline ? 'var(--stage-warn)' : undefined} strokeDasharray={offline ? '6 5' : undefined}
        vectorEffect="non-scaling-stroke" /> : null}
      {selected ? <rect {...panel.body} transform={rotation} fill="none" stroke="var(--stage-sel)"
        strokeWidth="3" vectorEffect="non-scaling-stroke" /> : null}
      <g aria-hidden="true" fill="var(--stage-text)">
        <rect x={chipX} y={chipY} width={pillWidth} height={size * 22 / 13} rx={size * 11 / 13}
          fill="var(--stage-pill)" stroke="var(--stage-line)" vectorEffect="non-scaling-stroke" />
        <text data-tablet-label={panel.id} x={chipX + size * 8 / 13} y={chipY + size * 1.2}
          fontSize={size}>{number ?? label}</text>
        {number && !compact ? <text x={chipX + size * 1.8} y={chipY + size * 1.2}
          fontSize={size}>{label}</text> : null}
        {offline ? <g>
          <rect x={labelX - size * 37 / 13} y={labelY - size * 12 / 13}
            width={size * 74 / 13} height={size * 24 / 13} rx={size * 6 / 13}
            fill="var(--stage-pill)" stroke="var(--stage-warn)" vectorEffect="non-scaling-stroke" />
          <path d="M0 -4.5 L5 4.5 L-5 4.5 Z" fill="var(--stage-warn)"
            transform={`translate(${labelX - size * 24 / 13} ${labelY}) scale(${size / 13})`} />
          <text x={labelX - size * 14 / 13} y={labelY + size * 0.36} fontSize={size} fill="var(--stage-warn)">Offline</text>
        </g> : exception ? (() => {
          const fit = Math.min(size, (bodyWidth * 0.9) / (exception.length * 0.6 + 1.6));
          return <g>
            <rect x={labelX - (exception.length * 0.3 + 0.8) * fit} y={labelY - fit * 12 / 13}
              width={(exception.length * 0.6 + 1.6) * fit} height={fit * 24 / 13} rx={fit * 6 / 13}
              fill="var(--stage-pill)" stroke="var(--stage-line)" vectorEffect="non-scaling-stroke" />
            <text x={labelX} y={labelY + fit * 0.36} textAnchor="middle" fontSize={fit}>{exception}</text>
          </g>;
        })() : null}
      </g>
    </g>
  );
}
