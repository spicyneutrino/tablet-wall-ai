import { z } from 'zod';
import { expect, test } from '../fixtures';

const operatorConfig = z.object({ tablet_origin: z.string().nullable() });

test('V1 The Joining section shows the tablet URL, QR and Copy link. Without a tablet origin it says why', async ({ page, server, api, guard }) => {
  await guard(page);
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], { origin: server.origin });
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('status')).toHaveText('Live operator updates connected.');
  const config = operatorConfig.parse(await (await api.request.get('/operator-config')).json());
  if (!config.tablet_origin) throw new Error('The parity server must start with a tablet origin.');
  const url = `${config.tablet_origin}/client/`;

  await page.getByRole('button', { name: 'Server', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'Server', exact: true });
  await sheet.getByRole('tab', { name: 'Joining', exact: true }).click();
  await expect(sheet.getByText(url, { exact: true })).toBeVisible();
  const qr = sheet.getByRole('img', { name: 'QR code for the tablet address' });
  await expect(qr).toHaveAttribute('src', '/api/v3/join-qr');
  await expect.poll(() => qr.evaluate((image) => image instanceof HTMLImageElement && image.complete && image.naturalWidth > 0)).toBe(true);
  await sheet.getByRole('button', { name: 'Copy link', exact: true }).click();
  await expect(sheet.getByText('Copied', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(url);

  await page.route('**/operator-config', (route) => route.fulfill({ json: { tablet_origin: null } }));
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Server', exact: true }).click();
  await sheet.getByRole('tab', { name: 'Joining', exact: true }).click();
  await expect(sheet.getByText(/No tablet address is configured/)).toBeVisible();
  await expect(sheet.getByText(/TABLET_WALL_TABLET_ORIGIN/)).toBeVisible();
  await expect(sheet.getByText(url)).toHaveCount(0);
  await expect(sheet.getByRole('img', { name: 'QR code for the tablet address' })).toHaveCount(0);
  await expect(sheet.getByRole('button', { name: 'Copy link', exact: true })).toHaveCount(0);
});
