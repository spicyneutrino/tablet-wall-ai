import { z } from 'zod';
import { StoredLayoutSchema } from './layouts';
import { SceneSchema } from './scene';

export const SnapshotSummarySchema = z.looseObject({ name: z.string(), etag: z.string().min(1), kind: z.string().nullable(), valid: z.boolean() });
export const SnapshotsSchema = z.looseObject({ layouts: z.array(SnapshotSummarySchema), scenes: z.array(SnapshotSummarySchema) });
export const SavedLayoutSchema = z.union([
  SnapshotSummarySchema.extend({ valid: z.literal(true), layout: StoredLayoutSchema }),
  SnapshotSummarySchema.extend({ valid: z.literal(false), layout: z.unknown() }),
]);
export const SavedSceneSchema = z.union([
  SnapshotSummarySchema.extend({ valid: z.literal(true), content: SceneSchema }),
  SnapshotSummarySchema.extend({ valid: z.literal(false), content: z.unknown() }),
]);
export const SavedLayoutsSchema = z.looseObject({ layouts: z.array(SavedLayoutSchema) });
export const SavedScenesSchema = z.looseObject({ scenes: z.array(SavedSceneSchema) });
export type SnapshotSummary = z.infer<typeof SnapshotSummarySchema>;
export type SavedLayout = z.infer<typeof SavedLayoutSchema>;
export type SavedScene = z.infer<typeof SavedSceneSchema>;
export type Snapshots = z.infer<typeof SnapshotsSchema>;
export type SavedLayouts = z.infer<typeof SavedLayoutsSchema>;
export type SavedScenes = z.infer<typeof SavedScenesSchema>;
