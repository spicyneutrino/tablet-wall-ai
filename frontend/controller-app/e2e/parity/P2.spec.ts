import { mkdir, writeFile } from 'node:fs/promises';
import { crc32, deflateSync } from 'node:zlib';
import type { Request } from '@playwright/test';
import { expect, test } from '../fixtures';
import type { Tablet } from '../fixtures';

test.use({ serverScope: 'parity-P2' });

function solidPng(width: number, height: number, [red, green, blue]: readonly [number, number, number]) {
  const chunk = (type: string, data: Buffer) => {
    const body = Buffer.concat([Buffer.from(type), data]);
    const length = Buffer.alloc(4); length.writeUInt32BE(data.length);
    const check = Buffer.alloc(4); check.writeUInt32BE(crc32(body));
    return Buffer.concat([length, body, check]);
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0); header.writeUInt32BE(height, 4); header.set([8, 2, 0, 0, 0], 8);
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: width }, () => [red, green, blue]).flat())]);
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', header),
    chunk('IDAT', deflateSync(Buffer.concat(Array.from({ length: height }, () => row)))), chunk('IEND', Buffer.alloc(0))]);
}

const RED = [224, 48, 64] as const;
const BLUE = [32, 96, 224] as const;
const near = (pixel: number[], colour: readonly number[]) => Math.max(...colour.map((value, channel) => Math.abs(value - (pixel[channel] ?? -255)))) <= 24;

function post(request: Request) {
  const url = new URL(request.url());
  return { method: request.method(), path: url.pathname, ifMatch: request.headers()['if-match'] ?? null, body: request.postData() };
}

async function placeWall(api: Parameters<Parameters<typeof test>[2]>[0]['api'], fleet: Tablet[]) {
  for (const [index, tablet] of fleet.entries()) {
    const display = await api.request.put(`/api/v3/displays/${tablet.id}`, { headers: { 'If-Match': (await api.config()).etag }, data: {
      active_width_mm: 400, active_height_mm: 225, bezels: { left: 0, top: 0, right: 0, bottom: 0 },
      label: `Tablet ${index + 1}`, provenance: 'hand-derived' } });
    expect(display.ok(), await display.text()).toBe(true);
    const calibration = await api.request.put(`/api/v3/calibrations/${tablet.id}`, { headers: { 'If-Match': ((await display.json()) as { etag: string }).etag }, data: {
      profile_revision: 1, viewport_width: 800, viewport_height: 450, dpr: 1, orientation: 0, mode: 'tab', quarter_turn: 0,
      panel_offset_mm: [0, 0], mm_per_css: [0.5, 0.5], anchor_edge: 'top-left', uncertainty_mm: 0, method: 'hand-derived' } });
    expect(calibration.ok(), await calibration.text()).toBe(true);
  }
  const layout = await api.request.put('/api/v3/layout', { headers: { 'If-Match': (await api.config()).etag }, data: {
    bounds: { x: 0, y: 0, width: 860, height: 250 },
    slots: Object.fromEntries(fleet.map((tablet, index) => [tablet.id, { center_x_mm: 220 + 430 * index, center_y_mm: 125, mount_angle: 0,
      nudge_x_mm: 0, nudge_y_mm: 0, profile_revision: 1, calibration_revision: 1, participating: true }])) } });
  expect(layout.ok(), await layout.text()).toBe(true);
}

test('P2 Start (with policy and exclusions), Pause, Resume, Next, Previous, Retry and Stop each send the playback version. Status updates every 1 s only while visible', async ({
  server, api, tablets, tabletPixel, page, writes, guard, axe,
}, info) => {
  test.setTimeout(240_000);
  await mkdir('/tmp/U30-shots', { recursive: true });
  await guard(page, { allow: [/\/api\/v3\/playback\//] });
  const fleet = await tablets(2);
  await expect.poll(async () => { const config = await api.config(); return fleet.map(({ id }) => config.runtime.devices[id]?.online); }, { timeout: 15_000 }).toEqual([true, true]);
  await placeWall(api, fleet);

  const red = await api.upload(await save('red.png', solidPng(320, 180, RED)));
  const blue = await api.upload(await save('blue.png', solidPng(320, 180, BLUE)));
  async function save(name: string, bytes: Buffer) { const path = info.outputPath(name); await writeFile(path, bytes); return path; }
  const empty = (await (await api.request.get('/api/v3/playlist')).json()) as { etag: string };
  const seeded = await api.request.put('/api/v3/playlist', { headers: { 'If-Match': empty.etag },
    data: { items: [{ asset: red.id, dwell_ms: 3000 }, { asset: blue.id, dwell_ms: 3000 }], loop: true } });
  expect(seeded.ok(), await seeded.text()).toBe(true);

  const sent = writes(page);
  const reads: number[] = [];
  page.on('request', request => { if (request.method() === 'GET' && new URL(request.url()).pathname === '/api/v3/playback') reads.push(Date.now()); });
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: 'Server', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'Server', exact: true });
  await sheet.getByRole('tab', { name: 'Playback' }).click();
  await sheet.getByRole('switch', { name: /Playlist and playback/ }).check();
  const state = sheet.locator('.playback-head .state');
  await expect(state).toHaveText('Stopped');
  const start = sheet.getByRole('button', { name: 'Start', exact: true });
  await expect(start).toBeEnabled();
  await expect(sheet.getByRole('button', { name: 'Next item' })).toHaveAttribute('aria-disabled', 'true');

  await start.click();
  const dialog = page.getByRole('dialog', { name: 'Start playback' });
  await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused();
  await dialog.getByLabel('If a tablet is not ready').selectOption('online');
  const tablet2 = dialog.locator('.playback-tablet').nth(1);
  await tablet2.getByRole('switch').uncheck();
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const theme of ['light', 'dark']) {
    await page.evaluate(value => { localStorage.setItem('tablet-wall-theme', value); document.documentElement.dataset.theme = value; }, theme);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: `/tmp/U30-shots/start-${info.project.name}-${theme}.png` });
  }
  expect((await axe(page)).violations).toEqual([]);
  expect(sent).toEqual([]);
  await dialog.getByRole('button', { name: 'Start playback', exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(sheet).toBeVisible();
  await expect.poll(() => sent.length).toBe(1);
  const started = post(sent[0]!);
  expect(started).toMatchObject({ method: 'POST', path: '/api/v3/playback/start', ifMatch: null });
  const body = JSON.parse(started.body ?? 'null') as { policy: string; exclusions: string[] };
  expect(body.policy).toBe('online');
  expect(body.exclusions).toHaveLength(1);
  const excluded = body.exclusions[0];
  const shown = fleet.find(tablet => tablet.id !== excluded);
  if (!shown) throw new Error('One tablet must stay in the show.');

  await expect(state).toHaveText(/Playing|Preparing|Getting ready/);
  const centre = { x: 400, y: 225 };
  const colour = async () => tabletPixel(shown, centre.x, centre.y);
  await expect.poll(async () => near(await colour(), RED), { timeout: 20_000, message: 'first image reaches the wall' }).toBe(true);
  await expect.poll(async () => near(await colour(), BLUE), { timeout: 10_000, message: 'wall advances to the second image' }).toBe(true);
  await expect.poll(async () => near(await colour(), RED), { timeout: 10_000, message: 'wall loops back to the first image' }).toBe(true);
  await expect(state).toHaveText('Playing');
  await expect(sheet.getByText(/Showing item \d/)).toBeVisible();
  const status = async () => (await (await api.request.get('/api/v3/playback')).json()) as { state: string; version: string | number; excluded: string[]; policy: string };
  expect(await status()).toMatchObject({ excluded: [excluded], policy: 'online' });
  await page.screenshot({ path: `/tmp/U30-shots/playing-${info.project.name}-dark.png` });
  await page.evaluate(() => { localStorage.setItem('tablet-wall-theme', 'light'); document.documentElement.dataset.theme = 'light'; });
  await page.screenshot({ path: `/tmp/U30-shots/playing-${info.project.name}-light.png` });
  expect((await axe(page)).violations).toEqual([]);

  const gap = (list: number[]) => list.slice(1).map((time, index) => time - list[index]!);
  await expect.poll(() => reads.length, { timeout: 5_000 }).toBeGreaterThan(2);
  const count = reads.length; await page.waitForTimeout(3_200);
  expect(reads.length - count, 'status polls in 3.2 s while visible').toBeGreaterThanOrEqual(2);
  expect(reads.length - count).toBeLessThanOrEqual(5);
  expect(Math.max(...gap(reads.slice(-4)))).toBeLessThan(2_500);
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await page.waitForTimeout(1_200);
  const hidden = reads.length; await page.waitForTimeout(3_200);
  expect(reads.length - hidden, 'status polls while the page is hidden').toBe(0);
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(() => reads.length, { message: 'polling resumes at once when visible again' }).toBeGreaterThan(hidden);

  const transports = sent.length;
  await sheet.getByRole('button', { name: 'Pause', exact: true }).click();
  await expect(state).toHaveText('Paused');
  const sentSince = (name: string) => sent.slice(transports).find(request => request.url().endsWith(`/playback/${name}`));
  const pause = post(sentSince('pause')!);
  expect(pause).toMatchObject({ method: 'POST', path: '/api/v3/playback/pause', body: null });
  expect(pause.ifMatch).toMatch(/^\d+$/);
  const frozen = await colour();
  await page.waitForTimeout(2_500);
  expect(await colour(), 'a paused wall holds its image').toEqual(frozen);

  await sheet.getByRole('button', { name: 'Resume', exact: true }).click();
  await expect(state).toHaveText(/Playing|Preparing|Getting ready/);
  const resume = post(sentSince('start')!);
  expect(resume).toMatchObject({ method: 'POST', path: '/api/v3/playback/start', body: null });
  expect(resume.ifMatch).toMatch(/^\d+$/);
  await expect(state).toHaveText('Playing', { timeout: 15_000 });

  // The server bumps the playback version at every cut, and the app retries a stale write once. The forced 412
  // below uses that retry, so click Next just after a cut: the real retry then has most of a dwell before the next one.
  const before = (await status()).version;
  await expect.poll(async () => (await status()).version, { timeout: 15_000, message: 'a cut lands' }).not.toBe(before);
  let refuse = true;
  await page.route('**/api/v3/playback/next', async route => {
    if (refuse) { refuse = false; await route.fulfill({ status: 412, contentType: 'application/json', body: JSON.stringify({ detail: 'playback version is stale' }) }); } else await route.continue();
  });
  await sheet.getByRole('button', { name: 'Next item' }).click();
  await expect.poll(() => sent.filter(request => request.url().endsWith('/playback/next')).length).toBe(2);
  const nexts = sent.filter(request => request.url().endsWith('/playback/next')).map(post);
  expect(nexts.map(entry => entry.ifMatch)).toEqual([expect.stringMatching(/^\d+$/), expect.stringMatching(/^\d+$/)]);
  await page.unroute('**/api/v3/playback/next');
  await expect(sheet.getByRole('alert')).toHaveCount(0);
  await expect(state).toHaveText(/Playing|Preparing|Getting ready/);

  await sheet.getByRole('button', { name: 'Previous item' }).click();
  await expect.poll(() => sent.some(request => request.url().endsWith('/playback/previous'))).toBe(true);
  const previous = post(sent.find(request => request.url().endsWith('/playback/previous'))!);
  expect(previous.ifMatch).toMatch(/^\d+$/);

  await sheet.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(state).toHaveText('Stopped');
  const stop = post(sent.find(request => request.url().endsWith('/playback/stop'))!);
  expect(stop).toMatchObject({ method: 'POST', path: '/api/v3/playback/stop', body: null });
  expect(stop.ifMatch).toMatch(/^\d+$/);
  expect(await status()).toEqual({ state: 'stopped' });
  await expect(start).toBeEnabled();

  await fleet[1]!.context.close();
  await expect.poll(async () => (await api.config()).runtime.devices[fleet[1]!.id]?.online, { timeout: 15_000 }).toBe(false);
  await start.click();
  await dialog.getByLabel('If a tablet is not ready').selectOption('strict');
  await dialog.locator('.playback-tablet').nth(1).getByRole('switch').check();
  await dialog.getByRole('button', { name: 'Start playback', exact: true }).click();
  await expect(dialog).toBeHidden();
  const strict = post(sent.filter(request => request.url().endsWith('/playback/start')).at(-1)!);
  expect(strict.ifMatch).toBeNull();
  expect(JSON.parse(strict.body ?? 'null')).toEqual({ exclusions: [], policy: 'strict' });

  await expect(state).toHaveText('Blocked', { timeout: 50_000 });
  await expect(sheet.getByRole('alert').filter({ hasText: 'Playback is blocked' })).toBeVisible();
  await sheet.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect.poll(() => sent.some(request => request.url().endsWith('/playback/retry'))).toBe(true);
  const retry = post(sent.find(request => request.url().endsWith('/playback/retry'))!);
  expect(retry).toMatchObject({ method: 'POST', path: '/api/v3/playback/retry', body: null });
  expect(retry.ifMatch).toMatch(/^\d+$/);
  await sheet.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(state).toHaveText('Stopped');
});
