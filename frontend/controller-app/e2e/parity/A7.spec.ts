import { fileURLToPath } from 'node:url';
import { test, expect } from '../fixtures';
import { ConfigSchema } from '../../src/api/config';
import { imageColors } from '../fixtures/fleet';

const image = fileURLToPath(new URL('../fixtures/images/two-colour.png', import.meta.url));
test.use({ serverScope: 'parity-A7' });

test('A7 Apply arrangement sends 1 PUT with the ETag from the first edit, and no scene write. On wall changes only after the response', async ({ page, server, api, tablets, writes, guard, tabletPixel }) => {
  test.setTimeout(120_000);
  await guard(page);
  const fleet = await tablets(2);
  const ids = fleet.map(tablet => tablet.id);
  await api.placeLogical({ columns: 2, rows: 1, deviceIds: ids });
  const asset = await api.upload(image);
  await api.scene({ type: 'image', asset: asset.id, fit: 'cover' });
  async function pixelMatches(index: number, expected: readonly number[]) {
    await expect.poll(async () => {
      const pixel = await tabletPixel(fleet[index]!, 400, 225);
      return Math.max(...expected.map((value, channel) => Math.abs(value - pixel[channel]!)));
    }, { timeout: 10_000 }).toBeLessThanOrEqual(2);
  }
  await pixelMatches(0, imageColors.left);
  await pixelMatches(1, imageColors.right);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  const sent = writes(page);
  await page.getByRole('button', { name: 'Edit layout', exact: true }).click();
  const before = ConfigSchema.parse(await api.config());
  const onwall = () => page.locator('[data-stage="onwall"] [data-screen]').first().getAttribute('x');
  const onwallBefore = await onwall();
  for (const [index, id] of ids.entries()) {
    await page.locator(`[data-edit-overlay] [data-edit-id="${id}"][role="button"]`).first().click();
    const field = page.getByLabel('X', { exact: true });
    await field.fill(index === 0 ? '800' : '0'); await field.press('Enter');
  }
  expect(sent).toEqual([]);
  expect(await onwall()).toBe(onwallBefore);
  await pixelMatches(0, imageColors.left);
  let release = () => {};
  const gate = new Promise<void>(resolve => { release = resolve; });
  let receiptReady = () => {};
  const receipt = new Promise<void>(resolve => { receiptReady = resolve; });
  await page.route('**/api/v3/logical-layout', async route => {
    const response = await route.fetch(); receiptReady(); await gate; await route.fulfill({ response });
  });
  try {
    await page.getByRole('button', { name: 'Apply layout', exact: true }).click();
    await expect.poll(() => sent.length).toBe(1);
    const request = sent[0]!;
    expect(request.method()).toBe('PUT');
    expect(new URL(request.url()).pathname).toBe('/api/v3/logical-layout');
    expect(request.headers()['if-match']).toBe(before.etag);
    expect(request.postDataJSON()).toMatchObject({ placements: { [ids[0]!]: { x: 800 }, [ids[1]!]: { x: 0 } } });
    expect(await onwall()).toBe(onwallBefore);
    await receipt;
    expect(ConfigSchema.parse(await api.config()).etag).not.toBe(before.etag);
    expect(await onwall()).toBe(onwallBefore);
    release();
    await expect(page.getByRole('status').filter({ hasText: 'Layout applied.' })).toBeVisible();
    await pixelMatches(0, imageColors.right);
    await pixelMatches(1, imageColors.left);
    await expect.poll(onwall).not.toBe(onwallBefore);
    const after = ConfigSchema.parse(await api.config());
    expect(after.scene).toEqual(before.scene);
    expect(after.etag).not.toBe(before.etag);
    expect(sent).toHaveLength(1);
    await expect(page.getByRole('button', { name: 'Undo layout edit', exact: true })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Apply layout', exact: true })).toBeDisabled();
  } finally { release(); await page.unrouteAll({ behavior: 'wait' }); }

  await page.locator(`[data-edit-overlay] [data-edit-id="${ids[0]}"][role="button"]`).first().click();
  await page.getByLabel('X', { exact: true }).fill('790'); await page.getByLabel('X', { exact: true }).press('Enter');
  const stale = ConfigSchema.parse(await api.config());
  await api.scene({ type: 'calibration' });
  await expect(page.getByRole('button', { name: 'Apply layout', exact: true })).toBeDisabled();
  await expect(page.getByLabel('X', { exact: true })).toHaveValue('790');
  expect(sent).toHaveLength(1);
  expect(ConfigSchema.parse(await api.config()).etag).not.toBe(stale.etag);
});
