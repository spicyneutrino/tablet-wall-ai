import { fileURLToPath } from 'node:url';
import { test, expect } from '../fixtures';

const image = fileURLToPath(new URL('../fixtures/images/EXLENT_Cohort_3_Flyer_Temp.png', import.meta.url));

test.use({ serverScope: 'parity-D7' });
test('D7 First run: empty wall, then join card with QR and link, then arrange step, then show step, then the card disappears', async ({ page, server, api, tablets, guard, axe }) => {
  test.setTimeout(120_000);
  await guard(page);
  const asset = await api.upload(image);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });

  const firstRun = page.getByRole('region', { name: 'Next step: add your first tablet' });
  await expect(firstRun).toBeVisible();
  const qr = firstRun.locator('.join-code img');
  await expect(qr).toHaveAttribute('src', '/api/v3/join-qr');
  await expect.poll(() => qr.evaluate(element => element instanceof HTMLImageElement
    && element.complete && element.naturalWidth > 0)).toBe(true);
  const readiness = await api.request.get('/api/v3/readiness');
  expect(readiness.ok(), await readiness.text()).toBe(true);
  const tabletUrl = (await readiness.json()).tablet_url;
  if (typeof tabletUrl !== 'string') throw new Error('The server must expose a tablet URL.');
  const link = firstRun.getByRole('link', { name: new URL(tabletUrl).host });
  await expect(link).toHaveAttribute('href', tabletUrl);
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
  await firstRun.getByRole('button', { name: 'Copy link' }).click();
  await expect(firstRun.getByText('Link copied.')).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(tabletUrl);
  expect((await axe(page)).violations).toEqual([]);

  const fleet = await tablets(3);
  await expect(page.locator('#tablet-health .row')).toHaveCount(3, { timeout: 10_000 });
  await expect(firstRun).toHaveCount(0, { timeout: 10_000 });
  const arrange = page.getByRole('region', { name: 'Next step: arrange the tablets' });
  await expect(arrange).toBeVisible({ timeout: 10_000 });
  const tabs = page.getByRole('tablist', { name: 'Source type' });
  await arrange.getByRole('button', { name: 'Arrange tablets' }).click();
  await expect(tabs.getByRole('tab', { name: 'Layouts', exact: true })).toHaveAttribute('aria-selected', 'true');

  await api.placeLogical({ columns: 3, rows: 1, deviceIds: fleet.map(tablet => tablet.id) });
  await expect(arrange).toHaveCount(0, { timeout: 10_000 });
  const show = page.getByRole('region', { name: 'Next step: show an image' });
  await expect(show).toBeVisible({ timeout: 10_000 });
  await show.getByRole('button', { name: 'Choose an image' }).click();
  await expect(tabs.getByRole('tab', { name: 'Images', exact: true })).toHaveAttribute('aria-selected', 'true');

  await page.getByRole('button', { name: 'EXLENT_Cohort_3_Flyer_Temp.png', exact: true }).click();
  await expect(show).toBeVisible();
  await page.getByRole('button', { name: 'Show on wall', exact: true }).click();
  await expect(show).toHaveCount(0, { timeout: 10_000 });
  await expect(page.getByRole('heading', { name: /^Next step:/ })).toHaveCount(0);
  expect((await api.config()).scene).toMatchObject({ content: { type: 'image', asset: asset.id } });
  expect((await axe(page)).violations).toEqual([]);
});
