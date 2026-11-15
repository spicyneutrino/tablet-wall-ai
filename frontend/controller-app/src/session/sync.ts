import { ApiError, isRecord } from './outcome';
import type { Device, SessionState } from './session';

export type Timers = Pick<typeof globalThis, 'setTimeout' | 'clearTimeout' | 'setInterval' | 'clearInterval'>;
export type Socket = Pick<WebSocket, 'readyState' | 'onopen' | 'onmessage' | 'onclose' | 'onerror' | 'close'>;
export type SyncDependencies = {
  now: () => number; timers: Timers; WebSocket: new (url: string) => Socket;
  document: Pick<Document, 'visibilityState' | 'addEventListener' | 'removeEventListener'>;
  window: Pick<Window, 'addEventListener' | 'removeEventListener'>; href: string;
};
type Dependencies = SyncDependencies & {
  state: SessionState; api: () => Promise<unknown>; roster: () => Promise<unknown>;
  ingest: (config: unknown, options?: { preserveDraft: boolean; remote: boolean }) => void; publish: () => void;
  onConflict: (message: string) => void; isDirty: () => boolean;
};

export function observeDevice(device: Device, now: number): Device {
  const render = device.render;
  if (!isRecord(render)) return { ...device };
  const elapsed = typeof render.observed_mono === 'number' && Number.isFinite(render.observed_mono)
    ? Math.max(0, now - render.observed_mono) : 0;
  return { ...device, render: { ...render,
    ...(typeof render.age_ms === 'number' ? { age_ms: render.age_ms + elapsed } : {}), observed_mono: now } };
}

export function deviceMap(value: unknown): Record<string, Device> | null {
  if (!isRecord(value) || !Object.values(value).every(isRecord)) return null;
  return value as Record<string, Device>;
}

export function createSync(deps: Dependencies) {
  const { state, timers, document, window } = deps;
  const fence = state.readFence;
  let socket: Socket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  let reconcileTimer: ReturnType<typeof setInterval> | undefined;
  let stopped = false, started = false, fetching = false, queued = false;
  function status(text: string) { state.transportText = text; deps.publish(); }
  async function reconcile(force = false): Promise<void> {
    if (stopped) return;
    if (fetching || state.busy && !force) { queued = true; return; }
    fetching = true; queued = false;
    const ticket = fence.start();
    try {
      const config = await deps.api();
      if (stopped) return;
      if (!fence.accept(ticket)) { queued ||= state.etagState === 'stale'; return; }
      if (!isRecord(config) || !isRecord(config.runtime) || !deviceMap(config.runtime.devices)) {
        const roster = await deps.roster();
        if (stopped) return;
        if (!fence.accept(ticket)) { queued ||= state.etagState === 'stale'; return; }
        const devices = deviceMap(roster);
        if (!devices) throw new Error('Invalid tablet roster. Refresh status to reconcile.');
        state.roster = devices;
      }
      deps.ingest(config, { preserveDraft: true, remote: true });
      state.rosterError = null;
      state.rosterCheckedAt = new Date().toISOString();
      status(socket?.readyState === 1
        ? 'Live operator updates connected. Slow reconciliation is active.'
        : 'Socket unavailable. Showing reconciled status; live updates may be delayed.');
    } catch (error) {
      if (stopped) return;
      state.rosterUnreachable = error instanceof ApiError && error.status === 0;
      state.rosterError = error instanceof Error ? error.message : String(error);
      status(error instanceof ApiError && error.status === 401 ? 'Signed out' : `Status stale. ${state.rosterError} Retry Refresh.`);
      deps.publish();
    } finally {
      fetching = false;
      if (queued && !stopped && !state.busy) { queued = false; void reconcile(); }
    }
  }
  function malformed() {
    status('Invalid operator update. Refresh status to reconcile.');
    void reconcile();
  }
  function connect() {
    if (stopped) return;
    const url = new URL('/ws/controller?protocol=3', deps.href);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    socket = new deps.WebSocket(url.href);
    socket.onopen = () => status('Connected. Waiting for authoritative snapshot…');
    socket.onmessage = (event) => {
      if (stopped) return;
      let frame: unknown;
      try { frame = JSON.parse(String(event.data)); } catch { malformed(); return; }
      if (!isRecord(frame) || typeof frame.type !== 'string') { malformed(); return; }
      fence.event();
      if (frame.type === 'snapshot') {
        if (!isRecord(frame.config)) { malformed(); return; }
        if (!frame.config.runtime && Array.isArray(frame.devices)) {
          const devices: Record<string, Record<string, unknown>> = {};
          for (const device of frame.devices) {
            if (!isRecord(device)) { malformed(); return; }
            const id = device.id || device.device_id;
            if (typeof id !== 'string') { malformed(); return; }
            devices[id] = device;
          }
          state.roster = devices;
        }
        try { deps.ingest(frame.config, { preserveDraft: true, remote: true }); } catch { malformed(); return; }
        state.rosterCheckedAt = new Date().toISOString(); state.rosterError = null;
        status('Live operator updates connected. Last snapshot ' + new Date().toLocaleTimeString() + '.');
      } else if (frame.type === 'config_updated') {
        if (!state.busy && frame.etag !== state.etag) { state.etagState = 'stale'; deps.publish(); }
        if (deps.isDirty() && frame.etag && frame.etag !== state.etag) {
          deps.onConflict('The server changed while this draft was being edited. Keep the draft and reload when ready.');
        }
        void reconcile();
      } else if (['device_online', 'device_offline', 'device_removed', 'device_updated', 'device_status'].includes(frame.type)) {
        if (fetching) queued = true;
        const device = isRecord(frame.device) ? frame.device : null;
        const deviceStatus = isRecord(frame.status) ? frame.status : null;
        const id = frame.device_id || frame.id || device && (device.id || device.device_id);
        if (typeof id !== 'string') { malformed(); return; }
        if (['device_online', 'device_offline', 'device_removed'].includes(frame.type)) {
          state.connectionVersions[id] = (state.connectionVersions[id] || 0) + 1;
        }
        if (frame.type === 'device_removed') delete state.roster[id];
        else if (device || deviceStatus) state.roster[id] = { ...state.roster[id], ...device, ...deviceStatus };
        else if (frame.type === 'device_offline' && state.roster[id]) state.roster[id] = { ...state.roster[id], online: false };
        const current = state.roster[id];
        if ((device?.render || deviceStatus?.render) && current) state.roster[id] = observeDevice(current, deps.now());
        state.rosterCheckedAt = new Date().toISOString(); state.rosterError = null;
        if (state.operatorConfig) {
          state.operatorConfig = { ...state.operatorConfig, runtime: {
            ...(isRecord(state.operatorConfig.runtime) ? state.operatorConfig.runtime : {}), devices: state.roster,
          } };
        }
        deps.publish();
      }
    };
    socket.onclose = () => {
      if (stopped) return;
      state.rosterError = 'Operator socket disconnected';
      status('Live updates disconnected. Reconnecting; status may be stale.');
      deps.publish();
      void reconcile();
      reconnectTimer = timers.setTimeout(connect, 3000);
    };
    socket.onerror = () => status('Operator socket failed. Slow reconciliation remains available.');
  }
  const visible = () => { if (document.visibilityState !== 'hidden') void reconcile(); };
  const online = () => { void reconcile(); };
  return {
    start() {
      if (started || stopped) return;
      started = true;
      connect(); void reconcile();
      reconcileTimer = timers.setInterval(visible, 15000);
      document.addEventListener('visibilitychange', visible);
      window.addEventListener('online', online);
    },
    reconcile,
    destroy() {
      stopped = true;
      timers.clearTimeout(reconnectTimer); timers.clearInterval(reconcileTimer);
      if (started) {
        document.removeEventListener('visibilitychange', visible);
        window.removeEventListener('online', online);
      }
      if (socket) {
        socket.onopen = socket.onmessage = socket.onclose = socket.onerror = null;
        socket.close();
      }
    },
  };
}
