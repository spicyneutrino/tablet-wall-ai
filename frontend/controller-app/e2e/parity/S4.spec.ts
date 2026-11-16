import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import type { Page, WebSocketRoute } from '@playwright/test';
import { test, expect } from '../fixtures';

test.use({ serverScope: 'parity-S4' });
test('S4 Within 2 s of a tablet going offline, the header names it, its board row says Offline, its stage tile shows an Offline label, and the board order does not change', async ({ page, browser, server, api, tablets, guard, axe }, info) => {
  test.setTimeout(180_000);
  await guard(page);
  const fleet = await tablets(4);
  await expect.poll(async () => Object.keys((await api.config()).runtime.devices).length).toBe(4);
  await api.placeLogical({ columns: 2, rows: 2, deviceIds: fleet.map(tablet => tablet.id) });
  const image = await api.upload(fileURLToPath(new URL('../fixtures/images/EXLENT_Cohort_3_Flyer_Temp.png', import.meta.url)));
  await api.scene({ type: 'image', asset: image.id, fit: 'cover' });
  await page.goto(`${server.origin}/controller/app/`);
  const summary = page.locator(`header .status-${info.project.name === 'phone' ? 'compact' : 'full'}`);
  const width = info.project.use.viewport!.width;
  const rows = page.locator('#tablet-health .row');
  await expect(page.locator('#tablet-health .state-ok')).toHaveCount(4);
  const order = await rows.evaluateAll(items => items.map(item => item.id));
  const lastId = await rows.last().getAttribute('data-device-id');
  const last = fleet.find(tablet => tablet.id === lastId);
  if (!last) throw new Error('Expected the fourth board row to have a real tablet.');
  await mkdir('/tmp/u23-shots', { recursive: true });
  async function capture(target: Page, state: string) {
    for (const theme of ['light', 'dark']) {
      const toggle = target.getByRole('button', { name: /^Theme:/ });
      for (let i = 0; i < 3 && await toggle.getAttribute('aria-label') !== `Theme: ${theme}`; i++) await toggle.click();
      await expect(toggle).toHaveAttribute('aria-label', `Theme: ${theme}`);
      await target.evaluate(() => document.fonts.ready);
      await target.mouse.move(0, 0);
      await target.evaluate(() => window.scrollTo(0, 0));
      expect(await target.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await target.screenshot({ path: `/tmp/u23-shots/${state}-${width}-${theme}.png`, fullPage: true, animations: 'disabled' });
      await target.locator('#tablet-health').screenshot({ path: `/tmp/u23-shots/${state}-${width}-${theme}-board.png`, animations: 'disabled' });
      expect((await axe(target)).violations, `${state}/${width}/${theme} axe`).toEqual([]);
      console.log(`${state}/${width}/${theme}: axe 0; /tmp/u23-shots/${state}-${width}-${theme}.png`);
    }
  }
  await capture(page, 'online');
  await last.page.close();
  const offline = page.locator(`#tablet-row-${last.id}`);
  await expect(offline.locator('.state')).toHaveText('Offline', { timeout: 2000 });
  await expect(summary).toHaveAccessibleDescription('Tablet 4: Offline.', { timeout: 2000 });
  await expect(summary).toHaveText(info.project.name === 'phone' ? '3 of 4' : '3 of 4 showing', { timeout: 2000 });
  await expect(page.locator(`[data-stage="preview"] [data-device-id="${last.id}"]`)).toHaveAttribute('data-status', 'offline', { timeout: 2000 });
  await expect(page.locator(`[data-stage="preview"] [data-device-id="${last.id}"]`).getByText('Offline', { exact: true })).toBeVisible({ timeout: 2000 });
  expect(await rows.evaluateAll(items => items.map(item => item.id))).toEqual(order);
  await capture(page, 'offline');
  const returned = await last.context.newPage();
  await guard(returned);
  await returned.goto(`${server.origin}/client/`);
  await expect(offline.locator('.state')).toHaveText('Showing', { timeout: 5000 });
  await expect(summary).toHaveClass(/chip-ok/, { timeout: 5000 });
  expect(await rows.evaluateAll(items => items.map(item => item.id))).toEqual(order);

  const context = await browser.newContext({ viewport: info.project.use.viewport, bypassCSP: true });
  try {
    const disconnectedPage = await context.newPage();
    const errors: string[] = [], warnings: string[] = [];
    disconnectedPage.on('pageerror', error => errors.push(error.message));
    disconnectedPage.on('console', message => {
      if (message.type() === 'error' || message.type() === 'warning') warnings.push(message.text());
    });
    let disconnected = false;
    const sockets: WebSocketRoute[] = [];
    await disconnectedPage.routeWebSocket('**/ws/controller?protocol=3', socket => {
      if (disconnected) return;
      sockets.push(socket);
      socket.connectToServer();
    });
    await disconnectedPage.goto(`${server.origin}/controller/app/`);
    await expect(disconnectedPage.locator('#tablet-health .state-ok')).toHaveCount(4);
    disconnected = true;
    await context.setOffline(true);
    await Promise.all(sockets.map(socket => socket.close({ code: 1001 })));
    await disconnectedPage.evaluate(() => window.dispatchEvent(new Event('online')));
    await expect(disconnectedPage.getByRole('heading', { name: 'Next step: wait for the server' })).toBeVisible();
    await expect(disconnectedPage.locator('#tablet-health .state')).toHaveText(['Unknown', 'Unknown', 'Unknown', 'Unknown']);
    await capture(disconnectedPage, 'unreachable');
    expect(errors).toEqual([]);
    expect(warnings.every(message => /ERR_INTERNET_DISCONNECTED|ERR_NETWORK_CHANGED|WebSocket.*(closed|failed)|net::ERR_FAILED/.test(message)), warnings.join('\n')).toBe(true);
    await context.setOffline(false);
    await disconnectedPage.evaluate(() => window.dispatchEvent(new Event('online')));
    await expect(disconnectedPage.locator('#tablet-health .state-ok')).toHaveCount(4, { timeout: 5000 });
  } finally { await context.close(); }
});
