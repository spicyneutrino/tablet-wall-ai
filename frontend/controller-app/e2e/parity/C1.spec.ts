import { test, expect } from '../fixtures';
import { fileURLToPath } from 'node:url';
import { mkdir } from 'node:fs/promises';

const image = fileURLToPath(new URL('../fixtures/images/two-colour.png', import.meta.url));

test.use({ serverScope: 'parity-C1' });
test('C1 Selecting an image changes Preview only: 0 writes, On wall unchanged', async ({ server, api, tablets, page, writes, guard, axe }, info) => {
  await guard(page);
  const fleet = await tablets(4);
  await api.placeLogical({ columns: 2, rows: 2, deviceIds: fleet.map(tablet => tablet.id) });
  const asset = await api.upload(image);
  await api.scene({ type: 'calibration' });
  const before = await api.config();
  const recorded = writes(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  const live = page.locator('.desktop-onwall');
  const beforeLive = await live.locator('svg[aria-label="Wall preview"]').innerHTML();
  await page.getByRole('button', { name: 'two-colour.png', exact: true }).click();
  const preview = page.getByRole('region', { name: 'Preview', exact: true });
  await expect(preview.locator('[data-stage="preview"] image')).toHaveAttribute('href', /.+/);
  expect(await preview.locator('[data-stage="preview"] image').getAttribute('href')).toContain(asset.id.slice(7));
  await expect(preview).toContainText('two-colour.png, Fill');
  await expect(page.getByRole('button', { name: 'Show on wall', exact: true })).toBeEnabled();
  expect(await live.locator('svg[aria-label="Wall preview"]').innerHTML()).toBe(beforeLive);
  expect((await api.config()).etag).toBe(before.etag);
  expect(recorded).toEqual([]);
  await mkdir('/tmp/U16-shots', { recursive: true });
  for (const theme of ['light', 'dark']) {
    await page.evaluate(theme => {
      localStorage.setItem('tablet-wall-theme', theme);
      document.documentElement.dataset.theme = theme;
    }, theme);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: `/tmp/U16-shots/draft-${info.project.name}-${theme}.png`, fullPage: true });
    expect((await axe(page)).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.getByRole('button', { name: 'All images' }).click();
  const library = page.getByRole('dialog', { name: 'Library', exact: true });
  await library.getByRole('searchbox', { name: 'Search images' }).fill('not-in-the-library');
  await expect(library).toContainText('No images match');
  await library.getByRole('searchbox').fill('two-colour');
  await expect(library.getByRole('button', { name: 'two-colour.png', exact: true })).toBeVisible();
  for (const theme of ['light', 'dark']) {
    await page.evaluate(theme => { document.documentElement.dataset.theme = theme; }, theme);
    await page.screenshot({ path: `/tmp/U16-shots/library-${info.project.name}-${theme}.png`, fullPage: true });
  }
  expect((await axe(page)).violations).toEqual([]);
  await library.getByRole('button', { name: 'two-colour.png', exact: true }).click();
  await expect(library).not.toBeVisible();
  await page.getByRole('button', { name: 'Calibration grid', exact: true }).click();
  await expect(preview.locator('[data-stage="preview"] use[href$="-pattern"]')).toHaveCount(4);
  expect(recorded).toEqual([]);
  await page.getByRole('button', { name: 'two-colour.png', exact: true }).click();
  await expect(preview.locator('[data-stage="preview"] image')).toHaveCount(1);
  await page.getByRole('tab', { name: 'Tests', exact: true }).click();
  await page.getByRole('button', { name: 'Calibration grid', exact: true }).click();
  await expect(preview.locator('[data-stage="preview"] [data-preview-pattern="grid"]')).toHaveCount(1);
  await expect(preview.locator('[data-stage="preview"] image')).toHaveCount(0);
  await expect(preview.locator('[data-stage="preview"] use[href$="-pattern"]')).toHaveCount(4);
  await page.getByRole('button', { name: 'Black', exact: true }).click();
  await expect(preview.locator('[data-stage="preview"] [data-preview-pattern="grid"]')).toHaveCount(0);
  await expect(preview.locator('[data-stage="preview"] image')).toHaveCount(0);
  await expect(preview).toContainText('Black');
  expect((await api.config()).etag).toBe(before.etag);
  expect(recorded).toEqual([]);
});
