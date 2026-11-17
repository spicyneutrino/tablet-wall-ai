import { fileURLToPath } from 'node:url';
import { z } from 'zod';
import { test, expect } from './fixtures';
import { imageColors } from './fixtures/fleet';
import { walls } from './fixtures/walls';

const source = fileURLToPath(new URL('./fixtures/images/two-colour.png', import.meta.url));
const colours = { ...imageColors, background: [16, 32, 48] };

test.describe('independent screen geometry and visible image pixels at 1440x900', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  for (const fixture of walls) {
    test(fixture.name, async ({ server, api, page, guard, writes, axe }, testInfo) => {
      await guard(page);
      const requests = writes(page);
      const failed: string[] = [];
      page.on('requestfailed', (request) => failed.push(request.url()));
      page.on('response', (response) => { if (response.status() >= 400) failed.push(`${response.status()} ${response.url()}`); });
      const asset = await api.upload(source);
      const config = await api.scene({ type: 'image', asset: asset.id, fit: 'cover' });
      const { scene: { content: { url } } } = z.object({ scene: z.object({ content: z.object({ url: z.string() }) }) }).parse(config);
      for (const fit of ['cover', 'contain'] as const) {
        const query = new URLSearchParams({ wall: fixture.name, image: url, fit });
        await page.goto(`${server.origin}/controller/app-e2e/?${query}#stage-fixture`, { waitUntil: 'networkidle' });
        await page.evaluate(() => document.fonts.ready);
        const svg = page.getByRole('group', { name: 'Wall preview' });
        const box = await svg.boundingBox();
        expect(box).not.toBeNull();
        if (!box) throw new Error('Wall SVG must have a client rectangle');
        const wall = fixture.layout.kind === 'physical' ? fixture.layout.bounds :
          { x: 0, y: 0, width: fixture.layout.width, height: fixture.layout.height };
        const margin = wall.width / 70;
        const viewWidth = wall.width + margin * 2, viewHeight = wall.height + margin * 2;
        const scale = Math.min(box.width / viewWidth, box.height / viewHeight);
        const originX = box.x + (box.width - viewWidth * scale) / 2 - (wall.x - margin) * scale;
        const originY = box.y + (box.height - viewHeight * scale) / 2 - (wall.y - margin) * scale;
        expect(await svg.locator('[data-screen]').count()).toBe(Object.keys(fixture.screens).length);
        // The label size follows the measured stage width, which settles one ResizeObserver frame after layout.
        await expect.poll(async () => {
          const sizes = await svg.locator('[data-tablet-label]').evaluateAll((labels) => labels.map((label) => {
            if (!(label instanceof SVGGraphicsElement)) throw new Error('Tablet label must be SVG');
            const matrix = label.getScreenCTM();
            if (!matrix) throw new Error('Visible label must have a screen transform');
            return Number(label.getAttribute('font-size')) * Math.hypot(matrix.a, matrix.b);
          }));
          return Math.max(...sizes.map((size) => Math.abs(size - 16)));
        }, { message: 'Labels stay 16px through wall scale and rotation' }).toBeLessThan(0.01);
        const points: { id: string; x: number; y: number; expected: readonly number[] }[] = [];
        for (const [id, screen] of Object.entries(fixture.screens)) {
          const expected = { x: originX + screen.x * scale, y: originY + screen.y * scale,
            width: screen.width * scale, height: screen.height * scale };
          const actual = await svg.locator(`[data-screen="${id}"]`).boundingBox();
          expect(actual).not.toBeNull();
          if (!actual) throw new Error(`Missing screen ${id}`);
          for (const key of ['x', 'y', 'width', 'height'] as const) {
            expect(Math.abs(actual[key] - expected[key]), `${fixture.name}/${id}/${key} within 0.5px`).toBeLessThanOrEqual(0.5);
          }
          points.push({ id, x: expected.x + expected.width / 2, y: expected.y + expected.height / 2, expected: colours[screen[fit]] });
        }
        if (fixture.name === 'missing-profile') await expect(svg.getByText(/Missing profile/)).toBeVisible();
        const screenshot = testInfo.outputPath(`${fixture.name}-${fit}-1440x900.png`);
        const png = await page.screenshot({ path: screenshot, animations: 'disabled' });
        const pixels = await page.evaluate(async ({ bytes, points }) => {
          const bitmap = await createImageBitmap(new Blob([new Uint8Array(bytes)], { type: 'image/png' }));
          const canvas = document.createElement('canvas');
          canvas.width = bitmap.width; canvas.height = bitmap.height;
          const context = canvas.getContext('2d');
          if (!context) throw new Error('Screenshot sampler needs a canvas context');
          context.drawImage(bitmap, 0, 0); bitmap.close();
          return points.map((point) => [...context.getImageData(Math.floor(point.x), Math.floor(point.y), 1, 1).data]);
        }, { bytes: [...png], points });
        for (const [index, point] of points.entries()) {
          for (const [channel, expected] of point.expected.entries()) {
            expect(Math.abs((pixels[index]?.[channel] ?? -255) - expected), `${point.id} ${fit} visible centre pixel`).toBeLessThanOrEqual(30);
          }
        }
        expect((await axe(page)).violations).toEqual([]);
        console.log(`${fixture.name} ${fit}: ${points.length} screen rects within 0.5px, ${points.length} centre pixels within ±30; ${screenshot}`);
      }
      expect(requests).toEqual([]);
      expect(failed).toEqual([]);
    });
  }
});

test('stage budget survives modes, selection, offline overlays and alerts at each viewport', async ({ server, page, stageBox, guard }) => {
  await guard(page);
  await page.goto(`${server.origin}/controller/app-e2e/#stage-fixture`, { waitUntil: 'networkidle' });
  const before = await stageBox(page);
  for (const change of [
    () => page.getByRole('button', { name: 'Toggle selection' }).click(),
    () => page.getByRole('button', { name: 'Toggle alert' }).click(),
    () => page.getByRole('button', { name: 'Preview', exact: true }).click(),
    () => page.getByRole('combobox', { name: 'Status', exact: true }).selectOption('offline'),
  ]) {
    await change();
    const after = await stageBox(page);
    for (const key of ['x', 'y', 'width', 'height'] as const) expect(Math.abs(after[key] - before[key])).toBeLessThanOrEqual(0.02);
  }
  await expect(page.getByRole('group', { name: 'Wall preview' }).getByRole('button')).toHaveCount(0);
  const stage = page.locator('[data-stage="preview"]');
  await stage.evaluate((element) => { element.style.display = 'none'; });
  await expect(stage).toBeHidden();
  await page.getByRole('button', { name: 'Toggle selection' }).click();
  await stage.evaluate((element) => { element.style.display = 'grid'; });
  await expect(stage).toBeVisible();
  const restored = await stageBox(page);
  for (const key of ['x', 'y', 'width', 'height'] as const) expect(Math.abs(restored[key] - before[key])).toBeLessThanOrEqual(0.02);
  await expect(page.locator('[data-tablet-label]').first()).toHaveText('1');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: test.info().outputPath(`offline-${page.viewportSize()?.width}.png`), animations: 'disabled' });
  console.log(`Stable stage budget at ${page.viewportSize()?.width}x${page.viewportSize()?.height}: drift ≤0.02px`);
});
