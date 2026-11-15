import { z } from 'zod';

export const AssetIdSchema = z.string().regex(/^sha256:[0-9a-f]{64}$/).brand<'AssetId'>();
export const HexColorSchema = z.string().regex(/^#[0-9a-fA-F]{6}$/).brand<'HexColor'>();
const image = { type: z.literal('image'), asset: AssetIdSchema, fit: z.enum(['cover', 'contain']), background: HexColorSchema.optional() };
export const SceneInputSchema = z.discriminatedUnion('type', [
  z.strictObject({ type: z.literal('color') }),
  z.strictObject({ type: z.literal('calibration') }),
  z.strictObject(image),
]);
export const SceneSchema = z.discriminatedUnion('type', [
  z.looseObject({ type: z.literal('color') }),
  z.looseObject({ type: z.literal('calibration') }),
  z.looseObject({ ...image, url: z.string().optional(), intrinsicWidth: z.int().positive().optional(),
    intrinsicHeight: z.int().positive().optional(), available: z.boolean().optional(), name: z.string().optional() }),
]);
export const SceneUpdateSchema = z.strictObject({ content: SceneInputSchema });
export type AssetId = z.infer<typeof AssetIdSchema>;
export type HexColor = z.infer<typeof HexColorSchema>;
export type SceneInput = z.infer<typeof SceneInputSchema>;
export type Scene = z.infer<typeof SceneSchema>;
export type SceneUpdate = z.infer<typeof SceneUpdateSchema>;
