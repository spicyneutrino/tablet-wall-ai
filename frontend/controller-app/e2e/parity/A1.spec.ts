import { mkdir, writeFile } from 'node:fs/promises';
import { ConfigSchema } from '../../src/api/config';
import { GridPreviewSchema } from '../../src/api/grid';
import { test, expect } from '../fixtures';

test.use({ serverScope: 'parity-A1' });
test('A1 Grid preview then apply for 1×3, 2×3, 3×2, 2×2 with a trailing hole, and an explicit order. Preview sends 0 durable writes. Apply sends 1 POST `/api/v3/grid`', async ({ server, api, tablets, page, writes, tabletPixel, guard, axe }, info) => {
  test.setTimeout(180_000);
  const fleet = await tablets(6, { viewport: { width: 400, height: 400 }, deviceScaleFactor: 1 });
  await expect.poll(async () => Object.values((await api.config()).runtime.devices).filter(device => device.online).length).toBe(6);
  await api.placeLogical({ columns: 3, rows: 2, cellWidth: 100, cellHeight: 100, deviceIds: fleet.map(tablet => tablet.id) });
  await guard(page);
  const sent = writes(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  await page.getByRole('tab', { name: 'Layouts', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'Build grid', exact: true });
  const colors = [[224, 48, 64], [32, 160, 224], [40, 190, 90], [220, 170, 20], [180, 60, 200], [20, 180, 180]];
  await mkdir('/tmp/U21-shots', { recursive: true });
  for (const [caseIndex, shape] of [
    { columns: 1, rows: 3, count: 3 }, { columns: 2, rows: 3, count: 6 },
    { columns: 3, rows: 2, count: 6 }, { columns: 2, rows: 2, count: 3 },
    { columns: 3, rows: 2, count: 6 },
  ].entries()) {
    const before = ConfigSchema.parse(await api.config());
    const start = sent.length;
    await page.getByRole('button', { name: 'New grid…', exact: true }).click();
    await sheet.getByLabel('Columns', { exact: true }).fill(String(shape.columns));
    await sheet.getByLabel('Rows', { exact: true }).fill(String(shape.rows));
    await sheet.getByRole('switch', { name: 'Allow empty trailing cells' }).setChecked(shape.count !== shape.rows * shape.columns);
    const chosen = fleet.slice(0, shape.count);
    for (const tablet of fleet) {
      const row = sheet.locator(`[data-grid-device="${tablet.id}"]`);
      if (!chosen.includes(tablet)) {
        await row.getByRole('button', { name: /^Exclude / }).click();
        const release = row.getByRole('switch', { name: /^Release / });
        if (await release.count()) await release.check();
      } else {
        await row.locator('summary').click();
        await row.getByLabel(/^Width for /).fill('100');
        await row.getByLabel(/^Height for /).fill('100');
      }
    }
    if (caseIndex === 4) {
      const last = chosen.at(-1)!;
      const earlier = sheet.locator(`[data-grid-device="${last.id}"]`).getByRole('button', { name: /^Move earlier/ });
      for (let index = 0; index < chosen.length; index++) {
        if (await earlier.getAttribute('aria-disabled') === 'true') break;
        await earlier.click();
      }
    }
    const order = await sheet.locator('[data-grid-device]').evaluateAll(rows => rows
      .filter(row => row.querySelector('button[aria-label^="Exclude "]')).map(row => row.getAttribute('data-grid-device')));
    if (caseIndex === 4) {
      expect(order[0]).toBe(chosen.at(-1)!.id);
      await sheet.locator('.dialog-body').evaluate(node => { node.scrollTop = 0; });
      for (const theme of ['light', 'dark']) {
        await page.evaluate(theme => { document.documentElement.dataset.theme = theme; }, theme);
        expect((await axe(page)).violations).toEqual([]);
        expect(await page.locator('.btn-primary:visible').count()).toBe(1);
        await page.screenshot({ path: `/tmp/U21-shots/builder-${info.project.name}-${theme}.png` });
      }
    }
    const responsePromise = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v3/grid/preview');
    await sheet.getByRole('button', { name: 'Preview grid', exact: true }).click();
    const response = await responsePromise;
    expect(response.ok(), await response.text()).toBe(true);
    const preview = GridPreviewSchema.parse(await response.json());
    await expect(sheet).toBeHidden();
    expect(preview.order).toEqual(order);
    expect(sent.slice(start).map(request => new URL(request.url()).pathname)).toEqual(['/api/v3/grid/preview']);
    expect(ConfigSchema.parse(await api.config()).layout).toEqual(before.layout);
    expect(preview.layout).not.toEqual(before.layout);
    await expect(page.locator('[data-stage="preview"] [data-device-id]')).toHaveCount(shape.count);
    const imagePath = info.outputPath(`parts-${caseIndex}.png`);
    const bytes = await page.evaluate(async ({ columns, rows, colors }) => {
      const canvas = document.createElement('canvas');
      canvas.width = columns * 100; canvas.height = rows * 100;
      const context = canvas.getContext('2d')!;
      for (let index = 0; index < columns * rows; index++) {
        context.fillStyle = `rgb(${colors[index]!.join(',')})`;
        context.fillRect(index % columns * 100, Math.floor(index / columns) * 100, 100, 100);
      }
      const blob = await new Promise<Blob>(resolve => canvas.toBlob(blob => resolve(blob!), 'image/png'));
      return [...new Uint8Array(await blob.arrayBuffer())];
    }, { columns: shape.columns, rows: shape.rows, colors });
    await writeFile(imagePath, new Uint8Array(bytes));
    const asset = await api.upload(imagePath);
    if (caseIndex === 4) {
      for (const theme of ['light', 'dark']) {
        await page.evaluate(theme => { document.documentElement.dataset.theme = theme; }, theme);
        expect((await axe(page)).violations).toEqual([]);
        expect(await page.locator('.btn-primary:visible').count()).toBe(1);
        await page.screenshot({ path: `/tmp/U21-shots/preview-${info.project.name}-${theme}.png` });
      }
    }
    const applyResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v3/grid');
    await page.getByRole('button', { name: 'Apply layout', exact: true }).click();
    expect((await applyResponse).ok()).toBe(true);
    await expect(page.getByRole('button', { name: 'New grid…', exact: true })).toBeVisible();
    const durable = sent.slice(start).filter(request => !new URL(request.url()).pathname.endsWith('/preview'));
    expect(durable.map(request => [request.method(), new URL(request.url()).pathname])).toEqual([['POST', '/api/v3/grid']]);
    expect(durable[0]!.headers()['if-match']).toBe(preview.base_etag);
    expect(durable[0]!.postDataJSON()).toMatchObject({ rows: shape.rows, columns: shape.columns, device_ids: order, guards: preview.guards });
    expect(ConfigSchema.parse(await api.config()).layout).toEqual(preview.layout);
    await api.scene({ type: 'image', asset: asset.id, fit: 'cover' });
    for (const [index, id] of order.entries()) {
      const tablet = fleet.find(tablet => tablet.id === id)!;
      await expect.poll(async () => (await api.config()).runtime.devices[tablet.id]?.render.state).toBe('displayed');
      await expect.poll(async () => Math.max(...(await tabletPixel(tablet, 200, 200)).slice(0, 3)
        .map((channel, colorIndex) => Math.abs(channel - colors[index]![colorIndex]!))), { message: `${id} shows grid cell ${index + 1}` }).toBeLessThanOrEqual(10);
    }
  }
});
