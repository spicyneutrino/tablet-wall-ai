// @vitest-environment jsdom
import { createElement } from 'react';
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { ConfigSchema } from '../api/config';
import { SceneInputSchema } from '../api/scene';
import { GridPreviewSchema } from '../api/grid';
import { configFixture } from '../session/testFixtures';
import { createSession } from '../session/session';
import { createWallStore, editArrangement, editContent, editForm, observeForm, selectDevice } from './store';
import { createGrid } from './drafts/grid';
import { GridCommandSchema } from '../api/grid';
import { A, B } from '../session/testFixtures';
import { selectStageEditable, selectStageMode, selectPreviewContent, selectPreviewLayout,
  selectOnWallLayout, selectOnWallContent, selectOnWallMode, selectOnWallEditable, selectPreviewUnavailable, selectSelectedNameDirty, useWallStore } from './hooks';

it('ports all 16 stageView assertions at operator_state lines 120–141, plus explicit edit mode and On wall editability', () => {
  const store = createWallStore(), session = createSession({ store, isDirty: () => false });
  const image = SceneInputSchema.parse({ type: 'image', asset: 'sha256:' + 'a'.repeat(64), fit: 'contain' });
  const config = ConfigSchema.parse({ ...configFixture('base'), scene: { content: image } });
  session.ingest(config);
  const state = () => store.getState();
  expect(selectStageEditable(state())).toBe(false);
  store.setState({ ui: { ...state().ui, editLayout: true } });
  expect(selectStageMode(state())).toBe('live');
  expect(selectStageEditable(state())).toBe(true);
  const preview = SceneInputSchema.parse({ type: 'image', asset: 'sha256:' + 'b'.repeat(64), fit: 'cover' });
  editContent(store, { type: 'select', selection: preview, etag: config.etag });
  const selectedContent = selectPreviewContent(state());
  expect(selectedContent?.type === 'image' && selectedContent.asset).toBe(preview.type === 'image' && preview.asset);
  expect(selectStageMode(state())).toBe('image-preview');
  expect(selectStageEditable(state())).toBe(false);
  expect(selectOnWallContent(state())).toEqual(image);
  expect(selectOnWallLayout(state())).toBe(state().server.config!.layout);
  expect(selectOnWallMode()).toBe('live');
  expect(selectOnWallEditable()).toBe(false);
  editContent(store, { type: 'discard' });
  const command = GridCommandSchema.parse({ kind: 'logical', device_ids: [A], rows: 1, columns: 1,
    gap: 0, padding: 0, sizing: 'fixed', orientation: 'preserve', allow_empty_cells: false, release_unselected: [] });
  store.setState({ grid: { ...createGrid(command, config.etag), preview: GridPreviewSchema.parse({ layout: { ...config.layout, width: 200 },
    order: [A], warnings: [], guards: {}, base_etag: config.etag, reservations_removed: [], previous_kind: 'logical' }) } });
  expect(selectPreviewLayout(state())?.width).toBe(200);
  expect(selectStageMode(state())).toBe('arrangement-preview');
  expect(selectStageEditable(state())).toBe(false);
  store.setState({ grid: null }); editArrangement(store, { type: 'edit', layout: { ...config.layout, width: 300 } });
  expect(selectPreviewLayout(state())?.width).toBe(300);
  expect(selectStageMode(state())).toBe('arrangement-preview');
  expect(selectStageEditable(state())).toBe(true);
  store.setState({ ui: { ...state().ui, activeImageUnavailableId: image.type === 'image' ? image.asset : null } });
  expect(selectPreviewUnavailable(state())).toBe(true);
  expect(selectOnWallContent(state())?.available).toBeUndefined();
  session.destroy();
});

afterEach(cleanup);
it('a primitive selector does not rerender when another device draft or runtime snapshot changes', () => {
  const store = createWallStore(), session = createSession({ store, isDirty: () => false });
  session.ingest(configFixture('base')); selectDevice(store, A); observeForm(store, A, 'name'); observeForm(store, B, 'name');
  let renders = 0;
  function SelectedName() {
    const dirty = useWallStore(store, selectSelectedNameDirty); renders += 1;
    return createElement('output', null, String(dirty));
  }
  const view = render(createElement(SelectedName));
  expect(view.getByText('false')).toBeTruthy(); expect(renders).toBe(1);
  act(() => editForm(store, `${B}:name`, { name: 'B' }));
  act(() => session.ingest(configFixture('base', 'displayed')));
  expect(renders).toBe(1);
  act(() => editForm(store, `${A}:name`, { name: 'A' }));
  expect(view.getByText('true')).toBeTruthy(); expect(renders).toBe(2);
  session.destroy();
});
