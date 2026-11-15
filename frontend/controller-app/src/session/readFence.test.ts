import { createRequire } from 'node:module';
import { expect, it } from 'vitest';
import { readFence } from './readFence';

const legacy = createRequire(import.meta.url)('../../../controller/operator-state.js') as { readFence: typeof readFence };

it('matches legacy read tickets across superseded reads and event invalidation', () => {
  const current = readFence(), old = legacy.readFence();
  const first = current.start(), oldFirst = old.start();
  const next = current.start(), oldNext = old.start();
  expect(current.accept(next)).toBe(old.accept(oldNext));
  expect(current.accept(first)).toBe(old.accept(oldFirst));
  expect(current.current(first)).toBe(old.current(oldFirst));
  current.event(); old.event();
  expect(current.accept(next)).toBe(old.accept(oldNext));
  expect(current.current(next)).toBe(old.current(oldNext));
  const fresh = current.start(), oldFresh = old.start();
  expect(current.accept(fresh)).toBe(old.accept(oldFresh));
  expect(current.accept(fresh)).toBe(true);
});
