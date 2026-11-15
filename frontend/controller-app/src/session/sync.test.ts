import { A, B, C, configFixture, deviceFixture, renderFixture } from './testFixtures';
import { ConfigSchema } from '../api/config';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createSync } from './sync';
import { createSession } from './session';
import type { SessionState } from './session';
import { ApiError, isRecord } from './outcome';
import { readFence } from './readFence';

class FakeSocket {
  static sockets: FakeSocket[] = [];
  readyState: WebSocket['readyState'] = 1;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(readonly url: string) { FakeSocket.sockets.push(this); }
  close() { this.readyState = 3; }
  message(frame: unknown) { this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(frame) })); }
  disconnect() { this.close(); this.onclose?.(); }
}
class Visibility extends EventTarget { visibilityState: DocumentVisibilityState = 'visible'; }
const config = (revision: number) => ConfigSchema.parse({ ...configFixture(String(revision)), revision, runtime: { ...configFixture(String(revision)).runtime, devices: {} } });
const cleanups: (() => void)[] = [];
const flush = async () => { await vi.advanceTimersByTimeAsync(0); };
function harness(failure?: ApiError) {
  const state: SessionState = { readFence: readFence(), roster: {}, busy: false, operatorConfig: null,
    etag: null, etagState: 'missing', connectionVersions: {}, rosterUnreachable: false,
    rosterError: null, rosterCheckedAt: null, transportText: '' };
  const document = new Visibility(), window = new EventTarget();
  const pending: ((value: unknown) => void)[] = [];
  const received: unknown[] = [];
  const adoptions: unknown[] = [];
  const onConflict = vi.fn(), publish = vi.fn();
  const api = vi.fn<() => Promise<unknown>>(() => failure ? Promise.reject(failure) : new Promise((resolve) => pending.push(resolve)));
  const sync = createSync({ state, api, roster: api, ingest(value, options) {
    adoptions.push(options);
    if (!isRecord(value) || !isRecord(value.layout)) throw new Error('bad config');
    received.push(value.revision);
    state.operatorConfig = ConfigSchema.parse(value);
    state.etag = state.operatorConfig.etag; state.etagState = 'current';
  }, publish, onConflict, isDirty: () => true, now: () => 1000,
  timers: { setTimeout, clearTimeout, setInterval, clearInterval },
  WebSocket: FakeSocket, document, window, href: 'https://example.test/controller/app/' });
  cleanups.push(sync.destroy);
  return { state, pending, received, adoptions, sync, document, window, onConflict, publish, api };
}

beforeEach(() => { vi.useFakeTimers(); FakeSocket.sockets = []; });
afterEach(() => { cleanups.splice(0).forEach((cleanup) => cleanup()); vi.useRealTimers(); });

it('ports operator_sync: late reads, stale ETags, queued reconciliation, runtime evidence and connection versions', async () => {
  const { state, pending, received, adoptions, sync } = harness();
  sync.start();
  expect(pending.length).toBe(1);
  const socket = FakeSocket.sockets[0]!;
  socket.message({ type: 'snapshot', config: config(8) });
  pending.shift()!(config(1)); await flush();
  expect(received).toEqual([8]);
  expect(adoptions[0]).toEqual({ preserveDraft: true, remote: true });
  const first = sync.reconcile();
  socket.message({ type: 'config_updated', etag: '9', revision: 9, generation: 'session' });
  expect(state.etagState).toBe('stale');
  pending.shift()!(config(7)); await first; await flush();
  expect(pending.length).toBe(1);
  pending.shift()!(config(9)); await flush();
  expect(state.etagState).toBe('current');
  expect(received).toEqual([8, 9]);
  const interrupted = sync.reconcile();
  socket.message({ type: 'device_online', device: deviceFixture(B) });
  pending.shift()!(config(10)); await interrupted; await flush();
  expect(pending.length).toBe(1);
  pending.shift()!(config(11)); await flush();
  expect(received).toEqual([8, 9, 11]);
  socket.message({ type: 'config_updated', etag: '12', revision: 12, generation: 'session' });
  expect(state.etagState).toBe('stale');
  state.readFence.event();
  pending.shift()!(config(12)); await flush();
  expect(pending.length).toBe(1);
  expect(received).toEqual([8, 9, 11]);
  pending.shift()!(config(12)); await flush();
  expect(state.etagState).toBe('current');
  expect(received).toEqual([8, 9, 11, 12]);
  state.roster[C] = deviceFixture(C, { render: renderFixture('displayed', { age_ms: 100, observed_mono: 10 }) });
  socket.message({ type: 'device_updated', device: deviceFixture(A, { render: renderFixture('loading') }) });
  expect(state.roster[A]?.render).toMatchObject({ state: 'loading' });
  expect(state.operatorConfig?.runtime).toMatchObject({ devices: { [A]: { render: { state: 'loading' } } } });
  expect(state.roster[A]?.render).toMatchObject({ observed_mono: 1000 });
  expect(state.roster[C]!.render).toMatchObject({ observed_mono: 10 });
  socket.message({ type: 'device_offline', device_id: A, last_seen: 'now' });
  expect(state.roster[A]?.online).toBe(false);
  const version = state.connectionVersions[A]!;
  socket.message({ type: 'device_removed', device_id: A });
  expect(state.roster[A]).toBeUndefined();
  expect(state.connectionVersions[A]).toBe(version + 1);
  sync.destroy();
  expect(socket.readyState).toBe(3);
});

it('ports operator_unreachable: network failure is unreachable, HTTP failure is stale, independent of wording', async () => {
  const network = harness(new ApiError(0, 'Connection lost.'));
  await network.sync.reconcile();
  expect(network.state.rosterUnreachable).toBe(true);
  const server = harness(new ApiError(503, '503 unavailable', false));
  await server.sync.reconcile();
  expect(server.state.rosterUnreachable).toBe(false);
  expect(server.state.rosterError).toBe('503 unavailable');
  const reworded = harness(new ApiError(0, 'Le serveur ne répond pas'));
  await reworded.sync.reconcile();
  expect(reworded.state.rosterUnreachable).toBe(true);
});

it('schedules a fixed reconnect at 3000ms, immediately reconciles on close, and starts once', async () => {
  const { sync, pending, api } = harness();
  sync.start(); sync.start();
  expect(FakeSocket.sockets).toHaveLength(1);
  expect(FakeSocket.sockets[0]?.url).toBe('wss://example.test/ws/controller?protocol=3');
  pending.shift()!(config(1)); await flush();
  FakeSocket.sockets[0]!.disconnect();
  expect(api).toHaveBeenCalledTimes(2);
  await vi.advanceTimersByTimeAsync(2999);
  expect(FakeSocket.sockets).toHaveLength(1);
  await vi.advanceTimersByTimeAsync(1);
  expect(FakeSocket.sockets).toHaveLength(2);
  sync.destroy();
  expect(vi.getTimerCount()).toBe(0);
});

it('reconciles every 15000ms only when visible, and also on visible and online events', async () => {
  const { sync, api, pending, document, window } = harness();
  sync.start(); pending.shift()!(config(1)); await flush();
  await vi.advanceTimersByTimeAsync(14999);
  expect(api).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(1);
  expect(api).toHaveBeenCalledTimes(2);
  pending.shift()!(config(2)); await flush();
  document.visibilityState = 'hidden';
  document.dispatchEvent(new Event('visibilitychange'));
  await vi.advanceTimersByTimeAsync(15000);
  expect(api).toHaveBeenCalledTimes(2);
  document.visibilityState = 'visible'; document.dispatchEvent(new Event('visibilitychange'));
  expect(api).toHaveBeenCalledTimes(3);
  pending.shift()!(config(3)); await flush();
  window.dispatchEvent(new Event('online'));
  expect(api).toHaveBeenCalledTimes(4);
  sync.destroy(); pending.shift()!(config(4)); await flush();
  expect(api).toHaveBeenCalledTimes(4);
});

it('config_updated marks the session ETag stale and refuses a guarded command while reconciling', async () => {
  let resolve!: (response: Response) => void;
  const fetch = vi.fn<typeof globalThis.fetch>(() => new Promise((done) => { resolve = done; }));
  const session = createSession({ fetch, WebSocket: FakeSocket, document: new Visibility(), window: new EventTarget(), isDirty: () => true });
  cleanups.push(session.destroy);
  session.ingest(config(1)); session.start();
  FakeSocket.sockets[0]!.message({ type: 'config_updated', etag: '2', revision: 2, generation: 'session' });
  expect(session.view().etagState).toBe('stale');
  expect(await session.request('PUT', '/api/v3/scene', {}, { useCurrentEtag: true }))
    .toEqual({ kind: 'refused-locally', reason: 'stale-etag' });
  resolve(new Response(JSON.stringify(config(2))));
  await flush();
});

it('drops malformed frames and reconciles, ignores unknown frame types and retains placements on offline', async () => {
  const { sync, api, pending, state } = harness();
  sync.start(); pending.shift()!(config(1)); await flush();
  const socket = FakeSocket.sockets[0]!;
  socket.onmessage?.(new MessageEvent('message', { data: '{' }));
  expect(api).toHaveBeenCalledTimes(2);
  pending.shift()!(config(2)); await flush();
  socket.message({ type: 'unknown' });
  expect(api).toHaveBeenCalledTimes(2);
  const placement = { x: 1, y: 0, w: 10, h: 10, bezel: { top: 0, right: 0, bottom: 0, left: 0 } };
  if (state.operatorConfig!.layout.kind === 'logical') state.operatorConfig!.layout.placements = { [A]: placement };
  state.roster[A] = deviceFixture(A);
  socket.message({ type: 'device_offline', device_id: A, last_seen: 'now' });
  expect(state.operatorConfig?.layout.placements).toEqual({ [A]: placement });
  expect(state.roster[A]!.online).toBe(false);
});

it('falls back to /devices only when config has no runtime devices, fencing the fallback read too', async () => {
  const { sync, api, pending, received } = harness();
  const first = sync.reconcile();
  pending.shift()!({ ...config(1), runtime: undefined }); await flush();
  expect(api).toHaveBeenCalledTimes(2);
  pending.shift()!({ [A]: deviceFixture(A) }); await first;
  expect(received).toEqual([1]);
  const read = sync.reconcile();
  pending.shift()!({ ...config(2), runtime: undefined }); await flush();
  sync.start();
  FakeSocket.sockets[0]!.message({ type: 'snapshot', config: config(3) });
  pending.shift()!({ [C]: deviceFixture(C) }); await read;
  expect(received).toEqual([1, 3]);
});

it('a signed-out reconcile remains Signed out and an unsupported config blocks commands', async () => {
  const session = createSession({ fetch: async () => new Response(JSON.stringify({ detail: 'Authentication required' }), { status: 401 }), isDirty: () => false });
  cleanups.push(session.destroy);
  await expect(session.refresh()).rejects.toThrow(/reconciled/);
  expect(session.view().transportText).toBe('Signed out');
  expect(session.view().rosterUnreachable).toBe(false);
  const unsupported = createSession({ fetch: async () => new Response(JSON.stringify({ layout: { kind: 'future' }, runtime: { devices: {} } })), isDirty: () => false });
  cleanups.push(unsupported.destroy);
  await expect(unsupported.refresh()).rejects.toThrow(/Update the console/);
  expect(unsupported.view().supported).toBe(false);
  expect(await unsupported.request('PUT', '/api/v3/scene', {})).toEqual({ kind: 'refused-locally', reason: 'unsupported' });
});

it('drops schema-invalid known frames and reconciles without merging malformed devices', async () => {
  const { sync, api, pending, state } = harness();
  sync.start(); pending.shift()!(config(1)); await flush();
  const socket = FakeSocket.sockets[0]!;
  socket.message({ type: 'device_online', device: { device_id: A, online: 'yes' } });
  expect(state.roster[A]).toBeUndefined(); expect(api).toHaveBeenCalledTimes(2);
  pending.shift()!(config(2)); await flush();
  socket.message({ type: 'snapshot', config: { ...config(3), operator_state_version: 2 } });
  expect(state.operatorConfig?.revision).toBe(2); expect(api).toHaveBeenCalledTimes(3);
  pending.shift()!(config(4)); await flush();
  expect(state.operatorConfig?.revision).toBe(4);
});

it('a real session validates a legacy config plus fallback roster with the shared schemas', async () => {
  const transport = vi.fn<typeof fetch>()
    .mockResolvedValueOnce(new Response(JSON.stringify({ ...config(1), runtime: undefined })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ [A]: deviceFixture(A) })));
  const session = createSession({ fetch: transport, isDirty: () => false }); cleanups.push(session.destroy);
  await session.refresh();
  expect(session.view()).toMatchObject({ supported: true, etag: '1', roster: { [A]: { online: true } } });
  expect(transport.mock.calls.map(call => call[0])).toEqual(['/api/v3/config', '/devices']);
});
it('malformed config devices block writes without a fallback masking the failed Config parse', async () => {
  const invalid = { ...config(2), runtime: { ...config(2).runtime, devices: { [A]: { online: 'bad' } } } };
  const transport = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(invalid)));
  const session = createSession({ fetch: transport, isDirty: () => false }); cleanups.push(session.destroy);
  session.ingest(config(1));
  await expect(session.refresh()).rejects.toThrow(/Update the console/);
  expect(session.view()).toMatchObject({ supported: false, etagState: 'stale', etag: '1' });
  expect(transport).toHaveBeenCalledTimes(1);
  expect(await session.request('PUT', '/api/v3/scene', {})).toEqual({ kind: 'refused-locally', reason: 'unsupported' });
});
