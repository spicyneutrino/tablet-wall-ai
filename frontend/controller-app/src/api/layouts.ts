import { z } from 'zod';
import { DeviceIdSchema } from './devices';

export const BezelSchema = z.looseObject({ top: z.int().nonnegative(), right: z.int().nonnegative(), bottom: z.int().nonnegative(), left: z.int().nonnegative() });
export const PlacementSchema = z.looseObject({ device_id: DeviceIdSchema.optional(), x: z.int(), y: z.int(), w: z.int().positive(), h: z.int().positive(), bezel: BezelSchema })
  .refine((p) => p.w > p.bezel.left + p.bezel.right && p.h > p.bezel.top + p.bezel.bottom, 'Bezel must leave a visible rectangle');
export const SlotSchema = z.looseObject({ center_x_mm: z.number(), center_y_mm: z.number(), mount_angle: z.number(),
  nudge_x_mm: z.number(), nudge_y_mm: z.number(), profile_revision: z.int().positive(), calibration_revision: z.int().positive(), participating: z.boolean().optional() });
export const RectSchema = z.looseObject({ x: z.number(), y: z.number(), width: z.number().positive(), height: z.number().positive() });
export const SizingSchema = z.looseObject({ mode: z.enum(['fixed', 'tablets']), padding: z.number().nonnegative() });
export const LogicalLayoutSchema = z.looseObject({ kind: z.literal('logical'), width: z.int().positive(), height: z.int().positive(),
  placements: z.record(DeviceIdSchema, PlacementSchema), sizing: SizingSchema.refine((s) => Number.isInteger(s.padding), 'Logical padding must be whole units') });
export const PhysicalLayoutSchema = z.looseObject({ kind: z.literal('physical'), bounds: RectSchema, slots: z.record(DeviceIdSchema, SlotSchema), sizing: SizingSchema });
export const LayoutSchema = z.discriminatedUnion('kind', [LogicalLayoutSchema, PhysicalLayoutSchema]);
// Saved logical layouts predate the kind and sizing projections in GET config.
export const StoredLayoutSchema = z.union([LayoutSchema, LogicalLayoutSchema.omit({ kind: true, sizing: true }).extend({ kind: z.literal('logical').optional(), sizing: SizingSchema.optional() }),
  PhysicalLayoutSchema.extend({ sizing: SizingSchema.optional() })]);
export const LogicalLayoutCommandSchema = z.strictObject({ width: z.int().positive(), height: z.int().positive(),
  placements: z.record(DeviceIdSchema, PlacementSchema), sizing: SizingSchema.optional() });
export const PhysicalLayoutCommandSchema = z.strictObject({ bounds: RectSchema, slots: z.record(DeviceIdSchema, SlotSchema), sizing: SizingSchema.optional() });
export const ClearLayoutCommandSchema = z.strictObject({ confirm: z.literal(true) });
export type Bezel = z.infer<typeof BezelSchema>;
export type Placement = z.infer<typeof PlacementSchema>;
export type Slot = z.infer<typeof SlotSchema>;
export type Rect = z.infer<typeof RectSchema>;
export type Sizing = z.infer<typeof SizingSchema>;
export type LogicalLayout = z.infer<typeof LogicalLayoutSchema>;
export type PhysicalLayout = z.infer<typeof PhysicalLayoutSchema>;
export type Layout = z.infer<typeof LayoutSchema>;
export type StoredLayout = z.infer<typeof StoredLayoutSchema>;
export type LogicalLayoutCommand = z.infer<typeof LogicalLayoutCommandSchema>;
export type PhysicalLayoutCommand = z.infer<typeof PhysicalLayoutCommandSchema>;
export type ClearLayoutCommand = z.infer<typeof ClearLayoutCommandSchema>;
