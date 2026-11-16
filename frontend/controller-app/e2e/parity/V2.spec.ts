import { readFile } from 'node:fs/promises';
import { z } from 'zod';
import { expect, test } from '../fixtures';

test.use({ serverScope: 'parity-V2' });

const healthSchema = z.object({ ready: z.literal(true), schema: z.number() });
const diagnosticsSchema = z.object({
  media: z.object({ assets: z.number(), objects: z.number() }),
  db: z.object({ schema: z.number() }),
  backup: z.object({ last_manifest_at: z.string().nullable() }),
});

test('V2 Health shows `healthz` and diagnostics. Verify runs `?verify=1`. Download saves the JSON', async ({ page, server, api, guard }) => {
  await guard(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('status')).toHaveText('Live operator updates connected.');
  const health = healthSchema.parse(await (await api.request.get('/healthz')).json());
  const diagnostics = diagnosticsSchema.parse(await (await api.request.get('/diagnostics')).json());

  await page.getByRole('button', { name: 'Server', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'Server', exact: true });
  await expect(sheet.getByRole('tab', { name: 'Health', exact: true })).toHaveAttribute('aria-selected', 'true');
  await expect(sheet.getByText('All checks pass', { exact: true })).toBeVisible();
  await expect(sheet.getByRole('heading', { name: 'Diagnostics', exact: true })).toBeVisible();
  await expect(sheet.getByText('Ready', { exact: true })).toBeVisible();
  await expect(sheet.getByText(new RegExp(`schema ${health.schema}`))).toBeVisible();
  await expect(sheet.getByText(`${diagnostics.media.assets} assets, ${diagnostics.media.objects} objects`)).toBeVisible();

  let release = () => {};
  const gate = new Promise<void>((resolve) => { release = resolve; });
  await page.route('**/diagnostics?verify=1', async (route) => { await gate; await route.continue(); });
  const verifyRequest = page.waitForRequest((request) => request.method() === 'GET' && new URL(request.url()).pathname === '/diagnostics' && new URL(request.url()).searchParams.get('verify') === '1');
  await sheet.getByRole('button', { name: 'Verify files', exact: true }).click();
  await verifyRequest;
  await expect(sheet.getByRole('button', { name: 'Checking files' })).toBeVisible();
  release();
  await expect(sheet.getByText('File check passed. Every ready object matches its recorded id.')).toBeVisible();
  await page.unroute('**/diagnostics?verify=1');

  const [download] = await Promise.all([
    page.waitForEvent('download'),
    sheet.getByRole('button', { name: 'Download report', exact: true }).click(),
  ]);
  const saved = diagnosticsSchema.parse(JSON.parse(await readFile(await download.path(), 'utf8')));
  expect(saved.media.assets).toBe(diagnostics.media.assets);
  expect(saved.media.objects).toBe(diagnostics.media.objects);
  expect(saved.db.schema).toBe(diagnostics.db.schema);
  expect(saved.backup.last_manifest_at).toBe(diagnostics.backup.last_manifest_at);
});
