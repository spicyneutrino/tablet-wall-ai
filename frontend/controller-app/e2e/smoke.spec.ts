import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { z } from 'zod';
import { startServer } from './server';

let server: Awaited<ReturnType<typeof startServer>>;
test.beforeAll(async () => { server = await startServer(); });
test.afterAll(async () => { await server?.stop(); });

for (const theme of ['light', 'dark', 'system']) {
  test(`serves the controller with CSP, local fonts and a snapshot (${theme})`, async ({ page, context }, testInfo) => {
    const errors: string[] = [];
    const external: string[] = [];
    const failed: string[] = [];
    const snapshots: unknown[] = [];
    page.on('console', (message) => {
      if (message.type() === 'error' || message.type() === 'warning') errors.push(message.text());
    });
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('requestfailed', (request) => failed.push(`${request.url()} ${request.failure()?.errorText}`));
    page.on('response', (response) => {
      if (response.status() >= 400) failed.push(`${response.status()} ${response.url()}`);
    });
    page.on('request', (request) => {
      if (new URL(request.url()).origin !== server.origin) external.push(request.url());
    });
    page.on('websocket', (socket) => {
      const url = new URL(socket.url());
      expect(url.protocol).toBe('ws:');
      expect(url.host).toBe(new URL(server.origin).host);
      expect(url.pathname + url.search).toBe('/ws/controller?protocol=3');
      socket.on('framereceived', ({ payload }) => {
        const frame: unknown = JSON.parse(payload.toString());
        if (typeof frame === 'object' && frame !== null && 'type' in frame && frame.type === 'snapshot') snapshots.push(frame);
      });
    });
    await context.addInitScript((savedTheme) => {
      localStorage.setItem('tablet-wall-theme', savedTheme);
      const violations: string[] = [];
      Object.assign(window, { cspViolations: violations });
      document.addEventListener('securitypolicyviolation', (event) => violations.push(`${event.violatedDirective} ${event.blockedURI}`));
    }, theme);
    const token = process.env.TABLET_WALL_AUTH_TOKEN;
    if (token) {
      await page.goto(`${server.origin}/controller/app/`);
      await expect(page).toHaveURL(/\/auth\/login\?next=/);
      await page.getByLabel('Access token').fill(token);
      const login = page.waitForResponse((response) => response.url().endsWith('/auth/login') && response.request().method() === 'POST');
      await page.getByRole('button', { name: 'Sign in' }).click();
      expect((await login).status()).toBe(303);
      await expect(page).toHaveURL(`${server.origin}/controller/app/`);
      expect((await context.cookies()).some((cookie) => cookie.name === 'tablet_wall_session' && cookie.httpOnly)).toBe(true);
    }
    const response = await page.goto(`${server.origin}/controller/app/`);
    expect(response?.status()).toBe(200);
    expect(response?.headers()['content-security-policy']).toContain("script-src 'self'");
    expect(response?.headers()['content-security-policy']).toContain("font-src 'self'");
    expect(response?.headers()['cache-control']).toBe(token ? 'private, no-store' : 'no-cache');
    await expect(page).toHaveTitle('Tablet wall');
    expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe(theme === 'system' ? undefined : theme);
    await expect(page.getByRole('heading', { name: 'Tablet wall', level: 1 })).toBeVisible();
    await expect(page.getByRole('status')).toHaveText('Live operator updates connected.');
    await expect.poll(() => snapshots.length).toBeGreaterThan(0);
    await page.evaluate(() => document.fonts.ready);
    expect(await page.evaluate(() => document.fonts.check('16px "Atkinson Hyperlegible Next"'))).toBe(true);
    expect(await page.evaluate(() => [...document.fonts].some((font) => font.family.includes('Atkinson Hyperlegible Next') && font.status === 'loaded'))).toBe(true);
    const resources = await page.evaluate(() => performance.getEntriesByType('resource').map((entry) => entry.name));
    expect(resources.some((url) => url.startsWith(`${server.origin}/controller/app/assets/`) && url.endsWith('.woff2'))).toBe(true);
    const config = await page.evaluate(async () => {
      const response = await fetch('/api/v3/config');
      return { status: response.status, body: await response.json() as unknown };
    });
    expect(config.status).toBe(200);
    const capabilities = z.object({ capabilities: z.object({ login_supported: z.boolean() }) }).parse(config.body).capabilities;
    expect(capabilities.login_supported).toBe(Boolean(token));
    await expect(page.locator('script')).toHaveCount(2);
    for (const script of await page.locator('script').all()) expect(await script.getAttribute('src')).toBeTruthy();
    expect(await page.locator('script:not([src])').count()).toBe(0);
    for (const width of [390, 820, 1440]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      await expect(page.getByRole('status')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`${theme}-${width}.png`) });
    }
    expect(await page.evaluate(() => Reflect.get(window, 'cspViolations'))).toEqual([]);
    expect(external).toEqual([]);
    expect(failed).toEqual([]);
    expect(errors).toEqual([]);
    const axeContext = await page.context().browser()?.newContext({ bypassCSP: true, storageState: await context.storageState() });
    if (!axeContext) throw new Error('Browser is required for accessibility checks');
    try {
      await axeContext.addInitScript((savedTheme) => localStorage.setItem('tablet-wall-theme', savedTheme), theme);
      const axePage = await axeContext.newPage();
      await axePage.goto(`${server.origin}/controller/app/`);
      await expect(axePage.getByRole('status')).toHaveText('Live operator updates connected.');
      const results = await new AxeBuilder({ page: axePage }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
      expect(results.violations).toEqual([]);
    } finally { await axeContext.close(); }
  });
}

test('stage fixture is limited to the e2e build', async ({ page }) => {
  if (process.env.TABLET_WALL_AUTH_TOKEN) {
    await page.goto(`${server.origin}/controller/app/`);
    await page.getByLabel('Access token').fill(process.env.TABLET_WALL_AUTH_TOKEN);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(`${server.origin}/controller/app/`);
  }
  await page.goto(`${server.origin}/controller/app/#stage-fixture`);
  await expect(page.getByRole('heading', { name: 'Tablet wall' })).toBeVisible();
  await page.goto(`${server.origin}/controller/app-e2e/#stage-fixture`);
  await expect(page.getByRole('main', { name: 'Stage fixture' })).toBeAttached();
  await expect(page.getByRole('heading', { name: 'Tablet wall' })).toHaveCount(0);
});
