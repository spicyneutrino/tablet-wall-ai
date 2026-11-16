import { test, expect } from '../fixtures';
import { ConfigSchema } from '../../src/api/config';
import { DeviceIdSchema } from '../../src/api/devices';

test.use({ serverScope: 'parity-T1' });
test('T1 Rename (trimmed, at most 80 characters), model assignment, Identify, Retry image and Reconnect each send 1 request, and their results show', async ({ page, server, api, tablets, writes, guard }) => {
  test.setTimeout(120_000);
  await guard(page);
  const [tablet] = await tablets(1);
  if (!tablet) throw new Error('A real tablet is required.');
  await expect.poll(async () => (await api.config()).runtime.devices[tablet.id]?.online).toBe(true);
  await api.placeLogical({ columns: 1, rows: 1, deviceIds: [tablet.id] });
  await expect.poll(async () => (await api.config()).runtime.devices[tablet.id]?.render.state).toBe('displayed');
  const recorded = writes(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  const row = page.locator(`#tablet-row-${tablet.id}`);
  await expect(row).toBeVisible();
  await row.click();
  await expect(page.locator('#tablet-title')).toBeVisible();
  const facts = page.locator('.tablet-facts');
  await expect(facts).toContainText('Showing');
  await expect(facts).toContainText('Now');
  await expect(facts).toContainText('Model not set');
  await expect(facts).toContainText('Not measured');
  await expect(facts).toContainText('Screen awake');

  // The limit blocks the save before any request.
  const name = page.getByLabel('Name', { exact: true });
  const save = page.getByRole('button', { name: 'Save', exact: true });
  const nameField = page.locator('.field').filter({ has: name });
  await name.fill('x'.repeat(81));
  await expect(name).toHaveAttribute('aria-invalid', 'true');
  await expect(nameField.locator('.field-error')).toHaveText('Names are 80 characters at most. This name has 81.');
  await expect(save).toBeDisabled();
  expect(recorded).toEqual([]);

  // A trimmed name saves with one PATCH and the ETag at submit time.
  const guardBefore = (await api.config()).etag;
  await name.fill('  Lab tablet  ');
  await expect(save).toBeEnabled();
  await save.click();
  await expect(page.getByText('Name saved.', { exact: true })).toBeVisible();
  await expect(page.locator('#tablet-title')).toHaveText('Lab tablet');
  expect(recorded).toHaveLength(1);
  expect(recorded[0]?.method()).toBe('PATCH');
  expect(new URL(recorded[0]!.url()).pathname).toBe(`/api/v3/devices/${tablet.id}`);
  expect(recorded[0]?.headers()['if-match']).toBe(guardBefore);
  expect(recorded[0]?.postDataJSON()).toEqual({ label: 'Lab tablet' });

  // A model choice saves with one PUT and shows its result inline.
  const model = page.getByLabel('Model', { exact: true });
  await expect(model.locator('option')).toHaveCount(4);
  await expect(model.locator('option')).toContainText(['Choose a model or manual measurements', 'Manual measurements', 'Google Pixel C']);
  const modelGuard = (await api.config()).etag;
  await model.selectOption('google-pixel-c');
  await page.getByRole('button', { name: 'Save model', exact: true }).click();
  await expect(page.getByText('Model saved. Measured readiness is checked separately.', { exact: true })).toBeVisible();
  expect(recorded).toHaveLength(2);
  expect(recorded[1]?.method()).toBe('PUT');
  expect(new URL(recorded[1]!.url()).pathname).toBe(`/api/v3/tablet-assignments/${tablet.id}`);
  expect(recorded[1]?.headers()['if-match']).toBe(modelGuard);
  expect(recorded[1]?.postDataJSON()).toEqual({ mode: 'explicit', model_id: 'google-pixel-c' });
  await expect.poll(async () => ConfigSchema.parse(await api.config()).tablet_assignments[DeviceIdSchema.parse(tablet.id)]?.model_id).toBe('google-pixel-c');
  await expect(facts).toContainText('Google Pixel C');

  // Each command sends exactly one POST with the current guard.
  for (const [label, path, result] of [
    ['Identify', `/api/v3/devices/${tablet.id}/identify`, 'Flashing for 5 s'],
    ['Retry image', `/api/v3/devices/${tablet.id}/retry-image`, 'Retry sent'],
    ['Reconnect', `/api/v3/devices/${tablet.id}/reconnect`, 'Reconnect sent'],
  ] as const) {
    const before = recorded.length;
    const etag = (await api.config()).etag;
    await page.getByRole('button', { name: label, exact: true }).click();
    await expect(page.locator('[data-command-result]')).toHaveText(result);
    expect(recorded).toHaveLength(before + 1);
    const request = recorded[before]!;
    expect(request.method()).toBe('POST');
    expect(new URL(request.url()).pathname).toBe(path);
    expect(request.headers()['if-match']).toBe(etag);
    if (label === 'Identify') expect(request.postDataJSON()).toEqual({ duration_ms: 5000 });
    else expect(request.postData()).toBeNull();
  }
  expect(recorded).toHaveLength(5);
});
