import { Ruler } from 'lucide-react';
import { useShell } from '../preview/ShellContext';
import { useWallStore } from '../../state/hooks';
import { observeForm } from '../../state/store';
import { Button } from '../../ui/Button';

export default function MeasureEntry() {
  const { store } = useShell();
  const id = useWallStore(store, state => state.ui.drill ?? state.ui.selected);
  if (!id) return null;
  return <Button onClick={() => {
    for (const group of ['model', 'profile', 'calibration'] as const) observeForm(store, id, group);
    store.setState(state => ({ ui: { ...state.ui, selected: id, measureStep: 'model', editLayout: false } }));
  }}><Ruler aria-hidden="true" />Measure…</Button>;
}
