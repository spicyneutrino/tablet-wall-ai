import { test, expect } from '../fixtures';
import { DeviceIdSchema } from '../../src/api/devices';
import { ConfigSchema } from '../../src/api/config';
import { DisplayResponseSchema } from '../../src/api/measure';

test.use({ serverScope: 'parity-M3' });
test('M3 Calibration save with a mismatched viewport gets 409, and the message names the fix', async ({ server, api, tablets, page, writes }) => {
  const consoleErrors: string[] = [];
  page.on('pageerror', error => consoleErrors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  const [tablet] = await tablets(1);
  if (!tablet) throw new Error('A real tablet is required.');
  const id = DeviceIdSchema.parse(tablet.id);
  await expect.poll(async () => (await api.config()).runtime.devices[id]?.online).toBe(true);
  const initial = ConfigSchema.parse(await api.config());
  const response = await api.request.put(`/api/v3/displays/${id}`, { headers: { 'If-Match': initial.etag }, data: {
    active_width_mm: 200, active_height_mm: 112.5, bezels: { left: 0, right: 0, top: 0, bottom: 0 },
    panel_pixels: null, label: 'Measured tablet', provenance: 'manual',
  } });
  expect(response.ok(), await response.text()).toBe(true);
  DisplayResponseSchema.parse(await response.json());
  await api.placeLogical({ columns: 1, rows: 1, deviceIds: [id] });
  const recorded = writes(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  await page.locator(`#tablet-row-${id}`).click();
  await page.getByRole('button', { name: 'Measure…', exact: true }).click();
  await page.getByLabel('Which model is it?').selectOption('manual');
  await page.getByRole('button', { name: 'Next: size and bezels', exact: true }).click();
  await page.getByRole('button', { name: 'Next: ruler check', exact: true }).click();
  await page.getByRole('button', { name: 'Skip', exact: true }).click();
  await page.getByText('Advanced: quarter turn, anchor, offsets', { exact: true }).click();
  await page.getByLabel('Viewport width', { exact: true }).fill('700');
  const rejected = page.waitForResponse(response => new URL(response.url()).pathname === `/api/v3/calibrations/${id}` && response.request().method() === 'PUT');
  await page.getByRole('button', { name: 'Save measurements', exact: true }).click();
  const result = await rejected;
  expect(result.status()).toBe(409);
  await expect(page.locator('.measure-error')).toContainText('Return to Ruler check, restore the tablet viewport at 100% zoom, and check again.');
  await expect(page.getByRole('heading', { name: 'Measure Tablet 1', exact: true })).toBeVisible();
  await expect(page.getByLabel('Viewport width', { exact: true })).toHaveValue('700');
  expect(recorded.map(request => request.method())).toEqual(['PUT', 'PUT']);
  for (const request of recorded) expect(request.headers()['if-match']).toBeTruthy();
  expect(recorded[1]?.postDataJSON().viewport_guard).toBe(true);
  const saved = ConfigSchema.parse(await api.config());
  expect(saved.displays.filter(profile => profile.device_id === id)).toHaveLength(1);
  expect(saved.displays.find(profile => profile.device_id === id)?.revision).toBe(2);
  expect(saved.calibrations.filter(calibration => calibration.device_id === id)).toHaveLength(0);
  expect(consoleErrors.every(error => /409 \(Conflict\)/.test(error)), consoleErrors.join('\n')).toBe(true);
  await page.getByLabel('Viewport width', { exact: true }).fill('800');
  await page.getByRole('button', { name: 'Save measurements', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Measure Tablet 1', exact: true })).toHaveCount(0);
  const recovered = ConfigSchema.parse(await api.config());
  expect(recovered.calibrations.find(calibration => calibration.device_id === id)?.profile_revision).toBe(3);
  console.log('M3: real backend 409; saved profile receipt retained; mismatched calibration not saved; inline fix names viewport, zoom and recheck.');
});
