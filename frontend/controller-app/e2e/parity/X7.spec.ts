import { test, expect } from '../fixtures';

test.use({ serverScope: 'parity-X7' });
test('X7 The old entry URLs redirect to `/controller/app/` and keep the query and hash', async ({ server, page, guard }) => {
  await guard(page);
  for (const entry of ['/controller/?a=1#b', '/controller/physical.html?a=1#b']) {
    await page.goto(`${server.origin}${entry}`);
    await page.waitForURL(`${server.origin}/controller/app/?a=1#b`);
    await expect(page.locator('#root')).toBeAttached();
  }
});
