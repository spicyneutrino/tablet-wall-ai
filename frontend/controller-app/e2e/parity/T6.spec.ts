import { test, expect } from '../fixtures';
import { ConfigSchema } from '../../src/api/config';
import type { DeviceStatus } from '../../src/api/devices';
import { POWER_HELP } from '../../src/domain/stagePanels';

test.use({ serverScope: 'parity-T6' });
test('T6 Wake-lock reports show per tablet (held or denied) and as a fleet power summary, with the help text from `operator-stage.js:46-48`', async ({ page, server, api, tablets, guard }) => {
  test.setTimeout(120_000);
  await guard(page);
  const fleet = await tablets(2);
  const ids = fleet.map(tablet => tablet.id);
  await api.placeLogical({ columns: 2, rows: 1, deviceIds: ids });
  await expect.poll(async () => {
    const config = await api.config();
    return fleet.map(({ id }) => config.runtime.devices[id]?.render.state);
  }).toEqual(['displayed', 'displayed']);
  const base = ConfigSchema.parse(await api.config());
  let current = base;
  await page.routeWebSocket('**/ws/controller?protocol=3', () => {});
  await page.route('**/api/v3/config', route => route.fulfill({ json: current }));
  const open = async () => {
    await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
    await expect(page.locator(`#tablet-row-${ids[0]}`)).toBeVisible();
  };
  const showTablet = async (index: number, expected: string) => {
    await page.locator(`#tablet-row-${ids[index]}`).click();
    await expect(page.locator('#tablet-title')).toBeVisible();
    await expect(page.locator('.tablet-facts')).toContainText(expected);
  };
  const withWake = (value: 'held' | 'denied' | null) => {
    const next = structuredClone(base);
    const devices = next.runtime.devices as unknown as Record<string, DeviceStatus>;
    for (const id of ids) {
      const device = devices[id];
      if (!device) throw new Error('Expected both tablets in the routed config.');
      if (value === null) delete device.wake_lock;
      else device.wake_lock = value;
    }
    return ConfigSchema.parse(next);
  };

  // Both held: each tablet reports Held and the fleet summary stays quiet.
  current = withWake('held');
  await open();
  await showTablet(0, 'Held');
  await expect(page.locator('[data-fleet-power]')).toHaveCount(0);
  await showTablet(1, 'Held');

  // Both denied: the fleet summary and its help text appear, and each tablet names the browser report.
  current = withWake('denied');
  await open();
  await showTablet(0, 'Denied by browser');
  await expect(page.locator('[data-fleet-power]')).toHaveText('All online tablets report wake lock denied.');
  await expect(page.locator('[data-power-help]')).toHaveText(POWER_HELP);
  await expect(page.locator('[data-power-help]')).toContainText('Screen wake locks are browser reports, not proof the operating system will keep the screen on.');
  await expect(page.locator('[data-power-help]')).toContainText('The operator cannot wake a sleeping tablet remotely.');
  await showTablet(1, 'Denied by browser');

  // No report from the browser is Unknown, not a guess.
  current = withWake(null);
  await open();
  await showTablet(0, 'Unknown');
  await expect(page.locator('[data-fleet-power]')).toHaveText('All online tablets report wake lock unknown.');
});
