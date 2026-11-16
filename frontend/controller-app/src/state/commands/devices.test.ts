import { expect, it, vi } from 'vitest';
import { ConfigSchema } from '../../api/config';
import { LabelCommandSchema } from '../../api/devices';
import type { DeviceId } from '../../api/devices';
import { paths } from '../../api/paths';
import { A, B, C, configFixture, deviceFixture } from '../../session/testFixtures';
import type { Config } from '../../api/config';
import { createSession } from '../../session/session';
import { formKey } from '../drafts/tabletForms';
import { createWallStore, editForm, observeForm } from '../store';
import {
  ACTION_RESULT, BATCH_WORD, assignmentBody, deviceCommand, labelBody, labelProblem,
  runDeviceBatch, saveLabel, saveModelChoice,
} from './devices';

const D = '00000000-0000-4000-8000-000000000004' as DeviceId;
const MODEL = ConfigSchema.parse(configFixture('base')).tablet_models['google-pixel-c']!;

function setup(config: Config = configFixture('base')) {
  const store = createWallStore();
  const transport = vi.fn<typeof fetch>();
  const session = createSession({ store, fetch: transport, isDirty: () => false });
  session.ingest(config);
  return { store, session, transport };
}

function respond(transport: ReturnType<typeof setup>['transport'], body: unknown, status = 200) {
  transport.mockResolvedValueOnce(new Response(JSON.stringify(body), { status,
    headers: { 'Content-Type': 'application/json' } }));
}

function sent(transport: ReturnType<typeof setup>['transport'], index = 0) {
  const call = transport.mock.calls[index];
  if (!call) throw new Error(`missing request ${index}`);
  return { url: call[0], method: call[1]?.method, headers: call[1]?.headers as Record<string, string>,
    body: call[1]?.body, signal: call[1]?.signal };
}

function withDevices(etag: string, ids: readonly DeviceId[], offline: readonly DeviceId[] = []): Config {
  const base = configFixture(etag);
  return ConfigSchema.parse({ ...base, runtime: { ...base.runtime, devices: Object.fromEntries(ids.map(id =>
    [id, deviceFixture(id, { caps: ['identify', 'render_ack'], online: !offline.includes(id) })])) } });
}

function assigned(etag: string, mode: 'explicit' | 'manual', modelId: string | null): Config {
  const base = configFixture(etag);
  return ConfigSchema.parse({ ...base, tablet_assignments: { [A]: mode === 'manual'
    ? { mode, model_id: null }
    : { mode, model_id: modelId!, model: MODEL, profile_revision: 1, calibration_revision: 1 } } });
}

it('measures names the way the server does: trimmed, code points, 80 at most', () => {
  expect(labelProblem('')).toBeNull();
  expect(labelProblem('x'.repeat(80))).toBeNull();
  expect(labelProblem(`  ${'x'.repeat(80)}  `)).toBeNull();
  expect(labelProblem('😀'.repeat(80))).toBeNull();
  expect(labelProblem('x'.repeat(81))).toBe('Names are 80 characters at most. This name has 81.');
  expect(labelProblem('😀'.repeat(81))).toBe('Names are 80 characters at most. This name has 81.');
  expect(labelBody('  Lab tablet  ')).toEqual({ label: 'Lab tablet' });
  expect(labelBody('   ')).toEqual({ label: null });
  expect(LabelCommandSchema.parse(labelBody('Pad'))).toEqual({ label: 'Pad' });
});

it('renames with one PATCH, the submitted guard and the trimmed label, then clears the draft', async () => {
  const { store, session, transport } = setup();
  observeForm(store, A, 'name');
  editForm(store, formKey(A, 'name'), { name: '  Lab tablet  ' });
  respond(transport, configFixture('next'));
  const outcome = await saveLabel(store, session, A);
  expect(outcome.kind).toBe('ok');
  expect(sent(transport)).toMatchObject({ url: paths.device(A), method: 'PATCH', headers: { 'If-Match': 'base' } });
  expect(sent(transport).body).toBe(JSON.stringify({ label: 'Lab tablet' }));
  expect(transport).toHaveBeenCalledTimes(1);
  expect(store.getState().forms[formKey(A, 'name')]).toMatchObject({ dirty: false, conflict: false,
    baseline: { name: 'Lab tablet' }, values: { name: 'Lab tablet' } });
});

it('refuses a name over 80 characters before any request', async () => {
  const { store, session, transport } = setup();
  observeForm(store, A, 'name');
  editForm(store, formKey(A, 'name'), { name: 'x'.repeat(81) });
  const outcome = await saveLabel(store, session, A);
  expect(outcome.kind).toBe('rejected');
  if (outcome.kind === 'rejected') expect(outcome.message).toContain('80 characters');
  expect(transport).not.toHaveBeenCalled();
});

it('saves an explicit model with one PUT, adopts the returned revision and keeps the form', async () => {
  const { store, session, transport } = setup();
  observeForm(store, A, 'model');
  editForm(store, formKey(A, 'model'), { 'tablet-model': 'google-pixel-c' });
  respond(transport, { assignment: { mode: 'explicit', model_id: 'google-pixel-c', model: MODEL,
    profile_revision: 1, calibration_revision: 1 }, suggestions: [], etag: 'next' });
  respond(transport, assigned('next', 'explicit', 'google-pixel-c'));
  const outcome = await saveModelChoice(store, session, A, 'google-pixel-c');
  expect(outcome.kind).toBe('ok');
  expect(sent(transport)).toMatchObject({ url: paths.tabletAssignment(A), method: 'PUT', headers: { 'If-Match': 'base' } });
  expect(JSON.parse(String(sent(transport).body))).toEqual({ mode: 'explicit', model_id: 'google-pixel-c' });
  expect(sent(transport, 1)).toMatchObject({ url: paths.config, method: 'GET' });
  expect(transport.mock.calls.filter(call => call[1]?.method === 'PUT')).toHaveLength(1);
  expect(store.getState().forms[formKey(A, 'model')]).toMatchObject({ dirty: false,
    values: { 'tablet-model': 'google-pixel-c' }, baseline: { 'tablet-model': 'google-pixel-c' } });
});

it('saves Manual measurements without a model id and refuses an empty choice', async () => {
  const { store, session, transport } = setup();
  expect(assignmentBody('')).toBeNull();
  observeForm(store, A, 'model');
  editForm(store, formKey(A, 'model'), { 'tablet-model': 'manual' });
  respond(transport, { assignment: { mode: 'manual', model_id: null }, suggestions: [], etag: 'next' });
  respond(transport, assigned('next', 'manual', null));
  expect((await saveModelChoice(store, session, A, 'manual')).kind).toBe('ok');
  expect(JSON.parse(String(sent(transport).body))).toEqual({ mode: 'manual', model_id: null });
  const before = transport.mock.calls.length;
  expect((await saveModelChoice(store, session, A, '')).kind).toBe('rejected');
  expect(transport.mock.calls.length).toBe(before);
});

it('sends Identify, Retry image and Reconnect once each with If-Match and the duration body', async () => {
  const config = withDevices('base', [A]);
  const { session, transport } = setup(config);
  respond(transport, withDevices('one', [A]));
  expect((await deviceCommand(session, A, 'identify')).kind).toBe('ok');
  expect(sent(transport)).toMatchObject({ url: paths.identify(A), method: 'POST', headers: { 'If-Match': 'base' } });
  expect(JSON.parse(String(sent(transport).body))).toEqual({ duration_ms: 5000 });

  respond(transport, withDevices('two', [A]));
  expect((await deviceCommand(session, A, 'retry')).kind).toBe('ok');
  expect(sent(transport, 1)).toMatchObject({ url: paths.retryImage(A), method: 'POST', headers: { 'If-Match': 'one' } });
  expect(sent(transport, 1).body).toBeUndefined();

  respond(transport, withDevices('three', [A]));
  expect((await deviceCommand(session, A, 'reconnect')).kind).toBe('ok');
  expect(sent(transport, 2)).toMatchObject({ url: paths.reconnect(A), method: 'POST', headers: { 'If-Match': 'two' } });
  expect(sent(transport, 2).body).toBeUndefined();
  expect(transport).toHaveBeenCalledTimes(3);
  expect(ACTION_RESULT).toEqual({ identify: 'Flashing for 5 s', retry: 'Retry sent', reconnect: 'Reconnect sent' });
});

it('runs a batch in captured order with each preceding returned ETag', async () => {
  const ids = [A, B, C, D];
  const { store, session, transport } = setup(withDevices('base', ids));
  let etag = 'base';
  transport.mockImplementation(async (url, init) => {
    expect(init?.method).toBe('POST');
    expect(new URL(String(url), 'http://localhost').pathname).toBe(paths.identify(ids.shift()!));
    const next = etag === 'base' ? 'one' : etag === 'one' ? 'two' : etag === 'two' ? 'three' : 'four';
    etag = next;
    return new Response(JSON.stringify(withDevices(next, [A, B, C, D])), { status: 200,
      headers: { 'Content-Type': 'application/json' } });
  });
  const guards: string[] = [];
  store.subscribe((state, previous) => {
    if (state.server.etag !== previous.server.etag) guards.push(String(state.server.etag));
  });
  const result = await runDeviceBatch(store, session, 'identify', [A, B, C, D]);
  expect(result.subjects.map(subject => [subject.id, subject.status])).toEqual([
    [A, 'completed'], [B, 'completed'], [C, 'completed'], [D, 'completed'],
  ]);
  expect(result.subjects.map(subject => subject.message)).toEqual(Array(4).fill('Flashing for 5 s'));
  expect(guards).toEqual(['one', 'two', 'three', 'four']);
  expect(transport).toHaveBeenCalledTimes(4);
});

it('stops a batch on a conflict and leaves the rest untouched', async () => {
  const ids = [A, B, C, D];
  const { store, session, transport } = setup(withDevices('base', ids));
  respond(transport, withDevices('one', ids));
  respond(transport, withDevices('two', ids));
  respond(transport, { detail: 'configuration changed; reload' }, 412);
  const result = await runDeviceBatch(store, session, 'identify', ids);
  expect(result.subjects.map(subject => subject.status)).toEqual(['completed', 'completed', 'conflict', 'untouched']);
  expect(result.subjects[2]?.message).toMatch(/wall changed/i);
  expect(result.subjects[3]?.message).toBe('Not reached.');
  const writes = transport.mock.calls.filter(call => call[1]?.method === 'POST');
  expect(writes).toHaveLength(3);
  expect(writes.map(call => (call[1]?.headers as Record<string, string>)['If-Match'])).toEqual(['base', 'one', 'two']);
});

it('stops a batch on an uncertain completion and leaves the rest untouched', async () => {
  const ids = [A, B, C, D];
  const { store, session, transport } = setup(withDevices('base', ids));
  respond(transport, withDevices('one', ids));
  transport.mockRejectedValueOnce(new TypeError('connection lost'));
  const result = await runDeviceBatch(store, session, 'identify', ids);
  expect(result.subjects.map(subject => subject.status)).toEqual(['completed', 'uncertain', 'untouched', 'untouched']);
  expect(result.subjects[1]?.message).toMatch(/Not confirmed/);
  expect(transport).toHaveBeenCalledTimes(2);
  expect(BATCH_WORD.uncertain).toBe('Uncertain');
  expect(store.getState().server.uncertain).toBe(true);
});

it('reports an offline tablet first and sends nothing', async () => {
  const ids = [A, B, C, D];
  const { store, session, transport } = setup(withDevices('base', ids, [A]));
  const result = await runDeviceBatch(store, session, 'reconnect', ids);
  expect(result.subjects.map(subject => subject.status)).toEqual(['failed', 'untouched', 'untouched', 'untouched']);
  expect(result.subjects[0]?.message).toMatch(/Offline/);
  expect(transport).not.toHaveBeenCalled();
});
