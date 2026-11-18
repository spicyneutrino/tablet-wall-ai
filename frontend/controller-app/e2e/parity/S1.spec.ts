import { DeviceIdSchema } from '../../src/api/devices';
import { ConfigSchema } from '../../src/api/config';
import { projectRoster } from '../../src/domain/roster';
import { aggregate, observeConfig, tabletState } from '../../src/domain/status';
import { test, expect } from '../fixtures';

test.use({ serverScope: 'parity-S1' });
test('S1 Board status matches `tabletState` for displayed, stale (evidence older than 15 s), offline, excluded, identifying, unplaced, wrong content and missing tablet', async ({ page, server, api, tablets, guard }, info) => {
  await guard(page);
  const [tablet] = await tablets(1);
  if (!tablet) throw new Error('Expected one joined tablet.');
  const id = DeviceIdSchema.parse(tablet.id);
  await expect.poll(async () => (await api.config()).runtime.devices[id]?.online).toBe(true);
  await api.placeLogical({ columns: 1, rows: 1, deviceIds: [id] });
  await expect.poll(async () => (await api.config()).runtime.devices[id]?.render.state).toBe('displayed');
  const base = ConfigSchema.parse(await api.config());
  const scenarios = ['displayed', 'stale', 'offline', 'excluded', 'identifying', 'unplaced', 'failed', 'missing'] as const;
  let current = base;
  await page.routeWebSocket('**/ws/controller?protocol=3', () => {});
  await page.route('**/api/v3/config', route => route.fulfill({ json: current }));
  for (const scenario of scenarios) {
    current = structuredClone(base);
    const device = current.runtime.devices[id];
    if (!device?.render || current.layout.kind !== 'logical') throw new Error('Expected a placed tablet with live paint evidence.');
    if (scenario === 'stale') device.render.age_ms = 16_000;
    if (scenario === 'offline') device.online = false;
    if (scenario === 'excluded') current.layout.placements[id] = {
      ...current.layout.placements[id]!, participating: false,
    };
    if (scenario === 'identifying') device.identify = { command_id: 'parity', state: 'active', duration_ms: 5000, remaining_ms: 5000, active: true };
    if (scenario === 'unplaced') current.layout.placements = {};
    if (scenario === 'failed') device.render.state = 'failed';
    if (scenario === 'missing') { delete current.runtime.devices[id]; delete current.device_labels[id]; }
    current = ConfigSchema.parse(current);
    const projected = observeConfig(projectRoster(current, current.runtime.devices), 0);
    const expected = tabletState(projected, tablet.id, 0), counts = aggregate(projected, 0);
    await page.goto(`${server.origin}/controller/app/`);
    const row = page.locator(`#tablet-row-${tablet.id}`);
    await expect(row).toHaveAttribute('data-status', expected.status);
    await expect(row).toHaveAccessibleDescription(new RegExp(expected.text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
    await expect(row.locator('.state')).toHaveText(scenario === 'displayed' ? 'Showing' : scenario === 'failed' ? 'Wrong content'
      : scenario === 'unplaced' ? 'Not placed' : scenario === 'offline' ? 'Offline' : scenario === 'stale' ? 'Stale' : expected.text.split(' · ')[0]!);
    const summary = page.locator(`header .status-${info.project.name === 'phone' ? 'compact' : 'full'}`);
    await expect(summary).toHaveText(`${counts.showing} of ${counts.total}${info.project.name === 'phone' ? '' : ' showing'}`);
    if (scenario === 'missing') {
      await expect(row.locator('.row-name')).toHaveText(`Tablet ${tablet.id.slice(-6)}`);
      await expect(page.locator(`[data-tablet-label="${tablet.id}"]`).first()).toHaveText(`Tablet ${tablet.id.slice(-6)}`);
    }
  }
});
