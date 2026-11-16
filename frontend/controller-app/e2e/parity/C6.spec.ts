import { test, expect } from '../fixtures';
import { fileURLToPath } from 'node:url';
import { crc32, deflateSync } from 'node:zlib';

const twoColour = fileURLToPath(new URL('../fixtures/images/two-colour.png', import.meta.url));
const flyer = fileURLToPath(new URL('../fixtures/images/EXLENT_Cohort_3_Flyer_Temp.png', import.meta.url));

function pngChunk(type: string, data: Buffer) {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(body));
  return Buffer.concat([length, body, checksum]);
}

function solidPng(red: number, green: number, blue: number) {
  const width = 8, height = 8;
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header[8] = 8;
  header[9] = 2;
  const row = Buffer.alloc(1 + width * 3);
  for (let pixel = 0; pixel < width; pixel += 1) row.set([red, green, blue], 1 + pixel * 3);
  const pixels = Buffer.concat(Array.from({ length: height }, () => row));
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    pngChunk('IHDR', header), pngChunk('IDAT', deflateSync(pixels)), pngChunk('IEND', Buffer.alloc(0))]);
}

function imageFile(name: string, colour: [number, number, number]) {
  return { name, mimeType: 'image/png', buffer: solidPng(...colour) };
}

test.use({ serverScope: 'parity-C6' });
test('C6 Upload: progress, a refusal message, and an uncertain state on timeout, 500 or malformed JSON. Inventory order is kept. Upload is never shown automatically. Disabled when uploads are off', async ({ server, api, tablets, page, writes }) => {
  const [tablet] = await tablets(1);
  if (!tablet) throw new Error('Expected tablet');
  await api.placeLogical({ columns: 1, rows: 1, deviceIds: [tablet.id] });
  const recorded = writes(page);
  const sceneWrites = () => recorded.filter(request => new URL(request.url()).pathname === '/api/v3/scene');
  const before = await api.config() as Record<string, unknown>;
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  const preview = page.getByRole('region', { name: 'Preview', exact: true });
  const sheet = page.getByRole('dialog', { name: 'Library', exact: true });
  const queue = sheet.getByRole('list');
  const input = sheet.locator('input[type="file"]');
  await page.getByRole('button', { name: 'All images' }).click();
  await expect(sheet).toBeVisible();

  // An empty library with an empty queue says what to add.
  const emptyLibrary = 'Add a JPEG or PNG image to this server, then refresh images.';
  await expect(sheet.getByText(emptyLibrary)).toBeVisible();

  // One real upload: the library refreshes, the single file is selected as a preview, nothing reaches the wall.
  // While the transfer is held, the queue counts it and the empty-library sentence goes away.
  let releaseInitial = () => {};
  const initialHeld = new Promise<void>(resolve => { releaseInitial = resolve; });
  await page.route('**/uploads?*', async route => { await initialHeld; await route.continue(); }, { times: 1 });
  await input.setInputFiles(imageFile('single-upload.png', [200, 60, 40]));
  await expect(queue.getByRole('listitem')).toHaveCount(1);
  await expect(sheet.getByRole('heading', { name: 'Uploading 1 of 1', exact: true })).toBeVisible();
  await expect(sheet.getByText(emptyLibrary)).toHaveCount(0);
  releaseInitial();
  await expect(sheet.getByRole('button', { name: 'single-upload.png', exact: true })).toBeVisible();
  await expect(sheet.getByText(emptyLibrary)).toHaveCount(0);
  await expect(preview).toContainText('single-upload.png, Fill');
  expect(sceneWrites()).toEqual([]);

  // Several files: one request at a time, and a queue of more than one never selects anything.
  let releaseFirst = () => {};
  const firstHeld = new Promise<void>(resolve => { releaseFirst = resolve; });
  let uploads = 0;
  await page.route('**/uploads?*', async route => {
    uploads += 1;
    if (uploads === 1) await firstHeld;
    await route.continue();
  }, { times: 2 });
  await input.setInputFiles([twoColour, flyer]);
  await expect.poll(() => uploads).toBe(1);
  await expect(queue.getByText('EXLENT_Cohort_3_Flyer_Temp.png')).toBeVisible();
  await expect(queue.getByText('Waiting')).toBeVisible();
  await page.waitForTimeout(300);
  expect(uploads).toBe(1);
  releaseFirst();
  await expect.poll(() => uploads, { timeout: 30_000 }).toBe(2);
  await expect(sheet.getByRole('button', { name: 'two-colour.png', exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(sheet.getByRole('button', { name: 'EXLENT_Cohort_3_Flyer_Temp.png', exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(preview).toContainText('single-upload.png, Fill');
  expect(sceneWrites()).toEqual([]);

  // The server decides the type: a real 415 becomes a refusal on its row.
  await input.setInputFiles({ name: 'banner.heic', mimeType: 'image/heic', buffer: Buffer.from('not an image') });
  const refused = queue.getByRole('listitem').filter({ hasText: 'banner.heic' });
  await expect(refused.getByText('This file type is not accepted')).toBeVisible();
  // The refused row shows its size once, under the name, and nothing is left to upload.
  await expect(refused.getByText('12 B', { exact: true })).toHaveCount(1);
  await expect(refused.getByRole('button', { name: 'Cancel upload of banner.heic' })).toHaveCount(0);
  await expect(sheet.getByRole('heading', { name: 'Uploads finished', exact: true })).toBeVisible();
  expect(sceneWrites()).toEqual([]);

  // Cancel is offered while the transfer is held; aborting marks the row and adds nothing.
  let releaseCancel = () => {};
  const cancelGate = new Promise<void>(resolve => { releaseCancel = resolve; });
  let cancelSettled = () => {};
  const cancelRouteDone = new Promise<void>(resolve => { cancelSettled = resolve; });
  await page.route('**/uploads?*', async route => {
    await cancelGate;
    try { await route.abort(); } catch { /* the page aborted the request first */ }
    cancelSettled();
  }, { times: 1 });
  await input.setInputFiles(imageFile('cancelled.png', [40, 120, 200]));
  const cancelledRow = queue.getByRole('listitem').filter({ hasText: 'cancelled.png' });
  await expect(cancelledRow.getByRole('progressbar', { name: 'cancelled.png' })).toHaveAttribute('aria-valuemax', '100');
  await expect(cancelledRow.getByRole('button', { name: 'Cancel upload of cancelled.png' })).toBeVisible();
  // Only the held transfer counts now; the refused row is left out of the total.
  await expect(sheet.getByRole('heading', { name: 'Uploading 1 of 1', exact: true })).toBeVisible();
  // A refused row's X is Remove, and it removes the row.
  await refused.getByRole('button', { name: 'Remove banner.heic', exact: true }).click();
  await expect(refused).toHaveCount(0);
  await cancelledRow.getByRole('button', { name: 'Cancel upload of cancelled.png' }).click();
  await expect(cancelledRow.getByText('Cancelled', { exact: true })).toBeVisible();
  await expect(cancelledRow.getByRole('button', { name: 'Cancel upload of cancelled.png' })).toHaveCount(0);
  await expect(cancelledRow.getByRole('button', { name: 'Remove cancelled.png', exact: true })).toBeVisible();
  await expect(sheet.getByRole('heading', { name: 'Uploads finished', exact: true })).toBeVisible();
  releaseCancel();
  await cancelRouteDone;
  await expect(sheet.getByRole('button', { name: 'cancelled.png', exact: true })).toHaveCount(0);
  expect(sceneWrites()).toEqual([]);

  // A delayed response is held, then aborted: the row becomes a retryable failure.
  let releaseStall = () => {};
  const stalled = new Promise<void>(resolve => { releaseStall = resolve; });
  await page.route('**/uploads?*', async route => { await stalled; await route.abort(); }, { times: 1 });
  await input.setInputFiles(imageFile('stalled.png', [40, 120, 200]));
  const stalledRow = queue.getByRole('listitem').filter({ hasText: 'stalled.png' });
  await expect(stalledRow.getByRole('progressbar', { name: 'stalled.png' })).toBeVisible();
  await expect(stalledRow.getByRole('button', { name: 'Cancel upload of stalled.png' })).toBeVisible();
  releaseStall();
  await expect(stalledRow.getByText('Upload failed. Try again.')).toBeVisible();
  await expect(stalledRow.getByRole('button', { name: 'Retry', exact: true })).toBeVisible();
  await expect(stalledRow.getByRole('button', { name: 'Remove stalled.png', exact: true })).toBeVisible();
  await expect(stalledRow.getByRole('button', { name: 'Cancel upload of stalled.png' })).toHaveCount(0);
  expect(sceneWrites()).toEqual([]);

  // A 500 is retryable, and Retry uploads the same file again.
  await page.route('**/uploads?*', route => route.fulfill({ status: 500, contentType: 'application/json',
    body: JSON.stringify({ detail: 'upload failed (OSError)' }) }), { times: 1 });
  await input.setInputFiles(imageFile('retry-me.png', [200, 180, 40]));
  const retryRow = queue.getByRole('listitem').filter({ hasText: 'retry-me.png' });
  await expect(retryRow.getByText('Upload failed. Try again.')).toBeVisible();
  await retryRow.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(sheet.getByRole('button', { name: 'retry-me.png', exact: true })).toBeVisible({ timeout: 30_000 });
  expect(sceneWrites()).toEqual([]);

  // A 201 with unreadable JSON is a retryable failure, not a success.
  await page.route('**/uploads?*', route => route.fulfill({ status: 201, contentType: 'application/json',
    body: '{unreadable successful upload' }), { times: 1 });
  await input.setInputFiles(imageFile('malformed.png', [90, 40, 160]));
  const malformedRow = queue.getByRole('listitem').filter({ hasText: 'malformed.png' });
  await expect(malformedRow.getByText('Upload failed. Try again.')).toBeVisible();
  await expect(malformedRow.getByRole('button', { name: 'Retry', exact: true })).toBeVisible();
  expect(sceneWrites()).toEqual([]);

  // The library keeps the server's inventory order across refreshes.
  const inventory = await api.request.get('/api/v3/images');
  expect(inventory.ok(), await inventory.text()).toBe(true);
  const names = ((await inventory.json()) as { images: { name: string }[] }).images.map(image => image.name);
  const tiles = (await sheet.locator('.image-library-grid').getByRole('button').allTextContents()).map(text => text.trim());
  expect(tiles).toEqual(names);
  expect(names).toEqual(expect.arrayContaining(['single-upload.png', 'two-colour.png', 'EXLENT_Cohort_3_Flyer_Temp.png', 'retry-me.png']));

  // Uploads off: the control is disabled with the reason the server reports.
  await page.route('**/api/v3/config', async route => {
    const response = await route.fetch();
    const config = await response.json() as { capabilities: { uploads: boolean } };
    config.capabilities.uploads = false;
    await route.fulfill({ status: response.status(), headers: { ...response.headers(), 'content-type': 'application/json' },
      body: JSON.stringify(config) });
  });
  await page.routeWebSocket('**/ws/controller?protocol=3', () => {});
  await page.reload({ waitUntil: 'networkidle' });
  await page.getByRole('button', { name: 'All images' }).click();
  await expect(sheet).toBeVisible();
  await expect(sheet.getByRole('button', { name: 'Choose files…', exact: true })).toBeDisabled();
  await expect(sheet.getByRole('group', { name: 'Upload images' })).toContainText('Uploads are off on this server');
  await expect(sheet.locator('.btn-reason').getByText('Uploads are off on this server', { exact: true })).toBeVisible();

  expect(sceneWrites()).toEqual([]);
  expect((await api.config() as Record<string, unknown>).scene).toEqual(before.scene);
});
