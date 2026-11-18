import { expect, it } from 'vitest';
import { ConfigSchema } from '../../api/config';
import { A, B, configFixture, deviceFixture, renderFixture } from '../../session/testFixtures';
import { createWallStore } from '../../state/store';
import { boardView, reportAge } from './model';

function wall() {
  const token = { generation: 'session', revision: 1, connection_id: 'c', render_seq: 1, mapping_revision: 'm', asset: null };
  const device = deviceFixture(A, { number: 1, connection_id: 'c',
    mapping: { state: 'ready', revision: 'm', reason: null, viewport: null },
    render: renderFixture('displayed', { current: true, age_ms: 0, observed_mono: 0, expected_token: token, accepted_token: token }) });
  const config = ConfigSchema.parse({ ...configFixture('base'), runtime: { devices: { [A]: device }, observed_at: null,
    presentation: { owner: 'static', state: 'static' } },
    layout: { kind: 'logical', width: 100, height: 100, sizing: { mode: 'fixed', padding: 0 },
      placements: { [A]: { x: 0, y: 0, w: 100, h: 100, bezel: { top: 0, bottom: 0, left: 0, right: 0 } } } } });
  return { ...createWallStore(0).getState().server, config, roster: { [A]: device } };
}

it('counts calibration paint as showing and expires it at 15 seconds', () => {
  const server = wall();
  server.config.scene.content = { type: 'calibration' };
  expect(boardView(server, 14_999).summary).toBe('1 of 1 showing');
  const expired = boardView(server, 15_000);
  expect(expired.summary).toBe('0 of 1 showing');
  expect(expired.tablets[0]).toMatchObject({ status: 'stale', word: 'Stale', attention: true });
});

it('uses the live roster rather than older configuration evidence', () => {
  const server = wall();
  server.roster[A] = { ...server.roster[A]!, online: false };
  const view = boardView(server, 0);
  expect(view.summary).toBe('0 of 1 showing');
  expect(view.tablets[0]).toMatchObject({ word: 'Offline', tone: 'warn' });
});

it('keeps reservations and registrations once each, with a short fallback name', () => {
  const server = wall();
  server.roster = { [B]: deviceFixture(B) };
  const view = boardView(server, 0);
  expect(view.tablets.map(tablet => tablet.id)).toEqual([A, B]);
  expect(view.tablets[0]).toMatchObject({ status: 'unknown', word: 'Missing tablet', name: `Tablet ${A.slice(-6)}` });
  expect(view.tablets[1]).toMatchObject({ status: 'unplaced', word: 'Not placed' });
  expect(view.total).toBe(1);
});

it('does not show old paint as healthy while the server cannot be checked', () => {
  for (const rosterUnreachable of [false, true]) {
    const view = boardView({ ...wall(), rosterUnreachable, rosterError: 'Status unavailable' }, 0);
    expect(view.summary).toBe('0 of 1 showing');
    expect(view.tablets[0]).toMatchObject({ status: 'unknown', word: 'Unknown', showing: false, tone: 'muted' });
  }
});

it('ages last-seen reports, tolerates clock skew, and says when no report exists', () => {
  const seen = '2026-11-15T12:00:00Z', now = Date.parse(seen);
  expect(reportAge(seen, now - 1000).label).toBe('just now');
  expect(reportAge(seen, now + 59_999).label).toBe('just now');
  expect(reportAge(seen, now + 60_000).label).toBe('1 min');
  expect(reportAge(seen, now + 7_200_000).label).toBe('2 hr');
  expect(reportAge(seen, now + 86_400_000).label).toBe('1 d');
  expect(reportAge(null, now).label).toBe('No report');
  expect(reportAge('invalid', now).label).toBe('No report');
});
