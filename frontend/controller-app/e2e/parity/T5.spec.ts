import { test, expect } from '../fixtures';
import type { Tablet } from '../fixtures';
import { ConfigSchema } from '../../src/api/config';
import { DeviceIdSchema } from '../../src/api/devices';
import { entries } from '../../src/domain/layout';
import { fleet } from '../fixtures/fleet';

test.use({ serverScope: 'parity-T5' });
test('T5 Replacement: same and different hardware, saved-layout choices, label and number transfer, new-connection and digest guards', async ({ page, server, api, tablets, writes, guard, axe }) => {
  test.setTimeout(300_000);
  await guard(page);
  const [id0, id1, id2] = fleet.map(item => item.id);
  const live = new Map<string, Tablet>();
  const join = async (id: string) => { live.set(id, (await tablets(1, { ids: [id] }))[0]!); };
  const config = async () => ConfigSchema.parse(await api.config());
  const device = async (id: string) => (await config()).runtime.devices[DeviceIdSchema.parse(id)];
  const placed = async () => Object.keys(entries((await config()).layout));
  const online = (id: string, value: boolean) => expect.poll(async () => (await device(id))?.online ?? false).toBe(value);
  const offline = async (id: string) => { await live.get(id)!.page.close(); await online(id, false); };
  const rename = async (id: string, label: string) => {
    const response = await api.request.patch(`/api/v3/devices/${id}`, { headers: { 'If-Match': (await config()).etag }, data: { label } });
    expect(response.ok(), await response.text()).toBe(true);
  };
  const save = async (name: string) => {
    const response = await api.request.put(`/api/v3/logical-layouts/${name}`, { headers: { 'If-Match': (await config()).etag } });
    expect(response.ok(), await response.text()).toBe(true);
  };
  const savedPlacements = async (name: string) => {
    const body = await (await api.request.get('/api/v3/logical-layouts')).json() as { layouts: { name: string; layout: { placements: Record<string, unknown> } }[] };
    return Object.keys(body.layouts.find(layout => layout.name === name)!.layout.placements);
  };
  const numberOf = async (id: string) => (await device(id))?.number;

  await join(id0!);
  await join(id1!);
  await online(id0!, true);
  await online(id1!, true);
  await api.placeLogical({ columns: 2, rows: 1, deviceIds: [id0!, id1!] });
  await rename(id0!, 'Keep');
  await rename(id1!, 'Wall left');
  await save('Layout one');
  await save('Layout two');
  const oldNumber = await numberOf(id1!);
  expect(oldNumber).toBeGreaterThan(0);

  const sent = writes(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  const dialog = page.getByRole('dialog', { name: /^Put .* in an offline tablet’s place\?$/ });
  const cancel = dialog.getByRole('button', { name: 'Cancel', exact: true });
  const hardware = dialog.getByLabel('Is it the same tablet?', { exact: true });
  const review = dialog.getByRole('button', { name: 'Review replacement', exact: true });
  const calls = (suffix: string) => sent.filter(request => new URL(request.url()).pathname.endsWith(suffix));
  const offer = page.getByRole('button', { name: 'Use the new tablet here', exact: true });
  const notice = (text: string | RegExp) => page.getByRole('status').filter({ hasText: text });

  // A: same hardware. Only one of two saved layouts is chosen. The label and number carry over.
  await offline(id1!);
  await join(id2!);
  await online(id2!, true);
  await expect(page.getByRole('heading', { name: 'A new tablet joined', exact: true })).toBeVisible();
  await expect(page.getByText(/is online and not on the wall\. If it replaces Wall left, put it in Wall left’s place\./)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Next step: bring Wall left back' })).toBeVisible();
  await offer.click();
  await expect(dialog).toBeVisible();
  await expect(cancel).toBeFocused();
  await expect(dialog.getByLabel('Replace', { exact: true })).toHaveValue(id1!);
  await expect(review).toBeDisabled();
  await expect(dialog.getByText('Say whether it is the same tablet.')).toBeVisible();
  await expect(dialog.getByRole('switch', { name: /^Update saved layout “Layout one”/ })).toBeChecked();
  await dialog.getByRole('switch', { name: /^Update saved layout “Layout two”/ }).uncheck();
  await dialog.getByLabel('Number (optional)', { exact: true }).fill('abc');
  await expect(dialog.getByText('Use a whole number from 1 up')).toBeVisible();
  await dialog.getByLabel('Number (optional)', { exact: true }).fill('');
  await hardware.selectOption('same_hardware');
  expect((await axe(page)).violations).toEqual([]);
  await review.click();
  await expect(dialog.getByText('Review what changes. Nothing is saved until you confirm.')).toBeVisible();
  await expect(cancel).toBeFocused();
  await expect(dialog.getByText('Tablet 3 takes Wall left’s place on the wall.', { exact: false })).toBeVisible();
  await expect(dialog.getByText('Saved layouts updated to use it: Layout one.')).toBeVisible();
  await expect(dialog.getByText('Saved layouts left as they are, still pointing at Wall left: Layout two.')).toBeVisible();
  await expect(dialog.getByText(`Name afterwards: Wall left. Number afterwards: ${oldNumber}.`)).toBeVisible();
  expect((await axe(page)).violations).toEqual([]);
  expect(sent.map(request => new URL(request.url()).pathname.split('/').at(-1))).toEqual(['preview']);
  const previewBody = sent[0]!.postDataJSON() as { replaces: string; saved_layouts: { name: string }[] };
  expect(previewBody).toMatchObject({ replaces: id1, hardware: 'same_hardware', active: true, transfer_label: true });
  expect(previewBody.saved_layouts.map(item => item.name)).toEqual(['Layout one']);
  await cancel.click();
  await expect(dialog).toBeHidden();
  expect(calls('/rebind')).toEqual([]);
  expect(await placed()).toEqual([id0, id1]);

  await offer.click();
  await hardware.selectOption('same_hardware');
  await dialog.getByRole('switch', { name: /^Update saved layout “Layout two”/ }).uncheck();
  await review.click();
  const replaceEtag = (await config()).etag;
  await dialog.getByRole('button', { name: 'Replace Wall left', exact: true }).click();
  await expect(dialog).toBeHidden();
  expect(calls('/rebind')).toHaveLength(1);
  const rebind = calls('/rebind')[0]!;
  expect(new URL(rebind.url()).pathname).toBe(`/api/v3/devices/${id2}/rebind`);
  expect(rebind.headers()['if-match']).toBe(replaceEtag);
  expect(rebind.postDataJSON()).toMatchObject({ replaces: id1, hardware: 'same_hardware', active: true, transfer_label: true,
    saved_layouts: [{ name: 'Layout one' }], new_connection_id: expect.any(String) });
  await expect(notice('Wall left replaced Wall left and took its place on the wall.')).toBeFocused();
  expect(await placed()).toEqual([id0, id2]);
  expect(await device(id1!)).toBeUndefined();
  expect((await config()).device_labels[DeviceIdSchema.parse(id2)]).toBe('Wall left');
  expect(await numberOf(id2!)).toBe(oldNumber);
  expect(await savedPlacements('Layout one')).toEqual([id0, id2]);
  expect(await savedPlacements('Layout two')).toEqual([id0, id1]);
  await online(id2!, true);
  await expect(page.getByRole('heading', { name: 'A new tablet joined' })).toHaveCount(0);

  // B: a different tablet, a typed number, no name transfer. A reconnect makes the review stale.
  sent.length = 0;
  await offline(id2!);
  await join(id1!);
  await online(id1!, true);
  await offer.click();
  await hardware.selectOption('different_hardware');
  await expect(dialog.getByText('A different tablet. It will need its own measurements.')).toBeVisible();
  await dialog.getByRole('switch', { name: /^Keep Wall left’s name/ }).uncheck();
  await dialog.getByLabel('Number (optional)', { exact: true }).fill('9');
  await review.click();
  await expect(dialog.getByText('Name afterwards: the generated name. Number afterwards: 9.')).toBeVisible();
  await expect(dialog.getByText(/will need its own measurements/)).toBeVisible();
  await live.get(id1!)!.page.reload();
  await expect(dialog.getByRole('alert').filter({ hasText: /Review again\./ })).toBeVisible();
  const confirm = dialog.getByRole('button', { name: /^Replace / });
  await expect(confirm).toBeDisabled();
  await online(id1!, true);
  expect(calls('/rebind')).toEqual([]);
  await dialog.getByRole('button', { name: 'Review again', exact: true }).click();
  await expect(hardware).toHaveValue('different_hardware');
  await expect(dialog.getByLabel('Number (optional)', { exact: true })).toHaveValue('9');
  await review.click();
  await confirm.click();
  await expect(dialog).toBeHidden();
  expect(calls('/rebind')).toHaveLength(1);
  expect(calls('/rebind')[0]!.postDataJSON()).toMatchObject({ hardware: 'different_hardware', transfer_label: false, number: 9 });
  await expect.poll(placed).toEqual([id0, id1]);
  expect(await numberOf(id1!)).toBe(9);
  expect((await config()).device_labels[DeviceIdSchema.parse(id1)] ?? null).toBeNull();
  await online(id1!, true);

  // C: the saved layouts change after the review, so the reviewed digest is stale and nothing is sent.
  sent.length = 0;
  await offline(id1!);
  await join(id2!);
  await online(id2!, true);
  await offer.click();
  await hardware.selectOption('same_hardware');
  await review.click();
  await expect(confirm).toBeEnabled();
  await save('Layout three');
  await expect(dialog.getByRole('alert').filter({ hasText: 'Something changed since you looked. Review it again.' })).toBeVisible();
  await expect(confirm).toBeDisabled();
  expect(calls('/rebind')).toEqual([]);
  await cancel.click();
  await expect(dialog).toBeHidden();
  expect(await placed()).toEqual([id0, id1]);

  // D: on a measured wall, a different tablet cannot take the place, and the same tablet brings its measurements.
  await join(id1!);
  await online(id1!, true);
  const measure = async (id: string) => {
    const viewport = (await device(id))?.viewport;
    if (!viewport) throw new Error('A report with the viewport is required.');
    const display = await api.request.put(`/api/v3/displays/${id}`, { headers: { 'If-Match': (await config()).etag }, data: {
      active_width_mm: 200, active_height_mm: 112.5, bezels: { left: 0, right: 0, top: 0, bottom: 0 }, panel_pixels: null, label: 'Measured', provenance: 'manual' } });
    expect(display.ok(), await display.text()).toBe(true);
    const shown = await display.json() as { etag: string; display: { revision: number } };
    const calibration = await api.request.put(`/api/v3/calibrations/${id}`, { headers: { 'If-Match': shown.etag }, data: {
      profile_revision: shown.display.revision, viewport_width: viewport.width, viewport_height: viewport.height, dpr: viewport.dpr,
      orientation: viewport.orientation, mode: viewport.mode, quarter_turn: 0, panel_offset_mm: [0, 0], mm_per_css: [0.25, 0.25],
      anchor_edge: 'top-left', uncertainty_mm: 0, method: 'manual', viewport_guard: true } });
    expect(calibration.ok(), await calibration.text()).toBe(true);
    const saved = await calibration.json() as { calibration: { revision: number } };
    return { profile_revision: shown.display.revision, calibration_revision: saved.calibration.revision };
  };
  const slot = (x: number, revisions: { profile_revision: number; calibration_revision: number }) =>
    ({ center_x_mm: x, center_y_mm: 56.25, mount_angle: 0, nudge_x_mm: 0, nudge_y_mm: 0, ...revisions });
  await api.placePhysical({ bounds: { x: 0, y: 0, width: 400, height: 112.5 },
    slots: { [id0!]: slot(100, await measure(id0!)), [id1!]: slot(300, await measure(id1!)) } });
  await offline(id1!);
  sent.length = 0;
  await expect(offer).toBeVisible();
  await offer.click();
  await hardware.selectOption('different_hardware');
  await review.click();
  await expect(dialog.getByText('A different tablet has different measurements. Measure it, then place it in Edit layout instead of replacing.')).toBeVisible();
  await expect(confirm).toBeDisabled();
  await expect(dialog.getByText('Fix the problems above first.')).toBeVisible();
  expect((await axe(page)).violations).toEqual([]);
  await dialog.getByRole('button', { name: 'Back', exact: true }).click();
  await hardware.selectOption('same_hardware');
  await review.click();
  await expect(dialog.getByText(/measurements are copied to/)).toBeVisible();
  await confirm.click();
  await expect(dialog).toBeHidden();
  expect(calls('/rebind')).toHaveLength(1);
  await expect.poll(placed).toEqual([id0, id2]);
  const moved = await config();
  expect(moved.displays.some(record => record.device_id === id2)).toBe(true);
  expect(moved.calibrations.some(record => record.device_id === id2)).toBe(true);
  await online(id2!, true);

  // E: an offline tablet is removed from the wall, then the Next step card leads to the replacement.
  sent.length = 0;
  await join(id1!);
  await online(id1!, true);
  await offline(id2!);
  await page.locator(`#tablet-row-${id2}`).click();
  const details = page.locator('details.tablet-lifecycle');
  if (!await details.evaluate(element => (element as HTMLDetailsElement).open)) await details.locator('summary').click();
  await details.getByRole('button', { name: 'Remove from wall', exact: true }).click();
  await page.getByRole('dialog', { name: /^Remove .* from the wall\?$/ }).getByRole('button', { name: 'Remove from wall', exact: true }).click();
  await expect.poll(placed).toEqual([id0]);
  expect(sent).toHaveLength(1);
  expect(sent[0]!.method()).toBe('DELETE');
  const next = page.getByRole('alert').filter({ has: page.getByRole('heading', { name: /^Next step: replace / }) });
  await expect(next).toBeVisible();
  await next.getByRole('button', { name: 'Review replacement', exact: true }).click();
  const use = page.locator('details.tablet-lifecycle').getByRole('button', { name: 'Use this tablet as a replacement', exact: true });
  await expect(use).toBeVisible();
  await use.click();
  await expect(dialog.getByLabel('Replace', { exact: true })).toHaveValue(id2!);
  await expect(dialog.getByRole('switch', { name: /^Take its place on the wall/ })).toHaveCount(0);
  await hardware.selectOption('same_hardware');
  await review.click();
  await expect(dialog.getByText('The wall’s layout is not changed.')).toBeVisible();
  await cancel.click();
  expect(calls('/rebind')).toEqual([]);
  expect(await placed()).toEqual([id0]);
});
