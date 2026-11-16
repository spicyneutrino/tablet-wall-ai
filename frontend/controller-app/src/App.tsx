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
import NextStep from './features/nextstep';
import Server from './features/server';
import Conflict from './features/conflict';
import { ImagesProvider } from './features/sources/images/ImagesContext';
import './features/preview/shell.css';

export default function App({ session, store }: { session: Session; store: WallStoreApi }) {
  const value = useMemo(() => ({ session, store }), [session, store]);
  return <ShellContext value={value}><ImagesProvider>
    <div className="controller-shell">
      <a className="skip" href="#preview">Skip to preview</a>
      <Header />
      <main className="controller-workspace" id="preview" tabIndex={-1} aria-label="Wall controller">
        <div className="preview-column"><Preview /><Sources /></div>
        <aside className="side wall-sidebar" aria-label="Wall status">
          <div className="sidebar-scroll"><OnWall /><NextStep /><Conflict /><Tablet /><Measure /><Board /></div>
        </aside>
      </main>
      <Server />
    </div>
  </ImagesProvider></ShellContext>;
}
