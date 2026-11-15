import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import StageFixture from './dev/StageFixture';
import { createSession } from './session/session';
import type { ServerState } from './session/session';
import { createStore } from 'zustand/vanilla';
import './styles/app.css';

const root = document.getElementById('root');
if (!root) throw new Error('Controller root is missing');

const store = createStore<{ server: ServerState | null }>(() => ({ server: null }));
const session = createSession({ store, isDirty: () => false });
session.start();
window.addEventListener('pagehide', () => session.destroy(), { once: true });
if (import.meta.hot) import.meta.hot.dispose(() => session.destroy());

createRoot(root).render(
  <StrictMode>
    {import.meta.env.MODE === 'e2e' && location.hash === '#stage-fixture'
      ? <StageFixture /> : <App session={session} />}
  </StrictMode>,
);
