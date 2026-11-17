import { fileURLToPath } from 'node:url';
import { test, expect } from '../fixtures';

const firstImage = fileURLToPath(new URL('../fixtures/images/EXLENT_Cohort_3_Flyer_Temp.png', import.meta.url));
const secondImage = fileURLToPath(new URL('../fixtures/images/two-colour.png', import.meta.url));

// The brief names seven sizes, but composition_gates.py:26-27 defines a different canonical
// set (VIEWPORTS and SHORT_VIEWPORTS), and G2 adds 320x740. Check the union of both lists so
// no size named by the brief or by the gate source is left out.
const VIEWPORTS: ReadonlyArray<readonly [number, number]> = [
  [390, 844], [320, 740], [844, 390], [667, 375], [1024, 600], [1280, 600], [1440, 900],
  [1920, 1080], [1366, 768], [1280, 800], [1024, 768], [768, 1024],
];

type Box = { x: number; y: number; width: number; height: number } | null;

function inside(box: Box, width: number, height: number) {
  return !!box && box.width > 0 && box.height > 0 && box.x >= -0.5 && box.y >= -0.5
    && box.x + box.width <= width + 0.5 && box.y + box.height <= height + 0.5;
}

test.use({ serverScope: 'parity-X8' });
test('X8 With an image or arrangement draft open, the primary action is fully inside the viewport at all seven `composition_gates.py:26` viewports', async ({ server, api, tablets, page, guard }, info) => {
  test.setTimeout(300_000);
  test.fail(true, 'With an image draft open the primary action is below the viewport at 844x390 (y=871.33, height 44) and 667x375 (y=753.33, height 44), so it is not fully inside it.');
  const viewport = info.project.use.viewport;
  if (!viewport) throw new Error('X8 requires an explicit viewport.');
  const projectWidth = viewport.width;
  const secondName = 'two-colour.png';
  await guard(page);
  const fleet = await tablets(4, { viewport: { width: 400, height: 300 } });
  await api.placeLogical({ columns: 2, rows: 2, deviceIds: fleet.map(tablet => tablet.id) });
  const first = await api.upload(firstImage);
  await api.upload(secondImage);
  await api.scene({ type: 'image', asset: first.id, fit: 'cover' });
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  await expect(page.locator('[data-stage="preview"] [data-screen]')).toHaveCount(4);

  const primary = page.locator('.primary-action .btn-primary').first();
  async function measure(draft: 'image' | 'arrangement') {
    const problems: { draft: string; width: number; height: number; box: Box }[] = [];
    for (const [width, height] of VIEWPORTS) {
      await page.setViewportSize({ width, height });
      await page.evaluate(() => document.fonts.ready);
      await page.evaluate(() => window.scrollTo(0, 0));
      const box = await primary.boundingBox() as Box;
      if (!inside(box, width, height)) problems.push({ draft, width, height, box });
    }
    expect(problems, `Primary action outside the viewport (${projectWidth}px project)`).toEqual([]);
  }

  await page.getByRole('button', { name: secondName, exact: true }).click();
  await expect(page.getByRole('button', { name: 'Show on wall', exact: true })).toBeEnabled();
  await measure('image');

  await page.setViewportSize(viewport);
  await page.getByRole('button', { name: 'Discard', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Show on wall', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Edit layout', exact: true }).click();
  const overlay = page.locator('[data-edit-overlay]');
  const body = overlay.locator(`[data-edit-id="${fleet[0]!.id}"][role="button"]`).first();
  await body.focus();
  const before = await page.getByLabel('X', { exact: true }).inputValue();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByLabel('X', { exact: true })).not.toHaveValue(before);
  await expect(primary).toContainText('Apply layout');
  await measure('arrangement');
});
