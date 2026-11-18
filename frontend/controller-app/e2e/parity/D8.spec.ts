import { fileURLToPath } from 'node:url';
import { test, expect } from '../fixtures';

const image = fileURLToPath(new URL('../fixtures/images/two-colour.png', import.meta.url));

test.use({ serverScope: 'parity-D8' });
test('D8 The Next step card shows the highest-priority problem and its action works', async ({ page, server, api, tablets, guard, axe }) => {
  test.setTimeout(120_000);
  await guard(page);
  const fleet = await tablets(3);
  const [offlineTablet, wrongTablet] = fleet;
  if (!offlineTablet || !wrongTablet) throw new Error('Expected three joined tablets.');
  await expect.poll(async () => Object.keys((await api.config()).runtime.devices).length).toBe(3);
  await api.placeLogical({ columns: 3, rows: 1, deviceIds: fleet.map(tablet => tablet.id) });
  const asset = await api.upload(image);
  await api.scene({ type: 'image', asset: asset.id, fit: 'cover' });
  await page.goto(`${server.origin}/controller/app/`);
  await expect(page.locator('#tablet-health .state-ok')).toHaveCount(3, { timeout: 15_000 });
  await expect(page.getByRole('heading', { name: /^Next step:/ })).toHaveCount(0);

  const offlineRow = page.locator(`#tablet-row-${offlineTablet.id}`);
  const wrongRow = page.locator(`#tablet-row-${wrongTablet.id}`);
  const offlineName = (await offlineRow.locator('.row-name').textContent())?.trim();
  const wrongName = (await wrongRow.locator('.row-name').textContent())?.trim();
  if (!offlineName || !wrongName) throw new Error('Every board row must have a name.');
  const sidebar = page.getByRole('complementary', { name: 'Wall status' });

  await wrongTablet.page.route('**/assets/**', route => route.fulfill({ status: 200, contentType: 'text/plain', body: 'not an image' }));
  await wrongTablet.page.reload();
  await expect(wrongRow.locator('.state')).toHaveText('Wrong content', { timeout: 20_000 });
  await expect(sidebar.getByRole('alert').locator('.note-title')).toHaveText(`Next step: get ${wrongName} showing again`);

  await offlineTablet.page.close();
  await expect(offlineRow.locator('.state')).toHaveText('Offline', { timeout: 5_000 });
  const card = sidebar.getByRole('alert');
  await expect(card).toHaveCount(1);
  await expect(card.locator('.note-title')).toHaveText(`Next step: bring ${offlineName} back`);
  await expect(card).toContainText(/Offline for .+\. Wake it and it reconnects by itself\./);
  await card.getByRole('button', { name: 'Show tablet' }).click();
  await expect(offlineRow).toBeFocused();
  await expect(offlineRow).toHaveAttribute('aria-current', 'true');
  await expect(page.getByRole('heading', { name: offlineName, exact: true })).toBeVisible();
  expect((await axe(page)).violations).toEqual([]);

  const returning = await offlineTablet.context.newPage();
  await guard(returning);
  await returning.goto(`${server.origin}/client/`);
  await expect(offlineRow.locator('.state')).toHaveText('Showing', { timeout: 15_000 });
  await expect(card.locator('.note-title')).toHaveText(`Next step: get ${wrongName} showing again`, { timeout: 15_000 });
  await card.getByRole('button', { name: 'Show tablet' }).click();
  await expect(wrongRow).toBeFocused();
  await expect(wrongRow).toHaveAttribute('aria-current', 'true');
  expect((await axe(page)).violations).toEqual([]);
});
