import { spawn } from 'node:child_process';
import type { ChildProcess } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';
import { test, expect } from '../fixtures';
import { fleet } from '../fixtures/fleet';

test.use({ serverScope: 'parity-D5' });

const image = fileURLToPath(new URL('../fixtures/images/two-colour.png', import.meta.url));

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
  const directory = await mkdtemp(join(tmpdir(), 'tablet-wall-d5-'));
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

test('D5 Server stopped: On wall says "Server unreachable", every write control is disabled with that reason, and the page recovers on restart', async ({ page, browser, playwright, axe }) => {
  test.setTimeout(120_000);
  const server = await wall(await freePort());
  const context = await browser.newContext({ viewport: { width: 800, height: 450 } });
  const pageErrors: string[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  try {
    await server.start();
    const api = await playwright.request.newContext({ baseURL: server.origin, extraHTTPHeaders: { Origin: server.origin } });
    const id = fleet[0].id;
    await context.addInitScript(value => localStorage.setItem('tablet-wall-device-id', value), id);
    const tablet = await context.newPage();
    await tablet.goto(`${server.origin}/client/`);
    const read = async () => await (await api.get('/api/v3/config')).json() as { etag: string; runtime: { devices: object } };
    await expect.poll(async () => Object.keys((await read()).runtime.devices).length).toBe(1);
    expect((await api.put('/api/v3/logical-layout', { headers: { 'If-Match': (await read()).etag }, data: { width: 800, height: 450,
      placements: { [id]: { device_id: id, x: 0, y: 0, w: 800, h: 450, bezel: { left: 0, right: 0, top: 0, bottom: 0 } } },
      sizing: { mode: 'fixed', padding: 0 } } })).ok()).toBe(true);
    expect((await api.post('/uploads?name=two-colour.png', { data: await readFile(image), headers: { 'Content-Type': 'image/png' } })).status()).toBe(201);

    const writes: string[] = [];
    page.on('request', request => { if (request.method() !== 'GET') writes.push(`${request.method()} ${new URL(request.url()).pathname}`); });
    await page.addInitScript(() => localStorage.setItem('tablet-wall-playback', 'on'));
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: 'two-colour.png', exact: true }).click();
    const show = page.getByRole('button', { name: 'Show on wall', exact: true });
    await expect(show).toBeEnabled();

    await server.stop();
    await expect(page.getByRole('heading', { name: 'Next step: wait for the server' })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('button', { name: /^Server unreachable/ })).toBeVisible();
    await expect(page.locator('.desktop-onwall')).toContainText(/Unknown since \d{2}:\d{2}/);
    await expect(show).toBeDisabled();
    await expect(show).toHaveAccessibleDescription('The server can’t be reached.');
    await expect(page.getByRole('button', { name: 'Edit layout', exact: true })).toHaveCount(0);
    for (const name of ['Images', 'Saved', 'Layouts', 'Tests']) await expect(page.getByRole('tab', { name, exact: true })).toBeDisabled();
    for (const name of ['Upload…', 'Library…', 'two-colour.png']) await expect(page.getByRole('button', { name, exact: true })).toBeDisabled();
    await expect(page.getByText('The server can’t be reached.')).toBeVisible();
    expect((await axe(page)).violations).toEqual([]);

    await page.locator('#tablet-health .row').first().click();
    for (const name of ['Measure…', 'Identify', 'Retry image', 'Reconnect', 'Save', 'Save model']) {
      await expect(page.getByRole('button', { name, exact: true }), name).toBeDisabled();
    }
    for (const name of ['Identify', 'Retry image', 'Reconnect']) {
      await expect(page.getByRole('button', { name, exact: true })).toHaveAccessibleDescription('The server can’t be reached.');
    }
    await page.getByRole('button', { name: 'Server', exact: true }).click();
    const sheet = page.getByRole('dialog', { name: 'Server' });
    await sheet.getByRole('tab', { name: 'Backup and reset' }).click();
    await expect(sheet.getByRole('button', { name: 'Clear wall…', exact: true })).toBeDisabled();
    await expect(sheet.getByRole('button', { name: 'Clear wall…', exact: true })).toHaveAccessibleDescription('The server can’t be reached.');
    await sheet.getByRole('tab', { name: 'Playback' }).click();
    await expect(sheet.getByText('The server can’t be reached. Playlist and playback controls are paused.')).toBeVisible();
    await expect(sheet.locator('[data-mount="playback"] button:enabled')).toHaveCount(0);
    expect((await axe(page)).violations).toEqual([]);
    await sheet.getByRole('button', { name: 'Close Server' }).click();
    expect(writes).toEqual([]);

    await server.start();
    await expect(page.getByRole('heading', { name: 'Next step: wait for the server' })).toHaveCount(0, { timeout: 30_000 });
    await expect(page.getByRole('button', { name: /^Server unreachable/ })).toHaveCount(0);
    await expect(page.getByRole('tab', { name: 'Saved', exact: true })).toBeEnabled();
    await expect(page.locator('.desktop-onwall')).not.toContainText('Unknown since');
    await expect(page.locator('[data-stage="preview"]')).toHaveClass(/is-draft/);
    const banner = page.locator('#conflict');
    await expect(banner).toBeVisible();
    await expect(show).toBeDisabled();
    await expect(show).toHaveAccessibleDescription('Review the change first.');
    await banner.getByRole('button', { name: 'Keep mine', exact: true }).click();
    await expect(banner).toHaveCount(0);
    await expect(show).toBeEnabled();
    expect(writes).toEqual([]);
    expect(pageErrors).toEqual([]);
    await api.dispose();
  } finally { await context.close(); await server.dispose(); }
});
