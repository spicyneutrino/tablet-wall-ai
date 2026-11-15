import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import StageFixture from './dev/StageFixture';
import './styles/app.css';

const root = document.getElementById('root');
if (!root) throw new Error('Controller root is missing');

createRoot(root).render(
  <StrictMode>
    {import.meta.env.MODE === 'e2e' && location.hash === '#stage-fixture'
      ? <StageFixture /> : <App />}
  </StrictMode>,
);
