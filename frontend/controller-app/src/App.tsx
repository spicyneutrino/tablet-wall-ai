import { useMemo } from 'react';
import type { Session } from './session/session';
import type { WallStoreApi } from './state/store';
import { ShellContext } from './features/preview/ShellContext';
import Header from './features/header';
import Preview from './features/preview';
import Sources from './features/sources';
import OnWall from './features/onwall';
import Board from './features/board';
import Tablet from './features/tablet';
import Measure from './features/measure';
import MeasurementProvider from './features/measure/MeasurementProvider';
import { useWallStore } from './state/hooks';
import NextStep from './features/nextstep';
import Server from './features/server';
import Conflict from './features/conflict';
import { ImagesProvider } from './features/sources/images/ImagesContext';
import './features/preview/shell.css';

export default function App({ session, store }: { session: Session; store: WallStoreApi }) {
  const measuring = useWallStore(store, state => !!state.ui.measureStep);
  const value = useMemo(() => ({ session, store }), [session, store]);
  return <ShellContext value={value}><ImagesProvider>
    <MeasurementProvider><div className={`controller-shell${measuring ? ' is-measuring' : ''}`}>
      <a className="skip" href="#preview">Skip to preview</a>
      <Header />
      <main className="controller-workspace" id="preview" tabIndex={-1} aria-label="Wall controller">
        <div className="preview-column"><Preview /><fieldset className="measure-source-controls" disabled={measuring}><Sources /></fieldset></div>
        <aside className="side wall-sidebar" aria-label="Wall status">
          <div className="sidebar-scroll">{measuring ? <><Conflict /><Measure /></> : <><OnWall /><NextStep /><Conflict /><Tablet /><Board /></>}</div>
        </aside>
      </main>
      <Server />
    </div></MeasurementProvider>
  </ImagesProvider></ShellContext>;
}
