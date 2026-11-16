import type { Request } from '@playwright/test';
import { expect, test } from '../fixtures';
import { fleet } from '../fixtures/fleet';

test.use({ serverScope: 'parity-A6' });

function summary(request: Request) {
  const url = new URL(request.url());
  return { method: request.method(), path: url.pathname + url.search,
    ifMatch: request.headers()['if-match'] ?? null, body: request.postData() };
}

test('A6 Empty wall needs confirmation and sends 1 POST `/api/v3/layout/clear`', async ({ browser, server, api, writes, guard }, info) => {
  test.setTimeout(120_000);
  const viewport = info.project.use.viewport ?? { width: 1440, height: 900 };
  const context = await browser.newContext({ viewport, hasTouch: viewport.width < 1024 });
  context.setDefaultTimeout(10_000);
  const page = await context.newPage();
  await guard(page);
  const sent = writes(page);
  try {
    await api.placeLogical({ columns: 2, rows: 2, deviceIds: [fleet[0].id, fleet[1].id] });
    await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: 'Server', exact: true }).click();
    const sheet = page.getByRole('dialog', { name: 'Server' });
    await expect(sheet).toBeVisible();
    await sheet.getByRole('tab', { name: 'Backup and reset' }).click();

    await sheet.getByRole('button', { name: 'Clear wall…' }).click();
    const dialog = page.getByRole('dialog', { name: 'Clear every position?' });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText('The wall goes blank until you apply a layout.');
    await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused();
    await dialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(dialog).toBeHidden();
    expect(sent).toEqual([]);
    const untouched = await (await api.request.get('/api/v3/config')).json() as { layout: { placements?: object } };
    expect(Object.keys(untouched.layout.placements ?? {})).toHaveLength(2);

    const etag = (await api.config()).etag;
    await sheet.getByRole('button', { name: 'Clear wall…' }).click();
    await dialog.getByRole('button', { name: 'Clear wall' }).click();
    await expect.poll(() => sent.length).toBe(1);
    expect(summary(sent[0]!)).toEqual({ method: 'POST', path: '/api/v3/layout/clear', ifMatch: etag,
      body: JSON.stringify({ confirm: true }) });
    await expect(sheet.getByText('Active positions cleared. Tablets and saved arrangements are retained.')).toBeVisible();
    expect(sent.length).toBe(1);
    const cleared = await (await api.request.get('/api/v3/config')).json() as { layout: { placements?: object } };
    expect(Object.keys(cleared.layout.placements ?? {})).toEqual([]);
  } finally { await context.close(); }
});
