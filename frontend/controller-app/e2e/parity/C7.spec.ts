import { DatabaseSync } from 'node:sqlite';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Request } from '@playwright/test';
import { expect, test } from '../fixtures';
import { imageColors } from '../fixtures/fleet';

const image = fileURLToPath(new URL('../fixtures/images/two-colour.png', import.meta.url));

test.use({ serverScope: 'parity-C7' });

function summary(request: Request) {
  const url = new URL(request.url());
  return { method: request.method(), path: url.pathname + url.search,
    ifMatch: request.headers()['if-match'] ?? null, body: request.postData() };
}

test('C7 Saved content: an invalid name sends 0 requests. Save, replace, delete, and recall then Show work', async ({ server, api, tablets, page, writes, tabletPixel, guard }, info) => {
  test.setTimeout(180_000);
  await mkdir('/tmp/U18-shots', { recursive: true });
  await guard(page, { allow: [/\/api\/v3\/scenes\/[^/]+\/recall/] });
  const fleet = await tablets(2, { viewport: { width: 800, height: 800 } });
  await api.placeLogical({ columns: 2, rows: 1, cellWidth: 800, cellHeight: 800,
    deviceIds: fleet.map(tablet => tablet.id) });
  const asset = await api.upload(image);
  await api.scene({ type: 'image', asset: asset.id, fit: 'cover', background: '#0b1120' });
  await expect.poll(async () => Object.keys((await api.config()).runtime.devices).length).toBe(2);

  const sent = writes(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  await page.getByRole('tab', { name: 'Saved', exact: true }).click();
  await expect(page.getByText('Nothing saved yet. Save what is on the wall to reuse it.')).toBeVisible();
  expect(sent).toEqual([]);

  const save = page.getByRole('dialog', { name: 'Save content' });
  await page.getByRole('button', { name: 'Save current…' }).click();
  await save.getByLabel('Name').fill('-not a name');
  await save.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(save.locator('.field-error')).toHaveText(/Use letters, numbers, spaces, dots, underscores or hyphens/);
  expect(sent).toEqual([]);
  await save.getByRole('button', { name: 'Cancel' }).click();
  await expect(save).toBeHidden();
  expect(sent).toEqual([]);

  const database = new DatabaseSync(join(server.directory, 'wall.db'));
  try {
    const insert = database.prepare('INSERT OR REPLACE INTO saved_scenes (name, content) VALUES (?, ?)');
    insert.run('Gone', JSON.stringify({ type: 'image', asset: `sha256:${'b'.repeat(64)}`, fit: 'cover',
      background: '#0b1120', intrinsicWidth: 1600, intrinsicHeight: 900 }));
    insert.run('Studio', JSON.stringify({ type: 'image', asset: asset.id, fit: 'contain',
      background: '#0b1120', intrinsicWidth: asset.intrinsicWidth, intrinsicHeight: asset.intrinsicHeight }));
  } finally { database.close(); }

  await page.reload({ waitUntil: 'networkidle' });
  await page.getByRole('tab', { name: 'Saved', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Gone', exact: true })).toBeVisible();

  const saveEtag = (await api.config()).etag;
  await page.getByRole('button', { name: 'Save current…' }).click();
  await save.getByLabel('Name').fill('Lobby');
  await save.getByRole('button', { name: 'Save', exact: true }).click();
  await expect.poll(() => sent.length).toBe(1);
  expect(summary(sent[0]!)).toEqual({ method: 'PUT', path: '/api/v3/scenes/Lobby', ifMatch: saveEtag, body: null });
  await expect(page.getByRole('button', { name: 'Lobby', exact: true })).toBeVisible();

  await api.scene({ type: 'calibration' });
  await expect(page.locator('.desktop-onwall')).toContainText('Calibration grid');

  await page.getByRole('button', { name: 'Lobby', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Preview', exact: true })).toContainText('Lobby, Fill');
  await expect(page.getByRole('button', { name: 'Lobby', exact: true })).toHaveAttribute('aria-pressed', 'true');
  expect(sent).toHaveLength(1);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const theme of ['light', 'dark']) {
    await page.evaluate(value => {
      localStorage.setItem('tablet-wall-theme', value);
      document.documentElement.dataset.theme = value;
    }, theme);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: `/tmp/U18-shots/saved-selected-${info.project.name}-${theme}.png`, fullPage: true });
  }
  await page.emulateMedia({ reducedMotion: 'no-preference' });

  const recallEtag = (await api.config()).etag;
  await page.getByRole('button', { name: 'Actions for Lobby' }).click();
  await page.getByRole('menuitem', { name: 'Show on wall' }).click();
  await expect.poll(() => sent.length).toBe(2);
  expect(summary(sent[1]!)).toEqual({ method: 'POST', path: '/api/v3/scenes/Lobby/recall',
    ifMatch: recallEtag, body: null });
  await expect(page.getByText(/Content “Lobby” is on the wall/)).toBeVisible();
  await expect.poll(async () => Promise.all(fleet.map(async tablet =>
    (await api.config()).runtime.devices[tablet.id]?.render.state)), { timeout: 10_000 })
    .toEqual(['displayed', 'displayed']);
  for (const [index, tablet] of fleet.entries()) {
    const centre = await tablet.page.locator('#surface').evaluate(canvas => {
      if (!(canvas instanceof HTMLCanvasElement)) throw new Error('Expected tablet canvas');
      return { x: canvas.width / 2, y: canvas.height / 2 };
    });
    const expected = index ? imageColors.right : imageColors.left;
    await expect.poll(async () => Math.max(...(await tabletPixel(tablet, centre.x, centre.y)).slice(0, 3)
      .map((value, channel) => Math.abs(value - (expected[channel] ?? 0)))), { timeout: 10_000 }).toBeLessThanOrEqual(30);
  }

  await page.getByRole('button', { name: 'Lobby', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Preview', exact: true })).toContainText('Lobby, Fill');
  const primary = page.getByRole('button', { name: 'Show on wall', exact: true });
  await expect(primary).toBeDisabled();
  await expect(primary).toHaveAccessibleDescription('This is already on the wall.');
  await page.getByRole('button', { name: 'Discard', exact: true }).click();

  await page.getByRole('button', { name: 'Save current…' }).click();
  await save.getByLabel('Name').fill('Lobby');
  await save.getByRole('button', { name: 'Save', exact: true }).click();
  const replace = page.getByRole('dialog', { name: 'Replace saved content' });
  await expect(replace).toBeVisible();
  await expect(replace.getByRole('button', { name: 'Cancel' })).toBeFocused();
  await replace.getByRole('button', { name: 'Cancel' }).click();
  await expect(replace).toBeHidden();
  expect(sent).toHaveLength(2);

  await page.getByRole('button', { name: 'Save current…' }).click();
  await save.getByLabel('Name').fill('Lobby');
  await save.getByRole('button', { name: 'Save', exact: true }).click();
  await replace.getByRole('button', { name: 'Replace', exact: true }).click();
  await expect.poll(() => sent.length).toBe(3);
  expect(summary(sent[2]!)).toMatchObject({ method: 'PUT', path: '/api/v3/scenes/Lobby?replace=true' });
  await expect(page.getByText(/Content “Lobby” replaced/)).toBeVisible();

  await page.getByRole('button', { name: 'Actions for Lobby' }).click();
  await page.getByRole('menuitem', { name: 'Delete' }).click();
  const remove = page.getByRole('dialog', { name: 'Delete saved content' });
  await expect(remove).toBeVisible();
  await expect(remove.getByRole('button', { name: 'Cancel' })).toBeFocused();
  await remove.getByRole('button', { name: 'Cancel' }).click();
  await expect(remove).toBeHidden();
  expect(sent).toHaveLength(3);

  await page.getByRole('button', { name: 'Actions for Lobby' }).click();
  await page.getByRole('menuitem', { name: 'Delete' }).click();
  await remove.getByRole('button', { name: 'Delete', exact: true }).click();
  await expect.poll(() => sent.length).toBe(4);
  expect(summary(sent[3]!)).toMatchObject({ method: 'DELETE', path: '/api/v3/scenes/Lobby' });  await expect(page.getByRole('button', { name: 'Lobby', exact: true })).toHaveCount(0);

  const studioEtag = (await api.config()).etag;
  await page.getByRole('button', { name: 'Studio', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Preview', exact: true })).toContainText('Studio, Fit');
  await expect(primary).toBeEnabled();
  await primary.click();
  await expect.poll(() => sent.length).toBe(5);
  expect(summary(sent[4]!)).toEqual({ method: 'POST', path: '/api/v3/scenes/Studio/recall',
    ifMatch: studioEtag, body: null });
  await expect(page.getByText('Content “Studio” is on the wall.')).toBeVisible();

  await page.getByRole('button', { name: 'Gone', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Preview', exact: true })).toContainText('Image unavailable');
  await primary.click();
  await expect.poll(() => sent.length).toBe(6);
  expect(summary(sent[5]!)).toMatchObject({ method: 'POST', path: '/api/v3/scenes/Gone/recall' });
  await expect(page.getByText('The image for this saved content was deleted.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Gone', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('region', { name: 'Preview', exact: true })).toContainText('Image unavailable');
  expect(sent.filter(request => request.method() === 'PUT'
    && new URL(request.url()).pathname === '/api/v3/scene')).toEqual([]);

  const saved = await (await api.request.get('/api/v3/scenes')).json() as { scenes: { name: string }[] };
  expect(saved.scenes.map(entry => entry.name)).not.toContain('Lobby');
  const config = await (await api.request.get('/api/v3/config')).json() as { scene: { content: { type: string } } };
  expect(config.scene.content.type).toBe('image');
});
