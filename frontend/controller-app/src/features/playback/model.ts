import { DeviceIdSchema } from '../../api/devices';
import type { DeviceId } from '../../api/devices';
import type { ManagedAsset } from '../../api/images';
import type { PlaybackStatus, PlaylistItem } from '../../api/playback';
import type { Layout } from '../../api/layouts';

export const MAX_ITEMS = 64;
export const DEFAULT_DWELL_MS = 5000;

export type Parsed = { ok: true; ms: number } | { ok: false; error: string };

export function parseSeconds(text: string): Parsed {
  const value = text.trim();
  if (!value) return { ok: false, error: 'Enter how many seconds this image stays up.' };
  if (!/^\d+(\.\d{1,3})?$/.test(value)) return { ok: false, error: 'Use a number of seconds, such as 5 or 2.5.' };
  const ms = Math.round(Number(value) * 1000);
  return ms >= 1000 && ms <= 600000 ? { ok: true, ms } : { ok: false, error: 'Use 1 to 600 seconds.' };
}

export const secondsText = (ms: number) => String(ms / 1000);

export function playlistSummary(items: readonly PlaylistItem[], loop: boolean) {
  const seconds = items.reduce((sum, item) => sum + item.dwell_ms, 0) / 1000;
  return `${items.length} ${items.length === 1 ? 'item' : 'items'}, ${Math.round(seconds * 10) / 10} s${loop ? ' loop' : ''}`;
}

export function moved<T>(list: readonly T[], from: number, to: number): T[] {
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item as T);
  return next;
}

export const isVideo = (asset: ManagedAsset | undefined) =>
  asset?.kind === 'video' || (typeof asset?.mime === 'string' && asset.mime.startsWith('video/'));

export function participants(layout: Layout | null | undefined): DeviceId[] {
  return layout?.kind === 'physical'
    ? Object.entries(layout.slots).filter(([, slot]) => slot.participating !== false).map(([id]) => DeviceIdSchema.parse(id)) : [];
}

export function startReason(input: { layout: Layout | null | undefined; saved: boolean; supported: boolean; uncertain: boolean }): string | null {
  if (!input.supported) return 'Update the console before starting playback.';
  if (input.uncertain) return 'The last change was not confirmed. Refresh status first.';
  if (input.layout?.kind !== 'physical') return 'Apply a physical layout first. Playback needs measured tablets.';
  if (!participants(input.layout).length) return 'Add a tablet to the wall first.';
  if (!input.saved) return 'Save the playlist first.';
  return null;
}

const STATES: Record<string, { label: string; tone: 'ok' | 'warn' | 'err' | 'muted' }> = {
  playing: { label: 'Playing', tone: 'ok' }, paused: { label: 'Paused', tone: 'muted' }, stopped: { label: 'Stopped', tone: 'muted' },
  preparing: { label: 'Preparing', tone: 'warn' }, armed: { label: 'Getting ready for the next cut', tone: 'warn' },
  recovering: { label: 'Recovering', tone: 'warn' }, blocked: { label: 'Blocked', tone: 'err' }, failed: { label: 'Failed', tone: 'err' },
  final: { label: 'Showing the last item', tone: 'ok' },
};

export const isActive = (status: PlaybackStatus | null): status is Extract<PlaybackStatus, { version: unknown }> =>
  !!status && 'version' in status && status.state !== 'stopped';

export const stateView = (status: PlaybackStatus | null) => STATES[status?.state ?? 'stopped'] ?? STATES.stopped!;

export function position(status: PlaybackStatus | null): { index: number; loop: number } | null {
  if (!isActive(status)) return null;
  const occurrence = status.displayed ?? status.current ?? status.pending?.occurrence;
  return occurrence ? { index: occurrence.item_index, loop: occurrence.loop } : null;
}
