import empty from '../api/__fixtures__/config-empty.json';
import { ConfigSchema } from '../api/config';
import { DeviceSchema, DeviceIdSchema, RenderEvidenceSchema } from '../api/devices';
export const A = DeviceIdSchema.parse('00000000-0000-4000-8000-000000000001');
export const B = DeviceIdSchema.parse('00000000-0000-4000-8000-000000000002');
export const C = DeviceIdSchema.parse('00000000-0000-4000-8000-000000000003');
export function renderFixture(state = 'loading', extra: Record<string, unknown> = {}) {
  return RenderEvidenceSchema.parse({ state, current: false, expected_token: null, accepted_token: null,
    accepted_status: null, received_at: null, age_ms: 0, reason: null, ...extra });
}
export function deviceFixture(id = A, extra: Record<string, unknown> = {}) {
  return DeviceSchema.parse({ device_id: id, width: 100, height: 100, type: 'other', color: null,
    protocol: 3, caps: ['render_ack'], online: true, ...extra });
}
export function configFixture(etag: string, paint = 'loading') {
  return ConfigSchema.parse({ ...empty, etag, revision: 1, generation: 'session',
    layout: { kind: 'logical', width: 100, height: 100, placements: {}, sizing: { mode: 'fixed', padding: 0 } },
    runtime: { ...empty.runtime, devices: { [A]: deviceFixture(A, { render: renderFixture(paint) }) } } });
}
