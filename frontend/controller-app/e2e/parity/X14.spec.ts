import { fileURLToPath } from 'node:url';
import type { Dialog, Page } from '@playwright/test';
import { test, expect } from '../fixtures';

test.use({ serverScope: 'parity-X14' });

const image = fileURLToPath(new URL('../fixtures/images/two-colour.png', import.meta.url));

test('X14 Before the first authoritative config arrives, the page shows a loading state and never an empty wall', async ({ page, server, guard, axe }) => {
  await guard(page);
  let release = () => {};
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/v3/config', async route => { await gate; await route.continue(); });
  await page.routeWebSocket('**/ws/controller?protocol=3', () => {});
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'domcontentloaded' });
  try {
    await expect(page.getByRole('button', { name: /^Connecting/ })).toBeVisible();
    await expect(page.locator('.preview-pinned > .monitor-label > .monitor-description')).toHaveText('Loading the wall…');
    await expect(page.locator('[data-stage="preview"] .skel-pulse').first()).toBeVisible();
    await expect(page.getByText('No tablets on the wall yet')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Next step: add your first tablet' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Show on wall', exact: true })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Show on wall', exact: true })).toHaveAccessibleDescription('Loading…');
    expect((await axe(page)).violations).toEqual([]);
  } finally { release(); }
  await expect(page.getByRole('heading', { name: 'Next step: add your first tablet' })).toBeVisible();
  await expect(page.getByRole('button', { name: /^Connecting/ })).toHaveCount(0);
});

test('X14 An unsaved draft asks before the tab is left, and a clean page leaves without asking', async ({ browser, server, api, tablets, guard }) => {
  const [tablet] = await tablets(1);
  if (!tablet) throw new Error('Expected one joined tablet.');
  await expect.poll(async () => Object.keys((await api.config()).runtime.devices).length).toBe(1);
  await api.placeLogical({ columns: 1, rows: 1, deviceIds: [tablet.id] });
  await api.upload(image);
  const page = await browser.newPage();
  await guard(page);
  const dialogs: Dialog[] = [];
  page.on('dialog', dialog => { dialogs.push(dialog); });
  const app = `${server.origin}/controller/app/`;
  const leave = (target: Page) => target.goto('about:blank').catch(() => undefined);
  await page.goto(app, { waitUntil: 'networkidle' });

  await page.getByRole('button', { name: 'two-colour.png', exact: true }).click();
  await page.getByRole('button', { name: 'Discard', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Discard', exact: true })).toHaveCount(0);
  await leave(page);
  expect(dialogs).toEqual([]);
  expect(page.url()).toBe('about:blank');

  await page.goto(app, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: 'two-colour.png', exact: true }).click();
  const left = leave(page);
  await expect.poll(() => dialogs.length).toBe(1);
  expect(dialogs[0]!.type()).toBe('beforeunload');
  await dialogs[0]!.dismiss();
  void left; // WebKit never settles a goto whose beforeunload dialog was dismissed; Chromium does
  expect(page.url()).toBe(app);
  await expect(page.getByRole('button', { name: 'Discard', exact: true })).toBeVisible();
  await page.close();
});
