import { expect, test } from '../fixtures';

test.use({ serverScope: 'parity-P3' });
test('P3 Without opt-in: no `/api/v3/playback` polling, and no playlist controls', async ({ server, page, guard, axe, writes }) => {
  test.setTimeout(90_000);
  await guard(page);
  const sent = writes(page);
  const requested: string[] = [];
  page.on('request', request => {
    const { pathname } = new URL(request.url());
    if (/^\/(api\/v3\/(playback|playlist)|media)(\/|$)/.test(pathname)) requested.push(`${request.method()} ${pathname}`);
  });
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: 'Server', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'Server', exact: true });
  await sheet.getByRole('tab', { name: 'Playback' }).click();
  const optIn = sheet.getByRole('switch', { name: /Playlist and playback/ });
  await expect(optIn).not.toBeChecked();
  await page.waitForTimeout(3_500);
  expect(requested, 'no playback, playlist or media request without the opt-in').toEqual([]);
  for (const name of ['Playlist', 'Playback']) await expect(sheet.getByRole('heading', { name, exact: true })).toHaveCount(0);
  for (const name of ['Start', 'Save playlist', 'Add', 'Pause', 'Next item']) await expect(sheet.getByRole('button', { name, exact: true })).toHaveCount(0);
  await expect(sheet.getByRole('list', { name: 'Playlist order' })).toHaveCount(0);
  expect((await axe(page)).violations).toEqual([]);

  await optIn.check();
  await expect(sheet.getByRole('heading', { name: 'Playlist', exact: true })).toBeVisible();
  await expect.poll(() => requested.filter(entry => entry === 'GET /api/v3/playback').length, { timeout: 5_000 }).toBeGreaterThan(1);
  expect(await page.evaluate(() => localStorage.getItem('tablet-wall-playback'))).toBe('on');

  await optIn.uncheck();
  await expect(sheet.getByRole('heading', { name: 'Playlist', exact: true })).toHaveCount(0);
  await page.waitForTimeout(1_500);
  const settled = requested.length;
  await page.waitForTimeout(3_500);
  expect(requested.length, 'switching off stops the polling').toBe(settled);
  expect(await page.evaluate(() => localStorage.getItem('tablet-wall-playback'))).toBe('off');
  expect(sent, 'opting in and out writes nothing').toEqual([]);
});
