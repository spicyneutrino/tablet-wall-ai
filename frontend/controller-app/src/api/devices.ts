import { z } from 'zod';
import { AssetIdSchema, HexColorSchema } from './scene';

export const DeviceIdSchema = z.uuidv4().brand<'DeviceId'>();
export const ViewportSchema = z.looseObject({ width: z.number().positive(), height: z.number().positive(), dpr: z.number().positive(),
  orientation: z.union([z.literal(0), z.literal(90), z.literal(180), z.literal(270)]),
  mode: z.enum(['tab', 'fullscreen', 'standalone']), visual_scale: z.number().positive() });
export const CalibrationHealthSchema = z.looseObject({ schema: z.literal(1), device_id: DeviceIdSchema.nullable(),
  status: z.enum(['ready', 'needs_calibration', 'viewport_mismatch', 'zoom_changed']), status_reason: z.string(), status_label: z.string(), ok: z.boolean(),
  provenance: z.looseObject({ kind: z.enum(['manual', 'model', 'unknown']), description: z.string(), approximate: z.boolean(), confirmed: z.boolean() }),
  approximate: z.boolean(), confirmed: z.boolean(), accuracy_claimed: z.literal(false), uncertainty_mm: z.number().nonnegative().nullable(),
  viewport: z.looseObject({ insets: z.looseObject({ source: z.string() }).nullable() }),
  comparison: z.looseObject({ discrepancy: z.boolean().nullable(), lit_dimensions_mm: z.tuple([z.number(), z.number()]).nullable(),
    predicted_mm: z.tuple([z.number(), z.number()]).nullable(), message: z.string() }),
  actionable_warning: z.looseObject({ code: z.string(), message: z.string(), action: z.string() }).nullable() });
export const MappingSchema = z.looseObject({ revision: z.string(), state: z.enum(['ready', 'unplaced', 'unsupported_client',
  'unsupported_content', 'zoom_changed', 'needs_calibration', 'viewport_mismatch']), reason: z.string().nullable(),
  viewport: ViewportSchema.nullable(), profile_revision: z.int().positive().nullable().optional(), calibration_revision: z.int().positive().nullable().optional(),
  health: CalibrationHealthSchema.nullable().optional() });
export const RenderTokenSchema = z.looseObject({ connection_id: z.string(), generation: z.string(), revision: z.int().nonnegative(),
  render_seq: z.int().nonnegative(), mapping_revision: z.string(), asset: AssetIdSchema.nullable() });
export const RenderEvidenceSchema = z.looseObject({ state: z.enum(['displayed', 'loading', 'failed', 'hidden', 'stale', 'unknown',
  'offline', 'unplaced', 'unsupported', 'blocked', 'identifying']),
  current: z.boolean(), expected_token: RenderTokenSchema.nullable(), accepted_token: RenderTokenSchema.nullable(),
  accepted_status: z.string().nullable(), received_at: z.number().nullable(), age_ms: z.number().nonnegative().nullable(), reason: z.string().nullable() });
export const IdentifyStateSchema = z.looseObject({ command_id: z.string(), state: z.string(), duration_ms: z.int().positive(),
  remaining_ms: z.number().nonnegative(), active: z.boolean() });
export const DeviceStatusSchema = z.looseObject({ online: z.boolean(), protocol: z.int().positive().nullable(), caps: z.array(z.string()),
  number: z.int().positive().nullish(), label: z.string().nullish(), last_seen: z.string().nullish(), viewport: ViewportSchema.nullish(),
  mapping: MappingSchema.optional(), render: RenderEvidenceSchema.optional(), identify: IdentifyStateSchema.nullish(),
  connection_id: z.string().optional(), model_suggestions: z.array(z.string()).optional(),
  wake_lock: z.enum(['held', 'released', 'unsupported', 'insecure', 'denied']).nullish() });
export const DeviceSchema = DeviceStatusSchema.extend({ device_id: DeviceIdSchema, width: z.int().positive(), height: z.int().positive(),
  type: z.string(), color: HexColorSchema.nullable(), screen_width: z.int().positive().nullish(), screen_height: z.int().positive().nullish(),
  screen_dpr: z.number().positive().nullish(), platform_family: z.enum(['ios', 'android', 'other']).nullish(), render_seq: z.int().nonnegative().optional() });
export const DevicesSchema = z.record(DeviceIdSchema, DeviceSchema);
export const LabelCommandSchema = z.strictObject({ label: z.string().refine((value) => !/[\p{Cc}\p{Cf}\p{Cs}]/u.test(value), 'Control characters are forbidden')
  .transform((value) => value.trim() || null).refine((value) => value === null || [...value].length <= 80, 'Label is too long').nullable() });
export const TabletAssignmentCommandSchema = z.discriminatedUnion('mode', [
  z.strictObject({ mode: z.literal('auto'), model_id: z.string().nullable().optional() }),
  z.strictObject({ mode: z.literal('manual'), model_id: z.string().nullable().optional() }),
  z.strictObject({ mode: z.literal('explicit'), model_id: z.string().min(1) }),
]);
export const IdentifyCommandSchema = z.strictObject({ duration_ms: z.int().min(1000).max(10000).optional() });
export const ColorCommandSchema = z.strictObject({ color: z.string().regex(/^#?[0-9a-fA-F]{6}$/) });
export const ColorDeliverySchema = z.union([
  z.looseObject({ color: HexColorSchema, updated: z.int().nonnegative(), delivered: z.int().nonnegative() }),
  z.looseObject({ device_id: DeviceIdSchema, color: HexColorSchema, delivered: z.boolean() }),
]);
export type DeviceId = z.infer<typeof DeviceIdSchema>;
export type Viewport = z.infer<typeof ViewportSchema>;
export type Mapping = z.infer<typeof MappingSchema>;
export type RenderEvidence = z.infer<typeof RenderEvidenceSchema>;
export type IdentifyState = z.infer<typeof IdentifyStateSchema>;
export type DeviceStatus = z.infer<typeof DeviceStatusSchema>;
export type Device = z.infer<typeof DeviceSchema>;
export type LabelCommand = z.infer<typeof LabelCommandSchema>;
export type TabletAssignmentCommand = z.infer<typeof TabletAssignmentCommandSchema>;
export type RenderToken = z.infer<typeof RenderTokenSchema>;
export type Devices = z.infer<typeof DevicesSchema>;
export type IdentifyCommand = z.infer<typeof IdentifyCommandSchema>;
export type ColorCommand = z.infer<typeof ColorCommandSchema>;
export type ColorDelivery = z.infer<typeof ColorDeliverySchema>;
export type CalibrationHealth = z.infer<typeof CalibrationHealthSchema>;
