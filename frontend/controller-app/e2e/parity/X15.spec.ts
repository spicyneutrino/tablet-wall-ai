import { fileURLToPath } from 'node:url';
import type { ElementHandle, Page } from '@playwright/test';
import { test, expect } from '../fixtures';
import { installContrast, textRuns, type Ring, type TextRun } from '../contrast';

const image = fileURLToPath(new URL('../fixtures/images/EXLENT_Cohort_3_Flyer_Temp.png', import.meta.url));
const themes = ['light', 'dark'] as const;
const viewports = [[1440, 900], [390, 844]] as const;

const selectControls = () => {
  const modal = document.querySelector('dialog[open]');
  return [...document.querySelectorAll('button, a[href], [role="tab"], summary')].filter(element => {
    if (element.matches(':disabled') || element.getAttribute('aria-disabled') === 'true') return false;
    if (element.closest('[inert], [aria-hidden="true"], .sr-only, .skip')) return false;
    if (modal && !modal.contains(element)) return false;
    return element.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) && (element.textContent ?? '').trim() !== '';
  });
};

const selectChosen = () => {
  const modal = document.querySelector('dialog[open]');
  return [...document.querySelectorAll(
    '[aria-pressed="true"], [aria-selected="true"], [aria-current="true"], [aria-checked="true"], [data-state="on"]')].filter(element => {
    if (modal && !modal.contains(element)) return false;
    return element.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
  });
};

type Failure = { state: string; kind: string; where: string; detail: string };

function readable(runs: TextRun[], state: string, kind: string, failures: Failure[]) {
  for (const run of runs) {
    if (run.ratio < 4.5) failures.push({ state, kind, where: run.where, detail: `"${run.text}" ${run.foreground} on ${run.background} is ${run.ratio.toFixed(2)}:1` });
  }
  return runs.length;
}

const handlesOf = async (page: Page, select: () => Element[]) => {
  const list = await page.evaluateHandle(select);
  const handles = [...(await list.getProperties()).values()].map(property => property.asElement() as ElementHandle<HTMLElement>).filter(Boolean);
  await list.dispose();
  return handles;
};

// Hover, then press, every visible enabled control that has text; the colours are read from the
// painted element while the pointer is on it, composited through its real ancestors.
async function pointerStates(page: Page, state: string, failures: Failure[], options: { press: boolean }) {
  const viewport = page.viewportSize() ?? { width: 1440, height: 900 };
  let hovered = 0;
  let pressed = 0;
  await page.mouse.move(0, 0);
  for (const control of await handlesOf(page, selectControls)) {
    await control.scrollIntoViewIfNeeded().catch(() => {});
    const box = await control.boundingBox();
    if (!box || box.y < 0 || box.y + box.height > viewport.height || box.x < 0 || box.x + box.width > viewport.width) continue;
    if (!(await control.isEnabled())) continue;
    await control.hover({ timeout: 5_000 });
    hovered += readable(await control.evaluate(textRuns), state, 'hover', failures);
    const plain = await control.evaluate(element => element.matches('button.btn:not([role]):not([aria-haspopup])'));
    if (options.press && plain) {
      // Press, then slide off before release, so the press paints without firing a click.
      await page.mouse.down();
      pressed += readable(await control.evaluate(textRuns), state, 'pressed', failures);
      await page.mouse.move(0, 0);
      await page.mouse.up();
    }
    await page.mouse.move(0, 0);
  }
  return { hovered, pressed };
}

async function chosenStates(page: Page, state: string, failures: Failure[]) {
  let checked = 0;
  for (const element of await handlesOf(page, selectChosen)) checked += readable(await element.evaluate(textRuns), state, 'selected', failures);
  return checked;
}

// A real keyboard walk: Tab through the page and measure the ring the browser paints on each stop.
async function tabRings(page: Page) {
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    Reflect.set(window, '__tabSeen', []);
  });
  const rings: Ring[] = [];
  let repeats = 0;
  for (let step = 0; step < 120; step++) {
    await page.keyboard.press('Tab');
    const stop = await page.evaluate(() => {
      const element = document.activeElement;
      if (!element || element === document.body) return 'end' as const;
      const seen = Reflect.get(window, '__tabSeen') as Element[];
      if (seen.includes(element)) return 'repeat' as const;
      seen.push(element);
      const kit = Reflect.get(window, '__contrast') as { ring: (element: Element) => Ring; settle: () => void };
      kit.settle();
      return kit.ring(element);
    });
    if (stop === 'end') break;
    // Scroll containers join the tab order and a repeat before the cycle closes is normal.
    if (stop === 'repeat') { if (++repeats > 3) break; continue; }
    repeats = 0;
    rings.push(stop);
  }
  return rings;
}

test.use({ serverScope: 'parity-X15' });
test('X15 Hover, selected and pressed text, and the keyboard focus ring, meet contrast on the real elements. axe does not check these states', async ({ page, server, api, tablets, guard, writes }) => {
  test.setTimeout(420_000);
  const fleet = await tablets(4);
  await expect.poll(async () => Object.values((await api.config()).runtime.devices).filter(device => device.online).length).toBe(4);
  const asset = await api.upload(image);
  await api.placeLogical({ columns: 2, rows: 2, deviceIds: fleet.map(tablet => tablet.id) });
  await api.scene({ type: 'image', asset: asset.id, fit: 'cover' });
  await installContrast(page);
  await guard(page);
  const written = writes(page);
  // Colours animate; measure settled states, not frames.
  await page.emulateMedia({ reducedMotion: 'reduce' });

  const failures: Failure[] = [];
  const totals = { hover: 0, pressed: 0, selected: 0, rings: 0 };
  for (const [width, height] of viewports) {
    await page.setViewportSize({ width, height });
    for (const theme of themes) {
      const where = (state: string) => `${width}x${height} ${theme} ${state}`;
      const fresh = async () => {
        await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
        await expect(page.locator('#tablet-health .state-ok')).toHaveCount(4, { timeout: 20_000 });
        await page.evaluate(value => { document.documentElement.dataset.theme = value; }, theme);
        await page.mouse.move(0, 0);
      };

      await fresh();
      const main = await pointerStates(page, where('wall'), failures, { press: true });
      totals.hover += main.hovered;
      totals.pressed += main.pressed;
      totals.selected += await chosenStates(page, where('wall'), failures);

      await page.getByRole('button', { name: 'Edit layout', exact: true }).click();
      await expect(page.getByRole('button', { name: 'Edit layout', exact: true })).toHaveAttribute('aria-pressed', 'true');
      totals.selected += await chosenStates(page, where('edit layout'), failures);
      totals.hover += (await pointerStates(page, where('edit layout'), failures, { press: false })).hovered;
      await page.getByRole('button', { name: 'Edit layout', exact: true }).click();

      await page.getByRole('tab', { name: 'Tests', exact: true }).click();
      totals.selected += await chosenStates(page, where('Tests tab'), failures);
      totals.hover += (await pointerStates(page, where('Tests tab'), failures, { press: false })).hovered;

      await page.locator(`#tablet-row-${fleet[0]!.id}`).click();
      await expect(page.locator('#tablet-title')).toHaveText(/\S+/);
      totals.selected += await chosenStates(page, where('tablet details'), failures);
      totals.hover += (await pointerStates(page, where('tablet details'), failures, { press: false })).hovered;

      await fresh();
      await page.getByRole('button', { name: 'Server', exact: true }).click();
      await expect(page.getByRole('dialog', { name: 'Server', exact: true })).toBeVisible();
      totals.selected += await chosenStates(page, where('Server sheet'), failures);
      totals.hover += (await pointerStates(page, where('Server sheet'), failures, { press: false })).hovered;

      await fresh();
      await page.getByRole('button', { name: 'All images', exact: true }).click();
      await expect(page.getByRole('dialog', { name: 'Library', exact: true })).toBeVisible();
      totals.selected += await chosenStates(page, where('Library'), failures);
      totals.hover += (await pointerStates(page, where('Library'), failures, { press: false })).hovered;
    }
  }
  expect(failures, 'hover, pressed and selected text is at least 4.5:1 on the painted element').toEqual([]);
  expect(written.map(request => `${request.method()} ${request.url()}`), 'hovering and pressing wrote nothing').toEqual([]);
  expect(totals.hover, 'hover text runs were measured').toBeGreaterThan(100);
  expect(totals.pressed, 'pressed text runs were measured').toBeGreaterThan(20);
  expect(totals.selected, 'selected text runs were measured').toBeGreaterThan(30);

  const ringFailures: string[] = [];
  for (const [width, height] of viewports) {
    await page.setViewportSize({ width, height });
    for (const theme of themes) {
      const pages: [string, () => Promise<void>][] = [
        ['wall', async () => {}],
        ['Server sheet', async () => { await page.getByRole('button', { name: 'Server', exact: true }).click(); }],
        ['Library', async () => { await page.getByRole('button', { name: 'All images', exact: true }).click(); }],
      ];
      for (const [state, open] of pages) {
        await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
        await expect(page.locator('#tablet-health .state-ok')).toHaveCount(4, { timeout: 20_000 });
        await page.evaluate(value => { document.documentElement.dataset.theme = value; }, theme);
        await open();
        const rings = await tabRings(page);
        expect(rings.length, `${width}x${height} ${theme} ${state}: Tab reaches controls`).toBeGreaterThan(state === 'wall' ? 10 : 2);
        for (const ring of rings) {
          if (!ring.kind) ringFailures.push(`${width}x${height} ${theme} ${state}: no ring on ${ring.where} "${ring.label}"`);
          else if (ring.ratio < 3) ringFailures.push(`${width}x${height} ${theme} ${state}: ring ${ring.color} on ${ring.surround} is ${ring.ratio.toFixed(2)}:1 on ${ring.where} "${ring.label}"`);
        }
        totals.rings += rings.length;
      }
    }
  }
  expect(ringFailures, 'every keyboard focus ring is at least 3:1 against what is behind it').toEqual([]);
  console.log(`X15: ${totals.hover} hover, ${totals.pressed} pressed and ${totals.selected} selected text runs at or above 4.5:1; ${totals.rings} Tab stops with a focus ring at or above 3:1`);
});
