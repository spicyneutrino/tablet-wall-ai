import { z } from 'zod';

export const DiagnosticsSchema = z.looseObject({ media: z.looseObject({ quota_bytes: z.int().nonnegative(), used_bytes: z.int().nonnegative(),
  free_bytes: z.int().nonnegative(), reserve_bytes: z.int().nonnegative(), objects: z.int().nonnegative(), assets: z.int().nonnegative(), orphans: z.int().nonnegative(),
  integrity: z.looseObject({ ok: z.boolean(), problems: z.array(z.unknown()) }).optional() }),
  db: z.looseObject({ schema: z.int(), bytes: z.int().nonnegative().nullable() }), backup: z.looseObject({ last_manifest_at: z.string().nullable() }),
  clients: z.looseObject({ online: z.int().nonnegative(), total: z.int().nonnegative(), wake_lock: z.record(z.string(), z.int().nonnegative()) }) });
export type Diagnostics = z.infer<typeof DiagnosticsSchema>;
