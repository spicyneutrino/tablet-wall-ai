import { test, expect } from '../fixtures';
import { ConfigSchema } from '../../src/api/config';
import { DeviceIdSchema } from '../../src/api/devices';

test.use({ serverScope: 'parity-T2' });
test('T2 Form drafts are kept per device when switching tablets and when a remote update arrives', async ({ page, server, api, tablets, writes, guard }) => {
  test.setTimeout(120_000);
  await guard(page);
  const fleet = await tablets(2);
  const [first, second] = fleet;
  if (!first || !second) throw new Error('Two real tablets are required.');
  await api.placeLogical({ columns: 2, rows: 1, deviceIds: [first.id, second.id] });
  await expect.poll(async () => {
    const config = await api.config();
    return fleet.map(({ id }) => config.runtime.devices[id]?.render.state);
  }).toEqual(['displayed', 'displayed']);
  const recorded = writes(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  const name = page.getByLabel('Name', { exact: true });
  const model = page.getByLabel('Model', { exact: true });

  await page.locator(`#tablet-row-${first.id}`).click();
  await expect(page.locator('#tablet-title')).toBeVisible();
  await name.fill('A draft');
  await model.selectOption('manual');

  await page.locator(`#tablet-row-${second.id}`).click();
  await expect(name).toHaveValue('');
  await name.fill('B draft');
  await model.selectOption('google-pixel-c');

  await page.locator(`#tablet-row-${first.id}`).click();
  await expect(name).toHaveValue('A draft');
  await expect(model).toHaveValue('manual');

  await page.locator(`#tablet-row-${second.id}`).click();
  await expect(name).toHaveValue('B draft');
  await expect(model).toHaveValue('google-pixel-c');
  expect(recorded).toEqual([]);

  // A remote rename arrives while the first tablet's name draft is dirty.
  const beforeName = await api.config();
  const renamed = await api.request.patch(`/api/v3/devices/${first.id}`, {
    headers: { 'If-Match': beforeName.etag }, data: { label: 'Remote name' } });
  expect(renamed.ok(), await renamed.text()).toBe(true);
  await page.locator(`#tablet-row-${first.id}`).click();
  await expect(page.locator('#tablet-title')).toHaveText('Remote name');
  await expect(name).toHaveValue('A draft');
  await expect(page.getByText('The saved name changed elsewhere. Keep yours or use the current name.')).toBeVisible();

  // A remote model change arrives while the second tablet's model draft is dirty.
  const beforeModel = await api.config();
  const assigned = await api.request.put(`/api/v3/tablet-assignments/${second.id}`, {
    headers: { 'If-Match': beforeModel.etag }, data: { mode: 'explicit', model_id: 'ipad-air-2' } });
  expect(assigned.ok(), await assigned.text()).toBe(true);
  await page.locator(`#tablet-row-${second.id}`).click();
  await expect(page.locator('.tablet-facts')).toContainText('iPad Air 2');
  await expect(model).toHaveValue('google-pixel-c');
  await expect(page.getByText('The saved model changed elsewhere. Keep yours or use the current model.')).toBeVisible();
  await expect(name).toHaveValue('B draft');

  // Keep mine rebases the draft on the current wall, so the next save is guarded by the new revision.
  await page.getByRole('button', { name: 'Keep my model', exact: true }).click();
  await expect(page.getByText('The saved model changed elsewhere. Keep yours or use the current model.')).toHaveCount(0);
  const modelGuard = (await api.config()).etag;
  await page.getByRole('button', { name: 'Save model', exact: true }).click();
  await expect(page.getByText('Model saved. Measured readiness is checked separately.', { exact: true })).toBeVisible();
  expect(recorded).toHaveLength(1);
  expect(new URL(recorded[0]!.url()).pathname).toBe(`/api/v3/tablet-assignments/${second.id}`);
  expect(recorded[0]?.headers()['if-match']).toBe(modelGuard);
  await expect.poll(async () => ConfigSchema.parse(await api.config()).tablet_assignments[DeviceIdSchema.parse(second.id)]?.model_id).toBe('google-pixel-c');

  // The other tablet's draft is untouched by all of it.
  await page.locator(`#tablet-row-${first.id}`).click();
  await expect(name).toHaveValue('A draft');
  await expect(model).toHaveValue('manual');
});
