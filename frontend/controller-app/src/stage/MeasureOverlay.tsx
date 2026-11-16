import { createContext } from 'react';
import type { Panel } from '../domain/stagePanels';

export type StageMeasurement = { id: string; width: string; height: string; ruler: boolean; spanX: string; spanY: string };
export const MeasurementContext = createContext<StageMeasurement | null>(null);
export function MeasureOverlay({ panel, measurement, scale }: { panel: Panel; measurement: StageMeasurement; scale: number }) {
  if (panel.missing) return null;
  const { active } = panel;
  const size = Math.min(16 / scale, active.width / 15, active.height / 10);
  const x = active.x + active.width / 2, y = active.y + active.height / 2;
  const ruler = measurement.ruler;
  return <g data-measure-overlay={panel.id} pointerEvents="none" role="img"
    aria-label={ruler ? `Ruler A ${measurement.spanX} CSS px, B ${measurement.spanY} CSS px`
      : `Entered screen ${measurement.width} by ${measurement.height} millimetres`}
    transform={`rotate(${panel.angle} ${panel.cx ?? x} ${panel.cy ?? y})`}>
    <rect {...active} fill="var(--stage-screen)" />
    {ruler ? <g fill="var(--stage-text)" fontSize={size} stroke="var(--stage-text)" strokeWidth={1.5 / scale}>
      <path d={`M${active.x + size * 2} ${y - size} H${active.x + active.width - size * 4}`} />
      <text x={x} y={y + size * 1.4} textAnchor="middle" stroke="none">A · {measurement.spanX} px</text>
      <path d={`M${active.x + size * 2} ${y + size} V${active.y + active.height - size * 2}`} />
      <text x={active.x + size * 3} y={y + size * 3} stroke="none">B · {measurement.spanY} px</text>
    </g> : <g fill="var(--stage-sel)" fontSize={size} stroke="var(--stage-sel)" strokeWidth={1.5 / scale}>
      <rect {...active} fill="none" strokeDasharray="4 4" />
      <path d={`M${active.x + size} ${active.y + active.height - size} H${active.x + active.width - size}`} />
      <text x={x} y={active.y + active.height - size * 1.7} textAnchor="middle" stroke="none">{measurement.width || '?'} mm</text>
      <path d={`M${active.x + active.width - size} ${active.y + size * 2} V${active.y + active.height - size * 2}`} />
      <text x={active.x + active.width - size * 1.7} y={y} textAnchor="end" stroke="none">{measurement.height || '?'} mm</text>
    </g>}
  </g>;
}
