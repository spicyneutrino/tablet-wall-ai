import { test, expect } from '../fixtures';

test.use({ serverScope: 'parity-S3' });
test('S3 Status re-evaluates on the 1 s tick without any server event', async ({ page, server, api, tablets, guard }, info) => {
  await guard(page);
  const [tablet] = await tablets(1);
  if (!tablet) throw new Error('Expected one joined tablet.');
  await expect.poll(async () => (await api.config()).runtime.devices[tablet.id]?.online).toBe(true);
  await api.placeLogical({ columns: 1, rows: 1, deviceIds: [tablet.id] });
  await expect.poll(async () => (await api.config()).runtime.devices[tablet.id]?.render.state).toBe('displayed');
  const snapshot = await api.config();
  await page.clock.install();
  await page.routeWebSocket('**/ws/controller?protocol=3', () => {});
  let release = () => {};
  const gate = new Promise<void>(resolve => { release = resolve; });
  let reads = 0;
  await page.route('**/api/v3/config', async route => {
    if (reads++ > 0) await gate;
    await route.fulfill({ json: snapshot });
  });
  try {
    await page.goto(`${server.origin}/controller/app/`);
    const summary = page.locator(`header .status-${info.project.name === 'phone' ? 'compact' : 'full'}`);
    const row = page.locator(`#tablet-row-${tablet.id}`);
    await expect(row).toHaveAttribute('data-status', 'displayed');
    await page.clock.runFor(14_000);
    await expect(row).toHaveAttribute('data-status', 'displayed');
    await page.clock.runFor(2000);
    await expect(row).toHaveAttribute('data-status', 'stale');
    await expect(row.locator('.state')).toHaveText('Stale');
    await expect(summary).toHaveText(info.project.name === 'phone' ? '0 of 1' : '0 of 1 showing');
    await expect(summary).toHaveClass(/chip-warn/);
  } finally { release(); await page.unrouteAll({ behavior: 'wait' }); }
});
