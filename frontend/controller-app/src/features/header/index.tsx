import { Server, SunMoon } from 'lucide-react';
import { useState } from 'react';
import { Button } from '../../ui/Button';
import StatusSummary from './StatusSummary';
import { useShell } from '../preview/ShellContext';
import { useWallStore } from '../../state/hooks';

export default function Header() {
  const { store } = useShell();
  const server = useWallStore(store, state => state.server);
  const serverOpen = useWallStore(store, state => state.ui.serverOpen);
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme ?? 'system');
  function cycleTheme() {
    const next = theme === 'system' ? 'light' : theme === 'light' ? 'dark' : 'system';
    if (next === 'system') delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = next;
    try { localStorage.setItem('tablet-wall-theme', next); } catch { /* Theme still works when storage is unavailable. */ }
    setTheme(next);
  }
  return <header className="appbar">
    <span className="wall-mark" aria-hidden="true"><i /><i /><i /><i /></span>
    <h1 className="t-heading app-name">Tablet wall</h1>
    <StatusSummary />
    {server.transportText === 'Signed out' ? <a className="link" href="/auth/login?next=/controller/app/">Sign in</a> : null}
    <div className="header-actions">
      <Button variant="ghost" className="server-button" aria-label="Server" aria-pressed={serverOpen}
        onClick={() => store.setState(state => ({ ui: { ...state.ui, serverOpen: true } }))}>
        <Server aria-hidden="true" /><span>Server</span>
      </Button>
      <Button variant="ghost" size="icon" aria-label={`Theme: ${theme === 'system' ? 'follows the system' : theme}`}
        onClick={cycleTheme}><SunMoon aria-hidden="true" /></Button>
    </div>
    <p role="status" className="sr-only">{server.transportText.startsWith('Live operator updates connected.')
      ? 'Live operator updates connected.' : server.transportText}</p>
  </header>;
}
