import './styles/app.css';
import './features/preview/configureValidation';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import StageFixture from './dev/StageFixture';
import PrimitivesGallery from './dev/PrimitivesGallery';
import { createSession } from './session/session';
import { createWallStore, startClock } from './state/store';
import { hasUnsavedEdits } from './state/unsaved';

const root = document.getElementById('root');
if (!root) throw new Error('Controller root is missing');

const store = createWallStore();
const session = createSession({ store, isDirty: () => hasUnsavedEdits(store) });
const stopClock = startClock(store);
session.start();
const beforeUnload = (event: BeforeUnloadEvent) => {
  if (!hasUnsavedEdits(store)) return;
  event.preventDefault();
  event.returnValue = '';
};
window.addEventListener('beforeunload', beforeUnload);
const destroy = () => {
  session.destroy();
  stopClock();
  window.removeEventListener('beforeunload', beforeUnload);
};
window.addEventListener('pagehide', destroy, { once: true });
if (import.meta.hot) import.meta.hot.dispose(destroy);

createRoot(root).render(
  <StrictMode>
    {import.meta.env.MODE === 'e2e' && location.hash === '#stage-fixture'
      ? <StageFixture /> : import.meta.env.MODE === 'e2e' && location.hash === '#primitives-gallery'
        ? <PrimitivesGallery /> : <App store={store} session={session} />}
  </StrictMode>,
);
