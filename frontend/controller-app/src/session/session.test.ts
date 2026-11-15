import gridPreview from '../api/__fixtures__/grid-logical.json';
import { GridPreviewSchema } from '../api/grid';
import { A, configFixture as config } from './testFixtures';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createSession, parseConfig } from './session';
import type { Session } from './session';
import { isRecord } from './outcome';

const response = (payload: unknown, status = 200) => new Response(JSON.stringify(payload), { status });
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
const sessions: Session[] = [];
function setup(transport: typeof fetch) {
  const session = createSession({ fetch: transport, now: () => 100, isDirty: () => false });
  sessions.push(session);
  session.ingest(config('first'));
  return session;
}
function paint(value: unknown) {
  if (!isRecord(value) || !isRecord(value.runtime) || !isRecord(value.runtime.devices)) return;
  const device = value.runtime.devices[A];
  return isRecord(device) && isRecord(device.render) ? device.render.state : undefined;
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => { sessions.splice(0).forEach((session) => session.destroy()); vi.useRealTimers(); });

describe('ported operator_session assertions', () => {
  it('publishes readonly authority, serializes commands, and preserves newer runtime and commandEtag', async () => {
    let pending = deferred<Response>();
    const transport = vi.fn<typeof fetch>((_path, options) => options?.method === 'GET'
      ? Promise.resolve(response(config('reconciled'))) : pending.promise);
    const session = setup(transport);
    expect(Reflect.get(session, 'state')).toBeUndefined();
    expect(() => Object.assign(session.view().roster[A]!, { online: false })).toThrow(TypeError);
    const old = session.request('PUT', '/api/v3/scene', {}, { useCurrentEtag: true });
    expect(await session.request('POST', '/api/v3/layout/clear', { confirm: true }, { useCurrentEtag: true }))
      .toEqual({ kind: 'refused-locally', reason: 'busy' });
    session.ingest(config('returned', 'displayed'));
    pending.resolve(response(config('returned')));
    const firstReceipt = await old;
    expect(firstReceipt.kind === 'ok' && paint(firstReceipt.value)).toBe('displayed');
    pending = deferred<Response>();
    const changed = session.request('PUT', '/api/v3/scene', {}, { useCurrentEtag: true });
    session.ingest(config('another-operator', 'displayed'));
    pending.resolve(response(config('own-command')));
    const receipt = await changed;
    expect(receipt.kind === 'ok' && isRecord(receipt.value) && receipt.value.etag).toBe('another-operator');
    expect(receipt.kind === 'ok' && receipt.commandEtag).toBe('own-command');
    transport.mockRejectedValue(new Error('network'));
    expect(await session.request('PATCH', '/api/v3/devices/a', { label: 'A' }, { useCurrentEtag: true }))
      .toMatchObject({ kind: 'uncertain' });
    expect(session.view().uncertain).toBe(true);
    expect(await session.request('PATCH', '/api/v3/devices/a', {}, { useCurrentEtag: true }))
      .toEqual({ kind: 'refused-locally', reason: 'uncertain' });
    await vi.advanceTimersByTimeAsync(0);
    transport.mockResolvedValue(response(config('fresh')));
    await session.refresh();
    expect(session.view().uncertain).toBe(false);
  });

  it.each([500, 502, 503])('latches a %i until explicit refresh, including across incidental reads and snapshots', async (status) => {
    const transport = vi.fn<typeof fetch>(async (_path, options) => options?.method === 'GET'
      ? response(config('read')) : response({ detail: 'Server failed after processing the command' }, status));
    const session = setup(transport);
    expect(await session.request('PATCH', '/api/v3/devices/a', { label: 'Saved name' }, { useCurrentEtag: true }))
      .toMatchObject({ kind: 'uncertain', message: expect.stringContaining('Completion is uncertain.') });
    expect(session.view().uncertain).toBe(true);
    expect(await session.request('PATCH', '/api/v3/devices/a', {}, { useCurrentEtag: true }))
      .toEqual({ kind: 'refused-locally', reason: 'uncertain' });
    expect(transport).toHaveBeenCalledTimes(1);
    await session.request('GET', '/api/v3/config');
    session.ingest(config('socket-update'));
    expect(session.view().uncertain).toBe(true);
    await session.refresh();
    expect(session.view().uncertain).toBe(false);
  });
});

describe('command and refresh boundaries', () => {
  it('a 10 second timeout makes the next durable write refused-locally:uncertain, and refresh clears it', async () => {
    const transport = vi.fn<typeof fetch>((_path, options) => new Promise((_resolve, reject) => {
      options?.signal?.addEventListener('abort', () => reject(new DOMException('timeout', 'AbortError')));
    }));
    const session = setup(transport);
    const command = session.request('PUT', '/api/v3/scene', {});
    await vi.advanceTimersByTimeAsync(9999);
    expect(session.view().busy).toBe(true);
    await vi.advanceTimersByTimeAsync(1);
    expect(await command).toMatchObject({ kind: 'uncertain', message: expect.stringContaining('Request timed out.') });
    expect(await session.request('PUT', '/api/v3/scene', {})).toEqual({ kind: 'refused-locally', reason: 'uncertain' });
    transport.mockResolvedValue(response(config('after-timeout')));
    await session.refresh();
    expect(session.view().uncertain).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it.each(['not-json', 'null'])('an unreadable 2xx (%s) is uncertain', async (body) => {
    const session = setup(async () => new Response(body));
    expect(await session.request('PUT', '/api/v3/scene', {})).toMatchObject({ kind: 'uncertain' });
    expect(session.view().uncertain).toBe(true);
    expect(session.view().busy).toBe(false);
  });

  it('a schema failure on 2xx is uncertain and does not adopt the response', async () => {
    const session = setup(async () => response(config('invalid')));
    expect(await session.request('PUT', '/api/v3/scene', {}, { parse: { parse() { throw new Error('invalid'); } } }))
      .toMatchObject({ kind: 'uncertain' });
    expect(session.view().etag).toBe('first');
  });

  it('a 412 keeps the draft and authority, and 428 remains distinct', async () => {
    const draft = { content: { type: 'color' } };
    const transport = vi.fn<typeof fetch>().mockResolvedValueOnce(response({ detail: 'stale' }, 412))
      .mockResolvedValueOnce(response({ detail: 'missing' }, 428));
    const session = setup(transport);
    expect(await session.request('PUT', '/api/v3/scene', draft, { ifMatch: 'draft-etag' })).toEqual({ kind: 'conflict' });
    expect(draft).toEqual({ content: { type: 'color' } });
    expect(session.view().etag).toBe('first');
    expect(session.view().uncertain).toBe(false);
    expect(await session.request('PUT', '/api/v3/scene', draft)).toEqual({ kind: 'precondition-missing' });
    expect(transport.mock.calls[0]?.[1]?.headers).toMatchObject({ 'If-Match': 'draft-etag', 'Content-Type': 'application/json' });
  });

  it('fences late reads, but durable fencing permits runtime-only updates with the same ETag', async () => {
    let pending = deferred<Response>();
    const session = setup(() => pending.promise);
    const read = session.request('GET', '/api/v3/layouts', undefined, { fenced: true });
    session.ingest(config('second'));
    pending.resolve(response({ layouts: [] }));
    expect(await read).toMatchObject({ kind: 'rejected', status: 409 });
    pending = deferred<Response>();
    const durableRead = session.request('GET', '/api/v3/layouts', undefined, { fenced: 'durable' });
    session.ingest(config('second', 'displayed'));
    pending.resolve(response({ layouts: [] }));
    expect(await durableRead).toEqual({ kind: 'ok', value: { layouts: [] } });
    pending = deferred<Response>();
    const changed = session.request('GET', '/api/v3/layouts', undefined, { fenced: 'durable' });
    session.ingest(config('third'));
    pending.resolve(response({ layouts: [] }));
    expect(await changed).toMatchObject({ kind: 'rejected', status: 409 });
  });

  it('refuses unsupported and missing ETag writes before transport', async () => {
    const transport = vi.fn<typeof fetch>();
    const session = setup(transport);
    expect(() => session.ingest({ layout: { kind: 'future' } })).toThrow(/Update the console/);
    expect(await session.request('PUT', '/api/v3/scene', {})).toEqual({ kind: 'refused-locally', reason: 'unsupported' });
    expect(() => session.ingest({ ...config('valid'), etag: null })).toThrow(/Unsupported/);
    session.ingest(config('valid'));
    expect(await session.request('PUT', '/api/v3/scene', {}, { ifMatch: '' }))
      .toEqual({ kind: 'refused-locally', reason: 'stale-etag' });
    expect(transport).not.toHaveBeenCalled();
    expect(() => parseConfig({ layout: { kind: 'logical' }, operator_state_version: 2 })).toThrow(/Unsupported/);
  });

  it('previews and calibration-check remain available during a durable command', async () => {
    const pending = deferred<Response>();
    const transport = vi.fn<typeof fetch>().mockReturnValueOnce(pending.promise).mockImplementation(async () => response({ preview: true }));
    const session = setup(transport);
    const command = session.request('PUT', '/api/v3/scene', {});
    expect(await session.request('POST', '/api/v3/grid/preview', {})).toMatchObject({ kind: 'ok' });
    expect(await session.request('POST', '/api/v3/calibration-check', {})).toMatchObject({ kind: 'ok' });
    pending.resolve(response(config('written')));
    expect(await command).toMatchObject({ kind: 'ok' });
    expect(session.view().etag).toBe('written');
  });

  it('a failed refresh retains the uncertainty latch', async () => {
    const transport = vi.fn<typeof fetch>().mockRejectedValue(new Error('network'));
    const session = setup(transport);
    await session.request('PUT', '/api/v3/scene', {});
    await expect(session.refresh()).rejects.toThrow(/reconciled/);
    expect(session.view().uncertain).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });
});

it('adopts a successful config once, preserves unknown fields, and publishes the same frozen snapshot to the store', async () => {
  const configWithExtensions = { ...config('saved'), extension: { keep: true }, layout: { ...config('saved').layout, future: { keep: true } } };
  const setState = vi.fn();
  const session = createSession({ store: { setState }, fetch: async () => response(configWithExtensions), isDirty: () => false });
  sessions.push(session);
  session.ingest(config('first'));
  const adoption = session.view().adoption;
  const outcome = await session.request('PUT', '/api/v3/scene', {}, { parse: { parse: parseConfig } });
  expect(outcome).toMatchObject({ kind: 'ok', value: configWithExtensions });
  expect(session.view().adoption).toBe(adoption + 1);
  expect(session.view().config).toMatchObject(configWithExtensions);
  expect(setState.mock.lastCall?.[0].server).toBe(session.view());
});

it('normalizes error details and uses tablet labels, and a 401 publishes Signed out', async () => {
  const id = '1eb61a6f-0872-4cb4-9107-6523136723ae';
  const transport = vi.fn<typeof fetch>().mockResolvedValueOnce(response({ detail: { code: 'unready', message: `Tablet ${id} is unready` } }, 409))
    .mockResolvedValueOnce(response({ detail: [{ msg: 'bad value', loc: ['body', 'name'] }] }, 422))
    .mockResolvedValueOnce(response({ detail: 'Authentication required' }, 401));
  const session = setup(transport);
  session.ingest({ ...config('first'), device_labels: { [id]: 'North wall' } });
  expect(await session.request('POST', '/api/v3/grid', {}))
    .toEqual({ kind: 'rejected', status: 409, message: 'Tablet North wall is unready' });
  expect(await session.request('POST', '/api/v3/grid', {}))
    .toMatchObject({ kind: 'rejected', status: 422, message: 'bad value' });
  expect(await session.request('GET', '/api/v3/config')).toMatchObject({ kind: 'rejected', status: 401 });
  expect(session.view().transportText).toBe('Signed out');
  expect(session.view().uncertain).toBe(false);
});

it('refresh waits for a newer adoption and retains uncertainty on timeout', async () => {
  let pending = deferred<Response>();
  const transport = vi.fn<typeof fetch>(() => pending.promise);
  const session = setup(transport);
  const failed = session.request('PUT', '/api/v3/scene', {});
  pending.resolve(response({ detail: 'failed' }, 500)); await failed;
  pending = deferred<Response>();
  const refresh = session.refresh();
  const rejected = expect(refresh).rejects.toThrow(/snapshot timed out/);
  await vi.advanceTimersByTimeAsync(9999);
  expect(session.view().uncertain).toBe(true);
  await vi.advanceTimersByTimeAsync(1);
  await rejected;
  expect(session.view().uncertain).toBe(true);
  pending.resolve(response(config('late-read')));
  await vi.advanceTimersByTimeAsync(0);
});

it('schema-invalid config responses cannot be hidden by a newer socket adoption', async () => {
  const pending = deferred<Response>();
  const session = setup(() => pending.promise);
  const writing = session.request('PUT', '/api/v3/scene', {}, { useCurrentEtag: true });
  session.ingest(config('newer'));
  pending.resolve(response({ ...config('invalid'), layout: { kind: 'logical', width: 'bad' } }));
  expect(await writing).toMatchObject({ kind: 'uncertain' });
  expect(session.view()).toMatchObject({ supported: false, etagState: 'stale', etag: 'newer', uncertain: true });
});
it('invalid config reads and invalid roster values fail the shared schemas', async () => {
  const session = setup(async () => response({ ...config('invalid'), revision: 'bad' }));
  expect(await session.request('GET', '/api/v3/config')).toMatchObject({ kind: 'rejected' });
  expect(session.view().supported).toBe(false);
  expect(session.view().config?.revision).toBe(1);
});

it('a fenced obsolete config response cannot mark newer valid authority unsupported', async () => {
  const pending = deferred<Response>(), session = setup(() => pending.promise);
  const reading = session.request('GET', '/api/v3/config', undefined, { fenced: true });
  session.ingest(config('newer'));
  pending.resolve(response({ layout: { kind: 'future' } }));
  expect(await reading).toMatchObject({ kind: 'rejected', status: 409 });
  expect(session.view()).toMatchObject({ supported: true, etag: 'newer', etagState: 'current' });
});

it('a real grid preview layout is parsed as GridPreview and never treated as an authoritative Config', async () => {
  const session = setup(async () => response(gridPreview));
  const before = session.view();
  const result = await session.request('POST', '/api/v3/grid/preview', {}, { parse: GridPreviewSchema });
  expect(result).toEqual({ kind: 'ok', value: GridPreviewSchema.parse(gridPreview) });
  expect(session.view()).toBe(before);
  expect(session.view()).toMatchObject({ supported: true, etag: 'first', uncertain: false });
});
