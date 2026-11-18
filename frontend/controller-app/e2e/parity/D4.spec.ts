import { spawn } from 'node:child_process';
import type { ChildProcess } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, rm } from 'node:fs/promises';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';
import { test, expect } from '../fixtures';
import { fleet } from '../fixtures/fleet';

test.use({ serverScope: 'parity-D4' });

async function freePort() {
  const listener = createServer();
  listener.listen(0, '127.0.0.1');
  await once(listener, 'listening');
  const address = listener.address();
  if (!address || typeof address === 'string') throw new Error('Missing port');
  await new Promise<void>(resolve => listener.close(() => resolve()));
  return address.port;
}

async function wall(port: number) {
  const origin = `http://127.0.0.1:${port}`;
  const directory = await mkdtemp(join(tmpdir(), 'tablet-wall-d4-'));
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('TABLET_WALL_') && !key.startsWith('WALL_')));
  Object.assign(env, { TABLET_WALL_DB: join(directory, 'wall.db'), TABLET_WALL_ASSET_DIR: join(directory, 'assets'),
    TABLET_WALL_MEDIA_DIR: join(directory, 'media'), TABLET_WALL_BACKUP_DIR: join(directory, 'backups'),
    TABLET_WALL_TABLET_ORIGIN: origin, TABLET_WALL_OPERATOR_ORIGIN: origin, TABLET_WALL_UPLOAD_MODE: 'loopback', TABLET_WALL_WIFI_NAME: 'QA' });
  let child: ChildProcess | null = null;
  async function stop() {
    const running = child;
    child = null;
    if (!running?.pid || running.exitCode !== null) return;
    const exited = once(running, 'exit');
    process.kill(-running.pid, 'SIGTERM');
    if (!await Promise.race([exited.then(() => true), delay(5_000).then(() => false)])) { process.kill(-running.pid, 'SIGKILL'); await exited; }
  }
  async function start() {
    child = spawn('uv', ['run', 'fastapi', 'run', 'main.py', '--host', '127.0.0.1', '--port', String(port)], {
      cwd: fileURLToPath(new URL('../../../../', import.meta.url)), env, detached: true, stdio: 'ignore' });
    await expect.poll(() => fetch(`${origin}/healthz`, { signal: AbortSignal.timeout(500) }).then(r => r.status).catch(() => 0),
      { timeout: 20_000 }).toBe(200);
  }
  return { origin, start, stop, dispose: async () => { await stop(); await rm(directory, { recursive: true, force: true }); } };
}

const box = { left: 0, right: 0, top: 0, bottom: 0 };
const logical = (id: string, width: number) => ({ width, height: 450,
  placements: { [id]: { device_id: id, x: 0, y: 0, w: width, h: 450, bezel: box } }, sizing: { mode: 'fixed', padding: 0 } });

test('D4 Server restart (new generation): the new snapshot is adopted, drafts are kept, and a conflict is raised if the layout changed', async ({ page, browser, playwright }) => {
  test.setTimeout(150_000);
  const port = await freePort();
  const before = await wall(port), after = await wall(port);
  const context = await browser.newContext({ viewport: { width: 800, height: 450 } });
  const pageErrors: string[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  try {
    await before.start();
    const api = await playwright.request.newContext({ baseURL: before.origin, extraHTTPHeaders: { Origin: before.origin } });
    const id = fleet[0].id;
    await context.addInitScript(value => localStorage.setItem('tablet-wall-device-id', value), id);
    await (await context.newPage()).goto(`${before.origin}/client/`);
    const read = async () => await (await api.get('/api/v3/config')).json() as { etag: string; generation: string; layout: { width: number }; runtime: { devices: object } };
    const place = async (width: number) => expect((await api.put('/api/v3/logical-layout', { headers: { 'If-Match': (await read()).etag }, data: logical(id, width) })).ok()).toBe(true);
    const save = async (name: string) => expect((await api.put(`/api/v3/logical-layouts/${name}`, { headers: { 'If-Match': (await read()).etag } })).ok()).toBe(true);
    await expect.poll(async () => Object.keys((await read()).runtime.devices).length).toBe(1);
    await place(1200); await save('Draft');
    await place(800);
    const generation = (await read()).generation;

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`${before.origin}/controller/app/`, { waitUntil: 'networkidle' });
    await page.getByRole('tab', { name: 'Layouts', exact: true }).click();
    await page.getByRole('button', { name: 'Draft', exact: true }).click();
    const apply = page.getByRole('button', { name: 'Apply layout', exact: true });
    await expect(apply).toBeEnabled();
    const width = (stage: 'preview' | 'onwall') => page.locator(`[data-stage="${stage}"] svg`).first()
      .evaluate(svg => svg instanceof SVGSVGElement ? svg.viewBox.baseVal.width : 0);
    const draftWidth = await width('preview');
    const oldWall = await width('onwall');
    expect(draftWidth).toBeGreaterThan(oldWall);

    await before.stop();
    await expect(page.getByRole('heading', { name: 'Next step: wait for the server' })).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('[data-stage="preview"]')).toHaveClass(/is-draft/);

    await after.start();
    const next = await playwright.request.newContext({ baseURL: after.origin, extraHTTPHeaders: { Origin: after.origin } });
    await expect.poll(async () => Object.keys(((await (await next.get('/api/v3/config')).json()) as { runtime: { devices: object } }).runtime.devices).length,
      { timeout: 30_000 }).toBe(1);
    const fresh = await (await next.get('/api/v3/config')).json() as { etag: string; generation: string };
    expect(fresh.generation).not.toBe(generation);
    expect((await next.put('/api/v3/logical-layout', { headers: { 'If-Match': fresh.etag }, data: logical(id, 1000) })).ok()).toBe(true);

    const banner = page.locator('#conflict');
    await expect(page.getByRole('heading', { name: 'Next step: wait for the server' })).toHaveCount(0, { timeout: 30_000 });
    await expect(banner).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-stage="preview"]')).toHaveClass(/is-draft/);
    expect(await width('preview')).toBe(draftWidth);
    expect(await width('onwall')).toBeGreaterThan(oldWall);
    expect(await width('onwall')).toBeLessThan(draftWidth);
    await expect(apply).toBeDisabled();
    await expect(page.getByText('Review the change first.')).toBeVisible();
    await banner.getByRole('button', { name: 'Keep mine', exact: true }).click();
    await expect(banner).toHaveCount(0);
    await expect(apply).toBeEnabled();
    expect(pageErrors).toEqual([]);
    await next.dispose(); await api.dispose();
  } finally { await context.close(); await before.dispose(); await after.dispose(); }
});
