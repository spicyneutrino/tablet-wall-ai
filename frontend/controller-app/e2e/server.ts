import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, rm } from 'node:fs/promises';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';

export async function startServer() {
  const listener = createServer();
  listener.listen(0, '127.0.0.1');
  await once(listener, 'listening');
  const address = listener.address();
  if (!address || typeof address === 'string') throw new Error('Missing test server port');
  const port = address.port;
  await new Promise<void>((resolve, reject) => listener.close((error) => error ? reject(error) : resolve()));
  const origin = `http://127.0.0.1:${port}`;
  const directory = await mkdtemp(join(tmpdir(), 'tablet-wall-u01-'));
  const env = Object.fromEntries(Object.entries(process.env)
    .filter(([key]) => !key.startsWith('TABLET_WALL_') && !key.startsWith('WALL_')));
  const token = process.env.TABLET_WALL_AUTH_TOKEN;
  Object.assign(env, {
    TABLET_WALL_DB: join(directory, 'wall.db'),
    TABLET_WALL_ASSET_DIR: join(directory, 'assets'),
    TABLET_WALL_MEDIA_DIR: join(directory, 'media'),
    TABLET_WALL_BACKUP_DIR: join(directory, 'backups'),
    TABLET_WALL_TABLET_ORIGIN: origin,
    TABLET_WALL_OPERATOR_ORIGIN: origin,
    TABLET_WALL_UPLOAD_MODE: 'loopback',
    TABLET_WALL_WIFI_NAME: 'QA',
    ...(token ? { TABLET_WALL_AUTH_TOKEN: token } : {}),
  });
  const child = spawn('uv', ['run', 'fastapi', 'run', 'main.py', '--host', '127.0.0.1', '--port', String(port)], {
    cwd: fileURLToPath(new URL('../../../', import.meta.url)), env,
    detached: true, stdio: ['ignore', 'pipe', 'pipe'],
  });
  let logs = '';
  child.stdout.on('data', (data: Buffer) => { logs = (logs + data.toString()).slice(-16_000); });
  child.stderr.on('data', (data: Buffer) => { logs = (logs + data.toString()).slice(-16_000); });
  const exited = once(child, 'exit');
  async function stop() {
    if (child.exitCode === null && child.signalCode === null && child.pid) {
      process.kill(-child.pid, 'SIGTERM');
      const stopped = await Promise.race([exited.then(() => true), delay(5_000).then(() => false)]);
      if (!stopped) { process.kill(-child.pid, 'SIGKILL'); await exited; }
    }
    await rm(directory, { recursive: true, force: true });
  }
  try {
    for (let attempt = 0; attempt < 150; attempt++) {
      if (child.exitCode !== null || child.signalCode !== null) throw new Error(logs);
      try {
        const response = await fetch(`${origin}/healthz`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          signal: AbortSignal.timeout(500),
        });
        if (response.status === 200) return { origin, stop };
      } catch { /* The child may still be starting. */ }
      await delay(100);
    }
    throw new Error(`Test server did not become ready.\n${logs}`);
  } catch (error) {
    await stop();
    throw error;
  }
}
