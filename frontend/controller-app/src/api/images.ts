import { z } from 'zod';
import { AssetIdSchema } from './scene';
import { ConfigEtagSchema } from './etag';

export const ImageSchema = z.looseObject({ id: AssetIdSchema, name: z.string(), width: z.int().positive(), height: z.int().positive(),
  url: z.string(), thumbnail_url: z.string(), source: z.enum(['curated', 'managed']) });
export const ImagesSchema = z.looseObject({ images: z.array(ImageSchema) });
export const TestPatternCommandSchema = z.strictObject({ pattern: z.enum(['grid', 'black']) });
export const TestPatternSchema = ImageSchema.extend({ etag: ConfigEtagSchema, metadata: z.record(z.string(), z.unknown()) });
export const ManagedAssetSchema = z.looseObject({ id: AssetIdSchema, name: z.string(), kind: z.enum(['image', 'video']).optional(),
  url: z.string(), intrinsicWidth: z.int().positive(), intrinsicHeight: z.int().positive(),
  thumbnail: z.looseObject({ url: z.string() }).nullable() });
export const UploadResponseSchema = z.looseObject({ state: z.literal('ready'), asset: ManagedAssetSchema });
export const MediaSchema = z.looseObject({ assets: z.array(ManagedAssetSchema), pipeline_version: z.int().positive() });
export type Image = z.infer<typeof ImageSchema>;
export type ManagedAsset = z.infer<typeof ManagedAssetSchema>;
export type UploadResponse = z.infer<typeof UploadResponseSchema>;
export type Images = z.infer<typeof ImagesSchema>;
export type TestPatternCommand = z.infer<typeof TestPatternCommandSchema>;
export type TestPattern = z.infer<typeof TestPatternSchema>;
export type Media = z.infer<typeof MediaSchema>;
