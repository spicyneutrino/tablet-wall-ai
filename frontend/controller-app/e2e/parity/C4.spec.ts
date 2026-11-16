import { test, expect } from '../fixtures';
import { fileURLToPath } from 'node:url';
import { mkdir } from 'node:fs/promises';
import { ConfigSchema } from '../../src/api/config';
import { fitTransform } from '../../src/domain/layout';

const image = fileURLToPath(new URL('../fixtures/images/two-colour.png', import.meta.url));

test.use({ serverScope: 'parity-C4' });
test('C4 Fill and Fit, and the background colour, reach the tablets (pixel check). The crop text matches `fitTransform`', async ({ server, api, tablets, page, writes, tabletPixel, guard, axe }, info) => {
  await guard(page);
  await mkdir('/tmp/U16-shots', { recursive: true });
  const [tablet] = await tablets(1, { viewport: { width: 800, height: 800 } });
  if (!tablet) throw new Error('Expected tablet');
  await api.placeLogical({ columns: 1, rows: 1, cellWidth: 800, cellHeight: 800, deviceIds: [tablet.id] });
  await api.upload(image);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  const recorded = writes(page);
  const preview = page.getByRole('region', { name: 'Preview', exact: true });
  for (const fit of ['cover', 'contain'] as const) {
    await page.getByRole('button', { name: 'two-colour.png', exact: true }).click();
    await page.getByRole('button', { name: /Fit and crop/ }).click();
    const sheet = page.getByRole('dialog', { name: 'Fit and crop', exact: true });
    await sheet.getByRole('radio', { name: fit === 'cover' ? 'Fill' : 'Fit', exact: true }).click();
    await sheet.getByLabel('Background', { exact: true }).fill('#123456');
    const config = ConfigSchema.parse(await api.config());
    const transform = fitTransform(config.layout, { intrinsicWidth: 1600, intrinsicHeight: 900, fit });
    if (!transform) throw new Error('Expected image transform');
    const width = config.layout.kind === 'physical' ? config.layout.bounds.width : config.layout.width;
    const height = config.layout.kind === 'physical' ? config.layout.bounds.height : config.layout.height;
    const cropX = fit === 'contain' ? 1 - transform.width / width : transform.cropX;
    const cropY = fit === 'contain' ? 1 - transform.height / height : transform.cropY;
    await expect(sheet.locator('[data-crop-summary]')).toHaveText(`${(cropX * 100).toFixed(1)}% ${fit === 'contain' ? 'of wall width uncovered' : 'of source width cropped'}; ${(cropY * 100).toFixed(1)}% ${fit === 'contain' ? 'of wall height uncovered' : 'of source height cropped'}.`);
    await expect(preview.locator('[data-stage="preview"] image')).toHaveAttribute('width', String(transform.width));
    await expect(preview.locator('[data-stage="preview"] image')).toHaveAttribute('height', String(transform.height));
    expect(recorded).toHaveLength(fit === 'cover' ? 0 : 1);
    for (const theme of ['light', 'dark']) {
      await page.evaluate(theme => { document.documentElement.dataset.theme = theme; }, theme);
      expect((await axe(page)).violations).toEqual([]);
      await page.screenshot({ path: `/tmp/U16-shots/fit-${fit}-${info.project.name}-${theme}.png`, fullPage: true });
    }
    await sheet.getByRole('button', { name: 'Close Fit and crop', exact: true }).click();
    await page.getByRole('button', { name: 'Show on wall', exact: true }).click();
    await expect.poll(async () => (await api.config()).runtime.devices[tablet.id]?.render.state, { timeout: 10_000 }).toBe('displayed');
    const size = await tablet.page.locator('#surface').evaluate(canvas => {
      if (!(canvas instanceof HTMLCanvasElement)) throw new Error('Expected tablet canvas');
      return { w: canvas.width, h: canvas.height };
    });
    for (const sample of [
      { x: size.w / 4, y: size.h / 2, color: [224, 48, 64] },
      { x: size.w * 3 / 4, y: size.h / 2, color: [32, 160, 224] },
      { x: size.w / 4, y: 5, color: fit === 'contain' ? [18, 52, 86] : [224, 48, 64] },
    ]) {
      await expect.poll(async () => Math.max(...(await tabletPixel(tablet, sample.x, sample.y)).slice(0, 3)
        .map((value, channel) => Math.abs(value - (sample.color[channel] ?? 0))))).toBeLessThanOrEqual(30);
    }
  }
  expect(recorded).toHaveLength(2);
  expect(recorded.map(request => request.postDataJSON().content.fit)).toEqual(['cover', 'contain']);
});
