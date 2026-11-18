import { useEffect, useId, useRef, useState } from 'react';
import { Magnet, MousePointer2, Redo2, RotateCcw, RotateCw, Undo2 } from 'lucide-react';
import { DeviceIdSchema } from '../api/devices';
import type { DeviceId } from '../api/devices';
import type { Layout } from '../api/layouts';
import { panels } from '../domain/stagePanels';
import { selectDevice } from '../state/store';
import type { WallStoreApi } from '../state/store';
import type { WallSvgProps } from './WallSvg';
import { positionReadout } from './useStageGesture';
import type { ResizeHandle, useStageGesture } from './useStageGesture';

export type StageGesture = ReturnType<typeof useStageGesture>;
const handles: { name: ResizeHandle; x: number; y: number }[] = [
  { name: 'nw', x: 0, y: 0 }, { name: 'n', x: 0.5, y: 0 }, { name: 'ne', x: 1, y: 0 },
  { name: 'e', x: 1, y: 0.5 }, { name: 'se', x: 1, y: 1 }, { name: 's', x: 0.5, y: 1 },
  { name: 'sw', x: 0, y: 1 }, { name: 'w', x: 0, y: 0.5 },
];

export function EditOverlay({ store, layout, profileFor, statuses, selected, editable, gesture, snap, onSnapChange }: {
  store: WallStoreApi; layout: Layout; profileFor: WallSvgProps['profileFor']; statuses: WallSvgProps['statuses'];
  selected: DeviceId | null; editable: boolean; gesture: StageGesture; snap: boolean; onSnapChange: (snap: boolean) => void;
}) {
  const helpId = useId();
  const svg = useRef<SVGSVGElement>(null);
  const wall = layout.kind === 'physical' ? layout.bounds : { x: 0, y: 0, width: layout.width, height: layout.height };
  const margin = wall.width / 70, width = wall.width + margin * 2, height = wall.height + margin * 2;
  const [scale, setScale] = useState(700 / wall.width);
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => {
      if (entry && entry.contentRect.width > 0 && entry.contentRect.height > 0) {
        setScale(Math.min(entry.contentRect.width / width, entry.contentRect.height / height));
      }
    });
    if (svg.current) observer.observe(svg.current);
    return () => observer.disconnect();
  }, [width, height]);
  const px = 1 / scale, list = panels(layout, profileFor);
  const panel = list.find(item => item.id === selected);
  const label = (id: string) => statuses[id]?.label ?? `Tablet ${statuses[id]?.number ?? id}`;
  const draft = store.getState().arrangement;
  return <>
    <svg ref={svg} data-edit-overlay="" role="group" aria-label="Layout canvas" tabIndex={0} aria-describedby={helpId}
      className="focus-visible:outline-2 focus-visible:outline-[var(--stage-sel)] [&[data-dragging]_[data-edit-hit]_rect]:cursor-grabbing"
      viewBox={`${wall.x - margin} ${wall.y - margin} ${width} ${height}`} preserveAspectRatio="xMidYMid meet"
      onPointerDown={gesture.onPointerDown} onPointerMove={gesture.onPointerMove} onPointerUp={gesture.onPointerUp}
      onPointerCancel={gesture.onPointerCancel} onLostPointerCapture={gesture.onLostPointerCapture}
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', color: 'var(--stage-sel)', touchAction: editable ? 'none' : 'auto' }}>
      {list.map(item => item.missing ? <circle key={item.id} cx={item.cx} cy={item.cy} r={wall.width / 70}
        data-edit-id={item.id} role="button" tabIndex={0} aria-label={`${label(item.id)}. Missing profile.`}
        aria-pressed={selected === item.id} fill="transparent" onFocus={() => selectDevice(store, DeviceIdSchema.parse(item.id))}
        onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') event.preventDefault(); }} />
        : <g key={item.id} data-edit-hit={item.id}><rect data-edit-id={item.id}
        role="button" tabIndex={0} aria-label={`${label(item.id)}. Use arrow keys to move.`} aria-pressed={selected === item.id}
        onFocus={() => { const id = DeviceIdSchema.parse(item.id); selectDevice(store, id); }}
        onKeyDown={event => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault(); selectDevice(store, DeviceIdSchema.parse(item.id));
          }
        }}
        {...item.body} transform={`rotate(${item.angle} ${item.cx ?? 0} ${item.cy ?? 0})`}
        fill="transparent" className={`focus-visible:outline-2 focus-visible:outline-[var(--stage-sel)] ${editable ? 'cursor-grab' : 'cursor-pointer'}`}
        style={{ touchAction: editable ? 'none' : 'auto', userSelect: 'none', WebkitUserSelect: 'none' }} /></g>)}
      <line data-guide="x" visibility="hidden" stroke="currentColor" strokeDasharray="4 4" vectorEffect="non-scaling-stroke" />
      <line data-guide="y" visibility="hidden" stroke="currentColor" strokeDasharray="4 4" vectorEffect="non-scaling-stroke" />
      {editable && panel && !panel.missing ? <g data-edit-frame="">
        <g transform={`rotate(${panel.angle} ${panel.cx ?? 0} ${panel.cy ?? 0})`}>
          <rect {...panel.body} fill="none" stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke" pointerEvents="none" />
          {layout.kind === 'logical' ? handles.map(handle => {
            const x = panel.body.x + panel.body.width * handle.x, y = panel.body.y + panel.body.height * handle.y;
            return <g key={handle.name} data-edit-id={panel.id} data-resize={handle.name} role="button" tabIndex={0}
              aria-label={`Resize ${label(panel.id)} ${handle.name}. Use Width and Height fields for exact size.`}
              className="focus-visible:outline-2 focus-visible:outline-[var(--stage-sel)]"
              style={{ cursor: `${handle.name}-resize`, touchAction: 'none' }}>
              <rect x={x - 12 * px} y={y - 12 * px} width={24 * px} height={24 * px} fill="transparent" />
              <rect x={x - 5 * px} y={y - 5 * px} width={10 * px} height={10 * px}
                fill="var(--stage-text)" stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
            </g>;
          }) : <g data-edit-id={panel.id} data-rotate="" role="button" tabIndex={0}
            aria-label={`Rotate ${label(panel.id)}. Press R to turn 90 degrees.`}
            onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); gesture.rotate(90); } }}
            className="focus-visible:outline-2 focus-visible:outline-[var(--stage-sel)]"
            style={{ cursor: 'crosshair', touchAction: 'none' }}>
            <line x1={panel.cx} y1={panel.body.y} x2={panel.cx} y2={panel.body.y - 22 * px}
              stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
            <circle cx={panel.cx} cy={panel.body.y - 22 * px} r={12 * px} fill="transparent" />
            <circle data-rotate-knob="" cx={panel.cx} cy={panel.body.y - 22 * px} r={5 * px}
              fill="var(--stage-text)" stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
          </g>}
        </g>
      </g> : null}
    </svg>
    {editable ? <>
      <div role="toolbar" aria-label="Canvas tools" className="absolute left-2 top-2 flex flex-col gap-1 rounded-[var(--radius-control)] bg-[var(--surface)] p-1 text-[var(--text)] shadow-[var(--shadow-float)]">
        <button type="button" aria-label="Move selected tablet" aria-pressed="true" title="Move. Arrow keys nudge; Shift moves ten steps."
          className="grid size-[var(--control-h)] place-items-center rounded bg-[var(--sel-bg)] text-[var(--sel-text)]" onClick={() => svg.current?.focus()}><MousePointer2 size={18} /></button>
        <button type="button" aria-label="Snap to grid and edges" aria-pressed={snap} title="Snap to grid and edges. Alt pauses snapping."
          className={`grid size-[var(--control-h)] place-items-center rounded hover:bg-[var(--tonal)] ${snap ? 'bg-[var(--sel-bg)] text-[var(--sel-text)]' : ''}`} onClick={() => onSnapChange(!snap)}><Magnet size={18} /></button>
        <button type="button" aria-label="Undo layout edit" disabled={!draft?.undo.length} className="grid size-[var(--control-h)] place-items-center rounded hover:bg-[var(--tonal)] disabled:opacity-50" onClick={() => gesture.history('undo')}><Undo2 size={18} /></button>
        <button type="button" aria-label="Redo layout edit" disabled={!draft?.redo.length} className="grid size-[var(--control-h)] place-items-center rounded hover:bg-[var(--tonal)] disabled:opacity-50" onClick={() => gesture.history('redo')}><Redo2 size={18} /></button>
      </div>
      {selected ? <div data-layout-readout="" className="pointer-events-none absolute right-2 top-2 max-w-[calc(100%-4rem)] rounded bg-[var(--stage-sel)] px-2 py-1 text-[13px] font-semibold text-[var(--stage)]">{layout.kind === 'physical' ? <span>Centre + nudge · </span> : null}<span data-position-readout="">{positionReadout(layout, selected)}</span></div> : null}
      {selected ? <div className="absolute bottom-2 right-2 flex gap-1 rounded bg-[var(--surface)] p-1 text-[var(--text)] shadow-[var(--shadow-float)]">
        <button type="button" aria-label="Rotate selected tablet minus 90 degrees" className="grid size-[var(--control-h)] place-items-center rounded hover:bg-[var(--tonal)]" onClick={() => gesture.rotate(-90)}><RotateCcw size={18} /></button>
        <button type="button" aria-label="Rotate selected tablet 90 degrees" className="grid size-[var(--control-h)] place-items-center rounded hover:bg-[var(--tonal)]" onClick={() => gesture.rotate(90)}><RotateCw size={18} /></button>
      </div> : null}
    </> : null}
    <p id={helpId} className="sr-only">Select a tablet. Arrow keys move by the step; Shift moves ten steps. R turns 90 degrees. Escape cancels a drag. Control or Command Z undoes. Use numeric fields to move, resize or turn without dragging.</p>
    <div className="sr-only" role="status" aria-label="Layout updates" aria-live="polite" aria-atomic="true">{gesture.message}</div>
  </>;
}
