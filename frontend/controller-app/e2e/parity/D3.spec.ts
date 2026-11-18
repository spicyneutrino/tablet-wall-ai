import type { Page } from '@playwright/test';
import { test, expect } from '../fixtures';

test.use({ serverScope: 'parity-D3' });

const stageWidth = (page: Page, stage: 'preview' | 'onwall') =>
  page.locator(`[data-stage="${stage}"] svg`).first().evaluate(svg => svg instanceof SVGSVGElement ? svg.viewBox.baseVal.width : 0);

test('D3 A second controller\'s write marks the ETag stale. With a dirty draft, the conflict banner appears. Use theirs discards. Keep mine re-guards, and the next Apply succeeds', async ({ browser, server, api, tablets, guard, writes, axe }, info) => {
  test.setTimeout(120_000);
  const [first, second] = await tablets(2);
  if (!first || !second) throw new Error('Expected two joined tablets.');
  const ids = [first.id, second.id];
  await expect.poll(async () => Object.keys((await api.config()).runtime.devices).length).toBe(2);
  const saveAs = async (name: string, grid: Parameters<typeof api.placeLogical>[0]) => {
    const placed = await api.placeLogical(grid);
    const saved = await api.request.put(`/api/v3/logical-layouts/${name}`, { headers: { 'If-Match': placed.etag } });
    expect(saved.ok(), await saved.text()).toBe(true);
  };
  await saveAs('Wide', { columns: 2, rows: 1, deviceIds: ids });
  await saveAs('Offset', { columns: 2, rows: 1, deviceIds: ids, cellWidth: 900 });
  await saveAs('Tall', { columns: 1, rows: 2, deviceIds: ids });

  const viewport = info.project.use.viewport ?? { width: 1440, height: 900 };
  const open = async () => (await browser.newContext({ viewport, hasTouch: viewport.width < 1024 })).newPage();
  const mine = await open();
  const other = await open();
  await guard(mine);
  await guard(other);
  const sent = writes(mine);
  const banner = mine.locator('#conflict');
  const apply = mine.getByRole('button', { name: 'Apply layout', exact: true });
  const draft = async (page: Page, name: string) => {
    await page.getByRole('tab', { name: 'Layouts', exact: true }).click();
    await page.getByRole('button', { name: name, exact: true }).click();
  };
  try {
    await mine.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
    await other.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });

    await draft(mine, 'Wide');
    await expect(apply).toBeEnabled();
    expect(await stageWidth(mine, 'preview')).toBeGreaterThan(await stageWidth(mine, 'onwall'));

    await draft(other, 'Offset');
    await other.getByRole('button', { name: 'Apply layout', exact: true }).click();
    await expect.poll(async () => (await api.config()).layout).toMatchObject({ width: 1800 });

    await expect(banner).toBeVisible();
    await expect(banner).toContainText('Review the change');
    await expect(banner.getByText('Your edit', { exact: true })).toBeVisible();
    await expect(banner.getByText('Layout on wall now', { exact: true })).toBeVisible();
    expect(await stageWidth(mine, 'onwall')).toBeGreaterThan(await stageWidth(mine, 'preview'));
    expect((await axe(mine)).violations).toEqual([]);
    await expect(apply).toBeDisabled();
    await expect(mine.getByText('Review the change first.')).toBeVisible();
    expect(sent).toEqual([]);

    await banner.getByRole('button', { name: 'Use theirs', exact: true }).click();
    await expect(banner).toHaveCount(0);
    expect(await stageWidth(mine, 'preview')).toBe(await stageWidth(mine, 'onwall'));
    await expect(mine.locator('.preview-pinned > .monitor-label > .monitor-description')).toHaveText('Same as the wall');
    expect(sent).toEqual([]);

    await draft(mine, 'Wide');
    await draft(other, 'Tall');
    await other.getByRole('button', { name: 'Apply layout', exact: true }).click();
    await expect.poll(async () => (await api.config()).layout).toMatchObject({ width: 800 });
    await expect(banner).toBeVisible();
    await expect(apply).toBeDisabled();
    await banner.getByRole('button', { name: 'Keep mine', exact: true }).click();
    await expect(banner).toHaveCount(0);
    expect(await stageWidth(mine, 'preview')).toBeGreaterThan(await stageWidth(mine, 'onwall'));
    await expect(apply).toBeEnabled();
    const etag = (await api.config()).etag;
    await apply.click();
    await expect.poll(() => sent.length).toBe(1);
    expect(sent[0]!.method()).toBe('PUT');
    expect(sent[0]!.url()).toContain('/api/v3/logical-layout');
    expect(sent[0]!.headers()['if-match']).toBe(etag);
    await expect.poll(async () => (await api.config()).layout).toMatchObject({ width: 1600 });
    await expect(banner).toHaveCount(0);
    await expect(mine.locator('.preview-pinned > .monitor-label > .monitor-description')).toHaveText('Same as the wall');
  } finally {
    await mine.context().close();
    await other.context().close();
  }
});
