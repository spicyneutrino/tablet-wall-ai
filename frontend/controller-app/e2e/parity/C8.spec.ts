import { test, expect } from '../fixtures';
import type { Tablet } from '../fixtures';
import { ConfigSchema } from '../../src/api/config';

test.use({ serverScope: 'parity-C8' });

const background = (pixel: number[]) => pixel.slice(0, 3).every(channel => channel >= 200);
const black = (pixel: number[]) => pixel.slice(0, 3).every(channel => channel <= 20);

async function readyPixels(tablet: Tablet, tabletPixel: (tablet: Tablet, x: number, y: number) => Promise<number[]>,
  ok: (pixel: number[]) => boolean, message: string) {
  await expect.poll(async () => {
    const seen = await Promise.all([37, 211, 403].flatMap(x => [53, 149, 337]
      .map(y => tabletPixel(tablet, x, y))));
    return seen.filter(ok).length;
  }, { timeout: 15_000, message }).toBeGreaterThanOrEqual(7);
}

test('C8 Test patterns (grid, black) and colours (all tablets, one tablet) reach the tablets', async ({
  server, api, tablets, tabletPixel, guard, writes, axe, page,
}, info) => {
  test.setTimeout(180_000);
  const config = async () => ConfigSchema.parse(await (await api.request.get('/api/v3/config')).json());
  await guard(page);
  const recorded = writes(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });

  const fleet: Tablet[] = await tablets(4);
  await expect.poll(async () => {
    const config = await api.config();
    return fleet.map(({ id }) => config.runtime.devices[id]?.online);
  }, { timeout: 15_000 }).toEqual([true, true, true, true]);

  for (const [index, tablet] of fleet.entries()) {
    const { etag } = await api.config();
    const display = await api.request.put(`/api/v3/displays/${tablet.id}`, { headers: { 'If-Match': etag }, data: {
      active_width_mm: 400, active_height_mm: 225,
      bezels: { left: 0, top: 0, right: 0, bottom: 0 },
      label: `Tablet ${index + 1}`, provenance: 'hand-derived',
    } });
    expect(display.ok(), await display.text()).toBe(true);
    const calibration = await api.request.put(`/api/v3/calibrations/${tablet.id}`, {
      headers: { 'If-Match': (await display.json()).etag }, data: {
        profile_revision: 1, viewport_width: 800, viewport_height: 450, dpr: 1,
        orientation: 0, mode: 'tab', quarter_turn: 0, panel_offset_mm: [0, 0],
        mm_per_css: [0.5, 0.5], anchor_edge: 'top-left', uncertainty_mm: 0, method: 'hand-derived',
      },
    });
    expect(calibration.ok(), await calibration.text()).toBe(true);
  }
  const layout = await api.request.put('/api/v3/layout', {
    headers: { 'If-Match': (await api.config()).etag }, data: {
      bounds: { x: 0, y: 0, width: 1720, height: 250 },
      slots: Object.fromEntries(fleet.map((tablet, index) => [tablet.id, {
        center_x_mm: 220 + 430 * index, center_y_mm: 125, mount_angle: 0,
        nudge_x_mm: 0, nudge_y_mm: 0, profile_revision: 1, calibration_revision: 1, participating: true,
      }])),
    },
  });
  expect(layout.ok(), await layout.text()).toBe(true);
  await expect(page.locator('[data-stage="preview"] [data-screen]')).toHaveCount(4);

  await page.getByRole('tab', { name: 'Tests' }).click();
  await expect(page.getByRole('button', { name: 'Calibration grid' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Black' })).toBeVisible();
  for (const name of ['Red', 'Green', 'Blue', 'White', 'Black']) await expect(page.getByLabel(name)).toBeVisible();

  recorded.length = 0;
  await page.getByRole('button', { name: 'Calibration grid' }).click();
  await expect(page.getByRole('button', { name: 'Calibration grid' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('section[aria-label="Preview"] .monitor-description').first()).toHaveText('Calibration grid, not on the wall yet');
  expect(recorded).toEqual([]);

  const gridEtag = (await api.config()).etag;
  await page.getByRole('button', { name: 'Show on wall' }).click();
  await expect.poll(() => recorded.length, { timeout: 15_000 }).toBe(2);
  const [gridPost, gridScene] = recorded;
  expect(gridPost?.method()).toBe('POST');
  expect(new URL(gridPost!.url()).pathname).toBe('/api/v3/test-pattern');
  expect(gridPost?.postDataJSON()).toEqual({ pattern: 'grid' });
  expect(gridPost?.headers()['if-match']).toBe(gridEtag);
  expect(gridScene?.method()).toBe('PUT');
  expect(new URL(gridScene!.url()).pathname).toBe('/api/v3/scene');
  expect(gridScene?.headers()['if-match']).toBeTruthy();
  await expect.poll(async () => (await config()).scene.content.type, { timeout: 15_000 }).toBe('image');
  const gridContent = (await config()).scene.content;
  if (gridContent.type !== 'image') throw new Error('The grid must be selected as an image scene.');
  expect(gridContent.fit).toBe('contain');
  expect(gridScene?.postDataJSON()).toEqual({ content: { type: 'image', asset: gridContent.asset, fit: 'contain' } });
  await expect(page.getByText('Test pattern on the wall.')).toBeVisible();
  for (const tablet of fleet) {
    await readyPixels(tablet, tabletPixel, background, `${tablet.id} shows the calibration grid`);
  }

  recorded.length = 0;
  await page.getByRole('button', { name: 'Black' }).click();
  await expect(page.getByRole('button', { name: 'Black' })).toHaveAttribute('aria-pressed', 'true');
  expect(recorded).toEqual([]);
  await page.getByRole('button', { name: 'Show on wall' }).click();
  await expect.poll(() => recorded.length, { timeout: 15_000 }).toBe(2);
  expect(recorded[0]?.postDataJSON()).toEqual({ pattern: 'black' });
  expect(new URL(recorded[0]!.url()).pathname).toBe('/api/v3/test-pattern');
  expect(new URL(recorded[1]!.url()).pathname).toBe('/api/v3/scene');
  for (const tablet of fleet) {
    await readyPixels(tablet, tabletPixel, black, `${tablet.id} shows black`);
  }

  await api.scene({ type: 'color' });
  recorded.length = 0;
  await page.getByLabel('Red').click();
  await page.getByRole('button', { name: 'All tablets' }).click();
  await expect.poll(() => recorded.length, { timeout: 15_000 }).toBe(1);
  expect(recorded[0]?.method()).toBe('POST');
  expect(new URL(recorded[0]!.url()).pathname).toBe('/devices/color');
  expect(recorded[0]?.postDataJSON()).toEqual({ color: '#ef4444' });
  expect(recorded[0]?.headers()).not.toHaveProperty('if-match');
  await expect(page.getByText('Sent to 4 tablets')).toBeVisible();
  for (const tablet of fleet) {
    await expect.poll(() => tablet.page.evaluate(() =>
      getComputedStyle(document.documentElement).backgroundColor), { timeout: 15_000 })
      .toBe('rgb(239, 68, 68)');
  }

  await page.locator('#tablet-health .row').first().click();
  const one = page.getByRole('button', { name: /^This tablet: / });
  await expect(one).toBeVisible();
  const chosenName = (await one.locator('.btn-rest').textContent())!.replace('This tablet: ', '').trim();
  recorded.length = 0;
  await page.getByLabel('Blue').click();
  await one.click();
  await expect.poll(() => recorded.length, { timeout: 15_000 }).toBe(1);
  expect(recorded[0]?.method()).toBe('POST');
  const chosenMatch = /^\/devices\/([0-9a-f-]{36})\/color$/i.exec(new URL(recorded[0]!.url()).pathname);
  expect(chosenMatch).not.toBeNull();
  const chosen = fleet.find(tablet => tablet.id === chosenMatch![1]);
  if (!chosen) throw new Error('The colour command must name a joined tablet.');
  expect(recorded[0]?.postDataJSON()).toEqual({ color: '#3b82f6' });
  await expect(page.getByText(`Sent to ${chosenName}`)).toBeVisible();
  await expect.poll(() => chosen.page.evaluate(() =>
    getComputedStyle(document.documentElement).backgroundColor), { timeout: 15_000 }).toBe('rgb(59, 130, 246)');
  for (const tablet of fleet.filter(tablet => tablet.id !== chosen.id)) {
    await expect.poll(() => tablet.page.evaluate(() =>
      getComputedStyle(document.documentElement).backgroundColor), { timeout: 15_000 }).toBe('rgb(239, 68, 68)');
  }

  expect((await axe(page)).violations).toEqual([]);
  console.log(`${info.project.name}: C8 grid, black and colours reached 4 tablets`);
});
