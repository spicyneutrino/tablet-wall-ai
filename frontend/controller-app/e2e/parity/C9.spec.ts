import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';
import { test, expect } from '../fixtures';

test.use({ serverScope: 'parity-C9' });

const image = fileURLToPath(new URL('../fixtures/images/two-colour.png', import.meta.url));

test('C9 A timeout, 5xx or unreadable response on Show gives "Not confirmed". Further writes are refused until Refresh status', async ({ page, server, api, tablets, guard, writes, axe }) => {
  test.setTimeout(120_000);
  await guard(page, { allow: [/\/api\/v3\/scene/] });
  const [tablet] = await tablets(1);
  if (!tablet) throw new Error('Expected one joined tablet.');
  await api.placeLogical({ columns: 1, rows: 1, deviceIds: [tablet.id] });
  await api.upload(image);
  await expect.poll(async () => Object.keys((await api.config()).runtime.devices).length).toBe(1);
  const sent = writes(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });

  const show = page.getByRole('button', { name: 'Show on wall', exact: true });
  const onWall = page.locator('.desktop-onwall, .mobile-onwall');
  const refresh = page.getByRole('button', { name: 'Refresh', exact: true });
  async function pick() {
    await page.getByRole('button', { name: 'two-colour.png', exact: true }).click();
    await expect(show).toBeEnabled();
  }
  async function notConfirmed(mode: string) {
    await show.click();
    await expect(page.getByRole('heading', { name: 'Next step: refresh' }), mode).toBeVisible({ timeout: 20_000 });
    await expect(onWall.filter({ visible: true }).getByText('Not confirmed')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Show on wall', exact: true })).toBeDisabled();
    await expect(page.getByText('Refresh first.')).toBeVisible();
  }
  async function recover() {
    const before = sent.length;
    await refresh.click();
    await expect(page.getByRole('heading', { name: 'Next step: refresh' })).toHaveCount(0);
    await expect(page.getByText('Not confirmed', { exact: true })).toHaveCount(0);
    expect(sent.length).toBe(before);
  }

  await pick();
  await page.route('**/api/v3/scene', route => route.fulfill({ status: 503, json: { detail: 'upstream busy' } }));
  await notConfirmed('503');
  expect(sent.length).toBe(1);
  expect((await axe(page)).violations).toEqual([]);
  await page.unroute('**/api/v3/scene');
  await recover();
  await expect(show).toBeEnabled();
  await expect(page.locator('[data-stage="preview"]')).toHaveClass(/is-draft/);

  await page.route('**/api/v3/scene', route => route.fulfill({ status: 200, contentType: 'text/plain', body: 'not json' }));
  await notConfirmed('unreadable 2xx');
  expect(sent.length).toBe(2);
  await page.unroute('**/api/v3/scene');
  await recover();

  await page.route('**/api/v3/scene', async route => {
    const response = await route.fetch();
    await delay(11_500);
    await route.fulfill({ response }).catch(() => undefined);
  });
  await notConfirmed('timeout');
  expect(sent.length).toBe(3);
  await page.unroute('**/api/v3/scene');
  await recover();
  await expect.poll(async () => ((await api.config()).scene as { content: unknown }).content).toMatchObject({ type: 'image' });
  await expect(onWall.filter({ visible: true })).toContainText('two-colour.png');
});
