import { DatabaseSync } from 'node:sqlite';
import { join } from 'node:path';
import type { Request } from '@playwright/test';
import { expect, test } from '../fixtures';
import { fleet } from '../fixtures/fleet';

test.use({ serverScope: 'parity-A5' });

function summary(request: Request) {
  const url = new URL(request.url());
  return { method: request.method(), path: url.pathname + url.search,
    ifMatch: request.headers()['if-match'] ?? null, body: request.postData() };
}

test('A5 Saved arrangements (logical and physical, invalid entries listed): preview, recall with a kind-change confirmation, return point shown, save, replace, delete', async ({ browser, server, api, writes, guard }, info) => {
  test.setTimeout(180_000);
  const viewport = info.project.use.viewport ?? { width: 1440, height: 900 };
  const context = await browser.newContext({ viewport, hasTouch: viewport.width < 1024 });
  context.setDefaultTimeout(10_000);
  const page = await context.newPage();
  await guard(page);
  const sent = writes(page);
  const id = fleet[0].id;
  const request = async (method: 'put' | 'post', path: string, data?: unknown) => {
    const response = await api.request[method](path, { data, headers: { 'If-Match': (await api.config()).etag } });
    expect(response.ok(), await response.text()).toBe(true);
    return response;
  };
  try {
    await api.placeLogical({ columns: 2, rows: 1, deviceIds: [id] });
    await request('put', '/api/v3/logical-layouts/Grid%20two');
    const display = await request('put', `/api/v3/displays/${id}`, { active_width_mm: 150, active_height_mm: 200,
      bezels: { left: 10, top: 10, right: 10, bottom: 10 }, panel_pixels: { width: 768, height: 1024 },
      label: 'Layout tablet', provenance: 'manual' });
    const revision = (await display.json() as { display: { revision: number } }).display.revision;
    await request('put', `/api/v3/calibrations/${id}`, { profile_revision: revision, viewport_width: 768, viewport_height: 1024,
      dpr: 2, orientation: 0, mode: 'tab', quarter_turn: 0, panel_offset_mm: [0, 0], mm_per_css: [0.1953125, 0.1953125],
      anchor_edge: 'top-left', uncertainty_mm: 0.5, method: 'manual' });
    await request('put', '/api/v3/layout', { bounds: { x: 0, y: 0, width: 340, height: 440 }, sizing: { mode: 'fixed', padding: 0 },
      slots: { [id]: { center_x_mm: 85, center_y_mm: 110, mount_angle: 0, nudge_x_mm: 0, nudge_y_mm: 0,
        profile_revision: revision, calibration_revision: 1 } } });
    await request('put', '/api/v3/layouts/Desk');
    const database = new DatabaseSync(join(server.directory, 'wall.db'));
    try {
      database.prepare('INSERT OR REPLACE INTO saved_layouts (name, layout) VALUES (?, ?)')
        .run('Broken', JSON.stringify({ width: 0, height: 100, placements: {} }));
    } finally { database.close(); }

    await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
    await page.getByRole('tab', { name: 'Layouts', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Grid two', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Desk', exact: true })).toBeVisible();
    const broken = page.getByRole('button', { name: 'Broken', exact: true });
    await expect(broken).toBeVisible();
    await expect(broken).toBeDisabled();
    await expect(broken).toHaveAccessibleDescription(/Damaged saved data/);
    await page.getByRole('button', { name: 'Actions for Broken' }).click();
    await expect(page.getByRole('menuitem', { name: 'Apply layout' })).toHaveAttribute('aria-disabled', 'true');
    await expect(page.getByRole('menuitem', { name: 'Delete' })).not.toHaveAttribute('aria-disabled', 'true');
    await page.keyboard.press('Escape');
    expect(sent).toEqual([]);

    await page.getByRole('button', { name: 'Grid two', exact: true }).click();
    await expect(page.locator('.preview-pinned > .monitor-label > .monitor-description')).toHaveText('Your layout: switched to a logical layout');
    expect(sent).toEqual([]);

    const openActions = async (name: string) => {
      await page.getByRole('button', { name: `Actions for ${name}` }).click();
    };
    await openActions('Grid two');
    await page.getByRole('menuitem', { name: 'Apply layout' }).click();
    const kindDialog = page.getByRole('dialog', { name: 'Change the wall kind' });
    await expect(kindDialog).toBeVisible();
    await expect(kindDialog.getByRole('button', { name: 'Cancel' })).toBeFocused();
    await kindDialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(kindDialog).toBeHidden();
    expect(sent).toEqual([]);

    const logicalEtag = (await api.config()).etag;
    await openActions('Grid two');
    await page.getByRole('menuitem', { name: 'Apply layout' }).click();
    await kindDialog.getByRole('button', { name: 'Apply layout', exact: true }).click();
    await expect.poll(() => sent.length).toBe(1);
    expect(summary(sent[0]!)).toEqual({ method: 'POST', path: '/api/v3/logical-layouts/Grid%20two/recall',
      ifMatch: logicalEtag, body: null });
    await expect(page.getByText(/Arrangement “Grid two” recalled/)).toBeVisible();
    await expect(page.getByRole('button', { name: /^Restore, \d{2}:\d{2}$/ })).toBeVisible();

    await page.getByRole('button', { name: 'Desk', exact: true }).click();
    await expect(page.locator('.preview-pinned > .monitor-label > .monitor-description')).toHaveText('Your layout: switched to a physical layout');
    expect(sent.length).toBe(1);

    const physicalEtag = (await api.config()).etag;
    await openActions('Desk');
    await page.getByRole('menuitem', { name: 'Apply layout' }).click();
    await kindDialog.getByRole('button', { name: 'Apply layout', exact: true }).click();
    await expect.poll(() => sent.length).toBe(2);
    expect(summary(sent[1]!)).toEqual({ method: 'POST', path: '/api/v3/layouts/Desk/recall',
      ifMatch: physicalEtag, body: null });

    const save = page.getByRole('dialog', { name: 'Save arrangement' });
    await page.getByRole('button', { name: 'Save current…' }).click();
    await save.getByLabel('Name').fill('-not a name');
    await save.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(save.locator('.field-error')).toHaveText(/Use letters, numbers, spaces, dots, underscores or hyphens/);
    expect(sent.length).toBe(2);
    await save.getByRole('button', { name: 'Cancel' }).click();

    const saveEtag = (await api.config()).etag;
    await page.getByRole('button', { name: 'Save current…' }).click();
    await save.getByLabel('Name').fill('Studio');
    await save.getByRole('button', { name: 'Save', exact: true }).click();
    await expect.poll(() => sent.length).toBe(3);
    expect(summary(sent[2]!)).toEqual({ method: 'PUT', path: '/api/v3/layouts/Studio', ifMatch: saveEtag, body: null });
    await expect(page.getByRole('button', { name: 'Studio', exact: true })).toBeVisible();

    await page.getByRole('button', { name: 'Save current…' }).click();
    await save.getByLabel('Name').fill('Studio');
    await save.getByRole('button', { name: 'Save', exact: true }).click();
    const replace = page.getByRole('dialog', { name: 'Replace saved arrangement' });
    await expect(replace).toBeVisible();
    await expect(replace.getByRole('button', { name: 'Cancel' })).toBeFocused();
    await replace.getByRole('button', { name: 'Cancel' }).click();
    await expect(replace).toBeHidden();
    expect(sent.length).toBe(3);

    await page.getByRole('button', { name: 'Save current…' }).click();
    await save.getByLabel('Name').fill('Studio');
    await save.getByRole('button', { name: 'Save', exact: true }).click();
    await replace.getByRole('button', { name: 'Replace', exact: true }).click();
    await expect.poll(() => sent.length).toBe(4);
    expect(summary(sent[3]!)).toMatchObject({ method: 'PUT', path: '/api/v3/layouts/Studio?replace=true' });
    await expect(page.getByText(/Arrangement “Studio” replaced/)).toBeVisible();

    await page.getByRole('button', { name: 'Studio', exact: true }).click();
    await openActions('Studio');
    await page.getByRole('menuitem', { name: 'Delete' }).click();
    const remove = page.getByRole('dialog', { name: 'Delete saved arrangement' });
    await expect(remove).toBeVisible();
    await expect(remove.getByRole('button', { name: 'Cancel' })).toBeFocused();
    await remove.getByRole('button', { name: 'Cancel' }).click();
    await expect(remove).toBeHidden();
    expect(sent.length).toBe(4);

    await openActions('Studio');
    await page.getByRole('menuitem', { name: 'Delete' }).click();
    await remove.getByRole('button', { name: 'Delete', exact: true }).click();
    await expect.poll(() => sent.length).toBe(5);
    expect(summary(sent[4]!)).toMatchObject({ method: 'DELETE', path: '/api/v3/layouts/Studio' });
    await expect(page.getByRole('button', { name: 'Studio', exact: true })).toHaveCount(0);
    expect(sent.length).toBe(5);

    const saved = await (await api.request.get('/api/v3/layouts')).json() as { layouts: { name: string }[] };
    expect(saved.layouts.map(entry => entry.name)).not.toContain('Studio');
    const config = await (await api.request.get('/api/v3/config')).json() as { layout: { kind: string } };
    expect(config.layout.kind).toBe('physical');
  } finally { await context.close(); }
});
