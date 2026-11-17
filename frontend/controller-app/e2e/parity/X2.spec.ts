import { fileURLToPath } from 'node:url';
import type { Page } from '@playwright/test';
import { test, expect } from '../fixtures';

const firstImage = fileURLToPath(new URL('../fixtures/images/EXLENT_Cohort_3_Flyer_Temp.png', import.meta.url));
const themes = ['light', 'dark'] as const;
type Theme = typeof themes[number];

async function setTheme(page: Page, theme: Theme) {
  const toggle = page.getByRole('button', { name: /^Theme:/ });
  for (let step = 0; step < 3 && await toggle.getAttribute('aria-label') !== `Theme: ${theme}`; step++) await toggle.click();
  await expect(toggle).toHaveAttribute('aria-label', `Theme: ${theme}`);
}

test.use({ serverScope: 'parity-X2' });
test('X2 axe reports 0 violations, for every state, at 390, 820 and 1440, in light and dark', async ({ server, api, tablets, page, guard, axe }, info) => {
  test.setTimeout(300_000);
  const viewport = info.project.use.viewport;
  if (!viewport) throw new Error('X2 requires an explicit viewport.');
  const width = viewport.width;
  await guard(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });

  async function audit(state: string) {
    for (const theme of themes) {
      await setTheme(page, theme);
      await page.evaluate(() => document.fonts.ready);
      const results = await axe(page);
      expect(results.violations, `${state}/${width}/${theme} axe violations`).toEqual([]);
    }
  }

  await expect(page.getByRole('region', { name: 'Next step: add your first tablet' })).toBeVisible();
  await audit('firstrun');

  const fleet = await tablets(4, { viewport: { width: 400, height: 300 } });
  await expect.poll(async () => Object.values((await api.config()).runtime.devices).filter(device => device.online).length).toBe(4);
  await api.placeLogical({ columns: 2, rows: 2, deviceIds: fleet.map(tablet => tablet.id) });
  const asset = await api.upload(firstImage);
  await api.scene({ type: 'image', asset: asset.id, fit: 'cover' });
  await expect(page.locator('[data-stage="preview"] [data-screen]')).toHaveCount(4);
  await expect(page.getByRole('button', { name: /4 of 4/ })).toBeVisible();
  await audit('main');

  const target = fleet[1]!;
  const screen = page.locator(`[data-stage="preview"] [data-screen="${target.id}"]`);
  const box = await screen.boundingBox();
  if (!box) throw new Error('The tablet screen must be visible for the selected state.');
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect(page.locator('[data-stage="preview"] [data-selected="true"]')).toHaveCount(1);
  await audit('selected');

  await page.getByRole('button', { name: 'Edit layout', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Edit layout', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await audit('arrange');
  await page.getByRole('button', { name: 'Edit layout', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Edit layout', exact: true })).toHaveAttribute('aria-pressed', 'false');

  await page.getByRole('button', { name: 'Measure…', exact: true }).click();
  await expect(page.getByRole('heading', { name: /^Measure Tablet/ })).toBeVisible();
  await expect(page.getByLabel('Which model is it?', { exact: true })).toBeVisible();
  await audit('measure');
  await page.locator('.measure-back').click();
  await expect(page.getByRole('heading', { name: /^Measure Tablet/ })).toHaveCount(0);

  await fleet[3]!.context.close();
  await expect(page.locator('#tablet-health .state-warn')).toHaveCount(1);
  await expect(page.locator('[data-stage="preview"] [data-status="offline"]')).toHaveCount(1);
  await audit('offline');

  for (const theme of themes) {
    await setTheme(page, theme);
    await page.getByRole('button', { name: 'Server', exact: true }).click();
    const serverSheet = page.getByRole('dialog', { name: 'Server', exact: true });
    await expect(serverSheet).toBeVisible();
    const results = await axe(page);
    expect(results.violations, `server/${width}/${theme} axe violations`).toEqual([]);
    await page.keyboard.press('Escape');
    await expect(serverSheet).toHaveCount(0);
  }

  for (const theme of themes) {
    await setTheme(page, theme);
    await page.getByRole('button', { name: 'All images' }).click();
    const librarySheet = page.getByRole('dialog', { name: 'Library', exact: true });
    await expect(librarySheet).toBeVisible();
    const results = await axe(page);
    expect(results.violations, `library/${width}/${theme} axe violations`).toEqual([]);
    await page.keyboard.press('Escape');
    await expect(librarySheet).toHaveCount(0);
  }
});
