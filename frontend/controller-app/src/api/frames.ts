import { z } from 'zod';
import { ConfigSchema } from './config';
import { DeviceIdSchema, DeviceSchema } from './devices';
import { ConfigEtagSchema } from './etag';
import { ActivePlaybackStatusSchema } from './playback';

export const ControllerFrameSchema = z.union([
  z.discriminatedUnion('type', [
    z.looseObject({ type: z.literal('snapshot'), config: ConfigSchema, devices: z.array(DeviceSchema).optional() }),
    z.looseObject({ type: z.literal('config_updated'), revision: z.int().nonnegative(), generation: z.string(), etag: ConfigEtagSchema }),
    z.looseObject({ type: z.literal('device_online'), device: DeviceSchema }),
    z.looseObject({ type: z.literal('device_updated'), device: DeviceSchema }),
    z.looseObject({ type: z.literal('device_offline'), device_id: DeviceIdSchema, last_seen: z.string() }),
    z.looseObject({ type: z.literal('device_removed'), device_id: DeviceIdSchema }),
    z.looseObject({ type: z.literal('device_status') }),
  ]),
  ActivePlaybackStatusSchema.extend({ type: z.literal('playback_status') }),
  z.strictObject({ type: z.literal('playback_status'), state: z.literal('stopped') }),
]);
export type ControllerFrame = z.infer<typeof ControllerFrameSchema>;
