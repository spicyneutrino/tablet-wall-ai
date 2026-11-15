import { z } from 'zod';

export const ConfigEtagSchema = z.string().min(1).brand<'ConfigEtag'>();
export const PlaylistEtagSchema = z.string().min(1).brand<'PlaylistEtag'>();
export const PlaybackVersionSchema = z.int().positive().transform(String).brand<'PlaybackVersion'>();
export type ConfigEtag = z.infer<typeof ConfigEtagSchema>;
export type PlaylistEtag = z.infer<typeof PlaylistEtagSchema>;
export type PlaybackVersion = z.infer<typeof PlaybackVersionSchema>;
