import { test, expect } from './fixtures';

test.use({ serverScope: 'board-status-line' });

test('tablet status words stay on one line at 1440', async ({ server, tablets, page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await tablets(2);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  const state = page.locator('.tablet-row .state').filter({ hasText: 'Not placed' }).first();
  await expect(state).toBeVisible();
  const { height, lineHeight } = await state.evaluate((el) => {
    const style = getComputedStyle(el);
    return {
      height: el.getBoundingClientRect().height,
      lineHeight: style.lineHeight === 'normal' ? parseFloat(style.fontSize) * 1.5 : parseFloat(style.lineHeight),
    };
  });
  expect(height).toBeLessThan(lineHeight * 1.5);
});
