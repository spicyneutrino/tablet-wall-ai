import { createContext, useContext, useRef, useState } from 'react';
import type { ReactNode, RefObject } from 'react';
import { Maximize, Package, Grid2X2, Scan, Settings2 } from 'lucide-react';
import { LayoutSchema } from '../../api/layouts';
import type { Layout, LogicalLayout, Placement } from '../../api/layouts';
import { arrangeLogical } from '../../domain/layout';
import { freshViewport, matchScreenShape, packSlots, validateLogicalField } from '../../domain/physicalSizing';
import { editArrangement, useTheirs as discardDraft } from '../../state/store';
import { useWallStore } from '../../state/hooks';
import { canEditStage, fitStageLayout, useStageGesture } from '../../stage/useStageGesture';
import { Button } from '../../ui/Button';
import { Field } from '../../ui/Field';
import { Input, Select } from '../../ui/Input';
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuItem, DropdownMenuPortal, DropdownMenuTrigger } from '../../ui/DropdownMenu';
import { ModalDialog } from '../../ui/ModalDialog';
import { useShell } from './ShellContext';
import { useShellView } from './useShellView';

export function layoutButton(disabled: boolean, reason = 'Editing is unavailable while the wall is busy or disconnected.') {
  return disabled ? { disabled: true as const, disabledReason: reason } : { disabled: false as const };
}
function geometryPlacement(placement: Placement) {
  const { top, right, bottom, left } = placement.bezel;
  return { ...placement, bezel: { top, right, bottom, left } };
}
function geometryLayout(layout: LogicalLayout) {
  return { ...layout, placements: Object.fromEntries(Object.entries(layout.placements).map(([id, value]) => [id, geometryPlacement(value)])) };
}
function useEditor(rootRef: RefObject<HTMLDivElement | null>) {
  const { store } = useShell();
  const { profileFor, tablets } = useShellView();
  const [snap, setSnap] = useState(true);
  const [step, setStep] = useState(1);
  const [error, setError] = useState('');
  const gesture = useStageGesture({ store, rootRef, profileFor, snap, step,
    labelFor: id => tablets.find(tablet => tablet.id === id)?.name ?? 'Tablet' });
  const enabled = useWallStore(store, state => canEditStage(state) && !state.server.rosterUnreachable && !state.server.uncertain);
  function commit(layout: Layout) {
    if (!enabled) return;
    const fitted = fitStageLayout(layout, profileFor);
    const parsed = LayoutSchema.safeParse(fitted.layout);
    if (!parsed.success) { setError(parsed.error.issues[0]?.message ?? 'Review the wall dimensions.'); return; }
    setError(fitted.warning);
    if (!fitted.warning) editArrangement(store, { type: 'edit', layout: parsed.data });
  }
  function discard() {
    discardDraft(store, { kind: 'arrangement' });
    store.setState(state => ({ ui: { ...state.ui, editLayout: false } }));
    setError('');
    document.querySelector<HTMLButtonElement>('[aria-label="Edit layout"]')?.focus();
  }
  return { snap, setSnap, step, setStep, gesture, enabled, error, setError, commit, discard };
}
const EditorContext = createContext<ReturnType<typeof useEditor> | null>(null);
export function ArrangementEditor({ children }: { children: ReactNode }) {
  const rootRef = useRef<HTMLDivElement>(null);
  const editor = useEditor(rootRef);
  return <EditorContext value={editor}><div ref={rootRef} className="contents" onKeyDown={event => {
    if (editor.enabled && event.target instanceof Element && event.target.closest('[data-edit-overlay], [data-placement-controls]')) editor.gesture.onKeyDown(event);
  }}>{children}</div></EditorContext>;
}
export function useArrangementEditor() {
  const editor = useContext(EditorContext);
  if (!editor) throw new Error('Layout controls need the arrangement editor.');
  return editor;
}
export function LayoutNumber({ label, value, onCommit, disabled = false, error }: {
  label: string; value: number; onCommit: (raw: string) => void; disabled?: boolean; error?: string;
}) {
  const [draft, setDraft] = useState({ value, raw: String(value) });
  if (draft.value !== value) setDraft({ value, raw: String(value) });
  return <Field label={label} error={error}>{props => <Input {...props} inputMode="decimal" autoComplete="off"
    value={draft.raw} disabled={disabled} onChange={event => setDraft({ value, raw: event.target.value })}
    onBlur={() => onCommit(draft.raw)} onKeyDown={event => {
      if (event.key === 'Enter') { event.preventDefault(); event.currentTarget.blur(); }
      if (event.key === 'Escape') { event.preventDefault(); setDraft({ value, raw: String(value) }); }
    }} />}</Field>;
}

export default function EditToolbar() {
  const { store } = useShell();
  const { profileFor } = useShellView();
  const { enabled, commit, error, setError, snap, setSnap } = useArrangementEditor();
  const layout = useWallStore(store, state => state.arrangement?.draft);
  const selected = useWallStore(store, state => state.ui.selected);
  const server = useWallStore(store, state => state.server);
  const [panel, setPanel] = useState<'bounds' | 'pack' | 'tile' | null>(null);
  const [columns, setColumns] = useState(2);
  const [rows, setRows] = useState(2);
  const [gap, setGap] = useState(0);
  const [preserveAspect, setPreserveAspect] = useState(true);
  if (!layout) return <p className="t-caption">Wait for the wall layout to load.</p>;
  const device = selected ? server.roster[selected] : null;
  const viewport = freshViewport(device ? { online: device.online, viewport: device.viewport ?? undefined } : null, { stale: !!server.rosterError });
  const matchReason = layout.kind !== 'logical' ? 'Physical size comes from the measured profile.'
    : !selected || !layout.placements[selected] ? 'Select a placed tablet first.' : !viewport.available ? viewport.reason : undefined;
  function arrange() {
    if (!layout || !panel) return;
    try {
      if (layout.kind === 'logical') {
        const ids = Object.keys(layout.placements).sort();
        const aspects = Object.fromEntries(ids.flatMap(id => {
          const device = server.roster[id]?.viewport;
          return device && device.width > 0 && device.height > 0 ? [[id, device.width / device.height]] : [];
        }));
        commit(LayoutSchema.parse(arrangeLogical(layout, ids, { columns, rows, gap, tile: panel === 'tile', preserveAspect, aspects })));
      } else {
        const ordered = Object.fromEntries(Object.entries(layout.slots).sort(([a], [b]) => a.localeCompare(b)));
        const packed = packSlots(ordered, (id, revision) => {
          const profile = profileFor(id, revision);
          if (!profile) return null;
          const { top, right, bottom, left } = profile.bezels;
          return { ...profile, bezels: { top, right, bottom, left } };
        }, columns, gap, layout.sizing.padding);
        if (packed.error !== undefined) { setError(packed.error); return; }
        if (!packed.bounds) { setError('Add tablets before packing the wall.'); return; }
        if (layout.sizing.mode === 'fixed') for (const slot of Object.values(packed.slots)) {
          slot.center_x_mm += layout.bounds.x; slot.center_y_mm += layout.bounds.y;
        }
        commit(LayoutSchema.parse({ ...layout, slots: packed.slots,
          bounds: layout.sizing.mode === 'tablets' ? packed.bounds : layout.bounds }));
      }
      setPanel(null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Review the arrangement settings.'); }
  }
  function boundsField(field: string, raw: string) {
    if (!layout) return;
    const value = Number(raw);
    if (!raw.trim() || !Number.isFinite(value)) { setError('Enter a finite number.'); return; }
    if (layout.kind === 'logical') {
      const result = validateLogicalField(field, raw, geometryLayout(layout));
      if (!result.valid) { setError(result.message); return; }
      commit({ ...layout, [field]: value });
    } else {
      if (['width', 'height'].includes(field) && value <= 0) { setError('Wall dimensions must be positive.'); return; }
      commit({ ...layout, bounds: { ...layout.bounds, [field]: value } });
    }
  }
  const bounds = layout.kind === 'logical' ? { width: layout.width, height: layout.height }
    : { x: layout.bounds.x, y: layout.bounds.y, width: layout.bounds.width, height: layout.bounds.height };
  return <>
    <DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon" aria-label="Layout tools"><Settings2 aria-hidden="true" /></Button></DropdownMenuTrigger>
      <DropdownMenuPortal><DropdownMenuContent align="end" aria-label="Layout tools">
        <DropdownMenuCheckboxItem checked={snap} onCheckedChange={setSnap}>Snap to grid and edges</DropdownMenuCheckboxItem>
        <DropdownMenuItem disabled={!enabled} onSelect={() => commit({ ...layout, sizing: { ...layout.sizing, mode: 'tablets' } })}><Maximize aria-hidden="true" />Fit to tablets</DropdownMenuItem>
        <DropdownMenuItem disabled={!enabled} onSelect={() => { setError(''); setPanel('pack'); }}><Package aria-hidden="true" />Pack</DropdownMenuItem>
        {layout.kind === 'logical' ? <DropdownMenuItem disabled={!enabled} onSelect={() => { setError(''); setPanel('tile'); }}><Grid2X2 aria-hidden="true" />Tile</DropdownMenuItem> : null}
        {layout.kind === 'logical' ? <DropdownMenuItem disabled={!enabled || !!matchReason} aria-description={matchReason} onSelect={() => {
          if (!selected || !viewport.available) return;
          const placement = layout.placements[selected];
          if (!placement) return;
          const result = matchScreenShape(geometryPlacement(placement), viewport.viewport);
          if (result.error !== undefined) setError(result.error);
          else commit({ ...layout, placements: { ...layout.placements, [selected]: { ...placement, ...result.placement } } });
        }}><Scan aria-hidden="true" />Match screen shape</DropdownMenuItem> : null}
        <DropdownMenuItem disabled={!enabled} onSelect={() => { setError(''); setPanel('bounds'); }}><Settings2 aria-hidden="true" />Wall bounds</DropdownMenuItem>
      </DropdownMenuContent></DropdownMenuPortal>
    </DropdownMenu>
    <ModalDialog open={panel !== null} onOpenChange={open => { if (!open) setPanel(null); }} title={panel === 'bounds' ? 'Wall bounds' : panel === 'tile' ? 'Tile tablets' : 'Pack tablets'}>
      {panel === 'bounds' ? <div className="grid gap-4">
        <Field label="Wall sizing">{props => <Select {...props} disabled={!enabled} value={layout.sizing.mode} onChange={event =>
          commit({ ...layout, sizing: { ...layout.sizing, mode: event.target.value === 'tablets' ? 'tablets' : 'fixed' } })}>
          <option value="fixed">Fixed bounds</option><option value="tablets">Fit to tablets</option></Select>}</Field>
        <div className="grid grid-cols-2 gap-3">{Object.entries(bounds).map(([field, value]) => <LayoutNumber key={field}
          label={`Wall ${field}`} value={value} disabled={!enabled || layout.sizing.mode === 'tablets'} onCommit={raw => boundsField(field, raw)} />)}</div>
        <LayoutNumber label="Outer padding" value={layout.sizing.padding} disabled={!enabled || layout.sizing.mode !== 'tablets'} onCommit={raw => {
          const value = Number(raw);
          if (!raw.trim() || !Number.isFinite(value) || value < 0 || layout.kind === 'logical' && !Number.isInteger(value)) { setError('Use nonnegative padding, in whole units for a logical wall.'); return; }
          commit({ ...layout, sizing: { ...layout.sizing, padding: value } });
        }} />
        <Button onClick={() => setPanel(null)}>Done</Button>
      </div> : <form className="grid gap-4" onSubmit={event => { event.preventDefault(); arrange(); }}>
        <p className="t-body">{panel === 'tile' ? 'Fill wall cells with the placed tablets.' : 'Keep tablet sizes and arrange them in rows.'}</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Columns">{props => <Input {...props} type="number" min={1} step={1} required value={columns} onChange={event => setColumns(event.target.valueAsNumber)} />}</Field>
          {layout.kind === 'logical' ? <Field label="Rows">{props => <Input {...props} type="number" min={1} step={1} required value={rows} onChange={event => setRows(event.target.valueAsNumber)} />}</Field> : null}
          <Field label={`Gap (${layout.kind === 'logical' ? 'units' : 'mm'})`}>{props => <Input {...props} type="number" min={0} step={layout.kind === 'logical' ? 1 : 'any'} required value={gap} onChange={event => setGap(event.target.valueAsNumber)} />}</Field>
          {panel === 'tile' ? <Field label="Screen shape">{props => <Select {...props} value={preserveAspect ? 'keep' : 'fill'} onChange={event => setPreserveAspect(event.target.value === 'keep')}>
            <option value="keep">Keep screen shape</option><option value="fill">Fill cells</option></Select>}</Field> : null}
        </div>
        <Button type="submit" {...layoutButton(!enabled)}>{panel === 'tile' ? 'Tile tablets' : 'Pack tablets'}</Button>
      </form>}
      {error ? <p role="alert" className="t-caption text-[var(--err)]">{error}</p> : null}
    </ModalDialog>
  </>;
}
