import { defineConfig, devices } from '@playwright/test';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

if (!process.env.CONTROLLER_E2E_RUN_DIRECTORY) {
  const directory = mkdtempSync(join(tmpdir(), 'tablet-wall-e2e-run-'));
  process.env.CONTROLLER_E2E_RUN_DIRECTORY = directory;
  process.env.CONTROLLER_E2E_CHECK_PORTS = String(!process.argv.some((arg) => arg.startsWith('--project')));
  process.once('exit', () => rmSync(directory, { recursive: true, force: true }));
}

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 2,
  timeout: 30_000,
  reporter: 'list',
  metadata: { runDirectory: process.env.CONTROLLER_E2E_RUN_DIRECTORY,
    checkWorkerPorts: process.env.CONTROLLER_E2E_CHECK_PORTS === 'true' },
  expect: { toHaveScreenshot: { animations: 'disabled', maxDiffPixelRatio: 0.002 } },
  projects: [
    { name: 'phone', use: { viewport: { width: 390, height: 844 } } },
    { name: 'tablet', use: { viewport: { width: 820, height: 1180 } } },
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'webkit-desktop', use: { browserName: 'webkit', viewport: { width: 1440, height: 900 } },
      testIgnore: process.argv.some((arg) => arg === '--project=webkit-desktop' || arg === 'webkit-desktop') ? undefined : '**/*' },
  ],
  use: { ...devices['Desktop Chrome'],
    trace: 'retain-on-failure' },
});
