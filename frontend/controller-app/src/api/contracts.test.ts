import { readFileSync, readdirSync } from 'node:fs';
import { expect, expectTypeOf, test } from 'vitest';
import { z } from 'zod';
import { ConfigSchema, TabletAssignmentResponseSchema } from './config';
import { ColorDeliverySchema, DeviceIdSchema, DevicesSchema, TabletAssignmentCommandSchema } from './devices';
import { DiagnosticsSchema } from './diagnostics';
import { ErrorBodySchema, errorMessage } from './errors';
import { ConfigEtagSchema, PlaylistEtagSchema, PlaybackVersionSchema } from './etag';
import type { ConfigEtag, PlaylistEtag, PlaybackVersion } from './etag';
import { ControllerFrameSchema } from './frames';
import { GridCommandSchema, GridPreviewSchema } from './grid';
import { ImagesSchema, MediaSchema, TestPatternSchema, UploadResponseSchema } from './images';
import { LayoutSchema } from './layouts';
import { ImpactPreviewSchema, RebindCommandSchema, RebindPreviewSchema } from './lifecycle';
import { CalibrationResponseSchema, DisplayResponseSchema, RulerCheckResultSchema } from './measure';
import { paths } from './paths';
import type { ApiPath } from './paths';
import { PlaybackStatusSchema, PlaylistResponseSchema } from './playback';
import { OperatorConfigSchema, ReadinessSchema } from './readiness';
import { SavedLayoutsSchema, SavedScenesSchema } from './saved';
import { AssetIdSchema, SceneInputSchema } from './scene';

const directory = new URL('./__fixtures__/', import.meta.url);
const fixtures = readdirSync(directory).filter((name) => name.endsWith('.json'));
const schemas: Record<string, z.ZodType> = {
  devices: DevicesSchema, 'grid-logical': GridPreviewSchema, 'grid-physical': GridPreviewSchema,
  'saved-logical-layouts': SavedLayoutsSchema, 'saved-physical-layouts': SavedLayoutsSchema, 'saved-scenes': SavedScenesSchema,
  display: DisplayResponseSchema, calibration: CalibrationResponseSchema, 'test-pattern': TestPatternSchema, images: ImagesSchema,
  impact: ImpactPreviewSchema, 'rebind-preview': RebindPreviewSchema, 'ruler-check': RulerCheckResultSchema, readiness: ReadinessSchema,
  diagnostics: DiagnosticsSchema, 'diagnostics-verified': DiagnosticsSchema, 'operator-config': OperatorConfigSchema, upload: UploadResponseSchema,
  media: MediaSchema, 'playlist-empty': PlaylistResponseSchema, playlist: PlaylistResponseSchema, 'playback-stopped': PlaybackStatusSchema,
  'playback-start': PlaybackStatusSchema, playback: PlaybackStatusSchema, 'playback-stop': PlaybackStatusSchema, color: ColorDeliverySchema,
  'error-validation': ErrorBodySchema, 'error-precondition': ErrorBodySchema,
};
function fixture(name: string): unknown {
  return JSON.parse(readFileSync(new URL(name, directory), 'utf8'));
}

test('the captured contract includes both layout kinds and every emitted frame type', () => {
  expect(fixtures).toEqual(expect.arrayContaining(['layout-logical.json', 'layout-physical.json',
    ...['snapshot', 'config_updated', 'device_online', 'device_updated', 'device_offline', 'device_removed', 'playback_status'].map((type) => `frame-${type}.json`)]));
});

for (const name of fixtures) {
  test(`parses captured ${name}`, () => {
    const key = name.slice(0, -5);
    const schema = key.startsWith('config') ? ConfigSchema : key.startsWith('frame-') ? ControllerFrameSchema : key.startsWith('layout-') ? LayoutSchema : schemas[key];
    expect(schema, `Missing fixture schema for ${name}`).toBeDefined();
    expect(schema?.safeParse(fixture(name)).success).toBe(true);
  });
  if (name.startsWith('layout-')) {
    test(`round trips ${name} without dropping fields`, () => {
      const raw = fixture(name);
      expect(LayoutSchema.parse(raw)).toEqual(raw);
    });
  }
}

test('preserves unknown fields throughout a config and nested layouts', () => {
  const config = ConfigSchema.parse(fixture('config-physical.json'));
  config.future_config = { enabled: true };
  config.scene.future_scene = 1;
  config.scene.content.future_content = true;
  config.layout.future_layout = 'preserved';
  if (config.layout.kind !== 'physical') throw new Error('Physical fixture is required');
  const slot = Object.values(config.layout.slots)[0];
  if (!slot) throw new Error('Fixture must contain a slot');
  slot.future_slot = [1, 2];
  const runtime = Object.values(config.runtime.devices)[0];
  if (!runtime) throw new Error('Fixture must contain a runtime device');
  runtime.future_device = 'preserved';
  expect(ConfigSchema.parse(config)).toEqual(config);
  const logical = LayoutSchema.parse(fixture('layout-logical.json'));
  if (logical.kind !== 'logical') throw new Error('Logical fixture is required');
  const placement = Object.values(logical.placements)[0];
  if (!placement) throw new Error('Fixture must contain a placement');
  placement.future_placement = { value: 1 };
  placement.bezel.future_bezel = 5;
  expect(LayoutSchema.parse(logical)).toEqual(logical);
});

const asset = AssetIdSchema.parse(`sha256:${'a'.repeat(64)}`);
test('rejects derived fields on scene writes', () => {
  expect(() => SceneInputSchema.parse({ type: 'image', asset, fit: 'cover', url: 'x' })).toThrow();
  for (const field of ['intrinsicWidth', 'intrinsicHeight', 'available', 'cropX', 'cropY']) {
    expect(SceneInputSchema.safeParse({ type: 'image', asset, fit: 'cover', [field]: 1 }).success).toBe(false);
  }
  expect(SceneInputSchema.parse({ type: 'image', asset, fit: 'cover' })).toEqual({ type: 'image', asset, fit: 'cover' });
});

test.each([{ type: 'image', asset: 'invalid', fit: 'cover' }, { type: 'image', asset, fit: 'stretch' },
  { type: 'color', asset }, { type: 'calibration', background: '#ffffff' }, { type: 'video', asset }])('rejects illegal scene variants %j', (input) => {
  expect(SceneInputSchema.safeParse(input).success).toBe(false);
});

test.each([{ operator_state_version: 2 }, { schema: 3 }, { layout: { kind: 'future' } }])('rejects unsupported config %j', (change) => {
  const config = ConfigSchema.parse(fixture('config-empty.json'));
  expect(ConfigSchema.safeParse({ ...config, ...change }).success).toBe(false);
});

test('rejects malformed frames and accepts compatibility device_status frames', () => {
  expect(ControllerFrameSchema.safeParse({ type: 'config_updated', revision: '1', generation: 'g', etag: 'e' }).success).toBe(false);
  expect(ControllerFrameSchema.safeParse({ type: 'future_event' }).success).toBe(false);
  expect(ControllerFrameSchema.parse({ type: 'device_status', future: true })).toEqual({ type: 'device_status', future: true });
});

test('keeps concurrency tokens distinct and converts the numeric playback version to an HTTP token', () => {
  expectTypeOf<ConfigEtag>().not.toEqualTypeOf<PlaylistEtag>();
  expectTypeOf<ConfigEtag>().not.toEqualTypeOf<PlaybackVersion>();
  expectTypeOf<PlaylistEtag>().not.toEqualTypeOf<PlaybackVersion>();
  expect(ConfigEtagSchema.parse('config')).toBe('config');
  expect(PlaylistEtagSchema.parse('playlist')).toBe('playlist');
  expect(PlaybackVersionSchema.parse(3)).toBe('3');
  expect(PlaybackVersionSchema.safeParse(1.5).success).toBe(false);
});

test('formats all error variants and replaces UUIDs with operator labels', () => {
  const id = '00000000-0000-4000-8000-000000000001';
  for (const detail of [`Cannot use ${id}`, [{ loc: ['body'], msg: `Cannot use ${id}`, type: 'invalid' }], { code: 'invalid', message: `Cannot use ${id}` }]) {
    expect(errorMessage(detail, () => 'North tablet')).toBe('Cannot use North tablet');
  }
  expect(errorMessage(null)).toBe('The server returned an unreadable error.');
});

test('encodes path segments and query values without introducing a route', () => {
  const id = DeviceIdSchema.parse('00000000-0000-4000-8000-000000000001');
  const path: ApiPath = paths.savedScene('a/b ?#', true);
  expect(path).toBe('/api/v3/scenes/a%2Fb%20%3F%23?replace=true');
  expect(paths.recallLayout('logical', 'a/b')).toBe('/api/v3/logical-layouts/a%2Fb/recall');
  expect(paths.upload('a&b.png')).toBe('/uploads?name=a%26b.png');
  expect(paths.rebindPreview(id)).toBe(`/api/v3/devices/${id}/rebind/preview`);
  expect(paths.color()).toBe('/devices/color');
  expect(paths.color(id)).toBe(`/devices/${id}/color`);
  expect(paths.diagnostics(true)).toBe('/diagnostics?verify=1');
});

test('rejects inconsistent grid membership and overrides from the other layout kind', () => {
  const id = DeviceIdSchema.parse('00000000-0000-4000-8000-000000000001');
  const grid = { kind: 'logical', device_ids: [id], rows: 1, columns: 1, gap: 0, padding: 0,
    sizing: 'tablets', orientation: 'preserve', allow_empty_cells: false, release_unselected: [] };
  expect(GridCommandSchema.safeParse(grid).success).toBe(true);
  for (const change of [{ device_ids: [id, id] }, { rows: 2 }, { release_unselected: [id] }, { mount_angles: { [id]: 0 } }, { gap: 0.5 }]) {
    expect(GridCommandSchema.safeParse({ ...grid, ...change }).success).toBe(false);
  }
  expect(RebindCommandSchema.safeParse({ replaces: id, hardware: 'same_hardware', active: true,
    saved_layouts: [{ name: 'Wall', etag: 'a' }, { name: 'Wall', etag: 'b' }], transfer_label: true }).success).toBe(false);
});

test('requires a model for an explicit assignment and parses the assignment response envelope', () => {
  expect(TabletAssignmentCommandSchema.safeParse({ mode: 'explicit' }).success).toBe(false);
  expect(TabletAssignmentCommandSchema.parse({ mode: 'manual', model_id: null })).toEqual({ mode: 'manual', model_id: null });
  expect(TabletAssignmentCommandSchema.parse({ mode: 'explicit', model_id: 'ipad-air-2' })).toEqual({ mode: 'explicit', model_id: 'ipad-air-2' });
  expect(TabletAssignmentResponseSchema.parse({ assignment: { mode: 'manual', model_id: null }, suggestions: [], etag: 'config' })).toEqual({
    assignment: { mode: 'manual', model_id: null }, suggestions: [], etag: 'config',
  });
});
