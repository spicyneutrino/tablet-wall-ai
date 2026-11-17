import { fileURLToPath } from 'node:url';
import { test, expect } from '../fixtures';

const image = fileURLToPath(new URL('../fixtures/images/EXLENT_Cohort_3_Flyer_Temp.png', import.meta.url));

test.use({ serverScope: 'parity-X6' });
test('X6 The page makes 0 CSP violations and 0 requests to another origin, so it loads with no WAN', async ({ page, server, api, tablets, guard }) => {
  test.setTimeout(180_000);
  const fleet = await tablets(4);
  await expect.poll(async () => Object.values((await api.config()).runtime.devices).filter(device => device.online).length).toBe(4);
  const asset = await api.upload(image);
  await api.placeLogical({ columns: 2, rows: 2, deviceIds: fleet.map(tablet => tablet.id) });
  await api.scene({ type: 'image', asset: asset.id, fit: 'cover' });

  const foreignRequests: string[] = [];
  const foreignSockets: string[] = [];
  // The context sees requests from workers as well as the page.
  page.context().on('request', request => {
    if (new URL(request.url()).origin !== server.origin) foreignRequests.push(`${request.method()} ${request.url()}`);
  });
  page.on('websocket', socket => {
    if (new URL(socket.url()).host !== new URL(server.origin).host) foreignSockets.push(socket.url());
  });
  await page.addInitScript(() => {
    const state: string[] = [];
    Reflect.set(window, '__designCsp', state);
    document.addEventListener('securitypolicyviolation', event => {
      state.push(`${event.violatedDirective} ${event.blockedURI}`);
    });
  });
  await guard(page);
  const response = await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  const policy = response?.headers()['content-security-policy'] ?? '';
  expect(policy, 'the console page is served with a Content-Security-Policy, so 0 violations means something').toContain("default-src 'self'");
  expect(policy.match(/https?:\/\/[^\s;]+/g) ?? [], 'the policy names no outside origin').toEqual([]);
  await expect(page.locator('#tablet-health .state-ok')).toHaveCount(4, { timeout: 20_000 });
  const csp = () => page.evaluate(() => Reflect.get(window, '__designCsp') as string[]);
  const states: { state: string; csp: string[]; foreignRequests: string[]; foreignSockets: string[] }[] = [];
  async function record(state: string) {
    await page.waitForTimeout(400);
    states.push({
      state,
      csp: await csp(),
      foreignRequests: [...foreignRequests],
      foreignSockets: [...foreignSockets],
    });
  }

  await record('main');
  const screen = page.locator('[data-stage="preview"] [data-screen]').first();
  const box = await screen.boundingBox();
  if (!box) throw new Error('The 2x2 fixture must draw a selectable screen.');
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect(page.locator('[data-stage="preview"] [data-selected="true"]')).toHaveCount(1);
  await record('selected');

  await page.getByRole('button', { name: 'Server', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'Server', exact: true });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByRole('heading', { name: 'Diagnostics', exact: true })).toBeVisible();
  await record('server');
  await page.getByRole('button', { name: 'Close Server', exact: true }).click();
  await expect(sheet).not.toBeVisible();

  await page.getByRole('button', { name: 'All images', exact: true }).click();
  const library = page.getByRole('dialog', { name: 'Library', exact: true });
  await expect(library).toBeVisible();
  await record('library');

  for (const entry of states) {
    expect(entry.csp, `${entry.state}: CSP violations`).toEqual([]);
    expect(entry.foreignRequests, `${entry.state}: requests to another origin`).toEqual([]);
    expect(entry.foreignSockets, `${entry.state}: websockets to another origin`).toEqual([]);
  }
  expect(foreignRequests, 'no request left the server origin').toEqual([]);
  expect(foreignSockets, 'no websocket left the server origin').toEqual([]);
  expect(await csp(), 'no CSP violation for the whole session').toEqual([]);
  console.log(`X6: main, selected, Server and Library made 0 CSP violations, 0 foreign requests and 0 foreign websockets`);
});
