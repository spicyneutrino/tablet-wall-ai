import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import type { Request } from '@playwright/test';
import { expect, test } from '../fixtures';

const twoColour = fileURLToPath(new URL('../fixtures/images/two-colour.png', import.meta.url));
const flyer = fileURLToPath(new URL('../fixtures/images/EXLENT_Cohort_3_Flyer_Temp.png', import.meta.url));

test.use({ serverScope: 'parity-P1' });

function summary(request: Request) {
  const url = new URL(request.url());
  return { method: request.method(), path: url.pathname, ifMatch: request.headers()['if-match'] ?? null,
    body: request.postData() ? JSON.parse(request.postData() ?? 'null') as unknown : null };
}

test('P1 Opt-in shows the playlist controls. Editing and saving the playlist sends `If-Match` with the playlist ETag. A stale ETag gives 412 and keeps the edits', async ({ server, api, page, writes, guard, axe }, info) => {
  test.setTimeout(120_000);
  await mkdir('/tmp/U30-shots', { recursive: true });
  await guard(page, { allow: [/\/api\/v3\/playlist/] });
  const first = await api.upload(twoColour);
  const second = await api.upload(flyer);
  const sent = writes(page);

  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: 'Server', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'Server', exact: true });
  await sheet.getByRole('tab', { name: 'Playback' }).click();
  await expect(sheet.getByRole('heading', { name: 'Playlist', exact: true })).toHaveCount(0);
  await sheet.getByRole('switch', { name: /Playlist and playback/ }).check();
  await expect(sheet.getByRole('heading', { name: 'Playlist', exact: true })).toBeVisible();
  await expect(sheet.getByText('No images yet. Pick one below and choose Add.')).toBeVisible();
  const saveButton = sheet.getByRole('button', { name: 'Save playlist' });
  await expect(saveButton).toBeDisabled();
  await expect(saveButton).toHaveAccessibleDescription('Add at least one image first.');

  await sheet.getByLabel('Image to add').selectOption({ label: 'two-colour.png' });
  await sheet.getByRole('button', { name: 'Add', exact: true }).click();
  const dwell = sheet.getByLabel('two-colour.png: seconds on screen');
  await expect(dwell).toHaveValue('5');
  for (const [text, error] of [['0', 'Use 1 to 600 seconds.'], ['601', 'Use 1 to 600 seconds.'], ['soon', 'Use a number of seconds, such as 5 or 2.5.'], ['', 'Enter how many seconds this image stays up.']] as const) {
    await dwell.fill(text);
    await expect(sheet.getByRole('alert').filter({ hasText: error })).toBeVisible();
    await expect(dwell).toHaveAttribute('aria-invalid', 'true');
    await expect(saveButton).toBeDisabled();
    await expect(saveButton).toHaveAccessibleDescription('Fix the seconds shown in red first.');
  }
  await dwell.fill('3');
  await expect(dwell).not.toHaveAttribute('aria-invalid', 'true');
  await expect(saveButton).toBeEnabled();
  expect(sent).toEqual([]);

  await sheet.getByLabel('Image to add').selectOption({ label: 'EXLENT_Cohort_3_Flyer_Temp.png' });
  await sheet.getByRole('button', { name: 'Add', exact: true }).click();
  await sheet.getByLabel('EXLENT_Cohort_3_Flyer_Temp.png: seconds on screen').fill('2.5');
  const rows = sheet.getByRole('list', { name: 'Playlist order' }).getByRole('listitem');
  await expect(rows).toHaveCount(2);
  await sheet.getByRole('button', { name: 'Move EXLENT_Cohort_3_Flyer_Temp.png up' }).click();
  await expect(rows.first()).toContainText('EXLENT_Cohort_3_Flyer_Temp.png');
  await expect(sheet.getByRole('button', { name: 'Move EXLENT_Cohort_3_Flyer_Temp.png down' })).toBeFocused();
  await expect(sheet.getByRole('button', { name: 'Move EXLENT_Cohort_3_Flyer_Temp.png up' })).toHaveCount(0);

  await sheet.getByRole('button', { name: 'Remove two-colour.png' }).click();
  await expect(rows).toHaveCount(1);
  await expect(sheet.getByText('Removed two-colour.png.', { exact: false }).first()).toBeVisible();
  await sheet.getByRole('button', { name: 'Undo' }).click();
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(1)).toContainText('two-colour.png');
  await expect(sheet.getByRole('button', { name: 'Undo' })).toHaveCount(0);
  await sheet.getByRole('switch', { name: 'Loop' }).check();
  expect(sent).toEqual([]);

  const initial = await api.request.get('/api/v3/playlist');
  const staleEtag = ((await initial.json()) as { etag: string }).etag;
  await saveButton.click();
  await expect.poll(() => sent.length).toBe(1);
  expect(summary(sent[0]!)).toEqual({ method: 'PUT', path: '/api/v3/playlist', ifMatch: staleEtag,
    body: { items: [{ asset: second.id, dwell_ms: 2500 }, { asset: first.id, dwell_ms: 3000 }], loop: true } });
  await expect(sheet.getByText('Playlist saved.')).toBeVisible();
  await expect(sheet.getByText('2 items, 5.5 s loop')).toBeVisible();
  const saved = (await (await api.request.get('/api/v3/playlist')).json()) as { playlist: { items: unknown[]; loop: boolean }; etag: string };
  expect(saved.playlist).toMatchObject({ loop: true, items: [{ asset: second.id, dwell_ms: 2500 }, { asset: first.id, dwell_ms: 3000 }] });
  expect(saved.etag).not.toBe(staleEtag);
  await expect(saveButton).toBeDisabled();
  await expect(saveButton).toHaveAccessibleDescription('No changes to save.');

  const elsewhere = await api.request.put('/api/v3/playlist', { headers: { 'If-Match': saved.etag },
    data: { items: [{ asset: first.id, dwell_ms: 1000 }], loop: false } });
  expect(elsewhere.ok(), await elsewhere.text()).toBe(true);
  await sheet.getByRole('switch', { name: 'Loop' }).uncheck();
  await saveButton.click();
  await expect.poll(() => sent.length).toBe(2);
  expect(summary(sent[1]!)).toMatchObject({ method: 'PUT', path: '/api/v3/playlist', ifMatch: saved.etag });
  await expect(sheet.getByText('The saved playlist changed', { exact: true })).toBeVisible();
  await expect(rows).toHaveCount(2);
  await expect(sheet.getByRole('switch', { name: 'Loop' })).not.toBeChecked();
  await expect(sheet.getByLabel('EXLENT_Cohort_3_Flyer_Temp.png: seconds on screen')).toHaveValue('2.5');

  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const theme of ['light', 'dark']) {
    await page.evaluate(value => {
      localStorage.setItem('tablet-wall-theme', value);
      document.documentElement.dataset.theme = value;
    }, theme);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: `/tmp/U30-shots/playlist-${info.project.name}-${theme}.png` });
  }
  expect((await axe(page)).violations).toEqual([]);

  const kept = await api.request.get('/api/v3/playlist');
  const currentEtag = ((await kept.json()) as { etag: string }).etag;
  await sheet.getByRole('button', { name: 'Keep my edits' }).click();
  await expect(sheet.getByText('The saved playlist changed', { exact: true })).toHaveCount(0);
  await saveButton.click();
  await expect.poll(() => sent.length).toBe(3);
  expect(summary(sent[2]!)).toEqual({ method: 'PUT', path: '/api/v3/playlist', ifMatch: currentEtag,
    body: { items: [{ asset: second.id, dwell_ms: 2500 }, { asset: first.id, dwell_ms: 3000 }], loop: false } });
  await expect(sheet.getByText('Playlist saved.')).toBeVisible();
});
