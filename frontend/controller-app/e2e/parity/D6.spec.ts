import { fileURLToPath } from 'node:url';
import { test, expect } from '../fixtures';

test.use({ serverScope: 'parity-D6' });

const image = fileURLToPath(new URL('../fixtures/images/two-colour.png', import.meta.url));

test('D6 A late or out-of-order read never overwrites newer state', async ({ page, server, api, tablets, guard }) => {
  await guard(page);
  const [tablet] = await tablets(1);
  if (!tablet) throw new Error('Expected one joined tablet.');
  await expect.poll(async () => Object.keys((await api.config()).runtime.devices).length).toBe(1);
  await api.placeLogical({ columns: 1, rows: 1, deviceIds: [tablet.id] });
  await api.upload(image);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  const onWall = page.locator('.desktop-onwall .monitor-description');
  const before = await onWall.innerText();
  expect(before).not.toContain('two-colour.png');

  let release = () => {};
  const gate = new Promise<void>(resolve => { release = resolve; });
  let held = 0;
  await page.route('**/api/v3/config', async route => {
    if (held++) { await route.continue(); return; }
    const response = await route.fetch();
    await gate;
    await route.fulfill({ response });
  });
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await expect.poll(() => held).toBe(1);

  await page.getByRole('button', { name: 'two-colour.png', exact: true }).click();
  await page.getByRole('button', { name: 'Show on wall', exact: true }).click();
  await expect(onWall).toContainText('two-colour.png');

  release();
  await page.evaluate(() => new Promise(resolve => setTimeout(resolve, 750)));
  await expect(onWall).toContainText('two-colour.png');
  const wall = (await api.config()).scene as { content: { type: string } };
  expect(wall.content.type).toBe('image');
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await page.evaluate(() => new Promise(resolve => setTimeout(resolve, 750)));
  await expect(onWall).toContainText('two-colour.png');
});
