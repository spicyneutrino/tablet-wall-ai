import { useState } from 'react';
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, RotateCcw, RotateCw } from 'lucide-react';
import { useWallStore } from '../../state/hooks';
import { Button } from '../../ui/Button';
import { Field } from '../../ui/Field';
import { Switch } from '../../ui/Input';
import { useShell } from '../preview/ShellContext';
import { layoutButton, LayoutNumber, useArrangementEditor } from '../preview/EditToolbar';

export default function PlacementFields() {
  const { store } = useShell();
  const { gesture, enabled, step, setStep, commit } = useArrangementEditor();
  const [activeField, setActiveField] = useState('');
  const layout = useWallStore(store, state => state.arrangement?.draft);
  const selected = useWallStore(store, state => state.ui.selected);
  if (!layout || !selected) return null;
  const placement = layout.kind === 'logical' ? layout.placements[selected] : null;
  const slot = layout.kind === 'physical' ? layout.slots[selected] : null;
  if (!placement && !slot) return <p className="t-caption">Select a tablet placed on the preview to edit it.</p>;
  const fields = placement ? [['X', 'x', placement.x], ['Y', 'y', placement.y], ['Width', 'w', placement.w], ['Height', 'h', placement.h],
    ['Top bezel', 'bezel-top', placement.bezel.top], ['Right bezel', 'bezel-right', placement.bezel.right],
    ['Bottom bezel', 'bezel-bottom', placement.bezel.bottom], ['Left bezel', 'bezel-left', placement.bezel.left]] as const
    : slot ? [['Centre X (mm)', 'center_x_mm', slot.center_x_mm], ['Centre Y (mm)', 'center_y_mm', slot.center_y_mm],
      ['Turn (degrees)', 'mount_angle', slot.mount_angle], ['Nudge X (mm)', 'nudge_x_mm', slot.nudge_x_mm], ['Nudge Y (mm)', 'nudge_y_mm', slot.nudge_y_mm]] as const : [];
  return <div data-placement-controls="" className="grid gap-4">
    <fieldset className={`grid gap-3 ${slot ? 'grid-cols-3' : 'grid-cols-2'}`}><legend className="sr-only">Tablet placement</legend>
      {fields.map(([label, field, value]) => <LayoutNumber key={`${selected}-${field}`} label={label} value={value} disabled={!enabled}
        error={activeField === field ? gesture.error || undefined : undefined} onCommit={raw => { setActiveField(field); gesture.setField(field, raw); }} />)}
    </fieldset>
    {slot ? <>
      <p className="t-caption">Centre is the base position. The canvas shows centre + nudge. Size and bezels come from the measured profile.</p>
      <Field label="Participating">{props => <Switch {...props} disabled={!enabled} checked={slot.participating !== false} onChange={event => {
        if (layout.kind === 'physical') commit({ ...layout, slots: { ...layout.slots, [selected]: { ...slot, participating: event.target.checked } } });
      }} />}</Field>
    </> : null}
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Nudge selected tablet">
      {([['left', -1, 0, ArrowLeft], ['up', 0, -1, ArrowUp], ['down', 0, 1, ArrowDown], ['right', 1, 0, ArrowRight]] as const).map(([name, dx, dy, Icon]) =>
        <Button key={name} variant="secondary" size="icon" aria-label={`Nudge ${name}`} {...layoutButton(!enabled)} onClick={() => gesture.nudge(dx * step, dy * step)}><Icon aria-hidden="true" /></Button>)}
      <Button variant="ghost" size="icon" aria-label="Turn minus 90 degrees" {...layoutButton(!enabled)} onClick={() => gesture.rotate(-90)}><RotateCcw aria-hidden="true" /></Button>
      <Button variant="ghost" size="icon" aria-label="Turn 90 degrees" {...layoutButton(!enabled)} onClick={() => gesture.rotate(90)}><RotateCw aria-hidden="true" /></Button>
    </div>
    <div className="flex gap-2" role="group" aria-label="Nudge step">{[1, 10].map(value => <Button key={value} variant="ghost" size="sm" aria-pressed={step === value} onClick={() => setStep(value)}>
      {value} {slot ? 'mm' : 'unit'}</Button>)}</div>
    <p className="t-caption">Drag on the preview, or use the arrow keys. Shift moves ten steps. R turns 90°. Escape cancels a drag.</p>
    <Button variant="ghost" className="justify-self-start" {...layoutButton(!enabled)} onClick={gesture.remove}>Remove placement…</Button>
  </div>;
}
