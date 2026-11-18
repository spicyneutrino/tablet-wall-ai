import { fileURLToPath } from 'node:url';
import type { ElementHandle, Page } from '@playwright/test';
import { test, expect } from '../fixtures';

const image = fileURLToPath(new URL('../fixtures/images/EXLENT_Cohort_3_Flyer_Temp.png', import.meta.url));
const viewports = [[390, 844], [820, 1180]] as const;

const selectControls = () => {
  const selector = 'button, a[href], select, textarea, summary, [role="tab"], [role="switch"], [role="button"], .check-label, .check,'
    + ' input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"])';
  const modal = document.querySelector('dialog[open]');
  return [...document.querySelectorAll(selector)].filter((element) => {
    if (element.matches(':disabled') || element.getAttribute('aria-disabled') === 'true') return false;
    if (element.closest('[inert], [aria-hidden="true"], .sr-only, svg, details:not([open]) > :not(summary)')) return false;
    if (modal && !modal.contains(element)) return false;
    return element.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
  });
};

const heights = (controls: Element[]) => ({
  coarse: matchMedia('(pointer: coarse)').matches,
  count: controls.length,
  // A switch is operated through its label, so the label is the target a finger lands on.
  short: controls.map((element) => ({
    tag: element.tagName.toLowerCase(),
    cls: String(element.getAttribute('class') ?? '').slice(0, 50),
    label: (element.getAttribute('aria-label') ?? element.textContent ?? '').trim().slice(0, 40),
    height: Math.round((element.matches('.switch') ? element.closest('label') ?? element : element).getBoundingClientRect().height * 100) / 100,
  })).filter(control => control.height < 44),
});

// Every control is measured, then a trial tap proves a finger can land on it: Playwright scrolls
// it into view and fails if another element would receive the touch.
async function sweep(page: Page, where: string) {
  const list = await page.evaluateHandle(selectControls);
  const measured = await list.evaluate(heights);
  expect(measured.coarse, `${where}: pointer must be coarse`).toBe(true);
  expect(measured.count, `${where}: visible enabled controls exist`).toBeGreaterThan(0);
  expect(measured.short, `${where}: every visible enabled control is at least 44px tall`).toEqual([]);
  const properties = await list.getProperties();
  const unreachable: string[] = [];
  for (const property of properties.values()) {
    const control = property.asElement() as ElementHandle<HTMLElement> | null;
    if (!control) continue;
    // The skip link waits above the viewport until a keyboard focuses it; it is measured, not tapped.
    if (await control.evaluate(element => element.matches('.skip'))) continue;
    try {
      await control.tap({ trial: true, timeout: 4_000 });
    } catch (error) {
      const name = await control.evaluate(element => `${element.tagName.toLowerCase()} "${(element.getAttribute('aria-label') ?? element.textContent ?? '').trim().slice(0, 30)}"`);
      unreachable.push(`${name}: ${String(error).split('\n').find(line => /intercepts|not visible|outside|not stable/.test(line))?.trim() ?? 'cannot be tapped'}`);
    }
  }
  await list.dispose();
  expect(unreachable, `${where}: a touch reaches every control`).toEqual([]);
  console.log(`X12 ${where}: ${measured.count} controls, all at least 44px tall and tappable`);
}

test.use({ serverScope: 'parity-X12' });
test('X12 Under `pointer: coarse`, every control is at least 44 px tall, and a touch sweep reaches every required control', async ({ browser, server, api, tablets, guard }) => {
  test.setTimeout(240_000);
  const fleet = await tablets(4);
  await expect.poll(async () => Object.values((await api.config()).runtime.devices).filter(device => device.online).length).toBe(4);
  const asset = await api.upload(image);
  await api.placeLogical({ columns: 2, rows: 2, deviceIds: fleet.map(tablet => tablet.id) });
  await api.scene({ type: 'image', asset: asset.id, fit: 'cover' });

  for (const [width, height] of viewports) {
    const context = await browser.newContext({ viewport: { width, height }, hasTouch: true, isMobile: true });
    context.setDefaultTimeout(10_000);
    const page = await context.newPage();
    const at = (state: string) => `${width}x${height} ${state}`;
    try {
      await guard(page);
      await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
      await expect(page.locator('#tablet-health .state-ok')).toHaveCount(4, { timeout: 20_000 });
      await sweep(page, at('wall'));

      await page.getByRole('button', { name: 'Edit layout', exact: true }).tap();
      await expect(page.getByRole('button', { name: 'Edit layout', exact: true })).toHaveAttribute('aria-pressed', 'true');
      await sweep(page, at('edit layout'));
      await page.getByRole('button', { name: 'Edit layout', exact: true }).tap();

      await page.getByRole('button', { name: 'Server', exact: true }).tap();
      const sheet = page.getByRole('dialog', { name: 'Server', exact: true });
      await expect(sheet).toBeVisible();
      for (const tab of await sheet.getByRole('tab').allInnerTexts()) {
        await sheet.getByRole('tab', { name: tab.trim(), exact: true }).tap();
        await sweep(page, at(`Server sheet, ${tab.trim()}`));
      }
      await page.getByRole('button', { name: 'Close Server', exact: true }).tap();
      await expect(sheet).not.toBeVisible();

      await page.getByRole('button', { name: 'All images', exact: true }).tap();
      const library = page.getByRole('dialog', { name: 'Library', exact: true });
      await expect(library).toBeVisible();
      await expect(library.getByRole('button', { name: /Refresh images/ })).toBeVisible();
      await sweep(page, at('Library'));
      await page.getByRole('button', { name: 'Close Library', exact: true }).tap();
      await expect(library).not.toBeVisible();

      await page.locator(`#tablet-row-${fleet[0]!.id}`).tap();
      await expect(page.locator('#tablet-title')).toHaveText(/\S+/);
      await sweep(page, at('tablet details'));
      await page.getByRole('button', { name: 'Measure…', exact: true }).tap();
      await expect(page.getByLabel('Which model is it?')).toBeVisible();
      await sweep(page, at('measure'));
    } finally {
      await context.close();
    }
  }
});
