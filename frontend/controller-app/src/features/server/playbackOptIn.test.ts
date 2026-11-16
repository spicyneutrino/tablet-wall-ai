import { afterEach, expect, it, vi } from 'vitest';
import { PLAYBACK_OPT_IN_KEY, readPlaybackOptIn, writePlaybackOptIn } from './playbackOptIn';

afterEach(() => { vi.unstubAllGlobals(); });

it('stores the playlist switch under tablet-wall-playback', () => {
  const store = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => { store.set(key, value); },
  });
  expect(readPlaybackOptIn()).toBe(false);
  expect(writePlaybackOptIn(true)).toBe(true);
  expect(store.get(PLAYBACK_OPT_IN_KEY)).toBe('on');
  expect(readPlaybackOptIn()).toBe(true);
  expect(writePlaybackOptIn(false)).toBe(true);
  expect(readPlaybackOptIn()).toBe(false);
});

it('stays off when storage throws', () => {
  vi.stubGlobal('localStorage', {
    getItem: () => { throw new Error('blocked'); },
    setItem: () => { throw new Error('blocked'); },
  });
  expect(readPlaybackOptIn()).toBe(false);
  expect(writePlaybackOptIn(true)).toBe(false);
});
