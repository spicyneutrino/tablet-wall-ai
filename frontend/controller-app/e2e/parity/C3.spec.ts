import { test, expect } from '../fixtures';
import { fileURLToPath } from 'node:url';
const image = fileURLToPath(new URL('../fixtures/images/two-colour.png', import.meta.url));

test.use({ serverScope: 'parity-C3' });
test('C3 Show after another controller changed the wall gets a 412. The selection is kept, and Rebuild preview then Show succeeds', async ({ server, api, tablets, page, writes }) => {
  const [tablet] = await tablets(1);
  if (!tablet) throw new Error('Expected tablet');
  await api.placeLogical({ columns: 1, rows: 1, deviceIds: [tablet.id] });
  await api.upload(image);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  const recorded = writes(page);
  await page.getByRole('button', { name: 'two-colour.png', exact: true }).click();
  await page.route('**/api/v3/scene', async route => {
    await api.scene({ type: 'calibration' });
    await route.continue();
  }, { times: 1 });
  const response = page.waitForResponse(response => response.url().endsWith('/api/v3/scene') && response.request().method() === 'PUT');
  await page.getByRole('button', { name: 'Show on wall', exact: true }).click();
  expect((await response).status()).toBe(412);
  await expect(page.getByRole('button', { name: 'two-colour.png', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('region', { name: 'Preview', exact: true }).locator('image')).toHaveCount(1);
  await expect(page.locator('.desktop-onwall')).toContainText('Calibration grid');
  await page.getByRole('button', { name: 'Rebuild preview', exact: true }).click();
  const rebuiltEtag = (await api.config()).etag;
  await page.getByRole('button', { name: 'Show on wall', exact: true }).click();
  await expect(page.locator('.desktop-onwall')).toContainText('two-colour.png, Fill');
  expect(recorded).toHaveLength(2);
  expect(recorded[1]?.headers()['if-match']).toBe(rebuiltEtag);
});
