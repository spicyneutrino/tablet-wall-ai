import { z } from 'zod';
import { DeviceIdSchema, DeviceStatusSchema } from './devices';
import { ConfigEtagSchema } from './etag';
import { LayoutSchema } from './layouts';
import { DisplaySchema, CalibrationSchema } from './measure';
import { SnapshotsSchema } from './saved';
import { SceneSchema } from './scene';

export { BezelSchema, PlacementSchema, SlotSchema, RectSchema, SizingSchema, LogicalLayoutSchema, PhysicalLayoutSchema, LayoutSchema } from './layouts';
export type { Bezel, Placement, Slot, Rect, Sizing, LogicalLayout, PhysicalLayout, Layout } from './layouts';
export const TabletModelSchema = z.looseObject({ label: z.string(), active_width_mm: z.number().positive(), active_height_mm: z.number().positive(),
  bezels: DisplaySchema.shape.bezels, screen_width: z.int().positive(), screen_height: z.int().positive(), portrait_angle: z.int(), dpr: z.number().positive(),
  platform: z.enum(['ios', 'android', 'other']), mm_per_css: z.tuple([z.number().positive(), z.number().positive()]), uncertainty_mm: z.number().nonnegative() });
export const TabletAssignmentSchema = z.union([
  z.looseObject({ mode: z.enum(['auto', 'manual']), model_id: z.null() }),
  z.looseObject({ mode: z.enum(['auto', 'explicit']), model_id: z.string(), model: TabletModelSchema, profile_revision: z.int().positive(), calibration_revision: z.int().positive() }),
]);
export const TabletAssignmentResponseSchema = z.looseObject({ assignment: TabletAssignmentSchema, suggestions: z.array(z.string()), etag: ConfigEtagSchema });
export const CapabilitiesSchema = z.looseObject({ layout_kinds: z.array(z.enum(['logical', 'physical'])), fits: z.array(z.enum(['cover', 'contain'])),
  render_ack: z.boolean(), identify: z.boolean(), image_contain: z.boolean(), grid: z.boolean(), test_patterns: z.array(z.enum(['grid', 'black'])),
  uploads: z.boolean(), diagnostics: z.boolean(), login_supported: z.boolean() });
export const ConfigSchema = z.looseObject({ schema: z.literal(2), operator_state_version: z.literal(1), revision: z.int().nonnegative(),
  generation: z.string().min(1), etag: ConfigEtagSchema, layout: LayoutSchema, scene: z.looseObject({ content: SceneSchema }),
  previous_layout_saved: z.string().nullable().optional(),
  displays: z.array(DisplaySchema), calibrations: z.array(CalibrationSchema), referenced_displays: z.array(DisplaySchema), referenced_calibrations: z.array(CalibrationSchema),
  tablet_models: z.record(z.string(), TabletModelSchema), tablet_assignments: z.record(DeviceIdSchema, TabletAssignmentSchema),
  device_labels: z.record(DeviceIdSchema, z.string().nullable()), snapshots: SnapshotsSchema, capabilities: CapabilitiesSchema,
  runtime: z.looseObject({ devices: z.record(DeviceIdSchema, DeviceStatusSchema), observed_at: z.string().nullable(),
    presentation: z.looseObject({ owner: z.enum(['static', 'playback']), state: z.string() }) }) });
export type TabletModel = z.infer<typeof TabletModelSchema>;
export type TabletAssignment = z.infer<typeof TabletAssignmentSchema>;
export type Capabilities = z.infer<typeof CapabilitiesSchema>;
export type Config = z.infer<typeof ConfigSchema>;
export type TabletAssignmentResponse = z.infer<typeof TabletAssignmentResponseSchema>;
