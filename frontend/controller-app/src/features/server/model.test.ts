import { expect, it } from 'vitest';
import { joiningMessage, manifestInstant, manifestSummary, recordedFact, tabletAddress } from './model';

it('turns a tablet origin into the client URL and explains a missing one', () => {
  expect(tabletAddress('http://10.42.0.1:8080')).toEqual({ kind: 'ready', url: 'http://10.42.0.1:8080/client/' });
  expect(tabletAddress(null)).toEqual({ kind: 'missing' });
  expect(tabletAddress('ftp://10.42.0.1:8080')).toEqual({ kind: 'unusable' });
  expect(joiningMessage({ kind: 'missing' })).toContain('TABLET_WALL_TABLET_ORIGIN');
  expect(joiningMessage({ kind: 'ready', url: 'http://10.42.0.1:8080/client/' })).toBeNull();
});

it('says not recorded when a backup fact has no timestamp', () => {
  expect(recordedFact(null, false)).toBe('not recorded');
  expect(recordedFact('2026-11-15T16:00:00Z', true)).toBe('2026-11-15T16:00:00Z');
  expect(manifestInstant(null)).toBe('not recorded');
  expect(manifestSummary('not recorded', 'not recorded')).toBe('not recorded');
  expect(manifestSummary('2026-11-15T16:00:00Z', 'not recorded')).toBe('Readiness: 2026-11-15T16:00:00Z. Diagnostics: not recorded.');
});
