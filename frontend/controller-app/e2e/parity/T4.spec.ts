import type { Page } from '@playwright/test';
import { test, expect } from '../fixtures';
import { ConfigSchema } from '../../src/api/config';
import { DeviceIdSchema } from '../../src/api/devices';
import { entries } from '../../src/domain/layout';

test.use({ serverScope: 'parity-T4' });
test('T4 Remove placement, and Forget (offline only, impact shown, explicit acknowledgement)', async ({ page, server, api, tablets, writes, guard, axe }) => {
  test.setTimeout(180_000);
  await guard(page);
  const fleet = await tablets(3);
  const [stay, middle, right] = fleet;
  if (!stay || !middle || !right) throw new Error('Three real tablets are required.');
  const config = async () => ConfigSchema.parse(await api.config());
  const placed = async () => Object.keys(entries((await config()).layout));
  const device = async (id: string) => (await config()).runtime.devices[DeviceIdSchema.parse(id)];
  const rename = async (id: string, label: string) => {
    const response = await api.request.patch(`/api/v3/devices/${id}`, { headers: { 'If-Match': (await config()).etag }, data: { label } });
    expect(response.ok(), await response.text()).toBe(true);
  };
  await expect.poll(async () => (await Promise.all(fleet.map(({ id }) => device(id)))).map(item => item?.online)).toEqual([true, true, true]);
  await api.placeLogical({ columns: 3, rows: 1, deviceIds: fleet.map(tablet => tablet.id) });
  await rename(stay.id, 'Stay');
  await rename(middle.id, 'Middle');
  await rename(right.id, 'Right');
  const saved = await api.request.put('/api/v3/logical-layouts/Three across', { headers: { 'If-Match': (await config()).etag } });
  expect(saved.ok(), await saved.text()).toBe(true);
  await expect.poll(async () => (await device(stay.id))?.render?.state).toBe('displayed');

  const sent = writes(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  const choose = async (id: string, title: string) => {
    await page.locator(`#tablet-row-${id}`).click();
    await expect(page.locator('#tablet-title')).toHaveText(title);
    const details = page.locator('details.tablet-lifecycle');
    if (!await details.evaluate(element => (element as HTMLDetailsElement).open)) await details.locator('summary').click();
    return details;
  };
  const dialogOf = (name: string | RegExp) => page.getByRole('dialog', { name });
  const offline = async (tablet: { id: string; page: Page }) => {
    await tablet.page.close();
    await expect.poll(async () => (await device(tablet.id))?.online).toBe(false);
  };

  // Remove: the impact is read first, Cancel is focused and sends nothing.
  let details = await choose(middle.id, 'Middle');
  await details.getByRole('button', { name: 'Remove from wall', exact: true }).click();
  let dialog = dialogOf('Remove Middle from the wall?');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText('Saved layouts that include it keep its place: Three across.')).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Cancel', exact: true })).toBeFocused();
  expect((await axe(page)).violations).toEqual([]);
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(dialog).toBeHidden();
  expect(sent).toEqual([]);
  expect(await placed()).toContain(middle.id);

  await details.getByRole('button', { name: 'Remove from wall', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'Remove from wall', exact: true })).toBeEnabled();
  const removeEtag = (await config()).etag;
  await dialog.getByRole('button', { name: 'Remove from wall', exact: true }).click();
  await expect(dialog).toBeHidden();
  expect(sent).toHaveLength(1);
  expect(sent[0]!.method()).toBe('DELETE');
  expect(new URL(sent[0]!.url()).pathname).toBe(`/api/v3/devices/${middle.id}/placement`);
  expect(sent[0]!.headers()['if-match']).toBe(removeEtag);
  const notice = page.getByRole('status').filter({ hasText: 'Middle is off the wall' });
  await expect(notice).toBeVisible();
  await expect(notice).toBeFocused();
  expect(await placed()).toEqual([stay.id, right.id]);
  expect((await device(middle.id))?.online).toBe(true);
  const layouts = await (await api.request.get('/api/v3/logical-layouts')).json() as { layouts: { name: string; layout: { placements: Record<string, unknown> } }[] };
  expect(Object.keys(layouts.layouts.find(layout => layout.name === 'Three across')!.layout.placements)).toContain(middle.id);
  await notice.getByRole('button', { name: 'Dismiss', exact: true }).click();
  await expect(notice).toBeHidden();

  // Remove is not offered for a tablet that is not on the wall.
  details = await choose(middle.id, 'Middle');
  await expect(details.getByRole('button', { name: 'Remove from wall', exact: true })).toBeDisabled();
  await expect(details.getByText('Middle is not on the wall.')).toBeVisible();

  // Forget is offered only when the tablet is offline.
  await expect(details.getByRole('button', { name: 'Forget tablet', exact: true })).toBeDisabled();
  await expect(details.getByText('Forget needs the tablet offline.')).toBeVisible();
  await offline(middle);
  await expect(details.getByRole('button', { name: 'Forget tablet', exact: true })).toBeEnabled();

  // Forget an offline tablet that is not on the wall: no wall acknowledgement is asked for.
  sent.length = 0;
  await details.getByRole('button', { name: 'Forget tablet', exact: true }).click();
  dialog = dialogOf('Forget Middle?');
  await expect(dialog.getByText('This cannot be undone.', { exact: false })).toBeVisible();
  await expect(dialog.getByText('It is not on the wall.')).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Cancel', exact: true })).toBeFocused();
  await expect(dialog.getByRole('switch')).toHaveCount(0);
  expect((await axe(page)).violations).toEqual([]);
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  expect(sent).toEqual([]);
  await details.getByRole('button', { name: 'Forget tablet', exact: true }).click();
  const forgetEtag = (await config()).etag;
  await dialog.getByRole('button', { name: 'Forget tablet', exact: true }).click();
  await expect(dialog).toBeHidden();
  expect(sent).toHaveLength(1);
  expect(sent[0]!.method()).toBe('DELETE');
  expect(new URL(sent[0]!.url()).pathname).toBe(`/api/v3/devices/${middle.id}`);
  expect(sent[0]!.headers()['if-match']).toBe(forgetEtag);
  expect(sent[0]!.postDataJSON()).toEqual({ remove_active: false, saved_layouts: 'keep' });
  await expect(page.getByRole('status').filter({ hasText: 'Middle was forgotten.' })).toBeFocused();
  await expect.poll(async () => (await device(middle.id)) === undefined).toBe(true);
  await expect(page.locator(`#tablet-row-${middle.id}`)).toHaveCount(0);

  // The old browser can register again, as a new tablet with no name.
  const [again] = await tablets(1, { ids: [middle.id] });
  await expect.poll(async () => (await device(middle.id))?.online).toBe(true);
  expect((await device(middle.id))?.label ?? null).toBeNull();
  expect(await placed()).toEqual([stay.id, right.id]);
  await offline(again!);

  // Forget a placed offline tablet: the wall acknowledgement is required, and a reconnect makes the review stale.
  sent.length = 0;
  await offline(right);
  details = await choose(right.id, 'Right');
  await details.getByRole('button', { name: 'Forget tablet', exact: true }).click();
  dialog = dialogOf('Forget Right?');
  await expect(dialog.getByText('Saved layouts that include it keep its reserved place: Three across.')).toBeVisible();
  const confirm = dialog.getByRole('button', { name: 'Forget tablet', exact: true });
  await expect(confirm).toBeDisabled();
  await expect(dialog.getByText('Switch on “Also remove it from the wall” to continue.')).toBeVisible();
  const reopened = await right.context.newPage();
  await guard(reopened);
  await reopened.goto(`${server.origin}/client/`);
  await expect(dialog.getByRole('alert').filter({ hasText: 'came back online' })).toBeVisible();
  await dialog.getByRole('switch', { name: /Also remove it from the wall/ }).check();
  await expect(confirm).toBeDisabled();
  await reopened.close();
  await expect.poll(async () => (await device(right.id))?.online).toBe(false);
  await expect(dialog.getByRole('alert').filter({ hasText: 'came back online' })).toHaveCount(0);
  await expect(confirm).toBeEnabled();
  expect(sent).toEqual([]);
  const placedEtag = (await config()).etag;
  await confirm.click();
  await expect(dialog).toBeHidden();
  expect(sent).toHaveLength(1);
  expect(sent[0]!.method()).toBe('DELETE');
  expect(new URL(sent[0]!.url()).pathname).toBe(`/api/v3/devices/${right.id}`);
  expect(sent[0]!.headers()['if-match']).toBe(placedEtag);
  expect(sent[0]!.postDataJSON()).toEqual({ remove_active: true, saved_layouts: 'keep' });
  await expect.poll(placed).toEqual([stay.id]);
  await expect.poll(async () => (await device(right.id)) === undefined).toBe(true);
  const after = await (await api.request.get('/api/v3/logical-layouts')).json() as { layouts: { name: string; layout: { placements: Record<string, unknown> } }[] };
  expect(Object.keys(after.layouts.find(layout => layout.name === 'Three across')!.layout.placements)).toContain(right.id);
  expect((await device(stay.id))?.online).toBe(true);
});
