import { useEffect, useState } from 'react';
import { PanelsTopLeft } from 'lucide-react';
import { z } from 'zod';

z.config({ jitless: true });

const frameSchema = z.object({ type: z.string() });

function useTransportText() {
  const [transportText, setTransportText] = useState('Connecting to the wall…');
  useEffect(() => {
    const url = new URL('/ws/controller?protocol=3', location.href);
    url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(url);
    socket.onmessage = (event: MessageEvent<string>) => {
      try {
        const frame = frameSchema.safeParse(JSON.parse(event.data));
        if (frame.success && frame.data.type === 'snapshot') {
          setTransportText('Live operator updates connected.');
        }
      } catch { /* Ignore malformed frames in this temporary serving spike. */ }
    };
    socket.onclose = () => setTransportText('Connection closed. Reload to reconnect.');
    socket.onerror = () => setTransportText('Cannot connect to the wall. Reload to retry.');
    return () => { socket.onclose = null; socket.onmessage = null; socket.onerror = null; socket.close(); };
  }, []);
  return transportText;
}

export default function App() {
  const transportText = useTransportText();
  return (
    <main className="mx-auto max-w-5xl p-6 sm:p-10">
      <header className="flex items-center gap-3">
        <PanelsTopLeft aria-hidden="true" className="size-6 text-primary" />
        <h1 className="t-title">Tablet wall</h1>
      </header>
      <p role="status" className="mt-6 text-muted">{transportText}</p>
    </main>
  );
}
