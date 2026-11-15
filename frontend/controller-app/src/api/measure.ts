import { z } from 'zod';
import { DeviceIdSchema, ViewportSchema } from './devices';
import { ConfigEtagSchema } from './etag';

const bezels = z.looseObject({ left: z.number().nonnegative(), right: z.number().nonnegative(), top: z.number().nonnegative(), bottom: z.number().nonnegative() });
export const ProfileCommandSchema = z.strictObject({ active_width_mm: z.number().positive(), active_height_mm: z.number().positive(), bezels,
  panel_pixels: z.object({ width: z.int().positive(), height: z.int().positive() }).nullable().optional(), label: z.string().min(1).max(80), provenance: z.string().min(1).max(40) });
export const DisplaySchema = z.looseObject({ ...ProfileCommandSchema.shape, panel_pixels: z.object({ width: z.number().positive(), height: z.number().positive() }).nullable(),
  device_id: DeviceIdSchema, revision: z.int().positive(), created_at: z.string() });
export const CalibrationCommandSchema = z.strictObject({ profile_revision: z.int().positive(), viewport_width: z.number().positive(), viewport_height: z.number().positive(),
  dpr: z.number().positive(), orientation: ViewportSchema.shape.orientation, mode: ViewportSchema.shape.mode, quarter_turn: z.int().min(0).max(3),
  panel_offset_mm: z.tuple([z.number(), z.number()]), mm_per_css: z.tuple([z.number().positive(), z.number().positive()]),
  anchor_edge: z.enum(['top-left', 'top-right', 'bottom-left', 'bottom-right']), uncertainty_mm: z.number().nonnegative(), method: z.string().min(1).max(80), viewport_guard: z.boolean().optional() });
export const CalibrationSchema = z.looseObject({ ...CalibrationCommandSchema.omit({ viewport_guard: true }).shape,
  device_id: DeviceIdSchema, revision: z.int().positive(), created_at: z.string() });
export const DisplayResponseSchema = z.looseObject({ display: DisplaySchema, etag: ConfigEtagSchema });
export const CalibrationResponseSchema = z.looseObject({ calibration: CalibrationSchema, etag: ConfigEtagSchema });
export const RulerCheckSchema = z.strictObject({ device_id: DeviceIdSchema, profile_revision: z.int().positive(), quarter_turn: z.int().min(0).max(3), axis: z.enum(['x', 'y']),
  span_px: z.number().positive(), span_mm: z.number().positive(), span_error_mm: z.number().nonnegative(), usable_width_px: z.number().positive(), usable_height_px: z.number().positive() });
const warning = z.looseObject({ code: z.string(), severity: z.string(), message: z.string(), action: z.string().optional() });
export const RulerCheckResultSchema = z.looseObject({ schema: z.literal(1), axis: z.enum(['x', 'y']), status: z.enum(['agree', 'disagreement', 'uncompared']),
  derived: z.looseObject({ mm_per_css: z.number().positive(), mm_per_css_uncertainty: z.number().nonnegative(), relative_error: z.number().nonnegative(),
    span_quality: z.string(), quality_label: z.string(), short_span: z.boolean(), extrapolation_factor: z.number(), span_count: z.number() }),
  inputs: z.looseObject({ span_px: z.number(), span_mm: z.number(), span_error_mm: z.number(), usable_width_px: z.number(), usable_height_px: z.number() }),
  comparison: z.looseObject({ supplied_mm: z.number().nullable(), implied_mm: z.number().nullable(), tolerance_mm: z.number().nullable() }),
  implied_dimensions_mm: z.looseObject({ width: z.number(), height: z.number(), measured: z.number(), assumes_uniform_scale: z.literal(true) }),
  extrapolated_uncertainty: z.looseObject({ width_mm: z.number(), height_mm: z.number(), measured_mm: z.number(), mm_per_css: z.number(), relative: z.number(), formula: z.string() }),
  decision: z.looseObject({ required: z.boolean(), code: z.string().nullable(), message: z.string(), choices: z.array(z.looseObject({ id: z.enum(['keep_supplied', 'use_ruler', 'remeasure']), label: z.string(), consequence: z.string() })), changes_nothing: z.literal(true), saved: z.literal(false) }),
  warnings: z.array(warning), actionable_warning: warning.nullable(), assumptions: z.array(z.string()), accuracy_claimed: z.literal(false), note: z.string(),
  profile: z.looseObject({ device_id: DeviceIdSchema, revision: z.int().positive(), active_width_mm: z.number().positive(), active_height_mm: z.number().positive(), quarter_turn: z.int().min(0).max(3), native_axis: z.enum(['width', 'height']) }) });
export type Display = z.infer<typeof DisplaySchema>;
export type Calibration = z.infer<typeof CalibrationSchema>;
export type ProfileCommand = z.infer<typeof ProfileCommandSchema>;
export type CalibrationCommand = z.infer<typeof CalibrationCommandSchema>;
export type RulerCheck = z.infer<typeof RulerCheckSchema>;
export type RulerCheckResult = z.infer<typeof RulerCheckResultSchema>;
export type DisplayResponse = z.infer<typeof DisplayResponseSchema>;
export type CalibrationResponse = z.infer<typeof CalibrationResponseSchema>;
