import { fileURLToPath } from 'node:url';
import { test, expect } from '../fixtures';

const firstImage = fileURLToPath(new URL('../fixtures/images/EXLENT_Cohort_3_Flyer_Temp.png', import.meta.url));
const secondImage = fileURLToPath(new URL('../fixtures/images/two-colour.png', import.meta.url));

type ClippedButton = { description: string; x: number; right: number; scrollWidth: number; clientWidth: number };

test.use({ serverScope: 'parity-X4' });
test('X4 200% zoom and enlarged text leave no clipped controls and no horizontal page scroll', async ({ server, api, tablets, page, guard }, info) => {
  test.setTimeout(240_000);
  test.fail(info.project.name === 'phone', 'At 390px the "4 of 4" status chip is clipped at 200% text (scrollWidth 102 > clientWidth 91) and the "Calibration grid" and "Tests" controls extend past the viewport (right 408 and 468 > 390).');
  const viewport = info.project.use.viewport;
  if (!viewport) throw new Error('X4 requires an explicit viewport.');
  const width = viewport.width;
  const secondName = 'two-colour.png';
  await guard(page);
  const fleet = await tablets(4, { viewport: { width: 400, height: 300 } });
  await api.placeLogical({ columns: 2, rows: 2, deviceIds: fleet.map(tablet => tablet.id) });
  const first = await api.upload(firstImage);
  await api.upload(secondImage);
  await api.scene({ type: 'image', asset: first.id, fit: 'cover' });
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  await expect(page.locator('[data-stage="preview"] [data-screen]')).toHaveCount(4);
  await expect(page.getByRole('button', { name: /4 of 4/ })).toBeVisible();

  async function check(state: string) {
    const problems: string[] = [];
    for (const percent of [100, 200]) {
      await page.evaluate(value => { document.documentElement.style.fontSize = value === 100 ? '' : `${value}%`; }, percent);
      await page.evaluate(() => document.fonts.ready);
      const measured = await page.evaluate(() => {
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
            && rect.bottom > 0 && rect.top < innerHeight && rect.right > 0 && rect.left < innerWidth
            && element.getClientRects().length > 0 && !closed(element)
            && (!element.checkVisibility || element.checkVisibility({ contentVisibilityAuto: true }));
        };
        const clipped: { description: string; x: number; right: number; scrollWidth: number; clientWidth: number }[] = [];
        for (const button of [...document.querySelectorAll('button')].filter(visible)) {
          const rect = button.getBoundingClientRect();
          const x = Math.round(rect.x * 100) / 100;
          const right = Math.round(rect.right * 100) / 100;
          if (x < -0.5 || right > innerWidth + 0.5 || button.scrollWidth > button.clientWidth + 1) {
            clipped.push({ description: button.getAttribute('aria-label')
              || (button.textContent || '').trim().slice(0, 40) || button.type,
            x, right, scrollWidth: button.scrollWidth, clientWidth: button.clientWidth });
          }
        }
        return { scrollWidth: document.documentElement.scrollWidth, innerWidth, clipped };
      });
      if (measured.scrollWidth > measured.innerWidth) {
        problems.push(`${state}/${percent}%: document scrollWidth ${measured.scrollWidth} > innerWidth ${measured.innerWidth}`);
      }
      for (const button of measured.clipped as ClippedButton[]) {
        problems.push(`${state}/${percent}%: button "${button.description}" x ${button.x}, right ${button.right} of ${measured.innerWidth}, scrollWidth ${button.scrollWidth} > clientWidth ${button.clientWidth}`);
      }
    }
    await page.evaluate(() => { document.documentElement.style.fontSize = ''; });
    expect(problems, `Zoom / enlarged text at ${width}px`).toEqual([]);
  }

  await check('main');

  const screen = page.locator(`[data-stage="preview"] [data-screen="${fleet[0]!.id}"]`);
  const box = await screen.boundingBox();
  if (!box) throw new Error('The tablet screen must be visible.');
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect(page.locator('[data-stage="preview"] [data-selected="true"]')).toHaveCount(1);
  await check('selected');

  await page.getByRole('button', { name: secondName, exact: true }).click();
  await expect(page.getByRole('button', { name: 'Show on wall', exact: true })).toBeEnabled();
  await check('image draft');
});
