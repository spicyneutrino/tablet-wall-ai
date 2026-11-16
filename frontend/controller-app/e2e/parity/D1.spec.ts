import { test, expect } from '../fixtures';

test.use({ serverScope: 'parity-D1' });
test('D1 A tablet that opens `/client/` appears on the board within 2 s, and the setup step advances', async ({ page, server, tablets, guard, axe }) => {
  await guard(page);
  await page.goto(`${server.origin}/controller/app/`);
  await expect(page.getByRole('heading', { name: 'Next step: add your first tablet' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Tablets', exact: true })).toBeVisible();
  const [tablet] = await tablets(1);
  if (!tablet) throw new Error('Expected one joined tablet.');
  const row = page.locator(`#tablet-row-${tablet.id}`);
  await expect(row).toBeVisible({ timeout: 2000 });
  await expect(row).toContainText('Not placed');
  await expect(page.getByRole('heading', { name: 'Next step: add your first tablet' })).toHaveCount(0, { timeout: 2000 });
  await expect(page.getByRole('button', { name: 'Edit layout', exact: true })).toBeVisible();
  expect((await axe(page)).violations).toEqual([]);
});
