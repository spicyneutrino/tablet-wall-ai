import { expect, it } from 'vitest';
import { ConfigEtagSchema } from '../../api/etag';
import { contentReducer, emptyContent } from './content';
it('selections keep the original guard and saved scenes cannot be rebased with Keep mine', () => {
  const etag = ConfigEtagSchema.parse('base');
  const saved = contentReducer(emptyContent(), { type: 'select', selection: { type: 'color' }, etag, savedScene: { name: 'Lobby', etag } });
  expect(contentReducer(saved, { type: 'rebuild', etag: ConfigEtagSchema.parse('new'), version: saved.version })).toBe(saved);
  const changed = contentReducer(saved, { type: 'select', selection: { type: 'calibration' }, etag: ConfigEtagSchema.parse('new') });
  expect(changed.baseEtag).toBe('base');
  expect(changed.savedScene).toBeNull();
  expect(contentReducer(changed, { type: 'rebuild', etag, version: changed.version - 1 })).toBe(changed);
});
