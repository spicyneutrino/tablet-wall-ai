import type { WebSocketRoute } from '@playwright/test';
import { test, expect } from './fixtures';
import { fleet } from './fixtures/fleet';

test('one controller socket per page, with a reconnect within 3.5 seconds after close', async ({ page, server, guard, writes }) => {
  await guard(page);
  const mutations = writes(page);
  const sockets: WebSocketRoute[] = [];
  await page.routeWebSocket('**/ws/controller?protocol=3', (socket) => {
    sockets.push(socket);
    socket.connectToServer();
  });
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  await expect(page.getByRole('status')).toContainText('Live operator updates connected.');
  expect(sockets).toHaveLength(1);
  const closedAt = Date.now();
  await sockets[0]!.close({ code: 1001, reason: 'U04 reconnect check' });
  await expect.poll(() => sockets.length, { timeout: 3500, intervals: [50] }).toBe(2);
  expect(Date.now() - closedAt).toBeLessThanOrEqual(3500);
  await expect(page.getByRole('status')).toContainText('Live operator updates connected.');
  expect(sockets).toHaveLength(2);
  expect(mutations).toEqual([]);
  await page.screenshot({ path: test.info().outputPath('session-connected.png'), fullPage: true });
});

test('periodic reconcile shows an API label change within 16 seconds while sockets are blocked', async ({ page, server, api, tablets, guard, writes }) => {
  await tablets(1);
  await guard(page);
  const mutations = writes(page);
  let sockets = 0;
  let reads = 0;
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/v3/config' && request.method() === 'GET') reads += 1;
  });
  await page.routeWebSocket('**/ws/controller?protocol=3', () => { sockets += 1; });
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'networkidle' });
  await expect(page.getByRole('list', { name: 'Tablets' }).getByRole('listitem')).toHaveCount(1);
  const readsBefore = reads;
  const { etag } = await api.config();
  const changedAt = Date.now();
  const response = await api.request.patch(`/api/v3/devices/${fleet[0].id}`, {
    data: { label: 'Reconciled tablet' }, headers: { 'If-Match': etag },
  });
  expect(response.ok(), await response.text()).toBe(true);
  await expect(page.getByRole('list', { name: 'Tablets' })).toContainText('Reconciled tablet', { timeout: 16000 });
  expect(Date.now() - changedAt).toBeLessThanOrEqual(16000);
  expect(reads).toBeGreaterThan(readsBefore);
  expect(sockets).toBe(1);
  expect(mutations).toEqual([]);
  await page.screenshot({ path: test.info().outputPath('session-reconciled.png'), fullPage: true });
});
