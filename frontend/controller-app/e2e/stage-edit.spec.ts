import { z } from 'zod';
import type { Page } from '@playwright/test';
import { LayoutSchema } from '../src/api/layouts';
import { DeviceIdSchema } from '../src/api/devices';
import { fleet } from './fixtures/fleet';
import { test, expect } from './fixtures';

const first = DeviceIdSchema.parse(fleet[0].id), second = DeviceIdSchema.parse(fleet[1].id);
const draftSchema = z.object({ layout: LayoutSchema, undo: z.number(), redo: z.number(), version: z.number() });
async function draft(page: Page) {
  return draftSchema.parse(JSON.parse(await page.getByLabel('Draft layout').innerText()));
}
const canvas = (page: Page) => page.getByRole('group', { name: 'Layout canvas', exact: true });
const body = (page: Page, id = second) => canvas(page).locator(`rect[data-edit-id="${id}"]`);
async function point(page: Page, id = second) {
  const box = await body(page, id).boundingBox();
  if (!box) throw new Error('Tablet must have visible geometry');
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}
async function begin(page: Page, id = second) {
  const start = await point(page, id);
  await page.mouse.move(start.x, start.y); await page.mouse.down();
  return start;
}
async function open(page: Page, origin: string, wall = 'physical-cardinal') {
  await page.goto(`${origin}/controller/app-e2e/?wall=${wall}&edit=1#stage-fixture`, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  await expect(canvas(page)).toBeVisible();
}
async function rotateTo(page: Page, degrees: number, shift: boolean) {
  const before = await draft(page);
  if (before.layout.kind !== 'physical') throw new Error('Rotation requires a physical fixture');
  const slot = before.layout.slots[first]!;
  const knob = canvas(page).locator('[data-rotate-knob]');
  const box = await knob.boundingBox();
  if (!box) throw new Error('Rotation knob must be visible');
  const center = await canvas(page).evaluate((svg, slot) => {
    if (!(svg instanceof SVGSVGElement)) throw new Error('Expected SVG');
    const matrix = svg.getScreenCTM();
    if (!matrix) throw new Error('Expected screen matrix');
    const p = new DOMPoint(slot.center_x_mm + slot.nudge_x_mm, slot.center_y_mm + slot.nudge_y_mm).matrixTransform(matrix);
    return { x: p.x, y: p.y };
  }, slot);
  const x = box.x + box.width / 2, y = box.y + box.height / 2;
  const angle = Math.atan2(y - center.y, x - center.x) + (degrees - slot.mount_angle) * Math.PI / 180;
  const radius = Math.hypot(x - center.x, y - center.y);
  if (shift) await page.keyboard.down('Shift');
  await page.mouse.move(x, y); await page.mouse.down();
  await page.mouse.move(center.x + Math.cos(angle) * radius, center.y + Math.sin(angle) * radius, { steps: 12 });
  await page.mouse.up();
  if (shift) await page.keyboard.up('Shift');
}

test('physical drag maps screen pixels to mm, commits once, sends no writes and supports undo, redo and Escape', async ({ page, server, guard, writes }) => {
  await guard(page); const requests = writes(page);
  await open(page, server.origin);
  const before = await draft(page);
  if (before.layout.kind !== 'physical') throw new Error('Expected physical fixture');
  const original = before.layout.slots[second]!;
  const mapping = await canvas(page).evaluate(svg => {
    if (!(svg instanceof SVGSVGElement)) throw new Error('Expected SVG');
    const box = svg.getBoundingClientRect(), view = svg.viewBox.baseVal;
    return Math.max(view.width / box.width, view.height / box.height);
  });
  const start = await begin(page);
  await page.mouse.move(start.x + 100, start.y, { steps: 20 });
  expect(await draft(page)).toEqual(before);
  await expect(canvas(page)).toHaveAttribute('data-dragging', 'true');
  const transient = await page.locator(`[data-device-id="${second}"]`).boundingBox();
  expect(transient).not.toBeNull();
  expect(Math.abs((transient!.x + transient!.width / 2) - start.x - 100)).toBeLessThan(0.5);
  await page.mouse.up();
  const moved = await draft(page);
  if (moved.layout.kind !== 'physical') throw new Error('Expected physical fixture');
  expect(Math.abs(moved.layout.slots[second]!.center_x_mm - original.center_x_mm - 100 * mapping)).toBeLessThanOrEqual(0.5);
  expect(moved.layout.slots[second]!.center_y_mm).toBe(original.center_y_mm);
  expect(moved.undo).toBe(1); expect(moved.version).toBe(1);
  await expect(page.getByRole('status', { name: 'Layout updates' })).toContainText('Tablet 2 moved');
  await page.keyboard.press('Control+z');
  expect((await draft(page)).layout).toEqual(before.layout);
  await page.keyboard.press('Control+Shift+z');
  expect((await draft(page)).layout).toEqual(moved.layout);
  await page.keyboard.press('Control+z');
  const restored = await draft(page), again = await begin(page);
  await page.mouse.move(again.x + 40, again.y + 10, { steps: 4 });
  await page.keyboard.press('Escape'); await page.mouse.up();
  expect(await draft(page)).toEqual(restored);
  await expect(canvas(page)).not.toHaveAttribute('data-dragging');
  await expect(page.getByRole('status', { name: 'Layout updates' })).toContainText('cancelled');
  expect(requests).toHaveLength(0);
});

test('three-pixel threshold, primary button, pointer cancellation, lost capture and view changes leave no edit', async ({ page, server, guard }) => {
  await guard(page); await open(page, server.origin);
  const before = await draft(page), start = await point(page);
  await page.mouse.click(start.x, start.y, { button: 'right' });
  expect(await draft(page)).toEqual(before);
  await begin(page); await page.mouse.move(start.x + 2, start.y); await page.mouse.up();
  expect(await draft(page)).toEqual(before);
  for (const reason of ['pointercancel', 'lostpointercapture', 'resize', 'blur']) {
    await begin(page); await page.mouse.move(start.x + 20, start.y + 10);
    await canvas(page).evaluate((svg, reason) => {
      if (reason === 'resize' || reason === 'blur') window.dispatchEvent(new Event(reason));
      else svg.dispatchEvent(new PointerEvent(reason, { bubbles: true, pointerId: 1 }));
    }, reason);
    await page.mouse.up();
    expect(await draft(page), reason).toEqual(before);
    await expect(canvas(page)).not.toHaveAttribute('data-dragging');
  }
  await begin(page); await page.mouse.move(start.x + 20, start.y);
  await page.getByRole('button', { name: 'Edit layout', exact: true }).evaluate(button => { if (button instanceof HTMLButtonElement) button.click(); });
  await page.mouse.up(); expect(await draft(page)).toEqual(before);
});

test('keyboard and button nudges use the snap step, announce every move and leave numeric arrow keys alone', async ({ page, server, guard, writes }) => {
  await guard(page); const requests = writes(page); await open(page, server.origin);
  await body(page).focus();
  const before = await draft(page);
  await page.keyboard.press('ArrowRight');
  let moved = await draft(page);
  expect(moved.layout).toMatchObject({ slots: { [second]: { nudge_x_mm: 1, center_x_mm: 300 } } });
  const announcement = await page.getByRole('status', { name: 'Layout updates' }).innerText();
  await page.keyboard.press('Shift+ArrowRight');
  moved = await draft(page);
  expect(moved.layout).toMatchObject({ slots: { [second]: { nudge_x_mm: 11 } } });
  expect(await page.getByRole('status', { name: 'Layout updates' }).innerText()).not.toBe(announcement);
  await page.getByLabel('Step', { exact: true }).selectOption('10');
  await body(page).focus(); await page.keyboard.press('ArrowDown');
  expect((await draft(page)).layout).toMatchObject({ slots: { [second]: { nudge_y_mm: 10 } } });
  await page.getByRole('button', { name: 'Nudge left' }).click();
  expect((await draft(page)).layout).toMatchObject({ slots: { [second]: { nudge_x_mm: 1 } } });
  const numericBefore = await draft(page);
  await page.getByLabel('X (mm)', { exact: true }).focus(); await page.keyboard.press('ArrowRight');
  expect(await draft(page)).toEqual(numericBefore);
  expect((await draft(page)).undo).toBe(before.undo + 4); expect(requests).toHaveLength(0);
});

test('physical rotation is free with Shift and snaps by 15 degrees otherwise; quarter-turn buttons undo', async ({ page, server, guard }) => {
  await guard(page); await open(page, server.origin, 'physical-37-nudge');
  await body(page, first).click();
  await page.getByLabel('Turn (degrees)').fill('0'); await page.getByLabel('Turn (degrees)').press('Enter');
  await rotateTo(page, 37, true);
  expect((await draft(page)).layout).toMatchObject({ slots: { [first]: { mount_angle: 37 } } });
  await page.getByRole('button', { name: 'Undo layout edit' }).click();
  await rotateTo(page, 37, false);
  const snapped = await draft(page);
  if (snapped.layout.kind !== 'physical') throw new Error('Expected physical fixture');
  expect([30, 45]).toContain(snapped.layout.slots[first]!.mount_angle);
  await page.getByRole('button', { name: 'Rotate selected tablet 90 degrees', exact: true }).click();
  expect((await draft(page)).layout).toMatchObject({ slots: { [first]: { mount_angle: snapped.layout.slots[first]!.mount_angle + 90 } } });
  await page.keyboard.press('Control+z'); expect((await draft(page)).layout).toEqual(snapped.layout);
  await expect(canvas(page).locator('[data-resize]')).toHaveCount(0);
});

test('logical resize refuses invisible screens, supports handles and numeric alternatives, and rotates bezels', async ({ page, server, guard }) => {
  await guard(page); await open(page, server.origin, 'logical-grid-hole');
  await body(page).click();
  const before = await draft(page);
  await expect(canvas(page).locator('[data-resize]')).toHaveCount(8);
  const handle = canvas(page).locator('[data-resize="e"]');
  const box = await handle.boundingBox();
  if (!box) throw new Error('Expected resize handle');
  const density = await canvas(page).evaluate(svg => {
    if (!(svg instanceof SVGSVGElement)) throw new Error('Expected SVG');
    return svg.getScreenCTM()!.a;
  });
  const x = box.x + box.width / 2, y = box.y + box.height / 2;
  await page.mouse.move(x, y); await page.mouse.down(); await page.mouse.move(x - 170 * density, y, { steps: 8 }); await page.mouse.up();
  expect(await draft(page)).toEqual(before);
  await expect(page.getByRole('alert')).toHaveText('Bezels leave no visible width. Reduce the left or right bezel.');
  await page.getByLabel('Width', { exact: true }).fill('30'); await page.getByLabel('Width', { exact: true }).press('Enter');
  expect(await draft(page)).toEqual(before);
  await expect(page.getByRole('alert')).toHaveText('Bezels leave no visible width. Reduce the left or right bezel.');
  await page.getByLabel('Width', { exact: true }).fill('200'); await page.getByLabel('Width', { exact: true }).press('Enter');
  expect(await draft(page)).toEqual(before);
  await expect(page.getByRole('alert')).toHaveCount(0);
  await page.getByLabel('Width', { exact: true }).fill('180'); await page.getByLabel('Width', { exact: true }).press('Enter');
  expect((await draft(page)).layout).toMatchObject({ placements: { [second]: { w: 180 } } });
  await canvas(page).locator('[data-resize="se"]').focus(); await page.keyboard.press('ArrowDown');
  expect((await draft(page)).layout).toMatchObject({ placements: { [second]: { h: 201 } } });
  await page.getByRole('button', { name: 'Rotate selected tablet 90 degrees', exact: true }).click();
  expect((await draft(page)).layout).toMatchObject({ placements: { [second]: { w: 201, h: 180,
    bezel: { top: 10, right: 20, bottom: 30, left: 40 } } } });
});

test('logical snapping shows alignment guides, Alt and the snap toggle pause it, and each drag is one undo', async ({ page, server, guard }) => {
  await guard(page); await open(page, server.origin, 'logical-grid-hole');
  await page.getByLabel('Step', { exact: true }).selectOption('10');
  const start = await begin(page);
  const density = await canvas(page).evaluate(svg => {
    if (!(svg instanceof SVGSVGElement)) throw new Error('Expected SVG');
    return svg.getScreenCTM()!.a;
  });
  await page.mouse.move(start.x + 16 * density, start.y, { steps: 5 });
  await expect(canvas(page).locator('[data-guide="y"]')).toHaveAttribute('visibility', 'visible');
  expect((await draft(page)).undo).toBe(0);
  await page.mouse.up();
  const snappedX = 6 * density <= 8 ? 210 : 220;
  expect((await draft(page)).layout).toMatchObject({ placements: { [second]: { x: snappedX } } });
  expect((await draft(page)).undo).toBe(1);
  await page.keyboard.press('Control+z');
  await page.keyboard.down('Alt');
  await begin(page); await page.mouse.move(start.x + 16 * density, start.y, { steps: 5 }); await page.mouse.up();
  await page.keyboard.up('Alt');
  expect((await draft(page)).layout).toMatchObject({ placements: { [second]: { x: 216 } } });
  await page.keyboard.press('Control+z');
  await page.getByRole('button', { name: 'Snap to grid and edges' }).click();
  await begin(page); await page.mouse.move(start.x + 16 * density, start.y, { steps: 5 }); await page.mouse.up();
  expect((await draft(page)).layout).toMatchObject({ placements: { [second]: { x: 216 } } });
});

test('Alt drag edits physical nudge and live mode blocks all editing while displaying the baseline', async ({ page, server, guard }) => {
  await guard(page); await open(page, server.origin);
  const before = await draft(page);
  await page.keyboard.down('Alt'); const start = await begin(page);
  await page.mouse.move(start.x + 30, start.y, { steps: 5 }); await page.mouse.up(); await page.keyboard.up('Alt');
  const moved = await draft(page);
  expect(moved.layout).toMatchObject({ slots: { [second]: { center_x_mm: 300 } } });
  expect(moved.layout).not.toEqual(before.layout);
  await page.getByRole('button', { name: 'Edit layout', exact: true }).click();
  await body(page).focus(); await page.keyboard.press('ArrowRight'); await page.keyboard.press('r'); await page.keyboard.press('Control+z');
  await begin(page); await page.mouse.move(start.x + 40, start.y); await page.mouse.up();
  expect(await draft(page)).toEqual(moved);
  await expect(page.getByText('On wall. Editing is off.')).toBeVisible();
  await expect(page.getByRole('toolbar', { name: 'Canvas tools' })).toHaveCount(0);
});

test('logical pointer resize and arrow moves commit one history entry each', async ({ page, server, guard }) => {
  await guard(page); await open(page, server.origin, 'logical-grid-hole');
  await body(page).focus();
  const before = await draft(page);
  const handle = canvas(page).locator('[data-resize="se"]');
  const box = await handle.boundingBox();
  if (!box) throw new Error('Expected southeast resize handle');
  const density = await canvas(page).evaluate(svg => {
    if (!(svg instanceof SVGSVGElement)) throw new Error('Expected SVG');
    return svg.getScreenCTM()!.a;
  });
  const x = box.x + box.width / 2, y = box.y + box.height / 2;
  await page.mouse.move(x, y); await page.mouse.down();
  await page.mouse.move(x + 30 * density, y + 20 * density, { steps: 8 });
  expect(await draft(page)).toEqual(before);
  await page.mouse.up();
  expect((await draft(page)).layout).toMatchObject({ placements: { [second]: { w: 230, h: 220 } } });
  expect((await draft(page)).undo).toBe(1);
  await page.keyboard.press('Control+z'); expect((await draft(page)).layout).toEqual(before.layout);
  await body(page).focus(); await page.keyboard.press('ArrowRight'); await page.keyboard.press('Shift+ArrowRight');
  expect((await draft(page)).layout).toMatchObject({ placements: { [second]: { x: 211 } } });
  expect((await draft(page)).undo).toBe(2);
});

test('touch dragging captures the pointer, commits once and leaves the page scroll position unchanged', async ({ page, server, guard, writes }) => {
  await guard(page); const requests = writes(page);
  await open(page, server.origin, 'physical-37-nudge');
  const before = await draft(page), start = await point(page, first);
  const cdp = await page.context().newCDPSession(page);
  try {
    await cdp.send('Emulation.setTouchEmulationEnabled', { enabled: true });
    const scroll = await page.evaluate(() => scrollY);
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: start.x, y: start.y }] });
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: start.x + 30, y: start.y + 10 }] });
    await expect(canvas(page)).toHaveAttribute('data-dragging', 'true');
    expect(await draft(page)).toEqual(before);
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    expect((await draft(page)).undo).toBe(1);
    expect((await draft(page)).layout).not.toEqual(before.layout);
    expect(await page.evaluate(() => scrollY)).toBe(scroll); expect(requests).toHaveLength(0);
  } finally { await cdp.detach(); }
});

test('Delete requires confirmation and undo restores the removed placement', async ({ page, server, guard }) => {
  await guard(page); await open(page, server.origin);
  await body(page).focus(); const before = await draft(page);
  page.once('dialog', dialog => dialog.dismiss()); await page.keyboard.press('Delete');
  expect(await draft(page)).toEqual(before);
  page.once('dialog', dialog => dialog.accept()); await page.keyboard.press('Delete');
  await expect(body(page)).toHaveCount(0); expect((await draft(page)).undo).toBe(1);
  await page.keyboard.press('Control+z'); expect((await draft(page)).layout).toEqual(before.layout);
});

test('drag and rotated selection screenshots, clean network and accessible controls', async ({ page, server, guard, axe }, testInfo) => {
  await guard(page);
  const failed: string[] = [], warnings: string[] = [];
  page.on('requestfailed', request => failed.push(request.url()));
  page.on('response', response => { if (response.status() >= 400) failed.push(`${response.status()} ${response.url()}`); });
  page.on('console', message => { if (message.type() === 'warning') warnings.push(message.text()); });
  await open(page, server.origin, 'physical-37-nudge');
  const size = page.viewportSize()!;
  const start = await begin(page, first);
  await page.mouse.move(start.x + 20, start.y + 10, { steps: 8 });
  await expect(canvas(page)).toHaveAttribute('data-dragging', 'true');
  await page.screenshot({ path: testInfo.outputPath(`drag-${size.width}.png`), animations: 'disabled' });
  await page.mouse.up();
  await rotateTo(page, 37, true);
  await page.screenshot({ path: testInfo.outputPath(`rotated-${size.width}.png`), animations: 'disabled', fullPage: true });
  const bounds = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }));
  expect(bounds.scroll).toBeLessThanOrEqual(bounds.width);
  expect((await axe(page)).violations).toEqual([]);
  expect(failed).toEqual([]); expect(warnings).toEqual([]);
});
