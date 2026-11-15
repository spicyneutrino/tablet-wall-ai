import { useSyncExternalStore } from 'react';
import { PanelsTopLeft } from 'lucide-react';
import { z } from 'zod';
import type { Session } from './session/session';

z.config({ jitless: true });

export default function App({ session }: { session: Session }) {
  const server = useSyncExternalStore(session.subscribe, session.view);
  const transportText = server.transportText.startsWith('Live operator updates connected.')
    ? 'Live operator updates connected.' : server.transportText;
  return (
    <main className="mx-auto max-w-5xl p-6 sm:p-10">
      <header className="flex items-center gap-3">
        <PanelsTopLeft aria-hidden="true" className="size-6 text-primary" />
        <h1 className="t-title">Tablet wall</h1>
      </header>
      <p role="status" className="mt-6 text-muted">{transportText}</p>
      {server.transportText === 'Signed out'
        ? <a href="/auth/login?next=/controller/app/">Sign in</a> : null}
      {!server.supported && server.config
        ? <p role="alert">Update the console before editing.</p> : null}
      <ul aria-label="Tablets">
        {Object.entries(server.roster).map(([id, device]) => (
          <li key={id}>{typeof device.label === 'string' && device.label
            ? device.label : `Tablet ${String(device.number ?? id)}`}</li>
        ))}
      </ul>
    </main>
  );
}
