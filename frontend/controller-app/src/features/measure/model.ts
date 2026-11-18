import type { Config } from '../../api/config';
import type { DeviceId } from '../../api/devices';
import type { WallStore } from '../../state/store';
import { selectedViewport } from '../../domain/calibration';
import { createPayloads } from '../../domain/measurements';
import { CalibrationCommandSchema, ProfileCommandSchema } from '../../api/measure';

export const steps = ['model', 'profile', 'ruler', 'calibration'] as const;
export const stepNames = ['Model', 'Size and bezels', 'Ruler check', 'Review and save'];
export type Values = Record<string, string>;
export function latestProfile(config: Config, id: DeviceId) {
  return config.displays.filter(p => p.device_id === id).sort((a, b) => b.revision - a.revision)[0];
}
export function modelChoice(state: WallStore, id: DeviceId) {
  const value = state.forms[`${id}:model`]?.values['tablet-model'];
  if (typeof value === 'string') return value;
  const assignment = state.server.config?.tablet_assignments[id];
  return assignment?.mode === 'explicit' ? assignment.model_id : assignment?.mode === 'manual' ? 'manual' : '';
}
export function measurementValues(state: WallStore, id: DeviceId) {
  const config = state.server.config;
  if (!config) throw new Error('Wait for the wall to load.');
  const profile = latestProfile(config, id);
  const model = config.tablet_models[modelChoice(state, id)];
  const source = profile ?? model;
  const calibration = config.calibrations.filter(c => c.device_id === id).sort((a, b) => b.revision - a.revision)[0];
  const viewport = liveViewport(state, id);
  const profileDefaults: Values = {
    profileActiveWidth: String(source?.active_width_mm ?? ''), profileActiveHeight: String(source?.active_height_mm ?? ''),
    profileBezelLeft: String(source?.bezels.left ?? 0), profileBezelRight: String(source?.bezels.right ?? 0),
    profileBezelTop: String(source?.bezels.top ?? 0), profileBezelBottom: String(source?.bezels.bottom ?? 0),
    profilePixelWidth: String(profile?.panel_pixels?.width ?? ''), profilePixelHeight: String(profile?.panel_pixels?.height ?? ''),
    profileLabel: profile?.label ?? model?.label ?? 'Measured tablet', profileProvenance: profile?.provenance ?? (model ? 'model' : 'manual'),
  };
  const calibrationDefaults: Values = {
    calProfileRevision: String(profile?.revision ?? 1),
    calViewportWidth: String(viewport?.width ?? calibration?.viewport_width ?? ''),
    calViewportHeight: String(viewport?.height ?? calibration?.viewport_height ?? ''),
    calDpr: String(viewport?.dpr ?? calibration?.dpr ?? ''), calOrientation: String(viewport?.orientation ?? calibration?.orientation ?? ''),
    calMode: viewport?.mode ?? calibration?.mode ?? '', calQuarterTurn: String(calibration?.quarter_turn ?? 0),
    calAnchorEdge: calibration?.anchor_edge ?? 'top-left', calOffsetX: String(calibration?.panel_offset_mm[0] ?? 0),
    calOffsetY: String(calibration?.panel_offset_mm[1] ?? 0),
    calMmCssX: String(calibration?.mm_per_css[0] ?? model?.mm_per_css[0] ?? ''),
    calMmCssY: String(calibration?.mm_per_css[1] ?? model?.mm_per_css[1] ?? ''),
    calUncertainty: String(calibration?.uncertainty_mm ?? model?.uncertainty_mm ?? 0),
    calMethod: calibration?.method ?? (model ? 'model-estimate' : 'manual'),
    rulerX: '', rulerY: '', rulerErrorX: '0.5', rulerErrorY: '0.5', rulerSpanX: '200', rulerSpanY: '200',
  };
  const merge = (defaults: Values, group: 'profile' | 'calibration') => Object.fromEntries(Object.entries(defaults)
    .map(([key, fallback]) => [key, typeof state.forms[`${id}:${group}`]?.values[key] === 'string'
      ? String(state.forms[`${id}:${group}`]?.values[key]) : fallback]));
  return { ...merge(profileDefaults, 'profile'), ...merge(calibrationDefaults, 'calibration') };
}
export function payloads(values: Values, markInvalid?: (id: string, invalid: boolean) => void) {
  return createPayloads({ fields: Object.fromEntries(Object.entries(values).map(([id, value]) => [id, { id, value }])),
    num: raw => raw.trim() && Number.isFinite(Number(raw)) ? Number(raw) : null,
    markInvalid: (field, invalid) => { if (field.id) markInvalid?.(field.id, invalid); } });
}
export function profileBody(values: Values) { return ProfileCommandSchema.parse(payloads(values).buildProfileBody()); }
export function calibrationBody(values: Values) { return CalibrationCommandSchema.parse(payloads(values).buildCalibrationBody()); }

export function liveViewport(state: WallStore, id: DeviceId) {
  const record = state.server.roster[id];
  return selectedViewport({ [id]: record ? { online: record.online, viewport: record.viewport ?? undefined } : undefined }, id);
}
