import { DeviceIdSchema } from '../../src/api/devices';
import { ConfigSchema } from '../../src/api/config';
import { test, expect } from '../fixtures';

test.use({ serverScope: 'parity-A2' });
test('A2 A refused grid (capacity, changed connection or viewport) shows the reason and keeps the inputs', async ({ server, api, tablets, page, writes, guard }) => {
  test.setTimeout(90_000);
  const fleet = await tablets(3, { viewport: { width: 400, height: 400 } });
  await expect.poll(async () => Object.values((await api.config()).runtime.devices).filter(device => device.online).length).toBe(3);
  await api.placeLogical({ columns: 1, rows: 3, deviceIds: fleet.map(tablet => tablet.id) });
  await guard(page, { allow: [/\/api\/v3\/grid$/] });
  const sent = writes(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  await page.getByRole('tab', { name: 'Layouts', exact: true }).click();
  await page.getByRole('button', { name: 'New grid…', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'Build grid', exact: true });
  await sheet.getByLabel('Columns', { exact: true }).fill('1');
  await sheet.getByLabel('Rows', { exact: true }).fill('2');
  await sheet.getByRole('switch', { name: 'Allow empty trailing cells' }).uncheck();
  await sheet.getByRole('button', { name: 'Preview grid', exact: true }).click();
  await expect(sheet.getByRole('alert')).toHaveText(/Select exactly 2 tablets/);
  await expect(sheet.getByRole('alert')).toBeFocused();
  await expect(sheet.getByLabel('Columns', { exact: true })).toHaveValue('1');
  await expect(sheet.getByLabel('Rows', { exact: true })).toHaveValue('2');
  expect(sent).toEqual([]);
  await sheet.getByLabel('Rows', { exact: true }).fill('3');
  await sheet.getByLabel('Gap (logical units)', { exact: true }).fill('7');
  const original = ConfigSchema.parse(await api.config()).layout;
  const tablet = fleet[0]!;
  const deviceId = DeviceIdSchema.parse(tablet.id);
  const device = async () => ConfigSchema.parse(await api.config()).runtime.devices[deviceId];
  let tabletPage = tablet.page;
  for (const mutation of ['connection', 'viewport'] as const) {
    await sheet.getByRole('button', { name: 'Preview grid', exact: true }).click();
    await expect(sheet).toBeHidden();
    if (mutation === 'connection') {
      await tabletPage.close();
      await expect.poll(async () => (await device())?.online).toBe(false);
      tabletPage = await tablet.context.newPage();
      await guard(tabletPage);
      await tabletPage.goto(`${server.origin}/client/`);
      await expect.poll(async () => (await device())?.online).toBe(true);
    } else {
      await tabletPage.setViewportSize({ width: 440, height: 400 });
      await expect.poll(async () => (await device())?.viewport?.width).toBe(440);
    }
    const responsePromise = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v3/grid');
    await page.getByRole('button', { name: 'Apply layout', exact: true }).click();
    const response = await responsePromise;
    expect(response.status()).toBe(412);
    await expect(page.locator('.primary-action').getByRole('alert')).toContainText(mutation === 'connection' ? /connection|reconnect/i : /viewport/i);
    expect(ConfigSchema.parse(await api.config()).layout).toEqual(original);
    await expect(page.locator('[data-stage="preview"] [data-device-id]')).toHaveCount(3);
    await page.getByRole('button', { name: 'Edit grid', exact: true }).click();
    await expect(sheet.getByLabel('Rows', { exact: true })).toHaveValue('3');
    await expect(sheet.getByLabel('Columns', { exact: true })).toHaveValue('1');
    await expect(sheet.getByLabel('Gap (logical units)', { exact: true })).toHaveValue('7');
    expect(await sheet.locator('[data-grid-device] button[aria-label^="Exclude "]').count()).toBe(3);
  }
  await sheet.getByRole('button', { name: 'Preview grid', exact: true }).click();
  await expect(sheet).toBeHidden();
  await page.getByRole('button', { name: 'Apply layout', exact: true }).click();
  await expect(page.getByRole('button', { name: 'New grid…', exact: true })).toBeVisible();
  expect(sent.filter(request => new URL(request.url()).pathname === '/api/v3/grid')).toHaveLength(3);
});
