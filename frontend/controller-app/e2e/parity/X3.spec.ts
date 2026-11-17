import { fileURLToPath } from 'node:url';
import { test, expect } from '../fixtures';

const image = fileURLToPath(new URL('../fixtures/images/EXLENT_Cohort_3_Flyer_Temp.png', import.meta.url));

test.use({ serverScope: 'parity-X3' });
test('X3 Every action is reachable by keyboard. Focus is visible on every control. Dialogs return focus', async ({ server, api, tablets, page, guard }, info) => {
  test.setTimeout(180_000);
  const viewport = info.project.use.viewport;
  if (!viewport) throw new Error('X3 requires an explicit viewport.');
  await guard(page);
  const fleet = await tablets(4, { viewport: { width: 400, height: 300 } });
  await api.placeLogical({ columns: 2, rows: 2, deviceIds: fleet.map(tablet => tablet.id) });
  const asset = await api.upload(image);
  await api.scene({ type: 'image', asset: asset.id, fit: 'cover' });
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  await expect(page.locator('[data-stage="preview"] [data-screen]')).toHaveCount(4);
  await expect(page.getByRole('button', { name: /4 of 4/ })).toBeVisible();

  // A tablist uses WAI-ARIA roving tabindex: Tab reaches the active tab only,
  // and arrow keys move focus between tabs. Inactive tabs are not Tab stops,
  // so they must not be counted as missing from the Tab sweep below.
  const expected = await page.evaluate(() => {
    const closed = (element: Element) => {
      for (let node = element.parentElement; node; node = node.parentElement) {
        if (node.tagName === 'DETAILS' && !node.hasAttribute('open')) return true;
      }
      return false;
    };
    const visible = (element: Element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0
        && element.getClientRects().length > 0 && !closed(element)
        && (!element.checkVisibility || element.checkVisibility({ contentVisibilityAuto: true }));
    };
    const inTabOrder = (element: Element) => element.getAttribute('role') !== 'tab'
      || element.getAttribute('aria-selected') === 'true' || element.getAttribute('tabindex') === '0';
    const controls = [...new Set([...document.querySelectorAll(
      'button, a[href], input:not([type="hidden"]), select, [role="tab"]',
    )].filter(visible).filter(element => !element.hasAttribute('disabled')
      && element.getAttribute('aria-disabled') !== 'true' && inTabOrder(element)))];
    return controls.map((control, index) => {
      const key = `x3-${index}`;
      control.setAttribute('data-x3-key', key);
      return { key, description: `${control.tagName.toLowerCase()}[${control.getAttribute('aria-label')
        || (control.textContent || '').trim().slice(0, 40) || control.getAttribute('type') || ''}]` };
    });
  });

  const reached = new Set<string>();
  const focusProblems: string[] = [];
  await page.evaluate(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); });
  for (let press = 0; press < 200; press++) {
    await page.keyboard.press('Tab');
    const focused = await page.evaluate(() => {
      const element = document.activeElement;
      if (!element || element === document.body) return null;
      const style = getComputedStyle(element);
      return {
        key: element.getAttribute('data-x3-key'),
        description: `${element.tagName.toLowerCase()}[${element.getAttribute('aria-label')
          || (element.textContent || '').trim().slice(0, 40) || element.getAttribute('type') || ''}]`,
        outline: style.outlineStyle,
        boxShadow: style.boxShadow,
      };
    });
    if (!focused) continue;
    if (focused.key) reached.add(focused.key);
    if (focused.outline === 'none' && focused.boxShadow === 'none') {
      focusProblems.push(`${focused.description} at ${viewport.width}px: outline ${focused.outline}, box-shadow ${focused.boxShadow}`);
    }
  }

  const missing = expected.filter(control => !reached.has(control.key)).map(control => control.description);

  // Prove the other tabs in each tablist are reachable with ArrowRight.
  const tablists = await page.evaluate(() => {
    const closed = (element: Element) => {
      for (let node = element.parentElement; node; node = node.parentElement) {
        if (node.tagName === 'DETAILS' && !node.hasAttribute('open')) return true;
      }
      return false;
    };
    return [...document.querySelectorAll('[role="tablist"]')].map(list => {
      const tabs = [...list.querySelectorAll('[role="tab"]')].filter(tab => !closed(tab));
      const names = tabs.map(tab => (tab.textContent || '').trim());
      const active = tabs.findIndex(tab => tab.getAttribute('aria-selected') === 'true'
        || tab.getAttribute('tabindex') === '0');
      return { names, active: Math.max(0, active) };
    }).filter(list => list.names.length > 1);
  });
  const tabProblems: string[] = [];
  const focusedTab = () => page.evaluate(() => {
    const element = document.activeElement;
    return element?.getAttribute('role') === 'tab' ? (element.textContent || '').trim() : '';
  });
  for (const list of tablists) {
    const activeName = list.names[list.active]!;
    await page.getByRole('tab', { name: activeName, exact: true }).first().focus();
    expect(await focusedTab(), `Focus the active tab before the arrow sweep at ${viewport.width}px`).toBe(activeName);
    const visited = new Set<string>([activeName]);
    let previous = activeName;
    for (let press = 0; press < list.names.length; press++) {
      await page.keyboard.press('ArrowRight');
      await expect.poll(focusedTab, { message: `ArrowRight did not move focus from ${previous}` }).not.toBe(previous);
      const focused = await focusedTab();
      if (list.names.includes(focused)) visited.add(focused);
      previous = focused;
    }
    if (visited.size !== list.names.length) {
      tabProblems.push(`tablist [${list.names.join(', ')}]: ArrowRight reached ${[...visited].join(', ')} at ${viewport.width}px`);
    }
  }

  const serverButton = page.getByRole('button', { name: 'Server', exact: true });
  await serverButton.focus();
  await expect(serverButton).toBeFocused();
  await page.keyboard.press('Enter');
  const sheet = page.getByRole('dialog', { name: 'Server', exact: true });
  await expect(sheet).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(sheet).toHaveCount(0);
  await expect(serverButton).toBeFocused();

  expect(missing, `Controls not reached by Tab at ${viewport.width}px`).toEqual([]);
  expect(focusProblems, `Controls without a visible focus style at ${viewport.width}px`).toEqual([]);
  expect(tabProblems, `Tabs not reachable by ArrowRight at ${viewport.width}px`).toEqual([]);
});
