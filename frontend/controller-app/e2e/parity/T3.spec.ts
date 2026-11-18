import { test, expect } from '../fixtures';

test.use({ serverScope: 'parity-T3' });
test('T3 Batch commands report completed, untouched, conflict and uncertain correctly', async ({ page, server, api, tablets, writes, guard }) => {
  test.setTimeout(180_000);
  await guard(page, { allow: [/\/identify$/] });
  const fleet = await tablets(4);
  const ids = fleet.map(tablet => tablet.id);
  await api.placeLogical({ columns: 4, rows: 1, deviceIds: ids, cellWidth: 200, cellHeight: 150 });
  await expect.poll(async () => {
    const config = await api.config();
    return fleet.map(({ id }) => config.runtime.devices[id]?.render.state);
  }).toEqual(['displayed', 'displayed', 'displayed', 'displayed']);
  const recorded = writes(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: 'Select several', exact: true }).click();
  for (const id of ids) {
    const row = page.locator(`#tablet-row-${id}`);
    await row.click();
    await expect(row).toHaveAttribute('aria-pressed', 'true');
  }
  await expect(page.getByText('4 selected', { exact: true })).toBeVisible();
  const identify = page.getByRole('button', { name: 'Identify selected', exact: true });
  const statuses = async () => page.locator('.batch-results li').evaluateAll(rows =>
    rows.map(row => [row.getAttribute('data-device-id'), row.getAttribute('data-batch-status')]));
  const posts = () => recorded.filter(request => request.method() === 'POST'
    && new URL(request.url()).pathname.endsWith('/identify'));

  // A lost response after the server committed is uncertain, and nothing after it runs.
  await page.route(`**/api/v3/devices/${ids[1]}/identify`, async route => {
    await route.fetch();
    await route.abort('connectionreset');
  }, { times: 1 });
  const guardBefore = (await api.config()).etag;
  await identify.click();
  await expect(page.locator('.batch-results li')).toHaveCount(4);
  expect(await statuses()).toEqual([[ids[0], 'completed'], [ids[1], 'uncertain'], [ids[2], 'untouched'], [ids[3], 'untouched']]);
  await expect(page.locator(`.batch-results li[data-device-id="${ids[1]}"]`)).toContainText('Uncertain');
  await expect(page.locator(`.batch-results li[data-device-id="${ids[1]}"]`)).toContainText('Not confirmed.');
  const first = posts();
  expect(first).toHaveLength(2);
  expect(first.map(request => new URL(request.url()).pathname)).toEqual(ids.slice(0, 2).map(id => `/api/v3/devices/${id}/identify`));
  expect(first.map(request => request.headers()['if-match'])).toEqual([guardBefore, guardBefore]);
  await expect(identify).toHaveAttribute('aria-disabled', 'true');
  await expect(page.getByText('The last change was not confirmed. Refresh status first.').first()).toBeVisible();

  // Refresh status clears the latch, then a real external durable change makes the third write conflict.
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(identify).not.toHaveAttribute('aria-disabled', 'true');
  await page.route(`**/api/v3/devices/${ids[2]}/identify`, async route => {
    const before = await api.config();
    const renamed = await api.request.patch(`/api/v3/devices/${ids[0]}`, {
      headers: { 'If-Match': before.etag }, data: { label: 'Concurrent batch edit' } });
    expect(renamed.ok(), await renamed.text()).toBe(true);
    await route.continue();
  }, { times: 1 });
  const guardAfterRefresh = (await api.config()).etag;
  await identify.click();
  await expect(page.locator('.batch-results li')).toHaveCount(4);
  expect(await statuses()).toEqual([[ids[0], 'completed'], [ids[1], 'completed'], [ids[2], 'conflict'], [ids[3], 'untouched']]);
  await expect(page.locator(`.batch-results li[data-device-id="${ids[2]}"]`)).toContainText('Conflict');
  await expect(page.locator(`.batch-results li[data-device-id="${ids[3]}"]`)).toContainText('Untouched');
  const second = posts().slice(first.length);
  expect(second).toHaveLength(3);
  expect(second.map(request => new URL(request.url()).pathname)).toEqual(ids.slice(0, 3).map(id => `/api/v3/devices/${id}/identify`));
  expect(second.map(request => request.headers()['if-match'])).toEqual([guardAfterRefresh, guardAfterRefresh, guardAfterRefresh]);
});
