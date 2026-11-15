import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { basename, extname, join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import { test as base, expect } from '@playwright/test';
import type { APIRequestContext, BrowserContext, BrowserContextOptions, Page, Request } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { z } from 'zod';
import { fleet } from './fixtures/fleet';

const configSchema = z.looseObject({
  etag: z.string(),
  runtime: z.looseObject({ devices: z.record(z.string(), z.looseObject({
    online: z.boolean(), render: z.looseObject({ state: z.string() }),
  })) }),
});
const assetSchema = z.looseObject({ id: z.string(), intrinsicWidth: z.number(), intrinsicHeight: z.number() });
export type Config = z.infer<typeof configSchema>;
export type SceneInput = { type: 'color' | 'calibration' } |
  { type: 'image'; asset: string; fit: 'cover' | 'contain'; background?: string };
export type LogicalGrid = {
  columns: number; rows: number; deviceIds: readonly string[];
  cellWidth?: number; cellHeight?: number;
};
export type PhysicalSlot = {
  center_x_mm: number; center_y_mm: number; mount_angle: number;
  nudge_x_mm: number; nudge_y_mm: number;
  profile_revision: number; calibration_revision: number; participating?: boolean;
};
export type PhysicalLayout = {
  bounds: { x: number; y: number; width: number; height: number };
  slots: Record<string, PhysicalSlot>;
};
export type Tablet = { id: string; context: BrowserContext; page: Page };
type Server = { origin: string; port: number; directory: string };
type Api = {
  request: APIRequestContext;
  config: () => Promise<Config>;
  placeLogical: (grid: LogicalGrid) => Promise<Config>;
  placePhysical: (layout: PhysicalLayout) => Promise<Config>;
  upload: (file: string) => Promise<z.infer<typeof assetSchema>>;
  scene: (input: SceneInput) => Promise<Config>;
};
type Fixtures = {
  api: Api;
  tablets: (count: number, options?: BrowserContextOptions & { ids?: readonly string[] }) => Promise<Tablet[]>;
  writes: (page: Page) => Request[];
  tabletPixel: (tablet: Tablet, x: number, y: number) => Promise<number[]>;
  guard: (page: Page) => Promise<void>;
  axe: (page: Page) => Promise<Awaited<ReturnType<AxeBuilder['analyze']>>>;
  stageBox: (page: Page) => Promise<{ x: number; y: number; width: number; height: number }>;
};

export const test = base.extend<Fixtures, { server: Server }>({
  server: [async ({}, use, workerInfo) => {
    const listener = createServer();
    listener.listen(0, '127.0.0.1');
    await once(listener, 'listening');
    const address = listener.address();
    if (!address || typeof address === 'string') throw new Error('Missing server port');
    const port = address.port;
    await new Promise<void>((resolve, reject) => listener.close((error) => error ? reject(error) : resolve()));
    expect(port).not.toBe(8012);
    const origin = `http://127.0.0.1:${port}`;
    const directory = await mkdtemp(join(tmpdir(), 'tablet-wall-e2e-'));
    const env = Object.fromEntries(Object.entries(process.env)
      .filter(([key]) => !key.startsWith('TABLET_WALL_') && !key.startsWith('WALL_')));
    Object.assign(env, {
      TABLET_WALL_DB: join(directory, 'wall.db'),
      TABLET_WALL_ASSET_DIR: join(directory, 'assets'),
      TABLET_WALL_MEDIA_DIR: join(directory, 'media'),
      TABLET_WALL_BACKUP_DIR: join(directory, 'backups'),
      TABLET_WALL_TABLET_ORIGIN: origin, TABLET_WALL_OPERATOR_ORIGIN: origin,
      TABLET_WALL_UPLOAD_MODE: 'loopback', TABLET_WALL_WIFI_NAME: 'QA',
    });
    const child = spawn('uv', ['run', 'fastapi', 'run', 'main.py', '--host', '127.0.0.1', '--port', String(port)], {
      cwd: fileURLToPath(new URL('../../../', import.meta.url)), env,
      detached: true, stdio: ['ignore', 'pipe', 'pipe'],
    });
    let logs = '';
    let spawnError: Error | undefined;
    child.on('error', (error) => { spawnError = error; });
    child.stdout.on('data', (data: Buffer) => { logs = (logs + data.toString()).slice(-16_000); });
    child.stderr.on('data', (data: Buffer) => { logs = (logs + data.toString()).slice(-16_000); });
    const exited = new Promise<void>((resolve) => child.once('close', () => resolve()));
    try {
      await expect.poll(async () => {
        if (spawnError) throw spawnError;
        if (child.exitCode !== null || child.signalCode !== null) throw new Error(logs);
        return fetch(`${origin}/healthz`, { signal: AbortSignal.timeout(500) })
          .then((response) => response.status).catch(() => 0);
      }, { timeout: 15_000, message: 'FastAPI must become healthy' }).toBe(200);
      await writeFile(join(workerInfo.config.metadata.runDirectory, `worker-${workerInfo.workerIndex}.json`),
        JSON.stringify({ worker: workerInfo.workerIndex, port, origin }));
      await use({ origin, port, directory });
    } finally {
      if (child.pid && child.exitCode === null && child.signalCode === null) {
        process.kill(-child.pid, 'SIGTERM');
        if (!await Promise.race([exited.then(() => true), delay(5_000).then(() => false)])) {
          process.kill(-child.pid, 'SIGKILL');
          await exited;
        }
      }
      await rm(directory, { recursive: true, force: true });
    }
  }, { scope: 'worker', timeout: 25_000 }],

  api: async ({ playwright, server }, use) => {
    const request = await playwright.request.newContext({ baseURL: server.origin,
      extraHTTPHeaders: { Origin: server.origin } });
    async function config() {
      const response = await request.get('/api/v3/config');
      expect(response.ok(), await response.text()).toBe(true);
      const value = configSchema.parse(await response.json());
      expect(response.headers().etag?.replaceAll('"', '')).toBe(value.etag.replaceAll('"', ''));
      return value;
    }
    async function put(path: string, data: unknown) {
      const { etag } = await config();
      const response = await request.put(path, { data, headers: { 'If-Match': etag } });
      expect(response.ok(), await response.text()).toBe(true);
      return configSchema.parse(await response.json());
    }
    try {
      await use({ request, config,
        placeLogical: ({ columns, rows, deviceIds, cellWidth = 800, cellHeight = 450 }) => {
          if (!Number.isInteger(columns) || columns < 1 || !Number.isInteger(rows) || rows < 1 || deviceIds.length > columns * rows) {
            throw new Error('Logical grid needs positive integer dimensions and enough cells');
          }
          return put('/api/v3/logical-layout', {
            width: columns * cellWidth, height: rows * cellHeight,
            placements: Object.fromEntries(deviceIds.map((id, index) => [id, {
              device_id: id, x: (index % columns) * cellWidth, y: Math.floor(index / columns) * cellHeight,
              w: cellWidth, h: cellHeight, bezel: { left: 0, right: 0, top: 0, bottom: 0 },
            }])), sizing: { mode: 'fixed', padding: 0 },
          });
        },
        placePhysical: (layout) => put('/api/v3/layout', layout),
        scene: (input) => put('/api/v3/scene', { content: input }),
        upload: async (file) => {
          const contentType = extname(file).toLowerCase() === '.png' ? 'image/png' : 'image/jpeg';
          const response = await request.post(`/uploads?name=${encodeURIComponent(basename(file))}`, {
            data: await readFile(file), headers: { 'Content-Type': contentType },
          });
          expect(response.status(), await response.text()).toBe(201);
          return z.object({ state: z.literal('ready'), asset: assetSchema }).parse(await response.json()).asset;
        },
      });
    } finally { await request.dispose(); }
  },

  tablets: async ({ browser, server, guard }, use) => {
    const contexts: BrowserContext[] = [];
    try {
      await use(async (count, { ids = fleet.map((tablet) => tablet.id), ...options } = {}) => {
        if (!Number.isInteger(count) || count < 1 || count > ids.length) throw new Error('Tablet count exceeds fleet');
        return Promise.all(ids.slice(0, count).map(async (id, index) => {
          const context = await browser.newContext({ viewport: fleet[index]?.viewport, ...options });
          contexts.push(context);
          await context.addInitScript((deviceId) => localStorage.setItem('tablet-wall-device-id', deviceId), id);
          const page = await context.newPage();
          await guard(page);
          await page.goto(`${server.origin}/client/`);
          return { id, context, page };
        }));
      });
    } finally { await Promise.all(contexts.map((context) => context.close())); }
  },

  writes: async ({ server }, use) => {
    const listeners: { page: Page; listener: (request: Request) => void }[] = [];
    try {
      await use((page) => {
        const records: Request[] = [];
        const listener = (request: Request) => {
          const url = new URL(request.url());
          if (url.origin === server.origin && request.method() !== 'GET' && /^\/(api|devices|uploads|media)(\/|$)/.test(url.pathname)) records.push(request);
        };
        page.on('request', listener);
        listeners.push({ page, listener });
        return records;
      });
    } finally { for (const { page, listener } of listeners) page.off('request', listener); }
  },

  tabletPixel: async ({}, use) => {
    await use((tablet, x, y) => tablet.page.locator('#surface').evaluate((canvas, point) => {
      if (!(canvas instanceof HTMLCanvasElement)) throw new Error('Tablet surface must be a canvas');
      const context = canvas.getContext('2d');
      if (!context) throw new Error('Tablet canvas has no 2d context');
      return [...context.getImageData(Math.floor(point.x), Math.floor(point.y), 1, 1).data];
    }, { x, y }));
  },

  guard: async ({ server }, use) => {
    const errors: string[] = [];
    const cleanups: (() => void)[] = [];
    try {
      await use(async (page) => {
        const report = (message: string) => { errors.push(message); };
        const binding = `reportGuard${cleanups.length}`;
        await page.exposeBinding(binding, (_, message: string) => report(message));
        await page.addInitScript((name) => {
          document.addEventListener('securitypolicyviolation', (event) => {
            const callback = Reflect.get(window, name);
            void callback(`CSP ${event.violatedDirective} ${event.blockedURI}`);
          });
        }, binding);
        const onError = (error: Error) => report(error.message);
        const onConsole = (message: import('@playwright/test').ConsoleMessage) => {
          if (message.type() === 'error') report(message.text());
        };
        const onRequest = (request: Request) => {
          if (new URL(request.url()).origin !== server.origin) report(`External request ${request.url()}`);
        };
        const onSocket = (socket: import('@playwright/test').WebSocket) => {
          if (new URL(socket.url()).host !== new URL(server.origin).host) report(`External websocket ${socket.url()}`);
        };
        page.on('pageerror', onError).on('console', onConsole).on('request', onRequest).on('websocket', onSocket);
        cleanups.push(() => { page.off('pageerror', onError).off('console', onConsole).off('request', onRequest).off('websocket', onSocket); });
      });
    } finally {
      for (const cleanup of cleanups) cleanup();
      expect(errors, 'Normal browser context must have no CSP, console, page or origin errors').toEqual([]);
    }
  },

  axe: async ({ browser }, use) => {
    const analyze = (page: Page) => new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
    await use(async (page) => {
      try { return await analyze(page); } catch (error) {
        if (!(error instanceof Error) || !/content security policy|unsafe-eval|script-src/i.test(error.message)) throw error;
        const context = await browser.newContext({ bypassCSP: true,
          storageState: await page.context().storageState(), viewport: page.viewportSize() });
        try {
          const axePage = await context.newPage();
          await axePage.goto(page.url(), { waitUntil: 'networkidle' });
          return await analyze(axePage);
        } finally { await context.close(); }
      }
    });
  },

  stageBox: async ({}, use) => {
    await use((page) => page.locator('[data-stage="preview"]').evaluate((stage) => {
      const { x, y, width, height } = stage.getBoundingClientRect();
      return { x, y, width, height };
    }));
  },
});

export { expect };
