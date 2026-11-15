import { readFence } from './readFence';
import { ApiError, errorMessage, isRecord } from './outcome';
import type { CommandOutcome } from './outcome';
import { createSync, deviceMap, observeDevice } from './sync';
import type { SyncDependencies, Timers } from './sync';

export type Device = Record<string, unknown>;
export type Config = Record<string, unknown> & { layout: Record<string, unknown> };
export type ServerState = {
  config: Config | null; etag: string | null; etagState: 'current' | 'stale' | 'missing';
  roster: Record<string, Device>; connectionVersions: Record<string, number>;
  rosterError: string | null; rosterUnreachable: boolean; rosterCheckedAt: string | null;
  transportText: string; uncertain: boolean; supported: boolean; busy: boolean; adoption: number;
};
export type SessionState = Omit<ServerState, 'config' | 'uncertain' | 'supported' | 'adoption'> & {
  operatorConfig: Config | null; readFence: ReturnType<typeof readFence>;
};
export type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
export type RequestOptions<T> = {
  ifMatch?: string; useCurrentEtag?: boolean; fenced?: boolean | 'durable';
  parse?: { parse: (value: unknown) => T };
};
export type Session = ReturnType<typeof createSession>;
type Dependencies = Partial<SyncDependencies> & {
  store?: { setState: (partial: { server: ServerState }) => void };
  fetch?: typeof fetch; isDirty: () => boolean; onConflict?: (message: string) => void;
};

function freeze<T>(value: T): T {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value);
    Object.values(value).forEach(freeze);
  }
  return value;
}

export function parseConfig(value: unknown): Config {
  if (!isRecord(value) || !isRecord(value.layout)
    || value.layout.kind !== undefined && value.layout.kind !== 'logical' && value.layout.kind !== 'physical'
    || value.operator_state_version !== undefined && value.operator_state_version !== 1) {
    throw new Error('Unsupported wall configuration. Update the console before editing.');
  }
  return { ...value, layout: value.layout };
}

export function createSession(deps: Dependencies) {
  const transport = deps.fetch ?? globalThis.fetch.bind(globalThis);
  const now = deps.now ?? (() => performance.now());
  const timers: Timers = deps.timers ?? {
    setTimeout: globalThis.setTimeout.bind(globalThis), clearTimeout: globalThis.clearTimeout.bind(globalThis),
    setInterval: globalThis.setInterval.bind(globalThis), clearInterval: globalThis.clearInterval.bind(globalThis),
  };
  const listeners = new Set<() => void>();
  const state: SessionState = {
    operatorConfig: null, roster: {}, etag: null, etagState: 'missing', busy: false,
    rosterError: null, rosterUnreachable: false, rosterCheckedAt: null,
    transportText: 'Connecting to the wall…', connectionVersions: {}, readFence: readFence(),
  };
  let snapshot: ServerState, uncertain = false, adoption = 0, supported = false, destroyed = false;
  function publish() {
    if (destroyed) return;
    snapshot = freeze({ config: state.operatorConfig ? structuredClone(state.operatorConfig) : null,
      etag: state.etag, etagState: state.etagState, connectionVersions: { ...state.connectionVersions },
      roster: structuredClone(state.roster), rosterError: state.rosterError,
      rosterUnreachable: !!state.rosterError && state.rosterUnreachable,
      rosterCheckedAt: state.rosterCheckedAt, transportText: state.transportText,
      uncertain, supported, busy: state.busy, adoption });
    deps.store?.setState({ server: snapshot });
    listeners.forEach((listener) => listener());
  }
  function ingest(value: unknown) {
    if (destroyed) return;
    let config: Config;
    try { config = parseConfig(value); } catch (error) {
      supported = false;
      state.etagState = 'stale';
      publish();
      throw error;
    }
    supported = true;
    state.readFence.event();
    adoption += 1;
    const runtime = isRecord(config.runtime) ? config.runtime : {};
    const devices = deviceMap(runtime.devices);
    if (devices) state.roster = Object.fromEntries(Object.entries(devices).map(([id, device]) => [id, observeDevice(device, now())]));
    state.operatorConfig = { ...structuredClone(config), runtime: { ...runtime, devices: state.roster } };
    state.etag = typeof config.etag === 'string' && config.etag ? config.etag : null;
    state.etagState = state.etag ? 'current' : 'missing';
    state.rosterCheckedAt = new Date().toISOString();
    state.rosterError = null;
    publish();
  }
  async function send(method: Method, path: string, body?: unknown, expected?: string | null, durable = false) {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (expected) headers['If-Match'] = expected;
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const controller = new AbortController();
    const timer = timers.setTimeout(() => controller.abort(), 10000);
    try {
      let response: Response;
      try {
        response = await transport(path, { method, headers, signal: controller.signal,
          ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
      } catch (error) {
        throw new ApiError(0, (error instanceof Error && error.name === 'AbortError' ? 'Request timed out.' : 'Connection lost.')
          + (durable ? ' Completion is uncertain. Refresh status and inspect the result before retrying.' : ' Refresh status to reconnect.'));
      }
      let payload: unknown;
      try { payload = await response.json(); } catch { payload = null; }
      if (!response.ok) {
        const message = errorMessage(isRecord(payload) ? payload.detail : null, response.status)
          .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, (id) => {
            const labels = state.operatorConfig?.device_labels;
            const label = isRecord(labels) ? labels[id] : null;
            const device = state.roster[id];
            return typeof label === 'string' ? label : typeof device?.label === 'string' ? device.label
              : device?.number ? `Tablet ${String(device.number)}` : 'Unregistered tablet';
          });
        if (response.status === 401) {
          state.transportText = 'Signed out';
          publish();
        }
        throw new ApiError(response.status, message + (durable && response.status >= 500
          ? '. Completion is uncertain. Refresh status and inspect the result before retrying.' : ''), response.status >= 500);
      }
      return payload;
    } finally { timers.clearTimeout(timer); }
  }
  const sync = createSync({ state, api: () => send('GET', '/api/v3/config'),
    roster: () => send('GET', '/devices'), ingest, publish,
    onConflict: deps.onConflict ?? (() => {}), isDirty: deps.isDirty,
    now, timers, WebSocket: deps.WebSocket ?? globalThis.WebSocket,
    document: deps.document ?? globalThis.document, window: deps.window ?? globalThis.window,
    href: deps.href ?? globalThis.location?.href ?? 'http://localhost/controller/app/',
  });
  function request<T>(method: Method, path: string, body: unknown,
    options: RequestOptions<T> & { parse: { parse: (value: unknown) => T } }): Promise<CommandOutcome<T>>;
  function request(method: Method, path: string, body?: unknown,
    options?: RequestOptions<unknown>): Promise<CommandOutcome<unknown>>;
  async function request(method: Method, path: string, body?: unknown,
    options: RequestOptions<unknown> = {}): Promise<CommandOutcome<unknown>> {
    const durable = method !== 'GET' && !path.endsWith('/preview') && path !== '/api/v3/calibration-check';
    if (durable && !supported) return { kind: 'refused-locally', reason: 'unsupported' };
    if (durable && state.busy) return { kind: 'refused-locally', reason: 'busy' };
    if (durable && uncertain) return { kind: 'refused-locally', reason: 'uncertain' };
    const expected = options.ifMatch || (options.useCurrentEtag ? state.etag : null);
    if ((options.useCurrentEtag || options.ifMatch !== undefined) && (!expected || state.etagState !== 'current')) return { kind: 'refused-locally', reason: 'stale-etag' };
    const atSend = state.operatorConfig, ticket = state.readFence.start();
    if (durable) { state.busy = true; publish(); }
    try {
      let payload = await send(method, path, body, expected, durable);
      if (durable) {
        if (!payload) throw new ApiError(0, 'The command may have completed, but its response was unreadable. Refresh status and review before retrying.');
        state.readFence.event();
        const current = state.operatorConfig;
        if (isRecord(payload) && payload.layout && current && current !== atSend
          && (current.etag === payload.etag || current.etag !== expected)) {
          void sync.reconcile(true);
          const commandEtag = typeof payload.etag === 'string' ? payload.etag : undefined;
          payload = { ...payload, ...current };
          let value: unknown;
          try { value = options.parse ? options.parse.parse(payload) : payload; } catch {
            throw new ApiError(0, 'The response was unreadable. Refresh status and review before retrying.');
          }
          return { kind: 'ok', value, commandEtag };
        }
      } else if (options.fenced === 'durable') {
        if (atSend?.etag !== state.operatorConfig?.etag || state.etagState === 'stale') {
          return { kind: 'rejected', status: 409, message: 'Saved wall data changed during this read. Refresh this task.' };
        }
      } else if (options.fenced && !state.readFence.current(ticket)) {
        return { kind: 'rejected', status: 409, message: 'A newer update arrived. Refresh this task.' };
      }
      let value: unknown;
      try { value = options.parse ? options.parse.parse(payload) : payload; } catch {
        throw new ApiError(0, 'The response was unreadable. Refresh status and review before retrying.');
      }
      if (durable && isRecord(payload) && payload.layout) {
        try { ingest(payload); } catch {
          throw new ApiError(0, 'The response was unsupported. Update the console and refresh status before retrying.');
        }
      }
      return { kind: 'ok', value };
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      if (durable && error.uncertain) { uncertain = true; return { kind: 'uncertain', message: error.message }; }
      if (error.status === 412) return { kind: 'conflict' };
      if (error.status === 428) return { kind: 'precondition-missing' };
      return { kind: 'rejected', status: error.status, message: error.message };
    } finally { if (durable) { state.busy = false; publish(); } }
  }
  publish();
  return {
    view: () => snapshot,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    ingest, request,
    async refresh() {
      const version = adoption;
      let listener = () => {};
      let timer: ReturnType<typeof setTimeout> | undefined;
      const received = new Promise<void>((resolve, reject) => {
        listener = () => {
          if (snapshot.rosterError) reject(new ApiError(0, 'Status could not be reconciled. ' + snapshot.rosterError));
          else if (adoption > version) resolve();
        };
        listeners.add(listener);
        timer = timers.setTimeout(() => reject(new ApiError(0, 'Waiting for a current wall snapshot timed out. Retry Refresh status.')), 10000);
      });
      try {
        await Promise.all([sync.reconcile(true), received]);
        uncertain = false;
        publish();
      } finally { timers.clearTimeout(timer); listeners.delete(listener); }
    },
    start: sync.start,
    destroy() { destroyed = true; sync.destroy(); listeners.clear(); },
  };
}
