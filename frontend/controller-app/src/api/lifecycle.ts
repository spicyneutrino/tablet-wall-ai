import { z } from 'zod';
import { DeviceIdSchema } from './devices';
import { ConfigEtagSchema } from './etag';
import { PlacementSchema, SlotSchema } from './layouts';
import { SnapshotSummarySchema } from './saved';

export const ForgetCommandSchema = z.strictObject({ remove_active: z.boolean(), saved_layouts: z.literal('keep') });
export const SavedSelectionSchema = z.strictObject({ name: z.string().min(1), etag: z.string().min(1) });
export const RebindCommandSchema = z.strictObject({ replaces: DeviceIdSchema, hardware: z.enum(['same_hardware', 'different_hardware']), active: z.boolean(),
  saved_layouts: z.array(SavedSelectionSchema).refine((items) => new Set(items.map((item) => item.name)).size === items.length, 'Saved layout names must be unique'),
  transfer_label: z.boolean(), number: z.int().positive().nullable().optional() });
export const RebindApplySchema = RebindCommandSchema.extend({ new_connection_id: z.string().min(1).nullable() });
export const ImpactPreviewSchema = z.looseObject({ etag: ConfigEtagSchema, online: z.boolean(), active_entry: z.union([PlacementSchema, SlotSchema]).nullable(),
  saved_layouts: z.array(SnapshotSummarySchema), has_measurement_history: z.boolean() });
export const RebindPreviewSchema = z.looseObject({ base_etag: ConfigEtagSchema, old_id: DeviceIdSchema, new_id: DeviceIdSchema, affected_active: z.boolean(),
  affected_saved: z.array(SnapshotSummarySchema), untouched_saved: z.array(SnapshotSummarySchema), conflicts: z.array(z.looseObject({ code: z.string(), message: z.string() })),
  profile_revision_map: z.record(z.string(), z.int().positive()), calibration_revision_map: z.record(z.string(), z.int().positive()),
  label_after: z.string().nullable(), number_after: z.int().positive().nullable(), old_offline: z.boolean(), new_connection_id: z.string().nullable() });
export type ForgetCommand = z.infer<typeof ForgetCommandSchema>;
export type RebindCommand = z.infer<typeof RebindCommandSchema>;
export type RebindApply = z.infer<typeof RebindApplySchema>;
export type ImpactPreview = z.infer<typeof ImpactPreviewSchema>;
export type RebindPreview = z.infer<typeof RebindPreviewSchema>;
export type SavedSelection = z.infer<typeof SavedSelectionSchema>;
