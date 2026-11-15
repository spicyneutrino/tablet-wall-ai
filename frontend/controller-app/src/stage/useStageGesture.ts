import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent, PointerEvent, RefObject } from 'react';
import { DeviceIdSchema } from '../api/devices';
import type { DeviceId } from '../api/devices';
import type { Layout, LogicalLayout, Placement } from '../api/layouts';
import { fitLogical, layoutSignature, rotateLogical } from '../domain/layout';
import { edgeThreshold, fitBounds, snapLogical, validateLogicalField } from '../domain/physicalSizing';
import { panels } from '../domain/stagePanels';
import type { PlacedPanel } from '../domain/stagePanels';
import { selectStageEditable } from '../state/hooks';
import { editArrangement, selectDevice } from '../state/store';
import type { WallStore, WallStoreApi } from '../state/store';
import type { WallSvgProps } from './WallSvg';

export type ResizeHandle = 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w' | 'nw';
export type StageChange =
  | { type: 'move'; dx: number; dy: number; nudge?: boolean }
  | { type: 'resize'; dx: number; dy: number; handle: ResizeHandle }
  | { type: 'rotate'; angle: number };
type Snap = { step: number; enabled: boolean; scale: number };
type ChangeResult = { layout: Layout; error?: undefined } | { error: string; layout?: undefined };
const round = (value: number, digits = 2) => Math.round(value * 10 ** digits) / 10 ** digits;
export const normalizeAngle = (angle: number) => round((angle % 360 + 360) % 360);
function sizingPlacement(slot: Placement) {
  const { top, right, bottom, left } = slot.bezel;
  return { x: slot.x, y: slot.y, w: slot.w, h: slot.h, bezel: { top, right, bottom, left } };
}
function sizingLayout(layout: LogicalLayout) {
  return { ...layout, placements: Object.fromEntries(Object.entries(layout.placements).map(([id, slot]) => [id, sizingPlacement(slot)])) };
}

export function changeStageLayout(layout: Layout, id: DeviceId, change: StageChange, snap: Snap): ChangeResult {
  if (layout.kind === 'physical') {
    const slot = layout.slots[id];
    if (!slot || change.type === 'resize') return { layout };
    const next = { ...slot };
    if (change.type === 'rotate') next.mount_angle = normalizeAngle(change.angle);
    else if (change.nudge) {
      next.nudge_x_mm = round(slot.nudge_x_mm + change.dx, 3);
      next.nudge_y_mm = round(slot.nudge_y_mm + change.dy, 3);
    } else {
      next.center_x_mm = round(slot.center_x_mm + change.dx);
      next.center_y_mm = round(slot.center_y_mm + change.dy);
    }
    return { layout: { ...layout, slots: { ...layout.slots, [id]: next } } };
  }
  const slot = layout.placements[id];
  if (!slot) return { layout };
  const geometry = sizingLayout(layout), geometrySlot = sizingPlacement(slot);
  let next = { ...slot };
  if (change.type === 'rotate') {
    const turns = normalizeAngle(change.angle) / 90;
    for (let i = 0; i < turns; i++) next = { ...next, ...rotateLogical(next) };
  } else if (change.type === 'move') {
    next = { ...next, ...snapLogical({ ...geometrySlot, x: next.x + change.dx, y: next.y + change.dy }, geometry,
      { id, step: snap.step, enabled: snap.enabled, threshold: edgeThreshold(8, snap.scale) }) };
  } else {
    const west = change.handle.includes('w'), north = change.handle.includes('n');
    const horizontal = west || change.handle.includes('e'), vertical = north || change.handle.includes('s');
    const w = Math.round(slot.w + (horizontal ? (west ? -change.dx : change.dx) : 0));
    const h = Math.round(slot.h + (vertical ? (north ? -change.dy : change.dy) : 0));
    for (const [field, value] of [['w', w], ['h', h]] as const) {
      const result = validateLogicalField(field, value, geometry, geometrySlot);
      if (!result.valid) return { error: result.message };
    }
    const resized = snapLogical({ ...geometrySlot, w, h }, geometry, { mode: 'resize', step: snap.step, enabled: snap.enabled });
    if (resized) next = { ...next, w: horizontal ? resized.w : slot.w, h: vertical ? resized.h : slot.h };
    if (west) next.x = slot.x + slot.w - next.w;
    if (north) next.y = slot.y + slot.h - next.h;
    for (const field of ['w', 'h'] as const) {
      const result = validateLogicalField(field, next[field], geometry, sizingPlacement(next));
      if (!result.valid) return { error: result.message };
    }
  }
  return { layout: { ...layout, placements: { ...layout.placements, [id]: next } } };
}

export const canEditStage = (state: WallStore) => selectStageEditable(state)
  && state.server.supported && !state.server.busy;
export function fitStageLayout(layout: Layout, profileFor: WallSvgProps['profileFor']) {
  const next = structuredClone(layout);
  if (next.sizing.mode !== 'tablets') return { layout: next, warning: '' };
  if (next.kind === 'logical') {
    fitLogical(next);
    return { layout: next, warning: '' };
  }
  const fitted = fitBounds(next.slots, (id, revision) => {
    const profile = profileFor(id, revision);
    return profile ? { ...profile, bezels: { top: profile.bezels?.top ?? 0, right: profile.bezels?.right ?? 0,
      bottom: profile.bezels?.bottom ?? 0, left: profile.bezels?.left ?? 0 } } : null;
  }, next.sizing.padding);
  if (fitted.bounds) next.bounds = fitted.bounds;
  return { layout: next, warning: fitted.error ?? '' };
}
type Operation = { type: 'move' } | { type: 'rotate' } | { type: 'resize'; handle: ResizeHandle };
type Gesture = {
  id: DeviceId; pointer: number; svg: SVGSVGElement; inverse: DOMMatrix; start: DOMPoint;
  client: { x: number; y: number }; operation: Operation; before: NonNullable<WallStore['arrangement']>;
  panel: PlacedPanel; startAngle: number; moved: boolean; result: ChangeResult;
};
function operationFor(target: Element): Operation {
  const handle = target.closest('[data-resize]')?.getAttribute('data-resize');
  if (handle === 'n' || handle === 'ne' || handle === 'e' || handle === 'se'
    || handle === 's' || handle === 'sw' || handle === 'w' || handle === 'nw') return { type: 'resize', handle };
  return { type: target.closest('[data-rotate]') ? 'rotate' : 'move' };
}
function clearPreview(root: HTMLElement | null) {
  root?.querySelectorAll<SVGElement>('[data-device-id], [data-edit-frame], [data-edit-hit]').forEach(node => {
    node.style.removeProperty('transform'); node.style.removeProperty('transform-origin');
  });
  root?.querySelector('[data-edit-overlay]')?.removeAttribute('data-dragging');
  root?.querySelectorAll('[data-guide]').forEach(node => node.setAttribute('visibility', 'hidden'));
}
function restoreReadout(root: HTMLElement | null, gesture: Gesture) {
  const readout = root?.querySelector('[data-position-readout]');
  if (readout) readout.textContent = positionReadout(gesture.before.draft, gesture.id);
}
function showGuides(root: HTMLElement | null, layout: Layout, id: DeviceId) {
  if (layout.kind !== 'logical') return;
  const slot = layout.placements[id];
  if (!slot) return;
  const others = Object.entries(layout.placements).filter(([key]) => key !== id).map(([, value]) => value);
  const edges = (p: Placement, axis: 'x' | 'y') => axis === 'x'
    ? [p.x, p.x + p.w, p.x + p.bezel.left, p.x + p.w - p.bezel.right]
    : [p.y, p.y + p.h, p.y + p.bezel.top, p.y + p.h - p.bezel.bottom];
  for (const axis of ['x', 'y'] as const) {
    const targets = [0, axis === 'x' ? layout.width : layout.height, ...others.flatMap(other => edges(other, axis))];
    const match = edges(slot, axis).find(value => targets.includes(value));
    const line = root?.querySelector(`[data-guide="${axis}"]`);
    if (!line) continue;
    line.setAttribute('visibility', match === undefined ? 'hidden' : 'visible');
    if (match === undefined) continue;
    line.setAttribute('x1', String(axis === 'x' ? match : 0)); line.setAttribute('x2', String(axis === 'x' ? match : layout.width));
    line.setAttribute('y1', String(axis === 'y' ? match : 0)); line.setAttribute('y2', String(axis === 'y' ? match : layout.height));
  }
}
function release(gesture: Gesture) {
  if (gesture.svg.hasPointerCapture(gesture.pointer)) gesture.svg.releasePointerCapture(gesture.pointer);
}

export function useStageGesture({ store, rootRef, profileFor, step = 1, snap = true, labelFor }: {
  store: WallStoreApi; profileFor: WallSvgProps['profileFor']; step?: number; snap?: boolean;
  labelFor: (id: string) => string; rootRef: RefObject<HTMLElement | null>;
}) {
  const active = useRef<Gesture | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const sequence = useRef(0);
  function announce(text: string) { setMessage(`${text} (${++sequence.current})`); }
  function cancel() {
    const gesture = active.current;
    if (!gesture) return;
    active.current = null;
    clearPreview(rootRef.current); restoreReadout(rootRef.current, gesture); release(gesture);
    announce(`${labelFor(gesture.id)} move cancelled.`);
  }
  useEffect(() => {
    const root = rootRef.current;
    function abort() {
      const gesture = active.current;
      if (!gesture) return;
      active.current = null;
      clearPreview(root); restoreReadout(root, gesture); release(gesture);
      setMessage(`Move cancelled because the wall view changed. (${++sequence.current})`);
    }
    const unsubscribe = store.subscribe(state => {
      if (active.current && (!canEditStage(state) || state.arrangement !== active.current.before
        || state.ui.selected !== active.current.id)) abort();
    });
    const observer = new ResizeObserver(abort);
    const svg = root?.querySelector('[data-edit-overlay]');
    if (svg) observer.observe(svg);
    window.addEventListener('blur', abort);
    window.addEventListener('resize', abort);
    window.addEventListener('scroll', abort, true);
    return () => {
      unsubscribe(); observer.disconnect();
      window.removeEventListener('blur', abort); window.removeEventListener('resize', abort);
      window.removeEventListener('scroll', abort, true);
      const gesture = active.current;
      active.current = null;
      clearPreview(root);
      if (gesture) release(gesture);
    };
  }, [store, rootRef]);

  function commit(result: ChangeResult, verb: string) {
    if (result.error !== undefined) { setError(result.error); announce(result.error); return; }
    setError('');
    const before = store.getState().arrangement;
    if (!before || layoutSignature(before.draft) === layoutSignature(result.layout)) return;
    const fitted = fitStageLayout(result.layout, profileFor);
    editArrangement(store, { type: 'edit', layout: fitted.layout });
    setError(fitted.warning);
    if (store.getState().arrangement !== before) announce(`${labelFor(store.getState().ui.selected ?? '')} ${verb}.`);
  }
  function changeSelected(change: StageChange) {
    const state = store.getState();
    if (!canEditStage(state) || active.current || !state.arrangement || !state.ui.selected) return;
    commit(changeStageLayout(state.arrangement.draft, state.ui.selected, change,
      { step, enabled: false, scale: 1 }), change.type === 'rotate' ? 'rotated' : change.type === 'resize' ? 'resized' : 'moved');
  }
  function nudge(dx: number, dy: number) { changeSelected({ type: 'move', dx, dy, nudge: true }); }
  function rotate(turn: number) {
    const state = store.getState(), layout = state.arrangement?.draft, id = state.ui.selected;
    if (!layout || !id) return;
    const angle = layout.kind === 'physical' ? (layout.slots[id]?.mount_angle ?? 0) + turn : turn;
    changeSelected({ type: 'rotate', angle });
  }
  function history(type: 'undo' | 'redo') {
    if (!canEditStage(store.getState()) || active.current) return;
    editArrangement(store, { type }); setError(''); announce(type === 'undo' ? 'Layout edit undone.' : 'Layout edit redone.');
  }
  function setField(field: string, raw: string) {
    const state = store.getState(), layout = state.arrangement?.draft, id = state.ui.selected;
    if (!canEditStage(state) || active.current || !layout || !id) return;
    if (layout.kind === 'logical') {
      const slot = layout.placements[id];
      if (!slot) return;
      const result = validateLogicalField(field, raw, sizingLayout(layout), sizingPlacement(slot));
      if (!result.valid) { setError(result.message); announce(result.message); return; }
      const next = field.startsWith('bezel-') ? { ...slot, bezel: { ...slot.bezel, [field.slice(6)]: result.value } }
        : { ...slot, [field]: result.value };
      commit({ layout: { ...layout, placements: { ...layout.placements, [id]: next } } }, 'updated');
    } else {
      const slot = layout.slots[id], value = Number(raw);
      if (!slot) return;
      if (!raw.trim() || !Number.isFinite(value)) { setError('Enter a finite number.'); return; }
      commit({ layout: { ...layout, slots: { ...layout.slots, [id]: { ...slot,
        [field]: field === 'mount_angle' ? normalizeAngle(value) : value } } } }, 'updated');
    }
  }
  function remove() {
    const state = store.getState(), layout = state.arrangement?.draft, id = state.ui.selected;
    if (!canEditStage(state) || active.current || !layout || !id) return;
    if (!window.confirm(`Remove ${labelFor(id)} from the draft wall?`)) return;
    const next = structuredClone(layout);
    if (next.kind === 'physical') delete next.slots[id]; else delete next.placements[id];
    commit({ layout: next }, 'removed'); selectDevice(store, null);
    rootRef.current?.querySelector<SVGSVGElement>('[data-edit-overlay]')?.focus();
  }
  function onPointerDown(event: PointerEvent<SVGSVGElement>) {
    if (event.button !== 0 || !event.isPrimary || active.current || !(event.target instanceof Element)) return;
    const id = event.target.closest('[data-edit-id]')?.getAttribute('data-edit-id');
    const layout = store.getState().arrangement?.draft;
    const parsed = DeviceIdSchema.safeParse(id);
    if (!layout || !parsed.success || !(layout.kind === 'physical' ? layout.slots[parsed.data] : layout.placements[parsed.data])) {
      selectDevice(store, null); return;
    }
    const currentId = parsed.data;
    selectDevice(store, currentId);
    event.target.closest<SVGElement>('[data-edit-id]')?.focus({ preventScroll: true });
    const state = store.getState(), before = state.arrangement;
    if (!canEditStage(state) || !before) return;
    const matrix = event.currentTarget.getScreenCTM();
    const panel = panels(before.draft, profileFor).find(item => item.id === currentId);
    if (!matrix || !panel || panel.missing) return;
    const inverse = matrix.inverse(), start = new DOMPoint(event.clientX, event.clientY).matrixTransform(inverse);
    const cx = panel.cx ?? panel.body.x + panel.body.width / 2, cy = panel.cy ?? panel.body.y + panel.body.height / 2;
    active.current = { id: currentId, pointer: event.pointerId, svg: event.currentTarget, inverse, start,
      client: { x: event.clientX, y: event.clientY }, operation: operationFor(event.target), before, panel,
      startAngle: Math.atan2(start.y - cy, start.x - cx) * 180 / Math.PI, moved: false, result: { layout: before.draft } };
    event.currentTarget.setPointerCapture(event.pointerId); event.preventDefault();
  }
  function onPointerMove(event: PointerEvent<SVGSVGElement>) {
    const gesture = active.current;
    if (!gesture || gesture.pointer !== event.pointerId) return;
    if (Math.hypot(event.clientX - gesture.client.x, event.clientY - gesture.client.y) <= 3 && !gesture.moved) return;
    gesture.moved = true;
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(gesture.inverse);
    const dx = point.x - gesture.start.x, dy = point.y - gesture.start.y;
    const { panel, operation, before, id } = gesture;
    let change: StageChange;
    if (operation.type === 'rotate') {
      const cx = panel.cx ?? 0, cy = panel.cy ?? 0;
      const delta = (Math.atan2(point.y - cy, point.x - cx) * 180 / Math.PI - gesture.startAngle + 540) % 360 - 180;
      const raw = panel.angle + delta;
      change = { type: 'rotate', angle: event.shiftKey ? raw : Math.round(raw / 15) * 15 };
    } else change = operation.type === 'resize' ? { ...operation, dx, dy } : { type: 'move', dx, dy, nudge: event.altKey };
    const scale = 1 / Math.hypot(gesture.inverse.a, gesture.inverse.b);
    gesture.result = changeStageLayout(before.draft, id, change, { step, enabled: snap && !event.altKey, scale });
    if (gesture.result.layout) {
      const next = panels(gesture.result.layout, profileFor).find(item => item.id === id);
      if (next && !next.missing) {
        let transform: string;
        if (operation.type === 'rotate') {
          transform = `translate(${panel.cx}px, ${panel.cy}px) rotate(${next.angle - panel.angle}deg) translate(${-panel.cx!}px, ${-panel.cy!}px)`;
        } else if (operation.type === 'resize') {
          transform = `translate(${next.body.x}px, ${next.body.y}px) scale(${next.body.width / panel.body.width}, ${next.body.height / panel.body.height}) translate(${-panel.body.x}px, ${-panel.body.y}px)`;
        } else transform = `translate(${next.body.x - panel.body.x}px, ${next.body.y - panel.body.y}px)`;
        rootRef.current?.querySelectorAll<SVGElement>('[data-device-id], [data-edit-frame], [data-edit-hit]').forEach(node => {
          if (node.getAttribute('data-device-id') === id || node.hasAttribute('data-edit-frame') || node.getAttribute('data-edit-hit') === id) {
            node.style.transformOrigin = '0 0'; node.style.transform = transform;
          }
        });
        gesture.svg.setAttribute('data-dragging', 'true');
        const readout = rootRef.current?.querySelector('[data-position-readout]');
        if (readout) readout.textContent = positionReadout(gesture.result.layout, id);
        if (snap && !event.altKey && operation.type === 'move') showGuides(rootRef.current, gesture.result.layout, id);
        else rootRef.current?.querySelectorAll('[data-guide]').forEach(node => node.setAttribute('visibility', 'hidden'));
      }
    }
    event.preventDefault();
  }
  function onPointerUp(event: PointerEvent<SVGSVGElement>) {
    const gesture = active.current;
    if (!gesture || gesture.pointer !== event.pointerId) return;
    active.current = null; clearPreview(rootRef.current); restoreReadout(rootRef.current, gesture); release(gesture);
    if (gesture.moved) commit(gesture.result, gesture.operation.type === 'move' ? 'moved' : gesture.operation.type === 'rotate' ? 'rotated' : 'resized');
  }
  function onKeyDown(event: KeyboardEvent<HTMLElement | SVGSVGElement>) {
    if (event.key === 'Escape' && active.current) { event.preventDefault(); cancel(); return; }
    if (event.target instanceof Element && event.target.closest('input, select, textarea, [contenteditable="true"]')) return;
    if (active.current) return;
    if ((event.ctrlKey || event.metaKey) && ['z', 'y'].includes(event.key.toLowerCase())) {
      event.preventDefault(); history(event.shiftKey || event.key.toLowerCase() === 'y' ? 'redo' : 'undo'); return;
    }
    if (event.altKey || event.metaKey || event.ctrlKey) return;
    const amount = step * (event.shiftKey ? 10 : 1);
    const moves: Record<string, [number, number]> = { ArrowLeft: [-amount, 0], ArrowRight: [amount, 0], ArrowUp: [0, -amount], ArrowDown: [0, amount] };
    const move = moves[event.key];
    if (move) {
      event.preventDefault();
      const operation = event.target instanceof Element ? operationFor(event.target) : { type: 'move' };
      if (operation.type === 'resize' && 'handle' in operation) changeSelected({ type: 'resize', handle: operation.handle, dx: move[0], dy: move[1] });
      else nudge(...move);
    }
    else if (event.key.toLowerCase() === 'r') { event.preventDefault(); rotate(event.shiftKey ? -90 : 90); }
    else if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); remove(); }
    else if (event.key === 'Escape') selectDevice(store, null);
  }
  function onPointerCancel(event: PointerEvent<SVGSVGElement>) {
    if (active.current?.pointer === event.pointerId) cancel();
  }
  return { message, error, onPointerDown, onPointerMove, onPointerUp,
    onPointerCancel, onLostPointerCapture: onPointerCancel, onKeyDown, nudge, rotate, history, setField, remove };
}

export function positionReadout(layout: Layout, id: DeviceId): string {
  if (layout.kind === 'physical') {
    const slot = layout.slots[id];
    return slot ? `x ${round(slot.center_x_mm + slot.nudge_x_mm)}  y ${round(slot.center_y_mm + slot.nudge_y_mm)} mm  ${slot.mount_angle}°` : '';
  }
  const slot = layout.placements[id];
  return slot ? `x ${slot.x}  y ${slot.y}  ${slot.w} × ${slot.h}` : '';
}
