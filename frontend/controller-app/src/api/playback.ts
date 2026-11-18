import { z } from 'zod';
import { DeviceIdSchema } from './devices';
import { PlaylistEtagSchema, PlaybackVersionSchema } from './etag';
import { AssetIdSchema } from './scene';

export const PlaylistItemSchema = z.looseObject({ asset: AssetIdSchema, dwell_ms: z.int().min(1000).max(600000) });
export const PlaylistSchema = z.looseObject({ items: z.array(PlaylistItemSchema).min(1).max(64), loop: z.boolean(), revision: z.int().positive().optional() });
export const PlaylistResponseSchema = z.looseObject({ playlist: PlaylistSchema.nullable(), etag: PlaylistEtagSchema });
export const PlaylistCommandSchema = z.strictObject({ items: z.array(PlaylistItemSchema).min(1).max(64), loop: z.boolean() });
export const OccurrenceSchema = z.looseObject({ playlist_revision: z.int().positive(), item_index: z.int().nonnegative(), loop: z.int().nonnegative() });
export const PlaybackItemSchema = z.looseObject({ occurrence: OccurrenceSchema, asset: AssetIdSchema, kind: z.enum(['still', 'video']),
  duration_ms: z.int().positive().nullable(), dwell_ms: z.int().positive() });
export const PreparationSchema = z.looseObject({ preparation_id: z.string(), version: PlaybackVersionSchema, occurrence: OccurrenceSchema, asset: AssetIdSchema,
  prepare_deadline_ms: z.number(), effective_server_ms: z.number(), recovery_id: z.string().optional(), start_media_ms: z.int().nonnegative().optional() });
export const RecoverySchema = z.looseObject({ id: z.string(), occurrence: OccurrenceSchema, position_ms: z.number().nonnegative(), reason: z.string(),
  device_id: DeviceIdSchema.nullable(), attempts: z.int().nonnegative(), started_ms: z.number(), deadline_ms: z.number(), degraded_ms: z.number().nonnegative(),
  state: z.enum(['preparing', 'armed', 'playing', 'blocked', 'failed']), missing: z.array(DeviceIdSchema) });
export const ActivePlaybackStatusSchema = z.looseObject({ state: z.enum(['preparing', 'armed', 'playing', 'paused', 'stopped', 'blocked', 'failed', 'final', 'recovering']),
  now_ms: z.number(), session_id: z.string(), version: PlaybackVersionSchema, generation: z.string(), clock_epoch: z.string(),
  current: OccurrenceSchema.nullable(), displayed: OccurrenceSchema.nullable(), current_effective_ms: z.number().nullable(), pending: PreparationSchema.nullable(),
  playlist_revision: z.int().positive(), live: z.looseObject({ current: PlaybackItemSchema.nullable(), displayed: PlaybackItemSchema.nullable(), pending: PlaybackItemSchema.nullable() }),
  cohort: z.array(DeviceIdSchema), required: z.array(DeviceIdSchema), excluded: z.array(DeviceIdSchema), missed: z.array(DeviceIdSchema), held: z.boolean(),
  hold_deadline_ms: z.number().nullable(), policy: z.enum(['online', 'strict']), blocked_reason: z.string().nullable(), final: z.boolean(), paused_at_ms: z.number().nullable(),
  recovery: RecoverySchema.nullable(), video: z.record(DeviceIdSchema, z.looseObject({ drift_ms: z.number(), rate: z.number(), source: z.enum(['rvfc', 'time']), media_ms: z.number(), age_ms: z.number().nonnegative() })),
  members: z.record(DeviceIdSchema, z.looseObject({ ready: z.boolean(), video: z.record(z.string(), z.unknown()).nullable() })) });
export const PlaybackStatusSchema = z.union([ActivePlaybackStatusSchema, z.strictObject({ state: z.literal('stopped') })]);
export const PlaybackStartCommandSchema = z.strictObject({ policy: z.enum(['online', 'strict']).optional(), exclusions: z.array(DeviceIdSchema).optional() });
export type Playlist = z.infer<typeof PlaylistSchema>;
export type PlaylistItem = z.infer<typeof PlaylistItemSchema>;
export type PlaylistResponse = z.infer<typeof PlaylistResponseSchema>;
export type PlaybackStatus = z.infer<typeof PlaybackStatusSchema>;
export type Occurrence = z.infer<typeof OccurrenceSchema>;
export type PlaylistCommand = z.infer<typeof PlaylistCommandSchema>;
export type PlaybackItem = z.infer<typeof PlaybackItemSchema>;
export type Preparation = z.infer<typeof PreparationSchema>;
export type Recovery = z.infer<typeof RecoverySchema>;
export type ActivePlaybackStatus = z.infer<typeof ActivePlaybackStatusSchema>;
export type PlaybackStartCommand = z.infer<typeof PlaybackStartCommandSchema>;
