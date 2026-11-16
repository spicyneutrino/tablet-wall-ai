import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { basename } from 'node:path';
import { test, expect } from '../fixtures';
import type { Tablet } from '../fixtures';
import { fleet as devices } from '../fixtures/fleet';
import { ConfigSchema } from '../../src/api/config';

const evidence = `/tmp/u22-shots/${basename(fileURLToPath(new URL('../../../../', import.meta.url)))}`;
const image = fileURLToPath(new URL('../fixtures/images/EXLENT_Cohort_3_Flyer_Temp.png', import.meta.url));
test.use({ serverScope: 'parity-A4' });

test('A4 Logical: fixed and fit-to-tablets sizing, pack, tile, custom bounds, rotate (with bezels rotated). Physical: 0/90/180/270 and arbitrary angles, nudge, participation off (bounds unchanged), mixed models', async ({ browser, server, api, tablets, writes, guard, axe }, info) => {
  test.setTimeout(180_000);
  const context = await browser.newContext({ viewport: info.project.use.viewport, bypassCSP: true });
  const page = await context.newPage();
  await guard(page);
  let staleRoster = false;
  await page.routeWebSocket('**/ws/controller?protocol=3', socket => {
    const upstream = socket.connectToServer();
    upstream.onMessage(message => { if (!staleRoster) socket.send(message); });
  });
  const fleet: Tablet[] = [];
  for (const device of devices) fleet.push(...await tablets(1, { ids: [device.id] }));
  const ids = fleet.map(tablet => tablet.id);
  async function put(path: string, data: unknown) {
    const response = await api.request.put(path, { headers: { 'If-Match': (await api.config()).etag }, data });
    expect(response.ok(), await response.text()).toBe(true);
    return response;
  }
  async function field(label: string, value: string) {
    const input = page.getByLabel(label, { exact: true });
    await input.fill(value); await input.press('Enter');
  }
  async function tool(name: string) {
    await page.getByRole('button', { name: 'Layout tools', exact: true }).click();
    await page.getByRole('menuitem', { name, exact: true }).click();
  }
  async function select(id: string) {
    await page.locator(`[data-edit-overlay] [data-edit-id="${id}"][role="button"]`).first().click();
  }
  try {
    await api.placeLogical({ columns: 3, rows: 2, deviceIds: ids, cellWidth: 200, cellHeight: 180 });
    const base = ConfigSchema.parse(await api.config());
    if (base.layout.kind !== 'logical') throw new Error('Expected logical layout');
    await put('/api/v3/logical-layout', { width: 600, height: 400, sizing: base.layout.sizing,
      placements: Object.fromEntries(Object.entries(base.layout.placements).map(([id, placement]) => [id,
        { ...placement, bezel: { top: 20, right: 30, bottom: 40, left: 10 } }])) });
    await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
    const sent = writes(page);
    const screen = await page.locator(`[data-stage="preview"] [data-screen="${ids[0]}"]`).boundingBox();
    if (!screen) throw new Error('Placed tablet screen must be visible');
    await page.mouse.click(screen.x + screen.width / 2, screen.y + screen.height / 2);
    await page.getByRole('button', { name: 'Tablet details', exact: true }).click();
    await page.getByRole('button', { name: 'Edit layout', exact: true }).click();
    await select(ids[1]!);
    await expect(page.getByRole('heading', { name: 'Tablet 2', exact: true })).toBeVisible();
    await field('Width', '1');
    await expect(page.getByRole('button', { name: 'Apply layout', exact: true })).toBeDisabled();
    await expect(page.getByText('Bezels leave no visible width. Reduce the left or right bezel.', { exact: true }).first()).toBeVisible();
    await field('Width', '200');
    await page.getByRole('button', { name: 'Turn 90 degrees', exact: true }).click();
    await expect(page.getByLabel('Width', { exact: true })).toHaveValue('180');
    await expect(page.getByLabel('Height', { exact: true })).toHaveValue('200');
    for (const [label, value] of [['Top bezel', '10'], ['Right bezel', '20'], ['Bottom bezel', '30'], ['Left bezel', '40']]) {
      await expect(page.getByLabel(label!, { exact: true })).toHaveValue(value!);
    }
    await page.getByRole('button', { name: 'Undo layout edit', exact: true }).click();
    await page.route('**/api/v3/config', async route => {
      const response = await route.fetch();
      const config = ConfigSchema.parse(await response.json());
      const runtime = Object.fromEntries(Object.entries(config.runtime).filter(([key]) => key !== 'devices'));
      await route.fulfill({ response, json: { ...config, runtime } });
    });
    await page.route('**/devices', route => route.fulfill({ json: [] }));
    staleRoster = true;
    await page.evaluate(() => window.dispatchEvent(new Event('online')));
    await expect(page.getByText(/Status stale\. Invalid tablet roster/)).toBeVisible();
    await page.getByRole('button', { name: 'Layout tools', exact: true }).click();
    const match = page.getByRole('menuitem', { name: 'Match screen shape', exact: true });
    await expect(match).toBeDisabled();
    await expect(match).toHaveAttribute('aria-description', 'Tablet status is stale. Refresh status or reconnect before matching the screen shape.');
    await match.click({ force: true });
    await expect(page.getByLabel('Height', { exact: true })).toHaveValue('180');
    expect(sent).toEqual([]);
    await page.keyboard.press('Escape');
    staleRoster = false;
    await page.unroute('**/api/v3/config');
    await page.unroute('**/devices');
    await page.evaluate(() => window.dispatchEvent(new Event('online')));
    await expect(page.getByText(/Status stale\. Invalid tablet roster/)).toHaveCount(0);
    await tool('Match screen shape');
    await expect(page.getByLabel('Height', { exact: true })).toHaveValue('150');
    await tool('Fit to tablets');
    await tool('Wall bounds');
    const bounds = page.getByRole('dialog', { name: 'Wall bounds', exact: true });
    await expect(bounds.getByLabel('Wall sizing')).toHaveValue('tablets');
    await expect(bounds.getByLabel('Wall width')).toBeDisabled();
    await field('Outer padding', '12');
    await bounds.getByLabel('Wall sizing').selectOption('fixed');
    await field('Wall width', '1000'); await field('Wall height', '800');
    await bounds.getByRole('button', { name: 'Done', exact: true }).click();
    await tool('Pack');
    const pack = page.getByRole('dialog', { name: 'Pack tablets', exact: true });
    await pack.getByLabel('Columns').fill('2'); await pack.getByLabel('Rows').fill('2'); await pack.getByLabel('Gap (units)').fill('24');
    await pack.getByRole('button', { name: 'Pack tablets', exact: true }).click();
    await expect(page.getByLabel('X', { exact: true })).toHaveValue('236');
    await tool('Tile');
    const tile = page.getByRole('dialog', { name: 'Tile tablets', exact: true });
    await tile.getByLabel('Columns').fill('2'); await tile.getByLabel('Rows').fill('2');
    await tile.getByLabel('Screen shape').selectOption('fill');
    await tile.getByRole('button', { name: 'Tile tablets', exact: true }).click();
    await expect(page.getByLabel('Width', { exact: true })).toHaveValue('488');
    expect(sent).toEqual([]);
    await page.getByRole('button', { name: 'Apply layout', exact: true }).click();
    await expect(page.getByText('Layout applied.', { exact: true })).toBeVisible();
    const logical = ConfigSchema.parse(await api.config());
    expect(logical.layout).toMatchObject({ width: 1000, height: 800, sizing: { mode: 'fixed', padding: 12 } });
    expect(sent).toHaveLength(1);
    await page.getByRole('button', { name: 'Discard', exact: true }).click();

    for (const [index, id] of ids.entries()) {
      const width = 110 + index * 10, height = 70 + index * 5;
      await put(`/api/v3/displays/${id}`, { active_width_mm: width, active_height_mm: height,
        bezels: { top: 10, right: 10, bottom: 10, left: 10 }, panel_pixels: { width: 800, height: 450 },
        label: `Measured model ${index + 1}`, provenance: 'manual' });
      await put(`/api/v3/calibrations/${id}`, { profile_revision: 1, viewport_width: 800, viewport_height: 450,
        dpr: 1, orientation: 0, mode: 'tab', quarter_turn: 0, panel_offset_mm: [0, 0], mm_per_css: [width / 800, height / 450],
        anchor_edge: 'top-left', uncertainty_mm: 0.5, method: 'manual' });
    }
    await put('/api/v3/layout', { bounds: { x: 0, y: 0, width: 540, height: 400 }, sizing: { mode: 'fixed', padding: 0 },
      slots: Object.fromEntries(ids.map((id, index) => [id, {
        center_x_mm: index % 2 ? 350 : 130, center_y_mm: index < 2 ? 100 : 280,
        mount_angle: [0, 90, 180, 270][index], nudge_x_mm: 0, nudge_y_mm: 0, profile_revision: 1, calibration_revision: 1, participating: true,
      }])) });
    const asset = await api.upload(image); await api.scene({ type: 'image', asset: asset.id, fit: 'cover' });
    await page.getByRole('button', { name: 'Edit layout', exact: true }).click();
    for (const [index, id] of ids.entries()) {
      await select(id); await expect(page.getByLabel('Turn (degrees)')).toHaveValue(String([0, 90, 180, 270][index]));
    }
    await select(ids[1]!);
    await expect(page.getByLabel('Turn (degrees)')).toHaveValue('90');
    await field('Nudge X (mm)', '15'); await field('Nudge Y (mm)', '-5');
    await expect(page.locator('[data-position-readout]').locator('..')).toContainText('Centre + nudge');
    await expect(page.locator('[data-position-readout]')).toContainText('x 365');
    await expect(page.getByLabel('Centre X (mm)')).toHaveValue('350');
    const participating = page.getByRole('switch', { name: 'Participating' });
    await participating.uncheck();
    await tool('Wall bounds');
    await expect(page.getByLabel('Wall width', { exact: true })).toHaveValue('540');
    await expect(page.getByLabel('Wall height', { exact: true })).toHaveValue('400');
    await page.getByRole('button', { name: 'Done', exact: true }).click();
    await participating.check();
    await field('Turn (degrees)', '37');
    const mutations = sent.length;
    await tool('Pack');
    await page.getByRole('dialog').getByRole('button', { name: 'Pack tablets', exact: true }).click();
    await page.getByRole('button', { name: 'Undo layout edit', exact: true }).click();
    await tool('Fit to tablets');
    const fittedBounds = await page.locator('[data-edit-overlay]').getAttribute('viewBox');
    await participating.uncheck();
    expect(await page.locator('[data-edit-overlay]').getAttribute('viewBox')).toBe(fittedBounds);
    await page.getByRole('button', { name: 'Undo layout edit', exact: true }).click();
    await page.getByRole('button', { name: 'Undo layout edit', exact: true }).click();
    expect(sent).toHaveLength(mutations);
    await page.getByRole('tab', { name: 'Layouts', exact: true }).click();
    await mkdir(evidence, { recursive: true });
    for (const theme of ['light', 'dark']) {
      const toggle = page.getByRole('button', { name: /^Theme:/ });
      for (let turn = 0; turn < 3 && await toggle.getAttribute('aria-label') !== `Theme: ${theme}`; turn++) await toggle.click();
      await expect(toggle).toHaveAttribute('aria-label', `Theme: ${theme}`);
      await page.evaluate(() => { window.scrollTo(0, 0); document.querySelector('.sidebar-scroll')?.scrollTo(0, 0); });
      await page.evaluate(() => document.fonts.ready);
      await page.mouse.move(0, 0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const audit = await axe(page); expect(audit.violations).toEqual([]);
      const width = info.project.use.viewport?.width;
      await page.screenshot({ path: `${evidence}/arrange-${width}-${theme}.png`, animations: 'disabled' });
      console.log(`arrange ${width} ${theme}: axe ${audit.violations.length}; ${evidence}/arrange-${width}-${theme}.png`);
    }
    await page.getByRole('button', { name: 'Apply layout', exact: true }).click();
    await expect(page.getByText('Layout applied.', { exact: true })).toBeVisible();
    expect(sent).toHaveLength(mutations + 1);
    const physical = ConfigSchema.parse(await api.config());
    expect(physical.layout).toMatchObject({ kind: 'physical', bounds: { width: 540, height: 400 },
      slots: { [ids[1]!]: { mount_angle: 37, center_x_mm: 350, nudge_x_mm: 15, nudge_y_mm: -5, participating: true } } });
  } finally { await context.close(); }
});
