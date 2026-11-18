import type { ReactNode } from 'react';
import { MeasurementContext } from '../../stage/MeasureOverlay';
import { useWallStore } from '../../state/hooks';
import { useShell } from '../preview/ShellContext';
import { measurementValues } from './model';

export default function MeasurementProvider({ children }: { children: ReactNode }) {
  const { store } = useShell();
  const state = useWallStore(store, state => state);
  const id = state.ui.drill ?? state.ui.selected;
  const values = id && state.ui.measureStep && state.server.config ? measurementValues(state, id) : null;
  return <MeasurementContext value={id && values ? { id, width: values.profileActiveWidth ?? '', height: values.profileActiveHeight ?? '',
    ruler: state.ui.measureStep === 'ruler', spanX: values.rulerSpanX ?? '200', spanY: values.rulerSpanY ?? '200' } : null}>{children}</MeasurementContext>;
}
