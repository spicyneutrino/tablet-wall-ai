import { describe, expect, it } from 'vitest';
import { payloads } from './model';

describe('measurement payload validation', () => {
  it('rejects blank dimensions instead of treating them as zero', () => {
    const invalid: string[] = [];
    expect(() => payloads({ profilePixelWidth: '', profilePixelHeight: '', profileActiveWidth: '', profileActiveHeight: '100' },
      (key, failed) => { if (failed) invalid.push(key); }).buildProfileBody()).toThrow('Active width must be a positive number.');
    expect(invalid).toEqual(['profileActiveWidth']);
  });
});
