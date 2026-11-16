import { expect, it, vi } from 'vitest';
import { ConfigSchema } from '../../api/config';
import { A, configFixture } from '../../session/testFixtures';
import { createSession } from '../../session/session';
import { createWallStore } from '../store';
import pattern from '../../api/__fixtures__/test-pattern.json';
import {
  colourDeliveryText, colourOutcomeText, patternOutcomeText, selectTestPattern, sendTestColour,
  showTestPattern, testColours, testPatterns,
} from './testPatterns';

function reply(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
}

function setup(responses: Array<() => Response>) {
  const store = createWallStore();
  const transport = vi.fn<typeof fetch>();
  responses.forEach(response => transport.mockImplementationOnce(async () => response()));
  const session = createSession({ store, fetch: transport, isDirty: () => false });
  session.ingest(configFixture('base'));
  return { store, session, transport };
}

it('offers two patterns and the five test colours', () => {
  expect(testPatterns.map(entry => entry.name)).toEqual(['Calibration grid', 'Black']);
  expect(testColours.map(entry => entry.name)).toEqual(['Red', 'Green', 'Blue', 'White', 'Black']);
  expect(new Set(testColours.map(entry => entry.color)).size).toBe(5);
});

it('selecting a test pattern previews it without a request', () => {
  const { store, transport } = setup([]);
  selectTestPattern(store, 'grid');
  expect(store.getState().ui.testPattern).toBe('grid');
  selectTestPattern(store, null);
  expect(store.getState().ui.testPattern).toBeNull();
  expect(transport).not.toHaveBeenCalled();
});

it('shows the grid by publishing the pattern and then selecting its scene with the returned ETags', async () => {
  const after = ConfigSchema.parse(configFixture('after'));
  const { store, session, transport } = setup([() => reply(pattern), () => reply(after)]);
  const outcome = await showTestPattern(store, session, 'grid');
  expect(outcome.kind).toBe('ok');
  expect(transport.mock.calls.map(call => call[0])).toEqual(['/api/v3/test-pattern', '/api/v3/scene']);
  const [postPath, post] = transport.mock.calls[0]!;
  expect(postPath).toBe('/api/v3/test-pattern');
  expect(post?.method).toBe('POST');
  expect(post?.headers).toMatchObject({ 'If-Match': 'base' });
  expect(JSON.parse(String(post?.body))).toEqual({ pattern: 'grid' });
  const [putPath, put] = transport.mock.calls[1]!;
  expect(putPath).toBe('/api/v3/scene');
  expect(put?.method).toBe('PUT');
  expect(put?.headers).toMatchObject({ 'If-Match': pattern.etag });
  expect(JSON.parse(String(put?.body))).toEqual({ content: { type: 'image', asset: pattern.id, fit: 'contain' } });
  expect(store.getState().server.etag).toBe('after');
  session.destroy();
});

it('shows black with the black pattern body and a black background', async () => {
  const { store, session, transport } = setup([() => reply(pattern), () => reply(configFixture('after'))]);
  expect((await showTestPattern(store, session, 'black')).kind).toBe('ok');
  const post = transport.mock.calls[0]![1];
  expect(JSON.parse(String(post?.body))).toEqual({ pattern: 'black' });
  const put = transport.mock.calls[1]![1];
  expect(JSON.parse(String(put?.body))).toEqual({ content: { type: 'image', asset: pattern.id, fit: 'contain', background: '#000000' } });
  session.destroy();
});

it('a refused pattern keeps a readable reason and sends no scene write', async () => {
  const { store, session, transport } = setup([() => reply({ detail: 'grid requires a physical layout' }, 422)]);
  const outcome = await showTestPattern(store, session, 'grid');
  expect(outcome).toEqual({ kind: 'rejected', status: 422, message: 'grid requires a physical layout' });
  expect(patternOutcomeText(outcome)).toBe('grid requires a physical layout');
  expect(transport).toHaveBeenCalledTimes(1);
  session.destroy();
});

it('sends a colour to all tablets and reports the delivery count', async () => {
  const { session, transport } = setup([() => reply({ color: '#ef4444', updated: 4, delivered: 4 })]);
  const outcome = await sendTestColour(session, '#ef4444', { kind: 'all' });
  expect(outcome.kind).toBe('ok');
  expect(transport.mock.calls[0]![0]).toBe('/devices/color');
  expect(transport.mock.calls[0]![1]?.headers).not.toHaveProperty('If-Match');
  expect(JSON.parse(String(transport.mock.calls[0]![1]?.body))).toEqual({ color: '#ef4444' });
  expect(outcome.kind === 'ok' && colourDeliveryText(outcome.value, { kind: 'all' })).toBe('Sent to 4 tablets');
  if (outcome.kind === 'ok') expect(colourOutcomeText(outcome, { kind: 'all' })).toBe('Sent to 4 tablets');
  session.destroy();
});

it('sends a colour to one tablet by id and says when it was not delivered', async () => {
  const target = { kind: 'tablet', id: A, name: 'Tablet 1' } as const;
  const { session, transport } = setup([
    () => reply({ device_id: A, color: '#3b82f6', delivered: true }),
    () => reply({ device_id: A, color: '#3b82f6', delivered: false }),
  ]);
  const delivered = await sendTestColour(session, '#3b82f6', target);
  expect(transport.mock.calls[0]![0]).toBe(`/devices/${A}/color`);
  expect(delivered.kind === 'ok' && colourDeliveryText(delivered.value, target)).toBe('Sent to Tablet 1');
  const missing = await sendTestColour(session, '#3b82f6', target);
  expect(missing.kind === 'ok' && colourDeliveryText(missing.value, target)).toBe('Not delivered. Tablet 1 is offline.');
  session.destroy();
});

it('maps an unreadable colour response to a plain reason', async () => {
  const { session } = setup([() => new Response('not json', { status: 200 })]);
  const outcome = await sendTestColour(session, '#ffffff', { kind: 'all' });
  expect(outcome.kind).toBe('uncertain');
  expect(colourOutcomeText(outcome, { kind: 'all' }))
    .toBe('The command may have completed, but its response was unreadable. Refresh status and review before retrying.');
  session.destroy();
});
