import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { expect, test } from '@playwright/test';
import type { BrowserContext } from '@playwright/test';
import { z } from 'zod';
import { startServer } from './server';
import { ConfigSchema } from '../src/api/config';
import { DeviceIdSchema, DevicesSchema, ColorDeliverySchema } from '../src/api/devices';
import { DiagnosticsSchema } from '../src/api/diagnostics';
import { ErrorBodySchema } from '../src/api/errors';
import { ControllerFrameSchema } from '../src/api/frames';
import { GridCommandSchema, GridPreviewSchema } from '../src/api/grid';
import { ImagesSchema, MediaSchema, TestPatternSchema, UploadResponseSchema } from '../src/api/images';
import { LayoutSchema } from '../src/api/layouts';
import { ImpactPreviewSchema, RebindCommandSchema, RebindPreviewSchema } from '../src/api/lifecycle';
import { CalibrationResponseSchema, DisplayResponseSchema, RulerCheckResultSchema, RulerCheckSchema } from '../src/api/measure';
import { paths } from '../src/api/paths';
import type { ApiPath, Method } from '../src/api/paths';
import { PlaybackStatusSchema, PlaylistResponseSchema } from '../src/api/playback';
import { OperatorConfigSchema, ReadinessSchema } from '../src/api/readiness';
import { SavedLayoutsSchema, SavedScenesSchema } from '../src/api/saved';
import { SceneInputSchema } from '../src/api/scene';

test('parses the real controller HTTP and WebSocket contract', async ({ browser, playwright }) => {
  test.setTimeout(90_000);
  const server = await startServer();
  const contexts: BrowserContext[] = [];
  const api = await playwright.request.newContext({ baseURL: server.origin, extraHTTPHeaders: { Origin: server.origin } });
  const captured = new Map<string, unknown>();
  const frames: unknown[] = [];
  const browserErrors: string[] = [];
  const ids = [1, 2, 3, 4].map((n) => DeviceIdSchema.parse(`00000000-0000-4000-8000-00000000000${n}`));
  const [first, second, third, fourth] = ids;
  if (!first || !second || !third || !fourth) throw new Error('Four tablet IDs are required');

  function parse<T>(name: string, schema: z.ZodType<T>, raw: unknown): T {
    const value = schema.parse(raw);
    captured.set(name, raw);
    return value;
  }
  async function request<T>(name: string, schema: z.ZodType<T>, method: Method, path: ApiPath, data?: unknown, etag?: string) {
    const response = await api.fetch(path, { method, data, headers: etag ? { 'If-Match': etag } : {} });
    expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
    return parse(name, schema, await response.json());
  }
  const config = () => request('config', ConfigSchema, 'GET', paths.config);
  async function write(path: ApiPath, data?: unknown, method: Method = 'POST') {
    return request('config-write', ConfigSchema, method, path, data, (await config()).etag);
  }

  try {
    const operator = await browser.newContext();
    contexts.push(operator);
    const page = await operator.newPage();
    page.on('websocket', (socket) => {
      if (new URL(socket.url()).pathname === '/ws/controller') {
        socket.on('framereceived', ({ payload }) => frames.push(JSON.parse(payload.toString())));
      }
    });
    page.on('pageerror', (error) => browserErrors.push(error.message));
    await page.goto(`${server.origin}/controller/app/`);
    await expect.poll(() => frames.length).toBeGreaterThan(0);
    parse('config-empty', ConfigSchema, await config());
    for (const id of ids) {
      const context = await browser.newContext({ viewport: { width: 768, height: 1024 } });
      contexts.push(context);
      await context.addInitScript((deviceId) => localStorage.setItem('tablet-wall-device-id', deviceId), id);
      const tablet = await context.newPage();
      tablet.on('pageerror', (error) => browserErrors.push(error.message));
      await tablet.goto(`${server.origin}/client/`);
    }
    await expect.poll(async () => Object.values((await config()).runtime.devices).filter((device) => device.online && device.protocol === 3).length).toBe(4);
    await request('devices', DevicesSchema, 'GET', paths.devices);
    const grid = GridCommandSchema.parse({ kind: 'logical', device_ids: ids, rows: 2, columns: 2, gap: 0, padding: 0,
      sizing: 'tablets', orientation: 'preserve', allow_empty_cells: false, release_unselected: [] });
    const preview = await request('grid-logical', GridPreviewSchema, 'POST', paths.gridPreview, grid, (await config()).etag);
    const logical = await write(paths.grid, { ...grid, guards: preview.guards });
    parse('layout-logical', LayoutSchema, logical.layout);
    await write(paths.savedLayout('logical', 'Contract logical'), undefined, 'PUT');
    await request('saved-logical-layouts', SavedLayoutsSchema, 'GET', paths.logicalLayouts);
    await write(paths.recallLayout('logical', 'Contract logical'));
    const slots: Record<string, unknown> = {};
    for (const [index, id] of ids.entries()) {
      const profile = await request('display', DisplayResponseSchema, 'PUT', paths.display(id), {
        active_width_mm: 150, active_height_mm: 200, bezels: { left: 10, right: 10, top: 10, bottom: 10 },
        panel_pixels: { width: 768, height: 1024 }, label: 'Contract tablet', provenance: 'manual',
      }, (await config()).etag);
      const viewport = (await config()).runtime.devices[id]?.viewport;
      if (!viewport) throw new Error('Joined tablet must report a viewport');
      const calibration = await request('calibration', CalibrationResponseSchema, 'PUT', paths.calibration(id), {
        profile_revision: profile.display.revision, viewport_width: viewport.width, viewport_height: viewport.height, dpr: viewport.dpr,
        orientation: viewport.orientation, mode: viewport.mode, quarter_turn: 0, panel_offset_mm: [0, 0], mm_per_css: [150 / 768, 200 / 1024],
        anchor_edge: 'top-left', uncertainty_mm: 0.5, method: 'manual', viewport_guard: true,
      }, (await config()).etag);
      slots[id] = { center_x_mm: 85 + (index % 2) * 170, center_y_mm: 110 + Math.floor(index / 2) * 220,
        mount_angle: 0, nudge_x_mm: 0, nudge_y_mm: 0, profile_revision: profile.display.revision, calibration_revision: calibration.calibration.revision };
    }
    const physical = await write(paths.layout, { bounds: { x: 0, y: 0, width: 340, height: 440 }, slots, sizing: { mode: 'fixed', padding: 0 } }, 'PUT');
    parse('layout-physical', LayoutSchema, physical.layout);
    parse('config-physical', ConfigSchema, physical);
    await write(paths.savedLayout('physical', 'Contract physical'), undefined, 'PUT');
    await request('saved-physical-layouts', SavedLayoutsSchema, 'GET', paths.layouts);
    const pattern = await request('test-pattern', TestPatternSchema, 'POST', paths.testPattern, { pattern: 'grid' }, (await config()).etag);
    const image = SceneInputSchema.parse({ type: 'image', asset: pattern.id, fit: 'contain', background: '#0b1120' });
    parse('config-image', ConfigSchema, await write(paths.scene, { content: image }, 'PUT'));
    await request('images', ImagesSchema, 'GET', paths.images);
    await write(paths.savedScene('Contract image'), undefined, 'PUT');
    await request('saved-scenes', SavedScenesSchema, 'GET', paths.scenes);
    await write(paths.recallScene('Contract image'));
    if (physical.layout.kind !== 'physical') throw new Error('Physical layout is required');
    const physicalGrid = GridCommandSchema.parse({ ...grid, kind: 'physical', orientation: 'portrait',
      physical_revisions: Object.fromEntries(Object.entries(physical.layout.slots).map(([id, slot]) => [id, {
        profile_revision: slot.profile_revision, calibration_revision: slot.calibration_revision,
      }])) });
    await request('grid-physical', GridPreviewSchema, 'POST', paths.gridPreview, physicalGrid, (await config()).etag);
    await request('impact', ImpactPreviewSchema, 'GET', paths.impact(first));
    const rebind = RebindCommandSchema.parse({ replaces: first, hardware: 'different_hardware', active: false, saved_layouts: [], transfer_label: true });
    await request('rebind-preview', RebindPreviewSchema, 'POST', paths.rebindPreview(second), rebind, (await config()).etag);
    const ruler = RulerCheckSchema.parse({ device_id: first, profile_revision: 1, quarter_turn: 0, axis: 'x', span_px: 500, span_mm: 100,
      span_error_mm: 0.5, usable_width_px: 768, usable_height_px: 1024 });
    await request('ruler-check', RulerCheckResultSchema, 'POST', paths.calibrationCheck, ruler);
    await request('readiness', ReadinessSchema, 'GET', paths.readiness);
    await request('diagnostics', DiagnosticsSchema, 'GET', paths.diagnostics());
    await request('diagnostics-verified', DiagnosticsSchema, 'GET', paths.diagnostics(true));
    await request('operator-config', OperatorConfigSchema, 'GET', paths.operatorConfig);
    const qr = await api.get(paths.joinQr);
    expect(qr.status()).toBe(200);
    expect(qr.headers()['content-type']).toBe('image/png');
    const bytes = await (await api.get(pattern.url)).body();
    const upload = await api.post(paths.upload('Contract.png'), { data: bytes, headers: { 'Content-Type': 'image/png' } });
    expect(upload.status()).toBe(201);
    parse('upload', UploadResponseSchema, await upload.json());
    await request('media', MediaSchema, 'GET', paths.media);
    const playlist = await request('playlist-empty', PlaylistResponseSchema, 'GET', paths.playlist);
    await request('playlist', PlaylistResponseSchema, 'PUT', paths.playlist, { items: [{ asset: pattern.id, dwell_ms: 10000 }], loop: true }, playlist.etag);
    await request('playback-stopped', PlaybackStatusSchema, 'GET', paths.playback);
    await request('playback-start', PlaybackStatusSchema, 'POST', paths.playbackCommand('start'), { policy: 'online', exclusions: [] });
    // The playback version advances as tablets acknowledge items; a 412 means re-read and retry, as the controller does.
    await expect(async () => {
      const status = await request('playback', PlaybackStatusSchema, 'GET', paths.playback);
      if (!('version' in status) || typeof status.version !== 'string') throw new Error('Started playback must have a version');
      await request('playback-stop', PlaybackStatusSchema, 'POST', paths.playbackCommand('stop'), undefined, status.version);
    }).toPass({ timeout: 5_000 });
    await write(paths.device(first), { label: 'North tablet' }, 'PATCH');
    await write(paths.identify(first), { duration_ms: 1000 });
    await request('color', ColorDeliverySchema, 'POST', paths.color(), { color: '#123456' });
    await contexts[4]?.close();
    await expect.poll(async () => (await config()).runtime.devices[fourth]?.online).toBe(false);
    parse('config-offline', ConfigSchema, await config());
    await write(paths.device(fourth), { remove_active: true, saved_layouts: 'keep' }, 'DELETE');
    const invalid = await api.put(paths.scene, { data: { content: { ...image, url: 'x' } }, headers: { 'If-Match': (await config()).etag } });
    expect(invalid.status()).toBe(422);
    parse('error-validation', ErrorBodySchema, await invalid.json());
    const missing = await api.put(paths.scene, { data: { content: image } });
    expect(missing.status()).toBe(428);
    parse('error-precondition', ErrorBodySchema, await missing.json());
    const observed = new Set<string>();
    for (const raw of frames) {
      const frame = ControllerFrameSchema.parse(raw);
      if (!observed.has(frame.type)) captured.set(`frame-${frame.type}`, raw);
      observed.add(frame.type);
    }
    expect([...observed].sort()).toEqual(['config_updated', 'device_offline', 'device_online', 'device_removed', 'device_updated', 'playback_status', 'snapshot']);
    expect(browserErrors).toEqual([]);
    if (process.env.CAPTURE === '1') {
      const directory = fileURLToPath(new URL('../src/api/__fixtures__/', import.meta.url));
      await mkdir(directory, { recursive: true });
      for (const [name, raw] of captured) await writeFile(`${directory}${name}.json`, `${JSON.stringify(raw, null, 2)}\n`);
    }
  } finally {
    await Promise.all(contexts.map((context) => context.close()));
    await api.dispose();
    await server.stop();
  }
});
