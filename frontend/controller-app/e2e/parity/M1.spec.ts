import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { test, expect } from '../fixtures';
import { DeviceIdSchema } from '../../src/api/devices';
import { ConfigSchema } from '../../src/api/config';
import { CalibrationResponseSchema, DisplayResponseSchema } from '../../src/api/measure';
import { imageColors } from '../fixtures/fleet';

test.use({ serverScope: 'parity-M1' });
test("M1 Saving a profile appends a revision. The active layout's `profile_revision` pins do not change", async ({ server, api, tablets, page, writes, guard, axe, tabletPixel }, info) => {
  test.setTimeout(180_000);
  await guard(page);
  const [tablet] = await tablets(1);
  if (!tablet) throw new Error('A real tablet is required.');
  const id = DeviceIdSchema.parse(tablet.id);
  await expect.poll(async () => (await api.config()).runtime.devices[id]?.online).toBe(true);
  const initial = ConfigSchema.parse(await api.config());
  const viewport = initial.runtime.devices[id]?.viewport;
  if (!viewport) throw new Error('Tablet must report its viewport.');
  const displayResponse = await api.request.put(`/api/v3/displays/${id}`, { headers: { 'If-Match': initial.etag }, data: {
    active_width_mm: 200, active_height_mm: 112.5, bezels: { left: 0, right: 0, top: 0, bottom: 0 },
    panel_pixels: null, label: 'Measured tablet', provenance: 'manual',
  } });
  expect(displayResponse.ok(), await displayResponse.text()).toBe(true);
  const display = DisplayResponseSchema.parse(await displayResponse.json());
  const calibrationResponse = await api.request.put(`/api/v3/calibrations/${id}`, { headers: { 'If-Match': display.etag }, data: {
    profile_revision: display.display.revision, viewport_width: viewport.width, viewport_height: viewport.height,
    dpr: viewport.dpr, orientation: viewport.orientation, mode: viewport.mode, quarter_turn: 0,
    panel_offset_mm: [0, 0], mm_per_css: [0.25, 0.25], anchor_edge: 'top-left', uncertainty_mm: 0, method: 'manual', viewport_guard: true,
  } });
  expect(calibrationResponse.ok(), await calibrationResponse.text()).toBe(true);
  const calibration = CalibrationResponseSchema.parse(await calibrationResponse.json());
  const slot = { center_x_mm: 100, center_y_mm: 56.25, mount_angle: 0, nudge_x_mm: 0, nudge_y_mm: 0,
    profile_revision: display.display.revision, calibration_revision: calibration.calibration.revision };
  await api.placePhysical({ bounds: { x: 0, y: 0, width: 300, height: 168.75 }, slots: { [id]: slot } });
  const asset = await api.upload(fileURLToPath(new URL('../fixtures/images/two-colour.png', import.meta.url)));
  await api.scene({ type: 'image', asset: asset.id, fit: 'contain' });
  await expect.poll(async () => { const pixel = await tabletPixel(tablet, 590, 200); return Math.max(...imageColors.left.map((c, i) => Math.abs(c - (pixel[i] ?? -255)))); }).toBeLessThanOrEqual(3);
  const recorded = writes(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  await page.locator(`#tablet-row-${id}`).click();
  await page.getByRole('button', { name: 'Measure…', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Measure Tablet 1', exact: true })).toBeVisible();
  await expect(page.getByText('Measuring Tablet 1', { exact: true })).toBeVisible();
  if (info.project.name === 'desktop') {
    await expect(page.getByText('Finish measuring first.', { exact: true })).toBeVisible();
    await expect(page.getByText('two-colour.png, Fit · Measuring blanks only Tablet 1', { exact: true })).toBeVisible();
  }
  await page.getByLabel('Which model is it?').selectOption('manual');
  await mkdir('/tmp/u26-shots/3170a157', { recursive: true });
  async function capture(step: string) {
    for (const theme of ['light', 'dark'] as const) {
      const toggle = page.getByRole('button', { name: /^Theme:/ });
      for (let i = 0; i < 3 && await toggle.getAttribute('aria-label') !== `Theme: ${theme}`; i++) await toggle.click();
      await expect(toggle).toHaveAttribute('aria-label', `Theme: ${theme}`);
      await page.evaluate(() => { window.scrollTo(0, 0); return document.fonts.ready; });
      await page.mouse.move(0, 0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (info.project.name === 'desktop') {
        expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight)).toBe(true);
        const footer = await page.locator('.measure-footer').boundingBox();
        expect(footer && footer.y + footer.height).toBeLessThanOrEqual(900);
      }
      const path = `/tmp/u26-shots/3170a157/${step}-${info.project.use.viewport?.width}-${theme}.png`;
      await page.screenshot({ path, animations: 'disabled', fullPage: true });
      expect((await axe(page)).violations, `${step}/${theme} axe`).toEqual([]);
      await expect(page).toHaveScreenshot(`${step}-${theme}.png`);
      console.log(`${step} ${info.project.use.viewport?.width} ${theme}: axe 0; ${path}`);
    }
  }
  await capture('model');
  await page.getByRole('button', { name: 'Next: size and bezels', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Size and bezels', exact: true })).toBeFocused();
  await page.getByLabel('Width', { exact: true }).fill('');
  await page.getByRole('button', { name: 'Next: ruler check', exact: true }).click();
  await expect(page.getByLabel('Width', { exact: true })).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByLabel('Width', { exact: true })).toBeFocused();
  await page.getByLabel('Width', { exact: true }).fill('220');
  await page.getByLabel('Height', { exact: true }).fill('123.75');
  await expect(page.locator('[data-measure-overlay]')).toHaveAttribute('aria-label', 'Entered screen 220 by 123.75 millimetres');
  await capture('size');
  await page.getByRole('button', { name: 'Next: ruler check', exact: true }).click();
  await capture('ruler');
  await page.getByRole('button', { name: 'Skip', exact: true }).click();
  await capture('review');
  expect(recorded).toEqual([]);
  await page.getByRole('button', { name: 'Back', exact: true }).click();
  await page.getByRole('button', { name: 'Back', exact: true }).click();
  await expect(page.getByLabel('Width', { exact: true })).toHaveValue('220');
  await page.getByRole('button', { name: 'Next: ruler check', exact: true }).click();
  await page.getByRole('button', { name: 'Skip', exact: true }).click();
  await page.getByRole('button', { name: 'Save measurements', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Measure Tablet 1', exact: true })).toHaveCount(0);
  const saved = ConfigSchema.parse(await api.config());
  const latest = saved.displays.filter(p => p.device_id === id).sort((a, b) => b.revision - a.revision)[0];
  const latestCalibration = saved.calibrations.filter(c => c.device_id === id).sort((a, b) => b.revision - a.revision)[0];
  expect(latest?.revision).toBe(display.display.revision + 1);
  expect(latest?.active_width_mm).toBe(220);
  expect(latestCalibration?.profile_revision).toBe(latest?.revision);
  expect(latestCalibration?.mm_per_css).toEqual([0.275, 0.275]);
  expect(saved.layout.kind).toBe('physical');
  if (saved.layout.kind !== 'physical' || !latest || !latestCalibration) throw new Error('Saved physical measurements required.');
  expect(saved.layout.slots[id]?.profile_revision).toBe(slot.profile_revision);
  expect(saved.layout.slots[id]?.calibration_revision).toBe(slot.calibration_revision);
  expect(recorded.map(request => [request.method(), new URL(request.url()).pathname])).toEqual([
    ['PUT', `/api/v3/displays/${id}`], ['PUT', `/api/v3/calibrations/${id}`],
  ]);
  for (const request of recorded) expect(request.headers()['if-match']).toBeTruthy();
  expect(recorded[1]?.postDataJSON().viewport_guard).toBe(true);
  await expect.poll(async () => { const pixel = await tabletPixel(tablet, 590, 200); return Math.max(...imageColors.left.map((c, i) => Math.abs(c - (pixel[i] ?? -255)))); }).toBeLessThanOrEqual(3);
  await api.placePhysical({ bounds: saved.layout.bounds, slots: { [id]: { ...slot,
    profile_revision: latest.revision, calibration_revision: latestCalibration.revision } } });
  await expect.poll(async () => { const pixel = await tabletPixel(tablet, 590, 200); return Math.max(...imageColors.right.map((c, i) => Math.abs(c - (pixel[i] ?? -255)))); }).toBeLessThanOrEqual(3);
  await tablet.page.screenshot({ path: `/tmp/u26-shots/3170a157/tablet-new-scale-${info.project.name}.png` });
  console.log('M1: appended profile; active revision pins preserved; applying new pins changes real tablet pixels from red to blue.');
});
