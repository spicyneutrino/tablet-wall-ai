import { createStore } from 'zustand/vanilla';
import type { StoreApi } from 'zustand/vanilla';
import type { DeviceId } from '../api/devices';
import type { ConfigEtag, PlaybackVersion } from '../api/etag';
import type { PlaybackStatus } from '../api/playback';
import type { RulerCheckResult } from '../api/measure';
import type { ServerState } from '../session/session';
import type { Timers } from '../session/sync';
import { entries } from '../domain/layout';
import { tabletState } from '../domain/status';
import { projectRoster } from '../domain/roster';
import { reconcile } from './reconcile';
import { arrangementReducer } from './drafts/arrangement';
import type { ArrangementDraft, ArrangementEvent } from './drafts/arrangement';
import { contentReducer, emptyContent } from './drafts/content';
import type { ContentDraft, ContentEvent } from './drafts/content';
import { createForm, formBaseline, formKey, tabletFormReducer } from './drafts/tabletForms';
import type { FormGroup, FormKey, FormValues, TabletForm } from './drafts/tabletForms';
import { gridReducer } from './drafts/grid';
import type { GridDraft, GridEvent } from './drafts/grid';
import { emptyPlaylist, playlistReducer } from './drafts/playlist';
import type { PlaylistDraft, PlaylistEvent } from './drafts/playlist';

export type WallStore = {
  server: ServerState;
  clock: { nowMono: number };
  ui: { selected: DeviceId | null; source: 'images' | 'saved' | 'layouts' | 'tests'; editLayout: boolean;
    drill: DeviceId | null; measureStep: 'model' | 'profile' | 'calibration' | 'ruler' | null; serverOpen: boolean;
    activeImageUnavailableId: string | null; testPattern: 'grid' | 'black' | null };
  arrangement: ArrangementDraft | null; grid: GridDraft | null; content: ContentDraft;
  forms: Partial<Record<FormKey, TabletForm>>;
  rulerReview: { deviceId: DeviceId; version: number; result: RulerCheckResult } | null;
  playlist: PlaylistDraft;
  playback: { status: PlaybackStatus | null; version: PlaybackVersion | null; optedIn: boolean; exclusions: DeviceId[] };
};
export type WallStoreApi = StoreApi<WallStore>;
export function createWallStore(nowMono = performance.now()): WallStoreApi {
  const store = createStore<WallStore>(() => ({
    server: { config: null, etag: null, etagState: 'missing', roster: {}, connectionVersions: {}, rosterError: null,
      rosterUnreachable: false, rosterCheckedAt: null, transportText: 'Connecting to the wall…',
      uncertain: false, supported: false, busy: false, adoption: 0 },
    clock: { nowMono }, ui: { selected: null, source: 'images', editLayout: false, drill: null,
      measureStep: null, serverOpen: false, activeImageUnavailableId: null, testPattern: null },
    arrangement: null, grid: null, content: emptyContent(), forms: {}, rulerReview: null,
    playlist: emptyPlaylist(), playback: { status: null, version: null, optedIn: false, exclusions: [] },
  }));
  store.subscribe((state, previous) => {
    if (state.server.adoption !== previous.server.adoption) store.setState(reconcile(state));
  });
  return store;
}
export function selectDevice(store: WallStoreApi, id: DeviceId | null) {
  store.setState(state => ({ ui: { ...state.ui, selected: id } }));
}
export function observeForm(store: WallStoreApi, id: DeviceId, group: FormGroup, values?: FormValues) {
  const state = store.getState(), config = state.server.config;
  if (!config) return;
  const key = formKey(id, group), baseline = values ?? formBaseline(config, id, group);
  const old = state.forms[key];
  const form = old ? tabletFormReducer(old, { type: 'observe', values: baseline, etag: state.server.etag })
    : createForm(id, group, baseline, state.server.etag);
  store.setState({ forms: { ...state.forms, [key]: form } });
}
export function editForm(store: WallStoreApi, key: FormKey, values: FormValues) {
  const state = store.getState(), form = state.forms[key];
  if (!form) throw new Error('Observe the form before editing.');
  store.setState({ forms: { ...state.forms, [key]: tabletFormReducer(form, { type: 'edit', values, etag: state.server.etag }) } });
}
export type DraftTarget = { kind: 'arrangement' | 'content' | 'grid' } | { kind: 'form'; key: FormKey };
export function keepMine(store: WallStoreApi, target: DraftTarget, review: { version: number; etag: ConfigEtag }): boolean {
  const state = store.getState(), config = state.server.config;
  if (!config || state.server.etagState !== 'current' || state.server.etag !== review.etag) return false;
  switch (target.kind) {
    case 'arrangement':
      if (!state.arrangement || state.arrangement.version !== review.version) return false;
      store.setState({ arrangement: arrangementReducer(state.arrangement, { type: 'keep', layout: config.layout, ...review }) });
      return true;
    case 'form': {
      const form = state.forms[target.key];
      if (!form || form.version !== review.version) return false;
      store.setState({ forms: { ...state.forms, [target.key]: tabletFormReducer(form,
        { type: 'review', values: formBaseline(config, form.id, form.group), ...review }) } });
      return true;
    }
    case 'content':
      if (state.content.savedScene || state.content.version !== review.version) return false;
      store.setState({ content: contentReducer(state.content, { type: 'rebuild', ...review }) });
      return true;
    case 'grid': return false;
  }
}
export function useTheirs(store: WallStoreApi, target: DraftTarget) {
  const state = store.getState(), config = state.server.config;
  if (!config) return;
  switch (target.kind) {
    case 'arrangement':
      if (state.arrangement) store.setState({ arrangement: arrangementReducer(state.arrangement,
        { type: 'discard', layout: config.layout, etag: state.server.etag }) });
      break;
    case 'content': store.setState({ content: contentReducer(state.content, { type: 'discard' }) }); break;
    case 'grid': store.setState({ grid: null }); break;
    case 'form': {
      const form = state.forms[target.key];
      if (form) store.setState({ forms: { ...state.forms, [target.key]: tabletFormReducer(form,
        { type: 'discard', values: formBaseline(config, form.id, form.group), etag: state.server.etag }) } });
    }
  }
}
export function editArrangement(store: WallStoreApi, event: ArrangementEvent) {
  store.setState(state => state.arrangement ? { arrangement: arrangementReducer(state.arrangement, event) } : state);
}
export function editContent(store: WallStoreApi, event: ContentEvent) {
  store.setState(state => ({ content: contentReducer(state.content, event) }));
}
export function editGrid(store: WallStoreApi, event: GridEvent) {
  store.setState(state => state.grid ? { grid: gridReducer(state.grid, event) } : state);
}
export function editPlaylist(store: WallStoreApi, event: PlaylistEvent) {
  store.setState(state => ({ playlist: playlistReducer(state.playlist, event) }));
}
export function statusSignature(state: WallStore, nowMono: number): string {
  const config = state.server.config;
  if (!config) return '';
  const projected = projectRoster(config, state.server.roster);
  return JSON.stringify(Object.keys(entries(config.layout)).sort().map(id => [id, tabletState(projected, id, nowMono)]));
}
export function startClock(store: WallStoreApi, options: { now?: () => number; timers?: Pick<Timers, 'setInterval' | 'clearInterval'> } = {}) {
  const now = options.now ?? (() => performance.now());
  const timers = options.timers ?? globalThis;
  let signature = statusSignature(store.getState(), now());
  const unsubscribe = store.subscribe((state, previous) => {
    if (state.server !== previous.server) {
      const nowMono = now(), next = statusSignature(state, nowMono);
      if (next !== signature) { signature = next; store.setState({ clock: { nowMono } }); }
    }
  });
  const timer = timers.setInterval(() => {
    const nowMono = now(), next = statusSignature(store.getState(), nowMono);
    if (next !== signature) { signature = next; store.setState({ clock: { nowMono } }); }
  }, 1000);
  return () => { timers.clearInterval(timer); unsubscribe(); };
}
