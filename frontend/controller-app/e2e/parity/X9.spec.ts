import { fileURLToPath } from 'node:url';
import { test, expect } from '../fixtures';

const firstImage = fileURLToPath(new URL('../fixtures/images/EXLENT_Cohort_3_Flyer_Temp.png', import.meta.url));
const secondImage = fileURLToPath(new URL('../fixtures/images/two-colour.png', import.meta.url));

test.use({ serverScope: 'parity-X9' });
test('X9 At most one primary-styled button is visible per view, with or without a draft', async ({ server, api, tablets, page, guard }, info) => {
  test.setTimeout(240_000);
  const viewport = info.project.use.viewport;
  if (!viewport) throw new Error('X9 requires an explicit viewport.');
  const width = viewport.width;
  const secondName = 'two-colour.png';
  await guard(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });

  async function count(view: string) {
    const primaries = await page.evaluate(() => {
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
      return [...document.querySelectorAll('.btn-primary')].filter(visible)
        .map(element => (element.textContent || '').trim().slice(0, 40) || element.getAttribute('aria-label') || element.id);
    });
    expect(primaries.length, `${view}/${width}px visible .btn-primary buttons: ${JSON.stringify(primaries)}`).toBeLessThanOrEqual(1);
  }

  await expect(page.getByRole('region', { name: 'Next step: add your first tablet' })).toBeVisible();
  await count('firstrun');

  const fleet = await tablets(4, { viewport: { width: 400, height: 300 } });
  await api.placeLogical({ columns: 2, rows: 2, deviceIds: fleet.map(tablet => tablet.id) });
  const first = await api.upload(firstImage);
  await api.upload(secondImage);
  await api.scene({ type: 'image', asset: first.id, fit: 'cover' });
  await expect(page.locator('[data-stage="preview"] [data-screen]')).toHaveCount(4);
  await count('main');

  const screen = page.locator(`[data-stage="preview"] [data-screen="${fleet[0]!.id}"]`);
  const box = await screen.boundingBox();
  if (!box) throw new Error('The tablet screen must be visible.');
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect(page.locator('[data-stage="preview"] [data-selected="true"]')).toHaveCount(1);
  await count('selected');

  await page.getByRole('button', { name: 'Edit layout', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Edit layout', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await count('arrange');
  await page.getByRole('button', { name: 'Edit layout', exact: true }).click();

  await page.getByRole('button', { name: 'Measure…', exact: true }).click();
  await expect(page.getByRole('heading', { name: /^Measure Tablet/ })).toBeVisible();
  await count('measure');
  await page.locator('.measure-back').click();

  await page.getByRole('button', { name: secondName, exact: true }).click();
  await expect(page.getByRole('button', { name: 'Show on wall', exact: true })).toBeEnabled();
  await count('image draft');
  await page.getByRole('button', { name: 'Discard', exact: true }).click();

  await page.getByRole('button', { name: 'Edit layout', exact: true }).click();
  const body = page.locator('[data-edit-overlay]').locator(`[data-edit-id="${fleet[0]!.id}"][role="button"]`).first();
  await body.focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('.primary-action .btn-primary').first()).toContainText('Apply layout');
  await count('arrangement draft');
  await page.getByRole('button', { name: 'Discard', exact: true }).click();

  await page.getByRole('button', { name: 'Server', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Server', exact: true })).toBeVisible();
  await count('server sheet');
  await page.keyboard.press('Escape');

  await page.getByRole('button', { name: 'All images' }).click();
  await expect(page.getByRole('dialog', { name: 'Library', exact: true })).toBeVisible();
  await count('library sheet');
  await page.keyboard.press('Escape');
});
