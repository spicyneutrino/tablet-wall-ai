import { fileURLToPath } from 'node:url';
import { test, expect } from '../fixtures';

const image = fileURLToPath(new URL('../fixtures/images/EXLENT_Cohort_3_Flyer_Temp.png', import.meta.url));

// Union of the sizes named in the brief and the canonical (SHORT_)VIEWPORTS in
// simulator/browser/composition_gates.py:26-27, which differ from the brief's list.
const ALL_SIZES: ReadonlyArray<readonly [number, number]> = [
  [390, 844], [320, 740], [844, 390], [667, 375], [1024, 600], [1280, 600], [1440, 900],
  [1920, 1080], [1366, 768], [1280, 800], [1024, 768], [768, 1024],
];
const OVERLAP_SIZES: ReadonlyArray<readonly [number, number]> = [
  [390, 844], [320, 740], [844, 390], [667, 375], [1024, 600], [1280, 600],
];

type Box = { x: number; y: number; width: number; height: number };

function overlap(a: Box | null, b: Box | null) {
  if (!a || !b) return false;
  return Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x) > 0.5
    && Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y) > 0.5;
}

test.use({ serverScope: 'parity-X11' });
test('X11 No horizontal page overflow at the seven viewports. At 390×844, 320×740 and the short sizes 844×390, 667×375, 1024×600 and 1280×600, regions do not overlap and every control can be reached and clicked, at 100% and 200% root text', async ({ server, api, tablets, page, guard }, info) => {
  test.setTimeout(300_000);
  const viewport = info.project.use.viewport;
  if (!viewport) throw new Error('X11 requires an explicit viewport.');
  await guard(page);
  const fleet = await tablets(4, { viewport: { width: 400, height: 300 } });
  await api.placeLogical({ columns: 2, rows: 2, deviceIds: fleet.map(tablet => tablet.id) });
  const asset = await api.upload(image);
  await api.scene({ type: 'image', asset: asset.id, fit: 'cover' });
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  await expect(page.locator('[data-stage="preview"] [data-screen]')).toHaveCount(4);
  await expect(page.getByRole('button', { name: /4 of 4/ })).toBeVisible();

  const overflow: string[] = [];
  for (const [width, height] of ALL_SIZES) {
    await page.setViewportSize({ width, height });
    await page.evaluate(() => document.fonts.ready);
    const measured = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, innerWidth }));
    if (measured.scrollWidth > measured.innerWidth) {
      overflow.push(`${width}x${height}: scrollWidth ${measured.scrollWidth} > innerWidth ${measured.innerWidth}`);
    }
  }
  expect(overflow, `Horizontal page overflow (${viewport.width}px project)`).toEqual([]);

  const problems: string[] = [];
  for (const [width, height] of OVERLAP_SIZES) {
    await page.setViewportSize({ width, height });
    for (const percent of [100, 200]) {
      await page.evaluate(value => { document.documentElement.style.fontSize = value === 100 ? '' : `${value}%`; }, percent);
      await page.evaluate(() => document.fonts.ready);
      await page.evaluate(() => window.scrollTo(0, 0));

      const boxes = await page.evaluate(() => {
        const rect = (element: Element | null): { x: number; y: number; width: number; height: number } | null => {
          if (!element) return null;
          const style = getComputedStyle(element);
          if (style.display === 'none' || style.visibility === 'hidden') return null;
          const box = element.getBoundingClientRect();
          if (box.width <= 0 || box.height <= 0) return null;
          return { x: box.x, y: box.y, width: box.width, height: box.height };
        };
        const union = (a: ReturnType<typeof rect>, b: ReturnType<typeof rect>) => {
          if (!a) return b;
          if (!b) return a;
          const x = Math.min(a.x, b.x);
          const y = Math.min(a.y, b.y);
          return { x, y, width: Math.max(a.x + a.width, b.x + b.width) - x,
            height: Math.max(a.y + a.height, b.y + b.height) - y };
        };
        const sheet = document.querySelector('dialog[open]');
        return {
          header: rect(document.querySelector('header.appbar')),
          preview: rect(document.querySelector('[data-stage="preview"]')),
          source: union(rect(document.querySelector('.source-strip')), rect(document.querySelector('.primary-action'))),
          side: sheet ? rect(sheet) : rect(document.querySelector('.wall-sidebar')),
        };
      });
      const names = Object.keys(boxes) as (keyof typeof boxes)[];
      for (let first = 0; first < names.length; first++) {
        for (let second = first + 1; second < names.length; second++) {
          if (overlap(boxes[names[first]!]!, boxes[names[second]!]!)) {
            problems.push(`${width}x${height}/${percent}%: ${names[first]} overlaps ${names[second]}: `
              + `${JSON.stringify(boxes[names[first]!])} vs ${JSON.stringify(boxes[names[second]!])}`);
          }
        }
      }

      const controls = await page.evaluate(() => {
        for (const tagged of document.querySelectorAll('[data-x11-key]')) tagged.removeAttribute('data-x11-key');
        const closed = (element: Element) => {
          for (let node = element.parentElement; node; node = node.parentElement) {
            if (node.tagName === 'DETAILS' && !node.hasAttribute('open')) return true;
          }
          return false;
        };
        const visible = (element: Element) => {
          const style = getComputedStyle(element);
          const box = element.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden' && box.width > 0 && box.height > 0
            && box.bottom > 0 && box.right > 0
            && element.getClientRects().length > 0 && !closed(element)
            && (!element.checkVisibility || element.checkVisibility({ contentVisibilityAuto: true }));
        };
        const elements = [...new Set([...document.querySelectorAll(
          'button, a[href], input:not([type="hidden"]), select, [role="tab"], summary',
        )].filter(visible))];
        return elements.map((element, index) => {
          const key = `x11-${index}`;
          element.setAttribute('data-x11-key', key);
          return { key, description: `${element.tagName.toLowerCase()}[${element.getAttribute('aria-label')
            || (element.textContent || '').trim().slice(0, 40) || element.getAttribute('type') || ''}]`,
          disabled: element.hasAttribute('disabled') || element.getAttribute('aria-disabled') === 'true' };
        });
      });
      for (const control of controls) {
        if (control.disabled) continue;
        try {
          await page.locator(`[data-x11-key="${control.key}"]`).click({ trial: true, timeout: 2_000 });
        } catch (error) {
          const detail = error instanceof Error ? error.message : String(error);
          const cause = detail.split('\n').filter(line => /intercepts pointer events/.test(line)).at(-1)
            ?? detail.split('\n')[0] ?? detail;
          problems.push(`${width}x${height}/${percent}%: ${control.description} trial click failed: ${cause.trim()}`);
        }
      }
    }
    await page.evaluate(() => { document.documentElement.style.fontSize = ''; });
  }
  expect(problems, `Region overlap / click reachability (${viewport.width}px project)`).toEqual([]);
});
