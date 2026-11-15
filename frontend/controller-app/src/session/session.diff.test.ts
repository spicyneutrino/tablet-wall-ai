import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { afterEach, expect, it, vi } from 'vitest';
import { createSession } from './session';
import { isRecord } from './outcome';
import type { CommandOutcome } from './outcome';

const require = createRequire(import.meta.url);
type LegacySession = {
  view(): Record<string, unknown>; subscribe(listener: () => void): () => void;
  ingest(value: unknown): void; start(): void; destroy(): void; refresh(): Promise<void>;
  request(method: string, path: string, body?: unknown, options?: Record<string, unknown>): Promise<unknown>;
};
const legacy = require('../../../controller/operator-session.js') as {
  create(deps: { transport: typeof fetch; clock: () => number; syncFactory: unknown; isDirty: () => boolean }): LegacySession;
};
const model: unknown = require('../../../controller/operator-state.js');
const syncSource = readFileSync(require.resolve('../../../controller/operator-sync.js'), 'utf8');
const config = (etag: string, paint = 'loading') => ({ etag, revision: 1, generation: 'session',
  layout: { kind: 'logical', placements: {} }, runtime: { devices: { a: { online: true, render: { state: paint } } } } });

async function runScript(version: 'old' | 'new') {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2026-11-15T12:00:00Z'));
  const sockets: FakeSocket[] = [], pending: { resolve: (value: Response) => void; path: string }[] = [];
  const calls: unknown[] = [], published: unknown[] = [], outcomes: unknown[] = [];
  class FakeSocket {
    static OPEN = 1;
    readyState: WebSocket['readyState'] = 1;
    onopen: (() => void) | null = null;
    onmessage: ((event: MessageEvent) => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    constructor(readonly url: string) { sockets.push(this); }
    close() { this.readyState = 3; }
    frame(frame: unknown) { this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(frame) })); }
  }
  const transport: typeof fetch = (path, options) => {
    calls.push({ path, method: options?.method, headers: options?.headers, body: options?.body });
    return new Promise((resolve, reject) => {
      pending.push({ resolve, path: String(path) });
      options?.signal?.addEventListener('abort', () => reject(new DOMException('timeout', 'AbortError')));
    });
  };
  const document = Object.assign(new EventTarget(), { visibilityState: 'visible' as DocumentVisibilityState });
  const window = Object.assign(new EventTarget(), { OperatorState: model, location: { href: 'http://localhost/controller/app/' } });
  runInNewContext(syncSource, { window, document, WebSocket: FakeSocket, URL, Date,
    performance: { now: () => 100 }, setTimeout, clearTimeout, setInterval, clearInterval });
  const session = version === 'old'
    ? legacy.create({ transport, clock: () => 100, syncFactory: Reflect.get(window, 'OperatorSync'), isDirty: () => true })
    : createSession({ fetch: transport, now: () => 100, WebSocket: FakeSocket, document, window, isDirty: () => true });
  const normalize = () => {
    const value = session.view();
    return Object.fromEntries(Object.entries(value).filter(([key]) => key !== 'adoption'));
  };
  session.subscribe(() => published.push(normalize()));
  const flush = () => vi.advanceTimersByTimeAsync(0);
  const reply = (value: unknown, status = 200, raw = false) => {
    const item = pending.shift();
    if (!item) throw new Error('Script replied without a request');
    item.resolve(new Response(raw ? String(value) : JSON.stringify(value), { status }));
  };
  async function request(method: 'GET' | 'PUT' | 'PATCH' | 'POST', path: string, fenced?: boolean | 'durable'): Promise<unknown> {
    try {
      let result: CommandOutcome<unknown>;
      if (version === 'old') {
        const value = await (session as LegacySession).request(method, path, method === 'GET' ? undefined : {}, { etag: method !== 'GET', fenced });
        if (isRecord(value) && typeof value.commandEtag === 'string') {
          const { commandEtag, ...receipt } = value;
          result = { kind: 'ok', value: receipt, commandEtag };
        } else result = { kind: 'ok', value };
      } else {
        result = await (session as ReturnType<typeof createSession>).request(method, path, method === 'GET' ? undefined : {}, { useCurrentEtag: method !== 'GET', fenced });
      }
      const outcome = result.kind === 'uncertain' ? { kind: result.kind }
        : result.kind === 'rejected' ? { kind: result.kind, status: result.status } : result;
      outcomes.push(outcome);
      return outcome;
    } catch (error) {
      if (!isRecord(error)) throw error;
      const message = String(error.message);
      const outcome = error.uncertain ? { kind: 'uncertain' }
        : /in progress/.test(message) ? { kind: 'refused-locally', reason: 'busy' }
        : /may have completed/.test(message) ? { kind: 'refused-locally', reason: 'uncertain' }
        : /Refresh the wall before saving/.test(message) ? { kind: 'refused-locally', reason: 'stale-etag' }
        : error.status === 412 ? { kind: 'conflict' }
        : error.status === 428 ? { kind: 'precondition-missing' }
        : { kind: 'rejected', status: error.status };
      outcomes.push(outcome);
      return outcome;
    }
  }
  try {
    session.start();
    sockets[0]!.frame({ type: 'snapshot', config: config('first') });
    reply(config('obsolete')); await flush();
    const write = request('PUT', '/api/v3/scene');
    await request('POST', '/api/v3/layout/clear');
    sockets[0]!.frame({ type: 'snapshot', config: config('returned', 'displayed') });
    reply(config('returned')); await write;
    reply(config('returned', 'displayed')); await flush();
    const another = request('PUT', '/api/v3/scene');
    sockets[0]!.frame({ type: 'snapshot', config: config('another-operator', 'displayed') });
    reply(config('own-command')); await another;
    reply(config('another-operator', 'displayed')); await flush();
    for (const status of [500, 502, 503]) {
      const failing = request('PATCH', '/api/v3/devices/a');
      reply({ detail: 'server error' }, status); await failing;
      sockets[0]!.frame({ type: 'snapshot', config: config('incidental') });
      await request('PUT', '/api/v3/scene');
      const refresh = session.refresh(); reply(config('refreshed')); await refresh;
    }
    for (const status of [412, 428]) {
      const failing = request('PUT', '/api/v3/scene'); reply({ detail: 'precondition' }, status); await failing;
    }
    const unreadable = request('PUT', '/api/v3/scene'); reply('not-json', 200, true); await unreadable;
    const refresh = session.refresh(); reply(config('readable')); await refresh;
    const timed = request('PUT', '/api/v3/scene'); await vi.advanceTimersByTimeAsync(10000); await timed;
    pending.shift();
    await request('PUT', '/api/v3/scene');
    const afterTimeout = session.refresh(); reply(config('after-timeout')); await afterTimeout;
    const read = request('GET', '/api/v3/layouts', true);
    sockets[0]!.frame({ type: 'snapshot', config: config('newer') });
    reply({ layouts: [] }); await read;
    sockets[0]!.frame({ type: 'config_updated', etag: 'next' });
    await request('PUT', '/api/v3/scene');
    reply(config('next')); await flush();
    sockets[0]!.frame({ type: 'device_online', device: { device_id: 'b', online: true } });
    sockets[0]!.frame({ type: 'device_updated', device: { device_id: 'b', render: { state: 'displayed', age_ms: 20 } } });
    sockets[0]!.frame({ type: 'device_offline', device_id: 'b' });
    sockets[0]!.frame({ type: 'device_removed', device_id: 'b' });
    sockets[0]!.close(); sockets[0]!.onclose?.(); reply(config('reconnected')); await flush();
    await vi.advanceTimersByTimeAsync(3000);
    const urls = sockets.map((socket) => socket.url);
    return { outcomes, published, calls, urls, final: normalize() };
  } finally { session.destroy(); vi.useRealTimers(); }
}

afterEach(() => vi.useRealTimers());

it('drives legacy and new sessions through the same fake HTTP/socket/timer transport script', async () => {
  const old = await runScript('old'), current = await runScript('new');
  expect(current.outcomes).toEqual(old.outcomes);
  expect(current.published).toEqual(old.published);
  expect(current.calls).toEqual(old.calls);
  expect(current.urls).toEqual(old.urls);
  expect(current.final).toEqual(old.final);
});
