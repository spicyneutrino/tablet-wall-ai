import type { DeviceId } from './devices';

const segment = encodeURIComponent;
const device = (id: DeviceId) => `/api/v3/devices/${segment(id)}` as const;
const saved = (kind: 'scenes' | 'layouts' | 'logical-layouts', name: string, replace = false) =>
  `/api/v3/${kind}/${segment(name)}${replace ? '?replace=true' : ''}` as const;

export const paths = {
  config: '/api/v3/config', devices: '/devices', images: '/api/v3/images', scene: '/api/v3/scene',
  upload: (name: string) => `/uploads?name=${segment(name)}` as const,
  testPattern: '/api/v3/test-pattern',
  color: (id?: DeviceId) => id ? `/devices/${segment(id)}/color` as const : '/devices/color',
  scenes: '/api/v3/scenes', savedScene: (name: string, replace = false) => saved('scenes', name, replace),
  recallScene: (name: string) => `${saved('scenes', name)}/recall` as const,
  layout: '/api/v3/layout', logicalLayout: '/api/v3/logical-layout', clearLayout: '/api/v3/layout/clear',
  gridPreview: '/api/v3/grid/preview', grid: '/api/v3/grid', layouts: '/api/v3/layouts', logicalLayouts: '/api/v3/logical-layouts',
  savedLayout: (kind: 'logical' | 'physical', name: string, replace = false) => saved(kind === 'logical' ? 'logical-layouts' : 'layouts', name, replace),
  recallLayout: (kind: 'logical' | 'physical', name: string) => `${saved(kind === 'logical' ? 'logical-layouts' : 'layouts', name)}/recall` as const,
  device, identify: (id: DeviceId) => `${device(id)}/identify` as const,
  retryImage: (id: DeviceId) => `${device(id)}/retry-image` as const,
  reconnect: (id: DeviceId) => `${device(id)}/reconnect` as const,
  impact: (id: DeviceId) => `${device(id)}/impact` as const,
  placement: (id: DeviceId) => `${device(id)}/placement` as const,
  rebindPreview: (id: DeviceId) => `${device(id)}/rebind/preview` as const,
  rebind: (id: DeviceId) => `${device(id)}/rebind` as const,
  tabletAssignment: (id: DeviceId) => `/api/v3/tablet-assignments/${segment(id)}` as const,
  display: (id: DeviceId) => `/api/v3/displays/${segment(id)}` as const,
  calibration: (id: DeviceId) => `/api/v3/calibrations/${segment(id)}` as const,
  calibrationCheck: '/api/v3/calibration-check', operatorConfig: '/operator-config', readiness: '/api/v3/readiness', joinQr: '/api/v3/join-qr',
  diagnostics: (verify = false) => `/diagnostics${verify ? '?verify=1' : ''}` as const,
  media: '/media', playlist: '/api/v3/playlist', playback: '/api/v3/playback',
  playbackCommand: (action: 'start' | 'pause' | 'stop' | 'retry' | 'next' | 'previous') => `/api/v3/playback/${action}` as const,
} as const;
export type ApiPath = { [K in keyof typeof paths]: (typeof paths)[K] extends (...args: never[]) => infer R ? R : (typeof paths)[K] }[keyof typeof paths];
export type Method = 'GET' | 'PUT' | 'POST' | 'PATCH' | 'DELETE';
