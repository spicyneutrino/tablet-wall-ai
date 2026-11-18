import { test, expect } from '../fixtures';
import { DeviceIdSchema } from '../../src/api/devices';
import { ConfigSchema } from '../../src/api/config';

test.use({ serverScope: 'parity-A3' });

test('A3 Drag, nudge, rotate, resize and snap in Edit layout. Each gesture is one undo entry, history holds 80, and Esc cancels', async ({ page, server, api, tablets, writes, guard }) => {
  test.setTimeout(180_000);
  await guard(page);
  const fleet = await tablets(2);
  const ids = fleet.map(tablet => tablet.id);
  const selected = ids[1]!;
  await api.placeLogical({ columns: 3, rows: 2, deviceIds: ids, cellWidth: 200, cellHeight: 150 });
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  const sent = writes(page);
  await page.getByRole('button', { name: 'Edit layout', exact: true }).click();
  const overlay = page.locator('[data-edit-overlay]');
  const body = overlay.locator(`[data-edit-id="${selected}"][role="button"]`).first();
  await body.click();
  const x = page.getByLabel('X', { exact: true });
  const width = page.getByLabel('Width', { exact: true });
  await expect(x).toHaveValue('200');
  const undo = page.getByRole('button', { name: 'Undo layout edit', exact: true });
  const redo = page.getByRole('button', { name: 'Redo layout edit', exact: true });
  await expect(undo).toBeDisabled();
  const scale = await overlay.evaluate(svg => {
    if (!(svg instanceof SVGSVGElement)) throw new Error('Expected layout canvas');
    return svg.getScreenCTM()!.a;
  });
  async function begin() {
    await overlay.scrollIntoViewIfNeeded();
    const box = await body.boundingBox();
    if (!box) throw new Error('Tablet body must be visible');
    const start = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    await page.mouse.move(start.x, start.y); await page.mouse.down();
    return start;
  }
  let start = await begin();
  await page.mouse.move(start.x + 16 * scale, start.y, { steps: 5 });
  await expect(overlay.locator('[data-guide="y"]')).toHaveAttribute('visibility', 'visible');
  await expect(undo).toBeDisabled();
  await page.mouse.up();
  await expect(x).not.toHaveValue('200');
  await undo.click(); await expect(x).toHaveValue('200'); await expect(undo).toBeDisabled();
  await redo.click(); await expect(x).not.toHaveValue('200'); await undo.click();
  start = await begin();
  await page.mouse.move(start.x + 30, start.y + 20, { steps: 5 });
  await page.keyboard.press('Escape'); await page.mouse.up();
  await expect(x).toHaveValue('200'); await expect(undo).toBeDisabled();
  const snap = page.getByRole('button', { name: 'Snap to grid and edges' });
  if (await snap.isVisible()) {
    await snap.click(); await expect(snap).toHaveAttribute('aria-pressed', 'false');
  } else {
    await page.getByRole('button', { name: 'Layout tools', exact: true }).click();
    await page.getByRole('menuitemcheckbox', { name: 'Snap to grid and edges' }).click();
  }
  start = await begin(); await page.mouse.move(start.x + 16 * scale, start.y, { steps: 5 }); await page.mouse.up();
  await expect(x).toHaveValue('216'); await undo.click(); await expect(x).toHaveValue('200');
  const handle = overlay.locator('[data-resize="e"]');
  const box = await handle.boundingBox();
  if (!box) throw new Error('Resize handle must be visible');
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2); await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 - 20 * scale, box.y + box.height / 2, { steps: 5 }); await page.mouse.up();
  await expect(width).toHaveValue('180'); await undo.click(); await expect(width).toHaveValue('200'); await expect(undo).toBeDisabled();
  await body.focus(); await page.keyboard.press('r');
  await expect(width).toHaveValue('150'); await undo.click(); await expect(width).toHaveValue('200');
  await body.focus(); await page.keyboard.press('Shift+ArrowRight'); await expect(x).toHaveValue('210');
  await undo.click(); await expect(x).toHaveValue('200');
  await x.focus(); await page.keyboard.press('ArrowRight'); await expect(x).toHaveValue('200');
  await body.focus();
  for (let index = 0; index < 82; index++) await page.keyboard.press('ArrowRight');
  await expect(x).toHaveValue('282');
  for (let index = 0; index < 80; index++) await undo.click();
  await expect(x).toHaveValue('202'); await expect(undo).toBeDisabled();
  await expect(redo).toBeEnabled();
  expect(sent).toEqual([]);
  const config = ConfigSchema.parse(await api.config());
  expect(config.layout.kind).toBe('logical');
  if (config.layout.kind === 'logical') expect(config.layout.placements[DeviceIdSchema.parse(selected)]?.x).toBe(200);
  await page.getByRole('button', { name: 'Discard', exact: true }).click();
  await expect(overlay).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Edit layout', exact: true })).toBeFocused();
});
