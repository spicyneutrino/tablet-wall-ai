import { z } from 'zod';
import { DeviceIdSchema, ViewportSchema } from './devices';
import { ConfigEtagSchema } from './etag';
import { LayoutSchema } from './layouts';

export const GridGuardSchema = z.strictObject({ connection_id: z.string().nullable(), viewport: ViewportSchema.nullable() });
const common = { device_ids: z.array(DeviceIdSchema).min(1), rows: z.int().positive(), columns: z.int().positive(), gap: z.number().nonnegative(),
  padding: z.number().nonnegative(), sizing: z.enum(['fixed', 'tablets']), orientation: z.enum(['preserve', 'auto', 'portrait', 'landscape']),
  allow_empty_cells: z.boolean(), release_unselected: z.array(DeviceIdSchema), guards: z.record(DeviceIdSchema, GridGuardSchema).optional() };
export const GridCommandSchema = z.discriminatedUnion('kind', [
  z.strictObject({ ...common, kind: z.literal('logical'), gap: z.int().nonnegative(), padding: z.int().nonnegative(),
    logical_sizes: z.record(DeviceIdSchema, z.strictObject({ w: z.int().positive(), h: z.int().positive() })).optional() }),
  z.strictObject({ ...common, kind: z.literal('physical'), mount_angles: z.record(DeviceIdSchema, z.union([z.literal(0), z.literal(90), z.literal(180), z.literal(270)])).optional(),
    physical_revisions: z.record(DeviceIdSchema, z.strictObject({ profile_revision: z.int().positive(), calibration_revision: z.int().positive() })).optional() }),
]).superRefine((command, ctx) => {
  const selected = new Set<string>(command.device_ids);
  const capacity = command.rows * command.columns;
  if (selected.size !== command.device_ids.length || command.device_ids.length > capacity || (!command.allow_empty_cells && command.device_ids.length !== capacity)) {
    ctx.addIssue({ code: 'custom', message: 'Grid membership must fill the selected capacity without duplicates' });
  }
  if (new Set(command.release_unselected).size !== command.release_unselected.length || command.release_unselected.some((id) => selected.has(id))) {
    ctx.addIssue({ code: 'custom', message: 'Released tablets must be unique and unselected' });
  }
  const maps = [command.guards, ...(command.kind === 'logical' ? [command.logical_sizes] : [command.mount_angles, command.physical_revisions])];
  if (maps.some((map) => map && Object.keys(map).some((id) => !selected.has(id)))) {
    ctx.addIssue({ code: 'custom', message: 'Grid overrides must name selected tablets' });
  }
});
export const GridPreviewSchema = z.looseObject({ layout: LayoutSchema, order: z.array(DeviceIdSchema), warnings: z.array(z.string()),
  guards: z.record(DeviceIdSchema, GridGuardSchema), base_etag: ConfigEtagSchema, reservations_removed: z.array(DeviceIdSchema), previous_kind: z.enum(['logical', 'physical']) });
export type GridCommand = z.infer<typeof GridCommandSchema>;
export type GridGuard = z.infer<typeof GridGuardSchema>;
export type GridPreview = z.infer<typeof GridPreviewSchema>;
