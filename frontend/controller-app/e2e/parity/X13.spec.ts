import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { crc32, deflateSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';
import type { Locator } from '@playwright/test';
import { test, expect } from '../fixtures';
import { ImagesSchema } from '../../src/api/images';

const fixture = fileURLToPath(new URL('../fixtures/images/EXLENT_Cohort_3_Flyer_Temp.png', import.meta.url));
const widths = [[390, 844], [820, 1180], [1440, 900]] as const;

// One long name per script: Latin with emoji and accents, Arabic (right to left), and CJK with Hangul.
const names = {
  latin: 'Gallery north wall with a very long descriptive label 🧱🖼️ Ünïcödé façade ñandú',
  arabic: 'جهاز لوحي كبير جدا في الزاوية الشمالية الشرقية من قاعة المعرض الرئيسية الطويلة',
  cjk: '北側の壁に掛けた非常に長い名前の端末 日本語 中文名称 한국어 표시',
};
const imageFiles = Object.fromEntries(Object.entries(names).map(([script, name]) => [script, `${name}.png`]));

// Assets with identical bytes are one asset, so each curated file is a different solid-colour PNG.
const solidPng = (red: number, green: number, blue: number) => {
  const chunk = (type: string, data: Buffer) => {
    const body = Buffer.concat([Buffer.from(type), data]);
    const length = Buffer.alloc(4);
    length.writeUInt32BE(data.length);
    const checksum = Buffer.alloc(4);
    checksum.writeUInt32BE(crc32(body));
    return Buffer.concat([length, body, checksum]);
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(64, 0);
  header.writeUInt32BE(40, 4);
  header.set([8, 2, 0, 0, 0], 8);
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: 64 }, () => [red, green, blue]).flat())]);
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', header), chunk('IDAT', deflateSync(Buffer.concat(Array.from({ length: 40 }, () => row)))), chunk('IEND', Buffer.alloc(0)),
  ]);
};

// What a reader needs: the full name is in the page, nothing escapes its container or the
// viewport, the type stays at caption size or larger, and a clipped name keeps room for a
// recognisable start and an ellipsis.
const measureName = (element: Element, options: { clip: boolean }) => {
  const style = getComputedStyle(element);
  const rect = element.getBoundingClientRect();
  const container = element.parentElement?.getBoundingClientRect();
  return {
    text: (element.textContent ?? '').trim(),
    fontSize: parseFloat(style.fontSize),
    visibleWidth: element.clientWidth,
    clipped: element.scrollWidth > element.clientWidth + 1,
    ellipsis: style.textOverflow === 'ellipsis' && style.overflow !== 'visible',
    insideContainer: !container || (rect.left >= container.left - 0.5 && rect.right <= container.right + 0.5),
    insideViewport: rect.left >= -0.5 && rect.right <= innerWidth + 0.5,
    documentOverflow: document.documentElement.scrollWidth > innerWidth + 1,
    clipAllowed: options.clip,
  };
};

async function expectReadable(locator: Locator, expected: string, label: string, clip: boolean) {
  const result = await locator.evaluate(measureName, { clip });
  expect(result.text, `${label}: the full name is present`).toBe(expected);
  expect(result.fontSize, `${label}: the name is at least caption size`).toBeGreaterThanOrEqual(13);
  expect(result.insideContainer, `${label}: the name stays inside its container`).toBe(true);
  expect(result.insideViewport, `${label}: the name stays inside the viewport`).toBe(true);
  expect(result.documentOverflow, `${label}: no horizontal document overflow`).toBe(false);
  if (result.clipped) {
    expect(result.clipAllowed, `${label}: this name must wrap, not clip`).toBe(true);
    expect(result.ellipsis, `${label}: a clipped name ends in an ellipsis`).toBe(true);
    expect(result.visibleWidth, `${label}: a clipped name still shows a recognisable start`).toBeGreaterThanOrEqual(80);
  }
  return result;
}

test.use({ serverScope: 'parity-X13' });
test('X13 Long Unicode tablet and image names stay readable at every width. A missing thumbnail shows a fallback', async ({ page, server, api, tablets, guard }) => {
  test.setTimeout(300_000);
  const fleet = await tablets(4);
  await expect.poll(async () => Object.values((await api.config()).runtime.devices).filter(device => device.online).length).toBe(4);
  const tabletIds: Record<string, string> = {};
  for (const [index, script] of Object.keys(names).entries()) {
    const tablet = fleet[index]!;
    tabletIds[script] = tablet.id;
    const current = await api.config();
    const response = await api.request.patch(`/api/v3/devices/${tablet.id}`, {
      headers: { 'If-Match': current.etag },
      data: { label: names[script as keyof typeof names] },
    });
    expect(response.ok(), await response.text()).toBe(true);
  }

  // The upload endpoint keeps only printable ASCII in a display name, so curated assets
  // dropped in the supported asset directory are how Unicode names reach the library.
  const curatedDirectory = join(server.directory, 'assets');
  await mkdir(curatedDirectory, { recursive: true });
  for (const [index, file] of Object.values(imageFiles).entries()) await writeFile(join(curatedDirectory, file), solidPng(40 + index * 80, 90, 200 - index * 60));
  await api.request.get('/assets');
  const asset = await api.upload(fixture);
  await api.placeLogical({ columns: 2, rows: 2, deviceIds: fleet.map(tablet => tablet.id) });
  await api.scene({ type: 'image', asset: asset.id, fit: 'cover' });
  const inventory = ImagesSchema.parse(await (await api.request.get('/api/v3/images')).json());
  const missing = new Set<string>();
  for (const file of Object.values(imageFiles)) {
    const curated = inventory.images.find(image => image.name === file);
    if (!curated) throw new Error(`The curated asset ${file} must appear in the image inventory.`);
    missing.add(new URL(curated.thumbnail_url, server.origin).pathname);
  }
  await page.route(url => missing.has(url.pathname), route => route.fulfill({ status: 404, contentType: 'text/plain', body: 'missing' }));
  await guard(page, { allow: [/404/] });

  for (const [width, height] of widths) {
    await page.setViewportSize({ width, height });
    await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
    await expect(page.locator('#tablet-health .state-ok')).toHaveCount(4, { timeout: 20_000 });

    for (const [script, name] of Object.entries(names)) {
      const row = page.locator(`#tablet-row-${tabletIds[script]}`);
      await row.scrollIntoViewIfNeeded();
      const shown = await expectReadable(row.locator('.row-name'), name, `${width}px ${script} tablet row`, true);
      await row.click();
      const title = page.locator('#tablet-title');
      await expect(title).toHaveText(name);
      await expectReadable(title, name, `${width}px ${script} tablet title`, false);
      await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
      await expect(page.locator('#tablet-health .state-ok')).toHaveCount(4, { timeout: 20_000 });
      console.log(`X13 ${width}px ${script} tablet: ${shown.visibleWidth}px of the row name visible, clipped=${shown.clipped}`);
    }

    await page.getByRole('button', { name: 'All images', exact: true }).click();
    const library = page.getByRole('dialog', { name: 'Library', exact: true });
    await expect(library).toBeVisible();
    for (const [script, file] of Object.entries(imageFiles)) {
      const tile = library.locator('.image-tile').filter({ has: page.locator('.source-name', { hasText: file }) });
      await expect(tile, `${width}px ${script} image tile`).toHaveCount(1);
      await expect(tile.locator('img'), `${width}px ${script} image tile: a missing thumbnail leaves no broken image`).toHaveCount(0);
      await expect(tile.locator('svg'), `${width}px ${script} image tile: a missing thumbnail shows the fallback icon`).toBeVisible();
      await expectReadable(tile.locator('.source-name'), file, `${width}px ${script} image name`, false);
      const inside = await tile.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        const grid = element.parentElement?.getBoundingClientRect();
        return !grid || (rect.left >= grid.left - 0.5 && rect.right <= grid.right + 0.5);
      });
      expect(inside, `${width}px ${script} image tile stays inside the library grid`).toBe(true);
    }
    const loaded = library.locator('.image-tile').filter({ hasText: 'EXLENT_Cohort_3_Flyer_Temp.png' }).locator('img');
    await expect(loaded, `${width}px: a thumbnail that exists still loads`).toHaveCount(1);
    expect(await loaded.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0), `${width}px: the real thumbnail decoded`).toBe(true);
    console.log(`X13 ${width}x${height}: Latin, Arabic and CJK tablet and image names readable; missing thumbnails show the fallback`);
    await page.getByRole('button', { name: 'Close Library', exact: true }).click();
    await expect(library).not.toBeVisible();
  }
});
