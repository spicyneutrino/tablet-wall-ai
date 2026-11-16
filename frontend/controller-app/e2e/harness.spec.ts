import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { z } from 'zod';
import { test, expect } from './fixtures';
import { imageColors } from './fixtures/fleet';

const image = fileURLToPath(new URL('./fixtures/images/two-colour.png', import.meta.url));
const flyer = fileURLToPath(new URL('./fixtures/images/EXLENT_Cohort_3_Flyer_Temp.png', import.meta.url));

test('real tablets join, display a wall image and paint the expected pixels', async ({
  server, api, tablets, tabletPixel, guard, page, writes,
}, testInfo) => {
  if (testInfo.config.workers > 1 && testInfo.config.metadata.checkWorkerPorts) {
    const recordSchema = z.object({ worker: z.number(), port: z.number() });
    let workers: z.infer<typeof recordSchema>[] = [];
    await expect.poll(async () => {
      const directory: string = testInfo.config.metadata.runDirectory;
      const files = await readdir(directory);
      workers = await Promise.all(files.map(async (file) => recordSchema.parse(JSON.parse(await readFile(join(directory, file), 'utf8')))));
      return new Set(workers.map((worker) => worker.worker)).size;
    }, { timeout: 10_000, message: 'Two Playwright workers must start isolated servers' }).toBeGreaterThanOrEqual(2);
    // Later workers start after earlier ones exit (per-file serverScope), so the OS may reuse a port; only the first batch runs at once.
    const concurrent = workers.filter((worker) => worker.worker < testInfo.config.workers);
    expect(new Set(concurrent.map((worker) => worker.port)).size).toBe(concurrent.length);
    console.log(`Worker ports ${JSON.stringify(workers)}`);
  }

  await guard(page);
  const recorded = writes(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  await expect(page.getByRole('status')).toHaveText('Live operator updates connected.');
  const fleet = await tablets(4);
  for (const tablet of fleet) {
    expect(await tablet.page.evaluate(() => localStorage.getItem('tablet-wall-device-id'))).toBe(tablet.id);
  }
  expect(new Set(fleet.map((tablet) => tablet.context)).size).toBe(4);
  await expect.poll(async () => {
    const config = await api.config();
    return fleet.map(({ id }) => config.runtime.devices[id]?.online);
  }, { timeout: 10_000 }).toEqual([true, true, true, true]);

  const withoutOrigin = await fetch(`${server.origin}/api/v3/scene`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json', 'If-Match': (await api.config()).etag },
    body: JSON.stringify({ content: { type: 'color' } }),
  });
  expect(withoutOrigin.status).toBe(403);
  const withoutEtag = await api.request.put('/api/v3/scene', { data: { content: { type: 'color' } } });
  expect(withoutEtag.status()).toBe(428);
  await api.placePhysical({ bounds: { x: 0, y: 0, width: 160, height: 90 }, slots: {} });
  await api.placeLogical({ columns: 2, rows: 2, deviceIds: fleet.map(({ id }) => id) });
  const asset = await api.upload(image);
  expect([asset.intrinsicWidth, asset.intrinsicHeight]).toEqual([1600, 900]);
  await api.scene({ type: 'image', asset: asset.id, fit: 'cover' });
  await expect.poll(async () => {
    const config = await api.config();
    return fleet.map(({ id }) => config.runtime.devices[id]?.render.state);
  }, { timeout: 10_000 }).toEqual(['displayed', 'displayed', 'displayed', 'displayed']);

  for (const [index, tablet] of fleet.entries()) {
    const centre = await tablet.page.locator('#surface').evaluate((canvas) => {
      if (!(canvas instanceof HTMLCanvasElement)) throw new Error('Tablet surface must be a canvas');
      return { x: canvas.width / 2, y: canvas.height / 2 };
    });
    const expected = index % 2 === 0 ? imageColors.left : imageColors.right;
    await expect.poll(async () => {
      const pixel = await tabletPixel(tablet, centre.x, centre.y);
      return Math.max(...expected.map((channel, channelIndex) => Math.abs(channel - (pixel[channelIndex] ?? -255))));
    }, { timeout: 10_000, message: `${tablet.id} must display ${expected.join(',')}` }).toBeLessThanOrEqual(30);
    const pixel = await tabletPixel(tablet, centre.x, centre.y);
    for (const [channelIndex, channel] of expected.entries()) {
      expect(Math.abs(channel - (pixel[channelIndex] ?? -255))).toBeLessThanOrEqual(30);
    }
    expect(pixel[3]).toBe(255);
    await tablet.page.screenshot({ path: testInfo.outputPath(`tablet-${index}.png`) });
  }
  expect(recorded).toEqual([]);
  const sceneStatus = await page.evaluate(async () => {
    const current = await fetch('/api/v3/config').then((response) => response.json());
    return (await fetch('/api/v3/scene', { method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'If-Match': current.etag },
      body: JSON.stringify({ content: { type: 'calibration' } }),
    })).status;
  });
  expect(sceneStatus).toBe(200);
  expect(recorded.map((request) => [request.method(), new URL(request.url()).pathname])).toEqual([['PUT', '/api/v3/scene']]);
  const uploadedFlyer = await api.upload(flyer);
  expect(uploadedFlyer.intrinsicWidth).toBeGreaterThan(0);
  console.log(`Worker ${testInfo.workerIndex} port ${server.port}: 4 online, 4 displayed, 4 centre pixels within ±30`);
});

test('accessibility helper checks the served controller and stageBox reads rendered geometry', async ({ server, page, axe, stageBox, guard }) => {
  await guard(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  const results = await axe(page);
  expect(results.violations).toEqual([]);
  await page.goto(`${server.origin}/controller/app-e2e/#stage-fixture`);
  await expect(page.getByRole('main', { name: 'Stage fixture' })).toBeAttached();
  const stage = page.locator('[data-stage="preview"]');
  const box = await stageBox(page);
  const rect = await stage.boundingBox();
  expect(box).toEqual(rect);
});
