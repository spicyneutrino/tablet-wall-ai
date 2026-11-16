import type { Config } from '../api/config';
import type { DeviceStatus } from '../api/devices';

export function projectRoster(config: Config, roster: Record<string, DeviceStatus>) {
  const devices = Object.fromEntries(Object.entries(roster).map(([id, device]) => [id, {
    online: device.online, protocol: device.protocol ?? undefined, caps: device.caps,
    connection_id: device.connection_id,
    mapping: device.mapping ? { state: device.mapping.state, reason: device.mapping.reason ?? undefined,
      profile_revision: device.mapping.profile_revision ?? undefined,
      calibration_revision: device.mapping.calibration_revision ?? undefined } : undefined,
    identify: device.identify ?? undefined,
    render: device.render ? { ...device.render, age_ms: device.render.age_ms ?? undefined,
      expected_token: device.render.expected_token ?? undefined, accepted_token: device.render.accepted_token ?? undefined,
      reason: device.render.reason ?? undefined,
      observed_mono: typeof device.render.observed_mono === 'number' ? device.render.observed_mono : undefined } : undefined,
  }]));
  return { ...config, runtime: { ...config.runtime, devices } };
}
