import { test, expect } from '../fixtures';
import { fileURLToPath } from 'node:url';
import { imageColors } from '../fixtures/fleet';

const image = fileURLToPath(new URL('../fixtures/images/two-colour.png', import.meta.url));

test.use({ serverScope: 'parity-C2' });
test('C2 Show on wall sends exactly 1 PUT `/api/v3/scene` with `If-Match` equal to the ETag at selection, and no layout write. All tablets reach `displayed`, and On wall updates', async ({ server, api, tablets, page, writes, guard, tabletPixel }) => {
  await guard(page);
  const fleet = await tablets(4);
  await api.placeLogical({ columns: 2, rows: 2, deviceIds: fleet.map(tablet => tablet.id) });
  const asset = await api.upload(image);
  const before = await api.config();
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  const recorded = writes(page);
  await page.getByRole('button', { name: 'two-colour.png', exact: true }).click();
  expect(recorded).toEqual([]);
  await page.getByRole('button', { name: 'Show on wall', exact: true }).click();
  await expect.poll(async () => {
    const config = await api.config();
    return fleet.map(({ id }) => config.runtime.devices[id]?.render.state);
  }, { timeout: 10_000 })
    .toEqual(['displayed', 'displayed', 'displayed', 'displayed']);
  expect(recorded.map(request => [request.method(), new URL(request.url()).pathname])).toEqual([['PUT', '/api/v3/scene']]);
  expect(recorded[0]?.headers()['if-match']).toBe(before.etag);
  expect(recorded[0]?.postDataJSON()).toEqual({ content: { type: 'image', asset: asset.id, fit: 'cover', background: '#0b1120' } });
  await expect(page.locator('.desktop-onwall')).toContainText('two-colour.png, Fill');
  for (const [index, tablet] of fleet.entries()) {
    const centre = await tablet.page.locator('#surface').evaluate(canvas => {
      if (!(canvas instanceof HTMLCanvasElement)) throw new Error('Expected tablet canvas');
      return { x: canvas.width / 2, y: canvas.height / 2 };
    });
    const expected = index % 2 ? imageColors.right : imageColors.left;
    await expect.poll(async () => Math.max(...(await tabletPixel(tablet, centre.x, centre.y)).slice(0, 3).map((value, channel) => Math.abs(value - (expected[channel] ?? 0)))), { timeout: 10_000 }).toBeLessThanOrEqual(30);
  }
  expect((await api.config()).layout).toEqual(before.layout);
});
