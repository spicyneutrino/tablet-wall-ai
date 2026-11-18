import { MediaSchema } from '../../api/images';
import type { Media } from '../../api/images';
import type { DeviceId } from '../../api/devices';
import type { PlaybackVersion } from '../../api/etag';
import { paths } from '../../api/paths';
import { PlaybackStatusSchema, PlaylistCommandSchema, PlaylistResponseSchema } from '../../api/playback';
import type { PlaybackStatus, PlaylistResponse } from '../../api/playback';
import type { CommandOutcome } from '../../session/outcome';
import type { Session } from '../../session/session';
import { editPlaylist } from '../store';
import type { WallStoreApi } from '../store';
import { run } from './run';

export type Transport = 'pause' | 'resume' | 'stop' | 'retry' | 'next' | 'previous';
export type StartOptions = { policy: 'online' | 'strict' | null; exclusions: DeviceId[] };

export const versionOf = (status: PlaybackStatus | null): PlaybackVersion | null =>
  status && 'version' in status ? status.version : null;

/*
 * A response from a command and a slower poll can arrive out of order. Every
 * applied status bumps the epoch, and a poll that began before the bump is dropped.
 */
const epochs = new WeakMap<WallStoreApi, number>();
const epochOf = (store: WallStoreApi) => epochs.get(store) ?? 0;

export function applyStatus(store: WallStoreApi, status: PlaybackStatus) {
  epochs.set(store, epochOf(store) + 1);
  store.setState(state => ({ playback: { ...state.playback, status, version: versionOf(status) } }));
}

export async function pollPlayback(store: WallStoreApi, session: Session): Promise<CommandOutcome<PlaybackStatus>> {
  const epoch = epochOf(store);
  const outcome = await session.request('GET', paths.playback, undefined, { parse: PlaybackStatusSchema });
  if (outcome.kind === 'ok' && epochOf(store) === epoch) {
    store.setState(state => ({ playback: { ...state.playback, status: outcome.value, version: versionOf(outcome.value) } }));
  }
  return outcome;
}

export const loadMedia = (session: Session): Promise<CommandOutcome<Media>> =>
  session.request('GET', paths.media, undefined, { parse: MediaSchema });

/** `observe` keeps unsaved edits, `discard` takes the server's playlist, `keep` rebases the edits onto its etag. */
export async function loadPlaylist(store: WallStoreApi, session: Session,
  mode: 'observe' | 'discard' | 'keep' = 'observe'): Promise<CommandOutcome<PlaylistResponse>> {
  const outcome = await session.request('GET', paths.playlist, undefined, { parse: PlaylistResponseSchema });
  if (outcome.kind !== 'ok') return outcome;
  const { playlist, etag } = outcome.value;
  editPlaylist(store, mode === 'keep' ? { type: 'keep', etag } : { type: mode, value: playlist, etag });
  return outcome;
}

export async function savePlaylist(store: WallStoreApi, session: Session): Promise<CommandOutcome<PlaylistResponse>> {
  const { draft } = store.getState().playlist;
  if (!draft?.items.length) return { kind: 'rejected', status: 422, message: 'Add at least one image before saving.' };
  const command = PlaylistCommandSchema.parse({ loop: draft.loop,
    items: draft.items.map(({ asset, dwell_ms }) => ({ asset, dwell_ms })) });
  return run(store, { kind: 'playlist' }, guard => guard
    ? session.request('PUT', paths.playlist, command, { ifMatch: guard, parse: PlaylistResponseSchema })
    : Promise.resolve({ kind: 'refused-locally', reason: 'stale-etag' } as const), receipt => receipt);
}

export async function startPlayback(store: WallStoreApi, session: Session, options: StartOptions): Promise<CommandOutcome<PlaybackStatus>> {
  const outcome = await session.request('POST', paths.playbackCommand('start'),
    { exclusions: options.exclusions, ...(options.policy ? { policy: options.policy } : {}) }, { parse: PlaybackStatusSchema });
  if (outcome.kind === 'ok') applyStatus(store, outcome.value);
  return outcome;
}

/*
 * The version moves as tablets acknowledge items, so read it immediately before
 * the write. A 412 means a cut landed in that window: read again and retry once.
 * Resume is a Start of the paused session; the server ignores If-Match there.
 */
export async function sendTransport(store: WallStoreApi, session: Session, action: Transport): Promise<CommandOutcome<PlaybackStatus>> {
  for (let attempt = 0; ; attempt += 1) {
    const read = await session.request('GET', paths.playback, undefined, { parse: PlaybackStatusSchema });
    if (read.kind !== 'ok') return read;
    const version = versionOf(read.value);
    if (!version) return { kind: 'rejected', status: 409, message: 'Playback is not running. Start it first.' };
    const outcome = await session.request('POST', paths.playbackCommand(action === 'resume' ? 'start' : action),
      undefined, { ifMatch: version, parse: PlaybackStatusSchema });
    if (outcome.kind === 'conflict' && attempt === 0) continue;
    if (outcome.kind === 'ok') applyStatus(store, outcome.value);
    return outcome;
  }
}

const REJECTIONS: [RegExp, string][] = [
  [/no eligible physical endpoints/i, 'No wall tablets are online. Open the tablet address on a tablet on the same network, then start again.'],
  [/save a playlist/i, 'Save a playlist before starting playback.'],
  [/physical layout is required/i, 'Apply a physical layout before starting playback.'],
  [/all participating slots are excluded/i, 'Every participating tablet is excluded. Include at least one tablet, then start again.'],
];

export function playbackOutcomeMessage(outcome: CommandOutcome<unknown>): string {
  switch (outcome.kind) {
    case 'ok': return '';
    case 'conflict': return 'Playback changed again while this was sent. Try once more.';
    case 'precondition-missing': return 'Refresh status, then try again.';
    case 'rejected': return REJECTIONS.find(([pattern]) => pattern.test(outcome.message))?.[1] ?? outcome.message;
    case 'uncertain': return `Not confirmed. ${outcome.message}`;
    case 'refused-locally':
      return outcome.reason === 'busy' ? 'Another change is already being sent. Wait for it to finish.'
        : outcome.reason === 'uncertain' ? 'The last change was not confirmed. Refresh status first.'
          : outcome.reason === 'unsupported' ? 'Update the console before changing playback.'
            : 'The wall may have changed. Refresh status first.';
  }
}

/** A stale playlist etag is shown by the editor's conflict note, not as a message. */
export function playlistOutcomeMessage(outcome: CommandOutcome<unknown>): string {
  return outcome.kind === 'conflict' ? '' : playbackOutcomeMessage(outcome);
}
