import { useRef, useState } from 'react';
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp } from 'lucide-react';
import { useStore } from 'zustand';
import { DeviceIdSchema } from '../api/devices';
import { LayoutSchema } from '../api/layouts';
import type { Scene } from '../api/scene';
import { createWallStore } from '../state/store';
import { createArrangement } from '../state/drafts/arrangement';
import { canEditStage, useStageGesture } from '../stage/useStageGesture';
import { EditOverlay } from '../stage/EditOverlay';
import { WallSvg } from '../stage/WallSvg';
import type { WallStatus } from '../stage/WallSvg';
import type { WallFixture } from '../../e2e/fixtures/walls';
import { walls } from '../../e2e/fixtures/walls';
import { fleet } from '../../e2e/fixtures/fleet';

function createFixtureStore(fixture: WallFixture) {
  const source = fixture.layout;
  const entries = Object.entries(source.kind === 'physical' ? source.slots ?? {} : source.placements ?? {});
  const mapped = Object.fromEntries(entries.map(([, value], index) => [
    fleet[index]?.id ?? `00000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
    source.kind === 'physical' ? { mount_angle: 0, nudge_x_mm: 0, nudge_y_mm: 0,
      profile_revision: 1, calibration_revision: 1, ...value } : value,
  ]));
  const layout = LayoutSchema.parse({ ...source, [source.kind === 'physical' ? 'slots' : 'placements']: mapped,
    sizing: { mode: 'fixed', padding: 0 } });
  const store = createWallStore();
  store.setState(state => ({ arrangement: createArrangement(layout, null),
    server: { ...state.server, supported: true }, ui: { ...state.ui, editLayout: true } }));
  return store;
}

function NumericField({ label, value, field, gesture }: {
  label: string; value: number; field: string; gesture: ReturnType<typeof useStageGesture>;
}) {
  const [draft, setDraft] = useState({ value, raw: String(value) });
  if (draft.value !== value) setDraft({ value, raw: String(value) });
  const raw = draft.raw;
  return <label className="flex min-w-0 flex-col gap-1 text-sm">{label}
    <input type="number" step="any" value={raw} aria-describedby={gesture.error ? 'stage-field-error' : undefined}
      aria-invalid={gesture.error ? true : undefined}
      className="w-full min-w-0 rounded-[var(--radius-control)] border border-[var(--control)] bg-[var(--surface)] px-2 py-1 text-base"
      onChange={event => setDraft({ value, raw: event.target.value })} onBlur={() => gesture.setField(field, raw)}
      onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); gesture.setField(field, raw); } }} />
  </label>;
}

export default function EditableStageFixture({ fixture, content }: { fixture: WallFixture; content: Scene | null }) {
  const [store] = useState(() => createFixtureStore(fixture));
  const [snap, setSnap] = useState(true);
  const [step, setStep] = useState(1);
  const rootRef = useRef<HTMLElement>(null);
  const arrangement = useStore(store, state => state.arrangement)!;
  const selected = useStore(store, state => state.ui.selected);
  const editable = useStore(store, canEditStage);
  const editing = useStore(store, state => state.ui.editLayout);
  const layout = arrangement.draft;
  const base = arrangement.base;
  const ids = Object.keys(base.kind === 'physical' ? base.slots : base.placements);
  const labelFor = (id: string) => `Tablet ${ids.indexOf(id) + 1}`;
  const statuses = Object.fromEntries(ids.map((id, index): [string, WallStatus] =>
    [id, { status: 'preview', text: 'Local preview', label: labelFor(id), number: index + 1 }]));
  const profileFor = () => fixture.profile;
  const gesture = useStageGesture({ store, rootRef, profileFor, step, snap, labelFor });
  const shown = editing ? layout : base;
  const slot = selected && layout.kind === 'physical' ? layout.slots[selected] : null;
  const placement = selected && layout.kind === 'logical' ? layout.placements[selected] : null;
  const fields = slot ? [['X (mm)', 'center_x_mm', slot.center_x_mm], ['Y (mm)', 'center_y_mm', slot.center_y_mm],
    ['Turn (degrees)', 'mount_angle', slot.mount_angle], ['Nudge X (mm)', 'nudge_x_mm', slot.nudge_x_mm], ['Nudge Y (mm)', 'nudge_y_mm', slot.nudge_y_mm]] as const
    : placement ? [['X', 'x', placement.x], ['Y', 'y', placement.y], ['Width', 'w', placement.w], ['Height', 'h', placement.h],
      ['Top bezel', 'bezel-top', placement.bezel.top], ['Right bezel', 'bezel-right', placement.bezel.right],
      ['Bottom bezel', 'bezel-bottom', placement.bezel.bottom], ['Left bezel', 'bezel-left', placement.bezel.left]] as const : [];

  return <main aria-label="Editable stage fixture" className="grid min-w-0 gap-4 p-4">
    <h1 className="t-title">{fixture.name}</h1>
    <nav aria-label="Fixture controls" className="flex flex-wrap items-center gap-4">
      <label>Wall <select value={fixture.name} onChange={event => {
        const query = new URLSearchParams(location.search); query.set('wall', event.target.value); location.search = query.toString();
      }}>{walls.map(wall => <option key={wall.name}>{wall.name}</option>)}</select></label>
      <button type="button" aria-pressed={editing} onClick={() => store.setState(state => ({ ui: { ...state.ui, editLayout: !state.ui.editLayout } }))}>Edit layout</button>
      <a href={`${location.pathname}?wall=${fixture.name}#stage-fixture`}>Read-only fixture</a>
    </nav>
    <section ref={rootRef} onKeyDown={gesture.onKeyDown} aria-label="Layout editor" className="grid min-w-0 gap-4">
      <div data-stage="preview" className="relative grid min-h-0 w-full grid-cols-[minmax(0,1fr)]"
        style={{ aspectRatio: '16 / 9', maxBlockSize: '70dvh' }}>
        <WallSvg layout={shown} profileFor={profileFor} content={content} statuses={statuses}
          selected={editable ? undefined : selected ?? undefined} interactive={editable} />
        <EditOverlay store={store} layout={shown} selected={selected} profileFor={profileFor} statuses={statuses}
          editable={editable} gesture={gesture} snap={snap} onSnapChange={setSnap} />
      </div>
      {editable ? <div aria-label="Numeric layout controls" className="grid gap-4">
        <div className="flex flex-wrap items-center gap-4">
          <label>Tablet <select aria-label="Selected tablet" value={selected ?? ''} onChange={event => store.setState(state => ({ ui: { ...state.ui,
            selected: event.target.value ? DeviceIdSchema.parse(event.target.value) : null } }))}>
            <option value="">Select a tablet</option>{ids.map(id => <option key={id} value={id}>{labelFor(id)}</option>)}
          </select></label>
          <label>Step <select aria-label="Step" value={step} onChange={event => setStep(Number(event.target.value))}>
            <option value={1}>1 {layout.kind === 'physical' ? 'mm' : 'unit'}</option><option value={10}>10 {layout.kind === 'physical' ? 'mm' : 'units'}</option>
          </select></label>
        </div>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {fields.map(([label, field, value]) => <NumericField key={`${selected}-${field}`} label={label} field={field} value={value} gesture={gesture} />)}
        </div>
        {gesture.error ? <p id="stage-field-error" role="alert" className="text-[var(--err)]">{gesture.error}</p> : null}
        {selected ? <div role="group" aria-label="Nudge selected tablet" className="flex flex-wrap items-center gap-2">
          {([['left', -step, 0, ArrowLeft], ['up', 0, -step, ArrowUp], ['down', 0, step, ArrowDown], ['right', step, 0, ArrowRight]] as const)
            .map(([name, dx, dy, Icon]) => <button key={name} type="button" aria-label={`Nudge ${name}`} className="grid size-10 place-items-center rounded bg-[var(--surface-2)]" onClick={() => gesture.nudge(dx, dy)}><Icon size={18} /></button>)}
          <button type="button" onClick={gesture.remove}>Remove placement…</button>
          {slot && fixture.profile ? <p>Size comes from the pinned profile. Bezels are read-only.</p> : null}
        </div> : null}
        <p className="text-sm text-[var(--muted)]">Arrow keys move one step; Shift moves ten. R turns 90°. Escape cancels a drag. Alt pauses logical snapping or adjusts physical nudge.</p>
      </div> : <p>On wall. Editing is off.</p>}
    </section>
    <output aria-label="Draft layout" className="sr-only">{JSON.stringify({ layout, undo: arrangement.undo.length, redo: arrangement.redo.length, version: arrangement.version })}</output>
  </main>;
}
