import { z } from 'zod';

export const OperatorConfigSchema = z.looseObject({ tablet_origin: z.string().nullable() });
export const ReadinessSchema = z.looseObject({ tablet_url: z.string().nullable(), join_qr_url: z.string().nullable(),
  wifi: z.looseObject({ name: z.string().nullable(), known: z.boolean() }),
  security: z.looseObject({ transport: z.enum(['http', 'https', 'unknown']), authentication: z.enum(['disabled', 'shared-secret']), uploads: z.enum(['disabled', 'loopback', 'proxy']), trust: z.string() }),
  content: z.looseObject({ type: z.string().nullable(), summary: z.string() }),
  wall: z.looseObject({ schema: z.int().nullable(), generation: z.string().nullable(), revision: z.int().nullable(), layout: z.enum(['logical', 'physical']).nullable() }),
  devices: z.looseObject({ online: z.int().nonnegative(), total: z.int().nonnegative() }),
  storage: z.looseObject({ readable: z.boolean(), database: z.string(), assets: z.string(), media: z.string(), backup_dir: z.string().nullable() }),
  backup: z.looseObject({ last_manifest_at: z.string().nullable(), recorded: z.boolean(), scope: z.string() }),
  restore_rehearsal: z.looseObject({ completed_utc: z.string().nullable(), recorded: z.boolean() }), advice: z.array(z.string()), errors: z.array(z.string()) });
export type Readiness = z.infer<typeof ReadinessSchema>;
export type OperatorConfig = z.infer<typeof OperatorConfigSchema>;
