import { fileURLToPath } from 'node:url';
import type { Locator, Page, WebSocketRoute } from '@playwright/test';
import type { Tablet } from '../fixtures';
import { ConfigSchema } from '../../src/api/config';
import { DeviceIdSchema } from '../../src/api/devices';
import { CalibrationResponseSchema, DisplayResponseSchema } from '../../src/api/measure';
import { test, expect } from '../fixtures';
import { fleet as fleetDevices } from '../fixtures/fleet';

test.use({ serverScope: 'parity-X5' });

const flyer = fileURLToPath(new URL('../fixtures/images/EXLENT_Cohort_3_Flyer_Temp.png', import.meta.url));
const twoColour = fileURLToPath(new URL('../fixtures/images/two-colour.png', import.meta.url));
const themes = ['light', 'dark'] as const;
type Theme = typeof themes[number];

async function setTheme(page: Page, theme: Theme) {
  const toggle = page.getByRole('button', { name: /^Theme:/ });
  for (let step = 0; step < 3 && await toggle.getAttribute('aria-label') !== `Theme: ${theme}`; step++) await toggle.click();
  await expect(toggle).toHaveAttribute('aria-label', `Theme: ${theme}`);
  await page.mouse.move(0, 0);
}

async function dynamicMask(page: Page): Promise<Locator[]> {
  const mask: Locator[] = [];
  for (const selector of ['.tablet-age', '[data-report-time]', '.join-address', '.join-code img', 'p:has-text("Checked at")']) {
    const locator = page.locator(selector);
    if (await locator.count()) mask.push(locator);
  }
  return mask;
}

async function prepare(page: Page) {
  await page.evaluate(() => {
    for (const element of document.querySelectorAll('*')) {
      if (element instanceof HTMLElement) { element.scrollTop = 0; element.scrollLeft = 0; }
    }
    window.scrollTo(0, 0);
    return document.fonts.ready;
  });
  await page.mouse.move(0, 0);
}

async function capture(page: Page, state: string) {
  for (const theme of themes) {
    await setTheme(page, theme);
    await prepare(page);
    await expect(page).toHaveScreenshot(`${state}-${theme}.png`, { fullPage: false, mask: await dynamicMask(page) });
  }
}

async function clickScreen(page: Page, id: string) {
  const screen = page.locator(`[data-stage="preview"] [data-screen="${id}"]`);
  const box = await screen.boundingBox();
  if (!box) throw new Error(`Tablet ${id} has no visible screen.`);
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
}

test('X5 Screenshots match the approved baselines', async ({ browser, server, api, tablets, page, guard }, info) => {
  test.setTimeout(600_000);
  const viewport = info.project.use.viewport;
  if (!viewport) throw new Error('X5 requires an explicit viewport.');
  await guard(page, { allow: [/\/api\/v3\/scene/] });
  const url = `${server.origin}/controller/app/`;

  let release = () => {};
  try {
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route('**/api/v3/config', async route => { await gate; await route.continue(); });
    await page.routeWebSocket('**/ws/controller?protocol=3', async socket => { await gate; socket.connectToServer(); });
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('button', { name: 'Connecting…' })).toBeVisible();
    await capture(page, 'loading');
    release();
    await expect(page.getByRole('heading', { name: 'Next step: add your first tablet' })).toBeVisible();
    await expect.poll(() => page.locator('.join-code img').evaluate(image => image instanceof HTMLImageElement && image.complete && image.naturalWidth > 0)).toBe(true);
    await capture(page, 'firstrun');
  } finally {
    release();
    await page.unrouteAll({ behavior: 'wait' });
  }

  const fleet: Tablet[] = [];
  for (const device of fleetDevices.slice(0, 4)) {
    fleet.push(...await tablets(1, { ids: [device.id] }));
    await expect.poll(async () => (await api.config()).runtime.devices[device.id]?.online).toBe(true);
  }
  await expect.poll(async () => Object.values((await api.config()).runtime.devices).filter(device => device.online).length).toBe(4);
  await api.placeLogical({ columns: 2, rows: 2, deviceIds: fleet.map(tablet => tablet.id) });
  const hero = await api.upload(flyer);
  await api.scene({ type: 'image', asset: hero.id, fit: 'cover' });
  await expect(page.locator('[data-stage="preview"] [data-screen]')).toHaveCount(4);
  await capture(page, 'main');
  await clickScreen(page, fleet[1]!.id);
  await expect(page.getByRole('heading', { name: 'Tablet 2', exact: true })).toBeVisible();
  await expect(page.locator('[data-fleet-power]')).toHaveText('All online tablets report wake lock denied.');
  await capture(page, 'selected');
  await page.getByRole('button', { name: 'Edit layout', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Edit layout', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await capture(page, 'arrange');
  await page.getByRole('button', { name: 'Edit layout', exact: true }).click();
  await page.getByRole('button', { name: 'Tablet details', exact: true }).click();
  await expect(page.getByRole('button', { name: 'All tablets', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'All tablets', exact: true }).click();

  await fleet[3]!.context.close();
  await expect(page.locator('#tablet-health .state-warn')).toHaveCount(1);
  await expect(page.locator('[data-stage="preview"] [data-status="offline"]')).toHaveCount(1);
  await capture(page, 'offline');
  await tablets(1, { ids: [fleetDevices[3]!.id] });
  await expect(page.locator('#tablet-health .state-ok')).toHaveCount(4);

  await api.upload(twoColour);
  await page.reload({ waitUntil: 'networkidle' });
  await page.getByRole('button', { name: 'two-colour.png', exact: true }).click();
  await page.route('**/api/v3/scene', route => route.fulfill({ status: 503, json: { detail: 'upstream busy' } }));
  await page.getByRole('button', { name: 'Show on wall', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Next step: refresh' })).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('.desktop-onwall, .mobile-onwall').filter({ visible: true }).getByText('Not confirmed')).toBeVisible();
  await capture(page, 'uncertain');
  await page.unroute('**/api/v3/scene');

  const ids = [fleet[0]!.id, fleet[1]!.id];
  const saveAs = async (name: string, grid: Parameters<typeof api.placeLogical>[0]) => {
    const placed = await api.placeLogical(grid);
    const saved = await api.request.put(`/api/v3/logical-layouts/${name}`, { headers: { 'If-Match': placed.etag } });
    expect(saved.ok(), await saved.text()).toBe(true);
  };
  await saveAs('Wide', { columns: 2, rows: 1, deviceIds: ids });
  await saveAs('Offset', { columns: 2, rows: 1, deviceIds: ids, cellWidth: 900 });
  await saveAs('Tall', { columns: 1, rows: 2, deviceIds: ids });
  const mine = await (await browser.newContext({ viewport, hasTouch: viewport.width < 1024 })).newPage();
  const other = await (await browser.newContext({ viewport, hasTouch: viewport.width < 1024 })).newPage();
  await guard(mine);
  await guard(other);
  try {
    await mine.goto(url, { waitUntil: 'networkidle' });
    await other.goto(url, { waitUntil: 'networkidle' });
    await mine.getByRole('tab', { name: 'Layouts', exact: true }).click();
    await mine.getByRole('button', { name: 'Wide', exact: true }).click();
    await other.getByRole('tab', { name: 'Layouts', exact: true }).click();
    await other.getByRole('button', { name: 'Offset', exact: true }).click();
    await other.getByRole('button', { name: 'Apply layout', exact: true }).click();
    await expect(mine.locator('#conflict')).toBeVisible();
    await expect(mine.locator('#conflict')).toContainText('Review the change');
    await capture(mine, 'conflict');
  } finally {
    await mine.context().close();
    await other.context().close();
  }

  const measured = DeviceIdSchema.parse(fleet[1]!.id);
  const before = ConfigSchema.parse(await api.config());
  const measuredViewport = before.runtime.devices[measured]?.viewport;
  if (!measuredViewport) throw new Error('The measured tablet must report its viewport.');
  const displayResponse = await api.request.put(`/api/v3/displays/${measured}`, { headers: { 'If-Match': before.etag }, data: {
    active_width_mm: 200, active_height_mm: 112.5, bezels: { left: 0, right: 0, top: 0, bottom: 0 },
    panel_pixels: null, label: 'Measured tablet', provenance: 'manual',
  } });
  expect(displayResponse.ok(), await displayResponse.text()).toBe(true);
  const display = DisplayResponseSchema.parse(await displayResponse.json());
  const calibrationResponse = await api.request.put(`/api/v3/calibrations/${measured}`, { headers: { 'If-Match': display.etag }, data: {
    profile_revision: display.display.revision, viewport_width: measuredViewport.width, viewport_height: measuredViewport.height,
    dpr: measuredViewport.dpr, orientation: measuredViewport.orientation, mode: measuredViewport.mode, quarter_turn: 0,
    panel_offset_mm: [0, 0], mm_per_css: [0.25, 0.25], anchor_edge: 'top-left', uncertainty_mm: 0, method: 'manual', viewport_guard: true,
  } });
  expect(calibrationResponse.ok(), await calibrationResponse.text()).toBe(true);
  const calibration = CalibrationResponseSchema.parse(await calibrationResponse.json());
  const slot = { center_x_mm: 100, center_y_mm: 56.25, mount_angle: 0, nudge_x_mm: 0, nudge_y_mm: 0,
    profile_revision: display.display.revision, calibration_revision: calibration.calibration.revision };
  await api.placePhysical({ bounds: { x: 0, y: 0, width: 300, height: 168.75 }, slots: { [measured]: slot } });
  await page.reload({ waitUntil: 'networkidle' });
  await page.locator(`#tablet-row-${measured}`).click();
  await page.getByRole('button', { name: 'Measure…', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Measure Tablet 2', exact: true })).toBeVisible();
  await page.getByLabel('Which model is it?').selectOption('manual');
  await capture(page, 'measure-model');
  await page.getByRole('button', { name: 'Next: size and bezels', exact: true }).click();
  await page.getByLabel('Width', { exact: true }).fill('220');
  await page.getByLabel('Height', { exact: true }).fill('123.75');
  await capture(page, 'measure-size');
  await page.getByRole('button', { name: 'Next: ruler check', exact: true }).click();
  await capture(page, 'measure-ruler');
  await page.getByRole('button', { name: 'Skip', exact: true }).click();
  await capture(page, 'measure-review');
  await page.reload({ waitUntil: 'networkidle' });

  async function sheetShot(state: string, tab?: string) {
    for (const theme of themes) {
      await setTheme(page, theme);
      await page.getByRole('button', { name: 'Server', exact: true }).click();
      const sheet = page.getByRole('dialog', { name: 'Server', exact: true });
      await expect(sheet).toBeVisible();
      if (tab) await sheet.getByRole('tab', { name: tab }).click();
      if (state === 'server') await expect(sheet.getByText('All checks pass', { exact: true })).toBeVisible();
      await prepare(page);
      await expect(page).toHaveScreenshot(`${state}-${theme}.png`, { fullPage: false, mask: await dynamicMask(page) });
      await page.keyboard.press('Escape');
      await expect(sheet).toHaveCount(0);
    }
  }
  await sheetShot('server');
  await sheetShot('data', 'Backup and reset');

  await page.getByRole('button', { name: 'Server', exact: true }).click();
  const setupSheet = page.getByRole('dialog', { name: 'Server', exact: true });
  await setupSheet.getByRole('tab', { name: 'Playback' }).click();
  await setupSheet.getByRole('switch', { name: /Playlist and playback/ }).check();
  await setupSheet.getByLabel('Image to add').selectOption({ label: 'two-colour.png' });
  await setupSheet.getByRole('button', { name: 'Add', exact: true }).click();
  await setupSheet.getByLabel('two-colour.png: seconds on screen').fill('3');
  await setupSheet.getByRole('button', { name: 'Save playlist' }).click();
  await expect(setupSheet.getByText('Playlist saved.')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(setupSheet).toHaveCount(0);
  await sheetShot('playback', 'Playback');

  for (const theme of themes) {
    await setTheme(page, theme);
    await page.getByRole('button', { name: 'All images' }).click();
    const library = page.getByRole('dialog', { name: 'Library', exact: true });
    await expect(library).toBeVisible();
    await prepare(page);
    await expect(page).toHaveScreenshot(`library-${theme}.png`, { fullPage: false, mask: await dynamicMask(page) });
    await page.keyboard.press('Escape');
    await expect(library).toHaveCount(0);
  }

  const offlineContext = await browser.newContext({ viewport, hasTouch: viewport.width < 1024 });
  try {
    const offlinePage = await offlineContext.newPage();
    const sockets: WebSocketRoute[] = [];
    let disconnected = false;
    await offlinePage.routeWebSocket('**/ws/controller?protocol=3', socket => {
      if (disconnected) return;
      sockets.push(socket);
      socket.connectToServer();
    });
    await offlinePage.goto(url, { waitUntil: 'networkidle' });
    await expect(offlinePage.locator('#tablet-health .row').first()).toBeVisible();
    disconnected = true;
    await offlineContext.setOffline(true);
    await Promise.all(sockets.map(socket => socket.close({ code: 1001 })));
    await offlinePage.evaluate(() => window.dispatchEvent(new Event('online')));
    await expect(offlinePage.getByRole('heading', { name: 'Next step: wait for the server' })).toBeVisible();
    await capture(offlinePage, 'unreachable');
  } finally {
    await offlineContext.close();
  }
});
