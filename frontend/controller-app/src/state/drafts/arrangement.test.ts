import { expect, it } from 'vitest';
import { configFixture } from '../../session/testFixtures';
import { arrangementReducer, createArrangement } from './arrangement';
it('undo stops at 80 entries and redo clears after a new edit', () => {
  const config = configFixture('base');
  let draft = createArrangement(config.layout, config.etag);
  for (let width = 101; width <= 200; width++) draft = arrangementReducer(draft, { type: 'edit', layout: { ...config.layout, width } });
  expect(draft.undo).toHaveLength(80);
  for (let i = 0; i < 100; i++) draft = arrangementReducer(draft, { type: 'undo' });
  expect(draft.draft.width).toBe(120); expect(draft.redo).toHaveLength(80);
  draft = arrangementReducer(draft, { type: 'redo' }); expect(draft.draft.width).toBe(121);
  draft = arrangementReducer(draft, { type: 'edit', layout: { ...config.layout, width: 800 } });
  expect(draft.redo).toEqual([]); expect(config.layout.width).toBe(100);
});
