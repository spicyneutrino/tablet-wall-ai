import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import type { Page } from '@playwright/test';
import type { WebSocketRoute } from '@playwright/test';
import type { Tablet } from './fixtures';
import { ConfigSchema } from '../src/api/config';
import { test, expect } from './fixtures';
import { fleet as fleetDevices } from './fixtures/fleet';

const image = fileURLToPath(new URL('./fixtures/images/EXLENT_Cohort_3_Flyer_Temp.png', import.meta.url));
const themes = ['light', 'dark'] as const;
const evidence = '/tmp/u15-finish';

test('Direction C shell keeps its preview through all operator and connection states', async ({ browser, server, api, tablets, guard, writes, axe, stageBox }, info) => {
  test.setTimeout(300_000);
  const viewport = info.project.use.viewport;
  if (!viewport) throw new Error('Shell coverage requires an explicit viewport.');
  const width = viewport.width;
  const height = viewport.height;
  const context = await browser.newContext({ viewport, hasTouch: width < 1024 });
  context.setDefaultTimeout(5_000);
  const page = await context.newPage();
  await guard(page);
  const mutations = writes(page);
  const failed: string[] = [];
  const warnings: string[] = [];
  page.on('console', message => { if (message.type() === 'warning') warnings.push(message.text()); });
  page.on('requestfailed', request => failed.push(`${request.method()} ${request.url()} ${request.failure()?.errorText}`));
  page.on('response', response => { if (response.status() >= 400) failed.push(`${response.status()} ${response.url()}`); });
  const measurements: Record<string, Awaited<ReturnType<typeof stageBox>>> = {};
  await mkdir(evidence, { recursive: true });
  const baselines = new Map<number, Awaited<ReturnType<typeof stageBox>>>();
  async function setTheme(target: Page, theme: typeof themes[number]) {
    const toggle = target.getByRole('button', { name: /^Theme:/ });
    for (let step = 0; step < 3 && await toggle.getAttribute('aria-label') !== `Theme: ${theme}`; step++) await toggle.click();
    await expect(toggle).toHaveAttribute('aria-label', `Theme: ${theme}`);
    await target.mouse.move(0, 0);
  }
  async function clickScreen(target: Page, id: string) {
    const screen = target.locator(`[data-stage="preview"] [data-screen="${id}"]`);
    const box = await screen.boundingBox();
    if (!box) throw new Error(`Tablet ${id} must have a visible screen.`);
    await target.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  }
  async function audit(target: Page, state: string, theme: typeof themes[number]) {
    const auditViewport = target.viewportSize();
    if (!auditViewport) throw new Error('Audit requires a viewport.');
    const auditContext = await browser.newContext({ viewport: auditViewport, hasTouch: auditViewport.width < 1024, bypassCSP: true });
    auditContext.setDefaultTimeout(5_000);
    const auditPage = await auditContext.newPage();
    let releaseAudit = () => {};
    let disconnected = false;
    const sockets: WebSocketRoute[] = [];
    try {
      await auditContext.addInitScript(value => localStorage.setItem('tablet-wall-theme', value), theme);
      if (state === 'loading') {
        const gate = new Promise<void>(resolve => { releaseAudit = resolve; });
        await auditPage.route('**/api/v3/config', async route => { await gate; await route.continue(); });
        await auditPage.routeWebSocket('**/ws/controller?protocol=3', () => {});
      } else if (state === 'unreachable') {
        await auditPage.routeWebSocket('**/ws/controller?protocol=3', socket => {
          if (disconnected) return;
          sockets.push(socket);
          socket.connectToServer();
        });
      }
      await auditPage.goto(target.url(), { waitUntil: state === 'loading' ? 'domcontentloaded' : 'networkidle' });
      if (['selected', 'arrange', 'drill'].includes(state)) {
        const id = await target.locator('[data-stage="preview"] [data-selected="true"]').getAttribute('data-device-id');
        if (!id) throw new Error('The normal page must have a selected tablet.');
        await clickScreen(auditPage, id);
        if (state === 'arrange') await auditPage.getByRole('button', { name: 'Edit layout', exact: true }).click();
        if (state === 'drill') await auditPage.getByRole('button', { name: 'Tablet details', exact: true }).click();
      }
      if (state === 'unreachable') {
        disconnected = true;
        await auditContext.setOffline(true);
        await Promise.all(sockets.map(socket => socket.close({ code: 1001 })));
        await auditPage.evaluate(() => window.dispatchEvent(new Event('online')));
        await expect(auditPage.getByRole('heading', { name: 'Next step: wait for the server' })).toBeVisible();
      }
      if (state === 'server') await auditPage.getByRole('button', { name: 'Server', exact: true }).click();
      const results = await axe(auditPage);
      expect(results.violations, `${state}/${auditViewport.width}/${theme} axe`).toEqual([]);
      return results;
    } finally {
      releaseAudit();
      await auditPage.unrouteAll({ behavior: 'wait' });
      await auditContext.close();
    }
  }
  async function captureViewport(target: Page, state: string, theme: typeof themes[number]) {
    const currentViewport = target.viewportSize();
    if (!currentViewport) throw new Error('Capture requires a viewport.');
    const { width, height } = currentViewport;
    await target.evaluate(() => window.scrollTo(0, 0));
    await setTheme(target, theme);
    await target.evaluate(() => document.fonts.ready);
    const box = await stageBox(target);
    const baseline = baselines.get(width) ?? box;
    baselines.set(width, baseline);
    if (width === 1366) expect(box.width * box.height / (width * height), `${state}/${theme} preview area`).toBeGreaterThanOrEqual(0.45);
    for (const key of ['x', 'y', 'width', 'height'] as const) {
      expect(Math.abs(box[key] - baseline[key]), `${state}/${theme}/${key} stage drift`).toBeLessThanOrEqual(0.02);
    }
    measurements[`${state}-${width}-${theme}`] = box;
    expect(await target.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${state} horizontal overflow`).toBe(true);
    await target.screenshot({ path: join(evidence, `${state}-${width}-${theme}.png`), animations: 'disabled' });
    const results = await audit(target, state, theme);
    await expect(target).toHaveScreenshot(`${state}-${theme}${width === 1366 ? '-laptop' : ''}.png`, {
      mask: state === 'firstrun' ? [target.locator('.join-address'), target.locator('.join-code img')]
        : state === 'unreachable' ? [target.locator('[data-report-time]')] : [],
    });
    if (width === 390) {
      await target.evaluate(() => {
        for (const element of document.querySelectorAll('*')) {
          if (element instanceof HTMLElement) {
            element.scrollTop = element.scrollHeight;
            element.scrollLeft = element.scrollWidth;
          }
        }
        window.scrollTo(0, document.documentElement.scrollHeight);
      });
      const pinned = await stageBox(target);
      expect(pinned.y, `${state} preview starts inside phone viewport`).toBeGreaterThanOrEqual(0);
      expect(pinned.y + pinned.height, `${state} preview ends inside phone viewport`).toBeLessThanOrEqual(height);
      await target.evaluate(() => {
        window.scrollTo(0, 0);
        for (const element of document.querySelectorAll('*')) {
          if (element instanceof HTMLElement) { element.scrollTop = 0; element.scrollLeft = 0; }
        }
      });
    }
    console.log(`${state} ${width} ${theme}: preview ${box.width}x${box.height} at (${box.x},${box.y}); axe ${results.violations.length}; ${join(evidence, `${state}-${width}-${theme}.png`)}`);
  }
  async function capture(target: Page, state: string, theme: typeof themes[number]) {
    await captureViewport(target, state, theme);
    if (width === 1440) {
      await target.setViewportSize({ width: 1366, height: 768 });
      await captureViewport(target, state, theme);
      await target.setViewportSize({ width, height });
    }
  }
  let release: () => void = () => {};
  try {
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route('**/api/v3/config', async route => { await gate; await route.continue(); });
    await page.routeWebSocket('**/ws/controller?protocol=3', async socket => { await gate; socket.connectToServer(); });
    await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('button', { name: 'Connecting…' })).toBeVisible();
    for (const theme of themes) await capture(page, 'loading', theme);
    release();
    await expect(page.getByRole('heading', { name: 'Next step: add your first tablet' })).toBeVisible();
    await expect(page.locator('.join-code img')).toBeVisible();
    await expect.poll(() => page.locator('.join-code img').evaluate(image => image instanceof HTMLImageElement && image.complete && image.naturalWidth > 0)).toBe(true);
    for (const theme of themes) await capture(page, 'firstrun', theme);

    const fleet: Tablet[] = [];
    for (const device of fleetDevices) {
      fleet.push(...await tablets(1, { ids: [device.id] }));
      await expect.poll(async () => (await api.config()).runtime.devices[device.id]?.online).toBe(true);
    }
    await expect.poll(async () => Object.values((await api.config()).runtime.devices).filter(device => device.online).length).toBe(4);
    const asset = await api.upload(image);
    const placed = await api.placeLogical({ columns: 2, rows: 2, deviceIds: fleet.map(tablet => tablet.id), cellWidth: 800, cellHeight: 600 });
    const config = ConfigSchema.parse(placed);
    if (config.layout.kind !== 'logical') throw new Error('Shell test requires the logical wall it just placed.');
    const spaced = await api.request.put('/api/v3/logical-layout', { headers: { 'If-Match': config.etag }, data: {
      width: 1600, height: 1200, sizing: config.layout.sizing,
      placements: Object.fromEntries(Object.entries(config.layout.placements).map(([id, placement]) => [id, {
        ...placement, x: placement.x + 24, y: placement.y + 24, w: placement.w - 48, h: placement.h - 48,
        bezel: { left: 16, top: 16, right: 16, bottom: 16 },
      }])),
    } });
    expect(spaced.ok(), await spaced.text()).toBe(true);
    await api.scene({ type: 'image', asset: asset.id, fit: 'cover' });
    await expect(page.locator('#tablet-health .state-ok')).toHaveCount(4);
    await expect(page.getByRole('button', { name: width < 640 ? '4 of 4' : '4 of 4 showing', exact: true })).toBeVisible();
    await expect(page.locator('[data-stage="preview"] [data-screen]')).toHaveCount(4);
    await expect(page.getByRole('heading', { name: /Next step:/ })).toHaveCount(0);
    for (const theme of themes) {
      await capture(page, 'main', theme);
      await clickScreen(page, fleetDevices[1].id);
      await expect(page.locator('[data-stage="preview"] [data-selected="true"]')).toHaveCount(1);
      await expect(page.getByRole('heading', { name: 'Tablet 2', exact: true })).toBeVisible();
      await capture(page, 'selected', theme);
      await page.getByRole('button', { name: 'Edit layout', exact: true }).click();
      await expect(page.getByRole('button', { name: 'Edit layout', exact: true })).toHaveAttribute('aria-pressed', 'true');
      await capture(page, 'arrange', theme);
      await page.getByRole('button', { name: 'Edit layout', exact: true }).click();
      await page.getByRole('button', { name: 'Tablet details', exact: true }).click();
      await expect(page.getByRole('button', { name: 'All tablets', exact: true })).toBeVisible();
      await capture(page, 'drill', theme);
      await page.getByRole('button', { name: 'All tablets', exact: true }).click();
      await expect(page.getByRole('heading', { name: 'Tablet 2', exact: true })).toHaveCount(0);
    }
    await page.locator('[data-stage="preview"]').focus();
    await page.keyboard.press('ArrowLeft');
    await expect(page.getByRole('heading', { name: 'Tablet 4', exact: true })).toBeVisible();
    await page.keyboard.press('ArrowRight');
    await expect(page.getByRole('heading', { name: 'Tablet 1', exact: true })).toBeVisible();
    await expect(page.locator('[data-stage="onwall"] [data-selected="true"]')).toHaveCount(0);
    await page.getByRole('button', { name: 'Tablet details', exact: true }).click();
    await page.getByRole('button', { name: 'All tablets', exact: true }).click();
    const sources = page.getByRole('tablist', { name: 'Source type' });
    await sources.getByRole('tab', { name: 'Images', exact: true }).focus();
    await page.keyboard.press('ArrowRight');
    await expect(sources.getByRole('tab', { name: 'Saved', exact: true })).toBeFocused();
    await expect(sources.getByRole('tab', { name: 'Saved', exact: true })).toHaveAttribute('aria-selected', 'true');
    await sources.getByRole('tab', { name: 'Images', exact: true }).click();
    if (width < 1024) {
      await page.getByRole('button', { name: 'View', exact: true }).click();
      await expect(page.getByRole('button', { name: 'Hide', exact: true })).toHaveAttribute('aria-expanded', 'true');
      await expect(page.locator('.mobile-onwall [data-stage="onwall"]')).toBeVisible();
      await page.getByRole('button', { name: 'Hide', exact: true }).click();
    }
    await page.getByRole('button', { name: 'Server', exact: true }).click();
    const sheet = page.getByRole('dialog', { name: 'Server', exact: true });
    await expect(sheet).toBeVisible();
    await audit(page, 'server', 'dark');
    await page.keyboard.press('Escape');
    await expect(sheet).not.toBeVisible();
    await expect(page.getByRole('button', { name: 'Server', exact: true })).toBeFocused();
    await page.getByRole('button', { name: /^Theme:/ }).click();
    await expect.poll(() => page.evaluate(() => localStorage.getItem('tablet-wall-theme'))).toBe('system');
    await fleet[3]!.context.close();
    await expect(page.locator('#tablet-health .state-warn')).toHaveCount(1);
    await expect(page.locator('[data-stage="preview"] [data-status="offline"]')).toHaveCount(1);
    for (const theme of themes) await capture(page, 'offline', theme);
    await tablets(1, { ids: [fleetDevices[3].id] });
    await expect(page.locator('#tablet-health .state-ok')).toHaveCount(4);

    const offlineContext = await browser.newContext({ viewport, hasTouch: width < 1024 });
    try {
      const offlinePage = await offlineContext.newPage();
      const runtimeErrors: string[] = [];
      const consoleErrors: string[] = [];
      let disconnected = false;
      const sockets: WebSocketRoute[] = [];
      await offlinePage.routeWebSocket('**/ws/controller?protocol=3', socket => {
        if (disconnected) return;
        sockets.push(socket);
        socket.connectToServer();
      });
      await offlinePage.addInitScript(() => document.addEventListener('securitypolicyviolation', event => {
        console.error(`CSP ${event.violatedDirective} ${event.blockedURI}`);
      }));
      offlinePage.on('pageerror', error => runtimeErrors.push(error.message));
      offlinePage.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
      await offlinePage.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
      await expect(offlinePage.locator('#tablet-health .row')).toHaveCount(4);
      disconnected = true;
      await offlineContext.setOffline(true);
      await Promise.all(sockets.map(socket => socket.close({ code: 1001 })));
      await offlinePage.evaluate(() => window.dispatchEvent(new Event('online')));
      await expect(offlinePage.getByRole('heading', { name: 'Next step: wait for the server' })).toBeVisible();
      for (const theme of themes) await capture(offlinePage, 'unreachable', theme);
      const reportTimes = offlinePage.locator('[data-report-time]');
      const reportLabels = await reportTimes.allTextContents();
      expect(reportLabels.length).toBeGreaterThanOrEqual(3);
      expect(new Set(reportLabels).size).toBe(1);
      expect(reportLabels[0]).toMatch(/^\d{2}:\d{2}$/);
      const reportInstants = await reportTimes.evaluateAll(times => times.map(time => time.getAttribute('datetime')));
      expect(new Set(reportInstants).size).toBe(1);
      expect(Number.isNaN(Date.parse(reportInstants[0] ?? ''))).toBe(false);
      expect(runtimeErrors).toEqual([]);
      expect(consoleErrors.every(error => /ERR_INTERNET_DISCONNECTED|ERR_NETWORK_CHANGED|WebSocket.*(closed|failed)|net::ERR_FAILED/.test(error)), JSON.stringify(consoleErrors)).toBe(true);
      console.log(`Unreachable transport: ${consoleErrors.length} expected network diagnostics, 0 page errors.`);
      await offlinePage.getByRole('button', { name: 'Try now', exact: true }).click();
      await expect(offlinePage.getByText(/Status could not be reconciled/)).toBeVisible();
      expect(runtimeErrors).toEqual([]);
    } finally { await offlineContext.close(); }
    expect(mutations).toEqual([]);
    expect(failed).toEqual([]);
    expect(warnings).toEqual([]);
    await writeFile(join(evidence, `preview-boxes-${width}.json`), JSON.stringify(measurements, null, 2));
    console.log(`PASS ${width}: stage drift ≤0.02px; phone pinning; both themes; keyboard tabs; live disclosure; modal focus; theme persistence; no controller writes or failed normal requests.`);
    ConfigSchema.parse(await api.config());
    if (width === 1440) {
      await page.setViewportSize({ width: 1366, height: 768 });
      const box = await stageBox(page);
      const ratio = box.width * box.height / (1366 * 768);
      await writeFile(join(evidence, 'preview-1366.json'), JSON.stringify({ ...box, viewportAreaRatio: ratio }, null, 2));
      expect(ratio).toBeGreaterThanOrEqual(0.45);
      console.log(`1366x768: preview ${box.width}x${box.height}, ${(100 * ratio).toFixed(2)}% of the viewport; 45% area gate passed in every state and theme.`);
    }
  } finally {
    release();
    await page.unrouteAll({ behavior: 'wait' });
    await context.close();
  }
});
