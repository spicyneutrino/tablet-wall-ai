import { test, expect } from '../fixtures';
import { fileURLToPath } from 'node:url';
import { readdir, unlink } from 'node:fs/promises';
import { join } from 'node:path';

const image = fileURLToPath(new URL('../fixtures/images/two-colour.png', import.meta.url));

test.use({ serverScope: 'parity-C10' });
test('C10 A missing applied image keeps the geometry, shows the image as unavailable on both monitors, and recovers through Add image, Preview and Show', async ({ server, api, tablets, page, writes, tabletPixel }) => {
  const [tablet] = await tablets(1);
  if (!tablet) throw new Error('Expected tablet');
  await api.placeLogical({ columns: 1, rows: 1, deviceIds: [tablet.id] });
  const asset = await api.upload(image);
  await api.scene({ type: 'image', asset: asset.id, fit: 'cover' });
  await expect.poll(async () => (await api.config()).runtime.devices[tablet.id]?.render.state, { timeout: 10_000 }).toBe('displayed');
  const before = await api.config();
  async function removeObject(directory: string): Promise<void> {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) await removeObject(path);
      else if (entry.name.includes(asset.id.slice(7))) await unlink(path);
    }
  }
  await removeObject(join(server.directory, 'media'));
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  const recorded = writes(page);
  const preview = page.getByRole('region', { name: 'Preview', exact: true });
  const live = page.locator('.desktop-onwall');
  await expect(preview).toContainText('Image unavailable');
  await expect(live).toContainText('Image unavailable');
  expect((await api.config()).layout).toEqual(before.layout);
  await expect(preview.locator('[data-stage="preview"] [data-screen]')).toHaveCount(1);
  await api.upload(image);
  await page.getByRole('button', { name: 'All images' }).click();
  const sheet = page.getByRole('dialog', { name: 'Library', exact: true });
  await sheet.getByRole('button', { name: 'Refresh images' }).click();
  await sheet.getByRole('button', { name: 'two-colour.png', exact: true }).click();
  await expect(preview).toContainText('two-colour.png, Fill');
  await expect(live).toContainText('Image unavailable');
  expect(recorded).toEqual([]);
  await page.getByRole('button', { name: 'Show on wall', exact: true }).click();
  await expect(live).toContainText('two-colour.png, Fill');
  await expect.poll(async () => (await api.config()).runtime.devices[tablet.id]?.render.state, { timeout: 10_000 }).toBe('displayed');
  await expect.poll(async () => Math.max(...(await tabletPixel(tablet, 100, 100)).slice(0, 3)
    .map((value, channel) => Math.abs(value - ([224, 48, 64][channel] ?? 0))))).toBeLessThanOrEqual(30);
  expect((await api.config()).layout).toEqual(before.layout);
  expect(recorded.map(request => new URL(request.url()).pathname)).toEqual(['/api/v3/scene']);
});
